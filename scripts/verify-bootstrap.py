#!/usr/bin/env python3
import hashlib,json,pathlib,posixpath,shutil,subprocess,sys,tarfile,tempfile
manifest_path,archive_path=map(pathlib.Path,sys.argv[1:3]); m=json.loads(manifest_path.read_text()); data=archive_path.read_bytes()
assert m['packageName']=='studio.ocean.app' and m['prefix']=='/data/data/studio.ocean.app/files/usr'
assert m['architecture']=='aarch64' and m['archiveSize']==len(data)
assert m['archiveSha256']==hashlib.sha256(data).hexdigest()
with tempfile.NamedTemporaryFile(suffix='.tar') as expanded:
 if shutil.which('zstd'):
  subprocess.run(['zstd','-q','-d','-c',archive_path],stdout=expanded,check=True)
 else:
  try: import zstandard
  except ImportError as error: raise RuntimeError('zstd or the Python zstandard module is required') from error
  with archive_path.open('rb') as compressed, zstandard.ZstdDecompressor().stream_reader(compressed) as stream:
   shutil.copyfileobj(stream,expanded)
 expanded.flush()
 tar=tarfile.open(expanded.name)
 names=set(tar.getnames()); assert len(names)==m['entryCount']
 for path in ('usr/bin/bash','usr/bin/apt','usr/bin/dpkg','usr/bin/pkg'): assert path in names, path
 for member in tar.getmembers():
  p=pathlib.PurePosixPath(member.name); assert not p.is_absolute() and '..' not in p.parts
  assert p.parts and p.parts[0]=='usr', member.name
  if member.issym():
   assert not posixpath.isabs(member.linkname), (member.name,member.linkname)
   resolved=posixpath.normpath(posixpath.join(posixpath.dirname(member.name),member.linkname))
   assert resolved=='usr' or resolved.startswith('usr/'), (member.name,member.linkname,resolved)
  if member.islnk():
   assert not posixpath.isabs(member.linkname), (member.name,member.linkname)
   resolved=posixpath.normpath(member.linkname)
   assert resolved=='usr' or resolved.startswith('usr/'), (member.name,member.linkname,resolved)
assert {'bash','apt','dpkg','ocean-pkg','ocean-hello'} <= set(m['packageList'])
print(f"verified Ocean bootstrap {m['bootstrapVersion']} ({len(data)} bytes)")
