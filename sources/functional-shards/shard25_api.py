#!/usr/bin/env python3
from __future__ import annotations

import base64, copy, datetime as dt, hashlib, hmac, json, os, re, shutil, subprocess, sys, urllib.parse, uuid
from email.utils import parsedate_to_datetime
from pathlib import Path
import xml.etree.ElementTree as ET

VERSION="2.0.0"

def die(msg,code=2): print(msg,file=sys.stderr); raise SystemExit(code)
def out(v): print(json.dumps(v,indent=2,ensure_ascii=False,default=str) if isinstance(v,(dict,list,tuple)) else v)
def read_text(path=None): return Path(path).read_text(encoding="utf-8",errors="replace") if path and path!="-" else sys.stdin.read()
def read_json(path=None): return json.loads(read_text(path))
def scalar(s):
    try:return json.loads(s)
    except Exception:return s
def pointer_parts(ptr):
    if ptr=="": return []
    if not ptr.startswith("/"): die("JSON Pointer must start with /")
    return [x.replace("~1","/").replace("~0","~") for x in ptr[1:].split("/")]
def ptr_get(doc,ptr):
    cur=doc
    for p in pointer_parts(ptr):
        cur=cur[int(p)] if isinstance(cur,list) else cur[p]
    return cur
def ptr_parent(doc,ptr,create=False):
    ps=pointer_parts(ptr)
    if not ps: return None,None
    cur=doc
    for p in ps[:-1]:
        if isinstance(cur,list): cur=cur[int(p)]
        else:
            if create: cur=cur.setdefault(p,{})
            else: cur=cur[p]
    return cur,ps[-1]

def basic_spec_errors(spec,kind="openapi"):
    e=[]
    if not isinstance(spec,dict): return ["document must be an object"]
    if kind=="openapi":
        ver=spec.get("openapi")
        if not isinstance(ver,str) or not re.match(r"^3\.(0|1)\.",ver): e.append("openapi must be a 3.0.x or 3.1.x version string")
        if not isinstance(spec.get("info"),dict): e.append("info object missing")
        else:
            if not spec["info"].get("title"): e.append("info.title missing")
            if not spec["info"].get("version"): e.append("info.version missing")
        if not isinstance(spec.get("paths"),dict): e.append("paths object missing")
    elif kind=="asyncapi":
        if not re.match(r"^2\.",str(spec.get("asyncapi",""))): e.append("asyncapi 2.x version missing")
        if not isinstance(spec.get("info"),dict): e.append("info object missing")
        if not isinstance(spec.get("channels"),dict): e.append("channels object missing")
    return e

def openapi_v3_spec_linter(args):
    s=read_json(args[0] if args else None); errors=basic_spec_errors(s); warnings=[]
    for path,item in (s.get("paths") or {}).items():
        if not str(path).startswith("/"): errors.append(f"path does not start with /: {path}")
        if not isinstance(item,dict): errors.append(f"path item must be object: {path}"); continue
        for method,op in item.items():
            if method.lower() in {"get","put","post","delete","patch","options","head","trace"}:
                if not isinstance(op,dict): errors.append(f"{method.upper()} {path} must be object")
                elif "responses" not in op: warnings.append(f"{method.upper()} {path} has no responses")
    out({"valid":not errors,"errors":errors,"warnings":warnings})

def collect_params(path_item,op):
    rows=[]
    for x in (path_item.get("parameters",[]) if isinstance(path_item,dict) else [])+(op.get("parameters",[]) if isinstance(op,dict) else []):
        if isinstance(x,dict): rows.append(x)
    return rows

def openapi_path_param_chk(args):
    s=read_json(args[0] if args else None); errors=[]; details=[]
    for path,item in (s.get("paths") or {}).items():
        templ=set(re.findall(r"\{([^{}]+)\}",path))
        for method,op in item.items() if isinstance(item,dict) else []:
            if method.lower() not in {"get","put","post","delete","patch","options","head","trace"} or not isinstance(op,dict): continue
            defs={p.get("name") for p in collect_params(item,op) if p.get("in")=="path"}
            missing=sorted(templ-defs); extra=sorted(defs-templ)
            required_false=sorted(p.get("name") for p in collect_params(item,op) if p.get("in")=="path" and p.get("required") is not True)
            if missing or extra or required_false: errors.append({"method":method,"path":path,"missing":missing,"extra":extra,"not_required_true":required_false})
            details.append({"method":method,"path":path,"template":sorted(templ),"defined":sorted(x for x in defs if x)})
    out({"valid":not errors,"errors":errors,"operations":details})

def resolve_refs(obj,root,seen=None):
    if seen is None: seen=set()
    if isinstance(obj,dict) and set(obj)=={"$ref"} and isinstance(obj["$ref"],str) and obj["$ref"].startswith("#"):
        ref=obj["$ref"]; 
        if ref in seen: return {"$ref":ref,"$cycle":True}
        target=ptr_get(root,ref[1:])
        return resolve_refs(copy.deepcopy(target),root,seen|{ref})
    if isinstance(obj,dict): return {k:resolve_refs(v,root,seen) for k,v in obj.items()}
    if isinstance(obj,list): return [resolve_refs(v,root,seen) for v in obj]
    return obj

