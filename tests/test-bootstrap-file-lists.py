#!/usr/bin/env python3
"""Exercise bootstrap ownership records with real dpkg tools, not APT simulation."""
import importlib.util
import subprocess
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location('hydrate', Path(__file__).parents[1] / 'scripts/hydrate-signed-bootstrap.py')
hydrate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hydrate)

with tempfile.TemporaryDirectory(prefix='ocean-dpkg-regression-') as directory:
    root = Path(directory)
    package = root / 'package'
    (package / 'DEBIAN').mkdir(parents=True)
    package.chmod(0o755)
    (package / 'DEBIAN').chmod(0o755)
    control = 'Package: ocean-fixture\nVersion: 1.0\nArchitecture: all\nMaintainer: Ocean <test@ocean.studio>\nDescription: file-list regression fixture\n'
    (package / 'DEBIAN/control').write_text(control)
    payload = package / 'data/data/studio.ocean.app/files/usr/bin'
    payload.mkdir(parents=True)
    (payload / 'file with spaces').write_text('fixture\n')
    (payload / 'alias').symlink_to('file with spaces')
    deb = root / 'fixture.deb'
    subprocess.run(['dpkg-deb', '--build', '--root-owner-group', str(package), str(deb)], check=True, capture_output=True)
    listing = hydrate.package_file_list(deb)
    assert listing.splitlines()[0] == '/.'
    assert '/data/data/studio.ocean.app/files/usr/bin/file with spaces' in listing.splitlines()
    assert '/data/data/studio.ocean.app/files/usr/bin/alias' in listing.splitlines()
    assert ' -> ' not in listing
    assert '/' not in listing.splitlines()
    db = root / 'db'
    (db / 'info').mkdir(parents=True)
    (db / 'status').write_text(control + 'Status: install ok installed\n\n')
    record = db / 'info/ocean-fixture.list'
    record.write_text(listing.replace('/.\n', '/\n', 1))
    query = ['dpkg-query', '--admindir=' + str(db), '-S', '/data/data/studio.ocean.app/files/usr/bin/alias']
    broken = subprocess.run(query, text=True, capture_output=True)
    assert broken.returncode == 2 and 'contains empty filename' in broken.stderr
    record.write_text(listing)
    repaired = subprocess.run(query, text=True, capture_output=True)
    assert repaired.returncode == 0, repaired.stderr
    assert 'ocean-fixture:' in repaired.stdout
    print('PASS: reproduced dpkg exit 2; generated root, spaces and symlink records load successfully')
