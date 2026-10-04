#!/usr/bin/env python3
"""Stage upstream Android libraries, FFmpeg and llama-server; never publish implicitly."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'sources/mobile-runtime-additions/manifest.json'
PREFIX = '/data/data/studio.ocean.app/files/usr'


def run(command, **kwargs):
    return subprocess.run([str(x) for x in command], check=True, **kwargs)


def fetch(item, directory):
    run(['git', 'init', directory])
    run(['git', '-C', directory, 'fetch', '--depth=1', item['url'], item['commit']])
    run(['git', '-C', directory, 'checkout', '--detach', 'FETCH_HEAD'])
    actual = subprocess.check_output(['git', '-C', directory, 'rev-parse', 'HEAD'], text=True).strip()
    if actual != item['commit']:
        raise RuntimeError('Upstream revision mismatch')
    if item['name'] == 'mbedtls':
        # The framework revision is pinned by the upstream commit's gitlink.
        run(['git', '-C', directory, 'submodule', 'update', '--init', '--depth=1', 'framework'])


def validate_elf(path, readelf):
    text = subprocess.check_output([str(readelf), '-h', '-l', '-d', str(path)], text=True)
    if 'AArch64' not in text or any(value in text for value in ['libc.so.6', 'libm.so.6', 'ld-linux-aarch64']):
        raise RuntimeError('Non-Android ELF rejected: ' + str(path))
    if '/tmp/' in text or '(RPATH)' in text or '(RUNPATH)' in text:
        raise RuntimeError('Build-time library search path rejected: ' + str(path))


def build(args):
    manifest = json.loads(MANIFEST.read_text())
    ndk = args.ndk.resolve()
    tools = ndk / 'toolchains/llvm/prebuilt/linux-x86_64/bin'
    compiler = tools / 'aarch64-linux-android28-clang'
    if not compiler.is_file():
        raise SystemExit('Android NDK with the API 28 AArch64 compiler is required; no packages were built.')
    for command in ['cmake', 'make', 'git', 'dpkg-deb']:
        if shutil.which(command) is None:
            raise SystemExit('Missing build tool: ' + command)
    args.output.mkdir(parents=True, exist_ok=True)
    receipts = []
    with tempfile.TemporaryDirectory(prefix='ocean-mobile-runtime-') as temporary:
        work = Path(temporary)
        installs = {}
        for item in manifest['sources']:
            source = work / item['name']
            fetch(item, source)
            install = work / (item['name'] + '-install')
            install.mkdir()
            installs[item['name']] = install
            if item['name'] == 'ffmpeg':
                mbed = installs['mbedtls'] / PREFIX.lstrip('/')
                configure = [source / 'configure', '--enable-cross-compile', '--arch=aarch64', '--target-os=android',
                             '--cc=' + str(compiler), '--cxx=' + str(tools / 'aarch64-linux-android28-clang++'),
                             '--ar=' + str(tools / 'llvm-ar'), '--ranlib=' + str(tools / 'llvm-ranlib'),
                             '--strip=' + str(tools / 'llvm-strip'), '--prefix=' + PREFIX,
                             '--enable-shared', '--disable-static', '--disable-autodetect', '--disable-doc',
                             '--disable-debug', '--disable-zlib', '--disable-bzlib', '--disable-lzma', '--disable-iconv',
                             '--disable-openssl', '--enable-mbedtls', '--enable-version3', '--extra-cflags=-I' + str(mbed / 'include'),
                             '--extra-ldflags=-L' + str(mbed / 'lib') + ' -Wl,-z,max-page-size=16384']
                run(configure, cwd=source)
                run(['make', '-j', args.jobs], cwd=source)
                run(['make', 'install', 'DESTDIR=' + str(install)], cwd=source)
            else:
                build_dir = work / (item['name'] + '-build')
                options = ['-DCMAKE_TOOLCHAIN_FILE=' + str(ndk / 'build/cmake/android.toolchain.cmake'),
                           '-DANDROID_ABI=arm64-v8a', '-DANDROID_PLATFORM=android-28',
                           '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_INSTALL_PREFIX=' + PREFIX,
                           '-DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON']
                if item['name'] == 'mbedtls':
                    options += ['-DENABLE_PROGRAMS=OFF', '-DENABLE_TESTING=OFF',
                                '-DUSE_STATIC_MBEDTLS_LIBRARY=OFF', '-DUSE_SHARED_MBEDTLS_LIBRARY=ON']
                else:
                    # This build supplies HTTP/WebSocket transport. TLS remains in
                    # the separate Mbed TLS packages; do not claim WSS in this library.
                    options += ['-DLWS_WITH_SHARED=ON', '-DLWS_WITH_STATIC=OFF', '-DLWS_WITH_SSL=OFF',
                                '-DLWS_WITH_ZLIB=OFF', '-DLWS_WITHOUT_TESTAPPS=ON']
                if item['name'] == 'llama.cpp':
                    options = options[:6] + ['-DANDROID_STL=c++_static', '-DBUILD_SHARED_LIBS=OFF',
                                             '-DGGML_OPENMP=OFF', '-DLLAMA_CURL=OFF',
                                             '-DLLAMA_BUILD_TESTS=OFF', '-DLLAMA_BUILD_SERVER=ON']
                run(['cmake', '-S', source, '-B', build_dir] + options)
                run(['cmake', '--build', build_dir, '--parallel', args.jobs])
                run(['cmake', '--install', build_dir], env=dict(os.environ, DESTDIR=str(install)))

            prefix = install / PREFIX.lstrip('/')
            for package in item['packages']:
                stage = work / ('package-' + package)
                dest = stage / PREFIX.lstrip('/')
                depends = []
                if package == 'ocean-llama-runtime':
                    (dest / 'bin').mkdir(parents=True)
                    binary = prefix / 'bin/llama-server'
                    validate_elf(binary, tools / 'llvm-readelf')
                    shutil.copy2(binary, dest / 'bin/llama-server-ocean')
                elif package == 'ocean-ffmpeg-native':
                    (dest / 'bin').mkdir(parents=True)
                    for binary in ['ffmpeg', 'ffprobe']:
                        built = prefix / 'bin' / binary
                        validate_elf(built, tools / 'llvm-readelf')
                        shutil.copy2(built, dest / 'bin' / ('ocean-' + binary))
                    depends = ['libavdevice', 'libavfilter', 'libavformat', 'libavcodec', 'libswresample', 'libswscale', 'libavutil']
                else:
                    (dest / 'lib').mkdir(parents=True)
                    library_name = package.replace('libmbedtls', 'libmbedtls')
                    if package == 'libwebsockets': library_name = 'libwebsockets'
                    files = list((prefix / 'lib').glob(library_name + '.so*'))
                    if not files: raise RuntimeError('No built shared library for ' + package)
                    for library in files:
                        validate_elf(library.resolve(), tools / 'llvm-readelf')
                        shutil.copy2(library, dest / 'lib' / library.name, follow_symlinks=False)
                    mapping = {'libavcodec': ['libavutil', 'libswresample'],
                               'libavformat': ['libavcodec', 'libavutil', 'libmbedtls', 'libmbedx509', 'libmbedcrypto'],
                               'libavdevice': ['libavformat', 'libavcodec', 'libavfilter', 'libavutil'],
                               'libavfilter': ['libavformat', 'libavcodec', 'libswscale', 'libswresample', 'libavutil'],
                               'libswscale': ['libavutil'], 'libswresample': ['libavutil'],
                               'libmbedtls': ['libmbedx509', 'libmbedcrypto'], 'libmbedx509': ['libmbedcrypto']}
                    depends = mapping.get(package, [])
                documentation = dest / 'share/doc' / package
                documentation.mkdir(parents=True)
                for license_name in ['LICENSE', 'LICENSE.md', 'COPYING.LGPLv2.1', 'COPYING.LGPLv3']:
                    license_file = source / license_name
                    if license_file.is_file(): shutil.copy2(license_file, documentation / license_name)
                receipt = dict(item, package=package, target=manifest['target'], physicalDeviceTested=False)
                (documentation / 'ocean-build.json').write_text(json.dumps(receipt, indent=2) + '\n')
                control = stage / 'DEBIAN'
                control.mkdir()
                dependency_field = ('Depends: ' + ', '.join(depends) + '\n') if depends else ''
                (control / 'control').write_text(
                    f"Package: {package}\nVersion: {item['version']}-1+ocean1\nArchitecture: aarch64\n"
                    'Maintainer: OceanStudio <packages@ocean.studio>\nSection: libs\nPriority: optional\n'
                    + dependency_field + f"Homepage: {item['url'].removesuffix('.git')}\n"
                    + f"Description: Upstream Android API 28 build of {package}\n")
                artifact = args.output / f"{package}_{item['version']}-1+ocean1_aarch64.deb"
                run(['dpkg-deb', '--root-owner-group', '-Zxz', '--build', stage, artifact])
                receipt.update(artifact=artifact.name, sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
                receipts.append(receipt)
    (args.output / 'build-receipts.json').write_text(json.dumps(receipts, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ndk', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'staging/mobile-runtime-additions')
    parser.add_argument('--jobs', type=int, default=2)
    arguments = parser.parse_args()
    # Mbed TLS must be installed before FFmpeg's HTTPS feature detection.
    data = json.loads(MANIFEST.read_text())
    data['sources'].sort(key=lambda item: {'mbedtls': 0, 'ffmpeg': 1, 'libwebsockets': 2, 'llama.cpp': 3}[item['name']])
    # The manifest itself remains immutable. build() follows its declared order.
    if data['sources'] != json.loads(MANIFEST.read_text())['sources']:
        raise SystemExit('Manifest must declare mbedtls before ffmpeg.')
    build(arguments)
