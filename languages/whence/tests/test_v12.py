"""v0.12 (round 122): structural types — `fn f(a: num, b: Point) {…}` and
`shape Name = @{field: type, …}`.

Design AS SHIPPED IN v0.12 (see SPEC.md "v0.12"): a type annotation was
erased entirely at PARSE time. `_apply_type_guards` (parser.py) prepended
one `let <param> = typed(<param>, <spec>, <label>)` per annotated parameter
to the body's statement list — an ordinary Let/Call/Str AST, evaluated by
the existing interpreter with zero new machinery.

**v0.19 (round 344) deleted the erasure and `_apply_type_guards` with it**
(SPEC.md "## v0.19", decision 29): the annotation rides on the fn node as
`param_types`, is resolved in the DEFINING env at closure creation by the
same `_closure_spec` a `-> Type` uses, and is checked by `_check_contract`
at the call boundary. The tests below still hold — they were written about
OBSERVABLE behaviour, which is exactly why they survived the mechanism
being replaced underneath them — but the mechanism sentence above is
history, not a description of the current parser. The consequences under
test:

  - an untyped function's body is untouched (no guard is ever inserted) —
    the whole existing corpus (654 tests, run.py) is the regression gate;
  - a mismatch is an ordinary miss (decision 2): it propagates, `rescue`
    recovers it, `blame` finds it — nothing new to learn;
  - the guard only PREPENDS statements, so `mark_tails` (called once, on
    the finished body) marks the same node it always would have — a
    recursive tail call through a typed parameter is still one frame
    (three-way differential + a `peak_depth` pin);
  - `shape Name = @{…}` is sugar for `let Name = @{__shape: "Name", …}`:
    an ordinary binding, reachable by `matches`/nested shape fields, and
    subject to the parser's own duplicate-name rule for free.
"""

import os
import sys

import pytest

from whence.interp import Interpreter
from whence.parser import parse, ParseError
from whence.values import Miss

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_v09 import run, val, assert_three_way  # noqa: E402


def checks_of(interp):
    return [(c["label"], c["ok"]) for c in interp.checks]


def all_ok(src, **kw):
    interp, env, out = run(src, **kw)
    bad = [c for c in interp.checks if not c["ok"]]
    assert bad == [], (bad, out)
    assert interp.checks, "no checks ran"
    return interp, env, out


# --- parser: annotations and shapes -----------------------------------------

def test_untyped_param_list_unchanged():
    prog = parse("fn f(a, b) { a + b }\n")
    fn = prog.stmts[0]
    assert fn.params == ["a", "b"]
    assert [s.__class__.__name__ for s in fn.body.stmts] == ["ExprStmt"]


def test_typed_param_records_exactly_one_contract_per_annotation():
    """v0.19 (round 344) moved the parameter half of a contract OFF the
    body and onto the node. v0.12-v0.18 this test read
    `["Let", "Let", "ExprStmt"]` off `fn.body.stmts`, because the parser
    prepended one `let p = typed(p, spec, label)` per annotation; the body
    of an annotated function is now byte-identical to an unannotated one,
    and the same four facts (position, name, spec, label) live in
    `fn.param_types`. Both halves are asserted: what IS on the node, and
    what is no longer in the body."""
    prog = parse("fn f(a: num, b, c: str) { a }\n")
    fn = prog.stmts[0]
    assert fn.params == ["a", "b", "c"]      # runtime param names untouched
    assert [s.__class__.__name__ for s in fn.body.stmts] == ["ExprStmt"]
    assert [(i, n, spec.value, label)
            for i, n, spec, label in fn.param_types] == [
        (0, "a", "num", "parameter 'a' of f"),
        (2, "c", "str", "parameter 'c' of f"),   # b (untyped) is skipped
    ]
    # the INDEX is the parameter's own position, not its position among the
    # annotated ones — `c` is param 2 even though it is contract 1.
    assert [i for i, _n, _s, _l in fn.param_types] == [0, 2]


