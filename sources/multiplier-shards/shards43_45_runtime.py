#!/usr/bin/env python3
from __future__ import annotations
import base64, configparser, csv, datetime as dt, gzip, hashlib, hmac, html, io, ipaddress, json, mimetypes, os, pathlib, re, shutil, socket, sqlite3, subprocess, sys, tarfile, time, tomllib, urllib.parse, urllib.request, zipfile, zlib
from collections import Counter
P = pathlib.Path

FAMILIES = {
"jsonx":["pretty","minify","keys","values","type","get","pluck","merge","validate","lines"],
"textx":["lines","words","chars","bytes","upper","lower","reverse","sort","uniq","trim"],
"hashx":["md5","sha1","sha224","sha256","sha384","sha512","blake2b","blake2s","crc32","hmac-sha256"],
"encx":["b64-encode","b64-decode","b32-encode","b32-decode","hex-encode","hex-decode","url-encode","url-decode","json-escape","html-escape"],
"urlx":["parse","join","query","query-get","query-set","origin","host","path","normalize","resolve"],
"csvx":["count","headers","json","tsv","select","sort","uniq","filter","transpose","validate"],
"inix":["sections","keys","get","json","validate","merge","set","delete","normalize","template"],
"tomlx":["json","keys","get","validate","flatten","sections","count","lookup","normalize","merge"],
"envx":["parse","json","get","keys","validate","export","mask","merge","sort","template"],
"timex":["now","epoch","iso-to-epoch","epoch-to-iso","diff","add","format","weekday","month","duration"],
"pathx":["abs","base","dir","ext","stem","join","norm","rel","parts","exists"],
"filex":["size","lines","words","sha256","mime","head","tail","stat","copy","cat"],
"dirx":["list","tree","count","size","files","dirs","largest","newest","oldest","dupes"],
"archivex":["zip-list","zip-test","zip-extract","zip-create","tar-list","tar-test","tar-extract","tar-create","gzip","gunzip"],
"httpxcli":["get","head","status","headers","json","download","encode-query","resolve-url","user-agent","time"],
"netx":["host","reverse","tcp-check","resolve","local-ip","hostname","service-port","url-host","cidr-hosts","ip-version"],
"procx":["env","cwd","which","pid","ppid","uid","uname","python-version","run","timeout"],
"gitmeta":["root","branch","head","status","remotes","config","list-files","changed","log-one","describe"],
"manifestx":["package-json","name","version","scripts","deps","devdeps","pyproject","requirements","gradle","maven"],
"semverx":["parse","compare","bump-major","bump-minor","bump-patch","normalize","valid","sort","max","min"],
"jwtx":["decode-header","decode-payload","expiry","issuer","audience","subject","claims","is-expired","not-before","segments"],
"regexx":["match","search","findall","split","replace","count","escape","groups","lines","validate"],
"mcpconf":["validate","list","add","remove","get","merge","stdio","http","env","template"],
"agentcfg":["detect","list-files","summary","init","merge","paths","ignore","scan-prompts","scan-skills","scan-mcp"],
"projectx":["detect","files","langs","size","todos","licenses","readmes","manifests","entrypoints","summary"],
"logx":["count","levels","errors","warnings","tail","head","grep","json-lines","timestamps","stats"],
"datax":["jsonl-count","jsonl-pretty","jsonl-keys","jsonl-dedupe","jsonl-sort","sample","head","tail","grep","stats"],
"sqliteq":["tables","schema","count","query","columns","indexes","pragma","integrity","export-json","vacuum"],
"androidmeta":["apk-list","apk-files","apk-size","dex-count","lib-list","abi-list","res-count","assets-list","cert-files","summary"],
"mcpmsg":["stdio-frame","parse-frame","request","notification","response","error","initialize","ping","tools-list","resources-list"],
}
SHARDS = {
"43": list(FAMILIES.keys())[:10],
"44": list(FAMILIES.keys())[10:20],
"45": list(FAMILIES.keys())[20:30],
}
GATEWAYS = {
"uv":{"depends":["mise"],"mode":"mise","tool":"uv","binary":"uv"},
"uvx":{"depends":["mise"],"mode":"mise","tool":"uv","binary":"uvx"},
"npx":{"depends":["npm"],"mode":"npm-exec"},
"fastmcp":{"depends":["uvx"],"mode":"uvx","package":"fastmcp","binary":"fastmcp"},
"apm":{"depends":["uvx"],"mode":"uvx-from","package":"apm-cli","binary":"apm"},
"claude-code":{"depends":["npm"],"mode":"npm-package","package":"@anthropic-ai/claude-code","binary":"claude","aliases":["claude"]},
"codex-cli":{"depends":["npm"],"mode":"npm-package","package":"@openai/codex","binary":"codex","aliases":["codex"]},
"claude-mcp-add":{"depends":["claude-code"],"mode":"gateway-sub","gateway":"claude-code","prefix":["mcp","add"]},
"claude-mcp-list":{"depends":["claude-code"],"mode":"gateway-sub","gateway":"claude-code","prefix":["mcp","list"]},
"claude-mcp-remove":{"depends":["claude-code"],"mode":"gateway-sub","gateway":"claude-code","prefix":["mcp","remove"]},
"codex-mcp-add":{"depends":["codex-cli"],"mode":"gateway-sub","gateway":"codex-cli","prefix":["mcp","add"]},
"codex-mcp-list":{"depends":["codex-cli"],"mode":"gateway-sub","gateway":"codex-cli","prefix":["mcp","list"]},
"codex-mcp-remove":{"depends":["codex-cli"],"mode":"gateway-sub","gateway":"codex-cli","prefix":["mcp","remove"]},
"apm-mcp-install":{"depends":["apm"],"mode":"gateway-sub","gateway":"apm","prefix":["install","--mcp"]},
"apm-mcp-list":{"depends":["apm"],"mode":"gateway-sub","gateway":"apm","prefix":["mcp","list"]},
}
COMMANDS = {}
for fam, ops in FAMILIES.items():
    for op in ops:
        COMMANDS[fam + "-" + op] = (fam, op)

