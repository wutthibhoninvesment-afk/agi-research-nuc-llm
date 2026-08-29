"""Offline tests for nuc/reachability_check.py.

`parse_tailscale_peer` is a pure JSON-in/dict-out parser, tested directly.
`check()`'s real subprocess calls (tailscale status, ssh) are replaced with
injected fakes (`tailscale_runner`/`ssh_runner`/`now_fn`) so these tests
never touch the network or depend on the real box's live state -- the real
live check lives in the round's own knowledge file, run manually.
"""
import json
import subprocess
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


# --- _parse_ts tolerance (round 334) -----------------------------------------

def test_parse_ts_plain_no_fraction():
    dt = rc._parse_ts("2026-08-29T02:13:07Z")
    assert (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second) == (2026, 8, 29, 2, 13, 7)
    assert dt.microsecond == 0
    assert dt.tzinfo is not None and dt.utcoffset().total_seconds() == 0


def test_parse_ts_single_fractional_digit_is_tenths_not_microseconds():
    """tailscale's `LastSeen` for pgain-nuc is literally "...:00.1Z". ".1"
    means 100000us, not 1us -- the parser must left-pad the fraction to 6
    digits, not right-align it."""
    dt = rc._parse_ts("2026-08-29T02:10:00.1Z")
    assert dt.microsecond == 100000


def test_parse_ts_nanosecond_fraction_truncates_to_microseconds():
    """tailscale's `LastWrite` carries 9 fractional digits, which strptime's
    %f rejects outright. Truncate (never round) to 6."""
    dt = rc._parse_ts("2026-08-29T12:47:50.906797174Z")
    assert dt.microsecond == 906797


def test_parse_ts_fraction_truncation_never_rolls_a_second_forward():
    dt = rc._parse_ts("2026-08-29T12:47:50.9999999Z")
    assert (dt.second, dt.microsecond) == (50, 999999)


def test_parse_ts_tolerates_surrounding_whitespace_and_missing_z():
    assert rc._parse_ts("  2026-08-29T02:13:07Z  ") == rc._parse_ts("2026-08-29T02:13:07")


def test_parse_ts_still_rejects_genuine_garbage():
    with pytest.raises(ValueError):
        rc._parse_ts("not-a-timestamp")


# --- _build_streaks -----------------------------------------------------------

def test_build_streaks_keeps_underlying_records_summarize_log_drops():
    records = [
        {"checked_at_utc": "2026-08-29T00:00:00Z", "round": 1, "verdict": "up"},
        {"checked_at_utc": "2026-08-29T01:00:00Z", "round": 2, "verdict": "down",
         "tailscale_last_seen_utc": "2026-08-29T00:30:00Z"},
    ]
    streaks = rc._build_streaks(records)
    assert [s["verdict"] for s in streaks] == ["up", "down"]
    assert streaks[1]["records"][0]["tailscale_last_seen_utc"] == "2026-08-29T00:30:00Z"
    # summarize_log's public projection still has no `records` key at all.
    assert "records" not in rc.summarize_log(records)["streaks"][1]


# --- streak_bounds ------------------------------------------------------------

def _bounds_by_rounds(records, start_round):
    return next(b for b in rc.streak_bounds(records) if b["start_round"] == start_round)


BRACKET_RECORDS = [
    {"checked_at_utc": "2026-08-27T00:00:00Z", "round": 1, "verdict": "up"},
    {"checked_at_utc": "2026-08-27T04:00:00Z", "round": 2, "verdict": "up"},
    {"checked_at_utc": "2026-08-27T08:00:00Z", "round": 3, "verdict": "down"},
    {"checked_at_utc": "2026-08-27T10:00:00Z", "round": 4, "verdict": "down"},
    {"checked_at_utc": "2026-08-27T13:00:00Z", "round": 5, "verdict": "up"},
]


def test_streak_bounds_empty_log():
    assert rc.streak_bounds([]) == []


def test_streak_bounds_middle_streak_brackets_both_sides():
    b = _bounds_by_rounds(BRACKET_RECORDS, 3)
    assert b["confirmed_span_s"] == 2 * 3600.0          # 08:00 -> 10:00 observed down
    assert b["earliest_possible_start_utc"] == "2026-08-27T04:00:00Z"
    assert b["earliest_possible_start_source"] == "previous_check"
    assert b["latest_possible_end_utc"] == "2026-08-27T13:00:00Z"
    assert b["latest_possible_end_source"] == "next_check"
    assert b["start_uncertainty_s"] == 4 * 3600.0
    assert b["end_uncertainty_s"] == 3 * 3600.0
    assert b["max_possible_span_s"] == 9 * 3600.0       # 04:00 -> 13:00
    assert b["max_possible_span_s"] == (b["confirmed_span_s"]
                                        + b["start_uncertainty_s"]
                                        + b["end_uncertainty_s"])
    assert b["ongoing"] is False
    assert b["confirmed_span_human"] == "2h00m00s"
    assert b["max_possible_span_human"] == "9h00m00s"


def test_streak_bounds_first_streak_has_no_lower_bound_so_no_max_span():
    b = _bounds_by_rounds(BRACKET_RECORDS, 1)
    assert b["earliest_possible_start_utc"] is None
    assert b["earliest_possible_start_source"] is None
    assert b["start_uncertainty_s"] is None
    assert b["max_possible_span_s"] is None      # unbounded before => no claim
    assert b["max_possible_span_human"] is None
    assert b["end_uncertainty_s"] == 4 * 3600.0  # 04:00 -> 08:00, end side is known


def test_streak_bounds_last_streak_is_ongoing_and_has_no_upper_bound():
    b = _bounds_by_rounds(BRACKET_RECORDS, 5)
    assert b["ongoing"] is True
    assert b["latest_possible_end_utc"] is None
    assert b["latest_possible_end_source"] is None
    assert b["end_uncertainty_s"] is None
    assert b["max_possible_span_s"] is None


def test_streak_bounds_last_seen_tightens_a_down_streaks_start():
    records = list(BRACKET_RECORDS)
    records[2] = dict(records[2], tailscale_last_seen_utc="2026-08-27T07:30:00Z")
    b = _bounds_by_rounds(records, 3)
    # 07:30 is later evidence of "up" than the 04:00 up check, so the outage
    # can only have started in the 30 minutes before we first saw it down.
    assert b["earliest_possible_start_utc"] == "2026-08-27T07:30:00Z"
    assert b["earliest_possible_start_source"] == "tailscale_last_seen"
    assert b["start_uncertainty_s"] == 1800.0
    assert b["max_possible_span_s"] == 5.5 * 3600.0


def test_streak_bounds_takes_the_latest_last_seen_across_the_whole_streak():
    records = list(BRACKET_RECORDS)
    records[2] = dict(records[2], tailscale_last_seen_utc="2026-08-27T05:00:00Z")
    records[3] = dict(records[3], tailscale_last_seen_utc="2026-08-27T07:00:00Z")
    b = _bounds_by_rounds(records, 3)
    assert b["earliest_possible_start_utc"] == "2026-08-27T07:00:00Z"


def test_streak_bounds_ignores_last_seen_after_the_first_down_check():
    """A peer seen alive AFTER the moment we called it down is a flicker the
    streak model cannot represent; using it would invert the bracket into a
    negative start_uncertainty, so it is dropped rather than clamped."""
    records = list(BRACKET_RECORDS)
    records[2] = dict(records[2], tailscale_last_seen_utc="2026-08-27T09:00:00Z")
    b = _bounds_by_rounds(records, 3)
    assert b["earliest_possible_start_utc"] == "2026-08-27T04:00:00Z"
    assert b["earliest_possible_start_source"] == "previous_check"
    assert b["start_uncertainty_s"] > 0


def test_streak_bounds_accepts_last_seen_exactly_at_the_first_down_check():
    """The boundary case is usable, not a flicker: last seen alive at the
    same second we first saw it down pins the transition exactly."""
    records = list(BRACKET_RECORDS)
    records[2] = dict(records[2], tailscale_last_seen_utc="2026-08-27T08:00:00Z")
    b = _bounds_by_rounds(records, 3)
    assert b["earliest_possible_start_source"] == "tailscale_last_seen"
    assert b["start_uncertainty_s"] == 0.0


def test_streak_bounds_ignores_last_seen_on_an_up_streak():
    """On an up record LastSeen means "seen alive during this streak", not
    "last alive before it" -- the opposite direction, so it must not be
    read as a lower bound on the streak's start."""
    records = list(BRACKET_RECORDS)
    records[4] = dict(records[4], tailscale_last_seen_utc="2026-08-27T12:59:00Z")
    b = _bounds_by_rounds(records, 5)
    assert b["earliest_possible_start_utc"] == "2026-08-27T10:00:00Z"
    assert b["earliest_possible_start_source"] == "previous_check"


