#!/usr/bin/env python3
"""Repair Ocean tool ownership without removing commands or changing native bytes.

Inputs are pinned in ownership-plan.json. All reverse exact dependencies are
revised together. Except for ocean-tools' script relocation, the compressed data
member is copied byte for byte; this is NOT an upstream-source rebuild.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
import copy
import hashlib
import io
import json
import lzma
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

from index_all_staged import fields

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'data/data/studio.ocean.app/files/usr'
RELATIONS = ('Depends', 'Pre-Depends', 'Recommends', 'Suggests', 'Enhances')
COMMANDS = ('ocean-api', 'ocean-change-repo', 'ocean-clipboard-get',
            'ocean-clipboard-set', 'ocean-hello', 'ocean-open', 'ocean-share',
            'ocean-toast', 'ocean-vibrate')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def ar_read(data):
    if not data.startswith(b'!<arch>\n'):
        raise ValueError('Not a Debian ar archive')
    members, offset = [], 8
    while offset < len(data):
        header = data[offset:offset + 60]
        if len(header) != 60 or header[58:] != b'`\n':
            raise ValueError('Truncated ar header')
        name = header[:16].decode('ascii').strip().rstrip('/')
        size = int(header[48:58])
        offset += 60
        body = data[offset:offset + size]
        if len(body) != size or not re.fullmatch(r'[a-zA-Z0-9._+-]+', name):
            raise ValueError('Invalid ar member')
        members.append((name, body))
        offset += size + size % 2
    if len(members) != 3 or members[0] != ('debian-binary', b'2.0\n'):
        raise ValueError('Unexpected Debian archive members')
    if not members[1][0].startswith('control.tar') or not members[2][0].startswith('data.tar'):
        raise ValueError('Invalid Debian member order')
    return members


def ar_write(members):
    out = bytearray(b'!<arch>\n')
    for name, data in members:
        header = f'{name + "/":<16}{0:<12}{0:<6}{0:<6}{"100644":<8}{len(data):<10}`\n'
        if len(header) != 60:
            raise ValueError('ar member header overflow')
        out.extend(header.encode('ascii'))
        out.extend(data)
        if len(data) % 2:
            out.extend(b'\n')
    return bytes(out)


def tar_entries(data):
    if data.startswith(b'\x28\xb5\x2f\xfd'):
        data = subprocess.check_output(['zstd', '-d', '-q', '-c'], input=data)
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as archive:
        return [(copy.copy(m), archive.extractfile(m).read() if m.isfile() else None)
                for m in archive]


def tar_bytes(entries):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w', format=tarfile.PAX_FORMAT) as archive:
        for member, body in entries:
            if body is not None:
                member.size = len(body)
            archive.addfile(member, io.BytesIO(body) if body is not None else None)
    return lzma.compress(stream.getvalue(), preset=6)


def revise_relations(control, plan):
    for field in RELATIONS:
        if field not in control:
            continue
        for row in plan['packages']:
            # Only revise actual equality constraints, never arbitrary text or
            # minimum versions. This retains the precise graph of the snapshot.
            pattern = (r'(?<![A-Za-z0-9+.-])(' + re.escape(row['name']) +
                       r'(?::[a-z0-9-]+)?\s*\(=\s*)' +
                       re.escape(row['oldVersion']) + r'(\s*\))')
            control[field] = re.sub(pattern, lambda m: m[1] + row['newVersion'] + m[2], control[field])


def repair(data, row, plan):
    members = ar_read(data)
    control_entries = tar_entries(members[1][1])
    controls = [(m, b) for m, b in control_entries if m.name.removeprefix('./') == 'control']
    if len(controls) != 1 or controls[0][1] is None:
        raise ValueError('Expected one regular control file')
    control = fields(controls[0][1].decode())
    expected = (row['name'], row['oldVersion'], row['architecture'])
    if tuple(control[k] for k in ('Package', 'Version', 'Architecture')) != expected:
        raise ValueError('Pinned control identity mismatch')
    control['Version'] = row['newVersion']
    revise_relations(control, plan)
    report = dict(package=row['name'], oldVersion=row['oldVersion'], version=row['newVersion'],
                  sourceSha256=digest(data), dataMemberSha256Before=digest(members[2][1]))
    if row['name'] == 'ocean-tools':
        # Each public command has exactly one owner. The original Ocean scripts
        # remain available explicitly, so differing device-tool behavior is not
        # silently thrown away during this packaging migration.
        control.pop('Conflicts', None)
        control.pop('Replaces', None)
        versions = {r['name']: r['newVersion'] for r in plan['packages']}
        control['Depends'] += ', ' + ', '.join(n + ' (>= ' + versions[n] + ')' for n in plan['components'])
        entries = tar_entries(members[2][1])
        preserved = []
        for member, body in entries:
            name = member.name.removeprefix('./')
            if member.isdir():
                continue
            if not member.isfile() or not name.startswith(PREFIX + '/bin/') or not body.startswith(b'#!'):
                raise ValueError('Unexpected Ocean tools payload: ' + name)
            command = name.rsplit('/', 1)[-1]
            if command in COMMANDS:
                member.name = './' + PREFIX + '/libexec/ocean-tools/previous-cli/' + command
            preserved.append(dict(previousPath=name, path=member.name.removeprefix('./'), sha256=digest(body)))
        if len(preserved) != 25 or sum(p['path'] != p['previousPath'] for p in preserved) != len(COMMANDS):
            raise ValueError('Ocean tool inventory changed; re-audit before migrating')
        wrapper = ('#!/' + PREFIX + '/bin/sh\n' +
                   '# Explicit access to the preserved original Ocean shell commands.\n' +
                   'case "${1:-}" in\n  ' + '|'.join(COMMANDS) + ') tool="$1"; shift ;;\n' +
                   '  *) printf "%s\\n" "Usage: ocean-tools-legacy <' + ' | '.join(COMMANDS) + '> [args]" >&2; exit 2 ;;\nesac\n' +
                   'exec "${PREFIX:-/' + PREFIX + '}/libexec/ocean-tools/previous-cli/$tool" "$@"\n').encode()
        member = tarfile.TarInfo('./' + PREFIX + '/bin/ocean-tools-legacy')
        member.mode = 0o755
        entries.append((member, wrapper))
        members[2] = ('data.tar.xz', tar_bytes(entries))
        report['preservedScripts'] = preserved
        # If an archive carries md5sums, update relocated paths as well.
        for member, body in control_entries:
            if member.name.removeprefix('./') == 'md5sums':
                raise ValueError('Unexpected md5sums inventory; require explicit migration')
    elif row['name'] in plan['components']:
        relation = 'ocean-tools (<< 1.1.0+ocean2)'
        for field in ('Breaks', 'Replaces'):
            control[field] = ', '.join(filter(None, (control.get(field), relation)))
    control_text = ''.join(k + ': ' + v + '\n' for k, v in control.items()).encode()
    control_entries = [(m, control_text if m.name.removeprefix('./') == 'control' else b)
                       for m, b in control_entries]
    members[1] = ('control.tar.xz', tar_bytes(control_entries))
    report['dataMemberSha256After'] = digest(members[2][1])
    report['payloadUnchanged'] = report['dataMemberSha256Before'] == report['dataMemberSha256After']
    output = ar_write(members)
    report['sha256'] = digest(output)
    return output, report


def fetch_input(row, plan, cache):
    target = cache / (row['sha256'] + '.deb')
    local = ROOT / 'apt' / row['filename']
    if not target.exists():
        if local.is_file():
            data = local.read_bytes()
        else:
            url = ('https://raw.githubusercontent.com/leonpresistforever-png/'
                   'Oceanstudio-packages/' + plan['sourceCommit'] + '/apt/' + row['filename'])
            with urllib.request.urlopen(url, timeout=120) as response:
                data = response.read()
        if len(data) != row['size'] or digest(data) != row['sha256']:
            raise ValueError('Input size/hash mismatch: ' + row['name'])
        target.write_bytes(data)
    data = target.read_bytes()
    if len(data) != row['size'] or digest(data) != row['sha256']:
        raise ValueError('Cache size/hash mismatch: ' + row['name'])
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=ROOT/'packages/ocean-tools/ownership-plan.json')
    parser.add_argument('--output', type=Path, default=ROOT/'staging/ocean-tools-coinstallation')
    parser.add_argument('--cache', type=Path, default=Path(tempfile.gettempdir())/'ocean-ownership-inputs')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    args.cache.mkdir(parents=True, exist_ok=True)
    # Nothing reaches staging until every pinned input has been verified and
    # every output is complete. Failed runs cannot publish a partial graph.
    with tempfile.TemporaryDirectory(prefix='ocean-tool-migration-') as td:
        staging = Path(td)
        pool = staging/'pool/main'
        pool.mkdir(parents=True)
        def build(row):
            source = fetch_input(row, plan, args.cache)
            output, report = repair(source, row, plan)
            filename = f"{row['name']}_{row['newVersion']}_{row['architecture']}.deb"
            (pool/filename).write_bytes(output)
            return report
        with ThreadPoolExecutor(max_workers=6) as executor:
            reports = list(executor.map(build, plan['packages']))
        receipt = dict(sourceCommit=plan['sourceCommit'], packages=reports,
                       scope='Control metadata migration; compressed payloads unchanged except retained Ocean script relocation',
                       upstreamRebuilt=False, androidRuntimeTested=False)
        (staging/'ownership-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        args.output.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staging, args.output, dirs_exist_ok=True)
    print(json.dumps(dict(packages=len(reports), unchangedPayloads=sum(r['payloadUnchanged'] for r in reports))))


if __name__ == '__main__':
    main()
