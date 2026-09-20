#!/usr/bin/env python3
from __future__ import annotations
import base64,calendar,configparser,csv,datetime as dt,difflib,email.utils,hashlib,html,ipaddress,json,math,os,random,re,shlex,shutil,statistics,stat,sys,tempfile,textwrap,time,urllib.parse,xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
P=Path
VERSION="1.0.0"

GROUPS={
"date":["now","epoch","from-epoch","iso-normalize","add-days","add-seconds","diff-seconds","weekday","month-days","leap-year","week-number","day-of-year","start-of-day","end-of-day","parse-rfc2822","format","tz-offset","duration-parse","duration-format","range-days"],
"math":["sum","mean","median","mode","min","max","range","variance","stdev","percentile","gcd","lcm","factorial","prime-check","prime-factors","fibonacci","clamp","lerp","distance-2d","quadratic"],
"unit":["bytes-human","human-bytes","c-to-f","f-to-c","c-to-k","km-mi","mi-km","m-ft","ft-m","kg-lb","lb-kg","l-ml","ml-l","deg-rad","rad-deg","percent","ratio","base-convert","bits-bytes","speed-kmh-ms"],
"enc":["url-quote","url-unquote","html-escape","html-unescape","json-string","json-unstring","unicode-codepoints","unicode-from-codepoints","utf8-bytes","utf8-validate","ascii-check","hex-encode","hex-decode","base32-encode","base32-decode","base64url-encode","base64url-decode","rot13","caesar","punycode"],
"xml":["wellformed","root","elements","attrs","text","find-tag","find-attr","pretty","minify","namespaces","paths","count","to-json","from-json","strip-ns","remove-tag","set-attr","get-attr","xpath-lite","canonical"],
"config":["ini-get","ini-set","ini-sections","ini-keys","ini-to-json","json-to-ini","props-get","props-set","props-to-json","json-to-props","dotenv-get","dotenv-set","dotenv-to-json","json-to-dotenv","toml-get","toml-keys","toml-to-json","merge-json","env-expand","config-detect"],
"md":["headings","links","images","codeblocks","tables","task-count","word-count","toc","strip","escape","unescape","frontmatter","frontmatter-get","frontmatter-set","normalize-headings","check-links","code-languages","stats","anchor","wrap-paragraphs"],
"regex":["test","find","findall","replace","split","escape","groups","named-groups","flags","literal","line-filter","line-exclude","count","first","last","extract-numbers","extract-emails","extract-urls","extract-ips","validate"],
"diff":["text-unified","text-context","text-html","lines-added","lines-removed","lines-changed","json","json-keys","dir-names","dir-size","file-hash","file-size","same-file","common-lines","unique-left","unique-right","sequence-ratio","prefix-common","suffix-common","hexdiff"],
"proc":["self","pid-info","pid-cmdline","pid-status","pid-env","pid-fds","pid-threads","pid-maps","pid-cwd","pid-exe","list","search","count","uptime","loadavg","meminfo","cpu-count","kernel","limits","open-fds"],
"perm":["mode","octal-to-symbolic","symbolic-to-octal","is-readable","is-writable","is-executable","is-owner","chmod","add-exec","remove-exec","umask","stat","inode","links","owner","group","same-device","is-symlink","resolve-symlink","access-matrix"],
"semver":["parse","compare","sort","bump-major","bump-minor","bump-patch","is-prerelease","core","prerelease","build","satisfies-exact","satisfies-caret","satisfies-tilde","next-major","next-minor","next-patch","normalize","max","min","distance"],
"log":["levels","count-levels","errors","warnings","tail-errors","timestamps","time-range","grep","json-lines","invalid-json-lines","dedupe","top-messages","top-words","line-rate","size","rotate-name","split-by-level","extract-ids","extract-ips","summary"],
"stream":["head","tail","count","nonempty","blank","number","prefix","suffix","trim","unique","duplicates","sample","every-n","chunk","join","split-delim","columns","reverse","shuffle","hash-lines"],
"shell":["quote","join","split","which","path-list","path-dedupe","path-missing","env-get","env-has","env-list","env-prefix","shebang","command-exists","command-type","cwd","home","tempdir","shell","argv-json","export-line"]
}
COMMANDS=[f"ocean-wb-{g}-{op}" for g,ops in GROUPS.items() for op in ops]
assert len(COMMANDS)==300 and len(set(COMMANDS))==300

def emit(x):
    if isinstance(x,(dict,list,tuple)): print(json.dumps(x,indent=2,ensure_ascii=False,default=str))
    else: print(x)
def die(s,c=2): print(s,file=sys.stderr); raise SystemExit(c)
def text_arg(a):
    if a and P(a[0]).exists() and P(a[0]).is_file(): return P(a[0]).read_text(errors="replace")
    return " ".join(a) if a else sys.stdin.read()
def parse_dt(s):
    s=s.strip()
    if s.lower()=="now": return dt.datetime.now(dt.timezone.utc)
    if re.fullmatch(r"\d+(?:\.\d+)?",s): return dt.datetime.fromtimestamp(float(s),dt.timezone.utc)
    if s.endswith("Z"): s=s[:-1]+"+00:00"
    x=dt.datetime.fromisoformat(s)
    if x.tzinfo is None: x=x.replace(tzinfo=dt.timezone.utc)
    return x
def parse_duration(s):
    m=re.fullmatch(r"\s*(?:(\d+(?:\.\d+)?)d)?\s*(?:(\d+(?:\.\d+)?)h)?\s*(?:(\d+(?:\.\d+)?)m)?\s*(?:(\d+(?:\.\d+)?)s)?\s*",s)
    if not m: die("duration format: 1d2h3m4s")
    d,h,mn,sec=[float(x or 0) for x in m.groups()]
    return d*86400+h*3600+mn*60+sec
