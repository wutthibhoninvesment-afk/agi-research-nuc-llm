"""v0.11 (round 110): the ceiling round.

Measured before building (bench numbers in knowledge/round-110): fusing a
NameRef / constant operand into its parent closure saves 10–20 ns per
operand; a hand-transpiled `fib` body (15 closure frames → 1 Python
frame, why-tree identical) through the real `_call_direct` is 1.09×; the
call path with EVERY piece of bookkeeping ablated is 1.14×. So v0.11 does
the last thing that pays and pins it:

  - `_body_entry` caches `(bd, cost)` on the function body node
    (`Node.entry`): the evaluator a direct call runs and the frames it is
    charged (1 for a fast body, `cdepth` + 1 for a direct one, False when
    the body cannot compile — then every call of it falls back).
  - one- and two-parameter bindings are unrolled; `depth` / `_hleft` are
    read once and stored back.
  - the frame-charge oracle (`harness/swe/oracles.py::oracle_frames`)
    automates round 108's bug class; `bench/reserve_probe.py` measures the
    reserve the budget really needs; `bench/minof.py` is the min-of-N
    fresh-process bench driver.

Semantic anchor: the three-way differential on every call shape the
unrolling touches (0–4 parameters, misses as arguments, arity misses at
every stage of a tail loop, body switches with different parameter
counts), plus the frames-per-level measurement now asserting the cached
cost directly.
"""

import os
import subprocess
import sys

import pytest

from whence.interp import Interpreter, Env
from whence.parser import parse
from whence.values import Builtin, Miss, leaf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_v09 import run, val, assert_three_way  # noqa: E402
from test_v10 import _peak_frames, NEST, ARG, ARG3, FIELD_LIST  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_ast(src, **kw):
    """Like `run`, but keeps the parsed program so tests can read the
    caches on its nodes."""
    out = []
    interp = Interpreter(out=out.append, **kw)
    program = parse(src)
    env = Env(interp.globals)
    for stmt in program.stmts:
        interp.exec_stmt(stmt, env)
    return program, interp, env, out


# --- the entry cache ---------------------------------------------------------

def test_body_entry_caches_the_evaluator_and_its_cost():
    src = "fn f(x) { x + 1 }\nfn g(x) { f(x) + f(x) }\nlet result = g(1)\n"
    program, interp, env, _ = run_ast(src)
    fbody = program.stmts[0].body
    gbody = program.stmts[1].body
    assert env.get("result").value == 4
    # call-free body: the fast closure, one frame charged (this call's)
    assert fbody.entry == (fbody.fast, 1) and fbody.fast
    # body with calls: the direct closure, cdepth + 1 frames
    assert gbody.entry[0] is gbody.direct and gbody.direct
    assert gbody.entry[1] == gbody.cdepth + 1
    assert interp.direct_fallbacks == 0


def test_entry_is_computed_once_and_reused_by_a_second_interpreter():
    src = "fn f(x) { x * 2 }\nlet result = f(2)\n"
    program = parse(src)
    a = Interpreter()
    env = Env(a.globals)
    for s in program.stmts:
        a.exec_stmt(s, env)
    ent = program.stmts[0].body.entry
    assert ent is not None
    b = Interpreter()
    env2 = Env(b.globals)
    for s in program.stmts:
        b.exec_stmt(s, env2)
    assert program.stmts[0].body.entry is ent      # not recomputed
    assert env2.get("result").value == 4 and b.direct_fallbacks == 0


def test_a_body_too_tall_to_compile_has_a_false_entry_and_always_falls_back():
    terms = " + ".join(["1"] * (Interpreter.FAST_MAX_DEPTH + 40))
    src = "fn f(n) { %s + n }\nlet result = f(1)\nlet again = f(2)\n" % terms
    program, interp, env, _ = run_ast(src)
    body = program.stmts[0].body
    assert body.entry[0] is False
    assert env.get("result").value == Interpreter.FAST_MAX_DEPTH + 41
    assert env.get("again").value == Interpreter.FAST_MAX_DEPTH + 42
    assert interp.direct_fallbacks == 2          # every call of it


