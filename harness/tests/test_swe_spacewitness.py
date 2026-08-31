"""Round 401 (SWE-loop D): what the tail-transparency SPACE exemption
actually suppresses, and the tightening that measurement justified.

Round 389's next-step item 5 asked what seeds 140/273/341 — "the corpus's
only unbounded tail programs" — actually are. The answer turned out to
generalise: the exemption's POTENTIAL cost (it drops the whole comparison)
was already recorded; its REALIZED cost was not, and the number that splits
the two was on the row and thrown away.
"""

import json
import os
import subprocess
import sys

import pytest

from harness.swe import exemptmap as M
from harness.swe import instrument as INS
from harness.swe import oracles as O
from harness.swe import spacewitness as S

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def pkg():
    return S.load(tag="r401wtest")


# ------------------------------------------------------ the classification --

def test_a_pure_tail_loop_is_a_ceiling_artifact(pkg):
    """The shape the exemption exists for: only the LIFTED run hits the
    ceiling, and the answers differ because of it."""
    w = S.witness(pkg, M.deep_program(1200), max_depth=500)
    assert w["klass"] == S.CEILING_ARTIFACT
    assert w["peak_original"] < 500 <= w["peak_lifted"]
    assert w["differs"] is True and w["suppressed"]


def test_a_non_tail_runaway_beside_a_tail_call_is_free(pkg):
    """Round 401's finding, synthesised. Both forms stop at the same wall,
    the miss is symmetric, and the exemption drops a valid comparison."""
    w = S.witness(pkg, S.both_at_ceiling_program(600), max_depth=500)
    assert w["klass"] == S.FREE_BOTH_AT_CEILING
    assert w["peak_original"] == w["peak_lifted"] == 500
    assert w["differs"] is False and w["suppressed"] == ""


def test_a_shallow_program_does_not_fire_the_exemption_at_all(pkg):
    w = S.witness(pkg, M.deep_program(10), max_depth=500)
    assert w["klass"] == S.NOT_FIRED
    assert w["peak_lifted"] < 500


def test_a_program_with_no_tail_call_is_classified_separately(pkg):
    w = S.witness(pkg, "let a = 1 + 1\nprint(str(a))\n", max_depth=500)
    assert w["klass"] == S.NO_TAIL and w["n_tail"] == 0


def test_a_parse_error_is_data_not_a_raise(pkg):
    w = S.witness(pkg, "let = = =\n", max_depth=500)
    assert w["klass"] == "parse_error"


def test_the_class_moves_with_the_ceiling_for_a_bounded_program(pkg):
    """`deep_program(1200)` is exempt at 500 and compared at 5000 — round
    389's "the exemption is a property of the HARNESS's ceiling"."""
    src = M.deep_program(1200)
    assert S.witness(pkg, src, max_depth=500)["klass"] == S.CEILING_ARTIFACT
    assert S.witness(pkg, src, max_depth=5000)["klass"] == S.NOT_FIRED


def test_the_class_does_NOT_move_with_the_ceiling_for_an_unbounded_program(pkg):
    """And this is why raising the ceiling could never convert the three
    survivors: there is no rung at which the original run stops being
    censored."""
    src = S.both_at_ceiling_program(10 ** 9)
    for md in (200, 500, 1500):
        w = S.witness(pkg, src, max_depth=md)
        assert w["klass"] == S.FREE_BOTH_AT_CEILING, (md, w)
        assert w["peak_original"] == w["peak_lifted"] == md


# ----------------------------------------------------------- the bracket ----

def test_demand_bracket_calls_an_unbounded_program_unbounded(pkg):
    br = S.demand_bracket(pkg, S.both_at_ceiling_program(10 ** 9),
                          rungs=(100, 300, 700))
    assert br["unbounded"] is True
    assert all(r["censored"] for r in br["rungs"])


def test_demand_bracket_calls_a_bounded_program_bounded(pkg):
    br = S.demand_bracket(pkg, S.both_at_ceiling_program(150),
                          rungs=(100, 300, 700))
    assert br["unbounded"] is False
    assert br["rungs"][0]["censored"] is True      # 100 is not enough
    assert br["rungs"][-1]["censored"] is False    # 700 is


