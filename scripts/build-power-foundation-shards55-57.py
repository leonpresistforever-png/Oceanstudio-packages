#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path

PREFIX="/data/data/studio.ocean.app/files/usr"
VERSION="1.0.0-1"

SYS_GROUPS={
"repo":["list","add","remove","enable","disable","switch","pin","unpin","backup","restore"],
"pkg":["installed","search","policy","files","owner","deps","rdeps","manifest","verify","cache"],
"proc":["list","find","tree","topcpu","topmem","env","fds","cwd","signal","wait"],
"session":["new","list","has","kill","send","capture","rename","window-new","window-list","detach"],
"service":["define","start","stop","restart","status","list","logs","enable","disable","purge"],
"fs":["stat","tree","mkdir","touch","copy","move","symlink","chmod","checksum","remove"],
"envfile":["get","set","unset","list","merge","export","path-add","path-remove","which","doctor"],
"perm":["mode","chmod","executable","readonly","writable","owner","access","dirs","files","secure"],
"watch":["mtime","wait-change","wait-create","wait-delete","tail","size","exists","newest","oldest","changed-since"],
"archive":["zip-create","zip-extract","zip-list","tar-create","tar-extract","tar-list","gzip","gunzip","checksum","manifest"],
}
AGENT_GROUPS={
"task":["init","add","list","next","start","done","fail","retry","clear","stats"],
"state":["get","set","delete","list","export","import","diff","merge","clear","version"],
"queue":["push","pop","peek","list","count","clear","dedupe","export","import","merge"],
"event":["emit","list","tail","filter","count","clear","export","import","types","latest"],
"lock":["acquire","release","status","list","wait","touch","owner","stale","clear-stale","clear-all"],
"approval":["request","list","approve","deny","status","pending","clear","export","import","history"],
"cap":["which","has-command","has-env","has-file","has-dir","writable","readable","port-free","python","summary"],
"exec":["run","shell","capture","timeout","env","cwd","pipeline","which","dryrun","history"],
"job":["define","start","status","list","wait","stop","logs","retry","purge","summary"],
"workspace":["scan","manifest","hash","snapshot","diff","changed","large","recent","summary","clean-empty"],
}
CORE_GROUPS={
"http":["get","head","status","download","headers","json","post-json","put-json","delete","serve"],
"tcp":["connect","send","port","wait","listen-once","resolve","local-ports","remote","latency","echo-server"],
"tls":["cert","subject","issuer","serial","expires","days-left","san","fingerprint","protocol","check"],
"dns":["lookup","lookup-all","reverse","fqdn","hostname","hosts","resolv","mx-hint","local-ip","summary"],
"sqlite":["query","tables","schema","indexes","integrity","backup","dump","vacuum","rowcount","info"],
"json":["validate","pretty","compact","get","set","merge","diff","keys","select","jsonl-count"],
"csv":["stats","to-json","from-json","select","filter","sort","dedupe","head","tail","split"],
"blob":["sha256","sha512","md5","base64","unbase64","hex","unhex","gzip","gunzip","size"],
"stream":["lines","words","chars","head","tail","grep","dedupe","sort","count","checksum"],
"kv":["set","get","delete","list","clear","has","keys","export","import","stats"],
}

def catalog(groups,prefix):
    return {f"{prefix}-{g}-{o}":(g,o) for g,ops in groups.items() for o in ops}
SYS=catalog(SYS_GROUPS,"sysx");AGENT=catalog(AGENT_GROUPS,"agentx");CORE=catalog(CORE_GROUPS,"corex")
assert len(SYS)==len(AGENT)==len(CORE)==100
assert len(set(SYS)|set(AGENT)|set(CORE))==300

SHARDS={
"55":(SYS,"staging/shard-55","ocean-system-control-suite","system/package/session/process customization"),
"56":(AGENT,"staging/shard-56","ocean-agent-runtime-suite","agent task/state/job/workspace orchestration"),
"57":(CORE,"staging/shard-57","ocean-core-io-suite","network/data/storage/runtime foundations"),
}
SUPERPACK="ocean-power-foundation-superpack"

