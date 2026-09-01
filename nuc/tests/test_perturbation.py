"""Tests for nuc/perturbation.py (round 394).

The fixtures below are VERBATIM `sar` output captured from pgain-nuc on
2026-08-31, not hand-written samples. That matters: round 388 read `sar -W` and
`sar -B` from this same boot and recorded the 01:50-02:00 bucket as
"unexplained ... zero journald entries". Both halves were wrong -- there were
21 journal entries in that window, and the missing instrument was `sar -r`,
which nobody in this track had ever read. A test suite whose fixtures are
invented cannot reproduce that; one whose fixtures are the real bytes can.

Nothing here opens a socket or runs a command, so this file is safe to run from
any track and there is no path by which it can contact port 8001.
"""
import json
import subprocess
import sys

import pytest

from nuc import perturbation as pt


# ------------------------------------------------------------- fixtures
# `sar -r -f /var/log/sysstat/sa31`, buckets 01:30 through 04:10, captured
# 2026-08-31T09:13Z. The 02:00:05 row is the event round 388 could not explain.
SA31_R = """Linux 6.8.0-138-generic (pgain-nuc) \t08/31/26 \t_x86_64_\t(4 CPU)

00:00:05    kbmemfree   kbavail kbmemused  %memused kbbuffers  kbcached  kbcommit   %commit  kbactive   kbinact   kbdirty
01:30:05       296276   2033820  30187592     92.17    123648   1966992  30634440     82.92  19785452  12270744        24
01:40:03       292748   2031552  30189816     92.18    124552   1967364  30634440     82.92  19785468  12271988       124
01:50:05       292276   2032236  30189092     92.18    125448   1967596  30634440     82.92  19785412  12273128         8
02:00:05       390936   2067492  30153420     92.07    124120   1905372  30781532     83.31  19791500  12137688        20
02:10:05       394352   2072160  30148736     92.05    125024   1905712  30781532     83.31  19791500  12138924        92
02:20:05       395616   2074744  30146124     92.04    125920   1906140  30781532     83.31  19791524  12140104       168
02:30:05       405520   2086332  30134412     92.01    126832   1906936  30781532     83.31  19792216  12141376        16
03:50:05       412996   2104168  30115992     91.95    134116   1910256  30783280     83.32  19793404  12151252       188
04:00:03       530476   2294540  29925900     91.37     64448   2051432  30781660     83.31  20695024  11111204        84
04:10:05       534004   2299440  29920984     91.36     65344   2051904  30781660     83.31  20695032  11112564        92
Average:       395520   2089648  30131207     91.97    112035   1974907  30742204     83.20  20144686  12013897        82
"""

# `sar -W -f /var/log/sysstat/sa31`, non-zero rows only, plus the header.
SA31_W = """Linux 6.8.0-138-generic (pgain-nuc) \t08/31/26 \t_x86_64_\t(4 CPU)

00:00:05     pswpin/s pswpout/s
00:40:05         0.00      0.14
00:50:05         0.01      0.00
02:00:05         0.00     27.54
04:00:03         0.00     89.88
04:50:05         0.02      0.00
06:30:05         0.01      0.00
Average:         0.00      2.13
"""

# `sar -W -f /var/log/sysstat/sa30` -- carries the LINUX RESTART marker.
SA30_W = """Linux 6.8.0-138-generic (pgain-nuc) \t08/30/26 \t_x86_64_\t(4 CPU)

00:32:34     LINUX RESTART\t(4 CPU)

00:40:05     pswpin/s pswpout/s
15:10:03         0.09      2.78
17:00:05         0.03      0.00
Average:         0.00      0.02
"""


# ------------------------------------------------------------- parsing


def test_the_banner_restart_marker_and_average_row_are_all_dropped():
    t = pt.parse_sar(SA30_W)
    assert t.columns == ("pswpin/s", "pswpout/s")
    assert [r.time for r in t.rows] == ["15:10:03", "17:00:05"]


def test_columns_are_addressed_by_name_not_position():
    t = pt.parse_sar(SA31_R)
    assert t.at("02:00:05").get("kbcommit") == 30_781_532
    assert t.at("02:00:05").get("kbcached") == 1_905_372


def test_a_twelve_hour_stamp_parses_and_the_meridiem_is_not_a_column():
    t = pt.parse_sar("Linux x\n\n01:00:00 AM  pswpin/s pswpout/s\n"
                     "02:00:00 AM      0.00      1.00\n")
    assert t.columns == ("pswpin/s", "pswpout/s")
    assert t.rows[0].get("pswpout/s") == 1.0


def test_a_short_row_raises_rather_than_silently_misaligning():
    bad = "Linux x\n\n00:00:05  a  b  c\n00:10:05  1  2\n"
    with pytest.raises(pt.PerturbationError):
        pt.parse_sar(bad)


def test_text_with_no_header_raises():
    with pytest.raises(pt.PerturbationError):
        pt.parse_sar("Linux 6.8.0 (pgain-nuc)\n\n")


def test_asking_for_a_column_that_is_not_there_names_what_is():
    t = pt.parse_sar(SA31_W)
    with pytest.raises(pt.PerturbationError) as e:
        t.rows[0].get("kbcommit")
    assert "pswpout/s" in str(e.value)


def test_asking_for_a_bucket_that_is_not_there_raises():
    with pytest.raises(pt.PerturbationError):
        pt.parse_sar(SA31_W).at("11:11:11")


# --------------------------------------------------- the commitment channel


def test_the_real_capture_yields_exactly_one_persistent_commit_step():
    steps = pt.commit_steps(pt.parse_sar(SA31_R))
    persistent = [s for s in steps if s.persistent]
    assert len(persistent) == 1
    only = persistent[0]
    assert only.time == "02:00:05"
    assert only.delta_kb == 147_092
    assert only.as_dict()["delta_bytes"] == 147_092 * 1024


def test_the_0350_blip_is_seen_as_transient_not_as_a_step():
    """03:50:05 rises 1,748 kB and is gone by 04:00 -- an ssh session, not fwupd."""
    steps = pt.commit_steps(pt.parse_sar(SA31_R), min_step_kb=1_000)
    times = {s.time: s.persistent for s in steps}
    assert times["03:50:05"] is False
    assert times["02:00:05"] is True


def test_a_step_at_the_very_end_cannot_be_graded_persistent():
    """No lookahead means no verdict; defaulting to True would launder blips."""
    text = "Linux x\n\n00:00:05  kbcommit\n00:10:05  100000\n00:20:05  900000\n"
    steps = pt.commit_steps(pt.parse_sar(text), min_step_kb=50_000)
    assert len(steps) == 1 and steps[0].persistent is False


def test_a_step_that_falls_back_within_the_lookahead_is_not_persistent():
    text = ("Linux x\n\n00:00:05  kbcommit\n00:10:05  100000\n00:20:05  900000\n"
            "00:30:05  900000\n00:40:05  100000\n00:50:05  900000\n")
    steps = pt.commit_steps(pt.parse_sar(text), min_step_kb=50_000,
                            persist_buckets=3)
    assert steps[0].persistent is False


def test_persist_buckets_below_one_is_rejected():
    with pytest.raises(pt.PerturbationError):
        pt.commit_steps(pt.parse_sar(SA31_R), persist_buckets=0)


def test_a_nonpositive_min_step_is_rejected():
    with pytest.raises(pt.PerturbationError):
        pt.commit_steps(pt.parse_sar(SA31_R), min_step_kb=0)


# --------------------------------------------------- the swap channel


def test_the_three_swap_excursions_of_the_boot_day_are_recovered_in_bytes():
    x = pt.swap_excursions(pt.parse_sar(SA31_W))
    assert [(e.time, e.pages) for e in x] == [
        ("00:40:05", 84), ("02:00:05", 16_524), ("04:00:03", 53_928)]
    assert x[2].bytes == 53_928 * 4096          # 220,889,088 -- apt-daily


def test_the_bucket_interval_scales_every_figure_and_must_be_passed_explicitly():
    x300 = pt.swap_excursions(pt.parse_sar(SA31_W), interval_s=300)
    assert x300[2].pages == round(89.88 * 300)


def test_a_nonpositive_interval_is_rejected():
    with pytest.raises(pt.PerturbationError):
        pt.swap_excursions(pt.parse_sar(SA31_W), interval_s=0)


def test_swap_and_commit_agree_that_0200_and_0400_are_different_events():
    """The whole finding, as one assertion.

    Both buckets swapped the engine's pages out. Only 02:00 stepped the
    commitment; only 04:00 pulled a surge through the page cache. An instrument
    that reads just one of the two channels must call one of them a mystery --
    which is exactly what round 388 did."""
    r = pt.parse_sar(SA31_R)
    steps = {s.time: s.delta_kb for s in pt.commit_steps(r)}
    assert "02:00:05" in steps and "04:00:03" not in steps
    assert r.at("02:00:05").get("kbcached") < r.at("01:50:05").get("kbcached")
    assert r.at("04:00:03").get("kbcached") > r.at("03:50:05").get("kbcached")


# --------------------------------------------------- channel classification


def test_apt_is_page_cache_and_fwupd_is_commitment():
    assert pt.classify_bucket(pgpgin_s=554.76, pgpgin_baseline_s=0.1,
                              commit_delta_kb=-1620,
                              swapped_bytes=220_889_088) == "page_cache"
    assert pt.classify_bucket(pgpgin_s=4.17, pgpgin_baseline_s=0.1,
                              commit_delta_kb=147_092,
                              swapped_bytes=67_682_304) == "commitment"


def test_swap_with_neither_channel_is_named_unattributed_not_forced_into_one():
    assert pt.classify_bucket(0.05, 0.1, 0.0, 4096) == "unattributed"
    assert pt.classify_bucket(0.05, 0.1, 0.0, 0) == "quiet"


def test_both_channels_at_once_is_its_own_verdict():
    assert pt.classify_bucket(500.0, 0.1, 200_000, 1) == "both"


def test_a_surge_factor_that_cannot_discriminate_is_rejected():
    with pytest.raises(pt.PerturbationError):
        pt.classify_bucket(1.0, 1.0, 0.0, 0, surge_factor=1.0)
    with pytest.raises(pt.PerturbationError):
        pt.classify_bucket(1.0, 0.1, 0.0, 0, min_pgpgin_s=0)


def test_a_ratio_without_an_absolute_floor_would_call_25MB_a_surge():
    """The bug this file's own fixture caught.

    02:00's `pgpgin/s` is 4.17 against an idle baseline of ~0.1: a 41x ratio,
    and 2.5 MB. apt's bucket is 554.76 KB/s, 333 MB. Grading both `page_cache`
    on the ratio alone erases the distinction the module exists to draw."""
    ratio_only = pt.classify_bucket(4.17, 0.1, 147_092, 67_682_304,
                                    min_pgpgin_s=1.0)
    assert ratio_only == "both"
    assert pt.classify_bucket(4.17, 0.1, 147_092, 67_682_304) == "commitment"


# --------------------------------------------------- timers and windows


def test_the_two_timers_that_perturbed_this_box_are_both_unavoidable():
    by = {t.unit: t for t in pt.NUC_TIMERS}
    assert by["fwupd-refresh.timer"].avoidable is False    # 1h period, 1h jitter
    assert by["apt-daily.timer"].avoidable is False        # 12h period, 12h jitter


def test_a_timer_with_jitter_below_its_period_is_avoidable():
    assert pt.Timer("x.timer", period_s=86400, randomized_delay_s=3600).avoidable


def test_the_guard_never_calls_this_box_schedulable():
    g = pt.window_guard(1800)
    assert g["verdict"] == "contaminated_by_construction"
    assert "fwupd-refresh.timer" in g["unavoidable_units"]
    assert "apt-daily.timer" in g["unavoidable_units"]


def test_fire_probability_is_the_window_over_the_period_and_saturates():
    t = pt.Timer("x.timer", period_s=3600, randomized_delay_s=3600)
    assert t.p_fire_in_window(1800) == pytest.approx(0.5)
    assert t.p_fire_in_window(7200) == 1.0


def test_an_hour_long_window_is_certain_to_contain_a_fwupd_refresh():
    g = pt.window_guard(3600)
    row = next(r for r in g["timers"] if r["unit"] == "fwupd-refresh.timer")
    assert row["p_fire_in_window"] == 1.0


def test_a_negative_window_is_rejected():
    with pytest.raises(pt.PerturbationError):
        pt.window_guard(-1)


def test_a_timer_with_a_nonpositive_period_is_rejected():
    with pytest.raises(pt.PerturbationError):
        pt.Timer("x.timer", period_s=0)
    with pytest.raises(pt.PerturbationError):
        pt.Timer("x.timer", period_s=60, randomized_delay_s=-1)


# --------------------------------------------------- attribution


def test_an_event_at_015733_lands_in_the_bucket_ending_020005():
    """The off-by-one that would have moved fwupd out of the window it caused."""
    x = pt.swap_excursions(pt.parse_sar(SA31_W))
    got = pt.attribute(x, [pt.Event("2026-08-31T01:57:33", "fwupd-refresh.service")])
    by = {r["bucket_end"]: r for r in got}
    assert by["02:00:05"]["attributed"] is True
    assert by["04:00:03"]["attributed"] is False
    assert by["02:00:05"]["events"][0]["label"] == "fwupd-refresh.service"


