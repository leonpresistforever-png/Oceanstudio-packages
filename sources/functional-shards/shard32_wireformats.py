#!/usr/bin/env python3
from __future__ import annotations
import hashlib,ipaddress,json,re,struct,sys,urllib.parse
from collections import Counter
from pathlib import Path
P=Path

DNS=[
"dnswire-id","dnswire-flags","dnswire-opcode","dnswire-rcode","dnswire-counts","dnswire-questions","dnswire-qnames","dnswire-qtypes","dnswire-answers","dnswire-answer-types","dnswire-answer-ttls","dnswire-authorities","dnswire-additionals","dnswire-nameservers","dnswire-cnames","dnswire-a-records","dnswire-aaaa-records","dnswire-mx-records","dnswire-txt-records","dnswire-size-summary","dnswire-validate","dnswire-sha256"]
HTTP=[
"http1-start-line","http1-method","http1-target","http1-status","http1-version","http1-headers","http1-header-names","http1-content-type","http1-content-length","http1-host","http1-user-agent","http1-body-size","http1-cookie-names","http1-query-params","http1-summary"]
H2=[
"h2-frame-list","h2-frame-count","h2-frame-types","h2-stream-ids","h2-frame-flags","h2-payload-sizes","h2-settings","h2-window-updates","h2-ping-values","h2-goaway","h2-rst-stream","h2-priority","h2-data-bytes","h2-header-block-bytes","h2-validate"]
WS=[
"wsframe-list","wsframe-count","wsframe-opcodes","wsframe-fin-count","wsframe-masked-count","wsframe-payload-sizes","wsframe-text","wsframe-binary-bytes","wsframe-close-codes","wsframe-ping-count","wsframe-pong-count","wsframe-fragment-count","wsframe-mask-keys","wsframe-validate","wsframe-summary"]
COMMANDS=DNS+HTTP+H2+WS
assert len(COMMANDS)==67 and len(set(COMMANDS))==67

def emit(x):
    if isinstance(x,(dict,list,tuple,Counter)):print(json.dumps(x,indent=2,ensure_ascii=False,default=str))
    else:print(x)
def die(s,c=2):print(s,file=sys.stderr);raise SystemExit(c)
def readb(a):
    if not a:return sys.stdin.buffer.read()
    p=P(a[0]);return p.read_bytes() if p.exists() and p.is_file() else bytes.fromhex(a[0].removeprefix("0x"))
def sha(b):return hashlib.sha256(b).hexdigest()

TYPE_NAMES={1:"A",2:"NS",5:"CNAME",6:"SOA",12:"PTR",15:"MX",16:"TXT",28:"AAAA",33:"SRV",41:"OPT",64:"SVCB",65:"HTTPS"}

def dns_name(b,p,seen=None):
    seen=set() if seen is None else seen
    labels=[];jump_end=None
    while True:
        if p>=len(b):die("truncated DNS name")
        n=b[p]
        if n==0:
            p+=1
            return ".".join(labels) or ".", (jump_end if jump_end is not None else p)
        if n&0xc0==0xc0:
            if p+1>=len(b):die("truncated DNS pointer")
            off=((n&0x3f)<<8)|b[p+1]
            if off in seen:die("DNS compression loop")
            seen.add(off)
            sub,_=dns_name(b,off,seen)
            if sub!=".":labels.extend(sub.split("."))
            if jump_end is None:jump_end=p+2
            return ".".join(labels) or ".",jump_end
        if n&0xc0:die("invalid DNS label")
        p+=1
        if p+n>len(b):die("truncated DNS label")
        labels.append(b[p:p+n].decode("ascii",errors="replace"));p+=n

def rr_rdata(b,typ,rstart,rdlen):
    r=b[rstart:rstart+rdlen]
    try:
        if typ==1 and len(r)==4:return str(ipaddress.IPv4Address(r))
        if typ==28 and len(r)==16:return str(ipaddress.IPv6Address(r))
        if typ in (2,5,12):
            n,_=dns_name(b,rstart);return n
        if typ==15 and len(r)>=3:
            pref=struct.unpack(">H",r[:2])[0];n,_=dns_name(b,rstart+2);return {"preference":pref,"exchange":n}
        if typ==16:
            vals=[];p=0
            while p<len(r):
                n=r[p];p+=1
                if p+n>len(r):break
                vals.append(r[p:p+n].decode(errors="replace"));p+=n
            return vals
    except SystemExit:pass
    return r.hex()