RUNTIME=r'''#!/usr/bin/env python3
from __future__ import annotations
import base64,csv,difflib,gzip,hashlib,http.server,json,os,pathlib,shlex,shutil,signal,socket,sqlite3,ssl,subprocess,sys,tarfile,time,urllib.request,zipfile
P=pathlib.Path;HOME=P.home()
STATE=HOME/".local/state/ocean-power";CONF=HOME/".config/ocean-power"
STATE.mkdir(parents=True,exist_ok=True);CONF.mkdir(parents=True,exist_ok=True)

def emit(x):
 print(json.dumps(x,indent=2,ensure_ascii=False,default=str) if isinstance(x,(dict,list,tuple,bool,int,float)) or x is None else x)
def load(p,d):
 try:return json.loads(P(p).read_text())
 except:return d
def save(p,o):
 p=P(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(o,indent=2,ensure_ascii=False)+"\n")
def txt(a,i=0):
 if len(a)<=i:return sys.stdin.read()
 p=P(a[i]).expanduser();return p.read_text(errors="replace") if p.exists() else a[i]
def pref():return P(os.environ.get("PREFIX") or "/data/data/studio.ocean.app/files/usr")
def run(argv,**kw):return subprocess.run(argv,text=True,**kw)

def repo(o,a):
 apt=pref()/"etc/apt";main=apt/"sources.list";extra=apt/"sources.list.d/ocean-extra.list";extra.parent.mkdir(parents=True,exist_ok=True)
 files=[x for x in [main] if x.exists()]+(sorted((apt/"sources.list.d").glob("*.list")) if (apt/"sources.list.d").exists() else [])
 if o=="list":emit({str(x):x.read_text(errors="replace").splitlines() for x in files});return
 lines=extra.read_text(errors="replace").splitlines() if extra.exists() else []
 if o=="add":
  q=" ".join(a)
  if q and q not in lines:lines.append(q)
  extra.write_text("\n".join(lines)+("\n" if lines else ""));emit(str(extra));return
 if o=="remove":
  q=" ".join(a);lines=[x for x in lines if q not in x];extra.write_text("\n".join(lines)+("\n" if lines else ""));emit(True);return
 if o in ("enable","disable"):
  q=" ".join(a);out=[]
  for x in lines:
   raw=x.lstrip("# ").strip()
   if q in raw:x=raw if o=="enable" else "# "+raw
   out.append(x)
  extra.write_text("\n".join(out)+("\n" if out else ""));emit(True);return
 if o=="switch":
  if len(a)<2:raise SystemExit("NAME URL [SUITE] [COMP]")
  main.parent.mkdir(parents=True,exist_ok=True);main.write_text("deb "+a[1]+" "+(a[2] if len(a)>2 else "stable")+" "+(a[3] if len(a)>3 else "main")+"\n");emit({"backend":a[0],"file":str(main)});return
 pd=apt/"preferences.d";pd.mkdir(parents=True,exist_ok=True)
 if o=="pin":
  if len(a)<3:raise SystemExit("NAME ORIGIN PRIORITY")
  p=pd/("ocean-"+a[0]);p.write_text("Package: *\nPin: origin "+a[1]+"\nPin-Priority: "+str(int(a[2]))+"\n");emit(str(p));return
 if o=="unpin":(pd/("ocean-"+a[0])).unlink(missing_ok=True);emit(True);return
 bk=STATE/"apt-backup"
 if o=="backup":
  if bk.exists():shutil.rmtree(bk)
  if apt.exists():shutil.copytree(apt,bk)
  emit(str(bk));return
 if o=="restore":
  if not bk.exists():raise SystemExit("no backup")
  if apt.exists():shutil.rmtree(apt)
  shutil.copytree(bk,apt);emit(str(apt));return

def pkg(o,a):
 x=a[0] if a else ""
 fmt="-"+"f="+"$"+"{Package}\\t$"+"{Version}\\n"
 if o=="installed":
  cp=run(["dpkg-query","-W",fmt],capture_output=True);print(cp.stdout,end="");return
 if o=="search":subprocess.run(["apt-cache","search",*a]);return
 if o=="policy":subprocess.run(["apt-cache","policy",*a]);return
 if o=="files":subprocess.run(["dpkg","-L",x]);return
 if o=="owner":subprocess.run(["dpkg","-S",x]);return
 if o=="deps":subprocess.run(["apt-cache","depends",x]);return
 if o=="rdeps":subprocess.run(["apt-cache","rdepends",x]);return
 if o=="manifest":
  cp=run(["dpkg-query","-W",fmt],capture_output=True);emit([{"package":q.split("\t",1)[0],"version":q.split("\t",1)[1]} for q in cp.stdout.splitlines() if "\t" in q]);return
 if o=="verify":subprocess.run(["dpkg","-V",x] if x else ["dpkg","-V"]);return
 if o=="cache":
  d=pref()/"var/cache/apt/archives";emit([{"file":p.name,"bytes":p.stat().st_size} for p in d.glob("*.deb")] if d.exists() else []);return

def plist():
 out=[]
 for d in P("/proc").iterdir():
  if not d.name.isdigit():continue
  try:
   st=(d/"stat").read_text().split();rss=0
   for l in (d/"status").read_text(errors="replace").splitlines():
    if l.startswith("VmRSS:"):rss=int(l.split()[1]);break
   out.append({"pid":int(d.name),"ppid":int(st[3]),"comm":st[1].strip("()"),"cpu_ticks":int(st[13])+int(st[14]),"rss_kb":rss})
  except:pass
 return out
def proc(o,a):
 ps=plist()
 if o=="list":emit(ps);return
 if o=="find":q=" ".join(a).lower();emit([x for x in ps if q in x["comm"].lower()]);return
 if o=="tree":
  by={}
  for x in ps:by.setdefault(x["ppid"],[]).append(x)
  out=[]
  def walk(pid,d=0):
   for x in sorted(by.get(pid,[]),key=lambda z:z["pid"]):out.append({"depth":d,**x});walk(x["pid"],d+1)
  walk(0);emit(out);return
 if o=="topcpu":emit(sorted(ps,key=lambda x:x["cpu_ticks"],reverse=True)[:int(a[0]) if a else 20]);return
 if o=="topmem":emit(sorted(ps,key=lambda x:x["rss_kb"],reverse=True)[:int(a[0]) if a else 20]);return
 pid=int(a[0]);root=P("/proc")/str(pid)
 if o=="env":raw=(root/"environ").read_bytes().decode(errors="replace");emit(dict(q.split("=",1) for q in raw.split("\0") if "=" in q));return
 if o=="fds":emit({x.name:os.readlink(x) for x in (root/"fd").iterdir()});return
 if o=="cwd":emit(os.readlink(root/"cwd"));return
 if o=="signal":os.kill(pid,getattr(signal,(a[1] if len(a)>1 else "SIGTERM").upper()));emit(True);return
 if o=="wait":
  end=time.time()+(float(a[1]) if len(a)>1 else 60)
  while root.exists() and time.time()<end:time.sleep(.2)
  emit(not root.exists());return

def session(o,a):
 m={"new":["new-session","-d","-s"],"list":["list-sessions"],"has":["has-session","-t"],"kill":["kill-session","-t"],"capture":["capture-pane","-p","-t"],"window-list":["list-windows","-t"],"detach":["detach-client","-s"]}
 if o=="send":argv=["tmux","send-keys","-t",a[0],*a[1:],"Enter"]
 elif o=="rename":argv=["tmux","rename-session","-t",a[0],a[1]]
 elif o=="window-new":argv=["tmux","new-window","-t",a[0],*a[1:]]
 elif o=="new":argv=["tmux",*m[o],a[0],*a[1:]]
 elif o=="list":argv=["tmux",*m[o]]
 else:argv=["tmux",*m[o],a[0]]
 raise SystemExit(subprocess.run(argv).returncode)

def sfile():return STATE/"services.json"
def service(o,a):
 d=load(sfile(),{})
 if o=="define":d[a[0]]={"argv":a[1:],"pid":None,"enabled":False,"log":str(STATE/("service-"+a[0]+".log"))};save(sfile(),d);emit(a[0]);return
 if o=="list":emit(d);return
 if o=="status":
  x=d.get(a[0]);pid=x.get("pid") if x else None;emit({"defined":bool(x),"running":bool(pid and (P("/proc")/str(pid)).exists()),"service":x});return
 if o=="logs":
  p=P(d[a[0]]["log"]);print(p.read_text(errors="replace") if p.exists() else "",end="");return
 if o in ("enable","disable"):d[a[0]]["enabled"]=o=="enable";save(sfile(),d);emit(True);return
 if o=="purge":d.pop(a[0],None);save(sfile(),d);emit(True);return
 n=a[0];x=d[n]
 if o in ("stop","restart") and x.get("pid"):
  try:os.kill(x["pid"],signal.SIGTERM)
  except ProcessLookupError:pass
  x["pid"]=None
  if o=="stop":save(sfile(),d);emit(True);return
 if o in ("start","restart"):
  log=open(x["log"],"ab");p=subprocess.Popen(x["argv"],stdout=log,stderr=subprocess.STDOUT,start_new_session=True);x["pid"]=p.pid;save(sfile(),d);emit(p.pid);return

def fs(o,a):
 p=P(a[0]).expanduser() if a else P(".")
 if o=="stat":s=p.stat();emit({"path":str(p),"bytes":s.st_size,"mode":oct(s.st_mode&0o777),"mtime":s.st_mtime});return
 if o=="tree":emit([str(x.relative_to(p)) for x in sorted(p.rglob("*"))]);return
 if o=="mkdir":p.mkdir(parents=True,exist_ok=True);emit(str(p));return
 if o=="touch":p.parent.mkdir(parents=True,exist_ok=True);p.touch();emit(str(p));return
 if o=="copy":
  d=P(a[1]).expanduser();shutil.copytree(p,d,dirs_exist_ok=True) if p.is_dir() else shutil.copy2(p,d);emit(str(d));return
 if o=="move":emit(shutil.move(str(p),a[1]));return
 if o=="symlink":P(a[1]).expanduser().symlink_to(p);emit(a[1]);return
 if o=="chmod":os.chmod(p,int(a[1],8));emit(oct(p.stat().st_mode&0o777));return
 if o=="checksum":emit(hashlib.sha256(p.read_bytes()).hexdigest());return
 if o=="remove":shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink(missing_ok=True);emit(True);return

def efile():return CONF/"environment.json"
def envfile(o,a):
 d=load(efile(),{})
 if o=="get":emit(d.get(a[0],""));return
 if o=="set":d[a[0]]=a[1];save(efile(),d);emit(True);return
 if o=="unset":d.pop(a[0],None);save(efile(),d);emit(True);return
 if o=="list":emit(d);return
 if o=="merge":d.update(json.loads(txt(a)));save(efile(),d);emit(d);return
 if o=="export":print("\n".join("export "+k+"="+shlex.quote(str(v)) for k,v in sorted(d.items())));return
 if o in ("path-add","path-remove"):
  cur=d.get("PATH",os.environ.get("PATH","")).split(os.pathsep);cur=[x for x in cur if x!=a[0]]
  if o=="path-add":cur.insert(0,a[0])
  d["PATH"]=os.pathsep.join(cur);save(efile(),d);emit(d["PATH"]);return
 if o=="which":emit(shutil.which(a[0],path=d.get("PATH") or None) or "");return
 if o=="doctor":emit({"file":str(efile()),"entries":len(d),"path_entries":len((d.get("PATH") or os.environ.get("PATH","")).split(os.pathsep))});return

def perm(o,a):
 p=P(a[0]).expanduser();s=p.stat()
 if o=="mode":emit(oct(s.st_mode&0o777));return
 if o=="chmod":os.chmod(p,int(a[1],8));emit(oct(p.stat().st_mode&0o777));return
 if o=="executable":os.chmod(p,s.st_mode|0o111);emit(True);return
 if o=="readonly":os.chmod(p,s.st_mode&~0o222);emit(True);return
 if o=="writable":os.chmod(p,s.st_mode|0o200);emit(True);return
 if o=="owner":emit({"uid":s.st_uid,"gid":s.st_gid});return
 if o=="access":emit({"read":os.access(p,os.R_OK),"write":os.access(p,os.W_OK),"exec":os.access(p,os.X_OK)});return
 if o=="dirs":emit([str(x) for x in p.rglob("*") if x.is_dir()]);return
 if o=="files":emit([str(x) for x in p.rglob("*") if x.is_file()]);return
 if o=="secure":os.chmod(p,0o700 if p.is_dir() else 0o600);emit(True);return

def watch(o,a):
 p=P(a[0]).expanduser()
 if o=="mtime":emit(p.stat().st_mtime);return
 if o in ("wait-change","wait-create","wait-delete"):
  end=time.time()+(float(a[1]) if len(a)>1 else 60);ex=p.exists();mt=p.stat().st_mtime if ex else None
  while time.time()<end:
   now=p.exists();nmt=p.stat().st_mtime if now else None
   if (o=="wait-create" and now and not ex) or (o=="wait-delete" and not now and ex) or (o=="wait-change" and now and nmt!=mt):emit(True);return
   time.sleep(.25)
  emit(False);return
 if o=="tail":print("\n".join(p.read_text(errors="replace").splitlines()[-(int(a[1]) if len(a)>1 else 20):]));return
 if o=="size":emit(p.stat().st_size);return
 if o=="exists":emit(p.exists());return
 f=[x for x in p.rglob("*") if x.is_file()] if p.is_dir() else [p]
 if o=="newest":emit(str(max(f,key=lambda x:x.stat().st_mtime)) if f else "");return
 if o=="oldest":emit(str(min(f,key=lambda x:x.stat().st_mtime)) if f else "");return
 if o=="changed-since":emit([str(x) for x in f if x.stat().st_mtime>=float(a[1])]);return

def archive(o,a):
 if o=="zip-create":
  src=P(a[0]);dst=P(a[1])
  with zipfile.ZipFile(dst,"w",zipfile.ZIP_DEFLATED) as z:
   for x in ([src] if src.is_file() else [q for q in src.rglob("*") if q.is_file()]):z.write(x,x.name if src.is_file() else x.relative_to(src))
  emit(str(dst));return
 if o=="zip-extract":
  with zipfile.ZipFile(a[0]) as z:z.extractall(a[1])
  emit(a[1]);return
 if o=="zip-list":
  with zipfile.ZipFile(a[0]) as z:emit(z.namelist())
  return
 if o=="tar-create":
  with tarfile.open(a[1],"w:gz") as t:t.add(a[0],arcname=P(a[0]).name)
  emit(a[1]);return
 if o=="tar-extract":
  with tarfile.open(a[0]) as t:t.extractall(a[1],filter="data")
  emit(a[1]);return
 if o=="tar-list":
  with tarfile.open(a[0]) as t:emit(t.getnames())
  return
 if o=="gzip":P(a[1]).write_bytes(gzip.compress(P(a[0]).read_bytes()));emit(a[1]);return
 if o=="gunzip":P(a[1]).write_bytes(gzip.decompress(P(a[0]).read_bytes()));emit(a[1]);return
 if o=="checksum":emit(hashlib.sha256(P(a[0]).read_bytes()).hexdigest());return
 if o=="manifest":
  p=P(a[0]);emit([{"path":str(x.relative_to(p)),"bytes":x.stat().st_size,"sha256":hashlib.sha256(x.read_bytes()).hexdigest()} for x in p.rglob("*") if x.is_file()]);return

def rfile(n):return STATE/(n+".json")
def task(o,a):
 p=rfile("tasks");d=load(p,[])
 if o=="init":save(p,[]);emit(True);return
 if o=="add":x={"id":str(int(time.time()*1000)),"text":" ".join(a),"status":"pending","attempts":0,"created":time.time()};d.append(x);save(p,d);emit(x);return
 if o=="list":emit(d);return
 if o=="next":emit(next((x for x in d if x["status"]=="pending"),None));return
 if o in ("start","done","fail","retry"):
  x=next(x for x in d if x["id"]==a[0]);x["status"]={"start":"running","done":"done","fail":"failed","retry":"pending"}[o];x["attempts"]+=1 if o=="start" else 0;save(p,d);emit(x);return
 if o=="clear":save(p,[]);emit(True);return
 if o=="stats":
  from collections import Counter;emit(dict(Counter(x["status"] for x in d)));return

def state(o,a):
 p=rfile("agent-state");d=load(p,{"_version":1})
 if o=="get":emit(d.get(a[0]));return
 if o=="set":d[a[0]]=a[1];d["_version"]=d.get("_version",0)+1;save(p,d);emit(True);return
 if o=="delete":d.pop(a[0],None);save(p,d);emit(True);return
 if o=="list" or o=="export":emit(d);return
 if o=="import":d=json.loads(txt(a));save(p,d);emit(True);return
 if o=="diff":
  y=json.loads(txt(a));print("\n".join(difflib.unified_diff(json.dumps(d,indent=2,sort_keys=True).splitlines(),json.dumps(y,indent=2,sort_keys=True).splitlines(),lineterm="")));return
 if o=="merge":d.update(json.loads(txt(a)));save(p,d);emit(d);return
 if o=="clear":save(p,{"_version":1});emit(True);return
 if o=="version":emit(d.get("_version",0));return

def queue(o,a):
 p=rfile("queue");q=load(p,[])
 if o=="push":q.append(" ".join(a));save(p,q);emit(len(q));return
 if o=="pop":x=q.pop(0) if q else None;save(p,q);emit(x);return
 if o=="peek":emit(q[0] if q else None);return
 if o=="list" or o=="export":emit(q);return
 if o=="count":emit(len(q));return
 if o=="clear":save(p,[]);emit(True);return
 if o=="dedupe":q=list(dict.fromkeys(q));save(p,q);emit(q);return
 if o=="import":q=json.loads(txt(a));save(p,q);emit(len(q));return
 if o=="merge":q+=json.loads(txt(a));save(p,q);emit(len(q));return

def event(o,a):
 p=STATE/"events.jsonl";rows=[]
 if p.exists():
  for l in p.read_text(errors="replace").splitlines():
   try:rows.append(json.loads(l))
   except:pass
 if o=="emit":e={"ts":time.time(),"type":a[0] if a else "event","data":" ".join(a[1:])};open(p,"a").write(json.dumps(e)+"\n");emit(e);return
 if o=="list" or o=="export":emit(rows);return
 if o=="tail":emit(rows[-(int(a[0]) if a else 20):]);return
 if o=="filter":emit([x for x in rows if x.get("type")==a[0]]);return
 if o=="count":emit(len(rows));return
 if o=="clear":p.unlink(missing_ok=True);emit(True);return
 if o=="import":arr=json.loads(txt(a));p.write_text("".join(json.dumps(x)+"\n" for x in arr));emit(len(arr));return
 if o=="types":emit(sorted(set(x.get("type") for x in rows)));return
 if o=="latest":emit(rows[-1] if rows else None);return

def lock(o,a):
 d=STATE/"locks";d.mkdir(exist_ok=True);name=a[0] if a else "";p=d/(name+".lock")
 if o=="acquire":
  try:fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,json.dumps({"pid":os.getpid(),"ts":time.time()}).encode());os.close(fd);emit(True)
  except FileExistsError:emit(False)
  return
 if o=="release":p.unlink(missing_ok=True);emit(True);return
 if o=="status":emit(load(p,None));return
 if o=="list":emit({x.stem:load(x,None) for x in d.glob("*.lock")});return
 if o=="wait":
  end=time.time()+(float(a[1]) if len(a)>1 else 60)
  while p.exists() and time.time()<end:time.sleep(.2)
  emit(not p.exists());return
 if o=="touch":p.touch();emit(True);return
 if o=="owner":emit(load(p,{}).get("pid"));return
 if o=="stale":pid=load(p,{}).get("pid");emit(bool(pid and not (P("/proc")/str(pid)).exists()));return
 if o=="clear-stale":
  n=0
  for x in d.glob("*.lock"):
   pid=load(x,{}).get("pid")
   if pid and not (P("/proc")/str(pid)).exists():x.unlink();n+=1
  emit(n);return
 if o=="clear-all":
  for x in d.glob("*.lock"):x.unlink()
  emit(True);return

def approval(o,a):
 p=rfile("approvals");d=load(p,[])
 if o=="request":x={"id":str(int(time.time()*1000)),"action":" ".join(a),"status":"pending","ts":time.time()};d.append(x);save(p,d);emit(x);return
 if o=="list" or o=="export":emit(d);return
 if o in ("approve","deny"):x=next(x for x in d if x["id"]==a[0]);x["status"]="approved" if o=="approve" else "denied";x["decided"]=time.time();save(p,d);emit(x);return
 if o=="status":emit(next((x for x in d if x["id"]==a[0]),None));return
 if o=="pending":emit([x for x in d if x["status"]=="pending"]);return
 if o=="clear":save(p,[]);emit(True);return
 if o=="import":d=json.loads(txt(a));save(p,d);emit(len(d));return
 if o=="history":emit([x for x in d if x["status"]!="pending"]);return

def cap(o,a):
 if o=="which":emit(shutil.which(a[0]) or "");return
 if o=="has-command":emit(bool(shutil.which(a[0])));return
 if o=="has-env":emit(a[0] in os.environ);return
 if o=="has-file":emit(P(a[0]).expanduser().is_file());return
 if o=="has-dir":emit(P(a[0]).expanduser().is_dir());return
 if o=="writable":emit(os.access(P(a[0]).expanduser(),os.W_OK));return
 if o=="readable":emit(os.access(P(a[0]).expanduser(),os.R_OK));return
 if o=="port-free":
  s=socket.socket()
  try:s.bind(("127.0.0.1",int(a[0])));ok=True
  except OSError:ok=False
  s.close();emit(ok);return
 if o=="python":emit({"executable":sys.executable,"version":sys.version});return
 if o=="summary":emit({"cwd":os.getcwd(),"home":str(HOME),"prefix":str(pref()),"commands":{x:bool(shutil.which(x)) for x in ("git","curl","tmux","rclone","ssh","python")}});return

def exechist():return STATE/"exec-history.jsonl"
def rexec(o,a):
 if o=="which":emit(shutil.which(a[0]) or "");return
 if o=="dryrun":emit({"argv":a,"cwd":os.getcwd()});return
 if o=="history":print(exechist().read_text(errors="replace") if exechist().exists() else "",end="");return
 if o=="pipeline":
  parts=" ".join(a).split("|");prev=None;ps=[]
  for part in parts:
   p=subprocess.Popen(shlex.split(part),stdin=prev.stdout if prev else None,stdout=subprocess.PIPE)
   if prev and prev.stdout:prev.stdout.close()
   ps.append(p);prev=p
  out,_=ps[-1].communicate();[p.wait() for p in ps[:-1]];sys.stdout.buffer.write(out or b"");return
 env=os.environ.copy();cwd=None;timeout=None;argv=a
 if o=="shell":cp=subprocess.run(" ".join(a),shell=True);raise SystemExit(cp.returncode)
 if o=="timeout":timeout=float(a[0]);argv=a[1:]
 if o=="cwd":cwd=a[0];argv=a[1:]
 if o=="env":
  argv=list(a)
  while argv and "=" in argv[0]:
   k,v=argv.pop(0).split("=",1);env[k]=v
 if o=="capture":
  cp=subprocess.run(argv,text=True,capture_output=True);open(exechist(),"a").write(json.dumps({"ts":time.time(),"argv":argv,"rc":cp.returncode})+"\n");emit({"rc":cp.returncode,"stdout":cp.stdout,"stderr":cp.stderr});return
 cp=subprocess.run(argv,env=env,cwd=cwd,timeout=timeout);open(exechist(),"a").write(json.dumps({"ts":time.time(),"argv":argv,"rc":cp.returncode})+"\n");raise SystemExit(cp.returncode)

def job(o,a):
 p=rfile("jobs");d=load(p,{})
 if o=="define":d[a[0]]={"argv":a[1:],"pid":None,"log":str(STATE/("job-"+a[0]+".log"))};save(p,d);emit(a[0]);return
 if o=="list":emit(d);return
 if o=="status":x=d.get(a[0]);pid=x.get("pid") if x else None;emit({"defined":bool(x),"running":bool(pid and (P("/proc")/str(pid)).exists()),"job":x});return
 if o=="logs":q=P(d[a[0]]["log"]);print(q.read_text(errors="replace") if q.exists() else "",end="");return
 if o=="purge":d.pop(a[0],None);save(p,d);emit(True);return
 if o=="summary":emit({"defined":len(d),"running":sum(bool(x.get("pid") and (P("/proc")/str(x["pid"])).exists()) for x in d.values())});return
 x=d[a[0]]
 if o=="wait":
  end=time.time()+(float(a[1]) if len(a)>1 else 60);pid=x.get("pid")
  while pid and (P("/proc")/str(pid)).exists() and time.time()<end:time.sleep(.2)
  emit(not pid or not (P("/proc")/str(pid)).exists());return
 if o=="stop":
  if x.get("pid"):
   try:os.kill(x["pid"],signal.SIGTERM)
   except ProcessLookupError:pass
  x["pid"]=None;save(p,d);emit(True);return
 if o in ("start","retry"):
  log=open(x["log"],"ab");q=subprocess.Popen(x["argv"],stdout=log,stderr=subprocess.STDOUT,start_new_session=True);x["pid"]=q.pid;save(p,d);emit(q.pid);return

def wfiles(root):return [x for x in P(root).rglob("*") if x.is_file()]
def snap(root):
 r=P(root);return {str(x.relative_to(r)):{"bytes":x.stat().st_size,"mtime":x.stat().st_mtime,"sha256":hashlib.sha256(x.read_bytes()).hexdigest()} for x in wfiles(r)}
def workspace(o,a):
 root=P(a[0] if a else ".").resolve();sp=STATE/"workspace-snapshot.json"
 if o=="scan":emit([str(x.relative_to(root)) for x in wfiles(root)]);return
 if o=="manifest":emit(snap(root));return
 if o=="hash":emit(hashlib.sha256(json.dumps(snap(root),sort_keys=True).encode()).hexdigest());return
 if o=="snapshot":save(sp,{"root":str(root),"files":snap(root)});emit(str(sp));return
 if o in ("diff","changed"):
  old=load(sp,{}).get("files",{});new=snap(root);emit(sorted(x for x in set(old)|set(new) if old.get(x)!=new.get(x)));return
 if o=="large":emit(sorted([{"path":str(x.relative_to(root)),"bytes":x.stat().st_size} for x in wfiles(root)],key=lambda z:z["bytes"],reverse=True)[:20]);return
 if o=="recent":emit([str(x.relative_to(root)) for x in sorted(wfiles(root),key=lambda z:z.stat().st_mtime,reverse=True)[:20]]);return
 if o=="summary":
  from collections import Counter;f=wfiles(root);emit({"files":len(f),"bytes":sum(x.stat().st_size for x in f),"extensions":dict(Counter(x.suffix or "<none>" for x in f))});return
 if o=="clean-empty":
  n=0
  for d in sorted([x for x in root.rglob("*") if x.is_dir()],reverse=True):
   try:d.rmdir();n+=1
   except OSError:pass
  emit(n);return

def req(method,url,data=None,headers=None):
 b=None if data is None else (data if isinstance(data,bytes) else data.encode());q=urllib.request.Request(url,data=b,method=method,headers=headers or {})
 with urllib.request.urlopen(q,timeout=20) as r:return r.status,dict(r.headers),r.read()
def http(o,a):
 if o=="serve":
  port=int(a[0]) if a else 8000;os.chdir(a[1] if len(a)>1 else ".");http.server.ThreadingHTTPServer(("127.0.0.1",port),http.server.SimpleHTTPRequestHandler).serve_forever();return
 url=a[0]
 if o=="get":st,h,b=req("GET",url);sys.stdout.buffer.write(b);return
 if o=="head":st,h,b=req("HEAD",url);emit({"status":st,"headers":h});return
 if o=="status":st,h,b=req("HEAD",url);emit(st);return
 if o=="download":st,h,b=req("GET",url);P(a[1]).write_bytes(b);emit({"status":st,"bytes":len(b),"file":a[1]});return
 if o=="headers":st,h,b=req("HEAD",url);emit(h);return
 if o=="json":st,h,b=req("GET",url,headers={"Accept":"application/json"});emit(json.loads(b));return
 if o in ("post-json","put-json"):st,h,b=req("POST" if o=="post-json" else "PUT",url,txt(a,1),{"Content-Type":"application/json"});emit({"status":st,"body":b.decode(errors="replace")});return
 if o=="delete":st,h,b=req("DELETE",url);emit({"status":st,"body":b.decode(errors="replace")});return

def tcp(o,a):
 host=a[0] if a else "127.0.0.1";port=int(a[1]) if len(a)>1 else 0
 if o=="resolve":emit(socket.gethostbyname(host));return
 if o=="port":s=socket.socket();s.settimeout(2);rc=s.connect_ex((host,port));s.close();emit(rc==0);return
 if o=="wait":
  end=time.time()+(float(a[2]) if len(a)>2 else 30)
  while time.time()<end:
   s=socket.socket();s.settimeout(1);rc=s.connect_ex((host,port));s.close()
   if rc==0:emit(True);return
   time.sleep(.25)
  emit(False);return
 if o=="connect":s=socket.create_connection((host,port),timeout=5);emit({"local":s.getsockname(),"remote":s.getpeername()});s.close();return
 if o=="send":
  s=socket.create_connection((host,port),timeout=5);s.sendall(" ".join(a[2:]).encode());s.settimeout(2)
  try:b=s.recv(65536)
  except:b=b""
  s.close();sys.stdout.buffer.write(b);return
 if o=="listen-once":s=socket.socket();s.bind((host,port));s.listen(1);c,ad=s.accept();b=c.recv(65536);emit({"peer":ad,"data":b.decode(errors="replace")});c.close();s.close();return
 if o=="local-ports":
  rows=[]
  for f in ("/proc/net/tcp","/proc/net/tcp6"):
   p=P(f)
   if p.exists():
    for l in p.read_text().splitlines()[1:]:rows.append(int(l.split()[1].split(":")[1],16))
  emit(sorted(set(rows)));return
 if o=="remote":emit({"host":host,"port":port});return
 if o=="latency":t=time.time();s=socket.create_connection((host,port),timeout=5);ms=(time.time()-t)*1000;s.close();emit(ms);return
 if o=="echo-server":
  s=socket.socket();s.bind((host,port));s.listen(5)
  while True:c,_=s.accept();b=c.recv(65536);c.sendall(b);c.close()

def cert(host,port):
 ctx=ssl.create_default_context()
 with socket.create_connection((host,port),timeout=10) as raw:
  with ctx.wrap_socket(raw,server_hostname=host) as s:return s.getpeercert(),s.version(),s.getpeercert(binary_form=True)
def tls(o,a):
 host=a[0];port=int(a[1]) if len(a)>1 else 443;c,ver,der=cert(host,port)
 flat=lambda k:"; ".join("=".join(x) for g in c.get(k,()) for x in g)
 if o=="cert":emit(c);return
 if o=="subject":emit(flat("subject"));return
 if o=="issuer":emit(flat("issuer"));return
 if o=="serial":emit(c.get("serialNumber"));return
 if o=="expires":emit(c.get("notAfter"));return
 if o=="days-left":emit((ssl.cert_time_to_seconds(c["notAfter"])-time.time())/86400);return
 if o=="san":emit(c.get("subjectAltName",[]));return
 if o=="fingerprint":emit(hashlib.sha256(der).hexdigest());return
 if o=="protocol":emit(ver);return
 if o=="check":emit({"host":host,"protocol":ver,"expires":c.get("notAfter"),"sha256":hashlib.sha256(der).hexdigest()});return

def dns(o,a):
 host=a[0] if a else socket.gethostname()
 if o=="lookup":emit(socket.gethostbyname(host));return
 if o=="lookup-all":emit(sorted(set(x[4][0] for x in socket.getaddrinfo(host,None))));return
 if o=="reverse":emit(socket.gethostbyaddr(host));return
 if o=="fqdn":emit(socket.getfqdn(host));return
 if o=="hostname":emit(socket.gethostname());return
 if o=="hosts":print(P("/etc/hosts").read_text(errors="replace"),end="");return
 if o=="resolv":print(P("/etc/resolv.conf").read_text(errors="replace"),end="");return
 if o=="mx-hint":emit({"domain":host,"hint":"use the staged bind/dig package for MX records"});return
 if o=="local-ip":
  s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
  try:s.connect(("8.8.8.8",80));ip=s.getsockname()[0]
  except:ip="127.0.0.1"
  s.close();emit(ip);return
 if o=="summary":emit({"hostname":socket.gethostname(),"fqdn":socket.getfqdn(),"addresses":sorted(set(x[4][0] for x in socket.getaddrinfo(host,None)))});return

def sql(o,a):
 con=sqlite3.connect(a[0])
 if o=="query":cur=con.execute(a[1]);emit({"columns":[x[0] for x in cur.description] if cur.description else [],"rows":cur.fetchall()});return
 if o=="tables":emit([x[0] for x in con.execute("select name from sqlite_master where type='table' order by name")]);return
 if o=="schema":emit([x for x in con.execute("select type,name,sql from sqlite_master order by type,name")]);return
 if o=="indexes":emit([x for x in con.execute("select name,tbl_name,sql from sqlite_master where type='index'")]);return
 if o=="integrity":emit(con.execute("pragma integrity_check").fetchall());return
 if o=="backup":dst=sqlite3.connect(a[1]);con.backup(dst);dst.close();emit(a[1]);return
 if o=="dump":print("\n".join(con.iterdump()));return
 if o=="vacuum":con.execute("vacuum");con.commit();emit(True);return
 if o=="rowcount":emit(con.execute('select count(*) from "'+a[1].replace('"','""')+'"').fetchone()[0]);return
 if o=="info":emit({"path":str(P(a[0]).resolve()),"bytes":P(a[0]).stat().st_size if P(a[0]).exists() else 0,"sqlite":sqlite3.sqlite_version});return

def jget(x,p):
 cur=x
 for k in p.split(".") if p else []:cur=cur[int(k)] if isinstance(cur,list) else cur[k]
 return cur
def js(o,a):
 s=txt(a);x=json.loads(s)
 if o=="validate":emit(True);return
 if o=="pretty":emit(x);return
 if o=="compact":print(json.dumps(x,separators=(",",":")));return
 if o=="get":emit(jget(x,a[1]));return
 if o=="set":
  path=a[1].split(".");cur=x
  for k in path[:-1]:cur=cur.setdefault(k,{})
  cur[path[-1]]=a[2];emit(x);return
 if o=="merge":y=json.loads(txt(a,1));z=dict(x);z.update(y);emit(z);return
 if o=="diff":y=json.loads(txt(a,1));print("\n".join(difflib.unified_diff(json.dumps(x,indent=2,sort_keys=True).splitlines(),json.dumps(y,indent=2,sort_keys=True).splitlines(),lineterm="")));return
 if o=="keys":emit(sorted(x.keys()) if isinstance(x,dict) else []);return
 if o=="select":emit({k:x.get(k) for k in a[1:] if isinstance(x,dict)});return
 if o=="jsonl-count":emit(sum(1 for l in s.splitlines() if l.strip() and json.loads(l) is not None));return

def csvx(o,a):
 s=txt(a);rows=list(csv.reader(s.splitlines()))
 if o=="stats":emit({"rows":len(rows),"columns":max((len(r) for r in rows),default=0),"bytes":len(s.encode())});return
 if o=="to-json":emit(list(csv.DictReader(s.splitlines())));return
 if o=="from-json":
  arr=json.loads(s);keys=sorted({k for r in arr for k in r});w=csv.DictWriter(sys.stdout,fieldnames=keys);w.writeheader();w.writerows(arr);return
 if o=="select":idx=[int(x) for x in a[1].split(",")];emit([[r[i] if i<len(r) else "" for i in idx] for r in rows]);return
 if o=="filter":q=a[1].lower();emit([r for r in rows if q in ",".join(r).lower()]);return
 if o=="sort":emit(sorted(rows));return
 if o=="dedupe":emit([list(x) for x in dict.fromkeys(tuple(r) for r in rows)]);return
 if o=="head":emit(rows[:int(a[1]) if len(a)>1 else 10]);return
 if o=="tail":emit(rows[-(int(a[1]) if len(a)>1 else 10):]);return
 if o=="split":n=int(a[1]);emit([rows[i:i+n] for i in range(0,len(rows),n)]);return

def blob(o,a):
 b=P(a[0]).read_bytes() if a and P(a[0]).exists() else (a[0].encode() if a else sys.stdin.buffer.read())
 if o in ("sha256","sha512","md5"):emit(getattr(hashlib,o)(b).hexdigest());return
 if o=="base64":sys.stdout.write(base64.b64encode(b).decode());return
 if o=="unbase64":sys.stdout.buffer.write(base64.b64decode(b));return
 if o=="hex":sys.stdout.write(b.hex());return
 if o=="unhex":sys.stdout.buffer.write(bytes.fromhex(b.decode().strip()));return
 if o=="gzip":sys.stdout.buffer.write(gzip.compress(b));return
 if o=="gunzip":sys.stdout.buffer.write(gzip.decompress(b));return
 if o=="size":emit(len(b));return

def stream(o,a):
 s=txt(a);L=s.splitlines()
 if o=="lines":emit(len(L));return
 if o=="words":emit(len(s.split()));return
 if o=="chars":emit(len(s));return
 if o=="head":print("\n".join(L[:int(a[1]) if len(a)>1 else 10]));return
 if o=="tail":print("\n".join(L[-(int(a[1]) if len(a)>1 else 10):]));return
 if o=="grep":print("\n".join(x for x in L if a[1] in x));return
 if o=="dedupe":print("\n".join(dict.fromkeys(L)));return
 if o=="sort":print("\n".join(sorted(L)));return
 if o=="count":
  from collections import Counter;emit(dict(Counter(L)));return
 if o=="checksum":emit(hashlib.sha256(s.encode()).hexdigest());return

def kv(o,a):
 p=rfile("kv");d=load(p,{})
 if o=="set":d[a[0]]=a[1];save(p,d);emit(True);return
 if o=="get":emit(d.get(a[0]));return
 if o=="delete":d.pop(a[0],None);save(p,d);emit(True);return
 if o=="list" or o=="export":emit(d);return
 if o=="clear":save(p,{});emit(True);return
 if o=="has":emit(a[0] in d);return
 if o=="keys":emit(sorted(d));return
 if o=="import":d=json.loads(txt(a));save(p,d);emit(len(d));return
 if o=="stats":emit({"keys":len(d),"bytes":len(json.dumps(d).encode())});return

F={"repo":repo,"pkg":pkg,"proc":proc,"session":session,"service":service,"fs":fs,"envfile":envfile,"perm":perm,"watch":watch,"archive":archive,
"task":task,"state":state,"queue":queue,"event":event,"lock":lock,"approval":approval,"cap":cap,"exec":rexec,"job":job,"workspace":workspace,
"http":http,"tcp":tcp,"tls":tls,"dns":dns,"sqlite":sql,"json":js,"csv":csvx,"blob":blob,"stream":stream,"kv":kv}
if __name__=="__main__":
 if len(sys.argv)<3:raise SystemExit("GROUP OP [ARGS...]")
 F[sys.argv[1]](sys.argv[2],sys.argv[3:])
'''

