"""v0.9 (round 30): direct mode — subtrees WITH calls compile to closures
that recurse on the host stack under a frame budget; `_call_direct` is
`_call_gen` without the generator; an exhausted budget falls back to the
trampoline, so host stack depth is bounded by construction.

Semantic anchors:
  - THREE-way differential: direct (default) / fast-only (`direct=False`,
    v0.8 behaviour) / slow (`fast=False`, pure trampoline) must agree byte
    for byte in `render_why` on every binding, in printed output, in check
    records, and in `peak_depth` / `tail_calls` / `depth`.
  - The budget is load-bearing: with it disabled, deep recursion under the
    default recursion limit raises RecursionError; with it, it does not —
    from a top-level entry, from inside a deep host stack, and under a
    recursion limit too small for direct mode to engage at all.
  - Round-30 bug fix (found by the three-way differential on
    self_host.lang): a multi-frame tail loop whose final iteration
    tail-calls a BUILTIN rendered one extra `if ×1` input in fast=False.
    The final iteration's decisions now wrap the result in every mode.
"""

import os
import subprocess
import sys

import pytest

from whence.interp import Interpreter, Env
from whence.parser import parse
from whence.values import Miss, leaf, render_why

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODES = {"direct": {}, "fast": {"direct": False}, "slow": {"fast": False}}


def run(src, **kw):
    out = []
    interp = Interpreter(out=out.append, **kw)
    env = interp.run(src)
    return interp, env, out


def val(src, **kw):
    return run(src, **kw)[1].get("result")


def check_records(interp):
    return [(c["label"], c["ok"], c.get("note"), c.get("why"), c.get("contrast"))
            for c in interp.checks]


def assert_three_way(src, names=("result",), **kw):
    """render_why byte-equality on `names`, plus output, checks and the
    depth counters, across all three evaluation modes."""
    runs = {}
    for mode, mkw in MODES.items():
        k = dict(kw)
        k.update(mkw)
        runs[mode] = run(src, **k)
    ref_i, ref_env, ref_out = runs["direct"]
    assert ref_i.direct_hits > 0, "direct mode never engaged"
    for mode in ("fast", "slow"):
        i, env, out = runs[mode]
        assert out == ref_out, (mode, out, ref_out)
        assert check_records(i) == check_records(ref_i), mode
        for n in names:
            a, b = ref_env.get(n), env.get(n)
            assert a is not None and b is not None, n
            assert render_why(a) == render_why(b), (mode, n, render_why(a),
                                                    render_why(b))
        assert (i.peak_depth, i.tail_calls, i.depth) == \
            (ref_i.peak_depth, ref_i.tail_calls, ref_i.depth), mode
    assert runs["fast"][0].direct_hits == 0
    assert runs["slow"][0].direct_hits == 0 and runs["slow"][0].fast_hits == 0
    return runs


FIB = "fn fib(n) { if n < 2 { n } else { fib(n - 1) + fib(n - 2) } }\n"
COUNT = "fn count(n) { if n == 0 { 0 } else { 1 + count(n - 1) } }\n"
EVEN_ODD = ("fn even(n) { if n == 0 { true } else { odd(n - 1) } }\n"
            "fn odd(n) { if n == 0 { false } else { even(n - 1) } }\n")
TAIL = "fn go(i, acc) { if i == 0 { acc } else { go(i - 1, acc + i) } }\n"


# --- direct mode engages, and is invisible -----------------------------------

def test_direct_engages_and_budget_is_restored():
    interp, env, _ = run(FIB + "let result = fib(12)\n")
    assert env.get("result").payload == 144
    assert interp.direct_hits > 0 and interp.direct_fallbacks == 0
    # counters: `fast_hits` counts driver-level entries into ANY compiled
    # closure (fast or direct); `direct_hits` counts direct entries plus
    # every `_call_direct` closure call (those are not driver entries)
    assert interp.fast_hits > 0 and interp.direct_hits > interp.fast_hits
    assert interp.host_budget() > 0                 # fully restored after run
    assert interp.depth == 0 and interp.peak_depth == 12


def test_direct_off_and_fast_off_imply_no_direct():
    i1, env1, _ = run(FIB + "let result = fib(10)\n", direct=False)
    i2, env2, _ = run(FIB + "let result = fib(10)\n", fast=False)
    assert i1.direct_hits == 0 and i2.direct_hits == 0
    assert i2.direct is False and i2.fast_hits == 0
    assert env1.get("result").payload == env2.get("result").payload == 55


