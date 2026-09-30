#!/usr/bin/env python3
"""Inspect real Ocean .debs and emit a factual repository package report."""
import argparse, hashlib, json, os, pathlib, stat, subprocess, tempfile

def field(deb, name):
    try: return subprocess.check_output(['dpkg-deb','-f',str(deb),name],text=True,stderr=subprocess.DEVNULL).strip()
    except subprocess.CalledProcessError: return ''

parser=argparse.ArgumentParser(); parser.add_argument('debs',type=pathlib.Path); parser.add_argument('report',type=pathlib.Path); args=parser.parse_args()
forbidden=(b'/data/data/com.termux',b'/data/user/0/com.termux',b'TERMUX_PREFIX')
def contains_forbidden(path):
    overlap=b''
    with path.open('rb') as stream:
        while True:
            chunk=stream.read(1024*1024)
            if not chunk: return False
            sample=overlap+chunk
            if any(value in sample for value in forbidden): return True
            overlap=sample[-64:]
packages=[]
with tempfile.TemporaryDirectory() as temporary:
    root=pathlib.Path(temporary)
    for deb in sorted(args.debs.glob('*.deb')):
        target=root/field(deb,'Package'); target.mkdir()
        subprocess.run(['dpkg-deb','-x',str(deb),str(target)],check=True)
        executables=[]; elf=[]
        for path in target.rglob('*'):
            if path.is_symlink() or not path.is_file(): continue
            mode=path.stat().st_mode
            with path.open('rb') as stream: header_bytes=stream.read(4)
            relative=str(path.relative_to(target))
            runtime_file=bool(mode & stat.S_IXUSR) or header_bytes==b'\x7fELF' or header_bytes.startswith(b'#!') or relative.endswith(('.pc','.cmake','.sh'))
            if runtime_file and contains_forbidden(path):
                raise SystemExit(f'foreign Termux runtime identity in {deb.name}:{relative}')
            if mode & stat.S_IXUSR: executables.append(relative)
            if header_bytes==b'\x7fELF':
                header=subprocess.check_output(['readelf','-h',str(path)],text=True)
                if 'AArch64' not in header: raise SystemExit(f'non-AArch64 ELF in {deb.name}:{relative}')
                elf.append(relative)
        packages.append({'name':field(deb,'Package'),'version':field(deb,'Version'),'architecture':field(deb,'Architecture'),'depends':field(deb,'Depends'),'description':field(deb,'Description'),'artifact':deb.name,'bytes':deb.stat().st_size,'sha256':hashlib.sha256(deb.read_bytes()).hexdigest(),'executables':executables,'elf':elf,'staticValidation':'PASS'})
args.report.parent.mkdir(parents=True,exist_ok=True)
args.report.write_text(json.dumps({'schemaVersion':1,'target':'Android/bionic API 28 aarch64','packageCount':len(packages),'repositoryBytes':sum(x['bytes'] for x in packages),'packages':packages},indent=2)+'\n')
print(f"Validated {len(packages)} Ocean packages ({sum(x['bytes'] for x in packages)} bytes)")
