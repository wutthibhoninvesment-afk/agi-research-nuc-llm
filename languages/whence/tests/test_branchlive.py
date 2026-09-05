"""`branchlive.py` — is a guest AST BRANCH taken, not merely written?

Round 510 (language C). The fourth level of the liveness question: round
503 asked whether the Python def is referenced, 504 whether the guest name
is called in source, 506 whether the builtin runs, and this asks whether
the `if` arm is decided.

What this file pins is everything that can make the census answer a clean,
plausible, entirely false number:

  * the two `detail` strings the hook keys on are still the strings
    `interp.py` writes. A rename there would report every branch in the
    language as never taken, with nothing raised;
  * `MergedProv.__init__` still does NOT call `Prov.__init__`. That is the
    hole the module exists to cover, and if a later refactor makes the
    subclass call super() the double-count would be silent in the other
    direction;
  * a decision made inside a merged tail loop IS observed;
  * the process is left uninstrumented, including after a program raises;
  * the documented BLIND SPOTS are still blind — `rescue`'s pass-through
    builds no node, and two `if`s on one line are one bucket. Both are
    asserted so the docstring cannot go stale in the flattering direction.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import branchlive as B              # noqa: E402
from whence import values as V      # noqa: E402
from whence.interp import Interpreter   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
WHENCE = os.path.dirname(HERE)


def run(src, direct=True):
    """Census a source string the way `census_file` censuses a file."""
    program = B.parse_program(src)
    nodes = B.if_nodes(program)
    with B.BranchCounter() as c:
        r = B.run_program(src, c, direct=direct)
        hits = c.hits()
        plain = dict(c.plain)
    rows = B.attribute(nodes, hits, src.splitlines())
    return rows, r, hits, plain


def by_line(rows):
    return dict((r["line"], r) for r in rows)


# ------------------------------------------------------ the coupling --

def test_the_two_branch_details_are_still_what_interp_writes():
    """The hook keys on two literal strings written at six sites in
    `interp.py`. If they are renamed there and not here, every branch in
    the language reports as never taken and nothing raises."""
    src = open(os.path.join(WHENCE, "whence", "interp.py"),
               encoding="utf-8").read()
    assert src.count('"%s"' % B.THEN) >= 5, B.THEN
    assert src.count('"%s"' % B.ELSE) >= 5, B.ELSE
    assert src.count('"%s"' % B.THEN) == src.count('"%s"' % B.ELSE)


def test_mergedprov_does_not_call_prov_init():
    """THE REASON THIS MODULE HOOKS TWO CONSTRUCTORS. `MergedProv.__init__`
    re-inlines its parent's six slot assignments (a v0.10 speed change).
    A census hooking only the base class misses every merged run."""
    assert V.MergedProv.__init__ is not V.Prov.__init__
    import inspect
    body = inspect.getsource(V.MergedProv.__init__)
    assert "Prov.__init__" not in body, body
    assert "super(" not in body, body


# ---------------------------------------------------- the measurement --

def test_both_arms_of_a_two_armed_if_are_seen():
    rows, r, _, _ = run(
        "fn f(x) {\n"
        "  if x > 0 { \"pos\" } else { \"neg\" }\n"
        "}\n"
        "let a = f(1)\n"
        "let b = f(-1)\n")
    assert r["ok"], r["error"]
    row = by_line(rows)[2]
    assert (row["then"], row["else"]) == (1, 1)
    assert row["verdict"] == B.BOTH


def test_an_unreached_else_is_then_only():
    rows, r, _, _ = run(
        "fn f(x) {\n"
        "  if x > 0 { 1 } else { 2 }\n"
        "}\n"
        "let a = f(1)\n")
    assert r["ok"], r["error"]
    row = by_line(rows)[2]
    assert (row["then"], row["else"], row["verdict"]) == (1, 0, B.THEN_ONLY)


def test_an_if_in_a_function_nobody_calls_is_never():
    rows, r, _, _ = run(
        "fn dead(x) {\n"
        "  if x { 1 } else { 2 }\n"
        "}\n"
        "let a = 1\n")
    assert r["ok"], r["error"]
    row = by_line(rows)[2]
    assert row["verdict"] == B.NEVER
    assert row["fn"] == "dead"


def test_a_non_boolean_condition_is_undecided_not_a_branch():
    """`_if_bad` turns a non-bool condition into a miss with the SAME
    `op`, so a hook that only looked at `op` would count it as a branch."""
    rows, r, _, _ = run("let a = if 3 { 1 } else { 2 }\n")
    assert r["ok"], r["error"]
    row = by_line(rows)[1]
    assert (row["then"], row["else"]) == (0, 0)
    assert row["undecided"] == 1
    assert row["verdict"] == B.UNDECIDED_ONLY


def test_a_missing_condition_is_also_undecided():
    rows, r, _, _ = run('let a = if miss "no" { 1 } else { 2 }\n')
    assert r["ok"], r["error"]
    assert by_line(rows)[1]["undecided"] == 1


def test_an_if_with_no_else_does_not_parse_so_every_arm_is_written():
    """P6 of this round's bank, and a MISS. The census was built expecting
    to discount a synthesised `else`; since v0.19 the parser requires an
    explicit `{}` block for BOTH arms, so there is nothing to discount and
    "else never taken" is always a fact about code somebody wrote."""
    from whence.parser import ParseError
    with pytest.raises(ParseError):
        B.parse_program("fn f(x) {\n  if x > 0 { 1 }\n}\nlet a = f(1)\n")


def test_two_ifs_on_one_line_are_reported_ambiguous():
    """A provenance node carries a LINE, not a node identity. The census
    says so rather than picking one."""
    rows, r, _, _ = run(
        "let a = if true { if false { 1 } else { 2 } } else { 3 }\n")
    assert r["ok"], r["error"]
    assert len([x for x in rows if x["line"] == 1]) == 2
    assert all(x["verdict"] == B.AMBIGUOUS for x in rows if x["line"] == 1)


def test_the_walk_finds_ifs_inside_named_and_anonymous_functions():
    nodes = B.if_nodes(B.parse_program(
        "fn outer(x) {\n"
        "  let g = fn(y) { if y { 1 } else { 2 } }\n"
        "  if x { g(1) } else { 0 }\n"
        "}\n"))
    fns = sorted(n["fn"] for n in nodes)
    assert len(nodes) == 2
    assert fns == ["fn@2", "outer"], fns


# ------------------------------------------------- the merged-run hole --

def _merged_case():
    """A tail loop whose `if` decides the same way many times in a row —
    the shape `_merge_ifs` folds into one `MergedProv`."""
    return ("fn count(n, acc) {\n"
            "  if n <= 0 { acc } else { count(n - 1, acc + n) }\n"
            "}\n"
            "let total = count(200, 0)\n")


def test_a_merged_tail_loop_decision_is_seen():
    rows, r, hits, plain = run(_merged_case())
    assert r["ok"], r["error"]
    row = by_line(rows)[2]
    assert row["verdict"] == B.BOTH, row


def test_the_merged_hook_sees_decisions_the_plain_hook_does_not():
    """The module's central structural claim, measured. If this ever comes
    back empty, either the tail-loop merge changed or the hook did."""
    rows, r, hits, plain = run(_merged_case())
    assert r["ok"], r["error"]
    known = set(n["line"] for n in rows)
    merged_only = [k for k in hits if k not in plain and k[0] in known]
    assert merged_only, (sorted(hits), sorted(plain))


def test_merged_steps_counts_more_than_merged_constructor_calls():
    """A count is a lower bound: one `MergedProv` stands for `count`
    decisions. `merged_steps` is what makes that visible."""
    src = _merged_case()
    with B.BranchCounter() as c:
        r = B.run_program(src, c)
        n_merged_calls = sum(c.merged.values())
        steps = c.merged_steps
    assert r["ok"], r["error"]
    assert n_merged_calls >= 1
    assert steps > n_merged_calls


# ----------------------------------------------------- the blind spots --

def test_rescue_pass_through_builds_no_node_so_it_cannot_be_censused():
    """Asserted, not merely documented: the recovery path builds a
    `rescue` node and the pass-through path builds nothing, so this hook
    is structurally incapable of branch-censusing `rescue`. If a later
    version starts building a node on both sides, this goes red and the
    module's stated blind spot is out of date."""
    ops = []
    saved = V.Prov.__init__

    def spy(node, op, detail, line, ins=(), show=V._LAZY, value=None):
        saved(node, op, detail, line, ins, show, value)
        if op == "rescue":
            ops.append(detail)
    V.Prov.__init__ = spy
    try:
        Interpreter().run('let a = 1 rescue 2\n')
        assert ops == [], ops              # no miss: no node at all
        Interpreter().run('let b = miss "x" rescue 2\n')
        assert ops == ["recovered"], ops
    finally:
        V.Prov.__init__ = saved


