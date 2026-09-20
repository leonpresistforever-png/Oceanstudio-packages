#!/usr/bin/env python3
from __future__ import annotations
import argparse, base64, binascii, bz2, csv, datetime as dt, difflib, gzip, hashlib, hmac, html, io, ipaddress, json, lzma, math, os, pathlib, platform, random, re, secrets, shlex, socket, sqlite3, ssl, statistics, struct, subprocess, sys, tarfile, time, urllib.parse, urllib.request, uuid, zlib, zipfile
from collections import Counter
from zoneinfo import ZoneInfo, available_timezones

VERSION='1.0.0'

def read_bytes(path=None):
    if path and path != '-': return pathlib.Path(path).read_bytes()
    return sys.stdin.buffer.read()
def read_text(path=None): return read_bytes(path).decode('utf-8','replace')
def out(x):
    if isinstance(x,(dict,list,tuple)): print(json.dumps(x,indent=2,ensure_ascii=False,default=str))
    elif isinstance(x,bytes): sys.stdout.buffer.write(x)
    else: print(x)
def arg_path(args): return args[0] if args else None
def arg_data(args): return read_bytes(arg_path(args))
def txt(args): return read_text(arg_path(args))
def num(x):
    try: return int(x)
    except: return float(x)

def do_hash(tool,args):
    algo=tool.split('hash-',1)[1].replace('-','_'); h=hashlib.new(algo); h.update(arg_data(args)); out(h.hexdigest())
def do_hmac(tool,args):
    algo=tool.split('hmac-',1)[1].replace('-','_'); key=(args[0] if args else '').encode(); data=read_bytes(args[1] if len(args)>1 else None); out(hmac.new(key,data,algo).hexdigest())

def encdec(tool,args,decode=False):
    mode=tool.split(('decode-' if decode else 'encode-'),1)[1]; d=arg_data(args)
    if mode=='base64': r=base64.b64decode(d) if decode else base64.b64encode(d)
    elif mode=='base32': r=base64.b32decode(d) if decode else base64.b32encode(d)
    elif mode=='base16': r=base64.b16decode(d,casefold=True) if decode else base64.b16encode(d)
    elif mode=='base85': r=base64.b85decode(d) if decode else base64.b85encode(d)
    elif mode=='ascii85': r=base64.a85decode(d) if decode else base64.a85encode(d)
    elif mode=='hex': r=bytes.fromhex(d.decode().strip()) if decode else d.hex().encode()
    elif mode=='url': r=(urllib.parse.unquote_to_bytes(d.decode()) if decode else urllib.parse.quote_from_bytes(d).encode())
    elif mode=='html': r=(html.unescape(d.decode()).encode() if decode else html.escape(d.decode()).encode())
    elif mode=='json':
        val=json.loads(d.decode()) if decode else None
        r=(val.encode() if decode and isinstance(val,str) else (json.dumps(val,ensure_ascii=False).encode() if decode else json.dumps(d.decode(),ensure_ascii=False).encode()))
    elif mode=='rot13': import codecs; r=codecs.decode(d.decode(),'rot_13').encode()
    elif mode=='gzip': r=gzip.decompress(d) if decode else gzip.compress(d,mtime=0)
    elif mode=='zlib': r=zlib.decompress(d) if decode else zlib.compress(d,9)
    elif mode=='bz2': r=bz2.decompress(d) if decode else bz2.compress(d)
    elif mode=='lzma': r=lzma.decompress(d) if decode else lzma.compress(d)
    elif mode=='utf8': r=d.decode('utf-8','replace').encode('unicode_escape') if not decode else d.decode().encode().decode('unicode_escape').encode()
    elif mode=='repr': r=(bytes(d.decode(),'utf-8').decode('unicode_escape').encode() if decode else repr(d.decode('utf-8','replace')).encode())
    else: raise SystemExit('unsupported codec')
    out(r)

