#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, subprocess, tempfile
from pathlib import Path

PREFIX='/data/data/studio.ocean.app/files/usr'
VERSION='1.0.0-1'
CORE_PACKAGE='ocean-power-core'

FAMILIES={
'hash':['md5','sha1','sha224','sha256','sha384','sha512','sha3-224','sha3-256','sha3-384','sha3-512','blake2b','blake2s'],
'hmac':['md5','sha1','sha224','sha256','sha384','sha512','sha3-256','sha3-512','blake2b','blake2s'],
'encode':['base64','base32','base16','base85','ascii85','hex','url','html','json','rot13','gzip','zlib','bz2','lzma','utf8','repr'],
'decode':['base64','base32','base16','base85','ascii85','hex','url','html','json','rot13','gzip','zlib','bz2','lzma','utf8','repr'],
'text':['lines','words','chars','bytes','reverse','reverse-lines','sort','sort-num','unique','uniq-count','freq-words','freq-lines','lower','upper','title','strip','squeeze-space','tabs-to-spaces','spaces-to-tabs','head','tail','grep','grep-v','regex-replace','number-lines'],
'json':['pretty','minify','validate','keys','values','get','set','delete','merge','diff','flatten','unflatten','sort-keys','array-length','object-size','type','path-list','ndjson-to-array','array-to-ndjson','canonical'],
'csv':['rows','columns','header','head','tail','select','drop','sort','unique','filter-eq','filter-regex','stats','sum','mean','min','max','transpose','to-json','from-json','dialect'],
'file':['size','entropy','strings','hexdump','magic','lines','words','duplicates','find-name','find-size','tree','largest','newest','oldest','empty','permissions','mtime','crc32','gzip','gunzip','compare','basename','dirname','extension','realpath'],
'net':['ip-info','cidr-info','cidr-contains','cidr-hosts','url-parse','url-normalize','dns-a','dns-aaaa','dns-reverse','resolve','port-check','tcp-ping','http-head','http-get','http-status','http-headers','tls-cert','tls-expiry','host-port-parse','ipv4-to-int','int-to-ipv4','mac-normalize','user-agent','query-encode','query-decode'],
'time':['now-utc','now-local','epoch-now','epoch-to-iso','iso-to-epoch','rfc3339-normalize','duration-seconds','seconds-human','date-add-days','date-diff','weekday','month-days','leap-year','timezone-list','timezone-convert','unix-ms-now','unix-ms-to-iso','iso-to-unix-ms','relative-age','sleep-until'],
'id':['uuid4','uuid1','uuid3-dns','uuid5-dns','token-hex','token-url','token-base64','nanoid-like','random-int','random-choice','random-bytes','ulid-like','snowflake-like','hash-id','slug-id'],
'binary':['zip-list','zip-extract','zip-test','tar-list','gzip-info','elf-header','png-info','jpeg-info','pdf-info','sqlite-tables','sqlite-schema','strings','hex','base64','apk-list','apk-native-libs','apk-dex-list','apk-assets','apk-signature-files','zip-ratio'],
'system':['platform','cpu-count','loadavg','meminfo','cpuinfo','disk-usage','env','env-json','path','which','processes','uptime','kernel','hostname','cwd'],
'dev':['semver-compare','semver-sort','regex-test','regex-groups','diff-unified','json-escape','shell-quote','int-base','bytes-human','bytes-parse'],
}

SECTIONS={'hash':'utils','hmac':'utils','encode':'utils','decode':'utils','text':'utils','json':'utils','csv':'utils','file':'utils','net':'net','time':'utils','id':'utils','binary':'devel','system':'admin','dev':'devel'}

DESCS={
'hash':'streaming cryptographic digest utility','hmac':'keyed HMAC digest utility','encode':'data encoding utility','decode':'data decoding utility','text':'text processing utility','json':'JSON transformation and inspection utility','csv':'CSV analysis and transformation utility','file':'filesystem analysis utility','net':'network and protocol diagnostic utility','time':'time and date conversion utility','id':'identifier and secure token generation utility','binary':'binary/archive/Android inspection utility','system':'system and process diagnostics utility','dev':'developer conversion and debugging utility'}

def tools():
    out=[]
    for fam,modes in FAMILIES.items():
        for mode in modes: out.append((f'ocean-pwr-{fam}-{mode}',fam,mode))
    assert len(out)==249, len(out)
    assert len({x[0] for x in out})==249
    return out

def run(cmd,**kw):
    r=subprocess.run(cmd,text=True,capture_output=True,**kw)
    if r.returncode: raise SystemExit(f"command failed: {' '.join(cmd)}\n{r.stdout}\n{r.stderr}")
    return r

def normalize(root:Path):
    for p in root.rglob('*'):
        try:
            p.chmod(0o755 if (p.is_dir() or '/bin/' in str(p)) else 0o644)
            os.utime(p,(0,0),follow_symlinks=False)
        except FileNotFoundError: pass

