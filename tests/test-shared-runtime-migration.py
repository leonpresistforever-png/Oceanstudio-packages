#!/usr/bin/env python3
"""Use real dpkg databases to reproduce overlap and verify the ownership move.

No maintainer scripts are included or executed. Temporary prefixes and dpkg roots
are used for fixtures. This proves packaging behavior, not Android compatibility.
"""
import hashlib
import getpass
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('builder', ROOT / 'scripts/build-shared-runtime-repairs.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class Migration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ocean-dpkg-test-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'root'
        (self.root / 'var/lib/dpkg').mkdir(parents=True)
        (self.root / 'var/lib/dpkg/status').write_text('')
        self.output = self.base / 'packages'
        self.names = ['ocean-test-left', 'ocean-test-right']
        self.source = self.base / 'module.py'
        self.source.write_text('import sys\nprint("Ocean result:", int(sys.argv[2]) * 7)\n')
        self.records = {n: {'Package': n, 'Version': '1.0-1', 'Architecture': 'all',
            'Maintainer': 'Ocean tests <test@ocean.studio>', 'Depends': 'python',
            'Description': 'Original Ocean fixture'} for n in self.names}
        self.recipe = {'source': 'module.py', 'sourceSha256': hashlib.sha256(self.source.read_bytes()).hexdigest(),
            'package': 'ocean-test-runtime', 'version': '1.0-1', 'commands': self.names,
            'installPath': b.PREFIX.lstrip('/') + '/lib/test/shared.py'}
        # An actual dependency package owns a Python link for host-only execution.
        control = 'Package: python\nVersion: 3.12\nArchitecture: all\nMaintainer: Test <test@ocean.studio>\nDescription: Host-only test dependency\n'
        python = b.build_archive('python', '3.12', 'all', control, {}, self.output)
        self.dpkg('--install', python)
        py = self.root / b.PREFIX.lstrip('/') / 'bin/python'
        py.parent.mkdir(parents=True, exist_ok=True)
        py.symlink_to(sys.executable)

    def dpkg(self, *args, success=True):
        r = subprocess.run(['dpkg', '--force-not-root', '--root=' + str(self.root), *map(str, args)],
            text=True, capture_output=True)
        if success and r.returncode:
            self.fail(r.stdout + '\n' + r.stderr)
        return r

    def old(self, name):
        c = f'Package: {name}\nVersion: 1.0-1\nArchitecture: all\nMaintainer: Test <test@ocean.studio>\nDepends: python\nDescription: Original fixture\n'
        return b.build_archive(name, '1.0-1', 'all', c,
            {self.recipe['installPath']: (self.source.read_bytes(), 0o644),
             b.PREFIX + '/bin/' + name: (b'#!/system/bin/sh\nexit 0\n', 0o755)}, self.output)

    def new(self):
        return b.build_group(self.recipe, self.records, self.base, self.output)

    def execute(self, name):
        prefix = self.root / b.PREFIX.lstrip('/')
        r = subprocess.run(['sh', str(prefix / 'bin' / name), '6'],
            env={**os.environ, 'PREFIX': str(prefix)}, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), 'Ocean result: 42')

    def test_old_identical_files_reproduce_dpkg_overwrite_failure(self):
        self.dpkg('--install', self.old(self.names[0]))
        result = self.dpkg('--install', self.old(self.names[1]), success=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('trying to overwrite', result.stderr)

    def test_fresh_install_two_commands_and_remove_one(self):
        self.dpkg('--install', *self.new())
        for name in self.names:
            self.execute(name)
        self.dpkg('--remove', self.names[0])
        self.execute(self.names[1])
        owned = self.dpkg('--search', '/' + self.recipe['installPath']).stdout
        self.assertIn('ocean-test-runtime:', owned)
        self.assertNotIn(self.names[0] + ':', owned)

    def test_upgrade_from_old_owner_and_install_second_command(self):
        self.dpkg('--install', self.old(self.names[0]))
        self.dpkg('--auto-deconfigure', '--install', *self.new())
        for name in self.names:
            self.execute(name)
        self.dpkg('--remove', self.names[0])
        self.execute(self.names[1])

    def test_repeated_source_build_is_byte_reproducible(self):
        first = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.new()}
        second = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.new()}
        self.assertEqual(first, second)

    def test_real_apt_plans_ownership_migration_without_removing_commands(self):
        self.dpkg('--install', self.old(self.names[1]))
        artifacts = self.new()
        repo = self.base / 'repo'
        repo.mkdir()
        paragraphs = []
        for artifact in artifacts:
            (repo / artifact.name).write_bytes(artifact.read_bytes())
            control = subprocess.check_output(['dpkg-deb', '-f', str(artifact)], text=True)
            paragraphs.append(control.strip() + '\nFilename: ' + artifact.name +
                '\nSize: ' + str(artifact.stat().st_size) + '\nSHA256: ' + b.sha256(artifact) + '\n')
        (repo / 'Packages').write_text('\n'.join(paragraphs))
        client = self.base / 'apt'
        (client / 'lists/partial').mkdir(parents=True)
        (client / 'cache/archives/partial').mkdir(parents=True)
        # This is an isolated, local test-fixture repository. Production signing
        # is exercised separately by test-index-publication.py and stays required.
        (client / 'sources.list').write_text(f'deb [trusted=yes] file:{repo} ./\n')
        options = ['-o', f'Dir::Etc::sourcelist={client}/sources.list',
            '-o', 'Dir::Etc::sourceparts=-', '-o', f'Dir::State::lists={client}/lists',
            '-o', f'Dir::State::status={self.root}/var/lib/dpkg/status',
            '-o', f'Dir::Cache={client}/cache', '-o', f'APT::Sandbox::User={getpass.getuser()}',
            '-o', 'Debug::NoLocking=true']
        update = subprocess.run(['apt-get', *options, 'update'], capture_output=True, text=True)
        self.assertEqual(update.returncode, 0, update.stdout + update.stderr)
        install = subprocess.run(['apt-get', *options, '--simulate', 'install', self.names[0]],
            capture_output=True, text=True)
        self.assertEqual(install.returncode, 0, install.stdout + install.stderr)
        for name in [*self.names, 'ocean-test-runtime']:
            self.assertIn('Inst ' + name + ' ', install.stdout)
        self.assertNotIn('Remv ', install.stdout)

    def test_changed_source_is_rejected(self):
        self.source.write_text('print("changed")\n')
        with self.assertRaisesRegex(ValueError, 'differs from audited bytes'):
            self.new()


if __name__ == '__main__':
    unittest.main()
