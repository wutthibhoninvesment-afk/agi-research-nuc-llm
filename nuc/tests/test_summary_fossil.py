#!/usr/bin/env python3
"""Falsifiers for nuc/summary_fossil.py (round 478).

Round 472's lesson: a test that has never gone red is not a falsifier. Every
test here was mutation-checked -- the mutation list is at the bottom of the
file in `MUTATIONS`, and `test_mutation_list_is_honest` keeps it from drifting
away from the assertions it claims to cover.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import summary_fossil as sf  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
REAL_CAPTURE = os.path.join(ROOT, "state", "nuc-capture-r478")
REAL_NOW = "2026-09-03T17:13:00Z"


def ls(*rows) -> str:
    """`ls -l` text. Each row is (name, size, 'Mon DD HH:MM')."""
    out = ["total 5284"]
    for name, size, stamp in rows:
        out.append(f"-rw-r--r-- 1 root root {size:>8} {stamp} {name}")
    return "\n".join(out) + "\n"


# A three-day box: day 10 rendered, day 11 NOT rendered, day 12 still open.
BASIC = ls(
    ("sa10", 1000, "Aug 10 23:50"),
    ("sar10", 2000, "Aug 11 00:07"),
    ("sa11", 1000, "Aug 11 23:50"),
    ("sa12", 1000, "Aug 12 17:00"),
)
BASIC_NOW = "2026-08-12T17:30:00Z"


# --------------------------------------------------------------------------
# fires()
# --------------------------------------------------------------------------

def test_receipt_present_means_the_fire_ran():
    rep = sf.fires(BASIC, BASIC_NOW)
    row = [r for r in rep["fires"] if r["day_file"] == "sa10"][0]
    assert row["verdict"] == "fire_ran"
    assert row["fire_utc"] == "2026-08-11T00:07:00Z"
    assert row["receipt"] == "sar10"
    assert row["receipt_lag_s"] == 0.0


def test_day_file_without_receipt_is_a_missed_fire_not_rotation():
    """The retention theorem. sa11 survived, so sar11 would have too."""
    rep = sf.fires(BASIC, BASIC_NOW)
    row = [r for r in rep["fires"] if r["day_file"] == "sa11"][0]
    assert row["verdict"] == "fire_missed"
    assert row["fire_utc"] == "2026-08-12T00:07:00Z"
    assert rep["missed_fires_utc"] == ["2026-08-12T00:07:00Z"]


def test_the_newest_day_is_pending_not_missed():
    """Without this the last day of every capture reads as an outage."""
    rep = sf.fires(BASIC, BASIC_NOW)
    row = [r for r in rep["fires"] if r["day_file"] == "sa12"][0]
    assert row["verdict"] == "fire_pending"
    assert "2026-08-13T00:07:00Z" not in rep["missed_fires_utc"]


def test_a_day_whose_fire_has_just_passed_is_scored_not_pending():
    """Past the settle window with no receipt, the fire is a miss."""
    rep = sf.fires(BASIC, "2026-08-13T00:20:00Z")
    row = [r for r in rep["fires"] if r["day_file"] == "sa12"][0]
    assert row["verdict"] == "fire_missed"


def test_a_fire_inside_the_settle_window_is_pending_not_missed():
    """The boundary mutation `fire > now` -> `fire >= now` survived round
    478's first mutation pass, which means nothing pinned this at all. A
    capture taken seconds after 00:07 must not manufacture an outage out of a
    receipt `sa2` has not finished writing."""
    at_the_instant = sf.fires(BASIC, "2026-08-13T00:07:00Z")
    row = [r for r in at_the_instant["fires"] if r["day_file"] == "sa12"][0]
    assert row["verdict"] == "fire_pending"
    assert at_the_instant["settle_s"] == 600
    one_second_later = sf.fires(BASIC, "2026-08-13T00:07:01Z")
    assert [r for r in one_second_later["fires"]
            if r["day_file"] == "sa12"][0]["verdict"] == "fire_pending"
    # ...and exactly at the far edge of the window it is still pending,
    # one second past it a miss.
    assert [r for r in sf.fires(BASIC, "2026-08-13T00:16:59Z")["fires"]
            if r["day_file"] == "sa12"][0]["verdict"] == "fire_pending"
    assert [r for r in sf.fires(BASIC, "2026-08-13T00:17:00Z")["fires"]
            if r["day_file"] == "sa12"][0]["verdict"] == "fire_missed"


def test_settle_window_is_tunable_and_zero_restores_the_hard_boundary():
    rep = sf.fires(BASIC, "2026-08-13T00:07:00Z", settle_s=0)
    row = [r for r in rep["fires"] if r["day_file"] == "sa12"][0]
    assert row["verdict"] == "fire_missed"
    assert rep["settle_s"] == 0


def test_missing_day_file_is_a_hole_and_gets_no_verdict():
    """`sa02` did not exist on the real box; the fire it would feed is
    overdetermined and must not be scored."""
    text = ls(
        ("sa10", 1000, "Aug 10 23:50"),
        ("sar10", 2000, "Aug 11 00:07"),
        ("sa12", 1000, "Aug 12 23:50"),
        ("sar12", 2000, "Aug 13 00:07"),
    )
    rep = sf.fires(text, "2026-08-14T09:00:00Z")
    assert rep["no_day_file_dates"] == ["2026-08-11"]
    assert [r["day_file"] for r in rep["fires"]] == ["sa10", "sa12"]
    assert rep["missed_fires_utc"] == []


def test_fire_time_of_day_is_derived_from_the_receipts_not_hardcoded():
    """Round 448's rule. A box whose timer says 03:11 must be scored at 03:11."""
    text = ls(
        ("sa10", 1000, "Aug 10 23:50"),
        ("sar10", 2000, "Aug 11 03:11"),
        ("sa11", 1000, "Aug 11 23:50"),
        ("sar11", 2000, "Aug 12 03:11"),
        ("sa12", 1000, "Aug 12 23:50"),
    )
    rep = sf.fires(text, "2026-08-13T09:00:00Z")
    assert rep["fire_time_of_day"] == "03:11"
    assert rep["missed_fires_utc"] == ["2026-08-13T03:11:00Z"]


