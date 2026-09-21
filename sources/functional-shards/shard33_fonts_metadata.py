#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt,hashlib,json,re,struct,sys,xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
P=Path

SFNT=[
"fontsfnt-scaler-type","fontsfnt-table-count","fontsfnt-table-tags","fontsfnt-table-offsets","fontsfnt-table-lengths","fontsfnt-table-checksums","fontsfnt-head-units-per-em","fontsfnt-head-bbox","fontsfnt-head-created","fontsfnt-head-modified","fontsfnt-maxp-glyphs","fontsfnt-name-record-count","fontsfnt-name-strings","fontsfnt-name-family","fontsfnt-name-style","fontsfnt-name-full","fontsfnt-os2-weight","fontsfnt-os2-width","fontsfnt-post-format","fontsfnt-cmap-subtables","fontsfnt-sha256","fontsfnt-summary"]
WOFF=[
"woff-magic-check","woff-flavor","woff-length","woff-table-count","woff-total-sfnt-size","woff-version","woff-meta-size","woff-private-size","woff-table-directory","woff-summary"]
ICC=[
"icc-profile-size","icc-cmm-type","icc-version","icc-device-class","icc-color-space","icc-pcs","icc-created","icc-platform","icc-rendering-intent","icc-creator","icc-tag-count","icc-tag-signatures"]
XMP=[
"xmp-root","xmp-namespaces","xmp-descriptions","xmp-properties","xmp-dc-title","xmp-dc-creator","xmp-dc-subject","xmp-create-date","xmp-modify-date","xmp-summary"]
SUB=[
"subtrack-format-detect","subtrack-cue-count","subtrack-duration","subtrack-first-start","subtrack-last-end","subtrack-text-lines","subtrack-speakers","subtrack-tags","subtrack-overlaps","subtrack-gaps","subtrack-word-count","subtrack-summary"]
COMMANDS=SFNT+WOFF+ICC+XMP+SUB
assert len(COMMANDS)==66 and len(set(COMMANDS))==66

def emit(x):
    if isinstance(x,(dict,list,tuple,Counter)):print(json.dumps(x,indent=2,ensure_ascii=False,default=str))
    else:print(x)
def die(s,c=2):print(s,file=sys.stderr);raise SystemExit(c)
def sha(b):return hashlib.sha256(b).hexdigest()
def readb(path):return P(path).read_bytes()

def tag4(b):return b.decode("latin1",errors="replace")
def mac_time(x):
    try:return (dt.datetime(1904,1,1,tzinfo=dt.timezone.utc)+dt.timedelta(seconds=x)).isoformat()
    except:return None

def sfnt(path):
    b=readb(path)
    if len(b)<12:die("truncated sfnt header")
    scaler=b[:4];num=struct.unpack(">H",b[4:6])[0]
    if 12+16*num>len(b):die("truncated sfnt table directory")
    tabs=[]
    for i in range(num):
        p=12+i*16;tag=tag4(b[p:p+4]);chk,off,n=struct.unpack(">III",b[p+4:p+16])
        tabs.append({"tag":tag,"checksum":chk,"offset":off,"length":n})
    return b,scaler,tabs

def table_bytes(b,tabs,tag):
    row=next((x for x in tabs if x["tag"]==tag),None)
    if not row:return None
    off,n=row["offset"],row["length"]
    if off+n>len(b):die("sfnt table exceeds file: "+tag)
    return b[off:off+n]

def decode_name(raw,platform,encoding):
    try:
        if platform in (0,3):return raw.decode("utf-16-be",errors="replace")
        if platform==1:return raw.decode("mac_roman",errors="replace")
        return raw.decode("latin1",errors="replace")
    except:return raw.hex()

def name_records(tb):
    if not tb or len(tb)<6:return []
    fmt,count,stringoff=struct.unpack(">HHH",tb[:6]);out=[]
    if 6+12*count>len(tb):return out
    for i in range(count):
        p=6+12*i;platform,enc,lang,nid,n,off=struct.unpack(">HHHHHH",tb[p:p+12]);s0=stringoff+off;s1=s0+n
        if s1>len(tb):continue
        text=decode_name(tb[s0:s1],platform,enc)
        out.append({"platform":platform,"encoding":enc,"language":lang,"name_id":nid,"text":text})
    return out

