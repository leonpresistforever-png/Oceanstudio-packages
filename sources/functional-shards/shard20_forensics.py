#!/usr/bin/env python3
from __future__ import annotations
import sys,json,re,math,hashlib,ipaddress,os,struct,base64,hmac,platform
from pathlib import Path
VERSION="2.0.0"
def out(x):print(json.dumps(x,indent=2,sort_keys=True,default=str))
def die(x,c=2):print(x,file=sys.stderr);raise SystemExit(c)
def rb(a):return Path(a[0]).read_bytes()
def rt(a):return Path(a[0]).read_text(errors="replace") if a and Path(a[0]).exists() else (" ".join(a) if a else sys.stdin.read())
def pcap_packets(path):
    b=Path(path).read_bytes()
    if b[:4]==b"\xd4\xc3\xb2\xa1":end="<"
    elif b[:4]==b"\xa1\xb2\xc3\xd4":end=">"
    else:die("unsupported pcap")
    p=24;rows=[]
    while p+16<=len(b):
        ts,frac,n,orig=struct.unpack_from(end+"IIII",b,p);p+=16
        if p+n>len(b):break
        rows.append((ts+frac/1e6,b[p:p+n]));p+=n
    return rows
def decode_l3(pkt):
    if len(pkt)<14:return None
    et=int.from_bytes(pkt[12:14],"big");o=14
    if et==0x8100 and len(pkt)>=18:et=int.from_bytes(pkt[16:18],"big");o=18
    if et!=0x0800 or len(pkt)<o+20:return None
    ip=pkt[o:];ihl=(ip[0]&15)*4;proto=ip[9];src=".".join(map(str,ip[12:16]));dst=".".join(map(str,ip[16:20]));return proto,src,dst,ip[ihl:]
def dns_extract(a):
    rows=[]
    for ts,p in pcap_packets(a[0]):
        x=decode_l3(p)
        if not x or x[0] not in (6,17):continue
        tr=x[3];sport=int.from_bytes(tr[:2],"big");dport=int.from_bytes(tr[2:4],"big")
        if 53 not in (sport,dport):continue
        pay=tr[8:] if x[0]==17 else tr[((tr[12]>>4)*4):]
        if len(pay)<12:continue
        qd=int.from_bytes(pay[4:6],"big");pos=12;qs=[]
        for _ in range(qd):
            labs=[]
            while pos<len(pay) and pay[pos]:
                n=pay[pos];pos+=1;labs.append(pay[pos:pos+n].decode(errors="replace"));pos+=n
            pos+=1
            if pos+4<=len(pay):qt=int.from_bytes(pay[pos:pos+2],"big");pos+=4;qs.append({"name":".".join(labs),"type":qt})
        rows.append({"ts":ts,"src":x[1],"dst":x[2],"questions":qs})
    out(rows)
def http_extract(a):
    rows=[]
    for ts,p in pcap_packets(a[0]):
        x=decode_l3(p)
        if not x or x[0]!=6:continue
        tr=x[3]
        if len(tr)<20:continue
        pay=tr[((tr[12]>>4)*4):]
        s=pay.decode(errors="ignore")
        m=re.match(r"(GET|POST|PUT|DELETE|HEAD|PATCH|OPTIONS)\s+(\S+)\s+HTTP/",s)
        if m:
            host=re.search(r"(?im)^Host:\s*(\S+)",s);ua=re.search(r"(?im)^User-Agent:\s*(.+)$",s)
            rows.append({"ts":ts,"method":m.group(1),"uri":m.group(2),"host":host.group(1) if host else None,"user_agent":ua.group(1).strip() if ua else None})
    out(rows)
