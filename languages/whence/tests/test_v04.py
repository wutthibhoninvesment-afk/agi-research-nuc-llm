"""Whence v0.4 (round 9): value == provenance node, shared literals,
run-length-merged `if` decisions in tail loops, the call-free closure fast
path, `contrast`, n-way `diverge`, merged-name addressing."""

import gc
import tracemalloc

import pytest

from whence.interp import Interpreter, Env
from whence.values import Prov, Value, Miss, render_why, walk_steps


def run(src, **kw):
    interp = Interpreter(**kw)
    env = interp.run(src)
    return interp, env


def val(src, **kw):
    return run(src, **kw)[1].get("result")


LOOP = "fn go(i, acc) { if i == 0 { acc } else { go(i - 1, acc + i) } }\n"


# --- 1. a value IS its provenance node --------------------------------------

def test_value_is_prov():
    assert Value is Prov
    v = val("let result = 1 + 2")
    assert v.prov is v
    assert v.payload is v.value
    assert v.payload == 3 and v.op == "let"


def test_payload_and_value_are_one_slot():
    p = Prov("literal", "", 1, (), "5", 5)
    assert p.payload == 5
    p.value = 6
    assert p.payload == 6
    p.payload = 7
    assert p.value == 7


def test_pass_through_access_returns_the_element_node_itself():
    _, env = run("let xs = [1, 2]\nlet result = xs[1]")
    xs = env.get("xs")
    assert env.get("result").inputs[0] is xs.payload[1]


# --- 2. literals are shared per source occurrence -----------------------------

def test_same_source_literal_is_one_node():
    v = val(LOOP + "let s = go(5, 0)\nlet result = len(steps(s, \"literal\"))")
    # `0` and `1` in the body, `5` and `0` in the call: four source literals
    assert v.payload == 4


def test_literal_node_is_identical_across_evaluations():
    interp, env = run("fn one() { 1 }\nlet a = one()\nlet b = one()")
    a = env.get("a").inputs[0].inputs[0]   # let a ← call one ← literal
    b = env.get("b").inputs[0].inputs[0]
    assert a is b and a.op == "literal"


def test_shared_literal_renders_each_time_it_is_used():
    v = val("let x = 1\nlet result = x + x")
    tree = render_why(v)
    assert tree.count("1 ← literal") == 1        # shared `let x` shown once …
    assert "⟲ shown above" in tree               # … and marked on re-encounter
    v2 = val("let result = 2 + 2")
    assert render_why(v2).count("2 ← literal") == 2  # distinct source literals


# --- 3. tail loops merge consecutive identical `if` decisions -----------------

def test_tail_loop_if_decisions_are_run_length_merged():
    interp, env = run(LOOP + "let s = go(5, 0)")
    s = env.get("s")
    call = s.inputs[0]
    assert call.op == "call" and call.count == 6
    # inputs: the final result (the last iteration's own `if`, which was
    # not a tail call) then one node per *run* of deferred decisions
    assert len(call.inputs) == 2
    then_run, else_run = call.inputs[0], call.inputs[1]
    assert else_run.op == "if" and else_run.detail == "took else-branch"
    assert else_run.count == 5 and len(else_run.inputs) == 5
    assert then_run.detail == "took then-branch" and then_run.count == 1
    # every input of the merged node is a distinct condition (nothing lost)
    conds = [c.value for c in else_run.inputs]
    assert conds == [False] * 5
    assert [c.inputs[0].value for c in else_run.inputs] == [5, 4, 3, 2, 1]
    assert else_run.value == 15 and then_run.value == 15


def test_merged_if_nodes_are_step_records_with_count():
    v = val(LOOP + "let s = go(5, 0)\n"
            "let result = map(fn(s) { [s.detail, s.count, s.inputs] }, steps(s, \"if\"))")
    got = [[e.payload for e in r.payload] for r in v.payload]
    assert got == [["took then-branch", 1, 2], ["took else-branch", 5, 5]]


