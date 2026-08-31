#!/usr/bin/env python3
"""Every message-normalising regex in `tests/`, and whether it eats a FACT.

Round 404 (v0.38, decision 47). `tests/` normalises incidental junk out of
messages before comparing them — the implementation coordinate `miss`
appends, the `at line L, col C` clause, a pid, a path. Each normaliser is
written against the junk that exists on the day it is written, and then it
is infrastructure and nobody reads it again.

v0.37 shipped the first Whence message to carry a parenthesised line
number as a FACT (`'a' is already bound in this block (line 1); …`) and
v0.38 the second (`shape 'S' is already declared in this block (line 3)`).
Both are the exact shape of the junk. Round 404 found

    LINE_SUFFIX = re.compile(r" \\(line \\d+\\)")

defined SEVEN times across six test files, every copy unanchored and every
copy applied with a global `.sub("", …)` — so each deleted every
parenthesised number in a message, not just the trailing coordinate. One
of them was reached, went red, and named the guest as disagreeing with a
host it agreed with byte for byte. An eighth copy was already `$`-anchored
and had been pinned by a test one round earlier; that pin was about one of
eight.

This is the re-execution of that count. It does not read the round file
and it does not trust a comment: it walks each test module's AST for
`re.compile` calls, recovers the pattern string, and then MEASURES what
each pattern does to messages the live parser actually produces.

    python3 bench/sanitisers.py report   # the table
    python3 bench/sanitisers.py check    # exit 1 if any copy eats a fact

`report` prints the rejects too — a module that fails to parse, or a
`re.compile` whose argument is not a literal, contributes nothing and must
say so rather than quietly shrinking the denominator (round 402's
`bindline.py` pitfall).
"""

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")

#: A pattern is a CANDIDATE normaliser if it could match a parenthesised
#: line number — that is the shape both fact-bearing messages render, and
#: the shape every known copy of the bug matches. Deliberately decided by
#: RUNNING the pattern against the rendered shape, not by comparing
#: pattern source text: two spellings of the same regex are the same
#: hazard and a textual test would see two classes.
_FACT_SHAPE = " (line 7)"


def compiled_patterns(path):
    """[(lineno, name, pattern)] for every `re.compile("<literal>")` in a
    module, plus the rejects. Reads the AST — a grep for `re.compile`
    would also match the ones inside docstrings, and this round's own
    docstrings contain several."""
    src = open(path, encoding="utf-8").read()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [], [("%s: does not parse: %s" % (os.path.basename(path), e))]
    out, rejects = [], []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "compile"
                and getattr(node.func.value, "id", None) == "re"):
            continue
        if not (node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            rejects.append("%s:%d: re.compile with a non-literal pattern"
                           % (os.path.basename(path), node.lineno))
            continue
        out.append((node.lineno, _name_of(tree, node), node.args[0].value))
    return out, rejects


def _name_of(tree, call):
    """The module-level name a `re.compile(...)` is assigned to, or ''."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and node.value is call:
            t = node.targets[0]
            return getattr(t, "id", "")
    return ""


def fact_messages():
    """The messages this language renders that CARRY a parenthesised line
    number as data. Produced by the live parser, not written out here, so
    a round that changes a sentence changes this corpus with it."""
    sys.path.insert(0, ROOT)
    from whence.parser import ParseError, parse
    out = {}
    for label, src in (
            ("v0.37 rebind", "let a = 1\nlet a = 2"),
            ("v0.38 shape",
             "let k = 0\n\nshape S = @{a: num}\nshape S = @{b: num}\nS")):
        try:
            parse(src)
        except ParseError as e:
            # what a GUEST error looks like: the sentence, the position
            # clause, then `miss`'s own raising line, in that order.
            out[label] = str(e) + " (line 997)"
        else:
            raise AssertionError("%s: parsed, but should not have" % label)
    return out


def eats_a_fact(pattern, message):
    """Does `re.sub(pattern, "", message)` remove more than the trailing
    implementation coordinate? Compares against the same pattern anchored,
    which is the intended behaviour in every known case."""
    try:
        got = re.sub(pattern, "", message)
    except re.error:
        return None
    want = re.sub(pattern.rstrip("$") + "$", "", message)
    return got != want


def survey():
    rows, rejects = [], []
    for fname in sorted(os.listdir(TESTS)):
        if not (fname.startswith("test_") and fname.endswith(".py")):
            continue
        pats, rej = compiled_patterns(os.path.join(TESTS, fname))
        rejects.extend(rej)
        for lineno, name, pattern in pats:
            try:
                if not re.search(pattern, _FACT_SHAPE):
                    continue
            except re.error as e:
                rejects.append("%s:%d: bad pattern %r (%s)"
                               % (fname, lineno, pattern, e))
                continue
            rows.append({"file": fname, "line": lineno, "name": name,
                         "pattern": pattern,
                         "anchored": pattern.endswith("$")})
    return rows, rejects


def main(argv):
    mode = argv[1] if len(argv) > 1 else "report"
    rows, rejects = survey()
    facts = fact_messages()
    bad = []
    for r in rows:
        r["eats"] = sorted(label for label, msg in facts.items()
                           if eats_a_fact(r["pattern"], msg))
        if r["eats"]:
            bad.append(r)
    if mode == "report":
        print("fact-bearing messages this language renders:")
        for label, msg in sorted(facts.items()):
            print("  %-14s %s" % (label, msg))
        print("\ncandidate normalisers (patterns that match %r):" % _FACT_SHAPE)
        for r in rows:
            print("  %-40s %-13s anchored=%-5s eats=%s"
                  % ("%s:%d" % (r["file"], r["line"]), r["name"] or "-",
                     r["anchored"], ",".join(r["eats"]) or "-"))
        print("\n%d candidate(s), %d anchored, %d eating a fact"
              % (len(rows), sum(1 for r in rows if r["anchored"]), len(bad)))
        print("%d reject(s)%s" % (len(rejects),
                                  ":" if rejects else ""))
        for rj in rejects:
            print("  " + rj)
        return 0
    if mode == "check":
        for r in bad:
            print("EATS A FACT %s:%d %s pattern=%r -> %s"
                  % (r["file"], r["line"], r["name"], r["pattern"],
                     ",".join(r["eats"])))
        print("sanitisers: %d candidate(s), %d over-matching" % (len(rows), len(bad)))
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
