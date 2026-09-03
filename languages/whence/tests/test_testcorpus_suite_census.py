"""Round 470 (language C): the suite-mode `--tests` census, as a slow-tier
unit of its own.

This file exists because round 469 decided it should, in its §5, and said
where it must NOT go:

    "`test_depthcensus.py` is ALREADY the most expensive unit in the tier at
     472.2 s, 33% of the whole thing, and its three marked tests census the
     33-program `examples/` corpus, not the 765-program `--tests` corpus. So
     the suite-mode `--tests` census really is uncovered, and it really does
     guard something the fast tier cannot ...
     But it must not go into `test_depthcensus.py`. Adding 84 s to that file
     makes one unit ~556 s against a 120 s per-round budget. `plan()`'s
     no-silent-truncation rule would then return it ALONE on the rounds it
     comes up, consuming the entire slice and starving the other 26 units ...
     The census belongs in its own file, so it is its own unit and the
     planner can schedule it against a real budget."

The question had been raised and deferred by rounds 456, 458, 462, 463 and
468 -- six times -- and round 469 found the reason it kept coming back: the
`whence_slow` tier had no runner at all, so "is it worth a slot" was a
question about slots that did not exist. `harness/whenceslow.py` and
`harness/run_whenceslow_slice.sh` are the slots. This is the first test
written INTO them.

WHAT THIS GUARDS THAT THE FAST TIER CANNOT. `test_testcorpus_census.py`
(70 tests, ~7 s, fast tier) is entirely about the HARVESTER -- it runs over
`harvest_tests()` and over synthetic modules, and never executes a harvested
program. This file runs all 829 of them through the interpreter at the
`max_depth` their own runner would give them, and asserts on the whole run:
no program errors, the allocation arithmetic agrees with an independent
re-walk on every champion, no walk hits a cap, and the champion is the one
decision 53 is about. That is a class of regression -- an interpreter change
that breaks one program in the corpus, or that makes the allocation
accounting disagree with the walk -- which nothing else in this repo looks
for.

Cost, measured this round on a 1-CPU box: 83.3 s for the census fixture,
which round 469's table would place FOURTH in the tier behind
`test_depthcensus.py` (472.2 s), `test_v29.py` (291.1 s) and
`test_miss_message_differential.py` (106.9 s).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import depthcensus as dc                                    # noqa: E402

pytestmark = pytest.mark.whence_slow


@pytest.fixture(scope="module")
def suite_census():
    """(rows, summary, harvest stats) for the WHOLE test corpus, suite mode.

    Module-scoped: the census is the expensive thing in this file and every
    test below is a different question about the same run. `depth="suite"`
    and not `"default"` on purpose -- `census_tests`' own docstring says the
    two answers differ and that the difference IS decision 53's error, so a
    census that had one mode would be re-making that error."""
    programs, stats = dc.harvest_tests()
    rows = dc.census_tests(programs, depth="suite", alloc=True)
    return rows, dc.summarise(rows), stats


# ---------------------------------------------------------------------------
# 1. every harvested program still runs
# ---------------------------------------------------------------------------

def test_every_harvested_program_runs_without_error(suite_census):
    """The headline guard, and the reason this belongs in a tier at all. A
    harvested program is one the suite itself runs, so a program that errors
    here is either an interpreter regression or a harvester that claimed a
    program the suite never ran. Both are worth a red."""
    rows, summary, _stats = suite_census
    failed = [(r["program"], r["error"]) for r in rows if not r["ok"]]
    assert failed == [], failed
    assert summary["failed"] == 0
    assert summary["ran"] == summary["programs"] == len(rows)


def test_the_corpus_is_the_harvest_and_has_not_silently_shrunk(suite_census):
    """A bound, not a pin: the corpus is meant to grow. 829 at round 470,
    765 at round 468, 559 at round 462, 488 at round 458."""
    rows, summary, stats = suite_census
    assert summary["programs"] == stats["programs"]
    assert summary["programs"] >= 829, summary["programs"]


# ---------------------------------------------------------------------------
# 2. the allocation accounting, checked against an independent re-walk
# ---------------------------------------------------------------------------

def test_the_constructor_arithmetic_agrees_with_the_independent_rewalk(
        suite_census):
    """`_AllocTracker` computes a value's size by arithmetic as it is built;
    `alloc_agrees` re-walks the finished value and compares. They are two
    implementations of one quantity and a disagreement means one of them is
    wrong. 0 disagreements over 829 programs."""
    _rows, summary, _stats = suite_census
    assert summary["alloc_disagreements"] == [], \
        summary["alloc_disagreements"]


def test_the_alloc_depth_is_never_below_the_built_depth(suite_census):
    """The invariant, stated as an inequality rather than an equality. The
    allocation census has NO root set -- it sees every value constructed --
    so it can only ever see MORE than the provenance walk reaches from the
    roots, never less. A violation is a hole in the allocation hook."""
    _rows, summary, _stats = suite_census
    assert summary["alloc_invariant_violations"] == [], \
        summary["alloc_invariant_violations"]
    assert summary["max_alloc_gap"] >= 0


def test_the_root_set_misses_values_and_the_census_says_which(suite_census):
    """NOT a failure -- a measured property, pinned so that it going to zero
    is as visible as it going up. The root set is bindings + drops + prints,
    so a value built inside a call whose result is discarded without passing
    through `_note_drop` is unreachable from it, and the allocation census
    is the only thing that sees those. The gap is real and small."""
    _rows, summary, _stats = suite_census
    assert summary["programs_alloc_deeper"], \
        "the root set now reaches everything -- verify before relaxing this"
    assert summary["max_alloc_gap"] <= 8, summary["max_alloc_gap"]


def test_no_allocation_walk_hits_a_cap(suite_census):
    """A capped walk is a measurement with an unknown remainder, and the
    numbers this census publishes are quoted elsewhere as maxima."""
    _rows, summary, _stats = suite_census
    assert summary["alloc_capped_programs"] == [], \
        summary["alloc_capped_programs"]
    assert summary["width_sample_incomplete"] == [], \
        summary["width_sample_incomplete"]


# ---------------------------------------------------------------------------
# 3. the champion, which is what decision 53 is about
# ---------------------------------------------------------------------------

def test_the_deepest_value_in_the_test_corpus_is_twenty_thousand(
        suite_census):
    """SPEC decision 53's number, re-derived by the instrument rather than
    read out of a test. Round 458 found the error in reading it -- the file
    the cited program lives in runs everything at `max_depth=500` -- and
    this is the census that gets it right, because suite mode gives every
    program the depth its OWN runner would."""
    _rows, summary, _stats = suite_census
    assert summary["max_built_depth"] == 20000, summary["max_built_depth"]
    assert summary["max_alloc_depth"] == 20000
    assert summary["deepest_program"] == summary["deepest_alloc_program"]


def test_the_printed_depth_stays_far_under_the_full_cap(suite_census):
    """The other half of the two-population rule this module exists to keep
    apart: values are BUILT 20000 deep and PRINTED 4 deep, and no printed
    value in the whole corpus exceeds the full renderer's cap."""
    _rows, summary, _stats = suite_census
    assert summary["max_printed_depth"] <= summary["full_levels"]
    assert summary["printed_values_over_cap"] == 0
    assert summary["programs_over_full_cap"] > 0, \
        "programs that BUILD past the cap are the reason the cap matters"


