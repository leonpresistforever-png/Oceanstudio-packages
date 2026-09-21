#!/usr/bin/env python3
from __future__ import annotations
import json,os,re,shutil,sys
from pathlib import Path
from collections import Counter
P=Path

REACT=["react-package-check","react-deps","react-scripts","react-entry-find","react-jsx-files","react-tsx-files","react-component-names","react-hook-usage","react-imports","react-dom-imports","react-router-routes","react-env-vars","react-vite-detect","react-next-detect","react-tsconfig-check","react-eslint-check","react-build-dir","react-scaffold-minimal","react-index-html","react-health"]
VITE=["vite-package-check","vite-config-find","vite-config-summary","vite-plugins","vite-aliases","vite-env-files","vite-env-vars","vite-public-dir","vite-entry-html","vite-script-check","vite-dependency-scan","vite-assets-scan","vite-base-path","vite-server-port","vite-proxy-routes","vite-build-target","vite-outdir","vite-scaffold-react","vite-scaffold-vanilla","vite-health"]
ANG=["angular-package-check","angular-json-projects","angular-json-default-project","angular-build-config","angular-serve-config","angular-assets","angular-styles","angular-scripts","angular-tsconfig-paths","angular-module-files","angular-component-files","angular-service-files","angular-route-hints","angular-env-files","angular-cli-version","angular-node-check","angular-port","angular-output-path","angular-scaffold-component","angular-health"]
CLOUD=["cloud-provider-detect","cloud-env-aws","cloud-env-azure","cloud-env-gcp","cloud-env-cloudflare","cloud-env-vercel","cloud-env-netlify","cloud-credential-files","cloud-kube-context","cloud-kube-namespace","cloud-terraform-workspace","cloud-terraform-vars","cloud-helm-values","cloud-docker-context","cloud-region-normalize","cloud-url-provider","cloud-ci-detect","cloud-secret-name-audit","cloud-config-summary","cloud-health"]
NODE=["node-version-check","node-package-manager","node-lock-detect","node-package-json-summary","node-bin-scripts","node-module-type","node-engines-check","node-workspaces","node-dependency-count","node-peer-deps","node-optional-deps","node-package-exports","node-package-imports","node-npmrc-summary","node-pnpm-workspace","node-yarn-workspaces","node-bun-lock","node-esm-check","node-cjs-check","node-project-health"]
COMMANDS=REACT+VITE+ANG+CLOUD+NODE
assert len(COMMANDS)==100 and len(set(COMMANDS))==100

def emit(x):
    if isinstance(x,(dict,list,tuple,Counter)):print(json.dumps(x,indent=2,ensure_ascii=False,default=str))
    else:print(x)
def die(s,c=2):print(s,file=sys.stderr);raise SystemExit(c)
def root(a):return P(a[0] if a else ".").resolve()
def load_json(p):
    try:return json.loads(P(p).read_text())
    except Exception:return {}
def pkg(rootp):
    p=rootp/"package.json"
    return load_json(p) if p.exists() else {}
def files(rootp,patterns):
    out=[]
    for pat in patterns:out += [x for x in rootp.rglob(pat) if "node_modules" not in x.parts and ".git" not in x.parts]
    return sorted(set(out))
def source_texts(rootp,patterns):
    for p in files(rootp,patterns):
        try:yield p,p.read_text(errors="replace")
        except:pass
def rels(rootp,ps):return [str(x.relative_to(rootp)) for x in ps]
def npmdeps(d):
    out={}
    for k in ("dependencies","devDependencies","peerDependencies","optionalDependencies"):
        if isinstance(d.get(k),dict):out.update(d[k])
    return out
def parse_version(v):
    m=re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?",str(v));return tuple(int(x or 0) for x in m.groups()) if m else None

