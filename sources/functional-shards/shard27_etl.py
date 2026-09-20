#!/usr/bin/env python3
from __future__ import annotations

import base64
import csv
import datetime as dt
import hashlib
import hmac
import io
import ipaddress
import itertools
import json
import math
import os
import random
import re
import statistics
import struct
import sys
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path

VERSION = "2.0.0"
GROK = {
    "WORD": r"\b\w+\b",
    "NUMBER": r"[+-]?(?:\d+(?:\.\d+)?)",
    "INT": r"[+-]?\d+",
    "IP": r"(?:\d{1,3}\.){3}\d{1,3}",
    "IPORHOST": r"(?:[A-Za-z0-9_.-]+)",
    "DATA": r".*?",
    "GREEDYDATA": r".*",
    "NOTSPACE": r"\S+",
    "HTTPDATE": r"\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2} [+-]\d{4}",
    "QS": r'"(?:\\.|[^"])*"',
}

CLF_RE = re.compile(
    r'^(?P<host>\S+) (?P<ident>\S+) (?P<user>\S+) '
    r'\[(?P<time>[^\]]+)\] "(?P<request>[^"]*)" '
    r'(?P<status>\d{3}|-) (?P<size>\d+|-)$'
)
COMBINED_RE = re.compile(
    r'^(?P<host>\S+) (?P<ident>\S+) (?P<user>\S+) '
    r'\[(?P<time>[^\]]+)\] "(?P<request>[^"]*)" '
    r'(?P<status>\d{3}|-) (?P<size>\d+|-) '
    r'"(?P<referer>[^"]*)" "(?P<agent>[^"]*)"$'
)

def die(msg: str, code: int = 2):
    print(msg, file=sys.stderr)
    raise SystemExit(code)

def read_text(path: str | None = None) -> str:
    if path and path != "-":
        return Path(path).read_text(encoding="utf-8", errors="replace")
    return sys.stdin.read()

def read_bytes(path: str | None = None) -> bytes:
    if path and path != "-":
        return Path(path).read_bytes()
    return sys.stdin.buffer.read()

def write_json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))

def parse_table(text: str, delimiter: str):
    return list(csv.reader(io.StringIO(text), delimiter=delimiter))

def emit_table(rows, delimiter: str):
    out = io.StringIO()
    w = csv.writer(out, delimiter=delimiter, lineterminator="\n")
    w.writerows(rows)
    sys.stdout.write(out.getvalue())

def column_index(header, spec: str) -> int:
    if re.fullmatch(r"\d+", spec):
        i = int(spec)
        if i < 0 or i >= len(header):
            die(f"column index out of range: {i}")
        return i
    try:
        return header.index(spec)
    except ValueError:
        die(f"unknown column: {spec}")

def scalar(s: str):
    lo = s.lower()
    if lo == "true":
        return True
    if lo == "false":
        return False
    if lo in ("null", "none"):
        return None
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return s

def flatten_obj(v, prefix="", out=None):
    if out is None:
        out = {}
    if isinstance(v, dict):
        for k, x in v.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            flatten_obj(x, p, out)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            p = f"{prefix}.{i}" if prefix else str(i)
            flatten_obj(x, p, out)
    else:
        out[prefix] = v
    return out

def unflatten_obj(obj):
    root = {}
    for key, value in obj.items():
        parts = str(key).split(".")
        cur = root
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = value
    return root

def json_path(obj, path: str):
    cur = obj
    for p in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(p)]
        elif isinstance(cur, dict):
            cur = cur.get(p)
        else:
            return None
    return cur

def percentile(sorted_vals, q):
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_vals[lo]
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac

def csv_delimiter_detector(args):
    text = read_text(args[0] if args else None)
    sample = text[:65536]
    try:
        d = csv.Sniffer().sniff(sample, delimiters=",\t;|:")
        delim = d.delimiter
    except csv.Error:
        counts = {x: sample.count(x) for x in [",", "\t", ";", "|", ":"]}
        delim = max(counts, key=counts.get)
    names = {",": "comma", "\t": "tab", ";": "semicolon", "|": "pipe", ":": "colon"}
    write_json({"delimiter": delim, "name": names.get(delim, delim), "count": sample.count(delim)})

def csv_quoting_fixer(args):
    text = read_text(args[0] if args else None)
    fixed = []
    for line in text.splitlines():
        q = 0
        esc = False
        for i, ch in enumerate(line):
            if ch == '"':
                if i + 1 < len(line) and line[i + 1] == '"':
                    esc = not esc
                else:
                    q += 1
        if q % 2:
            line += '"'
        fixed.append(line)
    try:
        rows = list(csv.reader(io.StringIO("\n".join(fixed)), strict=False))
        emit_table(rows, ",")
    except csv.Error:
        sys.stdout.write("\n".join(fixed) + ("\n" if fixed else ""))

