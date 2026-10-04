#!/usr/bin/env python3
"""Build real upstream Python packages, npm and the independent Ocean gateway."""
import argparse
import base64
import configparser
import csv
import email
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = Path('data/data/studio.ocean.app/files/usr')
VENDOR = PREFIX / 'lib/ocean-python/site-packages'
normalize = lambda text: re.sub(r'[-_.]+', '-', text).lower()

def fetch(item, cache):
    artifact = cache / item['artifact']
    if not artifact.exists():
        temporary = artifact.with_suffix(artifact.suffix + '.download')
        with urllib.request.urlopen(item['url'], timeout=120) as source, temporary.open('wb') as output:
            shutil.copyfileobj(source, output)
        os.replace(temporary, artifact)
    if hashlib.sha256(artifact.read_bytes()).hexdigest() != item['sha256']:
        raise RuntimeError('Upstream SHA-256 mismatch: ' + artifact.name)
    return artifact

def safe_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name:
        raise RuntimeError('Unsafe upstream archive path: ' + name)
    return path

def unpack_wheel(wheel, destination, item):
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata_path = next(n for n in names if n.endswith('.dist-info/METADATA'))
        metadata = email.message_from_bytes(archive.read(metadata_path))
        if normalize(metadata['Name']) != item['name'] or metadata['Version'] != item['version']:
            raise RuntimeError('Upstream wheel identity mismatch')
        wheel_metadata = archive.read(metadata_path.replace('METADATA', 'WHEEL')).decode()
        if 'Root-Is-Purelib: true' not in wheel_metadata or any('-none-any' not in line for line in wheel_metadata.splitlines() if line.startswith('Tag:')):
            raise RuntimeError('Only upstream platform-independent Python payloads are permitted')
        record_path = metadata_path.replace('METADATA', 'RECORD')
        records = {row[0]: row[1:] for row in csv.reader(io.StringIO(archive.read(record_path).decode()))}
        for name in names:
            safe_path(name)
            if name.endswith('/'):
                continue
            content = archive.read(name)
            if content.startswith(b'\x7fELF'):
                raise RuntimeError('Native binary found in a pure Python wheel')
            record = records.get(name)
            if record is None:
                raise RuntimeError('Wheel file missing from upstream RECORD: ' + name)
            if record[0]:
                algorithm, expected = record[0].split('=', 1)
                actual = base64.urlsafe_b64encode(hashlib.new(algorithm, content).digest()).decode().rstrip('=')
                if actual != expected or str(len(content)) != record[1]:
                    raise RuntimeError('Wheel RECORD integrity failure: ' + name)
            parts = PurePosixPath(name).parts
            if parts[0].endswith('.data'):
                if len(parts) < 3 or parts[1] not in ['purelib', 'data', 'scripts']:
                    raise RuntimeError('Unsupported upstream wheel relocation: ' + name)
                relative = Path(*parts[2:]) if parts[1] == 'purelib' else Path('share/ocean-python-data') / item['name'] / Path(*parts[2:])
                target = destination / (VENDOR / relative if parts[1] == 'purelib' else PREFIX / relative)
                if parts[1] == 'scripts':
                    command = parts[-1]
                    if not re.fullmatch(r'[A-Za-z0-9_.-]+', command) or not content.startswith((b'#!python', b'#!/usr/bin/env python')):
                        raise RuntimeError('Unsupported upstream non-Python script: ' + name)
                    launcher(destination, 'ocean-' + command, '#!/system/bin/sh\nexec "${PREFIX:-/data/data/studio.ocean.app/files/usr}/bin/python" '
                             '"${PREFIX:-/data/data/studio.ocean.app/files/usr}/' + str(relative) + '" "$@"\n')
            else:
                target = destination / VENDOR / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            target.chmod(0o644)
        entry_path = metadata_path.replace('METADATA', 'entry_points.txt')
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        if entry_path in names:
            parser.read_string(archive.read(entry_path).decode())
        return dict(parser['console_scripts']) if parser.has_section('console_scripts') else {}

def launcher(stage, name, script):
    path = stage / PREFIX / 'bin' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(script)
    path.chmod(0o755)