def parse_dns(b):
    if len(b)<12:die("DNS packet too short")
    ident,flags,qd,an,ns,ar=struct.unpack(">HHHHHH",b[:12]);p=12
    qs=[]
    for _ in range(qd):
        name,p=dns_name(b,p)
        if p+4>len(b):die("truncated DNS question")
        typ,cls=struct.unpack(">HH",b[p:p+4]);p+=4
        qs.append({"name":name,"type":typ,"type_name":TYPE_NAMES.get(typ,str(typ)),"class":cls})
    def rrs(count):
        nonlocal p
        out=[]
        for _ in range(count):
            name,p=dns_name(b,p)
            if p+10>len(b):die("truncated DNS RR")
            typ,cls,ttl,rdlen=struct.unpack(">HHIH",b[p:p+10]);p+=10
            if p+rdlen>len(b):die("truncated DNS RDATA")
            val=rr_rdata(b,typ,p,rdlen);out.append({"name":name,"type":typ,"type_name":TYPE_NAMES.get(typ,str(typ)),"class":cls,"ttl":ttl,"rdlength":rdlen,"value":val})
            p+=rdlen
        return out
    ans=rrs(an);auth=rrs(ns);add=rrs(ar)
    return {"id":ident,"flags":flags,"qd":qd,"an":an,"ns":ns,"ar":ar,"questions":qs,"answers":ans,"authorities":auth,"additionals":add,"parsed_bytes":p}

def dns(cmd,a):
    b=readb(a);d=parse_dns(b);op=cmd.removeprefix("dnswire-");flags=d["flags"]
    if op=="id":print(d["id"]);return
    if op=="flags":emit({"raw":flags,"qr":bool(flags&0x8000),"aa":bool(flags&0x0400),"tc":bool(flags&0x0200),"rd":bool(flags&0x0100),"ra":bool(flags&0x0080),"ad":bool(flags&0x0020),"cd":bool(flags&0x0010)});return
    if op=="opcode":print((flags>>11)&15);return
    if op=="rcode":print(flags&15);return
    if op=="counts":emit({"questions":d["qd"],"answers":d["an"],"authorities":d["ns"],"additionals":d["ar"]});return
    if op=="questions":emit(d["questions"]);return
    if op=="qnames":emit([x["name"] for x in d["questions"]]);return
    if op=="qtypes":emit([x["type_name"] for x in d["questions"]]);return
    if op=="answers":emit(d["answers"]);return
    if op=="answer-types":emit([x["type_name"] for x in d["answers"]]);return
    if op=="answer-ttls":emit([x["ttl"] for x in d["answers"]]);return
    if op=="authorities":emit(d["authorities"]);return
    if op=="additionals":emit(d["additionals"]);return
    allrr=d["answers"]+d["authorities"]+d["additionals"]
    if op=="nameservers":emit([x["value"] for x in allrr if x["type"]==2]);return
    if op=="cnames":emit([x["value"] for x in allrr if x["type"]==5]);return
    if op=="a-records":emit([x["value"] for x in allrr if x["type"]==1]);return
    if op=="aaaa-records":emit([x["value"] for x in allrr if x["type"]==28]);return
    if op=="mx-records":emit([x["value"] for x in allrr if x["type"]==15]);return
    if op=="txt-records":emit([x["value"] for x in allrr if x["type"]==16]);return
    if op=="size-summary":emit({"bytes":len(b),"parsed_bytes":d["parsed_bytes"],"questions":d["qd"],"rrs":d["an"]+d["ns"]+d["ar"]});return
    if op=="validate":emit({"valid":d["parsed_bytes"]<=len(b),"trailing_bytes":len(b)-d["parsed_bytes"]});return
    if op=="sha256":print(sha(b));return

def parse_http(b):
    sep=b"\r\n\r\n";i=b.find(sep);sl=4
    if i<0:i=b.find(b"\n\n");sl=2
    if i<0:head=b;body=b""
    else:head=b[:i];body=b[i+sl:]
    lines=head.decode("iso-8859-1",errors="replace").replace("\r\n","\n").split("\n")
    start=lines[0] if lines else ""
    headers=[];cur=None
    for line in lines[1:]:
        if line.startswith((" ","\t")) and cur is not None:
            headers[-1]=(headers[-1][0],headers[-1][1]+" "+line.strip());continue
        if ":" in line:
            k,v=line.split(":",1);headers.append((k.strip(),v.strip()));cur=k
    hdict={}
    for k,v in headers:hdict.setdefault(k.lower(),[]).append(v)
    req=re.match(r"^([A-Z][A-Z0-9!#$%&'*+.^_|~-]*)\s+(\S+)\s+(HTTP/\d(?:\.\d)?)$",start)
    res=re.match(r"^(HTTP/\d(?:\.\d)?)\s+(\d{3})(?:\s+(.*))?$",start)
    return {"start":start,"headers":headers,"hdict":hdict,"body":body,"request":req.groups() if req else None,"response":res.groups() if res else None}

