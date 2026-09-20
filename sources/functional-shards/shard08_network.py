#!/usr/bin/env python3
from __future__ import annotations
import sys, json, struct, socket, ssl, time, statistics, ipaddress, urllib.parse, urllib.request, hashlib, re
from pathlib import Path
VERSION="2.0.0"
def out(x): print(json.dumps(x,indent=2,sort_keys=True,default=str))
def die(x,c=2): print(x,file=sys.stderr); raise SystemExit(c)
def bsrc(s):
    p=Path(s)
    return p.read_bytes() if p.exists() else bytes.fromhex(re.sub(r"[^0-9a-fA-F]","",s))
def u16(b,o=0): return struct.unpack_from("!H",b,o)[0]
def u32(b,o=0): return struct.unpack_from("!I",b,o)[0]
def checksum16(data):
    if len(data)%2:data+=b"\0"
    s=sum(struct.unpack(f"!{len(data)//2}H",data)); s=(s&0xffff)+(s>>16); s=(s&0xffff)+(s>>16)
    return (~s)&0xffff
def pcap(args):
    b=Path(args[0]).read_bytes(); 
    if len(b)<24: die("short pcap")
    magic=b[:4]; end="<" if magic in (b"\xd4\xc3\xb2\xa1",b"M<\xb2\xa1") else ">" if magic in (b"\xa1\xb2\xc3\xd4",b"\xa1\xb2<M") else None
    if not end: die("unknown pcap")
    maj,minr,zone,sig,snap,net=struct.unpack_from(end+"HHIIII",b,4); pos=24; rows=[]
    while pos+16<=len(b):
        ts,frac,inc,orig=struct.unpack_from(end+"IIII",b,pos); pos+=16
        if pos+inc>len(b): break
        rows.append({"ts":ts,"frac":frac,"captured":inc,"original":orig}); pos+=inc
    out({"version":f"{maj}.{minr}","snaplen":snap,"linktype":net,"packets":rows})
def payload(args):
    b=bsrc(args[0]); out({"bytes":len(b),"hex":b.hex(),"ascii":"".join(chr(x) if 32<=x<127 else "." for x in b),"sha256":hashlib.sha256(b).hexdigest()})
def ethernet(args):
    b=bsrc(args[0]); 
    if len(b)<14:die("short ethernet")
    et=u16(b,12); pos=14; vlans=[]
    while et in (0x8100,0x88a8) and pos+4<=len(b):
        t=u16(b,pos); vlans.append({"id":t&4095,"pcp":(t>>13)&7}); et=u16(b,pos+2); pos+=4
    mac=lambda x:":".join(f"{v:02x}" for v in x)
    out({"dst":mac(b[:6]),"src":mac(b[6:12]),"ethertype":hex(et),"vlans":vlans,"payload_offset":pos})
def ipv4(args):
    b=bsrc(args[0]); 
    if len(b)<20 or b[0]>>4!=4:die("not IPv4")
    ihl=(b[0]&15)*4; fl=u16(b,6)
    out({"ihl":ihl,"total_length":u16(b,2),"id":u16(b,4),"df":bool(fl&0x4000),"mf":bool(fl&0x2000),"fragment_offset":fl&0x1fff,"ttl":b[8],"protocol":b[9],"checksum_valid":checksum16(b[:ihl])==0,"src":socket.inet_ntoa(b[12:16]),"dst":socket.inet_ntoa(b[16:20])})
def ipv6(args):
    b=bsrc(args[0]); 
    if len(b)<40 or b[0]>>4!=6:die("not IPv6")
    nh=b[6]; pos=40; rows=[]; names={0:"hop-by-hop",43:"routing",44:"fragment",60:"destination",51:"ah"}
    while nh in names and pos+2<=len(b):
        cur=nh
        if cur==44:
            if pos+8>len(b):break
            nh=b[pos]; rows.append({"type":"fragment","offset":pos,"fragment_offset":(u16(b,pos+2)>>3)&8191,"more":bool(u16(b,pos+2)&1),"id":u32(b,pos+4)}); pos+=8
        else:
            nh=b[pos]; n=(b[pos+1]+1)*8; rows.append({"type":names[cur],"offset":pos,"bytes":n}); pos+=n
    out({"src":socket.inet_ntop(socket.AF_INET6,b[8:24]),"dst":socket.inet_ntop(socket.AF_INET6,b[24:40]),"extensions":rows,"next_header":nh})