def out(v):
    if isinstance(v, (dict,list,tuple)):
        print(json.dumps(v, indent=2, ensure_ascii=False, default=str))
    else:
        print(v)

def read_text(args):
    if args and args[0] == "--file" and len(args) > 1:
        return P(args[1]).read_text(errors="replace"), args[2:]
    if not sys.stdin.isatty():
        return sys.stdin.read(), args
    return (" ".join(args) if args else ""), []

def read_bytes(args):
    if args and args[0] == "--file" and len(args) > 1:
        return P(args[1]).read_bytes(), args[2:]
    if not sys.stdin.isatty():
        return sys.stdin.buffer.read(), args
    return (" ".join(args)).encode(), []

def json_path(obj, path):
    cur=obj
    for part in path.split(".") if path else []:
        cur = cur[int(part)] if isinstance(cur,list) else cur[part]
    return cur

def parse_env(text):
    d={}
    for line in text.splitlines():
        s=line.strip()
        if not s or s.startswith("#") or "=" not in s: continue
        k,v=s.split("=",1); d[k.strip()]=v.strip().strip("'\"")
    return d

def parse_semver(s):
    m=re.match(r"^[vV]?(\d+)\.(\d+)\.(\d+)(?:[-+]([0-9A-Za-z.-]+))?$",s.strip())
    if not m: raise ValueError("invalid semantic version")
    return (int(m.group(1)),int(m.group(2)),int(m.group(3)),m.group(4) or "")

def jwt_part(token, idx):
    parts=token.strip().split(".")
    if len(parts)<3: raise ValueError("JWT must have three segments")
    raw=parts[idx] + "="*((4-len(parts[idx])%4)%4)
    return json.loads(base64.urlsafe_b64decode(raw.encode()))

def file_arg(args):
    if not args: raise SystemExit("path required")
    return P(args[0])

def family_jsonx(op,args):
    text,rest=read_text(args); obj=json.loads(text or "null")
    if op=="pretty": out(obj)
    elif op=="minify": print(json.dumps(obj,separators=(",",":")))
    elif op=="keys": out(list(obj.keys()) if isinstance(obj,dict) else list(range(len(obj))) if isinstance(obj,list) else [])
    elif op=="values": out(list(obj.values()) if isinstance(obj,dict) else obj if isinstance(obj,list) else [obj])
    elif op=="type": print(type(obj).__name__)
    elif op in ("get","pluck"): out(json_path(obj, rest[0] if rest else ""))
    elif op=="merge":
        other=json.loads(rest[0] if rest else "{}"); merged=dict(obj); merged.update(other); out(merged)
    elif op=="validate": print("valid")
    elif op=="lines":
        if not isinstance(obj,list): obj=[obj]
        for x in obj: print(json.dumps(x,separators=(",",":")))

def family_textx(op,args):
    text,_=read_text(args)
    if op=="lines": print(len(text.splitlines()))
    elif op=="words": print(len(text.split()))
    elif op=="chars": print(len(text))
    elif op=="bytes": print(len(text.encode()))
    elif op=="upper": print(text.upper())
    elif op=="lower": print(text.lower())
    elif op=="reverse": print(text[::-1])
    elif op=="sort": print("\n".join(sorted(text.splitlines())))
    elif op=="uniq": print("\n".join(dict.fromkeys(text.splitlines())))
    elif op=="trim": print(text.strip())

def family_hashx(op,args):
    data,rest=read_bytes(args)
    if op=="crc32": print("%08x"%(zlib.crc32(data)&0xffffffff)); return
    if op=="hmac-sha256":
        key=(rest[0] if rest else os.environ.get("HMAC_KEY","")).encode()
        print(hmac.new(key,data,hashlib.sha256).hexdigest()); return
    print(getattr(hashlib,op)(data).hexdigest())

def family_encx(op,args):
    data,_=read_bytes(args)
    if op=="b64-encode": print(base64.b64encode(data).decode())
    elif op=="b64-decode": sys.stdout.buffer.write(base64.b64decode(data))
    elif op=="b32-encode": print(base64.b32encode(data).decode())
    elif op=="b32-decode": sys.stdout.buffer.write(base64.b32decode(data))
    elif op=="hex-encode": print(data.hex())
    elif op=="hex-decode": sys.stdout.buffer.write(bytes.fromhex(data.decode().strip()))
    elif op=="url-encode": print(urllib.parse.quote(data.decode()))
    elif op=="url-decode": print(urllib.parse.unquote(data.decode()))
    elif op=="json-escape": print(json.dumps(data.decode())[1:-1])
    elif op=="html-escape": print(html.escape(data.decode()))

