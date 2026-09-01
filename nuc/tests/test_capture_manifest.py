"""Tests for nuc/capture_manifest.py (round 406).

The module exists because round 400's capture was filtered in a way nothing
recorded, and round 406 designed an analysis against a field that had never
been captured before discovering it was absent. So the tests are mostly about
the module's ability to say NO: to report a gap rather than audit half a
capture quietly, and to name the right `sar` flag when it does.

`state/nuc-capture-r400/` is read directly by the last group. It is the only
copy of that data off a box that has been unreachable since
2026-08-31T16:30:00.1Z, and these tests are deliberately not skipped when it is
absent -- a missing capture is the failure, not a reason to pass.

Nothing here opens a socket or runs a command against the NUC, so this file is
safe to run from any track and cannot contact port 8001.
"""
import json
import pathlib
import subprocess
import sys

import pytest

from nuc import capture_manifest as cm


ROOT = pathlib.Path(__file__).resolve().parents[2]
CAP400 = ROOT / "state" / "nuc-capture-r400"


# ------------------------------------------------------------------- fixtures

SAR_TWO_DAYS = """### SYSSTAT_FILES
-rw-r--r--  1 root root   121012 Aug 30 23:50 sa30
-rw-r--r--  1 root root   121012 Aug 31 13:10 sa31
### SAR_R_SA30
00:10:05    kbmemfree
### SAR_R_SA31
00:10:05    kbmemfree
### SAR_W_SA30
00:10:05     pswpin/s pswpout/s
### SAR_W_SA31
00:10:05     pswpin/s pswpout/s
"""

JOURNAL_FILTERED = """2026-08-31T01:57:33+00:00 nuc systemd[1]: Starting fwupd-refresh.service - x...
2026-08-31T02:00:05+00:00 nuc systemd[1]: Starting sysstat-collect.service - y...
2026-08-31T02:00:06+00:00 nuc systemd[1]: Started packagekit.service - z.
"""

JOURNAL_FULL = JOURNAL_FILTERED + (
    "2026-08-31T01:57:41+00:00 nuc systemd[1]: Finished fwupd-refresh.service - x.\n"
    "2026-08-31T02:00:07+00:00 nuc systemd[1]: Finished sysstat-collect.service - y.\n"
    "2026-08-31T03:00:00+00:00 nuc systemd[1]: Failed apt-news.service - w.\n"
)

# ROUND 424: every line above is dated 08-31, and the fixtures it is paired
# with declare day files sa30 AND sa31. That was invisible until `audit` grew
# `journal_span_coverage`, which is the point -- the same one-day-short shape
# is what `journalctl -b` produced against a nine-day archive on the real box.
JOURNAL_FULL_BOTH_DAYS = JOURNAL_FULL + (
    "2026-08-30T04:00:03+00:00 nuc systemd[1]: Starting dpkg-db-backup.service - z.\n"
    "2026-08-30T04:00:09+00:00 nuc systemd[1]: Finished dpkg-db-backup.service - z.\n"
)


# --------------------------------------------------------------- sar coverage

def test_sar_coverage_pairs_each_activity_with_the_days_it_covers():
    cov = cm.sar_coverage(SAR_TWO_DAYS)
    assert cov["day_files_on_box"] == ["30", "31"]
    assert cov["by_activity"] == {"R": ["30", "31"], "W": ["30", "31"]}


def test_sar_coverage_reads_multi_character_keys():
    """`capture_plan` emits SWAPSPACE/NET/CSW to break the -B/-b collision. A
    single-letter regex could not read back the markers its own plan writes."""
    cov = cm.sar_coverage("### SAR_SWAPSPACE_SA31\n### SAR_NET_SA31\n")
    assert set(cov["by_activity"]) == {"SWAPSPACE", "NET"}


def test_an_activity_missing_on_only_some_days_names_those_days():
    text = SAR_TWO_DAYS + "### SAR_B_SA31\n00:10:05  pgpgin/s\n"
    gaps = cm.audit(text, JOURNAL_FULL)["gaps"]
    b = [g for g in gaps if g["missing"].startswith("`sar -B`")]
    assert len(b) == 1
    assert "sa30" in b[0]["missing"] and "sa31" not in b[0]["missing"]


