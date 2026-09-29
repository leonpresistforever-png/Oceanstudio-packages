#!/usr/bin/env python3
"""Smoke tests for priority userland half media helpers."""
from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "sources/priority-userland-half/ocean_media_half.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ocean_media_half", SRC)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_handlers_distinct():
    mod = load_module()
    names = [f"ocean-term-media-{i:03d}" for i in range(11, 51)]
    assert len(mod.HANDLERS) >= 50
    for name in names:
        assert name in mod.HANDLERS


def test_wav_info():
    mod = load_module()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        path = tf.name
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 100)
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        mod.HANDLERS["ocean-term-media-001"]([path])
    finally:
        sys.stdout = old
    assert '"channels": 1' in buf.getvalue()


if __name__ == "__main__":
    test_handlers_distinct()
    test_wav_info()
    print("ok")
