#!/usr/bin/env python3
import importlib.util,json,os,subprocess,sys,tempfile
from pathlib import Path

R=Path(sys.argv[1]).resolve()
spec=importlib.util.spec_from_file_location("workbench",R);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert len(m.COMMANDS)==300 and len(set(m.COMMANDS))==300
assert len(m.GROUPS)==15 and all(len(v)==20 for v in m.GROUPS.values())

def run(cmd,*args,cwd=None):
    p=subprocess.run([sys.executable,str(R),cmd,*map(str,args)],cwd=cwd,capture_output=True,text=True)
    if p.returncode:
        raise AssertionError(f"{cmd} failed rc={p.returncode}\nstdout={p.stdout}\nstderr={p.stderr}")
    return p.stdout

# Registration / safe invocation path for every package.
for cmd in m.COMMANDS:
    assert cmd in run(cmd,"--help")

with tempfile.TemporaryDirectory() as td:
    d=Path(td)

    # date/time
    assert run("ocean-wb-date-weekday","2026-09-20T00:00:00Z").strip()=="Sunday"
    assert run("ocean-wb-date-duration-parse","1h30m").strip()=="5400.0"
    assert len(json.loads(run("ocean-wb-date-range-days","2026-01-01","2026-01-03")))==3

    # math
    assert run("ocean-wb-math-gcd","84","126").strip()=="42"
    assert run("ocean-wb-math-fibonacci","10").strip()=="55"
    assert json.loads(run("ocean-wb-math-prime-factors","84"))==[2,2,3,7]

    # unit conversion
    assert abs(float(run("ocean-wb-unit-c-to-f","100"))-212)<1e-9
    assert run("ocean-wb-unit-ratio","1920","1080").strip()=="16:9"
    assert run("ocean-wb-unit-base-convert","ff","16","10").strip()=="255"

    # encoding/unicode
    assert run("ocean-wb-enc-url-quote","a b").strip()=="a%20b"
    assert json.loads(run("ocean-wb-enc-unicode-codepoints","A🙂"))[0]=="U+0041"
    assert run("ocean-wb-enc-hex-encode","Ocean").strip()=="4f6365616e"

    # XML
    xf=d/"x.xml";xf.write_text('<root id="7"><item a="b">hello</item><item>two</item></root>')
    assert run("ocean-wb-xml-root",xf).strip()=="root"
    assert json.loads(run("ocean-wb-xml-count",xf))==3
    assert len(json.loads(run("ocean-wb-xml-find-tag",xf,"item")))==2

    # config formats
    ini=d/"a.ini";ini.write_text("[core]\nname=Ocean\n")
    assert run("ocean-wb-config-ini-get",ini,"core","name").strip()=="Ocean"
    env=d/"a.env";env.write_text("A=1\nB=two\n")
    assert json.loads(run("ocean-wb-config-dotenv-to-json",env))["B"]=="two"
    toml=d/"a.toml";toml.write_text('[tool]\nname="ocean"\n')
    assert run("ocean-wb-config-toml-get",toml,"tool.name").strip()=="ocean"

    # Markdown
    md=d/"a.md";md.write_text("# Ocean\n\n[Link](https://example.com)\n\n- [x] done\n- [ ] open\n")
    assert len(json.loads(run("ocean-wb-md-headings",md)))==1
    assert json.loads(run("ocean-wb-md-links",md))==["https://example.com"]
    assert json.loads(run("ocean-wb-md-task-count",md))=={"done":1,"open":1}

    # regex
    assert run("ocean-wb-regex-test",r"\d+","abc123").strip()=="true"
    assert json.loads(run("ocean-wb-regex-extract-emails","mail a@b.com and c@d.org"))==["a@b.com","c@d.org"]
    assert json.loads(run("ocean-wb-regex-validate","[a-z]+"))["valid"] is True

    # diff/comparison
    left=d/"left.txt";right=d/"right.txt";left.write_text("a\nb\n");right.write_text("a\nc\n")
    assert "c" in json.loads(run("ocean-wb-diff-lines-added",left,right))
    assert float(run("ocean-wb-diff-sequence-ratio","abc","abd"))>0.5
    assert run("ocean-wb-diff-same-file",left,left).strip()=="true"

    # procfs
    me=json.loads(run("ocean-wb-proc-self"));assert me["pid"]>0
    assert int(run("ocean-wb-proc-count"))>0
    assert int(run("ocean-wb-proc-open-fds"))>=0

    # permissions
    pf=d/"p";pf.write_text("x");os.chmod(pf,0o640)
    assert run("ocean-wb-perm-mode",pf).strip().endswith("640")
    assert run("ocean-wb-perm-octal-to-symbolic","755").strip()=="rwxr-xr-x"
    assert run("ocean-wb-perm-symbolic-to-octal","rw-r-----").strip()=="640"

    # semantic versions
    assert run("ocean-wb-semver-compare","1.2.3","1.3.0").strip()=="-1"
    assert run("ocean-wb-semver-bump-minor","1.2.3").strip()=="1.3.0"
    assert json.loads(run("ocean-wb-semver-sort","2.0.0","1.9.0","1.10.0"))==["1.9.0","1.10.0","2.0.0"]

    # logs
    log=d/"a.log";log.write_text("2026-01-01T00:00:00Z INFO started\n2026-01-01T00:00:01Z WARN slow\n2026-01-01T00:00:02Z ERROR failed id=req7 from 192.0.2.1\n")
    summary=json.loads(run("ocean-wb-log-summary",log));assert summary["errors"]==1 and summary["warnings"]==1
    assert json.loads(run("ocean-wb-log-extract-ips",log))==["192.0.2.1"]
    assert "failed" in run("ocean-wb-log-errors",log)

    # stream processing
    sf=d/"s.txt";sf.write_text("a\na\n\nb\n")
    assert run("ocean-wb-stream-count",sf).strip()=="4"
    assert json.loads(run("ocean-wb-stream-duplicates",sf))==["a"]
    assert len(json.loads(run("ocean-wb-stream-hash-lines",sf)))==4

    # shell/environment
    assert json.loads(run("ocean-wb-shell-split","echo 'hello world'"))==["echo","hello world"]
    assert run("ocean-wb-shell-command-exists","python3").strip()=="true"
    assert json.loads(run("ocean-wb-shell-argv-json","a","b"))==["a","b"]

print("PASS: 300 unique commands; every command help path plus all 15 functional domains validated")
