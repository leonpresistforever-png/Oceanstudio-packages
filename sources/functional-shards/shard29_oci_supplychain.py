#!/usr/bin/env python3
from __future__ import annotations
import base64,hashlib,json,re,sys
from collections import Counter
from pathlib import Path
P=Path

OCI=[
"oci-layout-check","oci-index-summary","oci-index-manifests","oci-index-platforms","oci-index-digests","oci-manifest-summary","oci-manifest-config","oci-manifest-layers","oci-manifest-subject","oci-manifest-artifact-type","oci-manifest-annotations","oci-config-architecture","oci-config-os","oci-config-env","oci-config-entrypoint","oci-config-cmd","oci-config-labels","oci-layer-media-types","oci-layer-sizes","oci-digest-check","oci-blob-list","oci-blob-size","oci-missing-blobs","oci-unreferenced-blobs","oci-referrers-hints","oci-media-types","oci-platform-matrix","oci-history","oci-rootfs-diffids","oci-layout-sha256"]
SBOM=[
"sbom-cdx-version","sbom-cdx-components","sbom-cdx-services","sbom-cdx-dependencies","sbom-cdx-licenses","sbom-cdx-purls","sbom-cdx-hashes","sbom-cdx-vulnerabilities","sbom-cdx-serial","sbom-cdx-metadata","sbom-spdx-version","sbom-spdx-packages","sbom-spdx-files","sbom-spdx-relationships","sbom-spdx-licenses","sbom-spdx-external-refs","sbom-spdx-checksums","sbom-spdx-creators","sbom-spdx-document-name","sbom-spdx-namespace","sbom-format-detect","sbom-component-count","sbom-license-summary","sbom-hash-summary","sbom-purl-domains"]
ATTEST=[
"attest-dsse-envelope","attest-dsse-payload-type","attest-dsse-signatures","attest-intoto-statement","attest-intoto-subjects","attest-intoto-predicate-type","attest-slsa-builder","attest-slsa-build-type","attest-slsa-materials","attest-slsa-invocation","attest-subject-digests","attest-summary"]
COMMANDS=OCI+SBOM+ATTEST
assert len(COMMANDS)==67 and len(set(COMMANDS))==67

def emit(x):
    if isinstance(x,(dict,list,tuple,Counter)):print(json.dumps(x,indent=2,ensure_ascii=False,default=str))
    else:print(x)

def die(s,c=2):print(s,file=sys.stderr);raise SystemExit(c)
def loadj(path_or_json):
    p=P(path_or_json)
    return json.loads(p.read_text()) if p.exists() and p.is_file() else json.loads(path_or_json)

def sha256_file(p):
    h=hashlib.sha256()
    with P(p).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def oci_root(arg):
    p=P(arg)
    if p.is_file():p=p.parent
    return p

def blob_path(root,digest):
    algo,hexv=digest.split(":",1)
    return P(root)/"blobs"/algo/hexv

def index(root):
    p=P(root)/"index.json"
    if not p.exists():die("index.json not found")
    return json.loads(p.read_text())

def descriptor_digests(obj):
    out=[]
    def rec(x):
        if isinstance(x,dict):
            if isinstance(x.get("digest"),str) and ":" in x["digest"]:out.append(x["digest"])
            for v in x.values():rec(v)
        elif isinstance(x,list):
            for v in x:rec(v)
    rec(obj);return out

def load_desc_blob(root,desc):
    d=desc.get("digest")
    if not d:return None
    p=blob_path(root,d)
    if not p.exists():return None
    try:return json.loads(p.read_text())
    except:return None

