"""Round 383 (SWE-loop D) — the exemption map for the whole oracle suite.

Round 377's next-step item 3: apply `zero-rate-needs-a-distance` to the
oracles round 377 did not audit. Eight sites, four oracles.

What is pinned here, on round 377's own rule, is STRUCTURE and DISTANCE, never
this round's measured rates. Three things in particular:

  * every site's anchor still exists in `oracles.py` at the multiplicity the
    registry claims — the registry's only defence against measuring a branch
    that has moved;
  * `FRAME_SLACK` still exceeds the largest excess a CORRECT program can
    produce, computed live from `Interpreter.FAST_MAX_DEPTH` rather than
    restated — this round measured `excess == FAST_MAX_DEPTH - 2` exactly, so
    raising that constant past ~142 turns `oracle_frames` into a false-positive
    generator on correct code, and nothing in the tree links the two files;
  * `render`'s `names[:6]` cap really does skip pairs, counted through the
    oracle's own entry point rather than read off the loop bound.

A rate would go stale. Each of these goes red at the moment the thing it
describes actually changes.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from harness.swe import exemptmap as M             # noqa: E402
from harness.swe import oracles as O               # noqa: E402
from harness.swe.fuzz import ProgramGen, WHENCE_ROOT   # noqa: E402
from harness.swe.killers import load_whence        # noqa: E402


@pytest.fixture(scope="module")
def pkg():
    p = dict(load_whence(WHENCE_ROOT, "t383map"))
    p.setdefault("root", WHENCE_ROOT)
    return p


# ------------------------------------------------------- the registry itself --

def test_every_site_anchor_still_exists_at_the_claimed_multiplicity():
    """The registry names a literal line of `oracles.py` per site.

    This is the one assertion that has to hold for every OTHER number in this
    module to mean anything: if an anchor has drifted, `measure` is still
    computing a rate, but for a branch that is no longer there.
    """
    assert M.verify_sites() == len(M.SITES) == 8


def test_a_drifted_anchor_raises_instead_of_measuring_the_wrong_line(tmp_path):
    """The failure mode `patch_lib_source` was written against: a silent
    no-op that reports numbers under the wrong label."""
    p = tmp_path / "oracles.py"
    p.write_text("# nothing in here matches any anchor\n", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        M.verify_sites(str(p))
    msg = str(e.value)
    assert "stale" in msg
    for s in M.SITES:
        assert s.id in msg


def test_the_t_all_anchor_is_two_lines_because_the_one_line_form_is_shared():
    """`if not a["vals"] and not whole:` appears in BOTH the tail and the
    param oracle, and the 4-space form is a substring of the 8-space one, so
    a naive anchor counts 2. The registry's first run caught it; this keeps
    the reason attached to the code.
    """
    with open(M._ORACLES_PY, encoding="utf-8") as f:
        text = f.read()
    assert text.count('if not a["vals"] and not whole:') == 2
    assert text.count(M.site("T-ALL").anchor) == 1


def test_every_site_declares_a_metric_and_a_polarity():
    for s in M.SITES:
        assert s.metric in ("distance", "surface", "rate"), s.id
        assert s.polarity in ("suppress", "tolerate"), s.id
        # a distance site must name the constant it is a distance FROM
        if s.metric == "distance":
            assert isinstance(s.threshold, int), s.id


# -------------------------------------------------- F-SLACK: the real band --

def test_a_correct_programs_frame_excess_is_bounded_by_FAST_MAX_DEPTH(pkg):
    """The measured law, on this checkout: a call-free `1 + 1 + ...` chain's
    host-frame excess is exactly `FAST_MAX_DEPTH - 2`, whatever the chain's
    length. `_compile_fast` refuses a subtree taller than `FAST_MAX_DEPTH`
    (`interp.py:1271`), so the transient cannot grow past it.
    """
    fmd = pkg["Interpreter"].FAST_MAX_DEPTH
    for terms in (100, 200, 400):
        excess, _at = M.chain_excess(pkg, terms)
        assert excess == fmd - 2, (terms, excess, fmd)


def test_FRAME_SLACK_still_has_headroom_over_that_bound(pkg):
    """`FRAME_SLACK` (oracles.py) and `FAST_MAX_DEPTH` (whence/interp.py) are
    in different trees with nothing linking them, and the oracle is only
    sound while the first exceeds the second.

    Round 110 sized the slack to sit between a legitimate transient and
    round 108's undercharge bug (which reaches ~161). This round measured the
    legitimate side exactly and found 42 frames of headroom. The assertion is
    the RELATION, not either number: raise `FAST_MAX_DEPTH` past ~142 and
    `oracle_frames` starts reporting mismatches on correct programs.
    """
    fmd = pkg["Interpreter"].FAST_MAX_DEPTH
    # (round 389) The relation is now COMPUTED, not asserted: `frame_slack`
    # reads the same `FAST_MAX_DEPTH` this test reads. The assertion below
    # therefore checks the DERIVATION rather than the literal, and the
    # literal is checked separately for the packages that still use it.
    assert O.frame_slack(pkg) > fmd, (
        "derived slack=%d no longer exceeds FAST_MAX_DEPTH=%d; a correct "
        "call-free chain now produces excess %d and oracle_frames will "
        "report a mismatch on it" % (O.frame_slack(pkg), fmd, fmd - 2))
    assert O.frame_slack(pkg) == fmd + O.FRAME_SLACK_MARGIN
    assert O.frame_slack(None) == O.FRAME_SLACK


def test_a_LITERAL_slack_still_fires_on_correct_code_when_FAST_MAX_DEPTH_rises(pkg):
    """Round 383's tripwire, preserved as the reason for round 389's fix.

    This is what `oracle_frames` DID on every round from 110 to 388: the
    threshold was the module literal, so raising `FAST_MAX_DEPTH` past
    `FRAME_SLACK + 2` made a CORRECT call-free chain report a mismatch. The
    literal path still exists (`slack=` is an explicit argument, and older
    packages with no fast path get `FRAME_SLACK`), so the failure mode is
    still reachable and is pinned here rather than deleted.
    """
    I = pkg["Interpreter"]
    orig = I.FAST_MAX_DEPTH
    src = M.chain_program(400)
    try:
        assert O.run_oracle("frames", pkg, src, timeout_s=30.0,
                            slack=O.FRAME_SLACK).kind == "ok"
        I.FAST_MAX_DEPTH = O.FRAME_SLACK + 10
        o = O.run_oracle("frames", pkg, src, timeout_s=30.0,
                         slack=O.FRAME_SLACK)
        assert o.kind == "mismatch", o.detail
        assert "excess %d > slack %d" % (I.FAST_MAX_DEPTH - 2, O.FRAME_SLACK) \
            in o.detail
    finally:
        I.FAST_MAX_DEPTH = orig
    assert O.run_oracle("frames", pkg, src, timeout_s=30.0,
                        slack=O.FRAME_SLACK).kind == "ok"


def test_the_DERIVED_slack_absorbs_a_raised_FAST_MAX_DEPTH(pkg):
    """(round 389) The same edit, with the threshold derived: no verdict
    changes, because the floor and the threshold move together.

    This is the whole content of round 383's item 3. What it buys is not a
    louder alarm — it is the ABSENCE of one on correct code.
    """
    I = pkg["Interpreter"]
    orig = I.FAST_MAX_DEPTH
    src = M.chain_program(400)
    try:
        assert O.run_oracle("frames", pkg, src, timeout_s=30.0).kind == "ok"
        I.FAST_MAX_DEPTH = O.FRAME_SLACK + 10          # 150, round 383's break
        o = O.run_oracle("frames", pkg, src, timeout_s=30.0)
        assert o.kind == "ok", o.detail
        assert "slack %d = FAST_MAX_DEPTH %d + %d" % (
            O.frame_slack(pkg), I.FAST_MAX_DEPTH, O.FRAME_SLACK_MARGIN) \
            in o.detail
    finally:
        I.FAST_MAX_DEPTH = orig
    assert O.run_oracle("frames", pkg, src, timeout_s=30.0).kind == "ok"


def test_the_parser_caps_nested_literals_below_the_slack_too(pkg):
    """The second ceiling holding the legitimate side down. `MAX_NESTING`
    lives in the language, not the oracle, and is the reason the nested-list
    shape round 110's comment names cannot approach 140 either."""
    P = __import__(pkg["name"] + ".parser", fromlist=["MAX_NESTING"])
    deep = "let z = " + "[" * P.MAX_NESTING + "1" + "]" * P.MAX_NESTING + "\n"
    with pytest.raises((pkg["ParseError"], pkg["LexError"])):
        O._parse(pkg, deep)
    ok = P.MAX_NESTING - 1
    src = "let z = " + "[" * ok + "1" + "]" * ok + "\nprint(str(z))\n"
    excess, _at = O.frame_excess(pkg, O._parse(pkg, src))[:2]
    assert 0 < excess < O.frame_slack(pkg)


