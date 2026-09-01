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


# --- the precondition, decided from the EDIT (round 426) -------------------
#
# Round 420 recorded `append_only` in `Verdict.pre` and `law` printed it
# beside every violation alike, so the sentence carried no information. These
# tests pin the decision procedure that replaced it. The hermetic ones use
# the SHAPES of round 422's planted discriminator pair (CP22p appends, CP22p2
# inserts in the middle) on a two-line guest program; the corpus ones run the
# real registries and are `whence_slow` because each pin costs one parse of a
# ~2600-line guest file (measured: 6.9 s for 23 pins).

REG_422 = os.path.join(HERE, "..", "..", "state", "whence", "round-422")
REG_416 = os.path.join(HERE, "..", "..", "state", "whence", "round-416")


def _pin(becomes, needle):
    return {"id": "T1", "guest_file": "examples/self_host.lang",
            "dir": "+", "guardian": "g", "edit": "line_replace",
            "needle": needle, "becomes": becomes}


def _pre(base, becomes, needle):
    return PO.edit_precondition(base, _pin(becomes, needle))


BASE_MSG = 'fn f(x) { "a" + x + "b" }\ncheck "g": contains(f("q"), "aq")\n'


def test_appending_an_atom_to_a_concat_chain_holds():
    r = _pre(BASE_MSG, 'fn f(x) { "a" + x + "b" + "!" }', 'fn f(x)')
    assert r["status"] == PO.PRE_HOLDS
    assert r["kinds"] == [PO.DELTA_APPEND]


def test_rewriting_a_non_final_atom_of_a_chain_breaks_it():
    r = _pre(BASE_MSG, 'fn f(x) { "a here" + x + "b" }', 'fn f(x)')
    assert r["status"] == PO.PRE_BROKEN
    assert r["kinds"] == [PO.DELTA_INFIX]


def test_extending_the_final_literal_of_a_chain_holds():
    r = _pre(BASE_MSG, 'fn f(x) { "a" + x + "b more" }', 'fn f(x)')
    assert r["status"] == PO.PRE_HOLDS


def test_extending_a_non_final_literal_of_a_chain_breaks_it():
    """Same number of atoms, same text added — but not at the end."""
    r = _pre(BASE_MSG, 'fn f(x) { "a more" + x + "b" }', 'fn f(x)')
    assert r["status"] == PO.PRE_BROKEN


def test_a_bare_literal_extended_at_its_end_holds():
    base = 'fn f() { "hello" }\ncheck "g": contains(f(), "hello")\n'
    r = _pre(base, 'fn f() { "hello there" }', 'fn f()')
    assert r["status"] == PO.PRE_HOLDS


def test_a_bare_literal_extended_at_its_front_breaks_it():
    base = 'fn f() { "hello" }\ncheck "g": contains(f(), "hello")\n'
    r = _pre(base, 'fn f() { "oh hello" }', 'fn f()')
    assert r["status"] == PO.PRE_BROKEN


def test_a_promotion_from_one_atom_to_a_chain_is_an_append():
    """`str(k.v)` -> `str(k.v) + " (a number)"`, pin CP04p's exact shape.

    REGRESSION: this came out `infix` while `_node_eq` compared `Call.tail`.
    Moving the call out of tail position flips a flag the PARSER sets, and
    the two otherwise-identical `str(k.v)` nodes stopped comparing equal.
    """
    base = 'fn f(k) { str(k) }\ncheck "g": contains(f(1), "1")\n'
    r = _pre(base, 'fn f(k) { str(k) + " (a number)" }', 'fn f(k)')
    assert r["status"] == PO.PRE_HOLDS
    assert r["kinds"] == [PO.DELTA_APPEND]


def test_a_non_string_edit_is_undecided_not_broken():
    base = 'fn f(x) { x > 1 }\ncheck "g": f(2)\n'
    r = _pre(base, 'fn f(x) { x > 0 }', 'fn f(x)')
    assert r["status"] == PO.PRE_UNKNOWN
    assert r["kinds"] == [PO.DELTA_STRUCTURAL]


