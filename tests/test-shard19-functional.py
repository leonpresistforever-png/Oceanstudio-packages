#!/usr/bin/env python3
import hashlib,importlib.util,io,json,os,pathlib,struct,subprocess,sys,tarfile,tempfile,zipfile,zlib
rt=pathlib.Path(sys.argv[1]);s=importlib.util.spec_from_file_location("r",rt);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
assert len(m.COMMANDS)==50 and len(set(m.COMMANDS))==50
def run(cmd,*args):
    r=subprocess.run([sys.executable,str(rt),cmd,*map(str,args)],text=True,capture_output=True)
    if r.returncode!=0:raise AssertionError((cmd,r.returncode,r.stdout,r.stderr))
    if not r.stdout.strip():raise AssertionError((cmd,"empty output"))
    return r.stdout
def ar_header(name,data):
    n=(name+"/").encode()[:16].ljust(16,b" ")
    h=n+b"0".ljust(12)+b"0".ljust(6)+b"0".ljust(6)+b"100644".ljust(8)+str(len(data)).encode().ljust(10)+b"`\n"
    return h+data+(b"\n" if len(data)%2 else b"")
def newc_entry(name,data=b"",magic=b"070701"):
    names=name.encode()+b"\0";vals=[1,0o100644,0,0,1,0,len(data),0,0,0,0,len(names),sum(data) if magic==b"070702" else 0]
    h=magic+b"".join(f"{v:08x}".encode() for v in vals);x=h+names;x+=b"\0"*((4-len(x)%4)%4);x+=data;x+=b"\0"*((4-len(x)%4)%4);return x
def odc_entry(name,data=b""):
    nm=name.encode()+b"\0";fields=[0,1,0o100644,0,0,1,0,0,0,len(nm),len(data)]
    h=b"070707"+f"{fields[0]:06o}{fields[1]:06o}{fields[2]:06o}{fields[3]:06o}{fields[4]:06o}{fields[5]:06o}{fields[6]:06o}{fields[7]:011o}{fields[9]:06o}{fields[10]:011o}".encode()
    return h+nm+data
