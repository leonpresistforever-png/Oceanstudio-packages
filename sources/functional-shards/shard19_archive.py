#!/usr/bin/env python3
from __future__ import annotations
import base64, datetime as dt, hashlib, json, os, re, struct, sys, tarfile, zipfile, zlib
from pathlib import Path

COMMANDS=[
"tar-header-validator","tar-gnu-longlink-chk","tar-pax-extended-chk","tar-sparse-header-chk","cpio-crc-format-dump","cpio-odc-format-dump","cpio-newc-header-chk","ar-bsd-variant-parser","ar-gnu-variant-parser","zip-eocd-locator-cli","zip-cd-record-viewer","zip-extra-field-parse","zip64-locator-parser","sevenzip-signature-chk","sevenzip-header-view","rar5-header-validator","cab-folder-extractor","iso-rockridge-parser","iso-joliet-ext-parser","wim-header-inspector","squashfs-inode-table","ext4-dump-restore-chk","rdiff-delta-generator","rdiff-patch-applier","rsync-checksum-block","rsync-rolling-hash","adler32-rolling-calc","rabin-karp-chunker","content-defined-chunk","fastcdc-chunker-cli","backup-catalog-verify","backup-retention-calc","snapshot-differential","dir-tree-hasher-fast","mtree-specification-gen","mtree-validator-tool","dar-disk-archiver-chk","afio-archive-linter","pax-archive-validator","xar-xml-toc-extractor","chm-archive-header-chk","deb-ar-data-splitter","rpm-lead-header-parser","apk-zip-comment-tool","vhd-footer-inspector","qcow2-header-parser","vmdk-descriptor-view","raw-disk-image-resizer","sparse-image-converter","simg2img-ocean-cli"
]

def emit(x):
    if isinstance(x,(dict,list,tuple)): print(json.dumps(x,indent=2,default=str))
    else: print(x)
def need(a,n):
    if len(a)<n: raise SystemExit(f"expected at least {n} arguments")
def read(path): return Path(path).read_bytes()
def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()
def tar_block(path):
    b=read(path)[:512]
    if len(b)<512:return {"valid":False,"reason":"short header"}
    raw=b[148:156].rstrip(b"\0 ").decode("ascii","ignore")
    stored=int(raw or "0",8) if re.fullmatch(r"[0-7]+",raw or "0") else -1
    calc=sum(b[:148])+8*32+sum(b[156:])
    name=b[:100].split(b"\0",1)[0].decode("utf-8","replace")
    prefix=b[345:500].split(b"\0",1)[0].decode("utf-8","replace")
    return {"valid":stored==calc,"stored_checksum":stored,"calculated_checksum":calc,"name":f"{prefix}/{name}" if prefix else name,"typeflag":chr(b[156]) if b[156] else "0","magic":b[257:263].decode("ascii","replace")}
