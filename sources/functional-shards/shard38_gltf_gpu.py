#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,math,re,struct,sys
from collections import Counter
from pathlib import Path
P=Path

GLTF=[
"gltf-asset-version","gltf-generator","gltf-extensions-used","gltf-extensions-required","gltf-scene-count","gltf-default-scene","gltf-node-count","gltf-mesh-count","gltf-primitive-count","gltf-material-count","gltf-texture-count","gltf-image-count","gltf-sampler-count","gltf-accessor-count","gltf-buffer-count","gltf-bufferview-count","gltf-animation-count","gltf-skin-count","gltf-camera-count","gltf-light-count","gltf-node-names","gltf-mesh-names","gltf-material-names","gltf-image-uris","gltf-buffer-uris","gltf-external-uris","gltf-data-uris","gltf-draco-hints","gltf-meshopt-hints","gltf-basisu-hints","gltf-pbr-materials","gltf-alpha-modes","gltf-double-sided","gltf-texture-transforms","gltf-scene-roots","gltf-node-children","gltf-accessor-bounds","gltf-minify","gltf-pretty","gltf-summary"]
GLB=[
"glb-magic","glb-version","glb-length","glb-chunk-count","glb-chunk-types","glb-json-chunk","glb-bin-chunk-size","glb-chunk-offsets","glb-validate-length","glb-json-summary","glb-embedded-buffer","glb-sha256","glb-entropy","glb-hexdump","glb-summary"]
KTX=[
"ktx2-magic","ktx2-vk-format","ktx2-type-size","ktx2-pixel-width","ktx2-pixel-height","ktx2-pixel-depth","ktx2-layer-count","ktx2-face-count","ktx2-level-count","ktx2-supercompression","ktx2-dfd-offset","ktx2-dfd-length","ktx2-kvd-offset","ktx2-kvd-length","ktx2-sgd-offset","ktx2-sgd-length","ktx2-levels","ktx2-level-sizes","ktx2-basis-detect","ktx2-cubemap-detect","ktx2-array-detect","ktx2-mipmap-detect","ktx2-sha256","ktx2-header-json","ktx2-summary"]
MESH=[
"stl-format","stl-triangle-count","stl-bbox","stl-size-check","stl-sha256",
"ply-format","ply-elements","ply-vertex-count","ply-face-count","ply-properties","ply-header","ply-sha256",
"objmesh-vertex-count","objmesh-normal-count","objmesh-texcoord-count","objmesh-face-count","objmesh-object-names","objmesh-group-names","mtl-material-names","mtl-texture-files"]
COMMANDS=GLTF+GLB+KTX+MESH
assert len(COMMANDS)==100 and len(set(COMMANDS))==100

def emit(x):
    if isinstance(x,(dict,list,tuple,Counter)):print(json.dumps(x,indent=2,ensure_ascii=False,default=str))
    else:print(x)
def die(s,c=2):print(s,file=sys.stderr);raise SystemExit(c)
def entropy(b):
    if not b:return 0.0
    c=Counter(b);return -sum((n/len(b))*math.log2(n/len(b)) for n in c.values())
def loadj(path):
    return json.loads(P(path).read_text(errors="replace"))

def ext_hints(d,name):
    hits=[]
    def rec(x,path=""):
        if isinstance(x,dict):
            if name in x:hits.append(path or "/")
            for k,v in x.items():rec(v,path+"/"+str(k))
        elif isinstance(x,list):
            for i,v in enumerate(x):rec(v,path+"/"+str(i))
    rec(d);return hits

