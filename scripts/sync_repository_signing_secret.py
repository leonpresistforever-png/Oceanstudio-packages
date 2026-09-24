#!/usr/bin/env python3
"""Restore the same trusted Ocean archive key in the package publisher's secrets.

Run only in the private repository's authorized Actions context. Key material is
never printed, written to artifacts, or returned through workflow outputs. The
destination receives an encrypted Actions secret, not a repository file.
"""
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request

REPOSITORY = 'leonpresistforever-png/Oceanstudio-packages'
FINGERPRINT = '09D45DD2CDC37BD4F9BC2C458EC15431CA5542E2'


def api(path, method='GET', body=None):
    token = os.environ.get('OCEAN_SECRET_SYNC_TOKEN') or os.environ.get('OCEAN_PACKAGES_PUBLISH_TOKEN')
    if not token:
        raise RuntimeError('An authorized destination repository token is required')
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
        body = json.dumps(body).encode()
    request = urllib.request.Request('https://api.github.com/repos/' + REPOSITORY + '/' + path,
                                     headers=headers, method=method, data=body)
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
        return json.loads(raw) if raw else {'status': response.status}


def main():
    from nacl.public import PublicKey, SealedBox
    secret = os.environ.get('OCEAN_REPOSITORY_SIGNING_KEY', '')
    if not secret:
        raise RuntimeError('The existing private archive key is not configured')
    with tempfile.TemporaryDirectory(prefix='ocean-signing-', dir=os.environ.get('RUNNER_TEMP')) as tmp:
        Path(tmp).chmod(0o700)
        env = dict(os.environ, GNUPGHOME=tmp)
        def gpg(*args, data=None):
            result = subprocess.run(['gpg', '--batch', *args], input=data, capture_output=True, env=env)
            if result.returncode:
                raise RuntimeError('Existing-key verification failed; no destination secret was changed')
            return result.stdout
        try:
            public = base64.b64decode(api('contents/apt/ocean.gpg')['content'])
            trust = gpg('--with-colons', '--show-keys', data=public).decode()
            fingerprints = [line.split(':')[9] for line in trust.splitlines() if line.startswith('fpr:')]
            if fingerprints != [FINGERPRINT]:
                raise RuntimeError('Destination archive trust root changed; refusing key substitution')
            gpg('--import', data=secret.encode())
            private = gpg('--with-colons', '--list-secret-keys', FINGERPRINT).decode()
            if not any(line.startswith('sec:') for line in private.splitlines()):
                raise RuntimeError('Configured material does not contain the existing private key')
            # Prove this secret can actually sign for the already-trusted key.
            challenge = Path(tmp) / 'challenge'
            challenge.write_bytes(b'Ocean repository signing continuity verification\n')
            signature = Path(tmp) / 'challenge.sig'
            gpg('--local-user', FINGERPRINT, '--detach-sign', '--output', str(signature), str(challenge))
            gpg('--verify', str(signature), str(challenge))
            exported = gpg('--armor', '--export-secret-keys', FINGERPRINT)
            if not exported:
                raise RuntimeError('Existing key export is empty')
            destination = api('actions/secrets/public-key')
            encrypted = SealedBox(PublicKey(base64.b64decode(destination['key']))).encrypt(exported)
            result = api('actions/secrets/OCEAN_REPOSITORY_SIGNING_KEY', 'PUT', {
                'key_id': destination['key_id'], 'encrypted_value': base64.b64encode(encrypted).decode()})
            print('Restored the existing archive key as an encrypted publisher secret:', FINGERPRINT,
                  'HTTP', result['status'])
        finally:
            subprocess.run(['gpgconf', '--kill', 'gpg-agent'], env=env, capture_output=True)


if __name__ == '__main__':
    main()
