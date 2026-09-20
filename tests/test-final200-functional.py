#!/usr/bin/env python3
import importlib.util,sys,tempfile,sqlite3,struct,zlib,binascii,json,hashlib
from pathlib import Path
def load(p,n):
    s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
r12=load(Path(sys.argv[1]),"r12");r14=load(Path(sys.argv[2]),"r14");r20=load(Path(sys.argv[3]),"r20");r23=load(Path(sys.argv[4]),"r23")
b2=load(Path(sys.argv[5]),"b2");b3=load(Path(sys.argv[6]),"b3");b4=load(Path(sys.argv[7]),"b4")
expected={
 "12":{x[0] for x in b2.BATCH2_SHARDS["shard-12-database-query-engines"]["packages"]},
 "14":{x[0] for x in b2.BATCH2_SHARDS["shard-14-image-media-audio"]["packages"]},
 "20":{x[0] for x in b3.BATCH3_SHARDS["shard-20-security-audit-forensics"]["packages"]},
 "23":{x[0] for x in b4.BATCH4_SHARDS["shard-23-distributed-consensus-p2p"]["packages"]},
}
for n,r in [("12",r12),("14",r14),("20",r20),("23",r23)]:
    assert len(expected[n])==50
    assert set(r.COMMANDS)==expected[n],(n,sorted(expected[n]-set(r.COMMANDS)),sorted(set(r.COMMANDS)-expected[n]))
    assert all(callable(r.COMMANDS[x]) for x in expected[n])
assert len(set().union(*expected.values()))==200

