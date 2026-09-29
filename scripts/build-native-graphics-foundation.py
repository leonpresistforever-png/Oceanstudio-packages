#!/usr/bin/env python3
"""Build native Ocean graphics development packages from pinned upstream commits."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = Path('/data/data/studio.ocean.app/files/usr')
SOURCES = {
    'glm': ('https://github.com/g-truc/glm.git', '1.0.3', '8d1fd52e5ab5590e2c81768ace50c72bae28f2ed'),
    'imgui': ('https://github.com/ocornut/imgui.git', 'v1.92.9b', 'f1cc2ae15e53a861a874c3034aae6798fde194ab'),
    'assimp': ('https://github.com/assimp/assimp.git', 'v6.0.5', '392a658f9c271be965271f45e7521a1b80ea4392'),
}


def run(*args, **kwargs):
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def fetch(key, work):
    url, tag, commit = SOURCES[key]
    path = work / key
    run('git', 'clone', '--quiet', '--depth=1', '--branch', tag, url, path)
    actual = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != commit:
        raise RuntimeError(f'{key} upstream tag changed: {actual} != {commit}')
    return path


def control(stage, name, version, architecture, description, depends='', homepage=''):
    debian = stage / 'DEBIAN'
    debian.mkdir()
    fields = [f'Package: {name}', f'Version: {version}', f'Architecture: {architecture}',
              'Maintainer: OceanStudio <packages@ocean.studio>', 'Section: devel',
              'Priority: optional']
    if depends:
        fields.append('Depends: ' + depends)
    if homepage:
        fields.append('Homepage: ' + homepage)
    fields.append('Description: ' + description)
    (debian / 'control').write_text('\n'.join(fields) + '\n')


def package(pool, stage, name, version, architecture):
    result = pool / f'{name}_{version}_{architecture}.deb'
    run('dpkg-deb', '--root-owner-group', '-Zxz', '-z6', '--build', stage, result)
    return {'package': name, 'version': version, 'file': result.name,
            'sha256': hashlib.sha256(result.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ndk', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'staging/native-graphics-foundation')
    args = parser.parse_args()
    ndk = args.ndk.resolve()
    if 'Pkg.Revision = 27.0.12077973' not in (ndk / 'source.properties').read_text():
        raise RuntimeError('Android NDK 27.0.12077973 is required')
    args.output.mkdir(parents=True, exist_ok=True)
    pool = args.output / 'pool/main'
    pool.mkdir(parents=True, exist_ok=True)
    receipts = []
    with tempfile.TemporaryDirectory(prefix='ocean-graphics-') as temporary:
        work = Path(temporary)
        glm = fetch('glm', work)
        stage = work / 'stage-glm'
        include = stage / PREFIX.relative_to('/') / 'include'
        shutil.copytree(glm / 'glm', include / 'glm', ignore=shutil.ignore_patterns('*.cpp', '*.vcxproj', '*.filters', 'CMakeLists.txt'))
        doc = stage / PREFIX.relative_to('/') / 'share/doc/glm'
        doc.mkdir(parents=True)
        shutil.copy2(glm / 'copying.txt', doc / 'copyright')
        control(stage, 'glm', '1.0.3-1+ocean1', 'all', 'Official GLM C++ graphics mathematics headers for Ocean', homepage=SOURCES['glm'][0])
        receipts.append(package(pool, stage, 'glm', '1.0.3-1+ocean1', 'all'))

        imgui = fetch('imgui', work)
        stage = work / 'stage-imgui'
        prefix = stage / PREFIX.relative_to('/')
        include = prefix / 'include/imgui'
        library = prefix / 'lib'
        include.mkdir(parents=True)
        library.mkdir(parents=True)
        sources = ['imgui.cpp', 'imgui_draw.cpp', 'imgui_tables.cpp', 'imgui_widgets.cpp']
        headers = ['imgui.h', 'imconfig.h', 'imgui_internal.h', 'imstb_rectpack.h', 'imstb_textedit.h', 'imstb_truetype.h']
        for name in headers: shutil.copy2(imgui / name, include / name)
        toolchain = ndk / 'toolchains/llvm/prebuilt/linux-x86_64/bin'
        cxx = toolchain / 'aarch64-linux-android28-clang++'
        objects = []
        for name in sources:
            obj = work / (name + '.o')
            run(cxx, '-std=c++17', '-O2', '-fPIC', '-ffile-prefix-map=' + str(work) + '=/usr/src/ocean',
                '-I' + str(imgui), '-c', imgui / name, '-o', obj)
            objects.append(obj)
        run(toolchain / 'llvm-ar', 'rcs', library / 'libimgui.a', *objects)
        pc = library / 'pkgconfig'
        pc.mkdir()
        (pc / 'imgui.pc').write_text(f'prefix={PREFIX}\nlibdir=${{prefix}}/lib\nincludedir=${{prefix}}/include/imgui\n'
                                    'Name: imgui\nDescription: Dear ImGui core (application supplies a renderer backend)\n'
                                    'Version: 1.92.9b\nLibs: -L${libdir} -limgui -lc++\nCflags: -I${includedir}\n')
        doc = prefix / 'share/doc/imgui'
        doc.mkdir(parents=True)
        shutil.copy2(imgui / 'LICENSE.txt', doc / 'copyright')
        control(stage, 'imgui', '1.92.9b-1+ocean1', 'aarch64',
                'Dear ImGui core headers and native static library for Ocean Android',
                depends='libc++', homepage=SOURCES['imgui'][0])
        receipts.append(package(pool, stage, 'imgui', '1.92.9b-1+ocean1', 'aarch64'))

        assimp = fetch('assimp', work)
        stage = work / 'stage-assimp'
        build = work / 'build-assimp'
        run('cmake', '-S', assimp, '-B', build, '-G', 'Ninja',
            '-DCMAKE_TOOLCHAIN_FILE=' + str(ndk / 'build/cmake/android.toolchain.cmake'),
            '-DANDROID_ABI=arm64-v8a', '-DANDROID_PLATFORM=28',
            '-DCMAKE_INSTALL_PREFIX=' + str(PREFIX), '-DCMAKE_BUILD_TYPE=Release',
            '-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-z,max-page-size=16384',
            '-DASSIMP_BUILD_TESTS=OFF', '-DASSIMP_BUILD_ASSIMP_TOOLS=OFF',
            '-DASSIMP_BUILD_SAMPLES=OFF', '-DASSIMP_INSTALL=ON',
            '-DASSIMP_WARNINGS_AS_ERRORS=OFF', '-DASSIMP_BUILD_ZLIB=ON',
            '-DBUILD_SHARED_LIBS=ON')
        run('cmake', '--build', build, '--parallel', '2')
        env = dict(os.environ, DESTDIR=str(stage))
        run('cmake', '--install', build, env=env)
        prefix = stage / PREFIX.relative_to('/')
        if not list((prefix / 'lib').glob('libassimp.so*')):
            raise RuntimeError('Assimp native shared library missing')
        for path in (prefix / 'lib').glob('libassimp.so*'):
            if path.is_file() and not path.is_symlink():
                info = subprocess.check_output(['readelf', '-hW', str(path)], text=True)
                if 'AArch64' not in info: raise RuntimeError('Assimp is not AArch64')
        doc = prefix / 'share/doc/assimp'
        doc.mkdir(parents=True, exist_ok=True)
        shutil.copy2(assimp / 'LICENSE', doc / 'copyright')
        control(stage, 'assimp', '6.0.5-1+ocean1', 'aarch64',
                'Official Assimp 3D asset import/export library for Ocean Android',
                depends='libc++', homepage=SOURCES['assimp'][0])
        receipts.append(package(pool, stage, 'assimp', '6.0.5-1+ocean1', 'aarch64'))

        stage = work / 'stage-build-essential'
        doc = stage / PREFIX.relative_to('/') / 'share/doc/build-essential'
        doc.mkdir(parents=True)
        (doc / 'README').write_text('Native Ocean C/C++ development bundle; dependencies provide actual tools.\n')
        control(stage, 'build-essential', '1.0.0-1+ocean1', 'all',
                'Ocean native C and C++ build tool dependency bundle',
                depends='clang, g++, make, cmake, pkg-config, ndk-sysroot')
        receipts.append(package(pool, stage, 'build-essential', '1.0.0-1+ocean1', 'all'))
    (args.output / 'provenance.json').write_text(json.dumps({'sourcePolicy': 'Official upstream commits only; no Termux artifacts',
        'sources': SOURCES, 'packages': receipts, 'deviceRuntimeTested': False}, indent=2) + '\n')
    print(json.dumps(receipts, indent=2))


if __name__ == '__main__': main()
