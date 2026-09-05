"""`depthcensus.py` — the instrument behind v0.44's number.

Round 452. Round 450's next step asked for "the deepest value any corpus
program actually builds" and nobody had measured it. The disposition banked
before the measurement (`state/whence/round-452/PREDICTIONS.md`, item 5) said
the census would land as an ARTEFACT with its own tests, so the next round to
ask re-derives the number instead of quoting round 452's. This is that half.

What is worth testing about a measuring instrument is not that it produces a
number — it is that the number means what the prose says. So:

  * `D` is the metric the bank defined, on values built by hand where the
    right answer is obvious;
  * `D` agrees with the RENDERER's own boundary, by differential, at whatever
    the cap happens to be — that is what makes "a printed value is rendered
    in full iff D <= FULL_LEVELS" a fact rather than a sentence;
  * the root set reaches values NOTHING KEEPS, which is the whole reason it
    hooks `_note_drop` instead of reading the final `Env`;
  * the walk is iterative, so measuring a deep value does not blow the host
    stack the census exists to reason about.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import depthcensus as DC                                        # noqa: E402
from whence import values as V                                  # noqa: E402
from whence.values import (                                     # noqa: E402
    FULL_SHOW_NEST, Prov, Record, full_show, wlist,
)


def node(p):
    return Prov("lit", "", 1, (), value=p)


def nest(depth):
    v = node(1)
    for _ in range(depth):
        v = node(wlist([v]))
    return v


# --------------------------------------------------------------------------
# the metric
# --------------------------------------------------------------------------

def test_scalars_are_depth_zero():
    for p in (1, 1.5, True, "s", None):
        assert DC.payload_depth(p) == 0


def test_an_empty_container_is_depth_one():
    assert DC.payload_depth(wlist([])) == 1
    assert DC.payload_depth(Record({})) == 1


@pytest.mark.parametrize("depth", [1, 2, 5, 30])
def test_a_nested_list_is_its_nesting(depth):
    assert DC.depth_of(nest(depth)) == depth


def test_depth_is_the_max_over_children_not_the_first():
    shallow, deep = node(1), nest(6)
    assert DC.depth_of(node(wlist([shallow, deep]))) == 7
    assert DC.depth_of(node(wlist([deep, shallow]))) == 7


def test_records_and_lists_alternate_without_special_casing():
    v = node(Record({"a": node(wlist([node(Record({"b": node(1)}))]))}))
    assert DC.depth_of(v) == 3
    assert DC.spine_of(v) == ["Record", "WList", "Record", "int"]


def test_a_guess_costs_a_level_because_the_renderer_descends_into_it():
    """`_show`'s `Guess` branch renders `Guess.node` at nest + 1, so the
    metric charges a level for it. The bank fixed this before measuring."""
    from whence.values import Guess
    inner = nest(2)
    g = node(Guess(inner, 0.5, ("s",)))
    assert DC.depth_of(g) == 3


def test_the_walk_is_iterative_and_survives_a_value_deeper_than_the_stack():
    """2500 levels — the depth `show_payload`'s own docstring names as the
    reason a cap exists. An instrument that could not measure it would be
    measuring the wrong thing."""
    old = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(300)
        assert DC.depth_of(nest(2500)) == 2500
    finally:
        sys.setrecursionlimit(old)


def test_shared_subvalues_are_counted_once_not_once_per_path():
    """A DAG. `D` is a property of the value graph; the RENDERER's cost is a
    property of the path count, and those are different numbers about the
    same object. Conflating them is how "O(n) in elements" got written down."""
    a = nest(3)
    v = a
    for _ in range(10):
        v = node(wlist([v, v]))
    assert DC.depth_of(v) == 13
    nodes, truncated = DC.reachable([v])
    assert truncated is False
    assert len(nodes) == 14, "a shared node walked once, not 2**10 times"


# --------------------------------------------------------------------------
# the metric agrees with the renderer — the differential that makes it a fact
# --------------------------------------------------------------------------

@pytest.mark.parametrize("depth", [1, 2, 3, 4, 10,
                                   FULL_SHOW_NEST, FULL_SHOW_NEST + 1,
                                   FULL_SHOW_NEST + 2, FULL_SHOW_NEST + 6])
def test_full_rendering_is_complete_exactly_when_depth_is_within_the_cap(depth):
    """`FULL_LEVELS` is derived from the constant, so this holds at whatever
    the cap is — which is the property that lets a later round move the cap
    and keep the instrument."""
    v = nest(depth)
    complete = "…" not in full_show(v.value)
    assert complete == (DC.depth_of(v) <= DC.FULL_LEVELS), depth


def test_the_derived_level_counts_match_the_constants():
    assert DC.FULL_LEVELS == FULL_SHOW_NEST + 1
    assert DC.SNAPSHOT_LEVELS == V.SHOW_NEST


# --------------------------------------------------------------------------
# the root set
# --------------------------------------------------------------------------

def test_a_value_nothing_keeps_is_still_measured():
    """THE REASON THE CENSUS HOOKS `_note_drop`. `map` as a bare statement
    binds nothing; a root set built from the final `Env` would report depth 0
    for a program that built a depth-3 value and threw it away."""
    src = ("map(fn(i) { [[i]] }, [1, 2])\n"
           "let kept = 1\n")
    path = _tmp_program(src)
    all_roots = DC.census_program(path, roots="all")
    env_only = DC.census_program(path, roots="env")
    assert all_roots["built_depth"] == 3
    assert env_only["built_depth"] == 0
    assert all_roots["drop_roots"] >= 1


def test_a_bound_value_is_measured_by_both_root_sets():
    path = _tmp_program("let x = [[[1]]]\n")
    assert DC.census_program(path, roots="all")["built_depth"] == 3
    assert DC.census_program(path, roots="env")["built_depth"] == 3


def test_printed_depth_is_separate_from_built_depth():
    path = _tmp_program("let deep = [[[[[1]]]]]\nprint([1])\n")
    r = DC.census_program(path)
    assert r["built_depth"] == 5
    assert r["printed_depth"] == 1
    assert r["printed_values"] == 1


def test_the_print_hook_sees_print_and_str_and_counts_each_once():
    """The hook is on the WALK (`full_show_named`), not on `full_show`.
    Round 452 had it on `full_show`, decision 53 moved `b_print` off that
    name, and the census silently stopped seeing `print` while still
    reporting a printed-depth number."""
    path = _tmp_program('print([1])\nlet s = str([[2]])\n')
    r = DC.census_program(path)
    assert r["printed_values"] == 2
    assert r["printed_depth"] == 2


def test_a_program_that_does_not_parse_is_reported_not_skipped():
    path = _tmp_program("let x = \n")
    r = DC.census_program(path)
    assert r["ok"] is False
    assert r["error"].startswith("parse:")


def test_the_node_budget_is_reported_when_it_stops_a_walk():
    path = _tmp_program("let xs = map(fn(i) { i }, range(1, 500))\n")
    r = DC.census_program(path, max_nodes=50)
    assert r["built_truncated"] is True
    assert r["deepest_at_budget"] is True
    assert r["built_nodes"] == 50


# --------------------------------------------------------------------------
# the corpus reading
# --------------------------------------------------------------------------

def test_the_corpus_is_thirty_four_programs():
    """34 since round 506 added `examples/typed.lang`. RENAMED rather than
    left reading `thirty_three` with a 34 under it: the name is the claim a
    reader sees in a `FAILED` line, and this file's own neighbour explains
    that a constant justified by a comment is not justified."""
    assert len(DC.corpus_paths()) == 34


@pytest.mark.whence_slow
def test_the_corpus_maximum_is_fourteen_and_it_is_self_host_lang():
    """THE NUMBER v0.44 IS BUILT ON. Marked slow (~35 s: it runs every
    example, `meta.lang` alone walks 2.5 M nodes) and kept rather than
    trimmed, because a constant justified by a corpus reading nothing
    re-takes is a constant justified by a comment."""
    rows = DC.census(alloc=False)
    s = DC.summarise(rows)
    assert s["programs"] == 34
    assert s["max_built_depth"] == 14
    assert s["deepest_program"] == "self_host.lang"
    assert s["max_printed_depth"] == 2
    # the honest half: nothing the corpus PRINTS was ever truncated, at the
    # old cap or the new one
    assert s["printed_values_over_cap"] == 0
    assert s["printed_marker_lines"] == 0
    assert s["programs_over_full_cap"] == 0        # true at FULL_SHOW_NEST 24
    assert s["truncated_walks"] == []


def _tmp_program(src):
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".lang")
    with os.fdopen(fd, "w") as fh:
        fh.write(src)
    _TMP.append(path)
    return path


_TMP = []


def teardown_module(module):
    for p in _TMP:
        try:
            os.unlink(p)
        except OSError:
            pass


# --------------------------------------------------------------------------
# the ALLOCATION census (round 456)
#
# The root-set census answers "how deep is the deepest value the program
# RETAINS". Round 452's own docstring named the class it could not reach and
# could not size. This half measures at CONSTRUCTION, so there is no root set
# and therefore no residual, and everything below is about the two ways that
# can go wrong: arithmetic that disagrees with the ordinary walk, and a
# patched interpreter that does not get put back.
# --------------------------------------------------------------------------

def test_payload_size_counts_the_tree_unfolding_not_the_dag():
    """N is what the RENDERER walks. `values._show` re-descends into shared
    sub-structure -- its `seen` set is for misses, not for dedup -- so a
    payload used twice is rendered twice and must be counted twice. Pinning
    this is the difference between N and "number of distinct nodes"."""
    shared = node(wlist([node(1), node(2)]))            # N = 3
    twice = wlist([shared, shared])
    assert DC._payload_size(shared.value) == 3
    assert DC._payload_size(twice) == 1 + 3 + 3
    assert DC.payload_depth(twice) == 2


def test_payload_size_of_a_leaf_and_an_empty_container():
    assert DC._payload_size(7) == 1
    assert DC._payload_size(wlist([])) == 1
    assert DC._payload_size(Record({})) == 1


def test_alloc_payload_metrics_pairs_the_two_walks():
    p = wlist([node(Record({"a": node(wlist([node(1)]))}))])
    assert DC.alloc_payload_metrics(p) == (DC.payload_depth(p),
                                           DC._payload_size(p))


def _alloc(src):
    return DC.census_program(_tmp_program(src))


def test_the_constructor_arithmetic_agrees_with_an_independent_rewalk():
    """The census reports `alloc_agrees` by recomputing its champions with
    `depth_of` and `_payload_size`, which share no code with the
    constructor-time incremental arithmetic. Two implementations, not one
    asserting about itself."""
    r = _alloc("let xs = [[1, 2], [[3]], [[[4]]]]\nprint(len(xs))\n")
    assert r["ok"], r["error"]
    assert r["alloc_agrees"] is True
    assert r["alloc_depth"] == r["alloc_depth_check"]
    assert r["alloc_size"] == r["alloc_size_check"]


def test_the_allocation_population_is_a_superset_of_the_reachable_one():
    r = _alloc("let xs = [[[1]]]\nprint(xs)\n")
    assert r["alloc_depth"] >= r["built_depth"]
    assert r["alloc_nodes"] >= r["built_nodes"]


def test_a_value_no_root_reaches_is_invisible_to_the_root_walk_and_seen_here():
    """The residual class round 452 named, made concrete. `deep` binds a
    local, uses it only to produce an int, and returns the int: the deep list
    is not a top-level binding, not a discarded statement value, not printed,
    and not an input to anything that survives -- so the root walk cannot
    reach it and the allocation census can."""
    src = ("fn deep() {\n"
           "  let a = [[[[[[[1]]]]]]]\n"
           "  0\n"
           "}\n"
           "let n = deep()\n"
           "print(n)\n")
    r = _alloc(src)
    assert r["ok"], r["error"]
    assert r["alloc_depth"] == 7
    assert r["built_depth"] == 0                  # the root walk sees nothing
    assert r["alloc_depth_reachable"] is False


def test_a_returned_value_is_reached_by_both_censuses():
    """The control for the test above: change one line so the deep value is
    RETURNED, and the root set finds it. Without this the previous test only
    shows that the root walk is bad at something, not that it is bad at the
    specific thing."""
    src = ("fn deep() {\n"
           "  let a = [[[[[[[1]]]]]]]\n"
           "  a\n"
           "}\n"
           "let n = deep()\n"
           "print(len(n))\n")
    r = _alloc(src)
    assert r["ok"], r["error"]
    assert r["built_depth"] == r["alloc_depth"] == 7
    assert r["alloc_depth_reachable"] is True
    # `len(a)` would ALSO make it reachable -- an intermediate sub-expression
    # is an input, and round 452's docstring says so. The residual is values
    # nothing consumes, not values nothing binds.


def test_a_list_grown_by_push_is_measured_through_the_shared_buffer():
    """`values.WList` is a length-bounded view over an append-only buffer, so
    a fold that pushes n times makes n views over ONE buffer. The census
    keeps per-buffer prefix aggregates for that case; this checks the answer,
    not the mechanism."""
    src = ("let xs = fold(fn(acc, i) { push(acc, [[i]]) }, [], range(40))\n"
           "print(len(xs))\n")
    r = _alloc(src)
    assert r["ok"], r["error"]
    assert r["alloc_agrees"] is True
    assert r["alloc_depth"] == 3                      # list > list > list > int
    assert r["alloc_size"] == 1 + 40 * 3              # the tip view


def test_the_interpreter_is_put_back_after_a_census_run():
    before = (V.Prov, V.MergedProv, V.Value)
    _alloc("let x = 1\nprint(x)\n")
    assert (V.Prov, V.MergedProv, V.Value) == before


def test_the_interpreter_is_put_back_even_when_the_program_fails():
    before = (V.Prov, V.MergedProv)
    r = _alloc("let x = (((\n")
    assert not r["ok"]
    assert (V.Prov, V.MergedProv) == before


def test_value_is_deliberately_not_repointed():
    """`timetravel` does `isinstance(v, Prov)` against the name it imported.
    Rebinding an isinstance TARGET to a subclass would make every node built
    before the patch fail a test it used to pass, so `_install_counting`
    patches the two constructor names and nothing else. Pinned because the
    obvious "patch every alias" edit is silently wrong."""
    cp, cm = DC._counting_classes()
    saved = DC._install_counting(cp, cm)
    try:
        assert V.Prov is cp and V.MergedProv is cm
        assert V.Value is not cp
        plain = Prov("lit", "", 1, (), value=1)
        assert isinstance(plain, V.Value)
    finally:
        DC._restore_counting(saved)
    assert V.Prov is not cp


def test_no_alloc_turns_the_second_census_off_and_says_so():
    path = _tmp_program("let xs = [[1]]\nprint(xs)\n")
    r = DC.census_program(path, alloc=False)
    assert r["alloc_on"] is False
    assert r["alloc_depth"] == 0 and r["alloc_nodes"] == 0
    assert r["alloc_agrees"] is None


# --------------------------------------------------------------------------
# the WIDTH bound, and the claim the measurement refuted
# --------------------------------------------------------------------------

def test_a_value_bigger_than_the_node_budget_need_not_stop_on_it():
    """ROUND 456'S CORRECTION, held open as a test. The census comment used
    to say `N > FULL_SHOW_NODES` was "exactly the condition" under which a
    full rendering stops on the width bound. It is not: the DEPTH cap
    truncates the walk first, and a value can be arbitrarily large in N and
    still render with `node_stopped` False. Built here by hand so the claim
    does not depend on any corpus program surviving."""
    # Narrow and deep, with the bulk BELOW the cap: the shape `self_eval.lang`
    # actually builds. A wide-AND-deep value does stop on the budget, which is
    # why the census renders rather than reasons.
    n = node(wlist([node(i) for i in range(V.FULL_SHOW_NODES + 5)]))
    for _ in range(V.FULL_SHOW_NEST + 10):
        n = node(wlist([n]))                   # branching factor ONE
    assert DC._payload_size(n.value) > V.FULL_SHOW_NODES
    assert DC.depth_of(n) > V.FULL_SHOW_NEST
    r = V.full_show_named(n)
    assert r.depth_stopped is True
    assert r.node_stopped is False


def test_a_wide_shallow_value_does_stop_on_the_node_budget():
    """The other side: within the depth cap, N decides. Together the two
    tests are why the census renders the undecided case instead of asserting
    about it."""
    wide = wlist([node(i) for i in range(V.FULL_SHOW_NODES + 10)])
    n = node(wide)
    assert DC._payload_size(wide) > V.FULL_SHOW_NODES
    r = V.full_show_named(n)
    assert r.node_stopped is True


def test_a_program_that_builds_nothing_large_reports_no_width_candidates():
    src = "let xs = " + "[" * 30 + "1" + "]" * 30 + "\nprint(len(xs))\n"
    r = _alloc(src)
    assert r["ok"], r["error"]
    assert r["alloc_depth"] == 30
    assert r["width_over_n"] == 0
    assert r["width_fired"] == 0
    assert r["width_sample_complete"] is True


def test_the_width_check_reports_its_own_cost_separately():
    """`seconds` is measured around the RUN and the width check happens
    after it. Reported apart so a program the census spends minutes on cannot
    report four seconds."""
    r = _alloc("let x = 1\nprint(x)\n")
    assert "width_seconds" in r and r["width_seconds"] >= 0.0
    assert r["seconds"] >= 0.0


def test_the_census_says_when_its_width_sample_was_not_exhaustive(monkeypatch):
    """Silence about a truncated sample is the failure mode this whole field
    exists to prevent (v0.42's rule for `dropped_scan_truncated`). Forced by
    lowering the bound to one, on a program that has more than one candidate."""
    monkeypatch.setattr(DC, "ALLOC_BUDGET_SAMPLES", 1)
    src = ("let wide = range(%d)\n"
           "let deep = fold(fn(a, i) { [a] }, wide, range(40))\n"
           "print(len(deep))\n" % (V.FULL_SHOW_NODES + 5))
    r = _alloc(src)
    assert r["ok"], r["error"]
    assert r["width_over_n"] > 1
    assert r["width_sampled"] == 1
    assert r["width_sample_complete"] is False
    # and the arithmetic half is decided without rendering anything
    assert r["width_fires_by_arithmetic"] > 0


@pytest.mark.whence_slow
def test_a_prefix_of_construction_order_is_not_a_sample():
    """ROUND 456'S METHOD FINDING, held open. `self_eval.lang` builds 15 178
    values larger than the node budget and 2 813 of them (18.5%) really do
    stop the renderer on it. The census's first bound was 400 -- and the
    first 400 in CONSTRUCTION order contain zero of them, because early
    over-budget values are the narrow-and-deep links of the reify chain and
    the wide ones come later. A uniform 400-sample would have found ~74.
    Whoever lowers ALLOC_BUDGET_SAMPLES for speed is choosing this."""
    path = os.path.join(DC.EXAMPLES, "self_eval.lang")
    import unittest.mock as mock
    with mock.patch.object(DC, "ALLOC_BUDGET_SAMPLES", 400):
        prefix = DC.census_program(path)
    assert prefix["width_over_n"] == 15178
    assert prefix["width_sampled"] == 400
    assert prefix["width_sample_complete"] is False
    assert prefix["width_fired"] == 0
    full = DC.census_program(path)
    assert full["width_sample_complete"] is True
    assert full["width_fired"] == 2813


@pytest.mark.whence_slow
def test_the_corpus_allocation_maximum_is_not_the_root_walks_number():
    """THE NUMBER ROUND 456 CORRECTS. Round 452 measured 14 and v0.44's cap
    was set against it. Over every value the corpus BUILDS the maximum is
    1201, in `self_eval.lang`, and the root walk cannot see it. Slow (the
    width check renders every over-budget value); kept for the same reason
    round 452 kept its own corpus reading."""
    rows = DC.census()
    s = DC.summarise(rows)
    assert s["max_built_depth"] == 14
    assert s["max_alloc_depth"] == 1201
    assert s["deepest_alloc_program"] == "self_eval.lang"
    assert s["alloc_invariant_violations"] == []
    assert s["alloc_disagreements"] == []
    assert "self_eval.lang" in s["alloc_champions_unreachable"]
    assert s["max_alloc_depth"] > s["full_levels"]
    assert s["width_fired"] > 0
    assert s["width_sample_incomplete"] == []
