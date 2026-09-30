#!/usr/bin/env python3
import importlib.util, json, pathlib, subprocess, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[2]
subprocess.run(['python3',str(ROOT/'ocean-packages/scripts/catalog.py'),'validate'],check=True)
roots=subprocess.check_output(['python3',str(ROOT/'ocean-packages/scripts/catalog.py'),'roots','--through','foundation'],text=True).splitlines()
assert roots[:3]==['bash','apt','libcurl']
assert {'coreutils','findutils','wget','openssl','util-linux'} <= set(roots)
assert 'python' not in roots and 'nodejs' not in roots
spec=importlib.util.spec_from_file_location('ocean_catalog',ROOT/'ocean-packages/scripts/catalog.py')
catalog=importlib.util.module_from_spec(spec); spec.loader.exec_module(catalog)
data=catalog.load()
for mutation, expected in (
    (lambda value: value['packages'].__setitem__('BASH',dict(value['packages']['bash'],recipe='packages/bash-copy')), 'duplicate package identity'),
    (lambda value: value['packages']['grep'].__setitem__('commands',['ls']), 'duplicate command ownership'),
    (lambda value: value['phases']['foundation'].append('bash'), 'package assigned to multiple phases'),
):
    candidate=json.loads(json.dumps(data)); mutation(candidate)
    try: catalog.validate(candidate)
    except ValueError as error: assert expected in str(error), error
    else: raise AssertionError(f'catalog accepted {expected}')
print('Ocean package catalogue tests passed.')
