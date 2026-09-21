#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, shutil, subprocess, tempfile
from pathlib import Path

PREFIX="/data/data/studio.ocean.app/files/usr"
VERSION="1.0.0-1"
SRC=Path("sources/multiplier-shards/shards43_45_runtime.py")
OUT_ROOT=Path("staging")
SUPER=OUT_ROOT/"multiplier-superpack"

def load():
    spec=importlib.util.spec_from_file_location("ocean_multi",SRC)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def control(pkg,depends,desc):
    dep=", ".join(depends)
    return (
      "Package: %s\nVersion: %s\nArchitecture: all\n"%(pkg,VERSION)
      +"Maintainer: OceanStudio <packages@ocean.studio>\nSection: utils\nPriority: optional\n"
      +(("Depends: %s\n"%dep) if dep else "")
      +"Description: %s\n"%desc
      +" Functional OceanStudio package for the Android user-space prefix.\n"
    )

def utility_launcher(pkg):
    return """#!/system/bin/sh
if [ -z "$PREFIX" ]; then PREFIX="%s"; fi
exec "$PREFIX/bin/python" "$PREFIX/lib/ocean-multipliers/%s.py" %s "$@"
"""%(PREFIX,pkg,repr(pkg))

def gateway_launcher(name,spec):
    p=PREFIX
    mode=spec["mode"]
    if mode=="mise":
        return """#!/system/bin/sh
PREFIX="${PREFIX:-%s}"
exec "$PREFIX/bin/mise" exec %s@latest -- %s "$@"
"""%(p,spec["tool"],spec["binary"])
    if mode=="npm-exec":
        return """#!/system/bin/sh
PREFIX="${PREFIX:-%s}"
exec "$PREFIX/bin/npm" exec -- "$@"
"""%p
    if mode=="uvx":
        return """#!/system/bin/sh
PREFIX="${PREFIX:-%s}"
exec "$PREFIX/bin/uvx" %s "$@"
"""%(p,spec["package"])
    if mode=="uvx-from":
        return """#!/system/bin/sh
PREFIX="${PREFIX:-%s}"
exec "$PREFIX/bin/uvx" --from %s %s "$@"
"""%(p,spec["package"],spec["binary"])
    if mode=="npm-package":
        return """#!/system/bin/sh
PREFIX="${PREFIX:-%s}"
exec "$PREFIX/bin/npm" exec --yes --package %s -- %s "$@"
"""%(p,spec["package"],spec["binary"])
    if mode=="gateway-sub":
        prefix=" ".join("'" + x.replace("'","'\"'\"'") + "'" for x in spec["prefix"])
        return """#!/system/bin/sh
PREFIX="${PREFIX:-%s}"
exec "$PREFIX/bin/%s" %s "$@"
"""%(p,spec["gateway"],prefix)
    raise ValueError(mode)

def build_deb(pkg,depends,desc,launcher,runtime=None,outdir=None,aliases=None):
    outdir=Path(outdir); outdir.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ocean-multi-") as td:
        root=Path(td)/pkg
        deb=root/"DEBIAN"; bind=root/PREFIX.strip("/")/"bin"; lib=root/PREFIX.strip("/")/"lib/ocean-multipliers"
        deb.mkdir(parents=True); bind.mkdir(parents=True)
        (deb/"control").write_text(control(pkg,depends,desc))
        q=bind/pkg; q.write_text(launcher); q.chmod(0o755)
        for alias in (aliases or []):
            os.symlink(pkg,bind/alias)
        if runtime is not None:
            lib.mkdir(parents=True)
            r=lib/(pkg+".py"); shutil.copy2(runtime,r); r.chmod(0o755)
        art=outdir/(pkg+"_"+VERSION+"_all.deb")
        subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(art)],check=True,stdout=subprocess.DEVNULL)
        return art

def build_meta(pkg,deps,outdir,desc):
    return build_deb(pkg,deps,desc,"#!/system/bin/sh\nprintf '%s\\n' 'meta-package: no executable action'\n",None,outdir)