def csv_transpose_matrix(args):
    rows = parse_table(read_text(args[0] if args else None), ",")
    emit_table(itertools.zip_longest(*rows, fillvalue=""), ",")

def csv_diff_table_tool(args):
    if len(args) < 2:
        die("usage: csv-diff-table-tool OLD.csv NEW.csv [KEY_COLUMN]")
    a = parse_table(read_text(args[0]), ",")
    b = parse_table(read_text(args[1]), ",")
    if not a or not b:
        write_json({"added": [], "removed": [], "changed": []})
        return
    key_spec = args[2] if len(args) > 2 else a[0][0]
    ia = column_index(a[0], key_spec)
    ib = column_index(b[0], key_spec)
    ma = {r[ia]: r for r in a[1:] if len(r) > ia}
    mb = {r[ib]: r for r in b[1:] if len(r) > ib}
    added = [mb[k] for k in sorted(mb.keys() - ma.keys())]
    removed = [ma[k] for k in sorted(ma.keys() - mb.keys())]
    changed = [{"key": k, "old": ma[k], "new": mb[k]} for k in sorted(ma.keys() & mb.keys()) if ma[k] != mb[k]]
    write_json({"key": key_spec, "added": added, "removed": removed, "changed": changed})

def tsv_aggregate_group_by(args):
    if len(args) < 3:
        die("usage: tsv-aggregate-group-by GROUP_COLUMN VALUE_COLUMN sum|min|max|count [FILE]")
    group_spec, value_spec, op = args[:3]
    rows = parse_table(read_text(args[3] if len(args) > 3 else None), "\t")
    if not rows:
        return
    gi = column_index(rows[0], group_spec)
    vi = column_index(rows[0], value_spec)
    groups = defaultdict(list)
    for r in rows[1:]:
        if len(r) > max(gi, vi):
            groups[r[gi]].append(float(r[vi]))
    out = [["group", op]]
    for k in sorted(groups):
        vals = groups[k]
        val = {"sum": sum, "min": min, "max": max}.get(op, lambda x: len(x))(vals)
        out.append([k, val])
    emit_table(out, "\t")

def tsv_sliding_window_avg(args):
    if len(args) < 2:
        die("usage: tsv-sliding-window-avg COLUMN WINDOW [FILE]")
    rows = parse_table(read_text(args[2] if len(args) > 2 else None), "\t")
    if not rows:
        return
    i = column_index(rows[0], args[0])
    w = max(1, int(args[1]))
    hist = []
    out = [rows[0] + [f"{rows[0][i]}_moving_avg_{w}"]]
    for r in rows[1:]:
        hist.append(float(r[i]))
        cur = hist[-w:]
        out.append(r + [statistics.fmean(cur)])
    emit_table(out, "\t")

def tsv_cumsum_running_tot(args):
    if not args:
        die("usage: tsv-cumsum-running-tot COLUMN [sum|product] [FILE]")
    mode = args[1] if len(args) > 1 and args[1] in ("sum", "product") else "sum"
    file_arg = args[2] if len(args) > 2 else None
    rows = parse_table(read_text(file_arg), "\t")
    if not rows:
        return
    i = column_index(rows[0], args[0])
    acc = 0.0 if mode == "sum" else 1.0
    out = [rows[0] + [f"{mode}_{rows[0][i]}"]]
    for r in rows[1:]:
        x = float(r[i])
        acc = acc + x if mode == "sum" else acc * x
        out.append(r + [acc])
    emit_table(out, "\t")

def tsv_quantile_cut_cli(args):
    if len(args) < 2:
        die("usage: tsv-quantile-cut-cli COLUMN BINS [FILE]")
    rows = parse_table(read_text(args[2] if len(args) > 2 else None), "\t")
    if not rows:
        return
    i = column_index(rows[0], args[0])
    bins = max(2, int(args[1]))
    vals = sorted(float(r[i]) for r in rows[1:] if len(r) > i)
    edges = [percentile(vals, j / bins) for j in range(1, bins)]
    out = [rows[0] + ["quantile_bin"]]
    for r in rows[1:]:
        x = float(r[i])
        b = 1 + sum(x > e for e in edges)
        out.append(r + [b])
    emit_table(out, "\t")

def json_lines_flatten_tool(args):
    for line in read_text(args[0] if args else None).splitlines():
        if line.strip():
            print(json.dumps(flatten_obj(json.loads(line)), ensure_ascii=False, separators=(",", ":")))

def json_lines_unflatten(args):
    for line in read_text(args[0] if args else None).splitlines():
        if line.strip():
            print(json.dumps(unflatten_obj(json.loads(line)), ensure_ascii=False, separators=(",", ":")))

