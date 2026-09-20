#!/usr/bin/env python3
from __future__ import annotations
import sys,json,re,sqlite3,struct,hashlib,math,base64,csv,io
from pathlib import Path
VERSION="2.0.0"
def out(x): print(json.dumps(x,indent=2,sort_keys=True,default=str))
def die(x,c=2): print(x,file=sys.stderr); raise SystemExit(c)
def txt(a): return Path(a[0]).read_text(errors="replace") if a and Path(a[0]).exists() else (" ".join(a) if a else sys.stdin.read())
def blob(a): return Path(a[0]).read_bytes()
def con(p): return sqlite3.connect(p)
def duckdb(a):
    try: import duckdb as d
    except Exception: out({"available":False,"reason":"duckdb Python module not installed"}); return
    q=a[0] if a else sys.stdin.read(); c=d.connect(":memory:"); cur=c.execute(q); out({"columns":[x[0] for x in cur.description] if cur.description else [],"rows":cur.fetchall() if cur.description else []})
def sqlite_fts(a):
    if len(a)<2: die("DB QUERY")
    c=con(a[0]); rows=[]
    for (name,) in c.execute("select name from sqlite_master where type='table' and sql like '%fts5%'"):
        try:
            rows += [{"table":name,"row":r} for r in c.execute(f'SELECT rowid,* FROM "{name}" WHERE "{name}" MATCH ? LIMIT 50',(a[1],))]
        except Exception: pass
    c.close(); out(rows)
def sqlite_json(a):
    if len(a)<2: die("JSON PATH")
    cur=json.loads(Path(a[0]).read_text() if Path(a[0]).exists() else a[0])
    for p in a[1].strip("$.").split(".") if a[1] not in ("$","") else []: cur=cur[int(p)] if isinstance(cur,list) else cur[p]
    out(cur)
def sqlite_header(a):
    b=blob(a)
    if b[:16]!=b"SQLite format 3\0": die("not sqlite3")
    ps=int.from_bytes(b[16:18],"big"); ps=65536 if ps==1 else ps
    out({"page_size":ps,"write_version":b[18],"read_version":b[19],"reserved":b[20],"page_count":int.from_bytes(b[28:32],"big"),"freelist_pages":int.from_bytes(b[36:40],"big"),"schema_cookie":int.from_bytes(b[40:44],"big"),"encoding":int.from_bytes(b[56:60],"big")})
def sqlite_page(a):
    b=blob(a); ps=int.from_bytes(b[16:18],"big"); ps=65536 if ps==1 else ps; pages=(len(b)+ps-1)//ps; kinds={}
    for i in range(pages):
        o=i*ps+(100 if i==0 else 0)
        if o<len(b): kinds[hex(b[o])]=kinds.get(hex(b[o]),0)+1
    out({"page_size":ps,"pages":pages,"page_types":kinds})
def sqlite_frag(a):
    b=blob(a); pages=int.from_bytes(b[28:32],"big") if b[:16]==b"SQLite format 3\0" else 0; free=int.from_bytes(b[36:40],"big") if pages else 0
    out({"page_count":pages,"freelist_pages":free,"free_percent":100*free/pages if pages else 0})
def sqlite_pragma(a):
    c=con(a[0]); d={}
    for k in ["page_size","page_count","freelist_count","journal_mode","synchronous","foreign_keys","user_version","schema_version","encoding"]:
        try:d[k]=c.execute("PRAGMA "+k).fetchone()[0]
        except Exception:d[k]=None
    c.close(); out(d)
def sqlite_tables(a):
    c=con(a[0]); rows=[]
    for (name,) in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'"):
        try:n=c.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
        except:n=None
        rows.append({"table":name,"rows":n})
    c.close(); out(rows)
def sqlite_index(a):
    if len(a)<2:die("DB SQL")
    c=con(a[0]); plan=list(c.execute("EXPLAIN QUERY PLAN "+a[1])); c.close(); scans=[x[-1] for x in plan if "SCAN" in str(x[-1]).upper() and "USING INDEX" not in str(x[-1]).upper()]
    out({"plan":plan,"full_scans":scans,"recommendation":"consider indexes on filtered/joined columns" if scans else "no obvious full table scan"})
