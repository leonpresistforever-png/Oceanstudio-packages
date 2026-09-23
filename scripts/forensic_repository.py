#!/usr/bin/env python3
"""Read every unique pool/staged archive, every control file and every payload byte.

This is static evidence, not an Android installation or source-provenance certificate.
No maintainer script or package executable is run. Old archives are never removed.
"""
from __future__ import annotations
import argparse
import collections
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import tarfile
import tempfile
from audit_package_payloads import dependency_errors
from index_all_staged import fields, stanzas, hashes, ROOT, INDEX

PREFIX = '/data/data/studio.ocean.app/files/usr'
MARKERS = {
    'foreign-app-prefix': (b'/data/data/com.termux', b'/data/user/0/com.termux'),
    'foreign-repository': (b'packages.termux.', b'packages-cf.termux.', b'github.com/termux/',
                           b'raw.githubusercontent.com/termux/'),
    'foreign-runtime-variable': (b'termux_prefix', b'termux__prefix'),
    'confirmed-ready-stub': (b'ready on ocean os',),
    'termux-mention-review': (b'termux',),
}
URL = re.compile(rb'https?://[^\s\x00\"\'<>`\\]{5,1024}')


def location(path):
    if path.startswith(PREFIX.lstrip('/') + '/'): return 'native-prefix'
    if path.startswith('data/data/studio.ocean.app/files/glibc/'): return 'isolated-glibc'
    if path.startswith('data/data/studio.ocean.app/'): return 'ocean-app-data'
    return 'outside-ocean-prefix-review'


def elf_role(path, machine, elf_type):
    # Guile .go files contain VM bytecode in ELF containers, with EM_NONE.
    # Go distributes cross-target relocatable .syso files as compiler inputs.
    if machine == 0 and '/lib/guile/' in '/' + path and path.endswith('.go'):
        return 'guile-vm-bytecode'
    if elf_type == 1 and '/lib/go/src/' in '/' + path and path.endswith('.syso'):
        return 'go-cross-target-object'
    if path.endswith('/libexec/proot/loader32') and machine == 40:
        return 'proot-arm32-helper-review'
    return 'native-elf'


def scan_stream(stream, name, executable=False, control=False):
    digest = hashlib.sha256()
    count, tail, head, findings, urls = 0, b'', b'', {}, set()
    elf_file = None
    try:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk: break
            if count == 0 and chunk.startswith(b'\x7fELF'):
                elf_file = tempfile.NamedTemporaryFile(prefix='ocean-elf-')
            if elf_file: elf_file.write(chunk)
            digest.update(chunk)
            if len(head) < 65536: head += chunk[:65536 - len(head)]
            window = tail + chunk
            lowered = window.lower()
            for kind, needles in MARKERS.items():
                for needle in needles:
                    offset = lowered.find(needle)
                    if offset >= 0 and kind not in findings:
                        findings[kind] = {'kind': kind, 'offset': max(0, count - len(tail) + offset),
                                          'marker': needle.decode()}
            # URLs in executable scripts, configuration and maintainer scripts are
            # runtime download candidates. Documentation URLs are not source proof.
            if control or executable or '/etc/' in '/' + name or name.endswith('.json'):
                urls.update(x.decode('utf-8', 'replace').rstrip(').,;') for x in URL.findall(window))
            tail = window[-2048:]
            count += len(chunk)
        row = {'path': name, 'bytes': count, 'sha256': digest.hexdigest(),
               'executable': executable, 'findings': list(findings.values())}
        if urls: row['urls'] = sorted(urls)
        if head.startswith(b'#!'):
            row['interpreter'] = head.split(b'\n', 1)[0].decode('utf-8', 'replace')
        if elf_file:
            elf_file.flush()
            if len(head) < 20 or head[5] not in (1, 2):
                row['findings'].append({'kind': 'invalid-elf-header'})
            else:
                endian = '<' if head[5] == 1 else '>'
                elf_type, machine = struct.unpack(endian + 'HH', head[16:20])
                info = subprocess.run(['readelf', '-lW', '-dW', elf_file.name],
                                      capture_output=True, text=True, timeout=30)
                row['elf'] = {'machine': machine, 'type': elf_type,
                    'role': elf_role(name, machine, elf_type),
                    'interpreter': re.findall(r'Requesting program interpreter: ([^\]]+)', info.stdout),
                    'needed': re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', info.stdout),
                    'rpath': re.findall(r'\((?:RPATH|RUNPATH)\).*?\[([^\]]+)\]', info.stdout)}
                if info.returncode:
                    row['findings'].append({'kind': 'elf-reader-error', 'detail': info.stderr[:1000]})
                if row['elf']['role'] == 'native-elf' and machine != 183:
                    row['findings'].append({'kind': 'native-architecture-review', 'machine': machine})
        return row
    finally:
        if elf_file: elf_file.close()


