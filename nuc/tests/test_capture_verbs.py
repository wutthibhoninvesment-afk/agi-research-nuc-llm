#!/usr/bin/env python3
"""Falsifiers for round 508: the two verbs that could not read a capture, and
the battery entry that was not the channel its name said.

Three findings are pinned here, each by the test that would have caught it:

1. `reclaim`/`gap` took only a single hand-extracted `sar -B` table. Round 502
   recorded their failure against `state/nuc-record-union` as a property of
   that union ("the union's sar-all.txt is 120 sections"). It is a property of
   the VERBS: the identical raise comes from every capture in this repo,
   including `nuc-capture-r424`, the one every published number in this track
   was computed from.
2. `cost_ledger`'s refusal message said the threshold was missing "on this
   record" while `CHANNEL_MIN_BYTES` is a module constant the raise never
   reads a record to consult.
3. `survivor_impact.BATTERY`'s entry named `wsweep_swap` passed no `--channel`
   and `wsweep`'s default is `steal`, so it was a second copy of
   `wsweep_steal` -- byte-identical output. The battery advertised five verbs
   and ran four.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import perturbation as pt  # noqa: E402
import survivor_impact as si  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
PERT = os.path.join(ROOT, "nuc", "perturbation.py")
UNION = os.path.join(ROOT, "state", "nuc-record-union")
R424 = os.path.join(ROOT, "state", "nuc-capture-r424")


def _run(*argv):
    return subprocess.run([sys.executable, PERT, *argv], capture_output=True,
                          text=True, cwd=ROOT)


def _union_sar():
    with open(os.path.join(UNION, "sar-all.txt"), encoding="utf-8") as fh:
        return fh.read()


# ------------------------------------------------- 1. the section walker

def test_capture_day_tables_finds_every_sar_b_day_of_the_union():
    days = pt.capture_day_tables(_union_sar(), "SAR_B_")
    assert len(days) == 12
    assert [d[0] for d in days] == sorted(d[0] for d in days)
    assert all(isinstance(t, pt.SarTable) for _d, _n, t in days)


def test_the_walker_dates_from_the_banner_not_from_the_section_name():
    days = pt.capture_day_tables(_union_sar(), "SAR_B_")
    for date, name, _t in days:
        assert name.endswith("SA%02d" % int(date[8:10]))
    # and the dates span more than one month, which a day-of-month name cannot
    assert len({d[:7] for d, _n, _t in days}) == 2


def test_a_section_whose_banner_disagrees_with_its_name_raises():
    text = ("### SAR_B_SA31\n"
            "Linux 6.8.0 (nuc)\t08/30/26\t_x86_64_\t(4 CPU)\n"
            "\n"
            "00:10:01\tpgpgin/s\tpgpgout/s\tfault/s\tmajflt/s\tpgfree/s"
            "\tpgscank/s\tpgscand/s\tpgsteal/s\t%vmeff\n"
            "00:10:01\t0.00\t0.00\t1.00\t0.00\t1.00\t0.00\t0.00\t0.00\t0.00\n")
    with pytest.raises(pt.PerturbationError) as e:
        pt.capture_day_tables(text, "SAR_B_")
    assert "the file name says day 31" in str(e.value)


def test_the_walker_returns_nothing_for_a_prefix_the_capture_lacks():
    assert pt.capture_day_tables(_union_sar(), "SAR_NOSUCH_") == []


# --------------------------------------- 2. the regression that was blamed
#                                            on the union

@pytest.mark.parametrize("capture", ["nuc-capture-r400", "nuc-capture-r424",
                                     "nuc-capture-r478", "nuc-capture-r484",
                                     "nuc-record-union"])
def test_sar_b_on_a_whole_capture_still_raises_and_it_is_not_the_union(capture):
    """The old call, kept as a pin. Every record fails, not just the union."""
    path = os.path.join(ROOT, "state", capture, "sar-all.txt")
    if not os.path.exists(path):
        pytest.skip("no sar in %s" % capture)
    r = _run("reclaim", "--sar-b", path)
    assert r.returncode == 1
    assert "header changed mid-table" in r.stderr


def test_reclaim_reads_the_union_by_capture():
    r = _run("reclaim", "--capture", UNION)
    assert r.returncode == 0, r.stderr[-400:]
    out = json.loads(r.stdout)
    assert out["pooled"]["n_days"] == 12
    assert len(out["days"]) == 12


def test_reclaim_reads_r424_too_the_capture_the_track_published_from():
    r = _run("reclaim", "--capture", R424)
    assert r.returncode == 0, r.stderr[-400:]
    assert json.loads(r.stdout)["pooled"]["n_days"] == 10


def test_reclaim_one_day_is_a_subset_of_the_pooled_run():
    one = json.loads(_run("reclaim", "--capture", UNION,
                          "--date", "2026-08-31").stdout)
    every = json.loads(_run("reclaim", "--capture", UNION).stdout)
    assert one["pooled"]["n_days"] == 1
    match = [d for d in every["days"] if d["date"] == "2026-08-31"]
    assert one["days"] == match


def test_a_date_the_capture_does_not_hold_is_an_error_naming_what_it_holds():
    r = _run("reclaim", "--capture", UNION, "--date", "2026-09-02")
    assert r.returncode != 0
    assert "2026-08-31" in r.stderr and "holds no SAR_B_" in r.stderr


def test_capture_and_sar_b_are_exclusive():
    r = _run("reclaim", "--capture", UNION, "--sar-b", "/dev/null")
    assert r.returncode != 0 and "exclusive" in r.stderr


def test_reclaim_with_neither_input_says_so():
    r = _run("reclaim")
    assert r.returncode != 0 and "--capture" in r.stderr


def test_gap_reads_the_union_and_pairs_every_day_by_date():
    r = _run("gap", "--capture", UNION, "--channel", "commit")
    assert r.returncode == 0, r.stderr[-400:]
    out = json.loads(r.stdout)
    assert out["dates_without_a_level_table"] == []
    assert all("date" in row for row in out["rows"])
    assert out["summary"]["n_rows"] == len(out["rows"])


def test_gap_with_only_one_of_the_two_files_is_an_error():
    r = _run("gap", "--sar-b", "/dev/null")
    assert r.returncode != 0 and "--sar-b and" in r.stderr


# ------------------------------------------------------ 3. pooling honestly

def _day(date, buckets, loud, kinds, stolen=0, pin=0, pout=0, ses=0, sfs=0,
         largest=None):
    return {"date": date, "n_buckets": buckets, "n_reclaim_buckets": loud,
            "by_kind": kinds, "total_scanned_pages": 0,
            "total_stolen_pages": 0, "total_stolen_bytes": stolen,
            "total_paged_in_kb": pin, "total_paged_out_kb": pout,
            "n_steal_exceeds_scan": ses, "n_scan_free_steal": sfs,
            "largest_bucket": largest}


def test_pooled_counts_are_sums_and_the_fraction_uses_the_pooled_denominator():
    p = pt.reclaim_pooled([_day("A", 100, 5, {"quiet": 95, "kswapd": 5}),
                           _day("B", 100, 15, {"quiet": 85, "kswapd": 15})])
    assert p["n_buckets"] == 200 and p["n_reclaim_buckets"] == 20
    assert p["reclaim_bucket_fraction"] == 0.1
    assert p["by_kind"] == {"quiet": 180, "kswapd": 20}


def test_pooled_direct_counts_mixed_as_direct():
    p = pt.reclaim_pooled([_day("A", 10, 3, {"direct": 1, "mixed": 2})])
    assert p["n_direct_reclaim_buckets"] == 3


def test_a_day_with_no_reclaim_is_named_not_averaged_away():
    p = pt.reclaim_pooled([_day("A", 50, 0, {"quiet": 50}),
                           _day("B", 50, 2, {"quiet": 48, "kswapd": 2})])
    assert p["days_with_no_reclaim"] == ["A"]


def test_the_largest_bucket_carries_the_day_it_came_from():
    p = pt.reclaim_pooled([
        _day("A", 10, 1, {}, largest={"stolen_bytes": 5, "time": "01:00:00"}),
        _day("B", 10, 1, {}, largest={"stolen_bytes": 9, "time": "02:00:00"})])
    assert p["largest_bucket"]["stolen_bytes"] == 9
    assert p["largest_bucket_date"] == "B"


def test_pooling_a_day_whose_largest_is_none_does_not_crash():
    p = pt.reclaim_pooled([_day("A", 10, 0, {}, largest=None),
                           _day("B", 10, 1, {},
                                largest={"stolen_bytes": 1, "time": "0"})])
    assert p["largest_bucket_date"] == "B"


def test_pooling_nothing_reports_no_fraction_rather_than_zero():
    p = pt.reclaim_pooled([])
    assert p["n_days"] == 0 and p["reclaim_bucket_fraction"] is None
    assert p["largest_bucket"] is None


def test_an_undefined_level_cost_is_not_counted_as_a_zero_one():
    s = pt.eviction_gap_pooled([
        {"level_bytes": None, "ratio": None},
        {"level_bytes": 0, "ratio": 0.0},
        {"level_bytes": 10, "ratio": 2.0}])
    assert s["n_rows"] == 3 and s["n_level_undefined"] == 1
    assert s["n_level_defined"] == 2 and s["n_level_zero"] == 1
    assert s["fraction_level_zero"] == 0.5


def test_the_median_ratio_of_an_even_number_of_rows_is_the_mean_of_the_middle():
    s = pt.eviction_gap_pooled([{"level_bytes": 1, "ratio": r}
                                for r in (1.0, 2.0, 3.0, 6.0)])
    assert s["median_ratio"] == 2.5 and s["max_ratio"] == 6.0


def test_gap_pooled_on_nothing_reports_none_not_zero():
    s = pt.eviction_gap_pooled([])
    assert s["fraction_level_zero"] is None and s["median_ratio"] is None


# ------------------------------- 4. the refusal that blamed the record

def test_the_missing_threshold_message_names_the_constant_not_the_record():
    table = pt.parse_sar(
        "Linux 6.8.0 (nuc)\t08/31/26\t_x86_64_\t(4 CPU)\n"
        "\n"
        "00:10:01\tkbmemfree\tkbavail\tkbcommit\n"
        "00:10:01\t1.0\t2.0\t3.0\n")
    with pytest.raises(pt.PerturbationError) as e:
        pt.cost_ledger([], table, "2026-08-31", channel=pt.COMMIT_CHANNEL)
    msg = str(e.value)
    assert "CHANNEL_MIN_BYTES" in msg and "MODULE CONSTANT" in msg
    assert "no derived costly-threshold on this record" not in msg


def test_the_refusal_is_lifted_by_a_flag_that_already_existed():
    r = _run("window", "--capture", UNION, "--channel", "commit",
             "--min-bytes", str(pt.LEDGER_MIN_BYTES))
    assert r.returncode == 0, r.stderr[-400:]
    assert json.loads(r.stdout)["frame"]["channel"] == "commit"


# --------------------------------------- 5. the battery that ran one verb
#                                             twice

def test_no_two_battery_entries_are_the_same_command():
    seen = {}
    for name, argv in si.BATTERY:
        key = tuple(argv)
        assert key not in seen, (
            "%s and %s are the same command; one of them is measuring "
            "nothing new" % (seen[key], name))
        seen[key] = name


def test_every_battery_entry_that_can_take_a_channel_names_one():
    """The defect was a DEFAULT, so relying on any default is the bug class.

    `wsweep` defaults to `steal` and ten of its sibling subcommands default to
    `swap`; a battery entry that omits the flag is asserting a default it did
    not check."""
    takes_channel = {"window", "wsweep", "population", "gap"}
    for name, argv in si.BATTERY:
        if argv[0] in takes_channel:
            assert "--channel" in argv, (
                "%s runs `%s` without naming a channel" % (name, argv[0]))


def test_the_battery_names_the_swap_channel_at_least_once():
    chans = [argv[argv.index("--channel") + 1] for _n, argv in si.BATTERY
             if "--channel" in argv]
    assert "swap" in chans and "commit" in chans and "steal" in chans


def test_wsweep_still_defaults_to_steal_so_the_pin_stays_meaningful():
    """Not a wish: if somebody 'fixes' the default the guard above goes quiet.

    This test says out loud that the default is what it is, so a change to it
    is a decision somebody makes here rather than a silent re-interpretation
    of every argv in the repo."""
    r = _run("wsweep", "--capture", UNION)
    assert r.returncode == 0, r.stderr[-400:]
    assert json.loads(r.stdout)["frame"]["channel"] == "steal"


def test_reclaim_and_gap_are_no_longer_recorded_as_unreachable():
    assert "reclaim" not in si.BATTERY_GAP and "gap" not in si.BATTERY_GAP
    names = [n for n, _a in si.BATTERY]
    assert "reclaim_all" in names and "gap_commit" in names


def test_the_two_window_exclusions_no_longer_blame_the_record():
    for key in ("window_commit", "window_steal"):
        why = si.BATTERY_GAP[key]
        assert "CHANNEL_MIN_BYTES" in why
        assert "on this record" not in why


# ---------------------------------------- 6. the refactor changed nothing

def test_window_frame_is_unchanged_by_the_shared_section_walker():
    with open(os.path.join(UNION, "journal-pid1-full.txt"),
              encoding="utf-8") as fh:
        jrnl = fh.read()
    frame = pt.window_frame(_union_sar(), jrnl)
    # The numbers round 490 published from this record, re-derived.
    assert frame["n_sections_total"] == 120
    assert frame["n_day_files"] == 12
    assert frame["section_prefix"] == "SAR_W_"