def test_streak_bounds_boot_utc_tightens_the_preceding_outages_end():
    records = list(BRACKET_RECORDS)
    records[4] = dict(records[4], boot_utc="2026-08-27T11:00:00Z")
    b = _bounds_by_rounds(records, 3)
    assert b["latest_possible_end_utc"] == "2026-08-27T11:00:00Z"
    assert b["latest_possible_end_source"] == "boot_utc"
    assert b["end_uncertainty_s"] == 3600.0            # was 3h without it
    assert b["max_possible_span_s"] == 7 * 3600.0      # was 9h without it


def test_streak_bounds_ignores_boot_utc_at_or_before_our_last_down_check():
    """boot_utc earlier than a later down observation implies more than one
    transition inside the gap -- unrepresentable, so fall back to the
    next check rather than claim a bound the evidence contradicts."""
    records = list(BRACKET_RECORDS)
    records[4] = dict(records[4], boot_utc="2026-08-27T09:00:00Z")
    b = _bounds_by_rounds(records, 3)
    assert b["latest_possible_end_utc"] == "2026-08-27T13:00:00Z"
    assert b["latest_possible_end_source"] == "next_check"


def test_streak_bounds_boot_utc_only_read_off_the_next_streaks_first_record():
    """A boot recorded two checks later is a different (or unknown) boot;
    only the first up record after the outage bounds that outage's end."""
    records = list(BRACKET_RECORDS) + [
        {"checked_at_utc": "2026-08-27T16:00:00Z", "round": 6, "verdict": "up",
         "boot_utc": "2026-08-27T11:00:00Z"},
    ]
    b = _bounds_by_rounds(records, 3)
    assert b["latest_possible_end_source"] == "next_check"


def test_streak_bounds_handles_fractional_last_seen_end_to_end():
    records = [
        {"checked_at_utc": "2026-08-29T00:00:00Z", "round": 1, "verdict": "up"},
        {"checked_at_utc": "2026-08-29T02:13:07Z", "round": 2, "verdict": "down",
         "tailscale_last_seen_utc": "2026-08-29T02:10:00.1Z"},
        {"checked_at_utc": "2026-08-29T03:00:00Z", "round": 3, "verdict": "up"},
    ]
    b = _bounds_by_rounds(records, 2)
    assert b["start_uncertainty_s"] == pytest.approx(186.9)
    assert b["start_uncertainty_human"] == "0h03m06s"


# --- longest_completed_streak_bounds -------------------------------------------

def test_longest_completed_streak_bounds_agrees_with_longest_completed_streak():
    """Two independent max() calls over the same candidate set must never
    drift apart -- `current_streak_duration` reports one streak's confirmed
    span and the other's max-possible span side by side, and they have to
    describe the SAME streak for that pairing to mean anything."""
    records = [
        {"checked_at_utc": "2026-08-29T00:00:00Z", "round": 1, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T00:30:00Z", "round": 2, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T01:00:00Z", "round": 3, "verdict": "up"},
        {"checked_at_utc": "2026-08-29T03:00:00Z", "round": 4, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T05:00:00Z", "round": 5, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T06:00:00Z", "round": 6, "verdict": "up"},
    ]
    plain = rc.longest_completed_streak(records, "down")
    bounded = rc.longest_completed_streak_bounds(records, "down")
    assert (bounded["start_round"], bounded["end_round"]) == (plain["start_round"], plain["end_round"])
    assert bounded["confirmed_span_s"] == rc._streak_span_seconds(plain)
    assert bounded["max_possible_span_s"] == 5 * 3600.0   # 01:00 -> 06:00


def test_longest_completed_streak_bounds_none_when_no_completed_streak():
    records = [{"checked_at_utc": "2026-08-29T00:00:00Z", "round": 1, "verdict": "down"}]
    assert rc.longest_completed_streak_bounds(records, "down") is None


# --- current_streak_duration: bracket fields ------------------------------------

def test_current_streak_duration_elapsed_upper_is_elapsed_plus_start_uncertainty():
    records = [
        {"checked_at_utc": "2026-08-29T00:00:00Z", "round": 1, "verdict": "up"},
        {"checked_at_utc": "2026-08-29T02:13:07Z", "round": 2, "verdict": "down",
         "tailscale_last_seen_utc": "2026-08-29T02:10:00.1Z"},
    ]
    result = rc.current_streak_duration(records, now_fn=lambda: "2026-08-29T03:13:07Z")
    assert result["elapsed_s"] == 3600.0
    assert result["earliest_possible_start_utc"] == "2026-08-29T02:10:00.1Z"
    assert result["earliest_possible_start_source"] == "tailscale_last_seen"
    assert result["start_uncertainty_s"] == pytest.approx(186.9)
    assert result["elapsed_upper_s"] == pytest.approx(3786.9)
    assert result["elapsed_upper_human"] == "1h03m06s"


def test_current_streak_duration_definite_comparison_none_when_prior_is_unbounded():
    records = [
        {"checked_at_utc": "2026-08-29T00:00:00Z", "round": 1, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T01:00:00Z", "round": 2, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T02:00:00Z", "round": 3, "verdict": "up"},
        {"checked_at_utc": "2026-08-29T03:00:00Z", "round": 4, "verdict": "down"},
    ]
    result = rc.current_streak_duration(records, now_fn=lambda: "2026-08-29T10:00:00Z")
    # The prior down streak OPENS the log, so its own start is unbounded and
    # it has no max-possible span at all. No amount of elapsed time can then
    # prove the current outage beats it, so the definite comparison abstains
    # rather than silently falling back to the confirmed-span comparison.
    assert result["longest_completed_same_verdict_streak_s"] == 3600.0
    assert result["longest_completed_same_verdict_streak_max_possible_s"] is None
    assert result["definitely_exceeds_longest_completed"] is None
    assert result["definite_margin_s"] is None
    # ...but the like-for-like lower-bound comparison still answers.
    assert result["exceeds_longest_completed"] is True