def openapi_schema_resolver(args):
    if len(args)<2: die("usage: openapi-schema-resolver SPEC.json JSON_POINTER_OR_REF")
    s=read_json(args[0]); ref=args[1]
    target=ptr_get(s,ref[1:] if ref.startswith("#") else ref)
    out(resolve_refs(copy.deepcopy(target),s))

def swagger_v2_converter(args):
    s=read_json(args[0] if args else None)
    if str(s.get("swagger"))!="2.0": die("input is not Swagger 2.0")
    o={"openapi":"3.0.3","info":s.get("info",{}),"paths":copy.deepcopy(s.get("paths",{}))}
    schemes=s.get("schemes") or ["https"]; host=s.get("host"); base=s.get("basePath","")
    if host:o["servers"]=[{"url":f"{schemes[0]}://{host}{base}"}]
    comps={}
    if s.get("definitions"): comps["schemas"]=s["definitions"]
    if s.get("securityDefinitions"): comps["securitySchemes"]=s["securityDefinitions"]
    if comps:o["components"]=comps
    for path,item in o["paths"].items():
        if not isinstance(item,dict):continue
        for method,op in list(item.items()):
            if not isinstance(op,dict):continue
            consumes=op.pop("consumes",s.get("consumes",[])); produces=op.pop("produces",s.get("produces",[]))
            body=[p for p in op.get("parameters",[]) if isinstance(p,dict) and p.get("in")=="body"]
            op["parameters"]=[p for p in op.get("parameters",[]) if not (isinstance(p,dict) and p.get("in")=="body")]
            if body:
                schema=body[0].get("schema",{}); ctype=(consumes or ["application/json"])[0]
                op["requestBody"]={"required":body[0].get("required",False),"content":{ctype:{"schema":schema}}}
            for code,r in (op.get("responses") or {}).items():
                if isinstance(r,dict) and "schema" in r:
                    schema=r.pop("schema"); ctype=(produces or ["application/json"])[0]
                    r["content"]={ctype:{"schema":schema}}
    out(o)

def asyncapi_spec_validator(args):
    s=read_json(args[0] if args else None); errors=basic_spec_errors(s,"asyncapi")
    for name,ch in (s.get("channels") or {}).items():
        if not isinstance(ch,dict): errors.append(f"channel {name} must be object")
        elif not any(k in ch for k in ("publish","subscribe")): errors.append(f"channel {name} has neither publish nor subscribe")
    out({"valid":not errors,"errors":errors})

def graphql_schema_parser(args):
    text=read_text(args[0] if args else None)
    types=[]
    for m in re.finditer(r"\b(type|interface|input|enum|scalar|union)\s+([_A-Za-z][_0-9A-Za-z]*)",text):
        kind,name=m.groups(); types.append({"kind":kind,"name":name})
    fields={}
    for m in re.finditer(r"\btype\s+([_A-Za-z]\w*)[^{]*\{([^}]*)\}",text,re.S):
        fields[m.group(1)]=[x.group(1) for x in re.finditer(r"^\s*([_A-Za-z]\w*)\s*(?:\([^)]*\))?\s*:",m.group(2),re.M)]
    out({"types":types,"fields":fields,"type_count":len(types)})

def graphql_query_linter(args):
    text=read_text(args[0] if args else None); errors=[]
    stack=[]; depth=0; maxdepth=0; in_string=False; esc=False
    for i,ch in enumerate(text):
        if in_string:
            if esc:esc=False
            elif ch=="\\":esc=True
            elif ch=='"':in_string=False
            continue
        if ch=='"':in_string=True;continue
        if ch in "{([": stack.append(ch); depth+=ch=="{"; maxdepth=max(maxdepth,depth)
        elif ch in "})]":
            pairs={"}":"{",")":"(","]":"["}
            if not stack or stack.pop()!=pairs[ch]: errors.append(f"unbalanced delimiter at offset {i}")
            if ch=="}": depth=max(0,depth-1)
    if stack: errors.append("unclosed delimiters")
    ops=re.findall(r"\b(query|mutation|subscription)\s+([_A-Za-z]\w*)",text)
    out({"valid":not errors,"errors":errors,"max_selection_depth":maxdepth,"operations":[{"kind":a,"name":b} for a,b in ops]})

def graphql_introspection_chk(args):
    d=read_json(args[0] if args else None); schema=(d.get("data") or d).get("__schema") if isinstance(d,dict) else None
    if not isinstance(schema,dict): out({"valid":False,"error":"__schema missing"}); return
    types=schema.get("types") or []; out({"valid":True,"queryType":schema.get("queryType"),"mutationType":schema.get("mutationType"),"type_count":len(types),"types":[x.get("name") for x in types if isinstance(x,dict)]})

def proto_fields(text):
    return [(m.group(1),m.group(2),int(m.group(3))) for m in re.finditer(r"^\s*(?:optional\s+|repeated\s+)?([.\w<>]+)\s+(\w+)\s*=\s*(\d+)",text,re.M)]
