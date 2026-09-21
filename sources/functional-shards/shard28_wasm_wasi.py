#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,math,re,struct,sys
from collections import Counter
from pathlib import Path
P=Path

WASM=[
"wasm-magic-check","wasm-version","wasm-section-list","wasm-section-sizes","wasm-custom-sections","wasm-type-count","wasm-import-count","wasm-export-count","wasm-function-count","wasm-table-count","wasm-memory-count","wasm-global-count","wasm-code-count","wasm-data-count","wasm-start-function","wasm-name-section","wasm-producers-section","wasm-target-features","wasm-import-modules","wasm-export-names","wasm-memory-limits","wasm-table-limits","wasm-data-bytes","wasm-code-bytes","wasm-custom-names","wasm-section-order","wasm-section-duplicates","wasm-size-summary","wasm-sha256","wasm-entropy","wasm-hexdump","wasm-leb128-u32","wasm-leb128-i32","wasm-validate-basic","wasm-component-detect"]
WIT=[
"wit-package-name","wit-worlds","wit-interfaces","wit-functions","wit-records","wit-variants","wit-resources","wit-enums","wit-flags","wit-types","wit-use-count","wit-include-count","wit-async-functions","wit-stream-types","wit-future-types","wasi-version-hints","wasi-imports","wasi-preview1-detect","wasi-preview2-detect","wasi-preview3-hints","wasi-http-hints","wasi-cli-hints","wasi-filesystem-hints","wasi-sockets-hints","wasi-random-hints","wasi-clocks-hints","wasi-io-hints","wasi-component-hints","component-section-list","component-import-hints","component-export-hints","component-async-hints"]
COMMANDS=WASM+WIT
assert len(COMMANDS)==67 and len(set(COMMANDS))==67

CORE_SECTION_NAMES={0:"custom",1:"type",2:"import",3:"function",4:"table",5:"memory",6:"global",7:"export",8:"start",9:"element",10:"code",11:"data",12:"data-count",13:"tag"}
COMP_SECTION_NAMES={0:"custom",1:"core-module",2:"core-instance",3:"core-type",4:"component",5:"instance",6:"alias",7:"type",8:"canon",9:"start",10:"import",11:"export",12:"value"}

def emit(x):
    if isinstance(x,(dict,list,tuple,Counter)): print(json.dumps(x,indent=2,ensure_ascii=False,default=str))
    else: print(x)

def die(s,c=2): print(s,file=sys.stderr); raise SystemExit(c)

def uleb(b,pos=0,bits=64):
    n=0;shift=0;start=pos
    while pos<len(b):
        x=b[pos];pos+=1;n|=(x&0x7f)<<shift
        if not x&0x80:return n,pos
        shift+=7
        if shift>=bits+7:die("invalid unsigned LEB128")
    die("truncated unsigned LEB128")

def sleb(b,pos=0,bits=32):
    n=0;shift=0;start=pos
    while pos<len(b):
        x=b[pos];pos+=1;n|=(x&0x7f)<<shift;shift+=7
        if not x&0x80:
            if shift<bits and x&0x40:n|=-(1<<shift)
            return n,pos
        if shift>=bits+7:die("invalid signed LEB128")
    die("truncated signed LEB128")

def name(b,pos):
    n,pos=uleb(b,pos,32);end=pos+n
    if end>len(b):die("truncated wasm name")
    return b[pos:end].decode("utf-8",errors="replace"),end

def header_kind(b):
    if len(b)<8 or b[:4]!=b"\x00asm":return "invalid"
    if b[4:8]==b"\x01\x00\x00\x00":return "module"
    if b[4:8]==b"\x0d\x00\x01\x00":return "component"
    return "unknown"

def sections(b):
    kind=header_kind(b)
    if kind=="invalid":die("invalid WebAssembly magic")
    pos=8;out=[];names=CORE_SECTION_NAMES if kind=="module" else COMP_SECTION_NAMES
    while pos<len(b):
        sid=b[pos];pos+=1
        size,pos2=uleb(b,pos,32);payload_start=pos2;end=payload_start+size
        if end>len(b):die("section exceeds file")
        row={"id":sid,"name":names.get(sid,f"section-{sid}"),"offset":payload_start,"size":size,"end":end}
        if sid==0:
            try:n,_=name(b,payload_start);row["custom_name"]=n
            except SystemExit:row["custom_name"]="<invalid>"
        out.append(row);pos=end
    return kind,out

def vector_count(payload):
    try:n,_=uleb(payload,0,32);return n
    except SystemExit:return None

def sec_payload(b,row):return b[row["offset"]:row["end"]]

def core_rows(b,sid):
    kind,rows=sections(b)
    return [r for r in rows if r["id"]==sid],kind

