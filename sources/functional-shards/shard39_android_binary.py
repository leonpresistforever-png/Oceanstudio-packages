#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,math,re,struct,sys,zipfile,zlib
from collections import Counter
from pathlib import Path
P=Path

DEX=[
"dex-magic","dex-version","dex-checksum","dex-signature","dex-file-size","dex-header-size","dex-endian-tag","dex-link-size","dex-map-off","dex-string-count","dex-string-off","dex-type-count","dex-type-off","dex-proto-count","dex-proto-off","dex-field-count","dex-field-off","dex-method-count","dex-method-off","dex-class-count","dex-class-off","dex-data-size","dex-data-off","dex-map-list","dex-string-sample","dex-strings","dex-type-descriptors","dex-method-id-summary","dex-class-def-summary","dex-sha1-check","dex-adler32-check","dex-compact-dex-detect","dex-hiddenapi-hints","dex-duplicate-strings","dex-utf8-errors","dex-section-ranges","dex-section-overlap","dex-entropy","dex-sha256","dex-summary"]
AXML=[
"axml-magic","axml-chunk-size","axml-chunk-count","axml-chunk-types","axml-string-pool-detect","axml-string-count","axml-utf8-flag","axml-resource-map-count","axml-namespace-count","axml-element-count","axml-attribute-count","axml-text-chunk-count","axml-chunk-offsets","axml-invalid-chunks","axml-package-hints","axml-permission-string-hints","axml-intent-string-hints","axml-component-string-hints","axml-sha256","axml-summary"]
ARSC=[
"arsc-magic","arsc-file-size","arsc-chunk-count","arsc-chunk-types","arsc-string-pool-count","arsc-package-count","arsc-package-ids","arsc-package-name-hints","arsc-type-string-hints","arsc-key-string-hints","arsc-type-chunk-count","arsc-spec-chunk-count","arsc-entry-count-hints","arsc-config-size-hints","arsc-density-hints","arsc-locale-hints","arsc-chunk-offsets","arsc-sha256","arsc-entropy","arsc-summary"]
APK=[
"apk-entry-count","apk-uncompressed-size","apk-compressed-size","apk-compression-ratio","apk-dex-files","apk-dex-total","apk-native-abis","apk-native-lib-count","apk-assets-count","apk-res-count","apk-signing-block-detect","apk-v1-signature-files","apk-zipalign-check","apk-central-directory-offset","apk-comment","apk-duplicate-entries","apk-zero-size-files","apk-largest-files","apk-sha256","apk-summary"]
COMMANDS=DEX+AXML+ARSC+APK
assert len(COMMANDS)==100 and len(set(COMMANDS))==100

def emit(x):
    if isinstance(x,(dict,list,tuple,Counter)):print(json.dumps(x,indent=2,ensure_ascii=False,default=str))
    else:print(x)
def die(s,c=2):print(s,file=sys.stderr);raise SystemExit(c)
def entropy(b):
    if not b:return 0.0
    c=Counter(b);return -sum((n/len(b))*math.log2(n/len(b)) for n in c.values())
def uleb(b,p):
    n=0;s=0
    while p<len(b):
        x=b[p];p+=1;n|=(x&0x7f)<<s
        if not x&0x80:return n,p
        s+=7
        if s>35:break
    raise ValueError("bad uleb")

DEX_FIELDS={
"file-size":(32,"I"),"header-size":(36,"I"),"endian-tag":(40,"I"),"link-size":(44,"I"),"map-off":(52,"I"),
"string-count":(56,"I"),"string-off":(60,"I"),"type-count":(64,"I"),"type-off":(68,"I"),
"proto-count":(72,"I"),"proto-off":(76,"I"),"field-count":(80,"I"),"field-off":(84,"I"),
"method-count":(88,"I"),"method-off":(92,"I"),"class-count":(96,"I"),"class-off":(100,"I"),
"data-size":(104,"I"),"data-off":(108,"I")
}
def dex_header(b):
    if len(b)<112:die("truncated DEX header")
    h={k:struct.unpack_from("<"+fmt,b,off)[0] for k,(off,fmt) in DEX_FIELDS.items()}
    h["magic"]=b[:8];h["checksum"]=struct.unpack_from("<I",b,8)[0];h["signature"]=b[12:32]
    return h
