"""Whence v0.28 (round 372, language C) — decision 36: the MISS-MESSAGE
surface, host vs host, and host vs guest.

Round 362 (v0.25) asked whether the host and `examples/self_eval.lang` word
a CONTRACT miss identically. Its `TYPE_FNS` names five functions
(`_check_contract`, `b_typed`, `b_sure`, `b_get`, `_field`) and its own
coverage assertion is `len(declared) >= 12`. An AST census of the same file
finds **126** `mk_miss`/`merge_miss`/`_propagate` sites in **46** enclosing
functions, so 41 of those functions — the arithmetic, the operators, the
call path, the size budgets, 30 of the 36 builtins — had never had their
wording compared with anything.

THIS FILE ASKS TWO QUESTIONS OVER THE WHOLE SURFACE.

  1. HOST vs HOST. Whence has three evaluation engines (`direct` /
     `direct=False` / `fast=False`) and the call guards are QUADRUPLICATED:
     `_builtin_inline`, `_closure_inline`, `_call_direct` and `_call_gen`
     each carry their own copy of "N expects M args", "recursion too deep",
     "tail loop too long" and "is not callable". Nothing compared the
     sentences those copies produce. The answer is that they agree — see
     `test_the_three_engines_word_every_miss_identically`, which is a
     PIN on a negative result, not a discovery. `oracles.oracle_fast_slow`
     / `oracle_direct` already covered this incidentally, because
     `behaviour_ex`'s `vals` renders a Miss through `full_show` and that
     includes its reasons; this file makes the coverage deliberate and
     site-keyed rather than incidental and program-keyed.

  2. HOST vs GUEST. 114 cases, one per reachable site (greedy set cover
     over the instrumented census, across all three engines). Before this
     round 86 of 114 agreed. v0.28's fixes take it to 103, and every one
     of the remaining 11 belongs to one of THREE named exemptions, each
     asserted load-bearing in both directions.

WHY THE CORPUS IS SITE-KEYED. A message-keyed or case-keyed corpus measures
enthusiasm, not coverage: one generic site absorbs a dozen cases and looks
like a dozen. `declared_sites()` reads the sites off the AST and
`observed_sites()` captures the ones the corpus reaches by wrapping the two
miss constructors — the same rule `skills/refusal-set-differential` states
and round 362 applied to its five functions.

WHAT SITE-KEYING DOES **NOT** MEASURE, discovered while building this file:
one host site can be reached by cases the GUEST words differently from each
other. The greedy cover kept one representative for `binop`'s `==` guard,
and it happened to be an operand for which the guest agreed; a different
operand for the SAME site disagreed (the guest said "cannot compare
functions" where the host said "cannot compare functions with =="). Site
coverage bounds the host side and only samples the guest side. `EXTRA` below
holds the cases that exist for that reason.

Cost: the guest side is ONE interpreter run for the whole corpus (round
362's trick). It is still ~40 s, so every fixture that touches the guest or
sweeps three engines is `whence_slow`; the AST census and the corpus's own
well-formedness stay in the fast tier.
"""

import ast
import os
import sys

import pytest

from whence.interp import Interpreter
from whence.lexer import LexError
from whence.parser import ParseError
from whence.values import Miss

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERP_PY = os.path.join(ROOT, "whence", "interp.py")
EXAMPLE = os.path.join(ROOT, "examples", "self_eval.lang")
MARKER = "# ==== SELF-TESTS"

# The guest's trailing `(line N)` is a line in `self_eval.lang`, the host's a
# line in the program. Both are stripped; `test_parse_error_differential.py`
# owns positions and `test_v24` owns lines.
import re
LINE_SUFFIX = re.compile(r" \(line \d+\)")

# `_propagate` is shared machinery: a miss it builds is attributed to the
# function that CALLED it, exactly as in test_contract_message_differential.
MACHINERY = {"_propagate"}

MODES = (("direct", {}), ("fast", {"direct": False}), ("slow", {"fast": False}))