def do_text(tool,args):
    mode=tool.split('text-',1)[1]; s=txt(args); lines=s.splitlines(); extra=args[1:] if args else []
    if mode=='lines': out(len(lines))
    elif mode=='words': out(len(s.split()))
    elif mode=='chars': out(len(s))
    elif mode=='bytes': out(len(s.encode()))
    elif mode=='reverse': out(s[::-1])
    elif mode=='reverse-lines': out('\n'.join(reversed(lines)))
    elif mode=='sort': out('\n'.join(sorted(lines)))
    elif mode=='sort-num': out('\n'.join(sorted(lines,key=lambda x:float(x.strip()))))
    elif mode=='unique': out('\n'.join(dict.fromkeys(lines)))
    elif mode=='uniq-count': out('\n'.join(f'{n}\t{k}' for k,n in Counter(lines).most_common()))
    elif mode=='freq-words': out('\n'.join(f'{n}\t{k}' for k,n in Counter(re.findall(r"[\w'-]+",s.lower())).most_common()))
    elif mode=='freq-lines': out('\n'.join(f'{n}\t{k}' for k,n in Counter(lines).most_common()))
    elif mode in ('lower','upper','title','strip'): out(getattr(s,mode)())
    elif mode=='squeeze-space': out(re.sub(r'[ \t]+',' ',s))
    elif mode=='tabs-to-spaces': out(s.expandtabs(int(extra[0]) if extra else 4))
    elif mode=='spaces-to-tabs': out(s.replace(' '*(int(extra[0]) if extra else 4),'\t'))
    elif mode=='head': out('\n'.join(lines[:int(extra[0]) if extra else 10]))
    elif mode=='tail': out('\n'.join(lines[-(int(extra[0]) if extra else 10):]))
    elif mode=='grep': out('\n'.join(x for x in lines if re.search(extra[0],x)))
    elif mode=='grep-v': out('\n'.join(x for x in lines if not re.search(extra[0],x)))
    elif mode=='regex-replace': out(re.sub(extra[0],extra[1],s))
    elif mode=='number-lines': out('\n'.join(f'{i+1:6d}\t{x}' for i,x in enumerate(lines)))

def jload(args): return json.loads(txt(args))
def do_json(tool,args):
    mode=tool.split('json-',1)[1]; obj=jload(args); ex=args[1:] if args else []
    if mode=='pretty': out(json.dumps(obj,indent=2,ensure_ascii=False,sort_keys=True))
    elif mode=='minify': out(json.dumps(obj,separators=(',',':'),ensure_ascii=False))
    elif mode=='validate': out('valid')
    elif mode=='keys': out(list(obj.keys()) if isinstance(obj,dict) else [])
    elif mode=='values': out(list(obj.values()) if isinstance(obj,dict) else [])
    elif mode=='get':
        cur=obj
        for p in ex[0].split('.'):
            cur=cur[int(p)] if isinstance(cur,list) else cur[p]
        out(cur)
    elif mode=='set':
        cur=obj; ps=ex[0].split('.'); val=json.loads(ex[1])
        for p in ps[:-1]: cur=cur[int(p)] if isinstance(cur,list) else cur.setdefault(p,{})
        if isinstance(cur,list): cur[int(ps[-1])]=val
        else: cur[ps[-1]]=val
        out(obj)
    elif mode=='delete':
        cur=obj; ps=ex[0].split('.')
        for p in ps[:-1]: cur=cur[int(p)] if isinstance(cur,list) else cur[p]
        if isinstance(cur,list): cur.pop(int(ps[-1]))
        else: cur.pop(ps[-1],None)
        out(obj)
    elif mode=='merge':
        other=json.loads(read_text(ex[0])); out({**obj,**other} if isinstance(obj,dict) and isinstance(other,dict) else [obj,other])
    elif mode=='diff':
        other=json.loads(read_text(ex[0])); a=json.dumps(obj,indent=2,sort_keys=True).splitlines(); b=json.dumps(other,indent=2,sort_keys=True).splitlines(); out('\n'.join(difflib.unified_diff(a,b,lineterm='')))
    elif mode=='flatten':
        flat={}
        def rec(v,p=''):
            if isinstance(v,dict):
                for k,x in v.items(): rec(x,f'{p}.{k}' if p else k)
            elif isinstance(v,list):
                for i,x in enumerate(v): rec(x,f'{p}.{i}' if p else str(i))
            else: flat[p]=v
        rec(obj); out(flat)
    elif mode=='unflatten':
        root={}
        for k,v in obj.items():
            cur=root; ps=k.split('.')
            for p in ps[:-1]: cur=cur.setdefault(p,{})
            cur[ps[-1]]=v
        out(root)
    elif mode=='sort-keys': out(json.loads(json.dumps(obj,sort_keys=True)))
    elif mode=='array-length': out(len(obj) if isinstance(obj,list) else 0)
    elif mode=='object-size': out(len(obj) if isinstance(obj,dict) else 0)
    elif mode=='type': out(type(obj).__name__)
    elif mode=='path-list':
        paths=[]
        def rec(v,p='$'):
            if isinstance(v,dict):
                for k,x in v.items(): rec(x,p+'.'+k)
            elif isinstance(v,list):
                for i,x in enumerate(v): rec(x,f'{p}[{i}]')
            else: paths.append(p)
        rec(obj); out(paths)
    elif mode=='ndjson-to-array': out([json.loads(x) for x in txt(args).splitlines() if x.strip()])
    elif mode=='array-to-ndjson': out('\n'.join(json.dumps(x,separators=(',',':')) for x in obj))
    elif mode=='canonical': out(json.dumps(obj,separators=(',',':'),sort_keys=True,ensure_ascii=False))