def package(stage, output, name, version, description, dependencies=(), homepage='', section='python', relationships=''):
    control = stage / 'DEBIAN'
    control.mkdir()
    (control / 'control').write_text(f'Package: {name}\nVersion: {version}\nArchitecture: all\n'
        'Maintainer: OceanStudio <packages@ocean.studio>\nPriority: optional\n' + f'Section: {section}\n'
        + ('Depends: ' + ', '.join(dependencies) + '\n' if dependencies else '')
        + (f'Homepage: {homepage}\n' if homepage else '')
        + relationships
        + 'Description: ' + ' '.join(description.split()) + '\n')
    artifact = output / f'{name}_{version}_all.deb'
    temporary = stage.parent / (artifact.name + '.complete')
    subprocess.run(['dpkg-deb', '--threads-max=1', '--root-owner-group', '-Zxz', '--build', str(stage), str(temporary)], check=True, stdout=subprocess.DEVNULL)
    # Validate the data member before making an archive visible to a publisher.
    subprocess.run(['dpkg-deb', '--contents', str(temporary)], check=True, stdout=subprocess.DEVNULL)
    payload = temporary.read_bytes()
    ready = artifact.with_suffix('.deb.new')
    with ready.open('wb') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(ready, artifact)
    if hashlib.sha256(artifact.read_bytes()).digest() != hashlib.sha256(payload).digest():
        raise RuntimeError('Archive changed during atomic publication: ' + name)
    return {'package': name, 'version': version, 'artifact': artifact.name, 'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest()}

def main(args):
    lock = json.loads((ROOT / 'sources/runtime-dependencies/lock.json').read_text())
    npm = json.loads((ROOT / 'sources/runtime-dependencies/npm.json').read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    args.cache.mkdir(parents=True, exist_ok=True)
    entries = lock['packages']
    if len(entries) < 100 or len({e['name'] for e in entries}) != len(entries):
        raise RuntimeError('The catalogue must contain at least 100 distinct upstream distributions')
    indexed = (ROOT / 'apt/dists/stable/main/binary-aarch64/Packages')
    existing = set(re.findall(r'^Package: (.+)$', indexed.read_text(), re.M)) if indexed.is_file() else set()
    duplicate = existing.intersection(p['package'] for p in entries)
    if duplicate and not args.allow_existing:
        raise RuntimeError('New package names already indexed: ' + ', '.join(sorted(duplicate)))
    versions = {p['name']: p['version'] + '-1+ocean1' for p in entries}
    receipts = []
    with tempfile.TemporaryDirectory(prefix='ocean-upstream-runtime-') as directory:
        work = Path(directory)
        for item in entries:
            source = fetch(item, args.cache)
            if item.get('build'):
                unpack = work / ('source-' + item['name'])
                unpack.mkdir()
                with tarfile.open(source) as archive:
                    for member in archive.getmembers():
                        safe_path(member.name)
                    archive.extractall(unpack, filter='data')
                wheel_directory = work / ('wheel-' + item['name'])
                wheel_directory.mkdir()
                project = next(unpack.iterdir())
                env = dict(os.environ, **item['build']['environment'], SOURCE_DATE_EPOCH='1760000000')
                subprocess.run([os.sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation', '--wheel-dir', str(wheel_directory), str(project)], check=True, env=env)
                source = next(wheel_directory.glob('*.whl'))
            stage = work / item['package']
            stage.mkdir()
            commands = unpack_wheel(source, stage, item)
            for command in commands:
                if not re.fullmatch(r'[A-Za-z0-9_.-]+', command):
                    raise RuntimeError('Invalid upstream entry point')
                launcher(stage, 'ocean-' + command, '#!/system/bin/sh\nexec "${PREFIX:-/data/data/studio.ocean.app/files/usr}/bin/python" '
                    '"${PREFIX:-/data/data/studio.ocean.app/files/usr}/share/ocean-python/entrypoint.py" '
                    + item['name'] + ' ' + command + ' "$@"\n')
            doc = stage / PREFIX / 'share/doc' / item['package']
            doc.mkdir(parents=True)
            (doc / 'upstream.json').write_text(json.dumps(item, indent=2) + '\n')
            deps = ['ocean-python-site (= 1.0.0-1+ocean1)'] + [f'python-{d} (= {versions[d]})'
                for d in sorted(set(item['dependencies'] + item.get('oceanExtraDependencies', [])))]
            receipt = package(stage, args.output, item['package'], versions[item['name']], item['summary'], deps, 'https://pypi.org/project/' + item['name'] + '/')
            receipt.update(upstreamSha256=item['sha256'], upstreamUrl=item['url'], distribution=item['name'])
            receipts.append(receipt)
            print('Built ' + item['package'], flush=True)
        site = work / 'ocean-python-site'
        pth = site / PREFIX / ('lib/python' + '.'.join(lock['python'].split('.')[:2])) / 'site-packages/ocean-runtime.pth'
        pth.parent.mkdir(parents=True)
        pth.write_text('../../ocean-python/site-packages\n')
        dispatch = site / PREFIX / 'share/ocean-python/entrypoint.py'
        dispatch.parent.mkdir(parents=True)
        dispatch.write_text('import sys\nfrom importlib.metadata import distribution\n'
            'name, command = sys.argv[1:3]\nentry = next(e for e in distribution(name).entry_points if e.group == "console_scripts" and e.name == command)\n'
            'sys.argv = [command] + sys.argv[3:]\nraise SystemExit(entry.load()())\n')
        receipts.append(package(site, args.output, 'ocean-python-site', '1.0.0-1+ocean1', 'Shared additive import path and entry point loader for upstream Python libraries', ['python (>= 3.14.6)']))
        npm_source = fetch(npm, args.cache)
        npm_stage = work / 'npm'
        npm_stage.mkdir()
        npm_target = npm_stage / PREFIX / 'lib/node_modules/npm'
        npm_target.mkdir(parents=True)
        with tarfile.open(npm_source) as archive:
            for member in archive.getmembers():
                safe_path(member.name)
                relative = PurePosixPath(member.name).relative_to('package')
                if not relative.parts:
                    continue
                if not member.isfile() and not member.isdir():
                    raise RuntimeError('Unexpected npm tarball link')
                target = npm_target / str(relative)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.extractfile(member).read())
                    target.chmod(0o755 if member.mode & 0o111 else 0o644)
        for command in ['npm', 'npx']:
            launcher(npm_stage, command, '#!/system/bin/sh\nexec "${PREFIX:-/data/data/studio.ocean.app/files/usr}/bin/node" '
                     '"${PREFIX:-/data/data/studio.ocean.app/files/usr}/lib/node_modules/npm/bin/' + command + '-cli.js" "$@"\n')
        receipts.append(package(npm_stage, args.output, 'npm', npm['version'] + '-2+ocean1', 'Official npm CLI with relocation-safe Ocean Android launchers', ['nodejs (>= 20.17)'], 'https://github.com/npm/cli', 'devel',
                                'Replaces: npx (<< 11.19.1)\nBreaks: npx (<< 11.19.1)\nProvides: npx (= 11.19.1)\n'))
        gateway = work / 'ocean-gateway'
        gateway.mkdir()
        code = gateway / PREFIX / 'share/ocean-gateway'
        code.mkdir(parents=True)
        for path in (ROOT / 'packages/ocean-gateway').iterdir():
            if path.suffix == '.mjs' or path.name in ['README.md', 'LICENSE']:
                shutil.copy2(path, code / path.name)
        launcher(gateway, 'ocean-gateway', (ROOT / 'packages/ocean-gateway/ocean-gateway').read_text())
        receipts.append(package(gateway, args.output, 'ocean-gateway', '4.0.0-1+ocean1', 'Independent Ocean encrypted account gateway with browser authorization and OpenAI-compatible inference', ['nodejs (>= 22)', 'ca-certificates'], 'https://github.com/leonpresistforever-png/Oceanstudio-packages', 'net'))
        compat = work / 'ocean-runtime-compat'
        compat.mkdir()
        doctor = compat / PREFIX / 'share/ocean-runtime-compat/doctor.py'
        doctor.parent.mkdir(parents=True)
        shutil.copy2(ROOT / 'packages/ocean-runtime-compat/doctor.py', doctor)
        shebang = compat / PREFIX / 'share/ocean/scripts/fix-runtime-shebangs.py'
        shebang.parent.mkdir(parents=True)
        shutil.copy2(ROOT / 'scripts/fix-runtime-shebangs.py', shebang)
        launcher(compat, 'ocean-runtime-doctor', '#!/system/bin/sh\nexec "${PREFIX:-/data/data/studio.ocean.app/files/usr}/bin/python" '
                 '"${PREFIX:-/data/data/studio.ocean.app/files/usr}/share/ocean-runtime-compat/doctor.py" "$@"\n')
        receipts.append(package(compat, args.output, 'ocean-runtime-compat', '1.0.1-1+ocean1', 'Inspect runtime compatibility, repair npm launchers and provide the missing Ocean shebang helper', ['python'], section='utils'))
    (args.output / 'build-receipts.json').write_text(json.dumps(receipts, indent=2) + '\n')
    print(f'Built {len(receipts)} verified packages; {len(entries)} distinct upstream Python distributions')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'staging/independent-runtime')
    parser.add_argument('--cache', type=Path, default=ROOT.parent / 'upstream-cache')
    parser.add_argument('--allow-existing', action='store_true', help='Rebuild already published locked packages for verification')
    main(parser.parse_args())
