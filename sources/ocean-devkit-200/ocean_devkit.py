#!/usr/bin/env python3
from __future__ import annotations
import base64,bz2,csv,gzip,hashlib,hmac,html,io,ipaddress,json,mimetypes,os,re,secrets,shlex,shutil,socket,stat,subprocess,sys,tarfile,textwrap,time,urllib.parse,urllib.request,uuid,xml.etree.ElementTree as ET,zipfile,lzma
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
P=Path
VERSION="1.0.0"
APK=["ocean-apkx-entry-list","ocean-apkx-dex-count","ocean-apkx-dex-names","ocean-apkx-resource-list","ocean-apkx-native-abis","ocean-apkx-native-libs","ocean-apkx-permission-hints","ocean-apkx-feature-hints","ocean-apkx-manifest-bytes","ocean-apkx-file-map","ocean-apkx-compression-report","ocean-apkx-largest-files","ocean-apkx-duplicate-files","ocean-apkx-path-search","ocean-apkx-cert-files","ocean-apkx-integrity-hash","ocean-apkx-zip-test","ocean-apkx-assets-list","ocean-apkx-res-list","ocean-apkx-meta-inf-list"]
WEB=["ocean-webx-url-parse","ocean-webx-url-normalize","ocean-webx-query-get","ocean-webx-query-set","ocean-webx-query-delete","ocean-webx-http-head","ocean-webx-http-get","ocean-webx-http-json","ocean-webx-http-status","ocean-webx-http-headers","ocean-webx-http-download","ocean-webx-form-encode","ocean-webx-multipart-boundary","ocean-webx-html-links","ocean-webx-html-images","ocean-webx-html-title","ocean-webx-html-text","ocean-webx-robots-paths","ocean-webx-sitemap-urls","ocean-webx-cookie-parse"]
GIT=["ocean-gitx-status-json","ocean-gitx-branch-current","ocean-gitx-branches","ocean-gitx-log-json","ocean-gitx-last-commit","ocean-gitx-remotes","ocean-gitx-config-get","ocean-gitx-config-list","ocean-gitx-diff-stat","ocean-gitx-changed-files","ocean-gitx-untracked","ocean-gitx-root","ocean-gitx-object-type","ocean-gitx-object-size","ocean-gitx-show-file","ocean-gitx-tag-list","ocean-gitx-head-sha","ocean-gitx-short-sha","ocean-gitx-author","ocean-gitx-commit-message"]
TEXT=["ocean-textx-slug","ocean-textx-wordfreq","ocean-textx-lines-unique","ocean-textx-lines-duplicate","ocean-textx-lines-sort","ocean-textx-lines-reverse","ocean-textx-tabs-spaces","ocean-textx-spaces-tabs","ocean-textx-trim","ocean-textx-lower","ocean-textx-upper","ocean-textx-title","ocean-textx-wrap","ocean-textx-indent","ocean-textx-dedent","ocean-textx-prefix","ocean-textx-suffix","ocean-textx-replace","ocean-textx-regex-find","ocean-textx-regex-replace"]
DATA=["ocean-datax-json-pretty","ocean-datax-json-minify","ocean-datax-json-keys","ocean-datax-json-values","ocean-datax-json-flatten","ocean-datax-json-unflatten","ocean-datax-json-merge","ocean-datax-json-diff","ocean-datax-json-lines","ocean-datax-csv-head","ocean-datax-csv-columns","ocean-datax-csv-select","ocean-datax-csv-count","ocean-datax-csv-sort","ocean-datax-tsv-to-csv","ocean-datax-csv-to-tsv","ocean-datax-ndjson-to-json","ocean-datax-json-to-ndjson","ocean-datax-kv-json","ocean-datax-env-json"]
FS=["ocean-fsx-tree-size","ocean-fsx-largest","ocean-fsx-newest","ocean-fsx-oldest","ocean-fsx-empty","ocean-fsx-duplicates","ocean-fsx-extension-stats","ocean-fsx-mime-stats","ocean-fsx-name-search","ocean-fsx-content-search","ocean-fsx-checksum-manifest","ocean-fsx-verify-manifest","ocean-fsx-safe-name","ocean-fsx-touch-batch","ocean-fsx-mkdir-batch","ocean-fsx-copy-tree","ocean-fsx-file-age","ocean-fsx-path-depth","ocean-fsx-permissions","ocean-fsx-symlinks"]
NET=["ocean-netx-dns-a","ocean-netx-dns-aaaa","ocean-netx-dns-reverse","ocean-netx-tcp-check","ocean-netx-port-range","ocean-netx-http-latency","ocean-netx-url-latency","ocean-netx-ip-classify","ocean-netx-cidr-info","ocean-netx-cidr-contains","ocean-netx-cidr-split","ocean-netx-ip-int","ocean-netx-int-ip","ocean-netx-hostname","ocean-netx-interfaces","ocean-netx-route-lite","ocean-netx-proxy-env","ocean-netx-user-agent","ocean-netx-content-type","ocean-netx-download-size"]
CRYPTO=["ocean-cryptox-sha256-file","ocean-cryptox-sha512-file","ocean-cryptox-blake2b-file","ocean-cryptox-md5-file","ocean-cryptox-hmac-sha256","ocean-cryptox-hmac-sha512","ocean-cryptox-random-hex","ocean-cryptox-random-base64","ocean-cryptox-token-url","ocean-cryptox-uuid4","ocean-cryptox-uuid5","ocean-cryptox-pbkdf2","ocean-cryptox-scrypt","ocean-cryptox-compare","ocean-cryptox-base64-encode","ocean-cryptox-base64-decode","ocean-cryptox-hex-encode","ocean-cryptox-hex-decode","ocean-cryptox-file-fingerprint","ocean-cryptox-dir-fingerprint"]
BUILD=["ocean-buildx-env-report","ocean-buildx-tool-versions","ocean-buildx-path-check","ocean-buildx-shebang-check","ocean-buildx-executable-check","ocean-buildx-script-lint","ocean-buildx-json-check","ocean-buildx-xml-check","ocean-buildx-python-compile","ocean-buildx-python-imports","ocean-buildx-c-includes","ocean-buildx-make-targets","ocean-buildx-gradle-tasks-lite","ocean-buildx-package-json-scripts","ocean-buildx-lockfiles","ocean-buildx-source-count","ocean-buildx-todo-scan","ocean-buildx-binary-detect","ocean-buildx-line-endings","ocean-buildx-repro-hash"]
ARCHIVE=["ocean-archivex-zip-list","ocean-archivex-zip-test","ocean-archivex-zip-extract-one","ocean-archivex-zip-top","ocean-archivex-zip-ratio","ocean-archivex-tar-list","ocean-archivex-tar-test","ocean-archivex-tar-extract-one","ocean-archivex-gzip-info","ocean-archivex-gzip-test","ocean-archivex-gzip-decompress","ocean-archivex-bz2-test","ocean-archivex-xz-test","ocean-archivex-file-count","ocean-archivex-largest-entry","ocean-archivex-extension-stats","ocean-archivex-manifest-hash","ocean-archivex-path-search","ocean-archivex-safe-check"]
COMMANDS=APK+WEB+GIT+TEXT+DATA+FS+NET+CRYPTO+BUILD+ARCHIVE+["ocean-devkit-runtime"]
assert len(COMMANDS)==200 and len(set(COMMANDS))==200
def emit(x):
    if isinstance(x,(dict,list,tuple)):print(json.dumps(x,indent=2,ensure_ascii=False,default=str))
    else:print(x)