def test_current_streak_duration_definitely_exceeds_with_a_fully_bracketed_prior():
    records = [
        {"checked_at_utc": "2026-08-29T00:00:00Z", "round": 1, "verdict": "up"},
        {"checked_at_utc": "2026-08-29T01:00:00Z", "round": 2, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T02:00:00Z", "round": 3, "verdict": "down"},
        {"checked_at_utc": "2026-08-29T03:00:00Z", "round": 4, "verdict": "up"},
        {"checked_at_utc": "2026-08-29T04:00:00Z", "round": 5, "verdict": "down"},
    ]
    # prior down streak: confirmed 1h, max-possible 3h (00:00 -> 03:00).
    at_2h = rc.current_streak_duration(records, now_fn=lambda: "2026-08-29T06:00:00Z")
    assert at_2h["elapsed_s"] == 2 * 3600.0
    assert at_2h["exceeds_longest_completed"] is True         # 2h > 1h confirmed
    assert at_2h["definitely_exceeds_longest_completed"] is False  # 2h < 3h possible
    assert at_2h["definite_margin_s"] == -3600.0
    assert at_2h["definite_margin_human"] == "1h00m00s"       # magnitude only

    at_4h = rc.current_streak_duration(records, now_fn=lambda: "2026-08-29T08:00:00Z")
    assert at_4h["definitely_exceeds_longest_completed"] is True
    assert at_4h["definite_margin_s"] == 3600.0
    assert at_4h["longest_completed_same_verdict_streak_max_possible_human"] == "3h00m00s"


def test_current_streak_duration_no_prior_streak_leaves_every_bracket_field_none():
    records = [{"checked_at_utc": "2026-08-29T00:00:00Z", "round": 1, "verdict": "down"}]
    result = rc.current_streak_duration(records, now_fn=lambda: "2026-08-29T01:00:00Z")
    assert result["earliest_possible_start_utc"] is None
    assert result["start_uncertainty_s"] is None
    assert result["elapsed_upper_s"] is None
    assert result["elapsed_upper_human"] is None
    assert result["longest_completed_same_verdict_streak_max_possible_s"] is None
    assert result["definitely_exceeds_longest_completed"] is None
    assert result["definite_margin_human"] is None


# --- boot_probe / boot_utc_from_uptime / check() boot capture (round 334) ------

def test_boot_probe_parses_proc_uptime_first_field():
    def fake_runner(argv, **kwargs):
        assert argv[0] == "ssh"
        assert argv[-1] == "cat /proc/uptime"
        return FakeCompleted(0, stdout="26576.31 205712.44\n")
    assert rc.boot_probe(runner=fake_runner) == pytest.approx(26576.31)


def test_boot_probe_returns_none_on_failed_ssh():
    def fake_runner(argv, **kwargs):
        return FakeCompleted(255, stdout="", stderr="Connection timed out")
    assert rc.boot_probe(runner=fake_runner) is None


def test_boot_probe_returns_none_on_local_timeout():
    import subprocess as sp

    def fake_runner(argv, **kwargs):
        raise sp.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout", 0))
    assert rc.boot_probe(runner=fake_runner) is None


@pytest.mark.parametrize("stdout", ["", "   \n", "not-a-number 1.0\n", "-5.0 1.0\n"])
def test_boot_probe_returns_none_on_unusable_output(stdout):
    def fake_runner(argv, **kwargs):
        return FakeCompleted(0, stdout=stdout)
    assert rc.boot_probe(runner=fake_runner) is None


def test_boot_utc_from_uptime_subtracts_and_truncates_to_whole_seconds():
    assert rc.boot_utc_from_uptime("2026-08-27T13:18:26Z", 5258.0) == "2026-08-27T11:50:48Z"
    # sub-second remainder truncates downward, never rolls a second forward
    assert rc.boot_utc_from_uptime("2026-08-27T13:18:26Z", 5257.4) == "2026-08-27T11:50:48Z"


def test_boot_utc_from_uptime_reproduces_round_202s_recorded_boot_time():
    """Round 202's own `uptime -s` said 2026-08-27T11:50:48Z at a check
    timestamped 13:18:26Z -- 5258s of uptime. Pinning the round trip here
    ties the new derivation to the one real boot time this log carries."""
    assert rc.boot_utc_from_uptime("2026-08-27T13:18:26Z", 5258.0) == "2026-08-27T11:50:48Z"


class _CountingSshRunner:
    """Answers `echo UP` and `cat /proc/uptime` differently, and counts calls
    so a test can prove the boot probe is NOT attempted on a down check."""

    def __init__(self, up=True, uptime_stdout="26576.31 205712.44\n"):
        self.up = up
        self.uptime_stdout = uptime_stdout
        self.commands = []

    def __call__(self, argv, **kwargs):
        self.commands.append(argv[-1])
        if not self.up:
            return FakeCompleted(255, stderr="Connection timed out")
        if argv[-1] == "cat /proc/uptime":
            return FakeCompleted(0, stdout=self.uptime_stdout)
        return FakeCompleted(0, stdout="UP\n")


def test_check_up_record_carries_a_derived_boot_utc():
    runner = _CountingSshRunner()
    record = rc.check(
        round_=340,
        now_fn=lambda: "2026-08-29T13:00:00Z",
        tailscale_runner=_fake_tailscale_runner(TAILSCALE_JSON_ONLINE),
        ssh_runner=runner,
    )
    assert record["verdict"] == "up"
    # 13:00:00 - 26576.31s = 05:37:03.69 -> truncated to 05:37:03
    assert record["boot_utc"] == "2026-08-29T05:37:03Z"
    assert runner.commands == ["echo UP", "cat /proc/uptime"]


def test_check_down_record_has_null_boot_utc_and_never_probes_for_it():
    runner = _CountingSshRunner(up=False)
    record = rc.check(
        round_=334,
        now_fn=lambda: "2026-08-29T12:47:54Z",
        tailscale_runner=_fake_tailscale_runner(TAILSCALE_JSON_OFFLINE),
        ssh_runner=runner,
    )
    assert record["verdict"] == "down"
    assert record["boot_utc"] is None
    # exactly one ssh call: no second connect-timeout wait for a boot time
    # that a down box cannot supply anyway.
    assert runner.commands == ["echo UP"]


def test_check_up_record_tolerates_an_unreadable_boot_time():
    runner = _CountingSshRunner(uptime_stdout="cat: /proc/uptime: No such file\n")
    record = rc.check(
        now_fn=lambda: "2026-08-29T13:00:00Z",
        tailscale_runner=_fake_tailscale_runner(TAILSCALE_JSON_ONLINE),
        ssh_runner=runner,
    )
    assert record["verdict"] == "up"
    assert record["boot_utc"] is None


def test_check_boot_utc_flows_through_to_streak_bounds():
    """End-to-end: a `check()`-shaped up record closing an outage must
    tighten that outage's end bound with no manual field plumbing."""
    down = rc.check(
        round_=1,
        now_fn=lambda: "2026-08-29T02:00:00Z",
        tailscale_runner=_fake_tailscale_runner(TAILSCALE_JSON_OFFLINE),
        ssh_runner=_CountingSshRunner(up=False),
    )
    up = rc.check(
        round_=2,
        now_fn=lambda: "2026-08-29T13:00:00Z",
        tailscale_runner=_fake_tailscale_runner(TAILSCALE_JSON_ONLINE),
        ssh_runner=_CountingSshRunner(uptime_stdout="3600.0 1.0\n"),
    )
    assert up["boot_utc"] == "2026-08-29T12:00:00Z"
    b = _bounds_by_rounds([down, up], 1)
    assert b["latest_possible_end_source"] == "boot_utc"
    assert b["end_uncertainty_s"] == 10 * 3600.0   # 02:00 -> 12:00, not -> 13:00


# --- brackets against the REAL committed log ------------------------------------

REAL_LOG = Path(__file__).resolve().parents[2] / "state" / "nuc-reachability-log.jsonl"


def _real_log_records():
    if not REAL_LOG.exists():
        pytest.skip(f"{REAL_LOG} not present")
    return rc.load_log(str(REAL_LOG))


# The instant round 340 ran its continuity analysis. Everything at or before
# it is frozen history for these tests; everything after is future data.
ROUND_340_ANALYSIS_UTC = "2026-08-29T17:15:41Z"


def _real_log_through_round(_last_round=340):
    """The real log as it stood when round 340 analysed it.

    Frozen by TIMESTAMP, not by round number: round 340 itself appended a
    round-end check after this point, and a round-number filter would have
    swept it back in and broken every aggregate pinned below.

    Every assertion below that pins a whole-log AGGREGATE (gap counts,
    unwitnessed totals, which streaks exist) must run against a frozen
    prefix, not the live file: the next E round appends a record and turns
    an exact aggregate into a failing test that looks like a regression and
    is really just arithmetic. Round 334's own real-log tests got away with
    exact pins because they only ever pinned CLOSED history (outage 1),
    which can never move again. This helper generalises that discipline to
    the rest of the log -- pin the frozen prefix exactly, and assert only
    monotone invariants against the live file.
    """
    return [r for r in _real_log_records()
            if r["checked_at_utc"] <= ROUND_340_ANALYSIS_UTC]


def test_real_log_first_outage_bracket_is_pinned():
    """Outage 1 (rounds 184-196) is closed history -- its bracket can never
    legitimately move again, so pin every number of it. Round 322/328 quoted
    only its 5h14m40s CONFIRMED span as "the record to beat"; the bracket
    says the same outage could really have run to 7h02m26s, and that the
    understatement splits into 51m38s of not-knowing-when-it-fell-over and
    56m08s of not-knowing-when-it-came-back."""
    bounds = [b for b in rc.streak_bounds(_real_log_records())
              if b["verdict"] == "down"]
    first = bounds[0]
    assert (first["start_round"], first["end_round"]) == (184, 196)
    assert first["confirmed_span_s"] == 18880.0
    assert first["confirmed_span_human"] == "5h14m40s"
    assert first["earliest_possible_start_utc"] == "2026-08-27T04:48:21.1Z"
    assert first["earliest_possible_start_source"] == "tailscale_last_seen"
    assert first["start_uncertainty_human"] == "0h51m38s"
    assert first["latest_possible_end_utc"] == "2026-08-27T11:50:48Z"
    assert first["latest_possible_end_source"] == "boot_utc"
    assert first["end_uncertainty_human"] == "0h56m08s"
    assert first["max_possible_span_s"] == pytest.approx(25346.9)
    assert first["max_possible_span_human"] == "7h02m26s"
    assert first["ongoing"] is False


def test_real_log_second_outage_started_at_the_tailscale_last_seen():
    """Outage 2 is still open, so only its start side is pinnable. Round
    310's prose measured this outage from LastSeen (02:10:00.1Z) while every
    tool-reported figure since round 316 measured it from the first down
    CHECK (02:13:07Z) -- a 3m06s disagreement nothing reconciled until the
    bracket made both bounds first-class."""
    bounds = [b for b in rc.streak_bounds(_real_log_records())
              if b["verdict"] == "down"]
    second = bounds[1]
    assert second["start_round"] == 298
    assert second["first_check_utc"] == "2026-08-29T02:13:07Z"
    assert second["earliest_possible_start_utc"] == "2026-08-29T02:10:00.1Z"
    assert second["earliest_possible_start_source"] == "tailscale_last_seen"
    assert second["start_uncertainty_s"] == pytest.approx(186.9)
    assert second["start_uncertainty_human"] == "0h03m06s"
    assert second["ongoing"] is True
    assert second["max_possible_span_s"] is None


def test_real_log_every_bracket_is_internally_consistent():
    """Invariants that must hold for EVERY streak in the real log, now and
    as future rounds append to it: uncertainties are never negative, and a
    confirmed span never exceeds its own max-possible span."""
    for b in rc.streak_bounds(_real_log_records()):
        assert b["confirmed_span_s"] >= 0, b
        if b["start_uncertainty_s"] is not None:
            assert b["start_uncertainty_s"] >= 0, b
        if b["end_uncertainty_s"] is not None:
            assert b["end_uncertainty_s"] >= 0, b
        if b["max_possible_span_s"] is not None:
            assert b["max_possible_span_s"] >= b["confirmed_span_s"], b
        # an unbounded side must leave the whole max-possible span unstated
        if b["start_uncertainty_s"] is None or b["end_uncertainty_s"] is None:
            assert b["max_possible_span_s"] is None, b


# --- boot_utc as a START bound on its own streak (round 334) --------------------

def test_streak_bounds_boot_utc_tightens_its_own_up_streaks_start():
    """The mirror of the LastSeen rule: nothing before the box booted can
    belong to the up streak that boot began, so a boot time later than the
    last down check is a strictly tighter start bound than that check."""
    records = list(BRACKET_RECORDS)
    records[4] = dict(records[4], boot_utc="2026-08-27T11:00:00Z")
    b = _bounds_by_rounds(records, 5)
    assert b["earliest_possible_start_utc"] == "2026-08-27T11:00:00Z"
    assert b["earliest_possible_start_source"] == "boot_utc"
    assert b["start_uncertainty_s"] == 2 * 3600.0     # 11:00 -> 13:00, was 3h


def test_streak_bounds_boot_utc_bounds_a_log_that_opens_on_an_up_record():
    """With no preceding streak there is normally no start bound at all --
    a boot time supplies one, so the opening streak gets a real
    max_possible_span instead of None."""
    records = [
        {"checked_at_utc": "2026-08-27T13:00:00Z", "round": 1, "verdict": "up",
         "boot_utc": "2026-08-27T11:00:00Z"},
        {"checked_at_utc": "2026-08-27T15:00:00Z", "round": 2, "verdict": "down"},
    ]
    b = _bounds_by_rounds(records, 1)
    assert b["earliest_possible_start_source"] == "boot_utc"
    assert b["max_possible_span_s"] == 4 * 3600.0     # 11:00 -> 15:00


def test_streak_bounds_ignores_a_boot_utc_after_its_own_first_check():
    """A boot recorded as happening after we already observed the box up is
    contradictory -- fall back rather than invert the bracket."""
    records = [
        {"checked_at_utc": "2026-08-27T10:00:00Z", "round": 1, "verdict": "down"},
        {"checked_at_utc": "2026-08-27T13:00:00Z", "round": 2, "verdict": "up",
         "boot_utc": "2026-08-27T14:00:00Z"},
    ]
    b = _bounds_by_rounds(records, 2)
    assert b["earliest_possible_start_source"] == "previous_check"
    assert b["earliest_possible_start_utc"] == "2026-08-27T10:00:00Z"


def test_streak_bounds_mid_streak_boot_utc_is_not_read():
    """Only the streak's FIRST record's boot time is evidence about when
    THAT streak began; a boot recorded later in the same streak would be a
    mid-streak reboot, which a single bracket cannot represent."""
    records = list(BRACKET_RECORDS)
    records[1] = dict(records[1], boot_utc="2026-08-27T03:00:00Z")
    b = _bounds_by_rounds(records, 1)
    assert b["earliest_possible_start_source"] is None


def test_real_log_up_streak_after_the_reboot_starts_at_the_boot_not_the_check():
    """Round 202's boot time bounds BOTH sides of the transition it
    straddles: it closes outage 1 and opens the 202-286 up streak."""
    up = [b for b in rc.streak_bounds(_real_log_records()) if b["verdict"] == "up"][1]
    assert (up["start_round"], up["end_round"]) == (202, 286)
    assert up["earliest_possible_start_utc"] == "2026-08-27T11:50:48Z"
    assert up["earliest_possible_start_source"] == "boot_utc"
    assert up["confirmed_span_human"] == "32h23m22s"
    assert up["max_possible_span_human"] == "38h22m19s"


# ==========================================================================
# Round 340: gap continuity -- is a streak we report as unbroken actually
# unbroken? `summarize_log`'s n_streaks is a LOWER bound on the number of
# state transitions in exactly the way round 334 showed `confirmed_span_s`
# is a lower bound on duration.
# ==========================================================================

def _rec(ts, verdict, rnd=None, last_seen=None, boot=None):
    r = {"checked_at_utc": ts, "verdict": verdict, "round": rnd}
    if last_seen is not None:
        r["tailscale_last_seen_utc"] = last_seen
    if boot is not None:
        r["boot_utc"] = boot
    return r


# --- the down-side witness rule -------------------------------------------

def test_gap_witnessed_when_last_seen_precedes_the_earlier_down_check():
    """The core rule. A LastSeen read at t2 that points at or before t1
    means the peer was not seen on the tailnet at any instant in (t1, t2],
    so no up excursion can hide in the gap."""
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1),
            _rec("2026-01-01T14:00:00Z", "down", 2, last_seen="2026-01-01T09:30:00Z")]
    gap = rc.gap_continuity(recs)[0]["gaps"][0]
    assert gap["witnessed"] is True
    assert gap["witness_strength"] == rc.WITNESS_FULL
    assert gap["witness_source"] == "tailscale_last_seen"
    assert gap["gap_human"] == "4h00m00s"
    # The note names both timestamps in the log's own canonical form, so a
    # reader can check the rule by eye without re-deriving it.
    assert "2026-01-01T09:30:00Z" in gap["witness_note"]
    assert "2026-01-01T10:00:00Z" in gap["witness_note"]


