#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,math,re,struct,sys
from collections import Counter
from pathlib import Path
P=Path

PROTO=[
"protobuf-varint-decode","protobuf-varint-encode","protobuf-zigzag-decode","protobuf-zigzag-encode","protobuf-tag-decode","protobuf-tag-encode","protobuf-field-list","protobuf-field-count","protobuf-field-numbers","protobuf-wire-types","protobuf-length-fields","protobuf-length-strings","protobuf-length-hex","protobuf-fixed32-values","protobuf-fixed64-values","protobuf-varint-values","protobuf-size-summary","protobuf-validate","protobuf-depth-lite","protobuf-unknown-fields","protobuf-field-frequency","protobuf-first-field","protobuf-last-field","protobuf-sha256","protobuf-hexdump"]
CBOR=[
"cbor-decode","cbor-top-type","cbor-map-keys","cbor-array-length","cbor-item-count","cbor-depth","cbor-tags","cbor-text-values","cbor-byte-lengths","cbor-number-values","cbor-validate","cbor-sha256","cbor-hexdump","cbor-summary"]
MSGPACK=[
"msgpack-decode","msgpack-top-type","msgpack-map-keys","msgpack-array-length","msgpack-item-count","msgpack-depth","msgpack-string-values","msgpack-bin-lengths","msgpack-number-values","msgpack-validate","msgpack-sha256","msgpack-hexdump","msgpack-summary","msgpack-type-frequency"]
AVRO=[
"avro-magic-check","avro-metadata","avro-schema","avro-codec","avro-sync-marker","avro-block-counts","avro-block-sizes","avro-block-offsets","avro-header-size","avro-validate-basic","avro-sha256","avro-file-size","avro-metadata-keys","avro-summary"]
COMMANDS=PROTO+CBOR+MSGPACK+AVRO
assert len(COMMANDS)==67 and len(set(COMMANDS))==67

def emit(x):
    if isinstance(x,(dict,list,tuple,Counter)): print(json.dumps(x,indent=2,ensure_ascii=False,default=str))
    else: print(x)

def die(s,c=2): print(s,file=sys.stderr); raise SystemExit(c)
def readarg(a):
    if not a: return sys.stdin.buffer.read()
    p=P(a[0]); return p.read_bytes() if p.exists() and p.is_file() else bytes.fromhex(a[0].removeprefix("0x"))
def sha(b): return hashlib.sha256(b).hexdigest()

def uvarint(b,p=0):
    n=0;shift=0;start=p
    while p<len(b) and shift<70:
        x=b[p];p+=1;n|=(x&0x7f)<<shift
        if not x&0x80:return n,p
        shift+=7
    die("invalid/truncated varint")
def svarint(b,p=0):
    u,p=uvarint(b,p);return (u>>1)^-(u&1),p
def putvarint(n):
    n=int(n)
    if n<0: die("unsigned varint must be >=0")
    out=bytearray()
    while True:
        x=n&0x7f;n>>=7;out.append(x|(0x80 if n else 0))
        if not n:return bytes(out)

def proto_fields(b):
    out=[];p=0
    while p<len(b):
        start=p;tag,p=uvarint(b,p);num=tag>>3;wire=tag&7
        row={"field":num,"wire":wire,"offset":start}
        if num==0:die("protobuf field number 0")
        if wire==0:
            v,p=uvarint(b,p);row["value"]=v;row["end"]=p
        elif wire==1:
            if p+8>len(b):die("truncated fixed64")
            raw=b[p:p+8];p+=8;row["value"]=struct.unpack("<Q",raw)[0];row["raw"]=raw.hex();row["end"]=p
        elif wire==2:
            n,p=uvarint(b,p)
            if p+n>len(b):die("truncated length-delimited")
            raw=b[p:p+n];p+=n;row["length"]=n;row["raw"]=raw.hex()
            try:
                s=raw.decode("utf-8")
                if all((ord(c)>=32 or c in "\r\n\t") for c in s):row["text"]=s
            except:pass
            row["end"]=p
        elif wire==5:
            if p+4>len(b):die("truncated fixed32")
            raw=b[p:p+4];p+=4;row["value"]=struct.unpack("<I",raw)[0];row["raw"]=raw.hex();row["end"]=p
        else:die("unsupported protobuf wire type "+str(wire))
        out.append(row)
    return out

def proto_depth(raw,limit=8):
    def rec(b,d):
        if d>=limit:return d
        try:fs=proto_fields(b)
        except SystemExit:return d
        best=d
        for f in fs:
            if f["wire"]==2 and f.get("length",0)>0:
                q=bytes.fromhex(f["raw"])
                try:
                    nested=proto_fields(q)
                    if nested:best=max(best,rec(q,d+1))
                except SystemExit:pass
        return best
    return rec(raw,1)