def csv_rows(args):
    s=txt(args); return list(csv.reader(io.StringIO(s)))
def do_csv(tool,args):
    mode=tool.split('csv-',1)[1]; rows=csv_rows(args); ex=args[1:] if args else []
    if not rows: return
    h=rows[0]; data=rows[1:]
    if mode=='rows': out(len(data))
    elif mode=='columns': out(len(h))
    elif mode=='header': out(h)
    elif mode=='head': out('\n'.join(','.join(r) for r in [h]+data[:int(ex[0]) if ex else 10]))
    elif mode=='tail': out('\n'.join(','.join(r) for r in [h]+data[-(int(ex[0]) if ex else 10):]))
    elif mode in ('select','drop'):
        cols=ex[0].split(','); idx=[i for i,x in enumerate(h) if (x in cols)==(mode=='select')]; out('\n'.join(','.join(r[i] for i in idx) for r in rows))
    elif mode=='sort':
        i=h.index(ex[0]); out('\n'.join(','.join(r) for r in [h]+sorted(data,key=lambda r:r[i])))
    elif mode=='unique':
        i=h.index(ex[0]); seen=set(); keep=[]
        for r in data:
            if r[i] not in seen: seen.add(r[i]); keep.append(r)
        out('\n'.join(','.join(r) for r in [h]+keep))
    elif mode in ('filter-eq','filter-regex'):
        i=h.index(ex[0]); pred=(lambda x:x==ex[1]) if mode=='filter-eq' else (lambda x:re.search(ex[1],x)!=None); out('\n'.join(','.join(r) for r in [h]+[r for r in data if pred(r[i])]))
    elif mode in ('stats','sum','mean','min','max'):
        i=h.index(ex[0]); vals=[float(r[i]) for r in data if r[i] not in ('','NA','null')]; d={'count':len(vals),'sum':sum(vals),'mean':statistics.fmean(vals) if vals else None,'min':min(vals) if vals else None,'max':max(vals) if vals else None}; out(d if mode=='stats' else d[mode])
    elif mode=='transpose': out('\n'.join(','.join(r) for r in zip(*rows)))
    elif mode=='to-json': out([dict(zip(h,r)) for r in data])
    elif mode=='from-json':
        arr=json.loads(txt(args)); keys=list(arr[0].keys()) if arr else []; o=io.StringIO(); w=csv.DictWriter(o,fieldnames=keys); w.writeheader(); w.writerows(arr); print(o.getvalue(),end='')
    elif mode=='dialect':
        d=csv.Sniffer().sniff(txt(args)[:4096]); out({'delimiter':d.delimiter,'quotechar':d.quotechar,'escapechar':d.escapechar,'doublequote':d.doublequote})

