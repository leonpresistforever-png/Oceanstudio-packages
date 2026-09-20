#!/usr/bin/env python3
from __future__ import annotations

import csv
import gc
import hashlib
import html
import io
import json
import math
import os
import platform
import re
import select
import shutil
import socket
import statistics
import struct
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

VERSION = "2.0.0"

def die(msg, code=2):
    print(msg, file=sys.stderr)
    raise SystemExit(code)

def out(obj):
    if isinstance(obj, (dict, list, tuple)):
        print(json.dumps(obj, indent=2, default=str))
    else:
        print(obj)

def read_text(path=None):
    if path and path != "-":
        return Path(path).read_text(encoding="utf-8", errors="replace")
    return sys.stdin.read()

def nums(path=None):
    text = read_text(path)
    vals = []
    for x in re.split(r"[\s,]+", text.strip()):
        if x:
            vals.append(float(x))
    return vals

def pct(sorted_vals, q):
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals)-1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return sorted_vals[lo]
    f = pos-lo
    return sorted_vals[lo]*(1-f)+sorted_vals[hi]*f

def summary(v):
    if not v:
        return {"count": 0}
    s = sorted(v)
    return {
        "count": len(s), "min": min(s), "max": max(s),
        "mean": statistics.fmean(s),
        "p50": pct(s, .50), "p90": pct(s, .90),
        "p95": pct(s, .95), "p99": pct(s, .99),
        "p999": pct(s, .999),
    }

def pid_arg(args, pos=0):
    return int(args[pos]) if len(args) > pos else os.getpid()

def proc_status(pid):
    d = {}
    for line in Path(f"/proc/{pid}/status").read_text(errors="replace").splitlines():
        if ":" in line:
            k,v=line.split(":",1)
            d[k]=v.strip()
    return d

def perf_event_sample_view(args):
    data = Path(args[0]).read_bytes() if args else sys.stdin.buffer.read()
    off=0; rows=[]
    while off+8 <= len(data):
        typ,misc,size=struct.unpack_from("<IHH",data,off)
        if size < 8 or off+size > len(data):
            rows.append({"offset":off,"error":"invalid record size","type":typ,"misc":misc,"size":size})
            break
        rows.append({"offset":off,"type":typ,"misc":misc,"size":size,"payload_hex":data[off+8:off+min(size,40)].hex()})
        off += size
    out({"records":rows,"bytes_parsed":off,"total_bytes":len(data)})

def hardware_counter_query(args):
    root=Path("/sys/bus/event_source/devices")
    devices={}
    if root.exists():
        for d in sorted(root.iterdir()):
            info={}
            try:
                info["type"]=int((d/"type").read_text().strip())
            except Exception: pass
            ev={}
            if (d/"events").is_dir():
                for f in list(sorted((d/"events").iterdir()))[:128]:
                    try: ev[f.name]=f.read_text().strip()
                    except Exception: pass
            info["events"]=ev
            devices[d.name]=info
    if args:
        name=args[0]
        out({name:devices.get(name,{"available":False})})
    else:
        out({"architecture":platform.machine(),"devices":devices})

def flame_color(name):
    h=int(hashlib.sha1(name.encode()).hexdigest()[:6],16)
    return f"#{200+(h&31):02x}{80+((h>>5)&95):02x}{40+((h>>12)&63):02x}"

def collapsed_lines(text):
    rows=[]
    for line in text.splitlines():
        line=line.strip()
        if not line: continue
        m=re.match(r"^(.*?)(?:\s+(\d+(?:\.\d+)?))?$",line)
        stack=m.group(1); count=float(m.group(2) or 1)
        rows.append((stack.split(";"),count))
    return rows

