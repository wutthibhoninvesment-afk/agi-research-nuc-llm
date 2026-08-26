"""v0.6 (round 20): `has`, the string fast path in binop, and inline call
dispatch (Call nodes with fast parts skip eval_Call; plain builtins run with
no trampoline frame).

Semantic anchors:
  - has(r, n) is presence, not readability: true for a field whose VALUE is
    a miss (get would return that miss), false only when the name is absent.
  - The string fast path must not change a single node: == / != / ordering
    render exactly as before, and str % str / str * str stay misses (the
    host's own % would silently FORMAT).
  - Inline dispatch is invisible: fast=True and fast=False agree node for
    node on call-heavy programs.
"""

from whence.interp import Interpreter
from whence.values import Miss


def run(src, **kw):
    interp = Interpreter(**kw)
    env = interp.run(src)
    return interp, env


def val(src, **kw):
    return run(src, **kw)[1].get("result")


def is_miss(v):
    return isinstance(v.payload, Miss)


def reasons(v):
    return " | ".join(v.payload.reasons)


# --- has ---------------------------------------------------------------------

def test_has_present_and_absent():
    v = val('let r = @{a: 1}\nlet result = [has(r, "a"), has(r, "b")]')
    assert [e.payload for e in v.payload] == [True, False]


def test_has_true_for_miss_valued_field():
    # presence, not readability: the field exists, its value is a miss
    v = val('let r = @{a: miss "gone"}\nlet result = has(r, "a")')
    assert v.payload is True


def test_has_agrees_with_contains_keys():
    v = val('let r = @{x: 1, y: 2}\n'
            'let result = has(r, "y") == contains(keys(r), "y")')
    assert v.payload is True


def test_has_propagates_misses():
    v = val('let result = has(miss "no record", "a")')
    assert is_miss(v) and "no record" in reasons(v)
    v = val('let result = has(@{a: 1}, miss "no name")')
    assert is_miss(v) and "no name" in reasons(v)


def test_has_needs_record_and_string():
    v = val('let result = has([1], "a")')
    assert is_miss(v) and "has needs a record" in reasons(v)
    v = val('let result = has(@{a: 1}, 3)')
    assert is_miss(v) and "field name must be a string" in reasons(v)


def test_has_node_names_the_field():
    v = val('let r = @{a: 1}\nlet result = has(r, "a")')
    # the `let` wrapper's input is the has node
    assert v.inputs[0].label() == "has a"


# --- string fast path --------------------------------------------------------

def test_string_compare_ops():
    v = val('let result = ["b" > "a", "a" >= "b", "x" < "y", "y" <= "x",'
            ' "a" == "a", "a" != "a"]')
    assert [e.payload for e in v.payload] == \
        [True, False, True, False, True, False]


def test_string_eq_node_shape_unchanged():
    # same op, empty detail, two inputs — exactly what deep_eq's path built
    v = val('let result = "ab" == "ab"')
    node = v.inputs[0]
    assert node.op == "==" and node.detail == ""
    assert len(node.inputs) == 2 and node.payload is True


def test_string_concat_node_shape_unchanged():
    v = val('let result = "a" + "b"')
    node = v.inputs[0]
    assert node.op == "+" and node.detail == "concat" and node.payload == "ab"


def test_string_mod_is_still_a_miss():
    # the host's "a%s" % "b" would FORMAT; Whence must miss
    v = val('let result = "a%s" % "b"')
    assert is_miss(v) and "cannot apply '%'" in reasons(v)


def test_string_mul_sub_div_are_misses():
    for op in ("*", "-", "/"):
        v = val('let result = "a" %s "b"' % op)
        assert is_miss(v), op
        assert "cannot apply '%s'" % op in reasons(v)


# --- inline call dispatch ----------------------------------------------------

CALL_HEAVY = """
fn add(a, b) { a + b }
fn twice(f, x) { f(f(x, x), f(x, x)) }
fn fib(n) { if n < 2 { n } else { fib(n - 1) + fib(n - 2) } }
let r1 = twice(add, 3)
let r2 = fib(10)
let r3 = len([1, 2, 3])
let r4 = num("41") + 1
let r5 = add(1, miss "bad arg")
let result = [r1, r2, r3, r4]
"""


def test_inline_dispatch_matches_slow_path():
    from whence.values import diverge
    _, fast_env = run(CALL_HEAVY)
    _, slow_env = run(CALL_HEAVY, fast=False)
    for name in ("r1", "r2", "r3", "r4", "r5", "result"):
        a, b = fast_env.get(name), slow_env.get(name)
        assert diverge(a, b) == [], name


def test_inline_builtin_wrong_arity_is_the_same_miss():
    fast = val("let result = len(1, 2)")
    slow = val("let result = len(1, 2)", fast=False)
    assert is_miss(fast) and reasons(fast) == reasons(slow)
    assert "len expects 1 args, got 2" in reasons(fast)


def test_inline_call_of_a_miss_callee_propagates():
    v = val('let f = miss "no fn"\nlet result = f(1)')
    assert is_miss(v) and "no fn" in reasons(v)


def test_inline_call_of_noncallable():
    v = val("let result = 3(1)")
    assert is_miss(v) and "not callable" in reasons(v)


def test_deferred_loop_bookkeeping_still_merges():
    # names/runs are now allocated lazily; a mutual-recursion tail loop must
    # still produce one merged `call even/odd ×N` node
    interp, env = run("""
fn even(n) { if n == 0 { true } else { odd(n - 1) } }
fn odd(n) { if n == 0 { false } else { even(n - 1) } }
let result = even(6)
""")
    node = env.get("result").inputs[0]
    assert node.op == "call" and node.detail == "even/odd"
    assert node.count == 7 and node.payload is True