def proto(cmd,a):
    op=cmd.removeprefix("protobuf-")
    if op in ("varint-decode","zigzag-decode"):
        if not a:die("hex bytes required")
        b=bytes.fromhex(a[0]);u,p=uvarint(b,0);print((u>>1)^-(u&1) if op.startswith("zigzag") else u);return
    if op in ("varint-encode","zigzag-encode"):
        if not a:die("integer required")
        n=int(a[0])
        if op.startswith("zigzag"):n=(n<<1)^(n>>63)
        print(putvarint(n).hex());return
    if op in ("tag-decode","tag-encode"):
        if op=="tag-decode":
            n=int(a[0],0);emit({"field":n>>3,"wire":n&7});return
        if len(a)<2:die("FIELD WIRE")
        print((int(a[0])<<3)|int(a[1]));return
    b=readarg(a);fs=proto_fields(b)
    if op=="field-list":emit(fs);return
    if op=="field-count":print(len(fs));return
    if op=="field-numbers":emit([x["field"] for x in fs]);return
    if op=="wire-types":emit([x["wire"] for x in fs]);return
    if op=="length-fields":emit([x for x in fs if x["wire"]==2]);return
    if op=="length-strings":emit([x.get("text") for x in fs if x["wire"]==2 and "text" in x]);return
    if op=="length-hex":emit([x["raw"] for x in fs if x["wire"]==2]);return
    if op=="fixed32-values":emit([x["value"] for x in fs if x["wire"]==5]);return
    if op=="fixed64-values":emit([x["value"] for x in fs if x["wire"]==1]);return
    if op=="varint-values":emit([x["value"] for x in fs if x["wire"]==0]);return
    if op=="size-summary":emit({"bytes":len(b),"fields":len(fs),"payload_bytes":sum(x.get("length",0) for x in fs if x["wire"]==2)});return
    if op=="validate":emit({"valid":True,"bytes":len(b),"fields":len(fs)});return
    if op=="depth-lite":print(proto_depth(b));return
    if op=="unknown-fields":emit(fs);return
    if op=="field-frequency":emit(Counter(str(x["field"]) for x in fs));return
    if op=="first-field":emit(fs[0] if fs else None);return
    if op=="last-field":emit(fs[-1] if fs else None);return
    if op=="sha256":print(sha(b));return
    if op=="hexdump":
        for i in range(0,len(b),16):print(f"{i:08x}  "+b[i:i+16].hex(" "))
        return

class CborReader:
    def __init__(self,b):self.b=b;self.p=0;self.tags=[]
    def need(self,n):
        if self.p+n>len(self.b):die("truncated CBOR")
    def take(self,n):self.need(n);q=self.b[self.p:self.p+n];self.p+=n;return q
    def ai(self,a):
        if a<24:return a
        if a==24:return self.take(1)[0]
        if a==25:return int.from_bytes(self.take(2),"big")
        if a==26:return int.from_bytes(self.take(4),"big")
        if a==27:return int.from_bytes(self.take(8),"big")
        if a==31:return None
        die("reserved CBOR additional info")
    def item(self):
        ib=self.take(1)[0];major=ib>>5;a=ib&31;n=self.ai(a)
        if major==0:return n
        if major==1:return -1-n
        if major==2:
            if n is None:
                out=b""
                while self.b[self.p]!=0xff:out+=self.item()
                self.p+=1;return out
            return self.take(n)
        if major==3:
            if n is None:
                out=""
                while self.b[self.p]!=0xff:out+=self.item()
                self.p+=1;return out
            return self.take(n).decode("utf-8",errors="replace")
        if major==4:
            out=[]
            if n is None:
                while self.b[self.p]!=0xff:out.append(self.item())
                self.p+=1
            else:
                for _ in range(n):out.append(self.item())
            return out
        if major==5:
            out={}
            if n is None:
                while self.b[self.p]!=0xff:
                    k=self.item();v=self.item();out[k]=v
                self.p+=1
            else:
                for _ in range(n):
                    k=self.item();v=self.item();out[k]=v
            return out
        if major==6:
            self.tags.append(n);return {"tag":n,"value":self.item()}
        if major==7:
            if a==20:return False
            if a==21:return True
            if a in (22,23):return None
            if a==25:
                try:return struct.unpack(">e",n.to_bytes(2,"big"))[0]
                except:return n
            if a==26:return struct.unpack(">f",n.to_bytes(4,"big"))[0]
            if a==27:return struct.unpack(">d",n.to_bytes(8,"big"))[0]
            if a==31:die("unexpected CBOR break")
            return n
        die("bad CBOR")

