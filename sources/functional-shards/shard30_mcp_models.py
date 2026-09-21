#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,struct,sys
from collections import Counter
from pathlib import Path
P=Path

MCP=[
"mcp-jsonrpc-validate","mcp-jsonrpc-method","mcp-jsonrpc-id","mcp-jsonrpc-error","mcp-jsonrpc-result","mcp-initialize-info","mcp-capabilities","mcp-protocol-version","mcp-tools-list","mcp-tool-names","mcp-tool-schema","mcp-tool-call","mcp-resources-list","mcp-resource-uris","mcp-prompts-list","mcp-prompt-names","mcp-roots-list","mcp-sampling-request","mcp-elicitation-request","mcp-logging-message","mcp-progress-notification","mcp-cancel-notification","mcp-task-detect","mcp-task-status","mcp-task-id","mcp-task-result","mcp-extension-list","mcp-session-header-hints","mcp-cache-header-hints","mcp-auth-header-hints","mcp-batch-count","mcp-message-direction","mcp-content-types","mcp-text-content","mcp-image-content","mcp-resource-content"]
GGUF=[
"gguf-magic-check","gguf-version","gguf-tensor-count","gguf-kv-count","gguf-metadata-keys","gguf-metadata-summary","gguf-architecture","gguf-model-name","gguf-alignment","gguf-tensor-names","gguf-tensor-dims","gguf-tensor-types","gguf-tensor-offsets","gguf-data-offset","gguf-file-sha256","gguf-header-size"]
SAFE=[
"safetensors-header-size","safetensors-header-json","safetensors-tensor-names","safetensors-tensor-count","safetensors-dtypes","safetensors-shapes","safetensors-offsets","safetensors-metadata","safetensors-data-size","safetensors-gap-check","safetensors-overlap-check","safetensors-range-check","safetensors-file-sha256","safetensors-summary"]
COMMANDS=MCP+GGUF+SAFE
assert len(COMMANDS)==66 and len(set(COMMANDS))==66

def emit(x):
    if isinstance(x,(dict,list,tuple,Counter)):print(json.dumps(x,indent=2,ensure_ascii=False,default=str))
    else:print(x)
def die(s,c=2):print(s,file=sys.stderr);raise SystemExit(c)
def loadj(arg):
    p=P(arg)
    if p.exists() and p.is_file():
        s=p.read_text(errors="replace").strip()
    else:s=arg
    try:return json.loads(s)
    except:
        rows=[json.loads(x) for x in s.splitlines() if x.strip()]
        return rows

def pick_messages(x):
    return x if isinstance(x,list) else [x]

def find_content(x,typ):
    out=[]
    def rec(v):
        if isinstance(v,dict):
            if v.get("type")==typ:out.append(v)
            for q in v.values():rec(q)
        elif isinstance(v,list):
            for q in v:rec(q)
    rec(x);return out

