"""Whence v0.3: structural-sharing lists, fold node, filtered steps,
tail calls with merged call nodes, and `diverge`."""

import pytest

from whence.interp import Interpreter
from whence.values import Miss, Record, WList, wlist, leaf, Prov, diverge


def result(src, **kw):
    interp = Interpreter(**kw)
    env = interp.run(src)
    return interp, env.get("result")


def val(src, **kw):
    return result(src, **kw)[1].payload


def field(rec, name):
    return rec.fields[name].payload


# --- WList: immutable views over a shared append-only buffer -----------------

def test_push_on_tip_shares_buffer_and_old_view_is_unchanged():
    a = wlist([leaf("literal", "", 1, 1)])
    b = a.push(leaf("literal", "", 1, 2))
    assert b.shares_buffer_with(a)
    assert [e.payload for e in a] == [1]
    assert [e.payload for e in b] == [1, 2]
    assert len(a) == 1 and len(b) == 2


def test_second_push_on_same_list_copies():
    a = wlist([leaf("literal", "", 1, 1)])
    b = a.push(leaf("literal", "", 1, 2))
    c = a.push(leaf("literal", "", 1, 3))
    assert not c.shares_buffer_with(a)
    assert [e.payload for e in b] == [1, 2]
    assert [e.payload for e in c] == [1, 3]
    assert [e.payload for e in a] == [1]


def test_concat_shares_when_tip_and_copies_otherwise():
    a = wlist([leaf("literal", "", 1, 1)])
    b = a.concat([leaf("literal", "", 1, 2), leaf("literal", "", 1, 3)])
    assert b.shares_buffer_with(a) and len(b) == 3
    c = a.concat([leaf("literal", "", 1, 9)])
    assert not c.shares_buffer_with(a)
    assert [e.payload for e in c] == [1, 9]


def test_view_index_is_bounded_by_its_own_length():
    a = wlist([leaf("literal", "", 1, 1)])
    a.push(leaf("literal", "", 1, 2))
    try:
        a[1]
        assert False, "index past the view must fail"
    except IndexError:
        pass


def test_wlist_equality_with_python_lists():
    x = leaf("literal", "", 1, 1)
    assert wlist([x]) == [x] and wlist([x]) == wlist([x])
    assert wlist([x]) != [] and wlist() == []


def test_language_level_aliasing_is_invisible():
    src = ("let xs = [1]\nlet a = push(xs, 2)\nlet b = push(xs, 3)\n"
           "let result = [xs, a, b, xs[0], len(xs)]")
    p = val(src)
    xs, a, b, first, n = [e.payload for e in p]
    assert [e.payload for e in xs] == [1]
    assert [e.payload for e in a] == [1, 2]
    assert [e.payload for e in b] == [1, 3]
    assert first == 1 and n == 1


def test_push_in_fold_retains_full_history_in_linear_memory():
    src = ("fn step(acc, x) { push(acc, x) }\n"
           "let result = fold(step, [], range(2000))")
    interp, v = result(src)
    assert len(v.payload) == 2000
    # every intermediate list is still reachable through the history …
    steps = [n for n, _ in _walk(v.prov) if n.op == "push"]
    assert len(steps) == 2000
    # … and they all share one buffer
    bufs = set(id(n.value.buf) for n in steps)
    assert len(bufs) == 1


def _walk(root):
    from whence.values import walk_steps
    return walk_steps(root)


# --- fold node + filtered steps ---------------------------------------------

def test_fold_has_its_own_node_with_count_and_list_input():
    src = "fn add(a, b) { a + b }\nlet result = fold(add, 0, [1, 2, 3])"
    _, v = result(src)
    node = v.prov.inputs[0]           # under `let result`
    assert node.op == "fold" and node.detail == "3 items"
    assert node.value == 6
    assert node.inputs[1].op == "list"          # the folded list


def test_fold_over_empty_list_is_seed_with_fold_node():
    src = "fn add(a, b) { a + b }\nlet result = fold(add, 7, [])"
    _, v = result(src)
    assert v.payload == 7 and v.prov.inputs[0].op == "fold"


def test_at_finds_fold_and_steps_filters_by_name():
    src = ("fn add(a, b) { a + b }\nlet total = fold(add, 0, [1, 2, 3])\n"
           "let result = [at(total, \"fold\"), len(steps(total, \"call add\")),"
           " len(steps(total, \"call\")), len(steps(total, \"nope\"))]")
    p = [e.payload for e in val(src)]
    assert p == [6, 3, 3, 0]


def test_steps_filter_rejects_non_string():
    p = val("let result = steps(1, 2)")
    assert isinstance(p, Miss) and "string step name" in p.reasons[0]


# --- tail calls ------------------------------------------------------------

LOOP = "fn go(i, acc) { if i == 0 { acc } else { go(i - 1, acc + i) } }\n"


