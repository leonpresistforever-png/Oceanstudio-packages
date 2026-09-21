#!/usr/bin/env python3
from __future__ import annotations
import configparser,hashlib,json,math,os,re,shlex,shutil,socket,struct,subprocess,sys,tarfile,tempfile,urllib.parse
from collections import Counter
from pathlib import Path
P=Path

VNC=["vnc-uri-parse","vnc-endpoint","vnc-default-port","vnc-port-check","vnc-rfb-version","vnc-rfb-security-types","vnc-rfb-pixel-format","vnc-rfb-encoding-names","vnc-rfb-encoding-id","vnc-rfb-rect-header","vnc-rfb-key-event","vnc-rfb-pointer-event","vnc-rfb-cuttext-size","vnc-rfb-framebuffer-request","vnc-password-length-check","vnc-session-env","vnc-display-port","vnc-port-display","vnc-localhost-check","vnc-websocket-url","novnc-url","novnc-query","novnc-token-path","novnc-listen-args","novnc-proxy-args","novnc-ssl-args","novnc-path-info","novnc-config-json","novnc-session-json","novnc-health"]
WINE=["wine-prefix-path","wine-prefix-info","wine-prefix-size","wine-prefix-drives","wine-prefix-system-reg","wine-prefix-user-reg","wine-prefix-userdef-reg","wine-reg-sections","wine-reg-key-count","wine-reg-value-count","wine-reg-search","wine-drive-map","wine-path-to-win","wine-path-to-unix","wine-pe-arch","wine-pe-subsystem","wine-pe-sections","wine-pe-import-hints","wine-pe-export-hints","wine-dll-search","wine-env","wine-wow64-hints","wine-prefix-backup-list","wine-log-summary","wine-launch-plan"]
BOX=["box64-rc-parse","box64-rc-get","box64-rc-sections","box64-env-list","box64-env-merge","box64-elf-arch","box64-elf-needed-hints","box64-x64-check","box64-arm64-check","box64-library-map","box64-cache-path","box64-cache-size","box64-log-warnings","box64-log-missing-libs","box64-wine-command","box64-run-plan","box64-dynarec-flags","box64-page-size-check","box64-host-info","box64-compat-summary"]
X11=["x11-display-parse","x11-display-env","x11-socket-path","x11-auth-path","x11-xauthority-list","x11-font-paths","x11-color-parse","x11-geometry-parse","x11-screen-size","x11-dpi","x11-xrandr-parse","x11-xinput-parse","x11-xkb-layout","x11-lib-scan","x11-libx11-check","x11-libxcb-check","x11-libxext-check","x11-libxrender-check","x11-libxft-check","x11-libxss-check","x11-opengl-env","x11-mesa-env","x11-software-render-env","x11-vnc-plan","x11-stack-summary"]
COMMANDS=VNC+WINE+BOX+X11
assert len(COMMANDS)==100 and len(set(COMMANDS))==100

def emit(x):
    if isinstance(x,(dict,list,tuple,Counter)):print(json.dumps(x,indent=2,ensure_ascii=False,default=str))
    else:print(x)
def die(s,c=2):print(s,file=sys.stderr);raise SystemExit(c)
def readtext(a):
    if not a:return sys.stdin.read()
    p=P(a[0]);return p.read_text(errors="replace") if p.exists() and p.is_file() else " ".join(a)
def size_path(p):
    p=P(p)
    if p.is_file():return p.stat().st_size
    return sum(x.stat().st_size for x in p.rglob("*") if x.is_file())

RFB_ENCODINGS={0:"raw",1:"copyrect",2:"rre",5:"hextile",6:"zlib",7:"tight",-239:"cursor",-223:"desktop-size",-308:"extended-desktop-size",-313:"continuous-updates"}

