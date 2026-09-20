#!/usr/bin/env python3
from __future__ import annotations
import sys,struct,zlib,binascii,re,math,json,colorsys,xml.etree.ElementTree as ET,subprocess,shutil
from pathlib import Path
VERSION="2.0.0"
def out(x):print(json.dumps(x,indent=2,sort_keys=True,default=str))
def die(x,c=2):print(x,file=sys.stderr);raise SystemExit(c)
def rb(a):return Path(a[0]).read_bytes()
def rt(a):return Path(a[0]).read_text(errors="replace") if a and Path(a[0]).exists() else (" ".join(a) if a else sys.stdin.read())
def png_chunks(b):
    if b[:8]!=b"\x89PNG\r\n\x1a\n":die("not PNG")
    p=8;rows=[]
    while p+12<=len(b):
        n=int.from_bytes(b[p:p+4],"big");t=b[p+4:p+8];d=b[p+8:p+8+n];crc=int.from_bytes(b[p+8+n:p+12+n],"big")
        rows.append({"type":t.decode(errors="replace"),"length":n,"crc_valid":(binascii.crc32(t+d)&0xffffffff)==crc,"data":d});p+=12+n
        if t==b"IEND":break
    return rows
def png_parse(a):out([{k:v for k,v in x.items() if k!="data"} for x in png_chunks(rb(a))])
def png_ihdr(a):
    c=png_chunks(rb(a));d=next(x["data"] for x in c if x["type"]=="IHDR")
    w,h,bd,ct,comp,filt,inter=struct.unpack(">IIBBBBB",d);out({"width":w,"height":h,"bit_depth":bd,"color_type":ct,"compression":comp,"filter":filt,"interlace":inter})
def png_opt(a):
    b=rb(a);c=png_chunks(b);idat=b"".join(x["data"] for x in c if x["type"]=="IDAT");raw=zlib.decompress(idat);best=zlib.compress(raw,9);out({"original_idat_bytes":len(idat),"recompressed_bytes":len(best),"saved":len(idat)-len(best)})
def jpeg_segments(b):
    if b[:2]!=b"\xff\xd8":die("not JPEG")
    p=2;rows=[]
    while p<len(b):
        if b[p]!=0xff:p+=1;continue
        while p<len(b) and b[p]==0xff:p+=1
        if p>=len(b):break
        m=b[p];p+=1
        if m in (0xd8,0xd9):rows.append((m,b"")); 
        if m==0xd9:break
        if m in range(0xd0,0xd8) or m==0x01:continue
        if p+2>len(b):break
        n=int.from_bytes(b[p:p+2],"big");d=b[p+2:p+n];rows.append((m,d));p+=n
        if m==0xda:break
    return rows
def jpeg_mark(a):out([{"marker":hex(m),"bytes":len(d)} for m,d in jpeg_segments(rb(a))])
def jpeg_prog(a):out({"progressive":any(m==0xc2 for m,d in jpeg_segments(rb(a))),"baseline":any(m==0xc0 for m,d in jpeg_segments(rb(a)))})
def jpeg_strip(a):
    if len(a)<2:die("INPUT OUTPUT")
    b=rb(a)
    if b[:2]!=b"\xff\xd8":die("not JPEG")
    p=2;o=bytearray(b[:2])
    while p<len(b):
        if b[p]!=0xff:o.extend(b[p:]);break
        start=p
        while p<len(b) and b[p]==0xff:p+=1
        if p>=len(b):break
        m=b[p];p+=1
        if m==0xd9:o.extend(b[start:p]);break
        if m in range(0xd0,0xd8) or m==0x01:o.extend(b[start:p]);continue
        if p+2>len(b):break
        n=int.from_bytes(b[p:p+2],"big");seg=b[start:p+n]
        if m!=0xe1:o.extend(seg)
        p+=n
        if m==0xda:o.extend(b[p:]);break
    Path(a[1]).write_bytes(o);out({"output":a[1],"bytes":len(o)})
def gif_info(a):
    b=rb(a)
    if b[:6] not in (b"GIF87a",b"GIF89a"):die("not GIF")
    w,h=struct.unpack_from("<HH",b,6);frames=b.count(b"\x2c");gct=bool(b[10]&0x80);gsize=2**((b[10]&7)+1) if gct else 0
    out({"width":w,"height":h,"frames":frames,"global_palette_entries":gsize})
