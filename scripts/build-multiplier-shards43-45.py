#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, subprocess, tempfile
from pathlib import Path

PREFIX="/data/data/studio.ocean.app/files/usr"
VERSION="1.0.0-1"

# Shard 43: 100 agent/MCP/ecosystem multipliers.
AGENT={}
def add(name,provider,*argv):
    if name in AGENT: raise RuntimeError("duplicate "+name)
    AGENT[name]=(provider,list(argv))

# Requested parent tools + their useful subcommands.
for name,provider,args in [
("npx","npx",()),("npx-exec","npx",()),("npx-create","npx",("create",)),("npx-package","npx",("--package",)),("npx-yes","npx",("--yes",)),("npx-version","npx",("--version",)),("npx-help","npx",("--help",)),("npm-exec-tool","npm",("exec","--")),("npm-view-tool","npm",("view",)),("npm-search-tool","npm",("search",)),
("uv","uv",()),("uvx","uvx",()),("uv-run","uv",("run",)),("uv-sync","uv",("sync",)),("uv-add","uv",("add",)),("uv-remove","uv",("remove",)),("uv-lock","uv",("lock",)),("uv-tree","uv",("tree",)),("uv-tool-install","uv",("tool","install")),("uv-python-list","uv",("python","list")),
("fastmcp","fastmcp",()),("fastmcp-run","fastmcp",("run",)),("fastmcp-dev","fastmcp",("dev",)),("fastmcp-version","fastmcp",("--version",)),("fastmcp-help","fastmcp",("--help",)),("fastmcp-via-uvx","fastmcp-uvx",()),("fastmcp-via-pipx","fastmcp-pipx",()),("fastmcp-install-local","pipx",("install","fastmcp")),("fastmcp-upgrade-local","pipx",("upgrade","fastmcp")),("fastmcp-uninstall-local","pipx",("uninstall","fastmcp")),
("apm","apm",()),("apm-init","apm",("init",)),("apm-install","apm",("install",)),("apm-update","apm",("update",)),("apm-audit","apm",("audit",)),("apm-pack","apm",("pack",)),("apm-run","apm",("run",)),("apm-compile","apm",("compile",)),("apm-mcp-install","apm",("install","--mcp")),("apm-marketplace","apm",("marketplace",)),
("claude-code","claude",()),("claude-mcp-add","claude",("mcp","add")),("claude-mcp-list","claude",("mcp","list")),("claude-mcp-remove","claude",("mcp","remove")),("claude-mcp-get","claude",("mcp","get")),("claude-print","claude",("-p",)),("claude-resume","claude",("--resume",)),("claude-continue","claude",("--continue",)),("claude-version","claude",("--version",)),("claude-help","claude",("--help",)),
("codex-cli","codex",()),("codex-mcp-add","codex",("mcp","add")),("codex-mcp-list","codex",("mcp","list")),("codex-mcp-remove","codex",("mcp","remove")),("codex-mcp-get","codex",("mcp","get")),("codex-exec","codex",("exec",)),("codex-resume","codex",("resume",)),("codex-login","codex",("login",)),("codex-version","codex",("--version",)),("codex-help","codex",("--help",)),
]:
    add(name,provider,*args)

for op in ["run","install","uninstall","list","upgrade","upgrade-all","inject","uninject","reinstall","runpip"]:
    add("pipx-"+op+"-tool","pipx",op)
for name,args in [
("gh-repo-clone",("repo","clone")),("gh-repo-view",("repo","view")),("gh-pr-list",("pr","list")),("gh-pr-view",("pr","view")),("gh-issue-list",("issue","list")),("gh-issue-view",("issue","view")),("gh-release-list",("release","list")),("gh-release-view",("release","view")),("gh-workflow-list",("workflow","list")),("gh-run-list",("run","list"))]:
    add(name,"gh",*args)
for op in ["config-lint","config-list","config-add","config-remove","jsonrpc-request","http-probe","stdio-probe","env-check","server-template","manifest-init"]:
    add("mcp-"+op,"mcp-native",op)
for op in ["audit","outdated","cache","doctor","pack","publish-dryrun","init","prefix","config","query"]:
    argv=("publish","--dry-run") if op=="publish-dryrun" else (op,)
    add("npm-"+op+"-tool","npm",*argv)