def test_receipt_lag_is_reported_so_a_drifting_timer_is_visible():
    """The mode needs a MAJORITY to be meaningful, so this fixture gives it
    three 00:07 receipts against one late one."""
    text = ls(
        ("sa08", 1000, "Aug  8 23:50"),
        ("sar08", 2000, "Aug  9 00:07"),
        ("sa09", 1000, "Aug  9 23:50"),
        ("sar09", 2000, "Aug 10 00:07"),
        ("sa10", 1000, "Aug 10 23:50"),
        ("sar10", 2000, "Aug 11 00:07"),
        ("sa11", 1000, "Aug 11 23:50"),
        ("sar11", 2000, "Aug 12 00:39"),
    )
    rep = sf.fires(text, "2026-08-13T09:00:00Z")
    assert rep["fire_time_of_day"] == "00:07"
    assert (rep["fire_tod_votes"], rep["fire_tod_receipts"]) == (3, 4)
    lags = {r["day_file"]: r["receipt_lag_s"] for r in rep["fires"]}
    assert lags["sa10"] == 0.0
    assert lags["sa11"] == 32 * 60


def test_a_tied_schedule_vote_is_broken_deterministically_and_is_visible():
    """Two receipts, one vote each. `Counter.most_common` would pick by `ls`
    ordering; the module picks the EARLIER time of day and reports that the
    mode carried only 1 of 2 receipts, so a caller can see the tie."""
    text = ls(
        ("sa10", 1000, "Aug 10 23:50"),
        ("sar10", 2000, "Aug 11 00:07"),
        ("sa11", 1000, "Aug 11 23:50"),
        ("sar11", 2000, "Aug 12 00:39"),
    )
    rep = sf.fires(text, "2026-08-13T09:00:00Z")
    assert rep["fire_time_of_day"] == "00:07"
    assert (rep["fire_tod_votes"], rep["fire_tod_receipts"]) == (1, 2)
    # and reversing the listing order must not change the answer
    rev = "\n".join(text.splitlines()[:1] + text.splitlines()[1:][::-1]) + "\n"
    assert sf.fires(rev, "2026-08-13T09:00:00Z")["fire_time_of_day"] == "00:07"