def artifact_row(art,pkg,kind,extra=None):
    raw=art.read_bytes()
    x={"package":pkg,"artifact":art.name,"kind":kind,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
    if extra:x.update(extra)
    return x

def existing_names(index_path):
    txt=Path(index_path).read_text(errors="replace")
    return set(re.findall(r"^Package:\\s*(\\S+)",txt,re.M))

def write_manifest(folder,rows,meta):
    d={"schemaVersion":1,"version":VERSION,"prefix":PREFIX,"packageCount":len(rows),"uniquePackageCount":len({r["package"] for r in rows}),"packages":rows}
    d.update(meta)
    (folder/"provenance.json").write_text(json.dumps(d,indent=2)+"\n")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--live-index",default="apt/dists/stable/main/binary-aarch64/Packages")
    a=ap.parse_args()
    m=load()
    assert len(m.COMMANDS)==300
    assert len(m.GATEWAYS)==15
    live=existing_names(a.live_index)

    shard_pkgs={}
    all_new=[]
    for shard,families in m.SHARDS.items():
        names=[n for n,(fam,op) in m.COMMANDS.items() if fam in families]
        assert len(names)==100 and len(set(names))==100
        if shard=="43":
            names += list(m.GATEWAYS)
        shard_pkgs[shard]=names
        all_new += names
    metas=["multiplier-shard-43","multiplier-shard-44","multiplier-shard-45","ocean-multiplier-superpack"]
    collision=sorted(set(all_new+metas)&live)
    if collision:
        raise SystemExit("live package collisions: "+", ".join(collision))
    if len(set(all_new+metas))!=len(all_new)+len(metas):
        raise SystemExit("internal package-name collision")

    for shard,families in m.SHARDS.items():
        folder=OUT_ROOT/("shard-"+shard); pool=folder/"pool/main"
        if folder.exists(): shutil.rmtree(folder)
        pool.mkdir(parents=True)
        rows=[]; util_names=[]
        for pkg,(fam,op) in m.COMMANDS.items():
            if fam not in families: continue
            art=build_deb(pkg,["python"],"%s utility: %s"%(fam,op),utility_launcher(pkg),SRC,pool)
            rows.append(artifact_row(art,pkg,"standalone-utility",{"family":fam,"operation":op}))
            util_names.append(pkg)
        if shard=="43":
            for pkg,spec in m.GATEWAYS.items():
                art=build_deb(pkg,spec["depends"],"ecosystem multiplier gateway: "+pkg,gateway_launcher(pkg,spec),None,pool,spec.get("aliases",[]))
                rows.append(artifact_row(art,pkg,"upstream-gateway",{"mode":spec["mode"],"depends":spec["depends"]}))
        meta_name="multiplier-shard-"+shard
        deps=[r["package"] for r in rows]
        art=build_meta(meta_name,deps,pool,"Ocean multiplier shard "+shard+" meta-package")
        rows.append(artifact_row(art,meta_name,"meta"))
        write_manifest(folder,rows,{
            "shard":int(shard),
            "families":families,
            "standaloneUtilityCount":len(util_names),
            "gatewayCount":len(m.GATEWAYS) if shard=="43" else 0,
            "metaPackageCount":1,
            "networkAtAptInstall":False,
            "rootRequired":False,
            "promotion":"staged; signed live promotion requires OCEAN_REPOSITORY_SIGNING_KEY",
        })

    if SUPER.exists(): shutil.rmtree(SUPER)
    pool=SUPER/"pool/main"; pool.mkdir(parents=True)
    deps=["multiplier-shard-43","multiplier-shard-44","multiplier-shard-45"]
    art=build_meta("ocean-multiplier-superpack",deps,pool,"OceanStudio 300-utility multiplier superpack")
    rows=[artifact_row(art,"ocean-multiplier-superpack","meta")]
    write_manifest(SUPER,rows,{
      "standaloneUtilityCount":300,
      "gatewayCount":15,
      "shardMetaCount":3,
      "totalNewPackageNames":319,
      "dependsOn":deps,
      "promotion":"staged; signed live promotion requires OCEAN_REPOSITORY_SIGNING_KEY",
    })
    print(json.dumps({
      "standaloneUtilities":300,
      "gatewayPackages":15,
      "shardMetaPackages":3,
      "superpack":1,
      "totalNewPackages":319,
      "shard43":116,
      "shard44":101,
      "shard45":101,
      "superpackFiles":1
    },indent=2))

if __name__=="__main__":
    main()
