"""Offline tests for nuc/reachability_check.py.

`parse_tailscale_peer` is a pure JSON-in/dict-out parser, tested directly.
`check()`'s real subprocess calls (tailscale status, ssh) are replaced with
injected fakes (`tailscale_runner`/`ssh_runner`/`now_fn`) so these tests
never touch the network or depend on the real box's live state -- the real
live check lives in the round's own knowledge file, run manually.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reachability_check as rc  # noqa: E402


TAILSCALE_JSON_ONLINE = json.dumps({
    "Peer": {
        "abc": {
            "HostName": "pgain-nuc",
            "Online": True,
            "LastSeen": "2026-08-29T05:42:00Z",
            "LastWrite": "2026-08-29T05:42:43Z",
        },
        "def": {
            "HostName": "some-other-host",
            "Online": False,
        },
    }
})

TAILSCALE_JSON_OFFLINE = json.dumps({
    "Peer": {
        "abc": {
            "HostName": "pgain-nuc",
            "Online": False,
            "LastSeen": "2026-08-29T02:10:00.1Z",
            "LastWrite": "2026-08-29T05:42:43.013910137Z",
        },
    }
})

TAILSCALE_JSON_NO_PEER = json.dumps({"Peer": {}})


class FakeCompleted:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# --- parse_tailscale_peer ---------------------------------------------------

def test_parse_tailscale_peer_online():
    peer = rc.parse_tailscale_peer(TAILSCALE_JSON_ONLINE)
    assert peer == {
        "online": True,
        "last_seen": "2026-08-29T05:42:00Z",
        "last_write": "2026-08-29T05:42:43Z",
        "last_handshake": None,
    }


def test_parse_tailscale_peer_offline():
    peer = rc.parse_tailscale_peer(TAILSCALE_JSON_OFFLINE)
    assert peer["online"] is False
    assert peer["last_seen"] == "2026-08-29T02:10:00.1Z"


def test_parse_tailscale_peer_missing_hostname_returns_none():
    assert rc.parse_tailscale_peer(TAILSCALE_JSON_NO_PEER) is None
    assert rc.parse_tailscale_peer(TAILSCALE_JSON_ONLINE, hostname="not-there") is None


def test_parse_tailscale_peer_bad_json_raises():
    with pytest.raises(json.JSONDecodeError):
        rc.parse_tailscale_peer("not json")


# --- ssh_probe ---------------------------------------------------------------

def test_ssh_probe_reachable():
    def fake_runner(argv, **kwargs):
        assert argv[0] == "ssh"
        return FakeCompleted(0, stdout="UP\n", stderr="")
    result = rc.ssh_probe(runner=fake_runner)
    assert result == {"reachable": True, "returncode": 0, "stderr": ""}


def test_ssh_probe_connection_timed_out():
    def fake_runner(argv, **kwargs):
        return FakeCompleted(255, stdout="", stderr="ssh: connect to host x port 22: Connection timed out")
    result = rc.ssh_probe(runner=fake_runner)
    assert result["reachable"] is False
    assert result["returncode"] == 255


def test_ssh_probe_local_timeout_does_not_raise():
    import subprocess as sp

    def fake_runner(argv, **kwargs):
        raise sp.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout", 0))
    result = rc.ssh_probe(runner=fake_runner)
    assert result["reachable"] is False
    assert result["returncode"] is None


def test_ssh_probe_unexpected_stdout_not_reachable():
    """rc=0 but stdout isn't exactly 'UP' (e.g. a MOTD leaked through) should
    not be trusted as reachable -- the check is deliberately strict."""
    def fake_runner(argv, **kwargs):
        return FakeCompleted(0, stdout="Welcome to Ubuntu\nUP\n", stderr="")
    result = rc.ssh_probe(runner=fake_runner)
    assert result["reachable"] is False


# --- check() -----------------------------------------------------------------

def _fake_tailscale_runner(json_text, returncode=0, stderr=""):
    def runner(argv, **kwargs):
        return FakeCompleted(returncode, stdout=json_text, stderr=stderr)
    return runner


def test_check_verdict_up_when_ssh_succeeds():
    record = rc.check(
        round_=310,
        now_fn=lambda: "2026-08-29T05:42:47Z",
        tailscale_runner=_fake_tailscale_runner(TAILSCALE_JSON_OFFLINE),
        ssh_runner=lambda argv, **kw: FakeCompleted(0, stdout="UP\n"),
    )
    assert record["verdict"] == "up"
    assert record["ssh_reachable"] is True
    assert record["round"] == 310
    assert record["checked_at_utc"] == "2026-08-29T05:42:47Z"
    assert record["source"] == "live"
    assert record["precision"] == "precise"


def test_check_verdict_down_when_ssh_fails_and_tailscale_agrees():
    record = rc.check(
        round_=310,
        now_fn=lambda: "2026-08-29T05:42:47Z",
        tailscale_runner=_fake_tailscale_runner(TAILSCALE_JSON_OFFLINE),
        ssh_runner=lambda argv, **kw: FakeCompleted(255, stderr="Connection timed out"),
    )
    assert record["verdict"] == "down"
    assert record["tailscale_online"] is False
    assert record["tailscale_last_seen_utc"] == "2026-08-29T02:10:00.1Z"


def test_check_verdict_ambiguous_when_ssh_fails_but_tailscale_says_online():
    record = rc.check(
        now_fn=lambda: "2026-08-29T05:42:47Z",
        tailscale_runner=_fake_tailscale_runner(TAILSCALE_JSON_ONLINE),
        ssh_runner=lambda argv, **kw: FakeCompleted(255, stderr="Connection refused"),
    )
    assert record["verdict"] == "ambiguous"


def test_check_down_when_tailscale_itself_unreadable():
    """SSH failing is sufficient on its own to call it down -- a broken
    `tailscale` binary/command shouldn't block reporting the SSH ground
    truth, just leave the corroborating fields None/empty."""
    record = rc.check(
        now_fn=lambda: "2026-08-29T05:42:47Z",
        tailscale_runner=_fake_tailscale_runner("", returncode=1, stderr="tailscale: command not found"),
        ssh_runner=lambda argv, **kw: FakeCompleted(255, stderr="Connection timed out"),
    )
    assert record["verdict"] == "down"
    assert record["tailscale_online"] is None
    assert record["tailscale_error"] == "tailscale: command not found"


# --- log I/O + summarize_log --------------------------------------------------

def test_append_and_load_log_roundtrip(tmp_path):
    log_path = tmp_path / "log.jsonl"
    r1 = {"checked_at_utc": "2026-08-29T01:00:00Z", "round": 1, "verdict": "up"}
    r2 = {"checked_at_utc": "2026-08-29T02:00:00Z", "round": 2, "verdict": "down"}
    rc.append_record(r1, str(log_path))
    rc.append_record(r2, str(log_path))
    loaded = rc.load_log(str(log_path))
    assert loaded == [r1, r2]


def test_load_log_missing_file_returns_empty_list(tmp_path):
    assert rc.load_log(str(tmp_path / "nope.jsonl")) == []


def test_summarize_log_merges_adjacent_same_verdict_into_one_streak():
    records = [
        {"checked_at_utc": "2026-08-27T00:00:00Z", "round": 166, "verdict": "up"},
        {"checked_at_utc": "2026-08-27T04:00:00Z", "round": 172, "verdict": "up"},
        {"checked_at_utc": "2026-08-27T08:00:00Z", "round": 184, "verdict": "down"},
        {"checked_at_utc": "2026-08-27T10:00:00Z", "round": 196, "verdict": "down"},
        {"checked_at_utc": "2026-08-27T12:00:00Z", "round": 202, "verdict": "up"},
    ]
    summary = rc.summarize_log(records)
    assert summary["n_records"] == 5
    assert summary["n_streaks"] == 3
    assert summary["n_down_streaks"] == 1
    down_streak = summary["streaks"][1]
    assert down_streak["verdict"] == "down"
    assert down_streak["start"] == "2026-08-27T08:00:00Z"
    assert down_streak["end"] == "2026-08-27T10:00:00Z"
    assert down_streak["rounds"] == [184, 196]


def test_summarize_log_treats_ambiguous_as_its_own_class():
    records = [
        {"checked_at_utc": "2026-08-27T00:00:00Z", "round": 1, "verdict": "up"},
        {"checked_at_utc": "2026-08-27T01:00:00Z", "round": 2, "verdict": "ambiguous"},
        {"checked_at_utc": "2026-08-27T02:00:00Z", "round": 3, "verdict": "down"},
    ]
    summary = rc.summarize_log(records)
    assert [s["verdict"] for s in summary["streaks"]] == ["up", "ambiguous", "down"]


def test_summarize_log_sorts_out_of_order_input_by_timestamp():
    records = [
        {"checked_at_utc": "2026-08-27T02:00:00Z", "round": 3, "verdict": "down"},
        {"checked_at_utc": "2026-08-27T00:00:00Z", "round": 1, "verdict": "up"},
    ]
    summary = rc.summarize_log(records)
    assert summary["streaks"][0]["verdict"] == "up"
    assert summary["streaks"][0]["start_round"] == 1
    assert summary["streaks"][1]["verdict"] == "down"


def test_summarize_log_empty():
    summary = rc.summarize_log([])
    assert summary == {"n_records": 0, "n_streaks": 0, "n_down_streaks": 0, "streaks": []}


# --- current_streak_duration --------------------------------------------------

def test_current_streak_duration_empty_log_returns_none():
    assert rc.current_streak_duration([]) is None


def test_current_streak_duration_walks_back_through_matching_verdicts_only():
    records = [
        {"checked_at_utc": "2026-08-29T00:00:00Z", "round": 298, "verdict": "up"},
        {"checked_at_utc": "2026-08-29T02:13:07Z", "round": 304, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T05:47:35Z", "round": 310, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T07:42:24Z", "round": 316, "verdict": "down"},
    ]
    result = rc.current_streak_duration(records, now_fn=lambda: "2026-08-29T08:12:24Z")
    assert result["verdict"] == "down"
    assert result["streak_start_utc"] == "2026-08-29T02:13:07Z"
    assert result["streak_start_round"] == 304
    assert result["latest_check_round"] == 316
    assert result["as_of_utc"] == "2026-08-29T08:12:24Z"
    # 08:12:24 - 02:13:07 = 5h59m17s = 21557s
    assert result["elapsed_s"] == 21557.0


def test_current_streak_duration_single_record_streak_start_is_that_record():
    records = [
        {"checked_at_utc": "2026-08-29T00:00:00Z", "round": 1, "verdict": "up"},
        {"checked_at_utc": "2026-08-29T01:00:00Z", "round": 2, "verdict": "down"},
    ]
    result = rc.current_streak_duration(records, now_fn=lambda: "2026-08-29T01:30:00Z")
    assert result["streak_start_utc"] == "2026-08-29T01:00:00Z"
    assert result["streak_start_round"] == 2
    assert result["elapsed_s"] == 1800.0


def test_current_streak_duration_unsorted_input_still_uses_latest_by_timestamp():
    records = [
        {"checked_at_utc": "2026-08-29T02:00:00Z", "round": 2, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T00:00:00Z", "round": 1, "verdict": "up"},
    ]
    result = rc.current_streak_duration(records, now_fn=lambda: "2026-08-29T02:30:00Z")
    assert result["verdict"] == "down"
    assert result["streak_start_round"] == 2
    assert result["elapsed_s"] == 1800.0


def test_longest_completed_streak_none_when_only_streak_is_the_logs_last():
    records = [
        {"checked_at_utc": "2026-08-29T00:00:00Z", "round": 1, "verdict": "up"},
        {"checked_at_utc": "2026-08-29T01:00:00Z", "round": 2, "verdict": "up"},
    ]
    # the only streak in the log is also its LAST streak -- always excluded
    # as potentially-still-ongoing, regardless of verdict.
    assert rc.longest_completed_streak(records, "up") is None
    assert rc.longest_completed_streak(records, "down") is None


def test_longest_completed_streak_excludes_the_logs_own_last_streak():
    records = [
        {"checked_at_utc": "2026-08-29T00:00:00Z", "round": 1, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T01:00:00Z", "round": 2, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T02:00:00Z", "round": 3, "verdict": "up"},
        {"checked_at_utc": "2026-08-29T10:00:00Z", "round": 4, "verdict": "down"},
    ]
    # the trailing "down" streak (round 4 alone, 8h elapsed if measured against
    # "now") is the log's own last streak -- it must never count as "completed"
    # even though it is numerically longer than the real completed one.
    result = rc.longest_completed_streak(records, "down")
    assert result["start_round"] == 1
    assert result["end_round"] == 2


def test_longest_completed_streak_picks_the_longest_among_multiple_completed():
    records = [
        {"checked_at_utc": "2026-08-29T00:00:00Z", "round": 1, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T00:30:00Z", "round": 2, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T01:00:00Z", "round": 3, "verdict": "up"},
        {"checked_at_utc": "2026-08-29T03:00:00Z", "round": 4, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T05:00:00Z", "round": 5, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T06:00:00Z", "round": 6, "verdict": "up"},
    ]
    result = rc.longest_completed_streak(records, "down")
    assert result["start_round"] == 4
    assert result["end_round"] == 5


def test_current_streak_duration_exceeds_longest_completed_true():
    records = [
        {"checked_at_utc": "2026-08-29T00:00:00Z", "round": 1, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T01:00:00Z", "round": 2, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T02:00:00Z", "round": 3, "verdict": "up"},
        {"checked_at_utc": "2026-08-29T03:00:00Z", "round": 4, "verdict": "down"},
    ]
    result = rc.current_streak_duration(records, now_fn=lambda: "2026-08-29T10:00:00Z")
    assert result["longest_completed_same_verdict_streak_s"] == 3600.0
    assert result["elapsed_s"] == 7 * 3600.0
    assert result["exceeds_longest_completed"] is True
    assert result["elapsed_human"] == "7h00m00s"
    assert result["longest_completed_same_verdict_streak_human"] == "1h00m00s"
    assert result["margin_s"] == 6 * 3600.0
    assert result["margin_human"] == "6h00m00s"


def test_current_streak_duration_exceeds_longest_completed_false():
    records = [
        {"checked_at_utc": "2026-08-29T00:00:00Z", "round": 1, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T10:00:00Z", "round": 2, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T11:00:00Z", "round": 3, "verdict": "up"},
        {"checked_at_utc": "2026-08-29T12:00:00Z", "round": 4, "verdict": "down"},
    ]
    result = rc.current_streak_duration(records, now_fn=lambda: "2026-08-29T12:30:00Z")
    assert result["longest_completed_same_verdict_streak_s"] == 36000.0
    assert result["elapsed_s"] == 1800.0
    assert result["exceeds_longest_completed"] is False
    assert result["elapsed_human"] == "0h30m00s"
    assert result["longest_completed_same_verdict_streak_human"] == "10h00m00s"
    # margin is reported as a magnitude regardless of direction; the sign
    # lives in `exceeds_longest_completed`, not in `margin_human` itself.
    assert result["margin_s"] == -34200.0
    assert result["margin_human"] == "9h30m00s"


def test_current_streak_duration_no_prior_completed_streak_gives_none_comparison():
    records = [
        {"checked_at_utc": "2026-08-29T00:00:00Z", "round": 1, "verdict": "down"},
    ]
    result = rc.current_streak_duration(records, now_fn=lambda: "2026-08-29T01:00:00Z")
    assert result["longest_completed_same_verdict_streak_s"] is None
    assert result["exceeds_longest_completed"] is None
    assert result["longest_completed_same_verdict_streak_human"] is None
    assert result["margin_s"] is None
    assert result["margin_human"] is None
    assert result["elapsed_human"] == "1h00m00s"


def test_format_duration_s_basic():
    assert rc.format_duration_s(0) == "0h00m00s"
    assert rc.format_duration_s(59) == "0h00m59s"
    assert rc.format_duration_s(60) == "0h01m00s"
    assert rc.format_duration_s(3599) == "0h59m59s"
    assert rc.format_duration_s(3600) == "1h00m00s"


def test_format_duration_s_matches_hand_computed_round_history():
    # Real elapsed/streak/margin figures rounds recorded by hand in prose
    # (round 322's own knowledge file and research-state.md entry).
    assert rc.format_duration_s(28821.0) == "8h00m21s"
    assert rc.format_duration_s(18880.0) == "5h14m40s"
    assert rc.format_duration_s(9941.0) == "2h45m41s"


def test_format_duration_s_truncates_not_rounds_sub_second_remainder():
    # 3599.9s must stay "0h59m59s", never roll over to "1h00m00s".
    assert rc.format_duration_s(3599.9) == "0h59m59s"


def test_format_duration_s_hours_unpadded_past_two_digits():
    assert rc.format_duration_s(100 * 3600 + 61) == "100h01m01s"
