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


# --- the out-of-scope shape name: a crash (round 128), then a miss, --------
# --- and since v0.18 (round 342) a parse error at the annotation itself ----
#
# Round 128 found a CRASH here and fixed the crash. What it left in place
# was the cause: the parser's shape table was file-global, so an annotation
# naming a shape whose block had closed was ACCEPTED, and the three ways
# that then went wrong were all deferred to run time and all different
# (`-> Local`: a `_UnboundRetType` miss per call; `p: Local`: an "unbound
# name" miss per call, different wording for the identical mistake; and a
# later shape's own FIELD spec: a silently miss-valued field, no miss at
# all until something read it). v0.18 makes the annotation itself the
# error, once, at parse time, with one sentence for all three.

SRC_OUT_OF_SCOPE_RET = ('fn make() { shape Local = @{x: num} 1 }\n'
                        'fn f() -> Local { @{x: 1} }\n'
                        'let r = f()\n')
SRC_OUT_OF_SCOPE_PARAM = ('fn make() { shape Local = @{x: num} 1 }\n'
                          'fn g(p: Local) { p }\n'
                          'let r = g(@{x: 1})\n')
SRC_OUT_OF_SCOPE_FIELD = ('fn make() { shape Local = @{x: num} 1 }\n'
                          'shape Wrap = @{inner: Local}\n'
                          'let r = 1\n')


@pytest.mark.parametrize("src", [SRC_OUT_OF_SCOPE_RET,
                                 SRC_OUT_OF_SCOPE_PARAM,
                                 SRC_OUT_OF_SCOPE_FIELD])
def test_out_of_scope_shape_in_any_annotation_position_is_one_parse_error(src):
    """v0.18: return type, parameter type and a shape's own field type are
    three routes into the same `parse_type`, and all three now refuse an
    out-of-scope shape identically. Before v0.18 they produced three
    DIFFERENT run-time outcomes from the same mistake."""
    with pytest.raises(ParseError) as e:
        parse(src)
    assert "type 'Local' is not in scope here" in str(e.value)


def test_out_of_scope_is_worded_differently_from_never_declared():
    """The two are genuinely different mistakes — a typo vs. a scope error —
    and `shapes_seen` exists only to tell them apart."""
    with pytest.raises(ParseError) as never:
        parse('fn f() -> Nope { 1 }\nlet r = 1\n')
    assert "unknown type 'Nope'" in str(never.value)
    with pytest.raises(ParseError) as closed:
        parse(SRC_OUT_OF_SCOPE_RET)
    assert "not in scope here" in str(closed.value)


def test_the_error_points_at_the_annotation_not_the_declaration():
    # line 2 is `fn f() -> Local ...`; the shape is declared on line 1.
    with pytest.raises(ParseError) as e:
        parse(SRC_OUT_OF_SCOPE_RET)
    assert e.value.line == 2


def test_a_local_shape_is_still_usable_inside_its_own_block():
    """The expressiveness v0.18 must NOT cost: a shape declared in a block
    is a perfectly good type for annotations in that same block, param and
    return alike. This is the case round 128 could not distinguish from
    the broken one."""
    all_ok('fn make() {\n'
           '  shape Local = @{x: num}\n'
           '  fn f(p: Local) -> Local { p }\n'
           '  check "local shape works": (f(@{x: 1})).x == 1\n'
           '  1\n'
           '}\n'
           'let r = make()\n')


def test_sibling_blocks_may_each_declare_the_same_shape_name():
    """A `let` may; before v0.18 a `shape` could not, because the table was
    one flat file-global dict. Nothing is shadowed here — the two blocks
    never see each other."""
    all_ok('fn a() {\n'
           '  shape S = @{x: num}\n'
           '  fn f(p: S) { p.x }\n'
           '  f(@{x: 1})\n'
           '}\n'
           'fn b() {\n'
           '  shape S = @{y: str}\n'
           '  fn g(p: S) { p.y }\n'
           '  g(@{y: "ok"})\n'
           '}\n'
           'check "sibling a": a() == 1\n'
           'check "sibling b": b() == "ok"\n')