def die(s,c=2):print(s,file=sys.stderr);raise SystemExit(c)
def inp(a):
    if a and P(a[0]).exists() and P(a[0]).is_file():return P(a[0]).read_text(errors="replace")
    return " ".join(a) if a else sys.stdin.read()
def filehash(path,algo="sha256"):
    h=hashlib.new(algo)
    with P(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()
def walkfiles(root):
    p=P(root)
    if p.is_file():return [p]
    return [x for x in p.rglob("*") if x.is_file()]
def safe_join(base,name):
    b=P(base).resolve();p=(b/name).resolve()
    if p!=b and b not in p.parents:die("unsafe archive path")
    return p
def apk_strings(data):
    vals=set(x.decode(errors="ignore") for x in re.findall(rb"[A-Za-z0-9_.$:/-]{6,}",data))
    try:
        u=data.decode("utf-16le",errors="ignore")
        vals.update(re.findall(r"[A-Za-z0-9_.$:/-]{6,}",u))
    except:pass
    return vals
def handle_apk(cmd,a):
    if not a:die("APK path required")
    p=P(a[0]);z=zipfile.ZipFile(p);infos=z.infolist();names=[i.filename for i in infos]
    if cmd=="ocean-apkx-entry-list":emit(names)
    elif cmd=="ocean-apkx-dex-count":print(sum(bool(re.fullmatch(r"classes\d*\.dex",P(n).name)) for n in names))
    elif cmd=="ocean-apkx-dex-names":emit([n for n in names if re.fullmatch(r"classes\d*\.dex",P(n).name)])
    elif cmd=="ocean-apkx-resource-list":emit([n for n in names if n.startswith("res/") or n=="resources.arsc"])
    elif cmd=="ocean-apkx-native-abis":emit(sorted({n.split("/")[1] for n in names if n.startswith("lib/") and n.count("/")>=2}))
    elif cmd=="ocean-apkx-native-libs":emit([n for n in names if n.startswith("lib/") and n.endswith(".so")])
    elif cmd in ("ocean-apkx-permission-hints","ocean-apkx-feature-hints"):
        raw=z.read("AndroidManifest.xml") if "AndroidManifest.xml" in names else b"";ss=apk_strings(raw)
        pref="android.permission." if "permission" in cmd else "android.hardware."
        emit(sorted(x for x in ss if x.startswith(pref)))
    elif cmd=="ocean-apkx-manifest-bytes":
        raw=z.read("AndroidManifest.xml") if "AndroidManifest.xml" in names else b"";emit({"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()})
    elif cmd=="ocean-apkx-file-map":emit([{"name":i.filename,"size":i.file_size,"compressed":i.compress_size,"method":i.compress_type} for i in infos])
    elif cmd=="ocean-apkx-compression-report":
        raw=sum(i.file_size for i in infos);comp=sum(i.compress_size for i in infos);emit({"files":len(infos),"raw_bytes":raw,"compressed_bytes":comp,"ratio":comp/raw if raw else 0})
    elif cmd=="ocean-apkx-largest-files":emit(sorted([{"name":i.filename,"bytes":i.file_size} for i in infos],key=lambda x:x["bytes"],reverse=True)[:int(a[1]) if len(a)>1 else 20])
    elif cmd=="ocean-apkx-duplicate-files":
        d={}
        for i in infos:
            if i.is_dir():continue
            h=hashlib.sha256(z.read(i)).hexdigest();d.setdefault(h,[]).append(i.filename)
        emit([{"sha256":h,"files":v} for h,v in d.items() if len(v)>1])
    elif cmd=="ocean-apkx-path-search":
        q=a[1].lower() if len(a)>1 else "";emit([n for n in names if q in n.lower()])
    elif cmd=="ocean-apkx-cert-files":emit([n for n in names if n.upper().startswith("META-INF/") and n.upper().endswith((".RSA",".DSA",".EC",".SF",".MF"))])
    elif cmd=="ocean-apkx-integrity-hash":emit({"sha256":filehash(p),"bytes":p.stat().st_size})
    elif cmd=="ocean-apkx-zip-test":emit({"valid":z.testzip() is None,"bad_entry":z.testzip()})
    elif cmd=="ocean-apkx-assets-list":emit([n for n in names if n.startswith("assets/")])
    elif cmd=="ocean-apkx-res-list":emit([n for n in names if n.startswith("res/")])
    elif cmd=="ocean-apkx-meta-inf-list":emit([n for n in names if n.upper().startswith("META-INF/")])
    z.close()
class H(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.images=[];self.title=[];self.text=[];self._title=False
    def handle_starttag(self,t,attrs):
        d=dict(attrs)
        if t=="a" and d.get("href"):self.links.append(d["href"])
        if t=="img" and d.get("src"):self.images.append(d["src"])
        if t=="title":self._title=True
    def handle_endtag(self,t):
        if t=="title":self._title=False
    def handle_data(self,d):
        if self._title:self.title.append(d)
        if d.strip():self.text.append(d.strip())
def req(url,method="GET"):
    return urllib.request.urlopen(urllib.request.Request(url,method=method,headers={"User-Agent":"OceanDevKit/1.0"}),timeout=20)
def handle_web(cmd,a):
    if cmd=="ocean-webx-multipart-boundary":print("----Ocean"+secrets.token_hex(16));return
    if cmd=="ocean-webx-form-encode":
        pairs=[x.split("=",1) if "=" in x else (x,"") for x in a];print(urllib.parse.urlencode(pairs));return
    if not a:die("URL/input required")
    if cmd.startswith("ocean-webx-url-") or cmd.startswith("ocean-webx-query-"):
        u=urllib.parse.urlsplit(a[0]);q=urllib.parse.parse_qsl(u.query,keep_blank_values=True)
        if cmd=="ocean-webx-url-parse":emit({"scheme":u.scheme,"netloc":u.netloc,"hostname":u.hostname,"port":u.port,"path":u.path,"query":dict(q),"fragment":u.fragment});return
        if cmd=="ocean-webx-url-normalize":
            scheme=(u.scheme or "https").lower();host=(u.hostname or "").lower();port=(":"+str(u.port)) if u.port and not((scheme=="http" and u.port==80)or(scheme=="https" and u.port==443)) else "";path=urllib.parse.quote(urllib.parse.unquote(u.path or "/"),safe="/:@");print(urllib.parse.urlunsplit((scheme,host+port,path,urllib.parse.urlencode(sorted(q)),u.fragment)));return
        key=a[1] if len(a)>1 else ""
        if cmd=="ocean-webx-query-get":emit([v for k,v in q if k==key]);return
        if cmd=="ocean-webx-query-set":
            val=a[2] if len(a)>2 else "";q=[(k,v) for k,v in q if k!=key]+[(key,val)]
        else:q=[(k,v) for k,v in q if k!=key]
        print(urllib.parse.urlunsplit((u.scheme,u.netloc,u.path,urllib.parse.urlencode(q),u.fragment)));return
    if cmd in ("ocean-webx-http-head","ocean-webx-http-status","ocean-webx-http-headers","ocean-webx-content-type","ocean-webx-download-size"):
        with req(a[0],"HEAD") as r:
            if cmd=="ocean-webx-http-status":print(r.status)
            elif cmd=="ocean-webx-http-headers":emit(dict(r.headers.items()))
            elif cmd=="ocean-webx-content-type":print(r.headers.get("Content-Type",""))
            elif cmd=="ocean-webx-download-size":print(r.headers.get("Content-Length","unknown"))
            else:emit({"status":r.status,"headers":dict(r.headers.items())})
        return
    if cmd=="ocean-webx-http-download":
        if len(a)<2:die("URL OUTPUT");urllib.request.urlretrieve(a[0],a[1]);emit({"path":a[1],"bytes":P(a[1]).stat().st_size});return
    if cmd in ("ocean-webx-http-get","ocean-webx-http-json"):
        with req(a[0]) as r:raw=r.read()
        if cmd.endswith("json"):emit(json.loads(raw))
        else:sys.stdout.buffer.write(raw)
        return
    if cmd in ("ocean-webx-html-links","ocean-webx-html-images","ocean-webx-html-title","ocean-webx-html-text"):
        s=inp(a);p=H();p.feed(s)
        if cmd.endswith("links"):emit(p.links)
        elif cmd.endswith("images"):emit(p.images)
        elif cmd.endswith("title"):print(" ".join(p.title).strip())
        else:print("\n".join(p.text))
        return
    if cmd=="ocean-webx-robots-paths":
        emit([l.split(":",1)[1].strip() for l in inp(a).splitlines() if l.lower().startswith(("allow:","disallow:"))]);return
    if cmd=="ocean-webx-sitemap-urls":
        root=ET.fromstring(inp(a));emit([x.text.strip() for x in root.iter() if x.tag.endswith("loc") and x.text]);return
    if cmd=="ocean-webx-cookie-parse":
        emit({k.strip():v.strip() for k,v in [x.split("=",1) for x in inp(a).split(";") if "=" in x]});return
def git(args):
    try:return subprocess.check_output(["git"]+args,text=True,stderr=subprocess.STDOUT).rstrip("\n")
    except subprocess.CalledProcessError as e:die(e.output.strip() or "git command failed")
def handle_git(cmd,a):
    if cmd=="ocean-gitx-status-json":
        rows=[]
        for l in git(["status","--porcelain=v1"]).splitlines():
            if l:rows.append({"xy":l[:2],"path":l[3:]})
        emit(rows);return
    if cmd=="ocean-gitx-branch-current":print(git(["branch","--show-current"]));return
    if cmd=="ocean-gitx-branches":emit([x.strip().lstrip("* ") for x in git(["branch","--format=%(refname:short)"]).splitlines() if x.strip()]);return
    if cmd=="ocean-gitx-log-json":
        n=a[0] if a else "20";raw=git(["log","-"+n,"--pretty=format:%H%x09%an%x09%ae%x09%aI%x09%s"]);emit([dict(zip(["sha","author","email","date","subject"],l.split("\t",4))) for l in raw.splitlines()]);return
    if cmd=="ocean-gitx-last-commit":emit({"sha":git(["rev-parse","HEAD"]),"message":git(["log","-1","--pretty=%B"])});return
    if cmd=="ocean-gitx-remotes":emit([dict(zip(["name","url","kind"],l.split())) for l in git(["remote","-v"]).splitlines()]);return
    if cmd=="ocean-gitx-config-get":print(git(["config","--get",a[0]]));return
    if cmd=="ocean-gitx-config-list":emit(git(["config","--list"]).splitlines());return
    if cmd=="ocean-gitx-diff-stat":print(git(["diff","--stat"]+a));return
    if cmd=="ocean-gitx-changed-files":emit(git(["diff","--name-only"]+a).splitlines());return
    if cmd=="ocean-gitx-untracked":emit([l[3:] for l in git(["status","--porcelain"]).splitlines() if l.startswith("?? ")]);return
    if cmd=="ocean-gitx-root":print(git(["rev-parse","--show-toplevel"]));return
    if cmd=="ocean-gitx-object-type":print(git(["cat-file","-t",a[0]]));return
    if cmd=="ocean-gitx-object-size":print(git(["cat-file","-s",a[0]]));return
    if cmd=="ocean-gitx-show-file":print(git(["show",a[0]]));return
    if cmd=="ocean-gitx-tag-list":emit(git(["tag","--list"]).splitlines());return
    if cmd=="ocean-gitx-head-sha":print(git(["rev-parse","HEAD"]));return
    if cmd=="ocean-gitx-short-sha":print(git(["rev-parse","--short",a[0] if a else "HEAD"]));return
    if cmd=="ocean-gitx-author":print(git(["log","-1","--pretty=%an <%ae>",a[0] if a else "HEAD"]));return
    if cmd=="ocean-gitx-commit-message":print(git(["log","-1","--pretty=%B",a[0] if a else "HEAD"]));return
def handle_text(cmd,a):
    s=inp(a);lines=s.splitlines()
    if cmd=="ocean-textx-slug":print(re.sub(r"[^a-z0-9]+","-",s.lower()).strip("-"))
    elif cmd=="ocean-textx-wordfreq":emit(Counter(re.findall(r"\b[\w'-]+\b",s.lower())).most_common(int(a[1]) if len(a)>1 and P(a[0]).exists() else 50))
    elif cmd=="ocean-textx-lines-unique":print("\n".join(dict.fromkeys(lines)))
    elif cmd=="ocean-textx-lines-duplicate":emit([x for x,n in Counter(lines).items() if n>1])
    elif cmd=="ocean-textx-lines-sort":print("\n".join(sorted(lines,key=str.lower)))
    elif cmd=="ocean-textx-lines-reverse":print("\n".join(reversed(lines)))
    elif cmd=="ocean-textx-tabs-spaces":print(s.replace("\t"," "*int(a[1] if len(a)>1 and P(a[0]).exists() else 4)),end="")
    elif cmd=="ocean-textx-spaces-tabs":print(s.replace(" "*int(a[1] if len(a)>1 and P(a[0]).exists() else 4),"\t"),end="")
    elif cmd=="ocean-textx-trim":print("\n".join(x.strip() for x in lines))
    elif cmd=="ocean-textx-lower":print(s.lower(),end="")
    elif cmd=="ocean-textx-upper":print(s.upper(),end="")
    elif cmd=="ocean-textx-title":print(s.title(),end="")
    elif cmd=="ocean-textx-wrap":print(textwrap.fill(s,width=int(a[1]) if len(a)>1 and P(a[0]).exists() else 80))
    elif cmd=="ocean-textx-indent":print(textwrap.indent(s,a[1] if len(a)>1 and P(a[0]).exists() else "  "),end="")
    elif cmd=="ocean-textx-dedent":print(textwrap.dedent(s),end="")
    elif cmd=="ocean-textx-prefix":print("\n".join((a[1] if len(a)>1 and P(a[0]).exists() else "> ")+x for x in lines))
    elif cmd=="ocean-textx-suffix":print("\n".join(x+(a[1] if len(a)>1 and P(a[0]).exists() else " <") for x in lines))
    elif cmd=="ocean-textx-replace":
        off=1 if a and P(a[0]).exists() else 0;print(s.replace(a[off],a[off+1]),end="")
    elif cmd=="ocean-textx-regex-find":
        off=1 if a and P(a[0]).exists() else 0;emit(re.findall(a[off],s,re.M))
    elif cmd=="ocean-textx-regex-replace":
        off=1 if a and P(a[0]).exists() else 0;print(re.sub(a[off],a[off+1],s,flags=re.M),end="")
def loadj(x):return json.loads(P(x).read_text() if P(x).exists() else x)
def flat(o,p="",r=None):
    r={} if r is None else r
    if isinstance(o,dict):
        for k,v in o.items():flat(v,f"{p}.{k}" if p else k,r)
    elif isinstance(o,list):
        for i,v in enumerate(o):flat(v,f"{p}.{i}" if p else str(i),r)
    else:r[p]=o
    return r
def unflat(d):
    root={}
    for k,v in d.items():
        cur=root;parts=k.split(".")
        for p in parts[:-1]:cur=cur.setdefault(p,{})
        cur[parts[-1]]=v
    return root
def handle_data(cmd,a):
    if cmd.startswith("ocean-datax-json-"):
        if not a:die("JSON/file required")
        o=loadj(a[0])
        if cmd=="ocean-datax-json-pretty":print(json.dumps(o,indent=2,ensure_ascii=False))
        elif cmd=="ocean-datax-json-minify":print(json.dumps(o,separators=(",",":"),ensure_ascii=False))
        elif cmd=="ocean-datax-json-keys":emit(list(o.keys()) if isinstance(o,dict) else list(range(len(o))))
        elif cmd=="ocean-datax-json-values":emit(list(o.values()) if isinstance(o,dict) else o)
        elif cmd=="ocean-datax-json-flatten":emit(flat(o))
        elif cmd=="ocean-datax-json-unflatten":emit(unflat(o))
        elif cmd=="ocean-datax-json-merge":
            q=loadj(a[1]);r=dict(o);r.update(q);emit(r)
        elif cmd=="ocean-datax-json-diff":
            q=loadj(a[1]);fo,fq=flat(o),flat(q);emit({"added":{k:fq[k] for k in fq.keys()-fo.keys()},"removed":{k:fo[k] for k in fo.keys()-fq.keys()},"changed":{k:[fo[k],fq[k]] for k in fo.keys()&fq.keys() if fo[k]!=fq[k]}})
        elif cmd=="ocean-datax-json-lines":
            rows=o if isinstance(o,list) else [o]
            for x in rows:print(json.dumps(x,separators=(",",":"),ensure_ascii=False))
        elif cmd=="ocean-datax-json-to-ndjson":
            for x in (o if isinstance(o,list) else [o]):print(json.dumps(x,separators=(",",":"),ensure_ascii=False))
        return
    if cmd=="ocean-datax-ndjson-to-json":emit([json.loads(l) for l in inp(a).splitlines() if l.strip()]);return
    if cmd=="ocean-datax-kv-json":
        emit({k:v for k,v in (x.split("=",1) for x in a if "=" in x)});return
    if cmd=="ocean-datax-env-json":emit(dict(os.environ));return
    if not a:die("CSV file required")
    delim="\t" if cmd=="ocean-datax-tsv-to-csv" else ","
    with P(a[0]).open(newline="",errors="replace") as f:rows=list(csv.reader(f,delimiter=delim))
    if cmd=="ocean-datax-csv-head":emit(rows[:int(a[1]) if len(a)>1 else 6])
    elif cmd=="ocean-datax-csv-columns":emit(rows[0] if rows else [])
    elif cmd=="ocean-datax-csv-select":
        ids=[int(x) for x in a[1].split(",")];w=csv.writer(sys.stdout);w.writerows([[r[i] for i in ids if i<len(r)] for r in rows])
    elif cmd=="ocean-datax-csv-count":print(max(0,len(rows)-1))
    elif cmd=="ocean-datax-csv-sort":
        i=int(a[1]);head=rows[:1];body=sorted(rows[1:],key=lambda r:r[i] if i<len(r) else "");w=csv.writer(sys.stdout);w.writerows(head+body)
    elif cmd in ("ocean-datax-tsv-to-csv","ocean-datax-csv-to-tsv"):
        w=csv.writer(sys.stdout,delimiter="," if cmd.endswith("to-csv") else "\t");w.writerows(rows)
def handle_fs(cmd,a):
    if cmd in ("ocean-fsx-touch-batch","ocean-fsx-mkdir-batch"):
        for x in a:(P(x).touch() if cmd.endswith("touch-batch") else P(x).mkdir(parents=True,exist_ok=True))
        emit({"count":len(a)});return
    if cmd=="ocean-fsx-safe-name":
        s=" ".join(a);print(re.sub(r"[^A-Za-z0-9._-]+","_",s).strip("._") or "file");return
    root=P(a[0] if a else ".");files=walkfiles(root)
    if cmd=="ocean-fsx-tree-size":print(sum(x.stat().st_size for x in files))
    elif cmd in ("ocean-fsx-largest","ocean-fsx-newest","ocean-fsx-oldest"):
        key=(lambda x:x.stat().st_size) if cmd.endswith("largest") else (lambda x:x.stat().st_mtime);rev=not cmd.endswith("oldest");emit([{"path":str(x),"bytes":x.stat().st_size,"mtime":x.stat().st_mtime} for x in sorted(files,key=key,reverse=rev)[:int(a[1]) if len(a)>1 else 20]])
    elif cmd=="ocean-fsx-empty":emit([str(x) for x in files if x.stat().st_size==0])
    elif cmd=="ocean-fsx-duplicates":
        by={}
        for x in files:
            k=(x.stat().st_size,filehash(x));by.setdefault(k,[]).append(str(x))
        emit([v for v in by.values() if len(v)>1])
    elif cmd=="ocean-fsx-extension-stats":emit(Counter((x.suffix.lower() or "<none>") for x in files))
    elif cmd=="ocean-fsx-mime-stats":emit(Counter(mimetypes.guess_type(str(x))[0] or "application/octet-stream" for x in files))
    elif cmd=="ocean-fsx-name-search":
        q=a[1].lower();emit([str(x) for x in files if q in x.name.lower()])
    elif cmd=="ocean-fsx-content-search":
        pat=re.compile(a[1]);hits=[]
        for x in files:
            try:
                for n,l in enumerate(x.read_text(errors="replace").splitlines(),1):
                    if pat.search(l):hits.append({"path":str(x),"line":n,"text":l[:500]})
            except:pass
        emit(hits[:5000])
    elif cmd=="ocean-fsx-checksum-manifest":
        target=P(a[1]) if len(a)>1 else P("SHA256SUMS.json");target.write_text(json.dumps({str(x.relative_to(root) if root.is_dir() else x.name):filehash(x) for x in files},indent=2)+"\n");emit({"path":str(target),"files":len(files)})
    elif cmd=="ocean-fsx-verify-manifest":
        m=json.loads(P(a[1]).read_text());bad=[]
        for rel,hv in m.items():
            p=root/rel if root.is_dir() else root
            if not p.exists() or filehash(p)!=hv:bad.append(rel)
        emit({"valid":not bad,"bad":bad})
    elif cmd=="ocean-fsx-copy-tree":
        dst=P(a[1]);shutil.copytree(root,dst,dirs_exist_ok=True);emit({"destination":str(dst)})
    elif cmd=="ocean-fsx-file-age":print(max(0,time.time()-root.stat().st_mtime))
    elif cmd=="ocean-fsx-path-depth":print(len(root.resolve().parts))
    elif cmd=="ocean-fsx-permissions":emit({"mode":oct(stat.S_IMODE(root.stat().st_mode)),"read":os.access(root,os.R_OK),"write":os.access(root,os.W_OK),"execute":os.access(root,os.X_OK)})
    elif cmd=="ocean-fsx-symlinks":emit([{"path":str(x),"target":os.readlink(x)} for x in root.rglob("*") if x.is_symlink()])
def handle_net(cmd,a):
    if cmd=="ocean-netx-hostname":print(socket.gethostname());return
    if cmd=="ocean-netx-interfaces":
        p=P("/sys/class/net");emit([x.name for x in p.iterdir()] if p.exists() else []);return
    if cmd=="ocean-netx-route-lite":
        p=P("/proc/net/route");emit(p.read_text().splitlines() if p.exists() else []);return
    if cmd=="ocean-netx-proxy-env":emit({k:v for k,v in os.environ.items() if "proxy" in k.lower()});return
    if cmd=="ocean-netx-user-agent":print("OceanDevKit/1.0 (Android; arm64)");return
    if cmd=="ocean-netx-content-type":print(mimetypes.guess_type(a[0])[0] or "application/octet-stream");return
    if cmd=="ocean-netx-download-size":
        with req(a[0],"HEAD") as r:print(r.headers.get("Content-Length","unknown"));return
    if not a:die("argument required")
    if cmd in ("ocean-netx-dns-a","ocean-netx-dns-aaaa"):
        fam=socket.AF_INET if cmd.endswith("dns-a") else socket.AF_INET6;emit(sorted({x[4][0] for x in socket.getaddrinfo(a[0],None,fam)}));return
    if cmd=="ocean-netx-dns-reverse":emit(socket.gethostbyaddr(a[0]));return
    if cmd=="ocean-netx-tcp-check":
        host=a[0];port=int(a[1]);t=time.time()
        try:s=socket.create_connection((host,port),float(a[2]) if len(a)>2 else 3);s.close();emit({"open":True,"latency_ms":round((time.time()-t)*1000,2)})
        except Exception as e:emit({"open":False,"error":str(e)})
        return
    if cmd=="ocean-netx-port-range":
        host=a[0];start,end=int(a[1]),int(a[2]); 
        if end-start>255:die("range limited to 256 ports")
        found=[]
        for port in range(start,end+1):
            s=socket.socket();s.settimeout(.15)
            try:
                if s.connect_ex((host,port))==0:found.append(port)
            finally:s.close()
        emit(found);return
    if cmd in ("ocean-netx-http-latency","ocean-netx-url-latency"):
        t=time.time()
        with req(a[0],"HEAD") as r:emit({"status":r.status,"latency_ms":round((time.time()-t)*1000,2)})
        return
    if cmd=="ocean-netx-ip-classify":
        x=ipaddress.ip_address(a[0]);emit({"version":x.version,"private":x.is_private,"global":x.is_global,"loopback":x.is_loopback,"multicast":x.is_multicast,"reserved":x.is_reserved});return
    if cmd=="ocean-netx-cidr-info":
        n=ipaddress.ip_network(a[0],strict=False);emit({"network":str(n.network_address),"broadcast":str(n.broadcast_address),"prefix":n.prefixlen,"addresses":n.num_addresses,"version":n.version});return
    if cmd=="ocean-netx-cidr-contains":print(str(ipaddress.ip_address(a[1]) in ipaddress.ip_network(a[0],strict=False)).lower());return
    if cmd=="ocean-netx-cidr-split":
        n=ipaddress.ip_network(a[0],strict=False);emit([str(x) for x in n.subnets(new_prefix=int(a[1]))]);return
    if cmd=="ocean-netx-ip-int":print(int(ipaddress.ip_address(a[0])));return
    if cmd=="ocean-netx-int-ip":print(ipaddress.ip_address(int(a[0])));return
def handle_crypto(cmd,a):
    if cmd.endswith("-file") or cmd in ("ocean-cryptox-file-fingerprint","ocean-cryptox-dir-fingerprint"):
        if not a:die("path required")
        if cmd=="ocean-cryptox-dir-fingerprint":
            root=P(a[0]);h=hashlib.sha256()
            for p in sorted(walkfiles(root),key=str):h.update(str(p.relative_to(root)).encode()+b"\0"+bytes.fromhex(filehash(p)))
            print(h.hexdigest());return
        algo="sha256" if "sha256" in cmd or "fingerprint" in cmd else "sha512" if "sha512" in cmd else "blake2b" if "blake2b" in cmd else "md5";print(filehash(a[0],algo));return
    if cmd in ("ocean-cryptox-hmac-sha256","ocean-cryptox-hmac-sha512"):
        if len(a)<2:die("KEY DATA");print(hmac.new(a[0].encode()," ".join(a[1:]).encode(),getattr(hashlib,"sha256" if cmd.endswith("sha256") else "sha512")).hexdigest());return
    if cmd=="ocean-cryptox-random-hex":print(secrets.token_hex(int(a[0]) if a else 32));return
    if cmd=="ocean-cryptox-random-base64":print(base64.b64encode(secrets.token_bytes(int(a[0]) if a else 32)).decode());return
    if cmd=="ocean-cryptox-token-url":print(secrets.token_urlsafe(int(a[0]) if a else 32));return
    if cmd=="ocean-cryptox-uuid4":print(uuid.uuid4());return
    if cmd=="ocean-cryptox-uuid5":print(uuid.uuid5(uuid.NAMESPACE_URL," ".join(a)));return
    if cmd=="ocean-cryptox-pbkdf2":
        if len(a)<2:die("PASSWORD SALT [ITERATIONS]");print(hashlib.pbkdf2_hmac("sha256",a[0].encode(),a[1].encode(),int(a[2]) if len(a)>2 else 200000).hex());return
    if cmd=="ocean-cryptox-scrypt":
        if len(a)<2:die("PASSWORD SALT");print(hashlib.scrypt(a[0].encode(),salt=a[1].encode(),n=2**14,r=8,p=1).hex());return
    if cmd=="ocean-cryptox-compare":
        if len(a)<2:die("A B");print(str(hmac.compare_digest(a[0],a[1])).lower());return
    data=(" ".join(a)).encode()
    if cmd=="ocean-cryptox-base64-encode":print(base64.b64encode(data).decode());return
    if cmd=="ocean-cryptox-base64-decode":sys.stdout.buffer.write(base64.b64decode(a[0]));return
    if cmd=="ocean-cryptox-hex-encode":print(data.hex());return
    if cmd=="ocean-cryptox-hex-decode":sys.stdout.buffer.write(bytes.fromhex(a[0]));return
def handle_build(cmd,a):
    root=P(a[0] if a and P(a[0]).exists() else ".")
    if cmd=="ocean-buildx-env-report":emit({"cwd":str(P.cwd()),"python":sys.version,"path":os.environ.get("PATH"),"prefix":os.environ.get("PREFIX"),"arch":os.uname().machine});return
    if cmd=="ocean-buildx-tool-versions":
        d={}
        for x in a or ["git","python","gcc","clang","cmake","make","ninja","java"]:
            p=shutil.which(x)
            if p:
                try:d[x]=subprocess.check_output([p,"--version"],text=True,stderr=subprocess.STDOUT,timeout=4).splitlines()[0]
                except Exception:d[x]=p
        emit(d);return
    if cmd=="ocean-buildx-path-check":emit([{"path":x,"exists":P(x).exists(),"executable":os.access(x,os.X_OK)} for x in a]);return
    files=walkfiles(root)
    if cmd=="ocean-buildx-shebang-check":emit([{"path":str(x),"shebang":x.read_text(errors="replace").splitlines()[0]} for x in files if x.read_bytes()[:2]==b"#!"])
    elif cmd=="ocean-buildx-executable-check":emit([str(x) for x in files if os.access(x,os.X_OK)])
    elif cmd=="ocean-buildx-script-lint":
        bad=[]
        for x in files:
            if x.suffix==".py":
                r=subprocess.run([sys.executable,"-m","py_compile",str(x)],capture_output=True,text=True)
                if r.returncode:bad.append({"path":str(x),"error":r.stderr})
        emit({"valid":not bad,"errors":bad})
    elif cmd=="ocean-buildx-json-check":
        bad=[]
        for x in files:
            if x.suffix==".json":
                try:json.loads(x.read_text())
                except Exception as e:bad.append({"path":str(x),"error":str(e)})
        emit({"valid":not bad,"errors":bad})
    elif cmd=="ocean-buildx-xml-check":
        bad=[]
        for x in files:
            if x.suffix in (".xml",".svg"):
                try:ET.parse(x)
                except Exception as e:bad.append({"path":str(x),"error":str(e)})
        emit({"valid":not bad,"errors":bad})
    elif cmd=="ocean-buildx-python-compile":
        bad=[]
        for x in files:
            if x.suffix==".py":
                r=subprocess.run([sys.executable,"-m","py_compile",str(x)],capture_output=True,text=True)
                if r.returncode:bad.append(str(x))
        emit({"compiled":sum(x.suffix==".py" for x in files)-len(bad),"failed":bad})
    elif cmd=="ocean-buildx-python-imports":
        imports=set()
        for x in files:
            if x.suffix==".py":
                for l in x.read_text(errors="replace").splitlines():
                    m=re.match(r"\s*(?:from|import)\s+([A-Za-z_][\w.]*)",l)
                    if m:imports.add(m.group(1).split(".")[0])
        emit(sorted(imports))
    elif cmd=="ocean-buildx-c-includes":
        inc=set()
        for x in files:
            if x.suffix in (".c",".h",".cc",".cpp",".hpp"):
                inc.update(re.findall(r'(?m)^\s*#\s*include\s*[<"]([^>"]+)',x.read_text(errors="replace")))
        emit(sorted(inc))
    elif cmd=="ocean-buildx-make-targets":
        mf=root/"Makefile";s=mf.read_text(errors="replace");emit(re.findall(r"(?m)^([A-Za-z0-9_.-]+)\s*:(?!=)",s))
    elif cmd=="ocean-buildx-gradle-tasks-lite":
        vals=[]
        for x in files:
            if x.name.endswith((".gradle",".gradle.kts")):vals+=re.findall(r"\b(?:task|register)\s*\(?[\"']?([A-Za-z0-9_.-]+)",x.read_text(errors="replace"))
        emit(sorted(set(vals)))
    elif cmd=="ocean-buildx-package-json-scripts":
        p=root/"package.json";emit(json.loads(p.read_text()).get("scripts",{}))
    elif cmd=="ocean-buildx-lockfiles":emit([str(x) for x in files if x.name in {"package-lock.json","yarn.lock","pnpm-lock.yaml","Pipfile.lock","poetry.lock","Cargo.lock","gradle.lockfile"}])
    elif cmd=="ocean-buildx-source-count":emit(Counter(x.suffix.lower() or "<none>" for x in files))
    elif cmd=="ocean-buildx-todo-scan":
        hits=[]
        for x in files:
            try:
                for n,l in enumerate(x.read_text(errors="replace").splitlines(),1):
                    if re.search(r"\b(TODO|FIXME|XXX)\b",l):hits.append({"path":str(x),"line":n,"text":l.strip()[:300]})
            except:pass
        emit(hits[:5000])
    elif cmd=="ocean-buildx-binary-detect":
        emit([str(x) for x in files if b"\0" in x.read_bytes()[:4096]])
    elif cmd=="ocean-buildx-line-endings":
        d=Counter()
        for x in files:
            b=x.read_bytes()[:1024*1024]
            d["crlf" if b"\r\n" in b else "lf" if b"\n" in b else "none"]+=1
        emit(d)
    elif cmd=="ocean-buildx-repro-hash":
        h=hashlib.sha256()
        for x in sorted(files,key=lambda p:str(p.relative_to(root))):
            h.update(str(x.relative_to(root)).encode()+b"\0"+bytes.fromhex(filehash(x)))
        print(h.hexdigest())
def archive_entries(path):
    p=P(path)
    if zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as z:return [{"name":i.filename,"size":i.file_size,"compressed":i.compress_size} for i in z.infolist()]
    with tarfile.open(p,"r:*") as t:return [{"name":i.name,"size":i.size,"compressed":None} for i in t.getmembers() if i.isfile()]
def handle_archive(cmd,a):
    if not a:die("archive path required")
    p=P(a[0])
    if cmd.startswith("ocean-archivex-zip-"):
        with zipfile.ZipFile(p) as z:
            infos=z.infolist()
            if cmd=="ocean-archivex-zip-list":emit([i.filename for i in infos])
            elif cmd=="ocean-archivex-zip-test":emit({"valid":z.testzip() is None,"bad":z.testzip()})
            elif cmd=="ocean-archivex-zip-extract-one":
                if len(a)<3:die("ZIP ENTRY OUTPUT_DIR");i=z.getinfo(a[1]);dst=safe_join(a[2],i.filename);dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(z.read(i));emit({"path":str(dst)})
            elif cmd=="ocean-archivex-zip-top":emit(sorted([{"name":i.filename,"bytes":i.file_size} for i in infos],key=lambda x:x["bytes"],reverse=True)[:20])
            elif cmd=="ocean-archivex-zip-ratio":
                raw=sum(i.file_size for i in infos);comp=sum(i.compress_size for i in infos);emit({"raw":raw,"compressed":comp,"ratio":comp/raw if raw else 0})
        return
    if cmd.startswith("ocean-archivex-tar-"):
        with tarfile.open(p,"r:*") as t:
            mem=t.getmembers()
            if cmd=="ocean-archivex-tar-list":emit([i.name for i in mem])
            elif cmd=="ocean-archivex-tar-test":
                for i in mem:
                    if i.isfile():
                        f=t.extractfile(i)
                        if f:
                            while f.read(1024*1024):pass
                emit({"valid":True,"members":len(mem)})
            elif cmd=="ocean-archivex-tar-extract-one":
                if len(a)<3:die("TAR ENTRY OUTPUT_DIR");i=t.getmember(a[1]);dst=safe_join(a[2],i.name);dst.parent.mkdir(parents=True,exist_ok=True);f=t.extractfile(i);dst.write_bytes(f.read() if f else b"");emit({"path":str(dst)})
        return
    if cmd=="ocean-archivex-gzip-info":
        with gzip.open(p,"rb") as f:data=f.read()
        emit({"compressed_bytes":p.stat().st_size,"raw_bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()});return
    if cmd in ("ocean-archivex-gzip-test","ocean-archivex-bz2-test","ocean-archivex-xz-test"):
        op=gzip.open if "gzip" in cmd else bz2.open if "bz2" in cmd else lzma.open
        try:
            with op(p,"rb") as f:
                while f.read(1024*1024):pass
            emit({"valid":True})
        except Exception as e:emit({"valid":False,"error":str(e)})
        return
    if cmd=="ocean-archivex-gzip-decompress":
        out=P(a[1] if len(a)>1 else p.with_suffix(""));out.write_bytes(gzip.open(p,"rb").read());emit({"path":str(out),"bytes":out.stat().st_size});return
    entries=archive_entries(p)
    if cmd=="ocean-archivex-file-count":print(len(entries))
    elif cmd=="ocean-archivex-largest-entry":emit(max(entries,key=lambda x:x["size"]) if entries else {})
    elif cmd=="ocean-archivex-extension-stats":emit(Counter(P(x["name"]).suffix.lower() or "<none>" for x in entries))
    elif cmd=="ocean-archivex-manifest-hash":
        h=hashlib.sha256()
        for x in sorted(entries,key=lambda q:q["name"]):h.update((x["name"]+"\0"+str(x["size"])+"\n").encode())
        print(h.hexdigest())
    elif cmd=="ocean-archivex-path-search":
        q=a[1].lower() if len(a)>1 else "";emit([x["name"] for x in entries if q in x["name"].lower()])
    elif cmd=="ocean-archivex-safe-check":
        bad=[]
        for x in entries:
            q=P(x["name"])
            if q.is_absolute() or ".." in q.parts:bad.append(x["name"])
        emit({"safe":not bad,"unsafe":bad})
def main():
    cmd=P(sys.argv[0]).name;a=sys.argv[1:]
    if cmd not in COMMANDS:
        if a and a[0] in COMMANDS:cmd=a.pop(0)
        elif not a or a[0] in ("-h","--help"):
            print("Ocean DevKit: 200 package suite");print("\n".join(COMMANDS));return
        else:die("unknown command")
    if cmd=="ocean-devkit-runtime":
        emit({"suite":"ocean-devkit","version":VERSION,"commands":200,"groups":{"apk":len(APK),"web":len(WEB),"git":len(GIT),"text":len(TEXT),"data":len(DATA),"fs":len(FS),"net":len(NET),"crypto":len(CRYPTO),"build":len(BUILD),"archive":len(ARCHIVE)}});return
    if cmd in APK:handle_apk(cmd,a)
    elif cmd in WEB:handle_web(cmd,a)
    elif cmd in GIT:handle_git(cmd,a)
    elif cmd in TEXT:handle_text(cmd,a)
    elif cmd in DATA:handle_data(cmd,a)
    elif cmd in FS:handle_fs(cmd,a)
    elif cmd in NET:handle_net(cmd,a)
    elif cmd in CRYPTO:handle_crypto(cmd,a)
    elif cmd in BUILD:handle_build(cmd,a)
    elif cmd in ARCHIVE:handle_archive(cmd,a)
if __name__=="__main__":main()