def gif_palette(a):
    b=rb(a);g=bool(b[10]&0x80);n=2**((b[10]&7)+1) if g else 0;off=13;out([{"r":b[off+i*3],"g":b[off+i*3+1],"b":b[off+i*3+2]} for i in range(n)])
def riff(a):
    b=rb(a)
    if b[:4] not in (b"RIFF",b"RIFX"):die("not RIFF")
    le=b[:4]==b"RIFF";p=12;rows=[]
    while p+8<=len(b):
        n=int.from_bytes(b[p+4:p+8],"little" if le else "big");rows.append({"id":b[p:p+4].decode(errors="replace"),"size":n,"offset":p+8});p+=8+n+(n&1)
    out({"form":b[8:12].decode(errors="replace"),"chunks":rows})
def webp(a):riff(a)
def isobmff(a):
    b=rb(a);p=0;rows=[]
    while p+8<=len(b):
        n=int.from_bytes(b[p:p+4],"big");typ=b[p+4:p+8].decode(errors="replace");hdr=8
        if n==1 and p+16<=len(b):n=int.from_bytes(b[p+8:p+16],"big");hdr=16
        if n==0:n=len(b)-p
        if n<hdr or p+n>len(b):break
        rows.append({"type":typ,"size":n,"offset":p});p+=n
    out(rows)
def bmp(a):
    b=rb(a)
    if b[:2]!=b"BM":die("not BMP")
    out({"file_size":int.from_bytes(b[2:6],"little"),"pixel_offset":int.from_bytes(b[10:14],"little"),"dib_size":int.from_bytes(b[14:18],"little"),"width":int.from_bytes(b[18:22],"little",signed=True),"height":int.from_bytes(b[22:26],"little",signed=True),"bpp":int.from_bytes(b[28:30],"little")})
def ico(a):
    b=rb(a);n=int.from_bytes(b[4:6],"little");rows=[]
    for i in range(n):
        o=6+i*16;rows.append({"width":b[o] or 256,"height":b[o+1] or 256,"colors":b[o+2],"bytes":int.from_bytes(b[o+8:o+12],"little"),"offset":int.from_bytes(b[o+12:o+16],"little")})
    out(rows)
def tga(a):
    b=rb(a);out({"id_length":b[0],"color_map_type":b[1],"image_type":b[2],"width":int.from_bytes(b[12:14],"little"),"height":int.from_bytes(b[14:16],"little"),"pixel_depth":b[16]})
def tiff(a):
    b=rb(a);le=b[:2]==b"II";be=b[:2]==b"MM"
    if not(le or be):die("not TIFF")
    end="little" if le else "big";off=int.from_bytes(b[4:8],end);n=int.from_bytes(b[off:off+2],end);out({"endian":end,"ifd_offset":off,"tag_count":n})
def svg_path(a):
    s=rt(a);prec=int(a[1]) if len(a)>1 and a[1].isdigit() else 3
    print(re.sub(r"-?\d+\.\d+",lambda m:(f"{float(m.group()):.{prec}f}".rstrip("0").rstrip(".")),s))
def svg_viewbox(a):
    root=ET.fromstring(rt(a));w=root.get("width");h=root.get("height")
    if root.get("viewBox") is None and w and h:
        num=lambda x:re.sub(r"[^0-9.+-]","",x);root.set("viewBox",f"0 0 {num(w)} {num(h)}")
    print(ET.tostring(root,encoding="unicode"))
def svg_clean(a):
    root=ET.fromstring(rt(a))
    for parent in root.iter():
        for child in list(parent):
            if child.tag.lower().endswith("script"):parent.remove(child)
        for k in list(parent.attrib):
            if k.lower().startswith("on") or "href" in k.lower() and str(parent.attrib[k]).lower().startswith("javascript:"):del parent.attrib[k]
    print(ET.tostring(root,encoding="unicode"))
def parse_hex(s):
    s=s.strip().lstrip("#")
    if len(s)==3:s="".join(c*2 for c in s)
    return tuple(int(s[i:i+2],16) for i in (0,2,4))
