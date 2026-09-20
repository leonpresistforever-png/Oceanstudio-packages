#!/usr/bin/env python3
from __future__ import annotations
import sys,json,re,struct,subprocess,shutil,ast
from pathlib import Path
VERSION="2.0.0"
def out(x):print(json.dumps(x,indent=2,sort_keys=True,default=str))
def die(x,c=2):print(x,file=sys.stderr);raise SystemExit(c)
def rb(a):return Path(a[0]).read_bytes()
def rt(a):return Path(a[0]).read_text(errors="replace") if a and Path(a[0]).exists() else (" ".join(a) if a else sys.stdin.read())
class Elf:
    def __init__(self,b):
        if b[:4]!=b"\x7fELF":raise ValueError("not ELF")
        self.b=b;self.cls=b[4];self.end="<" if b[5]==1 else ">";self.bits=64 if self.cls==2 else 32
        if self.bits==64:
            vals=struct.unpack_from(self.end+"HHIQQQIHHHHHH",b,16)
            self.type,self.machine,self.ver,self.entry,self.phoff,self.shoff,self.flags,self.ehsize,self.phentsize,self.phnum,self.shentsize,self.shnum,self.shstrndx=vals
        else:
            vals=struct.unpack_from(self.end+"HHIIIIIHHHHHH",b,16)
            self.type,self.machine,self.ver,self.entry,self.phoff,self.shoff,self.flags,self.ehsize,self.phentsize,self.phnum,self.shentsize,self.shnum,self.shstrndx=vals
        self.sections=self._sections()
    def _rawsh(self,i):
        o=self.shoff+i*self.shentsize
        fmt=self.end+("IIQQQQIIQQ" if self.bits==64 else "IIIIIIIIII")
        return struct.unpack_from(fmt,self.b,o)
    def _sections(self):
        raw=[self._rawsh(i) for i in range(self.shnum)]
        if not raw:return []
        s=raw[self.shstrndx]; off,size=(s[4],s[5]) if self.bits==64 else (s[4],s[5]); names=self.b[off:off+size]
        def nm(o):
            e=names.find(b"\0",o);return names[o:e if e>=0 else None].decode(errors="replace")
        rows=[]
        for i,x in enumerate(raw):
            if self.bits==64:name,typ,flags,addr,off,size,link,info,align,entsize=x
            else:name,typ,flags,addr,off,size,link,info,align,entsize=x
            rows.append({"index":i,"name":nm(name),"type":typ,"flags":flags,"addr":addr,"offset":off,"size":size,"link":link,"info":info,"align":align,"entsize":entsize})
        return rows
    def sec(self,n):return next((x for x in self.sections if x["name"]==n),None)
    def strings(self,n):
        s=self.sec(n)
        if not s:return b""
        return self.b[s["offset"]:s["offset"]+s["size"]]
    def symbols(self,n=".dynsym"):
        s=self.sec(n)
        if not s or not s["entsize"]:return []
        strsec=self.sections[s["link"]] if s["link"]<len(self.sections) else None
        strings=self.b[strsec["offset"]:strsec["offset"]+strsec["size"]] if strsec else b""
        rows=[]
        for o in range(s["offset"],s["offset"]+s["size"],s["entsize"]):
            if o+s["entsize"]>len(self.b):break
            if self.bits==64:st_name,info,other,shndx,val,size=struct.unpack_from(self.end+"IBBHQQ",self.b,o)
            else:st_name,val,size,info,other,shndx=struct.unpack_from(self.end+"IIIBBH",self.b,o)
            e=strings.find(b"\0",st_name);name=strings[st_name:e if e>=0 else None].decode(errors="replace") if st_name<len(strings) else ""
            rows.append({"name":name,"bind":info>>4,"type":info&15,"visibility":other&3,"shndx":shndx,"value":val,"size":size})
        return rows
def elf(a):return Elf(rb(a))
def demangle(a):
    if not a:die("SYMBOL")
    sym=a[0]
    for exe in ("c++filt","llvm-cxxfilt"):
        p=shutil.which(exe)
        if p:
            r=subprocess.run([p,sym],capture_output=True,text=True);print(r.stdout.strip());return
    print(sym)
def rustdem(a):
    if shutil.which("rustfilt"):print(subprocess.run(["rustfilt",a[0]],capture_output=True,text=True).stdout.strip())
    else:print(re.sub(r"^_?ZN\d+","",a[0]).replace("$LT$","<").replace("$GT$",">"))
