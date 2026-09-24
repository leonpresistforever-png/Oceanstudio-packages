#!/usr/bin/env python3
"""Build and validate the Ocean-owned distro manager package.

This packages only Ocean source files. It never copies proot-distro/Termux
payloads, and unresolved distro entries remain safely uninstallable until they
carry a pinned SHA256.
"""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,tempfile

ROOT=Path(__file__).resolve().parents[1]
PREFIX="/data/data/studio.ocean.app/files/usr"
SRC=ROOT/"packages/ocean-distro"
OUT=ROOT/"staging/ocean-distro-repair"
VERSION="1.0.1-1"

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def run(*args,**kw): return subprocess.run(args,check=True,text=True,**kw)

def main():
    shutil.rmtree(OUT,ignore_errors=True)
    pool=OUT/"pool/main"; pool.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="ocean-distro-pkg-") as td:
        stage=Path(td); root=stage/PREFIX.lstrip("/")
        (root/"bin").mkdir(parents=True)
        (root/"share/ocean-distro").mkdir(parents=True)
        shutil.copy2(SRC/"ocean-distro",root/"bin/ocean-distro")
        (root/"bin/ocean-distro").chmod(0o755)
        shutil.copy2(SRC/"distros.json",root/"share/ocean-distro/distros.json")
        debian=stage/"DEBIAN"; debian.mkdir()
        control=(SRC/"control").read_text()
        if f"Version: {VERSION}\n" not in control: raise SystemExit("control version mismatch")
        (debian/"control").write_text(control)
        for p in stage.rglob("*"):
            os.utime(p,(0,0),follow_symlinks=False)
        deb=pool/f"ocean-distro_{VERSION}_all.deb"
        run("dpkg-deb","--root-owner-group","-Zxz","-z6","--build",str(stage),str(deb))
        # Full archive scanner: active runtime must not contain Termux identity.
        import sys; sys.path.insert(0,str(ROOT/"scripts"))
        from forensic_repository import scan_tar
        rows=list(scan_tar(deb))+list(scan_tar(deb,control=True))
        hard={"foreign-app-prefix","foreign-repository","foreign-runtime-variable",
              "foreign-link-target","unsafe-archive-path","confirmed-ready-stub","invalid-elf-header","elf-reader-error"}
        defects=[{"path":r["path"],**f} for r in rows for f in r.get("findings",[]) if f["kind"] in hard]
        if defects: raise SystemExit("ocean-distro package audit failed: "+repr(defects[:20]))
        registry=json.loads((SRC/"distros.json").read_text())
        if len(registry)!=13: raise SystemExit(f"expected 13 distro records, got {len(registry)}")
        verified=[n for n,v in registry.items() if isinstance(v.get("sha256"),str) and len(v["sha256"])==64]
        unresolved=[n for n,v in registry.items() if n not in verified]
        # Real source-level installer tests exercise lookup/case handling, download
        # verification, manager separation, interrupted downloads and /dev handling.
        test=subprocess.run(["python3",str(ROOT/"tests/test-ocean-distro.py")],capture_output=True,text=True)
        if test.returncode: raise SystemExit("ocean-distro tests failed:\n"+test.stdout+"\n"+test.stderr)
        report={"status":"PASS_CANDIDATE","package":"ocean-distro","version":VERSION,
                "sha256":sha(deb),"sourcePolicy":"Ocean-owned manager; no Termux/proot-distro payload copied",
                "prefix":PREFIX,"advertisedDistros":list(registry),"verifiedChecksumEntries":verified,
                "unresolvedChecksumEntries":unresolved,"sourceTests":"PASS",
                "physicalAndroidDeviceTested":False}
        (OUT/"provenance.json").write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report,indent=2))
if __name__=="__main__": main()
