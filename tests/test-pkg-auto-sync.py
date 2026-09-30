#!/usr/bin/env python3
"""Catalogue behavior tests; fake APT never installs packages or uses the network."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

PKG = Path(__file__).resolve().parents[1] / 'packages/ocean-pkg/pkg'

class CatalogueSync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.prefix = self.root / 'usr'
        self.lists = self.prefix / 'var/lib/apt/lists'
        self.lists.mkdir(parents=True)
        bins = self.root / 'fake-bin'
        bins.mkdir()
        self.log = self.root / 'calls'
        bash_bin = shutil.which('bash') or '/bin/bash'
        cat_bin = shutil.which('cat') or '/bin/cat'
        apt = bins / 'apt-get'
        apt.write_text(f'''#!{bash_bin}
printf '%s\\n' "$*" >> "$CALL_LOG"
if [[ "$1" == update ]]; then
  [[ "${{FAIL_UPDATE:-0}}" == 0 ]] || exit 100
  [[ "${{EMPTY_UPDATE:-0}}" == 0 ]] || exit 0
  printf 'Package: example\\n' > "$PREFIX/var/lib/apt/lists/ocean_Packages"
  exit 0
fi
exit "${{COMMAND_STATUS:-0}}"
''')
        apt.chmod(0o755)
        (bins / 'apt-cache').symlink_to('apt-get')
        # The cloud executor uses a PID namespace different from its /proc mount.
        # Only normalize stat reads in this fixture; these tests do not test locks.
        cat = bins / 'cat'
        cat.write_text(f'''#!{bash_bin}
case "$1" in /proc/*/stat) exec {cat_bin} /proc/self/stat;; *) exec {cat_bin} "$@";; esac
''')
        cat.chmod(0o755)
        self.env = dict(os.environ, PREFIX=str(self.prefix),
            PATH=f'{bins}:' + os.environ['PATH'], CALL_LOG=str(self.log),
            OCEAN_PKG_LOCK_WAIT='0')

    def run_pkg(self, *args, **env):
        return subprocess.run(['bash', str(PKG), *args], env=dict(self.env, **env),
                              text=True, capture_output=True)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def old_index(self, suffix=''):
        index = self.lists / ('ocean_Packages' + suffix)
        index.write_text('Package: example\n')
        os.utime(index, (time.time() - 172800,) * 2)
        return index

    def test_first_install_refreshes_and_preserves_arguments(self):
        result = self.run_pkg('install', 'example', '--no-install-recommends')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.calls()[0].startswith('update '))
        self.assertEqual(self.calls()[1], 'install example --no-install-recommends')

    def test_recent_refresh_reused(self):
        self.assertEqual(self.run_pkg('update').returncode, 0)
        self.assertEqual(self.run_pkg('search', 'example').returncode, 0)
        self.assertEqual(len(self.calls()), 2)
        self.assertEqual(self.calls()[1], 'search example')

    def test_stale_index_refreshes(self):
        self.old_index()
        self.assertEqual(self.run_pkg('show', 'example').returncode, 0)
        self.assertTrue(self.calls()[0].startswith('update '))

    def test_offline_empty_index_stops_install(self):
        result = self.run_pkg('install', 'example', FAIL_UPDATE='1')
        self.assertEqual(result.returncode, 100)
        self.assertEqual(len(self.calls()), 1)
        self.assertIn('Connect to the internet', result.stderr)

    def test_offline_cached_lists_remain_usable_with_backoff(self):
        self.old_index('.lz4')
        self.assertEqual(self.run_pkg('search', 'example', FAIL_UPDATE='1').returncode, 0)
        self.assertEqual(self.run_pkg('show', 'example', FAIL_UPDATE='1').returncode, 0)
        self.assertEqual(sum(c.startswith('update ') for c in self.calls()), 1)
        self.assertEqual(self.calls()[-1], 'show example')

    def test_missing_index_refreshes_despite_success_stamp(self):
        self.assertEqual(self.run_pkg('update').returncode, 0)
        (self.lists / 'ocean_Packages').unlink()
        self.assertEqual(self.run_pkg('install', 'example').returncode, 0)
        self.assertEqual(sum(c.startswith('update ') for c in self.calls()), 2)

    def test_install_exit_status_is_preserved(self):
        self.assertEqual(self.run_pkg('install', 'example', COMMAND_STATUS='42').returncode, 42)

    def test_inrelease_only_success_does_not_claim_catalogue_success(self):
        result = self.run_pkg('update', EMPTY_UPDATE='1')
        self.assertEqual(result.returncode, 100)
        self.assertIn('no Packages index', result.stderr)
        self.assertFalse((self.prefix / 'var/lib/ocean-pkg/last-success').exists())

    def test_empty_update_never_proceeds_to_install(self):
        result = self.run_pkg('install', 'ocean-glibc', EMPTY_UPDATE='1')
        self.assertEqual(result.returncode, 100)
        self.assertEqual(len(self.calls()), 1)

    def test_paths_uses_the_actual_ocean_prefix(self):
        result = self.run_pkg('paths')
        self.assertEqual(result.returncode, 0)
        self.assertIn(str(self.prefix / 'etc/apt'), result.stdout)
        self.assertIn(str(self.lists), result.stdout)
        self.assertEqual(self.calls(), [])

if __name__ == '__main__':
    unittest.main()
