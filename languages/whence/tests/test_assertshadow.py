"""Round 498 (language C). Tests for `assertshadow.py`, and the tree-wide
gate round 494's next-step #1 asked for.

    "The AST shadow gate is ONE NODE DEEP. ... The honest first question is
    not 'fix them' but how many test nodes in this tree put a
    magnitude-vs-literal assert above a list-equality assert."

THE ORDER OF THIS FILE IS PART OF ITS ARGUMENT, and it is the same order
round 494 used for the same reason:

  1. the predicates, falsified in BOTH directions on synthetic input;
  2. a LIVE pytest run proving the shadow is real -- not argued from the
     language reference, run;
  3. the gate, against the ledger on disk;
  4. this file's own footprint, swept by the instrument it tests.

Every assertion here is written shape-first. A file that gates against
count-above-shape and contains one would be the fourth instance in this
program of an instrument reproducing the defect it measures, and section 4
is what stops that being a claim.
"""

import ast
import json
import os
import subprocess
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import assertshadow as A                                       # noqa: E402
import curecheck as _C                                         # noqa: E402


def _fn(src, name=None):
    """Parse one function out of a source string."""
    tree = ast.parse(textwrap.dedent(src))
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if name:
        fns = [n for n in fns if n.name == name]
    return tree, fns[0]


def _pairs(src, name=None):
    tree, fn = _fn(src, name)
    _records, pairs = A._scan_function(tree, fn, "<synth>")
    return pairs


# ---------------------------------------------------------------------------
# 1. the predicates, both directions
# ---------------------------------------------------------------------------

def test_the_predicate_agrees_with_round_494s_on_round_494s_own_examples():
    """`is_magnitude_strict` must BE `_count_asserts`, not merely resemble
    it, or the tree-wide number is not comparable with the node-level one
    round 494 published. These are the exact expressions round 494's two
    falsification tests used."""
    fires = ["len(rows) == 114", "len(building) == 104",
             "stats['unresolved_args'] > 0"]
    holds = ["sorted(r['cls'] for r in rest) == ['a', 'b']",
             "x == True", "a == b"]
    got = [(e, A.is_magnitude_strict(ast.parse(e, mode="eval").body))
           for e in fires + holds]
    assert got == [(e, True) for e in fires] + [(e, False) for e in holds]


def test_the_widening_is_the_literals_side_and_the_not_equal_op():
    """`is_magnitude` is NOT a pure widening of round 494's predicate, and
    this table is where round 498 found that out.

    It widens on two cases (the literal may be on the left, and `!=`
    counts) and it NARROWS on one: `assert 1 == 1` satisfies
    `_count_asserts`, because that predicate only asks whether the
    right-hand side is an integer, and a comparison of two literals is not
    a claim about anything. Measured over `tests/`, the two predicates
    disagree on exactly TWO asserts, both `r.returncode != 0`
    (`test_v10.py:684`, `test_v40.py:131`), and neither forms a pair -- so
    the tree-wide candidate count is the same under either, which is what
    makes it comparable with round 494's node-level number."""
    cases = [
        ("114 == len(rows)", False, True),      # literal on the left
        ("len(rows) != 0", False, True),        # NotEq
        ("len(rows) == 114", True, True),       # both
        ("1 == 1", True, False),                # THE NARROWING
        ("x == 'a'", False, False),             # not an int
    ]
    got = [(e, A.is_magnitude_strict(ast.parse(e, mode="eval").body),
            A.is_magnitude(ast.parse(e, mode="eval").body)) for e, _s, _w in cases]
    assert got == cases