def color(a):
    r,g,b=parse_hex(a[0]);h,l,s=colorsys.rgb_to_hls(r/255,g/255,b/255);hh,ss,v=colorsys.rgb_to_hsv(r/255,g/255,b/255);k=1-max(r,g,b)/255;c=(1-r/255-k)/(1-k) if k<1 else 0;m=(1-g/255-k)/(1-k) if k<1 else 0;y=(1-b/255-k)/(1-k) if k<1 else 0
    out({"rgb":[r,g,b],"hex":"#%02x%02x%02x"%(r,g,b),"hsl":[h*360,s,l],"hsv":[hh*360,ss,v],"cmyk":[c,m,y,k]})
def palette(a):
    r,g,b=parse_hex(a[0]);h,l,s=colorsys.rgb_to_hls(r/255,g/255,b/255)
    mk=lambda dh:"#%02x%02x%02x"%tuple(round(x*255) for x in colorsys.hls_to_rgb((h+dh)%1,l,s))
    out({"base":a[0],"complement":mk(.5),"triad":[mk(1/3),mk(2/3)]})
def luminance(rgb):
    xs=[]
    for c in rgb:
        v=c/255;xs.append(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4)
    return .2126*xs[0]+.7152*xs[1]+.0722*xs[2]
def contrast(a):
    l1,l2=luminance(parse_hex(a[0])),luminance(parse_hex(a[1]));ratio=(max(l1,l2)+.05)/(min(l1,l2)+.05);out({"ratio":ratio,"AA_normal":ratio>=4.5,"AAA_normal":ratio>=7})
def cube(a):
    s=rt(a);size=re.search(r"(?m)^LUT_3D_SIZE\s+(\d+)",s);rows=[l for l in s.splitlines() if re.match(r"^\s*[-.\d]+\s+[-.\d]+\s+[-.\d]+\s*$",l)]
    out({"size":int(size.group(1)) if size else None,"entries":len(rows),"valid":bool(size) and len(rows)==int(size.group(1))**3})
def hist(a):
    b=rb(a);out({"byte_histogram":{str(i):b.count(bytes([i])) for i in range(256) if b.count(bytes([i]))}})
def aspect(a):
    if len(a)<4:die("WIDTH HEIGHT PAR_NUM PAR_DEN")
    w,h,pn,pd=map(float,a[:4]);out({"display_aspect":w*pn/(h*pd),"pixel_aspect":pn/pd})
def dim(a):
    b=rb(a)
    if b[:8]==b"\x89PNG\r\n\x1a\n":fmt="png";w=int.from_bytes(b[16:20],"big");h=int.from_bytes(b[20:24],"big")
    elif b[:6] in (b"GIF87a",b"GIF89a"):fmt="gif";w=int.from_bytes(b[6:8],"little");h=int.from_bytes(b[8:10],"little")
    elif b[:2]==b"BM":fmt="bmp";w=int.from_bytes(b[18:22],"little",signed=True);h=abs(int.from_bytes(b[22:26],"little",signed=True))
    else:fmt="unknown";w=h=None
    out({"format":fmt,"width":w,"height":h})
def wav_fmt(a):
    b=rb(a);p=b.find(b"fmt ")
    if p<0:die("fmt missing")
    n=int.from_bytes(b[p+4:p+8],"little");d=b[p+8:p+8+n];fmt,ch,rate,byterate,align,bps=struct.unpack_from("<HHIIHH",d,0);out({"format":fmt,"channels":ch,"sample_rate":rate,"byte_rate":byterate,"block_align":align,"bits_per_sample":bps})
def flac(a):
    b=rb(a)
    if b[:4]!=b"fLaC":die("not FLAC")
    out({"valid":True,"first_block_type":b[4]&0x7f,"first_block_last":bool(b[4]&0x80),"first_block_length":int.from_bytes(b[5:8],"big")})
def id3(a):
    b=rb(a)
    if b[:3]!=b"ID3":die("no ID3v2")
    size=((b[6]&127)<<21)|((b[7]&127)<<14)|((b[8]&127)<<7)|(b[9]&127);out({"version":f"2.{b[3]}.{b[4]}","flags":b[5],"tag_size":size})
def mp3sync(a):
    b=rb(a);offs=[i for i in range(len(b)-1) if b[i]==0xff and b[i+1]&0xe0==0xe0];out({"frames_found":len(offs),"first_offsets":offs[:100]})