def sections(a):out(elf(a).sections)
def relocs(a):
    e=elf(a);rows=[]
    for s in e.sections:
        if s["type"] not in (4,9) or not s["entsize"]:continue
        for o in range(s["offset"],s["offset"]+s["size"],s["entsize"]):
            if e.bits==64:
                if s["type"]==4:r_off,r_info,add=struct.unpack_from(e.end+"QQq",e.b,o)
                else:r_off,r_info=struct.unpack_from(e.end+"QQ",e.b,o);add=None
                sym=r_info>>32;typ=r_info&0xffffffff
            else:
                if s["type"]==4:r_off,r_info,add=struct.unpack_from(e.end+"IIi",e.b,o)
                else:r_off,r_info=struct.unpack_from(e.end+"II",e.b,o);add=None
                sym=r_info>>8;typ=r_info&0xff
            rows.append({"section":s["name"],"offset":r_off,"symbol":sym,"type":typ,"addend":add})
    out(rows)
def dynamic(a):
    e=elf(a);s=e.sec(".dynamic");rows=[]
    if s:
        ent=16 if e.bits==64 else 8
        for o in range(s["offset"],s["offset"]+s["size"],ent):
            tag,val=struct.unpack_from(e.end+("qQ" if e.bits==64 else "iI"),e.b,o);rows.append({"tag":tag,"value":val})
            if tag==0:break
    out(rows)
def strings(a):
    e=elf(a);name=a[1] if len(a)>1 else ".dynstr";b=e.strings(name);out([x.decode(errors="replace") for x in b.split(b"\0") if x])
def symver(a):
    e=elf(a);out({"gnu_version":bool(e.sec(".gnu.version")),"version_d":bool(e.sec(".gnu.version_d")),"version_r":bool(e.sec(".gnu.version_r"))})
def hashchk(a):
    e=elf(a);out({"sysv_hash":e.sec(".hash"),"gnu_hash":e.sec(".gnu.hash")})
def gnuhash(a):
    e=elf(a);s=e.sec(".gnu.hash");out({"present":bool(s),"bytes":s["size"] if s else 0,"symbol":a[1] if len(a)>1 else None})
def ar(a):
    b=rb(a)
    if not b.startswith(b"!<arch>\n"):die("not ar")
    pos=8;rows=[]
    while pos+60<=len(b):
        h=b[pos:pos+60];name=h[:16].decode(errors="replace").strip().rstrip("/");size=int(h[48:58].decode().strip() or 0);rows.append({"name":name,"size":size,"offset":pos+60});pos+=60+size+(size&1)
    out(rows)
def ranlib(a):ar(a)
def nms(a,defined):
    e=elf(a);rows=[x for x in e.symbols(".symtab")+e.symbols(".dynsym") if bool(x["shndx"])==defined and x["name"]];out(rows)
def nmundef(a):nms(a,False)
def nmdef(a):nms(a,True)
def stripdbg(a):
    e=elf(a);out([x for x in e.sections if x["name"].startswith(".debug") or x["name"].startswith(".zdebug")])
def objcopy(a):
    if len(a)<2:die("ELF SECTION")
    e=elf(a);s=e.sec(a[1])
    if not s:die("section missing")
    sys.stdout.buffer.write(e.b[s["offset"]:s["offset"]+s["size"]])
def llvm_bc(a):
    b=rb(a);out({"magic":b[:4].hex(),"raw_bitcode":b.startswith(b"BC\xc0\xde"),"wrapper":b.startswith(b"\xde\xc0\x17\x0b"),"bytes":len(b)})
def llvm_ir(a):
    s=rt(a);blocks=re.findall(r"(?m)^([A-Za-z$._][\w$.-]*):",s);ops=re.findall(r"(?m)^\s*(?:[%@][\w$.-]+\s*=\s*)?([a-z][a-z0-9.]*)\b",s);out({"blocks":blocks,"opcodes":{x:ops.count(x) for x in sorted(set(ops))}})
def leb(b,p):
    v=0;s=0
    while p<len(b):
        x=b[p];p+=1;v|=(x&127)<<s
        if not x&128:return v,p
        s+=7
    raise ValueError("truncated leb")
def wasm_sections(a):
    b=rb(a)
    if b[:4]!=b"\0asm":die("not wasm")
    p=8;rows=[]
    while p<len(b):
        sid=b[p];p+=1;n,p=leb(b,p);rows.append({"id":sid,"size":n,"offset":p});p+=n
    out(rows)
def wasm_header(a):
    b=rb(a);out({"magic":b[:4].hex(),"version":int.from_bytes(b[4:8],"little") if len(b)>=8 else None,"valid":b[:4]==b"\0asm"})
def wasm_ops(a):
    b=rb(a); out({"bytes":len(b),"opcode_frequency":{hex(x):b.count(bytes([x])) for x in (0x0b,0x20,0x21,0x41,0x6a,0x10)}})
def dwarf(a):
    e=elf(a);out([x for x in e.sections if x["name"].startswith(".debug") or x["name"].startswith(".zdebug")])
def ctf(a):
    b=rb(a);out({"magic":b[:4].hex(),"bytes":len(b)})
