#!/usr/bin/env python3
from __future__ import annotations
import base64,binascii,csv,email,email.header,email.policy,hashlib,io,json,mailbox,math,os,re,shlex,statistics,struct,sys,time,urllib.parse,uuid,xml.etree.ElementTree as ET,zipfile,zlib,tomllib
from email import policy
from email.parser import BytesParser
from pathlib import Path
from collections import Counter
P=Path

OFFICE=["entries","content-types","docx-text","docx-links","docx-images","xlsx-sheets","xlsx-shared-strings","xlsx-formulas","xlsx-dimensions","pptx-slides","pptx-text","pptx-images","epub-metadata","epub-manifest","epub-spine","odf-mimetype","odf-content-stats","media-list","largest-parts","integrity"]
PDF=["header","version","eof-check","object-count","stream-count","page-count","metadata-strings","font-hints","image-hints","xref-offsets","trailer","linearized","encrypted","attachment-hints","uri-links","producer","creator","title","sha256","entropy"]
MAIL=["headers","subject","from","to","cc","date","message-id","attachments","mime-parts","text-body","html-body","domains","addresses","received-hops","content-types","attachment-names","decode-header","canonicalize","mbox-count","eml-hash"]
CAL=["ics-events","ics-todos","ics-timezones","ics-dtstart","ics-dtend","ics-duration","ics-attendees","ics-organizers","ics-locations","ics-summaries","ics-uids","ics-rrules","ics-alarms","ics-freebusy","vcard-names","vcard-emails","vcard-phones","vcard-orgs","vcard-addresses","vcard-properties"]
TOKEN=["jwt-header","jwt-payload","jwt-claims","jwt-exp","jwt-nbf","jwt-iat","jwt-aud","jwt-iss","jwt-sub","jwt-jti","jwt-scopes","jwt-alg","jwt-kid","jwt-type","jwt-expired","jwt-ttl","base64url-split","compact-parts","fingerprint","redact"]
PROJECT=["npm-name","npm-version","npm-deps","npm-devdeps","npm-scripts","npm-engines","cargo-package","cargo-deps","cargo-features","pyproject-project","pyproject-deps","pyproject-scripts","requirements-packages","gradle-plugins","gradle-deps","pom-gav","pom-deps","android-package","android-permissions","project-detect"]
SOURCE=["detect-language","lines-total","lines-blank","lines-comment","lines-code","longest-line","trailing-space","tab-lines","nonascii-lines","todo-lines","python-functions","python-classes","js-imports","js-requires","go-imports","rust-uses","java-package","java-imports","kotlin-imports","symbols-lite"]
BINARY=["u16le","u16be","u32le","u32be","u64le","u64be","varint-encode","varint-decode","zigzag-encode","zigzag-decode","crc32","adler32","entropy","magic","hexdump","xor","bitcount","swap32","slice","concat"]
STRING=["env-subst","map-subst","mustache-lite","repeat","pad-left","pad-right","center","truncate","ellipsis","camel","snake","kebab","pascal","initials","plural-simple","singular-simple","normalize-space","template-lines","join-nonempty","placeholders"]
BUNDLE=["aab-entries","aab-modules","aab-manifests","aab-dex","aab-native-abis","aab-native-libs","aab-assets","aab-resources","aab-bundle-config","aab-largest","apks-entries","apks-split-apks","apks-split-names","apks-total-size","apks-native-abis","apks-dex-count","apks-assets","bundle-sha256","bundle-integrity","bundle-search"]
GROUPS={"office":OFFICE,"pdf":PDF,"mail":MAIL,"cal":CAL,"token":TOKEN,"project":PROJECT,"source":SOURCE,"binary":BINARY,"string":STRING,"bundle":BUNDLE}
COMMANDS=[f"ocean-lab-{g}-{op}" for g,ops in GROUPS.items() for op in ops]
assert len(COMMANDS)==200 and len(set(COMMANDS))==200

def emit(x):
    if isinstance(x,(dict,list,tuple,Counter)): print(json.dumps(x,indent=2,ensure_ascii=False,default=str))
    else: print(x)

def die(msg,code=2):
    print(msg,file=sys.stderr); raise SystemExit(code)

def read_bytes_arg(a):
    if not a: return sys.stdin.buffer.read()
    p=P(a[0])
    return p.read_bytes() if p.exists() and p.is_file() else " ".join(a).encode()

def read_text_arg(a):
    if not a: return sys.stdin.read()
    p=P(a[0])
    return p.read_text(errors="replace") if p.exists() and p.is_file() else " ".join(a)