def test_an_inner_block_may_shadow_an_outer_shape_name():
    all_ok('shape S = @{x: num}\n'
           'fn inner() {\n'
           '  shape S = @{y: str}\n'
           '  fn g(p: S) { p.y }\n'
           '  g(@{y: "ok"})\n'
           '}\n'
           'fn outer(p: S) { p.x }\n'
           'check "inner annotation means the inner shape": inner() == "ok"\n'
           'check "outer annotation still means the outer one": '
           'outer(@{x: 2}) == 2\n')


def test_redeclaring_a_shape_in_the_SAME_block_is_still_an_error():
    with pytest.raises(ParseError, match="already declared in this block"):
        parse('shape P = @{x: num}\nshape P = @{y: num}\nlet r = 1\n')
    with pytest.raises(ParseError, match="already declared in this block"):
        parse('fn f() {\n  shape P = @{x: num}\n  shape P = @{y: num}\n'
              '  1\n}\nlet r = 1\n')


def test_unbound_ret_type_sentinel_is_still_the_defensive_floor():
    """`_UnboundRetType` is unreachable from source text after v0.18 (the
    parser refuses the only annotation that could produce it), and is kept
    anyway: `_closure_ret` resolves a spec directly in Python, not through
    a Whence expression, so a `None` lookup there would raise rather than
    miss. Exercised directly, since no program can reach it."""
    from whence.interp import _UnboundRetType, _check_ret
    from whence.values import leaf
    v = leaf("literal", "1", 1, 1)
    out = _check_ret(v, _UnboundRetType("Local"), "return value of f", 7)
    assert isinstance(out.value, Miss)
    assert out.value.reasons[0].startswith(
        "return value of f: type 'Local' is not in scope here")
    # and a miss in still propagates unchanged, ahead of the sentinel
    m = _check_ret(mk_miss_for_test(), _UnboundRetType("Local"), "lbl", 7)
    assert list(m.value.reasons) == ["boom (line 1)"]


def mk_miss_for_test():
    from whence.interp import mk_miss
    return mk_miss("boom", 1, "literal", "x")


# --- the LATE-BINDING hazard v0.18 makes nameable (pre-existing, unfixed) ---
#
# v0.18 gives the parser an opinion about WHICH declaration an annotation
# names. The runtime has its own, and they can disagree: a param guard is a
# prepended `let p = typed(p, <NameRef>, …)` re-evaluated on every call, so
# its spec resolves in the CALL env — while a return spec is resolved once,
# at closure creation (`_closure_ret`), in the DEFINING env. A block env is
# one mutable dict that later statements keep adding to (that is what makes
# mutual recursion work, see `f_block`), so a binding added AFTER the
# annotation is still visible to a later call.
#
# These two tests pin the behaviour as it is, deliberately. They are not
# claims that it is right — see SPEC.md § v0.18 "the capture hazard" and
# the round-342 knowledge file for the fix direction (resolve a param spec
# at closure creation too, i.e. move param checks to the call boundary,
# which is a v0.19-sized interpreter change: it touches all three call
# paths and every typed function's why-tree).

def test_a_param_spec_is_late_bound_and_a_later_let_captures_it():
    src = ('shape P = @{x: num}\n'
           'fn g() {\n'
           '  fn h(p: P) { p.x }\n'
           '  let P = 3\n'
           '  h(@{x: 1})\n'
           '}\n'
           'let r = g()\n')
    interp, env, out = run(src)
    r = env.get("r")
    assert isinstance(r.value, Miss)
    # the annotation named the shape; the guard found the number
    assert "typed spec must be a type name or a shape, got 3" \
        in r.value.reasons[0]