def test_a_longer_or_chain_is_one_structural_delta_not_manufactured_infixes():
    """REGRESSION: pin CP06p adds one disjunct to a four-way `or`.

    A pairwise descent lines `"["` up against `"@{"` and `"@{"` against
    `"{"` and reports TWO infix string rewrites — a positive `broken`
    finding produced entirely by left-associative misalignment, on an edit
    that touches no rendered text at all.
    """
    base = ('fn f(t) { t == "(" or t == "[" or t == "@{" }\n'
            'check "g": f("(")\n')
    r = _pre(base, 'fn f(t) { t == "(" or t == "[" or t == "@{" or t == "{" }',
             'fn f(t)')
    assert r["status"] == PO.PRE_UNKNOWN
    assert r["kinds"] == [PO.DELTA_STRUCTURAL]


def test_equal_length_or_chains_are_still_descended_pairwise():
    base = 'fn f(t) { t == "(" or t == "[" }\ncheck "g": f("(")\n'
    r = _pre(base, 'fn f(t) { t == "(" or t == "@{" }', 'fn f(t)')
    assert len(r["kinds"]) == 1
    assert "'['" in r["deltas"][0] and "'@{'" in r["deltas"][0]


def test_pinning_a_condition_false_compares_the_two_branches():
    """Round 420's EP11p, mechanically: the observation moves branch.

    `if fn_name == "(anonymous)" { "return value" } else { "return value of
    " + fn_name }` with the condition pinned `false` produces a LONGER
    message by inserting in the middle, which is why round 416's `+`-blind
    `contains` guardian saw it. Without this case the delta is
    `<Binary> -> <BoolLit>` and the decider leaves round 420's own worked
    example undecided.
    """
    base = ('fn f(n) { if n == "x" { "return value" } '
            'else { "return value of " + n } }\n'
            'check "g": contains(f("x"), "return value")\n')
    r = _pre(base,
             'fn f(n) { if false { "return value" } '
             'else { "return value of " + n } }', 'fn f(n)')
    assert r["status"] == PO.PRE_BROKEN
    assert r["kinds"] == [PO.DELTA_INFIX]
    assert "'return value'" in r["deltas"][0]


def test_pinning_a_condition_true_selects_the_then_branch():
    base = ('fn f(n) { if n == "x" { "short" } '
            'else { "short and long" } }\n'
            'check "g": contains(f("y"), "short")\n')
    r = _pre(base,
             'fn f(n) { if true { "short" } '
             'else { "short and long" } }', 'fn f(n)')
    # the observation goes from the ELSE arm to the THEN arm, i.e. shrinks
    assert r["status"] == PO.PRE_BROKEN


def test_an_edit_that_moves_only_line_numbers_is_identity():
    base = 'fn f() { "a" }\n\ncheck "g": contains(f(), "a")\n'
    pin = _pin('fn f() { "a" }\n', 'fn f()')
    # apply_edit refuses a byte-identical edit; a whitespace-only one is
    # located, applied, and leaves the AST alone.
    r = PO.edit_precondition(base, pin)
    assert r["status"] == "identity"


def test_an_unlocatable_edit_is_reported_not_raised():
    r = _pre(BASE_MSG, 'fn nope() { 1 }', 'fn nowhere(')
    assert r["status"] == "unlocatable"
    assert "nowhere" in r["why"]


# --- the law, partitioned by the precondition ------------------------------

def test_check_law_without_a_precondition_map_calls_every_violation_strict():
    pins = [{"id": "P", "dir": "+", "guardian": "g"}]
    res = [{"id": "P", "verdict": "guarded", "guardian": "g"}]
    out = PO.check_law(pins, res, [_v("g", ("+",), ("append_only",))])
    assert len(out["violations"]) == 1
    assert len(out["strict_violations"]) == 1
    assert out["excused"] == [] and out["undecided"] == []


def test_check_law_partitions_violations_three_ways():
    pins = [{"id": "H", "dir": "+", "guardian": "g"},
            {"id": "B", "dir": "+", "guardian": "g"},
            {"id": "U", "dir": "+", "guardian": "g"}]
    res = [{"id": i, "verdict": "guarded", "guardian": "g"}
           for i in ("H", "B", "U")]
    pre = {"H": {"status": PO.PRE_HOLDS}, "B": {"status": PO.PRE_BROKEN},
           "U": {"status": PO.PRE_UNKNOWN}}
    out = PO.check_law(pins, res, [_v("g", ("+",), ("append_only",))], pre)
    assert [r["id"] for r in out["strict_violations"]] == ["H"]
    assert [r["id"] for r in out["excused"]] == ["B"]
    assert [r["id"] for r in out["undecided"]] == ["U"]
    assert len(out["violations"]) == 3


