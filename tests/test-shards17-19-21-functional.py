#!/usr/bin/env python3
import importlib.util,pathlib,subprocess,sys,tempfile,tarfile,zipfile,json
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
runtime=pathlib.Path(sys.argv[1]); batch=load(pathlib.Path(sys.argv[2]),"batch"); r=load(runtime,"runtime")
targets=["shard-17-android-bionic-platform","shard-19-archive-backup-sync","shard-21-cloud-container-runtime"]
names=[n for sh in targets for n,_,_ in batch.BATCH3_SHARDS[sh]["packages"]]
assert len(names)==150 and len(set(names))==150 and all(r.supports(n) for n in names)
with tempfile.TemporaryDirectory() as td:
 d=pathlib.Path(td); raw=d/"sample.bin"; raw.write_bytes(b"ANDROID!"+b"\0"*512)
 txt=d/"sample.txt"; txt.write_text("[ro.product.cpu.abi]: [arm64-v8a]\nlevel: 88\nMemTotal: 4096 kB\n")
 js=d/"sample.json"; js.write_text(json.dumps({"services":{"api":{"image":"ocean/api:1"}},"namespace":"default"}))
 zp=d/"sample.zip"
 with zipfile.ZipFile(zp,"w") as z:z.writestr("META-INF/CERT.RSA",b"x");z.writestr("a.txt",b"hello")
 tp=d/"sample.tar"
 with tarfile.open(tp,"w") as t:t.add(txt,arcname="sample.txt")
 ar=d/"sample.ar"; ar.write_bytes(b"!<arch>\n")
 def arg(cmd):
  if cmd.startswith("zip-") or "apk-zip" in cmd:return zp
  if cmd.startswith("tar-") or "pax-" in cmd:return tp
  if cmd.startswith("ar-") or "deb-ar" in cmd:return ar
  if cmd.startswith("package-signing"):return zp
  if any(x in cmd for x in ("property","getprop","logcat","dumpsys","fstab","mount","avc")):return txt
  if any(x in cmd for x in ("cloud","docker","container","kube","helm","terraform","ansible","oci","pod","systemd","compose","yaml","json")):return js
  return raw
 failures=[]
 for cmd in names:
  q=subprocess.run([sys.executable,str(runtime),cmd,str(arg(cmd))],text=True,capture_output=True)
  if q.returncode not in (0,1): failures.append((cmd,q.returncode,q.stderr[-300:]))
 if failures:
  print(failures);raise SystemExit(f"{len(failures)} commands crashed")
print("SUCCESS: exercised 150/150 shard 17/19/21 commands")
