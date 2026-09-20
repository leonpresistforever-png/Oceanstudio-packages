#!/usr/bin/env python3
import importlib.util,pathlib,subprocess,sys,tempfile
rt=pathlib.Path(sys.argv[1]);sp=importlib.util.spec_from_file_location("r",rt);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
assert len(m.COMMANDS)==50 and len(set(m.COMMANDS))==50
def run(cmd,*args):
    r=subprocess.run([sys.executable,str(rt),cmd,*map(str,args)],text=True,capture_output=True)
    if r.returncode!=0:raise AssertionError((cmd,r.returncode,r.stdout,r.stderr))
    if not r.stdout.strip():raise AssertionError((cmd,"empty output"))
    return r.stdout
with tempfile.TemporaryDirectory() as td:
    d=pathlib.Path(td)
    a=d/"a.txt";a.write_text("Hello world. Ocean Studio builds useful tools.\nSecond line TODO.\n",newline="")
    b=d/"b.txt";b.write_text("Hello brave world. Ocean Studio builds powerful tools.\nSecond line.\n")
    md=d/"doc.md";md.write_text("# Ocean Tools\n\nSee [Section](#section) and [local](a.txt).\n\n## Section\n\n| A | B |\n|---|---|\n| x | longer |\n")
    fm=d/"front.md";fm.write_text("---\ntitle: Ocean\nversion: 1\n---\nBody\n")
    ad=d/"doc.adoc";ad.write_text("= Ocean\n== Section\ntext\n")
    roff=d/"x.1";roff.write_text(".TH OCEAN 1\n.SH NAME\n.B ocean\n.PP\nUseful tool.\n")
    dic=d/"words.dic";dic.write_text("8\nhello\nworld\nocean\nstudio\nuseful\ntools\nsecond\nline\n")
    crlf=d/"crlf.txt";crlf.write_bytes(b"a\r\nb\r\n")
    patch=d/"x.patch";patch.write_text("--- a\n+++ b\n@@ -1,2 +1,2 @@\n-Hello world. Ocean Studio builds useful tools.\n+Hello brave world. Ocean Studio builds powerful tools.\n Second line TODO.\n")
    cases={
      "unicode-codepoint-info":("AΩ",),
      "unicode-normalization":("NFC","Cafe\u0301"),
      "utf8-byte-inspector":("A€",),
      "utf16-surrogate-pair":("0x1F600",),
      "ascii-armor-encoder":("hello","TEST"),
      "punycode-idna-decode":("xn--bcher-kva.de",),
      "regex-pcre2-tester":("(Ocean)\\s+(Studio)",a),
      "regex-posix-matcher":("^Hello",a),
      "regex-dfa-visualizer":("ab+c?",),
      "word-frequency-counter":(a,),
      "character-ngram-gen":("banana","2"),
      "token-stopword-filter":(a,),
      "porter-stemmer-cli":("running studies relational",),
      "snowball-stemmer-tool":("running studies relational",),
      "soundex-phonetic-calc":("Robert",),
      "metaphone-phonetic-cli":("Smith",),
      "levenshtein-distance":("kitten","sitting"),
      "jaro-winkler-similarity":("MARTHA","MARHTA"),
      "hamming-distance-calc":("karolin","kathrin"),
      "diff-side-by-side":(a,b,"40"),
      "diff-unified-patcher":(a,patch,d/"patched.txt"),
      "diff-3way-merge-tool":(a,a,b),
      "wdiff-word-differ":(a,b),
      "markdown-ast-generator":(md,),
      "markdown-toc-builder":(md,),
      "markdown-table-prettifier":("| A | B |\n| x | longer |",),
      "markdown-link-auditor":(md,),
      "frontmatter-extractor":(fm,),
      "latex-math-sanitizer":("$x^{2}+y_{1}$",),
      "typst-document-linter":("= Title\n#let x = (1 + 2)\n",),
      "asciidoc-section-view":(ad,),
      "manpage-troff-linter":(roff,),
      "groff-formatter-lite":(roff,),
      "spellcheck-hunspell":("hello ocean wurld",dic),
      "aspell-word-filter":("hello ocean wurld",dic),
      "syllable-counter-cli":("ocean computer beautiful",),
      "readability-flesch":(a,),
      "text-summarizer-lex":("Cats chase mice. Dogs chase balls. Cats and dogs are animals. Mice are small.","2"),
      "line-wrap-hyphenator":("one two three four five six seven eight nine ten","12"),
      "column-table-justifier":("a bb ccc\nlong x yy",),
      "ansi-color-stripper":("\u001b[31mred\u001b[0m normal",),
      "ansi-art-renderer":("\u001b[31mXX\u001b[0m\nYY",),
      "ascii-box-drawing":("hello\nworld",),
      "slugify-text-cli":("Héllo, Ocean Studio!",),
      "case-camel-snake-kebab":("oceanStudio-tools",),
      "rot47-cipher-tool":("Hello!",),
      "bidi-text-reverser":("abc אבג",),
      "zero-width-char-chk":("a\u200bb",),
      "line-ending-dos2unix":(crlf,d/"lf.txt"),
      "tab-space-converter":("\talpha\n    beta","4","expand"),
    }
    assert set(cases)==set(m.COMMANDS),(set(m.COMMANDS)-set(cases),set(cases)-set(m.COMMANDS))
    for cmd,args in cases.items():run(cmd,*args)
    assert (d/"lf.txt").read_bytes()==b"a\nb\n"
    assert "brave world" in (d/"patched.txt").read_text()
print("SUCCESS: exercised 50/50 shard-13 text/NLP commands")
