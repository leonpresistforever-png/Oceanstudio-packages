#!/usr/bin/env python3
"""Repair OpenJDK split-package ownership, maintainer scripts, and prove clean co-installation.

This repair:
1. Fixes openjdk-21-jre-headless maintainer scripts:
   - Removes hardcoded missing JDK slave alternatives that crash update-alternatives during dpkg --configure.
   - Gracefully checks for existing binaries before passing --slave.
   - Prevents non-zero exit codes from aborting package configuration.
   - Bumps version to 21.0.12-1+ocean1.
2. Fixes openjdk-21 (JDK):
   - Removes overlapping JRE-owned files from the JDK payload.
   - Fixes maintainer scripts to safely register alternatives.
   - Updates dependency to openjdk-21-jre-headless (= 21.0.12-1+ocean1).
   - Bumps version to 21.0.12-1+ocean1.
3. Stages both in staging/openjdk-21-repair/pool/main/ for seamless APT publication.
4. Validates unpack and mutual non-interference.
"""
from pathlib import Path
import hashlib, os, shutil, subprocess, tempfile

ROOT=Path(__file__).resolve().parents[1]
POOL=ROOT/"apt/pool/main"
JRE=POOL/"openjdk-21-jre-headless_21.0.12_aarch64.deb"
JDK=POOL/"openjdk-21_21.0.12_aarch64.deb"
OUT=ROOT/"staging/openjdk-21-repair"
OUT_POOL=OUT/"pool/main"
REPAIR_VERSION="21.0.12-1+ocean1"
PREFIX="data/data/studio.ocean.app/files/usr"

def run(*a, **kw): return subprocess.run(a, check=True, text=True, **kw)
def files(root):
    return {str(p.relative_to(root)):p for p in root.rglob("*") if (p.is_file() or p.is_symlink()) and "DEBIAN" not in p.relative_to(root).parts}
def same(a,b):
    if a.is_symlink() or b.is_symlink():
        return a.is_symlink() and b.is_symlink() and os.readlink(a)==os.readlink(b)
    return hashlib.sha256(a.read_bytes()).digest()==hashlib.sha256(b.read_bytes()).digest()

POSTINST_SCRIPT = """#!/data/data/studio.ocean.app/files/usr/bin/sh
if [ "$1" = 'configure' ] || [ "$1" = 'abort-upgrade' ] || [ "$1" = 'abort-deconfigure' ] || [ "$1" = 'abort-remove' ]; then
  if [ -x "/data/data/studio.ocean.app/files/usr/bin/update-alternatives" ]; then
    slaves=""
    for tool in jar jarsigner javac javadoc javap jcmd jconsole jdb jdeprscan jdeps jfr jhsdb jimage jinfo jlink jmap jmod jpackage jps jrunscript jshell jstack jstat jstatd jwebserver keytool rmiregistry serialver; do
      target="/data/data/studio.ocean.app/files/usr/lib/jvm/java-21-openjdk/bin/$tool"
      link="/data/data/studio.ocean.app/files/usr/bin/$tool"
      if [ -e "$target" ]; then
        slaves="$slaves --slave $link $tool $target"
      fi
    done
    for man in jar jarsigner java javac javadoc javap jcmd jconsole jdb jdeprscan jdeps jfr jhsdb jinfo jlink jmap jmod jpackage jps jrunscript jshell jstack jstat jstatd jwebserver keytool rmiregistry serialver; do
      target="/data/data/studio.ocean.app/files/usr/lib/jvm/java-21-openjdk/man/man1/$man.1.gz"
      link="/data/data/studio.ocean.app/files/usr/share/man/man1/$man.1.gz"
      if [ -e "$target" ]; then
        slaves="$slaves --slave $link $man.1.gz $target"
      fi
    done
    profile="/data/data/studio.ocean.app/files/usr/lib/jvm/java-21-openjdk/etc/profile.d/java.sh"
    if [ -e "$profile" ]; then
      slaves="$slaves --slave /data/data/studio.ocean.app/files/usr/etc/profile.d/java.sh java-profile $profile"
    fi
    if [ -e "/data/data/studio.ocean.app/files/usr/lib/jvm/java-21-openjdk/bin/java" ]; then
      update-alternatives --install "/data/data/studio.ocean.app/files/usr/bin/java" "java" "/data/data/studio.ocean.app/files/usr/lib/jvm/java-21-openjdk/bin/java" 60 $slaves || true
    fi
  fi
fi
exit 0
"""

PRERM_SCRIPT = """#!/data/data/studio.ocean.app/files/usr/bin/sh
if [ "$1" = 'remove' ] || [ "$1" != 'upgrade' ]; then
  if [ -x "/data/data/studio.ocean.app/files/usr/bin/update-alternatives" ]; then
    update-alternatives --remove "java" "/data/data/studio.ocean.app/files/usr/lib/jvm/java-21-openjdk/bin/java" || true
  fi
fi
exit 0
"""

PREINST_SCRIPT = """#!/data/data/studio.ocean.app/files/usr/bin/sh
if [ -x "/data/data/studio.ocean.app/files/usr/bin/update-alternatives" ]; then
  for item in java-profile jar jarsigner java javac javadoc javap jcmd jconsole jdb jdeprscan jdeps jfr jhsdb jimage jinfo jlink jmap jmod jpackage jps jrunscript jshell jstack jstat jstatd jwebserver keytool rmiregistry serialver jar.1.gz jarsigner.1.gz java.1.gz javac.1.gz javadoc.1.gz javap.1.gz jcmd.1.gz jconsole.1.gz jdb.1.gz jdeprscan.1.gz jdeps.1.gz jfr.1.gz jhsdb.1.gz jinfo.1.gz jlink.1.gz jmap.1.gz jmod.1.gz jpackage.1.gz jps.1.gz jrunscript.1.gz jshell.1.gz jstack.1.gz jstat.1.gz jstatd.1.gz jwebserver.1.gz keytool.1.gz rmiregistry.1.gz serialver.1.gz; do
    update-alternatives --remove-all "$item" 2>/dev/null || true
  done
fi
exit 0
"""

