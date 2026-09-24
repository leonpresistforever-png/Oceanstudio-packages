#!/usr/bin/env python3
"""Build Caddy/strace from official upstream commits for the Ocean prefix.

No existing .deb or foreign distribution binary is used as a build input.
Only packages whose actual ARM executable passes the stated smoke tests enter
staging. This does not certify every feature or execution on an Android phone.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
PREFIX = '/data/data/studio.ocean.app/files/usr'
SOURCES = {
    'caddy': ('https://github.com/caddyserver/caddy.git', 'e2eee6a7fce366321294c9c2a79f3146891dcbdf'),
    'strace': ('https://github.com/strace/strace.git', '195ac8ddbf6fad16ff1ff125b0feb725b6c46dcf'),
}
spec = importlib.util.spec_from_file_location('upstream', ROOT/'scripts/build-upstream-repairs.py')
upstream = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upstream)
upstream.SOURCES.update(SOURCES)
run, capture = upstream.run, upstream.capture


def json_stream(text):
    decoder, objects, pos = json.JSONDecoder(), [], 0
    while pos < len(text):
        while pos < len(text) and text[pos].isspace(): pos += 1
        if pos == len(text): break
        obj, pos = decoder.raw_decode(text, pos)
        objects.append(obj)
    return objects


def caddy(src, work, stage, receipts):
    env = dict(os.environ, GOOS='linux', GOARCH='arm64', CGO_ENABLED='0',
               GOMAXPROCS='2', SOURCE_DATE_EPOCH='0')
    run(['go', 'mod', 'download', 'all'], cwd=src, env=env)
    run(['go', 'mod', 'verify'], cwd=src, env=env)
    prefix = stage/PREFIX.lstrip('/')
    binary = prefix/'bin/caddy'; binary.parent.mkdir(parents=True)
    run(['go', 'build', '-mod=readonly', '-trimpath', '-buildvcs=false',
         '-tags=netgo,osusergo', '-ldflags=-s -w -buildid= -X github.com/caddyserver/caddy/v2.CustomVersion=v2.11.4-ocean.1',
         '-o', binary, './cmd/caddy'], cwd=src, env=env)
    # Caddy is pure Go here: use a static Linux/AArch64 executable with no libc
    # dependency. Android uses the Linux kernel ABI, so this avoids requiring a
    # host copy of Android's /system/bin/linker64 merely to execute CI tests.
    elf = subprocess.check_output(['readelf','-lW','-dW',binary],text=True)
    if 'Requesting program interpreter' in elf or '(NEEDED)' in elf:
        raise RuntimeError('Caddy candidate unexpectedly depends on a userspace libc/linker')
    version, err = capture(['qemu-aarch64',binary,'version'],env=env)
    if b'v2.11.4' not in version+err:
        raise RuntimeError('Actual Android ARM Caddy version did not match the source')
    doc = prefix/'share/doc/caddy'; doc.mkdir(parents=True)
    # License the modules actually linked for this target. `go list -m all`
    # includes upstream lint/test tools that are not shipped in the executable.
    packages = json_stream(subprocess.check_output(
        ['go','list','-deps','-json','-tags=netgo,osusergo','./cmd/caddy'],cwd=src,env=env,text=True))
    modules = list({r['Module']['Path']:r['Module'] for r in packages if 'Module' in r}.values())
    missing = []
    for module in modules:
        location = module.get('Dir')
        if not location:
            missing.append(module['Path']); continue
        copied = []
        for source in Path(location).iterdir():
            if source.name.upper().startswith(('LICENSE','COPYING','NOTICE','COPYRIGHT')):
                destination = doc/'licenses'/module['Path']/source.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir(): shutil.copytree(source,destination,dirs_exist_ok=True)
                else: shutil.copy2(source,destination)
                copied.append(source.name)
        if not copied: missing.append(module['Path'])
    if missing:
        raise RuntimeError('Dependency license collection is incomplete: '+repr(missing))
    goroot = subprocess.check_output(['go','env','GOROOT'],text=True).strip()
    shutil.copy2(Path(goroot)/'LICENSE', doc/'Go-LICENSE')
    (doc/'modules.json').write_text(json.dumps([
        {k:v for k,v in m.items() if k in ('Path','Version','Sum','GoModSum')}
        for m in modules],indent=2)+'\n')
    receipts['toolchain'] = subprocess.check_output(['go','version'],text=True).strip()
    content = work/'served'; content.mkdir()
    expected = b'Ocean official-source Caddy HTTP smoke test\n'
    (content/'proof.txt').write_bytes(expected)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    log = work/'caddy.log'
    with log.open('wb') as output:
        server = subprocess.Popen(['qemu-aarch64',str(binary),'file-server','--listen',f'127.0.0.1:{port}',
                                   '--root',str(content)],env=env,stdout=output,stderr=output)
        try:
            deadline=time.monotonic()+30
            while True:
                if server.poll() is not None:
                    raise RuntimeError('Caddy exited during HTTP smoke test: '+log.read_text()[-3000:])
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/proof.txt',timeout=1) as response:
                        actual=response.read()
                    if actual!=expected: raise RuntimeError('Caddy served different data')
                    break
                except (urllib.error.URLError,TimeoutError):
                    if time.monotonic()>=deadline: raise
                    time.sleep(.1)
        finally:
            server.terminate()
            try: server.wait(timeout=10)
            except subprocess.TimeoutExpired: server.kill();server.wait()
    return {'qemuArm64Binary':(version+err).decode().strip(),'runtimeAbi':'linux-arm64-static-purego-no-libc',
            'loopbackHttpRoundTrip':True,'androidPhone':False,'tlsAndDnsIntegration':'not tested'}


def strace(src, work, stage, ndk, receipts):
    if not ndk or 'Pkg.Revision = 27.0.12077973' not in (ndk/'source.properties').read_text():
        raise RuntimeError('Official Android NDK r27 is required')
    tools=ndk/'toolchains/llvm/prebuilt/linux-x86_64/bin'
    cc=tools/'aarch64-linux-android28-clang'
    tls=work/'ocean-tls.o'
    run([cc,'-c',ROOT/'scripts/android-static-tls.S','-o',tls])
    # The pinned official tag provides autotools' version metadata in a shallow checkout.
    run(['git','tag','v7.2',SOURCES['strace'][1]],cwd=src)
    # Upstream intentionally probes a kernel ABI with a null mask. Bionic's
    # sched_getaffinity contract rejects null arguments, so invoke that same
    # documented kernel probe directly without violating the libc contract.
    affinity=src/'src/affinity.c'
    original=affinity.read_text()
    probe='sched_getaffinity(0, cpuset_size, NULL)'
    if original.count(probe)!=1:raise RuntimeError('Upstream affinity probe changed')
    patched=original.replace('#include <sched.h>','#include <sched.h>\n#include <sys/syscall.h>\n#include <unistd.h>')
    patched=patched.replace(probe,'syscall(SYS_sched_getaffinity, 0, cpuset_size, NULL)')
    affinity.write_text(patched)
    # Bionic's <arpa/inet.h> expects in_addr_t from <netinet/in.h>. Upstream
    # currently includes them in the opposite order, which glibc tolerates.
    msghdr=src/'src/msghdr.c'
    ms_original=msghdr.read_text()
    ms_lines=ms_original.splitlines()
    try:
        arpa_index=ms_lines.index('#include <arpa/inet.h>')
        net_index=ms_lines.index('#include <netinet/in.h>')
    except ValueError as exc:
        raise RuntimeError('Upstream msghdr network includes changed') from exc
    if net_index != arpa_index + 1:
        raise RuntimeError('Upstream msghdr network include layout changed')
    # strace's bundled Linux UAPI headers can suppress the Bionic typedef
    # that arpa/inet.h expects. Define the ABI-identical 32-bit type locally
    # and keep Bionic netinet/in.h ahead of arpa/inet.h.
    ms_lines[arpa_index:net_index+1]=[
        '#include <stdint.h>',
        'typedef uint32_t in_addr_t;',
        '#include <netinet/in.h>',
        '#include <arpa/inet.h>',
    ]
    ms_patched='\n'.join(ms_lines)+'\n'
    msghdr.write_text(ms_patched)
    # The same bundled-UAPI/Bionic collision can occur in any translation unit
    # that includes arpa/inet.h, not only msghdr.c. Patch every such upstream
    # source deterministically before configure. Files already carrying the
    # compatibility typedef (including msghdr.c above) are left untouched.
    network_compat_patches=[]
    for network_file in sorted((src/'src').rglob('*')):
        if not network_file.is_file() or network_file.suffix not in ('.c','.h'):
            continue
        try:
            network_before=network_file.read_text()
        except UnicodeDecodeError:
            continue
        if '#include <arpa/inet.h>' not in network_before or 'typedef uint32_t in_addr_t;' in network_before:
            continue
        network_after=network_before.replace(
            '#include <arpa/inet.h>',
            '#include <stdint.h>\ntypedef uint32_t in_addr_t;\n#include <arpa/inet.h>',
            1)
        network_file.write_text(network_after)
        network_compat_patches.append({
            'path':network_file.relative_to(src).as_posix(),
            'reason':'Restore Bionic in_addr_t when strace bundled Linux UAPI headers suppress the libc typedef',
            'beforeSha256':hashlib.sha256(network_before.encode()).hexdigest(),
            'afterSha256':hashlib.sha256(network_after.encode()).hexdigest()})
    receipts['oceanPatches']=[{'path':'src/affinity.c',
        'reason':'Use the kernel affinity-size probe without passing NULL to Bionic nonnull API',
        'beforeSha256':hashlib.sha256(original.encode()).hexdigest(),
        'afterSha256':hashlib.sha256(patched.encode()).hexdigest()},
        {'path':'src/msghdr.c','reason':'Restore Bionic in_addr_t when strace bundled Linux UAPI headers suppress the libc typedef',
        'beforeSha256':hashlib.sha256(ms_original.encode()).hexdigest(),
        'afterSha256':hashlib.sha256(ms_patched.encode()).hexdigest()}] + network_compat_patches
    run(['./bootstrap'],cwd=src)
    env=dict(os.environ,CC=str(cc),AR=str(tools/'llvm-ar'),RANLIB=str(tools/'llvm-ranlib'),
             CFLAGS='-O2 -ffile-prefix-map='+str(work)+'=/usr/src/ocean',
             LDFLAGS='-static -Wl,-z,max-page-size=16384 '+str(tls),SOURCE_DATE_EPOCH='0')
    run(['./configure','--host=aarch64-linux-android','--prefix='+PREFIX,
         '--enable-mpers=no','--enable-stacktrace=no'],cwd=src,env=env)
    run(['make','-j2'],cwd=src,env=env)
    run(['make','install','DESTDIR='+str(stage)],cwd=src,env=env)
    prefix=stage/PREFIX.lstrip('/')
    merge=prefix/'bin/strace-log-merge'
    if merge.exists():
        text=merge.read_text(); lines=text.splitlines(keepends=True)
        if not lines or lines[0].strip()!='#!/bin/sh':
            raise RuntimeError('Unexpected upstream log-merge interpreter')
        lines[0]='#!'+PREFIX+'/bin/sh\n';merge.write_text(''.join(lines))
    doc=prefix/'share/doc/strace';doc.mkdir(parents=True,exist_ok=True)
    for filename in ('COPYING','CREDITS','AUTHORS','LGPL-2.1-or-later'):
        if (src/filename).is_file():shutil.copy2(src/filename,doc/filename)
    version,err=capture(['qemu-aarch64',prefix/'bin/strace','--version'])
    if b'7.2' not in version+err:raise RuntimeError('Actual ARM strace version mismatch')
    receipts['toolchain']='Android NDK 27.0.12077973; API 28; static Bionic'
    return {'qemuAndroidBinary':(version+err).decode().strip(),
            'ptraceOnAndroidPhone':False,'limitation':'QEMU user mode cannot exercise ptrace',
            'configureOptions':['--enable-mpers=no','--enable-stacktrace=no']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('package',choices=SOURCES)
    p.add_argument('--ndk',type=Path)
    p.add_argument('--output',type=Path)
    a=p.parse_args();name=a.package
    output=a.output or ROOT/'staging/official-native-repairs'/name
    output.mkdir(parents=True,exist_ok=True)
    receipts={}
    with tempfile.TemporaryDirectory(prefix='ocean-native-source-') as tmp:
        work=Path(tmp);src=upstream.source(name,work,receipts);stage=work/'stage'
        try:
            tests=caddy(src,work,stage,receipts) if name=='caddy' else strace(src,work,stage,a.ndk,receipts)
            record=upstream.package(name,{'caddy':'2.11.4-1+ocean1','strace':'7.2-1+ocean1'}[name],
                stage,output,'Official-source '+name+' built for the Ocean native Android prefix',receipts,tests)
            # Read every payload/control byte, including binary embedded prefixes.
            from forensic_repository import scan_tar
            archive=output/'pool/main'/record['artifact']
            payload=list(scan_tar(archive))+list(scan_tar(archive,control=True))
            hard={'foreign-app-prefix','foreign-repository','foreign-runtime-variable',
                  'foreign-link-target','unsafe-archive-path','confirmed-ready-stub','invalid-elf-header'}
            defects=[{'path':r['path'],**f} for r in payload for f in r.get('findings',[]) if f['kind'] in hard]
            if defects:raise RuntimeError('Full archive audit failed: '+repr(defects))
            record['completePayloadFilesRead']=len(payload)
        except Exception:
            diagnostics=ROOT/'build-diagnostics'/('official-'+name)
            diagnostics.mkdir(parents=True,exist_ok=True)
            for filename in ('config.log','config.status'):
                if (src/filename).is_file():shutil.copy2(src/filename,diagnostics/filename)
            for binary in stage.glob('**/bin/'+name):shutil.copy2(binary,diagnostics/(name+'-candidate'))
            raise
    (output/'Packages.repaired').write_text(record.pop('index')+'\n')
    (output/'provenance.json').write_text(json.dumps(record,indent=2)+'\n')
    print('Official-source candidate staged:',name,'; live APT unchanged')


if __name__=='__main__': main()