def entropy(d):
    if not d:return 0.0
    c=Counter(d); n=len(d); return -sum((v/n)*math.log2(v/n) for v in c.values())
def do_file(tool,args):
    mode=tool.split('file-',1)[1]; p=pathlib.Path(args[0]) if args else pathlib.Path('.')
    if mode=='size': out(p.stat().st_size)
    elif mode=='entropy': out(entropy(p.read_bytes()))
    elif mode=='strings': out('\n'.join(x.decode('ascii','ignore') for x in re.findall(rb'[ -~]{4,}',p.read_bytes())))
    elif mode=='hexdump':
        d=p.read_bytes(); out('\n'.join(f'{i:08x}  '+ ' '.join(f'{b:02x}' for b in d[i:i+16]) for i in range(0,len(d),16)))
    elif mode=='magic': out(p.read_bytes()[:16].hex())
    elif mode=='lines': out(len(p.read_text(errors='replace').splitlines()))
    elif mode=='words': out(len(p.read_text(errors='replace').split()))
    elif mode=='duplicates':
        seen={}; dup=[]
        for f in p.rglob('*'):
            if f.is_file():
                h=hashlib.sha256(f.read_bytes()).hexdigest(); dup.append((h,str(f))) if h in seen else seen.setdefault(h,str(f))
        out([{'hash':h,'first':seen[h],'duplicate':f} for h,f in dup])
    elif mode=='find-name': out([str(x) for x in p.rglob(args[1])])
    elif mode=='find-size':
        m=int(args[1]); out([str(x) for x in p.rglob('*') if x.is_file() and x.stat().st_size>=m])
    elif mode=='tree': out('\n'.join(str(x.relative_to(p)) for x in sorted(p.rglob('*'))))
    elif mode in ('largest','newest','oldest'):
        fs=[x for x in p.rglob('*') if x.is_file()]; key=(lambda x:x.stat().st_size) if mode=='largest' else (lambda x:x.stat().st_mtime); fs=sorted(fs,key=key,reverse=mode!='oldest')[:int(args[1]) if len(args)>1 else 20]; out([{'path':str(x),'size':x.stat().st_size,'mtime':x.stat().st_mtime} for x in fs])
    elif mode=='empty': out([str(x) for x in p.rglob('*') if x.is_file() and x.stat().st_size==0])
    elif mode=='permissions': out(oct(p.stat().st_mode & 0o7777))
    elif mode=='mtime': out(dt.datetime.fromtimestamp(p.stat().st_mtime,dt.timezone.utc).isoformat())
    elif mode=='crc32': out(f'{zlib.crc32(p.read_bytes()) & 0xffffffff:08x}')
    elif mode=='gzip': gzip.open(str(p)+'.gz','wb').write(p.read_bytes()); out(str(p)+'.gz')
    elif mode=='gunzip':
        q=p.with_suffix('') if p.suffix=='.gz' else pathlib.Path(str(p)+'.out'); q.write_bytes(gzip.open(p,'rb').read()); out(q)
    elif mode=='compare': out('same' if p.read_bytes()==pathlib.Path(args[1]).read_bytes() else 'different')
    elif mode=='basename': out(p.name)
    elif mode=='dirname': out(str(p.parent))
    elif mode=='extension': out(p.suffix)
    elif mode=='realpath': out(str(p.resolve()))

