#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,importlib.util,json,shutil,subprocess,tempfile
from pathlib import Path
PREFIX="/data/data/studio.ocean.app/files/usr"
VERSION="1.0.0-1"
RUNTIME_PKG="ocean-devkit-runtime"
def load_runtime(path):
    spec=importlib.util.spec_from_file_location("ocean_devkit",path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def deps(pkg):
    if pkg==RUNTIME_PKG:return "python"
    d=[f"{RUNTIME_PKG} (= {VERSION})"]
    if pkg.startswith("ocean-gitx-"):d.append("git")
    return ", ".join(d)
def control(pkg):
    return f"""Package: {pkg}
Version: {VERSION}
Architecture: all
Maintainer: OceanStudio <packages@ocean.studio>
Section: utils
Priority: optional
Depends: {deps(pkg)}
Description: OceanStudio {pkg.removeprefix('ocean-').replace('-',' ')}
 Functional Ocean-native developer utility from the Ocean DevKit 200 suite.
"""
def launcher(pkg):
    return f"""#!/system/bin/sh
if [ -z "$PREFIX" ]; then PREFIX="{PREFIX}"; fi
exec "$PREFIX/bin/python" "$PREFIX/lib/ocean-devkit/ocean_devkit.py" {pkg!r} "$@"
"""
def build_one(pkg,runtime,out):
    with tempfile.TemporaryDirectory(prefix="ocean-devkit-deb-") as td:
        root=Path(td)/pkg;deb=root/"DEBIAN";bin_dir=root/PREFIX.strip("/")/"bin";lib=root/PREFIX.strip("/")/"lib/ocean-devkit"
        deb.mkdir(parents=True);bin_dir.mkdir(parents=True);lib.mkdir(parents=True)
        (deb/"control").write_text(control(pkg))
        q=bin_dir/pkg;q.write_text(launcher(pkg));q.chmod(0o755)
        if pkg==RUNTIME_PKG:
            shutil.copy2(runtime,lib/"ocean_devkit.py");(lib/"ocean_devkit.py").chmod(0o755)
        artifact=out/f"{pkg}_{VERSION}_all.deb"
        subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(artifact)],check=True,stdout=subprocess.DEVNULL)
        return artifact
def parse_packages(path):
    out=set()
    if not path or not Path(path).exists():return out
    for line in Path(path).read_text(errors="replace").splitlines():
        if line.startswith("Package: "):out.add(line.split(": ",1)[1].strip())
    return out
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--runtime",required=True);ap.add_argument("--output",required=True);ap.add_argument("--live-packages",default="")
    a=ap.parse_args();runtime=Path(a.runtime);out=Path(a.output);pool=out/"pool/main"
    m=load_runtime(runtime);names=list(m.COMMANDS)
    if len(names)!=200 or len(set(names))!=200:raise SystemExit("suite must contain exactly 200 unique names")
    collisions=sorted(set(names)&parse_packages(a.live_packages))
    if collisions:raise SystemExit("live APT collision: "+", ".join(collisions))
    if out.exists():shutil.rmtree(out)
    pool.mkdir(parents=True)
    rows=[]
    for pkg in names:
        art=build_one(pkg,runtime,pool);raw=art.read_bytes()
        rows.append({"package":pkg,"artifact":art.name,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"depends":deps(pkg)})
    paras=[]
    for row in rows:
        fields=subprocess.check_output(["dpkg-deb","-f",str(pool/row["artifact"])],text=True).strip()
        paras.append(fields+"\nFilename: staging/ocean-devkit-200/pool/main/"+row["artifact"]+"\nSize: "+str(row["bytes"])+"\nSHA256: "+row["sha256"]+"\n")
    (out/"Packages.repaired").write_text("\n".join(paras))
    prov={"schemaVersion":1,"suite":"ocean-devkit-200","version":VERSION,"sourceType":"Ocean-native original source","prefix":PREFIX,"packageCount":200,"uniquePackageCount":200,"runtimePackage":RUNTIME_PKG,"termuxRuntimeDependency":False,"groups":{"apk":20,"web":20,"git":20,"text":20,"data":20,"filesystem":20,"network":20,"crypto":20,"build":20,"archive":19,"runtime":1},"packages":rows,"promotion":"staging-only until APT promotion/signing"}
    (out/"provenance.json").write_text(json.dumps(prov,indent=2)+"\n")
    print(json.dumps({"built":len(rows),"unique":len({x["package"] for x in rows}),"output":str(out)},indent=2))
if __name__=="__main__":main()