# Shard 44: 100 concrete developer/data/build subcommands, 10 per provider.
DEV={}
def adddev(name,provider,*argv):
    DEV[name]=(provider,list(argv))
for op,args in {
"status":("status",),"log":("log",),"diff":("diff",),"branch":("branch",),"remote":("remote",),"tag":("tag",),"grep":("grep",),"show":("show",),"ls-files":("ls-files",),"clean-dryrun":("clean","-nd")}.items(): adddev("devx-git-"+op,"git",*args)
for op,args in {
"head":("-I",),"follow":("-L",),"download":("-L","-O"),"json":("-H","Accept: application/json"),"verbose":("-v",),"compressed":("--compressed",),"headers":("-D","-"),"http2":("--http2",),"fail":("--fail-with-body",),"silent":("-sS",)}.items(): adddev("devx-curl-"+op,"curl",*args)
for op,args in {
"pretty":(".",),"compact":("-c","."),"sort-keys":("--sort-keys","."),"slurp":("-s","."),"raw":("-r",),"keys":("keys",),"length":("length",),"type":("type",),"paths":("paths",),"empty":("-e",".")}.items(): adddev("devx-jq-"+op,"jq",*args)
for op,args in {
"version":("version",),"rand":("rand",),"sha256":("dgst","-sha256"),"sha512":("dgst","-sha512"),"base64":("base64",),"x509-text":("x509","-text","-noout"),"s-client":("s_client",),"ciphers":("ciphers",),"speed":("speed",),"pkey":("pkey",)}.items(): adddev("devx-openssl-"+op,"openssl",*args)
for op,args in {
"version":("--version",),"schema":(".schema",),"tables":(".tables",),"dump":(".dump",),"integrity":("PRAGMA integrity_check;",),"indexes":(".indexes",),"dbinfo":(".dbinfo",),"databases":(".databases",),"query":(),"csv":("-csv",)}.items(): adddev("devx-sqlite-"+op,"sqlite3",*args)
for op,provider,args in [
("version","ffmpeg",("-version",)),("formats","ffmpeg",("-formats",)),("codecs","ffmpeg",("-codecs",)),("filters","ffmpeg",("-filters",)),("hwaccels","ffmpeg",("-hwaccels",)),("devices","ffmpeg",("-devices",)),("probe-json","ffprobe",("-v","quiet","-print_format","json","-show_format","-show_streams")),("probe-streams","ffprobe",("-v","quiet","-show_streams")),("probe-format","ffprobe",("-v","quiet","-show_format")),("benchmark","ffmpeg",("-benchmark",))]:
    adddev("devx-ffmpeg-"+op,provider,*args)
for op,args in {
"list":("list",),"badging":("dump","badging"),"permissions":("dump","permissions"),"resources":("dump","resources"),"configurations":("dump","configurations"),"xmltree":("dump","xmltree"),"xmlstrings":("dump","xmlstrings"),"package":("package",),"version":("version",),"add":("add",)}.items(): adddev("devx-aapt-"+op,"aapt",*args)
for op,args in {
"list":("-tf",),"extract":("-xf",),"create":("-cf",),"gzip":("-czf",),"bzip2":("-cjf",),"xz":("-cJf",),"compare":("--compare","-f"),"append":("-rf",),"update":("-uf",),"verbose-list":("-tvf",)}.items(): adddev("devx-tar-"+op,"tar",*args)
for name,provider,args in [
("devx-zip-create","zip",()),("devx-zip-recurse","zip",("-r",)),("devx-zip-update","zip",("-u",)),("devx-zip-delete","zip",("-d",)),("devx-zip-test","unzip",("-t",)),("devx-unzip-list","unzip",("-l",)),("devx-unzip-extract","unzip",()),("devx-unzip-pipe","unzip",("-p",)),("devx-zipinfo-list","zipinfo",()),("devx-zipinfo-long","zipinfo",("-l",))]: adddev(name,provider,*args)
for op,args in {
"download":(),"output":("-O",),"continue":("-c",),"mirror":("--mirror",),"spider":("--spider",),"recursive":("-r",),"quiet":("-q",),"server-response":("-S",),"no-clobber":("-nc",),"timestamping":("-N",)}.items(): adddev("devx-wget-"+op,"wget",*args)