# ------------------------------------------------------------ the summary ---

def _row(klass, differs, seed):
    return {"seed": seed, "klass": klass, "differs": differs,
            "max_depth": 500}


def test_realized_cost_is_not_the_potential_cost():
    """The whole point. `surface 0.0` says a firing CAN hide anything;
    `realized_cost` says how often it did."""
    rows = [_row(S.CEILING_ARTIFACT, True, i) for i in range(26)]
    rows += [_row(S.FREE_BOTH_AT_CEILING, False, 100 + i) for i in range(14)]
    rows += [_row(S.FREE_LIFTED_ONLY, False, 200)]
    rows += [_row(S.NOT_FIRED, False, 300 + i) for i in range(50)]
    s = S.summarize(rows)
    assert s["fired"] == 41
    assert s["paid"] == 26 and s["free"] == 15
    assert abs(s["realized_cost"] - 26 / 41) < 1e-9
    assert s["tightenable"] == 14
    assert s["alarm"] == 0
    txt = S.report(s)
    assert "REALIZED" in txt and "potential cost 100.0%" in txt


def test_an_alarm_class_is_counted_and_named():
    rows = [_row(S.SUPPRESSED_AT_CEILING, True, 7)]
    s = S.summarize(rows)
    assert s["alarm"] == 1 and s["alarm_seeds"] == [7]
    assert "ALARM" in S.report(s)


def test_summarize_tolerates_an_empty_scan():
    s = S.summarize([])
    assert s["n_rows"] == 0 and s["realized_cost"] is None
    S.report(s)          # must not raise


# --------------------------------------------------- the tightened oracle ---

def test_the_oracle_still_exempts_the_asymmetry_it_was_built_for(pkg):
    """Round 337's own witness must keep its verdict, wording included —
    `test_swe_oracles.py` pins the substring."""
    src = ("fn even(n) { if n == 0 { true } else { odd(n - 1) } }\n"
           "fn odd(n) { if n == 0 { false } else { even(n - 1) } }\n"
           "let par = even(1500)\n")
    o = O.run_oracle("tail_transparency", pkg, src, timeout_s=20.0)
    assert o.kind == "ok" and "space-exempt" in o.detail, o.detail
    assert "depth 500 >= max_depth 500" in o.detail, o.detail


def test_the_oracle_no_longer_exempts_a_symmetric_ceiling(pkg):
    """The tightening. Both forms stop at the same wall, so the comparison
    is made — and on this program it passes, which is the point: 15 of round
    389's 41 firings were being dropped for nothing."""
    o = O.run_oracle("tail_transparency", pkg,
                     S.both_at_ceiling_program(600), timeout_s=30.0,
                     max_depth=500)
    assert o.kind == "ok"
    assert "space-exempt" not in o.detail, o.detail
    assert "both runs reached max_depth" in o.detail, o.detail


def test_the_tightening_is_a_named_constant_a_future_round_can_flip():
    """A widening this narrow deserves a switch, not an archaeology dig:
    `free_both_at_ceiling` is safe on THIS corpus and a future corpus could
    contain a genuine ceiling artefact with symmetric peaks."""
    assert O.SPACE_EXEMPT_WHEN_BOTH_AT_CEILING is False


def test_the_oracle_detail_always_carries_both_peaks(pkg):
    """Round 110's convention — a verdict reports the number it decided on.
    The ORIGINAL run's peak is the number this round found discarded."""
    o = O.run_oracle("tail_transparency", pkg, M.deep_program(1200),
                     timeout_s=30.0, max_depth=500)
    assert "original reached" in o.detail, o.detail


def test_measure_and_the_oracle_still_agree_on_T_SPACE(pkg):
    """`test_swe_exemptmap.py` asserts `("space-exempt" in detail) ==
    T-SPACE.fired` over the corpus; the map's predicate had to move with the
    oracle's or that cross-check would go red."""
    for src in (M.deep_program(1200), S.both_at_ceiling_program(600),
                M.deep_program(10)):
        row = M.measure(pkg, src, max_depth=500)
        o = O.run_oracle("tail_transparency", pkg, src, timeout_s=30.0,
                         max_depth=500)
        assert ("space-exempt" in o.detail) == row["sites"]["T-SPACE"]["fired"], src


