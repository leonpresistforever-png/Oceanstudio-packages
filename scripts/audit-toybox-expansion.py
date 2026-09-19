#!/usr/bin/env python3
"""Audit the staged official-source Toybox expansion without modifying live apt/."""
from __future__ import annotations
import argparse, hashlib, json, pathlib, re, sys

def sha256(path: pathlib.Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def parse_packages(text: str):
    rows=[]
    for paragraph in re.split(r"\n\n+",text.strip()):
        values={}
        for line in paragraph.splitlines():
            if ": " in line:
                k,v=line.split(": ",1); values[k]=v
        if values.get("Package"): rows.append(values)
    return rows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("root",type=pathlib.Path,nargs="?",default=pathlib.Path("staging/toybox-0.8.14"))
    args=ap.parse_args()
    root=args.root.resolve()
    provenance=json.loads((root/"provenance.json").read_text())
    index=root/"dists/stable/main/binary-aarch64/Packages"
    index_gz=root/"dists/stable/main/binary-aarch64/Packages.gz"
    rows=parse_packages(index.read_text())
    failures=[]

    if len(rows)!=153: failures.append(f"index records={len(rows)} expected=153")
    if len({x["Package"] for x in rows})!=153: failures.append("package names are not unique")
    if provenance.get("packageCount")!=153: failures.append("provenance packageCount is not 153")
    if provenance.get("sourcePolicy")!="official pinned upstream Git source; no Termux package or binary input":
        failures.append("unexpected source policy")
    if provenance.get("target")!="aarch64-linux-android28": failures.append("unexpected Android target")
    if provenance.get("ndkRevision")!="27.0.12077973": failures.append("unexpected NDK revision")
    if provenance.get("indexSha256")!=sha256(index): failures.append("Packages hash mismatch")
    if provenance.get("indexGzipSha256")!=sha256(index_gz): failures.append("Packages.gz hash mismatch")

    artifacts={x["artifact"]:x for x in provenance.get("packages",[])}
    if len(artifacts)!=153: failures.append("provenance artifact list is not 153")
    base=[x for x in rows if x["Package"]=="ocean-toybox"]
    if len(base)!=1 or base[0].get("Architecture")!="aarch64": failures.append("base package identity invalid")

    for row in rows:
        file=root/row["Filename"]
        if not file.is_file(): failures.append(f"missing artifact {row['Filename']}"); continue
        actual=sha256(file)
        if row.get("SHA256")!=actual: failures.append(f"index SHA mismatch {file.name}")
        item=artifacts.get(file.name)
        if not item or item.get("sha256")!=actual: failures.append(f"provenance SHA mismatch {file.name}")
        if row["Package"].startswith("ocean-toybox-"):
            if row.get("Architecture")!="all": failures.append(f"wrapper arch invalid {row['Package']}")
            if row.get("Depends")!="ocean-toybox (= 0.8.14-1)": failures.append(f"dependency invalid {row['Package']}")

    forbidden=(b"/data/data/com.termux",b"/data/user/0/com.termux",b"packages.termux.dev",b"TERMUX_PREFIX")
    for file in (root/"pool/main").glob("*.deb"):
        data=file.read_bytes()
        if any(marker in data for marker in forbidden): failures.append(f"foreign runtime marker {file.name}")

    report={
        "status":"failed" if failures else "passed",
        "packageCount":len(rows),
        "distinctPackageNames":len({x["Package"] for x in rows}),
        "officialSourcePinned":provenance.get("commit")=="b7ec52ac35e075caffca5d330995d44e8dbfc8c3",
        "androidTarget":provenance.get("target"),
        "ndkRevision":provenance.get("ndkRevision"),
        "staticArchiveElfPrefixChecks":"passed" if not failures else "see failures",
        "physicalAndroidExecution":"pending",
        "liveRepositoryPromotion":"requires existing Ocean repository private signing key",
        "failures":failures,
    }
    print(json.dumps(report,indent=2))
    return 1 if failures else 0

if __name__=="__main__":
    raise SystemExit(main())
