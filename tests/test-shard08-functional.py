#!/usr/bin/env python3
import importlib.util,struct,tempfile,sys
from pathlib import Path
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
r=load(Path(sys.argv[1]),"r");b=load(Path(sys.argv[2]),"b")
names={x[0] for x in b.BATCH1_SHARDS["shard-08-network-traffic-sockets"]["packages"]}
assert set(r.COMMANDS)==names and len(names)==50 and all(callable(r.COMMANDS[x]) for x in names)
with tempfile.TemporaryDirectory() as td:
 p=Path(td)
 gh=bytes.fromhex("d4c3b2a1020004000000000000000000ffff000001000000")
 ph=struct.pack("<IIII",1,2,4,4);(p/"a.pcap").write_bytes(gh+ph+b"test")
 r.COMMANDS["pcap-header-analyzer"]([str(p/"a.pcap")])
 r.COMMANDS["packet-payload-dissector"](["414243"])
 r.COMMANDS["ethernet-frame-parser"](["00112233445566778899aabb0800"])
 ip=bytearray(20);ip[0]=0x45;ip[2:4]=(20).to_bytes(2,"big");ip[8]=64;ip[9]=6;ip[12:16]=b"\x7f\0\0\1";ip[16:20]=b"\x7f\0\0\1";ip[10:12]=r.checksum16(bytes(ip)).to_bytes(2,"big")
 r.COMMANDS["ipv4-header-checker"]([bytes(ip).hex()])
 r.COMMANDS["udp-packet-builder"](["1","2","abc"])
 r.COMMANDS["icmp-latency-sampler"](["1","2","3"])
 r.COMMANDS["dns-record-lookup"](["localhost","A"])
 r.COMMANDS["dns-soa-serial-checker"](["1","2","3"])
 r.COMMANDS["dns-mx-priority-sorter"](["10:mx2","5:mx1"])
 r.COMMANDS["dns-ptr-reverse-resolver"](["127.0.0.1"])
 r.COMMANDS["dns-srv-balancer"](["10:5:443:a","5:1:443:b"])
 r.COMMANDS["bandwidth-rate-calc"](["1000","2"])
 r.COMMANDS["packet-loss-estimator"](["100","97"])
 r.COMMANDS["url-encode-decode-cli"](["encode","a b"])
 r.COMMANDS["punycode-domain-codec"](["encode","münich.example"])
 r.COMMANDS["subnet-mask-calc"](["10.0.0.1/24"])
 r.COMMANDS["cidr-overlap-checker"](["10.0.0.0/24","10.0.0.128/25"])
 r.COMMANDS["ip-range-expander"](["192.0.2.0/30","10"])
 r.COMMANDS["ipv6-compressor"](["2001:0db8::1"])
 r.COMMANDS["network-interface-stat"]([])
print("PASS: shard08 exact 50-command registry + deterministic functional smoke")
