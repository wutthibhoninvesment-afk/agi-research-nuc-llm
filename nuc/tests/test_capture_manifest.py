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
    assert "journalctl -b -o short-iso --no-pager _PID=1" in plan
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
    res = cm.audit("\n".join(lines) + "\n", JOURNAL_FULL)
    assert res["n_blocking_gaps"] == 0
    assert res["n_gaps"] == 0
    assert res["verdict"] == "complete"


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

def test_the_round_400_capture_audits_as_filtered_with_three_blocking_gaps():
    res = cm.audit_dir(str(CAP400))
    assert res["verdict"] == "filtered"
    assert res["n_blocking_gaps"] == 3          # -B on 7 days, Finished, Failed
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