with tempfile.TemporaryDirectory() as td:
    p=Path(td)
    # Database fixtures.
    db=p/"t.db";c=sqlite3.connect(db);c.executescript("PRAGMA foreign_keys=ON; CREATE TABLE parent(id INTEGER PRIMARY KEY,name TEXT); CREATE TABLE child(id INTEGER PRIMARY KEY,parent_id INTEGER REFERENCES parent(id),payload BLOB); INSERT INTO parent VALUES(1,'ocean'); INSERT INTO child VALUES(1,1,X'4142'); CREATE INDEX idx_child_parent ON child(parent_id);");c.commit();c.close()
    for cmd,args in [
        ("sqlite-b-tree-inspector",[str(db)]),("sqlite-page-analyzer",[str(db)]),("sqlite-vacuum-analyze",[str(db)]),
        ("sqlite-pragma-dump",[str(db)]),("sqlite-table-sizes",[str(db)]),("sqlite-index-recommend",[str(db),"SELECT * FROM child WHERE parent_id=1"]),
        ("db-foreign-key-chk",[str(db)]),("db-constraint-audit",[str(db)]),("db-schema-snapshot",["CREATE TABLE x(id INT);"]),
        ("sql-syntax-formatter",["SELECT a FROM t WHERE a=1"]),("sql-ast-visualizer",["SELECT a FROM t"]),("sql-injection-tester",["SELECT * FROM t WHERE id=?"]),
        ("db-migration-history",["1","2","4"]),("db-seed-data-gen",["2","id:int","name:str"]),("vector-embedding-index",["1,0","0.5,0.5"]),
        ("hnsw-distance-calc",["1,0","1,1"]),("influxdb-line-protocol",["cpu,host=x usage=1.2 10"]),("timescaledb-hypertable",["0","3600","600"])
    ]: r12.COMMANDS[cmd](args)
    rdb=p/"dump.rdb";rdb.write_bytes(b"REDIS0009"+b"\xff");r12.COMMANDS["redis-rdb-parser"]([str(rdb)])
    par=p/"x.parquet";par.write_bytes(b"PAR1"+b"\0"*8+(0).to_bytes(4,"little")+b"PAR1");r12.COMMANDS["parquet-metadata-dump"]([str(par)])

    # PNG and common media fixtures.
    def chunk(t,d):
        return len(d).to_bytes(4,"big")+t+d+(binascii.crc32(t+d)&0xffffffff).to_bytes(4,"big")
    raw=b"\x00\xff\x00\x00";png=b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",1,1,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(raw))+chunk(b"IEND",b"")
    pf=p/"x.png";pf.write_bytes(png)
    for cmd in ["png-chunk-parser","png-ihdr-analyzer","png-crush-optimizer","image-dimension-probe","histogram-image-cli"]:r14.COMMANDS[cmd]([str(pf)])
    svg=p/"x.svg";svg.write_text('<svg width="10" height="20" xmlns="http://www.w3.org/2000/svg"><script>x</script><path d="M 1.23456 2.34567"/></svg>')
    for cmd in ["svg-path-optimizer","svg-viewbox-fixer","svg-xml-sanitizer"]:r14.COMMANDS[cmd]([str(svg)])
    for cmd,args in [
        ("color-hex-rgb-hsl",["#336699"]),("color-palette-generator",["#336699"]),("color-contrast-wcag",["#000000","#ffffff"]),
        ("pixel-aspect-ratio",["1920","1080","1","1"]),("audio-duration-calc",["176400","44100","2","16"]),
        ("audio-bitrate-sampler",["128","192","256"]),("yuv-frame-calculator",["1920","1080","420"]),
        ("video-fps-timecode",["60","30"]),("dpi-calculator-cli",["1920","1080","20","11.25"]),
        ("aspect-ratio-reducer",["1920","1080"]),("color-temperature-calc",["6500"]),("bayer-pattern-matrix",["RGGB"])
    ]:r14.COMMANDS[cmd](args)

    # Defensive forensic fixtures; all offline/static.
    mem=p/"mem.bin";mem.write_bytes(b"A"*80+b"/bin/sh\0"+b"\0"*128+b"UPX!\0")
    for cmd in ["raw-memory-string-dump","mem-injection-scanner","code-cave-finder-elf","binary-entropy-graph","packed-executable-chk","upx-header-unpacker","fuzzy-ssdeep-hasher","fuzzy-tlsh-calculator"]:r20.COMMANDS[cmd]([str(mem)])
    for cmd,args in [
        ("page-table-walk-tool",["0x12345","12"]),("ptrace-anti-debug-chk",["ptrace(PTRACE_TRACEME)"]),
        ("threat-intel-ip-parser",["bad 192.0.2.1 and 10.0.0.1"]),("snort-rule-validator",["alert tcp any any -> any 80 (msg:test;)"]),
        ("sigma-rule-converter",["title: X\ndetection:\n  condition: test\n"]),("syslog-auth-failure",["Failed password for x from 192.0.2.2"]),
        ("pam-auth-audit-trail",["authentication failure\nsession opened"]),("sudoers-file-validator",["user ALL=(ALL) NOPASSWD: ALL"]),
        ("shadow-password-audit",["u:$6$abc:1:2:3:4:5:6:7"]),("ssh-authorized-keys-chk",["no-pty ssh-ed25519 AAAA test"]),
        ("ssh-known-hosts-hash",["example.com ssh-ed25519 AAAA"]),("ssl-tls-poodle-tester",["TLS1.2 AES_GCM"]),
        ("heartbleed-probe-cli",["TLS1.2 no-heartbeat"]),("shellshock-cve-tester",["x=plain"]),
        ("dirty-cow-probe-chk",["6.1.0"]),("dmesg-taint-explainer",["0"])
    ]:r20.COMMANDS[cmd](args)
    stix=p/"i.json";stix.write_text(json.dumps({"type":"bundle","objects":[{"type":"indicator"},{"type":"indicator"}]}));r20.COMMANDS["ioc-stix-json-parser"]([str(stix)])

    # Distributed systems fixtures.
    for cmd,args in [
        ("raft-vote-simulator",["3","2","2:true","2:true"]),("paxos-ballot-calculator",["4","2"]),
        ("gossip-cluster-ping",["a","b","c","d"]),("swim-membership-check",["1","3","0.1"]),
        ("kademlia-distance-xor",["01","0f"]),("dht-kademlia-routing",["0f","01","02","ff"]),
        ("dht-bucket-balancer",["2","a","b","c"]),("merkle-tree-hasher",["a","b","c"]),
        ("merkle-proof-generator",["1","a","b","c"]),("merkle-mountain-range",["a","b","c"]),
        ("sparse-merkle-tree",["key","value"]),("vector-clock-comparator",['{"a":1}','{"a":2}']),
        ("lamport-timestamp-calc",["4","8"]),("crdt-g-counter-cli",['{"a":2}','{"a":3,"b":1}']),
        ("crdt-pn-counter-tool",['{"p":{"a":3},"n":{"a":1}}']),("crdt-lww-register",['{"value":"x","ts":1,"node":"a"}','{"value":"y","ts":2,"node":"b"}']),
        ("crdt-or-set-resolver",['{"adds":{"x":["t1"]},"removes":[]}']),("bloom-filter-hasher",["1000","0.01"]),
        ("counting-bloom-filter",["128","a","b","a"]),("cuckoo-filter-cli",["100","a","b"]),
        ("hyperloglog-cardinality",["a","b","c"]),("count-min-sketch-calc",["64","a","a","b"]),
        ("consistent-hash-ring",["key","n1","n2"]),("rendezvous-hash-eval",["key","n1","n2"]),
        ("virtual-node-balancer",["8","n1","n2"]),("magnet-link-builder",["0123456789abcdef","Ocean"]),
        ("libp2p-multiaddr-parse",["/ip4/127.0.0.1/tcp/4001/p2p/QmPeer"]),("noise-protocol-handshake",["XX"]),
        ("gossipsub-topic-filter",["topic","5"]),("quic-congestion-cubic",["10","20","1"]),
        ("bbr-bandwidth-estimator",["10","12","0.05"]),("replicated-state-sync",["1,2,3","2,3,4"]),
        ("quorum-majority-calc",["5"]),("split-brain-detector",["5","2","3"]),
        ("byzantine-fault-ratio",["7"]),("epoch-watermark-tracker",["10","12","11"]),
        ("distributed-trace-span",["0123456789abcdef0123456789abcdef","0123456789abcdef"]),
        ("w3c-trace-context-parse",["00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"]),
        ("b3-trace-header-inject",["0123456789abcdef","0123456789abcdef"]),
        ("rate-limiter-token-bucket",["10","5","2","1","3"]),("leaky-bucket-algorithm",["10","5","2","1","3"])
    ]:r23.COMMANDS[cmd](args)

print("PASS: exact 200-command manifest match; all four runtimes compile; cross-domain functional fixtures passed")