# ------------------------------------------------------ R-CAP: the pair cap --

def test_render_skips_pairs_beyond_the_cap_counted_live(pkg):
    """Counted through `run_oracle("render", ...)`, not read off the loop
    bound.

    Round 383 wrote this as a tripwire — "a future round that lifts the cap
    makes this test red, which is the intended signal" — and pinned the
    literal 15/30 beside the relation. Round 389 lifted the cap from 6 to 24
    after measuring that full coverage costs 0.98x, and the test went red on
    the literals while the relation held. The literals are gone; the
    relation, derived from the site's own declared threshold, is what is
    asserted.
    """
    cap = M.site("R-CAP").threshold
    k = cap + 4                          # above the cap whatever the cap is
    w = M.paircap_witness(pkg, k=k)
    assert w["kind"] == "ok"
    assert w["pairs_total"] == k * (k - 1) // 2
    assert w["pairs_checked"] == cap * (cap - 1) // 2
    assert w["pairs_skipped"] == w["pairs_total"] - w["pairs_checked"] > 0


def test_the_pair_cap_does_not_bind_below_seven_bindings(pkg):
    """The negative case: at 6 bindings the oracle checks every pair, so the
    cap costs nothing and the site must not report itself as fired."""
    src = M.paircap_program(6)
    row = M.measure(pkg, src)
    st = row["sites"]["R-CAP"]
    assert st["fired"] is False
    assert st["pairs_skipped"] == 0
    assert st["surface"] == 1.0
    w = M.paircap_witness(pkg, k=6)
    assert w["pairs_checked"] == w["pairs_total"] == 15


