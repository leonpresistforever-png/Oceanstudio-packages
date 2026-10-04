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
import tarfile
import urllib.request
import re

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'sources/mobile-runtime-additions/manifest.json'
PREFIX = '/data/data/studio.ocean.app/files/usr'


def run(command, **kwargs):
    return subprocess.run([str(x) for x in command], check=True, **kwargs)


def fetch(item, directory):
    if 'sha256' in item:
        payload = urllib.request.urlopen(item['url'], timeout=90).read()
        if hashlib.sha256(payload).hexdigest() != item['sha256']:
            raise RuntimeError('Official source archive digest mismatch')
        archive = directory.parent / (item['name'] + '.tar.gz')
        archive.write_bytes(payload)
        with tarfile.open(archive) as bundle:
            bundle.extractall(directory.parent, filter='data')
        (directory.parent / (item['name'] + '-' + item['version'])).rename(directory)
        return
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
    # Verify load-segment alignment from the bytes, independently of build flags.
    import struct
    data = path.read_bytes()
    if data[:6] != b'\x7fELF\x02\x01':
        raise RuntimeError('Expected ELF64 little-endian')
    start = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    for index in range(count):
        offset = start + size * index
        if struct.unpack_from('<I', data, offset)[0] == 1:
            alignment = struct.unpack_from('<Q', data, offset + 48)[0]
            if alignment < 16384:
                raise RuntimeError('ELF cannot load on a 16 KiB page device: ' + str(path))


def build_ollama(item, source, install, work, ndk, tools, jobs):
    # Upstream searches ../lib/ollama relative to its real executable on Android.
    # Keep that layout instead of replacing the CLI with a success-printing stub.
    path = source / 'mlx/mlx.go'
    original = path.read_text()
    needle = '// #cgo LDFLAGS: -lstdc++'
    if original.count(needle) != 1:
        raise RuntimeError('Upstream Ollama C++ linkage changed')
    path.write_text(original.replace(needle, '// #cgo !android LDFLAGS: -lstdc++'))
    prefix = install / PREFIX.lstrip('/')
    (prefix / 'bin').mkdir(parents=True)
    env = dict(os.environ, GOOS='android', GOARCH='arm64', CGO_ENABLED='1', GOMAXPROCS='2',
               CC=str(tools / 'aarch64-linux-android28-clang'), CXX=str(tools / 'aarch64-linux-android28-clang++'),
               CGO_LDFLAGS='-static-libstdc++ -lc++_static -lc++abi -Wl,-z,max-page-size=16384')
    run(['go', 'build', '-p', '2', '-trimpath', '-tags', 'netgo osusergo', '-buildmode=pie',
         '-ldflags', '-s -w -X github.com/ollama/ollama/version.Version=' + item['version'] +
         ' -extldflags=-Wl,-z,max-page-size=16384', '-o', prefix / 'bin/ollama', '.'], cwd=source, env=env)
    llama = work / 'ollama-llama'
    fetch({'name': 'ollama-llama', 'url': 'https://github.com/ggml-org/llama.cpp.git', 'commit': item['llamaCommit']}, llama)
    build = work / 'ollama-backend-build'
    run(['cmake', '-S', source / 'llama/server', '-B', build,
         '-DFETCHCONTENT_SOURCE_DIR_LLAMA_CPP=' + str(llama),
         '-DCMAKE_TOOLCHAIN_FILE=' + str(ndk / 'build/cmake/android.toolchain.cmake'),
         '-DANDROID_ABI=arm64-v8a', '-DANDROID_PLATFORM=android-28', '-DANDROID_STL=c++_static',
         '-DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON', '-DCMAKE_BUILD_TYPE=Release',
         '-DBUILD_SHARED_LIBS=OFF', '-DGGML_NATIVE=OFF', '-DGGML_CPU_ARM_ARCH=armv8-a',
         '-DGGML_OPENMP=OFF', '-DGGML_BACKEND_DL=OFF', '-DGGML_CPU_ALL_VARIANTS=OFF',
         '-DCMAKE_EXE_LINKER_FLAGS=-Wl,-z,max-page-size=16384'])
    run(['cmake', '--build', build, '--target', 'llama-server', '--parallel', jobs])
    backend = next(build.rglob('llama-server'))
    destination = prefix / 'lib/ollama/llama-server'
    destination.parent.mkdir(parents=True)
    shutil.copy2(backend, destination)
    run([tools / 'llvm-strip', destination])