def react(cmd,a):
    r=root(a);d=pkg(r);deps=npmdeps(d)
    if cmd=="react-package-check":emit({"package_json":bool(d),"react":deps.get("react"),"react_dom":deps.get("react-dom")});return
    if cmd=="react-deps":emit({k:v for k,v in deps.items() if "react" in k.lower()});return
    if cmd=="react-scripts":emit(d.get("scripts",{}));return
    if cmd=="react-entry-find":
        cand=["src/main.tsx","src/main.jsx","src/index.tsx","src/index.jsx","src/App.tsx","src/App.jsx"];emit([x for x in cand if (r/x).exists()]);return
    if cmd=="react-jsx-files":emit(rels(r,files(r,["*.jsx"])));return
    if cmd=="react-tsx-files":emit(rels(r,files(r,["*.tsx"])));return
    if cmd=="react-component-names":
        vals=set()
        for _,s in source_texts(r,["*.jsx","*.tsx","*.js","*.ts"]):
            vals.update(re.findall(r"(?m)(?:function|class)\s+([A-Z][A-Za-z0-9_]*)",s));vals.update(re.findall(r"(?m)const\s+([A-Z][A-Za-z0-9_]*)\s*=",s))
        emit(sorted(vals));return
    if cmd=="react-hook-usage":
        c=Counter()
        for _,s in source_texts(r,["*.jsx","*.tsx","*.js","*.ts"]):
            c.update(re.findall(r"\b(use[A-Z][A-Za-z0-9_]*)\s*\(",s))
        emit(c);return
    if cmd=="react-imports":
        vals=[]
        for p,s in source_texts(r,["*.jsx","*.tsx","*.js","*.ts"]):
            if re.search(r"""from\s+['"]react['"]|require\(['"]react['"]\)""",s):vals.append(str(p.relative_to(r)))
        emit(vals);return
    if cmd=="react-dom-imports":
        vals=[]
        for p,s in source_texts(r,["*.jsx","*.tsx","*.js","*.ts"]):
            if "react-dom" in s:vals.append(str(p.relative_to(r)))
        emit(vals);return
    if cmd=="react-router-routes":
        vals=[]
        for _,s in source_texts(r,["*.jsx","*.tsx","*.js","*.ts"]):
            vals+=re.findall(r"""(?:path\s*=\s*|path\s*:\s*)['"]([^'"]+)['"]""",s)
        emit(vals);return
    if cmd=="react-env-vars":
        vals=set()
        for _,s in source_texts(r,["*.jsx","*.tsx","*.js","*.ts"]):
            vals.update(re.findall(r"\b(?:import\.meta\.env|process\.env)\.([A-Z0-9_]+)",s))
        emit(sorted(vals));return
    if cmd=="react-vite-detect":emit({"vite":bool(deps.get("vite") or (r/"vite.config.js").exists() or (r/"vite.config.ts").exists())});return
    if cmd=="react-next-detect":emit({"next":bool(deps.get("next") or (r/"next.config.js").exists() or (r/"next.config.mjs").exists())});return
    if cmd=="react-tsconfig-check":emit({"present":(r/"tsconfig.json").exists(),"jsx":load_json(r/"tsconfig.json").get("compilerOptions",{}).get("jsx") if (r/"tsconfig.json").exists() else None});return
    if cmd=="react-eslint-check":emit({"present":any((r/x).exists() for x in ["eslint.config.js","eslint.config.mjs",".eslintrc",".eslintrc.json"])});return
    if cmd=="react-build-dir":
        for x in ("dist","build",".next"):
            if (r/x).exists():print(str(r/x));return
        print("");return
    if cmd=="react-scaffold-minimal":
        out=P(a[1] if len(a)>1 else r/"ocean-react-app");(out/"src").mkdir(parents=True,exist_ok=True)
        (out/"package.json").write_text(json.dumps({"scripts":{"dev":"vite","build":"vite build"},"dependencies":{"react":"latest","react-dom":"latest"},"devDependencies":{"vite":"latest","@vitejs/plugin-react":"latest"}},indent=2)+"\n")
        (out/"index.html").write_text('<div id="root"></div><script type="module" src="/src/main.jsx"></script>\n')
        (out/"src/main.jsx").write_text("import React from 'react';\nimport {createRoot} from 'react-dom/client';\ncreateRoot(document.getElementById('root')).render(<h1>Ocean React</h1>);\n")
        emit({"path":str(out)});return
    if cmd=="react-index-html":emit({"present":(r/"index.html").exists(),"path":str(r/"index.html")});return
    if cmd=="react-health":emit({"react":deps.get("react"),"react_dom":deps.get("react-dom"),"node":shutil.which("node"),"npm":shutil.which("npm"),"entries":rels(r,files(r,["*.jsx","*.tsx"]))[:20]});return

