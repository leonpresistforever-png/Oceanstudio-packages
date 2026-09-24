#!/usr/bin/env python3
"""Move the Ocean-owned distro script out of the old Ocean tools shell package.

This is an ownership migration of existing Ocean shell sources, not an upstream
native rebuild or a certification of all preserved utilities. No ELF is reused.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'data/data/studio.ocean.app/files/usr'
VERSION = '1.1.0+ocean1'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, default=ROOT/'staging/ocean-distro-repair')
    args = ap.parse_args()
    original = ROOT/'apt/pool/main/ocean-tools_1.1.0_all.deb'
    # Pin the indexed legacy input; never silently migrate unrelated bytes.
    import sys
    sys.path.insert(0, str(ROOT/'scripts'))
    from index_all_staged import fields
    from forensic_repository import scan_tar
    original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    control_tar = subprocess.check_output(['dpkg-deb', '--ctrl-tarfile', str(original)])
    with tarfile.open(fileobj=io.BytesIO(control_tar)) as tar:
        member = next(m for m in tar if m.name.removeprefix('./') == 'control')
        control = fields(tar.extractfile(member).read().decode())
    if (control['Package'], control['Version'], control['Architecture']) != ('ocean-tools', '1.1.0', 'all'):
        raise SystemExit('Unexpected Ocean tools source archive identity')
    if original_hash != EXPECTED_SOURCE_SHA256:
        raise SystemExit('Ocean tools source archive hash changed')
    data = subprocess.check_output(['dpkg-deb', '--fsys-tarfile', str(original)])
    preserved = {}
    manager = PREFIX+'/bin/ocean-distro'
    with tempfile.TemporaryDirectory(prefix='ocean-tools-ownership-') as td:
        stage = Path(td)
        removed = []
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            for member in tar:
                if member.isdir():
                    continue
                name = member.name.removeprefix('./')
                if not member.isfile() or not name.startswith(PREFIX+'/bin/') or '..' in PurePosixPath(name).parts:
                    raise SystemExit('Unexpected non-script Ocean tools payload: '+name)
                source = tar.extractfile(member).read()
                if not source.startswith(b'#!') or b'\x00' in source:
                    raise SystemExit('Expected an Ocean shell source file: '+name)
                if name == manager:
                    removed.append(name)
                    continue
                dest = stage/name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(source)
                dest.chmod(member.mode & 0o777)
                preserved[name] = hashlib.sha256(source).hexdigest()
        if removed != [manager] or len(preserved) != 25:
            raise SystemExit('Unexpected Ocean tools file inventory')
        control['Version'] = VERSION
        control['Depends'] += ', ocean-distro (>= 1.0.1-3)'
        for field in ('Provides', 'Replaces', 'Conflicts'):
            if control.get(field) == 'ocean-tools':
                del control[field]
        (stage/'DEBIAN').mkdir()
        (stage/'DEBIAN/control').write_text(''.join(k+': '+v+'\n' for k,v in control.items()))
        for path in stage.rglob('*'):
            if path.is_dir():
                path.chmod(0o755)
            os.utime(path, (0, 0), follow_symlinks=False)
        stage.chmod(0o755)
        os.utime(stage, (0, 0))
        pool = args.output/'pool/main'
        pool.mkdir(parents=True, exist_ok=True)
        deb = pool/f'ocean-tools_{VERSION}_all.deb'
        subprocess.run(['dpkg-deb', '--root-owner-group', '-Zxz', '-z6', '--build', str(stage), str(deb)], check=True)
    hard = {'foreign-app-prefix', 'foreign-repository', 'foreign-runtime-variable',
            'foreign-link-target', 'unsafe-archive-path', 'confirmed-ready-stub',
            'invalid-elf-header', 'elf-reader-error'}
    rows = list(scan_tar(deb)) + list(scan_tar(deb, control=True))
    bad = [f for row in rows for f in row.get('findings', []) if f['kind'] in hard]
    if bad:
        raise SystemExit('Preserved Ocean scripts need further repair: '+repr(bad))
    report = {'sourceArchive': str(original.relative_to(ROOT)), 'sourceSha256': original_hash,
              'package': 'ocean-tools', 'version': VERSION,
              'sha256': hashlib.sha256(deb.read_bytes()).hexdigest(),
              'preservedScriptSha256': preserved, 'movedToOceanDistro': removed,
              'scope': 'Ownership migration; existing Ocean script bytes retained.',
              'androidExecutionTested': False}
    (args.output/'ocean-tools-ownership.json').write_text(json.dumps(report, indent=2)+'\n')


EXPECTED_SOURCE_SHA256 = '46d362be243df5ae7af5397ed2946c8b749c739db5cef285d039cd8c2de668ab'

if __name__ == '__main__':
    main()