def import_modules(payload):
    out=[];pos=0
    count,pos=uleb(payload,pos,32)
    for _ in range(count):
        mod,pos=name(payload,pos);field,pos=name(payload,pos)
        if pos>=len(payload):break
        kind=payload[pos];pos+=1;out.append(mod)
        try:
            if kind==0:_,pos=uleb(payload,pos,32)
            elif kind==1:
                if pos<len(payload):pos+=1
                flags,pos=uleb(payload,pos,32);_,pos=uleb(payload,pos,32)
                if flags&1:_,pos=uleb(payload,pos,32)
            elif kind==2:
                flags,pos=uleb(payload,pos,32);_,pos=uleb(payload,pos,32)
                if flags&1:_,pos=uleb(payload,pos,32)
            elif kind==3:
                pos+=2
            elif kind==4:
                if pos<len(payload):pos+=1
                _,pos=uleb(payload,pos,32)
        except SystemExit:break
    return out

def export_names(payload):
    out=[];pos=0
    count,pos=uleb(payload,pos,32)
    for _ in range(count):
        n,pos=name(payload,pos);out.append(n)
        if pos>=len(payload):break
        pos+=1
        try:_,pos=uleb(payload,pos,32)
        except SystemExit:break
    return out

def limits(payload,kind):
    out=[];pos=0
    count,pos=uleb(payload,pos,32)
    for _ in range(count):
        try:
            if kind=="table":
                if pos>=len(payload):break
                pos+=1
            flags,pos=uleb(payload,pos,32);minimum,pos=uleb(payload,pos,64);maximum=None
            if flags&1:maximum,pos=uleb(payload,pos,64)
            out.append({"min":minimum,"max":maximum,"flags":flags})
        except SystemExit:break
    return out

def entropy(b):
    if not b:return 0.0
    c=Counter(b);return -sum((n/len(b))*math.log2(n/len(b)) for n in c.values())

def wasm(cmd,a):
    op=cmd.removeprefix("wasm-")
    if op in ("leb128-u32","leb128-i32"):
        if not a:die("hex bytes required")
        b=bytes.fromhex(a[0]);v,p=(uleb(b,0,32) if op.endswith("u32") else sleb(b,0,32));emit({"value":v,"bytes":p});return
    if not a:die("wasm path required")
    p=P(a[0]);b=p.read_bytes();kind,rows=sections(b)
    if op=="magic-check":emit({"valid":b[:4]==b"\x00asm","kind":kind});return
    if op=="version":emit({"raw":b[4:8].hex(),"kind":kind,"core_version":1 if kind=="module" else None});return
    if op=="section-list":emit(rows);return
    if op=="section-sizes":emit({r["name"]:r["size"] for r in rows});return
    if op=="custom-sections":emit([r for r in rows if r["id"]==0]);return
    countmap={"type-count":1,"import-count":2,"function-count":3,"table-count":4,"memory-count":5,"global-count":6,"export-count":7,"code-count":10,"data-count":11}
    if op in countmap:
        rs=[r for r in rows if r["id"]==countmap[op]];print(sum(vector_count(sec_payload(b,r)) or 0 for r in rs));return
    if op=="start-function":
        rs=[r for r in rows if r["id"]==8]
        if not rs:emit(None);return
        emit(uleb(sec_payload(b,rs[0]),0,32)[0]);return
    if op in ("name-section","producers-section","target-features"):
        want={"name-section":"name","producers-section":"producers","target-features":"target_features"}[op]
        emit([r for r in rows if r.get("custom_name")==want]);return
    if op=="import-modules":
        rs=[r for r in rows if r["id"]==2];emit(sorted(set(sum((import_modules(sec_payload(b,r)) for r in rs),[]))));return
    if op=="export-names":
        rs=[r for r in rows if r["id"]==7];emit(sum((export_names(sec_payload(b,r)) for r in rs),[]));return
    if op in ("memory-limits","table-limits"):
        sid=5 if op.startswith("memory") else 4;kind2="memory" if sid==5 else "table";rs=[r for r in rows if r["id"]==sid];emit(sum((limits(sec_payload(b,r),kind2) for r in rs),[]));return
    if op in ("data-bytes","code-bytes"):
        sid=11 if op.startswith("data") else 10;print(sum(r["size"] for r in rows if r["id"]==sid));return
    if op=="custom-names":emit([r.get("custom_name") for r in rows if r["id"]==0]);return
    if op=="section-order":emit([r["id"] for r in rows]);return
    if op=="section-duplicates":
        c=Counter(r["id"] for r in rows if r["id"]!=0);emit({str(k):v for k,v in c.items() if v>1});return
    if op=="size-summary":emit({"file_bytes":len(b),"section_bytes":sum(r["size"] for r in rows),"sections":len(rows),"kind":kind});return
    if op=="sha256":print(hashlib.sha256(b).hexdigest());return
    if op=="entropy":print(f"{entropy(b):.6f}");return
    if op=="hexdump":
        for off in range(0,min(len(b),int(a[1]) if len(a)>1 else 256),16):
            q=b[off:off+16];print(f"{off:08x}  {' '.join(f'{x:02x}' for x in q)}")
        return
    if op=="validate-basic":
        ids=[r["id"] for r in rows if r["id"]!=0]
        ordered=ids==sorted(ids) if kind=="module" else True
        emit({"valid_magic":b[:4]==b"\x00asm","kind":kind,"sections_parse":True,"core_section_order":ordered});return
    if op=="component-detect":emit({"component":kind=="component","kind":kind,"preamble":b[:8].hex()});return