# Shard 45: 100 self-contained Python utilities.
GROUPS={
"hash":["sha256","sha1","md5","blake2b","crc32","text-sha256","verify-sha256","size","lines","bytes"],
"text":["lines","words","chars","head","tail","sort","unique","grep","replace","join"],
"json":["validate","pretty","compact","keys","get","merge","diff","jsonl-count","sort-keys","path-exists"],
"url":["parse","encode","decode","join","query-parse","query-build","host","scheme","normalize","resolve"],
"semver":["parse","compare","bump-major","bump-minor","bump-patch","major","minor","patch","normalize","is-valid"],
"csv":["rows","columns","head","to-json","from-json","select","sort","unique","dialect","stats"],
"fs":["stat","tree","find-name","find-ext","find-large","duplicates","newest","oldest","permissions","relative"],
"net":["dns","ip-parse","cidr-info","port-check","tcp-send","http-head","http-get","url-status","localhost","hostname"],
"encode":["b64-encode","b64-decode","hex-encode","hex-decode","urlsafe-b64-encode","urlsafe-b64-decode","gzip-encode","gzip-decode","json-escape","shell-quote"],
"config":["ini-get","ini-list","toml-validate","toml-get","env-get","env-list","dotenv-parse","dotenv-get","path-split","which"],
}
CUSTOM={"util-"+g+"-"+op:("custom",[g,op]) for g,ops in GROUPS.items() for op in ops}

assert len(AGENT)==100 and len(DEV)==100 and len(CUSTOM)==100
assert len(set(AGENT)|set(DEV)|set(CUSTOM))==300

SHARDS={
"43":(AGENT,"staging/shard-43","agent-mcp-multiplier-suite","devel","AI agent, MCP and ecosystem multipliers"),
"44":(DEV,"staging/shard-44","developer-tool-multiplier-suite","utils","developer, data, network and build multipliers"),
"45":(CUSTOM,"staging/shard-45","portable-utility-multiplier-suite","utils","portable Python utility multipliers"),
}
SUPERPACK="ocean-multiplier-superpack"

DEPS={
"npx":["npm"],"npm":["npm"],"uv":["mise"],"uvx":["mise"],"fastmcp":["python","pipx","mise"],"fastmcp-uvx":["mise"],"fastmcp-pipx":["pipx"],
"apm":["python","pipx"],"claude":["npm"],"codex":["npm"],"pipx":["pipx"],"gh":["gh"],"mcp-native":["python","curl"],
"git":["git"],"curl":["curl"],"jq":["jq"],"openssl":["openssl"],"sqlite3":["sqlite"],"ffmpeg":["ffmpeg"],"ffprobe":["ffmpeg"],"aapt":["aapt"],"tar":["tar"],
"zip":["zip"],"unzip":["unzip"],"zipinfo":["unzip"],"wget":["wget"],"custom":["python"],
}

