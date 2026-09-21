#!/usr/bin/env python3
from __future__ import annotations
import json, os, pathlib, shutil, subprocess, sys
P=pathlib.Path

PREFIX="/data/data/studio.ocean.app/files/usr"
PROVIDERS={
"maven":{
 "dependency-get":["dependency:get"],"dependency-copy":["dependency:copy"],"dependency-tree":["dependency:tree"],
 "dependency-list":["dependency:list"],"versions-display":["versions:display-dependency-updates"],
 "versions-update":["versions:use-latest-versions"],"wrapper":["wrapper:wrapper"],"package":["package"],
 "test":["test"],"exec":["exec:java"]},
"gradle":{
 "dependencies":["dependencies"],"dependency-insight":["dependencyInsight"],"build":["build"],"test":["test"],
 "tasks":["tasks"],"properties":["properties"],"wrapper":["wrapper"],"projects":["projects"],
 "components":["components"],"build-environment":["buildEnvironment"]},
"jbang":{
 "run":[],"app-install":["app","install"],"app-uninstall":["app","uninstall"],"app-list":["app","list"],
 "catalog-list":["catalog","list"],"catalog-add":["catalog","add"],"cache-clear":["cache","clear"],
 "jdk-list":["jdk","list"],"jdk-install":["jdk","install"],"version-update":["version","--update"]},
"coursier":{
 "install":["install"],"uninstall":["uninstall"],"list":["list"],"launch":["launch"],"resolve":["resolve"],
 "fetch":["fetch"],"search":["search"],"java":["java"],"java-home":["java-home"],"setup":["setup"]},
"dart":{
 "pub-add":["pub","add"],"pub-remove":["pub","remove"],"pub-get":["pub","get"],"pub-upgrade":["pub","upgrade"],
 "pub-outdated":["pub","outdated"],"pub-cache":["pub","cache"],"pub-global-activate":["pub","global","activate"],
 "pub-global-deactivate":["pub","global","deactivate"],"run":["run"],"compile":["compile"]},
"pixi":{
 "add":["add"],"remove":["remove"],"install":["install"],"update":["update"],"list":["list"],"run":["run"],
 "global-install":["global","install"],"global-remove":["global","remove"],"global-list":["global","list"],"search":["search"]},
"nix":{
 "profile-install":["profile","install"],"profile-remove":["profile","remove"],"profile-list":["profile","list"],
 "search":["search"],"run":["run"],"shell":["shell"],"develop":["develop"],"flake-show":["flake","show"],
 "flake-update":["flake","update"],"store-gc":["store","gc"]},
"aqua":{
 "init":["init"],"install":["install"],"generate":["generate"],"update":["update"],"remove":["remove"],
 "which":["which"],"info":["info"],"vacuum":["vacuum"],"update-checksum":["update-checksum"],"update-aqua":["update-aqua"]},
"mise":{
 "install":["install"],"use":["use"],"exec":["exec"],"list":["ls"],"latest":["latest"],"outdated":["outdated"],
 "upgrade":["upgrade"],"uninstall":["uninstall"],"which":["which"],"doctor":["doctor"]},
"asdf":{
 "plugin-add":["plugin","add"],"plugin-list":["plugin","list"],"plugin-update":["plugin","update"],
 "install":["install"],"uninstall":["uninstall"],"set":["set"],"current":["current"],"list":["list"],
 "latest":["latest"],"exec":["exec"]},
}
COMMANDS={f"envhub-{provider}-{op}":(provider,op) for provider,ops in PROVIDERS.items() for op in ops}
assert len(COMMANDS)==100 and len(set(COMMANDS))==100

DIRECT={"maven":"mvn","gradle":"gradle","jbang":"jbang","coursier":"cs","dart":"dart","pixi":"pixi",
        "nix":"nix","aqua":"aqua","mise":"mise","asdf":"asdf"}
MISE_TOOL={"maven":"maven","gradle":"gradle","jbang":"jbang","coursier":"coursier","dart":"dart","pixi":"pixi"}

def emit(x):
    print(json.dumps(x,indent=2,ensure_ascii=False,default=str) if isinstance(x,(dict,list,tuple)) else x)
def die(msg,code=2):
    print(msg,file=sys.stderr);raise SystemExit(code)
def find(name):return shutil.which(name)

def preferred(provider):
    return {"binary":DIRECT[provider],"fallback_tool":MISE_TOOL.get(provider)}

def resolve_base(provider):
    direct=find(DIRECT[provider])
    if not direct and provider=="coursier":
        direct=find("coursier")
    if direct:return [direct],{"mode":"direct","binary":direct}
    tool=MISE_TOOL.get(provider)
    mise=find("mise")
    if tool and mise:
        binary=DIRECT[provider]
        return [mise,"exec",tool+"@latest","--",binary],{"mode":"mise","tool":tool+"@latest","binary":binary}
    if provider=="nix":die("nix backend unavailable; install the Ocean nix-ocean package")
    if provider=="aqua":die("aqua backend unavailable; install the Ocean aqua package")
    if provider=="mise":die("mise backend unavailable; install the Ocean mise package")
    if provider=="asdf":die("asdf backend unavailable; install the Ocean asdf-vm package")
    die(f"{provider} backend unavailable. Install mise or the native manager.")

def plan(cmd,args):
    provider,op=COMMANDS[cmd];p=preferred(provider)
    return {"package":cmd,"provider":provider,"operation":op,"preferred_binary":p["binary"],
            "mise_fallback_tool":(p["fallback_tool"]+"@latest" if p["fallback_tool"] else None),
            "operation_argv":PROVIDERS[provider][op]+list(args),"prefix":PREFIX}

def main():
    cmd=P(sys.argv[0]).name;args=sys.argv[1:]
    if cmd not in COMMANDS:
        if args and args[0] in COMMANDS:cmd=args.pop(0)
        elif not args or args[0] in ("-h","--help"):
            print("Ocean Foundation shard 42 — JVM/Dart/universal environment managers")
            print("\n".join(COMMANDS));return
        else:die("unknown command")
    if args and args[0] in ("-h","--help"):
        provider,op=COMMANDS[cmd]
        print(f"{cmd} — {provider} {op}; forwards remaining arguments to the environment/package manager");return
    dry=False
    if "--plan" in args:
        args=[x for x in args if x!="--plan"];dry=True
    p=plan(cmd,args)
    if dry or os.environ.get("OCEAN_FOUNDATION_PLAN")=="1":
        emit(p);return
    provider,op=COMMANDS[cmd]
    base,_=resolve_base(provider)
    raise SystemExit(subprocess.run(base+PROVIDERS[provider][op]+list(args)).returncode)

if __name__=="__main__":main()
