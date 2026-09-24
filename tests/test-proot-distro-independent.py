#!/usr/bin/env python3
"""Exercise actual independent manager commands with real guest archives."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ocean_distro_tests', ROOT/'tests/test-ocean-distro.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
SCRIPT = ROOT/'packages/proot-distro/proot-distro'


class IndependentManagerTests(fixtures.DistroTests):
    # Reuse only fixture construction; own assertions cover public command behavior.
    def setUp(self):
        super().setUp()
        self.ocean = self.base
        (self.ocean/'ubuntu/etc').mkdir(parents=True)
        (self.ocean/'ubuntu/keep').write_text('Ocean guest must survive')
        self.base = self.root/'independent/installed-rootfs'
        self.env['OCEAN_PROOT_DISTRO_DIR'] = str(self.root/'independent')
        self.env['OCEAN_PROOT_DISTRO_REGISTRY'] = str(self.registry)

    def call(self, *args, **env):
        return subprocess.run(['bash', str(SCRIPT), *args], env=dict(self.env, **env), capture_output=True, text=True)

    def test_case_normalization_and_manager_separation(self):
        # There is no ocean-distro executable in the fixture PATH.
        result = self.call('install', 'Ubuntu')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.base/'ubuntu/.ocean-proot-installed').is_file())
        result = self.call('login', 'Ubuntu', '--', '/bin/sh', '-c', 'true')
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = json.loads((self.root/'call.json').read_text())['argv']
        self.assertIn(str(self.base/'ubuntu'), argv)
        self.assertNotIn(str(self.ocean/'ubuntu'), argv)
        self.assertEqual(self.call('remove', 'ubuntu').returncode, 0)
        self.assertEqual((self.ocean/'ubuntu/keep').read_text(), 'Ocean guest must survive')

    def test_clear_cache_leaves_both_guests_and_ocean_cache(self):
        self.assertEqual(self.call('install', 'ubuntu').returncode, 0)
        (self.ocean/'.downloads').mkdir()
        (self.ocean/'.downloads/keep').write_text('Ocean cache')
        self.assertEqual(self.call('clear-cache').returncode, 0)
        self.assertFalse((self.root/'independent/dl-cache').exists())
        self.assertTrue((self.base/'ubuntu/etc').exists())
        self.assertEqual((self.ocean/'.downloads/keep').read_text(), 'Ocean cache')

    def test_failed_reset_keeps_original_guest(self):
        self.assertEqual(self.call('install', 'ubuntu').returncode, 0)
        (self.base/'ubuntu/keep').write_text('PRoot user data')
        self.assertEqual(self.call('clear-cache').returncode, 0)
        result = self.call('reset', 'Ubuntu', BAD_DOWNLOAD='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.base/'ubuntu/keep').read_text(), 'PRoot user data')
        self.assertTrue((self.ocean/'ubuntu/keep').exists())

    def test_reset_only_replaces_selected_proot_guest(self):
        self.assertEqual(self.call('install', 'ubuntu').returncode, 0)
        (self.base/'ubuntu/old').write_text('reset requested')
        result = self.call('reset', 'ubuntu')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.base/'ubuntu/old').exists())
        self.assertTrue((self.base/'ubuntu/etc/os-release').is_file())
        self.assertTrue((self.ocean/'ubuntu/keep').exists())

    def test_backup_restore_retains_data_without_ocean_changes(self):
        self.assertEqual(self.call('install', 'ubuntu').returncode, 0)
        (self.base/'ubuntu/user-file').write_text('independent data')
        archive = str(self.root/'guest.tar')
        result = self.call('backup', 'ubuntu', '--output', archive)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(self.call('restore', archive).returncode, 0)
        self.assertEqual(self.call('remove', 'ubuntu').returncode, 0)
        result = self.call('restore', archive)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.base/'ubuntu/user-file').read_text(), 'independent data')
        self.assertTrue((self.ocean/'ubuntu/keep').exists())

    def test_rename_keeps_login_registry_and_ocean_state(self):
        self.assertEqual(self.call('install', 'ubuntu').returncode, 0)
        self.assertEqual(self.call('rename', 'ubuntu', 'my-ubuntu').returncode, 0)
        result = self.call('login', 'my-ubuntu', '--', '/bin/sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.base/'my-ubuntu'), json.loads((self.root/'call.json').read_text())['argv'])
        self.assertTrue((self.ocean/'ubuntu/keep').exists())

    def test_shared_state_and_host_symlink_are_rejected(self):
        for path in (self.ocean, self.ocean/'nested', self.root):
            result = self.call('clear-cache', OCEAN_PROOT_DISTRO_DIR=str(path))
            self.assertNotEqual(result.returncode, 0)
        self.base.mkdir(parents=True)
        (self.base/'ubuntu').symlink_to(self.ocean/'ubuntu', target_is_directory=True)
        self.assertNotEqual(self.call('remove', 'ubuntu').returncode, 0)
        self.assertTrue((self.ocean/'ubuntu/keep').exists())


if __name__ == '__main__':
    unittest.main()