def repo_names():
 try:paths=subprocess.check_output(["git","ls-tree","-r","--name-only","HEAD"],text=True).splitlines()
 except:return set()
 skip=("staging/shard-55/","staging/shard-56/","staging/shard-57/","staging/power-foundation-superpack/")
 return {Path(x).name.split("_",1)[0] for x in paths if x.endswith(".deb") and not x.startswith(skip)}

def dependencies(spec):
 g,_=spec
 if g=="pkg":return "python, apt, dpkg"
 if g=="repo":return "python, apt"
 if g=="session":return "python, tmux"
 return "python"

def control(pkg,label,spec):
 return f"""Package: {pkg}
Version: {VERSION}
Architecture: all
Maintainer: OceanStudio <packages@ocean.studio>
Section: utils
Priority: optional
Depends: {dependencies(spec)}
Description: {label} - {pkg}
 Self-contained non-root Ocean capability package with concrete local behavior.
 It has no maintainer-script side effects and requires no network at APT install.
"""

def meta_control(pkg,deps,desc):
 return f"""Package: {pkg}
Version: {VERSION}
Architecture: all
Maintainer: OceanStudio <packages@ocean.studio>
Section: metapackages
Priority: optional
Depends: {", ".join(f"{x} (= {VERSION})" for x in deps)}
Description: {desc}
 Meta-package installing the complete Ocean power capability shard.
"""