def vite_config(r):
    for n in ("vite.config.ts","vite.config.js","vite.config.mjs","vite.config.cjs"):
        if (r/n).exists():return r/n
    return None
def vite(cmd,a):
    r=root(a);d=pkg(r);deps=npmdeps(d);cf=vite_config(r);s=cf.read_text(errors="replace") if cf else ""
    if cmd=="vite-package-check":emit({"vite":deps.get("vite"),"config":str(cf) if cf else None});return
    if cmd=="vite-config-find":print(str(cf) if cf else "");return
    if cmd=="vite-config-summary":emit({"path":str(cf) if cf else None,"bytes":cf.stat().st_size if cf else 0,"defineConfig":"defineConfig" in s});return
    if cmd=="vite-plugins":emit(re.findall(r"\bplugins\s*:\s*\[([^\]]*)\]",s,re.S));return
    if cmd=="vite-aliases":
        vals=re.findall(r"""find\s*:\s*['"]([^'"]+)['"].*?replacement\s*:\s*['"]([^'"]+)['"]""",s,re.S);emit(vals);return
    if cmd=="vite-env-files":emit(rels(r,[x for x in r.glob(".env*") if x.is_file()]));return
    if cmd=="vite-env-vars":
        vals={}
        for p in r.glob(".env*"):
            if p.is_file():
                for line in p.read_text(errors="replace").splitlines():
                    if "=" in line and not line.lstrip().startswith("#"):
                        k,v=line.split("=",1);vals[k.strip()]=v.strip()
        emit(vals);return
    if cmd=="vite-public-dir":print(str(r/"public") if (r/"public").exists() else "");return
    if cmd=="vite-entry-html":print(str(r/"index.html") if (r/"index.html").exists() else "");return
    if cmd=="vite-script-check":emit({k:v for k,v in d.get("scripts",{}).items() if "vite" in str(v)});return
    if cmd=="vite-dependency-scan":emit({k:v for k,v in deps.items() if k in ("vite","rollup","esbuild") or k.startswith("@vitejs/")});return
    if cmd=="vite-assets-scan":emit(rels(r,[x for x in r.rglob("*") if x.is_file() and x.suffix.lower() in (".png",".jpg",".jpeg",".svg",".webp",".css",".woff",".woff2")]));return
    if cmd=="vite-base-path":
        m=re.search(r"""base\s*:\s*['"]([^'"]+)['"]""",s);print(m.group(1) if m else "/");return
    if cmd=="vite-server-port":
        m=re.search(r"\bport\s*:\s*(\d+)",s);print(m.group(1) if m else "5173");return
    if cmd=="vite-proxy-routes":emit(re.findall(r"""['"](/[^'"]*)['"]\s*:\s*(?:['"]([^'"]+)['"]|\{)""",s));return
    if cmd=="vite-build-target":
        m=re.search(r"""target\s*:\s*['"]([^'"]+)['"]""",s);print(m.group(1) if m else "");return
    if cmd=="vite-outdir":
        m=re.search(r"""outDir\s*:\s*['"]([^'"]+)['"]""",s);print(m.group(1) if m else "dist");return
    if cmd in ("vite-scaffold-react","vite-scaffold-vanilla"):
        out=P(a[1] if len(a)>1 else r/("ocean-vite-react" if cmd.endswith("react") else "ocean-vite-vanilla"));out.mkdir(parents=True,exist_ok=True)
        if cmd.endswith("react"):
            (out/"package.json").write_text(json.dumps({"scripts":{"dev":"vite"},"dependencies":{"react":"latest","react-dom":"latest"},"devDependencies":{"vite":"latest","@vitejs/plugin-react":"latest"}},indent=2))
            (out/"index.html").write_text('<div id="root"></div><script type="module" src="/src.jsx"></script>');(out/"src.jsx").write_text("import React from 'react';import{createRoot}from'react-dom/client';createRoot(document.getElementById('root')).render(<h1>Ocean</h1>);")
        else:
            (out/"package.json").write_text(json.dumps({"scripts":{"dev":"vite"},"devDependencies":{"vite":"latest"}},indent=2));(out/"index.html").write_text('<div id="app">Ocean Vite</div><script type="module" src="/main.js"></script>');(out/"main.js").write_text("console.log('Ocean Vite');\n")
        emit({"path":str(out)});return
    if cmd=="vite-health":emit({"vite":deps.get("vite"),"node":shutil.which("node"),"config":str(cf) if cf else None,"index_html":(r/"index.html").exists()});return

