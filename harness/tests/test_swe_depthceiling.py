"""Round 389 (SWE-loop D) — the ceilings the oracle suite chose for itself.

Round 383 left four asks. Three of them are about a BOUND the suite writes
down once and then never re-derives:

  * `max_depth=500` — a default repeated at 15 call sites in `oracles.py`,
    40x below the language's own `Interpreter.DEFAULT_MAX_DEPTH = 20000`,
    and the reason 10.8 % of the corpus was silently exempt from the
    tail-transparency oracle;
  * `names[:6]` — a literal in two loop bounds, skipping 6 426 of 13 509
    corpus pairs behind a green `render ok`;
  * `FRAME_SLACK = 140` — a constant in one tree that is only sound while it
    exceeds `FAST_MAX_DEPTH` in another.

What is pinned here is RELATIONS and MECHANISMS, never this round's rates.
The one number that IS pinned is `excess == under * depth`, because it is a
property of the charge arithmetic and not of the corpus: if it ever stops
holding, every conclusion drawn from the detection ladder is void.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from harness.swe import exemptmap as M             # noqa: E402
from harness.swe import oracles as O               # noqa: E402
from harness.swe.fuzz import WHENCE_ROOT           # noqa: E402
from harness.swe.killers import load_whence        # noqa: E402


@pytest.fixture(scope="module")
def pkg():
    p = dict(load_whence(WHENCE_ROOT, "t389depth"))
    p.setdefault("root", WHENCE_ROOT)
    return p


# ------------------------------------------- FRAME_SLACK: the upper bound --

def test_a_correct_recursion_costs_a_FLAT_excess_at_every_depth(pkg):
    """The control the detection ladder needs.

    If a correct non-tail recursion's transient grew with depth, a rung
    going over slack would say nothing about the injected bug. It does not
    grow: direct mode charges `cdepth + 1` per body and the excess is the
    same handful of frames at depth 2 and at depth 400.
    """
    lad = M.clean_frame_excess_ladder(pkg, depths=(2, 8, 32, 100, 400))
    excesses = [r["excess"] for r in lad["rungs"]]
    assert None not in excesses, lad
    assert len(set(excesses)) == 1, lad
    assert not any(r["over_slack"] for r in lad["rungs"]), lad


@pytest.mark.parametrize("under", (1, 2))
def test_an_undercharge_produces_excess_exactly_under_times_depth(pkg, under):
    """The arithmetic the whole ladder rests on. `oraclekill`'s mutant turns
    `cost = body.cdepth + 1` into `- 1` (2 frames per level); round 108's
    real bug was 1. Either way the excess is linear in guest depth with the
    undercharge as its slope, which is what makes `FRAME_SLACK` a DETECTION
    DEPTH and not just a threshold."""
    d = M.undercharge_detection_depth(pkg, under=under, depths=(8, 16, 32, 64))
    for r in d["rungs"]:
        assert r["excess"] == under * r["depth"], (under, r)


def test_the_frames_oracle_is_blind_to_the_bug_below_slack_over_under(pkg):
    """The ceiling half of the bracket, stated as a relation.

    `excess = under * depth`, so the oracle first sees the bug at
    `depth > slack / under`. Raising `FAST_MAX_DEPTH` raises the derived
    slack and therefore raises this depth: the derivation trades a
    false-positive risk for a strictly larger blind spot, and that trade is
    the thing round 383's item 3 did not name.
    """
    slack = O.frame_slack(pkg)
    under = 2
    d = M.undercharge_detection_depth(pkg, under=under,
                                      depths=(slack // under - 4,
                                              slack // under + 4))
    assert d["rungs"][0]["over_slack"] is False, d
    assert d["rungs"][1]["over_slack"] is True, d
    assert d["first_detected_at_depth"] == slack // under + 4


def test_the_detectable_band_has_a_measured_TOP_not_an_open_one(pkg):
    """Past some guest depth the undercharged run dies on the host stack (or
    is stopped by `max_depth`) before its excess can exceed the slack. Above
    that, `oracle_frames` reports `ok` on a buggy interpreter and only
    `modes` sees anything — so the band is two-sided and both sides are
    measurable."""
    r = M.deepest_undercharged_run(pkg, under=2, limit=1000, hi=600)
    assert r["deepest_surviving_depth"] is not None, r
    assert r["excess_there"] == 2 * r["deepest_surviving_depth"]
    assert r["max_detectable_slack"] == r["excess_there"] - 1
    # today's derived slack must sit strictly inside the band
    assert O.frame_slack(pkg) < r["max_detectable_slack"], (
        "the derived slack %d is at or above the largest excess the bug can "
        "reach (%d): oracle_frames can no longer see round 108's undercharge"
        % (O.frame_slack(pkg), r["excess_there"]))


def test_slack_band_reports_sound_on_todays_tree(pkg):
    b = M.slack_band(pkg)
    assert b["floor_measured"] < b["frame_slack_now"], b
    assert b["sound"] is True, b


# ------------------------------------------------- render: the pair cap --

def test_every_render_verdict_now_carries_its_pair_coverage(pkg):
    """Round 383's item 2. A green `render ok` used to say nothing about how
    many pairs it compared; 39.6 % of the corpus was past the cap."""
    over = "\n".join("let v%d = %d" % (i, i)
                     for i in range(O.RENDER_PAIR_CAP + 6)) + "\n"
    k = O.RENDER_PAIR_CAP + 6
    o = O.run_oracle("render", pkg, over, timeout_s=30.0)
    assert o.kind == "ok", o.detail
    assert "%d bindings, pairs %d/%d" % (
        k, O._n_choose_2(O.RENDER_PAIR_CAP), O._n_choose_2(k)) in o.detail, o.detail

    under = "let a = 1\nlet b = 2\nlet c = 3\n"
    o2 = O.run_oracle("render", pkg, under, timeout_s=30.0)
    assert "3 bindings, pairs 3/3" in o2.detail, o2.detail


def test_the_pair_cap_is_a_named_constant_and_is_overridable(pkg):
    """It was two bare `6`s in two loop bounds. A campaign that wants full
    coverage should be able to buy it rather than edit the oracle."""
    # the cap is 24 (round 389, measured); the corpus max is 16 bindings, so
    # the pin is the RELATION to what the corpus can produce, not the number
    assert O.RENDER_PAIR_CAP >= 16
    over = "\n".join("let v%d = %d" % (i, i) for i in range(10)) + "\n"
    o = O.oracle_render(pkg, over, pair_cap=4)
    assert o.kind == "ok" and "pairs 6/45" in o.detail, o.detail
    o2 = O.oracle_render(pkg, over)
    assert o2.kind == "ok" and "pairs 45/45" in o2.detail, o2.detail


def test_n_choose_2_is_zero_below_two_bindings():
    assert [O._n_choose_2(k) for k in (0, 1, 2, 3, 6, 10)] == \
        [0, 0, 1, 3, 15, 45]


# ------------------------------------------------ max_depth: the plumbing --

def test_the_suite_ceiling_is_far_below_the_languages_own_default(pkg):
    """The fact that made round 383's item 1 worth a round. Not a claim
    about which number is right — a claim that the two exist and differ."""
    assert pkg["Interpreter"].DEFAULT_MAX_DEPTH > 500 * 10


def test_sweep_records_the_ceiling_it_measured_under(pkg):
    """A row that does not name its arm cannot be A/B'd against another."""
    row = M.sweep_record(pkg, 3, max_depth=777, with_oracles=False)
    assert row["max_depth"] == 777 and row["timeout_s"] == 3.0