def protobuf_proto3_linter(args):
    text=read_text(args[0] if args else None); errors=[]; warnings=[]
    if not re.search(r'^\s*syntax\s*=\s*"proto3"\s*;',text,re.M): errors.append('missing syntax = "proto3";')
    seen=set()
    for typ,name,num in proto_fields(text):
        if not (1<=num<=536870911) or 19000<=num<=19999: errors.append(f"invalid/reserved field number {num} for {name}")
        if num in seen: errors.append(f"duplicate field number {num}")
        seen.add(num)
        if "_" not in name and re.search(r"[A-Z]",name): warnings.append(f"field {name} should use snake_case")
    out({"valid":not errors,"errors":errors,"warnings":warnings,"fields":len(seen)})
def protobuf_field_number_chk(args):
    vals=[int(x) for x in args] if args else [int(x) for x in re.findall(r"\d+",read_text())]
    out([{"number":n,"valid":1<=n<=536870911 and not 19000<=n<=19999,"reason":"reserved implementation range" if 19000<=n<=19999 else None} for n in vals])
def parse_reserved(text):
    nums=set(); names=set()
    for m in re.finditer(r"\breserved\s+([^;]+);",text):
        for p in m.group(1).split(","):
            p=p.strip()
            if p.startswith('"'): names.add(p.strip('"'))
            elif "to" in p:
                a,b=[x.strip() for x in p.split("to",1)]
                end=536870911 if b=="max" else int(b); nums.update(range(int(a),min(end,int(a)+100000)+1))
            elif p.isdigit():nums.add(int(p))
    return nums,names
def protobuf_reserved_ranges(args):
    text=read_text(args[0] if args else None); nums,names=parse_reserved(text); conflicts=[]
    for typ,name,num in proto_fields(text):
        if num in nums or name in names: conflicts.append({"field":name,"number":num})
    out({"valid":not conflicts,"conflicts":conflicts,"reserved_numbers_checked":len(nums),"reserved_names":sorted(names)})
def protobuf_deprecated_tag(args):
    text=read_text(args[0] if args else None); rows=[]
    for line_no,line in enumerate(text.splitlines(),1):
        if re.search(r"\[\s*deprecated\s*=\s*true\s*\]",line): rows.append({"line":line_no,"text":line.strip()})
    out({"count":len(rows),"fields":rows})

def read_varint(data,pos):
    v=0;shift=0
    while pos<len(data):
        b=data[pos];pos+=1;v|=(b&127)<<shift
        if not b&128:return v,pos
        shift+=7
    raise ValueError("truncated varint")
def proto_wire(data):
    pos=0; fields=[]
    while pos<len(data):
        tag,pos=read_varint(data,pos); num=tag>>3; wt=tag&7
        if wt==0:v,pos=read_varint(data,pos)
        elif wt==1:v=data[pos:pos+8];pos+=8
        elif wt==2:
            n,pos=read_varint(data,pos);v=data[pos:pos+n];pos+=n
        elif wt==5:v=data[pos:pos+4];pos+=4
        else: raise ValueError(f"unsupported wire type {wt}")
        fields.append((num,wt,v))
    return fields
def descriptor_services(blob):
    rows=[]
    for num,wt,filemsg in proto_wire(blob):
        if num!=1 or wt!=2:continue
        package=""; services=[]
        for fn,fw,fv in proto_wire(filemsg):
            if fn==2 and fw==2: package=fv.decode(errors="replace")
            if fn==6 and fw==2:
                name=""
                for sn,sw,sv in proto_wire(fv):
                    if sn==1 and sw==2:name=sv.decode(errors="replace")
                if name:services.append(name)
        rows.extend(f"{package}.{s}".strip(".") for s in services)
    return rows
def grpc_reflection_client(args):
    if args and args[0]=="--descriptor-set":
        blob=Path(args[1]).read_bytes();out({"mode":"descriptor-set","services":descriptor_services(blob)});return
    if not args:die("usage: grpc-reflection-client HOST:PORT | --descriptor-set FILE")
    grpcurl=shutil.which("grpcurl")
    if not grpcurl: out({"supported":False,"host":args[0],"reason":"grpcurl is not installed; use --descriptor-set for offline service listing"});return
    r=subprocess.run([grpcurl,"-plaintext",args[0],"list"],capture_output=True,text=True)
    out({"supported":True,"host":args[0],"returncode":r.returncode,"services":r.stdout.splitlines(),"stderr":r.stderr.strip()})

def type_matches(v,t):
    return {"object":isinstance(v,dict),"array":isinstance(v,list),"string":isinstance(v,str),"number":isinstance(v,(int,float)) and not isinstance(v,bool),"integer":isinstance(v,int) and not isinstance(v,bool),"boolean":isinstance(v,bool),"null":v is None}.get(t,True)