def test_a_shape_assertion_needs_a_NON_EMPTY_display():
    """`assert bad == []` is an emptiness claim and carries no composition
    to lose -- the property that made round 494's eleven-class list worth
    protecting in the first place. It is classified apart."""
    got = [(e, A.classify(ast.parse(e, mode="eval").body)) for e in [
        "sorted(x) == ['a', 'b']",
        "got == {'Prov', 'MergedProv'}",
        "d == {'a': 1}",
        "('f.py', 'k', 1, 0) in bad",
        "bad == []",
        "x == y",
        "len(x) == 3",
    ]]
    assert got == [
        ("sorted(x) == ['a', 'b']", "shape"),
        ("got == {'Prov', 'MergedProv'}", "shape"),
        ("d == {'a': 1}", "shape"),
        ("('f.py', 'k', 1, 0) in bad", "shape"),
        ("bad == []", "shape_empty"),
        ("x == y", "other"),
        ("len(x) == 3", "magnitude"),
    ]


def test_execution_order_branch_and_nesting_are_all_decided_correctly():
    """Nine synthetic functions, one behaviour each, as ONE table.

    Each of these was a wrong answer some version of `_scan_function` gave.
    Opposite arms of an `if` are not a shadow; an `except:` body is visible
    at all (`ExceptHandler` is not an `ast.stmt`, and the first version
    walked straight past it); a nested `def`'s asserts are not this
    function's order."""
    src = """
        def test_plain_shadow():
            assert len(rows) == 114
            assert sorted(x) == ['a', 'b']

        def test_shape_first_is_fine():
            assert sorted(x) == ['a', 'b']
            assert len(rows) == 114

        def test_opposite_branches_do_not_shadow():
            if flag:
                assert len(rows) == 114
            else:
                assert sorted(x) == ['a', 'b']

        def test_a_loop_body_shadows_what_follows_it():
            for r in rows:
                assert len(r) == 3
            assert sorted(x) == ['a', 'b']

        def test_an_empty_display_is_not_shadowed():
            assert len(rows) == 114
            assert bad == []

        def test_the_literal_may_be_on_the_left():
            assert 114 == len(rows)
            assert sorted(x) == ['a']

        def test_an_except_body_is_visible():
            try:
                f()
            except ValueError:
                assert len(rows) == 2
                assert sorted(x) == ['a']

        def test_a_nested_def_is_not_this_functions_order():
            def helper():
                assert len(z) == 1
            assert sorted(x) == ['a']

        def test_no_asserts_at_all():
            pass
    """
    tree = ast.parse(textwrap.dedent(src))
    got = []
    for fn in tree.body:
        _r, pairs = A._scan_function(tree, fn, "<synth>")
        got.append((fn.name, len(pairs),
                    tuple(p["magnitude_conditional"] for p in pairs)))
    assert got == [
        ("test_plain_shadow", 1, (False,)),
        ("test_shape_first_is_fine", 0, ()),
        ("test_opposite_branches_do_not_shadow", 0, ()),
        ("test_a_loop_body_shadows_what_follows_it", 1, (True,)),
        ("test_an_empty_display_is_not_shadowed", 0, ()),
        ("test_the_literal_may_be_on_the_left", 1, (False,)),
        ("test_an_except_body_is_visible", 1, (True,)),
        ("test_a_nested_def_is_not_this_functions_order", 0, ()),
        ("test_no_asserts_at_all", 0, ()),
    ]


def test_independence_is_about_subjects_and_not_about_adjacency():
    """THE AXIS THAT SEPARATES THE MECHANISM FROM THE COST.

    Round 494's instance on the left, an ordinary two-assert unit test on
    the right. Both are shadows mechanically; only the first hides
    anything, because only in the first do the two assertions move for
    different reasons."""
    round_494 = _pairs("""
        def test_a(rows, rest):
            assert len(rows) == 114
            assert sorted(r['cls'] for r in rest) == ['attribute', 'call']
    """)
    ordinary = _pairs("""
        def test_b():
            assert env.get('result').payload == 15
            assert [c['ok'] for c in env.checks] == [True, True]
    """)
    assert [p["independent"] for p in round_494] == [True]
    assert [p["independent"] for p in ordinary] == [False]
    assert ordinary[0]["shared_subjects"] == ["env"]


