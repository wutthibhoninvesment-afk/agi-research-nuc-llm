"""The evaluator is trampolined: Whence recursion depth must not depend on
CPython's recursion limit, and the depth cap must be a language tunable."""

import sys

import pytest

from whence.interp import Interpreter, _Call
from whence.values import Miss

COUNT = "fn count(n) { if n == 0 { 0 } else { 1 + count(n - 1) } }\n"
EVEN_ODD = ("fn even(n) { if n == 0 { true } else { odd(n - 1) } }\n"
            "fn odd(n) { if n == 0 { false } else { even(n - 1) } }\n")


def result(src, **kw):
    interp = Interpreter(**kw)
    env = interp.run(src)
    return interp, env.get("result").payload


def test_deep_recursion_under_tiny_python_limit():
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(200)   # far below the old ~11-frames-per-call need
    try:
        interp, p = result(COUNT + "let result = count(3000)")
    finally:
        sys.setrecursionlimit(old)
    assert p == 3000
    assert interp.peak_depth == 3001


def test_mutual_recursion_deep():
    _, p = result(EVEN_ODD + "let result = even(5001)")
    assert p is False


def test_depth_cap_is_a_miss_with_depth_in_reason():
    interp, p = result("fn loop(n) { 1 + loop(n + 1) }\nlet result = loop(0)",
                       max_depth=500)
    assert isinstance(p, Miss)
    assert "recursion too deep in loop (depth 500)" in p.reasons[0]
    assert interp.peak_depth == 500
    assert interp.depth == 0          # counter unwound after the miss


def test_depth_cap_applies_to_anonymous_fns():
    src = "let f = fn(n) { 1 + f(n + 1) }\nlet result = f(0)"
    _, p = result(src, max_depth=50)
    assert isinstance(p, Miss) and "<fn>" in p.reasons[0]


def test_program_continues_after_runaway():
    src = ("fn loop(n) { 1 + loop(n + 1) }\nlet bad = loop(0)\n" +
           COUNT + "let result = count(100)")
    interp, p = result(src, max_depth=300)
    assert p == 100 and interp.depth == 0


def test_depth_counter_unwinds_on_ordinary_return():
    interp, p = result(COUNT + "let result = count(50)")
    assert p == 50 and interp.depth == 0 and interp.peak_depth == 51


def test_recursion_through_builtins_is_trampolined():
    # map -> closure -> map -> ... nests builtin bodies, not Python frames
    src = ("fn tree(n) { if n == 0 { [] } else { map(tree, [n - 1]) } }\n"
           "let result = len(tree(2500))")
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(300)
    try:
        _, p = result(src)
    finally:
        sys.setrecursionlimit(old)
    assert p == 1


def test_fold_and_filter_call_closures_via_requests():
    src = ("fn add(a, b) { a + b }\n"
           "fn small(x) { x < 5 }\n"
           "let result = fold(add, 0, filter(small, range(100)))")
    _, p = result(src)
    assert p == 10


def test_public_call_value_and_eval_still_work():
    interp = Interpreter()
    env = interp.run("fn double(x) { x * 2 }")
    fn = env.get("double")
    from whence.values import leaf
    v = interp.call_value(fn, [leaf("literal", "", 1, 21)], 1)
    assert v.payload == 42 and v.prov.op == "call"


def test_leaf_nodes_are_not_generators():
    # Literals/names/fn-literals evaluate inline; compound nodes are generators.
    leaf_names = {m.__name__ for m in Interpreter._LEAF}
    assert leaf_names == {"eval_Num", "eval_Str", "eval_BoolLit",
                          "eval_NameRef", "eval_FnExpr"}


def test_call_request_object_is_minimal():
    c = _Call("f", ["a"], 3)
    assert (c.fn, c.args, c.line) == ("f", ["a"], 3)
    with pytest.raises(AttributeError):
        c.extra = 1   # __slots__: no accidental per-request dict