MCP_RUNTIME=r'''#!/usr/bin/env python3
import json,os,pathlib,subprocess,sys,urllib.request
def load(p):
 p=pathlib.Path(p); return json.loads(p.read_text()) if p.exists() else {}
def save(p,o):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(o,indent=2)+"\n")
def main(op,a):
 cfg=a[0] if a and a[0].endswith(".json") else os.path.expanduser("~/.config/ocean/mcp.json"); r=a[1:] if a and a[0].endswith(".json") else a
 if op=="config-lint":
  o=load(cfg);assert isinstance(o,dict);print(json.dumps({"valid":True,"servers":len(o.get("mcpServers",{}))},indent=2));return
 if op=="config-list": print("\n".join(sorted(load(cfg).get("mcpServers",{}))));return
 if op=="config-add":
  if len(r)<2: raise SystemExit("NAME COMMAND [ARG...]")
  o=load(cfg);o.setdefault("mcpServers",{})[r[0]]={"command":r[1],"args":r[2:]};save(cfg,o);print(r[0]);return
 if op=="config-remove":
  o=load(cfg);print("removed" if o.setdefault("mcpServers",{}).pop(r[0],None) is not None else "absent");save(cfg,o);return
 if op=="jsonrpc-request":
  print(json.dumps({"jsonrpc":"2.0","id":1,"method":r[0] if r else "initialize","params":json.loads(r[1]) if len(r)>1 else {}}));return
 if op=="http-probe":
  q=urllib.request.Request(r[0],headers={"Accept":"application/json, text/event-stream"});x=urllib.request.urlopen(q,timeout=10);print(json.dumps({"status":x.status,"content_type":x.headers.get("content-type")},indent=2));return
 if op=="stdio-probe":
  p=subprocess.Popen(r,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);msg=json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2026-07-28","capabilities":{},"clientInfo":{"name":"ocean-probe","version":"1"}}})+"\n";out,err=p.communicate(msg,timeout=8);print(out.strip() or err.strip());return
 if op=="env-check": print(json.dumps({x:bool(os.environ.get(x)) for x in (r or ["PATH","HOME","OPENAI_API_KEY","ANTHROPIC_API_KEY"])},indent=2));return
 if op=="server-template": print(json.dumps({"mcpServers":{r[0] if r else "ocean-server":{"command":"python","args":["server.py"]}}},indent=2));return
 if op=="manifest-init": save(r[0] if r else "mcp.json",{"mcpServers":{}});return
 raise SystemExit("unknown MCP operation")
if __name__=="__main__": main(sys.argv[1],sys.argv[2:])
'''

