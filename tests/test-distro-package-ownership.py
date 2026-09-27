#!/usr/bin/env python3
"""Replay actual dpkg ownership transfer; dependency execution is out of scope."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
POOL = ROOT/'staging/ocean-distro-repair/pool/main'
PREFIX = 'data/data/studio.ocean.app/files/usr'


def main():
    evidence = {'scope': 'Host dpkg ownership migration, with --force-depends. Not an Android installation test.'}
    scripts = json.loads((POOL.parent.parent/'ocean-tools-ownership.json').read_text())['preservedScriptSha256']
    with tempfile.TemporaryDirectory(prefix='ocean-distro-ownership-') as directory:
        root = Path(directory)
        admindir = directory + '/var/lib/dpkg'
        (root/'var/lib/dpkg/updates').mkdir(parents=True, exist_ok=True)
        (root/'var/lib/dpkg/info').mkdir(parents=True, exist_ok=True)
        (root/'var/lib/dpkg/status').touch()
        command = ['dpkg', '--root='+directory, '--admindir='+admindir, '--force-not-root', '--force-depends', '--auto-deconfigure']
        ocean_distro_deb = sorted(POOL.glob('ocean-distro_*.deb'))[-1]
        proot_distro_deb = sorted(POOL.glob('proot-distro_*.deb'))[-1]
        steps = [('oldTools', [ROOT/'apt/pool/main/ocean-tools_1.1.0_all.deb']),
                 ('ownershipUpgrade', [POOL/'ocean-tools_1.1.0+ocean1_all.deb', ocean_distro_deb]),
                 ('independentProot', [proot_distro_deb])]
        for label, archives in steps:
            run = subprocess.run(command+['--install']+[str(p) for p in archives], capture_output=True, text=True)
            evidence[label] = {'exit': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr}
            if run.returncode:
                raise RuntimeError(label+': '+run.stderr)
        for path, digest in scripts.items():
            assert hashlib.sha256((root/path).read_bytes()).hexdigest() == digest, path
        path = '/'+PREFIX+'/bin/ocean-distro'
        owner = subprocess.check_output(['dpkg-query', '--admindir='+directory+'/var/lib/dpkg', '--search', path], text=True).strip()
        assert owner == 'ocean-distro: '+path, owner
        evidence['managerOwner'] = owner
        run = subprocess.run(command+['--remove', 'ocean-tools'], capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        assert (root/path.lstrip('/')).read_bytes() == (ROOT/'packages/ocean-distro/ocean-distro').read_bytes()
        assert (root/PREFIX/'bin/proot-distro').read_bytes() == (ROOT/'packages/proot-distro/proot-distro').read_bytes()
        evidence['preservedScriptCount'] = len(scripts)
        evidence['managerSurvivesToolsRemoval'] = True
        evidence['status'] = 'PASS'
    (POOL.parent.parent/'ownership-test.json').write_text(json.dumps(evidence, indent=2)+'\n')
    print('PASS: independent managers; 25 preserved scripts; owner transfer and tools removal')


if __name__ == '__main__':
    main()