def do_net(tool,args):
    mode=tool.split('net-',1)[1]
    if mode=='ip-info':
        ip=ipaddress.ip_address(args[0]); out({'version':ip.version,'private':ip.is_private,'global':ip.is_global,'loopback':ip.is_loopback,'multicast':ip.is_multicast,'compressed':ip.compressed})
    elif mode=='cidr-info':
        n=ipaddress.ip_network(args[0],strict=False); out({'network':str(n.network_address),'broadcast':str(n.broadcast_address),'prefixlen':n.prefixlen,'num_addresses':n.num_addresses})
    elif mode=='cidr-contains': out(ipaddress.ip_address(args[1]) in ipaddress.ip_network(args[0],strict=False))
    elif mode=='cidr-hosts': out([str(x) for x in list(ipaddress.ip_network(args[0],strict=False).hosts())[:int(args[1]) if len(args)>1 else 256]])
    elif mode in ('url-parse','url-normalize'):
        u=urllib.parse.urlparse(args[0]); out({'scheme':u.scheme.lower(),'host':(u.hostname or '').lower(),'port':u.port,'path':u.path or '/','query':urllib.parse.parse_qs(u.query),'fragment':u.fragment}) if mode=='url-parse' else out(urllib.parse.urlunparse((u.scheme.lower(),(u.hostname or '').lower()+(f':{u.port}' if u.port else ''),u.path or '/',u.params,u.query,'')))
    elif mode in ('dns-a','dns-aaaa','resolve'):
        fam=socket.AF_INET if mode=='dns-a' else socket.AF_INET6 if mode=='dns-aaaa' else 0; out(sorted({x[4][0] for x in socket.getaddrinfo(args[0],None,fam)}))
    elif mode=='dns-reverse': out(socket.gethostbyaddr(args[0]))
    elif mode in ('port-check','tcp-ping'):
        host=args[0]; port=int(args[1]); t=time.time(); s=socket.create_connection((host,port),timeout=float(args[2]) if len(args)>2 else 3); s.close(); out({'open':True,'ms':round((time.time()-t)*1000,2)})
    elif mode.startswith('http-'):
        url=args[0]; req=urllib.request.Request(url,method='HEAD' if mode=='http-head' else 'GET',headers={'User-Agent':'OceanPower/1.0'}); r=urllib.request.urlopen(req,timeout=10)
        if mode=='http-status': out(r.status)
        elif mode=='http-headers': out(dict(r.headers.items()))
        elif mode=='http-head': out(dict(r.headers.items()))
        else: sys.stdout.buffer.write(r.read())
    elif mode in ('tls-cert','tls-expiry'):
        host=args[0]; port=int(args[1]) if len(args)>1 else 443; ctx=ssl.create_default_context(); s=ctx.wrap_socket(socket.create_connection((host,port),timeout=5),server_hostname=host); cert=s.getpeercert(); s.close(); out(cert if mode=='tls-cert' else cert.get('notAfter'))
    elif mode=='host-port-parse':
        host,sep,port=args[0].rpartition(':'); out({'host':host if sep else args[0],'port':int(port) if sep else None})
    elif mode=='ipv4-to-int': out(int(ipaddress.IPv4Address(args[0])))
    elif mode=='int-to-ipv4': out(str(ipaddress.IPv4Address(int(args[0]))))
    elif mode=='mac-normalize': out(':'.join(re.findall(r'[0-9a-fA-F]{2}',args[0])).lower())
    elif mode=='user-agent': out({'raw':' '.join(args),'mobile':bool(re.search(r'Android|iPhone|Mobile',' '.join(args),re.I))})
    elif mode=='query-encode': out(urllib.parse.urlencode(dict(x.split('=',1) for x in args)))
    elif mode=='query-decode': out(urllib.parse.parse_qs(args[0].lstrip('?')))