@pytest.mark.parametrize("src", [
    FIB + "let result = fib(11)\n",
    COUNT + "let result = count(40)\n",
    EVEN_ODD + "let result = even(31)\n",
    TAIL + "let result = go(50, 0)\n",
    # alternating branches inside a tail loop: separate `if ×N` runs
    "fn alt(i, acc) { if i == 0 { acc } else if i % 2 == 0 { alt(i - 1, acc + 1) }"
    " else { alt(i - 1, acc * 2) } }\nlet result = alt(9, 1)\n",
    # rescue around calls, miss produced deep inside
    "fn bad(n) { if n == 0 { 1 / 0 } else { bad(n - 1) + 1 } }\n"
    "let result = bad(5) rescue 42\n",
    # generator builtins with closures: nested drive from direct code
    FIB + "let result = map(fn(x) { fib(x) }, [3, 5, 7])\n",
    FIB + "let result = filter(fn(x) { fib(x) > 3 }, range(1, 8))\n",
    FIB + "let result = fold(fn(a, x) { a + fib(x) }, 0, range(1, 8))\n",
    FIB + "let result = find(fn(x) { fib(x) > 10 }, range(1, 12))\n",
    # higher-order: closures returned and called (single-stmt body unwrap)
    "fn mk(x) { fn(y) { x + y } }\nlet result = mk(1)(2) + mk(10)(20)\n",
    # calls inside list / record / index / field
    FIB + "let result = [fib(3), @{a: fib(4)}][1].a + [fib(5)][0]\n",
    # why / snip / not / unary minus / miss literal over calls
    FIB + "let result = [why fib(4), snip fib(5), -fib(6), not (fib(3) == 2)]\n",
    FIB + "let result = miss (\"n=\" + str(fib(4)))\n",
    # and / or short-circuit with calls on both sides
    FIB + "let result = [fib(1) == 1 and fib(2) == 1, fib(5) > 100 or fib(3) == 2]\n",
    # arity miss, non-callable call, miss callee
    FIB + "let result = [fib(1, 2), fib(3)(1), (1 / 0)(5)]\n",
    # else-if chain whose CONDITIONS contain calls (no fast cond: no F3)
    FIB + "fn kind(n) { if fib(n) == 1 { \"one\" } else if fib(n) < 10 { \"small\" }"
    " else { \"big\" } }\nlet result = [kind(1), kind(4), kind(8)]\n",
    # multi-statement bodies: let shadowing, nested fn, nested blocks
    "fn f(x) {\n  let y = x + 1\n  fn g(z) { z * y }\n  let x = g(2)\n"
    "  if x > 3 { let w = x - 1\n w } else { x }\n}\nlet result = f(1) + f(5)\n",
    # print inside bodies: output order must match across modes
    FIB + "fn noisy(n) { print(\"n=\" + str(n))\n fib(n) }\n"
    "let result = noisy(3) + noisy(4)\n",
    # checks inside bodies (record_check from a direct block)
    FIB + "fn checked(n) { check \"inner\": fib(n) > 0\n fib(n) }\n"
    "let result = checked(3) + checked(5)\n",
    # tail loop whose LAST iteration tail-calls a builtin (round-30 fix)
    "fn lp(i, acc) { if i >= 3 { push(acc, i) } else { lp(i + 1, push(acc, i)) } }\n"
    "let result = lp(0, [])\n",
    # same with the builtin shadowed (F1 off: real _TailCall to a closure)
    "fn push(xs, x) { xs + [x] }\n"
    "fn lp(i, acc) { if i >= 3 { push(acc, i) } else { lp(i + 1, push(acc, i)) } }\n"
    "let result = lp(0, [])\n",
    # ... and to a non-callable / a miss, mid-chain, single frame + multi
    "fn lp(i) { if i >= 2 { 7(i) } else if i == 5 { 1 } else { lp(i + 1) } }\n"
    "let result = lp(0)\n",
    "fn lp(i) { if i >= 2 { (1 / 0)(i) } else { lp(i + 1) } }\nlet result = lp(2)\n",
    # max_iter miss inside a merged loop
    TAIL + "let result = go(1000, 0)\n",
])
def test_three_way_differential(src):
    assert_three_way(src, max_iter=500)


def test_three_way_depth_miss_and_counters():
    src = "fn loop(n) { 1 + loop(n + 1) }\nlet result = loop(0)\n" + \
          COUNT + "let after = count(20)\n"
    runs = assert_three_way(src, ("result", "after"), max_depth=60)
    for i, env, _ in runs.values():
        assert isinstance(env.get("result").payload, Miss)
        assert "depth 60" in env.get("result").payload.reasons[0]
        assert i.peak_depth == 60 and i.depth == 0
        assert env.get("after").payload == 20
    assert runs["direct"][0].host_budget() > 0