def test_single_call_has_plain_call_node():
    v = val("fn inc(x) { x + 1 }\nlet result = inc(4)")
    node = v.inputs[0]
    assert node.op == "call" and node.detail == "inc" and node.count == 1


# --- slimmer nodes (count as class attr, unboxed single input) --------------

def test_plain_nodes_have_class_level_count():
    from whence.values import Prov, MergedProv
    v = val("let result = 1 + 2")
    node = v.inputs[0]
    assert node.count == 1
    assert type(node) is Prov and "count" not in Prov.__slots__
    # plain nodes cannot be given a count: it lives only on MergedProv
    try:
        node.count = 5
        assert False, "assigning count to a plain Prov must fail"
    except AttributeError:
        pass
    assert "count" in MergedProv.__slots__


def test_merged_loop_nodes_are_mergedprov():
    from whence.values import MergedProv
    interp, env = run(
        "fn go(i) { if i == 0 { 0 } else { go(i - 1) } }\nlet result = go(5)")
    node = env.get("result").inputs[0]
    assert isinstance(node, MergedProv)
    assert node.op == "call" and node.count == 6
    # the merged `if` RUNS are MergedProv; the final iteration's `if`
    # completed normally (no pending tail call), so it is a plain node
    # reached through the result input, not a merged run
    decisions = [n for n in node.inputs if n.op == "if"]
    merged_runs = [n for n in decisions if n.count > 1]
    assert merged_runs and all(isinstance(n, MergedProv) for n in merged_runs)
    assert [n.count for n in merged_runs] == [5]   # 5 else-branch loops
    finals = [n for n in decisions if n.count == 1]
    assert len(finals) == 1 and finals[0].detail == "took then-branch"


def test_single_input_reads_back_as_tuple():
    v = val("let result = not true")
    node = v.inputs[0]           # the `not` node: one input
    assert type(node.inputs) is tuple and len(node.inputs) == 1
    assert node.inputs[0].payload is True
    two = val("let result = 1 + 2").inputs[0]
    assert type(two.inputs) is tuple and len(two.inputs) == 2


def test_zero_input_nodes_share_the_empty_tuple():
    v = val("let result = 5")
    lit = v.inputs[0]
    assert lit.inputs == ()


# --- n-way contrast and contrast-on-failing-checks ---------------------------

NWAY = """
fn tally(rate) {
  let base = 200
  let fee = base * rate
  base + fee
}
let r0 = tally(0.1)
let r1 = tally(0.1)
let r2 = tally(0.3)
let result = contrast([r0, r1, r2])
"""


def test_contrast_nway_names_only_diverging_runs():
    v = val(NWAY)
    text = v.payload
    assert "run 2 vs run 0:" in text          # r2 used a different rate
    assert "run 1 vs run 0:" not in text      # r1 is identical: skipped
    assert "0.3" in text and "0.1" in text    # the diverging literals appear


def test_contrast_nway_all_agree():
    v = val("let a = 1 + 1\nlet b = 1 + 1\nlet result = contrast([a, b])")
    assert v.payload == "no divergence"


def test_contrast_nway_short_lists():
    assert val("let result = contrast([])").payload == "no divergence"
    assert val("let result = contrast([42])").payload == "no divergence"


def test_contrast_nway_bad_input():
    v = val("let result = contrast(5)")
    assert is_miss(v) and "contrast needs two values or a list" in reasons(v)
    v = val('let result = contrast(miss "gone")')
    assert is_miss(v) and "gone" in reasons(v)


def test_contrast_two_arg_form_unchanged():
    v = val("let a = 1 + 1\nlet b = 1 + 2\nlet result = contrast(a, b)")
    assert "origin 1 of" in v.payload


def test_failing_eq_check_carries_contrast():
    interp, _ = run('let a = 2 + 2\nlet b = 2 + 3\ncheck "same": a == b')
    (c,) = interp.failed_checks()
    assert "contrast" in c
    assert "origin 1 of" in c["contrast"]
    # the diverging literals are named side by side
    assert "2" in c["contrast"] and "3" in c["contrast"]


def test_passing_check_has_no_contrast():
    interp, _ = run('check "same": 1 == 1')
    assert interp.checks[0]["ok"] and "contrast" not in interp.checks[0]


def test_failing_ne_check_has_no_contrast():
    # a failing != means the sides AGREE: nothing to contrast
    interp, _ = run('check "differ": 1 != 1')
    (c,) = interp.failed_checks()
    assert "contrast" not in c


def test_missing_eq_check_has_no_contrast():
    interp, _ = run('check "m": (miss "gone") == 1')
    (c,) = interp.failed_checks()
    assert "contrast" not in c and "gone" in c["note"]


def test_failing_eq_check_contrast_in_fast_and_slow_paths():
    src = 'let a = 2 + 2\nlet b = 2 + 3\ncheck "same": a == b'
    for fast in (True, False):
        interp, _ = run(src, fast=fast)
        (c,) = interp.failed_checks()
        assert "contrast" in c, fast


def test_run_py_prints_contrast(tmp_path):
    import subprocess, sys, os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prog = tmp_path / "c.lang"
    prog.write_text('let a = 2 + 2\nlet b = 2 + 3\ncheck "same": a == b\n')
    r = subprocess.run([sys.executable, os.path.join(root, "run.py"),
                        str(prog)], capture_output=True, text=True)
    assert r.returncode == 1
    assert "where the two sides diverge:" in r.stdout
    assert "origin 1 of" in r.stdout
