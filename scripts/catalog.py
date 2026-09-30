#!/usr/bin/env python3
"""Validate and query the versioned Ocean package catalogue."""
import argparse, json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]

def _reject_duplicate_json_keys(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError(f'duplicate JSON key: {key}')
        result[key]=value
    return result

def validate(data):
    """Validate identity, ownership and phase invariants for the whole catalogue."""
    packages=data['packages']; phases=data['phases']
    normalized={}; recipes={}; commands={}; assigned={}
    for name,item in packages.items():
        canonical=name.casefold().replace('_','-')
        if canonical in normalized: raise ValueError(f'duplicate package identity: {normalized[canonical]}/{name}')
        normalized[canonical]=name
        recipe=item.get('recipe','')
        if not recipe.startswith('packages/'): raise ValueError(f'invalid recipe path: {name}')
        if recipe in recipes: raise ValueError(f'duplicate recipe ownership: {recipes[recipe]}/{name}')
        recipes[recipe]=name
        for command in item.get('commands',[]):
            command_key=command.casefold()
            if command_key in commands: raise ValueError(f'duplicate command ownership: {commands[command_key]}/{name}:{command}')
            commands[command_key]=name
    for phase,names in phases.items():
        if len(names)!=len(set(names)): raise ValueError(f'duplicate package in phase {phase}')
        for name in names:
            if name in assigned: raise ValueError(f'package assigned to multiple phases: {name}')
            assigned[name]=phase
            item=packages.get(name)
            if not item or item.get('phase')!=phase: raise ValueError(f'invalid phase mapping: {phase}/{name}')
    missing=set(packages)-set(assigned)
    if missing: raise ValueError(f'unassigned catalogue packages: {",".join(sorted(missing))}')

def load():
    try: data=json.loads((ROOT/'catalog.json').read_text(),object_pairs_hook=_reject_duplicate_json_keys)
    except ValueError as error: raise SystemExit(str(error)) from error
    target=data['target']
    actual=(target['applicationId'],target['architecture'],target['androidApi'],target['prefix'])
    expected=('studio.ocean.app','aarch64',28,'/data/data/studio.ocean.app/files/usr')
    if actual != expected: raise SystemExit(f'catalog target mismatch: {actual!r}')
    try: validate(data)
    except ValueError as error: raise SystemExit(str(error)) from error
    return data
def main():
    parser=argparse.ArgumentParser(); parser.add_argument('command',choices=('validate','roots','table')); parser.add_argument('--through',default='foundation'); args=parser.parse_args()
    data=load(); phases=list(data['phases'])
    if args.through not in phases: raise SystemExit(f'unknown phase: {args.through}')
    names=[name for phase in phases[:phases.index(args.through)+1] for name in data['phases'][phase]]
    if args.command=='roots': print('\n'.join(names))
    elif args.command=='table':
        for name in names:
            item=data['packages'][name]; print(f"{item['phase']}\t{name}\t{item['recipe']}\t{','.join(item.get('commands',[]))}")
    else: print(f"Ocean catalogue valid: {len(data['packages'])} packages, phases={','.join(phases)}")
if __name__=='__main__': main()
