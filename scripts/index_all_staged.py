#!/usr/bin/env python3
"""Promote staged packages and sign a complete APT snapshot with the existing key."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
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
    # Read the control stream without extracting Android-owned files on the
    # build host. --field can fail trying to chown an otherwise valid archive.
    data = subprocess.check_output(["dpkg-deb", "--ctrl-tarfile", str(path)])
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        controls = [m for m in archive if m.name.removeprefix("./") == "control"]
        if len(controls) != 1 or not controls[0].isfile():
            raise ValueError(f"Expected one regular control file: {path}")
        control = archive.extractfile(controls[0]).read().decode("utf-8")
    identity(fields(control))
    return control, hashes(path)


def make_stanza(control_text, digest, deb_name, filename=None):
    control = fields(control_text)
    identity(control)
    lines = [f"{k}: {v}" for k, v in control.items() if k not in GENERATED]
    lines.extend([
        f"Filename: {filename or 'pool/main/' + deb_name}", f"Size: {digest['size']}",
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
            if algorithm == "sha256" and metadata.get("Acquire-By-Hash") == "yes":
                immutable = dists / Path(name).parent / "by-hash/SHA256" / entries[name][0]
                if not immutable.is_file() or immutable.read_bytes() != content:
                    raise ValueError(f"Missing or damaged immutable index: {name}")
    if gzip.decompress((dists / (str(INDEX) + ".gz")).read_bytes()) != (dists / INDEX).read_bytes():
        raise ValueError("Packages.gz differs from Packages")


def release_bytes(packages, compressed):
    now = datetime.now(timezone.utc)
    lines = [
        "Origin: OceanStudio", "Label: Ocean Packages", "Suite: stable", "Codename: stable",
        "Architectures: aarch64 all", "Components: main", "Description: Official Ocean APT Repository",
        "Acquire-By-Hash: yes",
        f"Date: {now:%a, %d %b %Y %H:%M:%S +0000}",
        f"Valid-Until: {now + timedelta(days=90):%a, %d %b %Y %H:%M:%S +0000}",
    ]
    for label, algorithm in (("MD5Sum", "md5"), ("SHA1", "sha1"), ("SHA256", "sha256")):
        lines.append(label + ":")
        for suffix, content in (("", packages), (".gz", compressed)):
            lines.append(f" {hashlib.new(algorithm, content).hexdigest()} {len(content)} {INDEX}{suffix}")
    return ("\n".join(lines) + "\n").encode()


def retain_by_hash(dists, content):
    destination = dists / INDEX.parent / "by-hash/SHA256" / hashlib.sha256(content).hexdigest()
    if destination.exists():
        if destination.read_bytes() != content:
            raise ValueError(f"Immutable index hash collision/corruption: {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)


def select_packages(root):
    """Read real controls and bytes across the entire pool and staging tree.

    Keep one candidate per package/architecture, using dpkg version ordering.
    Historical pool files are retained. A previously indexed same-version build
    remains canonical; conflicting unindexed bytes are reported, never relabelled.
    """
    root = Path(root).resolve()
    apt, dists = root / "apt", root / "apt/dists/stable"
    selected, original, conflicts = {}, {}, []
    staged = []
    for deb in sorted((root / "staging").rglob("*.deb")):
        control_text, digest = parse_deb(deb)
        staged.append((deb, control_text, digest))
    replacements = {digest["sha256"]: (deb, text, digest) for deb, text, digest in staged}
    for stanza in stanzas((dists / INDEX).read_text()):
        control = fields(stanza)
        key = identity(control)
        if key in selected:
            raise ValueError(f"Duplicate indexed package/architecture: {key}")
        filename = control.get("Filename", "")
        deb = apt / filename
        if not filename.startswith("pool/") or not deb.resolve().is_relative_to((apt / "pool").resolve()):
            raise ValueError(f"Invalid package Filename: {filename}")
        # An exact staging copy can repair a missing/damaged pool file. Nothing
        # is changed yet, and no stale index checksum is used as a size shortcut.
        source, text, digest = replacements.get(control.get("SHA256"), (None, None, None))
        if source is None:
            source = deb
            text, digest = parse_deb(source)
        actual = fields(text)
        if identity(actual) != key or actual["Version"] != control["Version"]:
            raise ValueError(f"Indexed control identity mismatch: {filename}")
        if digest["sha256"] != control.get("SHA256"):
            raise ValueError(f"Indexed checksum mismatch without an exact staged replacement: {filename}")
        corrected = make_stanza(text, digest, deb.name, filename)
        selected[key] = (corrected, fields(corrected), source)
        original[key] = control

    def consider(deb, control_text, digest, from_pool):
        control = fields(control_text)
        key = identity(control)
        previous = selected.get(key)
        if previous:
            comparison = compare_versions(control["Version"], previous[1]["Version"])
            if comparison < 0:
                return
            if comparison == 0:
                if digest["sha256"] != previous[1].get("SHA256"):
                    canonical = original.get(key, {})
                    if from_pool and canonical.get("Version") == control["Version"]:
                        conflicts.append({"path": deb.relative_to(root).as_posix(),
                                          "package": control["Package"], "version": control["Version"],
                                          "sha256": digest["sha256"], "kept": canonical["Filename"]})
                        return
                    raise ValueError(f"Conflicting bytes for {key} {control['Version']}; bump the version")
                return
        filename = deb.relative_to(apt).as_posix() if from_pool else "pool/main/" + deb.name
        destination = apt / filename
        if not from_pool and destination.exists() and hashes(destination)["sha256"] != digest["sha256"]:
            raise ValueError(f"Staged filename would overwrite different pool bytes: {filename}; use a versioned filename")
        stanza = make_stanza(control_text, digest, deb.name, filename)
        selected[key] = (stanza, fields(stanza), deb)

    current_paths = {r["Filename"] for r in original.values()}
    pool = sorted((apt / "pool").rglob("*.deb"))
    for deb in pool:
        if deb.is_symlink():
            if not deb.resolve().is_relative_to((apt / "pool").resolve()) or not deb.is_file():
                raise ValueError(f"Broken or unsafe pool symlink: {deb}")
            continue
        if deb.relative_to(apt).as_posix() in current_paths:
            continue  # Already checked above, including exact staging recovery.
        text, digest = parse_deb(deb)
        consider(deb, text, digest, True)
    for deb, text, digest in staged:
        consider(deb, text, digest, False)
    destinations = {}
    for _, control, _ in selected.values():
        filename = control.get("Filename", "")
        path = (apt / filename).resolve()
        if not filename.startswith("pool/") or not path.is_relative_to((apt / "pool").resolve()):
            raise ValueError(f"Invalid package Filename: {filename}")
        if filename in destinations and destinations[filename] != control.get("SHA256"):
            raise ValueError(f"Package filename collision: {filename}")
        destinations[filename] = control.get("SHA256")

    updates = [dict(package=c["Package"], version=c["Version"], architecture=c["Architecture"],
                    filename=c["Filename"]) for k, (_, c, _) in selected.items()
               if any(original.get(k, {}).get(f) != c[f] for f in ("Version", "SHA256", "Filename"))]
    return selected, {"indexedBefore": len(original), "indexedAfter": len(selected),
                      "poolFiles": len(pool), "stagedFiles": len(staged),
                      "updates": updates, "retainedPoolConflicts": conflicts,
                      "runtimeTested": False}


def run_indexing(copy_debs=True, root=ROOT):
    if not copy_debs:
        raise ValueError("Cannot publish references without copying the corresponding packages")
    root = Path(root).resolve()
    apt, dists = root / "apt", root / "apt/dists/stable"
    keyring = apt / "ocean.gpg"
    # Fail before touching ANY live file if the original private key is absent.
    fingerprint = require_signing_key(keyring)
    selected, report = select_packages(root)

    output = ("\n\n".join(selected[k][0] for k in sorted(selected)) + "\n").encode()
    compressed = gzip.compress(output, mtime=0)
    # Complete and verify both signatures off to the side before replacing live files.
    with tempfile.TemporaryDirectory(prefix="ocean-signed-index-", dir=root) as directory:
        temporary = Path(directory)
        (temporary / INDEX).parent.mkdir(parents=True)
        (temporary / INDEX).write_bytes(output)
        (temporary / (str(INDEX) + ".gz")).write_bytes(compressed)
        for content in (output, compressed):
            retain_by_hash(temporary, content)
        (temporary / "Release").write_bytes(release_bytes(output, compressed))
        for filename, operation in (("InRelease", "--clearsign"), ("Release.gpg", "--detach-sign")):
            subprocess.run([
                "gpg", "--batch", "--yes", "--local-user", fingerprint, "--digest-algo", "SHA256",
                "--output", str(temporary / filename), operation, str(temporary / "Release"),
            ], check=True)
        verify_release(temporary, keyring)
        # Preserve previous snapshots so an APT client holding a cached signed
        # Release can still fetch exactly the index that Release authenticates.
        for filename in (str(INDEX), str(INDEX) + ".gz"):
            if (dists / filename).is_file():
                retain_by_hash(dists, (dists / filename).read_bytes())
        for content in (output, compressed):
            retain_by_hash(dists, content)
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
    print(f"Verified signed index: {len(selected)} package/architecture entries; {len(report['updates'])} updates")
    for conflict in report["retainedPoolConflicts"]:
        print(f"Retained conflicting historical bytes without indexing: {conflict['path']}; canonical={conflict['kept']}")
    # Publish pool + all five metadata files in ONE Git commit. Indexing is not
    # runtime validation: never rewrite functional-repair-status.json here.


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--plan", type=Path, help="Write a read-only complete-pool selection report without signing")
    args = parser.parse_args()
    try:
        if args.plan:
            _, report = select_packages(args.root)
            args.plan.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps({k: v for k, v in report.items() if k not in ("updates", "retainedPoolConflicts")}))
        else:
            run_indexing(root=args.root)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Index publication failed: {exc}\n")