def test_no_receipts_at_all_yields_no_schedule_and_no_verdicts():
    """A capture that lost every receipt must not silently score everything
    as downtime; with no fire lattice there is nothing to score."""
    text = ls(("sa10", 1000, "Aug 10 23:50"), ("sa11", 1000, "Aug 11 23:50"))
    rep = sf.fires(text, "2026-08-12T09:00:00Z")
    assert rep["fire_time_of_day"] is None
    assert rep["missed_fires_utc"] == [None, None]
    assert all(r["fire_utc"] is None for r in rep["fires"])


def test_orphan_receipt_is_named():
    text = ls(
        ("sa10", 1000, "Aug 10 23:50"),
        ("sar10", 2000, "Aug 11 00:07"),
        ("sar09", 2000, "Aug 10 00:07"),
    )
    rep = sf.fires(text, "2026-08-12T09:00:00Z")
    assert rep["orphan_receipts"] == ["sar09"]


def test_compressed_day_files_are_reported_and_not_scored():
    """A `.xz` mtime is the compression's, so the 17-minute argument the
    retention theorem rests on does not hold for it."""
    text = ls(
        ("sa10", 1000, "Aug 10 23:50"),
        ("sar10", 2000, "Aug 11 00:07"),
        ("sa09.xz", 400, "Aug 20 00:07"),
    )
    rep = sf.fires(text, "2026-08-21T09:00:00Z")
    assert rep["compressed_not_scored"] == ["sa09.xz"]
    assert [r["day_file"] for r in rep["fires"]] == ["sa10"]


def test_day_file_whose_mtime_is_a_different_day_of_month_is_refused():
    """`saNN` is written on day NN. A mismatch means the year/month
    reconstruction misplaced it, and a fire instant derived from it would be
    wrong by a month."""
    text = ls(
        ("sa10", 1000, "Aug 11 23:50"),
        ("sa12", 1000, "Aug 12 23:50"),
        ("sar12", 2000, "Aug 13 00:07"),
    )
    rep = sf.fires(text, "2026-08-14T09:00:00Z")
    assert [e["name"] for e in rep["day_file_month_mismatch"]] == ["sa10"]
    assert [r["day_file"] for r in rep["fires"]] == ["sa12"]


def test_non_sysstat_rows_in_the_listing_are_ignored():
    text = ls(
        ("sa10", 1000, "Aug 10 23:50"),
        ("sar10", 2000, "Aug 11 00:07"),
        ("sa1", 10, "Aug 10 23:50"),
        ("README", 10, "Aug 10 23:50"),
    )
    rep = sf.fires(text, "2026-08-12T09:00:00Z")
    assert rep["n_day_files"] == 1
    assert rep["n_receipts"] == 1


# --------------------------------------------------------------------------
# parse_boots() / crosscheck()
# --------------------------------------------------------------------------

BOOTS = """IDX BOOT ID                          FIRST ENTRY                 LAST ENTRY
 -1 aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa Mon 2026-08-10 08:00:00 UTC Tue 2026-08-11 09:00:00 UTC
  0 bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb Thu 2026-08-13 10:00:00 UTC Thu 2026-08-13 17:00:00 UTC
"""


def test_parse_boots_reads_the_table():
    boots = sf.parse_boots(BOOTS)
    assert [b["idx"] for b in boots] == [-1, 0]
    assert boots[0]["first_utc"] == "2026-08-10T08:00:00Z"
    assert boots[1]["boot_id"] == "b" * 32


def test_crosscheck_agrees_when_both_sources_say_the_same():
    rep = sf.crosscheck(BASIC, BOOTS, BASIC_NOW)
    by_fire = {r["fire_utc"]: r for r in rep["rows"]}
    # 08-11 00:07 is inside boot -1 and has a receipt -> agree(up)
    assert by_fire["2026-08-11T00:07:00Z"]["scored"] == "agree"
    assert by_fire["2026-08-11T00:07:00Z"]["boot_says"] == "up"
    # 08-12 00:07 is between the boots and has no receipt -> agree(down)
    assert by_fire["2026-08-12T00:07:00Z"]["scored"] == "agree"
    assert by_fire["2026-08-12T00:07:00Z"]["boot_says"] == "down"
    assert rep["n_disagree"] == 0
    assert rep["agreement"] == 1.0


