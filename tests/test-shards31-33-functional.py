#!/usr/bin/env python3
import hashlib,importlib.util,json,struct,subprocess,sys,tempfile
from pathlib import Path

R31=Path(sys.argv[1]).resolve();R32=Path(sys.argv[2]).resolve();R33=Path(sys.argv[3]).resolve()
def load(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m31=load(R31,"s31");m32=load(R32,"s32");m33=load(R33,"s33")
assert len(m31.COMMANDS)==67 and len(set(m31.COMMANDS))==67
assert len(m32.COMMANDS)==67 and len(set(m32.COMMANDS))==67
assert len(m33.COMMANDS)==66 and len(set(m33.COMMANDS))==66
all_names=m31.COMMANDS+m32.COMMANDS+m33.COMMANDS
assert len(all_names)==200 and len(set(all_names))==200

RT={**{x:R31 for x in m31.COMMANDS},**{x:R32 for x in m32.COMMANDS},**{x:R33 for x in m33.COMMANDS}}
def run(cmd,*args,binary=False):
    p=subprocess.run([sys.executable,str(RT[cmd]),cmd,*map(str,args)],capture_output=True,text=not binary)
    if p.returncode:
        raise AssertionError(f"{cmd} rc={p.returncode}\nstdout={p.stdout}\nstderr={p.stderr}")
    return p.stdout

for cmd in all_names:
    assert cmd in run(cmd,"--help")

def pv(n):
    out=bytearray()
    while True:
        x=n&0x7f;n>>=7;out.append(x|(0x80 if n else 0))
        if not n:return bytes(out)
def avlong(n):
    z=(n<<1)^(n>>63)
    return pv(z)
def avbytes(b):return avlong(len(b))+b
def avstr(s):return avbytes(s.encode())

with tempfile.TemporaryDirectory() as td:
    d=Path(td)

    # Shard 31 — Protobuf
    pb=d/"m.pb"
    pb.write_bytes(bytes([0x08,0x96,0x01,0x12,0x05])+b"Ocean"+bytes([0x1d])+struct.pack("<I",0x12345678))
    assert run("protobuf-field-count",pb).strip()=="3"
    assert json.loads(run("protobuf-field-numbers",pb))==[1,2,3]
    assert "Ocean" in json.loads(run("protobuf-length-strings",pb))
    assert json.loads(run("protobuf-fixed32-values",pb))==[0x12345678]
    assert json.loads(run("protobuf-validate",pb))["valid"] is True
    assert run("protobuf-varint-decode","ac02").strip()=="300"
    assert run("protobuf-varint-encode","300").strip()=="ac02"
    assert json.loads(run("protobuf-tag-decode","18"))=={"field":2,"wire":2}

    # CBOR map {"a":1,"b":[2,3]}
    cb=d/"m.cbor";cb.write_bytes(bytes.fromhex("a26161016162820203"))
    decoded=json.loads(run("cbor-decode",cb))
    assert decoded["a"]==1 and decoded["b"]==[2,3]
    assert json.loads(run("cbor-map-keys",cb))==["a","b"]
    assert run("cbor-array-length",cb).strip()=="0"
    assert json.loads(run("cbor-validate",cb))["valid"] is True

    # MessagePack same object.
    mp=d/"m.msgpack";mp.write_bytes(bytes.fromhex("82a16101a162920203"))
    decoded=json.loads(run("msgpack-decode",mp))
    assert decoded["a"]==1 and decoded["b"]==[2,3]
    assert json.loads(run("msgpack-map-keys",mp))==["a","b"]
    assert json.loads(run("msgpack-type-frequency",mp))["map"]==1

    # Minimal Avro OCF.
    sync=b"0123456789abcdef"
    schema=b'{"type":"record","name":"X","fields":[]}'
    meta=avlong(2)+avstr("avro.schema")+avbytes(schema)+avstr("avro.codec")+avbytes(b"null")+avlong(0)
    block=avlong(1)+avlong(1)+b"\x00"+sync
    av=d/"m.avro";av.write_bytes(b"Obj\x01"+meta+sync+block)
    assert json.loads(run("avro-magic-check",av))["valid"] is True
    assert run("avro-codec",av).strip()=="null"
    assert json.loads(run("avro-block-counts",av))==[1]
    assert json.loads(run("avro-validate-basic",av))["valid"] is True
    assert json.loads(run("avro-schema",av))["name"]=="X"

    # Shard 32 — DNS response with one compressed A answer.
    qname=b"\x07example\x03com\x00"
    dns=d/"dns.bin"
    dns.write_bytes(struct.pack(">HHHHHH",0x1234,0x8180,1,1,0,0)+qname+struct.pack(">HH",1,1)+b"\xc0\x0c"+struct.pack(">HHIH",1,1,60,4)+bytes([1,2,3,4]))
    assert run("dnswire-id",dns).strip()==str(0x1234)
    assert json.loads(run("dnswire-qnames",dns))==["example.com"]
    assert json.loads(run("dnswire-a-records",dns))==["1.2.3.4"]
    assert json.loads(run("dnswire-answer-ttls",dns))==[60]
    assert json.loads(run("dnswire-validate",dns))["valid"] is True

    # HTTP/1 request.
    http=d/"http.bin"
    http.write_bytes(b"GET /api?q=one&q=two HTTP/1.1\r\nHost: example.com\r\nUser-Agent: OceanTest\r\nCookie: a=1; b=2\r\nContent-Length: 3\r\n\r\nxyz")
    assert run("http1-method",http).strip()=="GET"
    assert run("http1-host",http).strip()=="example.com"
    assert json.loads(run("http1-cookie-names",http))==["a","b"]
    assert json.loads(run("http1-query-params",http))["q"]==["one","two"]
    assert run("http1-body-size",http).strip()=="3"

    # HTTP/2 preface + SETTINGS + DATA.
    pre=b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
    settings=bytes([0,0,6,4,0])+struct.pack(">I",0)+struct.pack(">HI",4,65535)
    data=bytes([0,0,3,0,1])+struct.pack(">I",1)+b"abc"
    h2=d/"h2.bin";h2.write_bytes(pre+settings+data)
    assert run("h2-frame-count",h2).strip()=="2"
    assert json.loads(run("h2-frame-types",h2))==["SETTINGS","DATA"]
    assert json.loads(run("h2-settings",h2))[0]["value"]==65535
    assert run("h2-data-bytes",h2).strip()=="3"
    assert json.loads(run("h2-validate",h2))["valid"] is True

    # WebSocket text + ping + normal close.
    ws=d/"ws.bin";ws.write_bytes(b"\x81\x02hi\x89\x00\x88\x02\x03\xe8")
    assert run("wsframe-count",ws).strip()=="3"
    assert json.loads(run("wsframe-opcodes",ws))==["text","ping","close"]
    assert json.loads(run("wsframe-text",ws))==["hi"]
    assert json.loads(run("wsframe-close-codes",ws))==[1000]
    assert json.loads(run("wsframe-validate",ws))["valid"] is True

    # Shard 33 — build a tiny but structurally valid SFNT with key tables.
    head=bytearray(54);head[18:20]=struct.pack(">H",1000);head[20:28]=struct.pack(">Q",3600);head[28:36]=struct.pack(">Q",7200);head[36:44]=struct.pack(">hhhh",-10,-20,1000,900)
    maxp=struct.pack(">IH",0x00010000,42)
    strs=["Ocean Sans","Regular","Ocean Sans Regular"];raws=[x.encode("utf-16-be") for x in strs]
    stringdata=b"".join(raws);offs=[];cur=0
    for x in raws:offs.append(cur);cur+=len(x)
    records=b"".join(struct.pack(">HHHHHH",3,1,0x409,nid,len(raw),off) for nid,raw,off in zip((1,2,4),raws,offs))
    name=struct.pack(">HHH",0,3,6+len(records))+records+stringdata
    os2=bytearray(8);os2[4:6]=struct.pack(">H",400);os2[6:8]=struct.pack(">H",5)
    post=struct.pack(">I",0x00030000)
    cmap=struct.pack(">HHHHI",0,1,3,1,12)
    tables=[("head",bytes(head)),("maxp",maxp),("name",name),("OS/2",bytes(os2)),("post",post),("cmap",cmap)]
    num=len(tables);header=struct.pack(">IHHHH",0x00010000,num,0,0,0);directory=bytearray();payload=bytearray();offset=12+16*num
    for tag,raw in tables:
        directory+=tag.encode("latin1")+struct.pack(">III",0,offset,len(raw));payload+=raw;offset+=len(raw)
    font=d/"font.ttf";font.write_bytes(header+directory+payload)
    assert run("fontsfnt-table-count",font).strip()==str(num)
    assert run("fontsfnt-head-units-per-em",font).strip()=="1000"
    assert run("fontsfnt-maxp-glyphs",font).strip()=="42"
    assert "Ocean Sans" in json.loads(run("fontsfnt-name-family",font))
    assert run("fontsfnt-os2-weight",font).strip()=="400"
    assert json.loads(run("fontsfnt-head-bbox",font))["xMax"]==1000

    # WOFF1 minimal header and directory.
    woff=d/"font.woff";wofflen=44+20+4
    wh=b"wOFF"+struct.pack(">I",0x00010000)+struct.pack(">IHHIHHIIIII",wofflen,1,0,16,1,0,0,0,0,0,0)
    wd=b"test"+struct.pack(">IIII",64,4,4,0)
    woff.write_bytes(wh+wd+b"DATA")
    assert json.loads(run("woff-magic-check",woff))["valid"] is True
    assert run("woff-table-count",woff).strip()=="1"
    assert json.loads(run("woff-table-directory",woff))[0]["tag"]=="test"

    # ICC profile with one tag.
    iccb=bytearray(144);iccb[0:4]=struct.pack(">I",144);iccb[4:8]=b"OCEA";iccb[8:12]=bytes([4,0x40,0,0]);iccb[12:16]=b"mntr";iccb[16:20]=b"RGB ";iccb[20:24]=b"XYZ ";iccb[24:36]=struct.pack(">HHHHHH",2026,9,21,12,0,0);iccb[36:40]=b"acsp";iccb[40:44]=b"APPL";iccb[64:68]=struct.pack(">I",1);iccb[80:84]=b"OCEN";iccb[128:132]=struct.pack(">I",1);iccb[132:144]=b"desc"+struct.pack(">II",144,0)
    iccf=d/"profile.icc";iccf.write_bytes(iccb)
    assert run("icc-profile-size",iccf).strip()=="144"
    assert run("icc-device-class",iccf).strip()=="mntr"
    assert run("icc-rendering-intent",iccf).strip()=="1"
    assert json.loads(run("icc-tag-signatures",iccf))==["desc"]

    # XMP/RDF XML.
    xmp=d/"meta.xmp";xmp.write_text("""<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:xmp="http://ns.adobe.com/xap/1.0/"><rdf:Description><dc:title>Ocean Image</dc:title><dc:creator>Leon</dc:creator><xmp:CreateDate>2026-09-21T12:00:00Z</xmp:CreateDate></rdf:Description></rdf:RDF>""")
    assert run("xmp-root",xmp).strip()=="RDF"
    assert "Ocean Image" in json.loads(run("xmp-dc-title",xmp))
    assert "Leon" in json.loads(run("xmp-dc-creator",xmp))
    assert json.loads(run("xmp-summary",xmp))["descriptions"]==1

    # Subtitle track.
    srt=d/"a.srt";srt.write_text("""1
00:00:01,000 --> 00:00:03,000
ALICE: Hello Ocean

2
00:00:04,500 --> 00:00:06,000
Second line
""")
    assert run("subtrack-format-detect",srt).strip()=="srt"
    assert run("subtrack-cue-count",srt).strip()=="2"
    assert json.loads(run("subtrack-speakers",srt))==["ALICE"]
    assert len(json.loads(run("subtrack-gaps",srt)))==1
    assert json.loads(run("subtrack-summary",srt))["cues"]==2

print("PASS: shards 31/32/33 expose 200 unique commands and representative serialization, wire-format, font/profile/subtitle behavior works")