def test_an_unannotated_fn_carries_no_param_types_at_all():
    """The `None` (not `()`) sentinel is the whole cost story for an
    unannotated function: `_mk_closure` -> `_closure_params` returns None
    on an identity check, and every call path skips `_check_params` on
    `is not None`. An empty tuple would work too and would cost a loop
    setup per call, so the distinction is pinned."""
    assert parse("fn f(a, b) { a }\n").stmts[0].param_types is None
    assert parse("let g = fn(a) { a }\n").stmts[0].expr.param_types is None
    # ...and a `-> Type` alone does not create one either
    assert parse("fn f(a) -> num { 1 }\n").stmts[0].param_types is None


def test_anonymous_fn_guard_label_has_no_function_name():
    interp, env, out = run(
        'let g = fn(a: num) { a }\nlet r = g("x")\n')
    m = env.get("r")
    assert isinstance(m.value, Miss)
    assert m.value.reasons[0].startswith("parameter 'a' expected num, got str")


@pytest.mark.parametrize("bad_src", [
    "fn f(a: bogus) { a }\n",
    "shape S = @{x: bogus}\n",
    "shape Line = @{a: Point}\nshape Point = @{x: num}\n",   # forward ref
])
def test_unknown_type_is_a_parse_error(bad_src):
    with pytest.raises(ParseError, match="unknown type"):
        parse(bad_src)


def test_reserved_type_name_cannot_be_a_shape():
    with pytest.raises(ParseError, match="reserved type name"):
        parse("shape num = @{x: num}\n")


def test_duplicate_shape_is_a_parse_error():
    with pytest.raises(ParseError, match="already declared"):
        parse("shape P = @{x: num}\nshape P = @{y: num}\n")


def test_duplicate_field_in_shape_is_a_parse_error():
    with pytest.raises(ParseError, match="duplicate field"):
        parse("shape P = @{x: num, x: num}\n")


def test_shape_is_a_contextual_keyword_not_reserved():
    # "shape" used as an ordinary name is unaffected: no "NAME NAME =" shape.
    interp, env, out = all_ok(
        'let shape = "circle"\ncheck "shape is an ordinary name": shape == "circle"\n')


def test_fn_keyword_usable_as_a_type_tag():
    prog = parse("fn f(g: fn) { g }\n")
    assert prog.stmts[0].param_types[0][2].value == "fn"


# --- typed / matches / shapeof: every primitive tag -------------------------

PRIMITIVE_CASES = [
    ("num", "3", True), ("num", '"3"', False),
    ("str", '"hi"', True), ("str", "3", False),
    ("bool", "true", True), ("bool", "1", False),
    ("list", "[1, 2]", True), ("list", '"[]"', False),
    ("record", "@{x: 1}", True), ("record", "3", False),
    ("fn", "fn(a) { a }", True), ("fn", "3", False),
    ("any", "3", True), ("any", '"x"', True), ("any", "@{x: 1}", True),
]


@pytest.mark.parametrize("tag,expr,expected", PRIMITIVE_CASES)
def test_typed_primitive_tags(tag, expr, expected):
    src = 'let v = %s\nlet r = typed(v, "%s", "x")\n' % (expr, tag)
    interp, env, out = run(src)
    r = env.get("r")
    if expected:
        assert not isinstance(r.value, Miss), r.value.reasons
        assert r.value == env.get("v").value  # pass-through payload
    else:
        assert isinstance(r.value, Miss)
        assert tag in r.value.reasons[0] and "expected" in r.value.reasons[0]


@pytest.mark.parametrize("tag,expr,expected", PRIMITIVE_CASES)
def test_matches_mirrors_typed_as_a_total_predicate(tag, expr, expected):
    src = 'let v = %s\nlet r = matches(v, "%s")\n' % (expr, tag)
    interp, env, out = run(src)
    r = env.get("r")
    assert not isinstance(r.value, Miss)      # matches never itself misses
    assert r.value is expected


def test_matches_on_a_miss_is_false_not_a_miss():
    interp, env, out = run('let bad = 1 + "x"\nlet r = matches(bad, "any")\n')
    r = env.get("r")
    assert not isinstance(r.value, Miss)
    assert r.value is False


def test_typed_propagates_a_miss_argument():
    interp, env, out = run('let bad = 1 + "x"\nlet r = typed(bad, "num", "x")\n')
    assert isinstance(env.get("r").value, Miss)
    assert env.get("r").value.reasons == env.get("bad").value.reasons


