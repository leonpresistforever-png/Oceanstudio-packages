#!/usr/bin/env python3
"""Audit actual APT metadata and every staged .deb, without changing the repository.

Normally reads package controls and hashes from a full checkout. --tree accepts
an untruncated GitHub recursive tree snapshot for a metadata-only audit: it proves
that each staged blob is the exact Git object referenced by the index, but does
not claim to have rehashed every binary or run Android programs.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
import subprocess
from pathlib import Path, PurePosixPath

from index_all_staged import INDEX, ROOT, compare_versions, fields, hashes, identity, parse_deb, stanzas, verify_release


def audit(root, tree=None):
    root = Path(root).resolve()
    apt, dists = root / "apt", root / "apt/dists/stable"
    records = [fields(s) for s in stanzas((dists / INDEX).read_text())]
    errors, indexed, groups, rows = [], {}, collections.defaultdict(collections.Counter), []
    for record in records:
        key = identity(record)
        if key in indexed:
            errors.append(f"Duplicate indexed package/architecture: {key}")
        indexed[key] = record
    try:
        verify_release(dists, apt / "ocean.gpg")
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        errors.append(f"Signed metadata: {exc}")
    if gzip.decompress((dists / (str(INDEX) + ".gz")).read_bytes()) != (dists / INDEX).read_bytes():
        errors.append("Packages.gz differs from Packages")

    referenced, by_blob = set(), collections.defaultdict(list)
    if tree is not None:
        if tree.get("truncated") or not isinstance(tree.get("tree"), list):
            raise ValueError("A complete recursive Git tree is required")
        nodes = {node["path"]: node for node in tree["tree"] if node["type"] == "blob"}
        # The supplied index must belong to this exact tree, not a newer/older ref.
        for name in ("Packages", "Packages.gz"):
            path = "apt/dists/stable/main/binary-aarch64/" + name
            data = (root / path).read_bytes()
            sha = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if nodes.get(path, {}).get("sha") != sha:
                errors.append(f"Local metadata does not match supplied tree: {path}")
        for record in records:
            path = "apt/" + record.get("Filename", "")
            node = nodes.get(path)
            referenced.add(path)
            if not node or node.get("mode") == "120000":
                errors.append(f"Indexed target missing or unresolved symlink: {path}")
                continue
            if node["size"] != int(record["Size"]):
                errors.append(f"Indexed size mismatch: {path}")
            by_blob[node["sha"]].append(record)
        staged = sorted(n for n in nodes if n.startswith("staging/") and n.endswith(".deb"))
        for path in staged:
            node = nodes[path]
            matches = by_blob.get(node["sha"], [])
            status = "exact_blob_indexed" if matches else "missing"
            row = {"staged": path, "blob": node["sha"], "status": status}
            if matches:
                match = matches[0]
                row.update({k: match[k] for k in ("Package", "Version", "Architecture", "Filename", "SHA256")})
            else:
                errors.append(f"Staged Git blob not referenced by index: {path}")
            groups[path.split("/")[1]][status] += 1
            rows.append(row)
        pool = {p for p in nodes if p.startswith("apt/pool/") and p.endswith(".deb")}
        links = [{"path": p, "blob": nodes[p]["sha"]} for p in sorted(pool) if nodes[p]["mode"] == "120000"]
    else:
        for record in records:
            relative = record.get("Filename", "")
            path = (apt / relative).resolve()
            if not relative.startswith("pool/") or not path.is_relative_to((apt / "pool").resolve()):
                errors.append(f"Unsafe indexed Filename: {relative}")
                continue
            referenced.add("apt/" + relative)
            try:
                control, digest = parse_deb(path)
                actual = fields(control)
                if any(actual.get(k) != record.get(k) for k in ("Package", "Version", "Architecture")):
                    errors.append(f"Indexed control identity mismatch: {relative}")
                for name, key in (("Size", "size"), ("SHA256", "sha256"), ("SHA1", "sha1"), ("MD5sum", "md5")):
                    if record.get(name) != str(digest[key]):
                        errors.append(f"Indexed {name} mismatch: {relative}")
            except (ValueError, OSError, subprocess.CalledProcessError) as exc:
                errors.append(f"Unreadable indexed package {relative}: {exc}")
        staged = sorted((root / "staging").rglob("*.deb"))
        for path in staged:
            relative = path.relative_to(root).as_posix()
            row = {"staged": relative}
            try:
                control_text, digest = parse_deb(path)
                control = fields(control_text)
                match = indexed.get(identity(control))
                if match and control["Version"] == match["Version"] and digest["sha256"] == match["SHA256"]:
                    status = "exact_bytes_indexed"
                elif match and compare_versions(control["Version"], match["Version"]) < 0:
                    status = "superseded"
                else:
                    status = "missing"
                    errors.append(f"Staged package missing/conflicting: {relative}")
                row.update({k: control[k] for k in ("Package", "Version", "Architecture")})
                row["SHA256"] = digest["sha256"]
            except (ValueError, OSError, subprocess.CalledProcessError) as exc:
                status = "invalid"
                errors.append(f"Invalid staged package {relative}: {exc}")
            row["status"] = status
            groups[relative.split("/")[1]][status] += 1
            rows.append(row)
        pool = {p.relative_to(root).as_posix() for p in (apt / "pool").rglob("*.deb")}
        links = [{"path": p, "target": str((root / p).readlink())} for p in sorted(pool) if (root / p).is_symlink()]

    return {
        "mode": "git-blob-identity" if tree is not None else "full-checkout-controls-and-hashes",
        "tree": tree.get("sha") if tree else None,
        "indexedEntries": len(records),
        "uniqueNames": len({r["Package"] for r in records}),
        "uniquePackageArchitectures": len(indexed),
        "stagedFiles": len(staged),
        "stagedGroups": dict(groups),
        "unreferencedPoolFiles": sorted(pool - referenced),
        "poolSymlinks": links,
        "packages": rows,
        "errors": errors,
        "runtimeTested": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--tree", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    report = audit(args.root, json.loads(args.tree.read_text()) if args.tree else None)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{report['indexedEntries']} indexed; {report['stagedFiles']} staged; "
          f"{len(report['errors'])} errors; mode={report['mode']}")
    for error in report["errors"]:
        print(error)
    raise SystemExit(bool(report["errors"]))


if __name__ == "__main__":
    main()