def ndjson_filter_jq_lite(args):
    if len(args) < 2:
        die("usage: ndjson-filter-jq-lite FIELD OP [VALUE] [FILE]")
    field, op = args[:2]
    value = scalar(args[2]) if len(args) > 2 and op not in ("exists", "missing") else None
    file_arg = args[3] if len(args) > 3 else None
    for line in read_text(file_arg).splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        got = json_path(obj, field)
        ok = False
        if op == "exists":
            ok = got is not None
        elif op == "missing":
            ok = got is None
        elif op == "==":
            ok = got == value
        elif op == "!=":
            ok = got != value
        elif op == ">":
            ok = got is not None and got > value
        elif op == ">=":
            ok = got is not None and got >= value
        elif op == "<":
            ok = got is not None and got < value
        elif op == "<=":
            ok = got is not None and got <= value
        elif op == "contains":
            ok = str(value) in str(got)
        elif op == "regex":
            ok = re.search(str(value), str(got or "")) is not None
        else:
            die(f"unknown operator: {op}")
        if ok:
            print(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))

def ndjson_sort_by_key(args):
    if not args:
        die("usage: ndjson-sort-by-key FIELD [FILE]")
    field = args[0]
    objs = [json.loads(x) for x in read_text(args[1] if len(args) > 1 else None).splitlines() if x.strip()]
    objs.sort(key=lambda o: (json_path(o, field) is None, json_path(o, field)))
    for obj in objs:
        print(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))

def log_regex_named_captures(args):
    if not args:
        die("usage: log-regex-named-captures REGEX [FILE]")
    rx = re.compile(args[0])
    for line in read_text(args[1] if len(args) > 1 else None).splitlines():
        m = rx.search(line)
        if m:
            print(json.dumps(m.groupdict() or {"groups": list(m.groups())}, ensure_ascii=False))

def grok_to_regex(pattern: str):
    token = re.compile(r"%\{([A-Z0-9_]+)(?::([A-Za-z_][A-Za-z0-9_]*))?\}")
    pos = 0
    parts = []
    for m in token.finditer(pattern):
        parts.append(re.escape(pattern[pos:m.start()]))
        base = GROK.get(m.group(1))
        if base is None:
            die(f"unknown grok pattern: {m.group(1)}")
        parts.append(f"(?P<{m.group(2)}>{base})" if m.group(2) else f"(?:{base})")
        pos = m.end()
    parts.append(re.escape(pattern[pos:]))
    return "".join(parts)

def grok_pattern_parser(args):
    if not args:
        die("usage: grok-pattern-parser GROK_PATTERN [FILE]")
    rx = re.compile("^" + grok_to_regex(args[0]) + "$")
    for line in read_text(args[1] if len(args) > 1 else None).splitlines():
        m = rx.match(line)
        if m:
            print(json.dumps(m.groupdict(), ensure_ascii=False))

def parse_request(req):
    parts = req.split()
    return {
        "method": parts[0] if len(parts) > 0 else None,
        "path": parts[1] if len(parts) > 1 else None,
        "protocol": parts[2] if len(parts) > 2 else None,
    }

def clf_apache_log_parser(args):
    for line in read_text(args[0] if args else None).splitlines():
        m = CLF_RE.match(line)
        if not m:
            continue
        d = m.groupdict()
        d.update(parse_request(d.pop("request")))
        d["status"] = int(d["status"]) if d["status"].isdigit() else None
        d["size"] = int(d["size"]) if d["size"].isdigit() else None
        print(json.dumps(d, ensure_ascii=False))

def combined_log_formatter(args):
    for line in read_text(args[0] if args else None).splitlines():
        m = COMBINED_RE.match(line)
        if not m:
            continue
        d = m.groupdict()
        d.update(parse_request(d.pop("request")))
        d["status"] = int(d["status"]) if d["status"].isdigit() else None
        d["size"] = int(d["size"]) if d["size"].isdigit() else None
        print(json.dumps(d, ensure_ascii=False))

def nginx_access_log_parser(args):
    if not args:
        die("usage: nginx-access-log-parser FORMAT [FILE]")
    fmt = args[0]
    vars_rx = {
        "remote_addr": r"\S+",
        "remote_user": r"\S+",
        "time_local": r"[^]]+",
        "request": r'[^"]*',
        "status": r"\d{3}",
        "body_bytes_sent": r"\d+|-",
        "http_referer": r'[^"]*',
        "http_user_agent": r'[^"]*',
        "request_time": r"[0-9.]+",
        "host": r"\S+",
    }
    pattern = ""
    names = []
    i = 0
    for m in re.finditer(r"\$([A-Za-z0-9_]+)", fmt):
        pattern += re.escape(fmt[i:m.start()])
        name = m.group(1)
        names.append(name)
        pattern += f"(?P<{name}>{vars_rx.get(name, r'.*?')})"
        i = m.end()
    pattern += re.escape(fmt[i:])
    rx = re.compile("^" + pattern + "$")
    for line in read_text(args[1] if len(args) > 1 else None).splitlines():
        m = rx.match(line)
        if m:
            print(json.dumps(m.groupdict(), ensure_ascii=False))