def test_shapeof_every_kind_including_miss():
    src = '''
let a = 3
let b = "s"
let c = true
let d = [1]
let e = @{x: 1}
let f = fn(x) { x }
let m = 1 + "x"
'''
    want = {"a": "num", "b": "str", "c": "bool", "d": "list",
            "e": "record", "f": "fn", "m": "miss"}
    for name, kind in want.items():
        interp2, env2, _ = run(src + 'let k = shapeof(%s)\n' % name)
        assert env2.get("k").value == kind, (name, kind)


# --- structural (shape) matching --------------------------------------------

SHAPE_SRC = 'shape Point = @{x: num, y: num}\n'


def test_shape_matches_structurally_with_extra_fields():
    src = SHAPE_SRC + 'let result = matches(@{x: 1, y: 2, z: 3}, Point)\n'
    assert val(src).value is True


def test_shape_rejects_missing_field():
    src = SHAPE_SRC + 'let result = matches(@{x: 1}, Point)\n'
    assert val(src).value is False


def test_shape_rejects_wrong_field_type():
    src = SHAPE_SRC + 'let result = matches(@{x: 1, y: "2"}, Point)\n'
    assert val(src).value is False


def test_shape_rejects_a_field_that_is_itself_a_miss():
    src = SHAPE_SRC + 'let result = matches(@{x: 1, y: 1 + "x"}, Point)\n'
    assert val(src).value is False


def test_shape_rejects_a_non_record():
    src = SHAPE_SRC + 'let result = matches(3, Point)\n'
    assert val(src).value is False


def test_nested_shape_two_levels():
    src = (SHAPE_SRC + 'shape Line = @{a: Point, b: Point}\n'
          'let good = matches(@{a: @{x:0,y:0}, b: @{x:1,y:1}}, Line)\n'
          'let bad = matches(@{a: @{x:0}, b: @{x:1,y:1}}, Line)\n')
    interp, env, out = run(src + 'let g = good\nlet b = bad\n')
    assert env.get("good").value is True
    assert env.get("bad").value is False


def test_shape_is_an_ordinary_record_with_a_shape_marker_field():
    interp, env, out = run(SHAPE_SRC + 'let name = Point.__shape\n')
    assert env.get("name").value == "Point"


# --- the desugared guard end to end ------------------------------------------

def test_typed_param_passes_through():
    interp, env, out = all_ok(
        'fn add(a: num, b: num) { a + b }\n'
        'check "typed call ok": add(2, 3) == 5\n')


def test_typed_param_mismatch_is_a_miss_naming_the_function():
    interp, env, out = run(
        'fn add(a: num, b: num) { a + b }\nlet r = add("x", 2)\n')
    r = env.get("r")
    assert isinstance(r.value, Miss)
    assert r.value.reasons[0].startswith(
        "parameter 'a' of add expected num, got str")


def test_arity_mismatch_takes_priority_over_the_type_guard():
    # the guard lives INSIDE the body; a wrong argument count never gets
    # that far (existing arity check in the call machinery runs first).
    interp, env, out = run('fn add(a: num, b: num) { a + b }\nlet r = add(1)\n')
    r = env.get("r")
    assert isinstance(r.value, Miss)
    assert "expects 2 args" in r.value.reasons[0]


def test_type_mismatch_propagates_and_rescues_like_any_other_miss():
    interp, env, out = all_ok(
        'fn add(a: num, b: num) { a + b }\n'
        'let total = add("x", 2) rescue -1\n'
        'check "rescue recovers a type miss": total == -1\n')


def test_blame_reaches_the_call_that_rejected_the_value():
    interp, env, out = run(
        'fn add(a: num, b: num) { a + b }\n'
        'let r = add("x", 2)\nlet b = blame(r)\n')
    bl = env.get("b").value.to_list()
    assert len(bl) == 1
    assert bl[0].value.fields["detail"].value == "parameter 'a' of add"


def test_rebinding_the_parameter_name_reads_the_guarded_value():
    # `let a = a` after the guard reads the ALREADY-checked (missed) `a` —
    # the guard is not silently discarded by a same-named rebind that
    # still depends on the original.
    interp, env, out = run(
        'fn f(a: num) { let a = a  a }\nlet r = f("x")\n')
    assert isinstance(env.get("r").value, Miss)


