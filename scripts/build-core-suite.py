#!/usr/bin/env python3
"""Build isolated official-source Ocean core-suite packages for Android/AArch64."""
from __future__ import annotations
import argparse, gzip, hashlib, json, os, re, shutil, subprocess, tarfile, tempfile, urllib.request
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parents[1]
PREFIX="/data/data/studio.ocean.app/files/usr"
FORBIDDEN=(b"/data/data/com.termux",b"/data/user/0/com.termux",b"packages.termux.dev",b"TERMUX_PREFIX")

def run(cmd,cwd=None,env=None,capture=False):
    print("+"," ".join(map(str,cmd)),flush=True)
    return subprocess.run(list(map(str,cmd)),cwd=cwd,env=env,check=True,text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None)

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def require(cmd):
    p=shutil.which(cmd)
    if not p: raise SystemExit("missing build command: "+cmd)
    return p

def fetch(url,out):
    req=urllib.request.Request(url,headers={"User-Agent":"OceanStudio-package-builder/1"})
    with urllib.request.urlopen(req,timeout=180) as r, open(out,"wb") as f:
        if not r.url.startswith("https://"): raise SystemExit("insecure redirect: "+r.url)
        shutil.copyfileobj(r,f)

def safe_extract(archive,dest):
    with tarfile.open(archive) as t:
        for m in t.getmembers():
            p=PurePosixPath(m.name)
            if p.is_absolute() or ".." in p.parts: raise SystemExit("unsafe archive path")
        t.extractall(dest,filter="data")
    dirs=[x for x in dest.iterdir() if x.is_dir()]
    if len(dirs)!=1: raise SystemExit("archive should contain one source directory")
    return dirs[0]

def clone_pinned(url,commit,dest):
    run(["git","clone","--no-checkout",url,dest])
    run(["git","-C",dest,"fetch","--depth=1","origin",commit])
    run(["git","-C",dest,"checkout","--detach","-q",commit])
    head=run(["git","-C",dest,"rev-parse","HEAD"],capture=True).stdout.strip()
    if head!=commit: raise SystemExit("source commit mismatch")

def clone_tag(url,tag,dest):
    run(["git","clone","--depth=1","--branch",tag,url,dest])
    head=run(["git","-C",dest,"rev-parse","HEAD"],capture=True).stdout.strip()
    exact=run(["git","-C",dest,"describe","--tags","--exact-match"],capture=True).stdout.strip()
    if exact!=tag: raise SystemExit("source tag mismatch")
    return head

def control(stage,fields):
    d=stage/"DEBIAN";d.mkdir(parents=True)
    (d/"control").write_text("".join(f"{k}: {v}\n" for k,v in fields))

def normalize(root):
    for p in sorted(root.rglob("*"),reverse=True):
        try: os.utime(p,(0,0),follow_symlinks=False)
        except FileNotFoundError: pass
    os.utime(root,(0,0))

def build_deb(stage,out):
    normalize(stage);out.parent.mkdir(parents=True,exist_ok=True)
    run(["dpkg-deb","--root-owner-group","-Zxz","--build",stage,out])

def validate_binary(path,readelf):
    data=path.read_bytes()
    if any(x in data for x in FORBIDDEN): raise SystemExit("foreign runtime identity: "+str(path))
    info=run([readelf,"-h","-l","-d",path],capture=True).stdout
    if "AArch64" not in info: raise SystemExit("not AArch64: "+str(path))
    interps=re.findall(r"Requesting program interpreter: ([^\]]+)",info)
    if interps and interps!=["/system/bin/linker64"]: raise SystemExit("unexpected interpreter: "+repr(interps))
    needed=re.findall(r"\(NEEDED\).*?\[([^\]]+)\]",info)
    if any(x in ("libc.so.6","libpthread.so.0") or x.startswith("ld-linux") for x in needed):
        raise SystemExit("host libc dependency: "+repr(needed))
    return {"needed":needed,"interpreter":interps}

def package_binary(name,version,binary,license_file,out,description,extra=None,depends=None):
    with tempfile.TemporaryDirectory(prefix=name+"-pkg-") as td:
        stage=Path(td);prefix=stage/PREFIX.lstrip("/")
        (prefix/"bin").mkdir(parents=True)
        target=prefix/"bin"/name
        shutil.copy2(binary,target);target.chmod(0o755)
        doc=prefix/"share/doc"/name;doc.mkdir(parents=True)
        shutil.copy2(license_file,doc/"LICENSE")
        if extra:
            for rel,src,mode in extra:
                dst=prefix/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst);dst.chmod(mode)
        fields=[("Package",name),("Version",version),("Architecture","aarch64")]
        if depends: fields.append(("Depends",depends))
        fields += [("Maintainer","OceanStudio <maintainer@ocean.studio>"),("Section","utils"),("Priority","optional"),("Description",description)]
        control(stage,fields)
        deb=out/f"{name}_{version}_aarch64.deb";build_deb(stage,deb);return deb

