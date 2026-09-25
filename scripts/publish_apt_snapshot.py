#!/usr/bin/env python3
"""Publish a fully checked snapshot; regenerate after concurrent main updates."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def git(root, *args, check=True):
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=check)


def publish(root, rebuild, attempts=3):
    """The caller owns an isolated checkout. No signed snapshot is rebased."""
    if git(root, "status", "--porcelain", "--untracked-files=no").stdout:
        raise ValueError("Publication requires a clean tracked checkout")
    for attempt in range(1, attempts + 1):
        base = git(root, "rev-parse", "HEAD").stdout.strip()
        rebuild(root, attempt)
        git(root, "add", "apt/pool", "apt/dists/stable")
        if git(root, "diff", "--cached", "--quiet", check=False).returncode == 0:
            return {"status": "already-current", "commit": base, "attempts": attempt}
        git(root, "-c", "user.name=Ocean Package Builder", "-c", "user.email=packages@ocean.studio",
            "commit", "-m", "fix(apt): publish complete verified signed package index [skip ci]")
        commit = git(root, "rev-parse", "HEAD").stdout.strip()
        pushed = git(root, "push", "origin", "HEAD:main", check=False)
        if pushed.returncode == 0:
            return {"status": "published", "commit": commit, "attempts": attempt}
        print(pushed.stderr, file=sys.stderr)
        if attempt == attempts:
            raise RuntimeError("Publication push failed after bounded retries; no forced update was attempted")
        git(root, "fetch", "origin", "main")
        if git(root, "merge-base", "--is-ancestor", base, "FETCH_HEAD", check=False).returncode:
            raise RuntimeError("Remote main no longer descends from the audited base; refusing automatic reset")
        if git(root, "status", "--porcelain", "--untracked-files=no").stdout:
            raise RuntimeError("Checkout changed during publication; preserving it for inspection")
        # This is a disposable Actions checkout. Drop only this failed local
        # publication commit, then re-read all candidates, rerun every gate and
        # regenerate both signatures against the now-current repository.
        git(root, "reset", "--hard", "FETCH_HEAD")
    raise AssertionError("unreachable")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true":
        parser.error("This retry publisher is restricted to a disposable GitHub Actions checkout")
    args.report_dir.mkdir(parents=True, exist_ok=True)

    def rebuild(root, attempt):
        prefix = args.report_dir / f"attempt-{attempt}"
        commands = [
            ["index_all_staged.py", "--plan", str(prefix) + "-selection.json"],
            ["check-publication-payloads.py", "--json", str(prefix) + "-payloads.json"],
            ["index_all_staged.py"],
            ["audit_repository.py", "--json", str(prefix) + "-audit.json"],
        ]
        for script, *arguments in commands:
            subprocess.run([sys.executable, root / "scripts" / script, "--root", root, *arguments],
                           cwd=root, check=True)

    result = publish(args.root.resolve(), rebuild)
    (args.report_dir / "publication.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
