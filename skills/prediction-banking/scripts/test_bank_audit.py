"""Tests for bank_audit.py (round 471, skills B).

Every regression test below names the round whose real markdown broke the
parser, because each one was found by hand-checking a false positive the
script had just reported. The corpus these run against is this repo's own
`knowledge/` tree, so the live-tree pins carry the value they were taken at
and the command to re-derive it.
"""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)

import bank_audit as B  # noqa: E402


def _rows(md, tmp_path, name="f.md"):
    p = tmp_path / name
    p.write_text(md, encoding="utf-8")
    return B.parse_rows(str(p))


# --------------------------------------------------------------- row parsing

def test_the_verdict_column_is_found_by_content_not_position(tmp_path):
    """Nine rounds, at least four column layouts. Position is not a key."""
    md = (
        "| # | claim | verdict |\n|---|---|---|\n"
        "| P1 | a claim | **HIT** |\n"                       # verdict col 3
        "| A1 | **MISS** | a note about it |\n"              # verdict col 2
        "| P2 | S | a claim | **HIT** x4 |\n"                # verdict col 4
        "| R1 | a claim | 42.1-45.0 | HIT |\n"               # unbolded col 4
    )
    got = {r["id"]: r["verdict"] for r in _rows(md, tmp_path)}
    assert got == {"P1": B.HIT, "A1": B.MISS, "P2": B.HIT, "R1": B.HIT}


def test_a_claim_that_talks_about_misses_is_not_a_miss(tmp_path):
    """Round 112's R8: `| R8 | round-106 ledger >= 4 MISS | 5 MISS parts | HIT |`.

    The naive rule -- first cell containing a verdict word -- scored this
    HIT as a MISS, and that single row was one of the four HIT/MISS
    discrepancies the script attributed to round 112's headline. A verdict
    cell LEADS with its verdict; a claim cell talks about one.
    """
    md = "| R8 | round-106 ledger >= 4 MISS | 5 MISS parts | HIT |\n"
    rows = _rows(md, tmp_path)
    assert len(rows) == 1
    assert rows[0]["verdict"] == B.HIT


def test_a_note_after_the_verdict_is_not_part_of_the_verdict(tmp_path):
    """Round 376's P4: `**HIT** -- 61.6 % partial, ...`.

    Scanning the whole cell finds `partial` before `hit` and scores a HIT as
    a HALF. That one row was the entirety of round 376's apparent
    headline-vs-table disagreement; with it fixed, round 376 agrees.
    """
    md = ("| P4 | unpack is partial, not whole-model | "
          "**HIT** - 61.6 % partial, `anon` 30,600,970,240 |\n")
    rows = _rows(md, tmp_path)
    assert rows[0]["verdict"] == B.HIT


def test_qualified_verdicts_keep_their_class(tmp_path):
    md = (
        "| P1 | c | **WEAK HIT** - 2 not 3 |\n"
        "| P2 | c | **MISS (far)** |\n"
        "| P3 | c | **PARTIAL** |\n"
        "| P4 | c | **no-basis-reported** |\n"
        "| P5 | c | **NOT SCORED** - observed by the mandated instrument |\n"
        "| P6 | c | **unscorable-by-my-own-ordering** |\n"
    )
    got = {r["id"]: r["verdict"] for r in _rows(md, tmp_path)}
    assert got == {"P1": B.HALF, "P2": B.MISS, "P3": B.HALF,
                   "P4": B.OTHER, "P5": B.OTHER, "P6": B.OTHER}


def test_a_row_with_no_verdict_at_all_is_dropped(tmp_path):
    """Round 380's P11 reads `see §8` -- banked, not yet scored."""
    md = ("| P11 | whole-atlas agreement stays 6861 | see §8 | slow tier |\n"
          "| P12 | something | **HIT** |\n")
    rows = _rows(md, tmp_path)
    assert [r["id"] for r in rows] == ["P12"]


def test_a_separator_row_is_not_a_prediction(tmp_path):
    md = "| # | claim | verdict |\n|---|---|---|\n| P1 | c | **HIT** |\n"
    assert len(_rows(md, tmp_path)) == 1


# ------------------------------------------------------------- aggregates

def test_a_prediction_id_is_not_a_count(tmp_path):
    """`P11 pending` parsed as "11 PENDING" and `P4 HIT. P5 HIT.` as
    "4 HIT, 5 HIT". Before the digit-boundary guard the script reported 18
    self-inconsistent headlines; 12 of them were its own regex."""
    a = B.parse_aggregates("**11 HIT, 2 HALF, 3 MISS of 14** (P11 pending §8).")
    assert len(a) == 1
    assert a[0]["counts"] == {B.HIT: 11, B.HALF: 2, B.MISS: 3}
    assert a[0]["total"] == 14
    assert B.parse_aggregates("- P4 HIT. P5 HIT. P6 **MISS** - it did not.") == []


def test_a_wrapped_headline_is_joined_before_it_is_added_up(tmp_path):
    """Round 428's headline is split across two source lines."""
    a = B.parse_aggregates("bank scored **5\nHIT, 3 PARTIAL, 7 MISS of 15**, which is the worst\n")
    assert a and a[0]["counts"] == {B.HIT: 5, B.HALF: 3, B.MISS: 7}
    assert a[0]["total"] == 15


def test_four_aggregates_on_two_lines_stay_four(tmp_path):
    """Round 415."""
    a = B.parse_aggregates(
        "**5 HIT / 0 PARTIAL / 0 MISS of 5 mechanism; 4 HIT / 1 PARTIAL / 2 MISS of 7\n"
        "outcome; 2 HIT / 1 MISS of 3 ledger; 1 HIT / 1 MISS of 2 cost.**\n")
    assert [x["total"] for x in a] == [5, 7, 3, 2]


