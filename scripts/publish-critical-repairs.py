#!/usr/bin/env python3
"""Compatibility entry point for complete publication, with the shared gates.

All legitimate package names are preserved. There is no fixed candidate list.
"""
from pathlib import Path
import argparse
import json
import subprocess
import sys
import tempfile
from index_all_staged import ROOT, select_packages, run_indexing
from audit_repository import audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--plan', type=Path)
    args = parser.parse_args()
    if args.plan:
        _, report = select_packages(args.root)
        args.plan.parent.mkdir(parents=True, exist_ok=True)
        args.plan.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({k: v for k, v in report.items() if k != 'updates'}))
        return
    with tempfile.TemporaryDirectory(prefix='ocean-publication-gate-') as directory:
        subprocess.run([sys.executable, ROOT / 'scripts/check-publication-payloads.py',
                        '--root', args.root, '--json', Path(directory) / 'gate.json'], check=True)
    run_indexing(root=args.root)
    result = audit(args.root)
    if result['errors']:
        raise ValueError('Post-publication audit failed: ' + repr(result['errors']))


if __name__ == '__main__':
    main()
