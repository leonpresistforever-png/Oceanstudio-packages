#!/usr/bin/env python3
"""Replay the real JDK/JRE data archives against disposable dpkg state.

Only test copies are made, with control fields retained and maintainer scripts
omitted so no Android script or binary executes on the host. Data archive bytes
are copied unchanged. Test copies are never published or called repaired packages.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

from index_all_staged import fields, stanzas

ROOT = Path(__file__).resolve().parents[1]
NAMES = ['openjdk-21-jre-headless', 'openjdk-21']


def replay(root, output):
    records = {r['Package']: r for r in map(fields, stanzas(
        (root / 'apt/dists/stable/main/binary-aarch64/Packages').read_text()))}
    report = {'androidRuntimeTested': False, 'originalMaintainerScriptsExecuted': False,
        'purpose': 'Isolated dpkg unpack reproduction with unchanged data archives', 'packages': []}
    with tempfile.TemporaryDirectory(prefix='ocean-jdk-replay-') as tmp:
        base = Path(tmp)
        guest = base / 'root'
        (guest / 'var/lib/dpkg').mkdir(parents=True)
        (guest / 'var/lib/dpkg/status').write_text('')
        for name in NAMES:
            row = records[name]
            original = root / 'apt' / row['Filename']
            digest = hashlib.sha256(original.read_bytes()).hexdigest()
            if digest != row['SHA256'] or original.stat().st_size != int(row['Size']):
                raise ValueError('Original .deb fails current-index size/hash comparison: ' + name)
            work = base / name
            work.mkdir()
            control = subprocess.check_output(['dpkg-deb', '-f', str(original)])
            control_fields = fields(control.decode())
            if control_fields['Package'] != name:
                raise ValueError('Original package identity mismatch')
            raw_control = io.BytesIO()
            with tarfile.open(fileobj=raw_control, mode='w') as tf:
                member = tarfile.TarInfo('./control')
                member.size, member.mode = len(control), 0o644
                tf.addfile(member, io.BytesIO(control))
            (work / 'control.tar.gz').write_bytes(gzip.compress(raw_control.getvalue(), mtime=0))
            (work / 'debian-binary').write_bytes(b'2.0\n')
            members = subprocess.check_output(['ar', 't', str(original)], text=True).splitlines()
            data = [m for m in members if m.startswith('data.tar')]
            if len(data) != 1 or '/' in data[0]:
                raise ValueError('Ambiguous original data archive')
            with (work / data[0]).open('wb') as f:
                subprocess.run(['ar', 'p', str(original), data[0]], stdout=f, check=True)
            candidate = work / 'test-only-no-maintainer-scripts.deb'
            subprocess.run(['ar', 'rcD', str(candidate), 'debian-binary', 'control.tar.gz', data[0]],
                cwd=work, check=True, capture_output=True)
            result = subprocess.run(['dpkg', '--force-not-root', '--force-architecture',
                '--root=' + str(guest), '--unpack', str(candidate)], capture_output=True, text=True)
            report['packages'].append({'package': name, 'version': row['Version'],
                'originalSha256': digest, 'originalBytes': original.stat().st_size,
                'payloadArchiveSha256': hashlib.sha256((work / data[0]).read_bytes()).hexdigest(),
                'replayExitCode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
            if name == NAMES[0] and result.returncode:
                raise ValueError('First archive did not unpack: ' + result.stderr)
        last = report['packages'][-1]
        report['overwriteFailureReproduced'] = last['replayExitCode'] != 0 and 'trying to overwrite' in last['stderr']
        if not report['overwriteFailureReproduced']:
            raise ValueError('Expected overlap not reproduced: ' + last['stderr'])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = replay(a.root, a.output)
    print(json.dumps(result, indent=2))
