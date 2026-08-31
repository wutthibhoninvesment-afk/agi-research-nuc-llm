#!/usr/bin/env python3
"""Every `self.expect(...)` site in `whence/parser.py`: how it RENDERS the
thing it wanted, and whether it can fail at all.

usage: python3 bench/expectsites.py sites
       python3 bench/expectsites.py sweep  [--corpus a,b,c] [--mutations N]
       python3 bench/expectsites.py report [--corpus a,b,c] [--mutations N]

Round 396. Round 392 deferred "the `expected (` / `expected '{'` quoting
inconsistency" with the numbers *"nine of `parser.py`'s twenty `expect` call
sites pass a quoted `what` and eleven pass the bare token"*. Both numbers
were hand-counted and both are wrong: there are 28 sites, 9 pass a `what`
of which only 2 quote a token, and 19 pass no `what` at all. This file
exists so that no round has to hand-count them again --- `sites` derives the
classification from the AST of the file itself.

The second command is the one that changes the conclusion. A rendering only
matters if an author can SEE it, and `expect` is called on paths where the
caller has already established the token it is about to demand. `sweep`
patches `Parser.expect` to record, per call site, how often it was
EXECUTED and how often it RAISED, then runs a corpus. The three outcomes
are different facts:

  reached      executed and raised          --- a live diagnostic
  never-fails  executed, never raised       --- a DEAD diagnostic: the
                                               guard upstream makes the
                                               token certain
  unexecuted   never reached at all         --- the corpus is too thin, or
                                               the branch is dead

Distinguishing `never-fails` from `unexecuted` is the whole point. Six of
this parser's 28 sites are executed on nearly every parse and have never
once raised, because each sits behind a guard that already tested the
token (`while not self.at(end)` before `expect(end)`; `peek(1).type ==
"NAME"` before `expect("NAME")`; `at("KW", "if")` before
`expect("KW", "if")`). Their wording is unobservable, so normalising it is
not a user-visible change --- and a corpus that merely never reached them
could not tell you that.

`--mutations N` is the honesty clause. "No input in the corpus made site X
fail" is weak; the mutation corpus mechanically deletes and duplicates one
token at a time across every example, which is a much harder search for a
failure, and it is what makes `never-fails` a claim rather than a shrug.
"""
import argparse
import ast
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PARSER_PY = os.path.join(ROOT, "whence", "parser.py")

# The token TYPES that name a CATEGORY of token rather than one spelling,
# DERIVED from the lexer rather than listed: a category is exactly a type
# the lexer emits with a value that is not the type's own name (`NAME`/`x`,
# `EOF`/`None`), where punctuation is emitted as `Token(")", ")")`. Listing
# them by hand here would be a second copy of `parser._CATEGORY_PROSE`'s
# key set, which is the kind of hand-written twin this file exists to
# retire.
def _category_types():
    from whence.lexer import tokenize
    probe = 'let a = 1\nlet s = "t"\nfn f(x) { x }\nlet r = @{k: [a]}\n'
    return frozenset(t.type for t in tokenize(probe) if t.type != t.value)


CATEGORY_TYPES = _category_types()


# --------------------------------------------------------------------------
# sites --- the classification, derived from the AST
# --------------------------------------------------------------------------

class Site(object):
    __slots__ = ("line", "end_line", "type_", "value", "what", "want",
                 "kind", "executed", "raised", "example")

    def __init__(self, line, end_line, type_, value, what):
        self.line, self.end_line = line, end_line
        self.type_, self.value, self.what = type_, value, what
        # Rendered by the PARSER's own `_spell_want` (decision 44), never
        # re-implemented here: a tool that spells the message a second way
        # is a second thing to keep in sync, which is the failure this
        # whole file exists to stop.
        from whence.parser import _spell_want
        self.want = _spell_want(type_, value, what)
        self.kind = classify(type_, value, what)
        self.executed = self.raised = 0
        self.example = None

    @property
    def outcome(self):
        if self.raised:
            return "reached"
        return "never-fails" if self.executed else "unexecuted"


def classify(type_, value, what):
    """The five ways `expect` can name the thing it wanted.

    Round 392 saw two (quoted vs bare). The bare half is really three, and
    the difference matters because the fix differs: a punctuation token
    wants quoting, a CATEGORY name wants prose (`expected 'NAME'` reads as
    a literal the author should type), and a `what` that is already prose
    wants nothing.
    """
    if what is not None:
        return "quoted-token" if str(what).startswith("'") else "bare-prose"
    if value is not None:
        return "bare-keyword"
    return "bare-category" if type_ in CATEGORY_TYPES else "bare-punct"


def _const(node):
    return node.value if isinstance(node, ast.Constant) else "<expr>"