def test_gap_witness_needs_no_last_seen_on_the_EARLIER_record():
    """Strictly more general than "LastSeen unchanged across both records",
    and this generality is not hypothetical: the real 184->196 gap's earlier
    record predates the field entirely, and is still fully witnessed by the
    later record alone."""
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1),
            _rec("2026-01-01T14:00:00Z", "down", 2, last_seen="2026-01-01T08:00:00Z")]
    assert rc.gap_continuity(recs)[0]["gaps"][0]["witnessed"] is True


def test_gap_witnessed_when_last_seen_lands_exactly_on_the_earlier_check():
    """Boundary: `<= t1` is the rule, not `< t1`. A peer last seen at the
    very instant of the earlier check was still not seen strictly inside
    the gap, so the gap is witnessed."""
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1),
            _rec("2026-01-01T14:00:00Z", "down", 2, last_seen="2026-01-01T10:00:00Z")]
    assert rc.gap_continuity(recs)[0]["gaps"][0]["witnessed"] is True


def test_gap_unwitnessed_when_the_later_record_has_no_last_seen():
    """Fails closed. Absent evidence is not evidence of continuity, and
    this is the shape every backfilled coarse record has."""
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1),
            _rec("2026-01-01T14:00:00Z", "down", 2)]
    gap = rc.gap_continuity(recs)[0]["gaps"][0]
    assert gap["witnessed"] is False
    assert gap["witness_strength"] == rc.WITNESS_NONE
    assert "no tailscale_last_seen_utc" in gap["witness_note"]


def test_last_seen_strictly_inside_a_down_gap_is_a_reported_missed_excursion():
    """Positive evidence that contradicts us must be surfaced, not dropped.
    A LastSeen inside a span the log calls one continuous outage means the
    box WAS alive in there and this log's streak count is wrong."""
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1),
            _rec("2026-01-01T14:00:00Z", "down", 2, last_seen="2026-01-01T12:00:00Z")]
    streak = rc.gap_continuity(recs)[0]
    assert streak["gaps"][0]["witnessed"] is False
    assert len(streak["missed_excursions"]) == 1
    m = streak["missed_excursions"][0]
    assert m["kind"] == "tailscale_last_seen_inside_gap"
    assert m["evidence_utc"] == "2026-01-01T12:00:00Z"
    assert (m["from_round"], m["to_round"]) == (1, 2)
    assert rc.continuity_report(recs)["missed_excursions"] == [m]


def test_last_seen_at_or_after_the_later_down_check_is_contradictory_not_a_witness():
    """Mirrors round 334's `streak_bounds` rule: a LastSeen at/after a check
    that called the box down implies more transitions than one gap can
    represent. Dropped with a named reason, never clamped into a witness."""
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1),
            _rec("2026-01-01T14:00:00Z", "down", 2, last_seen="2026-01-01T14:00:00Z")]
    gap = rc.gap_continuity(recs)[0]["gaps"][0]
    assert gap["witnessed"] is False
    assert "contradictory" in gap["witness_note"]
    assert rc.gap_continuity(recs)[0]["missed_excursions"] == []


def test_ambiguous_streaks_use_the_same_last_seen_rule_as_down():
    recs = [_rec("2026-01-01T10:00:00Z", "ambiguous", 1),
            _rec("2026-01-01T14:00:00Z", "ambiguous", 2, last_seen="2026-01-01T09:00:00Z")]
    assert rc.gap_continuity(recs)[0]["gaps"][0]["witnessed"] is True