CORPUS = [
    ('"abc" + 1',
     'let r = "abc" + 1\n'),
    ('("")[-1]',
     'let r = ("")[-1]\n'),
    ('("abc")[[1, 2]]',
     'let r = ("abc")[[1, 2]]\n'),
    ('((1 / 0)).a',
     'let r = ((1 / 0)).a\n'),
    ('(1 / 0) and (1 / 0)',
     'let r = (1 / 0) and (1 / 0)\n'),
    ('(@{})[@{a: 1}]',
     'let r = (@{})[@{a: 1}]\n'),
    ('([1, 2])["abc"]',
     'let r = ([1, 2])["abc"]\n'),
    ('([1, 2])[(1 / 0)]',
     'let r = ([1, 2])[(1 / 0)]\n'),
    ('([])[1]',
     'let r = ([])[1]\n'),
    ('(len)()',
     'let r = (len)()\n'),
    ('(true).a',
     'let r = (true).a\n'),
    ('- (1 / 0)',
     'let r = - (1 / 0)\n'),
    ('- @{}',
     'let r = - @{}\n'),
    ('0 / why 1',
     'let r = 0 / why 1\n'),
    ('3^2048 + 0.5',
     'fn p(n, a) { if n == 0 { a } else { p(n - 1, a * a) } }\nlet r = p(11, 3) + 0.5\n'),
    ('@{} == why 1',
     'let r = @{} == why 1\n'),
    ('[] and [1, 2]',
     'let r = [] and [1, 2]\n'),
    ('abs((1 / 0))',
     'let r = abs((1 / 0))\n'),
    ('abs(true)',
     'let r = abs(true)\n'),
    ('at((1 / 0), "abc")',
     'let r = at((1 / 0), "abc")\n'),
    ('at((1 / 0), fn(a) { a })',
     'let r = at((1 / 0), fn(a) { a })\n'),
    ('at(0, (1 / 0))',
     'let r = at(0, (1 / 0))\n'),
    ('closure_inline depth',
     'fn h(a) { a + 1 }\nfn f(n) { if n == 0 { map(h, [1]) } else { f(n - 1) + 0 } }\nlet r = f(3)\n'),
    ('confidence((1 / 0))',
     'let r = confidence((1 / 0))\n'),
    ('confidence(1)',
     'let r = confidence(1)\n'),
    ('contains((1 / 0), (1 / 0))',
     'let r = contains((1 / 0), (1 / 0))\n'),
    ('contains(guess(1, 0.5, "s"), 1)',
     'let r = contains(guess(1, 0.5, "s"), 1)\n'),
    ('contrast((1 / 0))',
     'let r = contrast((1 / 0))\n'),
    ('contrast(@{a: 1})',
     'let r = contrast(@{a: 1})\n'),
    ('deep@max_depth',
     'fn g(n) { if n == 0 { 0 } else { 1 + g(n - 1) } }\nlet r = g(50)\n'),
    ('diverge((1 / 0))',
     'let r = diverge((1 / 0))\n'),
    ('diverge(guess(1, 0.5, "s"))',
     'let r = diverge(guess(1, 0.5, "s"))\n'),
    ('filter((1 / 0), "")',
     'let r = filter((1 / 0), "")\n'),
    ('filter(1, [1, 2])',
     'let r = filter(1, [1, 2])\n'),
    ('filter(fn(a) { a }, 0)',
     'let r = filter(fn(a) { a }, 0)\n'),
    ('filter(fn(a) { a }, [1, 2])',
     'let r = filter(fn(a) { a }, [1, 2])\n'),
    ('filter(len, [1, 2])',
     'let r = filter(len, [1, 2])\n'),
    ('find((1 / 0), -1)',
     'let r = find((1 / 0), -1)\n'),
    ('find([1, 2], [])',
     'let r = find([1, 2], [])\n'),
    ('find(fn(a) { a }, [1, 2])',
     'let r = find(fn(a) { a }, [1, 2])\n'),
    ('find(true, fn(a) { a })',
     'let r = find(true, fn(a) { a })\n'),
    ('find(why 1, [1, 2])',
     'let r = find(why 1, [1, 2])\n'),
    ('fn a(n) { b(n) }; fn b(n) { a(n, 1) }; let r = a(1)',
     'fn a(n) { b(n) }\nfn b(n) { a(n, 1) }\nlet r = a(1)\n'),
    ('fn d(n, s) { if n == 0 { s } else { d(n - 1, s + s) } }; let r = d(40,',
     'fn d(n, s) { if n == 0 { s } else { d(n - 1, s + s) } }\nlet r = d(40, "ab")\n'),
    ('fn g(a) { a }; let r = g(1, 2)',
     'fn g(a) { a }\nlet r = g(1, 2)\n'),
    ('fn g(n) { if n == 0 { 0 } else { 1 + g(n - 1) } }; let r = g(100000)',
     'fn g(n) { if n == 0 { 0 } else { 1 + g(n - 1) } }\nlet r = g(100000)\n'),
    ('fn g(n) { if n == 0 { 0 } else { g(n - 1) } }; let r = g(3000000)',
     'fn g(n) { if n == 0 { 0 } else { g(n - 1) } }\nlet r = g(3000000)\n'),
    ('fn g(p: num) { p }; let r = g("s")',
     'fn g(p: num) { p }\nlet r = g("s")\n'),
    ('fold((1 / 0), 1, len)',
     'let r = fold((1 / 0), 1, len)\n'),
    ('fold(1, -1, 2.5)',
     'let r = fold(1, -1, 2.5)\n'),
    ('fold(fn(a) { a }, 0, [1, 2])',
     'let r = fold(fn(a) { a }, 0, [1, 2])\n'),
    ('fold(fn(a) { a }, why 1, [1, 2])',
     'let r = fold(fn(a) { a }, why 1, [1, 2])\n'),
    ('fold(len, 2.5, [1, 2])',
     'let r = fold(len, 2.5, [1, 2])\n'),
    ('fold(len, true, [1, 2])',
     'let r = fold(len, true, [1, 2])\n'),
    ('get((1 / 0), guess(1, 0.5, "s"))',
     'let r = get((1 / 0), guess(1, 0.5, "s"))\n'),
    ('get(@{}, "abc")',
     'let r = get(@{}, "abc")\n'),
    ('get([], (1 / 0))',
     'let r = get([], (1 / 0))\n'),
    ('guess(0, [1, 2], true)',
     'let r = guess(0, [1, 2], true)\n'),
    ('guess(2.5, 1, why 1)',
     'let r = guess(2.5, 1, why 1)\n'),
    ('guess([], guess(1, 0.5, "s"), (1 / 0))',
     'let r = guess([], guess(1, 0.5, "s"), (1 / 0))\n'),
    ('has((1 / 0), @{})',
     'let r = has((1 / 0), @{})\n'),
    ('has(0, @{})',
     'let r = has(0, @{})\n'),
    ('has(@{}, true)',
     'let r = has(@{}, true)\n'),
    ('if (1 / 0) { 1 } else { 2 }',
     'let r = if (1 / 0) { 1 } else { 2 }\n'),
    ('if guess(1, 0.5, "s") { 1 } else { 2 }',
     'let r = if guess(1, 0.5, "s") { 1 } else { 2 }\n'),
    ('join(0, @{})',
     'let r = join(0, @{})\n'),
    ('join(@{a: 1}, (1 / 0))',
     'let r = join(@{a: 1}, (1 / 0))\n'),
    ('join([1 / 0], ",")',
     'let r = join([1 / 0], ",")\n'),
    ('keys((1 / 0))',
     'let r = keys((1 / 0))\n'),
    ('keys(2.5)',
     'let r = keys(2.5)\n'),
    ('len((1 / 0))',
     'let r = len((1 / 0))\n'),
    ('let big = 10 * 10; fn p(n, a) { if n == 0 { a } else { p(n - 1, a * a)',
     'let big = 10 * 10\nfn p(n, a) { if n == 0 { a } else { p(n - 1, a * a) } }\nlet r = sqrt(p(30, 3))\n'),
    ('let r = join([1, 1 / 0], ",")',
     'let r = join([1, 1 / 0], ",")\n'),
    ('let r = nope(1)',
     'let r = nope(1)\n'),
    ('let r = num("1e999999")',
     'let r = num("1e999999")\n'),
    ('let r = num("999999999999999999999999999999999999999999999999999999999',
     'let r = num("99999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999")\n'),
    ('map(2.5, 1)',
     'let r = map(2.5, 1)\n'),
    ('map([], (1 / 0))',
     'let r = map([], (1 / 0))\n'),
    ('merge("abc", len)',
     'let r = merge("abc", len)\n'),
    ('merge((1 / 0), 2.5)',
     'let r = merge((1 / 0), 2.5)\n'),
    ('miss (1 / 0)',
     'let r = miss (1 / 0)\n'),
    ('miss len',
     'let r = miss len\n'),
    ('not why 1',
     'let r = not why 1\n'),
    ('note((1 / 0), 0)',
     'let r = note((1 / 0), 0)\n'),
    ('num("abc")',
     'let r = num("abc")\n'),
    ('num((1 / 0))',
     'let r = num((1 / 0))\n'),
    ('num(@{a: 1})',
     'let r = num(@{a: 1})\n'),
    ('push((1 / 0), -1)',
     'let r = push((1 / 0), -1)\n'),
    ('push(1, (1 / 0))',
     'let r = push(1, (1 / 0))\n'),
    ('put("", [], (1 / 0))',
     'let r = put("", [], (1 / 0))\n'),
    ('put((1 / 0), "", @{a: 1})',
     'let r = put((1 / 0), "", @{a: 1})\n'),
    ('put(@{}, 1, (1 / 0))',
     'let r = put(@{}, 1, (1 / 0))\n'),
    ('range([1, 2], "abc")',
     'let r = range([1, 2], "abc")\n'),
    ('range(len, (1 / 0))',
     'let r = range(len, (1 / 0))\n'),
    ('rebind builtin',
     'fn g() { len(1, 2, 3) }\nlet r0 = g()\nlet len = push\nlet r = g()\n'),
    ('shape S = @{x: num}; fn outer() { let S = 5; fn g() -> S { 1 }; g() };',
     'shape S = @{x: num}\nfn outer() { let S = 5\nfn g() -> S { 1 }\ng() }\nlet r = outer()\n'),
    ('sqrt(-1)',
     'let r = sqrt(-1)\n'),
    ('sqrt(3^2048)',
     'fn p(n, a) { if n == 0 { a } else { p(n - 1, a * a) } }\nlet r = sqrt(p(11, 3))\n'),
    ('sqrt(@{})',
     'let r = sqrt(@{})\n'),
    ('steps((1 / 0), @{})',
     'let r = steps((1 / 0), @{})\n'),
    ('steps(len, (1 / 0))',
     'let r = steps(len, (1 / 0))\n'),
    ('sure("abc", guess(1, 0.5, "s"))',
     'let r = sure("abc", guess(1, 0.5, "s"))\n'),
    ('sure((1 / 0), 0)',
     'let r = sure((1 / 0), 0)\n'),
    ('sure(guess(1, 0.5, "s"), 1)',
     'let r = sure(guess(1, 0.5, "s"), 1)\n'),
    ('true and (1 / 0)',
     'let r = true and (1 / 0)\n'),
    ('true and len',
     'let r = true and len\n'),
    ('trunc((1 / 0))',
     'let r = trunc((1 / 0))\n'),
    ('trunc(1e400)',
     'let r = trunc(1e400)\n'),
    ('trunc(true)',
     'let r = trunc(true)\n'),
    ('typed(-1, [], "")',
     'let r = typed(-1, [], "")\n'),
    ('typed(2.5, fn(a) { a }, 0)',
     'let r = typed(2.5, fn(a) { a }, 0)\n'),
    ('typed(@{}, (1 / 0), len)',
     'let r = typed(@{}, (1 / 0), len)\n'),
    ('typed(len, @{}, "abc")',
     'let r = typed(len, @{}, "abc")\n'),
    ('why 1 < []',
     'let r = why 1 < []\n'),
]