def angular_json(r):
    p=r/"angular.json";return load_json(p) if p.exists() else {}
def ang(cmd,a):
    r=root(a);d=pkg(r);aj=angular_json(r);deps=npmdeps(d);projects=aj.get("projects",{}) if isinstance(aj,dict) else {}
    if cmd=="angular-package-check":emit({"angular_core":deps.get("@angular/core"),"angular_cli":deps.get("@angular/cli"),"angular_json":bool(aj)});return
    if cmd=="angular-json-projects":emit(projects);return
    if cmd=="angular-json-default-project":emit(aj.get("defaultProject"));return
    if cmd in ("angular-build-config","angular-serve-config"):
        key="build" if cmd=="angular-build-config" else "serve";emit({n:(v.get("architect",{}).get(key) or v.get("targets",{}).get(key)) for n,v in projects.items()});return
    if cmd in ("angular-assets","angular-styles","angular-scripts"):
        key=cmd.split("-",1)[1];vals=[]
        for v in projects.values():
            q=(v.get("architect",{}).get("build") or v.get("targets",{}).get("build") or {}).get("options",{}).get(key,[]);vals+=q if isinstance(q,list) else []
        emit(vals);return
    if cmd=="angular-tsconfig-paths":
        p=r/"tsconfig.json";emit(load_json(p).get("compilerOptions",{}).get("paths",{}) if p.exists() else {});return
    if cmd=="angular-module-files":emit(rels(r,files(r,["*.module.ts"])));return
    if cmd=="angular-component-files":emit(rels(r,files(r,["*.component.ts"])));return
    if cmd=="angular-service-files":emit(rels(r,files(r,["*.service.ts"])));return
    if cmd=="angular-route-hints":
        vals=[]
        for _,s in source_texts(r,["*.ts"]):vals+=re.findall(r"""path\s*:\s*['"]([^'"]*)['"]""",s)
        emit(vals);return
    if cmd=="angular-env-files":emit(rels(r,[x for x in r.rglob("environment*.ts") if x.is_file()]));return
    if cmd=="angular-cli-version":emit(deps.get("@angular/cli"));return
    if cmd=="angular-node-check":
        node=shutil.which("node");emit({"node":node,"package_engine":d.get("engines",{}).get("node")});return
    if cmd=="angular-port":
        vals=[]
        for v in projects.values():
            q=(v.get("architect",{}).get("serve") or v.get("targets",{}).get("serve") or {}).get("options",{}).get("port")
            if q:vals.append(q)
        emit(vals or [4200]);return
    if cmd=="angular-output-path":
        vals=[]
        for v in projects.values():
            q=(v.get("architect",{}).get("build") or v.get("targets",{}).get("build") or {}).get("options",{}).get("outputPath")
            if q:vals.append(q)
        emit(vals);return
    if cmd=="angular-scaffold-component":
        name=a[1] if len(a)>1 else "ocean-card";base=r/"src/app"/name;base.mkdir(parents=True,exist_ok=True);cls="".join(x.title() for x in name.split("-"))+"Component"
        (base/(name+".component.ts")).write_text("import {Component} from '@angular/core';\n@Component({selector:'app-"+name+"',standalone:true,template:'<p>"+name+" works!</p>'})\nexport class "+cls+" {}\n")
        emit({"path":str(base)});return
    if cmd=="angular-health":emit({"angular_core":deps.get("@angular/core"),"angular_cli":deps.get("@angular/cli"),"projects":list(projects),"node":shutil.which("node")});return

