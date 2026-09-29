#!/usr/bin/env python3
"""Build 63 new terminal packages: CLI bridges + Ocean media helpers."""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, subprocess, tempfile
from pathlib import Path

PREFIX = "/data/data/studio.ocean.app/files/usr"
VERSION = "1.0.0-1+ocean1"
CORE = "ocean-term-media-core"

# kind: shell installs a PREFIX/bin wrapper; meta is Depends-only (binary comes from dependency)
BRIDGES = [
    ("notify-send", "ocean-notify", "shell", "Send Android notifications via ocean-notify", "utils"),
    ("aplay", "pulseaudio", "shell", "Play audio via pulseaudio paplay/pacat or alsa-utils", "sound"),
    ("arecord", "pulseaudio", "shell", "Record audio via pulseaudio pacat or alsa-utils", "sound"),
    ("paplay", "pulseaudio", "meta", "Install name for pulseaudio paplay binary", "sound"),
    ("pacat", "pulseaudio", "meta", "Install name for pulseaudio pacat binary", "sound"),
    ("pactl", "pulseaudio", "meta", "Install name for pulseaudio pactl binary", "sound"),
    ("parec", "pulseaudio", "meta", "Install name for pulseaudio parec binary", "sound"),
    ("parecord", "pulseaudio", "meta", "Install name for pulseaudio parecord binary", "sound"),
    ("ffprobe", "ffmpeg", "meta", "Install name for ffmpeg ffprobe binary", "video"),
    ("ffplay", "ffmpeg", "meta", "Install name for ffmpeg ffplay binary", "video"),
    ("xeyes", "ocean-x11-runtime, proot-distro", "shell", "Launch xeyes in Ocean X11 guest", "x11"),
    ("ocean", "ocean-notify, ocean-api", "shell", "OceanStudio multi-command dispatcher", "utils"),
]

BRIDGE_SCRIPTS = {
    "notify-send": f'''#!{PREFIX}/bin/sh
exec {PREFIX}/bin/ocean-notify "$@"
''',
    "aplay": f'''#!{PREFIX}/bin/sh
if [ -x "{PREFIX}/bin/aplay.real" ]; then exec "{PREFIX}/bin/aplay.real" "$@"; fi
if [ -x "{PREFIX}/bin/paplay" ]; then exec "{PREFIX}/bin/paplay" "$@"; fi
if [ -x "{PREFIX}/bin/pacat" ]; then exec "{PREFIX}/bin/pacat" --playback "$@"; fi
echo "install pulseaudio or alsa-utils" >&2; exit 127
''',
    "arecord": f'''#!{PREFIX}/bin/sh
if [ -x "{PREFIX}/bin/arecord.real" ]; then exec "{PREFIX}/bin/arecord.real" "$@"; fi
if [ -x "{PREFIX}/bin/pacat" ]; then exec "{PREFIX}/bin/pacat" --record "$@"; fi
echo "install pulseaudio or alsa-utils" >&2; exit 127
''',
    "xeyes": f'''#!{PREFIX}/bin/sh
exec {PREFIX}/bin/ocean-x11-run sh -lc 'command -v xeyes >/dev/null 2>&1 || (apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y x11-apps); exec xeyes'
''',
    "ocean": f'''#!{PREFIX}/bin/sh
case "$1" in
  notify) shift; exec {PREFIX}/bin/ocean-notify "$@";;
  open-audio) shift; exec {PREFIX}/bin/ocean-open-audio "$@";;
  x11) shift; exec {PREFIX}/bin/ocean-x11 "$@";;
  "") echo "usage: ocean notify|open-audio|x11 ..." >&2; exit 2;;
  *) echo "unknown ocean subcommand: $1" >&2; exit 2;;
esac
''',
}

MEDIA_TOOLS = [f"ocean-term-media-{i:03d}" for i in range(1, 51)]


def run(cmd):
    subprocess.run(cmd, check=True)


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_deb(pkg, desc, section, depends, files, outpath: Path):
    with tempfile.TemporaryDirectory(prefix="ocean-half-") as td:
        root = Path(td)
        (root / "DEBIAN").mkdir()
        for rel, (content, mode) in files.items():
            p = root / rel.lstrip("/")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            p.chmod(mode)
        (root / "DEBIAN/control").write_text(
            f"Package: {pkg}\nVersion: {VERSION}\nArchitecture: all\n"
            "Maintainer: OceanStudio Packaging Team <maintainer@ocean.studio>\n"
            f"Section: {section}\nPriority: optional\nDepends: {depends}\n"
            f"Description: {desc}\n Ocean terminal package for OceanStudio on Android.\n",
            encoding="utf-8",
        )
        for p in root.rglob("*"):
            try:
                os.utime(p, (0, 0), follow_symlinks=False)
            except FileNotFoundError:
                pass
        run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", str(root), str(outpath)])