def dex_strings(b,h,limit=None):
    out=[];errs=0
    n=min(h["string-count"],1_000_000)
    if h["string-off"]+n*4>len(b):return [],1
    for i in range(n if limit is None else min(n,limit)):
        off=struct.unpack_from("<I",b,h["string-off"]+i*4)[0]
        if off>=len(b):errs+=1;out.append("");continue
        try:_,p=uleb(b,off)
        except:errs+=1;out.append("");continue
        e=b.find(b"\0",p)
        if e<0:e=len(b);errs+=1
        try:s=b[p:e].decode("utf-8")
        except:s=b[p:e].decode("utf-8",errors="replace");errs+=1
        out.append(s)
    return out,errs
def dex_sections(h):
    defs=[("string_ids",h["string-off"],h["string-count"]*4),("type_ids",h["type-off"],h["type-count"]*4),("proto_ids",h["proto-off"],h["proto-count"]*12),("field_ids",h["field-off"],h["field-count"]*8),("method_ids",h["method-off"],h["method-count"]*8),("class_defs",h["class-off"],h["class-count"]*32),("data",h["data-off"],h["data-size"])]
    return [{"name":n,"offset":o,"size":s,"end":o+s} for n,o,s in defs if o or s]
def dex_map(b,h):
    off=h["map-off"]
    if not off or off+4>len(b):return []
    n=struct.unpack_from("<I",b,off)[0];out=[];p=off+4
    for _ in range(min(n,10000)):
        if p+12>len(b):break
        typ,unused,size,ofs=struct.unpack_from("<HHII",b,p);p+=12
        out.append({"type":typ,"size":size,"offset":ofs})
    return out