# --- a coverage gap is an EMPTY co_red, not an empty sighted list ----------

def test_repoint_calls_a_pin_with_a_blind_red_candidate_not_a_gap():
    """REGRESSION: `repoint` printed "a genuine coverage gap" for pin CP03p
    and then, on the very next line, named the check that went red."""
    pins = [{"id": "P", "dir": "+", "guardian": "g"}]
    res = [{"id": "P", "verdict": "shadowed", "guardian": "g",
            "co_red": ["blindone"]}]
    vs = [_v("g", ("+",), ("append_only",)), _v("blindone", ("+",))]
    row = PO.repoint(pins, vs, res)[0]
    assert row["sighted_candidates"] == []
    assert row["blind_candidates"] == ["blindone"]
    assert row["gap"] is False


def test_repoint_calls_a_pin_with_nothing_red_a_gap():
    pins = [{"id": "P", "dir": "+", "guardian": "g"}]
    res = [{"id": "P", "verdict": "inert", "guardian": "g", "co_red": []}]
    row = PO.repoint(pins, [_v("g", ("+",), ("append_only",))], res)[0]
    assert row["gap"] is True and row["blind_candidates"] == []


def test_audit_marks_a_dropped_blind_red_candidate_rather_than_a_gap():
    pins = [{"id": "P", "guest_file": "x.lang", "dir": "+", "guardian": "g"}]
    res = [{"id": "P", "verdict": "shadowed", "guardian": "g",
            "co_red": ["blindone"]}]
    vs = [_v("g", ("+",), ("append_only",)), _v("blindone", ("+",))]
    row = PO.audit_registry(pins, vs, res)[0]
    assert row["status"] == "mispointed"
    assert row["candidates"] == [] and row["dropped_blind"] == ["blindone"]
    assert row["gap"] is False


def test_cored_polarity_counts_the_evidence_the_filter_drops():
    pins = [{"id": "P", "dir": "+", "guardian": "g"},
            {"id": "Q", "dir": "+", "guardian": "g"},
            {"id": "G", "dir": "+", "guardian": "g"}]
    res = [{"id": "P", "verdict": "shadowed", "guardian": "g",
            "co_red": ["blindone", "sighted"]},
           {"id": "Q", "verdict": "shadowed", "guardian": "g",
            "co_red": ["blindone"]},
           {"id": "G", "verdict": "guarded", "guardian": "g",
            "co_red": ["blindone"]}]
    vs = [_v("g", ("+",), ("append_only",)), _v("blindone", ("+",)),
          _v("sighted", ())]
    out = PO.cored_polarity(pins, res, vs)
    assert out["co_red_total"] == 3      # G is guarded; the filter never runs
    assert out["co_red_blind"] == 2
    assert out["false_gaps"] == ["Q"]


# --- the corpus: the real registries ---------------------------------------

@pytest.mark.whence_slow
def test_the_planted_discriminator_pair_is_decided_from_the_edit_alone():
    """CP22p and CP22p2: same rule, same guardian, same direction.

    Round 422 planted them with the note "if both come back the same way the
    precondition is decoration". They did not — CP22p is a finding and
    CP22p2 is the one `guarded` pin of that campaign — and this asserts the
    decision procedure reaches the same split WITHOUT reading a verdict.
    """
    import json
    with open(os.path.join(REG_422, "host-pins-plus.json"),
              encoding="utf-8") as f:
        pins = {p["id"]: p for p in json.load(f)["pins"]}
    with open(SELF_HOST, encoding="utf-8") as f:
        base = f.read()
    assert PO.edit_precondition(base, pins["CP22p"])["status"] == PO.PRE_HOLDS
    assert PO.edit_precondition(base, pins["CP22p2"])["status"] == PO.PRE_BROKEN


@pytest.mark.whence_slow
def test_round_420s_two_law_violations_are_both_explained_or_out_of_scope():
    """EP11p's precondition is `append_only` and the decider breaks it;
    EP10m's is `kind_stable`, which this module does not decide at all."""
    import json
    with open(os.path.join(REG_416, "eval-pins.json"), encoding="utf-8") as f:
        reg = json.load(f)
    with open(os.path.join(REG_416, "run.json"), encoding="utf-8") as f:
        run = json.load(f)
    with open(SELF_EVAL, encoding="utf-8") as f:
        base = f.read()
    pre = PO.precondition_map(reg["pins"], base)
    out = PO.check_law(reg["pins"], run["results"],
                       PO.classify_file(SELF_EVAL), pre)
    assert [r["id"] for r in out["excused"]] == ["EP11p"]
    assert [r["id"] for r in out["undecided"]] == ["EP10m"]
    assert out["strict_violations"] == []