def oci(cmd,a):
    op=cmd.removeprefix("oci-")
    if not a:die("OCI layout directory or JSON file required")
    target=P(a[0])
    if op.startswith("manifest-") or op.startswith("config-") or op.startswith("layer-"):
        d=loadj(a[0])
        if op=="manifest-summary":
            emit({"schemaVersion":d.get("schemaVersion"),"mediaType":d.get("mediaType"),"artifactType":d.get("artifactType"),"layers":len(d.get("layers",[])),"hasSubject":bool(d.get("subject"))});return
        if op=="manifest-config":emit(d.get("config"));return
        if op=="manifest-layers":emit(d.get("layers",[]));return
        if op=="manifest-subject":emit(d.get("subject"));return
        if op=="manifest-artifact-type":emit(d.get("artifactType"));return
        if op=="manifest-annotations":emit(d.get("annotations",{}));return
        if op=="config-architecture":emit(d.get("architecture"));return
        if op=="config-os":emit(d.get("os"));return
        cfg=d.get("config",{}) if isinstance(d.get("config"),dict) else {}
        if op=="config-env":emit(cfg.get("Env",[]));return
        if op=="config-entrypoint":emit(cfg.get("Entrypoint",[]));return
        if op=="config-cmd":emit(cfg.get("Cmd",[]));return
        if op=="config-labels":emit(cfg.get("Labels",{}));return
        if op=="layer-media-types":emit([x.get("mediaType") for x in d.get("layers",[])]);return
        if op=="layer-sizes":emit([x.get("size") for x in d.get("layers",[])]);return
    root=oci_root(a[0])
    if op=="layout-check":
        layout=root/"oci-layout";idx=root/"index.json"
        info={"oci_layout":layout.exists(),"index":idx.exists(),"blobs":(root/"blobs").exists()}
        if layout.exists():
            try:info["imageLayoutVersion"]=json.loads(layout.read_text()).get("imageLayoutVersion")
            except:info["imageLayoutVersion"]=None
        info["valid_basic"]=all(info[k] for k in ("oci_layout","index","blobs"))
        emit(info);return
    idx=index(root);mans=idx.get("manifests",[])
    if op=="index-summary":emit({"schemaVersion":idx.get("schemaVersion"),"mediaType":idx.get("mediaType"),"manifests":len(mans),"annotations":idx.get("annotations",{})});return
    if op=="index-manifests":emit(mans);return
    if op=="index-platforms":emit([x.get("platform",{}) for x in mans]);return
    if op=="index-digests":emit([x.get("digest") for x in mans]);return
    if op=="digest-check":
        bad=[];checked=0
        for d in descriptor_digests(idx):
            p=blob_path(root,d);checked+=1
            if not p.exists() or ("sha256:"+sha256_file(p))!=d:bad.append(d)
        emit({"checked":checked,"valid":not bad,"bad":bad});return
    if op=="blob-list":
        out=[]
        bp=root/"blobs"
        if bp.exists():
            for algo in bp.iterdir():
                if algo.is_dir():
                    for p in algo.iterdir():
                        if p.is_file():out.append(f"{algo.name}:{p.name}")
        emit(sorted(out));return
    if op=="blob-size":
        if len(a)<2:die("OCI_ROOT DIGEST")
        p=blob_path(root,a[1]);emit({"digest":a[1],"exists":p.exists(),"bytes":p.stat().st_size if p.exists() else None});return
    if op=="missing-blobs":
        refs=set(descriptor_digests(idx))
        for desc in mans:
            obj=load_desc_blob(root,desc)
            if obj:refs.update(descriptor_digests(obj))
        emit(sorted(d for d in refs if not blob_path(root,d).exists()));return
    if op=="unreferenced-blobs":
        refs=set(descriptor_digests(idx))
        for desc in mans:
            obj=load_desc_blob(root,desc)
            if obj:refs.update(descriptor_digests(obj))
        actual=set()
        bp=root/"blobs"
        if bp.exists():
            for algo in bp.iterdir():
                if algo.is_dir():
                    for p in algo.iterdir():
                        if p.is_file():actual.add(f"{algo.name}:{p.name}")
        emit(sorted(actual-refs));return
    if op=="referrers-hints":
        emit([x for x in mans if x.get("artifactType") or x.get("subject")]);return
    if op=="media-types":
        mts=[]
        if idx.get("mediaType"):mts.append(idx["mediaType"])
        mts += [x.get("mediaType") for x in mans if x.get("mediaType")]
        for desc in mans:
            obj=load_desc_blob(root,desc)
            if obj:
                if obj.get("mediaType"):mts.append(obj["mediaType"])
                mts += [x.get("mediaType") for x in obj.get("layers",[]) if x.get("mediaType")]
        emit(sorted(set(mts)));return
    if op=="platform-matrix":
        emit([{"digest":x.get("digest"),**(x.get("platform") or {})} for x in mans]);return
    if op in ("history","rootfs-diffids"):
        rows=[]
        for desc in mans:
            man=load_desc_blob(root,desc)
            if not man:continue
            cfg=load_desc_blob(root,man.get("config",{}))
            if cfg:rows += cfg.get("history",[]) if op=="history" else cfg.get("rootfs",{}).get("diff_ids",[])
        emit(rows);return
    if op=="layout-sha256":
        rows={}
        for p in sorted(root.rglob("*")):
            if p.is_file():rows[str(p.relative_to(root))]=sha256_file(p)
        h=hashlib.sha256()
        for k,v in rows.items():h.update((k+"\0"+v+"\n").encode())
        emit({"sha256":h.hexdigest(),"files":len(rows)});return

