"""Unit tests for `polarity.py` (round 420, language C).

Two kinds of test, kept apart on purpose:

* SHAPE tests build a one-line guest program and assert what the analyser
  makes of it. They are hermetic and fast, and they are what pins the
  monotonicity algebra (`not` flips, `and` intersects, preconditions union).
* CORPUS tests read `examples/self_eval.lang` and assert the polarity of
  named checks that round 420's finding rests on. They parse the guest file
  but never RUN it, so they cost milliseconds, not the 100 s a check-pin
  campaign costs. If somebody rewrites one of these checks, this is the
  test that says the round-420 conclusion about it no longer applies.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import polarity as PO                                          # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELF_EVAL = os.path.join(HERE, "examples", "self_eval.lang")
SELF_HOST = os.path.join(HERE, "examples", "self_host.lang")


def one(src):
    """Classify a source holding exactly one `check`."""
    vs = PO.classify_source(src)
    assert len(vs) == 1, "expected one check, got %d" % len(vs)
    return vs[0]


# --- the atoms ------------------------------------------------------------

def test_missed_is_plus_blind_under_refusal():
    v = one('check "c": missed(1 / 0)')
    assert v.blind == frozenset(("+",))
    assert v.pre == (PO.PRE_REFUSAL,)
    assert not v.unknown


def test_contains_is_plus_blind_under_append_only():
    v = one('check "c": contains("abc", "a")')
    assert v.blind == frozenset(("+",))
    assert v.pre == (PO.PRE_APPEND_ONLY,)


def test_is_guess_is_minus_blind_under_kind_stable():
    v = one('check "c": is_guess(guess(1, 0.5, "s"))')
    assert v.blind == frozenset(("-",))
    assert v.pre == (PO.PRE_KIND_STABLE,)


def test_guest_is_prefix_predicate_is_read_as_a_type_test():
    src = 'fn is_thing(v) { true }\ncheck "c": is_thing(1)'
    v = one(src)
    assert v.blind == frozenset(("-",))
    assert v.pre == (PO.PRE_KIND_STABLE,)


def test_is_prefix_convention_needs_the_guest_to_define_it():
    """An `is_*` name the file does NOT define is unknown, not a type test.

    The convention is a fact about this corpus, and a corpus-derived rule
    that fires on names it has never seen would be asserting the convention
    rather than using it.
    """
    v = one('check "c": is_mystery(1)')
    assert v.blind == PO.NEITHER
    assert v.unknown


# --- the algebra ----------------------------------------------------------

def test_not_flips_the_direction():
    v = one('check "c": not missed(1)')
    assert v.blind == frozenset(("-",))
    # the precondition survives the flip: it is what the claim rests on,
    # not which way the claim points.
    assert v.pre == (PO.PRE_REFUSAL,)


def test_double_negation_returns_the_original_direction():
    assert one('check "c": not (not missed(1))').blind == frozenset(("+",))


def test_and_of_two_same_direction_atoms_stays_blind():
    v = one('check "c": missed(1 / 0) and contains("ab", "a")')
    assert v.blind == frozenset(("+",))
    assert set(v.pre) == {PO.PRE_REFUSAL, PO.PRE_APPEND_ONLY}


def test_and_of_opposite_directions_is_two_sided():
    """Round 416's EP03 guardian shape, which is why it caught a `+` edit
    nobody wrote it for."""
    v = one('check "c": contains("ab", "a") and not contains("ab", "z")')
    assert v.blind == PO.NEITHER
    assert not v.unknown


def test_or_intersects_like_and():
    assert one('check "c": missed(1) or missed(2)').blind == frozenset(("+",))
    assert one('check "c": missed(1) or not missed(2)').blind == PO.NEITHER


def test_equality_is_two_sided():
    v = one('check "c": 1 + 1 == 2')
    assert v.blind == PO.NEITHER
    assert v.reason == "two-sided `==`"
    assert not v.unknown


def test_ordering_is_two_sided():
    assert one('check "c": 2 > 1').blind == PO.NEITHER


def test_constant_predicate_is_blind_to_everything_and_named_as_such():
    v = one('check "c": true')
    assert v.blind == PO.BOTH
    assert v.reason == "constant"


def test_unknown_shape_is_reported_rather_than_scored_two_sided():
    src = 'fn thing() { true }\ncheck "c": thing()'
    v = one(src)
    assert v.blind == PO.NEITHER
    assert v.unknown, "an unrecognised call must not masquerade as two-sided"


def test_unknown_propagates_through_a_connective():
    src = 'fn thing() { true }\ncheck "c": missed(1) and thing()'
    v = one(src)
    assert v.unknown


# --- guest_functions ------------------------------------------------------

def test_guest_functions_sees_both_fn_and_let_fn():
    prog = PO.P.parse('fn a(x) { x }\nlet b = fn(x) { x }\nlet c = 1\n0')
    assert PO.guest_functions(prog) == {"a", "b"}


# --- the corpus -----------------------------------------------------------

CORPUS_POLARITY = {
    # the two round-420 found were genuinely PREDICATE-blind
    "guest strict if rejects 0": frozenset(("+",)),
    "is_num rejects a guess wrapping a number": frozenset(("+",)),
    # the three that are two-sided, and were therefore shadowed for the
    # OTHER reason (the probe agreed with both rules)
    "guest miss <BOUND name> stays plain propagation": PO.NEITHER,
    "top-level == between two guesses yields a new guess": frozenset(("-",)),
    "guest return type is not re-checked over an already-missed body":
        PO.NEITHER,
    # the two the analyser flags but the run cleared: a broken precondition
    "guest anonymous fn return-type miss label has no 'of' suffix "
    "(round 326)": frozenset(("+",)),
    # the replacements round 420 re-pointed to, each sighted in its
    # pin's own direction
    "guest if": PO.NEITHER,
    "guest miss <unbound name> names the miss-reason cure": frozenset(("+",)),
    "guest return type accepts a matching value": PO.NEITHER,
    "nested guess-vs-guess equality ignores confidence": PO.NEITHER,
    "guest return type rejects a mismatched value": frozenset(("+",)),
}


@pytest.mark.parametrize("label,expected", sorted(CORPUS_POLARITY.items()))
def test_named_self_eval_checks_have_the_polarity_round_420_measured(
        label, expected):
    by = {v.label: v for v in PO.classify_file(SELF_EVAL)}
    assert label in by, "check %r is gone from self_eval.lang" % label
    assert by[label].blind == expected


def test_every_check_in_both_guest_files_classifies_without_raising():
    for path in (SELF_EVAL, SELF_HOST):
        vs = PO.classify_file(path)
        assert len(vs) > 100, "%s: only %d checks?" % (path, len(vs))
        for v in vs:
            assert v.blind <= PO.BOTH


def test_unknown_share_stays_small_enough_for_the_summary_to_mean_anything():
    """The one-sided share is only informative if `unknown` is small.

    Not a fixed threshold on the count -- that would rot the moment a check
    is added -- but on the SHARE, which is the number `classify` prints.
    """
    for path in (SELF_EVAL, SELF_HOST):
        s = PO.summarise(PO.classify_file(path))
        assert s["unknown_pct"] < 5.0, "%s: %.1f%% unknown" % (
            path, s["unknown_pct"])


# --- the law and the audit ------------------------------------------------

def _v(label, blind, pre=()):
    return PO.Verdict(label, 1, blind, False, "synthetic", pre)


def test_check_law_separates_violation_from_confirmation():
    verdicts = [_v("blindy", ("+",), (PO.PRE_REFUSAL,)), _v("sighted", ())]
    pins = [{"id": "A", "dir": "+", "guardian": "blindy"},
            {"id": "B", "dir": "+", "guardian": "blindy"},
            {"id": "C", "dir": "+", "guardian": "sighted"}]
    results = [{"id": "A", "guardian": "blindy", "verdict": "guarded"},
               {"id": "B", "guardian": "blindy", "verdict": "shadowed"},
               {"id": "C", "guardian": "sighted", "verdict": "guarded"}]
    out = PO.check_law(pins, results, verdicts)
    assert [r["id"] for r in out["violations"]] == ["A"]
    assert [r["id"] for r in out["confirmations"]] == ["B"]
    assert [r["id"] for r in out["sighted"]] == ["C"]
    assert out["n_scored"] == 3


def test_check_law_reports_a_guardian_label_that_names_no_check():
    pins = [{"id": "A", "dir": "+", "guardian": "ghost"}]
    results = [{"id": "A", "guardian": "ghost", "verdict": "guarded"}]
    out = PO.check_law(pins, results, [_v("real", ())])
    assert out["unmatched"] == [("A", "ghost")]
    assert not out["violations"]


def test_check_law_ignores_a_pin_with_no_direction():
    pins = [{"id": "NC", "guardian": "blindy"}]
    results = [{"id": "NC", "guardian": "blindy", "verdict": "inert"}]
    out = PO.check_law(pins, results, [_v("blindy", ("+",))])
    assert out["n_scored"] == 0


def test_audit_calls_a_blind_non_guarded_pin_mispointed():
    verdicts = [_v("blindy", ("+",), (PO.PRE_REFUSAL,)), _v("sighted", ())]
    pins = [{"id": "A", "dir": "+", "guardian": "blindy"}]
    results = [{"id": "A", "guardian": "blindy", "verdict": "shadowed",
                "co_red": ["sighted", "blindy"]}]
    rows = PO.audit_registry(pins, verdicts, results)
    assert rows[0]["status"] == "mispointed"
    # only the SIGHTED co-red check is offered as a replacement
    assert rows[0]["candidates"] == ["sighted"]
    assert rows[0]["candidate_source"] == "co_red"


def test_audit_calls_a_blind_but_guarded_pin_a_broken_precondition():
    """The round-420 false-positive case (EP11p, CP06, CP08).

    The static rule says blind; the run says guarded; the honest report is
    that the edit left the order the predicate is monotone along, NOT that
    the pin is fine and not that the analyser is broken.
    """
    verdicts = [_v("blindy", ("+",), (PO.PRE_APPEND_ONLY,))]
    pins = [{"id": "A", "dir": "+", "guardian": "blindy"}]
    results = [{"id": "A", "guardian": "blindy", "verdict": "guarded",
                "co_red": []}]
    rows = PO.audit_registry(pins, verdicts, results)
    assert rows[0]["status"] == "precondition_broken"
    assert rows[0]["pre"] == [PO.PRE_APPEND_ONLY]


def test_audit_without_a_run_cannot_suppress_and_says_so():
    """No run means no verdict, so a blind pin is reported mispointed and
    its candidates come from the whole file rather than from `co_red`."""
    verdicts = [_v("blindy", ("+",)), _v("sighted", ())]
    pins = [{"id": "A", "dir": "+", "guardian": "blindy"}]
    rows = PO.audit_registry(pins, verdicts, None)
    assert rows[0]["status"] == "mispointed"
    assert rows[0]["candidate_source"] == "whole file"
    assert "sighted" in rows[0]["candidates"]
    assert "blindy" not in rows[0]["candidates"]


def test_audit_flags_a_guardian_that_names_no_check():
    rows = PO.audit_registry([{"id": "A", "dir": "-", "guardian": "ghost"}],
                             [_v("real", ())], None)
    assert rows[0]["status"] == "unlocatable"


def test_audit_skips_a_lateral_direction():
    """`~` (neither more nor less) has no order for a monotone predicate to
    be blind along — round 420 found three such edits in round 414's
    registry, and scoring them would invent a verdict."""
    rows = PO.audit_registry([{"id": "A", "dir": "~", "guardian": "blindy"}],
                             [_v("blindy", ("+",))], None)
    assert rows == []


def test_repoint_skips_guarded_pins_and_splits_candidates_by_polarity():
    verdicts = [_v("named", ("+",)), _v("ok", ()), _v("alsoblind", ("+",))]
    pins = [{"id": "A", "dir": "+", "guardian": "named"},
            {"id": "B", "dir": "+", "guardian": "named"}]
    results = [
        {"id": "A", "guardian": "named", "verdict": "guarded",
         "co_red": ["ok"]},
        {"id": "B", "guardian": "named", "verdict": "shadowed",
         "co_red": ["ok", "alsoblind"]},
    ]
    rows = PO.repoint(pins, verdicts, results)
    assert [r["id"] for r in rows] == ["B"]
    assert rows[0]["sighted_candidates"] == ["ok"]
    assert rows[0]["blind_candidates"] == ["alsoblind"]
    assert rows[0]["guardian_blind"] is True


def test_repoint_reports_a_genuine_coverage_gap_as_an_empty_candidate_list():
    verdicts = [_v("named", ("+",)), _v("alsoblind", ("+",))]
    pins = [{"id": "A", "dir": "+", "guardian": "named"}]
    results = [{"id": "A", "guardian": "named", "verdict": "shadowed",
                "co_red": ["alsoblind"]}]
    rows = PO.repoint(pins, verdicts, results)
    assert rows[0]["sighted_candidates"] == []
    assert rows[0]["blind_candidates"] == ["alsoblind"]
