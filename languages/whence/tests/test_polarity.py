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
import shutil
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import curecheck as _C                                         # noqa: E402
import polarity as PO                                          # noqa: E402
import checkpin as CP                                          # noqa: E402

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

#: ROUND 431 (SWE-loop D): resolved from `curecheck.AGI_ROOT`, which prefers
#: the `AGI_RESEARCH_ROOT` env var that `harness/swe/proc.py` exports into
#: every sandbox it starts, and only falls back to `__file__` arithmetic.
#: These two lines used to read `os.path.join(HERE, "..", "..", ...)`, which
#: is round 413's defect class for the FOURTH time (149, 413, 419, here) and
#: which took the mutation engine down: `_copy_project` copies
#: `languages/whence` alone, so in the sandbox `..` `..` is the TEMPDIR and
#: `state/whence/round-422/host-pins-plus.json` is not there. Measured round
#: 431: 17 tests in this file red in the sandbox, `baseline_check` exit 1,
#: and NO campaign could start. Do not re-derive a repo path from `__file__`
#: in this tree -- `swe/copyparity.py escapes` is what checks it now, and as
#: of round 431 it can actually see this shape.
REG_422 = os.path.join(_C.AGI_ROOT, "state", "whence", "round-422")
REG_416 = os.path.join(_C.AGI_ROOT, "state", "whence", "round-416")


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
    # ROUND 438: was PRE_UNKNOWN. The regression this test guards -- ONE
    # structural delta, not two manufactured infixes -- is unchanged; what
    # moved is the NAME for "and therefore undecided". An `or` chain rewrite
    # is the class round 438 proved no syntactic rule can settle, so it is
    # `undecidable` rather than an open invitation to widen the rule.
    assert r["status"] == PO.PRE_UNDECIDABLE
    assert r["kinds"] == [PO.DELTA_STRUCTURAL]
    assert "boolean condition" in r["why"]


# --- round 438: `undecidable`, and the construction that earns it ---------
#
# Round 434 item 3 left the `append_only` residual as a choice: "a widening
# rule for `append_only` analogous to round 428's shape 4 for `refusal`, or a
# written decision that the class is out of scope. Say which." Round 438 says
# OUT OF SCOPE, and does not say it by argument: the two programs under
# `state/whence/round-438/` produce the same delta and disagree, so there is
# no rule over the delta to widen TO.

_R438 = os.path.join(_C.AGI_ROOT, "state", "whence", "round-438")

_BOOL_EDIT = ('k == "a" or k == "b"', 'k == "a" or k == "b" or k == "c"')


def _r438_case(stem):
    path = os.path.join(_R438, "append-only-%s.lang" % stem)
    with open(path, encoding="utf-8") as f:
        src = f.read()
    fn = src[src.index("fn tag(k) {"):]
    fn = fn[:fn.index("\n}\n") + 2]
    pin = {"id": stem, "guest_file": path, "dir": "+", "guardian":
           "the got slot still contains the probe", "edit": "fn_replace",
           "target": "tag", "becomes": fn.replace(*_BOOL_EDIT)}
    assert pin["becomes"] != fn, "the edit did not apply to %s" % stem
    return src, pin


def test_the_two_counterexamples_produce_the_identical_delta():
    """The load-bearing half of `PRE_UNDECIDABLE`.

    Same guardian shape, same precondition, same edit, and the delta strings
    are equal BYTE FOR BYTE. Whatever a rule could read off this delta, it
    reads the same thing in both programs.
    """
    a_src, a_pin = _r438_case("suffix")
    b_src, b_pin = _r438_case("infix")
    a = PO.edit_precondition(a_src, a_pin)
    b = PO.edit_precondition(b_src, b_pin)
    assert a["deltas"] == b["deltas"]
    assert a["deltas"] == ["structural: ((k == 'a') or (k == 'b'))  ->  "
                           "(((k == 'a') or (k == 'b')) or (k == 'c'))"]
    assert a["kinds"] == b["kinds"] == [PO.DELTA_STRUCTURAL]
    # and both guest files' single check is the same blind shape
    for src in (a_src, b_src):
        v, = PO.classify_source(src)
        assert v.blind == frozenset(("+",)) and v.pre == (PO.PRE_APPEND_ONLY,)


def test_the_two_counterexamples_disagree_when_actually_run():
    """The other half: the answers really are opposite.

    `append_only` HOLDS for the suffix program (the edit appends, the
    `contains` guardian stays blind, the check still passes) and is BROKEN
    for the infix program (the edit splices into the middle, containment is
    destroyed, the check goes red). Run rather than argued -- this is the
    step that makes `undecidable` a measurement.
    """
    import subprocess
    import tempfile
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # ROUND 521 (SWE-loop D): this scratch program used to be written into
    # `here` -- the LIVE `languages/whence/` directory -- and removed in the
    # `finally`. `harness/tests/test_swe_oraclekill.py` (and two more) copy
    # that directory with `shutil.copytree` at MODULE SCOPE, and the driver
    # runs the whence and harness health checks concurrently. At round 517
    # the copy listed `_r438_suffix.lang` with `os.scandir` and found it gone
    # by the time `copy2` reached it: `shutil.Error` at COLLECTION time, so
    # `harness/tests/` collected nothing, `test_tiering.py` went red, and the
    # R001 that followed reddened `test_redattrib.py` x2 for four rounds.
    # `run.py` takes an absolute path, so a temporary directory costs nothing
    # and takes this test out of every other suite's copy scope.
    # `harness/swe/livewrite.py` is the scanner that finds this shape.
    tmp = tempfile.mkdtemp(prefix="r438-")
    got = {}
    try:
        for stem in ("suffix", "infix"):
            src, pin = _r438_case(stem)
            mutant = CP.apply_edit(src, pin)
            prog = os.path.join(tmp, "_r438_%s.lang" % stem)
            with open(prog, "w", encoding="utf-8") as f:
                f.write(mutant)
            p = subprocess.run([sys.executable, os.path.join(here, "run.py"),
                                prog], cwd=here, capture_output=True,
                               text=True, timeout=120)
            got[stem] = p.returncode
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assert got == {"suffix": 0, "infix": 1}


def test_both_counterexamples_are_called_undecidable():
    """The rule must classify the very cases that prove it. If a future
    change made one of these `holds` or `broken`, the pair would no longer
    be a counterexample and `PRE_UNDECIDABLE`'s justification would be gone
    — so this is the test that fails when the claim stops being true.
    """
    for stem in ("suffix", "infix"):
        src, pin = _r438_case(stem)
        r = PO.edit_precondition(src, pin)
        assert r["status"] == PO.PRE_UNDECIDABLE, stem
        assert "not a function of this delta" in r["why"]


def test_undecidable_is_narrower_than_not_string_shaped():
    """`structural` is not `undecidable`. CP03p's edit adds an `if` branch —
    also structural, also not string-shaped — and round 438 kept it out of
    `undecidable` because "an if-expression's arms ARE observed text and a
    widening rule could reach them".

    ROUND 440 wrote that widening rule, so the expected status moves from
    `unknown` to `broken_on_branch` — and the point of the test does not:
    `undecidable` must still not swallow this shape, because the shape IS
    decidable as an edit. The top-level `kinds` stays `structural`; the
    decision comes from the guarded arm, which the top level cannot see.
    """
    base = 'fn f(c) { c }\ncheck "g": contains(f("x"), "x")\n'
    r = _pre(base, 'fn f(c) { if c == "q" { "Q" } else { c } }', 'fn f(c)')
    assert r["kinds"] == [PO.DELTA_STRUCTURAL]
    assert r["status"] == PO.PRE_BROKEN_ON_BRANCH
    assert r["status"] != PO.PRE_UNDECIDABLE
    # a guest predicate CALL returning a bool is not boolean-shaped either
    base2 = ('fn p(c) { true }\nfn f(c) { c }\n'
             'check "g": contains(f("x"), "x")\n')
    r2 = _pre(base2, 'fn f(c) { p(c) }', 'fn f(c)')
    assert r2["status"] == PO.PRE_UNKNOWN


def test_undecidable_never_becomes_holds_or_broken_downstream():
    """It is a REFUSAL to decide, so `check_law` must neither excuse nor
    strictly refute on it, and the audit must call it undecided."""
    v = _v("blindy", ("+",), (PO.PRE_APPEND_ONLY,))
    pins = [{"id": "U", "guest_file": "x.lang", "dir": "+",
             "guardian": "blindy"}]
    pre = {"U": {"status": PO.PRE_UNDECIDABLE,
                 "decided_over": (PO.PRE_APPEND_ONLY,)}}
    res = [{"id": "U", "guardian": "blindy", "verdict": "guarded",
            "co_red": []}]
    law = PO.check_law(pins, res, [v], pre)
    assert [r["id"] for r in law["undecided"]] == ["U"]
    assert law["excused"] == [] and law["strict_violations"] == []
    assert PO.audit_registry(pins, [v], res, pre)[0]["status"] == "undecided"


