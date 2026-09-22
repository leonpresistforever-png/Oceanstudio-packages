#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,shutil,subprocess,tempfile
from pathlib import Path
PREFIX="/data/data/studio.ocean.app/files/usr"
VERSION="1.0.0-1"

G49={
"vector":["dot","cosine","norm","normalize","dims","topk","mean","sum","min","max"],
"rag":["chunk-chars","chunk-words","chunk-lines","overlap","dedupe","rank","context","citations","manifest","stats"],
"prompt":["vars","render","roles","messages","compact","hash","estimate","json","join","stats"],
"jsonl":["count","head","tail","validate","dedupe","sample","shuffle","split","keys","stats"],
"json":["pretty","compact","keys","get","merge","equal","validate","to-jsonl","from-jsonl","stats"],
"csv":["rows","cols","head","to-json","from-json","select","dedupe","sort","header","stats"],
"markdown":["headings","links","images","codeblocks","toc","strip","words","sections","frontmatter","stats"],
"text":["normalize","lines","words","ngrams","keywords","emails","urls","redact","unique-lines","stats"],
"files":["sha256","size","lines","mime","extension","newest","largest","manifest","duplicates","stats"],
"eval":["exact","contains","regex","overlap","jaccard","length-delta","json-equal","list-overlap","passrate","stats"],
}
G50={
"python":["syntax","imports","functions","classes","todos","complexity","docstrings","ast-types","lines","stats"],
"javascript":["imports","exports","functions","classes","todos","requires","scripts","deps","devdeps","stats"],
"project":["detect","files","dirs","extensions","readme","licenses","configs","entrypoints","largest","stats"],
"tests":["discover","python","javascript","coverage","snapshots","fixtures","reports","flaky","names","stats"],
"docs":["files","headings","local-links","codeblocks","todos","readme","changelog","licenses","words","stats"],
"semver":["validate","compare","bump-major","bump-minor","bump-patch","major","minor","patch","normalize","range"],
"diff":["unified","added","removed","ratio","checksum","json-equal","word-diff","line-count","changed","stats"],
"manifest":["files","hashes","sizes","executables","symlinks","extensions","json","verify","compare","stats"],
"archive":["names","format","test","unsafe","duplicates","entries","compressed-size","raw-size","ratio","stats"],
"git":["branch","head","root","status","tracked","untracked","changed","tags","remotes","stats"],
}
G51={
"http":["status","headers","text","json","latency","final-url","content-type","length","head","download"],
"url":["parse","encode","decode","join","query-parse","query-build","normalize","domain","scheme","basename"],
"dns":["resolve","reverse","hostname","fqdn","localhost","addrinfo","canonical","service-port","port-service","stats"],
"tcp":["check","time","send","recv","resolve","service","common-ports","family","host","stats"],
"jsonrpc":["request","notify","response","error","batch","validate","methods","ids","pretty","line"],
"log":["lines","levels","errors","warnings","timestamps","json","grep","tail","top","stats"],
"metric":["avg","min","max","sum","count","p50","p90","p95","p99","stats"],
"trace":["new-trace","new-span","parse-parent","make-parent","duration","sort","critical","errors","services","stats"],
"tls":["pem-count","pem-labels","sha256","version","cipher","sans","issuer","expiry","certificate","stats"],
"system":["env","path","which","platform","python","cwd","disk","uname","hostname","stats"],
}
SHARDS={
"49":(G49,"airag","staging/shard-49","ai-rag-data-suite","AI RAG vector and data utilities"),
"50":(G50,"codeops","staging/shard-50","code-repo-automation-suite","code repository test docs and build utilities"),
"51":(G51,"netobs","staging/shard-51","network-observability-suite","API network logs metrics trace and observability utilities"),
}
SUPER="ocean-intelligence-toolkit"

