"""Tests for `nuc/sysstat_archive.py` (round 400).

Two layers, deliberately:

* inline fixtures for every rule and every edge, so the semantics are pinned
  independently of any capture file;
* a small number of tests against round 400's frozen capture
  (`state/nuc-capture-r400/sar-all.txt`), which SKIP if it is absent.

The frozen capture is a round artifact and will not change -- unlike
`state/nuc-reachability-log.jsonl`, which every E-round appends to. Round 340
lost a round to pinning a count against an append-only file; the split here is
that lesson applied.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from nuc.sysstat_archive import (  # noqa: E402
    ArchiveError, DayArchive, SAMPLE_INTERVAL_S, availability, banner_date,
    cross_check, load_episodes, multiday_steps, parse_capture, parse_day,
    split_capture, witness_probe_gaps, _is_rollover,
)

CAPTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "state", "nuc-capture-r400", "sar-all.txt")

BANNER = "Linux 6.8.0-138-generic (pgain-nuc) \t08/30/26 \t_x86_64_\t(4 CPU)"


def _day(date_mmddyy, rows, restarts=()):
    """Build a minimal `sar -r`-shaped table for one day."""
    out = [f"Linux 6.8.0-138-generic (pgain-nuc) \t{date_mmddyy} \t_x86_64_\t(4 CPU)", ""]
    for r in restarts:
        out.append(f"{r}     LINUX RESTART\t(4 CPU)")
        out.append("")
    out.append("00:00:05    kbmemfree   kbavail kbmemused  %memused kbbuffers"
               "  kbcached  kbcommit   %commit  kbactive   kbinact   kbdirty")
    for t, commit in rows:
        out.append(f"{t}     22412620  27286376   4975972     15.19     53824"
                   f"   5195472   {commit}     14.77   5071684   4960992         0")
    return "\n".join(out)


# ------------------------------------------------------------------ parsing


def test_banner_date_reads_the_files_own_date_not_the_callers():
    assert banner_date(BANNER) == "2026-08-30"


def test_banner_date_accepts_four_digit_years():
    assert banner_date(BANNER.replace("08/30/26", "08/30/2026")) == "2026-08-30"


def test_banner_date_raises_rather_than_guessing():
    with pytest.raises(ArchiveError, match="22-hour outage"):
        banner_date("no banner here at all")


def test_parse_day_lifts_samples_and_restarts_to_utc_instants():
    d = parse_day(_day("08/30/26", [("00:50:05", 5455308), ("01:00:05", 5459568)],
                       restarts=("00:32:34",)))
    assert d.date == "2026-08-30"
    assert [s.strftime("%H:%M:%S") for s in d.samples] == ["00:50:05", "01:00:05"]
    assert [r.strftime("%H:%M:%S") for r in d.restarts] == ["00:32:34"]
    assert d.first.day == 30 and d.last.hour == 1


def test_split_capture_keeps_only_the_requested_prefix():
    text = "### SAR_R_SA30\na\n### SAR_W_SA30\nb\n### SAR_B_SA30\nc\n"
    assert set(split_capture(text, "SAR_R_")) == {"SAR_R_SA30"}
    assert set(split_capture(text, "SAR_")) == {"SAR_R_SA30", "SAR_W_SA30",
                                                "SAR_B_SA30"}


def test_parse_capture_deduplicates_by_date_not_by_section_name():
    """`SAR_R_SA30` and `SAR_W_SA30` are ONE day. Counting both would double
    every gap statistic in the report."""
    r = _day("08/30/26", [("00:50:05", 1), ("01:00:05", 2), ("01:10:05", 3)])
    w = _day("08/30/26", [("00:50:05", 1)])
    days = parse_capture(f"### SAR_R_SA30\n{r}\n### SAR_W_SA30\n{w}\n", "SAR_")
    assert len(days) == 1
    assert len(days[0].samples) == 3          # the richer of the two, not the last


def test_parse_capture_orders_days_ascending():
    text = ("### SAR_R_SA31\n" + _day("08/31/26", [("00:10:05", 1)]) +
            "\n### SAR_R_SA30\n" + _day("08/30/26", [("00:50:05", 1)]) + "\n")
    assert [d.date for d in parse_capture(text)] == ["2026-08-30", "2026-08-31"]


# ------------------------------------------------------------- availability


def _six(start_h=1):
    return [(f"{start_h + i // 6:02d}:{(i % 6) * 10:02d}:05", 5_000_000 + i)
            for i in range(12)]


def test_contiguous_samples_produce_no_gaps():
    rep = availability([parse_day(_day("08/30/26", _six()))])
    assert rep["n_gaps"] == 0
    assert rep["n_samples"] == 12
    assert len(rep["up_intervals"]) == 1


def test_a_restart_inside_a_hole_dates_the_outage_end_exactly():
    rows = [("01:00:05", 1), ("01:10:05", 2), ("02:30:05", 3), ("02:40:05", 4)]
    rep = availability([parse_day(_day("08/30/26", rows), )])
    # no restart yet -> unexplained, not down
    assert rep["gaps"][0]["kind"] == "unexplained_gap"
    rep2 = availability([parse_day(_day("08/30/26", rows, restarts=("02:21:07",)))])
    g = rep2["gaps"][0]
    assert g["kind"] == "reboot"
    assert g["down_end_earliest_utc"] == g["down_end_latest_utc"] == \
        "2026-08-30T02:21:07Z"
    # start is bracketed to one sample interval, no wider and no narrower
    assert g["down_start_earliest_utc"] == "2026-08-30T01:10:05Z"
    assert g["down_start_latest_utc"] == "2026-08-30T01:20:05Z"


def test_two_restarts_in_one_hole_are_flagged_not_averaged():
    rows = [("00:20:03", 1), ("00:30:03", 2), ("01:00:06", 3), ("01:10:06", 4)]
    rep = availability([parse_day(_day("08/25/26", rows,
                                       restarts=("00:37:34", "00:47:30")))])
    g = rep["gaps"][0]
    assert len(g["restarts_utc"]) == 2
    assert "at least that many outages" in g["note"]
    assert g["down_end_earliest_utc"] == "2026-08-25T00:37:34Z"   # the FIRST


def test_a_missing_sample_that_is_not_at_midnight_stays_unexplained():
    """The rollover rule must not swallow a real one-sample outage."""
    rows = [("12:00:05", 1), ("12:10:05", 2), ("12:30:05", 3), ("12:40:05", 4)]
    rep = availability([parse_day(_day("08/30/26", rows))])
    assert rep["gaps"][0]["kind"] == "unexplained_gap"
    assert rep["n_rollover_gaps"] == 0


def test_a_two_slot_hole_across_midnight_is_not_a_rollover():
    """A real overnight outage straddles midnight too. Only the one-slot
    signature is the sysstat artefact."""
    a = parse_day(_day("08/30/26", [("23:40:05", 1), ("23:50:05", 2)]))
    b = parse_day(_day("08/31/26", [("00:20:05", 3), ("00:30:05", 4)]))
    rep = availability([a, b])
    assert rep["gaps"][0]["kind"] == "unexplained_gap"


def test_the_midnight_one_slot_hole_is_graded_rollover_and_named_as_such():
    a = parse_day(_day("08/30/26", [("23:40:05", 1), ("23:50:05", 2)]))
    b = parse_day(_day("08/31/26", [("00:10:05", 3), ("00:20:05", 4)]))
    rep = availability([a, b])
    g = rep["gaps"][0]
    assert g["kind"] == "rollover"
    assert "NOT downtime" in g["note"]
    assert rep["n_rollover_gaps"] == 1 and rep["n_unexplained_gaps"] == 0


def test_rollover_does_not_break_the_up_interval():
    """A displayed-sample artefact is not a loss of witness; splitting the
    interval there would fragment every day and understate coverage."""
    a = parse_day(_day("08/30/26", [("23:40:05", 1), ("23:50:05", 2)]))
    b = parse_day(_day("08/31/26", [("00:10:05", 3), ("00:20:05", 4)]))
    rep = availability([a, b])
    assert len(rep["up_intervals"]) == 1
    assert rep["up_intervals"][0]["from_utc"] == "2026-08-30T23:40:05Z"
    assert rep["up_intervals"][0]["to_utc"] == "2026-08-31T00:20:05Z"


def test_a_reboot_does_break_the_up_interval():
    rows = [("01:00:05", 1), ("01:10:05", 2), ("02:30:05", 3), ("02:40:05", 4)]
    rep = availability([parse_day(_day("08/30/26", rows, restarts=("02:21:07",)))])
    assert len(rep["up_intervals"]) == 2


def test_missed_slots_uses_rounding_not_floor():
    """A one-slot hole measures 1198 s as often as 1200 s: the real stamps
    drift. Floor division reported 0 missed slots for one and 1 for the other,
    for the same event."""
    a = parse_day(_day("08/27/26", [("23:40:04", 1), ("23:50:04", 2)]))
    b = parse_day(_day("08/28/26", [("00:10:02", 3), ("00:20:02", 4)]))
    rep = availability([a, b])
    assert rep["gaps"][0]["gap_s"] == 1198.0
    assert rep["gaps"][0]["missed_slots"] == 1
    assert rep["gaps"][0]["kind"] == "rollover"


def test_restart_before_the_first_sample_is_coverage_edge_not_downtime():
    d = parse_day(_day("08/23/26", [("14:20:03", 1), ("14:30:03", 2)],
                       restarts=("14:02:07",)))
    rep = availability([d])
    assert rep["gaps"][0]["kind"] == "coverage_edge"
    assert rep["n_reboot_gaps"] == 0


def test_availability_rejects_a_nonpositive_interval():
    with pytest.raises(ArchiveError):
        availability([parse_day(_day("08/30/26", _six()))], interval_s=0)


def test_empty_input_reports_nothing_rather_than_raising():
    assert availability([])["n_days"] == 0


def test_is_rollover_requires_all_three_conditions():
    from datetime import datetime, timezone
    a = datetime(2026, 8, 30, 23, 50, 5, tzinfo=timezone.utc)
    b = datetime(2026, 8, 31, 0, 10, 5, tzinfo=timezone.utc)
    assert _is_rollover(a, b, 1)
    assert not _is_rollover(a, b, 2)                       # two slots
    same = datetime(2026, 8, 30, 12, 10, 5, tzinfo=timezone.utc)
    assert not _is_rollover(datetime(2026, 8, 30, 11, 50, 5, tzinfo=timezone.utc),
                            same, 1)                       # no midnight


# --------------------------------------------------------------- crosscheck


def _streak(**kw):
    base = {"verdict": "down", "start_round": 1, "end_round": 2,
            "earliest_possible_start_utc": "2026-08-30T01:10:40Z",
            "latest_possible_end_utc": "2026-08-30T02:21:07Z"}
    base.update(kw)
    return base


def _reboot_report():
    rows = [("01:00:05", 1), ("01:10:05", 2), ("02:30:05", 3), ("02:40:05", 4)]
    return availability([parse_day(_day("08/30/26", rows, restarts=("02:21:07",)))])


def test_crosscheck_agrees_when_the_two_instruments_coincide():
    res = cross_check(_reboot_report(), [_streak()])
    assert len(res) == 1 and res[0]["verdict"] == "agrees"


def test_crosscheck_reports_a_conflict_when_the_boot_times_disagree():
    res = cross_check(_reboot_report(),
                      [_streak(latest_possible_end_utc="2026-08-30T02:40:00Z")])
    assert res[0]["verdict"] == "conflict"


def test_crosscheck_says_sar_tightens_when_it_witnessed_up_later():
    res = cross_check(_reboot_report(),
                      [_streak(earliest_possible_start_utc="2026-08-30T00:30:00Z")])
    assert res[0]["verdict"] == "sar_tightens"
    assert "01:10:05" in res[0]["detail"]


def test_crosscheck_calls_an_unmatched_gap_unknown_rather_than_agreeing():
    res = cross_check(_reboot_report(), [])
    assert res[0]["verdict"] == "unknown_to_log"


def test_crosscheck_skips_coverage_edges():
    d = parse_day(_day("08/23/26", [("14:20:03", 1), ("14:30:03", 2)],
                       restarts=("14:02:07",)))
    assert cross_check(availability([d]), []) == []


# ------------------------------------------------------- probe-gap closure


def test_witness_probe_gaps_closes_a_gap_the_archive_covers():
    rep = availability([parse_day(_day("08/30/26", _six()))])
    out = witness_probe_gaps(rep, [{"from_round": 1, "to_round": 2,
                                    "from_utc": "2026-08-30T01:10:00Z",
                                    "to_utc": "2026-08-30T01:40:00Z",
                                    "witnessed": False, "unobserved_s": 1800.0}])
    assert out[0]["verdict"] == "closed"
    assert out[0]["sar_uncovered_s"] == 0.0


def test_witness_probe_gaps_leaves_a_gap_open_when_the_archive_is_silent():
    rep = availability([parse_day(_day("08/30/26", _six()))])
    out = witness_probe_gaps(rep, [{"from_utc": "2026-08-29T01:00:00Z",
                                    "to_utc": "2026-08-29T02:00:00Z",
                                    "witnessed": False, "unobserved_s": 3600.0}])
    assert out[0]["verdict"] == "open"
    assert out[0]["sar_covered_s"] == 0.0


def test_witness_probe_gaps_reports_partial_coverage_as_partial():
    rep = availability([parse_day(_day("08/30/26", _six()))])
    out = witness_probe_gaps(rep, [{"from_utc": "2026-08-30T01:30:00Z",
                                    "to_utc": "2026-08-30T03:30:00Z",
                                    "witnessed": False, "unobserved_s": 7200.0}])
    assert out[0]["verdict"] == "partial"
    assert 0 < out[0]["sar_covered_s"] < out[0]["gap_s"]


def test_witness_probe_gaps_never_reports_more_coverage_than_the_gap():
    """Overlapping up-intervals must not sum past 100 %."""
    rep = availability([parse_day(_day("08/30/26", _six()))])
    out = witness_probe_gaps(rep, [{"from_utc": "2026-08-30T01:05:00Z",
                                    "to_utc": "2026-08-30T01:15:00Z",
                                    "witnessed": False, "unobserved_s": 600.0}])
    assert out[0]["sar_covered_s"] <= out[0]["gap_s"]
    assert out[0]["sar_uncovered_s"] >= 0.0


def test_witness_probe_gaps_ignores_a_degenerate_window():
    rep = availability([parse_day(_day("08/30/26", _six()))])
    assert witness_probe_gaps(rep, [{"from_utc": "2026-08-30T01:00:00Z",
                                     "to_utc": "2026-08-30T01:00:00Z"}]) == []


# ------------------------------------------------------------ memory steps


def test_multiday_steps_reports_releases_as_well_as_allocs():
    text = "### SAR_R_SA30\n" + _day("08/30/26", [
        ("01:00:05", 5_000_000), ("01:10:05", 25_000_000),
        ("01:20:05", 25_100_000), ("01:30:05", 5_000_000)]) + "\n"
    steps = multiday_steps(split_capture(text), min_step_kb=500_000)
    assert [s["direction"] for s in steps] == ["alloc", "release"]
    assert steps[0]["delta_kb"] == 20_000_000
    assert steps[1]["delta_kb"] == -20_100_000


def test_load_episodes_separates_the_model_load_from_the_per_request_steps():
    text = "### SAR_R_SA30\n" + _day("08/30/26", [
        ("13:20:05", 5_476_700), ("13:30:05", 23_472_692),
        ("13:40:05", 23_480_000), ("14:50:05", 23_484_980),
        ("15:00:05", 30_634_440)]) + "\n"
    eps = load_episodes(multiday_steps(split_capture(text), min_step_kb=500_000))
    assert len(eps) == 2                      # a >2-bucket quiet period splits them
    assert eps[0]["steps"][0]["delta_kb"] == 17_995_992
    assert eps[1]["steps"][0]["delta_kb"] == 7_149_460


def test_multiday_steps_flags_a_step_next_to_a_restart():
    text = "### SAR_R_SA30\n" + _day("08/30/26", [
        ("00:40:05", 5_000_000), ("00:50:05", 25_000_000)],
        restarts=("00:32:34",)) + "\n"
    steps = multiday_steps(split_capture(text), min_step_kb=500_000)
    assert steps[0]["near_restart"] is True

    # ...and NOT flagged once the step is more than two buckets from the boot.
    far = "### SAR_R_SA30\n" + _day("08/30/26", [
        ("01:00:05", 5_000_000), ("01:10:05", 25_000_000)],
        restarts=("00:32:34",)) + "\n"
    assert multiday_steps(split_capture(far), min_step_kb=500_000)[0][
        "near_restart"] is False


# --------------------------------------- round 400's frozen real capture


needs_capture = pytest.mark.skipif(not os.path.exists(CAPTURE),
                                   reason="round 400 capture not present")


@needs_capture
def test_real_capture_parses_nine_days_and_six_restarts():
    rep = availability(parse_capture(open(CAPTURE).read()))
    assert rep["n_days"] == 9
    assert rep["n_samples"] == 957
    assert rep["n_restarts"] == 6


@needs_capture
def test_real_capture_has_no_unexplained_gap_left():
    """Every hole in nine days of samples is a reboot, a rollover, or the
    retention edge. If a future capture reintroduces `unexplained_gap`, that is
    a FINDING -- a hole this module cannot name -- not a regression."""
    rep = availability(parse_capture(open(CAPTURE).read()))
    assert rep["n_unexplained_gaps"] == 0
    assert rep["n_rollover_gaps"] == 7
    assert rep["n_reboot_gaps"] == 4


@needs_capture
def test_every_rollover_in_the_real_capture_spans_a_midnight():
    """7 of 7 day boundaries the capture can observe. That ratio is why the
    rollover rule is a rule."""
    rep = availability(parse_capture(open(CAPTURE).read()))
    rolls = [g for g in rep["gaps"] if g["kind"] == "rollover"]
    assert len(rolls) == 7
    for g in rolls:
        assert g["after_utc"][8:10] != g["before_utc"][8:10]
        assert g["after_utc"].endswith("23:50:03Z") or "23:5" in g["after_utc"]


@needs_capture
def test_the_two_outages_this_track_recorded_are_both_in_the_archive():
    rep = availability(parse_capture(open(CAPTURE).read()))
    ends = {g["down_end_earliest_utc"] for g in rep["gaps"] if g["kind"] == "reboot"}
    assert "2026-08-27T11:50:53Z" in ends       # rounds 184-196
    assert "2026-08-30T00:32:34Z" in ends       # rounds 298-346
