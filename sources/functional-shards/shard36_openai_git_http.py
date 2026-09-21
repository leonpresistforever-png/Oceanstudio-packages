#!/usr/bin/env python3
from __future__ import annotations
import base64,email.utils,http.cookies,importlib.metadata,json,os,re,shlex,shutil,subprocess,sys,time,tomllib,urllib.parse,uuid
from pathlib import Path
from collections import Counter
P=Path

OPENAI=[
"openai-env-check","openai-key-format","openai-base-url","openai-project-header","openai-org-header","openai-request-headers","openai-responses-request","openai-responses-input","openai-responses-tools","openai-responses-json-schema","openai-responses-stream-events","openai-responses-output-text","openai-response-usage","openai-response-status","openai-response-errors","openai-files-request","openai-batches-request","openai-embeddings-request","openai-images-request","openai-audio-request","openai-realtime-url","openai-realtime-session","openai-realtime-event-types","openai-realtime-sdp-info","openai-agents-config","openai-agents-tools","openai-agents-handoffs","openai-agents-guardrails","openai-agents-model-settings","openai-agents-trace-id","openai-agents-span-summary","openai-mcp-tool-schema","openai-mcp-server-config","openai-codex-config","openai-codex-model","openai-codex-sandbox","openai-codex-approval-policy","openai-sdk-node-check","openai-sdk-python-check","openai-health"]
GIT=[
"gitplus-repo-root","gitplus-head","gitplus-branch","gitplus-upstream","gitplus-remotes","gitplus-status-counts","gitplus-staged","gitplus-unstaged","gitplus-untracked","gitplus-conflicts","gitplus-last-author","gitplus-last-date","gitplus-last-subject","gitplus-log-oneline","gitplus-tags","gitplus-branches","gitplus-remote-branches","gitplus-merge-base","gitplus-ahead-behind","gitplus-file-history","gitplus-blame-line","gitplus-tree","gitplus-object-exists","gitplus-submodules","gitplus-worktrees","gitplus-hooks","gitplus-lfs-detect","gitplus-ignore-check","gitplus-config-origin","gitplus-health"]
HTTP=[
"httpx-request-line","httpx-url","httpx-method","httpx-header-set","httpx-header-get","httpx-header-remove","httpx-query-set","httpx-query-get","httpx-form-encode","httpx-json-body","httpx-curl","httpx-wget","httpx-python-request","httpx-node-fetch","httpx-status-class","httpx-cache-control","httpx-etag","httpx-content-range","httpx-range","httpx-cookie-jar","httpx-set-cookie","httpx-auth-basic","httpx-auth-bearer","httpx-multipart","httpx-sse-events","httpx-ndjson","httpx-retry-after","httpx-link-header","httpx-cors-check","httpx-health"]
COMMANDS=OPENAI+GIT+HTTP
assert len(COMMANDS)==100 and len(set(COMMANDS))==100

def emit(x):
    if isinstance(x,(dict,list,tuple,Counter)):print(json.dumps(x,indent=2,ensure_ascii=False,default=str))
    else:print(x)
def die(s,c=2):print(s,file=sys.stderr);raise SystemExit(c)
def loadj(arg):
    p=P(arg)
    if p.exists() and p.is_file():return json.loads(p.read_text())
    return json.loads(arg)
def readtext(arg):
    p=P(arg)
    return p.read_text(errors="replace") if p.exists() and p.is_file() else arg
def mask(s):
    if not s:return None
    return s[:7]+"…"+s[-4:] if len(s)>14 else "<set>"
def base_url():
    return os.environ.get("OPENAI_BASE_URL","https://api.openai.com/v1").rstrip("/")
def event_rows(s):
    out=[];event=None;data=[]
    for line in s.splitlines()+[""]:
        if line.startswith("event:"):event=line[6:].strip()
        elif line.startswith("data:"):data.append(line[5:].lstrip())
        elif not line and (event or data):
            raw="\n".join(data);obj=raw
            if raw and raw!="[DONE]":
                try:obj=json.loads(raw)
                except:pass
            out.append({"event":event,"data":obj});event=None;data=[]
    return out

def response_text(d):
    if isinstance(d,dict) and isinstance(d.get("output_text"),str):return d["output_text"]
    texts=[]
    for item in d.get("output",[]) if isinstance(d,dict) else []:
        if not isinstance(item,dict):continue
        for c in item.get("content",[]) if isinstance(item.get("content"),list) else []:
            if isinstance(c,dict):
                if isinstance(c.get("text"),str):texts.append(c["text"])
                elif isinstance(c.get("output_text"),str):texts.append(c["output_text"])
    return "".join(texts)