def test_one_signature_can_mean_two_different_shapes():
    """The sharpest witness: `fn h(p: P) -> P` where the param `P` and the
    return `P` are different shapes, proved by which values pass. The param
    guard resolves the INNER `P` (bound in g's env by the time h is called);
    the return spec was resolved at closure creation, when only the OUTER
    `P` existed."""
    all_ok('shape P = @{x: num}\n'
           'fn g() {\n'
           '  fn h(p: P) -> P { p }\n'
           '  shape P = @{y: str}\n'
           '  check "a value satisfying BOTH passes": '
           'not missed(h(@{x: 1, y: "a"}))\n'
           '  check "inner-only satisfies the param, misses the RETURN":\n'
           '    contains(reasons(h(@{y: "a"}))[0], "return value")\n'
           '  check "outer-only satisfies the return, misses the PARAM":\n'
           '    contains(reasons(h(@{x: 1}))[0], "parameter \'p\'")\n'
           '  1\n'
           '}\n'
           'let r = g()\n')


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


def test_three_way_block_local_shape_return_type():
    # v0.18 (round 342): this case used to be the out-of-scope crash probe
    # (`fn f() -> Local` OUTSIDE make's body), which is now a parse error
    # and so cannot be run in any mode. What is worth three-way coverage is
    # the case that survived the change: a shape declared in a block, used
    # as a return type inside that same block, resolved once per closure
    # creation — i.e. once per call of the enclosing function.
    assert_three_way(
        'fn make(n) {\n'
        '  shape Local = @{x: num}\n'
        '  fn f(v) -> Local { @{x: v} }\n'
        '  (f(n)).x\n'
        '}\n'
        'let result = make(3) + make(4)\n')


# ============================================ round 335 (SWE-loop D) ========
# The docstring above, SPEC.md's own v0.13 bullet, and
# `test_mutual_tail_call_checks_against_the_caller_not_the_callee` all say
# the check must use the ORIGINALLY CALLED closure's ret_spec, "not
# whatever closure a tail loop bounces through along the way". That half
# was right. What nobody checked is the OTHER direction: the closure the
# chain bounces THROUGH has a contract of its own, and dropping the
# caller's spec on the floor is not the same thing as dropping the
# callee's. The existing mutual-tail-call tests only ever used an UNTYPED
# callee, so `fn f() -> num { "s" }` — a function that misses correctly
# when called as `let q = f()` — silently returned the raw `"s"` whenever
# some other function happened to call it in TAIL position. Whether a
# declared return type was enforced at all depended on the syntactic
# position of a call site in someone ELSE's body.
#
# Fix (`_note_chain_ret` / `_check_chain_rets`, interp.py): every ret_spec
# the tail loop enters is recorded and checked, so every contract along
# the chain applies to the one settled value it all shares.
#
# Round 336 (language C) took round 335's own next-steps item 4 — "the
# chain-order choice is a semantics decision worth a second opinion" — and
# settled it the other way: see the `--- round 336` section at the bottom
# of this file. Round 335 ran the caller's contract FIRST and the chain's
# in entry order (outermost-first) because that preserved every
# pre-existing message; round 336 runs them INNERMOST-FIRST, each at its
# own tail-call line, because that is what the same program does with
# every call lifted out of tail position, and what
# `examples/self_eval.lang` — Whence's own definition of Whence, which has
# no tail-call merging at all — has always computed.


def test_untyped_caller_does_not_erase_the_tail_callees_own_contract():
    src = ('fn f() -> num { "s" }\n'
           'fn outer() { f() }\n'
           'let r = outer()\n')
    interp, env, out = run(src)
    r = env.get("r")
    assert isinstance(r.value, Miss), r.value
    assert r.value.reasons[0].startswith("return value of f expected num")