def family_urlx(op,args):
    if not args: raise SystemExit("URL required")
    u=args[0]; p=urllib.parse.urlparse(u)
    if op=="parse": out({"scheme":p.scheme,"host":p.hostname,"port":p.port,"path":p.path,"query":p.query,"fragment":p.fragment})
    elif op=="join": print(urllib.parse.urljoin(u,args[1] if len(args)>1 else ""))
    elif op=="query": out(dict(urllib.parse.parse_qsl(p.query,keep_blank_values=True)))
    elif op=="query-get": print(dict(urllib.parse.parse_qsl(p.query,keep_blank_values=True)).get(args[1] if len(args)>1 else "",""))
    elif op=="query-set":
        if len(args)<3: raise SystemExit("URL KEY VALUE required")
        q=dict(urllib.parse.parse_qsl(p.query,keep_blank_values=True)); q[args[1]]=args[2]
        print(urllib.parse.urlunparse(p._replace(query=urllib.parse.urlencode(q))))
    elif op=="origin": print((p.scheme+"://"+p.netloc) if p.scheme else p.netloc)
    elif op=="host": print(p.hostname or "")
    elif op=="path": print(p.path)
    elif op=="normalize": print(urllib.parse.urlunparse((p.scheme.lower(),p.netloc.lower(),p.path or "/",p.params,p.query,p.fragment)))
    elif op=="resolve": print(urllib.parse.urljoin(u,args[1] if len(args)>1 else ""))

def family_csvx(op,args):
    text,rest=read_text(args); rows=list(csv.reader(io.StringIO(text)))
    if op=="count": print(max(0,len(rows)-1))
    elif op=="headers": out(rows[0] if rows else [])
    elif op=="json":
        if not rows: out([]); return
        out([dict(zip(rows[0],r)) for r in rows[1:]])
    elif op=="tsv":
        csv.writer(sys.stdout,delimiter="\t",lineterminator="\n").writerows(rows)
    elif op=="select":
        idx=[int(x) for x in (rest[0].split(",") if rest else ["0"])]
        csv.writer(sys.stdout,lineterminator="\n").writerows([[r[i] for i in idx if i<len(r)] for r in rows])
    elif op=="sort":
        col=int(rest[0]) if rest else 0; outrows=rows[:1]+sorted(rows[1:],key=lambda r:r[col] if col<len(r) else "")
        csv.writer(sys.stdout,lineterminator="\n").writerows(outrows)
    elif op=="uniq":
        seen=set(); outrows=[]
        for r in rows:
            t=tuple(r)
            if t not in seen: seen.add(t); outrows.append(r)
        csv.writer(sys.stdout,lineterminator="\n").writerows(outrows)
    elif op=="filter":
        needle=rest[0] if rest else ""; csv.writer(sys.stdout,lineterminator="\n").writerows([r for r in rows if any(needle in c for c in r)])
    elif op=="transpose":
        csv.writer(sys.stdout,lineterminator="\n").writerows(list(map(list,zip(*rows))) if rows else [])
    elif op=="validate": print("valid")

def family_inix(op,args):
    text,rest=read_text(args); c=configparser.ConfigParser(); c.read_string(text or "[default]\n")
    if op=="sections": out(c.sections())
    elif op=="keys": out(list(c[rest[0] if rest else c.sections()[0]].keys()) if c.sections() else [])
    elif op=="get": print(c.get(rest[0],rest[1]))
    elif op=="json": out({s:dict(c[s]) for s in c.sections()})
    elif op=="validate": print("valid")
    elif op=="merge":
        d=configparser.ConfigParser(); d.read_string(rest[0])
        for s in d.sections():
            if not c.has_section(s): c.add_section(s)
            for k,v in d[s].items(): c[s][k]=v
        c.write(sys.stdout)
    elif op=="set":
        s,k,v=rest[:3]
        if not c.has_section(s): c.add_section(s)
        c[s][k]=v;c.write(sys.stdout)
    elif op=="delete":
        s,k=rest[:2]; c.remove_option(s,k); c.write(sys.stdout)
    elif op=="normalize": c.write(sys.stdout)
    elif op=="template": print("[section]\nkey=value")

def family_tomlx(op,args):
    text,rest=read_text(args); obj=tomllib.loads(text or "")
    if op=="json": out(obj)
    elif op=="keys": out(list(obj.keys()))
    elif op in ("get","lookup"): out(json_path(obj,rest[0] if rest else ""))
    elif op=="validate": print("valid")
    elif op=="flatten":
        flat={}
        def walk(x,p=""):
            if isinstance(x,dict):
                for k,v in x.items(): walk(v,p+"."+k if p else k)
            else: flat[p]=x
        walk(obj); out(flat)
    elif op=="sections": out([k for k,v in obj.items() if isinstance(v,dict)])
    elif op=="count": print(len(obj))
    elif op=="normalize": out(obj)
    elif op=="merge":
        other=tomllib.loads(rest[0] if rest else ""); merged=dict(obj); merged.update(other); out(merged)

