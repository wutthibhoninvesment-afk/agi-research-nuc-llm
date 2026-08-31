"""v0.10 (round 108): the value-model floor — the frames AROUND each
provenance node, not the nodes (their count is fixed by the semantics).

  - `Prov.__init__` is a raw slot store: `ins` is a tuple or ONE unboxed
    node; `derived`/`leaf`/`mk_miss`/`merge_miss` normalise (lists,
    unboxing); `MergedProv.__init__` is one frame.
  - One compiled closure per binary operator with the numeric hot path
    inline (`==`/`!=`/`+` also strings); every other case is decided by
    `binop`, so misses have one wording.
  - Fused field / index closures for the pass-through case.
  - `if` guard: `c is True` / `c is False` / else `_if_bad`.
  - A run of ONE merged decision is a plain `if` node (one input: the
    condition); runs of ≥2 stay MergedProv. Same render, same shape.
  - `bench/ref_diff.py`: working tree vs a reference copy of the package
    (git HEAD by default) on every example — outputs, checks, every
    binding's render_why, counters. 39/39 SAME for v0.9 → v0.10.

Semantic anchor: the three-way differential (direct / fast / slow) over a
corpus of every operator × operand-kind combination, and over meta.lang and
self_eval.lang (previously excluded for runtime).
"""

import gc
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

from whence.interp import Interpreter, Env
from whence.parser import parse
from whence.values import (Prov, MergedProv, Miss, Record, derived, leaf,
                           mk_miss, merge_miss, render_why, _LAZY)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_v09 import run, val, assert_three_way, MODES, check_records  # noqa: E402,E501

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- the raw constructor contract -------------------------------------------

def test_prov_stores_ins_as_given_and_inputs_rewraps():
    a = leaf("literal", "", 1, 1)
    b = leaf("literal", "", 1, 2)
    assert Prov("x", "", 1, a).inputs == (a,)          # unboxed single
    assert Prov("x", "", 1, (a,)).inputs == (a,)       # 1-tuple accepted
    assert Prov("x", "", 1, (a, b)).inputs == (a, b)
    assert Prov("x", "", 1).inputs == ()
    assert Prov("x", "", 1, a)._ins is a
    assert Prov("x", "", 1, (a,))._ins == (a,)


def test_helpers_normalise_lists_and_unbox_singles():
    a = leaf("literal", "", 1, 1)
    b = leaf("literal", "", 1, 2)
    d = derived("+", "", 1, [a], 3)
    assert d._ins is a and d.inputs == (a,)
    assert derived("+", "", 1, [a, b], 3)._ins == (a, b)
    assert derived("+", "", 1, (), 3)._ins == ()
    m = mk_miss("boom", 1, "op", inputs=[a, b])
    assert m.inputs == (a, b) and isinstance(m.value, Miss)
    m1 = mk_miss("boom", 1, "op", inputs=[a])
    assert m1._ins is a
    bad = mk_miss("first", 1, "op")
    mm = merge_miss("+", "", 2, [bad, a])
    assert mm.inputs == (bad, a) and mm.value.reasons == ("first (line 1)",)
    mm1 = merge_miss("len", "", 2, [bad])
    assert mm1._ins is bad


def test_mergedprov_init_is_one_frame_and_keeps_count():
    a = leaf("literal", "", 1, 1)
    calls = []
    orig = Prov.__init__

    def spy(self, *args, **kw):
        calls.append(1)
        orig(self, *args, **kw)
    Prov.__init__ = spy
    try:
        m = MergedProv("if", "took then-branch", 3, (a, a), _LAZY, 1, 2)
    finally:
        Prov.__init__ = orig
    assert calls == []                  # no delegation to Prov.__init__
    assert m.count == 2 and m.inputs == (a, a) and m.value == 1
    assert m.show == "1" and m.label() == "if took then-branch"
    assert MergedProv("call", "f", 1, a, "x", 1, 4).count == 4


def test_env_takes_interp_positionally():
    root = Env()
    assert root.interp is None and root.parent is None
    sentinel = object()
    e = Env(root, sentinel)
    assert e.parent is root and e.interp is sentinel and e.vars == {}


# --- per-operator closures: every operand kind, every mode ------------------

