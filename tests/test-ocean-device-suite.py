#!/usr/bin/env python3
import base64, importlib.util, json, os, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
R=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location("suite",R);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert len(m.COMMANDS)==200 and len(set(m.COMMANDS))==200
assert len(m.DEVICE)==35 and len(m.CAPTURE)==25 and len(m.INTENT)==30 and len(m.X11)==30 and len(m.D3)==20 and len(m.FILES)==20 and len(m.SYSTEM)==20 and len(m.UTIL)==20
required={"ocean-open","ocean-click","ocean-coordinate","ocean-object","ocean-render","ocean-3d","ocean-intent-pass","ocean-take-selfie","ocean-screenshot","ocean-record","ocean-api","ocean-x11-runtime"}
assert required<=set(m.COMMANDS)

class H(BaseHTTPRequestHandler):
    def log_message(self,*x):pass
    def sendj(self,obj):
        b=json.dumps(obj).encode();self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        if self.path=="/api/info":self.sendj({"status":"ok","app":"OceanStudio","sdk":35})
        elif self.path=="/api/battery":self.sendj({"success":True,"percentage":80})
        elif self.path=="/api/clipboard":self.sendj({"success":True,"text":"clip"})
        else:self.sendj({"success":True})
    def do_POST(self):
        n=int(self.headers.get("Content-Length","0"));raw=self.rfile.read(n);body=json.loads(raw or b"{}")
        if self.path=="/api/device":
            tool=body.get("tool")
            if tool=="device_status":self.sendj({"connected":True,"live_control_enabled":True,"exit_code":0})
            elif tool=="inspect_android_screen":self.sendj({"nodes":[{"ref":"1:0","text":"OK","description":"","view_id":"x:id/ok","clickable":True,"editable":False,"bounds":[0,0,100,100]}],"exit_code":0})
            else:self.sendj({"completed":True,"exit_code":0})
        elif self.path=="/api/capture":self.sendj({"image_base64":base64.b64encode(b"jpg").decode(),"image_width":100,"image_height":50,"media_type":"image/jpeg","success":True})
        elif self.path=="/api/x11":self.sendj({"success":True,"open":True,"connected":False})
        elif self.path=="/api/3d":self.sendj({"success":True,"open":True})
        else:self.sendj({"success":True})
srv=HTTPServer(("127.0.0.1",8088),H);threading.Thread(target=srv.serve_forever,daemon=True).start()

def run(cmd,*args):
    r=subprocess.run([sys.executable,str(R),cmd,*args],capture_output=True,text=True,env={**os.environ,"OCEAN_IPC":"http://127.0.0.1:8088"})
    if r.returncode:raise AssertionError(cmd+": "+r.stderr)
    return r.stdout

with tempfile.TemporaryDirectory() as td:
    p=Path(td)
    f=p/"a.txt";f.write_text("one\ntwo\nthree\n")
    assert "3" in run("ocean-file-lines",str(f))
    assert len(run("ocean-file-hash",str(f)).strip())==64
    assert "OceanStudio" in run("ocean-device-info")
    assert "80" in run("ocean-battery")
    assert "OK" in run("ocean-screen-find","OK")
    assert "completed" in run("ocean-click","1:0")
    assert "success" in run("ocean-x11-open")
    obj=p/"x.obj";obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    assert '"vertices": 3' in run("ocean-obj-info",str(obj))
    assert "success" in run("ocean-3d-open",str(obj))
    assert json.loads(run("ocean-json",'{"x":1}'))["x"]==1
    assert run("ocean-urlencode","a b").strip()=="a%20b"
srv.shutdown()
print("PASS: 200 unique commands registered; local, IPC, accessibility, X11 and 3D paths smoke-tested")