def launcher(pkg,g,o):
 return f'''#!/system/bin/sh
P="$PREFIX"
[ -n "$P" ] || P="{PREFIX}"
exec "$P/bin/python" "$P/lib/ocean-power/{pkg}.py" "{g}" "{o}" "$@"
'''

def build_one(pkg,spec,pool,label):
 g,o=spec
 with tempfile.TemporaryDirectory(prefix="ocean-power-") as td:
  root=Path(td)/pkg;(root/"DEBIAN").mkdir(parents=True)
  (root/"DEBIAN/control").write_text(control(pkg,label,spec))
  bind=root/PREFIX.strip("/")/"bin";bind.mkdir(parents=True)
  sh=bind/pkg;sh.write_text(launcher(pkg,g,o));sh.chmod(0o755)
  lib=root/PREFIX.strip("/")/"lib/ocean-power";lib.mkdir(parents=True)
  rt=lib/(pkg+".py");rt.write_text(RUNTIME);rt.chmod(0o755)
  art=pool/f"{pkg}_{VERSION}_all.deb"
  subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(art)],check=True,stdout=subprocess.DEVNULL)
  return art

def build_meta(pkg,deps,pool,desc):
 with tempfile.TemporaryDirectory(prefix="ocean-power-meta-") as td:
  root=Path(td)/pkg;(root/"DEBIAN").mkdir(parents=True)
  (root/"DEBIAN/control").write_text(meta_control(pkg,deps,desc))
  art=pool/f"{pkg}_{VERSION}_all.deb"
  subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(art)],check=True,stdout=subprocess.DEVNULL)
  return art