def hashes(path:Path):
    d=path.read_bytes(); return {'size':len(d),'md5':hashlib.md5(d).hexdigest(),'sha1':hashlib.sha1(d).hexdigest(),'sha256':hashlib.sha256(d).hexdigest()}

def build_deb(pkg,desc,section,depends,files,outpath):
    with tempfile.TemporaryDirectory(prefix='ocean-power-') as td:
        root=Path(td); (root/'DEBIAN').mkdir()
        for rel,(content,mode) in files.items():
            p=root/rel.lstrip('/'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(content,encoding='utf-8'); p.chmod(mode)
        (root/'DEBIAN/control').write_text(
            f'Package: {pkg}\nVersion: {VERSION}\nArchitecture: all\nMaintainer: OceanStudio Packaging Team <maintainer@ocean.studio>\nSection: {section}\nPriority: optional\nDepends: {depends}\nDescription: {desc}\n Ocean-native utility for the OceanStudio Android terminal.\n',encoding='utf-8')
        normalize(root)
        run(['dpkg-deb','--root-owner-group','-Zxz','--build',str(root),str(outpath)])

def stanza(pkg,desc,section,path):
    h=hashes(path)
    return f'''Package: {pkg}
Version: {VERSION}
Architecture: all
Maintainer: OceanStudio Packaging Team <maintainer@ocean.studio>
Depends: {'python' if pkg==CORE_PACKAGE else 'ocean-power-core, python'}
Filename: pool/main/{path.name}
Size: {h['size']}
MD5sum: {h['md5']}
SHA1: {h['sha1']}
SHA256: {h['sha256']}
Section: {section}
Priority: optional
Description: {desc}
 Ocean-native utility for the OceanStudio Android terminal.'''

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--source',required=True); ap.add_argument('--output',required=True); ap.add_argument('--existing-packages',required=True); a=ap.parse_args()
    src=Path(a.source); out=Path(a.output); existing=Path(a.existing_packages)
    shutil.rmtree(out,ignore_errors=True); pool=out/'pool/main'; pool.mkdir(parents=True)
    existing_text=existing.read_text(encoding='utf-8',errors='replace')
    existing_names=set(re.findall(r'^Package:\s*(\S+)',existing_text,re.M))
    candidates=[CORE_PACKAGE]+[x[0] for x in tools()]
    collisions=sorted(existing_names.intersection(candidates))
    if collisions: raise SystemExit(f'package name collision(s): {collisions}')
    if len(candidates)!=250 or len(set(candidates))!=250: raise SystemExit('candidate count/uniqueness failure')

    core_source=(src/'ocean_power_core.py').read_text(encoding='utf-8')
    core_deb=pool/f'{CORE_PACKAGE}_{VERSION}_all.deb'
    build_deb(CORE_PACKAGE,'Shared runtime for 249 Ocean Power utilities','utils','python',{
        f'{PREFIX}/lib/ocean-power/ocean_power_core.py':(core_source,0o644),
        f'{PREFIX}/bin/ocean-power':(f'''#!{PREFIX}/bin/bash
exec {PREFIX}/bin/python {PREFIX}/lib/ocean-power/ocean_power_core.py "$@"
''',0o755),
    },core_deb)

    entries=[]; stanzas=[stanza(CORE_PACKAGE,'Shared runtime for 249 Ocean Power utilities','utils',core_deb)]
    hc=hashes(core_deb); entries.append({'package':CORE_PACKAGE,'family':'core','artifact':core_deb.name,'sha256':hc['sha256'],'size':hc['size']})
    for pkg,fam,mode in tools():
        desc=f'{DESCS[fam]}: {mode.replace("-"," ")}'
        deb=pool/f'{pkg}_{VERSION}_all.deb'
        wrapper=f'''#!{PREFIX}/bin/bash
exec {PREFIX}/bin/python {PREFIX}/lib/ocean-power/ocean_power_core.py {pkg} "$@"
'''
        build_deb(pkg,desc,SECTIONS[fam],'ocean-power-core, python',{f'{PREFIX}/bin/{pkg}':(wrapper,0o755)},deb)
        h=hashes(deb); entries.append({'package':pkg,'family':fam,'mode':mode,'artifact':deb.name,'sha256':h['sha256'],'size':h['size']}); stanzas.append(stanza(pkg,desc,SECTIONS[fam],deb))

    (out/'Packages.new').write_text('\n\n'.join(stanzas)+'\n',encoding='utf-8')
    (out/'provenance.json').write_text(json.dumps({'schemaVersion':1,'suite':'power-suite','sourceType':'Ocean-native original source','target':'OceanStudio Android terminal','prefix':PREFIX,'packageCount':250,'uniquePackageCount':250,'corePackage':CORE_PACKAGE,'packages':entries},indent=2)+'\n',encoding='utf-8')
    assert len(list(pool.glob('*.deb')))==250
    assert len(re.findall(r'^Package:',(out/'Packages.new').read_text(),re.M))==250
    for deb in pool.glob('*.deb'): run(['dpkg-deb','--info',str(deb)])
    print('Built 250 unique Ocean Power packages with zero collisions.')
if __name__=='__main__': main()
