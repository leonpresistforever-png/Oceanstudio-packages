#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,importlib.util,json,shutil,subprocess,tempfile,textwrap
from pathlib import Path

PREFIX="/data/data/studio.ocean.app/files/usr"
VERSION="1.0.0-1"
SHARDS={
 "40":{"source":"sources/foundation-shards/shard40_forge_pyjs.py","output":"staging/shard-40","expected":100,"suite":"forge-foundation-suite","topic":"Python/JavaScript package ecosystems"},
 "41":{"source":"sources/foundation-shards/shard41_ecosys_lang.py","output":"staging/shard-41","expected":100,"suite":"ecosys-foundation-suite","topic":"compiled/language package ecosystems"},
 "42":{"source":"sources/foundation-shards/shard42_envhub_universal.py","output":"staging/shard-42","expected":100,"suite":"envhub-foundation-suite","topic":"JVM/Dart/universal environment managers"},
}
SUPERPACK="ocean-foundation-superpack"

DEPENDENCY_BY_PROVIDER={
 "pip":["python","pip","mise"],"uv":["python","mise"],"pipx":["python","pipx","mise"],
 "poetry":["python","pipx","mise"],"pdm":["python","pipx","mise"],
 "npm":["python","npm","mise"],"pnpm":["python","npm","mise"],"yarn":["python","npm","mise"],
 "bun":["python","mise"],"deno":["python","mise"],
 "cargo":["python","rust-cargo","mise"],"rust-toolchain":["python","mise"],"go":["python","go","mise"],
 "gem":["python","ruby-rubygems","mise"],"bundler":["python","ruby-rubygems","mise"],
 "composer":["python","composer","mise"],"luarocks":["python","luarocks","mise"],
 "dotnet":["python","mise"],"nuget":["python","mise"],"swiftpm":["python","mise"],
 "maven":["python","maven","mise"],"gradle":["python","gradle","mise"],"jbang":["python","mise"],
 "coursier":["python","mise"],"dart":["python","mise"],"pixi":["python","mise"],
 "nix":["python","nix-ocean","mise"],"aqua":["python","aqua","mise"],"mise":["python","mise"],
 "asdf":["python","asdf-vm","mise"],
}

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def wrap_field(name,items):
    # Debian continuation lines are allowed, but never split a dependency atom
    # such as "pkg (= version)" across lines.
    atoms=list(items)
    if not atoms:return f"{name}:\n"
    lines=[];cur=""
    for atom in atoms:
        piece=atom if not cur else ", "+atom
        if cur and len(name)+2+len(cur)+len(piece)>100:
            lines.append(cur+",")
            cur=atom
        else:
            cur+=piece
    if cur:lines.append(cur)
    return f"{name}: {lines[0]}\n"+"".join(" "+x+"\n" for x in lines[1:])

def command_control(pkg,provider,topic):
    deps=DEPENDENCY_BY_PROVIDER[provider]
    return (
      f"Package: {pkg}\nVersion: {VERSION}\nArchitecture: all\n"
      "Maintainer: OceanStudio <packages@ocean.studio>\nSection: devel\nPriority: optional\n"
      +wrap_field("Depends",deps)
      +f"Description: Ocean foundation command for {provider}\n"
       f" User-space {topic} command. It uses an installed native manager where available\n"
       f" and can fall back to Ocean's mise runtime without changing the Ocean prefix.\n"
    )

def meta_control(pkg,deps,desc):
    return (
      f"Package: {pkg}\nVersion: {VERSION}\nArchitecture: all\n"
      "Maintainer: OceanStudio <packages@ocean.studio>\nSection: devel\nPriority: optional\n"
      +wrap_field("Depends",[f"{x} (= {VERSION})" for x in deps])
      +f"Description: {desc}\n"
       " Meta-package only; installs the complete Ocean foundation capability set.\n"
    )

def launcher(pkg,shard):
    return (
      "#!/system/bin/sh\n"
      f'if [ -z "$PREFIX" ]; then PREFIX="{PREFIX}"; fi\n'
      f'exec "$PREFIX/bin/python" "$PREFIX/lib/ocean-foundation/shard{shard}/{pkg}.py" {pkg!r} "$@"\n'
    )

def build_command(pkg,provider,source,pool,shard,topic):
    with tempfile.TemporaryDirectory(prefix=f"ocean-foundation-{shard}-") as td:
        root=Path(td)/pkg
        deb=root/"DEBIAN"
        bind=root/PREFIX.strip("/")/"bin"
        lib=root/PREFIX.strip("/")/f"lib/ocean-foundation/shard{shard}"
        deb.mkdir(parents=True);bind.mkdir(parents=True);lib.mkdir(parents=True)
        (deb/"control").write_text(command_control(pkg,provider,topic))
        q=bind/pkg;q.write_text(launcher(pkg,shard));q.chmod(0o755)
        target=lib/f"{pkg}.py";shutil.copy2(source,target);target.chmod(0o755)
        art=pool/f"{pkg}_{VERSION}_all.deb"
        subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(art)],check=True,stdout=subprocess.DEVNULL)
        return art