# ---------------------------------------------------------------------------
# 4. round 470: the widened corpus, corroborated by RUNNING it
# ---------------------------------------------------------------------------

def test_the_programs_the_zip_widening_added_are_in_the_census_and_green(
        suite_census):
    """Round 470 widened `zip(LITERAL, f(LITERAL))` and the corpus went
    765 -> 829. A static proof that a column may be bound is not a claim
    that the strings are runnable; this is. Every program attributed to one
    of the four files that held the 13 zip rows runs clean."""
    rows, _summary, _stats = suite_census
    zip_files = ("test_self_eval.py", "test_v20.py", "test_v22.py",
                 "test_v30.py", "test_v31.py")
    got = [r for r in rows if r["program"].split(":")[0] in zip_files]
    assert len(got) >= 60, len(got)
    assert [r["program"] for r in got if not r["ok"]] == []


def test_the_three_producers_really_do_return_one_element_per_input():
    """The EMPIRICAL counterpart to round 470's static proof, and the reason
    it is in the slow tier: it runs the self-evaluator.

    `_len_preserving_param` reads three functions' ASTs and concludes their
    output length equals an input's. That conclusion is what authorised
    binding 64 new programs into a published corpus, so it is worth one run
    that asks the functions themselves. Sizes 1 and 2 rather than 0: an
    empty input satisfies every length claim vacuously."""
    from test_self_eval import guest_eval_all as gea_self
    from test_v20 import guest_eval_all as gea_v20

    cases = ['let result = 1 + 1', 'let result = [1, 2]']
    for fn in (gea_self, gea_v20):
        assert len(fn(cases[:1])) == 1, fn
        assert len(fn(cases)) == 2, fn