def test_a_precondition_over_a_fixture_the_test_writes_is_not_tree_derived():
    """Round 494's own `test_a_compensating_move...` is the case this axis
    exists for: its `== 1` is over a `tmp_path` the test wrote three lines
    earlier and cannot drift. `harvest_tests` appears in `_TREE_READS`, so
    without the pytest-builtin short-circuit this node reads as costly."""
    fixture_owned = _fn("""
        def test_a(tmp_path):
            _pa, sa = dc.harvest_tests(str(tmp_path), by_file=True)
            assert sa['nonconstant_programs'] == 1
            assert sorted(bad) == ['test_aa.py', 'test_bb.py']
    """)[1]
    session_fixture = _fn("""
        def test_b(harvest, ledger):
            assert stats['programs'] >= 829
            assert (zips[0]['file'],) == ('test_v30.py',)
    """)[1]
    no_args_reads_the_tree = _fn("""
        def test_c():
            rows = C.survey(C.field_programs())
            assert len(rows) == 5
            assert dirty == ['a.lang', 'b.lang']
    """)[1]
    assert [A.tree_derived(f) for f in
            (fixture_owned, session_fixture, no_args_reads_the_tree)] == \
        [False, True, True]


def test_the_three_reorder_refusals_each_fire_on_their_own_case():
    """Each of these was a wrong `reorder` verdict before it was measured
    against the tree, and acting on any of them would have damaged a test.

      * REBINDING is the dangerous one -- `test_v10.py` runs a subprocess
        into `r`, asserts on it, then runs a SECOND subprocess into the
        same `r`. Moving the first assertion down would silently re-point
        it and the test would still PASS.
      * A GUARD must stay above the subscript it guards, or an empty list
        raises `IndexError` instead of failing an assertion.
      * Different NESTING cannot be reordered; the same `try:` body can,
        which is `test_v48.py`'s case and which the first version refused.
    """
    rebound = _pairs("""
        def test_a():
            r = run()
            assert r.returncode == 0
            r = run_again()
            assert [l[:4] for l in r.lines] == ['DIFF', 'DIFF']
    """)
    guard = _pairs("""
        def test_b():
            assert len(zips) == 1
            assert (zips[0]['file'], zips[0]['cls']) == ('a.py', 'z')
    """)
    not_a_guard = _pairs("""
        def test_c():
            assert stats['programs'] >= 829
            assert (zips[0]['file'], zips[0]['cls']) == ('a.py', 'z')
    """)
    same_try = _pairs("""
        def test_d():
            try:
                assert rep['violations'] == 46
                assert broken == {'Prov', 'MergedProv', 'Env'}
            finally:
                restore()
    """)
    across_nesting = _pairs("""
        def test_e():
            for r in rows:
                assert len(r) == 3
            assert sorted(x) == ['a', 'b']
    """)
    assert [p["remedy"] for p in
            rebound + guard + not_a_guard + same_try + across_nesting] == \
        ["split", "split", "reorder", "reorder", "split"]


def test_a_shape_assertion_that_already_implies_the_count_is_a_deletion():
    """`assert len(sig) == 3` above `assert sig == ['a', 'b', 'c']` is pure
    redundancy: the list pins the length, the membership and the order. The
    count is a strict subset of it and makes it unreachable.

    The element count must MATCH -- an inequality between them means the
    two assertions disagree and one of them is already wrong, which is not
    a case to offer a deletion for."""
    same = _pairs("""
        def test_a():
            assert len(sig) == 3
            assert sig == ['acc', 'elem', 'idx']
    """)
    mismatched = _pairs("""
        def test_b():
            assert len(sig) == 4
            assert sig == ['acc', 'elem', 'idx']
    """)
    not_a_len = _pairs("""
        def test_c():
            assert sig['n'] == 3
            assert sig['names'] == ['acc', 'elem', 'idx']
    """)
    assert [p["remedy"] for p in same + mismatched + not_a_len] == \
        ["delete_count", "reorder", "reorder"]


