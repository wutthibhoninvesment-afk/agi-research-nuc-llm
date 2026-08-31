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