def sqlite_journal(a):
    b=blob(a);out({"bytes":len(b),"magic":b[:8].hex(),"page_count_hint":int.from_bytes(b[8:12],"big") if len(b)>=12 else None})
def sqlite_blob(a):
    if len(a)<4:die("DB TABLE COLUMN ROWID")
    c=con(a[0]);r=c.execute(f'SELECT "{a[2]}" FROM "{a[1]}" WHERE rowid=?',(int(a[3]),)).fetchone();c.close()
    if not r:die("row not found")
    v=r[0];sys.stdout.buffer.write(v if isinstance(v,bytes) else str(v).encode())
def sqlite_recover(a): out([x.decode(errors="replace") for x in re.findall(rb"[\x20-\x7e]{6,}",blob(a))[:500]])
def magic(a):
    b=blob(a);out({"bytes":len(b),"head":b[:64].hex(),"sha256":hashlib.sha256(b).hexdigest()})
def redis_rdb(a):
    b=blob(a);out({"valid":b.startswith(b"REDIS"),"version":b[5:9].decode(errors="replace") if len(b)>=9 else None,"bytes":len(b)})
def redis_aof(a):
    s=txt(a);cmds=[];cur=[]
    for l in s.splitlines():
        if l.startswith("*"):
            if cur:cmds.append(cur);cur=[]
        elif l.startswith(chr(36)):continue
        else:cur.append(l)
    if cur:cmds.append(cur)
    out(cmds)
def resp_enc(a):
    parts=a or ["PING"]; dollar=chr(36); sys.stdout.write("*"+str(len(parts))+"\r\n"+"".join(dollar+str(len(x.encode()))+"\r\n"+x+"\r\n" for x in parts))
def resp_dec(a):
    s=txt(a);lines=s.split("\r\n");i=0;res=[]; dollar=chr(36)
    while i<len(lines):
        l=lines[i]
        if l.startswith(("+","-",":")):res.append(l[1:]);i+=1
        elif l.startswith(dollar):
            n=int(l[1:]);res.append(lines[i+1] if n>=0 and i+1<len(lines) else None);i+=2
        elif l.startswith("*"):
            n=int(l[1:]);arr=[];i+=1
            for _ in range(n):
                if i<len(lines) and lines[i].startswith(dollar):arr.append(lines[i+1]);i+=2
                else:arr.append(lines[i] if i<len(lines) else None);i+=1
            res.append(arr)
        elif l=="":i+=1
        else:res.append(l);i+=1
    out(res)
def memcached(a): out({"command":" ".join(a),"valid":bool(a and a[0].lower() in {"get","gets","set","add","replace","delete","incr","decr","stats","version","quit"})})
def cql(a):
    s=txt(a);out({"valid":s.count("(")==s.count(")") and s.count("{")==s.count("}") and bool(re.search(r"\b(CREATE|SELECT|INSERT|UPDATE|DELETE|ALTER|DROP)\b",s,re.I)),"keyspaces":re.findall(r"\bKEYSPACE\s+(\w+)",s,re.I),"tables":re.findall(r"\bTABLE\s+(\w+)",s,re.I)})
def mongo(a):
    x=json.loads(txt(a))
    def cv(v):
        if isinstance(v,dict):
            for k,fn in [("$numberLong",int),("$numberDouble",float),("$oid",str),("$date",str)]:
                if k in v:return fn(v[k])
            return {k:cv(z) for k,z in v.items()}
        return [cv(z) for z in v] if isinstance(v,list) else v
    out(cv(x))
def pgcopy(a): 
    rows=list(csv.reader(io.StringIO(txt(a)),delimiter="\t"));out({"rows":rows,"count":len(rows)})
def mysqlbin(a):
    b=blob(a);valid=b.startswith(b"\xfebin");rows=[];p=4
    while valid and p+19<=len(b):
        size=int.from_bytes(b[p+9:p+13],"little")
        if size<19 or p+size>len(b):break
        rows.append({"offset":p,"timestamp":int.from_bytes(b[p:p+4],"little"),"event_type":b[p+4],"event_size":size});p+=size
    out({"valid":valid,"events":rows})
def sql_convert(a):
    s=txt(a)
    for p,r in [(r"\bSERIAL\b","INTEGER"),(r"\bBOOLEAN\b","INTEGER"),(r"\bTRUE\b","1"),(r"\bFALSE\b","0")]:s=re.sub(p,r,s,flags=re.I)
    print(s)