def test_the_map_records_the_original_peak_it_used_to_discard(pkg):
    row = M.measure(pkg, S.both_at_ceiling_program(600), max_depth=500)
    st = row["sites"]["T-SPACE"]
    assert st["demand_original"] == 500
    assert st["demand"] == 500


def test_a_censored_demand_is_labelled_even_when_the_site_does_not_fire(pkg):
    """The invariant round 383 wrote was `fired == censored`. Tightening
    breaks it in one direction and the honest replacement is weaker and
    true: `censored` describes the NUMBER, and firing implies it."""
    row = M.measure(pkg, S.both_at_ceiling_program(600), max_depth=500)
    st = row["sites"]["T-SPACE"]
    assert st["fired"] is False
    assert st["censored"] is True
    for src in (M.deep_program(1200), M.deep_program(10)):
        st = M.measure(pkg, src, max_depth=500)["sites"]["T-SPACE"]
        assert (not st["fired"]) or st["censored"]


def test_the_site_registry_anchor_follows_the_branch_it_names():
    """The registry is self-verifying; moving the branch without moving the
    anchor is what killed round 389's arm mid-flight."""
    M.verify_sites()
    site = [s for s in M.SITES if s.id == "T-SPACE"][0]
    src = open(os.path.join(REPO, "harness", "swe", "oracles.py")).read()
    assert src.count(site.anchor) == site.anchor_n


# ------------------------------------------------------------------- scan ---

def test_scan_writes_stamped_resumable_rows(tmp_path, monkeypatch):
    out = tmp_path / "sw.jsonl"
    S.scan(3, out=str(out), max_depth=500, echo=False)
    rows = S.read_rows(str(out))
    assert len(rows) == 3
    for r in rows:
        assert r[INS.STAMP_KEY]["lane"] == "spacewitness.scan"
        assert "klass" in r and r["max_depth"] == 500
    S.scan(3, out=str(out), max_depth=500, echo=False)      # resume: no dupes
    assert len(S.read_rows(str(out))) == 3


def test_scan_keeps_two_ceilings_apart_in_one_file(tmp_path):
    out = tmp_path / "sw.jsonl"
    S.scan(2, out=str(out), max_depth=500, echo=False)
    S.scan(2, out=str(out), max_depth=1500, echo=False)
    rows = S.read_rows(str(out))
    assert len(rows) == 4
    assert sorted(set(r["max_depth"] for r in rows)) == [500, 1500]


# ----------------------------------------------------------------- shrink ---

def test_shrink_preserves_the_class_not_a_crash_signature(pkg):
    """This is an exemption witness, not a crash reproducer: the invariant
    to keep is WHY the branch was reached."""
    src = S.both_at_ceiling_program(600) + "let z = 1\nlet y = 2\nlet x = 3\n"
    base = S.witness(pkg, src, max_depth=500)
    assert base["klass"] == S.FREE_BOTH_AT_CEILING

    def keep(cand):
        return S.witness(pkg, cand, max_depth=500)["klass"] == base["klass"]

    from harness.swe.fuzz import shrink as ddshrink
    small = ddshrink(src, keep)
    assert small is not None
    assert len(small.strip().split("\n")) < len(src.strip().split("\n"))
    assert S.witness(pkg, small, max_depth=500)["klass"] == S.FREE_BOTH_AT_CEILING


# -------------------------------------------------------------------- cli ---

def test_cli_seeds_prints_one_json_row_per_seed():
    p = subprocess.run([sys.executable, "-m", "harness.swe.spacewitness",
                        "seeds", "--seeds", "140,341"],
                       cwd=REPO, capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stderr
    rows = [json.loads(l) for l in p.stdout.strip().split("\n")]
    assert [r["seed"] for r in rows] == [140, 341]
    for r in rows:
        assert r["klass"] == S.FREE_BOTH_AT_CEILING, r


def test_cli_unknown_command_returns_2():
    p = subprocess.run([sys.executable, "-m", "harness.swe.spacewitness", "nope"],
                       cwd=REPO, capture_output=True, text=True, timeout=120)
    assert p.returncode == 2
