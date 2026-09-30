#!/usr/bin/env python3
"""Verify packaged catalogue hashes AND their binding to the trusted signature."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

this = Path(__file__).resolve()
if (this.parents[1] / "scripts/hydrate-signed-bootstrap.py").is_file():
    ROOT = this.parents[1]
    hydrate_script = ROOT / "scripts/hydrate-signed-bootstrap.py"
elif (this.parents[2] / "ocean-packages/scripts/hydrate-signed-bootstrap.py").is_file():
    ROOT = this.parents[2]
    hydrate_script = ROOT / "ocean-packages/scripts/hydrate-signed-bootstrap.py"
else:
    ROOT = this.parents[1]
    hydrate_script = ROOT / "scripts/hydrate-signed-bootstrap.py"

spec = importlib.util.spec_from_file_location("hydrate", hydrate_script)
hydrate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hydrate)


def verify(read, minimum=0):
    metadata = dict(line.split("=", 1) for line in read("catalog.properties").decode().splitlines()
                    if line and not line.startswith("#"))
    assets = {name: read(name) for name in ("Packages.gz.bin", "InRelease", "ocean.gpg")}
    for name, data in assets.items():
        if hashlib.sha256(data).hexdigest() != metadata[name + "_sha256"]:
            raise RuntimeError("Asset hash mismatch: " + name)
    with tempfile.TemporaryDirectory(prefix="ocean-apk-signature-") as temporary:
        directory = Path(temporary)
        for name in ("InRelease", "ocean.gpg"):
            (directory / name).write_bytes(assets[name])
        result = subprocess.run(["gpg", "--batch", "--show-keys", "--with-colons", str(directory / "ocean.gpg")],
                                check=True, capture_output=True, text=True)
        fpr_file = ROOT / "keys/ocean-development-repository.fingerprint"
        if not fpr_file.is_file():
            fpr_file = ROOT / "ocean-packages/keys/ocean-development-repository.fingerprint"
        expected = fpr_file.read_text().strip()
        primary = next(line.split(":")[9] for line in result.stdout.splitlines() if line.startswith("fpr:"))
        if primary != expected:
            raise RuntimeError("Bundled archive signing identity changed")
        result = subprocess.run(["gpgv", "--keyring", str(directory / "ocean.gpg"), "--output", "-",
                                 str(directory / "InRelease")], check=True, capture_output=True)
    signed = result.stdout.decode()
    fields = hydrate.paragraphs(signed)[0]
    if parsedate_to_datetime(fields["Valid-Until"]) <= datetime.now(timezone.utc):
        raise RuntimeError("Bundled signed metadata has expired")
    packages = hydrate.verify_catalog_index(signed, assets["Packages.gz.bin"])
    if hashlib.sha256(packages).hexdigest() != metadata["packages_sha256"]:
        raise RuntimeError("Uncompressed catalogue hash mismatch")
    entries = hydrate.paragraphs(packages.decode())
    identities = [(e["Package"], e["Architecture"]) for e in entries]
    if len(identities) != len(set(identities)):
        raise RuntimeError("Duplicate package/architecture candidates")
    names = {e["Package"] for e in entries}
    if len(entries) != int(metadata["package_count"]) or len(names) < minimum:
        raise RuntimeError(f"Catalogue has {len(names)} unique packages; expected at least {minimum}")
    required = {"pip", "npm", "python", "nodejs", "proot", "proot-distro", "ocean-distro"}
    if minimum >= 6482:
        required |= {"ocean-glibc", "ocean-glibc-suite", "ocean-glibc-utils", "openjdk-21"}
    if not required <= names:
        raise RuntimeError("Required package names missing: " + repr(sorted(required - names)))
    for entry in entries:
        if entry["Architecture"] not in ("aarch64", "all"):
            raise RuntimeError("Unsupported package architecture: " + entry["Package"])
    print(f"Verified signed catalogue: {len(names)} names / {len(entries)} records; both index hashes match InRelease")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path, nargs="?")
    parser.add_argument("--assets", type=Path)
    parser.add_argument("--min-packages", type=int, default=0)
    args = parser.parse_args()
    if bool(args.apk) == bool(args.assets):
        parser.error("provide one APK or --assets directory")
    if args.apk:
        with zipfile.ZipFile(args.apk) as archive:
            verify(lambda name: archive.read("assets/ocean/repository/" + name), args.min_packages)
    else:
        verify(lambda name: (args.assets / name).read_bytes(), args.min_packages)
