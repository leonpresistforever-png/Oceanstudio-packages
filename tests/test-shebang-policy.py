#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/fix-runtime-shebangs.py"
spec = importlib.util.spec_from_file_location("fix_runtime_shebangs", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

PREFIX = "/data/data/studio.ocean.app/files/usr"


class ShebangPolicy(unittest.TestCase):
    def test_env_bash(self):
        self.assertEqual(
            module.rewrite_line("#!/usr/bin/env bash", PREFIX),
            f"#!{PREFIX}/bin/bash",
        )

    def test_env_node_with_s_flag(self):
        self.assertEqual(
            module.rewrite_line("#!/usr/bin/env -S node --watch", PREFIX),
            f"#!{PREFIX}/bin/node --watch",
        )

    def test_bin_sh(self):
        self.assertEqual(
            module.rewrite_line("#!/bin/sh", PREFIX),
            f"#!{PREFIX}/bin/sh",
        )

    def test_ocean_prefix_unchanged(self):
        self.assertIsNone(module.rewrite_line(f"#!{PREFIX}/bin/bash", PREFIX))


if __name__ == "__main__":
    unittest.main()
