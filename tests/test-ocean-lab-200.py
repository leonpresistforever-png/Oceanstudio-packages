#!/usr/bin/env python3
import base64,hashlib,importlib.util,io,json,os,subprocess,sys,tempfile,zipfile
from pathlib import Path
R=Path(sys.argv[1]).resolve()
spec=importlib.util.spec_from_file_location("lab",R);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert len(m.COMMANDS)==200 and len(set(m.COMMANDS))==200
assert all(len(v)==20 for v in m.GROUPS.values()) and len(m.GROUPS)==10

def run(cmd,*args,cwd=None,binary=False):
    p=subprocess.run([sys.executable,str(R),cmd,*map(str,args)],cwd=cwd,capture_output=True,text=not binary)
    if p.returncode:
        raise AssertionError(f"{cmd} failed rc={p.returncode}\nstdout={p.stdout}\nstderr={p.stderr}")
    return p.stdout

for cmd in m.COMMANDS:
    assert cmd in run(cmd,"--help")

def b64j(obj):
    return base64.urlsafe_b64encode(json.dumps(obj,separators=(",",":")).encode()).decode().rstrip("=")

with tempfile.TemporaryDirectory() as td:
    d=Path(td)

    docx=d/"a.docx"
    with zipfile.ZipFile(docx,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml","<Types><Default Extension='xml' ContentType='text/xml'/></Types>")
        z.writestr("word/document.xml","<w:document xmlns:w='w'><w:body><w:p><w:r><w:t>Hello Ocean</w:t></w:r></w:p></w:body></w:document>")
        z.writestr("word/media/a.png",b"\x89PNG\r\n\x1a\n")
        z.writestr("word/_rels/document.xml.rels","<Relationships><Relationship Target='https://example.com' TargetMode='External'/></Relationships>")
    assert "Hello Ocean" in run("ocean-lab-office-docx-text",docx)
    assert "word/media/a.png" in json.loads(run("ocean-lab-office-docx-images",docx))
    assert "https://example.com" in json.loads(run("ocean-lab-office-docx-links",docx))
    assert json.loads(run("ocean-lab-office-integrity",docx))["valid"] is True

    xlsx=d/"a.xlsx"
    with zipfile.ZipFile(xlsx,"w") as z:
        z.writestr("xl/workbook.xml","<workbook xmlns='x'><sheets><sheet name='Sheet1'/></sheets></workbook>")
        z.writestr("xl/sharedStrings.xml","<sst xmlns='x'><si><t>A</t></si></sst>")
        z.writestr("xl/worksheets/sheet1.xml","<worksheet xmlns='x'><dimension ref='A1:B2'/><sheetData><row><c><f>SUM(A1:A2)</f></c></row></sheetData></worksheet>")
    assert "Sheet1" in json.loads(run("ocean-lab-office-xlsx-sheets",xlsx))
    assert "SUM(A1:A2)" in json.loads(run("ocean-lab-office-xlsx-formulas",xlsx))

    pptx=d/"a.pptx"
    with zipfile.ZipFile(pptx,"w") as z:
        z.writestr("ppt/slides/slide1.xml","<p:sld xmlns:p='p' xmlns:a='a'><a:t>Slide</a:t></p:sld>")
        z.writestr("ppt/media/x.jpg",b"jpg")
    assert "Slide" in run("ocean-lab-office-pptx-text",pptx)

    epub=d/"a.epub"
    with zipfile.ZipFile(epub,"w") as z:
        z.writestr("META-INF/container.xml","<x/>")
        z.writestr("book.opf","<package xmlns:dc='dc'><metadata><dc:title>Ocean Book</dc:title></metadata><manifest><item id='c' href='c.xhtml'/></manifest><spine><itemref idref='c'/></spine></package>")
    assert "Ocean Book" in run("ocean-lab-office-epub-metadata",epub)

    pdf=d/"a.pdf"
    pdf.write_bytes(b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R /Title (Ocean PDF) /Producer (Ocean) >>\nendobj\n2 0 obj\n<< /Type /Pages /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /Subtype /Image /URI (https://example.com) >>\nstream\nabc\nendstream\nendobj\nstartxref\n123\n%%EOF\n")
    assert run("ocean-lab-pdf-version",pdf).strip()=="1.7"
    assert run("ocean-lab-pdf-page-count",pdf).strip()=="1"
    assert json.loads(run("ocean-lab-pdf-eof-check",pdf))["has_eof"] is True
    assert "https://example.com" in json.loads(run("ocean-lab-pdf-uri-links",pdf))

    eml=d/"a.eml"
    eml.write_text("From: A <a@example.com>\nTo: B <b@example.org>\nSubject: Ocean Mail\nMessage-ID: <1@ocean>\nMIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=x\n\n--x\nContent-Type: text/plain\n\nHello\n--x\nContent-Type: text/plain\nContent-Disposition: attachment; filename=test.txt\n\nAttach\n--x--\n")
    assert run("ocean-lab-mail-subject",eml).strip()=="Ocean Mail"
    assert set(json.loads(run("ocean-lab-mail-domains",eml)))=={"example.com","example.org"}
    assert "test.txt" in json.loads(run("ocean-lab-mail-attachment-names",eml))

    ics=d/"a.ics"
    ics.write_text("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:abc\nSUMMARY:Meeting\nDTSTART:20260921T100000Z\nATTENDEE:mailto:a@example.com\nEND:VEVENT\nEND:VCALENDAR\n")
    assert "Meeting" in json.loads(run("ocean-lab-cal-ics-summaries",ics))
    assert "abc" in json.loads(run("ocean-lab-cal-ics-uids",ics))
    vcf=d/"a.vcf";vcf.write_text("BEGIN:VCARD\nFN:Leon\nEMAIL:leon@example.com\nTEL:+911234\nORG:Ocean\nEND:VCARD\n")
    assert "Leon" in json.loads(run("ocean-lab-cal-vcard-names",vcf))

    tok=b64j({"alg":"HS256","typ":"JWT","kid":"k1"})+"."+b64j({"sub":"u1","iss":"ocean","exp":4102444800,"scope":"read write"})+".c2ln"
    assert json.loads(run("ocean-lab-token-jwt-header",tok))["alg"]=="HS256"
    assert json.loads(run("ocean-lab-token-jwt-payload",tok))["sub"]=="u1"
    assert run("ocean-lab-token-jwt-expired",tok).strip()=="false"
    assert run("ocean-lab-token-redact",tok).strip().endswith(".<redacted>")

    proj=d/"proj";proj.mkdir()
    (proj/"package.json").write_text('{"name":"ocean-app","version":"1.2.3","dependencies":{"x":"1"},"scripts":{"test":"x"}}')
    assert json.loads(run("ocean-lab-project-npm-name",proj))=="ocean-app"
    (proj/"Cargo.toml").write_text('[package]\nname="ocean"\nversion="0.1.0"\n[dependencies]\nserde="1"\n')
    assert json.loads(run("ocean-lab-project-cargo-package",proj))["name"]=="ocean"
    (proj/"pyproject.toml").write_text('[project]\nname="oceanpy"\ndependencies=["requests"]\n[project.scripts]\nocean="x:y"\n')
    assert "requests" in json.loads(run("ocean-lab-project-pyproject-deps",proj))
    (proj/"requirements.txt").write_text("requests>=2\nflask==3\n")
    assert json.loads(run("ocean-lab-project-requirements-packages",proj))==["requests","flask"]
    (proj/"build.gradle").write_text("plugins { id 'com.android.application' }\ndependencies { implementation 'a:b:1' }\n")
    assert "com.android.application" in json.loads(run("ocean-lab-project-gradle-plugins",proj))
    (proj/"pom.xml").write_text("<project><groupId>g</groupId><artifactId>a</artifactId><version>1</version><dependencies><dependency><groupId>x</groupId><artifactId>y</artifactId><version>2</version></dependency></dependencies></project>")
    assert json.loads(run("ocean-lab-project-pom-gav",proj))["artifactId"]=="a"
    (proj/"AndroidManifest.xml").write_text("<manifest xmlns:android='http://schemas.android.com/apk/res/android' package='studio.ocean.test'><uses-permission android:name='android.permission.INTERNET'/></manifest>")
    assert run("ocean-lab-project-android-package",proj).strip()=="studio.ocean.test"

    py=d/"x.py";py.write_text("import os\n# TODO hi\nclass A:\n    pass\n\ndef f():\n\treturn 1  \n")
    assert run("ocean-lab-source-detect-language",py).strip()=="python"
    assert "f" in json.loads(run("ocean-lab-source-python-functions",py))
    assert "A" in json.loads(run("ocean-lab-source-python-classes",py))
    assert len(json.loads(run("ocean-lab-source-todo-lines",py)))==1

    raw=d/"b.bin";raw.write_bytes(b"\x34\x12\x00\x00ABCD")
    assert run("ocean-lab-binary-u16le",raw).strip()=="4660"
    assert run("ocean-lab-binary-varint-encode","300").strip()=="ac02"
    assert run("ocean-lab-binary-varint-decode","ac02").strip()=="300"
    assert run("ocean-lab-binary-crc32",raw).strip()==f"{__import__('zlib').crc32(raw.read_bytes())&0xffffffff:08x}"

    assert run("ocean-lab-string-camel","hello ocean studio").strip()=="helloOceanStudio"
    assert run("ocean-lab-string-snake","Hello Ocean Studio").strip()=="hello_ocean_studio"
    assert run("ocean-lab-string-map-subst","Hi ${name}",'{"name":"Ocean"}').strip()=="Hi Ocean"
    assert run("ocean-lab-string-mustache-lite","Hi {{name}}",'{"name":"Ocean"}').strip()=="Hi Ocean"

    aab=d/"app.aab"
    with zipfile.ZipFile(aab,"w") as z:
        z.writestr("BundleConfig.pb",b"cfg")
        z.writestr("base/manifest/AndroidManifest.xml",b"manifest")
        z.writestr("base/dex/classes.dex",b"dex")
        z.writestr("base/lib/arm64-v8a/libx.so",b"elf")
        z.writestr("base/assets/a.txt","a")
        z.writestr("base/res/layout/x.xml","x")
    assert "base" in json.loads(run("ocean-lab-bundle-aab-modules",aab))
    assert "arm64-v8a" in json.loads(run("ocean-lab-bundle-aab-native-abis",aab))
    assert json.loads(run("ocean-lab-bundle-bundle-integrity",aab))["valid"] is True

    inner=io.BytesIO()
    with zipfile.ZipFile(inner,"w") as z:
        z.writestr("classes.dex",b"dex")
        z.writestr("lib/arm64-v8a/liba.so",b"elf")
        z.writestr("assets/x","x")
    apks=d/"app.apks"
    with zipfile.ZipFile(apks,"w") as z:
        z.writestr("splits/base-master.apk",inner.getvalue())
    assert "base-master.apk" in json.loads(run("ocean-lab-bundle-apks-split-names",apks))
    assert "arm64-v8a" in json.loads(run("ocean-lab-bundle-apks-native-abis",apks))
    assert run("ocean-lab-bundle-apks-dex-count",apks).strip()=="1"

print("PASS: 200 unique Ocean Lab commands registered; all command dispatch paths plus ten functional domains tested")