def test_trampoline_only_interpreters_never_write_the_entry():
    src = "fn f(x) { x + 1 }\nlet result = f(1)\n"
    program = parse(src)
    for kw in ({"direct": False}, {"fast": False}):
        interp = Interpreter(**kw)
        env = Env(interp.globals)
        for s in program.stmts:
            interp.exec_stmt(s, env)
        assert env.get("result").value == 2
    assert program.stmts[0].body.entry is None


@pytest.mark.parametrize("prog,fn,call", [
    (NEST, "nest", "let result = nest(%d)\n"),
    (ARG, "f", "let result = f(%d)\n"),
    (ARG3, "f", "let result = f(%d)\n"),
    (FIELD_LIST, "h", "let result = h(%d)\n"),
])
def test_cached_cost_is_the_measured_frames_per_level(prog, fn, call):
    a, _, _ = _peak_frames(prog + call % 20)
    b, interp, env = _peak_frames(prog + call % 50)
    per_level = (b - a) / 30.0
    body = [s for s in parse(prog).stmts if getattr(s, "name", None) == fn][0].body
    ent = interp._body_entry(body)
    assert body.entry is ent
    assert per_level == ent[1], (per_level, ent)


# --- unrolled bindings: every parameter count, three-way ----------------------

@pytest.mark.parametrize("src", [
    "fn z() { 7 }\nlet result = z()\n",
    "fn one(a) { a * 2 }\nlet result = one(3)\n",
    "fn two(a, b) { a - b }\nlet result = two(9, 4)\n",
    "fn three(a, b, c) { a + b * c }\nlet result = three(1, 2, 3)\n",
    "fn four(a, b, c, d) { [a, b, c, d] }\nlet result = four(1, 2, 3, 4)\n",
    # the same parameter name bound twice in one call (shadowing order)
    "fn two(a, b) { a }\nlet result = two(two(1, 2), two(3, 4))\n",
    # misses are bound like any value: functions run WITH miss args
    "fn two(a, b) { b }\nlet result = two(miss \"x\", 1)\n",
    "fn one(a) { a }\nlet result = one(miss \"x\")\n",
    # arity misses at the call
    "fn two(a, b) { a }\nlet result = two(1)\n",
    "fn one(a) { a }\nlet result = one(1, 2)\n",
    "fn z() { 1 }\nlet result = z(1)\n",
    # recursion through each binding width
    "fn one(n) { if n == 0 { 0 } else { 1 + one(n - 1) } }\nlet result = one(30)\n",
    "fn two(n, acc) { if n == 0 { acc } else { two(n - 1, acc + n) } }\nlet result = two(30, 0)\n",
    "fn three(n, a, b) { if n == 0 { a + b } else { three(n - 1, b, a + b) } }\nlet result = three(30, 0, 1)\n",
])
def test_binding_widths_three_way(src):
    assert_three_way(src)


def test_arg_nodes_carry_the_call_line_and_the_parameter_name():
    src = "fn two(a, b) {\n a - b\n}\nlet result = two(9,\n 4)\n"
    interp, env, _ = run(src)
    r = env.get("result")
    call = r.inputs[0]
    assert call.op == "call" and call.detail == "two"
    sub = call.inputs[0]
    a, b = sub.inputs
    assert (a.op, a.detail, a.line) == ("arg", "a", 4)
    assert (b.op, b.detail, b.line) == ("arg", "b", 4)


# --- tail loops that switch bodies and widths -------------------------------

@pytest.mark.parametrize("src", [
    # 1-param body hands off to a 2-param body and back
    "fn a(n) { if n == 0 { 0 } else { b(n - 1, 1) } }\n"
    "fn b(n, k) { if n == 0 { k } else { a(n - 1) } }\nlet result = a(11)\n",
    # arity miss at the SECOND body of the loop
    "fn a(n) { b(n) }\nfn b(n, k) { k }\nlet result = a(1)\n",
    # arity miss deep in the loop
    "fn a(n) { if n == 0 { b(0) } else { a(n - 1) } }\nfn b(n, k) { k }\nlet result = a(9)\n",
    # the switched-to body is taller (a call in argument position)
    "fn id(x) { x }\nfn a(n) { if n == 0 { 0 } else { b(n - 1, 1) } }\n"
    "fn b(n, k) { if n == 0 { k } else { a(id(n - 1)) } }\nlet result = a(21)\n",
    # three widths in one loop
    "fn p1(n) { if n == 0 { 0 } else { p2(n - 1, 1) } }\n"
    "fn p2(n, k) { if n == 0 { k } else { p3(n - 1, k, 2) } }\n"
    "fn p3(n, k, m) { if n == 0 { k + m } else { p1(n - 1) } }\nlet result = p1(31)\n",
    # loop ending in a builtin call (the v0.9 `_wrap_ifs` shape)
    "fn a(n, acc) { if n == 0 { len(acc) } else { a(n - 1, push(acc, n)) } }\nlet result = a(12, [])\n",
])
def test_width_switching_tail_loops_three_way(src):
    assert_three_way(src)


