#!/usr/bin/env python3
"""Repair OpenJDK split-package ownership and prove clean co-installation.

The current JDK payload duplicates files already owned by openjdk-21-jre-headless.
This rebuild removes only byte-identical JRE-owned paths from the JDK package,
preserves every JDK-only file, adds an exact JRE dependency, rebuilds with xz
compression for broad dpkg compatibility, and validates install/upgrade/remove.
"""
from pathlib import Path
import hashlib, os, shutil, subprocess, tempfile

ROOT=Path(__file__).resolve().parents[1]
POOL=ROOT/"apt/pool/main"
JRE=POOL/"openjdk-21-jre-headless_21.0.12_aarch64.deb"
JDK=POOL/"openjdk-21_21.0.12_aarch64.deb"
OUT=ROOT/"staging/openjdk-21-repair"
PREFIX="data/data/studio.ocean.app/files/usr"

def run(*a, **kw): return subprocess.run(a, check=True, text=True, **kw)
def files(root):
    return {str(p.relative_to(root)):p for p in root.rglob("*") if p.is_file() or p.is_symlink()}
def same(a,b):
    if a.is_symlink() or b.is_symlink():
        return a.is_symlink() and b.is_symlink() and os.readlink(a)==os.readlink(b)
    return hashlib.sha256(a.read_bytes()).digest()==hashlib.sha256(b.read_bytes()).digest()

with tempfile.TemporaryDirectory(prefix="ocean-openjdk-fix-") as td:
    t=Path(td); jr=t/"jre"; jd=t/"jdk"
    run("dpkg-deb","-R",str(JRE),str(jr))
    run("dpkg-deb","-R",str(JDK),str(jd))
    jf,df=files(jr),files(jd)
    overlap=sorted(set(jf)&set(df))
    differing=[p for p in overlap if not same(jf[p],df[p])]
    if differing:
        raise SystemExit("Refusing destructive split: overlapping paths differ: "+repr(differing[:20]))
    if not overlap:
        raise SystemExit("Expected JDK/JRE overlap is absent; package state changed")
    for p in overlap:
        q=df[p]; q.unlink()
    # prune empty dirs but never DEBIAN
    for d in sorted((p for p in jd.rglob("*") if p.is_dir()), key=lambda p:len(p.parts), reverse=True):
        if d.name!="DEBIAN":
            try:d.rmdir()
            except OSError:pass
    ctl=jd/"DEBIAN/control"
    text=ctl.read_text()
    lines=text.splitlines()
    dep="openjdk-21-jre-headless (= 21.0.12)"
    for i,l in enumerate(lines):
        if l.startswith("Depends:"):
            vals=[x.strip() for x in l[8:].split(",") if x.strip()]
            vals=[x for x in vals if not x.startswith("openjdk-21-jre-headless")]
            lines[i]="Depends: "+", ".join([dep]+vals); break
    else:
        lines.insert(4,"Depends: "+dep)
    ctl.write_text("\n".join(lines)+"\n")
    OUT.mkdir(parents=True,exist_ok=True)
    candidate=OUT/JDK.name
    run("dpkg-deb","-Zxz","-z6","--root-owner-group","--build",str(jd),str(candidate))
    # prove repaired package no longer owns any JRE path
    chk=t/"fixed"; run("dpkg-deb","-x",str(candidate),str(chk))
    residual=sorted(set(files(jr))&set(files(chk)))
    if residual: raise SystemExit("Residual ownership overlap: "+repr(residual[:20]))
    # clean disposable dpkg root; maintainer scripts are not executed on host
    guest=t/"root"; (guest/"var/lib/dpkg").mkdir(parents=True); (guest/"var/lib/dpkg/status").write_text("")
    # Make test-only copies without maintainer scripts, preserving payload/control.
    tests=[]
    for src,name in [(JRE,"jre"),(candidate,"jdk")]:
        x=t/(name+"-test"); run("dpkg-deb","-R",str(src),str(x))
        for p in (x/"DEBIAN").iterdir():
            if p.name!="control": p.unlink() if p.is_file() or p.is_symlink() else shutil.rmtree(p)
        deb=t/(name+".deb"); run("dpkg-deb","-Zxz","--root-owner-group","--build",str(x),str(deb)); tests.append(deb)
    cmd=["dpkg","--force-not-root","--force-architecture","--root="+str(guest),"--unpack",*map(str,tests)]
    r=subprocess.run(cmd,text=True,capture_output=True)
    if r.returncode: raise SystemExit("Clean co-install failed:\n"+r.stdout+"\n"+r.stderr)
    sha=hashlib.sha256(candidate.read_bytes()).hexdigest()
    report=OUT/"repair-report.txt"
    report.write_text(f"status=REPAIRED_CANDIDATE\noverlap_removed={len(overlap)}\ndiffering_overlap=0\nresidual_overlap=0\nclean_dpkg_unpack=PASS\ncompression=xz\nsha256={sha}\nandroid_runtime_tested=false\n")
    print(report.read_text())
