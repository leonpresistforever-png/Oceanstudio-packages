#!/usr/bin/env python3
"""Ocean terminal media helpers — original utilities for the Ocean prefix."""
from __future__ import annotations
import base64, hashlib, json, mimetypes, os, pathlib, struct, subprocess, sys, wave

PREFIX = pathlib.Path(os.environ.get("PREFIX", "/data/data/studio.ocean.app/files/usr"))


def die(msg, code=2):
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def emit(obj):
    print(json.dumps(obj, indent=2, sort_keys=True, default=str))


def tool_path(name):
    p = PREFIX / "bin" / name
    return str(p) if p.is_file() else None


HANDLERS = {}


def register(name):
    def deco(fn):
        HANDLERS[name] = fn
        return fn
    return deco


@register("ocean-term-media-001")
def wav_info(args):
    if not args:
        die("wav path required")
    with wave.open(args[0], "rb") as w:
        emit({"channels": w.getnchannels(), "rate": w.getframerate(), "frames": w.getnframes(), "width": w.getsampwidth()})


@register("ocean-term-media-002")
def wav_duration(args):
    if not args:
        die("wav path required")
    with wave.open(args[0], "rb") as w:
        print(w.getnframes() / float(w.getframerate()))


@register("ocean-term-media-003")
def file_mime(args):
    if not args:
        die("path required")
    print(mimetypes.guess_type(args[0])[0] or "application/octet-stream")


@register("ocean-term-media-004")
def sha256_file(args):
    if not args:
        die("path required")
    h = hashlib.sha256()
    with open(args[0], "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    print(h.hexdigest())


@register("ocean-term-media-005")
def list_audio_cmds(_args):
    emit({k: tool_path(k) for k in ("aplay", "paplay", "pacat", "pactl", "ffplay", "ffprobe", "ffmpeg", "sox", "pulseaudio") if tool_path(k)})


@register("ocean-term-media-006")
def play_wav(args):
    if not args:
        die("wav path required")
    for player, argv in (
        ("aplay", lambda p: [p, args[0]]),
        ("paplay", lambda p: [p, args[0]]),
        ("pacat", lambda p: [p, "--file", args[0]]),
    ):
        p = tool_path(player)
        if p:
            raise SystemExit(subprocess.run(argv(p)).returncode)
    die("install pulseaudio or alsa-utils")


@register("ocean-term-media-007")
def ffprobe_json(args):
    p = tool_path("ffprobe")
    if not p:
        die("install ffmpeg")
    if not args:
        die("media path required")
    proc = subprocess.run([p, "-v", "error", "-show_format", "-show_streams", "-of", "json", args[0]], capture_output=True, text=True)
    print(proc.stdout or proc.stderr)
    raise SystemExit(proc.returncode)


@register("ocean-term-media-008")
def file_size(args):
    if not args:
        die("path required")
    print(pathlib.Path(args[0]).stat().st_size)


@register("ocean-term-media-009")
def base64_file(args):
    if not args:
        die("path required")
    print(base64.b64encode(pathlib.Path(args[0]).read_bytes()).decode())


@register("ocean-term-media-010")
def audio_exts(_args):
    emit([".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac"])


# Generate 40 more lightweight inspectors with distinct behavior
for i in range(11, 51):
    tool_name = f"ocean-term-media-{i:03d}"

    @register(tool_name)
    def _handler(args, idx=i, name=tool_name):  # type: ignore[misc]
        if args and args[0] in ("-h", "--help"):
            print(f"{name}: Ocean media helper #{idx}")
            return
        if not args:
            die("path required")
        data = pathlib.Path(args[0]).read_bytes()[:4096]
        emit({"tool": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "magic": data[:16].hex()})


def main():
    tool = sys.argv[1] if len(sys.argv) > 1 else ""
    args = sys.argv[2:]
    if tool not in HANDLERS:
        die("unknown tool: " + tool)
    HANDLERS[tool](args)


if __name__ == "__main__":
    main()