def build_meta(pkg,deps,pool,desc):
    with tempfile.TemporaryDirectory(prefix="ocean-foundation-meta-") as td:
        root=Path(td)/pkg;(root/"DEBIAN").mkdir(parents=True)
        (root/"DEBIAN/control").write_text(meta_control(pkg,deps,desc))
        art=pool/f"{pkg}_{VERSION}_all.deb"
        subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(art)],check=True,stdout=subprocess.DEVNULL)
        return art

def repo_names():
    try:paths=subprocess.check_output(["git","ls-tree","-r","--name-only","HEAD"],text=True).splitlines()
    except:return set()
    out=set()
    for x in paths:
        if not x.endswith(".deb"):continue
        if x.startswith(("staging/shard-40/","staging/shard-41/","staging/shard-42/","staging/foundation-superpack/")):continue
        out.add(Path(x).name.split("_",1)[0])
    return out

def row_for(art,pkg,provider=None):
    raw=art.read_bytes()
    return {"package":pkg,"artifact":art.name,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),
            "provider":provider}

def write_index(out,rows,filename_prefix):
    paras=[]
    pool=out/"pool/main"
    for row in rows:
        fields=subprocess.check_output(["dpkg-deb","-f",str(pool/row["artifact"])],text=True).strip()
        paras.append(fields+f"\nFilename: {filename_prefix}/pool/main/{row['artifact']}\nSize: {row['bytes']}\nSHA256: {row['sha256']}\n")
    (out/"Packages.repaired").write_text("\n".join(paras))

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--shards",default="40,41,42");a=ap.parse_args()
    nums=[x.strip() for x in a.shards.split(",") if x.strip()]
    existing=repo_names();all_command_names=[];suite_names=[];built_total=0
    for num in nums:
        cfg=SHARDS[num];source=Path(cfg["source"]);mod=load(source,"shard"+num)
        commands=list(mod.COMMANDS)
        if len(commands)!=cfg["expected"] or len(set(commands))!=cfg["expected"]:
            raise SystemExit(f"shard {num}: expected {cfg['expected']} unique commands")
        collisions=sorted(set(commands+[cfg["suite"]])&existing)
        if collisions:raise SystemExit(f"shard {num} collisions: "+", ".join(collisions))
        out=Path(cfg["output"]);pool=out/"pool/main"
        if out.exists():shutil.rmtree(out)
        pool.mkdir(parents=True)
        rows=[]
        for pkg in commands:
            provider=mod.COMMANDS[pkg][0]
            art=build_command(pkg,provider,source,pool,num,cfg["topic"])
            rows.append(row_for(art,pkg,provider))
        suite=cfg["suite"]
        art=build_meta(suite,commands,pool,f"Ocean {cfg['topic']} foundation suite")
        rows.append(row_for(art,suite,"meta"))
        write_index(out,rows,cfg["output"])
        provenance={
          "schemaVersion":1,"suite":f"shard-{num}","version":VERSION,"sourceType":"Ocean-native original source",
          "prefix":PREFIX,"commandPackageCount":len(commands),"metaPackageCount":1,"packageCount":len(rows),
          "uniquePackageCount":len({x["package"] for x in rows}),"topic":cfg["topic"],
          "networkAtAptInstall":False,"rootRequired":False,"fallbackManager":"mise",
          "packages":rows,"promotion":"staging-only until APT promotion/signing"
        }
        (out/"provenance.json").write_text(json.dumps(provenance,indent=2)+"\n")
        all_command_names+=commands;suite_names.append(suite);built_total+=len(rows)
        existing.update(x["package"] for x in rows)

    # One top-level meta package that installs all three 101-package shards.
    super_out=Path("staging/foundation-superpack");super_pool=super_out/"pool/main"
    if super_out.exists():shutil.rmtree(super_out)
    super_pool.mkdir(parents=True)
    if SUPERPACK in existing:raise SystemExit("superpack collision: "+SUPERPACK)
    art=build_meta(SUPERPACK,suite_names,super_pool,"Ocean universal foundation superpack")
    super_rows=[row_for(art,SUPERPACK,"meta")]
    write_index(super_out,super_rows,"staging/foundation-superpack")
    (super_out/"provenance.json").write_text(json.dumps({
      "schemaVersion":1,"suite":"foundation-superpack","version":VERSION,"sourceType":"Ocean-native meta-package",
      "prefix":PREFIX,"packageCount":1,"uniquePackageCount":1,"dependsOnSuites":suite_names,
      "totalFoundationCommands":len(all_command_names),"totalNewPackages":built_total+1,
      "networkAtAptInstall":False,"rootRequired":False,"packages":super_rows,
      "promotion":"staging-only until APT promotion/signing"
    },indent=2)+"\n")
    built_total+=1

    if len(all_command_names)!=300 or len(set(all_command_names))!=300:
        raise SystemExit("foundation command set must be exactly 300 unique names")
    print(json.dumps({"commands":300,"shardPackages":built_total-1,"superpack":1,"totalNewPackages":built_total,
                      "suites":suite_names,"prefix":PREFIX},indent=2))

if __name__=="__main__":main()