# Cases that exist because site coverage only SAMPLES the guest side (see
# the module docstring): a second operand for a site the cover already
# reached, which the guest words differently from the first.
EXTRA = [
    ("len == len", "let r = len == len\n"),
    ("[1 / 0] == [1 / 0]", "let r = [1 / 0] == [1 / 0]\n"),
    ("@{a: 1 / 0} == @{a: 1}", "let r = @{a: 1 / 0} == @{a: 1}\n"),
    ("[len] == [len]", "let r = [len] == [len]\n"),
    ("merge(@{}, len)", "let r = merge(@{}, len)\n"),
    ("push(1, [2])", "let r = push(1, [2])\n"),
    ("put(\"\", [], 1)", 'let r = put("", [], 1)\n'),
    ("[1] + 0", "let r = [1] + 0\n"),
    ("(len)(1, 2, 3)", "let r = (len)(1, 2, 3)\n"),
    ("range(0, 1, 2)", "let r = range(0, 1, 2)\n"),
]

# Valid programs. Without these `test_missedness_agrees_except_where_exempt`
# would only ever see the failing half — round 362's `GOOD` reasoning, and
# the reason the corpus is not 100% misses by construction.
GOOD = [
    ("good-arith", "let r = 1 + 2 * 3\n"),
    ("good-list", "let r = push([1, 2], 3)\n"),
    ("good-record", 'let r = get(@{a: 1}, "a")\n'),
    ("good-closure", "fn g(a) { a + 1 }\nlet r = g(1)\n"),
    ("good-fold", "let r = fold(fn(ac, x) { ac + x }, 0, [1, 2, 3])\n"),
    ("good-rescue", "let r = (1 / 0) rescue 7\n"),
]

