#!/usr/bin/env python3
"""Build isolated Ocean glibc packages from GNU's signed upstream release."""
from __future__ import annotations
import argparse, gzip, hashlib, json, os, pathlib, re, shutil, subprocess, tarfile, tempfile, urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST=ROOT/"sources/glibc-2.44/manifest.json"
FORBIDDEN=(b"/data/data/com.termux",b"/data/user/0/com.termux",b"TERMUX_PREFIX",b"packages.termux.dev")

def run(cmd,*,cwd=None,env=None,capture=False):
    print("+"," ".join(map(str,cmd)),flush=True)
    return subprocess.run(list(map(str,cmd)),cwd=cwd,env=env,check=True,text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.STDOUT if capture else None)

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def download(url,dst):
    print("download",url,flush=True)
    req=urllib.request.Request(url,headers={"User-Agent":"OceanStudio-package-builder/1"})
    with urllib.request.urlopen(req,timeout=120) as src,open(dst,"wb") as out:
        shutil.copyfileobj(src,out)

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

def copytree_if(src,dst):
    if src.exists(): shutil.copytree(src,dst,symlinks=True,dirs_exist_ok=True)

def copy_runtime_libs(src_lib,dst_lib):
    dst_lib.mkdir(parents=True,exist_ok=True)
    for p in src_lib.iterdir():
        name=p.name
        runtime=(p.is_dir() and name in ("gconv","audit")) or ".so." in name or name.startswith("ld-") or name=="ld-linux-aarch64.so.1"
        if runtime:
            target=dst_lib/name
            if p.is_symlink(): target.symlink_to(os.readlink(p))
            elif p.is_dir(): shutil.copytree(p,target,symlinks=True,dirs_exist_ok=True)
            else: shutil.copy2(p,target)
    loader=dst_lib/"ld-linux-aarch64.so.1"
    if not loader.exists():
        candidates=list(dst_lib.glob("ld-*.so"))+list(dst_lib.glob("ld-linux*.so*"))
        if not candidates: raise SystemExit("glibc runtime loader not found")
        if candidates[0].name!="ld-linux-aarch64.so.1": loader.symlink_to(candidates[0].name)

def write_runner(stage,m):
    ocean=stage/m["oceanPrefix"].lstrip("/")/"bin"
    ocean.mkdir(parents=True,exist_ok=True)
    root=m["glibcPrefix"]
    runner=ocean/"ocean-glibc-run"
    runner.write_text(
        "#!/system/bin/sh\n"
        f"ROOT='{root}'\n"
        'LOADER="$ROOT/lib/ld-linux-aarch64.so.1"\n'
        'if [ ! -x "$LOADER" ]; then echo "Ocean glibc loader missing: $LOADER" >&2; exit 127; fi\n'
        'if [ "$#" -lt 1 ]; then echo "usage: ocean-glibc-run PROGRAM [ARGS...]" >&2; exit 2; fi\n'
        'export GCONV_PATH="$ROOT/lib/gconv"\n'
        'export LOCPATH="$ROOT/lib/locale"\n'
        'exec "$LOADER" --library-path "$ROOT/lib" "$@"\n'
    ); runner.chmod(0o755)
    info=ocean/"ocean-glibc-info"
    info.write_text(
        "#!/system/bin/sh\n"
        f"ROOT='{root}'\n"
        'echo "Ocean glibc root: $ROOT"\n'
        '"$ROOT/lib/ld-linux-aarch64.so.1" --version | head -n 1\n'
    ); info.chmod(0o755)

def write_utils_wrappers(stage,m,installed):
    ocean=stage/m["oceanPrefix"].lstrip("/")/"bin";ocean.mkdir(parents=True,exist_ok=True)
    root=m["glibcPrefix"]
    for name in ("iconv","getconf","getent","locale","localedef","sprof","pldd"):
        if (installed/"bin"/name).exists():
            w=ocean/f"glibc-{name}"
            w.write_text("#!/system/bin/sh\n"+f"exec '{m['oceanPrefix']}/bin/ocean-glibc-run' '{root}/bin/{name}' \"$@\"\n")
            w.chmod(0o755)
    if (installed/"bin"/"ldd").exists():
        w=ocean/"glibc-ldd"
        w.write_text("#!/system/bin/sh\n"+f"exec '{m['oceanPrefix']}/bin/bash' '{root}/bin/ldd' \"$@\"\n");w.chmod(0o755)

def verify_tree(root):
    for p in root.rglob("*"):
        if p.is_symlink() or not p.is_file(): continue
        data=p.read_bytes()
        if any(x in data for x in FORBIDDEN): raise SystemExit(f"forbidden Termux identity in {p}")

