#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, importlib.util, json, os, shutil, subprocess, tempfile
from pathlib import Path

PREFIX="/data/data/studio.ocean.app/files/usr"

def load_module(path:Path,name:str):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(mod); return mod

def run(cmd):
    r=subprocess.run(cmd,text=True,capture_output=True)
    if r.returncode: raise SystemExit(f"command failed: {' '.join(cmd)}\n{r.stdout}\n{r.stderr}")
    return r

def hashes(path):
    d=Path(path).read_bytes()
    return {"size":len(d),"md5":hashlib.md5(d).hexdigest(),"sha1":hashlib.sha1(d).hexdigest(),"sha256":hashlib.sha256(d).hexdigest()}

def normalize(root):
    for p in sorted(Path(root).rglob("*"),reverse=True):
        try:
            p.chmod(0o755 if p.is_dir() or "/bin/" in str(p) else 0o644)
            os.utime(p,(0,0),follow_symlinks=False)
        except FileNotFoundError: pass
    Path(root).chmod(0o755); os.utime(root,(0,0))

def build_one(name,desc,runtime_text,runtime_basename,version,section,out):
    deb=out/f"{name}_{version}_aarch64.deb"
    with tempfile.TemporaryDirectory(prefix=f"ocean-{name}-") as td:
        root=Path(td); (root/"DEBIAN").mkdir()
        runtime=root/PREFIX.lstrip("/")/"lib/ocean-functional-shards"/runtime_basename
        runtime.parent.mkdir(parents=True); runtime.write_text(runtime_text,encoding="utf-8"); runtime.chmod(0o644)
        wrapper=root/PREFIX.lstrip("/")/"bin"/name
        wrapper.parent.mkdir(parents=True,exist_ok=True)
        wrapper.write_text(f"#!{PREFIX}/bin/bash\nexec {PREFIX}/bin/python {PREFIX}/lib/ocean-functional-shards/{runtime_basename} {name} \"$@\"\n",encoding="utf-8")
        wrapper.chmod(0o755)
        doc=root/PREFIX.lstrip("/")/"share/doc"/name/"README.md"; doc.parent.mkdir(parents=True,exist_ok=True)
        doc.write_text(f"# {name}\n\n{desc}\n\nFunctional OceanStudio repair package.\nVersion: {version}\nRuntime: Python standard library / Linux interfaces.\n",encoding="utf-8")
        (root/"DEBIAN/control").write_text(
            f"Package: {name}\nVersion: {version}\nArchitecture: aarch64\nMaintainer: OceanStudio Packaging Team <maintainer@ocean.studio>\nSection: {section}\nPriority: optional\nDepends: python\nDescription: {desc}\n Functional OceanStudio implementation replacing the earlier generic passthrough placeholder.\n",
            encoding="utf-8")
        normalize(root)
        run(["dpkg-deb","--root-owner-group","-Zxz","--build",str(root),str(deb)])
    return deb

def stanza(name,desc,version,section,deb):
    h=hashes(deb)
    return f"""Package: {name}
Version: {version}
Architecture: aarch64
Maintainer: OceanStudio Packaging Team <maintainer@ocean.studio>
Depends: python
Filename: pool/main/{deb.name}
Size: {h['size']}
MD5sum: {h['md5']}
SHA1: {h['sha1']}
SHA256: {h['sha256']}
Section: {section}
Priority: optional
Description: {desc}
 Functional OceanStudio implementation replacing the earlier generic passthrough placeholder."""

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--runtime",required=True); ap.add_argument("--batch",required=True); ap.add_argument("--batch-symbol",default="BATCH4_SHARDS")
    ap.add_argument("--shard",required=True); ap.add_argument("--output",required=True); ap.add_argument("--live-packages",required=True)
    ap.add_argument("--version",default="1.0.0-2"); ap.add_argument("--section",default="utils")
    ns=ap.parse_args()

    runtime_path=Path(ns.runtime); batch_path=Path(ns.batch); output=Path(ns.output); live=Path(ns.live_packages)
    runtime=load_module(runtime_path,"functional_runtime"); batchmod=load_module(batch_path,"batch")
    shards=getattr(batchmod,ns.batch_symbol)
    if ns.shard not in shards: raise SystemExit(f"unknown shard: {ns.shard}")
    packages=shards[ns.shard]["packages"]
    section=shards[ns.shard].get("section",ns.section)
    names=[x[0] for x in packages]
    if len(names)!=50 or len(set(names))!=50: raise SystemExit(f"{ns.shard}: expected 50 unique names, got {len(names)}/{len(set(names))}")
    if hasattr(runtime,"COMMANDS"):
        if set(names)!=set(runtime.COMMANDS):
            raise SystemExit(f"runtime mismatch missing={sorted(set(names)-set(runtime.COMMANDS))} extra={sorted(set(runtime.COMMANDS)-set(names))}")
    elif hasattr(runtime,"supports"):
        unsupported=[n for n in names if not runtime.supports(n)]
        if unsupported: raise SystemExit(f"runtime does not support: {unsupported}")
    else:
        raise SystemExit("runtime must expose COMMANDS or supports(name)")

    live_text=live.read_text(encoding="utf-8",errors="replace")
    missing=[n for n in names if f"Package: {n}\n" not in live_text]
    if missing: raise SystemExit(f"live placeholders missing: {missing}")

    shutil.rmtree(output,ignore_errors=True); pool=output/"pool/main"; pool.mkdir(parents=True)
    runtime_text=runtime_path.read_text(encoding="utf-8"); runtime_basename=runtime_path.name
    stanzas=[]; prov=[]
    for name,old_version,desc in packages:
        deb=build_one(name,desc,runtime_text,runtime_basename,ns.version,section,pool)
        run(["dpkg-deb","--info",str(deb)])
        data=deb.read_bytes()
        for forbidden in (b"/data/data/com.termux",b"/data/user/0/com.termux",b"packages.termux.dev",b"TERMUX_PREFIX"):
            if forbidden in data: raise SystemExit(f"forbidden Termux reference in {name}")
        h=hashes(deb)
        stanzas.append(stanza(name,desc,ns.version,section,deb))
        prov.append({"package":name,"replacesVersion":old_version,"version":ns.version,"artifact":deb.name,"sha256":h["sha256"],"size":h["size"],"implementation":str(runtime_path),"status":"functional-repair"})
    (output/"Packages.repaired").write_text("\n\n".join(stanzas)+"\n",encoding="utf-8")
    (output/"provenance.json").write_text(json.dumps({
        "schemaVersion":2,"shard":ns.shard,"category":shards[ns.shard].get("category"),"repair":"placeholder-to-functional",
        "target":"aarch64-linux-android28","prefix":PREFIX,"packageCount":50,"uniquePackageCount":50,"version":ns.version,"packages":prov
    },indent=2)+"\n",encoding="utf-8")
    if len(list(pool.glob("*.deb")))!=50: raise SystemExit("deb count mismatch")
    if sum(1 for x in (output/"Packages.repaired").read_text().splitlines() if x.startswith("Package: "))!=50: raise SystemExit("index count mismatch")
    print(f"SUCCESS: rebuilt 50 packages in {ns.shard} as functional implementations")

if __name__=="__main__": main()
