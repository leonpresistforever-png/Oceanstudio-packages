#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, shutil, subprocess, tempfile
from pathlib import Path

PREFIX="/data/data/studio.ocean.app/files/usr"
VERSION="1.0.0-1"

def pip_family(name, dist, exe, ver=("--version",)):
    return {
      name:("piprun",dist,exe,[]),
      name+"-help":("piprun",dist,exe,["--help"]),
      name+"-version":("piprun",dist,exe,list(ver)),
      name+"-install":("pipx-install",dist,exe,[]),
      name+"-upgrade":("pipx-upgrade",dist,exe,[])
    }

def npm_family(name, spec, exe=None):
    exe=exe or name
    return {
      name:("npmrun",spec,exe,[]),
      name+"-help":("npmrun",spec,exe,["--help"]),
      name+"-version":("npmrun",spec,exe,["--version"]),
      name+"-install":("npm-install",spec,exe,[]),
      name+"-upgrade":("npm-upgrade",spec,exe,[])
    }

def add(dst,fam):
    if set(dst)&set(fam):raise RuntimeError("duplicate family")
    dst.update(fam)

AI={}
for x in [
 ("crewai","crewai","crewai",("--version",)),
 ("langgraph","langgraph-cli","langgraph",("--version",)),
 ("chromadb","chromadb","chroma",("--version",)),
 ("rich-cli","rich-cli","rich",("--version",)),
 ("aider","aider-chat","aider",("--version",)),
 ("open-interpreter","open-interpreter","interpreter",("--version",)),
 ("huggingface-cli","huggingface-hub","hf",("version",)),
 ("gradio","gradio","gradio",("--version",)),
 ("streamlit","streamlit","streamlit",("version",)),
 ("dvc","dvc","dvc",("version",)),
 ("mlflow","mlflow","mlflow",("--version",)),
 ("datasette","datasette","datasette",("--version",)),
 ("prefect","prefect","prefect",("version",)),
 ("dagster","dagster","dagster",("--version",)),
 ("bentoml","bentoml","bentoml",("--version",)),
 ("modal","modal","modal",("--version",)),
 ("chainlit","chainlit","chainlit",("--version",)),
 ("zenml","zenml","zenml",("version",)),
 ("kedro","kedro","kedro",("--version",)),
 ("openai","openai","openai",("--version",))
]: add(AI,pip_family(*x))

DEV={}
for x in [
 ("pytest","pytest","pytest",("--version",)),
 ("tox","tox","tox",("--version",)),
 ("nox","nox","nox",("--version",)),
 ("pre-commit","pre-commit","pre-commit",("--version",)),
 ("hatch","hatch","hatch",("--version",)),
 ("copier","copier","copier",("--version",)),
 ("mkdocs","mkdocs","mkdocs",("--version",)),
 ("sphinx","sphinx","sphinx-build",("--version",)),
 ("httpie","httpie","http",("--version",)),
 ("poetry","poetry","poetry",("--version",)),
 ("pdm","pdm","pdm",("--version",)),
 ("typer","typer","typer",("--version",)),
 ("invoke","invoke","invoke",("--version",)),
 ("watchfiles","watchfiles","watchfiles",("--version",)),
 ("ipython","ipython","ipython",("--version",)),
 ("jupyterlab","jupyterlab","jupyter-lab",("--version",))
]: add(DEV,pip_family(*x))
for x in [("pyright","pyright","pyright"),("eslint","eslint","eslint"),("prettier","prettier","prettier"),("vite","vite","vite")]:
    add(DEV,npm_family(*x))