# ---------------------------------------------- T-SPACE: censoring is real --

def test_a_fired_T_SPACE_demand_is_marked_censored(pkg):
    """`peak == max_depth` means "at least max_depth", so a distance computed
    from it is 100 % by construction — an artefact, not a measurement. The
    row has to say so, or the report lies with a true number."""
    src = M.deep_program(600)
    row = M.measure(pkg, src, max_depth=500)
    st = row["sites"]["T-SPACE"]
    if st["fired"]:
        assert st["censored"] is True
        assert st["surface"] == 0.0
    else:
        assert st["censored"] is False


def test_the_depth_ladder_uncensors_a_bounded_demand(pkg):
    """Raising the ceiling until the run stops hitting it turns the floor
    into a bracket. A program needing ~600 must bracket above 500."""
    res = M.depth_demand(pkg, M.deep_program(600), rungs=(500, 1000, 2000))
    assert res["note"] in ("bounded", "T-NONE"), res
    if res["note"] == "bounded":
        assert res["hi"] > 500
        assert res["peak"] >= 500


def test_a_shallow_program_needs_no_ladder(pkg):
    res = M.depth_demand(pkg, M.deep_program(10), rungs=(500, 1000))
    assert res["demand"] in ("(0, 500]", "no_tail_calls"), res


# ------------------------------------- P-EXEMPT: the corpus is one bind away --

