#!/usr/bin/env python3
"""Audit Ocean APT index: unique keys, duplicates, and quality rejects."""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def resolve_repo_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    env = Path(__import__("os").environ.get("OCEAN_PACKAGES_ROOT", ""))
    if env.is_dir() and (env / "apt").is_dir():
        return env.resolve()
    if (ROOT / "apt").is_dir():
        return ROOT.resolve()
    sibling = ROOT.parent / "Oceanstudio-packages"
    if sibling.is_dir() and (sibling / "apt").is_dir():
        return sibling.resolve()
    raise SystemExit(
        "No APT tree found. Set --root or OCEAN_PACKAGES_ROOT to Oceanstudio-packages."
    )


def load_index_names(repo: Path) -> list[str]:
    gz = repo / "apt/dists/stable/main/binary-aarch64/Packages.gz"
    plain = repo / "apt/dists/stable/main/binary-aarch64/Packages"
    if gz.is_file():
        text = gzip.open(gz, "rt", encoding="utf-8", errors="replace").read()
    elif plain.is_file():
        text = plain.read_text(encoding="utf-8", errors="replace")
    else:
        raise SystemExit(f"Missing Packages index under {repo / 'apt/dists/stable'}")
    names: list[str] = []
    for block in text.split("\n\n"):
        if not block.strip().startswith("Package:"):
            continue
        for line in block.splitlines():
            if line.startswith("Package:"):
                names.append(line.split(":", 1)[1].strip())
                break
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="Oceanstudio-packages (or apt/) root")
    parser.add_argument("--json", type=Path, help="Write machine-readable audit")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "scripts"))
    from package_quality import assess_name_set, junk_name_reason

    repo = resolve_repo_root(args.root)
    names = load_index_names(repo)
    unique = sorted(set(names))
    dupes = {n: c for n, c in __import__("collections").Counter(names).items() if c > 1}
    junk_hits = [n for n in unique if junk_name_reason(n)]

    staging_rejects: list[dict[str, object]] = []
    staging = repo / "staging"
    if staging.is_dir():
        from package_quality import assess_deb

        for deb in sorted(staging.rglob("*.deb")):
            verdict = assess_deb(deb)
            if verdict.reject:
                staging_rejects.append(
                    {
                        "path": deb.relative_to(repo).as_posix(),
                        "package": verdict.package,
                        "reasons": list(verdict.reasons),
                    }
                )

    name_audit = assess_name_set(unique)
    report = {
        "repositoryRoot": str(repo),
        "indexedEntries": len(names),
        "uniquePackageNames": len(unique),
        "duplicateKeys": dupes,
        "junkNamesInIndex": junk_hits,
        "junkNameBuckets": name_audit["junk_by_reason"],
        "stagingRejectedWouldBeJunk": staging_rejects,
        "stagingRejectedCount": len(staging_rejects),
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json:
        args.json.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