OPS={
"text":["lower","upper","strip","normalize","lines","words","chars","bytes","unique-lines","sort-lines","reverse-lines","head","tail","sha256","md5","slug","emails","urls","redact-emails","json-quote"],
"json":["validate","pretty","compact","keys","values","length","type","get","has","sort-keys","jsonl-count","jsonl-pretty","jsonl-head","jsonl-tail","jsonl-keys","jsonl-dedupe","to-jsonl","array-first","array-last","hash"],
"file":["stat","size","sha256","md5","lines","words","head","tail","exists","is-file","is-dir","basename","dirname","suffix","stem","resolve","permissions","newer","copy-plan","manifest"],
"repo":["files","dirs","tree","extensions","largest","smallest","newest","oldest","duplicates","readmes","licenses","todos","fixmes","python-files","js-files","json-files","yaml-files","markdown-files","total-bytes","manifest"],
"ai":["prompt-stats","prompt-hash","prompt-json","system-message","user-message","assistant-message","template-vars","fence","chunk-chars","chunk-words","chunk-lines","openai-chat-json","openai-response-json","openai-base-url","openai-auth-check","openai-curl-models","openai-curl-chat","mcp-initialize-json","mcp-tools-list-json","mcp-config-check"]
}
CUSTOM={"aiutil-"+g+"-"+op:("custom","", "", [g,op]) for g,items in OPS.items() for op in items}
assert len(AI)==100 and len(DEV)==100 and len(CUSTOM)==100
assert len(set(AI)|set(DEV)|set(CUSTOM))==300

SHARDS={
 "46":(AI,"staging/shard-46","ai-agent-ecosystem-suite","devel","AI agent, RAG, ML and terminal ecosystem"),
 "47":(DEV,"staging/shard-47","coding-ecosystem-suite","devel","coding, testing, docs and web-development ecosystem"),
 "48":(CUSTOM,"staging/shard-48","ai-pipeline-utility-suite","utils","self-contained AI and data pipeline utilities")
}
SUPERPACK="ocean-ai-dev-superpack"

