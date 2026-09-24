#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
spec = importlib.util.spec_from_file_location('gate', Path(__file__).resolve().parents[1] / 'scripts/check-publication-payloads.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def package(name, version='1', **extra):
    return {'Package': name, 'Version': version, 'Architecture': 'all', 'SHA256': name + '-' + version, **extra}


def file(path, **extra):
    return {'path': path, 'kind': 'file', 'section': 'payload', 'findings': [], **extra}


class GateTests(unittest.TestCase):
    def test_new_undeclared_collision_is_rejected(self):
        a, b = package('left'), package('right')
        result = gate.assess([a], [a, b], {'left-1': [file('bin/same')], 'right-1': [file('bin/same')]})
        self.assertEqual(result['errors'][0]['kind'], 'undeclared-file-overlap')

    def test_unchanged_legacy_defect_is_reported_without_package_deletion(self):
        a, b = package('left'), package('right')
        result = gate.assess([a, b], [a, b], {'left-1': [file('bin/same')], 'right-1': [file('bin/same')]})
        self.assertFalse(result['errors'])
        self.assertEqual(len(result['unchangedExistingCollisions']), 1)

    def test_upgrading_a_conflicting_package_must_repair_its_overlap(self):
        a, b, upgraded = package('left'), package('right'), package('left', '2')
        result = gate.assess([a, b], [upgraded, b], {r['SHA256']: [file('bin/same')] for r in [a, b, upgraded]})
        self.assertTrue(result['errors'])

    def test_versioned_transfer_requires_matching_target_version(self):
        a, b = package('left', Replaces='right (<< 2)'), package('right')
        self.assertTrue(gate.declared_overlap(a, b))
        self.assertFalse(gate.declared_overlap(a, package('right', '2')))

    def test_ready_stubs_and_foreign_prefixes_block_changed_archives(self):
        a = package('new')
        rows = [file('bin/new', findings=[{'kind': 'confirmed-ready-stub'}]),
                file('lib/new.so', findings=[{'kind': 'foreign-app-prefix', 'offset': 9000000}])]
        self.assertEqual(len(gate.assess([], [a], {'new-1': rows})['errors']), 2)

    def test_vm_bytecode_is_not_misclassified_as_native_elf(self):
        a = package('guile')
        rows = [file('lib/guile/x.go', elf={'machine': 0, 'role': 'guile-vm-bytecode'})]
        self.assertFalse(gate.assess([], [a], {'guile-1': rows})['errors'])


if __name__ == '__main__':
    unittest.main()
