"""v0.8 (round 26): F3 — else-if chains with fast conditions are walked
inline by `_if_chain` (one driver step per chain, not one eval_If generator
per level); F3b — eval_Block runs every statement kind inline instead of
pushing a `_stmt_gen` generator per Let/Check/FnDef.

Semantic anchors:
  - Both changes are invisible: fast=True and fast=False agree node for
    node (render_why equality, not just payload equality) on every chain
    shape: fast bottom, trampoline bottom, tail-call bottom, miss-valued
    condition mid-chain, merged `if ×N` runs in tail loops.
  - Level-1 `if` (no chain) takes the pre-F3 straight-line path; nothing
    about single-if programs changes.
"""

from whence.interp import Interpreter
from whence.parser import parse
from whence.values import Miss, diverge, render_why


def run(src, **kw):
    interp = Interpreter(**kw)
    env = interp.run(src)
    return interp, env


def val(src, **kw):
    return run(src, **kw)[1].get("result")


def is_miss(v):
    return isinstance(v.payload, Miss)


def assert_trees_identical(src, names):
    """Stronger than diverge()==[]: the rendered why-trees (op, detail,
    line, structure) must be byte-identical between the two modes."""
    _, fast_env = run(src)
    _, slow_env = run(src, fast=False)
    for name in names:
        a, b = fast_env.get(name), slow_env.get(name)
        assert render_why(a) == render_why(b), name
        assert diverge(a, b) == [], (name, diverge(a, b))


CHAIN = ('fn kindof(k) {\n'
         '  if k == "a" { 1 }\n'
         '  else if k == "b" { 2 }\n'
         '  else if k == "c" { 3 }\n'
         '  else if k == "d" { 4 }\n'
         '  else { 0 }\n'
         '}\n')


# --- F3: chain with a fast bottom -------------------------------------------

def test_chain_fast_bottom_all_arms():
    src = (CHAIN +
           'let a = kindof("a")\nlet b = kindof("b")\n'
           'let c = kindof("c")\nlet d = kindof("d")\nlet e = kindof("x")\n')
    assert_trees_identical(src, "abcde")
    _, env = run(src)
    assert [env.get(n).payload for n in "abcde"] == [1, 2, 3, 4, 0]


def test_chain_provenance_has_every_decision():
    # walking the chain inline must keep ONE `if` node per level walked
    _, env = run(CHAIN + 'let result = kindof("c")\n')
    tree = render_why(env.get("result"))
    assert tree.count("took else-branch") == 2   # fell past "a" and "b"
    assert tree.count("took then-branch") == 1   # took "c"


def test_chain_trampoline_bottom():
    # innermost taken branch contains a user call: _if_chain_gen path
    src = ('fn double(x) { x + x }\n'
           'fn pick(k) {\n'
           '  if k == "a" { 1 }\n'
           '  else if k == "b" { double(21) }\n'
           '  else { 0 }\n'
           '}\n'
           'let result = pick("b")\nlet other = pick("z")\n')
    assert_trees_identical(src, ["result", "other"])
    assert val(src).payload == 42


def test_chain_multistmt_block_bottom():
    # innermost branch is a multi-statement block (never unwrapped)
    src = ('fn f(k) {\n'
           '  if k == "a" { 1 }\n'
           '  else if k == "b" {\n'
           '    let t = k + k\n'
           '    len(t)\n'
           '  }\n'
           '  else { 0 }\n'
           '}\n'
           'let result = f("b")\n')
    assert_trees_identical(src, ["result"])
    assert val(src).payload == 2


def test_chain_miss_condition_mid_chain():
    # the second condition compares a number with a record -> miss cond;
    # the walked chain must propagate it exactly like nested eval_If
    src = ('fn f(x) {\n'
           '  if x == "nope" { 1 }\n'
           '  else if x < 3 { 2 }\n'
           '  else { 3 }\n'
           '}\n'
           'let result = f(@{a: 1})\n')
    fast, slow = val(src), val(src, fast=False)
    assert is_miss(fast) and is_miss(slow)
    assert fast.payload.reasons == slow.payload.reasons
    assert_trees_identical(src, ["result"])


def test_chain_into_tail_loop_merges_ifs():
    # chain bottoms in a tail call: decisions must reach _call_gen's
    # run-length merge, identical to the slow path (`if … ×N` preserved)
    src = ('fn spin(n, acc) {\n'
           '  if n == 0 { acc }\n'
           '  else if n % 2 == 0 { spin(n - 1, acc + 2) }\n'
           '  else { spin(n - 1, acc + 1) }\n'
           '}\n'
           'let result = spin(6, 0)\n')
    assert_trees_identical(src, ["result"])
    assert val(src).payload == 9
    tree = render_why(val(src))
    assert "call spin ×7" in tree


def test_chain_tail_call_resolving_to_builtin():
    # deferred-if decisions on a tail call that resolves to a builtin
    # (the v0.7 lossiness fix) must also hold for walked chains
    src = ('fn f(k, xs) {\n'
           '  if k == "len" { len(xs) }\n'
           '  else if k == "head" { xs[0] }\n'
           '  else { 0 }\n'
           '}\n'
           'let result = f("len", [1, 2, 3])\n')
    assert_trees_identical(src, ["result"])
    assert val(src).payload == 3


def test_deep_chain():
    arms = "".join('  else if k == %d { %d }\n' % (i, i * 10)
                   for i in range(1, 12))
    src = ('fn f(k) {\n  if k == 0 { 0 }\n' + arms + '  else { 0 - 1 }\n}\n'
           'let result = f(11)\nlet other = f(99)\n')
    assert_trees_identical(src, ["result", "other"])
    _, env = run(src)
    assert env.get("result").payload == 110
    assert env.get("other").payload == -1


def test_single_if_unchanged():
    # level 1 stays on the straight-line path; fib-shaped code identical
    src = ('fn fib(n) { if n < 2 { n } else { fib(n - 1) + fib(n - 2) } }\n'
           'let result = fib(10)\n')
    assert_trees_identical(src, ["result"])
    assert val(src).payload == 55


# --- F3b: statements run inline in eval_Block --------------------------------

def test_block_let_inline_provenance():
    src = ('fn f(x) {\n'
           '  let a = x + 1\n'
           '  let b = f2(a)\n'
           '  a + b\n'
           '}\n'
           'fn f2(y) { y * 2 }\n'
           'let result = f(3)\n')
    assert_trees_identical(src, ["result"])
    assert val(src).payload == 12


def test_block_check_and_fndef_inline():
    # a check INSIDE a function body block and a nested fn definition both
    # execute through the inlined eval_Block arms
    src = ('fn outer(x) {\n'
           '  check "inside": x > 0\n'
           '  fn inner(y) { y + x }\n'
           '  inner(10)\n'
           '}\n'
           'let result = outer(5)\n')
    for fast in (True, False):
        interp, env = run(src, fast=fast)
        assert env.get("result").payload == 15
        assert [c["ok"] for c in interp.checks] == [True]
    assert_trees_identical(src, ["result"])


def test_block_check_failure_recorded_identically():
    src = ('fn f(x) {\n'
           '  check "boom": x > 100\n'
           '  x\n'
           '}\n'
           'let result = f(1)\n')
    fast_i, _ = run(src)
    slow_i, _ = run(src, fast=False)
    assert len(fast_i.checks) == len(slow_i.checks) == 1
    assert fast_i.checks[0]["ok"] is False
    assert fast_i.checks[0]["note"] == slow_i.checks[0]["note"]
    assert fast_i.checks[0]["why"] == slow_i.checks[0]["why"]
