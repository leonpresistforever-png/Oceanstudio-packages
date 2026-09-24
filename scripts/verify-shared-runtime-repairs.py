#!/usr/bin/env python3
"""Verify every rebuilt archive and install the complete Python-only repair set.

The temporary host dpkg root uses a test Python package and permits the original
aarch64 control tag for source-only commands. No Android ELF or maintainer script
is executed. This proves file ownership and dependencies, not Android execution.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from forensic_repository import scan_tar
from index_all_staged import fields, stanzas

ROOT = Path(__file__).resolve().parents[1]
PREFIX = '/data/data/studio.ocean.app/files/usr'


def verify(directory, manifest_path, index_path):
    manifest = json.loads(manifest_path.read_text())
    live = {r['Package']: r for r in map(fields, stanzas(index_path.read_text()))}
    expected = {n for r in manifest['runtimes'] for n in [r['package'], *r['commands']]}
    owners, packages = {}, {}
    for artifact in sorted((directory / 'pool/main').glob('*.deb')):
        control = fields(subprocess.check_output(['dpkg-deb', '-f', str(artifact)], text=True))
        name = control['Package']
        if name not in expected or name in packages:
            raise ValueError('Unknown/duplicate repair package: ' + name)
        packages[name] = {'path': artifact, 'control': control}
        scripts = scan_tar(artifact, control=True)
        if {f['path'] for f in scripts} != {'control'}:
            raise ValueError('Unexpected maintainer files: ' + name)
        for entry in scan_tar(artifact):
            if entry['kind'] != 'file' or entry['findings'] or 'elf' in entry:
                raise ValueError(f'Unexpected payload in {name}: {entry}')
            path = entry['path']
            if not path.startswith(PREFIX.lstrip('/') + '/'):
                raise ValueError('Wrong prefix: ' + path)
            if path in owners:
                raise ValueError(f'Overlapping file: {path} in {owners[path]} and {name}')
            owners[path] = name
        if name in live:
            if control['Architecture'] != live[name]['Architecture']:
                raise ValueError('Changed architecture: ' + name)
            subprocess.run(['dpkg', '--compare-versions', control['Version'], 'gt', live[name]['Version']], check=True)
    if set(packages) != expected:
        raise ValueError('Missing repair packages: ' + ', '.join(sorted(expected - packages.keys())))
    for recipe in manifest['runtimes']:
        if owners.get(recipe['installPath']) != recipe['package']:
            raise ValueError('Shared runtime has wrong owner: ' + recipe['installPath'])
        for command in recipe['commands']:
            control = packages[command]['control']
            if control['Depends'] != f"python, {recipe['package']} (= {recipe['version']})":
                raise ValueError('Unresolvable or missing runtime dependency: ' + command)
    # Install every candidate together in a disposable dpkg database. The prior
    # 1,250 packages could not co-install because 18 payload files had many owners.
    with tempfile.TemporaryDirectory(prefix='ocean-coinstall-') as tmp:
        root = Path(tmp) / 'root'
        (root / 'var/lib/dpkg').mkdir(parents=True)
        (root / 'var/lib/dpkg/status').write_text('')
        fixture = Path(tmp) / 'python'
        (fixture / 'DEBIAN').mkdir(parents=True)
        (fixture / 'DEBIAN/control').write_text('Package: python\nVersion: 3.12\nArchitecture: all\nMulti-Arch: foreign\n'
            'Maintainer: Ocean test <test@ocean.studio>\nDescription: Host-only verification fixture\n')
        py = Path(tmp) / 'python.deb'
        subprocess.run(['dpkg-deb', '--build', str(fixture), str(py)], check=True, capture_output=True)
        dpkg = ['dpkg', '--root=' + str(root), '--force-not-root', '--force-architecture']
        # Runtimes precede wrappers. Dpkg configures dependencies across the batch.
        order = [packages[r['package']]['path'] for r in manifest['runtimes']]
        order += [packages[n]['path'] for r in manifest['runtimes'] for n in r['commands']]
        result = subprocess.run([*dpkg, '--install', str(py), *map(str, order)], text=True, capture_output=True)
        if result.returncode:
            raise ValueError('Complete co-install failed: ' + result.stderr[-8000:])
        status = [fields(s) for s in stanzas((root / 'var/lib/dpkg/status').read_text())]
        installed = {r['Package'] for r in status if r.get('Status') == 'install ok installed'}
        if installed != expected | {'python'}:
            raise ValueError('Incomplete dpkg installation')
        prefix = root / PREFIX.lstrip('/')
        (prefix / 'bin/python').symlink_to(sys.executable)
        # Exercise actual installed wrappers and source bytes, with independent
        # expected output for arithmetic and subnet parsing.
        checks = [('ocean-wb-math-gcd', ['84', '126'], '42'),
                  ('subnet-mask-calc', ['192.0.2.4/24'], '192.0.2.0')]
        for command, arguments, expected_output in checks:
            result = subprocess.run(['sh', str(prefix / 'bin' / command), *arguments],
                env={**os.environ, 'PREFIX': str(prefix)}, capture_output=True, text=True)
            if result.returncode or expected_output not in result.stdout:
                raise ValueError('Installed command failed: ' + command + ': ' + result.stderr)
        # Removing one wrapper in each group must not remove any shared module.
        victims = [r['commands'][0] for r in manifest['runtimes']]
        result = subprocess.run([*dpkg, '--remove', *victims], text=True, capture_output=True)
        if result.returncode:
            raise ValueError('Wrapper removal failed: ' + result.stderr)
        for recipe in manifest['runtimes']:
            path = root / recipe['installPath']
            if hashlib.sha256(path.read_bytes()).hexdigest() != recipe['sourceSha256']:
                raise ValueError('Shared module was removed or modified: ' + recipe['package'])
    report = {'packagesVerified': len(packages), 'commandPackages': sum(len(r['commands']) for r in manifest['runtimes']),
        'sharedRuntimePackages': len(manifest['runtimes']), 'overlappingPaths': 0,
        'allCandidatePackagesCoInstalled': True, 'removingOneCommandPerGroupPreservesSharedFiles': True,
        'hostExecutedCommands': [c[0] for c in checks], 'androidDeviceTested': False,
        'limitations': ['Host-only Python fixture, no native Android dependency test',
            'Co-installing does not establish functionality of every command']}
    (directory / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    p.add_argument('--manifest', type=Path, default=ROOT / 'packages/shared-runtime-repairs.json')
    p.add_argument('--index', type=Path, default=ROOT / 'apt/dists/stable/main/binary-aarch64/Packages')
    a = p.parse_args()
    print(json.dumps(verify(a.directory, a.manifest, a.index), indent=2))