def cloud(cmd,a):
    r=root(a)
    env=dict(os.environ)
    if cmd=="cloud-provider-detect":
        hits=[]
        if any(k.startswith("AWS_") for k in env):hits.append("aws")
        if any(k.startswith(("AZURE_","ARM_")) for k in env):hits.append("azure")
        if any(k.startswith(("GOOGLE_","GCP_")) for k in env):hits.append("gcp")
        if any(k.startswith("CLOUDFLARE_") for k in env):hits.append("cloudflare")
        if "VERCEL" in env:hits.append("vercel")
        if "NETLIFY" in env:hits.append("netlify")
        emit(hits);return
    prefixes={"cloud-env-aws":("AWS_",),"cloud-env-azure":("AZURE_","ARM_"),"cloud-env-gcp":("GOOGLE_","GCP_"),"cloud-env-cloudflare":("CLOUDFLARE_",),"cloud-env-vercel":("VERCEL",),"cloud-env-netlify":("NETLIFY",)}
    if cmd in prefixes:emit({k:v for k,v in env.items() if k.startswith(prefixes[cmd])});return
    if cmd=="cloud-credential-files":
        c=[P.home()/".aws/credentials",P.home()/".azure/accessTokens.json",P.home()/".config/gcloud/application_default_credentials.json",P.home()/".config/cloudflared/cert.pem"];emit([str(x) for x in c if x.exists()]);return
    if cmd=="cloud-kube-context":
        p=P.home()/".kube/config";s=p.read_text(errors="replace") if p.exists() else "";m=re.search(r"(?m)^current-context:\s*(.+)",s);print(m.group(1).strip() if m else "");return
    if cmd=="cloud-kube-namespace":
        p=P.home()/".kube/config";s=p.read_text(errors="replace") if p.exists() else "";m=re.search(r"(?m)^\s*namespace:\s*(.+)",s);print(m.group(1).strip() if m else "default");return
    if cmd=="cloud-terraform-workspace":
        p=r/".terraform/environment";print(p.read_text().strip() if p.exists() else "default");return
    if cmd=="cloud-terraform-vars":emit(rels(r,files(r,["*.tfvars","*.tfvars.json"])));return
    if cmd=="cloud-helm-values":emit(rels(r,files(r,["values*.yaml","values*.yml"])));return
    if cmd=="cloud-docker-context":print(env.get("DOCKER_CONTEXT","default"));return
    if cmd=="cloud-region-normalize":
        s=(a[0] if a else "").strip().lower().replace("_","-");print(s);return
    if cmd=="cloud-url-provider":
        u=(a[0] if a else "").lower();p="aws" if "amazonaws.com" in u else "azure" if "azure" in u else "gcp" if "googleapis.com" in u else "cloudflare" if "cloudflare" in u else "vercel" if "vercel" in u else "netlify" if "netlify" in u else "unknown";print(p);return
    if cmd=="cloud-ci-detect":emit({k:env.get(k) for k in ("GITHUB_ACTIONS","GITLAB_CI","CIRCLECI","VERCEL","NETLIFY","CI") if env.get(k)});return
    if cmd=="cloud-secret-name-audit":
        bad=[];pat=re.compile(r"(SECRET|TOKEN|PASSWORD|PRIVATE_KEY|API_KEY)",re.I)
        for k in env:
            if pat.search(k):bad.append(k)
        emit(sorted(bad));return
    if cmd=="cloud-config-summary":emit({"terraform":len(files(r,["*.tf"])),"helm":len(files(r,["Chart.yaml"])),"kubernetes":len(files(r,["*.yaml","*.yml"])),"dockerfile":(r/"Dockerfile").exists()});return
    if cmd=="cloud-health":emit({"kubectl":shutil.which("kubectl"),"helm":shutil.which("helm"),"terraform":shutil.which("terraform"),"pulumi":shutil.which("pulumi"),"cloudflared":shutil.which("cloudflared")});return

