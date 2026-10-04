#!/usr/bin/env python3
"""Co-install actual deb payloads, check closure/ownership and execute upstream code."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from index_all_staged import fields, stanzas
from audit_package_payloads import dependency_errors
from package_quality import assess_deb

def run(command, **kwargs):
    return subprocess.run([str(v) for v in command], check=True, **kwargs)

def main(directory):
    lock = json.loads((ROOT / 'sources/runtime-dependencies/lock.json').read_text())
    records = []
    owners = {}
    with tempfile.TemporaryDirectory(prefix='ocean-coinstall-') as folder:
        root = Path(folder)
        for path in sorted(directory.glob('*.deb')):
            control = fields(subprocess.check_output(['dpkg-deb', '-f', str(path)], text=True))
            records.append(control)
            listing = subprocess.check_output(['dpkg-deb', '--contents', str(path)], text=True)
            for row in listing.splitlines():
                if row.startswith('d'):
                    continue
                name = row.split(maxsplit=5)[-1].split(' -> ')[0]
                if name in owners:
                    raise AssertionError(f"Payload collision: {name} in {owners[name]} and {control['Package']}")
                owners[name] = control['Package']
            verdict = assess_deb(path)
            assert not verdict.reject, (control['Package'], verdict.reasons)
            run(['dpkg-deb', '-x', path, root])
        assert len({r['Package'] for r in records}) == len(records) == len(lock['packages']) + 4
        existing = [fields(s) for s in stanzas((ROOT / 'apt/dists/stable/main/binary-aarch64/Packages').read_text())]
        replacement = {r['Package'] for r in records}
        issues = dependency_errors(records + [r for r in existing if r['Package'] not in replacement])
        assert not issues, issues
        prefix = root / 'data/data/studio.ocean.app/files/usr'
        vendor = prefix / 'lib/ocean-python/site-packages'
        env = dict(os.environ, PYTHONPATH=str(vendor), PREFIX=str(prefix))
        smoke = r'''
from importlib.metadata import distributions
from importlib import import_module
from pathlib import PurePosixPath
import sys
all_dist = list(distributions(path=[sys.argv[1]]))
assert len(all_dist) == int(sys.argv[2]), len(all_dist)
modules = set()
for dist in all_dist:
    for file in dist.files or []:
        first = PurePosixPath(file).parts[0]
        if first.endswith('.py'):
            first = first[:-3]
        if first.isidentifier() and first not in ['tests', 'test', 'docs', 'examples', '_distutils_hack']:
            modules.add(first)
for name in sorted(modules):
    import_module(name)
print('Imported', len(modules), 'real upstream modules from', len(all_dist), 'distributions')
import requests, threading, http.server, httpx
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'upstream-http-success')
    def log_message(self, *a): pass
server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
url = 'http://127.0.0.1:' + str(server.server_port)
assert requests.get(url).text == 'upstream-http-success'
assert httpx.get(url, trust_env=False).text == 'upstream-http-success'
server.shutdown(); server.server_close()
from flask import Flask
app = Flask('ocean-test')
@app.route('/')
def index(): return {'real': True}
assert app.test_client().get('/').json == {'real': True}
from oauthlib.oauth2 import WebApplicationClient
client = WebApplicationClient('test-client')
assert 'code_challenge_method=S256' in client.prepare_request_uri('https://example.test/auth', redirect_uri='http://localhost:1455/auth/callback', state='random', code_challenge='sha256', code_challenge_method='S256')
from markupsafe import escape
assert str(escape('<x>')) == '&lt;x&gt;'
import xmltodict, jsonpatch, networkx
assert xmltodict.parse('<root>value</root>')['root'] == 'value'
assert jsonpatch.apply_patch({'a': 1}, [{'op':'replace','path':'/a','value':2}]) == {'a': 2}
assert networkx.shortest_path(networkx.path_graph(3), 0, 2) == [0, 1, 2]
print('HTTP, Flask, OAuth, escaping, XML, patching and graph behavior passed')
'''
        run([sys.executable, '-S', '-c', smoke, vendor, len(lock['packages'])], env=env)
        node = Path(subprocess.check_output(['sh', '-c', 'command -v node'], text=True).strip())
        (prefix / 'bin/node').symlink_to(node)
        for command in ['npm', 'npx']:
            version = subprocess.check_output(['sh', str(prefix / 'bin' / command), '--version'], text=True, env=env).strip()
            assert version == '11.19.1', (command, version)
        old_package = 'python-httpx'
        owned_files = [name for name, owner in owners.items() if owner == old_package]
        for name in owned_files:
            path = root / name.removeprefix('./')
            if path.exists():
                path.unlink()
        run([sys.executable, '-S', '-c', 'import requests, flask, oauthlib; print("Independent library removal preserved other packages")'], env=env)
        print(f'PASS: {len(records)} actual packages, no payload overlaps, complete indexed dependency closure, npm/npx repaired')

if __name__ == '__main__':
    main(Path(sys.argv[1]))
