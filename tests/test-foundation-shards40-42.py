#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,os,subprocess,sys,tempfile
from pathlib import Path

R40=Path(sys.argv[1]).resolve()
R41=Path(sys.argv[2]).resolve()
R42=Path(sys.argv[3]).resolve()
BUILDER=Path(sys.argv[4]).resolve()

def load(path,name):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

m40=load(R40,"s40");m41=load(R41,"s41");m42=load(R42,"s42");builder=load(BUILDER,"builder")
assert len(m40.COMMANDS)==100 and len(set(m40.COMMANDS))==100
assert len(m41.COMMANDS)==100 and len(set(m41.COMMANDS))==100
assert len(m42.COMMANDS)==100 and len(set(m42.COMMANDS))==100
all_cmds=list(m40.COMMANDS)+list(m41.COMMANDS)+list(m42.COMMANDS)
assert len(all_cmds)==300 and len(set(all_cmds))==300

providers=set()
for m in (m40,m41,m42):
    providers.update(p for p,_ in m.COMMANDS.values())
assert providers <= set(builder.DEPENDENCY_BY_PROVIDER)
assert builder.PREFIX=="/data/data/studio.ocean.app/files/usr"

runtime={}
runtime.update({x:R40 for x in m40.COMMANDS})
runtime.update({x:R41 for x in m41.COMMANDS})
runtime.update({x:R42 for x in m42.COMMANDS})

def run(cmd,*args,env=None):
    p=subprocess.run([sys.executable,str(runtime[cmd]),cmd,*map(str,args)],capture_output=True,text=True,env=env)
    if p.returncode:
        raise AssertionError(f"{cmd} rc={p.returncode}\nstdout={p.stdout}\nstderr={p.stderr}")
    return p.stdout

# Every package command must expose help and a side-effect-free concrete execution plan.
plans={}
for cmd in all_cmds:
    assert cmd in run(cmd,"--help")
    plan=json.loads(run(cmd,"--plan","demo"))
    assert plan["package"]==cmd
    assert plan["prefix"]=="/data/data/studio.ocean.app/files/usr"
    assert plan["provider"]
    assert plan["operation"]
    assert isinstance(plan["operation_argv"],list)
    plans[cmd]=plan

assert plans["forge-pip-install"]["operation_argv"][:2]==["install","demo"]
assert plans["forge-pip-index-versions"]["operation_argv"][:3]==["index","versions","demo"]
assert plans["forge-uv-tool-install"]["operation_argv"][:3]==["tool","install","demo"]
assert plans["ecosys-cargo-publish-dryrun"]["operation_argv"][:3]==["publish","--dry-run","demo"]
assert plans["ecosys-rust-toolchain-install"]["operation_argv"][:2]==["install","rust@demo"]
assert plans["ecosys-nuget-add-source"]["operation_argv"][:4]==["nuget","add","source","demo"]
assert plans["envhub-jbang-app-install"]["operation_argv"][:3]==["app","install","demo"]
assert plans["envhub-coursier-search"]["operation_argv"][:2]==["search","demo"]
assert plans["envhub-aqua-update-checksum"]["operation_argv"][:2]==["update-checksum","demo"]
assert plans["envhub-mise-install"]["operation_argv"][:2]==["install","demo"]

# Put harmless manager stubs first on PATH, then execute every command for real.
stub_names={
 "pip","uv","pipx","poetry","pdm","npm","pnpm","yarn","bun","deno",
 "cargo","mise","go","gem","bundle","composer","luarocks","dotnet","swift",
 "mvn","gradle","jbang","cs","dart","pixi","nix","aqua","asdf"
}
with tempfile.TemporaryDirectory() as td:
    d=Path(td);bind=d/"bin";bind.mkdir();log=d/"calls.log"
    script='''#!/bin/sh
printf "%s|" "$(basename "$0")" >> "$OCEAN_STUB_LOG"
printf "%s\\n" "$*" >> "$OCEAN_STUB_LOG"
exit 0
'''
    for name in stub_names:
        p=bind/name;p.write_text(script);p.chmod(0o755)
    env=dict(os.environ)
    env["PATH"]=str(bind)+os.pathsep+env.get("PATH","")
    env["OCEAN_STUB_LOG"]=str(log)
    for cmd in all_cmds:
        run(cmd,"demo",env=env)
    calls=log.read_text().splitlines()
    assert len(calls)==300, len(calls)

    # Representative dispatch assertions spanning every provider family.
    expected=[
      "pip|install demo","uv|tool install demo","pipx|install demo","poetry|add demo","pdm|add demo",
      "npm|install demo","pnpm|add demo","yarn|add demo","bun|add demo","deno|install demo",
      "cargo|install demo","mise|install rust@demo","go|install demo","gem|install demo","bundle|install demo",
      "composer|require demo","luarocks|install demo","dotnet|tool install demo","dotnet|nuget add source demo","swift|package resolve demo",
      "mvn|dependency:get demo","gradle|dependencies demo","jbang|demo","cs|install demo","dart|pub add demo",
      "pixi|add demo","nix|profile install demo","aqua|init demo","mise|install demo","asdf|plugin add demo"
    ]
    for e in expected:
        assert e in calls, (e,calls[:20])

print("PASS: 300 unique foundation command packages; all plans validated and all 300 dispatch paths executed against isolated manager stubs")