def schema_validate(inst,schema,path="$"):
    e=[]
    if not isinstance(schema,dict):return e
    t=schema.get("type")
    if isinstance(t,str) and not type_matches(inst,t): return [f"{path}: expected {t}"]
    if "const" in schema and inst!=schema["const"]:e.append(f"{path}: does not equal const")
    if "enum" in schema and inst not in schema["enum"]:e.append(f"{path}: not in enum")
    if isinstance(inst,dict):
        for req in schema.get("required",[]): 
            if req not in inst:e.append(f"{path}: missing required property {req}")
        props=schema.get("properties",{})
        for k,v in inst.items():
            if k in props:e+=schema_validate(v,props[k],f"{path}.{k}")
        if schema.get("additionalProperties") is False:
            for k in inst:
                if k not in props:e.append(f"{path}: additional property {k}")
    if isinstance(inst,list) and isinstance(schema.get("items"),dict):
        for i,v in enumerate(inst):e+=schema_validate(v,schema["items"],f"{path}[{i}]")
    if isinstance(inst,str):
        if "minLength" in schema and len(inst)<schema["minLength"]:e.append(f"{path}: shorter than minLength")
        if "maxLength" in schema and len(inst)>schema["maxLength"]:e.append(f"{path}: longer than maxLength")
        if "pattern" in schema and re.search(schema["pattern"],inst) is None:e.append(f"{path}: pattern mismatch")
    if isinstance(inst,(int,float)) and not isinstance(inst,bool):
        if "minimum" in schema and inst<schema["minimum"]:e.append(f"{path}: below minimum")
        if "maximum" in schema and inst>schema["maximum"]:e.append(f"{path}: above maximum")
    return e
def json_schema_runner(args,draft):
    if len(args)<2:die("usage: validator SCHEMA.json INSTANCE.json")
    s=read_json(args[0]); inst=read_json(args[1]); errors=schema_validate(inst,s)
    declared=s.get("$schema")
    warning=None
    if draft=="draft7" and declared and "draft-07" not in declared:warning=f"schema declares {declared}"
    if draft=="2020-12" and declared and "2020-12" not in declared:warning=f"schema declares {declared}"
    out({"valid":not errors,"errors":errors,"draft":draft,"warning":warning})

def json_patch_rfc6902_run(args):
    if len(args)<2:die("usage: json-patch-rfc6902-run DOCUMENT.json PATCH.json")
    doc=read_json(args[0]); ops=read_json(args[1])
    for op in ops:
        typ=op["op"]; path=op["path"]
        if typ=="test":
            if ptr_get(doc,path)!=op.get("value"):die(f"test failed at {path}",1)
            continue
        if typ in ("copy","move"):
            val=copy.deepcopy(ptr_get(doc,op["from"]))
            if typ=="move":
                par,key=ptr_parent(doc,op["from"]); par.pop(int(key)) if isinstance(par,list) else par.pop(key)
        elif typ in ("add","replace"):val=copy.deepcopy(op.get("value"))
        elif typ=="remove":val=None
        else:die(f"unsupported op {typ}")
        par,key=ptr_parent(doc,path,create=typ=="add")
        if par is None:
            if typ in ("add","replace","copy","move"):doc=val
            elif typ=="remove":doc=None
        elif typ=="remove":par.pop(int(key)) if isinstance(par,list) else par.pop(key)
        elif isinstance(par,list):
            if key=="-":par.append(val)
            elif typ=="add":par.insert(int(key),val)
            else:par[int(key)]=val
        else:par[key]=val
    out(doc)
def merge_patch(target,patch):
    if not isinstance(patch,dict):return copy.deepcopy(patch)
    if not isinstance(target,dict):target={}
    target=copy.deepcopy(target)
    for k,v in patch.items():
        if v is None:target.pop(k,None)
        else:target[k]=merge_patch(target.get(k),v)
    return target
def json_merge_patch_rfc7386(args):
    if len(args)<2:die("usage: json-merge-patch-rfc7386 DOCUMENT.json PATCH.json")
    out(merge_patch(read_json(args[0]),read_json(args[1])))
def json_pointer_rfc6901_cli(args):
    if len(args)<2:die("usage: json-pointer-rfc6901-cli DOCUMENT.json POINTER")
    out(ptr_get(read_json(args[0]),args[1]))

STATUS={100:"Continue",101:"Switching Protocols",200:"OK",201:"Created",202:"Accepted",204:"No Content",206:"Partial Content",301:"Moved Permanently",302:"Found",304:"Not Modified",307:"Temporary Redirect",308:"Permanent Redirect",400:"Bad Request",401:"Unauthorized",403:"Forbidden",404:"Not Found",405:"Method Not Allowed",409:"Conflict",410:"Gone",412:"Precondition Failed",415:"Unsupported Media Type",422:"Unprocessable Content",429:"Too Many Requests",500:"Internal Server Error",502:"Bad Gateway",503:"Service Unavailable",504:"Gateway Timeout"}
def http_status_code_lookup(args):
    if not args:die("usage: http-status-code-lookup CODE")
    code=int(args[0]);out({"code":code,"reason":STATUS.get(code,"Unknown/Unlisted"),"class":f"{code//100}xx"})
def http_auth_bearer_token(args):
    raw=" ".join(args).strip()
    m=re.fullmatch(r"(?:Bearer\s+)?([A-Za-z0-9\-._~+/]+=*)",raw,re.I)
    token=m.group(1) if m else None
    out({"valid":token is not None,"scheme":"Bearer","token_length":len(token) if token else 0})
