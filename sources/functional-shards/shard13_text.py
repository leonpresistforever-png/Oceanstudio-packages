#!/usr/bin/env python3
from __future__ import annotations
import base64,binascii,collections,difflib,json,math,re,shutil,subprocess,sys,textwrap,unicodedata
from pathlib import Path
from urllib.parse import urlparse

COMMANDS=["unicode-codepoint-info","unicode-normalization","utf8-byte-inspector","utf16-surrogate-pair","ascii-armor-encoder","punycode-idna-decode","regex-pcre2-tester","regex-posix-matcher","regex-dfa-visualizer","word-frequency-counter","character-ngram-gen","token-stopword-filter","porter-stemmer-cli","snowball-stemmer-tool","soundex-phonetic-calc","metaphone-phonetic-cli","levenshtein-distance","jaro-winkler-similarity","hamming-distance-calc","diff-side-by-side","diff-unified-patcher","diff-3way-merge-tool","wdiff-word-differ","markdown-ast-generator","markdown-toc-builder","markdown-table-prettifier","markdown-link-auditor","frontmatter-extractor","latex-math-sanitizer","typst-document-linter","asciidoc-section-view","manpage-troff-linter","groff-formatter-lite","spellcheck-hunspell","aspell-word-filter","syllable-counter-cli","readability-flesch","text-summarizer-lex","line-wrap-hyphenator","column-table-justifier","ansi-color-stripper","ansi-art-renderer","ascii-box-drawing","slugify-text-cli","case-camel-snake-kebab","rot47-cipher-tool","bidi-text-reverser","zero-width-char-chk","line-ending-dos2unix","tab-space-converter"]
STOP=set("a an and are as at be by for from has have he her his i in is it its of on or she that the their them they this to was were will with you your".split())
WORD=re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9_']+",re.UNICODE)
ANSI=re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

def emit(x):
    print(json.dumps(x,indent=2,ensure_ascii=False,default=str) if isinstance(x,(dict,list,tuple)) else x)
def need(a,n=1):
    if len(a)<n:raise SystemExit(f"expected at least {n} arguments")
def textarg(x):
    p=Path(x);return p.read_text(encoding="utf-8",errors="replace") if p.is_file() else x
def words(s):return WORD.findall(s)
def slug(s):
    s=unicodedata.normalize("NFKD",s).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+","-",s).strip("-")
def lev(a,b):
    prev=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        cur=[i]
        for j,y in enumerate(b,1):cur.append(min(cur[-1]+1,prev[j]+1,prev[j-1]+(x!=y)))
        prev=cur
    return prev[-1]