def test_a_twice_bound_spec_name_fires_the_param_exemption(pkg):
    """P-EXEMPT's threshold clause, exhibited. The distance the sweep reports
    is a binding multiplicity; this is what multiplicity 2 looks like."""
    src = M.spec_shadow_program()
    row = M.measure(pkg, src)
    # NOT pytest.skip. A witness the grammar rejects is a zero that renders
    # exactly like a pass — the failure this round's own skill names, and the
    # one it committed: all three of these witnesses were first written in
    # syntax Whence does not have (`@{a: "int"}`, `fn g(y: "int")`) and
    # skipped silently for a full test run.
    assert not row["parse_error"], (
        "witness does not parse (%s); a skipped witness is a false green"
        % row["parse_error"])
    st = row["sites"]["P-EXEMPT"]
    assert st["fired"] is True
    assert st["demand"] >= 2
    assert "bound" in st["reason"]
    assert st["surface"] == 0.0
    o = O.run_oracle("param_erasure", pkg, src, timeout_s=30.0)
    assert o.kind == "ok" and "exempt" in o.detail


def test_binding_typed_fires_the_other_clause(pkg):
    src = M.typed_bound_program()
    row = M.measure(pkg, src)
    # NOT pytest.skip. A witness the grammar rejects is a zero that renders
    # exactly like a pass — the failure this round's own skill names, and the
    # one it committed: all three of these witnesses were first written in
    # syntax Whence does not have (`@{a: "int"}`, `fn g(y: "int")`) and
    # skipped silently for a full test run.
    assert not row["parse_error"], (
        "witness does not parse (%s); a skipped witness is a false green"
        % row["parse_error"])
    st = row["sites"]["P-EXEMPT"]
    assert st["binds_typed"] >= 1
    assert st["fired"] is True
    assert O.GUARD_BUILTIN in st["reason"]


def test_an_unexempt_contract_program_reports_distance_one(pkg):
    """The ordinary case: one spec name, bound once. The site does not fire
    and the corpus sits exactly one extra binding from the boundary — which
    is the number the report calls `one_step_away`."""
    src = ("shape S = @{a: num}\nfn f(x: S) { x }\n"
           "let r = f(@{a: 1})\nprint(str(r))\n")
    row = M.measure(pkg, src)
    # NOT pytest.skip. A witness the grammar rejects is a zero that renders
    # exactly like a pass — the failure this round's own skill names, and the
    # one it committed: all three of these witnesses were first written in
    # syntax Whence does not have (`@{a: "int"}`, `fn g(y: "int")`) and
    # skipped silently for a full test run.
    assert not row["parse_error"], (
        "witness does not parse (%s); a skipped witness is a false green"
        % row["parse_error"])
    st = row["sites"]["P-EXEMPT"]
    assert st["fired"] is False
    assert st["demand"] == M.site("P-EXEMPT").threshold - 1 == 1
    assert st["surface"] == 1.0


# ------------------------------------------------------ measure vs the oracle --

def test_measure_agrees_with_the_oracle_it_describes(pkg):
    """The cross-check that keeps `measure` honest: for every seed, the sites
    it reports must match what the real oracle's own `detail` says.

    `measure` reuses the oracle's predicates but re-implements its BRANCH
    ORDER, and that is precisely what `verify_sites` cannot catch.
    """
    checked = 0
    for seed in range(40):
        src = ProgramGen(seed, stress_rate=0.5).program()
        row = M.measure(pkg, src)
        if row["parse_error"]:
            continue
        checked += 1
        s = row["sites"]
        t = O.run_oracle("tail_transparency", pkg, src, timeout_s=20.0)
        p = O.run_oracle("param_erasure", pkg, src, timeout_s=20.0)
        f = O.run_oracle("frames", pkg, src, timeout_s=20.0)
        if t.kind == "ok":
            assert (t.detail == "no tail calls") == s["T-NONE"]["fired"], seed
            assert ("space-exempt" in t.detail) == s["T-SPACE"]["fired"], seed
            if "every binding provenance-tainted" in t.detail:
                assert s["T-ALL"]["fired"], seed
        if p.kind == "ok":
            assert (p.detail == "no parameter contracts") == \
                s["P-NONE"]["fired"], seed
            assert (", exempt" in p.detail) == s["P-EXEMPT"]["fired"], seed
        if f.kind == "ok" and "max excess" in f.detail:
            got = int(f.detail.split("max excess ")[1].split(" ")[0])
            assert got == s["F-SLACK"]["demand"], seed
    assert checked >= 25


