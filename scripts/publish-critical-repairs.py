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
 "librsync": ROOT/"staging/upstream-repairs/pool/main/librsync_2.3.4-1_aarch64.deb",
 "luajit": ROOT/"apt/pool/main/luajit_1:2.1.1787165859+g1ee778a_aarch64.deb",
 "ocean-distro": ROOT/"staging/ocean-distro-repair/pool/main/ocean-distro_1.0.1-1_all.deb",
 "proot-distro": ROOT/"staging/ocean-distro-repair/pool/main/proot-distro_4.18.0-1+ocean1_all.deb",
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
    if old and compare_versions(rec["Version"],old["Version"])<=0:
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
        old=next((r for r in current if identity(r)==identity(rec)),None)
        evidence[name]={"path":str(path.relative_to(ROOT)),"version":rec["Version"],"sha256":digest["sha256"],
                        "action":"replace" if old else "add"}
    after=[]
    current_ids={identity(r) for r in current}
    for r in current:
        item=replacements.get(identity(r))
        if item:
            path,text,digest,rec=item
            stanza=fields(make_stanza(text,digest,path.name,"pool/main/"+path.name))
            after.append(stanza)
        else:
            after.append(r)
    # Add missing dependency packages only when they passed the same full payload
    # validation. Existing packages are never deleted to make the graph pass.
    for key,item in replacements.items():
        if key in current_ids:
            continue
        path,text,digest,rec=item
        after.append(fields(make_stanza(text,digest,path.name,"pool/main/"+path.name)))
    before_err={errkey(e) for e in dependency_errors(current)}
    after_err={errkey(e) for e in dependency_errors(after)}
    new_err=sorted(after_err-before_err)
    if new_err: raise ValueError("Critical repairs introduce dependency errors: "+repr(new_err[:20]))
    if after_err:
        raise ValueError("Critical repair snapshot still has unresolved dependency errors: "+repr(sorted(after_err)[:20]))
    additions=sum(1 for e in evidence.values() if e["action"]=="add")
    if len(after)!=len(current)+additions:
        raise ValueError("Critical repair snapshot changed package count unexpectedly")
    names={r["Package"] for r in after}
    for name in CANDIDATES:
        if name not in names: raise ValueError("Critical package disappeared: "+name)
    return current,after,replacements,{"status":"READY_FOR_SIGNING","indexedEntries":len(after),
        "replacements":evidence,"dependencyErrorsBefore":len(before_err),"dependencyErrorsAfter":len(after_err),
        "newDependencyErrors":0,"packageAdditions":additions,
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
            filename=r["Filename"]; deb=apt/filename
            text,digest=parse_deb(deb)
            stanzas_out.append(make_stanza(text,digest,deb.name,filename))
    packages = ((chr(10) + chr(10)).join(stanzas_out) + chr(10)).encode()
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
            *_,report=plan(); a.plan.parent.mkdir(parents=True,exist_ok=True); a.plan.write_text(json.dumps(report,indent=2)+chr(10)); print(json.dumps(report,indent=2))
        else:
            report=publish(); print(json.dumps(report,indent=2))
    except (ValueError,OSError,subprocess.CalledProcessError) as exc:
        ap.exit(1, "Critical publication failed: " + str(exc) + chr(10))
if __name__=="__main__":main()