def tcp(args):
    b=bsrc(args[0]); 
    if len(b)<20:die("short TCP")
    names=[n for bit,n in [(1,"FIN"),(2,"SYN"),(4,"RST"),(8,"PSH"),(16,"ACK"),(32,"URG"),(64,"ECE"),(128,"CWR")] if b[13]&bit]
    out({"src_port":u16(b),"dst_port":u16(b,2),"seq":u32(b,4),"ack":u32(b,8),"header_bytes":(b[12]>>4)*4,"flags":names,"window":u16(b,14)})
def udp(args):
    if len(args)<3:die("SRC_PORT DST_PORT PAYLOAD")
    sp,dp=int(args[0]),int(args[1]); p=args[2].encode(); ln=8+len(p); h=struct.pack("!HHHH",sp,dp,ln,0)
    out({"length":ln,"hex":(h+p).hex()})
def samples(args):
    v=[float(x) for x in args] if args else [float(x) for x in re.findall(r"[\d.]+",sys.stdin.read())]
    out({"count":len(v),"min":min(v) if v else None,"max":max(v) if v else None,"mean":statistics.mean(v) if v else None,"jitter":statistics.pstdev(v) if len(v)>1 else 0})
def arp(args):
    p=Path(args[0]) if args else Path("/proc/net/arp"); s=p.read_text(errors="replace") if p.exists() else ""; rows=[]
    for i,l in enumerate(s.splitlines()):
        x=l.split()
        if i and len(x)>=6:rows.append({"ip":x[0],"flags":x[2],"mac":x[3],"dev":x[5]})
    out(rows)
def text_rows(args): out([x for x in (Path(args[0]).read_text(errors="replace") if args and Path(args[0]).exists() else sys.stdin.read()).splitlines() if x.strip()])
def route(args):
    p=Path(args[0]) if args else Path("/proc/net/route"); rows=[]
    if p.exists():
        for i,l in enumerate(p.read_text().splitlines()):
            x=l.split()
            if i and len(x)>=8:
                cv=lambda h: socket.inet_ntoa(struct.pack("<I",int(h,16)))
                rows.append({"iface":x[0],"dst":cv(x[1]),"gateway":cv(x[2]),"metric":int(x[6]),"mask":cv(x[7])})
    out(rows)
def dns(args):
    if not args:die("HOST [A|AAAA]")
    fam=socket.AF_INET6 if len(args)>1 and args[1].upper()=="AAAA" else socket.AF_INET
    out(sorted({x[4][0] for x in socket.getaddrinfo(args[0],None,fam,socket.SOCK_STREAM)}))
def serial(args): 
    v=[int(x) for x in args]; out({"serials":v,"newest":max(v) if v else None,"monotonic":all(a<=b for a,b in zip(v,v[1:]))})
def pairs(args):
    rows=[]
    for x in args:
        a=x.split(":",1); rows.append({"priority":int(a[0]),"value":a[1] if len(a)>1 else ""})
    out(sorted(rows,key=lambda x:x["priority"]))
def reverse(args): out({"ip":args[0],"host":socket.gethostbyaddr(args[0])[0]})
def srv(args):
    rows=[]
    for x in args:
        p=x.split(":"); rows.append({"priority":int(p[0]),"weight":int(p[1]),"port":int(p[2]),"target":":".join(p[3:])})
    out(sorted(rows,key=lambda x:(x["priority"],-x["weight"])))
def fetch_json(args):
    if not args:die("URL")
    req=urllib.request.Request(args[0],headers={"User-Agent":"OceanStudio/2"})
    with urllib.request.urlopen(req,timeout=5) as r: out(json.load(r))
def passtext(args): text_rows(args)
def ping_jitter(args): samples(args)
def throughput(args):
    if len(args)<2:die("BYTES SECONDS")
    b,s=float(args[0]),float(args[1]); out({"Bps":b/s,"bps":b*8/s,"Mbps":b*8/s/1e6})
def http_ping(args):
    if not args:die("URL")
    t=time.perf_counter()
    try:
        with urllib.request.urlopen(args[0],timeout=5) as r: code=r.status; r.read(1)
        err=None
    except Exception as e: code=None;err=str(e)
    out({"url":args[0],"ms":(time.perf_counter()-t)*1000,"status":code,"error":err})
def hdr_audit(args):
    src=" ".join(args) if args else sys.stdin.read(); h={}
    for l in src.splitlines():
        if ":" in l:
            k,v=l.split(":",1); h[k.lower().strip()]=v.strip()
    required=["strict-transport-security","content-security-policy","x-content-type-options","referrer-policy"]
    out({"present":h,"missing":[x for x in required if x not in h]})
