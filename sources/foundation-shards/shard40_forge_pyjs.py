#!/usr/bin/env python3
from __future__ import annotations
import json, os, pathlib, shutil, subprocess, sys
P=pathlib.Path

PREFIX="/data/data/studio.ocean.app/files/usr"
PROVIDERS={
"pip":{
 "install":["install"],"uninstall":["uninstall"],"list":["list"],"show":["show"],
 "index-versions":["index","versions"],"freeze":["freeze"],"check":["check"],
 "download":["download"],"wheel":["wheel"],"cache":["cache"]},
"uv":{
 "tool-install":["tool","install"],"tool-uninstall":["tool","uninstall"],"tool-list":["tool","list"],
 "python-install":["python","install"],"python-list":["python","list"],"pip-install":["pip","install"],
 "pip-list":["pip","list"],"run":["run"],"sync":["sync"],"cache":["cache"]},
"pipx":{
 "install":["install"],"uninstall":["uninstall"],"list":["list"],"run":["run"],
 "upgrade":["upgrade"],"upgrade-all":["upgrade-all"],"inject":["inject"],"uninject":["uninject"],
 "reinstall":["reinstall"],"ensurepath":["ensurepath"]},
"poetry":{
 "add":["add"],"remove":["remove"],"install":["install"],"update":["update"],"show":["show"],
 "run":["run"],"env-info":["env","info"],"lock":["lock"],"build":["build"],"check":["check"]},
"pdm":{
 "add":["add"],"remove":["remove"],"install":["install"],"update":["update"],"list":["list"],
 "run":["run"],"lock":["lock"],"sync":["sync"],"build":["build"],"info":["info"]},
"npm":{
 "install":["install"],"uninstall":["uninstall"],"list":["list"],"search":["search"],"outdated":["outdated"],
 "update":["update"],"exec":["exec"],"view":["view"],"cache":["cache"],"doctor":["doctor"]},
"pnpm":{
 "add":["add"],"remove":["remove"],"list":["list"],"search":["search"],"outdated":["outdated"],
 "update":["update"],"exec":["exec"],"dlx":["dlx"],"store":["store"],"why":["why"]},
"yarn":{
 "add":["add"],"remove":["remove"],"up":["up"],"why":["why"],"dlx":["dlx"],"exec":["exec"],
 "info":["info"],"config":["config"],"workspaces":["workspaces"],"cache-clean":["cache","clean"]},
"bun":{
 "add":["add"],"remove":["remove"],"install":["install"],"update":["update"],"outdated":["outdated"],
 "x":["x"],"run":["run"],"pm":["pm"],"link":["link"],"unlink":["unlink"]},
"deno":{
 "install":["install"],"uninstall":["uninstall"],"add":["add"],"remove":["remove"],"run":["run"],
 "task":["task"],"cache":["cache"],"info":["info"],"compile":["compile"],"fmt":["fmt"]},
}
COMMANDS={f"forge-{provider}-{op}":(provider,op) for provider,ops in PROVIDERS.items() for op in ops}
assert len(COMMANDS)==100 and len(set(COMMANDS))==100

MISE_TOOL={
 "pip":"python","uv":"uv","pipx":"pipx","poetry":"poetry","pdm":"pdm",
 "npm":"node","pnpm":"pnpm","yarn":"yarn","bun":"bun","deno":"deno"
}
DIRECT={"pip":"pip","uv":"uv","pipx":"pipx","poetry":"poetry","pdm":"pdm","npm":"npm","pnpm":"pnpm","yarn":"yarn","bun":"bun","deno":"deno"}

def emit(x):
    print(json.dumps(x,indent=2,ensure_ascii=False,default=str) if isinstance(x,(dict,list,tuple)) else x)

def die(msg,code=2):
    print(msg,file=sys.stderr);raise SystemExit(code)

def find(name): return shutil.which(name)

def base(provider):
    direct=find(DIRECT[provider])
    if direct:return [direct],{"mode":"direct","binary":direct}
    if provider=="pip":
        py=find("python") or find("python3")
        if py:return [py,"-m","pip"],{"mode":"python-module","binary":py,"module":"pip"}
    if provider in ("poetry","pdm"):
        px=find("pipx")
        if px:return [px,"run",provider],{"mode":"pipx-run","binary":px,"package":provider}
    if provider in ("pnpm","yarn"):
        npx=find("npx")
        if npx:return [npx,"--yes",provider+"@latest"],{"mode":"npx","binary":npx,"package":provider+"@latest"}
    mise=find("mise")
    if mise:
        tool=MISE_TOOL[provider]
        binary=DIRECT[provider]
        if provider=="pip":
            return [mise,"exec","python@latest","--","python","-m","pip"],{"mode":"mise","tool":"python@latest","binary":"python -m pip"}
        return [mise,"exec",tool+"@latest","--",binary],{"mode":"mise","tool":tool+"@latest","binary":binary}
    die(f"{provider} backend unavailable. Install mise or the native manager.")

def plan(cmd,args):
    provider,op=COMMANDS[cmd]
    return {
      "package":cmd,"provider":provider,"operation":op,
      "preferred_binary":DIRECT[provider],
      "mise_fallback_tool":MISE_TOOL[provider]+"@latest",
      "operation_argv":PROVIDERS[provider][op]+list(args),
      "prefix":PREFIX
    }

def main():
    cmd=P(sys.argv[0]).name
    args=sys.argv[1:]
    if cmd not in COMMANDS:
        if args and args[0] in COMMANDS:cmd=args.pop(0)
        elif not args or args[0] in ("-h","--help"):
            print("Ocean Foundation shard 40 — Python/JavaScript ecosystem package managers")
            print("\n".join(COMMANDS));return
        else:die("unknown command")
    if args and args[0] in ("-h","--help"):
        provider,op=COMMANDS[cmd]
        print(f"{cmd} — {provider} {op}; forwards remaining arguments to the native ecosystem manager");return
    dry=False
    if "--plan" in args:
        args=[x for x in args if x!="--plan"];dry=True
    p=plan(cmd,args)
    if dry or os.environ.get("OCEAN_FOUNDATION_PLAN")=="1":
        emit(p);return
    provider,op=COMMANDS[cmd]
    prefix,_backend=base(provider)
    argv=prefix+PROVIDERS[provider][op]+list(args)
    raise SystemExit(subprocess.run(argv).returncode)

if __name__=="__main__":main()