def gltf(cmd,a):
    if not a:die("glTF JSON path required")
    op=cmd.removeprefix("gltf-");d=loadj(a[0])
    arr=lambda k:d.get(k,[]) if isinstance(d.get(k,[]),list) else []
    asset=d.get("asset",{}) if isinstance(d.get("asset"),dict) else {}
    if op=="asset-version":emit(asset.get("version"));return
    if op=="generator":emit(asset.get("generator"));return
    if op=="extensions-used":emit(d.get("extensionsUsed",[]));return
    if op=="extensions-required":emit(d.get("extensionsRequired",[]));return
    if op=="scene-count":print(len(arr("scenes")));return
    if op=="default-scene":emit(d.get("scene"));return
    counts={"node-count":"nodes","mesh-count":"meshes","material-count":"materials","texture-count":"textures","image-count":"images","sampler-count":"samplers","accessor-count":"accessors","buffer-count":"buffers","bufferview-count":"bufferViews","animation-count":"animations","skin-count":"skins","camera-count":"cameras"}
    if op in counts:print(len(arr(counts[op])));return
    if op=="primitive-count":print(sum(len(x.get("primitives",[])) for x in arr("meshes") if isinstance(x,dict)));return
    if op=="light-count":
        ext=d.get("extensions",{});q=ext.get("KHR_lights_punctual",{}) if isinstance(ext,dict) else {};print(len(q.get("lights",[])) if isinstance(q,dict) else 0);return
    if op=="node-names":emit([x.get("name") for x in arr("nodes") if isinstance(x,dict) and x.get("name")]);return
    if op=="mesh-names":emit([x.get("name") for x in arr("meshes") if isinstance(x,dict) and x.get("name")]);return
    if op=="material-names":emit([x.get("name") for x in arr("materials") if isinstance(x,dict) and x.get("name")]);return
    if op=="image-uris":emit([x.get("uri") for x in arr("images") if isinstance(x,dict) and x.get("uri")]);return
    if op=="buffer-uris":emit([x.get("uri") for x in arr("buffers") if isinstance(x,dict) and x.get("uri")]);return
    if op=="external-uris":
        uris=[]
        for k in ("images","buffers"):
            uris += [x.get("uri") for x in arr(k) if isinstance(x,dict) and isinstance(x.get("uri"),str) and not x["uri"].startswith("data:")]
        emit(uris);return
    if op=="data-uris":
        uris=[]
        for k in ("images","buffers"):
            uris += [x.get("uri") for x in arr(k) if isinstance(x,dict) and isinstance(x.get("uri"),str) and x["uri"].startswith("data:")]
        emit(uris);return
    if op=="draco-hints":emit(ext_hints(d,"KHR_draco_mesh_compression"));return
    if op=="meshopt-hints":emit(ext_hints(d,"EXT_meshopt_compression"));return
    if op=="basisu-hints":emit(ext_hints(d,"KHR_texture_basisu"));return
    if op=="pbr-materials":
        emit([x.get("pbrMetallicRoughness",{}) for x in arr("materials") if isinstance(x,dict)]);return
    if op=="alpha-modes":emit(Counter(x.get("alphaMode","OPAQUE") for x in arr("materials") if isinstance(x,dict)));return
    if op=="double-sided":print(sum(bool(x.get("doubleSided")) for x in arr("materials") if isinstance(x,dict)));return
    if op=="texture-transforms":emit(ext_hints(d,"KHR_texture_transform"));return
    if op=="scene-roots":emit([x.get("nodes",[]) for x in arr("scenes") if isinstance(x,dict)]);return
    if op=="node-children":emit({str(i):x.get("children",[]) for i,x in enumerate(arr("nodes")) if isinstance(x,dict) and x.get("children")});return
    if op=="accessor-bounds":emit([{"index":i,"min":x.get("min"),"max":x.get("max"),"count":x.get("count"),"type":x.get("type")} for i,x in enumerate(arr("accessors")) if isinstance(x,dict)]);return
    if op=="minify":print(json.dumps(d,separators=(",",":"),ensure_ascii=False));return
    if op=="pretty":print(json.dumps(d,indent=2,ensure_ascii=False));return
    if op=="summary":
        emit({"asset":asset,"scenes":len(arr("scenes")),"nodes":len(arr("nodes")),"meshes":len(arr("meshes")),"primitives":sum(len(x.get("primitives",[])) for x in arr("meshes") if isinstance(x,dict)),"materials":len(arr("materials")),"textures":len(arr("textures")),"images":len(arr("images")),"extensionsUsed":d.get("extensionsUsed",[])});return

def glb_chunks(b):
    if len(b)<12:die("truncated GLB")
    magic,version,length=struct.unpack_from("<4sII",b,0)
    out=[];p=12
    while p+8<=min(len(b),length):
        n,t=struct.unpack_from("<I4s",b,p);p+=8
        if p+n>len(b):die("truncated GLB chunk")
        out.append({"type":t.decode("ascii",errors="replace"),"offset":p,"length":n,"data":b[p:p+n]});p+=n
    return magic,version,length,out