def http1(cmd,a):
    b=readb(a);h=parse_http(b);op=cmd.removeprefix("http1-")
    if op=="start-line":print(h["start"]);return
    if op=="method":print(h["request"][0] if h["request"] else "");return
    if op=="target":print(h["request"][1] if h["request"] else "");return
    if op=="status":print(h["response"][1] if h["response"] else "");return
    if op=="version":print(h["request"][2] if h["request"] else h["response"][0] if h["response"] else "");return
    if op=="headers":emit([{"name":k,"value":v} for k,v in h["headers"]]);return
    if op=="header-names":emit([k for k,_ in h["headers"]]);return
    get=lambda k:(h["hdict"].get(k,[""])[0])
    if op=="content-type":print(get("content-type"));return
    if op=="content-length":print(get("content-length"));return
    if op=="host":print(get("host"));return
    if op=="user-agent":print(get("user-agent"));return
    if op=="body-size":print(len(h["body"]));return
    if op=="cookie-names":
        vals=h["hdict"].get("cookie",[]);names=[]
        for v in vals:names += [x.split("=",1)[0].strip() for x in v.split(";") if "=" in x]
        emit(names);return
    if op=="query-params":
        target=h["request"][1] if h["request"] else "";emit(urllib.parse.parse_qs(urllib.parse.urlsplit(target).query,keep_blank_values=True));return
    if op=="summary":emit({"start_line":h["start"],"headers":len(h["headers"]),"body_bytes":len(h["body"]),"request":bool(h["request"]),"response":bool(h["response"])});return

H2_TYPES={0:"DATA",1:"HEADERS",2:"PRIORITY",3:"RST_STREAM",4:"SETTINGS",5:"PUSH_PROMISE",6:"PING",7:"GOAWAY",8:"WINDOW_UPDATE",9:"CONTINUATION"}
def parse_h2(b):
    p=0;out=[];pre=b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
    if b.startswith(pre):p=len(pre)
    while p<len(b):
        if p+9>len(b):die("truncated HTTP/2 frame header")
        n=int.from_bytes(b[p:p+3],"big");typ=b[p+3];flags=b[p+4];sid=int.from_bytes(b[p+5:p+9],"big")&0x7fffffff;start=p;p+=9
        if p+n>len(b):die("truncated HTTP/2 payload")
        payload=b[p:p+n];p+=n
        out.append({"offset":start,"length":n,"type":typ,"type_name":H2_TYPES.get(typ,str(typ)),"flags":flags,"stream_id":sid,"payload":payload})
    return out

def h2(cmd,a):
    b=readb(a);fs=parse_h2(b);op=cmd.removeprefix("h2-");pub=[{k:v for k,v in x.items() if k!="payload"} for x in fs]
    if op=="frame-list":emit(pub);return
    if op=="frame-count":print(len(fs));return
    if op=="frame-types":emit([x["type_name"] for x in fs]);return
    if op=="stream-ids":emit([x["stream_id"] for x in fs]);return
    if op=="frame-flags":emit([x["flags"] for x in fs]);return
    if op=="payload-sizes":emit([x["length"] for x in fs]);return
    if op=="settings":
        rows=[]
        for f in fs:
            if f["type"]==4:
                p=f["payload"]
                if len(p)%6:continue
                for i in range(0,len(p),6):rows.append({"id":int.from_bytes(p[i:i+2],"big"),"value":int.from_bytes(p[i+2:i+6],"big")})
        emit(rows);return
    if op=="window-updates":emit([int.from_bytes(f["payload"][:4],"big")&0x7fffffff for f in fs if f["type"]==8 and len(f["payload"])>=4]);return
    if op=="ping-values":emit([f["payload"].hex() for f in fs if f["type"]==6]);return
    if op=="goaway":
        rows=[]
        for f in fs:
            if f["type"]==7 and len(f["payload"])>=8:rows.append({"last_stream_id":int.from_bytes(f["payload"][:4],"big")&0x7fffffff,"error_code":int.from_bytes(f["payload"][4:8],"big"),"debug":f["payload"][8:].hex()})
        emit(rows);return
    if op=="rst-stream":emit([int.from_bytes(f["payload"][:4],"big") for f in fs if f["type"]==3 and len(f["payload"])>=4]);return
    if op=="priority":
        rows=[]
        for f in fs:
            if f["type"]==2 and len(f["payload"])>=5:
                dep=int.from_bytes(f["payload"][:4],"big");rows.append({"exclusive":bool(dep&0x80000000),"dependency":dep&0x7fffffff,"weight":f["payload"][4]+1})
        emit(rows);return
    if op=="data-bytes":print(sum(f["length"] for f in fs if f["type"]==0));return
    if op=="header-block-bytes":print(sum(f["length"] for f in fs if f["type"] in (1,9)));return
    if op=="validate":
        bad=[]
        for i,f in enumerate(fs):
            if f["type"]==4 and f["stream_id"]!=0:bad.append(i)
            if f["type"]==6 and (f["stream_id"]!=0 or f["length"]!=8):bad.append(i)
        emit({"valid":not bad,"frames":len(fs),"bad_indexes":sorted(set(bad))});return