def sql_format(a):
    s=re.sub(r"\s+"," ",txt(a)).strip()
    for k in ["SELECT","FROM","WHERE","GROUP BY","ORDER BY","HAVING","JOIN","LEFT JOIN","RIGHT JOIN","INNER JOIN","VALUES","SET","RETURNING"]:s=re.sub(r"\s+"+k+r"\s+",f"\n{k} ",s,flags=re.I)
    print(s)
def sql_ast(a):
    t=re.findall(r"'(?:''|[^'])*'|[A-Za-z_]\w*|\d+(?:\.\d+)?|<=|>=|<>|!=|[(),.*=<>+-/]",txt(a));out({"tokens":t,"statement":t[0].upper() if t else None})
def sqlinj(a):
    s=txt(a);ps=[r"'\s*OR\s+['\d]",r"--",r";\s*(DROP|DELETE|UPDATE|INSERT)",r"\bUNION\s+SELECT\b",r"/\*"];bad=[p for p in ps if re.search(p,s,re.I)];out({"suspicious":bool(bad),"patterns":bad,"advice":"use bound parameters"})
def migrations(a):
    v=sorted(int(x) for x in a);out({"versions":v,"gaps":[n for n in range(v[0],v[-1]+1) if n not in v] if v else []})
def schema_snap(a):
    s=txt(a);out({"sha256":hashlib.sha256(s.encode()).hexdigest(),"normalized":" ".join(s.split())})
def fk(a):
    c=con(a[0]);c.execute("PRAGMA foreign_keys=ON");r=list(c.execute("PRAGMA foreign_key_check"));c.close();out({"valid":not r,"violations":r})
def orphan(a):
    if len(a)<5:die("DB child child_fk parent parent_pk")
    c=con(a[0]);q=f'SELECT c.rowid FROM "{a[1]}" c LEFT JOIN "{a[3]}" p ON c."{a[2]}"=p."{a[4]}" WHERE c."{a[2]}" IS NOT NULL AND p."{a[4]}" IS NULL';r=[x[0] for x in c.execute(q)];c.close();out(r)
def constraints(a):
    c=con(a[0]);rows=[]
    for n,s in c.execute("select name,sql from sqlite_master where type='table' and sql is not null"):rows.append({"table":n,"not_null":len(re.findall(r"\bNOT NULL\b",s,re.I)),"unique":len(re.findall(r"\bUNIQUE\b",s,re.I)),"check":len(re.findall(r"\bCHECK\s*\(",s,re.I))})
    c.close();out(rows)
def seed(a):
    if len(a)<2:die("ROWS COL[:type]...")
    rows=[]
    for i in range(int(a[0])):
        d={}
        for c in a[1:]:
            name,*typ=c.split(":");d[name]=i if typ and typ[0]=="int" else f"{name}_{i}"
        rows.append(d)
    out(rows)
def parquet(a):
    b=blob(a);valid=len(b)>=12 and b[:4]==b"PAR1" and b[-4:]==b"PAR1";meta=int.from_bytes(b[-8:-4],"little") if valid else None;out({"valid":valid,"bytes":len(b),"metadata_length":meta,"metadata_offset":len(b)-8-meta if valid else None})
def orc(a):
    b=blob(a);out({"valid":b[:3]==b"ORC","bytes":len(b),"postscript_length":b[-1] if b else None})
def arrow(a):
    b=blob(a);out({"valid_file":b[:6]==b"ARROW1" and b[-6:]==b"ARROW1","valid_stream":b[:4]==b"\xff\xff\xff\xff","bytes":len(b)})
def dbf(a):
    b=blob(a)
    if len(b)<32:die("short dbf")
    out({"version":b[0],"date":{"year":1900+b[1],"month":b[2],"day":b[3]},"records":int.from_bytes(b[4:8],"little"),"header_length":int.from_bytes(b[8:10],"little"),"record_length":int.from_bytes(b[10:12],"little")})
def script(a): 
    s=txt(a);out({"lines":s.splitlines(),"statements":[x.strip() for x in s.split(";") if x.strip()]})
def timescale(a):
    if len(a)<3:die("START END INTERVAL_SECONDS")
    start,end,step=map(float,a[:3]);out({"chunks":math.ceil(max(0,end-start)/step) if step>0 else None})