@pytest.mark.parametrize("verdict", ["up", "down", "ambiguous"])
def test_both_last_seen_rules_agree_on_which_verdicts_they_apply_to(verdict):
    """`_LAST_SEEN_WITNESSES_GAP` is aliased to `_LAST_SEEN_BOUNDS_START` so
    the two rules can never drift apart on which verdicts LastSeen means
    "not seen since" for. This asserts that BEHAVIOURALLY, per verdict.

    The obvious version -- `assert A is B` -- is not a test at all: CPython
    deduplicates equal constants inside one module's constant pool, so two
    separate `("down", "ambiguous")` literals ARE the same object and the
    identity assertion passes whether the alias exists or not. It was
    written that way here first and a mutant that replaced the alias with an
    equal literal survived, which is how the hole was found. Verified
    directly: `compile()`ing a module with two such literals yields exactly
    one tuple in `co_consts`."""
    same_last_seen = "2026-01-01T09:00:00Z"
    gap_uses_it = rc.gap_continuity([
        _rec("2026-01-01T10:00:00Z", verdict, 1),
        _rec("2026-01-01T14:00:00Z", verdict, 2, last_seen=same_last_seen),
    ])[0]["gaps"][0]["witness_source"] == "tailscale_last_seen"
    bounds_uses_it = rc.streak_bounds([
        _rec("2026-01-01T00:00:00Z", "other", 0),
        _rec("2026-01-01T10:00:00Z", verdict, 1, last_seen=same_last_seen),
        _rec("2026-01-01T14:00:00Z", verdict, 2, last_seen=same_last_seen),
    ])[1]["earliest_possible_start_source"] == "tailscale_last_seen"
    assert gap_uses_it == bounds_uses_it, verdict
    assert gap_uses_it is (verdict in ("down", "ambiguous"))


# --- the up-side rule, and why it is deliberately NOT a witness -----------

def test_boot_utc_unchanged_is_reboot_only_and_does_not_count_as_witnessed():
    """The round's sharpest negative result. `/proc/uptime`'s first field is
    CLOCK_BOOTTIME-based and keeps counting across suspend, so an unchanged
    boot time excludes a REBOOT but not a suspend/resume -- and suspend is
    this box's own documented failure mode. Recording it as `reboot_only`
    rather than `full` is what stops the tool offering false comfort."""
    recs = [_rec("2026-01-01T10:00:00Z", "up", 1, boot="2026-01-01T08:00:00Z"),
            _rec("2026-01-01T14:00:00Z", "up", 2, boot="2026-01-01T08:00:00Z")]
    gap = rc.gap_continuity(recs)[0]["gaps"][0]
    assert gap["witness_strength"] == rc.WITNESS_REBOOT_ONLY
    assert gap["witness_source"] == "boot_utc_unchanged"
    assert gap["witnessed"] is False           # <- the load-bearing assertion
    assert "suspend" in gap["witness_note"]
    assert rc.continuity_report(recs)["unwitnessed_gap_count"] == 1


def test_boot_utc_advancing_inside_an_up_streak_is_a_missed_excursion():
    """Two up checks straddling a reboot: the box demonstrably went down and
    came back, and the log renders it as one unbroken up streak."""
    recs = [_rec("2026-01-01T10:00:00Z", "up", 1, boot="2026-01-01T08:00:00Z"),
            _rec("2026-01-01T14:00:00Z", "up", 2, boot="2026-01-01T13:00:00Z")]
    streak = rc.gap_continuity(recs)[0]
    assert streak["gaps"][0]["witnessed"] is False
    assert streak["missed_excursions"][0]["kind"] == "boot_utc_advanced_inside_gap"
    assert streak["missed_excursions"][0]["evidence_utc"] == "2026-01-01T13:00:00Z"


def test_boot_utc_moving_backwards_is_contradictory_not_an_excursion():
    """A boot time that goes backwards is a clock or parsing fault, not a
    state change. Reported as contradictory; asserting an excursion from it
    would be inventing a transition out of an instrument error."""
    recs = [_rec("2026-01-01T10:00:00Z", "up", 1, boot="2026-01-01T09:00:00Z"),
            _rec("2026-01-01T14:00:00Z", "up", 2, boot="2026-01-01T08:00:00Z")]
    streak = rc.gap_continuity(recs)[0]
    gap = streak["gaps"][0]
    assert "contradictory" in gap["witness_note"]
    assert streak["missed_excursions"] == []
    # An instrument fault earns NO witness credit, not even the weak kind:
    # the reported strength is the evidence a reader acts on, and labelling
    # a backwards clock `reboot_only` would claim we had ruled a reboot out.
    assert gap["witness_strength"] == rc.WITNESS_NONE
    assert gap["witness_source"] is None
    assert gap["witnessed"] is False


def test_up_gap_with_boot_utc_on_only_one_endpoint_is_unwitnessed():
    """A boot-time witness needs both endpoints; one is the shape the real
    log has (exactly one record carries boot_utc)."""
    for a, b in (("2026-01-01T08:00:00Z", None), (None, "2026-01-01T08:00:00Z")):
        recs = [_rec("2026-01-01T10:00:00Z", "up", 1, boot=a),
                _rec("2026-01-01T14:00:00Z", "up", 2, boot=b)]
        gap = rc.gap_continuity(recs)[0]["gaps"][0]
        assert gap["witness_strength"] == rc.WITNESS_NONE
        assert "boot_utc missing" in gap["witness_note"]


def test_last_seen_is_never_read_as_a_witness_on_an_up_streak():
    """Round 334's asymmetry, carried forward: on an up record LastSeen
    means "seen alive during this streak", which says nothing about whether
    the interior was unbroken. A LastSeen that WOULD witness a down gap must
    leave an up gap unwitnessed."""
    recs = [_rec("2026-01-01T10:00:00Z", "up", 1),
            _rec("2026-01-01T14:00:00Z", "up", 2, last_seen="2026-01-01T09:00:00Z")]
    gap = rc.gap_continuity(recs)[0]["gaps"][0]
    assert gap["witnessed"] is False
    assert gap["witness_source"] is None


# --- structure ------------------------------------------------------------

def test_transition_gaps_are_not_counted_as_continuity_ignorance():
    """The gap between the last check of one streak and the first of the
    next is a TRANSITION, already bracketed by round 334's `streak_bounds`.
    Counting it here too would mix two different unknowns and double-count
    the same seconds."""
    recs = [_rec("2026-01-01T10:00:00Z", "up", 1),
            _rec("2026-01-01T11:00:00Z", "up", 2),
            _rec("2026-01-01T20:00:00Z", "down", 3),
            _rec("2026-01-01T21:00:00Z", "down", 4, last_seen="2026-01-01T19:00:00Z")]
    rep = rc.continuity_report(recs)
    assert rep["n_gaps"] == 2                      # not 3
    assert rep["transition_gap_total_s"] == 9 * 3600.0
    assert rep["unwitnessed_total_s"] == 3600.0    # the up gap only


def test_continuity_report_time_buckets_partition_the_log_span():
    """witnessed + unwitnessed + transition == the whole span, exactly.
    This is what makes `unwitnessed_fraction` a fraction of something real
    rather than of a denominator picked to flatter the number."""
    recs = _real_log_records()
    rep = rc.continuity_report(recs)
    assert (rep["witnessed_total_s"] + rep["unwitnessed_total_s"]
            + rep["transition_gap_total_s"]) == pytest.approx(rep["log_span_s"])
    assert rep["unwitnessed_fraction"] == pytest.approx(
        rep["unwitnessed_total_s"] / rep["log_span_s"])


def test_single_check_streak_is_trivially_continuous_with_zero_gaps():
    recs = [_rec("2026-01-01T10:00:00Z", "up", 1),
            _rec("2026-01-01T20:00:00Z", "down", 2)]
    streaks = rc.gap_continuity(recs)
    assert [s["n_gaps"] for s in streaks] == [0, 0]
    assert all(s["continuous_confirmed"] for s in streaks)
    assert rc.continuity_report(recs)["n_gaps"] == 0


def test_empty_and_single_record_logs_do_not_crash():
    assert rc.gap_continuity([]) == []
    empty = rc.continuity_report([])
    assert empty["n_gaps"] == 0 and empty["log_span_s"] == 0.0
    assert empty["unwitnessed_fraction"] is None
    assert empty["confirmed_transitions"] == 0
    one = rc.continuity_report([_rec("2026-01-01T10:00:00Z", "up", 1)])
    assert one["n_streaks"] == 1 and one["n_gaps"] == 0
    assert one["all_streaks_confirmed_continuous"] is True


def test_records_are_time_ordered_before_gaps_are_measured():
    """Gaps must never come out negative just because the caller handed the
    log in file order that happens not to be sorted."""
    recs = [_rec("2026-01-01T14:00:00Z", "down", 2, last_seen="2026-01-01T09:00:00Z"),
            _rec("2026-01-01T10:00:00Z", "down", 1)]
    gap = rc.gap_continuity(recs)[0]["gaps"][0]
    assert gap["gap_s"] == 4 * 3600.0
    assert (gap["from_round"], gap["to_round"]) == (1, 2)


