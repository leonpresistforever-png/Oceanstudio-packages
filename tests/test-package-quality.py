#!/usr/bin/env python3
"""Tests for Ocean package quality gate and shard builders."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

this = Path(__file__).resolve()
if (this.parents[1] / "scripts").is_dir():
    ROOT = this.parents[1]
    SCRIPTS = ROOT / "scripts"
    PACKAGES = ROOT / "packages/ocean-shard-multiplier"
elif (this.parents[2] / "ocean-packages/scripts").is_dir():
    ROOT = this.parents[2] / "ocean-packages"
    SCRIPTS = ROOT / "scripts"
    PACKAGES = ROOT / "packages/ocean-shard-multiplier"
else:
    ROOT = this.parents[1]
    SCRIPTS = ROOT / "scripts"
    PACKAGES = ROOT / "packages/ocean-shard-multiplier"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import package_quality as quality  # noqa: E402


class PackageQualityTests(unittest.TestCase):
    def test_junk_names_rejected(self):
        for name in (
            "ocean-term-media-001",
            "ocean-term-media-core",
            "placeholder-foo",
            "visual-only-bar",
        ):
            reason = quality.junk_name_reason(name)
            self.assertIsNotNone(reason, name)

    def test_ecosystem_names_allowed(self):
        self.assertIsNone(quality.junk_name_reason("ocean-distro"))
        self.assertIsNone(quality.junk_name_reason("ocean-shard-router"))

    def test_shard_packages_build_and_pass_gate(self):
        subprocess.run(
            ["python3", str(SCRIPTS / "build-ocean-shard-packages.py")],
            check=True,
            cwd=ROOT,
        )
        manifest_path = ROOT / "sources/shard-multiplier-manifest.json"
        if not manifest_path.is_file():
            manifest_path = ROOT / "ocean-packages/sources/shard-multiplier-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(len(manifest["packages"]), 5)
        staging = ROOT / "staging/shard-multiplier/pool/main/ocean-shard"
        if not staging.is_dir():
            staging = ROOT / "ocean-packages/staging/shard-multiplier/pool/main/ocean-shard"
        for entry in manifest["packages"]:
            deb = staging / entry["artifact"]
            self.assertTrue(deb.is_file(), deb)
            verdict = quality.assess_deb(deb)
            self.assertFalse(verdict.reject, verdict.reasons)

    def test_router_cli_dry_run(self):
        script = PACKAGES / "ocean-shard-router"
        routes = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        routes.write(json.dumps([{"prefix": "git.", "command": "echo"}]))
        routes.flush()
        proc = subprocess.run(
            [
                "python3",
                str(script),
                "--routes",
                routes.name,
                "--tool",
                "git.status",
                "--dry-run",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["tool"], "git.status")

    def test_blob_split_join_roundtrip(self):
        script = PACKAGES / "ocean-shard-blob-split"
        with tempfile.TemporaryDirectory() as temporary:
            src = Path(temporary) / "input.bin"
            src.write_bytes(b"ocean-shard-blob-" + b"x" * 2000)
            out = Path(temporary) / "shards"
            subprocess.run(
                ["python3", str(script), "split", "--input", str(src), "--output", str(out)],
                check=True,
            )
            joined = Path(temporary) / "joined.bin"
            subprocess.run(
                [
                    "python3",
                    str(script),
                    "join",
                    "--manifest",
                    str(out / "manifest.json"),
                    "--output",
                    str(joined),
                ],
                check=True,
            )
            self.assertEqual(src.read_bytes(), joined.read_bytes())


if __name__ == "__main__":
    unittest.main()