with tempfile.TemporaryDirectory() as td:
    d=pathlib.Path(td);src=d/"src";src.mkdir();(src/"a.txt").write_text("alpha\n");(src/"b.bin").write_bytes(b"beta"*2048)
    src2=d/"src2";src2.mkdir();(src2/"a.txt").write_text("changed\n");(src2/"c.txt").write_text("new\n")
    gnu=d/"gnu.tar"
    with tarfile.open(gnu,"w",format=tarfile.GNU_FORMAT) as t:
        data=b"hello";ti=tarfile.TarInfo("x"*140+".txt");ti.size=len(data);t.addfile(ti,io.BytesIO(data))
    pax=d/"pax.tar"
    with tarfile.open(pax,"w",format=tarfile.PAX_FORMAT) as t:
        data=b"pax";ti=tarfile.TarInfo("pax.txt");ti.size=len(data);ti.pax_headers={"comment":"ocean"};t.addfile(ti,io.BytesIO(data))
    cpio=d/"newc.cpio";cpio.write_bytes(newc_entry("a.txt",b"abc")+newc_entry("TRAILER!!!"))
    crc=d/"crc.cpio";crc.write_bytes(newc_entry("a.txt",b"abc",b"070702")+newc_entry("TRAILER!!!",b"",b"070702"))
    odc=d/"odc.cpio";odc.write_bytes(odc_entry("a.txt",b"abc")+odc_entry("TRAILER!!!"))
    deb=d/"x.deb";deb.write_bytes(b"!<arch>\n"+ar_header("debian-binary",b"2.0\n")+ar_header("control.tar",b"ctl")+ar_header("data.tar",b"dat"))
    zf=d/"x.apk"
    with zipfile.ZipFile(zf,"w",allowZip64=True) as z:
        info=zipfile.ZipInfo("a.txt");info.extra=struct.pack("<HHQ",0x0001,8,123);z.writestr(info,"hello");z.comment=b"Ocean"
    seven=d/"x.7z";b=bytearray(32);b[:6]=b"7z\xbc\xaf'\x1c";b[6]=0;b[7]=4;struct.pack_into("<I",b,8,1);struct.pack_into("<Q",b,12,0);struct.pack_into("<Q",b,20,0);struct.pack_into("<I",b,28,0);seven.write_bytes(b)
    rar=d/"x.rar";rar.write_bytes(b"Rar!\x1a\x07\x01\x00"+b"\0"*32)
    cab=d/"x.cab";b=bytearray(64);b[:4]=b"MSCF";struct.pack_into("<I",b,8,64);struct.pack_into("<I",b,16,36);b[24]=3;b[25]=1;struct.pack_into("<H",b,26,1);struct.pack_into("<H",b,28,1);cab.write_bytes(b)
    iso=d/"x.iso";iso.write_bytes(b"\0"*(20*2048))
    with iso.open("r+b") as f:
        f.seek(16*2048);p=bytearray(2048);p[0]=1;p[1:6]=b"CD001";p[6]=1;p[200:207]=b"SP\x07\x01ABC";f.write(p)
        q=bytearray(2048);q[0]=2;q[1:6]=b"CD001";q[6]=1;q[40:72]="OCEAN".encode("utf-16-be").ljust(32,b"\0");q[88:91]=b"%/E";f.write(q)
        e=bytearray(2048);e[0]=255;e[1:6]=b"CD001";e[6]=1;f.write(e)
    wim=d/"x.wim";b=bytearray(208);b[:8]=b"MSWIM\0\0\0";struct.pack_into("<I",b,8,208);struct.pack_into("<I",b,12,0x10);struct.pack_into("<I",b,20,32768);struct.pack_into("<H",b,40,1);struct.pack_into("<H",b,42,1);struct.pack_into("<I",b,44,1);wim.write_bytes(b)
    sq=d/"x.sqfs";b=bytearray(96);struct.pack_into("<I",b,0,0x73717368);struct.pack_into("<I",b,4,2);struct.pack_into("<I",b,12,131072);struct.pack_into("<Q",b,64,4096);struct.pack_into("<Q",b,72,8192);sq.write_bytes(b)
    dump=d/"dump.bin";b=bytearray(1024);struct.pack_into("<I",b,24,60012);dump.write_bytes(b)
    dar=d/"x.dar";dar.write_bytes(b"DAR"+b"\0"*64)
    xml=b"<?xml version='1.0'?><xar><toc/></xar>";comp=zlib.compress(xml);xar=d/"x.xar";xar.write_bytes(b"xar!"+struct.pack(">HHQQI",28,1,len(comp),len(xml),0)+comp)
    chm=d/"x.chm";b=bytearray(96);b[:4]=b"ITSF";struct.pack_into("<I",b,4,3);struct.pack_into("<I",b,8,96);struct.pack_into("<I",b,20,0x409);chm.write_bytes(b)
    rpm=d/"x.rpm";b=bytearray(96);b[:4]=b"\xed\xab\xee\xdb";b[4]=3;b[5]=0;struct.pack_into(">H",b,6,0);struct.pack_into(">H",b,8,1);b[10:15]=b"ocean";rpm.write_bytes(b)
    vhd=d/"x.vhd";b=bytearray(512);b[:8]=b"conectix";struct.pack_into(">I",b,8,2);struct.pack_into(">I",b,12,0x10000);struct.pack_into(">Q",b,16,0xffffffffffffffff);struct.pack_into(">Q",b,40,1024);struct.pack_into(">Q",b,48,1024);struct.pack_into(">I",b,60,2);vhd.write_bytes(b)
    qc=d/"x.qcow2";b=bytearray(104);b[:4]=b"QFI\xfb";struct.pack_into(">I",b,4,3);struct.pack_into(">I",b,20,16);struct.pack_into(">Q",b,24,1048576);struct.pack_into(">I",b,36,1);struct.pack_into(">Q",b,40,65536);qc.write_bytes(b)
    vmdk=d/"x.vmdk";vmdk.write_text('# Disk DescriptorFile\nversion=1\nCID=abcdef01\ncreateType="monolithicSparse"\nRW 2048 SPARSE "disk-s001.vmdk"\n')
    sparse=d/"x.simg";raw=b"ABCD";hdr=struct.pack("<I4H4I",0xED26FF3A,1,0,28,12,4,1,1,0);chunk=struct.pack("<2H2I",0xCAC1,0,1,16)+raw;sparse.write_bytes(hdr+chunk)
    old=d/"old.bin";old.write_bytes(b"A"*8192);new=d/"new.bin";new.write_bytes(b"A"*4096+b"B"*4096);delta=d/"delta.json";patched=d/"patched.bin"
    catalog=d/"catalog.json";catalog.write_text(json.dumps({"entries":{"a.txt":{"sha256":hashlib.sha256((src/"a.txt").read_bytes()).hexdigest()}}}))
    mt=d/"mtree.txt";run("rdiff-delta-generator",old,new,delta,"4096");run("mtree-specification-gen",src,mt)
    cases={
      "tar-header-validator":(gnu,),"tar-gnu-longlink-chk":(gnu,),"tar-pax-extended-chk":(pax,),"tar-sparse-header-chk":(pax,),"cpio-crc-format-dump":(crc,),"cpio-odc-format-dump":(odc,),"cpio-newc-header-chk":(cpio,),"ar-bsd-variant-parser":(deb,),"ar-gnu-variant-parser":(deb,),"zip-eocd-locator-cli":(zf,),"zip-cd-record-viewer":(zf,),"zip-extra-field-parse":(zf,),"zip64-locator-parser":(zf,),"sevenzip-signature-chk":(seven,),"sevenzip-header-view":(seven,),"rar5-header-validator":(rar,),"cab-folder-extractor":(cab,),"iso-rockridge-parser":(iso,),"iso-joliet-ext-parser":(iso,),"wim-header-inspector":(wim,),"squashfs-inode-table":(sq,),"ext4-dump-restore-chk":(dump,),"rdiff-patch-applier":(old,delta,patched),"rsync-checksum-block":(new,"1024"),"rsync-rolling-hash":(new,"32"),"adler32-rolling-calc":(new,),"rabin-karp-chunker":(new,"128","512","2048"),"content-defined-chunk":(new,),"fastcdc-chunker-cli":(new,),"backup-catalog-verify":(src,catalog),"backup-retention-calc":("40","2026-09-20T00:00:00+00:00"),"snapshot-differential":(src,src2),"dir-tree-hasher-fast":(src,),"mtree-validator-tool":(src,mt),"dar-disk-archiver-chk":(dar,),"afio-archive-linter":(cpio,),"pax-archive-validator":(pax,),"xar-xml-toc-extractor":(xar,),"chm-archive-header-chk":(chm,),"deb-ar-data-splitter":(deb,d/"debout"),"rpm-lead-header-parser":(rpm,),"apk-zip-comment-tool":(zf,),"vhd-footer-inspector":(vhd,),"qcow2-header-parser":(qc,),"vmdk-descriptor-view":(vmdk,),"raw-disk-image-resizer":(d/"raw.img","8","512"),"sparse-image-converter":(sparse,d/"raw1.img"),"simg2img-ocean-cli":(sparse,d/"raw2.img"),"rdiff-delta-generator":(old,new,d/"delta2.json","4096"),"mtree-specification-gen":(src,d/"mtree2.txt")}
    assert set(cases)==set(m.COMMANDS),(set(m.COMMANDS)-set(cases),set(cases)-set(m.COMMANDS))
    for cmd,args in cases.items():run(cmd,*args)
    assert patched.read_bytes()==new.read_bytes();assert (d/"raw1.img").read_bytes()==raw and (d/"raw2.img").read_bytes()==raw
print("SUCCESS: exercised 50/50 shard-19 archive/backup commands")