def package_all(m,install_root,source,output,source_meta):
    pool=output/"pool/main";pool.mkdir(parents=True,exist_ok=True)
    prefix=install_root/m["glibcPrefix"].lstrip("/")
    version=m["version"]; produced=[]

    with tempfile.TemporaryDirectory() as t:
        stage=pathlib.Path(t);dst=stage/m["glibcPrefix"].lstrip("/")
        copy_runtime_libs(prefix/"lib",dst/"lib")
        copytree_if(prefix/"etc",dst/"etc")
        doc=dst/"share/doc/ocean-glibc";doc.mkdir(parents=True,exist_ok=True);shutil.copy2(source/"COPYING",doc/"COPYING")
        (doc/"ocean-build.json").write_text(json.dumps(source_meta,indent=2)+"\n")
        control(stage,[("Package","ocean-glibc"),("Version",version),("Architecture","aarch64"),
            ("Maintainer","OceanStudio <maintainer@ocean.studio>"),("Homepage","https://www.gnu.org/software/libc/"),
            ("Section","libs"),("Priority","optional"),("Description","Isolated GNU C Library runtime for OceanStudio; does not replace Android Bionic")])
        out=pool/f"ocean-glibc_{version}_aarch64.deb";build_deb(stage,out);produced.append(out)

    with tempfile.TemporaryDirectory() as t:
        stage=pathlib.Path(t);write_runner(stage,m)
        control(stage,[("Package","ocean-glibc-runner"),("Version",version),("Architecture","all"),
            ("Depends",f"ocean-glibc (= {version})"),("Maintainer","OceanStudio <maintainer@ocean.studio>"),
            ("Section","utils"),("Priority","optional"),("Description","Explicit loader runner for isolated Ocean glibc binaries")])
        out=pool/f"ocean-glibc-runner_{version}_all.deb";build_deb(stage,out);produced.append(out)

    with tempfile.TemporaryDirectory() as t:
        stage=pathlib.Path(t);dst=stage/m["glibcPrefix"].lstrip("/")
        copytree_if(prefix/"include",dst/"include")
        libdst=dst/"lib";libdst.mkdir(parents=True,exist_ok=True)
        for p in (prefix/"lib").iterdir():
            if p.name.endswith(".a") or p.name.endswith(".o") or (p.name.endswith(".so") and not p.name.startswith("ld-")):
                target=libdst/p.name
                if p.is_symlink(): target.symlink_to(os.readlink(p))
                else: shutil.copy2(p,target)
        control(stage,[("Package","ocean-glibc-devel"),("Version",version),("Architecture","aarch64"),
            ("Depends",f"ocean-glibc (= {version})"),("Maintainer","OceanStudio <maintainer@ocean.studio>"),
            ("Section","devel"),("Priority","optional"),("Description","Headers and development files for the isolated Ocean glibc runtime")])
        out=pool/f"ocean-glibc-devel_{version}_aarch64.deb";build_deb(stage,out);produced.append(out)

    with tempfile.TemporaryDirectory() as t:
        stage=pathlib.Path(t);dst=stage/m["glibcPrefix"].lstrip("/")
        copytree_if(prefix/"bin",dst/"bin");copytree_if(prefix/"sbin",dst/"sbin")
        write_utils_wrappers(stage,m,prefix)
        control(stage,[("Package","ocean-glibc-utils"),("Version",version),("Architecture","aarch64"),
            ("Depends",f"ocean-glibc (= {version}), ocean-glibc-runner (= {version})"),
            ("Maintainer","OceanStudio <maintainer@ocean.studio>"),("Section","utils"),("Priority","optional"),
            ("Description","Namespaced GNU libc utilities for OceanStudio glibc compatibility")])
        out=pool/f"ocean-glibc-utils_{version}_aarch64.deb";build_deb(stage,out);produced.append(out)

    with tempfile.TemporaryDirectory() as t:
        stage=pathlib.Path(t);dst=stage/m["glibcPrefix"].lstrip("/")
        copytree_if(prefix/"share/i18n",dst/"share/i18n");copytree_if(prefix/"share/locale",dst/"share/locale")
        control(stage,[("Package","ocean-glibc-locale-data"),("Version",version),("Architecture","all"),
            ("Depends",f"ocean-glibc (= {version})"),("Maintainer","OceanStudio <maintainer@ocean.studio>"),
            ("Section","localization"),("Priority","optional"),("Description","Locale source and translation data for isolated Ocean glibc")])
        out=pool/f"ocean-glibc-locale-data_{version}_all.deb";build_deb(stage,out);produced.append(out)
    return produced

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--manifest",type=pathlib.Path,default=DEFAULT_MANIFEST);ap.add_argument("--output",type=pathlib.Path,default=ROOT/"staging/glibc-2.44")
    args=ap.parse_args();m=json.loads(args.manifest.read_text());out=args.output.resolve()
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True)
    for cmd in ("git","make","aarch64-linux-gnu-gcc","aarch64-linux-gnu-readelf","dpkg-deb","dpkg-scanpackages","qemu-aarch64"): shutil.which(cmd) or (_ for _ in ()).throw(SystemExit(f"missing tool: {cmd}"))
    with tempfile.TemporaryDirectory(prefix="ocean-glibc-") as temp:
        w=pathlib.Path(temp);source=w/"source"
        run(["git","init","-q",source])
        run(["git","-C",source,"remote","add","origin",m["sourceUrl"]])
        run(["git","-C",source,"fetch","--depth=1","origin",m["commit"]])
        run(["git","-C",source,"checkout","--detach","-q","FETCH_HEAD"])
        head=run(["git","-C",source,"rev-parse","HEAD"],capture=True).stdout.strip()
        if head!=m["commit"]: raise SystemExit(f"glibc source commit mismatch: {head}")
        tree=run(["git","-C",source,"rev-parse","HEAD^{tree}"],capture=True).stdout.strip()
        fix="0b4e41fc51e6aba6216a908961b49b0622b47fa0"
        if run(["git","-C",source,"merge-base","--is-ancestor",fix,"HEAD"],capture=True).returncode!=0:
            raise SystemExit("security-fixed glibc commit does not contain CVE-2026-18374 fix")
        build=w/"build";build.mkdir();dest=w/"dest";dest.mkdir()
        prefix=m["glibcPrefix"]
        env=dict(os.environ)
        env.update({"CC":"aarch64-linux-gnu-gcc","CXX":"aarch64-linux-gnu-g++","AR":"aarch64-linux-gnu-ar","RANLIB":"aarch64-linux-gnu-ranlib",
                    "libc_cv_slibdir":prefix+"/lib","libc_cv_rtlddir":prefix+"/lib","SOURCE_DATE_EPOCH":"0","LC_ALL":"C"})
        run([source/"configure","--build=x86_64-linux-gnu","--host=aarch64-linux-gnu",f"--prefix={prefix}",f"--sysconfdir={prefix}/etc",
             f"--localstatedir={prefix}/var",f"--libdir={prefix}/lib",f"--includedir={prefix}/include",
             "--with-headers=/usr/aarch64-linux-gnu/include",f"--enable-kernel={m['enableKernel']}","--disable-werror","--disable-nscd"],cwd=build,env=env)
        run(["make",f"-j{max(2,os.cpu_count() or 2)}"],cwd=build,env=env)
        run(["make","install",f"DESTDIR={dest}"],cwd=build,env=env)
        installed=dest/prefix.lstrip("/")
        loader=installed/"lib/ld-linux-aarch64.so.1"
        if not loader.exists(): raise SystemExit("installed glibc loader missing")
        header=run(["aarch64-linux-gnu-readelf","-h",loader],capture=True).stdout
        if "AArch64" not in header: raise SystemExit("glibc loader is not AArch64")
        hello=w/"hello.c";hello.write_text('#include <stdio.h>\nint main(void){puts("OCEAN_GLIBC_OK");return 0;}\n')
        hello_bin=w/"hello";run(["aarch64-linux-gnu-gcc",hello,"-o",hello_bin])
        test=run(["qemu-aarch64",loader,"--library-path",installed/"lib",hello_bin],capture=True).stdout
        if "OCEAN_GLIBC_OK" not in test: raise SystemExit("qemu glibc smoke test failed")
        meta={"schemaVersion":1,"sourceUrl":m["sourceUrl"],"sourceCommit":head,"sourceTree":tree,
              "releaseBranch":m["releaseBranch"],"securityFixes":m["securityFixes"],"version":m["version"],
              "glibcPrefix":prefix,"oceanPrefix":m["oceanPrefix"],"hostTriplet":m["hostTriplet"],
              "enableKernel":m["enableKernel"],"sourceVerification":"exact upstream git commit + CVE fix ancestry PASS",
              "qemuSmokeTest":"OCEAN_GLIBC_OK","sourcePolicy":"official Sourceware glibc stable branch; exact security-fixed commit; no Termux package or binary input"}
        produced=package_all(m,dest,source,out,meta)
        verify_tree(out)
        idx=out/"dists/stable/main/binary-aarch64";idx.mkdir(parents=True)
        result=run(["dpkg-scanpackages","--multiversion","pool/main","/dev/null"],cwd=out,capture=True).stdout.encode()
        (idx/"Packages").write_bytes(result);(idx/"Packages.gz").write_bytes(gzip.compress(result,9,mtime=0))
        records=[{"artifact":p.name,"sha256":sha256(p),"bytes":p.stat().st_size,"package":run(["dpkg-deb","-f",p,"Package"],capture=True).stdout.strip()} for p in produced]
        meta.update({"packageCount":len(records),"packages":records,"indexSha256":sha256(idx/"Packages"),"indexGzipSha256":sha256(idx/"Packages.gz"),"promotion":"staging-only"})
        (out/"provenance.json").write_text(json.dumps(meta,indent=2)+"\n")
        print(json.dumps({"packageCount":len(records),"output":str(out)},indent=2))
    return 0

if __name__=="__main__": raise SystemExit(main())
