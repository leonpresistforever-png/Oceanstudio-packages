#!/usr/bin/env python3
"""Build and validate Ocean-owned distro manager packages.

This packages only Ocean source files. It never copies proot-distro/Termux
payloads, and unresolved distro entries remain safely uninstallable until they
carry a pinned SHA256.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, tempfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "/data/data/studio.ocean.app/files/usr"
SRC_DISTRO = ROOT / "packages/ocean-distro"
SRC_PROOT = ROOT / "packages/proot-distro"
OUT = ROOT / "staging/ocean-distro-repair"
VERSION = "1.0.1-4"
PROOT_VERSION = "4.18.0-1+ocean3"

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def run(*args, **kw):
    return subprocess.run(args, check=True, text=True, **kw)

def main():
    pool = OUT / "pool/main"
    pool.mkdir(parents=True, exist_ok=True)

    hard = {
        "foreign-app-prefix", "foreign-repository", "foreign-runtime-variable",
        "foreign-link-target", "unsafe-archive-path", "confirmed-ready-stub",
        "invalid-elf-header", "elf-reader-error"
    }
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from forensic_repository import scan_tar

    # First migrate the old Ocean shell-script package away from the manager's
    # executable. Preserve every unrelated script byte; this is ownership repair.
    run("python3", str(ROOT / "scripts/build-ocean-tools-ownership-repair.py"), "--output", str(OUT))

    # 1. Build ocean-distro
    with tempfile.TemporaryDirectory(prefix="ocean-distro-pkg-") as td:
        stage = Path(td)
        stage.chmod(0o755)
        root = stage / PREFIX.lstrip("/")
        (root / "bin").mkdir(parents=True)
        (root / "share/ocean-distro").mkdir(parents=True)
        shutil.copy2(SRC_DISTRO / "ocean-distro", root / "bin/ocean-distro")
        (root / "bin/ocean-distro").chmod(0o755)
        shutil.copy2(SRC_DISTRO / "distros.json", root / "share/ocean-distro/distros.json")
        debian = stage / "DEBIAN"
        debian.mkdir(mode=0o755)
        debian.chmod(0o755)
        control = (SRC_DISTRO / "control").read_text()
        if ("Version: " + VERSION) not in control:
            raise SystemExit("control version mismatch")
        (debian / "control").write_text(control)
        for p in stage.rglob("*"):
            os.utime(p, (0, 0), follow_symlinks=False)
        os.utime(stage, (0, 0))
        deb = pool / f"ocean-distro_{VERSION}_all.deb"
        run("dpkg-deb", "--root-owner-group", "-Zxz", "-z6", "--build", str(stage), str(deb))

        rows = list(scan_tar(deb)) + list(scan_tar(deb, control=True))
        defects = [{"path": r["path"], **f} for r in rows for f in r.get("findings", []) if f["kind"] in hard]
        if defects:
            raise SystemExit("ocean-distro package audit failed: " + repr(defects[:20]))

    # 2. Build the independent Ocean-authored PRoot manager and its own registry.
    with tempfile.TemporaryDirectory(prefix="proot-distro-pkg-") as pd_td:
        stage = Path(pd_td)
        stage.chmod(0o755)
        root = stage / PREFIX.lstrip("/")
        (root / "bin").mkdir(parents=True)
        (root / "share/proot-distro").mkdir(parents=True)
        shutil.copy2(SRC_PROOT / "proot-distro", root / "bin/proot-distro")
        (root / "bin/proot-distro").chmod(0o755)
        shutil.copy2(SRC_PROOT / "distros.json", root / "share/proot-distro/distros.json")
        debian = stage / "DEBIAN"
        debian.mkdir(mode=0o755)
        debian.chmod(0o755)
        control = (SRC_PROOT / "control").read_text()
        if ("Version: " + PROOT_VERSION) not in control:
            raise SystemExit("proot-distro control version mismatch")
        (debian / "control").write_text(control)
        for p in stage.rglob("*"):
            os.utime(p, (0, 0), follow_symlinks=False)
        os.utime(stage, (0, 0))
        pd_deb = pool / f"proot-distro_{PROOT_VERSION}_all.deb"
        run("dpkg-deb", "--root-owner-group", "-Zxz", "-z6", "--build", str(stage), str(pd_deb))

        pd_rows = list(scan_tar(pd_deb)) + list(scan_tar(pd_deb, control=True))
        pd_defects = [{"path": r["path"], **f} for r in pd_rows for f in r.get("findings", []) if f["kind"] in hard]
        if pd_defects:
            raise SystemExit("proot-distro package audit failed: " + repr(pd_defects[:20]))

    registry = json.loads((SRC_DISTRO / "distros.json").read_text())
    if len(registry) != 13:
        raise SystemExit(f"expected 13 distro records, got {len(registry)}")
    pinned = [n for n, v in registry.items() if isinstance(v.get("sha256"), str) and len(v["sha256"]) == 64]
    unresolved = [n for n, v in registry.items() if n not in pinned]

    test = subprocess.run(["python3", str(ROOT / "tests/test-ocean-distro.py")], capture_output=True, text=True)
    if test.returncode:
        raise SystemExit("ocean-distro tests failed: " + test.stdout + " " + test.stderr)
    independent = subprocess.run(["python3", str(ROOT / "tests/test-proot-distro-independent.py")], capture_output=True, text=True)
    if independent.returncode:
        raise SystemExit("independent PRoot manager tests failed: " + independent.stdout + " " + independent.stderr)

    report = {
        "status": "PASS_CANDIDATE",
        "package": "ocean-distro",
        "version": VERSION,
        "sha256": sha(deb),
        "prootDistroPackage": "proot-distro",
        "prootDistroVersion": PROOT_VERSION,
        "prootDistroSha256": sha(pd_deb),
        "sourcePolicy": "Ocean-owned manager; no Termux/proot-distro payload copied",
        "prefix": PREFIX,
        "advertisedDistros": list(registry),
        "pinnedChecksumEntries": pinned,
        "unresolvedChecksumEntries": unresolved,
        "checksumMeaning": "Pinned checksum is integrity metadata only; runtime verification is recorded separately by rootfs audits",
        "sourceTests": "PASS",
        "independentManagerTests": "PASS",
        "prootState": PREFIX + "/var/lib/proot-distro/installed-rootfs",
        "oceanState": "${OCEAN_HOME}/.distro",
        "physicalAndroidDeviceTested": False
    }
    (OUT / "provenance.json").write_text(json.dumps(report, indent=2) + chr(10))
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
