#!/usr/bin/env python3
import importlib.util, pathlib, subprocess, sys, tempfile, json

runtime = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("r", runtime)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

assert len(m.COMMANDS) == 50 and len(set(m.COMMANDS)) == 50

def run(cmd, *args, input=None):
    r = subprocess.run([sys.executable, str(runtime), cmd, *map(str, args)], input=input, text=True, capture_output=True)
    if r.returncode not in (0, 1):
        raise AssertionError((cmd, r.returncode, r.stdout, r.stderr))
    return r

with tempfile.TemporaryDirectory() as td:
    d = pathlib.Path(td)
    up = d / "uptime"; up.write_text("12345.67 98765.43\n")
    mi = d / "meminfo"; mi.write_text("MemTotal: 8192000 kB\nMemFree: 2048000 kB\nMemAvailable: 4096000 kB\n")
    la = d / "loadavg"; la.write_text("0.15 0.25 0.35 1/250 9999\n")
    vm = d / "vmstat"; vm.write_text("nr_free_pages 1000\npgpgin 5000\npgpgout 6000\n")
    ds = d / "diskstats"; ds.write_text(" 8 0 sda 100 10 800 50 200 20 1600 80 0 40 130\n")
    cg = d / "cgroups"; cg.write_text("#subsys_name hierarchy num_cgroups enabled\ncpuset 1 1 1\n")
    lim = d / "limits.conf"; lim.write_text("* soft nofile 4096\n* hard nofile 8192\n")
    tcp = d / "tcp"; tcp.write_text("  sl  local_address rem_address   st tx_queue rx_queue\n   0: 0100007F:0050 00000000:0000 0A 00000000:00000000\n")
    udp = d / "udp"; udp.write_text("  sl  local_address rem_address   st tx_queue rx_queue\n   0: 00000000:0035 00000000:0000 07 00000000:00000000\n")
    unx = d / "unix"; unx.write_text("Num RefCount Protocol Flags Type St Inode Path\n0: 2 0 10000 1 1 12345 /dev/socket\n")
    sck = d / "sockstat"; sck.write_text("sockets: used 50\nTCP: inuse 5 orphan 0 tw 1 alloc 6 mem 2\n")
    nat = d / "nat"; nat.write_text("ipv4 2 tcp 6 100 ESTABLISHED src=10.0.0.1 dst=10.0.0.2\n")
    irq = d / "irq"; irq.write_text(" 1: 10 20 timer\n")
    sirq = d / "sirq"; sirq.write_text(" TIMER: 100 200\n")
    sdbg = d / "sdbg"; sdbg.write_text(".nr_running : 1\n.load : 1024\n")
    bdy = d / "buddy"; bdy.write_text("Node 0, zone Normal 1 2 3 4 5 0 0 0 0 0 0\n")
    slb = d / "slab"; slb.write_text("slabinfo - version: 2.1\nkmalloc-128 10 10 128 1 1\n")
    pag = d / "page"; pag.write_text("Node 0, zone Normal, type Unmovable 1 2 3\n")
    zon = d / "zone"; zon.write_text("Node 0, zone Normal\n  pages free 500\n min 100\n")
    dmsg = d / "dmesg"; dmsg.write_text("[ 0.000000] Booting Linux on physical CPU\n")
    ksym = d / "ksym"; ksym.write_text("ffff800010000000 T sys_clone\n")
    cmdl = d / "cmdline"; cmdl.write_text("console=tty0 root=/dev/sda1 quiet\n")
    sysc = d / "sysctl"; sysc.write_text("net.ipv4.ip_forward = 1\n")
    minf = d / "minf"; minf.write_text("1 0 0:1 / /proc rw - proc proc rw\n")
    stat = d / "stat"; stat.write_text("ctxt 50000\nprocesses 1200\n")
    zomb = d / "zombie"; zomb.write_text("100 1 Z defunct_task\n")

    tests = {
        "proc-uptime-monitor": (up,),
        "meminfo-analyzer": (mi,),
        "loadavg-tracker": (la,),
        "vmstat-summarizer": (vm,),
        "iostat-collector": (ds,),
        "pidstat-inspector": (),
        "cgroup-tree-viewer": (cg,),
        "cgroup-memory-limiter": (),
        "cgroup-cpu-quota": (),
        "limits-conf-checker": (lim,),
        "ulimit-inspector": (),
        "smaps-rollup-calc": (),
        "pmap-memory-mapper": (),
        "maps-segment-auditor": (),
        "fd-leak-detector": (),
        "open-files-summarizer": (),
        "tcp-socket-counter": (tcp,),
        "udp-socket-inspector": (udp,),
        "unix-domain-lister": (unx,),
        "sockstat-analyzer": (sck,),
        "netstat-nat-viewer": (nat,),
        "interrupts-counter": (irq,),
        "softirqs-profiler": (sirq,),
        "sched-debug-parser": (sdbg,),
        "buddyinfo-analyzer": (bdy,),
        "slabinfo-inspector": (slb,),
        "pagetype-fragmentation": (pag,),
        "zoneinfo-auditor": (zon,),
        "dmesg-boot-filter": (dmsg,),
        "kallsyms-resolver": ("sys_clone", ksym),
        "kernel-cmdline-parser": (cmdl,),
        "sysctl-rule-validator": (sysc,),
        "mountinfo-inspector": (minf,),
        "diskstats-parser": (ds,),
        "stat-context-switches": (stat,),
        "task-thread-counter": (),
        "zombie-process-killer": (zomb,),
        "pstree-ocean": (),
        "sched-latency-tracker": (),
        "futex-wait-detector": (),
        "oom-score-inspector": (),
        "oom-killer-analyzer": (dmsg,),
        "capsh-capability-view": (),
        "prctl-dump-status": (),
        "seccomp-filter-audit": (),
        "auxv-vector-inspector": (),
        "environ-auditor": (),
        "cmdline-sanitizer": (),
        "statm-resident-calc": (),
        "wchan-kernel-tracer": ()
    }

    assert set(tests) == set(m.COMMANDS), f"missing: {set(m.COMMANDS) - set(tests)}"
    for cmd, args in tests.items():
        res = run(cmd, *args)
        assert res.returncode == 0, f"{cmd} failed with {res.returncode}"

print("SUCCESS: exercised 50/50 shard-06 functional commands")
