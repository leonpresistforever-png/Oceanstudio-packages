#!/usr/bin/env python3
from __future__ import annotations
import ctypes, datetime as dt, fcntl, hashlib, json, mmap, os, shutil, socket, stat, struct, subprocess, sys, tempfile, time
from pathlib import Path

COMMANDS=[
"f2fs-status-inspector","ext4-super-block-dump","inode-usage-analyzer","sparse-file-creator","hole-punch-tester","disk-read-benchmark","disk-write-benchmark","sync-latency-timer","fdatasync-tester","blkdiscard-analyzer","blockdev-geometry","partition-table-view","gpt-header-inspector","mbr-sector-dump","vfat-boot-sector-chk","fat32-cluster-calc","exfat-header-parser","iso9660-browser","squashfs-super-view","ramdisk-builder-cli","tmpfs-usage-tracker","bind-mount-auditor","mount-options-checker","statvfs-free-calc","df-human-sorter","du-depth-limiter","hardlink-counter","broken-symlink-clean","file-timestamp-sync","touch-date-setter","truncate-file-tool","shred-secure-delete","wipefs-magic-scanner","file-allocation-chk","direct-io-benchmark","fallocate-prealloc","flock-file-mutex","lockfile-manager","faccessat-tester","chattr-attribute-view","lsattr-ocean","file-descriptor-duper","fifo-pipe-tester","mknod-device-parser","socket-file-creator","directory-depth-calc","empty-dir-pruner","xattr-metadata-viewer","file-checksum-tree","storage-tree-graph"
]
FS_IOC_GETFLAGS=0x80086601
ATTRS={0x00000001:"secure_delete",0x00000002:"undelete",0x00000004:"compress",0x00000008:"sync",0x00000010:"immutable",0x00000020:"append",0x00000040:"nodump",0x00000080:"noatime",0x00001000:"dirsync",0x00080000:"nocow",0x00100000:"dax"}
MAGICS=[(0,b"\x7fELF","ELF"),(0,b"PK\x03\x04","ZIP/APK"),(0,b"\x1f\x8b","gzip"),(0,b"BZh","bzip2"),(0,b"\xfd7zXZ\x00","xz"),(0,b"7z\xbc\xaf'\x1c","7z"),(0,b"Rar!\x1a\x07","RAR"),(0,b"%PDF","PDF"),(0,b"\x89PNG\r\n\x1a\n","PNG"),(0,b"GIF8","GIF"),(0,b"SQLite format 3\x00","SQLite"),(257,b"ustar","tar/ustar")]

def emit(x):
    if isinstance(x,(dict,list,tuple)): print(json.dumps(x,indent=2,default=str))
    else: print(x)
def need(a,n):
    if len(a)<n:raise SystemExit(f"expected at least {n} arguments")
def human(n):
    n=float(n)
    for u in ("B","KiB","MiB","GiB","TiB"):
        if abs(n)<1024:return f"{n:.2f}{u}"
        n/=1024
    return f"{n:.2f}PiB"
def readat(path,off,n):
    with open(path,"rb",buffering=0) as f:f.seek(off);return f.read(n)
def statv(path):
    s=os.statvfs(path);bs=s.f_frsize or s.f_bsize
    return {"path":str(path),"block_size":bs,"blocks":s.f_blocks,"free_blocks":s.f_bfree,"available_blocks":s.f_bavail,"total_bytes":s.f_blocks*bs,"free_bytes":s.f_bfree*bs,"available_bytes":s.f_bavail*bs,"inodes":s.f_files,"free_inodes":s.f_ffree,"used_percent":round((1-s.f_bavail/max(1,s.f_blocks))*100,2)}
def mounts():
    out=[]
    p=Path("/proc/self/mounts")
    if not p.exists():return out
    for line in p.read_text(errors="replace").splitlines():
        q=line.split()
        if len(q)>=4:out.append({"source":q[0].replace("\\040"," "),"target":q[1].replace("\\040"," "),"fstype":q[2],"options":q[3].split(",")})
    return out
