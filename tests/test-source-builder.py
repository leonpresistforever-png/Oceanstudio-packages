#!/usr/bin/env python3
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'scripts/build-source-packages.py'
spec=importlib.util.spec_from_file_location('builder',SCRIPT)
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

class SourceBuilderTests(unittest.TestCase):
    def test_shards_are_disjoint_and_complete(self):
        expected={x['name'] for x in builder.recipes(ROOT/'sources/recipes.json')}
        actual=[]
        for n in range(3):
            actual.extend(json.loads(subprocess.check_output(['python3',str(SCRIPT),'--plan','--shard-count','3','--shard-index',str(n)],text=True)))
        self.assertEqual(set(actual),expected)
        self.assertEqual(len(actual),len(expected))

    def test_unpinned_source_is_rejected(self):
        data=json.loads((ROOT/'sources/recipes.json').read_text());data[0]['commit']='main'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'recipes.json';path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'pinned'):builder.recipes(path)

    def test_traversal_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'bad.tar';dest=root/'out';dest.mkdir()
            with tarfile.open(archive,'w') as tar:
                entry=tarfile.TarInfo('../escaped');entry.size=1;tar.addfile(entry,io.BytesIO(b'x'))
            with self.assertRaisesRegex(ValueError,'Unsafe'):builder.extract(archive,dest)
            self.assertFalse((root/'escaped').exists())

    def test_host_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage=Path(tmp);(stage/'usr/bin').mkdir(parents=True);(stage/'usr/bin/tool').write_text('host')
            with self.assertRaisesRegex(ValueError,'outside Ocean'):builder.validate_payload(stage,'unused')

    def test_escaping_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage=Path(tmp);prefix=stage/builder.PREFIX.lstrip('/');prefix.mkdir(parents=True)
            (prefix/'bad').symlink_to('/etc/passwd')
            with self.assertRaisesRegex(ValueError,'Escaping'):builder.validate_payload(stage,'unused')

if __name__=='__main__':unittest.main()
