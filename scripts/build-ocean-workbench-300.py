#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,importlib.util,json,shutil,subprocess,tempfile
from pathlib import Path

PREFIX="/data/data/studio.ocean.app/files/usr"
VERSION="1.0.0-1"

def load_runtime(path):
    spec=importlib.util.spec_from_file_location("ocean_workbench",path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def control(pkg):
    return f"""Package: {pkg}
Version: {VERSION}
Architecture: all
Maintainer: OceanStudio <packages@ocean.studio>
Section: utils
Priority: optional
Depends: python
Description: OceanStudio {pkg.removeprefix('ocean-wb-').replace('-',' ')} workbench utility
 Functional Ocean-native command from the Workbench 300 suite.
"""

def launcher(pkg):
    return f"""#!/system/bin/sh
if [ -z "$PREFIX" ]; then PREFIX="{PREFIX}"; fi
exec "$PREFIX/bin/python" "$PREFIX/lib/ocean-workbench/ocean_workbench.py" {pkg!r} "$@"
"""

def build_one(pkg,runtime,out):
    with tempfile.TemporaryDirectory(prefix="ocean-workbench-deb-") as td:
        root=Path(td)/pkg
        deb=root/"DEBIAN";bin_dir=root/PREFIX.strip("/")/"bin";lib=root/PREFIX.strip("/")/"lib/ocean-workbench"
        deb.mkdir(parents=True);bin_dir.mkdir(parents=True);lib.mkdir(parents=True)
        (deb/"control").write_text(control(pkg))
        q=bin_dir/pkg;q.write_text(launcher(pkg));q.chmod(0o755)
        shutil.copy2(runtime,lib/"ocean_workbench.py");(lib/"ocean_workbench.py").chmod(0o755)
        art=out/f"{pkg}_{VERSION}_all.deb"
        subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(art)],check=True,stdout=subprocess.DEVNULL)
        return art

def parse_live(path):
    out=set()
    if path and Path(path).exists():
        for line in Path(path).read_text(errors="replace").splitlines():
            if line.startswith("Package: "):out.add(line.split(": ",1)[1].strip())
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--runtime",required=True);ap.add_argument("--output",required=True);ap.add_argument("--live-packages",default="")
    a=ap.parse_args();runtime=Path(a.runtime);out=Path(a.output);pool=out/"pool/main"
    m=load_runtime(runtime);names=list(m.COMMANDS)
    if len(names)!=300 or len(set(names))!=300:raise SystemExit("suite must contain exactly 300 unique commands")
    collisions=sorted(set(names)&parse_live(a.live_packages))
    if collisions:raise SystemExit("live package collision: "+", ".join(collisions))
    if out.exists():shutil.rmtree(out)
    pool.mkdir(parents=True)
    rows=[]
    for pkg in names:
        art=build_one(pkg,runtime,pool);raw=art.read_bytes()
        rows.append({"package":pkg,"artifact":art.name,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"depends":"python"})
    paras=[]
    for row in rows:
        fields=subprocess.check_output(["dpkg-deb","-f",str(pool/row["artifact"])],text=True).strip()
        paras.append(fields+"\nFilename: staging/ocean-workbench-300/pool/main/"+row["artifact"]+"\nSize: "+str(row["bytes"])+"\nSHA256: "+row["sha256"]+"\n")
    (out/"Packages.repaired").write_text("\n".join(paras))
    provenance={
      "schemaVersion":1,"suite":"ocean-workbench-300","version":VERSION,
      "sourceType":"Ocean-native original source","prefix":PREFIX,
      "packageCount":300,"uniquePackageCount":300,"termuxRuntimeDependency":False,
      "groups":{k:len(v) for k,v in m.GROUPS.items()},"packages":rows,
      "promotion":"staging-only until APT promotion/signing"
    }
    (out/"provenance.json").write_text(json.dumps(provenance,indent=2)+"\n")
    print(json.dumps({"built":len(rows),"unique":len({x["package"] for x in rows}),"output":str(out)},indent=2))
if __name__=="__main__":main()
