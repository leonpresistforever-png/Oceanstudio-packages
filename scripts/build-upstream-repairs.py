#!/usr/bin/env python3
"""Build pigz and librsync from pinned official sources for Ocean's native prefix."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = '/data/data/studio.ocean.app/files/usr'
SOURCES = {
    'pigz': ('https://github.com/madler/pigz.git', 'fe4894f57739e3039a2ffc2a2a360d35e19bacbe'),
    'zlib': ('https://github.com/madler/zlib.git', 'da607da739fa6047df13e66a2af6b8bec7c2a498'),
    'librsync': ('https://github.com/librsync/librsync.git', 'e364852674780e43d578e4239128ff7014190ed3'),
}


def run(args, **kwargs):
    print('+', ' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source(name, work, receipts):
    url, commit = SOURCES[name]
    destination = work / name
    run(['git', 'init', destination])
    run(['git', '-C', destination, 'fetch', '--depth=1', url, commit])
    run(['git', '-C', destination, 'checkout', '--detach', 'FETCH_HEAD'])
    actual = subprocess.check_output(['git', '-C', str(destination), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != commit:
        raise RuntimeError('Source commit mismatch: ' + name)
    archive = work / (name + '-source.tar')
    with archive.open('wb') as stream:
        run(['git', '-C', destination, 'archive', '--format=tar', 'HEAD'], stdout=stream)
    receipts[name] = {'url': url, 'commit': commit, 'sourceArchiveSha256': sha(archive)}
    return destination


def package(name, version, stage, output, description, sources, tests):
    from audit_package_payloads import inspect_payload
    from index_all_staged import fields, parse_deb, make_stanza
    control = stage / 'DEBIAN'
    control.mkdir()
    (control / 'control').write_text(
        f'Package: {name}\nVersion: {version}\nArchitecture: aarch64\n'
        'Maintainer: OceanStudio <packages@ocean.studio>\nSection: utils\nPriority: optional\n'
        f'Homepage: {SOURCES[name][0].removesuffix(".git")}\nDescription: {description}\n')
    doc = stage / PREFIX.lstrip('/') / 'share/doc' / name
    doc.mkdir(parents=True, exist_ok=True)
    (doc / 'ocean-build.json').write_text(json.dumps({'sources': sources, 'tests': tests,
        'target': 'aarch64-linux-android28', 'prefix': PREFIX, 'physicalDeviceTested': False}, indent=2) + '\n')
    for path in stage.rglob('*'):
        os.utime(path, (0, 0), follow_symlinks=False)
    deb = output / 'pool/main' / f'{name}_{version}_aarch64.deb'
    deb.parent.mkdir(parents=True, exist_ok=True)
    run(['dpkg-deb', '--root-owner-group', '-Zxz', '--build', stage, deb])
    details = inspect_payload(deb, 'aarch64')
    if details['issues']:
        raise RuntimeError('Built payload audit failed: ' + repr(details['issues']))
    text, digest = parse_deb(deb)
    return {'package': name, 'version': version, 'artifact': deb.name, 'sha256': sha(deb),
            'sources': sources, 'tests': tests, 'payloadAudit': details,
            'index': make_stanza(text, digest, deb.name), 'physicalDeviceTested': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ndk', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'staging/upstream-repairs')
    args = parser.parse_args()
    ndk = args.ndk.resolve()
    if 'Pkg.Revision = 27.0.12077973' not in (ndk / 'source.properties').read_text():
        raise RuntimeError('Android NDK r27 is required')
    tools = ndk / 'toolchains/llvm/prebuilt/linux-x86_64/bin'
    cc = tools / 'aarch64-linux-android28-clang'
    args.output.mkdir(parents=True, exist_ok=True)
    receipts, packages = {}, []
    with tempfile.TemporaryDirectory(prefix='ocean-official-repairs-') as temporary:
        work = Path(temporary)
        zlib = source('zlib', work, receipts)
        pigz = source('pigz', work, receipts)
        zprefix = work / 'zlib-prefix'
        env = dict(os.environ, CC=str(cc), AR=str(tools / 'llvm-ar'), RANLIB=str(tools / 'llvm-ranlib'),
                   CFLAGS='-O2 -fPIC', SOURCE_DATE_EPOCH='0')
        run(['./configure', '--static', '--prefix=' + str(zprefix)], cwd=zlib, env=env)
        run(['make', '-j2', 'install'], cwd=zlib, env=env)
        # Static Android/Bionic executable avoids dependence on a foreign prefix or libc.
        run(['make', '-j2', 'CC=' + str(cc), 'CFLAGS=-O2 -I' + str(zprefix / 'include'),
             'LDFLAGS=-static -Wl,-z,max-page-size=16384 -L' + str(zprefix / 'lib')], cwd=pigz, env=env)
        binary = pigz / 'pigz'
        version = subprocess.check_output(['qemu-aarch64', str(binary), '--version'], stderr=subprocess.STDOUT).decode().strip()
        payload = (bytes(range(256)) + b'Ocean upstream compression round trip\n') * 8192
        for level in ('-1', '-9'):
            compressed = subprocess.check_output(['qemu-aarch64', str(binary), '-p', '2', '-c', level], input=payload)
            if gzip.decompress(compressed) != payload:
                raise RuntimeError('pigz produced invalid gzip data')
            decoded = subprocess.check_output(['qemu-aarch64', str(binary), '-dc'], input=compressed)
            if decoded != payload:
                raise RuntimeError('pigz decompression changed data')
        stage = work / 'pigz-stage'
        prefix = stage / PREFIX.lstrip('/')
        (prefix / 'bin').mkdir(parents=True)
        shutil.copy2(binary, prefix / 'bin/pigz')
        (prefix / 'bin/unpigz').symlink_to('pigz')
        doc = prefix / 'share/doc/pigz'; doc.mkdir(parents=True)
        shutil.copy2(pigz / 'README', doc / 'README')
        # Upstream licensing notices remain unchanged, including bundled zopfli and zlib.
        for name, path in (('pigz', pigz), ('zlib', zlib)):
            for filename in ('LICENSE', 'README', 'README.md'):
                if (path / filename).is_file(): shutil.copy2(path / filename, doc / (name + '-' + filename))
        if (pigz / 'zopfli/COPYING').is_file(): shutil.copy2(pigz / 'zopfli/COPYING', doc / 'zopfli-COPYING')
        packages.append(package('pigz', '2.8-1', stage, args.output,
            'Parallel gzip compiled from official pigz and zlib sources for Ocean Android',
            {k: receipts[k] for k in ('pigz', 'zlib')}, {'qemuAndroidBinary': version, 'gzipRoundTrips': 2}))

        src = source('librsync', work, receipts)
        stage = work / 'librsync-stage'
        common = ['cmake', '-S', str(src), '-DCMAKE_TOOLCHAIN_FILE=' + str(ndk / 'build/cmake/android.toolchain.cmake'),
                  '-DANDROID_ABI=arm64-v8a', '-DANDROID_PLATFORM=android-28',
                  '-DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON', '-DCMAKE_BUILD_TYPE=Release',
                  '-DCMAKE_INSTALL_PREFIX=' + PREFIX, '-DCMAKE_INSTALL_LIBDIR=lib',
                  '-DBUILD_RDIFF=OFF', '-DENABLE_COMPRESSION=OFF', '-DUSE_LIBB2=OFF']
        shared, static = work / 'rsync-shared', work / 'rsync-static'
        run(common + ['-B', str(shared), '-DBUILD_SHARED_LIBS=ON'])
        run(['cmake', '--build', shared, '--target', 'rsync', '-j2'])
        run(['cmake', '--install', shared], env=dict(os.environ, DESTDIR=str(stage)))
        run(common + ['-B', str(static), '-DBUILD_SHARED_LIBS=OFF'])
        run(['cmake', '--build', static, '--target', 'rsync', '-j2'])
        test = ROOT / 'tests/librsync-roundtrip.c'
        executable = work / 'rsync-roundtrip'
        run([cc, '-static', '-DLIBRSYNC_STATIC_DEFINE', '-I' + str(src / 'src'), '-I' + str(static / 'src'),
             test, static / 'librsync.a', '-o', executable])
        testdir = work / 'roundtrip'; testdir.mkdir()
        result = subprocess.check_output(['qemu-aarch64', str(executable)], cwd=testdir, text=True).strip()
        if result != 'signature, delta and patch round trip passed':
            raise RuntimeError('Unexpected librsync test output: ' + result)
        prefix = stage / PREFIX.lstrip('/')
        shutil.copy2(static / 'librsync.a', prefix / 'lib/librsync.a')
        doc = prefix / 'share/doc/librsync'; doc.mkdir(parents=True)
        shutil.copy2(src / 'COPYING', doc / 'COPYING')
        packages.append(package('librsync', '2.3.4-1', stage, args.output,
            'Rsync signature and delta library compiled from official source for Ocean Android',
            {'librsync': receipts['librsync']}, {'qemuAndroidLibraryRoundTrip': result, 'sharedLibraryRuntime': 'not tested'}))
    index = '\n\n'.join(x.pop('index') for x in packages) + '\n'
    (args.output / 'Packages.repaired').write_text(index)
    (args.output / 'provenance.json').write_text(json.dumps({'packages': packages, 'prefix': PREFIX,
        'sourcePolicy': 'Pinned official upstream commits, Android NDK; no imported package binaries',
        'nativeAndroidDeviceTested': False, 'promotion': 'requires canonical signed publication'}, indent=2) + '\n')
    print('Two official-source packages built; static ARM Android payloads executed under QEMU. Live APT is unchanged.')


if __name__ == '__main__':
    main()