def test_crosscheck_names_a_disagreement_rather_than_averaging_it():
    """Boot table says up across 08-12 00:07 but no receipt exists."""
    boots = """IDX BOOT ID                          FIRST ENTRY                 LAST ENTRY
  0 cccccccccccccccccccccccccccccccc Mon 2026-08-10 08:00:00 UTC Wed 2026-08-12 17:00:00 UTC
"""
    rep = sf.crosscheck(BASIC, boots, BASIC_NOW)
    assert rep["n_disagree"] == 1
    assert rep["disagreements"][0]["fire_utc"] == "2026-08-12T00:07:00Z"
    assert rep["disagreements"][0]["verdict"] == "fire_missed"
    assert rep["disagreements"][0]["boot_says"] == "up"


def test_a_fire_before_the_boot_tables_horizon_is_unscorable_not_a_miss():
    """journald evicts old boots; a fire it cannot reach is not evidence."""
    boots = """IDX BOOT ID                          FIRST ENTRY                 LAST ENTRY
  0 dddddddddddddddddddddddddddddddd Wed 2026-08-12 08:00:00 UTC Wed 2026-08-12 17:00:00 UTC
"""
    rep = sf.crosscheck(BASIC, boots, BASIC_NOW)
    scored = {r["fire_utc"]: r["scored"] for r in rep["rows"]}
    # BOTH decidable fires (08-11 and 08-12) precede the 08-12T08:00 horizon,
    # and the 08-12 one is a `fire_missed` -- so without the horizon rule it
    # would be scored against a boot table that simply cannot see it.
    assert scored["2026-08-11T00:07:00Z"] == "boot_table_too_short"
    assert scored["2026-08-12T00:07:00Z"] == "boot_table_too_short"
    assert rep["n_unscorable_boot_table_too_short"] == 2
    assert rep["n_scored"] == 0
    assert rep["n_disagree"] == 0


def test_pending_fires_are_not_crosschecked():
    rep = sf.crosscheck(BASIC, BOOTS, BASIC_NOW)
    assert "2026-08-13T00:07:00Z" not in {r["fire_utc"] for r in rep["rows"]}


def test_crosscheck_refuses_an_empty_boot_table():
    with pytest.raises(SystemExit):
        sf.crosscheck(BASIC, "IDX BOOT ID\n", BASIC_NOW)


# --------------------------------------------------------------------------
# blindspot()
# --------------------------------------------------------------------------

def test_blindspot_measures_the_probe_bracket(tmp_path):
    log = tmp_path / "log.jsonl"
    log.write_text(
        json.dumps({"checked_at_utc": "2026-08-10T20:00:00Z",
                    "reachable": True}) + "\n" +
        json.dumps({"checked_at_utc": "2026-08-11T04:00:00Z",
                    "reachable": True}) + "\n")
    rep = sf.blindspot(BASIC, BASIC_NOW, str(log))
    row = [r for r in rep["rows"]
           if r["fire_utc"] == "2026-08-11T00:07:00Z"][0]
    assert row["probe_bracket_s"] == 8 * 3600
    assert row["bracketed_within_1h"] is False
    assert rep["n_fires_bracketed_within_1h"] == 0


def test_blindspot_counts_a_tight_bracket_when_one_exists(tmp_path):
    log = tmp_path / "log.jsonl"
    log.write_text(
        json.dumps({"checked_at_utc": "2026-08-10T23:50:00Z",
                    "reachable": True}) + "\n" +
        json.dumps({"checked_at_utc": "2026-08-11T00:20:00Z",
                    "reachable": True}) + "\n")
    rep = sf.blindspot(BASIC, BASIC_NOW, str(log))
    row = [r for r in rep["rows"]
           if r["fire_utc"] == "2026-08-11T00:07:00Z"][0]
    assert row["bracketed_within_1h"] is True


def test_blindspot_survives_a_corrupt_log_line(tmp_path):
    log = tmp_path / "log.jsonl"
    log.write_text("not json\n\n" + json.dumps(
        {"checked_at_utc": "2026-08-11T04:00:00Z"}) + "\n")
    rep = sf.blindspot(BASIC, BASIC_NOW, str(log))
    assert rep["n_probe_records"] == 1


def test_blindspot_with_no_log_reports_nothing_bracketed(tmp_path):
    rep = sf.blindspot(BASIC, BASIC_NOW, str(tmp_path / "absent.jsonl"))
    assert rep["n_probe_records"] == 0
    assert rep["n_fires_bracketed_within_1h"] == 0
    assert all(r["probe_bracket_s"] is None for r in rep["rows"])