def auth_log_ip_aggregator(args):
    text = read_text(args[0] if args else None)
    ips = re.findall(r"(?:Failed password|Invalid user).*?from\s+([0-9a-fA-F:.]+)", text)
    for ip, n in Counter(ips).most_common():
        print(f"{n}\t{ip}")

def fail2ban_regex_tester(args):
    if not args:
        die("usage: fail2ban-regex-tester REGEX [FILE]")
    pat = args[0].replace("<HOST>", r"(?P<host>(?:\d{1,3}\.){3}\d{1,3}|[0-9A-Fa-f:]+)")
    rx = re.compile(pat)
    matches = []
    lines = read_text(args[1] if len(args) > 1 else None).splitlines()
    for idx, line in enumerate(lines, 1):
        m = rx.search(line)
        if m:
            matches.append({"line": idx, "text": line, "groups": m.groupdict()})
    write_json({"tested": len(lines), "matched": len(matches), "matches": matches})

def tsv_pivot_table_gen(args):
    if len(args) < 3:
        die("usage: tsv-pivot-table-gen ROW_FIELD COLUMN_FIELD VALUE_FIELD [sum|count] [FILE]")
    rows = parse_table(read_text(args[4] if len(args) > 4 else None), "\t")
    if not rows:
        return
    ri = column_index(rows[0], args[0])
    ci = column_index(rows[0], args[1])
    vi = column_index(rows[0], args[2])
    op = args[3] if len(args) > 3 and args[3] in ("sum", "count") else "sum"
    rkeys = sorted({r[ri] for r in rows[1:]})
    ckeys = sorted({r[ci] for r in rows[1:]})
    agg = defaultdict(float)
    for r in rows[1:]:
        agg[(r[ri], r[ci])] += 1.0 if op == "count" else float(r[vi])
    out = [[args[0]] + ckeys]
    for rk in rkeys:
        out.append([rk] + [agg[(rk, ck)] for ck in ckeys])
    emit_table(out, "\t")

def tsv_unpivot_melt_tool(args):
    if not args:
        die("usage: tsv-unpivot-melt-tool ID_COLUMN[,ID_COLUMN...] [FILE]")
    rows = parse_table(read_text(args[1] if len(args) > 1 else None), "\t")
    if not rows:
        return
    ids = args[0].split(",")
    id_idx = [column_index(rows[0], x) for x in ids]
    value_idx = [i for i in range(len(rows[0])) if i not in id_idx]
    out = [ids + ["variable", "value"]]
    for r in rows[1:]:
        idvals = [r[i] for i in id_idx]
        for i in value_idx:
            out.append(idvals + [rows[0][i], r[i]])
    emit_table(out, "\t")

def stream_sample_reservoir(args):
    if not args:
        die("usage: stream-sample-reservoir K [SEED] [FILE]")
    k = max(0, int(args[0]))
    seed = int(args[1]) if len(args) > 1 and re.fullmatch(r"-?\d+", args[1]) else None
    file_arg = args[2] if seed is not None and len(args) > 2 else (args[1] if len(args) > 1 and seed is None else None)
    rng = random.Random(seed)
    sample = []
    for i, line in enumerate(read_text(file_arg).splitlines(), 1):
        if len(sample) < k:
            sample.append(line)
        else:
            j = rng.randrange(i)
            if j < k:
                sample[j] = line
    sys.stdout.write("\n".join(sample) + ("\n" if sample else ""))

def leading_zero_bits(x, width=64):
    if x == 0:
        return width
    return width - x.bit_length()

def stream_distinct_hyperlog(args):
    p = int(args[0]) if args and re.fullmatch(r"\d+", args[0]) else 12
    file_arg = args[1] if args and re.fullmatch(r"\d+", args[0]) and len(args) > 1 else (args[0] if args and not re.fullmatch(r"\d+", args[0]) else None)
    if not 4 <= p <= 16:
        die("precision p must be 4..16")
    m = 1 << p
    regs = [0] * m
    for line in read_text(file_arg).splitlines():
        h = int.from_bytes(hashlib.sha256(line.encode()).digest()[:8], "big")
        idx = h & (m - 1)
        w = h >> p
        regs[idx] = max(regs[idx], leading_zero_bits(w, 64 - p) + 1)
    alpha = 0.7213 / (1 + 1.079 / m)
    est = alpha * m * m / sum(2.0 ** (-r) for r in regs)
    zeros = regs.count(0)
    if est <= 2.5 * m and zeros:
        est = m * math.log(m / zeros)
    write_json({"precision": p, "registers": m, "estimate": est})