def licenses_from_cdx(d):
    out=[]
    def one(x):
        if isinstance(x,dict):
            lic=x.get("licenses")
            if isinstance(lic,list):
                for q in lic:
                    if isinstance(q,dict):
                        z=q.get("license",q)
                        if isinstance(z,dict):out.append(z.get("id") or z.get("name"))
                        elif isinstance(z,str):out.append(z)
            for v in x.values():one(v)
        elif isinstance(x,list):
            for v in x:one(v)
    one(d);return [x for x in out if x]

def spdx_licenses(d):
    out=[]
    for p in d.get("packages",[]):
        for k in ("licenseConcluded","licenseDeclared"):
            if p.get(k):out.append(p[k])
    for f in d.get("files",[]):
        if f.get("licenseConcluded"):out.append(f["licenseConcluded"])
    return out

def cdx_hashes(d):
    out=[]
    def rec(x):
        if isinstance(x,dict):
            if isinstance(x.get("hashes"),list):out.extend(x["hashes"])
            for v in x.values():rec(v)
        elif isinstance(x,list):
            for v in x:rec(v)
    rec(d);return out

def sbom(cmd,a):
    if not a:die("SBOM JSON required")
    op=cmd.removeprefix("sbom-");d=loadj(a[0])
    cdx=d.get("bomFormat")=="CycloneDX";spdx=("spdxVersion" in d or "SPDXID" in d)
    if op=="format-detect":print("cyclonedx" if cdx else "spdx" if spdx else "unknown");return
    if op.startswith("cdx-"):
        if op=="cdx-version":emit(d.get("specVersion"));return
        if op=="cdx-components":emit(d.get("components",[]));return
        if op=="cdx-services":emit(d.get("services",[]));return
        if op=="cdx-dependencies":emit(d.get("dependencies",[]));return
        if op=="cdx-licenses":emit(licenses_from_cdx(d));return
        if op=="cdx-purls":emit([x.get("purl") for x in d.get("components",[]) if x.get("purl")]);return
        if op=="cdx-hashes":emit(cdx_hashes(d));return
        if op=="cdx-vulnerabilities":emit(d.get("vulnerabilities",[]));return
        if op=="cdx-serial":emit(d.get("serialNumber"));return
        if op=="cdx-metadata":emit(d.get("metadata",{}));return
    if op.startswith("spdx-"):
        if op=="spdx-version":emit(d.get("spdxVersion"));return
        if op=="spdx-packages":emit(d.get("packages",[]));return
        if op=="spdx-files":emit(d.get("files",[]));return
        if op=="spdx-relationships":emit(d.get("relationships",[]));return
        if op=="spdx-licenses":emit(spdx_licenses(d));return
        if op=="spdx-external-refs":emit(sum((x.get("externalRefs",[]) for x in d.get("packages",[])),[]));return
        if op=="spdx-checksums":emit(sum((x.get("checksums",[]) for x in d.get("packages",[])+d.get("files",[])),[]));return
        if op=="spdx-creators":emit(d.get("creationInfo",{}).get("creators",[]));return
        if op=="spdx-document-name":emit(d.get("name"));return
        if op=="spdx-namespace":emit(d.get("documentNamespace"));return
    if op=="component-count":
        print(len(d.get("components",[])) if cdx else len(d.get("packages",[])) if spdx else 0);return
    if op=="license-summary":
        vals=licenses_from_cdx(d) if cdx else spdx_licenses(d);emit(Counter(vals));return
    if op=="hash-summary":
        vals=cdx_hashes(d) if cdx else sum((x.get("checksums",[]) for x in d.get("packages",[])+d.get("files",[])),[])
        algos=[]
        for x in vals:
            if isinstance(x,dict):algos.append(x.get("alg") or x.get("algorithm"))
        emit(Counter(x for x in algos if x));return
    if op=="purl-domains":
        purls=[x.get("purl") for x in d.get("components",[]) if x.get("purl")]
        emit(Counter(x.split(":",1)[1].split("/",1)[0] for x in purls if x.startswith("pkg:")));return