BINARY_CORPUS = [
    # numeric, int / float / mixed
    "let result = 7 + 5", "let result = 7 - 5", "let result = 7 * 5",
    "let result = 7 / 2", "let result = 7 % 5", "let result = 7.5 + 1",
    "let result = 1 + 7.5", "let result = 7.5 * 2.0", "let result = 8 / 2.0",
    "let result = 7.5 % 2", "let result = 3 < 4", "let result = 3.0 <= 3",
    "let result = 3 > 4.5", "let result = 3 >= 3", "let result = 3 == 3.0",
    "let result = 3 != 3", "let result = 0 - 7",
    # zero divisors: int, float, negative zero
    "let result = 7 / 0", "let result = 7 % 0", "let result = 7 / 0.0",
    "let result = 7.5 % (0 - 0.0)", "let result = 0 / 0",
    # int meets float overflow (v0.2.1 hardening) on every arithmetic op
    "let result = 10000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000"
    " + 1.5",
    "let big = 10 * 10\nlet result = (big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big) - 1.5",
    "let big = 10 * 10\nlet huge = big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big * big * big * big * big * big * big * big * big * big * big"
    " * big * big\nlet a = huge * 1.5\nlet b = huge / 1.5\nlet c = huge % 1.5"
    "\nlet d = huge < 1.5\nlet result = [a, b, c, d, huge == 1.5]",
    # strings: concat, ordering, equality; arithmetic on strings is a miss
    'let result = "ab" + "cd"', 'let result = "ab" < "cd"',
    'let result = "ab" >= "cd"', 'let result = "ab" == "ab"',
    'let result = "ab" != "ab"', 'let result = "ab" - "cd"',
    'let result = "ab" * "cd"', 'let result = "ab" % "cd"',
    'let result = "ab" / "cd"',
    # bool: excluded from the numeric path
    "let result = true + 1", "let result = true == true",
    "let result = true == 1", "let result = false < true",
    "let result = true * 2", "let result = 1 / true",
    # mixed kinds, lists, records, misses
    'let result = 1 + "a"', 'let result = "a" + 1', 'let result = 1 < "a"',
    'let result = "a" == 1', "let result = [1] + [2]", "let result = [1] == [1]",
    "let result = [1] < [2]", "let result = @{a: 1} == @{a: 1}",
    "let result = @{a: 1} + @{b: 2}",
    "let result = (1 / 0) + 1", "let result = 1 + (1 / 0)",
    "let result = (1 / 0) == (1 / 0)", "let result = (1 / 0) < 2",
    'let result = miss "x" + 1', "let result = 1 - miss \"x\"",
    "fn f(x) { x }\nlet result = f == f", "fn f(x) { x }\nlet result = f + 1",
    # inside a function body (direct mode: the closures compile via d_call)
    "fn g(a, b) { [a + b, a - b, a * b, a / b, a % b, a < b, a <= b, a > b,"
    " a >= b, a == b, a != b] }\nlet result = [g(7, 2), g(7.5, 2), g(7, 0),"
    ' g("a", "b"), g(true, 1), g([1], [2]), g(1 / 0, 2)]',
]


@pytest.mark.parametrize("src", BINARY_CORPUS)
def test_binary_operators_three_way(src):
    runs = {}
    for mode, mkw in MODES.items():
        runs[mode] = run(src, **mkw)
    ref = runs["direct"]
    for mode in ("fast", "slow"):
        i, env, out = runs[mode]
        assert out == ref[2]
        assert render_why(env.get("result")) == render_why(ref[1].get("result")), \
            (mode, render_why(env.get("result")), render_why(ref[1].get("result")))


def test_binary_closure_misses_have_binop_wording():
    assert val("let result = 7 / 0").value.reasons == ("division by zero (line 1)",)
    assert val("let result = 7 % 0.0").value.reasons == ("modulo by zero (line 1)",)
    big = "let result = 1" + "0" * 400 + " + 1.5"
    assert val(big).value.reasons == \
        ("number too large for float arithmetic (line 1)",)
    assert val('let result = "a" < 1').value.reasons == \
        ("cannot order \"a\" and 1 (line 1)",)
    assert val("let result = true + 1").value.reasons == \
        ("cannot add true and 1 (line 1)",)
    assert val('let result = "a" * "b"').value.reasons == \
        ("cannot apply '*' to \"a\" and \"b\" (line 1)",)


def test_binary_closure_nodes_are_the_binop_nodes():
    v = val("let result = 2 + 3")
    n = v.inputs[0]
    assert (n.op, n.detail, n.line, n.value) == ("+", "", 1, 5)
    assert len(n.inputs) == 2 and type(n._ins) is tuple
    s = val('let result = "a" + "b"').inputs[0]
    assert (s.op, s.detail, s.value) == ("+", "concat", "ab")
    e = val('let result = "a" == "a"').inputs[0]
    assert (e.op, e.detail, e.value) == ("==", "", True)
    f = val("let result = 1.5 < 2").inputs[0]
    assert (f.op, f.value) == ("<", True)
    assert val("let result = 7 / 2").value == 3.5
    assert val("let result = 7.0 % 2").value == 1.0
    assert val("let result = 3 == 3.0").value is True
    assert val("let result = true == 1").value is False   # deep_eq: kinds


