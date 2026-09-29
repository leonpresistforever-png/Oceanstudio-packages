#!/usr/bin/env python3
"""Unpack official distribution rootfs artifacts into a flat guest tree.

Handles flat tarballs, Docker save bundles (layer.tar), and OCI image layouts.
Hard links and symlinks are materialized as regular files where the platform
cannot preserve them (Android / proot installs).
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


def die(msg: str, code: int = 2) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def safe_parts(name: str) -> PurePosixPath:
    path = PurePosixPath(name.lstrip("./"))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe archive member: {name}")
    return path


def detect_layout(members: list[str]) -> str:
    names = {m.lstrip("./") for m in members}
    if "oci-layout" in names and any(n.startswith("blobs/sha256/") for n in names):
        return "oci"
    if "manifest.json" in names and any("/layer.tar" in n for n in names):
        return "docker"
    top_dirs = {n.split("/", 1)[0] for n in names if "/" in n}
    if len(top_dirs) == 1 and not any(n.startswith("etc/") for n in names):
        only = next(iter(top_dirs))
        if only not in ("var", "usr", "bin"):
            return f"prefixed:{only}"
    return "flat"


def extract_tar_stream(tf: tarfile.TarFile, dest: Path, *, prefix: str | None = None) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    link_map: dict[str, Path] = {}

    def target_path(member_name: str) -> Path:
        rel = safe_parts(member_name)
        if prefix and rel.parts and rel.parts[0] == prefix:
            rel = PurePosixPath(*rel.parts[1:])
        return dest.joinpath(*rel.parts) if rel.parts else dest

    for member in tf.getmembers():
        rel = safe_parts(member.name)
        if prefix and rel.parts and rel.parts[0] == prefix:
            rel = PurePosixPath(*rel.parts[1:])
        if not rel.parts:
            continue
        if rel.parts[0] == "dev":
            continue
        out = dest.joinpath(*rel.parts)

        if member.isdir():
            out.mkdir(parents=True, exist_ok=True)
            continue
        if member.issym():
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.exists() or out.is_symlink():
                out.unlink()
            try:
                out.symlink_to(member.linkname)
            except OSError:
                pass
            continue
        if member.islnk():
            link_map[member.name] = out
            continue
        if not member.isfile():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        with tf.extractfile(member) as stream:
            if stream is None:
                continue
            with out.open("wb") as handle:
                shutil.copyfileobj(stream, handle)
        mode = member.mode & 0o777
        if mode == 0:
            mode = 0o755 if member.isdir() else 0o644
        try:
            os.chmod(out, mode)
        except OSError:
            os.chmod(out, 0o644)

    for member_name, out in link_map.items():
        member = tf.getmember(member_name)
        src_rel = safe_parts(member.linkname)
        src = dest.joinpath(*src_rel.parts)
        if not src.is_file():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)


def extract_oci_blob(blob: Path, dest: Path) -> None:
    raw = blob.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as inner:
        extract_tar_stream(inner, dest)


def unpack_oci(archive: Path, dest: Path) -> None:
    with tarfile.open(archive) as outer:
        outer.extractall(path=dest / ".oci-bundle", filter="data")
    bundle = dest / ".oci-bundle"
    index = json.loads((bundle / "index.json").read_text(encoding="utf-8"))
    manifest_digest = index["manifests"][0]["digest"].split(":", 1)[1]
    manifest = json.loads((bundle / "blobs" / "sha256" / manifest_digest).read_text(encoding="utf-8"))
    layers = manifest.get("layers") or manifest.get("rootfs", {}).get("diff_ids") or []
    if not layers and "config" in manifest:
        cfg_digest = manifest["config"]["digest"].split(":", 1)[1]
        cfg = json.loads((bundle / "blobs" / "sha256" / cfg_digest).read_text(encoding="utf-8"))
        layers = cfg.get("rootfs", {}).get("diff_ids", [])
    guest = dest
    guest.mkdir(parents=True, exist_ok=True)
    for layer in manifest.get("layers", []):
        digest = layer["digest"].split(":", 1)[1]
        extract_oci_blob(bundle / "blobs" / "sha256" / digest, guest)
    shutil.rmtree(bundle, ignore_errors=True)


def unpack_docker(archive: Path, dest: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="ocean-docker-") as td:
        with tarfile.open(archive) as outer:
            outer.extractall(path=td, filter="data")
        layer = next(Path(td).rglob("layer.tar"))
        guest = dest
        guest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(layer) as inner:
            extract_tar_stream(inner, guest)


def unpack_flat(archive: Path, dest: Path, *, prefix: str | None = None) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tf:
        extract_tar_stream(tf, dest, prefix=prefix)


def guest_is_usable(root: Path) -> bool:
    if (root / "etc").is_dir() and not (root / "etc").is_symlink():
        return True
    return (root / "usr/lib/os-release").is_file()


def unpack_archive(archive: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tf:
        layout = detect_layout([m.name for m in tf.getmembers()])
    if layout == "oci":
        unpack_oci(archive, dest)
    elif layout == "docker":
        unpack_docker(archive, dest)
    elif layout.startswith("prefixed:"):
        unpack_flat(archive, dest, prefix=layout.split(":", 1)[1])
    else:
        unpack_flat(archive, dest)
    if not guest_is_usable(dest):
        die(f"Archive did not unpack to a usable rootfs under {dest}")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--proot", default="", help="Optional proot binary for a second-pass link2symlink extract")
    args = parser.parse_args()
    if args.proot:
        staging = args.destination
        staging.mkdir(parents=True, exist_ok=True)
        cmd = [
            args.proot,
            "--link2symlink",
            "-0",
            "tar",
            "--extract",
            "--file",
            str(args.archive),
            "--directory",
            str(staging),
            "--no-same-owner",
            "--no-same-permissions",
            "--delay-directory-restore",
            "--exclude=dev/*",
            "--exclude=./dev/*",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and (staging / "etc").exists():
            print(str(staging))
            return
    root = unpack_archive(args.archive, args.destination)
    print(str(root))


if __name__ == "__main__":
    main()