def sfnt_cmd(cmd,a):
    if not a:die("font path required")
    op=cmd.removeprefix("fontsfnt-");b,scaler,tabs=sfnt(a[0])
    if op=="scaler-type":
        raw=int.from_bytes(scaler,"big")
        known={0x00010000:"TrueType",0x4f54544f:"CFF/OpenType",0x74727565:"true",0x74797031:"typ1"}
        emit({"raw":scaler.hex(),"name":known.get(raw,tag4(scaler))});return
    if op=="table-count":print(len(tabs));return
    if op=="table-tags":emit([x["tag"] for x in tabs]);return
    if op=="table-offsets":emit({x["tag"]:x["offset"] for x in tabs});return
    if op=="table-lengths":emit({x["tag"]:x["length"] for x in tabs});return
    if op=="table-checksums":emit({x["tag"]:f'{x["checksum"]:08x}' for x in tabs});return
    head=table_bytes(b,tabs,"head")
    if op=="head-units-per-em":
        print(struct.unpack(">H",head[18:20])[0] if head and len(head)>=20 else "");return
    if op=="head-bbox":
        if not head or len(head)<44:emit(None);return
        x0,y0,x1,y1=struct.unpack(">hhhh",head[36:44]);emit({"xMin":x0,"yMin":y0,"xMax":x1,"yMax":y1});return
    if op=="head-created":
        print(mac_time(struct.unpack(">Q",head[20:28])[0]) if head and len(head)>=28 else "");return
    if op=="head-modified":
        print(mac_time(struct.unpack(">Q",head[28:36])[0]) if head and len(head)>=36 else "");return
    if op=="maxp-glyphs":
        tb=table_bytes(b,tabs,"maxp");print(struct.unpack(">H",tb[4:6])[0] if tb and len(tb)>=6 else "");return
    nr=name_records(table_bytes(b,tabs,"name"))
    if op=="name-record-count":print(len(nr));return
    if op=="name-strings":emit(nr);return
    ids={"name-family":1,"name-style":2,"name-full":4}
    if op in ids:emit([x["text"] for x in nr if x["name_id"]==ids[op]]);return
    if op in ("os2-weight","os2-width"):
        tb=table_bytes(b,tabs,"OS/2");off=4 if op.endswith("weight") else 6
        print(struct.unpack(">H",tb[off:off+2])[0] if tb and len(tb)>=off+2 else "");return
    if op=="post-format":
        tb=table_bytes(b,tabs,"post")
        if not tb or len(tb)<4:emit(None);return
        raw=struct.unpack(">I",tb[:4])[0];emit({"raw":raw,"major":raw>>16,"minor":raw&0xffff});return
    if op=="cmap-subtables":
        tb=table_bytes(b,tabs,"cmap");rows=[]
        if tb and len(tb)>=4:
            version,n=struct.unpack(">HH",tb[:4])
            for i in range(n):
                p=4+8*i
                if p+8<=len(tb):
                    platform,enc,off=struct.unpack(">HHI",tb[p:p+8]);rows.append({"platform":platform,"encoding":enc,"offset":off})
        emit(rows);return
    if op=="sha256":print(sha(b));return
    if op=="summary":
        emit({"bytes":len(b),"tables":len(tabs),"tags":[x["tag"] for x in tabs],"name_records":len(nr),"sha256":sha(b)});return

def parse_woff(path):
    b=readb(path)
    if len(b)<44:die("truncated WOFF header")
    magic=b[:4];flavor=b[4:8];length,num,res,total,major,minor,metaOff,metaLen,metaOrig,privOff,privLen=struct.unpack(">IHHIHHIIIII",b[8:44])
    return b,{"magic":tag4(magic),"flavor":flavor.hex(),"length":length,"numTables":num,"reserved":res,"totalSfntSize":total,"majorVersion":major,"minorVersion":minor,"metaOffset":metaOff,"metaLength":metaLen,"metaOrigLength":metaOrig,"privOffset":privOff,"privLength":privLen}

def woff(cmd,a):
    if not a:die("WOFF/WOFF2 path required")
    op=cmd.removeprefix("woff-");b,h=parse_woff(a[0])
    if op=="magic-check":emit({"valid":b[:4] in (b"wOFF",b"wOF2"),"magic":tag4(b[:4])});return
    if op=="flavor":emit(h["flavor"]);return
    if op=="length":print(h["length"]);return
    if op=="table-count":print(h["numTables"]);return
    if op=="total-sfnt-size":print(h["totalSfntSize"]);return
    if op=="version":emit({"major":h["majorVersion"],"minor":h["minorVersion"]});return
    if op=="meta-size":emit({"compressed":h["metaLength"],"original":h["metaOrigLength"]});return
    if op=="private-size":print(h["privLength"]);return
    if op=="table-directory":
        if b[:4]!=b"wOFF":emit({"supported":False,"reason":"WOFF2 directory is transformed/compressed"});return
        rows=[];p=44
        for _ in range(h["numTables"]):
            if p+20>len(b):die("truncated WOFF table directory")
            tag=b[p:p+4].decode("latin1");off,comp,orig,chk=struct.unpack(">IIII",b[p+4:p+20]);p+=20
            rows.append({"tag":tag,"offset":off,"compressed":comp,"original":orig,"checksum":f"{chk:08x}"})
        emit(rows);return
    if op=="summary":emit({**h,"fileBytes":len(b),"sha256":sha(b)});return