def build_mandoc(source, install, tools, jobs):
    # Configure's test executables cannot run on an x86 CI host. Test compile/link
    # against Bionic for symbol availability; use upstream compatibility routines
    # for behavioral tests and BSD-only APIs rather than host libc results.
    configure = (source / 'configure').read_text()
    variables = set(re.findall(r'^HAVE_([A-Z0-9_]+)=', configure, re.M))
    compiler = tools / 'aarch64-linux-android28-clang'
    detected = {key: 0 for key in variables}
    for test, key in re.findall(r'^runtest\s+(\S+)\s+(\w+)', configure, re.M):
        path = source / ('test-' + test + '.c')
        if not path.exists() or key not in detected: continue
        result = subprocess.run([str(compiler), '-D_GNU_SOURCE', '-Werror', str(path), '-o', str(source / 'probe')],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        detected[key] = int(result.returncode == 0)
    for key in ['FTS', 'FTS_COMPARE_CONST', 'LESS_T', 'REWB_BSD', 'REWB_SYSV', 'PLEDGE', 'SANDBOX_INIT', 'DIRENT_NAMLEN']:
        detected[key] = 0
    detected['WCHAR'] = 1
    settings = ['CC="' + str(compiler) + '"', 'AR="' + str(tools / 'llvm-ar') + '"',
                'CFLAGS="-O2 -D_GNU_SOURCE"', 'LDFLAGS="-Wl,-z,max-page-size=16384"',
                'STATIC="-Wl,-z,now"', 'PREFIX="' + PREFIX + '"', 'BINM_PAGER="more"',
                'UTF8_LOCALE="C.UTF-8"', 'MANPATH_BASE="' + PREFIX + '/share/man"',
                'MANPATH_DEFAULT="' + PREFIX + '/share/man"']
    settings += ['HAVE_' + key + '=' + str(value) for key, value in sorted(detected.items())]
    (source / 'configure.local').write_text('\n'.join(settings) + '\n')
    run(['sh', 'configure'], cwd=source)
    run(['make', '-j', jobs, 'mandoc', 'demandoc'], cwd=source)
    prefix = install / PREFIX.lstrip('/')
    (prefix / 'bin').mkdir(parents=True)
    for name in ['mandoc', 'demandoc']:
        shutil.copy2(source / name, prefix / 'bin' / name)
    # Upstream's single real mandoc executable dispatches makewhatis by argv[0].
    (prefix / 'bin/makewhatis').symlink_to('mandoc')


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
            if item['name'] == 'ollama':
                build_ollama(item, source, install, work, ndk, tools, args.jobs)
            elif item['name'] == 'mandoc':
                build_mandoc(source, install, tools, args.jobs)
            elif item['name'] == 'ffmpeg':
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
                if package == 'ollama-cli':
                    for relative in ['bin/ollama', 'lib/ollama/llama-server']:
                        built = prefix / relative
                        validate_elf(built, tools / 'llvm-readelf')
                        (dest / relative).parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(built, dest / relative)
                elif package == 'mandoc':
                    (dest / 'bin').mkdir(parents=True)
                    for binary in ['mandoc', 'demandoc', 'makewhatis']:
                        validate_elf((prefix / 'bin' / binary).resolve(), tools / 'llvm-readelf')
                        shutil.copy2(prefix / 'bin' / binary, dest / 'bin' / binary, follow_symlinks=False)
                elif package == 'ocean-llama-runtime':
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
                relations = 'Provides: ollama\n' if package == 'ollama-cli' else ''
                (control / 'control').write_text(
                    f"Package: {package}\nVersion: {item['version']}-1+ocean1\nArchitecture: aarch64\n"
                    'Maintainer: OceanStudio <packages@ocean.studio>\nSection: libs\nPriority: optional\n'
                    + dependency_field + relations + f"Homepage: {item['url'].removesuffix('.git')}\n"
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
    data['sources'].sort(key=lambda item: {'mbedtls': 0, 'ffmpeg': 1, 'libwebsockets': 2, 'llama.cpp': 3, 'ollama': 4, 'mandoc': 5}[item['name']])
    # The manifest itself remains immutable. build() follows its declared order.
    if data['sources'] != json.loads(MANIFEST.read_text())['sources']:
        raise SystemExit('Manifest must declare mbedtls before ffmpeg.')
    build(arguments)