def openai(cmd,a):
    op=cmd
    key=os.environ.get("OPENAI_API_KEY")
    if op=="openai-env-check":
        emit({"api_key":bool(key),"api_key_masked":mask(key),"base_url":base_url(),"project":bool(os.environ.get("OPENAI_PROJECT")),"organization":bool(os.environ.get("OPENAI_ORG_ID") or os.environ.get("OPENAI_ORGANIZATION"))});return
    if op=="openai-key-format":
        s=a[0] if a else key or "";emit({"set":bool(s),"prefix":s.split("-",2)[:2] if s else [],"looks_project_key":s.startswith("sk-proj-"),"length":len(s)});return
    if op=="openai-base-url":print(base_url());return
    if op=="openai-project-header":emit({"OpenAI-Project":os.environ.get("OPENAI_PROJECT")});return
    if op=="openai-org-header":emit({"OpenAI-Organization":os.environ.get("OPENAI_ORG_ID") or os.environ.get("OPENAI_ORGANIZATION")});return
    if op=="openai-request-headers":
        h={"Content-Type":"application/json","Authorization":"Bearer "+("<set>" if key else "<OPENAI_API_KEY>")}
        if os.environ.get("OPENAI_PROJECT"):h["OpenAI-Project"]=os.environ["OPENAI_PROJECT"]
        if os.environ.get("OPENAI_ORG_ID") or os.environ.get("OPENAI_ORGANIZATION"):h["OpenAI-Organization"]=os.environ.get("OPENAI_ORG_ID") or os.environ.get("OPENAI_ORGANIZATION")
        emit(h);return
    if op=="openai-responses-request":
        model=a[0] if a else "gpt-5";inp=" ".join(a[1:]) if len(a)>1 else "Hello";emit({"method":"POST","url":base_url()+"/responses","json":{"model":model,"input":inp}});return
    if op=="openai-responses-input":
        d=loadj(a[0]);emit(d.get("input"));return
    if op=="openai-responses-tools":
        d=loadj(a[0]);emit(d.get("tools",[]));return
    if op=="openai-responses-json-schema":
        name=a[0] if a else "result";schema=loadj(a[1]) if len(a)>1 else {"type":"object"};emit({"type":"json_schema","name":name,"schema":schema,"strict":True});return
    if op=="openai-responses-stream-events":
        emit(event_rows(readtext(a[0] if a else sys.stdin.read())));return
    if op=="openai-responses-output-text":
        d=loadj(a[0]);print(response_text(d));return
    if op=="openai-response-usage":
        d=loadj(a[0]);emit(d.get("usage",{}));return
    if op=="openai-response-status":
        d=loadj(a[0]);emit({"id":d.get("id"),"status":d.get("status"),"completed_at":d.get("completed_at"),"incomplete_details":d.get("incomplete_details")});return
    if op=="openai-response-errors":
        d=loadj(a[0]);emit({"error":d.get("error"),"incomplete_details":d.get("incomplete_details")});return
    if op=="openai-files-request":emit({"method":"POST","url":base_url()+"/files","purpose":a[0] if a else "assistants","file":a[1] if len(a)>1 else "<FILE>"});return
    if op=="openai-batches-request":emit({"method":"POST","url":base_url()+"/batches","json":{"input_file_id":a[0] if a else "<FILE_ID>","endpoint":a[1] if len(a)>1 else "/v1/responses","completion_window":"24h"}});return
    if op=="openai-embeddings-request":emit({"method":"POST","url":base_url()+"/embeddings","json":{"model":a[0] if a else "text-embedding-3-small","input":" ".join(a[1:]) if len(a)>1 else "hello"}});return
    if op=="openai-images-request":emit({"method":"POST","url":base_url()+"/images/generations","json":{"model":a[0] if a else "gpt-image-1","prompt":" ".join(a[1:]) if len(a)>1 else "an image"}});return
    if op=="openai-audio-request":emit({"method":"POST","url":base_url()+"/audio/speech","json":{"model":a[0] if a else "gpt-4o-mini-tts","input":" ".join(a[1:]) if len(a)>1 else "hello","voice":"alloy"}});return
    if op=="openai-realtime-url":
        model=a[0] if a else "";url=base_url().replace("https://","wss://").replace("http://","ws://")+"/realtime"+(("?model="+urllib.parse.quote(model)) if model else "");print(url);return
    if op=="openai-realtime-session":
        emit({"type":"session.update","session":{"modalities":["text","audio"],"instructions":" ".join(a) if a else "You are helpful."}});return
    if op=="openai-realtime-event-types":
        s=readtext(a[0] if a else sys.stdin.read());vals=[]
        for line in s.splitlines():
            try:
                d=json.loads(line)
                if isinstance(d,dict) and d.get("type"):vals.append(d["type"])
            except:pass
        emit(Counter(vals));return
    if op=="openai-realtime-sdp-info":
        s=readtext(a[0]);emit({"lines":len(s.splitlines()),"audio":sum(l.startswith("m=audio") for l in s.splitlines()),"ice_candidates":sum(l.startswith("a=candidate:") for l in s.splitlines()),"fingerprints":[l for l in s.splitlines() if l.startswith("a=fingerprint:")]});return
    if op=="openai-agents-config":
        emit({"model":os.environ.get("OPENAI_DEFAULT_MODEL"),"tracing_disabled":os.environ.get("OPENAI_AGENTS_DISABLE_TRACING"),"api_key":bool(key)});return
    if op in ("openai-agents-tools","openai-agents-handoffs","openai-agents-guardrails","openai-agents-model-settings"):
        d=loadj(a[0]);k={"openai-agents-tools":"tools","openai-agents-handoffs":"handoffs","openai-agents-guardrails":"guardrails","openai-agents-model-settings":"modelSettings"}[op];emit(d.get(k,[] if k!="modelSettings" else {}));return
    if op=="openai-agents-trace-id":print("trace_"+uuid.uuid4().hex);return
    if op=="openai-agents-span-summary":
        d=loadj(a[0]);sp=d if isinstance(d,list) else d.get("spans",[]);emit({"count":len(sp),"types":Counter(x.get("type","unknown") for x in sp if isinstance(x,dict))});return
    if op=="openai-mcp-tool-schema":
        name=a[0] if a else "tool";schema=loadj(a[1]) if len(a)>1 else {"type":"object","properties":{}};emit({"name":name,"inputSchema":schema});return
    if op=="openai-mcp-server-config":
        emit({"type":"mcp","server_label":a[0] if a else "server","server_url":a[1] if len(a)>1 else "http://127.0.0.1:8000/mcp"});return
    codex=P.home()/".codex/config.toml"
    if op=="openai-codex-config":
        emit(tomllib.loads(codex.read_text()) if codex.exists() else {});return
    if op in ("openai-codex-model","openai-codex-sandbox","openai-codex-approval-policy"):
        d=tomllib.loads(codex.read_text()) if codex.exists() else {}
        keyname={"openai-codex-model":"model","openai-codex-sandbox":"sandbox_mode","openai-codex-approval-policy":"approval_policy"}[op];emit(d.get(keyname));return
    if op=="openai-sdk-node-check":
        roots=[P.cwd()/"node_modules/openai/package.json",P(os.environ.get("PREFIX","/data/data/studio.ocean.app/files/usr"))/"lib/node_modules/openai/package.json"];found=[]
        for p in roots:
            if p.exists():
                d=json.loads(p.read_text());found.append({"path":str(p),"version":d.get("version")})
        emit(found);return
    if op=="openai-sdk-python-check":
        try:v=importlib.metadata.version("openai")
        except:v=None
        emit({"installed":bool(v),"version":v});return
    if op=="openai-health":
        emit({"api_key":bool(key),"base_url":base_url(),"node":shutil.which("node"),"python":shutil.which("python") or shutil.which("python3"),"curl":shutil.which("curl"),"sdk_node":(P.cwd()/"node_modules/openai/package.json").exists()});return

