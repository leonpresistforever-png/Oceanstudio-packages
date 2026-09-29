#!/usr/bin/env python3
"""Scan the live APT index and staging tree; write a plain-text issue list."""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "apt/dists/stable/main/binary-aarch64/Packages.gz"


def load_index():
    text = gzip.open(INDEX, "rt", encoding="utf-8", errors="replace").read()
    blocks = [b for b in text.split("\n\n") if b.strip().startswith("Package:")]
    records = []
    for block in blocks:
        rec = {}
        for line in block.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                rec[key.strip()] = value.strip()
        records.append(rec)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "scripts"))
    from index_all_staged import parse_deb, ROOT as IR

    records = load_index()
    names = {r["Package"] for r in records}
    lines = [
        "Ocean package index issue list (plain)",
        f"Indexed package names: {len(names)}",
        "",
    ]

    # Signed metadata (static check)
    try:
        from index_all_staged import verify_release

        verify_release(IR / "apt/dists/stable", IR / "apt/ocean.gpg")
        lines.append("[OK] Signed Release matches InRelease and Packages checksums.")
    except Exception as exc:
        lines.append(f"[BLOCKER] Signed APT metadata: {exc}")

    # Staging vs pool
    staged_conflicts = []
    staged_new = []
    for deb in sorted((IR / "staging").rglob("*.deb")):
        _, digest = parse_deb(deb)
        pool = IR / "apt/pool/main" / deb.name
        rel = deb.relative_to(IR).as_posix()
        if pool.exists():
            _, pool_digest = parse_deb(pool)
            if digest["sha256"] != pool_digest["sha256"]:
                staged_conflicts.append(rel)
        else:
            staged_new.append(deb.name)

    lines.extend(["", f"Staged .deb files not in live index: {len(staged_new)}"])
    for name in sorted(staged_new)[:80]:
        lines.append(f"  - {name}")
    if len(staged_new) > 80:
        lines.append(f"  ... and {len(staged_new) - 80} more")

    lines.extend(["", f"Staged same filename as pool but different bytes (blocks promotion): {len(staged_conflicts)}"])
    for item in staged_conflicts:
        lines.append(f"  - {item}")

    # Priority gaps
    targets = json.loads((IR / "sources/expansion-1000/target-packages.json").read_text())
    missing = targets.get("priorityMissing", [])
    lines.extend(["", f"Priority name gaps (not in index): {len(missing)}"])
    for name in missing:
        lines.append(f"  - {name}")

    # Flat pool layout
    flat = sum(1 for r in records if r.get("Filename", "").startswith("pool/main/") and r["Filename"].count("/") == 2)
    lines.extend(
        [
            "",
            f"Packages using flat pool/main/<deb> only (no subdirectory): {flat}",
            f"Packages with ocean- prefix: {sum(1 for n in names if n.startswith('ocean-'))}",
        ]
    )

    # Depends sanity
    broken = []
    for rec in records:
        dep = rec.get("Depends", "")
        if not dep:
            continue
        for part in re.split(r",\s*", dep):
            token = part.split("|")[0].strip()
            match = re.match(r"^([a-zA-Z0-9+.-]+)", token)
            if match and match.group(1) not in names:
                broken.append((rec["Package"], match.group(1)))
    lines.extend(["", f"Broken Depends references in index: {len(broken)}"])
    for pkg, dep in broken[:40]:
        lines.append(f"  - {pkg} -> {dep}")

    # Promotion plan
    lines.extend(["", "Promotion plan (read-only):"])
    try:
        from index_all_staged import select_packages

        _, report = select_packages(IR)
        lines.append(f"  Would index {report['indexedAfter']} entries (currently {report['indexedBefore']}).")
        lines.append(f"  Pending updates: {len(report['updates'])}")
    except Exception as exc:
        lines.append(f"  [BLOCKED] {exc}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "indexed": len(names),
                    "stagedNew": len(staged_new),
                    "stagedConflicts": staged_conflicts,
                    "priorityMissing": missing,
                    "brokenDepends": broken,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