def test_alternating_decisions_form_separate_runs():
    src = ("fn z(n, acc) { if n == 0 { acc } else if n % 2 == 0 { z(n - 1, acc + 1) }"
           " else { z(n - 1, acc) } }\n"
           "let s = z(4, 0)\nlet result = map(fn(s) { s.count }, steps(s, \"if\"))")
    v = val(src)
    # n=4: outer else, inner then; n=3: outer else, inner else; n=2: outer
    # else, inner then; n=1: outer else, inner else; n=0: outer then.
    # Flattened in evaluation order (outer before inner), no two consecutive
    # decisions are identical, so nothing merges: 9 runs of 1.
    assert [x.payload for x in v.payload] == [1] * 9


def test_render_shows_merged_if_count():
    interp, env = run(LOOP + "let s = go(3, 0)")
    tree = render_why(env.get("s"))
    assert "call go ×4" in tree
    assert "if took else-branch ×3" in tree


@pytest.mark.whence_slow
def test_tail_loop_retains_under_850_bytes_per_iteration():
    def measure(n):
        gc.collect()
        tracemalloc.start()
        interp = Interpreter(max_depth=10 ** 6)
        env = interp.run(LOOP + "let result = go(%d, 0)\n" % n)
        cur, _ = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return env, cur
    env1, m1 = measure(1000)
    env2, m2 = measure(6000)
    per_iter = (m2 - m1) / 5000.0
    # v0.3: ~1077 bytes per iteration; v0.4 measured 768 (5 nodes: ==, -, +,
    # arg i, arg acc — every one of them a distinct fact about that iteration)
    assert per_iter < 850, per_iter
    # …and the history is still complete: every iteration's `+` is reachable
    plus = [n for n, _ in walk_steps(env2.get("result")) if n.op == "+"]
    assert len(plus) == 6000


# --- 4. the call-free fast path ---------------------------------------------

CORPUS = [
    "1 + 2 * 3 - 4 / 2 % 3",
    "-(1 + 2) * -3",
    "\"a\" + \"b\"",
    "[1, 2] + [3]",
    "[1, [2, 3], @{k: 4}][1][0]",
    "@{a: 1, b: @{c: 2}}.b.c",
    "@{a: 1}.zz",
    "1 < 2 and 2 <= 2 and not (3 > 4) or false",
    "true and 5",
    "false and (1 / 0 == 0)",
    "true or (1 / 0 == 0)",
    "1 / 0 rescue 7",
    "(1 / 0) + 2 rescue 7",
    "num(\"3O\") rescue 0",
    "miss \"boom\"",
    "miss 5",
    "(miss \"a\") + (miss \"b\")",
    "if 1 < 2 { \"y\" } else { \"n\" }",
    "if 1 { 2 } else { 3 }",
    "if 1 / 0 == 0 { 2 } else { 3 }",
    "if 1 > 2 { 1 } else if 2 > 3 { 2 } else { 3 }",
    "{ let a = 2\n  let b = a * a\n  b + 1 }",
    "{ let a = 1 / 0\n a rescue 9 }",
    "why (1 + 2)",
    "str(why (1 + 2))",
    "snip (1 + 2)",
    "\"abc\"[1]",
    "\"abc\"[5]",
    "[1, 2][true]",
    "5[0]",
    "nosuch + 1",
    "fn(x) { x }",
    "(fn(x) { x }) == (fn(x) { x })",
    "1 == 1.0",
    "[1, 2] == [1, 2]",
    "\"a\" < 1",
    "-\"x\"",
    "not 1",
    "1 + \"x\"",
    "1 % 0",
]


@pytest.mark.parametrize("expr", CORPUS)
def test_fast_path_matches_generator_path(expr):
    """The compiled closure path and the generator path are the same
    semantics: identical payload rendering AND identical why-tree."""
    src = "let result = " + expr
    slow_i, slow_env = run(src, fast=False)
    fast_i, fast_env = run(src, fast=True)
    s, f = slow_env.get("result"), fast_env.get("result")
    assert render_why(f) == render_why(s)
    assert str(f.payload.__class__) == str(s.payload.__class__)
    assert fast_i.fast_hits > 0 and slow_i.fast_hits == 0


