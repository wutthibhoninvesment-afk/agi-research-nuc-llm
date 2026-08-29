import pytest

from whence.interp import Interpreter
from whence.values import Miss, Record, Explanation, render_why


def run(src):
    interp = Interpreter()
    env = interp.run(src)
    return interp, env


def val(src, name="result"):
    _, env = run(src)
    return env.get(name).payload


def is_miss(p):
    return isinstance(p, Miss)


# --- arithmetic & types --------------------------------------------------

def test_arithmetic():
    assert val("let result = 2 + 3 * 4") == 14
    assert val("let result = 7 / 2") == 3.5
    assert val("let result = 7 % 3") == 1
    assert val("let result = -(3 + 4)") == -7


def test_string_and_list_concat():
    assert val('let result = "a" + "b"') == "ab"
    p = val("let result = [1] + [2, 3]")
    assert [e.payload for e in p] == [1, 2, 3]


def test_mixed_type_arithmetic_is_miss():
    p = val('let result = 1 + "a"')
    assert is_miss(p) and "cannot add" in p.reasons[0]


def test_division_by_zero():
    p = val("let result = 1 / 0")
    assert is_miss(p) and "division by zero (line 1)" in p.reasons[0]
    assert is_miss(val("let result = 1 % 0"))


def test_unbound_name_is_miss():
    p = val("let result = nope + 1")
    assert is_miss(p) and "unbound name 'nope'" in p.reasons[0]


def test_miss_propagates_and_merges_reasons():
    p = val("let a = 1 / 0\nlet b = nope\nlet result = a + b")
    assert is_miss(p) and len(p.reasons) == 2


def test_duplicate_reasons_deduped():
    p = val("let a = 1 / 0\nlet result = a + a")
    assert is_miss(p) and len(p.reasons) == 1


# --- strict booleans -----------------------------------------------------

def test_if_strict_bool():
    assert val('let result = if 1 < 2 { "y" } else { "n" }') == "y"
    p = val("let result = if 0 { 1 } else { 2 }")
    assert is_miss(p) and "must be true/false" in p.reasons[0]


def test_if_condition_miss_propagates():
    p = val("let result = if 1 / 0 == 1 { 1 } else { 2 }")
    assert is_miss(p)


def test_logic_short_circuit():
    # short-circuit: the division by zero on the right is never evaluated
    assert val("let result = false and 1 / 0 == 1") is False
    assert val("let result = true or 1 / 0 == 1") is True
    assert val("let result = true and false") is False
    p = val("let result = 1 and true")
    assert is_miss(p)


def test_not_strict():
    assert val("let result = not false") is True
    assert is_miss(val("let result = not 1"))


# --- equality ------------------------------------------------------------

def test_bool_not_equal_number():
    assert val("let result = true == 1") is False


def test_deep_equality():
    assert val("let result = [1, [2, 3]] == [1, [2, 3]]") is True
    assert val("let result = @{a: 1, b: 2} == @{b: 2, a: 1}") is True
    assert val("let result = @{a: 1} == @{a: 2}") is False
    assert val("let result = 1 == 1.0") is True


def test_function_equality_is_miss():
    p = val("fn f(x) { x }\nlet result = f == f")
    assert is_miss(p) and "compare functions" in p.reasons[0]


def test_miss_equality_is_miss():
    p = val("let a = 1 / 0\nlet result = a == a")
    assert is_miss(p)


# --- functions -----------------------------------------------------------

def test_closures_capture():
    src = """
fn make_adder(n) { fn(x) { x + n } }
let add5 = make_adder(5)
let result = add5(3)
"""
    assert val(src) == 8


def test_recursion():
    src = """
fn fib(n) { if n < 2 { n } else { fib(n - 1) + fib(n - 2) } }
let result = fib(10)
"""
    assert val(src) == 55


def test_runaway_recursion_is_miss():
    p = val("fn loop(n) { 1 + loop(n + 1) }\nlet result = loop(0)")
    assert is_miss(p) and "recursion too deep" in p.reasons[0]


def test_arity_mismatch_is_miss():
    p = val("fn f(a, b) { a + b }\nlet result = f(1)")
    assert is_miss(p) and "expects 2 args, got 1" in p.reasons[0]


def test_call_non_function_is_miss():
    p = val("let x = 3\nlet result = x(1)")
    assert is_miss(p) and "not callable" in p.reasons[0]


def test_block_scoping():
    assert val("let result = { let y = 2\ny + 1 }") == 3
    p = val("let x = { let y = 2\ny }\nlet result = y")
    assert is_miss(p)  # y does not leak out of the block


# --- collections ---------------------------------------------------------

