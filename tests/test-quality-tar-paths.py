import sys
from pathlib import Path
import subprocess
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from package_quality import assess_deb

class TarPathTests(unittest.TestCase):
    def test_dpkg_dot_paths_are_read_and_stub_check_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root / 'stage'
            (stage / 'DEBIAN').mkdir(parents=True)
            (stage / 'DEBIAN/control').write_text('Package: python-test-library\nVersion: 1.0\nArchitecture: all\nMaintainer: Ocean <ocean@example.test>\nSection: python\nDescription: Real test library\n')
            skill = stage / 'data/data/studio.ocean.app/files/usr/lib/ocean-python/site-packages/sdk/.agents/skills/usage/SKILL.md'
            skill.parent.mkdir(parents=True)
            for content, rejected in [('Use the documented Python interface to process input. ' * 30, False), ('short', True)]:
                skill.write_text(content)
                archive = root / 'test.deb'
                subprocess.run(['dpkg-deb', '--threads-max=1', '--build', str(stage), str(archive)], check=True, stdout=subprocess.DEVNULL)
                self.assertEqual(rejected, assess_deb(archive).reject)

if __name__ == '__main__':
    unittest.main()