def sig(b):return b.decode("latin1",errors="replace").rstrip("\x00 ")
def icc_header(path):
    b=readb(path)
    if len(b)<132:die("ICC profile too short")
    size=int.from_bytes(b[0:4],"big");count=int.from_bytes(b[128:132],"big")
    tags=[];p=132
    for _ in range(count):
        if p+12>len(b):die("truncated ICC tag table")
        tags.append({"signature":sig(b[p:p+4]),"offset":int.from_bytes(b[p+4:p+8],"big"),"size":int.from_bytes(b[p+8:p+12],"big")});p+=12
    return b,size,count,tags

def icc(cmd,a):
    if not a:die("ICC path required")
    op=cmd.removeprefix("icc-");b,size,count,tags=icc_header(a[0])
    if op=="profile-size":print(size);return
    if op=="cmm-type":print(sig(b[4:8]));return
    if op=="version":
        x=b[8:12];emit({"major":x[0],"minor":x[1]>>4,"bugfix":x[1]&15,"raw":x.hex()});return
    if op=="device-class":print(sig(b[12:16]));return
    if op=="color-space":print(sig(b[16:20]));return
    if op=="pcs":print(sig(b[20:24]));return
    if op=="created":
        vals=struct.unpack(">HHHHHH",b[24:36])
        try:print(dt.datetime(*vals,tzinfo=dt.timezone.utc).isoformat())
        except:emit(vals)
        return
    if op=="platform":print(sig(b[40:44]));return
    if op=="rendering-intent":print(int.from_bytes(b[64:68],"big"));return
    if op=="creator":print(sig(b[80:84]));return
    if op=="tag-count":print(count);return
    if op=="tag-signatures":emit([x["signature"] for x in tags]);return

def xmp_parse(path):
    s=P(path).read_text(errors="replace")
    start=min([x for x in [s.find("<x:xmpmeta"),s.find("<rdf:RDF"),s.find("<xmpmeta")] if x>=0] or [0])
    fragment=s[start:]
    root=ET.fromstring(fragment)
    ns={}
    for event,item in ET.iterparse(P(path),events=("start-ns",)):
        prefix,uri=item;ns[prefix or "default"]=uri
    return root,ns

def local(tag):return tag.split("}")[-1].split(":")[-1]
def xmp_values(root,want):
    out=[]
    for x in root.iter():
        if local(x.tag)==want:
            txt=" ".join(t.strip() for t in x.itertext() if t.strip())
            if txt:out.append(txt)
    return out

def xmp(cmd,a):
    if not a:die("XMP XML path required")
    op=cmd.removeprefix("xmp-");root,ns=xmp_parse(a[0])
    if op=="root":print(local(root.tag));return
    if op=="namespaces":emit(ns);return
    desc=[x for x in root.iter() if local(x.tag)=="Description"]
    if op=="descriptions":emit([{"attributes":{local(k):v for k,v in x.attrib.items()}} for x in desc]);return
    if op=="properties":
        props={}
        for x in root.iter():
            if len(x)==0 and (x.text or "").strip():props.setdefault(local(x.tag),[]).append((x.text or "").strip())
        emit(props);return
    if op=="dc-title":emit(xmp_values(root,"title"));return
    if op=="dc-creator":emit(xmp_values(root,"creator"));return
    if op=="dc-subject":emit(xmp_values(root,"subject"));return
    if op=="create-date":emit(xmp_values(root,"CreateDate"));return
    if op=="modify-date":emit(xmp_values(root,"ModifyDate"));return
    if op=="summary":
        props=sum(1 for x in root.iter() if len(x)==0 and (x.text or "").strip())
        emit({"root":local(root.tag),"namespaces":len(ns),"descriptions":len(desc),"leaf_properties":props});return

def ts(s):
    s=s.strip().replace(",",".")
    m=re.match(r"(?:(\d+):)?(\d{1,2}):(\d{2}(?:\.\d+)?)",s)
    if not m:return None
    h=int(m.group(1) or 0);mi=int(m.group(2));sec=float(m.group(3));return h*3600+mi*60+sec