def gitrun(args,cwd=None,ok=(0,)):
    p=subprocess.run(["git"]+args,cwd=cwd,capture_output=True,text=True)
    if p.returncode not in ok:die(p.stderr.strip() or p.stdout.strip() or "git failed")
    return p.stdout.rstrip("\n")
def gitroot(a):
    cwd=a[0] if a and P(a[0]).is_dir() else None
    return gitrun(["rev-parse","--show-toplevel"],cwd=cwd)
def git(cmd,a):
    cwd=a[0] if a and P(a[0]).is_dir() else None
    if cmd=="gitplus-repo-root":print(gitroot(a));return
    if cmd=="gitplus-head":print(gitrun(["rev-parse","HEAD"],cwd));return
    if cmd=="gitplus-branch":print(gitrun(["branch","--show-current"],cwd));return
    if cmd=="gitplus-upstream":
        p=subprocess.run(["git","rev-parse","--abbrev-ref","--symbolic-full-name","@{u}"],cwd=cwd,capture_output=True,text=True);print(p.stdout.strip() if p.returncode==0 else "");return
    if cmd=="gitplus-remotes":
        rows=[]
        for l in gitrun(["remote","-v"],cwd).splitlines():
            q=l.split()
            if len(q)>=3:rows.append({"name":q[0],"url":q[1],"kind":q[2].strip("()")})
        emit(rows);return
    if cmd=="gitplus-status-counts":
        c=Counter()
        for l in gitrun(["status","--porcelain=v1"],cwd).splitlines():
            if l.startswith("??"):c["untracked"]+=1
            else:
                if l[0]!=" ":c["staged"]+=1
                if len(l)>1 and l[1]!=" ":c["unstaged"]+=1
                if "U" in l[:2]:c["conflicts"]+=1
        emit(c);return
    if cmd in ("gitplus-staged","gitplus-unstaged","gitplus-untracked","gitplus-conflicts"):
        lines=gitrun(["status","--porcelain=v1"],cwd).splitlines()
        if cmd=="gitplus-staged":out=[l[3:] for l in lines if not l.startswith("??") and l[0]!=" "]
        elif cmd=="gitplus-unstaged":out=[l[3:] for l in lines if not l.startswith("??") and len(l)>1 and l[1]!=" "]
        elif cmd=="gitplus-untracked":out=[l[3:] for l in lines if l.startswith("??")]
        else:out=[l[3:] for l in lines if "U" in l[:2]]
        emit(out);return
    fmap={"gitplus-last-author":"%an <%ae>","gitplus-last-date":"%aI","gitplus-last-subject":"%s"}
    if cmd in fmap:print(gitrun(["log","-1","--pretty="+fmap[cmd]],cwd));return
    if cmd=="gitplus-log-oneline":
        n=a[1] if cwd and len(a)>1 else a[0] if a and not cwd else "20";print(gitrun(["log","-"+str(n),"--oneline","--decorate"],cwd));return
    if cmd=="gitplus-tags":emit(gitrun(["tag","--list"],cwd).splitlines());return
    if cmd=="gitplus-branches":emit(gitrun(["branch","--format=%(refname:short)"],cwd).splitlines());return
    if cmd=="gitplus-remote-branches":emit(gitrun(["branch","-r","--format=%(refname:short)"],cwd).splitlines());return
    if cmd=="gitplus-merge-base":
        args=a[1:] if cwd else a
        if len(args)<2:die("A B")
        print(gitrun(["merge-base",args[0],args[1]],cwd));return
    if cmd=="gitplus-ahead-behind":
        args=a[1:] if cwd else a
        ref=args[0] if args else "@{u}"
        p=subprocess.run(["git","rev-list","--left-right","--count",f"HEAD...{ref}"],cwd=cwd,capture_output=True,text=True)
        if p.returncode:emit({"ahead":None,"behind":None});return
        ahead,behind=map(int,p.stdout.split());emit({"ahead":ahead,"behind":behind});return
    if cmd=="gitplus-file-history":
        path=a[1] if cwd and len(a)>1 else a[0] if a else die("FILE");print(gitrun(["log","--oneline","--",path],cwd));return
    if cmd=="gitplus-blame-line":
        args=a[1:] if cwd else a
        if len(args)<2:die("FILE LINE")
        print(gitrun(["blame","-L",f"{args[1]},{args[1]}","--",args[0]],cwd));return
    if cmd=="gitplus-tree":emit(gitrun(["ls-tree","-r","--name-only","HEAD"],cwd).splitlines());return
    if cmd=="gitplus-object-exists":
        obj=a[1] if cwd and len(a)>1 else a[0];p=subprocess.run(["git","cat-file","-e",obj],cwd=cwd);print(str(p.returncode==0).lower());return
    if cmd=="gitplus-submodules":print(gitrun(["submodule","status"],cwd));return
    if cmd=="gitplus-worktrees":print(gitrun(["worktree","list","--porcelain"],cwd));return
    if cmd=="gitplus-hooks":
        r=P(gitroot(a))/".git/hooks";emit([x.name for x in r.glob("*") if x.is_file() and not x.name.endswith(".sample")]);return
    if cmd=="gitplus-lfs-detect":emit({"gitattributes":(P(gitroot(a))/".gitattributes").exists(),"git_lfs":shutil.which("git-lfs")});return
    if cmd=="gitplus-ignore-check":
        path=a[1] if cwd and len(a)>1 else a[0];p=subprocess.run(["git","check-ignore","-v",path],cwd=cwd,capture_output=True,text=True);emit({"ignored":p.returncode==0,"rule":p.stdout.strip()});return
    if cmd=="gitplus-config-origin":print(gitrun(["config","--list","--show-origin"],cwd));return
    if cmd=="gitplus-health":emit({"root":gitroot(a),"branch":gitrun(["branch","--show-current"],cwd),"head":gitrun(["rev-parse","--short","HEAD"],cwd),"git":shutil.which("git")});return