def flamegraph_svg_builder(args):
    rows=collapsed_lines(read_text(args[0] if args else None))
    total=sum(c for _,c in rows) or 1
    width=1200; fh=18; margin=20
    maxdepth=max((len(s) for s,_ in rows),default=1)
    height=margin*2+maxdepth*fh
    ybase=height-margin
    x=0.0; rects=[]
    for stack,count in rows:
        w=width*count/total
        for depth,name in enumerate(stack):
            y=ybase-(depth+1)*fh
            rects.append(f'<g><title>{html.escape(name)} ({count:g})</title><rect x="{x:.2f}" y="{y}" width="{max(w,.5):.2f}" height="{fh-1}" fill="{flame_color(name)}"/><text x="{x+3:.2f}" y="{y+13}" font-size="11">{html.escape(name[:80])}</text></g>')
        x+=w
    print(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/>')
    print("\n".join(rects)); print("</svg>")

def stackcollapse_perf_cli(args):
    text=read_text(args[0] if args else None)
    samples=[]; frames=[]
    for line in text.splitlines()+[""]:
        if not line.strip():
            if frames:
                samples.append(";".join(reversed(frames))+" 1"); frames=[]
            continue
        if re.match(r"^\s",line):
            s=line.strip()
            m=re.search(r"(?:[0-9a-f]+\s+)?([A-Za-z_.$<>~][^+\s]*(?:(?:\([^)]*\))?))",s)
            if m: frames.append(m.group(1))
    print("\n".join(samples))

def stackcollapse_gdb_tool(args):
    text=read_text(args[0] if args else None)
    stacks=[]; frames=[]
    for line in text.splitlines()+[""]:
        if line.startswith("Thread ") or not line.strip():
            if frames:
                stacks.append(";".join(reversed(frames))+" 1"); frames=[]
            continue
        m=re.match(r"^#\d+\s+(?:0x[0-9a-f]+\s+in\s+)?([^\s(]+)",line.strip(),re.I)
        if m: frames.append(m.group(1))
    print("\n".join(stacks))

def ratio_calc(args, kind):
    if len(args)<2: die(f"usage: {kind} NUMERATOR DENOMINATOR")
    a,b=float(args[0]),float(args[1])
    if b==0: die("denominator must be non-zero")
    if kind=="pmu-cycle-ratio-calc": out({"cycles":a,"instructions":b,"cycles_per_instruction":a/b})
    elif kind=="branch-mispredict-calc": out({"branch_misses":a,"branches":b,"mispredict_percent":100*a/b})
    elif kind=="cache-miss-rate-analyzer": out({"cache_misses":a,"cache_accesses":b,"miss_percent":100*a/b})
    elif kind=="instruction-per-cycle": out({"instructions":a,"cycles":b,"ipc":a/b})
    elif kind=="memory-bandwidth-calc": out({"bytes":a,"seconds":b,"bytes_per_second":a/b,"gib_per_second":a/b/(1024**3)})
    elif kind=="throughput-rps-calc": out({"operations":a,"seconds":b,"operations_per_second":a/b})
    elif kind=="disk-iops-calculator": out({"io_operations":a,"seconds":b,"iops":a/b})
    elif kind=="tlb-miss-ratio-analyzer": out({"tlb_misses":a,"translations":b,"miss_percent":100*a/b})

def latency_histogram_ascii(args):
    v=nums(args[1] if len(args)>1 else None) if args and args[0].isdigit() else nums(args[0] if args else None)
    bins=int(args[0]) if args and args[0].isdigit() else 20
    if not v: return
    lo,hi=min(v),max(v)
    if lo==hi:
        print(f"{lo:g} | {'#'*len(v)} {len(v)}"); return
    counts=[0]*bins
    for x in v:
        i=min(bins-1,int((x-lo)/(hi-lo)*bins)); counts[i]+=1
    mx=max(counts) or 1
    for i,c in enumerate(counts):
        a=lo+(hi-lo)*i/bins; b=lo+(hi-lo)*(i+1)/bins
        bar="#"*max(1,round(c/mx*50)) if c else ""
        print(f"{a:12.3f}-{b:12.3f} | {bar} {c}")

def percentile_p90_p99_p999(args):
    out(summary(nums(args[0] if args else None)))

def jitter_interarrival_chk(args):
    v=nums(args[0] if args else None)
    if len(v)<2: die("need at least two timestamps")
    diffs=[b-a for a,b in zip(v,v[1:])]
    out({"intervals":summary(diffs),"jitter_stddev":statistics.pstdev(diffs),"mean_absolute_jitter":statistics.fmean(abs(x-statistics.fmean(diffs)) for x in diffs)})

def hdr_histogram_log_view(args):
    text=read_text(args[0] if args else None)
    values=[]; metadata=[]
    for line in text.splitlines():
        s=line.strip()
        if not s: continue
        if s.startswith("#"):
            metadata.append(s); continue
        parts=[x.strip() for x in s.split(",")]
        # Accept common exported percentile/value text or simple value,count files.
        nums_here=[]
        for x in parts:
            try: nums_here.append(float(x))
            except ValueError: pass
        if len(parts)>=2 and len(nums_here)>=2:
            val=nums_here[-1]
            count=max(1,int(nums_here[-2])) if nums_here[-2].is_integer() and nums_here[-2] < 1_000_000 else 1
            values.extend([val]*min(count,100000))
    out({"metadata":metadata[:20],"summary":summary(values),"note":"plain/exported HDR log values decoded; compressed V2 payloads are reported as metadata only"})

def malloc_count_hook_cli(args):
    text=read_text(args[0] if args else None)
    sizes=[]
    for line in text.splitlines():
        m=re.search(r"\b(?:malloc|calloc|realloc)\b.*?\b(?:size=)?(\d+)\b",line,re.I)
        if m: sizes.append(int(m.group(1)))
    buckets=Counter()
    for s in sizes:
        b=1 if s<=1 else 1<<(s-1).bit_length()
        buckets[b]+=1
    out({"allocations":len(sizes),"bytes":sum(sizes),"size_buckets":dict(sorted(buckets.items()))})

def mmap_allocation_tracer(args):
    pid=pid_arg(args)
    rows=[]; total=0
    for line in Path(f"/proc/{pid}/maps").read_text(errors="replace").splitlines():
        parts=line.split(maxsplit=5); start,end=[int(x,16) for x in parts[0].split("-")]
        path=parts[5] if len(parts)>5 else ""
        if not path or path.startswith("["):
            size=end-start; total+=size
            rows.append({"range":parts[0],"size":size,"perms":parts[1],"name":path or "[anonymous]"})
    out({"pid":pid,"anonymous_or_special_bytes":total,"mappings":rows})

def brk_heap_expansion_chk(args):
    pid=pid_arg(args); count=int(args[1]) if len(args)>1 else 1; interval=float(args[2]) if len(args)>2 else 0
    samples=[]
    for i in range(count):
        size=0
        for line in Path(f"/proc/{pid}/maps").read_text(errors="replace").splitlines():
            if line.rstrip().endswith("[heap]"):
                a,b=[int(x,16) for x in line.split()[0].split("-")]; size=b-a
        samples.append({"time_ns":time.time_ns(),"heap_bytes":size})
        if i+1<count: time.sleep(interval)
    out({"pid":pid,"samples":samples,"growth_bytes":samples[-1]["heap_bytes"]-samples[0]["heap_bytes"]})

def page_fault_counter_cli(args):
    pid=pid_arg(args)
    def snap():
        f=Path(f"/proc/{pid}/stat").read_text().split()
        return int(f[9]),int(f[11])
    interval=float(args[1]) if len(args)>1 else 0
    a=snap()
    if interval>0: time.sleep(interval)
    b=snap()
    out({"pid":pid,"minor_faults":b[0],"major_faults":b[1],"delta_minor":b[0]-a[0],"delta_major":b[1]-a[1],"interval_seconds":interval})

def context_switch_cost_est(args):
    rounds=int(args[0]) if args else 1000
    a=threading.Event(); b=threading.Event(); done=threading.Event()
    def worker():
        for _ in range(rounds):
            a.wait(); a.clear(); b.set()
        done.set()
    t=threading.Thread(target=worker); t.start()
    start=time.perf_counter_ns()
    for _ in range(rounds):
        a.set(); b.wait(); b.clear()
    done.wait(); elapsed=time.perf_counter_ns()-start; t.join()
    out({"round_trips":rounds,"elapsed_ns":elapsed,"estimated_switch_ns":elapsed/(rounds*2)})

def thread_pool_saturation(args):
    if len(args)<3: die("usage: thread-pool-saturation WORKERS BUSY QUEUED")
    workers,busy,queued=map(float,args[:3])
    if workers<=0: die("workers must be >0")
    out({"workers":workers,"busy":busy,"queued":queued,"utilization":min(1,busy/workers),"queue_per_worker":queued/workers,"saturated":busy>=workers and queued>0})

def epoll_latency_bench(args):
    if not hasattr(select,"epoll"):
        out({"supported":False}); return
    n=int(args[0]) if args else 100
    r,w=os.pipe(); ep=select.epoll(); ep.register(r,select.EPOLLIN); vals=[]
    try:
        for _ in range(n):
            t=time.perf_counter_ns(); os.write(w,b"x"); ev=ep.poll(1,1); os.read(r,1); vals.append(time.perf_counter_ns()-t)
    finally:
        ep.close(); os.close(r); os.close(w)
    out({"supported":True,"nanoseconds":summary(vals)})

def select_poll_scale_bench(args):
    n=int(args[0]) if args else 32
    n=max(1,min(n,256))
    pairs=[os.pipe() for _ in range(n)]
    target=pairs[-1]
    os.write(target[1],b"x")
    try:
        t=time.perf_counter_ns(); rr,_,_=select.select([p[0] for p in pairs],[],[],1); sel=time.perf_counter_ns()-t
        poller=select.poll()
        for r,_ in pairs: poller.register(r,select.POLLIN)
        t=time.perf_counter_ns(); pe=poller.poll(1000); pol=time.perf_counter_ns()-t
        out({"descriptors":n,"select_ns":sel,"poll_ns":pol,"select_ready":len(rr),"poll_ready":len(pe)})
    finally:
        for r,w in pairs: os.close(r); os.close(w)

def io_uring_probe_support(args):
    p=Path("/proc/sys/kernel/io_uring_disabled")
    disabled=int(p.read_text().strip()) if p.exists() else None
    out({"kernel":platform.release(),"architecture":platform.machine(),"sysctl_io_uring_disabled":disabled,"supported_by_policy":disabled in (0,None)})

def io_uring_sq_poll_view(args):
    rows=[]
    proc=Path("/proc")
    for d in proc.iterdir() if proc.exists() else []:
        if not d.name.isdigit(): continue
        try:
            for task in (d/"task").iterdir():
                comm=(task/"comm").read_text().strip()
                if re.search(r"(iou-sqp|io_uring|sqpoll)",comm,re.I):
                    rows.append({"pid":int(d.name),"tid":int(task.name),"comm":comm})
        except Exception: pass
    out({"threads":rows,"count":len(rows)})

def futex_contention_timer(args):
    threads=int(args[0]) if args else 4; iterations=int(args[1]) if len(args)>1 else 10000
    lock=threading.Lock(); counter=0; waits=[]; guard=threading.Lock()
    def work():
        nonlocal counter
        local=[]
        for _ in range(iterations):
            t=time.perf_counter_ns()
            with lock:
                local.append(time.perf_counter_ns()-t); counter+=1
        with guard: waits.extend(local)
    ts=[threading.Thread(target=work) for _ in range(threads)]
    start=time.perf_counter_ns()
    for t in ts:t.start()
    for t in ts:t.join()
    out({"threads":threads,"iterations_each":iterations,"operations":counter,"elapsed_ns":time.perf_counter_ns()-start,"lock_wait_ns":summary(waits),"backend_note":"CPython lock contention on Linux generally blocks through OS primitives including futexes"})

def spinlock_cycles_wasted(args):
    if len(args)>=2:
        spins=float(args[0]); cycles=float(args[1]); out({"spins":spins,"cycles_per_spin":cycles,"wasted_cycles":spins*cycles}); return
    n=int(args[0]) if args else 1000000
    t=time.perf_counter_ns(); x=0
    for i in range(n): x ^= i
    ns=time.perf_counter_ns()-t
    out({"iterations":n,"elapsed_ns":ns,"ns_per_spin":ns/n,"checksum":x})

def cpu_cache_line_bouncing(args):
    text=read_text(args[0] if args else None)
    line_size=int(args[1]) if len(args)>1 else 64
    owners=defaultdict(set); writes=0
    for line in text.splitlines():
        p=re.split(r"[\s,]+",line.strip())
        if len(p)<2: continue
        tid=p[0]; addr=int(p[1],0); owners[addr//line_size].add(tid); writes+=1
    shared={hex(k*line_size):sorted(v) for k,v in owners.items() if len(v)>1}
    out({"writes":writes,"cache_line_bytes":line_size,"shared_lines":shared,"suspected_false_sharing_lines":len(shared)})

def numa_memory_distance(args):
    base=Path("/sys/devices/system/node")
    rows={}
    for d in sorted(base.glob("node[0-9]*")):
        f=d/"distance"
        if f.exists(): rows[d.name]=[int(x) for x in f.read_text().split()]
    out({"nodes":rows,"count":len(rows)})

def sched_wakeup_latency(args):
    v=nums(args[0] if args else None)
    if len(v)>=2 and len(v)%2==0:
        l=[v[i+1]-v[i] for i in range(0,len(v),2)]
        out({"nanoseconds":summary(l)}); return
    rounds=int(args[0]) if args and args[0].isdigit() else 100
    ev=threading.Event(); ack=threading.Event(); vals=[]
    def w():
        for _ in range(rounds):
            ev.wait(); ev.clear(); vals.append(time.perf_counter_ns()); ack.set()
    t=threading.Thread(target=w); t.start(); sent=[]
    for _ in range(rounds):
        sent.append(time.perf_counter_ns()); ev.set(); ack.wait(); ack.clear()
    t.join()
    out({"nanoseconds":summary([b-a for a,b in zip(sent,vals)])})

def irq_cpu_affinity_view(args):
    rows=[]
    for d in sorted(Path("/proc/irq").glob("[0-9]*"),key=lambda p:int(p.name)):
        f=d/"smp_affinity_list"
        try: aff=f.read_text().strip()
        except Exception: continue
        rows.append({"irq":int(d.name),"affinity":aff})
    out(rows)

def disk_queue_depth_bench(args):
    if not args: die("usage: disk-queue-depth-bench FILE [QUEUE_DEPTH] [OPS] [BLOCK_SIZE]")
    path=Path(args[0]); depth=int(args[1]) if len(args)>1 else 4; ops=int(args[2]) if len(args)>2 else 128; bs=int(args[3]) if len(args)>3 else 4096
    size=path.stat().st_size
    if size<bs: die("file smaller than block size")
    offsets=[(i*bs)%(size-bs+1) for i in range(ops)]
    def readat(off):
        with path.open("rb",buffering=0) as f:
            f.seek(off); return len(f.read(bs))
    t=time.perf_counter()
    with ThreadPoolExecutor(max_workers=depth) as ex: total=sum(ex.map(readat,offsets))
    sec=time.perf_counter()-t
    out({"queue_depth":depth,"operations":ops,"bytes":total,"seconds":sec,"iops":ops/sec,"mib_per_s":total/sec/(1024**2)})

def tcp_rtt_smoothing_calc(args):
    vals=nums(args[0] if args else None)
    if not vals: die("provide RTT samples")
    alpha=1/8; beta=1/4; srtt=vals[0]; rttvar=vals[0]/2
    history=[]
    for r in vals[1:]:
        rttvar=(1-beta)*rttvar+beta*abs(srtt-r)
        srtt=(1-alpha)*srtt+alpha*r
        history.append({"sample":r,"srtt":srtt,"rttvar":rttvar,"rto":srtt+4*rttvar})
    out({"srtt":srtt,"rttvar":rttvar,"rto":srtt+4*rttvar,"history":history})

def tcp_cwnd_growth_analyzer(args):
    cwnd=float(args[0]) if args else 10; ssthresh=float(args[1]) if len(args)>1 else 100; acks=int(args[2]) if len(args)>2 else 20
    hist=[]
    for i in range(acks):
        phase="slow_start" if cwnd<ssthresh else "congestion_avoidance"
        cwnd += 1 if phase=="slow_start" else 1/max(cwnd,1)
        hist.append({"ack":i+1,"cwnd":cwnd,"phase":phase})
    out({"initial_cwnd":float(args[0]) if args else 10,"ssthresh":ssthresh,"history":hist,"final_cwnd":cwnd})

def buffer_copy_throughput(args):
    sizes=[int(x) for x in args] if args else [1024,16384,262144,1048576]
    rows=[]
    for size in sizes:
        src=bytearray(os.urandom(min(size,1024))*((size+1023)//1024))[:size]
        loops=max(10,min(10000,64*1024*1024//max(size,1)))
        t=time.perf_counter(); chk=0
        for _ in range(loops):
            dst=src[:]; chk ^= dst[0] if dst else 0
        sec=time.perf_counter()-t
        rows.append({"bytes":size,"loops":loops,"seconds":sec,"gib_per_s":size*loops/sec/(1024**3),"checksum":chk})
    out(rows)

def zero_copy_splice_bench(args):
    if not hasattr(os,"splice"):
        out({"supported":False}); return
    total=int(args[0]) if args else 1024*1024; chunk=min(65536,total)
    r,w=os.pipe(); sink=os.open("/dev/null",os.O_WRONLY); moved=0; payload=b"x"*chunk
    t=time.perf_counter()
    try:
        while moved<total:
            n=min(chunk,total-moved)
            os.write(w,payload[:n])
            done=0
            while done<n:
                done += os.splice(r,sink,n-done)
            moved += n
    finally:
        os.close(r); os.close(w); os.close(sink)
    sec=time.perf_counter()-t
    out({"supported":True,"bytes":moved,"seconds":sec,"gib_per_s":moved/sec/(1024**3)})

def linear_slope(points):
    n=len(points)
    if n<2: die("need at least two samples")
    xs=[p[0] for p in points]; ys=[p[1] for p in points]
    xm=statistics.fmean(xs); ym=statistics.fmean(ys)
    den=sum((x-xm)**2 for x in xs)
    return sum((x-xm)*(y-ym) for x,y in points)/den if den else 0.0

def parse_pairs(path=None):
    pts=[]
    for line in read_text(path).splitlines():
        p=re.split(r"[\s,]+",line.strip())
        if len(p)>=2: pts.append((float(p[0]),float(p[1])))
    return pts

def memory_leak_growth_rate(args):
    pts=parse_pairs(args[0] if args else None); slope=linear_slope(pts)
    out({"samples":len(pts),"bytes_per_time_unit":slope,"growth_detected":slope>0})

def resident_set_growth_chk(args):
    if args and Path(args[0]).exists():
        pts=parse_pairs(args[0])
    else:
        vals=nums(args[0] if args else None); pts=list(enumerate(vals))
    slope=linear_slope(pts)
    out({"samples":len(pts),"rss_growth_per_unit":slope,"growing":slope>0})

def virtual_memory_size_view(args):
    pid=pid_arg(args); st=proc_status(pid)
    def kb(name):
        m=re.search(r"(\d+)",st.get(name,"0")); return int(m.group(1))*1024 if m else 0
    vm,rss=kb("VmSize"),kb("VmRSS")
    out({"pid":pid,"virtual_bytes":vm,"resident_bytes":rss,"rss_to_vmsize_ratio":rss/vm if vm else None})

def garbage_collector_pause(args):
    rounds=int(args[0]) if args else 20; vals=[]
    for _ in range(rounds):
        t=time.perf_counter_ns(); collected=gc.collect(); vals.append(time.perf_counter_ns()-t)
    out({"rounds":rounds,"pause_ns":summary(vals),"last_collected":collected})

def allocator_fragmentation(args):
    if len(args)<2: die("usage: allocator-fragmentation REQUESTED_BYTES RESERVED_BYTES [LIVE_BYTES]")
    requested,reserved=map(float,args[:2]); live=float(args[2]) if len(args)>2 else requested
    if reserved<=0: die("reserved bytes must be >0")
    out({"requested_bytes":requested,"live_bytes":live,"reserved_bytes":reserved,"internal_fragmentation_bytes":max(0,reserved-requested),"external_or_free_bytes":max(0,reserved-live),"utilization":live/reserved})

def simd_vector_width_probe(args):
    text=Path("/proc/cpuinfo").read_text(errors="replace") if Path("/proc/cpuinfo").exists() else ""
    flags=set(re.findall(r"\b(?:asimd|neon|sve|sve2)\b",text.lower()))
    sve=Path("/proc/sys/abi/sve_default_vector_length")
    vl=int(sve.read_text().strip()) if sve.exists() else None
    width=vl*8 if vl else (128 if ("asimd" in flags or "neon" in flags) else None)
    out({"architecture":platform.machine(),"features":sorted(flags),"vector_bits":width,"sve_default_bytes":vl})

def neon_fp_pipeline_bench(args):
    arch=platform.machine().lower()
    if arch not in ("aarch64","arm64"):
        out({"supported":False,"reason":f"requires AArch64 NEON, current architecture is {arch}"}); return
    cc=shutil.which("clang") or shutil.which("cc")
    if not cc:
        out({"supported":False,"reason":"C compiler not installed"}); return
    loops=int(args[0]) if args else 10_000_000
    src=r'''
#include <arm_neon.h>
#include <stdio.h>
#include <time.h>
#include <stdlib.h>
static double now(void){struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return t.tv_sec+t.tv_nsec/1e9;}
int main(int argc,char**argv){long n=atol(argv[1]); float32x4_t a=vdupq_n_f32(1.0001f),b=vdupq_n_f32(1.0002f),c=vdupq_n_f32(0.9999f); double t=now(); for(long i=0;i<n;i++) a=vfmaq_f32(c,a,b); double s=now()-t; float x=vaddvq_f32(a); printf("%.9f %.3f\n",s,(double)n*8.0/s/1e9); return x==0;}
'''
    with tempfile.TemporaryDirectory() as td:
        c=Path(td)/"b.c"; exe=Path(td)/"b"; c.write_text(src)
        r=subprocess.run([cc,"-O3",str(c),"-o",str(exe)],capture_output=True,text=True)
        if r.returncode: out({"supported":False,"reason":"compiler failed","stderr":r.stderr[-1000:]}); return
        r=subprocess.run([str(exe),str(loops)],capture_output=True,text=True,check=True)
        sec,gflops=r.stdout.split()[:2]
        out({"supported":True,"loops":loops,"seconds":float(sec),"estimated_gflops":float(gflops)})

def cpu_throttle_detector(args):
    rows=[]
    for cpu in sorted(Path("/sys/devices/system/cpu").glob("cpu[0-9]*")):
        cp=cpu/"cpufreq"
        if not cp.exists(): continue
        def r(name):
            try:return int((cp/name).read_text().strip())
            except Exception:return None
        cur,maxf,minf=r("scaling_cur_freq"),r("cpuinfo_max_freq"),r("cpuinfo_min_freq")
        rows.append({"cpu":cpu.name,"current_khz":cur,"max_khz":maxf,"min_khz":minf,"current_to_max":cur/maxf if cur and maxf else None})
    therm=[]
    for z in Path("/sys/class/thermal").glob("thermal_zone*"):
        try: therm.append({"zone":z.name,"temp_mC":int((z/"temp").read_text().strip())})
        except Exception: pass
    out({"cpus":rows,"thermal":therm})

def thermal_governor_latency(args):
    interval=float(args[0]) if args else .1; samples=int(args[1]) if len(args)>1 else 10
    devs=sorted(Path("/sys/class/thermal").glob("cooling_device*")); last={}; changes=[]
    for _ in range(samples):
        now=time.time_ns()
        for d in devs:
            try: cur=(d/"cur_state").read_text().strip()
            except Exception: continue
            if d.name in last and last[d.name][0]!=cur: changes.append({"device":d.name,"from":last[d.name][0],"to":cur,"delta_ns":now-last[d.name][1]})
            last[d.name]=(cur,now)
        time.sleep(interval)
    out({"devices":len(devs),"samples":samples,"changes":changes})

def power_consumption_model(args):
    if len(args)<6: die("usage: power-consumption-model LITTLE_CORES LITTLE_FREQ_GHZ LITTLE_UTIL BIG_CORES BIG_FREQ_GHZ BIG_UTIL [LITTLE_COEFF BIG_COEFF]")
    lc,lf,lu,bc,bf,bu=map(float,args[:6]); lcoef=float(args[6]) if len(args)>6 else .35; bcoef=float(args[7]) if len(args)>7 else 1.0
    lp=lc*lcoef*(lf**3)*lu; bp=bc*bcoef*(bf**3)*bu
    out({"little_watts_model":lp,"big_watts_model":bp,"total_watts_model":lp+bp,"model":"P ~= coefficient * cores * GHz^3 * utilization"})

def perf_script_filter_cli(args):
    if not args: die("usage: perf-script-filter-cli REGEX [FILE]")
    rx=re.compile(args[0]); text=read_text(args[1] if len(args)>1 else None)
    for line in text.splitlines():
        if rx.search(line): print(line)

def call_graph_dot_generator(args):
    rows=collapsed_lines(read_text(args[0] if args else None)); edges=Counter(); nodes=Counter()
    for stack,count in rows:
        for n in stack:nodes[n]+=count
        for a,b in zip(stack,stack[1:]): edges[(a,b)]+=count
    print("digraph callgraph {")
    print('  graph [rankdir="LR"];')
    for n,c in nodes.items(): print(f'  "{n.replace(chr(34),chr(92)+chr(34))}" [label="{n.replace(chr(34),chr(92)+chr(34))}\\n{c:g}"];')
    for (a,b),c in edges.items(): print(f'  "{a.replace(chr(34),chr(92)+chr(34))}" -> "{b.replace(chr(34),chr(92)+chr(34))}" [label="{c:g}"];')
    print("}")

COMMANDS={
"perf-event-sample-view":perf_event_sample_view,
"hardware-counter-query":hardware_counter_query,
"flamegraph-svg-builder":flamegraph_svg_builder,
"stackcollapse-perf-cli":stackcollapse_perf_cli,
"stackcollapse-gdb-tool":stackcollapse_gdb_tool,
"pmu-cycle-ratio-calc":lambda a:ratio_calc(a,"pmu-cycle-ratio-calc"),
"branch-mispredict-calc":lambda a:ratio_calc(a,"branch-mispredict-calc"),
"cache-miss-rate-analyzer":lambda a:ratio_calc(a,"cache-miss-rate-analyzer"),
"instruction-per-cycle":lambda a:ratio_calc(a,"instruction-per-cycle"),
"memory-bandwidth-calc":lambda a:ratio_calc(a,"memory-bandwidth-calc"),
"latency-histogram-ascii":latency_histogram_ascii,
"percentile-p90-p99-p999":percentile_p90_p99_p999,
"throughput-rps-calc":lambda a:ratio_calc(a,"throughput-rps-calc"),
"jitter-interarrival-chk":jitter_interarrival_chk,
"hdr-histogram-log-view":hdr_histogram_log_view,
"malloc-count-hook-cli":malloc_count_hook_cli,
"mmap-allocation-tracer":mmap_allocation_tracer,
"brk-heap-expansion-chk":brk_heap_expansion_chk,
"page-fault-counter-cli":page_fault_counter_cli,
"tlb-miss-ratio-analyzer":lambda a:ratio_calc(a,"tlb-miss-ratio-analyzer"),
"context-switch-cost-est":context_switch_cost_est,
"thread-pool-saturation":thread_pool_saturation,
"epoll-latency-bench":epoll_latency_bench,
"select-poll-scale-bench":select_poll_scale_bench,
"io-uring-probe-support":io_uring_probe_support,
"io-uring-sq-poll-view":io_uring_sq_poll_view,
"futex-contention-timer":futex_contention_timer,
"spinlock-cycles-wasted":spinlock_cycles_wasted,
"cpu-cache-line-bouncing":cpu_cache_line_bouncing,
"numa-memory-distance":numa_memory_distance,
"sched-wakeup-latency":sched_wakeup_latency,
"irq-cpu-affinity-view":irq_cpu_affinity_view,
"disk-queue-depth-bench":disk_queue_depth_bench,
"disk-iops-calculator":lambda a:ratio_calc(a,"disk-iops-calculator"),
"tcp-rtt-smoothing-calc":tcp_rtt_smoothing_calc,
"tcp-cwnd-growth-analyzer":tcp_cwnd_growth_analyzer,
"buffer-copy-throughput":buffer_copy_throughput,
"zero-copy-splice-bench":zero_copy_splice_bench,
"memory-leak-growth-rate":memory_leak_growth_rate,
"resident-set-growth-chk":resident_set_growth_chk,
"virtual-memory-size-view":virtual_memory_size_view,
"garbage-collector-pause":garbage_collector_pause,
"allocator-fragmentation":allocator_fragmentation,
"simd-vector-width-probe":simd_vector_width_probe,
"neon-fp-pipeline-bench":neon_fp_pipeline_bench,
"cpu-throttle-detector":cpu_throttle_detector,
"thermal-governor-latency":thermal_governor_latency,
"power-consumption-model":power_consumption_model,
"perf-script-filter-cli":perf_script_filter_cli,
"call-graph-dot-generator":call_graph_dot_generator,
}

def main():
    if len(COMMANDS)!=50: die(f"internal command count mismatch: {len(COMMANDS)}")
    prog=Path(sys.argv[0]).name
    if prog in COMMANDS: cmd=prog; args=sys.argv[1:]
    else:
        if len(sys.argv)<2 or sys.argv[1] in ("-h","--help"):
            print("OceanStudio functional shard 26 runtime")
            for n in sorted(COMMANDS): print(" ",n)
            return
        if sys.argv[1] in ("-v","--version"): print(VERSION); return
        cmd=sys.argv[1]; args=sys.argv[2:]
    if cmd not in COMMANDS: die(f"unknown command: {cmd}")
    COMMANDS[cmd](args)

if __name__=="__main__": main()
