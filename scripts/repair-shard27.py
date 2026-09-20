#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

PREFIX = "/data/data/studio.ocean.app/files/usr"
VERSION = "1.0.0-2"

def load_runtime(path: Path):
    spec = importlib.util.spec_from_file_location("shard27_runtime", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod

def load_batch(path: Path):
    spec = importlib.util.spec_from_file_location("shard_batch4", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod.BATCH4_SHARDS["shard-27-data-stream-etl"]["packages"]

def run(cmd):
    r = subprocess.run(cmd, text=True, capture_output=True)
    if r.returncode:
        raise SystemExit(f"command failed: {' '.join(cmd)}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}")
    return r

def hashes(path: Path):
    data = path.read_bytes()
    return {
        "size": len(data),
        "md5": hashlib.md5(data).hexdigest(),
        "sha1": hashlib.sha1(data).hexdigest(),
        "sha256": hashlib.sha256(data).hexdigest(),
    }

def normalize(root: Path):
    for p in sorted(root.rglob("*"), reverse=True):
        try:
            if p.is_dir() or "/bin/" in str(p):
                p.chmod(0o755)
            else:
                p.chmod(0o644)
            os.utime(p, (0, 0), follow_symlinks=False)
        except FileNotFoundError:
            pass
    root.chmod(0o755)
    os.utime(root, (0, 0))

def build_one(name: str, desc: str, runtime_text: str, out: Path):
    deb = out / f"{name}_{VERSION}_aarch64.deb"
    with tempfile.TemporaryDirectory(prefix=f"ocean-{name}-") as td:
        root = Path(td)
        (root / "DEBIAN").mkdir(parents=True)
        runtime = root / PREFIX.lstrip("/") / "lib/ocean-functional-shards/shard27_etl.py"
        runtime.parent.mkdir(parents=True)
        runtime.write_text(runtime_text, encoding="utf-8")
        runtime.chmod(0o644)

        wrapper = root / PREFIX.lstrip("/") / "bin" / name
        wrapper.parent.mkdir(parents=True, exist_ok=True)
        wrapper.write_text(
            f"""#!{PREFIX}/bin/bash
exec {PREFIX}/bin/python {PREFIX}/lib/ocean-functional-shards/shard27_etl.py {name} "$@"
""",
            encoding="utf-8",
        )
        wrapper.chmod(0o755)

        doc = root / PREFIX.lstrip("/") / "share/doc" / name / "README.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text(
            f"""# {name}

{desc}

This package is part of OceanStudio's repaired functional shard 27.
Unlike the earlier placeholder build, this version executes real data-processing logic.

Version: {VERSION}
Runtime: Python standard library only
Prefix: {PREFIX}
""",
            encoding="utf-8",
        )

        control = root / "DEBIAN/control"
        control.write_text(
            f"""Package: {name}
Version: {VERSION}
Architecture: aarch64
Maintainer: OceanStudio Packaging Team <maintainer@ocean.studio>
Section: utils
Priority: optional
Depends: python
Description: {desc}
 Functional OceanStudio implementation for Android AArch64.
 This repair replaces the earlier generic passthrough placeholder.
""",
            encoding="utf-8",
        )
        normalize(root)
        run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", str(root), str(deb)])
    return deb

def stanza(name: str, desc: str, deb: Path):
    h = hashes(deb)
    return f"""Package: {name}
Version: {VERSION}
Architecture: aarch64
Maintainer: OceanStudio Packaging Team <maintainer@ocean.studio>
Depends: python
Filename: pool/main/{deb.name}
Size: {h['size']}
MD5sum: {h['md5']}
SHA1: {h['sha1']}
SHA256: {h['sha256']}
Section: utils
Priority: optional
Description: {desc}
 Functional OceanStudio implementation for Android AArch64.
 This repair replaces the earlier generic passthrough placeholder."""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime", required=True)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--live-packages", required=True)
    ns = ap.parse_args()

    runtime_path = Path(ns.runtime)
    batch_path = Path(ns.batch)
    output = Path(ns.output)
    live_packages = Path(ns.live_packages)

    runtime_mod = load_runtime(runtime_path)
    batch = load_batch(batch_path)
    expected = [name for name, version, desc in batch]
    if len(expected) != 50 or len(set(expected)) != 50:
        raise SystemExit("shard 27 source list must contain exactly 50 unique names")
    if set(expected) != set(runtime_mod.COMMANDS):
        missing = sorted(set(expected) - set(runtime_mod.COMMANDS))
        extra = sorted(set(runtime_mod.COMMANDS) - set(expected))
        raise SystemExit(f"runtime command mismatch: missing={missing}, extra={extra}")

    live_text = live_packages.read_text(encoding="utf-8", errors="replace")
    for name in expected:
        if f"Package: {name}\n" not in live_text:
            raise SystemExit(f"expected live placeholder package missing: {name}")

    shutil.rmtree(output, ignore_errors=True)
    pool = output / "pool/main"
    pool.mkdir(parents=True)
    runtime_text = runtime_path.read_text(encoding="utf-8")

    stanzas = []
    provenance = []
    for name, old_version, desc in batch:
        deb = build_one(name, desc, runtime_text, pool)
        run(["dpkg-deb", "--info", str(deb)])
        extracted = output / ".verify" / name
        extracted.mkdir(parents=True, exist_ok=True)
        run(["dpkg-deb", "-x", str(deb), str(extracted)])
        wrapper = extracted / PREFIX.lstrip("/") / "bin" / name
        runtime_copy = extracted / PREFIX.lstrip("/") / "lib/ocean-functional-shards/shard27_etl.py"
        if not wrapper.exists() or not runtime_copy.exists():
            raise SystemExit(f"payload verification failed: {name}")
        data = deb.read_bytes()
        for forbidden in (b"/data/data/com.termux", b"/data/user/0/com.termux", b"packages.termux.dev", b"TERMUX_PREFIX"):
            if forbidden in data:
                raise SystemExit(f"forbidden Termux reference found in {name}")
        h = hashes(deb)
        stanzas.append(stanza(name, desc, deb))
        provenance.append({
            "package": name,
            "replacesVersion": old_version,
            "version": VERSION,
            "artifact": deb.name,
            "sha256": h["sha256"],
            "size": h["size"],
            "implementation": "sources/functional-shards/shard27_etl.py",
            "status": "functional-repair",
        })

    shutil.rmtree(output / ".verify", ignore_errors=True)
    (output / "Packages.repaired").write_text("\n\n".join(stanzas) + "\n", encoding="utf-8")
    (output / "provenance.json").write_text(
        json.dumps({
            "schemaVersion": 2,
            "shard": "shard-27-data-stream-etl",
            "category": "Data Streaming & ETL Pipelines",
            "repair": "placeholder-to-functional",
            "target": "aarch64-linux-android28",
            "prefix": PREFIX,
            "packageCount": 50,
            "uniquePackageCount": 50,
            "version": VERSION,
            "packages": provenance,
        }, indent=2) + "\n",
        encoding="utf-8",
    )

    built = list(pool.glob("*.deb"))
    if len(built) != 50:
        raise SystemExit(f"expected 50 debs, got {len(built)}")
    if sum(1 for x in (output / "Packages.repaired").read_text().splitlines() if x.startswith("Package: ")) != 50:
        raise SystemExit("repaired index count mismatch")
    print("SUCCESS: rebuilt 50 shard-27 packages as functional implementations")

if __name__ == "__main__":
    main()
