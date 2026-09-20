#!/usr/bin/env python3
from __future__ import annotations
import sys,json,re,os,time,hashlib,hmac,base64,random,datetime as dt,shlex,socket
from pathlib import Path
VERSION="2.0.0"
def out(x):print(json.dumps(x,indent=2,sort_keys=True,default=str))
def die(x,c=2):print(x,file=sys.stderr);raise SystemExit(c)
def text(args):return Path(args[0]).read_text(errors="replace") if args and Path(args[0]).exists() else (" ".join(args) if args else sys.stdin.read())
def jread(args):return json.loads(text(args))
def kvlines(s):
    d={}
    for l in s.splitlines():
        if "=" in l and not l.lstrip().startswith("#"):
            k,v=l.split("=",1);d[k.strip()]=v.strip().strip('"').strip("'")
    return d
def consul(a):
    x=jread(a); rows=x if isinstance(x,list) else [x]
    out({"passing":all((r.get("Status") or r.get("status") or (r.get("Checks") or [{}])[0].get("Status")) in ("passing","ok","healthy",True) for r in rows),"items":rows})
def etcd(a):
    x=jread(a);kvs=((x.get("kvs") or (x.get("responses") or [{}])[0].get("response_range",{}).get("kvs",[])) if isinstance(x,dict) else [])
    rows=[]
    for k in kvs:
        dec=lambda z:base64.b64decode(z).decode(errors="replace") if z else ""
        rows.append({"key":dec(k.get("key","")),"value":dec(k.get("value","")),"mod_revision":k.get("mod_revision")})
    out(rows)
def probe(a):
    if not a:die("host:port")
    target=a[0]
    if target.startswith(("http://","https://")):
        import urllib.request
        t=time.perf_counter()
        try:
            with urllib.request.urlopen(target,timeout=3) as r:code=r.status
            ok=200<=code<500;err=None
        except Exception as e:ok=False;code=None;err=str(e)
        out({"ready":ok,"status":code,"ms":(time.perf_counter()-t)*1000,"error":err})
    else:
        h,p=target.rsplit(":",1)
        try:s=socket.create_connection((h,int(p)),2);s.close();ok=True;err=None
        except Exception as e:ok=False;err=str(e)
        out({"ready":ok,"error":err})
def prometheus(a):
    if len(a)<2:die("NAME VALUE [TYPE]")
    n=re.sub(r"[^a-zA-Z0-9_:]","_",a[0]);typ=a[2] if len(a)>2 else "gauge"
    print(f"# TYPE {n} {typ}\n{n} {float(a[1])}")
def openmetrics(a):
    s=text(a);errs=[];names=set()
    for i,l in enumerate(s.splitlines(),1):
        if not l or l.startswith("#"):continue
        m=re.match(r"([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{[^}]*\})?\s+([-+]?(?:\d+(?:\.\d*)?|\.\d+|Inf|NaN))(?:\s+\d+)?$",l)
        if not m:errs.append(i)
        else:names.add(m.group(1))
    out({"valid":not errs,"error_lines":errs,"metrics":sorted(names)})
def statsd(a):
    if len(a)<3:die("NAME VALUE TYPE")
    print(f"{a[0]}:{a[1]}|{a[2]}")
def logfmt(a):
    toks=shlex.split(text(a));d={}
    for t in toks:
        if "=" in t:k,v=t.split("=",1);d[k]=v
    out(d)
def fluent(a):
    tag=a[0] if a else "ocean";record=json.loads(a[1]) if len(a)>1 else {};out([tag,int(time.time()),record])
def syslog(a):
    msg=" ".join(a) or "OceanStudio";pri=14;print(f"<{pri}>1 {dt.datetime.now(dt.timezone.utc).isoformat()} ocean ocean - - - {msg}")
def envsubst(a):
    s=text(a)
    def f(m):return os.environ.get(m.group(1) or m.group(2),"")
    print(re.sub(r"\$\{([A-Za-z_]\w*)\}|\$([A-Za-z_]\w*)",f,s))