RUNTIME=r'''#!/usr/bin/env python3
import collections,hashlib,json,os,pathlib,re,shlex,shutil,sys
P=pathlib.Path
def inp(a):
 p=P(a[0]) if a else None
 return p.read_text(errors="replace") if p and p.exists() else (a[0] if a else sys.stdin.read())
def emit(x):
 print(json.dumps(x,indent=2,ensure_ascii=False,default=str) if isinstance(x,(dict,list,tuple,bool,int,float)) else x)
def jget(x,path):
 cur=x
 for k in path.split("."):
  cur=cur[int(k)] if isinstance(cur,list) else cur[k]
 return cur
def allfiles(root):
 return [x for x in P(root).rglob("*") if x.is_file()]
def main(g,o,a):
 if g=="text":
  s=inp(a);L=s.splitlines()
  if o=="lower":emit(s.lower());return
  if o=="upper":emit(s.upper());return
  if o=="strip":emit(s.strip());return
  if o=="normalize":emit(" ".join(s.split()));return
  if o=="lines":emit(len(L));return
  if o=="words":emit(len(s.split()));return
  if o=="chars":emit(len(s));return
  if o=="bytes":emit(len(s.encode()));return
  if o=="unique-lines":emit("\n".join(dict.fromkeys(L)));return
  if o=="sort-lines":emit("\n".join(sorted(L)));return
  if o=="reverse-lines":emit("\n".join(reversed(L)));return
  if o=="head":emit("\n".join(L[:int(a[1]) if len(a)>1 else 10]));return
  if o=="tail":emit("\n".join(L[-(int(a[1]) if len(a)>1 else 10):]));return
  if o=="sha256":emit(hashlib.sha256(s.encode()).hexdigest());return
  if o=="md5":emit(hashlib.md5(s.encode()).hexdigest());return
  if o=="slug":emit(re.sub(r"-+","-",re.sub(r"[^a-z0-9]+","-",s.lower())).strip("-"));return
  if o=="emails":emit(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",s));return
  if o=="urls":emit(re.findall(r"https?://[^\s<>'\"]+",s));return
  if o=="redact-emails":emit(re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}","[REDACTED_EMAIL]",s));return
  if o=="json-quote":print(json.dumps(s));return
 if g=="json":
  s=inp(a)
  if o.startswith("jsonl-"):
   rows=[json.loads(x) for x in s.splitlines() if x.strip()]
   if o=="jsonl-count":emit(len(rows));return
   if o=="jsonl-pretty":emit(rows);return
   if o=="jsonl-head":emit(rows[:int(a[1]) if len(a)>1 else 10]);return
   if o=="jsonl-tail":emit(rows[-(int(a[1]) if len(a)>1 else 10):]);return
   if o=="jsonl-keys":emit(sorted({k for r in rows if isinstance(r,dict) for k in r}));return
   if o=="jsonl-dedupe":
    seen=set();out=[]
    for r in rows:
     k=json.dumps(r,sort_keys=True)
     if k not in seen:seen.add(k);out.append(r)
    emit(out);return
  x=json.loads(s)
  if o=="validate":emit(True);return
  if o=="pretty":emit(x);return
  if o=="compact":print(json.dumps(x,separators=(",",":")));return
  if o=="keys":emit(list(x.keys()) if isinstance(x,dict) else []);return
  if o=="values":emit(list(x.values()) if isinstance(x,dict) else []);return
  if o=="length":emit(len(x));return
  if o=="type":emit(type(x).__name__);return
  if o=="get":emit(jget(x,a[1]));return
  if o=="has":
   try:jget(x,a[1]);emit(True)
   except Exception:emit(False)
   return
  if o=="sort-keys":print(json.dumps(x,indent=2,sort_keys=True));return
  if o=="to-jsonl":
   for r in x:print(json.dumps(r,separators=(",",":")))
   return
  if o=="array-first":emit(x[0] if x else None);return
  if o=="array-last":emit(x[-1] if x else None);return
  if o=="hash":emit(hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest());return
 if g=="file":
  p=P(a[0] if a else ".");s=p.read_text(errors="replace") if p.is_file() else ""
  if o=="stat":st=p.stat();emit({"path":str(p),"bytes":st.st_size,"mode":oct(st.st_mode&511),"mtime":st.st_mtime});return
  if o=="size":emit(p.stat().st_size);return
  if o=="sha256":emit(hashlib.sha256(p.read_bytes()).hexdigest());return
  if o=="md5":emit(hashlib.md5(p.read_bytes()).hexdigest());return
  if o=="lines":emit(len(s.splitlines()));return
  if o=="words":emit(len(s.split()));return
  if o=="head":emit("\n".join(s.splitlines()[:int(a[1]) if len(a)>1 else 10]));return
  if o=="tail":emit("\n".join(s.splitlines()[-(int(a[1]) if len(a)>1 else 10):]));return
  if o=="exists":emit(p.exists());return
  if o=="is-file":emit(p.is_file());return
  if o=="is-dir":emit(p.is_dir());return
  if o=="basename":emit(p.name);return
  if o=="dirname":emit(str(p.parent));return
  if o=="suffix":emit(p.suffix);return
  if o=="stem":emit(p.stem);return
  if o=="resolve":emit(str(p.resolve()));return
  if o=="permissions":emit(oct(p.stat().st_mode&511));return
  if o=="newer":emit(p.stat().st_mtime>P(a[1]).stat().st_mtime);return
  if o=="copy-plan":emit({"source":str(p.resolve()),"destination":str(P(a[1]).resolve()),"bytes":p.stat().st_size});return
  if o=="manifest":emit({"path":str(p),"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()});return
 if g=="repo":
  root=P(a[0] if a else ".");F=allfiles(root)
  rel=lambda x:str(x.relative_to(root))
  if o=="files":emit([rel(x) for x in F]);return
  if o=="dirs":emit([str(x.relative_to(root)) for x in root.rglob("*") if x.is_dir()]);return
  if o=="tree":emit([str(x.relative_to(root)) for x in sorted(root.rglob("*"))]);return
  if o=="extensions":emit(dict(collections.Counter(x.suffix or "<none>" for x in F).most_common()));return
  if o=="largest":emit([{"path":rel(x),"bytes":x.stat().st_size} for x in sorted(F,key=lambda z:z.stat().st_size,reverse=True)[:20]]);return
  if o=="smallest":emit([{"path":rel(x),"bytes":x.stat().st_size} for x in sorted(F,key=lambda z:z.stat().st_size)[:20]]);return
  if o=="newest":emit(rel(max(F,key=lambda z:z.stat().st_mtime)) if F else "");return
  if o=="oldest":emit(rel(min(F,key=lambda z:z.stat().st_mtime)) if F else "");return
  if o=="duplicates":
   d={}
   for x in F:d.setdefault(hashlib.sha256(x.read_bytes()).hexdigest(),[]).append(rel(x))
   emit([v for v in d.values() if len(v)>1]);return
  if o=="readmes":emit([rel(x) for x in F if x.name.lower().startswith("readme")]);return
  if o=="licenses":emit([rel(x) for x in F if x.name.lower().startswith(("license","copying"))]);return
  if o in ("todos","fixmes"):
   needle=o[:-1].upper();out=[]
   for x in F:
    try:
     for i,line in enumerate(x.read_text(errors="replace").splitlines()):
      if needle in line.upper():out.append({"file":rel(x),"line":i+1,"text":line.strip()})
    except:pass
   emit(out);return
  extmap={"python-files":{".py"},"js-files":{".js",".mjs",".cjs",".ts",".tsx",".jsx"},"json-files":{".json",".jsonl"},"yaml-files":{".yaml",".yml"},"markdown-files":{".md",".mdx"}}
  if o in extmap:emit([rel(x) for x in F if x.suffix.lower() in extmap[o]]);return
  if o=="total-bytes":emit(sum(x.stat().st_size for x in F));return
  if o=="manifest":emit([{"path":rel(x),"bytes":x.stat().st_size,"sha256":hashlib.sha256(x.read_bytes()).hexdigest()} for x in F]);return
 if g=="ai":
  s=inp(a);base=os.environ.get("OPENAI_BASE_URL","https://api.openai.com/v1").rstrip("/");key=bool(os.environ.get("OPENAI_API_KEY"))
  if o=="prompt-stats":emit({"chars":len(s),"words":len(s.split()),"lines":len(s.splitlines()),"bytes":len(s.encode())});return
  if o=="prompt-hash":emit(hashlib.sha256(s.encode()).hexdigest());return
  if o=="prompt-json":emit({"prompt":s});return
  if o in ("system-message","user-message","assistant-message"):emit({"role":o.split("-")[0],"content":s});return
  if o=="template-vars":emit(sorted(set(re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}",s))));return
  if o=="fence":emit(chr(96)*3+"\n"+s.rstrip()+"\n"+chr(96)*3);return
  if o.startswith("chunk-"):
   n=int(a[1]) if len(a)>1 and a[1].isdigit() else 1000
   if o=="chunk-chars":emit([s[i:i+n] for i in range(0,len(s),n)]);return
   if o=="chunk-words":
    w=s.split();emit([" ".join(w[i:i+n]) for i in range(0,len(w),n)]);return
   L=s.splitlines();emit(["\n".join(L[i:i+n]) for i in range(0,len(L),n)]);return
  model=a[0] if a else os.environ.get("OPENAI_MODEL","gpt-5");prompt=" ".join(a[1:]) if len(a)>1 else ""
  chat={"model":model,"messages":[{"role":"user","content":prompt}]};resp={"model":model,"input":prompt}
  if o=="openai-chat-json":emit(chat);return
  if o=="openai-response-json":emit(resp);return
  if o=="openai-base-url":emit(base);return
  if o=="openai-auth-check":emit(key);return
  if o=="openai-curl-models":emit("curl -sS "+shlex.quote(base+"/models")+" -H "+shlex.quote("Authorization: Bearer $OPENAI_API_KEY"));return
  if o=="openai-curl-chat":emit("curl -sS "+shlex.quote(base+"/chat/completions")+" -H "+shlex.quote("Authorization: Bearer $OPENAI_API_KEY")+" -H 'Content-Type: application/json' -d "+shlex.quote(json.dumps(chat)));return
  if o=="mcp-initialize-json":emit({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2026-07-28","capabilities":{},"clientInfo":{"name":"ocean-aiutil","version":"1"}}});return
  if o=="mcp-tools-list-json":emit({"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}});return
  if o=="mcp-config-check":
   try:x=json.loads(s);emit({"valid":isinstance(x,dict) and isinstance(x.get("mcpServers",{}),dict),"servers":len(x.get("mcpServers",{}))})
   except Exception:emit({"valid":False,"servers":0})
   return
 raise SystemExit("unsupported operation "+g+"/"+o)
if __name__=="__main__":main(sys.argv[1],sys.argv[2],sys.argv[3:])
'''

