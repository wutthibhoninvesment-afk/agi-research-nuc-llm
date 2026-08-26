"""v0.13 (round 128): `-> Type` return type annotations.

Design (see SPEC.md "v0.13"): unlike a v0.12 param guard (an ordinary
prepended `let` statement, re-evaluated every call), a return annotation
cannot be sugar in the same way — checking a value AFTER the body runs
needs the result back, which costs tail position if done as a wrapping
`if`. Instead the check happens at the ONE point every call path (the
trampoline's `_call_gen`, the compiled `_call_direct`, and both loops'
merged-tail-chain exit) already settles to a final `result` Prov, via one
new interpreter function (`_check_ret`) called from both places. The spec
itself is resolved ONCE per Closure at creation time (`_closure_ret`/
`_mk_closure`), not per call and not per body statement, so:

  - an untyped function is unaffected (`ret_spec is None`, one identity
    check per call, no new provenance node, no guest-visible frame);
  - a mismatch is an ordinary origin miss, same wording/op/single-input
    shape the `typed` builtin itself produces — `blame`/`rescue` treat it
    identically to a param-type miss;
  - a result that is ALREADY a miss is not re-wrapped (decision 2: misses
    propagate before inspection — a function that already failed does not
    also get a "wrong return type" gloss painted over its own miss);
  - tail position is exactly as `mark_tails` already computes it: the
    check applies ONCE, to the chain's final settled result, using the
    ORIGINALLY CALLED closure's own ret_spec — not whatever closure a
    tail loop bounces through along the way (`count_down` tail-calling
    itself, or `a` tail-calling a differently-typed `b`, must both check
    against `a`'s own contract, checked exactly once, not once per bounce).

Bug found and fixed by this round's own exploratory testing (not the
existing fuzzer, which does not generate type annotations at all yet): a
`-> Shape` naming a shape declared inside ANOTHER function's body parses
(the parser's `self.shapes` is not scope-aware — a pre-existing v0.12 gap
shared by param types) but is never bound in the env chain `_closure_ret`
walks at closure-creation time; the naive `env.get(name).payload` raised
AttributeError on the `None` — a real crash, violating the "never raises"
core discipline every other Whence error path upholds by construction.
Param types don't have this crash because a param guard's spec is an
ordinary `A.NameRef`, walked by the everyday evaluator, which already
turns a missing name into a `miss` instead of raising. Fixed with a
`_UnboundRetType` sentinel `_check_ret` turns into an ordinary miss —
never leaks to Whence code.
"""

import os
import sys

import pytest

from whence.interp import Interpreter
from whence.parser import parse, ParseError
from whence.values import Miss

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_v09 import run, val, assert_three_way  # noqa: E402


def all_ok(src, **kw):
    interp, env, out = run(src, **kw)
    bad = [c for c in interp.checks if not c["ok"]]
    assert bad == [], (bad, out)
    assert interp.checks, "no checks ran"
    return interp, env, out


def reasons_of(env, name):
    v = env.get(name)
    assert isinstance(v.value, Miss), (name, v.value)
    return v.value.reasons


# --- parser: `-> Type` accepted / rejected -----------------------------------

def test_no_return_type_is_none():
    prog = parse("fn f(a) { a }\n")
    assert prog.stmts[0].ret_type is None


def test_return_type_primitive_is_a_str_spec():
    prog = parse("fn f(a) -> num { a }\n")
    rt = prog.stmts[0].ret_type
    assert rt.__class__.__name__ == "Str" and rt.value == "num"


def test_return_type_shape_is_a_nameref_spec():
    prog = parse("shape Point = @{x: num}\nfn f() -> Point { @{x: 1} }\n")
    rt = prog.stmts[1].ret_type
    assert rt.__class__.__name__ == "NameRef" and rt.name == "Point"


def test_anonymous_fn_return_type_parses():
    prog = parse("let g = fn(a) -> num { a }\n")
    fn_expr = prog.stmts[0].expr
    assert fn_expr.ret_type.value == "num"