def decode_dsse(d):
    payload=d.get("payload","")
    try:return json.loads(base64.b64decode(payload+"="*((4-len(payload)%4)%4)))
    except:return None

def attest(cmd,a):
    if not a:die("attestation JSON required")
    op=cmd.removeprefix("attest-");d=loadj(a[0]);payload=decode_dsse(d) if "payload" in d else d
    if op=="dsse-envelope":emit({"payloadType":d.get("payloadType"),"signatures":len(d.get("signatures",[])),"hasPayload":"payload" in d});return
    if op=="dsse-payload-type":emit(d.get("payloadType"));return
    if op=="dsse-signatures":emit(d.get("signatures",[]));return
    if not isinstance(payload,dict):payload={}
    if op=="intoto-statement":emit(payload);return
    if op=="intoto-subjects":emit(payload.get("subject",[]));return
    if op=="intoto-predicate-type":emit(payload.get("predicateType"));return
    pred=payload.get("predicate",{}) if isinstance(payload.get("predicate"),dict) else {}
    if op=="slsa-builder":emit(pred.get("builder") or pred.get("runDetails",{}).get("builder"));return
    if op=="slsa-build-type":emit(pred.get("buildType") or pred.get("buildDefinition",{}).get("buildType"));return
    if op=="slsa-materials":emit(pred.get("materials") or pred.get("buildDefinition",{}).get("resolvedDependencies",[]));return
    if op=="slsa-invocation":emit(pred.get("invocation") or pred.get("buildDefinition",{}).get("externalParameters",{}));return
    if op=="subject-digests":emit([x.get("digest",{}) for x in payload.get("subject",[])]);return
    if op=="summary":
        emit({"payloadType":d.get("payloadType"),"statementType":payload.get("_type"),"predicateType":payload.get("predicateType"),"subjects":len(payload.get("subject",[])),"signatures":len(d.get("signatures",[]))});return

def main():
    cmd=P(sys.argv[0]).name;a=sys.argv[1:]
    if cmd not in COMMANDS:
        if a and a[0] in COMMANDS:cmd=a.pop(0)
        elif not a or a[0] in ("-h","--help"):
            print("Shard 29 — OCI 1.1, SBOM and attestation utilities");print("\n".join(COMMANDS));return
        else:die("unknown command")
    if a and a[0] in ("-h","--help"):print(cmd+" — functional shard 29 utility");return
    if cmd in OCI:oci(cmd,a)
    elif cmd in SBOM:sbom(cmd,a)
    else:attest(cmd,a)
if __name__=="__main__":main()
