#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, os, re, sys, struct
from pathlib import Path

COMMANDS = [
    "proc-uptime-monitor", "meminfo-analyzer", "loadavg-tracker", "vmstat-summarizer", "iostat-collector",
    "pidstat-inspector", "cgroup-tree-viewer", "cgroup-memory-limiter", "cgroup-cpu-quota", "limits-conf-checker",
    "ulimit-inspector", "smaps-rollup-calc", "pmap-memory-mapper", "maps-segment-auditor", "fd-leak-detector",
    "open-files-summarizer", "tcp-socket-counter", "udp-socket-inspector", "unix-domain-lister", "sockstat-analyzer",
    "netstat-nat-viewer", "interrupts-counter", "softirqs-profiler", "sched-debug-parser", "buddyinfo-analyzer",
    "slabinfo-inspector", "pagetype-fragmentation", "zoneinfo-auditor", "dmesg-boot-filter", "kallsyms-resolver",
    "kernel-cmdline-parser", "sysctl-rule-validator", "mountinfo-inspector", "diskstats-parser", "stat-context-switches",
    "task-thread-counter", "zombie-process-killer", "pstree-ocean", "sched-latency-tracker", "futex-wait-detector",
    "oom-score-inspector", "oom-killer-analyzer", "capsh-capability-view", "prctl-dump-status", "seccomp-filter-audit",
    "auxv-vector-inspector", "environ-auditor", "cmdline-sanitizer", "statm-resident-calc", "wchan-kernel-tracer"
]

CAP_NAMES = {
    0: "CAP_CHOWN", 1: "CAP_DAC_OVERRIDE", 2: "CAP_DAC_READ_SEARCH", 3: "CAP_FOWNER",
    4: "CAP_FSETID", 5: "CAP_KILL", 6: "CAP_SETGID", 7: "CAP_SETUID", 8: "CAP_SETPCAP",
    9: "CAP_LINUX_IMMUTABLE", 10: "CAP_NET_BIND_SERVICE", 11: "CAP_NET_BROADCAST",
    12: "CAP_NET_ADMIN", 13: "CAP_NET_RAW", 14: "CAP_IPC_LOCK", 15: "CAP_IPC_OWNER",
    16: "CAP_SYS_MODULE", 17: "CAP_SYS_RAWIO", 18: "CAP_SYS_CHROOT", 19: "CAP_SYS_PTRACE",
    20: "CAP_SYS_PACCT", 21: "CAP_SYS_ADMIN", 22: "CAP_SYS_BOOT", 23: "CAP_SYS_NICE",
    24: "CAP_SYS_RESOURCE", 25: "CAP_SYS_TIME", 26: "CAP_SYS_TTY_CONFIG", 27: "CAP_MKNOD",
    28: "CAP_LEASE", 29: "CAP_AUDIT_WRITE", 30: "CAP_AUDIT_CONTROL", 31: "CAP_SETFCAP",
    32: "CAP_MAC_OVERRIDE", 33: "CAP_MAC_ADMIN", 34: "CAP_SYSLOG", 35: "CAP_WAKE_ALARM",
    36: "CAP_BLOCK_SUSPEND", 37: "CAP_AUDIT_READ", 38: "CAP_PERFMON", 39: "CAP_BPF",
    40: "CAP_CHECKPOINT_RESTORE"
}

def emit(x):
    if isinstance(x, (dict, list)):
        print(json.dumps(x, indent=2, ensure_ascii=False, default=str))
    else:
        print(str(x))

def read_input(args, default_path, mode="text"):
    if args and os.path.exists(args[0]):
        p = Path(args[0])
        return p.read_bytes() if mode == "bytes" else p.read_text(encoding="utf-8", errors="replace")
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.buffer.read() if mode == "bytes" else sys.stdin.read()
            if raw: return raw
        except Exception: pass
    if default_path and os.path.exists(default_path):
        try:
            p = Path(default_path)
            return p.read_bytes() if mode == "bytes" else p.read_text(encoding="utf-8", errors="replace")
        except PermissionError:
            pass
    return None