def busybox(item,ndk,work,pool,readelf):
    arc=work/"busybox.tar.bz2";sumfile=work/"busybox.sha256"
    fetch(item["source"],arc);fetch(item["checksum"],sumfile)
    expected=sumfile.read_text(errors="replace").split()[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}",expected) or sha256(arc)!=expected:
        raise SystemExit("BusyBox upstream SHA-256 verification failed")
    srcroot=work/"busybox-src";srcroot.mkdir();src=safe_extract(arc,srcroot)
    clang=ndk/"toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android28-clang"
    strip=ndk/"toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip"
    env=dict(os.environ,CC=str(clang),HOSTCC=require("cc"),STRIP=str(strip),KCONFIG_NOTIMESTAMP="1",LC_ALL="C")
    run(["make","android_ndk_defconfig"],cwd=src,env=env)
    cfg=src/".config";text=cfg.read_text()
    text=re.sub(r'^CONFIG_CROSS_COMPILER_PREFIX=.*$', 'CONFIG_CROSS_COMPILER_PREFIX=""', text, flags=re.M)
    text=re.sub(r'^CONFIG_SYSROOT=.*$', 'CONFIG_SYSROOT=""', text, flags=re.M)
    (src / "include/ocean_compat.h").write_text("#ifndef __ASSEMBLER__\n#include <string.h>\nstatic inline void explicit_bzero(void *s, size_t n) { memset(s, 0, n); }\n#endif\n")
    text=re.sub(r'^CONFIG_EXTRA_CFLAGS=.*$', 'CONFIG_EXTRA_CFLAGS="-include include/ocean_compat.h"', text, flags=re.M)
    text=re.sub(r'^CONFIG_EXTRA_LDFLAGS=.*$', 'CONFIG_EXTRA_LDFLAGS=""', text, flags=re.M)
    text=re.sub(r'^CONFIG_EXTRA_LDLIBS=.*$', 'CONFIG_EXTRA_LDLIBS=""', text, flags=re.M)
    text=re.sub(r'^CONFIG_STATIC=y$', '# CONFIG_STATIC is not set', text, flags=re.M)
    text=re.sub(r'^# CONFIG_PIE is not set$', 'CONFIG_PIE=y', text, flags=re.M)
    text=re.sub(r'^# CONFIG_USE_BB_CRYPT is not set$', 'CONFIG_USE_BB_CRYPT=y', text, flags=re.M)
    text=re.sub(r'^# CONFIG_USE_BB_CRYPT_SHA is not set$', 'CONFIG_USE_BB_CRYPT_SHA=y', text, flags=re.M)
    android_off=[
      "TC","HOSTID","CHVT","DEALLOCVT","DUMPKMAP","FGCONSOLE","KBD_MODE",
      "LOADFONT","LOADKMAP","OPENVT","RESET","RESIZE","SETCONSOLE",
      "SETFONT","SETKEYCODES","SHOWKEY","SETLOGCONS",
      "HALT","REBOOT","POWEROFF","INIT","LINUXRC","BOOTCHARTD",
      "FEATURE_UTMP","FEATURE_WTMP","ADJTIMEX",
      "PASSWD","FEATURE_PASSWD_WEAK_CHECK",
      "CRYPTPW","MKPASSWD","CHPASSWD","SULOGIN","VLOCK","SU","LOGIN","GETTY"
    ]
    for symbol in android_off:
        text=re.sub(rf"^CONFIG_{symbol}=y$",f"# CONFIG_{symbol} is not set",text,flags=re.M)
    cfg.write_text(text)
    run(["make","oldconfig",f"CC={clang}","HOSTCC=cc",f"STRIP={strip}"],cwd=src,env=env)
    run(["make","-j2",f"CC={clang}","HOSTCC=cc",f"STRIP={strip}"],cwd=src,env=env)
    binary=src/"busybox";validation=validate_binary(binary,readelf)
    deb=package_binary("busybox",item["version"],binary,src/"LICENSE",pool,
        "BusyBox multicall utility compiled from official upstream source for Ocean Android/AArch64")
    return {"package":"busybox","artifact":deb.name,"sha256":sha256(deb),"sourceSha256":expected,
      "patches":["base config switched to upstream android_ndk_defconfig","strip obsolete upstream NDK path/toolchain flags","disable Android-incompatible console/init/power/adjtimex/login crypt features"],"validation":validation}