def tls_hello(a):
    rows=[]
    for ts,p in pcap_packets(a[0]):
        x=decode_l3(p)
        if not x or x[0]!=6:continue
        tr=x[3]
        if len(tr)<25:continue
        pay=tr[((tr[12]>>4)*4):]
        if len(pay)>9 and pay[0]==22 and pay[5]==1:rows.append({"ts":ts,"src":x[1],"dst":x[2],"record_version":pay[1:3].hex(),"client_version":pay[9:11].hex(),"bytes":len(pay)})
    out(rows)
def credential(a):
    needles=re.compile(rb"(?i)(authorization:\s*basic\s+[A-Za-z0-9+/=]+|password=([^&\s]+)|passwd=([^&\s]+)|user(name)?=([^&\s]+))")
    hits=[]
    for ts,p in pcap_packets(a[0]):
        for m in needles.finditer(p):hits.append({"ts":ts,"offset":m.start(),"match":m.group(0)[:120].decode(errors="replace")})
    out({"findings":hits,"count":len(hits)})
def icmp(a):
    sizes=[]
    for ts,p in pcap_packets(a[0]):
        x=decode_l3(p)
        if x and x[0]==1:sizes.append(len(x[3]))
    out({"icmp_packets":len(sizes),"payload_sizes":sizes,"high_variance":len(set(sizes))>5})
def strings(a):
    b=rb(a);ascii=[x.decode(errors="replace") for x in re.findall(rb"[\x20-\x7e]{5,}",b)]
    utf=[m.group(0).decode("utf-16le",errors="replace") for m in re.finditer(rb"(?:[\x20-\x7e]\x00){5,}",b)]
    out({"ascii":ascii[:1000],"utf16le":utf[:500]})
def profile(a):
    s=rt(a);out({"banners":re.findall(r"Linux version [^\n]+|Windows [^\n]+|Darwin Kernel Version [^\n]+",s),"symbols":re.findall(r"\b[_A-Za-z]\w{5,}\b",s)[:500]})
def pagetable(a):
    if len(a)<2:die("VA PAGE_SHIFT")
    va=int(a[0],0);shift=int(a[1]);out({"virtual_address":hex(va),"page_number":va>>shift,"offset":va&((1<<shift)-1)})
def modsig(a):
    b=rb(a);marker=b"~Module signature appended~";out({"signed":marker in b,"marker_offset":b.rfind(marker)})
def rootsym(a):
    s=rt(a);names=["sys_call_table","security_ops","ftrace_ops","kprobe","do_sys_open","commit_creds"];out({"hits":{n:len(re.findall(r"\b"+re.escape(n)+r"\b",s)) for n in names}})
def hidden(a):
    proc={int(x.name) for x in Path("/proc").iterdir() if x.name.isdigit()};out({"visible_proc_pids":len(proc),"note":"non-root mode cannot authoritatively enumerate kernel-hidden processes"})
def maps(a):
    s=Path(a[0]).read_text() if a else Path("/proc/self/maps").read_text();rows=[]
    for l in s.splitlines():
        parts=l.split()
        if len(parts)>=2:
            perm=parts[1];path=parts[-1] if len(parts)>=6 else ""
            if "x" in perm and ("[heap]" in path or "[stack]" in path or path==""):rows.append(l)
    out({"executable_writable_or_anon":rows})
def injection(a):
    b=rb(a);patterns={"nop_sled":b"\x90"*16 in b,"elf_magic":b"\x7fELF" in b,"mz_magic":b"MZ" in b,"shell_strings":bool(re.search(rb"(?i)/bin/(sh|bash)|cmd\.exe|powershell",b))}
    out(patterns)
def codecave(a):
    b=rb(a);runs=[(m.start(),len(m.group(0))) for m in re.finditer(rb"\x00{64,}",b)];out({"zero_runs":runs[:500]})
def elfsec(a):
    b=rb(a);out({"elf":b[:4]==b"\x7fELF","got_strings":b.count(b".got"),"plt_strings":b.count(b".plt"),"sha256":hashlib.sha256(b).hexdigest()})
