#!/usr/bin/env python3
import json,os,struct,subprocess,sys,tempfile
from pathlib import Path

R34=Path(sys.argv[1]).resolve()
R35=Path(sys.argv[2]).resolve()
R36=Path(sys.argv[3]).resolve()

def load(path,name):
    import importlib.util
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

m34=load(R34,"s34");m35=load(R35,"s35");m36=load(R36,"s36")
assert len(m34.COMMANDS)==100 and len(set(m34.COMMANDS))==100
assert len(m35.COMMANDS)==100 and len(set(m35.COMMANDS))==100
assert len(m36.COMMANDS)==100 and len(set(m36.COMMANDS))==100
all_names=m34.COMMANDS+m35.COMMANDS+m36.COMMANDS
assert len(all_names)==300 and len(set(all_names))==300

RUNTIME={**{x:R34 for x in m34.COMMANDS},**{x:R35 for x in m35.COMMANDS},**{x:R36 for x in m36.COMMANDS}}

def run(cmd,*args,cwd=None,env=None):
    e=os.environ.copy()
    if env:e.update(env)
    p=subprocess.run([sys.executable,str(RUNTIME[cmd]),cmd,*map(str,args)],cwd=cwd,env=e,capture_output=True,text=True)
    if p.returncode:
        raise AssertionError(f"{cmd} failed rc={p.returncode}\nstdout={p.stdout}\nstderr={p.stderr}")
    return p.stdout

# Every package command must enter a real registered dispatch path.
for cmd in all_names:
    out=run(cmd,"--help")
    assert cmd in out

