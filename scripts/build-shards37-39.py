#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,importlib.util,json,shutil,subprocess,tempfile
from pathlib import Path

PREFIX="/data/data/studio.ocean.app/files/usr"
VERSION="1.0.0-1"
SHARDS={
  "37":{"source":"sources/functional-shards/shard37_geospatial.py","output":"staging/shard-37","expected":100,"label":"GeoJSON/WKT/GPX/KML/MapLibre tiles"},
  "38":{"source":"sources/functional-shards/shard38_gltf_gpu.py","output":"staging/shard-38","expected":100,"label":"glTF/GLB/KTX2/3D asset inspection"},
  "39":{"source":"sources/functional-shards/shard39_android_binary.py","output":"staging/shard-39","expected":100,"label":"Android DEX/AXML/ARSC/APK internals"},
}

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def control(pkg,shard,label):
    return f"""Package: {pkg}
Version: {VERSION}
Architecture: all
Maintainer: OceanStudio <packages@ocean.studio>
Section: utils
Priority: optional
Depends: python
Description: {label} utility ({pkg})
 Functional OceanStudio shard {shard} utility. Package-family names are new,
 while the installation prefix remains {PREFIX}.
"""

def launcher(pkg,shard):
    return f"""#!/system/bin/sh
if [ -z "$PREFIX" ]; then PREFIX="{PREFIX}"; fi
exec "$PREFIX/bin/python" "$PREFIX/lib/ocean-shard{shard}/{pkg}.py" {pkg!r} "$@"
"""

def existing_names():
    try:paths=subprocess.check_output(["git","ls-tree","-r","--name-only","HEAD"],text=True).splitlines()
    except:return set()
    out=set()
    for path in paths:
        if not path.endswith(".deb"):continue
        if path.startswith(("staging/shard-37/","staging/shard-38/","staging/shard-39/")):continue
        out.add(Path(path).name.split("_",1)[0])
    return out

def build_one(pkg,src,out,shard,label):
    with tempfile.TemporaryDirectory(prefix=f"ocean-shard{shard}-") as td:
        root=Path(td)/pkg
        deb=root/"DEBIAN";bind=root/PREFIX.strip("/")/"bin";lib=root/PREFIX.strip("/")/f"lib/ocean-shard{shard}"
        deb.mkdir(parents=True);bind.mkdir(parents=True);lib.mkdir(parents=True)
        (deb/"control").write_text(control(pkg,shard,label))
        l=bind/pkg;l.write_text(launcher(pkg,shard));l.chmod(0o755)
        target=lib/f"{pkg}.py";shutil.copy2(src,target);target.chmod(0o755)
        art=out/f"{pkg}_{VERSION}_all.deb"
        subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(art)],check=True,stdout=subprocess.DEVNULL)
        return art

def build_shard(num,collision_set):
    cfg=SHARDS[num];src=Path(cfg["source"]);out=Path(cfg["output"]);pool=out/"pool/main"
    mod=load(src,f"shard{num}");names=list(mod.COMMANDS)
    if len(names)!=cfg["expected"] or len(set(names))!=cfg["expected"]:
        raise SystemExit(f"shard {num}: expected {cfg['expected']} unique names, got {len(names)}/{len(set(names))}")
    collisions=sorted(set(names)&collision_set)
    if collisions:raise SystemExit(f"shard {num} repo-wide collisions: "+", ".join(collisions))
    if out.exists():shutil.rmtree(out)
    pool.mkdir(parents=True)
    rows=[]
    for pkg in names:
        art=build_one(pkg,src,pool,num,cfg["label"]);raw=art.read_bytes()
        rows.append({"package":pkg,"artifact":art.name,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"depends":"python"})
    paras=[]
    for row in rows:
        fields=subprocess.check_output(["dpkg-deb","-f",str(pool/row["artifact"])],text=True).strip()
        paras.append(fields+f"\nFilename: {cfg['output']}/pool/main/{row['artifact']}\nSize: {row['bytes']}\nSHA256: {row['sha256']}\n")
    (out/"Packages.repaired").write_text("\n".join(paras))
    prov={
      "schemaVersion":1,"suite":f"shard-{num}","version":VERSION,"sourceType":"Ocean-native original source",
      "prefix":PREFIX,"packageCount":len(rows),"uniquePackageCount":len({x["package"] for x in rows}),
      "termuxRuntimeDependency":False,"topic":cfg["label"],"packages":rows,
      "promotion":"staging-only until APT promotion/signing"
    }
    (out/"provenance.json").write_text(json.dumps(prov,indent=2)+"\n")
    return rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--shards",default="37,38,39");a=ap.parse_args()
    nums=[x.strip() for x in a.shards.split(",") if x.strip()]
    seen=existing_names();built=[]
    for num in nums:
        if num not in SHARDS:raise SystemExit("unknown shard "+num)
        rows=build_shard(num,seen);built+=rows;seen.update(x["package"] for x in rows)
    print(json.dumps({"built":len(built),"unique":len({x["package"] for x in built}),"shards":nums},indent=2))
if __name__=="__main__":main()
