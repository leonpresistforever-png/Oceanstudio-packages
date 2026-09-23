import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from forensic_repository import scan_stream, scan_tar, elf_role, file_collisions


class ForensicTests(unittest.TestCase):
    def test_markers_after_old_scan_limit_and_across_chunk_boundary(self):
        marker = b'/data/data/com.termux/files/usr/bin/sh'
        payload = b'x' * (2 * 1024 * 1024 - 7) + marker
        row = scan_stream(io.BytesIO(payload), 'bin/example', True)
        self.assertEqual(row['bytes'], len(payload))
        found = next(x for x in row['findings'] if x['kind'] == 'foreign-app-prefix')
        self.assertEqual(found['offset'], 2 * 1024 * 1024 - 7)

    def test_bytecode_not_misclassified_as_a_native_binary(self):
        self.assertEqual(elf_role('data/data/studio.ocean.app/files/usr/lib/guile/3.0/ccache/a.go', 0, 3), 'guile-vm-bytecode')
        self.assertEqual(elf_role('data/data/studio.ocean.app/files/usr/bin/a', 0, 3), 'native-elf')
        self.assertEqual(elf_role('data/data/studio.ocean.app/files/usr/lib/go/src/runtime/race/a.syso', 62, 1), 'go-cross-target-object')

    def test_even_identical_cross_package_files_need_review(self):
        rows = file_collisions({'bin/a': [
            {'package': 'a', 'content': 'same'}, {'package': 'b', 'content': 'same'}]})
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['sameContent'])

    def test_real_archive_controls_and_truncated_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); stage = root / 'stage'; (stage / 'DEBIAN').mkdir(parents=True)
            (stage / 'DEBIAN/control').write_text('Package: forensic-fixture\nVersion: 1\nArchitecture: all\nMaintainer: Test <test@example.invalid>\nDescription: test\n')
            (stage / 'DEBIAN/postinst').write_text('#!/bin/sh\ncurl https://github.com/termux/example\n')
            (stage / 'DEBIAN/postinst').chmod(0o755)
            (stage / 'usr/bin').mkdir(parents=True); (stage / 'usr/bin/example').write_bytes(b'x' * 20000)
            deb = root / 'test.deb'
            subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(stage), str(deb)], check=True, stdout=subprocess.DEVNULL)
            rows = scan_tar(deb, True)
            self.assertTrue(any(f['kind'] == 'foreign-repository' for r in rows for f in r['findings']))
            self.assertTrue(scan_tar(deb))
            deb.write_bytes(deb.read_bytes()[:100])
            with self.assertRaises(Exception): scan_tar(deb)


if __name__ == '__main__': unittest.main()