def ogg(a):
    b=rb(a)
    if b[:4]!=b"OggS":die("not Ogg")
    out({"version":b[4],"header_type":b[5],"granule":int.from_bytes(b[6:14],"little"),"serial":int.from_bytes(b[14:18],"little"),"sequence":int.from_bytes(b[18:22],"little"),"segments":b[26]})
def opus(a):
    b=rb(a);p=b.find(b"OpusHead")
    if p<0:die("OpusHead missing")
    out({"channels":b[p+9],"preskip":int.from_bytes(b[p+10:p+12],"little"),"input_rate":int.from_bytes(b[p+12:p+16],"little")})
def vorbis(a):
    b=rb(a);strings=re.findall(rb"[\x20-\x7e]{4,}",b);out([x.decode(errors="replace") for x in strings[:200] if b"=" in x or b"vorbis" in x.lower()])
def adts(a):
    b=rb(a)
    if len(b)<7 or b[0]!=0xff or b[1]&0xf6!=0xf0:die("not ADTS")
    out({"profile":((b[2]>>6)&3)+1,"sample_rate_index":(b[2]>>2)&15,"channels":((b[2]&1)<<2)|(b[3]>>6),"frame_length":((b[3]&3)<<11)|(b[4]<<3)|(b[5]>>5)})
def midi(a):
    b=rb(a)
    if b[:4]!=b"MThd":die("not MIDI")
    out({"header_length":int.from_bytes(b[4:8],"big"),"format":int.from_bytes(b[8:10],"big"),"tracks":int.from_bytes(b[10:12],"big"),"division":int.from_bytes(b[12:14],"big"),"track_chunks":b.count(b"MTrk")})
def pcm(a):
    if len(a)<5:die("BYTES SRC_RATE DST_RATE CHANNELS BITS")
    n,sr,dr,ch,bits=map(float,a[:5]);samples=n/(ch*(bits/8));out({"source_samples":samples,"source_seconds":samples/sr,"target_samples":round(samples*dr/sr),"target_bytes":round(samples*dr/sr*ch*(bits/8))})
def duration(a):
    n,rate,ch,bits=map(float,a[:4]);out({"seconds":n/(rate*ch*(bits/8))})
def bitrate(a):
    vals=[float(x) for x in a];out({"mean":sum(vals)/len(vals) if vals else None,"min":min(vals) if vals else None,"max":max(vals) if vals else None,"variable":len(set(vals))>1})
def ffprobe(a):
    exe=shutil.which("ffprobe")
    if not exe:out({"available":False});return
    r=subprocess.run([exe,"-v","error","-show_format","-show_streams","-of","json",a[0]],capture_output=True,text=True);print(r.stdout if r.returncode==0 else json.dumps({"error":r.stderr}))
def ebml(a):
    b=rb(a);out({"ebml_magic":b[:4].hex(),"valid":b[:4]==b"\x1a\x45\xdf\xa3","bytes":len(b)})
def srt(a):
    if len(a)<2:die("FILE OFFSET_MS")
    off=int(a[1]);s=Path(a[0]).read_text()
    def f(m):
        def one(x):
            h,mi,rest=x.split(":");sec,ms=rest.split(",");t=max(0,((int(h)*60+int(mi))*60+int(sec))*1000+int(ms)+off);return f"{t//3600000:02d}:{t//60000%60:02d}:{t//1000%60:02d},{t%1000:03d}"
        return one(m.group(1))+" --> "+one(m.group(2))
    print(re.sub(r"(\d\d:\d\d:\d\d,\d\d\d)\s+-->\s+(\d\d:\d\d:\d\d,\d\d\d)",f,s))
def vtt(a):
    s=rt(a);errs=[] 
    if not s.lstrip().startswith("WEBVTT"):errs.append("missing WEBVTT header")
    cues=re.findall(r"(?m)^(\d\d:\d\d(?:\.\d\d\d)?|\d\d:\d\d:\d\d\.\d\d\d)\s+-->\s+(.+)$",s);out({"valid":not errs,"errors":errs,"cues":len(cues)})
def yuv(a):
    w,h=map(int,a[:2]);fmt=a[2].lower() if len(a)>2 else "420";factor={"420":1.5,"422":2,"444":3}.get(fmt,1.5);out({"bytes_per_frame":int(w*h*factor)})
