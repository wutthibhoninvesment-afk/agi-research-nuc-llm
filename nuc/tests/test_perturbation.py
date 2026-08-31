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
    assert led["entries"][0]["bucket_swapped_bytes"] == round(27.54 * 600) * 4096


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


def test_total_swapped_bytes_sums_distinct_buckets_not_fires():
    """Summing per-fire bytes reported 799 MB for a day whose real total is
    289 MB. The bucket's cost is a property of the bucket."""
    t = _swap_table([("03:50:05", 0.00), ("04:00:03", 89.88)])
    one = cost_ledger(_fires(("03:57:05", "fwupd-refresh")), t, "2026-08-31")
    three = cost_ledger(_fires(("03:50:05", "apt-daily"), ("03:50:09", "packagekit"),
                               ("03:57:05", "fwupd-refresh")), t, "2026-08-31")
    assert one["total_swapped_bytes"] == three["total_swapped_bytes"]


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


def test_a_unit_whose_own_fires_are_mostly_free_is_a_coincidence():
    """The refutation in miniature: one expensive bucket, many zero ones."""
    entries = [_entry("fwupd-refresh", "02:00:05", 67_682_304)]
    entries += [_entry("fwupd-refresh", f"{h:02d}:00:05", 0) for h in range(3, 20)]
    ev = attribution_evidence([_ledger(entries, 79, 1)])["units"][0]
    assert ev["n_fires"] == 18 and ev["n_zero_byte"] == 17
    assert ev["consistency"] == pytest.approx(1 / 18)
    assert ev["verdict"] == "coincidence"


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
    assert sole[0]["bucket_swapped_bytes"] == 67_682_304


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
    assert ev["verdict"] == "coincidence"


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
    assert got["units"][0]["verdict"] == "coincidence"
    assert got["n_units_tested"] == 16      # the filter must not shrink the family