def test_the_ceiling_actually_changes_a_verdicts_reason(pkg):
    """`deep_program(1200)` is space-exempt at 500 and compared at 5000: the
    exemption is a property of the HARNESS's ceiling, not of the program."""
    src = M.deep_program(1200)
    lo = O.run_oracle("tail_transparency", pkg, src, timeout_s=30.0,
                      max_depth=500)
    hi = O.run_oracle("tail_transparency", pkg, src, timeout_s=30.0,
                      max_depth=5000)
    assert lo.kind == "ok" and "space-exempt" in lo.detail, lo.detail
    assert hi.kind == "ok" and "space-exempt" not in hi.detail, hi.detail


def test_default_out_is_no_longer_pinned_to_one_round(tmp_path):
    """Round 383 wrote `round-383` in as a literal, so this round's sweep
    would have appended to round 383's file and mixed two arms into one
    population."""
    base = tmp_path / "state" / "swe"
    for name in ("round-101", "round-9", "round-1200", "notaround"):
        (base / name).mkdir(parents=True)
    assert M.round_dir(str(tmp_path)).endswith("round-1200")
    old = os.environ.get("EXEMPTMAP_ROUND_DIR")
    os.environ["EXEMPTMAP_ROUND_DIR"] = "/tmp/anarm"
    try:
        assert M.round_dir(str(tmp_path)) == "/tmp/anarm"
    finally:
        if old is None:
            del os.environ["EXEMPTMAP_ROUND_DIR"]
        else:
            os.environ["EXEMPTMAP_ROUND_DIR"] = old


