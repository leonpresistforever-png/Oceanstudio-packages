#!/usr/bin/env python3
import hashlib,importlib.util,json,math,os,struct,subprocess,sys,tempfile,zipfile,zlib
from pathlib import Path

R37=Path(sys.argv[1]).resolve();R38=Path(sys.argv[2]).resolve();R39=Path(sys.argv[3]).resolve()
def load(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m37=load(R37,"s37");m38=load(R38,"s38");m39=load(R39,"s39")
assert len(m37.COMMANDS)==100 and len(set(m37.COMMANDS))==100
assert len(m38.COMMANDS)==100 and len(set(m38.COMMANDS))==100
assert len(m39.COMMANDS)==100 and len(set(m39.COMMANDS))==100
ALL=m37.COMMANDS+m38.COMMANDS+m39.COMMANDS
assert len(ALL)==300 and len(set(ALL))==300
RUNTIME={**{x:R37 for x in m37.COMMANDS},**{x:R38 for x in m38.COMMANDS},**{x:R39 for x in m39.COMMANDS}}

def run(cmd,*args,binary=False):
    p=subprocess.run([sys.executable,str(RUNTIME[cmd]),cmd,*map(str,args)],capture_output=True,text=not binary)
    if p.returncode:
        raise AssertionError(f"{cmd} rc={p.returncode}\nstdout={p.stdout}\nstderr={p.stderr}")
    return p.stdout

for cmd in ALL:
    assert cmd in run(cmd,"--help")

def vint(n):
    out=bytearray()
    while True:
        x=n&0x7f;n>>=7;out.append(x|(0x80 if n else 0))
        if not n:return bytes(out)
def pb_field(num,wire,val):
    key=vint((num<<3)|wire)
    if wire==0:return key+vint(val)
    if wire==2:return key+vint(len(val))+val
    raise ValueError
def mk_chunk(typ,payload,header_size=8):
    return struct.pack("<HHI",typ,header_size,header_size+len(payload))+payload

with tempfile.TemporaryDirectory() as td:
    d=Path(td)

    # Shard 37: GeoJSON/WKT/GPX/KML and modern tile formats.
    gj=d/"map.geojson"
    gj.write_text(json.dumps({"type":"FeatureCollection","features":[
      {"type":"Feature","id":"road1","properties":{"name":"Road"},"geometry":{"type":"LineString","coordinates":[[0,0],[3,4]]}},
      {"type":"Feature","properties":{"zone":1},"geometry":{"type":"Polygon","coordinates":[[[0,0],[2,0],[2,2],[0,0]]]}}
    ]}))
    assert run("geojson-feature-count",gj).strip()=="2"
    assert json.loads(run("geojson-bbox",gj))==[0.0,0.0,3.0,4.0]
    assert json.loads(run("geojson-geometry-types",gj))["LineString"]==1
    assert "name" in json.loads(run("geojson-property-keys",gj))
    assert float(run("geojson-line-length-deg",gj).strip())==5.0

    w=d/"shape.wkt";w.write_text("SRID=4326;POLYGON ((0 0, 2 0, 2 2, 0 0))")
    assert run("wkt-type",w).strip()=="POLYGON"
    assert json.loads(run("wkt-bbox",w))==[0.0,0.0,2.0,2.0]
    assert json.loads(run("wkt-srid",w))==4326
    assert json.loads(run("wkt-to-geojson-lite",w))["type"]=="Polygon"

    gpx=d/"track.gpx";gpx.write_text("<gpx><trk><name>T</name><trkseg><trkpt lat='1' lon='2'><ele>10</ele><time>2026-01-01T00:00:00Z</time></trkpt><trkpt lat='2' lon='3'><ele>20</ele><time>2026-01-01T00:01:00Z</time></trkpt></trkseg></trk><wpt lat='0' lon='1'/></gpx>")
    assert run("gpx-tracks",gpx).strip()=="1"
    assert run("gpx-trackpoints",gpx).strip()=="2"
    assert json.loads(run("gpx-elevation-range",gpx))==[10.0,20.0]

    kml=d/"map.kml";kml.write_text("<kml><Document><Folder><Placemark><name>P</name><Point><coordinates>10,20,0</coordinates></Point></Placemark></Folder></Document></kml>")
    assert run("kml-placemarks",kml).strip()=="1"
    assert json.loads(run("kml-bbox",kml))==[10.0,20.0,10.0,20.0]

    tile=json.loads(run("slippy-lonlat-to-tile","0","0","1"))
    assert tile=={"z":1,"x":1,"y":1}
    assert run("slippy-tile-count","3","0","0").strip()=="64"

    layer=(pb_field(1,2,b"roads")+pb_field(2,2,b"")+pb_field(3,2,b"name")+pb_field(4,2,b"")+pb_field(5,0,4096)+pb_field(15,0,2))
    mvt=d/"x.mvt";mvt.write_bytes(pb_field(3,2,layer))
    assert run("mvt-layer-count",mvt).strip()=="1"
    assert json.loads(run("mvt-layer-names",mvt))==["roads"]
    assert run("mvt-feature-count",mvt).strip()=="1"
    assert json.loads(run("mvt-extent",mvt))["roads"]==4096

    mlt=d/"x.mlt";mlt.write_bytes(vint(3)+b"\x01AB"+vint(2)+b"\x01Z")
    assert run("mlt-layer-count",mlt).strip()=="2"
    assert json.loads(run("mlt-layer-sizes",mlt))==[3,2]
    assert run("mlt-v1-detect",mlt).strip()=="true"

    pm=d/"x.pmtiles";buf=bytearray(127);buf[:7]=b"PMTiles";buf[7]=3
    for off,val in [(8,127),(16,10),(24,137),(32,20),(40,157),(48,0),(56,157),(64,100),(72,5),(80,5),(88,5)]:
        struct.pack_into("<Q",buf,off,val)
    buf[96]=1;buf[97]=1;buf[98]=1;buf[99]=1;buf[100]=0;buf[101]=14
    pm.write_bytes(buf)
    assert run("pmtiles-version",pm).strip()=="3"
    assert run("pmtiles-root-offset",pm).strip()=="127"
    assert json.loads(run("pmtiles-header-v3",pm))["tile_type"]==1

    # Shard 38: glTF, GLB, KTX2, STL, PLY, OBJ/MTL.
    gltf=d/"scene.gltf"
    gd={"asset":{"version":"2.0","generator":"Ocean"},"extensionsUsed":["KHR_texture_basisu"],"scene":0,"scenes":[{"nodes":[0]}],"nodes":[{"name":"Root","mesh":0}],"meshes":[{"name":"Cube","primitives":[{"attributes":{"POSITION":0}}]}],"accessors":[{"count":3,"type":"VEC3","min":[0,0,0],"max":[1,1,1]}],"materials":[{"name":"Mat","alphaMode":"BLEND","doubleSided":True,"pbrMetallicRoughness":{}}],"images":[{"uri":"tex.ktx2"}],"textures":[{"extensions":{"KHR_texture_basisu":{"source":0}}}],"buffers":[{"uri":"buf.bin","byteLength":12}]}
    gltf.write_text(json.dumps(gd))
    assert run("gltf-asset-version",gltf).strip().strip('"')=="2.0"
    assert run("gltf-mesh-count",gltf).strip()=="1"
    assert run("gltf-primitive-count",gltf).strip()=="1"
    assert json.loads(run("gltf-basisu-hints",gltf))
    assert json.loads(run("gltf-alpha-modes",gltf))["BLEND"]==1

    js=json.dumps(gd,separators=(",",":")).encode();js+=b" " *((4-len(js)%4)%4)
    binp=b"\x00\x01\x02\x03"
    total=12+8+len(js)+8+len(binp)
    glb=d/"scene.glb";glb.write_bytes(struct.pack("<4sII",b"glTF",2,total)+struct.pack("<I4s",len(js),b"JSON")+js+struct.pack("<I4s",len(binp),b"BIN\x00")+binp)
    assert json.loads(run("glb-magic",glb))["valid"] is True
    assert run("glb-chunk-count",glb).strip()=="2"
    assert run("glb-bin-chunk-size",glb).strip()=="4"
    assert json.loads(run("glb-validate-length",glb))["valid"] is True

    ktx=d/"tex.ktx2";kb=bytearray(108);kb[:12]=m38.KTX_MAGIC
    vals=[37,1,64,32,0,0,1,1,1,80,0,80,0,0,0]
    struct.pack_into("<13I2Q",kb,12,*vals)
    struct.pack_into("<QQQ",kb,80,104,4,4);kb[104:108]=b"DATA";ktx.write_bytes(kb)
    assert json.loads(run("ktx2-magic",ktx))["valid"] is True
    assert run("ktx2-pixel-width",ktx).strip()=="64"
    assert run("ktx2-level-count",ktx).strip()=="1"
    assert json.loads(run("ktx2-levels",ktx))[0]["length"]==4

    stl=d/"m.stl";sb=bytearray(84+50);struct.pack_into("<I",sb,80,1)
    struct.pack_into("<12fH",sb,84,0,0,1,0,0,0,1,0,0,0,1,0,0);stl.write_bytes(sb)
    assert run("stl-format",stl).strip()=="binary"
    assert run("stl-triangle-count",stl).strip()=="1"
    assert json.loads(run("stl-size-check",stl))["valid"] is True

    ply=d/"m.ply";ply.write_text("ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\nproperty float y\nproperty float z\nelement face 1\nproperty list uchar int vertex_indices\nend_header\n0 0 0\n1 0 0\n0 1 0\n3 0 1 2\n")
    assert run("ply-format",ply).strip()=="ascii"
    assert run("ply-vertex-count",ply).strip()=="3"
    assert run("ply-face-count",ply).strip()=="1"

    obj=d/"m.obj";obj.write_text("o Cube\ng G\nv 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0 0\nvn 0 0 1\nf 1/1/1 2/1/1 3/1/1\n")
    assert run("objmesh-vertex-count",obj).strip()=="3"
    assert run("objmesh-face-count",obj).strip()=="1"
    assert "Cube" in json.loads(run("objmesh-object-names",obj))
    mtl=d/"m.mtl";mtl.write_text("newmtl Mat\nmap_Kd tex.png\n")
    assert json.loads(run("mtl-material-names",mtl))==["Mat"]
    assert json.loads(run("mtl-texture-files",mtl))==["tex.png"]

    # Shard 39: real structural fixtures for DEX, binary XML, resources.arsc and APK ZIP.
    dex=d/"classes.dex"
    db=bytearray(121);db[:8]=b"dex\n035\0"
    struct.pack_into("<I",db,32,len(db));struct.pack_into("<I",db,36,112);struct.pack_into("<I",db,40,0x12345678)
    struct.pack_into("<I",db,56,1);struct.pack_into("<I",db,60,112);struct.pack_into("<I",db,104,5);struct.pack_into("<I",db,108,116)
    struct.pack_into("<I",db,112,116);db[116:121]=b"\x03abc\0"
    sig=hashlib.sha1(db[32:]).digest();db[12:32]=sig;struct.pack_into("<I",db,8,zlib.adler32(db[12:])&0xffffffff);dex.write_bytes(db)
    assert run("dex-version",dex).strip()=="035"
    assert run("dex-string-count",dex).strip()=="1"
    assert json.loads(run("dex-strings",dex))==["abc"]
    assert json.loads(run("dex-sha1-check",dex))["valid"] is True
    assert json.loads(run("dex-adler32-check",dex))["valid"] is True

    text=b"com.example.app";sp=bytearray(52);struct.pack_into("<HHI",sp,0,0x0001,28,52)
    struct.pack_into("<IIIII",sp,8,1,0,0x100,32,0);struct.pack_into("<I",sp,28,0);sp[32]=len(text);sp[33]=len(text);sp[34:34+len(text)]=text;sp[34+len(text)]=0
    ax=bytearray(8+len(sp));struct.pack_into("<HHI",ax,0,0x0003,8,len(ax));ax[8:]=sp
    axml=d/"AndroidManifest.xml";axml.write_bytes(ax)
    assert run("axml-string-count",axml).strip()=="1"
    assert run("axml-utf8-flag",axml).strip()=="true"
    assert "com.example.app" in json.loads(run("axml-package-hints",axml))

    pkg=bytearray(288);struct.pack_into("<HHI",pkg,0,0x0200,288,288);struct.pack_into("<I",pkg,8,0x7f)
    name="com.example.app".encode("utf-16le");pkg[12:12+len(name)]=name
    ar=bytearray(12+len(pkg));struct.pack_into("<HHI",ar,0,0x0002,12,len(ar));struct.pack_into("<I",ar,8,1);ar[12:]=pkg
    arsc=d/"resources.arsc";arsc.write_bytes(ar)
    assert run("arsc-package-count",arsc).strip()=="1"
    assert json.loads(run("arsc-package-ids",arsc))==[127]
    assert "com.example.app" in json.loads(run("arsc-package-name-hints",arsc))

    apk=d/"app.apk"
    with zipfile.ZipFile(apk,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("AndroidManifest.xml",ax)
        z.writestr("classes.dex",db)
        z.writestr("lib/arm64-v8a/libx.so",b"\x7fELF")
        z.writestr("assets/a.txt","a")
        z.writestr("res/layout/x.xml","x")
        z.writestr("META-INF/CERT.SF","sig")
    assert run("apk-entry-count",apk).strip()=="6"
    assert json.loads(run("apk-dex-files",apk))==["classes.dex"]
    assert json.loads(run("apk-native-abis",apk))==["arm64-v8a"]
    assert json.loads(run("apk-summary",apk))["dexFiles"]==1

print("PASS: shards 37/38/39 register 300 unique commands; geospatial, 3D/GPU and Android binary fixtures passed")