def parse_sub(path):
    s=P(path).read_text(errors="replace").replace("\r\n","\n");st=s.lstrip()
    cues=[];fmt="unknown"
    if st.startswith("WEBVTT"):
        fmt="webvtt"
        for block in re.split(r"\n\s*\n",s):
            lines=[x for x in block.splitlines() if x.strip()]
            ti=next((i for i,x in enumerate(lines) if "-->" in x),None)
            if ti is None:continue
            a,b=lines[ti].split("-->",1);endtok=b.strip().split()[0]
            cues.append({"start":ts(a),"end":ts(endtok),"text":"\n".join(lines[ti+1:])})
    elif re.search(r"(?m)^\s*Dialogue:",s):
        fmt="ass"
        for line in s.splitlines():
            if not line.lstrip().startswith("Dialogue:"):continue
            parts=line.split(",",9)
            if len(parts)>=10:cues.append({"start":ts(parts[1]),"end":ts(parts[2]),"text":parts[9]})
    else:
        fmt="srt"
        for block in re.split(r"\n\s*\n",s):
            lines=[x for x in block.splitlines() if x.strip()]
            ti=next((i for i,x in enumerate(lines) if "-->" in x),None)
            if ti is None:continue
            a,b=lines[ti].split("-->",1)
            cues.append({"start":ts(a),"end":ts(b.strip().split()[0]),"text":"\n".join(lines[ti+1:])})
    cues=[x for x in cues if x["start"] is not None and x["end"] is not None]
    return fmt,cues

def sub(cmd,a):
    if not a:die("subtitle path required")
    op=cmd.removeprefix("subtrack-");fmt,cues=parse_sub(a[0])
    starts=[x["start"] for x in cues];ends=[x["end"] for x in cues]
    if op=="format-detect":print(fmt);return
    if op=="cue-count":print(len(cues));return
    if op=="duration":print((max(ends)-min(starts)) if cues else 0);return
    if op=="first-start":print(min(starts) if starts else "");return
    if op=="last-end":print(max(ends) if ends else "");return
    if op=="text-lines":emit([line for x in cues for line in x["text"].splitlines() if line.strip()]);return
    if op=="speakers":
        names=[]
        for x in cues:
            m=re.match(r"(?:<v\s+([^>]+)>|([A-Z][A-Z0-9 _-]{1,30}):)",x["text"])
            if m:names.append(m.group(1) or m.group(2))
        emit(sorted(set(names)));return
    if op=="tags":emit(sorted(set(re.findall(r"</?([A-Za-z][\w-]*)\b", "\n".join(x["text"] for x in cues)))));return
    if op=="overlaps":
        rows=[]
        for i in range(1,len(cues)):
            if cues[i]["start"]<cues[i-1]["end"]:rows.append({"left":i-1,"right":i,"seconds":cues[i-1]["end"]-cues[i]["start"]})
        emit(rows);return
    if op=="gaps":
        rows=[]
        for i in range(1,len(cues)):
            if cues[i]["start"]>cues[i-1]["end"]:rows.append({"left":i-1,"right":i,"seconds":cues[i]["start"]-cues[i-1]["end"]})
        emit(rows);return
    if op=="word-count":print(sum(len(re.findall(r"\b[\w'-]+\b",x["text"])) for x in cues));return
    if op=="summary":
        emit({"format":fmt,"cues":len(cues),"first_start":min(starts) if starts else None,"last_end":max(ends) if ends else None,"duration":(max(ends)-min(starts)) if cues else 0,"words":sum(len(re.findall(r"\b[\w'-]+\b",x["text"])) for x in cues)});return

def main():
    cmd=P(sys.argv[0]).name;a=sys.argv[1:]
    if cmd not in COMMANDS:
        if a and a[0] in COMMANDS:cmd=a.pop(0)
        elif not a or a[0] in ("-h","--help"):
            print("Shard 33 — SFNT/WOFF/ICC/XMP/subtitle metadata utilities");print("\n".join(COMMANDS));return
        else:die("unknown command")
    if a and a[0] in ("-h","--help"):print(cmd+" — functional shard 33 utility");return
    if cmd in SFNT:sfnt_cmd(cmd,a)
    elif cmd in WOFF:woff(cmd,a)
    elif cmd in ICC:icc(cmd,a)
    elif cmd in XMP:xmp(cmd,a)
    else:sub(cmd,a)
if __name__=="__main__":main()
