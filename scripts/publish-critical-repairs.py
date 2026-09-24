#!/usr/bin/env python3
"""Publish a minimal signed repair snapshot for known critical packages only.

This intentionally does NOT sweep every staged package into the live catalogue.
It starts from the current live Packages file, replaces only independently
validated critical candidates, rechecks dependency resolution and payload
defects, then signs one coherent APT snapshot with the already-trusted archive
key. No signature verification is disabled and no package is silently deleted.
"""
from pathlib import Path
import argparse, gzip, hashlib, json, os, shutil, subprocess, tempfile, sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from index_all_staged import fields,stanzas,identity,parse_deb,make_stanza,compare_versions,require_signing_key,release_bytes,verify_release,INDEX
from audit_package_payloads import dependency_errors
from forensic_repository import scan_tar

CANDIDATES={
 "openjdk-21": ROOT/"staging/openjdk-21-repair/openjdk-21_21.0.12-1+ocean1_aarch64.deb",
 "caddy": ROOT/"staging/official-native-repairs/caddy/pool/main/caddy_2.11.4-1+ocean1_aarch64.deb",
 "strace": ROOT/"staging/official-native-repairs/strace/pool/main/strace_7.2-1+ocean1_aarch64.deb",
 "gdb": ROOT/"staging/official-gdb-repair/pool/main/gdb_9.2-1+ocean1_aarch64.deb",
}
HARD={"foreign-app-prefix","foreign-repository","foreign-runtime-variable","foreign-link-target",
      "unsafe-archive-path","confirmed-ready-stub","invalid-elf-header","elf-reader-error"}

def errkey(e): return json.dumps(e,sort_keys=True,separators=(",",":"))

def load_current():
    d=ROOT/"apt/dists/stable"
    return [fields(s) for s in stanzas((d/INDEX).read_text())]

def validate_candidate(name,path,current):
    if not path.is_file(): raise ValueError(f"Missing validated candidate: {path.relative_to(ROOT)}")
    text,digest=parse_deb(path); rec=fields(text)
    if rec["Package"]!=name: raise ValueError(f"{path}: package name mismatch")
    old=next((r for r in current if identity(r)==identity(rec)),None)
    if not old: raise ValueError(f"{name}: no current indexed package to repair")
    if compare_versions(rec["Version"],old["Version"])<=0:
        raise ValueError(f"{name}: repaired version must be newer than live {old['Version']}")
    rows=list(scan_tar(path))+list(scan_tar(path,control=True))
    bad=[{"path":r["path"],**f} for r in rows for f in r.get("findings",[]) if f["kind"] in HARD]
    if bad: raise ValueError(f"{name}: repaired candidate still has hard payload defects: {bad[:10]}")
    return text,digest,rec

def plan():
    current=load_current(); replacements={}; evidence={}
    for name,path in CANDIDATES.items():
        text,digest,rec=validate_candidate(name,path,current)
        replacements[identity(rec)]=(path,text,digest,rec)
        evidence[name]={"path":str(path.relative_to(ROOT)),"version":rec["Version"],"sha256":digest["sha256"]}
    after=[]
    for r in current:
        item=replacements.get(identity(r))
        if item:
            path,text,digest,rec=item
            stanza=fields(make_stanza(text,digest,path.name,"pool/main/"+path.name))
            after.append(stanza)
        else:
            after.append(r)
    before_err={errkey(e) for e in dependency_errors(current)}
    after_err={errkey(e) for e in dependency_errors(after)}
    new_err=sorted(after_err-before_err)
    if new_err: raise ValueError("Critical repairs introduce dependency errors: "+repr(new_err[:20]))
    if len(after)!=len(current): raise ValueError("Critical repair snapshot changed package count")
    names={r["Package"] for r in after}
    for name in CANDIDATES:
        if name not in names: raise ValueError("Critical package disappeared: "+name)
    return current,after,replacements,{"status":"READY_FOR_SIGNING","indexedEntries":len(after),
        "replacements":evidence,"existingDependencyErrors":len(before_err),"newDependencyErrors":0,
        "packageDeletionCount":0,"androidPhysicalRuntimeTested":False}

def publish():
    current,after,replacements,report=plan()
    apt=ROOT/"apt"; dists=apt/"dists/stable"; keyring=apt/"ocean.gpg"
    fingerprint=require_signing_key(keyring)
    stanzas_out=[]
    for r in after:
        item=replacements.get(identity(r))
        if item:
            path,text,digest,_=item
            stanzas_out.append(make_stanza(text,digest,path.name,"pool/main/"+path.name))
        else:
            # Preserve existing control metadata but regenerate exactly from the
            # already indexed package bytes to prevent stale size/hash fields.
            filename=r["Filename"]; deb=apt/filename
            text,digest=parse_deb(deb)
            stanzas_out.append(make_stanza(text,digest,deb.name,filename))
    packages=("\n\n".join(stanzas_out)+"\n").encode()
    compressed=gzip.compress(packages,mtime=0)
    with tempfile.TemporaryDirectory(prefix="ocean-critical-signed-",dir=ROOT) as td:
        tmp=Path(td); (tmp/INDEX).parent.mkdir(parents=True)
        (tmp/INDEX).write_bytes(packages); (tmp/(str(INDEX)+".gz")).write_bytes(compressed)
        (tmp/"Release").write_bytes(release_bytes(packages,compressed))
        for fn,op in (("InRelease","--clearsign"),("Release.gpg","--detach-sign")):
            subprocess.run(["gpg","--batch","--yes","--local-user",fingerprint,"--digest-algo","SHA256",
                            "--output",str(tmp/fn),op,str(tmp/"Release")],check=True)
        verify_release(tmp,keyring)
        # Only after the complete signed snapshot verifies do any live files move.
        for _,(src,_,digest,_) in replacements.items():
            dst=apt/"pool/main"/src.name
            if not dst.exists() or hashlib.sha256(dst.read_bytes()).hexdigest()!=digest["sha256"]:
                shutil.copyfile(src,dst)
        for fn in (str(INDEX),str(INDEX)+".gz","Release","Release.gpg","InRelease"):
            os.replace(tmp/fn,dists/fn)
    verify_release(dists,keyring)
    report.update(status="PUBLISHED_SIGNED",fingerprint=fingerprint)
    return report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--plan",type=Path)
    a=ap.parse_args()
    try:
        if a.plan:
            *_,report=plan(); a.plan.parent.mkdir(parents=True,exist_ok=True);a.plan.write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report,indent=2))
        else:
            report=publish();print(json.dumps(report,indent=2))
    except (ValueError,OSError,subprocess.CalledProcessError) as exc:
        ap.exit(1,"Critical publication failed: "+str(exc)+"\n")
if __name__=="__main__":main()
