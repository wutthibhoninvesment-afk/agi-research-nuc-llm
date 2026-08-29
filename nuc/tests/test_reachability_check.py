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
