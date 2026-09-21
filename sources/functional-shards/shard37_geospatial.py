#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,math,re,struct,sys,xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
P=Path

GEOJSON=[
"geojson-validate-basic","geojson-type","geojson-feature-count","geojson-geometry-count","geojson-point-count","geojson-bbox","geojson-properties","geojson-property-keys","geojson-crs-hints","geojson-coordinate-depth","geojson-empty-geometries","geojson-null-geometries","geojson-geometry-types","geojson-ids","geojson-centroid-approx","geojson-area-bbox","geojson-line-length-deg","geojson-polygon-rings","geojson-multiparts","geojson-normalize","geojson-minify","geojson-pretty","geojson-ndjson","geojson-sha256","geojson-summary"]
WKT=[
"wkt-type","wkt-dimension","wkt-coordinate-count","wkt-bbox","wkt-srid","wkt-strip-srid","wkt-point","wkt-linestring","wkt-polygon-rings","wkt-empty","wkt-normalize","wkt-to-geojson-lite","wkt-from-geojson-lite","wkt-sha256","wkt-summary"]
GPX=["gpx-tracks","gpx-routes","gpx-waypoints","gpx-trackpoints","gpx-bbox","gpx-elevation-range","gpx-time-range","gpx-distance-deg","gpx-names","gpx-summary"]
KML=["kml-placemarks","kml-points","kml-linestrings","kml-polygons","kml-coordinates","kml-names","kml-styles","kml-folders","kml-bbox","kml-summary"]
SLIPPY=["slippy-lonlat-to-tile","slippy-tile-to-bbox","slippy-quadkey-encode","slippy-quadkey-decode","slippy-tile-parent","slippy-tile-children","slippy-tile-neighbors","slippy-tile-count","slippy-url-template","slippy-tile-center"]
MVT=["mvt-wire-fields","mvt-layer-count","mvt-layer-names","mvt-feature-count","mvt-extent","mvt-version","mvt-key-count","mvt-value-count","mvt-sha256","mvt-summary"]
MLT=["mlt-version-byte","mlt-layer-count","mlt-layer-sizes","mlt-tags","mlt-v1-detect","mlt-v2-detect","mlt-varints","mlt-sha256","mlt-bytes","mlt-summary"]
PM=["pmtiles-header-v3","pmtiles-version","pmtiles-root-offset","pmtiles-root-length","pmtiles-json-offset","pmtiles-json-length","pmtiles-tile-type","pmtiles-compression","pmtiles-sha256","pmtiles-summary"]
COMMANDS=GEOJSON+WKT+GPX+KML+SLIPPY+MVT+MLT+PM
assert len(COMMANDS)==100 and len(set(COMMANDS))==100

def emit(x):
    if isinstance(x,(dict,list,tuple,Counter)):print(json.dumps(x,indent=2,ensure_ascii=False,default=str))
    else:print(x)
def die(s,c=2):print(s,file=sys.stderr);raise SystemExit(c)
def load_text(a):
    if not a: return sys.stdin.read()
    p=P(a[0]); return p.read_text(errors="replace") if p.exists() and p.is_file() else " ".join(a)
def load_json(a):
    s=load_text(a);return json.loads(s)

def geom_iter(obj):
    if not isinstance(obj,dict):return
    t=obj.get("type")
    if t=="FeatureCollection":
        for f in obj.get("features",[]): yield from geom_iter(f)
    elif t=="Feature":
        g=obj.get("geometry")
        if g is None: yield None
        else: yield g
    elif t=="GeometryCollection":
        for g in obj.get("geometries",[]): yield from geom_iter(g)
    else: yield obj

def coord_points(x):
    if isinstance(x,(list,tuple)):
        if len(x)>=2 and all(isinstance(v,(int,float)) for v in x[:2]):
            yield (float(x[0]),float(x[1]))
        else:
            for q in x: yield from coord_points(q)

def all_points(obj):
    for g in geom_iter(obj):
        if isinstance(g,dict):
            yield from coord_points(g.get("coordinates"))