def node(cmd,a):
    r=root(a);d=pkg(r)
    if cmd=="node-version-check":
        v=subprocess.run(["node","--version"],capture_output=True,text=True).stdout.strip() if shutil.which("node") else "";emit({"node":v,"engines":d.get("engines",{}).get("node")});return
    if cmd=="node-package-manager":
        pm="pnpm" if (r/"pnpm-lock.yaml").exists() else "yarn" if (r/"yarn.lock").exists() else "bun" if (r/"bun.lock").exists() or (r/"bun.lockb").exists() else "npm" if (r/"package-lock.json").exists() else None;emit(pm);return
    if cmd=="node-lock-detect":emit([x for x in ("package-lock.json","pnpm-lock.yaml","yarn.lock","bun.lock","bun.lockb") if (r/x).exists()]);return
    if cmd=="node-package-json-summary":emit({k:d.get(k) for k in ("name","version","type","main","module","bin","scripts","engines","packageManager") if k in d});return
    if cmd=="node-bin-scripts":emit(d.get("bin",{}));return
    if cmd=="node-module-type":emit(d.get("type","commonjs"));return
    if cmd=="node-engines-check":emit(d.get("engines",{}));return
    if cmd=="node-workspaces":emit(d.get("workspaces",[]));return
    if cmd=="node-dependency-count":emit({k:len(d.get(k,{})) for k in ("dependencies","devDependencies","peerDependencies","optionalDependencies")});return
    if cmd=="node-peer-deps":emit(d.get("peerDependencies",{}));return
    if cmd=="node-optional-deps":emit(d.get("optionalDependencies",{}));return
    if cmd=="node-package-exports":emit(d.get("exports"));return
    if cmd=="node-package-imports":emit(d.get("imports"));return
    if cmd=="node-npmrc-summary":
        p=r/".npmrc";vals={}
        if p.exists():
            for line in p.read_text(errors="replace").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k,v=line.split("=",1);vals[k.strip()]="<redacted>" if any(x in k.lower() for x in ("token","password","auth")) else v.strip()
        emit(vals);return
    if cmd=="node-pnpm-workspace":emit({"present":(r/"pnpm-workspace.yaml").exists()});return
    if cmd=="node-yarn-workspaces":emit(d.get("workspaces",[]));return
    if cmd=="node-bun-lock":emit({"bun.lock":(r/"bun.lock").exists(),"bun.lockb":(r/"bun.lockb").exists()});return
    if cmd=="node-esm-check":emit({"type_module":d.get("type")=="module","mjs":len(files(r,["*.mjs"]))});return
    if cmd=="node-cjs-check":emit({"type_commonjs":d.get("type")!="module","cjs":len(files(r,["*.cjs"]))});return
    if cmd=="node-project-health":emit({"package_json":bool(d),"node":shutil.which("node"),"npm":shutil.which("npm"),"manager":("pnpm" if (r/"pnpm-lock.yaml").exists() else "npm"),"dependency_count":sum(len(d.get(k,{})) for k in ("dependencies","devDependencies"))});return

def main():
    cmd=P(sys.argv[0]).name;a=sys.argv[1:]
    if cmd not in COMMANDS:
        if a and a[0] in COMMANDS:cmd=a.pop(0)
        elif not a or a[0] in ("-h","--help"):
            print("Shard 35 — React Vite Angular cloud and Node project tooling");print("\n".join(COMMANDS));return
        else:die("unknown command")
    if a and a[0] in ("-h","--help"):print(cmd+" — functional shard 35 utility");return
    if cmd in REACT:react(cmd,a)
    elif cmd in VITE:vite(cmd,a)
    elif cmd in ANG:ang(cmd,a)
    elif cmd in CLOUD:cloud(cmd,a)
    else:node(cmd,a)
if __name__=="__main__":main()
