#!/usr/bin/env python3
"""Indexer rejects junk staging packages via package_quality integration."""
from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

this = Path(__file__).resolve()
if (this.parents[1] / "scripts").is_dir():
    ROOT = this.parents[1]
    SCRIPTS = ROOT / "scripts"
elif (this.parents[2] / "ocean-packages/scripts").is_dir():
    ROOT = this.parents[2] / "ocean-packages"
    SCRIPTS = ROOT / "scripts"
else:
    ROOT = this.parents[1]
    SCRIPTS = ROOT / "scripts"


class IndexQualityGateTests(unittest.TestCase):
    def test_select_packages_skips_junk_staging(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            dists = repo / "apt/dists/stable/main/binary-aarch64"
            dists.mkdir(parents=True)
            (dists / "Packages").write_text(
                "Package: bash\nVersion: 1.0\nArchitecture: aarch64\n"
                "Maintainer: t\nDescription: d\n"
                "Filename: pool/main/bash_1.0_aarch64.deb\n"
                "Size: 100\nMD5sum: aa\nSHA1: bb\nSHA256: cc\n\n",
                encoding="utf-8",
            )
            (dists / "Packages.gz").write_bytes(gzip.compress((dists / "Packages").read_bytes(), mtime=0))
            pool = repo / "apt/pool/main"
            pool.mkdir(parents=True)
            (pool / "bash_1.0_aarch64.deb").write_bytes(b"not-a-real-deb")
            staging = repo / "staging"
            staging.mkdir()
            junk = staging / "ocean-term-media-001_1.0.0-1+ocean1_all.deb"
            subprocess.run(
                [
                    "bash",
                    "-c",
                    f"""
set -euo pipefail
work=$(mktemp -d)
chmod 755 "$work"
mkdir -p "$work/DEBIAN" "$work/data/data/studio.ocean.app/files/usr/bin"
printf 'Package: ocean-term-media-001\\nVersion: 1.0.0-1+ocean1\\nArchitecture: all\\nMaintainer: t\\nDepends: bash\\nDescription: filler\\n' > "$work/DEBIAN/control"
printf '#!/bin/sh\\necho ok\\n' > "$work/data/data/studio.ocean.app/files/usr/bin/fake"
chmod -R 755 "$work"
dpkg-deb --root-owner-group -b "$work" "{junk}"
""",
                ],
                check=True,
            )
            sys.path.insert(0, str(SCRIPTS))
            from index_all_staged import select_packages

            # parse_deb on fake bash will fail - use minimal real deb for indexed entry instead
            # Build a valid bash deb for index consistency
            good = pool / "bash_1.0_aarch64.deb"
            good.unlink(missing_ok=True)
            subprocess.run(
                [
                    "bash",
                    "-c",
                    f"""
set -euo pipefail
work=$(mktemp -d)
chmod 755 "$work"
mkdir -p "$work/DEBIAN" "$work/data/data/studio.ocean.app/files/usr/bin"
printf 'Package: bash\\nVersion: 1.0\\nArchitecture: aarch64\\nMaintainer: t\\nDescription: d\\n' > "$work/DEBIAN/control"
printf '#!/bin/sh\\necho bash\\n' > "$work/data/data/studio.ocean.app/files/usr/bin/bash"
chmod -R 755 "$work"
dpkg-deb --root-owner-group -b "$work" "{good}"
""",
                ],
                check=True,
            )
            from index_all_staged import parse_deb, make_stanza, hashes

            text, digest = parse_deb(good)
            stanza = make_stanza(text, digest, good.name, "pool/main/bash_1.0_aarch64.deb")
            (dists / "Packages").write_text(stanza + "\n\n", encoding="utf-8")
            (dists / "Packages.gz").write_bytes(gzip.compress((dists / "Packages").read_bytes(), mtime=0))

            _, report = select_packages(repo)
            self.assertEqual(report["indexedBefore"], 1)
            self.assertEqual(report["indexedAfter"], 1)
            self.assertGreaterEqual(len(report["rejectedStaging"]), 1)
            self.assertEqual(report["rejectedStaging"][0]["package"], "ocean-term-media-001")


if __name__ == "__main__":
    unittest.main()