def test_merged_call_names_follow_the_bodies_in_order():
    src = ("fn a(n) { if n == 0 { 0 } else { b(n - 1, 1) } }\n"
           "fn b(n, k) { if n == 0 { k } else { a(n - 1) } }\nlet result = a(11)\n")
    r = val(src)
    call = r.inputs[0]
    assert call.op == "call" and call.detail == "a/b" and call.count == 12


# --- state after a host exception inside a direct call ----------------------

def test_depth_is_restored_when_a_builtin_raises_inside_direct_recursion():
    interp = Interpreter()

    def boom(it, args, line):
        raise RuntimeError("boom")
    interp.globals.define("boom", leaf("fn", "boom", 0, Builtin("boom", 0, boom)))
    env = Env(interp.globals)
    program = parse("fn f(n) { if n == 0 { boom() } else { f(n - 1) + 1 } }\n"
                    "let x = f(5)\nlet y = f(0) rescue 3\n")
    interp.exec_stmt(program.stmts[0], env)
    with pytest.raises(RuntimeError):
        interp.exec_stmt(program.stmts[1], env)
    assert interp.depth == 0
    # the next statement re-measures its budget and runs normally
    hits = interp.direct_hits
    interp.exec_stmt(parse("fn g(n) { if n == 0 { 0 } else { g(n - 1) + 1 } }\n"
                           "let z = g(40)\n").stmts[0], env)
    interp.exec_stmt(parse("let z = g(40)\n").stmts[0], env)
    assert env.get("z").value == 40 and interp.depth == 0
    assert interp.direct_hits > hits and interp.direct_fallbacks == 0


def test_peak_depth_and_depth_miss_unchanged_by_the_load_once_rewrite():
    src = "fn f(n) { if n == 0 { 0 } else { f(n - 1) + 1 } }\nlet result = f(30)\n"
    for kw in ({}, {"direct": False}, {"fast": False}):
        interp, env, _ = run(src, **kw)
        assert interp.peak_depth == 31 and interp.depth == 0
    # the depth miss reports the depth at the failing call, all modes
    assert_three_way(src, max_depth=10)
    r = val(src, max_depth=10)
    assert isinstance(r.value, Miss)
    assert "recursion too deep in f (depth 10)" in r.value.reasons[0]


# --- the bench drivers ------------------------------------------------------

@pytest.mark.whence_slow
def test_minof_runs_a_bench_in_a_fresh_process():
    out = subprocess.run([sys.executable, os.path.join(ROOT, "bench", "minof.py"),
                          "-n", "1", "fib20 direct"], capture_output=True,
                         text=True, timeout=60).stdout
    assert out.startswith("fib20 direct") and "us/call" in out and "result=6765" in out


@pytest.mark.whence_slow
def test_reserve_probe_finds_a_need_below_the_current_reserve():
    sys.path.insert(0, os.path.join(ROOT, "bench"))
    import reserve_probe as RP
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), "count.lang")
    with open(path, "w") as f:
        f.write("fn count(n) { if n == 0 { 0 } else { 1 + count(n - 1) } }\n"
                "let cnt = count(2000)\nprint(cnt)\n")
    need, line = RP.need(path, 6000, Interpreter.HOST_RESERVE)
    assert 1 <= need <= Interpreter.HOST_RESERVE, (need, line)
    assert line.startswith("OK fallbacks=")
    assert RP.probe(path, Interpreter.HOST_RESERVE, 6000).startswith("OK")
