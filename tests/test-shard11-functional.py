#!/usr/bin/env python3
import importlib.util,tempfile,sys,subprocess
from pathlib import Path
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
r=load(Path(sys.argv[1]),"r");b=load(Path(sys.argv[2]),"b")
names={x[0] for x in b.BATCH2_SHARDS["shard-11-compiler-toolchain-helpers"]["packages"]}
assert set(r.COMMANDS)==names and len(names)==50 and all(callable(r.COMMANDS[x]) for x in names)
with tempfile.TemporaryDirectory() as td:
 p=Path(td);c=p/"x.c";c.write_text("#ifndef X_H\n#define X_H\n#pragma once\n#include <stdio.h>\n#define N 3\nint f(void){return N;}\n#endif\n")
 exe=p/"x.o";subprocess.run(["gcc","-g","-c",str(c),"-o",str(exe)],check=True)
 for cmd in ["elf-section-size-calc","elf-relocation-dumper","elf-dynamic-tags-view","elf-string-table-cat","elf-symbol-versioning","elf-hash-table-chk","nm-undefined-symbols","nm-defined-symbols","strip-debug-symbols","dwarf-line-info-view","dwarf-die-inspector","weak-symbol-finder","hidden-visibility-chk"]:
  r.COMMANDS[cmd]([str(exe)])
 r.COMMANDS["cxx-symbol-demangler"](["_Z3foov"])
 wasm=p/"x.wasm";wasm.write_bytes(b"\0asm\x01\0\0\0")
 for cmd in ["wasm-header-parser","wasm-section-lister","wasm-opcode-disasm","llvm-bitcode-header"]:r.COMMANDS[cmd]([str(wasm)])
 ir=p/"x.ll";ir.write_text("define i32 @f(){ entry:\n %x = add i32 1, 2\n ret i32 %x\n}\n");r.COMMANDS["llvm-ir-instruction-chk"]([str(ir)])
 for cmd in ["include-graph-builder","c-preprocessor-macro","c-token-counter","header-guard-validator","pragma-once-checker"]:r.COMMANDS[cmd]([str(c)])
 r.COMMANDS["static-assert-verify"](["1","+","2","==","3"])
 r.COMMANDS["endian-byte-order-chk"](["0x12345678","4"])
 r.COMMANDS["calling-convention-chk"](["a","b","c","d","e","f","g","h","i"])
 r.COMMANDS["stack-frame-calculator"](["8","24","3"])
 r.COMMANDS["abi-alignment-checker"](["a:1:1","b:8:8","c:2:2"])
 r.COMMANDS["structure-padding-calc"](["a:1:1","b:8:8"])
 cpp=p/"x.hpp";cpp.write_text("struct X { virtual ~X(); virtual void f(); };");r.COMMANDS["vtable-layout-analyzer"]([str(cpp)])
 ld=p/"x.ld";ld.write_text("SECTIONS { .text : { *(.text) } }\n");r.COMMANDS["linker-script-parser"]([str(ld)])
 al=p/"a.c";al.write_text('void target(){} void alias() __attribute__((alias("target")));');r.COMMANDS["symbol-alias-resolver"]([str(al)])
print("PASS: shard11 exact 50-command registry + deterministic functional smoke")