def fps(a):
    frame=int(a[0]);fps=float(a[1]);sec=frame/fps;out({"seconds":sec,"timecode":f"{int(sec//3600):02d}:{int(sec//60)%60:02d}:{int(sec)%60:02d}:{frame%round(fps):02d}"})
def dpi(a):
    pxw,pxh,inchw,inchh=map(float,a[:4]);out({"dpi_x":pxw/inchw,"dpi_y":pxh/inchh,"diagonal_inches":math.hypot(inchw,inchh)})
def ratio(a):
    w,h=map(int,a[:2]);g=math.gcd(w,h);out({"ratio":[w//g,h//g],"decimal":w/h})
def kelvin(a):
    k=max(1000,min(40000,float(a[0])))/100
    r=255 if k<=66 else 329.698727446*((k-60)**-0.1332047592)
    g=99.4708025861*math.log(k)-161.1195681661 if k<=66 else 288.1221695283*((k-60)**-0.0755148492)
    b=255 if k>=66 else (0 if k<=19 else 138.5177312231*math.log(k-10)-305.044792731)
    out({"rgb":[round(max(0,min(255,x))) for x in (r,g,b)]})
def bayer(a):
    pat=(a[0] if a else "RGGB").upper()
    if pat not in {"RGGB","BGGR","GRBG","GBRG"}:die("bad Bayer pattern")
    out([[pat[0],pat[1]],[pat[2],pat[3]]])
COMMANDS={"png-chunk-parser":png_parse,"png-ihdr-analyzer":png_ihdr,"png-crush-optimizer":png_opt,"jpeg-exif-stripper":jpeg_strip,"jpeg-marker-parser":jpeg_mark,"jpeg-progressive-chk":jpeg_prog,"gif-frame-counter":gif_info,"gif-palette-extractor":gif_palette,"webp-vp8-chunk-view":webp,"avif-box-inspector":isobmff,"heif-item-parser":isobmff,"bmp-dib-header-dump":bmp,"ico-icon-dir-parser":ico,"tga-header-analyzer":tga,"tiff-ifd-inspector":tiff,"svg-path-optimizer":svg_path,"svg-viewbox-fixer":svg_viewbox,"svg-xml-sanitizer":svg_clean,"color-hex-rgb-hsl":color,"color-palette-generator":palette,"color-contrast-wcag":contrast,"lut-color-cube-parser":cube,"histogram-image-cli":hist,"pixel-aspect-ratio":aspect,"image-dimension-probe":dim,"wav-riff-chunk-dump":riff,"wav-fmt-spec-checker":wav_fmt,"flac-metadata-block":flac,"mp3-id3v2-tag-dump":id3,"mp3-frame-sync-chk":mp3sync,"ogg-page-header-dump":ogg,"opus-head-packet-chk":opus,"vorbis-comment-reader":vorbis,"aac-adts-header-dump":adts,"midi-track-event-view":midi,"pcm-sample-rate-conv":pcm,"audio-duration-calc":duration,"audio-bitrate-sampler":bitrate,"ffmpeg-probe-lite":ffprobe,"mp4-moov-atom-parser":isobmff,"mkv-ebml-header-dump":ebml,"avi-riff-list-parser":riff,"subtitle-srt-time-shift":srt,"subtitle-vtt-validator":vtt,"yuv-frame-calculator":yuv,"video-fps-timecode":fps,"dpi-calculator-cli":dpi,"aspect-ratio-reducer":ratio,"color-temperature-calc":kelvin,"bayer-pattern-matrix":bayer}
def main():
    if len(COMMANDS)!=50:die(f"command count {len(COMMANDS)}")
    p=Path(sys.argv[0]).name
    if p in COMMANDS:cmd,args=p,sys.argv[1:]
    else:
        if len(sys.argv)<2 or sys.argv[1] in ("-h","--help"):print("OceanStudio functional shard 14");print("\n".join(sorted(COMMANDS)));return
        if sys.argv[1] in ("-v","--version"):print(VERSION);return
        cmd,args=sys.argv[1],sys.argv[2:]
    if cmd not in COMMANDS:die("unknown command: "+cmd)
    COMMANDS[cmd](args)
if __name__=="__main__":main()
