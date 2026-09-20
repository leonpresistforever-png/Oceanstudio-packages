#!/usr/bin/env python3
import json, subprocess, sys, tempfile, uuid
from pathlib import Path

R = Path(sys.argv[1])

def p(cmd, *args, data="", binary=False):
    if binary:
        return subprocess.run([sys.executable,str(R),cmd,*map(str,args)],input=data,capture_output=True)
    r=subprocess.run([sys.executable,str(R),cmd,*map(str,args)],input=data,text=True,capture_output=True)
    if r.returncode:
        raise AssertionError(f"{cmd}: {r.stderr}")
    return r

def j(cmd,*args,data=""):
    return json.loads(p(cmd,*args,data=data).stdout)

def ok(name, cond, passed):
    if not cond: raise AssertionError(name)
    passed.append(name)

def main():
    q=[]
    ok("csv-delimiter-detector",j("csv-delimiter-detector",data="a;b\n1;2\n")["delimiter"]==";",q)
    ok("csv-quoting-fixer","a,b" in p("csv-quoting-fixer",data='a,b\n"x,y\n').stdout,q)
    ok("csv-transpose-matrix",p("csv-transpose-matrix",data="a,b\n1,2\n").stdout.splitlines()==["a,1","b,2"],q)
    with tempfile.TemporaryDirectory() as td:
        a=Path(td)/"a.csv"; b=Path(td)/"b.csv"; a.write_text("id,v\n1,a\n2,b\n"); b.write_text("id,v\n1,z\n3,c\n")
        d=j("csv-diff-table-tool",a,b,"id"); ok("csv-diff-table-tool",all(len(d[x])==1 for x in ("added","removed","changed")),q)
    t="g\tv\na\t1\na\t2\nb\t4\n"
    ok("tsv-aggregate-group-by","a\t3.0" in p("tsv-aggregate-group-by","g","v","sum",data=t).stdout,q)
    ok("tsv-sliding-window-avg","1.5" in p("tsv-sliding-window-avg","v","2",data="v\n1\n2\n3\n").stdout,q)
    ok("tsv-cumsum-running-tot","3.0" in p("tsv-cumsum-running-tot","v","sum",data="v\n1\n2\n").stdout,q)
    ok("tsv-quantile-cut-cli","quantile_bin" in p("tsv-quantile-cut-cli","v","2",data="v\n1\n2\n3\n4\n").stdout,q)
    ok("json-lines-flatten-tool",json.loads(p("json-lines-flatten-tool",data='{"a":{"b":1}}\n').stdout)["a.b"]==1,q)
    ok("json-lines-unflatten",json.loads(p("json-lines-unflatten",data='{"a.b":1}\n').stdout)["a"]["b"]==1,q)
    ok("ndjson-filter-jq-lite",'"x":2' in p("ndjson-filter-jq-lite","x",">","1",data='{"x":1}\n{"x":2}\n').stdout,q)
    ok("ndjson-sort-by-key",p("ndjson-sort-by-key","x",data='{"x":2}\n{"x":1}\n').stdout.splitlines()[0]=='{"x":1}',q)
    ok("log-regex-named-captures",j("log-regex-named-captures",r"id=(?P<id>\w+)",data="id=abc\n")["id"]=="abc",q)
    ok("grok-pattern-parser",j("grok-pattern-parser","%{IP:ip} %{WORD:verb}",data="1.2.3.4 GET\n")["verb"]=="GET",q)
    clf='127.0.0.1 - u [10/Oct/2000:13:55:36 -0700] "GET /x HTTP/1.1" 200 12\n'
    ok("clf-apache-log-parser",j("clf-apache-log-parser",data=clf)["status"]==200,q)
    comb='127.0.0.1 - u [10/Oct/2000:13:55:36 -0700] "GET /x HTTP/1.1" 200 12 "-" "UA"\n'
    ok("combined-log-formatter",j("combined-log-formatter",data=comb)["agent"]=="UA",q)
    ok("nginx-access-log-parser",j("nginx-access-log-parser",'$remote_addr $status',data="127.0.0.1 200\n")["status"]=="200",q)
    ok("auth-log-ip-aggregator",p("auth-log-ip-aggregator",data="Failed password for x from 1.2.3.4 port 1\n"*2).stdout.startswith("2\t"),q)
    ok("fail2ban-regex-tester",j("fail2ban-regex-tester",r"from <HOST>",data="bad from 1.2.3.4\n")["matched"]==1,q)
    pv="r\tc\tv\nA\tX\t2\nA\tY\t3\n"
    ok("tsv-pivot-table-gen","A\t2.0\t3.0" in p("tsv-pivot-table-gen","r","c","v","sum",data=pv).stdout,q)
    ok("tsv-unpivot-melt-tool",p("tsv-unpivot-melt-tool","id",data="id\ta\tb\n1\tx\ty\n").stdout.count("\n")==3,q)
    ok("stream-sample-reservoir",len(p("stream-sample-reservoir","2","42",data="a\nb\nc\nd\n").stdout.splitlines())==2,q)
    h=j("stream-distinct-hyperlog","8",data="a\nb\nc\na\n"); ok("stream-distinct-hyperlog",2<=h["estimate"]<=5,q)
    ok("stream-moving-average",p("stream-moving-average","2",data="1\n3\n5\n").stdout.splitlines()[-1]=="4.0",q)
    ok("stream-exponential-decay",p("stream-exponential-decay","0.5",data="0\n10\n").stdout.splitlines()[-1]=="5.0",q)
    ok("stream-rate-throttle-cli",p("stream-rate-throttle-cli","100000",data="a\nb\n").stdout=="a\nb\n",q)
    ok("stream-chunk-byte-split",len(p("stream-chunk-byte-split","2",data="abcde").stdout.splitlines())==3,q)
    c=p("stream-checksum-hasher","sha256",data="abc"); ok("stream-checksum-hasher",c.stdout=="abc" and "sha256:" in c.stderr,q)
    ok("stream-xor-filter-cli",len(j("stream-xor-filter-cli","build","256",data="a\nb\n")["filter_hex"])==64,q)
    ok("byte-frequency-analysis","61\t3" in p("byte-frequency-analysis",data="aaa").stdout,q)
    with tempfile.TemporaryDirectory() as td:
        f=Path(td)/"x"; f.write_bytes(b"ABCDABCD"); ok("file-dedup-block-hasher",j("file-dedup-block-hasher",f,"4")[0]["count"]==2,q)
    ok("rolling-checksum-fast",len(p("rolling-checksum-fast","3",data="abcdef").stdout.splitlines())==4,q)
    e=p("run-length-encoder-cli",data=b"aaabbc",binary=True).stdout
    d=p("run-length-decoder-cli",data=e,binary=True).stdout
    ok("run-length-encoder-cli",e.startswith(b"ORLE1"),q); ok("run-length-decoder-cli",d==b"aaabbc",q)
    ok("delta-encoding-tool",p("delta-encoding-tool","encode",data="10 13 20").stdout.strip()=="10 3 7",q)
    ok("zigzag-encoding-cli",p("zigzag-encoding-cli","encode","-1","0","1").stdout.strip()=="1 0 2",q)
    hx=p("variable-byte-encoder","encode","1","300").stdout.strip(); ok("variable-byte-encoder",p("variable-byte-encoder","decode",hx).stdout.strip()=="1 300",q)
    hx=p("bit-packing-unpacker","pack","3","1","2","7").stdout.strip(); ok("bit-packing-unpacker",p("bit-packing-unpacker","unpack","3",hx,"3").stdout.strip()=="1 2 7",q)
    ok("column-to-row-transposer",p("column-to-row-transposer",data="a\nb\nc\n").stdout.strip()=="a,b,c",q)
    ok("row-to-column-pack-cli",j("row-to-column-pack-cli",data='{"a":1}\n{"a":2}\n')["a"]==[1,2],q)
    m=p("data-masking-pseudonym","test-key",data="same\nsame\n").stdout.splitlines(); ok("data-masking-pseudonym",m[0]==m[1] and m[0]!="same",q)
    ok("pii-regex-scrubber-cli","[EMAIL]" in p("pii-regex-scrubber-cli",data="person@example.test").stdout,q)
    ok("credit-card-luhn-chk","valid" in j("credit-card-luhn-chk","0000000000000000"),q)
    ok("iban-validator-cli-tool","valid" in j("iban-validator-cli-tool","ZZ00TEST000000000000"),q)
    u1=str(uuid.uuid1()); ok("uuid-v1-timestamp-view",j("uuid-v1-timestamp-view",u1)["timestamp_unix"]>0,q)
    u4=str(uuid.uuid4()); ok("uuid-v4-entropy-tester",j("uuid-v4-entropy-tester",u4)[0]["version4"] is True,q)
    ok("uuid-v5-name-hasher",uuid.UUID(p("uuid-v5-name-hasher","dns","example.test").stdout.strip()).version==5,q)
    us=p("uuid-v7-sortable-maker","2").stdout.splitlines(); ok("uuid-v7-sortable-maker",len(us)==2 and all(uuid.UUID(x).version==7 for x in us),q)
    ok("ulid-timestamp-extractor","unix_ms" in j("ulid-timestamp-extractor","01ARZ3NDEKTSV4RRFFQ69G5FAV"),q)
    ok("nanoid-collision-calc",0<=j("nanoid-collision-calc","64","21","1000000")["collision_probability"]<1,q)
    if len(q)!=50 or len(set(q))!=50: raise AssertionError(f"expected 50 unique tests, got {len(q)}/{len(set(q))}")
    print("PASS: 50/50 shard-27 functional commands")
if __name__=="__main__": main()
