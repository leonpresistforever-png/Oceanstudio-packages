#!/usr/bin/env python3
import base64,hashlib,importlib.util,json,os,struct,subprocess,sys,tempfile
from pathlib import Path
R28=Path(sys.argv[1]).resolve();R29=Path(sys.argv[2]).resolve();R30=Path(sys.argv[3]).resolve()

def load(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m28=load(R28,"s28");m29=load(R29,"s29");m30=load(R30,"s30")
assert len(m28.COMMANDS)==67 and len(set(m28.COMMANDS))==67
assert len(m29.COMMANDS)==67 and len(set(m29.COMMANDS))==67
assert len(m30.COMMANDS)==66 and len(set(m30.COMMANDS))==66
all_names=m28.COMMANDS+m29.COMMANDS+m30.COMMANDS
assert len(all_names)==200 and len(set(all_names))==200

RUNTIME={**{x:R28 for x in m28.COMMANDS},**{x:R29 for x in m29.COMMANDS},**{x:R30 for x in m30.COMMANDS}}
def run(cmd,*args,binary=False):
    p=subprocess.run([sys.executable,str(RUNTIME[cmd]),cmd,*map(str,args)],capture_output=True,text=not binary)
    if p.returncode:
        raise AssertionError(f"{cmd} rc={p.returncode}\nstdout={p.stdout}\nstderr={p.stderr}")
    return p.stdout

# Every package must dispatch to a registered real command.
for cmd in all_names:
    assert cmd in run(cmd,"--help")

def uleb(n):
    b=bytearray()
    while True:
        x=n&0x7f;n>>=7
        b.append(x|(0x80 if n else 0))
        if not n:return bytes(b)
def sec(i,p):return bytes([i])+uleb(len(p))+p
def nm(s):
    b=s.encode();return uleb(len(b))+b

with tempfile.TemporaryDirectory() as td:
    d=Path(td)

    # Shard 28: a real core Wasm module plus current-style WIT/component fixtures.
    wasm=d/"demo.wasm"
    typ=uleb(1)+b"\x60\x00\x00"
    imp=uleb(1)+nm("env")+nm("f")+b"\x00"+uleb(0)
    table=uleb(1)+b"\x70"+uleb(1)+uleb(1)+uleb(1)
    mem=uleb(1)+uleb(1)+uleb(1)+uleb(2)
    fun=uleb(1)+uleb(0)
    exp=uleb(1)+nm("run")+b"\x00"+uleb(0)
    code=uleb(1)+uleb(2)+b"\x00\x0b"
    custom=nm("name")
    wasm.write_bytes(b"\x00asm\x01\x00\x00\x00"+sec(0,custom)+sec(1,typ)+sec(2,imp)+sec(3,fun)+sec(4,table)+sec(5,mem)+sec(7,exp)+sec(10,code))
    assert json.loads(run("wasm-magic-check",wasm))["valid"] is True
    assert run("wasm-import-count",wasm).strip()=="1"
    assert "env" in json.loads(run("wasm-import-modules",wasm))
    assert "run" in json.loads(run("wasm-export-names",wasm))
    assert json.loads(run("wasm-memory-limits",wasm))[0]["max"]==2
    assert json.loads(run("wasm-component-detect",wasm))["component"] is False
    assert json.loads(run("wasm-validate-basic",wasm))["sections_parse"] is True
    assert json.loads(run("wasm-leb128-u32","ac02"))["value"]==300

    component=d/"c.wasm";component.write_bytes(b"\x00asm\x0d\x00\x01\x00")
    assert json.loads(run("wasm-component-detect",component))["component"] is True
    assert json.loads(run("component-section-list",component))==[]

    wit=d/"demo.wit"
    wit.write_text("""package ocean:demo@0.1.0;
use wasi:http/types@0.3.1;
interface api {
  record item { id: u32 }
  variant state { ready, wait }
  resource handle;
  enum mode { a, b }
  flags perms { read, write }
  type id = u64;
  fetch: async func() -> future<string>;
  bytes: func() -> stream<u8>;
}
world app { import api; }
""")
    assert run("wit-package-name",wit).strip()=="ocean:demo@0.1.0"
    assert "api" in json.loads(run("wit-interfaces",wit))
    assert "fetch" in json.loads(run("wit-async-functions",wit))
    assert json.loads(run("wasi-preview3-hints",wit))["detected"] is True
    assert "wasi:http/types@0.3.1" in json.loads(run("wasi-version-hints",wit))

    # Shard 29: actual OCI layout with manifest/config blobs.
    oci=d/"oci";(oci/"blobs/sha256").mkdir(parents=True)
    cfg={"architecture":"arm64","os":"linux","config":{"Env":["A=1"],"Entrypoint":["/bin/app"],"Cmd":["--serve"],"Labels":{"x":"y"}},"rootfs":{"type":"layers","diff_ids":["sha256:"+"1"*64]},"history":[{"created_by":"test"}]}
    cfgraw=json.dumps(cfg,separators=(",",":")).encode();cfgdig="sha256:"+hashlib.sha256(cfgraw).hexdigest();(oci/"blobs/sha256"/cfgdig.split(":")[1]).write_bytes(cfgraw)
    layer=b"layer";ldig="sha256:"+hashlib.sha256(layer).hexdigest();(oci/"blobs/sha256"/ldig.split(":")[1]).write_bytes(layer)
    man={"schemaVersion":2,"mediaType":"application/vnd.oci.image.manifest.v1+json","config":{"mediaType":"application/vnd.oci.image.config.v1+json","digest":cfgdig,"size":len(cfgraw)},"layers":[{"mediaType":"application/vnd.oci.image.layer.v1.tar","digest":ldig,"size":len(layer)}],"annotations":{"org.opencontainers.image.title":"demo"}}
    manraw=json.dumps(man,separators=(",",":")).encode();mandig="sha256:"+hashlib.sha256(manraw).hexdigest();(oci/"blobs/sha256"/mandig.split(":")[1]).write_bytes(manraw)
    idx={"schemaVersion":2,"mediaType":"application/vnd.oci.image.index.v1+json","manifests":[{"mediaType":man["mediaType"],"digest":mandig,"size":len(manraw),"platform":{"architecture":"arm64","os":"linux"}}]}
    (oci/"index.json").write_text(json.dumps(idx));(oci/"oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}')
    assert json.loads(run("oci-layout-check",oci))["valid_basic"] is True
    assert json.loads(run("oci-index-platforms",oci))[0]["architecture"]=="arm64"
    assert json.loads(run("oci-digest-check",oci))["valid"] is True
    assert json.loads(run("oci-missing-blobs",oci))==[]
    assert "application/vnd.oci.image.manifest.v1+json" in json.loads(run("oci-media-types",oci))
    manf=d/"manifest.json";manf.write_text(json.dumps(man))
    assert json.loads(run("oci-manifest-config",manf))["digest"]==cfgdig
    cfgf=d/"config.json";cfgf.write_text(json.dumps(cfg))
    assert json.loads(run("oci-config-env",cfgf))==["A=1"]

    cdx=d/"cdx.json";cdx.write_text(json.dumps({"bomFormat":"CycloneDX","specVersion":"1.7","serialNumber":"urn:uuid:00000000-0000-4000-8000-000000000000","metadata":{"component":{"name":"app"}},"components":[{"name":"lib","purl":"pkg:pypi/lib@1","licenses":[{"license":{"id":"MIT"}}],"hashes":[{"alg":"SHA-256","content":"abc"}]}],"dependencies":[{"ref":"app","dependsOn":["lib"]}]}))
    assert run("sbom-format-detect",cdx).strip()=="cyclonedx"
    assert run("sbom-cdx-version",cdx).strip().strip('"')=="1.7"
    assert run("sbom-component-count",cdx).strip()=="1"
    assert json.loads(run("sbom-license-summary",cdx))["MIT"]==1

    spdx=d/"spdx.json";spdx.write_text(json.dumps({"spdxVersion":"SPDX-2.3","SPDXID":"SPDXRef-DOCUMENT","name":"demo","documentNamespace":"https://example.test/spdx","creationInfo":{"creators":["Tool: Ocean"]},"packages":[{"name":"lib","SPDXID":"SPDXRef-lib","licenseDeclared":"MIT","checksums":[{"algorithm":"SHA256","checksumValue":"abc"}]}],"relationships":[]}))
    assert run("sbom-format-detect",spdx).strip()=="spdx"
    assert "SPDX-2.3" in run("sbom-spdx-version",spdx)

    statement={"_type":"https://in-toto.io/Statement/v1","subject":[{"name":"artifact","digest":{"sha256":"abc"}}],"predicateType":"https://slsa.dev/provenance/v1","predicate":{"buildDefinition":{"buildType":"https://example/build","externalParameters":{"target":"app"},"resolvedDependencies":[{"uri":"git+https://example/repo"}]},"runDetails":{"builder":{"id":"ocean-builder"}}}}
    env={"payloadType":"application/vnd.in-toto+json","payload":base64.b64encode(json.dumps(statement).encode()).decode(),"signatures":[{"keyid":"k","sig":"x"}]}
    att=d/"att.json";att.write_text(json.dumps(env))
    assert json.loads(run("attest-dsse-envelope",att))["signatures"]==1
    assert "slsa.dev/provenance" in run("attest-intoto-predicate-type",att)
    assert "ocean-builder" in run("attest-slsa-builder",att)

    # Shard 30: MCP 2026 structures.
    mcp=d/"mcp.json"
    mcp.write_text(json.dumps([
      {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2026-07-28","capabilities":{"tools":{},"extensions":{"io.modelcontextprotocol/tasks":{}}},"serverInfo":{"name":"Ocean","version":"1"},"tools":[{"name":"echo","inputSchema":{"type":"object"}}],"resources":[{"uri":"file:///a"}],"prompts":[{"name":"hello"}]}},
      {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"echo","arguments":{"x":1}}},
      {"jsonrpc":"2.0","id":3,"result":{"resultType":"task","taskId":"t1","status":"working","content":[{"type":"text","text":"running"}]}},
      {"jsonrpc":"2.0","method":"notifications/progress","params":{"progressToken":"p","progress":1}}
    ]))
    assert json.loads(run("mcp-jsonrpc-validate",mcp))["valid"] is True
    assert "2026-07-28" in json.loads(run("mcp-protocol-version",mcp))
    assert "echo" in json.loads(run("mcp-tool-names",mcp))
    assert json.loads(run("mcp-task-detect",mcp))["detected"] is True
    assert "t1" in json.loads(run("mcp-task-id",mcp))
    assert json.loads(run("mcp-content-types",mcp))["text"]>=1

    # Minimal GGUF v3 fixture.
    def gs(s):
        b=s.encode();return struct.pack("<Q",len(b))+b
    kv=[]
    for k,v in [("general.architecture","llama"),("general.name","Ocean Tiny")]:
        kv.append(gs(k)+struct.pack("<I",8)+gs(v))
    kv.append(gs("general.alignment")+struct.pack("<I",4)+struct.pack("<I",32))
    tensor=gs("weight")+struct.pack("<I",2)+struct.pack("<Q",2)+struct.pack("<Q",2)+struct.pack("<I",0)+struct.pack("<Q",0)
    header=b"GGUF"+struct.pack("<IQQ",3,1,len(kv))+b"".join(kv)+tensor
    aligned=(len(header)+31)//32*32
    gg=d/"m.gguf";gg.write_bytes(header+b"\0"*(aligned-len(header))+b"\x01\x02\x03\x04")
    assert run("gguf-version",gg).strip()=="3"
    assert run("gguf-tensor-count",gg).strip()=="1"
    assert json.loads(run("gguf-metadata-summary",gg))["general.architecture"]=="llama"
    assert "weight" in json.loads(run("gguf-tensor-names",gg))
    assert run("gguf-data-offset",gg).strip()==str(aligned)

    # Safetensors fixture with contiguous tensor ranges.
    sh={"a":{"dtype":"F32","shape":[1],"data_offsets":[0,4]},"b":{"dtype":"U8","shape":[2],"data_offsets":[4,6]},"__metadata__":{"format":"pt"}}
    hb=json.dumps(sh,separators=(",",":")).encode();sf=d/"m.safetensors";sf.write_bytes(struct.pack("<Q",len(hb))+hb+b"\x00"*6)
    assert run("safetensors-tensor-count",sf).strip()=="2"
    assert json.loads(run("safetensors-gap-check",sf))["has_gaps"] is False
    assert json.loads(run("safetensors-overlap-check",sf))["has_overlaps"] is False
    assert json.loads(run("safetensors-range-check",sf))["valid"] is True
    assert json.loads(run("safetensors-metadata",sf))["format"]=="pt"

print("PASS: shards 28/29/30 register 200 unique commands and representative WASM/WASI, OCI/SBOM/attestation, MCP/GGUF/Safetensors behavior works")