def walk(v):
    yield v
    if isinstance(v,dict):
        for k,x in v.items():yield from walk(k);yield from walk(x)
    elif isinstance(v,list):
        for x in v:yield from walk(x)
    elif isinstance(v,dict) and "tag" in v:yield from walk(v["value"])
def depth(v):
    if isinstance(v,list):return 1+max([depth(x) for x in v] or [0])
    if isinstance(v,dict):return 1+max([depth(k) for k in v.keys()]+[depth(x) for x in v.values()] or [0])
    return 1

def cbor(cmd,a):
    b=readarg(a);r=CborReader(b);v=r.item()
    if r.p!=len(b):die("trailing CBOR bytes")
    op=cmd.removeprefix("cbor-")
    if op=="decode":emit(v);return
    if op=="top-type":print(type(v).__name__);return
    if op=="map-keys":emit(list(v.keys()) if isinstance(v,dict) else []);return
    if op=="array-length":print(len(v) if isinstance(v,list) else 0);return
    vals=list(walk(v))
    if op=="item-count":print(len(vals));return
    if op=="depth":print(depth(v));return
    if op=="tags":emit(r.tags);return
    if op=="text-values":emit([x for x in vals if isinstance(x,str)]);return
    if op=="byte-lengths":emit([len(x) for x in vals if isinstance(x,(bytes,bytearray))]);return
    if op=="number-values":emit([x for x in vals if isinstance(x,(int,float)) and not isinstance(x,bool)]);return
    if op=="validate":emit({"valid":True,"bytes":len(b)});return
    if op=="sha256":print(sha(b));return
    if op=="hexdump":print(b.hex(" "));return
    if op=="summary":emit({"bytes":len(b),"top_type":type(v).__name__,"items":len(vals),"depth":depth(v),"tags":r.tags});return

class MP:
    def __init__(self,b):self.b=b;self.p=0;self.freq=Counter()
    def take(self,n):
        if self.p+n>len(self.b):die("truncated MessagePack")
        q=self.b[self.p:self.p+n];self.p+=n;return q
    def item(self):
        x=self.take(1)[0]
        if x<=0x7f:self.freq["uint"]+=1;return x
        if x>=0xe0:self.freq["int"]+=1;return x-256
        if 0xa0<=x<=0xbf:self.freq["str"]+=1;return self.take(x&31).decode(errors="replace")
        if 0x90<=x<=0x9f:self.freq["array"]+=1;return [self.item() for _ in range(x&15)]
        if 0x80<=x<=0x8f:self.freq["map"]+=1;return {self.item():self.item() for _ in range(x&15)}
        if x==0xc0:self.freq["nil"]+=1;return None
        if x in (0xc2,0xc3):self.freq["bool"]+=1;return x==0xc3
        if x in (0xc4,0xc5,0xc6):
            n=int.from_bytes(self.take({0xc4:1,0xc5:2,0xc6:4}[x]),"big");self.freq["bin"]+=1;return self.take(n)
        if x in (0xd9,0xda,0xdb):
            n=int.from_bytes(self.take({0xd9:1,0xda:2,0xdb:4}[x]),"big");self.freq["str"]+=1;return self.take(n).decode(errors="replace")
        if x in (0xdc,0xdd):
            n=int.from_bytes(self.take(2 if x==0xdc else 4),"big");self.freq["array"]+=1;return [self.item() for _ in range(n)]
        if x in (0xde,0xdf):
            n=int.from_bytes(self.take(2 if x==0xde else 4),"big");self.freq["map"]+=1;return {self.item():self.item() for _ in range(n)}
        specs={0xcc:(1,">B","uint"),0xcd:(2,">H","uint"),0xce:(4,">I","uint"),0xcf:(8,">Q","uint"),0xd0:(1,">b","int"),0xd1:(2,">h","int"),0xd2:(4,">i","int"),0xd3:(8,">q","int"),0xca:(4,">f","float"),0xcb:(8,">d","float")}
        if x in specs:
            n,fmt,t=specs[x];self.freq[t]+=1;return struct.unpack(fmt,self.take(n))[0]
        die(f"unsupported MessagePack opcode 0x{x:02x}")