UTIL_RUNTIME=r'''#!/usr/bin/env python3
import base64,configparser,csv,difflib,gzip,hashlib,ipaddress,json,os,pathlib,re,shlex,shutil,socket,sys,urllib.parse,urllib.request,zlib
P=pathlib.Path
def inp(a,b=False):
 if not a:return sys.stdin.buffer.read() if b else sys.stdin.read()
 p=P(a[0])
 if p.exists():return p.read_bytes() if b else p.read_text(errors="replace")
 return a[0].encode() if b else a[0]
def emit(x):print(json.dumps(x,indent=2,ensure_ascii=False,default=str) if isinstance(x,(dict,list,tuple)) else x)
def sem(v):
 m=re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+]([0-9A-Za-z.-]+))?",v.strip())
 if not m:raise ValueError("invalid semver")
 return int(m[1]),int(m[2]),int(m[3]),m[4] or ""
def main(g,o,a):
 if g=="hash":
  r=inp(a,True)
  if o in ("sha256","sha1","md5","blake2b"):emit(getattr(hashlib,o)(r).hexdigest());return
  if o=="crc32":emit(f"{zlib.crc32(r)&0xffffffff:08x}");return
  if o=="text-sha256":emit(hashlib.sha256(" ".join(a).encode()).hexdigest());return
  if o=="verify-sha256":emit(hashlib.sha256(P(a[0]).read_bytes()).hexdigest()==a[1].lower());return
  if o in ("size","bytes"):emit(len(r));return
  if o=="lines":s=inp(a);emit(len(s.splitlines()));return
 if g=="text":
  s=inp(a);L=s.splitlines()
  if o=="lines":emit(len(L));return
  if o=="words":emit(len(s.split()));return
  if o=="chars":emit(len(s));return
  if o=="head":emit("\n".join(L[:int(a[1]) if len(a)>1 else 10]));return
  if o=="tail":emit("\n".join(L[-(int(a[1]) if len(a)>1 else 10):]));return
  if o=="sort":emit("\n".join(sorted(L)));return
  if o=="unique":emit("\n".join(dict.fromkeys(L)));return
  if o=="grep":emit("\n".join(x for x in L if re.search(a[1] if len(a)>1 else "",x)));return
  if o=="replace":emit(s.replace(a[1],a[2]));return
  if o=="join":emit((a[1] if len(a)>1 else " ").join(L));return
 if g=="json":
  s=inp(a);x=json.loads(s)
  if o=="validate":emit(True);return
  if o=="pretty":emit(x);return
  if o=="compact":print(json.dumps(x,separators=(",",":")));return
  if o=="keys":emit(sorted(x) if isinstance(x,dict) else []);return
  if o in ("get","path-exists"):
   cur=x;ok=True
   for k in (a[1].split(".") if len(a)>1 else []):
    try:cur=cur[int(k)] if isinstance(cur,list) else cur[k]
    except Exception:ok=False;cur=None;break
   emit(ok if o=="path-exists" else cur);return
  if o=="merge":
   y=json.loads(inp(a[1:]));z=dict(x);z.update(y);emit(z);return
  if o=="diff":
   y=json.loads(inp(a[1:]));print("\n".join(difflib.unified_diff(json.dumps(x,indent=2,sort_keys=True).splitlines(),json.dumps(y,indent=2,sort_keys=True).splitlines(),lineterm="")));return
  if o=="jsonl-count":emit(sum(1 for q in s.splitlines() if q.strip() and json.loads(q) is not None));return
  if o=="sort-keys":print(json.dumps(x,indent=2,sort_keys=True));return
 if g=="url":
  u=a[0] if a else sys.stdin.read().strip();p=urllib.parse.urlparse(u)
  if o=="parse":emit({"scheme":p.scheme,"host":p.hostname,"port":p.port,"path":p.path,"query":p.query,"fragment":p.fragment});return
  if o=="encode":emit(urllib.parse.quote(u,safe=""));return
  if o=="decode":emit(urllib.parse.unquote(u));return
  if o=="join":emit(urllib.parse.urljoin(u,a[1]));return
  if o=="query-parse":emit(urllib.parse.parse_qs(p.query or u));return
  if o=="query-build":emit(urllib.parse.urlencode(dict(x.split("=",1) for x in a)));return
  if o=="host":emit(p.hostname or "");return
  if o=="scheme":emit(p.scheme);return
  if o=="normalize":emit(urllib.parse.urlunparse((p.scheme.lower(),p.netloc.lower(),p.path or "/",p.params,p.query,"")));return
  if o=="resolve":emit(socket.gethostbyname(p.hostname or u));return
 if g=="semver":
  v=a[0] if a else "0.0.0"
  try:x=sem(v)
  except Exception:
   if o=="is-valid":emit(False);return
   raise
  if o=="is-valid":emit(True);return
  if o=="parse":emit({"major":x[0],"minor":x[1],"patch":x[2],"suffix":x[3]});return
  if o=="compare":y=sem(a[1]);emit(-1 if x[:3]<y[:3] else 1 if x[:3]>y[:3] else 0);return
  if o.startswith("bump-"):
   A,B,C=x[:3];k=o[5:];A,B,C=(A+1,0,0) if k=="major" else (A,B+1,0) if k=="minor" else (A,B,C+1);emit(f"{A}.{B}.{C}");return
  if o in ("major","minor","patch"):emit(x[{"major":0,"minor":1,"patch":2}[o]]);return
  if o=="normalize":emit(f"{x[0]}.{x[1]}.{x[2]}"+("-"+x[3] if x[3] else ""));return
 if g=="csv":
  s=inp(a);R=list(csv.reader(s.splitlines()))
  if o=="rows":emit(len(R));return
  if o=="columns":emit(max((len(r) for r in R),default=0));return
  if o=="head":emit(R[:int(a[1]) if len(a)>1 else 5]);return
  if o=="to-json":emit(list(csv.DictReader(s.splitlines())));return
  if o=="from-json":
   arr=json.loads(s);keys=sorted({k for r in arr for k in r});w=csv.DictWriter(sys.stdout,fieldnames=keys);w.writeheader();w.writerows(arr);return
  if o=="select":I=[int(x) for x in a[1].split(",")];emit([[r[i] if i<len(r) else "" for i in I] for r in R]);return
  if o=="sort":emit(sorted(R));return
  if o=="unique":emit(list(dict.fromkeys(tuple(r) for r in R)));return
  if o=="dialect":emit({"delimiter":csv.Sniffer().sniff(s[:2048]).delimiter});return
  if o=="stats":emit({"rows":len(R),"columns":max((len(r) for r in R),default=0),"bytes":len(s.encode())});return
 if g=="fs":
  p=P(a[0] if a else ".")
  if o=="stat":emit({"path":str(p),"size":p.stat().st_size,"mode":oct(p.stat().st_mode&0o777),"mtime":p.stat().st_mtime});return
  if o=="tree":emit([str(x.relative_to(p)) for x in sorted(p.rglob("*"))]);return
  F=[x for x in p.rglob("*") if x.is_file()] if p.is_dir() else [p]
  if o=="find-name":emit([str(x) for x in F if a[1] in x.name]);return
  if o=="find-ext":emit([str(x) for x in F if x.suffix==a[1]]);return
  if o=="find-large":emit([str(x) for x in F if x.stat().st_size>=int(a[1] if len(a)>1 else 1048576)]);return
  if o=="duplicates":
   d={}
   for x in F:d.setdefault(hashlib.sha256(x.read_bytes()).hexdigest(),[]).append(str(x))
   emit([v for v in d.values() if len(v)>1]);return
  if o=="newest":emit(str(max(F,key=lambda x:x.stat().st_mtime)) if F else "");return
  if o=="oldest":emit(str(min(F,key=lambda x:x.stat().st_mtime)) if F else "");return
  if o=="permissions":emit(oct(p.stat().st_mode&0o777));return
  if o=="relative":emit(os.path.relpath(p,a[1] if len(a)>1 else "."));return
 if g=="net":
  t=a[0] if a else "localhost"
  if o=="dns":emit(socket.gethostbyname_ex(t));return
  if o=="ip-parse":x=ipaddress.ip_address(t);emit({"version":x.version,"private":x.is_private});return
  if o=="cidr-info":x=ipaddress.ip_network(t,strict=False);emit({"network":str(x.network_address),"broadcast":str(x.broadcast_address),"num_addresses":x.num_addresses});return
  if o=="port-check":s=socket.socket();s.settimeout(3);c=s.connect_ex((t,int(a[1])));s.close();emit(c==0);return
  if o=="tcp-send":s=socket.create_connection((t,int(a[1])),timeout=5);s.sendall((a[2] if len(a)>2 else "").encode());sys.stdout.buffer.write(s.recv(65536));s.close();return
  if o in ("http-head","http-get","url-status"):
   m="HEAD" if o!="http-get" else "GET";r=urllib.request.urlopen(urllib.request.Request(t,method=m),timeout=10);emit(r.status if o=="url-status" else {"status":r.status,"headers":dict(r.headers)} if o=="http-head" else r.read().decode(errors="replace"));return
  if o=="localhost":emit(socket.gethostbyname("localhost"));return
  if o=="hostname":emit(socket.gethostname());return
 if g=="encode":
  r=inp(a,True)
  if o=="b64-encode":sys.stdout.write(base64.b64encode(r).decode());return
  if o=="b64-decode":sys.stdout.buffer.write(base64.b64decode(r));return
  if o=="hex-encode":sys.stdout.write(r.hex());return
  if o=="hex-decode":sys.stdout.buffer.write(bytes.fromhex(r.decode().strip()));return
  if o=="urlsafe-b64-encode":sys.stdout.write(base64.urlsafe_b64encode(r).decode());return
  if o=="urlsafe-b64-decode":sys.stdout.buffer.write(base64.urlsafe_b64decode(r));return
  if o=="gzip-encode":sys.stdout.buffer.write(gzip.compress(r));return
  if o=="gzip-decode":sys.stdout.buffer.write(gzip.decompress(r));return
  if o=="json-escape":print(json.dumps(r.decode(errors="replace")));return
  if o=="shell-quote":emit(shlex.quote(r.decode(errors="replace")));return
 if g=="config":
  if o.startswith("ini-"):
   c=configparser.ConfigParser();c.read(a[0])
   if o=="ini-list":emit({s:dict(c[s]) for s in c.sections()});return
   emit(c.get(a[1],a[2]));return
  if o.startswith("toml-"):
   import tomllib;x=tomllib.loads(P(a[0]).read_text())
   if o=="toml-validate":emit(True);return
   cur=x
   for k in a[1].split("."):cur=cur[k]
   emit(cur);return
  if o=="env-get":emit(os.environ.get(a[0],""));return
  if o=="env-list":emit(dict(sorted(os.environ.items())));return
  if o.startswith("dotenv-"):
   d={}
   for line in P(a[0]).read_text().splitlines():
    if line.strip() and not line.lstrip().startswith("#") and "=" in line:
     k,v=line.split("=",1);d[k.strip()]=v.strip().strip("'\"")
   emit(d if o=="dotenv-parse" else d.get(a[1],""));return
  if o=="path-split":emit(os.environ.get("PATH","").split(os.pathsep));return
  if o=="which":emit(shutil.which(a[0]) or "");return
 raise SystemExit("unsupported operation")
if __name__=="__main__":main(sys.argv[1],sys.argv[2],sys.argv[3:])
'''

