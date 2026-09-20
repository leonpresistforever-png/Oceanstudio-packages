#!/usr/bin/env python3
from __future__ import annotations
import binascii, hashlib, json, math, os, re, struct, sys, termios, uuid, zlib
from collections import Counter
from pathlib import Path

VERSION="2.0.0"
FDT_MAGIC=0xD00DFEED

def die(msg,code=2):print(msg,file=sys.stderr);raise SystemExit(code)
def out(v):print(json.dumps(v,indent=2,default=str) if isinstance(v,(dict,list,tuple)) else v)
def rb(path=None):return Path(path).read_bytes() if path and path!="-" else sys.stdin.buffer.read()
def rt(path=None):return Path(path).read_text(errors="replace") if path and path!="-" else sys.stdin.read()
def u16le(b,o=0):return int.from_bytes(b[o:o+2],"little")
def u32le(b,o=0):return int.from_bytes(b[o:o+4],"little")
def u32be(b,o=0):return int.from_bytes(b[o:o+4],"big")
def u64le(b,o=0):return int.from_bytes(b[o:o+8],"little")
def cstr(b):return b.split(b"\0",1)[0].decode(errors="replace")

def fdt_parse(data):
    if len(data)<40:die("DTB too small")
    vals=struct.unpack_from(">10I",data,0)
    magic,totalsize,off_struct,off_strings,off_rsvmap,version,last_comp,boot_cpuid,size_strings,size_struct=vals
    if magic!=FDT_MAGIC:die("bad FDT magic")
    if totalsize>len(data):die("truncated DTB")
    strings=data[off_strings:off_strings+size_strings]
    pos=off_struct;end=off_struct+size_struct;stack=[];nodes=[];current=None
    def sname(off):
        if off>=len(strings):return f"<bad-string-offset:{off}>"
        return cstr(strings[off:])
    while pos+4<=end:
        token=u32be(data,pos);pos+=4
        if token==1:
            z=data.find(b"\0",pos,end)
            if z<0:die("unterminated FDT node name")
            name=data[pos:z].decode(errors="replace");pos=(z+4)&~3
            stack.append(name)
            path="/" + "/".join(x for x in stack if x)
            current={"path":path or "/","name":name,"properties":{}}
            nodes.append(current)
        elif token==2:
            if stack:stack.pop()
            current=nodes[-1] if nodes else None
        elif token==3:
            if pos+8>end:die("truncated FDT property")
            ln=u32be(data,pos);noff=u32be(data,pos+4);pos+=8
            val=data[pos:pos+ln];pos=(pos+ln+3)&~3
            if nodes:nodes[-1]["properties"][sname(noff)]=val
        elif token==4:continue
        elif token==9:break
        else:die(f"unknown FDT token {token}")
    return {"header":{"totalsize":totalsize,"off_dt_struct":off_struct,"off_dt_strings":off_strings,"off_mem_rsvmap":off_rsvmap,"version":version,"last_comp_version":last_comp,"boot_cpuid_phys":boot_cpuid,"size_dt_strings":size_strings,"size_dt_struct":size_struct},"nodes":nodes}
def val_repr(v):
    if len(v)==0:return True
    try:
        s=v.rstrip(b"\0").decode("utf-8")
        if s and all(c.isprintable() or c=="\0" for c in s):return s.split("\0") if "\0" in s else s
    except:pass
    if len(v)%4==0 and len(v)<=64:return {"cells_be":[u32be(v,i) for i in range(0,len(v),4)],"hex":v.hex()}
    return {"hex":v.hex(),"length":len(v)}
def fdt_json(parsed):
    return {"header":parsed["header"],"nodes":[{"path":n["path"],"name":n["name"],"properties":{k:val_repr(v) for k,v in n["properties"].items()}} for n in parsed["nodes"]]}
def device_tree_fdt_dump(args):out(fdt_json(fdt_parse(rb(args[0] if args else None))))
def fdt_property_inspector(args):
    if len(args)<3:die("usage: fdt-property-inspector DTB NODE_PATH PROPERTY")
    p=fdt_parse(rb(args[0]));node=next((n for n in p["nodes"] if n["path"]==args[1]),None)
    if not node:die("node not found")
    if args[2] not in node["properties"]:die("property not found")
    out({"path":args[1],"property":args[2],"value":val_repr(node["properties"][args[2]])})
def fdt_node_path_search(args):
    if len(args)<2:die("usage: fdt-node-path-search DTB REGEX")
    p=fdt_parse(rb(args[0]));rx=re.compile(args[1]);out([n["path"] for n in p["nodes"] if rx.search(n["path"])])

def u_boot_image_header(args):
    d=rb(args[0] if args else None)
    if len(d)<64:die("image shorter than 64-byte U-Boot header")
    magic,hcrc,timestamp,size,load,entry,dcrc=struct.unpack_from(">7I",d,0)
    osid,arch,typ,comp=struct.unpack_from("4B",d,28);name=cstr(d[32:64])
    hdr=bytearray(d[:64]);hdr[4:8]=b"\0"*4;calc=zlib.crc32(hdr)&0xffffffff
    payload=d[64:64+size];pcrc=zlib.crc32(payload)&0xffffffff if len(payload)==size else None
    out({"valid_magic":magic==0x27051956,"magic":hex(magic),"header_crc":hex(hcrc),"header_crc_valid":calc==hcrc,"timestamp":timestamp,"data_size":size,"load_address":hex(load),"entry_point":hex(entry),"data_crc":hex(dcrc),"data_crc_valid":pcrc==dcrc if pcrc is not None else None,"os":osid,"arch":arch,"type":typ,"compression":comp,"name":name})
