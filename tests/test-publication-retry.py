#!/usr/bin/env python3
"""Real Git race tests; package/signature integrity has separate dpkg/GPG tests."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from publish_apt_snapshot import git, publish


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ocean-publication-race-')
        self.root = Path(self.temp.name)
        self.remote = self.root / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '--initial-branch=main', self.remote],
                       check=True, capture_output=True)
        self.worker, self.peer = self.root / 'worker', self.root / 'peer'
        subprocess.run(['git', 'clone', self.remote, self.worker], check=True, capture_output=True)
        for name in ('apt/pool', 'apt/dists/stable', 'staging'):
            (self.worker / name).mkdir(parents=True, exist_ok=True)
        (self.worker / 'apt/pool/ocean-tools.txt').write_text('preserve existing package')
        (self.worker / 'apt/dists/stable/Packages').write_text('previous snapshot')
        (self.worker / 'staging/original.txt').write_text('original staged package')
        self.commit(self.worker, 'initial')
        git(self.worker, 'push', 'origin', 'main')
        subprocess.run(['git', 'clone', self.remote, self.peer], check=True, capture_output=True)

    def tearDown(self):
        self.temp.cleanup()

    def commit(self, root, message):
        git(root, 'add', '.')
        git(root, '-c', 'user.name=Ocean fixture', '-c', 'user.email=test@example.invalid',
            'commit', '-m', message)

    def advance_peer(self):
        (self.peer / 'staging/concurrent.txt').write_text('new package from another contributor')
        self.commit(self.peer, 'another contributor stages a package')
        git(self.peer, 'push', 'origin', 'main')

    def test_rejected_push_rebuilds_from_new_main_and_preserves_all_packages(self):
        inventories = []

        def rebuild(root, attempt):
            inventory = sorted(p.name for p in (root / 'staging').iterdir())
            inventories.append(inventory)
            (root / 'apt/dists/stable/Packages').write_text('\n'.join(inventory))
            if attempt == 1:
                self.advance_peer()

        result = publish(self.worker, rebuild)
        self.assertEqual(result['attempts'], 2)
        self.assertEqual(inventories, [['original.txt'], ['concurrent.txt', 'original.txt']])
        git(self.peer, 'pull', '--ff-only')
        self.assertEqual((self.peer / 'apt/pool/ocean-tools.txt').read_text(), 'preserve existing package')
        self.assertEqual((self.peer / 'apt/dists/stable/Packages').read_text(),
                         'concurrent.txt\noriginal.txt')
        # The losing signed commit was not rebased or merged into the result.
        self.assertEqual(git(self.peer, 'rev-list', '--count', 'HEAD').stdout.strip(), '3')

    def test_failed_validation_does_not_publish_any_snapshot(self):
        before = git(self.peer, 'rev-parse', 'HEAD').stdout

        def rebuild(root, attempt):
            raise ValueError('invalid dependency')

        with self.assertRaisesRegex(ValueError, 'invalid dependency'):
            publish(self.worker, rebuild)
        git(self.peer, 'fetch', 'origin', 'main')
        self.assertEqual(git(self.peer, 'rev-parse', 'FETCH_HEAD').stdout, before)

    def test_retry_limit_never_forces_over_another_contributor(self):
        def rebuild(root, attempt):
            (root / 'apt/dists/stable/Packages').write_text('candidate')
            self.advance_peer()

        with self.assertRaisesRegex(RuntimeError, 'bounded retries'):
            publish(self.worker, rebuild, attempts=1)
        git(self.peer, 'fetch', 'origin', 'main')
        self.assertEqual(git(self.peer, 'rev-parse', 'FETCH_HEAD').stdout,
                         git(self.peer, 'rev-parse', 'HEAD').stdout)

    def test_user_changes_are_not_reset(self):
        path = self.worker / 'apt/pool/ocean-tools.txt'
        path.write_text('uncommitted user work')
        with self.assertRaisesRegex(ValueError, 'clean tracked checkout'):
            publish(self.worker, lambda root, attempt: self.fail('must not rebuild'))
        self.assertEqual(path.read_text(), 'uncommitted user work')


if __name__ == '__main__':
    unittest.main()