# ----------------------------------------------------------- the flag-case bug

def test_the_required_paging_activity_is_named_dash_B_not_dash_b():
    """`-B` is paging; `-b` is block I/O. They are different activities that
    upper-case to the same marker letter, and the first draft of this module
    printed the wrong one in the remediation it emits."""
    gaps = cm.audit(SAR_TWO_DAYS, JOURNAL_FULL)["gaps"]
    missing = [g["missing"] for g in gaps]
    assert any(m.startswith("`sar -B`") for m in missing)
    assert any(m.startswith("`sar -b`") for m in missing)
    paging = next(g for g in gaps if g["missing"].startswith("`sar -B`"))
    blockio = next(g for g in gaps if g["missing"].startswith("`sar -b`"))
    assert paging["blocking"] is True          # a nuc/ module parses it
    assert blockio["blocking"] is False        # nothing reads it yet


def test_every_activity_key_and_flag_is_unique():
    assert len({a.key for a in cm.ACTIVITIES}) == len(cm.ACTIVITIES)
    assert len({a.flag for a in cm.ACTIVITIES}) == len(cm.ACTIVITIES)


# ----------------------------------------------------------- journal coverage

def test_a_starting_only_journal_reports_no_derivable_durations():
    cov = cm.journal_coverage(JOURNAL_FILTERED)
    assert cov["kinds"] == {"Started": 1, "Starting": 2}
    assert cov["n_starting_events"] == 2
    assert cov["durations_derivable"] == 0
    assert cov["durations_missing"] == 2
    assert set(cov["units_never_closed"]) == {"fwupd-refresh", "sysstat-collect"}


def test_a_full_journal_closes_every_start():
    cov = cm.journal_coverage(JOURNAL_FULL)
    assert cov["durations_derivable"] == 2
    assert cov["durations_missing"] == 0
    assert cov["units_never_closed"] == []
    assert cov["first_utc"] == "2026-08-31T01:57:33"
    assert cov["last_utc"] == "2026-08-31T03:00:00"


def test_a_missing_finished_kind_is_a_BLOCKING_gap():
    """This is the exact gap that stopped round 406 running the test round 400
    asked for. If it is ever downgraded to advisory, this fails."""
    res = cm.audit(SAR_TWO_DAYS, JOURNAL_FILTERED)
    fin = next(g for g in res["gaps"] if "Finished" in g["missing"])
    assert fin["blocking"] is True
    assert fin["recoverable"] == "only-on-box"
    assert res["verdict"] == "filtered"


# ------------------------------------------------------------------- the plan