def stream_moving_average(args):
    if not args:
        die("usage: stream-moving-average WINDOW [FILE]")
    w = max(1, int(args[0]))
    hist = []
    for line in read_text(args[1] if len(args) > 1 else None).splitlines():
        if not line.strip():
            continue
        hist.append(float(line))
        if len(hist) > w:
            hist.pop(0)
        print(statistics.fmean(hist))

def stream_exponential_decay(args):
    if not args:
        die("usage: stream-exponential-decay ALPHA|half-life=SECONDS [FILE]")
    spec = args[0]
    alpha = 1 - math.exp(math.log(0.5) / float(spec.split("=", 1)[1])) if spec.startswith("half-life=") else float(spec)
    if not 0 < alpha <= 1:
        die("alpha must be >0 and <=1")
    ema = None
    for line in read_text(args[1] if len(args) > 1 else None).splitlines():
        if not line.strip():
            continue
        x = float(line)
        ema = x if ema is None else alpha * x + (1 - alpha) * ema
        print(ema)

def stream_rate_throttle_cli(args):
    if not args:
        die("usage: stream-rate-throttle-cli LINES_PER_SECOND [FILE]")
    rate = float(args[0])
    if rate <= 0:
        die("rate must be positive")
    delay = 1.0 / rate
    first = True
    for line in read_text(args[1] if len(args) > 1 else None).splitlines(True):
        if not first:
            time.sleep(delay)
        first = False
        sys.stdout.write(line)
        sys.stdout.flush()