def sites():
    """Every `self.expect(...)` in `whence/parser.py`, in source order."""
    tree = ast.parse(open(PARSER_PY, encoding="utf-8").read())
    out = []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "expect"):
            continue
        pos = [_const(a) for a in n.args]
        kw = {k.arg: _const(k.value) for k in n.keywords}
        out.append(Site(n.lineno, n.end_lineno or n.lineno,
                        pos[0] if pos else kw.get("type_"),
                        pos[1] if len(pos) > 1 else kw.get("value"),
                        kw.get("what")))
    out.sort(key=lambda s: s.line)
    return out


# --------------------------------------------------------------------------
# the corpora
# --------------------------------------------------------------------------

def corpus_differential():
    """`tests/test_parse_error_differential.py`'s own BAD + GOOD lists.

    Imported rather than copied: round 386's lesson that a hand-written
    list beside a derived one is a list that goes stale on one side.
    """
    tests = os.path.join(ROOT, "tests")
    if tests not in sys.path:
        sys.path.insert(0, tests)
    import test_parse_error_differential as d
    return ([("bad:" + n, s) for n, s in d.BAD]
            + [("good:" + n, s) for n, s in d.GOOD])


def corpus_examples():
    ex = os.path.join(ROOT, "examples")
    out = []
    for n in sorted(os.listdir(ex)):
        if n.endswith(".lang"):
            out.append(("ex:" + n,
                        open(os.path.join(ex, n), encoding="utf-8").read()))
    return out


# One input aimed at each site, written by reading the site's guard. Where
# a site is DEAD the input is the closest thing to a trigger that exists,
# and the sweep's job is to show it lands somewhere else.
HANDWRITTEN = [
    ("h:eof-after-block",   "let a = 1\n}"),
    ("h:let-name",          "let = 1"),
    ("h:let-eq",            "let a 1"),
    ("h:fn-name",           "fn 1() { 0 }"),
    ("h:check-label",       "check 1: 1 == 1"),
    ("h:check-colon",       'check "a" 1 == 1'),
    ("h:fn-expr-named",     "let g = fn adder(a, b) { a + b }"),
    ("h:param-name",        "fn f(1) { 0 }"),
    ("h:param-close",       "fn f(a b) { 0 }"),
    ("h:effect-name",       "fn f() effects [1] { 0 }"),
    ("h:effects-close",     "fn f() effects [io io] { 0 }"),
    ("h:shape-name",        "shape 1 = @{a: num}"),
    ("h:shape-eq",          "shape P @{a: num}"),
    ("h:shape-at",          "shape P = {a: num}"),
    ("h:shape-field",       "shape P = @{1: num}"),
    ("h:shape-colon",       "shape P = @{a num}"),
    ("h:shape-close",       "shape P = @{a: num"),
    ("h:block-open",        "let y = if true 1 else 2"),
    ("h:block-close",       "let y = fn() { 1"),
    ("h:call-close",        "let f = fn(x) { x }\nlet v = f(1"),
    ("h:index-close",       "let x = [1,2]\nlet y = x[0"),
    ("h:field-after-dot",   "let r = @{a: 1}\nlet v = r.1"),
    ("h:list-close",        "let x = [1, 2"),
    ("h:record-key",        "let r = @{1: 2}"),
    ("h:record-colon",      "let r = @{a 2}"),
    ("h:record-close",      "let r = @{a: 1"),
    ("h:group-close",       "let x = (1 + 2"),
    ("h:else-alone",        "let y = 1\nelse { 2 }"),
]


def corpus_mutations(n, seed=396):
    """Single-token deletions and duplications over every example.

    The point is not coverage of valid programs --- it is an adversarial
    search for ANY input that makes a `never-fails` site raise. A token
    stream is mutated and re-rendered with one space between tokens, so
    every mutant is still lexable; only the SHAPE is broken.
    """
    from whence.lexer import tokenize, LexError
    rnd = random.Random(seed)
    streams = []
    for name, src in corpus_examples():
        try:
            toks = [t for t in tokenize(src) if t.type not in ("EOF",)]
        except LexError:
            continue
        if len(toks) > 4:
            streams.append((name, toks))
    out = []
    if not streams:
        return out
    for i in range(n):
        name, toks = streams[i % len(streams)]
        j = rnd.randrange(len(toks))
        op = rnd.choice(("delete", "duplicate", "truncate"))
        if op == "delete":
            mut = toks[:j] + toks[j + 1:]
        elif op == "duplicate":
            mut = toks[:j] + [toks[j]] + toks[j:]
        else:
            mut = toks[:j]
        out.append(("mut:%s:%s@%d#%d" % (name, op, j, i), render(mut)))
    return out


