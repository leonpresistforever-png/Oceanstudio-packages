#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, importlib.util, json, shutil, subprocess, tempfile
from pathlib import Path

PREFIX="/data/data/studio.ocean.app/files/usr"
VERSION="1.0.0-1"

def load_runtime(path):
    spec=importlib.util.spec_from_file_location("ocean_device_suite",path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def control(pkg,deps,description):
    return f"""Package: {pkg}
Version: {VERSION}
Architecture: all
Maintainer: OceanStudio <packages@ocean.studio>
Section: utils
Priority: optional
Depends: {deps}
Description: {description}
 OceanStudio non-root device/render command. Android remains the authority for
 user permissions and protected/secure surfaces.
"""

def launcher(pkg):
    return f"""#!/system/bin/sh
if [ -z "$PREFIX" ]; then PREFIX="{PREFIX}"; fi
exec "$PREFIX/bin/python" "$PREFIX/lib/ocean-device/ocean_device.py" {pkg!r} "$@"
"""

def desc(pkg):
    return "OceanStudio "+pkg.removeprefix("ocean-").replace("-"," ")+" command"

def deps(pkg):
    if pkg=="ocean-api": return "python"
    d=["ocean-api (= 1.0.0-1)"]
    if pkg in {"ocean-image-convert","ocean-image-thumbnail"}:d.append("imagemagick")
    if pkg=="ocean-media-info":d.append("ffmpeg")
    if pkg in {"ocean-x11-start","ocean-x11-stop","ocean-x11-runtime","ocean-x11-run","ocean-x11-shell","ocean-x11-app"}:d+=["proot","proot-distro"]
    return ", ".join(d)

def build_one(pkg,runtime,out):
    with tempfile.TemporaryDirectory(prefix="ocean-device-deb-") as td:
        root=Path(td)/pkg
        debian=root/"DEBIAN";bin_dir=root/PREFIX.strip("/")/"bin";lib_dir=root/PREFIX.strip("/")/"lib/ocean-device"
        debian.mkdir(parents=True);bin_dir.mkdir(parents=True);lib_dir.mkdir(parents=True)
        (debian/"control").write_text(control(pkg,deps(pkg),desc(pkg)))
        launch=bin_dir/pkg;launch.write_text(launcher(pkg));launch.chmod(0o755)
        if pkg=="ocean-api":
            shutil.copy2(runtime,lib_dir/"ocean_device.py");(lib_dir/"ocean_device.py").chmod(0o755)
        artifact=out/f"{pkg}_{VERSION}_all.deb"
        subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(artifact)],check=True,stdout=subprocess.DEVNULL)
        return artifact

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--runtime",required=True);ap.add_argument("--output",required=True)
    ap.add_argument("--live-packages",default="")
    a=ap.parse_args()
    runtime=Path(a.runtime);out=Path(a.output);pool=out/"pool/main"
    if out.exists():shutil.rmtree(out)
    pool.mkdir(parents=True)
    m=load_runtime(runtime);names=list(m.COMMANDS)
    if len(names)!=200 or len(set(names))!=200:raise SystemExit("suite must contain exactly 200 unique packages")
    live=set()
    lp=Path(a.live_packages) if a.live_packages else None
    if lp and lp.exists():
        for line in lp.read_text(errors="replace").splitlines():
            if line.startswith("Package: "):live.add(line.split(": ",1)[1].strip())
    collisions=sorted(set(names)&live)
    if collisions:raise SystemExit("live package name collision: "+", ".join(collisions))
    rows=[]
    for pkg in names:
        art=build_one(pkg,runtime,pool)
        raw=art.read_bytes();rows.append({"package":pkg,"artifact":art.name,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"depends":deps(pkg)})
    paragraphs=[]
    for r in rows:
        fields=subprocess.check_output(["dpkg-deb","-f",str(pool/r["artifact"])],text=True).strip()
        paragraphs.append(fields+"\nFilename: staging/ocean-device-suite/pool/main/"+r["artifact"]+"\nSize: "+str(r["bytes"])+"\nSHA256: "+r["sha256"]+"\n")
    (out/"Packages.repaired").write_text("\n".join(paragraphs))
    provenance={"schemaVersion":1,"suite":"ocean-device-suite","version":VERSION,"sourceType":"Ocean-native original source","prefix":PREFIX,"packageCount":len(rows),"uniquePackageCount":len({r["package"] for r in rows}),"termuxRuntimeDependency":False,"permissionModel":"Android user-granted permissions only","packages":rows,"promotion":"staging-only until repository signing identity is available"}
    (out/"provenance.json").write_text(json.dumps(provenance,indent=2)+"\n")
    print(json.dumps({"built":len(rows),"unique":len(set(names)),"output":str(out)},indent=2))
if __name__=="__main__":main()