RUNTIME=r'''#!/usr/bin/env python3
import ast,collections,csv,difflib,hashlib,json,math,mimetypes,os,pathlib,platform,random,re,shutil,socket,ssl,statistics,subprocess,sys,time,urllib.parse,urllib.request,zipfile,tarfile
P=pathlib.Path
def emit(x):
 print(json.dumps(x,indent=2,ensure_ascii=False,default=str) if isinstance(x,(dict,list,tuple,bool,int,float)) else x)
def text(a):
 if not a:return sys.stdin.read()
 p=P(a[0]);return p.read_text(errors="replace") if p.exists() else a[0]
def values(a):
 s=text(a).strip()
 try:return json.loads(s)
 except:return [float(x) for x in re.split(r"[,\s]+",s) if x]
def files(root):
 p=P(root);return [x for x in p.rglob("*") if x.is_file()]
def sem(v):
 m=re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+]([0-9A-Za-z.-]+))?",v.strip())
 if not m:raise ValueError("invalid semver")
 return int(m[1]),int(m[2]),int(m[3]),m[4] or ""
def pct(a,p):
 a=sorted(a)
 if not a:return None
 k=(len(a)-1)*p;i=int(k);j=min(i+1,len(a)-1);return a[i]+(a[j]-a[i])*(k-i)
def git(*a):return subprocess.check_output(["git",*a],text=True,stderr=subprocess.DEVNULL).strip()
def main(pref,g,o,a):
 if pref=="airag":
  if g=="vector":
   x=[float(v) for v in values(a)]
   if o=="dims":emit(len(x));return
   if o in ("min","max","sum"):emit({"min":min,"max":max,"sum":sum}[o](x) if x else None);return
   if o=="norm":emit(math.sqrt(sum(v*v for v in x)));return
   if o=="normalize":
    n=math.sqrt(sum(v*v for v in x));emit([v/n for v in x] if n else x);return
   if o=="mean":emit(statistics.fmean(x) if x else None);return
   if o=="topk":emit(sorted(enumerate(x),key=lambda z:z[1],reverse=True)[:int(a[1]) if len(a)>1 else 5]);return
   y=[float(v) for v in values(a[1:])]
   if o=="dot":emit(sum(i*j for i,j in zip(x,y)));return
   if o=="cosine":
    nx=math.sqrt(sum(i*i for i in x));ny=math.sqrt(sum(i*i for i in y));emit(sum(i*j for i,j in zip(x,y))/(nx*ny) if nx and ny else 0);return
  if g=="rag":
   s=text(a)
   if o.startswith("chunk-"):
    n=int(a[1]) if len(a)>1 else 500
    seq=list(s) if o=="chunk-chars" else s.split() if o=="chunk-words" else s.splitlines()
    chunks=[seq[i:i+n] for i in range(0,len(seq),n)]
    emit(["".join(x) if o=="chunk-chars" else " ".join(x) if o=="chunk-words" else "\n".join(x) for x in chunks]);return
   if o=="overlap":
    n=int(a[1]) if len(a)>1 else 200;ov=int(a[2]) if len(a)>2 else 40;w=s.split();step=max(1,n-ov);emit([" ".join(w[i:i+n]) for i in range(0,len(w),step) if w[i:i+n]]);return
   if o=="dedupe":emit("\n\n".join(dict.fromkeys(x.strip() for x in re.split(r"\n\s*\n",s) if x.strip())));return
   if o=="rank":
    q=(a[1] if len(a)>1 else "").lower().split();c=[x.strip() for x in re.split(r"\n\s*\n",s) if x.strip()];emit(sorted([{"score":sum(x.lower().count(k) for k in q),"text":x} for x in c],key=lambda z:z["score"],reverse=True));return
   if o=="context":emit({"context":s,"chars":len(s),"words":len(s.split())});return
   if o=="citations":emit([{"id":i+1,"preview":x[:120]} for i,x in enumerate([q for q in re.split(r"\n\s*\n",s) if q.strip()])]);return
   if o=="manifest":
    root=a[0] if a else ".";emit([{"path":str(x),"bytes":x.stat().st_size,"sha256":hashlib.sha256(x.read_bytes()).hexdigest()} for x in files(root)]);return
   if o=="stats":emit({"chars":len(s),"words":len(s.split()),"lines":len(s.splitlines())});return
  if g=="prompt":
   s=text(a)
   if o=="vars":emit(sorted(set(re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}",s))));return
   if o=="render":emit(s.format(**dict(x.split("=",1) for x in a[1:] if "=" in x)));return
   if o=="roles":emit(re.findall(r"(?mi)^(system|user|assistant)\s*:\s*(.*)$",s));return
   if o=="messages":emit([{"role":r.lower(),"content":c} for r,c in re.findall(r"(?mi)^(system|user|assistant)\s*:\s*(.*)$",s)]);return
   if o=="compact":emit(" ".join(s.split()));return
   if o=="hash":emit(hashlib.sha256(s.encode()).hexdigest());return
   if o=="estimate":emit(max(1,round(len(s)/4)));return
   if o=="json":emit({"prompt":s});return
   if o=="join":emit((a[1] if len(a)>1 else "\n").join(s.splitlines()));return
   if o=="stats":emit({"chars":len(s),"words":len(s.split()),"lines":len(s.splitlines()),"tokens":max(1,round(len(s)/4))});return
  if g=="jsonl":
   L=[x for x in text(a).splitlines() if x.strip()];X=[json.loads(x) for x in L]
   if o=="count":emit(len(X));return
   if o=="head":emit(X[:int(a[1]) if len(a)>1 else 10]);return
   if o=="tail":emit(X[-(int(a[1]) if len(a)>1 else 10):]);return
   if o=="validate":emit(True);return
   if o=="dedupe":emit(list({json.dumps(x,sort_keys=True):x for x in X}.values()));return
   if o=="sample":emit(random.Random(0).sample(X,min(int(a[1]) if len(a)>1 else 10,len(X))));return
   if o=="shuffle":
    r=random.Random(int(a[1]) if len(a)>1 else 0);r.shuffle(X);emit(X);return
   if o=="split":
    n=int(len(X)*(float(a[1]) if len(a)>1 else .8));emit({"train":X[:n],"test":X[n:]});return
   if o=="keys":emit(sorted({k for x in X if isinstance(x,dict) for k in x}));return
   if o=="stats":emit({"rows":len(X),"keys":sorted({k for x in X if isinstance(x,dict) for k in x})});return
  if g=="json":
   s=text(a)
   if o=="from-jsonl":emit([json.loads(x) for x in s.splitlines() if x.strip()]);return
   x=json.loads(s)
   if o=="pretty":emit(x);return
   if o=="compact":print(json.dumps(x,separators=(",",":")));return
   if o=="keys":emit(sorted(x) if isinstance(x,dict) else []);return
   if o=="get":
    cur=x
    for k in a[1].split("."):cur=cur[int(k)] if isinstance(cur,list) else cur[k]
    emit(cur);return
   if o=="merge":
    y=json.loads(text(a[1:]));z=dict(x);z.update(y);emit(z);return
   if o=="equal":emit(x==json.loads(text(a[1:])));return
   if o=="validate":emit(True);return
   if o=="to-jsonl":
    for q in x:print(json.dumps(q,separators=(",",":")))
    return
   if o=="stats":emit({"type":type(x).__name__,"size":len(x) if hasattr(x,"__len__") else 1});return
  if g=="csv":
   s=text(a);R=list(csv.reader(s.splitlines()))
   if o=="rows":emit(len(R));return
   if o=="cols":emit(max((len(r) for r in R),default=0));return
   if o=="head":emit(R[:int(a[1]) if len(a)>1 else 5]);return
   if o=="to-json":emit(list(csv.DictReader(s.splitlines())));return
   if o=="from-json":
    arr=json.loads(s);keys=sorted({k for r in arr for k in r});w=csv.DictWriter(sys.stdout,fieldnames=keys);w.writeheader();w.writerows(arr);return
   if o=="select":emit([[r[int(i)] if int(i)<len(r) else "" for i in a[1].split(",")] for r in R]);return
   if o=="dedupe":emit([list(x) for x in dict.fromkeys(tuple(r) for r in R)]);return
   if o=="sort":emit(sorted(R));return
   if o=="header":emit(R[0] if R else []);return
   if o=="stats":emit({"rows":len(R),"cols":max((len(r) for r in R),default=0),"bytes":len(s.encode())});return
  if g=="markdown":
   s=text(a);heads=re.findall(r"(?m)^(#{1,6})\s+(.+)$",s);links=re.findall(r"\[([^\]]*)\]\(([^)]+)\)",s);fence=chr(96)*3;codes=re.findall(re.escape(fence)+r"[^\n]*\n(.*?)"+re.escape(fence),s,re.S)
   if o=="headings":emit([{"level":len(h),"text":t} for h,t in heads]);return
   if o=="links":emit([{"text":t,"url":u} for t,u in links]);return
   if o=="images":emit([{"alt":t,"url":u} for t,u in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)",s)]);return
   if o=="codeblocks":emit(codes);return
   if o=="toc":emit([("  "*(len(h)-1))+"- "+t for h,t in heads]);return
   if o=="strip":emit(re.sub(r"[#*_>~-]","",re.sub(r"\[([^\]]+)\]\([^)]+\)",r"\1",s)));return
   if o=="words":emit(len(s.split()));return
   if o=="sections":emit([t for _,t in heads]);return
   if o=="frontmatter":
    m=re.match(r"^---\s*\n(.*?)\n---\s*\n",s,re.S);emit(m.group(1) if m else "");return
   if o=="stats":emit({"headings":len(heads),"links":len(links),"codeblocks":len(codes),"words":len(s.split())});return
  if g=="text":
   s=text(a)
   if o=="normalize":emit(" ".join(s.split()));return
   if o=="lines":emit(len(s.splitlines()));return
   if o=="words":emit(len(s.split()));return
   if o=="ngrams":
    n=int(a[1]) if len(a)>1 else 2;w=s.split();emit([" ".join(w[i:i+n]) for i in range(len(w)-n+1)]);return
   if o=="keywords":emit(collections.Counter(re.findall(r"[A-Za-z0-9_]+",s.lower())).most_common(int(a[1]) if len(a)>1 else 20));return
   if o=="emails":emit(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",s));return
   if o=="urls":emit(re.findall(r"https?://[^\s<>'\"]+",s));return
   if o=="redact":emit(re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}","[REDACTED_EMAIL]",s));return
   if o=="unique-lines":emit("\n".join(dict.fromkeys(s.splitlines())));return
   if o=="stats":emit({"chars":len(s),"words":len(s.split()),"lines":len(s.splitlines())});return
  if g=="files":
   p=P(a[0] if a else ".");F=files(p) if p.is_dir() else [p]
   if o=="sha256":emit(hashlib.sha256(p.read_bytes()).hexdigest());return
   if o=="size":emit(p.stat().st_size);return
   if o=="lines":emit(len(p.read_text(errors="replace").splitlines()));return
   if o=="mime":emit(mimetypes.guess_type(str(p))[0] or "application/octet-stream");return
   if o=="extension":emit(p.suffix);return
   if o=="newest":emit(str(max(F,key=lambda x:x.stat().st_mtime)) if F else "");return
   if o=="largest":emit([{"path":str(x),"bytes":x.stat().st_size} for x in sorted(F,key=lambda x:x.stat().st_size,reverse=True)[:20]]);return
   if o=="manifest":emit([{"path":str(x),"bytes":x.stat().st_size,"sha256":hashlib.sha256(x.read_bytes()).hexdigest()} for x in F]);return
   if o=="duplicates":
    d={}
    for x in F:d.setdefault(hashlib.sha256(x.read_bytes()).hexdigest(),[]).append(str(x))
    emit([v for v in d.values() if len(v)>1]);return
   if o=="stats":emit({"files":len(F),"bytes":sum(x.stat().st_size for x in F)});return
  if g=="eval":
   if o=="passrate":
    x=values(a);emit(sum(bool(v) for v in x)/len(x) if x else 0);return
   s=text(a);t=text(a[1:])
   if o=="exact":emit(s==t);return
   if o=="contains":emit(t in s);return
   if o=="regex":emit(bool(re.search(t,s)));return
   A=set(s.lower().split());B=set(t.lower().split())
   if o=="overlap":emit(len(A&B));return
   if o=="jaccard":emit(len(A&B)/len(A|B) if A|B else 1);return
   if o=="length-delta":emit(len(s)-len(t));return
   if o=="json-equal":emit(json.loads(s)==json.loads(t));return
   if o=="list-overlap":emit(sorted(set(json.loads(s))&set(json.loads(t))));return
   if o=="stats":emit({"left_chars":len(s),"right_chars":len(t),"jaccard":len(A&B)/len(A|B) if A|B else 1});return
 if pref=="codeops":
  if g=="python":
   s=text(a);T=ast.parse(s)
   if o=="syntax":emit(True);return
   if o=="imports":
    z=[]
    for n in ast.walk(T):
     if isinstance(n,ast.Import):z += [x.name for x in n.names]
     elif isinstance(n,ast.ImportFrom):z.append(n.module or "")
    emit(sorted(set(z)));return
   if o=="functions":emit([n.name for n in ast.walk(T) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]);return
   if o=="classes":emit([n.name for n in ast.walk(T) if isinstance(n,ast.ClassDef)]);return
   if o=="todos":emit([{"line":i+1,"text":x.strip()} for i,x in enumerate(s.splitlines()) if "TODO" in x.upper()]);return
   if o=="complexity":emit(sum(isinstance(n,(ast.If,ast.For,ast.While,ast.Try,ast.BoolOp,ast.Match)) for n in ast.walk(T))+1);return
   if o=="docstrings":emit([ast.get_docstring(n) for n in ast.walk(T) if isinstance(n,(ast.Module,ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and ast.get_docstring(n)]);return
   if o=="ast-types":emit(collections.Counter(type(n).__name__ for n in ast.walk(T)));return
   if o=="lines":emit(len(s.splitlines()));return
   if o=="stats":emit({"lines":len(s.splitlines()),"functions":sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) for n in ast.walk(T)),"classes":sum(isinstance(n,ast.ClassDef) for n in ast.walk(T))});return
  if g=="javascript":
   s=text(a)
   if o=="imports":emit(re.findall(r"(?:import.*?from\s*|require\()\s*['\"]([^'\"]+)",s));return
   if o=="exports":emit(re.findall(r"\bexport\b",s));return
   if o=="functions":emit(len(re.findall(r"\bfunction\b|=>",s)));return
   if o=="classes":emit(re.findall(r"\bclass\s+([A-Za-z_$][\w$]*)",s));return
   if o=="todos":emit([{"line":i+1,"text":x.strip()} for i,x in enumerate(s.splitlines()) if "TODO" in x.upper()]);return
   if o=="requires":emit(re.findall(r"require\(['\"]([^'\"]+)",s));return
   if o in ("scripts","deps","devdeps"):
    x=json.loads(s);emit(x.get({"scripts":"scripts","deps":"dependencies","devdeps":"devDependencies"}[o],{}));return
   if o=="stats":emit({"lines":len(s.splitlines()),"imports":len(re.findall(r"\bimport\b|\brequire\s*\(",s)),"functions":len(re.findall(r"\bfunction\b|=>",s))});return
  if g=="project":
   root=P(a[0] if a else ".");F=files(root)
   if o=="detect":
    marks={"python":["pyproject.toml","requirements.txt"],"node":["package.json"],"rust":["Cargo.toml"],"go":["go.mod"],"java":["pom.xml","build.gradle"]};emit([k for k,v in marks.items() if any((root/x).exists() for x in v)]);return
   if o=="files":emit([str(x.relative_to(root)) for x in F]);return
   if o=="dirs":emit([str(x.relative_to(root)) for x in root.rglob("*") if x.is_dir()]);return
   if o=="extensions":emit(dict(collections.Counter(x.suffix or "<none>" for x in F).most_common()));return
   if o=="readme":emit([str(x.relative_to(root)) for x in F if x.name.lower().startswith("readme")]);return
   if o=="licenses":emit([str(x.relative_to(root)) for x in F if x.name.lower().startswith(("license","copying"))]);return
   if o=="configs":emit([str(x.relative_to(root)) for x in F if x.name.startswith(".") or x.suffix in (".toml",".yaml",".yml",".json",".ini",".cfg")]);return
   if o=="entrypoints":emit([str(x.relative_to(root)) for x in F if x.name in ("main.py","app.py","index.js","main.js","index.ts","main.go","main.rs")]);return
   if o=="largest":emit([{"path":str(x.relative_to(root)),"bytes":x.stat().st_size} for x in sorted(F,key=lambda q:q.stat().st_size,reverse=True)[:20]]);return
   if o=="stats":emit({"files":len(F),"bytes":sum(x.stat().st_size for x in F)});return
  if g=="tests":
   root=P(a[0] if a else ".");F=files(root);T=[x for x in F if re.search(r"(^test_|_test\.|\.test\.|\.spec\.)",x.name)]
   if o=="discover":emit([str(x.relative_to(root)) for x in T]);return
   if o=="python":emit(sum(x.suffix==".py" for x in T));return
   if o=="javascript":emit(sum(x.suffix in (".js",".ts",".jsx",".tsx") for x in T));return
   if o=="coverage":emit([str(x.relative_to(root)) for x in F if "coverage" in x.name.lower()]);return
   if o=="snapshots":emit([str(x.relative_to(root)) for x in F if "snapshot" in x.name.lower()]);return
   if o=="fixtures":emit([str(x.relative_to(root)) for x in F if "fixture" in x.name.lower()]);return
   if o=="reports":emit([str(x.relative_to(root)) for x in F if "report" in x.name.lower()]);return
   if o=="flaky":emit([str(x.relative_to(root)) for x in F if "flaky" in x.read_text(errors="ignore").lower()]);return
   if o=="names":emit([x.name for x in T]);return
   if o=="stats":emit({"tests":len(T),"python":sum(x.suffix==".py" for x in T),"javascript":sum(x.suffix in (".js",".ts",".jsx",".tsx") for x in T)});return
  if g=="docs":
   root=P(a[0] if a else ".");F=[x for x in files(root) if x.suffix.lower() in (".md",".mdx",".rst")];S="\n".join(x.read_text(errors="replace") for x in F)
   if o=="files":emit([str(x.relative_to(root)) for x in F]);return
   if o=="headings":emit(re.findall(r"(?m)^#{1,6}\s+(.+)$",S));return
   if o=="local-links":emit([u for u in re.findall(r"\[[^\]]*\]\(([^)]+)\)",S) if not re.match(r"[a-z]+://|#|mailto:",u)]);return
   if o=="codeblocks":emit(S.count(chr(96)*3)//2);return
   if o=="todos":emit([str(x.relative_to(root)) for x in F if "TODO" in x.read_text(errors="replace").upper()]);return
   if o=="readme":emit([str(x.relative_to(root)) for x in F if x.name.lower().startswith("readme")]);return
   if o=="changelog":emit([str(x.relative_to(root)) for x in F if "changelog" in x.name.lower()]);return
   if o=="licenses":emit([str(x.relative_to(root)) for x in files(root) if x.name.lower().startswith(("license","copying"))]);return
   if o=="words":emit(len(S.split()));return
   if o=="stats":emit({"docs":len(F),"words":len(S.split()),"headings":len(re.findall(r"(?m)^#{1,6}\s+",S))});return
  if g=="semver":
   v=a[0] if a else "0.0.0"
   try:x=sem(v)
   except:
    if o=="validate":emit(False);return
    raise
   if o=="validate":emit(True);return
   if o=="compare":
    y=sem(a[1]);emit(-1 if x[:3]<y[:3] else 1 if x[:3]>y[:3] else 0);return
   if o.startswith("bump-"):
    A,B,C=x[:3];k=o[5:];A,B,C=(A+1,0,0) if k=="major" else (A,B+1,0) if k=="minor" else (A,B,C+1);emit(f"{A}.{B}.{C}");return
   if o in ("major","minor","patch"):emit(x[{"major":0,"minor":1,"patch":2}[o]]);return
   if o=="normalize":emit(f"{x[0]}.{x[1]}.{x[2]}"+("-"+x[3] if x[3] else ""));return
   if o=="range":emit({"min":f"{x[0]}.{x[1]}.{x[2]}","next_major":f"{x[0]+1}.0.0"});return
  if g=="diff":
   s=text(a);t=text(a[1:]);A=s.splitlines();B=t.splitlines();D=list(difflib.unified_diff(A,B,lineterm=""))
   if o=="unified":print("\n".join(D));return
   if o=="added":emit([x[1:] for x in D if x.startswith("+") and not x.startswith("+++")]);return
   if o=="removed":emit([x[1:] for x in D if x.startswith("-") and not x.startswith("---")]);return
   if o=="ratio":emit(difflib.SequenceMatcher(None,s,t).ratio());return
   if o=="checksum":emit({"left":hashlib.sha256(s.encode()).hexdigest(),"right":hashlib.sha256(t.encode()).hexdigest()});return
   if o=="json-equal":emit(json.loads(s)==json.loads(t));return
   if o=="word-diff":emit(list(difflib.ndiff(s.split(),t.split())));return
   if o=="line-count":emit(len(D));return
   if o=="changed":emit(s!=t);return
   if o=="stats":emit({"added":sum(x.startswith("+") and not x.startswith("+++") for x in D),"removed":sum(x.startswith("-") and not x.startswith("---") for x in D)});return
  if g=="manifest":
   root=P(a[0] if a else ".");F=files(root);M=[{"path":str(x.relative_to(root)),"bytes":x.stat().st_size,"sha256":hashlib.sha256(x.read_bytes()).hexdigest(),"executable":os.access(x,os.X_OK),"symlink":x.is_symlink()} for x in F]
   if o=="files":emit([x["path"] for x in M]);return
   if o=="hashes":emit({x["path"]:x["sha256"] for x in M});return
   if o=="sizes":emit({x["path"]:x["bytes"] for x in M});return
   if o=="executables":emit([x["path"] for x in M if x["executable"]]);return
   if o=="symlinks":emit([x["path"] for x in M if x["symlink"]]);return
   if o=="extensions":emit(dict(collections.Counter(P(x["path"]).suffix or "<none>" for x in M).most_common()));return
   if o=="json":emit(M);return
   if o=="verify":
    old=json.loads(text(a[1:]));now={x["path"]:x["sha256"] for x in M};emit(all(now.get(x["path"])==x["sha256"] for x in old));return
   if o=="compare":
    old={x["path"]:x for x in json.loads(text(a[1:]))};now={x["path"]:x for x in M};emit({"added":sorted(now.keys()-old.keys()),"removed":sorted(old.keys()-now.keys()),"changed":sorted(k for k in now.keys()&old.keys() if now[k]["sha256"]!=old[k]["sha256"])});return
   if o=="stats":emit({"files":len(M),"bytes":sum(x["bytes"] for x in M)});return
  if g=="archive":
   p=P(a[0]);N=[];S=[]
   if zipfile.is_zipfile(p):
    with zipfile.ZipFile(p) as z:N=z.namelist();S=[i.file_size for i in z.infolist()];fmt="zip"
   else:
    with tarfile.open(p) as z:
     m=z.getmembers();N=[x.name for x in m];S=[x.size for x in m];fmt="tar"
   if o=="names":emit(N);return
   if o=="format":emit(fmt);return
   if o=="test":emit(True);return
   if o=="unsafe":emit([n for n in N if n.startswith("/") or ".." in P(n).parts]);return
   if o=="duplicates":emit([k for k,v in collections.Counter(N).items() if v>1]);return
   if o=="entries":emit(len(N));return
   if o=="compressed-size":emit(p.stat().st_size);return
   if o=="raw-size":emit(sum(S));return
   if o=="ratio":emit(sum(S)/p.stat().st_size if p.stat().st_size else None);return
   if o=="stats":emit({"format":fmt,"entries":len(N),"raw":sum(S),"archive":p.stat().st_size});return
  if g=="git":
   if o=="branch":emit(git("branch","--show-current"));return
   if o=="head":emit(git("rev-parse","HEAD"));return
   if o=="root":emit(git("rev-parse","--show-toplevel"));return
   if o=="status":emit(git("status","--porcelain").splitlines());return
   if o=="tracked":emit(git("ls-files").splitlines());return
   if o=="untracked":emit(git("ls-files","--others","--exclude-standard").splitlines());return
   if o=="changed":emit(git("diff","--name-only").splitlines());return
   if o=="tags":emit(git("tag","--list").splitlines());return
   if o=="remotes":emit(git("remote","-v").splitlines());return
   if o=="stats":emit({"branch":git("branch","--show-current"),"head":git("rev-parse","--short","HEAD"),"changed":len(git("status","--porcelain").splitlines())});return
 if pref=="netobs":
  if g=="http":
   u=a[0];st=time.time();method="HEAD" if o=="head" else "GET";r=urllib.request.urlopen(urllib.request.Request(u,method=method),timeout=15);body=b"" if method=="HEAD" else r.read();dt=time.time()-st
   if o=="status":emit(r.status);return
   if o in ("headers","head"):emit(dict(r.headers));return
   if o=="text":emit(body.decode(errors="replace"));return
   if o=="json":emit(json.loads(body));return
   if o=="latency":emit(dt);return
   if o=="final-url":emit(r.geturl());return
   if o=="content-type":emit(r.headers.get("content-type",""));return
   if o=="length":emit(len(body));return
   if o=="download":
    out=P(a[1] if len(a)>1 else "download.bin");out.write_bytes(body);emit(str(out));return
  if g=="url":
   u=a[0] if a else "";p=urllib.parse.urlparse(u)
   if o=="parse":emit({"scheme":p.scheme,"host":p.hostname,"port":p.port,"path":p.path,"query":p.query,"fragment":p.fragment});return
   if o=="encode":emit(urllib.parse.quote(u,safe=""));return
   if o=="decode":emit(urllib.parse.unquote(u));return
   if o=="join":emit(urllib.parse.urljoin(u,a[1]));return
   if o=="query-parse":emit(urllib.parse.parse_qs(p.query or u));return
   if o=="query-build":emit(urllib.parse.urlencode(dict(x.split("=",1) for x in a)));return
   if o=="normalize":emit(urllib.parse.urlunparse((p.scheme.lower(),p.netloc.lower(),p.path or "/",p.params,p.query,"")));return
   if o=="domain":emit(p.hostname or "");return
   if o=="scheme":emit(p.scheme);return
   if o=="basename":emit(P(p.path).name);return
  if g=="dns":
   t=a[0] if a else "localhost"
   if o=="resolve":emit(socket.gethostbyname_ex(t));return
   if o=="reverse":emit(socket.gethostbyaddr(t));return
   if o=="hostname":emit(socket.gethostname());return
   if o=="fqdn":emit(socket.getfqdn(t));return
   if o=="localhost":emit(socket.gethostbyname("localhost"));return
   if o=="addrinfo":emit(socket.getaddrinfo(t,None));return
   if o=="canonical":emit(socket.getfqdn(t));return
   if o=="service-port":emit(socket.getservbyname(t));return
   if o=="port-service":emit(socket.getservbyport(int(t)));return
   if o=="stats":emit({"query":t,"fqdn":socket.getfqdn(t),"address":socket.gethostbyname(t)});return
  if g=="tcp":
   h=a[0] if a else "localhost";p=int(a[1]) if len(a)>1 else 80
   if o=="check":
    s=socket.socket();s.settimeout(3);c=s.connect_ex((h,p));s.close();emit(c==0);return
   if o=="time":
    st=time.time();s=socket.create_connection((h,p),timeout=5);s.close();emit(time.time()-st);return
   if o=="send":
    s=socket.create_connection((h,p),timeout=5);s.sendall((a[2] if len(a)>2 else "").encode());s.close();emit(True);return
   if o=="recv":
    s=socket.create_connection((h,p),timeout=5);s.sendall((a[2] if len(a)>2 else "").encode());emit(s.recv(65536).decode(errors="replace"));s.close();return
   if o=="resolve":emit(socket.gethostbyname(h));return
   if o=="service":emit(socket.getservbyport(p));return
   if o=="common-ports":
    out={}
    for q in (22,80,443,3000,5000,8000,8080):
     s=socket.socket();s.settimeout(.4);out[q]=s.connect_ex((h,q))==0;s.close()
    emit(out);return
   if o=="family":emit("IPv6" if ":" in h else "IPv4");return
   if o=="host":emit(socket.gethostname());return
   if o=="stats":emit({"host":h,"port":p,"ip":socket.gethostbyname(h)});return
  if g=="jsonrpc":
   if o=="request":emit({"jsonrpc":"2.0","id":1,"method":a[0] if a else "initialize","params":json.loads(a[1]) if len(a)>1 else {}});return
   if o=="notify":emit({"jsonrpc":"2.0","method":a[0] if a else "notify","params":json.loads(a[1]) if len(a)>1 else {}});return
   if o=="response":emit({"jsonrpc":"2.0","id":1,"result":json.loads(a[0]) if a else {}});return
   if o=="error":emit({"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":a[0] if a else "error"}});return
   x=json.loads(text(a));arr=x if isinstance(x,list) else [x]
   if o=="batch":emit(arr);return
   if o=="validate":emit(all(isinstance(q,dict) and q.get("jsonrpc")=="2.0" for q in arr));return
   if o=="methods":emit([q.get("method") for q in arr if "method" in q]);return
   if o=="ids":emit([q.get("id") for q in arr if "id" in q]);return
   if o=="pretty":emit(x);return
   if o=="line":print(json.dumps(x,separators=(",",":")));return
  if g=="log":
   s=text(a);L=s.splitlines()
   if o=="lines":emit(len(L));return
   if o=="levels":emit(collections.Counter((m.group(1).upper() if (m:=re.search(r"\b(DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\b",x,re.I)) else "UNKNOWN") for x in L));return
   if o=="errors":emit([x for x in L if re.search(r"\b(error|fatal|critical)\b",x,re.I)]);return
   if o=="warnings":emit([x for x in L if re.search(r"\bwarn(?:ing)?\b",x,re.I)]);return
   if o=="timestamps":emit([m.group(0) for x in L if (m:=re.search(r"\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:\.\d+)?Z?",x))]);return
   if o=="json":emit([json.loads(x) for x in L if x.strip().startswith(("{","["))]);return
   if o=="grep":emit([x for x in L if re.search(a[1],x,re.I)]);return
   if o=="tail":emit(L[-(int(a[1]) if len(a)>1 else 20):]);return
   if o=="top":emit(collections.Counter(re.sub(r"\d+","<n>",x) for x in L).most_common(20));return
   if o=="stats":emit({"lines":len(L),"bytes":len(s.encode()),"errors":sum(bool(re.search(r"\berror\b",x,re.I)) for x in L)});return
  if g=="metric":
   x=[float(q) for q in values(a)]
   if o=="avg":emit(statistics.fmean(x) if x else None);return
   if o=="min":emit(min(x) if x else None);return
   if o=="max":emit(max(x) if x else None);return
   if o=="sum":emit(sum(x));return
   if o=="count":emit(len(x));return
   if o in ("p50","p90","p95","p99"):emit(pct(x,int(o[1:])/100));return
   if o=="stats":emit({"count":len(x),"sum":sum(x),"avg":statistics.fmean(x) if x else None,"min":min(x) if x else None,"max":max(x) if x else None,"p95":pct(x,.95)});return
  if g=="trace":
   if o=="new-trace":emit(os.urandom(16).hex());return
   if o=="new-span":emit(os.urandom(8).hex());return
   if o=="parse-parent":
    z=a[0].split("-");emit({"version":z[0],"trace_id":z[1],"span_id":z[2],"flags":z[3]});return
   if o=="make-parent":emit("00-"+(a[0] if a else os.urandom(16).hex())+"-"+(a[1] if len(a)>1 else os.urandom(8).hex())+"-01");return
   x=json.loads(text(a));A=x if isinstance(x,list) else x.get("spans",[])
   if o=="duration":emit(sum(float(q.get("duration",0)) for q in A));return
   if o=="sort":emit(sorted(A,key=lambda q:q.get("start",0)));return
   if o=="critical":emit(max(A,key=lambda q:q.get("duration",0)) if A else None);return
   if o=="errors":emit([q for q in A if q.get("error")]);return
   if o=="services":emit(sorted({q.get("service") for q in A if q.get("service")}));return
   if o=="stats":emit({"spans":len(A),"services":len({q.get("service") for q in A if q.get("service")}),"errors":sum(bool(q.get("error")) for q in A)});return
  if g=="tls":
   if o in ("pem-count","pem-labels","sha256"):
    s=text(a)
    if o=="pem-count":emit(len(re.findall(r"-----BEGIN ",s)));return
    if o=="pem-labels":emit(re.findall(r"-----BEGIN ([^-]+)-----",s));return
    if o=="sha256":emit(hashlib.sha256(s.encode()).hexdigest());return
   h=a[0];p=int(a[1]) if len(a)>1 else 443;ctx=ssl.create_default_context()
   with socket.create_connection((h,p),timeout=8) as raw:
    with ctx.wrap_socket(raw,server_hostname=h) as ss:
     c=ss.getpeercert()
     if o=="version":emit(ss.version());return
     if o=="cipher":emit(ss.cipher());return
     if o=="sans":emit(c.get("subjectAltName",[]));return
     if o=="issuer":emit(c.get("issuer"));return
     if o=="expiry":emit(c.get("notAfter"));return
     if o=="certificate":emit(ssl.DER_cert_to_PEM_cert(ss.getpeercert(binary_form=True)));return
     if o=="stats":emit({"version":ss.version(),"cipher":ss.cipher(),"issuer":c.get("issuer"),"expiry":c.get("notAfter")});return
  if g=="system":
   if o=="env":emit(dict(sorted(os.environ.items())));return
   if o=="path":emit(os.environ.get("PATH","").split(os.pathsep));return
   if o=="which":emit(shutil.which(a[0]) or "");return
   if o=="platform":emit(platform.platform());return
   if o=="python":emit(sys.version);return
   if o=="cwd":emit(os.getcwd());return
   if o=="disk":emit(shutil.disk_usage(a[0] if a else "."));return
   if o=="uname":emit(tuple(os.uname()));return
   if o=="hostname":emit(socket.gethostname());return
   if o=="stats":emit({"platform":platform.platform(),"python":sys.version.split()[0],"cwd":os.getcwd(),"hostname":socket.gethostname()});return
 raise SystemExit("unsupported operation")
if __name__=="__main__":main(sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4:])
'''