def test_the_v30_and_v31_producers_return_one_element_per_input():
    """Same check, the other two producers. Separate test because they take
    a `lib` argument and build a different library."""
    import test_v30
    import test_v31

    progs = ['let x = 1 + 2\nlet r = len(steps(x))',
             'let x = 1 / 0\nlet r = len(blame(x))']
    lib30 = test_v30.library_source() if hasattr(test_v30, "library_source") \
        else test_v30._library_source()
    assert len(test_v30.guest_batch(progs[:1], lib30)) == 1
    assert len(test_v30.guest_batch(progs, lib30)) == 2

    dprogs = ['let x = 1 + 2\nlet y = 1 + 3\nlet r = contrast(x, y)',
              'let x = 1 + 2\nlet y = 1 + 3\nlet r = len(diverge(x, y))']
    lib31 = test_v31.library_source() if hasattr(test_v31, "library_source") \
        else test_v31._library_source()
    assert len(test_v31.guest_values(dprogs[:1], lib31)) == 1
    assert len(test_v31.guest_values(dprogs, lib31)) == 2


# ---------------------------------------------------------------------------
# 5. round 474 -- a censused row must be nameable
# ---------------------------------------------------------------------------

def test_every_censused_row_has_a_label_that_names_exactly_one_program(
        suite_census):
    """Round 470's next-step 3: "`file:line` is not a key for a source
    position; `(file, line, col)` is."

    The first clause was right about this census and understated: with
    `file:line` labels, 346 of 829 rows (41.7 %) shared a label with another
    row, so the census could not name what it had measured. The second
    clause is what round 474 measured and had to amend -- the column splits
    ONE of the forty colliding keys, because 39 of the 40 are a single call
    site inside a loop over a table, denoting many programs at one column.

    A harvested program's POSITION is a one-to-many relation and cannot key
    it. `census_tests` therefore labels `file:line:col#k`, k counting within
    the site, which is unique AND says out loud that the site is shared. This
    test is the one that goes red if somebody "simplifies" the ordinal away.
    """
    rows, _summary, _stats = suite_census
    labels = [r["program"] for r in rows]
    assert len(set(labels)) == len(labels), \
        [l for l in labels if labels.count(l) > 1][:5]
    # and the ordinal is load-bearing, not decorative: strip it and the
    # labels collide again. If this ever stops being true the corpus has
    # changed shape, not the instrument.
    stripped = [l.rsplit("#", 1)[0] for l in labels]
    assert len(set(stripped)) < len(stripped), \
        "no site is shared any more -- re-read round 474 before deleting #k"