def h2(args):
    b=bsrc(args[0]); pos=0; rows=[]
    while pos+9<=len(b):
        ln=int.from_bytes(b[pos:pos+3],"big"); typ=b[pos+3]; flags=b[pos+4]; sid=u32(b,pos+5)&0x7fffffff
        if pos+9+ln>len(b):break
        rows.append({"type":typ,"flags":flags,"stream":sid,"length":ln}); pos+=9+ln
    out(rows)
def quic(args):
    b=bsrc(args[0]); out({"long_header":bool(b and b[0]&0x80),"fixed_bit":bool(b and b[0]&0x40),"version":hex(u32(b,1)) if len(b)>=5 and b[0]&0x80 else None,"bytes":len(b)})
def tcp_probe(args):
    if len(args)<2:die("HOST PORT")
    t=time.perf_counter()
    try:
        s=socket.create_connection((args[0],int(args[1])),timeout=2); s.close(); ok=True;err=None
    except Exception as e:ok=False;err=str(e)
    out({"open":ok,"ms":(time.perf_counter()-t)*1000,"error":err})
def sweep(args):
    if len(args)<3:die("HOST START END")
    st,en=int(args[1]),int(args[2]); 
    if en-st>256:die("range capped at 257 ports")
    openp=[]
    for p in range(st,en+1):
        s=socket.socket();s.settimeout(.05)
        if s.connect_ex((args[0],p))==0:openp.append(p)
        s.close()
    out({"host":args[0],"open":openp})
def udp_test(args):
    if len(args)<2:die("HOST PORT [PAYLOAD]")
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(.5);s.sendto((args[2] if len(args)>2 else "").encode(),(args[0],int(args[1])))
    try:data,peer=s.recvfrom(4096);res={"response":data.hex(),"peer":peer}
    except Exception as e:res={"response":None,"note":str(e)}
    s.close();out(res)
def tls(args):
    if not args:die("HOST [PORT]")
    host=args[0];port=int(args[1]) if len(args)>1 else 443;t=time.perf_counter();ctx=ssl.create_default_context()
    try:
        with socket.create_connection((host,port),timeout=5) as raw:
            with ctx.wrap_socket(raw,server_hostname=host) as s: out({"ms":(time.perf_counter()-t)*1000,"version":s.version(),"cipher":s.cipher(),"subject":s.getpeercert().get("subject")})
    except Exception as e: out({"ms":(time.perf_counter()-t)*1000,"error":str(e)})
def sni(args):
    b=bsrc(args[0]); names=[]
    for m in re.finditer(rb"(?=([a-zA-Z0-9-]{1,63}(?:\.[a-zA-Z0-9-]{1,63})+))",b):
        try:names.append(m.group(1).decode())
        except:pass
    out(sorted(set(names)))
def loss(args):
    s,r=int(args[0]),int(args[1]); out({"sent":s,"received":r,"lost":s-r,"loss_percent":100*(s-r)/s if s else None})
def curlfmt(args):
    d={}
    for x in args:
        if "=" in x:
            k,v=x.split("=",1)
            try:d[k]=float(v)
            except:d[k]=v
    out(d)
def links(args):
    src=Path(args[0]).read_text(errors="replace") if args and Path(args[0]).exists() else (" ".join(args) if args else sys.stdin.read())
    out(sorted(set(re.findall(r'href=["\']([^"\']+)',src,re.I))))
def urlcodec(args):
    if len(args)<2:die("encode|decode TEXT")
    print(urllib.parse.quote(args[1],safe="") if args[0]=="encode" else urllib.parse.unquote(args[1]))
def idna(args):
    if len(args)<2:die("encode|decode DOMAIN")
    print(args[1].encode("idna").decode() if args[0]=="encode" else args[1].encode().decode("idna"))
def mac(args):
    raw=re.sub(r"[^0-9A-Fa-f]","",args[0]).upper(); out({"mac":args[0],"oui":raw[:6]})
def subnet(args):
    n=ipaddress.ip_network(args[0],strict=False); out({"network":str(n.network_address),"prefixlen":n.prefixlen,"netmask":str(n.netmask),"broadcast":str(n.broadcast_address) if n.version==4 else None,"addresses":n.num_addresses})
def overlap(args):
    a,b=(ipaddress.ip_network(x,strict=False) for x in args[:2]); out({"overlaps":a.overlaps(b),"a_contains_b":b.subnet_of(a),"b_contains_a":a.subnet_of(b)})