def cat(groups,prefix):return {f"{prefix}-{g}-{o}":(g,o) for g,ops in groups.items() for o in ops}
def ctrl(pkg,desc,deps):
 return f"""Package: {pkg}
Version: {VERSION}
Architecture: all
Maintainer: OceanStudio <packages@ocean.studio>
Section: utils
Priority: optional
Depends: {", ".join(deps)}
Description: {desc} - {pkg}
 Functional self-contained Ocean utility implemented with Python standard library.
 No network access occurs during apt installation.
"""
def mctrl(pkg,deps,desc):
 return f"""Package: {pkg}
Version: {VERSION}
Architecture: all
Maintainer: OceanStudio <packages@ocean.studio>
Section: metapackages
Priority: optional
Depends: {", ".join(f"{x} (= {VERSION})" for x in deps)}
Description: {desc}
 Meta-package installing the complete Ocean utility shard.
"""
def existing():
 out=set()
 try:paths=subprocess.check_output(["git","ls-tree","-r","--name-only","HEAD"],text=True).splitlines()
 except:return out
 skip=("staging/shard-49/","staging/shard-50/","staging/shard-51/","staging/intelligence-superpack/")
 for x in paths:
  if x.endswith(".deb") and not x.startswith(skip):out.add(Path(x).name.split("_",1)[0])
 return out