@pytest.mark.whence_slow
def test_the_law_has_no_strict_counterexample_on_either_guest_file():
    """The round-426 headline, and the one number that can move.

    A STRICT violation is a pin that is blind in its direction, measured
    `guarded`, and whose edit's `append_only` is ESTABLISHED. There is none
    in any of the three campaigns on disk. If a future campaign produces
    one, round 420's law is refuted rather than conditional, and this test
    is where that is found out.
    """
    import json
    campaigns = [(os.path.join(REG_416, "eval-pins.json"),
                  os.path.join(REG_416, "run.json"), SELF_EVAL),
                 (os.path.join(REG_422, "host-pins-plus.json"),
                  os.path.join(REG_422, "run-plus-witnessed.json"), SELF_HOST),
                 (os.path.join(REG_422, "host-pins-plus-repointed.json"),
                  os.path.join(REG_422, "run-repointed.json"), SELF_HOST)]
    for pf, rf, guest in campaigns:
        with open(pf, encoding="utf-8") as f:
            reg = json.load(f)
        with open(rf, encoding="utf-8") as f:
            run = json.load(f)
        with open(guest, encoding="utf-8") as f:
            base = f.read()
        out = PO.check_law(reg["pins"], run["results"],
                           PO.classify_file(guest),
                           PO.precondition_map(reg["pins"], base))
        assert out["strict_violations"] == [], "%s: %s" % (
            os.path.basename(pf), [r["id"] for r in out["strict_violations"]])


@pytest.mark.whence_slow
def test_the_repointed_registry_fails_its_own_acceptance_criterion():
    """`host-pins-plus-repointed.json`'s own `_` field says:

        `polarity.py audit` over this file must report 0 MISPOINTED, which
        is the non-circular half

    It reports five. Round 422 hand-repointed five pins onto guardians that
    are blind in the pin's own direction; every one then came back `guarded`
    (a repoint onto a co-red check is guarded by construction) and the
    campaign scored 20/20. Nothing ran the criterion, and `audit` exits 1.
    This test holds the failure open rather than letting it be inherited
    again as a green result.
    """
    import json
    with open(os.path.join(REG_422, "host-pins-plus-repointed.json"),
              encoding="utf-8") as f:
        reg = json.load(f)
    rows = PO.audit_registry(reg["pins"], PO.classify_file(SELF_HOST))
    bad = sorted(r["id"] for r in rows if r["status"] == "mispointed")
    assert bad == ["CP03p", "CP06p", "CP08p", "CP10p2", "CP22p2"]


@pytest.mark.whence_slow
def test_the_sightedness_filter_drops_measured_red_evidence():
    """The filter is a same-rule theorem applied across rules, and this is
    what it costs: on `self_host.lang` it discards 16 of the 93 checks that
    actually went red, and calls CP03p a coverage gap on the strength of it.
    """
    import json
    with open(os.path.join(REG_422, "host-pins-plus.json"),
              encoding="utf-8") as f:
        reg = json.load(f)
    with open(os.path.join(REG_422, "run-plus.json"), encoding="utf-8") as f:
        run = json.load(f)
    out = PO.cored_polarity(reg["pins"], run["results"],
                            PO.classify_file(SELF_HOST))
    assert out["co_red_unmatched"] == 0
    assert out["co_red_total"] == 93
    assert out["co_red_blind"] == 16
    assert out["false_gaps"] == ["CP03p"]


# --- the CLI --------------------------------------------------------------

def test_the_precondition_verb_runs_and_is_listed_in_the_usage(capsys):
    assert PO.main(["polarity.py"]) == 2
    err = capsys.readouterr().err
    assert "precondition" in err


@pytest.mark.whence_slow
def test_the_precondition_verb_runs_end_to_end(capsys):
    rc = PO.main(["polarity.py", "precondition",
                  os.path.join(REG_422, "host-pins-plus.json")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "CP22p2  broken" in out and "CP22p   holds" in out
