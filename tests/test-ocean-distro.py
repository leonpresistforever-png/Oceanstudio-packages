#!/usr/bin/env python3
"""Exercise the actual distro command with real archives and controlled transport."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'packages/ocean-distro/ocean-distro'


class DistroTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'; self.bin.mkdir()
        self.base = self.root / 'ocean-guests'
        self.proot_base = self.root / 'prefix/var/lib/proot-distro/installed-rootfs/ubuntu'
        self.proot_base.mkdir(parents=True)
        (self.proot_base / 'keep').write_text('Independent proot-distro guest')
        self.archive = self.root / 'rootfs.tar.gz'
        with tarfile.open(self.archive, 'w:gz') as out:
            for name, content in [('etc/os-release', b'ID=ubuntu\n'), ('bin/sh', b'#!/bin/sh\n'), ('usr/bin/env', b'fixture')]:
                item = tarfile.TarInfo(name); item.mode = 0o755; item.size = len(content)
                out.addfile(item, io.BytesIO(content))
        self.sha = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.registry = self.root / 'registry.json'
        self.entries = {key: {'name': key.title(), 'version': 'test', 'arch': 'arm64',
            'url': 'https://upstream.example/' + key + '.tar.gz', 'sha256': self.sha,
            'shell': '/bin/sh', 'pkg_manager': 'test', 'priority': 'test'} for key in ('debian', 'arch', 'ubuntu')}
        self.save_registry()
        for name, body in {
            'proot': '#!/usr/bin/env python3\nimport json,os,sys\nopen(os.environ["CALL_LOG"],"w").write(json.dumps({"argv":sys.argv,"path":os.environ["PATH"]}))\n',
            'curl': '''#!/usr/bin/env python3
import os,sys,shutil
args=sys.argv[1:]; dest=args[args.index('--output')+1]
open(os.environ['URL_LOG'],'a').write(args[-1]+'\\n')
if os.environ.get('BAD_DOWNLOAD') == '1':
    open(dest,'wb').write(b'half download')
else: shutil.copyfile(os.environ['ARCHIVE'],dest)
''',
        }.items():
            p=self.bin/name; p.write_text(body); p.chmod(0o755)
        self.env = dict(os.environ, OCEAN_PREFIX=str(self.root/'prefix'), OCEAN_HOME=str(self.root/'home'),
            OCEAN_DISTRO_DIR=str(self.base), OCEAN_DISTRO_REGISTRY=str(self.registry),
            PATH=str(self.bin)+':'+os.environ['PATH'], ARCHIVE=str(self.archive),
            CALL_LOG=str(self.root/'call.json'), URL_LOG=str(self.root/'urls'))

    def save_registry(self): self.registry.write_text(json.dumps(self.entries))
    def call(self,*args,**env):
        return subprocess.run(['bash',str(SCRIPT),*args],env=dict(self.env,**env),capture_output=True,text=True)

    def test_arch_lookup_is_not_debian_architecture_field(self):
        result=self.call('install','arch'); self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual((self.root/'urls').read_text().strip(),'https://upstream.example/arch.tar.gz')

    def test_case_normalization_and_manager_separation(self):
        result=self.call('install','Ubuntu'); self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue((self.base/'ubuntu/.ocean-installed').is_file())
        self.assertEqual((self.proot_base/'keep').read_text(),'Independent proot-distro guest')
        result=self.call('login','Ubuntu','--','/bin/sh','-c','true')
        self.assertEqual(result.returncode,0,result.stderr)
        invocation=json.loads((self.root/'call.json').read_text())
        self.assertTrue(invocation['argv'][0].startswith(str(self.bin)))
        self.assertIn(str(self.base/'ubuntu'),invocation['argv'])
        self.assertIn('/usr/bin/env',invocation['argv'])
        self.assertTrue(invocation['path'].startswith(str(self.bin)))

    def test_half_download_never_becomes_installed(self):
        result=self.call('install','ubuntu',BAD_DOWNLOAD='1')
        self.assertNotEqual(result.returncode,0)
        self.assertFalse((self.base/'ubuntu').exists())
        self.assertIn('No distribution was installed',result.stderr)

    def test_failed_extraction_does_not_leave_installed_directory(self):
        self.archive.write_bytes(b'not an archive')
        self.entries['ubuntu']['sha256']=hashlib.sha256(self.archive.read_bytes()).hexdigest();self.save_registry()
        result=self.call('install','ubuntu')
        self.assertNotEqual(result.returncode,0)
        self.assertFalse((self.base/'ubuntu').exists())
        self.assertEqual(list(self.base.glob('.install-*')),[])

    def test_existing_guest_preserved_and_names_cannot_escape(self):
        self.assertEqual(self.call('install','ubuntu').returncode,0)
        (self.base/'ubuntu/my-data').write_text('keep')
        self.assertNotEqual(self.call('install','ubuntu').returncode,0)
        self.assertEqual((self.base/'ubuntu/my-data').read_text(),'keep')
        self.assertNotEqual(self.call('remove','../prefix').returncode,0)
        self.assertTrue((self.proot_base/'keep').exists())

    def test_missing_digest_fails_before_network(self):
        self.entries['ubuntu']['sha256']='skip';self.save_registry()
        self.assertNotEqual(self.call('install','ubuntu').returncode,0)
        self.assertFalse((self.root/'urls').exists())


if __name__=='__main__': unittest.main()