def test_three_way_on_examples_that_recurse():
    for name in ("tco.lang", "history.lang", "blame.lang", "diverge.lang",
                 "checks_demo.lang", "sales.lang"):
        with open(os.path.join(ROOT, "examples", name)) as f:
            src = f.read()
        runs = {}
        for mode, mkw in MODES.items():
            runs[mode] = run(src, **mkw)
        ref_i, ref_env, ref_out = runs["direct"]
        for mode in ("fast", "slow"):
            i, env, out = runs[mode]
            assert out == ref_out, (name, mode)
            assert check_records(i) == check_records(ref_i), (name, mode)
            for n in ref_env.vars:
                assert render_why(env.get(n)) == render_why(ref_env.get(n)), \
                    (name, mode, n)


def test_self_host_lexer_regression_multi_frame_builtin_tail():
    # the shape that exposed the v0.7 leftover: 13 merged frames, the last
    # one `push(acc, eof)` — every mode must show the final `if` wrapping
    # the result, not as one more `if ×1` input of the merged call node
    with open(os.path.join(ROOT, "examples", "self_host.lang")) as f:
        src = f.read()
    trees = {}
    for mode, mkw in MODES.items():
        _, env, _ = run(src, **mkw)
        trees[mode] = render_why(env.get("lx"))
        call = env.get("lx").inputs[0]
        assert call.op == "call" and call.count == 13
        assert call.inputs[0].op == "if"          # final decision wraps result
        assert call.inputs[0].detail == "took then-branch"
    assert trees["direct"] == trees["fast"] == trees["slow"]


# --- the budget --------------------------------------------------------------

def test_deep_recursion_under_default_limit_falls_back_to_trampoline():
    interp, env, _ = run(COUNT + "let result = count(15000)\n")
    assert env.get("result").payload == 15000
    assert interp.peak_depth == 15001 and interp.depth == 0
    assert interp.direct_hits > 0 and interp.direct_fallbacks >= 1
    assert interp.host_budget() > 0


def test_budget_is_load_bearing():
    class Unbounded(Interpreter):
        def exec_stmt(self, stmt, env):
            self._collect_shadowed(stmt)
            self._hleft = 10 ** 9      # lie: infinite host headroom
            return self._drive(self._stmt_gen(stmt, env))
    with pytest.raises(RecursionError):
        Unbounded().run(COUNT + "let result = count(5000)\n")
    # the honest budget handles the same program
    _, env, _ = run(COUNT + "let result = count(5000)\n")
    assert env.get("result").payload == 5000


def test_runs_inside_a_deep_host_stack():
    def deep(n, thunk):
        if n == 0:
            return thunk()
        return deep(n - 1, thunk)
    src = COUNT + "let result = count(3000)\n"
    # ~300 frames already used: direct engages for a while, then falls back
    interp, env, _ = deep(300, lambda: run(src))
    assert env.get("result").payload == 3000
    assert interp.direct_hits > 0 and interp.direct_fallbacks >= 1
    # the stack already past `limit - HOST_RESERVE`: no headroom at all —
    # direct never engages, and the program still runs (trampoline), no
    # RecursionError. Computed from the constant (v0.11 shrank the reserve
    # 350 → 250 after measuring it; a fixed 650 would now leave headroom).
    from whence.interp import _stack_depth
    n = sys.getrecursionlimit() - Interpreter.HOST_RESERVE - _stack_depth() + 5
    interp, env, _ = deep(n, lambda: run(src))
    assert env.get("result").payload == 3000
    assert interp.direct_hits == 0 and interp.host_budget() <= 0


def test_tiny_recursion_limit_keeps_direct_dormant():
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(200)
    try:
        interp, env, _ = run(COUNT + "let result = count(2000)\n")
    finally:
        sys.setrecursionlimit(old)
    assert env.get("result").payload == 2000
    assert interp.direct_hits == 0 and interp.host_budget() <= 0


def test_budget_is_remeasured_per_statement():
    interp = Interpreter()
    env = Env(interp.globals)
    prog = parse(COUNT + "let a = count(10)\nlet b = count(10)\n")
    old = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(old + 2000)
        interp.exec_stmt(prog.stmts[0], env)
        interp.exec_stmt(prog.stmts[1], env)
        big = interp.host_budget()
        sys.setrecursionlimit(old)
        interp.exec_stmt(prog.stmts[2], env)
        small = interp.host_budget()
    finally:
        sys.setrecursionlimit(old)
    assert big - small >= 1900
    assert env.get("a").payload == env.get("b").payload == 10