def build(pkg,g,o,pool,n,desc,prefix):
 with tempfile.TemporaryDirectory(prefix="ocean-intel-") as td:
  root=Path(td)/pkg;d=root/"DEBIAN";b=root/PREFIX.strip("/")/"bin";l=root/PREFIX.strip("/")/"lib/ocean-intelligence"
  d.mkdir(parents=True);b.mkdir(parents=True);l.mkdir(parents=True)
  deps=["python"]+(["git"] if n=="50" and g=="git" else [])
  (d/"control").write_text(ctrl(pkg,desc,deps))
  sh=b/pkg;sh.write_text('#!/system/bin/sh\\nP="$PREFIX"\\n[ -n "$P" ] || P="'+PREFIX+'"\\nexec "$P/bin/python" "$P/lib/ocean-intelligence/'+pkg+'.py" '+repr(prefix)+' '+repr(g)+' '+repr(o)+' "$@"\\n');sh.chmod(0o755)
  rt=l/(pkg+".py");rt.write_text(RUNTIME);rt.chmod(0o755)
  art=pool/f"{pkg}_{VERSION}_all.deb";subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(art)],check=True,stdout=subprocess.DEVNULL);return art
def meta(pkg,deps,pool,desc):
 with tempfile.TemporaryDirectory(prefix="ocean-meta-") as td:
  root=Path(td)/pkg;(root/"DEBIAN").mkdir(parents=True);(root/"DEBIAN/control").write_text(mctrl(pkg,deps,desc))
  art=pool/f"{pkg}_{VERSION}_all.deb";subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(art)],check=True,stdout=subprocess.DEVNULL);return art