# --- fused field / index --------------------------------------------------------

FIELD_INDEX_CORPUS = [
    "let r = @{a: 1, b: @{c: 2}}\nlet result = [r.a, r.b.c]",
    "let r = @{a: 1}\nlet result = r.zz",
    "let result = (1 / 0).a",
    "let result = 5.a",
    'let result = "s".a',
    "let xs = [10, 20, 30]\nlet result = [xs[0], xs[2]]",
    "let xs = [10, 20, 30]\nlet result = xs[3]",
    "let xs = [10, 20, 30]\nlet result = xs[0 - 1]",
    "let xs = [10, 20, 30]\nlet result = xs[true]",
    "let xs = [10, 20, 30]\nlet result = xs[1.0]",
    "let xs = [10, 20, 30]\nlet result = xs[1 / 0]",
    "let result = (1 / 0)[0]",
    'let result = "abc"[1]',
    'let result = "abc"[3]',
    "let result = 5[0]",
    "let result = @{a: 1}[0]",
    "fn f(r, xs, i) { [r.a, xs[i], r.b, xs[i + 1]] }\n"
    "let result = [f(@{a: 1, b: 2}, [7, 8], 0), f(@{a: 1}, [7], 0),"
    " f(5, [], 0)]",
    # pass-through: the element / field node IS the value (no new node)
    "let xs = [1 + 1]\nlet r = @{k: 2 + 2}\nlet result = [xs[0], r.k]",
]


@pytest.mark.parametrize("src", FIELD_INDEX_CORPUS)
def test_field_and_index_three_way(src):
    runs = {}
    for mode, mkw in MODES.items():
        runs[mode] = run(src, **mkw)
    ref = runs["direct"]
    for mode in ("fast", "slow"):
        i, env, out = runs[mode]
        assert render_why(env.get("result")) == render_why(ref[1].get("result")), \
            (mode, render_why(env.get("result")), render_why(ref[1].get("result")))


def test_field_and_index_pass_through_identity():
    interp, env, _ = run("let xs = [1 + 1]\nlet r = @{k: 2 + 2}\n"
                         "let a = xs[0]\nlet b = r.k")
    assert env.get("a").inputs[0] is env.get("xs").inputs[0].inputs[0]
    assert env.get("b").inputs[0] is env.get("r").inputs[0].inputs[0]
    assert env.get("xs").value.buf[0] is env.get("a").inputs[0]


def test_field_and_index_miss_wording_unchanged():
    assert val("let r = @{a: 1}\nlet result = r.zz").value.reasons == \
        ("no field 'zz' (record has: a) (line 2)",)
    assert val("let result = 5.a").value.reasons == \
        ("cannot access .a on 5 (line 1)",)
    assert val("let xs = [1]\nlet result = xs[1]").value.reasons == \
        ("index 1 out of range (len 1) (line 2)",)
    assert val("let xs = [1]\nlet result = xs[true]").value.reasons == \
        ("list index must be an integer, got true (line 2)",)
    assert val('let result = "ab"[5]').value.reasons == \
        ("index 5 out of range (len 2) (line 1)",)
    assert val("let result = 5[0]").value.reasons == \
        ("cannot index 5 (line 1)",)


# --- the `if` guard ---------------------------------------------------------------

IF_CORPUS = [
    "let result = if true { 1 } else { 2 }",
    "let result = if false { 1 } else { 2 }",
    "let result = if 1 { 1 } else { 2 }",
    'let result = if "yes" { 1 } else { 2 }',
    "let result = if 1 / 0 { 1 } else { 2 }",
    "let result = if [] { 1 } else { 2 }",
    "fn f(c) { if c { 1 } else { 2 } }\n"
    "let result = [f(true), f(false), f(1), f(1 / 0), f(@{})]",
    "fn f(c) { if c { 1 } else if c == 0 { 3 } else { 2 } }\n"
    "let result = [f(true), f(false), f(0), f(1 / 0)]",
    # pending tail call through a bad condition never happens: the guard
    # decides before the branch runs
    "fn lp(i) { if i { lp(false) } else { i } }\nlet result = lp(true)",
    "fn lp(i) { if i { lp(1) } else { i } }\nlet result = lp(true)",
]


@pytest.mark.parametrize("src", IF_CORPUS)
def test_if_guard_three_way(src):
    assert_three_way(src) if "fn " in src else None
    runs = {}
    for mode, mkw in MODES.items():
        runs[mode] = run(src, **mkw)
    ref = runs["direct"]
    for mode in ("fast", "slow"):
        assert render_why(runs[mode][1].get("result")) == \
            render_why(ref[1].get("result")), mode