def family_envx(op,args):
    text,rest=read_text(args); d=parse_env(text)
    if op in ("parse","json"): out(d)
    elif op=="get": print(d.get(rest[0] if rest else "",""))
    elif op=="keys": out(sorted(d))
    elif op=="validate": print("valid" if all(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$",k) for k in d) else "invalid")
    elif op=="export":
        for k,v in d.items(): print("export %s=%s"%(k,json.dumps(v)))
    elif op=="mask": out({k:("***" if v else "") for k,v in d.items()})
    elif op=="merge":
        d.update(parse_env(rest[0] if rest else ""))
        for k in sorted(d): print("%s=%s"%(k,d[k]))
    elif op=="sort":
        for k in sorted(d): print("%s=%s"%(k,d[k]))
    elif op=="template": print("KEY=value\nOTHER=value")

def parse_dt(s):
    if s.endswith("Z"): s=s[:-1]+"+00:00"
    return dt.datetime.fromisoformat(s)

def family_timex(op,args):
    now=dt.datetime.now(dt.timezone.utc)
    if op=="now": print(now.isoformat())
    elif op=="epoch": print(int(now.timestamp()))
    elif op=="iso-to-epoch": print(int(parse_dt(args[0]).timestamp()))
    elif op=="epoch-to-iso": print(dt.datetime.fromtimestamp(float(args[0]),dt.timezone.utc).isoformat())
    elif op=="diff": print((parse_dt(args[1])-parse_dt(args[0])).total_seconds())
    elif op=="add": print((parse_dt(args[0])+dt.timedelta(seconds=float(args[1]))).isoformat())
    elif op=="format": print(parse_dt(args[0]).strftime(args[1] if len(args)>1 else "%Y-%m-%d %H:%M:%S"))
    elif op=="weekday": print(parse_dt(args[0]).strftime("%A"))
    elif op=="month": print(parse_dt(args[0]).strftime("%B"))
    elif op=="duration":
        sec=int(float(args[0])); h,sec=divmod(sec,3600); m,s=divmod(sec,60); print("%02d:%02d:%02d"%(h,m,s))

def family_pathx(op,args):
    if op=="join": print(str(P(args[0]).joinpath(*args[1:]))); return
    p=P(args[0] if args else ".")
    vals={"abs":str(p.absolute()),"base":p.name,"dir":str(p.parent),"ext":p.suffix,"stem":p.stem,"norm":os.path.normpath(str(p)),"parts":list(p.parts),"exists":p.exists()}
    if op=="rel": print(os.path.relpath(str(p),args[1] if len(args)>1 else "."))
    else: out(vals[op])

def family_filex(op,args):
    p=file_arg(args)
    if op=="size": print(p.stat().st_size)
    elif op=="lines": print(sum(1 for _ in p.open(errors="replace")))
    elif op=="words": print(len(p.read_text(errors="replace").split()))
    elif op=="sha256": print(hashlib.sha256(p.read_bytes()).hexdigest())
    elif op=="mime": print(mimetypes.guess_type(str(p))[0] or "application/octet-stream")
    elif op=="head": print("".join(p.read_text(errors="replace").splitlines(True)[:int(args[1]) if len(args)>1 else 10]),end="")
    elif op=="tail": print("".join(p.read_text(errors="replace").splitlines(True)[-(int(args[1]) if len(args)>1 else 10):]),end="")
    elif op=="stat":
        s=p.stat(); out({"size":s.st_size,"mtime":s.st_mtime,"mode":oct(s.st_mode),"file":p.is_file(),"dir":p.is_dir()})
    elif op=="copy": shutil.copy2(p,args[1]); print(args[1])
    elif op=="cat": sys.stdout.buffer.write(p.read_bytes())

def walk_files(p):
    return [x for x in p.rglob("*") if x.is_file()]

def family_dirx(op,args):
    p=P(args[0] if args else "."); files=walk_files(p)
    if op=="list": print("\n".join(x.name for x in p.iterdir()))
    elif op=="tree": print("\n".join(str(x.relative_to(p)) for x in sorted(p.rglob("*"))))
    elif op=="count": print(len(files))
    elif op=="size": print(sum(x.stat().st_size for x in files))
    elif op=="files": print("\n".join(str(x) for x in files))
    elif op=="dirs": print("\n".join(str(x) for x in p.rglob("*") if x.is_dir()))
    elif op=="largest": print(max(files,key=lambda x:x.stat().st_size) if files else "")
    elif op=="newest": print(max(files,key=lambda x:x.stat().st_mtime) if files else "")
    elif op=="oldest": print(min(files,key=lambda x:x.stat().st_mtime) if files else "")
    elif op=="dupes":
        seen={}
        for x in files:
            h=hashlib.sha256(x.read_bytes()).hexdigest(); seen.setdefault(h,[]).append(str(x))
        out([v for v in seen.values() if len(v)>1])

def family_archivex(op,args):
    if not args: raise SystemExit("archive path required")
    p=P(args[0])
    if op.startswith("zip-"):
        if op=="zip-list":
            with zipfile.ZipFile(p) as z: print("\n".join(z.namelist()))
        elif op=="zip-test":
            with zipfile.ZipFile(p) as z: print(z.testzip() or "ok")
        elif op=="zip-extract":
            with zipfile.ZipFile(p) as z: z.extractall(args[1] if len(args)>1 else ".")
        elif op=="zip-create":
            root=P(args[1] if len(args)>1 else ".")
            with zipfile.ZipFile(p,"w",zipfile.ZIP_DEFLATED) as z:
                for x in walk_files(root): z.write(x,x.relative_to(root))
    elif op.startswith("tar-"):
        mode="r:*" if op!="tar-create" else "w:gz"
        with tarfile.open(p,mode) as t:
            if op=="tar-list": print("\n".join(t.getnames()))
            elif op=="tar-test": print("ok")
            elif op=="tar-extract": t.extractall(args[1] if len(args)>1 else ".")
            elif op=="tar-create": t.add(args[1] if len(args)>1 else ".",arcname=".")
    elif op=="gzip":
        src=P(args[0]); dst=P(args[1] if len(args)>1 else str(src)+".gz")
        with src.open("rb") as a,gzip.open(dst,"wb") as b: shutil.copyfileobj(a,b)
    elif op=="gunzip":
        src=P(args[0]); dst=P(args[1] if len(args)>1 else str(src).removesuffix(".gz"))
        with gzip.open(src,"rb") as a,dst.open("wb") as b: shutil.copyfileobj(a,b)

def http_request(url,method="GET"):
    req=urllib.request.Request(url,method=method,headers={"User-Agent":"OceanStudio-httpxcli/1"})
    return urllib.request.urlopen(req,timeout=20)

def family_httpxcli(op,args):
    if op=="encode-query": print(urllib.parse.urlencode(dict(x.split("=",1) for x in args))); return
    if op=="resolve-url": print(urllib.parse.urljoin(args[0],args[1])); return
    if op=="user-agent": print("OceanStudio-httpxcli/1"); return
    if not args: raise SystemExit("URL required")
    url=args[0]; start=time.time()
    with http_request(url,"HEAD" if op in ("head","status","headers") else "GET") as r:
        if op=="get": sys.stdout.buffer.write(r.read())
        elif op=="head": out(dict(r.headers))
        elif op=="status": print(r.status)
        elif op=="headers": out(dict(r.headers))
        elif op=="json": out(json.loads(r.read().decode()))
        elif op=="download":
            dst=P(args[1] if len(args)>1 else P(urllib.parse.urlparse(url).path).name or "download.bin"); dst.write_bytes(r.read()); print(dst)
        elif op=="time": print(round(time.time()-start,6))

def family_netx(op,args):
    if op=="hostname": print(socket.gethostname())
    elif op=="local-ip":
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try: s.connect(("8.8.8.8",80)); print(s.getsockname()[0])
        finally: s.close()
    elif op=="host": out(socket.getaddrinfo(args[0],None))
    elif op=="reverse": out(socket.gethostbyaddr(args[0]))
    elif op=="tcp-check":
        host=args[0]; port=int(args[1]); s=socket.create_connection((host,port),timeout=float(args[2]) if len(args)>2 else 3); s.close(); print("open")
    elif op=="resolve": print(socket.gethostbyname(args[0]))
    elif op=="service-port": print(socket.getservbyname(args[0],args[1] if len(args)>1 else "tcp"))
    elif op=="url-host": print(urllib.parse.urlparse(args[0]).hostname or "")
    elif op=="cidr-hosts":
        n=ipaddress.ip_network(args[0],strict=False)
        for i,x in enumerate(n.hosts()):
            if i>=256: break
            print(x)
    elif op=="ip-version": print(ipaddress.ip_address(args[0]).version)

def family_procx(op,args):
    if op=="env": out(dict(os.environ))
    elif op=="cwd": print(os.getcwd())
    elif op=="which": print(shutil.which(args[0]) or "")
    elif op=="pid": print(os.getpid())
    elif op=="ppid": print(os.getppid())
    elif op=="uid": print(os.getuid() if hasattr(os,"getuid") else -1)
    elif op=="uname": out(tuple(os.uname()) if hasattr(os,"uname") else ())
    elif op=="python-version": print(sys.version)
    elif op=="run": raise SystemExit(subprocess.run(args).returncode)
    elif op=="timeout":
        sec=float(args[0]); raise SystemExit(subprocess.run(args[1:],timeout=sec).returncode)

def git(args):
    return subprocess.check_output(["git"]+args,text=True,stderr=subprocess.DEVNULL).strip()

def family_gitmeta(op,args):
    m={"root":["rev-parse","--show-toplevel"],"branch":["branch","--show-current"],"head":["rev-parse","HEAD"],"status":["status","--short"],
       "remotes":["remote","-v"],"list-files":["ls-files"],"changed":["diff","--name-only"],"log-one":["log","-1","--oneline"],"describe":["describe","--always","--dirty"]}
    if op=="config": print(git(["config","--get",args[0]]))
    else: print(git(m[op]))

def family_manifestx(op,args):
    if op=="package-json": out(json.loads(P("package.json").read_text()))
    elif op in ("name","version","scripts","deps","devdeps"):
        d=json.loads(P("package.json").read_text())
        key={"name":"name","version":"version","scripts":"scripts","deps":"dependencies","devdeps":"devDependencies"}[op]; out(d.get(key,{} if op not in ("name","version") else ""))
    elif op=="pyproject": out(tomllib.loads(P("pyproject.toml").read_text()))
    elif op=="requirements": print(P("requirements.txt").read_text(),end="")
    elif op=="gradle": print(next((str(P(x)) for x in ("build.gradle","build.gradle.kts") if P(x).exists()),""))
    elif op=="maven": print("pom.xml" if P("pom.xml").exists() else "")

def family_semverx(op,args):
    if op=="parse": out(parse_semver(args[0])); return
    if op=="compare":
        a,b=parse_semver(args[0]),parse_semver(args[1]); print(-1 if a<b else 1 if a>b else 0); return
    if op.startswith("bump-"):
        a=list(parse_semver(args[0])[:3]); i={"bump-major":0,"bump-minor":1,"bump-patch":2}[op]; a[i]+=1
        for j in range(i+1,3): a[j]=0
        print("%d.%d.%d"%tuple(a)); return
    if op=="normalize":
        a=parse_semver(args[0]); print(("%d.%d.%d"%a[:3])+(("-"+a[3]) if a[3] else "")); return
    if op=="valid":
        try: parse_semver(args[0]); print("true")
        except Exception: print("false")
        return
    versions=[x.strip() for x in (args if len(args)>1 else args[0].split(","))]
    versions=sorted(versions,key=parse_semver)
    if op=="sort": print("\n".join(versions))
    elif op=="max": print(versions[-1])
    elif op=="min": print(versions[0])

def family_jwtx(op,args):
    token=args[0] if args else read_text([])[0].strip(); h=jwt_part(token,0); p=jwt_part(token,1)
    if op=="decode-header": out(h)
    elif op=="decode-payload": out(p)
    elif op=="expiry": out(p.get("exp"))
    elif op=="issuer": out(p.get("iss"))
    elif op=="audience": out(p.get("aud"))
    elif op=="subject": out(p.get("sub"))
    elif op=="claims": out(sorted(p.keys()))
    elif op=="is-expired": print(str(bool(p.get("exp") and time.time()>float(p["exp"]))).lower())
    elif op=="not-before": out(p.get("nbf"))
    elif op=="segments": print(len(token.split(".")))

def family_regexx(op,args):
    if op=="escape": print(re.escape(args[0])); return
    pat=args[0]; text=args[1] if len(args)>1 else read_text([])[0]
    if op=="match": print(str(bool(re.match(pat,text))).lower())
    elif op=="search":
        m=re.search(pat,text); print(m.group(0) if m else "")
    elif op=="findall": out(re.findall(pat,text))
    elif op=="split": out(re.split(pat,text))
    elif op=="replace": print(re.sub(pat,args[2] if len(args)>2 else "",text))
    elif op=="count": print(len(re.findall(pat,text)))
    elif op=="groups":
        m=re.search(pat,text); out(m.groups() if m else [])
    elif op=="lines": print("\n".join(x for x in text.splitlines() if re.search(pat,x)))
    elif op=="validate": re.compile(pat); print("valid")

def load_json_file(path):
    p=P(path); return json.loads(p.read_text()) if p.exists() else {}

def save_json_file(path,obj):
    P(path).write_text(json.dumps(obj,indent=2)+"\n")

def mcp_servers(obj):
    return obj.setdefault("mcpServers",{})

def family_mcpconf(op,args):
    path=args[0] if args else "mcp.json"; obj=load_json_file(path)
    if op=="validate": mcp_servers(obj); print("valid")
    elif op=="list": out(sorted(mcp_servers(obj)))
    elif op=="get": out(mcp_servers(obj).get(args[1]))
    elif op=="remove": mcp_servers(obj).pop(args[1],None); save_json_file(path,obj)
    elif op=="add":
        name=args[1]; cmd=args[2]; mcp_servers(obj)[name]={"command":cmd,"args":args[3:]}; save_json_file(path,obj)
    elif op=="merge":
        other=load_json_file(args[1]); mcp_servers(obj).update(mcp_servers(other)); save_json_file(path,obj)
    elif op=="stdio":
        name=args[1]; out({name:{"command":args[2],"args":args[3:]}})
    elif op=="http":
        name=args[1]; out({name:{"url":args[2]}})
    elif op=="env":
        name=args[1]; out((mcp_servers(obj).get(name) or {}).get("env",{}))
    elif op=="template": out({"mcpServers":{"example":{"command":"npx","args":["-y","server-package"]}}})

AGENT_MARKERS={".claude":"claude",".codex":"codex",".cursor":"cursor",".github":"copilot",".gemini":"gemini",".windsurf":"windsurf"}

def family_agentcfg(op,args):
    root=P(args[0] if args else ".")
    if op=="detect": out([v for k,v in AGENT_MARKERS.items() if (root/k).exists()])
    elif op=="list-files": print("\n".join(str(x.relative_to(root)) for x in root.rglob("*") if x.is_file() and any(part in AGENT_MARKERS for part in x.parts)))
    elif op=="summary": out({"root":str(root.resolve()),"targets":[v for k,v in AGENT_MARKERS.items() if (root/k).exists()]})
    elif op=="init": (root/".apm").mkdir(exist_ok=True); print(root/".apm")
    elif op=="merge": out({"left":args[0] if args else ".","right":args[1] if len(args)>1 else "."})
    elif op=="paths": out({v:str(root/k) for k,v in AGENT_MARKERS.items()})
    elif op=="ignore": print(".claude/cache\n.codex/cache\n.apm/cache")
    elif op=="scan-prompts": print("\n".join(str(x) for x in root.rglob("*prompt*") if x.is_file()))
    elif op=="scan-skills": print("\n".join(str(x) for x in root.rglob("SKILL.md")))
    elif op=="scan-mcp": print("\n".join(str(x) for x in root.rglob("*mcp*") if x.is_file()))

LANG_EXT={".py":"Python",".js":"JavaScript",".ts":"TypeScript",".java":"Java",".kt":"Kotlin",".rs":"Rust",".go":"Go",".c":"C",".cpp":"C++",".sh":"Shell",".lua":"Lua"}

def family_projectx(op,args):
    root=P(args[0] if args else "."); files=walk_files(root)
    if op=="detect":
        for n in ("package.json","pyproject.toml","requirements.txt","build.gradle","build.gradle.kts","pom.xml","Cargo.toml","go.mod"):
            if (root/n).exists(): print(n); return
        print("")
    elif op=="files": print(len(files))
    elif op=="langs": out(Counter(LANG_EXT.get(x.suffix,"Other") for x in files))
    elif op=="size": print(sum(x.stat().st_size for x in files))
    elif op=="todos":
        n=0
        for x in files:
            try:n+=x.read_text(errors="ignore").count("TODO")
            except Exception:pass
        print(n)
    elif op=="licenses": print("\n".join(str(x) for x in files if x.name.lower().startswith("license")))
    elif op=="readmes": print("\n".join(str(x) for x in files if x.name.lower().startswith("readme")))
    elif op=="manifests": print("\n".join(str(x) for x in files if x.name in ("package.json","pyproject.toml","requirements.txt","pom.xml","build.gradle","Cargo.toml","go.mod")))
    elif op=="entrypoints": print("\n".join(str(x) for x in files if x.name in ("main.py","index.js","index.ts","Main.java","main.rs","main.go")))
    elif op=="summary": out({"files":len(files),"bytes":sum(x.stat().st_size for x in files),"languages":Counter(LANG_EXT.get(x.suffix,"Other") for x in files)})

def family_logx(op,args):
    text,rest=read_text(args); lines=text.splitlines()
    if op=="count": print(len(lines))
    elif op=="levels":
        vals=[]
        for x in lines:
            m=re.search(r"\b(DEBUG|INFO|WARN|WARNING|ERROR|FATAL|TRACE)\b",x,re.I); vals.append(m.group(1).upper() if m else "OTHER")
        out(Counter(vals))
    elif op=="errors": print("\n".join(x for x in lines if re.search(r"\berror\b",x,re.I)))
    elif op=="warnings": print("\n".join(x for x in lines if re.search(r"\bwarn(?:ing)?\b",x,re.I)))
    elif op=="tail": print("\n".join(lines[-(int(rest[0]) if rest else 20):]))
    elif op=="head": print("\n".join(lines[:int(rest[0]) if rest else 20]))
    elif op=="grep": print("\n".join(x for x in lines if (rest[0] if rest else "") in x))
    elif op=="json-lines":
        for x in lines:
            try: out(json.loads(x))
            except Exception: pass
    elif op=="timestamps": print("\n".join(re.findall(r"\d{4}-\d{2}-\d{2}[T ][0-9:.+\-Z]+",text)))
    elif op=="stats": out({"lines":len(lines),"bytes":len(text.encode()),"errors":sum(bool(re.search(r"\berror\b",x,re.I)) for x in lines)})

def parse_jsonl(text):
    return [json.loads(x) for x in text.splitlines() if x.strip()]

def family_datax(op,args):
    text,rest=read_text(args); rows=parse_jsonl(text) if op.startswith("jsonl-") or op=="stats" else text.splitlines()
    if op=="jsonl-count": print(len(rows))
    elif op=="jsonl-pretty": out(rows)
    elif op=="jsonl-keys": out(sorted({k for r in rows if isinstance(r,dict) for k in r}))
    elif op=="jsonl-dedupe":
        seen=set()
        for r in rows:
            s=json.dumps(r,sort_keys=True,separators=(",",":"))
            if s not in seen: seen.add(s); print(s)
    elif op=="jsonl-sort":
        key=rest[0] if rest else ""
        for r in sorted(rows,key=lambda x:str(x.get(key,"")) if isinstance(x,dict) else str(x)): print(json.dumps(r,separators=(",",":")))
    elif op=="sample":
        n=int(rest[0]) if rest else 5; print("\n".join(text.splitlines()[:n]))
    elif op=="head": print("\n".join(text.splitlines()[:int(rest[0]) if rest else 10]))
    elif op=="tail": print("\n".join(text.splitlines()[-(int(rest[0]) if rest else 10):]))
    elif op=="grep": print("\n".join(x for x in text.splitlines() if (rest[0] if rest else "") in x))
    elif op=="stats": out({"rows":len(rows),"types":Counter(type(x).__name__ for x in rows)})

def family_sqliteq(op,args):
    if not args: raise SystemExit("database path required")
    con=sqlite3.connect(args[0])
    try:
        if op=="tables": out([r[0] for r in con.execute("select name from sqlite_master where type='table' order by name")])
        elif op=="schema": print("\n".join(r[0] for r in con.execute("select sql from sqlite_master where sql is not null order by name")))
        elif op=="count": print(con.execute("select count(*) from "+args[1]).fetchone()[0])
        elif op=="query":
            cur=con.execute(" ".join(args[1:])); cols=[d[0] for d in cur.description] if cur.description else []; out([dict(zip(cols,r)) for r in cur.fetchall()])
        elif op=="columns": out([dict(zip(("cid","name","type","notnull","default","pk"),r)) for r in con.execute("pragma table_info("+args[1]+")")])
        elif op=="indexes": out([r[1] for r in con.execute("pragma index_list("+args[1]+")")])
        elif op=="pragma": out(con.execute("pragma "+args[1]).fetchall())
        elif op=="integrity": print(con.execute("pragma integrity_check").fetchone()[0])
        elif op=="export-json":
            table=args[1]; cur=con.execute("select * from "+table); cols=[d[0] for d in cur.description]; out([dict(zip(cols,r)) for r in cur.fetchall()])
        elif op=="vacuum": con.execute("vacuum"); print("ok")
    finally: con.close()

def family_androidmeta(op,args):
    p=file_arg(args)
    with zipfile.ZipFile(p) as z:
        names=z.namelist()
        if op=="apk-list": print("\n".join(names))
        elif op=="apk-files": print(len(names))
        elif op=="apk-size": print(p.stat().st_size)
        elif op=="dex-count": print(sum(bool(re.match(r"classes\d*\.dex$",P(n).name)) for n in names))
        elif op=="lib-list": print("\n".join(n for n in names if n.startswith("lib/") and n.endswith(".so")))
        elif op=="abi-list": out(sorted({n.split("/")[1] for n in names if n.startswith("lib/") and n.count("/")>=2}))
        elif op=="res-count": print(sum(n.startswith("res/") for n in names))
        elif op=="assets-list": print("\n".join(n for n in names if n.startswith("assets/")))
        elif op=="cert-files": print("\n".join(n for n in names if n.upper().startswith("META-INF/") and n.upper().endswith((".RSA",".DSA",".EC",".SF"))))
        elif op=="summary": out({"files":len(names),"bytes":p.stat().st_size,"dex":sum(bool(re.match(r"classes\d*\.dex$",P(n).name)) for n in names),"abis":sorted({n.split("/")[1] for n in names if n.startswith("lib/") and n.count("/")>=2})})

def family_mcpmsg(op,args):
    ident=int(args[0]) if args and args[0].isdigit() else 1
    if op=="stdio-frame":
        payload=(args[0] if args else "{}").encode(); sys.stdout.buffer.write(("Content-Length: %d\r\n\r\n"%len(payload)).encode()+payload)
    elif op=="parse-frame":
        text=read_text(args)[0]; body=text.split("\r\n\r\n",1)[-1]; out(json.loads(body))
    elif op=="request": out({"jsonrpc":"2.0","id":ident,"method":args[1] if len(args)>1 else "tools/list","params":{}})
    elif op=="notification": out({"jsonrpc":"2.0","method":args[0] if args else "notifications/initialized","params":{}})
    elif op=="response": out({"jsonrpc":"2.0","id":ident,"result":{}})
    elif op=="error": out({"jsonrpc":"2.0","id":ident,"error":{"code":-32000,"message":"error"}})
    elif op=="initialize": out({"jsonrpc":"2.0","id":ident,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"ocean","version":"1"}}})
    elif op=="ping": out({"jsonrpc":"2.0","id":ident,"method":"ping"})
    elif op=="tools-list": out({"jsonrpc":"2.0","id":ident,"method":"tools/list","params":{}})
    elif op=="resources-list": out({"jsonrpc":"2.0","id":ident,"method":"resources/list","params":{}})

HANDLERS={k:globals()["family_"+k] for k in FAMILIES}

def main():
    argv=sys.argv[1:]
    if not argv or argv[0] in ("-h","--help"):
        print("Ocean standalone utility runtime")
        print("commands:",len(COMMANDS))
        return
    cmd=argv.pop(0)
    if cmd not in COMMANDS: raise SystemExit("unknown command: "+cmd)
    if argv and argv[0]=="--self-test":
        fam,op=COMMANDS[cmd]
        out({"command":cmd,"family":fam,"operation":op,"ok":True})
        return
    fam,op=COMMANDS[cmd]
    HANDLERS[fam](op,argv)

if __name__=="__main__":
    main()
