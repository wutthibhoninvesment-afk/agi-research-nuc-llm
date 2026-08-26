"""v0.12 (round 122): structural types — `fn f(a: num, b: Point) {…}` and
`shape Name = @{field: type, …}`.

Design (see SPEC.md "v0.12"): a type annotation is erased entirely at
PARSE time. `_apply_type_guards` (parser.py) prepends one
`let <param> = typed(<param>, <spec>, <label>)` per annotated parameter to
the body's statement list — an ordinary Let/Call/Str AST, evaluated by the
existing interpreter with zero new machinery. Consequences that are the
actual claims under test here:

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


def test_typed_param_prepends_exactly_one_let_per_annotation():
    prog = parse("fn f(a: num, b, c: str) { a }\n")
    fn = prog.stmts[0]
    assert fn.params == ["a", "b", "c"]      # runtime param names untouched
    kinds = [s.__class__.__name__ for s in fn.body.stmts]
    assert kinds == ["Let", "Let", "ExprStmt"]
    assert fn.body.stmts[0].name == "a"
    assert fn.body.stmts[1].name == "c"      # b (untyped) gets no guard


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
    assert prog.stmts[0].body.stmts[0].__class__.__name__ == "Let"


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