def ptrace(a):out({"ptrace_traceme_refs":len(re.findall(r"PTRACE_TRACEME|ptrace\s*\(",rt(a)))})
def envdiff(a):
    if len(a)<2:die("ENV_A ENV_B")
    def parse(p):return dict(x.split("=",1) for x in Path(p).read_text().splitlines() if "=" in x)
    x,y=parse(a[0]),parse(a[1]);out({"added":sorted(y.keys()-x.keys()),"removed":sorted(x.keys()-y.keys()),"changed":sorted(k for k in x.keys()&y.keys() if x[k]!=y[k])})
def preload(a):
    vals=[]
    if "LD_PRELOAD" in os.environ:vals+=os.environ["LD_PRELOAD"].split(":")
    if a and Path(a[0]).exists():vals+=[x for x in Path(a[0]).read_text().splitlines() if x.strip() and not x.startswith("#")]
    out({"entries":vals,"missing":[x for x in vals if x and not Path(x).exists()]})
def entropy_bytes(b):
    if not b:return 0
    return -sum((c/len(b))*math.log2(c/len(b)) for c in [b.count(bytes([i])) for i in range(256)] if c)
def entropy(a):
    b=rb(a);w=int(a[1]) if len(a)>1 else 4096;out([{"offset":i,"entropy":entropy_bytes(b[i:i+w])} for i in range(0,len(b),w)])
def packed(a):
    b=rb(a);e=entropy_bytes(b);out({"entropy":e,"upx":b"UPX!" in b or b"UPX0" in b,"packed_heuristic":e>7.2})
def upx(a):
    b=rb(a);out({"upx_magic":b"UPX!" in b or b"UPX0" in b,"offset":max(b.find(b"UPX!"),b.find(b"UPX0"))})
def rich(a):
    b=rb(a);p=b.find(b"Rich");out({"present":p>=0,"offset":p,"sha256":hashlib.sha256(b[max(0,p-128):p+4]).hexdigest() if p>=0 else None})
def imphash(a):
    s=rt(a).lower();names=sorted(set(re.findall(r"\b[a-z0-9_]+\.(?:dll|so)\b|\b[a-z_][a-z0-9_]{2,}\b",s)));out({"normalized":names[:500],"md5":hashlib.md5(",".join(names).encode()).hexdigest()})
def fuzzy(a):
    b=rb(a);chunks=[hashlib.sha1(b[i:i+64]).hexdigest()[:8] for i in range(0,len(b),64)];out({"block":64,"digest":":".join(chunks)})
def antivm(a):
    s=(rt(a) if a else platform.platform()+" "+platform.machine()).lower();terms=[x for x in ["qemu","kvm","virtualbox","vmware","hyper-v","xen"] if x in s];out({"artifacts":terms})
def sandbox(a):
    up=0
    try:up=float(Path("/proc/uptime").read_text().split()[0])
    except:pass
    out({"uptime_seconds":up,"low_uptime":0<up<300,"cpu_count":os.cpu_count(),"note":"heuristic only"})
def threatip(a):
    vals=[]
    for t in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b",rt(a)):
        try:vals.append(str(ipaddress.ip_address(t)))
        except:pass
    out(sorted(set(vals)))
def stix(a):
    x=json.loads(rt(a));objs=x.get("objects",[]) if isinstance(x,dict) else [];out({"type":x.get("type") if isinstance(x,dict) else None,"object_types":{t:sum(1 for o in objs if o.get("type")==t) for t in sorted({o.get("type") for o in objs if isinstance(o,dict)})}})
def snort(a):
    s=rt(a);errs=[]
    for i,l in enumerate(s.splitlines(),1):
        if not l.strip() or l.lstrip().startswith("#"):continue
        if not re.match(r"^(alert|log|pass|drop|reject|sdrop)\s+\w+\s+\S+\s+\S+\s+->\s+\S+\s+\S+\s*\(.*\)\s*$",l.strip()):errs.append(i)
    out({"valid":not errs,"error_lines":errs})
