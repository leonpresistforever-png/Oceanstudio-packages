#!/usr/bin/env python3
"""Exercise key continuity and secret encryption with disposable local keys."""
import base64
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from nacl.public import PrivateKey, SealedBox

spec=importlib.util.spec_from_file_location('sync',Path(__file__).resolve().parents[1]/'scripts/sync_repository_signing_secret.py')
sync=importlib.util.module_from_spec(spec);spec.loader.exec_module(sync)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.home=self.root/'gpg';self.home.mkdir(mode=0o700)
        env=dict(os.environ,GNUPGHOME=str(self.home))
        def gpg(*args):
            return subprocess.run(['gpg','--batch',*args],env=env,check=True,capture_output=True).stdout
        self.gpg=gpg
        gpg('--pinentry-mode','loopback','--passphrase','','--quick-generate-key',
            'Ocean disposable continuity fixture','ed25519','sign','1d')
        self.fpr=next(line.split(':')[9] for line in gpg('--with-colons','--list-keys').decode().splitlines() if line.startswith('fpr:'))
        self.public=gpg('--export',self.fpr)
        self.secret=gpg('--armor','--export-secret-keys',self.fpr).decode()
        self.destination=PrivateKey.generate();self.writes=[]
        self.addCleanup(lambda:subprocess.run(['gpgconf','--kill','gpg-agent'],env=env,capture_output=True))

    def api(self,path,method='GET',body=None):
        if path=='contents/apt/ocean.gpg':return {'content':base64.b64encode(self.public).decode()}
        if path=='actions/secrets/public-key':return {'key_id':'fixture','key':base64.b64encode(bytes(self.destination.public_key)).decode()}
        self.assertEqual(path,'actions/secrets/OCEAN_REPOSITORY_SIGNING_KEY')
        self.assertEqual(method,'PUT');self.writes.append(body);return {'status':204}

    def invoke(self,secret=None,fingerprint=None):
        with patch.dict(os.environ,{'RUNNER_TEMP':str(self.root),
                'OCEAN_REPOSITORY_SIGNING_KEY':self.secret if secret is None else secret}), \
             patch.object(sync,'FINGERPRINT',fingerprint or self.fpr),patch.object(sync,'api',self.api):
            sync.main()

    def test_same_key_is_verified_and_sent_only_as_sealed_ciphertext(self):
        self.invoke();self.assertEqual(len(self.writes),1)
        body=self.writes[0];self.assertEqual(body['key_id'],'fixture')
        plaintext=SealedBox(self.destination).decrypt(base64.b64decode(body['encrypted_value']))
        self.assertEqual(plaintext.decode(),self.secret)
        self.assertNotIn('PRIVATE KEY',body['encrypted_value'])
        self.assertEqual(list(self.root.glob('ocean-signing-*')),[])

    def test_unexpected_public_identity_cannot_overwrite_the_destination(self):
        with self.assertRaisesRegex(RuntimeError,'trust root changed'):self.invoke(fingerprint='0'*40)
        self.assertEqual(self.writes,[])

    def test_public_only_material_cannot_be_published_as_private_signing_key(self):
        public_ascii=self.gpg('--armor','--export',self.fpr).decode()
        with self.assertRaises(RuntimeError):self.invoke(secret=public_ascii)
        self.assertEqual(self.writes,[])

    def test_missing_key_never_calls_destination(self):
        with self.assertRaisesRegex(RuntimeError,'not configured'):self.invoke(secret='')
        self.assertEqual(self.writes,[])


if __name__=='__main__':unittest.main()