def u_boot_env_crc_calc(args):
    d=rb(args[0] if args else None)
    if len(d)>=5:
        stored=u32le(d,0);payload=d[4:];calc=zlib.crc32(payload)&0xffffffff
        out({"stored_crc_le":hex(stored),"calculated_crc32":hex(calc),"valid":stored==calc,"variables":[x.decode(errors="replace") for x in payload.split(b"\0") if b"=" in x][:200]})
    else:out({"calculated_crc32":hex(zlib.crc32(d)&0xffffffff),"valid":None})
def u_boot_fit_image_view(args):
    p=fdt_parse(rb(args[0] if args else None));j=fdt_json(p)
    imgs=[n for n in j["nodes"] if n["path"].startswith("/images/")]
    cfg=[n for n in j["nodes"] if n["path"].startswith("/configurations/")]
    out({"header":j["header"],"images":imgs,"configurations":cfg})

def coreboot_cbfs_parser(args):
    d=rb(args[0] if args else None);rows=[];pos=0
    while True:
        i=d.find(b"LARCHIVE",pos)
        if i<0:break
        if i+24>len(d):break
        ln,typ,checksum,offset=struct.unpack_from(">4I",d,i+8)
        nz=d.find(b"\0",i+24,min(len(d),i+1024));name=d[i+24:nz].decode(errors="replace") if nz>=0 else ""
        start=i+offset;rows.append({"offset":i,"name":name,"data_length":ln,"type":typ,"checksum":hex(checksum),"data_offset":start,"data_within_file":start+ln<=len(d)})
        pos=i+8
    out({"files":rows,"count":len(rows)})
def edkid_uefi_capsule_chk(args):
    d=rb(args[0] if args else None)
    if len(d)<28:die("capsule shorter than EFI_CAPSULE_HEADER")
    guid=str(uuid.UUID(bytes_le=d[:16]));hs,flags,size=struct.unpack_from("<III",d,16)
    out({"capsule_guid":guid,"header_size":hs,"flags":hex(flags),"capsule_image_size":size,"valid":28<=hs<=len(d) and size<=len(d) and size>=hs,"persist_across_reset":bool(flags&0x00010000),"populate_system_table":bool(flags&0x00020000),"initiate_reset":bool(flags&0x00040000)})
def uefi_variable_dump(args):
    if not args:die("usage: uefi-variable-dump EFIVARFS_FILE")
    p=Path(args[0]);d=p.read_bytes()
    m=re.match(r"^(.*)-([0-9a-fA-F-]{36})$",p.name);attrs=u32le(d,0) if len(d)>=4 else None
    out({"name":m.group(1) if m else p.name,"vendor_guid":m.group(2) if m else None,"attributes":hex(attrs) if attrs is not None else None,"non_volatile":bool(attrs&1) if attrs is not None else None,"bootservice_access":bool(attrs&2) if attrs is not None else None,"runtime_access":bool(attrs&4) if attrs is not None else None,"data_length":max(0,len(d)-4),"data_hex":d[4:260].hex()})

def smbios_dmi_table_view(args):
    d=rb(args[0] if args else None);pos=0;rows=[]
    names={0:"BIOS",1:"System",2:"Baseboard",3:"Chassis",4:"Processor",17:"Memory Device",127:"End"}
    while pos+4<=len(d):
        typ,ln,handle=struct.unpack_from("<BBH",d,pos)
        if ln<4 or pos+ln>len(d):break
        sp=pos+ln;end=sp
        while end+1<len(d) and d[end:end+2]!=b"\0\0":end+=1
        strings=[x.decode(errors="replace") for x in d[sp:end].split(b"\0") if x]
        rows.append({"offset":pos,"type":typ,"type_name":names.get(typ,"Other"),"length":ln,"handle":hex(handle),"formatted_hex":d[pos+4:pos+ln].hex(),"strings":strings})
        pos=end+2
        if typ==127:break
    out({"structures":rows,"count":len(rows)})

def acpi_header(d):
    if len(d)<36:die("ACPI table too short")
    sig=d[:4].decode(errors="replace");length=u32le(d,4);rev=d[8];chk=d[9];oemid=d[10:16].decode(errors="replace").rstrip();oemt=d[16:24].decode(errors="replace").rstrip();oemrev=u32le(d,24);creator=d[28:32].decode(errors="replace");crev=u32le(d,32)
    return {"signature":sig,"length":length,"revision":rev,"checksum":chk,"checksum_valid":sum(d[:min(length,len(d))])%256==0 if length<=len(d) else None,"oem_id":oemid,"oem_table_id":oemt,"oem_revision":oemrev,"creator_id":creator,"creator_revision":crev}
def acpi_table_parser_dsdt(args):
    d=rb(args[0] if args else None);h=acpi_header(d);h["is_dsdt"]=h["signature"]=="DSDT";h["aml_length"]=max(0,min(h["length"],len(d))-36);out(h)