# -------------------------------------------------------- the hygiene --

def test_the_hook_restores_both_constructors_after_a_raise():
    before = (V.Prov.__init__, V.MergedProv.__init__)
    with pytest.raises(ValueError):
        with B.BranchCounter():
            raise ValueError("boom")
    assert (V.Prov.__init__, V.MergedProv.__init__) == before


def test_the_hook_restores_both_constructors_after_a_guest_error():
    before = (V.Prov.__init__, V.MergedProv.__init__)
    with B.BranchCounter() as c:
        r = B.run_program("let a = (\n", c)
    assert r["ok"] is False and r["error_kind"] == "parse"
    assert (V.Prov.__init__, V.MergedProv.__init__) == before


def test_the_counter_is_not_reentrant():
    c = B.BranchCounter()
    with c:
        with pytest.raises(RuntimeError):
            c.__enter__()


def test_reset_program_clears_rather_than_rebinds():
    """Round 506's `runlive.py` shipped a `reset_program` that rebound the
    dict the wrappers close over, and reported zero for every builtin
    while the interpreter ran perfectly. Same shape, one file later."""
    c = B.BranchCounter()
    with c:
        plain = c.plain
        B.run_program("let a = if true { 1 } else { 2 }\n", c)
        assert c.plain is plain
        assert c.plain, "a decision was made and the wrapper did not see it"