def test_fn_keyword_usable_as_a_return_type_tag():
    prog = parse("fn apply(f: fn, x: num) -> fn { f }\n")
    assert prog.stmts[0].ret_type.value == "fn"


def test_unknown_return_type_is_a_parse_error():
    with pytest.raises(ParseError, match="unknown type"):
        parse("fn f() -> bogus { 1 }\n")


def test_return_type_does_not_touch_the_runtime_param_list():
    prog = parse("fn f(a, b) -> num { a + b }\n")
    fn = prog.stmts[0]
    assert fn.params == ["a", "b"]
    kinds = [s.__class__.__name__ for s in fn.body.stmts]
    assert kinds == ["ExprStmt"]        # no guard prepended for the return


def test_return_type_composes_with_param_types():
    prog = parse("fn f(a: num) -> num { a }\n")
    fn = prog.stmts[0]
    kinds = [s.__class__.__name__ for s in fn.body.stmts]
    assert kinds == ["Let", "ExprStmt"]      # the param guard is untouched
    assert fn.ret_type.value == "num"


# --- interpreter: pass / mismatch, every primitive tag -----------------------

PRIMITIVE_CASES = [
    ("num", "3", True), ("num", '"3"', False),
    ("str", '"hi"', True), ("str", "3", False),
    ("bool", "true", True), ("bool", "1", False),
    ("list", "[1, 2]", True), ("list", '"[]"', False),
    ("record", "@{x: 1}", True), ("record", "3", False),
    ("fn", "fn(a) { a }", True), ("fn", "3", False),
    ("any", "3", True), ("any", '"x"', True),
]


@pytest.mark.parametrize("tag,expr,expected", PRIMITIVE_CASES)
def test_return_type_every_primitive_tag(tag, expr, expected):
    src = 'fn f() -> %s { %s }\nlet r = f()\n' % (tag, expr)
    interp, env, out = run(src)
    r = env.get("r")
    if expected:
        assert not isinstance(r.value, Miss), r.value
    else:
        assert isinstance(r.value, Miss)
        assert "return value of f" in r.value.reasons[0]
        assert "expected %s" % tag in r.value.reasons[0]


def test_any_return_type_always_passes_but_still_runs_the_check():
    # `any` always matches but is still a real check; only the fully
    # untyped (no `->` at all) case is a true no-op, asserted by the
    # parser test above (no extra statement, ret_spec stays None).
    interp, env, out = run('fn f(a) -> any { a + 1 }\nlet r = f(1)\n')
    assert env.get("r").value == 2


def test_shape_return_type_structural():
    src = ('shape Point = @{x: num, y: num}\n'
          'fn origin() -> Point { @{x: 0, y: 0} }\n'
          'fn bad() -> Point { @{x: 0} }\n'
          'let p = origin()\nlet q = bad()\n')
    interp, env, out = run(src)
    assert not isinstance(env.get("p").value, Miss)
    assert isinstance(env.get("q").value, Miss)
    assert "expected Point" in env.get("q").value.reasons[0]


def test_shape_return_type_extra_fields_are_ignored():
    src = ('shape Point = @{x: num}\n'
          'fn f() -> Point { @{x: 1, y: 2} }\nlet r = f()\n')
    assert not isinstance(val(src), Miss)


def test_nested_shape_return_type():
    src = ('shape Point = @{x: num, y: num}\n'
          'shape Line = @{a: Point, b: Point}\n'
          'fn f() -> Line { @{a: @{x:0,y:0}, b: @{x:1,y:1}} }\n'
          'fn g() -> Line { @{a: @{x:0}, b: @{x:1,y:1}} }\n'
          'let good = f()\nlet bad = g()\n')
    interp, env, out = run(src)
    assert not isinstance(env.get("good").value, Miss)
    assert isinstance(env.get("bad").value, Miss)


# --- a mismatch is an ordinary, origin miss -----------------------------------