def vnc(cmd,a):
    op=cmd
    if op=="vnc-uri-parse":
        if not a:die("vnc://host:port required")
        u=urllib.parse.urlsplit(a[0]);emit({"scheme":u.scheme,"host":u.hostname,"port":u.port or 5900,"display":((u.port or 5900)-5900) if (u.port or 5900)>=5900 else None,"query":dict(urllib.parse.parse_qsl(u.query))});return
    if op=="vnc-endpoint":
        if not a:die("HOST[:PORT]");s=a[0]
        host,port=(s.rsplit(":",1) if ":" in s else (s,"5900"));emit({"host":host,"port":int(port)});return
    if op=="vnc-default-port":print(5900);return
    if op=="vnc-port-check":
        if not a:die("HOST [PORT]")
        host=a[0];port=int(a[1]) if len(a)>1 else 5900
        try:
            s=socket.create_connection((host,port),2);banner=s.recv(12);s.close();emit({"open":True,"banner":banner.decode(errors="replace")})
        except Exception as e:emit({"open":False,"error":str(e)})
        return
    if op=="vnc-rfb-version":
        b=bytes.fromhex(a[0]) if a else sys.stdin.buffer.read();emit({"banner":b[:12].decode(errors="replace"),"valid":bool(re.fullmatch(br"RFB \d{3}\.\d{3}\n",b[:12]))});return
    if op=="vnc-rfb-security-types":
        b=bytes.fromhex(a[0]) if a else sys.stdin.buffer.read()
        if not b:emit([]);return
        n=b[0];emit(list(b[1:1+n]));return
    if op=="vnc-rfb-pixel-format":
        b=bytes.fromhex(a[0]) if a else sys.stdin.buffer.read()
        if len(b)<16:die("need 16-byte RFB pixel format")
        bpp,depth,bigend,truecolor,rmax,gmax,bmax,rshift,gshift,bshift=struct.unpack(">BBBBHHHBBBxxx",b[:16]);emit(locals()|{"big_endian":bool(bigend),"true_color":bool(truecolor)});return
    if op=="vnc-rfb-encoding-names":
        ids=[int(x) for x in a] if a else [];emit([RFB_ENCODINGS.get(x,f"encoding-{x}") for x in ids]);return
    if op=="vnc-rfb-encoding-id":
        name=(a[0] if a else "").lower();rev={v:k for k,v in RFB_ENCODINGS.items()};emit(rev.get(name));return
    if op=="vnc-rfb-rect-header":
        b=bytes.fromhex(a[0]) if a else sys.stdin.buffer.read()
        if len(b)<12:die("need 12 bytes")
        x,y,w,h,enc=struct.unpack(">HHHHi",b[:12]);emit({"x":x,"y":y,"width":w,"height":h,"encoding":enc,"encoding_name":RFB_ENCODINGS.get(enc)});return
    if op=="vnc-rfb-key-event":
        if len(a)<2:die("DOWN KEYCODE");down=int(a[0])!=0;key=int(a[1],0);print((bytes([4,1 if down else 0,0,0])+struct.pack(">I",key)).hex());return
    if op=="vnc-rfb-pointer-event":
        if len(a)<3:die("MASK X Y");print((bytes([5,int(a[0],0)&255])+struct.pack(">HH",int(a[1]),int(a[2]))).hex());return
    if op=="vnc-rfb-cuttext-size":
        b=bytes.fromhex(a[0]) if a else sys.stdin.buffer.read()
        if len(b)<8:die("need ServerCutText header");print(struct.unpack(">I",b[4:8])[0]);return
    if op=="vnc-rfb-framebuffer-request":
        if len(a)<4:die("X Y W H [incremental]");x,y,w,h=map(int,a[:4]);inc=int(a[4]) if len(a)>4 else 1;print((bytes([3,inc])+struct.pack(">HHHH",x,y,w,h)).hex());return
    if op=="vnc-password-length-check":emit({"length":len(a[0]) if a else 0,"classic_vnc_uses_first_8":len(a[0])>8 if a else False});return
    if op=="vnc-session-env":emit({k:v for k,v in os.environ.items() if any(x in k.upper() for x in ("VNC","DISPLAY","XAUTH"))});return
    if op=="vnc-display-port":print(5900+int(a[0]));return
    if op=="vnc-port-display":print(int(a[0])-5900);return
    if op=="vnc-localhost-check":
        h=(a[0] if a else "localhost").lower();emit({"localhost":h in ("localhost","127.0.0.1","::1")});return
    if op=="vnc-websocket-url":
        host=a[0] if a else "127.0.0.1";port=int(a[1]) if len(a)>1 else 6080;path=a[2] if len(a)>2 else "websockify";print(f"ws://{host}:{port}/{path.lstrip('/')}");return
    if op=="novnc-url":
        host=a[0] if a else "127.0.0.1";port=int(a[1]) if len(a)>1 else 6080;vnc=a[2] if len(a)>2 else "127.0.0.1:5900"
        q=urllib.parse.urlencode({"host":vnc.rsplit(":",1)[0],"port":vnc.rsplit(":",1)[1]});print(f"http://{host}:{port}/vnc.html?{q}");return
    if op=="novnc-query":emit(dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(a[0]).query)));return
    if op=="novnc-token-path":print(str(P(a[0] if a else ".").resolve()/"tokens"));return
    if op=="novnc-listen-args":emit(["--listen",a[0] if a else "6080"]);return
    if op=="novnc-proxy-args":emit(["--vnc",a[0] if a else "127.0.0.1:5900"]);return
    if op=="novnc-ssl-args":
        emit(["--cert",a[0],"--key",a[1]] if len(a)>=2 else []);return
    if op=="novnc-path-info":
        p=P(a[0] if a else ".");emit({"exists":p.exists(),"vnc_html":(p/"vnc.html").exists(),"core":(p/"core").exists(),"utils":(p/"utils").exists()});return
    if op in ("novnc-config-json","novnc-session-json"):
        emit({"listen":int(a[0]) if a else 6080,"vnc":a[1] if len(a)>1 else "127.0.0.1:5900","ssl":False});return
    if op=="novnc-health":
        emit({"python":shutil.which("python") or shutil.which("python3"),"display":os.environ.get("DISPLAY"),"x11vnc":shutil.which("x11vnc"),"websockify":shutil.which("websockify"),"novnc":shutil.which("novnc_proxy")});return