def test_if_guard_wording():
    assert val("let result = if 1 { 1 } else { 2 }").value.reasons == \
        ("if condition must be true/false, got 1 (line 1)",)
    v = val("let result = if 1 / 0 { 1 } else { 2 }")
    assert v.value.reasons == ("division by zero (line 1)",)
    n = v.inputs[0]                       # `let` wraps the `if` miss
    assert n.op == "if" and n.detail == "condition was miss"
    assert n.inputs[0].op == "/" and isinstance(n.inputs[0].value, Miss)


# --- merged runs: one decision is a plain node ------------------------------------

def test_single_decision_runs_are_plain_nodes_multi_are_merged():
    # alternating between two `if` nodes: every run is one decision long
    src = ("fn a(i) { if i == 0 { 0 } else { b(i - 1) } }\n"
           "fn b(i) { if i == 100 { 1 } else { a(i - 1) } }\n"
           "let result = a(6)")
    interp, env, _ = run(src)
    call = env.get("result").inputs[0]
    assert isinstance(call, MergedProv) and call.count == 7
    assert call.detail == "a/b"
    runs = list(call.inputs[1:])
    assert len(runs) == 6
    for n in runs:
        assert type(n) is Prov and n.count == 1 and n.op == "if"
        assert len(n.inputs) == 1 and n.inputs[0].op == "=="
        assert n.detail == "took else-branch" and n.value == 0
        assert n._ins is n.inputs[0]                 # unboxed single input
    assert render_why(env.get("result")) == render_why(
        run(src, fast=False)[1].get("result"))
    # the same loop through ONE `if`: a single run of six merged decisions
    src2 = "fn go(i) { if i == 0 { 0 } else { go(i - 1) } }\nlet result = go(6)"
    interp, env, _ = run(src2)
    call = env.get("result").inputs[0]
    runs = list(call.inputs[1:])
    assert len(runs) == 1 and isinstance(runs[0], MergedProv)
    assert runs[0].count == 6 and len(runs[0].inputs) == 6
    assert "×6" in render_why(env.get("result"))
    # mixed: two decisions, then one, then two → [2, 1, 2]-shaped runs
    src3 = ("fn a(i) { if i > 4 { a(i - 1) } else { b(i) } }\n"
            "fn b(i) { if i == 0 { 0 } else if i == 3 { a(i - 1) }"
            " else { b(i - 1) } }\n"
            "let result = a(6)")
    interp, env, _ = run(src3)
    call = env.get("result").inputs[0]
    kinds = [(type(n).__name__, n.count) for n in call.inputs[1:]]
    assert all(k == "MergedProv" if c > 1 else k == "Prov"
               for k, c in kinds), kinds
    assert any(c > 1 for _, c in kinds) and any(c == 1 for _, c in kinds)
    assert render_why(env.get("result")) == render_why(
        run(src3, fast=False)[1].get("result"))


def test_merged_call_node_golden_render():
    src = ("fn a(i) { if i == 0 { 0 } else { b(i - 1) } }\n"
           "fn b(i) { if i == 9 { 1 } else { a(i - 1) } }\n"
           "let result = a(2)")
    tree = render_why(run(src)[1].get("result"))
    assert tree == (
        "0 ← let result  (line 3)\n"
        "└─ 0 ← call a/b ×3  (line 3)\n"
        "   ├─ 0 ← if took then-branch  (line 1)\n"
        "   │  ├─ 0 ← literal  (line 1)\n"
        "   │  └─ true ← ==  (line 1)\n"
        "   │     ├─ 0 ← arg i  (line 2)\n"
        "   │     │  └─ 0 ← -  (line 2)\n"
        "   │     │     ├─ 1 ← arg i  (line 1)\n"
        "   │     │     │  └─ 1 ← -  (line 1)\n"
        "   │     │     │     ├─ 2 ← arg i  (line 3)\n"
        "   │     │     │     │  └─ 2 ← literal  (line 3)\n"
        "   │     │     │     └─ 1 ← literal  (line 1)\n"
        "   │     │     └─ 1 ← literal  (line 2)\n"
        "   │     └─ 0 ← literal  (line 1)\n"
        "   ├─ 0 ← if took else-branch  (line 1)\n"
        "   │  └─ false ← ==  (line 1)\n"
        "   │     ├─ 2 ← arg i  (line 3)  ⟲ shown above\n"
        "   │     └─ 0 ← literal  (line 1)\n"
        "   └─ 0 ← if took else-branch  (line 2)\n"
        "      └─ false ← ==  (line 2)\n"
        "         ├─ 1 ← arg i  (line 1)  ⟲ shown above\n"
        "         └─ 9 ← literal  (line 2)"), tree


