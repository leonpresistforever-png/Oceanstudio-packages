#!/usr/bin/env python3
import importlib.util,json,os,subprocess,sys,tempfile,zipfile,tarfile,hashlib
from pathlib import Path
R=Path(sys.argv[1]).resolve()
spec=importlib.util.spec_from_file_location("devkit",R);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert len(m.COMMANDS)==200
assert len(set(m.COMMANDS))==200
assert [len(m.APK),len(m.WEB),len(m.GIT),len(m.TEXT),len(m.DATA),len(m.FS),len(m.NET),len(m.CRYPTO),len(m.BUILD),len(m.ARCHIVE)]==[20,20,20,20,20,20,20,20,20,19]
assert m.COMMANDS[-1]=="ocean-devkit-runtime"

def run(cmd,*args,cwd=None):
    p=subprocess.run([sys.executable,str(R),cmd,*map(str,args)],cwd=cwd,capture_output=True,text=True)
    if p.returncode:
        raise AssertionError(f"{cmd} failed rc={p.returncode}\nstdout={p.stdout}\nstderr={p.stderr}")
    return p.stdout

# Every package command must at least enter a real registered code path.
for cmd in m.COMMANDS:
    s=run(cmd,"--help")
    assert cmd in s

with tempfile.TemporaryDirectory() as td:
    d=Path(td)

    # APK/ZIP inspection fixture
    apk=d/"demo.apk"
    with zipfile.ZipFile(apk,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("AndroidManifest.xml","<manifest><uses-permission name='android.permission.CAMERA'/><uses-feature name='android.hardware.camera'/></manifest>".encode("utf-16le"))
        z.writestr("classes.dex",b"dex\n035\0"+b"x"*64)
        z.writestr("lib/arm64-v8a/libdemo.so",b"\x7fELF"+b"x"*64)
        z.writestr("assets/config.json",'{"ok":true}')
        z.writestr("res/layout/main.xml","<x/>")
        z.writestr("META-INF/CERT.SF","sig")
    assert json.loads(run("ocean-apkx-native-abis",apk))==["arm64-v8a"]
    assert "android.permission.CAMERA" in run("ocean-apkx-permission-hints",apk)
    assert json.loads(run("ocean-apkx-zip-test",apk))["valid"] is True
    assert json.loads(run("ocean-apkx-dex-count",apk))==1

    # Web parsing stays offline in tests.
    assert json.loads(run("ocean-webx-url-parse","https://Example.com:443/a?q=1#z"))["hostname"]=="example.com"
    html=d/"page.html";html.write_text("<html><head><title>Ocean</title></head><body><a href='/a'>A</a><img src='x.png'></body></html>")
    assert json.loads(run("ocean-webx-html-links",html))==["/a"]
    assert run("ocean-webx-html-title",html).strip()=="Ocean"

    # Git utilities operate on a real temporary repository.
    g=d/"repo";g.mkdir()
    subprocess.run(["git","init","-b","main"],cwd=g,check=True,capture_output=True)
    subprocess.run(["git","config","user.email","test@ocean.local"],cwd=g,check=True)
    subprocess.run(["git","config","user.name","Ocean Test"],cwd=g,check=True)
    (g/"a.txt").write_text("hello\n")
    subprocess.run(["git","add","a.txt"],cwd=g,check=True)
    subprocess.run(["git","commit","-m","first"],cwd=g,check=True,capture_output=True)
    assert run("ocean-gitx-branch-current",cwd=g).strip()=="main"
    assert len(run("ocean-gitx-head-sha",cwd=g).strip())==40
    assert "first" in run("ocean-gitx-commit-message",cwd=g)

    # Text/data utilities.
    assert run("ocean-textx-slug","Hello Ocean Studio!").strip()=="hello-ocean-studio"
    t=d/"t.txt";t.write_text("a\na\nb\n")
    assert json.loads(run("ocean-textx-lines-duplicate",t))==["a"]
    j=d/"x.json";j.write_text('{"a":{"b":2},"c":3}')
    flat=json.loads(run("ocean-datax-json-flatten",j));assert flat["a.b"]==2
    c=d/"x.csv";c.write_text("name,n\nx,1\ny,2\n")
    assert run("ocean-datax-csv-count",c).strip()=="2"

    # Filesystem analysis and manifest verification.
    fs=d/"fs";fs.mkdir();(fs/"a").write_text("same");(fs/"b").write_text("same");(fs/"c").write_text("")
    dup=json.loads(run("ocean-fsx-duplicates",fs));assert any(len(x)==2 for x in dup)
    mf=d/"manifest.json";run("ocean-fsx-checksum-manifest",fs,mf)
    assert json.loads(run("ocean-fsx-verify-manifest",fs,mf))["valid"] is True

    # Network math/classification, no Internet needed.
    ip=json.loads(run("ocean-netx-ip-classify","127.0.0.1"));assert ip["loopback"] is True
    assert run("ocean-netx-cidr-contains","10.0.0.0/24","10.0.0.7").strip()=="true"
    assert run("ocean-netx-int-ip","2130706433").strip()=="127.0.0.1"

    # Crypto primitives.
    f=d/"blob";f.write_bytes(b"abc")
    assert run("ocean-cryptox-sha256-file",f).strip()==hashlib.sha256(b"abc").hexdigest()
    assert len(run("ocean-cryptox-random-hex","16").strip())==32
    assert run("ocean-cryptox-compare","same","same").strip()=="true"

    # Build/source checks.
    src=d/"src";src.mkdir();(src/"ok.json").write_text('{"x":1}');(src/"a.py").write_text("import json\n# TODO test\nprint(1)\n")
    assert json.loads(run("ocean-buildx-json-check",src))["valid"] is True
    assert "json" in json.loads(run("ocean-buildx-python-imports",src))
    assert len(json.loads(run("ocean-buildx-todo-scan",src)))==1

    # Archive operations and traversal audit.
    zf=d/"a.zip"
    with zipfile.ZipFile(zf,"w") as z:z.writestr("dir/a.txt","hello")
    assert json.loads(run("ocean-archivex-zip-test",zf))["valid"] is True
    assert json.loads(run("ocean-archivex-safe-check",zf))["safe"] is True
    tf=d/"a.tar"
    with tarfile.open(tf,"w") as t:t.add(f,arcname="blob")
    assert "blob" in json.loads(run("ocean-archivex-tar-list",tf))

    meta=json.loads(run("ocean-devkit-runtime"))
    assert meta["commands"]==200 and meta["groups"]["archive"]==19

print("PASS: 200 unique DevKit packages registered; every command help path and all ten functional domains tested")