def jaro(a,b):
    if a==b:return 1.0
    if not a or not b:return 0.0
    w=max(0,max(len(a),len(b))//2-1);ma=[False]*len(a);mb=[False]*len(b);m=0
    for i,x in enumerate(a):
        for j in range(max(0,i-w),min(i+w+1,len(b))):
            if not mb[j] and x==b[j]:ma[i]=True;mb[j]=True;m+=1;break
    if not m:return 0.0
    aa=[a[i] for i in range(len(a)) if ma[i]];bb=[b[i] for i in range(len(b)) if mb[i]]
    t=sum(x!=y for x,y in zip(aa,bb))/2
    return (m/len(a)+m/len(b)+(m-t)/m)/3
def jw(a,b):
    j=jaro(a,b);p=0
    for x,y in zip(a,b):
        if x!=y or p==4:break
        p+=1
    return j+.1*p*(1-j)
def soundex(s):
    s=re.sub("[^A-Za-z]","",s).upper()
    if not s:return ""
    mp={**dict.fromkeys("BFPV","1"),**dict.fromkeys("CGJKQSXZ","2"),**dict.fromkeys("DT","3"),"L":"4",**dict.fromkeys("MN","5"),"R":"6"}
    out=[s[0]];last=mp.get(s[0],"")
    for c in s[1:]:
        n=mp.get(c,"")
        if n and n!=last:out.append(n)
        last=n
    return ("".join(out)+"000")[:4]
def metaphone(s):
    w=re.sub("[^A-Za-z]","",s).upper()
    if w[:2] in ("KN","GN","PN","AE","WR"):w=w[1:]
    if w.startswith("X"):w="S"+w[1:]
    out=[];i=0
    while i<len(w):
        c=w[i];p=w[i-1] if i else "";n=w[i+1] if i+1<len(w) else "";n2=w[i+2] if i+2<len(w) else ""
        if c in "AEIOU":
            if i==0:out.append(c)
        elif c=="C":
            if n=="H":out.append("X");i+=1
            else:out.append("S" if n in "IEY" else "K")
        elif c=="D":out.append("J" if n=="G" and n2 in "IEY" else "T")
        elif c=="G":out.append("J" if n in "IEY" else "K")
        elif c in "FJLMNR":out.append(c)
        elif c=="P":out.append("F" if n=="H" else "P")
        elif c=="Q":out.append("K")
        elif c=="S":out.append("X" if n=="H" else "S")
        elif c=="T":out.append("0" if n=="H" else "X" if w[i:i+3] in ("TIA","TIO") else "T")
        elif c=="V":out.append("F")
        elif c=="X":out.extend(("K","S"))
        elif c=="Z":out.append("S")
        elif c in "BK":
            if not out or out[-1]!=c:out.append(c)
        i+=1
    return "".join(out)
def stem(w):
    w=w.lower()
    for suf,rep in [("ational","ate"),("tional","tion"),("ization","ize"),("fulness","ful"),("ousness","ous"),("iveness","ive"),("ingly",""),("edly",""),("ing",""),("ed",""),("ies","y"),("sses","ss"),("s","")]:
        if w.endswith(suf) and len(w)>len(suf)+2:w=w[:-len(suf)]+rep;break
    if w.endswith("e") and len(w)>4:w=w[:-1]
    return w
def mdnodes(s):
    out=[];code=False
    for i,l in enumerate(s.splitlines(),1):
        if l.strip().startswith(chr(96)*3):code=not code;out.append({"type":"fence","line":i});continue
        if code:out.append({"type":"code","line":i,"text":l});continue
        m=re.match(r"^(#{1,6})\s+(.+)$",l)
        if m:out.append({"type":"heading","line":i,"level":len(m.group(1)),"text":m.group(2)});continue
        if re.match(r"^\s*[-*+]\s+",l):out.append({"type":"list_item","line":i,"text":re.sub(r"^\s*[-*+]\s+","",l)});continue
        if l.strip():out.append({"type":"paragraph","line":i,"text":l.strip()})
    return out
def patch(original,diff):
    src=original.splitlines(True);out=[];si=0;ls=diff.splitlines(True);i=0
    while i<len(ls):
        if not ls[i].startswith("@@"):i+=1;continue
        m=re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@",ls[i])
        if not m:raise ValueError("invalid hunk")
        pos=int(m.group(1))-1;out+=src[si:pos];si=pos;i+=1
        while i<len(ls) and not ls[i].startswith("@@"):
            l=ls[i]
            if l.startswith(" "):out.append(src[si]);si+=1
            elif l.startswith("-"):si+=1
            elif l.startswith("+"):out.append(l[1:])
            elif l.startswith("\\"):pass
            else:break
            i+=1
    return "".join(out+src[si:])
def syll(w):
    w=re.sub("[^a-z]","",w.lower())
    if not w:return 0
    n=len(re.findall(r"[aeiouy]+",w))
    if w.endswith("e") and not w.endswith("le") and n>1:n-=1
    return max(1,n)
def sentences(s):return [x.strip() for x in re.split(r"(?<=[.!?])\s+",s.strip()) if x.strip()]
def main(cmd,a):
    if cmd not in COMMANDS:raise SystemExit("unknown command")
    if cmd=="unicode-codepoint-info":need(a);emit([{"char":c,"codepoint":f"U+{ord(c):04X}","name":unicodedata.name(c,"UNASSIGNED"),"category":unicodedata.category(c),"bidi":unicodedata.bidirectional(c)} for c in textarg(a[0])]);return
    if cmd=="unicode-normalization":need(a,2);emit(unicodedata.normalize(a[0].upper(),textarg(a[1])));return
    if cmd=="utf8-byte-inspector":
        need(a);off=0;out=[]
        for c in textarg(a[0]):
            b=c.encode();out.append({"char":c,"offset":off,"hex":b.hex(),"length":len(b)});off+=len(b)
        emit(out);return
    if cmd=="utf16-surrogate-pair":
        need(a);cp=int(a[0],0) if a[0].startswith(("0x","0X")) or a[0].isdigit() else ord(a[0][0]);x=cp-0x10000
        emit({"codepoint":f"U+{cp:04X}","units":[cp]} if cp<=0xffff else {"codepoint":f"U+{cp:06X}","high":0xD800+(x>>10),"low":0xDC00+(x&1023)});return
    if cmd=="ascii-armor-encoder":
        need(a);d=Path(a[0]).read_bytes() if Path(a[0]).is_file() else a[0].encode();lab=a[1] if len(a)>1 else "OCEAN DATA";body="\n".join(textwrap.wrap(base64.b64encode(d).decode(),64));emit(f"-----BEGIN {lab}-----\n{body}\n={binascii.crc32(d)&0xffffffff:08X}\n-----END {lab}");return
    if cmd=="punycode-idna-decode":need(a);emit(a[0].encode("idna").decode() if len(a)>1 and a[1]=="encode" else a[0].encode("ascii").decode("idna"));return
    if cmd in ("regex-pcre2-tester","regex-posix-matcher"):
        need(a,2);p=a[0];s=textarg(a[1])
        if cmd=="regex-pcre2-tester" and shutil.which("pcre2grep") and Path(a[1]).is_file():
            r=subprocess.run(["pcre2grep","-n",p,a[1]],text=True,capture_output=True);emit({"engine":"pcre2grep","matches":r.stdout.splitlines(),"returncode":r.returncode});return
        emit({"engine":"python-re-compatible","matches":[{"span":m.span(),"match":m.group(),"groups":m.groups()} for m in re.finditer(p,s,re.M)]});return
    if cmd=="regex-dfa-visualizer":
        need(a);tok=re.findall(r"\\.|\[[^\]]*\]|\([^)]*\)|\*|\+|\?|\||.",a[0]);print("digraph regex {")
        for i,t in enumerate(tok):print(f"n{i} [label={json.dumps(t)}];")
        for i in range(len(tok)-1):print(f"n{i}->n{i+1};")
        print("}");return
    if cmd=="word-frequency-counter":need(a);c=collections.Counter(x.lower() for x in words(textarg(a[0])));emit(c.most_common(int(a[1]) if len(a)>1 else 100));return
    if cmd=="character-ngram-gen":need(a);s=textarg(a[0]);n=int(a[1]) if len(a)>1 else 3;emit(collections.Counter(s[i:i+n] for i in range(max(0,len(s)-n+1))).most_common());return
    if cmd=="token-stopword-filter":need(a);emit([x for x in words(textarg(a[0])) if x.lower() not in STOP]);return
    if cmd in ("porter-stemmer-cli","snowball-stemmer-tool"):need(a);emit({"engine":"ocean-porter","stems":[stem(x) for x in words(textarg(a[0]))]});return
    if cmd=="soundex-phonetic-calc":need(a);emit(soundex(a[0]));return
    if cmd=="metaphone-phonetic-cli":need(a);emit(metaphone(a[0]));return
    if cmd=="levenshtein-distance":need(a,2);emit(lev(a[0],a[1]));return
    if cmd=="jaro-winkler-similarity":need(a,2);emit(jw(a[0],a[1]));return
    if cmd=="hamming-distance-calc":need(a,2);emit({"distance":sum(x!=y for x,y in zip(a[0],a[1]))+abs(len(a[0])-len(a[1]))});return
    if cmd=="diff-side-by-side":
        need(a,2);A=textarg(a[0]).splitlines();B=textarg(a[1]).splitlines();w=int(a[2]) if len(a)>2 else 50
        for i in range(max(len(A),len(B))):print(f"{(A[i] if i<len(A) else '')[:w]:<{w}} | {(B[i] if i<len(B) else '')[:w]}")
        return
    if cmd=="diff-unified-patcher":need(a,2);r=patch(textarg(a[0]),textarg(a[1]));Path(a[2]).write_text(r) if len(a)>2 else None;emit(r);return
    if cmd=="diff-3way-merge-tool":
        need(a,3);b=textarg(a[0]);o=textarg(a[1]);t=textarg(a[2])
        if o==t:r,conf=o,False
        elif o==b:r,conf=t,False
        elif t==b:r,conf=o,False
        else:r,conf=f"<<<<<<< ours\n{o}\n||||||| base\n{b}\n=======\n{t}\n>>>>>>> theirs\n",True
        emit({"conflict":conf,"merged":r});return
    if cmd=="wdiff-word-differ":
        need(a,2);A=words(textarg(a[0]));B=words(textarg(a[1]));out=[]
        for op,i1,i2,j1,j2 in difflib.SequenceMatcher(a=A,b=B).get_opcodes():
            out+=A[i1:i2] if op=="equal" else (["[-"+" ".join(A[i1:i2])+"-]"] if op=="delete" else ["{+"+" ".join(B[j1:j2])+"+}"] if op=="insert" else ["[-"+" ".join(A[i1:i2])+"-]","{+"+" ".join(B[j1:j2])+"+}"])
        emit(" ".join(out));return
    if cmd=="markdown-ast-generator":need(a);emit(mdnodes(textarg(a[0])));return
    if cmd=="markdown-toc-builder":need(a);emit("\n".join("  "*(n["level"]-1)+f"- [{n['text']}](#{slug(n['text'])})" for n in mdnodes(textarg(a[0])) if n["type"]=="heading"));return
    if cmd=="markdown-table-prettifier":
        need(a);rows=[[c.strip() for c in l.strip().strip("|").split("|")] for l in textarg(a[0]).splitlines() if "|" in l]
        if not rows:emit("");return
        n=max(map(len,rows));w=[max(len(r[i]) if i<len(r) else 0 for r in rows) for i in range(n)];emit("\n".join("| "+" | ".join((r[i] if i<len(r) else "").ljust(w[i]) for i in range(n))+" |" for r in rows));return
    if cmd=="markdown-link-auditor":
        need(a);s=textarg(a[0]);heads={slug(n["text"]) for n in mdnodes(s) if n["type"]=="heading"};out=[]
        for m in re.finditer(r"!?\[([^\]]*)\]\(([^)]+)\)",s):
            t=m.group(2);st="external" if urlparse(t).scheme else "ok"
            if t.startswith("#"):st="ok" if t[1:] in heads else "missing-anchor"
            elif Path(a[0]).is_file() and not urlparse(t).scheme:st="ok" if (Path(a[0]).parent/t.split("#")[0]).exists() else "missing-file"
            out.append({"label":m.group(1),"target":t,"status":st})
        emit(out);return
    if cmd=="frontmatter-extractor":
        need(a);s=textarg(a[0]);ls=s.splitlines();out={"format":None}
        if ls and ls[0].strip() in ("---","+++"):
            mark=ls[0].strip();end=next((i for i in range(1,len(ls)) if ls[i].strip()==mark),None)
            if end is not None:out={"format":"yaml" if mark=="---" else "toml","raw":"\n".join(ls[1:end])}
        emit(out);return
    if cmd in ("latex-math-sanitizer","typst-document-linter"):
        need(a);s=textarg(a[0]);stack=[];pairs={")":"(","]":"[","}":"{"};err=[]
        for i,c in enumerate(s):
            if c in "([{":stack.append((c,i))
            elif c in ")]}":
                if not stack or stack[-1][0]!=pairs[c]:err.append({"offset":i,"error":"unmatched"})
                else:stack.pop()
        if cmd=="latex-math-sanitizer" and len(re.findall(r"(?<!\\)\$",s))%2:err.append({"error":"unbalanced dollar delimiter"})
        emit({"valid":not err and not stack,"errors":err+[{"offset":i,"error":"unclosed"} for c,i in stack]});return
    if cmd=="asciidoc-section-view":need(a);emit([{"line":i,"level":len(m.group(1)),"title":m.group(2)} for i,l in enumerate(textarg(a[0]).splitlines(),1) if (m:=re.match(r"^(=+)\s+(.+)$",l))]);return
    if cmd=="manpage-troff-linter":need(a);s=textarg(a[0]);emit({"macros":[{"line":i,"macro":m.group(1),"args":m.group(2).strip()} for i,l in enumerate(s.splitlines(),1) if (m:=re.match(r"^\.([A-Za-z][A-Za-z0-9]*)\b(.*)",l))]});return
    if cmd=="groff-formatter-lite":
        need(a);out=[]
        for l in textarg(a[0]).splitlines():
            if l.startswith(".SH "):out+=["",l[4:].upper(),""]
            elif l.startswith(".SS "):out+=["",l[4:],""]
            elif l.startswith((".B ",".I ")):out.append(l[3:])
            elif l.startswith(".PP"):out.append("")
            elif not l.startswith("."):out.append(re.sub(r"\\f[BRIP]","",l))
        emit("\n".join(out));return
    if cmd in ("spellcheck-hunspell","aspell-word-filter"):
        need(a);s=textarg(a[0]);D=set()
        if len(a)>1 and Path(a[1]).is_file():
            ls=Path(a[1]).read_text(errors="replace").splitlines();ls=ls[1:] if ls and ls[0].isdigit() else ls;D={x.split("/")[0].strip().lower() for x in ls if x.strip()}
        else:D=STOP|{"ocean","studio","hello","world","python","android","linux","text","file","data","tool","test"}
        miss=sorted({w.lower() for w in words(s) if w.lower() not in D});emit({"engine":"dictionary","misspelled":[{"word":w,"suggestions":difflib.get_close_matches(w,D,n=5,cutoff=.65)} for w in miss]});return
    if cmd=="syllable-counter-cli":need(a);emit([{"word":w,"syllables":syll(w)} for w in words(textarg(a[0]))]);return
    if cmd=="readability-flesch":need(a);s=textarg(a[0]);W=words(s);S=sentences(s);sy=sum(syll(w) for w in W);n=max(1,len(W));sn=max(1,len(S));emit({"reading_ease":206.835-1.015*n/sn-84.6*sy/n,"grade":.39*n/sn+11.8*sy/n-15.59,"words":len(W),"sentences":len(S)});return
    if cmd=="text-summarizer-lex":
        need(a);s=textarg(a[0]);S=sentences(s);f=collections.Counter(w.lower() for w in words(s) if w.lower() not in STOP);scores=[(sum(f[w.lower()] for w in words(x))/max(1,len(words(x))),i,x) for i,x in enumerate(S)];k=int(a[1]) if len(a)>1 else min(3,len(S));emit(" ".join(x[2] for x in sorted(sorted(scores,reverse=True)[:k],key=lambda z:z[1])));return
    if cmd=="line-wrap-hyphenator":need(a);emit(textwrap.fill(textarg(a[0]),width=int(a[1]) if len(a)>1 else 80,break_long_words=True));return
    if cmd=="column-table-justifier":
        need(a);rows=[re.split(r"\s+",l.strip()) for l in textarg(a[0]).splitlines() if l.strip()];n=max((len(r) for r in rows),default=0);w=[max((len(r[i]) if i<len(r) else 0 for r in rows),default=0) for i in range(n)];emit("\n".join("  ".join((r[i] if i<len(r) else "").ljust(w[i]) for i in range(n)).rstrip() for r in rows));return
    if cmd=="ansi-color-stripper":need(a);emit(ANSI.sub("",textarg(a[0])));return
    if cmd=="ansi-art-renderer":need(a);s=textarg(a[0]);c=ANSI.sub("",s);ls=c.splitlines();emit({"width":max(map(len,ls),default=0),"height":len(ls),"rendered":s});return
    if cmd=="ascii-box-drawing":need(a);ls=textarg(a[0]).splitlines() or [""];w=max(map(len,ls));emit("\n".join(["┌"+"─"*(w+2)+"┐"]+["│ "+x.ljust(w)+" │" for x in ls]+["└"+"─"*(w+2)+"┘"]));return
    if cmd=="slugify-text-cli":need(a);emit(slug(textarg(a[0])));return
    if cmd=="case-camel-snake-kebab":need(a);s=re.sub(r"([a-z0-9])([A-Z])",r"\1 \2",textarg(a[0]));p=[x.lower() for x in re.split(r"[^A-Za-z0-9]+",s) if x];emit({"snake":"_".join(p),"kebab":"-".join(p),"camel":(p[0] if p else "")+"".join(x.title() for x in p[1:]),"pascal":"".join(x.title() for x in p)});return
    if cmd=="rot47-cipher-tool":need(a);emit("".join(chr(33+(ord(c)-33+47)%94) if 33<=ord(c)<=126 else c for c in textarg(a[0])));return
    if cmd=="bidi-text-reverser":need(a);s=textarg(a[0]);emit({"logical":s,"reversed":s[::-1],"classes":[{"char":c,"bidi":unicodedata.bidirectional(c)} for c in s]});return
    if cmd=="zero-width-char-chk":need(a);s=textarg(a[0]);emit([{"offset":i,"codepoint":f"U+{ord(c):04X}","name":unicodedata.name(c,"UNASSIGNED")} for i,c in enumerate(s) if unicodedata.category(c)=="Cf"]);return
    if cmd=="line-ending-dos2unix":need(a);p=Path(a[0]);d=p.read_bytes() if p.is_file() else a[0].encode();out=d.replace(b"\r\n",b"\n").replace(b"\r",b"\n");Path(a[1]).write_bytes(out) if len(a)>1 else None;emit({"crlf":d.count(b"\r\n"),"output":out.decode("utf-8","replace")});return
    if cmd=="tab-space-converter":need(a);s=textarg(a[0]);w=int(a[1]) if len(a)>1 else 4;mode=a[2] if len(a)>2 else "expand";emit(s.expandtabs(w) if mode=="expand" else "\n".join(re.sub(r"^( +)",lambda m:"\t"*(len(m.group(1))//w)+" "*(len(m.group(1))%w),l) for l in s.splitlines()));return
    raise SystemExit("implementation missing")

if __name__=="__main__":
    if len(sys.argv)<2:raise SystemExit("usage: runtime COMMAND [args...]")
    try:main(sys.argv[1],sys.argv[2:])
    except (ValueError,OSError,re.error,UnicodeError) as e:raise SystemExit(str(e))