def dex(cmd,a):
    if not a:die("DEX path required")
    op=cmd.removeprefix("dex-");b=P(a[0]).read_bytes()
    compact=b[:4]==b"cdex";h=dex_header(b) if len(b)>=112 else None
    if op=="magic":emit({"magic":b[:8].decode("latin1",errors="replace"),"dex":b[:4]==b"dex\n","compact":compact});return
    if op=="compact-dex-detect":print(str(compact).lower());return
    if h is None:die("DEX header unavailable")
    if op=="version":print(b[4:7].decode(errors="replace"));return
    if op=="checksum":print(f"{h['checksum']:08x}");return
    if op=="signature":print(h["signature"].hex());return
    if op in DEX_FIELDS:print(h[op]);return
    if op=="map-list":emit(dex_map(b,h));return
    strings,errs=dex_strings(b,h)
    if op=="string-sample":emit(strings[:int(a[1]) if len(a)>1 else 20]);return
    if op=="strings":emit(strings);return
    if op=="type-descriptors":
        out=[]
        for i in range(min(h["type-count"],1_000_000)):
            off=h["type-off"]+i*4
            if off+4>len(b):break
            idx=struct.unpack_from("<I",b,off)[0]
            out.append(strings[idx] if idx<len(strings) else None)
        emit(out);return
    if op=="method-id-summary":
        out=[]
        for i in range(min(h["method-count"],100000)):
            off=h["method-off"]+i*8
            if off+8>len(b):break
            cls,proto,name=struct.unpack_from("<HHI",b,off);out.append({"class_idx":cls,"proto_idx":proto,"name_idx":name,"name":strings[name] if name<len(strings) else None})
        emit(out);return
    if op=="class-def-summary":
        out=[]
        for i in range(min(h["class-count"],100000)):
            off=h["class-off"]+i*32
            if off+32>len(b):break
            vals=struct.unpack_from("<8I",b,off);out.append({"class_idx":vals[0],"access_flags":vals[1],"superclass_idx":vals[2],"interfaces_off":vals[3],"source_file_idx":vals[4],"annotations_off":vals[5],"class_data_off":vals[6],"static_values_off":vals[7]})
        emit(out);return
    if op=="sha1-check":
        calc=hashlib.sha1(b[32:]).digest();emit({"valid":calc==h["signature"],"stored":h["signature"].hex(),"calculated":calc.hex()});return
    if op=="adler32-check":
        calc=zlib.adler32(b[12:])&0xffffffff;emit({"valid":calc==h["checksum"],"stored":f"{h['checksum']:08x}","calculated":f"{calc:08x}"});return
    if op=="hiddenapi-hints":emit([s for s in strings if "hiddenapi" in s.lower() or "hidden_api" in s.lower()]);return
    if op=="duplicate-strings":emit({s:n for s,n in Counter(strings).items() if s and n>1});return
    if op=="utf8-errors":print(errs);return
    if op=="section-ranges":emit(dex_sections(h));return
    if op=="section-overlap":
        q=sorted(dex_sections(h),key=lambda x:x["offset"]);bad=[]
        for i in range(1,len(q)):
            if q[i]["offset"]<q[i-1]["end"]:bad.append([q[i-1]["name"],q[i]["name"]])
        emit({"hasOverlap":bool(bad),"overlaps":bad});return
    if op=="entropy":print(f"{entropy(b):.6f}");return
    if op=="sha256":print(hashlib.sha256(b).hexdigest());return
    if op=="summary":emit({"version":b[4:7].decode(errors="replace"),"fileSize":h["file-size"],"strings":h["string-count"],"types":h["type-count"],"protos":h["proto-count"],"fields":h["field-count"],"methods":h["method-count"],"classes":h["class-count"],"dataSize":h["data-size"],"mapItems":len(dex_map(b,h))});return

def chunks(b,start=0,end=None,recursive=False):
    end=len(b) if end is None else min(end,len(b));out=[];p=start
    while p+8<=end:
        typ,hs,size=struct.unpack_from("<HHI",b,p)
        if hs<8 or size<hs or p+size>end:out.append({"offset":p,"type":typ,"headerSize":hs,"size":size,"valid":False});break
        row={"offset":p,"type":typ,"headerSize":hs,"size":size,"end":p+size,"valid":True};out.append(row)
        if recursive and typ in (0x0002,0x0200) and p+hs<p+size:
            out.extend(chunks(b,p+hs,p+size,True))
        p+=size
    return out

def read_len8(b,p):
    if p>=len(b):raise ValueError
    x=b[p];p+=1
    if x&0x80:
        if p>=len(b):raise ValueError
        x=((x&0x7f)<<8)|b[p];p+=1
    return x,p
def read_len16(b,p):
    if p+2>len(b):raise ValueError
    x=struct.unpack_from("<H",b,p)[0];p+=2
    if x&0x8000:
        if p+2>len(b):raise ValueError
        x=((x&0x7fff)<<16)|struct.unpack_from("<H",b,p)[0];p+=2
    return x,p
def string_pool(b,row):
    p=row["offset"];hs=row["headerSize"]
    if p+28>len(b):return {"count":0,"utf8":False,"strings":[]}
    count,styles,flags,stringsStart,stylesStart=struct.unpack_from("<IIIII",b,p+8);utf8=bool(flags&0x100)
    offs=[];base=p+hs
    for i in range(min(count,200000)):
        if base+i*4+4>p+row["size"]:break
        offs.append(struct.unpack_from("<I",b,base+i*4)[0])
    vals=[]
    for off in offs:
        q=p+stringsStart+off
        try:
            if utf8:
                _,q=read_len8(b,q);n,q=read_len8(b,q);vals.append(b[q:q+n].decode("utf-8",errors="replace"))
            else:
                n,q=read_len16(b,q);vals.append(b[q:q+n*2].decode("utf-16le",errors="replace"))
        except:vals.append("")
    return {"count":count,"utf8":utf8,"strings":vals}