def reg_stats(s):
    secs=re.findall(r"(?m)^\[([^\]]+)\]\s*$",s);vals=re.findall(r"(?m)^\s*\"?[^\n=]+\"?\s*=",s)
    return secs,vals

def pe_info(path):
    b=P(path).read_bytes()
    if len(b)<0x40 or b[:2]!=b"MZ":die("not PE/MZ")
    off=struct.unpack("<I",b[0x3c:0x40])[0]
    if off+24>len(b) or b[off:off+4]!=b"PE\0\0":die("bad PE header")
    machine,sections,_,_,_,optsize,_=struct.unpack("<HHIIIHH",b[off+4:off+24])
    opt=b[off+24:off+24+optsize];magic=struct.unpack("<H",opt[:2])[0] if len(opt)>=2 else 0
    subsystem=struct.unpack("<H",opt[68:70])[0] if len(opt)>=70 and magic==0x10b else struct.unpack("<H",opt[88:90])[0] if len(opt)>=90 and magic==0x20b else None
    return {"machine":machine,"arch":{0x14c:"x86",0x8664:"x86_64",0xaa64:"arm64"}.get(machine,hex(machine)),"sections":sections,"optional_magic":hex(magic),"subsystem":subsystem}

def wine(cmd,a):
    op=cmd
    prefix=P(os.environ.get("WINEPREFIX",str(P.home()/".wine")))
    if op=="wine-prefix-path":print(str(prefix));return
    if op=="wine-prefix-info":emit({"path":str(prefix),"exists":prefix.exists(),"drive_c":(prefix/"drive_c").exists(),"system_reg":(prefix/"system.reg").exists(),"user_reg":(prefix/"user.reg").exists()});return
    if op=="wine-prefix-size":print(size_path(prefix) if prefix.exists() else 0);return
    if op=="wine-prefix-drives":emit([{"name":x.name,"target":str(x.resolve()) if x.exists() else None} for x in (prefix/"dosdevices").glob("*")] if (prefix/"dosdevices").exists() else []);return
    if op in ("wine-prefix-system-reg","wine-prefix-user-reg","wine-prefix-userdef-reg"):
        f={"wine-prefix-system-reg":"system.reg","wine-prefix-user-reg":"user.reg","wine-prefix-userdef-reg":"userdef.reg"}[op];print((prefix/f).read_text(errors="replace") if (prefix/f).exists() else "",end="");return
    if op.startswith("wine-reg-"):
        s=readtext(a)
        secs,vals=reg_stats(s)
        if op=="wine-reg-sections":emit(secs)
        elif op=="wine-reg-key-count":print(len(secs))
        elif op=="wine-reg-value-count":print(len(vals))
        elif op=="wine-reg-search":
            q=a[1].lower() if len(a)>1 and P(a[0]).exists() else (a[0].lower() if a else "");emit([x for x in s.splitlines() if q in x.lower()])
        return
    if op=="wine-drive-map":emit({"c:":str(prefix/"drive_c"),"z:":"/"});return
    if op=="wine-path-to-win":
        p=str(P(a[0]).resolve());print("Z:"+p.replace("/","\\"));return
    if op=="wine-path-to-unix":
        s=a[0];print(("/"+s[3:].replace("\\","/")) if re.match(r"(?i)^z:\\\\",s) else s);return
    if op.startswith("wine-pe-"):
        info=pe_info(a[0])
        if op=="wine-pe-arch":print(info["arch"])
        elif op=="wine-pe-subsystem":emit(info["subsystem"])
        elif op=="wine-pe-sections":emit(info["sections"])
        elif op in ("wine-pe-import-hints","wine-pe-export-hints"):
            b=P(a[0]).read_bytes();strings=sorted(set(x.decode(errors="ignore") for x in re.findall(rb"[A-Za-z0-9_.-]{4,}",b)))
            if op.endswith("import-hints"):emit([x for x in strings if x.lower().endswith(".dll")])
            else:emit([x for x in strings if not x.lower().endswith(".dll")][:200])
        return
    if op=="wine-dll-search":
        q=(a[0] if a else "").lower();roots=[prefix/"drive_c/windows/system32",prefix/"drive_c/windows/syswow64"];emit([str(x) for r in roots if r.exists() for x in r.glob("*") if q in x.name.lower()]);return
    if op=="wine-env":emit({k:v for k,v in os.environ.items() if k.startswith("WINE")});return
    if op=="wine-wow64-hints":
        emit({"prefix":str(prefix),"syswow64":(prefix/"drive_c/windows/syswow64").exists(),"system32":(prefix/"drive_c/windows/system32").exists(),"box64":bool(shutil.which("box64"))});return
    if op=="wine-prefix-backup-list":
        root=P(a[0] if a else prefix.parent);emit([str(x) for x in root.glob("*.wine*") if x.exists()]);return
    if op=="wine-log-summary":
        s=readtext(a);emit(Counter(re.findall(r"\b(fixme|err|warn|trace):",s,re.I)));return
    if op=="wine-launch-plan":
        exe=a[0] if a else "app.exe";emit({"command":["wine",exe,*a[1:]],"wineprefix":str(prefix),"box64_present":bool(shutil.which("box64"))});return