def test_the_same_callee_misses_identically_out_of_tail_position():
    # the point of the bug: these two must not disagree. Round 335 could
    # only compare the wording (it stripped the line, because the tail
    # form reported the OUTER call site); round 336 records each chain
    # entry's own tail-call line, so the two forms — laid out line for
    # line — now agree byte for byte, line number included.
    tail = run('fn f() -> num { "s" }\nfn outer() { f() }\nlet r = outer()\n')
    lifted = run('fn f() -> num { "s" }\n'
                 'fn outer() { let q = f()  q }\n'
                 'let r = outer()\n')
    a, b = tail[1].get("r").value, lifted[1].get("r").value
    assert isinstance(a, Miss) and isinstance(b, Miss)
    assert a.reasons == b.reasons
    assert a.reasons[0].endswith("(line 2)"), a.reasons


def test_nested_fn_and_fnexpr_tail_calls_keep_their_return_contracts():
    for src, want in [
        ('fn outer() { fn f() -> num { "s" }  f() }\nlet r = outer()\n',
         "return value of f expected num"),
        ('fn outer() { let f = fn() -> num { "s" }  f() }\nlet r = outer()\n',
         "return value expected num"),
    ]:
        interp, env, out = run(src)
        r = env.get("r")
        assert isinstance(r.value, Miss), (src, r.value)
        assert r.value.reasons[0].startswith(want), (src, r.value.reasons)


def test_only_the_caller_violated_names_the_caller():
    # `f`'s own contract is SATISFIED ("s" is a str); only `outer`'s is
    # violated, so `outer` names itself under either ordering. (Round 335
    # called this test "typed caller still wins when both contracts are
    # violated" — a misnomer: only one of the two is violated here. The
    # genuinely-both-violated case is
    # `test_both_contracts_violated_names_the_inner_one` below, and it is
    # the one round 336 changed.)
    src = ('fn f() -> str { "s" }\n'
           'fn outer() -> num { f() }\n'
           'let r = outer()\n')
    interp, env, out = run(src)
    assert env.get("r").value.reasons[0].startswith(
        "return value of outer expected num")


def test_a_callee_only_violation_is_reported_against_the_callee():
    src = ('fn f() -> num { "s" }\n'
           'fn outer() -> str { f() }\n'   # outer's own contract is satisfied
           'let r = outer()\n')
    interp, env, out = run(src)
    assert env.get("r").value.reasons[0].startswith(
        "return value of f expected num")


def test_every_contract_in_a_three_hop_chain_applies():
    src = ('fn c() -> bool { "s" }\n'
           'fn b() -> num { c() }\n'
           'fn a() { b() }\n'
           'let r = a()\n')
    interp, env, out = run(src)
    r = env.get("r")
    assert isinstance(r.value, Miss)
    # round 336: the chain is checked INSIDE OUT, so the innermost
    # violated contract wins — `c`, which is what the same program says
    # with the calls lifted out of tail position, and what the guest
    # evaluator has always said. (Round 335 asserted `b` here, on the
    # opposite ordering; that is the decision this round reversed.)
    assert r.value.reasons[0].startswith("return value of c expected bool")


def test_a_satisfied_chain_passes_through_unchanged():
    src = ('fn c() -> str { "s" }\n'
           'fn b() -> any { c() }\n'
           'fn a() { b() }\n'
           'let r = a()\n')
    interp, env, out = run(src)
    assert env.get("r").value == "s"


def test_typed_self_tail_recursion_keeps_exactly_one_chain_entry():
    # the per-bounce cost story: a self-recursive typed tail loop bounces
    # through the SAME closure, so `_note_chain_ret`'s `last[0] is rs`
    # fast path hits every time and the one-element chain list is
    # allocated once, never grown. Behaviour and depth are the pin.
    # (Round 335 named this "...still_records_nothing_extra"; round 336
    # drops the `rs is ret_spec` skip, so one entry IS now recorded and
    # the old name would assert something false.)
    src = ('fn cd(n) -> num { if n <= 0 { 0 } else { cd(n - 1) } }\n'
           'let r = cd(2000)\n')
    interp, env, out = run(src, max_depth=50)
    assert env.get("r").value == 0
    assert interp.peak_depth == 1