def acpi_fadt_header_dump(args):
    d=rb(args[0] if args else None);h=acpi_header(d);h["is_fadt"]=h["signature"] in ("FACP","FADT")
    if len(d)>=44:h["firmware_ctrl"]=hex(u32le(d,36));h["dsdt"]=hex(u32le(d,40))
    if len(d)>=116:h["flags"]=hex(u32le(d,112))
    out(h)

def spdx_sbom_firmware_chk(args):
    d=json.loads(rt(args[0] if args else None));errors=[]
    if not str(d.get("spdxVersion","")).startswith("SPDX-"):errors.append("spdxVersion missing")
    if not d.get("SPDXID"):errors.append("SPDXID missing")
    pkgs=d.get("packages",[]);files=d.get("files",[])
    for i,p in enumerate(pkgs):
        if not p.get("name"):errors.append(f"packages[{i}].name missing")
        if not p.get("SPDXID"):errors.append(f"packages[{i}].SPDXID missing")
    out({"valid":not errors,"errors":errors,"packages":len(pkgs),"files":len(files),"document_name":d.get("name")})
def entropy(block):
    if not block:return 0.0
    c=Counter(block);n=len(block);return -sum((v/n)*math.log2(v/n) for v in c.values())
def binwalk_entropy_plot(args):
    if not args:die("usage: binwalk-entropy-plot FILE [BLOCK_SIZE]")
    d=rb(args[0]);bs=int(args[1]) if len(args)>1 else 1024
    vals=[entropy(d[i:i+bs]) for i in range(0,len(d),bs)]
    for i,e in enumerate(vals):
        print(f"{i*bs:08x} {e:0.4f} {'#'*round(e/8*40)}")
def firmware_crc32_verifier(args):
    if not args:die("usage: firmware-crc32-verifier FILE [EXPECTED_HEX]")
    crc=zlib.crc32(rb(args[0]))&0xffffffff;expected=int(args[1],16) if len(args)>1 else None
    out({"crc32":f"{crc:08x}","expected":f"{expected:08x}" if expected is not None else None,"valid":crc==expected if expected is not None else None})

def ihex_records(text):
    rows=[]
    for n,line in enumerate(text.splitlines(),1):
        line=line.strip()
        if not line:continue
        if not line.startswith(":"):die(f"line {n}: missing ':'")
        raw=bytes.fromhex(line[1:])
        if len(raw)<5:die(f"line {n}: too short")
        count=raw[0];addr=int.from_bytes(raw[1:3],"big");typ=raw[3];data=raw[4:4+count];chk=raw[4+count]
        valid=(sum(raw)&0xff)==0
        rows.append({"line":n,"count":count,"address":addr,"type":typ,"data":data,"checksum_valid":valid})
    return rows
def intel_hex_ihex_converter(args):
    mode=args[0] if args and args[0] in ("parse","to-bin") else "parse";path=args[1] if mode!="parse" and len(args)>1 else (args[1] if args and args[0]=="parse" and len(args)>1 else (args[0] if args and args[0] not in ("parse","to-bin") else None))
    rows=ihex_records(rt(path))
    if mode=="parse":out([{"line":r["line"],"count":r["count"],"address":hex(r["address"]),"type":r["type"],"checksum_valid":r["checksum_valid"],"data_hex":r["data"].hex()} for r in rows]);return
    upper=0;mem={}
    for r in rows:
        if not r["checksum_valid"]:die(f"bad checksum at line {r['line']}")
        if r["type"]==0:
            base=upper+r["address"]
            for i,b in enumerate(r["data"]):mem[base+i]=b
        elif r["type"]==4:upper=int.from_bytes(r["data"],"big")<<16
        elif r["type"]==2:upper=int.from_bytes(r["data"],"big")<<4
    if not mem:return
    lo,hi=min(mem),max(mem);sys.stdout.buffer.write(bytes(mem.get(i,0xff) for i in range(lo,hi+1)))
def srec_records(text):
    rows=[]
    addrlen={"0":2,"1":2,"2":3,"3":4,"5":2,"6":3,"7":4,"8":3,"9":2}
    for n,line in enumerate(text.splitlines(),1):
        line=line.strip()
        if not line:continue
        if not re.match(r"^S[0-9]",line):die(f"line {n}: invalid S-record")
        typ=line[1];raw=bytes.fromhex(line[2:]);count=raw[0];al=addrlen.get(typ)
        if al is None:continue
        addr=int.from_bytes(raw[1:1+al],"big");data=raw[1+al:-1];valid=((sum(raw)&0xff)==0xff and count==len(raw)-1)
        rows.append({"line":n,"type":typ,"address":addr,"data":data,"checksum_valid":valid})
    return rows
def motorola_srec_parser(args):
    rows=srec_records(rt(args[0] if args else None));out([{"line":r["line"],"type":"S"+r["type"],"address":hex(r["address"]),"data_hex":r["data"].hex(),"checksum_valid":r["checksum_valid"]} for r in rows])

def gf2_remainder(data,poly):
    degree=poly.bit_length()-1;reg=0;mask=(1<<degree)-1
    for byte in data:
        for bit in range(7,-1,-1):
            top=(reg>>(degree-1))&1 if degree else 0
            reg=((reg<<1)|((byte>>bit)&1))&mask
            if top:reg^=(poly&mask)
    for _ in range(degree):
        top=(reg>>(degree-1))&1 if degree else 0;reg=(reg<<1)&mask
        if top:reg^=(poly&mask)
    return reg,degree