def elf_machine(path):
    b=P(path).read_bytes()
    if len(b)<20 or b[:4]!=b"\x7fELF":die("not ELF")
    le=b[5]==1;machine=int.from_bytes(b[18:20],"little" if le else "big")
    return machine,{62:"x86_64",183:"aarch64",3:"x86",40:"arm"}.get(machine,str(machine))
def parse_boxrc(path):
    c=configparser.ConfigParser(interpolation=None,strict=False);c.optionxform=str;c.read(path);return c
def box(cmd,a):
    op=cmd
    if op=="box64-rc-parse":
        c=parse_boxrc(a[0]);emit({s:dict(c[s]) for s in c.sections()});return
    if op=="box64-rc-get":
        c=parse_boxrc(a[0]);emit(c.get(a[1],a[2],fallback=None));return
    if op=="box64-rc-sections":
        c=parse_boxrc(a[0]);emit(c.sections());return
    if op=="box64-env-list":emit({k:v for k,v in os.environ.items() if k.startswith("BOX64_")});return
    if op=="box64-env-merge":
        d=json.loads(P(a[0]).read_text() if P(a[0]).exists() else a[0]);e={k:v for k,v in os.environ.items() if k.startswith("BOX64_")};e.update(d);emit(e);return
    if op in ("box64-elf-arch","box64-x64-check","box64-arm64-check"):
        m,n=elf_machine(a[0])
        if op=="box64-elf-arch":print(n)
        else:print(str(n==("x86_64" if "x64" in op else "aarch64")).lower())
        return
    if op=="box64-elf-needed-hints":
        b=P(a[0]).read_bytes();emit(sorted(set(x.decode() for x in re.findall(rb"lib[A-Za-z0-9_.+-]+\.so(?:\.\d+)*",b))));return
    if op=="box64-library-map":
        roots=[P(x) for x in os.environ.get("LD_LIBRARY_PATH","").split(":") if x];emit({r.name:[str(p) for root in roots if root.exists() for p in root.glob(r.name)] for r in [P(x) for x in a]});return
    if op=="box64-cache-path":print(str(P.home()/".cache/box64"));return
    if op=="box64-cache-size":
        p=P.home()/".cache/box64";print(size_path(p) if p.exists() else 0);return
    if op in ("box64-log-warnings","box64-log-missing-libs"):
        s=readtext(a);pat=r"(?i)^.*(?:warning|warn).*$" if op.endswith("warnings") else r"(?i)^.*(?:missing|cannot open shared object|not found).*$";emit(re.findall(pat,s,re.M));return
    if op=="box64-wine-command":emit(["box64","wine64",*(a or ["app.exe"])]);return
    if op=="box64-run-plan":emit({"box64":shutil.which("box64"),"target":a[0] if a else None,"arch":elf_machine(a[0])[1] if a and P(a[0]).exists() else None});return
    if op=="box64-dynarec-flags":emit({k:v for k,v in os.environ.items() if k.startswith("BOX64_DYNAREC")});return
    if op=="box64-page-size-check":emit({"page_size":os.sysconf("SC_PAGE_SIZE"),"16k":os.sysconf("SC_PAGE_SIZE")==16384});return
    if op=="box64-host-info":emit({"machine":os.uname().machine,"system":os.uname().sysname,"box64":shutil.which("box64")});return
    if op=="box64-compat-summary":
        target=a[0] if a else None;arch=elf_machine(target)[1] if target and P(target).exists() else None;emit({"host":os.uname().machine,"target":arch,"box64":bool(shutil.which("box64")),"wine":bool(shutil.which("wine") or shutil.which("wine64"))});return

