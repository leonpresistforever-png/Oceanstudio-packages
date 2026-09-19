#!/usr/bin/env python3
"""Package a pre-initialized static Nix chroot store for OceanStudio."""
from __future__ import annotations
import argparse, gzip, hashlib, json, os, re, shutil, subprocess, tempfile
from pathlib import Path

PREFIX="/data/data/studio.ocean.app/files/usr"
FORBIDDEN=(b"/data/data/com."+b"termux",b"/data/user/0/com."+b"termux",b"packages."+b"termux.dev",b"TERMUX_"+b"PREFIX")

def run(cmd,capture=False):
    return subprocess.run(list(map(str,cmd)),check=True,text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None)

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def control(stage,fields):
    d=stage/"DEBIAN";d.mkdir(parents=True)
    (d/"control").write_text("".join(f"{k}: {v}\n" for k,v in fields))

def normalize(root):
    for p in sorted(root.rglob("*"),reverse=True):
        try: os.utime(p,(0,0),follow_symlinks=False)
        except FileNotFoundError: pass
    os.utime(root,(0,0))

def validate_primary(binary):
    info=run(["readelf","-h","-l","-d",binary],capture=True).stdout
    if "AArch64" not in info: raise SystemExit("Nix bootstrap binary is not AArch64")
    if "Requesting program interpreter:" in info: raise SystemExit("Nix bootstrap binary is not static")
    needed=re.findall(r"\(NEEDED\).*?\[([^\]]+)\]",info)
    if needed: raise SystemExit("Nix bootstrap binary has dynamic dependencies: "+repr(needed))
    return info

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",type=Path,required=True)
    ap.add_argument("--root",type=Path,required=True,help="Prepared chroot store root created by nix copy --to local?root=...")
    ap.add_argument("--nix-output",required=True,help="Original /nix/store/... static Nix output path")
    ap.add_argument("--source",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--chroot-smoke",default="UNSPECIFIED")
    ap.add_argument("--proot-smoke",default="UNSPECIFIED")
    a=ap.parse_args()
    m=json.loads(a.manifest.read_text())
    root=a.root.resolve();source=a.source.resolve();out=a.output.resolve()
    if m["package"]!="nix-ocean" or m["prefix"]!=PREFIX: raise SystemExit("Nix manifest mismatch")
    if not a.nix_output.startswith("/nix/store/"): raise SystemExit("Nix output is not a store path")
    physical=root/a.nix_output.lstrip("/")
    primary=physical/"bin/nix"
    if not primary.is_file(): raise SystemExit("static Nix output has no bin/nix")
    validate_primary(primary)
    if run(["git","-C",source,"rev-parse","HEAD"],capture=True).stdout.strip()!=m["commit"]: raise SystemExit("Nix source commit mismatch")
    if run(["git","-C",source,"rev-parse","HEAD^{tree}"],capture=True).stdout.strip()!=m["tree"]: raise SystemExit("Nix source tree mismatch")
    if run(["git","-C",source,"rev-parse","HEAD:COPYING"],capture=True).stdout.strip()!=m["copyingBlob"]: raise SystemExit("Nix COPYING blob mismatch")

    # Add stable in-chroot command links without changing immutable store content.
    usrbin=root/"usr/bin";usrbin.mkdir(parents=True,exist_ok=True)
    source_bin=physical/"bin"
    commands=[]
    for executable in sorted(source_bin.iterdir()):
        if not (executable.is_file() or executable.is_symlink()): continue
        name=executable.name
        if not re.fullmatch(r"[A-Za-z0-9+._-]+",name): continue
        link=usrbin/name
        if link.exists() or link.is_symlink(): link.unlink()
        link.symlink_to(a.nix_output+"/bin/"+name)
        commands.append(name)
    if "nix" not in commands: raise SystemExit("Nix command was not exposed")

    etc=root/"etc";(etc/"nix").mkdir(parents=True,exist_ok=True)
    (etc/"passwd").write_text("root:x:0:0:root:/root:/bin/sh\nocean:x:1000:1000:Ocean:/home/ocean:/bin/sh\n")
    (etc/"group").write_text("root:x:0:\nocean:x:1000:\n")
    (etc/"nix/nix.conf").write_text(
        "sandbox = false\n"
        "build-users-group =\n"
        "experimental-features = nix-command flakes\n"
        "accept-flake-config = false\n"
    )
    (root/"tmp").mkdir(exist_ok=True);(root/"home/ocean").mkdir(parents=True,exist_ok=True)
    for p in ("android/system","android/vendor","android/product"):
        (root/p).mkdir(parents=True,exist_ok=True)

    cacerts=list((root/"nix/store").glob("*/etc/ssl/certs/ca-bundle.crt"))
    if not cacerts: cacerts=list((root/"nix/store").glob("*/etc/ssl/certs/ca-certificates.crt"))
    cert_target=""
    if cacerts:
        cert_target="/"+str(cacerts[0].relative_to(root))
        cert_dir=etc/"ssl/certs";cert_dir.mkdir(parents=True,exist_ok=True)
        cert_link=cert_dir/"ca-certificates.crt"
        if cert_link.exists() or cert_link.is_symlink():cert_link.unlink()
        cert_link.symlink_to(cert_target)

    with tempfile.TemporaryDirectory(prefix="nix-ocean-deb-") as td:
        stage=Path(td);prefix=stage/PREFIX.lstrip("/")
        runtime=prefix/"var/lib/nix-ocean/root";runtime.parent.mkdir(parents=True)
        shutil.copytree(root,runtime,symlinks=True)

        bindir=prefix/"bin";bindir.mkdir(parents=True)
        launcher=bindir/"nix-ocean"
        launcher.write_text(
            "#!/system/bin/sh\n"
            "set -eu\n"
            "PREFIX='"+PREFIX+"'\n"
            "ROOT=\"$PREFIX/var/lib/nix-ocean/root\"\n"
            "HOME_DIR=\"$PREFIX/var/lib/nix-ocean/home\"\n"
            "mkdir -p \"$HOME_DIR\" \"$ROOT/etc\" \"$ROOT/tmp\"\n"
            "DNS1=$(/system/bin/getprop net.dns1 2>/dev/null || true)\n"
            "DNS2=$(/system/bin/getprop net.dns2 2>/dev/null || true)\n"
            "if [ -n \"$DNS1$DNS2\" ]; then { [ -z \"$DNS1\" ] || echo \"nameserver $DNS1\"; [ -z \"$DNS2\" ] || echo \"nameserver $DNS2\"; } > \"$ROOT/etc/resolv.conf\"; fi\n"
            "export HOME=/home/ocean USER=ocean LOGNAME=ocean TMPDIR=/tmp\n"
            "export NIX_CONFIG='sandbox = false\nbuild-users-group =\nexperimental-features = nix-command flakes'\n"
            + (("export NIX_SSL_CERT_FILE='"+cert_target+"'\n") if cert_target else "") +
            "exec \"$PREFIX/bin/proot\" -0 -r \"$ROOT\" -b /dev:/dev -b /proc:/proc -b /sys:/sys "
            "-b /system:/android/system -b /vendor:/android/vendor -b \"$PREFIX:/ocean\" "
            "-b \"$HOME_DIR:/home/ocean\" -w /home/ocean /usr/bin/nix \"$@\"\n"
        )
        launcher.chmod(0o755)

        doc=prefix/"share/doc/nix-ocean";doc.mkdir(parents=True)
        shutil.copy2(source/"COPYING",doc/"COPYING")
        provenance={
          "schemaVersion":1,"package":"nix-ocean","version":m["version"],"upstream":m["upstream"],
          "commit":m["commit"],"tree":m["tree"],"buildAttribute":m["buildAttribute"],
          "buildSystem":m["buildSystem"],"nixOutput":a.nix_output,"commands":commands,
          "staticPrimarySha256":sha256(primary),"caCertificate":cert_target,
          "runtime":"Ocean proot with pre-initialized rooted Nix store",
          "chrootSmokeTest":a.chroot_smoke,
          "prootSmokeTest":a.proot_smoke,
          "deviceExecuted":False,
          "sourcePolicy":m["sourcePolicy"]
        }
        (doc/"ocean-build.json").write_text(json.dumps(provenance,indent=2)+"\n")
        control(stage,[("Package","nix-ocean"),("Version",m["version"]),("Architecture","aarch64"),
          ("Depends","proot"),("Maintainer","OceanStudio <maintainer@ocean.studio>"),
          ("Homepage","https://nixos.org/"),("Section","devel"),("Priority","optional"),
          ("Description","Official Nix package manager static ARM64 runtime in an isolated Ocean proot store")])

        # Scan generated control/runtime scripts for foreign package-manager identity.
        for p in stage.rglob("*"):
            if p.is_symlink() or not p.is_file():continue
            if p.stat().st_size<=8*1024*1024:
                data=p.read_bytes()
                if any(x in data for x in FORBIDDEN):raise SystemExit("forbidden Termux identity in "+str(p.relative_to(stage)))

        normalize(stage)
        out.parent.mkdir(parents=True,exist_ok=True)
        run(["dpkg-deb","--root-owner-group","-Zxz","--build",stage,out])

    report=out.parent/"provenance.json"
    provenance.update({"artifact":out.name,"artifactSha256":sha256(out),"artifactBytes":out.stat().st_size})
    report.write_text(json.dumps(provenance,indent=2)+"\n")
    print(json.dumps(provenance,indent=2))
    return 0
if __name__=="__main__":raise SystemExit(main())
