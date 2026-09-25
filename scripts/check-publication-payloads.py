#!/usr/bin/env python3
"""Reject new payload defects and undeclared file collisions before publication.

The earlier complete inventory is reusable only for byte-identical archives,
after the selector has hashed every candidate. All other candidates are read in
full. Existing defects are reported without deleting packages to make checks pass.
This is a regression gate, not certification of all unchanged packages.
"""
from collections import defaultdict
import argparse
import gzip
import itertools
import json
from pathlib import Path

from audit_package_payloads import dependencies, dependency_errors, satisfies
from forensic_repository import scan_tar, elf_role
from index_all_staged import ROOT, INDEX, fields, stanzas, identity, select_packages

BASELINE = 'audits/forensic/45bd61a0d25f7676f1dbef2c8fcac9065b3e446d'
HARD_FINDINGS = {'foreign-app-prefix', 'foreign-repository', 'foreign-runtime-variable',
    'foreign-link-target', 'unsafe-archive-path', 'confirmed-ready-stub', 'invalid-elf-header', 'elf-reader-error'}


def relation(record, other, field):
    for group in dependencies(record.get(field, '')):
        for name, arch, operator, version in group:
            if name == other['Package'] and arch in (None, 'any', 'native', other['Architecture']):
                if satisfies(other['Version'], operator, version):
                    return True
    return False


def declared_overlap(left, right):
    # Explicit mutually-exclusive packages and versioned ownership transfers
    # are valid metadata patterns; an undeclared overwrite is not.
    return any(relation(a, b, f) for a, b in ((left, right), (right, left))
               for f in ('Conflicts', 'Replaces'))


def assess(before, after, payloads):
    old = {identity(r): r for r in before}
    new = {identity(r): r for r in after}
    changed = {k for k, r in new.items() if old.get(k, {}).get('SHA256') != r['SHA256']}

    def ownership(records):
        owners = defaultdict(set)
        for key, record in records.items():
            for row in payloads[record['SHA256']]:
                if row['section'] == 'payload' and row['kind'] != 'directory':
                    owners[row['path']].add(key)
        return owners

    before_owners, after_owners = ownership(old), ownership(new)
    errors = [dict(kind='unresolved-dependency', **problem) for problem in dependency_errors(after)]
    remaining = []
    for key in changed:
        record = new[key]
        for row in payloads[record['SHA256']]:
            for finding in row.get('findings', []):
                if finding['kind'] in HARD_FINDINGS:
                    errors.append({'package': record['Package'], 'path': row['path'], **finding})
            elf = row.get('elf')
            # A byte-identical cached inventory can predate classification fixes.
            # Reclassify from its recorded ELF header, retaining all raw findings.
            role = elf_role(row['path'], elf['machine'], elf.get('type')) if elf else None
            if elf and role == 'native-elf' and (elf['machine'] != 183 or record['Architecture'] == 'all'):
                errors.append({'package': record['Package'], 'path': row['path'], 'kind': 'native-architecture',
                    'machine': elf['machine'], 'declared': record['Architecture']})
    for path, keys in sorted(after_owners.items()):
        if len({k[0] for k in keys}) < 2:
            continue
        for left, right in itertools.combinations(sorted(keys), 2):
            if left[0] == right[0] or declared_overlap(new[left], new[right]):
                continue
            issue = {'kind': 'undeclared-file-overlap', 'path': path, 'packages': [left[0], right[0]]}
            existing = {left, right}.issubset(before_owners.get(path, set()))
            if not existing or left in changed or right in changed:
                errors.append(issue)
            else:
                remaining.append(issue)
    return {'changedPackages': len(changed), 'errors': errors, 'unchangedExistingCollisions': remaining,
        'overlappingPathsAfter': len({p for p, owners in after_owners.items() if len({k[0] for k in owners}) > 1}),
        'androidRuntimeTested': False, 'scope': 'Regression gate; unchanged packages are not certified functional'}


def check(root, baseline):
    selected, selection = select_packages(root)
    before = [fields(s) for s in stanzas((root / 'apt/dists/stable' / INDEX).read_text())]
    after = [r for _, r, _ in selected.values()]
    paths = {r['SHA256']: root / 'apt' / r['Filename'] for r in before}
    paths.update({r['SHA256']: path for _, r, path in selected.values()})
    cache = defaultdict(list)
    if (baseline / 'forensic-report.json').exists() and (baseline / 'file-inventory.jsonl.gz').exists():
        audit = json.loads((baseline / 'forensic-report.json').read_text())
        if not audit.get('complete') or audit.get('invalidArchives'):
            raise ValueError('Incomplete forensic evidence cannot be used as a cache')
        archive_hashes = {r['path']: r['sha256'] for r in audit['archives'] if 'sha256' in r}
        with gzip.open(baseline / 'file-inventory.jsonl.gz', 'rt') as inventory:
            for line in inventory:
                row = json.loads(line)
                digest = archive_hashes.get(row['archive'])
                if digest in paths:
                    cache[digest].append(row)
    reused = len(cache)
    for digest, path in paths.items():
        if digest not in cache:
            cache[digest] = [dict(section='payload', **r) for r in scan_tar(path)]
            cache[digest] += [dict(section='control', **r) for r in scan_tar(path, control=True)]
    result = assess(before, after, cache)
    result.update(indexedBefore=selection['indexedBefore'], indexedAfter=selection['indexedAfter'],
        hashMatchedAuditArchives=reused, fullyReadAdditionalArchives=len(cache) - reused)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--baseline', type=Path)
    p.add_argument('--json', type=Path, required=True)
    a = p.parse_args()
    result = check(a.root, a.baseline or a.root / BASELINE)
    a.json.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('errors', 'unchangedExistingCollisions')}, indent=2))
    for error in result['errors'][:30]:
        print(json.dumps(error))
    raise SystemExit(bool(result['errors']))