def fmt_duration(sec):
    neg=sec<0;sec=abs(float(sec));d=int(sec//86400);sec%=86400;h=int(sec//3600);sec%=3600;m=int(sec//60);s=sec%60
    q=(f"{d}d" if d else "")+(f"{h}h" if h else "")+(f"{m}m" if m else "")+(f"{s:g}s" if s or not(d or h or m) else "")
    return ("-" if neg else "")+q
def handle_date(op,a):
    now=dt.datetime.now(dt.timezone.utc)
    if op=="now": print(now.isoformat()); return
    if op=="epoch": print(time.time()); return
    if op=="from-epoch": print(dt.datetime.fromtimestamp(float(a[0]),dt.timezone.utc).isoformat()); return
    if op=="duration-parse": print(parse_duration(" ".join(a))); return
    if op=="duration-format": print(fmt_duration(float(a[0]))); return
    if not a: die("date/time argument required")
    x=parse_dt(a[0])
    if op=="iso-normalize": print(x.isoformat())
    elif op=="add-days": print((x+dt.timedelta(days=float(a[1]))).isoformat())
    elif op=="add-seconds": print((x+dt.timedelta(seconds=float(a[1]))).isoformat())
    elif op=="diff-seconds": print((parse_dt(a[1])-x).total_seconds())
    elif op=="weekday": print(calendar.day_name[x.weekday()])
    elif op=="month-days": print(calendar.monthrange(x.year,x.month)[1])
    elif op=="leap-year": print(str(calendar.isleap(int(a[0][:4]))).lower())
    elif op=="week-number": print(x.isocalendar().week)
    elif op=="day-of-year": print(x.timetuple().tm_yday)
    elif op=="start-of-day": print(x.replace(hour=0,minute=0,second=0,microsecond=0).isoformat())
    elif op=="end-of-day": print(x.replace(hour=23,minute=59,second=59,microsecond=999999).isoformat())
    elif op=="parse-rfc2822": print(email.utils.parsedate_to_datetime(" ".join(a)).isoformat())
    elif op=="format": print(x.strftime(a[1] if len(a)>1 else "%Y-%m-%d %H:%M:%S %z"))
    elif op=="tz-offset": print(int((x.utcoffset() or dt.timedelta()).total_seconds()))
    elif op=="range-days":
        y=parse_dt(a[1]);step=1 if y.date()>=x.date() else -1;cur=x.date();rows=[]
        while True:
            rows.append(cur.isoformat())
            if cur==y.date():break
            cur+=dt.timedelta(days=step)
            if len(rows)>10000:die("range too large")
        emit(rows)
def nums(a): return [float(x) for x in a]
def pct(v,p):
    v=sorted(v)
    if not v:die("no values")
    k=(len(v)-1)*p/100;f=math.floor(k);c=math.ceil(k)
    return v[f] if f==c else v[f]*(c-k)+v[c]*(k-f)
def handle_math(op,a):
    if op in {"sum","mean","median","mode","min","max","range","variance","stdev"}:
        v=nums(a)
        if not v:die("numbers required")
        funcs={"sum":sum,"mean":statistics.fmean,"median":statistics.median,"min":min,"max":max,"variance":statistics.pvariance,"stdev":statistics.pstdev}
        if op=="mode":emit(Counter(v).most_common())
        elif op=="range":print(max(v)-min(v))
        else:print(funcs[op](v))
    elif op=="percentile":
        if len(a)<2:die("PERCENT numbers...")
        print(pct(nums(a[1:]),float(a[0])))
    elif op=="gcd": print(math.gcd(*map(int,a)))
    elif op=="lcm": print(math.lcm(*map(int,a)))
    elif op=="factorial": print(math.factorial(int(a[0])))
    elif op=="prime-check":
        n=int(a[0]);ok=n>=2 and all(n%d for d in range(2,int(math.sqrt(n))+1));print(str(ok).lower())
    elif op=="prime-factors":
        n=int(a[0]);r=[];d=2
        while d*d<=n:
            while n%d==0:r.append(d);n//=d
            d+=1
        if n>1:r.append(n)
        emit(r)
    elif op=="fibonacci":
        n=int(a[0]);x,y=0,1
        for _ in range(n):x,y=y,x+y
        print(x)
    elif op=="clamp": print(max(float(a[1]),min(float(a[2]),float(a[0]))))
    elif op=="lerp": print(float(a[0])+(float(a[1])-float(a[0]))*float(a[2]))
    elif op=="distance-2d": print(math.hypot(float(a[2])-float(a[0]),float(a[3])-float(a[1])))
    elif op=="quadratic":
        A,B,C=map(float,a[:3]);disc=B*B-4*A*C
        roots=((complex(-B+complex(disc)**.5)/(2*A)),(complex(-B-complex(disc)**.5)/(2*A))) if disc<0 else ((-B+math.sqrt(disc))/(2*A),(-B-math.sqrt(disc))/(2*A))
        emit(roots)
def human_bytes(n):
    n=float(n);units=["B","KiB","MiB","GiB","TiB","PiB"]
    for u in units:
        if abs(n)<1024 or u==units[-1]:return f"{n:.2f} {u}"
        n/=1024
def parse_hbytes(s):
    m=re.fullmatch(r"\s*([0-9.]+)\s*([KMGTPE]?i?B)?\s*",s,re.I)
    if not m:die("bad size")
    n=float(m.group(1));u=(m.group(2) or "B").upper();power={"B":0,"KB":1,"KIB":1,"MB":2,"MIB":2,"GB":3,"GIB":3,"TB":4,"TIB":4,"PB":5,"PIB":5,"EB":6,"EIB":6}[u]
    return int(n*(1024**power))
def handle_unit(op,a):
    if op=="bytes-human": print(human_bytes(float(a[0])))
    elif op=="human-bytes": print(parse_hbytes(" ".join(a)))
    elif op=="c-to-f": print(float(a[0])*9/5+32)
    elif op=="f-to-c": print((float(a[0])-32)*5/9)
    elif op=="c-to-k": print(float(a[0])+273.15)
    elif op=="km-mi": print(float(a[0])*0.6213711922)
    elif op=="mi-km": print(float(a[0])/0.6213711922)
    elif op=="m-ft": print(float(a[0])*3.280839895)
    elif op=="ft-m": print(float(a[0])/3.280839895)
    elif op=="kg-lb": print(float(a[0])*2.2046226218)
    elif op=="lb-kg": print(float(a[0])/2.2046226218)
    elif op=="l-ml": print(float(a[0])*1000)
    elif op=="ml-l": print(float(a[0])/1000)
    elif op=="deg-rad": print(math.radians(float(a[0])))
    elif op=="rad-deg": print(math.degrees(float(a[0])))
    elif op=="percent": print(float(a[0])*float(a[1])/100)
    elif op=="ratio":
        x,y=map(int,a[:2]);g=math.gcd(x,y);print(f"{x//g}:{y//g}")
    elif op=="base-convert":
        target=int(a[2]);n=int(a[0],int(a[1]));print(format(n,{2:"b",8:"o",10:"d",16:"x"}[target]))
    elif op=="bits-bytes": print(math.ceil(float(a[0])/8))
    elif op=="speed-kmh-ms": print(float(a[0])/3.6)
def handle_enc(op,a):
    s=" ".join(a) if a else sys.stdin.read()
    if op=="url-quote": print(urllib.parse.quote(s,safe=""))
    elif op=="url-unquote": print(urllib.parse.unquote(s))
    elif op=="html-escape": print(html.escape(s))
    elif op=="html-unescape": print(html.unescape(s))
    elif op=="json-string": print(json.dumps(s,ensure_ascii=False))
    elif op=="json-unstring": print(json.loads(s))
    elif op=="unicode-codepoints": emit([f"U+{ord(c):04X}" for c in s])
    elif op=="unicode-from-codepoints": print("".join(chr(int(x.upper().removeprefix("U+"),16)) for x in a))
    elif op=="utf8-bytes": emit(list(s.encode()))
    elif op=="utf8-validate":
        try: bytes.fromhex(a[0]).decode();print("true")
        except:print("false")
    elif op=="ascii-check": print(str(s.isascii()).lower())
    elif op=="hex-encode": print(s.encode().hex())
    elif op=="hex-decode": sys.stdout.buffer.write(bytes.fromhex(s.strip()))
    elif op=="base32-encode": print(base64.b32encode(s.encode()).decode())
    elif op=="base32-decode": sys.stdout.buffer.write(base64.b32decode(s.strip().upper()))
    elif op=="base64url-encode": print(base64.urlsafe_b64encode(s.encode()).decode().rstrip("="))
    elif op=="base64url-decode":
        q=s.strip();sys.stdout.buffer.write(base64.urlsafe_b64decode(q+"="*((4-len(q)%4)%4)))
    elif op=="rot13": print(s.translate(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz","NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm")))
    elif op=="caesar":
        shift=int(a[0]);s=" ".join(a[1:]);out=[]
        for c in s:
            if c.isalpha():
                base=65 if c.isupper() else 97;out.append(chr((ord(c)-base+shift)%26+base))
            else:out.append(c)
        print("".join(out))
    elif op=="punycode": print(s.encode("idna").decode())
def xml_obj(e): return {"tag":e.tag,"attrs":dict(e.attrib),"text":(e.text or "").strip(),"children":[xml_obj(c) for c in e]}
def obj_xml(o):
    e=ET.Element(o["tag"],o.get("attrs",{}));e.text=o.get("text") or None
    for c in o.get("children",[]):e.append(obj_xml(c))
    return e
def xml_input(a):
    s=text_arg(a);return ET.fromstring(s),s
def strip_ns(tag): return tag.split("}",1)[-1]
def handle_xml(op,a):
    if op=="from-json":
        print(ET.tostring(obj_xml(json.loads(text_arg(a))),encoding="unicode"));return
    try:r,s=xml_input(a)
    except Exception as e:
        if op=="wellformed":emit({"valid":False,"error":str(e)});return
        raise
    if op=="wellformed":emit({"valid":True})
    elif op=="root":print(r.tag)
    elif op=="elements":emit([x.tag for x in r.iter()])
    elif op=="attrs":emit([{"tag":x.tag,"attrs":dict(x.attrib)} for x in r.iter() if x.attrib])
    elif op=="text":print(" ".join(x.strip() for x in r.itertext() if x.strip()))
    elif op=="find-tag":emit([xml_obj(x) for x in r.iter() if strip_ns(x.tag)==a[1]])
    elif op=="find-attr":emit([xml_obj(x) for x in r.iter() if a[1] in x.attrib and (len(a)<3 or x.attrib[a[1]]==a[2])])
    elif op=="pretty": ET.indent(r);print(ET.tostring(r,encoding="unicode"))
    elif op=="minify": print(ET.tostring(r,encoding="unicode",short_empty_elements=True))
    elif op=="namespaces":emit(sorted(set(re.findall(r"\{([^}]+)\}",ET.tostring(r,encoding="unicode")))))
    elif op=="paths":
        rows=[]
        def rec(e,p):
            rows.append(p)
            for c in e:rec(c,p+"/"+strip_ns(c.tag))
        rec(r,"/"+strip_ns(r.tag));emit(rows)
    elif op=="count":print(sum(1 for _ in r.iter()))
    elif op=="to-json":emit(xml_obj(r))
    elif op=="strip-ns":
        for x in r.iter():x.tag=strip_ns(x.tag)
        print(ET.tostring(r,encoding="unicode"))
    elif op=="remove-tag":
        target=a[1]
        for par in r.iter():
            for c in list(par):
                if strip_ns(c.tag)==target:par.remove(c)
        print(ET.tostring(r,encoding="unicode"))
    elif op=="set-attr":r.set(a[1],a[2]);print(ET.tostring(r,encoding="unicode"))
    elif op=="get-attr":print(r.get(a[1],""))
    elif op=="xpath-lite":emit([xml_obj(x) for x in r.findall(a[1])])
    elif op=="canonical":
        try: print(ET.canonicalize(s))
        except AttributeError: print(ET.tostring(r,encoding="unicode"))
def parse_props(s):
    d={}
    for l in s.splitlines():
        l=l.strip()
        if not l or l.startswith(("#","!")):continue
        m=re.search(r"[:=]",l)
        k,v=(l[:m.start()],l[m.end():]) if m else (l,"")
        d[k.strip()]=v.strip()
    return d
def parse_dotenv(s):
    d={}
    for l in s.splitlines():
        l=l.strip()
        if not l or l.startswith("#") or "=" not in l:continue
        k,v=l.split("=",1);d[k.strip()]=v.strip().strip("\"'")
    return d
def toml_simple(s):
    d={};cur=d
    for l in s.splitlines():
        l=l.split("#",1)[0].strip()
        if not l:continue
        if l.startswith("[") and l.endswith("]"):
            cur=d
            for p in l[1:-1].split("."):cur=cur.setdefault(p,{})
        elif "=" in l:
            k,v=l.split("=",1);k=k.strip();v=v.strip()
            try:v=json.loads(v)
            except:v=v.strip("\"'")
            cur[k]=v
    return d
def dotget(o,path):
    cur=o
    for p in path.split(".") if path else []:cur=cur[int(p)] if isinstance(cur,list) else cur[p]
    return cur
def handle_config(op,a):
    if op=="config-detect":
        ext=P(a[0]).suffix.lower();print({".ini":"ini",".cfg":"ini",".properties":"properties",".env":"dotenv",".toml":"toml",".json":"json"}.get(ext,"unknown"));return
    if op=="merge-json":
        x=json.loads(P(a[0]).read_text() if P(a[0]).exists() else a[0]);y=json.loads(P(a[1]).read_text() if P(a[1]).exists() else a[1]);z=dict(x);z.update(y);emit(z);return
    if op=="env-expand":print(os.path.expandvars(" ".join(a)));return
    if op.startswith("ini-") or op=="json-to-ini":
        if op=="json-to-ini":
            o=json.loads(text_arg(a));c=configparser.ConfigParser()
            for sec,v in o.items():c[sec]={k:str(x) for k,x in v.items()}
            import io;q=io.StringIO();c.write(q);print(q.getvalue(),end="");return
        c=configparser.ConfigParser();c.read_string(text_arg(a))
        if op=="ini-get":print(c.get(a[1],a[2]))
        elif op=="ini-set":
            c.set(a[1],a[2],a[3]);import io;q=io.StringIO();c.write(q);print(q.getvalue(),end="")
        elif op=="ini-sections":emit(c.sections())
        elif op=="ini-keys":emit(list(c[a[1]].keys()))
        elif op=="ini-to-json":emit({s:dict(c[s]) for s in c.sections()})
        return
    if op.startswith("props-") or op=="json-to-props":
        if op=="json-to-props":
            o=json.loads(text_arg(a));print("\n".join(f"{k}={v}" for k,v in o.items()));return
        d=parse_props(text_arg(a))
        if op=="props-get":print(d.get(a[1],""))
        elif op=="props-set":d[a[1]]=a[2];print("\n".join(f"{k}={v}" for k,v in d.items()))
        elif op=="props-to-json":emit(d)
        return
    if op.startswith("dotenv-") or op=="json-to-dotenv":
        if op=="json-to-dotenv":
            o=json.loads(text_arg(a));print("\n".join(f"{k}={shlex.quote(str(v))}" for k,v in o.items()));return
        d=parse_dotenv(text_arg(a))
        if op=="dotenv-get":print(d.get(a[1],""))
        elif op=="dotenv-set":d[a[1]]=a[2];print("\n".join(f"{k}={shlex.quote(str(v))}" for k,v in d.items()))
        elif op=="dotenv-to-json":emit(d)
        return
    if op.startswith("toml-"):
        d=toml_simple(text_arg(a))
        if op=="toml-get":emit(dotget(d,a[1]))
        elif op=="toml-keys":emit(list(dotget(d,a[1]).keys()) if len(a)>1 else list(d.keys()))
        elif op=="toml-to-json":emit(d)
def md_front(s):
    if s.startswith("---\n") and "\n---\n" in s[4:]:
        i=s.find("\n---\n",4);head=s[4:i];body=s[i+5:];return parse_props("\n".join(x.replace(":","=",1) for x in head.splitlines())),body
    return {},s
def handle_md(op,a):
    s=text_arg(a)
    if op=="headings":emit([{"level":len(m.group(1)),"text":m.group(2).strip()} for m in re.finditer(r"(?m)^(#{1,6})\s+(.+)$",s)])
    elif op=="links":emit(re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)",s))
    elif op=="images":emit(re.findall(r"!\[[^\]]*\]\(([^)]+)\)",s))
    elif op=="codeblocks":emit([{"lang":m.group(1),"code":m.group(2)} for m in re.finditer(r"\x60\x60\x60([^\n]*)\n(.*?)\x60\x60\x60",s,re.S)])
    elif op=="tables":print(sum(1 for l in s.splitlines() if "|" in l))
    elif op=="task-count":emit({"done":len(re.findall(r"(?mi)^\s*[-*]\s+\[x\]",s)),"open":len(re.findall(r"(?mi)^\s*[-*]\s+\[ \]",s))})
    elif op=="word-count":print(len(re.findall(r"\b\w+\b",s)))
    elif op=="toc":
        rows=[]
        for m in re.finditer(r"(?m)^(#{1,6})\s+(.+)$",s):
            t=m.group(2).strip();anchor=re.sub(r"[^a-z0-9 -]","",t.lower()).replace(" ","-");rows.append("  "*(len(m.group(1))-1)+f"- [{t}](#{anchor})")
        print("\n".join(rows))
    elif op=="strip":
        q=re.sub(r"\x60\x60\x60.*?\x60\x60\x60","",s,flags=re.S);q=re.sub(r"!\[[^\]]*\]\([^)]+\)","",q);q=re.sub(r"\[([^\]]+)\]\([^)]+\)",r"\1",q);q=re.sub(r"(?m)^#{1,6}\s*","",q);q=re.sub(r"[*_\x60~]","",q);print(q)
    elif op=="escape":print(re.sub(r"([\\*{}\[\]()#+\-.!_>])",r"\\\1",s))
    elif op=="unescape":print(re.sub(r"\\([\\*{}\[\]()#+\-.!_>])",r"\1",s))
    elif op=="frontmatter":emit(md_front(s)[0])
    elif op=="frontmatter-get":emit(md_front(s)[0].get(a[1]))
    elif op=="frontmatter-set":
        meta,body=md_front(s);meta[a[1]]=a[2];print("---\n"+"\n".join(f"{k}: {v}" for k,v in meta.items())+"\n---\n"+body)
    elif op=="normalize-headings":print(re.sub(r"(?m)^(#{1,6})\s*(.*?)\s*#*\s*$",lambda m:m.group(1)+" "+m.group(2).strip(),s))
    elif op=="check-links":
        links=re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)",s);emit({"links":links,"empty":[x for x in links if not x.strip()]})
    elif op=="code-languages":emit(Counter(m.group(1).strip() or "<none>" for m in re.finditer(r"\x60\x60\x60([^\n]*)\n",s)))
    elif op=="stats":emit({"chars":len(s),"lines":len(s.splitlines()),"words":len(re.findall(r"\b\w+\b",s)),"headings":len(re.findall(r"(?m)^#{1,6}\s+",s)),"links":len(re.findall(r"\[[^\]]+\]\([^)]+\)",s))})
    elif op=="anchor":
        t=" ".join(a);print(re.sub(r"-+","-",re.sub(r"[^a-z0-9 -]","",t.lower()).replace(" ","-")).strip("-"))
    elif op=="wrap-paragraphs":print("\n\n".join(textwrap.fill(p,width=int(a[1]) if len(a)>1 and P(a[0]).exists() else 80) for p in s.split("\n\n")))
def rx(pattern,flags=""):
    f=0
    if "i" in flags:f|=re.I
    if "m" in flags:f|=re.M
    if "s" in flags:f|=re.S
    return re.compile(pattern,f)
def handle_regex(op,a):
    if op in {"extract-numbers","extract-emails","extract-urls","extract-ips"}:
        s=text_arg(a);pat={"extract-numbers":r"[-+]?\d+(?:\.\d+)?","extract-emails":r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b","extract-urls":r"https?://[^\s<>'\"]+","extract-ips":r"\b(?:\d{1,3}\.){3}\d{1,3}\b"}[op]
        vals=re.findall(pat,s)
        if op=="extract-ips": vals=[x for x in vals if all(0<=int(p)<=255 for p in x.split("."))]
        emit(vals);return
    if op in {"escape","literal"}:print(re.escape(" ".join(a)));return
    if op=="validate":
        try:re.compile(a[0]);emit({"valid":True})
        except Exception as e:emit({"valid":False,"error":str(e)})
        return
    if len(a)<2:die("PATTERN TEXT/FILE [extra]")
    pat=a[0];src=a[1:];s=P(src[0]).read_text(errors="replace") if P(src[0]).exists() else " ".join(src)
    r=rx(pat,a[-1] if len(a)>2 and set(a[-1])<=set("ims") else "")
    if op=="test":print(str(bool(r.search(s))).lower())
    elif op=="find":
        m=r.search(s);emit({"match":m.group(0),"groups":m.groups(),"span":m.span()} if m else None)
    elif op=="findall":emit(r.findall(s))
    elif op=="replace":
        repl=a[1];s=P(a[2]).read_text(errors="replace") if len(a)>2 and P(a[2]).exists() else " ".join(a[2:]);print(r.sub(repl,s))
    elif op=="split":emit(r.split(s))
    elif op=="groups":print(r.groups)
    elif op=="named-groups":emit(r.groupindex)
    elif op=="flags":emit({"ignorecase":bool(r.flags&re.I),"multiline":bool(r.flags&re.M),"dotall":bool(r.flags&re.S)})
    elif op in {"line-filter","line-exclude"}:
        keep=(op=="line-filter");print("\n".join(l for l in s.splitlines() if bool(r.search(l))==keep))
    elif op=="count":print(sum(1 for _ in r.finditer(s)))
    elif op=="first":
        m=r.search(s);print(m.group(0) if m else "")
    elif op=="last":
        m=list(r.finditer(s));print(m[-1].group(0) if m else "")
def read_two(a):
    if len(a)<2:die("LEFT RIGHT")
    def q(x):return P(x).read_text(errors="replace") if P(x).exists() else x
    return q(a[0]),q(a[1])
def file_digest(p):
    h=hashlib.sha256()
    with P(p).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def handle_diff(op,a):
    if op in {"file-hash","file-size"}:
        print(file_digest(a[0]) if op=="file-hash" else P(a[0]).stat().st_size);return
    if op=="same-file":
        print(str(P(a[0]).stat().st_size==P(a[1]).stat().st_size and file_digest(a[0])==file_digest(a[1])).lower());return
    if op in {"dir-names","dir-size"}:
        l=P(a[0]);r=P(a[1]);ls={str(x.relative_to(l)):x for x in l.rglob("*") if x.is_file()};rs={str(x.relative_to(r)):x for x in r.rglob("*") if x.is_file()}
        if op=="dir-names":emit({"only_left":sorted(ls.keys()-rs.keys()),"only_right":sorted(rs.keys()-ls.keys()),"common":sorted(ls.keys()&rs.keys())})
        else:emit({"left":sum(x.stat().st_size for x in ls.values()),"right":sum(x.stat().st_size for x in rs.values())})
        return
    x,y=read_two(a);xl=x.splitlines();yl=y.splitlines()
    if op=="text-unified":print("\n".join(difflib.unified_diff(xl,yl,fromfile="left",tofile="right")))
    elif op=="text-context":print("\n".join(difflib.context_diff(xl,yl,fromfile="left",tofile="right")))
    elif op=="text-html":print(difflib.HtmlDiff().make_file(xl,yl,"left","right"))
    elif op in {"lines-added","lines-removed","lines-changed"}:
        d=list(difflib.ndiff(xl,yl))
        if op=="lines-added":emit([z[2:] for z in d if z.startswith("+ ")])
        elif op=="lines-removed":emit([z[2:] for z in d if z.startswith("- ")])
        else:print(sum(1 for z in d if z.startswith(("+ ","- "))))
    elif op=="json":
        a1=json.loads(x);a2=json.loads(y);emit({"equal":a1==a2,"left":a1,"right":a2} if a1!=a2 else {"equal":True})
    elif op=="json-keys":
        a1=json.loads(x);a2=json.loads(y);emit({"added":sorted(a2.keys()-a1.keys()),"removed":sorted(a1.keys()-a2.keys()),"changed":sorted(k for k in a1.keys()&a2.keys() if a1[k]!=a2[k])})
    elif op=="common-lines":emit(sorted(set(xl)&set(yl)))
    elif op=="unique-left":emit([z for z in xl if z not in set(yl)])
    elif op=="unique-right":emit([z for z in yl if z not in set(xl)])
    elif op=="sequence-ratio":print(difflib.SequenceMatcher(None,x,y).ratio())
    elif op=="prefix-common":print(os.path.commonprefix([x,y]))
    elif op=="suffix-common":
        n=0
        while n<min(len(x),len(y)) and x[-1-n]==y[-1-n]:n+=1
        print(x[len(x)-n:] if n else "")
    elif op=="hexdiff":
        xb=x.encode();yb=y.encode();emit([{"offset":i,"left":xb[i] if i<len(xb) else None,"right":yb[i] if i<len(yb) else None} for i in range(max(len(xb),len(yb))) if (xb[i] if i<len(xb) else None)!=(yb[i] if i<len(yb) else None)][:10000])
def proc_path(pid,name):return P("/proc")/str(pid)/name
def proc_info(pid):
    d={"pid":int(pid)}
    try:d["cmdline"]=proc_path(pid,"cmdline").read_bytes().replace(b"\0",b" ").decode(errors="replace").strip()
    except:pass
    try:
        for l in proc_path(pid,"status").read_text().splitlines():
            if ":" in l:
                k,v=l.split(":",1)
                if k in {"Name","State","PPid","Uid","Gid","Threads","VmRSS","VmSize"}:d[k]=v.strip()
    except:pass
    return d
def handle_proc(op,a):
    pid=int(a[0]) if a and a[0].isdigit() else os.getpid()
    if op=="self":emit(proc_info(os.getpid()));return
    if op=="pid-info":emit(proc_info(pid));return
    if op=="pid-cmdline":print(proc_path(pid,"cmdline").read_bytes().replace(b"\0",b" ").decode(errors="replace").strip());return
    if op=="pid-status":print(proc_path(pid,"status").read_text(errors="replace"));return
    if op=="pid-env":emit(dict(x.split("=",1) for x in proc_path(pid,"environ").read_bytes().decode(errors="replace").split("\0") if "=" in x));return
    if op=="pid-fds":emit([{"fd":x.name,"target":os.readlink(x)} for x in proc_path(pid,"fd").iterdir() if x.is_symlink()]);return
    if op=="pid-threads":emit(sorted(int(x.name) for x in proc_path(pid,"task").iterdir() if x.name.isdigit()));return
    if op=="pid-maps":print(proc_path(pid,"maps").read_text(errors="replace"));return
    if op=="pid-cwd":print(os.readlink(proc_path(pid,"cwd")));return
    if op=="pid-exe":print(os.readlink(proc_path(pid,"exe")));return
    pids=sorted(int(x.name) for x in P("/proc").iterdir() if x.name.isdigit())
    if op=="list":emit([proc_info(x) for x in pids])
    elif op=="search":
        q=" ".join(a).lower();emit([x for x in (proc_info(p) for p in pids) if q in x.get("cmdline","").lower() or q in x.get("Name","").lower()])
    elif op=="count":print(len(pids))
    elif op=="uptime":print(P("/proc/uptime").read_text().split()[0])
    elif op=="loadavg":emit(P("/proc/loadavg").read_text().split())
    elif op=="meminfo":
        d={}
        for l in P("/proc/meminfo").read_text().splitlines():
            if ":" in l:k,v=l.split(":",1);d[k]=v.strip()
        emit(d)
    elif op=="cpu-count":print(os.cpu_count())
    elif op=="kernel":print(os.uname().release)
    elif op=="limits":print(proc_path(pid,"limits").read_text(errors="replace"))
    elif op=="open-fds":print(len(list(proc_path(pid,"fd").iterdir())))
def mode_symbolic(mode):
    chars=[]
    for shift in (6,3,0):
        v=(mode>>shift)&7;chars += ["r" if v&4 else "-","w" if v&2 else "-","x" if v&1 else "-"]
    return "".join(chars)
def symbolic_mode(s):
    if len(s)!=9:die("symbolic mode must be rwxrwxrwx")
    n=0
    for i,c in enumerate(s):
        if c!="-":n|=[4,2,1][i%3] << (6-(i//3)*3)
    return n
def handle_perm(op,a):
    if op=="octal-to-symbolic":print(mode_symbolic(int(a[0],8)));return
    if op=="symbolic-to-octal":print(f"{symbolic_mode(a[0]):03o}");return
    if op=="umask":
        old=os.umask(0);os.umask(old);print(f"{old:03o}");return
    p=P(a[0]);st=p.lstat()
    if op=="mode":print(f"{stat.S_IMODE(st.st_mode):04o}")
    elif op=="is-readable":print(str(os.access(p,os.R_OK)).lower())
    elif op=="is-writable":print(str(os.access(p,os.W_OK)).lower())
    elif op=="is-executable":print(str(os.access(p,os.X_OK)).lower())
    elif op=="is-owner":print(str(st.st_uid==os.getuid()).lower())
    elif op=="chmod":os.chmod(p,int(a[1],8));print(f"{stat.S_IMODE(p.stat().st_mode):04o}")
    elif op=="add-exec":os.chmod(p,stat.S_IMODE(st.st_mode)|0o111);print(f"{stat.S_IMODE(p.stat().st_mode):04o}")
    elif op=="remove-exec":os.chmod(p,stat.S_IMODE(st.st_mode)&~0o111);print(f"{stat.S_IMODE(p.stat().st_mode):04o}")
    elif op=="stat":emit({"mode":f"{stat.S_IMODE(st.st_mode):04o}","uid":st.st_uid,"gid":st.st_gid,"inode":st.st_ino,"nlink":st.st_nlink,"device":st.st_dev,"size":st.st_size})
    elif op=="inode":print(st.st_ino)
    elif op=="links":print(st.st_nlink)
    elif op=="owner":print(st.st_uid)
    elif op=="group":print(st.st_gid)
    elif op=="same-device":print(str(st.st_dev==P(a[1]).stat().st_dev).lower())
    elif op=="is-symlink":print(str(p.is_symlink()).lower())
    elif op=="resolve-symlink":print(p.resolve())
    elif op=="access-matrix":emit({"read":os.access(p,os.R_OK),"write":os.access(p,os.W_OK),"execute":os.access(p,os.X_OK),"exists":p.exists()})
SEMVER=re.compile(r"^[vV]?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$")
def sv(s):
    m=SEMVER.fullmatch(s.strip())
    if not m:die("invalid semver")
    return int(m[1]),int(m[2]),int(m[3]),m[4] or "",m[5] or ""
def cmp_sv(a,b):
    x,y=sv(a),sv(b)
    if x[:3]!=y[:3]:return -1 if x[:3]<y[:3] else 1
    if x[3]==y[3]:return 0
    if not x[3]:return 1
    if not y[3]:return -1
    xa,ya=x[3].split("."),y[3].split(".")
    for i in range(max(len(xa),len(ya))):
        if i>=len(xa):return -1
        if i>=len(ya):return 1
        p,q=xa[i],ya[i]
        if p==q:continue
        if p.isdigit() and q.isdigit():return -1 if int(p)<int(q) else 1
        if p.isdigit()!=q.isdigit():return -1 if p.isdigit() else 1
        return -1 if p<q else 1
    return 0
def norm_sv(x):return f"{x[0]}.{x[1]}.{x[2]}"+(f"-{x[3]}" if x[3] else "")+(f"+{x[4]}" if x[4] else "")
def handle_semver(op,a):
    if op=="sort":
        import functools;emit(sorted(a,key=functools.cmp_to_key(cmp_sv)));return
    if op in {"max","min"}:
        import functools;vals=sorted(a,key=functools.cmp_to_key(cmp_sv));print(vals[-1] if op=="max" else vals[0]);return
    x=sv(a[0])
    if op=="parse":emit({"major":x[0],"minor":x[1],"patch":x[2],"prerelease":x[3] or None,"build":x[4] or None})
    elif op=="compare":print(cmp_sv(a[0],a[1]))
    elif op in {"bump-major","next-major"}:print(f"{x[0]+1}.0.0")
    elif op in {"bump-minor","next-minor"}:print(f"{x[0]}.{x[1]+1}.0")
    elif op in {"bump-patch","next-patch"}:print(f"{x[0]}.{x[1]}.{x[2]+1}")
    elif op=="is-prerelease":print(str(bool(x[3])).lower())
    elif op=="core":print(f"{x[0]}.{x[1]}.{x[2]}")
    elif op=="prerelease":print(x[3])
    elif op=="build":print(x[4])
    elif op=="satisfies-exact":print(str(cmp_sv(a[0],a[1])==0).lower())
    elif op=="satisfies-caret":
        y=sv(a[1]);upper=(y[0]+1,0,0) if y[0]>0 else ((0,y[1]+1,0) if y[1]>0 else (0,0,y[2]+1));print(str(x[:3]>=y[:3] and x[:3]<upper).lower())
    elif op=="satisfies-tilde":
        y=sv(a[1]);print(str(x[:3]>=y[:3] and x[:3]<(y[0],y[1]+1,0)).lower())
    elif op=="normalize":print(norm_sv(x))
    elif op=="distance":
        y=sv(a[1]);emit({"major":x[0]-y[0],"minor":x[1]-y[1],"patch":x[2]-y[2]})
def detect_level(line):
    m=re.search(r"\b(TRACE|DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|ERR|FATAL|CRITICAL|CRIT)\b",line,re.I);return m.group(1).upper() if m else "UNKNOWN"
def handle_log(op,a):
    s=text_arg(a);lines=s.splitlines()
    if op=="levels":emit([{"line":i+1,"level":detect_level(l),"text":l} for i,l in enumerate(lines)])
    elif op=="count-levels":emit(Counter(detect_level(l) for l in lines))
    elif op=="errors":print("\n".join(l for l in lines if detect_level(l) in {"ERROR","ERR","FATAL","CRITICAL","CRIT"}))
    elif op=="warnings":print("\n".join(l for l in lines if detect_level(l).startswith("WARN")))
    elif op=="tail-errors":
        rows=[l for l in lines if detect_level(l) in {"ERROR","ERR","FATAL","CRITICAL","CRIT"}];n=int(a[1]) if len(a)>1 and P(a[0]).exists() else 20;print("\n".join(rows[-n:]))
    elif op=="timestamps":emit(re.findall(r"\b\d{4}-\d{2}-\d{2}[T ][0-9:.+-]+Z?\b",s))
    elif op=="time-range":
        ts=[parse_dt(x) for x in re.findall(r"\b\d{4}-\d{2}-\d{2}T[0-9:.+-]+Z?\b",s)];emit({"first":min(ts).isoformat() if ts else None,"last":max(ts).isoformat() if ts else None})
    elif op=="grep":
        q=a[1] if len(a)>1 and P(a[0]).exists() else a[0];print("\n".join(l for l in lines if q.lower() in l.lower()))
    elif op=="json-lines":
        out=[]
        for i,l in enumerate(lines,1):
            try:out.append({"line":i,"value":json.loads(l)})
            except:pass
        emit(out)
    elif op=="invalid-json-lines":
        bad=[]
        for i,l in enumerate(lines,1):
            try:json.loads(l)
            except:bad.append(i)
        emit(bad)
    elif op=="dedupe":print("\n".join(dict.fromkeys(lines)))
    elif op=="top-messages":emit(Counter(re.sub(r"\b\d+\b","<n>",l) for l in lines).most_common(20))
    elif op=="top-words":emit(Counter(re.findall(r"\b\w+\b",s.lower())).most_common(50))
    elif op=="line-rate":
        secs=float(a[1]) if len(a)>1 and P(a[0]).exists() else float(a[0]);print(len(lines)/secs if secs else 0)
    elif op=="size":emit({"lines":len(lines),"chars":len(s),"bytes":len(s.encode())})
    elif op=="rotate-name":print(a[0]+"."+dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    elif op=="split-by-level":emit({k:[l for l in lines if detect_level(l)==k] for k in sorted(set(detect_level(l) for l in lines))})
    elif op=="extract-ids":emit(sorted(set(re.findall(r"\b(?:id|request_id|trace_id)[=: ]+([A-Za-z0-9_-]+)",s,re.I))))
    elif op=="extract-ips":
        vals=[]
        for x in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b",s):
            try:ipaddress.ip_address(x);vals.append(x)
            except:pass
        emit(sorted(set(vals)))
    elif op=="summary":emit({"lines":len(lines),"levels":Counter(detect_level(l) for l in lines),"errors":sum(detect_level(l) in {"ERROR","ERR","FATAL","CRITICAL","CRIT"} for l in lines),"warnings":sum(detect_level(l).startswith("WARN") for l in lines)})
def handle_stream(op,a):
    s=text_arg(a);lines=s.splitlines()
    filearg=bool(a and P(a[0]).exists());n=int(a[1]) if filearg and len(a)>1 and str(a[1]).lstrip("-").isdigit() else 10
    if op=="head":print("\n".join(lines[:n]))
    elif op=="tail":print("\n".join(lines[-n:]))
    elif op=="count":print(len(lines))
    elif op=="nonempty":print("\n".join(l for l in lines if l.strip()))
    elif op=="blank":print(sum(not l.strip() for l in lines))
    elif op=="number":print("\n".join(f"{i+1}\t{l}" for i,l in enumerate(lines)))
    elif op=="prefix":print("\n".join((a[1] if filearg and len(a)>1 else "> ")+l for l in lines))
    elif op=="suffix":print("\n".join(l+(a[1] if filearg and len(a)>1 else " <") for l in lines))
    elif op=="trim":print("\n".join(l.strip() for l in lines))
    elif op=="unique":print("\n".join(dict.fromkeys(lines)))
    elif op=="duplicates":emit([x for x,c in Counter(lines).items() if c>1])
    elif op=="sample":print("\n".join(random.sample(lines,min(n,len(lines)))))
    elif op=="every-n":print("\n".join(lines[::max(1,n)]))
    elif op=="chunk":emit([lines[i:i+n] for i in range(0,len(lines),n)])
    elif op=="join":print((a[1] if filearg and len(a)>1 else " ").join(lines))
    elif op=="split-delim":
        delim=a[1] if filearg and len(a)>1 else ",";emit([x for l in lines for x in l.split(delim)])
    elif op=="columns":
        delim=a[1] if filearg and len(a)>2 else None;idx=int(a[2] if filearg and len(a)>2 else 0);print("\n".join((l.split(delim)[idx] if len(l.split(delim))>idx else "") for l in lines))
    elif op=="reverse":print("\n".join(reversed(lines)))
    elif op=="shuffle":
        q=lines[:];random.shuffle(q);print("\n".join(q))
    elif op=="hash-lines":emit([hashlib.sha256(l.encode()).hexdigest() for l in lines])
def handle_shell(op,a):
    if op=="quote":print(shlex.quote(" ".join(a)))
    elif op=="join":print(shlex.join(a))
    elif op=="split":emit(shlex.split(" ".join(a)))
    elif op=="which":print(shutil.which(a[0]) or "")
    elif op=="path-list":emit(os.environ.get("PATH","").split(os.pathsep))
    elif op=="path-dedupe":print(os.pathsep.join(dict.fromkeys(x for x in os.environ.get("PATH","").split(os.pathsep) if x)))
    elif op=="path-missing":emit([x for x in os.environ.get("PATH","").split(os.pathsep) if x and not P(x).exists()])
    elif op=="env-get":print(os.environ.get(a[0],""))
    elif op=="env-has":print(str(a[0] in os.environ).lower())
    elif op=="env-list":emit(dict(os.environ))
    elif op=="env-prefix":emit({k:v for k,v in os.environ.items() if k.startswith(a[0])})
    elif op=="shebang":
        p=P(a[0]);lines=p.read_text(errors="replace").splitlines() if p.exists() else [];print(lines[0] if lines and lines[0].startswith("#!") else "")
    elif op=="command-exists":print(str(shutil.which(a[0]) is not None).lower())
    elif op=="command-type":
        q=shutil.which(a[0]);emit({"command":a[0],"path":q,"exists":bool(q),"executable":bool(q and os.access(q,os.X_OK))})
    elif op=="cwd":print(P.cwd())
    elif op=="home":print(P.home())
    elif op=="tempdir":print(tempfile.gettempdir())
    elif op=="shell":print(os.environ.get("SHELL","/system/bin/sh"))
    elif op=="argv-json":emit(a)
    elif op=="export-line":
        if len(a)<2:die("NAME VALUE")
        print(f"export {a[0]}={shlex.quote(' '.join(a[1:]))}")
def main():
    cmd=P(sys.argv[0]).name;a=sys.argv[1:]
    if cmd not in COMMANDS:
        if a and a[0] in COMMANDS:cmd=a.pop(0)
        elif not a or a[0] in ("-h","--help"):
            print("Ocean Workbench 300 functional utility suite");print("\n".join(COMMANDS));return
        else:die("unknown command")
    if a and a[0] in ("-h","--help"):
        print(f"{cmd} — Ocean Workbench utility");return
    rest=cmd.removeprefix("ocean-wb-");group,op=rest.split("-",1)
    handlers={"date":handle_date,"math":handle_math,"unit":handle_unit,"enc":handle_enc,"xml":handle_xml,"config":handle_config,"md":handle_md,"regex":handle_regex,"diff":handle_diff,"proc":handle_proc,"perm":handle_perm,"semver":handle_semver,"log":handle_log,"stream":handle_stream,"shell":handle_shell}
    handlers[group](op,a)
if __name__=="__main__":main()
