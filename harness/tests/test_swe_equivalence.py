"""swe.equivalence: escalated corpus search, ambiguous-survivor filtering,
verdict reporting (round 220)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe.equivalence import (escalate, escalation_corpus, level_reached, filter_ambiguous,
                             run_equivalence, summarize, DEFAULT_LEVELS)
from swe.fuzz import WHENCE_ROOT
from swe.killers import load_whence
from swe.mutation import generate
from tests.whence_anchor import reachable_concat_mutant


def _concat_mutant():
    """The `+` -> `-` arith mutant on a string-concat site, which crashes on
    two strings.

    This used to be a hand-rolled copy of `swe.killers`' own selection, and
    its docstring said so ("Same anchor swe.killers' own test uses") — a
    cross-file claim with no reader, which round 437 falsified by
    re-anchoring killers alone. Round 445 made the claim true by construction
    instead: `tests/whence_anchor` is now the single definition, and it
    ITERATES to a candidate that really kills, which this copy never did.
    """
    return reachable_concat_mutant()[0]


def _equivalent_mutant():
    """A mutant that changes the SOURCE TEXT but not any observable
    behaviour — appending dead code — same trick swe.killers' own
    no-killer test uses."""
    with open(os.path.join(WHENCE_ROOT, "whence", "interp.py")) as f:
        src = f.read()
    m = generate(src, "whence/interp.py")[0]
    m.source = src + "\n_UNUSED_ROUND_220 = 1\n"
    return m


def test_escalation_corpus_bigger_and_more_diverse_than_default_levels():
    small_levels = ((1, 5, 0.1, 2), (2, 5, 0.6, 6))
    progs, bounds = escalation_corpus(small_levels)
    assert len(progs) == 10
    assert bounds == [5, 10]
    # two independent seeds/knob-sets must not collapse to the same programs
    assert progs[:5] != progs[5:]


def test_level_reached_maps_tried_index_to_the_containing_level():
    bounds = [5, 10, 15]
    assert level_reached(1, bounds) == 1
    assert level_reached(5, bounds) == 1
    assert level_reached(6, bounds) == 2
    assert level_reached(15, bounds) == 3


def test_escalate_finds_a_killer_the_default_corpus_alone_would_have_missed():
    m = _concat_mutant()
    orig = load_whence(WHENCE_ROOT, "eq_gap")
    # level 1 has NOTHING that exercises string concat; level 2 does — the
    # verdict must report the killer AND correctly attribute it to level 2.
    levels = (("noop", 3, 0.0, 1), ("hit", 2, 0.0, 1))
    level1 = ["let a = 1\n", "print(2)\n", "let b = 1 + 1\n"]
    level2 = ['let a = "x" + "y"\n', "let c = 3\n"]
    programs = level1 + level2
    bounds = [len(level1), len(programs)]
    v = escalate(m, orig, WHENCE_ROOT, levels=levels, programs=programs, bounds=bounds)
    assert v.verdict == "corpus_gap_closed"
    assert v.killer.found
    assert v.killer.tried == 4          # first string-concat program is index 4 (1-based)
    d = v.as_dict()
    assert d["level_reached"] == 2
    assert d["total_levels"] == 2
    assert d["killer_program"] is not None


def test_escalate_reports_likely_equivalent_after_exhausting_every_level():
    m = _equivalent_mutant()
    orig = load_whence(WHENCE_ROOT, "eq_equiv")
    levels = (("a", 3, 0.0, 1), ("b", 2, 0.0, 1))
    programs = ["let a = 1\n", "print(2)\n", "let b = 3\n", "check \"x\": 1 == 1\n", "let m = 1 / 0\n"]
    bounds = [3, 5]
    v = escalate(m, orig, WHENCE_ROOT, levels=levels, programs=programs, bounds=bounds)
    assert v.verdict == "likely_equivalent"
    assert not v.killer.found
    d = v.as_dict()
    assert d["programs_tried"] == 5 and d["total_programs"] == 5
    assert d["level_reached"] == 2 and d["total_levels"] == 2
    assert "killer_program" not in d      # no fabricated evidence for a non-finding


def test_default_levels_are_each_bigger_or_more_diverse_than_killers_default_corpus():
    # killers.corpus()'s own default: stress_rate=0.15, max_depth=3, n=300 total.
    # Every escalation level individually matches or exceeds that per-level n,
    # and at least one level goes meaningfully deeper/stress-heavier — an
    # escalation that was actually SMALLER than the thing it escalates past
    # would be a silent regression, not a stronger search.
    assert all(n >= 300 for _, n, _, _ in DEFAULT_LEVELS)
    assert any(md > 3 for _, _, _, md in DEFAULT_LEVELS)
    assert any(sr > 0.15 for _, _, sr, _ in DEFAULT_LEVELS)


def test_filter_ambiguous_drops_uncovered_and_non_behavioural_and_reports_dropped_counts():
    counter_src = "class C:\n    def m(self):\n        self.fast_hits += 1\n"
    from swe.mutation import generate as gen
    counter_mut = gen(counter_src, "f.py")[0]
    behavioural_src = "def f(x):\n    return x > 0\n"
    behavioural_mut = gen(behavioural_src, "g.py")[0]
    mutant_dicts = [
        {"id": counter_mut.id, "path": "f.py", "status": "survived",
         "line": counter_mut.lineno, "end_line": counter_mut.end_lineno},
        {"id": behavioural_mut.id, "path": "g.py", "status": "survived",
         "line": behavioural_mut.lineno, "end_line": behavioural_mut.end_lineno},
        {"id": "g.py#999", "path": "g.py", "status": "killed",
         "line": behavioural_mut.lineno, "end_line": behavioural_mut.end_lineno},   # non-survivor: never escalated
    ]
    # coverage: f.py's site covered, g.py's site UNCOVERED (a test gap, not
    # an equivalence question)
    from swe import triage as TR
    f_index = TR.site_index(counter_mut.id)
    cov = {"f.py": {TR.sites(counter_src)[f_index].line: 1}, "g.py": {}}
    ambiguous, dropped = filter_ambiguous(
        mutant_dicts, cov=cov, source_by_path={"f.py": counter_src, "g.py": behavioural_src})
    assert ambiguous == []          # f.py's survivor is counter (non-behavioural); g.py's is uncovered
    assert dropped["non_behavioural"] == 1
    assert dropped["uncovered"] == 1


def test_filter_ambiguous_keeps_a_covered_behavioural_survivor():
    behavioural_src = "def f(x):\n    return x > 0\n"
    from swe.mutation import generate as gen
    from swe import triage as TR
    mut = gen(behavioural_src, "g.py")[0]
    idx = TR.site_index(mut.id)
    line = TR.sites(behavioural_src)[idx].line
    mutant_dicts = [{"id": mut.id, "path": "g.py", "status": "survived",
                     "line": mut.lineno, "end_line": mut.end_lineno}]
    cov = {"g.py": {line: 3}}
    ambiguous, dropped = filter_ambiguous(mutant_dicts, cov=cov, source_by_path={"g.py": behavioural_src})
    assert len(ambiguous) == 1 and dropped == {"uncovered": 0, "unknown_coverage": 0, "non_behavioural": 0}


def test_filter_ambiguous_with_no_coverage_or_triage_info_keeps_every_survivor():
    mutant_dicts = [{"id": "x.py#0", "path": "x.py", "status": "survived"},
                    {"id": "x.py#1", "path": "x.py", "status": "killed"}]
    ambiguous, dropped = filter_ambiguous(mutant_dicts)
    assert len(ambiguous) == 1 and ambiguous[0]["id"] == "x.py#0"
    assert dropped == {"uncovered": 0, "unknown_coverage": 0, "non_behavioural": 0}


def test_run_equivalence_shares_one_cache_and_corpus_across_a_batch():
    m1 = _concat_mutant()
    m2 = _equivalent_mutant()
    dicts = [{"id": m1.id, "path": m1.path, "status": "survived"},
             {"id": m2.id, "path": m2.path, "status": "survived"}]
    # deterministic corpus (not left to fuzz luck): includes exactly one
    # string-concat program, so m1 must be found and m2 must not be.
    fixed_programs = ["let a = 1\n", "print(2)\n", 'let c = "x" + "y"\n', "let d = 3\n"]
    verdicts = run_equivalence(dicts, WHENCE_ROOT, programs=fixed_programs, bounds=[len(fixed_programs)])
    assert len(verdicts) == 2
    by_id = dict((v.mutant.id, v) for v in verdicts)
    assert by_id[m1.id].verdict == "corpus_gap_closed"     # concat-crash is easy to hit even shallow
    assert by_id[m2.id].verdict == "likely_equivalent"     # dead code, no program can observe it
    # both verdicts were computed against the SAME escalation corpus (shared, not regenerated per mutant)
    assert by_id[m1.id].bounds == by_id[m2.id].bounds


def test_summarize_counts_and_effort():
    m = _concat_mutant()
    orig = load_whence(WHENCE_ROOT, "eq_summ")
    levels = (("hit", 3, 0.0, 1),)
    programs = ['let a = "x" + "y"\n', "let b = 1\n", "print(2)\n"]
    v_found = escalate(m, orig, WHENCE_ROOT, levels=levels, programs=programs, bounds=[3])
    m2 = _equivalent_mutant()
    v_miss = escalate(m2, orig, WHENCE_ROOT, levels=levels, programs=programs, bounds=[3])
    s = summarize([v_found, v_miss])
    assert s["total"] == 2 and s["corpus_gap_closed"] == 1 and s["likely_equivalent"] == 1
    assert s["total_escalation_programs"] == 3


def test_summarize_of_empty_list_is_well_formed():
    s = summarize([])
    assert s == {"total": 0, "corpus_gap_closed": 0, "likely_equivalent": 0,
                 "programs_per_verdict_mean": 0, "total_escalation_programs": 0}