def sigma(a):
    s=rt(a);req=["title:","detection:"]
    out({"valid":all(x in s for x in req),"has_logsource":"logsource:" in s,"has_condition":"condition:" in s})
def evtx(a):
    b=rb(a);out({"file_header":b[:8]==b"ElfFile\0","chunk_headers":b.count(b"ElfChnk\0"),"bytes":len(b)})
def authfail(a):
    s=rt(a);rows=[]
    for l in s.splitlines():
        if re.search(r"(?i)(failed password|authentication failure|invalid user)",l):
            ip=re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b",l);rows.append({"ip":ip.group(0) if ip else None,"line":l})
    out({"failures":rows,"count":len(rows)})
def pam(a):
    s=rt(a);out({"successes":len(re.findall(r"(?i)session opened|authentication success",s)),"failures":len(re.findall(r"(?i)authentication failure|failed password",s))})
def sudoers(a):
    s=rt(a);out({"nopasswd_lines":[l for l in s.splitlines() if "NOPASSWD" in l and not l.lstrip().startswith("#")],"aliases":re.findall(r"(?m)^(User_Alias|Cmnd_Alias|Host_Alias|Runas_Alias)\s+(\w+)",s)})
def suid(a):
    root=Path(a[0]) if a else Path(".");rows=[]
    for p in root.rglob("*"):
        try:
            m=p.stat().st_mode
            if p.is_file() and m&0o6000:rows.append({"path":str(p),"setuid":bool(m&0o4000),"setgid":bool(m&0o2000)})
        except:pass
    out(rows[:1000])
def shadow(a):
    rows=[]
    for l in rt(a).splitlines():
        if ":" not in l:continue
        u,h,*_=l.split(":");alg="locked" if h.startswith(("!","*")) else ("yescrypt" if h.startswith("$y$") else "sha512" if h.startswith("$6$") else "sha256" if h.startswith("$5$") else "md5" if h.startswith("$1$") else "des/legacy" if h else "empty")
        rows.append({"user":u,"algorithm":alg,"weak":alg in {"md5","des/legacy","empty"}})
    out(rows)
def authkeys(a):
    rows=[]
    for l in rt(a).splitlines():
        if not l.strip() or l.startswith("#"):continue
        parts=l.split();kind=next((x for x in parts if x.startswith(("ssh-","ecdsa-","sk-"))),None);opts=l.split(kind)[0].strip(" ,") if kind else ""
        rows.append({"type":kind,"options":opts,"forced_command":"command=" in opts,"no_pty":"no-pty" in opts})
    out(rows)
def knownhosts(a):
    rows=[]
    for l in rt(a).splitlines():
        if not l.strip() or l.startswith("#"):continue
        p=l.split();rows.append({"host":p[0],"hashed":p[0].startswith("|1|"),"key_type":p[1] if len(p)>1 else None})
    out(rows)
def gpg(a):
    s=rt(a);weak=[l for l in s.splitlines() if re.search(r"(?i)\bDSA\b|RSA\s*1024|1024\s*bit",l)];out({"weak_indicators":weak})
def poodle(a):
    s=" ".join(a).lower();out({"sslv3_enabled":"ssl3" in s or "sslv3" in s,"cbc_present":"cbc" in s,"risk":"ssl3" in s and "cbc" in s})
def heartbleed(a):
    s=" ".join(a).lower();out({"heartbeat_extension_advertised":"heartbeat" in s,"assessment":"offline-only; no exploit packets are sent"})
def shellshock(a):
    s=rt(a);out({"function_export_pattern":bool(re.search(r"\(\)\s*\{",s)),"suspicious_trailing_command":bool(re.search(r"\(\)\s*\{[^}]*\}\s*;",s))})
