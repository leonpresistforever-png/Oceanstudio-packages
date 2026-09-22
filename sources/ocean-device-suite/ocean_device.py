#!/usr/bin/env python3
from __future__ import annotations
import base64, datetime as dt, hashlib, json, mimetypes, os, pathlib, random, shutil, socket, subprocess, sys, tempfile, time, urllib.parse, urllib.request, uuid, re, struct
P=pathlib.Path
PREFIX=P(os.environ.get("PREFIX","/data/data/studio.ocean.app/files/usr"))
IPC=os.environ.get("OCEAN_IPC","http://127.0.0.1:8088")

DEVICE=[
"ocean-click","ocean-coordinate","ocean-object","ocean-inspect","ocean-screen-tree","ocean-screen-text","ocean-screen-find","ocean-screen-ref","ocean-tap","ocean-long-press","ocean-swipe","ocean-scroll","ocean-type","ocean-back","ocean-home","ocean-recents","ocean-notifications","ocean-quick-settings","ocean-apps","ocean-app-find","ocean-app-open","ocean-device-status","ocean-screen-size","ocean-screen-package","ocean-focus","ocean-click-text","ocean-click-ref","ocean-type-ref","ocean-scroll-ref","ocean-tap-center","ocean-swipe-up","ocean-swipe-down","ocean-swipe-left","ocean-swipe-right","ocean-wait-ui"]
CAPTURE=[
"ocean-screenshot","ocean-screenshot-jpg","ocean-screenshot-png","ocean-screenshot-base64","ocean-screenshot-info","ocean-take-selfie","ocean-take-photo","ocean-camera-front","ocean-camera-back","ocean-record","ocean-record-start","ocean-record-stop","ocean-record-status","ocean-open-photo","ocean-open-video","ocean-open-audio","ocean-share-photo","ocean-share-video","ocean-share-audio","ocean-media-info","ocean-image-dim","ocean-image-format","ocean-image-convert","ocean-image-thumbnail","ocean-image-base64"]
INTENT=[
"ocean-open","ocean-open-url","ocean-open-file","ocean-open-app","ocean-open-settings","ocean-open-browser","ocean-open-map","ocean-open-mail","ocean-open-market","ocean-intent-pass","ocean-intent-view","ocean-intent-send","ocean-intent-dial","ocean-intent-settings","ocean-intent-package","ocean-share","ocean-share-text","ocean-share-file","ocean-copy","ocean-paste","ocean-clipboard-get","ocean-clipboard-set","ocean-toast","ocean-notify","ocean-vibrate","ocean-api","ocean-api-get","ocean-api-post","ocean-app-info","ocean-device-info"]
X11=[
"ocean-render","ocean-x11","ocean-x11-open","ocean-x11-attach","ocean-x11-start","ocean-x11-stop","ocean-x11-status","ocean-x11-display","ocean-x11-env","ocean-x11-run","ocean-x11-shell","ocean-x11-app","ocean-x11-resize","ocean-x11-fit","ocean-x11-fullscreen","ocean-x11-keyboard","ocean-x11-mouse","ocean-x11-touch","ocean-x11-clipboard","ocean-x11-screenshot","ocean-x11-record","ocean-render-open","ocean-render-image","ocean-render-video","ocean-render-html","ocean-render-pdf","ocean-render-port","ocean-render-status","ocean-render-session","ocean-x11-runtime"]
D3=[
"ocean-3d","ocean-3d-open","ocean-3d-obj","ocean-3d-model","ocean-3d-grid","ocean-3d-wireframe","ocean-3d-solid","ocean-3d-rotate","ocean-3d-zoom","ocean-3d-pan","ocean-3d-reset","ocean-3d-camera","ocean-3d-light","ocean-3d-background","ocean-3d-screenshot","ocean-3d-info","ocean-obj-info","ocean-obj-bounds","ocean-obj-normalize","ocean-obj-center"]
FILES=[
"ocean-file-info","ocean-file-mime","ocean-file-hash","ocean-file-head","ocean-file-tail","ocean-file-lines","ocean-file-bytes","ocean-file-copy","ocean-file-move","ocean-file-remove","ocean-file-find","ocean-file-list","ocean-file-tree","ocean-file-preview","ocean-file-share","ocean-file-open","ocean-path","ocean-path-real","ocean-path-size","ocean-path-space"]
SYSTEM=[
"ocean-battery","ocean-os","ocean-arch","ocean-memory","ocean-cpu","ocean-storage","ocean-network","ocean-ip","ocean-ports","ocean-processes","ocean-process","ocean-env","ocean-prefix","ocean-which","ocean-command","ocean-runtime","ocean-version","ocean-health","ocean-permissions","ocean-features"]
UTIL=[
"ocean-wait","ocean-retry","ocean-sequence","ocean-parallel","ocean-json","ocean-json-get","ocean-json-set","ocean-base64","ocean-urlencode","ocean-urldecode","ocean-timestamp","ocean-uuid","ocean-random","ocean-hash","ocean-http","ocean-download","ocean-upload","ocean-watch-file","ocean-watch-port","ocean-wait-app"]
COMMANDS=DEVICE+CAPTURE+INTENT+X11+D3+FILES+SYSTEM+UTIL
assert len(COMMANDS)==200 and len(set(COMMANDS))==200

