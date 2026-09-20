#!/usr/bin/env python3
from __future__ import annotations
import sys,json,hashlib,math,random,urllib.parse,base64,re,time
from pathlib import Path
VERSION="2.0.0"
def out(x):print(json.dumps(x,indent=2,sort_keys=True,default=str))
def die(x,c=2):print(x,file=sys.stderr);raise SystemExit(c)
def rt(a):return Path(a[0]).read_text(errors="replace") if a and Path(a[0]).exists() else (" ".join(a) if a else sys.stdin.read())
def h(x):return hashlib.sha256(x if isinstance(x,bytes) else str(x).encode()).digest()
def raftlog(a):
    x=json.loads(rt(a));rows=x if isinstance(x,list) else x.get("entries",[]);out({"entries":rows,"last_index":max([r.get("index",0) for r in rows],default=0),"last_term":rows[-1].get("term") if rows else None})
def raftvote(a):
    if len(a)<3:die("VOTERS TERM candidateTerm[:upToDate]...")
    n=int(a[0]);term=int(a[1]);votes=0;details=[]
    for s in a[2:]:
        p=s.split(":");ct=int(p[0]);uptodate=(len(p)<2 or p[1].lower() in ("1","true","yes"));grant=ct>=term and uptodate;votes+=grant;details.append({"candidate_term":ct,"up_to_date":uptodate,"granted":grant})
    out({"votes":votes,"majority":n//2+1,"elected":votes>=n//2+1,"details":details})
def paxos(a):
    if len(a)<2:die("ROUND NODE")
    r,n=int(a[0]),int(a[1]);out({"proposal_number":(r<<32)|n,"round":r,"node":n})
def gossip(a):
    peers=a;seed=int(hashlib.sha256("|".join(peers).encode()).hexdigest()[:8],16);rng=random.Random(seed);sample=rng.sample(peers,min(3,len(peers))) if peers else [];out({"fanout":sample})
def swim(a):
    if len(a)<3:die("PROBE_INTERVAL MISSED RTT")
    interval,missed,rtt=float(a[0]),int(a[1]),float(a[2]);timeout=interval*max(1,missed)+rtt*3;out({"suspicion_timeout":timeout,"suspect":missed>=3})
def xor(a):
    x=int(a[0],16);y=int(a[1],16);d=x^y;out({"distance_hex":hex(d),"bucket":d.bit_length()-1 if d else 0})
def kademlia(a):
    target=int(a[0],16);peers=[(p,int(p,16)^target) for p in a[1:]];out([{"peer":p,"distance":hex(d)} for p,d in sorted(peers,key=lambda x:x[1])])
def bucket(a):
    if len(a)<2:die("K PEER...")
    k=int(a[0]);out({"kept":a[1:1+k],"replacement":a[1+k:]})
def merkle_levels(items):
    cur=[h(x) for x in items] or [h(b"")];levels=[cur]
    while len(cur)>1:
        if len(cur)%2:cur=cur+[cur[-1]]
        cur=[h(cur[i]+cur[i+1]) for i in range(0,len(cur),2)];levels.append(cur)
    return levels
def merkle(a):out({"root":merkle_levels(a)[-1][0].hex(),"leaves":len(a)})
def proof(a):
    if len(a)<2:die("INDEX item...")
    idx=int(a[0]);items=a[1:];levels=merkle_levels(items);proof=[];i=idx
    for level in levels[:-1]:
        ext=level+[level[-1]] if len(level)%2 else level;sib=i^1;proof.append({"side":"left" if sib<i else "right","hash":ext[sib].hex()});i//=2
    out({"root":levels[-1][0].hex(),"proof":proof})
def mmr(a):
    n=len(a);peaks=[];size=1
    while n:
        if n&1:peaks.append(size)
        n>>=1;size*=2
    out({"leaves":len(a),"peak_sizes":list(reversed(peaks)),"root_hint":hashlib.sha256("".join(a).encode()).hexdigest()})
def sparse(a):
    key=a[0] if a else "";value=a[1] if len(a)>1 else "";leaf=h(b"\0"+key.encode()+value.encode());out({"key_hash":h(key).hex(),"leaf_hash":leaf.hex(),"depth":256})
def vclock(a):
    if len(a)<2:die('JSON_A JSON_B')
    x=json.loads(a[0]);y=json.loads(a[1]);keys=set(x)|set(y);le=all(x.get(k,0)<=y.get(k,0) for k in keys);ge=all(x.get(k,0)>=y.get(k,0) for k in keys)
    rel="equal" if le and ge else "before" if le else "after" if ge else "concurrent";out({"relation":rel})
def lamport(a):
    local=int(a[0]);recv=int(a[1]) if len(a)>1 else None;out({"next":max(local,recv if recv is not None else local)+1})
def gcounter(a):
    states=[json.loads(x) for x in a];keys=set().union(*(s.keys() for s in states)) if states else set();merged={k:max(int(s.get(k,0)) for s in states) for k in keys};out({"state":merged,"value":sum(merged.values())})
def pncounter(a):
    states=[json.loads(x) for x in a];pos={};neg={}
    for s in states:
        for k,v in s.get("p",{}).items():pos[k]=max(pos.get(k,0),int(v))
        for k,v in s.get("n",{}).items():neg[k]=max(neg.get(k,0),int(v))
    out({"p":pos,"n":neg,"value":sum(pos.values())-sum(neg.values())})
def lww(a):
    rows=[json.loads(x) for x in a];winner=max(rows,key=lambda r:(r.get("ts",0),str(r.get("node","")))) if rows else None;out(winner)
def orset(a):
    states=[json.loads(x) for x in a];adds={};rem=set()
    for s in states:
        for e,tags in s.get("adds",{}).items():adds.setdefault(e,set()).update(tags)
        rem.update(s.get("removes",[]))
    out({"elements":sorted(e for e,tags in adds.items() if any(t not in rem for t in tags))})
def bloom(a):
    if len(a)<2:die("N FALSE_POSITIVE_RATE")
    n=float(a[0]);p=float(a[1]);m=math.ceil(-n*math.log(p)/(math.log(2)**2));k=max(1,round(m/n*math.log(2)));out({"bits":m,"hashes":k,"bits_per_item":m/n})
def counting(a):
    size=int(a[0]);vals=a[1:];arr=[0]*size
    for v in vals:
        for salt in range(3):arr[int.from_bytes(h(str(salt)+v)[:8],"big")%size]+=1
    out({"size":size,"nonzero":sum(x>0 for x in arr),"max_count":max(arr,default=0)})
def cuckoo(a):
    cap=int(a[0]);items=a[1:];load=len(items)/cap if cap else 1;out({"capacity":cap,"items":len(items),"load_factor":load,"healthy":load<0.95})
def hll(a):
    vals=a; p=10;m=1<<p;reg=[0]*m
    for v in vals:
        x=int.from_bytes(h(v)[:8],"big");idx=x>>(64-p);w=(x<<p)&((1<<64)-1);rho=(64-p)-w.bit_length()+1 if w else 64-p+1;reg[idx]=max(reg[idx],rho)
    alpha=.7213/(1+1.079/m);est=alpha*m*m/sum(2.0**-r for r in reg);out({"estimate":round(est),"actual_input_count":len(vals)})
def cms(a):
    if len(a)<2:die("WIDTH item...")
    w=int(a[0]);d=4;table=[[0]*w for _ in range(d)]
    for item in a[1:]:
        for i in range(d):table[i][int.from_bytes(h(str(i)+item)[:8],"big")%w]+=1
    est={item:min(table[i][int.from_bytes(h(str(i)+item)[:8],"big")%w] for i in range(d)) for item in set(a[1:])};out(est)
def ring(a):
    if len(a)<2:die("KEY NODE...")
    key=a[0];nodes=a[1:];tokens=sorted((int.from_bytes(h(n)[:8],"big"),n) for n in nodes);kh=int.from_bytes(h(key)[:8],"big");pick=next((n for t,n in tokens if t>=kh),tokens[0][1] if tokens else None);out({"key":key,"node":pick})
def rendezvous(a):
    key=a[0];nodes=a[1:];scores=[(int.from_bytes(h(key+"|"+n)[:8],"big"),n) for n in nodes];out({"node":max(scores)[1] if scores else None,"scores":sorted(scores,reverse=True)})
def vnode(a):
    if len(a)<2:die("VNODES NODE...")
    v=int(a[0]);nodes=a[1:];tokens=[]
    for n in nodes:
        for i in range(v):tokens.append((int.from_bytes(h(f"{n}:{i}")[:8],"big"),n))
    tokens.sort();counts={n:0 for n in nodes}
    for _,n in tokens:counts[n]+=1
    out({"tokens":len(tokens),"distribution":counts})
def bdecode(data,pos=0):
    c=data[pos:pos+1]
    if c==b"i":
        e=data.index(b"e",pos);return int(data[pos+1:e]),e+1
    if c==b"l":
        pos+=1;v=[]
        while data[pos:pos+1]!=b"e":x,pos=bdecode(data,pos);v.append(x)
        return v,pos+1
    if c==b"d":
        pos+=1;v={}
        while data[pos:pos+1]!=b"e":k,pos=bdecode(data,pos);x,pos=bdecode(data,pos);v[k.decode(errors="replace") if isinstance(k,bytes) else str(k)]=x
        return v,pos+1
    colon=data.index(b":",pos);n=int(data[pos:colon]);start=colon+1;return data[start:start+n],start+n
def bencode_cmd(a):
    b=Path(a[0]).read_bytes() if a and Path(a[0]).exists() else a[0].encode();x,_=bdecode(b);out(x)
def torrent(a):
    b=Path(a[0]).read_bytes();x,_=bdecode(b);info=x.get("info",{}) if isinstance(x,dict) else {};out({"announce":x.get("announce"),"piece_length":info.get("piece length"),"name":info.get("name"),"pieces_bytes":len(info.get("pieces",b"")) if isinstance(info,dict) else 0})
def piece(a):
    if len(a)<2:die("FILE EXPECTED_SHA1")
    got=hashlib.sha1(Path(a[0]).read_bytes()).hexdigest();out({"sha1":got,"match":got.lower()==a[1].lower()})
def magnet(a):
    if not a:die("BTIH [NAME] [TRACKER...]")
    q=[("xt","urn:btih:"+a[0])]
    if len(a)>1:q.append(("dn",a[1]))
    for t in a[2:]:q.append(("tr",t))
    print("magnet:?"+urllib.parse.urlencode(q))
def ipni(a):out({"cid":a[0] if a else None,"provider":a[1] if len(a)>1 else None,"context_id":hashlib.sha256("|".join(a).encode()).hexdigest()[:32]})
def multiaddr(a):
    s=a[0] if a else "";parts=[x for x in s.split("/") if x];rows=[]
    i=0
    while i<len(parts):
        proto=parts[i];val=parts[i+1] if i+1<len(parts) and proto not in {"quic","quic-v1","ws","wss","p2p-circuit"} else None;rows.append({"protocol":proto,"value":val});i+=2 if val is not None else 1
    out(rows)
B58="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58decode(s):
    n=0
    for c in s:n=n*58+B58.index(c)
    return n.to_bytes((n.bit_length()+7)//8,"big")
def peerid(a):
    b=b58decode(a[0]);out({"bytes":len(b),"hex":b.hex(),"multihash_code":b[0] if b else None,"digest_length":b[1] if len(b)>1 else None})
def noise(a):
    pat=a[0] if a else "XX";msgs={"NN":2,"NK":2,"NX":2,"XN":3,"XK":3,"XX":3,"IK":2,"IX":2};out({"pattern":pat,"messages":msgs.get(pat),"recognized":pat in msgs})
def topic(a):
    if len(a)<2:die("TOPIC SCORE")
    score=float(a[1]);out({"topic":a[0],"score":score,"mesh_eligible":score>=0,"graylisted":score<-100})
def cubic(a):
    cwnd=float(a[0]);wmax=float(a[1]);t=float(a[2]);c=.4;k=((wmax-cwnd)/c)**(1/3) if wmax>=cwnd else 0;out({"cwnd":c*((t-k)**3)+wmax,"K":k})
def bbr(a):
    rates=[float(x) for x in a[:-1]];rtt=float(a[-1]);bw=max(rates) if rates else 0;out({"btlbw":bw,"rtprop":rtt,"bdp":bw*rtt})
def sync(a):
    x=[int(v) for v in a[0].split(",")];y=[int(v) for v in a[1].split(",")];out({"missing_on_a":sorted(set(y)-set(x)),"missing_on_b":sorted(set(x)-set(y))})
def quorum(a):
    n=int(a[0]);out({"nodes":n,"majority":n//2+1,"crash_faults":(n-1)//2,"byzantine_faults":(n-1)//3})
def splitbrain(a):
    n=int(a[0]);parts=[int(x) for x in a[1:]];maj=n//2+1;out({"majority":maj,"partitions":parts,"multiple_majorities":sum(p>=maj for p in parts)>1,"available_partitions":sum(p>=maj for p in parts)})
def byz(a):
    n=int(a[0]);f=(n-1)//3;out({"nodes":n,"max_byzantine_faults":f,"required_for_f_faults":3*f+1})
def watermark(a):
    vals=[int(x) for x in a];out({"watermark":min(vals) if vals else None,"lag":max(vals)-min(vals) if vals else 0})
def span(a):
    t=a[0].lower() if a else "";s=a[1].lower() if len(a)>1 else "";out({"trace_id_valid":bool(re.fullmatch(r"[0-9a-f]{32}",t)) and t!="0"*32,"span_id_valid":bool(re.fullmatch(r"[0-9a-f]{16}",s)) and s!="0"*16})
def traceparent(a):
    s=a[0];m=re.fullmatch(r"([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})",s,re.I);out({"valid":bool(m),"version":m.group(1) if m else None,"trace_id":m.group(2) if m else None,"span_id":m.group(3) if m else None,"flags":m.group(4) if m else None})
def b3(a):
    if len(a)<2:die("TRACEID SPANID")
    out({"b3":f"{a[0]}-{a[1]}-1","X-B3-TraceId":a[0],"X-B3-SpanId":a[1],"X-B3-Sampled":"1"})
def jaeger(a):out(json.loads(rt(a)))
def zipkin(a):
    x=json.loads(rt(a));rows=x if isinstance(x,list) else [x];out([{"traceId":r.get("traceId"),"id":r.get("id"),"duration":r.get("duration"),"annotations":len(r.get("annotations",[]))} for r in rows])
def otlp(a):
    b=Path(a[0]).read_bytes();out({"bytes":len(b),"nonempty":bool(b),"sha256":hashlib.sha256(b).hexdigest()})
def tokenbucket(a):
    if len(a)<5:die("CAPACITY TOKENS RATE ELAPSED COST")
    cap,tok,rate,elapsed,cost=map(float,a[:5]);tok=min(cap,tok+rate*elapsed);ok=tok>=cost;out({"allowed":ok,"tokens_after":tok-cost if ok else tok})
def leaky(a):
    if len(a)<4:die("CAPACITY LEVEL LEAK_RATE ELAPSED [IN]")
    cap,level,rate,elapsed=map(float,a[:4]);incoming=float(a[4]) if len(a)>4 else 0;level=max(0,level-rate*elapsed);overflow=max(0,level+incoming-cap);level=min(cap,level+incoming);out({"level":level,"overflow":overflow})
COMMANDS={"raft-term-log-viewer":raftlog,"raft-vote-simulator":raftvote,"paxos-ballot-calculator":paxos,"gossip-cluster-ping":gossip,"swim-membership-check":swim,"dht-kademlia-routing":kademlia,"kademlia-distance-xor":xor,"dht-bucket-balancer":bucket,"merkle-tree-hasher":merkle,"merkle-proof-generator":proof,"merkle-mountain-range":mmr,"sparse-merkle-tree":sparse,"vector-clock-comparator":vclock,"lamport-timestamp-calc":lamport,"crdt-g-counter-cli":gcounter,"crdt-pn-counter-tool":pncounter,"crdt-lww-register":lww,"crdt-or-set-resolver":orset,"bloom-filter-hasher":bloom,"counting-bloom-filter":counting,"cuckoo-filter-cli":cuckoo,"hyperloglog-cardinality":hll,"count-min-sketch-calc":cms,"consistent-hash-ring":ring,"rendezvous-hash-eval":rendezvous,"virtual-node-balancer":vnode,"p2p-bit-torrent-bencode":bencode_cmd,"torrent-metainfo-parser":torrent,"torrent-piece-hash-chk":piece,"magnet-link-builder":magnet,"ipni-network-indexer":ipni,"libp2p-multiaddr-parse":multiaddr,"libp2p-peer-id-inspect":peerid,"noise-protocol-handshake":noise,"gossipsub-topic-filter":topic,"quic-congestion-cubic":cubic,"bbr-bandwidth-estimator":bbr,"replicated-state-sync":sync,"quorum-majority-calc":quorum,"split-brain-detector":splitbrain,"byzantine-fault-ratio":byz,"epoch-watermark-tracker":watermark,"distributed-trace-span":span,"w3c-trace-context-parse":traceparent,"b3-trace-header-inject":b3,"jaeger-thrift-exporter":jaeger,"zipkin-span-json-view":zipkin,"opentelemetry-collector":otlp,"rate-limiter-token-bucket":tokenbucket,"leaky-bucket-algorithm":leaky}
def main():
    if len(COMMANDS)!=50:die(f"command count {len(COMMANDS)}")
    p=Path(sys.argv[0]).name
    if p in COMMANDS:cmd,args=p,sys.argv[1:]
    else:
        if len(sys.argv)<2 or sys.argv[1] in ("-h","--help"):print("OceanStudio functional shard 23");print("\n".join(sorted(COMMANDS)));return
        if sys.argv[1] in ("-v","--version"):print(VERSION);return
        cmd,args=sys.argv[1],sys.argv[2:]
    if cmd not in COMMANDS:die("unknown command: "+cmd)
    COMMANDS[cmd](args)
if __name__=="__main__":main()