def fix_maintainer_scripts(pkg_dir):
    deb_dir = pkg_dir / "DEBIAN"
    deb_dir.mkdir(parents=True, exist_ok=True)
    for name, script in [("postinst", POSTINST_SCRIPT), ("prerm", PRERM_SCRIPT), ("preinst", PREINST_SCRIPT)]:
        target = deb_dir / name
        target.write_text(script)
        target.chmod(0o755)

def update_control_version(ctl_path, new_version, new_deps=None):
    lines = ctl_path.read_text().splitlines()
    v_done = False
    for i, l in enumerate(lines):
        if l.startswith("Version:"):
            lines[i] = f"Version: {new_version}"
            v_done = True
        elif l.startswith("Depends:") and new_deps:
            lines[i] = f"Depends: {new_deps}"
    if not v_done:
        lines.insert(2, f"Version: {new_version}")
    ctl_path.write_text("\n".join(lines) + "\n")

def main():
    with tempfile.TemporaryDirectory(prefix="ocean-openjdk-fix-") as td:
        t=Path(td); jr=t/"jre"; jd=t/"jdk"
        run("dpkg-deb","-R",str(JRE),str(jr))
        run("dpkg-deb","-R",str(JDK),str(jd))

        jf,df=files(jr),files(jd)
        overlap=sorted(set(jf)&set(df))
        differing=[p for p in overlap if not same(jf[p],df[p])]
        if differing:
            raise SystemExit("Refusing destructive split: overlapping paths differ: "+repr(differing[:20]))

        for p in overlap:
            df[p].unlink()

        # prune empty dirs in JDK
        for d in sorted((p for p in jd.rglob("*") if p.is_dir()), key=lambda p:len(p.parts), reverse=True):
            if d.name!="DEBIAN":
                try: d.rmdir()
                except OSError: pass

        # Fix maintainer scripts in both packages
        fix_maintainer_scripts(jr)
        fix_maintainer_scripts(jd)

        # Update JRE control version
        update_control_version(jr / "DEBIAN/control", REPAIR_VERSION)

        # Update JDK control version and exact JRE dependency
        jdk_lines = (jd / "DEBIAN/control").read_text().splitlines()
        orig_deps = []
        for l in jdk_lines:
            if l.startswith("Depends:"):
                orig_deps = [x.strip() for x in l[8:].split(",") if x.strip() and not x.strip().startswith("openjdk-21-jre-headless")]
                break
        dep_str = ", ".join([f"openjdk-21-jre-headless (= {REPAIR_VERSION})"] + orig_deps)
        update_control_version(jd / "DEBIAN/control", REPAIR_VERSION, dep_str)

        # Normalise timestamps
        for stage in (jr, jd):
            for p in stage.rglob("*"):
                if p.is_dir(): p.chmod(0o755)
                os.utime(p, (0, 0), follow_symlinks=False)
            os.utime(stage, (0, 0))

        shutil.rmtree(OUT, ignore_errors=True)
        OUT_POOL.mkdir(parents=True, exist_ok=True)

        cand_jre = OUT_POOL / f"openjdk-21-jre-headless_{REPAIR_VERSION}_aarch64.deb"
        cand_jdk = OUT_POOL / f"openjdk-21_{REPAIR_VERSION}_aarch64.deb"

        run("dpkg-deb","-Zxz","-z6","--root-owner-group","--build",str(jr),str(cand_jre))
        run("dpkg-deb","-Zxz","-z6","--root-owner-group","--build",str(jd),str(cand_jdk))

        # Verify no residual overlap
        chk_jre, chk_jdk = t/"chk_jre", t/"chk_jdk"
        run("dpkg-deb","-x",str(cand_jre),str(chk_jre))
        run("dpkg-deb","-x",str(cand_jdk),str(chk_jdk))
        residual=sorted(set(files(chk_jre))&set(files(chk_jdk)))
        if residual: raise SystemExit("Residual ownership overlap: "+repr(residual[:20]))

        # Test unpack in disposable dpkg root
        guest=t/"root"; (guest/"var/lib/dpkg").mkdir(parents=True); (guest/"var/lib/dpkg/status").write_text("")
        cmd=["dpkg","--force-not-root","--force-architecture","--root="+str(guest),"--unpack",str(cand_jre),str(cand_jdk)]
        r=subprocess.run(cmd,text=True,capture_output=True)
        if r.returncode: raise SystemExit("Clean co-install failed:\n"+r.stdout+"\n"+r.stderr)

        # Generate report
        report=OUT/"repair-report.txt"
        report.write_text(f"status=REPAIRED_CANDIDATE\nversion={REPAIR_VERSION}\n"
                          f"overlap_removed={len(overlap)}\ndiffering_overlap=0\nresidual_overlap=0\n"
                          f"clean_dpkg_unpack=PASS\ncompression=xz\n"
                          f"jre_sha256={hashlib.sha256(cand_jre.read_bytes()).hexdigest()}\n"
                          f"jdk_sha256={hashlib.sha256(cand_jdk.read_bytes()).hexdigest()}\n"
                          f"maintainer_scripts_fixed=true\nandroid_runtime_tested=false\n")
        print(report.read_text())

if __name__=="__main__":
    main()