def test_mutual_typed_tail_loop_checks_once_not_once_per_bounce():
    # `a` and `b` bounce ~5 times; both declare `-> num`; the settled value
    # is a str. Exactly one "typed" origin miss, not one per bounce.
    src = ('fn a(n) -> num { if n <= 0 { "s" } else { b(n - 1) } }\n'
           'fn b(n) -> num { a(n) }\n'
           'let r = a(4)\n')
    interp, env, out = run(src, max_depth=50)
    r = env.get("r")
    assert isinstance(r.value, Miss)
    assert len(r.value.reasons) == 1, r.value.reasons
    assert r.value.reasons[0].startswith("return value of a expected num")


def test_three_way_untyped_caller_typed_tail_callee():
    assert_three_way(
        'fn f() -> num { "s" }\n'
        'fn outer() { f() }\n'
        'let result = outer()\n')


def test_three_way_three_hop_typed_tail_chain():
    assert_three_way(
        'fn c() -> bool { "s" }\n'
        'fn b() -> num { c() }\n'
        'fn a() { b() }\n'
        'let result = a()\n')


def test_three_way_mutual_typed_tail_loop():
    assert_three_way(
        'fn a(n) -> num { if n <= 0 { "s" } else { b(n - 1) } }\n'
        'fn b(n) -> num { a(n) }\n'
        'let result = a(60)\n')


# --- round 336 (language C): tail position is a SPACE optimisation only ------
#
# Round 335 closed "is the callee's contract checked at all"; it left open,
# as its own next-steps item 4, "which contract is blamed when more than
# one is violated" — it applied the caller's first and the chain's in
# ENTRY order, i.e. outermost-first, and said so explicitly: "both
# statements are true; the current order was chosen because it preserves
# every pre-existing message."
#
# Round 336 settles it against three independent references, all of which
# say INNERMOST-FIRST:
#
#   1. The same program with each call lifted out of tail position by a
#      `let`. A tail call is decision 8's space optimisation ("tail calls
#      merge, they do not forget"); nothing in the spec licenses it to
#      change which function is blamed.
#   2. Non-tail recursion, which has behaved this way since v0.13
#      (`test_non_tail_recursion_checks_every_frame_independently`): the
#      innermost frame's own check fires first and the miss propagates.
#   3. `examples/self_eval.lang` — Whence's own definition of Whence. The
#      guest evaluator has NO tail-call merging: `apply_closure` recurses
#      into `eval(c.body, ...)` and runs `check_ret` per frame, so its
#      order is inside-out by construction. On five of the seven chain
#      programs round 336 probed, the host blamed a different function
#      than the guest did. The guest-differential oracle could not see it
#      because miss WORDINGS are an explicit exemption of that oracle
#      (round 17) — see `tests/test_self_eval.py`'s own round-336 case,
#      which compares them anyway.
#
# The same rule fixes line attribution: each chain entry now carries the
# line of the TAIL CALL that entered it, so a chain miss points at the
# call that produced the bad value, exactly as the lifted program does.


def test_both_contracts_violated_names_the_inner_one():
    # the genuinely-both-violated case, and the one behaviour round 336
    # reversed: `f` returns a num, violating its own `-> str`, and `outer`
    # demands bool. Round 335 named `outer`; the lifted form, non-tail
    # recursion and the guest all name `f`.
    src = ('fn f() -> str { 1 }\n'
           'fn outer() -> bool { f() }\n'
           'let r = outer()\n')
    interp, env, out = run(src)
    assert env.get("r").value.reasons[0].startswith(
        "return value of f expected str")