def scan_tar(deb, control=False):
    flag = '--ctrl-tarfile' if control else '--fsys-tarfile'
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(['dpkg-deb', flag, str(deb)], stdout=subprocess.PIPE, stderr=errors)
        records = []
        try:
            with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
                for member in archive:
                    name = PurePosixPath(member.name).as_posix()
                    if member.isdir(): continue
                    bad = (name.startswith('/') or '..' in PurePosixPath(name).parts
                           or any(c in name for c in '\n\r\0'))
                    if member.isfile():
                        with archive.extractfile(member) as stream:
                            row = scan_stream(stream, name, bool(member.mode & 0o111), control)
                        if row['bytes'] != member.size:
                            raise ValueError('Truncated tar member: ' + name)
                        row['kind'] = 'file'
                    else:
                        row = {'path': name, 'kind': 'symlink' if member.issym() else
                               'hardlink' if member.islnk() else 'special',
                               'target': member.linkname, 'findings': []}
                        if 'termux' in member.linkname.lower():
                            row['findings'].append({'kind': 'foreign-link-target', 'target': member.linkname})
                    row['mode'] = oct(member.mode)
                    row['location'] = 'control' if control else location(name)
                    if bad: row['findings'].append({'kind': 'unsafe-archive-path'})
                    records.append(row)
            # Consume any remaining bytes so dpkg's decompressor can report a
            # truncated/invalid stream rather than confusing SIGPIPE with success.
            while process.stdout.read(1048576): pass
            if process.wait():
                errors.seek(0)
                raise ValueError('Archive decode failed: ' + errors.read().decode(errors='replace')[:2000])
            return records
        finally:
            process.stdout.close()
            if process.poll() is None: process.terminate()
            process.wait()


def file_collisions(owners):
    result = []
    for path, records in sorted(owners.items()):
        if len({r['package'] for r in records}) < 2: continue
        # Even byte-identical files can trigger dpkg overwrite errors. Record
        # Replaces/Conflicts for review instead of silently treating them as safe.
        result.append({'path': path, 'sameContent': len({r['content'] for r in records}) == 1,
                       'owners': records})
    return result


def audit(root, output):
    output.mkdir(parents=True, exist_ok=True)
    current = [fields(s) for s in stanzas((root / 'apt/dists/stable' / INDEX).read_text())]
    live = collections.defaultdict(list)
    for record in current: live[record['SHA256']].append(record)
    paths = sorted((root / 'apt/pool').rglob('*.deb')) + sorted((root / 'staging').rglob('*.deb'))
    seen, archives, owners, problems = {}, [], collections.defaultdict(list), []
    totals, elf_roles = collections.Counter(), collections.Counter()
    with gzip.open(output / 'file-inventory.jsonl.gz', 'wt') as inventory:
        for number, path in enumerate(paths, 1):
            rel = path.relative_to(root).as_posix()
            entry = {'path': rel}
            try:
                if not path.resolve().is_relative_to(root.resolve()):
                    raise ValueError('Archive symlink escapes repository')
                digest = hashes(path)['sha256']
                entry['sha256'] = digest
                if digest in seen:
                    entry['sameArchiveAs'] = seen[digest]
                    archives.append(entry)
                    continue
                seen[digest] = rel
                control = fields(subprocess.check_output(['dpkg-deb', '--field', str(path)], text=True))
                entry.update({k: control[k] for k in ('Package', 'Version', 'Architecture')})
                entry['indexed'] = digest in live
                entry['sourceProvenance'] = 'not-established-by-payload-scan'
                payload = scan_tar(path)
                scripts = scan_tar(path, True)
                entry['files'] = len(payload)
                entry['payloadBytes'] = sum(x.get('bytes', 0) for x in payload)
                entry['findings'] = []
                entry['runtimeUrls'] = sorted({u for x in payload + scripts for u in x.get('urls', [])})
                entry['locations'] = dict(collections.Counter(x['location'] for x in payload))
                for section, rows in (('payload', payload), ('control', scripts)):
                    for row in rows:
                        inventory.write(json.dumps({'archive': rel, 'package': control['Package'],
                            'version': control['Version'], 'section': section, **row}) + '\n')
                        for finding in row['findings']:
                            entry['findings'].append({'path': row['path'], 'section': section, **finding})
                        if 'elf' in row:
                            elf_roles[row['elf']['role']] += 1
                            if control['Architecture'] == 'all' and row['elf']['role'] == 'native-elf':
                                entry['findings'].append({'path': row['path'], 'kind': 'native-elf-declared-all'})
                        if section == 'payload' and digest in live:
                            content = row.get('sha256', row['kind'] + ':' + row.get('target', ''))
                            for r in live[digest]:
                                owners[row['path']].append({'package': r['Package'], 'content': content,
                                    'Replaces': r.get('Replaces', ''), 'Conflicts': r.get('Conflicts', '')})
                totals.update(x['kind'] for x in entry['findings'])
                inventory.flush()
            except (ValueError, OSError, subprocess.SubprocessError, tarfile.TarError) as exc:
                entry['error'] = str(exc)
                problems.append({'path': rel, 'error': str(exc)})
            archives.append(entry)
            if number % 100 == 0:
                print(f'Inspected {number}/{len(paths)} archive paths; {len(seen)} unique byte streams', flush=True)
    collisions = file_collisions(owners)
    with gzip.open(output / 'file-collisions.json.gz', 'wt') as out:
        json.dump(collisions, out, indent=2)
    report = {'complete': len(archives) == len(paths), 'archivePaths': len(paths),
        'uniqueArchiveBytes': len(seen), 'indexedEntries': len(current),
        'indexedNames': len({r['Package'] for r in current}), 'invalidArchives': problems,
        'findingCounts': dict(totals), 'elfRoles': dict(elf_roles),
        'overlappingLivePaths': len(collisions), 'dependencyErrors': dependency_errors(current),
        'archives': archives, 'androidRuntimeTested': False,
        'limitations': ['Static inspection does not prove upstream provenance or successful installation.',
            'Compressed files nested inside package payloads are hashed but not recursively unpacked.',
            'Cross-package path overlap requires Replaces/Conflicts and installation review.',
            'URLs are inventoried; this scan does not claim their HTTP availability.']}
    (output / 'forensic-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'archives'}, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit(args.root.resolve(), args.output)