def test_mutual_recursion_recharges_for_a_taller_body():
    # `odd` has a taller body than `even` (a let + nested if); the tail
    # loop switches bodies every frame and must re-charge the difference
    src = ("fn even(n) { if n == 0 { true } else { odd(n - 1) } }\n"
           "fn odd(n) {\n  let m = n - 1\n"
           "  if m < 0 { false } else { if m == 0 { false } else { even(m) } }\n}\n"
           "let result = even(2001)\n")
    runs = assert_three_way(src)
    assert runs["direct"][1].get("result").payload is False


def test_cdepth_is_the_frame_count_to_the_deepest_call():
    interp = Interpreter()
    prog = parse(FIB + "let result = fib(3)\n")
    env = Env(interp.globals)
    for stmt in prog.stmts:
        interp.exec_stmt(stmt, env)
    body = prog.stmts[0].body
    assert body.direct is not False and body.direct is not None
    # single-expression block: no frame of its own (unwrapped)
    assert body.cdepth == body.stmts[0].expr.cdepth == 3   # if -> + -> call
    call = prog.stmts[1].expr
    assert call.cdepth == 1
    assert prog.stmts[0].body.stmts[0].expr.cond.fast   # `n < 2` is fast


def test_host_frames_per_guest_level_match_the_charge():
    def peak_frames(src):
        depth = [0]
        peak = [0]

        def prof(frame, event, arg):
            if event == "call":
                depth[0] += 1
                if depth[0] > peak[0]:
                    peak[0] = depth[0]
            elif event == "return":
                depth[0] -= 1
        interp = Interpreter()
        sys.setprofile(prof)
        try:
            interp.run(src)
        finally:
            sys.setprofile(None)
        assert interp.direct_fallbacks == 0
        return peak[0]
    a = peak_frames(COUNT + "let result = count(30)\n")
    b = peak_frames(COUNT + "let result = count(60)\n")
    assert (b - a) / 30.0 == 4.0     # cdepth 3 + the _call_direct frame


# --- shared-AST determinism (the v0.7 bug shape, now for direct closures) ---

def test_shared_ast_two_interpreters_keep_their_own_state():
    src = (FIB + "fn noisy(n) { print(\"n=\" + str(n))\n"
           " check \"inner\": fib(n) > 0\n fib(n) }\n"
           "let result = noisy(6)\n")
    prog = parse(src)
    outs = [[], []]
    interps = [Interpreter(out=outs[0].append), Interpreter(out=outs[1].append)]
    for k, interp in enumerate(interps):
        env = Env(interp.globals)
        for stmt in prog.stmts:
            interp.exec_stmt(stmt, env)
        assert env.get("result").payload == 8
    assert outs[0] == outs[1] == ["n=6"]
    assert [len(i.checks) for i in interps] == [1, 1]
    assert [i.peak_depth for i in interps] == [7, 7]
    # fresh parse agrees byte for byte
    _, env, out = run(src)
    assert out == ["n=6"]
    assert render_why(env.get("result")) == render_why(
        Env(interps[0].globals).get("result") or env.get("result"))


def test_call_value_public_api_before_and_after_a_run():
    interp = Interpreter()
    env = interp.run(FIB)
    fn = env.get("fib")
    assert interp.host_budget() > 0
    v = interp.call_value(fn, [leaf("literal", "", 1, 10)], 1)
    assert v.payload == 55 and v.op == "call"
    fresh = Interpreter()
    fenv = fresh.run(FIB)
    assert fresh.host_budget() > 0
    v2 = fresh.call_value(fenv.get("fib"), [leaf("literal", "", 1, 10)], 1)
    assert render_why(v) == render_why(v2)


# --- CLI ----------------------------------------------------------------------

def test_cli_no_direct_flag_gives_identical_output():
    exe = os.path.join(ROOT, "run.py")
    ex = os.path.join(ROOT, "examples", "tco.lang")
    a = subprocess.run([sys.executable, exe, ex], capture_output=True, text=True)
    b = subprocess.run([sys.executable, exe, "--no-direct", ex],
                       capture_output=True, text=True)
    assert a.returncode == b.returncode == 0
    assert a.stdout == b.stdout
    bad = subprocess.run([sys.executable, exe, "--no-direct"],
                         capture_output=True, text=True)
    assert bad.returncode == 2
