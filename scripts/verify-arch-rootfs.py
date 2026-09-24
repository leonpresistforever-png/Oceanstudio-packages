#!/usr/bin/env python3
"""Authenticate an official Arch Linux ARM image before proposing a SHA256 pin.

The archive fingerprint is published by Arch Linux ARM on its downloads/signing
pages. It is unrelated to Ocean's APT signing key. Only evidence/candidate JSON is
written; changing the live distro registry requires reviewing this result.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FINGERPRINT = '68B3537F39A313B3E574D06777193F152BDBE6A6'
KEY_COMMIT = '91e6b11698f8df66042d56aaa56fbe9c9263847d'
KEY_URL = f'https://raw.githubusercontent.com/archlinuxarm/archlinuxarm-keyring/{KEY_COMMIT}/archlinuxarm.gpg'
URL = 'https://ca.us.mirror.archlinuxarm.org/os/ArchLinuxARM-aarch64-latest.tar.gz'


def download(url, target):
    subprocess.run(['curl', '--fail', '--location', '--proto', '=https', '--proto-redir', '=https',
        '--retry', '3', '--connect-timeout', '30', '--max-time', '1800', '--output', str(target), url], check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    report = {'url': URL, 'officialFingerprintSource': 'https://archlinuxarm.org/about/downloads',
        'fingerprint': FINGERPRINT, 'keyringUrl': KEY_URL, 'published': False}
    try:
        with tempfile.TemporaryDirectory(prefix='ocean-arch-auth-') as tmp:
            directory = Path(tmp)
            archive, signature, keyring = [directory / n for n in ['rootfs.tar.gz', 'rootfs.sig', 'archlinuxarm.gpg']]
            key_source = directory / 'upstream-keyring.asc'
            download(KEY_URL, key_source)
            # Upstream calls its ASCII-armored public keyring .gpg; gpgv needs
            # binary key packets, not the filename-based assumption made before.
            subprocess.run(['gpg', '--batch', '--dearmor', '--output', str(keyring), str(key_source)], check=True)
            for url, target in [(URL + '.sig', signature), (URL, archive)]:
                download(url, target)
            result = subprocess.run(['gpgv', '--status-fd', '1', '--keyring', str(keyring), str(signature), str(archive)],
                text=True, capture_output=True)
            valid = [l.split() for l in result.stdout.splitlines() if l.startswith('[GNUPG:] VALIDSIG ')]
            report['signatureResult'] = {'exitCode': result.returncode, 'status': result.stdout, 'stderr': result.stderr}
            if result.returncode or not any(FINGERPRINT in (v[2], v[-1]) for v in valid):
                raise ValueError('Archive lacks a valid signature from the official pinned Arch ARM key')
            h = hashlib.sha256()
            with archive.open('rb') as stream:
                while chunk := stream.read(1048576):
                    h.update(chunk)
            registry = json.loads((ROOT / 'packages/ocean-distro/distros.json').read_text())
            entry = dict(registry['arch'], url=URL, sha256=h.hexdigest())
            entry.pop('fallback_url', None)
            spec = importlib.util.spec_from_file_location('rootfs', ROOT / 'scripts/verify-rootfs-candidates.py')
            auditor = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(auditor)
            # Re-download is intentional: the pin must still match the served
            # image; an upstream rolling-image replacement cannot slip through.
            report['rootfsAudit'] = auditor.inspect('arch', entry)
            if report['rootfsAudit']['status'] != 'checksum-identity-arm-shell-passed':
                raise ValueError('Authenticated image failed OS identity / ARM execution checks')
            report['candidate'] = entry
            report['status'] = 'authenticated-arm-rootfs-candidate'
            (a.output / 'arch-candidate.json').write_text(json.dumps(entry, indent=2) + '\n')
    except Exception as exc:
        report.update(status='failed', error=str(exc))
    (a.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