def test_git_history_separates_a_repin_from_a_block_rewrite():
    """`git log -L` follows a moving line range, so a commit that replaced a
    whole test body reads as an edit to "the line". Four of the seven
    literal changes this round found in `tests/` are that, including three
    from one commit (`dbaf51ba`) whose recorded `before` is a different
    assertion entirely. A shadow that "fired" is a RE-PIN: identical
    skeleton, different number."""
    repin = ("assert len(shared) == 20, sorted(shared)",
             "assert len(shared) == 24, sorted(shared)")
    rewrite = ("assert set(guest[0]) and len(guest[0]) == 3",
               "assert len(guest[0]) == 4")
    assert [A._skeleton(repin[0]) == A._skeleton(repin[1]),
            A._skeleton(rewrite[0]) == A._skeleton(rewrite[1])] == [True, False]
    assert A._ints("assert len(x) == 114") == ["114"]


# ---------------------------------------------------------------------------
# 2. the shadow is real: a LIVE pytest run, not an argument
# ---------------------------------------------------------------------------

_SHADOWED = '''
def test_subject():
    rows = [1, 2, 3]
    rest = ["WRONG"]
    assert len(rows) == 999, len(rows)
    assert sorted(rest) == ["attribute"], rest
'''

_REORDERED = '''
def test_subject():
    rows = [1, 2, 3]
    rest = ["WRONG"]
    assert sorted(rest) == ["attribute"], rest
    assert len(rows) == 999, len(rows)
'''


def _run_pytest(tmp_path, src, name):
    path = tmp_path / name
    path.write_text(src, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider",
         "-q", str(path)],
        capture_output=True, text=True, cwd=str(tmp_path), timeout=120)


def test_pytest_really_does_report_only_the_first_failure(tmp_path):
    """THE DEMONSTRATION. Two files, both with BOTH assertions false, and
    the only difference is their order. pytest reports the count in one and
    the shape in the other -- so on a round where the count moves, the
    shape assertion's verdict is not merely unreported, it is unknown.

    Round 494 established this by reading pytest's behaviour and by finding
    a stale pin that had survived six red rounds. This runs it. Without a
    demonstration the whole census rests on a claim about a tool."""
    bad = _run_pytest(tmp_path, _SHADOWED, "test_shadowed_probe.py")
    good = _run_pytest(tmp_path, _REORDERED, "test_reordered_probe.py")
    assert [bad.returncode, good.returncode] == [1, 1]
    assert ["len(rows) == 999" in bad.stdout,
            "sorted(rest) ==" in bad.stdout] == [True, False]
    assert ["sorted(rest) ==" in good.stdout,
            "len(rows) == 999" in good.stdout] == [True, False]


def test_the_sweep_calls_the_probe_pair_exactly_what_it_is(tmp_path):
    """The same two files through the instrument. A gate that disagreed
    with the demonstration next to it would be worse than no gate."""
    for name, src in (("test_shadowed_probe.py", _SHADOWED),
                      ("test_reordered_probe.py", _REORDERED)):
        (tmp_path / name).write_text(src, encoding="utf-8")
    got = [(f["file"], len(f["pairs"])) for f in A.scan_tree(str(tmp_path))]
    assert got == [("test_reordered_probe.py", 0),
                   ("test_shadowed_probe.py", 1)]


# ---------------------------------------------------------------------------
# 3. the gate
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def live():
    return A.scan_tree()


@pytest.fixture(scope="module")
def declared():
    return A.load_census()