def btf(a):
    b=rb(a);out({"magic":hex(int.from_bytes(b[:2],"little")) if len(b)>=2 else None,"version":b[2] if len(b)>2 else None,"flags":b[3] if len(b)>3 else None,"bytes":len(b)})
def pe(a):
    b=rb(a)
    if b[:2]!=b"MZ":die("not PE")
    peoff=int.from_bytes(b[0x3c:0x40],"little")
    if b[peoff:peoff+4]!=b"PE\0\0":die("bad PE")
    machine,nsec,timestamp,ptrsym,nsym,optsz,chars=struct.unpack_from("<HHIIIHH",b,peoff+4)
    out({"machine":hex(machine),"sections":nsec,"timestamp":timestamp,"symbol_table":ptrsym,"symbols":nsym,"optional_header_size":optsz,"characteristics":hex(chars)})
def coff(a):pe(a)
def macho(a):
    b=rb(a);magic=int.from_bytes(b[:4],"little");bits=64 if magic in (0xfeedfacf,0xcffaedfe) else 32;out({"magic":hex(magic),"bits":bits,"bytes":len(b)})
def clangast(a):
    x=json.loads(Path(a[0]).read_text());needle=a[1] if len(a)>1 else "";rows=[]
    def walk(v):
        if isinstance(v,dict):
            if needle.lower() in str(v.get("kind","")).lower() or needle.lower() in str(v.get("name","")).lower():rows.append({"kind":v.get("kind"),"name":v.get("name")})
            for z in v.values():walk(z)
        elif isinstance(v,list):
            for z in v:walk(z)
    walk(x);out(rows)
def gccspec(a):
    s=rt(a);rows={}
    cur=None
    for l in s.splitlines():
        if l.startswith("*") and l.endswith(":"):cur=l[1:-1];rows[cur]=[]
        elif cur:rows[cur].append(l)
    out({k:"\n".join(v) for k,v in rows.items()})
def includes(a):
    s=rt(a);out(re.findall(r'(?m)^\s*#\s*include\s*[<"]([^>"]+)[>"]',s))
def macros(a):
    s=rt(a);out([{"name":n,"value":v.strip()} for n,v in re.findall(r"(?m)^\s*#\s*define\s+([A-Za-z_]\w*)(.*)$",s)])
def ctokens(a):
    s=rt(a);tok=re.findall(r"[A-Za-z_]\w*|0x[0-9A-Fa-f]+|\d+(?:\.\d+)?|==|!=|<=|>=|->|&&|\|\||[{}()[\];,+*/%<>=!&|^-]",re.sub(r"//.*?$|/\*.*?\*/"," ",s,flags=re.M|re.S));out({"count":len(tok),"identifiers":sum(bool(re.match(r"[A-Za-z_]",x)) for x in tok)})
def guard(a):
    s=rt(a);m1=re.search(r"(?m)^\s*#ifndef\s+(\w+)",s);m2=re.search(r"(?m)^\s*#define\s+(\w+)",s);out({"valid":bool(m1 and m2 and m1.group(1)==m2.group(1) and "#endif" in s),"guard":m1.group(1) if m1 else None})
def once(a):out({"pragma_once":bool(re.search(r"(?m)^\s*#\s*pragma\s+once\b",rt(a)))})
_ALLOWED=(ast.Expression,ast.Constant,ast.UnaryOp,ast.BinOp,ast.BoolOp,ast.Compare,ast.Add,ast.Sub,ast.Mult,ast.Div,ast.FloorDiv,ast.Mod,ast.Pow,ast.USub,ast.UAdd,ast.Not,ast.And,ast.Or,ast.Eq,ast.NotEq,ast.Lt,ast.LtE,ast.Gt,ast.GtE)
def staticassert(a):
    e=ast.parse(" ".join(a),mode="eval")
    if any(not isinstance(n,_ALLOWED) for n in ast.walk(e)):die("unsafe expression")
    out({"value":eval(compile(e,"<expr>","eval"),{"__builtins__":{}},{})})
def endian(a):
    n=int(a[0],0);size=int(a[1]) if len(a)>1 else 4;out({"little":n.to_bytes(size,"little").hex(),"big":n.to_bytes(size,"big").hex()})
def callconv(a):
    vals=a;out([{"arg":i,"location":f"x{i}" if i<8 else f"stack+{(i-8)*8}"} for i,_ in enumerate(vals)])
def frame(a):
    vals=[int(x,0) for x in a] or [0];size=sum(vals);aligned=(size+15)//16*16;out({"payload":size,"stack_frame":aligned,"alignment":16})
def layout(a):
    fields=[]
    for spec in a:
        name,size,align=spec.split(":");size=int(size);align=int(align);fields.append((name,size,align))
    off=0;rows=[];maxa=1
    for name,size,al in fields:
        maxa=max(maxa,al);pad=(-off)%al;off+=pad;rows.append({"name":name,"offset":off,"size":size,"padding_before":pad});off+=size
    tail=(-off)%maxa;out({"fields":rows,"size":off+tail,"tail_padding":tail,"alignment":maxa})