def sysblock(path):
    try:
        st=os.stat(path)
        dev=os.major(st.st_rdev if stat.S_ISBLK(st.st_mode) else st.st_dev);mino=os.minor(st.st_rdev if stat.S_ISBLK(st.st_mode) else st.st_dev)
        base=Path(f"/sys/dev/block/{dev}:{mino}")
        real=base.resolve()
        return real
    except Exception:return None
def ext4(path):
    b=readat(path,1024,1024)
    if len(b)<0x78:raise ValueError("short ext superblock")
    magic=struct.unpack_from("<H",b,0x38)[0]
    return {"magic":hex(magic),"valid_ext":magic==0xEF53,"inodes_count":struct.unpack_from("<I",b,0)[0],"blocks_count_lo":struct.unpack_from("<I",b,4)[0],"free_blocks_lo":struct.unpack_from("<I",b,12)[0],"free_inodes":struct.unpack_from("<I",b,16)[0],"block_size":1024<<struct.unpack_from("<I",b,24)[0],"blocks_per_group":struct.unpack_from("<I",b,32)[0],"inodes_per_group":struct.unpack_from("<I",b,40)[0],"feature_compat":hex(struct.unpack_from("<I",b,92)[0]),"feature_incompat":hex(struct.unpack_from("<I",b,96)[0]),"feature_ro_compat":hex(struct.unpack_from("<I",b,100)[0])}
def mbr(path):
    b=readat(path,0,512)
    if len(b)<512:raise ValueError("short sector")
    parts=[]
    for i in range(4):
        e=b[446+i*16:462+i*16]
        parts.append({"index":i+1,"bootable":e[0]==0x80,"type":hex(e[4]),"lba_start":struct.unpack_from("<I",e,8)[0],"sectors":struct.unpack_from("<I",e,12)[0]})
    return {"signature":b[510:512].hex(),"valid":b[510:512]==b"\x55\xaa","partitions":parts}
def gpt(path):
    b=readat(path,512,512)
    if b[:8]!=b"EFI PART":return {"valid":False,"signature":b[:8].decode("latin1","replace")}
    return {"valid":True,"revision":hex(struct.unpack_from("<I",b,8)[0]),"header_size":struct.unpack_from("<I",b,12)[0],"header_crc32":hex(struct.unpack_from("<I",b,16)[0]),"current_lba":struct.unpack_from("<Q",b,24)[0],"backup_lba":struct.unpack_from("<Q",b,32)[0],"first_usable_lba":struct.unpack_from("<Q",b,40)[0],"last_usable_lba":struct.unpack_from("<Q",b,48)[0],"disk_guid":b[56:72].hex(),"partition_entries_lba":struct.unpack_from("<Q",b,72)[0],"num_entries":struct.unpack_from("<I",b,80)[0],"entry_size":struct.unpack_from("<I",b,84)[0]}
def fat(path):
    b=readat(path,0,512);bps=struct.unpack_from("<H",b,11)[0];spc=b[13];reserved=struct.unpack_from("<H",b,14)[0];fats=b[16];root_entries=struct.unpack_from("<H",b,17)[0];tot16=struct.unpack_from("<H",b,19)[0];tot32=struct.unpack_from("<I",b,32)[0];spf16=struct.unpack_from("<H",b,22)[0];spf32=struct.unpack_from("<I",b,36)[0];spf=spf16 or spf32;total=tot16 or tot32
    root_secs=((root_entries*32)+(bps-1))//bps if bps else 0;data_secs=total-(reserved+fats*spf+root_secs) if total else 0;clusters=data_secs//spc if spc else 0
    kind="FAT32" if clusters>=65525 else "FAT16" if clusters>=4085 else "FAT12"
    return {"jump":b[:3].hex(),"oem":b[3:11].decode("ascii","replace").strip(),"bytes_per_sector":bps,"sectors_per_cluster":spc,"reserved_sectors":reserved,"fat_count":fats,"sectors_per_fat":spf,"total_sectors":total,"cluster_count":clusters,"detected":kind,"boot_signature":b[510:512].hex()}
