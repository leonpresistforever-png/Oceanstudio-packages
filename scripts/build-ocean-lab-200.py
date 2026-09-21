#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,importlib.util,json,shutil,subprocess,tempfile
from pathlib import Path
PREFIX="/data/data/studio.ocean.app/files/usr"
VERSION="1.0.0-1"

def load_runtime(path):
    spec=importlib.util.spec_from_file_location("ocean_lab",path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def control(pkg):
    return f"""Package: {pkg}
Version: {VERSION}
Architecture: all
Maintainer: OceanStudio <packages@ocean.studio>
Section: utils
Priority: optional
Depends: python
Description: OceanStudio {pkg.removeprefix('ocean-lab-').replace('-',' ')}
 Functional Ocean Lab utility using Python standard-library parsing and analysis.
"""

def launcher(pkg):
    return f"""#!/system/bin/sh
if [ -z "$PREFIX" ]; then PREFIX="{PREFIX}"; fi
exec "$PREFIX/bin/python" "$PREFIX/lib/ocean-lab/{pkg}.py" {pkg!r} "$@"
"""

def build_one(pkg,runtime,out):
    with tempfile.TemporaryDirectory(prefix="ocean-lab-deb-") as td:
        root=Path(td)/pkg
        deb=root/"DEBIAN"
        bin_dir=root/PREFIX.strip("/")/"bin"
        lib_dir=root/PREFIX.strip("/")/"lib/ocean-lab"
        deb.mkdir(parents=True);bin_dir.mkdir(parents=True);lib_dir.mkdir(parents=True)
        (deb/"control").write_text(control(pkg))
        l=bin_dir/pkg;l.write_text(launcher(pkg));l.chmod(0o755)
        target=lib_dir/f"{pkg}.py";shutil.copy2(runtime,target);target.chmod(0o755)
        artifact=out/f"{pkg}_{VERSION}_all.deb"
        subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(artifact)],check=True,stdout=subprocess.DEVNULL)
        return artifact

def package_names_from_tree():
    try:
        paths=subprocess.check_output(["git","ls-tree","-r","--name-only","HEAD"],text=True).splitlines()
    except Exception:
        return set()
    out=set()
    for path in paths:
        if path.endswith(".deb") and not path.startswith("staging/ocean-lab-200/"):
            out.add(Path(path).name.split("_",1)[0])
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--runtime",required=True)
    ap.add_argument("--output",required=True)
    a=ap.parse_args()
    runtime=Path(a.runtime);out=Path(a.output);pool=out/"pool/main"
    m=load_runtime(runtime);names=list(m.COMMANDS)
    if len(names)!=200 or len(set(names))!=200:raise SystemExit("suite must contain exactly 200 unique package names")
    collisions=sorted(set(names)&package_names_from_tree())
    if collisions:raise SystemExit("repo-wide package collision: "+", ".join(collisions))
    if out.exists():shutil.rmtree(out)
    pool.mkdir(parents=True)
    rows=[]
    for pkg in names:
        art=build_one(pkg,runtime,pool);raw=art.read_bytes()
        rows.append({"package":pkg,"artifact":art.name,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"depends":"python"})
    paras=[]
    for row in rows:
        fields=subprocess.check_output(["dpkg-deb","-f",str(pool/row["artifact"])],text=True).strip()
        paras.append(fields+"\nFilename: staging/ocean-lab-200/pool/main/"+row["artifact"]+"\nSize: "+str(row["bytes"])+"\nSHA256: "+row["sha256"]+"\n")
    (out/"Packages.repaired").write_text("\n".join(paras))
    provenance={
      "schemaVersion":1,"suite":"ocean-lab-200","version":VERSION,
      "sourceType":"Ocean-native original source","prefix":PREFIX,
      "packageCount":200,"uniquePackageCount":200,
      "termuxRuntimeDependency":False,
      "groups":{k:len(v) for k,v in m.GROUPS.items()},
      "runtimeModel":"self-contained package-specific Python runtime copy",
      "packages":rows,
      "promotion":"staging-only until APT promotion/signing"
    }
    (out/"provenance.json").write_text(json.dumps(provenance,indent=2)+"\n")
    print(json.dumps({"built":200,"unique":200,"output":str(out)},indent=2))
if __name__=="__main__":main()