def render(toks):
    parts = []
    for t in toks:
        if t.type == "NEWLINE":
            parts.append("\n")
        elif t.type == "STRING":
            parts.append('"%s"' % str(t.value).replace('"', '\\"'))
        else:
            parts.append("%s " % (t.value,))
    return "".join(parts)


CORPORA = {
    "differential": corpus_differential,
    "examples": corpus_examples,
    "handwritten": lambda: list(HANDWRITTEN),
}


def build_corpus(names, mutations):
    out = []
    for n in names:
        if n not in CORPORA:
            raise SystemExit("unknown corpus %r (have %s)"
                             % (n, ",".join(sorted(CORPORA))))
        out.extend(CORPORA[n]())
    if mutations:
        out.extend(corpus_mutations(mutations))
    return out


# --------------------------------------------------------------------------
# sweep --- the instrument
# --------------------------------------------------------------------------

def sweep(all_sites, corpus):
    """Run `corpus` with `Parser.expect` instrumented.

    The call site is recovered from the CALLER's frame line number and
    mapped into the site whose `lineno..end_lineno` range contains it ---
    not by equality, because a call split across lines reports the line
    Python is executing, not the line the AST calls the start.
    """
    from whence.lexer import LexError
    from whence import parser as P

    by_line = {}
    for s in all_sites:
        for ln in range(s.line, s.end_line + 1):
            by_line[ln] = s

    original = P.Parser.expect

    def instrumented(self, type_, value=None, what=None):
        site = by_line.get(sys._getframe(1).f_lineno)
        if site is not None:
            site.executed += 1
        try:
            return original(self, type_, value=value, what=what)
        except P.ParseError as e:
            if site is not None:
                site.raised += 1
                if site.example is None:
                    site.example = str(e)
            raise

    P.Parser.expect = instrumented
    stats = {"programs": 0, "parsed": 0, "parse-error": 0, "lex-error": 0,
             "other": 0}
    try:
        for _name, src in corpus:
            stats["programs"] += 1
            try:
                P.parse(src)
                stats["parsed"] += 1
            except P.ParseError:
                stats["parse-error"] += 1
            except LexError:
                stats["lex-error"] += 1
            except RecursionError:
                stats["other"] += 1
    finally:
        P.Parser.expect = original
    return stats


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def print_sites(all_sites):
    from collections import Counter
    c = Counter(s.kind for s in all_sites)
    print("%d `self.expect(...)` sites in whence/parser.py" % len(all_sites))
    for k in sorted(c):
        print("  %-14s %2d" % (k, c[k]))
    print()
    print("%-6s %-14s %s" % ("line", "class", "renders"))
    for s in all_sites:
        print("%-6d %-14s expected %s" % (s.line, s.kind, s.want))


def print_report(all_sites, stats):
    from collections import Counter
    print("corpus: %(programs)d programs — %(parsed)d parsed, "
          "%(parse-error)d parse-error, %(lex-error)d lex-error, "
          "%(other)d other" % stats)
    print()
    print("%-6s %-14s %-12s %8s %7s  %s"
          % ("line", "class", "outcome", "executed", "raised", "renders"))
    for s in all_sites:
        print("%-6d %-14s %-12s %8d %7d  expected %s"
              % (s.line, s.kind, s.outcome, s.executed, s.raised, s.want))
    print()
    o = Counter(s.outcome for s in all_sites)
    for k in ("reached", "never-fails", "unexecuted"):
        print("  %-12s %2d" % (k, o.get(k, 0)))
    live = [s for s in all_sites if s.outcome == "reached"]
    lc = Counter(s.kind for s in live)
    print()
    print("of the %d LIVE sites, the rendering classes are:" % len(live))
    for k in sorted(lc):
        print("  %-14s %2d" % (k, lc[k]))
    dead = [s for s in all_sites if s.outcome != "reached"]
    if dead:
        print()
        print("DEAD diagnostics (wording unobservable):")
        for s in dead:
            print("  parser.py:%-5d %-14s expected %s"
                  % (s.line, s.kind, s.want))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=("sites", "sweep", "report"))
    ap.add_argument("--corpus", default="differential,examples,handwritten")
    ap.add_argument("--mutations", type=int, default=0,
                    help="N single-token mutants of the examples")
    a = ap.parse_args(argv)

    all_sites = sites()
    if a.command == "sites":
        print_sites(all_sites)
        return 0
    corpus = build_corpus([c for c in a.corpus.split(",") if c], a.mutations)
    stats = sweep(all_sites, corpus)
    if a.command == "sweep":
        for s in all_sites:
            print("%-6d %-12s executed=%-6d raised=%-4d %s"
                  % (s.line, s.outcome, s.executed, s.raised,
                     (s.example or "").split(" at line")[0]))
        return 0
    print_report(all_sites, stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