def mcp(cmd,a):
    if not a:die("MCP JSON message/file required")
    op=cmd.removeprefix("mcp-");d=loadj(a[0]);msgs=pick_messages(d)
    first=msgs[0] if msgs else {}
    if op=="jsonrpc-validate":
        bad=[]
        for i,m in enumerate(msgs):
            if not isinstance(m,dict) or m.get("jsonrpc")!="2.0" or not any(k in m for k in ("method","result","error")):bad.append(i)
        emit({"valid":not bad,"messages":len(msgs),"bad_indexes":bad});return
    if op=="jsonrpc-method":emit([m.get("method") for m in msgs if isinstance(m,dict) and m.get("method")]);return
    if op=="jsonrpc-id":emit([m.get("id") for m in msgs if isinstance(m,dict) and "id" in m]);return
    if op=="jsonrpc-error":emit([m.get("error") for m in msgs if isinstance(m,dict) and "error" in m]);return
    if op=="jsonrpc-result":emit([m.get("result") for m in msgs if isinstance(m,dict) and "result" in m]);return
    if op=="initialize-info":
        r=first.get("result",first.get("params",{})) if isinstance(first,dict) else {};emit({"protocolVersion":r.get("protocolVersion"),"capabilities":r.get("capabilities"),"serverInfo":r.get("serverInfo"),"clientInfo":r.get("clientInfo")});return
    if op=="capabilities":
        out=[]
        for m in msgs:
            if isinstance(m,dict):
                q=m.get("result",m.get("params",{}))
                if isinstance(q,dict) and "capabilities" in q:out.append(q["capabilities"])
        emit(out);return
    if op=="protocol-version":
        vals=[]
        for m in msgs:
            if isinstance(m,dict):
                for q in (m.get("result"),m.get("params")):
                    if isinstance(q,dict) and q.get("protocolVersion"):vals.append(q["protocolVersion"])
        emit(vals);return
    if op=="tools-list":
        out=[]
        for m in msgs:
            r=m.get("result",{}) if isinstance(m,dict) else {}
            if isinstance(r,dict):out+=r.get("tools",[])
        emit(out);return
    if op=="tool-names":
        tools=[]
        for m in msgs:
            r=m.get("result",{}) if isinstance(m,dict) else {}
            if isinstance(r,dict):tools+=r.get("tools",[])
        emit([x.get("name") for x in tools if isinstance(x,dict)]);return
    if op=="tool-schema":
        name=a[1] if len(a)>1 else None;tools=[]
        for m in msgs:
            r=m.get("result",{}) if isinstance(m,dict) else {}
            if isinstance(r,dict):tools+=r.get("tools",[])
        emit([{"name":x.get("name"),"inputSchema":x.get("inputSchema"),"outputSchema":x.get("outputSchema")} for x in tools if not name or x.get("name")==name]);return
    if op=="tool-call":
        emit([m for m in msgs if isinstance(m,dict) and m.get("method")=="tools/call"]);return
    if op=="resources-list":
        out=[]
        for m in msgs:
            r=m.get("result",{}) if isinstance(m,dict) else {}
            if isinstance(r,dict):out+=r.get("resources",[])
        emit(out);return
    if op=="resource-uris":
        rows=[]
        for m in msgs:
            r=m.get("result",{}) if isinstance(m,dict) else {}
            if isinstance(r,dict):rows+=r.get("resources",[])
        emit([x.get("uri") for x in rows if isinstance(x,dict) and x.get("uri")]);return
    if op=="prompts-list":
        out=[]
        for m in msgs:
            r=m.get("result",{}) if isinstance(m,dict) else {}
            if isinstance(r,dict):out+=r.get("prompts",[])
        emit(out);return
    if op=="prompt-names":
        rows=[]
        for m in msgs:
            r=m.get("result",{}) if isinstance(m,dict) else {}
            if isinstance(r,dict):rows+=r.get("prompts",[])
        emit([x.get("name") for x in rows if isinstance(x,dict)]);return
    methods={
      "roots-list":"roots/list","sampling-request":"sampling/createMessage","elicitation-request":"elicitation/create","logging-message":"notifications/message","progress-notification":"notifications/progress","cancel-notification":"notifications/cancelled"
    }
    if op in methods:emit([m for m in msgs if isinstance(m,dict) and m.get("method")==methods[op]]);return
    if op=="task-detect":
        hits=[]
        def rec(v):
            if isinstance(v,dict):
                if v.get("resultType")=="task" or "taskId" in v or ("status" in v and "task" in str(v).lower()):hits.append(v)
                for q in v.values():rec(q)
            elif isinstance(v,list):
                for q in v:rec(q)
        rec(d);emit({"detected":bool(hits),"matches":hits});return
    if op in ("task-status","task-id","task-result"):
        keys={"task-status":"status","task-id":"taskId","task-result":"result"};key=keys[op];vals=[]
        def rec(v):
            if isinstance(v,dict):
                if key in v:vals.append(v[key])
                for q in v.values():rec(q)
            elif isinstance(v,list):
                for q in v:rec(q)
        rec(d);emit(vals);return
    if op=="extension-list":
        vals=[]
        def rec(v):
            if isinstance(v,dict):
                for k,q in v.items():
                    if k in ("extensions","experimental") and isinstance(q,(dict,list)):vals.append(q)
                    rec(q)
            elif isinstance(v,list):
                for q in v:rec(q)
        rec(d);emit(vals);return
    if op.endswith("header-hints"):
        headers=first.get("headers",first) if isinstance(first,dict) else {}
        if not isinstance(headers,dict):headers={}
        terms={"session-header-hints":("session","mcp"),"cache-header-hints":("cache","etag","last-modified"),"auth-header-hints":("authorization","authenticate","oauth","token")}[op]
        emit({k:v for k,v in headers.items() if any(t in k.lower() for t in terms)});return
    if op=="batch-count":print(len(msgs));return
    if op=="message-direction":
        rows=[]
        for m in msgs:
            if not isinstance(m,dict):continue
            kind="request" if "method" in m and "id" in m else "notification" if "method" in m else "response" if "result" in m or "error" in m else "unknown"
            rows.append(kind)
        emit(rows);return
    if op=="content-types":
        vals=[]
        def rec(v):
            if isinstance(v,dict):
                if isinstance(v.get("type"),str):vals.append(v["type"])
                for q in v.values():rec(q)
            elif isinstance(v,list):
                for q in v:rec(q)
        rec(d);emit(Counter(vals));return
    if op in ("text-content","image-content","resource-content"):
        emit(find_content(d,op.split("-")[0]));return