def http_basic_auth_encoder(args):
    if len(args)<2:die("usage: http-basic-auth-encoder USER PASSWORD")
    raw=f"{args[0]}:{args[1]}".encode();print("Basic "+base64.b64encode(raw).decode())
def oauth2_token_exchange(args):
    if args and Path(args[0]).exists():d=read_json(args[0])
    else:d=dict(x.split("=",1) for x in args if "=" in x)
    required=["subject_token","subject_token_type"]
    errors=[f"missing {x}" for x in required if not d.get(x)]
    gt=d.get("grant_type","urn:ietf:params:oauth:grant-type:token-exchange")
    if gt!="urn:ietf:params:oauth:grant-type:token-exchange":errors.append("invalid grant_type")
    out({"valid":not errors,"errors":errors,"normalized":{**d,"grant_type":gt}})
def oauth2_pkce_challenge(args):
    if not args:die("usage: oauth2-pkce-challenge CODE_VERIFIER")
    v=args[0]
    valid=43<=len(v)<=128 and re.fullmatch(r"[A-Za-z0-9\-._~]+",v) is not None
    challenge=base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
    out({"valid_verifier":valid,"code_challenge":challenge,"code_challenge_method":"S256"})
def oidc_discovery_parser(args):
    d=read_json(args[0] if args else None);req=["issuer","authorization_endpoint","token_endpoint","jwks_uri"];missing=[x for x in req if not d.get(x)]
    out({"valid":not missing,"missing":missing,"issuer":d.get("issuer"),"endpoints":{k:v for k,v in d.items() if k.endswith("_endpoint") or k=="jwks_uri"},"scopes_supported":d.get("scopes_supported",[])})
def xml_root(path=None):return ET.fromstring(read_text(path))
def local(tag):return tag.split("}",1)[-1]
def saml_assertion_xml_chk(args):
    r=xml_root(args[0] if args else None); errs=[]
    if local(r.tag)!="Assertion":errs.append("root is not Assertion")
    version=r.attrib.get("Version"); 
    if version!="2.0":errs.append("Version is not 2.0")
    issuer=next((x.text for x in r.iter() if local(x.tag)=="Issuer"),None)
    subject=next((x for x in r.iter() if local(x.tag)=="Subject"),None)
    cond=next((x for x in r.iter() if local(x.tag)=="Conditions"),None)
    sig=next((x for x in r.iter() if local(x.tag)=="Signature"),None)
    out({"valid":not errs,"errors":errs,"id":r.attrib.get("ID"),"issuer":issuer,"has_subject":subject is not None,"has_conditions":cond is not None,"has_signature":sig is not None})
def soap_envelope_parser(args):
    r=xml_root(args[0] if args else None); ns=r.tag.split("}")[0].strip("{") if "}" in r.tag else ""
    ver="1.2" if ns=="http://www.w3.org/2003/05/soap-envelope" else "1.1" if ns=="http://schemas.xmlsoap.org/soap/envelope/" else None
    body=next((x for x in r if local(x.tag)=="Body"),None)
    ops=[local(x.tag) for x in body] if body is not None else []
    out({"valid":local(r.tag)=="Envelope" and ver is not None and body is not None,"soap_version":ver,"body_operations":ops})
def wsdl_contract_inspector(args):
    r=xml_root(args[0] if args else None)
    elems=lambda n:[x for x in r.iter() if local(x.tag)==n]
    out({"root":local(r.tag),"targetNamespace":r.attrib.get("targetNamespace"),"services":[x.attrib.get("name") for x in elems("service")],"bindings":[x.attrib.get("name") for x in elems("binding")],"portTypes":[x.attrib.get("name") for x in elems("portType")],"operations":[x.attrib.get("name") for x in elems("operation")]})

def shape(v):
    if isinstance(v,dict):return {k:shape(x) for k,x in v.items()}
    if isinstance(v,list):return [shape(v[0])] if v else []
    return type(v).__name__
def shape_diff(a,b,path="$"):
    e=[]
    if type(a)!=type(b):return [{"path":path,"old_type":type(a).__name__,"new_type":type(b).__name__}]
    if isinstance(a,dict):
        for k in a.keys()-b.keys():e.append({"path":f"{path}.{k}","change":"removed"})
        for k in b.keys()-a.keys():e.append({"path":f"{path}.{k}","change":"added"})
        for k in a.keys()&b.keys():e+=shape_diff(a[k],b[k],f"{path}.{k}")
    elif isinstance(a,list) and a and b:e+=shape_diff(a[0],b[0],path+"[]")
    return e
def rest_api_response_diff(args):
    if len(args)<2:die("usage: rest-api-response-diff OLD.json NEW.json")
    a,b=read_json(args[0]),read_json(args[1]);d=shape_diff(a,b)
    out({"breaking_candidates":[x for x in d if x.get("change")=="removed" or "old_type" in x],"all_changes":d})
