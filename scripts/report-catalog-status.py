#!/usr/bin/env python3
"""Report declared roots separately from packages that were actually built."""
import argparse
import json
import pathlib
import subprocess


parser = argparse.ArgumentParser()
parser.add_argument("catalog", type=pathlib.Path)
parser.add_argument("debs", type=pathlib.Path)
parser.add_argument("report", type=pathlib.Path)
args = parser.parse_args()

catalog = json.loads(args.catalog.read_text())
artifacts = {}
for deb in sorted(args.debs.glob("*.deb")):
    name = subprocess.check_output(
        ["dpkg-deb", "-f", str(deb), "Package"], text=True
    ).strip()
    artifacts.setdefault(name, []).append(deb.name)

roots = []
for phase, names in catalog["phases"].items():
    for name in names:
        built = name in artifacts
        roots.append(
            {
                "name": name,
                "phase": phase,
                "state": "BUILT" if built else "DECLARED",
                "artifacts": artifacts.get(name, []),
            }
        )

built_count = sum(item["state"] == "BUILT" for item in roots)
missing = [item["name"] for item in roots if item["state"] != "BUILT"]
report = {
    "schemaVersion": 1,
    "target": catalog["target"],
    "declaredRootCount": len(roots),
    "builtRootCount": built_count,
    "repositoryPackageCount": len(artifacts),
    "missingRoots": missing,
    "roots": roots,
    "summary": (
        f"Ocean catalogue roots built: {built_count}/{len(roots)}; "
        f"repository binary packages: {len(artifacts)}; "
        f"missing roots: {', '.join(missing) if missing else 'none'}"
    ),
}
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, indent=2) + "\n")
print(report["summary"])