@pytest.mark.whence_slow
def test_tail_loop_does_not_consume_depth():
    interp, v = result(LOOP + "let result = go(100000, 0)", max_depth=50)
    assert v.payload == 5000050000
    assert interp.peak_depth == 1
    assert interp.tail_calls == 100000


def test_merged_call_node_counts_frames_and_keeps_every_branch():
    _, v = result(LOOP + "let result = go(5, 0)")
    node = v.prov.inputs[0]
    assert node.op == "call" and node.detail == "go" and node.count == 6
    assert node.label() == "call go"
    ifs = [i for i in node.inputs[1:]]
    # v0.4: the five identical else-decisions are one merged node whose
    # inputs are the five conditions (v0.3: five separate `if` nodes)
    assert [(i.detail, i.count) for i in ifs] == [("took else-branch", 5)]
    assert [c.value for c in ifs[0].inputs] == [False] * 5
    assert all(i.value == 15 and i.show == "15" for i in ifs)
    # the final iteration's `if` (then-branch) is the ordinary result input
    assert node.inputs[0].op == "if" and node.inputs[0].detail == "took then-branch"


def test_step_records_expose_count_and_render_shows_it():
    src = LOOP + "let s = go(3, 0)\nlet result = steps(s, \"call go\")[0].count"
    assert val(src) == 4
    interp = Interpreter()
    interp.run(LOOP + "let s = go(3, 0)\nprint(why s)")
    assert "call go ×4" in interp.out_lines[0]


def test_non_tail_recursion_still_makes_one_node_per_call():
    src = "fn count(n) { if n == 0 { 0 } else { 1 + count(n - 1) } }\nlet result = count(3)"
    interp, v = result(src)
    assert v.prov.inputs[0].count == 1 and interp.tail_calls == 0
    assert interp.peak_depth == 4


@pytest.mark.whence_slow
def test_mutual_tail_recursion_merges_under_both_names():
    src = ("fn even(n) { if n == 0 { true } else { odd(n - 1) } }\n"
           "fn odd(n) { if n == 0 { false } else { even(n - 1) } }\n"
           "let result = even(100001)")
    interp, v = result(src, max_depth=10)
    assert v.payload is False and interp.peak_depth == 1
    node = v.prov.inputs[0]
    assert node.detail == "even/odd" and node.count == 100002


def test_tail_call_to_builtin_and_non_callable_and_wrong_arity():
    src = ("fn a(xs) { len(xs) }\nfn b() { 3(1) }\nfn c(n) { c(n, n) }\n"
           "let result = [a([1, 2]), b(), c(1)]")
    xs = [e.payload for e in val(src)]
    assert xs[0] == 2
    assert isinstance(xs[1], Miss) and "not callable" in xs[1].reasons[0]
    assert isinstance(xs[2], Miss) and "c expects 1 args, got 2" in xs[2].reasons[0]


def test_tail_position_excludes_let_rescue_and_operands():
    src = ("fn f(n) { let m = f2(n)\n m + 1 }\nfn f2(n) { n }\n"
           "fn g(n) { g2(n) rescue 0 }\nfn g2(n) { n }\n"
           "let result = [f(1), g(2)]")
    interp, v = result(src)
    assert [e.payload for e in v.payload] == [2, 2]
    assert interp.tail_calls == 0 and interp.peak_depth == 2


def test_max_iter_turns_an_infinite_tail_loop_into_a_miss():
    src = "fn spin(n) { spin(n + 1) }\nlet result = spin(0)"
    interp, v = result(src, max_iter=1000)
    assert isinstance(v.payload, Miss)
    assert "tail loop too long in spin (1000 iterations)" in v.payload.reasons[0]
    assert interp.depth == 0


def test_depth_miss_still_applies_to_non_tail_runaway():
    src = "fn spin(n) { 1 + spin(n + 1) }\nlet result = spin(0)"
    _, v = result(src, max_depth=100)
    assert "recursion too deep in spin (depth 100)" in v.payload.reasons[0]


def test_tail_loop_through_else_if_chain():
    src = ("fn f(n) { if n == 0 { \"zero\" } else if n == 1 { f(0) } else { f(n - 1) } }\n"
           "let result = f(4)")
    interp, v = result(src, max_depth=2)
    assert v.payload == "zero"
    node = v.prov.inputs[0]
    assert node.count == 5
    details = [i.detail for i in node.inputs[1:]]
    # each iteration contributes the ifs it passed through, outermost first
    assert details == ["took else-branch", "took else-branch"] * 3 + \
        ["took else-branch", "took then-branch"]


