#!/usr/bin/env python3
"""Build quarantined Android ARM64 candidates from pinned official source archives.

This does not publish, sign an APT repository, or certify device compatibility.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

PREFIX = '/data/data/studio.ocean.app/files/usr'
TARGET = 'aarch64-linux-android28'
NDK_REVISION = '27.0.12077973'
ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1048576), b''): h.update(chunk)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def recipes(path):
    data = json.loads(Path(path).read_text())
    names = set()
    for item in data:
        name = item['name']
        if not re.fullmatch(r'[a-z0-9][a-z0-9+.-]+', name) or name in names:
            raise ValueError('Invalid or duplicate package name: ' + name)
        names.add(name)
        commit = item['commit']
        if not re.fullmatch(r'[0-9a-f]{40}', commit): raise ValueError('Source commit must be pinned')
        if item['url'] != 'https://codeload.github.com/' + item['upstream'] + '/tar.gz/' + commit:
            raise ValueError('Source URL does not match pinned upstream')
        if not re.fullmatch(r'[0-9a-f]{64}', item['sha256']): raise ValueError('Missing source checksum')
        if not item['licenses'] or not item['expected']: raise ValueError('License and payload checks required')
    return sorted(data, key=lambda x: x['name'])


def fetch(item, cache):
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (item['sha256'] + '.tar.gz')
    if path.exists() and sha(path) == item['sha256']: return path
    fd, name = tempfile.mkstemp(dir=cache, suffix='.download')
    os.close(fd)
    temporary = Path(name)
    try:
        request = urllib.request.Request(item['url'], headers={'User-Agent': 'OceanStudio-source-builder/1'})
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open('wb') as out:
            if not response.url.startswith('https://'): raise ValueError('Insecure source redirect')
            shutil.copyfileobj(response, out)
        if sha(temporary) != item['sha256']: raise ValueError('Source checksum mismatch: ' + item['name'])
        temporary.replace(path)
    finally: temporary.unlink(missing_ok=True)
    return path


def extract(archive, destination):
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            p = PurePosixPath(member.name)
            if p.is_absolute() or '..' in p.parts or any(c in member.name for c in '\r\n\0'):
                raise ValueError('Unsafe source archive path')
        source.extractall(destination, filter='data')
    children = list(destination.iterdir())
    if len(children) != 1 or not children[0].is_dir(): raise ValueError('Expected one source directory')
    return children[0]


def validate_payload(stage, readelf):
    prefix = stage / PREFIX.lstrip('/')
    files, elfs = [], []
    forbidden = (b'/data/data/com.termux', b'/data/user/0/com.termux', b'packages.termux.dev', b'TERMUX_PREFIX')
    for path in sorted(stage.rglob('*')):
        if path.is_symlink():
            if not path.is_relative_to(prefix) or not path.resolve().is_relative_to(prefix.resolve()):
                raise ValueError('Escaping payload symlink: ' + str(path))
            files.append(str(path.relative_to(stage)))
            continue
        if not path.is_file(): continue
        if not path.is_relative_to(prefix): raise ValueError('File outside Ocean prefix: ' + str(path))
        payload = path.read_bytes()
        if any(marker in payload for marker in forbidden): raise ValueError('Foreign runtime prefix: ' + str(path))
        relative = str(path.relative_to(stage)); files.append(relative)
        if path.is_relative_to(prefix / 'bin') and not os.access(path, os.X_OK): raise ValueError('Non-executable command')
        if payload.startswith(b'\x7fELF'):
            info = subprocess.check_output([str(readelf), '-h', '-l', '-d', str(path)], text=True)
            if 'AArch64' not in info: raise ValueError('Non-ARM64 ELF: ' + relative)
            interpreters = re.findall(r'Requesting program interpreter: ([^\]]+)', info)
            if any(x != '/system/bin/linker64' for x in interpreters): raise ValueError('Non-Android interpreter')
            needed = re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', info)
            if any(x in ('libc.so.6', 'libpthread.so.0') or x.startswith('ld-linux') for x in needed):
                raise ValueError('Host libc dependency')
            elfs.append({'path': relative, 'needed': needed, 'interpreter': interpreters})
    if not files or not elfs: raise ValueError('No compiled payload')
    return {'staticChecks': 'passed', 'androidRuntime': 'pending', 'files': files, 'elfs': elfs}


def build(item, args, identity):
    output = args.output / ('shard-%03d' % args.shard_index) / item['name']
    output.mkdir(parents=True, exist_ok=True)
    artifact = output / (item['name'] + '_' + item['version'] + '_aarch64.deb')
    receipt = output / 'provenance.json'
    build_id = dict(identity, recipeSha256=hashlib.sha256(canonical(item)).hexdigest())
    if args.resume and receipt.exists() and artifact.exists():
        old = json.loads(receipt.read_text())
        if old.get('buildIdentity') == build_id and old.get('artifactSha256') == sha(artifact):
            return {'name': item['name'], 'status': 'cached', 'artifact': str(artifact)}
    ndk_bin = args.ndk / 'toolchains/llvm/prebuilt/linux-x86_64/bin'
    environment = dict(os.environ, SOURCE_DATE_EPOCH='0', LC_ALL='C')
    with tempfile.TemporaryDirectory(prefix='build-', dir=output) as temporary, (output / 'build.log').open('w') as log:
        work = Path(temporary); source_dir = work / 'source'; source_dir.mkdir()
        source = extract(fetch(item, args.cache), source_dir)
        stage = work / 'stage'; stage.mkdir()
        prefix = stage / PREFIX.lstrip('/')
        def run(*command, **kwargs):
            log.write('$ ' + ' '.join(map(str, command)) + '\n'); log.flush()
            subprocess.run(list(map(str, command)), check=True, stdout=log, stderr=subprocess.STDOUT,
                           env=environment, **kwargs)
        if item['build'] == 'cmake':
            build_dir = work / 'build'
            run(args.cmake, '-S', source, '-B', build_dir,
                '-DCMAKE_TOOLCHAIN_FILE=' + str(args.ndk / 'build/cmake/android.toolchain.cmake'),
                '-DANDROID_ABI=arm64-v8a', '-DANDROID_PLATFORM=android-28',
                '-DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON', '-DCMAKE_BUILD_TYPE=Release',
                '-DCMAKE_INSTALL_PREFIX=' + PREFIX, '-DCMAKE_INSTALL_LIBDIR=lib',
                '-DCMAKE_INSTALL_RPATH=$ORIGIN/../lib', '-DCMAKE_C_FLAGS=-O2 -fPIC',
                '-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-z,max-page-size=16384',
                '-DCMAKE_EXE_LINKER_FLAGS=-Wl,-z,max-page-size=16384', *item.get('options', []))
            run(args.cmake, '--build', build_dir, '--parallel', args.jobs_per_package)
            environment['DESTDIR'] = str(stage)
            run(args.cmake, '--install', build_dir)
        elif item['build'] == 'single-c':
            (prefix / 'bin').mkdir(parents=True)
            run(ndk_bin / 'clang', '--target=' + TARGET, '-O2', '-fPIE', '-pie',
                '-Wl,-z,max-page-size=16384', source / item['source'], '-o', prefix / 'bin' / item['name'])
        else: raise ValueError('Unknown build system')
        for expected in item['expected']:
            if not (prefix / expected).exists(): raise ValueError('Missing expected payload: ' + expected)
        doc = prefix / 'share/doc' / item['name']; doc.mkdir(parents=True, exist_ok=True)
        licenses = {}
        for license_file in item['licenses']:
            original = source / license_file
            shutil.copyfile(original, doc / Path(license_file).name)
            licenses[license_file] = sha(original)
        validation = validate_payload(stage, ndk_bin / 'llvm-readelf')
        provenance = dict(package=item['name'], version=item['version'], architecture='aarch64',
            source=item, prefix=PREFIX, target=TARGET, buildIdentity=build_id,
            licenseSha256=licenses, validation=validation, published=False)
        (doc / 'ocean-build.json').write_text(json.dumps(provenance, indent=2) + '\n')
        control = stage / 'DEBIAN'; control.mkdir()
        (control / 'control').write_text(
            f"Package: {item['name']}\nVersion: {item['version']}\nArchitecture: aarch64\n"
            f"Maintainer: OceanStudio\nHomepage: https://github.com/{item['upstream']}\n"
            f"Section: devel\nPriority: optional\nDescription: {item['description']}\n")
        for path in sorted(stage.rglob('*'), reverse=True): os.utime(path, (0, 0), follow_symlinks=False)
        run('dpkg-deb', '--root-owner-group', '-Zxz', '--build', stage, artifact)
        provenance.update(artifactSha256=sha(artifact), artifactSize=artifact.stat().st_size)
        receipt.write_text(json.dumps(provenance, indent=2) + '\n')
    return {'name': item['name'], 'status': 'built', 'artifact': str(artifact), 'runtime': 'pending'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, default=ROOT / 'sources/recipes.json')
    p.add_argument('--ndk', type=Path, default=os.environ.get('ANDROID_NDK_HOME'))
    p.add_argument('--cmake', type=Path, default=shutil.which('cmake'))
    p.add_argument('--output', type=Path, default=ROOT / 'build/source-candidates')
    p.add_argument('--cache', type=Path, default=ROOT / 'build/source-cache')
    p.add_argument('--shard-index', type=int, default=0)
    p.add_argument('--shard-count', type=int, default=1)
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--jobs-per-package', type=int, default=2)
    p.add_argument('--resume', action='store_true'); p.add_argument('--plan', action='store_true')
    args = p.parse_args()
    if not 0 <= args.shard_index < args.shard_count or min(args.workers, args.jobs_per_package) < 1:
        p.error('Invalid shard or worker counts')
    items = [x for n, x in enumerate(recipes(args.manifest)) if n % args.shard_count == args.shard_index]
    if args.plan: print(json.dumps([x['name'] for x in items])); return 0
    if args.ndk is None or args.cmake is None: p.error('--ndk and --cmake are required')
    args.ndk = args.ndk.resolve(); args.cmake = args.cmake.resolve()
    args.output = args.output.resolve(); args.cache = args.cache.resolve()
    if not re.search(r'^Pkg.Revision\s*=\s*' + re.escape(NDK_REVISION) + r'\s*$',
                     (args.ndk / 'source.properties').read_text(), re.M): raise ValueError('Unexpected NDK revision')
    bins = args.ndk / 'toolchains/llvm/prebuilt/linux-x86_64/bin'
    identity = {'ndkRevision': NDK_REVISION, 'clangSha256': sha(bins / 'clang'),
        'linkerSha256': sha(bins / 'ld.lld'), 'cmakeSha256': sha(args.cmake),
        'toolchainSha256': sha(args.ndk / 'build/cmake/android.toolchain.cmake'),
        'builderSha256': sha(__file__), 'prefix': PREFIX, 'target': TARGET}
    def task(item):
        try: return build(item, args, identity)
        except Exception as error: return {'name': item['name'], 'status': 'failed', 'error': str(error)}
    with ThreadPoolExecutor(max_workers=args.workers) as pool: results = list(pool.map(task, items))
    args.output.mkdir(parents=True, exist_ok=True)
    report = args.output / ('shard-%03d-report.json' % args.shard_index)
    report.write_text(json.dumps({'published': False, 'results': results}, indent=2) + '\n')
    print(report.read_text())
    return int(any(x['status'] == 'failed' for x in results))

if __name__ == '__main__': raise SystemExit(main())