def exfat(path):
    b=readat(path,0,512)
    return {"valid":b[3:11]==b"EXFAT   ","fs_name":b[3:11].decode("ascii","replace"),"partition_offset":struct.unpack_from("<Q",b,64)[0],"volume_length":struct.unpack_from("<Q",b,72)[0],"fat_offset":struct.unpack_from("<I",b,80)[0],"fat_length":struct.unpack_from("<I",b,84)[0],"cluster_heap_offset":struct.unpack_from("<I",b,88)[0],"cluster_count":struct.unpack_from("<I",b,92)[0],"root_cluster":struct.unpack_from("<I",b,96)[0],"bytes_per_sector":1<<b[108],"sectors_per_cluster":1<<b[109]}
def squash(path):
    b=readat(path,0,96);magic=struct.unpack_from("<I",b,0)[0] if len(b)>=4 else 0
    return {"magic":hex(magic),"valid":magic==0x73717368,"inodes":struct.unpack_from("<I",b,4)[0] if len(b)>=8 else None,"mkfs_time":struct.unpack_from("<I",b,8)[0] if len(b)>=12 else None,"block_size":struct.unpack_from("<I",b,12)[0] if len(b)>=16 else None,"compression_id":struct.unpack_from("<H",b,20)[0] if len(b)>=22 else None,"block_log":struct.unpack_from("<H",b,22)[0] if len(b)>=24 else None,"fragments":struct.unpack_from("<I",b,28)[0] if len(b)>=32 else None}
def iso(path):
    b=readat(path,16*2048,2048)
    return {"valid":len(b)>=7 and b[1:6]==b"CD001","type":b[0] if b else None,"identifier":b[1:6].decode("ascii","replace") if len(b)>=6 else "","version":b[6] if len(b)>=7 else None,"system_id":b[8:40].decode("ascii","replace").strip() if len(b)>=40 else "","volume_id":b[40:72].decode("ascii","replace").strip() if len(b)>=72 else "","volume_space_blocks":struct.unpack_from("<I",b,80)[0] if len(b)>=84 else None}
def treefiles(root):
    root=Path(root)
    return [p for p in root.rglob("*") if p.is_file() and not p.is_symlink()]
def dir_size(path,maxdepth=None):
    root=Path(path);total=0;by={}
    for p in root.rglob("*"):
        try:
            rel=p.relative_to(root);d=len(rel.parts)
            if maxdepth is not None and d>maxdepth:continue
            if p.is_file() and not p.is_symlink():
                z=p.stat().st_size;total+=z;by[str(rel)]=z
        except OSError:pass
    return total,by
def attrs(path):
    flags=ctypes.c_uint(0)
    try:
        fd=os.open(path,os.O_RDONLY|getattr(os,"O_NONBLOCK",0))
        try:fcntl.ioctl(fd,FS_IOC_GETFLAGS,flags,True)
        finally:os.close(fd)
        v=flags.value
        return {"raw":hex(v),"flags":[name for bit,name in ATTRS.items() if v&bit]}
    except Exception as e:return {"error":str(e),"flags":[]}