def shquote(x): return "'" + x.replace("'","'\"'\"'") + "'"

def deps(provider): return DEPS[provider]

def script_for(pkg,provider,args):
    fixed=" ".join(shquote(x) for x in args)
    if provider=="custom":
        return '#!/system/bin/sh\nPREFIX="$PREFIX"\n[ -n "$PREFIX" ] || PREFIX="'+PREFIX+'"\nexec "$PREFIX/bin/python" "$PREFIX/lib/ocean-multipliers/'+pkg+'.py" '+shquote(args[0])+' '+shquote(args[1])+' "$@"\n'
    if provider=="mcp-native":
        return '#!/system/bin/sh\nPREFIX="$PREFIX"\n[ -n "$PREFIX" ] || PREFIX="'+PREFIX+'"\nexec "$PREFIX/bin/python" "$PREFIX/lib/ocean-multipliers/'+pkg+'.py" '+shquote(args[0])+' "$@"\n'
    if provider=="npx":
        return '#!/system/bin/sh\nif command -v npx >/dev/null 2>&1; then exec npx '+fixed+' "$@"; fi\nexec npm exec -- '+fixed+' "$@"\n'
    if provider=="uv":
        return '#!/system/bin/sh\nif command -v uv >/dev/null 2>&1; then exec uv '+fixed+' "$@"; fi\nexec mise exec uv@latest -- uv '+fixed+' "$@"\n'
    if provider=="uvx":
        return '#!/system/bin/sh\nif command -v uvx >/dev/null 2>&1; then exec uvx "$@"; fi\nif command -v uv >/dev/null 2>&1; then exec uv tool run "$@"; fi\nexec mise exec uv@latest -- uvx "$@"\n'
    if provider=="fastmcp":
        return '#!/system/bin/sh\nif command -v fastmcp >/dev/null 2>&1; then exec fastmcp '+fixed+' "$@"; fi\nif command -v pipx >/dev/null 2>&1; then exec pipx run fastmcp '+fixed+' "$@"; fi\nexec mise exec uv@latest -- uvx fastmcp '+fixed+' "$@"\n'
    if provider=="fastmcp-uvx":
        return '#!/system/bin/sh\nif command -v uvx >/dev/null 2>&1; then exec uvx fastmcp "$@"; fi\nexec mise exec uv@latest -- uvx fastmcp "$@"\n'
    if provider=="fastmcp-pipx":
        return '#!/system/bin/sh\nexec pipx run fastmcp "$@"\n'
    if provider=="apm":
        return '#!/system/bin/sh\nif command -v apm >/dev/null 2>&1; then exec apm '+fixed+' "$@"; fi\nexec pipx run --spec apm-cli apm '+fixed+' "$@"\n'
    if provider=="claude":
        return '#!/system/bin/sh\nif command -v claude >/dev/null 2>&1; then exec claude '+fixed+' "$@"; fi\nexec npm exec --yes --package=@anthropic-ai/claude-code@latest -- claude '+fixed+' "$@"\n'
    if provider=="codex":
        return '#!/system/bin/sh\nif command -v codex >/dev/null 2>&1; then exec codex '+fixed+' "$@"; fi\nexec npm exec --yes --package=@openai/codex@latest -- codex '+fixed+' "$@"\n'
    return '#!/system/bin/sh\nexec '+shquote(provider)+' '+fixed+' "$@"\n'

