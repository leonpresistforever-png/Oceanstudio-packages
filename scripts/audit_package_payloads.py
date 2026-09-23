#!/usr/bin/env python3
"""Inspect every real pool archive and the dependency graph; never execute payloads.

An archive passing these structural checks is not declared Android compatible.
Runtime results are recorded by separate tests. Historical archives are retained.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import re
import struct
import subprocess
import tarfile
from functools import lru_cache
from pathlib import Path, PurePosixPath
from index_all_staged import ROOT, INDEX, fields, stanzas, identity, hashes, compare_versions

ATOM = re.compile(r"^([A-Za-z0-9][A-Za-z0-9+.-]*)(?::([a-z0-9-]+))?(?:\s*\((<<|<=|=|>=|>>)\s*([^()]+)\))?$")

def dependencies(value):
    groups = []
    for group in value.replace("\n", " ").split(","):
        if not group.strip():
            continue
        choices = []
        for item in group.split("|"):
            match = ATOM.fullmatch(item.strip())
            if not match:
                raise ValueError(f"Malformed binary dependency: {item.strip()}")
            choices.append(match.groups())
        groups.append(choices)
    return groups

@lru_cache(maxsize=None)
def satisfies(version, operator, required):
    if not operator:
        return True
    if version is None:
        return False
    result = compare_versions(version, required)
    return {"<<": result < 0, "<=": result <= 0, "=": result == 0,
            ">=": result >= 0, ">>": result > 0}[operator]

def dependency_errors(records):
    available = collections.defaultdict(list)
    errors = []
    for record in records:
        available[record["Package"]].append((record["Version"], record["Architecture"]))
        try:
            for group in dependencies(record.get("Provides", "")):
                for name, arch, operator, version in group:
                    if operator not in (None, "="):
                        raise ValueError("Provides only permits an exact version")
                    available[name].append((version, record["Architecture"]))
        except ValueError as exc:
            errors.append({"package": record["Package"], "field": "Provides", "error": str(exc)})
    for record in records:
        for field in ("Pre-Depends", "Depends"):
            try:
                for group in dependencies(record.get(field, "")):
                    if not any(satisfies(version, operator, required)
                               for name, arch, operator, required in group
                               for version, candidate_arch in available[name]
                               if arch in (None, "any", "native", candidate_arch)
                               or candidate_arch == "all"):
                        errors.append({"package": record["Package"], "field": field, "unsatisfied": group})
            except ValueError as exc:
                errors.append({"package": record["Package"], "field": field, "error": str(exc)})
    return errors

def inspect_payload(path, architecture):
    issues, executables, elf_count, file_count = [], [], 0, 0
    process = subprocess.Popen(["dpkg-deb", "--fsys-tarfile", str(path)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                name = PurePosixPath(member.name)
                if name.is_absolute() or ".." in name.parts or any(c in member.name for c in "\0\n\r"):
                    issues.append({"kind": "unsafe-payload-path", "path": member.name})
                if not member.isfile():
                    continue
                file_count += 1
                # Inspection is bounded; tarfile still consumes the entire archive.
                with archive.extractfile(member) as stream:
                    data = stream.read(min(member.size, 256 * 1024))
                executable = bool(member.mode & 0o111)
                if executable:
                    executables.append(member.name)
                if data.startswith(b"\x7fELF") and len(data) >= 20:
                    elf_count += 1
                    machine = struct.unpack(("<" if data[5] == 1 else ">") + "H", data[18:20])[0]
                    if machine != 183 or architecture == "all":
                        issues.append({"kind": "elf-architecture", "path": member.name,
                                       "machine": machine, "declared": architecture})
                if executable and data.startswith(b"#!"):
                    if b"ready on Ocean OS" in data:
                        issues.append({"kind": "confirmed-ready-stub", "path": member.name})
                    if re.search(rb"(?:not implemented|placeholder only|coming soon)", data, re.I):
                        issues.append({"kind": "review-placeholder-text", "path": member.name})
                    first_line = data.split(b"\n", 1)[0].decode("utf-8", "replace")
                    if "/com.termux/" in first_line:
                        issues.append({"kind": "foreign-interpreter", "path": member.name, "value": first_line})
                # Attribution/docs are not configuration defects. Limit this to active APT sources.
                if "/etc/apt/" in member.name and (member.name.endswith((".list", ".sources"))):
                    for line in data.decode("utf-8", "replace").splitlines():
                        if line.lstrip().startswith(("deb ", "deb-src ", "URIs:")) and "termux" in line:
                            issues.append({"kind": "foreign-apt-source", "path": member.name, "value": line})
        if process.wait() != 0:
            raise ValueError("dpkg could not decode the full payload")
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.terminate()
        process.wait()
    return {"files": file_count, "elfFiles": elf_count, "executables": executables, "issues": issues}

def audit(root, payloads=True):
    apt = root / "apt"
    records = [fields(s) for s in stanzas((apt / "dists/stable" / INDEX).read_text())]
    live = {identity(r): r for r in records}
    referenced = {r["Filename"] for r in records}
    rows, invalid, payload_issues = [], [], []
    for path in sorted((apt / "pool").rglob("*.deb")):
        relative = path.relative_to(apt).as_posix()
        row = {"path": relative, "indexed": relative in referenced}
        if path.is_symlink():
            row.update(status="symlink-alias", target=str(path.readlink()), exists=path.exists())
            if not path.exists() or not path.resolve().is_relative_to((apt / "pool").resolve()):
                invalid.append({"path": relative, "error": "broken or escaping symlink"})
            rows.append(row)
            continue
        try:
            control = fields(subprocess.check_output(["dpkg-deb", "--field", str(path)], text=True))
            key = identity(control)
            row.update({k: control[k] for k in ("Package", "Version", "Architecture")})
            digest = hashes(path)
            row["sha256"] = digest["sha256"]
            current = live.get(key)
            if relative in referenced:
                row["status"] = "indexed"
            elif current is None:
                row["status"] = "unindexed-identity"
            else:
                compared = compare_versions(control["Version"], current["Version"])
                row["status"] = ("historical" if compared < 0 else "unindexed-newer" if compared > 0 else
                                 "duplicate-bytes" if digest["sha256"] == current["SHA256"] else "same-version-conflict")
            if payloads and row["indexed"]:
                details = inspect_payload(path, control["Architecture"])
                row["payload"] = details
                payload_issues.extend({"package": control["Package"], **issue} for issue in details["issues"])
        except (ValueError, OSError, subprocess.CalledProcessError, tarfile.TarError) as exc:
            row["status"] = "invalid"
            invalid.append({"path": relative, "error": str(exc)})
        rows.append(row)
    return {"indexedEntries": len(records), "poolFiles": len(rows),
            "poolClassification": dict(collections.Counter(r["status"] for r in rows)),
            "dependencyErrors": dependency_errors(records), "invalidArchives": invalid,
            "payloadIssues": payload_issues, "packages": rows, "runtimeTested": False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.root)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("packages", "payloadIssues")}, indent=2))
    print("Payload issue kinds:", dict(collections.Counter(x["kind"] for x in report["payloadIssues"])))
    return bool(report["invalidArchives"] or report["dependencyErrors"] or report["payloadIssues"])

if __name__ == "__main__":
    raise SystemExit(main())