ALL = CORPUS + EXTRA + GOOD

# Cases that need a NON-DEFAULT interpreter to reach their site, so they
# cannot go through the guest (`run_src` has no way to set `max_depth`) and
# are host-only. Both are depth guards: `_call_direct`'s and
# `_closure_inline`'s, which the default `max_depth` of 20000 hides behind
# `_call_gen`'s copy — the direct engine hands off to the trampoline long
# before 20000 host frames, and the inline path is only live with
# `direct=False`. Four copies of one guard, and only two are reachable
# without turning the budget down.
HOST_ONLY = [
    ("depth-guard-direct",
     "fn h(a) { a + 1 }\nfn f(n) { if n == 0 { map(h, [1]) } "
     "else { f(n - 1) + 0 } }\nlet r = f(3)\n",
     {"max_depth": 4}),
    ("depth-guard-closure-inline",
     "fn h(a) { a + 1 }\nfn f(n) { if n == 0 { map(h, [1]) } "
     "else { f(n - 1) + 0 } }\nlet r = f(3)\n",
     {"direct": False, "max_depth": 4}),
]


# ---------------------------------------------------------------------------
# the three exemptions — each asserted load-bearing in BOTH directions
# ---------------------------------------------------------------------------

EXEMPT = {
    "E1-why-is-reified": (
        "The host's `why x` is an opaque `Explanation` payload that "
        "`show_payload` renders `<why>` and `deep_eq` refuses. The guest's "
        "is a REIFIED record (`reify`/`reify_node`, `@{op, v, ins}`), "
        "because guest code has to be able to READ a history — SPEC's own "
        "'history is data'. So every message that renders a `why` value "
        "renders a record in the guest, and `@{} == why 1` is a miss on "
        "the host and a plain `false` on the guest. This is the ONE "
        "missedness divergence in the corpus and it is a consequence of "
        "the design, not of a bug: making the guest refuse would mean "
        "making a reified history opaque to the guest code that reifies "
        "it."),
    "E2-a-callable-cannot-be-rebuilt": (
        "The host renders a function `<fn>`, `<fn NAME>` or `<builtin "
        "NAME>`. A guest function is a tagged RECORD, so a host message "
        "built around one renders the record. v0.28 tried to close this "
        "the way it closed the box-leak class — substitute, on the miss "
        "path only, a host value that renders the same — and it CANNOT "
        "be done: `<fn NAME>` requires constructing a host closure with a "
        "chosen name at run time, and Whence has no expression that does "
        "that (`fn NAME(..)` is a statement with a literal name). The "
        "guest's builtins could be mapped by a name->value table, but "
        "half a fix here is worse than a named exemption. Closing it "
        "needs a LANGUAGE change (a way to name a value) or a decision "
        "that `show_payload` stops printing a closure's name."),
    "E3-the-budgets-are-different-in-kind": (
        "`recursion too deep in g (depth 20000)` vs `guest recursion too "
        "deep in g (guest depth 400)`, and `tail loop too long in g "
        "(1000000 iterations)` vs the same guest-depth sentence. Round "
        "371 established the second one is a difference of KIND, not "
        "degree: the host charges a tail call NOTHING (SPEC rule 8) and "
        "the guest's `apply_closure` charges one guest frame per CALL, so "
        "a tail loop the host runs to `max_iter` the guest refuses at "
        "`GUEST_MAX_DEPTH`. The wording is deliberately different (the "
        "guest says 'guest') precisely so this cannot be mistaken for "
        "agreement."),
}

