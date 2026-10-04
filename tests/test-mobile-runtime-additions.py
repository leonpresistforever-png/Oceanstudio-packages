#!/usr/bin/env python3
"""Check pinned recipe inputs and that missing NDK never creates publishable artifacts."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MobileRuntimeRecipes(unittest.TestCase):
    def test_pinned_official_sources_and_unique_packages(self):
        manifest = json.loads((ROOT / 'sources/mobile-runtime-additions/manifest.json').read_text())
        packages = []
        official = {'https://github.com/FFmpeg/FFmpeg.git', 'https://github.com/Mbed-TLS/mbedtls.git',
                    'https://github.com/warmcat/libwebsockets.git', 'https://github.com/ggml-org/llama.cpp.git',
                    'https://github.com/ollama/ollama.git', 'https://mandoc.bsd.lv/snapshots/mandoc-1.14.6.tar.gz'}
        for source in manifest['sources']:
            self.assertIn(source['url'], official)
            if 'sha256' in source:
                self.assertRegex(source['sha256'], r'^[a-f0-9]{64}$')
            else:
                self.assertRegex(source['commit'], r'^[a-f0-9]{40}$')
            packages.extend(source['packages'])
        self.assertEqual(15, len(set(packages)))
        self.assertEqual(len(packages), len(set(packages)))
        self.assertEqual('mbedtls', manifest['sources'][0]['name'])
        self.assertNotIn('ffmpeg', packages)
        self.assertNotIn('llama-cpp', packages)

    def test_missing_ndk_fails_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'staged'
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/build-mobile-runtime-additions.py'),
                                     '--ndk', str(Path(directory) / 'absent-ndk'), '--output', str(output)],
                                    capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode)
            self.assertIn('no packages were built', result.stderr)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