def test_transition_count_upper_bound_is_none_while_any_gap_is_unwitnessed():
    """Round 334's discipline applied to a count instead of a span: an
    unwitnessed gap admits arbitrarily many round trips, so there is
    genuinely no upper bound and printing one would be inventing it."""
    unwit = [_rec("2026-01-01T10:00:00Z", "up", 1),
             _rec("2026-01-01T14:00:00Z", "up", 2)]
    rep = rc.continuity_report(unwit)
    assert rep["confirmed_transitions"] == 0
    assert rep["transition_count_upper_bound"] is None
    assert rep["all_streaks_confirmed_continuous"] is False
    wit = [_rec("2026-01-01T10:00:00Z", "down", 1),
           _rec("2026-01-01T14:00:00Z", "down", 2, last_seen="2026-01-01T09:00:00Z"),
           _rec("2026-01-01T20:00:00Z", "up", 3)]
    rep2 = rc.continuity_report(wit)
    assert rep2["confirmed_transitions"] == 1
    assert rep2["transition_count_upper_bound"] == 1
    assert rep2["all_streaks_confirmed_continuous"] is True


# --- where a hidden streak can hide --------------------------------------

def test_a_hidden_outage_can_only_live_inside_an_up_streaks_gap():
    """The asymmetry that makes `max_unobserved_outage_s` meaningful: an
    outage hides in an up gap, an up excursion hides in a down gap. A log
    whose down gaps are all witnessed still admits a hidden outage."""
    recs = [_rec("2026-01-01T10:00:00Z", "up", 1),
            _rec("2026-01-02T00:00:00Z", "up", 2),
            _rec("2026-01-02T04:00:00Z", "down", 3),
            _rec("2026-01-02T06:00:00Z", "down", 4, last_seen="2026-01-02T03:00:00Z")]
    rep = rc.continuity_report(recs)
    assert rep["max_unobserved_outage_s"] == 14 * 3600.0
    assert rep["max_unobserved_outage_human"] == "14h00m00s"
    assert rep["max_unobserved_outage_window"]["from_round"] == 1
    assert rep["max_unobserved_uptime_s"] is None


def test_max_unobserved_streak_s_looks_at_the_opposite_verdicts_gaps():
    recs = [_rec("2026-01-01T10:00:00Z", "up", 1),
            _rec("2026-01-01T18:00:00Z", "up", 2),
            _rec("2026-01-02T04:00:00Z", "down", 3),
            _rec("2026-01-02T09:00:00Z", "down", 4)]
    down_hidden = rc.max_unobserved_streak_s(recs, "down")
    assert down_hidden["gap_s"] == 8 * 3600.0        # inside the up streak
    up_hidden = rc.max_unobserved_streak_s(recs, "up")
    assert up_hidden["gap_s"] == 5 * 3600.0          # inside the down streak
    assert rc.max_unobserved_streak_s(recs[:2], "up") is None


# --- the record claim, third competitor ----------------------------------

def test_status_abstains_on_the_unobserved_comparison_when_nothing_can_hide():
    """`definitely_longest_including_unobserved` is None, not True, when the
    log offers no hidden competitor at all -- True would read as "we checked
    a real alternative and beat it"."""
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1),
            _rec("2026-01-01T12:00:00Z", "down", 2, last_seen="2026-01-01T09:00:00Z")]
    st = rc.current_streak_duration(recs, now_fn=lambda: "2026-01-01T13:00:00Z")
    assert st["max_unobserved_same_verdict_streak_s"] is None
    assert st["definitely_longest_including_unobserved"] is None


def test_status_record_claim_fails_against_a_longer_hidden_outage():
    """An outage that beats every outage we SAW can still lose to one we
    could have missed. This is the case rounds 322/328/334 were actually in
    and had no way to see."""
    recs = [
        _rec("2026-01-01T00:00:00Z", "up", 1),
        _rec("2026-01-02T00:00:00Z", "up", 2),          # 24h unwitnessed up gap
        _rec("2026-01-02T02:00:00Z", "down", 3, last_seen="2026-01-02T01:00:00Z"),
        _rec("2026-01-02T03:00:00Z", "down", 4, last_seen="2026-01-02T01:00:00Z"),
        _rec("2026-01-02T04:00:00Z", "up", 5),
        _rec("2026-01-02T06:00:00Z", "down", 6, last_seen="2026-01-02T05:00:00Z"),
    ]
    st = rc.current_streak_duration(recs, now_fn=lambda: "2026-01-02T16:00:00Z")
    assert st["verdict"] == "down"
    assert st["exceeds_longest_completed"] is True          # beats what we saw
    assert st["definitely_exceeds_longest_completed"] is True
    assert st["max_unobserved_same_verdict_streak_s"] == 24 * 3600.0
    assert st["definitely_longest_including_unobserved"] is False   # ...but not this
    assert st["unobserved_margin_s"] == -14 * 3600.0
    assert st["unobserved_margin_human"] == "14h00m00s"     # magnitude; sign is the field


def test_status_record_claim_succeeds_once_elapsed_passes_the_hidden_bound():
    """Same log, run later: the claim becomes supportable at a computable
    instant rather than whenever someone asserts it."""
    recs = [
        _rec("2026-01-01T00:00:00Z", "up", 1),
        _rec("2026-01-02T00:00:00Z", "up", 2),
        _rec("2026-01-02T02:00:00Z", "down", 3, last_seen="2026-01-02T01:00:00Z"),
        _rec("2026-01-02T03:00:00Z", "down", 4, last_seen="2026-01-02T01:00:00Z"),
        _rec("2026-01-02T04:00:00Z", "up", 5),
        _rec("2026-01-02T06:00:00Z", "down", 6, last_seen="2026-01-02T05:00:00Z"),
    ]
    st = rc.current_streak_duration(recs, now_fn=lambda: "2026-01-03T07:00:00Z")
    assert st["elapsed_s"] == 25 * 3600.0
    assert st["definitely_longest_including_unobserved"] is True
    assert st["unobserved_margin_s"] == 3600.0


def test_status_bracket_fields_from_round_334_are_untouched():
    """A regression guard on the round-334 contract: adding the unobserved
    competitor must not move any pre-existing field's value."""
    recs = _real_log_through_round(340)
    st = rc.current_streak_duration(recs, now_fn=lambda: "2026-08-29T17:21:00Z")
    assert st["elapsed_s"] == 54473.0
    assert st["elapsed_human"] == "15h07m53s"
    assert st["longest_completed_same_verdict_streak_s"] == 18880.0
    assert st["definitely_exceeds_longest_completed"] is True
    assert st["definite_margin_human"] == "8h05m26s"
    assert st["earliest_possible_start_source"] == "tailscale_last_seen"


# --- the real log ---------------------------------------------------------

def test_real_log_every_down_gap_is_witnessed_and_every_up_gap_is_not():
    """The headline split, pinned. It is not a coincidence: LastSeen is the
    only continuity witness this log has, and it is only meaningful on a
    down record."""
    for s in rc.gap_continuity(_real_log_through_round(340)):
        for g in s["gaps"]:
            assert g["witnessed"] is (s["verdict"] == "down"), (s["verdict"], g)
    # The up half is an invariant, not a fact about the current data, so it
    # holds against the LIVE log too and will keep holding as the box comes
    # back and up checks resume: `check()` now records boot_utc on every up
    # record, and boot_utc unchanged is `reboot_only`, never `full`.
    for s in rc.gap_continuity(_real_log_records()):
        if s["verdict"] == "up":
            assert not any(g["witnessed"] for g in s["gaps"]), s


def test_real_log_both_outages_are_provably_continuous():
    """The prose claim every round since 298 has made -- "one continuous
    outage" -- is now computed rather than asserted. Outage 1 too, which no
    round ever claimed because nothing could check it."""
    downs = [s for s in rc.gap_continuity(_real_log_through_round(340))
             if s["verdict"] == "down"]
    assert [s["start_round"] for s in downs] == [184, 298]
    assert all(s["continuous_confirmed"] for s in downs)
    assert all(s["unwitnessed_total_s"] == 0 for s in downs)


def test_real_log_neither_up_streak_is_provably_continuous():
    ups = [s for s in rc.gap_continuity(_real_log_through_round(340))
           if s["verdict"] == "up"]
    assert [s["start_round"] for s in ups] == [124, 202]
    assert not any(s["continuous_confirmed"] for s in ups)
    assert [s["max_unwitnessed_gap_human"] for s in ups] == ["14h00m00s", "8h01m00s"]


def test_real_log_worst_blind_spot_is_the_r142_to_r154_gap():
    """The number that reframes this track's whole history: a complete
    14-hour outage could have happened between rounds 142 and 154 and left
    no trace anywhere in this log."""
    rep = rc.continuity_report(_real_log_through_round(340))
    assert rep["max_unobserved_outage_s"] == 50400.0
    assert rep["max_unobserved_outage_human"] == "14h00m00s"
    assert rep["max_unobserved_outage_window"] == {
        "from_round": 142, "to_round": 154,
        "from_utc": "2026-08-26T03:19:00Z", "to_utc": "2026-08-26T17:19:00Z",
    }
    # Against the live log the bound can only ever grow (a new up gap could
    # be worse; an old one cannot shrink). A future round that finds this
    # number has gone UP has found a new worst blind spot and owes the
    # `definitely_longest_including_unobserved` claim a re-check.
    live = rc.continuity_report(_real_log_records())
    assert live["max_unobserved_outage_s"] >= 50400.0