# --- the big examples join the three-way differential ---------------------------

def _snapshot(src, **mkw):
    """Everything the differential compares, as plain data — the run's
    interpreter, env and multi-million-node history are dropped before
    the next mode runs. Keeping three histories alive (and collecting
    between them) made meta.lang's three-way 27 s instead of 12: every
    gen-2 pass re-traverses whatever is live. gc_relief is the CLI's
    setting; the collect FIRST drops the previous test's cyclic garbage
    (Env <-> Closure <-> Prov), which took self_eval from 16 s to 1.7."""
    gc.collect()
    interp, env, out = run(src, gc_relief=True, **mkw)
    snap = {
        "out": out,
        "checks": check_records(interp),
        "trees": {n: render_why(env.get(n)) for n in env.vars},
        "counters": (interp.tail_calls, interp.depth),
        "direct_hits": interp.direct_hits,
        "all_ok": bool(interp.checks) and all(c["ok"] for c in interp.checks),
    }
    del interp, env
    return snap


@pytest.mark.parametrize("name", ["meta.lang", "self_eval.lang"])
@pytest.mark.whence_slow
def test_three_way_on_big_examples(name):
    with open(os.path.join(ROOT, "examples", name)) as f:
        src = f.read()
    ref = _snapshot(src)
    assert ref["direct_hits"] > 0 and ref["all_ok"]
    for mode in ("fast", "slow"):
        snap = _snapshot(src, **MODES[mode])
        assert snap["out"] == ref["out"], (name, mode)
        assert snap["checks"] == ref["checks"], (name, mode)
        for n in ref["trees"]:
            assert snap["trees"][n] == ref["trees"][n], (name, mode, n)
        assert snap["counters"] == ref["counters"]
    gc.collect()


# --- bench/ref_diff.py: the tool itself ----------------------------------------------

def _copy_package(dst):
    pkg = os.path.join(dst, "whence_ref")
    shutil.copytree(os.path.join(ROOT, "whence"), pkg,
                    ignore=shutil.ignore_patterns("__pycache__"))
    return pkg


def _ref_diff(ref_dir, *files, modes="direct"):
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "bench", "ref_diff.py"),
         "--ref", ref_dir, "--modes", modes, "--counters"] +
        [os.path.join(ROOT, "examples", f) for f in files],
        capture_output=True, text=True, timeout=120)


def test_ref_diff_same_on_identical_copy_and_diff_on_sabotage():
    tmp = tempfile.mkdtemp(prefix="whence_refdiff_")
    try:
        pkg = _copy_package(tmp)
        r = _ref_diff(tmp, "hello.lang", "blame.lang")
        assert r.returncode == 0, r.stdout + r.stderr
        assert r.stdout.count("SAME") == 2 and "0 differing" in r.stdout
        # a one-word rendering change in the reference: caught by `why`
        p = os.path.join(pkg, "interp.py")
        s = open(p).read()
        old = '"took then-branch"'
        assert s.count(old) > 1
        open(p, "w").write(s.replace(old, '"took then branch"'))
        r = _ref_diff(tmp, "hello.lang", "blame.lang", modes="direct,slow")
        assert r.returncode == 1
        assert "why:verdict" in r.stdout
        lines = r.stdout.splitlines()
        assert [l[:4] for l in lines if "hello" in l] == ["DIFF", "DIFF"]
        # blame.lang has no `if`, so it is legitimately unaffected
        assert [l[:4] for l in lines if "blame" in l] == ["SAME", "SAME"]
        assert "2 differing" in r.stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ref_diff_counters_flag_catches_a_mode_only_change():
    # a copy whose direct mode is off is byte-identical in every tree but
    # its counters differ: only --counters sees it
    tmp = tempfile.mkdtemp(prefix="whence_refdiff_")
    try:
        pkg = _copy_package(tmp)
        p = os.path.join(pkg, "interp.py")
        s = open(p).read()
        old = "direct = self.direct\n"
        assert s.count(old) == 1
        open(p, "w").write(s.replace(old, "direct = False\n"))
        r = _ref_diff(tmp, "history.lang")
        assert r.returncode == 1 and "counters" in r.stdout, r.stdout
        r2 = subprocess.run(
            [sys.executable, os.path.join(ROOT, "bench", "ref_diff.py"),
             "--ref", tmp, "--modes", "direct",
             os.path.join(ROOT, "examples", "history.lang")],
            capture_output=True, text=True, timeout=120)
        assert r2.returncode == 0 and "SAME" in r2.stdout, r2.stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.whence_slow