def test_a_hang_inside_measure_degrades_to_a_recorded_row(pkg):
    """One runaway seed cost the pilot 10.95 s of its 30.1 s and nothing
    bounded it. A sweep must lose one row, not the run."""
    slow = ("fn spin(n) { if n <= 0 { 0 } else { spin(n - 1) } }\n"
            "let v = spin(100000000)\nprint(str(v))\n")
    val, err, secs = M.guarded(lambda: M.measure(pkg, slow), 1.0)
    assert err == "timeout"
    assert val is None
    assert secs < 5.0


# ---------------------------------------------------------------- reporting --

def test_summarize_reports_a_distance_only_for_distance_sites():
    rows = [{"seed": 0, "sites": {
        "R-CAP": {"fired": True, "demand": 9, "threshold": 6, "surface": 0.3,
                  "pairs_total": 36, "pairs_checked": 15},
        "T-TAINT": {"fired": True, "demand": 2, "surface": 0.5},
        "T-NONE": {"fired": False, "demand": 3, "surface": 1.0},
    }, "parse_error": ""}]
    s = M.summarize(rows)
    assert "distance_ratio" in s["sites"]["R-CAP"]
    assert "distance_ratio" not in s["sites"]["T-TAINT"]
    assert "distance_ratio" not in s["sites"]["T-NONE"]
    # surface is reported for every site, because fire rate and cost are
    # independent numbers
    assert s["sites"]["R-CAP"]["surface_mean_when_fired"] == 0.3
    assert s["sites"]["T-TAINT"]["surface_mean_when_fired"] == 0.5
    txt = M.report(s)
    assert "predicate: no threshold to be far from" in txt
    assert "at_boundary" in txt


def test_a_censored_distance_is_labelled_in_the_report():
    rows = [{"seed": 0, "parse_error": "", "sites": {
        "T-SPACE": {"fired": True, "demand": 500, "threshold": 500,
                    "censored": True, "surface": 0.0}}}]
    txt = M.report(M.summarize(rows))
    assert "CENSORED" in txt
    assert "demand is a floor" in txt


def test_summarize_tolerates_an_empty_and_an_errored_sweep():
    assert M.summarize([])["rows"] == 0
    s = M.summarize([{"seed": 1, "measure_error": "timeout", "sites": {},
                      "parse_error": ""}])
    assert s["errors"] == 1
    assert s["measure_errors"] == {"timeout": 1}
    M.report(s)          # must not raise on a sweep with no usable rows


def test_done_seeds_survives_a_row_truncated_by_a_kill(tmp_path):
    p = tmp_path / "sweep.jsonl"
    p.write_text('{"seed": 1}\n{"seed": 2}\n{"seed": 3, "si', encoding="utf-8")
    assert M.done_seeds(str(p)) == {1, 2}


def test_sweep_is_resumable_and_flushed(tmp_path, pkg):
    out = str(tmp_path / "s.jsonl")
    a = M.sweep(3, out=out, echo=False, with_oracles=False)
    assert len(a) == 3
    b = M.sweep(3, out=out, echo=False, with_oracles=False)
    assert b == []                       # everything already on disk
    c = M.sweep(5, out=out, echo=False, with_oracles=False)
    assert [r["seed"] for r in c] == [3, 4]
    assert len(M.read_rows(out)) == 5


# --------------------------------------------- round 110's unchecked numbers --

def test_round110s_chain_number_still_reproduces(pkg):
    """`oracles.py`'s FRAME_SLACK comment has asserted "the fuzzer's
    `1 + 1 + ...` chains 98" for 273 rounds with nothing re-executing it.
    It reproduces exactly. Pinned here so it stops being a claim no round
    re-runs — round 321 item 14's class, on a comment rather than a header.
    """
    assert M.chain_excess(pkg, 100)[0] == 98