class Reader:
    def __init__(self,b):self.b=b;self.p=0
    def need(self,n):
        if self.p+n>len(self.b):die("truncated GGUF")
    def read(self,n):self.need(n);q=self.b[self.p:self.p+n];self.p+=n;return q
    def u8(self):return self.read(1)[0]
    def i8(self):return struct.unpack("<b",self.read(1))[0]
    def u16(self):return struct.unpack("<H",self.read(2))[0]
    def i16(self):return struct.unpack("<h",self.read(2))[0]
    def u32(self):return struct.unpack("<I",self.read(4))[0]
    def i32(self):return struct.unpack("<i",self.read(4))[0]
    def u64(self):return struct.unpack("<Q",self.read(8))[0]
    def i64(self):return struct.unpack("<q",self.read(8))[0]
    def f32(self):return struct.unpack("<f",self.read(4))[0]
    def f64(self):return struct.unpack("<d",self.read(8))[0]
    def string(self):
        n=self.u64()
        if n>100_000_000:die("GGUF string too large")
        return self.read(n).decode("utf-8",errors="replace")

def gguf_val(r,t):
    if t==0:return r.u8()
    if t==1:return r.i8()
    if t==2:return r.u16()
    if t==3:return r.i16()
    if t==4:return r.u32()
    if t==5:return r.i32()
    if t==6:return r.f32()
    if t==7:return bool(r.u8())
    if t==8:return r.string()
    if t==9:
        st=r.u32();n=r.u64()
        if n>1_000_000:die("GGUF array too large")
        return [gguf_val(r,st) for _ in range(n)]
    if t==10:return r.u64()
    if t==11:return r.i64()
    if t==12:return r.f64()
    die("unknown GGUF metadata type "+str(t))