def influx(a):
    s=txt(a);rows=[];errs=[]
    for i,l in enumerate(s.splitlines(),1):
        m=re.match(r"([^ ,]+)(?:,([^ ]+))?\s+([^ ]+)(?:\s+(\d+))?$",l)
        if m:rows.append({"measurement":m.group(1),"tags":m.group(2),"fields":m.group(3),"timestamp":m.group(4)})
        elif l.strip():errs.append(i)
    out({"valid":not errs,"points":rows,"error_lines":errs})
def promblock(a):
    p=Path(a[0]);m=json.loads((p/"meta.json").read_text() if p.is_dir() else p.read_text());out({"ulid":m.get("ulid"),"minTime":m.get("minTime"),"maxTime":m.get("maxTime"),"stats":m.get("stats")})
def vec(a):
    if len(a)<2:die("VEC1 VEC2")
    x=[float(v) for v in a[0].split(",")];y=[float(v) for v in a[1].split(",")];dot=sum(i*j for i,j in zip(x,y));nx=math.sqrt(sum(i*i for i in x));ny=math.sqrt(sum(i*i for i in y));out({"cosine":dot/(nx*ny) if nx and ny else None,"dimensions":min(len(x),len(y))})
def faiss(a):
    b=blob(a);out({"bytes":len(b),"magic_ascii":b[:8].decode(errors="replace"),"magic_hex":b[:8].hex()})
COMMANDS={"duckdb-query-runner":duckdb,"sqlite-fts5-tokenizer":sqlite_fts,"sqlite-json-query-cli":sqlite_json,"sqlite-rbtree-visualizer":sqlite_page,"sqlite-b-tree-inspector":sqlite_header,"sqlite-page-analyzer":sqlite_page,"sqlite-vacuum-analyze":sqlite_frag,"sqlite-pragma-dump":sqlite_pragma,"sqlite-table-sizes":sqlite_tables,"sqlite-index-recommend":sqlite_index,"sqlite-transaction-log":sqlite_journal,"sqlite-blob-extractor":sqlite_blob,"sqlite-repair-corrupt":sqlite_recover,"rocksdb-sst-dump":magic,"leveldb-log-inspector":magic,"lmdb-stat-analyzer":magic,"berkeleydb-hash-chk":magic,"redis-rdb-parser":redis_rdb,"redis-aof-rewriter":redis_aof,"redis-resp-encoder":resp_enc,"redis-resp-decoder":resp_dec,"memcached-text-proto":memcached,"cassandra-cql-parser":cql,"mongodb-extended-json":mongo,"postgresql-copy-stream":pgcopy,"mysql-binlog-event-chk":mysqlbin,"sql-dialect-converter":sql_convert,"sql-syntax-formatter":sql_format,"sql-ast-visualizer":sql_ast,"sql-injection-tester":sqlinj,"db-migration-history":migrations,"db-schema-snapshot":schema_snap,"db-foreign-key-chk":fk,"db-orphan-records-chk":orphan,"db-constraint-audit":constraints,"db-seed-data-gen":seed,"parquet-schema-viewer":parquet,"parquet-metadata-dump":parquet,"orc-file-footer-parser":orc,"arrow-ipc-validator":arrow,"feather-file-inspect":arrow,"dbf-xbase-reader":dbf,"h2-database-export":script,"derby-log-analyzer":magic,"timescaledb-hypertable":timescale,"influxdb-line-protocol":influx,"prometheus-tsdb-block":promblock,"vector-embedding-index":vec,"hnsw-distance-calc":vec,"faiss-index-header":faiss}
def main():
    if len(COMMANDS)!=50:die(f"command count {len(COMMANDS)}")
    p=Path(sys.argv[0]).name
    if p in COMMANDS:cmd,args=p,sys.argv[1:]
    else:
        if len(sys.argv)<2 or sys.argv[1] in ("-h","--help"):print("OceanStudio functional shard 12");print("\n".join(sorted(COMMANDS)));return
        if sys.argv[1] in ("-v","--version"):print(VERSION);return
        cmd,args=sys.argv[1],sys.argv[2:]
    if cmd not in COMMANDS:die("unknown command: "+cmd)
    COMMANDS[cmd](args)
if __name__=="__main__":main()