# ------------------------------------------------------ the two corpora --

def test_the_case_harvest_reads_test_self_eval_by_file_location():
    """Round 509's rule: an instrument must not put a subject tree's
    parent on `sys.path`. `tests` must not become importable as a package
    as a side effect of harvesting."""
    before = list(sys.modules)
    cases = B.selfeval_cases()
    assert len(cases) >= 60, len(cases)
    assert all(isinstance(c, str) and c.strip() for c in cases)
    assert len(set(cases)) == len(cases), "the harvest must deduplicate"
    assert "tests" not in set(sys.modules) - set(before)


def test_a_mixed_shape_list_is_not_guessed_at():
    assert B._string_cases(["a", "b"]) == ["a", "b"]
    assert B._string_cases([("a", 1), ("b", 2)]) == ["a", "b"]
    assert B._string_cases(["a", 1]) is None
    assert B._string_cases([1, 2]) is None


def test_the_selfeval_program_keeps_the_library_at_its_own_line_numbers():
    """The census needs no offset only because the library comes first and
    verbatim. If a later version prepends anything, every reported line is
    wrong by a constant and nothing else would say so."""
    lib = B.library_source()
    prog = B.selfeval_program(["let result = 1"])
    assert prog.startswith(lib)
    assert prog.count('run_src("let result = 1")') == 1
    assert prog.endswith('let __out0 = run_src("let result = 1")\n')


@pytest.mark.whence_slow
def test_the_corpus_reaches_apply_builtin_arms_the_standalone_run_does_not():
    """THE ROUND'S FINDING, as a test. Round 506 asked how many branches
    of `apply_builtin` nothing reaches; the answer depends entirely on
    which corpus you drive the evaluator with, and the standalone run is
    not the one the suite uses."""
    alone = B.census_selfeval(standalone=True)
    corpus = B.census_selfeval()
    assert alone["run"]["ok"] and corpus["run"]["ok"]
    a = set((r["line"], arm) for r in B.fn_rows(alone["rows"], "apply_builtin")
            for arm in ("then", "else") if r[arm])
    c = set((r["line"], arm) for r in B.fn_rows(corpus["rows"], "apply_builtin")
            for arm in ("then", "else") if r[arm])
    assert a - c == set(), sorted(a - c)
    assert len(c - a) >= 20, len(c - a)


@pytest.mark.whence_slow
def test_the_selfeval_census_is_about_the_library_only():
    c = B.census_selfeval()
    assert c["cases"] >= 60
    assert all(r["line"] <= c["library_lines"] for r in c["rows"])
    assert c["summary"]["nodes"] >= 200