def raw_tar_entries(path):
    data=read(path);out=[];i=0
    while i+512<=len(data):
        h=data[i:i+512]
        if h==b"\0"*512:break
        n=h[:100].split(b"\0",1)[0].decode("utf-8","replace");typ=chr(h[156]) if h[156] else "0"
        try:size=int(h[124:136].rstrip(b"\0 ").decode("ascii","ignore") or "0",8)
        except ValueError:size=0
        payload=data[i+512:i+512+size];out.append((n,typ,size,payload,h));i+=512+((size+511)//512)*512
    return out
def cpio_newc(path):
    b=read(path);out=[];p=0
    while p+110<=len(b):
        magic=b[p:p+6]
        if magic not in (b"070701",b"070702"):break
        vals=[int(b[p+6+i*8:p+14+i*8],16) for i in range(13)]
        namesz=vals[11];filesz=vals[6];name=b[p+110:p+110+namesz].rstrip(b"\0").decode("utf-8","replace")
        dataoff=(p+110+namesz+3)&~3
        out.append({"magic":magic.decode(),"name":name,"ino":vals[0],"mode":oct(vals[1]),"uid":vals[2],"gid":vals[3],"nlink":vals[4],"mtime":vals[5],"filesize":filesz,"checksum":vals[12]})
        p=(dataoff+filesz+3)&~3
        if name=="TRAILER!!!":break
    return out
def cpio_odc(path):
    b=read(path);out=[];p=0
    while p+76<=len(b) and b[p:p+6]==b"070707":
        h=b[p:p+76]
        try:
            ino=int(h[12:18],8);mode=int(h[18:24],8);namesz=int(h[59:65],8);filesz=int(h[65:76],8)
        except ValueError:break
        name=b[p+76:p+76+namesz].rstrip(b"\0").decode("utf-8","replace");dataoff=p+76+namesz
        out.append({"name":name,"ino":ino,"mode":oct(mode),"filesize":filesz});p=dataoff+filesz
        if name=="TRAILER!!!":break
    return out
def ar_entries(path,extract=None):
    b=read(path)
    if not b.startswith(b"!<arch>\n"):return []
    p=8;gnu_names=b"";out=[]
    while p+60<=len(b):
        h=b[p:p+60]
        if h[58:60]!=b"`\n":break
        raw=h[:16].decode("utf-8","replace").rstrip();full_size=int(h[48:58].decode().strip() or 0);data=b[p+60:p+60+full_size];name=raw.rstrip("/")
        if raw=="//":gnu_names=data
        elif raw.startswith("/") and raw[1:].isdigit() and gnu_names:
            off=int(raw[1:]);name=gnu_names[off:].split(b"/\n",1)[0].decode("utf-8","replace")
        elif raw.startswith("#1/"):
            n=int(raw[3:].strip());name=data[:n].decode("utf-8","replace");data=data[n:]
        item={"name":name,"size":len(data),"offset":p+60};out.append(item)
        if extract is not None and name not in ("","/","//"): (extract/Path(name).name).write_bytes(data)
        p+=60+full_size;p+=(p%2)
    return out
def zip_eocd(path):
    b=read(path);i=b.rfind(b"PK\x05\x06",max(0,len(b)-65557))
    if i<0:return {"valid":False}
    if i+22>len(b):return {"valid":False,"offset":i}
    vals=struct.unpack_from("<4s4H2IH",b,i)
    return {"valid":True,"offset":i,"disk":vals[1],"cd_disk":vals[2],"entries_disk":vals[3],"entries_total":vals[4],"cd_size":vals[5],"cd_offset":vals[6],"comment_length":vals[7],"comment":b[i+22:i+22+vals[7]].decode("utf-8","replace")}
def extra_fields(extra):
    p=0;out=[]
    while p+4<=len(extra):
        tag,n=struct.unpack_from("<HH",extra,p);p+=4;v=extra[p:p+n];out.append({"id":hex(tag),"length":n,"hex":v.hex()});p+=n
    return out
def seven(path):
    b=read(path)[:32]
    if len(b)<32:return {"valid":False}
    return {"valid":b[:6]==b"7z\xbc\xaf'\x1c","version_major":b[6],"version_minor":b[7],"start_header_crc":hex(struct.unpack_from("<I",b,8)[0]),"next_header_offset":struct.unpack_from("<Q",b,12)[0],"next_header_size":struct.unpack_from("<Q",b,20)[0],"next_header_crc":hex(struct.unpack_from("<I",b,28)[0])}
def cab(path):
    b=read(path)[:64]
    if len(b)<36 or b[:4]!=b"MSCF":return {"valid":False}
    return {"valid":True,"cabinet_size":struct.unpack_from("<I",b,8)[0],"files_offset":struct.unpack_from("<I",b,16)[0],"version_minor":b[24],"version_major":b[25],"folders":struct.unpack_from("<H",b,26)[0],"files":struct.unpack_from("<H",b,28)[0],"flags":hex(struct.unpack_from("<H",b,30)[0]),"set_id":struct.unpack_from("<H",b,32)[0],"cabinet_index":struct.unpack_from("<H",b,34)[0]}
def iso_desc(path):
    with open(path,"rb") as f:
        f.seek(16*2048);out=[]
        for _ in range(64):
            b=f.read(2048)
            if len(b)<2048 or b[1:6]!=b"CD001":break
            out.append((b[0],b))
            if b[0]==255:break
        return out
def wim(path):
    b=read(path)[:208]
    if len(b)<48:return {"valid":False}
    valid=b[:8]==b"MSWIM\0\0\0"
    return {"valid":valid,"header_size":struct.unpack_from("<I",b,8)[0] if valid else None,"version":hex(struct.unpack_from("<I",b,12)[0]) if len(b)>=16 else None,"flags":hex(struct.unpack_from("<I",b,16)[0]) if len(b)>=20 else None,"chunk_size":struct.unpack_from("<I",b,20)[0] if len(b)>=24 else None,"part_number":struct.unpack_from("<H",b,40)[0] if len(b)>=42 else None,"total_parts":struct.unpack_from("<H",b,42)[0] if len(b)>=44 else None,"images":struct.unpack_from("<I",b,44)[0] if len(b)>=48 else None}
def squash(path):
    b=read(path)[:96]
    if len(b)<96:return {"valid":False}
    return {"valid":struct.unpack_from("<I",b,0)[0]==0x73717368,"inodes":struct.unpack_from("<I",b,4)[0],"block_size":struct.unpack_from("<I",b,12)[0],"fragments":struct.unpack_from("<I",b,28)[0],"inode_table_start":struct.unpack_from("<Q",b,64)[0],"directory_table_start":struct.unpack_from("<Q",b,72)[0],"fragment_table_start":struct.unpack_from("<Q",b,80)[0],"export_table_start":struct.unpack_from("<Q",b,88)[0]}
def rollsum(b):
    a=sum(b)&0xffff;bb=sum((len(b)-i)*x for i,x in enumerate(b))&0xffff;return (bb<<16)|a
def chunks_rabin(data,minsz=2048,avgsz=8192,maxsz=65536):
    if not data:return []
    mask=max(1,avgsz-1);out=[];start=0;h=0
    for i,x in enumerate(data):
        h=((h*257)+x)&0xffffffff;n=i-start+1
        if n>=minsz and ((h&mask)==0 or n>=maxsz):out.append((start,n,h));start=i+1;h=0
    if start<len(data):out.append((start,len(data)-start,h))
    return out
GEAR=[int(hashlib.sha256(bytes([i])).hexdigest()[:16],16) for i in range(256)]
def ilog2(x):
    n=0
    while (1<<(n+1))<=x:n+=1
    return n
def chunks_fast(data,minsz=2048,avgsz=8192,maxsz=65536):
    if not data:return []
    mask=(1<<max(1,ilog2(avgsz)))-1;out=[];start=0;h=0
    for i,x in enumerate(data):
        h=((h<<1)+GEAR[x])&0xffffffffffffffff;n=i-start+1
        if n>=minsz and ((h&mask)==0 or n>=maxsz):out.append((start,n,h));start=i+1;h=0
    if start<len(data):out.append((start,len(data)-start,h))
    return out
def snapshot(root):
    root=Path(root);out={}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink():
            try:out[str(p.relative_to(root))]={"size":p.stat().st_size,"sha256":sha(p)}
            except OSError:pass
    return out
def merkle(root):
    items=snapshot(root);h=hashlib.sha256()
    for k,v in sorted(items.items()):h.update(k.encode()+b"\0"+v["sha256"].encode()+b"\0")
    return {"root_sha256":h.hexdigest(),"files":len(items),"entries":items}
def mtree(root):
    root=Path(root);rows=["#mtree"]
    for p in sorted(root.rglob("*")):
        rel="./"+str(p.relative_to(root))
        try:
            s=p.lstat()
            if p.is_symlink():rows.append(f"{rel} type=link link={os.readlink(p)}")
            elif p.is_dir():rows.append(f"{rel} type=dir mode={oct(s.st_mode&0o7777)}")
            elif p.is_file():rows.append(f"{rel} type=file size={s.st_size} sha256digest={sha(p)} mode={oct(s.st_mode&0o7777)}")
        except OSError:pass
    return rows
def parse_sparse(path,outpath):
    b=read(path)
    if len(b)<28:raise ValueError("short Android sparse image")
    magic,maj,minv,fhsz,chsz,blksz,total_blks,total_chunks,checksum=struct.unpack_from("<I4H4I",b,0)
    if magic!=0xED26FF3A:raise ValueError("bad Android sparse magic")
    p=fhsz;written=0
    with open(outpath,"wb") as o:
        for _ in range(total_chunks):
            typ,res,chunk_sz,total_sz=struct.unpack_from("<2H2I",b,p);payload=p+chsz;outbytes=chunk_sz*blksz
            if typ==0xCAC1:o.write(b[payload:payload+outbytes])
            elif typ==0xCAC2:
                word=b[payload:payload+4]
                if len(word)!=4:raise ValueError("short fill chunk")
                for _ in range(outbytes//4):o.write(word)
            elif typ==0xCAC3:o.seek(outbytes,1)
            elif typ==0xCAC4:pass
            else:raise ValueError(f"unknown chunk type {hex(typ)}")
            written+=outbytes;p+=total_sz
        o.truncate(total_blks*blksz)
    return {"major":maj,"minor":minv,"block_size":blksz,"blocks":total_blks,"chunks":total_chunks,"output_bytes":total_blks*blksz,"logical_written":written}

def main(cmd,a):
    if cmd not in COMMANDS:raise SystemExit("unknown command")
    if cmd=="tar-header-validator":need(a,1);emit(tar_block(a[0]));return
    if cmd=="tar-gnu-longlink-chk":need(a,1);emit([{"entry":n,"long_name":p.rstrip(b"\0").decode("utf-8","replace")} for n,t,s,p,h in raw_tar_entries(a[0]) if t=="L"]);return
    if cmd=="tar-pax-extended-chk":
        need(a,1);out=[]
        with tarfile.open(a[0],"r:*") as t:
            for m in t:
                if getattr(m,"pax_headers",None):out.append({"name":m.name,"pax":m.pax_headers})
        emit(out);return
    if cmd=="tar-sparse-header-chk":
        need(a,1);out=[]
        with tarfile.open(a[0],"r:*") as t:
            for m in t:
                keys={k:v for k,v in getattr(m,"pax_headers",{}).items() if "sparse" in k.lower()}
                if keys or getattr(m,"sparse",None):out.append({"name":m.name,"sparse":getattr(m,"sparse",None),"pax":keys})
        emit(out);return
    if cmd=="cpio-crc-format-dump":need(a,1);emit([x for x in cpio_newc(a[0]) if x["magic"]=="070702"]);return
    if cmd=="cpio-odc-format-dump":need(a,1);emit(cpio_odc(a[0]));return
    if cmd=="cpio-newc-header-chk":need(a,1);emit(cpio_newc(a[0]));return
    if cmd in ("ar-bsd-variant-parser","ar-gnu-variant-parser"):need(a,1);emit(ar_entries(a[0]));return
    if cmd=="zip-eocd-locator-cli":need(a,1);emit(zip_eocd(a[0]));return
    if cmd=="zip-cd-record-viewer":
        need(a,1)
        with zipfile.ZipFile(a[0]) as z:emit([{"name":i.filename,"compressed":i.compress_size,"size":i.file_size,"method":i.compress_type,"crc32":hex(i.CRC),"header_offset":i.header_offset} for i in z.infolist()])
        return
    if cmd=="zip-extra-field-parse":
        need(a,1);out=[]
        with zipfile.ZipFile(a[0]) as z:
            for i in z.infolist():out.append({"name":i.filename,"extra":extra_fields(i.extra)})
        emit(out);return
    if cmd=="zip64-locator-parser":
        need(a,1);b=read(a[0]);i=b.rfind(b"PK\x06\x07");emit({"found":i>=0,"offset":i if i>=0 else None,"disk_with_eocd64":struct.unpack_from("<I",b,i+4)[0] if i>=0 and i+20<=len(b) else None,"eocd64_offset":struct.unpack_from("<Q",b,i+8)[0] if i>=0 and i+20<=len(b) else None});return
    if cmd in ("sevenzip-signature-chk","sevenzip-header-view"):need(a,1);emit(seven(a[0]));return
    if cmd=="rar5-header-validator":need(a,1);b=read(a[0])[:8];emit({"valid":b==b"Rar!\x1a\x07\x01\x00","signature":b.hex()});return
    if cmd=="cab-folder-extractor":need(a,1);emit(cab(a[0]));return
    if cmd=="iso-rockridge-parser":
        need(a,1);b=read(a[0]);hits=[]
        for sig in (b"SP",b"RR",b"NM",b"PX",b"TF",b"SL"):
            pos=0
            while True:
                i=b.find(sig,pos)
                if i<0:break
                if i+4<=len(b) and 4<=b[i+2]<=255:hits.append({"signature":sig.decode(),"offset":i,"length":b[i+2],"version":b[i+3]})
                pos=i+2
        emit(hits[:500]);return
    if cmd=="iso-joliet-ext-parser":
        need(a,1);out=[]
        for typ,b in iso_desc(a[0]):
            if typ==2 and b[88:91] in (b"%/@",b"%/C",b"%/E"):out.append({"type":typ,"escape":b[88:91].decode("ascii","replace"),"volume_id_utf16":b[40:72].decode("utf-16-be","replace").rstrip("\0 ")})
        emit(out);return
    if cmd=="wim-header-inspector":need(a,1);emit(wim(a[0]));return
    if cmd=="squashfs-inode-table":need(a,1);emit(squash(a[0]));return
    if cmd=="ext4-dump-restore-chk":
        need(a,1);b=read(a[0])[:1024];vals=[]
        for off in range(0,max(0,len(b)-4),4):
            v=struct.unpack_from("<I",b,off)[0]
            if v in (60011,60012):vals.append({"offset":off,"magic":v})
        emit({"possible_dump_headers":vals,"valid":bool(vals)});return
    if cmd=="rdiff-delta-generator":
        need(a,3);old=read(a[0]);new=read(a[1]);bs=int(a[3]) if len(a)>3 else 4096;changes=[]
        for off in range(0,len(new),bs):
            nb=new[off:off+bs];ob=old[off:off+bs]
            if nb!=ob:changes.append({"offset":off,"data":base64.b64encode(nb).decode()})
        doc={"format":"ocean-rdiff-v1","block_size":bs,"new_size":len(new),"old_sha256":hashlib.sha256(old).hexdigest(),"new_sha256":hashlib.sha256(new).hexdigest(),"changes":changes};Path(a[2]).write_text(json.dumps(doc));emit({"changes":len(changes),"delta":a[2]});return
    if cmd=="rdiff-patch-applier":
        need(a,3);base=bytearray(read(a[0]));doc=json.loads(Path(a[1]).read_text())
        if hashlib.sha256(base).hexdigest()!=doc["old_sha256"]:raise SystemExit("base checksum mismatch")
        if len(base)<doc["new_size"]:base.extend(b"\0"*(doc["new_size"]-len(base)))
        for c in doc["changes"]:d=base64.b64decode(c["data"]);base[c["offset"]:c["offset"]+len(d)]=d
        base=base[:doc["new_size"]];Path(a[2]).write_bytes(base);got=hashlib.sha256(base).hexdigest();emit({"output":a[2],"sha256":got,"matches":got==doc["new_sha256"]});return
    if cmd=="rsync-checksum-block":need(a,1);bs=int(a[1]) if len(a)>1 else 4096;b=read(a[0]);emit([{"offset":o,"length":len(x),"weak":hex(rollsum(x)),"md5":hashlib.md5(x).hexdigest()} for o in range(0,len(b),bs) for x in [b[o:o+bs]]]);return
    if cmd=="rsync-rolling-hash":need(a,1);b=read(a[0]);w=int(a[1]) if len(a)>1 else 16;emit([{"offset":i,"weak":hex(rollsum(b[i:i+w]))} for i in range(max(0,len(b)-w+1))][:10000]);return
    if cmd=="adler32-rolling-calc":need(a,1);b=read(a[0]);emit({"adler32":hex(zlib.adler32(b)&0xffffffff),"bytes":len(b)});return
    if cmd=="rabin-karp-chunker":need(a,1);b=read(a[0]);emit([{"offset":o,"length":n,"hash":hex(h)} for o,n,h in chunks_rabin(b,int(a[1]) if len(a)>1 else 256,int(a[2]) if len(a)>2 else 1024,int(a[3]) if len(a)>3 else 4096)]);return
    if cmd=="content-defined-chunk":need(a,1);b=read(a[0]);emit([{"offset":o,"length":n,"sha256":hashlib.sha256(b[o:o+n]).hexdigest()} for o,n,h in chunks_rabin(b)]);return
    if cmd=="fastcdc-chunker-cli":need(a,1);b=read(a[0]);emit([{"offset":o,"length":n,"gear_hash":hex(h)} for o,n,h in chunks_fast(b)]);return
    if cmd=="backup-catalog-verify":
        need(a,2);root=Path(a[0]);cat=json.loads(Path(a[1]).read_text());bad=[];entries=cat.get("entries",cat)
        for rel,meta in entries.items():
            p=root/rel
            if not p.is_file():bad.append({"path":rel,"error":"missing"});continue
            got=sha(p)
            if meta.get("sha256") and got!=meta["sha256"]:bad.append({"path":rel,"error":"sha256","expected":meta["sha256"],"actual":got})
        emit({"valid":not bad,"problems":bad});return
    if cmd=="backup-retention-calc":
        count=int(a[0]) if a else 30;now=dt.datetime.fromisoformat(a[1].replace("Z","+00:00")) if len(a)>1 else dt.datetime.now(dt.timezone.utc);days=[now-dt.timedelta(days=i) for i in range(count)];keep=[]
        for x in days:
            tier="daily" if (now-x).days<7 else "weekly" if x.weekday()==0 and (now-x).days<35 else "monthly" if x.day==1 else None
            if tier:keep.append({"timestamp":x.isoformat(),"tier":tier})
        emit(keep);return
    if cmd=="snapshot-differential":need(a,2);A=snapshot(a[0]);B=snapshot(a[1]);ka=set(A);kb=set(B);emit({"added":sorted(kb-ka),"deleted":sorted(ka-kb),"modified":sorted(k for k in ka&kb if A[k]["sha256"]!=B[k]["sha256"])});return
    if cmd=="dir-tree-hasher-fast":need(a,1);emit(merkle(a[0]));return
    if cmd=="mtree-specification-gen":need(a,1);rows=mtree(a[0]);Path(a[1]).write_text("\n".join(rows)+"\n") if len(a)>1 else None;emit(rows);return
    if cmd=="mtree-validator-tool":
        need(a,2);root=Path(a[0]);spec=Path(a[1]).read_text().splitlines();bad=[]
        for line in spec:
            if not line or line.startswith("#"):continue
            parts=line.split();rel=parts[0][2:] if parts[0].startswith("./") else parts[0];kv=dict(x.split("=",1) for x in parts[1:] if "=" in x);p=root/rel
            if not p.exists() and not p.is_symlink():bad.append({"path":rel,"error":"missing"});continue
            if kv.get("type")=="file":
                if "size" in kv and p.stat().st_size!=int(kv["size"]):bad.append({"path":rel,"error":"size"})
                if "sha256digest" in kv and sha(p)!=kv["sha256digest"]:bad.append({"path":rel,"error":"sha256"})
        emit({"valid":not bad,"problems":bad});return
    if cmd=="dar-disk-archiver-chk":need(a,1);b=read(a[0])[:64];emit({"bytes":len(read(a[0])),"starts_with_dar":b.startswith((b"DAR",b"\0DAR")),"header_hex":b.hex()});return
    if cmd=="afio-archive-linter":need(a,1);n=cpio_newc(a[0]);o=cpio_odc(a[0]);emit({"newc_entries":n,"odc_entries":o,"recognized":bool(n or o)});return
    if cmd=="pax-archive-validator":
        need(a,1)
        try:
            with tarfile.open(a[0],"r:*") as t:members=t.getmembers();emit({"valid":True,"members":len(members),"names":[m.name for m in members[:200]]})
        except tarfile.TarError as e:emit({"valid":False,"error":str(e)})
        return
    if cmd=="xar-xml-toc-extractor":
        need(a,1);b=read(a[0])
        if len(b)<28 or b[:4]!=b"xar!":emit({"valid":False});return
        hdrsz,ver=struct.unpack_from(">HH",b,4);clen,ulen=struct.unpack_from(">QQ",b,8);alg=struct.unpack_from(">I",b,24)[0];comp=b[hdrsz:hdrsz+clen]
        try:xml=zlib.decompress(comp).decode("utf-8","replace")
        except Exception:xml=""
        emit({"valid":True,"header_size":hdrsz,"version":ver,"compressed_toc":clen,"uncompressed_toc":ulen,"checksum_alg":alg,"xml":xml});return
    if cmd=="chm-archive-header-chk":need(a,1);b=read(a[0])[:96];emit({"valid":b[:4]==b"ITSF","version":struct.unpack_from("<I",b,4)[0] if len(b)>=8 else None,"header_length":struct.unpack_from("<I",b,8)[0] if len(b)>=12 else None,"language_id":hex(struct.unpack_from("<I",b,20)[0]) if len(b)>=24 else None});return
    if cmd=="deb-ar-data-splitter":
        need(a,1);dest=Path(a[1]) if len(a)>1 else None
        if dest:dest.mkdir(parents=True,exist_ok=True)
        ents=ar_entries(a[0],dest);emit({"valid_deb":any(x["name"]=="debian-binary" for x in ents) and any(x["name"].startswith("control.tar") for x in ents) and any(x["name"].startswith("data.tar") for x in ents),"entries":ents,"extracted_to":str(dest) if dest else None});return
    if cmd=="rpm-lead-header-parser":need(a,1);b=read(a[0])[:96];valid=b[:4]==b"\xed\xab\xee\xdb";emit({"valid":valid,"major":b[4] if len(b)>4 else None,"minor":b[5] if len(b)>5 else None,"type":struct.unpack_from(">H",b,6)[0] if len(b)>=8 else None,"arch":struct.unpack_from(">H",b,8)[0] if len(b)>=10 else None,"name":b[10:76].split(b"\0",1)[0].decode("utf-8","replace") if len(b)>=76 else ""});return
    if cmd=="apk-zip-comment-tool":
        need(a,1)
        with zipfile.ZipFile(a[0]) as z:emit({"comment":z.comment.decode("utf-8","replace"),"comment_hex":z.comment.hex(),"entries":len(z.infolist())})
        return
    if cmd=="vhd-footer-inspector":
        need(a,1);b=read(a[0])[-512:]
        if len(b)<512 or b[:8]!=b"conectix":emit({"valid":False});return
        emit({"valid":True,"features":hex(struct.unpack_from(">I",b,8)[0]),"version":hex(struct.unpack_from(">I",b,12)[0]),"data_offset":struct.unpack_from(">Q",b,16)[0],"timestamp":struct.unpack_from(">I",b,24)[0],"creator":b[28:32].decode("ascii","replace"),"original_size":struct.unpack_from(">Q",b,40)[0],"current_size":struct.unpack_from(">Q",b,48)[0],"disk_type":struct.unpack_from(">I",b,60)[0],"checksum":hex(struct.unpack_from(">I",b,64)[0])});return
    if cmd=="qcow2-header-parser":
        need(a,1);b=read(a[0])[:104]
        if len(b)<72 or b[:4]!=b"QFI\xfb":emit({"valid":False});return
        emit({"valid":True,"version":struct.unpack_from(">I",b,4)[0],"backing_file_offset":struct.unpack_from(">Q",b,8)[0],"backing_file_size":struct.unpack_from(">I",b,16)[0],"cluster_bits":struct.unpack_from(">I",b,20)[0],"virtual_size":struct.unpack_from(">Q",b,24)[0],"crypt_method":struct.unpack_from(">I",b,32)[0],"l1_size":struct.unpack_from(">I",b,36)[0],"l1_table_offset":struct.unpack_from(">Q",b,40)[0]});return
    if cmd=="vmdk-descriptor-view":
        need(a,1);txt=read(a[0])[:65536].decode("utf-8","replace");kv={}
        for line in txt.splitlines():
            if "=" in line and not line.lstrip().startswith("#"):k,v=line.split("=",1);kv[k.strip()]=v.strip().strip('"')
        emit({"descriptor":kv,"extents":[x.strip() for x in txt.splitlines() if re.match(r"^(RW|RDONLY|NOACCESS)\s+",x.strip())]});return
    if cmd=="raw-disk-image-resizer":need(a,2);sector=int(a[2]) if len(a)>2 else 512;os.truncate(a[0],int(a[1])*sector);emit({"path":a[0],"sectors":int(a[1]),"sector_size":sector,"bytes":os.path.getsize(a[0])});return
    if cmd in ("sparse-image-converter","simg2img-ocean-cli"):need(a,2);emit(parse_sparse(a[0],a[1]));return
    raise SystemExit("implementation missing")

if __name__=="__main__":
    if len(sys.argv)<2:raise SystemExit("usage: runtime COMMAND [args...]")
    try:main(sys.argv[1],sys.argv[2:])
    except (ValueError,OSError,struct.error,zipfile.BadZipFile,tarfile.TarError) as e:raise SystemExit(str(e))
