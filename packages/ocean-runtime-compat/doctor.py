#!/usr/bin/env python3
"""Inspect Ocean's runtime and repair only identified npm/npx relocations."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

def inspect(prefix, repair=False):
    findings = []
    for command, target in [('npm', 'npm-cli.js'), ('npx', 'npx-cli.js')]:
        executable = prefix / 'bin' / command
        canonical = prefix / 'lib/node_modules/npm/bin' / target
        if not executable.exists():
            findings.append({'command': command, 'status': 'missing', 'action': 'pkg install npm'})
            continue
        if executable.is_symlink():
            findings.append({'command': command, 'status': 'valid-symlink', 'target': str(executable.resolve())})
            continue
        text = executable.read_bytes()[:65536].decode('utf8', errors='replace')
        flattened = ('../lib/cli.js' in text or "require('./npm-cli.js')" in text) and canonical.is_file()
        if flattened and repair:
            temporary = executable.with_name(command + '.ocean-repair')
            temporary.write_text('#!/system/bin/sh\nexec "${PREFIX:-/data/data/studio.ocean.app/files/usr}/bin/node" '
                                 '"${PREFIX:-/data/data/studio.ocean.app/files/usr}/lib/node_modules/npm/bin/' + target + '" "$@"\n')
            temporary.chmod(0o755)
            os.replace(temporary, executable)
        findings.append({'command': command, 'status': 'repaired' if flattened and repair else 'relocated-script' if flattened else 'launcher',
                         'canonicalExists': canonical.is_file()})
    for path in sorted((prefix / 'bin').glob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open('rb') as stream:
            head = stream.read(4096)
        if head.startswith(b'#!'):
            interpreter = head.splitlines()[0][2:].decode('utf8', errors='replace').strip().split()[0]
            if not Path(interpreter).exists():
                findings.append({'command': path.name, 'status': 'missing-interpreter', 'interpreter': interpreter})
        elif head.startswith(b'\x7fELF') and shutil.which('readelf'):
            result = subprocess.run(['readelf', '-l', '-d', str(path)], text=True, capture_output=True)
            dependencies = re.findall(r'\(NEEDED\).*?\[(.*?)\]', result.stdout)
            glibc = any(d in dependencies for d in ['libc.so.6', 'libm.so.6']) or 'ld-linux' in result.stdout
            if glibc:
                findings.append({'command': path.name, 'status': 'glibc-runtime-required', 'dependencies': dependencies,
                                 'action': 'Use ocean-ffmpeg for FFmpeg, or the isolated Ocean glibc runtime for this executable'})
            else:
                absent = [d for d in dependencies if not any((p / d).exists() for p in [prefix / 'lib', Path('/system/lib64'), Path('/apex/com.android.runtime/lib64/bionic')])]
                if absent:
                    findings.append({'command': path.name, 'status': 'unresolved-native-libraries', 'dependencies': absent})
    return findings

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, default=Path(os.environ.get('PREFIX', '/data/data/studio.ocean.app/files/usr')))
    parser.add_argument('--repair', action='store_true', help='Repair identified npm/npx relocated launchers; preserve all other files')
    args = parser.parse_args()
    print(json.dumps({'prefix': str(args.prefix), 'findings': inspect(args.prefix, args.repair)}, indent=2))
