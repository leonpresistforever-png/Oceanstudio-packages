#!/usr/bin/env python3
import importlib.util, pathlib, subprocess, sys, tempfile, json
runtime=pathlib.Path(sys.argv[1]); spec=importlib.util.spec_from_file_location("r",runtime); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
assert len(m.COMMANDS)==50 and len(set(m.COMMANDS))==50
def run(cmd,*args,input=None):
    r=subprocess.run([sys.executable,str(runtime),cmd,*map(str,args)],input=input,text=True,capture_output=True)
    if r.returncode not in (0,1): raise AssertionError((cmd,r.returncode,r.stdout,r.stderr))
    return r
with tempfile.TemporaryDirectory() as td:
    d=pathlib.Path(td); py=d/"a.py"; py.write_text("def f(x):\n    # TODO fix\n    if x:\n        return 42\n    return 0\n")
    c=d/"a.c"; c.write_text('#include <stdio.h>\nint f(char *x){ char b[8]; strcpy(b,x); printf(x); return 7; }\n')
    mk=d/"Makefile"; mk.write_text("all:\n    echo bad\n")
    pc=d/"x.pc"; pc.write_text("Name: x\nVersion: 1\n")
    api1=d/"old.txt"; api1.write_text("a\nb\n"); api2=d/"new.txt"; api2.write_text("b\nc\n")
    tests={
      "cyclomatic-complexity":(py,), "halstead-metric-calc":(py,), "lines-of-code-counter":(py,), "sloccount-lightweight":(d,),
      "maintainability-index":(py,), "cognitive-complexity":(py,), "dead-code-finder":(py,), "unreachable-code-chk":(py,),
      "cyclomatic-depth-tree":(py,), "switch-fallthrough-chk":(c,), "null-pointer-deref-chk":(c,), "buffer-overflow-pattern":(c,),
      "format-string-vuln-chk":(c,), "integer-overflow-chk":(c,), "uninitialized-var-chk":(c,), "memory-leak-pattern":(c,),
      "resource-leak-detector":(c,), "race-condition-pattern":(c,), "lock-inversion-finder":(c,), "deadlock-cycle-checker":(c,),
      "dep-graph-generator":(d,), "circular-dep-detector":(d,), "unused-include-finder":(c,), "header-dependency-tree":(d,),
      "c-symbol-coverage":(c,c), "py-ast-linter-lite":(py,), "js-ast-syntax-checker":(py,), "rust-syntax-validator":(c,),
      "go-ast-token-scanner":(c,), "shell-posix-validator":(py,), "makefile-syntax-linter":(mk,), "cmake-syntax-checker":(c,),
      "meson-build-validator":(c,), "ninja-graph-visualize":(mk,), "pkgconfig-file-linter":(pc,), "api-version-diff-tool":(api1,api2),
      "semver-bump-calculator":("1","1"), "changelog-linter-tool":(py,), "license-spdx-checker":("MIT",), "license-compatibility":("MIT","Apache-2.0"),
      "author-attribution-chk":(d,), "copyright-year-updater":(py,), "comment-ratio-metric":(py,), "todo-fixme-collector":(py,),
      "magic-number-detector":(py,), "variable-naming-linter":(py,), "function-length-linter":(c,), "nesting-depth-limiter":(c,),
      "duplicate-code-clone":(d,), "refactoring-advisor":(py,)
    }
    assert set(tests)==set(m.COMMANDS)
    for cmd,args in tests.items(): run(cmd,*args)
print("SUCCESS: exercised 50/50 shard-18 functional commands")
