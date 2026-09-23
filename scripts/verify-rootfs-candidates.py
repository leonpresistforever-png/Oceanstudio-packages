#!/usr/bin/env python3
"""Download every configured distro image and verify bytes, identity and ARM shell.

This only records evidence. It never changes a checksum to make an image pass,
installs a guest on a user's device, or aliases one distribution to another.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import tarfile
import tempfile
import urllib.request

IDS = {'arch': ('archarm','arch'), 'alma': ('almalinux',), 'opensuse': ('opensuse-tumbleweed',)}


def inspect(name, entry):
    report = {'distro': name, 'url': entry['url'], 'expectedSha256': entry.get('sha256'),
              'androidDeviceTested': False, 'status': 'failed'}
    try:
        url = entry['url']
        if not url.startswith('https://') or 'termux' in url.lower():
            raise ValueError('Source is not an accepted official HTTPS rootfs candidate')
        if 'linuxcontainers.org' in url:
            raise ValueError('Third-party image; an official distribution source is still needed')
        with tempfile.TemporaryDirectory(prefix='ocean-rootfs-check-') as tmp:
            archive = Path(tmp)/'image.tar'
            request = urllib.request.Request(url, headers={'User-Agent':'OceanStudio-rootfs-audit/1'})
            h, size = hashlib.sha256(), 0
            with urllib.request.urlopen(request, timeout=60) as response, archive.open('wb') as out:
                if not response.url.startswith('https://') or 'termux' in response.url.lower():
                    raise ValueError('Unaccepted redirect: '+response.url)
                report['finalUrl'] = response.url
                expected_size = int(response.headers.get('Content-Length', '0'))
                while chunk := response.read(1048576):
                    out.write(chunk); h.update(chunk); size += len(chunk)
                    if size > 2*1024**3: raise ValueError('Rootfs exceeds 2 GiB audit limit')
            report.update(bytes=size, sha256=h.hexdigest())
            if expected_size and expected_size != size: raise ValueError('Partial HTTP response')
            if h.hexdigest() != entry.get('sha256'):
                raise ValueError('Missing or mismatched pinned checksum; do not replace it without upstream verification')
            names, release, machines = set(), {}, set()
            with tarfile.open(archive) as tf:
                for m in tf:
                    p = PurePosixPath(m.name)
                    if p.is_absolute() or '..' in p.parts: raise ValueError('Unsafe archive member: '+m.name)
                    names.add(p.as_posix())
                    if m.isfile():
                        with tf.extractfile(m) as stream:
                            head = stream.read(8192)
                        if p.as_posix() in ('etc/os-release','usr/lib/os-release'):
                            for line in head.decode().splitlines():
                                if '=' in line:
                                    key,value=line.split('=',1);release[key]=value.strip('"\'')
                        if head.startswith(b'\x7fELF') and len(head)>=20:
                            machines.add(struct.unpack(('<' if head[5]==1 else '>')+'H',head[18:20])[0])
            report.update(osRelease=release, elfMachines=sorted(machines))
            if release.get('ID') not in IDS.get(name,(name,)):
                raise ValueError('Wrong distro identity or not a flat rootfs archive')
            if 183 not in machines: raise ValueError('No actual AArch64 ELF payload')
            guest = Path(tmp)/'guest'; guest.mkdir()
            subprocess.run(['tar','--extract','--file',str(archive),'--directory',str(guest),
                            '--no-same-owner','--no-same-permissions'], check=True, capture_output=True)
            shell = guest / entry.get('shell','/bin/sh').lstrip('/')
            if not shell.resolve().is_relative_to(guest.resolve()):
                raise ValueError('Shell path needs guest-aware absolute symlink resolution')
            result = subprocess.run(['qemu-aarch64','-L',str(guest),str(shell),'-c',
                                     'printf OCEAN_ROOTFS_EXEC_OK'],capture_output=True,text=True,timeout=30)
            report['armShellResult']={'exitCode':result.returncode,'stdout':result.stdout,'stderr':result.stderr[:2000]}
            if result.returncode or result.stdout!='OCEAN_ROOTFS_EXEC_OK':
                raise ValueError('Actual ARM guest shell did not execute successfully')
            report['status']='checksum-identity-arm-shell-passed'
    except Exception as exc:
        report['error']=str(exc)
    print(json.dumps(report),flush=True)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--registry',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();entries=json.loads(args.registry.read_text())
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda item:inspect(*item),entries.items()))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'distros':results,'allPassed':all(r['status']=='checksum-identity-arm-shell-passed' for r in results),
        'physicalAndroidTested':False,'sourceRegistrySha256':hashlib.sha256(args.registry.read_bytes()).hexdigest()},indent=2)+'\n')


if __name__=='__main__':main()
