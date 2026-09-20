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
    return {"valid":valid,"header_size":struct.unpack_from("<I",b,8)[0] if valid else None,"version":hex(struct.unpack_from("<I",b,12)[0]) if len(b)>=16 else None,"flags":hex(struct.unpack_from("<I",b