def test_ref_diff_fuzz_mode_same_on_copy_and_diff_on_sabotage():
    tmp = tempfile.mkdtemp(prefix="whence_refdiff_")
    try:
        pkg = _copy_package(tmp)
        cmd = [sys.executable, os.path.join(ROOT, "bench", "ref_diff.py"),
               "--ref", tmp, "--modes", "direct,slow", "--counters",
               "--fuzz", "7", "-n", "12", "--timeout", "5"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "0 (program, mode) pairs differ" in r.stdout
        # NOT every random program binds a name with a top-level `let`
        # (round 138 finding: e.g. a program made only of `fn`/`check`/
        # `print` statements whose fns are never called binds nothing via
        # `let` at all, so renaming the `let` op label changes none of its
        # rendered why-trees — a correct SAME, not a test failure). Compute
        # the expected count the same way instead of assuming every parsed
        # program qualifies.
        # ROOT is languages/whence; harness/ is a sibling of languages/ in the
        # real checkout, but this file may be running from a tempdir copy of
        # just languages/whence (any mutation/repair run) — in that case
        # AGI_RESEARCH_ROOT (set by harness/swe/proc.py on every test
        # subprocess it spawns) names the real repo instead (round 149).
        agi_root = os.environ.get("AGI_RESEARCH_ROOT") or os.path.dirname(os.path.dirname(ROOT))
        harness = os.path.join(agi_root, "harness")
        sys.path.insert(0, harness)
        try:
            from swe.fuzz import ProgramGen
        finally:
            sys.path.pop(0)
        gen = ProgramGen(7)
        n_with_let = 0
        for _ in range(12):
            src = gen.program()
            try:
                parse(src)
            except Exception:
                continue
            if any(line.startswith("let ") for line in src.splitlines()):
                n_with_let += 1
        p = os.path.join(pkg, "interp.py")
        src = open(p).read()
        assert src.count('"let"') >= 2
        open(p, "w").write(src.replace('"let"', '"lett"'))
        r = subprocess.run(cmd + ["--show"], capture_output=True, text=True,
                           timeout=300)
        assert r.returncode == 1, r.stdout + r.stderr
        parsed = int(r.stdout.split(" programs parsed")[0].split()[-1])
        diffs = r.stdout.count("DIFF program")
        # Round 347: floor lowered from 5 to 3. This is a SINGLE seed's
        # first 12 programs from one reused generator (so `scope`/`fns`
        # accumulate and later programs nest deeper), which makes the parse
        # count a coin flip against any perturbation of the random stream —
        # exactly the fragile-floor pattern round 337 documented in
        # `test_generator_now_emits_the_shape_builtins`. Round 347's shape
        # recipes moved it from 5/12 to 4/12 with no change in the parse
        # RATE that matters (600 programs: 545 ok, 49 parse errors, none of
        # them shape-related). The floor's only job is to keep the
        # comparison non-vacuous; the load-bearing assertions are the two
        # below, which relate the sabotage's diffs to the programs that can
        # actually show one.
        assert parsed >= 3 and n_with_let >= 1
        assert diffs == 2 * n_with_let, r.stdout
        assert "why:" in r.stdout and "let " in r.stdout    # --show printed a source
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _load_ref_diff_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ref_diff_under_test", os.path.join(ROOT, "bench", "ref_diff.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- round 395 (SWE-loop D): the precondition NO ref_diff test ran -----------
#
# The five tests above all pass `--ref <dir>`, so `extract_head` --- the only
# reader of the module set and the only path that touches git --- had zero
# coverage for its whole life. `whence/foreign.py` arrived with v0.33 and was
# missing from the hand-written list, and `harness/swe/toolliveness.py`
# re-executed the consequence commit by commit: the command died with
# `ModuleNotFoundError` before comparing anything at 9 consecutive HEADs, the
# HEADs of rounds 387-391, with every one of these tests green throughout.
# Green tests over every path but the one that broke.

V021_REV = "3ed4391"        # round 350, "Whence v0.21 host/guest lexer
                            # differential" --- the newest revision whose
                            # `whence/` predates `foreign.py`. A sha is
                            # immutable, so this pin cannot rot; it can only
                            # become unreachable, which the skip below names.


def _agi_root():
    return os.environ.get("AGI_RESEARCH_ROOT") or os.path.dirname(
        os.path.dirname(ROOT))


def _have_rev(rev):
    return subprocess.run(["git", "-C", _agi_root(), "cat-file", "-e",
                           rev + "^{commit}"],
                          capture_output=True).returncode == 0


def _importable(pkg_parent):
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r); "
         "import whence_ref.interp, whence_ref.values" % pkg_parent],
        capture_output=True, text=True, timeout=120)