def test_no_new_COSTLY_shadow_has_entered_the_tree(live, declared):
    """THE HARD GATE. A costly shadow is one whose count is INDEPENDENT of
    the shape assertion below it AND derived from data the test does not
    own -- the corpus, a registry, a subprocess, another system's files.
    That is the population round 494's instance belonged to.

    Round 498 took this from 9 nodes to 2, and both survivors are declared
    FALSE POSITIVES of the `tree_derived` heuristic rather than debt:

      * `test_v10.py::test_ref_diff_...` -- `r.returncode == 0` and
        `s.count(old) > 1` are preconditions for reading a subprocess's
        output. Reordering the first would re-point it at a second
        subprocess (see the rebinding refusal above); reordering the others
        would report a list mismatch where the real fact is that the run
        failed. Neither count can drift with the corpus.
      * `test_v30.py::test_the_guest_never_merges_a_tail_loop` -- its own
        docstring says the pin is deliberately `max(host) > 1 and
        set(guest) == {1}`, a conjunction over an INLINE program. It is
        flagged only because the node takes the `lib` session fixture.

    Both are named here rather than exempted in the instrument, because an
    exemption list inside a checker is a place for a real defect to hide."""
    assert A.costly_ids(live) == declared["costly_nodes"], (
        "the set of costly shadow nodes has moved. A NEW entry is a count "
        "over data the test does not own, standing above an assertion about "
        "something else -- put the count below it, or say here why it is a "
        "false positive. Regenerate with: cd languages/whence && python3 "
        "assertshadow.py --history --json %s" % A.census_path())


def test_the_full_census_matches_the_ledger_on_disk(live, declared):
    """The ratchet. Set difference, not a count comparison -- this file
    exists because a count hid a set, and a census whose own gate compared
    magnitudes would be the joke telling itself.

    Named separately from the costly gate so that adding an ordinary
    two-assert shadow (which is usually harmless) reddens ONE node with a
    regeneration command, and never the node that means something."""
    missing, extra = A.check_census(declared, live)
    assert (missing, extra) == ([], []), (
        "GONE %s / NEW %s -- regenerate and read the diff: cd "
        "languages/whence && python3 assertshadow.py --history --json %s"
        % (missing, extra, A.census_path()))


def test_the_ledgers_totals_are_the_sums_of_its_own_rows(live, declared):
    """A ledger that is regenerated to make a red go away should at least
    be internally checkable. Every headline is a SUM over the rows, so this
    re-derives them from `nodes` rather than trusting `totals`."""
    rows = [p for n in declared["nodes"].values() for p in n["pairs"]]
    t = declared["totals"]
    assert [t["candidates"], t["pairs"], t["pairs_costly"],
            t["pairs_independent"]] == [
        len(declared["nodes"]), len(rows),
        sum(1 for p in rows if p["independent"] and p["tree_derived"]),
        sum(1 for p in rows if p["independent"])]


def test_the_one_node_gate_round_494_built_still_holds_and_agrees(live):
    """Round 494's gate covers one function named by a constant. This
    module covers the tree. If they ever disagree ABOUT THAT FUNCTION, one
    of them has a predicate the other does not, and finding out from a diff
    of two numbers in two round files is the expensive way.

    `test_testcorpus_contributions.py` is the file that holds round 494's
    gate; the node it guards must be clean under this sweep too."""
    import test_testcorpus_contributions as C494    # noqa: PLC0415
    fns = {f["func"]: f for f in live
           if f["file"] == "test_testcorpus_census.py"}
    assert [C494.SHAPE_NODE in fns,
            fns[C494.SHAPE_NODE]["pairs"] if C494.SHAPE_NODE in fns else None] \
        == [True, []]


# ---------------------------------------------------------------------------
# 4. this file's own footprint
# ---------------------------------------------------------------------------

def test_this_file_contains_no_shadow_of_its_own(live):
    """Section 4, and the reason the other three are ordered as they are.

    An instrument that measures a defect and contains it has happened in
    this program before -- round 494's gate landed in the same commit as a
    new test with six independent shadow pairs in it, which is how this
    round found that node. This assertion is what makes "written
    shape-first" a fact rather than an intention."""
    mine = [f for f in live if f["file"] == os.path.basename(__file__)]
    assert [(f["func"], f["pairs"]) for f in mine if f["pairs"]] == []


