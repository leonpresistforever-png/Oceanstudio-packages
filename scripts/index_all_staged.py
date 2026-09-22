#!/usr/bin/env python3
"""Promote staged packages and sign a complete APT snapshot with the existing key."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = Path("main/binary-aarch64/Packages")
GENERATED = {"Filename", "Size", "MD5sum", "SHA1", "SHA256", "SHA512"}


def fields(text):
    result, key = {}, None
    for line in text.splitlines():
        if line.startswith((" ", "\t")) and key:
            result[key] += "\n" + line
        elif ":" in line:
            key, value = line.split(":", 1)
            if key in result:
                raise ValueError(f"Duplicate control field: {key}")
            result[key] = value.strip()
        elif line.strip():
            raise ValueError(f"Malformed control line: {line!r}")
    return result


def stanzas(text):
    return [s for s in re.split(r"\n[ \t]*\n", text.strip()) if s.strip()]


def identity(control):
    for key in ("Package", "Version", "Architecture"):
        if not control.get(key):
            raise ValueError(f"Missing {key} in package control")
    # Preserve legacy archive names such as glslangValidator without renaming.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9+.-]*", control["Package"]):
        raise ValueError("Invalid package name")
    if control["Architecture"] not in ("aarch64", "all"):
        raise ValueError(f"Unsupported architecture: {control['Architecture']}")
    return control["Package"], control["Architecture"]


def hashes(path):
    digests = {name: hashlib.new(name) for name in ("md5", "sha1", "sha256")}
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            for digest in digests.values():
                digest.update(chunk)
    return {"size": size, **{k: v.hexdigest() for k, v in digests.items()}}


def parse_deb(path):
    # dpkg validates ar and supports every installed control compression codec.
    control = subprocess.check_output(["dpkg-deb", "--field", str(path)], text=True)
    identity(fields(control))
    return control, hashes(path)


def make_stanza(control_text, digest, deb_name):
    control = fields(control_text)
    identity(control)
    lines = [f"{k}: {v}" for k, v in control.items() if k not in GENERATED]
    lines.extend([
        f"Filename: pool/main/{deb_name}", f"Size: {digest['size']}",
        f"MD5sum: {digest['md5']}", f"SHA1: {digest['sha1']}",
        f"SHA256: {digest['sha256']}",
    ])
    return "\n".join(lines)


def compare_versions(left, right):
    for operator, result in (("lt", -1), ("gt", 1)):
        code = subprocess.run(["dpkg", "--compare-versions", left, operator, right]).returncode
        if code == 0:
            return result
        if code != 1:
            raise ValueError(f"Invalid Debian version: {left!r} or {right!r}")
    return 0


def require_signing_key(keyring):
    output = subprocess.check_output(
        ["gpg", "--batch", "--with-colons", "--show-keys", str(keyring)],
        text=True, stderr=subprocess.DEVNULL,
    )
    primary, fingerprints = False, []
    for line in output.splitlines():
        parts = line.split(":")
        if parts[0] == "pub":
            primary = True
        elif parts[0] == "fpr" and primary:
            fingerprints.append(parts[9])
            primary = False
    if len(fingerprints) != 1:
        raise ValueError("Expected exactly one trusted Ocean archive public key")
    fingerprint = fingerprints[0]
    result = subprocess.run(
        ["gpg", "--batch", "--with-colons", "--list-secret-keys", fingerprint],
        text=True, capture_output=True,
    )
    if result.returncode or not any(x.startswith("sec:") for x in result.stdout.splitlines()):
        raise ValueError(
            "Trusted Ocean private signing key unavailable. Import the existing "
            f"OCEAN_REPOSITORY_SIGNING_KEY ({fingerprint}); live files were not changed."
        )
    return fingerprint


def verify_release(dists, keyring):
    signed = subprocess.check_output([
        "gpgv", "--keyring", str(keyring.resolve()), "--output", "-", str(dists / "InRelease")
    ], stderr=subprocess.PIPE)
    release = (dists / "Release").read_bytes()
    if signed != release:
        raise ValueError("InRelease signs different metadata than Release")
    subprocess.run([
        "gpgv", "--keyring", str(keyring.resolve()),
        str(dists / "Release.gpg"), str(dists / "Release"),
    ], check=True, capture_output=True)
    metadata = fields(release.decode())
    if parsedate_to_datetime(metadata["Valid-Until"]) <= datetime.now(timezone.utc):
        raise ValueError("Signed Release has expired")
    for section, algorithm in (("MD5Sum", "md5"), ("SHA1", "sha1"), ("SHA256", "sha256")):
        entries = {}
        for line in metadata.get(section, "").splitlines():
            if not line.strip():
                continue
            digest, size, name = line.split()
            if name in entries or not (dists / name).resolve().is_relative_to(dists.resolve()):
                raise ValueError(f"Unsafe or duplicate Release path: {name}")
            entries[name] = (digest, int(size))
        for name in (str(INDEX), str(INDEX) + ".gz"):
            content = (dists / name).read_bytes()
            if entries.get(name) != (hashlib.new(algorithm, content).hexdigest(), len(content)):
                raise ValueError(f"Release {section} mismatch: {name}")
    if gzip.decompress((dists / (str(INDEX) + ".gz")).read_bytes()) != (dists / INDEX).read_bytes():
        raise ValueError("Packages.gz differs from Packages")


def release_bytes(packages, compressed):
    now = datetime.now(timezone.utc)
    lines = [
        "Origin: OceanStudio", "Label: Ocean Packages", "Suite: stable", "Codename: stable",
        "Architectures: aarch64 all", "Components: main", "Description: Official Ocean APT Repository",
        f"Date: {now:%a, %d %b %Y %H:%M:%S +0000}",
        f"Valid-Until: {now + timedelta(days=90):%a, %d %b %Y %H:%M:%S +0000}",
    ]
    for label, algorithm in (("MD5Sum", "md5"), ("SHA1", "sha1"), ("SHA256", "sha256")):
        lines.append(label + ":")
        for suffix, content in (("", packages), (".gz", compressed)):
            lines.append(f" {hashlib.new(algorithm, content).hexdigest()} {len(content)} {INDEX}{suffix}")
    return ("\n".join(lines) + "\n").encode()


def run_indexing(copy_debs=True, root=ROOT):
    if not copy_debs:
        raise ValueError("Cannot publish references without copying the corresponding packages")
    root = Path(root).resolve()
    apt, dists = root / "apt", root / "apt/dists/stable"
    keyring = apt / "ocean.gpg"
    # Fail before touching ANY live file if the original private key is absent.
    fingerprint = require_signing_key(keyring)
    selected = {}
    for stanza in stanzas((dists / INDEX).read_text()):
        control = fields(stanza)
        key = identity(control)
        if key in selected:
            raise ValueError(f"Duplicate indexed package/architecture: {key}")
        selected[key] = (stanza, control, None)

    updates = 0
    for deb in sorted((root / "staging").rglob("*.deb")):
        control_text, digest = parse_deb(deb)
        control = fields(control_text)
        key = identity(control)
        previous = selected.get(key)
        if previous:
            comparison = compare_versions(control["Version"], previous[1]["Version"])
            if comparison < 0:
                continue  # Older staged builds cannot downgrade live packages.
            if comparison == 0:
                if digest["sha256"] != previous[1].get("SHA256"):
                    raise ValueError(f"Conflicting bytes for {key} {control['Version']}; bump the version")
                selected[key] = (previous[0], previous[1], deb)
                continue
        stanza = make_stanza(control_text, digest, deb.name)
        selected[key] = (stanza, fields(stanza), deb)
        updates += 1

    destinations = {}
    for _, control, _ in selected.values():
        filename = control.get("Filename", "")
        path = (apt / filename).resolve()
        if not filename.startswith("pool/") or not path.is_relative_to((apt / "pool").resolve()):
            raise ValueError(f"Invalid package Filename: {filename}")
        if filename in destinations and destinations[filename] != control.get("SHA256"):
            raise ValueError(f"Package filename collision: {filename}")
        destinations[filename] = control.get("SHA256")

    output = ("\n\n".join(selected[k][0] for k in sorted(selected)) + "\n").encode()
    compressed = gzip.compress(output, mtime=0)
    # Complete and verify both signatures off to the side before replacing live files.
    with tempfile.TemporaryDirectory(prefix="ocean-signed-index-", dir=root) as directory:
        temporary = Path(directory)
        (temporary / INDEX).parent.mkdir(parents=True)
        (temporary / INDEX).write_bytes(output)
        (temporary / (str(INDEX) + ".gz")).write_bytes(compressed)
        (temporary / "Release").write_bytes(release_bytes(output, compressed))
        for filename, operation in (("InRelease", "--clearsign"), ("Release.gpg", "--detach-sign")):
            subprocess.run([
                "gpg", "--batch", "--yes", "--local-user", fingerprint, "--digest-algo", "SHA256",
                "--output", str(temporary / filename), operation, str(temporary / "Release"),
            ], check=True)
        verify_release(temporary, keyring)
        for _, control, source in selected.values():
            if source is None:
                continue
            destination = apt / control["Filename"]
            if destination.exists() and hashes(destination)["sha256"] == control["SHA256"]:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        for filename in (str(INDEX), str(INDEX) + ".gz", "Release", "Release.gpg", "InRelease"):
            os.replace(temporary / filename, dists / filename)
    verify_release(dists, keyring)
    print(f"Verified signed index: {len(selected)} package/architecture entries; {updates} staged updates")
    # Publish pool + all five metadata files in ONE Git commit. Indexing is not
    # runtime validation: never rewrite functional-repair-status.json here.


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        run_indexing(root=args.root)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Index publication failed: {exc}\n")