def glb(cmd,a):
    if not a:die("GLB path required")
    op=cmd.removeprefix("glb-");b=P(a[0]).read_bytes();magic,version,length,ch=glb_chunks(b)
    if op=="magic":emit({"valid":magic==b"glTF","magic":magic.decode(errors="replace")});return
    if op=="version":print(version);return
    if op=="length":print(length);return
    if op=="chunk-count":print(len(ch));return
    if op=="chunk-types":emit([x["type"] for x in ch]);return
    if op=="json-chunk":
        q=next((x for x in ch if x["type"]=="JSON"),None);print(q["data"].rstrip(b" \0").decode(errors="replace") if q else "");return
    if op=="bin-chunk-size":
        q=next((x for x in ch if x["type"].startswith("BIN")),None);print(q["length"] if q else 0);return
    if op=="chunk-offsets":emit([{"type":x["type"],"offset":x["offset"],"length":x["length"]} for x in ch]);return
    if op=="validate-length":emit({"declared":length,"actual":len(b),"valid":length==len(b)});return
    if op=="json-summary":
        q=next((x for x in ch if x["type"]=="JSON"),None);d=json.loads(q["data"].rstrip(b" \0")) if q else {};emit({"asset":d.get("asset"),"nodes":len(d.get("nodes",[])),"meshes":len(d.get("meshes",[]))});return
    if op=="embedded-buffer":emit({"present":any(x["type"].startswith("BIN") for x in ch),"bytes":sum(x["length"] for x in ch if x["type"].startswith("BIN"))});return
    if op=="sha256":print(hashlib.sha256(b).hexdigest());return
    if op=="entropy":print(f"{entropy(b):.6f}");return
    if op=="hexdump":
        for off in range(0,min(len(b),int(a[1]) if len(a)>1 else 256),16):
            q=b[off:off+16];print(f"{off:08x}  {' '.join(f'{x:02x}' for x in q)}")
        return
    if op=="summary":emit({"version":version,"declaredLength":length,"actualLength":len(b),"chunks":[{"type":x["type"],"length":x["length"]} for x in ch]});return

KTX_MAGIC=b"\xABKTX 20\xBB\r\n\x1A\n"
def ktxh(b):
    if len(b)<80:die("truncated KTX2")
    vals=struct.unpack_from("<13I2Q",b,12)
    # 9 core u32 fields + DFD/KVD offset-length pairs + two u64 SGD fields.
    return {"magic":b[:12],"vkFormat":vals[0],"typeSize":vals[1],"pixelWidth":vals[2],"pixelHeight":vals[3],"pixelDepth":vals[4],"layerCount":vals[5],"faceCount":vals[6],"levelCount":vals[7],"supercompression":vals[8],"dfdOffset":vals[9],"dfdLength":vals[10],"kvdOffset":vals[11],"kvdLength":vals[12],"sgdOffset":vals[13],"sgdLength":vals[14]}
def ktx_levels(b,h):
    out=[];p=80
    for i in range(h["levelCount"]):
        if p+24>len(b):break
        off,n,u=struct.unpack_from("<QQQ",b,p);out.append({"level":i,"offset":off,"length":n,"uncompressedLength":u});p+=24
    return out

def ktx(cmd,a):
    if not a:die("KTX2 path required")
    op=cmd.removeprefix("ktx2-");b=P(a[0]).read_bytes();h=ktxh(b);levels=ktx_levels(b,h)
    if op=="magic":emit({"valid":b[:12]==KTX_MAGIC,"magic":b[:12].hex()});return
    fields={"vk-format":"vkFormat","type-size":"typeSize","pixel-width":"pixelWidth","pixel-height":"pixelHeight","pixel-depth":"pixelDepth","layer-count":"layerCount","face-count":"faceCount","level-count":"levelCount","supercompression":"supercompression","dfd-offset":"dfdOffset","dfd-length":"dfdLength","kvd-offset":"kvdOffset","kvd-length":"kvdLength","sgd-offset":"sgdOffset","sgd-length":"sgdLength"}
    if op in fields:print(h[fields[op]]);return
    if op=="levels":emit(levels);return
    if op=="level-sizes":emit([x["length"] for x in levels]);return
    if op=="basis-detect":emit({"basis_or_uastc_supercompression":h["supercompression"] in (1,2),"scheme":h["supercompression"]});return
    if op=="cubemap-detect":print(str(h["faceCount"]==6).lower());return
    if op=="array-detect":print(str(h["layerCount"]>0).lower());return
    if op=="mipmap-detect":print(str(h["levelCount"]>1).lower());return
    if op=="sha256":print(hashlib.sha256(b).hexdigest());return
    if op=="header-json":
        q=dict(h);q["magic"]=h["magic"].hex();q["levels"]=levels;emit(q);return
    if op=="summary":emit({"validMagic":b[:12]==KTX_MAGIC,"width":h["pixelWidth"],"height":h["pixelHeight"],"depth":h["pixelDepth"],"layers":h["layerCount"],"faces":h["faceCount"],"levels":h["levelCount"],"vkFormat":h["vkFormat"],"supercompression":h["supercompression"]});return