def test_ref_diff_extract_head_builds_an_importable_reference_package():
    """The anti-rot guard. A `whence/` module that HEAD's `interp` imports
    but the extraction misses makes this red in the round that adds it,
    instead of dark for five."""
    if not _have_rev("HEAD"):
        pytest.skip("no git checkout reachable from %s" % _agi_root())
    rd = _load_ref_diff_module()
    tmp = tempfile.mkdtemp(prefix="whence_refhead_")
    try:
        rd.extract_head(tmp)
        pkg = os.path.join(tmp, "whence_ref")
        got = sorted(f[:-3] for f in os.listdir(pkg) if f.endswith(".py"))
        assert got == sorted(rd.ref_modules("HEAD")), got
        assert "interp" in got and "__init__" in got
        r = _importable(tmp)
        assert r.returncode == 0, r.stderr
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ref_diff_module_set_follows_the_revision_not_the_working_tree():
    """Round 392 derived the set from `os.listdir(ROOT/whence)` while the
    extraction reads a git revision, so a module present in the working tree
    and not yet committed made `git show` exit 128 and killed the whole
    command --- in the round that adds a module, which is the round that most
    needs the differential. Reading it from the revision being BUILT is what
    closes that: here the working tree is a strict superset of v0.21's
    package, and the extraction must follow v0.21."""
    if not _have_rev(V021_REV):
        pytest.skip("%s unreachable (shallow clone?)" % V021_REV)
    rd = _load_ref_diff_module()
    worktree = {f[:-3] for f in os.listdir(os.path.join(ROOT, "whence"))
                if f.endswith(".py")}
    old = set(rd.ref_modules(V021_REV))
    assert "foreign" in worktree and "foreign" not in old
    assert old < worktree                      # strict subset: it is not
                                               # reading the working tree
    tmp = tempfile.mkdtemp(prefix="whence_refold_")
    try:
        rd.extract_head(tmp, V021_REV)
        pkg = os.path.join(tmp, "whence_ref")
        got = {f[:-3] for f in os.listdir(pkg) if f.endswith(".py")}
        assert got == old
        assert not os.path.exists(os.path.join(pkg, "foreign.py"))
        r = _importable(tmp)
        assert r.returncode == 0, r.stderr    # v0.21 imports on its own terms
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ref_diff_reference_package_omitting_an_imported_module_is_caught():
    """The positive control for the two tests above: build HEAD's package
    with `foreign` removed --- exactly what the v0.10-v0.33 hand-written
    tuple did --- and confirm the import fails with the recorded message. A
    guard that has never been shown to go red is not a guard."""
    if not _have_rev("HEAD"):
        pytest.skip("no git checkout reachable from %s" % _agi_root())
    rd = _load_ref_diff_module()
    tmp = tempfile.mkdtemp(prefix="whence_refsab_")
    try:
        rd.extract_head(tmp)
        os.remove(os.path.join(tmp, "whence_ref", "foreign.py"))
        r = _importable(tmp)
        assert r.returncode != 0
        assert "No module named 'whence_ref.foreign'" in r.stderr, r.stderr
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ref_diff_fuzz_transient_new_tree_timeout_is_retried_not_reported():
    """round 144: `run_capped`'s SIGALRM cap is wall-clock, not CPU time, so
    under concurrent load the SAME program can cross the budget on one
    interpreter and not the other with no real behavioural difference —
    round 137 saw exactly this ('DIFF ... timed out under the new tree
    only', reliably in-suite alongside another campaign's subprocesses,
    reliably absent standalone) and could not root-cause it. Simulates one
    transient new-tree timeout in-process (no real timing involved) and
    checks the automatic 4x retry absorbs it instead of reporting a diff."""
    rd = _load_ref_diff_module()
    tmp = tempfile.mkdtemp(prefix="whence_refdiff_retry_")
    try:
        _copy_package(tmp)
        real_run_capped = rd.run_capped
        timed_out_once = [False]

        def fake_run_capped(interp_mod, values_mod, src, mkw, seconds):
            if interp_mod.__name__.startswith("whence.") and not timed_out_once[0]:
                timed_out_once[0] = True
                return "timeout"
            return real_run_capped(interp_mod, values_mod, src, mkw, seconds)

        rd.run_capped = fake_run_capped
        old_argv = sys.argv
        sys.argv = ["ref_diff.py", "--ref", tmp, "--modes", "direct",
                    "--fuzz", "7", "-n", "5", "--timeout", "5"]
        try:
            with pytest.raises(SystemExit) as exc:
                rd.main()
        finally:
            sys.argv = old_argv
            rd.run_capped = real_run_capped
        assert timed_out_once[0]                # the fake actually fired
        assert exc.value.code == 0, "a transient timeout absorbed by the " \
            "4x retry must not be reported as a diff"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ref_diff_fuzz_persistent_new_tree_timeout_is_a_real_finding():
    """The other half of the same fix: a timeout that does NOT clear at 4x
    (a genuine hang, e.g. a regression that made some program loop forever)
    must still be reported, not silently absorbed."""
    rd = _load_ref_diff_module()
    tmp = tempfile.mkdtemp(prefix="whence_refdiff_hang_")
    try:
        _copy_package(tmp)
        real_run_capped = rd.run_capped

        def fake_run_capped(interp_mod, values_mod, src, mkw, seconds):
            if interp_mod.__name__.startswith("whence."):
                return "timeout"
            return real_run_capped(interp_mod, values_mod, src, mkw, seconds)

        rd.run_capped = fake_run_capped
        old_argv = sys.argv
        sys.argv = ["ref_diff.py", "--ref", tmp, "--modes", "direct",
                    "--fuzz", "7", "-n", "5", "--timeout", "5"]
        try:
            with pytest.raises(SystemExit) as exc:
                rd.main()
        finally:
            sys.argv = old_argv
            rd.run_capped = real_run_capped
        assert exc.value.code == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- the v0.9 frame-charge bug: comprehensions are frames ------------------------