def test_rebind_that_ignores_the_parameter_discards_the_guard():
    # a rebind that does NOT read `a` naturally replaces it, same as it
    # would replace any other prior binding — no special-casing needed.
    interp, env, out = all_ok(
        'fn f(a: num) { let a = 5  a }\n'
        'check "unrelated rebind wins": f("x") == 5\n')


# --- tail position is unaffected by a type guard -----------------------------

def test_typed_tail_recursion_stays_one_frame():
    interp, env, out = run(
        'fn count(n: num, acc: num) {\n'
        '  if n == 0 { acc } else { count(n - 1, acc + 1) }\n'
        '}\n'
        'let r = count(20000, 0)\n', max_depth=50)
    assert env.get("r").value == 20000
    assert interp.peak_depth == 1
    assert interp.tail_calls == 20000


def test_typed_non_tail_recursion_still_costs_depth():
    src = ('fn f(n: num) { if n == 0 { 0 } else { 1 + f(n - 1) } }\n'
          'let r = f(30)\n')
    interp, env, out = run(src, max_depth=10)
    assert isinstance(env.get("r").value, Miss)
    assert "recursion too deep" in env.get("r").value.reasons[0]


# --- three-way differential (fast / direct / slow) ---------------------------

def test_three_way_typed_function():
    assert_three_way(
        'fn add(a: num, b: num) { a + b }\nlet result = add(2, 3)\n')


def test_three_way_typed_mismatch():
    assert_three_way(
        'fn add(a: num, b: num) { a + b }\nlet result = add("x", 2)\n')


def test_three_way_shape_and_nested_shape():
    assert_three_way(
        'shape Point = @{x: num, y: num}\n'
        'shape Line = @{a: Point, b: Point}\n'
        'fn length(l: Line) {\n'
        '  let dx = l.b.x - l.a.x\n'
        '  let dy = l.b.y - l.a.y\n'
        '  sqrt(dx * dx + dy * dy)\n'
        '}\n'
        'let result = length(@{a: @{x: 0, y: 0}, b: @{x: 3, y: 4}})\n')


def test_three_way_typed_tail_recursion():
    assert_three_way(
        'fn count(n: num, acc: num) {\n'
        '  if n == 0 { acc } else { count(n - 1, acc + 1) }\n'
        '}\n'
        'let result = count(3000, 0)\n')


# ============================================ round 335 (SWE-loop D) ========
# A hand-built record is a first-class structural spec (SPEC v0.12,
# "structural, not nominal"), and `typed`/`matches` accept one directly.
# `_type_match` documented "every other field maps to a nested spec — a str
# or ... another Record" as an invariant, but only the PARSER enforced it
# (`parse_type` rejects `shape Bad = @{x: 5}`); nothing checked the fields
# of a hand-built spec, so the recursion reached `spec.fields` on an int and
# raised `AttributeError` straight out of the interpreter. Found by the
# fuzz-grammar totality sweep that round 335 ran when `matches`/`shapeof`/
# `typed` finally joined `harness/swe/fuzz.py`'s `BUILTIN_ARITY`.

MALFORMED_SPECS = ['@{a: 5}', '@{a: [1]}', '@{a: true}', '@{a: fn(x){x}}',
                   '@{a: miss "b"}', '@{a: @{b: 5}}', '@{a: guess(1,0.5,"m")}']


@pytest.mark.parametrize("spec", MALFORMED_SPECS)
def test_matches_with_a_malformed_record_spec_is_false_not_a_crash(spec):
    # `matches` is documented total: "never itself a miss, even on a miss or
    # a malformed spec (both simply do not match)". That has to hold at
    # every depth, not only at the top level.
    interp, env, out = run('let r = matches(@{a: 1}, %s)\n' % spec)
    assert env.get("r").value is False


@pytest.mark.parametrize("spec", MALFORMED_SPECS)
def test_typed_with_a_malformed_record_spec_is_the_spec_miss(spec):
    interp, env, out = run('let r = typed(@{a: 1}, %s, "L")\n' % spec)
    r = env.get("r")
    assert isinstance(r.value, Miss)
    assert r.value.reasons[0].startswith(
        "typed spec must be a type name or a shape"), r.value.reasons