def row(art,pkg,g,o):
 raw=art.read_bytes();return {"package":pkg,"artifact":art.name,"group":g,"operation":o,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
def index(out,rows):
 paras=[]
 for r in rows:
  art=out/"pool/main"/r["artifact"];f=subprocess.check_output(["dpkg-deb","-f",str(art)],text=True).strip()
  paras.append(f+"\\nFilename: "+out.as_posix()+"/pool/main/"+art.name+"\\nSize: "+str(r["bytes"])+"\\nSHA256: "+r["sha256"]+"\\n")
 (out/"Packages.repaired").write_text("\\n".join(paras))
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--shards",default="49,50,51");a=ap.parse_args()
 seen=existing();suites=[];total=0
 for n in [x.strip() for x in a.shards.split(",") if x.strip()]:
  groups,prefix,outname,suite,desc=SHARDS[n];C=cat(groups,prefix);assert len(C)==100 and len(set(C))==100
  col=sorted((set(C)|{suite})&seen)
  if col:raise SystemExit("repo collisions: "+", ".join(col))
  out=Path(outname);pool=out/"pool/main"
  if out.exists():shutil.rmtree(out)
  pool.mkdir(parents=True);rows=[]
  for pkg,(g,o) in C.items():rows.append(row(build(pkg,g,o,pool,n,desc,prefix),pkg,g,o))
  rows.append(row(meta(suite,list(C),pool,"Ocean "+desc+" suite"),suite,"meta","install"));index(out,rows)
  (out/"provenance.json").write_text(json.dumps({"schemaVersion":1,"shard":n,"version":VERSION,"prefix":PREFIX,"commandCount":100,"packageCount":101,"suite":suite,"networkAtAptInstall":False,"rootRequired":False,"implementation":"self-contained Python standard-library utilities","packages":rows},indent=2)+"\\n")
  seen.update(C);seen.add(suite);suites.append(suite);total+=101
 out=Path("staging/intelligence-superpack");pool=out/"pool/main"
 if out.exists():shutil.rmtree(out)
 pool.mkdir(parents=True)
 if SUPER in seen:raise SystemExit("superpack collision")
 r=row(meta(SUPER,suites,pool,"Ocean intelligence code automation and observability superpack"),SUPER,"meta","install");index(out,[r])
 (out/"provenance.json").write_text(json.dumps({"schemaVersion":1,"version":VERSION,"prefix":PREFIX,"dependsOn":suites,"commandCount":300,"totalNewPackages":304},indent=2)+"\\n")
 print(json.dumps({"commands":300,"metaPackages":4,"totalNewPackages":304,"shards":["49","50","51"]},indent=2))
if __name__=="__main__":main()