def axml_data(b):
    cs=chunks(b)
    if cs and cs[0].get("valid") and cs[0]["type"]==0x0003 and cs[0]["headerSize"]<cs[0]["size"]:
        cs=[cs[0]]+chunks(b,cs[0]["offset"]+cs[0]["headerSize"],cs[0]["end"],False)
    sp=next((x for x in cs if x["type"]==0x0001 and x["valid"]),None)
    pool=string_pool(b,sp) if sp else {"count":0,"utf8":False,"strings":[]}
    return cs,pool
def axml(cmd,a):
    if not a:die("binary Android XML path required")
    op=cmd.removeprefix("axml-");b=P(a[0]).read_bytes();cs,pool=axml_data(b)
    if op=="magic":emit({"type":struct.unpack_from("<H",b,0)[0] if len(b)>=2 else None,"binaryXml":len(b)>=2 and struct.unpack_from("<H",b,0)[0]==0x0003});return
    if op=="chunk-size":print(struct.unpack_from("<I",b,4)[0] if len(b)>=8 else 0);return
    if op=="chunk-count":print(len(cs));return
    if op=="chunk-types":emit(Counter(f"0x{x['type']:04x}" for x in cs));return
    if op=="string-pool-detect":print(str(any(x["type"]==0x0001 for x in cs)).lower());return
    if op=="string-count":print(pool["count"]);return
    if op=="utf8-flag":print(str(pool["utf8"]).lower());return
    if op=="resource-map-count":print(sum(1 for x in cs if x["type"]==0x0180));return
    if op=="namespace-count":print(sum(1 for x in cs if x["type"] in (0x0100,0x0101)));return
    if op=="element-count":print(sum(1 for x in cs if x["type"]==0x0102));return
    if op=="attribute-count":
        total=0
        for x in cs:
            if x["type"]==0x0102 and x["offset"]+28<=len(b):
                try:total+=struct.unpack_from("<H",b,x["offset"]+28)[0]
                except:pass
        print(total);return
    if op=="text-chunk-count":print(sum(1 for x in cs if x["type"]==0x0104));return
    if op=="chunk-offsets":emit([{"offset":x["offset"],"type":f"0x{x['type']:04x}","size":x["size"]} for x in cs]);return
    if op=="invalid-chunks":emit([x for x in cs if not x["valid"]]);return
    ss=pool["strings"]
    if op=="package-hints":emit(sorted({s for s in ss if re.fullmatch(r"[a-zA-Z]\w*(?:\.[a-zA-Z]\w*){1,}",s)}));return
    if op=="permission-string-hints":emit([s for s in ss if "permission." in s.lower()]);return
    if op=="intent-string-hints":emit([s for s in ss if "android.intent." in s.lower()]);return
    if op=="component-string-hints":emit([s for s in ss if re.search(r"(Activity|Service|Receiver|Provider)$",s)]);return
    if op=="sha256":print(hashlib.sha256(b).hexdigest());return
    if op=="summary":emit({"bytes":len(b),"chunks":len(cs),"strings":pool["count"],"utf8":pool["utf8"],"elements":sum(1 for x in cs if x["type"]==0x0102),"namespaces":sum(1 for x in cs if x["type"] in (0x0100,0x0101))});return

def arsc_data(b):
    return chunks(b,0,len(b),True)
def pkg_name(b,row):
    p=row["offset"]
    if p+268>len(b):return ""
    raw=b[p+12:p+268]
    return raw.decode("utf-16le",errors="ignore").split("\0",1)[0]