# Every case whose host and guest wording differ, mapped to the exemption
# that explains it. A case NOT in this table must agree.
EXEMPT_CASES = {
    "0 / why 1": "E1-why-is-reified",
    "find(why 1, [1, 2])": "E1-why-is-reified",
    "guess(2.5, 1, why 1)": "E1-why-is-reified",
    "not why 1": "E1-why-is-reified",
    "why 1 < []": "E1-why-is-reified",
    "@{} == why 1": "E1-why-is-reified",
    "at((1 / 0), fn(a) { a })": "E2-a-callable-cannot-be-rebuilt",
    "miss len": "E2-a-callable-cannot-be-rebuilt",
    "true and len": "E2-a-callable-cannot-be-rebuilt",
    "fn g(n) { if n == 0 { 0 } else { 1 + g(n - 1) } }; let r = g(100000)":
        "E3-the-budgets-are-different-in-kind",
    "fn g(n) { if n == 0 { 0 } else { g(n - 1) } }; let r = g(3000000)":
        "E3-the-budgets-are-different-in-kind",
}


# ---------------------------------------------------------------------------
# running the host
# ---------------------------------------------------------------------------

def outcome(src, **kw):
    """`("MISS", first-reason-without-position)`, `("VAL",)`, or a parse /
    host-exception marker. A host exception is DATA here: rule 2 says one
    can never escape, and `test_no_case_raises_out_of_the_host` is the
    assertion that says so."""
    try:
        env = Interpreter(out=lambda s: None, seed=7, **kw).run(src)
    except (LexError, ParseError) as e:
        return ("PARSE", type(e).__name__)
    except BaseException as e:                       # noqa: BLE001 — data
        return ("HOSTEXC", type(e).__name__, str(e)[:120])
    box = env.get("r")
    if box is None:
        return ("NOBIND",)
    if isinstance(box.payload, Miss):
        return ("MISS", LINE_SUFFIX.sub("", box.payload.reasons[0]))
    return ("VAL",)