# ------------------------------- the instrument digest (round 389, item 4) --

def test_a_sweep_row_records_the_instrument_that_measured_it(pkg):
    """`verify_sites()` runs once, at sweep start, so it can PREVENT a mixed
    file and cannot DETECT one that a mid-flight edit created. This round
    edited `oracles.py` while an arm was running and had to check the
    resulting file by hand."""
    row = M.sweep_record(pkg, 1, max_depth=500, with_oracles=False)
    assert len(row["oracles_sha"]) == 12
    assert row["oracles_sha"] == M.oracles_digest()


def test_the_digest_follows_the_CONTENT_not_the_stat(tmp_path):
    """An edit DURING a sweep must change the digest, so the rows written
    after it disagree with the rows written before — the only way an
    after-the-fact reader can see a mixed population.

    This is the test that killed the stat-keyed cache: same size, same
    mtime granularity, different content. `140 -> 190` is exactly the edit
    this round made to a constant in `oracles.py`.
    """
    f = tmp_path / "fake_oracles.py"
    f.write_text("FRAME_SLACK = 140\n")
    d1 = M.oracles_digest(str(f))
    f.write_text("FRAME_SLACK = 190\n")
    d2 = M.oracles_digest(str(f))
    assert d1 and d2 and d1 != d2
    assert M.oracles_digest("/nonexistent/oracles.py") == ""


def test_ab_reports_a_mixed_arm_rather_than_averaging_it(tmp_path):
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    a.write_text(
        '{"seed": 0, "sites": {}, "oracles_sha": "aaaaaaaaaaaa", "max_depth": 500}\n'
        '{"seed": 1, "sites": {}, "oracles_sha": "bbbbbbbbbbbb", "max_depth": 500}\n')
    b.write_text(
        '{"seed": 0, "sites": {}, "oracles_sha": "aaaaaaaaaaaa", "max_depth": 5000}\n'
        '{"seed": 1, "sites": {}, "oracles_sha": "aaaaaaaaaaaa", "max_depth": 5000}\n')
    r = M.ab(str(a), str(b))
    assert r["mixed_instrument"] is True
    assert r["digests_a"] == {"aaaaaaaaaaaa": 1, "bbbbbbbbbbbb": 1}
    assert r["digests_b"] == {"aaaaaaaaaaaa": 2}


def test_rows_written_before_round_389_are_named_not_guessed():
    """The arms this round actually ran carry no digest; `sweep_digests`
    reports them as `pre-r389` rather than inventing one."""
    import os as _os
    p = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__)))), "state", "swe", "round-389",
        "armA-500.jsonl")
    if not _os.path.exists(p):
        pytest.skip("round 389's arm A is not in this checkout")
    assert M.sweep_digests(p) == {"pre-r389": 360}