def test_fast_path_is_taken_for_call_free_subtrees_only():
    interp, env = run("fn f(x) { x + 1 }\nlet a = f(1) + f(2)\nlet b = 1 + 2")
    from whence import ast_nodes as A
    from whence.parser import parse
    prog = parse("fn f(x) { x + 1 }\nlet a = f(1) + f(2)\nlet b = 1 + 2")
    a_expr = prog.stmts[1].expr
    b_expr = prog.stmts[2].expr
    interp2 = Interpreter()
    assert interp2.compile_fast(a_expr) is False          # contains calls
    assert interp2.compile_fast(a_expr.left.args[0])      # `1` is simple
    assert interp2.compile_fast(b_expr)                   # no calls at all
    assert interp2.compile_fast(prog.stmts[0].body)       # body `x + 1`


def test_fast_path_checks_inside_blocks_are_recorded():
    interp, env = run("let r = { check \"inner\": 1 == 2\n 5 }")
    assert interp.fast_hits > 0
    assert [c["label"] for c in interp.failed_checks()] == ["inner"]
    assert "let" not in interp.checks[0]["why"] and "literal" in interp.checks[0]["why"]


def test_fast_path_deep_expression_nesting():
    # parenthesised nesting is bounded by the recursive-descent parser (~10
    # host frames per level) long before the closure tree (1 frame per level)
    # is; a long left-associative chain parses iteratively and nests the
    # compiled closures 400 deep.
    n = 400
    src = "let result = " + "(" * 50 + "1" + ")" * 50 + " + 1" * n
    v = val(src)
    assert v.payload == n + 1
    assert "+" in render_why(v)


def test_tall_call_free_trees_fall_back_to_the_trampoline():
    """A 3000-term chain is call-free but 3000 closures deep; compiling it
    is iterative and the tall part runs on the trampoline (fuzz, round 9:
    `cycle:_compile+compile_fast` RecursionError)."""
    n = 3000
    interp, env = run("let result = 1" + " + 1" * n)
    v = env.get("result")
    assert v.payload == n + 1
    expr = None
    from whence.parser import parse
    top = parse("let result = 1" + " + 1" * n).stmts[0].expr
    assert interp.compile_fast(top) is False
    assert top.fdepth == n + 1
    assert interp.compile_fast(top.left.left.left) is False    # still tall
    deep = top
    for _ in range(n - 50):
        deep = deep.left
    assert interp.compile_fast(deep)                         # 51 tall: fast


def test_deep_eq_is_iterative():
    src = ("fn wrap(n) { @{v: wrap(n)} }\nlet rec = wrap(1)\n"
           "let result = [rec == rec, rec == @{v: 1}, [rec] == [rec]]")
    v = val(src, max_depth=3000)
    # the innermost value is a depth miss, so == is a miss, not a crash —
    # unless a shape mismatch is found first (rec.v is a record, 1 is not)
    assert [isinstance(x.payload, Miss) for x in v.payload] == [True, False, True]
    assert v.payload[1].payload is False
    v2 = val("fn nest(n) { if n == 0 { [] } else { [nest(n - 1)] } }\n"
             "let result = nest(2500) == nest(2500)")
    assert v2.payload is True


def test_parser_reports_too_deep_nesting_instead_of_crashing():
    from whence.parser import parse, ParseError
    with pytest.raises(ParseError, match="nested more than"):
        parse("let x = " + "(" * 200 + "1" + ")" * 200)
    with pytest.raises(ParseError, match="nested more than"):
        parse("let x = " + "- " * 200 + "1")
    assert parse("let x = " + "(" * 50 + "1" + ")" * 50)
    assert parse("let x = " + "- " * 50 + "1")
    chain = "let x = if false { 0 } " + "else if false { 0 } " * 400 + "else { 1 }"
    with pytest.raises(ParseError, match="nested more than"):
        parse(chain)
    short = "let x = if false { 0 } " + "else if false { 0 } " * 40 + "else { 1 }"
    assert val(short.replace("let x", "let result")).payload == 1


def test_fast_closure_captures_env_per_evaluation():
    v = val("fn mk(a) { fn(b) { a + b } }\nlet result = mk(1)(2) + mk(10)(20)")
    assert v.payload == 33


@pytest.mark.whence_slow
def test_fast_path_speeds_up_a_tail_loop():
    """Relative, so it holds on a loaded machine: the same loop with the
    fast path off must be clearly slower (absolute numbers: bench/)."""
    import time

    def timed(**kw):
        interp = Interpreter(max_depth=10 ** 6, **kw)
        gc.collect()
        gc.disable()             # measure the evaluator, not the collector
        t0 = time.time()
        try:
            interp.run(LOOP + "let s = go(20000, 0)")
        finally:
            gc.enable()
        return time.time() - t0, interp
    slow, si = timed(fast=False)
    fast, fi = timed(fast=True)
    assert si.fast_hits == 0 and fi.fast_hits > 0
    assert fast * 1.4 < slow, (fast, slow)