def api_curl_command_gen(args):
    if len(args)<3:die("usage: api-curl-command-gen SPEC.json METHOD PATH [BASE_URL]")
    s=read_json(args[0]);method=args[1].lower();path=args[2];op=(s.get("paths") or {}).get(path,{}).get(method)
    if not isinstance(op,dict):die("operation not found")
    base=args[3] if len(args)>3 else ((s.get("servers") or [{"url":"http://localhost"}])[0].get("url","http://localhost"))
    headers=["-H 'Accept: application/json'"]; body=""
    if "requestBody" in op:headers.append("-H 'Content-Type: application/json'");body=" -d '{}'"
    print(f"curl -X {method.upper()} {' '.join(headers)} '{base.rstrip('/')}{path}'{body}")
def schema_fuzz_values(s):
    vals=[]
    t=s.get("type")
    if t in ("integer","number"):
        if "minimum" in s:vals += [s["minimum"]-1,s["minimum"]]
        if "maximum" in s:vals += [s["maximum"],s["maximum"]+1]
        vals += [0,-1,1]
    elif t=="string":
        vals += ["","A","A"*max(1,int(s.get("maxLength",16))+1)]
        if s.get("format")=="email":vals += ["x","a@example.test"]
    elif t=="boolean":vals += [True,False]
    elif t=="array":vals += [[],[None]]
    elif t=="object":vals += [{},None]
    if "enum" in s:vals+=s["enum"][:3]
    return vals
def api_fuzz_parameter_gen(args):
    s=read_json(args[0] if args else None)
    props=s.get("properties",s) if isinstance(s,dict) else {}
    out({k:schema_fuzz_values(v) for k,v in props.items() if isinstance(v,dict)})
def api_rate_limit_header(args):
    d={}
    for x in args:
        if ":" in x:k,v=x.split(":",1);d[k.strip().lower()]=v.strip()
        elif "=" in x:k,v=x.split("=",1);d[k.strip().lower()]=v.strip()
    def first(*names):
        for n in names:
            if n in d:return d[n]
    out({"limit":first("ratelimit-limit","x-ratelimit-limit"),"remaining":first("ratelimit-remaining","x-ratelimit-remaining"),"reset":first("ratelimit-reset","x-ratelimit-reset"),"raw":d})
def etag_if_none_match_chk(args):
    if len(args)<2:die("usage: etag-if-none-match-chk ETAG IF_NONE_MATCH")
    etag=args[0]; vals=[x.strip() for x in args[1].split(",")]
    def weak(x):return x[2:] if x.startswith("W/") else x
    match="*" in vals or any(weak(x)==weak(etag) for x in vals)
    out({"matched":match,"response_status_if_get":304 if match else 200})
def cache_control_validator(args):
    s=" ".join(args); directives={}
    for p in s.split(","):
        p=p.strip()
        if not p:continue
        if "=" in p:k,v=p.split("=",1);directives[k.lower()]=v.strip('"')
        else:directives[p.lower()]=True
    errors=[]
    for k in ("max-age","s-maxage"):
        if k in directives:
            try:
                if int(directives[k])<0:errors.append(f"{k} must be non-negative")
            except:errors.append(f"{k} must be integer")
    if "no-store" in directives and ("max-age" in directives or "s-maxage" in directives):errors.append("no-store conflicts with cache freshness directives")
    out({"valid":not errors,"errors":errors,"directives":directives})
def content_security_policy(args):
    s=" ".join(args);dirs={}
    for part in s.split(";"):
        toks=part.strip().split()
        if toks:dirs[toks[0].lower()]=toks[1:]
    warnings=[];known={"default-src","script-src","style-src","img-src","connect-src","font-src","object-src","frame-src","child-src","base-uri","form-action","frame-ancestors","media-src","worker-src","manifest-src","upgrade-insecure-requests","block-all-mixed-content","report-uri","report-to"}
    for d in dirs:
        if d not in known:warnings.append(f"unknown directive {d}")
    if "'unsafe-inline'" in dirs.get("script-src",[]):warnings.append("script-src allows unsafe-inline")
    if "*" in dirs.get("default-src",[]):warnings.append("default-src allows wildcard")
    out({"valid":True,"directives":dirs,"warnings":warnings})
def enum_header(args,valid,name):
    v=" ".join(args).strip()
    out({"header":name,"value":v,"valid":v in valid,"allowed":sorted(valid)})
def cross_origin_embedder(args):enum_header(args,{"unsafe-none","require-corp","credentialless"},"Cross-Origin-Embedder-Policy")
def cross_origin_resource(args):enum_header(args,{"same-site","same-origin","cross-origin"},"Cross-Origin-Resource-Policy")
def referrer_policy_checker(args):enum_header(args,{"no-referrer","no-referrer-when-downgrade","origin","origin-when-cross-origin","same-origin","strict-origin","strict-origin-when-cross-origin","unsafe-url"},"Referrer-Policy")
def hsts_preload_eligibility(args):
    s=" ".join(args).lower();d={}
    for x in s.split(";"):
        p=x.strip()
        if "=" in p:k,v=p.split("=",1);d[k]=v
        elif p:d[p]=True
    try:age=int(d.get("max-age","0"))
    except:age=0
    errors=[]
    if age<31536000:errors.append("max-age must be at least 31536000")
    if "includesubdomains" not in d:errors.append("includeSubDomains missing")
    if "preload" not in d:errors.append("preload token missing")
    out({"eligible_header":not errors,"errors":errors,"directives":d})
