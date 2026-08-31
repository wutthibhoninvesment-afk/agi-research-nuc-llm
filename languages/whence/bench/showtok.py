#!/usr/bin/env python3
r"""Token-level parity between `whence/parser.py`'s `_show` and the guest's
`show_tok` (v0.36, round 398, decision 45).

usage: python3 bench/showtok.py corpus
       python3 bench/showtok.py sweep
       python3 bench/showtok.py report

WHY THIS EXISTS, rather than another program-level differential.

`tests/test_parse_error_differential.py` compares 51 whole PROGRAMS and
reads the sentence each side produces. That is the right instrument for
"do the two parsers refuse the same programs in the same place", and it is
the wrong one for "does the guest name a token the way the host does",
because a program-level corpus only reaches the token kinds that happen to
sit at a refusal point. Measured: across all 51 rejected programs the got
slot is filled by exactly FOUR token kinds (EOF, NUMBER, NAME, and
punctuation). The lexer emits eight. A NEWLINE token in the got slot is
reachable in one line of real source --- `let x\nlet y = 1` gives
`expected '=', got '\n'` --- and no program in that corpus reaches it.

So this file compares the RENDERING FUNCTION directly, over every token of
every snippet in a corpus chosen to cover the kinds rather than the
grammar. `sweep` runs the guest library once, asks it to render every
token of every snippet, and lines the answers up against `_show` on the
host's own token stream.

THE TWO KNOWN RESIDUALS, and why they are exemptions and not bugs:

  * a NON-PRINTABLE character inside a string literal. Python `repr`
    writes `\x00`; Whence's escape table (`whence/lexer.py:_ESCAPES`) can
    spell exactly `\n \t \r \" \\` and nothing else, so a guest cannot
    write the character it would have to compare against, let alone
    render it. Same shape as the `\r` hole round 350 closed on the
    lexer, one level down --- and unreachable from source, because a
    literal cannot CONTAIN a byte it cannot spell.
  * an integer past `values.SHOW_INT_BITS` (13287 bits). `str` summarises
    it as `<integer, N bits>` by design (round 368); `repr` does not.
    Reachable only from a 4000+ digit literal.

Both are asserted absent from the corpus by `tests/test_v36.py`, in the
`skills/measured-exemption` discipline: an exemption that is not measured
is a shrug.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

EXAMPLE = os.path.join(ROOT, "examples", "self_eval.lang")
MARKER = "# ==== SELF-TESTS"

# The separator `show_all` joins renderings with. A RAW newline can never
# appear inside one: `_show`/`show_tok` escape it (`'\n'`, four
# characters), and `whence/lexer.py` refuses a raw newline inside a string
# literal, so no token VALUE can carry one either.
SEP = "\n"

# One snippet per token kind and per rendering rule, not per grammar rule.
# `label` is what the snippet is here to reach.
CORPUS = [
    ("keywords-and-names", 'let x = 1\nfn f(y) { y }\n'),
    ("every-one-char-op", 'let a = 1 + 2 - 3 * 4 / 5 % 6\n'
                          'let b = [a][0]\nlet c = @{k: a}.k\n'),
    ("every-two-char-op", 'let a = 1 == 2\nlet b = 1 != 2\nlet c = 1 <= 2\n'
                          'let d = 1 >= 2\nlet e = @{k: 1}\n'
                          'fn f(x) -> num { x }\n'),
    ("comparison-ops", 'let a = 1 < 2\nlet b = 2 > 1\n'),
    ("comma-in-every-construct",
     'let xs = [1, 2]\nfn f(a, b) { a }\nlet r = @{a: 1, b: 2}\n'
     'let v = f(1, 2)\n'),
    ("braces-and-blocks", 'let f = fn() { 1 }\nlet g = if true { 1 } else { 2 }\n'),
    ("newline-token", 'let x = 1\nlet y = 2\n'),
    ("int-literal", 'let a = 0\nlet b = 7\nlet c = 1234567890\n'),
    ("float-literal", 'let a = 1.5\nlet b = 0.25\nlet c = 3.0\n'),
    ("exponent-literal", 'let a = 1e5\nlet b = 2E-3\nlet c = 1e400\n'),
    ("plain-string", 'let s = "hello"\n'),
    ("empty-string", 'let s = ""\n'),
    ("string-with-single-quote", 'let s = "a\'b"\n'),
    ("string-with-double-quote", 'let s = "a\\"b"\n'),
    ("string-with-both-quotes", 'let s = "a\'b\\"c"\n'),
    ("string-with-backslash", 'let s = "a\\\\b"\n'),
    ("string-with-tab", 'let s = "a\\tb"\n'),
    ("string-with-newline-escape", 'let s = "a\\nb"\n'),
    ("string-with-cr-escape", 'let s = "a\\rb"\n'),
    ("string-that-looks-like-a-number", 'let s = "1"\nlet t = "1.5"\n'),
    ("all-keywords", 'let a = true\nlet b = false\nlet c = not a\n'
                     'let d = a and b\nlet e = a or b\n'
                     'let f = a rescue 0\nlet g = why a\nlet h = snip(a)\n'
                     'let i = miss "m"\ncheck "c": 1 == 1\n'),
    ("shape-and-effects", 'shape P = @{x: num}\nfn m(p: P) effects [io] { p.x }\n'),
    ("comment-then-eof", 'let x = 1 # trailing\n'),
    ("no-trailing-newline", 'let x = 1'),
    ("underscore-name", 'let _a1 = 1\n'),
]


def library_source():
    src = open(EXAMPLE, encoding="utf-8").read()
    assert MARKER in src, EXAMPLE
    return src.split(MARKER)[0]


def escape(s):
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r"))


# `show_all` lives HERE and not in the shared parser section: it is a
# harness, not part of the language's reference implementation, and the
# section is pinned byte-identical between the two example files.
PRELUDE = """
fn show_all(ts) { show_all_at(ts, 0, "") }
fn show_all_at(ts, i, acc) {
  if i >= len(ts) { acc }
  else {
    let piece = if i > 0 { "\\n" + show_tok(ts[i]) } else { show_tok(ts[i]) }
    show_all_at(ts, i + 1, acc + piece)
  }
}
"""


def host_shows(src):
    from whence.lexer import tokenize
    from whence.parser import _show
    return [_show(t) for t in tokenize(src)]


def guest_shows(cases, library=None):
    """{name: [rendering, ...]} for the whole corpus, in ONE interpreter run.

    `library` overrides the guest source, which is what lets
    `tests/test_v36.py` plant a divergence and check that this harness
    reports it. A parity sweep that has never been seen to FAIL is a green
    light, not a measurement."""
    from whence.interp import Interpreter
    prog = [library if library is not None else library_source(), PRELUDE]
    for k, (_, s) in enumerate(cases):
        prog.append('let __s%d = show_all(lex_all("%s"))' % (k, escape(s)))
    env = Interpreter().run("\n".join(prog) + "\n")
    out = {}
    for k, (name, _) in enumerate(cases):
        out[name] = env.get("__s%d" % k).payload.split(SEP)
    return out


class Row(object):
    __slots__ = ("name", "index", "kind", "value", "host", "guest")

    def __init__(self, name, index, kind, value, host, guest):
        self.name, self.index, self.kind, self.value = name, index, kind, value
        self.host, self.guest = host, guest

    @property
    def agrees(self):
        return self.host == self.guest

    def __repr__(self):
        return "%s[%d] %s %r: host %s | guest %s" % (
            self.name, self.index, self.kind, self.value, self.host, self.guest)


def sweep(cases=None, library=None):
    """Every token of every snippet, host rendering against guest."""
    from whence.lexer import tokenize
    cases = cases or CORPUS
    g = guest_shows(cases, library)
    rows, misaligned = [], []
    for name, src in cases:
        toks = tokenize(src)
        h = host_shows(src)
        gs = g[name]
        if len(gs) != len(h):
            misaligned.append((name, len(h), len(gs)))
            continue
        for i, t in enumerate(toks):
            rows.append(Row(name, i, t.type, t.value, h[i], gs[i]))
    return rows, misaligned


def report(cases=None, library=None):
    rows, misaligned = sweep(cases, library)
    bad = [r for r in rows if not r.agrees]
    kinds = sorted({r.kind for r in rows})
    print("snippets   : %d" % len(cases or CORPUS))
    print("tokens     : %d" % len(rows))
    print("token kinds: %d  (%s)" % (len(kinds), " ".join(kinds)))
    print("misaligned : %d%s" % (len(misaligned),
                                 "" if not misaligned else " " + repr(misaligned)))
    print("agree      : %d" % (len(rows) - len(bad)))
    print("differ     : %d" % len(bad))
    for r in bad:
        print("  %r" % r)
    return 1 if (bad or misaligned) else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=("corpus", "sweep", "report"))
    args = ap.parse_args(argv)
    if args.command == "corpus":
        for name, src in CORPUS:
            print("%-32s %r" % (name, src))
        return 0
    if args.command == "sweep":
        rows, misaligned = sweep()
        for r in rows:
            print("%s %r" % ("ok " if r.agrees else "DIFF", r))
        for m in misaligned:
            print("MISALIGNED %r" % (m,))
        return 0
    return report()


if __name__ == "__main__":
    sys.exit(main())