def parse_headers(s):
    out={}
    for l in s.splitlines():
        if ":" in l:
            k,v=l.split(":",1);out[k.strip()]=v.strip()
    return out
def request_obj(a):
    if a and P(a[0]).exists() and P(a[0]).is_file():
        try:return json.loads(P(a[0]).read_text())
        except:return {"url":P(a[0]).read_text().strip()}
    if a and a[0].lstrip().startswith("{"):return json.loads(a[0])
    return {"url":a[0] if a else "https://example.com","method":a[1].upper() if len(a)>1 else "GET","headers":{}}
def httpx(cmd,a):
    op=cmd
    if op=="httpx-form-encode":
        pairs=[x.split("=",1) if "=" in x else (x,"") for x in a];print(urllib.parse.urlencode(pairs));return
    if op=="httpx-status-class":
        n=int(a[0]);print("informational" if n<200 else "success" if n<300 else "redirection" if n<400 else "client-error" if n<500 else "server-error");return
    if op=="httpx-auth-basic":
        raw=((a[0] if a else "")+":"+(a[1] if len(a)>1 else "")).encode();print("Basic "+base64.b64encode(raw).decode());return
    if op=="httpx-auth-bearer":print("Bearer "+(a[0] if a else "<TOKEN>"));return
    if op=="httpx-sse-events":emit(event_rows(readtext(a[0] if a else sys.stdin.read())));return
    if op=="httpx-ndjson":
        s=readtext(a[0] if a else sys.stdin.read());emit([json.loads(l) for l in s.splitlines() if l.strip()]);return
    if op=="httpx-retry-after":
        s=a[0]
        try:print(max(0,int(s)))
        except:
            dt=email.utils.parsedate_to_datetime(s);print(max(0,int(dt.timestamp()-time.time())))
        return
    if op=="httpx-link-header":
        s=" ".join(a);rows=[]
        for part in re.split(r",\s*(?=<)",s):
            m=re.match(r"<([^>]+)>(.*)",part)
            if not m:continue
            params={}
            for q in m.group(2).split(";"):
                if "=" in q:
                    k,v=q.split("=",1);params[k.strip()]=v.strip().strip('"')
            rows.append({"url":m.group(1),"params":params})
        emit(rows);return
    if op=="httpx-cookie-jar":
        c=http.cookies.SimpleCookie();c.load(" ".join(a));emit({k:v.value for k,v in c.items()});return
    if op=="httpx-set-cookie":
        c=http.cookies.SimpleCookie();c.load(" ".join(a));emit({k:{"value":v.value,"path":v["path"],"domain":v["domain"],"secure":bool(v["secure"]),"httponly":bool(v["httponly"]),"samesite":v["samesite"]} for k,v in c.items()});return
    if op=="httpx-cache-control":
        vals={}
        for x in " ".join(a).split(","):
            x=x.strip()
            if not x:continue
            if "=" in x:
                k,v=x.split("=",1);vals[k.lower()]=v.strip('"')
            else:vals[x.lower()]=True
        emit(vals);return
    if op=="httpx-etag":
        s=a[0] if a else "";emit({"weak":s.startswith("W/"),"value":s[2:] if s.startswith("W/") else s});return
    if op=="httpx-content-range":
        m=re.fullmatch(r"(\w+)\s+(\d+)-(\d+)/(\d+|\*)",a[0]);emit({"unit":m.group(1),"start":int(m.group(2)),"end":int(m.group(3)),"total":None if m.group(4)=="*" else int(m.group(4))} if m else {});return
    if op=="httpx-range":
        start=int(a[0]);end=int(a[1]) if len(a)>1 else None;print("bytes="+str(start)+"-"+("" if end is None else str(end)));return
    if op=="httpx-multipart":
        boundary="----Ocean"+uuid.uuid4().hex;emit({"content_type":"multipart/form-data; boundary="+boundary,"boundary":boundary});return
    if op=="httpx-cors-check":
        h=parse_headers(readtext(a[0]));emit({"allow_origin":h.get("Access-Control-Allow-Origin"),"allow_methods":h.get("Access-Control-Allow-Methods"),"allow_headers":h.get("Access-Control-Allow-Headers"),"credentials":h.get("Access-Control-Allow-Credentials")});return
    if op=="httpx-health":emit({"curl":shutil.which("curl"),"wget":shutil.which("wget"),"python":shutil.which("python") or shutil.which("python3"),"node":shutil.which("node")});return
    r=request_obj(a);r.setdefault("method","GET");r.setdefault("headers",{})
    if op=="httpx-request-line":print(r["method"].upper()+" "+urllib.parse.urlsplit(r["url"]).path+(("?"+urllib.parse.urlsplit(r["url"]).query) if urllib.parse.urlsplit(r["url"]).query else "")+" HTTP/1.1");return
    if op=="httpx-url":print(r["url"]);return
    if op=="httpx-method":print(r["method"].upper());return
    if op=="httpx-header-set":
        if len(a)<3:die("REQUEST_JSON NAME VALUE")
        r["headers"][a[1]]=a[2];emit(r);return
    if op=="httpx-header-get":emit(next((v for k,v in r["headers"].items() if k.lower()==a[1].lower()),None));return
    if op=="httpx-header-remove":
        q={k:v for k,v in r["headers"].items() if k.lower()!=a[1].lower()};r["headers"]=q;emit(r);return
    if op in ("httpx-query-set","httpx-query-get"):
        u=urllib.parse.urlsplit(r["url"]);pairs=urllib.parse.parse_qsl(u.query,keep_blank_values=True)
        key=a[1]
        if op=="httpx-query-get":emit([v for k,v in pairs if k==key]);return
        val=a[2] if len(a)>2 else "";pairs=[(k,v) for k,v in pairs if k!=key]+[(key,val)];r["url"]=urllib.parse.urlunsplit((u.scheme,u.netloc,u.path,urllib.parse.urlencode(pairs),u.fragment));emit(r);return
    if op=="httpx-json-body":
        r["headers"]["Content-Type"]="application/json";r["body"]=loadj(a[1]) if len(a)>1 else {};emit(r);return
    if op=="httpx-curl":
        parts=["curl","-X",r["method"].upper()]
        for k,v in r["headers"].items():parts+=["-H",k+": "+str(v)]
        if "body" in r:parts+=["--data",json.dumps(r["body"],separators=(",",":"))]
        parts.append(r["url"]);print(" ".join(shlex.quote(x) for x in parts));return
    if op=="httpx-wget":
        parts=["wget","--method="+r["method"].upper()]
        for k,v in r["headers"].items():parts+=["--header",k+": "+str(v)]
        parts.append(r["url"]);print(" ".join(shlex.quote(x) for x in parts));return
    if op=="httpx-python-request":
        print("import urllib.request, json\nreq=urllib.request.Request("+repr(r["url"])+",method="+repr(r["method"].upper())+",headers="+repr(r["headers"])+")\nprint(urllib.request.urlopen(req).read().decode())");return
    if op=="httpx-node-fetch":
        print("const r=await fetch("+json.dumps(r["url"])+",{method:"+json.dumps(r["method"].upper())+",headers:"+json.dumps(r["headers"])+"}); console.log(await r.text());");return

def main():
    cmd=P(sys.argv[0]).name;a=sys.argv[1:]
    if cmd not in COMMANDS:
        if a and a[0] in COMMANDS:cmd=a.pop(0)
        elif not a or a[0] in ("-h","--help"):
            print("Shard 36 — OpenAI API, Git and HTTP tooling");print("\n".join(COMMANDS));return
        else:die("unknown command")
    if a and a[0] in ("-h","--help"):print(cmd+" — functional shard 36 utility");return
    if cmd in OPENAI:openai(cmd,a)
    elif cmd in GIT:git(cmd,a)
    else:httpx(cmd,a)
if __name__=="__main__":main()