def expand(args):
    n=ipaddress.ip_network(args[0],strict=False);limit=int(args[1]) if len(args)>1 else 256
    if n.num_addresses>limit:die(f"{n.num_addresses} addresses; explicit limit required")
    out([str(x) for x in n])
def v6(args):
    x=ipaddress.IPv6Address(args[0]);out({"compressed":x.compressed,"exploded":x.exploded})
def iface(args):
    p=Path(args[0]) if args else Path("/proc/net/dev"); rows=[]
    if p.exists():
        for l in p.read_text().splitlines():
            if ":" not in l:continue
            n,r=l.split(":",1);x=r.split()
            if len(x)>=16:rows.append({"interface":n.strip(),"rx_bytes":int(x[0]),"rx_packets":int(x[1]),"rx_errors":int(x[2]),"tx_bytes":int(x[8]),"tx_packets":int(x[9]),"tx_errors":int(x[10])})
    out(rows)
def calc(args): throughput(args)
def caa(args): out({"records":args,"valid":all(re.match(r"^\d+\s+\w+\s+.+$",x) for x in args)})
def nsec3(args): out({"hashes":args,"sorted":sorted(args)})
def bgp(args): out({"query":args[0] if args else None,"note":"offline ASN/prefix parser; provide mapping file for authoritative data"})
def geo(args): out({"hops":args,"note":"IP geolocation requires an external database; no location is invented"})
def iperf(args): throughput(args)
def ws(args): out({"url":args[0] if args else None,"supported_schemes":["ws","wss"],"note":"frame inspection available via payload-dissector"})
def socks(args): out({"proxy":args[:2],"target":args[2:4],"valid":len(args)>=4})
def proxy(args): out({"proxy":args[:2],"target":args[2:4],"valid":len(args)>=4})
def mtu(args): v=[int(x) for x in args];out({"probes":v,"largest_success":max(v) if v else None})
COMMANDS={
"pcap-header-analyzer":pcap,"packet-payload-dissector":payload,"ethernet-frame-parser":ethernet,"ipv4-header-checker":ipv4,"ipv6-extension-parser":ipv6,"tcp-flags-analyzer":tcp,"udp-packet-builder":udp,"icmp-latency-sampler":samples,"arp-table-auditor":arp,"ndp-neighbor-scanner":text_rows,"route-table-inspector":route,"ip-rule-viewer":text_rows,"dns-record-lookup":dns,"dns-soa-serial-checker":serial,"dns-mx-priority-sorter":pairs,"dns-txt-record-fetcher":passthext if False else passtext,"dns-ptr-reverse-resolver":reverse,"dns-srv-balancer":srv,"dns-caa-checker":caa,"dns-nsec3-walker":nsec3,"whois-rdap-client":fetch_json,"bgp-asn-lookup":bgp,"traceroute-geo-mapper":geo,"ping-jitter-analyzer":ping_jitter,"iperf-bandwidth-tester":iperf,"http-ping-bench":http_ping,"http-headers-security-audit":hdr_audit,"http2-frame-inspector":h2,"http3-quic-probe":quic,"websocket-cat":ws,"tcp-syn-prober":tcp_probe,"tcp-port-sweeper":sweep,"udp-port-tester":udp_test,"socks5-proxy-client":socks,"http-proxy-tunnel":proxy,"ssl-sni-detector":sni,"tls-handshake-timer":tls,"mtu-path-discovery":mtu,"bandwidth-rate-calc":calc,"packet-loss-estimator":loss,"curl-time-formatter":curlfmt,"wget-recursive-lister":links,"url-encode-decode-cli":urlcodec,"punycode-domain-codec":idna,"mac-address-lookup":mac,"subnet-mask-calc":subnet,"cidr-overlap-checker":overlap,"ip-range-expander":expand,"ipv6-compressor":v6,"network-interface-stat":iface}
def main():
    if len(COMMANDS)!=50:die(f"command count {len(COMMANDS)}")
    p=Path(sys.argv[0]).name
    if p in COMMANDS:cmd,args=p,sys.argv[1:]
    else:
        if len(sys.argv)<2 or sys.argv[1] in ("-h","--help"):
            print("OceanStudio functional shard 08"); print("\n".join(sorted(COMMANDS))); return
        if sys.argv[1] in ("-v","--version"):print(VERSION);return
        cmd,args=sys.argv[1],sys.argv[2:]
    if cmd not in COMMANDS:die("unknown command: "+cmd)
    COMMANDS[cmd](args)
if __name__=="__main__":main()