def parse_dt(s): return dt.datetime.fromisoformat(s.replace('Z','+00:00'))
def do_time(tool,args):
    mode=tool.split('time-',1)[1]; now=dt.datetime.now(dt.timezone.utc)
    if mode=='now-utc': out(now.isoformat())
    elif mode=='now-local': out(dt.datetime.now().astimezone().isoformat())
    elif mode=='epoch-now': out(int(time.time()))
    elif mode=='epoch-to-iso': out(dt.datetime.fromtimestamp(float(args[0]),dt.timezone.utc).isoformat())
    elif mode=='iso-to-epoch': out(parse_dt(args[0]).timestamp())
    elif mode=='rfc3339-normalize': out(parse_dt(args[0]).astimezone(dt.timezone.utc).isoformat().replace('+00:00','Z'))
    elif mode=='duration-seconds':
        m=re.fullmatch(r'(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?',args[0]); out(sum(float(x or 0)*k for x,k in zip(m.groups(),[86400,3600,60,1])))
    elif mode=='seconds-human':
        n=int(float(args[0])); d,n=divmod(n,86400); h,n=divmod(n,3600); m,s=divmod(n,60); out(f'{d}d {h}h {m}m {s}s')
    elif mode=='date-add-days': out((parse_dt(args[0])+dt.timedelta(days=float(args[1]))).isoformat())
    elif mode=='date-diff': out((parse_dt(args[1])-parse_dt(args[0])).total_seconds())
    elif mode=='weekday': out(parse_dt(args[0]).strftime('%A'))
    elif mode=='month-days': import calendar; out(calendar.monthrange(int(args[0]),int(args[1]))[1])
    elif mode=='leap-year': import calendar; out(calendar.isleap(int(args[0])))
    elif mode=='timezone-list': out(sorted(available_timezones()))
    elif mode=='timezone-convert': out(parse_dt(args[0]).astimezone(ZoneInfo(args[1])).isoformat())
    elif mode=='unix-ms-now': out(int(time.time()*1000))
    elif mode=='unix-ms-to-iso': out(dt.datetime.fromtimestamp(float(args[0])/1000,dt.timezone.utc).isoformat())
    elif mode=='iso-to-unix-ms': out(int(parse_dt(args[0]).timestamp()*1000))
    elif mode=='relative-age': out((now-parse_dt(args[0]).astimezone(dt.timezone.utc)).total_seconds())
    elif mode=='sleep-until':
        target=parse_dt(args[0]); sec=max(0,(target-dt.datetime.now(target.tzinfo)).total_seconds()); time.sleep(sec); out('done')

def do_id(tool,args):
    mode=tool.split('id-',1)[1]
    if mode=='uuid4': out(uuid.uuid4())
    elif mode=='uuid1': out(uuid.uuid1())
    elif mode=='uuid3-dns': out(uuid.uuid3(uuid.NAMESPACE_DNS,args[0]))
    elif mode=='uuid5-dns': out(uuid.uuid5(uuid.NAMESPACE_DNS,args[0]))
    elif mode=='token-hex': out(secrets.token_hex(int(args[0]) if args else 32))
    elif mode=='token-url': out(secrets.token_urlsafe(int(args[0]) if args else 32))
    elif mode=='token-base64': out(base64.b64encode(secrets.token_bytes(int(args[0]) if args else 32)).decode())
    elif mode=='nanoid-like':
        alpha='_-0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'; out(''.join(secrets.choice(alpha) for _ in range(int(args[0]) if args else 21)))
    elif mode=='random-int': out(secrets.randbelow(int(args[1])-int(args[0])+1)+int(args[0]))
    elif mode=='random-choice': out(secrets.choice(args))
    elif mode=='random-bytes': sys.stdout.buffer.write(secrets.token_bytes(int(args[0]) if args else 32))
    elif mode=='ulid-like': out(f'{int(time.time()*1000):012x}'+secrets.token_hex(10))
    elif mode=='snowflake-like': out((int(time.time()*1000)-1609459200000)<<22 | secrets.randbits(22))
    elif mode=='hash-id': out(hashlib.sha256(' '.join(args).encode()).hexdigest()[:16])
    elif mode=='slug-id': out(re.sub(r'[^a-z0-9]+','-',' '.join(args).lower()).strip('-'))