def test_the_census_file_is_where_the_module_says_it_is():
    """`census_path()` resolves through `curecheck.AGI_ROOT` and reads
    nothing at import -- curecheck's own round-413 notes, restated in
    `depthcensus.contributions_path`: a sixth `__file__`-derived root
    blocks every mutation campaign at the door, and a `state/` read at
    import time aborts COLLECTION of the whole suite."""
    p = A.census_path()
    assert [os.path.isabs(p), p.startswith(_C.AGI_ROOT),
            os.path.relpath(p, _C.AGI_ROOT)] == \
        [True, True, os.path.join("state", "whence",
                                  "assert-shadow-census.json")]


def test_the_cli_check_exits_zero_on_this_tree():
    """The CLI is the regeneration path every failure message names, so it
    is run here rather than assumed to work."""
    r = subprocess.run(
        [sys.executable, "assertshadow.py", "--check"],
        cwd=A.HERE, capture_output=True, text=True, timeout=300)
    assert [r.returncode, "ledger agrees" in r.stdout] == [0, True], \
        r.stdout + r.stderr


def test_the_cli_check_goes_red_on_a_tree_with_an_undeclared_shadow(tmp_path):
    """A gate nobody has seen go red is a gate nobody has tested.

    `--check` against a two-file tree the ledger knows nothing about: it
    must exit 1 and NAME the node, not merely disagree about a total."""
    (tmp_path / "test_probe.py").write_text(_SHADOWED, encoding="utf-8")
    live = A.scan_tree(str(tmp_path))
    missing, extra = A.check_census(json.loads('{"nodes": {}}'), live)
    assert (missing, extra) == ([], ["test_probe.py::test_subject"])
    cm, ce = A.check_costly(
        {"costly_nodes": ["gone.py::test_x"]}, live)
    assert (cm, ce) == (["gone.py::test_x"], [])


# ---------------------------------------------------------------------------
# 5. ROUND 524 — the sub-document every other check projects.
#
# `_residual` (round 516) is total over the census's TOP-LEVEL keys and buys
# that totality by naming two exclusions, `nodes` and `costly_nodes`, on the
# ground that `check_census`, `check_coordinates` and `check_costly` already
# report them. Round 524 mutated one leaf at a time UNDER `nodes` and asked
# the CLI: seven of eight mutations came back "ledger agrees".
#
# The order of this section follows the file's own argument: the predicates
# first, on synthetic input, then the structural sweep against the live
# document, then the CLI.
# ---------------------------------------------------------------------------

def _perturb(v):
    """A different value of the same shape. `None` is not a shape."""
    if isinstance(v, bool):
        return not v
    if isinstance(v, int):
        return v + 7
    if isinstance(v, str):
        return v + "  # round-524 perturbation"
    if isinstance(v, list):
        return v + ["round-524"]
    if isinstance(v, dict):
        return dict(v, round_524="perturbation")
    if v is None:
        return 0
    raise AssertionError("no perturbation for %r" % type(v))


#: The two pair fields that are UNCOMPARABLE without `--history`, which
#: `--check` deliberately does not run. Named here rather than left as a
#: silent pass: `literal_edits` and `repins` are NOT in this list because
#: `totals` sums both, so `check_internal` reaches them from the other side
#: with no tree at all. `moves` and `commits_touching` feed no total, so
#: nothing can see them on a `--check` run -- and
#: `test_the_history_only_exemption_is_conditional_and_not_a_hole` proves
#: that is a property of the RUN and not of the checker.
_HISTORY_BLIND = ("commits_touching", "moves")


def _any_check_fires(declared, funcs):
    """Every finding-producing check in the module, as one dict of booleans.

    The point of returning the whole dict rather than `or`-ing it is that a
    failure names WHICH check was supposed to see the mutation, which is
    what the round-524 measurement was missing when it started."""
    missing, extra = A.check_census(declared, funcs)
    cmiss, cextra = A.check_costly(declared, funcs)
    return {
        "check_census": bool(missing or extra),
        "check_costly": bool(cmiss or cextra),
        "check_coordinates": bool(A.check_coordinates(declared, funcs)),
        "check_node_bodies": bool(A.check_node_bodies(declared, funcs)),
        "check_internal": bool(A.check_internal(declared)),
        "_residual": bool(A._residual(declared, funcs)),
    }