def control(pkg,provider,section,desc):
    return f"Package: {pkg}\nVersion: {VERSION}\nArchitecture: all\nMaintainer: OceanStudio <packages@ocean.studio>\nSection: {section}\nPriority: optional\nDepends: {', '.join(deps(provider))}\nDescription: {desc} ({pkg})\n Functional OceanStudio multiplier package. It performs a concrete operation and has no network activity during apt installation.\n"

def meta_control(pkg,ds,desc):
    return f"Package: {pkg}\nVersion: {VERSION}\nArchitecture: all\nMaintainer: OceanStudio <packages@ocean.studio>\nSection: metapackages\nPriority: optional\nDepends: "+", ".join(f"{x} (= {VERSION})" for x in ds)+f"\nDescription: {desc}\n Installs the complete Ocean multiplier capability set.\n"

def build_one(pkg,provider,args,pool,section,desc):
    with tempfile.TemporaryDirectory(prefix="ocean-mult-") as td:
        root=Path(td)/pkg;deb=root/"DEBIAN";binp=root/PREFIX.strip("/")/"bin";lib=root/PREFIX.strip("/")/"lib/ocean-multipliers"
        deb.mkdir(parents=True);binp.mkdir(parents=True);lib.mkdir(parents=True)
        (deb/"control").write_text(control(pkg,provider,section,desc))
        exe=binp/pkg;exe.write_text(script_for(pkg,provider,args));exe.chmod(0o755)
        if provider in ("custom","mcp-native"):
            py=lib/(pkg+".py");py.write_text(UTIL_RUNTIME if provider=="custom" else MCP_RUNTIME);py.chmod(0o755)
        art=pool/f"{pkg}_{VERSION}_all.deb"
        subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(art)],check=True,stdout=subprocess.DEVNULL)
        return art