def do_binary(tool,args):
    mode=tool.split('binary-',1)[1]; p=pathlib.Path(args[0])
    if mode=='zip-list': out(zipfile.ZipFile(p).namelist())
    elif mode=='zip-extract': zipfile.ZipFile(p).extractall(args[1] if len(args)>1 else '.'); out('ok')
    elif mode=='zip-test': out(zipfile.ZipFile(p).testzip() or 'ok')
    elif mode=='tar-list': out(tarfile.open(p).getnames())
    elif mode=='gzip-info': out({'compressed':p.stat().st_size,'uncompressed':len(gzip.open(p,'rb').read())})
    elif mode=='elf-header':
        d=p.read_bytes()[:64]
        if d[:4]!=b'\x7fELF': raise SystemExit('not ELF')
        out({'class':32 if d[4]==1 else 64,'endian':'little' if d[5]==1 else 'big','type':int.from_bytes(d[16:18],'little'),'machine':int.from_bytes(d[18:20],'little'),'entry':hex(int.from_bytes(d[24:32] if d[4]==2 else d[24:28],'little'))})
    elif mode=='png-info':
        d=p.read_bytes()
        if d[:8]!=b'\x89PNG\r\n\x1a\n': raise SystemExit('not PNG')
        w,h=struct.unpack('>II',d[16:24]); out({'width':w,'height':h})
    elif mode=='jpeg-info':
        d=p.read_bytes(); i=2; w=h=None
        while i<len(d)-9:
            if d[i]!=0xff: i+=1; continue
            m=d[i+1]; ln=int.from_bytes(d[i+2:i+4],'big')
            if m in range(0xc0,0xc4): h=int.from_bytes(d[i+5:i+7],'big'); w=int.from_bytes(d[i+7:i+9],'big'); break
            i+=2+ln
        out({'width':w,'height':h})
    elif mode=='pdf-info':
        d=p.read_bytes(); out({'pdf':d.startswith(b'%PDF-'),'version':d[:8].decode(errors='ignore'),'pages_hint':len(re.findall(rb'/Type\s*/Page\b',d))})
    elif mode=='sqlite-tables':
        con=sqlite3.connect(p); out([r[0] for r in con.execute("select name from sqlite_master where type='table' order by name")]); con.close()
    elif mode=='sqlite-schema':
        con=sqlite3.connect(p); out([r[0] for r in con.execute("select sql from sqlite_master where sql is not null order by name")]); con.close()
    elif mode=='strings': out('\n'.join(x.decode('ascii','ignore') for x in re.findall(rb'[ -~]{4,}',p.read_bytes())))
    elif mode=='hex': out(p.read_bytes().hex())
    elif mode=='base64': out(base64.b64encode(p.read_bytes()).decode())
    elif mode.startswith('apk-'):
        z=zipfile.ZipFile(p); names=z.namelist()
        if mode=='apk-list': out(names)
        elif mode=='apk-native-libs': out([x for x in names if x.startswith('lib/') and x.endswith('.so')])
        elif mode=='apk-dex-list': out([x for x in names if re.fullmatch(r'classes\d*\.dex',pathlib.PurePosixPath(x).name)])
        elif mode=='apk-assets': out([x for x in names if x.startswith('assets/')])
        elif mode=='apk-signature-files': out([x for x in names if x.upper().startswith('META-INF/') and x.upper().endswith(('.RSA','.DSA','.EC','.SF','.MF'))])
    elif mode=='zip-ratio':
        z=zipfile.ZipFile(p); a=sum(i.file_size for i in z.infolist()); b=sum(i.compress_size for i in z.infolist()); out({'uncompressed':a,'compressed':b,'ratio':(b/a if a else 0)})