def test_a_well_formed_hand_built_record_spec_still_matches():
    # the fix must not narrow the documented duck-typing promise
    interp, env, out = run(
        'let ok = matches(@{a: 1, b: "s"}, @{a: "num"})\n'
        'let nested = matches(@{a: @{b: 1}}, @{a: @{b: "num"}})\n'
        'let named = matches(@{x: 1}, @{__shape: "Pt", x: "num"})\n'
        'let no = matches(@{a: "s"}, @{a: "num"})\n'
        'let passed = typed(@{a: 1}, @{a: "num"}, "L")\n')
    assert env.get("ok").value is True
    assert env.get("nested").value is True
    assert env.get("named").value is True
    assert env.get("no").value is False
    passed = env.get("passed").value
    assert {k: n.value for k, n in passed.fields.items()} == {"a": 1}


def test_malformed_spec_reaches_a_parameter_guard_through_a_shadowed_shape():
    # `parse_type` only checks that the NAME was declared as a shape; the
    # runtime spec is whatever that name is bound to where the guard runs.
    # A parameter shadowing it makes a caller-supplied value the type spec —
    # the crash was reachable from ordinary data, not just a literal call.
    interp, env, out = run(
        'shape Pt = @{x: num}\n'
        'fn outer(Pt) {\n'
        '  fn f(p: Pt) { p }\n'
        '  f(@{x: 1})\n'
        '}\n'
        'let r = outer(@{x: [1]})\n')
    r = env.get("r")
    assert isinstance(r.value, Miss)
    assert r.value.reasons[0].startswith(
        "typed spec must be a type name or a shape")


def test_a_non_string_shape_name_renders_as_a_whence_value():
    # `name_node.value` goes straight into a user-visible miss message. A
    # hand-built spec can put anything under `__shape`; rendering a Record
    # through `%s` leaked the Python repr INCLUDING the heap address, so the
    # same program produced a different message on every run — the
    # determinism / fast_slow / direct oracles all fired on it.
    for spec, want in [('@{__shape: 5, a: "num"}', "expected 5"),
                       ('@{__shape: [1, 2], a: "num"}', "expected [1, 2]"),
                       ('@{__shape: @{q: 1}, a: "num"}', "expected @{q: 1}")]:
        interp, env, out = run('let r = typed(@{a: "z"}, %s, "L")\n' % spec)
        reason = env.get("r").value.reasons[0]
        assert want in reason, (spec, reason)
        assert "object at 0x" not in reason, reason


def test_the_repr_leak_is_stable_across_two_runs_of_the_same_source():
    src = 'let r = typed(@{a: "z"}, @{__shape: @{q: 1}, a: "num"}, "L")\n'
    a = run(src)[1].get("r").value.reasons[0]
    b = run(src)[1].get("r").value.reasons[0]
    assert a == b


def test_three_way_hand_built_and_malformed_record_specs():
    # a real call so `direct` mode actually engages (assert_three_way's
    # own precondition), with the specs flowing through a parameter
    assert_three_way(
        'fn probe(v, spec) { [matches(v, spec), missed(typed(v, spec, "L"))] }\n'
        'let good = probe(@{a: 1}, @{a: "num"})\n'
        'let bad = probe(@{a: 1}, @{a: 5})\n'
        'let named = probe(@{a: "z"}, @{__shape: @{q: 1}, a: "num"})\n'
        'let result = [good, bad, named]\n')


# ============================================ round 344 (language C, v0.19) ==
# A parameter contract is no longer a `let p = typed(p, spec, label)`
# statement the parser prepends to the body: it rides on the fn node
# (`param_types`), is resolved once at closure creation in the DEFINING env
# (`_closure_params`, the same `_closure_spec` a `-> Type` uses), and is
# applied at the call boundary (`_check_params`). SPEC decision 29.
#
# The tests below are about what that MOVE changes at run time, as opposed
# to `test_v13.py`'s family, which is about which shape a name means.