def build_meta(pkg,ds,pool,desc):
    with tempfile.TemporaryDirectory(prefix="ocean-meta-") as td:
        root=Path(td)/pkg;(root/"DEBIAN").mkdir(parents=True)
        (root/"DEBIAN/control").write_text(meta_control(pkg,ds,desc))
        art=pool/f"{pkg}_{VERSION}_all.deb"
        subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(art)],check=True,stdout=subprocess.DEVNULL)
        return art

def row(art,pkg,provider):
    b=art.read_bytes();return {"package":pkg,"artifact":art.name,"provider":provider,"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}

def live_names():
    p=Path("apt/dists/stable/main/binary-aarch64/Packages")
    return set(re.findall(r"^Package:\s*(\S+)",p.read_text(errors="replace"),re.M))

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--shards",default="43,44,45");a=ap.parse_args()
    nums=[x.strip() for x in a.shards.split(",") if x.strip()]
    wanted=set()
    for n in nums:
        cmds,out,suite,section,desc=SHARDS[n];wanted.update(cmds);wanted.add(suite)
    wanted.add(SUPERPACK)
    col=sorted(wanted&live_names())
    if col:raise SystemExit("live package collisions: "+", ".join(col))
    suites=[];total=0
    for n in nums:
        cmds,out,suite,section,desc=SHARDS[n];out=Path(out);pool=out/"pool/main"
        if out.exists():shutil.rmtree(out)
        pool.mkdir(parents=True)
        rows=[]
        for pkg,(provider,args) in cmds.items():
            art=build_one(pkg,provider,args,pool,section,desc);rows.append(row(art,pkg,provider))
        art=build_meta(suite,list(cmds),pool,desc+" suite");rows.append(row(art,suite,"meta"))
        (out/"provenance.json").write_text(json.dumps({"schemaVersion":1,"shard":n,"version":VERSION,"prefix":PREFIX,"commandCount":100,"packageCount":101,"suite":suite,"networkAtAptInstall":False,"rootRequired":False,"packages":rows},indent=2)+"\n")
        suites.append(suite);total+=101
    out=Path("staging/multiplier-superpack");pool=out/"pool/main"
    if out.exists():shutil.rmtree(out)
    pool.mkdir(parents=True)
    art=build_meta(SUPERPACK,suites,pool,"Ocean multiplier superpack")
    (out/"provenance.json").write_text(json.dumps({"schemaVersion":1,"version":VERSION,"prefix":PREFIX,"dependsOn":suites,"commandCount":300,"totalNewPackages":304},indent=2)+"\n")
    total+=1
    print(json.dumps({"commands":300,"suitePackages":3,"superpack":1,"totalNewPackages":total,"shards":nums},indent=2))
if __name__=="__main__":main()