NEST = "fn nest(n) { if n == 0 { [] } else { [nest(n - 1)] } }\n"
ARG = ("fn id(x) { x }\n"
       "fn f(n) { if n == 0 { 0 } else { id(f(n - 1)) } }\n")
ARG3 = ("fn g(a, b, c) { a }\n"
        "fn f(n) { if n == 0 { 0 } else { g(f(n - 1), 1, 2) } }\n")
FIELD_LIST = ("fn h(n) { if n == 0 { @{v: 0} } else { @{v: [h(n - 1), n]} } }\n")


def _peak_frames(src, **kw):
    depth = [0]
    peak = [0]

    def prof(frame, event, arg):
        if event == "call":
            depth[0] += 1
            if depth[0] > peak[0]:
                peak[0] = depth[0]
        elif event == "return":
            depth[0] -= 1
    interp = Interpreter(**kw)
    sys.setprofile(prof)
    try:
        env = interp.run(src)
    finally:
        sys.setprofile(None)
    assert interp.direct_fallbacks == 0
    return peak[0], interp, env


@pytest.mark.parametrize("prog,fn,call", [
    (NEST, "nest", "let result = nest(%d)\n"),
    (ARG, "f", "let result = f(%d)\n"),
    (ARG3, "f", "let result = f(%d)\n"),
    (FIELD_LIST, "h", "let result = h(%d)\n"),
])
def test_host_frames_per_level_equal_the_charge_for_list_and_arg_shapes(prog, fn, call):
    # v0.9 charged `cdepth + 1` but the list literal / call-argument
    # comprehensions added a frame per level: measured 5, charged 4 for
    # `nest`. With ~1400 levels at the CLI's limit of 6000 the 350-frame
    # reserve overflowed and RecursionError escaped (bench/ref_diff.py
    # --fuzz found it; the oracle campaigns run at the default limit).
    a, _, _ = _peak_frames(prog + call % 20)
    b, interp, env = _peak_frames(prog + call % 50)
    per_level = (b - a) / 30.0
    body = [s for s in parse(prog).stmts if getattr(s, "name", None) == fn][0].body
    interp.compile_direct(body)
    charged = body.cdepth + 1
    assert per_level == charged, (per_level, charged)
    assert interp.depth == 0


def test_deep_list_nesting_at_the_cli_limit_does_not_raise():
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(6000)
    try:
        for src, want in ((NEST + "let deep = nest(3000)\nlet result = len(deep)\n", 1),
                          (ARG + "let result = f(2500)\n", 0),
                          (FIELD_LIST + "let result = len(h(2000).v)\n", 2)):
            interp, env, _ = run(src, gc_relief=True)
            assert env.get("result").value == want
            assert interp.depth == 0 and interp.peak_depth >= 2000
            assert interp.direct_hits > 1000        # ran direct for most levels
    finally:
        sys.setrecursionlimit(old)


def test_cli_runs_the_fuzz_deep_nesting_program():
    src = NEST + "let deep = nest(3000)\nlet v = len(deep)\ncheck \"one\": v == 1\n"
    path = os.path.join(tempfile.mkdtemp(prefix="whence_nest_"), "nest.lang")
    with open(path, "w") as f:
        f.write(src)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "run.py"), path],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Traceback" not in r.stderr and "checks: 1 passed" in r.stdout