def rec(art,pkg,spec):
 raw=art.read_bytes();return {"package":pkg,"artifact":art.name,"group":spec[0] if spec else "meta","operation":spec[1] if spec else "meta","bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}

def write_index(out,rows):
 paras=[]
 for r in rows:
  art=out/"pool/main"/r["artifact"];fields=subprocess.check_output(["dpkg-deb","-f",str(art)],text=True).strip()
  paras.append(fields+f"\nFilename: {out.as_posix()}/pool/main/{art.name}\nSize: {r['bytes']}\nSHA256: {r['sha256']}\n")
 (out/"Packages.repaired").write_text("\n".join(paras))

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--shards",default="55,56,57");a=ap.parse_args()
 names=list(SYS)+list(AGENT)+list(CORE)
 if len(names)!=300 or len(set(names))!=300:raise SystemExit("catalog must be exactly 300 unique package names")
 existing=repo_names();coll=sorted(set(names)&existing)
 if coll:raise SystemExit("repo-wide collisions: "+", ".join(coll))
 suites=[];total=0
 for n in [x.strip() for x in a.shards.split(",") if x.strip()]:
  cat,outname,suite,label=SHARDS[n]
  out=Path(outname);pool=out/"pool/main"
  if out.exists():shutil.rmtree(out)
  pool.mkdir(parents=True)
  rows=[]
  for pkg,spec in cat.items():rows.append(rec(build_one(pkg,spec,pool,label),pkg,spec))
  rows.append(rec(build_meta(suite,list(cat),pool,"Ocean "+label+" suite"),suite,None))
  write_index(out,rows)
  (out/"provenance.json").write_text(json.dumps({"schemaVersion":1,"shard":n,"version":VERSION,"prefix":PREFIX,"commandPackageCount":100,"metaPackageCount":1,"packageCount":101,"suite":suite,"networkAtAptInstall":False,"rootRequired":False,"implementation":"self-contained functional commands; no placeholder aliases; no maintainer-script side effects","packages":rows},indent=2)+"\n")
  existing.update(cat);existing.add(suite);suites.append(suite);total+=len(rows)
 out=Path("staging/power-foundation-superpack");pool=out/"pool/main"
 if out.exists():shutil.rmtree(out)
 pool.mkdir(parents=True)
 row=rec(build_meta(SUPERPACK,suites,pool,"Ocean power-user and agent foundation superpack"),SUPERPACK,None);write_index(out,[row])
 (out/"provenance.json").write_text(json.dumps({"schemaVersion":1,"version":VERSION,"prefix":PREFIX,"dependsOn":suites,"newCommandPackages":300,"totalNewPackages":304},indent=2)+"\n")
 print(json.dumps({"newCommandPackages":300,"metaPackages":4,"totalNewPackages":304,"suites":suites},indent=2))

if __name__=="__main__":main()
