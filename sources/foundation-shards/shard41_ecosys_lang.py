#!/usr/bin/env python3
from __future__ import annotations
import json, os, pathlib, shutil, subprocess, sys
P=pathlib.Path

PREFIX="/data/data/studio.ocean.app/files/usr"
PROVIDERS={
"cargo":{
 "install":["install"],"uninstall":["uninstall"],"search":["search"],"list":["install","--list"],
 "update":["update"],"tree":["tree"],"metadata":["metadata"],"vendor":["vendor"],
 "package":["package"],"publish-dryrun":["publish","--dry-run"]},
"rust-toolchain":{
 "install":[],"uninstall":[],"list":[],"use":[],"latest":[],"which":[],"current":[],"outdated":[],"upgrade":[],"doctor":[]},
"go":{
 "install":["install"],"get":["get"],"list":["list"],"env":["env"],"mod-download":["mod","download"],
 "mod-tidy":["mod","tidy"],"mod-graph":["mod","graph"],"work-sync":["work","sync"],
 "clean-cache":["clean","-cache"],"version":["version"]},
"gem":{
 "install":["install"],"uninstall":["uninstall"],"list":["list"],"search":["search"],"update":["update"],
 "outdated":["outdated"],"which":["which"],"contents":["contents"],"environment":["environment"],"cleanup":["cleanup"]},
"bundler":{
 "install":["install"],"update":["update"],"exec":["exec"],"check":["check"],"list":["list"],
 "show":["show"],"lock":["lock"],"config":["config"],"cache":["cache"],"doctor":["doctor"]},
"composer":{
 "require":["require"],"remove":["remove"],"install":["install"],"update":["update"],"show":["show"],
 "search":["search"],"outdated":["outdated"],"exec":["exec"],"audit":["audit"],"diagnose":["diagnose"]},
"luarocks":{
 "install":["install"],"remove":["remove"],"list":["list"],"search":["search"],"show":["show"],
 "make":["make"],"build":["build"],"pack":["pack"],"purge":["purge"],"config":["config"]},
"dotnet":{
 "tool-install":["tool","install"],"tool-uninstall":["tool","uninstall"],"tool-list":["tool","list"],"tool-update":["tool","update"],
 "add-package":["add","package"],"remove-package":["remove","package"],"list-package":["list","package"],
 "restore":["restore"],"build":["build"],"run":["run"]},
"nuget":{
 "add-source":["nuget","add","source"],"remove-source":["nuget","remove","source"],"update-source":["nuget","update","source"],
 "enable-source":["nuget","enable","source"],"disable-source":["nuget","disable","source"],"list-source":["nuget","list","source"],
 "locals":["nuget","locals"],"push":["nuget","push"],"verify":["nuget","verify"],"sign":["nuget","sign"]},
"swiftpm":{
 "resolve":["package","resolve"],"update":["package","update"],"show-dependencies":["package","show-dependencies"],
 "describe":["package","describe"],"dump-package":["package","dump-package"],"clean":["package","clean"],
 "reset":["package","reset"],"edit":["package","edit"],"unedit":["package","unedit"],"compute-checksum":["package","compute-checksum"]},
}
COMMANDS={f"ecosys-{provider}-{op}":(provider,op) for provider,ops in PROVIDERS.items() for op in ops}
assert len(COMMANDS)==100 and len(set(COMMANDS))==100

DIRECT={
 "cargo":"cargo","rust-toolchain":"mise","go":"go","gem":"gem","bundler":"bundle",
 "composer":"composer","luarocks":"luarocks","dotnet":"dotnet","nuget":"dotnet","swiftpm":"swift"
}
MISE_TOOL={
 "cargo":"rust","go":"go","gem":"ruby","bundler":"ruby","composer":"composer",
 "dotnet":"dotnet","nuget":"dotnet","swiftpm":"swift"
}

def emit(x):
    print(json.dumps(x,indent=2,ensure_ascii=False,default=str) if isinstance(x,(dict,list,tuple)) else x)
def die(msg,code=2):
    print(msg,file=sys.stderr);raise SystemExit(code)
def find(name):return shutil.which(name)

def rust_args(op,args):
    a=list(args)
    if op=="install":
        target=(a.pop(0) if a else "latest")
        return ["install",f"rust@{target}",*a]
    if op=="uninstall":
        if not a:die("VERSION required, e.g. ecosys-rust-toolchain-uninstall 1.90.0")
        target=a.pop(0);return ["uninstall",f"rust@{target}",*a]
    if op=="list":return ["ls","rust",*a]
    if op=="use":
        target=(a.pop(0) if a else "latest");return ["use",f"rust@{target}",*a]
    if op=="latest":return ["latest","rust",*a]
    if op=="which":return ["which","rust",*a]
    if op=="current":return ["current","rust",*a]
    if op=="outdated":return ["outdated","rust",*a]
    if op=="upgrade":return ["upgrade","rust",*a]
    return ["doctor",*a]

def op_argv(provider,op,args):
    if provider=="rust-toolchain":return rust_args(op,args)
    return PROVIDERS[provider][op]+list(args)

def preferred(provider):
    if provider=="rust-toolchain":
        return {"binary":"mise","fallback_tool":None}
    return {"binary":DIRECT[provider],"fallback_tool":MISE_TOOL.get(provider)}

def resolve_base(provider):
    direct=find(DIRECT[provider])
    if direct:return [direct],{"mode":"direct","binary":direct}
    if provider=="rust-toolchain":
        die("mise is required for Rust toolchain management")
    if provider=="luarocks":
        die("luarocks backend unavailable; install the Ocean luarocks package")
    mise=find("mise")
    tool=MISE_TOOL.get(provider)
    if mise and tool:
        binary=DIRECT[provider]
        return [mise,"exec",tool+"@latest","--",binary],{"mode":"mise","tool":tool+"@latest","binary":binary}
    die(f"{provider} backend unavailable. Install mise or the native manager.")

def plan(cmd,args):
    provider,op=COMMANDS[cmd]
    p=preferred(provider)
    return {"package":cmd,"provider":provider,"operation":op,"preferred_binary":p["binary"],
            "mise_fallback_tool":(p["fallback_tool"]+"@latest" if p["fallback_tool"] else None),
            "operation_argv":op_argv(provider,op,args),"prefix":PREFIX}

def main():
    cmd=P(sys.argv[0]).name;args=sys.argv[1:]
    if cmd not in COMMANDS:
        if args and args[0] in COMMANDS:cmd=args.pop(0)
        elif not args or args[0] in ("-h","--help"):
            print("Ocean Foundation shard 41 — compiled/language package ecosystems")
            print("\n".join(COMMANDS));return
        else:die("unknown command")
    if args and args[0] in ("-h","--help"):
        provider,op=COMMANDS[cmd]
        print(f"{cmd} — {provider} {op}; forwards remaining arguments to the ecosystem manager");return
    dry=False
    if "--plan" in args:
        args=[x for x in args if x!="--plan"];dry=True
    p=plan(cmd,args)
    if dry or os.environ.get("OCEAN_FOUNDATION_PLAN")=="1":
        emit(p);return
    provider,op=COMMANDS[cmd]
    base,_=resolve_base(provider)
    raise SystemExit(subprocess.run(base+op_argv(provider,op,args)).returncode)

if __name__=="__main__":main()