def test_mismatch_message_names_the_function():
    src = 'fn double(x) -> num { "not a number" }\nlet r = double(5)\n'
    interp, env, out = run(src)
    reasons = reasons_of(env, "r")
    assert reasons[0].startswith("return value of double expected num, got str")


def test_anonymous_return_mismatch_has_no_function_name():
    src = 'let g = fn(x) -> num { "x" }\nlet r = g(1)\n'
    interp, env, out = run(src)
    assert env.get("r").value.reasons[0].startswith(
        "return value expected num, got str")


def test_return_mismatch_rescues_like_any_other_miss():
    interp, env, out = all_ok(
        'fn f() -> num { "x" }\n'
        'let total = f() rescue -1\n'
        'check "rescue recovers a return-type miss": total == -1\n')


def test_blame_finds_the_call_that_rejected_the_return():
    interp, env, out = run('fn f() -> num { "x" }\nlet r = f()\nlet b = blame(r)\n')
    bl = env.get("b").value.to_list()
    assert len(bl) == 1
    assert bl[0].value.fields["op"].value == "typed"
    assert bl[0].value.fields["detail"].value == "return value of f"


def test_a_body_that_already_misses_is_not_double_wrapped():
    # the body itself fails (unbound name) before ever producing a value
    # to type-check; the ORIGINAL miss propagates, no "typed" node added.
    interp, env, out = run('fn f() -> num { nope }\nlet r = f()\n')
    r = env.get("r")
    assert isinstance(r.value, Miss)
    assert "unbound name 'nope'" in r.value.reasons[0]
    assert "return value" not in r.value.reasons[0]


def test_param_type_miss_flows_through_untouched_by_return_check():
    src = 'fn f(a: num) -> num { a }\nlet r = f("x")\n'
    interp, env, out = run(src)
    r = env.get("r")
    assert isinstance(r.value, Miss)
    assert r.value.reasons[0].startswith("parameter 'a' of f expected num")


# --- tail position: checked once, against the ORIGINALLY called closure ------

def test_typed_return_tail_recursion_stays_one_frame():
    interp, env, out = run(
        'fn count_down(n) -> num {\n'
        '  if n <= 0 { 0 } else { count_down(n - 1) }\n'
        '}\n'
        'let r = count_down(20000)\n', max_depth=50)
    assert env.get("r").value == 0
    assert interp.peak_depth == 1
    assert interp.tail_calls == 20000


def test_typed_return_tail_recursion_mismatch_after_many_bounces():
    interp, env, out = run(
        'fn count_down(n) -> num {\n'
        '  if n <= 0 { "done" } else { count_down(n - 1) }\n'
        '}\n'
        'let r = count_down(5000)\n', max_depth=50)
    assert isinstance(env.get("r").value, Miss)
    assert interp.peak_depth == 1        # the check itself costs no depth
    assert env.get("r").value.reasons[0].startswith(
        "return value of count_down expected num, got str")


def test_mutual_tail_call_checks_against_the_caller_not_the_callee():
    # `a` tail-calls `b`; `b` has no return type, `a` demands num. The
    # merged tail chain must check the settled result against `a`'s OWN
    # contract, not silently adopt whatever (or no) contract `b` has.
    src = (
        'fn b(n) {\n'
        '  if n <= 0 { "done" } else { b(n - 1) }\n'
        '}\n'
        'fn a(n) -> num {\n'
        '  b(n)\n'
        '}\n'
        'let r = a(5)\n')
    interp, env, out = run(src, max_depth=50)
    r = env.get("r")
    assert isinstance(r.value, Miss)
    assert r.value.reasons[0].startswith("return value of a expected num")


def test_mutual_tail_call_passes_when_the_settled_value_matches():
    src = (
        'fn b(n) {\n'
        '  if n <= 0 { 0 } else { b(n - 1) }\n'
        '}\n'
        'fn a(n) -> num {\n'
        '  b(n)\n'
        '}\n'
        'let r = a(5)\n')
    interp, env, out = run(src, max_depth=50)
    assert env.get("r").value == 0