def hash_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()
def main(cmd,a):
    if cmd not in COMMANDS:raise SystemExit("unknown command")
    if cmd=="f2fs-status-inspector":
        need(a,1);p=Path(a[0])
        if p.is_dir():
            vals={}
            for f in p.iterdir():
                if f.is_file():
                    try:vals[f.name]=f.read_text(errors="replace").strip()[:500]
                    except Exception:pass
            emit({"path":str(p),"sysfs":vals});return
        b=readat(p,1024,16);magic=struct.unpack_from("<I",b,0)[0] if len(b)>=4 else 0;emit({"magic":hex(magic),"valid":magic==0xF2F52010});return
    if cmd=="ext4-super-block-dump":need(a,1);emit(ext4(a[0]));return
    if cmd=="inode-usage-analyzer":need(a,1);emit(statv(a[0]));return
    if cmd=="sparse-file-creator":need(a,2);Path(a[0]).parent.mkdir(parents=True,exist_ok=True);os.truncate(a[0],int(a[1]));s=os.stat(a[0]);emit({"size":s.st_size,"allocated_bytes":s.st_blocks*512,"sparse":s.st_blocks*512<s.st_size});return
    if cmd=="hole-punch-tester":
        need(a,1);p=a[0];off=int(a[1]) if len(a)>1 else 0;length=int(a[2]) if len(a)>2 else 4096;libc=ctypes.CDLL(None,use_errno=True);fn=getattr(libc,"fallocate",None)
        if not fn:emit({"supported":False,"reason":"libc fallocate unavailable"});return
        fd=os.open(p,os.O_RDWR);rc=fn(fd,0x01|0x02,ctypes.c_longlong(off),ctypes.c_longlong(length));err=ctypes.get_errno();os.close(fd);emit({"supported":rc==0,"errno":err});return
    if cmd=="disk-read-benchmark":
        need(a,1);bs=int(a[1]) if len(a)>1 else 1024*1024;n=0;t=time.perf_counter()
        with open(a[0],"rb",buffering=0) as f:
            while True:
                b=f.read(bs)
                if not b:break
                n+=len(b)
        sec=max(time.perf_counter()-t,1e-9);emit({"bytes":n,"seconds":sec,"bytes_per_sec":n/sec,"human_per_sec":human(n/sec)});return
    if cmd=="disk-write-benchmark":
        need(a,2);n=int(a[1]);bs=int(a[2]) if len(a)>2 else 1024*1024;buf=b"\0"*min(bs,n);w=0;t=time.perf_counter()
        with open(a[0],"wb",buffering=0) as f:
            while w<n:
                q=min(len(buf),n-w);f.write(buf[:q]);w+=q
            os.fsync(f.fileno())
        sec=max(time.perf_counter()-t,1e-9);emit({"bytes":w,"seconds":sec,"bytes_per_sec":w/sec});return
    if cmd=="sync-latency-timer":
        t=time.perf_counter();os.sync();emit({"seconds":time.perf_counter()-t});return
    if cmd=="fdatasync-tester":
        need(a,1);fd=os.open(a[0],os.O_RDWR|os.O_CREAT,0o600);os.write(fd,b"x");t=time.perf_counter();os.fdatasync(fd);sec=time.perf_counter()-t;os.close(fd);emit({"seconds":sec});return
    if cmd=="blkdiscard-analyzer":
        need(a,1);sb=sysblock(a[0]);q=(sb/"queue") if sb else None
        def rd(n):
            try:return (q/n).read_text().strip()
            except Exception:return None
        emit({"sysfs":str(sb) if sb else None,"discard_granularity":rd("discard_granularity"),"discard_max_bytes":rd("discard_max_bytes"),"rotational":rd("rotational")});return
    if cmd=="blockdev-geometry":
        need(a,1);p=a[0];s=os.stat(p);sb=sysblock(p);q=(sb/"queue") if sb else None
        vals={"mode":oct(s.st_mode),"size":s.st_size,"major":os.major(s.st_rdev) if stat.S_ISBLK(s.st_mode) else os.major(s.st_dev),"minor":os.minor(s.st_rdev) if stat.S_ISBLK(s.st_mode) else os.minor(s.st_dev),"sysfs":str(sb) if sb else None}
        for n in ("logical_block_size","physical_block_size","minimum_io_size","optimal_io_size","rotational"):
            try:vals[n]=(q/n).read_text().strip()
            except Exception:vals[n]=None
        emit(vals);return
    if cmd=="partition-table-view":need(a,1);emit({"mbr":mbr(a[0]),"gpt":gpt(a[0])});return
    if cmd=="gpt-header-inspector":need(a,1);emit(gpt(a[0]));return
    if cmd=="mbr-sector-dump":need(a,1);emit(mbr(a[0]));return
    if cmd=="vfat-boot-sector-chk":need(a,1);emit(fat(a[0]));return
    if cmd=="fat32-cluster-calc":need(a,4);cluster=int(a[0]);spc=int(a[1]);bps=int(a[2]);data=int(a[3]);emit({"cluster":cluster,"byte_offset":(data+(cluster-2)*spc)*bps,"cluster_bytes":spc*bps});return
    if cmd=="exfat-header-parser":need(a,1);emit(exfat(a[0]));return
    if cmd=="iso9660-browser":need(a,1);emit(iso(a[0]));return
    if cmd=="squashfs-super-view":need(a,1);emit(squash(a[0]));return
    if cmd=="ramdisk-builder-cli":
        size=int(a[0]) if a else 64*1024*1024;target=a[1] if len(a)>1 else tempfile.mkdtemp(prefix="ocean-ramdisk-");Path(target).mkdir(parents=True,exist_ok=True);emit({"target":target,"bytes":size,"mount_command":f"mount -t tmpfs -o size={size} tmpfs {target}","note":"mount requires kernel permission/root; directory staged regardless"});return
    if cmd=="tmpfs-usage-tracker":
        out=[]
        for m in mounts():
            if m["fstype"]=="tmpfs":
                try:out.append({**m,**statv(m["target"])})
                except Exception:out.append(m)
        emit(out);return
    if cmd=="bind-mount-auditor":
        seen={};out=[]
        for m in mounts():
            key=(m["source"],m["fstype"]);seen.setdefault(key,[]).append(m["target"])
        for (src,fs),targets in seen.items():
            if len(targets)>1:out.append({"source":src,"fstype":fs,"targets":targets,"possible_bind_or_shared_source":True})
        emit(out);return
    if cmd=="mount-options-checker":
        wanted=set(a[0].split(",")) if a else {"noatime","nodiratime","nosuid","nodev","noexec"};emit([{**m,"present":sorted(wanted&set(m["options"])),"missing":sorted(wanted-set(m["options"]))} for m in mounts()]);return
    if cmd=="statvfs-free-calc":need(a,1);emit(statv(a[0]));return
    if cmd=="df-human-sorter":
        out=[]
        for m in mounts():
            try:out.append({**m,**statv(m["target"])})
            except Exception:pass
        out.sort(key=lambda x:x["used_percent"],reverse=True);emit(out);return
    if cmd=="du-depth-limiter":need(a,1);d=int(a[1]) if len(a)>1 else 1;t,b=dir_size(a[0],d);emit({"total":t,"entries":[{"path":k,"bytes":v} for k,v in sorted(b.items(),key=lambda kv:kv[1],reverse=True)]});return
    if cmd=="hardlink-counter":
        need(a,1);ino={}
        for p in treefiles(a[0]):
            try:s=p.stat();ino.setdefault((s.st_dev,s.st_ino),[]).append(str(p))
            except OSError:pass
        emit([{"links":len(v),"paths":v} for v in ino.values() if len(v)>1]);return
    if cmd=="broken-symlink-clean":
        need(a,1);delete="--delete" in a;bad=[]
        for p in Path(a[0]).rglob("*"):
            if p.is_symlink() and not p.exists():bad.append(str(p));p.unlink() if delete else None
        emit({"broken":bad,"deleted":delete});return
    if cmd=="file-timestamp-sync":need(a,2);s=os.stat(a[0]);os.utime(a[1],ns=(s.st_atime_ns,s.st_mtime_ns));emit({"source":a[0],"target":a[1],"atime_ns":s.st_atime_ns,"mtime_ns":s.st_mtime_ns});return
    if cmd=="touch-date-setter":need(a,2);t=dt.datetime.fromisoformat(a[1].replace("Z","+00:00")).timestamp();os.utime(a[0],(t,t));emit({"path":a[0],"timestamp":t});return
    if cmd=="truncate-file-tool":need(a,2);os.truncate(a[0],int(a[1]));emit({"path":a[0],"size":os.path.getsize(a[0])});return
    if cmd=="shred-secure-delete":
        need(a,1);p=Path(a[0]);passes=int(a[1]) if len(a)>1 and a[1].isdigit() else 3;do="--delete" in a
        if not p.is_file():raise SystemExit("regular file required")
        n=p.stat().st_size
        if do:
            with open(p,"r+b",buffering=0) as f:
                for i in range(passes):
                    f.seek(0);remain=n
                    while remain:
                        b=os.urandom(min(1024*1024,remain));f.write(b);remain-=len(b)
                    f.flush();os.fsync(f.fileno())
            p.unlink()
        emit({"path":str(p),"bytes":n,"passes":passes,"deleted":do,"warning":"overwrite cannot guarantee media sanitization on flash/CoW filesystems"});return
    if cmd=="wipefs-magic-scanner":
        need(a,1);size=os.path.getsize(a[0]);b=readat(a[0],0,min(size,4096));found=[]
        for off,mg,name in MAGICS:
            if off+len(mg)<=len(b) and b[off:off+len(mg)]==mg:found.append({"offset":off,"type":name})
        try:
            if ext4(a[0])["valid"]:found.append({"offset":1024+56,"type":"ext filesystem"})
        except Exception:pass
        emit(found);return
    if cmd=="file-allocation-chk":need(a,1);s=os.stat(a[0]);emit({"logical_bytes":s.st_size,"allocated_bytes":s.st_blocks*512,"ratio":(s.st_blocks*512/max(1,s.st_size)),"sparse":s.st_blocks*512<s.st_size});return
    if cmd=="direct-io-benchmark":
        need(a,1);flag=getattr(os,"O_DIRECT",0)
        if not flag:emit({"supported":False,"reason":"O_DIRECT unavailable"});return
        bs=int(a[1]) if len(a)>1 else 4096;fd=None
        try:
            fd=os.open(a[0],os.O_RDONLY|flag);buf=mmap.mmap(-1,bs);t=time.perf_counter();n=os.readv(fd,[buf]);sec=max(time.perf_counter()-t,1e-9);emit({"supported":True,"bytes":n,"seconds":sec,"bytes_per_sec":n/sec})
        except OSError as e:emit({"supported":False,"errno":e.errno,"error":str(e)})
        finally:
            if fd is not None:os.close(fd)
        return
    if cmd=="fallocate-prealloc":need(a,2);fd=os.open(a[0],os.O_RDWR|os.O_CREAT,0o600);os.posix_fallocate(fd,0,int(a[1]));os.close(fd);emit({"path":a[0],"size":os.path.getsize(a[0]),"allocated":os.stat(a[0]).st_blocks*512});return
    if cmd=="flock-file-mutex":
        need(a,1);timeout=float(a[1]) if len(a)>1 else 1;f=open(a[0],"a+");start=time.monotonic();ok=False
        while time.monotonic()-start<=timeout:
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);ok=True;break
            except BlockingIOError:time.sleep(.02)
        if ok:fcntl.flock(f,fcntl.LOCK_UN)
        f.close();emit({"acquired":ok,"wait_seconds":time.monotonic()-start});return
    if cmd=="lockfile-manager":
        need(a,1);timeout=float(a[1]) if len(a)>1 else 1;start=time.monotonic();fd=None
        while time.monotonic()-start<=timeout:
            try:fd=os.open(a[0],os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,str(os.getpid()).encode());break
            except FileExistsError:time.sleep(.02)
        ok=fd is not None
        if fd is not None:os.close(fd);os.unlink(a[0])
        emit({"acquired":ok,"wait_seconds":time.monotonic()-start});return
    if cmd=="faccessat-tester":need(a,1);emit({"exists":os.path.exists(a[0]),"read":os.access(a[0],os.R_OK),"write":os.access(a[0],os.W_OK),"execute":os.access(a[0],os.X_OK)});return
    if cmd=="chattr-attribute-view":need(a,1);emit({"path":a[0],**attrs(a[0])});return
    if cmd=="lsattr-ocean":need(a,1);emit([{"path":str(p),**attrs(p)} for p in Path(a[0]).iterdir()]);return
    if cmd=="file-descriptor-duper":
        need(a,1);fd=os.open(a[0],os.O_RDONLY);dup=os.dup(fd);same=os.fstat(fd).st_ino==os.fstat(dup).st_ino;emit({"fd":fd,"dup_fd":dup,"same_inode":same});os.close(dup);os.close(fd);return
    if cmd=="fifo-pipe-tester":
        base=Path(a[0]) if a else Path(tempfile.mkdtemp())/"ocean.fifo"
        if base.exists():base.unlink()
        os.mkfifo(base,0o600);r=os.open(base,os.O_RDONLY|os.O_NONBLOCK);w=os.open(base,os.O_WRONLY|os.O_NONBLOCK);msg=b"ocean-fifo";os.write(w,msg);got=os.read(r,128);os.close(w);os.close(r);base.unlink();emit({"roundtrip":got.decode(),"ok":got==msg});return
    if cmd=="mknod-device-parser":
        need(a,1);s=os.stat(a[0]);isdev=stat.S_ISCHR(s.st_mode) or stat.S_ISBLK(s.st_mode);emit({"path":a[0],"type":"char" if stat.S_ISCHR(s.st_mode) else "block" if stat.S_ISBLK(s.st_mode) else "other","major":os.major(s.st_rdev) if isdev else None,"minor":os.minor(s.st_rdev) if isdev else None});return
    if cmd=="socket-file-creator":
        need(a,1);p=a[0]
        try:os.unlink(p)
        except FileNotFoundError:pass
        s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.bind(p);st=os.stat(p);emit({"path":p,"is_socket":stat.S_ISSOCK(st.st_mode)});s.close();os.unlink(p);return
    if cmd=="directory-depth-calc":
        need(a,1);root=Path(a[0]);maxd=0;deep=str(root)
        for p in root.rglob("*"):
            if p.is_dir():
                d=len(p.relative_to(root).parts)
                if d>maxd:maxd=d;deep=str(p)
        emit({"max_depth":maxd,"deepest":deep});return
    if cmd=="empty-dir-pruner":
        need(a,1);delete="--delete" in a;root=Path(a[0]);empty=[]
        for p in sorted([x for x in root.rglob("*") if x.is_dir()],key=lambda x:len(x.parts),reverse=True):
            try:
                if not any(p.iterdir()):empty.append(str(p));p.rmdir() if delete else None
            except OSError:pass
        emit({"empty":empty,"deleted":delete});return
    if cmd=="xattr-metadata-viewer":
        need(a,1);out={}
        try:
            for n in os.listxattr(a[0]):
                try:v=os.getxattr(a[0],n);out[n]={"hex":v.hex(),"utf8":v.decode("utf-8","replace")}
                except OSError as e:out[n]={"error":str(e)}
        except OSError as e:emit({"error":str(e)});return
        emit(out);return
    if cmd=="file-checksum-tree":
        need(a,1);root=Path(a[0]);rows=[]
        for p in sorted(treefiles(root)):rows.append({"path":str(p.relative_to(root)),"sha256":hash_file(p),"bytes":p.stat().st_size})
        emit(rows);return
    if cmd=="storage-tree-graph":
        need(a,1);root=Path(a[0]);rows=[]
        for p in root.rglob("*"):
            try:
                if p.is_dir():
                    total,_=dir_size(p);rows.append((len(p.relative_to(root).parts),str(p.relative_to(root)),total))
            except OSError:pass
        for d,name,total in sorted(rows):print("  "*d+f"{name or '.'} [{human(total)}]")
        return
    raise SystemExit("implementation missing")
if __name__=="__main__":
    if len(sys.argv)<2:raise SystemExit("usage: runtime COMMAND [args...]")
    try:main(sys.argv[1],sys.argv[2:])
    except (ValueError,OSError,struct.error) as e:raise SystemExit(str(e))