def test_chain_miss_carries_the_tail_call_line_not_the_outer_call_line():
    src = ('fn c() -> bool { 1 }\n'      # line 1
           'fn b() -> str { c() }\n'     # line 2: the call to `c`
           'fn a() { b() }\n'            # line 3: the call to `b`
           'let r = a()\n')              # line 4: the call to `a`
    reasons = reasons_of(run(src)[1], "r")
    assert reasons[0] == "return value of c expected bool, got num (line 2)"


def test_the_originally_called_closure_is_still_checked_last():
    # nothing in the chain is violated, so `a`'s own contract is what
    # fails — proving the outermost check still runs, after the others.
    src = ('fn c() -> num { 1 }\n'
           'fn b() -> num { c() }\n'
           'fn a() -> str { b() }\n'
           'let r = a()\n')
    reasons = reasons_of(run(src)[1], "r")
    assert reasons[0] == "return value of a expected str, got num (line 4)"


def test_a_repeated_spec_blames_its_innermost_occurrence():
    # exercises `_note_chain_ret`'s move-to-end path: `num` is entered at
    # `b` and again, further in, at `d`, with a passing `any` between. The
    # backwards walk must reach `d`'s entry first, not `b`'s.
    src = ('fn d() -> num { "s" }\n'
           'fn c() -> any { d() }\n'
           'fn b() -> num { c() }\n'
           'fn a() { b() }\n'
           'let r = a()\n')
    reasons = reasons_of(run(src)[1], "r")
    assert reasons[0] == "return value of d expected num, got str (line 2)"


def test_two_closures_sharing_a_spec_object_blame_the_inner_one():
    # `b` and `c` both say `-> num`; their spec is the SAME interned
    # Python str, which is exactly the case round 335's identity dedup
    # silently collapsed onto the OUTER label.
    src = ('fn c() -> num { "s" }\n'
           'fn b() -> num { c() }\n'
           'fn a() { b() }\n'
           'let r = a()\n')
    reasons = reasons_of(run(src)[1], "r")
    assert reasons[0] == "return value of c expected num, got str (line 2)"


def test_a_chain_member_sharing_the_callers_spec_is_still_recorded():
    # round 335 skipped any chain spec identical to the originally-called
    # closure's (`rs is ret_spec`), so this blamed `a`. Same contract,
    # different origin: `c` is the function that produced the bad value.
    src = ('fn c() -> num { "s" }\n'
           'fn b() { c() }\n'
           'fn a() -> num { b() }\n'
           'let r = a()\n')
    reasons = reasons_of(run(src)[1], "r")
    assert reasons[0] == "return value of c expected num, got str (line 2)"


def test_self_recursive_tail_loop_blames_the_recursive_call_site():
    # the innermost frame IS the one that returned the bad value, so the
    # line is the recursive call's, not the outer call's — the same line
    # non-tail recursion has always reported.
    src = ('fn cd(n) -> num { if n <= 0 { "s" } else { cd(n - 1) } }\n'
           'let r = cd(3)\n')
    reasons = reasons_of(run(src, max_depth=50)[1], "r")
    assert reasons == ("return value of cd expected num, got str (line 1)",)


# --- the exhaustive tail-vs-lifted differential ------------------------------
#
# The oracle round 335 wrote for ONE program
# (`test_the_same_callee_misses_identically_out_of_tail_position`), driven
# over every chain the grammar can build at this size. Both forms are laid
# out line for line, so agreement includes the line number.

_CHAIN_RETS = (None, "num", "str", "bool", "any")
_CHAIN_TERMS = ('1', '"s"', 'true')


def chain_pair(specs, term):
    """(tail form, lifted form) of an n-hop chain `f0 -> f1 -> ... -> term`,
    line for line: `let t = <call>  t` fits on one line, so a `-> Type`
    miss must report the same line number under both."""
    tail, lifted = [], []
    last = len(specs) - 1
    for i, sp in enumerate(specs):
        ann = "" if sp is None else " -> %s" % sp
        body = term if i == last else "f%d()" % (i + 1)
        tail.append("fn f%d()%s { %s }" % (i, ann, body))
        lifted.append("fn f%d()%s { %s }" % (
            i, ann, body if i == last else "let t = %s  t" % body))
    end = "\nlet r = f0()\n"
    return "\n".join(tail) + end, "\n".join(lifted) + end