def test_a_satisfied_param_contract_leaves_no_node_in_the_why_tree():
    """v0.12-v0.18 a passing annotation still cost a `let a` node, because
    the guard was a real `Let` statement whose result was rebound. It costs
    nothing now — `_check_contract` returns its input UNCHANGED on a pass,
    and `_check_params` writes back only when the box actually changed. So
    the why-tree of a typed function that is called correctly is now
    byte-identical to the untyped version of the same function, which is
    the property `-> Type` has had since v0.13."""
    from whence.values import render_why
    typed_i, typed_env, _ = run('fn f(a: num) { a + 1 }\nlet result = f(2)\n')
    plain_i, plain_env, _ = run('fn f(a) { a + 1 }\nlet result = f(2)\n')
    assert render_why(typed_env.get("result")) == \
        render_why(plain_env.get("result"))
    assert "let a" not in render_why(typed_env.get("result"))


def test_a_failing_param_contract_still_runs_the_body():
    """Deliberately preserved from the prepended-guard era: a failing check
    binds the miss and the call proceeds, so a function that never READS a
    badly-typed parameter still returns normally. Whether it should
    short-circuit is a separate decision with its own corpus cost; pinning
    it here means changing it later has to be a choice, not a side effect."""
    assert val('fn f(a: num) { 42 }\nlet result = f("x")\n').value == 42
    # ...and one that does read it gets an ordinary propagating miss
    r = val('fn f(a: num) { a + 1 }\nlet result = f("x")\n')
    assert isinstance(r.value, Miss)
    assert r.value.reasons[0].startswith("parameter 'a' of f expected num")


def test_a_miss_argument_propagates_instead_of_being_glossed():
    """The other inherited-from-`_check_ret` rule, newly applied to the
    parameter end (decision 2): an argument that is ALREADY a miss passes
    through untouched. v0.12-v0.18 the guard was a real `typed(...)` call,
    so `_propagate` wrapped it in a `builtin typed` node with all three
    operands as inputs; the reason text was the same but the shape was not.
    A call that already failed does not also get a wrong-type gloss."""
    from whence.values import render_why
    r = val('fn f(a: num) { a }\nlet result = f(miss "boom")\n')
    assert isinstance(r.value, Miss)
    assert list(r.value.reasons) == ["boom (line 2)"]
    assert "typed" not in render_why(r)


def test_a_tail_chain_checks_the_params_of_the_closure_it_ENTERS():
    """`ret_spec` is captured ONCE from the originally called closure (a
    return contract is a promise to THIS call's caller, round 336); a
    parameter contract is the opposite — it guards the arguments of
    whichever closure the tail loop is entering right now, so `param_specs`
    is re-read beside `params` on every switch. Mutual recursion between a
    typed and an untyped function is what tells the two rules apart: `b`'s
    contract must fire on the value `a` tail-calls it with, in the merged
    frame, with no host frame of its own."""
    src = ('fn a(n) { if n == 0 { "done" } else { b(n) } }\n'
           'fn b(n: num) { a(n - 1) }\n'
           'let result = a(3)\n')
    interp, env, _ = run(src)
    assert env.get("result").value == "done"
    assert interp.tail_calls > 0            # it really is a merged tail loop
    bad = ('fn a(n) { if n == 0 { "done" } else { b(n) } }\n'
           'fn b(n: num) { a(n - 1) }\n'
           'let result = a("3")\n')
    r = val(bad)
    assert isinstance(r.value, Miss)
    assert any("parameter 'n' of b expected num, got str" in x
               for x in r.value.reasons), r.value.reasons
    assert_three_way(src)
    assert_three_way(bad)


def test_three_way_param_contract_resolved_in_the_defining_env():
    """The v0.19 resolution rule under the three-way differential: all
    three evaluation modes build closures through the one `_mk_closure`
    choke point, so they must agree on `param_specs` byte for byte."""
    assert_three_way(
        'shape P = @{x: num}\n'
        'fn g() {\n'
        '  fn h(p: P) -> P { p }\n'
        '  shape P = @{y: str}\n'
        '  [missed(h(@{x: 1})), missed(h(@{y: "a"}))]\n'
        '}\n'
        'let result = g()\n')


def test_three_way_param_contract_on_a_mutually_recursive_tail_chain():
    assert_three_way(
        'shape P = @{x: num}\n'
        'fn up(r: P, n) { if n == 0 { r.x } else { down(r, n) } }\n'
        'fn down(r, n: num) { up(r, n - 1) }\n'
        'let result = up(@{x: 9}, 40)\n')