def cmd_parts(cmd):
    m=re.match(r"ocean-lab-([^-]+)-(.+)",cmd)
    if not m: die("bad command")
    return m.group(1),m.group(2)

def xml_texts(root,tag_suffix):
    return [x.text or "" for x in root.iter() if x.tag.endswith(tag_suffix)]

def zip_names(path):
    with zipfile.ZipFile(path) as z: return z.namelist()

def office(cmd,a):
    if not a: die("office/document path required")
    op=cmd_parts(cmd)[1]; path=P(a[0])
    with zipfile.ZipFile(path) as z:
        names=z.namelist(); infos=z.infolist()
        if op=="entries": emit(names); return
        if op=="content-types":
            if "[Content_Types].xml" not in names: emit([]); return
            r=ET.fromstring(z.read("[Content_Types].xml")); emit([x.attrib for x in r]); return
        if op=="docx-text":
            n="word/document.xml"; 
            if n not in names: print(""); return
            r=ET.fromstring(z.read(n)); print("\n".join(x.text or "" for x in r.iter() if x.tag.endswith("}t"))); return
        if op=="docx-links":
            out=[]
            for n in names:
                if n.startswith("word/_rels/") and n.endswith(".rels"):
                    try:
                        r=ET.fromstring(z.read(n))
                        out += [x.attrib.get("Target","") for x in r if x.attrib.get("TargetMode")=="External"]
                    except: pass
            emit(out); return
        if op=="docx-images": emit([n for n in names if n.startswith("word/media/")]); return
        if op=="xlsx-sheets":
            n="xl/workbook.xml"
            if n not in names: emit([]); return
            r=ET.fromstring(z.read(n)); emit([x.attrib.get("name") for x in r.iter() if x.tag.endswith("}sheet")]); return
        if op=="xlsx-shared-strings":
            n="xl/sharedStrings.xml"
            if n not in names: emit([]); return
            r=ET.fromstring(z.read(n)); emit(["".join(x.itertext()) for x in r if x.tag.endswith("}si")]); return
        if op=="xlsx-formulas":
            out=[]
            for n in names:
                if re.fullmatch(r"xl/worksheets/sheet\d+\.xml",n):
                    try:
                        r=ET.fromstring(z.read(n))
                        out += [x.text or "" for x in r.iter() if x.tag.endswith("}f")]
                    except: pass
            emit(out); return
        if op=="xlsx-dimensions":
            out={}
            for n in names:
                if re.fullmatch(r"xl/worksheets/sheet\d+\.xml",n):
                    try:
                        r=ET.fromstring(z.read(n)); d=next((x.attrib.get("ref") for x in r.iter() if x.tag.endswith("}dimension")),None); out[n]=d
                    except: pass
            emit(out); return
        if op=="pptx-slides": emit(sorted([n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml",n)])); return
        if op=="pptx-text":
            out=[]
            for n in names:
                if re.fullmatch(r"ppt/slides/slide\d+\.xml",n):
                    try:
                        r=ET.fromstring(z.read(n)); out += [x.text or "" for x in r.iter() if x.tag.endswith("}t")]
                    except: pass
            print("\n".join(out)); return
        if op=="pptx-images": emit([n for n in names if n.startswith("ppt/media/")]); return
        if op=="epub-metadata":
            out={}
            for n in names:
                if n.lower().endswith(".opf"):
                    try:
                        r=ET.fromstring(z.read(n))
                        for k in ("title","creator","language","identifier","publisher","date"):
                            vals=[x.text for x in r.iter() if x.tag.endswith("}"+k) and x.text]
                            if vals: out[k]=vals
                    except: pass
            emit(out); return
        if op=="epub-manifest":
            out=[]
            for n in names:
                if n.lower().endswith(".opf"):
                    try:
                        r=ET.fromstring(z.read(n)); out += [x.attrib for x in r.iter() if x.tag.endswith("}item")]
                    except: pass
            emit(out); return
        if op=="epub-spine":
            out=[]
            for n in names:
                if n.lower().endswith(".opf"):
                    try:
                        r=ET.fromstring(z.read(n)); out += [x.attrib.get("idref") for x in r.iter() if x.tag.endswith("}itemref")]
                    except: pass
            emit(out); return
        if op=="odf-mimetype":
            print(z.read("mimetype").decode(errors="replace") if "mimetype" in names else ""); return
        if op=="odf-content-stats":
            n="content.xml"
            if n not in names: emit({"elements":0,"text_chars":0}); return
            r=ET.fromstring(z.read(n)); emit({"elements":sum(1 for _ in r.iter()),"text_chars":sum(len(x or "") for x in r.itertext())}); return
        if op=="media-list": emit([n for n in names if re.search(r"\.(png|jpe?g|gif|svg|webp|mp3|mp4|wav|ogg)$",n,re.I)]); return
        if op=="largest-parts": emit(sorted([{"name":i.filename,"bytes":i.file_size} for i in infos],key=lambda x:x["bytes"],reverse=True)[:20]); return
        if op=="integrity": emit({"valid":z.testzip() is None,"bad_entry":z.testzip(),"entries":len(infos)}); return

def pdf(cmd,a):
    if not a: die("PDF path required")
    op=cmd_parts(cmd)[1]; b=P(a[0]).read_bytes(); s=b.decode("latin1",errors="replace")
    if op=="header": emit({"header":b[:16].decode("latin1",errors="replace")}); return
    if op=="version":
        m=re.match(br"%PDF-([0-9.]+)",b); print(m.group(1).decode() if m else "unknown"); return
    if op=="eof-check": emit({"has_eof":b.rstrip().endswith(b"%%EOF")}); return
    if op=="object-count": print(len(re.findall(rb"\n?\d+\s+\d+\s+obj\b",b))); return
    if op=="stream-count": print(len(re.findall(rb"\bstream\r?\n",b))); return
    if op=="page-count": print(len(re.findall(rb"/Type\s*/Page\b",b))); return
    if op=="metadata-strings":
        vals={}
        for k in ("Title","Author","Subject","Keywords","Creator","Producer","CreationDate","ModDate"):
            m=re.search(r"/"+k+r"\s*\((.*?)\)",s,re.S)
            if m: vals[k]=m.group(1)[:2000]
        emit(vals); return
    if op=="font-hints": emit(sorted(set(re.findall(r"/BaseFont\s*/([^\s/<>\[\]()]+)",s)))); return
    if op=="image-hints": print(len(re.findall(r"/Subtype\s*/Image\b",s))); return
    if op=="xref-offsets": emit([int(x) for x in re.findall(r"startxref\s+(\d+)",s)]); return
    if op=="trailer":
        m=re.findall(r"trailer\s*<<(.*?)>>",s,re.S); print(m[-1][:4000] if m else ""); return
    if op=="linearized": print(str("/Linearized" in s).lower()); return
    if op=="encrypted": print(str("/Encrypt" in s).lower()); return
    if op=="attachment-hints": emit(sorted(set(re.findall(r"/F\s*\(([^)]{1,500})\)",s)))); return
    if op=="uri-links": emit(re.findall(r"/URI\s*\(([^)]{1,2000})\)",s)); return
    for key in ("producer","creator","title"):
        if op==key:
            m=re.search(r"/"+key.capitalize()+r"\s*\((.*?)\)",s,re.S); print(m.group(1)[:2000] if m else ""); return
    if op=="sha256": print(hashlib.sha256(b).hexdigest()); return
    if op=="entropy":
        if not b: print("0.0"); return
        c=Counter(b); e=-sum((n/len(b))*math.log2(n/len(b)) for n in c.values()); print(f"{e:.6f}"); return

def parse_mail(path):
    return BytesParser(policy=policy.default).parse(P(path).open("rb"))

def decode_header_value(v):
    if not v:return ""
    return str(email.header.make_header(email.header.decode_header(v)))

def mail(cmd,a):
    op=cmd_parts(cmd)[1]
    if op=="mbox-count":
        if not a:die("mbox path required")
        print(sum(1 for _ in mailbox.mbox(a[0]))); return
    if not a: die("EML path required")
    p=P(a[0]); m=parse_mail(p)
    if op=="headers": emit({k:decode_header_value(v) for k,v in m.items()}); return
    hmap={"subject":"Subject","from":"From","to":"To","cc":"Cc","date":"Date","message-id":"Message-ID"}
    if op in hmap: print(decode_header_value(m.get(hmap[op],""))); return
    parts=list(m.walk())
    if op=="attachments":
        emit([{"filename":x.get_filename(),"content_type":x.get_content_type(),"bytes":len(x.get_payload(decode=True) or b"")} for x in parts if x.get_content_disposition()=="attachment"]); return
    if op=="mime-parts": emit([{"content_type":x.get_content_type(),"disposition":x.get_content_disposition(),"filename":x.get_filename()} for x in parts]); return
    if op in ("text-body","html-body"):
        want="text/plain" if op=="text-body" else "text/html"; out=[]
        for x in parts:
            if x.get_content_type()==want and x.get_content_disposition()!="attachment":
                try: out.append(x.get_content())
                except: out.append((x.get_payload(decode=True) or b"").decode(errors="replace"))
        print("\n".join(out)); return
    if op=="domains":
        header_text="\n".join(str(m.get(k,"")) for k in ("From","To","Cc","Reply-To"))
        domains=sorted({x.lower().rstrip(".") for x in re.findall(r"@([A-Za-z0-9.-]+\.[A-Za-z]{2,})",header_text)})
        emit(domains); return
    if op=="addresses": emit([addr for _,addr in email.utils.getaddresses([m.get(k,"") for k in ("From","To","Cc","Reply-To")]) if addr]); return
    if op=="received-hops": emit(m.get_all("Received",[])); return
    if op=="content-types": emit([x.get_content_type() for x in parts]); return
    if op=="attachment-names": emit([x.get_filename() for x in parts if x.get_filename()]); return
    if op=="decode-header": print(decode_header_value(" ".join(a[1:]) if len(a)>1 else m.get("Subject",""))); return
    if op=="canonicalize": sys.stdout.buffer.write(m.as_bytes(policy=policy.SMTP)); return
    if op=="eml-hash": print(hashlib.sha256(p.read_bytes()).hexdigest()); return

def unfold_ical(s):
    return re.sub(r"\r?\n[ \t]","",s)

def parse_props(s):
    out=[]
    for line in unfold_ical(s).splitlines():
        if ":" in line:
            left,val=line.split(":",1); name=left.split(";",1)[0].upper(); out.append((name,val,left))
    return out

def blocks(s,name):
    pat=re.compile(rf"BEGIN:{name}\r?\n(.*?)\r?\nEND:{name}",re.S|re.I)
    return pat.findall(unfold_ical(s))

def cal(cmd,a):
    if not a:die("ICS/vCard path required")
    op=cmd_parts(cmd)[1]; s=P(a[0]).read_text(errors="replace")
    if op.startswith("ics-"):
        if op=="ics-events": emit(blocks(s,"VEVENT")); return
        if op=="ics-todos": emit(blocks(s,"VTODO")); return
        if op=="ics-timezones": emit(blocks(s,"VTIMEZONE")); return
        if op=="ics-alarms": emit(blocks(s,"VALARM")); return
        key={"ics-dtstart":"DTSTART","ics-dtend":"DTEND","ics-duration":"DURATION","ics-attendees":"ATTENDEE","ics-organizers":"ORGANIZER","ics-locations":"LOCATION","ics-summaries":"SUMMARY","ics-uids":"UID","ics-rrules":"RRULE","ics-freebusy":"FREEBUSY"}.get(op)
        if key: emit([v for n,v,_ in parse_props(s) if n==key]); return
    key={"vcard-names":"FN","vcard-emails":"EMAIL","vcard-phones":"TEL","vcard-orgs":"ORG","vcard-addresses":"ADR"}.get(op)
    if key: emit([v for n,v,_ in parse_props(s) if n==key]); return
    if op=="vcard-properties": emit([{"name":n,"value":v,"raw_key":k} for n,v,k in parse_props(s)]); return

def b64u_decode(s):
    return base64.urlsafe_b64decode(s+"="*((4-len(s)%4)%4))

def jwt_parts(tok):
    p=tok.strip().split(".")
    if len(p)<2:die("JWT/JWS compact token requires at least 2 parts")
    def dec(x):
        try:return json.loads(b64u_decode(x))
        except:return {}
    return p,dec(p[0]),dec(p[1])

def token(cmd,a):
    if not a:die("token required")
    op=cmd_parts(cmd)[1]; tok=a[0] if not P(a[0]).exists() else P(a[0]).read_text().strip(); parts,h,p=jwt_parts(tok)
    if op=="jwt-header": emit(h); return
    if op=="jwt-payload" or op=="jwt-claims": emit(p); return
    cmap={"jwt-exp":"exp","jwt-nbf":"nbf","jwt-iat":"iat","jwt-aud":"aud","jwt-iss":"iss","jwt-sub":"sub","jwt-jti":"jti","jwt-scopes":"scope"}
    if op in cmap: emit(p.get(cmap[op])); return
    if op=="jwt-alg": emit(h.get("alg")); return
    if op=="jwt-kid": emit(h.get("kid")); return
    if op=="jwt-type": emit(h.get("typ")); return
    now=int(time.time())
    if op=="jwt-expired": print(str(isinstance(p.get("exp"),(int,float)) and p["exp"]<now).lower()); return
    if op=="jwt-ttl": emit(None if not isinstance(p.get("exp"),(int,float)) else int(p["exp"]-now)); return
    if op=="base64url-split": emit(parts); return
    if op=="compact-parts": emit({"parts":len(parts),"header_bytes":len(b64u_decode(parts[0])),"payload_bytes":len(b64u_decode(parts[1])),"signature_bytes":len(b64u_decode(parts[2])) if len(parts)>2 and parts[2] else 0}); return
    if op=="fingerprint": print(hashlib.sha256(tok.encode()).hexdigest()); return
    if op=="redact": print(parts[0]+"."+parts[1]+".<redacted>"); return

def reqs(path):
    out=[]
    for line in P(path).read_text(errors="replace").splitlines():
        line=line.strip()
        if not line or line.startswith("#") or line.startswith("-"):continue
        out.append(re.split(r"[<>=!~;\[]",line,1)[0].strip())
    return out

def parse_gradle(s):
    plugins=sorted(set(re.findall(r"\bid\s+['\"]([^'\"]+)['\"]|id\(['\"]([^'\"]+)['\"]\)",s)))
    plugins=[a or b for a,b in plugins]
    deps=re.findall(r"\b(?:implementation|api|compileOnly|runtimeOnly|testImplementation)\s*\(?\s*['\"]([^'\"]+)['\"]",s)
    return plugins,deps

def project(cmd,a):
    op=cmd_parts(cmd)[1]; root=P(a[0] if a else ".")
    if op.startswith("npm-"):
        p=root if root.name=="package.json" else root/"package.json"; d=json.loads(p.read_text())
        key={"npm-name":"name","npm-version":"version","npm-deps":"dependencies","npm-devdeps":"devDependencies","npm-scripts":"scripts","npm-engines":"engines"}[op]; emit(d.get(key,{} if key not in ("name","version") else None)); return
    if op.startswith("cargo-"):
        p=root if root.name=="Cargo.toml" else root/"Cargo.toml"; d=tomllib.loads(p.read_text())
        if op=="cargo-package":emit(d.get("package",{}))
        elif op=="cargo-deps":emit(d.get("dependencies",{}))
        else:emit(d.get("features",{}))
        return
    if op.startswith("pyproject-"):
        p=root if root.name=="pyproject.toml" else root/"pyproject.toml"; d=tomllib.loads(p.read_text()); pr=d.get("project",{})
        if op=="pyproject-project":emit(pr)
        elif op=="pyproject-deps":emit(pr.get("dependencies",[]))
        else:emit(pr.get("scripts",{}))
        return
    if op=="requirements-packages":
        p=root if root.is_file() else root/"requirements.txt"; emit(reqs(p)); return
    if op in ("gradle-plugins","gradle-deps"):
        candidates=[root] if root.is_file() else [root/"build.gradle",root/"build.gradle.kts"]
        p=next((x for x in candidates if x.exists()),None)
        if not p:die("build.gradle(.kts) not found")
        plugins,deps=parse_gradle(p.read_text(errors="replace")); emit(plugins if op=="gradle-plugins" else deps); return
    if op in ("pom-gav","pom-deps"):
        p=root if root.name=="pom.xml" else root/"pom.xml"; r=ET.parse(p).getroot()
        def first(name):
            return next((x.text for x in r if x.tag.endswith("}"+name) or x.tag==name),None)
        if op=="pom-gav": emit({"groupId":first("groupId"),"artifactId":first("artifactId"),"version":first("version")})
        else:
            deps=[]
            for d in r.iter():
                if d.tag.endswith("}dependency") or d.tag=="dependency":
                    q={}
                    for x in d:q[x.tag.split("}")[-1]]=x.text
                    deps.append(q)
            emit(deps)
        return
    if op in ("android-package","android-permissions"):
        p=root if root.name=="AndroidManifest.xml" else root/"AndroidManifest.xml"; r=ET.parse(p).getroot()
        if op=="android-package": print(r.attrib.get("package",""))
        else:
            ns="{http://schemas.android.com/apk/res/android}"; emit([x.attrib.get(ns+"name") for x in r if x.tag.endswith("uses-permission")])
        return
    if op=="project-detect":
        markers={"npm":"package.json","cargo":"Cargo.toml","python":"pyproject.toml","requirements":"requirements.txt","gradle":"build.gradle","gradle-kts":"build.gradle.kts","maven":"pom.xml","android":"AndroidManifest.xml"}
        emit([k for k,v in markers.items() if (root/v).exists()]); return

def source(cmd,a):
    if not a:die("source path required")
    op=cmd_parts(cmd)[1]; p=P(a[0]); s=p.read_text(errors="replace"); lines=s.splitlines()
    ext=p.suffix.lower(); lang={".py":"python",".js":"javascript",".mjs":"javascript",".ts":"typescript",".go":"go",".rs":"rust",".java":"java",".kt":"kotlin",".kts":"kotlin",".c":"c",".h":"c",".cpp":"cpp",".cc":"cpp",".sh":"shell",".rb":"ruby",".php":"php"}.get(ext,"unknown")
    if op=="detect-language":print(lang);return
    if op=="lines-total":print(len(lines));return
    if op=="lines-blank":print(sum(not x.strip() for x in lines));return
    if op=="lines-comment":
        print(sum(x.lstrip().startswith(("#","//","/*","*")) for x in lines));return
    if op=="lines-code":
        print(sum(bool(x.strip()) and not x.lstrip().startswith(("#","//","/*","*")) for x in lines));return
    if op=="longest-line": emit(max(({"line":i+1,"length":len(x),"text":x} for i,x in enumerate(lines)),key=lambda q:q["length"],default={}));return
    if op=="trailing-space":emit([i+1 for i,x in enumerate(lines) if x.rstrip()!=x]);return
    if op=="tab-lines":emit([i+1 for i,x in enumerate(lines) if "\t" in x]);return
    if op=="nonascii-lines":emit([i+1 for i,x in enumerate(lines) if any(ord(c)>127 for c in x)]);return
    if op=="todo-lines":emit([{"line":i+1,"text":x.strip()} for i,x in enumerate(lines) if re.search(r"\b(TODO|FIXME|XXX)\b",x)]);return
    patterns={
      "python-functions":r"(?m)^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)",
      "python-classes":r"(?m)^\s*class\s+([A-Za-z_]\w*)",
      "js-imports":r"""(?m)^\s*import(?:.+?from\s+)?['"]([^'"]+)['"]""",
      "js-requires":r"""require\(\s*['"]([^'"]+)['"]\s*\)""",
      "go-imports":r"""(?m)^\s*import\s+(?:\w+\s+)?["]([^"]+)["]""",
      "rust-uses":r"(?m)^\s*use\s+([^;]+);",
      "java-package":r"(?m)^\s*package\s+([\w.]+)\s*;",
      "java-imports":r"(?m)^\s*import\s+([\w.*]+)\s*;",
      "kotlin-imports":r"(?m)^\s*import\s+([\w.*]+)",
    }
    if op in patterns: emit(re.findall(patterns[op],s));return
    if op=="symbols-lite":
        pats=[r"(?m)^\s*(?:def|class|function|func|fn|interface|enum|struct)\s+([A-Za-z_]\w*)",r"(?m)^\s*(?:public|private|protected|internal)?\s*(?:static\s+)?(?:fun|void|int|long|double|float|String|boolean)\s+([A-Za-z_]\w*)\s*\("]
        emit(sorted(set(sum((re.findall(x,s) for x in pats),[]))));return

def parse_int(s): return int(s,0)

def varint_encode(n):
    out=bytearray()
    while True:
        b=n&0x7f;n>>=7
        out.append(b|(0x80 if n else 0))
        if not n:return bytes(out)

def varint_decode(b):
    n=0;shift=0
    for x in b:
        n|=(x&0x7f)<<shift
        if not x&0x80:return n
        shift+=7
        if shift>63:die("varint too large")
    die("truncated varint")

def entropy(b):
    if not b:return 0.0
    c=Counter(b);return -sum((n/len(b))*math.log2(n/len(b)) for n in c.values())

def binary(cmd,a):
    op=cmd_parts(cmd)[1]
    if op in ("varint-encode","zigzag-encode"):
        if not a:die("integer required")
        n=parse_int(a[0])
        if op=="zigzag-encode":print((n<<1)^(n>>63));return
        print(varint_encode(n).hex());return
    if op in ("varint-decode","zigzag-decode"):
        if not a:die("input required")
        if op=="zigzag-decode":
            n=parse_int(a[0]);print((n>>1)^-(n&1));return
        b=bytes.fromhex(a[0]);print(varint_decode(b));return
    b=read_bytes_arg(a)
    if op in ("u16le","u16be","u32le","u32be","u64le","u64be"):
        size=int(op[1:3])//8; endian="<" if op.endswith("le") else ">"; code={2:"H",4:"I",8:"Q"}[size]
        if len(b)<size:die("not enough bytes")
        print(struct.unpack(endian+code,b[:size])[0]);return
    if op=="crc32":print(f"{zlib.crc32(b)&0xffffffff:08x}");return
    if op=="adler32":print(f"{zlib.adler32(b)&0xffffffff:08x}");return
    if op=="entropy":print(f"{entropy(b):.6f}");return
    if op=="magic":print(b[:int(a[1]) if len(a)>1 and P(a[0]).exists() else 16].hex());return
    if op=="hexdump":
        width=16
        for off in range(0,len(b),width):
            q=b[off:off+width]; print(f"{off:08x}  {' '.join(f'{x:02x}' for x in q):47}  {''.join(chr(x) if 32<=x<127 else '.' for x in q)}")
        return
    if op=="xor":
        if len(a)<2:die("FILE/TEXT KEYHEX")
        key=bytes.fromhex(a[-1]); src=b if P(a[0]).exists() else " ".join(a[:-1]).encode(); sys.stdout.buffer.write(bytes(x^key[i%len(key)] for i,x in enumerate(src)));return
    if op=="bitcount":print(sum(x.bit_count() for x in b));return
    if op=="swap32":
        if len(b)<4:die("need 4 bytes")
        print(b[:4][::-1].hex());return
    if op=="slice":
        start=int(a[1]) if len(a)>1 and P(a[0]).exists() else 0; end=int(a[2]) if len(a)>2 and P(a[0]).exists() else len(b);sys.stdout.buffer.write(b[start:end]);return
    if op=="concat":
        out=b"".join(P(x).read_bytes() if P(x).exists() else x.encode() for x in a);sys.stdout.buffer.write(out);return

def words(s):
    return [x for x in re.split(r"[^A-Za-z0-9]+",s) if x]

def snake(s): return "_".join(x.lower() for x in words(s))
def kebab(s): return "-".join(x.lower() for x in words(s))
def camel(s):
    w=words(s);return (w[0].lower()+"".join(x[:1].upper()+x[1:].lower() for x in w[1:])) if w else ""
def pascal(s): return "".join(x[:1].upper()+x[1:].lower() for x in words(s))

def string(cmd,a):
    op=cmd_parts(cmd)[1]
    if op=="map-subst":
        if len(a)<2:die("TEMPLATE JSON_MAP")
        s=a[0]; d=json.loads(P(a[1]).read_text() if P(a[1]).exists() else a[1]); print(re.sub(r"\$\{([^}]+)\}",lambda m:str(d.get(m.group(1),m.group(0))),s));return
    if op=="mustache-lite":
        if len(a)<2:die("TEMPLATE JSON_MAP")
        s=a[0];d=json.loads(P(a[1]).read_text() if P(a[1]).exists() else a[1]);print(re.sub(r"\{\{\s*([^}\s]+)\s*\}\}",lambda m:str(d.get(m.group(1),m.group(0))),s));return
    s=read_text_arg(a[:1] if a and P(a[0]).exists() else a)
    if op=="env-subst":print(os.path.expandvars(s));return
    if op=="repeat":print(s*int(a[1] if a and P(a[0]).exists() and len(a)>1 else 2),end="");return
    if op in ("pad-left","pad-right","center"):
        width=int(a[1] if a and P(a[0]).exists() and len(a)>1 else 20);fn={"pad-left":str.rjust,"pad-right":str.ljust,"center":str.center}[op];print(fn(s,width));return
    if op=="truncate":
        n=int(a[1] if a and P(a[0]).exists() and len(a)>1 else 80);print(s[:n]);return
    if op=="ellipsis":
        n=int(a[1] if a and P(a[0]).exists() and len(a)>1 else 80);print(s if len(s)<=n else s[:max(0,n-1)]+"…");return
    if op=="camel":print(camel(s));return
    if op=="snake":print(snake(s));return
    if op=="kebab":print(kebab(s));return
    if op=="pascal":print(pascal(s));return
    if op=="initials":print("".join(x[0].upper() for x in words(s)));return
    if op=="plural-simple":
        q=s.strip();print(q+"es" if q.endswith(("s","x","z","ch","sh")) else q[:-1]+"ies" if q.endswith("y") and len(q)>1 and q[-2].lower() not in "aeiou" else q+"s");return
    if op=="singular-simple":
        q=s.strip();print(q[:-3]+"y" if q.endswith("ies") else q[:-2] if q.endswith("es") else q[:-1] if q.endswith("s") else q);return
    if op=="normalize-space":print(" ".join(s.split()));return
    if op=="template-lines":
        prefix=a[1] if a and P(a[0]).exists() and len(a)>1 else "{n}: ";print("\n".join(prefix.replace("{n}",str(i+1)).replace("{line}",line)+("" if "{line}" in prefix else line) for i,line in enumerate(s.splitlines())));return
    if op=="join-nonempty":print((a[-1] if len(a)>1 else " ").join(x for x in s.splitlines() if x.strip()));return
    if op=="placeholders":emit(sorted(set(re.findall(r"\$\{([^}]+)\}|\{\{\s*([^}\s]+)\s*\}\}",s))));return

def bundle(cmd,a):
    if not a:die("AAB/APKS path required")
    op=cmd_parts(cmd)[1];p=P(a[0])
    if op=="bundle-sha256":print(hashlib.sha256(p.read_bytes()).hexdigest());return
    with zipfile.ZipFile(p) as z:
        names=z.namelist();infos=z.infolist()
        if op in ("aab-entries","apks-entries"):emit(names);return
        if op=="aab-modules":emit(sorted({n.split("/",1)[0] for n in names if "/" in n and not n.startswith("META-INF/")}));return
        if op=="aab-manifests":emit([n for n in names if n.endswith("/manifest/AndroidManifest.xml")]);return
        if op=="aab-dex":emit([n for n in names if "/dex/" in n and n.endswith(".dex")]);return
        if op=="aab-native-abis":emit(sorted({n.split("/lib/",1)[1].split("/",1)[0] for n in names if "/lib/" in n and n.endswith(".so")}));return
        if op=="aab-native-libs":emit([n for n in names if "/lib/" in n and n.endswith(".so")]);return
        if op=="aab-assets":emit([n for n in names if "/assets/" in n]);return
        if op=="aab-resources":emit([n for n in names if "/res/" in n or n.endswith("/resources.pb")]);return
        if op=="aab-bundle-config":emit({"present":"BundleConfig.pb" in names,"bytes":z.getinfo("BundleConfig.pb").file_size if "BundleConfig.pb" in names else 0});return
        if op=="aab-largest":emit(sorted([{"name":i.filename,"bytes":i.file_size} for i in infos],key=lambda x:x["bytes"],reverse=True)[:20]);return
        if op=="apks-split-apks":emit([n for n in names if n.endswith(".apk")]);return
        if op=="apks-split-names":emit([P(n).name for n in names if n.endswith(".apk")]);return
        if op=="apks-total-size":print(sum(i.file_size for i in infos if i.filename.endswith(".apk")));return
        if op=="apks-native-abis":
            ab=set()
            for n in names:
                if n.endswith(".apk"):
                    try:
                        with zipfile.ZipFile(io.BytesIO(z.read(n))) as q:
                            ab|={x.split("/")[1] for x in q.namelist() if x.startswith("lib/") and x.count("/")>=2}
                    except:pass
            emit(sorted(ab));return
        if op=="apks-dex-count":
            c=0
            for n in names:
                if n.endswith(".apk"):
                    try:
                        with zipfile.ZipFile(io.BytesIO(z.read(n))) as q:c+=sum(bool(re.fullmatch(r"classes\d*\.dex",P(x).name)) for x in q.namelist())
                    except:pass
            print(c);return
        if op=="apks-assets":
            out=[]
            for n in names:
                if n.endswith(".apk"):
                    try:
                        with zipfile.ZipFile(io.BytesIO(z.read(n))) as q:out += [n+":"+x for x in q.namelist() if x.startswith("assets/")]
                    except:pass
            emit(out);return
        if op=="bundle-integrity":emit({"valid":z.testzip() is None,"bad_entry":z.testzip(),"entries":len(infos)});return
        if op=="bundle-search":
            q=a[1].lower() if len(a)>1 else "";emit([n for n in names if q in n.lower()]);return

def main():
    cmd=P(sys.argv[0]).name; args=sys.argv[1:]
    if cmd not in COMMANDS:
        if args and args[0] in COMMANDS: cmd=args.pop(0)
        elif not args or args[0] in ("-h","--help"):
            print("Ocean Lab 200: document/token/project/binary/mobile inspection suite")
            print("\n".join(COMMANDS));return
        else: die("unknown command")
    if args and args[0] in ("-h","--help"):
        print(cmd+" — Ocean Lab functional utility");return
    group=cmd_parts(cmd)[0]
    if group=="office":office(cmd,args)
    elif group=="pdf":pdf(cmd,args)
    elif group=="mail":mail(cmd,args)
    elif group=="cal":cal(cmd,args)
    elif group=="token":token(cmd,args)
    elif group=="project":project(cmd,args)
    elif group=="source":source(cmd,args)
    elif group=="binary":binary(cmd,args)
    elif group=="string":string(cmd,args)
    elif group=="bundle":bundle(cmd,args)
if __name__=="__main__":main()