def do_system(tool,args):
    mode=tool.split('system-',1)[1]
    if mode=='platform': out(platform.platform())
    elif mode=='cpu-count': out(os.cpu_count())
    elif mode=='loadavg': out(os.getloadavg() if hasattr(os,'getloadavg') else None)
    elif mode=='meminfo': out(pathlib.Path('/proc/meminfo').read_text() if pathlib.Path('/proc/meminfo').exists() else 'unavailable')
    elif mode=='cpuinfo': out(pathlib.Path('/proc/cpuinfo').read_text() if pathlib.Path('/proc/cpuinfo').exists() else 'unavailable')
    elif mode=='disk-usage':
        u=os.statvfs(args[0] if args else '.'); out({'total':u.f_frsize*u.f_blocks,'free':u.f_frsize*u.f_bavail,'used':u.f_frsize*(u.f_blocks-u.f_bfree)})
    elif mode=='env': out('\n'.join(f'{k}={v}' for k,v in sorted(os.environ.items())))
    elif mode=='env-json': out(dict(sorted(os.environ.items())))
    elif mode=='path': out(os.environ.get('PATH','').split(os.pathsep))
    elif mode=='which': out(shutil_which(args[0]))
    elif mode=='processes':
        ps=[]
        for x in pathlib.Path('/proc').iterdir() if pathlib.Path('/proc').exists() else []:
            if x.name.isdigit():
                try: ps.append({'pid':int(x.name),'cmd':(x/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')})
                except: pass
        out(ps)
    elif mode=='uptime': out(pathlib.Path('/proc/uptime').read_text().split()[0] if pathlib.Path('/proc/uptime').exists() else None)
    elif mode=='kernel': out(platform.release())
    elif mode=='hostname': out(socket.gethostname())
    elif mode=='cwd': out(os.getcwd())

def shutil_which(cmd):
    import shutil; return shutil.which(cmd)

def ver_tuple(s): return tuple((0,int(x)) if x.isdigit() else (1,x) for x in re.split(r'[.+-]',s))
def do_dev(tool,args):
    mode=tool.split('dev-',1)[1]
    if mode=='semver-compare': out(-1 if ver_tuple(args[0])<ver_tuple(args[1]) else 1 if ver_tuple(args[0])>ver_tuple(args[1]) else 0)
    elif mode=='semver-sort': out(sorted(args,key=ver_tuple))
    elif mode=='regex-test': out(bool(re.search(args[0],args[1])))
    elif mode=='regex-groups':
        m=re.search(args[0],args[1]); out({'groups':m.groups(),'groupdict':m.groupdict()} if m else None)
    elif mode=='diff-unified': out('\n'.join(difflib.unified_diff(read_text(args[0]).splitlines(),read_text(args[1]).splitlines(),fromfile=args[0],tofile=args[1],lineterm='')))
    elif mode=='json-escape': out(json.dumps(' '.join(args)))
    elif mode=='shell-quote': out(' '.join(shlex.quote(x) for x in args))
    elif mode=='int-base': out(format(int(args[0],int(args[1])), {'2':'b','8':'o','10':'d','16':'x'}[args[2]]))
    elif mode=='bytes-human':
        n=float(args[0]); units=['B','KiB','MiB','GiB','TiB']; i=0
        while n>=1024 and i<len(units)-1: n/=1024;i+=1
        out(f'{n:.2f} {units[i]}')
    elif mode=='bytes-parse':
        m=re.fullmatch(r'([0-9.]+)\s*(B|KB|KIB|MB|MIB|GB|GIB|TB|TIB)?',args[0].upper()); mult={'B':1,'KB':1000,'KIB':1024,'MB':1000**2,'MIB':1024**2,'GB':1000**3,'GIB':1024**3,'TB':1000**4,'TIB':1024**4,None:1}; out(int(float(m.group(1))*mult[m.group(2)]))

def main():
    if len(sys.argv)<2 or sys.argv[1] in ('-h','--help'): print('Ocean Power Core: invoke through an ocean-pwr-* package'); return
    if sys.argv[1] in ('-v','--version'): print(VERSION); return
    tool=sys.argv[1].removeprefix('ocean-pwr-'); args=sys.argv[2:]
    try:
        if tool.startswith('hash-'): do_hash(tool,args)
        elif tool.startswith('hmac-'): do_hmac(tool,args)
        elif tool.startswith('encode-'): encdec(tool,args,False)
        elif tool.startswith('decode-'): encdec(tool,args,True)
        elif tool.startswith('text-'): do_text(tool,args)
        elif tool.startswith('json-'): do_json(tool,args)
        elif tool.startswith('csv-'): do_csv(tool,args)
        elif tool.startswith('file-'): do_file(tool,args)
        elif tool.startswith('net-'): do_net(tool,args)
        elif tool.startswith('time-'): do_time(tool,args)
        elif tool.startswith('id-'): do_id(tool,args)
        elif tool.startswith('binary-'): do_binary(tool,args)
        elif tool.startswith('system-'): do_system(tool,args)
        elif tool.startswith('dev-'): do_dev(tool,args)
        else: raise SystemExit(f'unknown tool: {tool}')
    except (IndexError,KeyError,ValueError,TypeError,OSError,json.JSONDecodeError) as e:
        raise SystemExit(f'{tool}: {e}')
if __name__=='__main__': main()