def parse_gguf(path):
    b=P(path).read_bytes();r=Reader(b)
    magic=r.read(4)
    if magic!=b"GGUF":die("not a GGUF file")
    version=r.u32();nt=r.u64();nk=r.u64()
    if nt>10_000_000 or nk>10_000_000:die("unreasonable GGUF counts")
    meta={};meta_types={}
    for _ in range(nk):
        k=r.string();t=r.u32();meta[k]=gguf_val(r,t);meta_types[k]=t
    tensors=[]
    for _ in range(nt):
        name=r.string();nd=r.u32()
        if nd>16:die("GGUF tensor dimension count too large")
        dims=[r.u64() for _ in range(nd)];typ=r.u32();off=r.u64()
        tensors.append({"name":name,"dims":dims,"type":typ,"offset":off})
    header_end=r.p;alignment=meta.get("general.alignment",32)
    if not isinstance(alignment,int) or alignment<=0:alignment=32
    data_offset=((header_end+alignment-1)//alignment)*alignment
    return {"bytes":b,"version":version,"tensor_count":nt,"kv_count":nk,"metadata":meta,"metadata_types":meta_types,"tensors":tensors,"header_end":header_end,"alignment":alignment,"data_offset":data_offset}

def gguf(cmd,a):
    if not a:die("GGUF path required")
    op=cmd.removeprefix("gguf-");p=P(a[0]);raw=p.read_bytes()
    if op=="magic-check":emit({"valid":raw[:4]==b"GGUF","magic":raw[:4].decode(errors="replace")});return
    g=parse_gguf(p)
    if op=="version":print(g["version"]);return
    if op=="tensor-count":print(g["tensor_count"]);return
    if op=="kv-count":print(g["kv_count"]);return
    if op=="metadata-keys":emit(list(g["metadata"].keys()));return
    if op=="metadata-summary":emit(g["metadata"]);return
    if op=="architecture":emit(g["metadata"].get("general.architecture"));return
    if op=="model-name":emit(g["metadata"].get("general.name"));return
    if op=="alignment":print(g["alignment"]);return
    if op=="tensor-names":emit([x["name"] for x in g["tensors"]]);return
    if op=="tensor-dims":emit({x["name"]:x["dims"] for x in g["tensors"]});return
    if op=="tensor-types":emit({x["name"]:x["type"] for x in g["tensors"]});return
    if op=="tensor-offsets":emit({x["name"]:x["offset"] for x in g["tensors"]});return
    if op=="data-offset":print(g["data_offset"]);return
    if op=="file-sha256":print(hashlib.sha256(raw).hexdigest());return
    if op=="header-size":emit({"metadata_and_tensor_header_bytes":g["header_end"],"aligned_data_offset":g["data_offset"]});return

def safe_header(path):
    p=P(path);b=p.read_bytes()
    if len(b)<8:die("truncated safetensors file")
    n=struct.unpack("<Q",b[:8])[0]
    if n>100_000_000 or 8+n>len(b):die("invalid safetensors header size")
    try:h=json.loads(b[8:8+n].decode("utf-8"))
    except Exception as e:die("invalid safetensors JSON header: "+str(e))
    tensors={k:v for k,v in h.items() if k!="__metadata__" and isinstance(v,dict)}
    data_len=len(b)-(8+n)
    return b,n,h,tensors,data_len

def safe(cmd,a):
    if not a:die("safetensors path required")
    op=cmd.removeprefix("safetensors-");b,n,h,tensors,data_len=safe_header(a[0])
    if op=="header-size":print(n);return
    if op=="header-json":emit(h);return
    if op=="tensor-names":emit(list(tensors));return
    if op=="tensor-count":print(len(tensors));return
    if op=="dtypes":emit({k:v.get("dtype") for k,v in tensors.items()});return
    if op=="shapes":emit({k:v.get("shape") for k,v in tensors.items()});return
    if op=="offsets":emit({k:v.get("data_offsets") for k,v in tensors.items()});return
    if op=="metadata":emit(h.get("__metadata__",{}));return
    if op=="data-size":print(data_len);return
    ranges=[]
    for k,v in tensors.items():
        o=v.get("data_offsets")
        if isinstance(o,list) and len(o)==2 and all(isinstance(x,int) for x in o):ranges.append((o[0],o[1],k))
    ranges.sort()
    if op=="gap-check":
        gaps=[];cur=0
        for s,e,k in ranges:
            if s>cur:gaps.append([cur,s])
            cur=max(cur,e)
        if cur<data_len:gaps.append([cur,data_len])
        emit({"has_gaps":bool(gaps),"gaps":gaps});return
    if op=="overlap-check":
        overlaps=[]
        for i in range(1,len(ranges)):
            if ranges[i][0]<ranges[i-1][1]:overlaps.append([ranges[i-1][2],ranges[i][2]])
        emit({"has_overlaps":bool(overlaps),"overlaps":overlaps});return
    if op=="range-check":
        bad=[k for s,e,k in ranges if s<0 or e<s or e>data_len];emit({"valid":not bad,"bad":bad,"data_bytes":data_len});return
    if op=="file-sha256":print(hashlib.sha256(b).hexdigest());return
    if op=="summary":
        emit({"header_bytes":n,"tensor_count":len(tensors),"data_bytes":data_len,"metadata":h.get("__metadata__",{}),"dtypes":Counter(str(v.get("dtype")) for v in tensors.values())});return

def main():
    cmd=P(sys.argv[0]).name;a=sys.argv[1:]
    if cmd not in COMMANDS:
        if a and a[0] in COMMANDS:cmd=a.pop(0)
        elif not a or a[0] in ("-h","--help"):
            print("Shard 30 — MCP 2026 and AI model artifact utilities");print("\n".join(COMMANDS));return
        else:die("unknown command")
    if a and a[0] in ("-h","--help"):print(cmd+" — functional shard 30 utility");return
    if cmd in MCP:mcp(cmd,a)
    elif cmd in GGUF:gguf(cmd,a)
    else:safe(cmd,a)
if __name__=="__main__":main()
