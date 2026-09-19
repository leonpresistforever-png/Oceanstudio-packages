#!/usr/bin/env python3
"""Build the isolated Ocean Toybox expansion from pinned official upstream source.

This builder never consumes Termux packages or binary caches. It fetches the
exact upstream Git commit declared in sources/toybox-0.8.14/manifest.json,
cross-compiles one Android/ARM64 Toybox multicall binary, and creates namespaced
Ocean subpackages (tb-<applet>) so existing package command ownership is not
modified.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "sources/toybox-0.8.14/manifest.json"
FORBIDDEN = (b"/data/data/com.termux", b"/data/user/0/com.termux", b"packages.termux.dev", b"TERMUX_PREFIX")

def run(command, *, cwd=None, env=None, capture=False):
    print("+", " ".join(map(str, command)), flush=True)
    return subprocess.run(list(map(str, command)), cwd=cwd, env=env, check=True,
                          text=True, stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.STDOUT if capture else None)

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def require(command: str) -> str:
    value = shutil.which(command)
    if not value:
        raise SystemExit(f"required command missing: {command}")
    return value

def write_control(stage: Path, fields: list[tuple[str, str]]) -> None:
    control = stage / "DEBIAN"
    control.mkdir(parents=True)
    text = "".join(f"{key}: {value}\n" for key, value in fields)
    (control / "control").write_text(text)

def normalize_times(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        try:
            os.utime(path, (0, 0), follow_symlinks=False)
        except FileNotFoundError:
            pass
    os.utime(root, (0, 0))

def build_deb(stage: Path, output: Path) -> None:
    normalize_times(stage)
    output.parent.mkdir(parents=True, exist_ok=True)
    run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", stage, output])

def source_checkout(manifest: dict, destination: Path) -> None:
    run(["git", "init", "-q", destination])
    run(["git", "-C", destination, "remote", "add", "origin", manifest["sourceUrl"]])
    run(["git", "-C", destination, "fetch", "--depth=1", "origin", manifest["commit"]])
    run(["git", "-C", destination, "checkout", "--detach", "-q", "FETCH_HEAD"])
    head = run(["git", "-C", destination, "rev-parse", "HEAD"], capture=True).stdout.strip()
    tree = run(["git", "-C", destination, "rev-parse", "HEAD^{tree}"], capture=True).stdout.strip()
    license_blob = run(["git", "-C", destination, "rev-parse", "HEAD:LICENSE"], capture=True).stdout.strip()
    miniconfig_blob = run(["git", "-C", destination, "rev-parse", "HEAD:scripts/android_miniconfig"], capture=True).stdout.strip()
    expected = (manifest["commit"], manifest["tree"], manifest["licenseBlob"], manifest["androidMiniconfigBlob"])
    actual = (head, tree, license_blob, miniconfig_blob)
    if actual != expected:
        raise SystemExit(f"official source identity mismatch: expected={expected!r} actual={actual!r}")
    remote = run(["git", "-C", destination, "remote", "get-url", "origin"], capture=True).stdout.strip()
    if remote != manifest["sourceUrl"]:
        raise SystemExit("upstream URL changed during checkout")

def compile_toybox(manifest: dict, source: Path, ndk: Path, work: Path) -> tuple[Path, list[str]]:
    toolchain = ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin"
    clang = toolchain / "clang"
    strip = toolchain / "llvm-strip"
    readelf = toolchain / "llvm-readelf"
    for path in (clang, strip, readelf):
        if not path.is_file():
            raise SystemExit(f"NDK tool missing: {path}")

    wrapper = work / "android-clang"
    wrapper.write_text(f"#!/bin/sh\nexec {clang} --target={manifest['target']} \"$@\"\n")
    wrapper.chmod(0o755)

    miniconfig = work / "ocean_miniconfig"
    symbols = []
    for applet in manifest["applets"]:
        symbol = applet.upper().replace("-", "_")
        if not re.fullmatch(r"[A-Z0-9_]+", symbol):
            raise SystemExit(f"invalid applet symbol: {applet}")
        symbols.append(symbol)
    feature_symbols = ["TOYBOX_FLOAT", "TOYBOX_HELP"]
    miniconfig.write_text(
        "".join(f"CONFIG_{symbol}=y\n" for symbol in symbols)
        + "".join(f"CONFIG_{symbol}=y\n" for symbol in feature_symbols)
    )

    env = dict(os.environ)
    env.update({
        "KCONFIG_ALLCONFIG": str(miniconfig),
        "CC": str(wrapper),
        "HOSTCC": require("cc"),
        "STRIP": str(strip),
        "SOURCE_DATE_EPOCH": "0",
        "LC_ALL": "C",
        "LANG": "C",
        "LDFLAGS": "-Wl,-z,max-page-size=16384",
        "CPUS": str(max(2, os.cpu_count() or 2)),
    })
    run(["bash", "scripts/genconfig.sh", "-n"], cwd=source, env=env)
    config = (source / ".config").read_text()
    missing_symbols = [symbol for symbol in symbols if f"CONFIG_{symbol}=y" not in config]
    if missing_symbols:
        raise SystemExit("Toybox config resolver disabled requested applets: " + ",".join(missing_symbols))

    run(["make", "toybox"], cwd=source, env=env)
    binary = source / "toybox"
    if not binary.is_file() or binary.stat().st_size < 100_000:
        raise SystemExit("Toybox build did not produce a plausible binary")

    data = binary.read_bytes()
    if any(marker in data for marker in FORBIDDEN):
        raise SystemExit("Toybox binary contains forbidden Termux identity")

    info = run([readelf, "-h", "-l", "-d", binary], capture=True).stdout
    if "AArch64" not in info:
        raise SystemExit("Toybox output is not AArch64")
    interpreters = re.findall(r"Requesting program interpreter: ([^\]]+)", info)
    if interpreters and interpreters != ["/system/bin/linker64"]:
        raise SystemExit(f"unexpected Android interpreter: {interpreters}")
    needed = re.findall(r"\(NEEDED\).*?\[([^\]]+)\]", info)
    if any(x in ("libc.so.6", "libpthread.so.0") or x.startswith("ld-linux") for x in needed):
        raise SystemExit(f"host libc dependency detected: {needed}")

    newtoys = (source / "generated/newtoys.h").read_text()
    built_applets = sorted(set(re.findall(r"(?:NEWTOY|OLDTOY)\(([^,\s]+)", newtoys)))
    missing = [applet for applet in manifest["applets"] if applet not in built_applets]
    if missing:
        raise SystemExit("compiled Toybox is missing requested applets: " + ",".join(missing))
    return binary, needed

def package_base(manifest: dict, binary: Path, source: Path, pool: Path, provenance: dict) -> Path:
    with tempfile.TemporaryDirectory(prefix="toybox-base-") as temp:
        stage = Path(temp)
        prefix = stage / manifest["prefix"].lstrip("/")
        (prefix / "bin").mkdir(parents=True)
        target = prefix / "bin/ocean-toybox"
        shutil.copy2(binary, target)
        target.chmod(0o755)

        doc = prefix / "share/doc/ocean-toybox"
        doc.mkdir(parents=True)
        shutil.copy2(source / "LICENSE", doc / "LICENSE")
        (doc / "ocean-build.json").write_text(json.dumps(provenance, indent=2) + "\n")

        write_control(stage, [
            ("Package", manifest["packageBase"]),
            ("Version", manifest["version"]),
            ("Architecture", "aarch64"),
            ("Maintainer", "OceanStudio <maintainer@ocean.studio>"),
            ("Homepage", "https://landley.net/toybox/"),
            ("Section", "utils"),
            ("Priority", "optional"),
            ("Description", "Ocean namespaced Toybox multicall binary built from pinned official upstream source"),
        ])
        output = pool / f"{manifest['packageBase']}_{manifest['version']}_aarch64.deb"
        build_deb(stage, output)
        return output

def package_applet(manifest: dict, applet: str, source: Path, pool: Path) -> Path:
    package = f"ocean-toybox-{applet}"
    command = manifest["commandPrefix"] + applet
    with tempfile.TemporaryDirectory(prefix=f"{package}-") as temp:
        stage = Path(temp)
        prefix = stage / manifest["prefix"].lstrip("/")
        bindir = prefix / "bin"
        bindir.mkdir(parents=True)
        wrapper = bindir / command
        wrapper.write_text(
            "#!/system/bin/sh\n"
            f"exec {manifest['prefix']}/bin/ocean-toybox {applet} \"$@\"\n"
        )
        wrapper.chmod(0o755)
        doc = prefix / "share/doc" / package
        doc.mkdir(parents=True)
        shutil.copy2(source / "LICENSE", doc / "LICENSE")
        (doc / "README.Ocean").write_text(
            f"Package: {package}\nCommand: {command}\nUpstream applet: {applet}\n"
            "This namespaced wrapper intentionally does not replace an existing Ocean command.\n"
        )
        write_control(stage, [
            ("Package", package),
            ("Version", manifest["version"]),
            ("Architecture", "all"),
            ("Depends", f"{manifest['packageBase']} (= {manifest['version']})"),
            ("Maintainer", "OceanStudio <maintainer@ocean.studio>"),
            ("Homepage", "https://landley.net/toybox/"),
            ("Section", "utils"),
            ("Priority", "optional"),
            ("Description", f"Namespaced Toybox {applet} applet for OceanStudio (command: {command})"),
        ])
        output = pool / f"{package}_{manifest['version']}_all.deb"
        build_deb(stage, output)
        return output

def validate_debs(pool: Path, manifest: dict, readelf: Path) -> list[dict]:
    records = []
    for deb in sorted(pool.glob("*.deb")):
        package = run(["dpkg-deb", "-f", deb, "Package"], capture=True).stdout.strip()
        arch = run(["dpkg-deb", "-f", deb, "Architecture"], capture=True).stdout.strip()
        with tempfile.TemporaryDirectory(prefix="verify-deb-") as temp:
            root = Path(temp)
            run(["dpkg-deb", "-x", deb, root])
            for path in root.rglob("*"):
                if path.is_symlink() or not path.is_file():
                    continue
                data = path.read_bytes()
                if any(marker in data for marker in FORBIDDEN):
                    raise SystemExit(f"forbidden Termux identity in {deb.name}:{path.relative_to(root)}")
                if data.startswith(b"\x7fELF"):
                    info = run([readelf, "-h", path], capture=True).stdout
                    if "AArch64" not in info:
                        raise SystemExit(f"non-AArch64 ELF in {deb.name}:{path.relative_to(root)}")
        records.append({
            "package": package,
            "architecture": arch,
            "artifact": deb.name,
            "bytes": deb.stat().st_size,
            "sha256": sha256(deb),
        })
    expected = 1 + len(manifest["applets"])
    if len(records) != expected:
        raise SystemExit(f"expected {expected} packages, produced {len(records)}")
    return records

def write_index(staging: Path) -> None:
    index_dir = staging / "dists/stable/main/binary-aarch64"
    index_dir.mkdir(parents=True, exist_ok=True)
    result = run(["dpkg-scanpackages", "--multiversion", "pool/main", "/dev/null"],
                 cwd=staging, capture=True)
    packages = result.stdout.encode()
    (index_dir / "Packages").write_bytes(packages)
    (index_dir / "Packages.gz").write_bytes(gzip.compress(packages, compresslevel=9, mtime=0))

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--ndk", type=Path, default=os.environ.get("ANDROID_NDK_HOME"))
    parser.add_argument("--output", type=Path, default=ROOT / "staging/toybox-0.8.14")
    args = parser.parse_args()
    if args.ndk is None:
        parser.error("--ndk or ANDROID_NDK_HOME is required")
    args.ndk = Path(args.ndk).resolve()
    manifest = json.loads(args.manifest.read_text())
    if manifest["schemaVersion"] != 1:
        raise SystemExit("unsupported Toybox manifest schema")
    if manifest["prefix"] != "/data/data/studio.ocean.app/files/usr":
        raise SystemExit("Ocean prefix mismatch")
    if manifest["target"] != "aarch64-linux-android28":
        raise SystemExit("Android target mismatch")
    source_properties = (args.ndk / "source.properties").read_text()
    if f"Pkg.Revision = {manifest['ndkRevision']}" not in source_properties:
        raise SystemExit("unexpected NDK revision")

    for command in ("git", "make", "cc", "dpkg-deb", "dpkg-scanpackages"):
        require(command)

    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    pool = output / "pool/main"
    pool.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="ocean-toybox-build-") as temp:
        work = Path(temp)
        source = work / "source"
        source_checkout(manifest, source)
        binary, needed = compile_toybox(manifest, source, args.ndk, work)
        provenance = {
            "schemaVersion": 1,
            "builder": "OceanStudio Toybox expansion",
            "upstream": manifest["upstream"],
            "sourceUrl": manifest["sourceUrl"],
            "commit": manifest["commit"],
            "tree": manifest["tree"],
            "licenseBlob": manifest["licenseBlob"],
            "androidMiniconfigBlob": manifest["androidMiniconfigBlob"],
            "target": manifest["target"],
            "ndkRevision": manifest["ndkRevision"],
            "prefix": manifest["prefix"],
            "patchesApplied": [],
            "configuration": "generated allowlist from manifest applets",
            "applets": manifest["applets"],
            "elfNeeded": needed,
            "binarySha256": sha256(binary),
            "sourcePolicy": "official pinned upstream Git source; no Termux package or binary input",
        }
        base = package_base(manifest, binary, source, pool, provenance)
        for applet in manifest["applets"]:
            package_applet(manifest, applet, source, pool)

        readelf = args.ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf"
        records = validate_debs(pool, manifest, readelf)
        write_index(output)
        report = {
            **provenance,
            "packageCount": len(records),
            "baseArtifact": base.name,
            "packages": records,
            "indexSha256": sha256(output / "dists/stable/main/binary-aarch64/Packages"),
            "indexGzipSha256": sha256(output / "dists/stable/main/binary-aarch64/Packages.gz"),
            "promotion": "staging-only until existing Ocean repository signing identity is available",
        }
        (output / "provenance.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"packageCount": len(records), "output": str(output), "base": base.name}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