def arsc(cmd,a):
    if not a:die("resources.arsc path required")
    op=cmd.removeprefix("arsc-");b=P(a[0]).read_bytes();cs=arsc_data(b)
    if op=="magic":emit({"type":struct.unpack_from("<H",b,0)[0] if len(b)>=2 else None,"resourceTable":len(b)>=2 and struct.unpack_from("<H",b,0)[0]==0x0002});return
    if op=="file-size":print(len(b));return
    if op=="chunk-count":print(len(cs));return
    if op=="chunk-types":emit(Counter(f"0x{x['type']:04x}" for x in cs));return
    if op=="string-pool-count":print(sum(1 for x in cs if x["type"]==0x0001));return
    pkgs=[x for x in cs if x["type"]==0x0200]
    if op=="package-count":print(len(pkgs));return
    if op=="package-ids":emit([struct.unpack_from("<I",b,x["offset"]+8)[0] for x in pkgs if x["offset"]+12<=len(b)]);return
    if op=="package-name-hints":emit([pkg_name(b,x) for x in pkgs if pkg_name(b,x)]);return
    if op=="type-string-hints":
        out=[]
        for x in pkgs:
            p=x["offset"]
            if p+272<=len(b):out.append(struct.unpack_from("<I",b,p+268)[0])
        emit(out);return
    if op=="key-string-hints":
        out=[]
        for x in pkgs:
            p=x["offset"]
            if p+280<=len(b):out.append(struct.unpack_from("<I",b,p+276)[0])
        emit(out);return
    types=[x for x in cs if x["type"]==0x0201];specs=[x for x in cs if x["type"]==0x0202]
    if op=="type-chunk-count":print(len(types));return
    if op=="spec-chunk-count":print(len(specs));return
    if op=="entry-count-hints":
        emit([struct.unpack_from("<I",b,x["offset"]+12)[0] for x in types if x["offset"]+16<=len(b)]);return
    if op in ("config-size-hints","density-hints","locale-hints"):
        vals=[]
        for x in types:
            base=x["offset"]+20
            if base+4>len(b):continue
            size=struct.unpack_from("<I",b,base)[0]
            if op=="config-size-hints":vals.append(size)
            elif op=="density-hints":
                vals.append(struct.unpack_from("<H",b,base+14)[0] if size>=16 and base+16<=len(b) else 0)
            else:
                if size>=12 and base+12<=len(b):
                    lang=b[base+8:base+10].decode("latin1",errors="ignore").rstrip("\0");country=b[base+10:base+12].decode("latin1",errors="ignore").rstrip("\0");vals.append((lang+"-"+country).strip("-"))
        emit(vals);return
    if op=="chunk-offsets":emit([{"offset":x["offset"],"type":f"0x{x['type']:04x}","size":x["size"]} for x in cs]);return
    if op=="sha256":print(hashlib.sha256(b).hexdigest());return
    if op=="entropy":print(f"{entropy(b):.6f}");return
    if op=="summary":emit({"bytes":len(b),"chunks":len(cs),"packages":len(pkgs),"packageNames":[pkg_name(b,x) for x in pkgs if pkg_name(b,x)],"stringPools":sum(1 for x in cs if x["type"]==0x0001),"typeChunks":len(types),"typeSpecs":len(specs)});return

def eocd(b):
    p=b.rfind(b"PK\x05\x06",max(0,len(b)-65557))
    if p<0:return None
    if p+22>len(b):return None
    vals=struct.unpack_from("<4s4H2IH",b,p)
    return {"offset":p,"entries":vals[4],"centralSize":vals[5],"centralOffset":vals[6],"commentLength":vals[7]}