def host_reason(src):
    o = outcome(src)
    return o[1] if o[0] == "MISS" else None


@pytest.fixture(scope="module")
def host_reasons():
    return {n: host_reason(s) for n, s in ALL}


# ---------------------------------------------------------------------------
# running the guest — ONE interpreter run for the whole corpus
# ---------------------------------------------------------------------------

def library_source():
    src = open(EXAMPLE, encoding="utf-8").read()
    assert MARKER in src
    return src.split(MARKER)[0]


def escape(s):
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r"))


@pytest.fixture(scope="module")
def guest_reasons():
    parts = [library_source()]
    for i, (_, src) in enumerate(ALL):
        parts.append('let __out%d = run_src("%s")\n' % (i, escape(src)))
    env = Interpreter(out=lambda s: None, seed=7).run("".join(parts))
    out = {}
    for i, (name, _) in enumerate(ALL):
        rec = env.get("__out%d" % i)
        assert rec is not None, name
        payload = rec.payload.fields["v"].payload
        out[name] = (LINE_SUFFIX.sub("", payload.reasons[0])
                     if isinstance(payload, Miss) else None)
    return out


# ---------------------------------------------------------------------------
# the site census
# ---------------------------------------------------------------------------

def declared_sites():
    """Every `mk_miss`/`merge_miss`/`_propagate` call in `interp.py`, keyed
    by (enclosing function, line)."""
    tree = ast.parse(open(INTERP_PY, encoding="utf-8").read())
    found = set()

    class V(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_Call(self, node):
            nm = (getattr(node.func, "id", None)
                  or getattr(node.func, "attr", None))
            fn = self.stack[-1] if self.stack else "<module>"
            if nm in ("mk_miss", "merge_miss", "_propagate") \
                    and fn not in MACHINERY:
                found.add((fn, node.lineno))
            self.generic_visit(node)

    V().visit(tree)
    return found


def observed_sites(cases, **kw):
    """The sites `cases` reach, captured by wrapping the two miss
    constructors and walking the host stack to the innermost declaring
    function. `sys._getframe` rather than `traceback.extract_stack`: the
    corpus builds tens of thousands of misses and the formatted variant
    costs more than the interpreter does."""
    import whence.interp as I
    fns = {fn for fn, _ in declared_sites()} - MACHINERY
    seen = set()
    originals = (I.mk_miss, I.merge_miss)

    def wrap(fn):
        def w(*a, **k):
            f = sys._getframe(1)
            while f is not None:
                if f.f_code.co_filename == INTERP_PY \
                        and f.f_code.co_name in fns:
                    seen.add((f.f_code.co_name, f.f_lineno))
                    break
                f = f.f_back
            return fn(*a, **k)
        return w

    I.mk_miss, I.merge_miss = wrap(originals[0]), wrap(originals[1])
    try:
        for _, src in cases:
            try:
                Interpreter(out=lambda s: None, seed=7, **kw).run(src)
            except (LexError, ParseError):
                pass
    finally:
        I.mk_miss, I.merge_miss = originals
    return seen


# Sites no program can reach, each with the reason and each still required
# to EXIST by `test_every_unreachable_site_still_exists`.
UNREACHABLE = {
    "_check_contract:_UnboundType":
        "Round 362's own entry, unchanged: v0.18 (round 342) made "
        "`parse_type` scope-aware, so an annotation naming a shape whose "
        "block has closed is a PARSE error at the annotation's own line "
        "and no source text reaches the sentinel.",
    "f_bcall:fnv-is-None":
        "DEAD CODE, and the source says so: `if fnv is None:  # "
        "unreachable while builtins are global`. `f_bcall` is only "
        "compiled for a name that resolved to a builtin, and Whence has no "
        "way to UNBIND a name, so the lookup cannot come back None. Kept "
        "as the floor under the `p is b` identity gate.",
}


def _unreachable_lines():
    src = open(INTERP_PY, encoding="utf-8").read().split("\n")
    out = set()
    for i, line in enumerate(src):
        if "isinstance(spec, _UnboundType)" in line:
            for j in range(i, min(i + 5, len(src))):
                if "mk_miss" in src[j]:
                    out.add(j + 1)
                    break
        if "unreachable while builtins are global" in line:
            for j in range(i, min(i + 3, len(src))):
                if "mk_miss" in src[j]:
                    out.add(j + 1)
                    break
    return out


# ---------------------------------------------------------------------------
# tests — the corpus and the census (fast tier)
# ---------------------------------------------------------------------------

def test_the_corpus_is_well_formed():
    names = [n for n, _ in ALL]
    assert len(names) == len(set(names)), "duplicate case name"
    assert len(ALL) >= 125, len(ALL)
    assert len(HOST_ONLY) == 2
    for name, src in ALL:
        assert src.endswith("\n"), name
        assert "let r = " in src, name


def test_the_declared_surface_is_far_wider_than_round_362_checked():
    """The number this round exists because of. If a future round narrows
    the surface this goes red and the narrowing has to be explained."""
    declared = declared_sites()
    fns = {fn for fn, _ in declared}
    assert len(declared) >= 120, len(declared)
    assert len(fns) >= 40, sorted(fns)
    # round 362's five, still there and still a small slice of the whole
    assert {"_check_contract", "b_typed", "b_sure", "b_get", "_field"} <= fns


def test_every_unreachable_site_still_exists():
    src = open(INTERP_PY, encoding="utf-8").read()
    assert "isinstance(spec, _UnboundType)" in src
    assert "unreachable while builtins are global" in src
    assert len(UNREACHABLE) == 2
    assert len(_unreachable_lines()) == 2


def test_every_exempt_case_is_in_the_corpus():
    names = {n for n, _ in ALL}
    missing = sorted(set(EXEMPT_CASES) - names)
    assert missing == [], missing
    assert set(EXEMPT_CASES.values()) == set(EXEMPT)


# ---------------------------------------------------------------------------
# tests — the host (slow tier: three engines over the whole corpus)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def three_engine_outcomes():
    """`{case: {engine: outcome}}`, computed ONCE. Three sweeps of this
    corpus cost ~90 s each (it contains a million-iteration tail loop, a
    20000-deep recursion and a 4100-digit `num`), so the three host tests
    below share one."""
    return {n: {m: outcome(s, **kw) for m, kw in MODES} for n, s in ALL}


@pytest.mark.whence_slow
def test_the_corpus_reaches_every_reachable_miss_site():
    declared = declared_sites()
    reached = set()
    for _, kw in MODES:
        reached |= observed_sites(ALL, **kw)
    for name, src, kw in HOST_ONLY:
        reached |= observed_sites([(name, src)], **kw)
    missing = sorted(s for s in declared
                     if s not in reached and s[1] not in _unreachable_lines())
    assert missing == [], (
        "the corpus reaches %d of %d declared sites; add a case for %s"
        % (len(reached & declared), len(declared), missing))


@pytest.mark.whence_slow
def test_the_three_engines_word_every_miss_identically(three_engine_outcomes):
    """A PIN on a negative result. The call guards exist in four copies
    across three engines; every copy must produce the same sentence and the
    same reason count for the same program."""
    bad = [(n, got) for n, got in three_engine_outcomes.items()
           if len({repr(v) for v in got.values()}) != 1]
    assert bad == [], bad


@pytest.mark.whence_slow
def test_no_case_raises_out_of_the_host(three_engine_outcomes):
    """SPEC rule 2, stated over this corpus: a runtime error is a miss, and
    never a host exception, in any engine."""
    bad = [(n, m, o) for n, got in three_engine_outcomes.items()
           for m, o in got.items() if o[0] == "HOSTEXC"]
    bad += [(n, "host-only", outcome(s, **kw)) for n, s, kw in HOST_ONLY
            if outcome(s, **kw)[0] == "HOSTEXC"]
    assert bad == [], bad


# ---------------------------------------------------------------------------
# tests — host vs guest (slow tier)
# ---------------------------------------------------------------------------

@pytest.mark.whence_slow
def test_the_corpus_exercises_both_outcomes(host_reasons):
    missed = [n for n, _ in ALL if host_reasons[n] is not None]
    clean = [n for n, _ in ALL if host_reasons[n] is None]
    assert len(missed) >= 115, len(missed)
    assert len(clean) >= 6, len(clean)


@pytest.mark.whence_slow
def test_missedness_agrees_except_where_exempt(host_reasons, guest_reasons):
    bad = [(n, host_reasons[n], guest_reasons[n]) for n, _ in ALL
           if (host_reasons[n] is None) != (guest_reasons[n] is None)
           and n not in EXEMPT_CASES]
    assert bad == [], bad


@pytest.mark.whence_slow
def test_the_wording_agrees_except_where_exempt(host_reasons, guest_reasons):
    bad = [(n, host_reasons[n], guest_reasons[n]) for n, _ in ALL
           if n not in EXEMPT_CASES and host_reasons[n] != guest_reasons[n]]
    assert bad == [], bad


@pytest.mark.whence_slow
def test_each_exemption_is_load_bearing(host_reasons, guest_reasons):
    """An exemption that no longer describes a real difference is a lie in
    the corpus — round 362's rule, and the thing that forced THIS round to
    retire its E3. Every exempt case must still diverge, and every
    exemption must still have at least one case."""
    agreed = [(n, host_reasons[n]) for n in EXEMPT_CASES
              if host_reasons[n] == guest_reasons[n]]
    assert agreed == [], (
        "these exemptions no longer describe a divergence — delete them "
        "rather than keep them: %s" % agreed)
    used = set(EXEMPT_CASES.values())
    assert used == set(EXEMPT), sorted(set(EXEMPT) ^ used)


@pytest.mark.whence_slow
def test_the_agreement_rate_does_not_regress(host_reasons, guest_reasons):
    """v0.28 took the 114-case cover from 86 agreeing to 103. A bound, not
    a pin: it may rise, and if it falls the round that lowered it has to
    say why. The two clauses say different things — the first is 'nothing
    diverges that is not exempt', the second is an absolute floor that a
    future round cannot satisfy by ADDING exemptions."""
    agree = sum(1 for n, _ in ALL if host_reasons[n] == guest_reasons[n])
    assert agree >= len(ALL) - len(EXEMPT_CASES), (agree, len(ALL))
    assert agree >= 119, agree