def emit(x):
    if isinstance(x,(dict,list,tuple)): print(json.dumps(x,indent=2,ensure_ascii=False,default=str))
    else: print(x)

def die(msg,code=2): print(msg,file=sys.stderr); raise SystemExit(code)

def api(method,path,payload=None,timeout=15):
    body=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request(IPC+path,data=body,method=method,headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            raw=r.read()
    except Exception as e:
        die("Ocean app API unavailable: "+str(e)+". Open OceanStudio so its local runtime service can answer.")
    try:return json.loads(raw)
    except:return {"raw":raw.decode(errors="replace")}

def post(path,payload): return api("POST",path,payload)
def get(path): return api("GET",path)

def device(tool,args=None): return post("/api/device",{"tool":tool,"args":args or {}})
def inspect(): return device("inspect_android_screen",{})
def nodes():
    r=inspect()
    if r.get("exit_code",-1)!=0:die(r.get("error","screen inspection failed"))
    return r.get("nodes",[])

def find_nodes(query):
    q=query.lower()
    return [n for n in nodes() if q in str(n.get("text","")).lower() or q in str(n.get("description","")).lower() or q in str(n.get("view_id","")).lower()]

def interact(action,**kw): return device("interact_android_screen",dict(action=action,**kw))

def save_screenshot(path,fmt=None):
    r=post("/api/capture",{"action":"screenshot"})
    if not r.get("image_base64"): die(r.get("error","capture failed"))
    data=base64.b64decode(r["image_base64"])
    path=P(path)
    if fmt=="png" or path.suffix.lower()==".png":
        magick=shutil.which("magick") or shutil.which("convert")
        if not magick: die("PNG conversion needs imagemagick; install imagemagick")
        with tempfile.NamedTemporaryFile(suffix=".jpg",delete=False) as t:t.write(data);tmp=t.name
        subprocess.run([magick,tmp,str(path)],check=True);P(tmp).unlink(missing_ok=True)
    else:path.write_bytes(data)
    return {"path":str(path),"bytes":path.stat().st_size,"width":r.get("image_width"),"height":r.get("image_height")}

def image_info(path):
    b=P(path).read_bytes()
    if b[:8]==b"\x89PNG\r\n\x1a\n" and len(b)>=24:return {"format":"png","width":int.from_bytes(b[16:20],"big"),"height":int.from_bytes(b[20:24],"big")}
    if b[:6] in (b"GIF87a",b"GIF89a"):return {"format":"gif","width":int.from_bytes(b[6:8],"little"),"height":int.from_bytes(b[8:10],"little")}
    if b[:2]==b"BM" and len(b)>=26:return {"format":"bmp","width":int.from_bytes(b[18:22],"little",signed=True),"height":abs(int.from_bytes(b[22:26],"little",signed=True))}
    if b[:2]==b"\xff\xd8":
        p=2
        while p+9<len(b):
            if b[p]!=0xff:p+=1;continue
            m=b[p+1];p+=2
            if m in (0xd8,0xd9) or 0xd0<=m<=0xd7:continue
            if p+2>len(b):break
            n=int.from_bytes(b[p:p+2],"big")
            if m in range(0xc0,0xc4) and p+7<len(b):return {"format":"jpeg","height":int.from_bytes(b[p+3:p+5],"big"),"width":int.from_bytes(b[p+5:p+7],"big")}
            p+=n
    return {"format":mimetypes.guess_type(str(path))[0] or "unknown","bytes":len(b)}

def obj_info(path,transform=None,out_path=None):
    verts=[];other=[]
    for line in P(path).read_text(errors="replace").splitlines():
        if line.startswith("v "):
            p=line.split();verts.append([float(p[1]),float(p[2]),float(p[3])])
        else:other.append(line)
    if not verts:return {"vertices":0}
    mins=[min(v[i] for v in verts) for i in range(3)];maxs=[max(v[i] for v in verts) for i in range(3)]
    center=[(mins[i]+maxs[i])/2 for i in range(3)]
    size=max(maxs[i]-mins[i] for i in range(3)) or 1
    if transform:
        new=[]
        for v in verts:
            if transform=="center":w=[v[i]-center[i] for i in range(3)]
            else:w=[(v[i]-center[i])*2/size for i in range(3)]
            new.append(w)
        target=P(out_path or (str(path)+".normalized.obj"))
        vi=0;lines=[]
        for line in P(path).read_text(errors="replace").splitlines():
            if line.startswith("v "):
                w=new[vi];vi+=1;lines.append("v %.8g %.8g %.8g"%tuple(w))
            else:lines.append(line)
        target.write_text("\n".join(lines)+"\n")
        return {"path":str(target),"vertices":len(verts)}
    return {"vertices":len(verts),"min":mins,"max":maxs,"center":center,"extent":[maxs[i]-mins[i] for i in range(3)]}

def x11_root():
    return P(os.environ.get("OCEAN_X11_ROOT",str(PREFIX/"var/lib/ocean-x11/rootfs")))
def x11_bin(name):
    p=shutil.which(name)
    if p:return p
    root=x11_root()
    for q in [root/"usr/bin"/name,root/"bin"/name]:
        if q.exists():return str(q)
    return None
def x11_config(args=None):
    cfg={"display":":1","geometry":"1280x720","dpi":120,"rfb_port":5901}
    path=PREFIX/"etc/ocean-x11.conf"
    if path.exists():
        try:
            for raw in path.read_text(errors="replace").splitlines():
                if "=" not in raw or raw.lstrip().startswith("#"):continue
                k,v=raw.split("=",1);k=k.strip().upper();v=v.strip()
                if k=="DISPLAY" and re.fullmatch(r":\d+",v):cfg["display"]=v
                elif k=="GEOMETRY" and re.fullmatch(r"\d{3,5}x\d{3,5}",v):cfg["geometry"]=v
                elif k=="DPI":
                    try:cfg["dpi"]=max(72,min(240,int(v)))
                    except:pass
                elif k=="RFB_PORT":
                    try:cfg["rfb_port"]=max(1024,min(65535,int(v)))
                    except:pass
        except Exception:pass
    env_display=os.environ.get("DISPLAY")
    if env_display and re.fullmatch(r":\d+",env_display):cfg["display"]=env_display
    a=list(args or [])
    i=0
    while i<len(a):
        x=a[i]
        if re.fullmatch(r":\d+",x):
            cfg["display"]=x;i+=1;continue
        if x in ("--geometry","--resolution") and i+1<len(a):
            v=a[i+1]
            if not re.fullmatch(r"\d{3,5}x\d{3,5}",v):die("invalid X11 geometry: "+v)
            cfg["geometry"]=v;i+=2;continue
        if x=="--dpi" and i+1<len(a):
            cfg["dpi"]=max(72,min(240,int(a[i+1])));i+=2;continue
        if x=="--rfb-port" and i+1<len(a):
            cfg["rfb_port"]=max(1024,min(65535,int(a[i+1])));i+=2;continue
        die("unknown ocean-x11-start option: "+x)
    # Keep the normal VNC mapping unless a custom port was explicitly configured.
    if cfg["rfb_port"]==5901:
        try:cfg["rfb_port"]=5900+int(cfg["display"][1:])
        except:pass
    return cfg

def x11_runtime_status(args=None):
    need=["Xvfb","x11vnc","openbox","xterm"]
    cfg=x11_config(args)
    return {"rootfs":str(x11_root()),"rootfs_present":x11_root().exists(),"commands":{n:x11_bin(n) for n in need},"proot":shutil.which("proot"),**cfg,"config_file":str(PREFIX/"etc/ocean-x11.conf")}

def x11_start(args=None):
    status=x11_runtime_status(args)
    missing=[k for k,v in status["commands"].items() if not v]
    if missing: die("X11 backend missing: "+", ".join(missing)+". Run ocean-x11-runtime --bootstrap or install the Ocean X11 runtime package.")
    run=P(PREFIX/"var/run/ocean-x11");run.mkdir(parents=True,exist_ok=True)
    log=open(run/"session.log","ab",buffering=0)
    display=status["display"];geometry=status["geometry"];dpi=str(status["dpi"]);rfb=str(status["rfb_port"])
    env=os.environ.copy();env["DISPLAY"]=display
    root=x11_root()
    xargs=[display,"-screen","0",geometry+"x24","-dpi",dpi,"-nolisten","tcp"]
    vargs=["-display",display,"-rfbport",rfb,"-localhost","-nopw","-forever","-shared"]
    if root.exists() and shutil.which("proot"):
        base=[shutil.which("proot"),"-0","-r",str(root),"-b","/dev","-b","/proc","-b","/sys","-b",f"{PREFIX}:{PREFIX}","-w","/root"]
        def launch(args2):return subprocess.Popen(base+args2,env=env,stdout=log,stderr=log,start_new_session=True)
        xv=launch(["/usr/bin/Xvfb",*xargs])
        time.sleep(.7);wm=launch(["/usr/bin/openbox"]);vnc=launch(["/usr/bin/x11vnc",*vargs])
    else:
        xv=subprocess.Popen([status["commands"]["Xvfb"],*xargs],env=env,stdout=log,stderr=log,start_new_session=True)
        time.sleep(.7);wm=subprocess.Popen([status["commands"]["openbox"]],env=env,stdout=log,stderr=log,start_new_session=True);vnc=subprocess.Popen([status["commands"]["x11vnc"],*vargs],env=env,stdout=log,stderr=log,start_new_session=True)
    (run/"pids.json").write_text(json.dumps({"xvfb":xv.pid,"wm":wm.pid,"vnc":vnc.pid,"display":display,"rfb_port":status["rfb_port"],"geometry":geometry,"dpi":status["dpi"]}))
    return {"started":True,"display":display,"geometry":geometry,"dpi":status["dpi"],"rfb_port":status["rfb_port"],"pids":{"xvfb":xv.pid,"wm":wm.pid,"vnc":vnc.pid}}
def x11_stop():
    p=P(PREFIX/"var/run/ocean-x11/pids.json")
    if p.exists():
        for pid in json.loads(p.read_text()).values():
            try:os.kill(int(pid),15)
            except:pass
        p.unlink(missing_ok=True)
    return {"stopped":True}

def x11_bootstrap():
    pd=shutil.which("proot-distro")
    if not pd:die("proot-distro is required for automatic X11 bootstrap")
    # Explicit user command only. Debian packages come from Debian's signed repositories.
    subprocess.run([pd,"install","debian"],check=False)
    subprocess.run([pd,"login","debian","--","sh","-lc","apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y xvfb x11vnc openbox xterm dbus-x11 mesa-utils"],check=True)
    return {"bootstrapped":True,"backend":"Debian official packages via proot-distro","note":"No Termux X11 application is used"}

def handle_device(cmd,a):
    if cmd in ("ocean-device-status",):emit(device("device_status",{}));return
    if cmd in ("ocean-apps","ocean-app-find"):
        emit(device("list_android_apps",{"query":" ".join(a)}));return
    if cmd=="ocean-app-open":
        if not a:die("package name required")
        emit(device("open_android_app",{"package_name":a[0]}));return
    if cmd in ("ocean-inspect","ocean-screen-tree","ocean-object"):emit(inspect());return
    if cmd=="ocean-screen-text":emit([n.get("text") for n in nodes() if n.get("text") not in (None,"","None")]);return
    if cmd in ("ocean-screen-find","ocean-click-text"):
        if not a:die("text required")
        hits=find_nodes(" ".join(a))
        if cmd=="ocean-click-text":
            hit=next((n for n in hits if n.get("clickable")),hits[0] if hits else None)
            if not hit:die("no matching visible object")
            emit(interact("click",ref=hit["ref"]))
        else:emit(hits)
        return
    if cmd=="ocean-screen-ref":
        if not a:die("ref required")
        emit(next((n for n in nodes() if n.get("ref")==a[0]),{}));return
    if cmd in ("ocean-click","ocean-click-ref"):
        if not a:die("ref required")
        emit(interact("click",ref=a[0]));return
    if cmd in ("ocean-type","ocean-type-ref"):
        if len(a)<2:die("REF TEXT")
        emit(interact("type",ref=a[0],text=" ".join(a[1:])));return
    if cmd in ("ocean-scroll","ocean-scroll-ref"):
        if not a:die("ref required")
        emit(interact("scroll",ref=a[0]));return
    if cmd in ("ocean-tap","ocean-coordinate"):
        if len(a)<2:die("X Y")
        emit(interact("tap",x=int(a[0]),y=int(a[1])));return
    if cmd=="ocean-long-press":
        emit(interact("long_press",x=int(a[0]),y=int(a[1])));return
    if cmd=="ocean-swipe":
        if len(a)<4:die("X Y TO_X TO_Y")
        emit(interact("swipe",x=int(a[0]),y=int(a[1]),to_x=int(a[2]),to_y=int(a[3])));return
    if cmd in ("ocean-back","ocean-home","ocean-recents","ocean-notifications","ocean-quick-settings"):
        action=cmd.removeprefix("ocean-").replace("-","_");emit(interact(action));return
    if cmd=="ocean-screen-size":
        r=post("/api/capture",{"action":"screenshot"});emit({"width":r.get("image_width"),"height":r.get("image_height"),"error":r.get("error")});return
    if cmd=="ocean-screen-package":
        ns=nodes();emit({"package_hint":ns[0].get("view_id","").split(":")[0] if ns and ns[0].get("view_id") else None});return
    if cmd=="ocean-focus":
        ns=nodes();emit([n for n in ns if n.get("editable")][:20]);return
    if cmd=="ocean-tap-center":
        if not a:die("REF")
        n=next((x for x in nodes() if x.get("ref")==a[0]),None)
        if not n:die("ref not found")
        b=n["bounds"];emit(interact("tap",x=(b[0]+b[2])//2,y=(b[1]+b[3])//2));return
    if cmd.startswith("ocean-swipe-"):
        r=post("/api/capture",{"action":"screenshot"});w,h=r.get("image_width",1080),r.get("image_height",1920);x,y=w//2,h//2
        d=cmd.rsplit("-",1)[1];tx,ty=x,y
        if d=="up":ty=h//4
        elif d=="down":ty=3*h//4
        elif d=="left":tx=w//4
        else:tx=3*w//4
        emit(interact("swipe",x=x,y=y,to_x=tx,to_y=ty));return
    if cmd=="ocean-wait-ui":
        q=" ".join(a[:-1]) if len(a)>1 else (a[0] if a else "");timeout=float(a[-1]) if len(a)>1 else 10;end=time.time()+timeout
        while time.time()<end:
            hits=find_nodes(q)
            if hits:emit(hits);return
            time.sleep(.5)
        die("timed out waiting for visible UI")
    die("unhandled device command")

def handle_capture(cmd,a):
    if cmd.startswith("ocean-screenshot"):
        if cmd=="ocean-screenshot-base64":emit(post("/api/capture",{"action":"screenshot"}));return
        r=post("/api/capture",{"action":"screenshot"})
        if cmd=="ocean-screenshot-info":emit({k:r.get(k) for k in ("image_width","image_height","media_type","error")});return
        path=a[0] if a else ("screenshot.png" if cmd=="ocean-screenshot-png" else "screenshot.jpg")
        emit(save_screenshot(path,"png" if cmd=="ocean-screenshot-png" else None));return
    if cmd in ("ocean-take-selfie","ocean-camera-front"):emit(post("/api/capture",{"action":"selfie"}));return
    if cmd in ("ocean-take-photo","ocean-camera-back"):emit(post("/api/capture",{"action":"photo"}));return
    if cmd in ("ocean-record","ocean-record-start"):emit(post("/api/capture",{"action":"record_start"}));return
    if cmd=="ocean-record-stop":emit(post("/api/capture",{"action":"record_stop"}));return
    if cmd=="ocean-record-status":emit(post("/api/capture",{"action":"status"}));return
    if cmd.startswith("ocean-open-"):
        if not a:die("file required")
        emit(post("/api/open",{"target":a[0]}));return
    if cmd.startswith("ocean-share-"):
        if not a:die("file required")
        emit(post("/api/share-file",{"path":a[0]}));return
    if cmd=="ocean-media-info":
        if not a:die("file required")
        ff=shutil.which("ffprobe")
        if not ff:die("ffprobe missing; install ffmpeg")
        p=subprocess.run([ff,"-v","error","-show_format","-show_streams","-of","json",a[0]],text=True,capture_output=True);print(p.stdout or p.stderr);return
    if cmd in ("ocean-image-dim","ocean-image-format"):
        if not a:die("image required")
        emit(image_info(a[0]));return
    if cmd=="ocean-image-base64":
        if not a:die("image required")
        print(base64.b64encode(P(a[0]).read_bytes()).decode());return
    if cmd in ("ocean-image-convert","ocean-image-thumbnail"):
        if len(a)<2:die("INPUT OUTPUT [SIZE]")
        magick=shutil.which("magick") or shutil.which("convert")
        if not magick:die("imagemagick missing")
        args=[magick,a[0]]
        if cmd=="ocean-image-thumbnail":args+=["-thumbnail",a[2] if len(a)>2 else "512x512>"]
        args+=[a[1]];subprocess.run(args,check=True);emit({"output":a[1]});return
    die("unhandled capture command")

def handle_intent(cmd,a):
    if cmd in ("ocean-open","ocean-open-file","ocean-open-url","ocean-open-browser"):
        if not a:die("target required")
        emit(post("/api/open",{"target":a[0]}));return
    if cmd in ("ocean-open-app","ocean-intent-package"):
        if not a:die("package required")
        emit(post("/api/open",{"target":"app:"+a[0]}));return
    if cmd=="ocean-open-settings":emit(post("/api/intent",{"action":"android.settings.SETTINGS"}));return
    if cmd=="ocean-open-map":emit(post("/api/open",{"target":"geo:"+(" ".join(a) if a else "0,0")}));return
    if cmd=="ocean-open-mail":emit(post("/api/open",{"target":"mailto:"+(a[0] if a else "")}));return
    if cmd=="ocean-open-market":emit(post("/api/open",{"target":"market://details?id="+a[0]}));return
    if cmd in ("ocean-intent-pass","ocean-intent-view","ocean-intent-send","ocean-intent-dial","ocean-intent-settings"):
        payload={}
        if cmd=="ocean-intent-pass":
            if not a:die("JSON payload required")
            payload=json.loads(P(a[0]).read_text() if P(a[0]).exists() else a[0])
        elif cmd=="ocean-intent-view":payload={"action":"android.intent.action.VIEW","uri":a[0]}
        elif cmd=="ocean-intent-send":payload={"action":"android.intent.action.SEND","type":"text/plain","extras":{"android.intent.extra.TEXT":" ".join(a)},"chooser":True}
        elif cmd=="ocean-intent-dial":payload={"action":"android.intent.action.DIAL","uri":"tel:"+a[0]}
        else:payload={"action":a[0] if a else "android.settings.SETTINGS"}
        emit(post("/api/intent",payload));return
    if cmd in ("ocean-share","ocean-share-text"):
        emit(post("/api/share",{"text":" ".join(a)}));return
    if cmd=="ocean-share-file":
        emit(post("/api/share-file",{"path":a[0]}));return
    if cmd in ("ocean-copy","ocean-clipboard-set"):emit(post("/api/clipboard",{"text":" ".join(a)}));return
    if cmd in ("ocean-paste","ocean-clipboard-get"):emit(get("/api/clipboard"));return
    if cmd=="ocean-toast":emit(post("/api/toast",{"message":" ".join(a)}));return
    if cmd=="ocean-notify":
        emit(post("/api/notification",{"title":a[0] if a else "OceanStudio","message":" ".join(a[1:]) if len(a)>1 else ""}));return
    if cmd=="ocean-vibrate":emit(post("/api/vibrate",{"duration_ms":int(a[0]) if a else 300}));return
    if cmd in ("ocean-device-info","ocean-app-info"):emit(get("/api/info"));return
    if cmd=="ocean-api":
        if not a:emit(get("/api/info"));return
        method=a[0].upper();path=a[1] if len(a)>1 else "/api/info";payload=json.loads(a[2]) if len(a)>2 else None;emit(api(method,path,payload));return
    if cmd=="ocean-api-get":emit(get(a[0]));return
    if cmd=="ocean-api-post":emit(post(a[0],json.loads(a[1]) if len(a)>1 else {}));return
    die("unhandled intent command")

def handle_x11(cmd,a):
    if cmd=="ocean-x11-runtime":
        if a and a[0]=="--bootstrap":emit(x11_bootstrap())
        else:emit(x11_runtime_status())
        return
    if cmd in ("ocean-x11-start","ocean-render-session"):emit(x11_start(a));return
    if cmd=="ocean-x11-stop":emit(x11_stop());return
    if cmd in ("ocean-x11-status","ocean-render-status"):emit(post("/api/x11",{"action":"status"}));return
    if cmd in ("ocean-x11","ocean-x11-open","ocean-x11-attach","ocean-render","ocean-render-open"):
        emit(post("/api/x11",{"action":"open","port":int(a[0]) if a else 5901}));return
    if cmd=="ocean-x11-display":print(x11_config().get("display",":1"));return
    if cmd=="ocean-x11-env":\n        c=x11_config();emit({"DISPLAY":c["display"],"RFB_PORT":c["rfb_port"],"GEOMETRY":c["geometry"],"DPI":c["dpi"],"PREFIX":str(PREFIX)});return
    if cmd in ("ocean-x11-fit","ocean-x11-keyboard"):
        emit(post("/api/x11",{"action":"fit" if cmd.endswith("fit") else "keyboard"}));return
    if cmd in ("ocean-x11-resize","ocean-x11-fullscreen","ocean-x11-mouse","ocean-x11-touch","ocean-x11-clipboard"):
        emit({"supported":True,"command":cmd,"note":"renderer input is handled directly by the native X11 screen"});return
    if cmd in ("ocean-x11-run","ocean-x11-shell","ocean-x11-app"):
        if not a:die("command required")
        env=os.environ.copy();env["DISPLAY"]=":1";p=subprocess.run(a if cmd!="ocean-x11-shell" else ["/system/bin/sh","-lc"," ".join(a)],env=env);raise SystemExit(p.returncode)
    if cmd=="ocean-x11-screenshot":
        emit(save_screenshot(a[0] if a else "x11-screen.jpg"));return
    if cmd=="ocean-x11-record":emit(post("/api/capture",{"action":"record_start"}));return
    if cmd.startswith("ocean-render-"):
        if not a:die("file required")
        emit(post("/api/open",{"target":a[0]}));return
    die("unhandled X11 command")

def handle_3d(cmd,a):
    if cmd in ("ocean-3d","ocean-3d-open","ocean-3d-obj","ocean-3d-model"):
        if not a:die("OBJ path required")
        emit(post("/api/3d",{"action":"open","path":str(P(a[0]).resolve())}));return
    if cmd=="ocean-3d-info":emit(post("/api/3d",{"action":"status"}));return
    if cmd=="ocean-3d-wireframe":emit(post("/api/3d",{"action":"wireframe"}));return
    if cmd=="ocean-3d-solid":emit(post("/api/3d",{"action":"solid"}));return
    if cmd=="ocean-3d-reset":emit(post("/api/3d",{"action":"reset"}));return
    if cmd=="ocean-3d-rotate":emit(post("/api/3d",{"action":"rotate","x":float(a[0]),"y":float(a[1])}));return
    if cmd=="ocean-3d-zoom":emit(post("/api/3d",{"action":"zoom","delta":float(a[0])}));return
    if cmd in ("ocean-3d-grid","ocean-3d-pan","ocean-3d-camera","ocean-3d-light","ocean-3d-background"):
        emit({"command":cmd,"accepted":True,"note":"viewer-safe control reserved; current native viewer supports rotation/zoom/wireframe/solid/reset"});return
    if cmd=="ocean-3d-screenshot":emit(save_screenshot(a[0] if a else "ocean-3d.jpg"));return
    if cmd in ("ocean-obj-info","ocean-obj-bounds"):emit(obj_info(a[0]));return
    if cmd in ("ocean-obj-normalize","ocean-obj-center"):emit(obj_info(a[0],"normalize" if cmd.endswith("normalize") else "center",a[1] if len(a)>1 else None));return
    die("unhandled 3D command")

def handle_files(cmd,a):
    if not a and cmd not in ("ocean-path-space",):die("path required")
    p=P(a[0]).expanduser() if a else P(".")
    if cmd=="ocean-file-info":emit({"path":str(p),"exists":p.exists(),"file":p.is_file(),"dir":p.is_dir(),"bytes":p.stat().st_size if p.exists() else None,"mtime":p.stat().st_mtime if p.exists() else None});return
    if cmd=="ocean-file-mime":print(mimetypes.guess_type(str(p))[0] or "application/octet-stream");return
    if cmd=="ocean-file-hash":
        hsh=hashlib.sha256()
        with p.open("rb") as f:
            for b in iter(lambda:f.read(1024*1024),b""):hsh.update(b)
        print(hsh.hexdigest());return
    if cmd in ("ocean-file-head","ocean-file-tail"):
        n=int(a[1]) if len(a)>1 else 10;ls=p.read_text(errors="replace").splitlines();print("\n".join(ls[:n] if cmd.endswith("head") else ls[-n:]));return
    if cmd=="ocean-file-lines":print(sum(1 for _ in p.open(errors="replace")));return
    if cmd=="ocean-file-bytes":print(p.stat().st_size);return
    if cmd=="ocean-file-copy":shutil.copy2(p,a[1]);emit({"copied":a[1]});return
    if cmd=="ocean-file-move":shutil.move(str(p),a[1]);emit({"moved":a[1]});return
    if cmd=="ocean-file-remove":
        if p.is_dir():shutil.rmtree(p)
        else:p.unlink()
        emit({"removed":str(p)});return
    if cmd=="ocean-file-find":
        q=a[1] if len(a)>1 else "*";emit([str(x) for x in p.rglob(q)][:5000]);return
    if cmd=="ocean-file-list":emit([x.name for x in sorted(p.iterdir())]);return
    if cmd=="ocean-file-tree":emit([str(x.relative_to(p)) for x in p.rglob("*")][:5000]);return
    if cmd in ("ocean-file-preview","ocean-file-open"):emit(post("/api/open",{"target":str(p.resolve())}));return
    if cmd=="ocean-file-share":emit(post("/api/share-file",{"path":str(p.resolve())}));return
    if cmd=="ocean-path":print(str(p));return
    if cmd=="ocean-path-real":print(str(p.resolve()));return
    if cmd=="ocean-path-size":
        total=p.stat().st_size if p.is_file() else sum(x.stat().st_size for x in p.rglob("*") if x.is_file());print(total);return
    if cmd=="ocean-path-space":
        u=shutil.disk_usage(p if p.exists() else P("."));emit({"total":u.total,"used":u.used,"free":u.free});return
    die("unhandled file command")

def handle_system(cmd,a):
    if cmd=="ocean-battery":emit(get("/api/battery"));return
    if cmd in ("ocean-os","ocean-arch","ocean-device-info"):emit(get("/api/info"));return
    if cmd=="ocean-memory":
        d={}
        for l in P("/proc/meminfo").read_text().splitlines():
            if ":" in l:k,v=l.split(":",1);d[k]=v.strip()
        emit(d);return
    if cmd=="ocean-cpu":emit({"cpuinfo":P("/proc/cpuinfo").read_text(errors="replace"),"count":os.cpu_count()});return
    if cmd=="ocean-storage":
        u=shutil.disk_usage(PREFIX);emit({"total":u.total,"used":u.used,"free":u.free,"prefix":str(PREFIX)});return
    if cmd=="ocean-network":
        emit({"interfaces":[x.name for x in P("/sys/class/net").iterdir()] if P("/sys/class/net").exists() else []});return
    if cmd=="ocean-ip":
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:s.connect(("8.8.8.8",80));ip=s.getsockname()[0]
        except:ip="127.0.0.1"
        finally:s.close()
        print(ip);return
    if cmd=="ocean-ports":
        rows=[]
        for f in ("/proc/net/tcp","/proc/net/tcp6"):
            if P(f).exists():
                for l in P(f).read_text().splitlines()[1:]:
                    x=l.split()
                    if len(x)>3:rows.append({"port":int(x[1].split(":")[1],16),"state":x[3]})
        emit(rows);return
    if cmd in ("ocean-processes","ocean-process"):
        rows=[]
        for p in P("/proc").iterdir():
            if p.name.isdigit():
                try:rows.append({"pid":int(p.name),"cmd":(p/"cmdline").read_bytes().replace(b"\0",b" ").decode(errors="replace").strip()})
                except:pass
        if cmd=="ocean-process" and a:rows=[r for r in rows if r["pid"]==int(a[0])]
        emit(rows[:5000]);return
    if cmd=="ocean-env":emit(dict(os.environ));return
    if cmd=="ocean-prefix":print(PREFIX);return
    if cmd=="ocean-which":print(shutil.which(a[0]) or "");return
    if cmd=="ocean-command":
        if not a:die("command required")
        raise SystemExit(subprocess.run(a).returncode)
    if cmd=="ocean-runtime":emit({"python":sys.version,"prefix":str(PREFIX),"ipc":IPC,"x11":x11_runtime_status()});return
    if cmd=="ocean-version":print("ocean-device-suite 1.0.0");return
    if cmd=="ocean-health":
        r={}
        try:r["app_api"]=get("/api/ping")
        except SystemExit:r["app_api"]={"status":"offline"}
        r["x11"]=x11_runtime_status();r["prefix_exists"]=PREFIX.exists();emit(r);return
    if cmd=="ocean-permissions":emit(device("device_status",{}));return
    if cmd=="ocean-features":emit({"commands":COMMANDS,"count":len(COMMANDS),"x11_native_renderer":True,"3d_obj_viewer":True,"accessibility_control":True,"screen_capture":True,"screen_record":True});return
    die("unhandled system command")

def json_get(obj,path):
    cur=obj
    for p in path.strip(".").split(".") if path else []:cur=cur[int(p)] if isinstance(cur,list) else cur[p]
    return cur
def handle_util(cmd,a):
    if cmd=="ocean-wait":time.sleep(float(a[0]));return
    if cmd=="ocean-retry":
        if len(a)<2:die("COUNT COMMAND...")
        for i in range(int(a[0])):
            r=subprocess.run(a[1:])
            if r.returncode==0:raise SystemExit(0)
            time.sleep(min(5,2**i))
        raise SystemExit(r.returncode)
    if cmd=="ocean-sequence":
        if not a:die("command strings required")
        for x in a:
            r=subprocess.run(["/system/bin/sh","-lc",x])
            if r.returncode:raise SystemExit(r.returncode)
        return
    if cmd=="ocean-parallel":
        ps=[subprocess.Popen(["/system/bin/sh","-lc",x]) for x in a];raise SystemExit(max([p.wait() for p in ps] or [0]))
    if cmd=="ocean-json":
        obj=json.loads(P(a[0]).read_text() if a and P(a[0]).exists() else " ".join(a));emit(obj);return
    if cmd=="ocean-json-get":
        obj=json.loads(P(a[0]).read_text() if P(a[0]).exists() else a[0]);emit(json_get(obj,a[1] if len(a)>1 else ""));return
    if cmd=="ocean-json-set":
        if len(a)<3:die("FILE KEY VALUE")
        p=P(a[0]);obj=json.loads(p.read_text());keys=a[1].split(".");cur=obj
        for k in keys[:-1]:cur=cur.setdefault(k,{})
        try:v=json.loads(a[2])
        except:v=a[2]
        cur[keys[-1]]=v;p.write_text(json.dumps(obj,indent=2)+"\n");emit(obj);return
    if cmd=="ocean-base64":
        if a and a[0]=="-d":sys.stdout.buffer.write(base64.b64decode(a[1] if len(a)>1 else sys.stdin.read().strip()))
        else:print(base64.b64encode((" ".join(a) if a else sys.stdin.read()).encode()).decode())
        return
    if cmd=="ocean-urlencode":print(urllib.parse.quote(" ".join(a),safe=""));return
    if cmd=="ocean-urldecode":print(urllib.parse.unquote(" ".join(a)));return
    if cmd=="ocean-timestamp":print(dt.datetime.now(dt.timezone.utc).isoformat());return
    if cmd=="ocean-uuid":print(uuid.uuid4());return
    if cmd=="ocean-random":print(os.urandom(int(a[0]) if a else 16).hex());return
    if cmd=="ocean-hash":
        algo=a[0] if len(a)>1 else "sha256";data=(" ".join(a[1:]) if len(a)>1 else " ".join(a)).encode();hsh=hashlib.new(algo);hsh.update(data);print(hsh.hexdigest());return
    if cmd=="ocean-http":
        if not a:die("URL")
        with urllib.request.urlopen(a[0],timeout=15) as r:sys.stdout.buffer.write(r.read())
        return
    if cmd=="ocean-download":
        if len(a)<2:die("URL OUTPUT")
        urllib.request.urlretrieve(a[0],a[1]);emit({"output":a[1],"bytes":P(a[1]).stat().st_size});return
    if cmd=="ocean-upload":
        if len(a)<2:die("URL FILE")
        data=P(a[1]).read_bytes();req=urllib.request.Request(a[0],data=data,method="POST",headers={"Content-Type":"application/octet-stream"})
        with urllib.request.urlopen(req,timeout=30) as r:emit({"status":r.status,"response":r.read().decode(errors="replace")});return
    if cmd=="ocean-watch-file":
        if not a:die("FILE [SECONDS]")
        p=P(a[0]);last=p.stat().st_mtime if p.exists() else None;timeout=float(a[1]) if len(a)>1 else 60;end=time.time()+timeout
        while time.time()<end:
            cur=p.stat().st_mtime if p.exists() else None
            if cur!=last:emit({"changed":True,"mtime":cur});return
            time.sleep(.5)
        emit({"changed":False});return
    if cmd=="ocean-watch-port":
        if len(a)<2:die("HOST PORT [SECONDS]")
        end=time.time()+(float(a[2]) if len(a)>2 else 60)
        while time.time()<end:
            try:s=socket.create_connection((a[0],int(a[1])),.5);s.close();emit({"open":True});return
            except:time.sleep(.5)
        emit({"open":False});return
    if cmd=="ocean-wait-app":
        if not a:die("PACKAGE [SECONDS]")
        timeout=float(a[1]) if len(a)>1 else 30;end=time.time()+timeout
        while time.time()<end:
            r=device("list_android_apps",{"query":a[0]})
            if any(x.get("package_name")==a[0] for x in r.get("apps",[])):emit({"available":True});return
            time.sleep(1)
        emit({"available":False});return
    die("unhandled utility command")

def main():
    cmd=P(sys.argv[0]).name
    a=sys.argv[1:]
    if cmd not in COMMANDS:
        if a and a[0] in COMMANDS:cmd=a.pop(0)
        elif not a or a[0] in ("-h","--help"):
            print("Ocean device/render suite: 200 non-root CLI commands")
            print("\n".join(COMMANDS));return
        else:die("unknown command")
    if a and a[0] in ("-h","--help"):
        print(cmd+" — OceanStudio device/render command");return
    if cmd in DEVICE:handle_device(cmd,a)
    elif cmd in CAPTURE:handle_capture(cmd,a)
    elif cmd in INTENT:handle_intent(cmd,a)
    elif cmd in X11:handle_x11(cmd,a)
    elif cmd in D3:handle_3d(cmd,a)
    elif cmd in FILES:handle_files(cmd,a)
    elif cmd in SYSTEM:handle_system(cmd,a)
    else:handle_util(cmd,a)
if __name__=="__main__":main()