def test_an_event_exactly_on_a_bucket_boundary_belongs_to_that_bucket():
    x = pt.swap_excursions(pt.parse_sar(SA31_W))
    got = pt.attribute(x, [pt.Event("2026-08-31T02:00:05", "on-the-edge")])
    by = {r["bucket_end"]: r for r in got}
    assert by["02:00:05"]["attributed"] is True


def test_commit_steps_can_be_attributed_too_not_just_swap():
    steps = pt.commit_steps(pt.parse_sar(SA31_R))
    got = pt.attribute(steps, [pt.Event("2026-08-31T01:57:33", "fwupd")])
    assert got[0]["delta_kb"] == 147_092 and got[0]["attributed"]


# --------------------------------------------------- CLI


def _cli(*args):
    r = subprocess.run([sys.executable, "-m", "nuc.perturbation", *args],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_cli_guard_and_timers_round_trip():
    assert _cli("guard", "--window-s", "600")["verdict"] == \
        "contaminated_by_construction"
    units = {t["unit"] for t in _cli("timers")}
    assert "apt-daily-upgrade.timer" in units


def test_cli_steps_reads_a_file(tmp_path):
    f = tmp_path / "sa31r.txt"
    f.write_text(SA31_R)
    out = _cli("steps", "--sar-r", str(f))
    assert [s["time"] for s in out if s["persistent"]] == ["02:00:05"]


def test_both_documented_entry_points_work():
    """`python3 -m nuc.perturbation` AND `python3 nuc/perturbation.py`.

    De-duplicating PAGE_BYTES against `swap_analysis` broke the second form
    outright -- `nuc` is not importable when the file is run as a script -- and
    nothing would have noticed, because every other test here uses `-m`."""
    import pathlib
    script = pathlib.Path(pt.__file__)
    for argv in ([sys.executable, "-m", "nuc.perturbation", "timers"],
                 [sys.executable, str(script), "timers"]):
        r = subprocess.run(argv, capture_output=True, text=True)
        assert r.returncode == 0, f"{argv}: {r.stderr}"
        assert {t["unit"] for t in json.loads(r.stdout)} >= {"apt-daily.timer"}


def test_the_page_size_is_the_one_swap_analysis_already_had():
    from nuc import swap_analysis
    assert pt.PAGE_BYTES is swap_analysis.DEFAULT_PAGE_BYTES


# ------------------------------------------------ round 400: the cost ledger

from nuc.perturbation import (  # noqa: E402
    ATTRIBUTION_MAX_FAMILY_P, ATTRIBUTION_MIN_CONSISTENCY, ATTRIBUTION_MIN_FIRES,
    attribution_evidence, _hypergeom_atleast,
    Event, LEDGER_BOUNDARY_SLACK_S, LEDGER_EXCLUDE_UNITS, LEDGER_MIN_BYTES,
    PerturbationError, cost_ledger, parse_sar, parse_unit_starts,
)

_W_HEADER = ("Linux 6.8.0-138-generic (pgain-nuc) \t08/31/26 \t_x86_64_\t(4 CPU)"
             "\n\n00:00:05     pswpin/s pswpout/s\n")


def _swap_table(rows):
    return parse_sar(_W_HEADER + "\n".join(
        f"{t}         0.00     {rate:.2f}" for t, rate in rows))


def _fires(*pairs):
    return [Event(at_utc=f"2026-08-31T{t}Z", label=u) for t, u in pairs]


def test_parse_unit_starts_matches_pid1_starting_only():
    text = (
        "2026-08-31T01:57:33+00:00 pgain-nuc systemd[1]: Starting "
        "fwupd-refresh.service - Refresh fwupd metadata...\n"
        "2026-08-31T01:57:35+00:00 pgain-nuc systemd[1]: Started "
        "fwupd-refresh.service - Refresh fwupd metadata.\n"
        "2026-08-30T00:32:35+00:00 pgain-nuc systemd[1057]: Started "
        "qwen36-colibri.service - Colibri.\n")
    ev = parse_unit_starts(text)
    assert [(e.at_utc, e.label) for e in ev] == [
        ("2026-08-31T01:57:33Z", "fwupd-refresh")]


def test_parse_unit_starts_handles_a_zulu_stamp_as_well_as_an_offset():
    text = "2026-08-31T03:50:05Z host systemd[1]: Starting apt-daily.service - x\n"
    assert [e.label for e in parse_unit_starts(text)] == ["apt-daily"]


def test_ledger_places_a_fire_in_the_bucket_that_ENDS_after_it():
    t = _swap_table([("01:50:05", 0.00), ("02:00:05", 27.54)])
    led = cost_ledger(_fires(("01:57:33", "fwupd-refresh")), t, "2026-08-31")
    assert led["entries"][0]["bucket_end"] == "02:00:05"
    assert led["entries"][0]["costly"] is True
    assert led["entries"][0]["sole_attributable"] is True
    assert led["entries"][0]["bucket_bytes"] == round(27.54 * 600) * 4096


def test_a_fire_on_a_bucket_boundary_goes_to_the_NEXT_bucket():
    """`apt-daily` fires at 03:50:05 and the sample that closes the 03:50:05
    bucket is taken at the same instant, so it cannot contain apt's work. The
    first version of this function credited apt to the zero bucket and gave its
    218 MB to `packagekit` four seconds later."""
    t = _swap_table([("03:50:05", 0.00), ("04:00:03", 89.88)])
    led = cost_ledger(_fires(("03:50:05", "apt-daily")), t, "2026-08-31")
    assert led["entries"][0]["bucket_end"] == "04:00:03"
    assert led["boundary_slack_s"] == LEDGER_BOUNDARY_SLACK_S


def test_the_boundary_slack_does_not_reach_a_real_bucket_boundary():
    """5 s must not move a fire that genuinely belongs to the earlier bucket."""
    t = _swap_table([("03:50:05", 89.88), ("04:00:03", 0.00)])
    led = cost_ledger(_fires(("03:49:00", "apt-daily")), t, "2026-08-31")
    assert led["entries"][0]["bucket_end"] == "03:50:05"


def test_a_shared_bucket_is_not_divided_and_no_fire_is_sole_attributable():
    t = _swap_table([("03:50:05", 0.00), ("04:00:03", 89.88)])
    led = cost_ledger(_fires(("03:50:05", "apt-daily"), ("03:50:09", "packagekit"),
                             ("03:57:05", "fwupd-refresh")), t, "2026-08-31")
    assert {e["bucket_shared_by"] for e in led["entries"]} == {3}
    assert led["n_fires_in_costly_bucket"] == 3
    assert led["n_sole_attributable"] == 0
    for e in led["entries"]:
        assert e["sole_attributable"] is False


def test_total_cost_bytes_sums_distinct_buckets_not_fires():
    """Summing per-fire bytes reported 799 MB for a day whose real total is
    289 MB. The bucket's cost is a property of the bucket."""
    t = _swap_table([("03:50:05", 0.00), ("04:00:03", 89.88)])
    one = cost_ledger(_fires(("03:57:05", "fwupd-refresh")), t, "2026-08-31")
    three = cost_ledger(_fires(("03:50:05", "apt-daily"), ("03:50:09", "packagekit"),
                               ("03:57:05", "fwupd-refresh")), t, "2026-08-31")
    assert one["total_cost_bytes"] == three["total_cost_bytes"]


def test_the_instrument_is_excluded_by_default_and_can_be_included():
    """`sysstat-collect` writes the bucket, so it is in every costly bucket by
    construction. Counting it makes the base rate a fact about the sampler."""
    t = _swap_table([("01:50:05", 0.00), ("02:00:05", 27.54), ("02:10:05", 0.00)])
    fires = _fires(("01:57:33", "fwupd-refresh"), ("02:00:05", "sysstat-collect"))
    default = cost_ledger(fires, t, "2026-08-31")
    assert default["n_fires"] == 1 and default["n_excluded_fires"] == 1
    assert default["excluded_units"] == list(LEDGER_EXCLUDE_UNITS)
    both = cost_ledger(fires, t, "2026-08-31", exclude_units=())
    assert both["n_fires"] == 2
    # And even when included, the boundary slack keeps the sampler OUT of the
    # bucket it wrote: sadc fires at 02:00:05 and the 02:00:05 sample is that
    # same write, so its own cost belongs to 02:10:05.
    sysstat = [e for e in both["entries"] if e["unit"] == "sysstat-collect"][0]
    assert sysstat["bucket_end"] == "02:10:05" and sysstat["costly"] is False


def test_a_sub_threshold_bucket_is_not_called_costly():
    """0.14 pswpout/s over 600 s is 344 kB. Three fires shared that bucket and
    none of them swapped a third of a megabyte of a 30 GB engine."""
    t = _swap_table([("00:30:05", 0.00), ("00:40:05", 0.14)])
    led = cost_ledger(_fires(("00:30:33", "fstrim")), t, "2026-08-31")
    assert led["entries"][0]["costly"] is False
    assert led["n_costly_buckets"] == 0
    assert led["min_bytes"] == LEDGER_MIN_BYTES


def test_a_fire_before_the_first_bucket_is_unclassified_not_free():
    t = _swap_table([("00:50:05", 0.00), ("01:00:05", 0.00)])
    led = cost_ledger(_fires(("00:32:32", "systemd-journald")), t, "2026-08-31")
    assert led["n_fires"] == 0 and led["n_unclassified"] == 1
    assert "no sar bucket" in led["unclassified"][0]["why"]


def test_a_costly_bucket_with_no_named_fire_is_reported_not_hidden():
    """A costly bucket nobody fired into is the interesting case -- it is what
    an unattributed perturbation looks like."""
    t = _swap_table([("01:50:05", 27.54), ("02:00:05", 0.00)])
    led = cost_ledger(_fires(("01:55:00", "fwupd-refresh")), t, "2026-08-31")
    assert led["costly_buckets_without_a_named_fire"] == ["01:50:05"]


def test_ledger_filters_by_date():
    t = _swap_table([("01:50:05", 0.00), ("02:00:05", 27.54)])
    fires = [Event(at_utc="2026-08-30T01:57:33Z", label="fwupd-refresh")]
    assert cost_ledger(fires, t, "2026-08-31")["n_fires"] == 0


def test_ledger_accepts_plain_tuples_as_well_as_events():
    t = _swap_table([("01:50:05", 0.00), ("02:00:05", 27.54)])
    led = cost_ledger([("2026-08-31T01:57:33Z", "fwupd-refresh")], t, "2026-08-31")
    assert led["entries"][0]["unit"] == "fwupd-refresh"


def test_ledger_rejects_a_nonpositive_interval_and_a_negative_floor():
    t = _swap_table([("01:50:05", 0.00), ("02:00:05", 27.54)])
    with pytest.raises(PerturbationError):
        cost_ledger([], t, "2026-08-31", interval_s=0)
    with pytest.raises(PerturbationError):
        cost_ledger([], t, "2026-08-31", min_bytes=-1)


# ------------------------------------------------- attribution evidence (406)
# Round 400 read `sole_attributable` as a licence for "unit X cost this" and
# named `fwupd-refresh` 2026-08-31T01:57:33Z the boot's only such event, 67.68
# MB, inherited from round 394's sample of one. `attribution_evidence` is the
# denominator that was missing. These tests fix the three ways the flag can be
# true while the claim is false, and pin the real capture that showed it.

def _ledger(entries, n_buckets, n_costly_buckets, date="2026-08-31"):
    """A minimal `cost_ledger`-shaped dict. `attribution_evidence` reads only
    these keys, so the fake is honest about the coupling."""
    return {"date": date, "n_buckets": n_buckets,
            "n_costly_buckets": n_costly_buckets, "entries": entries}


def _entry(unit, bucket_end, byts, shared_by=1, costly=None):
    return {"unit": unit, "bucket_end": bucket_end,
            "bucket_swapped_bytes": byts, "bucket_shared_by": shared_by,
            "costly": (byts >= LEDGER_MIN_BYTES) if costly is None else costly}


def test_hypergeometric_tail_at_zero_hits_is_certain_and_above_K_impossible():
    assert _hypergeom_atleast(100, 3, 10, 0) == 1.0
    assert _hypergeom_atleast(100, 3, 10, 4) == 0.0


def test_hypergeometric_matches_a_hand_computed_case():
    """P(both costly buckets inside a random 13-subset of 79) = 13*12/(79*78)."""
    assert _hypergeom_atleast(79, 2, 13, 2) == pytest.approx(156 / 6162)


def test_hypergeometric_rejects_out_of_range_arguments():
    with pytest.raises(pt.PerturbationError):
        _hypergeom_atleast(10, 2, 11, 1)


def test_a_single_fire_can_never_be_supported_however_expensive():
    """Round 394's actual epistemic position: one fire, one big bucket, held
    alone. It is not evidence -- there is nothing to replicate against."""
    led = _ledger([_entry("fwupd-refresh", "02:00:05", 67_682_304)], 79, 1)
    ev = attribution_evidence([led])["units"][0]
    assert ev["n_fires"] == 1
    assert ev["n_clean"] == 1
    assert ev["verdict"] == "insufficient-data"
    assert "replication" in ev["why"]


def test_round_406s_consistency_fixture_never_reached_the_consistency_rule():
    """Round 412. This fixture was WRITTEN to demonstrate the consistency rule
    ("a cause absent from most of its own occurrences is not the cause") and
    it never exercised it. With N=79, K=1 and one unit tested, an occupancy of
    18 gives p_chance = 18/79 = 0.228, so the CHANCE branch fires first and
    the consistency branch is unreachable behind it. The verdict string was
    right for the wrong reason, and round 412's power floor is what makes the
    difference visible: at K=1 the testable band is 1..3, and d=18 is outside
    it, so no arrangement of these fires could have been supported."""
    entries = [_entry("fwupd-refresh", "02:00:05", 67_682_304)]
    entries += [_entry("fwupd-refresh", f"{h:02d}:00:05", 0) for h in range(3, 20)]
    ev = attribution_evidence([_ledger(entries, 79, 1)])["units"][0]
    assert ev["n_fires"] == 18 and ev["n_zero_byte"] == 17
    assert ev["consistency"] == pytest.approx(1 / 18)
    assert ev["verdict"] == "untestable"
    assert pt._hypergeom_atleast(79, 1, 18, 1) > 0.05    # the branch that fired


def test_a_unit_whose_own_fires_are_mostly_free_is_a_coincidence():
    """The consistency rule, on a fixture that can actually reach it: the unit
    covers every costly bucket there is (so chance is ruled out at p=1e-5) and
    is STILL rejected, because 4 of its 10 fires cost nothing."""
    entries = [_entry("fwupd-refresh", f"{h:02d}:00:05", 67_682_304)
               for h in range(1, 5)]
    entries += [_entry("fwupd-refresh", f"{h:02d}:00:05", 0) for h in range(5, 11)]
    ev = attribution_evidence([_ledger(entries, 79, 4)])["units"][0]
    assert ev["n_fires"] == 10 and ev["n_costly"] == 4 and ev["n_clean"] == 4
    assert ev["testable"] is True            # chance is NOT the binding rule
    assert ev["p_family"] < 0.05
    assert ev["consistency"] == pytest.approx(0.4)
    assert ev["verdict"] == "coincidence"
    assert "of its own" in ev["why"]         # the consistency branch's text


def test_a_costly_hit_shared_with_another_unit_is_never_attributable():
    entries = [_entry("apt-daily", "04:00:03", 220_889_088, shared_by=5),
               _entry("apt-daily", "05:00:05", 0)]
    ev = attribution_evidence([_ledger(entries, 79, 1)])["units"][0]
    assert ev["n_costly"] == 1 and ev["n_clean"] == 0
    assert ev["verdict"] == "shared-only"


def test_a_unit_that_is_consistent_clean_and_rare_IS_supported():
    """The gate must be passable, or it is a way of never believing anything."""
    entries = [_entry("greedy", f"0{h}:00:05", 220_889_088) for h in (2, 3, 4)]
    entries += [_entry("quiet", f"1{h}:00:05", 0) for h in (0, 1, 2)]
    ev = {u["unit"]: u for u in
          attribution_evidence([_ledger(entries, 200, 3)])["units"]}
    assert ev["greedy"]["verdict"] == "supported"
    assert ev["greedy"]["consistency"] == 1.0
    assert ev["greedy"]["p_family"] <= ATTRIBUTION_MAX_FAMILY_P


def test_the_family_correction_uses_every_unit_in_the_ledger():
    """The unit under test was CHOSEN by having been noticed, so the p-value
    owes a correction over all the units that could have been noticed."""
    entries = [_entry("greedy", f"0{h}:00:05", 220_889_088) for h in (2, 3, 4)]
    entries += [_entry(f"other{i}", f"2{i}:00:05", 0) for i in range(8)]
    res = attribution_evidence([_ledger(entries, 200, 3)])
    g = next(u for u in res["units"] if u["unit"] == "greedy")
    assert res["n_units_tested"] == 9
    assert g["p_family"] == pytest.approx(min(1.0, g["p_chance"] * 9))


def test_pooling_two_days_keeps_same_named_buckets_distinct():
    """sa30's 02:00:05 and sa31's 02:00:05 are two buckets, not one."""
    a = _ledger([_entry("u", "02:00:05", 0)], 100, 1, date="2026-08-30")
    b = _ledger([_entry("u", "02:00:05", 0)], 79, 2, date="2026-08-31")
    res = attribution_evidence([a, b])
    assert res["n_buckets"] == 179 and res["n_costly_buckets"] == 3
    assert res["units"][0]["n_distinct_buckets"] == 2


def test_attribution_evidence_needs_at_least_one_ledger():
    with pytest.raises(pt.PerturbationError):
        attribution_evidence([])


def test_the_thresholds_are_decisions_not_discoveries():
    assert ATTRIBUTION_MAX_FAMILY_P == 0.05
    assert ATTRIBUTION_MIN_CONSISTENCY == 0.5
    assert ATTRIBUTION_MIN_FIRES == 2


# ------------------------------------- the real capture, as a regression pin
# `state/nuc-capture-r400/` is the ONLY surviving copy of this data off the
# box, and the box has been down since 2026-08-31T16:30Z. These tests read it
# directly rather than a hand-rolled fixture, and they are deliberately NOT
# skipped when it is absent: a missing capture is the failure, not a reason to
# pass quietly.

import pathlib  # noqa: E402

_CAP = pathlib.Path(__file__).resolve().parents[2] / "state" / "nuc-capture-r400"


def _sar_sections(text):
    secs, cur = {}, None
    for line in text.splitlines():
        if line.startswith("### "):
            cur = line[4:].strip()
            secs[cur] = []
        elif cur is not None:
            secs[cur].append(line)
    return {k: "\n".join(v) for k, v in secs.items()}


def _boot_ledgers():
    secs = _sar_sections((_CAP / "sar-all.txt").read_text())
    fires = pt.parse_unit_starts((_CAP / "unit-starts.txt").read_text())
    return [cost_ledger(fires, parse_sar(secs[f"SAR_W_{d}"]), date)
            for d, date in (("SA30", "2026-08-30"), ("SA31", "2026-08-31"))]


def test_the_banked_capture_still_reproduces_round_400s_headline_ledger():
    """62 named fires, 6 in a costly bucket, 1 sole-attributable. If this
    drifts, the disagreement is with round 400's published numbers."""
    a, b = _boot_ledgers()
    assert a["n_fires"] + b["n_fires"] == 62
    assert a["n_fires_in_costly_bucket"] + b["n_fires_in_costly_bucket"] == 6
    assert a["n_sole_attributable"] + b["n_sole_attributable"] == 1
    sole = [e for e in b["entries"] if e["sole_attributable"]]
    assert len(sole) == 1
    assert sole[0]["unit"] == "fwupd-refresh"
    assert sole[0]["at_utc"] == "2026-08-31T01:57:33Z"
    assert sole[0]["bucket_bytes"] == 67_682_304


def test_fwupd_refresh_fires_36_times_and_33_of_them_cost_nothing():
    """The measurement that drops the attribution. On sa30 alone it fired 23
    times for 23 zero-byte buckets -- an independent replication, on the same
    boot and the same configuration, in which the claimed cause is present and
    the claimed effect never appears."""
    ev = {u["unit"]: u for u in
          attribution_evidence(_boot_ledgers())["units"]}["fwupd-refresh"]
    assert ev["n_fires"] == 36
    assert ev["n_zero_byte"] == 33
    assert ev["n_costly"] == 2
    assert ev["n_clean"] == 1          # only the 02:00:05 bucket is separable
    assert ev["occupancy"] == pytest.approx(36 / 218, abs=1e-4)
    # Round 412 moved this verdict from `coincidence` to `untestable`. Round
    # 406 read "coincidence" as "we tested it and it looks like chance". At
    # d=36 against K=3 in N=218 the best p this unit could ever attain is
    # 0.00419, and 0.00419*16 = 0.067 > 0.05 -- so even hitting ALL THREE
    # costly buckets would have been graded `coincidence`. The swap channel
    # never had the power to support fwupd, whatever it did.
    assert ev["verdict"] == "untestable"
    assert ev["testable"] is False


def test_not_one_unit_in_the_whole_boot_licenses_an_attribution():
    res = attribution_evidence(_boot_ledgers())
    assert res["n_buckets"] == 218 and res["n_costly_buckets"] == 3
    assert res["n_units_tested"] == 16
    assert res["supported"] == []
    assert "supported" not in res["by_verdict"]


def test_cli_evidence_pools_ledger_files_and_filters_by_unit(tmp_path):
    paths = []
    for led in _boot_ledgers():
        p = tmp_path / f"{led['date']}.json"
        p.write_text(json.dumps(led))
        paths.append(str(p))
    argv = ["evidence"]
    for p in paths:
        argv += ["--ledger", p]
    out = subprocess.run(
        [sys.executable, "nuc/perturbation.py", *argv, "--unit", "fwupd-refresh"],
        capture_output=True, text=True,
        cwd=str(pathlib.Path(__file__).resolve().parents[2]))
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert [u["unit"] for u in got["units"]] == ["fwupd-refresh"]
    assert got["units"][0]["verdict"] == "untestable"
    assert got["n_units_tested"] == 16      # the filter must not shrink the family


# =====================================================================
# Round 412 -- the power floor, and the ledger as a two-channel instrument.
#
# Round 406 reported `supported: []` over the whole boot and wrote "this
# instrument, over this record, licenses no causal claim at all". That
# sentence conflates two different facts: the box did nothing attributable,
# and the arithmetic could not have detected it if it had. These tests pin the
# separation.

from nuc.perturbation import (                                    # noqa: E402
    Channel, SWAP_CHANNEL, COMMIT_CHANNEL, CHANNEL_MIN_BYTES,
    bucket_costs, best_case_p, power_floor, channel_sweep,
)

_SAR_WITH_RESTART = """Linux 6.8.0-138-generic (pgain-nuc) 	08/30/26 	_x86_64_	(4 CPU)

00:32:34     LINUX RESTART	(4 CPU)

00:40:05    kbmemfree kbcommit
00:50:05      273148  30634440
01:00:05      270976  30640000
"""


# ---------------------------------------------------- the restart marker

def test_parse_sar_marks_the_row_after_a_linux_restart():
    """It used to DROP the marker. Harmless for a rate column, corrupting for
    a level one: the delta across a reboot is two different address spaces."""
    t = parse_sar(_SAR_WITH_RESTART)
    assert [r.time for r in t.rows] == ["00:50:05", "01:00:05"]
    assert t.rows[0].restart_before is True
    assert t.rows[1].restart_before is False


def test_the_real_sa30_table_has_exactly_one_post_restart_row():
    t = parse_sar((_CAP / "sarW-30.txt").read_text())
    assert [r.time for r in t.rows if r.restart_before] == ["00:50:05"]
    assert len(t.rows) == 139          # and sa31 has 79: 139+79 = round 400's N


# ------------------------------------------------------------- channels

def test_a_rate_channel_cost_is_self_contained_per_bucket():
    t = parse_sar((_CAP / "sarW-31.txt").read_text())
    costs = bucket_costs(t, SWAP_CHANNEL)
    assert len(costs) == len(t.rows)
    assert all(b is not None for _n, _v, b in costs)     # never undefined
    assert dict((n, b) for n, _v, b in costs)["02:00:05"] == 67_682_304


def test_a_level_channels_first_and_post_restart_buckets_are_undefined():
    """`None`, not `0`. Round 400's own rule -- a fire whose cost is unknown
    is not a fire that cost nothing -- applied to the buckets themselves."""
    costs = bucket_costs(parse_sar(_SAR_WITH_RESTART), COMMIT_CHANNEL)
    assert costs[0][2] is None          # post-restart AND first row
    assert costs[1][2] == (30_640_000 - 30_634_440) * 1024


def test_a_level_channel_reads_rises_only_by_default():
    """A fall in Committed_AS is some other process exiting. Crediting a unit
    with it would make the ledger's sign depend on who happened to die."""
    text = _SAR_WITH_RESTART.replace("01:00:05      270976  30640000",
                                     "01:00:05      270976  30000000")
    assert bucket_costs(parse_sar(text), COMMIT_CHANNEL)[1][2] == 0
    both = Channel("c", "kbcommit", "level", 1024, "both")
    assert bucket_costs(parse_sar(text), both)[1][2] == (30_634_440 - 30_000_000) * 1024


def test_a_channel_rejects_an_incoherent_declaration():
    with pytest.raises(pt.PerturbationError):
        Channel("x", "c", "levl", 1)
    with pytest.raises(pt.PerturbationError):
        Channel("x", "c", "level", 1, "sideways")
    with pytest.raises(pt.PerturbationError):
        Channel("x", "c", "rate", 1, "rise")     # a rate has no predecessor


def test_bucket_costs_refuses_a_table_without_the_channels_column():
    t = parse_sar((_CAP / "sarW-31.txt").read_text())
    with pytest.raises(pt.PerturbationError) as e:
        bucket_costs(t, COMMIT_CHANNEL)
    assert "kbcommit" in str(e.value)


# ------------------------------------------- the threshold has no default

def test_the_commit_channel_refuses_to_invent_a_costly_threshold():
    """`LEDGER_MIN_BYTES` is derived from two LABELLED swap events. The commit
    channel has no such pair on this record, so a default would be a number
    with a derivation-shaped comment and no derivation."""
    assert CHANNEL_MIN_BYTES["commit"] is None
    t = parse_sar(_sar_sections((_CAP / "sar-all.txt").read_text())["SAR_R_SA31"])
    with pytest.raises(pt.PerturbationError) as e:
        cost_ledger([], t, "2026-08-31", channel=COMMIT_CHANNEL)
    assert "channel_sweep" in str(e.value)
    cost_ledger([], t, "2026-08-31", channel=COMMIT_CHANNEL, min_bytes=1 << 20)


# ------------------------------------------------------- the power floor

def test_a_record_with_one_costly_bucket_can_support_nothing_at_all():
    """The vacuity case, exactly. N=218, K=1, 16 units: the smallest p any
    unit can attain is 1/218 = 0.00459, and 0.00459*16 = 0.073 > 0.05."""
    pf = power_floor(218, 1, 16)
    assert pf["any_testable"] is False
    assert pf["n_testable_occupancies"] == 0
    assert pf["best_p_at_occupancy_1"] == pytest.approx(1 / 218)
    assert "whatever it contains" in pf["why"]


def test_occupancy_that_is_too_LOW_is_as_fatal_as_occupancy_too_high():
    """The counterintuitive half. Covering 1 of K by chance is common;
    covering 2 of K is rare. So d=1 can be untestable while d=2 is testable,
    and the testable set does not start at 1."""
    pf = power_floor(218, 3, 16)
    assert pf["min_testable_occupancy"] == 2
    assert pf["max_testable_occupancy"] == 32
    assert best_case_p(218, 3, 1) > best_case_p(218, 3, 2)
    assert best_case_p(218, 3, 1) * 16 > 0.05          # d=1 cannot clear
    assert best_case_p(218, 3, 2) * 16 <= 0.05         # d=2 can


def test_best_case_p_is_the_tail_at_the_best_possible_number_of_hits():
    assert best_case_p(218, 3, 36) == pt._hypergeom_atleast(218, 3, 36, 3)
    assert best_case_p(218, 3, 2) == pt._hypergeom_atleast(218, 3, 2, 2)  # d<K


def test_power_floor_rejects_an_impossible_record_shape():
    for args in ((0, 0, 1), (10, 11, 1), (10, 2, 0)):
        with pytest.raises(pt.PerturbationError):
            power_floor(*args)


# ------------------------------- untestable is not the same as unsupported

def _noisy(n_costly=3):
    """One unit at fwupd's real occupancy -- 36 buckets, all K costly ones
    covered and held alone. This is the BEST outcome the record allows it."""
    e = [_entry("noisy", f"{h:02d}:00:05", 67_682_304) for h in range(n_costly)]
    e += [_entry("noisy", f"{h:02d}:{m:02d}:05", 0)
          for h in range(n_costly, 24) for m in (0, 30)][:36 - n_costly]
    return e


def test_a_unit_too_large_to_test_is_graded_untestable_not_coincidence():
    """36 buckets against K=3 in N=218, with the best outcome available, and
    still not supported. `untestable` names that; `coincidence` implied a test
    ran and the unit lost it."""
    filler = [_entry(f"u{i}", f"{i:02d}:15:05", 0) for i in range(15)]
    res = attribution_evidence([_ledger(_noisy() + filler, 218, 3)])
    u = {x["unit"]: x for x in res["units"]}["noisy"]
    assert u["n_distinct_buckets"] == 36 and u["n_costly"] == 3
    assert u["n_clean"] == 3 and u["consistency"] > 0.05
    assert u["testable"] is False
    assert u["verdict"] == "untestable"
    assert "fact about" in u["why"]
    assert "noisy" in res["untestable_units"]


def test_testability_depends_on_how_many_OTHER_units_are_in_the_ledger():
    """Bonferroni's uncomfortable corollary, and the reason `untestable` is a
    property of the RUN and not of the unit. The identical 36 fires with the
    identical best-case outcome are testable in a one-unit family (bar 0.05)
    and untestable in a sixteen-unit one (bar 0.003125) -- so widening the
    family can retract a claim without a single new observation. It is still
    the right correction: the unit under test was chosen by having been
    noticed. But the ledger must say which family it was graded against."""
    alone = attribution_evidence([_ledger(_noisy(), 218, 3)])
    assert alone["n_units_tested"] == 1
    assert alone["units"][0]["testable"] is True
    # testable, and it then LOSES the test on consistency (3 of 36 fires
    # costly) -- which is a real result about the unit. The crowd run below
    # never gets that far.
    assert alone["units"][0]["verdict"] == "coincidence"
    assert "of its own" in alone["units"][0]["why"]

    filler = [_entry(f"u{i}", f"{i:02d}:15:05", 0) for i in range(15)]
    crowd = attribution_evidence([_ledger(_noisy() + filler, 218, 3)])
    noisy = {x["unit"]: x for x in crowd["units"]}["noisy"]
    assert crowd["n_units_tested"] == 16
    assert noisy["testable"] is False and noisy["verdict"] == "untestable"
    assert noisy["p_chance"] == alone["units"][0]["p_chance"]   # same evidence
    assert crowd["supported"] == []


def test_untestable_can_never_steal_a_unit_from_supported():
    """The new verdict sits between `shared-only` and `coincidence`. Anything
    it captures already had p_family > max_family_p, so round 406's
    `supported: []` headline is unchanged by construction."""
    entries = [_entry("clean", f"{h:02d}:00:05", 67_682_304) for h in range(1, 4)]
    res = attribution_evidence([_ledger(entries, 218, 3)])
    assert res["units"][0]["verdict"] == "supported"
    assert res["units"][0]["testable"] is True
    assert res["supported"] == ["clean"] and res["supported_was_reachable"]


def test_attribution_evidence_still_reads_a_round_400_era_ledger():
    """`_entry` writes the OLD `bucket_swapped_bytes` key, which is exactly
    the point: ledger JSON written by rounds 400-406 is on disk."""
    e = _entry("u", "02:00:05", 67_682_304)
    assert "bucket_swapped_bytes" in e and "bucket_bytes" not in e
    old = attribution_evidence([_ledger([e], 218, 3)])["units"][0]
    new_e = dict(e); new_e["bucket_bytes"] = new_e.pop("bucket_swapped_bytes")
    new = attribution_evidence([_ledger([new_e], 218, 3)])["units"][0]
    assert old["max_bucket_bytes"] == new["max_bucket_bytes"] == 67_682_304


# ------------------------------------ shared_by counts units, not fires

def test_two_fires_of_one_unit_in_a_bucket_leave_it_sole_attributable():
    """Latent defect found in round 412: `share` counted FIRES, so a bucket
    with exactly one unit implicated reported `sole_attributable = False`."""
    t = parse_sar(_sar_sections((_CAP / "sar-all.txt").read_text())["SAR_W_SA31"])
    led = cost_ledger([("2026-08-31T01:57:33Z", "fwupd-refresh"),
                       ("2026-08-31T01:58:00Z", "fwupd-refresh")],
                      t, "2026-08-31")
    a, b = led["entries"]
    assert a["bucket_end"] == b["bucket_end"] == "02:00:05"
    assert a["bucket_shared_by"] == 1 and a["bucket_fires"] == 2
    assert a["sole_attributable"] is True
    assert led["n_sole_attributable"] == 2


def test_two_DIFFERENT_units_in_a_bucket_are_still_not_separable():
    t = parse_sar(_sar_sections((_CAP / "sar-all.txt").read_text())["SAR_W_SA31"])
    led = cost_ledger([("2026-08-31T01:57:33Z", "fwupd-refresh"),
                       ("2026-08-31T01:58:00Z", "man-db")], t, "2026-08-31")
    assert led["entries"][0]["bucket_shared_by"] == 2
    assert led["n_sole_attributable"] == 0


def test_the_shared_by_fix_does_not_move_round_400s_published_headline():
    """No bucket in the r400 capture holds same-unit repeats, so the defect
    was latent. If a future capture makes it active, THIS is the pin that
    says the numbers moved for a reason."""
    a, b = _boot_ledgers()
    assert a["n_fires"] + b["n_fires"] == 62
    assert a["n_sole_attributable"] + b["n_sole_attributable"] == 1
    for led in (a, b):
        for e in led["entries"]:
            assert e["bucket_fires"] >= e["bucket_shared_by"]


# --------------------------------------------- the real capture, re-graded

def _commit_ledgers(min_bytes=4_825_700):
    secs = _sar_sections((_CAP / "sar-all.txt").read_text())
    fires = pt.parse_unit_starts((_CAP / "unit-starts.txt").read_text())
    return [cost_ledger(fires, parse_sar(secs[f"SAR_R_{d}"]), date,
                        min_bytes=min_bytes, channel=COMMIT_CHANNEL)
            for d, date in (("SA30", "2026-08-30"), ("SA31", "2026-08-31"))]


def test_half_the_boots_units_could_never_have_been_supported():
    res = attribution_evidence(_boot_ledgers())
    assert res["n_units_tested"] == 16
    assert res["n_testable_units"] == 8
    assert len(res["untestable_units"]) == 8
    # seven because their occupancy is too LOW (one bucket), one too high
    low = [u for u in res["units"]
           if not u["testable"] and u["n_distinct_buckets"] == 1]
    high = [u for u in res["units"]
            if not u["testable"] and u["n_distinct_buckets"] > 1]
    assert len(low) == 7
    assert [u["unit"] for u in high] == ["fwupd-refresh"]


def test_sa30_ALONE_is_a_record_that_could_not_have_supported_anything():
    """Round 406 pooled the two day-files "because sa30 contributes 23 free
    fwupd fires". This is the quantitative reason it had to: on its own, sa30
    has K=1 and therefore no power at any occupancy."""
    sa30 = _boot_ledgers()[0]
    assert sa30["n_buckets"] == 139 and sa30["n_costly_buckets"] == 1
    res = attribution_evidence([sa30])
    assert res["supported_was_reachable"] is False
    assert res["power"]["any_testable"] is False


def test_the_commit_channel_gives_fwupd_the_powered_test_swap_could_not():
    """Round 406's handoff item 4, answered. On `sar -W` fwupd is UNTESTABLE:
    its verdict was fixed before the data was read, and hitting all three
    costly buckets would still have read `coincidence`. On `Committed_AS` the
    same 36 fires sit against K=9 costly buckets in N=216, which IS inside the
    testable band -- so the test genuinely runs, and fwupd fails it: it
    covered 1 of the 9, which a unit of its occupancy does by chance with
    p=0.81. Round 406's DROP verdict now rests on a powered test rather than
    on a consistency argument alone."""
    swap = {u["unit"]: u for u in
            attribution_evidence(_boot_ledgers())["units"]}["fwupd-refresh"]
    commit = {u["unit"]: u for u in
              attribution_evidence(_commit_ledgers())["units"]}["fwupd-refresh"]
    assert swap["testable"] is False and swap["verdict"] == "untestable"
    assert commit["testable"] is True and commit["verdict"] == "coincidence"
    assert commit["n_fires"] == 36 and commit["n_costly"] == 1
    assert commit["n_buckets"] == 216 and commit["n_costly_buckets"] == 9
    assert commit["p_chance"] == pytest.approx(0.8127, abs=5e-4)
    assert commit["p_best"] * commit["n_units_tested"] <= 0.05   # it WAS testable
    assert "happens by chance" in commit["why"]


def test_neither_channel_supports_anything_at_any_threshold():
    """18 configurations. Round 406's headline survives all of them -- which
    is what makes it a result rather than a setting."""
    secs = _sar_sections((_CAP / "sar-all.txt").read_text())
    fires = pt.parse_unit_starts((_CAP / "unit-starts.txt").read_text())
    ths = [4096, 1 << 15, 1 << 17, 1 << 19, 4_825_700,
           1 << 23, 1 << 25, 1 << 27, 1 << 30]
    for chan, pfx in ((SWAP_CHANNEL, "SAR_W_"), (COMMIT_CHANNEL, "SAR_R_")):
        tables = [(parse_sar(secs[pfx + d]), dt)
                  for d, dt in (("SA30", "2026-08-30"), ("SA31", "2026-08-31"))]
        rows = channel_sweep(fires, tables, chan, ths)
        assert len(rows) == len(ths)
        assert all(r["supported"] == [] for r in rows)


def test_the_swap_channels_power_collapses_to_zero_and_commits_does_not():
    """The inversion. Above ~134 MB the swap channel has NO testable unit at
    any occupancy -- `supported: []` there is arithmetic, not evidence. The
    commit channel keeps 7 testable units at the same threshold, because it
    still has costly buckets to be improbably covered."""
    secs = _sar_sections((_CAP / "sar-all.txt").read_text())
    fires = pt.parse_unit_starts((_CAP / "unit-starts.txt").read_text())
    ths = [4_825_700, 1 << 27]
    got = {}
    for chan, pfx in ((SWAP_CHANNEL, "SAR_W_"), (COMMIT_CHANNEL, "SAR_R_")):
        tables = [(parse_sar(secs[pfx + d]), dt)
                  for d, dt in (("SA30", "2026-08-30"), ("SA31", "2026-08-31"))]
        got[chan.name] = channel_sweep(fires, tables, chan, ths)
    assert [r["n_testable_units"] for r in got["swap"]] == [8, 0]
    assert got["swap"][1]["supported_was_reachable"] is False
    assert [r["n_testable_units"] for r in got["commit"]] == [8, 7]
    assert all(r["supported_was_reachable"] for r in got["commit"])


def test_the_biggest_swap_event_of_the_boot_committed_nothing():
    """Rounds 388/394/400 circled the 04:00:03 bucket -- 220.9 MB out, five
    named units in it -- as the largest perturbation this deployment has seen.
    On the commitment channel that bucket does not rise at all; kbcommit FALLS
    1.6 MB across it. No NEW address space was promised there, so whatever
    drove 220 MB to swap was reclaim against memory already committed, not a
    housekeeping unit allocating. The 02:00:05 bucket, by contrast, is a real
    allocation: +150.6 MB committed alongside 67.7 MB out."""
    secs = _sar_sections((_CAP / "sar-all.txt").read_text())
    w = dict((n, b) for n, _v, b in
             bucket_costs(parse_sar(secs["SAR_W_SA31"]), SWAP_CHANNEL))
    r = parse_sar(secs["SAR_R_SA31"])
    c = dict((n, b) for n, _v, b in bucket_costs(r, COMMIT_CHANNEL))
    kb = {row.time: row.get("kbcommit") for row in r.rows}
    assert w["04:00:03"] == 220_889_088 and c["04:00:03"] == 0
    assert kb["04:00:03"] - kb["03:50:05"] == -1620          # kB, i.e. a FALL
    assert w["02:00:05"] == 67_682_304 and c["02:00:05"] == 150_622_208


def test_a_level_channel_loses_the_days_first_bucket_and_says_so():
    """Three units fire into sa31's 00:10:05 bucket, whose commit cost is
    undefined because the day-file has no earlier row. They are reported as
    unclassified, NOT as free -- and they vanish from the tested family,
    16 units -> 13. Stitching consecutive day-files would recover them."""
    swap_units = {e["unit"] for l in _boot_ledgers() for e in l["entries"]}
    commit = _commit_ledgers()
    commit_units = {e["unit"] for l in commit for e in l["entries"]}
    assert sorted(swap_units - commit_units) == [
        "dpkg-db-backup", "logrotate", "sysstat-summary"]
    whys = [u["why"] for l in commit for u in l["unclassified"]
            if "no defined commit cost" in u["why"]]
    assert len(whys) == 4
    assert all(l["n_undefined_buckets"] == 1 for l in commit)


def test_the_journal_bounds_attribution_to_two_of_the_nine_banked_days():
    """`sar` covers 2026-08-23..31; the journal covers one boot. Item 4's
    "runnable for all nine days" is true of the CHANNEL and false of the
    analysis, and no amount of sar data changes it."""
    fires = pt.parse_unit_starts((_CAP / "unit-starts.txt").read_text())
    dates = sorted({f.at_utc[:10] for f in fires})
    assert dates == ["2026-08-30", "2026-08-31"]


def _run(*argv):
    return subprocess.run([sys.executable, "-m", "nuc.perturbation", *argv],
                          capture_output=True, text=True,
                          cwd=str(pathlib.Path(__file__).resolve().parents[2]))


def test_cli_power_needs_no_data_at_all():
    """The point of exposing it separately: you can ask whether a record of a
    given shape COULD support anything before you go and capture it."""
    out = _run("power", "--n-buckets", "218", "--n-costly-buckets", "1",
               "--n-units-tested", "16")
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["any_testable"] is False


def test_cli_sweep_reports_the_verdict_as_a_function_of_the_threshold(tmp_path):
    secs = _sar_sections((_CAP / "sar-all.txt").read_text())
    days = []
    for d, date in (("SA30", "2026-08-30"), ("SA31", "2026-08-31")):
        f = tmp_path / f"{d}.txt"
        f.write_text(secs[f"SAR_W_{d}"])
        days += ["--day", f"{f}:{date}"]
    out = _run("sweep", *days, "--journal", str(_CAP / "unit-starts.txt"),
               "--channel", "swap", "--thresholds", "4825700,134217728")
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert [r["n_costly_buckets"] for r in got] == [3, 1]
    assert [r["supported_was_reachable"] for r in got] == [True, False]
    assert all(r["supported"] == [] for r in got)


def test_cli_ledger_defaults_to_the_channels_threshold_and_refuses_when_none():
    secs = _sar_sections((_CAP / "sar-all.txt").read_text())
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        w = os.path.join(td, "w.txt"); r = os.path.join(td, "r.txt")
        open(w, "w").write(secs["SAR_W_SA31"])
        open(r, "w").write(secs["SAR_R_SA31"])
        j = str(_CAP / "unit-starts.txt")
        ok = _run("ledger", "--sar-w", w, "--journal", j,
                  "--date", "2026-08-31")
        assert ok.returncode == 0, ok.stderr
        assert json.loads(ok.stdout)["min_bytes"] == LEDGER_MIN_BYTES
        bad = _run("ledger", "--sar-w", r, "--journal", j,
                   "--date", "2026-08-31", "--channel", "commit")
        assert bad.returncode != 0
        assert "channel_sweep" in bad.stderr
        good = _run("ledger", "--sar-w", r, "--journal", j, "--date",
                    "2026-08-31", "--channel", "commit",
                    "--min-bytes", "4825700")
        assert good.returncode == 0, good.stderr
        assert json.loads(good.stdout)["channel"] == "commit"


# ===================================================================== r418
# Round 418, NUC-integration(E), box DOWN. Two items from round 412's handoff,
# both answerable from `state/nuc-capture-r400/` with no box:
#   item 3 -- stitch consecutive day-files, so a LEVEL channel can cost a
#             day's first bucket and stops losing three real fires;
#   item 2 -- read `sar -B`, banked since round 400 and never opened, to say
#             what touched already-committed pages at 04:00:03 on sa31.
# Every number these tests pin is quoted in
# `knowledge/round-418-nuc-e-the-eviction-the-promise-channel-could-not-see.md`.


def _r418_sections():
    return _sar_sections((_CAP / "sar-all.txt").read_text())


def _r418_fires():
    return pt.parse_unit_starts((_CAP / "unit-starts.txt").read_text())


def _r418_stitch():
    secs = _r418_sections()
    return pt.stitch_from(parse_sar(secs["SAR_R_SA30"]), "2026-08-30",
                          parse_sar(secs["SAR_R_SA31"]), "2026-08-31")


# ------------------------------------------------------------- the stitch


def test_stitched_boundary_bucket_is_two_intervals_wide():
    """`sar` consumes each day-file's first record as its reference point and
    never prints it, so sa30 ends at 23:50:05 and sa31 begins at 00:10:05.
    The recovered bucket covers 1200 s, not 600, and saying otherwise puts ten
    minutes of the previous day inside a bucket labelled ten minutes wide."""
    st = _r418_stitch()
    assert (st.prev_time, st.next_time) == ("23:50:05", "00:10:05")
    assert st.span_s == 1200
    assert st.as_dict()["spans_more_than_one_interval"] is True
    # the swallowed sample's stamp is what sar prints on the HEADER line
    hdr = [l for l in _r418_sections()["SAR_R_SA31"].splitlines()
           if "kbmemfree" in l][0]
    assert hdr.split()[0] == "00:00:05"


def test_stitch_refuses_non_consecutive_days():
    secs = _r418_sections()
    with pytest.raises(pt.PerturbationError, match="2 day\\(s\\) apart"):
        pt.stitch_from(parse_sar(secs["SAR_R_SA29"]), "2026-08-29",
                       parse_sar(secs["SAR_R_SA31"]), "2026-08-31")


def test_stitch_refuses_a_first_row_that_follows_a_restart():
    """sa30's first printed row follows `LINUX RESTART 00:32:34`. Differencing
    it against sa29's last row books a whole reboot's address space as one
    bucket's cost -- 25 GB of it, on this record."""
    secs = _r418_sections()
    with pytest.raises(pt.PerturbationError, match="LINUX RESTART"):
        pt.stitch_from(parse_sar(secs["SAR_R_SA29"]), "2026-08-29",
                       parse_sar(secs["SAR_R_SA30"]), "2026-08-30")


def test_stitch_refuses_two_different_activity_types():
    secs = _r418_sections()
    with pytest.raises(pt.PerturbationError, match="different columns"):
        pt.stitch_from(parse_sar(secs["SAR_R_SA30"]), "2026-08-30",
                       parse_sar(secs["SAR_W_SA31"]), "2026-08-31")


def test_stitch_refuses_a_span_wider_than_a_sample_gap():
    secs = _r418_sections()
    with pytest.raises(pt.PerturbationError, match="more than max_span_s"):
        pt.stitch_from(parse_sar(secs["SAR_R_SA30"]), "2026-08-30",
                       parse_sar(secs["SAR_R_SA31"]), "2026-08-31",
                       max_span_s=900)


def test_stitch_refuses_a_bad_date_rather_than_guessing():
    secs = _r418_sections()
    with pytest.raises(pt.PerturbationError, match="not YYYY-MM-DD"):
        pt.stitch_from(parse_sar(secs["SAR_R_SA30"]), "sa30",
                       parse_sar(secs["SAR_R_SA31"]), "2026-08-31")


def test_bucket_costs_refuses_a_stitch_without_the_channel_column():
    """A stitch carried from a `sar -W` row into a commit-channel cost would
    silently leave the first bucket undefined; it raises instead."""
    secs = _r418_sections()
    st = _r418_stitch()
    bad = pt.Stitch(prev_date=st.prev_date, prev_time=st.prev_time,
                    next_date=st.next_date, next_time=st.next_time,
                    span_s=st.span_s, values={"pswpout/s": 0.0})
    with pytest.raises(pt.PerturbationError, match="has no column 'kbcommit'"):
        pt.bucket_costs(parse_sar(secs["SAR_R_SA31"]), pt.COMMIT_CHANNEL,
                        stitch=bad)


def test_stitch_recovers_the_three_units_round_412_lost():
    """`dpkg-db-backup`, `logrotate` (00:00:05) and `sysstat-summary`
    (00:07:05) all land in sa31's 00:10:05 bucket, which the commit channel
    could not cost. 3 unclassified -> 0."""
    secs, fires, st = _r418_sections(), _r418_fires(), _r418_stitch()
    t = parse_sar(secs["SAR_R_SA31"])
    mb = 50_000 * 1024
    no = pt.cost_ledger(fires, t, "2026-08-31", channel=pt.COMMIT_CHANNEL,
                        min_bytes=mb)
    yes = pt.cost_ledger(fires, t, "2026-08-31", channel=pt.COMMIT_CHANNEL,
                         min_bytes=mb, stitch=st)
    assert (no["n_unclassified"], yes["n_unclassified"]) == (3, 0)
    assert sorted(u["unit"] for u in no["unclassified"]) == [
        "dpkg-db-backup", "logrotate", "sysstat-summary"]
    assert (no["n_buckets"], yes["n_buckets"]) == (78, 79)
    assert (no["n_undefined_buckets"], yes["n_undefined_buckets"]) == (1, 0)
    assert (no["stitch_applied"], yes["stitch_applied"]) == (False, True)


def test_the_recovered_bucket_cost_nothing_and_carries_its_width():
    """Recovering the fires does not recover any COST: `kbcommit` is pinned at
    30 634 440 kB across the boundary, so the bucket's rise is exactly zero.
    Three units come back and zero attributions do."""
    secs, fires, st = _r418_sections(), _r418_fires(), _r418_stitch()
    led = pt.cost_ledger(fires, parse_sar(secs["SAR_R_SA31"]), "2026-08-31",
                         channel=pt.COMMIT_CHANNEL, min_bytes=50_000 * 1024,
                         stitch=st)
    wide = [e for e in led["entries"] if e["bucket_span_s"] != 600]
    assert len(wide) == 3 and led["n_wide_buckets"] == 1
    assert {e["bucket_end"] for e in wide} == {"00:10:05"}
    assert all(e["bucket_bytes"] == 0 and e["costly"] is False
               and e["bucket_span_s"] == 1200 for e in wide)
    assert st.values["kbcommit"] == 30_634_440.0


def test_stitching_a_rate_channel_changes_nothing():
    """A `pswpout/s` bucket is self-contained. Handing it a stitch is allowed
    -- `channel_sweep` hands the same one to every channel -- and is a no-op."""
    secs, fires = _r418_sections(), _r418_fires()
    t = parse_sar(secs["SAR_W_SA31"])
    st = pt.stitch_from(parse_sar(secs["SAR_W_SA30"]), "2026-08-30",
                        t, "2026-08-31")
    no = pt.cost_ledger(fires, t, "2026-08-31", channel=pt.SWAP_CHANNEL)
    yes = pt.cost_ledger(fires, t, "2026-08-31", channel=pt.SWAP_CHANNEL,
                         stitch=st)
    assert pt.stitch_applies(pt.SWAP_CHANNEL, st) is False
    assert yes["stitch_applied"] is False
    assert no["entries"] == yes["entries"]
    assert no["n_buckets"] == yes["n_buckets"]


def test_recovering_data_makes_the_power_floor_strictly_worse():
    """The counter-intuitive half of item 3, and the reason it is worth
    writing down. The three recovered units enter the Bonferroni family and
    bring no costly buckets with them, so K is unchanged, the per-unit bar
    tightens, and the testable band SHRINKS. More data, less power."""
    secs, fires = _r418_sections(), _r418_fires()
    st = _r418_stitch()
    mb = 50_000 * 1024
    l30 = pt.cost_ledger(fires, parse_sar(secs["SAR_R_SA30"]), "2026-08-30",
                         channel=pt.COMMIT_CHANNEL, min_bytes=mb)
    t31 = parse_sar(secs["SAR_R_SA31"])
    no = pt.attribution_evidence(
        [l30, pt.cost_ledger(fires, t31, "2026-08-31",
                             channel=pt.COMMIT_CHANNEL, min_bytes=mb)])
    yes = pt.attribution_evidence(
        [l30, pt.cost_ledger(fires, t31, "2026-08-31",
                             channel=pt.COMMIT_CHANNEL, min_bytes=mb,
                             stitch=st)])
    assert (no["n_units_tested"], yes["n_units_tested"]) == (13, 16)
    assert no["n_costly_buckets"] == yes["n_costly_buckets"] == 4
    assert (no["power"]["max_testable_occupancy"],
            yes["power"]["max_testable_occupancy"]) == (54, 52)
    assert yes["power"]["per_unit_bar"] < no["power"]["per_unit_bar"]
    assert no["n_testable_units"] == yes["n_testable_units"] == 8
    assert no["supported"] == yes["supported"] == []


def test_auto_stitches_keeps_the_reason_a_day_was_not_joined():
    secs = _r418_sections()
    tables = [(parse_sar(secs[f"SAR_R_SA{d}"]), f"2026-08-{d}")
              for d in ("29", "30", "31")]
    got = pt.auto_stitches(tables)
    assert isinstance(got["2026-08-31"], pt.Stitch)
    assert "LINUX RESTART" in got["2026-08-30"]


# ------------------------------------------------------------ the reclaim


def _r418_B(day):
    return parse_sar(_r418_sections()[f"SAR_B_SA{day}"])


def test_reclaim_refuses_a_table_that_is_not_sar_B():
    """A `sar -W` table parses fine and has no scan columns, so a lenient
    reader would report "this box never reclaimed" -- a false negative, which
    is exactly the claim this module exists to prevent."""
    with pytest.raises(pt.PerturbationError, match="not a `sar -B` table"):
        pt.reclaim_events(parse_sar(_r418_sections()["SAR_W_SA31"]))


def test_no_direct_reclaim_anywhere_in_the_banked_boot():
    """`pgscand/s` is 0.00 in every bucket of both days: the kernel woke
    kswapd seven times and never once stalled an allocation. Memory pressure
    on this box shows up as eviction, not as allocator latency."""
    for day in ("30", "31"):
        s = pt.reclaim_summary(_r418_B(day), f"2026-08-{day}")
        assert s["n_direct_reclaim_buckets"] == 0
        assert set(s["by_kind"]) <= {"quiet", "kswapd"}


def test_the_reclaim_denominator_is_kept():
    s30 = pt.reclaim_summary(_r418_B("30"), "2026-08-30")
    s31 = pt.reclaim_summary(_r418_B("31"), "2026-08-31")
    assert (s30["n_buckets"], s30["n_reclaim_buckets"]) == (139, 4)
    assert (s31["n_buckets"], s31["n_reclaim_buckets"]) == (79, 3)
    assert round(s30["reclaim_bucket_fraction"], 5) == 0.02878
    assert round(s31["reclaim_bucket_fraction"], 5) == 0.03797


def test_the_04_00_03_bucket_is_the_largest_reclaim_of_sa31():
    """Round 412's unexplained bucket, read on the channel that can see it."""
    big = pt.reclaim_summary(_r418_B("31"), "2026-08-31")["largest_bucket"]
    assert big["time"] == "04:00:03" and big["kind"] == "kswapd"
    assert (big["scan_kswapd_s"], big["scan_direct_s"], big["steal_s"]) == (
        1207.0, 0.0, 401.7)
    assert big["stolen_pages"] == 241_020
    assert big["stolen_bytes"] == 987_217_920
    assert big["paged_in_kb"] == 332_856
    assert round(big["vmeff_pct"], 2) == big["vmeff_reported"] == 33.28


def test_the_commit_channel_is_not_coarse_at_04_00_03_it_is_zero():
    """The finding. If the commit channel were merely a blunter instrument,
    its cost at a bucket that reclaimed a gigabyte would be the same order of
    magnitude. It is exactly 0 bytes: eviction moves residency, and
    `Committed_AS` counts promises, which an eviction does not revoke."""
    gap = pt.eviction_gap(_r418_B("31"),
                          parse_sar(_r418_sections()["SAR_R_SA31"]),
                          pt.COMMIT_CHANNEL, stitch=_r418_stitch())
    at = {g["time"]: g for g in gap}
    assert at["04:00:03"]["stolen_bytes"] == 987_217_920
    assert at["04:00:03"]["level_bytes"] == 0
    assert at["04:00:03"]["ratio"] == 0.0
    assert at["00:40:05"]["level_bytes"] == 0


def test_vmeff_over_100_is_reported_not_averaged_away():
    """Six of the seven reclaim buckets in this capture report `%vmeff > 100`,
    which is impossible if pgsteal and pgscan count the same pages."""
    loud = (pt.reclaim_events(_r418_B("30"))
            + pt.reclaim_events(_r418_B("31")))
    assert len(loud) == 7
    assert sum(1 for e in loud if e.steal_exceeds_scan) == 6
    assert max(e.vmeff_reported for e in loud) == 200.0


def test_halving_pgsteal_restores_the_reclaim_efficiency_ceiling():
    """`%vmeff <= 100` is a theorem, not a convention: you cannot steal a page
    you did not scan. Dividing pgsteal by 2 puts all seven observations at or
    under the ceiling, with the maximum landing on exactly 100.000 and five of
    seven within 1 % of it -- a sharp ceiling, not a scatter."""
    loud = (pt.reclaim_events(_r418_B("30"))
            + pt.reclaim_events(_r418_B("31")))
    chk = pt.reclaim_double_count_check(loud)
    assert chk["n_events"] == 7
    assert chk["n_over_ceiling_reported"] == 6
    assert chk["n_over_ceiling_corrected"] == 0
    assert chk["ceiling_restored"] is True
    assert round(chk["max_corrected_pct"], 3) == 100.0
    assert chk["n_near_ceiling"] == 5


def test_a_divisor_that_does_not_restore_the_ceiling_says_so():
    loud = pt.reclaim_events(_r418_B("30"))
    chk = pt.reclaim_double_count_check(loud, divisor=1.5)
    assert chk["ceiling_restored"] is False
    assert "does NOT restore the ceiling" in chk["why"]
    with pytest.raises(pt.PerturbationError, match="divisor must be > 0"):
        pt.reclaim_double_count_check(loud, divisor=0)


# ---------------------------------------------- the steal channel, graded


def test_steal_channel_has_no_derivable_threshold_either():
    """Round 412's rule, applied to a third channel: there is no bucket on
    this record independently labelled reclaim-noise, so a default would BE
    the result."""
    assert pt.CHANNEL_MIN_BYTES["steal"] is None
    with pytest.raises(pt.PerturbationError, match="no derived costly-thresh"):
        pt.cost_ledger(_r418_fires(), _r418_B("31"), "2026-08-31",
                       channel=pt.STEAL_CHANNEL)


def test_every_swapout_bucket_also_reclaimed_and_three_reclaimed_without():
    """`pgsteal > 0` is a strict superset of `pswpout > 0` pooled over the
    boot -- reclaim precedes swap-out. On sa31 alone the two sets are EQUAL;
    the three steal-only buckets are all on sa30."""
    secs = _r418_sections()
    def nz(t, col):
        return {r.time for r in t.rows if r.get(col) > 0}
    s30 = nz(_r418_B("30"), "pgsteal/s")
    w30 = nz(parse_sar(secs["SAR_W_SA30"]), "pswpout/s")
    s31 = nz(_r418_B("31"), "pgsteal/s")
    w31 = nz(parse_sar(secs["SAR_W_SA31"]), "pswpout/s")
    assert w30 < s30 and len(s30 - w30) == 3
    assert w31 == s31
    assert (w30 | w31) < (s30 | s31)


def test_the_steal_channel_verdict_does_not_turn_on_its_threshold():
    """The commit channel's verdict moves with an unpinned threshold, so it is
    a setting (round 412). The steal channel's does not: reclaim on this box
    is bimodal -- a bucket steals 0 or >= 260 MiB -- so K = 7 is stable over
    five orders of magnitude and only collapses past 1 GiB."""
    secs = _r418_sections()
    tables = [(_r418_B("30"), "2026-08-30"), (_r418_B("31"), "2026-08-31")]
    sw = pt.channel_sweep(_r418_fires(), tables, pt.STEAL_CHANNEL,
                          [4096, 1 << 20, pt.LEDGER_MIN_BYTES,
                           1 << 25, 1 << 27, 1 << 30])
    assert [r["n_costly_buckets"] for r in sw] == [7, 7, 7, 7, 7, 3]
    assert all(r["supported"] == [] for r in sw)
    assert all(r["n_units_tested"] == 16 for r in sw)


def test_the_steal_null_has_power_where_the_swap_null_did_not():
    """Round 412's whole point. `supported: []` on the steal channel is a
    statement about the box, because 9 of 16 units WERE testable and 44 % of
    occupancies could have cleared the bar."""
    fires = _r418_fires()
    ev = pt.attribution_evidence([
        pt.cost_ledger(fires, _r418_B("30"), "2026-08-30",
                       channel=pt.STEAL_CHANNEL, min_bytes=pt.LEDGER_MIN_BYTES),
        pt.cost_ledger(fires, _r418_B("31"), "2026-08-31",
                       channel=pt.STEAL_CHANNEL, min_bytes=pt.LEDGER_MIN_BYTES)])
    assert (ev["n_buckets"], ev["n_costly_buckets"]) == (218, 7)
    assert (ev["n_units_tested"], ev["n_testable_units"]) == (16, 9)
    assert ev["supported"] == [] and ev["supported_was_reachable"] is True
    assert round(ev["power"]["testable_fraction_of_N"], 4) == 0.4404


def test_fwupd_refresh_is_the_first_unit_this_record_can_nearly_support():
    """4 of 7 costly buckets, 2 of them held alone, p_chance 0.0154 -- the
    smallest p any unit has reached on any channel here -- and still
    `coincidence`, because 16-way Bonferroni puts it at 0.246. Its
    `consistency` of 0.111 is the reason it cannot be rescued: it fires 36
    times and moves the reclaim channel 4 times."""
    fires = _r418_fires()
    ev = pt.attribution_evidence([
        pt.cost_ledger(fires, _r418_B("30"), "2026-08-30",
                       channel=pt.STEAL_CHANNEL, min_bytes=pt.LEDGER_MIN_BYTES),
        pt.cost_ledger(fires, _r418_B("31"), "2026-08-31",
                       channel=pt.STEAL_CHANNEL, min_bytes=pt.LEDGER_MIN_BYTES)])
    u = next(x for x in ev["units"] if x["unit"] == "fwupd-refresh")
    assert (u["n_fires"], u["n_costly"], u["n_clean"]) == (36, 4, 2)
    assert round(u["p_chance"], 4) == 0.0154
    assert round(u["p_family"], 4) == 0.2461
    assert u["testable"] is True and u["verdict"] == "coincidence"


def test_the_biggest_reclaim_on_the_record_has_no_named_fire():
    """22 GB of sa30's reclaim falls in three buckets between 13:30 and 15:10
    that no systemd unit start covers -- the engine load, which runs as a user
    process (round 400's deployment drift), not as a system unit."""
    led = pt.cost_ledger(_r418_fires(), _r418_B("30"), "2026-08-30",
                         channel=pt.STEAL_CHANNEL,
                         min_bytes=pt.LEDGER_MIN_BYTES)
    assert led["costly_buckets_without_a_named_fire"] == [
        "13:30:05", "15:00:05", "15:10:03"]
    assert led["n_costly_buckets"] == 4


# ------------------------------------------------------------------- CLI


def test_cli_reclaim(tmp_path):
    f = tmp_path / "b31.txt"
    f.write_text(_r418_sections()["SAR_B_SA31"])
    out = _run("reclaim", "--sar-b", str(f), "--date", "2026-08-31")
    assert out.returncode == 0, out.stderr
    d = json.loads(out.stdout)
    assert d["largest_bucket"]["time"] == "04:00:03"
    assert d["double_count"]["ceiling_restored"] is True


def test_cli_gap(tmp_path):
    secs = _r418_sections()
    b = tmp_path / "b31.txt"; b.write_text(secs["SAR_B_SA31"])
    r = tmp_path / "r31.txt"; r.write_text(secs["SAR_R_SA31"])
    out = _run("gap", "--sar-b", str(b), "--sar-r", str(r))
    assert out.returncode == 0, out.stderr
    at = {g["time"]: g for g in json.loads(out.stdout)}
    assert at["04:00:03"]["level_bytes"] == 0


def test_cli_ledger_stitch_prev(tmp_path):
    secs = _r418_sections()
    p30 = tmp_path / "r30.txt"; p30.write_text(secs["SAR_R_SA30"])
    p31 = tmp_path / "r31.txt"; p31.write_text(secs["SAR_R_SA31"])
    base = ["ledger", "--sar-w", str(p31),
            "--journal", str(_CAP / "unit-starts.txt"),
            "--date", "2026-08-31", "--channel", "commit",
            "--min-bytes", str(50_000 * 1024)]
    no = json.loads(_run(*base).stdout)
    yes_run = _run(*base, "--stitch-prev", f"{p30}:2026-08-30")
    assert yes_run.returncode == 0, yes_run.stderr
    yes = json.loads(yes_run.stdout)
    assert (no["n_unclassified"], yes["n_unclassified"]) == (3, 0)
    assert yes["stitch"]["span_s"] == 1200


def test_cli_sweep_stitch_flag(tmp_path):
    secs = _r418_sections()
    days = []
    for d in ("30", "31"):
        p = tmp_path / f"r{d}.txt"; p.write_text(secs[f"SAR_R_SA{d}"])
        days += ["--day", f"{p}:2026-08-{d}"]
    out = _run("sweep", *days, "--journal", str(_CAP / "unit-starts.txt"),
               "--channel", "commit", "--thresholds", "51200000", "--stitch")
    assert out.returncode == 0, out.stderr
    row = json.loads(out.stdout)[0]
    # sa30 has no predecessor among the --day files, so it gets no entry at
    # all -- "not stitched because its previous day was not supplied" is not
    # the same fact as "not stitchable", and auto_stitches keeps them apart.
    assert row["stitched_days"] == ["2026-08-31"]
    assert row["unstitchable_days"] == {}
    assert row["n_units_tested"] == 16


# =====================================================================
# Round 424 (NUC-integration E). Round 418 inferred a factor-of-two double
# count in `pgsteal` from the shape of the data and wrote down the command
# that would settle it. Round 424 ran that command and it settled nothing;
# a different instrument settled it instead.
# =====================================================================

SADC_STRINGS_REAL = """pgscan_direct
pgscan_kswapd
pgsteal_
"""

VMSTAT_FRESH_BOOT = """pgsteal_kswapd 0
pgsteal_direct 0
pgsteal_khugepaged 0
pgscan_kswapd 0
pgscan_direct 0
pgscan_khugepaged 0
pgscan_direct_throttle 0
pgscan_anon 0
pgscan_file 0
pgsteal_anon 0
pgsteal_file 0
"""

VMSTAT_BUSY = VMSTAT_FRESH_BOOT.replace(
    "pgsteal_kswapd 0", "pgsteal_kswapd 900").replace(
    "pgsteal_anon 0", "pgsteal_anon 300").replace(
    "pgsteal_file 0", "pgsteal_file 600")


def test_the_literal_route_finds_the_asymmetry_that_makes_the_divisor_two():
    """`pgsteal_` is a bare prefix and matches BOTH complete partitions of the
    same events; `pgscan_kswapd`/`pgscan_direct` are full names and match one
    each. Numerator doubled, denominator not."""
    ev = pt.steal_double_count_evidence(SADC_STRINGS_REAL, VMSTAT_FRESH_BOOT)
    assert ev["literal_route"] == "double-counted"
    assert ev["divisor"] == pt.RECLAIM_STEAL_DIVISOR == 2
    assert ev["steal_partitions_hit"]["actor"] == [
        "pgsteal_direct", "pgsteal_khugepaged", "pgsteal_kswapd"]
    assert ev["steal_partitions_hit"]["by_type"] == ["pgsteal_anon", "pgsteal_file"]
    assert ev["n_steal_fields_summed"] == 5


def test_the_bare_prefix_is_not_itself_a_field_and_is_not_counted_as_one():
    """`pgsteal_` names no vmstat field. Counting the literal itself put the
    summed total at 6 where the collector sums 5."""
    ev = pt.steal_double_count_evidence(SADC_STRINGS_REAL, VMSTAT_FRESH_BOOT)
    assert "pgsteal_" not in pt.parse_vmstat_fields(VMSTAT_FRESH_BOOT)
    assert ev["n_steal_fields_summed"] == 5
    # ...whereas `pgscan_kswapd` IS a field, and counts itself
    assert ev["n_scan_fields_per_literal"]["pgscan_kswapd"] == 1


def test_the_counter_route_on_a_fresh_boot_is_named_vacuous_not_confirmed():
    """The whole methodological point. Round 418's falsification command was
    `grep -E '^pg(scan|steal)' /proc/vmstat`, to be checked for
    `anon+file == kswapd+direct+khugepaged`. Round 424 ran it 2h40m after a
    reboot: all fourteen counters read 0, the identity held as 0 == 0, and it
    measured nothing. Reporting that as agreement is how a vacuous test gets
    quoted as a measurement."""
    ev = pt.steal_double_count_evidence(SADC_STRINGS_REAL, VMSTAT_FRESH_BOOT)
    assert ev["counters_all_zero"] is True
    assert ev["counter_route"].startswith("vacuous")
    assert "agree" not in ev["counter_route"].split("--")[0]
    # ...and the verdict does NOT depend on it
    assert ev["divisor"] == 2


def test_the_counter_route_agrees_once_the_box_has_actually_reclaimed():
    ev = pt.steal_double_count_evidence(SADC_STRINGS_REAL, VMSTAT_BUSY)
    assert ev["counters_all_zero"] is False
    assert ev["actor_partition_sum"] == ev["type_partition_sum"] == 900
    assert ev["counter_route"] == "agree"


def test_a_collector_that_reads_one_partition_is_reported_single_not_doubled():
    """The refutation path has to work or the test is decoration. A kernel or
    sysstat that names the actor fields individually implies no double count."""
    single = "pgscan_direct\npgscan_kswapd\npgsteal_kswapd\npgsteal_direct\n"
    ev = pt.steal_double_count_evidence(single, VMSTAT_FRESH_BOOT)
    assert ev["literal_route"] == "single"
    assert ev["divisor"] == 1
    assert ev["steal_partitions_hit"]["by_type"] == []
    assert "no double count is implied" in ev["why"]


def test_the_scan_side_has_its_own_smaller_overmatch_in_the_other_direction():
    """`pgscan_direct` is a full name but still a prefix of
    `pgscan_direct_throttle`, a SUBSET counter. It reads 0 on any box not under
    allocator pressure -- which is every sample this program has -- but it
    inflates the DENOMINATOR, i.e. biases %vmeff the opposite way."""
    ev = pt.steal_double_count_evidence(SADC_STRINGS_REAL, VMSTAT_FRESH_BOOT)
    assert ev["scan_subset_overmatch"] == ["pgscan_direct_throttle"]
    assert ev["n_scan_fields_per_literal"]["pgscan_direct"] == 2


# ------------------------------------------- the corrected view, carried beside

R424_SAR_B = """08:00:01     pgpgin/s pgpgout/s   fault/s  majflt/s   pgfree/s pgscank/s pgscand/s pgsteal/s    %vmeff
08:10:01         0.00      0.00     10.00      0.00     100.00     55.44      0.00    110.88    200.00
"""


def test_reported_columns_are_untouched_and_the_correction_rides_alongside():
    """Round 418's rule survives confirmation: a silently halved byte count is
    the kind of number that gets quoted without its caveat. The raw columns
    still say what the file says; the caller has to name `corrected_*`."""
    ev = pt.reclaim_events(pt.parse_sar(R424_SAR_B))[0]
    assert ev.steal_s == 110.88            # as sysstat reported it
    assert ev.vmeff_pct == pytest.approx(200.0)
    assert ev.steal_exceeds_scan is True
    assert ev.corrected_steal_s == pytest.approx(55.44)
    assert ev.corrected_vmeff_pct == pytest.approx(100.0)
    assert ev.corrected_stolen_bytes * 2 == ev.stolen_bytes


def test_the_exact_two_point_zero_ratio_is_in_the_banked_r400_capture():
    """`sa30 14:50:05` reads pgscank 55.44 / pgsteal 110.88 -- 2.000x to the
    digit. A noisy undercount of pgscan does not land on a round number."""
    ev = pt.reclaim_events(pt.parse_sar(R424_SAR_B))[0]
    assert ev.steal_s / ev.scan_kswapd_s == pytest.approx(2.0, abs=1e-9)


def test_correcting_the_numerator_separates_clean_eviction_from_struggling_reclaim():
    """The payoff. Published as an upper bound, six of seven buckets are just
    'impossible'. Halved, five sit at ~100 % -- every page kswapd looked at, it
    took, which is what evicting clean file-backed cache looks like -- and the
    04:00:03 event stands out at 16.6 %, the one place reclaim actually had to
    work for it. That distinction is invisible while the numerator is doubled."""
    clean = pt.reclaim_events(pt.parse_sar(R424_SAR_B))[0]
    struggling = pt.reclaim_events(pt.parse_sar(
        R424_SAR_B.replace("55.44      0.00    110.88    200.00",
                           "1207.00      0.00    401.70     33.28")))[0]
    assert clean.corrected_vmeff_pct == pytest.approx(100.0)
    assert struggling.corrected_vmeff_pct == pytest.approx(16.64, abs=0.01)
    assert clean.corrected_vmeff_pct > 5 * struggling.corrected_vmeff_pct


# ------------------------------------------------------- round 430: the window
#
# Fixtures are the round-424 capture on disk, which is the whole point: this
# block exists because three rounds of analysis reached that capture only
# through a test helper, and the nine unread day-files were never pooled.

import pathlib as _pathlib430  # noqa: E402

_CAP430 = (_pathlib430.Path(__file__).resolve().parents[2]
           / "state" / "nuc-capture-r424")
_SAR430 = (_CAP430 / "sar-all.txt").read_text()
_JRNL430 = (_CAP430 / "journal-pid1-full.txt").read_text()
_COLLECTOR430 = (_CAP430 / "collector-evidence.txt").read_text()


def _collector_halves():
    lits = _COLLECTOR430.split("### SADC_VMSTAT_LITERALS")[1].split("###")[0]
    vm = _COLLECTOR430.split("### PROC_VMSTAT_RECLAIM_FIELDS")[1].split("###")[0]
    return lits, vm


def test_sar_sections_splits_the_banked_capture():
    secs = pt.sar_sections(_SAR430)
    assert len(secs) == 101
    assert len([k for k in secs if k.startswith("SAR_W_")]) == 10
    assert "SYSSTAT_FILES" in secs


def test_a_day_files_date_comes_from_its_own_banner_not_its_name():
    secs = pt.sar_sections(_SAR430)
    assert pt.sar_banner_date(secs["SAR_W_SA31"]) == "2026-08-31"
    # `SA01` is September, and nothing in the name says so.
    assert pt.sar_banner_date(secs["SAR_W_SA01"]) == "2026-09-01"


def test_a_section_with_no_banner_refuses_to_be_dated():
    with pytest.raises(pt.PerturbationError, match="banner"):
        pt.sar_banner_date("00:10:03   pswpout/s\n00:20:03   0.00\n")


def test_the_full_window_pairs_every_day_with_the_journal():
    f = pt.window_frame(_SAR430, _JRNL430)
    assert f["n_day_files"] == 10
    assert f["n_paired"] == 10
    assert f["n_sar_only"] == 0 and f["n_journal_only"] == 0
    assert f["dropped_dates"] == []
    assert f["n_buckets_poolable"] == 991
    assert f["n_journal_fires"] == 1652
    assert f["journal_first_event_utc"] == "2026-08-23T14:03:06Z"


def test_a_day_the_journal_is_silent_on_is_dropped_not_pooled():
    """Round 412's constraint, made mechanical. Widening a window is a
    false-POSITIVE hazard: an unpaired day adds buckets to N and fires to
    nothing, so every unit's p falls on strictly less evidence."""
    f = pt.window_frame(_SAR430, "\n".join(
        l for l in _JRNL430.splitlines() if not l.startswith("2026-08-26")))
    assert f["n_sar_only"] == 1
    assert f["dropped_dates"] == ["2026-08-26"]
    assert f["n_buckets_poolable"] < f["n_buckets_if_unpaired_pooled"]
    day = [d for d in f["days"] if d["date"] == "2026-08-26"][0]
    assert day["pairing"] == pt.PAIRING_SAR_ONLY
    assert "ZERO non-instrument unit starts" in day["why"]


def test_a_journal_date_with_no_sar_section_is_reported_not_ignored():
    f = pt.window_frame(_SAR430, _JRNL430 + (
        "\n2026-09-09T01:02:03+00:00 pgain-nuc systemd[1]: "
        "Starting fstrim.service - Discard unused blocks.\n"))
    assert f["n_journal_only"] == 1
    day = [d for d in f["days"] if d["date"] == "2026-09-09"][0]
    assert day["pairing"] == pt.PAIRING_JOURNAL_ONLY
    assert day["n_rows"] == 0


def test_a_banner_that_disagrees_with_the_file_name_raises():
    secs = pt.sar_sections(_SAR430)
    bad = _SAR430.replace(
        "### SAR_W_SA31\nLinux 6.8.0-138-generic (pgain-nuc) \t08/31/26",
        "### SAR_W_SA31\nLinux 6.8.0-138-generic (pgain-nuc) \t08/30/26", 1)
    assert bad != _SAR430 and "SAR_W_SA31" in secs
    with pytest.raises(pt.PerturbationError, match="file name says day"):
        pt.window_frame(bad, _JRNL430)


def test_the_full_window_swap_run_is_the_records_real_shape():
    """N 218 -> 991 and K 3 -> 52. Every ledger, evidence, sweep and power
    number this program published before round 430 came off two day-files."""
    out = pt.window_attribution(_SAR430, _JRNL430)
    ev = out["evidence"]
    assert ev["n_buckets"] == 991
    assert ev["n_costly_buckets"] == 52
    assert ev["n_units_tested"] == 26
    assert ev["supported"] == []
    assert ev["power"]["max_testable_occupancy"] == 881


def test_supported_was_unreachable_for_a_reason_power_floor_cannot_see():
    """Round 412 built `power_floor` for the CHANCE gate and it reports
    `supported_was_reachable: True` here. There are six gates and the pass
    sets do not intersect: the units that fire alone fire hourly, and the
    units that are surprising never fire alone."""
    out = pt.window_attribution(_SAR430, _JRNL430)
    assert out["evidence"]["supported_was_reachable"] is True
    g = out["gates"]
    assert g["supported_reachable_all_gates"] is False
    assert g["all_gates_passed"] == []
    assert g["pass_sets"]["separable"] == ["fwupd-refresh", "man-db",
                                           "motd-news"]
    assert g["pass_sets"]["chance"] == ["apt-daily", "apt-news", "esm-cache",
                                        "packagekit"]
    assert not (set(g["pass_sets"]["separable"]) & set(g["pass_sets"]["chance"]))


def test_exactly_one_gate_stands_between_three_units_and_supported():
    g = pt.window_attribution(_SAR430, _JRNL430)["gates"]
    assert g["single_gate_from_supported"] == {
        "separable": ["apt-news", "esm-cache", "packagekit"]}
    assert g["blocking_gate_histogram"]["separable"] == 9


def test_verdict_floor_says_reachable_when_a_unit_clears_every_gate():
    """The negative case has to be able to come back positive or it is not a
    measurement. Round 406's `supported: []` is the cautionary example."""
    ok = pt.verdict_floor({
        "max_family_p": 0.05, "min_consistency": 0.5, "min_fires": 2,
        "units": [{"unit": "u", "n_fires": 4, "n_costly": 3, "n_clean": 2,
                   "testable": True, "p_family": 0.001, "consistency": 0.75,
                   "verdict": "supported"}]})
    assert ok["supported_reachable_all_gates"] is True
    assert ok["all_gates_passed"] == ["u"]
    assert ok["per_unit"][0]["gates_failed"] == []


def test_packagekit_is_the_universal_confounder_of_this_deployment():
    """`shared-only` reports a fact about a unit; the fact is about a pair.
    PackageKit sits in every costly bucket eleven other units occupy, and in two
    more of its own -- so nothing in the apt or fwupd family can ever be
    sole-attributable while it exists."""
    c = pt.window_attribution(_SAR430, _JRNL430)["cofires"]
    assert c["n_costly_buckets_with_a_named_fire"] == 19
    assert c["n_sole_occupied"] == 11
    assert c["max_units_in_one_bucket"] == 9
    assert c["sole_occupants"] == ["fwupd-refresh", "man-db", "motd-news"]
    assert len(c["one_way_confounders"]) == 11
    assert all("packagekit" in v for v in c["one_way_confounders"].values())
    assert "packagekit" not in c["never_without"]


def test_only_63_percent_of_costly_buckets_have_any_named_fire_at_all():
    out = pt.window_attribution(_SAR430, _JRNL430)
    K = out["evidence"]["n_costly_buckets"]
    named = out["cofires"]["n_costly_buckets_with_a_named_fire"]
    assert (K, named) == (52, 19)
    assert K - named == 33


def test_inseparable_classes_are_mutual_only():
    c = pt.costly_bucket_cofires(
        [{"date": "d", "entries": [
            {"unit": "a", "bucket_end": "1", "bucket_bytes": 9, "costly": True,
             "bucket_shared_by": 2},
            {"unit": "b", "bucket_end": "1", "bucket_bytes": 9, "costly": True,
             "bucket_shared_by": 2},
            {"unit": "b", "bucket_end": "2", "bucket_bytes": 9, "costly": True,
             "bucket_shared_by": 1}]}])
    # `a` is never without `b`; `b` IS seen without `a`, so they do not merge.
    assert c["never_without"] == {"a": ["b"]}
    assert c["one_way_confounders"] == {"a": ["b"]}
    assert pt.inseparable_classes(c) == []


def test_a_class_on_one_observation_is_not_a_class():
    """Four boot-time units share the 08-30 restart bucket and nothing else.
    'They always co-occur' over a single bucket restates the bucket."""
    cls = pt.inseparable_classes(
        pt.costly_bucket_cofires(pt._round430_ledgers_for_test())
        if hasattr(pt, "_round430_ledgers_for_test") else
        pt.costly_bucket_cofires([{"date": "d", "entries": [
            {"unit": u, "bucket_end": "1", "bucket_bytes": 9, "costly": True,
             "bucket_shared_by": 3} for u in ("x", "y", "z")]}]))
    assert len(cls) == 1
    assert cls[0]["n_costly_buckets_of_class"] == 1
    assert cls[0]["testable_as_a_class"] is False


def test_merging_the_apt_trio_does_not_rescue_it():
    """The composite hypothesis the record CAN carry, run honestly -- and it
    still fails, because the confounding is DIRECTED: packagekit is in every
    bucket the trio occupies and in two more, so the trio can never be alone
    and packagekit is not attributable either."""
    cl = pt.window_attribution(_SAR430, _JRNL430)["clusters"]
    assert cl["merged_labels"] == ["apt-daily+apt-news+esm-cache",
                                   "fwupd+modprobe@sd_mod"]
    ev = cl["evidence"]
    assert ev["n_units_tested"] == 23        # 26 units -> 23 hypotheses
    assert ev["supported"] == []
    trio = [u for u in ev["units"]
            if u["unit"] == "apt-daily+apt-news+esm-cache"][0]
    assert trio["verdict"] == "shared-only"
    assert trio["n_clean"] == 0


def test_this_capture_has_no_unpaired_days_so_the_wide_number_is_clean():
    """`unpaired_inflation` earns its keep by coming back EMPTY: the pooled
    N was not bought by counting buckets from days the journal cannot see."""
    inf = pt.unpaired_inflation(_SAR430, _JRNL430)
    assert inf["comparable"] is True
    assert inf["n_dropped_days"] == 0
    assert inf["n_buckets_paired"] == inf["n_buckets_with_unpaired"] == 991
    assert inf["units_whose_p_moved"] == []


def test_window_refuses_when_nothing_is_poolable():
    with pytest.raises(pt.PerturbationError, match="no poolable day-file"):
        pt.window_attribution(_SAR430, "")


def test_window_cli_frame_only_is_clean_on_this_capture():
    r = subprocess.run(
        [sys.executable, "nuc/perturbation.py", "window",
         "--capture", str(_CAP430), "--frame-only", "--strict"],
        capture_output=True, text=True,
        cwd=str(_pathlib430.Path(__file__).resolve().parents[2]))
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["n_paired"] == 10


# ------------------------------- round 430: the correction that was incomplete


def test_pages_stolen_with_zero_pages_scanned_are_flagged_not_ranked_last():
    """`vmeff_pct` is documented '0 if no scan', so sa23 22:40 -- 4087.96
    pgsteal/s against 0.00 scanned -- renders as 0.000 %, the BOTTOM of an
    efficiency ranking, when it is an undefined ratio and the sharpest
    possible violation of steal <= scan."""
    secs = pt.sar_sections(_SAR430)
    evs = pt.reclaim_events(pt.parse_sar(secs["SAR_B_SA23"]))
    free = [e for e in evs if e.scan_free_steal]
    assert len(free) == 5
    e = [x for x in free if x.time == "21:40:03"][0]
    assert (e.scan_kswapd_s, e.scan_direct_s) == (0.0, 0.0)
    assert e.steal_s == 4087.96
    assert e.vmeff_defined is False
    assert e.vmeff_pct == 0.0 and e.corrected_vmeff_pct == 0.0
    assert e.steal_exceeds_scan is True


def test_the_factor_of_two_holds_on_the_two_days_anyone_had_looked_at():
    """Round 418's result is not overturned; it is scoped. sa30 and sa31 both
    still return `ceiling_restored: True`."""
    secs = pt.sar_sections(_SAR430)
    for day in ("SAR_B_SA30", "SAR_B_SA31"):
        chk = pt.reclaim_double_count_check(
            pt.reclaim_events(pt.parse_sar(secs[day])))
        assert chk["ceiling_restored"] is True, day
        assert chk["n_scan_free_steal"] == 0


def test_and_fails_on_the_eight_days_nobody_had():
    secs = pt.sar_sections(_SAR430)
    evs = []
    for k in sorted(s for s in secs if s.startswith("SAR_B_")):
        evs += pt.reclaim_events(pt.parse_sar(secs[k]))
    assert len(evs) == 108
    chk = pt.reclaim_double_count_check(evs)
    assert chk["ceiling_restored"] is False
    assert chk["n_scan_free_steal"] == 21
    assert chk["n_over_ceiling_reported"] == 66
    assert chk["n_over_ceiling_corrected"] == 8
    assert chk["max_corrected_pct"] > 3000
    assert "no divisor can fix" in chk["why"]


def test_the_dropped_buckets_are_counted_now_instead_of_filtered_silently():
    """The `scan > 0` filter has been in this function since round 418 and it
    dropped exactly the strongest counter-examples to the theorem the function
    tests, without saying how many."""
    secs = pt.sar_sections(_SAR430)
    evs = pt.reclaim_events(pt.parse_sar(secs["SAR_B_SA23"]))
    chk = pt.reclaim_double_count_check(evs)
    assert chk["n_events"] + chk["n_scan_free_steal"] == len(evs)
    assert chk["scan_free_steal_buckets"] == ["21:40:03", "21:50:01",
                                             "22:10:03", "22:20:03",
                                             "22:30:03"]


def test_the_denominator_omits_a_whole_reclaim_path_the_numerator_keeps():
    """The mechanism, from the SAME banked file round 424 read the numerator
    half out of -- one section further down. `pgscan_khugepaged` is exported
    by the kernel and is not a sadc literal, while `pgsteal_` collects
    `pgsteal_khugepaged`. Reported %vmeff is 2T/(S - S_khuge), so the residual
    is unbounded rather than a second constant, and undefined when khugepaged
    does all the work."""
    lits, vm = _collector_halves()
    u = pt.scan_undercount_evidence(lits, vm)
    assert u["denominator_is_complete"] is False
    assert u["actor_fields_omitted"] == ["pgscan_khugepaged"]
    assert u["steal_counterpart_collected"] == ["pgsteal_khugepaged"]
    assert "unbounded" in u["why"]


def test_a_collector_that_read_every_scan_field_would_report_complete():
    lits, vm = _collector_halves()
    u = pt.scan_undercount_evidence(lits + "\npgscan_khugepaged\n", vm)
    assert u["denominator_is_complete"] is True
    assert u["actor_fields_omitted"] == []
    assert "denominator is complete" in u["why"]


def test_round_424s_numerator_finding_is_untouched_by_the_new_half():
    """Both halves are real and they are different defects: the numerator is
    doubled (a constant) and the denominator is short one path (unbounded)."""
    lits, vm = _collector_halves()
    d = pt.steal_double_count_evidence(lits, vm)
    assert d["literal_route"] == "double-counted"
    assert d["divisor"] == 2
    assert pt.scan_undercount_evidence(lits, vm)["n_omitted"] == 1