def test_the_parser_marks_tails_in_an_anonymous_fn_body_too():
    """Round 413 (SWE-loop D). The killer for a survivor `guardpin` found.

    `mark_tails(body)` appears TWICE in the parser — `Parser.statement` for
    `fn name(...) {...}` (v0.3) and `Parser.primary` for the anonymous
    `fn(...) {...}` literal (v0.14.10, round 302). The test below this one is
    named `..._only_inside_fn_bodies` and parses only the NAMED form, so it
    reaches one of the two branches. `harness/swe/guardpin.py` deleted the
    other call and ran this whole file: nothing went red.

    Two doors, one behaviour, one named guardian — round 411's shape, caught
    here before it was a bug rather than 71 rounds after.
    """
    from whence.parser import parse
    prog = parse("let f = fn(n) { if n { f(1) } else { g(2) } }")
    body = prog.stmts[0].expr.body                  # Let -> FnExpr -> Block
    branches = body.stmts[-1].expr
    assert branches.then.stmts[-1].expr.tail is True
    assert branches.otherwise.stmts[-1].expr.tail is True


def test_a_let_bound_anonymous_fn_is_a_tail_loop_like_a_named_one():
    """The behavioural half, and the one that measures what the marking BUYS.

    With `Parser.primary`'s `mark_tails(body)` dropped, this exact program
    goes from `peak_depth 1, tail_calls 300` to `peak_depth 50 (the cap),
    tail_calls 0` — the named-fn form is untouched — so the anonymous branch
    was carrying real tail-call elimination that no test observed.
    """
    src = ("let go = fn(i, acc) { if i == 0 { acc } else { go(i - 1, acc + i) } }\n"
           "let result = go(300, 0)")
    interp, v = result(src, max_depth=50)
    assert v.payload == 45150                       # 300 * 301 / 2
    assert interp.peak_depth == 1 and interp.tail_calls == 300


def test_parser_marks_tails_only_inside_fn_bodies():
    from whence.parser import parse
    from whence import ast_nodes as A
    prog = parse("fn f(n) { if n { f(1) } else { g(2) } }\nlet x = if true { f(1) } else { f(2) }")
    body = prog.stmts[0].body
    assert body.stmts[-1].expr.then.stmts[-1].expr.tail is True
    assert body.stmts[-1].expr.otherwise.stmts[-1].expr.tail is True
    top_if = prog.stmts[1].expr
    assert top_if.then.stmts[-1].expr.tail is False


# --- diverge --------------------------------------------------------------

REPORT = ("fn total(rows) { fold(fn(a, r) { a + num(r.qty) }, 0, rows) }\n"
          "let good = total([@{qty: \"30\"}, @{qty: \"12\"}])\n"
          "let bad  = total([@{qty: \"3O\"}, @{qty: \"12\"}])\n")


def test_diverge_finds_the_changed_literal():
    p = val(REPORT + "let result = diverge(good, bad)")
    assert len(p) == 1
    rec = p[0].payload
    assert field(rec, "kind") == "value"
    a, b = field(rec, "a"), field(rec, "b")
    assert field(a, "op") == "literal" and field(a, "value") == "30"
    assert field(b, "value") == "3O" and field(b, "line") == 3


def test_diverge_of_identical_histories_is_empty():
    assert val(REPORT + "let result = diverge(good, good)") == []
    src = "fn f(x) { x * 2 }\nlet a = f(3)\nlet b = f(3)\nlet result = diverge(a, b)"
    assert val(src) == []


def test_diverge_accepts_why_values_and_reports_shape_changes():
    src = ("fn f(x) { if x > 0 { x } else { [x] } }\n"
           "let a = f(1)\nlet b = f(0)\nlet result = diverge(why a, why b)")
    p = val(src)
    kinds = sorted(field(e.payload, "kind") for e in p)
    assert kinds == ["step", "value"]
    shape = [e.payload for e in p if field(e.payload, "kind") == "step"][0]
    assert field(field(shape, "a"), "op") == "arg"
    assert field(field(shape, "b"), "op") == "list"


def test_diverge_treats_equal_misses_as_same_and_differing_misses_as_value():
    src = ("fn f(s) { num(s) }\nlet a = f(\"x\")\nlet b = f(\"x\")\nlet c = f(\"y\")\n"
           "let result = [len(diverge(a, b)), len(diverge(a, c))]")
    assert [e.payload for e in val(src)] == [0, 1]


def test_diverge_is_iterative_on_deep_histories():
    src = ("fn count(n) { if n == 0 { 0 } else { 1 + count(n - 1) } }\n"
           "let a = count(3000)\nlet b = count(3000)\nlet result = diverge(a, b)")
    assert val(src) == []


def test_diverge_low_level_shape_and_order():
    lit_a = Prov("literal", "", 1, (), "1", 1)
    lit_b = Prov("literal", "", 1, (), "2", 2)
    root_a = Prov("let", "x", 2, (Prov("+", "", 1, (lit_a, lit_a), "2", 2),), "2", 2)
    root_b = Prov("let", "x", 2, (Prov("+", "", 1, (lit_b, lit_b), "4", 4),), "4", 4)
    out = diverge(root_a, root_b)
    assert [(a.op, b.op, k) for a, b, k in out] == [("literal", "literal", "value")]