def test_index_and_bounds():
    assert val("let result = [10, 20][1]") == 20
    p = val("let result = [10][5]")
    assert is_miss(p) and "out of range" in p.reasons[0]
    assert is_miss(val("let result = [10][true]"))
    assert val('let result = "abc"[1]') == "b"
    assert is_miss(val("let result = 5[0]"))


def test_field_access():
    assert val("let result = @{a: 1}.a") == 1
    p = val("let result = @{a: 1, b: 2}.c")
    assert is_miss(p) and "record has: a, b" in p.reasons[0]
    assert is_miss(val("let result = 3.a"))


def test_access_passes_provenance_through():
    _, env = run("let x = 1 + 1\nlet xs = [x]\nlet result = xs[0]")
    tree = render_why(env.get("result").prov)
    assert "let x" in tree  # element kept its own history


# --- miss / rescue / why -------------------------------------------------

def test_miss_literal():
    p = val('let result = miss "no data"')
    assert is_miss(p) and p.reasons[0] == "no data (line 1)"
    assert is_miss(val("let result = miss 42"))  # non-string reason


def test_rescue():
    assert val("let result = 1 / 0 rescue 99") == 99
    assert val("let result = 5 rescue 99") == 5
    p = val("let result = 1 / 0 rescue nope")
    assert is_miss(p)  # recovery can itself miss


def test_rescue_keeps_no_wrapper_when_not_needed():
    _, env = run("let a = 5\nlet result = a rescue 99")
    assert "rescue" not in render_why(env.get("result").prov)


def test_rescue_provenance_remembers_miss():
    _, env = run("let result = 1 / 0 rescue 99")
    tree = render_why(env.get("result").prov)
    assert "rescue" in tree and "division by zero" in tree


def test_missed_and_reasons():
    assert val("let result = missed(1 / 0)") is True
    assert val("let result = missed(1)") is False
    p = val('let m = miss "a" + miss "b"\nlet result = reasons(m)')
    assert [e.payload for e in p] == ["a (line 1)", "b (line 1)"]
    assert val("let result = reasons(5)") == []


def test_why_and_str_why():
    _, env = run("let a = 2\nlet b = a * 3\nlet w = why b")
    w = env.get("w").payload
    assert isinstance(w, Explanation)
    s = val("let a = 2\nlet b = a * 3\nlet result = str(why b)")
    assert "let a" in s and "*" in s


def test_snip_erases_history():
    s = val("let a = 2\nlet b = a * 3\nlet result = str(why snip b)")
    assert "let a" not in s and "snipped" in s


def test_note_waypoint():
    s = val('let x = note("halfway", 2 + 2)\nlet result = str(why x)')
    assert "halfway" in s
    assert is_miss(val("let result = note(42, 1)"))


def test_note_annotates_miss_without_swallowing():
    p = val('let result = note("stage 1", 1 / 0)')
    assert is_miss(p) and "division by zero" in p.reasons[0]


def test_if_provenance_records_branch_and_condition():
    _, env = run("let c = 1 < 2\nlet result = if c { 10 } else { 20 }")
    tree = render_why(env.get("result").prov)
    assert "took then-branch" in tree and "let c" in tree


# --- builtins ------------------------------------------------------------

def test_len():
    assert val('let result = len("abc")') == 3
    assert val("let result = len([1, 2])") == 2
    assert val("let result = len(@{a: 1})") == 1
    assert is_miss(val("let result = len(5)"))


def test_range():
    assert [e.payload for e in val("let result = range(3)")] == [0, 1, 2]
    assert [e.payload for e in val("let result = range(2, 5)")] == [2, 3, 4]
    assert is_miss(val("let result = range(1.5)"))


def test_map_filter_fold():
    src = """
fn double(x) { x * 2 }
let result = map(double, [1, 2, 3])
"""
    assert [e.payload for e in val(src)] == [2, 4, 6]
    src = """
fn big(x) { x > 1 }
let result = filter(big, [1, 2, 3])
"""
    assert [e.payload for e in val(src)] == [2, 3]
    src = """
fn add(a, b) { a + b }
let result = fold(add, 100, [1, 2, 3])
"""
    assert val(src) == 106


def test_filter_predicate_must_be_bool():
    p = val("fn bad(x) { x }\nlet result = filter(bad, [1])")
    assert is_miss(p) and "must return true/false" in p.reasons[0]


def test_map_keeps_element_misses():
    src = "fn inv(x) { 10 / x }\nlet result = map(inv, [2, 0, 5])"
    p = val(src)
    assert p[0].payload == 5.0
    assert is_miss(p[1].payload)
    assert p[2].payload == 2.0


def test_push_is_functional():
    src = "let xs = [1]\nlet ys = push(xs, 2)\nlet result = len(xs)"
    assert val(src) == 1
    assert [e.payload for e in val("let result = push([1], 2)")] == [1, 2]