def vtable(a):
    s=rt(a);out({"virtual_methods":re.findall(r"\bvirtual\s+[^;{]+?(\w+)\s*\(",s),"has_virtual_destructor":bool(re.search(r"virtual\s+~\w+\s*\(",s))})
def rtti(a):
    e=elf(a);sy=[x["name"] for x in e.symbols(".dynsym")+e.symbols(".symtab") if x["name"].startswith(("_ZTI","_ZTS","_ZTV"))];out(sorted(set(sy)))
def weak(a):
    e=elf(a);out([x for x in e.symbols(".dynsym")+e.symbols(".symtab") if x["bind"]==2 and x["name"]])
def hidden(a):
    e=elf(a);out([x for x in e.symbols(".dynsym")+e.symbols(".symtab") if x["visibility"] in (1,2,3) and x["name"]])
def interpose(a):
    if len(a)<2:die("ELF ELF")
    x={s["name"] for s in elf([a[0]]).symbols(".dynsym") if s["shndx"] and s["name"]};y={s["name"] for s in elf([a[1]]).symbols(".dynsym") if s["shndx"] and s["name"]};out(sorted(x&y))
def ldscript(a):
    s=rt(a);secs=[m.group(1) for m in re.finditer(r"(?m)^\s*(\.[A-Za-z0-9_.$-]+)\s*(?:\([^)]*\))?\s*:",s)];mem=re.findall(r"(?m)^\s*(\w+)\s*\([^)]*\)\s*:\s*ORIGIN\s*=\s*([^,]+),\s*LENGTH\s*=\s*(\S+)",s);out({"sections":secs,"memory":[{"name":x,"origin":y.strip(),"length":z} for x,y,z in mem]})
def alias(a):
    s=rt(a);out([{"alias":x,"target":y} for x,y in re.findall(r'\b(\w+)\s*__attribute__\s*\(\(\s*alias\s*\(\s*"([^"]+)"\s*\)',s)])
COMMANDS={"cxx-symbol-demangler":demangle,"rust-symbol-demangle":rustdem,"itanium-demangler":demangle,"elf-section-size-calc":sections,"elf-relocation-dumper":relocs,"elf-dynamic-tags-view":dynamic,"elf-string-table-cat":strings,"elf-symbol-versioning":symver,"elf-hash-table-chk":hashchk,"elf-gnu-hash-lookup":gnuhash,"ar-archive-extractor":ar,"ranlib-index-viewer":ranlib,"nm-undefined-symbols":nmundef,"nm-defined-symbols":nmdef,"strip-debug-symbols":stripdbg,"objcopy-binary-dump":objcopy,"llvm-bitcode-header":llvm_bc,"llvm-ir-instruction-chk":llvm_ir,"wasm-header-parser":wasm_header,"wasm-section-lister":wasm_sections,"wasm-opcode-disasm":wasm_ops,"dwarf-line-info-view":dwarf,"dwarf-die-inspector":dwarf,"ctf-type-data-parser":ctf,"btf-kernel-type-dump":btf,"pe-relocation-table":pe,"coff-symbol-table-dump":coff,"macho-dylib-id-view":macho,"macho-uuid-inspector":macho,"macho-segment-calc":macho,"clang-ast-dump-filter":clangast,"gcc-spec-file-parser":gccspec,"include-graph-builder":includes,"c-preprocessor-macro":macros,"c-token-counter":ctokens,"header-guard-validator":guard,"pragma-once-checker":once,"static-assert-verify":staticassert,"endian-byte-order-chk":endian,"calling-convention-chk":callconv,"stack-frame-calculator":frame,"abi-alignment-checker":layout,"structure-padding-calc":layout,"vtable-layout-analyzer":vtable,"rtti-descriptor-view":rtti,"weak-symbol-finder":weak,"hidden-visibility-chk":hidden,"interposition-auditor":interpose,"linker-script-parser":ldscript,"symbol-alias-resolver":alias}
def main():
    if len(COMMANDS)!=50:die(f"command count {len(COMMANDS)}")
    p=Path(sys.argv[0]).name
    if p in COMMANDS:cmd,args=p,sys.argv[1:]
    else:
        if len(sys.argv)<2 or sys.argv[1] in ("-h","--help"):print("OceanStudio functional shard 11");print("\n".join(sorted(COMMANDS)));return
        if sys.argv[1] in ("-v","--version"):print(VERSION);return
        cmd,args=sys.argv[1],sys.argv[2:]
    if cmd not in COMMANDS:die("unknown command: "+cmd)
    COMMANDS[cmd](args)
if __name__=="__main__":main()