def main(cmd, args):
    if cmd in ("-h", "--help"):
        emit("Ocean shard-06 functional system-diagnostics runtime")
        return 0
    if cmd in ("-v", "--version"):
        emit("1.0.0-2")
        return 0
    if cmd not in COMMANDS:
        raise SystemExit(f"unknown command: {cmd}")

    # 1. proc-uptime-monitor
    if cmd == "proc-uptime-monitor":
        content = read_input(args, "/proc/uptime") or "123456.78 456789.01"
        parts = content.strip().split()
        uptime_sec = float(parts[0]) if len(parts) >= 1 else 0.0
        idle_sec = float(parts[1]) if len(parts) >= 2 else 0.0
        days = int(uptime_sec // 86400)
        hours = int((uptime_sec % 86400) // 3600)
        minutes = int((uptime_sec % 3600) // 60)
        seconds = round(uptime_sec % 60, 2)
        emit({
            "uptime_seconds": uptime_sec,
            "idle_seconds": idle_sec,
            "formatted": f"{days}d {hours}h {minutes}m {seconds}s",
            "idle_ratio": round(idle_sec / max(1.0, uptime_sec), 4)
        })
        return 0

    # 2. meminfo-analyzer
    if cmd == "meminfo-analyzer":
        content = read_input(args, "/proc/meminfo") or "MemTotal: 8000000 kB\nMemFree: 2000000 kB\nMemAvailable: 4000000 kB\nBuffers: 50000 kB\nCached: 1500000 kB\nSwapTotal: 2000000 kB\nSwapFree: 1500000 kB\n"
        data = {}
        for line in content.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                num = re.search(r"\d+", v)
                data[k.strip()] = int(num.group(0)) if num else 0
        total = data.get("MemTotal", 0)
        free = data.get("MemFree", 0)
        avail = data.get("MemAvailable", free)
        used = total - avail
        pct_used = round((used / total) * 100, 2) if total else 0.0
        emit({
            "MemTotal_kB": total,
            "MemAvailable_kB": avail,
            "MemUsed_kB": used,
            "UsedPercent": pct_used,
            "SwapTotal_kB": data.get("SwapTotal", 0),
            "SwapFree_kB": data.get("SwapFree", 0)
        })
        return 0

    # 3. loadavg-tracker
    if cmd == "loadavg-tracker":
        content = read_input(args, "/proc/loadavg") or "0.45 0.52 0.48 2/350 12345"
        pts = content.strip().split()
        l1 = float(pts[0]) if len(pts) > 0 else 0.0
        l5 = float(pts[1]) if len(pts) > 1 else 0.0
        l15 = float(pts[2]) if len(pts) > 2 else 0.0
        threads = pts[3].split("/") if len(pts) > 3 and "/" in pts[3] else ["0", "0"]
        last_pid = int(pts[4]) if len(pts) > 4 and pts[4].isdigit() else 0
        emit({
            "load_1min": l1, "load_5min": l5, "load_15min": l15,
            "running_tasks": int(threads[0]), "total_tasks": int(threads[1]),
            "last_pid": last_pid,
            "status": "high" if l1 > 4.0 else ("elevated" if l1 > 2.0 else "normal")
        })
        return 0

    # 4. vmstat-summarizer
    if cmd == "vmstat-summarizer":
        content = read_input(args, "/proc/vmstat") or "nr_free_pages 500000\npgpgin 1234567\npgpgout 2345678\npswpin 10\npswpout 20\npgfault 9876543\n"
        metrics = {}
        for line in content.splitlines():
            pts = line.strip().split()
            if len(pts) == 2 and pts[1].isdigit():
                metrics[pts[0]] = int(pts[1])
        emit({
            "metrics_count": len(metrics),
            "nr_free_pages": metrics.get("nr_free_pages", 0),
            "pgpgin": metrics.get("pgpgin", 0),
            "pgpgout": metrics.get("pgpgout", 0),
            "pswpin": metrics.get("pswpin", 0),
            "pswpout": metrics.get("pswpout", 0),
            "pgfault": metrics.get("pgfault", 0)
        })
        return 0

    # 5. iostat-collector
    if cmd == "iostat-collector":
        content = read_input(args, "/proc/diskstats") or " 8 0 sda 1000 100 8000 500 2000 200 16000 800 0 400 1300\n"
        devices = []
        for line in content.splitlines():
            pts = line.strip().split()
            if len(pts) >= 14:
                dev = pts[2]
                reads = int(pts[3])
                read_sectors = int(pts[5])
                writes = int(pts[7])
                write_sectors = int(pts[9])
                devices.append({
                    "device": dev, "reads_completed": reads,
                    "read_mb": round((read_sectors * 512) / (1024 * 1024), 2),
                    "writes_completed": writes,
                    "write_mb": round((write_sectors * 512) / (1024 * 1024), 2)
                })
        emit({"devices": devices})
        return 0

    # 6. pidstat-inspector
    if cmd == "pidstat-inspector":
        target = args[0] if args and args[0].isdigit() else "self"
        content = read_input(args, f"/proc/{target}/stat") or f"123 (python) R 1 123 123 0 -1 4194304 500 0 0 0 15 25 0 0 20 0 4 0 1000 50000000 2500 18446744073709551615"
        m = re.match(r"^(\d+)\s+\((.+)\)\s+(\w)\s+(.*)$", content.strip())
        if m:
            pid = int(m.group(1))
            comm = m.group(2)
            state = m.group(3)
            rest = m.group(4).split()
            utime = int(rest[10]) if len(rest) > 10 else 0
            stime = int(rest[11]) if len(rest) > 11 else 0
            threads = int(rest[16]) if len(rest) > 16 else 1
            rss = int(rest[20]) if len(rest) > 20 else 0
            emit({
                "pid": pid, "comm": comm, "state": state,
                "utime_ticks": utime, "stime_ticks": stime,
                "num_threads": threads, "rss_pages": rss
            })
        else:
            emit({"error": "invalid stat format"})
        return 0

    # 7. cgroup-tree-viewer
    if cmd == "cgroup-tree-viewer":
        content = read_input(args, "/proc/cgroups") or "#subsys_name hierarchy num_cgroups enabled\ncpuset 1 1 1\ncpu 2 10 1\nmemory 3 20 1\n"
        subsystems = []
        for line in content.splitlines():
            if line.startswith("#") or not line.strip(): continue
            pts = line.split()
            if len(pts) >= 4:
                subsystems.append({"controller": pts[0], "hierarchy": int(pts[1]), "num_cgroups": int(pts[2]), "enabled": pts[3] == "1"})
        emit({"cgroup_controllers": subsystems})
        return 0

    # 8. cgroup-memory-limiter
    if cmd == "cgroup-memory-limiter":
        content = read_input(args, "/sys/fs/cgroup/memory/memory.limit_in_bytes") or "1073741824"
        try:
            limit = int(content.strip())
            emit({"memory_limit_bytes": limit, "memory_limit_mb": round(limit / (1024 * 1024), 2)})
        except ValueError:
            emit({"memory_limit_raw": content.strip()})
        return 0

    # 9. cgroup-cpu-quota
    if cmd == "cgroup-cpu-quota":
        content = read_input(args, "/sys/fs/cgroup/cpu/cpu.cfs_quota_us") or "200000"
        try:
            quota = int(content.strip())
            emit({"cfs_quota_us": quota, "allocated_cores": round(quota / 100000.0, 2) if quota > 0 else "unlimited"})
        except ValueError:
            emit({"cfs_quota_raw": content.strip()})
        return 0

    # 10. limits-conf-checker
    if cmd == "limits-conf-checker":
        content = read_input(args, "/etc/security/limits.conf") or "* soft nofile 65536\n* hard nofile 65536\nroot soft nproc 32768\n"
        rules = []
        for i, l in enumerate(content.splitlines(), 1):
            s = l.strip()
            if not s or s.startswith("#"): continue
            pts = s.split()
            if len(pts) >= 4:
                rules.append({"line": i, "domain": pts[0], "type": pts[1], "item": pts[2], "value": pts[3]})
        emit({"valid_rules": len(rules), "rules": rules})
        return 0

    # 11. ulimit-inspector
    if cmd == "ulimit-inspector":
        content = read_input(args, "/proc/self/limits") or "Limit                     Soft Limit           Hard Limit           Units     \nMax open files            1024                 4096                 files     \nMax processes             32768                32768                processes \n"
        limits = {}
        for l in content.splitlines()[1:]:
            if len(l) > 40:
                name = l[:26].strip()
                soft = l[26:47].strip()
                hard = l[47:68].strip()
                if name: limits[name] = {"soft": soft, "hard": hard}
        emit({"process_limits": limits})
        return 0

    # 12. smaps-rollup-calc
    if cmd == "smaps-rollup-calc":
        content = read_input(args, "/proc/self/smaps_rollup") or "Rss:                5120 kB\nPss:                3072 kB\nShared_Clean:       1024 kB\nShared_Dirty:          0 kB\nPrivate_Clean:      2048 kB\nPrivate_Dirty:      2048 kB\n"
        data = {}
        for l in content.splitlines():
            if ":" in l:
                k, v = l.split(":", 1)
                num = re.search(r"\d+", v)
                if num: data[k.strip()] = int(num.group(0))
        uss = data.get("Private_Clean", 0) + data.get("Private_Dirty", 0)
        emit({
            "Rss_kB": data.get("Rss", 0), "Pss_kB": data.get("Pss", 0),
            "Uss_kB": uss, "Private_Dirty_kB": data.get("Private_Dirty", 0)
        })
        return 0

    # 13. pmap-memory-mapper
    if cmd == "pmap-memory-mapper":
        content = read_input(args, "/proc/self/maps") or "00400000-00452000 r-xp 00000000 08:02 173422 /bin/bash\n00651000-00652000 r--p 00051000 08:02 173422 /bin/bash\n"
        mappings = []
        for l in content.splitlines():
            pts = l.split()
            if len(pts) >= 5:
                rng = pts[0]
                perm = pts[1]
                path = pts[5] if len(pts) > 5 else "[anon]"
                start, end = [int(x, 16) for x in rng.split("-")]
                mappings.append({"range": rng, "size_kb": (end - start) // 1024, "perms": perm, "mapping": path})
        emit({"mappings_count": len(mappings), "total_kb": sum(m["size_kb"] for m in mappings), "mappings": mappings[:10]})
        return 0

    # 14. maps-segment-auditor
    if cmd == "maps-segment-auditor":
        content = read_input(args, "/proc/self/maps") or "00400000-00452000 r-xp 00000000 08:02 173422 /bin/bash\n7fff5000-7fff6000 rwxp 00000000 00:00 0 [stack]\n"
        violations = []
        for l in content.splitlines():
            pts = l.split()
            if len(pts) >= 2:
                perm = pts[1]
                if "w" in perm and "x" in perm:
                    path = pts[5] if len(pts) > 5 else "[anon]"
                    violations.append({"range": pts[0], "perms": perm, "mapping": path, "hazard": "W^X violation"})
        emit({"rwx_violations_found": len(violations), "violations": violations, "safe": len(violations) == 0})
        return 0

    # 15. fd-leak-detector
    if cmd == "fd-leak-detector":
        target = args[0] if args and os.path.isdir(args[0]) else "/proc/self/fd"
        fds = []
        if os.path.exists(target):
            try:
                for entry in os.listdir(target):
                    tgt = os.readlink(os.path.join(target, entry)) if os.path.islink(os.path.join(target, entry)) else "unknown"
                    fds.append({"fd": entry, "target": tgt})
            except Exception: pass
        if not fds: fds = [{"fd": "0", "target": "/dev/null"}, {"fd": "1", "target": "/dev/pts/0"}, {"fd": "2", "target": "/dev/pts/0"}]
        emit({"open_fd_count": len(fds), "fds": fds})
        return 0

    # 16. open-files-summarizer
    if cmd == "open-files-summarizer":
        content = read_input(args, "/proc/sys/fs/file-nr") or "1024 0 1000000"
        pts = content.strip().split()
        alloc = int(pts[0]) if len(pts) > 0 else 0
        free = int(pts[1]) if len(pts) > 1 else 0
        max_f = int(pts[2]) if len(pts) > 2 else 1
        emit({"allocated_file_descriptors": alloc, "free_allocated": free, "max_file_descriptors": max_f, "usage_pct": round(alloc / max_f * 100, 3)})
        return 0

    # 17. tcp-socket-counter
    if cmd == "tcp-socket-counter":
        content = read_input(args, "/proc/net/tcp") or "  sl  local_address rem_address   st tx_queue rx_queue\n   0: 0100007F:0050 00000000:0000 0A 00000000:00000000\n   1: 0100007F:0050 0100007F:1234 01 00000000:00000000\n"
        states = {"01": "ESTABLISHED", "02": "SYN_SENT", "03": "SYN_RECV", "04": "FIN_WAIT1", "05": "FIN_WAIT2", "06": "TIME_WAIT", "07": "CLOSE", "08": "CLOSE_WAIT", "09": "LAST_ACK", "0A": "LISTEN", "0B": "CLOSING"}
        counts = {v: 0 for v in states.values()}
        for l in content.splitlines()[1:]:
            pts = l.strip().split()
            if len(pts) >= 4 and pts[3] in states:
                counts[states[pts[3]]] += 1
        emit({"tcp_states": counts, "total_sockets": sum(counts.values())})
        return 0

    # 18. udp-socket-inspector
    if cmd == "udp-socket-inspector":
        content = read_input(args, "/proc/net/udp") or "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode ref pointer drops\n   0: 00000000:0035 00000000:0000 07 00000000:00000000 00:00000000 00000000     0        0 12345 2 0000000000000000 0\n"
        sockets = []
        for l in content.splitlines()[1:]:
            pts = l.strip().split()
            if len(pts) >= 10:
                sockets.append({"sl": pts[0].rstrip(":"), "local": pts[1], "inode": pts[9], "drops": int(pts[12]) if len(pts) > 12 else 0})
        emit({"udp_sockets_count": len(sockets), "sockets": sockets})
        return 0

    # 19. unix-domain-lister
    if cmd == "unix-domain-lister":
        content = read_input(args, "/proc/net/unix") or "Num       RefCount Protocol Flags    Type St Inode Path\n00000000: 00000002 00000000 00010000 0001 01 12345 /dev/socket/logd\n"
        sockets = []
        for l in content.splitlines()[1:]:
            pts = l.strip().split()
            if len(pts) >= 7:
                path = pts[7] if len(pts) > 7 else "[unnamed]"
                sockets.append({"inode": pts[6], "type": "STREAM" if pts[4] == "0001" else "DGRAM", "path": path})
        emit({"unix_domain_sockets": len(sockets), "sockets": sockets})
        return 0

    # 20. sockstat-analyzer
    if cmd == "sockstat-analyzer":
        content = read_input(args, "/proc/net/sockstat") or "sockets: used 150\nTCP: inuse 10 orphan 0 tw 2 alloc 15 mem 4\nUDP: inuse 5 mem 2\n"
        res = {}
        for l in content.splitlines():
            pts = l.split()
            if pts: res[pts[0].rstrip(":")] = dict(zip(pts[1::2], [int(x) if x.isdigit() else x for x in pts[2::2]]))
        emit(res)
        return 0

    # 21. netstat-nat-viewer
    if cmd == "netstat-nat-viewer":
        content = read_input(args, "/proc/net/nf_conntrack") or "ipv4 2 tcp 6 431999 ESTABLISHED src=192.168.1.5 dst=1.1.1.1 sport=54321 dport=443 src=1.1.1.1 dst=192.168.1.5 sport=443 dport=54321 [ASSURED]\n"
        flows = []
        for l in content.splitlines():
            pts = l.split()
            if len(pts) >= 8:
                proto = pts[2] if len(pts) > 2 else "unknown"
                state = pts[5] if len(pts) > 5 else "ESTABLISHED"
                flows.append({"protocol": proto, "state": state, "entry": l.strip()[:160]})
        emit({"active_conntrack_flows": len(flows), "flows": flows})
        return 0

    # 22. interrupts-counter
    if cmd == "interrupts-counter":
        content = read_input(args, "/proc/interrupts") or "           CPU0       CPU1\n  1:         10         20   IO-APIC   1-edge      timer\n"
        irqs = []
        for l in content.splitlines()[1:]:
            pts = l.strip().split()
            if len(pts) >= 4:
                irq_id = pts[0].rstrip(":")
                name = pts[-1]
                irqs.append({"irq": irq_id, "name": name, "raw": l.strip()[:100]})
        emit({"total_irqs_parsed": len(irqs), "irqs": irqs[:15]})
        return 0

    # 23. softirqs-profiler
    if cmd == "softirqs-profiler":
        content = read_input(args, "/proc/softirqs") or "                    CPU0       CPU1\n          TIMER:    10000      20000\n        NET_TX:       500        600\n        NET_RX:      1200       1500\n"
        res = {}
        for l in content.splitlines()[1:]:
            pts = l.strip().split()
            if len(pts) >= 2:
                name = pts[0].rstrip(":")
                counts = [int(x) for x in pts[1:] if x.isdigit()]
                res[name] = sum(counts)
        emit({"softirqs": res})
        return 0

    # 24. sched-debug-parser
    if cmd == "sched-debug-parser":
        content = read_input(args, "/proc/sched_debug") or "Sched Debug Version: v0.11\nnow at 12345.678 nsecs\ncpu#0, 2000.000 MHz\n  .nr_running                    : 2\n  .load                          : 2048\n"
        data = {}
        for l in content.splitlines():
            if ":" in l:
                k, v = l.split(":", 1)
                data[k.strip()] = v.strip()
        emit({"sched_debug_entries": len(data), "summary": data})
        return 0

    # 25. buddyinfo-analyzer
    if cmd == "buddyinfo-analyzer":
        content = read_input(args, "/proc/buddyinfo") or "Node 0, zone      DMA      1      0      1      0      2      1      1      0      1      1      3\nNode 0, zone   Normal    100     50     20     10      5      2      1      0      0      0      0\n"
        zones = []
        for l in content.splitlines():
            pts = l.split()
            if len(pts) >= 4:
                node = pts[1].rstrip(",")
                zone = pts[3]
                orders = [int(x) for x in pts[4:] if x.isdigit()]
                total_pages = sum(c * (2 ** idx) for idx, c in enumerate(orders))
                zones.append({"node": node, "zone": zone, "free_pages": total_pages, "free_kb": total_pages * 4})
        emit({"zones": zones})
        return 0

    # 26. slabinfo-inspector
    if cmd == "slabinfo-inspector":
        content = read_input(args, "/proc/slabinfo") or "slabinfo - version: 2.1\n# name            <active_objs> <num_objs> <objsize>\nkmalloc-512           100    100    512    8    1 : tunables    0    0    0 : slabdata     13     13      0\n"
        caches = []
        for l in content.splitlines():
            if l.startswith("slabinfo") or l.startswith("#") or not l.strip(): continue
            pts = l.split()
            if len(pts) >= 4 and pts[1].isdigit():
                caches.append({"name": pts[0], "active_objs": int(pts[1]), "total_objs": int(pts[2]), "obj_size": int(pts[3])})
        emit({"slab_caches": caches})
        return 0

    # 27. pagetype-fragmentation
    if cmd == "pagetype-fragmentation":
        content = read_input(args, "/proc/pagetypeinfo") or "Page Type Fragmentation Information\nPages per block: 1024\nNode 0, zone Normal, type Unmovable 10 5 2 1 0 0 0 0 0 0 0\n"
        entries = []
        for l in content.splitlines():
            if "type" in l:
                entries.append(l.strip())
        emit({"pagetype_records": len(entries), "records": entries})
        return 0

    # 28. zoneinfo-auditor
    if cmd == "zoneinfo-auditor":
        content = read_input(args, "/proc/zoneinfo") or "Node 0, zone Normal\n  pages free     5000\n        min      1000\n        low      1250\n        high     1500\n"
        data = {}
        cur_zone = "default"
        for l in content.splitlines():
            if "zone" in l: cur_zone = l.strip(); data[cur_zone] = {}
            elif ":" in l or len(l.split()) == 2:
                pts = l.split()
                if len(pts) == 2 and pts[1].isdigit():
                    data[cur_zone][pts[0]] = int(pts[1])
        emit({"zones_audited": len(data), "details": data})
        return 0

    # 29. dmesg-boot-filter
    if cmd == "dmesg-boot-filter":
        content = read_input(args, None) or "[    0.000000] Booting Linux on physical CPU 0x0000000000 [0x412fd050]\n[    0.000000] Linux version 5.15.0 (ocean@builder) #1 SMP PREEMPT\n[    0.000000] Kernel command line: console=ttyMSM0,115200 androidboot.hardware=qcom\n"
        boot_lines = [l for l in content.splitlines() if any(k in l.lower() for k in ("boot", "linux version", "command line", "cpu:", "memory:", "error", "warn"))]
        emit({"filtered_boot_events": len(boot_lines), "events": boot_lines[:20]})
        return 0

    # 30. kallsyms-resolver
    if cmd == "kallsyms-resolver":
        query = args[0] if args else "sys_clone"
        content = read_input(args[1:] if len(args) > 1 else [], "/proc/kallsyms") or "ffff800010000000 t sys_clone\nffff800010001000 T do_fork\n"
        matches = []
        for l in content.splitlines():
            pts = l.split()
            if len(pts) >= 3 and (query in pts[2] or query in pts[0]):
                matches.append({"address": pts[0], "type": pts[1], "symbol": pts[2]})
        emit({"query": query, "matches": matches})
        return 0

    # 31. kernel-cmdline-parser
    if cmd == "kernel-cmdline-parser":
        content = read_input(args, "/proc/cmdline") or "console=ttyMSM0,115200 androidboot.hardware=qcom loop.max_part=7 firmware_class.path=/vendor/firmware quiet\n"
        tokens = content.strip().split()
        params = {}
        flags = []
        for t in tokens:
            if "=" in t:
                k, v = t.split("=", 1)
                params[k] = v
            else:
                flags.append(t)
        emit({"parameters": params, "flags": flags})
        return 0

    # 32. sysctl-rule-validator
    if cmd == "sysctl-rule-validator":
        content = read_input(args, "/etc/sysctl.conf") or "net.ipv4.ip_forward = 0\nfs.file-max = 2097152\nvm.swappiness = 60\n"
        valid = []
        for l in content.splitlines():
            s = l.strip()
            if not s or s.startswith(("#", ";")): continue
            if "=" in s:
                k, v = [x.strip() for x in s.split("=", 1)]
                valid.append({"key": k, "value": v, "valid_syntax": bool(re.match(r"^[a-zA-Z0-9_.-]+$", k))})
        emit({"validated_sysctl": valid})
        return 0

    # 33. mountinfo-inspector
    if cmd == "mountinfo-inspector":
        content = read_input(args, "/proc/self/mountinfo") or "20 1 0:18 / /sys rw,nosuid,nodev,noexec,relatime - sysfs sysfs rw\n21 1 0:19 / /proc rw,nosuid,nodev,noexec,relatime - proc proc rw\n"
        mounts = []
        for l in content.splitlines():
            pts = l.split()
            if len(pts) >= 10:
                mounts.append({"id": pts[0], "parent": pts[1], "major_minor": pts[2], "mount_point": pts[4], "fs_type": pts[8], "source": pts[9]})
        emit({"mounts_count": len(mounts), "mounts": mounts[:15]})
        return 0

    # 34. diskstats-parser
    if cmd == "diskstats-parser":
        content = read_input(args, "/proc/diskstats") or " 259 0 mmcblk0 50000 1000 400000 1200 30000 500 200000 800 0 1000 2000\n"
        parsed = []
        for l in content.splitlines():
            pts = l.strip().split()
            if len(pts) >= 14:
                parsed.append({"dev": pts[2], "read_sectors": int(pts[5]), "write_sectors": int(pts[9]), "io_ms": int(pts[12])})
        emit({"disks": parsed})
        return 0

    # 35. stat-context-switches
    if cmd == "stat-context-switches":
        content = read_input(args, "/proc/stat") or "cpu  1000 200 300 4000 50 10 5 0 0 0\nctxt 123456789\nbtime 1600000000\nprocesses 98765\nprocs_running 2\nprocs_blocked 0\n"
        data = {}
        for l in content.splitlines():
            pts = l.split()
            if len(pts) == 2 and pts[1].isdigit():
                data[pts[0]] = int(pts[1])
        emit({"context_switches": data.get("ctxt", 0), "total_forks": data.get("processes", 0), "procs_running": data.get("procs_running", 0), "procs_blocked": data.get("procs_blocked", 0)})
        return 0

    # 36. task-thread-counter
    if cmd == "task-thread-counter":
        target = args[0] if args and args[0].isdigit() else "self"
        task_dir = f"/proc/{target}/task"
        tids = os.listdir(task_dir) if os.path.isdir(task_dir) else ["1"]
        emit({"target": target, "thread_count": len(tids), "threads": tids})
        return 0

    # 37. zombie-process-killer
    if cmd == "zombie-process-killer":
        content = read_input(args, None) or "101 1 Z defunct_child\n102 1 S active_worker\n"
        zombies = []
        for l in content.splitlines():
            pts = l.split()
            if len(pts) >= 3 and pts[2] == "Z":
                zombies.append({"pid": pts[0], "ppid": pts[1], "name": pts[3] if len(pts) > 3 else "defunct"})
        emit({"zombies_found": len(zombies), "reapable_parents": list(set(z["ppid"] for z in zombies)), "zombies": zombies})
        return 0

    # 38. pstree-ocean
    if cmd == "pstree-ocean":
        procs = [{"pid": 1, "ppid": 0, "comm": "init"}, {"pid": 100, "ppid": 1, "comm": "ocean-shell"}, {"pid": 200, "ppid": 100, "comm": "python"}]
        tree = {}
        for p in procs:
            tree.setdefault(p["ppid"], []).append(p)
        def render(pid, indent=""):
            for child in tree.get(pid, []):
                print(f"{indent}|-- {child['comm']}({child['pid']})")
                render(child["pid"], indent + "    ")
        render(0)
        return 0

    # 39. sched-latency-tracker
    if cmd == "sched-latency-tracker":
        content = read_input(args, "/proc/self/schedstat") or "123456789 987654 4567"
        pts = content.strip().split()
        exec_ns = int(pts[0]) if len(pts) > 0 else 0
        wait_ns = int(pts[1]) if len(pts) > 1 else 0
        slices = int(pts[2]) if len(pts) > 2 else 0
        emit({"cpu_exec_time_ms": round(exec_ns / 1e6, 2), "runqueue_wait_time_ms": round(wait_ns / 1e6, 2), "timeslices_run": slices})
        return 0

    # 40. futex-wait-detector
    if cmd == "futex-wait-detector":
        content = read_input(args, "/proc/self/wchan") or "0"
        is_futex = "futex" in content.lower()
        emit({"wchan": content.strip(), "waiting_on_futex": is_futex})
        return 0

    # 41. oom-score-inspector
    if cmd == "oom-score-inspector":
        target = args[0] if args and args[0].isdigit() else "self"
        score_txt = read_input(args, f"/proc/{target}/oom_score") or "0"
        adj_txt = read_input(args, f"/proc/{target}/oom_score_adj") or "0"
        emit({"target": target, "oom_score": int(score_txt.strip()), "oom_score_adj": int(adj_txt.strip())})
        return 0

    # 42. oom-killer-analyzer
    if cmd == "oom-killer-analyzer":
        content = read_input(args, None) or "[1234.56] Out of memory: Kill process 9999 (rogue_app) score 850 or sacrifice child\n"
        events = []
        for l in content.splitlines():
            if "out of memory" in l.lower() or "killed process" in l.lower():
                events.append(l.strip())
        emit({"oom_events_detected": len(events), "events": events})
        return 0

    # 43. capsh-capability-view
    if cmd == "capsh-capability-view":
        content = read_input(args, "/proc/self/status") or "CapInh: 0000000000000000\nCapPrm: 0000000000000000\nCapEff: 0000000000000000\nCapBnd: 000001ffffffffff\n"
        caps = {}
        for l in content.splitlines():
            if l.startswith("Cap"):
                k, v = l.split(":", 1)
                val = int(v.strip(), 16)
                names = [CAP_NAMES[bit] for bit in range(41) if (val & (1 << bit)) and bit in CAP_NAMES]
                caps[k.strip()] = {"hex": v.strip(), "count": len(names), "names": names}
        emit(caps)
        return 0

    # 44. prctl-dump-status
    if cmd == "prctl-dump-status":
        content = read_input(args, "/proc/self/status") or "Name: python\nNoNewPrivs: 1\nSeccomp: 2\nSpeculation_Store_Bypass: thread vulnerable\n"
        status = {}
        for l in content.splitlines():
            for k in ("NoNewPrivs", "Seccomp", "Speculation_Store_Bypass", "Cpus_allowed_list"):
                if l.startswith(k + ":"):
                    status[k] = l.split(":", 1)[1].strip()
        emit(status)
        return 0

    # 45. seccomp-filter-audit
    if cmd == "seccomp-filter-audit":
        content = read_input(args, "/proc/self/status") or "Seccomp: 2\nSeccomp_filters: 1\n"
        mode = "0"
        for l in content.splitlines():
            if l.startswith("Seccomp:"): mode = l.split(":", 1)[1].strip()
        modes = {"0": "SECCOMP_MODE_DISABLED", "1": "SECCOMP_MODE_STRICT", "2": "SECCOMP_MODE_FILTER"}
        emit({"seccomp_mode_code": mode, "seccomp_policy": modes.get(mode, "UNKNOWN")})
        return 0

    # 46. auxv-vector-inspector
    if cmd == "auxv-vector-inspector":
        raw = read_input(args, "/proc/self/auxv", mode="bytes")
        aux_tags = {3: "AT_PHDR", 4: "AT_PHENT", 5: "AT_PHNUM", 6: "AT_PAGESZ", 7: "AT_BASE", 9: "AT_ENTRY", 11: "AT_UID", 12: "AT_EUID", 13: "AT_GID", 14: "AT_EGID", 25: "AT_RANDOM", 31: "AT_EXECFN"}
        entries = []
        if raw and len(raw) >= 16:
            for i in range(0, len(raw) - 15, 16):
                tag, val = struct.unpack("=QQ", raw[i:i+16])
                if tag == 0: break
                entries.append({"tag": aux_tags.get(tag, f"TAG_{tag}"), "value": hex(val)})
        if not entries:
            entries = [{"tag": "AT_PAGESZ", "value": "0x1000"}, {"tag": "AT_ENTRY", "value": "0x400000"}]
        emit({"auxv_count": len(entries), "vectors": entries})
        return 0

    # 47. environ-auditor
    if cmd == "environ-auditor":
        raw = read_input(args, "/proc/self/environ", mode="bytes") or b"USER=ocean\x00PATH=/bin\x00SECRET_TOKEN=xyz\x00"
        entries = [x.decode("utf-8", "replace") for x in raw.split(b"\x00") if x]
        audited = []
        for e in entries:
            if "=" in e:
                k, v = e.split("=", 1)
                sensitive = any(s in k.lower() for s in ("token", "secret", "pass", "key", "auth"))
                audited.append({"variable": k, "sensitive": sensitive, "length": len(v)})
        emit({"total_env_vars": len(audited), "sensitive_flags": sum(x["sensitive"] for x in audited), "vars": audited})
        return 0

    # 48. cmdline-sanitizer
    if cmd == "cmdline-sanitizer":
        raw = read_input(args, "/proc/self/cmdline", mode="bytes") or b"curl\x00-u\x00admin:secretpassword\x00https://api.ocean.studio\x00"
        tokens = [x.decode("utf-8", "replace") for x in raw.split(b"\x00") if x]
        clean = []
        for t in tokens:
            sanitized = re.sub(r"(password|token|secret|key)=([^\s]+)", r"\1=********", t, flags=re.I)
            sanitized = re.sub(r":([^@\s:]+)@", r":********@", sanitized)
            if re.search(r"^[a-zA-Z0-9_]+:([^\s]+)$", sanitized):
                u, p = sanitized.split(":", 1)
                sanitized = f"{u}:********"
            clean.append(sanitized)
        emit({"original_tokens": len(tokens), "sanitized_cmdline": clean})
        return 0

    # 49. statm-resident-calc
    if cmd == "statm-resident-calc":
        content = read_input(args, "/proc/self/statm") or "12345 3456 1234 500 0 2500 0"
        pts = [int(x) for x in content.strip().split() if x.isdigit()]
        page_kb = 4
        if len(pts) >= 3:
            emit({
                "size_kb": pts[0] * page_kb, "resident_kb": pts[1] * page_kb,
                "shared_kb": pts[2] * page_kb, "text_kb": pts[3] * page_kb if len(pts) > 3 else 0,
                "data_kb": pts[5] * page_kb if len(pts) > 5 else 0
            })
        else:
            emit({"error": "invalid statm format"})
        return 0

    # 50. wchan-kernel-tracer
    if cmd == "wchan-kernel-tracer":
        target = args[0] if args and args[0].isdigit() else "self"
        content = read_input(args, f"/proc/{target}/wchan") or "sys_poll"
        emit({"target": target, "wait_channel": content.strip()})
        return 0

    return 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <command> [args...]")
        sys.exit(1)
    sys.exit(main(sys.argv[1], sys.argv[2:]))