WS_NAMES={0:"continuation",1:"text",2:"binary",8:"close",9:"ping",10:"pong"}
def parse_ws(b):
    p=0;out=[]
    while p<len(b):
        start=p
        if p+2>len(b):die("truncated WebSocket header")
        a,b2=b[p],b[p+1];p+=2;fin=bool(a&0x80);rsv=(a>>4)&7;opcode=a&15;masked=bool(b2&0x80);n=b2&127
        if n==126:
            if p+2>len(b):die("truncated ws len16")
            n=int.from_bytes(b[p:p+2],"big");p+=2
        elif n==127:
            if p+8>len(b):die("truncated ws len64")
            n=int.from_bytes(b[p:p+8],"big");p+=8
        mask=None
        if masked:
            if p+4>len(b):die("truncated ws mask")
            mask=b[p:p+4];p+=4
        if p+n>len(b):die("truncated ws payload")
        payload=bytearray(b[p:p+n]);p+=n
        if mask:
            for i in range(len(payload)):payload[i]^=mask[i%4]
        out.append({"offset":start,"fin":fin,"rsv":rsv,"opcode":opcode,"opcode_name":WS_NAMES.get(opcode,str(opcode)),"masked":masked,"payload_len":n,"mask":mask.hex() if mask else None,"payload":bytes(payload)})
    return out

def ws(cmd,a):
    b=readb(a);fs=parse_ws(b);op=cmd.removeprefix("wsframe-");pub=[{k:v for k,v in x.items() if k!="payload"} for x in fs]
    if op=="list":emit(pub);return
    if op=="count":print(len(fs));return
    if op=="opcodes":emit([x["opcode_name"] for x in fs]);return
    if op=="fin-count":print(sum(x["fin"] for x in fs));return
    if op=="masked-count":print(sum(x["masked"] for x in fs));return
    if op=="payload-sizes":emit([x["payload_len"] for x in fs]);return
    if op=="text":emit([x["payload"].decode("utf-8",errors="replace") for x in fs if x["opcode"]==1]);return
    if op=="binary-bytes":print(sum(x["payload_len"] for x in fs if x["opcode"]==2));return
    if op=="close-codes":emit([int.from_bytes(x["payload"][:2],"big") for x in fs if x["opcode"]==8 and len(x["payload"])>=2]);return
    if op=="ping-count":print(sum(x["opcode"]==9 for x in fs));return
    if op=="pong-count":print(sum(x["opcode"]==10 for x in fs));return
    if op=="fragment-count":print(sum(not x["fin"] or x["opcode"]==0 for x in fs));return
    if op=="mask-keys":emit([x["mask"] for x in fs if x["mask"]]);return
    if op=="validate":
        bad=[i for i,x in enumerate(fs) if x["rsv"]!=0 or (x["opcode"]>=8 and (not x["fin"] or x["payload_len"]>125))]
        emit({"valid":not bad,"frames":len(fs),"bad_indexes":bad});return
    if op=="summary":emit({"frames":len(fs),"bytes":len(b),"opcodes":Counter(x["opcode_name"] for x in fs),"masked":sum(x["masked"] for x in fs)});return

def main():
    cmd=P(sys.argv[0]).name;a=sys.argv[1:]
    if cmd not in COMMANDS:
        if a and a[0] in COMMANDS:cmd=a.pop(0)
        elif not a or a[0] in ("-h","--help"):
            print("Shard 32 — DNS, HTTP/1, HTTP/2 and WebSocket wire utilities");print("\n".join(COMMANDS));return
        else:die("unknown command")
    if a and a[0] in ("-h","--help"):print(cmd+" — functional shard 32 utility");return
    if cmd in DNS:dns(cmd,a)
    elif cmd in HTTP:http1(cmd,a)
    elif cmd in H2:h2(cmd,a)
    else:ws(cmd,a)
if __name__=="__main__":main()