def stl_info(p):
    b=P(p).read_bytes()
    binary=False;n=0;tris=[]
    if len(b)>=84:
        n0=struct.unpack_from("<I",b,80)[0]
        if 84+n0*50==len(b):binary=True;n=n0
    if binary:
        off=84
        mins=[float("inf")]*3;maxs=[float("-inf")]*3
        for _ in range(n):
            if off+50>len(b):break
            vals=struct.unpack_from("<12fH",b,off);off+=50
            for j in range(3):
                for k in (3,6,9):
                    mins[j]=min(mins[j],vals[k+j]);maxs[j]=max(maxs[j],vals[k+j])
        bb=None if n==0 else mins+maxs
        return {"format":"binary","triangles":n,"bbox":bb,"sizeValid":84+n*50==len(b)}
    s=b.decode(errors="replace")
    verts=[tuple(map(float,m)) for m in re.findall(r"(?im)^\s*vertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)",s)]
    n=len(re.findall(r"(?im)^\s*facet\s+normal\b",s))
    bb=bbox3(verts);return {"format":"ascii","triangles":n,"bbox":bb,"sizeValid":True}
def bbox3(pts):
    if not pts:return None
    return [min(p[0] for p in pts),min(p[1] for p in pts),min(p[2] for p in pts),max(p[0] for p in pts),max(p[1] for p in pts),max(p[2] for p in pts)]
def ply_header(p):
    b=P(p).read_bytes();end=b.find(b"end_header")
    if end<0:die("PLY end_header not found")
    nl=b.find(b"\n",end);nl=len(b) if nl<0 else nl+1
    s=b[:nl].decode(errors="replace");fmt=re.search(r"(?m)^format\s+(\S+)",s)
    elems=[{"name":m.group(1),"count":int(m.group(2))} for m in re.finditer(r"(?m)^element\s+(\S+)\s+(\d+)",s)]
    props=[m.group(1).strip() for m in re.finditer(r"(?m)^property\s+(.+)$",s)]
    return {"header":s,"headerBytes":nl,"format":fmt.group(1) if fmt else None,"elements":elems,"properties":props}
def mesh(cmd,a):
    if not a:die("mesh/material path required")
    op=cmd
    if op.startswith("stl-"):
        q=stl_info(a[0])
        if op=="stl-format":print(q["format"])
        elif op=="stl-triangle-count":print(q["triangles"])
        elif op=="stl-bbox":emit(q["bbox"])
        elif op=="stl-size-check":emit({"valid":q["sizeValid"]})
        else:print(hashlib.sha256(P(a[0]).read_bytes()).hexdigest())
        return
    if op.startswith("ply-"):
        q=ply_header(a[0])
        if op=="ply-format":print(q["format"] or "")
        elif op=="ply-elements":emit(q["elements"])
        elif op=="ply-vertex-count":print(next((x["count"] for x in q["elements"] if x["name"]=="vertex"),0))
        elif op=="ply-face-count":print(next((x["count"] for x in q["elements"] if x["name"]=="face"),0))
        elif op=="ply-properties":emit(q["properties"])
        elif op=="ply-header":print(q["header"],end="")
        else:print(hashlib.sha256(P(a[0]).read_bytes()).hexdigest())
        return
    s=P(a[0]).read_text(errors="replace")
    if op=="objmesh-vertex-count":print(len(re.findall(r"(?m)^\s*v\s+",s)));return
    if op=="objmesh-normal-count":print(len(re.findall(r"(?m)^\s*vn\s+",s)));return
    if op=="objmesh-texcoord-count":print(len(re.findall(r"(?m)^\s*vt\s+",s)));return
    if op=="objmesh-face-count":print(len(re.findall(r"(?m)^\s*f\s+",s)));return
    if op=="objmesh-object-names":emit(re.findall(r"(?m)^\s*o\s+(.+)$",s));return
    if op=="objmesh-group-names":emit(re.findall(r"(?m)^\s*g\s+(.+)$",s));return
    if op=="mtl-material-names":emit(re.findall(r"(?m)^\s*newmtl\s+(.+)$",s));return
    if op=="mtl-texture-files":emit(re.findall(r"(?m)^\s*map_[A-Za-z0-9_]+\s+(.+)$",s));return

def main():
    cmd=P(sys.argv[0]).name;a=sys.argv[1:]
    if cmd not in COMMANDS:
        if a and a[0] in COMMANDS:cmd=a.pop(0)
        elif not a or a[0] in ("-h","--help"):
            print("Shard 38 — glTF/GLB/KTX2 and 3D mesh utilities");print("\n".join(COMMANDS));return
        else:die("unknown command")
    if a and a[0] in ("-h","--help"):print(cmd+" — functional shard 38 utility");return
    if cmd in GLTF:gltf(cmd,a)
    elif cmd in GLB:glb(cmd,a)
    elif cmd in KTX:ktx(cmd,a)
    else:mesh(cmd,a)
if __name__=="__main__":main()