def q(x):return "'" + str(x).replace("'","'\"'\"'") + "'"
def launch(pkg,spec):
 r,d,e,a=spec;fixed=" ".join(q(x) for x in a)
 if r=="custom":return '#!/system/bin/sh\nP="$PREFIX"\n[ -n "$P" ] || P="'+PREFIX+'"\nexec "$P/bin/python" "$P/lib/ocean-ai-dev/'+pkg+'.py" '+q(a[0])+' '+q(a[1])+' "$@"\n'
 if r=="piprun":return '#!/system/bin/sh\nexec pipx run --spec '+q(d)+' '+q(e)+' '+fixed+' "$@"\n'
 if r=="pipx-install":return '#!/system/bin/sh\nexec pipx install '+q(d)+' "$@"\n'
 if r=="pipx-upgrade":return '#!/system/bin/sh\nexec pipx upgrade '+q(d)+' "$@"\n'
 if r=="npmrun":return '#!/system/bin/sh\nexec npm exec --yes --package='+q(d)+' -- '+q(e)+' '+fixed+' "$@"\n'
 if r=="npm-install":return '#!/system/bin/sh\nexec npm install -g '+q(d)+' "$@"\n'
 if r=="npm-upgrade":return '#!/system/bin/sh\nexec npm install -g '+q(d+'@latest')+' "$@"\n'
 raise RuntimeError(r)