def raw_nand_ecc_calculator(args):
    if not args:die("usage: raw-nand-ecc-calculator FILE [GENERATOR_POLY_HEX]")
    poly=int(args[1],16) if len(args)>1 else 0x201B
    rem,deg=gf2_remainder(rb(args[0]),poly)
    out({"generator_polynomial":hex(poly),"degree":deg,"parity_hex":f"{rem:0{(deg+3)//4}x}","note":"GF(2) polynomial parity; supply the generator polynomial required by the NAND/BCH profile"})
def nor_flash_sector_align(args):
    if len(args)<3:die("usage: nor-flash-sector-align OFFSET LENGTH SECTOR_SIZE")
    off,ln,sec=[int(x,0) for x in args[:3]]
    start=(off//sec)*sec;end=((off+ln+sec-1)//sec)*sec
    out({"aligned":off%sec==0 and ln%sec==0,"erase_start":hex(start),"erase_end":hex(end),"erase_length":end-start,"sector_size":sec})
JEDEC={0x01:"Spansion/Cypress",0x20:"Micron/Numonyx",0x1F:"Adesto/Atmel",0x9D:"ISSI",0xC2:"Macronix",0xEF:"Winbond",0xBF:"SST/Microchip",0xC8:"GigaDevice"}
def spi_flash_jedec_id_chk(args):
    if not args:die("usage: spi-flash-jedec-id-chk HEX_ID")
    s=re.sub(r"[^0-9a-fA-F]","",args[0]);d=bytes.fromhex(s)
    out({"raw":d.hex(),"manufacturer_id":hex(d[0]) if d else None,"manufacturer":JEDEC.get(d[0],"Unknown") if d else None,"memory_type":hex(d[1]) if len(d)>1 else None,"capacity_code":hex(d[2]) if len(d)>2 else None,"nominal_capacity_bytes":(1<<d[2]) if len(d)>2 and d[2]<64 else None})

def i2c_bus_address_probe(args):
    vals=[int(x,0) for x in args] if args else list(range(128));rows=[]
    for a in vals:
        reserved=a<0x08 or a>0x77
        reason="reserved/special" if reserved else "normal 7-bit device address"
        rows.append({"address":f"0x{a:02x}","valid_7bit":0<=a<=0x7f,"reserved":reserved,"reason":reason})
    out(rows)
def crc8_smbus(data):
    crc=0
    for b in data:
        crc^=b
        for _ in range(8):crc=((crc<<1)^0x07)&0xff if crc&0x80 else (crc<<1)&0xff
    return crc
def i2c_smbus_block_calc(args):
    data=bytes.fromhex(re.sub(r"[^0-9a-fA-F]","",args[0])) if args else sys.stdin.buffer.read()
    out({"bytes":data.hex(),"pec_crc8":f"{crc8_smbus(data):02x}"})
def gpio_sysfs_pin_export(args):
    if not args:die("usage: gpio-sysfs-pin-export GPIO [in|out] [VALUE]")
    gpio=int(args[0]);base=Path("/sys/class/gpio");gp=base/f"gpio{gpio}"
    out({"gpio":gpio,"legacy_sysfs_exists":base.exists(),"already_exported":gp.exists(),"export_path":str(base/"export"),"direction_path":str(gp/"direction"),"value_path":str(gp/"value"),"requested_direction":args[1] if len(args)>1 else None,"requested_value":args[2] if len(args)>2 else None,"note":"inspection/planning only; this command does not write sysfs"})
def gpio_cdev_line_event(args):
    d=rb(args[0] if args else None);size=48;rows=[]
    for o in range(0,len(d)-size+1,size):
        ts,idv,offset,seq,line_seq=struct.unpack_from("<QIIII",d,o)
        rows.append({"timestamp_ns":ts,"id":idv,"edge":"rising" if idv==1 else "falling" if idv==2 else "unknown","offset":offset,"seqno":seq,"line_seqno":line_seq})
    out(rows)
def uart_baud_rate_divisor(args):
    if len(args)<2:die("usage: uart-baud-rate-divisor CLOCK_HZ BAUD [OVERSAMPLE]")
    clk=float(args[0]);baud=float(args[1]);over=float(args[2]) if len(args)>2 else 16
    div=clk/(over*baud);nearest=max(1,round(div));actual=clk/(over*nearest)
    out({"ideal_divisor":div,"integer_divisor":nearest,"actual_baud":actual,"error_percent":100*(actual-baud)/baud,"oversample":over})
def serial_termios_config(args):
    if not args:die("usage: serial-termios-config C_CFLAG_INTEGER")
    f=int(args[0],0)
    cs=f&termios.CSIZE
    sizes={termios.CS5:5,termios.CS6:6,termios.CS7:7,termios.CS8:8}
    out({"c_cflag":hex(f),"data_bits":sizes.get(cs),"stop_bits":2 if f&termios.CSTOPB else 1,"parity_enabled":bool(f&termios.PARENB),"parity":"odd" if f&termios.PARODD else "even","hardware_flow_control":bool(f&getattr(termios,"CRTSCTS",0)),"receiver_enabled":bool(f&termios.CREAD),"local_mode":bool(f&termios.CLOCAL)})

USB_TYPES={1:"Device",2:"Configuration",3:"String",4:"Interface",5:"Endpoint",6:"Device Qualifier",7:"Other Speed Config",11:"IAD",15:"BOS",33:"HID",34:"Report"}
def usb_descriptors(data):
    rows=[];o=0
    while o+2<=len(data):
        ln=data[o];typ=data[o+1]
        if ln<2 or o+ln>len(data):rows.append({"offset":o,"error":"invalid length","length":ln,"type":typ});break
        rows.append({"offset":o,"length":ln,"type":typ,"type_name":USB_TYPES.get(typ,"Unknown"),"raw":data[o:o+ln].hex()});o+=ln
    return rows
def usb_descriptor_parser(args):out(usb_descriptors(rb(args[0] if args else None)))
def usb_string_descriptor(args):
    d=rb(args[0] if args else None)
    if len(d)<2 or d[1]!=3:die("not a USB string descriptor")
    ln=min(d[0],len(d));out({"length":ln,"type":3,"string":d[2:ln].decode("utf-16le",errors="replace")})
def usb_endpoint_analyzer(args):
    d=rb(args[0] if args else None)
    if len(d)<7 or d[1]!=5:die("not a USB endpoint descriptor")
    addr=d[2];attr=d[3];mps=u16le(d,4);tt={0:"control",1:"isochronous",2:"bulk",3:"interrupt"}[attr&3]
    out({"endpoint_number":addr&0xf,"direction":"IN" if addr&0x80 else "OUT","transfer_type":tt,"sync_type":(attr>>2)&3,"usage_type":(attr>>4)&3,"max_packet_size":mps&0x7ff,"transactions_per_microframe":1+((mps>>11)&3),"interval":d[6]})
def hid_report_descriptor(args):
    d=rb(args[0] if args else None);o=0;rows=[]
    types={0:"Main",1:"Global",2:"Local",3:"Reserved"}
    while o<len(d):
        b=d[o];o+=1
        if b==0xfe:
            if o+2>len(d):break
            size=d[o];tag=d[o+1];o+=2;val=d[o:o+size];o+=size;rows.append({"long":True,"tag":tag,"size":size,"data":val.hex()});continue
        sc=b&3;size=4 if sc==3 else sc;typ=(b>>2)&3;tag=(b>>4)&15;val=d[o:o+size];o+=size
        rows.append({"type":types[typ],"tag":tag,"size":size,"value_unsigned":int.from_bytes(val,"little") if val else 0,"data":val.hex()})
    out(rows)

def can_bus_frame_dumper(args):
    s=" ".join(args).strip() or rt().strip()
    m=re.search(r"(?:(\w+)\s+)?([0-9A-Fa-f]{3,8})#([0-9A-Fa-f]*)",s)
    if not m:die("expected can-utils frame like can0 123#112233")
    iface,cid,hexdata=m.groups();ident=int(cid,16);data=bytes.fromhex(hexdata)
    out({"interface":iface,"can_id":hex(ident),"extended":len(cid)>3 or ident>0x7ff,"dlc":len(data),"data":data.hex(),"bytes":list(data)})
def can_j1939_pgn_parser(args):
    if not args:die("usage: can-j1939-pgn-parser CAN_ID")
    ident=int(args[0],0);prio=(ident>>26)&7;dp=(ident>>24)&1;pf=(ident>>16)&0xff;ps=(ident>>8)&0xff;sa=ident&0xff
    pgn=(dp<<16)|(pf<<8)|(0 if pf<240 else ps);dest=ps if pf<240 else None
    out({"can_id":hex(ident),"priority":prio,"data_page":dp,"pdu_format":pf,"pdu_specific":ps,"source_address":sa,"destination_address":dest,"pgn":pgn,"pgn_hex":f"0x{pgn:05x}"})
def modbus_crc(data):
    crc=0xffff
    for b in data:
        crc^=b
        for _ in range(8):crc=(crc>>1)^0xA001 if crc&1 else crc>>1
    return crc&0xffff
def modbus_rtu_crc16_calc(args):
    d=bytes.fromhex(re.sub(r"[^0-9a-fA-F]","",args[0])) if args else sys.stdin.buffer.read();crc=modbus_crc(d)
    out({"crc16":f"{crc:04x}","wire_little_endian":crc.to_bytes(2,"little").hex()})
def modbus_tcp_header_chk(args):
    d=bytes.fromhex(re.sub(r"[^0-9a-fA-F]","",args[0])) if args else sys.stdin.buffer.read()
    if len(d)<8:die("need MBAP header plus function byte")
    tid,pid,ln=struct.unpack_from(">HHH",d,0);unit=d[6];func=d[7]
    out({"transaction_id":tid,"protocol_id":pid,"length":ln,"unit_id":unit,"function_code":func,"valid_protocol_id":pid==0,"length_matches_available":ln<=len(d)-6})
def zigbee_zcl_frame_view(args):
    d=bytes.fromhex(re.sub(r"[^0-9a-fA-F]","",args[0])) if args else sys.stdin.buffer.read()
    if len(d)<3:die("ZCL frame too short")
    fc=d[0];o=1;man=None
    if fc&0x04:
        if len(d)<5:die("manufacturer-specific ZCL frame truncated")
        man=u16le(d,o);o+=2
    seq=d[o];cmd=d[o+1];o+=2
    out({"frame_type":fc&3,"manufacturer_specific":bool(fc&4),"direction":"server-to-client" if fc&8 else "client-to-server","disable_default_response":bool(fc&0x10),"manufacturer_code":man,"sequence":seq,"command_id":cmd,"payload_hex":d[o:].hex()})
GATT={0x1800:"Generic Access",0x1801:"Generic Attribute",0x180A:"Device Information",0x180D:"Heart Rate",0x180F:"Battery Service",0x1812:"Human Interface Device",0x181A:"Environmental Sensing"}
def ble_gatt_uuid_lookup(args):
    if not args:die("usage: ble-gatt-uuid-lookup UUID")
    s=args[0].lower().replace("0x","")
    if re.fullmatch(r"[0-9a-f]{4}",s):
        v=int(s,16);full=f"0000{s}-0000-1000-8000-00805f9b34fb";out({"uuid16":f"0x{s}","uuid128":full,"assigned_name":GATT.get(v,"Unknown")})
    else:
        u=str(uuid.UUID(args[0]));m=re.fullmatch(r"0000([0-9a-f]{4})-0000-1000-8000-00805f9b34fb",u);v=int(m.group(1),16) if m else None
        out({"uuid128":u,"uuid16":f"0x{v:04x}" if v is not None else None,"assigned_name":GATT.get(v,"Unknown") if v is not None else None})
def bluetooth_hci_cmd_dump(args):
    d=bytes.fromhex(re.sub(r"[^0-9a-fA-F]","",args[0])) if args else sys.stdin.buffer.read();o=0
    if d and d[0]==1:o=1
    if len(d)<o+3:die("HCI command too short")
    opcode=u16le(d,o);plen=d[o+2];params=d[o+3:o+3+plen]
    out({"packet_type":"command" if o else "bare command","opcode":hex(opcode),"ogf":(opcode>>10)&0x3f,"ocf":opcode&0x3ff,"parameter_length":plen,"parameters_hex":params.hex(),"complete":len(params)==plen})
def rfid_mifare_block_chk(args):
    if not args:die("usage: rfid-mifare-block-chk SECTOR_TRAILER_HEX")
    d=bytes.fromhex(re.sub(r"[^0-9a-fA-F]","",args[0]))
    if len(d)<9:die("need at least bytes 6..8 of a 16-byte sector trailer")
    b6,b7,b8=d[6:9] if len(d)>=9 else d[:3];rows=[];valid=True
    for i in range(4):
        c1=(b7>>(4+i))&1;c2=(b8>>i)&1;c3=(b8>>(4+i))&1
        nc1=(b6>>i)&1;nc2=(b6>>(4+i))&1;nc3=(b7>>i)&1
        comp=(nc1==(1-c1) and nc2==(1-c2) and nc3==(1-c3));valid&=comp
        rows.append({"block":i,"C1":c1,"C2":c2,"C3":c3,"code":f"{c1}{c2}{c3}","complements_valid":comp})
    out({"access_bytes":bytes((b6,b7,b8)).hex(),"valid_complements":bool(valid),"blocks":rows})
def nfc_ndef_record_parser(args):
    d=rb(args[0] if args else None);o=0;rows=[]
    while o<len(d):
        start=o;hdr=d[o];o+=1;mb=bool(hdr&0x80);me=bool(hdr&0x40);cf=bool(hdr&0x20);sr=bool(hdr&0x10);il=bool(hdr&0x08);tnf=hdr&7
        if o>=len(d):break
        tl=d[o];o+=1
        if sr:
            if o>=len(d):break
            pl=d[o];o+=1
        else:
            if o+4>len(d):break
            pl=u32be(d,o);o+=4
        idl=d[o] if il and o<len(d) else 0
        if il:o+=1
        typ=d[o:o+tl];o+=tl;ident=d[o:o+idl];o+=idl;payload=d[o:o+pl];o+=pl
        rows.append({"offset":start,"mb":mb,"me":me,"cf":cf,"sr":sr,"il":il,"tnf":tnf,"type":typ.decode(errors="replace"),"id":ident.hex(),"payload_length":pl,"payload_hex":payload.hex()})
        if me:break
    out(rows)

def i2s_audio_clock_calc(args):
    if len(args)<3:die("usage: i2s-audio-clock-calc SAMPLE_RATE BITS_PER_SAMPLE CHANNELS [MCLK_MULTIPLE]")
    fs,bits,ch=float(args[0]),int(args[1]),int(args[2]);mult=int(args[3]) if len(args)>3 else 256
    out({"sample_rate_hz":fs,"bits_per_sample":bits,"channels":ch,"bclk_hz":fs*bits*ch,"lrclk_hz":fs,"mclk_hz":fs*mult,"mclk_multiple":mult})
def pwm_frequency_duty_calc(args):
    if len(args)<2:die("usage: pwm-frequency-duty-calc PERIOD_NS DUTY_NS")
    period,duty=float(args[0]),float(args[1])
    if period<=0 or not 0<=duty<=period:die("invalid period/duty")
    out({"period_ns":period,"duty_ns":duty,"frequency_hz":1e9/period,"duty_percent":100*duty/period})
def thermal_zone_temp_view(args):
    rows=[]
    for z in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        def r(n):
            try:return (z/n).read_text().strip()
            except:return None
        trips=[]
        for f in sorted(z.glob("trip_point_*_temp")):
            try:trips.append({"name":f.stem,"temp_mC":int(f.read_text().strip())})
            except:pass
        t=r("temp");rows.append({"zone":z.name,"type":r("type"),"temp_mC":int(t) if t and t.lstrip("-").isdigit() else t,"trips":trips})
    out(rows)
def cpufreq_scaling_gov(args):
    rows=[]
    for c in sorted(Path("/sys/devices/system/cpu").glob("cpu[0-9]*")):
        p=c/"cpufreq"
        if not p.exists():continue
        def r(n):
            try:return (p/n).read_text().strip()
            except:return None
        rows.append({"cpu":c.name,"governor":r("scaling_governor"),"available_governors":(r("scaling_available_governors") or "").split(),"current_khz":r("scaling_cur_freq"),"min_khz":r("scaling_min_freq"),"max_khz":r("scaling_max_freq")})
    out(rows)
def power_supply_status_chk(args):
    rows=[]
    for p in sorted(Path("/sys/class/power_supply").glob("*")):
        d={"name":p.name}
        for k in ("type","status","health","capacity","voltage_now","current_now","power_now","energy_now","charge_now","temp","technology"):
            try:d[k]=(p/k).read_text().strip()
            except:pass
        rows.append(d)
    out(rows)
def regulator_voltage_view(args):
    rows=[]
    bases=[Path("/sys/class/regulator"),Path("/sys/kernel/debug/regulator")]
    for base in bases:
        if not base.exists():continue
        for p in sorted(base.glob("*")):
            if not p.is_dir():continue
            d={"path":str(p)}
            for k in ("name","microvolts","min_microvolts","max_microvolts","state","status"):
                try:d[k]=(p/k).read_text().strip()
                except:pass
            rows.append(d)
    out(rows)

def nvme_smart_log_parser(args):
    d=rb(args[0] if args else None)
    if len(d)<192:die("NVMe SMART log must be at least 192 bytes")
    u128=lambda o:int.from_bytes(d[o:o+16],"little")
    temp=u16le(d,1)
    out({"critical_warning":d[0],"temperature_kelvin":temp,"temperature_celsius":temp-273.15 if temp else None,"available_spare_percent":d[3],"spare_threshold_percent":d[4],"percentage_used":d[5],"data_units_read":u128(32),"data_units_written":u128(48),"host_read_commands":u128(64),"host_write_commands":u128(80),"controller_busy_minutes":u128(96),"power_cycles":u128(112),"power_on_hours":u128(128),"unsafe_shutdowns":u128(144),"media_errors":u128(160),"error_log_entries":u128(176)})
def scsi_inquiry_vpd_dump(args):
    d=rb(args[0] if args else None)
    if len(d)<4:die("VPD page too short")
    pqdt=d[0];page=d[1];ln=u16le(bytes((d[3],d[2]))) if False else int.from_bytes(d[2:4],"big");payload=d[4:4+ln]
    res={"peripheral_qualifier":(pqdt>>5)&7,"peripheral_device_type":pqdt&31,"page_code":hex(page),"page_length":ln,"truncated":len(payload)<ln}
    if page==0x80:res["unit_serial_number"]=payload.decode(errors="replace").strip()
    elif page==0x83:
        desc=[];o=0
        while o+4<=len(payload):
            code=payload[o];assoc_type=payload[o+1];l=payload[o+3];val=payload[o+4:o+4+l]
            desc.append({"codeset":code&0xf,"association":(assoc_type>>4)&3,"designator_type":assoc_type&0xf,"value_hex":val.hex(),"value_text":val.decode(errors="replace") if (code&0xf)==2 else None});o+=4+l
        res["designators"]=desc
    out(res)
def pci_config_space_dump(args):
    d=rb(args[0] if args else None)
    if len(d)<64:die("PCI config space shorter than 64 bytes")
    vendor,device,command,status=struct.unpack_from("<HHHH",d,0);rev=d[8];progif=d[9];subclass=d[10];cls=d[11];cache=d[12];lat=d[13];hdr=d[14];bist=d[15]
    bars=[u32le(d,16+i*4) for i in range(6)]
    out({"vendor_id":f"0x{vendor:04x}","device_id":f"0x{device:04x}","command":hex(command),"status":hex(status),"revision":rev,"class_code":f"{cls:02x}{subclass:02x}{progif:02x}","cache_line_size":cache,"latency_timer":lat,"header_type":hdr,"bist":bist,"bars":[hex(x) for x in bars],"capabilities_pointer":d[0x34] if len(d)>0x34 else None})
def pci_express_link_speed(args):
    if not args:die("usage: pci-express-link-speed SYSFS_PCI_DEVICE_DIR")
    p=Path(args[0])
    def r(n):
        try:return (p/n).read_text().strip()
        except:return None
    out({"device":str(p),"current_link_speed":r("current_link_speed"),"current_link_width":r("current_link_width"),"max_link_speed":r("max_link_speed"),"max_link_width":r("max_link_width"),"numa_node":r("numa_node")})
def edid_monitor_data_parse(args):
    d=rb(args[0] if args else None)
    if len(d)<128:die("EDID must contain at least 128 bytes")
    valid_header=d[:8]==b"\x00\xff\xff\xff\xff\xff\xff\x00";mfg=u16le(bytes((d[9],d[8]))) if False else int.from_bytes(d[8:10],"big")
    mid="".join(chr(((mfg>>s)&0x1f)+64) for s in (10,5,0));prod=u16le(d,10);serial=u32le(d,12);week=d[16];year=1990+d[17];ver=(d[18],d[19]);digital=bool(d[20]&0x80);wcm=d[21];hcm=d[22];ext=d[126];chk=sum(d[:128])&0xff
    desc=[]
    for o in range(54,126,18):
        b=d[o:o+18]
        if b[:3]==b"\0\0\0" and b[3] in (0xfc,0xff,0xfe):
            desc.append({"tag":hex(b[3]),"text":b[5:18].rstrip(b"\n \0").decode(errors="replace")})
        else:
            pix=u16le(b,0)*10_000
            if pix:
                ha=u16le(bytes((b[4]&0xf0,b[2]))) if False else b[2]|((b[4]&0xf0)<<4);va=b[5]|((b[7]&0xf0)<<4)
                desc.append({"pixel_clock_hz":pix,"h_active":ha,"v_active":va})
    out({"valid_header":valid_header,"checksum_valid":chk==0,"manufacturer":mid,"product_code":prod,"serial":serial,"manufacture_week":week,"manufacture_year":year,"edid_version":f"{ver[0]}.{ver[1]}","digital_input":digital,"size_cm":[wcm,hcm],"extensions":ext,"descriptors":desc})

COMMANDS={
"device-tree-fdt-dump":device_tree_fdt_dump,"fdt-property-inspector":fdt_property_inspector,"fdt-node-path-search":fdt_node_path_search,
"u-boot-image-header":u_boot_image_header,"u-boot-env-crc-calc":u_boot_env_crc_calc,"u-boot-fit-image-view":u_boot_fit_image_view,
"coreboot-cbfs-parser":coreboot_cbfs_parser,"edkid-uefi-capsule-chk":edkid_uefi_capsule_chk,"uefi-variable-dump":uefi_variable_dump,
"smbios-dmi-table-view":smbios_dmi_table_view,"acpi-table-parser-dsdt":acpi_table_parser_dsdt,"acpi-fadt-header-dump":acpi_fadt_header_dump,
"spdx-sbom-firmware-chk":spdx_sbom_firmware_chk,"binwalk-entropy-plot":binwalk_entropy_plot,"firmware-crc32-verifier":firmware_crc32_verifier,
"intel-hex-ihex-converter":intel_hex_ihex_converter,"motorola-srec-parser":motorola_srec_parser,"raw-nand-ecc-calculator":raw_nand_ecc_calculator,
"nor-flash-sector-align":nor_flash_sector_align,"spi-flash-jedec-id-chk":spi_flash_jedec_id_chk,"i2c-bus-address-probe":i2c_bus_address_probe,
"i2c-smbus-block-calc":i2c_smbus_block_calc,"gpio-sysfs-pin-export":gpio_sysfs_pin_export,"gpio-cdev-line-event":gpio_cdev_line_event,
"uart-baud-rate-divisor":uart_baud_rate_divisor,"serial-termios-config":serial_termios_config,"usb-descriptor-parser":usb_descriptor_parser,
"usb-string-descriptor":usb_string_descriptor,"usb-endpoint-analyzer":usb_endpoint_analyzer,"hid-report-descriptor":hid_report_descriptor,
"can-bus-frame-dumper":can_bus_frame_dumper,"can-j1939-pgn-parser":can_j1939_pgn_parser,"modbus-rtu-crc16-calc":modbus_rtu_crc16_calc,
"modbus-tcp-header-chk":modbus_tcp_header_chk,"zigbee-zcl-frame-view":zigbee_zcl_frame_view,"ble-gatt-uuid-lookup":ble_gatt_uuid_lookup,
"bluetooth-hci-cmd-dump":bluetooth_hci_cmd_dump,"rfid-mifare-block-chk":rfid_mifare_block_chk,"nfc-ndef-record-parser":nfc_ndef_record_parser,
"i2s-audio-clock-calc":i2s_audio_clock_calc,"pwm-frequency-duty-calc":pwm_frequency_duty_calc,"thermal-zone-temp-view":thermal_zone_temp_view,
"cpufreq-scaling-gov":cpufreq_scaling_gov,"power-supply-status-chk":power_supply_status_chk,"regulator-voltage-view":regulator_voltage_view,
"nvme-smart-log-parser":nvme_smart_log_parser,"scsi-inquiry-vpd-dump":scsi_inquiry_vpd_dump,"pci-config-space-dump":pci_config_space_dump,
"pci-express-link-speed":pci_express_link_speed,"edid-monitor-data-parse":edid_monitor_data_parse,
}
def main():
    if len(COMMANDS)!=50:die(f"internal command count mismatch: {len(COMMANDS)}")
    prog=Path(sys.argv[0]).name
    if prog in COMMANDS:cmd=prog;args=sys.argv[1:]
    else:
        if len(sys.argv)<2 or sys.argv[1] in ("-h","--help"):
            print("OceanStudio functional shard 24 runtime");[print(" ",x) for x in sorted(COMMANDS)];return
        if sys.argv[1] in ("-v","--version"):print(VERSION);return
        cmd=sys.argv[1];args=sys.argv[2:]
    if cmd not in COMMANDS:die(f"unknown command: {cmd}")
    COMMANDS[cmd](args)
if __name__=="__main__":main()