def display_parts(s):
    m=re.fullmatch(r"(?:(?P<host>[^:]*):)?(?P<display>\d+)(?:\.(?P<screen>\d+))?",s)
    if not m:die("invalid DISPLAY")
    d=m.groupdict();d["display"]=int(d["display"]);d["screen"]=int(d["screen"] or 0);return d
def libfind(name):
    roots=[P("/data/data/studio.ocean.app/files/usr/lib"),P("/data/data/studio.ocean.app/files/glibc/lib"),P("/system/lib64")]
    return [str(p) for r in roots if r.exists() for p in r.glob(name+"*")]
def x11(cmd,a):
    op=cmd
    if op=="x11-display-parse":emit(display_parts(a[0] if a else os.environ.get("DISPLAY",":0")));return
    if op=="x11-display-env":print(os.environ.get("DISPLAY",""));return
    if op=="x11-socket-path":
        d=display_parts(a[0] if a else os.environ.get("DISPLAY",":0"));print(f"/tmp/.X11-unix/X{d['display']}");return
    if op=="x11-auth-path":print(os.environ.get("XAUTHORITY",str(P.home()/".Xauthority")));return
    if op=="x11-xauthority-list":
        p=P(os.environ.get("XAUTHORITY",str(P.home()/".Xauthority")));emit({"path":str(p),"exists":p.exists(),"bytes":p.stat().st_size if p.exists() else 0});return
    if op=="x11-font-paths":emit([x for x in os.environ.get("XDG_DATA_DIRS","").split(":") if x]);return
    if op=="x11-color-parse":
        s=a[0].lstrip("#");emit({"r":int(s[0:2],16),"g":int(s[2:4],16),"b":int(s[4:6],16)});return
    if op=="x11-geometry-parse":
        m=re.fullmatch(r"(\d+)x(\d+)([+-]\d+)?([+-]\d+)?",a[0]);emit({"width":int(m.group(1)),"height":int(m.group(2)),"x":int(m.group(3) or 0),"y":int(m.group(4) or 0)} if m else {});return
    if op=="x11-screen-size":
        w,h=map(int,a[:2]);emit({"width":w,"height":h,"pixels":w*h});return
    if op=="x11-dpi":
        px,mm=map(float,a[:2]);print(px/(mm/25.4));return
    if op=="x11-xrandr-parse":
        s=readtext(a);emit(re.findall(r"(?m)^([A-Za-z0-9_-]+)\s+connected(?: primary)?\s+(\d+x\d+)",s));return
    if op=="x11-xinput-parse":
        s=readtext(a);emit(re.findall(r"(?m)^[^↳]*↳\s*(.*?)\s+id=(\d+)",s));return
    if op=="x11-xkb-layout":print(os.environ.get("XKB_DEFAULT_LAYOUT","us"));return
    if op=="x11-lib-scan":
        emit({x:libfind(x) for x in ["libX11.so","libxcb.so","libXext.so","libXrender.so","libXft.so","libXss.so"]});return
    checks={"x11-libx11-check":"libX11.so","x11-libxcb-check":"libxcb.so","x11-libxext-check":"libXext.so","x11-libxrender-check":"libXrender.so","x11-libxft-check":"libXft.so","x11-libxss-check":"libXss.so"}
    if op in checks:emit({"library":checks[op],"paths":libfind(checks[op]),"present":bool(libfind(checks[op]))});return
    if op=="x11-opengl-env":emit({k:v for k,v in os.environ.items() if k.startswith(("LIBGL","MESA","EGL","GALLIUM"))});return
    if op=="x11-mesa-env":emit({"LIBGL_ALWAYS_SOFTWARE":os.environ.get("LIBGL_ALWAYS_SOFTWARE"),"MESA_LOADER_DRIVER_OVERRIDE":os.environ.get("MESA_LOADER_DRIVER_OVERRIDE")});return
    if op=="x11-software-render-env":emit({"LIBGL_ALWAYS_SOFTWARE":"1","GALLIUM_DRIVER":"llvmpipe"});return
    if op=="x11-vnc-plan":emit({"display":os.environ.get("DISPLAY",":1"),"command":["x11vnc","-display",os.environ.get("DISPLAY",":1),"-rfbport",a[0] if a else "5901","-localhost","-forever","-shared"]});return
    if op=="x11-stack-summary":emit({"display":os.environ.get("DISPLAY"),"libs":{x:bool(libfind(x)) for x in ["libX11.so","libxcb.so","libXext.so","libXrender.so","libXft.so","libXss.so"]},"x11vnc":shutil.which("x11vnc"),"Xvfb":shutil.which("Xvfb")});return

def main():
    cmd=P(sys.argv[0]).name;a=sys.argv[1:]
    if cmd not in COMMANDS:
        if a and a[0] in COMMANDS:cmd=a.pop(0)
        elif not a or a[0] in ("-h","--help"):
            print("Shard 31 — VNC/noVNC Wine/Box64 compatibility and X11/libX utilities");print("\n".join(COMMANDS));return
        else:die("unknown command")
    if a and a[0] in ("-h","--help"):print(cmd+" — functional shard 31 utility");return
    if cmd in VNC:vnc(cmd,a)
    elif cmd in WINE:wine(cmd,a)
    elif cmd in BOX:box(cmd,a)
    else:x11(cmd,a)
if __name__=="__main__":main()
