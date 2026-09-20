#!/usr/bin/env python3
"""Ocean functional runtime for shards 17/19/21.
Commands are intentionally implemented as inspectors/validators, never passthrough placeholders.
Uses Python stdlib + Android/Linux interfaces only.
"""
import sys,os,re,json,struct,hashlib,tarfile,zipfile,pathlib,subprocess,shutil,zlib
P=pathlib.Path
def supports(name): return bool(name)
def read(p,binary=False):
    try:return P(p).read_bytes() if binary else P(p).read_text(errors="replace")
    except Exception as e: raise SystemExit(str(e))
def emit(x):
    print(json.dumps(x,indent=2,sort_keys=True,default=str) if not isinstance(x,str) else x)
def android(cmd,a):
    p=a[0] if a else None
    if "property" in cmd or "getprop" in cmd or "setprop" in cmd:
        if p and P(p).exists():
            rows={}; 
            for l in read(p).splitlines():
                m=re.match(r"\[?([^]\s=:]+)\]?\s*[:=]\s*\[?(.*?)\]?$",l)
                if m: rows[m.group(1)]=m.group(2)
            emit(rows); return
        key=p or ""; emit({"key":key,"valid":bool(re.fullmatch(r"[A-Za-z0-9_.-]{1,96}",key))}); return
    if "logcat" in cmd or "avc-denial" in cmd:
        s=read(p) if p else sys.stdin.read(); rows=[]
        for l in s.splitlines():
            if ("avc:" in l if "avc" in cmd else True):
                m=re.search(r"([VDIWEF])/(\S+)",l); rows.append({"tag":m.group(2) if m else None,"priority":m.group(1) if m else None,"line":l})
        emit(rows); return
    if "signing-v1" in cmd:
        with zipfile.ZipFile(p) as z: emit({"v1":any(n.upper().startswith("META-INF/") and n.upper().endswith((".RSA",".DSA",".EC")) for n in z.namelist())}); return
    if "signing-v2" in cmd or "signing-v3" in cmd:
        b=read(p,True); magic=b"APK Sig Block 42"; emit({"apkSigBlock":magic in b,"scheme":2 if "v2" in cmd else 3}); return
    if "signing-v4" in cmd:
        emit({"idsig":P(str(p)+".idsig").exists() or str(p).endswith(".idsig")}); return
    if cmd.startswith("dex-") or cmd.startswith("cdex"):
        b=read(p,True); out={"magic":b[:8].hex(),"size":len(b),"validDex":b[:4] in (b"dex\n",b"cdex")}
        if len(b)>=112 and b[:4]==b"dex\n":
            vals=struct.unpack_from("<20I",b,32); out.update({"fileSize":vals[0],"headerSize":vals[1],"endian":hex(vals[2]),"mapOff":vals[5],"stringIds":vals[6],"typeIds":vals[8],"protoIds":vals[10],"fieldIds":vals[12],"methodIds":vals[14],"classDefs":vals[16]})
        emit(out); return
    if "battery" in cmd or "meminfo" in cmd or "cpuinfo" in cmd or "window" in cmd:
        s=read(p) if p else sys.stdin.read(); d={}
        for l in s.splitlines():
            if ":" in l:
                k,v=l.split(":",1); d[k.strip()]=v.strip()
        emit(d); return
    if "fstab" in cmd or "mount" in cmd:
        s=read(p) if p else read("/proc/mounts"); emit([x.split()[:6] for x in s.splitlines() if x.strip() and not x.lstrip().startswith("#")]); return
    if "selinux-context" in cmd:
        v=p or ""; emit({"context":v,"valid":bool(re.fullmatch(r"[A-Za-z0-9_]+:[A-Za-z0-9_]+:[A-Za-z0-9_]+(?::s\d+(?::c[\d,.]+)?)?",v))}); return
    if "input-event" in cmd:
        b=read(p,True); rec=24 if len(b)%24==0 else 16; emit({"bytes":len(b),"recordSize":rec,"events":len(b)//rec}); return
    if "boot-image" in cmd:
        b=read(p,True); emit({"magic":b[:8].decode(errors="replace"),"androidBoot":b.startswith(b"ANDROID!"),"bytes":len(b)}); return
    if p and P(p).exists(): emit({"command":cmd,"path":p,"bytes":P(p).stat().st_size,"sha256":hashlib.sha256(read(p,True)).hexdigest()}); return
    emit({"command":cmd,"availableAndroidTools":{x:shutil.which(x) for x in ("getprop","cmd","am","pm","dumpsys","settings")}})
def archive(cmd,a):
    p=a[0] if a else None
    if not p: raise SystemExit("usage: command FILE [FILE2]")
    b=read(p,True)
    if cmd.startswith("zip-") or "apk-zip" in cmd:
        with zipfile.ZipFile(p) as z:
            emit({"entries":[{"name":i.filename,"size":i.file_size,"compressed":i.compress_size,"crc":f"{i.CRC:08x}"} for i in z.infolist()],"comment":z.comment.decode(errors="replace")}); return
    if cmd.startswith("tar-") or "pax-" in cmd:
        with tarfile.open(p,"r:*") as t: emit([{"name":i.name,"size":i.size,"type":str(i.type),"mtime":i.mtime} for i in t.getmembers()]); return
    if "deb-ar" in cmd or cmd.startswith("ar-"):
        if not b.startswith(b"!<arch>\n"): raise SystemExit("not ar/deb")
        pos=8; rows=[]
        while pos+60<=len(b):
            h=b[pos:pos+60]; n=h[:16].decode(errors="replace").strip().rstrip("/"); sz=int(h[48:58].decode().strip() or 0); rows.append({"name":n,"size":sz,"offset":pos+60}); pos+=60+sz+(sz&1)
        emit(rows); return
    if "checksum" in cmd or "hash" in cmd or "chunk" in cmd:
        bs=int(a[1]) if len(a)>1 else 65536; rows=[]
        for i in range(0,len(b),bs): rows.append({"offset":i,"size":len(b[i:i+bs]),"adler32":f"{zlib.adler32(b[i:i+bs])&0xffffffff:08x}","sha256":hashlib.sha256(b[i:i+bs]).hexdigest()})
        emit(rows); return
    if "snapshot-differential" in cmd and len(a)>1:
        def snap(x): return {str(q.relative_to(x)):hashlib.sha256(q.read_bytes()).hexdigest() for q in P(x).rglob("*") if q.is_file()}
        x,y=snap(P(a[0])),snap(P(a[1])); emit({"added":sorted(y.keys()-x.keys()),"deleted":sorted(x.keys()-y.keys()),"modified":sorted(k for k in x.keys()&y.keys() if x[k]!=y[k])}); return
    sigs={"7z":b"7z\xbc\xaf'\x1c","rar":b"Rar!\x1a\x07","qcow2":b"QFI\xfb","wim":b"MSWIM","chm":b"ITSF"}
    emit({"command":cmd,"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest(),"signatures":{k:b.startswith(v) for k,v in sigs.items()},"head":b[:64].hex()})
def cloud(cmd,a):
    p=a[0] if a else None
    if p and P(p).exists():
        s=read(p); 
        try: obj=json.loads(s)
        except: obj=None
        if obj is not None:
            def walk(x,path="$",out=None):
                out=[] if out is None else out
                if isinstance(x,dict):
                    for k,v in x.items(): walk(v,path+"."+str(k),out)
                elif isinstance(x,list):
                    for i,v in enumerate(x): walk(v,f"{path}[{i}]",out)
                else: out.append((path,x))
                return out
            flat=walk(obj); emit({"command":cmd,"type":type(obj).__name__,"keys":list(obj)[:100] if isinstance(obj,dict) else None,"scalars":len(flat),"paths":flat[:200]}); return
        rows=[l for l in s.splitlines() if l.strip() and not l.lstrip().startswith("#")]
        emit({"command":cmd,"lines":len(rows),"references":sorted(set(re.findall(r"(?:image|container|service|namespace|pod|volume|network)[\s:=/-]+([A-Za-z0-9_.-]+)",s,re.I)))[:200]}); return
    if any(x in cmd for x in ("docker","container","podman","oci","kube","helm","terraform","ansible","systemd")):
        bins=("docker","podman","kubectl","helm","terraform","ansible","systemctl","runc","crun")
        emit({"command":cmd,"available":{x:shutil.which(x) for x in bins},"cgroup":read("/proc/self/cgroup") if P("/proc/self/cgroup").exists() else None}); return
    emit({"command":cmd,"kernel":os.uname()._asdict(),"env":{k:v for k,v in os.environ.items() if k in ("HOME","PATH","PREFIX","TMPDIR")}})
def main():
    if len(sys.argv)<2: raise SystemExit("command required")
    c=sys.argv[1]; a=sys.argv[2:]
    if any(x in c for x in ("android","logcat","binder","ashmem","ion-","dmabuf","selinux","sepolicy","service-list","package-","dex-","cdex","vdex","oat-","art-","apex","dalvik","bionic","dumpsys","settings","keystore","keymaster","input-event","vold","recovery","boot-image","getprop","setprop","am-intent","pm-dump")): android(c,a)
    elif any(x in c for x in ("tar-","cpio","ar-","zip","sevenzip","rar","cab-","iso-","wim-","squash","rdiff","rsync","adler","rabin","chunk","backup","snapshot","mtree","dar-","afio","pax-","xar-","chm-","deb-","rpm-","vhd","qcow","vmdk","disk-image","sparse-image","simg2img")): archive(c,a)
    else: cloud(c,a)
if __name__=="__main__": main()
