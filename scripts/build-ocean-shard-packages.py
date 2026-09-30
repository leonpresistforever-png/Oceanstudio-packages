#!/usr/bin/env python3
"""Build verified Ocean shard/multiplier .deb packages for git-distribution staging."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "packages/ocean-shard-multiplier"
OUT = ROOT / "staging/shard-multiplier"
PREFIX = "/data/data/studio.ocean.app/files/usr"
VERSION = "1.0.0-1+ocean1"

PACKAGES = (
    ("ocean-shard-router", "ocean-shard-router", "Composable JSON route multiplexer for agent tools"),
    ("ocean-shard-auth-store", "ocean-shard-auth-store", "Split/merge auth secrets across integrity-tagged shards"),
    ("ocean-shard-tool-mux", "ocean-shard-tool-mux", "Multiplex stdin to multiple Ocean plugin handlers"),
    ("ocean-shard-agent-flow", "ocean-shard-agent-flow", "Sequential JSON workflow runner for agent orchestration"),
    ("ocean-shard-blob-split", "ocean-shard-blob-split", "Content-addressed blob splitter and joiner for storage shards"),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_one(package: str, script_name: str, description: str, pool: Path) -> dict[str, object]:
    source = SRC / script_name
    if not source.is_file():
        raise SystemExit(f"Missing shard source: {source}")
    with tempfile.TemporaryDirectory(prefix=f"{package}-") as temporary:
        stage = Path(temporary)
        stage.chmod(0o755)
        root = stage / PREFIX.lstrip("/")
        (root / "bin").mkdir(parents=True, exist_ok=True)
        curr = root / "bin"
        while curr != stage:
            curr.chmod(0o755)
            curr = curr.parent
        dest = root / "bin" / script_name
        shutil.copy2(source, dest)
        dest.chmod(0o755)
        debian = stage / "DEBIAN"
        debian.mkdir(parents=True, exist_ok=True)
        debian.chmod(0o755)
        control = "\n".join(
            [
                f"Package: {package}",
                f"Version: {VERSION}",
                "Architecture: all",
                "Maintainer: OceanStudio <maintainer@ocean.studio>",
                "Depends: python",
                "Section: utils",
                "Priority: optional",
                f"Description: {description}",
                "",
            ]
        )
        (debian / "control").write_text(control)
        (debian / "control").chmod(0o644)
        for path in stage.rglob("*"):
            os.utime(path, (0, 0), follow_symlinks=False)
        deb = pool / f"{package}_{VERSION}_all.deb"
        subprocess.run(
            ["dpkg-deb", "--root-owner-group", "-Zxz", "-z6", "--build", str(stage), str(deb)],
            check=True,
        )
        sys_path = ROOT / "scripts"
        import sys

        if str(sys_path) not in sys.path:
            sys.path.insert(0, str(sys_path))
        from package_quality import assess_deb

        verdict = assess_deb(deb)
        if verdict.reject:
            raise SystemExit(f"Quality gate rejected {package}: {verdict.reasons}")
        return {
            "package": package,
            "version": VERSION,
            "artifact": deb.name,
            "sha256": sha256_file(deb),
            "bytes": deb.stat().st_size,
            "shard": "ocean-multiplier",
        }


def main() -> int:
    pool = OUT / "pool/main/ocean-shard"
    pool.mkdir(parents=True, exist_ok=True)
    built = [build_one(*row, pool) for row in PACKAGES]
    manifest = {
        "schemaVersion": 1,
        "distribution": "git-staging-only",
        "packages": built,
    }
    manifest_path = ROOT / "sources/shard-multiplier-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"built": len(built), "staging": str(OUT), "manifest": str(manifest_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
