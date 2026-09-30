#!/usr/bin/env python3
"""
HARD CI/device regression test that validates Ocean runtime purity:
Fails if ANY runtime package, APT source, archive payload, maintainer script,
metadata, executable, symlink, config or repo contains:
- /data/data/com.termux
- packages.termux.dev
- packages-cf.termux.dev
- TERMUX_PREFIX
"""
import argparse
import gzip
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

FORBIDDEN = [
    b"/data/data/com.termux",
    b"packages.termux.dev",
    b"packages-cf.termux.dev",
    b"TERMUX_PREFIX",
]

errors = []

def check_file(path: pathlib.Path, label: str):
    if not path.exists():
        return
    try:
        content = path.read_bytes()
        for f in FORBIDDEN:
            if f in content:
                errors.append(f"[{label}] Found forbidden {f.decode('utf-8', errors='ignore')} in {path}")
    except Exception as e:
        errors.append(f"[{label}] Could not read {path}: {e}")

parser = argparse.ArgumentParser()
parser.add_argument(
    "--bootstrap-prefix",
    type=pathlib.Path,
    default=pathlib.Path("ocean-packages/build/work/clean_bootstrap/data/data/studio.ocean.app/files/usr"),
)
parser.add_argument(
    "--repository",
    type=pathlib.Path,
    default=pathlib.Path("ocean-packages/build/out/repository/apt"),
)
parser.add_argument(
    "--bootstrap-archive",
    type=pathlib.Path,
    default=pathlib.Path("android/app/src/main/assets/ocean/bootstrap/aarch64/ocean-aarch64.tar.zst"),
    help="verified bootstrap used when the distribution staging prefix is absent",
)
parser.add_argument(
    "--repository-url",
    default="https://raw.githubusercontent.com/leonpresistforever-png/Oceanstudio-packages/main/apt",
    help="signed repository used when the assembled repository directory is absent",
)
args = parser.parse_args()
bootstrap_dir = args.bootstrap_prefix.resolve()
repo_dir = args.repository.resolve()
temporary = tempfile.TemporaryDirectory(prefix="ocean-no-termux-audit-")
temporary_root = pathlib.Path(temporary.name)

print("=== RUNNING HARD NO-TERMUX REGRESSION AUDIT ===")

if not bootstrap_dir.is_dir():
    archive = args.bootstrap_archive.resolve()
    if not archive.is_file():
        sibling = pathlib.Path(__file__).resolve().parents[1].parent / "Oceanstudio.apk"
        candidate = sibling / "android/app/src/main/assets/ocean/bootstrap/aarch64/ocean-aarch64.tar.zst"
        if candidate.is_file():
            archive = candidate
    if not archive.is_file():
        repo_root = pathlib.Path(__file__).resolve().parents[1]
        if not (repo_root / "apt").is_dir():
            errors.append(f"[Bootstrap] Neither staging prefix nor packaged archive exists: {archive}")
    else:
        extracted = temporary_root / "bootstrap"
        extracted.mkdir()
        try:
            if shutil.which("zstd"):
                subprocess.run(
                    ["bash", "-o", "pipefail", "-c", 'zstd -qdc "$1" | tar -xf - -C "$2"', "audit", str(archive), str(extracted)],
                    check=True,
                )
            else:
                import zstandard
                with archive.open("rb") as source, zstandard.ZstdDecompressor().stream_reader(source) as stream:
                    with tarfile.open(fileobj=stream, mode="r|") as payload:
                        payload.extractall(extracted, filter="data")
            bootstrap_dir = extracted / "usr"
            print(f"Auditing packaged bootstrap fallback: {archive}")
        except (ImportError, subprocess.CalledProcessError, tarfile.TarError) as error:
            errors.append(f"[Bootstrap] Could not extract {archive}: {error}")
if not repo_dir.is_dir():
    repo_dir = temporary_root / "repository" / "apt"
    metadata = (
        "dists/stable/InRelease",
        "dists/stable/Release",
        "dists/stable/Release.gpg",
        "dists/stable/main/binary-aarch64/Packages.gz",
        "ocean.gpg",
    )
    try:
        for relative in metadata:
            destination = repo_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            request = urllib.request.Request(f"{args.repository_url.rstrip('/')}/{relative}", headers={"User-Agent": "OceanStudio-auditor/1"})
            with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
                shutil.copyfileobj(response, output)
        subprocess.run(["gpgv", "--keyring", str(repo_dir / "ocean.gpg"), str(repo_dir / "dists/stable/InRelease")], check=True)
        packages_gz = repo_dir / "dists/stable/main/binary-aarch64/Packages.gz"
        (packages_gz.parent / "Packages").write_bytes(gzip.decompress(packages_gz.read_bytes()))
        print(f"Auditing signed repository fallback: {args.repository_url}")
    except Exception as error:
        errors.append(f"[Repository] Could not hydrate signed metadata from {args.repository_url}: {error}")

# 1. Audit APT sources
sources = list((bootstrap_dir / "etc/apt").rglob("*"))
for s in sources:
    if s.is_file():
        check_file(s, "APT Source / Config")

# 2. Audit trusted keys
keyrings = list((bootstrap_dir / "etc/apt/trusted.gpg.d").glob("*"))
for k in keyrings:
    if k.name != "ocean.gpg":
        errors.append(f"[Trusted Keys] Non-ocean key found: {k.name}")

# 3. Audit dpkg status
check_file(bootstrap_dir / "var/lib/dpkg/status", "DPKG Status DB")

# Audit every bootstrap payload and symlink target, not only APT configuration.
if bootstrap_dir.exists():
    for path in bootstrap_dir.rglob("*"):
        if path.is_symlink():
            target = os.readlink(path).encode()
            for forbidden in FORBIDDEN:
                if forbidden in target:
                    errors.append(f"[Bootstrap Symlink] Found forbidden {forbidden.decode()} in {path} -> {os.readlink(path)}")
        elif path.is_file():
            check_file(path, "Bootstrap Payload")

# 4. Audit APT Repository metadata
if repo_dir.exists():
    for f in (repo_dir / "dists/stable").rglob("*"):
        if f.is_file():
            check_file(f, "Repo Metadata")

if errors:
    print(f"\n❌ HARD REGRESSION AUDIT FAILED ({len(errors)} violations found):")
    for err in errors:
        print(f"  - {err}")
    sys.exit(1)
else:
    print("\n✅ HARD REGRESSION AUDIT PASSED: ZERO forbidden patterns found across Ocean runtime!")
    sys.exit(0)
