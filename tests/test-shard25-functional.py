#!/usr/bin/env python3
import base64, hashlib, hmac, json, subprocess, sys, tempfile
from pathlib import Path
R=Path(sys.argv[1])
def p(cmd,*args,data=""):
    r=subprocess.run([sys.executable,str(R),cmd,*map(str,args)],input=data,text=True,capture_output=True)
    if r.returncode: raise AssertionError(f"{cmd}: {r.stderr}")
    return r
def j(cmd,*args,data=""):return json.loads(p(cmd,*args,data=data).stdout)
def ok(n,c,q):
    if not c:raise AssertionError(n)
    q.append(n)
def wf(td,name,obj):
    f=Path(td)/name;f.write_text(json.dumps(obj));return f
def varint(n):
    b=bytearray()
    while True:
        x=n&127;n>>=7;b.append(x|(128 if n else 0))
        if not n:return bytes(b)
def fld(num,payload):
    return varint((num<<3)|2)+varint(len(payload))+payload
def main():
    q=[]
    with tempfile.TemporaryDirectory() as td:
        spec={"openapi":"3.0.3","info":{"title":"T","version":"1"},"paths":{"/users/{id}":{"get":{"parameters":[{"name":"id","in":"path","required":True,"schema":{"type":"string"}}],"responses":{"200":{"description":"ok"}}}}},"components":{"schemas":{"User":{"type":"object","properties":{"id":{"type":"string"}}}}}}
        sf=wf(td,"openapi.json",spec)
        ok("openapi-v3-spec-linter",j("openapi-v3-spec-linter",sf)["valid"],q)
        ok("openapi-path-param-chk",j("openapi-path-param-chk",sf)["valid"],q)
        ok("openapi-schema-resolver",j("openapi-schema-resolver",sf,"#/components/schemas/User")["type"]=="object",q)
        sw={"swagger":"2.0","info":{"title":"T","version":"1"},"host":"api.example.test","basePath":"/v1","paths":{},"definitions":{"X":{"type":"object"}}}
        swf=wf(td,"swagger.json",sw);ok("swagger-v2-converter",j("swagger-v2-converter",swf)["openapi"]=="3.0.3",q)
        aa=wf(td,"async.json",{"asyncapi":"2.6.0","info":{"title":"A","version":"1"},"channels":{"x":{"publish":{"message":{"name":"M"}}}}})
        ok("asyncapi-spec-validator",j("asyncapi-spec-validator",aa)["valid"],q)

        ok("graphql-schema-parser",j("graphql-schema-parser",data="type Query { hello: String }\n")["type_count"]==1,q)
        ok("graphql-query-linter",j("graphql-query-linter",data="query Q { user { id } }\n")["valid"],q)
        intro={"data":{"__schema":{"queryType":{"name":"Query"},"types":[{"name":"Query"},{"name":"String"}]}}}
        ok("graphql-introspection-chk",j("graphql-introspection-chk",data=json.dumps(intro))["type_count"]==2,q)
        proto='syntax = "proto3";\nmessage X { string name = 1; int32 age = 2; }\n'
        ok("protobuf-proto3-linter",j("protobuf-proto3-linter",data=proto)["valid"],q)
        ok("protobuf-field-number-chk",j("protobuf-field-number-chk","1","19000")[1]["valid"] is False,q)
        ok("protobuf-reserved-ranges",j("protobuf-reserved-ranges",data='syntax="proto3"; message X { reserved 2; string a = 1; }\n')["valid"],q)
        ok("protobuf-deprecated-tag",j("protobuf-deprecated-tag",data='string old = 1 [deprecated = true];\n')["count"]==1,q)
        svc=fld(1,b"Svc"); filemsg=fld(2,b"pkg")+fld(6,svc); ds=fld(1,filemsg); df=Path(td)/"d.pb";df.write_bytes(ds)
        ok("grpc-reflection-client","pkg.Svc" in j("grpc-reflection-client","--descriptor-set",df)["services"],q)

        schema={"$schema":"http://json-schema.org/draft-07/schema#","type":"object","required":["x"],"properties":{"x":{"type":"integer","minimum":1}}}
        inst={"x":2}; sc=wf(td,"schema.json",schema); ins=wf(td,"inst.json",inst)
        ok("json-schema-draft7-val",j("json-schema-draft7-val",sc,ins)["valid"],q)
        schema20={"$schema":"https://json-schema.org/draft/2020-12/schema","type":"string","minLength":2}; sc20=wf(td,"schema20.json",schema20); in20=wf(td,"in20.json","ok")
        ok("json-schema-draft2020",j("json-schema-draft2020",sc20,in20)["valid"],q)
        doc=wf(td,"doc.json",{"a":1,"b":{"x":2}}); patch=wf(td,"patch.json",[{"op":"replace","path":"/a","value":3},{"op":"add","path":"/c","value":4}])
        ok("json-patch-rfc6902-run",j("json-patch-rfc6902-run",doc,patch)["a"]==3,q)
        mp=wf(td,"merge.json",{"b":{"x":None,"y":5}}); merged=j("json-merge-patch-rfc7386",doc,mp)
        ok("json-merge-patch-rfc7386","x" not in merged["b"] and merged["b"]["y"]==5,q)
        ok("json-pointer-rfc6901-cli",j("json-pointer-rfc6901-cli",doc,"/b/x")==2,q)

        ok("http-status-code-lookup",j("http-status-code-lookup","404")["reason"]=="Not Found",q)
        ok("http-auth-bearer-token",j("http-auth-bearer-token","Bearer","abc.DEF_123")["valid"],q)
        ok("http-basic-auth-encoder",p("http-basic-auth-encoder","u","p").stdout.strip()==("Basic "+base64.b64encode(b"u:p").decode()),q)
        tx=j("oauth2-token-exchange","subject_token=x","subject_token_type=urn:test");ok("oauth2-token-exchange",tx["valid"],q)
        verifier="A"*43;ok("oauth2-pkce-challenge",j("oauth2-pkce-challenge",verifier)["valid_verifier"],q)
        oidc={"issuer":"https://id.example.test","authorization_endpoint":"https://id.example.test/a","token_endpoint":"https://id.example.test/t","jwks_uri":"https://id.example.test/j"}
        ok("oidc-discovery-parser",j("oidc-discovery-parser",data=json.dumps(oidc))["valid"],q)

        saml='<Assertion xmlns="urn:oasis:names:tc:SAML:2.0:assertion" Version="2.0" ID="x"><Issuer>issuer</Issuer><Subject/></Assertion>'
        ok("saml-assertion-xml-chk",j("saml-assertion-xml-chk",data=saml)["valid"],q)
        soap='<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/"><Body><Ping xmlns="urn:t"/></Body></Envelope>'
        ok("soap-envelope-parser",j("soap-envelope-parser",data=soap)["soap_version"]=="1.1",q)
        wsdl='<definitions xmlns="http://schemas.xmlsoap.org/wsdl/" targetNamespace="urn:t"><portType name="P"><operation name="Ping"/></portType><service name="S"/></definitions>'
        ok("wsdl-contract-inspector","Ping" in j("wsdl-contract-inspector",data=wsdl)["operations"],q)

        old=wf(td,"old.json",{"id":1,"name":"x"});new=wf(td,"new.json",{"id":"1"})
        ok("rest-api-response-diff",len(j("rest-api-response-diff",old,new)["breaking_candidates"])>=1,q)
        curl=p("api-curl-command-gen",sf,"GET","/users/{id}").stdout;ok("api-curl-command-gen","curl -X GET" in curl,q)
        fuzz=j("api-fuzz-parameter-gen",data=json.dumps({"properties":{"n":{"type":"integer","minimum":1,"maximum":5}}}))
        ok("api-fuzz-parameter-gen",0 in fuzz["n"] and 6 in fuzz["n"],q)

    rate=j("api-rate-limit-header","RateLimit-Limit: 100","RateLimit-Remaining: 10");ok("api-rate-limit-header",rate["limit"]=="100",q)
    ok("etag-if-none-match-chk",j("etag-if-none-match-chk",'"abc"','W/"abc"')["matched"],q)
    ok("cache-control-validator",j("cache-control-validator","max-age=60,","must-revalidate")["valid"],q)
    ok("content-security-policy","unsafe-inline" in " ".join(j("content-security-policy","default-src 'self'; script-src 'unsafe-inline'")["warnings"]),q)
    ok("cross-origin-embedder",j("cross-origin-embedder","require-corp")["valid"],q)
    ok("cross-origin-resource",j("cross-origin-resource","same-origin")["valid"],q)
    ok("referrer-policy-checker",j("referrer-policy-checker","strict-origin-when-cross-origin")["valid"],q)
    ok("hsts-preload-eligibility",j("hsts-preload-eligibility","max-age=31536000; includeSubDomains; preload")["eligible_header"],q)
    ok("expect-ct-header-chk",j("expect-ct-header-chk","max-age=60, enforce")["valid"],q)
    ok("feature-policy-analyzer",j("feature-policy-analyzer","camera=(), geolocation=(self)")["count"]==2,q)
    ok("permissions-policy-fmt","camera=()" in p("permissions-policy-fmt","geolocation=(self), camera=()").stdout,q)
    ok("webhook-delivery-retry",len(j("webhook-delivery-retry","3","1","10"))==3,q)
    secret="k";payload="body";sig=hmac.new(secret.encode(),payload.encode(),hashlib.sha256).hexdigest()
    ok("hmac-webhook-verifier",j("hmac-webhook-verifier",secret,"sha256="+sig,data=payload)["valid"],q)
    ok("api-deprecation-sunset","sunset" in j("api-deprecation-sunset","Deprecation: true","Sunset: Wed, 31 Dec 2036 23:59:59 GMT"),q)
    links=j("pagination-link-header",'<https://x.test/p2>; rel="next", <https://x.test/p1>; rel="prev"')
    ok("pagination-link-header",links["by_rel"]["next"].endswith("/p2"),q)
    tok=p("cursor-based-pager-cli","encode","row42").stdout.strip();ok("cursor-based-pager-cli",j("cursor-based-pager-cli","decode",tok)["v"]=="row42",q)
    feed={"version":"https://jsonfeed.org/version/1.1","title":"T","items":[{"id":"1","content_text":"x"}]}
    ok("json-feed-validator-cli",j("json-feed-validator-cli",data=json.dumps(feed))["valid"],q)
    rss='<rss version="2.0"><channel><title>T</title><link>https://x.test</link><description>D</description><item><title>I</title></item></channel></rss>'
    ok("rss2-feed-xml-checker",j("rss2-feed-xml-checker",data=rss)["valid"],q)
    atom='<feed xmlns="http://www.w3.org/2005/Atom"><id>x</id><title>T</title><updated>2026-01-01T00:00:00Z</updated><entry/></feed>'
    ok("atom-feed-xml-validator",j("atom-feed-xml-validator",data=atom)["valid"],q)
    site='<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://x.test/</loc></url></urlset>'
    ok("sitemap-xml-inspector",j("sitemap-xml-inspector",data=site)["url_count"]==1,q)
    if len(q)!=50 or len(set(q))!=50:raise AssertionError(f"expected 50 tests got {len(q)}/{len(set(q))}")
    print("PASS: 50/50 shard-25 functional commands")
if __name__=="__main__":main()