def wit(cmd,a):
    op=cmd
    if op.startswith("component-"):
        if not a:die("component wasm path required")
        b=P(a[0]).read_bytes();kind,rows=sections(b)
        if op=="component-section-list":emit(rows);return
        if op=="component-import-hints":emit([r for r in rows if r["id"]==10]);return
        if op=="component-export-hints":emit([r for r in rows if r["id"]==11]);return
        if op=="component-async-hints":
            payload=b"".join(sec_payload(b,r) for r in rows);emit({"component":kind=="component","async_opcode_0x43":payload.count(b"\x43"),"canon_async_option_0x06":payload.count(b"\x06")});return
    if not a:die("WIT text/file required")
    s=P(a[0]).read_text(errors="replace") if P(a[0]).exists() else " ".join(a)
    clean=re.sub(r"//.*?$|/\*.*?\*/","",s,flags=re.M|re.S)
    if op=="wit-package-name":
        m=re.search(r"\bpackage\s+([^;\s]+)",clean);print(m.group(1) if m else "");return
    patterns={
      "wit-worlds":r"\bworld\s+([A-Za-z_][\w-]*)",
      "wit-interfaces":r"\binterface\s+([A-Za-z_][\w-]*)",
      "wit-functions":r"\b([A-Za-z_][\w-]*)\s*:\s*(?:async\s+)?func\b",
      "wit-records":r"\brecord\s+([A-Za-z_][\w-]*)",
      "wit-variants":r"\bvariant\s+([A-Za-z_][\w-]*)",
      "wit-resources":r"\bresource\s+([A-Za-z_][\w-]*)",
      "wit-enums":r"\benum\s+([A-Za-z_][\w-]*)",
      "wit-flags":r"\bflags\s+([A-Za-z_][\w-]*)",
      "wit-types":r"\btype\s+([A-Za-z_][\w-]*)",
      "wit-async-functions":r"\b([A-Za-z_][\w-]*)\s*:\s*async\s+func\b",
    }
    if op in patterns:emit(re.findall(patterns[op],clean));return
    if op=="wit-use-count":print(len(re.findall(r"\buse\b",clean)));return
    if op=="wit-include-count":print(len(re.findall(r"\binclude\b",clean)));return
    if op=="wit-stream-types":emit(re.findall(r"\bstream\s*<([^>]+)>",clean));return
    if op=="wit-future-types":emit(re.findall(r"\bfuture\s*<([^>]+)>",clean));return
    if op=="wasi-version-hints":
        emit(sorted(set(re.findall(r"wasi:[A-Za-z0-9_./-]+@[0-9]+\.[0-9]+(?:\.[0-9]+)?",clean))));return
    if op=="wasi-imports":
        emit(sorted(set(re.findall(r"\b(?:import|use)\s+([^;{]+)",clean))));return
    checks={
      "wasi-preview1-detect":["wasi_snapshot_preview1"],
      "wasi-preview2-detect":["wasi:cli","wasi:io","wasi:http"],
      "wasi-preview3-hints":["async func","stream<","future<"],
      "wasi-http-hints":["wasi:http"],
      "wasi-cli-hints":["wasi:cli"],
      "wasi-filesystem-hints":["wasi:filesystem"],
      "wasi-sockets-hints":["wasi:sockets"],
      "wasi-random-hints":["wasi:random"],
      "wasi-clocks-hints":["wasi:clocks"],
      "wasi-io-hints":["wasi:io"],
      "wasi-component-hints":["world ","interface "],
    }
    if op in checks:
        emit({"matched":[x for x in checks[op] if x in clean],"detected":any(x in clean for x in checks[op])});return

def main():
    cmd=P(sys.argv[0]).name;a=sys.argv[1:]
    if cmd not in COMMANDS:
        if a and a[0] in COMMANDS:cmd=a.pop(0)
        elif not a or a[0] in ("-h","--help"):
            print("Shard 28 — WebAssembly/WASI 0.3/Component Model utilities");print("\n".join(COMMANDS));return
        else:die("unknown command")
    if a and a[0] in ("-h","--help"):
        print(cmd+" — functional shard 28 utility");return
    if cmd in WASM:wasm(cmd,a)
    else:wit(cmd,a)
if __name__=="__main__":main()