def test_real_log_two_thirds_of_the_span_is_unwitnessed():
    rep = rc.continuity_report(_real_log_through_round(340))
    assert rep["n_gaps"] == 29
    assert (rep["witnessed_gap_count"], rep["unwitnessed_gap_count"]) == (11, 18)
    assert rep["unwitnessed_total_human"] == "67h26m22s"
    assert 0.68 < rep["unwitnessed_fraction"] < 0.71


def test_real_log_has_no_detected_missed_excursions():
    """Zero here is a real result, not a vacuous one: the two rules CAN
    fire (`test_last_seen_strictly_inside_a_down_gap...`,
    `test_boot_utc_advancing_inside_an_up_streak...` both do), and on this
    log neither does."""
    assert rc.continuity_report(_real_log_through_round(340))["missed_excursions"] == []
    # Deliberately also run against the LIVE log. If a future append ever
    # makes this fail, that is a FINDING, not a regression: the log would be
    # carrying positive evidence that a streak it reports as unbroken was
    # broken. The round that sees it red should investigate the excursion,
    # not relax the assertion.
    assert rc.continuity_report(_real_log_records())["missed_excursions"] == []


def test_real_log_current_outage_now_clears_the_hidden_competitor():
    """Round 340 is the first round in which the "longest outage this track
    has measured" claim is supportable. Pinned against a FIXED `now` so the
    test asserts the round-340 finding rather than drifting with the clock:
    the crossing instant is first-down-check 02:13:07Z + the 14h00m hidden
    bound = 2026-08-29T16:13:07Z, and round 334's own last check (13:02:44Z)
    is 3h10m23s short of it."""
    recs = _real_log_through_round(340)
    at_340 = rc.current_streak_duration(recs, now_fn=lambda: "2026-08-29T17:21:00Z")
    assert at_340["max_unobserved_same_verdict_streak_s"] == 50400.0
    assert at_340["definitely_longest_including_unobserved"] is True
    assert at_340["unobserved_margin_human"] == "1h07m53s"
    at_334 = rc.current_streak_duration(recs, now_fn=lambda: "2026-08-29T13:02:44Z")
    assert at_334["exceeds_longest_completed"] is True            # what 334 reported
    assert at_334["definitely_exceeds_longest_completed"] is True
    assert at_334["definitely_longest_including_unobserved"] is False  # unsupported
    assert at_334["unobserved_margin_human"] == "3h10m23s"


# --- CLI ------------------------------------------------------------------