def pool_relpath(path: Path) -> str:
    parts = path.parts
    if "main" in parts:
        idx = parts.index("main")
        return "pool/main/" + "/".join(parts[idx + 1 :])
    return f"pool/main/{path.name}"


def stanza(pkg, desc, section, path: Path):
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    return (
        f"Package: {pkg}\nVersion: {VERSION}\nArchitecture: all\n"
        "Maintainer: OceanStudio Packaging Team <maintainer@ocean.studio>\n"
        f"Depends: {CORE if pkg != CORE else 'python'}\n"
        f"Filename: {pool_relpath(path)}\nSize: {len(data)}\n"
        f"MD5sum: {hashlib.md5(data).hexdigest()}\nSHA1: {hashlib.sha1(data).hexdigest()}\n"
        f"SHA256: {digest}\nSection: {section}\nPriority: optional\n"
        f"Description: {desc}\n Ocean terminal package for OceanStudio on Android."
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--existing-packages", required=True)
    ap.add_argument("--source", required=True)
    args = ap.parse_args()
    out = Path(args.output)
    existing = set(re.findall(r"^Package:\s*(\S+)", Path(args.existing_packages).read_text(), re.M))
    shutil.rmtree(out, ignore_errors=True)
    bridge_dir = out / "pool/main/bridge"
    term_dir = out / "pool/main/ocean-term"
    core_dir = term_dir / "core"
    bridge_dir.mkdir(parents=True, exist_ok=True)
    core_dir.mkdir(parents=True, exist_ok=True)
    candidates = [CORE] + [b[0] for b in BRIDGES] + MEDIA_TOOLS
    collisions = sorted(existing.intersection(candidates))
    if collisions:
        raise SystemExit("collisions: " + ", ".join(collisions))
    if len(candidates) != 63:
        raise SystemExit(f"expected 63 packages, got {len(candidates)}")

    core_src = (Path(args.source) / "ocean_media_half.py").read_text(encoding="utf-8")
    core_deb = core_dir / f"{CORE}_{VERSION}_all.deb"
    build_deb(
        CORE,
        "Shared runtime for Ocean terminal media helper commands",
        "utils",
        "python",
        {
            f"{PREFIX}/lib/ocean-term/ocean_media_half.py": (core_src, 0o644),
            f"{PREFIX}/bin/ocean-term-media": (
                f"#!{PREFIX}/bin/bash\nexec {PREFIX}/bin/python {PREFIX}/lib/ocean-term/ocean_media_half.py \"$@\"\n",
                0o755,
            ),
        },
        core_deb,
    )
    stanzas = [stanza(CORE, "Shared runtime for Ocean terminal media helper commands", "utils", core_deb)]
    for name, depends, kind, desc, section in BRIDGES:
        deb = bridge_dir / f"{name}_{VERSION}_all.deb"
        if kind == "meta":
            build_deb(name, desc, section, depends, {}, deb)
        elif kind == "shell":
            build_deb(
                name,
                desc,
                section,
                depends,
                {f"{PREFIX}/bin/{name}": (BRIDGE_SCRIPTS[name], 0o755)},
                deb,
            )
        else:
            raise SystemExit(f"unknown bridge kind: {kind}")
        stanzas.append(stanza(name, desc, section, deb))
    for tool in MEDIA_TOOLS:
        deb = term_dir / f"{tool}_{VERSION}_all.deb"
        wrapper = (
            f"#!{PREFIX}/bin/bash\nexec {PREFIX}/bin/python {PREFIX}/lib/ocean-term/ocean_media_half.py {tool} \"$@\"\n"
        )
        build_deb(
            tool,
            f"Ocean media helper command {tool}",
            "sound",
            f"{CORE}, python",
            {f"{PREFIX}/bin/{tool}": (wrapper, 0o755)},
            deb,
        )
        stanzas.append(stanza(tool, f"Ocean media helper command {tool}", "sound", deb))
    (out / "Packages.new").write_text("\n\n".join(stanzas) + "\n", encoding="utf-8")
    (out / "provenance.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "suite": "priority-userland-half",
                "packageCount": len(candidates),
                "uniquePackageCount": len(candidates),
                "bridges": [b[0] for b in BRIDGES],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Built {len(candidates)} packages into {out}")


if __name__ == "__main__":
    main()