def test_a_second_sentence_is_a_second_aggregate(tmp_path):
    """Round 416 put a total and a by-class breakdown in one line."""
    a = B.parse_aggregates(
        "**10 HIT / 1 PARTIAL / 4 MISS of 15. By class: mechanism 3/5, "
        "outcome 7 HIT / 1 PARTIAL / 3 MISS of 10.**\n")
    assert [x["total"] for x in a] == [15, 10]


def test_a_table_row_is_never_a_headline(tmp_path):
    """Round 407's `| Q16 | 13-17 HIT of 21, >= 1 UNSCORABLE | **MISS** |`
    is a PREDICTION about a count, not a scoring headline."""
    assert B.parse_aggregates(
        "| Q16 | 13-17 HIT of 21, >= 1 UNSCORABLE | **MISS** - 9 HIT |\n") == []


def test_the_of_n_must_follow_the_terms(tmp_path):
    """`1.5 GiB of 2.0 GiB swap` supplied an "of 2" to a tally in round 395,
    and prose 31 lines away supplied an "of 93" in round 426."""
    a = B.parse_aggregates(
        "**8 HIT, 2 MISS.** `nproc` 1, load 0.28, 1.5 GiB of 2.0 GiB swap in use.\n")
    assert a and a[0]["total"] is None


# ------------------------------------------------------------------ scoring

def test_score_counts_a_half_as_a_half_and_excludes_other():
    r, n = B.score({B.HIT: 6, B.HALF: 3, B.MISS: 2, B.OTHER: 4})
    assert n == 11
    assert r == pytest.approx((6 + 1.5) / 11)


def test_two_proportion_z_is_symmetric_and_zero_on_equal_rates():
    z, p = B.two_proportion_z(50, 100, 100, 200)
    assert z == pytest.approx(0.0)
    assert p == pytest.approx(1.0)
    z1, _ = B.two_proportion_z(60, 100, 40, 100)
    z2, _ = B.two_proportion_z(40, 100, 60, 100)
    assert z1 == pytest.approx(-z2)


# --------------------------------------------------- the SKILL's own checks

def test_this_rounds_own_bank_satisfies_every_bank_check():
    """Dogfood: round 471 banked under the rules this script enforces."""
    bank = os.path.join(ROOT, "state", "skills", "round-471", "PREDICTIONS.md")
    assert os.path.exists(bank), bank
    res = B.audit_bank(bank)
    assert [k for k, st, _ in res if st == B.FAIL] == [], res
    # and the audit must actually be exercising the bank, not shrugging
    assert sum(1 for _, st, _ in res if st == B.PASS) >= 6, res


def test_the_read_set_check_is_not_vacuous():
    """A bank with no read-set must FAIL the round-470 check, or the check
    is decoration. Round 468's bank is the negative control: it predates the
    rule, and nothing in it declares what had been opened."""
    old = os.path.join(ROOT, "state", "whence", "round-468", "PREDICTIONS.md")
    if not os.path.exists(old):
        pytest.skip("round 468's bank is not in this tree")
    res = dict((k, st) for k, st, _ in B.audit_bank(old))
    assert res["read_set_470"] == B.FAIL
    assert res["banked_before"] == B.PASS   # a real bank, just an older one


# ------------------------------------------------------- live-corpus pins

def test_round_470s_table_parses_to_the_score_round_470_published():
    """The one bank whose headline, ledger quote and table were all checked
    by hand this round: `6 HIT, 3 PARTIAL, 2 MISS of 11`."""
    import glob
    f = glob.glob(os.path.join(ROOT, "knowledge", "round-470-*.md"))
    assert len(f) == 1, f
    t = B.tally(B.parse_rows(f[0]))
    assert t == {B.HIT: 6, B.HALF: 3, B.MISS: 2}, t


def test_round_380s_headline_does_not_sum_to_its_own_of_n():
    """A CONFIRMED corpus defect, pinned so that fixing round 380's file
    turns this red rather than silently deleting the finding.

    `**11 HIT, 2 HALF, 3 MISS of 14**` -- the terms sum to 16, the table has
    13 scored rows (P11 is `see §8`), and its HIT count is 8, not 11.
    Re-derive:
      python3 skills/prediction-banking/scripts/bank_audit.py rows \\
          knowledge/round-380-*.md
    """
    import glob
    f = glob.glob(os.path.join(ROOT, "knowledge", "round-380-*.md"))
    if not f:
        pytest.skip("round 380's knowledge file is not in this tree")
    aggs = [a for a in B.parse_aggregates(open(f[0], errors="replace").read())
            if a["total"] == 14]
    assert aggs, "round 380's headline moved -- re-adjudicate before editing this test"
    a = aggs[0]
    assert sum(a["counts"].values()) == 16
    assert B.tally(B.parse_rows(f[0])).get(B.HIT) == 8


def test_the_corpus_walk_runs_and_reports_a_rate_in_the_measured_band():
    """End-to-end. The band is wide on purpose: the corpus grows every round
    and the point of the number is that it is re-derived, not carried.
    Round 471 measured 70.8% over 1474 scorable rows from 111 files."""
    out = subprocess.run(
        [sys.executable, os.path.join(HERE, "bank_audit.py"), "corpus"],
        cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    line = [l for l in out.stdout.splitlines() if "lifetime hit rate" in l]
    assert len(line) == 1, out.stdout[:500]
    pct = float(line[0].split(":")[1].strip().split("%")[0])
    assert 55.0 <= pct <= 85.0, line[0]
    for section in ("== A.", "== B.", "== C.", "== D.", "== E2.", "== F."):
        assert section in out.stdout, section