def msgpack(cmd,a):
    b=readarg(a);r=MP(b);v=r.item()
    if r.p!=len(b):die("trailing MessagePack bytes")
    op=cmd.removeprefix("msgpack-");vals=list(walk(v))
    if op=="decode":emit(v);return
    if op=="top-type":print(type(v).__name__);return
    if op=="map-keys":emit(list(v.keys()) if isinstance(v,dict) else []);return
    if op=="array-length":print(len(v) if isinstance(v,list) else 0);return
    if op=="item-count":print(len(vals));return
    if op=="depth":print(depth(v));return
    if op=="string-values":emit([x for x in vals if isinstance(x,str)]);return
    if op=="bin-lengths":emit([len(x) for x in vals if isinstance(x,(bytes,bytearray))]);return
    if op=="number-values":emit([x for x in vals if isinstance(x,(int,float)) and not isinstance(x,bool)]);return
    if op=="validate":emit({"valid":True,"bytes":len(b)});return
    if op=="sha256":print(sha(b));return
    if op=="hexdump":print(b.hex(" "));return
    if op=="summary":emit({"bytes":len(b),"top_type":type(v).__name__,"items":len(vals),"depth":depth(v)});return
    if op=="type-frequency":emit(r.freq);return

def avro_long(b,p):
    u,p=uvarint(b,p);return (u>>1)^-(u&1),p
def avro_bytes(b,p):
    n,p=avro_long(b,p)
    if n<0:die("negative avro byte length")
    if p+n>len(b):die("truncated avro bytes")
    return b[p:p+n],p+n
def avro_string(b,p):
    q,p=avro_bytes(b,p);return q.decode("utf-8",errors="replace"),p

def parse_avro(path):
    b=P(path).read_bytes()
    if b[:4]!=b"Obj\x01":die("invalid Avro OCF magic")
    p=4;meta={}
    while True:
        count,p=avro_long(b,p)
        if count==0:break
        if count<0:
            count=-count;_,p=avro_long(b,p)
        for _ in range(count):
            k,p=avro_string(b,p);v,p=avro_bytes(b,p);meta[k]=v
    if p+16>len(b):die("missing Avro sync marker")
    sync=b[p:p+16];p+=16;header_end=p;blocks=[]
    while p<len(b):
        start=p
        try:count,p=avro_long(b,p);size,p=avro_long(b,p)
        except SystemExit:break
        if count<0 or size<0 or p+size+16>len(b):die("invalid Avro block")
        data_start=p;p+=size
        marker=b[p:p+16];p+=16
        blocks.append({"count":count,"size":size,"offset":start,"data_offset":data_start,"sync_ok":marker==sync})
    return b,meta,sync,header_end,blocks

def avro(cmd,a):
    if not a:die("Avro OCF path required")
    op=cmd.removeprefix("avro-");p=P(a[0]);raw=p.read_bytes()
    if op=="magic-check":emit({"valid":raw[:4]==b"Obj\x01","magic":raw[:4].hex()});return
    b,meta,sync,header,blocks=parse_avro(p)
    md={k:(v.decode(errors="replace") if k.startswith("avro.") else v.hex()) for k,v in meta.items()}
    if op=="metadata":emit(md);return
    if op=="schema":
        try:emit(json.loads(meta.get("avro.schema",b"{}")))
        except:print(meta.get("avro.schema",b"").decode(errors="replace"))
        return
    if op=="codec":print(meta.get("avro.codec",b"null").decode(errors="replace"));return
    if op=="sync-marker":print(sync.hex());return
    if op=="block-counts":emit([x["count"] for x in blocks]);return
    if op=="block-sizes":emit([x["size"] for x in blocks]);return
    if op=="block-offsets":emit([x["offset"] for x in blocks]);return
    if op=="header-size":print(header);return
    if op=="validate-basic":emit({"valid":all(x["sync_ok"] for x in blocks),"blocks":len(blocks),"metadata_keys":len(meta)});return
    if op=="sha256":print(sha(b));return
    if op=="file-size":print(len(b));return
    if op=="metadata-keys":emit(sorted(meta));return
    if op=="summary":emit({"bytes":len(b),"codec":meta.get("avro.codec",b"null").decode(errors="replace"),"blocks":len(blocks),"records":sum(x["count"] for x in blocks),"header_bytes":header});return

def main():
    cmd=P(sys.argv[0]).name;a=sys.argv[1:]
    if cmd not in COMMANDS:
        if a and a[0] in COMMANDS:cmd=a.pop(0)
        elif not a or a[0] in ("-h","--help"):
            print("Shard 31 — Protobuf, CBOR, MessagePack and Avro utilities");print("\n".join(COMMANDS));return
        else:die("unknown command")
    if a and a[0] in ("-h","--help"):print(cmd+" — functional shard 31 utility");return
    if cmd in PROTO:proto(cmd,a)
    elif cmd in CBOR:cbor(cmd,a)
    elif cmd in MSGPACK:msgpack(cmd,a)
    else:avro(cmd,a)
if __name__=="__main__":main()