def bbox_points(pts):
    pts=list(pts)
    if not pts:return None
    xs=[p[0] for p in pts];ys=[p[1] for p in pts]
    return [min(xs),min(ys),max(xs),max(ys)]

def coord_depth(x):
    if not isinstance(x,list):return 0
    if not x:return 1
    return 1+max(coord_depth(q) for q in x)

def geojson(cmd,a):
    op=cmd.removeprefix("geojson-");obj=load_json(a)
    geoms=list(geom_iter(obj));pts=list(all_points(obj))
    if op=="validate-basic":
        valid=isinstance(obj,dict) and isinstance(obj.get("type"),str)
        emit({"valid":valid,"type":obj.get("type") if isinstance(obj,dict) else None});return
    if op=="type":emit(obj.get("type"));return
    if op=="feature-count":print(len(obj.get("features",[])) if isinstance(obj,dict) and obj.get("type")=="FeatureCollection" else 1 if isinstance(obj,dict) and obj.get("type")=="Feature" else 0);return
    if op=="geometry-count":print(sum(g is not None for g in geoms));return
    if op=="point-count":print(len(pts));return
    if op=="bbox":emit(bbox_points(pts));return
    if op=="properties":
        vals=[]
        if obj.get("type")=="FeatureCollection":vals=[f.get("properties",{}) for f in obj.get("features",[]) if isinstance(f,dict)]
        elif obj.get("type")=="Feature":vals=[obj.get("properties",{})]
        emit(vals);return
    if op=="property-keys":
        keys=set()
        fs=obj.get("features",[]) if obj.get("type")=="FeatureCollection" else [obj] if obj.get("type")=="Feature" else []
        for f in fs:
            p=f.get("properties",{})
            if isinstance(p,dict):keys.update(p)
        emit(sorted(keys));return
    if op=="crs-hints":emit(obj.get("crs"));return
    if op=="coordinate-depth":
        ds=[coord_depth(g.get("coordinates")) for g in geoms if isinstance(g,dict) and "coordinates" in g];print(max(ds) if ds else 0);return
    if op=="empty-geometries":
        emit([g.get("type") for g in geoms if isinstance(g,dict) and g.get("coordinates") in ([],None)]);return
    if op=="null-geometries":print(sum(g is None for g in geoms));return
    if op=="geometry-types":emit(Counter(g.get("type") for g in geoms if isinstance(g,dict)));return
    if op=="ids":
        fs=obj.get("features",[]) if obj.get("type")=="FeatureCollection" else [obj] if obj.get("type")=="Feature" else []
        emit([f.get("id") for f in fs if "id" in f]);return
    if op=="centroid-approx":
        emit(None if not pts else [sum(x for x,_ in pts)/len(pts),sum(y for _,y in pts)/len(pts)]);return
    if op=="area-bbox":
        b=bbox_points(pts);print(0 if not b else (b[2]-b[0])*(b[3]-b[1]));return
    if op=="line-length-deg":
        total=0.0
        for g in geoms:
            if not isinstance(g,dict):continue
            t=g.get("type");c=g.get("coordinates")
            lines=[]
            if t=="LineString":lines=[c]
            elif t=="MultiLineString":lines=c or []
            for line in lines:
                ps=list(coord_points(line))
                total+=sum(math.hypot(ps[i][0]-ps[i-1][0],ps[i][1]-ps[i-1][1]) for i in range(1,len(ps)))
        print(total);return
    if op=="polygon-rings":
        n=0
        for g in geoms:
            if not isinstance(g,dict):continue
            if g.get("type")=="Polygon":n+=len(g.get("coordinates") or [])
            elif g.get("type")=="MultiPolygon":n+=sum(len(p or []) for p in (g.get("coordinates") or []))
        print(n);return
    if op=="multiparts":emit([g.get("type") for g in geoms if isinstance(g,dict) and str(g.get("type","")).startswith("Multi")]);return
    if op=="normalize":print(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False));return
    if op=="minify":print(json.dumps(obj,separators=(",",":"),ensure_ascii=False));return
    if op=="pretty":print(json.dumps(obj,indent=2,ensure_ascii=False));return
    if op=="ndjson":
        rows=obj.get("features",[]) if obj.get("type")=="FeatureCollection" else [obj]
        for r in rows:print(json.dumps(r,separators=(",",":"),ensure_ascii=False))
        return
    raw=json.dumps(obj,sort_keys=True,separators=(",",":")).encode()
    if op=="sha256":print(hashlib.sha256(raw).hexdigest());return
    if op=="summary":emit({"type":obj.get("type"),"features":len(obj.get("features",[])) if obj.get("type")=="FeatureCollection" else None,"geometries":sum(g is not None for g in geoms),"points":len(pts),"bbox":bbox_points(pts),"geometryTypes":Counter(g.get("type") for g in geoms if isinstance(g,dict))});return