def _leaves(declared):
    """`(label, mutate)` for every leaf under `nodes`, read OUT OF THE LIVE
    DOCUMENT rather than typed here.

    That is the whole design of this sweep. A hand-written list of eleven
    field names is a twelfth artefact that can go stale, and the field that
    goes uncovered would be the one somebody adds next -- which is exactly
    how `nodes` came to have ten unchecked leaves in the first place."""
    nid = sorted(k for k, v in declared["nodes"].items() if v.get("pairs"))[0]
    out = [("nodes[*].lineno",
            lambda d: d["nodes"][nid].update(
                lineno=_perturb(d["nodes"][nid]["lineno"])))]
    for field in sorted(declared["nodes"][nid]["pairs"][0]):
        def mk(f):
            return lambda d: d["nodes"][nid]["pairs"][0].__setitem__(
                f, _perturb(d["nodes"][nid]["pairs"][0][f]))
        out.append(("nodes[*].pairs[0].%s" % field, mk(field)))
    out.append(("nodes[*].pairs  (one DELETED)",
                lambda d: d["nodes"][nid]["pairs"].pop(0)))
    out.append(("nodes[*].pairs  (one DUPLICATED)",
                lambda d: d["nodes"][nid]["pairs"].append(
                    json.loads(json.dumps(d["nodes"][nid]["pairs"][0])))))
    return out


def test_every_leaf_under_nodes_is_seen_by_some_check(live, declared):
    """THE STRUCTURAL GUARD, and the one round 524 exists to install.

    Round 522's lesson, in its own words, was that the guard on a whole
    class of drift was "two integer literals in one test function, not a
    structural check". This is the structural check for the class one level
    up. It enumerates the leaves from the document, so a pair field added
    by a future round arrives already covered -- or turns this red on the
    round that adds it, which is the round that can answer for it.

    Blind-by-run, not blind-by-checker: `_HISTORY_BLIND`."""
    blind = [name for name, mutate in _leaves(declared)
             if not any(_any_check_fires(
                 _mutated(declared, mutate), live).values())]
    assert blind == ["nodes[*].pairs[0].%s" % f for f in _HISTORY_BLIND]


def _mutated(declared, mutate):
    d = json.loads(json.dumps(declared))
    mutate(d)
    return d


def test_the_history_only_exemption_is_conditional_and_not_a_hole(live,
                                                                  declared):
    """`moves` and `commits_touching` are invisible because `--check` does
    not run `add_history`, NOT because `check_node_bodies` cannot see them.

    Proven by giving the live side history-shaped pairs: the same two
    mutations are then reported. An exemption that survives its own
    precondition being lifted would be a hole."""
    scored = json.loads(json.dumps(live))
    for f in scored:
        for p in f.get("pairs", []):
            p.setdefault("literal_edits", 0)
            p.setdefault("repins", 0)
            p.setdefault("moves", [])
            p.setdefault("commits_touching", 0)
    by_name = dict(_leaves(declared))
    seen = [f for f in _HISTORY_BLIND
            if A.check_node_bodies(
                _mutated(declared, by_name["nodes[*].pairs[0].%s" % f]),
                scored)]
    assert seen == list(_HISTORY_BLIND)


def test_check_internal_needs_no_tree_and_says_so_by_taking_none(declared):
    """The only check in this module that still works on a census whose
    tree is gone. It takes one argument on purpose."""
    flag = json.loads(json.dumps(declared))
    nid = sorted(k for k, v in flag["nodes"].items()
                 if any(p["independent"] and p["tree_derived"]
                        for p in v.get("pairs", [])))[0]
    for p in flag["nodes"][nid]["pairs"]:
        p["tree_derived"] = False
    keys = [k for k, _why in A.check_internal(flag)]
    assert [A.check_internal(declared), "costly_nodes" in keys] == [[], True]


