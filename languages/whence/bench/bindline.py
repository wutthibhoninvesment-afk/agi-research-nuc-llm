#!/usr/bin/env python3
"""bindline — does a binding statement's NODE line equal its HEAD TOKEN line?

v0.37 (round 402), decision 46. `whence/parser.py`'s `stmt_list` keeps a
`bound` table mapping a name to the line of its FIRST binding, and it fills
that table from the AST node (`bound[name] = s.line`) while it reports the
DUPLICATE's position from the head token it captured before parsing
(`start = self.peek()`).

The guest (`examples/self_eval.lang`) has no AST line field at all. It can
only see the head token. So the guest can reproduce the host's sentence
**if and only if** those two numbers are always the same number.

That is an empirical claim about every `A.Let` / `A.FnDef` / shape-desugar
constructor in a 2400-line parser, and this module measures it instead of
reading the constructors and believing them. It monkeypatches
`Parser.statement` in-process (never on disk), records
`(head_token.line, node.line)` for every binding node the parser builds,
and reports divergences.

`statement()` is called from more places than `stmt_list` — blocks, the
top level, `parse()` — so the sweep covers every construction site, not
just the one the rebind check reads.

Usage:
    python3 bench/bindline.py corpus            # list what will be swept
    python3 bench/bindline.py sweep             # measure, exit 1 on divergence
    python3 bench/bindline.py report            # human summary

Called from `tests/test_v37.py`, which also plants a divergence to prove
the sweep can fail (round 395's item 6: a parity harness that has never
been seen red is a green light, not a measurement).
"""
from __future__ import annotations

import glob
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from whence import ast_nodes as A          # noqa: E402
from whence import parser as P             # noqa: E402


# Snippets that reach binding forms the examples do not: a shape
# declaration (which desugars to `A.Let` through a DIFFERENT constructor),
# a typed `fn`, an effectful `fn`, a `fn` whose parameter list spans lines,
# and a `let` whose VALUE spans lines — the last two are the only shapes
# where a node line and a head-token line could plausibly come apart.
SNIPPETS = [
    ("let-simple", "let a = 1\na"),
    ("let-multiline-value", "let a = (1 +\n  2)\na"),
    ("let-record-multiline", "let a = @{x: 1,\n  y: 2}\na"),
    ("fn-simple", "fn f() { 1 }\nf()"),
    ("fn-typed", "fn f(x: num) -> num { x }\nf(1)"),
    ("fn-params-multiline", "fn f(a,\n  b) { a + b }\nf(1, 2)"),
    ("fn-body-multiline", "fn f(x) {\n  let y = x\n  y\n}\nf(1)"),
    ("shape-decl", "shape S = @{a: num}\nlet v = @{a: 1}\nmatches(v, S)"),
    ("shape-multiline", "shape S = @{a: num,\n  b: num}\nS"),
    ("nested-blocks", "fn f(x) {\n  let a = 1\n  if x > 0 { let a = 2\n a } else { a }\n}\nf(1)"),
    ("let-after-blank", "let a = 1\n\n\nlet b = 2\na + b"),
    ("fn-effects", "fn f(x) effects [io] { x }\nf(1)"),
]


def corpus():
    """Every source this sweep runs the parser over: examples + snippets."""
    out = []
    for path in sorted(glob.glob(os.path.join(_ROOT, "examples", "*.lang"))):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                src = fh.read()
        except OSError:
            continue
        out.append(("example:" + os.path.basename(path), src))
    for name, src in SNIPPETS:
        out.append(("snippet:" + name, src))
    return out


def _records_for(src, statement_impl=None):
    """Parse `src`, returning [(head_line, node_line, name, kind), ...].

    Returns [] if the program does not parse — a rejected program builds no
    binding node worth comparing, and the differential corpus already owns
    the question of WHICH programs are rejected.
    """
    seen = []
    original = P.Parser.statement

    def patched(self):
        tok = self.peek()
        node = (statement_impl or original)(self)
        if isinstance(node, (A.Let, A.FnDef)):
            seen.append((tok.line, node.line, node.name,
                         node.__class__.__name__))
        return node

    P.Parser.statement = patched
    try:
        P.parse(src)
    except Exception:
        return []
    finally:
        P.Parser.statement = original
    return seen


def sweep(statement_impl=None):
    """Measure every source in the corpus.

    `statement_impl` lets a test substitute a deliberately-wrong
    `statement` so the sweep can be observed RED.
    """
    total = 0
    parsed = 0
    divergences = []
    kinds = {}
    for label, src in corpus():
        recs = _records_for(src, statement_impl)
        if recs:
            parsed += 1
        for head_line, node_line, name, kind in recs:
            total += 1
            kinds[kind] = kinds.get(kind, 0) + 1
            if head_line != node_line:
                divergences.append({
                    "source": label, "name": name, "kind": kind,
                    "head_line": head_line, "node_line": node_line,
                })
    return {
        "sources": len(corpus()),
        "sources_parsed": parsed,
        "bindings": total,
        "by_kind": kinds,
        "divergences": divergences,
    }


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "report"
    if cmd == "corpus":
        for label, src in corpus():
            print("%-46s %4d lines" % (label, src.count("\n") + 1))
        return 0
    result = sweep()
    if cmd == "sweep":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("bindline — head-token line vs AST node line, %d binding "
              "statements over %d sources (%d parsed)"
              % (result["bindings"], result["sources"],
                 result["sources_parsed"]))
        for kind, n in sorted(result["by_kind"].items()):
            print("  %-10s %5d" % (kind, n))
        if result["divergences"]:
            print("DIVERGENCES (%d):" % len(result["divergences"]))
            for d in result["divergences"]:
                print("  %(source)s %(name)s: head %(head_line)d != "
                      "node %(node_line)d" % d)
        else:
            print("  0 divergences — the guest can compute the host's "
                  "(line N) from the head token alone")
    return 1 if result["divergences"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