def deps(spec):
 return ["pipx","python"] if spec[0].startswith("pip") else ["npm","nodejs"] if spec[0].startswith("npm") else ["python"]
def ctrl(pkg,spec,section,label):
 upstream="self-contained Ocean utility" if spec[0]=="custom" else "isolated upstream "+spec[1]+" launcher"
 return f"Package: {pkg}\nVersion: {VERSION}\nArchitecture: all\nMaintainer: OceanStudio <packages@ocean.studio>\nSection: {section}\nPriority: optional\nDepends: {', '.join(deps(spec))}\nDescription: {label} - {pkg}\n Functional {upstream}. APT installation itself performs no network access.\n"
def metactrl(pkg,names,desc):
 return f"Package: {pkg}\nVersion: {VERSION}\nArchitecture: all\nMaintainer: OceanStudio <packages@ocean.studio>\nSection: metapackages\nPriority: optional\nDepends: {', '.join(x+' (= '+VERSION+')' for x in names)}\nDescription: {desc}\n Installs the complete Ocean capability shard.\n"
def existing():
 paths=subprocess.check_output(["git","ls-tree","-r","--name-only","HEAD"],text=True).splitlines();skip=("staging/shard-46/","staging/shard-47/","staging/shard-48/","staging/ai-dev-superpack/");out=set()
 for x in paths:
  if x.endswith(".deb") and not x.startswith(skip):out.add(Path(x).name.split("_",1)[0])
 return out