def test_non_tail_recursion_checks_every_frame_independently():
    # the base case violates its own contract; every enclosing `*` frame
    # sees an already-missed operand and propagates (no re-check, no
    # double "typed" wrapping at the outer frames).
    src = ('fn weird(n) -> num {\n'
          '  if n <= 0 { "oops" } else { n * weird(n - 1) }\n'
          '}\n'
          'let r = weird(3)\n')
    interp, env, out = run(src, max_depth=50)
    r = env.get("r")
    assert isinstance(r.value, Miss)
    reasons = r.value.reasons
    assert any("return value of weird expected num, got str" in x
               for x in reasons)


# --- the crash bug: an out-of-scope shape name --------------------------------

def test_return_type_naming_an_out_of_scope_local_shape_is_a_miss_not_a_crash():
    src = ('fn make() { shape Local = @{x: num} 1 }\n'
          'fn f() -> Local { @{x: 1} }\n'
          'let r = f()\n')
    interp, env, out = run(src)     # must not raise
    r = env.get("r")
    assert isinstance(r.value, Miss)
    assert "not in scope" in r.value.reasons[0]
    assert "Local" in r.value.reasons[0]


def test_out_of_scope_shape_return_type_every_call_misses_the_same_way():
    src = ('fn make() { shape Local = @{x: num} 1 }\n'
          'fn f() -> Local { @{x: 1} }\n'
          'let a = f()\nlet b = f()\n')
    interp, env, out = run(src)
    strip_line = lambda r: r.split(" (line")[0]
    a_reasons = [strip_line(r) for r in env.get("a").value.reasons]
    b_reasons = [strip_line(r) for r in env.get("b").value.reasons]
    assert a_reasons == b_reasons


def test_param_type_naming_the_same_out_of_scope_shape_already_missed_safely():
    # the pre-existing (v0.12) param-type side of the identical scoping
    # gap: it already degrades to a miss via the ordinary NameRef walk,
    # so this is a regression pin, not a new fix.
    src = ('fn make() { shape Local = @{x: num} 1 }\n'
          'fn g(p: Local) { p }\n'
          'let r = g(@{x: 1})\n')
    interp, env, out = run(src)     # must not raise
    r = env.get("r")
    assert isinstance(r.value, Miss)
    assert "unbound name 'Local'" in r.value.reasons[0]


# --- three-way differential (fast / direct / slow) ---------------------------

def test_three_way_typed_return_pass():
    assert_three_way('fn f() -> num { 2 + 3 }\nlet result = f()\n')


def test_three_way_typed_return_mismatch():
    assert_three_way('fn f() -> num { "x" }\nlet result = f()\n')


def test_three_way_shape_return():
    assert_three_way(
        'shape Point = @{x: num, y: num}\n'
        'fn f() -> Point { @{x: 1, y: 2} }\n'
        'let result = f()\n')


def test_three_way_typed_return_tail_recursion():
    assert_three_way(
        'fn count_down(n) -> num {\n'
        '  if n <= 0 { 0 } else { count_down(n - 1) }\n'
        '}\n'
        'let result = count_down(3000)\n')


def test_three_way_mutual_tail_call_return_check():
    assert_three_way(
        'fn b(n) {\n'
        '  if n <= 0 { "done" } else { b(n - 1) }\n'
        '}\n'
        'fn a(n) -> num {\n'
        '  b(n)\n'
        '}\n'
        'let result = a(200)\n')


def test_three_way_non_tail_recursion_return_check():
    assert_three_way(
        'fn weird(n) -> num {\n'
        '  if n <= 0 { "oops" } else { n * weird(n - 1) }\n'
        '}\n'
        'let result = weird(5)\n')


def test_three_way_unbound_shape_return_type_does_not_crash_any_mode():
    assert_three_way(
        'fn make() { shape Local = @{x: num} 1 }\n'
        'fn f() -> Local { @{x: 1} }\n'
        'let result = f()\n')