def test_a_mixed_row_stays_unknown_rather_than_undecidable():
    """The conjunction rule: undecidable on one precondition and merely
    un-ruled on another is `unknown`, because widening the second could
    still settle the row."""
    v = _v("mixed", ("+",), (PO.PRE_APPEND_ONLY, PO.PRE_REFUSAL))
    base = 'fn f(t) { t == "(" or t == "[" }\ncheck "mixed": f("(")\n'
    pin = {"id": "M", "guest_file": "x.lang", "dir": "+", "guardian": "mixed",
           "edit": "fn_replace", "target": "f",
           "becomes": 'fn f(t) { t == "(" or t == "[" or t == "{" }'}
    row = PO.routed_precondition(base, pin, v.pre)
    per = {k: r["status"] for k, r in row["per_precondition"].items()}
    assert per[PO.PRE_APPEND_ONLY] == PO.PRE_UNDECIDABLE
    assert per[PO.PRE_REFUSAL] == PO.PRE_UNKNOWN
    assert row["status"] == PO.PRE_UNKNOWN


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
    EP10m's is `kind_stable`, which the UNROUTED map below cannot reach.

    Round 434 note: `kind_stable` now HAS a decider, and the routed map
    calls EP10m `broken` (see
    `test_no_violation_in_the_recorded_corpus_is_undecided_any_more`).
    This test deliberately keeps the unrouted call, because what it pins is
    round 428's finding that an `append_only`-only map answers a question
    EP10m never asked -- and that stays true however many deciders exist."""
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


def _repointed_registry():
    import json
    with open(os.path.join(REG_422, "host-pins-plus-repointed.json"),
              encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.whence_slow
def test_the_unconditional_audit_calls_five_pins_mispointed():
    """Round 426's measurement, kept: `audit_registry` with NO precondition
    map applies round 420's blindness as if it were unconditional, and on
    the repointed registry that names five pins.

    Round 426 read this as "the registry fails its own acceptance criterion"
    and held the failure open. Round 438 measured that the same command
    answers 0 MISPOINTED the moment `run.json` is passed, so the five were
    never the finding -- the PREDICATE was. This test keeps the
    unconditional number pinned, because it is the input to that comparison
    and the mode every pre-438 caller got by default.
    """
    reg = _repointed_registry()
    rows = PO.audit_registry(reg["pins"], PO.classify_file(SELF_HOST))
    bad = sorted(r["id"] for r in rows if r["status"] == "mispointed")
    assert bad == ["CP03p", "CP06p", "CP08p", "CP10p2", "CP22p2"]
    # ...and every one of them is called mispointed on blindness ALONE.
    assert {r["decided_by"] for r in rows if r["status"] == "mispointed"} == {
        "blindness"}


@pytest.mark.whence_slow
def test_the_precondition_aware_audit_clears_all_five_but_decides_only_one():
    """Round 438. The five are not mispointed and four are not anything.

    `precondition_map` decides, from the EDIT TEXT with no run, that CP22p2
    breaks `append_only` -- so its guardian is not blind to that edit and
    the flag is a false positive. The other four are `unknown`: nothing
    decided the precondition their blindness rests on, so neither
    `mispointed` nor `precondition_broken` is established, and neither is
    claimed.

    So `host-pins-plus-repointed.json`'s criterion -- *"`polarity.py audit`
    over this file must report 0 MISPOINTED"* -- is now literally satisfied
    and is still NOT MET: 0 is reached by declining to decide four rows.
    That is why `undecided` counts against the exit code.
    """
    reg = _repointed_registry()
    vs = PO.classify_file(SELF_HOST)
    with open(SELF_HOST, encoding="utf-8") as f:
        pre = PO.precondition_map(reg["pins"], f.read(), vs)
    rows = PO.audit_registry(reg["pins"], vs, None, pre)
    by = lambda st: sorted(r["id"] for r in rows if r["status"] == st)
    assert by("mispointed") == []
    assert by("precondition_broken") == ["CP22p2"]
    assert by("undecided") == ["CP03p", "CP06p", "CP08p", "CP10p2"]
    assert by("strict_violation") == []
    cp = [r for r in rows if r["id"] == "CP22p2"][0]
    assert cp["decided_by"] == "precondition"     # not "measurement"
    assert cp["pre_status"] == PO.PRE_BROKEN
    # The four split: three rewrite a boolean `or` chain and are
    # `undecidable` (round 438 proved no syntactic rule reaches them);
    # CP03p's delta is an `if` expression, and ROUND 440's widening rule
    # settles it — `broken_on_branch`, the edit rewrites the observed text
    # in place on the arm its own guard selects. The BUCKET is deliberately
    # unchanged: four undecided rows before, four after. `broken_on_branch`
    # is a decision about inputs and this bucket is about observers.
    pre_of = {r["id"]: r["pre_status"] for r in rows
              if r["status"] == "undecided"}
    assert pre_of == {"CP03p": PO.PRE_BROKEN_ON_BRANCH,
                      "CP06p": PO.PRE_UNDECIDABLE,
                      "CP08p": PO.PRE_UNDECIDABLE,
                      "CP10p2": PO.PRE_UNDECIDABLE}


@pytest.mark.whence_slow
def test_the_audit_answer_no_longer_moves_when_the_run_is_passed():
    """The circularity, and the fix, in one assertion.

    Before round 438 the same command over the same registry reported
    **5 MISPOINTED / exit 1** without `run.json` and **0 MISPOINTED / exit
    0** with it -- and the mode that PASSED the "non-circular half" criterion
    was the one that consults the measured `guarded` the criterion exists to
    forbid. `results` may now only sharpen a mispointed pin's candidate
    list; it can no longer decide a status.
    """
    reg = _repointed_registry()
    import json
    with open(os.path.join(REG_422, "run-repointed.json"),
              encoding="utf-8") as f:
        run = json.load(f)
    vs = PO.classify_file(SELF_HOST)
    with open(SELF_HOST, encoding="utf-8") as f:
        pre = PO.precondition_map(reg["pins"], f.read(), vs)
    without = PO.audit_registry(reg["pins"], vs, None, pre)
    with_run = PO.audit_registry(reg["pins"], vs, run["results"], pre)
    assert ([(r["id"], r["status"]) for r in without] ==
            [(r["id"], r["status"]) for r in with_run])
    # and every one of those five measured `guarded`, which is exactly the
    # evidence that used to flip the answer.
    mv = {r["id"]: r["verdict"] for r in run["results"]}
    assert all(mv[i] == "guarded" for i in
               ("CP03p", "CP06p", "CP08p", "CP10p2", "CP22p2"))


@pytest.mark.whence_slow
def test_the_audit_and_check_law_agree_row_for_row():
    """Two instruments, one campaign, one answer.

    `check_law` has conditioned blindness on the precondition since round
    426; `audit_registry` did not until round 438, and on this campaign the
    three modes gave three different answers -- audit-static 5 mispointed,
    audit-with-run 0 mispointed / 5 false positives, `check_law` 1 excused /
    4 undecided. Only `check_law` distinguished "decided broken" from "not
    decided". This pins the agreement so a future divergence is a failure
    rather than a discovery.
    """
    reg = _repointed_registry()
    import json
    with open(os.path.join(REG_422, "run-repointed.json"),
              encoding="utf-8") as f:
        run = json.load(f)
    vs = PO.classify_file(SELF_HOST)
    with open(SELF_HOST, encoding="utf-8") as f:
        pre = PO.precondition_map(reg["pins"], f.read(), vs)
    rows = PO.audit_registry(reg["pins"], vs, run["results"], pre)
    law = PO.check_law(reg["pins"], run["results"], vs, pre)
    st = lambda k: sorted(r["id"] for r in rows if r["status"] == k)
    ids = lambda rs: sorted(r["id"] for r in rs)
    assert st("precondition_broken") == ids(law["excused"])
    assert st("undecided") == ids(law["undecided"])
    assert st("strict_violation") == ids(law["strict_violations"])


def test_the_audit_reports_a_refuted_law_as_a_refutation_not_a_false_positive():
    """The defect this change closes, demonstrated by construction.

    Blind in the pin's direction + precondition ESTABLISHED + measured
    `guarded` is `check_law`'s STRICT violation: round 420's law refuted.
    Pre-438 `audit_registry` hard-coded the opposite conclusion -- it read
    any measured `guarded` as proof the precondition broke -- so the one
    instrument that "runs BEFORE any campaign", and would therefore meet a
    new counterexample first, would have labelled it `(fp)` and moved on.

    Unreachable on the three campaigns on disk (there is no strict violation
    in any of them, which is round 426's headline), so it is pinned
    synthetically on purpose -- the same reason round 434's `no_decider`
    branch is pinned against a synthetic name.
    """
    v = _v("blindy", ("+",), (PO.PRE_APPEND_ONLY,))
    pins = [{"id": "S", "guest_file": "x.lang", "dir": "+",
             "guardian": "blindy"}]
    res = [{"id": "S", "guardian": "blindy", "verdict": "guarded",
            "co_red": []}]
    pre = {"S": {"status": PO.PRE_HOLDS,
                 "decided_over": (PO.PRE_APPEND_ONLY,)}}
    row = PO.audit_registry(pins, [v], res, pre)[0]
    assert row["status"] == "strict_violation"
    assert row["decided_by"] == "precondition"
    # `check_law` calls the identical input a strict violation...
    law = PO.check_law(pins, res, [v], pre)
    assert [r["id"] for r in law["strict_violations"]] == ["S"]
    # ...and this is what the audit used to say about it.
    assert PO.audit_registry(pins, [v], res)[0]["status"] == \
        "precondition_broken"


def test_a_blind_guardian_naming_no_precondition_is_unconditionally_blind():
    """`pre` empty means the blindness rests on nothing, so no edit can
    excuse it: `mispointed` stands, and a measured `guarded` refutes the
    ANALYSIS rather than the law. Not reachable from `classify_file` today
    (every blind verdict it builds carries a precondition) and pinned so
    that stays a property rather than an accident.
    """
    v = _v("blindy", ("+",))                       # no precondition
    pins = [{"id": "U", "guest_file": "x.lang", "dir": "+",
             "guardian": "blindy"}]
    pre = {"U": {"status": PO.PRE_INAPPLICABLE, "decided_over": ()}}
    assert PO.audit_registry(pins, [v], None, pre)[0]["status"] == \
        "mispointed"
    res = [{"id": "U", "guardian": "blindy", "verdict": "guarded",
            "co_red": []}]
    assert PO.audit_registry(pins, [v], res, pre)[0]["status"] == \
        "strict_violation"


def test_an_undecided_pin_is_never_promoted_to_either_side():
    """`unknown` drags the row to `undecided` whatever the run says. A
    measured `guarded` is not evidence the precondition broke -- it is
    equally evidence the blindness analysis is wrong -- and choosing the
    first is the unfalsifiable excuse round 426's guards exist to prevent.
    """
    v = _v("blindy", ("+",), (PO.PRE_APPEND_ONLY,))
    pins = [{"id": "U", "guest_file": "x.lang", "dir": "+",
             "guardian": "blindy"}]
    pre = {"U": {"status": PO.PRE_UNKNOWN,
                 "decided_over": (PO.PRE_APPEND_ONLY,)}}
    for res in (None, [{"id": "U", "guardian": "blindy",
                        "verdict": "guarded", "co_red": []}],
                [{"id": "U", "guardian": "blindy", "verdict": "shadowed",
                  "co_red": []}]):
        assert PO.audit_registry(pins, [v], res, pre)[0]["status"] == \
            "undecided"


@pytest.mark.whence_slow
def test_the_audit_cli_exits_nonzero_on_undecided_rows(capsys):
    """0 MISPOINTED is not a pass while a row is open. Both modes agree,
    which is the round-438 property; the exit code is 1 in both because
    four rows are undecided, not because anything is mispointed.
    """
    reg_path = os.path.join(REG_422, "host-pins-plus-repointed.json")
    run_path = os.path.join(REG_422, "run-repointed.json")
    assert PO.main(["polarity.py", "audit", reg_path]) == 1
    first = capsys.readouterr().out
    assert PO.main(["polarity.py", "audit", reg_path, run_path]) == 1
    second = capsys.readouterr().out
    assert first == second
    assert "0 MISPOINTED" in first and "4 undecided" in first
    assert "1 precondition-broken" in first and "0 strict-violation" in first


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


# --- round 428: the `refusal` precondition, decided from the edit alone ----
#
# `refusal` is what `missed(...)` -- the parser guest file's dominant
# guardian -- is monotone along. Round 426 decided `append_only` and left
# this one as its own item 1. The four shapes below are the ones the corpus
# uses; the hermetic tests pin each shape in BOTH polarities, because a
# decider that can only ever say `holds` is the unfalsifiable excuse round
# 426's three guards exist to prevent.

REF_BASE = (
    'fn f(x) {\n'
    '  let a = x + 1\n'
    '  a\n'
    '}\n'
    'check "g": missed(f(1))\n'
)


def _fnpin(becomes, target="f"):
    return {"id": "R1", "guest_file": "examples/self_host.lang", "dir": "+",
            "guardian": "g", "edit": "fn_replace", "target": target,
            "becomes": becomes}


def _ref(base, becomes, target="f"):
    return PO.refusal_precondition(base, _fnpin(becomes, target))


def test_substituting_a_miss_for_a_value_holds():
    r = _ref(REF_BASE, 'fn f(x) {\n  let a = x + 1\n  miss ("no")\n}')
    assert r["status"] == PO.PRE_HOLDS
    assert r["kinds"] == [PO.REF_REFUSE]
    assert r["decided_over"] == (PO.PRE_REFUSAL,)


def test_substituting_a_value_for_a_miss_is_a_positive_broken():
    base = ('fn f(x) {\n  miss ("no")\n}\ncheck "g": missed(f(1))\n')
    r = _ref(base, 'fn f(x) {\n  x + 1\n}')
    assert r["status"] == PO.PRE_BROKEN
    assert r["kinds"] == [PO.REF_REVIVE]


def test_a_guard_inserted_around_the_tail_holds():
    """Shape 2, and the shape CP13p uses: the old statements survive
    verbatim as one arm of a new trailing `if` whose other arm misses."""
    r = _ref(REF_BASE,
             'fn f(x) {\n'
             '  let a = x + 1\n'
             '  if x > 3 { miss ("too big") } else { a }\n'
             '}')
    assert r["status"] == PO.PRE_HOLDS


def test_a_guard_removed_from_the_tail_is_broken():
    base = ('fn f(x) {\n'
            '  let a = x + 1\n'
            '  if x > 3 { miss ("too big") } else { a }\n'
            '}\ncheck "g": missed(f(9))\n')
    r = _ref(base, 'fn f(x) {\n  let a = x + 1\n  a\n}')
    assert r["status"] == PO.PRE_BROKEN


def test_a_guard_inserted_with_extra_statements_is_not_read_as_a_guard():
    """The surviving arm must be the old statements EXACTLY. An `if` that
    also rewrites what it wraps is a rewrite, and belongs in `unknown`."""
    r = _ref(REF_BASE,
             'fn f(x) {\n'
             '  let a = x + 1\n'
             '  if x > 3 { miss ("too big") } else { a + 100 }\n'
             '}')
    assert r["status"] == PO.PRE_UNKNOWN


def test_widening_an_existing_miss_guard_holds():
    """Shape 4 -- the one three shapes missed. CP16p is exactly this."""
    base = ('fn f(x) {\n'
            '  if x > 3 { miss ("no") } else { x }\n'
            '}\ncheck "g": missed(f(9))\n')
    r = _ref(base, 'fn f(x) {\n  if x > 3 or x < 0 { miss ("no") } else { x }\n}')
    assert r["status"] == PO.PRE_HOLDS


def test_narrowing_an_existing_miss_guard_is_broken():
    base = ('fn f(x) {\n'
            '  if x > 3 { miss ("no") } else { x }\n'
            '}\ncheck "g": missed(f(9))\n')
    r = _ref(base,
             'fn f(x) {\n  if x > 3 and x < 9 { miss ("no") } else { x }\n}')
    assert r["status"] == PO.PRE_BROKEN


def test_the_polarity_flips_when_the_miss_is_in_the_else_arm():
    base = ('fn f(x) {\n'
            '  if x > 3 { x } else { miss ("no") }\n'
            '}\ncheck "g": missed(f(1))\n')
    wider = _ref(base,
                 'fn f(x) {\n  if x > 3 or x < 0 { x } else { miss ("no") }\n}')
    narrower = _ref(base,
                    'fn f(x) {\n'
                    '  if x > 3 and x < 9 { x } else { miss ("no") }\n}')
    assert wider["status"] == PO.PRE_BROKEN      # fewer inputs reach the miss
    assert narrower["status"] == PO.PRE_HOLDS    # more do


def test_a_guard_whose_two_arms_both_miss_is_not_a_refusal_edge():
    base = ('fn f(x) {\n'
            '  if x > 3 { miss ("a") } else { miss ("b") }\n'
            '}\ncheck "g": missed(f(1))\n')
    r = _ref(base,
             'fn f(x) {\n  if x > 3 or x < 0 { miss ("a") } else { miss ("b") }\n}')
    assert r["status"] == PO.PRE_UNKNOWN


def test_a_value_to_value_edit_is_undecided_not_broken():
    r = _ref(REF_BASE, 'fn f(x) {\n  let a = x + 2\n  a\n}')
    assert r["status"] == PO.PRE_UNKNOWN


def test_a_rescue_arm_is_not_a_miss_however_it_is_written():
    """`a rescue b` is the operator that turns a miss BACK into a value, so
    a node containing one can never satisfy `_yields_miss`."""
    prog = PO.P.parse(
        'fn f(x) { miss ("no") rescue 1 }\ncheck "g": f(1) == 1\n')
    fn = prog.stmts[0]
    assert not PO._yields_miss(fn.body)


def test_an_edit_that_refuses_in_one_place_and_rewrites_in_another_is_unknown():
    base = ('fn f(x) {\n  x + 1\n}\n'
            'fn h(x) {\n  x + 2\n}\n'
            'check "g": missed(f(1))\n')
    pin = {"id": "R1", "guest_file": "examples/self_host.lang", "dir": "+",
           "guardian": "g", "edit": "line_replace", "needle": "  x + 1",
           "becomes": '  miss ("no")'}
    only_refuse = PO.refusal_precondition(base, pin)
    assert only_refuse["status"] == PO.PRE_HOLDS
    pin2 = dict(pin, needle="  x + 2", becomes="  x + 99")
    assert PO.refusal_precondition(base, pin2)["status"] == PO.PRE_UNKNOWN


def test_a_revive_anywhere_outranks_a_refuse_elsewhere():
    base = ('fn f(x) {\n  x + 1\n}\n'
            'fn h(x) {\n  miss ("no")\n}\n'
            'check "g": missed(f(1))\n')
    pin = {"id": "R1", "guest_file": "examples/self_host.lang", "dir": "+",
           "guardian": "g", "edit": "fn_replace", "target": "f",
           "becomes": 'fn f(x) {\n  miss ("gone")\n}',
           "also": [{"edit": "line_replace", "needle": '  miss ("no")',
                     "becomes": "  x + 7"}]}
    r = PO.refusal_precondition(base, pin)
    assert r["status"] == PO.PRE_BROKEN
    assert PO.REF_REVIVE in r["kinds"] and PO.REF_REFUSE in r["kinds"]


def test_an_identity_edit_is_identity_under_refusal_too():
    base = 'fn f() { 1 }\n\ncheck "g": missed(f())\n'
    r = PO.refusal_precondition(base, _fnpin('fn f() { 1 }\n'))
    assert r["status"] == "identity"


def test_an_unlocatable_refusal_edit_is_reported_not_raised():
    r = _ref(REF_BASE, 'fn nope() { 1 }', target="nowhere")
    assert r["status"] == "unlocatable"
    assert r["decided_over"] == (PO.PRE_REFUSAL,)


# --- `_implies`: a proof procedure, so False means "not shown" -------------

def _cond(src):
    return PO.P.parse('check "c": %s' % src).stmts[0].expr


@pytest.mark.parametrize("p,q,expected", [
    ("a", "a", True),
    ("a", "a or b", True),
    ("a", "b or a", True),
    ("a and b", "a", True),
    ("a or b", "a", False),
    ("a", "a and b", False),
    ("a and b", "a and b or c", True),
    ("a or b", "b or a or c", True),
    ("a", "b", False),
])
def test_implies_proves_only_what_is_syntactically_there(p, q, expected):
    assert PO._implies(_cond(p), _cond(q)) is expected


# --- routing: decide the precondition THIS pin's guardian rests on ---------

def test_an_unrouted_map_still_answers_append_only_and_says_so():
    pins = [_fnpin('fn f(x) {\n  let a = x + 1\n  miss ("no")\n}')]
    row = PO.precondition_map(pins, REF_BASE)["R1"]
    assert row["decided_over"] == (PO.PRE_APPEND_ONLY,)
    assert row["status"] == PO.PRE_UNKNOWN      # not string-shaped


def test_a_routed_map_sends_a_missed_guardian_to_refusal():
    pins = [_fnpin('fn f(x) {\n  let a = x + 1\n  miss ("no")\n}')]
    vs = PO.classify_source(REF_BASE)
    row = PO.precondition_map(pins, REF_BASE, vs)["R1"]
    assert row["decided_over"] == (PO.PRE_REFUSAL,)
    assert row["status"] == PO.PRE_HOLDS


def test_a_guardian_that_is_not_blind_has_no_precondition_to_decide():
    base = ('fn f(x) {\n  let a = x + 1\n  a\n}\n'
            'check "g": f(1) == 2\n')
    pins = [_fnpin('fn f(x) {\n  let a = x + 1\n  miss ("no")\n}')]
    row = PO.precondition_map(pins, base, PO.classify_source(base))["R1"]
    assert row["status"] == PO.PRE_INAPPLICABLE
    assert row["decided_over"] == ()


def test_a_guardian_naming_no_check_is_inapplicable_not_unknown():
    pins = [dict(_fnpin('fn f(x) {\n  miss ("no")\n}'), guardian="nowhere")]
    row = PO.precondition_map(pins, REF_BASE,
                              PO.classify_source(REF_BASE))["R1"]
    assert row["status"] == PO.PRE_INAPPLICABLE


def test_routing_is_conjunctive_and_broken_wins():
    base = ('fn f(x) {\n  miss ("no")\n}\n'
            'check "g": missed(f(1)) and contains("abc", "a")\n')
    vs = PO.classify_source(base)
    assert set(vs[0].pre) == {PO.PRE_REFUSAL, PO.PRE_APPEND_ONLY}
    # revives the miss AND is not an append -> refusal broken, append_only
    # undecided; the conjunction is `broken`.
    row = PO.routed_precondition(base, _fnpin('fn f(x) {\n  x + 1\n}'),
                                 vs[0].pre)
    assert row["status"] == PO.PRE_BROKEN
    assert row["per_precondition"][PO.PRE_REFUSAL]["status"] == PO.PRE_BROKEN


def test_a_precondition_with_no_decider_drags_the_row_to_unknown():
    """The `no_decider` MECHANISM, pinned against a synthetic name.

    Round 428 wrote this against `kind_stable`, the last precondition with
    no decider. Round 434 built that decider, which would have left the
    branch with no user at all -- `no_decider` unreachable, and round 422's
    own finding is that an unreachable thing is not a tested thing. So the
    mechanism is re-pinned here against a precondition name nothing decides,
    and `test_every_precondition_in_the_atom_table_has_a_decider` is what
    says the REAL table has no gap."""
    assert "invented_for_this_test" not in PO.PRECONDITION_DECIDERS
    row = PO.routed_precondition(
        REF_BASE, _fnpin('fn f(x) {\n  let a = x + 1\n  miss ("no")\n}'),
        (PO.PRE_REFUSAL, "invented_for_this_test"))
    assert row["per_precondition"][PO.PRE_REFUSAL]["status"] == PO.PRE_HOLDS
    assert row["per_precondition"]["invented_for_this_test"]["status"] == \
        PO.PRE_NO_DECIDER
    assert row["status"] == PO.PRE_UNKNOWN


def test_every_precondition_in_the_atom_table_has_a_decider():
    """Round 434. Each atom in `MONOTONE_BUILTINS` names the precondition
    its monotonicity rests on, and from this round every one of them is
    decided from the edit alone. A new atom that names a fourth
    precondition must arrive with its decider or fail here -- which is the
    only reading under which the conditional law stays falsifiable."""
    named = set(pre for _, pre in PO.MONOTONE_BUILTINS.values())
    named.add(PO.PRE_KIND_STABLE)          # the guest `is_*` convention
    assert named == {PO.PRE_APPEND_ONLY, PO.PRE_REFUSAL, PO.PRE_KIND_STABLE}
    assert named <= set(PO.PRECONDITION_DECIDERS)


# --- check_law refuses to bucket on the wrong precondition ----------------

def _mismatch_law(status):
    pins = [{"id": "P", "dir": "+", "guardian": "g"}]
    res = [{"id": "P", "verdict": "guarded", "guardian": "g"}]
    pre = {"P": {"status": status, "decided_over": (PO.PRE_APPEND_ONLY,)}}
    return PO.check_law(pins, res, [_v("g", ("+",), (PO.PRE_REFUSAL,))], pre)


def test_a_holds_decided_over_the_wrong_precondition_does_not_refute():
    out = _mismatch_law(PO.PRE_HOLDS)
    assert out["strict_violations"] == []
    assert [r["id"] for r in out["undecided"]] == ["P"]
    assert out["violations"][0]["pre_mismatch"] is True


def test_a_broken_decided_over_the_wrong_precondition_does_not_excuse():
    out = _mismatch_law(PO.PRE_BROKEN)
    assert out["excused"] == []
    assert [r["id"] for r in out["undecided"]] == ["P"]


def test_a_row_with_no_decided_over_is_read_as_append_only():
    """Back-compat: every precondition map written before round 428 was an
    `append_only` map, and a pin resting on `append_only` must still be
    bucketed by it."""
    pins = [{"id": "P", "dir": "+", "guardian": "g"}]
    res = [{"id": "P", "verdict": "guarded", "guardian": "g"}]
    out = PO.check_law(pins, res, [_v("g", ("+",), (PO.PRE_APPEND_ONLY,))],
                       {"P": {"status": PO.PRE_HOLDS}})
    assert [r["id"] for r in out["strict_violations"]] == ["P"]
    assert out["violations"][0]["pre_mismatch"] is False


# --- corpus: what round 428 actually measured on the parser guest file -----

def _host_src():
    with open(SELF_HOST, encoding="utf-8") as f:
        return f.read()


def _host_reg():
    import json
    with open(os.path.join(REG_422, "host-pins-plus.json"),
              encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("pid,expected", [
    ("CP13p", PO.PRE_HOLDS),      # guard inserted: trailing-comma rejection
    ("CP14p", PO.PRE_HOLDS),
    ("CP15p", PO.PRE_HOLDS),
    ("CP16p", PO.PRE_HOLDS),      # guard WIDENED -- shape 4
    ("CP21p", PO.PRE_HOLDS),      # substitution
    # Round 432: CP17p was `unknown` here through round 431. Shape 5
    # (`_let_hop_relation`) substitutes the edited `let`'s two RHSs into the
    # guard condition one hop below it, and `_norm` turns the resulting
    # `(if ...) != 0` into the `and`/`or` skeleton `_implies` can work on.
    ("CP17p", PO.PRE_HOLDS),      # a value feeding a downstream guard
    # CP18p/CP19p stay `unknown` on purpose, and §C of round 432's bank says
    # why: both reduce to `contains(X, y) -> len(X) > 0`, which is FALSE in
    # Whence. `test_the_contains_length_law_is_false_in_whence` is the
    # counterexample, and it is the reason this is the right answer rather
    # than a gap.
    ("CP18p", PO.PRE_UNKNOWN),
    ("CP19p", PO.PRE_UNKNOWN),
    ("CP20p", PO.PRE_UNKNOWN),    # branch selection, arms not all miss
])
def test_the_refusal_pins_decide_the_way_round_428_measured(pid, expected):
    reg = _host_reg()
    pin = [p for p in reg["pins"] if p["id"] == pid][0]
    assert PO.refusal_precondition(_host_src(), pin)["status"] == expected


def test_cp16p_is_decided_only_by_the_guard_widening_shape():
    """REGRESSION for the round's own measured miss: the three shapes
    written first (substitute / guard inserted / guard removed) all return
    `unknown` on CP16p, which widens an EXISTING guard's condition. Deleting
    `_guard_cond_relation` must break this test and nothing else in the
    `holds` column."""
    reg = _host_reg()
    pin = [p for p in reg["pins"] if p["id"] == "CP16p"][0]
    src = _host_src()
    saved = PO._guard_cond_relation
    try:
        PO._guard_cond_relation = lambda a, b: None
        assert PO.refusal_precondition(src, pin)["status"] == PO.PRE_UNKNOWN
    finally:
        PO._guard_cond_relation = saved
    assert PO.refusal_precondition(src, pin)["status"] == PO.PRE_HOLDS


def test_no_refusal_pin_in_the_corpus_comes_back_broken():
    """Every `+` pin on a `missed(...)` rule was written to refuse MORE. A
    `broken` here would be a mis-designed pin, not a broken law -- so this
    test is a claim about the REGISTRY, and it is the one that would notice
    a future pin planted the wrong way round."""
    reg, src = _host_reg(), _host_src()
    vs = PO.classify_file(SELF_HOST)
    by = {v.label: v for v in vs}
    ref = [p for p in reg["pins"]
           if by.get(p["guardian"]) and PO.PRE_REFUSAL in by[p["guardian"]].pre]
    assert len(ref) == 9
    got = [PO.refusal_precondition(src, p)["status"] for p in ref]
    assert got.count(PO.PRE_BROKEN) == 0
    assert got.count(PO.PRE_HOLDS) == 6      # round 432: was 5, +CP17p
    assert got.count(PO.PRE_UNKNOWN) == 3      # round 432: was 4, -CP17p


def test_routing_more_than_doubles_the_decided_share_of_the_registry():
    reg, src = _host_reg(), _host_src()
    vs = PO.classify_file(SELF_HOST)
    routed = PO.precondition_map(reg["pins"], src, vs)
    unrouted = PO.precondition_map(reg["pins"], src)

    def decided(m):
        return sum(1 for r in m.values()
                   if r["status"] in (PO.PRE_HOLDS, PO.PRE_BROKEN))
    assert len(reg["pins"]) == 23
    assert decided(unrouted) == 5           # round 426's number
    assert decided(routed) == 11            # round 432: was 10, +CP17p
    # and the 5 pins whose guardian is not blind at all stop being counted
    # as `unknown`, which is what made 18 read as a coverage number.
    assert sum(1 for r in routed.values()
               if r["status"] == PO.PRE_INAPPLICABLE) == 5


def test_the_wrong_question_hazard_is_latent_in_every_recorded_artefact():
    """The finding that made this round's guard prophylactic rather than a
    fix: 14 of 23 pins rest on something other than `append_only`, and not
    one of them has ever been a violation, so no published number of this
    program is wrong. If a future campaign makes one a violation, THIS test
    goes red and the round that sees it must read the partition again."""
    import json
    src = _host_src()
    vs = PO.classify_file(SELF_HOST)
    by = {v.label: v for v in vs}
    reg = _host_reg()
    off = [p["id"] for p in reg["pins"]
           if by.get(p["guardian"]) is not None
           and PO.PRE_APPEND_ONLY not in by[p["guardian"]].pre]
    assert len(off) == 14
    for regf, runf in (("host-pins-plus.json", "run-plus-witnessed.json"),
                       ("host-pins-plus-repointed.json", "run-repointed.json")):
        with open(os.path.join(REG_422, regf), encoding="utf-8") as f:
            r = json.load(f)
        with open(os.path.join(REG_422, runf), encoding="utf-8") as f:
            run = json.load(f)
        out = PO.check_law(r["pins"], run["results"], vs,
                           PO.precondition_map(r["pins"], src, vs))
        assert [v["id"] for v in out["violations"] if v["pre_mismatch"]] == []


def test_the_law_headline_is_unchanged_by_routing():
    """Routing changes which decider answers; on the recorded campaign it
    changes no bucket, because the one violation rests on `append_only`."""
    import json
    src = _host_src()
    vs = PO.classify_file(SELF_HOST)
    with open(os.path.join(REG_422, "host-pins-plus.json"),
              encoding="utf-8") as f:
        reg = json.load(f)
    with open(os.path.join(REG_422, "run-plus-witnessed.json"),
              encoding="utf-8") as f:
        run = json.load(f)
    routed = PO.check_law(reg["pins"], run["results"], vs,
                          PO.precondition_map(reg["pins"], src, vs))
    plain = PO.check_law(reg["pins"], run["results"], vs,
                         PO.precondition_map(reg["pins"], src))
    for k in ("confirmations", "violations", "strict_violations", "excused",
              "undecided"):
        assert len(routed[k]) == len(plain[k]), k
    assert [r["id"] for r in routed["excused"]] == ["CP22p2"]


# --- the power table, which is this round's headline and its regression ---

def _fisher_two_sided(a, b, c, d):
    """Fisher exact, two-sided by the sum-of-smaller-probabilities rule.

    Written out rather than imported: this repo is stdlib-first, and the
    whole point of the number is that a reader can check it.
    """
    import math
    n, r1, r2, c1 = a + b + c + d, a + b, c + d, a + c

    def p(x):
        y, z = r1 - x, c1 - x
        w = r2 - z
        if min(x, y, z, w) < 0:
            return 0.0
        return math.comb(r1, x) * math.comb(r2, z) / math.comb(n, c1)
    p0 = p(a)
    return sum(p(x) for x in range(0, min(r1, c1) + 1) if p(x) <= p0 + 1e-12)


def _law_table(routed, campaigns, collisions=None):
    """The law-scoped contingency over BLIND pins, deduplicated by pin.

    Round 434: the dedup key is `(guest, id, GUARDIAN)`, not `(guest, id)`.
    Two of the three campaigns are registries over the SAME guest file with
    the SAME pin ids -- `host-pins-plus.json` and its repointed twin -- so
    the old key silently let the last campaign overwrite the first, and
    `dict` update order decided which measurement of CP03p reached the
    table. The same pin pointed at the same check is the same evidence and
    must dedup (CP22p2, unmoved by the repoint, is measured twice); the same
    pin pointed at a DIFFERENT check is different evidence and must not.
    Measured: the fix changes no cell today (CP03p is `unknown` on both
    sides, so it lands in none of the four), which is why it is landed with
    a test rather than a new number --
    `test_the_two_host_registries_do_not_silently_overwrite_each_other`.
    """
    import json
    seen = {}
    by_pin = {}
    for guest, pinf, runf in campaigns:
        with open(pinf, encoding="utf-8") as f:
            reg = json.load(f)
        with open(runf, encoding="utf-8") as f:
            run = json.load(f)
        with open(guest, encoding="utf-8") as f:
            src = f.read()
        vs = PO.classify_file(guest)
        pre = (PO.precondition_map(reg["pins"], src, vs) if routed
               else PO.precondition_map(reg["pins"], src))
        out = PO.check_law(reg["pins"], run["results"], vs, pre)
        for row in out["violations"] + out["confirmations"]:
            cell = ((pre.get(row["id"]) or {}).get("status"),
                    row["verdict"] == "guarded")
            was = by_pin.get((guest, row["id"]))
            if was is not None and was != cell and collisions is not None:
                collisions.append((guest, row["id"], was, cell))
            by_pin[(guest, row["id"])] = cell
            seen[(guest, row["id"], row.get("guardian"))] = cell

    def cell(status, guarded):
        return sum(1 for s, g in seen.values()
                   if s == status and g is guarded)
    return (cell(PO.PRE_HOLDS, False), cell(PO.PRE_HOLDS, True),
            cell(PO.PRE_BROKEN, False), cell(PO.PRE_BROKEN, True))


def _campaigns():
    R428 = os.path.join(_C.AGI_ROOT, "state", "whence", "round-428")  # round 431: see REG_422
    return [(os.path.join(HERE, "examples", "self_eval.lang"),
             os.path.join(REG_416, "eval-pins.json"),
             os.path.join(REG_416, "run.json")),
            (SELF_HOST, os.path.join(REG_422, "host-pins-plus.json"),
             os.path.join(R428, "run-plus-428.json")),
            (SELF_HOST, os.path.join(REG_422, "host-pins-plus-repointed.json"),
             os.path.join(REG_422, "run-repointed.json"))]


def test_the_unrouted_table_reproduces_round_426s_p_of_one_tenth():
    """A cross-check on the arithmetic before the new number is believed:
    with round 426's single decider this reproduces its published
    `[[3,0],[0,2]]`, p = 0.10, computed here independently."""
    a, b, c, d = _law_table(False, _campaigns())
    assert (a, b, c, d) == (3, 0, 0, 2)
    assert round(_fisher_two_sided(a, b, c, d), 4) == 0.1000


def test_routing_and_refusal_take_the_law_below_p_of_five_hundredths():
    """Round 426 §11 costed this at "two more `holds` and two more `broken`
    in the law-scoped table", i.e. a designed campaign. Deciding the
    precondition each pin ACTUALLY rests on gets there for nothing: five
    pins move `unknown` -> `holds` and the table becomes [[8,0],[0,2]].

    This is not classifier-on-outcome: `refusal_precondition` reads the
    edit and the guest source and never a verdict (guard 1).

    Round 432: shape 5 adds CP17p to the confirmation cell, [[8,0],[0,2]]
    -> [[9,0],[0,2]], p 0.0222 -> 0.0182.

    Round 434: `kind_precondition` decides the third and last precondition.
    EP08p (`shadowed`, i.e. not guarded) moves `unknown` -> `holds` and
    EP10m (`guarded`) moves `unknown` -> `broken`, so BOTH diagonal cells
    grow: [[9,0],[0,2]] -> [[10,0],[0,3]], p 0.0182 -> 0.0035. Nothing was
    re-run to get it; the campaigns are round 416's and round 428's."""
    a, b, c, d = _law_table(True, _campaigns())
    assert (a, b, c, d) == (10, 0, 0, 3)
    assert _fisher_two_sided(a, b, c, d) < 0.05
    assert round(_fisher_two_sided(a, b, c, d), 4) == 0.0035


def test_the_significance_does_not_rest_on_the_shapes_added_after_looking():
    """DISCLOSURE, pinned, and now covering TWO shapes.

    Shape 4 (`_guard_cond_relation`) was written after round 428 had seen
    CP16p's measured verdict. Shape 5 (`_let_hop_relation`) is the same
    hazard one round on: round 428's next-steps NAMED CP17p/CP18p/CP19p as
    the class to attack, and their measured verdicts (`shadowed`, i.e. the
    not-guarded column) were in the file that named them. Neither decider
    can see a verdict, but both authors could.

    Round 434 is the same hazard a THIRD time, and the worst instance of
    it: `kind_precondition` was written to decide EP10m, whose measured
    `guarded` verdict is printed by the very `law` command whose baseline
    round 434 read first. The decider still cannot see a verdict -- it
    reads the edit, the guest source and the guardian's tested KIND -- but
    the author could, so it is removable here like the other two.

    So the honest control removes them one at a time AND together. Each
    shape alone costs one `holds`; both shapes together cost two; removing
    the kind decider costs one `holds` AND one `broken`. With all three
    gone the table is [[7,0],[0,2]] -- round 428's number exactly, which is
    the point of the control -- and the result still survives at
    p = 0.0278."""
    def table(**kw):
        saved = {k: getattr(PO, k) for k in kw}
        try:
            for k, v in kw.items():
                setattr(PO, k, v)
            return _law_table(True, _campaigns())
        finally:
            for k, v in saved.items():
                setattr(PO, k, v)

    def without_kind(**kw):
        saved = dict(PO.PRECONDITION_DECIDERS)
        try:
            PO.PRECONDITION_DECIDERS.pop(PO.PRE_KIND_STABLE, None)
            return table(**kw) if kw else _law_table(True, _campaigns())
        finally:
            PO.PRECONDITION_DECIDERS.clear()
            PO.PRECONDITION_DECIDERS.update(saved)

    no4 = table(_guard_cond_relation=lambda a, b: None)
    no5 = table(_let_hop_relation=lambda *a, **k: None)
    neither = table(_guard_cond_relation=lambda a, b: None,
                    _let_hop_relation=lambda *a, **k: None)
    assert no4 == (9, 0, 0, 3)
    assert no5 == (9, 0, 0, 3)
    assert neither == (8, 0, 0, 3)
    # round 434's own removal, alone and on top of both shapes
    assert without_kind() == (9, 0, 0, 2)
    none_of_three = without_kind(_guard_cond_relation=lambda a, b: None,
                                 _let_hop_relation=lambda *a, **k: None)
    assert none_of_three == (7, 0, 0, 2)
    assert round(_fisher_two_sided(*none_of_three), 4) == 0.0278
    assert _fisher_two_sided(*none_of_three) < 0.05


# --- round 432: shape 5, the one-hop let-substitution ----------------------

def _checks(src):
    """`{label: ok}` for a guest program, RUN. Used only by the two
    counterexamples below, which are claims about Whence's semantics and
    would be worthless asserted against the analyser's model of them."""
    from whence.interp import Interpreter
    it = Interpreter()
    it.run(src)
    return {c["label"]: c["ok"] for c in it.checks}


def _hop_pin(needle, becomes):
    return {"id": "T", "guest_file": "x.lang", "edit": "line_replace",
            "needle": needle, "becomes": becomes}


#: A block with the exact shape of CP18p: a `let` whose value is read one
#: hop later by an `if` whose then-arm only ever misses.
_HOP_SRC = """fn f(acc, x) {
  let dup = contains(acc, x)
  let acc2 = push(acc, x)
  if dup { miss ("dup") }
  else { acc2 }
}
check "c": missed(f([1], 1))
"""


def _hop_status(src, needle, becomes):
    return PO.refusal_precondition(src, _hop_pin(needle, becomes))["status"]


def test_cp17p_is_decided_only_by_the_one_hop_shape():
    """REGRESSION, the mirror of `test_cp16p_is_decided_only_by_the_guard_
    widening_shape`. Deleting `_let_hop_relation` must put CP17p back to
    `unknown` and move nothing else in the `holds` column."""
    reg, src = _host_reg(), _host_src()
    pin = [p for p in reg["pins"] if p["id"] == "CP17p"][0]
    assert PO.refusal_precondition(src, pin)["status"] == PO.PRE_HOLDS
    saved = PO._let_hop_relation
    try:
        PO._let_hop_relation = lambda *a, **k: None
        assert PO.refusal_precondition(src, pin)["status"] == PO.PRE_UNKNOWN
    finally:
        PO._let_hop_relation = saved


def test_the_one_hop_shape_alone_does_not_decide_cp17p_without_the_normaliser():
    """Round 428's next-steps: a one-hop rule "would decide all three, and
    `_implies` -- written this round -- is already the relation it needs".

    The second half is FALSE, and this is the measurement. Shape 5 hands
    `_implies` a COMPARISON with an `if` inside it, which matches none of
    the four laws. With `_norm` stubbed out and shape 5 fully live, CP17p
    is `unknown`; the normaliser is what earns the `holds`."""
    reg, src = _host_reg(), _host_src()
    pin = [p for p in reg["pins"] if p["id"] == "CP17p"][0]
    saved = PO._norm
    try:
        PO._norm = lambda n, depth=0: n
        PO._PARSE_CACHE.clear()
        assert PO.refusal_precondition(src, pin)["status"] == PO.PRE_UNKNOWN
    finally:
        PO._norm = saved
        PO._PARSE_CACHE.clear()
    assert PO.refusal_precondition(src, pin)["status"] == PO.PRE_HOLDS


def test_the_undecided_hop_names_its_residual_obligation():
    """CP18p's report used to read `unknown: contains(...) -> <Binary>`.
    An undecided verdict that does not say WHAT is undecided is the thing
    round 428's own next-steps then mis-described. After shape 5 the delta
    carries the two SUBSTITUTED conditions, so the residual is legible."""
    reg, src = _host_reg(), _host_src()
    pin = [p for p in reg["pins"] if p["id"] == "CP18p"][0]
    got = PO.refusal_precondition(src, pin)
    assert got["status"] == PO.PRE_UNKNOWN
    assert any("contains(acc, nm.name)" in d and "(len(acc) > 0)" in d
               for d in got["deltas"]), got["deltas"]


def test_the_contains_length_law_is_false_in_whence():
    """The residual CP18p and CP19p reduce to, refuted by RUNNING it.

    `contains(X, y) -> len(X) > 0` reads as obviously true and is the law a
    later round would reach for to close those two pins. It is false:
    `contains` takes `hay:str|list` (interp.py) and the empty string
    contains the empty string. Adding it would make `holds` a guess."""
    got = _checks('check "law fails": contains("", "") and not (len("") > 0)\n'
                  'check "list form holds": not contains([], 1)\n')
    assert got["law fails"] is True
    assert got["list form holds"] is True


def test_a_let_bound_miss_does_not_abort_the_block():
    """...and the obvious REPAIR of that law is unsound too.

    The natural guard is "the same block passes X to `push`, which takes
    lists only, so a non-list X misses anyway". It does not: a `let` whose
    RHS is a miss does NOT abort the block, so a guard arm that never reads
    the bound name returns a value as usual. `probe("xyz")` is 42, not a
    miss. This is why shape 5 stops at `unknown` on CP18p/CP19p, and the
    stopping is the correct answer rather than a coverage gap."""
    got = _checks(
        'fn probe(acc) {\n'
        '  let dup = contains(acc, "a")\n'
        '  let acc2 = push(acc, "a")\n'
        '  if dup { miss ("dup") }\n'
        '  else { 42 }\n'
        '}\n'
        'check "string hay still returns a value": probe("xyz") == 42\n'
        'check "and the pushed name is unread": not missed(probe("xyz"))\n')
    assert got["string hay still returns a value"] is True
    assert got["and the pushed name is unread"] is True


def test_the_hop_carries_the_polarity_flip_when_the_miss_is_in_the_else_arm():
    """D2. Widening the condition refuses more when the MISS is the then-arm
    and revives when it is the else-arm. Same edit, both ways round."""
    then_miss = _HOP_SRC
    else_miss = _HOP_SRC.replace('if dup { miss ("dup") }\n  else { acc2 }',
                                 'if dup { acc2 }\n  else { miss ("dup") }')
    wider = ("  let dup = contains(acc, x)", "  let dup = contains(acc, x) or true")
    assert _hop_status(then_miss, *wider) == PO.PRE_HOLDS
    assert _hop_status(else_miss, *wider) == PO.PRE_BROKEN


def test_a_second_downstream_reader_of_the_name_stays_unknown():
    """D3. One hop means ONE consumer. A value that also flows into a
    surviving statement can change that statement too, and this rule did
    not look at it."""
    src = _HOP_SRC.replace("  else { acc2 }", "  else { [acc2, dup] }")
    assert _hop_status(src, "  let dup = contains(acc, x)",
                       "  let dup = contains(acc, x) or true") == PO.PRE_UNKNOWN


def test_a_use_inside_the_miss_arm_is_allowed():
    """The allowance CP17p needs: its miss arm interpolates `str(first)`
    into the message. An arm that only ever misses cannot revive anything,
    whatever value it reads."""
    src = _HOP_SRC.replace('miss ("dup")', 'miss ("dup " + str(dup))')
    assert _hop_status(src, "  let dup = contains(acc, x)",
                       "  let dup = contains(acc, x) or true") == PO.PRE_HOLDS


def test_a_rebinding_between_the_let_and_the_guard_stays_unknown():
    """D4. Whence has no rebinding -- CP17p's own rule is that a duplicate
    `let` in one block is a miss -- so this control is VACUOUS on this
    corpus and is written for the rule, not for the corpus. It is asserted
    against a hand-built block that the guest language would itself refuse."""
    olds = PO._parse_cached(_HOP_SRC)
    body = olds.stmts[0].body
    stmts = list(body.stmts)
    dup_let = stmts[0]
    shadow = type(dup_let)(dup_let.line, "dup", dup_let.expr)
    assert PO._rebinds_name(shadow, "dup")
    news = list(stmts)
    news[0] = type(dup_let)(dup_let.line, "dup",
                            PO.A.BoolLit(dup_let.line, True))
    assert PO._let_hop_relation(stmts, news, body, body, []) is not None
    assert PO._let_hop_relation(stmts[:1] + [shadow] + stmts[1:],
                                news[:1] + [shadow] + news[1:],
                                body, body, []) is None


def test_an_equivalent_condition_is_not_a_refusal_edge():
    """A hop whose two conditions imply each other is not an edge at all,
    and must fall through rather than be scored either way."""
    src = _HOP_SRC
    assert _hop_status(src, "  let dup = contains(acc, x)",
                       "  let dup = contains(acc, x) and contains(acc, x)") \
        in (PO.PRE_UNKNOWN, "identity")


# --- round 432: the normaliser, and the fold it deliberately omits --------

def _n(src):
    """`_norm` applied to the expression of a one-check program."""
    return PO._norm(PO._parse_cached(src).stmts[0].expr)


def test_norm_folds_and_against_false_but_not_or_against_true():
    """The asymmetry is the whole soundness argument. `p and false` is TRUE
    on no input whatever `p` does, so folding it to `false` is safe under
    Whence's three outcomes. `p or true` is NOT folded, because nothing in
    this repo has measured whether `or` short-circuits past a miss on the
    left -- and `true` is true everywhere, so a wrong fold there would
    manufacture proofs."""
    assert isinstance(_n('check "c": f(1) and false'), PO.A.BoolLit)
    assert _n('check "c": f(1) and false').value is False
    keep = _n('check "c": f(1) or true')
    assert isinstance(keep, PO.A.Binary) and keep.op == "or"


def test_norm_distributes_an_if_through_a_comparison_with_a_literal():
    """The rewrite CP17p turns on."""
    got = PO._expr_text(_n('check "c": (if p { 0 } else { 1 }) != 0'))
    assert got == "not p", got


def test_norm_refuses_to_distribute_through_an_else_if_chain():
    """An `else if` leaves an `A.If` in the arm, and `<If> != 0` is not a
    claim this module can make."""
    src = 'check "c": (if p { 0 } else if q { 1 } else { 2 }) != 0'
    assert isinstance(_n(src), PO.A.Binary)
    assert _n(src).op == "!="


def test_norm_does_not_fold_across_literal_types():
    """Whence's `false` is not `0`. Folding `0 == false` either way would be
    a guess about the language rather than a rule about the shape."""
    got = _n('check "c": 0 == false')
    assert isinstance(got, PO.A.Binary) and got.op == "=="


def test_implies_is_unchanged_on_the_shapes_it_already_proved():
    """The normaliser runs at depth 0 of every `_implies` call, so this is
    the guard that it did not perturb round 428's four laws."""
    p = PO._parse_cached('check "c": a and b').stmts[0].expr
    q = PO._parse_cached('check "c": a').stmts[0].expr
    r = PO._parse_cached('check "c": a or z').stmts[0].expr
    assert PO._implies(p, q)
    assert PO._implies(q, r)
    assert not PO._implies(q, p)


# --- round 434: the `kind_stable` decider ---------------------------------
#
# Two kinds of test again, and the split matters more here than anywhere
# else in this file: the analysis MODELS Whence's kinds, so a test that
# asserts the model against itself proves nothing about the language. Every
# claim about what Whence actually does is therefore RUN, through `_checks`.


def test_the_kind_vocabulary_matches_the_interpreter():
    """`polarity.KINDS` is a literal copy of `interp._kind`'s vocabulary,
    kept literal so a 40 ms static analysis does not import an interpreter.
    This is the pin that makes the copy safe."""
    from whence import interp
    names = [n for _, n in interp._KIND_ORDER] + ["value"]
    assert sorted(PO.KINDS) == sorted(names)


def test_kind_tested_by_reads_the_is_convention_and_its_three_exceptions():
    assert PO.kind_tested_by("is_guess") == "guess"
    assert PO.kind_tested_by("is_num") == "num"
    assert PO.kind_tested_by("is_record") == "record"
    # the guest's own spellings
    assert PO.kind_tested_by("is_guess_val") == "guess"
    assert PO.kind_tested_by("is_callable") == "fn"
    assert PO.kind_tested_by("is_closure") == "fn"
    # an `is_*` predicate that is not a KIND test at all
    assert PO.kind_tested_by("is_digit") is None
    assert PO.kind_tested_by("is_op") is None
    assert PO.kind_tested_by("contains") is None


def test_miss_is_not_a_testable_kind():
    """The decider models `miss` only where it is syntactically produced,
    which is safe exactly because no ATOM tests for it -- `missed` belongs
    to `refusal`. Adding an `is_miss` atom would invalidate that argument,
    and this is where it would be noticed."""
    tested = set()
    for name in list(PO.MONOTONE_BUILTINS) + ["is_guess_val", "is_num"]:
        k = PO.kind_tested_by(name)
        if k is not None:
            tested.add(k)
    assert "miss" not in tested


def test_a_guardian_records_the_kind_its_type_test_probes():
    assert one('check "c": is_guess(guess(1, 0.5, "s"))').kinds == ("guess",)
    src = 'fn is_num(v) { true }\ncheck "c": not is_num(1)'
    assert one(src).kinds == ("num",)
    # an `is_*` guest predicate that names no kind
    src = 'fn is_digit(c) { true }\ncheck "c": is_digit("1")'
    assert one(src).kinds == ()


def test_a_guardian_with_no_resolvable_kind_test_is_unknown_not_holds():
    """`kinds` empty means there is no question to ask. The answer must be
    `unknown`; a `holds` here would excuse a violation on an assumption
    nothing established, which is round 426's guard 3."""
    row = PO.kind_precondition(REF_BASE, _fnpin('fn f(x) {\n  x + 2\n}'), ())
    assert row["status"] == PO.PRE_UNKNOWN
    assert row["decided_over"] == (PO.PRE_KIND_STABLE,)


# --- the language facts the analysis rests on, RUN ------------------------

def test_a_comparison_with_a_guess_operand_is_a_guess_in_whence():
    """The rule that makes EP10m decidable, and the one a kind analysis for
    almost any other language would get wrong. Asserted by RUNNING it."""
    got = _checks(
        'check "cmp of two guesses is a guess":\n'
        '  is_guess(guess(1, 0.9, "a") == guess(1, 0.8, "b"))\n'
        'check "cmp of two plain values is a bool":\n'
        '  not is_guess(1 == 2)\n')
    assert got == {"cmp of two guesses is a guess": True,
                   "cmp of two plain values is a bool": True}


def test_and_or_do_not_propagate_a_guess():
    """The one place contagion STOPS: `and`/`or` need a definite bool, so
    `_binary_kinds` answers `{bool}` for them with no contagion. If Whence
    ever propagated there, this goes red before the model does."""
    got = _checks(
        'check "and over a guess is not a guess": missed('
        'guess(true, 0.9, "a") and true)\n')
    assert got == {"and over a guess is not a guess": True}


def test_the_naive_comparison_kind_rule_would_invert_ep10m():
    """DISCLOSURE, and the sharpest single fact this round measured.

    Drop the Guess contagion from comparisons -- the rule any reader would
    write from "a comparison yields a bool" -- and EP10m stops being
    `broken` and becomes `holds`, which promotes this program's one
    remaining violation from `excused` to STRICT and reports the
    conditional law as REFUTED. The decider's answer is carried entirely by
    a v0.15 language decision, not by the analysis being clever."""
    pin = _eval_pin("EP10m")
    base = _eval_src()
    assert PO.kind_precondition(base, pin, ("guess",))["status"] == \
        PO.PRE_BROKEN
    saved = PO._contagion
    try:
        PO._contagion = lambda ks, operands: ks
        PO._KIND_CTX_CACHE.clear()
        naive = PO.kind_precondition(base, pin, ("guess",))
    finally:
        PO._contagion = saved
        PO._KIND_CTX_CACHE.clear()
    assert naive["status"] == PO.PRE_HOLDS, naive["deltas"]


# --- the interprocedural fixpoint -----------------------------------------

def _eval_src():
    with open(SELF_EVAL, encoding="utf-8") as f:
        return f.read()


def _eval_pin(pin_id):
    import json
    with open(os.path.join(REG_416, "eval-pins.json"), encoding="utf-8") as f:
        reg = json.load(f)
    return [p for p in reg["pins"] if p["id"] == pin_id][0]


def test_the_fixpoint_settles_the_mutually_recursive_equality_triangle():
    """`guest_eq` -> `raw_deep_eq` <-> `raw_deep_eq_list` /
    `raw_deep_eq_fields`. A single pass answers TOP; the least fixpoint
    from the empty set answers `{bool, miss}`, and that is exactly the set
    EP10m's decision turns on."""
    ctx = PO._kind_ctx(PO._parse_cached(_eval_src()))
    assert ctx.fn_kinds("guest_eq") == frozenset(("bool", "miss"))
    assert ctx.fn_kinds("raw_deep_eq") == frozenset(("bool", "miss"))
    assert ctx.fn_kinds("raw_deep_eq_list") == frozenset(("bool", "miss"))


def test_a_function_means_the_same_thing_wherever_it_is_called():
    """REGRESSION, round 434. The tree budget and the call budget were one
    counter, so a body was analysed from whatever depth its first caller
    sat at: `raw_deep_eq` answered `{bool, miss}` asked directly and TOP
    reached from inside `apply_binop`, and EP10p's DECISION therefore
    depended on which pin ran first in the process."""
    src = _eval_src()
    PO._KIND_CTX_CACHE.clear()
    ctx = PO._kind_ctx(PO._parse_cached(src))
    direct = ctx.fn_kinds("raw_deep_eq")
    PO._KIND_CTX_CACHE.clear()
    ctx2 = PO._kind_ctx(PO._parse_cached(src))
    deep = PO._kinds_of(PO._parse_cached(
        'fn q(a, b) { guest_eq(a, b) }\n').stmts[0].body,
        {"a": PO.KIND_TOP, "b": PO.KIND_TOP}, ctx2)
    assert deep == frozenset(("bool", "miss"))
    assert ctx2.fn_kinds("raw_deep_eq") == direct


def test_the_kind_decider_is_order_independent():
    """The observable consequence of the bug above, pinned at the level a
    reader cares about: the same four pins, two orders, one answer set."""
    want = {"EP08m": PO.PRE_HOLDS, "EP08p": PO.PRE_HOLDS,
            "EP10m": PO.PRE_BROKEN, "EP10p": PO.PRE_BROKEN}
    base = _eval_src()
    vs = {v.label: v for v in PO.classify_file(SELF_EVAL)}
    for order in (("EP08m", "EP08p", "EP10m", "EP10p"),
                  ("EP10p", "EP10m", "EP08p", "EP08m")):
        PO._KIND_CTX_CACHE.clear()
        PO._PARSE_CACHE.clear()
        got = {}
        for pid in order:
            pin = _eval_pin(pid)
            got[pid] = PO.kind_precondition(
                base, pin, vs[pin["guardian"]].kinds)["status"]
        assert got == want, (order, got)


# --- the corpus, and the result the decider was built for ------------------

def test_ep10m_is_broken_and_names_the_kind_that_moved():
    """Round 420 argued BY HAND that its second law violation was "a broken
    precondition rather than a broken predicate". This is that argument,
    mechanised: the value at the edit site goes from `{bool, guess}` to
    `{bool, miss}`, and `guess` is the kind the guardian tests."""
    row = PO.kind_precondition(_eval_src(), _eval_pin("EP10m"), ("guess",))
    assert row["status"] == PO.PRE_BROKEN
    assert len(row["deltas"]) == 1, row["deltas"]
    d = row["deltas"][0]
    assert "changed (guess)" in d
    assert "{bool,guess}" in d and "{bool,miss}" in d


def test_the_predicate_body_edits_are_kind_stable():
    """EP08m/EP08p replace `is_num`'s BODY. Both sides are boolean, the
    kind under test (`num`) is in neither, and the observed value is not
    touched at all -- so `holds`, and EP08p's confirmation of the law is
    strengthened rather than excused."""
    for pid in ("EP08m", "EP08p"):
        row = PO.kind_precondition(_eval_src(), _eval_pin(pid), ("num",))
        assert row["status"] == PO.PRE_HOLDS, (pid, row["deltas"])


def test_no_violation_in_the_recorded_corpus_is_undecided_any_more():
    """The result. Every `guarded`-although-blind pin this program has ever
    measured now has its OWN precondition decided from the edit, and every
    one of them is `broken` -- so the conditional law is nowhere refuted,
    and nowhere excused by an undecided assumption either."""
    import json
    with open(os.path.join(REG_416, "eval-pins.json"), encoding="utf-8") as f:
        reg = json.load(f)
    with open(os.path.join(REG_416, "run.json"), encoding="utf-8") as f:
        run = json.load(f)
    vs = PO.classify_file(SELF_EVAL)
    pre = PO.precondition_map(reg["pins"], _eval_src(), vs)
    out = PO.check_law(reg["pins"], run["results"], vs, pre)
    assert len(out["violations"]) == 2
    assert out["strict_violations"] == []
    assert [r["id"] for r in out["undecided"]] == []
    assert sorted(r["id"] for r in out["excused"]) == ["EP10m", "EP11p"]


def test_the_host_registry_is_untouched_by_the_third_decider():
    """The control. No pin in round 422's registry rests on `kind_stable`,
    so adding its decider must move nothing there. A decider that changes a
    registry it does not apply to is routing wrongly."""
    import json
    with open(os.path.join(REG_422, "host-pins-plus.json"),
              encoding="utf-8") as f:
        reg = json.load(f)
    with open(SELF_HOST, encoding="utf-8") as f:
        src = f.read()
    vs = PO.classify_file(SELF_HOST)
    pre = PO.precondition_map(reg["pins"], src, vs)
    counts = {}
    for row in pre.values():
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    # ROUND 438 split the old `PRE_UNKNOWN: 7` into 4 unknown + 3
    # undecidable. That is the `append_only` decider naming a permanent
    # limit, NOT the `kind_stable` decider reaching pins it does not apply
    # to -- which is what this control exists to catch, and which would show
    # up as a `holds` or `broken` moving. Those two are unchanged.
    # ROUND 440 moved exactly one more row: CP03p `unknown` ->
    # `broken_on_branch`. `holds`, `broken` and `inapplicable` are again
    # unchanged, which is what this control is for.
    assert counts == {PO.PRE_BROKEN: 2, PO.PRE_HOLDS: 9,
                      PO.PRE_INAPPLICABLE: 5, PO.PRE_UNKNOWN: 3,
                      PO.PRE_UNDECIDABLE: 3, PO.PRE_BROKEN_ON_BRANCH: 1}
    assert not any(PO.PRE_KIND_STABLE in (v.pre or ()) for v in vs)


def test_the_two_host_registries_do_not_silently_overwrite_each_other():
    """Round 434. Two of the three campaigns are registries over the SAME
    guest file with the SAME pin ids, so a `(guest, id)` dedup key let the
    last one silently replace the first. Measured on the recorded corpus the
    collision is real (CP03p: not-guarded in `host-pins-plus`, guarded in
    its repointed twin) and currently harmless (its precondition is the
    same on both sides, so it lands in none of the four cells). This
    pins BOTH halves: the collision exists, and the table is unchanged by
    keying on the guardian as well.

    ROUND 440 read that collision as the finding rather than the nuisance.
    One edit, one guest program, two guardians, opposite measured verdicts
    — so `append_only` is a property of the (edit, guardian) PAIR while
    every decider in the module is keyed on the PIN. The status is now
    `broken_on_branch` on both sides and the table is STILL (10, 0, 0, 3),
    which is the whole point: the decision is about inputs, the cells are
    about observers, and a status that moved this table would be claiming
    something about an observer it never read. Round 434's item 4 and round
    438's item 4 both asked for this table BEFORE and AFTER a CP03p
    decision; both values are here."""
    collisions = []
    tab = _law_table(True, _campaigns(), collisions)
    assert tab == (10, 0, 0, 3)
    ids = sorted(c[1] for c in collisions)
    assert ids == ["CP03p"], collisions
    was, now = [c for c in collisions if c[1] == "CP03p"][0][2:]
    assert was == (PO.PRE_BROKEN_ON_BRANCH, False)
    assert now == (PO.PRE_BROKEN_ON_BRANCH, True)


def test_a_repointed_registry_can_never_produce_a_confirmation():
    """Round 434, closing round 426 §7 / round 428 item 7 — "the repointed
    registry needs taking seriously or retiring".

    The answer is structural rather than a matter of degree. `repoint`
    re-points ONLY pins that did not come back `guarded`, and only to a
    check that DID go red for that pin's own edit. So on the re-run every
    repointed pin's guardian is red, i.e. `guarded` -- 20 of 20 that ran,
    score 1.0, which round 426 already noted is guaranteed by construction.
    A law CONFIRMATION is `blind AND NOT guarded`. The not-guarded column of
    a repointed registry is therefore empty by construction, and "0
    confirmations against 5 violations" is not a weak result: it is the only
    result that registry can produce.

    It stays in `_campaigns()` anyway, because a campaign that can only ever
    hurt the p-value is the conservative one to keep. What it may NOT do is
    silently help, which is what the test above is for.
    """
    import json
    guest, pinf, runf = _campaigns()[2]
    with open(pinf, encoding="utf-8") as f:
        reg = json.load(f)
    with open(runf, encoding="utf-8") as f:
        run = json.load(f)
    verdicts = {r["id"]: r["verdict"] for r in run["results"]}
    repointed = [p["id"] for p in reg["pins"]
                 if p.get("repointed_from") or p.get("guardian_was")]
    assert len(repointed) == 20, repointed
    ran = [i for i in repointed if verdicts.get(i) not in (None, "unreachable")]
    assert ran and all(verdicts[i] == "guarded" for i in ran), \
        {i: verdicts.get(i) for i in repointed}
    with open(guest, encoding="utf-8") as f:
        src = f.read()
    vs = PO.classify_file(guest)
    out = PO.check_law(reg["pins"], run["results"], vs,
                       PO.precondition_map(reg["pins"], src, vs))
    assert out["confirmations"] == []
    # ...and it contributes nothing at all to the contingency table
    assert _law_table(True, _campaigns()[:2]) == _law_table(True, _campaigns())


def test_repoint_emit_carries_the_negative_control_through():
    """Round 434. `repoint` only ever names pins that did NOT come back
    `guarded`, and a negative control is never guarded and is never named --
    so the emitted registry used to lose it. `state/whence/round-420/
    run-repointed.json` records `controls: []`: a campaign whose `inert` and
    `unreachable` verdicts have nothing to distinguish them from a runner
    that never applied an edit, which is exactly what round 408 §6.2 wrote
    the control rule for."""
    import json
    import tempfile
    with open(os.path.join(REG_416, "eval-pins.json"), encoding="utf-8") as f:
        reg = json.load(f)
    controls = [p["id"] for p in reg["pins"] if p.get("control_expect")]
    assert controls, "fixture has no control to carry"
    with tempfile.NamedTemporaryFile("w", suffix=".json",
                                     delete=False) as tmp:
        out = tmp.name
    try:
        rc = PO._cmd_repoint([os.path.join(REG_416, "eval-pins.json"),
                              os.path.join(REG_416, "run.json"),
                              "--emit", out])
        assert rc == 0
        with open(out, encoding="utf-8") as f:
            emitted = json.load(f)
    finally:
        os.unlink(out)
    ids = [p["id"] for p in emitted["pins"]]
    for c in controls:
        assert c in ids, (c, ids)
    # ...and a carried control is NOT repointed
    for p in emitted["pins"]:
        if p.get("control_expect"):
            assert "guardian_was" not in p, p["id"]


# --- ROUND 440: `append_only` is a property of the (edit, guardian) PAIR ---
#
# Round 438 left CP03p as the one open `append_only` residual and set the
# procedure: "write the counterexample FIRST and only widen if none exists."
# The counterexample was already in the repository, in the one form that
# leaves nothing to construct -- ONE edit, ONE guest program, TWO guardians
# of it, opposite measured verdicts. The widening rule exists too, and what
# it decides is the EDIT ("this rewrites the observed text in place on the
# arm its own guard selects"), which is not the question `check_law` and
# `audit_registry` ask ("is THIS guardian blind to it"). Hence a status of
# its own that is never promoted to either side.

REG_440 = os.path.join(_C.AGI_ROOT, "state", "whence", "round-440")


def _cp03p(registry):
    import json
    with open(os.path.join(REG_422, registry), encoding="utf-8") as f:
        return [p for p in json.load(f)["pins"] if p["id"] == "CP03p"][0]


def _verdict_of(runfile, pid="CP03p"):
    import json
    with open(os.path.join(REG_422, runfile), encoding="utf-8") as f:
        return [r for r in json.load(f)["results"] if r["id"] == pid][0]


def test_one_edit_two_guardians_and_opposite_measured_verdicts():
    """The counterexample round 438 asked for, read off the recorded corpus.

    `host-pins-plus.json` and its repointed twin hold CP03p with a
    BYTE-IDENTICAL edit and different `guardian` labels. Both guardians are
    checks in the SAME guest file. One measured `shadowed` (it stayed green;
    the edit was observable elsewhere) and the other `guarded`. So no rule
    over the delta can decide "is the guardian blind": the delta is the same
    in both rows.

    The `shadowed` row also names its own replacement -- `co_red` holds
    exactly the label the repointed registry uses -- which is why the pair
    exists at all and why no new program had to be written.
    """
    a, b = _cp03p("host-pins-plus.json"), _cp03p("host-pins-plus-repointed.json")
    assert a["becomes"] == b["becomes"]
    assert a["edit"] == b["edit"] == "fn_replace"
    assert a["guardian"] != b["guardian"]
    assert b["repointed_from"] == a["guardian"]
    ra, rb = _verdict_of("run-plus.json"), _verdict_of("run-repointed.json")
    assert (ra["verdict"], rb["verdict"]) == ("shadowed", "guarded")
    assert ra["co_red"] == [b["guardian"]]


def test_cp03p_is_decided_from_the_edit_and_the_decision_is_broken_on_branch():
    """The widening rule, on the pin it was written for.

    `_walk_delta` can only call this pair `structural` -- a Block against an
    If. The guarded arm is where the decision is: the else arm keeps `c`
    verbatim, the guard is `c == "'"`, so on the arm the guard selects the
    OLD text is the literal `'` and the new text is `\\'`. That is an INFIX
    rewrite, decided with no run and no verdict.
    """
    import json
    with open(SELF_HOST, encoding="utf-8") as f:
        src = f.read()
    r = PO.edit_precondition(src, _cp03p("host-pins-plus.json"))
    assert r["kinds"] == [PO.DELTA_STRUCTURAL]
    assert r["status"] == PO.PRE_BROKEN_ON_BRANCH
    arm = [d for d in r["deltas"] if "guarded arm" in d]
    assert len(arm) == 1, r["deltas"]
    assert "refined" in arm[0] and "[%s]" % PO.DELTA_INFIX in arm[0]
    # ...and the SAME edit against the SAME guest source gives the SAME
    # answer for the repointed pin, whose guardian measured the opposite.
    r2 = PO.edit_precondition(src, _cp03p("host-pins-plus-repointed.json"))
    assert r2["status"] == r["status"] == PO.PRE_BROKEN_ON_BRANCH


def test_widening_cp03p_to_holds_or_broken_would_publish_a_false_sentence():
    """Why the answer is a NEW status and not one of round 438's two.

    Both alternatives are wrong loudly rather than subtly, and this test
    runs the counterfactual rather than arguing it. Recorded in
    `state/whence/round-440/counterfactual.txt`.

      `holds`  -> the repointed registry reports `strict_violation` for
                  CP03p. That is the path round 438's next-step 3 says has
                  never fired on real data and whose firing "is the headline
                  of whatever round sees it" -- round 420's law refuted. It
                  would be announced against a guardian whose observed text
                  this edit demonstrably rewrote (`"a'b"` -> `"a\\'b"`).
      `broken` -> BOTH registries report `precondition_broken`, whose
                  printed reading is "the guardian is not blind to THIS edit
                  and the flag is a false positive". On `host-pins-plus.json`
                  the guardian measured `shadowed`, i.e. blind to this edit.
    """
    import json
    with open(SELF_HOST, encoding="utf-8") as f:
        src = f.read()
    vs = PO.classify_file(SELF_HOST)
    got = {}
    for regname, runname in (("host-pins-plus-repointed.json", "run-repointed.json"),
                             ("host-pins-plus.json", "run-plus.json")):
        with open(os.path.join(REG_422, regname), encoding="utf-8") as f:
            pins = json.load(f)["pins"]
        with open(os.path.join(REG_422, runname), encoding="utf-8") as f:
            res = json.load(f)["results"]
        pre = PO.precondition_map(pins, src, vs)
        for forced in (PO.PRE_BROKEN_ON_BRANCH, PO.PRE_HOLDS, PO.PRE_BROKEN):
            m = {k: dict(v) for k, v in pre.items()}
            m["CP03p"]["status"] = forced
            rows = {r["id"]: r for r in PO.audit_registry(pins, vs, res, m)}
            law = PO.check_law(pins, res, vs, m)
            got[(regname, forced)] = (
                rows["CP03p"]["status"],
                "CP03p" in [r["id"] for r in law["strict_violations"]],
                "CP03p" in [r["id"] for r in law["excused"]])
    rep, plus = "host-pins-plus-repointed.json", "host-pins-plus.json"
    assert got[(rep, PO.PRE_HOLDS)] == ("strict_violation", True, False)
    assert got[(rep, PO.PRE_BROKEN)] == ("precondition_broken", False, True)
    assert got[(plus, PO.PRE_BROKEN)][0] == "precondition_broken"
    # ...and the status actually shipped claims neither, on either registry.
    assert got[(rep, PO.PRE_BROKEN_ON_BRANCH)] == ("undecided", False, False)
    assert got[(plus, PO.PRE_BROKEN_ON_BRANCH)][0] == "undecided"


def test_broken_on_branch_is_never_promoted_downstream():
    """Same guarantee round 438 gave `undecidable`, for the same reason and
    with one difference worth naming: this status arrives WITH a decision.
    It is still refused by both consumers, because the decision is about
    inputs and both consumers ask about observers."""
    v = _v("blindy", ("+",), (PO.PRE_APPEND_ONLY,))
    pins = [{"id": "B", "guest_file": "x.lang", "dir": "+",
             "guardian": "blindy"}]
    results = [{"id": "B", "guardian": "blindy", "verdict": "guarded"}]
    pre = {"B": {"status": PO.PRE_BROKEN_ON_BRANCH,
                 "decided_over": (PO.PRE_APPEND_ONLY,)}}
    law = PO.check_law(pins, results, [v], pre)
    assert [r["id"] for r in law["violations"]] == ["B"]
    assert law["excused"] == [] and law["strict_violations"] == []
    assert [r["id"] for r in law["undecided"]] == ["B"]
    rows = PO.audit_registry(pins, [v], results, pre)
    assert [r["status"] for r in rows] == ["undecided"]


def test_a_conjunction_never_promotes_broken_on_branch_either():
    """`routed_precondition` combines per-precondition rows. A
    `broken_on_branch` beside a `holds` stays `broken_on_branch`; beside
    anything merely un-ruled it drops to `unknown`, by round 438's rule."""
    assert PO._combine_precondition([PO.PRE_BROKEN_ON_BRANCH, PO.PRE_HOLDS]) \
        == PO.PRE_BROKEN_ON_BRANCH
    assert PO._combine_precondition([PO.PRE_BROKEN_ON_BRANCH, PO.PRE_UNKNOWN]) \
        == PO.PRE_UNKNOWN
    assert PO._combine_precondition([PO.PRE_BROKEN_ON_BRANCH,
                                 PO.PRE_UNDECIDABLE]) == PO.PRE_UNKNOWN
    # a real `broken` still dominates: an unconditional rewrite is not made
    # conditional by a conditional one sitting next to it.
    assert PO._combine_precondition([PO.PRE_BROKEN_ON_BRANCH, PO.PRE_BROKEN]) \
        == PO.PRE_BROKEN


def test_a_guarded_arm_that_appends_is_a_real_widening_of_holds():
    """The positive half of the rule, with no instance in the corpus.

    `X -> if C { X + "!" } else { X }` only ever grows the observed text at
    its end, on BOTH arms, so it holds for every observer -- which is what
    `holds` means. Pinned synthetically on purpose, as round 434's
    `no_decider` branch and round 438's `strict_violation` are: the branch
    exists because the rule is stated over a shape, not over the corpus.
    """
    base = 'fn f(c) { c }\ncheck "g": contains(f("x"), "x")\n'
    r = _pre(base, 'fn f(c) { if c == "q" { c + "!" } else { c } }', 'fn f(c)')
    assert r["status"] == PO.PRE_HOLDS
    assert "only ever grow the text at its end" in r["why"]


def test_the_refinement_folds_only_an_equality_against_a_literal():
    """`_eq_literal` is the one substitution this module makes, and it is
    exact. A guard that is not an equality against a literal leaves the arms
    compared as written, which for two unrelated expressions is
    `structural` -- so the row stays `unknown` rather than being guessed
    into a decision."""
    base = 'fn f(c) { c }\ncheck "g": contains(f("x"), "x")\n'
    r = _pre(base, 'fn f(c) { if c > "q" { g(c) } else { c } }', 'fn f(c)')
    assert r["status"] == PO.PRE_UNKNOWN
    # The guard KEEPS the old expression on its TRUE arm, so the new text is
    # selected by `not C`, and an equality that HOLDS says nothing about the
    # inputs where it FAILS. That arm is compared as written -- which for a
    # bare name against a literal is `structural`, i.e. `unknown`. This is a
    # refusal to guess, not a gap: `c` is every character but `"q"` there.
    r2 = _pre(base, 'fn f(c) { if c == "q" { c } else { "Q" } }', 'fn f(c)')
    assert r2["status"] == PO.PRE_UNKNOWN
    # ...and the unrefined comparison still decides the arm whenever the two
    # sides are relatable WITHOUT knowing what the name holds. Both
    # directions, on the same negated shape:
    r3 = _pre(base, 'fn f(c) { if c == "q" { c } else { c + "!" } }',
              'fn f(c)')
    assert r3["status"] == PO.PRE_HOLDS
    r4 = _pre(base, 'fn f(c) { if c == "q" { c } else { "x" + c } }',
              'fn f(c)')
    assert r4["status"] == PO.PRE_BROKEN_ON_BRANCH
    arm = [d for d in r4["deltas"] if "guarded arm" in d]
    assert len(arm) == 1 and "refined" not in arm[0], arm


def test_a_guard_whose_arms_are_both_new_is_not_a_guarded_substitution():
    """The shape requires ONE arm kept verbatim. Without it the edit is a
    rewrite, not a guard -- the same rule `_guard_relation` states for
    `refusal` ("an `if` that misses on one side and returns something merely
    similar on the other is not a guard, it is a rewrite")."""
    base = 'fn f(c) { c }\ncheck "g": contains(f("x"), "x")\n'
    r = _pre(base, 'fn f(c) { if c == "q" { "Q" } else { "Z" } }', 'fn f(c)')
    assert PO._guarded_substitution is not None
    assert r["status"] == PO.PRE_UNKNOWN
    assert not [d for d in r["deltas"] if "guarded arm" in d]


def test_every_repointed_pin_still_carries_its_predecessors_rationale():
    """Round 440. `repoint` moves the `guardian` label and nothing else, and
    `why` is prose ABOUT the guardian — so a repoint leaves every pin
    arguing about a check it no longer names.

    Measured: 20 of 20 repointed pins had a `why` byte-identical to their
    pre-repoint twin's, and CP03p's was measurably FALSE of its own
    guardian. Its second sentence read "The guardian's probe string has no
    apostrophe in it at all, so it cannot see this however broken the
    escaper is"; the guardian it names probes `"a'b"`, and the pin measures
    `guarded` there. That sentence is now corrected in place, which is why
    the count is 19 and not 20. The other 19 are not asserted correct — they
    are asserted UNRE-AUTHORED, which is the fact this test exists to keep
    visible.

    `test_the_repointed_registry_changes_labels_and_nothing_else` in
    `test_checkpin.py` enumerates the fields a repoint may not move and
    `why` is not among them, so this correction does not weaken it.
    """
    import json
    with open(os.path.join(REG_422, "host-pins-plus.json"), encoding="utf-8") as f:
        a = {p["id"]: p for p in json.load(f)["pins"]}
    with open(os.path.join(REG_422, "host-pins-plus-repointed.json"),
              encoding="utf-8") as f:
        b = {p["id"]: p for p in json.load(f)["pins"]}
    repointed = [i for i in b if "repointed_from" in b[i]]
    assert len(repointed) == 20
    carried = sorted(i for i in repointed if a[i]["why"] == b[i]["why"])
    assert len(carried) == 19, carried
    assert "CP03p" not in carried
    assert "no apostrophe in it at all" in a["CP03p"]["why"]
    # The corrected field QUOTES the false sentence rather than deleting it,
    # so the test cannot be "the string is gone" -- it is "the string is no
    # longer asserted". Both halves are pinned.
    b_why = b["CP03p"]["why"]
    assert "ROUND 440 corrected the second half of this field" in b_why
    assert "false of this label" in b_why
    assert a["CP03p"]["why"] != b_why


def test_the_repointed_registrys_criterion_is_restated_and_still_not_met():
    """Round 438's next-step 1, discharged, and kept from rotting.

    The registry's `_` field now names a criterion in two parts and quotes
    what it measures TODAY. Both quoted measurements are re-derived here, so
    the header cannot drift from the instrument the way round 435 found its
    `nineteen` had.

    Part A is `0 MISPOINTED and 0 undecided and 0 strict-violation`. It is
    NOT met, and the assertion below says so positively rather than pinning
    a passing number -- a criterion whose test goes green the moment the
    instrument stops answering is the failure mode round 438 found in the
    criterion this one replaces.
    """
    import json
    with open(os.path.join(REG_422, "host-pins-plus-repointed.json"),
              encoding="utf-8") as f:
        reg = json.load(f)
    hdr = reg["_"]
    assert "THE CRITERION FROM HERE" in hdr
    with open(SELF_HOST, encoding="utf-8") as f:
        src = f.read()
    vs = PO.classify_file(SELF_HOST)
    pre = PO.precondition_map(reg["pins"], src, vs)
    rows = PO.audit_registry(reg["pins"], vs, None, pre)
    n = {s: sum(1 for r in rows if r["status"] == s)
         for s in PO.AUDIT_BLIND_STATUSES}
    assert (n["mispointed"], n["precondition_broken"], n["undecided"],
            n["strict_violation"]) == (0, 1, 4, 0)
    assert ("`22 directional pin(s), 0 MISPOINTED, 0 unlocatable, 1"
            " precondition-broken, 4 undecided, 0 strict-violation`") in hdr
    # ...and part (2) of why the OLD criterion was the wrong quantity: the
    # score the repoint moved, re-derived from the two campaigns.
    runs = {}
    for name in ("run-plus.json", "run-repointed.json"):
        with open(os.path.join(REG_422, name), encoding="utf-8") as f:
            runs[name] = json.load(f)
    assert (runs["run-plus.json"]["guarded"],
            runs["run-plus.json"]["n_pins"]) == (1, 20)
    assert (runs["run-repointed.json"]["guarded"],
            runs["run-repointed.json"]["n_pins"]) == (20, 20)
    assert "1/20 = 5%" in hdr and "20/20 = 100%" in hdr
    # ROUND 498: the directional COUNT and the `undecided > 0` clause moved
    # down here from above the two `runs[...]` tuples. Both move when a pin
    # is added to the registry; the two tuples above are the campaign scores
    # the repoint moved, and they are what this node is named for.
    assert len([r for r in rows if r["dir"] in (PO.PLUS, PO.MINUS)]) == 22
    # the criterion, evaluated: NOT met, on the `undecided` clause alone
    assert n["undecided"] > 0