with tempfile.TemporaryDirectory() as td:
    d=Path(td)

    # ---------------- shard 34: VNC/noVNC ----------------
    v=json.loads(run("vnc-uri-parse","vnc://127.0.0.1:5901"))
    assert v["host"]=="127.0.0.1" and v["port"]==5901 and v["display"]==1
    assert run("vnc-display-port","2").strip()=="5902"
    assert run("vnc-port-display","5903").strip()=="3"
    rfb=json.loads(run("vnc-rfb-version","524642203030332e3030380a"))
    assert rfb["valid"] is True
    assert json.loads(run("vnc-rfb-security-types","020102"))==[1,2]
    assert "tight" in json.loads(run("vnc-rfb-encoding-names","7","0"))
    assert run("vnc-rfb-key-event","1","0x41").strip().startswith("0401")
    assert json.loads(run("vnc-localhost-check","127.0.0.1"))["localhost"] is True
    assert "vnc.html" in run("novnc-url","127.0.0.1","6080","127.0.0.1:5901")

    # ---------------- shard 34: Wine/PE ----------------
    wp=d/"wineprefix";(wp/"drive_c/windows/system32").mkdir(parents=True)
    (wp/"system.reg").write_text("WINE REGISTRY Version 2\n[Software\\\\Ocean]\n\"Name\"=\"Ocean\"\n")
    (wp/"user.reg").write_text("[Software\\\\User]\n\"A\"=\"B\"\n")
    wine_env={"WINEPREFIX":str(wp)}
    info=json.loads(run("wine-prefix-info",env=wine_env))
    assert info["exists"] is True and info["system_reg"] is True
    assert run("wine-reg-key-count",wp/"system.reg").strip()=="1"
    assert run("wine-reg-value-count",wp/"system.reg").strip()=="1"
    assert "Z:" in run("wine-path-to-win",d/"hello.txt")

    pe=d/"demo.exe"
    b=bytearray(0x200)
    b[0:2]=b"MZ"
    b[0x3c:0x40]=struct.pack("<I",0x80)
    b[0x80:0x84]=b"PE\0\0"
    # machine x86_64, 3 sections, zero timestamps/symbol tables, opt header 0
    b[0x84:0x98]=struct.pack("<HHIIIHH",0x8664,3,0,0,0,0,0)
    b[0x120:0x130]=b"KERNEL32.dll\0"
    pe.write_bytes(b)
    assert run("wine-pe-arch",pe).strip()=="x86_64"
    assert run("wine-pe-sections",pe).strip()=="3"
    assert "KERNEL32.dll" in json.loads(run("wine-pe-import-hints",pe))

    # ---------------- shard 34: Box64/ELF ----------------
    elf=d/"x64.bin"
    e=bytearray(64);e[:4]=b"\x7fELF";e[4]=2;e[5]=1;e[18:20]=(62).to_bytes(2,"little");e[32:50]=b"libc.so.6\0libm.so.6\0"
    elf.write_bytes(e)
    assert run("box64-elf-arch",elf).strip()=="x86_64"
    assert run("box64-x64-check",elf).strip()=="true"
    assert "libc.so.6" in json.loads(run("box64-elf-needed-hints",elf))
    rc=d/"box64rc";rc.write_text("[*]\nBOX64_DYNAREC=1\nBOX64_LOG=1\n")
    assert "*" in json.loads(run("box64-rc-sections",rc))
    assert run("box64-rc-get",rc,"*","BOX64_DYNAREC").strip()=="1"
    assert json.loads(run("box64-compat-summary",elf))["target"]=="x86_64"

    # ---------------- shard 34: X11/libX ----------------
    disp=json.loads(run("x11-display-parse",":1.0"))
    assert disp["display"]==1 and disp["screen"]==0
    geom=json.loads(run("x11-geometry-parse","1280x720+10+20"))
    assert geom=={"width":1280,"height":720,"x":10,"y":20}
    rgb=json.loads(run("x11-color-parse","#ff8040"))
    assert rgb=={"r":255,"g":128,"b":64}
    assert "/tmp/.X11-unix/X1" in run("x11-socket-path",":1")

    # ---------------- shard 35: React/Vite ----------------
    web=d/"web";(web/"src").mkdir(parents=True)
    (web/"package.json").write_text(json.dumps({
      "name":"ocean-web","version":"1.0.0","type":"module",
      "scripts":{"dev":"vite","build":"vite build"},
      "dependencies":{"react":"^19.0.0","react-dom":"^19.0.0","react-router-dom":"^7.0.0"},
      "devDependencies":{"vite":"^8.3.0","@vitejs/plugin-react":"latest","typescript":"latest"}
    }))
    (web/"src/App.tsx").write_text("""import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Route} from 'react-router-dom';
export function App(){ const [n,setN]=useState(0); return <Route path="/home" element={<div>{n}</div>} />; }
""")
    (web/"src/main.tsx").write_text("import {App} from './App';\n")
    (web/"index.html").write_text('<div id="root"></div>')
    (web/"vite.config.ts").write_text("""export default { base:'/app/', server:{port:5199,proxy:{'/api':'http://127.0.0.1:8080'}}, build:{target:'es2022',outDir:'dist2'} }""")
    rp=json.loads(run("react-package-check",web));assert rp["react"]=="^19.0.0"
    assert "App" in json.loads(run("react-component-names",web))
    hooks=json.loads(run("react-hook-usage",web));assert hooks["useState"]==1
    assert "/home" in json.loads(run("react-router-routes",web))
    assert run("vite-server-port",web).strip()=="5199"
    assert run("vite-base-path",web).strip()=="/app/"
    assert run("vite-build-target",web).strip()=="es2022"
    assert run("vite-outdir",web).strip()=="dist2"
    assert json.loads(run("vite-package-check",web))["vite"]=="^8.3.0"

    # ---------------- shard 35: Angular ----------------
    ng=d/"ng";(ng/"src/app").mkdir(parents=True)
    (ng/"package.json").write_text(json.dumps({
      "dependencies":{"@angular/core":"^21.0.0","@angular/common":"^21.0.0"},
      "devDependencies":{"@angular/cli":"^21.0.0","typescript":"latest"}
    }))
    (ng/"angular.json").write_text(json.dumps({"defaultProject":"app","projects":{"app":{"architect":{"build":{"options":{"outputPath":"dist/app","assets":["public"],"styles":["src/styles.css"],"scripts":[]}},"serve":{"options":{"port":4300}}}}}}))
    (ng/"tsconfig.json").write_text(json.dumps({"compilerOptions":{"paths":{"@app/*":["src/app/*"]}}}))
    (ng/"src/app/app.component.ts").write_text("const routes=[{path:'dashboard'}];\n")
    ap=json.loads(run("angular-package-check",ng));assert ap["angular_core"]=="^21.0.0"
    assert "app" in json.loads(run("angular-json-projects",ng))
    assert "dashboard" in json.loads(run("angular-route-hints",ng))
    assert "4300" in run("angular-port",ng)
    sc=json.loads(run("angular-scaffold-component",ng,"ocean-card"));assert Path(sc["path"]).exists()

    # ---------------- shard 35: Cloud/Node ----------------
    cloud_env={
      "AWS_REGION":"us-east-1","AZURE_SUBSCRIPTION_ID":"x","GOOGLE_CLOUD_PROJECT":"ocean",
      "CLOUDFLARE_API_TOKEN":"secret","VERCEL":"1","NETLIFY":"true"
    }
    providers=json.loads(run("cloud-provider-detect",web,env=cloud_env))
    assert set(["aws","azure","gcp","cloudflare","vercel","netlify"]).issubset(set(providers))
    assert "AWS_REGION" in json.loads(run("cloud-env-aws",web,env=cloud_env))
    assert run("cloud-url-provider","https://s3.amazonaws.com/bucket").strip()=="aws"
    assert json.loads(run("cloud-secret-name-audit",web,env=cloud_env))
    assert json.loads(run("node-package-json-summary",web))["name"]=="ocean-web"
    assert json.loads(run("node-dependency-count",web))["dependencies"]==3
    assert json.loads(run("node-esm-check",web))["type_module"] is True

    # ---------------- shard 36: OpenAI ----------------
    oe={"OPENAI_API_KEY":"sk-proj-test_1234567890abcdef","OPENAI_PROJECT":"proj_test","HOME":str(d/"home")}
    (d/"home/.codex").mkdir(parents=True)
    (d/"home/.codex/config.toml").write_text('model="gpt-5.6"\nsandbox_mode="workspace-write"\napproval_policy="on-request"\n')
    envcheck=json.loads(run("openai-env-check",env=oe));assert envcheck["api_key"] is True and envcheck["project"] is True
    keycheck=json.loads(run("openai-key-format",env=oe));assert keycheck["looks_project_key"] is True
    req=json.loads(run("openai-responses-request","gpt-5.6","hello","ocean",env=oe))
    assert req["url"].endswith("/responses") and req["json"]["model"]=="gpt-5.6"
    response=d/"response.json";response.write_text(json.dumps({"id":"resp_1","status":"completed","output":[{"type":"message","content":[{"type":"output_text","text":"hello world"}]}],"usage":{"input_tokens":3,"output_tokens":2}}))
    assert run("openai-responses-output-text",response).strip()=="hello world"
    assert json.loads(run("openai-response-usage",response))["output_tokens"]==2
    sse=d/"events.txt";sse.write_text('event: response.output_text.delta\ndata: {"delta":"hi"}\n\n')
    ev=json.loads(run("openai-responses-stream-events",sse));assert ev[0]["event"]=="response.output_text.delta"
    assert run("openai-codex-model",env=oe).strip().strip('"')=="gpt-5.6"
    assert "workspace-write" in run("openai-codex-sandbox",env=oe)
    assert "trace_" in run("openai-agents-trace-id")

    # ---------------- shard 36: Git ----------------
    gr=d/"git";gr.mkdir()
    subprocess.run(["git","init","-b","main"],cwd=gr,check=True,capture_output=True)
    subprocess.run(["git","config","user.email","ocean@example.test"],cwd=gr,check=True)
    subprocess.run(["git","config","user.name","Ocean Test"],cwd=gr,check=True)
    (gr/"a.txt").write_text("one\n")
    subprocess.run(["git","add","a.txt"],cwd=gr,check=True)
    subprocess.run(["git","commit","-m","first"],cwd=gr,check=True,capture_output=True)
    assert run("gitplus-branch",cwd=gr).strip()=="main"
    assert len(run("gitplus-head",cwd=gr).strip())==40
    assert run("gitplus-last-subject",cwd=gr).strip()=="first"
    assert "a.txt" in json.loads(run("gitplus-tree",cwd=gr))
    (gr/"b.txt").write_text("new")
    st=json.loads(run("gitplus-status-counts",cwd=gr));assert st["untracked"]==1
    assert "b.txt" in json.loads(run("gitplus-untracked",cwd=gr))
    assert json.loads(run("gitplus-health",cwd=gr))["branch"]=="main"

    # ---------------- shard 36: HTTP ----------------
    rq=d/"req.json";rq.write_text(json.dumps({"url":"https://example.com/api?q=1","method":"POST","headers":{"Accept":"application/json"}}))
    assert run("httpx-request-line",rq).strip()=="POST /api?q=1 HTTP/1.1"
    assert run("httpx-header-get",rq,"accept").strip()=="application/json"
    changed=json.loads(run("httpx-query-set",rq,"q","2"));assert "q=2" in changed["url"]
    assert "curl" in run("httpx-curl",rq)
    assert "fetch(" in run("httpx-node-fetch",rq)
    assert run("httpx-status-class","404").strip()=="client-error"
    assert run("httpx-auth-basic","a","b").strip().startswith("Basic ")
    assert json.loads(run("httpx-cache-control","public,max-age=60"))["max-age"]=="60"
    hs=d/"headers.txt";hs.write_text("Access-Control-Allow-Origin: *\nAccess-Control-Allow-Methods: GET, POST\n")
    cors=json.loads(run("httpx-cors-check",hs));assert cors["allow_origin"]=="*"
    nd=d/"data.ndjson";nd.write_text('{"a":1}\n{"a":2}\n');assert len(json.loads(run("httpx-ndjson",nd)))==2

print("PASS: shards 34/35/36 register 300 unique commands and representative VNC/Wine/Box64/X11, React/Vite/Angular/cloud/Node, OpenAI/Git/HTTP behavior works")
