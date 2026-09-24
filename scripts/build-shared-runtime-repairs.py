#!/usr/bin/env python3
"""Build Ocean's original Python commands with one owner per shared source file.

Only the source/index hashes and command sets recorded by the complete forensic
inventory are accepted. This does not repackage foreign binaries or certify that
every command works on Android. All output remains staged pending signed release.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from index_all_staged import fields, stanzas

ROOT = Path(__file__).resolve().parents[1]
PREFIX = '/data/data/studio.ocean.app/files/usr'
REVISION = '+ocean1'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_archive(name, version, architecture, control, files, output):
    output.mkdir(parents=True, exist_ok=True)
    artifact = output / f'{name}_{version}_{architecture}.deb'
    with tempfile.TemporaryDirectory(prefix='ocean-source-build-') as tmp:
        root = Path(tmp)
        (root / 'DEBIAN').mkdir()
        (root / 'DEBIAN/control').write_text(control)
        for path, (content, mode) in files.items():
            target = root / path.lstrip('/')
            if not target.is_relative_to(root) or '..' in Path(path).parts:
                raise ValueError('Unsafe package path: ' + path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            target.chmod(mode)
        # Stable bytes let repeated CI builds reuse the same version safely.
        for path in sorted(root.rglob('*'), reverse=True):
            os.utime(path, (0, 0))
            if path.is_dir():
                path.chmod(0o755)
        root.chmod(0o755)
        os.utime(root, (0, 0))
        subprocess.run(['dpkg-deb', '--root-owner-group', '-Zxz', '--build', str(root), str(artifact)],
            env={**os.environ, 'SOURCE_DATE_EPOCH': '0'}, check=True, capture_output=True)
    return artifact


def build_group(recipe, records, root, output):
    source = root / recipe['source']
    if sha256(source) != recipe['sourceSha256']:
        raise ValueError('Original Ocean source differs from audited bytes: ' + str(source))
    name, version = recipe['package'], recipe['version']
    commands = recipe['commands']
    if len(commands) != len(set(commands)) or not commands:
        raise ValueError('Duplicate or empty command list')
    for command in commands:
        if not re.fullmatch(r'[a-z0-9][a-z0-9+.-]+', command) or command not in records:
            raise ValueError('Unknown command: ' + command)
        if records[command].get('Depends') != 'python':
            raise ValueError('Dependencies need review: ' + command)
    # Moving a file between packages requires an explicit, versioned ownership
    # transfer. Breaks makes APT upgrade any installed old wrappers in the same
    # transaction; it does not install all command packages from the suite.
    transfers = ', '.join(f"{cmd} (<< {records[cmd]['Version']}{REVISION})" for cmd in commands)
    runtime_control = (
        f'Package: {name}\nVersion: {version}\nArchitecture: all\n'
        # The interface is source bytes consumed by each caller's Python, with
        # no native ABI. Native/foreign callers may share these identical files.
        'Multi-Arch: foreign\n'
        'Maintainer: OceanStudio <packages@ocean.studio>\nSection: libs\nPriority: optional\n'
        f'Depends: python\nReplaces: {transfers}\nBreaks: {transfers}\n'
        f'Description: Shared original Ocean Python runtime for {len(commands)} commands\n'
        ' One package owns the unchanged source module; command packages depend on it.\n')
    artifacts = [build_archive(name, version, 'all', runtime_control,
        {recipe['installPath']: (source.read_bytes(), 0o644)}, output)]
    for cmd in commands:
        old = records[cmd]
        new_version = old['Version'] + REVISION
        control = (
            f"Package: {cmd}\nVersion: {new_version}\nArchitecture: {old['Architecture']}\n"
            f"Maintainer: {old['Maintainer']}\nSection: {old.get('Section', 'utils')}\nPriority: optional\n"
            f"Depends: python, {name} (= {version})\nDescription: {old['Description']}\n")
        wrapper = (f'#!/system/bin/sh\n: "${{PREFIX:={PREFIX}}}"\n'
            f'exec "$PREFIX/bin/python" "$PREFIX/{recipe["installPath"].removeprefix(PREFIX.lstrip("/") + "/")}" {cmd!r} "$@"\n')
        files = {f'{PREFIX}/bin/{cmd}': (wrapper.encode(), 0o755)}
        if not cmd.startswith('ocean-wb-'):
            # Retain a package-specific README as in the original source builder.
            doc = (f'# {cmd}\n\n{old["Description"]}\n\nVersion: {new_version}\n'
                f'Source: {recipe["source"]}\nSource SHA256: {recipe["sourceSha256"]}\n'
                f'Shared runtime package: {name}\n')
            files[f'{PREFIX}/share/doc/{cmd}/README.md'] = (doc.encode(), 0o644)
        artifacts.append(build_archive(cmd, new_version, old['Architecture'], control, files, output))
    return artifacts


def build(manifest_path, index_path, output, root=ROOT):
    manifest = json.loads(manifest_path.read_text())
    if sha256(index_path) != manifest['sourceIndexSha256']:
        raise ValueError('Live index changed; refresh the audited manifest before rebuilding')
    records = {r['Package']: r for r in map(fields, stanzas(index_path.read_text()))}
    recipes = manifest['runtimes']
    names = [n for r in recipes for n in [r['package'], *r['commands']]]
    if len(names) != len(set(names)):
        raise ValueError('Duplicate package names across repair groups')
    for r in recipes:
        if r['package'] in records:
            raise ValueError('Runtime name already exists: ' + r['package'])
        if not r['installPath'].startswith(PREFIX.lstrip('/') + '/lib/'):
            raise ValueError('Runtime path is outside the Ocean native library directory')
    # Never silently mix a prior build's packages into a new repair set.
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Output must be a new empty staging directory')
    artifacts = []
    for recipe in recipes:
        artifacts.extend(build_group(recipe, records, root, output / 'pool/main'))
    rows = [{'artifact': str(p.relative_to(output)), 'sha256': sha256(p), 'bytes': p.stat().st_size}
        for p in artifacts]
    receipt = {'schema': 1, 'sourceType': 'Ocean original Python sources',
        'forensicSourceCommit': manifest['forensicSourceCommit'],
        'sourceIndexSha256': manifest['sourceIndexSha256'], 'manifestSha256': sha256(manifest_path),
        'commandPackages': sum(len(r['commands']) for r in recipes), 'sharedRuntimePackages': len(recipes),
        'artifacts': rows, 'androidDeviceTested': False, 'publication': 'staging-only'}
    (output / 'provenance.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, default=ROOT / 'packages/shared-runtime-repairs.json')
    p.add_argument('--index', type=Path, default=ROOT / 'apt/dists/stable/main/binary-aarch64/Packages')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = build(a.manifest, a.index, a.output)
    print(json.dumps({k: v for k, v in result.items() if k != 'artifacts'}, indent=2))