# --- 5. merged mutual-recursion nodes answer to any member name ---------------

MUTUAL = ("fn even(n) { if n == 0 { true } else { odd(n - 1) } }\n"
          "fn odd(n) { if n == 0 { false } else { even(n - 1) } }\n")


def test_at_matches_merged_node_by_either_name():
    v = val(MUTUAL + "let e = even(7)\n"
            "let result = [steps(e, \"call even\")[0].count, steps(e, \"call odd\")[0].count,"
            " len(steps(e, \"call odd\")), missed(at(e, \"call nope\")), at(e, \"call even\")]")
    assert [x.payload for x in v.payload] == [8, 8, 1, True, False]


def test_plain_detail_match_still_exact():
    v = val(MUTUAL + "let e = even(3)\nlet result = [missed(at(e, \"even\")), steps(e, \"even/odd\")[0].op,"
            " missed(at(e, \"eve\"))]")
    # a bare member name matches like a bare detail does; a prefix does not
    assert [x.payload for x in v.payload] == [False, "call", True]


# --- 6. contrast: two histories side by side ----------------------------------

REPORT = ("fn parse_qty(row) { note(\"qty of \" + row.name, num(row.qty)) }\n"
          "fn add(a, b) { a + b }\n"
          "fn report(rows) { fold(add, 0, map(parse_qty, rows)) }\n"
          "let monday = report([@{name: \"alpha\", qty: \"10\"}, @{name: \"beta\", qty: \"30\"}])\n"
          "let tuesday = report([@{name: \"alpha\", qty: \"10\"}, @{name: \"beta\", qty: \"3O\"}])\n")


def test_contrast_renders_origin_paths_side_by_side():
    v = val(REPORT + "let result = contrast(monday, tuesday)")
    text = v.payload
    lines = text.splitlines()
    assert lines[0].startswith("origin 1 of 1 (value)")
    # the root pair on one line, the origin pair on one line
    assert any("let monday" in ln and "let tuesday" in ln for ln in lines)
    assert any('"30" ← literal' in ln and '"3O" ← literal' in ln for ln in lines)
    # the origin is the deepest line and marked
    assert lines[-1].lstrip().startswith("▶")
    assert v.inputs[0].op == "contrast"


def test_contrast_of_identical_histories():
    v = val(REPORT + "let result = contrast(monday, monday)")
    assert v.payload == "no divergence"


def test_contrast_accepts_why_values_and_misses():
    v = val("let a = num(\"x\")\nlet b = num(\"y\")\nlet result = contrast(why a, b)")
    assert '"x" ← literal' in v.payload and '"y" ← literal' in v.payload


# --- 7. n-way diverge ---------------------------------------------------------

def test_diverge_over_a_list_of_runs_tags_the_odd_one_out():
    src = REPORT + ("let wednesday = report([@{name: \"alpha\", qty: \"10\"}, @{name: \"beta\", qty: \"30\"}])\n"
                    "let d = diverge([monday, tuesday, wednesday])\n"
                    "let result = [len(d), d[0].which, d[0].kind, d[0].b.value]")
    v = val(src)
    assert [x.payload for x in v.payload] == [1, 1, "value", "3O"]


def test_diverge_list_edge_cases():
    v = val("let result = [len(diverge([1])), len(diverge([])), missed(diverge(5)), missed(diverge([1, 2]))]")
    assert [x.payload for x in v.payload] == [0, 0, True, False]
    v2 = val("let result = diverge([1, 2])[0].which")
    assert v2.payload == 1


# --- 8. gc_relief is scoped ---------------------------------------------------

def test_gc_relief_restores_thresholds():
    old = gc.get_threshold()
    interp = Interpreter(gc_relief=True)
    interp.run("let x = 1")
    assert gc.get_threshold() == old
    try:
        interp.run("let y = (")   # parse error propagates; thresholds restored
    except Exception:
        pass
    assert gc.get_threshold() == old
    assert Interpreter().gc_relief is False