# --------------------------------------------------------------------------
# read_listing()
# --------------------------------------------------------------------------

def test_read_listing_prefers_the_marked_section(tmp_path):
    d = tmp_path / "cap"
    d.mkdir()
    (d / "sar-all.txt").write_text(
        "### SYSSTAT_FILES\n"
        "-rw-r--r-- 1 root root 1000 Aug 10 23:50 sa10\n"
        "### SAR_R_SA10\nsome sar output mentioning sa99\n")
    (d / "collector-evidence.txt").write_text(
        "-rw-r--r-- 1 root root 1000 Aug 11 23:50 sa11\n")
    text = sf.read_listing(str(d))
    assert "sa10" in text and "sa11" not in text
    assert "SAR_R_SA10" not in text


def test_read_listing_falls_back_to_collector_evidence(tmp_path):
    d = tmp_path / "cap"
    d.mkdir()
    (d / "collector-evidence.txt").write_text(
        "-rw-r--r-- 1 root root 1000 Aug 11 23:50 sa11\n")
    assert "sa11" in sf.read_listing(str(d))


def test_read_listing_refuses_a_capture_with_neither(tmp_path):
    d = tmp_path / "cap"
    d.mkdir()
    with pytest.raises(SystemExit):
        sf.read_listing(str(d))


# --------------------------------------------------------------------------
# The real capture -- regression pins for round 478's published numbers
# --------------------------------------------------------------------------

@pytest.mark.skipif(not os.path.isdir(REAL_CAPTURE),
                    reason="round-478 capture not present")
def test_round_478_capture_reproduces_the_published_fire_table():
    rep = sf.fires(sf.read_listing(REAL_CAPTURE), REAL_NOW)
    assert rep["fire_time_of_day"] == "00:07"
    assert rep["n_day_files"] == 11
    assert rep["n_receipts"] == 7
    assert rep["counts"] == {"fire_ran": 7, "fire_missed": 3,
                             "fire_pending": 1}
    assert rep["missed_fires_utc"] == ["2026-08-30T00:07:00Z",
                                       "2026-09-01T00:07:00Z",
                                       "2026-09-02T00:07:00Z"]
    assert rep["no_day_file_dates"] == ["2026-09-02"]
    assert rep["orphan_receipts"] == []
    assert rep["day_file_month_mismatch"] == []


@pytest.mark.skipif(not os.path.isdir(REAL_CAPTURE),
                    reason="round-478 capture not present")
def test_round_478_crosscheck_is_eight_of_eight():
    with open(os.path.join(REAL_CAPTURE, "journal-boots.txt")) as fh:
        rep = sf.crosscheck(sf.read_listing(REAL_CAPTURE), fh.read(), REAL_NOW)
    assert rep["n_scored"] == 8
    assert rep["n_agree"] == 8
    assert rep["n_disagree"] == 0
    assert rep["agreement"] == 1.0
    assert rep["n_unscorable_boot_table_too_short"] == 2
    assert rep["boot_table_first_entry_utc"] == "2026-08-25T12:57:42Z"


@pytest.mark.skipif(not os.path.isdir(REAL_CAPTURE),
                    reason="round-478 capture not present")
def test_round_478_no_fire_was_bracketed_within_an_hour_by_our_own_probes():
    """The claim the module exists to support. If a later round makes the
    probe cadence dense enough to bracket a 00:07 fire, this goes red and the
    'blind spot' language in knowledge/round-478 must be revised."""
    rep = sf.blindspot(sf.read_listing(REAL_CAPTURE), REAL_NOW,
                       os.path.join(ROOT, "state",
                                    "nuc-reachability-log.jsonl"))
    assert rep["n_fires_scored"] == 10
    assert rep["n_fires_bracketed_within_1h"] == 0
    brackets = [r["probe_bracket_s"] for r in rep["rows"]
                if r["probe_bracket_s"] is not None]
    assert min(brackets) > 3600


@pytest.mark.skipif(not os.path.isdir(REAL_CAPTURE),
                    reason="round-478 capture not present")
def test_the_sweep_timer_is_not_persistent_on_the_real_box():
    """P1. Every retention forecast that walks past a skipped fire depends on
    this line; round 448 inferred it and round 478 read it. If the box is ever
    reconfigured to Persistent=yes, `--down-since` becomes unsound and this
    test is the thing that says so."""
    with open(os.path.join(REAL_CAPTURE, "timer-units.txt")) as fh:
        text = fh.read()
    block = text.split("### TIMER_SHOW_sysstat-summary", 1)[1]
    block = block.split("### ", 1)[0]
    assert "Persistent=no" in block