def dirtycow(a):
    v=(a[0] if a else platform.release());m=re.match(r"(\d+)\.(\d+)\.(\d+)",v);old=False
    if m:
        t=tuple(map(int,m.groups()));old=t<(4,8,3)
    out({"kernel":v,"historical_version_heuristic":old,"note":"version heuristic only; vendor backports can invalidate this result"})
def ebpf(a):
    b=rb(a);out({"bytes":len(b),"instruction_count":len(b)//8,"aligned":len(b)%8==0,"max_instructions_ok":len(b)//8<=1000000})
def kptr(a):
    vals={}
    for p in ["/proc/sys/kernel/kptr_restrict","/proc/sys/kernel/dmesg_restrict"]:
        try:vals[p]=Path(p).read_text().strip()
        except Exception:vals[p]=None
    out(vals)
def taint(a):
    n=int(a[0],0) if a else int(Path("/proc/sys/kernel/tainted").read_text().strip());names={0:"proprietary module",1:"forced module load",2:"SMP CPU issue",3:"forced unload",5:"machine check",6:"bad page",9:"out-of-tree module",12:"externally built module",13:"unsigned module"}
    out({"value":n,"flags":[v for bit,v in names.items() if n&(1<<bit)]})
COMMANDS={"pcap-dns-query-extract":dns_extract,"pcap-http-uri-extract":http_extract,"pcap-tls-client-hello":tls_hello,"pcap-credential-finder":credential,"pcap-icmp-tunnel-chk":icmp,"raw-memory-string-dump":strings,"volatility-profile-chk":profile,"page-table-walk-tool":pagetable,"kernel-module-sig-chk":modsig,"rootkit-symbol-search":rootsym,"hidden-process-finder":hidden,"proc-maps-anomaly-chk":maps,"mem-injection-scanner":injection,"code-cave-finder-elf":codecave,"elf-got-overwrite-chk":elfsec,"elf-plt-hook-detector":elfsec,"ptrace-anti-debug-chk":ptrace,"process-environment-diff":envdiff,"ld-preload-auditor":preload,"ld-so-preload-clean":preload,"binary-entropy-graph":entropy,"packed-executable-chk":packed,"upx-header-unpacker":upx,"pe-rich-header-hasher":rich,"imphash-calculator":imphash,"fuzzy-ssdeep-hasher":fuzzy,"fuzzy-tlsh-calculator":fuzzy,"anti-vm-artifact-chk":antivm,"sandbox-detection-chk":sandbox,"threat-intel-ip-parser":threatip,"ioc-stix-json-parser":stix,"snort-rule-validator":snort,"suricata-rule-tester":snort,"sigma-rule-converter":sigma,"windows-event-evtx-chk":evtx,"syslog-auth-failure":authfail,"pam-auth-audit-trail":pam,"sudoers-file-validator":sudoers,"suid-binary-matrix":suid,"shadow-password-audit":shadow,"ssh-authorized-keys-chk":authkeys,"ssh-known-hosts-hash":knownhosts,"gpg-keyring-auditor":gpg,"ssl-tls-poodle-tester":poodle,"heartbleed-probe-cli":heartbleed,"shellshock-cve-tester":shellshock,"dirty-cow-probe-chk":dirtycow,"ebpf-program-verifier":ebpf,"kernel-kptr-restrict-chk":kptr,"dmesg-taint-explainer":taint}
def main():
    if len(COMMANDS)!=50:die(f"command count {len(COMMANDS)}")
    p=Path(sys.argv[0]).name
    if p in COMMANDS:cmd,args=p,sys.argv[1:]
    else:
        if len(sys.argv)<2 or sys.argv[1] in ("-h","--help"):print("OceanStudio defensive forensic shard 20");print("\n".join(sorted(COMMANDS)));return
        if sys.argv[1] in ("-v","--version"):print(VERSION);return
        cmd,args=sys.argv[1],sys.argv[2:]
    if cmd not in COMMANDS:die("unknown command: "+cmd)
    COMMANDS[cmd](args)
if __name__=="__main__":main()
