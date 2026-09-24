#!/usr/bin/env python3
"""Guest path tests: an absolute guest symlink is not a host filesystem path."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('rootfs_inspector',
    Path(__file__).resolve().parents[1] / 'scripts/verify-rootfs-candidates.py')
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


class GuestPaths(unittest.TestCase):
    def test_alpine_absolute_busybox_and_usrmerge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'usr/bin').mkdir(parents=True)
            (root / 'bin').symlink_to('usr/bin')
            (root / 'usr/bin/busybox').write_bytes(b'guest executable')
            (root / 'usr/bin/sh').symlink_to('/bin/busybox')
            self.assertEqual(inspector.rooted_path(root, '/bin/sh').read_bytes(), b'guest executable')

    def test_parent_navigation_stays_inside_guest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'bin').mkdir()
            (root / 'shell').write_text('guest')
            (root / 'bin/sh').symlink_to('../../../../shell')
            self.assertEqual(inspector.rooted_path(root, '/bin/sh'), root / 'shell')

    def test_cyclic_links_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'a').symlink_to('/b')
            (root / 'b').symlink_to('/a')
            with self.assertRaisesRegex(ValueError, 'cycle'):
                inspector.rooted_path(root, '/a')


if __name__ == '__main__':
    unittest.main()
