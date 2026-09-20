#!/usr/bin/env python3
from __future__ import annotations
import ast, json, math, os, re, shlex, subprocess, sys, tokenize, io
from collections import Counter,defaultdict
from pathlib import Path

COMMANDS = [
"cyclomatic-complexity","halstead-metric-calc","lines-of-code-counter","sloccount-lightweight","maintainability-index","cognitive-complexity","dead-code-finder","unreachable-code-chk","cyclomatic-depth-tree","switch-fallthrough-chk","null-pointer-deref-chk","buffer-overflow-pattern","format-string-vuln-chk","integer-overflow-chk","uninitialized-var-chk","memory-leak-pattern","resource-leak-detector","race-condition-pattern","lock-inversion-finder","deadlock-cycle-checker","dep-graph-generator","circular-dep-detector","unused-include-finder","header-dependency-tree","c-symbol-coverage","py-ast-linter-lite","js-ast-syntax-checker","rust-syntax-validator","go-ast-token-scanner","shell-posix-validator","makefile-syntax-linter","cmake-syntax-checker","meson-build-validator","ninja-graph-visualize","pkgconfig-file-linter","api-version-diff-tool","semver-bump-calculator","changelog-linter-tool","license-spdx-checker","license-compatibility","author-attribution-chk","copyright-year-updater","comment-ratio-metric","todo-fixme-collector","magic-number-detector","variable-naming-linter","function-length-linter","nesting-depth-limiter","duplicate-code-clone","refactoring-advisor"
]

CONTROL=re.compile(r'\b(if|for|while|case|catch|except|elif|&&|\|\||\?)\b')
FUNC_RE=re.compile(r'^\s*(?:[\w:*&<>,\[\]\s]+\s+)?([A-Za-z_]\w*)\s*\([^;]*\)\s*\{',re.M)
IDENT=re.compile(r'\b[A-Za-z_]\w*\b')

def text(path): return Path(path).read_text(encoding='utf-8',errors='replace')
def lines(path): return text(path).splitlines()
def emit(x):
    if isinstance(x,(dict,list,tuple)): print(json.dumps(x,indent=2,ensure_ascii=False,default=str))
    else: print(x)
def files(args):
    ps=[]
    for a in args:
        p=Path(a)
        if p.is_dir(): ps += [x for x in p.rglob('*') if x.is_file() and x.stat().st_size < 5_000_000]
        elif p.is_file(): ps.append(p)
    return ps
def need(args,n=1):
    if len(args)<n: raise SystemExit('missing argument(s)')
def source_stats(p):
    ls=lines(p); blank=sum(not x.strip() for x in ls); comments=sum(x.lstrip().startswith(('#','//','/*','*')) for x in ls)
    return {'file':str(p),'physical':len(ls),'blank':blank,'comment':comments,'code':len(ls)-blank-comments}
def complexity(s): return 1+len(CONTROL.findall(s))
def max_nesting(s):
    d=m=0
    for ch in s:
        if ch=='{': d+=1;m=max(m,d)
        elif ch=='}': d=max(0,d-1)
    return m
def patterns(args, pats, label):
    out=[]
    for p in files(args):
        for i,l in enumerate(lines(p),1):
            if any(re.search(x,l) for x in pats): out.append({'file':str(p),'line':i,'kind':label,'text':l.strip()[:240]})
    emit(out); return bool(out)
def imports_for(p):
    s=text(p); out=[]
    if p.suffix=='.py':
        try:
            t=ast.parse(s)
            for n in ast.walk(t):
                if isinstance(n,ast.Import): out += [x.name for x in n.names]
                elif isinstance(n,ast.ImportFrom) and n.module: out.append(n.module)
        except SyntaxError: pass
    else:
        out += re.findall(r'^\s*#include\s*[<"]([^>"]+)',s,re.M)
        out += re.findall(r'\b(?:import|require)\s*(?:\(|)\s*["\']([^"\']+)',s)
    return out
def graph(args):
    g={}
    for p in files(args): g[str(p)]=imports_for(p)
    return g
def cycles(g):
    found=[]; temp=set(); perm=set()
    def visit(n,stack):
        if n in temp:
            i=stack.index(n); found.append(stack[i:]+[n]); return
        if n in perm:return
        temp.add(n); stack.append(n)
        for m in g.get(n,[]):
            if m in g: visit(m,stack)
        stack.pop();temp.remove(n);perm.add(n)
    for n in g: visit(n,[])
    return found

