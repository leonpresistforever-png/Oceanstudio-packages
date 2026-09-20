#!/usr/bin/env python3
import importlib.util,pathlib,subprocess,sys,tempfile,struct,os
rt=pathlib.Path(sys.argv[1]);s=importlib.util.spec_from_file_location("r",rt);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
assert len(m.COMMANDS)==50 and len(set(m.COMMANDS))==50
def run(cmd,*args):
    r=subprocess.run([sys.executable,str(rt),cmd,*map(str,args)],text=True,capture_output=True)
    if r.returncode!=0:raise AssertionError((cmd,r.returncode,r.stdout,r.stderr))
    if not (r.stdout.strip() or cmd=="storage-tree-graph"):raise AssertionError((cmd,"empty output"))
    return r.stdout
with tempfile.TemporaryDirectory() as td:
    d=pathlib.Path(td);(d/"sub/deep").mkdir(parents=True);(d/"empty").mkdir()
    data=d/"data.bin";data.write_bytes((b"OceanStudio"*1024)+b"x"*8192)
    other=d/"other.bin";other.write_bytes(b"other")
    os.link(data,d/"hardlink.bin")
    (d/"broken").symlink_to(d/"missing")
    f2=d/"f2fs.img";f2.write_bytes(b"\0"*2048)
    with f2.open("r+b") as f:f.seek(1024);f.write(struct.pack("<I",0xF2F52010))
    ext=d/"ext4.img";ext.write_bytes(b"\0"*4096)
    with ext.open("r+b") as f:
        f.seek(1024);sb=bytearray(1024);struct.pack_into("<I",sb,0,100);struct.pack_into("<I",sb,4,1000);struct.pack_into("<I",sb,12,500);struct.pack_into("<I",sb,16,50);struct.pack_into("<I",sb,24,2);struct.pack_into("<I",sb,32,8192);struct.pack_into("<I",sb,40,1000);struct.pack_into("<H",sb,0x38,0xEF53);f.write(sb)
    disk=d/"disk.img";disk.write_bytes(b"\0"*131072)
    with disk.open("r+b") as f:
        b=bytearray(512);b[446]=0x80;b[450]=0x83;struct.pack_into("<I",b,454,2048);struct.pack_into("<I",b,458,4096);b[510:512]=b"\x55\xaa";f.write(b)
        f.seek(512);g=bytearray(512);g[:8]=b"EFI PART";struct.pack_into("<I",g,8,0x00010000);struct.pack_into("<I",g,12,92);struct.pack_into("<Q",g,24,1);struct.pack_into("<Q",g,32,255);struct.pack_into("<Q",g,40,34);struct.pack_into("<Q",g,48,220);struct.pack_into("<Q",g,72,2);struct.pack_into("<I",g,80,128);struct.pack_into("<I",g,84,128);f.write(g)
    fat=d/"fat.img";fb=bytearray(512);fb[:3]=b"\xebX\x90";fb[3:11]=b"MSDOS5.0";struct.pack_into("<H",fb,11,512);fb[13]=8;struct.pack_into("<H",fb,14,32);fb[16]=2;struct.pack_into("<I",fb,32,1000000);struct.pack_into("<I",fb,36,1000);fb[510:512]=b"\x55\xaa";fat.write_bytes(fb)
    ex=d/"exfat.img";eb=bytearray(512);eb[:3]=b"\xebv\x90";eb[3:11]=b"EXFAT   ";struct.pack_into("<Q",eb,64,0);struct.pack_into("<Q",eb,72,100000);struct.pack_into("<I",eb,80,24);struct.pack_into("<I",eb,84,100);struct.pack_into("<I",eb,88,200);struct.pack_into("<I",eb,92,1000);struct.pack_into("<I",eb,96,2);eb[108]=9;eb[109]=3;ex.write_bytes(eb)
    iso=d/"x.iso";iso.write_bytes(b"\0"*(17*2048))
    with iso.open("r+b") as f:f.seek(16*2048);p=bytearray(2048);p[0]=1;p[1:6]=b"CD001";p[6]=1;p[8:40]=b"OCEAN".ljust(32,b" ");p[40:72]=b"TESTVOL".ljust(32,b" ");struct.pack_into("<I",p,80,17);f.write(p)
    sq=d/"sq.img";q=bytearray(96);struct.pack_into("<I",q,0,0x73717368);struct.pack_into("<I",q,4,3);struct.pack_into("<I",q,12,131072);struct.pack_into("<H",q,20,1);sq.write_bytes(q)
    cases={
      "f2fs-status-inspector":(f2,),"ext4-super-block-dump":(ext,),"inode-usage-analyzer":(d,),
      "sparse-file-creator":(d/"sparse.bin","1048576"),"hole-punch-tester":(data,"0","4096"),
      "disk-read-benchmark":(data,"4096"),"disk-write-benchmark":(d/"write.bin","65536","4096"),
      "sync-latency-timer":(),"fdatasync-tester":(d/"sync.bin",),"blkdiscard-analyzer":(data,),
      "blockdev-geometry":(data,),"partition-table-view":(disk,),"gpt-header-inspector":(disk,),
      "mbr-sector-dump":(disk,),"vfat-boot-sector-chk":(fat,),"fat32-cluster-calc":("5","8","512","100"),
      "exfat-header-parser":(ex,),"iso9660-browser":(iso,),"squashfs-super-view":(sq,),
      "ramdisk-builder-cli":("1048576",d/"ramstage"),"tmpfs-usage-tracker":(),"bind-mount-auditor":(),
      "mount-options-checker":(),"statvfs-free-calc":(d,),"df-human-sorter":(),"du-depth-limiter":(d,"2"),
      "hardlink-counter":(d,),"broken-symlink-clean":(d,),"file-timestamp-sync":(data,other),
      "touch-date-setter":(other,"2026-09-20T00:00:00+00:00"),"truncate-file-tool":(d/"truncate.bin","1024"),
      "shred-secure-delete":(data,"1"),"wipefs-magic-scanner":(ext,),"file-allocation-chk":(d/"sparse.bin",),
      "direct-io-benchmark":(data,"4096"),"fallocate-prealloc":(d/"alloc.bin","65536"),
      "flock-file-mutex":(d/"lock","0.2"),"lockfile-manager":(d/"lockfile","0.2"),
      "faccessat-tester":(data,),"chattr-attribute-view":(data,),"lsattr-ocean":(d,),
      "file-descriptor-duper":(data,),"fifo-pipe-tester":(d/"fifo",),"mknod-device-parser":("/dev/null",),
      "socket-file-creator":(d/"sock",),"directory-depth-calc":(d,),"empty-dir-pruner":(d,),
      "xattr-metadata-viewer":(data,),"file-checksum-tree":(d,),"storage-tree-graph":(d,)
    }
    assert set(cases)==set(m.COMMANDS),(set(m.COMMANDS)-set(cases),set(cases)-set(m.COMMANDS))
    for cmd,args in cases.items():run(cmd,*args)
print("SUCCESS: exercised 50/50 shard-09 filesystem/storage commands")