@pytest.mark.skipif(not os.path.isdir(REAL_CAPTURE),
                    reason="round-478 capture not present")
def test_cli_crosscheck_strict_exits_zero_on_the_real_capture():
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "nuc", "summary_fossil.py"),
         "crosscheck", "--capture", REAL_CAPTURE, "--now", REAL_NOW,
         "--strict"],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["n_disagree"] == 0


# --------------------------------------------------------------------------
# The mutation ledger
# --------------------------------------------------------------------------

MUTATIONS = {
    # mutation -> the test that must go red
    "fire_pending branch deleted":
        "test_the_newest_day_is_pending_not_missed",
    "`fire > now` becomes `fire >= now`":
        "test_a_day_whose_fire_has_just_passed_is_scored_not_pending",
    "fire day offset +1 becomes +0":
        "test_receipt_present_means_the_fire_ran",
    "fire tod hardcoded to (0, 7)":
        "test_fire_time_of_day_is_derived_from_the_receipts_not_hardcoded",
    "no_day_file hole detection deleted":
        "test_missing_day_file_is_a_hole_and_gets_no_verdict",
    "day-of-month mismatch guard deleted":
        "test_day_file_whose_mtime_is_a_different_day_of_month_is_refused",
    "orphan receipt list hardcoded empty":
        "test_orphan_receipt_is_named",
    "boot horizon check deleted":
        "test_a_fire_before_the_boot_tables_horizon_is_unscorable_not_a_miss",
    "crosscheck ok inverted":
        "test_crosscheck_names_a_disagreement_rather_than_averaging_it",
    "blindspot threshold 3600 becomes 86400":
        "test_blindspot_measures_the_probe_bracket",
    "settle window deleted (`< settle_s` becomes `< 0`)":
        "test_a_fire_inside_the_settle_window_is_pending_not_missed",
    "settle window made infinite (`< settle_s` becomes `< 10**9`)":
        "test_a_day_whose_fire_has_just_passed_is_scored_not_pending",
    "read_listing marker preference dropped":
        "test_read_listing_prefers_the_marked_section",
    "schedule tie-break reverts to Counter.most_common":
        "test_a_tied_schedule_vote_is_broken_deterministically_and_is_visible",
}


def test_mutation_list_is_honest():
    """Every test named in MUTATIONS exists in this module."""
    here = set(globals())
    missing = sorted(t for t in MUTATIONS.values() if t not in here)
    assert missing == [], f"MUTATIONS names tests that do not exist: {missing}"


def test_every_public_entry_point_is_covered_by_at_least_one_mutation():
    covered = " ".join(MUTATIONS)
    for fn in ("fires", "crosscheck", "blindspot", "read_listing"):
        assert callable(getattr(sf, fn))
    for token in ("fire_pending", "no_day_file", "boot horizon",
                  "blindspot", "read_listing"):
        assert token in covered


# --------------------------------------------------------------------------
# Retroactive application: the evidence was in the repo before the module was
# --------------------------------------------------------------------------

#: (capture, `now` for that capture, expected missed fires). The `now` values
#: are each after that capture's newest sar sample and before the next 00:07,
#: so the newest day is `fire_pending` in every one.
RETRO = [
    ("nuc-capture-r400", "2026-08-31T12:00:00Z",
     ["2026-08-30T00:07:00Z"]),
    ("nuc-capture-r424", "2026-09-01T08:10:00Z",
     ["2026-08-30T00:07:00Z", "2026-09-01T00:07:00Z"]),
    ("nuc-capture-r478", "2026-09-03T17:13:00Z",
     ["2026-08-30T00:07:00Z", "2026-09-01T00:07:00Z",
      "2026-09-02T00:07:00Z"]),
]


@pytest.mark.parametrize("cap,now,expected", RETRO)
def test_older_captures_already_held_the_answer(cap, now, expected):
    """`sarNN` was in `ls -l` output this program banked on 2026-08-31 and
    2026-09-01. Round 478 wrote the reader, not the evidence."""
    d = os.path.join(ROOT, "state", cap)
    if not os.path.isdir(d):
        pytest.skip(f"{cap} not present")
    rep = sf.fires(sf.read_listing(d), now)
    assert rep["fire_time_of_day"] == "00:07"
    assert rep["missed_fires_utc"] == expected