def test_cli_continuity_prints_the_rollup_without_per_gap_detail(capsys):
    assert rc.main(["continuity", "--log-path", str(REAL_LOG)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["n_gaps"] >= 29        # 29 at round 340; grows with the log
    assert "gaps" not in out["streaks"][0]


def test_cli_continuity_gaps_flag_includes_the_per_gap_detail(capsys):
    assert rc.main(["continuity", "--log-path", str(REAL_LOG), "--gaps",
                    "--verdict", "up"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [s["verdict"] for s in out["streaks"]] == ["up", "up"]
    assert all("gaps" in s for s in out["streaks"])
    # the rollup counts stay whole-log even when the streak list is filtered
    assert out["n_gaps"] >= 29


def test_cli_continuity_verdict_filter_without_gaps_flag(capsys):
    assert rc.main(["continuity", "--log-path", str(REAL_LOG),
                    "--verdict", "down"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [s["verdict"] for s in out["streaks"]] == ["down", "down"]
    assert all("gaps" not in s for s in out["streaks"])


# ==========================================================================
# Round 340: witnesses from the BOX's own continuous record.
# `journalctl --list-boots -o json` is the only source available here that
# was written while nobody was probing, so it is the only one that can
# witness an UP-streak gap at all. Built and tested entirely offline -- the
# box has been unreachable since 2026-08-29T02:10Z.
# ==========================================================================

# Real shape of `journalctl --list-boots -o json`: microseconds since the
# epoch. 2026-08-26T00:00:00Z = 1787788800; times below are that + offsets.
def _usec(iso):
    import datetime as _dt
    return int(_dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
               .replace(tzinfo=_dt.timezone.utc).timestamp()) * 1_000_000


BOOT_JSON_TWO_BOOTS = json.dumps([
    {"index": -1, "boot_id": "aaa", "first_entry": _usec("2026-08-25T12:00:00Z"),
     "last_entry": _usec("2026-08-26T06:00:00Z")},
    {"index": 0, "boot_id": "bbb", "first_entry": _usec("2026-08-26T09:00:00Z"),
     "last_entry": _usec("2026-08-27T00:00:00Z")},
])


def test_parse_boot_history_normalises_microseconds_to_utc():
    boots = rc.parse_boot_history(BOOT_JSON_TWO_BOOTS)
    assert [b["boot_id"] for b in boots] == ["aaa", "bbb"]
    assert boots[0]["first_entry_utc"] == "2026-08-25T12:00:00Z"
    assert boots[0]["last_entry_utc"] == "2026-08-26T06:00:00Z"
    assert boots[1]["first_entry_utc"] == "2026-08-26T09:00:00Z"


def test_parse_boot_history_accepts_decimal_string_timestamps():
    """systemd emits these as JSON numbers on some versions and decimal
    strings on others; the box's version is unknown (it is down), so both
    parse."""
    text = json.dumps([{"index": 0, "boot_id": "s",
                        "first_entry": str(_usec("2026-08-26T09:00:00Z")),
                        "last_entry": str(_usec("2026-08-26T10:00:00Z"))}])
    boots = rc.parse_boot_history(text)
    assert boots[0]["first_entry_utc"] == "2026-08-26T09:00:00Z"


def test_parse_boot_history_sorts_by_first_entry_not_by_index():
    """`index` is systemd's own relative numbering (0 = current, negative =
    older) and is not something the witness rules should have to trust; the
    rules pair ADJACENT boots, so ordering must come from the timestamps."""
    rows = json.loads(BOOT_JSON_TWO_BOOTS)
    boots = rc.parse_boot_history(json.dumps(list(reversed(rows))))
    assert [b["boot_id"] for b in boots] == ["aaa", "bbb"]


@pytest.mark.parametrize("text", [
    "", "   ", "not json", "{}", "[]", "null", '[{"index": 0}]',
    '[{"first_entry": 0, "last_entry": 0}]',
    '[{"first_entry": "x", "last_entry": "y"}]',
    '[{"first_entry": null, "last_entry": 1787788800000000}]',
    '["a string, not an object"]',
])
def test_parse_boot_history_fails_closed_on_anything_unusable(text):
    """A witness parser's failure mode must be "no evidence", never an
    exception a caller might catch and treat as one."""
    assert rc.parse_boot_history(text) == []


def test_parse_boot_history_drops_a_boot_whose_entries_are_inverted():
    text = json.dumps([{"index": 0, "boot_id": "bad",
                        "first_entry": _usec("2026-08-26T10:00:00Z"),
                        "last_entry": _usec("2026-08-26T09:00:00Z")}])
    assert rc.parse_boot_history(text) == []


def test_boot_history_witnesses_an_up_gap_no_probe_rule_can_reach():
    """The point of the whole source: an up gap that `boot_utc` can only
    call `reboot_only` becomes a FULL witness, because the box's own journal
    ran across it."""
    recs = [_rec("2026-08-25T18:00:00Z", "up", 1),
            _rec("2026-08-26T04:00:00Z", "up", 2)]
    boots = rc.parse_boot_history(BOOT_JSON_TWO_BOOTS)
    assert rc.gap_continuity(recs)[0]["gaps"][0]["witnessed"] is False
    gap = rc.gap_continuity(recs, boots)[0]["gaps"][0]
    assert gap["witnessed"] is True
    assert gap["witness_source"] == "boot_history"
    assert "aaa" in gap["witness_note"]
    assert rc.continuity_report(recs, boots)["all_streaks_confirmed_continuous"] is True


def test_boot_history_finds_a_missed_outage_with_exact_bounds():
    """Strictly more than any probe rule can produce: not just "an outage
    could have hidden here" but "one did, from 06:00 to 09:00"."""
    recs = [_rec("2026-08-26T05:00:00Z", "up", 1),
            _rec("2026-08-26T12:00:00Z", "up", 2)]
    boots = rc.parse_boot_history(BOOT_JSON_TWO_BOOTS)
    streak = rc.gap_continuity(recs, boots)[0]
    assert streak["gaps"][0]["witnessed"] is False
    m = streak["missed_excursions"][0]
    assert m["kind"] == "boot_history_gap_inside_up_streak"
    assert m["outage_from_utc"] == "2026-08-26T06:00:00Z"
    assert m["outage_to_utc"] == "2026-08-26T09:00:00Z"


def test_boot_history_covering_only_part_of_a_gap_witnesses_nothing():
    """Partial coverage is not coverage. The gap starts before boot `aaa`'s
    first entry, so nothing rules out an outage in the uncovered head."""
    recs = [_rec("2026-08-25T06:00:00Z", "up", 1),
            _rec("2026-08-26T04:00:00Z", "up", 2)]
    boots = rc.parse_boot_history(json.dumps(json.loads(BOOT_JSON_TWO_BOOTS)[:1]))
    gap = rc.gap_continuity(recs, boots)[0]["gaps"][0]
    assert gap["witnessed"] is False
    assert gap["witness_source"] is None


def test_boot_history_with_only_the_current_boot_witnesses_nothing_earlier():
    """The real deployment risk: journald `Storage=volatile` lists only the
    current boot, so the history says nothing about any older gap. It must
    degrade to the existing rules, not to a false witness."""
    boots = rc.parse_boot_history(json.dumps(json.loads(BOOT_JSON_TWO_BOOTS)[1:]))
    recs = [_rec("2026-08-25T18:00:00Z", "up", 1),
            _rec("2026-08-26T04:00:00Z", "up", 2)]
    assert rc.gap_continuity(recs, boots)[0]["gaps"][0]["witnessed"] is False


def test_boot_history_is_not_applied_to_down_streaks():
    """A down streak already has a real witness (LastSeen). Letting boot
    history speak there too would mean claiming the box was logging during
    an interval we observed it unreachable at both ends -- a contradiction
    to investigate, not a witness to record."""
    recs = [_rec("2026-08-25T18:00:00Z", "down", 1),
            _rec("2026-08-26T04:00:00Z", "down", 2)]
    boots = rc.parse_boot_history(BOOT_JSON_TWO_BOOTS)
    gap = rc.gap_continuity(recs, boots)[0]["gaps"][0]
    assert gap["witnessed"] is False
    assert gap["witness_source"] is None


def test_boot_history_beats_boot_utc_when_both_apply():
    """`boot_utc` is two endpoint samples of the fact the journal records
    continuously, so the continuous source wins and the gap is FULL rather
    than reboot_only."""
    recs = [_rec("2026-08-25T18:00:00Z", "up", 1, boot="2026-08-25T12:00:00Z"),
            _rec("2026-08-26T04:00:00Z", "up", 2, boot="2026-08-25T12:00:00Z")]
    boots = rc.parse_boot_history(BOOT_JSON_TWO_BOOTS)
    assert rc.gap_continuity(recs)[0]["gaps"][0]["witness_strength"] == rc.WITNESS_REBOOT_ONLY
    assert rc.gap_continuity(recs, boots)[0]["gaps"][0]["witness_strength"] == rc.WITNESS_FULL


def test_boot_history_cannot_see_a_suspend_and_the_tests_say_so():
    """The documented hole, pinned as a test so it cannot be quietly
    forgotten: a suspend/resume keeps one boot_id and leaves the boot's
    first/last entries straddling it, so this source reports a suspended box
    as continuously up. Suspend is the failure mode round 184 inferred for
    THIS box, so `boot_history` closes the reboot half of the blind spot
    only. If a future round adds a suspend-aware source, this test should be
    the one it has to change."""
    recs = [_rec("2026-08-25T18:00:00Z", "up", 1),
            _rec("2026-08-26T04:00:00Z", "up", 2)]
    # one boot, journal continuous across a hypothetical 20:00-02:00 suspend
    boots = rc.parse_boot_history(json.dumps(json.loads(BOOT_JSON_TWO_BOOTS)[:1]))
    assert rc.gap_continuity(recs, boots)[0]["gaps"][0]["witnessed"] is True


def test_boot_history_witnesses_shrink_the_real_logs_blind_spot():
    """End to end on the real log: a fabricated history covering the
    r142->r154 gap removes exactly that gap from the unwitnessed set and
    drops `max_unobserved_outage_s` to the next-worst gap. The number is
    hypothetical (the box is down and no real history has been read); the
    MECHANISM is what this pins."""
    recs = _real_log_through_round(340)
    before = rc.continuity_report(recs)
    boots = rc.parse_boot_history(json.dumps([
        {"index": 0, "boot_id": "covers-the-blind-spot",
         "first_entry": _usec("2026-08-26T00:00:00Z"),
         "last_entry": _usec("2026-08-26T20:00:00Z")}]))
    after = rc.continuity_report(recs, boots)
    assert before["max_unobserved_outage_human"] == "14h00m00s"
    assert after["max_unobserved_outage_human"] == "8h01m00s"
    assert after["unwitnessed_gap_count"] < before["unwitnessed_gap_count"]
    assert after["witnessed_total_s"] > before["witnessed_total_s"]
    # and the record claim gets a much wider margin as a direct consequence
    st = rc.current_streak_duration(recs, now_fn=lambda: "2026-08-29T17:21:00Z")
    assert st["unobserved_margin_human"] == "1h07m53s"


# --- the probe (not run live; the box is down) ---------------------------

class _FakeProc:
    def __init__(self, returncode=0, stdout=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, ""


def test_boot_history_probe_parses_a_successful_ssh_read():
    seen = []

    def runner(cmd):
        seen.append(cmd)
        return _FakeProc(0, BOOT_JSON_TWO_BOOTS)

    boots = rc.boot_history_probe(runner=runner)
    assert [b["boot_id"] for b in boots] == ["aaa", "bbb"]
    assert seen[0][0] == "ssh"
    assert seen[0][-1] == "journalctl --list-boots -o json"
    # its own ssh call, never bolted onto ssh_probe's strict `== "UP"` check
    assert "echo" not in " ".join(seen[0])


@pytest.mark.parametrize("proc", [
    _FakeProc(255, ""), _FakeProc(1, "denied"), _FakeProc(0, ""),
    _FakeProc(0, "not json"), _FakeProc(0, "[]"),
])
def test_boot_history_probe_returns_empty_on_every_failure_mode(proc):
    assert rc.boot_history_probe(runner=lambda cmd: proc) == []


def test_boot_history_probe_swallows_a_raising_runner():
    def boom(cmd):
        raise subprocess.TimeoutExpired(cmd, 1)
    assert rc.boot_history_probe(runner=boom) == []


def test_cli_continuity_accepts_a_saved_boot_history_file(tmp_path, capsys):
    hist = tmp_path / "boots.json"
    hist.write_text(json.dumps([
        {"index": 0, "boot_id": "covers-the-blind-spot",
         "first_entry": _usec("2026-08-26T00:00:00Z"),
         "last_entry": _usec("2026-08-26T20:00:00Z")}]))
    assert rc.main(["continuity", "--log-path", str(REAL_LOG),
                    "--boot-history", str(hist)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["boot_history_boots"] == 1
    assert out["max_unobserved_outage_human"] != "14h00m00s"


def test_cli_continuity_without_boot_history_reports_zero_boots(capsys):
    assert rc.main(["continuity", "--log-path", str(REAL_LOG)]) == 0
    assert json.loads(capsys.readouterr().out)["boot_history_boots"] == 0


def test_boot_history_that_neither_covers_nor_straddles_the_gap_says_nothing():
    """The third outcome, and the one a mutation run found missing: a gap
    that falls entirely AFTER the last boot's last entry is neither covered
    by a boot nor straddling a boot boundary. The rule must return None and
    hand back to the existing rules -- not witness, and not invent an
    excursion out of a boot boundary that is nowhere near the gap."""
    recs = [_rec("2026-08-27T02:00:00Z", "up", 1),
            _rec("2026-08-27T04:00:00Z", "up", 2)]
    boots = rc.parse_boot_history(BOOT_JSON_TWO_BOOTS)   # boundary is 08-26 06:00-09:00
    streak = rc.gap_continuity(recs, boots)[0]
    assert streak["gaps"][0]["witnessed"] is False
    assert streak["gaps"][0]["witness_source"] is None
    assert streak["missed_excursions"] == []


def test_parse_boot_history_orders_by_time_even_when_index_is_absent():
    """`index` is optional and its numbering convention differs between
    systemd versions (0/-1/-2 newest-first on some, 1..N oldest-first on
    others), so the ordering the witness rules depend on must come from the
    timestamps alone. With `index` absent entirely, an index-keyed sort is a
    no-op and leaves the input order untouched -- which is what this feeds
    it, reversed."""
    rows = [{k: v for k, v in row.items() if k != "index"}
            for row in json.loads(BOOT_JSON_TWO_BOOTS)]
    boots = rc.parse_boot_history(json.dumps(list(reversed(rows))))
    assert [b["first_entry_utc"] for b in boots] == [
        "2026-08-25T12:00:00Z", "2026-08-26T09:00:00Z"]


def test_boot_history_probe_discards_output_from_a_failed_ssh():
    """ssh can exit non-zero having already emitted usable-looking output
    (a partial read, a connection dropped mid-stream). The returncode check
    is what makes that unusable output unused -- and it is only observable
    with a mutant that pairs a bad exit code with GOOD stdout, which is why
    the earlier all-empty-stdout parametrisation could not see it."""
    proc = _FakeProc(255, BOOT_JSON_TWO_BOOTS)
    assert rc.boot_history_probe(runner=lambda cmd: proc) == []
