#!/usr/bin/env python3
"""Build a clean official-source GDB for the Ocean Android/AArch64 prefix.

The live gdb package contains a foreign /data/data/com.termux build-prefix
string and is therefore not eligible for publication. This builder never uses
the existing gdb .deb or any foreign-distribution binary as an input.
"""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess, tempfile

ROOT=Path(__file__).resolve().parents[1]
PREFIX="/data/data/studio.ocean.app/files/usr"
SOURCE="https://sourceware.org/git/binutils-gdb.git"
TAG="gdb-9.2-release"
VERSION="9.2-1+ocean1"

def run(cmd,**kw):
    print("+"," ".join(map(str,cmd)),flush=True)
    return subprocess.run(list(map(str,cmd)),check=True,text=True,**kw)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ndk",type=Path,required=True)
    ap.add_argument("--output",type=Path,default=ROOT/"staging/official-gdb-repair")
    a=ap.parse_args()
    ndk=a.ndk.resolve()
    if "Pkg.Revision = 27.0.12077973" not in (ndk/"source.properties").read_text():
        raise SystemExit("Official Android NDK r27 is required")
    tools=ndk/"toolchains/llvm/prebuilt/linux-x86_64/bin"
    cc=tools/"aarch64-linux-android28-clang"
    cxx=tools/"aarch64-linux-android28-clang++"
    out=a.output.resolve(); shutil.rmtree(out,ignore_errors=True)
    pool=out/"pool/main"; pool.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="ocean-gdb-source-") as td:
        work=Path(td); src=work/"src"; build=work/"build"; stage=work/"stage"
        run(["git","clone","--depth=1","--branch",TAG,SOURCE,str(src)])
        commit=subprocess.check_output(["git","-C",str(src),"rev-parse","HEAD"],text=True).strip()
        build.mkdir()
        env=dict(os.environ,CC=str(cc),CXX=str(cxx),AR=str(tools/"llvm-ar"),
                 RANLIB=str(tools/"llvm-ranlib"),STRIP=str(tools/"llvm-strip"),
                 CFLAGS=f"-O2 -ffile-prefix-map={work}=/usr/src/ocean -fdebug-prefix-map={work}=/usr/src/ocean",
                 CXXFLAGS=f"-O2 -ffile-prefix-map={work}=/usr/src/ocean -fdebug-prefix-map={work}=/usr/src/ocean",
                 LDFLAGS="-static -Wl,-z,max-page-size=16384",
                 SOURCE_DATE_EPOCH="0",MAKEINFO="true")
        configure=[
          str(src/"configure"),"--host=aarch64-linux-android","--target=aarch64-linux-android",
          "--prefix="+PREFIX,"--disable-nls","--disable-werror","--disable-tui",
          "--without-python","--without-guile","--without-expat","--without-lzma",
          "--without-zstd","--without-libunwind","--without-debuginfod",
          "--without-babeltrace","--disable-source-highlight","--with-system-readline=no"
        ]
        run(configure,cwd=build,env=env)
        run(["make","-j2","all-gdb"],cwd=build,env=env)
        binary=build/"gdb/gdb"
        if not binary.is_file(): raise SystemExit("GDB binary was not produced")
        info=subprocess.check_output(["readelf","-hW","-lW","-dW",str(binary)],text=True)
        if "AArch64" not in info: raise SystemExit("GDB is not AArch64")
        if "Requesting program interpreter" in info or "(NEEDED)" in info:
            raise SystemExit("GDB candidate is not fully static")
        data=binary.read_bytes()
        forbidden=(b"/data/data/com.termux",b"/data/user/0/com.termux",b"packages.termux",b"TERMUX_PREFIX")
        if any(x.lower() in data.lower() for x in forbidden):
            raise SystemExit("Foreign Termux identity remains in rebuilt GDB")
        ver=subprocess.run(["qemu-aarch64",str(binary),"--version"],capture_output=True,text=True,timeout=30)
        if ver.returncode or "GNU gdb" not in ver.stdout or "9.2" not in ver.stdout:
            raise SystemExit("Actual ARM GDB --version smoke test failed:\n"+ver.stdout+"\n"+ver.stderr)
        root=stage/PREFIX.lstrip("/"); (root/"bin").mkdir(parents=True)
        shutil.copy2(binary,root/"bin/gdb"); (root/"bin/gdb").chmod(0o755)
        doc=root/"share/doc/gdb"; doc.mkdir(parents=True)
        for name in ("COPYING","COPYING3","COPYING3.LIB","README"):
            p=src/name
            if p.is_file(): shutil.copy2(p,doc/name)
        debian=stage/"DEBIAN"; debian.mkdir()
        (debian/"control").write_text(
          f"Package: gdb\nVersion: {VERSION}\nArchitecture: aarch64\n"
          "Maintainer: OceanStudio <maintainer@ocean.studio>\nSection: devel\nPriority: optional\n"
          "Homepage: https://sourceware.org/gdb/\n"
          "Description: GNU debugger rebuilt from official upstream source for Ocean Android/AArch64\n")
        deb=pool/f"gdb_{VERSION}_aarch64.deb"
        run(["dpkg-deb","--root-owner-group","-Zxz","-z6","--build",str(stage),str(deb)])
        # Full package-level foreign marker audit using the same publication scanner.
        import sys; sys.path.insert(0,str(ROOT/"scripts"))
        from forensic_repository import scan_tar
        rows=list(scan_tar(deb))+list(scan_tar(deb,control=True))
        hard={"foreign-app-prefix","foreign-repository","foreign-runtime-variable",
              "foreign-link-target","unsafe-archive-path","confirmed-ready-stub","invalid-elf-header","elf-reader-error"}
        defects=[{"path":r["path"],**f} for r in rows for f in r.get("findings",[]) if f["kind"] in hard]
        if defects: raise SystemExit("Full GDB package audit failed: "+repr(defects))
        report={"status":"PASS_CANDIDATE","package":"gdb","version":VERSION,"source":SOURCE,
                "tag":TAG,"commit":commit,"sha256":sha(deb),"target":"aarch64-linux-android28",
                "prefix":PREFIX,"qemuArm64Version":ver.stdout.splitlines()[0],
                "static":True,"foreignRuntimeMarkers":[],"androidPhonePtraceTested":False,
                "limitation":"QEMU user mode proves executable startup/version, not ptrace debugging on a physical Android device"}
        (out/"provenance.json").write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report,indent=2))
if __name__=="__main__": main()