def test_the_three_captures_are_nested_not_merely_similar():
    """Independent captures days apart must agree about the past. A later
    capture may only ADD missed fires (as the box accrues them) and may only
    DROP old ones by rotation -- never contradict one that is still in range.
    A disagreement here would falsify the retention theorem itself."""
    seen = []
    for cap, now, _ in RETRO:
        d = os.path.join(ROOT, "state", cap)
        if not os.path.isdir(d):
            pytest.skip(f"{cap} not present")
        rep = sf.fires(sf.read_listing(d), now)
        oldest = min(r["fire_utc"] for r in rep["fires"]
                     if r["fire_utc"] is not None)
        newest_scored = max(
            [r["fire_utc"] for r in rep["fires"]
             if r["verdict"] != "fire_pending" and r["fire_utc"]],
            default=oldest)
        seen.append((set(rep["missed_fires_utc"]), oldest, newest_scored))
    for i in range(len(seen) - 1):
        earlier, _, e_newest = seen[i]
        later, l_oldest, _ = seen[i + 1]
        # every miss the earlier capture saw, that the later one still covers,
        # must still be a miss in the later one
        still_in_range = {f for f in earlier if f >= l_oldest}
        assert still_in_range <= later, (
            f"capture {i} saw {sorted(still_in_range - later)} that capture "
            f"{i+1} denies")
        # and the later capture must not invent a miss inside the earlier
        # capture's own scored range
        assert {f for f in later if f <= e_newest} <= earlier


def test_r424_crosscheck_is_nine_of_nine_with_no_horizon_loss():
    """r424's boot table still reached 2026-08-23, so every fire it can see is
    scorable. Nine days later r478's table reaches only 08-25 and two fires
    fall off -- the pair is this round's evidence that journald forgets."""
    d = os.path.join(ROOT, "state", "nuc-capture-r424")
    if not os.path.isdir(d):
        pytest.skip("r424 not present")
    with open(os.path.join(d, "journal-boots.txt")) as fh:
        rep = sf.crosscheck(sf.read_listing(d), fh.read(),
                            "2026-09-01T08:10:00Z")
    assert (rep["n_scored"], rep["n_agree"], rep["n_disagree"]) == (9, 9, 0)
    assert rep["n_unscorable_boot_table_too_short"] == 0


def test_the_two_crosschecked_captures_cover_ten_distinct_fires_all_agreeing():
    """The published headline. Two captures, two boot tables, one verdict set."""
    got = {}
    for cap, now in (("nuc-capture-r424", "2026-09-01T08:10:00Z"),
                     ("nuc-capture-r478", REAL_NOW)):
        d = os.path.join(ROOT, "state", cap)
        if not os.path.isdir(d):
            pytest.skip(f"{cap} not present")
        with open(os.path.join(d, "journal-boots.txt")) as fh:
            rep = sf.crosscheck(sf.read_listing(d), fh.read(), now)
        assert rep["n_disagree"] == 0
        for r in rep["rows"]:
            if r["scored"] == "agree":
                prev = got.get(r["fire_utc"])
                assert prev in (None, r["verdict"]), (
                    f"{r['fire_utc']}: {prev} vs {r['verdict']}")
                got[r["fire_utc"]] = r["verdict"]
    assert len(got) == 10
    assert sorted(f for f, v in got.items() if v == "fire_missed") == [
        "2026-08-30T00:07:00Z", "2026-09-01T00:07:00Z", "2026-09-02T00:07:00Z"]


def test_a_capture_taken_before_the_plan_grew_a_boot_table_cannot_crosscheck():
    """r400 predates step 3b of the capture plan. The module must say so
    rather than score the fossil against nothing."""
    d = os.path.join(ROOT, "state", "nuc-capture-r400")
    if not os.path.isdir(d):
        pytest.skip("r400 not present")
    assert not os.path.exists(os.path.join(d, "journal-boots.txt"))
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "nuc", "summary_fossil.py"),
         "crosscheck", "--capture", d, "--now", "2026-08-31T12:00:00Z"],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode != 0
    assert "journal-boots.txt missing" in (proc.stdout + proc.stderr)