def expect_ct_header_chk(args):
    s=" ".join(args);d={}
    for p in s.split(","):
        p=p.strip()
        if "=" in p:k,v=p.split("=",1);d[k.lower()]=v.strip('"')
        elif p:d[p.lower()]=True
    errs=[]
    if "max-age" in d:
        try:int(d["max-age"])
        except:errs.append("max-age must be integer")
    out({"valid":not errs,"errors":errs,"directives":d,"note":"Expect-CT is obsolete in modern browsers; parser retained for legacy diagnostics"})
def feature_policy_analyzer(args):
    s=" ".join(args);features={}
    for part in s.split(";"):
        p=part.strip()
        if not p:continue
        if "=" in p:k,v=p.split("=",1)
        else:
            toks=p.split();k=toks[0];v=" ".join(toks[1:])
        features[k.strip()]=v.strip()
    out({"features":features,"count":len(features)})
def permissions_policy_fmt(args):
    s=" ".join(args);rows=[]
    for part in s.split(","):
        p=part.strip()
        if not p:continue
        if "=" not in p:rows.append((p,"()"));continue
        k,v=p.split("=",1);v=v.strip();rows.append((k.strip(),v))
    print(", ".join(f"{k}={v}" for k,v in sorted(rows)))
def webhook_delivery_retry(args):
    if len(args)<2:die("usage: webhook-delivery-retry ATTEMPTS BASE_SECONDS [MAX_SECONDS]")
    n=int(args[0]);base=float(args[1]);mx=float(args[2]) if len(args)>2 else 3600
    now=dt.datetime.now(dt.timezone.utc);rows=[];elapsed=0
    for i in range(n):
        delay=min(mx,base*(2**i));elapsed+=delay;rows.append({"attempt":i+1,"delay_seconds":delay,"at":(now+dt.timedelta(seconds=elapsed)).isoformat()})
    out(rows)
def hmac_webhook_verifier(args):
    if len(args)<2:die("usage: hmac-webhook-verifier SECRET EXPECTED_SIGNATURE [FILE]")
    secret=args[0].encode();sig=args[1];data=Path(args[2]).read_bytes() if len(args)>2 else sys.stdin.buffer.read()
    got=hmac.new(secret,data,hashlib.sha256).hexdigest()
    normalized=sig.split("=",1)[-1] if "=" in sig else sig
    out({"valid":hmac.compare_digest(got.lower(),normalized.lower()),"computed":"sha256="+got})
def api_deprecation_sunset(args):
    d={}
    for x in args:
        if ":" in x:k,v=x.split(":",1);d[k.strip().lower()]=v.strip()
    sunset=d.get("sunset");dep=d.get("deprecation");parsed=None;seconds=None
    if sunset:
        try:parsed=parsedate_to_datetime(sunset);seconds=(parsed-dt.datetime.now(dt.timezone.utc)).total_seconds()
        except Exception:pass
    out({"deprecation":dep,"sunset":sunset,"sunset_utc":parsed.isoformat() if parsed else None,"seconds_until_sunset":seconds})
def pagination_link_header(args):
    s=" ".join(args);rows=[]
    for part in re.split(r",\s*(?=<)",s):
        m=re.match(r'\s*<([^>]+)>\s*(.*)',part)
        if not m:continue
        params={}
        for p in m.group(2).split(";"):
            p=p.strip()
            if "=" in p:k,v=p.split("=",1);params[k]=v.strip('"')
        rows.append({"url":m.group(1),"params":params})
    out({"links":rows,"by_rel":{r["params"].get("rel"):r["url"] for r in rows if r["params"].get("rel")}})
def cursor_based_pager_cli(args):
    if len(args)<2:die("usage: cursor-based-pager-cli encode VALUE | decode TOKEN")
    if args[0]=="encode":
        payload=json.dumps({"v":args[1]},separators=(",",":")).encode();print(base64.urlsafe_b64encode(payload).rstrip(b"=").decode())
    elif args[0]=="decode":
        token=args[1];raw=base64.urlsafe_b64decode(token+"="*((4-len(token)%4)%4));out(json.loads(raw))
    else:die("mode must be encode or decode")
def json_feed_validator_cli(args):
    d=read_json(args[0] if args else None);errors=[]
    if not str(d.get("version","")).startswith("https://jsonfeed.org/version/"):errors.append("invalid or missing version")
    if not d.get("title"):errors.append("title missing")
    if not isinstance(d.get("items"),list):errors.append("items must be array")
    else:
        for i,x in enumerate(d["items"]):
            if not isinstance(x,dict) or not x.get("id"):errors.append(f"items[{i}].id missing")
    out({"valid":not errors,"errors":errors,"items":len(d.get("items",[])) if isinstance(d.get("items"),list) else 0})
def rss2_feed_xml_checker(args):
    r=xml_root(args[0] if args else None);errors=[]
    if local(r.tag).lower()!="rss":errors.append("root is not rss")
    if r.attrib.get("version")!="2.0":errors.append("rss version is not 2.0")
    ch=next((x for x in r if local(x.tag)=="channel"),None)
    if ch is None:errors.append("channel missing")
    required={}
    if ch is not None:
        required={local(x.tag):x.text for x in ch}
        for k in ("title","link","description"):
            if not required.get(k):errors.append(f"channel {k} missing")
    out({"valid":not errors,"errors":errors,"items":sum(1 for x in ch if local(x.tag)=="item") if ch is not None else 0})