def wkt_parts(s):
    raw=s.strip();srid=None
    m=re.match(r"(?is)^\s*SRID=(\d+)\s*;\s*(.*)$",raw)
    if m:srid=int(m.group(1));raw=m.group(2)
    m=re.match(r"(?is)^\s*([A-Z]+)\s*(ZM|Z|M)?\s*(EMPTY|\(.*\))\s*$",raw)
    if not m:return srid,"UNKNOWN","",raw
    return srid,m.group(1).upper(),(m.group(2) or "").upper(),m.group(3)

def wkt_nums(body):
    return [float(x) for x in re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?",body)]
def wkt_pts(body,dim=2):
    n=wkt_nums(body);return [(n[i],n[i+1]) for i in range(0,len(n)-1,dim)]
def fmt_num(x):
    return str(int(x)) if float(x).is_integer() else ("%g"%x)

def wkt(cmd,a):
    op=cmd.removeprefix("wkt-");s=load_text(a);srid,t,dim,body=wkt_parts(s);pts=wkt_pts(body,3 if "Z" in dim else 2)
    if op=="type":print(t);return
    if op=="dimension":print(dim or "2D");return
    if op=="coordinate-count":print(len(pts));return
    if op=="bbox":emit(bbox_points(pts));return
    if op=="srid":emit(srid);return
    if op=="strip-srid":print(re.sub(r"(?is)^\s*SRID=\d+\s*;\s*","",s).strip());return
    if op=="point":emit(list(pts[0]) if t=="POINT" and pts else None);return
    if op=="linestring":emit([list(p) for p in pts] if t=="LINESTRING" else []);return
    if op=="polygon-rings":print(body.count("(")-1 if t=="POLYGON" and body!="EMPTY" else 0);return
    if op=="empty":print(str(body=="EMPTY").lower());return
    if op=="normalize":
        prefix=f"SRID={srid};" if srid is not None else "";print(prefix+t+((" "+dim) if dim else "")+" "+re.sub(r"\s+"," ",body.strip()));return
    if op=="to-geojson-lite":
        if t=="POINT":g={"type":"Point","coordinates":list(pts[0]) if pts else []}
        elif t=="LINESTRING":g={"type":"LineString","coordinates":[list(p) for p in pts]}
        elif t=="POLYGON":
            rings=[]
            for q in re.findall(r"\(([^()]+)\)",body):
                ns=wkt_nums(q);rings.append([[ns[i],ns[i+1]] for i in range(0,len(ns)-1,2)])
            g={"type":"Polygon","coordinates":rings}
        else:g={"type":t.title(),"coordinates":[]}
        emit(g);return
    if op=="from-geojson-lite":
        g=json.loads(s);typ=g.get("type");c=g.get("coordinates",[])
        if typ=="Point":print("POINT ("+" ".join(fmt_num(x) for x in c[:2])+")")
        elif typ=="LineString":print("LINESTRING ("+", ".join(" ".join(fmt_num(x) for x in p[:2]) for p in c)+")")
        elif typ=="Polygon":print("POLYGON ("+", ".join("(" + ", ".join(" ".join(fmt_num(x) for x in p[:2]) for p in ring) + ")" for ring in c)+")")
        else:die("supported GeoJSON types: Point LineString Polygon")
        return
    if op=="sha256":print(hashlib.sha256(s.encode()).hexdigest());return
    if op=="summary":emit({"srid":srid,"type":t,"dimension":dim or "2D","empty":body=="EMPTY","coordinates":len(pts),"bbox":bbox_points(pts)});return

def local(tag):return tag.split("}")[-1]
def xmlroot(a):return ET.fromstring(load_text(a))
def coords_xml(root,names):
    pts=[]
    for e in root.iter():
        if local(e.tag) in names:
            if "lat" in e.attrib and "lon" in e.attrib:
                try:pts.append((float(e.attrib["lon"]),float(e.attrib["lat"])))
                except:pass
            elif e.text:
                for q in e.text.replace("\n"," ").split():
                    z=q.split(",")
                    if len(z)>=2:
                        try:pts.append((float(z[0]),float(z[1])))
                        except:pass
    return pts

def gpx(cmd,a):
    op=cmd.removeprefix("gpx-");r=xmlroot(a);pts=coords_xml(r,{"trkpt","rtept","wpt"})
    counts=Counter(local(e.tag) for e in r.iter())
    if op=="tracks":print(counts["trk"]);return
    if op=="routes":print(counts["rte"]);return
    if op=="waypoints":print(counts["wpt"]);return
    if op=="trackpoints":print(counts["trkpt"]);return
    if op=="bbox":emit(bbox_points(pts));return
    if op=="elevation-range":
        vals=[]
        for e in r.iter():
            if local(e.tag)=="ele" and e.text:
                try:vals.append(float(e.text))
                except:pass
        emit(None if not vals else [min(vals),max(vals)]);return
    if op=="time-range":
        vals=sorted(e.text.strip() for e in r.iter() if local(e.tag)=="time" and e.text);emit(None if not vals else [vals[0],vals[-1]]);return
    if op=="distance-deg":print(sum(math.hypot(pts[i][0]-pts[i-1][0],pts[i][1]-pts[i-1][1]) for i in range(1,len(pts))));return
    if op=="names":emit([e.text for e in r.iter() if local(e.tag)=="name" and e.text]);return
    if op=="summary":emit({"tracks":counts["trk"],"routes":counts["rte"],"waypoints":counts["wpt"],"trackpoints":counts["trkpt"],"bbox":bbox_points(pts)});return

def kml(cmd,a):
    op=cmd.removeprefix("kml-");r=xmlroot(a);counts=Counter(local(e.tag) for e in r.iter());pts=coords_xml(r,{"coordinates"})
    if op=="placemarks":print(counts["Placemark"]);return
    if op=="points":print(counts["Point"]);return
    if op=="linestrings":print(counts["LineString"]);return
    if op=="polygons":print(counts["Polygon"]);return
    if op=="coordinates":emit([list(x) for x in pts]);return
    if op=="names":emit([e.text for e in r.iter() if local(e.tag)=="name" and e.text]);return
    if op=="styles":print(counts["Style"]+counts["StyleMap"]);return
    if op=="folders":print(counts["Folder"]);return
    if op=="bbox":emit(bbox_points(pts));return
    if op=="summary":emit({"placemarks":counts["Placemark"],"points":counts["Point"],"linestrings":counts["LineString"],"polygons":counts["Polygon"],"bbox":bbox_points(pts)});return

def clamp_lat(lat):return max(-85.05112878,min(85.05112878,lat))
def ll2tile(lon,lat,z):
    n=2**z;x=(lon+180.0)/360.0*n;lr=math.radians(clamp_lat(lat));y=(1-math.asinh(math.tan(lr))/math.pi)/2*n
    return int(x),int(y)
def tile2ll(x,y,z):
    n=2**z;lon=x/n*360-180;lat=math.degrees(math.atan(math.sinh(math.pi*(1-2*y/n))));return lon,lat
def slippy(cmd,a):
    op=cmd.removeprefix("slippy-")
    if op=="lonlat-to-tile":
        lon,lat,z=float(a[0]),float(a[1]),int(a[2]);x,y=ll2tile(lon,lat,z);emit({"z":z,"x":x,"y":y});return
    z,x,y=int(a[0]),int(a[1]),int(a[2])
    if op=="tile-to-bbox":
        w,n=tile2ll(x,y,z);e,s=tile2ll(x+1,y+1,z);emit([w,s,e,n]);return
    if op=="quadkey-encode":
        q=""
        for i in range(z,0,-1):
            bit=1<<(i-1);d=(1 if x&bit else 0)+(2 if y&bit else 0);q+=str(d)
        print(q);return
    if op=="quadkey-decode":
        q=a[0];x=y=0
        for i,ch in enumerate(q):
            bit=1<<(len(q)-i-1);d=int(ch);x|=bit if d&1 else 0;y|=bit if d&2 else 0
        emit({"z":len(q),"x":x,"y":y});return
    if op=="tile-parent":emit(None if z==0 else {"z":z-1,"x":x//2,"y":y//2});return
    if op=="tile-children":emit([{"z":z+1,"x":x*2+dx,"y":y*2+dy} for dy in (0,1) for dx in (0,1)]);return
    if op=="tile-neighbors":emit([{"z":z,"x":x+dx,"y":y+dy} for dy in (-1,0,1) for dx in (-1,0,1) if dx or dy]);return
    if op=="tile-count":print(4**z);return
    if op=="url-template":
        tpl=a[3] if len(a)>3 else "https://tiles/{z}/{x}/{y}.pbf";print(tpl.replace("{z}",str(z)).replace("{x}",str(x)).replace("{y}",str(y)));return
    if op=="tile-center":
        w,n=tile2ll(x,y,z);e,s=tile2ll(x+1,y+1,z);emit([(w+e)/2,(n+s)/2]);return

def varint(b,p):
    n=0;s=0
    while p<len(b):
        x=b[p];p+=1;n|=(x&0x7f)<<s
        if not x&0x80:return n,p
        s+=7
        if s>70:die("varint too large")
    die("truncated varint")
def pb_fields(b):
    out=[];p=0
    while p<len(b):
        key,p=varint(b,p);num=key>>3;wt=key&7
        if wt==0:v,p=varint(b,p)
        elif wt==1:v=b[p:p+8];p+=8
        elif wt==2:
            n,p=varint(b,p);v=b[p:p+n];p+=n
        elif wt==5:v=b[p:p+4];p+=4
        else:break
        out.append((num,wt,v))
    return out
def mvt_layers(b):
    return [v for n,w,v in pb_fields(b) if n==3 and w==2]
def layer_info(lb):
    f=pb_fields(lb);name="";features=keys=values=0;extent=version=None
    for n,w,v in f:
        if n==1 and w==2:name=v.decode(errors="replace")
        elif n==2 and w==2:features+=1
        elif n==3 and w==2:keys+=1
        elif n==4 and w==2:values+=1
        elif n==5 and w==0:extent=v
        elif n==15 and w==0:version=v
    return {"name":name,"features":features,"keys":keys,"values":values,"extent":extent,"version":version}
def mvt(cmd,a):
    op=cmd.removeprefix("mvt-");b=P(a[0]).read_bytes();layers=[layer_info(x) for x in mvt_layers(b)]
    if op=="wire-fields":emit([{"field":n,"wire":w,"size":len(v) if isinstance(v,bytes) else None,"value":v if not isinstance(v,bytes) else None} for n,w,v in pb_fields(b)]);return
    if op=="layer-count":print(len(layers));return
    if op=="layer-names":emit([x["name"] for x in layers]);return
    if op=="feature-count":print(sum(x["features"] for x in layers));return
    if op=="extent":emit({x["name"]:x["extent"] for x in layers});return
    if op=="version":emit({x["name"]:x["version"] for x in layers});return
    if op=="key-count":print(sum(x["keys"] for x in layers));return
    if op=="value-count":print(sum(x["values"] for x in layers));return
    if op=="sha256":print(hashlib.sha256(b).hexdigest());return
    if op=="summary":emit({"layers":layers,"bytes":len(b)});return

def mlt_layers(b):
    out=[];p=0
    while p<len(b):
        size,q=varint(b,p)
        if q>=len(b):break
        tag=b[q];start=q+1;end=start+max(0,size-1)
        if end>len(b):die("truncated MLT layer")
        out.append({"size":size,"tag":tag,"body_offset":start,"end":end});p=end
    return out
def mlt(cmd,a):
    op=cmd.removeprefix("mlt-");b=P(a[0]).read_bytes();ls=mlt_layers(b)
    if op=="version-byte":emit(ls[0]["tag"] if ls else None);return
    if op=="layer-count":print(len(ls));return
    if op=="layer-sizes":emit([x["size"] for x in ls]);return
    if op=="tags":emit([x["tag"] for x in ls]);return
    if op=="v1-detect":print(str(bool(ls) and ls[0]["tag"]==1).lower());return
    if op=="v2-detect":print(str(bool(ls) and ls[0]["tag"]==2).lower());return
    if op=="varints":
        vals=[];p=0
        while p<len(b):
            try:v,p2=varint(b,p);vals.append(v);p=p2
            except SystemExit:break
        emit(vals[:1000]);return
    if op=="sha256":print(hashlib.sha256(b).hexdigest());return
    if op=="bytes":print(len(b));return
    if op=="summary":emit({"bytes":len(b),"layers":len(ls),"tags":[x["tag"] for x in ls],"sizes":[x["size"] for x in ls]});return

def pmh(b):
    if len(b)<127:die("PMTiles v3 header requires 127 bytes")
    return {
      "magic":b[:7].decode(errors="replace"),"version":b[7],
      "root_offset":struct.unpack_from("<Q",b,8)[0],"root_length":struct.unpack_from("<Q",b,16)[0],
      "json_offset":struct.unpack_from("<Q",b,24)[0],"json_length":struct.unpack_from("<Q",b,32)[0],
      "leaf_offset":struct.unpack_from("<Q",b,40)[0],"leaf_length":struct.unpack_from("<Q",b,48)[0],
      "tile_data_offset":struct.unpack_from("<Q",b,56)[0],"tile_data_length":struct.unpack_from("<Q",b,64)[0],
      "addressed_tiles":struct.unpack_from("<Q",b,72)[0],"tile_entries":struct.unpack_from("<Q",b,80)[0],"tile_contents":struct.unpack_from("<Q",b,88)[0],
      "clustered":b[96],"internal_compression":b[97],"tile_compression":b[98],"tile_type":b[99],"min_zoom":b[100],"max_zoom":b[101]
    }
def pmtiles(cmd,a):
    op=cmd.removeprefix("pmtiles-");b=P(a[0]).read_bytes();h=pmh(b)
    if op=="header-v3":emit(h);return
    if op=="version":print(h["version"]);return
    if op=="root-offset":print(h["root_offset"]);return
    if op=="root-length":print(h["root_length"]);return
    if op=="json-offset":print(h["json_offset"]);return
    if op=="json-length":print(h["json_length"]);return
    if op=="tile-type":print(h["tile_type"]);return
    if op=="compression":emit({"internal":h["internal_compression"],"tile":h["tile_compression"]});return
    if op=="sha256":print(hashlib.sha256(b).hexdigest());return
    if op=="summary":emit(h);return

def main():
    cmd=P(sys.argv[0]).name;a=sys.argv[1:]
    if cmd not in COMMANDS:
        if a and a[0] in COMMANDS:cmd=a.pop(0)
        elif not a or a[0] in ("-h","--help"):
            print("Shard 37 — geospatial, MapLibre/tiles and map-format utilities");print("\n".join(COMMANDS));return
        else:die("unknown command")
    if a and a[0] in ("-h","--help"):print(cmd+" — functional shard 37 utility");return
    if cmd in GEOJSON:geojson(cmd,a)
    elif cmd in WKT:wkt(cmd,a)
    elif cmd in GPX:gpx(cmd,a)
    elif cmd in KML:kml(cmd,a)
    elif cmd in SLIPPY:slippy(cmd,a)
    elif cmd in MVT:mvt(cmd,a)
    elif cmd in MLT:mlt(cmd,a)
    else:pmtiles(cmd,a)
if __name__=="__main__":main()