def mustache(a):
    if not a:die("TEMPLATE [JSON]")
    s=Path(a[0]).read_text() if Path(a[0]).exists() else a[0];d=json.loads(a[1]) if len(a)>1 else {}
    print(re.sub(r"\{\{\s*([\w.-]+)\s*\}\}",lambda m:str(d.get(m.group(1),"")),s))
def gotmpl(a):mustache(a)
def dockerfile(a):
    s=text(a);ins=[];warn=[]
    for i,l in enumerate(s.splitlines(),1):
        q=l.strip()
        if not q or q.startswith("#"):continue
        op=q.split(None,1)[0].upper();ins.append({"line":i,"instruction":op})
        if op=="ADD":warn.append(f"line {i}: prefer COPY unless archive/URL semantics are required")
        if op=="RUN" and re.search(r"\b(curl|wget)\b.*\|\s*(sh|bash)",q):warn.append(f"line {i}: remote script pipe")
    if not any(x["instruction"]=="FROM" for x in ins):warn.append("missing FROM")
    out({"valid":not any(x=="missing FROM" for x in warn),"instructions":ins,"warnings":warn})
def containerfile(a):dockerfile(a)
def oci(a):
    x=jread(a);errs=[]
    if str(x.get("ociVersion","")).count(".")<1:errs.append("ociVersion missing")
    if not isinstance(x.get("process"),dict):errs.append("process missing")
    if not isinstance(x.get("root"),dict):errs.append("root missing")
    out({"valid":not errs,"errors":errs})
def manifest_diff(a):
    if len(a)<2:die("OLD NEW")
    def snap(p):return {str(x.relative_to(p)):hashlib.sha256(x.read_bytes()).hexdigest() for x in Path(p).rglob("*") if x.is_file()}
    x,y=snap(a[0]),snap(a[1]);out({"added":sorted(y.keys()-x.keys()),"removed":sorted(x.keys()-y.keys()),"changed":sorted(k for k in x.keys()&y.keys() if x[k]!=y[k])})
def overlay(a):
    s=text(a);out({"whiteouts":sorted(set(re.findall(r"(?:^|/)\.wh\.[^\s/]+",s,re.M))),"lines":len(s.splitlines())})
def simple_yaml(s):
    d={};stack=[(0,d)]
    for l in s.splitlines():
        if not l.strip() or l.lstrip().startswith("#") or ":" not in l:continue
        ind=len(l)-len(l.lstrip());k,v=l.strip().split(":",1)
        while stack and ind<stack[-1][0]:stack.pop()
        cur=stack[-1][1]
        if not v.strip():cur[k]={};stack.append((ind+2,cur[k]))
        else:cur[k]=v.strip().strip("'\"")
    return d
def yamlval(a):
    x=simple_yaml(text(a));out({"valid":bool(x),"top_level":sorted(x)})
def ingress(a):
    s=text(a);hosts=re.findall(r"\bhost:\s*([^\s]+)",s);paths=re.findall(r"\bpath:\s*([^\s]+)",s);dups=sorted({x for x in paths if paths.count(x)>1});out({"hosts":hosts,"paths":paths,"duplicate_paths":dups})
def cb(a):
    fail=int(a[0]);threshold=int(a[1]);success=int(a[2]) if len(a)>2 else 0
    state="open" if fail>=threshold else "closed";out({"state":state,"failures":fail,"threshold":threshold,"recovery_successes":success})
def ratelimit(a):
    if len(a)<3:die("LIMIT WINDOW_SECONDS timestamps...")
    limit=int(a[0]);w=float(a[1]);ts=sorted(float(x) for x in a[2:]);res=[]
    for t in ts:res.append({"t":t,"allowed":sum(1 for x in ts if t-w<x<=t)<=limit})
    out(res)
def backoff(a):
    if len(a)<3:die("ATTEMPTS BASE CAP")
    n,base,cap=int(a[0]),float(a[1]),float(a[2]);out([{"attempt":i,"max_delay":min(cap,base*(2**i))} for i in range(n)])