def main(cmd,args):
    if cmd in ('-h','--help'): emit('Ocean shard-18 functional static-analysis runtime'); return 0
    if cmd in ('-v','--version'): emit('1.0.0-2'); return 0
    if cmd not in COMMANDS: raise SystemExit('unknown command')
    if cmd=='lines-of-code-counter':
        need(args); emit([source_stats(p) for p in files(args)]); return 0
    if cmd=='sloccount-lightweight':
        need(args); ss=[source_stats(p) for p in files(args)]; total=sum(x['code'] for x in ss); emit({'files':len(ss),'sloc':total,'estimated_person_months':round((total/1000)**1.05*2.4,3) if total else 0}); return 0
    if cmd=='cyclomatic-complexity':
        need(args); emit([{'file':str(p),'complexity':complexity(text(p))} for p in files(args)]); return 0
    if cmd=='halstead-metric-calc':
        need(args); out=[]
        ops=re.compile(r'==|!=|<=|>=|\+\+|--|&&|\|\||[-+*/%=<>!&|^~?:]')
        for p in files(args):
            s=text(p); o=ops.findall(s); ids=IDENT.findall(s); n1,n2=len(set(o)),len(set(ids)); N1,N2=len(o),len(ids); vocab=n1+n2; length=N1+N2; volume=length*math.log2(vocab) if vocab else 0
            out.append({'file':str(p),'distinct_operators':n1,'distinct_operands':n2,'operators':N1,'operands':N2,'volume':round(volume,2)})
        emit(out); return 0
    if cmd=='maintainability-index':
        need(args); out=[]
        for p in files(args):
            s=text(p); loc=max(1,len(s.splitlines())); cc=complexity(s); toks=max(1,len(IDENT.findall(s))); vol=toks*math.log2(max(2,len(set(IDENT.findall(s))))); mi=max(0,(171-5.2*math.log(max(vol,1))-0.23*cc-16.2*math.log(loc))*100/171); out.append({'file':str(p),'mi':round(mi,2),'loc':loc,'complexity':cc})
        emit(out); return 0
    if cmd in ('cognitive-complexity','cyclomatic-depth-tree','nesting-depth-limiter'):
        need(args); threshold=int(args[-1]) if cmd=='nesting-depth-limiter' and args[-1].isdigit() else 5; ps=files(args[:-1] if cmd=='nesting-depth-limiter' and args[-1].isdigit() else args); r=[{'file':str(p),'max_brace_depth':max_nesting(text(p)),'control_points':len(CONTROL.findall(text(p)))} for p in ps]; emit([x for x in r if x['max_brace_depth']>threshold] if cmd=='nesting-depth-limiter' else r); return 0
    if cmd=='py-ast-linter-lite':
        need(args); out=[]
        for p in files(args):
            try:
                t=ast.parse(text(p),filename=str(p)); bad=[]
                for n in ast.walk(t):
                    if isinstance(n,(ast.Exec if hasattr(ast,'Exec') else ast.Expr,)): pass
                    if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ('eval','exec'): bad.append({'line':n.lineno,'warning':n.func.id})
                out.append({'file':str(p),'valid':True,'warnings':bad})
            except SyntaxError as e: out.append({'file':str(p),'valid':False,'line':e.lineno,'error':e.msg})
        emit(out); return 0
    if cmd=='shell-posix-validator':
        need(args); return 1 if patterns(args,[r'\[\[',r'\bfunction\s+\w+',r'\$\{!\w+',r'\bsource\s+'], 'bashism') else 0
    if cmd=='makefile-syntax-linter':
        need(args); out=[]
        for p in files(args):
            for i,l in enumerate(lines(p),1):
                if re.match(r' +\S',l) and i>1 and lines(p)[i-2].rstrip().endswith(':'): out.append({'file':str(p),'line':i,'warning':'recipe should begin with TAB'})
        emit(out); return bool(out)
    if cmd in ('js-ast-syntax-checker','rust-syntax-validator','go-ast-token-scanner','cmake-syntax-checker','meson-build-validator'):
        need(args); out=[]
        for p in files(args):
            s=text(p); stack=[]; pairs={')':'(',']':'[','}':'{'}; err=[]
            for i,ch in enumerate(s):
                if ch in '([{':stack.append(ch)
                elif ch in ')]}':
                    if not stack or stack.pop()!=pairs[ch]:err.append({'offset':i,'error':'unbalanced delimiter'});break
            if stack:err.append({'error':'unclosed delimiter','count':len(stack)})
            if cmd=='go-ast-token-scanner': out.append({'file':str(p),'package':(re.search(r'^\s*package\s+(\w+)',s,re.M) or [None,None])[1],'imports':re.findall(r'^\s*"([^"]+)"',s,re.M),'errors':err})
            else: out.append({'file':str(p),'valid':not err,'errors':err})
        emit(out); return 0
    if cmd in ('dep-graph-generator','header-dependency-tree'):
        need(args); g=graph(args)
        if cmd=='dep-graph-generator':
            print('digraph dependencies {')
            for a,bs in g.items():
                for b in bs: print(f'  {json.dumps(a)} -> {json.dumps(b)};')
            print('}')
        else: emit(g)
        return 0
    if cmd=='circular-dep-detector': need(args); emit(cycles(graph(args))); return 0
    if cmd=='unused-include-finder':
        need(args); out=[]
        for p in files(args):
            s=text(p)
            for h in re.findall(r'^\s*#include\s*[<"]([^>"]+)',s,re.M):
                stem=Path(h).stem
                if stem not in s[s.find(h)+len(h):]: out.append({'file':str(p),'include':h,'heuristic':'possibly-unused'})
        emit(out); return 0
    if cmd=='c-symbol-coverage':
        need(args,2); decl=set(re.findall(r'\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*;',text(args[0]))); defs=set(FUNC_RE.findall(text(args[1]))); emit({'declared_not_defined':sorted(decl-defs),'defined_not_declared':sorted(defs-decl)}); return 0
    if cmd=='ninja-graph-visualize':
        need(args); s=text(args[0]); print('digraph ninja {')
        for outs,ins in re.findall(r'^build\s+([^:]+):\s+\S+\s*(.*)$',s,re.M):
            for o in outs.split():
                for i in ins.split(): print(f'  {json.dumps(i)} -> {json.dumps(o)};')
        print('}'); return 0
    if cmd=='pkgconfig-file-linter':
        need(args); req={'Name','Description','Version'}; out=[]
        for p in files(args):
            keys={m.group(1) for m in re.finditer(r'^([A-Za-z][\w.]+):',text(p),re.M)}; out.append({'file':str(p),'missing':sorted(req-keys)})
        emit(out); return 0
    if cmd=='api-version-diff-tool':
        need(args,2); a={x.strip() for x in lines(args[0]) if x.strip()}; b={x.strip() for x in lines(args[1]) if x.strip()}; emit({'added':sorted(b-a),'removed':sorted(a-b)}); return 0
    if cmd=='semver-bump-calculator':
        need(args); removed=int(args[0]); added=int(args[1]) if len(args)>1 else 0; emit('major' if removed else 'minor' if added else 'patch'); return 0
    if cmd=='changelog-linter-tool':
        need(args); s=text(args[0]); warnings=[]; 
        if '# Changelog' not in s: warnings.append('missing # Changelog')
        if '## [Unreleased]' not in s: warnings.append('missing [Unreleased]')
        emit({'valid':not warnings,'warnings':warnings}); return bool(warnings)
    if cmd=='license-spdx-checker':
        need(args); allowed=re.compile(r'^[A-Za-z0-9.+-]+(?:\s+(?:AND|OR|WITH)\s+[A-Za-z0-9.+-]+)*$'); expr=' '.join(args); emit({'valid':bool(allowed.fullmatch(expr)),'expression':expr}); return 0
    if cmd=='license-compatibility':
        need(args,2); copyleft={'GPL-2.0','GPL-3.0','AGPL-3.0'}; emit({'a':args[0],'b':args[1],'note':'review-required' if (args[0] in copyleft)!=(args[1] in copyleft) else 'same-license-family-risk-low'}); return 0
    if cmd=='author-attribution-chk':
        need(args); r=subprocess.run(['git','-C',args[0],'log','--format=%an%x09%ae'],capture_output=True,text=True); bad=[x for x in r.stdout.splitlines() if not re.search(r'\t[^@\s]+@[^@\s]+\.[^@\s]+$',x)]; emit({'valid':not bad,'invalid':bad}); return bool(bad)
    if cmd=='copyright-year-updater':
        need(args); year=str(__import__('datetime').datetime.now().year); out=[]
        for p in files(args):
            for i,l in enumerate(lines(p),1):
                if re.search(r'copyright',l,re.I) and not re.search(rf'\b{year}\b',l): out.append({'file':str(p),'line':i,'current_year_missing':year,'text':l.strip()})
        emit(out); return 0
    if cmd=='comment-ratio-metric':
        need(args); ss=[source_stats(p) for p in files(args)]; emit([dict(x,comment_ratio=round(x['comment']/max(1,x['code']+x['comment']),4)) for x in ss]); return 0
    if cmd=='todo-fixme-collector': need(args); return 1 if patterns(args,[r'\b(?:TODO|FIXME|HACK|XXX)\b'],'annotation') else 0
    if cmd=='magic-number-detector': need(args); return 1 if patterns(args,[r'(?<![\w.])(?:[2-9]|\d{2,})(?:\.\d+)?(?![\w.])'],'magic-number') else 0
    if cmd=='variable-naming-linter':
        need(args); out=[]
        for p in files(args):
            ids=Counter(IDENT.findall(text(p)))
            for n,c in ids.items():
                if len(n)>1 and not re.fullmatch(r'[a-z_][a-z0-9_]*|[A-Z][A-Za-z0-9]*|[A-Z][A-Z0-9_]*',n): out.append({'file':str(p),'identifier':n,'count':c})
        emit(out[:500]); return 0
    if cmd=='function-length-linter':
        need(args); threshold=int(args[-1]) if args[-1].isdigit() else 60; ps=files(args[:-1] if args[-1].isdigit() else args); out=[]
        for p in ps:
            ls=lines(p)
            for m in FUNC_RE.finditer(text(p)):
                start=text(p)[:m.start()].count('\n')+1; depth=0; end=start
                for j in range(start-1,len(ls)):
                    depth+=ls[j].count('{')-ls[j].count('}'); end=j+1
                    if j>=start and depth<=0:break
                if end-start+1>threshold: out.append({'file':str(p),'function':m.group(1),'start':start,'lines':end-start+1})
        emit(out); return 0
    if cmd=='duplicate-code-clone':
        need(args); win=int(args[-1]) if args[-1].isdigit() else 6; ps=files(args[:-1] if args[-1].isdigit() else args); seen={}; out=[]
        for p in ps:
            ls=[re.sub(r'\s+',' ',x.strip()) for x in lines(p) if x.strip()]
            for i in range(max(0,len(ls)-win+1)):
                k='\n'.join(ls[i:i+win])
                if k in seen: out.append({'first':seen[k],'duplicate':f'{p}:{i+1}'})
                else: seen[k]=f'{p}:{i+1}'
        emit(out[:500]); return 0
    if cmd=='refactoring-advisor':
        need(args); out=[]
        for p in files(args):
            s=text(p); st=source_stats(p); advice=[]
            if complexity(s)>20: advice.append('split high-complexity control flow')
            if max_nesting(s)>5: advice.append('reduce nesting with guard clauses/extraction')
            if st['code']>500: advice.append('consider splitting large module')
            if re.search(r'\b(?:TODO|FIXME)\b',s): advice.append('resolve tracked TODO/FIXME debt')
            out.append({'file':str(p),'advice':advice})
        emit(out); return 0
    heuristic={
      'dead-code-finder':[r'\b(?:unused|dead_code)\b'],
      'unreachable-code-chk':[r'\b(?:return|break|continue|throw)\b.*;\s*\S+'],
      'switch-fallthrough-chk':[r'\bcase\b[^:]*:'],
      'null-pointer-deref-chk':[r'\bNULL\s*->|\bnullptr\s*->'],
      'buffer-overflow-pattern':[r'\b(?:strcpy|strcat|gets|sprintf)\s*\('],
      'format-string-vuln-chk':[r'\bprintf\s*\(\s*[A-Za-z_]\w*\s*\)'],
      'integer-overflow-chk':[r'\b(?:int|long)\s+\w+.*[+*].*\w+'],
      'uninitialized-var-chk':[r'\b(?:int|char|long|float|double)\s+\w+\s*;'],
      'memory-leak-pattern':[r'\b(?:malloc|calloc|realloc)\s*\('],
      'resource-leak-detector':[r'\b(?:open|fopen|socket)\s*\('],
      'race-condition-pattern':[r'\b(?:pthread_create|std::thread|Thread)\b'],
      'lock-inversion-finder':[r'\b(?:lock|mutex_lock)\s*\('],
      'deadlock-cycle-checker':[r'\b(?:lock|mutex_lock)\s*\('],
    }
    if cmd in heuristic: need(args); return 1 if patterns(args,heuristic[cmd],cmd) else 0
    raise SystemExit('command implementation missing')

if __name__=='__main__':
    if len(sys.argv)<2: raise SystemExit('usage: runtime COMMAND [args...]')
    raise SystemExit(main(sys.argv[1],sys.argv[2:]) or 0)