def atom_feed_xml_validator(args):
    r=xml_root(args[0] if args else None);errors=[]
    if local(r.tag)!="feed":errors.append("root is not feed")
    vals={local(x.tag):x.text for x in r}
    for k in ("id","title","updated"):
        if not vals.get(k):errors.append(f"{k} missing")
    out({"valid":not errors,"errors":errors,"entries":sum(1 for x in r if local(x.tag)=="entry")})
def sitemap_xml_inspector(args):
    r=xml_root(args[0] if args else None);kind=local(r.tag);urls=[];maps=[]
    if kind=="urlset":
        for u in r:
            loc=next((x.text for x in u if local(x.tag)=="loc"),None)
            if loc:urls.append(loc)
    elif kind=="sitemapindex":
        for s in r:
            loc=next((x.text for x in s if local(x.tag)=="loc"),None)
            if loc:maps.append(loc)
    out({"valid":kind in ("urlset","sitemapindex"),"kind":kind,"url_count":len(urls),"sitemap_count":len(maps),"urls":urls[:100],"sitemaps":maps[:100]})

COMMANDS={
"openapi-v3-spec-linter":openapi_v3_spec_linter,"openapi-path-param-chk":openapi_path_param_chk,"openapi-schema-resolver":openapi_schema_resolver,
"swagger-v2-converter":swagger_v2_converter,"asyncapi-spec-validator":asyncapi_spec_validator,"graphql-schema-parser":graphql_schema_parser,
"graphql-query-linter":graphql_query_linter,"graphql-introspection-chk":graphql_introspection_chk,"protobuf-proto3-linter":protobuf_proto3_linter,
"protobuf-field-number-chk":protobuf_field_number_chk,"protobuf-reserved-ranges":protobuf_reserved_ranges,"protobuf-deprecated-tag":protobuf_deprecated_tag,
"grpc-reflection-client":grpc_reflection_client,"json-schema-draft7-val":lambda a:json_schema_runner(a,"draft7"),"json-schema-draft2020":lambda a:json_schema_runner(a,"2020-12"),
"json-patch-rfc6902-run":json_patch_rfc6902_run,"json-merge-patch-rfc7386":json_merge_patch_rfc7386,"json-pointer-rfc6901-cli":json_pointer_rfc6901_cli,
"http-status-code-lookup":http_status_code_lookup,"http-auth-bearer-token":http_auth_bearer_token,"http-basic-auth-encoder":http_basic_auth_encoder,
"oauth2-token-exchange":oauth2_token_exchange,"oauth2-pkce-challenge":oauth2_pkce_challenge,"oidc-discovery-parser":oidc_discovery_parser,
"saml-assertion-xml-chk":saml_assertion_xml_chk,"soap-envelope-parser":soap_envelope_parser,"wsdl-contract-inspector":wsdl_contract_inspector,
"rest-api-response-diff":rest_api_response_diff,"api-curl-command-gen":api_curl_command_gen,"api-fuzz-parameter-gen":api_fuzz_parameter_gen,
"api-rate-limit-header":api_rate_limit_header,"etag-if-none-match-chk":etag_if_none_match_chk,"cache-control-validator":cache_control_validator,
"content-security-policy":content_security_policy,"cross-origin-embedder":cross_origin_embedder,"cross-origin-resource":cross_origin_resource,
"referrer-policy-checker":referrer_policy_checker,"hsts-preload-eligibility":hsts_preload_eligibility,"expect-ct-header-chk":expect_ct_header_chk,
"feature-policy-analyzer":feature_policy_analyzer,"permissions-policy-fmt":permissions_policy_fmt,"webhook-delivery-retry":webhook_delivery_retry,
"hmac-webhook-verifier":hmac_webhook_verifier,"api-deprecation-sunset":api_deprecation_sunset,"pagination-link-header":pagination_link_header,
"cursor-based-pager-cli":cursor_based_pager_cli,"json-feed-validator-cli":json_feed_validator_cli,"rss2-feed-xml-checker":rss2_feed_xml_checker,
"atom-feed-xml-validator":atom_feed_xml_validator,"sitemap-xml-inspector":sitemap_xml_inspector,
}

def main():
    if len(COMMANDS)!=50:die(f"internal command count mismatch: {len(COMMANDS)}")
    prog=Path(sys.argv[0]).name
    if prog in COMMANDS:cmd=prog;args=sys.argv[1:]
    else:
        if len(sys.argv)<2 or sys.argv[1] in ("-h","--help"):
            print("OceanStudio functional shard 25 runtime");[print(" ",x) for x in sorted(COMMANDS)];return
        if sys.argv[1] in ("-v","--version"):print(VERSION);return
        cmd=sys.argv[1];args=sys.argv[2:]
    if cmd not in COMMANDS:die(f"unknown command: {cmd}")
    COMMANDS[cmd](args)
if __name__=="__main__":main()