def test_costly_nodes_and_nodes_are_two_records_of_one_fact(declared):
    """On this tree they agree, which is the positive control: the check
    above is not passing because the derivation is wrong in the same
    direction as the file."""
    assert A.costly_from_nodes(declared["nodes"]) == \
        sorted(declared["costly_nodes"])


def test_totals_derivable_from_nodes_agree_with_the_totals_on_disk(declared):
    """Twelve of the census's totals are sums over `nodes` and are
    re-derived here from `nodes` alone. The ones that are NOT derivable
    (`files`, `test_functions`, `asserts`, `assert_kinds`,
    `functions_with_*`) are absent from `totals_from_nodes` rather than
    approximated, and that absence is asserted as a shape."""
    got = A.totals_from_nodes(declared["nodes"])
    not_derivable = ("files", "test_functions", "asserts", "assert_kinds",
                     "functions_with_magnitude", "functions_with_shape")
    assert [sorted(k for k in not_derivable if k in got),
            [(k, got[k], declared["totals"][k]) for k in sorted(got)
             if declared["totals"].get(k) != got[k]]] == [[], []]


def test_check_node_bodies_matches_pairs_by_index_and_says_which(live):
    """Matching by TEXT is what blinds `check_coordinates` to a text edit,
    and a text edit is what this function is for. So it matches by index,
    and a REORDER shows here as several field diffs -- asserted rather than
    left as a docstring claim."""
    one = [f for f in A.candidates(live) if len(f["pairs"]) >= 2][0]
    nid = "%s::%s" % (one["file"], one["func"])
    d = A.build_census(live)
    d["nodes"][nid]["pairs"] = list(reversed(d["nodes"][nid]["pairs"]))
    where = [w for n, w, _dv, _lv in A.check_node_bodies(d, live) if n == nid]
    assert [A.check_node_bodies(A.build_census(live), live),
            len(where) > 1, all(w.startswith("pairs[") for w in where)] == \
        [[], True, True]


def test_the_residual_excludes_exactly_the_keys_that_have_a_delegate():
    """`_residual`'s `ignore` tuple is a promise that something else ranges
    over those keys. Round 524's measurement is that the promise was true
    for one leaf of eleven. Pin the tuple: a THIRD exclusion added later
    must arrive with its delegate, and this is the test that asks for it."""
    src = ast.parse(open(A.__file__, encoding="utf-8").read())
    fn = next(n for n in ast.walk(src)
              if isinstance(n, ast.FunctionDef) and n.name == "_residual")
    kw = next(k for n in ast.walk(fn) if isinstance(n, ast.Call)
              for k in n.keywords if k.arg == "ignore")
    assert [e.value for e in kw.value.elts] == ["nodes", "costly_nodes"]


def test_the_cli_prints_every_check_it_gates_on():
    """The green gate and the report must range over the SAME checks. Round
    524 added two; a check gated on but never printed would exit 1 with no
    line naming why, and a check printed but not gated would print its
    findings underneath the words "ledger agrees"."""
    src = open(A.__file__, encoding="utf-8").read()
    tree = ast.parse(src)
    gate = sorted(set(
        n.id
        for node in ast.walk(tree) if isinstance(node, ast.If)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.op, ast.Not)
        and isinstance(node.test.operand, ast.BoolOp)
        and isinstance(node.test.operand.op, ast.Or)
        and any(isinstance(v, ast.Name) and v.id == "residual"
                for v in node.test.operand.values)
        for n in node.test.operand.values if isinstance(n, ast.Name)))
    report = src.split('print("GONE')[1].split("regenerate:")[0]
    ungated = [n for n in ("missing", "extra", "cmiss", "cextra", "moved",
                           "residual", "bodies", "internal") if n not in gate]
    unprinted = [n for n in ("bodies", "internal") if n not in report]
    assert [ungated, unprinted, "BODY" in report,
            "INCONSISTENT" in report] == [[], [], True, True]