def apk(cmd,a):
    if not a:die("APK path required")
    op=cmd.removeprefix("apk-");p=P(a[0]);b=p.read_bytes()
    with zipfile.ZipFile(p) as z:
        infos=z.infolist();names=[i.filename for i in infos]
        if op=="entry-count":print(len(infos));return
        if op=="uncompressed-size":print(sum(i.file_size for i in infos));return
        if op=="compressed-size":print(sum(i.compress_size for i in infos));return
        if op=="compression-ratio":
            raw=sum(i.file_size for i in infos);comp=sum(i.compress_size for i in infos);print(comp/raw if raw else 0);return
        if op=="dex-files":emit([n for n in names if re.fullmatch(r"(?:.*/)?classes\d*\.dex",n)]);return
        if op=="dex-total":print(sum(i.file_size for i in infos if re.fullmatch(r"(?:.*/)?classes\d*\.dex",i.filename)));return
        if op=="native-abis":emit(sorted({n.split("/")[1] for n in names if n.startswith("lib/") and n.count("/")>=2 and n.endswith(".so")}));return
        if op=="native-lib-count":print(sum(n.startswith("lib/") and n.endswith(".so") for n in names));return
        if op=="assets-count":print(sum(n.startswith("assets/") for n in names));return
        if op=="res-count":print(sum(n.startswith("res/") for n in names));return
        if op=="v1-signature-files":emit([n for n in names if n.upper().startswith("META-INF/") and n.upper().endswith((".RSA",".DSA",".EC",".SF",".MF"))]);return
        if op=="zipalign-check":
            bad=[]
            for i in infos:
                if i.compress_type!=zipfile.ZIP_STORED or i.is_dir():continue
                off=i.header_offset
                if off+30>len(b):continue
                fn,ex=struct.unpack_from("<HH",b,off+26);dataoff=off+30+fn+ex
                if dataoff%4:bad.append({"name":i.filename,"dataOffset":dataoff})
            emit({"aligned4":not bad,"misaligned":bad});return
        if op=="comment":emit(z.comment.decode(errors="replace"));return
        if op=="duplicate-entries":emit({n:c for n,c in Counter(names).items() if c>1});return
        if op=="zero-size-files":emit([i.filename for i in infos if i.file_size==0 and not i.is_dir()]);return
        if op=="largest-files":emit(sorted([{"name":i.filename,"bytes":i.file_size,"compressed":i.compress_size} for i in infos],key=lambda x:x["bytes"],reverse=True)[:int(a[1]) if len(a)>1 else 20]);return
    if op=="signing-block-detect":emit({"apkSigBlock42":b"APK Sig Block 42" in b});return
    if op=="central-directory-offset":
        q=eocd(b);emit(None if not q else q["centralOffset"]);return
    if op=="sha256":print(hashlib.sha256(b).hexdigest());return
    if op=="summary":
        q=eocd(b)
        with zipfile.ZipFile(p) as z:
            infos=z.infolist();names=[i.filename for i in infos]
            emit({"entries":len(infos),"bytes":len(b),"dexFiles":sum(bool(re.fullmatch(r"(?:.*/)?classes\d*\.dex",n)) for n in names),"nativeAbis":sorted({n.split("/")[1] for n in names if n.startswith("lib/") and n.count("/")>=2}),"v1Signatures":sum(n.upper().startswith("META-INF/") and n.upper().endswith((".RSA",".DSA",".EC",".SF")) for n in names),"v2v3SigningBlock":b"APK Sig Block 42" in b,"centralDirectory":q});return

def main():
    cmd=P(sys.argv[0]).name;a=sys.argv[1:]
    if cmd not in COMMANDS:
        if a and a[0] in COMMANDS:cmd=a.pop(0)
        elif not a or a[0] in ("-h","--help"):
            print("Shard 39 — Android DEX/AXML/ARSC/APK structural utilities");print("\n".join(COMMANDS));return
        else:die("unknown command")
    if a and a[0] in ("-h","--help"):print(cmd+" — functional shard 39 utility");return
    if cmd in DEX:dex(cmd,a)
    elif cmd in AXML:axml(cmd,a)
    elif cmd in ARSC:arsc(cmd,a)
    else:apk(cmd,a)
if __name__=="__main__":main()