def build(pkg,spec,pool,section,label):
 with tempfile.TemporaryDirectory() as td:
  root=Path(td)/pkg;debian=root/"DEBIAN";bind=root/PREFIX.strip("/")/"bin";debian.mkdir(parents=True);bind.mkdir(parents=True)
  (debian/"control").write_text(ctrl(pkg,spec,section,label));p=bind/pkg;p.write_text(launch(pkg,spec));p.chmod(0o755)
  if spec[0]=="custom":
   lib=root/PREFIX.strip("/")/"lib/ocean-ai-dev";lib.mkdir(parents=True);r=lib/(pkg+".py");r.write_text(RUNTIME);r.chmod(0o755)
  art=pool/f"{pkg}_{VERSION}_all.deb";subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(art)],check=True,stdout=subprocess.DEVNULL);return art
def buildmeta(pkg,names,pool,desc):
 with tempfile.TemporaryDirectory() as td:
  root=Path(td)/pkg;(root/"DEBIAN").mkdir(parents=True);(root/"DEBIAN/control").write_text(metactrl(pkg,names,desc));art=pool/f"{pkg}_{VERSION}_all.deb";subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(art)],check=True,stdout=subprocess.DEVNULL);return art
def row(art,pkg,spec):
 b=art.read_bytes();return {"package":pkg,"artifact":art.name,"runner":spec[0],"upstream":spec[1] or None,"command":spec[2] or None,"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
def writeidx(out,rows):
 z=[]
 for r in rows:
  a=out/"pool/main"/r["artifact"];f=subprocess.check_output(["dpkg-deb","-f",str(a)],text=True).strip();z.append(f+f"\nFilename: {out.as_posix()}/pool/main/{a.name}\nSize: {r['bytes']}\nSHA256: {r['sha256']}\n")
 (out/"Packages.repaired").write_text("\n".join(z))
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--shards",default="46,47,48");ns=ap.parse_args();nums=[x.strip() for x in ns.shards.split(",") if x.strip()];seen=existing();suites=[];total=0
 for n in nums:
  cat,path,suite,section,label=SHARDS[n];names=list(cat);col=sorted((set(names)|{suite})&seen)
  if len(names)!=100 or col:raise SystemExit("shard "+n+" invalid/colliding: "+", ".join(col))
  out=Path(path);pool=out/"pool/main"
  if out.exists():shutil.rmtree(out)
  pool.mkdir(parents=True);rows=[row(build(p,s,pool,section,label),p,s) for p,s in cat.items()];rows.append(row(buildmeta(suite,names,pool,"Ocean "+label+" suite"),suite,("meta","","",[])));writeidx(out,rows)
  (out/"provenance.json").write_text(json.dumps({"schemaVersion":1,"shard":n,"version":VERSION,"prefix":PREFIX,"commandCount":100,"packageCount":101,"suite":suite,"networkAtAptInstall":False,"rootRequired":False,"packages":rows},indent=2)+"\n");seen.update(names);seen.add(suite);suites.append(suite);total+=101
 out=Path("staging/ai-dev-superpack");pool=out/"pool/main"
 if out.exists():shutil.rmtree(out)
 pool.mkdir(parents=True)
 if SUPERPACK in seen:raise SystemExit("superpack collision")
 r=row(buildmeta(SUPERPACK,suites,pool,"Ocean AI and developer ecosystem superpack"),SUPERPACK,("meta","","",[]));writeidx(out,[r]);(out/"provenance.json").write_text(json.dumps({"schemaVersion":1,"version":VERSION,"dependsOn":suites,"commandCount":300,"totalNewPackages":304},indent=2)+"\n")
 print(json.dumps({"commands":300,"metaPackages":4,"totalNewPackages":total+1,"shards":nums},indent=2))
if __name__=="__main__":main()