def test_str_and_num():
    assert val("let result = str(42)") == "42"
    assert val('let result = str(1 / 0)').startswith("miss:")
    assert val('let result = num("12")') == 12
    assert val('let result = num(" 3.5 ")') == 3.5
    assert val("let result = num(7)") == 7
    p = val('let result = num("3O")')
    assert is_miss(p) and 'cannot parse "3O"' in p.reasons[0]


def test_abs_sqrt():
    assert val("let result = abs(-3)") == 3
    assert val("let result = sqrt(9)") == 3.0
    p = val("let result = sqrt(-1)")
    assert is_miss(p) and "negative" in p.reasons[0]


def test_trunc():
    # round 318 (v0.17): closes the "rand(lo, hi) not yet justified"
    # backlog item (round 294's item 4) by fixing the real blocker -- no
    # builtin could ever turn a float into an int, so a ranged random draw
    # was never expressible in pure Whence at all, regardless of rand's own
    # arity. `trunc` rounds TOWARD ZERO, like abs's own "toward zero is the
    # origin" convention, not floor's "toward negative infinity" -- the two
    # differ only for negative inputs.
    assert val("let result = trunc(3.9)") == 3
    assert val("let result = trunc(0 - 3.9)") == 0 - 3
    assert val("let result = trunc(7)") == 7  # already an int: unchanged
    assert val("let result = trunc(0 - 3.9) == 0 - 4") is False  # not floor
    p = val('let result = trunc("nope")')
    assert is_miss(p) and "trunc of" in p.reasons[0]
    # composes predictably with abs, in both orders, for both an int and a
    # float input -- not true of trunc/floor
    assert val("let result = abs(trunc(0 - 3.9)) == trunc(abs(0 - 3.9))") is True
    assert val("let result = abs(trunc(7)) == trunc(abs(7))") is True


def test_contains():
    assert val('let result = contains("whence", "hen")') is True
    assert val("let result = contains([1, 2], 2)") is True
    assert val("let result = contains([[1]], [1])") is True
    assert val("let result = contains([1], 5)") is False
    assert is_miss(val("let result = contains(5, 1)"))


def test_join():
    assert val('let result = join(["a", "b"], "-")') == "a-b"
    assert is_miss(val('let result = join(["a", 1], "-")'))
    assert is_miss(val('let result = join([str(1 / 0) + ""], "-")')) is False


def test_keys_and_merge():
    assert [e.payload for e in val("let result = keys(@{b: 1, a: 2})")] == ["a", "b"]
    src = "let result = merge(@{a: 1, b: 2}, @{b: 9, c: 3})"
    p = val(src)
    assert isinstance(p, Record)
    assert {k: v.payload for k, v in p.fields.items()} == {"a": 1, "b": 9, "c": 3}


def test_builtin_arity_and_miss_args():
    p = val("let result = len()")
    assert is_miss(p) and "expects 1 args, got 0" in p.reasons[0]
    p = val("let result = len(1 / 0)")
    assert is_miss(p) and "division by zero" in p.reasons[0]


def test_print_pass_through_and_capture():
    interp, env = run('let result = print("hi") + "!"')
    assert interp.out_lines == ["hi"]
    assert env.get("result").payload == "hi!"


def test_print_renders_misses_and_lists():
    interp, _ = run("print(1 / 0)\nprint([1, 2])")
    assert interp.out_lines[0].startswith("miss: division by zero")
    assert interp.out_lines[1] == "[1, 2]"


# --- checks --------------------------------------------------------------

def test_checks_recorded():
    interp, _ = run('check "yes": 1 == 1\ncheck "no": 1 == 2')
    assert [c["ok"] for c in interp.checks] == [True, False]
    assert interp.checks[1]["note"] == "value was false"
    assert "==" in interp.checks[1]["why"]
    assert len(interp.failed_checks()) == 1


def test_check_fails_on_miss_and_non_bool():
    interp, _ = run('check "m": 1 / 0 == 1\ncheck "n": 42')
    assert not interp.checks[0]["ok"]
    assert "miss" in interp.checks[0]["note"]
    assert not interp.checks[1]["ok"]
    assert "not a boolean" in interp.checks[1]["note"]


def test_failing_check_why_names_the_culprit():
    interp, _ = run('let rate = 1.08\ncheck "sane": rate < 1')
    assert "let rate" in interp.checks[0]["why"]


# --- provenance shape ----------------------------------------------------

def test_let_wraps_provenance():
    _, env = run("let x = 1 + 1")
    tree = render_why(env.get("x").prov)
    assert tree.splitlines()[0].startswith("2 ← let x")


def test_call_provenance_named():
    _, env = run("fn f(x) { x + 1 }\nlet r = f(2)")
    assert "call f" in render_why(env.get("r").prov)
