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

def test_the_corpus_is_thirty_three_programs():
    assert len(DC.corpus_paths()) == 33


@pytest.mark.whence_slow
def test_the_corpus_maximum_is_fourteen_and_it_is_self_host_lang():
    """THE NUMBER v0.44 IS BUILT ON. Marked slow (~35 s: it runs every
    example, `meta.lang` alone walks 2.5 M nodes) and kept rather than
    trimmed, because a constant justified by a corpus reading nothing
    re-takes is a constant justified by a comment."""
    rows = DC.census()
    s = DC.summarise(rows)
    assert s["programs"] == 33
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