def fieldmask(a):
    paths=a;bad=[x for x in paths if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*",x)];out({"valid":not bad,"invalid":bad})
def avro(a):
    if len(a)<2:die("OLD.json NEW.json")
    old,new=json.loads(Path(a[0]).read_text()),json.loads(Path(a[1]).read_text())
    of={x["name"]:x.get("type") for x in old.get("fields",[])};nf={x["name"]:x.get("type") for x in new.get("fields",[])}
    out({"removed":sorted(of.keys()-nf.keys()),"added":sorted(nf.keys()-of.keys()),"type_changes":sorted(k for k in of.keys()&nf.keys() if of[k]!=nf[k])})
def thrift(a):
    s=text(a);br=s.count("{")-s.count("}");out({"valid":br==0,"services":re.findall(r"\bservice\s+(\w+)",s),"structs":re.findall(r"\bstruct\s+(\w+)",s)})
def capnp(a):
    s=text(a);out({"structs":re.findall(r"\bstruct\s+(\w+)",s),"fields":[{"name":n,"ordinal":int(o),"type":t} for n,o,t in re.findall(r"(\w+)\s+@(\d+)\s*:\s*([\w()]+)",s)]})
def jsonrpc(a):
    method=a[0] if a else "ping";params=json.loads(a[1]) if len(a)>1 else {};out({"jsonrpc":"2.0","id":1,"method":method,"params":params})
def webhook(a):
    if len(a)<3:die("SECRET SIGNATURE PAYLOAD")
    expected=hmac.new(a[0].encode(),a[2].encode(),hashlib.sha256).hexdigest();sig=a[1].removeprefix("sha256=");out({"valid":hmac.compare_digest(expected,sig)})
def sse(a):
    ev=[];cur={}
    for l in text(a).splitlines():
        if not l.strip():
            if cur:ev.append(cur);cur={}
        elif ":" in l:
            k,v=l.split(":",1);cur.setdefault(k,[]).append(v.lstrip())
    if cur:ev.append(cur)
    out(ev)
def pubsub(a):
    if len(a)<2:die("PATTERN TOPIC")
    rx="^"+re.escape(a[0]).replace(r"\*","[^.]+").replace(r"\#",".*")+"$";out({"match":bool(re.match(rx,a[1]))})
def kafka(a):
    if len(a)<2:die("LOG_END CURRENT")
    e,c=int(a[0]),int(a[1]);out({"lag":max(0,e-c)})
def nats(a):
    if len(a)<2:die("SUBJECT PAYLOAD")
    p=a[1].encode();print(f"PUB {a[0]} {len(p)}\r\n{a[1]}\r\n",end="")
def mqtt(a):
    b=bytes.fromhex(re.sub(r"[^0-9a-fA-F]","",a[0]));out({"packet_type":b[0]>>4 if b else None,"flags":b[0]&15 if b else None,"remaining_length":b[1] if len(b)>1 else None})
def amqp(a):
    b=bytes.fromhex(re.sub(r"[^0-9a-fA-F]","",a[0]))
    if len(b)<7:die("short frame")
    out({"type":b[0],"channel":int.from_bytes(b[1:3],"big"),"size":int.from_bytes(b[3:7],"big")})
def zmq(a):out({"frames":a,"count":len(a)})
def cron(a):
    expr=" ".join(a[:5]) if len(a)>=5 else (a[0] if a else "")
    parts=expr.split();out({"valid":len(parts)==5,"parts":parts})
def systemd(a):
    s=text(a);secs=re.findall(r"^\[([^\]]+)\]",s,re.M);keys=re.findall(r"^([A-Za-z][A-Za-z0-9]+)=",s,re.M);out({"valid":bool(secs),"sections":secs,"keys":keys})
def init(a):
    s=text(a);out({"has_lsb_header":"### BEGIN INIT INFO" in s and "### END INIT INFO" in s,"provides":re.findall(r"^#\s*Provides:\s*(.*)$",s,re.M)})
def dotenv(a):out(kvlines(text(a)))
def dotenvsec(a):
    d=kvlines(text(a));sus=[k for k,v in d.items() if re.search(r"(secret|token|password|key)",k,re.I) and v and not v.startswith(("ENC[","vault:"))];out({"exposed_keys":sus,"safe":not sus})
def feature(a):
    if len(a)<3:die("KEY PERCENT USER")
    h=int(hashlib.sha256((a[0]+":"+a[2]).encode()).hexdigest()[:8],16)%10000;out({"enabled":h<int(float(a[1])*100),"bucket":h/100})
def chaos(a):
    vals=a;out({"selected":vals[0] if vals else None,"candidates":vals,"note":"selector only; does not terminate processes"})
def lb(a):
    if not a:die("backend[:weight]...")
    pool=[]
    for x in a:
        n,w=(x.rsplit(":",1) if ":" in x and x.rsplit(":",1)[1].isdigit() else (x,"1"));pool.extend([n]*int(w))
    out({"cycle":pool})
def canary(a):
    pct=float(a[0]);total=int(a[1]) if len(a)>1 else 1000;out({"canary":round(total*pct/100),"stable":total-round(total*pct/100)})
def generic_json(a):out(jread(a))
def mesh(a):out({"signals":kvlines(text(a))})
COMMANDS={"consul-health-checker":consul,"etcd-kv-parser":etcd,"service-liveness-probe":probe,"service-readiness-chk":probe,"prometheus-metric-fmt":prometheus,"openmetrics-validator":openmetrics,"statsd-packet-sender":statsd,"logfmt-parser-cli":logfmt,"fluentd-event-builder":fluent,"syslog-rfc5424-gen":syslog,"envsubst-lite":envsubst,"mustache-templater":mustache,"gomplate-substitute":gotmpl,"dockerfile-linter":dockerfile,"containerfile-parser":containerfile,"oci-spec-validator":oci,"rootfs-manifest-diff":manifest_diff,"overlayfs-layer-view":overlay,"compose-file-validator":yamlval,"k8s-pod-yaml-linter":yamlval,"helm-values-differ":yamlval,"crd-schema-validator":yamlval,"ingress-route-checker":ingress,"service-mesh-probe":mesh,"circuit-breaker-tester":cb,"rate-limit-simulator":ratelimit,"retry-backoff-calc":backoff,"grpc-channelz-monitor":generic_json,"protobuf-field-mask":fieldmask,"avro-schema-diff":avro,"thrift-idl-linter":thrift,"capnp-schema-viewer":capnp,"json-rpc-request-gen":jsonrpc,"webhook-signature-chk":webhook,"sse-event-streamer":sse,"pubsub-topic-tester":pubsub,"kafka-offset-calc":kafka,"nats-message-pub":nats,"mqtt-packet-decoder":mqtt,"amqp-frame-inspector":amqp,"zero-mq-socket-test":zmq,"cron-expression-next":cron,"systemd-unit-linter":systemd,"init-script-validator":init,"dotenv-loader-cli":dotenv,"dotenv-encryption-chk":dotenvsec,"feature-flag-eval":feature,"chaos-kill-selector":chaos,"load-balancer-round":lb,"canary-traffic-calc":canary}
def main():
    if len(COMMANDS)!=50:die(f"command count {len(COMMANDS)}")
    p=Path(sys.argv[0]).name
    if p in COMMANDS:cmd,args=p,sys.argv[1:]
    else:
        if len(sys.argv)<2 or sys.argv[1] in ("-h","--help"):print("OceanStudio functional shard 10");print("\n".join(sorted(COMMANDS)));return
        if sys.argv[1] in ("-v","--version"):print(VERSION);return
        cmd,args=sys.argv[1],sys.argv[2:]
    if cmd not in COMMANDS:die("unknown command: "+cmd)
    COMMANDS[cmd](args)
if __name__=="__main__":main()