def sbase(item,ndk,work,pool,readelf):
    src=work/"sbase";clone_pinned(item["source"],item["commit"],src)
    makefile=src/"Makefile";txt=makefile.read_text()
    txt=txt.replace("$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ make/*.c","$(HOSTCC) $(CPPFLAGS) $(CFLAGS) -o $@ make/*.c")
    makefile.write_text(txt)
    clang=ndk/"toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android28-clang"
    ar=ndk/"toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-ar";ran=ndk/"toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-ranlib"
    run(["make","-j2","sbase-box",f"CC={clang}","HOSTCC=cc",f"AR={ar}",f"RANLIB={ran}",
         f"PREFIX={PREFIX}","CFLAGS=-Os -fPIE","LDFLAGS=-pie -Wl,-z,max-page-size=16384"],cwd=src)
    binary=src/"sbase-box";validation=validate_binary(binary,readelf)
    deb=package_binary("sbase",item["version"],binary,src/"LICENSE",pool,
        "suckless sbase multicall utilities compiled for Ocean Android/AArch64")
    return {"package":"sbase","artifact":deb.name,"sha256":sha256(deb),"commit":item["commit"],"patches":["HOSTCC for build-time scripts/make"],"validation":validation}

def ubase(item,ndk,work,pool,readelf):
    src=work/"ubase";clone_pinned(item["source"],item["commit"],src)
    clang=ndk/"toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android28-clang"
    ar=ndk/"toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-ar";ran=ndk/"toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-ranlib"
    run(["make","-j2","ubase-box",f"CC={clang}",f"AR={ar}",f"RANLIB={ran}",
         f"PREFIX={PREFIX}","CFLAGS=-Os -fPIE -D_GNU_SOURCE","LDFLAGS=-pie -Wl,-z,max-page-size=16384"],cwd=src)
    binary=src/"ubase-box";validation=validate_binary(binary,readelf)
    deb=package_binary("ubase",item["version"],binary,src/"LICENSE",pool,
        "suckless ubase Linux utility multicall binary compiled for Ocean Android/AArch64")
    return {"package":"ubase","artifact":deb.name,"sha256":sha256(deb),"commit":item["commit"],"patches":[],"validation":validation}

def sinit(item,ndk,work,pool,readelf):
    src=work/"sinit";clone_pinned(item["source"],item["commit"],src)
    config=(src/"config.def.h").read_text()
    config=config.replace('"/bin/rc.init"',f'"{PREFIX}/etc/sinit/rc.init"').replace('"/bin/rc.shutdown"',f'"{PREFIX}/etc/sinit/rc.shutdown"')
    (src/"config.h").write_text(config)
    clang=ndk/"toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android28-clang"
    binary=work/"sinit-bin"
    run([clang,"-Os","-fPIE","-pie","-Wl,-z,max-page-size=16384","-I",src,src/"sinit.c","-o",binary])
    validation=validate_binary(binary,readelf)
    rcinit=work/"rc.init";rcinit.write_text("#!/system/bin/sh\nexit 0\n");rcinit.chmod(0o755)
    rcshutdown=work/"rc.shutdown";rcshutdown.write_text("#!/system/bin/sh\nexit 0\n");rcshutdown.chmod(0o755)
    deb=package_binary("sinit",item["version"],binary,src/"LICENSE",pool,
        "suckless sinit compiled for Ocean; intended for a suitable PID-1 container/rootfs environment",
        extra=[("etc/sinit/rc.init",rcinit,0o755),("etc/sinit/rc.shutdown",rcshutdown,0o755)])
    return {"package":"sinit","artifact":deb.name,"sha256":sha256(deb),"commit":item["commit"],
      "patches":["rc paths relocated to Ocean private prefix"],"validation":validation}