def stream_chunk_byte_split(args):
    if not args:
        die("usage: stream-chunk-byte-split BYTES [FILE]")
    size = max(1, int(args[0]))
    data = read_bytes(args[1] if len(args) > 1 else None)
    for i in range(0, len(data), size):
        chunk = data[i:i + size]
        print(json.dumps({"index": i // size, "size": len(chunk), "base64": base64.b64encode(chunk).decode()}))

def stream_checksum_hasher(args):
    algo = args[0] if args and args[0] in hashlib.algorithms_available else "sha256"
    file_arg = args[1] if args and args[0] in hashlib.algorithms_available and len(args) > 1 else (args[0] if args and args[0] not in hashlib.algorithms_available else None)
    data = read_bytes(file_arg)
    h = hashlib.new(algo, data)
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()
    print(f"\n{algo}:{h.hexdigest()}", file=sys.stderr)

def xor_indexes(item: bytes, bits: int):
    d = hashlib.blake2b(item, digest_size=24).digest()
    return [int.from_bytes(d[i:i + 8], "big") % bits for i in (0, 8, 16)]

def stream_xor_filter_cli(args):
    if not args or args[0] not in ("build", "query"):
        die("usage: stream-xor-filter-cli build BITS [FILE] | query FILTER_HEX ITEM")
    if args[0] == "build":
        bits = int(args[1])
        arr = bytearray((bits + 7) // 8)
        for line in read_text(args[2] if len(args) > 2 else None).splitlines():
            for idx in xor_indexes(line.encode(), bits):
                arr[idx // 8] ^= 1 << (idx % 8)
        write_json({"bits": bits, "filter_hex": arr.hex()})
    else:
        raw = bytes.fromhex(args[1])
        bits = len(raw) * 8
        item = args[2]
        vals = [bool(raw[idx // 8] & (1 << (idx % 8))) for idx in xor_indexes(item.encode(), bits)]
        write_json({"item": item, "maybe_present": sum(vals) >= 2, "probes": vals})

def byte_frequency_analysis(args):
    c = Counter(read_bytes(args[0] if args else None))
    for b in range(256):
        print(f"{b:02x}\t{c.get(b, 0)}")

def file_dedup_block_hasher(args):
    if not args:
        die("usage: file-dedup-block-hasher FILE [BLOCK_SIZE]")
    size = int(args[1]) if len(args) > 1 else 4096
    data = read_bytes(args[0])
    groups = defaultdict(list)
    for off in range(0, len(data), size):
        block = data[off:off + size]
        groups[hashlib.sha256(block).hexdigest()].append(off)
    write_json([{"sha256": h, "offsets": offs, "count": len(offs)} for h, offs in groups.items() if len(offs) > 1])

def rolling_checksum_fast(args):
    window = int(args[0]) if args and re.fullmatch(r"\d+", args[0]) else 64
    file_arg = args[1] if args and re.fullmatch(r"\d+", args[0]) and len(args) > 1 else (args[0] if args and not re.fullmatch(r"\d+", args[0]) else None)
    data = read_bytes(file_arg)
    mod = 2**32 - 5
    base = 257
    if len(data) < window:
        print(sum(data) % mod)
        return
    power = pow(base, window - 1, mod)
    h = 0
    for b in data[:window]:
        h = (h * base + b) % mod
    print(f"0\t{h}")
    for i in range(window, len(data)):
        h = ((h - data[i - window] * power) * base + data[i]) % mod
        print(f"{i - window + 1}\t{h}")

def run_length_encoder_cli(args):
    data = read_bytes(args[0] if args else None)
    out = bytearray(b"ORLE1")
    if data:
        cur = data[0]
        count = 1
        for b in data[1:]:
            if b == cur and count < 255:
                count += 1
            else:
                out += bytes((count, cur))
                cur, count = b, 1
        out += bytes((count, cur))
    sys.stdout.buffer.write(out)

def run_length_decoder_cli(args):
    data = read_bytes(args[0] if args else None)
    if not data.startswith(b"ORLE1") or (len(data) - 5) % 2:
        die("invalid ORLE1 stream")
    out = bytearray()
    for i in range(5, len(data), 2):
        out.extend(bytes([data[i + 1]]) * data[i])
    sys.stdout.buffer.write(out)

def delta_encoding_tool(args):
    if not args:
        die("usage: delta-encoding-tool encode|decode [FILE]")
    vals = [float(x) for x in re.split(r"[\s,]+", read_text(args[1] if len(args) > 1 else None).strip()) if x]
    out = []
    if args[0] == "encode":
        prev = 0.0
        for i, x in enumerate(vals):
            out.append(x if i == 0 else x - prev)
            prev = x
    elif args[0] == "decode":
        acc = 0.0
        for i, x in enumerate(vals):
            acc = x if i == 0 else acc + x
            out.append(acc)
    else:
        die("mode must be encode or decode")
    print(" ".join(str(int(x)) if x.is_integer() else str(x) for x in out))

def zigzag_encoding_cli(args):
    if len(args) < 2:
        die("usage: zigzag-encoding-cli encode|decode INTEGER...")
    if args[0] == "encode":
        vals = [int(x) for x in args[1:]]
        out = [(n << 1) ^ (n >> 63) for n in vals]
    elif args[0] == "decode":
        vals = [int(x) for x in args[1:]]
        out = [(n >> 1) ^ -(n & 1) for n in vals]
    else:
        die("mode must be encode or decode")
    print(" ".join(map(str, out)))

def leb128_encode(n: int):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)

def leb128_decode(data: bytes):
    vals = []
    value = shift = 0
    for b in data:
        value |= (b & 0x7F) << shift
        if b & 0x80:
            shift += 7
            if shift > 63:
                die("LEB128 integer too large")
        else:
            vals.append(value)
            value = shift = 0
    if shift:
        die("truncated LEB128 input")
    return vals

def variable_byte_encoder(args):
    if not args:
        die("usage: variable-byte-encoder encode INTEGER... | decode HEX")
    if args[0] == "encode":
        sys.stdout.write(b"".join(leb128_encode(int(x)) for x in args[1:]).hex() + "\n")
    elif args[0] == "decode":
        print(" ".join(map(str, leb128_decode(bytes.fromhex(args[1])))))
    else:
        die("mode must be encode or decode")

def bit_packing_unpacker(args):
    if len(args) < 2:
        die("usage: bit-packing-unpacker pack BITS INTEGER... | unpack BITS HEX")
    mode, bits_s = args[:2]
    bits = int(bits_s)
    if not 1 <= bits <= 32:
        die("BITS must be 1..32")
    if mode == "pack":
        values = [int(x) for x in args[2:]]
        acc = acc_bits = 0
        out = bytearray()
        mask = (1 << bits) - 1
        for v in values:
            if v < 0 or v > mask:
                die(f"value {v} does not fit in {bits} bits")
            acc |= v << acc_bits
            acc_bits += bits
            while acc_bits >= 8:
                out.append(acc & 0xFF)
                acc >>= 8
                acc_bits -= 8
        if acc_bits:
            out.append(acc & 0xFF)
        print(out.hex())
    elif mode == "unpack":
        data = bytes.fromhex(args[2])
        count = int(args[3]) if len(args) > 3 else (len(data) * 8) // bits
        acc = acc_bits = pos = 0
        out = []
        for _ in range(count):
            while acc_bits < bits:
                if pos >= len(data):
                    die("not enough packed bytes")
                acc |= data[pos] << acc_bits
                acc_bits += 8
                pos += 1
            out.append(acc & ((1 << bits) - 1))
            acc >>= bits
            acc_bits -= bits
        print(" ".join(map(str, out)))
    else:
        die("mode must be pack or unpack")

def column_to_row_transposer(args):
    rows = parse_table(read_text(args[0] if args else None), ",")
    vals = [r[0] for r in rows if r]
    emit_table([vals], ",")

def row_to_column_pack_cli(args):
    objs = [json.loads(x) for x in read_text(args[0] if args else None).splitlines() if x.strip()]
    keys = sorted({k for o in objs if isinstance(o, dict) for k in o})
    write_json({k: [o.get(k) for o in objs] for k in keys})

def data_masking_pseudonym(args):
    if not args:
        die("usage: data-masking-pseudonym SECRET [FILE]")
    secret = args[0].encode()
    for line in read_text(args[1] if len(args) > 1 else None).splitlines():
        digest = hmac.new(secret, line.encode(), hashlib.sha256).hexdigest()
        print(digest[:24])

def pii_regex_scrubber_cli(args):
    text = read_text(args[0] if args else None)
    text = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[EMAIL]", text, flags=re.I)
    text = re.sub(r"(?<!\w)(?:\+?\d[\d .()-]{7,}\d)(?!\w)", "[PHONE]", text)
    text = re.sub(r"\b(?:\d[ -]*?){13,19}\b", "[CARDLIKE]", text)
    sys.stdout.write(text)

def luhn_ok(raw: str):
    digits = [int(c) for c in re.sub(r"\D", "", raw)]
    if not 12 <= len(digits) <= 19:
        return False
    total = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0

def credit_card_luhn_chk(args):
    if not args:
        die("usage: credit-card-luhn-chk NUMBER")
    write_json({"valid": luhn_ok(args[0]), "digits": len(re.sub(r'\D', '', args[0]))})

def iban_validator_cli_tool(args):
    if not args:
        die("usage: iban-validator-cli-tool IBAN")
    iban = re.sub(r"\s+", "", args[0]).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", iban):
        write_json({"valid": False, "iban": iban})
        return
    rearranged = iban[4:] + iban[:4]
    num = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    rem = 0
    for ch in num:
        rem = (rem * 10 + int(ch)) % 97
    write_json({"valid": rem == 1, "iban": iban, "mod97": rem})

def uuid_v1_timestamp_view(args):
    if not args:
        die("usage: uuid-v1-timestamp-view UUID")
    u = uuid.UUID(args[0])
    if u.version != 1:
        die("UUID is not version 1")
    gregorian_offset_100ns = 0x01B21DD213814000
    unix_100ns = u.time - gregorian_offset_100ns
    ts = unix_100ns / 10_000_000
    write_json({"uuid": str(u), "timestamp_unix": ts, "timestamp_utc": dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()})

def uuid_v4_entropy_tester(args):
    if not args:
        die("usage: uuid-v4-entropy-tester UUID [UUID...]")
    rows = []
    for s in args:
        try:
            u = uuid.UUID(s)
            raw = u.bytes
            rows.append({
                "uuid": str(u),
                "version4": u.version == 4,
                "rfc4122_variant": u.variant == uuid.RFC_4122,
                "variant_bits": (raw[8] >> 6) & 0b11,
                "version_bits": (raw[6] >> 4) & 0xF,
            })
        except ValueError:
            rows.append({"uuid": s, "valid": False})
    write_json(rows)

def uuid_v5_name_hasher(args):
    if len(args) < 2:
        die("usage: uuid-v5-name-hasher dns|url|oid|x500|UUID NAME")
    nsmap = {"dns": uuid.NAMESPACE_DNS, "url": uuid.NAMESPACE_URL, "oid": uuid.NAMESPACE_OID, "x500": uuid.NAMESPACE_X500}
    ns = nsmap.get(args[0].lower())
    if ns is None:
        ns = uuid.UUID(args[0])
    print(uuid.uuid5(ns, args[1]))

def uuid7_now():
    ms = int(time.time() * 1000)
    rand = int.from_bytes(os.urandom(10), "big")
    value = ((ms & ((1 << 48) - 1)) << 80) | (0x7 << 76) | ((rand >> 68) & 0xFFF) << 64 | (0b10 << 62) | (rand & ((1 << 62) - 1))
    return uuid.UUID(int=value)

def uuid_v7_sortable_maker(args):
    count = int(args[0]) if args else 1
    for _ in range(count):
        print(uuid7_now())

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
def ulid_decode_timestamp(s: str):
    s = s.strip().upper()
    if len(s) != 26 or any(c not in CROCKFORD for c in s):
        die("invalid ULID")
    n = 0
    for c in s[:10]:
        n = n * 32 + CROCKFORD.index(c)
    return n

def ulid_timestamp_extractor(args):
    if not args:
        die("usage: ulid-timestamp-extractor ULID")
    ms = ulid_decode_timestamp(args[0])
    write_json({"unix_ms": ms, "utc": dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat()})

def nanoid_collision_calc(args):
    if len(args) < 3:
        die("usage: nanoid-collision-calc ALPHABET_SIZE ID_LENGTH GENERATED_IDS")
    a, l, n = int(args[0]), int(args[1]), float(args[2])
    if a < 2 or l < 1 or n < 0:
        die("invalid parameters")
    space = a ** l
    exponent = -(n * (n - 1)) / (2 * space)
    p = 1 - math.exp(exponent) if exponent > -745 else 1.0
    write_json({"alphabet_size": a, "length": l, "space": str(space), "generated_ids": n, "collision_probability": p})

COMMANDS = {
    "csv-delimiter-detector": csv_delimiter_detector,
    "csv-quoting-fixer": csv_quoting_fixer,
    "csv-transpose-matrix": csv_transpose_matrix,
    "csv-diff-table-tool": csv_diff_table_tool,
    "tsv-aggregate-group-by": tsv_aggregate_group_by,
    "tsv-sliding-window-avg": tsv_sliding_window_avg,
    "tsv-cumsum-running-tot": tsv_cumsum_running_tot,
    "tsv-quantile-cut-cli": tsv_quantile_cut_cli,
    "json-lines-flatten-tool": json_lines_flatten_tool,
    "json-lines-unflatten": json_lines_unflatten,
    "ndjson-filter-jq-lite": ndjson_filter_jq_lite,
    "ndjson-sort-by-key": ndjson_sort_by_key,
    "log-regex-named-captures": log_regex_named_captures,
    "grok-pattern-parser": grok_pattern_parser,
    "clf-apache-log-parser": clf_apache_log_parser,
    "combined-log-formatter": combined_log_formatter,
    "nginx-access-log-parser": nginx_access_log_parser,
    "auth-log-ip-aggregator": auth_log_ip_aggregator,
    "fail2ban-regex-tester": fail2ban_regex_tester,
    "tsv-pivot-table-gen": tsv_pivot_table_gen,
    "tsv-unpivot-melt-tool": tsv_unpivot_melt_tool,
    "stream-sample-reservoir": stream_sample_reservoir,
    "stream-distinct-hyperlog": stream_distinct_hyperlog,
    "stream-moving-average": stream_moving_average,
    "stream-exponential-decay": stream_exponential_decay,
    "stream-rate-throttle-cli": stream_rate_throttle_cli,
    "stream-chunk-byte-split": stream_chunk_byte_split,
    "stream-checksum-hasher": stream_checksum_hasher,
    "stream-xor-filter-cli": stream_xor_filter_cli,
    "byte-frequency-analysis": byte_frequency_analysis,
    "file-dedup-block-hasher": file_dedup_block_hasher,
    "rolling-checksum-fast": rolling_checksum_fast,
    "run-length-encoder-cli": run_length_encoder_cli,
    "run-length-decoder-cli": run_length_decoder_cli,
    "delta-encoding-tool": delta_encoding_tool,
    "zigzag-encoding-cli": zigzag_encoding_cli,
    "variable-byte-encoder": variable_byte_encoder,
    "bit-packing-unpacker": bit_packing_unpacker,
    "column-to-row-transposer": column_to_row_transposer,
    "row-to-column-pack-cli": row_to_column_pack_cli,
    "data-masking-pseudonym": data_masking_pseudonym,
    "pii-regex-scrubber-cli": pii_regex_scrubber_cli,
    "credit-card-luhn-chk": credit_card_luhn_chk,
    "iban-validator-cli-tool": iban_validator_cli_tool,
    "uuid-v1-timestamp-view": uuid_v1_timestamp_view,
    "uuid-v4-entropy-tester": uuid_v4_entropy_tester,
    "uuid-v5-name-hasher": uuid_v5_name_hasher,
    "uuid-v7-sortable-maker": uuid_v7_sortable_maker,
    "ulid-timestamp-extractor": ulid_timestamp_extractor,
    "nanoid-collision-calc": nanoid_collision_calc,
}

def main():
    if len(COMMANDS) != 50:
        die(f"internal command count mismatch: {len(COMMANDS)}")
    prog = Path(sys.argv[0]).name
    if prog in COMMANDS:
        cmd = prog
        args = sys.argv[1:]
    else:
        if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
            print("OceanStudio functional shard 27 runtime")
            print("Commands:")
            for name in sorted(COMMANDS):
                print(" ", name)
            return
        if sys.argv[1] in ("-v", "--version"):
            print(VERSION)
            return
        cmd = sys.argv[1]
        args = sys.argv[2:]
    if cmd not in COMMANDS:
        die(f"unknown command: {cmd}")
    COMMANDS[cmd](args)

if __name__ == "__main__":
    main()