def test_the_generated_plan_is_valid_bash():
    plan = cm.capture_plan(cm.audit(SAR_TWO_DAYS, JOURNAL_FILTERED))
    out = subprocess.run(["bash", "-n"], input=plan, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_the_plan_captures_the_binary_files_and_an_unfiltered_journal():
    plan = cm.capture_plan(cm.audit(SAR_TWO_DAYS, JOURNAL_FILTERED))
    assert "tar -C /var/log/sysstat" in plan
    # ROUND 424: this asserted the `-b` form. `-b` is the defect -- the plan
    # runs only when the box is reachable, and the box became reachable by
    # rebooting, so `-b` banked 2h40m of a nine-day archive. Inverted, so the
    # scoping cannot come back without failing here.
    assert "journalctl -o short-iso --no-pager _PID=1" in plan
    assert "journalctl -b " not in plan
    assert "Starting" not in plan.split("journalctl")[1].split("\n")[0]
    assert "8001" in plan            # named, as a prohibition
    assert "--strict" in plan        # it verifies itself


def test_the_plan_asks_for_every_activity_with_its_real_flag():
    plan = cm.capture_plan(cm.audit(SAR_TWO_DAYS, JOURNAL_FILTERED))
    for a in cm.ACTIVITIES:
        assert f"{a.key}:{a.flag.replace(' ', '=')}" in plan


def test_a_capture_matching_the_plans_markers_audits_as_COMPLETE():
    """Round-trip: emit the plan's marker scheme, feed it back, expect no
    blocking gap. Without this the plan could keep writing markers the auditor
    cannot read and every audit would look like a total capture failure."""
    lines = ["### SYSSTAT_FILES", "sa30", "sa31"]
    for a in cm.ACTIVITIES:
        for day in ("30", "31"):
            lines.append(f"### SAR_{a.key}_SA{day}")
    # ROUND 424: was `JOURNAL_FULL`, which is dated 08-31 only while the marker
    # block declares sa30 and sa31. It passed because `audit` graded line KINDS
    # and never asked which DAYS they covered.
    res = cm.audit("\n".join(lines) + "\n", JOURNAL_FULL_BOTH_DAYS)
    assert res["n_blocking_gaps"] == 0
    assert res["n_gaps"] == 0
    assert res["verdict"] == "complete"
    assert res["span"]["uncovered"] == []


def test_the_round_trip_capture_one_day_short_is_narrow_not_complete():
    """The half of the round-trip that used to pass silently."""
    lines = ["### SYSSTAT_FILES", "sa30", "sa31"]
    for a in cm.ACTIVITIES:
        for day in ("30", "31"):
            lines.append(f"### SAR_{a.key}_SA{day}")
    res = cm.audit("\n".join(lines) + "\n", JOURNAL_FULL)   # 08-31 only
    assert res["verdict"] == "narrow"
    assert res["span"]["uncovered"] == ["30"]
    assert res["n_blocking_gaps"] == 1


# ---------------------------------------------------------------------- io/cli

def test_a_capture_dir_missing_a_source_errors_rather_than_auditing_half(tmp_path):
    (tmp_path / "sar-all.txt").write_text(SAR_TWO_DAYS)
    with pytest.raises(cm.CaptureManifestError):
        cm.audit_dir(str(tmp_path))


def test_cli_audit_strict_exits_nonzero_on_a_filtered_capture(tmp_path):
    (tmp_path / "sar-all.txt").write_text(SAR_TWO_DAYS)
    (tmp_path / "unit-starts.txt").write_text(JOURNAL_FILTERED)
    for strict, want in ((False, 0), (True, 1)):
        argv = ["audit", "--capture", str(tmp_path)] + (["--strict"] if strict else [])
        out = subprocess.run([sys.executable, "nuc/capture_manifest.py", *argv],
                             capture_output=True, text=True, cwd=str(ROOT))
        assert out.returncode == want, out.stderr
        json.loads(out.stdout)


def test_cli_reports_a_bad_capture_dir_as_an_error_not_a_traceback():
    out = subprocess.run(
        [sys.executable, "nuc/capture_manifest.py", "audit", "--capture", "/nope"],
        capture_output=True, text=True, cwd=str(ROOT))
    assert out.returncode == 2
    assert "capture-manifest ERROR" in out.stderr
    assert "Traceback" not in out.stderr


# ------------------------------------------- the real capture, as a regression

def test_the_round_400_capture_audits_as_filtered_with_ten_blocking_gaps():
    """ROUND 424: was three -- `-B` on 7 days, `Finished`, `Failed`. Two things
    moved, in opposite directions, and the net is +7.

    `Failed` came OFF the blocking list everywhere a terminal line witnesses an
    unfiltered capture; round 400's capture has none, so it stays blocking here
    and this fixture is now the only place that path is exercised on real data.

    And SEVEN window gaps appeared. Round 400 banked nine day files and a
    journal covering two of them, so its cost ledger could never have
    attributed a fire on sa23-sa29 -- there were no fires in the file. That was
    true the whole time and nothing reported it."""
    res = cm.audit_dir(str(CAP400))
    assert res["verdict"] == "filtered"
    assert res["n_blocking_gaps"] == 10
    assert res["unfiltered_witnesses"] == []
    assert res["span"]["uncovered"] == [str(d) for d in range(23, 30)]
    assert res["span"]["covered"] == ["30", "31"]
    assert res["sar"]["day_files_on_box"] == [str(d) for d in range(23, 32)]
    assert sorted(res["sar"]["by_activity"]) == ["B", "R", "W"]


def test_the_round_400_capture_lost_92_percent_of_its_own_durations():
    """330 of 358 fires, and every housekeeping unit in the cost ledger."""
    j = cm.audit_dir(str(CAP400))["journal"]
    assert j["n_starting_events"] == 358
    assert j["durations_derivable"] == 28
    assert j["durations_missing"] == 330
    assert j["durations_derivable_fraction"] == pytest.approx(28 / 358, abs=1e-4)
    for unit in ("fwupd-refresh", "apt-daily", "apt-news", "esm-cache"):
        assert unit in j["units_never_closed"]


# =====================================================================
# Round 424 (NUC-integration E). Every test below exists because running
# this module's own emitted plan against a live box exposed something the
# module could not see.
# =====================================================================

R424_SAR = """### SYSSTAT_FILES
-rw-r--r-- 1 root root  36324 Sep  1 08:10 sa01
-rw-r--r-- 1 root root 121012 Aug 23 23:50 sa23
-rw-r--r-- 1 root root 293704 Aug 24 23:50 sa24
-rw-r--r-- 1 root root 192798 Aug 24 00:07 sar23
-rw-r--r-- 1 root root 468081 Aug 25 00:07 sar24
### SAR_R_SA01
dummy
"""

def _sar_all_required(days):
    """A marker block covering every REQUIRED activity, so a test about the
    journal is not silently also a test about missing `sar -W`."""
    lines = ["### SYSSTAT_FILES"] + [f"sa{d}" for d in days]
    for key in cm.REQUIRED_SAR_ACTIVITIES:
        lines += [f"### SAR_{key}_SA{d}" for d in days]
    return "\n".join(lines) + "\n"


def _jline(day, kind, unit, hh="10"):
    return (f"2026-08-{day}T{hh}:00:00+00:00 pgain-nuc systemd[1]: "
            f"{kind} {unit}.service - x.")


# ---------------------------------------------------------- span coverage

def test_span_coverage_is_the_axis_two_captures_differed_on_and_audit_did_not_see():
    """The round's headline, as a regression test.

    Round 424 took two captures minutes apart -- one `journalctl -b`, one
    unrestricted -- and the old `audit` returned identical verdicts, identical
    gap counts, and `durations_derivable_fraction` 1.0 for both, while they
    covered 81 and 1652 unit fires. Every KIND check passed on both because
    kinds were all it graded.
    """
    days = ["23", "24", "25"]
    narrow = "\n".join([_jline("25", "Starting", "a"), _jline("25", "Finished", "a")])
    wide = "\n".join(_jline(d, k, "a")
                     for d in days for k in ("Starting", "Finished"))
    assert cm.journal_span_coverage(narrow, days)["uncovered"] == ["23", "24"]
    assert cm.journal_span_coverage(wide, days)["uncovered"] == []
    assert cm.journal_span_coverage(narrow, days)["coverage_fraction"] == 1 / 3
    assert cm.journal_span_coverage(wide, days)["coverage_fraction"] == 1.0


def test_a_boot_scoped_capture_is_narrow_not_complete_and_not_filtered():
    """`narrow` is a third verdict on purpose. The capture is not filtered --
    every required line kind survived -- and it is not complete either.
    Collapsing it into `filtered` would have sent the next round hunting for
    a grep that was not there."""
    sar = _sar_all_required(["23", "24"])
    jrn = "\n".join([_jline("24", "Starting", "a"), _jline("24", "Finished", "a"),
                     _jline("24", "Started", "b"), _jline("24", "Failed", "c")])
    res = cm.audit(sar, jrn)
    assert res["verdict"] == "narrow"
    window = [g for g in res["gaps"] if g["absence_means"] == "window"]
    assert [g["missing"] for g in window] == [
        "any systemd[1] line dated day 23 (pairs with sa23)"]
    assert all(g["blocking"] for g in window)
    # and the kind checks are NOT what failed
    assert not [g for g in res["gaps"]
                if g["blocking"] and g["absence_means"] == "filtered"]


# ------------------------------------------ filtered vs. a healthy box

def test_absent_failed_lines_are_a_fact_about_the_box_when_a_witness_survived():
    """`--strict` could never pass. `Failed <unit>.service` was required, so
    a box on which nothing failed graded `filtered` forever -- and a gate that
    is red on a healthy box is a gate nobody reads. One `Finished` line proves
    the capture was not passed through round 400's `Starting|Started` grep, and
    after that a missing `Failed` is evidence about the world."""
    sar = _sar_all_required(["24"])
    jrn = "\n".join([_jline("24", "Starting", "a"), _jline("24", "Finished", "a"),
                     _jline("24", "Started", "b")])
    res = cm.audit(sar, jrn)
    assert res["unfiltered_witnesses"] == ["Finished"]
    failed = [g for g in res["gaps"] if "Failed" in g["missing"]][0]
    assert failed["blocking"] is False
    assert failed["absence_means"] == "box-state"
    assert failed["recoverable"] == "in-capture"
    assert "fact about the BOX" in failed["why_it_matters"]
    assert res["verdict"] == "complete"


def test_absent_failed_lines_are_still_blocking_when_nothing_witnesses():
    """The other direction must keep working: round 400's capture really was
    grepped, and has no terminal line of any kind. There, a missing `Failed`
    IS a capture defect and has to stay blocking."""
    sar = _sar_all_required(["24"])
    jrn = "\n".join([_jline("24", "Starting", "a"), _jline("24", "Started", "a")])
    res = cm.audit(sar, jrn)
    assert res["unfiltered_witnesses"] == []
    for name in ("Failed", "Finished"):
        g = [g for g in res["gaps"] if name in g["missing"]][0]
        assert g["blocking"] is True and g["absence_means"] == "filtered"
    assert res["verdict"] == "filtered"


# ------------------------------------------------------------- retention

def test_ls_year_reconstruction_does_not_move_a_file_across_the_boundary():
    """`ls -l` prints `Mon DD HH:MM` OR `Mon DD  YYYY` and never both. Guessing
    the year wrong moves a file by 365 days, which is 52 retention periods."""
    rows = cm.parse_sysstat_ls(R424_SAR, "2026-09-01T08:18:35Z")
    by = {r["name"]: r["mtime_utc"] for r in rows}
    assert by["sa01"] == "2026-09-01T08:10:00Z"
    assert by["sa23"] == "2026-08-23T23:50:00Z"
    # a December file seen in January belongs to the previous year
    dec = cm.parse_sysstat_ls(
        "-rw-r--r-- 1 root root 10 Dec 30 23:50 sa30", "2027-01-02T00:00:00Z")
    assert dec[0]["mtime_utc"] == "2026-12-30T23:50:00Z"


def test_find_mtime_truncates_to_whole_days_which_is_what_spared_sa23():
    """`find -mtime +N` compares WHOLE 24 h units, truncated. At the sweep on
    2026-08-31T00:07Z `sa23` was 7.012 days old; `int(7.012) == 7` is not
    `> 7`, so it survived a night it would not have survived under a float
    comparison -- and round 424 was therefore still able to capture it."""
    assert cm.find_mtime_matches(7.012 * 86400, 7) is False
    assert cm.find_mtime_matches(8.012 * 86400, 7) is True
    assert cm.find_mtime_matches(8.0 * 86400, 7) is True
    assert cm.find_mtime_matches(7.999 * 86400, 7) is False


def test_retention_forecast_reproduces_the_boxs_own_find_output():
    """The model is checked against `find /var/log/sysstat -mtime +7` run on
    the box at capture time, which returned exactly `sa23` and `sar23`."""
    files = cm.parse_sysstat_ls(R424_SAR, "2026-09-01T08:18:35Z")
    now = cm.retention_forecast(files, "2026-09-01T08:18:35Z", history_days=7)
    assert sorted(r["name"] for r in now["deleted_at_next_run"]) == ["sa23", "sar23"]


def test_the_next_sweep_takes_sa24_too_which_the_2026_09_23_constant_denied():
    """Rounds 406/412/418 emitted "sa23 is overwritten on 2026-09-23" in the
    plan. That models sysstat as a 31-slot ring keyed on day-of-month, which is
    the mechanism only when HISTORY > 28. At HISTORY=7 `sa2` deletes by mtime
    and the ring never gets to wrap: sa23 dies on 2026-09-02, 21 days early."""
    files = cm.parse_sysstat_ls(R424_SAR, "2026-09-01T08:18:35Z")
    nxt = cm.retention_forecast(files, "2026-09-02T00:07:00Z", history_days=7)
    assert sorted(r["name"] for r in nxt["deleted_at_next_run"]) == [
        "sa23", "sa24", "sar23", "sar24"]
    assert nxt["n_deleted_at_next_run"] == 4
    # sa01 is nowhere near the boundary and must not be swept
    assert "sa01" in [r["name"] for r in nxt["spared"]]


def test_a_history_above_28_switches_the_binding_mechanism_back_to_the_ring():
    """The constant was not nonsense, it was the right answer to a different
    configuration. `sa2` itself branches on `HISTORY > 28`. Kept as a test so
    the next box with a long retention is not told its files die at 7 days."""
    files = cm.parse_sysstat_ls(R424_SAR, "2026-09-01T08:18:35Z")
    out = cm.retention_forecast(files, "2026-09-02T00:07:00Z", history_days=31)
    assert out["deleted_at_next_run"] == []


def test_the_sweep_regex_is_sa2s_own_and_spares_a_stray_file():
    assert cm.SA2_SWEEP_RE.match("sa23") and cm.SA2_SWEEP_RE.match("sar23")
    assert cm.SA2_SWEEP_RE.match("sa23.xz")
    assert not cm.SA2_SWEEP_RE.match("sa1")        # too short for the regex
    assert not cm.SA2_SWEEP_RE.match("notes.md")
    files = cm.parse_sysstat_ls(
        "-rw-r--r-- 1 root root 10 Aug 01 00:00 notes.md",
        "2026-09-01T08:18:35Z")
    out = cm.retention_forecast(files, "2026-09-02T00:07:00Z")
    assert out["not_swept"] == ["notes.md"] and out["deleted_at_next_run"] == []


# ------------------------------------------------------------- the plan

def test_the_emitted_plan_no_longer_scopes_the_journal_to_the_current_boot():
    """The defect that produced this whole round. The plan can only run when
    the box is reachable; on 2026-09-01 the box became reachable by REBOOTING,
    so `-b` would have banked 2 h 40 m in place of 8 d 18 h."""
    plan = cm.capture_plan(cm.audit(R424_SAR, ""))
    assert "journalctl -o short-iso --no-pager _PID=1" in plan
    assert "journalctl -b " not in plan
    assert "--list-boots" in plan


def test_the_emitted_plan_captures_the_user_manager_and_the_prerendered_reports():
    plan = cm.capture_plan(cm.audit(R424_SAR, ""))
    assert "_SYSTEMD_USER_UNIT=qwen36-colibri.service" in plan
    assert "sar[0-9][0-9]" in plan          # sysstat's own daily text reports
    assert "collector-evidence.txt" in plan


def test_the_emitted_plan_no_longer_hardcodes_an_expiry_date():
    plan = cm.capture_plan(cm.audit(R424_SAR, ""))
    assert "2026-09-23" not in plan
    assert "capture_manifest.py retention" in plan


def test_retention_cli_is_strict_and_refuses_to_guess_when_there_is_no_ls(tmp_path):
    d = tmp_path / "cap"
    d.mkdir()
    (d / "sar-all.txt").write_text("### SAR_R_SA23\nnothing here\n")
    (d / "journal-pid1-full.txt").write_text("")
    rc = cm.main(["retention", "--capture", str(d), "--now",
                  "2026-09-01T08:18:35Z", "--next-run", "2026-09-02T00:07:00Z"])
    assert rc == 2      # not 0-with-an-empty-forecast