def outcome(src, **kw):
    v = run(src, **kw)[1].get("r")
    p = v.value
    return ("MISS",) + tuple(p.reasons) if isinstance(p, Miss) else ("VAL", p)


def chain_specs(n):
    out = [()]
    for _ in range(n):
        out = [s + (r,) for s in out for r in _CHAIN_RETS]
    return out


def run_chain_differential(hops, **kw):
    n = 0
    for specs in chain_specs(hops):
        for term in _CHAIN_TERMS:
            tail_src, lifted_src = chain_pair(specs, term)
            assert outcome(tail_src, **kw) == outcome(lifted_src, **kw), \
                (specs, term, tail_src, lifted_src)
            n += 1
    return n


@pytest.mark.parametrize("hops", [2, 3])
def test_tail_and_lifted_chains_agree_exhaustively(hops):
    # 75 + 375 programs; the 4-hop tier (1875 more) is the slow test below
    assert run_chain_differential(hops) == 3 * 5 ** hops


def test_tail_and_lifted_mutual_loops_agree():
    # a chain that REVISITS a closure, which is what makes
    # `_note_chain_ret`'s move-to-end path load-bearing
    n = 0
    for sa in _CHAIN_RETS:
        for sb in _CHAIN_RETS:
            for term in _CHAIN_TERMS:
                for k in (1, 3):
                    srcs = []
                    for call in (lambda c: c, lambda c: "let t = %s  t" % c):
                        ann = lambda s: "" if s is None else " -> %s" % s
                        srcs.append(
                            "fn a(k)%s { if k <= 0 { %s } else { %s } }\n"
                            "fn b(k)%s { %s }\n"
                            "let r = a(%d)\n" % (ann(sa), term,
                                                 call("b(k - 1)"), ann(sb),
                                                 call("a(k)"), k))
                    assert outcome(srcs[0], max_depth=50) == \
                        outcome(srcs[1], max_depth=50), (sa, sb, term, k)
                    n += 1
    assert n == 150


@pytest.mark.whence_slow
def test_tail_and_lifted_four_hop_chains_agree_in_every_mode():
    for mode in ({}, {"direct": False}, {"fast": False}):
        assert run_chain_differential(4, **mode) == 3 * 5 ** 4


@pytest.mark.whence_slow
def test_every_mode_agrees_on_three_hop_chains():
    # the three-way differential over the same family: `assert_three_way`
    # is too slow to run 375 times, so this compares outcomes directly and
    # leaves why-tree equality to the named `assert_three_way` cases below.
    for specs in chain_specs(3):
        for term in _CHAIN_TERMS:
            for src in chain_pair(specs, term):
                got = {outcome(src), outcome(src, direct=False),
                       outcome(src, fast=False)}
                assert len(got) == 1, (src, got)


def test_three_way_inside_out_three_hop_chain():
    assert_three_way(
        'fn c() -> bool { "s" }\n'
        'fn b() -> num { c() }\n'
        'fn a() { b() }\n'
        'let result = a()\n')


def test_three_way_repeated_spec_chain():
    assert_three_way(
        'fn d() -> num { "s" }\n'
        'fn c() -> any { d() }\n'
        'fn b() -> num { c() }\n'
        'fn a() { b() }\n'
        'let result = a()\n')


def test_three_way_self_recursive_typed_tail_loop_line():
    assert_three_way(
        'fn cd(n) -> num { if n <= 0 { "s" } else { cd(n - 1) } }\n'
        'let result = cd(30)\n', max_depth=50)