def buildroot(item,work,pool):
    src=work/"buildroot";commit=clone_tag(item["source"],item["tag"],src)
    run(["make","help"],cwd=src,capture=True)
    with tempfile.TemporaryDirectory(prefix="buildroot-pkg-") as td:
        stage=Path(td);prefix=stage/PREFIX.lstrip("/")
        dst=prefix/"share/buildroot"/item["tag"];dst.parent.mkdir(parents=True);shutil.copytree(src,dst,ignore=shutil.ignore_patterns(".git"))
        bindir=prefix/"bin";bindir.mkdir(parents=True)
        launcher=bindir/"buildroot-ocean"
        launcher.write_text("#!/system/bin/sh\nset -eu\nROOT=\""+PREFIX+"/share/buildroot/"+item["tag"]+"\"\nOUT=\"$HOME/.ocean/buildroot-output\"\nif [ -n \"$BUILDROOT_OUTPUT\" ]; then OUT=\"$BUILDROOT_OUTPUT\"; fi\nmkdir -p \"$OUT\"\nexec make -C \"$ROOT\" O=\"$OUT\" \"$@\"\n")
        launcher.chmod(0o755)
        doc=prefix/"share/doc/buildroot";doc.mkdir(parents=True)
        if (src/"COPYING").is_file(): shutil.copy2(src/"COPYING",doc/"COPYING")
        control(stage,[("Package","buildroot"),("Version",item["version"]),("Architecture","all"),
          ("Depends","bash, make, python, git, tar, gzip, bzip2, xz-utils, patch, sed, gawk, grep, findutils, diffutils, coreutils"),
          ("Maintainer","OceanStudio <maintainer@ocean.studio>"),("Section","devel"),("Priority","optional"),
          ("Description","Official Buildroot "+item["tag"]+" source framework with Ocean private workspace launcher")])
        deb=pool/f"buildroot_{item['version']}_all.deb";build_deb(stage,deb)
    return {"package":"buildroot","artifact":deb.name,"sha256":sha256(deb),"tag":item["tag"],"commit":commit,"validation":{"makeHelp":"passed"}}

def validate_debs(pool,readelf):
    records=[]
    for deb in sorted(pool.glob("*.deb")):
        pkg=run(["dpkg-deb","-f",deb,"Package"],capture=True).stdout.strip()
        arch=run(["dpkg-deb","-f",deb,"Architecture"],capture=True).stdout.strip()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);run(["dpkg-deb","-x",deb,root])
            for p in root.rglob("*"):
                if p.is_symlink() or not p.is_file(): continue
                data=p.read_bytes()
                if any(x in data for x in FORBIDDEN): raise SystemExit(f"Termux identity in {deb.name}:{p.relative_to(root)}")
                if data.startswith(b"\x7fELF"): validate_binary(p,readelf)
        records.append({"package":pkg,"architecture":arch,"artifact":deb.name,"sha256":sha256(deb),"bytes":deb.stat().st_size})
    return records

def write_index(out):
    d=out/"dists/stable/main/binary-aarch64";d.mkdir(parents=True,exist_ok=True)
    result=run(["dpkg-scanpackages","--multiversion","pool/main","/dev/null"],cwd=out,capture=True)
    data=result.stdout.encode();(d/"Packages").write_bytes(data);(d/"Packages.gz").write_bytes(gzip.compress(data,9,mtime=0))

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--manifest",type=Path,default=ROOT/"sources/core-suite/manifest.json")
    ap.add_argument("--ndk",type=Path,default=os.environ.get("ANDROID_NDK_HOME"));ap.add_argument("--output",type=Path,default=ROOT/"staging/core-suite")
    a=ap.parse_args()
    if a.ndk is None: ap.error("--ndk or ANDROID_NDK_HOME is required")
    for cmd in ("git","make","cc","dpkg-deb","dpkg-scanpackages"):require(cmd)
    m=json.loads(a.manifest.read_text());ndk=Path(a.ndk).resolve()
    if m["target"]!="aarch64-linux-android28" or m["prefix"]!=PREFIX: raise SystemExit("manifest target mismatch")
    if f"Pkg.Revision = {m['ndkRevision']}" not in (ndk/"source.properties").read_text(): raise SystemExit("NDK revision mismatch")
    out=a.output.resolve();shutil.rmtree(out,ignore_errors=True);pool=out/"pool/main";pool.mkdir(parents=True)
    readelf=ndk/"toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf"
    results=[]
    with tempfile.TemporaryDirectory(prefix="ocean-core-suite-") as td:
        work=Path(td);by={x["name"]:x for x in m["packages"]}
        results.append(busybox(by["busybox"],ndk,work,pool,readelf))
        results.append(sbase(by["sbase"],ndk,work,pool,readelf))
        results.append(ubase(by["ubase"],ndk,work,pool,readelf))
        results.append(sinit(by["sinit"],ndk,work,pool,readelf))
        results.append(buildroot(by["buildroot"],work,pool))
    records=validate_debs(pool,readelf);write_index(out)
    if len(records)!=5: raise SystemExit("expected exactly 5 core-suite packages")
    report={"schemaVersion":1,"sourcePolicy":"official upstream source only; no Termux packages or binary caches",
      "target":m["target"],"ndkRevision":m["ndkRevision"],"packageCount":len(records),"builds":results,"packages":records,
      "promotion":"staging-only until signed repository promotion"}
    (out/"provenance.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"packageCount":len(records),"output":str(out)},indent=2))
if __name__=="__main__": raise SystemExit(main())
