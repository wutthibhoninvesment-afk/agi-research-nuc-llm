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
from datetime import datetime, timezone
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


def test_streak_bounds_scans_the_whole_streak_and_takes_the_earliest_if_disputed():
    """ROUND 448 REVERSED THIS TEST, deliberately.

    Round 334 wrote it as `..._takes_the_latest_last_seen_across_the_whole_streak`
    and asserted 07:00 -- the tightest of the two readings. That is correct
    while `tailscale_last_seen_utc` is a reliable observation: a later
    sighting means the outage began later. Round 448 measured the field being
    RECOMPUTED across one continuous outage (124 s, and in the earlier
    direction), so two readings in one streak are a contradiction, at most
    one is right, and a bound named EARLIEST POSSIBLE has to hold whichever
    it is. The property round 334 was really protecting -- the WHOLE streak
    is scanned, not just its first record -- is unchanged and still asserted
    here: neither 05:00 nor 07:00 is on the streak's first record.

    The cost is a wider bracket. That is the point: the previous answer was
    narrower than the evidence supports."""
    records = list(BRACKET_RECORDS)
    records[2] = dict(records[2], tailscale_last_seen_utc="2026-08-27T05:00:00Z")
    records[3] = dict(records[3], tailscale_last_seen_utc="2026-08-27T07:00:00Z")
    b = _bounds_by_rounds(records, 3)
    assert b["earliest_possible_start_utc"] == "2026-08-27T05:00:00Z"
    assert b["earliest_possible_start_source"] == "tailscale_last_seen_min_disputed"
    assert b["lastseen_disputed"] == ["2026-08-27T05:00:00Z", "2026-08-27T07:00:00Z"]


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
        # Round 370: `check()` now also asks the box for its own suspend
        # counters. Answer it here so these tests keep exercising the real
        # call sequence rather than a stubbed-out one.
        if argv[-1].startswith("python3 -c"):
            return FakeCompleted(0, stdout=json.dumps(
                {"boottime": 26576.31, "monotonic": 26576.31,
                 "uptime": 26576.31, "success": "0", "fail": "0",
                 "last_failed_dev": "", "last_failed_step": ""}))
        return FakeCompleted(0, stdout="UP\n")

    @property
    def non_suspend_commands(self):
        return [c for c in self.commands if not c.startswith("python3 -c")]


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
    assert runner.non_suspend_commands == ["echo UP", "cat /proc/uptime"]
    # Round 370: the suspend counters ride along on every up check, so
    # "boot_utc unchanged" no longer has to assume anything about which
    # clock /proc/uptime reads.
    assert record["suspend"]["slept_this_boot"] is False
    assert record["suspend"]["suspend_success"] == 0


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
    # that a down box cannot supply anyway. Round 370's suspend probe is
    # gated behind the same `reachable` check for the same reason.
    assert runner.commands == ["echo UP"]
    assert record["suspend"] is None


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
    # ROUND 352: this used to assert `second["ongoing"] is True`, which was a
    # fact about the WORLD (the box was down) written down as a property of
    # the code. It stayed green for nine rounds only because the outage kept
    # going, and went red the moment round 352 found the box up -- i.e. the
    # suite treated "the outage is still running" as an invariant of the
    # thing under test. What the test is actually about is the 3m06s
    # LastSeen-vs-first-check disagreement on the START side, asserted above.
    # `ongoing` is now DERIVED from the log rather than pinned, so this test
    # says the same thing whichever state the box is in.
    # ROUND 406: round 352's derivation above was right for a log with two
    # down streaks and wrong for one with three. `_last["verdict"] == "down"`
    # asks "is the box down NOW", which answers whether the LAST streak is
    # ongoing -- not this one. Round 406 opened a third down streak (406..406,
    # ongoing) and the assertion claimed the CLOSED 298..346 streak was still
    # running. Same defect class round 352 fixed, one level up: the expectation
    # was derived from the log, but from the wrong part of it. A streak is
    # ongoing iff it contains the newest record, which is a statement about the
    # streak and cannot be falsified by a later, unrelated outage.
    _last = sorted(_real_log_records(), key=rc._sort_key)[-1]
    assert second["ongoing"] is (second["end_round"] == _last["round"])
    # Same treatment: `max_possible_span_s is None` was only true BECAUSE the
    # outage was open (an ongoing streak has no end bound to compute one
    # from). The durable statement is the conditional, which holds in both
    # states. The now-closed bracket gets its own dedicated test below.
    if second["ongoing"]:
        assert second["max_possible_span_s"] is None
    else:
        assert second["max_possible_span_s"] >= second["confirmed_span_s"]


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
    # ROUND 454: `end_round` moved 286 -> 292 because round 292 -- an E round
    # that probed the box twice, found it up, and then died without writing
    # anything -- was recovered from its own transcript and is now the last
    # record of this streak. The streak did not change; the log's knowledge
    # of it did.
    up = [b for b in rc.streak_bounds(_real_log_records()) if b["verdict"] == "up"][1]
    assert (up["start_round"], up["end_round"]) == (202, 292)
    assert up["earliest_possible_start_utc"] == "2026-08-27T11:50:48Z"
    assert up["earliest_possible_start_source"] == "boot_utc"
    # ROUND 454: 32h23m22s -> 34h27m37s, i.e. +7455 s exactly. The streak's
    # confirmed span now runs to round 292's check instead of round 286's,
    # and 7455 s is the interval between those two checks. Same number, same
    # cause, as the +7455 s in `test_real_log_two_thirds_of_the_span_is_
    # unwitnessed` -- one recovered observation extending one streak.
    assert up["confirmed_span_human"] == "34h27m37s"
    assert up["max_possible_span_human"] == "38h22m19s"


# ==========================================================================
# Round 340: gap continuity -- is a streak we report as unbroken actually
# unbroken? `summarize_log`'s n_streaks is a LOWER bound on the number of
# state transitions in exactly the way round 334 showed `confirmed_span_s`
# is a lower bound on duration.
# ==========================================================================

def _rec(ts, verdict, rnd=None, last_seen=None, boot=None, precision=None,
         last_seen_bounds=None):
    # `precision` is deliberately absent by default: the bulk of this suite
    # then exercises round 460's fail-closed path, where a record that does
    # not say how precise it is gets the WIDEST bracket. Tests that care pass
    # it explicitly.
    r = {"checked_at_utc": ts, "verdict": verdict, "round": rnd}
    if precision is not None:
        r["precision"] = precision
    if last_seen_bounds is not None:
        r["tailscale_last_seen_bounds_utc"] = list(last_seen_bounds)
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


def test_last_seen_after_the_later_down_check_is_contradictory_not_a_witness():
    """Mirrors round 334's `streak_bounds` rule: a LastSeen at/after a check
    that called the box down implies more transitions than one gap can
    represent. Dropped with a named reason, never clamped into a witness.

    Round 460 sharpened "at or after" to "after, by more than the later
    check's own declared resolution". A `precise` row's `checked_at_utc` is a
    truncated `now()`, so the true check happened somewhere in [t2, t2+1);
    a sighting AT t2 is therefore at-or-BEFORE the true check and proves no
    contradiction at all. See the straddle test below for that case."""
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1, precision="precise"),
            _rec("2026-01-01T14:00:00Z", "down", 2, precision="precise",
                 last_seen="2026-01-01T14:05:00Z")]
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
    # ROUND 454: the second streak's worst blind spot fell 8h01m00s ->
    # 3h07m22s. That is the recovery paying for itself: rounds 220, 226, 250
    # and 280 all landed INSIDE this streak, splitting its longest gaps. The
    # first streak is unmoved at 14h00m00s because no round was recovered
    # inside it -- round 190 is a `down` round, and it landed in the 184/196
    # outage instead.
    assert [s["max_unwitnessed_gap_human"] for s in ups] == ["14h00m00s", "3h07m22s"]


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
    # Against the live log the bound can grow (a new up gap could be worse).
    # A future round that finds this number has gone UP has found a new worst
    # blind spot and owes the `definitely_longest_including_unobserved` claim
    # a re-check.
    #
    # ROUND 454 struck the parenthetical that used to say "an old one cannot
    # shrink". An old gap shrinks the moment an observation is recovered
    # INSIDE it, and round 454 recovered four such observations: the second
    # up streak's worst gap went 8h01m00s -> 3h07m22s in the test above. The
    # assertion below still holds only because none of the recovered rounds
    # fell inside the r142->r154 window, which is luck, not an invariant.
    live = rc.continuity_report(_real_log_records())
    assert live["max_unobserved_outage_s"] >= 50400.0


def test_real_log_two_thirds_of_the_span_is_unwitnessed():
    # ROUND 454: 29 -> 35 gaps, because six recovered rounds (190, 220, 226,
    # 250, 280, 292) fall at or below round 340 and each one splits a gap in
    # two. The unwitnessed total moved 67h26m22s -> 69h30m37s, and the whole
    # of that +7455 s is ONE new gap, r286->r292: round 292 extends the up
    # streak past where the log used to end, so that interval is genuinely
    # new interior time rather than ignorance the recovery invented. The
    # five INTERIOR insertions contribute zero between them -- they split
    # gaps that were already unwitnessed in full, and round 190's half keeps
    # its witness through the forward-LastSeen rule this round added. That
    # zero is the point, and `test_inserting_an_interior_check_never_
    # increases_unobserved_total` states it directly.
    rep = rc.continuity_report(_real_log_through_round(340))
    assert rep["n_gaps"] == 35
    assert (rep["witnessed_gap_count"], rep["unwitnessed_gap_count"]) == (12, 23)
    assert rep["unwitnessed_total_human"] == "69h30m37s"
    assert 0.68 < rep["unwitnessed_fraction"] < 0.72


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
    # ROUND 352: was `== ["up", "up"]`. Pinning the COUNT of up streaks made
    # this test fail every time the box changes state, which is the one event
    # it has no opinion about -- its subject is that `--verdict up` filters
    # and `--gaps` adds per-gap detail. Both are asserted structurally now.
    verdicts = [s["verdict"] for s in out["streaks"]]
    assert verdicts and set(verdicts) == {"up"}
    assert all("gaps" in s for s in out["streaks"])
    # the rollup counts stay whole-log even when the streak list is filtered
    assert out["n_gaps"] >= 29


def test_cli_continuity_verdict_filter_without_gaps_flag(capsys):
    """ROUND 382: was `== ["down", "down"]`. Round 352 removed exactly this
    pin from the `--verdict up` test one function above -- "pinning the COUNT
    of up streaks made this test fail every time the box changes state, which
    is the one event it has no opinion about" -- and left the `down` twin
    untouched. The subject here is that `--verdict down` filters and that
    omitting `--gaps` withholds per-gap detail; the number of down streaks in
    an append-only log is not part of it. Fixed structurally, like its twin,
    before the next outage makes it three.
    """
    assert rc.main(["continuity", "--log-path", str(REAL_LOG),
                    "--verdict", "down"]) == 0
    out = json.loads(capsys.readouterr().out)
    verdicts = [s["verdict"] for s in out["streaks"]]
    assert verdicts and set(verdicts) == {"down"}
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


def test_boot_history_endpoint_coverage_is_reboot_only_not_full():
    """ROUND 358, replacing round 340's
    `test_boot_history_witnesses_an_up_gap_no_probe_rule_can_reach`.

    That test asserted `witnessed is True` for endpoint coverage. Round 352
    ran it on the real box and the consequence was
    `unwitnessed 0h00m00s` / `max_unobserved_outage: None` for a log full of
    multi-hour unprobed gaps -- i.e. the code claimed to have ruled out
    suspend, the one failure mode round 184 inferred for this box. Endpoint
    coverage rules out a REBOOT and nothing else, exactly like
    `boot_utc unchanged`, so it now returns the same strength."""
    recs = [_rec("2026-08-25T18:00:00Z", "up", 1),
            _rec("2026-08-26T04:00:00Z", "up", 2)]
    boots = rc.parse_boot_history(BOOT_JSON_TWO_BOOTS)
    assert rc.gap_continuity(recs)[0]["gaps"][0]["witnessed"] is False
    gap = rc.gap_continuity(recs, boots)[0]["gaps"][0]
    assert gap["witness_strength"] == rc.WITNESS_REBOOT_ONLY
    assert gap["witnessed"] is False
    assert gap["witness_source"] == "boot_history"
    assert "aaa" in gap["witness_note"]
    assert "suspend" in gap["witness_note"]
    # and the whole-log claim it used to license is withdrawn
    rep = rc.continuity_report(recs, boots)
    assert rep["all_streaks_confirmed_continuous"] is False
    assert rep["max_unobserved_outage_human"] == "10h00m00s"


def _journal(*iso_stamps):
    """A capture covering 2026-08-25 -> 08-27 with entries at the given
    instants. Whole seconds, as `parse_journal_seconds` produces them."""
    return {"covers_from_utc": "2026-08-25T00:00:00Z",
            "covers_to_utc": "2026-08-27T00:00:00Z",
            "seconds": sorted(int(rc._parse_ts(s).timestamp()) for s in iso_stamps)}


def test_journal_interior_upgrades_reboot_only_to_a_measured_bound():
    """ROUND 358, the fix round 352 §8 item 2 asked for. Endpoint coverage
    plus the journal's INTERIOR turns a boolean into a number: entries every
    two hours across a ten-hour gap mean no excursion longer than ~2 h could
    have hidden in it."""
    recs = [_rec("2026-08-25T18:00:00Z", "up", 1),
            _rec("2026-08-26T04:00:00Z", "up", 2)]
    boots = rc.parse_boot_history(BOOT_JSON_TWO_BOOTS)
    cap = _journal("2026-08-25T20:00:00Z", "2026-08-25T22:00:00Z",
                   "2026-08-26T00:00:00Z", "2026-08-26T02:00:00Z")
    gap = rc.gap_continuity(recs, boots, rc.make_silence_fn(cap))[0]["gaps"][0]
    assert gap["witness_strength"] == rc.WITNESS_BOUNDED
    assert gap["witness_source"] == "boot_history+journal"
    # 2 h between adjacent entries, +1 s for the whole-second truncation
    assert gap["bound_s"] == 7201.0
    assert gap["unobserved_s"] == 7201.0
    assert gap["interior_silence"]["n_entry_seconds"] == 4
    # still NOT "witnessed": a bound is not a refutation
    assert gap["witnessed"] is False
    assert "at most" in gap["witness_note"]


def test_bounded_gap_shrinks_max_unobserved_outage_below_the_gap_length():
    """The payoff, and the reason `_worst` ranks by `unobserved_s`: a 10 h
    gap that can only hide 2 h must not out-rank a 3 h gap that can hide all
    3 h."""
    recs = [_rec("2026-08-25T18:00:00Z", "up", 1),
            _rec("2026-08-26T04:00:00Z", "up", 2)]
    boots = rc.parse_boot_history(BOOT_JSON_TWO_BOOTS)
    cap = _journal("2026-08-25T20:00:00Z", "2026-08-25T22:00:00Z",
                   "2026-08-26T00:00:00Z", "2026-08-26T02:00:00Z")
    plain = rc.continuity_report(recs, boots)
    bounded = rc.continuity_report(recs, boots, rc.make_silence_fn(cap))
    assert plain["max_unobserved_outage_s"] == 36000.0
    assert bounded["max_unobserved_outage_s"] == 7201.0
    assert bounded["bounded_gap_count"] == 1
    assert bounded["max_unobserved_outage_strength"] == rc.WITNESS_BOUNDED
    # the boolean bucket is untouched: a bounded gap is still unwitnessed,
    # so the witnessed/unwitnessed partition of the log span still holds
    assert bounded["unwitnessed_total_s"] == plain["unwitnessed_total_s"]


def test_journal_interior_bounds_a_gap_with_no_boot_history_at_all():
    """ROUND 358, second cut. The first cut gated the bound behind
    boot-history endpoint coverage and scored `bounded_gap_count: 0` on the
    live log: the round-352 boot history's `last_entry` predates round 358's
    own check, so the ONE gap with a fresh interior capture was not covered
    by it. A journal entry proves the box was awake at that instant no
    matter what any boot record says, so the upgrade is keyed on the
    STRENGTH (reboot_only) and not on which rule produced it."""
    recs = [_rec("2026-08-25T18:00:00Z", "up", 1, boot="2026-08-25T12:00:00Z"),
            _rec("2026-08-26T04:00:00Z", "up", 2, boot="2026-08-25T12:00:00Z")]
    cap = _journal("2026-08-25T21:00:00Z", "2026-08-26T01:00:00Z")
    gap = rc.gap_continuity(recs, None, rc.make_silence_fn(cap))[0]["gaps"][0]
    assert gap["witness_strength"] == rc.WITNESS_BOUNDED
    assert gap["witness_source"] == "boot_utc_unchanged+journal"
    assert gap["bound_s"] == 4 * 3600 + 1     # 21:00 -> 01:00, plus truncation


def test_silence_never_upgrades_a_proven_excursion_or_a_full_witness():
    """`_silence_upgrade` may only strengthen reboot_only. A gap where the
    boot history PROVED an outage must keep saying so -- a bound computed
    from entries on either side of a real power-off would read as
    reassurance about a gap we have positive evidence about."""
    recs = [_rec("2026-08-26T05:00:00Z", "up", 1),
            _rec("2026-08-26T12:00:00Z", "up", 2)]
    boots = rc.parse_boot_history(BOOT_JSON_TWO_BOOTS)   # boundary 06:00-09:00
    cap = {"covers_from_utc": "2026-08-26T00:00:00Z",
           "covers_to_utc": "2026-08-26T23:00:00Z",
           "seconds": [int(rc._parse_ts("2026-08-26T05:30:00Z").timestamp())]}
    gap = rc.gap_continuity(recs, boots, rc.make_silence_fn(cap))[0]["gaps"][0]
    assert gap["witness_strength"] == rc.WITNESS_NONE
    assert rc.gap_continuity(recs, boots, rc.make_silence_fn(cap))[0]["missed_excursions"]
    assert gap["bound_s"] is None

    # and a down gap, where LastSeen already gives a genuine FULL witness
    down = [_rec("2026-08-26T05:00:00Z", "down", 1, last_seen="2026-08-26T04:00:00Z"),
            _rec("2026-08-26T12:00:00Z", "down", 2, last_seen="2026-08-26T04:00:00Z")]
    dgap = rc.gap_continuity(down, boots, rc.make_silence_fn(cap))[0]["gaps"][0]
    assert dgap["witness_strength"] == rc.WITNESS_FULL
    assert dgap["unobserved_s"] == 0.0


def test_bound_is_never_zero_because_a_short_excursion_always_fits():
    """The honest ceiling of the method, pinned. Even an entry every single
    second leaves a >=1 s bound, so this source can never return FULL and no
    future round should be tempted to make it."""
    recs = [_rec("2026-08-25T18:00:00Z", "up", 1),
            _rec("2026-08-25T18:00:05Z", "up", 2)]
    boots = rc.parse_boot_history(BOOT_JSON_TWO_BOOTS)
    cap = _journal(*["2026-08-25T18:00:0%dZ" % i for i in range(6)])
    gap = rc.gap_continuity(recs, boots, rc.make_silence_fn(cap))[0]["gaps"][0]
    assert gap["witness_strength"] == rc.WITNESS_BOUNDED
    assert 0 < gap["bound_s"] <= gap["gap_s"]


def test_interior_silence_refuses_a_window_that_does_not_cover_the_gap():
    """Partial coverage is not coverage -- the same rule the boot-history
    endpoint test already pins, one level down. Silence before the capture
    window began is indistinguishable from real silence, and reporting the
    second as the first is the exact overstatement this whole change
    removes."""
    t1, t2 = rc._parse_ts("2026-08-25T18:00:00Z"), rc._parse_ts("2026-08-26T04:00:00Z")
    secs = [int(rc._parse_ts("2026-08-25T20:00:00Z").timestamp())]
    assert rc.interior_silence(t1, t2, secs, "2026-08-25T19:00:00Z",
                               "2026-08-27T00:00:00Z") is None   # starts too late
    assert rc.interior_silence(t1, t2, secs, "2026-08-25T00:00:00Z",
                               "2026-08-26T03:00:00Z") is None   # ends too early
    assert rc.interior_silence(t1, t2, secs, None, None) is None
    assert rc.interior_silence(t1, t2, secs, "2026-08-25T00:00:00Z",
                               "2026-08-27T00:00:00Z") is not None


def test_interior_silence_bounds_the_edges_not_just_the_middle():
    """A gap whose only entry is one second after t1 is still wide open
    afterwards. Counting only entry-to-entry intervals would report ~0 and
    miss the whole excursion."""
    t1, t2 = rc._parse_ts("2026-08-25T18:00:00Z"), rc._parse_ts("2026-08-26T04:00:00Z")
    secs = [int(rc._parse_ts("2026-08-25T18:00:01Z").timestamp())]
    sil = rc.interior_silence(t1, t2, secs, "2026-08-25T00:00:00Z", "2026-08-27T00:00:00Z")
    # marker lo = 18:00:01 (earliest liveness), t2 is exact => 36000 - 1
    assert sil["max_silence_s"] == pytest.approx(35999.0)
    assert sil["silence_from_utc"] == "2026-08-25T18:00:01Z"


def test_empty_journal_capture_degrades_to_reboot_only_never_to_a_bound():
    """Fail-closed, the same discipline as `boot_history_probe`: a capture
    that came back empty (ssh failed, journal rotated, Storage=volatile)
    must leave the witness where it was, not produce a bound of "the whole
    gap" that reads like a measurement."""
    recs = [_rec("2026-08-25T18:00:00Z", "up", 1),
            _rec("2026-08-26T04:00:00Z", "up", 2)]
    boots = rc.parse_boot_history(BOOT_JSON_TWO_BOOTS)
    for cap in (None, {}, {"covers_from_utc": "a", "covers_to_utc": "b", "seconds": []}):
        fn = rc.make_silence_fn(cap)
        gap = rc.gap_continuity(recs, boots, fn)[0]["gaps"][0]
        assert gap["witness_strength"] == rc.WITNESS_REBOOT_ONLY
        assert gap["bound_s"] is None


def test_parse_journal_seconds_sorts_dedups_and_drops_junk():
    text = "1788000100\n1788000100\n1788000050\n\nnot-a-number\n-5\n0\n1788000200\n"
    assert rc.parse_journal_seconds(text) == [1788000050, 1788000100, 1788000200]
    assert rc.parse_journal_seconds("") == []
    assert rc.parse_journal_seconds(None) == []


def test_journal_seconds_probe_returns_empty_on_every_failure_mode():
    for proc in (_FakeProc(255, ""), _FakeProc(1, "denied"), _FakeProc(0, ""),
                 _FakeProc(0, "junk")):
        assert rc.journal_seconds_probe("2026-08-25T00:00:00Z",
                                        "2026-08-26T00:00:00Z",
                                        runner=lambda cmd: proc) == []

    def boom(cmd):
        raise subprocess.TimeoutExpired(cmd, 1)
    assert rc.journal_seconds_probe("2026-08-25T00:00:00Z", "2026-08-26T00:00:00Z",
                                    runner=boom) == []
    # inverted window and unparseable timestamps refuse BEFORE any ssh
    called = []
    assert rc.journal_seconds_probe("2026-08-26T00:00:00Z", "2026-08-25T00:00:00Z",
                                    runner=lambda cmd: called.append(cmd)) == []
    assert rc.journal_seconds_probe("nonsense", "2026-08-25T00:00:00Z",
                                    runner=lambda cmd: called.append(cmd)) == []
    assert called == []


def test_journal_seconds_probe_reduces_on_the_box_not_over_the_wire():
    """The payload discipline: the dedup-to-whole-seconds awk runs remotely,
    so a day of ~50k journal entries crosses the wire as ~1.9k short lines.
    If a future edit moves that reduction local, this test is the tripwire."""
    seen = []

    def runner(cmd):
        seen.append(cmd)
        return _FakeProc(0, "1788000050\n1788000100\n")

    out = rc.journal_seconds_probe("2026-08-25T00:00:00Z", "2026-08-26T00:00:00Z",
                                   runner=runner)
    assert out == [1788000050, 1788000100]
    remote = seen[0][-1]
    assert remote.startswith("journalctl --since @")
    assert "awk" in remote and "short-unix" in remote
    assert seen[0][0] == "ssh"


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


def test_boot_history_beats_boot_utc_only_once_it_has_the_interior():
    """ROUND 358 rewrite. Round 340 asserted boot_history beat `boot_utc`
    outright. It does not: both rule out a reboot and neither sees a
    suspend, so on endpoint coverage alone the two sources TIE at
    reboot_only, and boot_history's advantage is only realised when the
    journal interior is supplied. Consulting it first still matters (it can
    also PROVE an excursion, which `boot_utc` cannot on a same-boot gap),
    which is why the source name changes even when the strength does not."""
    recs = [_rec("2026-08-25T18:00:00Z", "up", 1, boot="2026-08-25T12:00:00Z"),
            _rec("2026-08-26T04:00:00Z", "up", 2, boot="2026-08-25T12:00:00Z")]
    boots = rc.parse_boot_history(BOOT_JSON_TWO_BOOTS)
    from_boot_utc = rc.gap_continuity(recs)[0]["gaps"][0]
    from_history = rc.gap_continuity(recs, boots)[0]["gaps"][0]
    assert from_boot_utc["witness_strength"] == rc.WITNESS_REBOOT_ONLY
    assert from_history["witness_strength"] == rc.WITNESS_REBOOT_ONLY
    assert from_boot_utc["witness_source"] == "boot_utc_unchanged"
    assert from_history["witness_source"] == "boot_history"

    cap = _journal("2026-08-25T20:00:00Z", "2026-08-26T02:00:00Z")
    upgraded = rc.gap_continuity(recs, boots, rc.make_silence_fn(cap))[0]["gaps"][0]
    assert upgraded["witness_strength"] == rc.WITNESS_BOUNDED


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
    # one boot, journal endpoints straddling a hypothetical 20:00-02:00 suspend
    boots = rc.parse_boot_history(json.dumps(json.loads(BOOT_JSON_TWO_BOOTS)[:1]))
    gap = rc.gap_continuity(recs, boots)[0]["gaps"][0]
    # ROUND 358: round 340 asserted `witnessed is True` HERE, in the very
    # test whose docstring says the source cannot see a suspend. That
    # contradiction is the bug this round fixed; the strength now matches
    # the docstring.
    assert gap["witnessed"] is False
    assert gap["witness_strength"] == rc.WITNESS_REBOOT_ONLY

    # With the journal interior, the suspend is still not DETECTED -- it is
    # bounded. Entries at 20:00 and 02:00 leave a 6 h silence, so a 6 h
    # suspend still fits and the bound says so out loud.
    cap = _journal("2026-08-25T20:00:00Z", "2026-08-26T02:00:00Z")
    bounded = rc.gap_continuity(recs, boots, rc.make_silence_fn(cap))[0]["gaps"][0]
    assert bounded["witness_strength"] == rc.WITNESS_BOUNDED
    assert bounded["bound_s"] == 6 * 3600 + 1
    assert bounded["witnessed"] is False


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
    # ROUND 358: the boot history ALONE no longer shrinks this -- endpoint
    # coverage is reboot_only, so the 14 h gap still admits a 14 h suspend.
    assert after["max_unobserved_outage_human"] == "14h00m00s"
    assert after["unwitnessed_gap_count"] == before["unwitnessed_gap_count"]

    # What DOES shrink it is the journal interior. One entry every 10 min
    # across the covered window caps the hideable excursion at ~10 min.
    t0 = rc._parse_ts("2026-08-26T00:00:00Z").timestamp()
    cap = {"covers_from_utc": "2026-08-25T00:00:00Z",
           "covers_to_utc": "2026-08-27T00:00:00Z",
           "seconds": [int(t0 + 600 * i) for i in range(121)]}
    bounded = rc.continuity_report(recs, boots, rc.make_silence_fn(cap))
    assert bounded["max_unobserved_outage_human"] != "14h00m00s"
    assert bounded["bounded_gap_count"] >= 1
    assert bounded["max_unobserved_outage_s"] < before["max_unobserved_outage_s"]


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
    """ROUND 382: this test is the QUIET half of the window-pin class its
    neighbour exhibited loudly. Its boot history was pinned to
    2026-08-26T00:00:00Z..20:00:00Z, chosen when the log ended near there;
    the log has since grown four days past it, so the fixture covered a
    shrinking prefix while the test stayed green -- it asserted only
    `boot_history_boots == 1` and `journal_seconds_loaded == 0`, neither of
    which depends on coverage at all. A window pin fails loudly when an
    assertion depends on it and goes silently VACUOUS when none does; both
    are the same defect, and only the loud one announces itself.

    Fixed twice over: the window now spans the live log, and the round-358
    claim in the old comment -- boot history alone is `reboot_only`, so the
    headline does not move -- is now ASSERTED rather than narrated.
    """
    boots, _capture, _n, _step = _covers_the_whole_live_log()
    hist = tmp_path / "boots.json"
    hist.write_text(json.dumps(boots))
    assert rc.main(["continuity", "--log-path", str(REAL_LOG),
                    "--boot-history", str(hist)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["boot_history_boots"] == 1
    assert out["journal_seconds_loaded"] == 0

    # ROUND 358, now asserted: boot history alone is reboot_only, so the
    # headline number does NOT move -- it only gains a source. The
    # `--journal-seconds` case below is what moves it.
    plain = rc.continuity_report(rc.load_log(str(REAL_LOG)))
    assert out["max_unobserved_outage_s"] == plain["max_unobserved_outage_s"]
    assert out["unobserved_total_s"] == plain["unobserved_total_s"]
    assert out["bounded_gap_count"] == plain["bounded_gap_count"] == 0
    assert plain["max_unobserved_outage_strength"] == rc.WITNESS_NONE
    assert out["max_unobserved_outage_strength"] == rc.WITNESS_REBOOT_ONLY


def _covers_the_whole_live_log(margin_s=3600, step_s=300):
    """Synthetic (boot_history, journal_seconds) fixtures sized from the LIVE
    log rather than from absolute dates.

    ROUND 382. The fixtures below used to hard-code
    `2026-08-25T00:00:00Z .. 2026-08-31T00:00:00Z`, chosen in round 358 to
    span the log as it stood then. `state/nuc-reachability-log.jsonl` is
    append-only, so wall-clock walked out of that window: round 382's own
    first-contact record landed at 2026-08-31T00:05:32Z, **5m32s past
    `covers_to_utc`**, the newest gap stopped being covered by the capture,
    and `max_unobserved_outage_s` became that entire gap -- 15108.0 against
    an asserted ceiling of 301.0.

    This is round 340's "live-file aggregate pin" hazard in a shape its
    next-steps item 4 did not name: not a pinned COUNT over a growing file,
    but a pinned absolute TIME WINDOW that a growing file leaves behind. A
    count pin fails loudly the round after the file grows; a window pin sits
    green for as long as the window has runway and then fails on a date
    nobody chose, for a reason that reads like an instrument regression.
    Derive the window from the data instead.
    """
    ROUND_454 = """The window is now min/max over the whole log, not
    recs[0]/recs[-1]. `load_log` returns FILE order and promises nothing
    else; every real consumer in the module sorts through `_sort_key`
    first, and this helper was the one place that did not. Round 454
    recovered eight missing rows and appended them, so the file stopped
    being chronological -- `recs[-1]` became round 292's 2026-08-28 record
    and the derived window ended four days before the log did. The symptom
    was `max_unobserved_outage_s` 20536.0 against a ceiling of 301, i.e.
    exactly the expired-window failure the test below exists to describe,
    arriving from a direction round 382 did not consider: not the clock
    walking past a fixed window, but an append landing out of order."""
    recs = rc.load_log(str(REAL_LOG))
    stamps = [rc._parse_ts(r["checked_at_utc"]).timestamp() for r in recs]
    lo = min(stamps) - margin_s
    hi = max(stamps) + margin_s
    lo_iso = rc._fmt_ts(datetime.fromtimestamp(lo, timezone.utc))
    hi_iso = rc._fmt_ts(datetime.fromtimestamp(hi, timezone.utc))
    n = int((hi - lo) // step_s) + 1
    boots = [{"index": 0, "boot_id": "covers-everything",
              "first_entry": int(lo) * 1_000_000,
              "last_entry": int(hi) * 1_000_000}]
    capture = {"covers_from_utc": lo_iso, "covers_to_utc": hi_iso,
               "seconds": [int(lo + step_s * i) for i in range(n)]}
    return boots, capture, n, step_s


def test_cli_continuity_accepts_a_journal_seconds_capture(tmp_path, capsys):
    """ROUND 358: the CLI half of the fix. Same log, same boot history, plus
    a journal-interior capture -> the headline number stops being the whole
    gap and becomes the measured silence.

    ROUND 382: window derived from the log, see `_covers_the_whole_live_log`.
    """
    boots, capture, n, step_s = _covers_the_whole_live_log()
    hist = tmp_path / "boots.json"
    hist.write_text(json.dumps(boots))
    cap = tmp_path / "journal.json"
    cap.write_text(json.dumps(capture))
    assert rc.main(["continuity", "--log-path", str(REAL_LOG),
                    "--boot-history", str(hist),
                    "--journal-seconds", str(cap)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["journal_seconds_loaded"] == n
    assert out["bounded_gap_count"] > 0
    # entries every `step_s`, so the largest interior silence is `step_s`
    assert out["max_unobserved_outage_s"] <= step_s + 1


def test_a_capture_window_that_ends_before_the_log_does_loses_the_bound():
    """ROUND 382, the regression witness for the bug above -- the failure the
    expired fixture was ACTUALLY exhibiting, pinned deliberately instead of
    incidentally.

    Truncating the capture so it stops before the newest record does not
    merely weaken the bound a little: the final gap reverts to its own full
    length, which on a log whose newest gap is hours long dwarfs every
    interior silence. Round 364 proved a coverage hole "can only decline to
    help"; this pins the size of that declining, which is what makes an
    expired window look like an instrument regression rather than a fixture
    running out of runway.
    """
    boots, capture, _n, step_s = _covers_the_whole_live_log()
    recs = rc.load_log(str(REAL_LOG))
    boot_objs = rc.parse_boot_history(json.dumps(boots))

    full = rc.continuity_report(recs, boot_objs,
                                silence=rc.make_silence_fn(capture))
    assert full["max_unobserved_outage_s"] <= step_s + 1

    # ROUND 406: this used to stop one second before the NEWEST record and
    # assert that the newest gap reverted to full length. That silently assumed
    # the newest record is `up`. `max_unobserved_outage_s` is by definition the
    # worst unwitnessed gap INSIDE AN UP STREAK (`_worst(lambda v: v == "up")`)
    # -- a gap that ends in a `down` check is a transition, and an outage
    # cannot hide in it because the outage is exactly what the check found. So
    # when round 406's down record arrived, the final gap stopped being
    # eligible and the assertion compared 301.0 against the whole 4h42m
    # up->down transition. The fixture pinned a fact about the world again,
    # one layer below where round 382 fixed it: not an absolute window this
    # time, but the assumption that the log ends in an up streak.
    #
    # ROUND 424: and it pinned one MORE, a layer below round 406's. Round 406
    # stopped assuming the log ends in an `up` record and went looking for the
    # newest one -- but then walked back to the start of ITS streak and
    # required that streak to be at least two records long. Round 424 found
    # the box up after rounds 406/412/418 all found it down, so the newest up
    # streak is exactly ONE record and has no interior gap at all. The metric
    # is fine; the fixture had no gap to point at.
    #
    # The quantity actually wanted is "the newest gap `max_unobserved_outage_s`
    # can see", i.e. the newest adjacent up->up pair. Asking for that directly
    # needs no streak-length assumption and cannot be broken by the shape of
    # the log's tail -- only by there being no up->up pair anywhere, which is
    # the genuine precondition and is what the message now says.
    eligible = [i for i in range(1, len(recs))
                if recs[i]["verdict"] == "up" and recs[i - 1]["verdict"] == "up"]
    assert eligible, "need at least one adjacent up->up pair in the live log"
    last_up = max(eligible)
    start_of_gap, end_of_gap = recs[last_up - 1], recs[last_up]

    cutoff = rc._parse_ts(end_of_gap["checked_at_utc"]).timestamp() - 1
    truncated = dict(capture,
                     covers_to_utc=rc._fmt_ts(
                         datetime.fromtimestamp(cutoff, timezone.utc)),
                     seconds=[s for s in capture["seconds"] if s <= cutoff])
    lost = rc.continuity_report(recs, boot_objs,
                                silence=rc.make_silence_fn(truncated))

    last_gap_s = (rc._parse_ts(end_of_gap["checked_at_utc"])
                  - rc._parse_ts(start_of_gap["checked_at_utc"])).total_seconds()
    assert lost["max_unobserved_outage_s"] >= last_gap_s
    assert lost["max_unobserved_outage_s"] > full["max_unobserved_outage_s"]


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


def test_real_log_second_outage_is_closed_and_its_end_came_from_boot_utc():
    """ROUND 352 -- the first up-check in nine rounds closed the 298->346
    outage, so its END bracket is pinnable for the first time.

    Its value is that ground truth arrived independently: the box's own
    `journalctl --list-boots` (saved at
    `state/nuc-boot-history-r352/list-boots-r352.json`) puts the previous
    boot's last journal entry at 2026-08-29T02:10:07Z and this boot's first
    at 2026-08-30T00:32:32Z. So the true outage is ~80545s, and the
    `max_possible_span_s` asserted here is within a couple of seconds of it
    while `confirmed_span_s` -- the probe-based number this track quoted for
    nine rounds -- is 9859s (2h44m19s) SHORT. That gap is the whole argument
    for `streak_bounds` publishing a bracket instead of a single figure.
    """
    bounds = [b for b in rc.streak_bounds(_real_log_records())
              if b["verdict"] == "down"]
    second = bounds[1]
    assert second["ongoing"] is False
    assert second["latest_possible_end_utc"] == "2026-08-30T00:32:27Z"
    assert second["latest_possible_end_source"] == "boot_utc"
    assert second["confirmed_span_s"] == pytest.approx(70686.0)
    assert second["max_possible_span_s"] == pytest.approx(80546.9)
    # The bracket must actually CONTAIN the journal-derived truth.
    assert second["confirmed_span_s"] <= 80545.0 <= second["max_possible_span_s"]


def test_boot_history_witness_closes_every_up_gap_the_probes_could_not():
    """ROUND 352 -- first live exercise of round 340's boot-history witness,
    against the box's real `journalctl --list-boots` output.
    **REWRITTEN BY ROUND 358.**

    Round 352 ran this and reported that all 18 up-streak gaps became FULL
    witnesses, `unwitnessed 0h00m00s`, `max_unobserved_outage: None`. Round
    358 established that claim was unearned: endpoint coverage rules out a
    reboot and cannot see a suspend, which is this box's own inferred
    failure mode. So the WITH-history column now says reboot_only, and the
    headline numbers come back.

    Two brittleness fixes while rewriting: the gap counts are no longer
    hardcoded (the real log grows every E-round -- round 358 alone took 18
    up gaps to 19), and the `sources` set now also allows the boot_utc rule,
    which newer records with a `boot_utc` field can legitimately reach.
    """
    records = _real_log_records()
    boots = rc.parse_boot_history(
        (Path(__file__).resolve().parents[2] / "state" / "nuc-boot-history-r352"
         / "list-boots-r352.json").read_text())
    assert len(boots) == 7

    without = rc.continuity_report(records)
    with_bh = rc.continuity_report(records, boots)

    assert without["unwitnessed_gap_count"] >= 18
    assert without["max_unobserved_outage_s"] is not None
    assert without["transition_count_upper_bound"] is None

    # The correction: the boot history alone changes NOTHING about how much
    # could be hiding. It only renames the source and rules out a reboot.
    assert with_bh["unwitnessed_gap_count"] == without["unwitnessed_gap_count"]
    assert with_bh["max_unobserved_outage_s"] == without["max_unobserved_outage_s"]
    assert with_bh["transition_count_upper_bound"] is None
    assert with_bh["missed_excursions"] == []

    up_gaps = [g for st in rc.gap_continuity(sorted(records, key=rc._sort_key), boots)
               if st["verdict"] == "up" for g in st["gaps"]]
    assert {g["witness_source"] for g in up_gaps} <= {"boot_history", "boot_utc_unchanged"}
    assert all(g["witness_strength"] == rc.WITNESS_REBOOT_ONLY for g in up_gaps)
    # what the history DOES still buy, and it is not nothing: every up gap
    # now has a reboot ruled out by a continuous record, including the ones
    # whose endpoints predate the `boot_utc` field entirely.
    assert sum(1 for g in up_gaps if g["witness_source"] == "boot_history") >= 18


# --- round 358: the one-shot backfill must be one-shot in CODE, not in prose

def test_backfill_refuses_unknown_args_and_is_idempotent(tmp_path, capsys, monkeypatch):
    """Round 310's `reachability_backfill.py` docstring said "re-running it
    would duplicate every row" and nothing enforced it. Round 358 duplicated
    all 24 rows by typing `--help`, which the script did not parse: it fell
    through to the append loop. Same shape as round 356's unenforced
    documented rule, one file over.

    Both guards are pinned, because they fail differently: the argv guard
    protects an EMPTY log (where the dedup guard would happily proceed), and
    the dedup guard protects a bare re-run (which passes the argv guard)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "reachability_backfill",
        Path(__file__).resolve().parents[1] / "reachability_backfill.py")
    bf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bf)

    log = tmp_path / "log.jsonl"
    monkeypatch.setattr(bf, "LOG_PATH", str(log))

    # argv guard, on an EMPTY log: writes nothing, exits non-zero
    assert bf.main(["--help"]) == 2
    assert not log.exists()
    assert bf.main(["--boot-history", "x"]) == 2
    assert not log.exists()

    # the real run seeds it
    assert bf.main([]) == 0
    first = log.read_text().splitlines()
    assert len(first) == len(bf.RECORDS)

    # dedup guard: bare re-runs and dry runs are no-ops, byte for byte
    assert bf.main([]) == 0
    assert bf.main(["--dry-run"]) == 0
    assert log.read_text().splitlines() == first


def test_cli_journal_seconds_never_writes_an_empty_capture(tmp_path, capsys, monkeypatch):
    """Round 358: the first wide capture failed on a client-side timeout and
    `journal_seconds_probe` returned [] -- correct, fail-closed -- and the
    CLI then wrote `{covers 4.5 days, n_seconds: 0}` to disk, which reads
    like a measurement of a silent box. Nothing downstream was fooled
    (`make_silence_fn` refuses an empty list) but a human reading the
    directory would have been. Empty means no file and a non-zero exit."""
    out = tmp_path / "cap.json"
    monkeypatch.setattr(rc, "journal_seconds_probe", lambda *a, **k: [])
    assert rc.main(["journal-seconds", "--since", "2026-08-25T00:00:00Z",
                    "--until", "2026-08-26T00:00:00Z", "--out", str(out)]) == 1
    assert not out.exists()
    assert json.loads(capsys.readouterr().out)["n_seconds"] == 0

    monkeypatch.setattr(rc, "journal_seconds_probe", lambda *a, **k: [1788000000])
    assert rc.main(["journal-seconds", "--since", "2026-08-25T00:00:00Z",
                    "--until", "2026-08-26T00:00:00Z", "--out", str(out)]) == 0
    assert json.loads(out.read_text())["seconds"] == [1788000000]


# ---------------------------------------------------------------------------
# Round 364: per-boot journal capture, cached.
# ---------------------------------------------------------------------------

_BOOTS_R364 = json.dumps([
    {"index": -2, "boot_id": "aaaa", "first_entry": 1_000_000_000_000,
     "last_entry": 1_000_100_000_000},
    {"index": -1, "boot_id": "bbbb", "first_entry": 1_000_200_000_000,
     "last_entry": 1_000_300_000_000},
    {"index": 0, "boot_id": "cccc", "first_entry": 1_000_400_000_000,
     "last_entry": 1_000_450_000_000},
])


def test_parse_rate_probe_is_fail_closed():
    assert rc.parse_rate_probe("17655 4069") == {"n_entries": 17655, "wall_ms": 4069}
    assert rc.parse_rate_probe("17655 4069\n") == {"n_entries": 17655, "wall_ms": 4069}
    # Every malformed shape must return None, not raise and not half-parse:
    # the caller turns None into the timeout FLOOR, and a floor is a scan
    # that fails fast and gets retried. A crash here would take out a sweep
    # that had already paid for the boots before it.
    for bad in ("", "17655", "abc def", "\n", None):
        assert rc.parse_rate_probe(bad) is None


def test_size_scan_timeout_scales_with_measured_rate_not_with_span():
    """The measured spread on the real box is what forces this.

    Boot -5 and boot -2 have comparable spans (124498 s and 143348 s) and
    scan costs of 14.5 s and 1944 s -- a 134x difference driven entirely by
    entry density, not by span. A timeout sized from span alone is wrong for
    one of them by two orders of magnitude in whichever direction it is
    tuned, which is precisely how round 358's single 1400 s constant both
    over-served six boots and killed the seventh.
    """
    sparse = rc.size_scan_timeout({"n_entries": 11, "wall_ms": 35}, 124498)
    dense = rc.size_scan_timeout({"n_entries": 17655, "wall_ms": 4069}, 143348)
    assert sparse["sized_from"] == "measured"
    assert 10 < sparse["projected_s"] < 20
    assert 1900 < dense["projected_s"] < 2000
    assert dense["timeout_s"] > sparse["timeout_s"] * 10
    # The floor keeps a tiny boot from getting a timeout too small to even
    # connect; the ceiling keeps a pathological probe from parking a round.
    assert rc.size_scan_timeout({"n_entries": 0, "wall_ms": 0}, 10)["timeout_s"] == 60
    assert rc.size_scan_timeout({"n_entries": 9, "wall_ms": 999999}, 10**9,
                                ceiling_s=3600)["timeout_s"] == 3600


def test_size_scan_timeout_missing_probe_falls_back_to_floor_not_to_a_big_constant():
    """An unmeasured boot must fail FAST. Round 358's failure was a 1400 s
    client timeout burning 23 min to produce `n_seconds: 0`; defaulting an
    unmeasurable boot to a large budget would reproduce exactly that."""
    out = rc.size_scan_timeout(None, 143348)
    assert out == {"timeout_s": 60, "projected_s": None, "sized_from": "fallback"}


def test_boot_scan_targets_skips_cached_closed_boots_and_always_rescans_the_open_one(tmp_path):
    boots = rc.parse_boot_history(_BOOTS_R364)
    cache = tmp_path / "c"
    cache.mkdir()

    first = {t["boot_id"]: t for t in rc.boot_scan_targets(boots, cache)}
    assert all(t["needs_scan"] for t in first.values())
    # cheapest-first ordering: a budgeted sweep must bank the cheap boots
    # before it risks the expensive one.
    assert [t["span_s"] for t in rc.boot_scan_targets(boots, cache)] == \
           sorted(t["span_s"] for t in first.values())

    for bid in ("aaaa", "bbbb", "cccc"):
        (cache / f"journal-seconds-{bid}.json").write_text(
            json.dumps({"boot_id": bid, "n_seconds": 5, "complete": True,
                        "seconds": [1, 2, 3, 4, 5]}))
    second = {t["boot_id"]: t for t in rc.boot_scan_targets(boots, cache)}
    assert second["aaaa"]["needs_scan"] is False       # closed + complete
    assert second["bbbb"]["needs_scan"] is False       # closed + complete
    assert second["cccc"]["needs_scan"] is True        # OPEN: journal grows
    assert second["cccc"]["reason"] == "open boot, rescan"

    # An INCOMPLETE cached capture is not a cache hit. `complete: False` is
    # how a truncated scan records itself, and treating it as done would
    # silently freeze a partial measurement into the record forever.
    (cache / "journal-seconds-aaaa.json").write_text(
        json.dumps({"boot_id": "aaaa", "n_seconds": 5, "complete": False,
                    "seconds": [1]}))
    third = {t["boot_id"]: t for t in rc.boot_scan_targets(boots, cache)}
    assert third["aaaa"]["needs_scan"] is True
    assert third["aaaa"]["reason"] == "cached but incomplete, rescan"

    # A corrupt cache file is a miss, not a crash.
    (cache / "journal-seconds-aaaa.json").write_text("{not json")
    assert {t["boot_id"]: t for t in rc.boot_scan_targets(boots, cache)}["aaaa"]["needs_scan"]


def test_boot_scan_targets_extends_the_open_boot_to_now():
    """The open boot's `last_entry` is a snapshot taken when the boot list
    was captured; by scan time the box has logged more. Scanning only to the
    stale `last_entry` leaves a sliver uncovered at exactly the end of the
    log, which is where the freshest gap always is."""
    boots = rc.parse_boot_history(_BOOTS_R364)
    later = 1_000_450 + 9999
    t = {x["boot_id"]: x for x in rc.boot_scan_targets(boots, "/nonexistent", now_s=later)}
    assert t["cccc"]["to_s"] == later
    assert t["bbbb"]["to_s"] == 1_000_300     # closed boot: untouched


def test_merge_captures_unions_and_never_overstates_liveness():
    a = {"boot_id": "aaaa", "covers_from_utc": "2026-08-20T00:00:00Z",
         "covers_to_utc": "2026-08-20T01:00:00Z", "n_seconds": 2,
         "complete": True, "seconds": [100, 200]}
    b = {"boot_id": "bbbb", "covers_from_utc": "2026-08-22T00:00:00Z",
         "covers_to_utc": "2026-08-22T01:00:00Z", "n_seconds": 2,
         "complete": True, "seconds": [200, 300]}
    m = rc.merge_captures([a, b])
    assert m["seconds"] == [100, 200, 300]          # union, deduped, sorted
    assert m["n_seconds"] == 3
    assert m["covers_from_utc"] == "2026-08-20T00:00:00Z"
    assert m["covers_to_utc"] == "2026-08-22T01:00:00Z"
    assert [s["boot_id"] for s in m["sources"]] == ["aaaa", "bbbb"]
    # Empty and all-empty inputs produce a capture `make_silence_fn` refuses,
    # rather than one claiming coverage it does not have.
    assert rc.make_silence_fn(rc.merge_captures([])) is None
    assert rc.make_silence_fn(rc.merge_captures([{"seconds": []}])) is None


def test_merged_coverage_hole_weakens_the_bound_it_never_inflates_liveness():
    """The one property that makes merging across boots sound.

    The merged `covers` window spans the inter-boot stretches when the box
    was OFF and no journal exists. A gap landing in such a hole must come
    back with a bound no better than its own length -- i.e. the same answer
    as no evidence at all -- and must never come back claiming the box was
    demonstrably alive there.
    """
    from datetime import datetime, timezone
    m = rc.merge_captures([
        {"boot_id": "a", "covers_from_utc": "2026-08-20T00:00:00Z",
         "covers_to_utc": "2026-08-20T01:00:00Z", "seconds": [
             int(datetime(2026, 8, 20, 0, 30, tzinfo=timezone.utc).timestamp())]},
        {"boot_id": "b", "covers_from_utc": "2026-08-22T00:00:00Z",
         "covers_to_utc": "2026-08-22T01:00:00Z", "seconds": [
             int(datetime(2026, 8, 22, 0, 30, tzinfo=timezone.utc).timestamp())]},
    ])
    sil = rc.make_silence_fn(m)
    t1 = datetime(2026, 8, 21, 0, 0, tzinfo=timezone.utc)   # inside the OFF hole
    t2 = datetime(2026, 8, 21, 6, 0, tzinfo=timezone.utc)
    got = sil(t1, t2)
    assert got is not None
    assert got["n_entry_seconds"] == 0
    # bound == the whole gap: no better than unwitnessed, which is correct.
    assert got["max_silence_s"] == got["gap_s"] == 6 * 3600
    assert rc.gap_unobserved_s({"witness_strength": rc.WITNESS_BOUNDED,
                                "bound_s": got["max_silence_s"],
                                "gap_s": got["gap_s"]}) == 6 * 3600


def test_cli_journal_boots_plan_probes_but_scans_nothing(tmp_path, capsys, monkeypatch):
    bh = tmp_path / "boots.json"
    bh.write_text(_BOOTS_R364)
    scanned = []
    monkeypatch.setattr(rc, "journal_rate_probe",
                        lambda *a, **k: {"n_entries": 300, "wall_ms": 100})
    monkeypatch.setattr(rc, "journal_seconds_probe",
                        lambda *a, **k: scanned.append(a) or [1])
    assert rc.main(["journal-boots", "--boot-history", str(bh),
                    "--cache-dir", str(tmp_path / "c"), "--plan"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert scanned == []
    assert {r["action"] for r in out["results"]} == {"planned"}
    assert all(r["sized_from"] == "measured" for r in out["results"])
    assert not list((tmp_path / "c").glob("*.json"))


def test_cli_journal_boots_caches_scans_and_merges(tmp_path, capsys, monkeypatch):
    bh = tmp_path / "boots.json"
    bh.write_text(_BOOTS_R364)
    calls = []

    def fake_scan(since, until, **kw):
        calls.append((since, until, kw.get("timeout_s")))
        return [1_000_000 + len(calls)]

    monkeypatch.setattr(rc, "journal_rate_probe",
                        lambda *a, **k: {"n_entries": 300, "wall_ms": 100})
    monkeypatch.setattr(rc, "journal_seconds_probe", fake_scan)
    cache = tmp_path / "c"
    merged = tmp_path / "merged.json"
    assert rc.main(["journal-boots", "--boot-history", str(bh),
                    "--cache-dir", str(cache), "--merge-out", str(merged)]) == 0
    first = json.loads(capsys.readouterr().out)
    assert len(calls) == 3
    assert all(t is not None and t >= 60 for _, _, t in calls)
    assert {r["action"] for r in first["results"]} == {"scanned"}
    assert all(r["complete"] for r in first["results"])
    assert len(list(cache.glob("journal-seconds-*.json"))) == 3
    assert json.loads(merged.read_text())["n_seconds"] == 3

    # Re-run: the two CLOSED boots are served from cache and only the OPEN
    # one is re-scanned. This is the whole point -- boot -2 on the real box
    # costs a projected 1944 s, and paying it once ever is what makes the
    # sweep affordable at all.
    calls.clear()
    assert rc.main(["journal-boots", "--boot-history", str(bh),
                    "--cache-dir", str(cache)]) == 0
    second = json.loads(capsys.readouterr().out)
    actions = {r["boot_id"]: r["action"] for r in second["results"]}
    assert actions == {"aaaa": "skip", "bbbb": "skip", "cccc": "scanned"}
    assert len(calls) == 1


def test_cli_journal_boots_budget_defers_rather_than_truncates(tmp_path, capsys, monkeypatch):
    """A sweep that runs out of round must DEFER whole boots, not half-scan
    one. Because the cache is per boot and keyed on completeness, a deferred
    boot costs the next round nothing extra, while a truncated one written as
    complete would poison the record permanently."""
    bh = tmp_path / "boots.json"
    bh.write_text(_BOOTS_R364)
    monkeypatch.setattr(rc, "journal_rate_probe",
                        lambda *a, **k: {"n_entries": 300, "wall_ms": 100})
    monkeypatch.setattr(rc, "journal_seconds_probe", lambda *a, **k: [1])
    # NB: main() calls time.time() twice before the loop (once for the open
    # boot's now_s, once for `started`), so a monotone counter is used rather
    # than a hand-built sequence -- getting that count wrong is how this test
    # first passed for the wrong reason.
    tick = {"v": 0.0}

    def clock():
        tick["v"] += 1000.0
        return tick["v"]

    monkeypatch.setattr(rc.time, "time", clock)
    assert rc.main(["journal-boots", "--boot-history", str(bh),
                    "--cache-dir", str(tmp_path / "c"), "--budget-s", "10"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [r["action"] for r in out["results"]] == ["deferred"] * 3
    assert not list((tmp_path / "c").glob("*.json"))


def test_cli_journal_boots_max_boot_s_defers_the_expensive_boot_only(tmp_path, capsys, monkeypatch):
    bh = tmp_path / "boots.json"
    bh.write_text(_BOOTS_R364)
    # The OPEN boot is extended to now, so `now` must be pinned or its span
    # becomes "epoch to today" and it dominates every projection -- which is
    # real behaviour, and is why this test pins the clock.
    monkeypatch.setattr(rc.time, "time", lambda: 1_000_460.0)
    # spans: aaaa 100 s, bbbb 100 s, cccc 60 s (extended 1_000_450 -> now).
    # At 100 s of probe wall per 300 s window: 33.3 s, 33.3 s, 20 s.
    monkeypatch.setattr(rc, "journal_rate_probe",
                        lambda *a, **k: {"n_entries": 300, "wall_ms": 100_000})
    monkeypatch.setattr(rc, "journal_seconds_probe", lambda *a, **k: [1])
    assert rc.main(["journal-boots", "--boot-history", str(bh),
                    "--cache-dir", str(tmp_path / "c"), "--max-boot-s", "25"]) == 0
    out = json.loads(capsys.readouterr().out)
    by = {r["boot_id"]: r for r in out["results"]}
    assert by["cccc"]["action"] == "scanned"
    assert by["aaaa"]["action"] == "deferred"
    assert by["aaaa"]["why"] == "over --max-boot-s"


def test_cli_journal_boots_marks_a_timed_out_scan_incomplete(tmp_path, capsys, monkeypatch):
    """Round 358's exact trap, now detectable.

    `journal_seconds_probe` returns [] for a client-side timeout and for a
    genuinely silent window alike. A scan that comes back having consumed
    essentially its whole budget is the truncation case; it must not be
    cached as a finished measurement of a quiet boot.
    """
    bh = tmp_path / "boots.json"
    bh.write_text(_BOOTS_R364)
    monkeypatch.setattr(rc, "journal_rate_probe",
                        lambda *a, **k: {"n_entries": 300, "wall_ms": 100})
    monkeypatch.setattr(rc, "journal_seconds_probe", lambda *a, **k: [1, 2, 3])
    # Each scan appears to consume its entire sized timeout.
    t = {"v": 0.0}

    def slow():
        t["v"] += 5000.0
        return t["v"]

    monkeypatch.setattr(rc.time, "time", slow)
    cache = tmp_path / "c"
    assert rc.main(["journal-boots", "--boot-history", str(bh),
                    "--cache-dir", str(cache)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert all(r["complete"] is False for r in out["results"] if r["action"] == "scanned")
    for f in cache.glob("journal-seconds-*.json"):
        assert json.loads(f.read_text())["complete"] is False
    # ...and therefore the next sweep re-scans them rather than trusting them.
    assert all(t_["needs_scan"] for t_ in
               rc.boot_scan_targets(rc.parse_boot_history(_BOOTS_R364), cache))


# --- Round 370: the suspend witness -------------------------------------


def test_classify_suspend_lines_real_suspend_is_detected():
    lines = ["kernel: PM: suspend entry (deep)",
             "kernel: Freezing user space processes ... done.",
             "kernel: usb 1-1: reset high-speed USB device"]
    out = rc.classify_suspend_lines(lines)
    assert out["slept"] is True
    assert out["n_real"] == 2
    assert out["n_false_positive"] == 0


def test_classify_suspend_lines_round_364_false_positive_is_not_a_suspend():
    """`Registered nosave memory` is boot-time setup, not a sleep.

    Round 364 saw 7 of these on boot 0 and correctly refused to read them as
    suspends. This pins that refusal so a future widening of
    SUSPEND_REAL_RE cannot silently re-admit them.
    """
    lines = ["kernel: PM: hibernation: Registered nosave memory: [mem 0x1000-0x1fff]"] * 7
    out = rc.classify_suspend_lines(lines)
    assert out["slept"] is False
    assert out["n_real"] == 0
    assert out["n_false_positive"] == 7


def test_classify_suspend_lines_unrecognised_pm_line_is_surfaced_not_dropped():
    lines = ["kernel: PM: hibernation: a future message we have no pattern for"]
    out = rc.classify_suspend_lines(lines)
    assert out["n_other"] == 1
    assert out["slept"] is False


def test_classify_suspend_lines_ignores_unrelated_lines():
    out = rc.classify_suspend_lines(["kernel: EXT4-fs (dm-0): mounted filesystem"])
    assert out == {"n_scanned": 1, "real": [], "false_positive": [], "other": [],
                   "n_real": 0, "n_false_positive": 0, "n_other": 0, "slept": False}


def test_max_interior_silence_finds_the_largest_gap():
    out = rc.max_interior_silence([100, 101, 102, 400, 401])
    assert out["max_silence_s"] == 298
    assert out["from_epoch"] == 102
    assert out["to_epoch"] == 400
    assert out["covered_span_s"] == 301


def test_max_interior_silence_needs_two_seconds_to_bound_anything():
    assert rc.max_interior_silence([]) is None
    assert rc.max_interior_silence([5]) is None


def test_max_interior_silence_deduplicates_and_sorts():
    assert rc.max_interior_silence([9, 1, 9, 1, 5])["max_silence_s"] == 4


def test_silence_bound_excludes_incomplete_captures():
    """A truncated scan's biggest gap bounds nothing.

    Round 358's trap: `journal_seconds_probe` returns [] on a client-side
    timeout, so a partial scan can look like a very quiet boot. Only
    `complete` captures may contribute to the overall bound.
    """
    caps = [
        {"boot_id": "a", "boot_index": -1, "complete": True,
         "seconds": [0, 10, 400]},          # 390 s gap, counts
        {"boot_id": "b", "boot_index": 0, "complete": False,
         "seconds": [0, 100000]},           # 100000 s gap, must NOT count
    ]
    out = rc.silence_bound(caps)
    assert out["max_silence_s"] == 390
    assert out["n_usable"] == 1
    assert out["n_unusable"] == 1
    assert out["unusable"][0]["boot_id"] == "b"


def test_silence_bound_empty_input_reports_no_bound_rather_than_zero():
    out = rc.silence_bound([])
    assert out["max_silence_s"] is None
    assert out["covered_running_time_s"] == 0


_R370_BOOTS = rc.parse_boot_history(json.dumps([
    {"index": -1, "boot_id": "aaa",
     "first_entry": 1787831451404446, "last_entry": 1787969407949006},
    {"index": 0, "boot_id": "bbb",
     "first_entry": 1788049952417669, "last_entry": 1788101832061199},
]))


def _r370_rec(round_, checked, boot_utc):
    return {"round": round_, "checked_at_utc": checked, "boot_utc": boot_utc,
            "verdict": "up"}


def test_boot_utc_crosscheck_healthy_deltas_are_small_and_negative():
    """The real round-352/358/364/370 shape: boot_utc lands just BEFORE
    journald's first record, because the kernel counts uptime before
    journald exists to write anything."""
    recs = [_r370_rec(352, "2026-08-30T02:20:54Z", "2026-08-30T00:32:27Z"),
            _r370_rec(370, "2026-08-30T14:56:57Z", "2026-08-30T00:32:27Z")]
    out = rc.boot_utc_crosscheck(recs, _R370_BOOTS)
    assert out["n_checked"] == 2
    assert out["n_out_of_tolerance"] == 0
    assert out["n_wrong_sign"] == 0
    assert out["max_abs_delta_s"] == 5.0
    assert all(c["boot_index"] == 0 for c in out["checks"])


def test_boot_utc_crosscheck_flags_uptime_that_lost_time():
    """The failure round 340 worried about: if /proc/uptime does NOT count
    a suspend, boot_utc drifts FORWARD of journald's first_entry by the
    slept duration. That is a positive delta out of tolerance."""
    recs = [_r370_rec(999, "2026-08-30T14:00:00Z", "2026-08-30T02:32:32Z")]
    out = rc.boot_utc_crosscheck(recs, _R370_BOOTS, tolerance_s=120)
    assert out["n_out_of_tolerance"] == 1
    assert out["n_wrong_sign"] == 1
    assert out["checks"][0]["delta_s"] == 7200.0


def test_boot_utc_crosscheck_records_without_boot_utc_are_skipped():
    recs = [{"round": 1, "checked_at_utc": "2026-08-30T14:00:00Z",
             "boot_utc": None, "verdict": "down"}]
    out = rc.boot_utc_crosscheck(recs, _R370_BOOTS)
    assert out["n_checked"] == 0 and out["n_unmatched"] == 0


def test_boot_utc_crosscheck_reports_uncheckable_records_rather_than_dropping():
    """A record older than the oldest surviving boot cannot be checked.
    It must be visible as `unmatched`, not silently absent -- otherwise
    `n_checked` reads as full coverage of the log."""
    recs = [_r370_rec(124, "2026-08-25T16:11:00Z", "2026-08-25T12:58:00Z")]
    out = rc.boot_utc_crosscheck(recs, _R370_BOOTS)
    assert out["n_checked"] == 0
    assert out["n_unmatched"] == 1
    assert "no boot in the journal" in out["unmatched"][0]["why"]


class _R370Res:
    def __init__(self, rc_, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc_, out, err


def test_suspend_probe_parses_a_healthy_never_slept_box():
    payload = json.dumps({"boottime": 51990.3, "monotonic": 51990.3,
                          "uptime": 51990.3, "success": "0", "fail": "0",
                          "last_failed_dev": "", "last_failed_step": ""})
    out = rc.suspend_probe(runner=lambda *a, **k: _R370Res(0, payload))
    assert out["suspend_success"] == 0
    assert out["slept_this_boot"] is False
    assert out["cumulative_suspend_s"] == 0.0


def test_suspend_probe_detects_a_box_that_slept():
    payload = json.dumps({"boottime": 8000.0, "monotonic": 5000.0,
                          "uptime": 8000.0, "success": "2", "fail": "0",
                          "last_failed_dev": "", "last_failed_step": ""})
    out = rc.suspend_probe(runner=lambda *a, **k: _R370Res(0, payload))
    assert out["suspend_success"] == 2
    assert out["cumulative_suspend_s"] == 3000.0
    assert out["slept_this_boot"] is True


def test_suspend_probe_cumulative_delta_alone_is_enough_to_call_it_slept():
    """success==0 but a real BOOTTIME/MONOTONIC gap still means it slept --
    the two sources are OR-ed, so a kernel that fails to bump the counter
    cannot produce a false 'never slept'."""
    payload = json.dumps({"boottime": 8000.0, "monotonic": 7000.0,
                          "uptime": 8000.0, "success": "0", "fail": "0",
                          "last_failed_dev": "", "last_failed_step": ""})
    out = rc.suspend_probe(runner=lambda *a, **k: _R370Res(0, payload))
    assert out["slept_this_boot"] is True


def test_suspend_probe_failures_return_none_not_a_reassuring_answer():
    """Every failure mode must degrade to 'unknown'. Returning a
    'never slept' record on a failed read would manufacture a witness --
    the exact mistake round 358 caught in the journal probe."""
    assert rc.suspend_probe(runner=lambda *a, **k: _R370Res(255, "")) is None
    assert rc.suspend_probe(runner=lambda *a, **k: _R370Res(0, "not json")) is None
    assert rc.suspend_probe(runner=lambda *a, **k: _R370Res(0, "{}")) is None
    assert rc.suspend_probe(
        runner=lambda *a, **k: _R370Res(0, json.dumps({"success": "x", "fail": "0"}))) is None

    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=1)
    assert rc.suspend_probe(runner=_timeout) is None


# --- round 376: boot_utc sampling jitter ----------------------------------

def _up_gap(b1, b2):
    """One up streak of two checks whose boot_utc endpoints are b1 -> b2.

    Returns the single gap dict with the streak's `missed_excursions` folded in
    as `missed_excursion` (None when empty), so each test reads as one claim."""
    records = [_rec("2026-08-30T14:56:57Z", "up", 370, boot=b1),
               _rec("2026-08-30T19:53:44Z", "up", 376, boot=b2)]
    streaks = rc.gap_continuity(sorted(records, key=rc._sort_key))
    gaps = [g for st in streaks for g in st["gaps"]]
    excursions = [e for st in streaks for e in st["missed_excursions"]]
    assert len(gaps) == 1
    assert len(excursions) <= 1
    gap = dict(gaps[0])
    gap["missed_excursion"] = excursions[0] if excursions else None
    return gap


def test_one_second_boot_utc_jitter_is_not_a_reboot():
    """ROUND 376, found by this round's own live check.

    `boot_utc` is `now - /proc/uptime` truncated to whole seconds and read a
    round-trip apart, so two checks of one boot need not agree exactly. The
    real log's five up-checks of boot 43e0c767 report 00:32:27Z four times and
    00:32:28Z once. The rule was `if d2 > d1: rebooted`, so that single second
    made the instrument announce a reboot that `journalctl --list-boots`
    directly contradicts -- same seven boot_ids, same 43e0c767, last_entry only
    grown -- and dropped an otherwise good gap to WITNESS_NONE."""
    g = _up_gap("2026-08-30T00:32:27Z", "2026-08-30T00:32:28Z")
    assert g["witness_strength"] == rc.WITNESS_REBOOT_ONLY
    assert g["witness_source"] == "boot_utc_unchanged"
    assert g["missed_excursion"] is None


def test_jitter_is_reported_not_silently_swallowed():
    """Absorbing the movement must not hide it: a box that starts drifting
    seconds per check should be visible in the note."""
    g = _up_gap("2026-08-30T00:32:27Z", "2026-08-30T00:32:28Z")
    assert "+1 s" in g["witness_note"]
    assert "sampling jitter" in g["witness_note"]
    # an exactly-equal pair says nothing extra
    same = _up_gap("2026-08-30T00:32:27Z", "2026-08-30T00:32:27Z")
    assert "sampling jitter" not in same["witness_note"]


def test_backwards_jitter_is_also_absorbed():
    """The old code called any backwards movement "contradictory". The same
    +/-1 s truncation produces it just as easily, and it is no more meaningful
    in that direction."""
    g = _up_gap("2026-08-30T00:32:28Z", "2026-08-30T00:32:27Z")
    assert g["witness_strength"] == rc.WITNESS_REBOOT_ONLY
    assert g["missed_excursion"] is None
    assert "-1 s" in g["witness_note"]


def test_a_real_reboot_still_trips_the_detector():
    """The tolerance must not blind the rule. This box needs 13.2 s just to
    load weights after the kernel is up, so any genuine reboot moves boot_utc
    by far more than the tolerance."""
    g = _up_gap("2026-08-30T00:32:27Z", "2026-08-30T11:50:48Z")
    assert g["witness_strength"] == rc.WITNESS_NONE
    assert g["missed_excursion"]["kind"] == "boot_utc_advanced_inside_gap"
    assert g["missed_excursion"]["advance_s"] == pytest.approx(40701.0)
    assert "rebooted" in g["witness_note"]


def test_jitter_tolerance_boundary_is_exclusive_above():
    """Exactly at the tolerance is still jitter; one second past it is not."""
    at = _up_gap("2026-08-30T00:32:27Z",
                 "2026-08-30T00:32:%02dZ" % (27 + rc.BOOT_UTC_JITTER_S))
    assert at["missed_excursion"] is None
    past = _up_gap("2026-08-30T00:32:27Z",
                   "2026-08-30T00:32:%02dZ" % (27 + rc.BOOT_UTC_JITTER_S + 1))
    assert past["missed_excursion"] is not None


def test_the_real_log_still_reports_no_missed_excursions():
    """End-to-end on the live log, which is what caught this."""
    report = rc.continuity_report(_real_log_records())
    assert report["missed_excursions"] == []


# ------------------------------- round 400: what unobserved_total is conditioned on

def test_continuity_report_always_states_the_basis_of_unobserved_total():
    """Round 394 (P22): the SAME command over the SAME log printed 102h19m47s
    and 0h12m00s depending on an optional flag, and nothing in the output said
    which. The name stays (round 334 item 5 -- three rounds have published
    under it); the basis ships beside it."""
    recs = [
        {"round": 1, "checked_at_utc": "2026-08-30T00:00:00Z", "verdict": "up"},
        {"round": 2, "checked_at_utc": "2026-08-30T05:00:00Z", "verdict": "up"},
    ]
    rep = rc.continuity_report(recs)
    b = rep["unobserved_basis"]
    assert b["interior_witness_supplied"] is False
    assert "loosest possible bracket" in b["note"]
    assert "Do not compare" in b["note"]


def test_the_basis_note_flips_once_a_witness_is_supplied():
    recs = [
        {"round": 1, "checked_at_utc": "2026-08-30T00:00:00Z", "verdict": "up"},
        {"round": 2, "checked_at_utc": "2026-08-30T05:00:00Z", "verdict": "up"},
    ]
    rep = rc.continuity_report(recs, basis={"sar_archive_supplied": True})
    b = rep["unobserved_basis"]
    assert b["interior_witness_supplied"] is True
    assert "CURRENT BEST BRACKET" in b["note"]
    assert "not a running total" in b["note"]


def test_the_basis_records_boot_history_and_journal_independently():
    recs = [
        {"round": 1, "checked_at_utc": "2026-08-30T00:00:00Z", "verdict": "up"},
        {"round": 2, "checked_at_utc": "2026-08-30T05:00:00Z", "verdict": "up"},
    ]
    rep = rc.continuity_report(
        recs, boots=[{"index": 0, "boot_id": "b0",
                      "first_entry_utc": "2026-08-30T00:00:00Z",
                      "last_entry_utc": "2026-08-30T05:00:00Z"}],
        silence=None)
    assert rep["unobserved_basis"]["boot_history_boots"] == 1
    assert rep["unobserved_basis"]["journal_capture_supplied"] is False
    assert rep["unobserved_basis"]["interior_witness_supplied"] is True


def test_the_basis_does_not_change_unobserved_total_itself():
    """Emitting the basis must be additive. If it moved the number, three
    rounds of published figures would silently change meaning."""
    recs = [
        {"round": 1, "checked_at_utc": "2026-08-30T00:00:00Z", "verdict": "up"},
        {"round": 2, "checked_at_utc": "2026-08-30T05:00:00Z", "verdict": "up"},
    ]
    a = rc.continuity_report(recs)
    b = rc.continuity_report(recs, basis={"sar_archive_supplied": True})
    assert a["unobserved_total_s"] == b["unobserved_total_s"]
    assert a["max_unobserved_outage_s"] == b["max_unobserved_outage_s"]


# --------------------------------------------- LastSeen drift (round 448)
#
# The module adopted `tailscale status --json`'s `LastSeen` over the
# plain-text renderer because the renderer is recomputed each read and
# LastSeen was "the actual timestamp". Round 448 measured LastSeen being
# recomputed too: one continuous outage, box down throughout, local
# `tailscaled` up since 2026-08-09, and the field read 124 s EARLIER eleven
# hours later. These pin what that costs and what it must not be allowed
# to cost.

DRIFT_RECORDS = [
    {"checked_at_utc": "2026-09-01T19:30:39Z", "round": 436, "verdict": "down",
     "tailscale_last_seen_utc": "2026-09-01T18:30:00.1Z"},
    {"checked_at_utc": "2026-09-01T19:46:19Z", "round": 436, "verdict": "down",
     "tailscale_last_seen_utc": "2026-09-01T18:30:00.1Z"},
    {"checked_at_utc": "2026-09-02T06:32:13Z", "round": 448, "verdict": "down",
     "tailscale_last_seen_utc": "2026-09-01T18:27:56.1Z"},
]


def test_lastseen_drift_names_the_streak_whose_field_was_recomputed():
    d = rc.lastseen_drift(DRIFT_RECORDS)
    assert d["n_drifting_streaks"] == 1
    s = d["streaks"][0]
    assert s["distinct_values"] == ["2026-09-01T18:27:56.1Z",
                                    "2026-09-01T18:30:00.1Z"]
    assert s["spread_s"] == 124.0
    assert s["direction"] == "earlier" and s["drift_s"] == -124.0
    assert (s["start_round"], s["end_round"]) == (436, 448)


def test_a_streak_with_one_lastseen_value_is_not_drift():
    """Round 436 read the field twice and got the same value both times. That
    is the ordinary case and must stay silent, or the check cries wolf on
    every log it is ever pointed at."""
    assert rc.lastseen_drift(DRIFT_RECORDS[:2])["n_drifting_streaks"] == 0


def test_the_tailscale_zero_value_is_not_a_timestamp():
    """`0001-01-01T00:00:00Z` is tailscale's "no reading", and it appears ten
    times in the live log. Treated as a timestamp it is both a permanent
    drift report and a start bound at the beginning of the calendar."""
    recs = [dict(DRIFT_RECORDS[0]),
            dict(DRIFT_RECORDS[1], tailscale_last_seen_utc="0001-01-01T00:00:00Z")]
    assert rc.lastseen_drift(recs)["n_drifting_streaks"] == 0
    assert rc._streak_lastseen_values({"records": recs}) == [
        "2026-09-01T18:30:00.1Z"]


def test_a_disputed_start_bound_takes_the_earliest_reading_and_says_so():
    """`earliest_possible_start` took the LATEST LastSeen, which is right only
    while the field is trustworthy. Two readings of one outage cannot both be
    the last instant the box was alive, and a bound named EARLIEST POSSIBLE
    has to hold whichever is wrong."""
    b = rc.streak_bounds(DRIFT_RECORDS)[0]
    assert b["earliest_possible_start_utc"] == "2026-09-01T18:27:56.1Z"
    assert b["earliest_possible_start_source"] == "tailscale_last_seen_min_disputed"
    assert b["lastseen_disputed"] == ["2026-09-01T18:27:56.1Z",
                                      "2026-09-01T18:30:00.1Z"]
    # the honest cost: 124 s more declared ignorance, not less
    assert b["start_uncertainty_s"] == 3638.9 + 124.0


def test_an_undisputed_start_bound_still_takes_the_reading_it_always_did():
    """The old behaviour is the majority case and is not changed by this."""
    b = rc.streak_bounds(DRIFT_RECORDS[:2])[0]
    assert b["earliest_possible_start_utc"] == "2026-09-01T18:30:00.1Z"
    assert b["earliest_possible_start_source"] == "tailscale_last_seen"
    assert b["lastseen_disputed"] is None


def test_a_disputed_lastseen_cannot_manufacture_a_missed_excursion():
    """The failure mode the drift makes reachable. A LastSeen rounded UP lands
    later than the truth, and later is the direction that walks a reading
    into a down gap -- where the module reports it as POSITIVE evidence that
    the box came back to life mid-outage. With another reading of the same
    streak placing the sighting before the gap, the two contradict and
    neither is evidence."""
    recs = [
        {"checked_at_utc": "2026-09-01T18:29:00Z", "round": 1, "verdict": "down",
         "tailscale_last_seen_utc": "2026-09-01T18:27:56.1Z"},
        {"checked_at_utc": "2026-09-01T18:35:00Z", "round": 2, "verdict": "down",
         "tailscale_last_seen_utc": "2026-09-01T18:30:00.1Z"},
    ]
    c = rc.gap_continuity(recs)[0]
    assert c["missed_excursions"] == []
    assert c["witnessed_gap_count"] == 0        # not witnessed either: unknown
    assert c["unwitnessed_gap_count"] == 1


def test_an_undisputed_lastseen_inside_a_gap_is_still_reported():
    """The negative control. The guard must not silence the contradiction the
    field exists to deliver -- only the case where the field contradicts
    ITSELF."""
    recs = [
        {"checked_at_utc": "2026-09-01T18:29:00Z", "round": 1, "verdict": "down"},
        {"checked_at_utc": "2026-09-01T18:35:00Z", "round": 2, "verdict": "down",
         "tailscale_last_seen_utc": "2026-09-01T18:31:00Z"},
    ]
    c = rc.gap_continuity(recs)[0]
    assert len(c["missed_excursions"]) == 1
    assert c["missed_excursions"][0]["evidence_utc"] == "2026-09-01T18:31:00Z"


def test_the_live_log_has_exactly_one_drifting_streak_and_it_is_this_outage():
    """Read against the real log, not a fixture. If a later round's record
    makes this two, that is a second measurement of the same instability and
    should be written down, not asserted away.

    ROUND 454 rewrote the third assertion. It used to read
    `d["streaks"][0]["end_round"] == 448`, and `end_round` is the LAST
    record of the streak -- so it advanced to 454 the moment round 454
    appended its own row, a row that read the SAME LastSeen round 448 did
    and therefore said nothing at all about drift. A test that is
    guaranteed to go red on the next down round, on a field that is not the
    one under test, teaches the next round to edit the number rather than
    look at it. The drift itself is what is pinned now: two distinct values,
    124.0 s apart, in the outage that began at round 436. All three survive
    any number of further readings of a value already in the set."""
    recs = rc.load_log(str(REAL_LOG))
    d = rc.lastseen_drift(recs)
    assert d["n_drifting_streaks"] == 1
    streak = d["streaks"][0]
    assert streak["spread_s"] == 124.0
    assert streak["n_distinct"] == 2
    assert streak["distinct_values"] == ["2026-09-01T18:27:56.1Z",
                                         "2026-09-01T18:30:00.1Z"]
    assert streak["start_round"] == 436
    assert streak["verdict"] == "down"


def test_round_442s_hole_was_closed_by_recovery_not_by_a_live_check():
    """Round 442 probed twice, recorded the failure in prose, and appended
    nothing; round 448 found the hole and replayed its OWN probes into the
    log rather than opening a third connection.

    ROUND 454 rewrote this test. Its first assertion used to be
    `448 in rounds and 442 not in rounds` -- which pinned the hole OPEN.
    Round 448's own prose called the hole a gap it had closed "by one round,
    not two", i.e. it wanted 442 recovered; the test it shipped in the same
    commit made recovering 442 a test failure. What is worth pinning is not
    that the hole persists but HOW each round's row got there: 448's by
    replay of its own probes, 442's by recovery from its transcript, which
    is a different and weaker provenance and must stay visibly so."""
    recs = rc.load_log(str(REAL_LOG))
    by_round = {r.get("round"): r for r in recs}
    assert 448 in by_round and 442 in by_round

    r448 = by_round[448]
    assert r448["verdict"] == "down"
    assert r448["source"] == "live-replay-r448"
    assert "two-failures rule" in r448["notes"]

    r442 = by_round[442]
    assert r442["verdict"] == "down"
    assert r442["source"] == "transcript-r442"
    assert r442["source"] != "live", "a recovered row must never claim to be live"
    assert "logs/round-442.json" in r442["notes"]


# --- round 454: the forward LastSeen witness -------------------------------
#
# `unobserved_total_s` was NON-MONOTONE in the number of observations. A gap
# whose later record carried no LastSeen scored WITNESS_NONE even when a
# still-later record in the same streak proved the peer had not been on the
# tailnet across the whole span -- so inserting a recovered row SPLIT a
# fully-witnessed gap and charged the log for the half that lost the witness.

def _down(at, round_, last_seen=None):
    r = {"checked_at_utc": at, "round": round_, "verdict": "down"}
    if last_seen is not None:
        r["tailscale_last_seen_utc"] = last_seen
    return r


def test_a_forward_lastseen_witnesses_a_gap_its_own_later_record_cannot():
    recs = [_down("2026-09-01T20:00:00Z", 1),
            _down("2026-09-01T22:00:00Z", 2),                      # no LastSeen
            _down("2026-09-02T00:00:00Z", 3, "2026-09-01T18:00:00Z")]
    gaps = rc.gap_continuity(recs)[0]["gaps"]
    assert gaps[0]["witnessed"] is True
    assert gaps[0]["witness_source"] == "tailscale_last_seen_forward"
    assert gaps[0]["unobserved_s"] == 0.0
    assert "2026-09-02T00:00:00Z" in gaps[0]["witness_note"]
    assert gaps[1]["witness_source"] == "tailscale_last_seen"


def test_the_forward_witness_fails_closed_when_the_streak_disputes_it():
    """Negative control. A reading INSIDE the gap contradicts the forward
    one; round 448 established that a disputed field is evidence of
    nothing, and the forward path must inherit that, not route around it."""
    recs = [_down("2026-09-01T20:00:00Z", 1),
            _down("2026-09-01T22:00:00Z", 2),
            _down("2026-09-02T00:00:00Z", 3, "2026-09-01T18:00:00Z"),
            _down("2026-09-02T02:00:00Z", 4, "2026-09-01T21:00:00Z")]
    gaps = rc.gap_continuity(recs)[0]["gaps"]
    assert gaps[0]["witnessed"] is False
    assert gaps[0]["witness_source"] is None
    assert "disputed" in gaps[0]["witness_note"]


def test_a_forward_reading_that_does_not_qualify_leaves_the_gap_unwitnessed():
    """The other negative control: a forward reading exists but puts the
    peer alive AFTER the earlier check, so it proves nothing about the gap
    and must not be used."""
    recs = [_down("2026-09-01T20:00:00Z", 1),
            _down("2026-09-01T22:00:00Z", 2),
            _down("2026-09-02T00:00:00Z", 3, "2026-09-02T00:00:00Z")]
    gaps = rc.gap_continuity(recs)[0]["gaps"]
    assert gaps[0]["witnessed"] is False
    assert "no later reading in this streak" in gaps[0]["witness_note"]


def test_the_forward_witness_never_manufactures_a_missed_excursion():
    """A forward reading may witness; it may not accuse. The excursion
    claim stays with the record that made the reading."""
    recs = [_down("2026-09-01T20:00:00Z", 1),
            _down("2026-09-01T22:00:00Z", 2),
            _down("2026-09-02T00:00:00Z", 3, "2026-09-01T18:00:00Z")]
    c = rc.gap_continuity(recs)[0]
    assert c["missed_excursions"] == []


def test_inserting_an_interior_check_never_increases_unobserved_total():
    """The invariant the bug broke, measured on the REAL log.

    Rounds 190/220/226/250/280/442 were recovered by round 454 and every one
    of them falls strictly INSIDE a streak that already existed. Removing
    them must leave `unobserved_total_s` exactly where it is -- an
    observation cannot buy ignorance. (292 and 454 are excluded because they
    EXTEND their streaks' spans, which creates genuinely new interior time:
    +7455 s, real and correctly charged.)"""
    recs = rc.load_log(str(REAL_LOG))
    interior = {190, 220, 226, 250, 280, 442}
    without = [r for r in recs if r.get("round") not in interior | {292, 454}]
    with_interior = [r for r in recs if r.get("round") not in {292, 454}]
    assert {r.get("round") for r in with_interior} - {r.get("round") for r in without} == interior
    assert (rc.continuity_report(with_interior)["unobserved_total_s"]
            == rc.continuity_report(without)["unobserved_total_s"])


def test_the_live_log_has_no_unobserved_down_time_at_all():
    """Every down streak in the log is fully witnessed. This was true before
    round 454's recovery, became FALSE when the recovered rows landed
    (+27699 s of down-side ignorance out of nowhere), and is true again."""
    recs = rc.load_log(str(REAL_LOG))
    per_verdict = {}
    for s in rc.gap_continuity(recs):
        per_verdict[s["verdict"]] = per_verdict.get(s["verdict"], 0.0) + s["unobserved_total_s"]
    assert per_verdict["down"] == 0.0


# --- round 454: log coverage ----------------------------------------------

DRIVER_LOG_SAMPLE = """\
[2026-08-26 17:10:17] round 154 track=NUC-integration(E) start (driver_version=x) pid=1
[2026-08-26 17:11:01] round 155 track=SWE-loop(D) start (driver_version=x) pid=1
[2026-08-27 07:56:18] round 190 track=NUC-integration(E) start (driver_version=y) pid=2
[2026-08-27 08:04:02] round 190: success
[2026-08-27 21:49:35] round 196 track=NUC-integration(E) start (driver_version=y) pid=2
"""


def test_driver_e_rounds_reads_the_driver_log_not_the_rotation():
    assert rc.driver_e_rounds(DRIVER_LOG_SAMPLE) == [154, 190, 196]


def test_coverage_exempts_the_round_currently_in_flight():
    """The driver writes a round's `start` line BEFORE the round runs, so a
    check that demanded a row from it would be red for the whole of every E
    round -- round 453's `the check that runs after you are gone` shape."""
    recs = [{"round": 154, "verdict": "down"}, {"round": 190, "verdict": "down"}]
    cov = rc.log_coverage(recs, [154, 190, 196])
    assert cov["in_flight_round"] == 196
    assert cov["missing"] == []
    assert cov["n_owed"] == 2 and cov["n_covered"] == 2


def test_coverage_finds_a_hole_once_the_round_is_no_longer_in_flight():
    recs = [{"round": 154, "verdict": "down"}]
    cov = rc.log_coverage(recs, [154, 190, 196])
    assert cov["missing"] == [190]
    cov2 = rc.log_coverage(recs, [154, 190, 196], allow_in_flight=False)
    assert cov2["missing"] == [190, 196]


def test_a_declared_hole_is_suppressed_but_named():
    recs = [{"round": 154, "verdict": "down"}]
    cov = rc.log_coverage(recs, [154, 190, 196], declared={190: "no transcript"})
    assert cov["missing"] == []
    assert cov["missing_declared"] == {190: "no transcript"}


def test_a_declaration_that_suppresses_nothing_is_reported_as_dead():
    """An acknowledgement that no longer acknowledges anything reads as
    coverage. Round 454 wrote exactly this mistake into its own registry
    first -- declaring round 148, which is outside the population -- and
    this field is what caught it."""
    recs = [{"round": 154, "verdict": "down"}, {"round": 190, "verdict": "down"}]
    cov = rc.log_coverage(recs, [154, 190, 196], declared={190: "stale"})
    assert cov["declared_but_not_missing"] == {190: "stale"}


def test_the_live_log_owes_no_e_round_a_row():
    """The rule round 448 wrote in prose, enforced. Eight E rounds had no
    row when round 454 measured it; seven were recovered and the eighth
    (148) predates the driver log and is outside the population."""
    recs = rc.load_log(str(REAL_LOG))
    e_rounds = rc.driver_e_rounds(Path("logs/driver.log").read_text())
    cov = rc.log_coverage(recs, e_rounds, rc.load_declared_holes())
    assert cov["missing"] == [], "an E round ran and appended nothing"
    assert cov["declared_but_not_missing"] == {}
    assert cov["n_covered"] == cov["n_owed"]


def test_the_declared_holes_registry_is_empty_and_that_is_the_point():
    """Round 454 recovered seven of eight holes, so nothing needs
    declaring. The file exists as the mechanism, not as a list of excuses;
    if a future round adds an entry, it is asserting it looked for a
    transcript and found none."""
    assert rc.load_declared_holes() == {}



def test_the_module_does_not_care_what_order_the_log_file_is_in():
    """`state/nuc-reachability-log.jsonl` is append-only, and round 454
    appended eight RECOVERED rows whose `checked_at_utc` predate rows
    already in the file -- so file order is no longer chronological order,
    and will not be again. Every consumer sorts through `_sort_key`; this
    pins that, because the one place that did not (a test fixture deriving
    its window from `recs[-1]`) failed silently-looking and took an hour to
    read."""
    recs = rc.load_log(str(REAL_LOG))
    stamps = [r["checked_at_utc"] for r in recs]
    assert stamps != sorted(stamps), "file is chronological; this test is vacuous"
    a = rc.continuity_report(recs)
    b = rc.continuity_report(sorted(recs, key=rc._sort_key))
    c = rc.continuity_report(list(reversed(recs)))
    assert a == b == c


# --------------------------------------------------------------------------
# Round 460: the `precision` field, which the log has carried on every row
# since round 310 and which no rule had ever read.
# --------------------------------------------------------------------------

def test_a_coarse_row_brackets_its_check_instant_forward_by_a_minute():
    """`checked_at_utc` on a backfilled row is `boot + a minute-TRUNCATED
    uptime`, so it can only be an UNDERstatement. The bracket therefore opens
    at the stated value and runs forward, never backward."""
    lo, hi = rc.checked_at_bounds({"checked_at_utc": "2026-08-26T03:19:00Z",
                                   "precision": "coarse"})
    assert rc._fmt_ts(lo) == "2026-08-26T03:19:00Z"
    assert (hi - lo).total_seconds() == 60


def test_a_precise_row_is_still_a_bracket_not_a_point():
    lo, hi = rc.checked_at_bounds({"checked_at_utc": "2026-08-26T03:19:00Z",
                                   "precision": "precise"})
    assert (hi - lo).total_seconds() == 1


def test_a_row_that_does_not_declare_its_precision_gets_the_widest_bracket():
    """Fails closed. An unknown provenance must not be able to buy a witness
    or an accusation it has not earned."""
    lo, hi = rc.checked_at_bounds({"checked_at_utc": "2026-08-26T03:19:00Z"})
    assert (hi - lo).total_seconds() == rc.UNKNOWN_PRECISION_RESOLUTION_S
    assert rc.UNKNOWN_PRECISION_RESOLUTION_S == max(rc.PRECISION_RESOLUTION_S.values())


def test_the_headline_max_unobserved_outage_is_a_two_minute_bracket():
    """The live log's `max_unobserved_outage` is rounds 142 -> 154, printed as
    exactly `14h00m00s`. BOTH endpoints are `coarse`, so the true value is
    somewhere in a 120 s window and the round number is an artefact of two
    minute-truncated readings agreeing on their seconds field."""
    e = {"checked_at_utc": "2026-08-26T03:19:00Z", "precision": "coarse"}
    l = {"checked_at_utc": "2026-08-26T17:19:00Z", "precision": "coarse"}
    lo, hi = rc.gap_duration_bounds(e, l)
    assert (lo, hi) == (50340.0, 50460.0)
    assert hi - lo == 2 * rc.PRECISION_RESOLUTION_S["coarse"]
    assert lo < 50400.0 < hi


def test_a_coarse_earlier_check_cannot_manufacture_a_missed_excursion():
    """THE round 460 guard, in one test.

    A sighting 30 s after a COARSE earlier check is not inside the gap on any
    honest reading: the check's true instant is somewhere in the following
    60 s, so the sighting may well precede it. Read as a point -- which is
    what every rule did before this round -- it is an accusation that the box
    came back to life mid-outage.
    """
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1, precision="coarse"),
            _rec("2026-01-01T14:00:00Z", "down", 2, precision="precise",
                 last_seen="2026-01-01T10:00:30Z")]
    rep = rc.gap_continuity(recs)[0]
    assert rep["missed_excursions"] == []
    assert "straddles the earlier check" in rep["gaps"][0]["witness_note"]
    assert rep["gaps"][0]["witnessed"] is False


def test_the_same_sighting_against_a_precise_earlier_check_still_accuses():
    """The falsifier for the test above: the guard must be about PRECISION,
    not about refusing to accuse. Identical data, one field changed."""
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1, precision="precise"),
            _rec("2026-01-01T14:00:00Z", "down", 2, precision="precise",
                 last_seen="2026-01-01T10:00:30Z")]
    rep = rc.gap_continuity(recs)[0]
    assert len(rep["missed_excursions"]) == 1
    assert rep["missed_excursions"][0]["kind"] == "tailscale_last_seen_inside_gap"


def test_a_witness_survives_a_coarse_earlier_check_when_it_has_the_margin():
    """The guard must not eat honest witnesses. A sighting 42m before a coarse
    check clears the check's 60 s bracket with room to spare -- this is round
    190's real shape."""
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1, precision="coarse"),
            _rec("2026-01-01T14:00:00Z", "down", 2, precision="precise",
                 last_seen="2026-01-01T09:18:00Z")]
    gap = rc.gap_continuity(recs)[0]["gaps"][0]
    assert gap["witnessed"] is True
    assert gap["witness_source"] == "tailscale_last_seen"


def test_a_sighting_inside_the_earlier_checks_own_bracket_witnesses_nothing():
    """The other side of the same coin: a sighting 30 s after a coarse check
    cannot witness either, because it may fall inside the gap. Neither
    witness nor accusation -- the third outcome."""
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1, precision="coarse"),
            _rec("2026-01-01T14:00:00Z", "down", 2, precision="precise",
                 last_seen="2026-01-01T10:00:30Z")]
    gap = rc.gap_continuity(recs)[0]["gaps"][0]
    assert gap["witnessed"] is False
    assert gap["witness_strength"] == rc.WITNESS_NONE
    assert gap.get("witness_source") is None


def test_a_sighting_exactly_at_the_later_check_straddles_it():
    """Split out of round 334's contradiction test. The later check's true
    instant is at or after its stated one, so a sighting AT the stated value
    is at-or-before the real check -- no contradiction is established."""
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1, precision="precise"),
            _rec("2026-01-01T14:00:00Z", "down", 2, precision="precise",
                 last_seen="2026-01-01T14:00:00Z")]
    gap = rc.gap_continuity(recs)[0]["gaps"][0]
    assert gap["witnessed"] is False
    assert "straddles the later check" in gap["witness_note"]
    assert rc.gap_continuity(recs)[0]["missed_excursions"] == []


# --- bounded (interval-valued) LastSeen ------------------------------------

def test_a_bounded_last_seen_witnesses_on_its_UPPER_bound():
    """Round 454 item 4, done as a bracket rather than a division. A reading
    recovered from `last seen 3h ago` is an interval; it witnesses only when
    even its LATEST possible instant precedes the earlier check."""
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1, precision="precise"),
            _rec("2026-01-01T14:00:00Z", "down", 2, precision="precise",
                 last_seen_bounds=("2026-01-01T08:00:00Z", "2026-01-01T09:00:00Z"))]
    gap = rc.gap_continuity(recs)[0]["gaps"][0]
    assert gap["witnessed"] is True
    assert "[2026-01-01T08:00:00Z, 2026-01-01T09:00:00Z]" in gap["witness_note"]


def test_a_bounded_last_seen_that_reaches_past_the_earlier_check_witnesses_nothing():
    """The falsifier: move the interval's upper end 1 s past the earlier
    check and the witness must vanish. A bracket that is allowed to witness
    on its midpoint is a division wearing a bracket's clothes."""
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1, precision="precise"),
            _rec("2026-01-01T14:00:00Z", "down", 2, precision="precise",
                 last_seen_bounds=("2026-01-01T08:00:00Z", "2026-01-01T10:00:01Z"))]
    gap = rc.gap_continuity(recs)[0]["gaps"][0]
    assert gap["witnessed"] is False


def test_a_bounded_last_seen_never_accuses_on_a_straddle():
    """An interval that pokes out of the gap at either end proves nothing,
    and must not be collapsed to a point that does."""
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1, precision="precise"),
            _rec("2026-01-01T14:00:00Z", "down", 2, precision="precise",
                 last_seen_bounds=("2026-01-01T09:30:00Z", "2026-01-01T11:00:00Z"))]
    rep = rc.gap_continuity(recs)[0]
    assert rep["missed_excursions"] == []
    assert rep["gaps"][0]["witnessed"] is False


def test_a_bounded_last_seen_fully_inside_the_gap_does_accuse():
    """...and the falsifier for THAT: an interval wholly inside the gap is as
    good as a point inside it."""
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1, precision="precise"),
            _rec("2026-01-01T14:00:00Z", "down", 2, precision="precise",
                 last_seen_bounds=("2026-01-01T11:00:00Z", "2026-01-01T12:00:00Z"))]
    rep = rc.gap_continuity(recs)[0]
    assert len(rep["missed_excursions"]) == 1


def test_bounds_beat_the_scalar_field_when_a_row_carries_both():
    """A recovered row keeps `tailscale_last_seen_utc: null` for compatibility
    and carries the interval beside it. If some future row carries both, the
    interval is the one with the provenance."""
    rec = {"tailscale_last_seen_utc": "2026-01-01T12:00:00Z",
           "tailscale_last_seen_bounds_utc": ["2026-01-01T08:00:00Z",
                                              "2026-01-01T09:00:00Z"]}
    lo, hi = rc.last_seen_bounds(rec)
    assert (rc._fmt_ts(lo), rc._fmt_ts(hi)) == ("2026-01-01T08:00:00Z",
                                                "2026-01-01T09:00:00Z")


def test_the_never_seen_sentinel_is_not_a_bracket():
    assert rc.last_seen_bounds({"tailscale_last_seen_utc": "0001-01-01T00:00:00Z"}) is None
    assert rc.last_seen_bounds({}) is None


# --- the precision audit ---------------------------------------------------

def test_the_audit_finds_nothing_unearned_in_the_live_log_today():
    """The honest headline, as a pin. 20 of the live log's 60 rows are coarse
    and they carry 60% of its published ignorance -- and not one published
    conclusion currently rests on that coarseness. The guards added this round
    are PREVENTIVE. Saying so is the finding; if a later round makes this go
    red, the log has started drawing conclusions from rounded digits."""
    aud = rc.precision_audit(rc.load_log(str(REAL_LOG)))
    assert aud["unearned_claims"] == []
    assert aud["unearned_missed_excursions"] == []
    assert aud["by_precision"]["coarse"] == 20
    assert aud["gaps_with_a_coarse_endpoint"] == 23
    assert 0.60 < aud["unobserved_carried_by_coarse_endpoint_fraction"] < 0.61


def test_the_audit_catches_an_excursion_that_only_a_point_reading_supports():
    """The falsifier. A sighting 30 s after a COARSE check is an accusation
    under the old point-valued rules and nothing at all under the row's own
    declared precision. If the audit cannot see that, it is decorative."""
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1, precision="coarse"),
            _rec("2026-01-01T14:00:00Z", "down", 2, precision="precise",
                 last_seen="2026-01-01T10:00:30Z")]
    aud = rc.precision_audit(recs)
    assert aud["unearned_missed_excursions"] == [(1, 2)]
    assert len(aud["unearned_claims"]) == 0  # strength is NONE either way
    assert rc.main(["precision-audit", "--log-path", str(REAL_LOG), "--strict"]) == 0


def test_a_witness_is_immune_to_the_EARLIER_checks_precision_and_here_is_why():
    """Not a gap in the audit -- a property of the rule, and the reason
    `unearned_claims` is empty on the live log.

    Witnessing needs "the sighting is at or before the earlier check", which
    is evaluated against that check's LOWER bound -- and the lower bound IS
    the stated value, whatever the row's precision. Coarseness only ever opens
    a bracket FORWARD. So declaring the earlier check coarse cannot take a
    witness away, and cannot hand one over either.
    """
    for prec in ("precise", "coarse"):
        recs = [_rec("2026-01-01T10:00:00Z", "down", 1, precision=prec),
                _rec("2026-01-01T14:00:00Z", "down", 2, precision="precise",
                     last_seen="2026-01-01T10:00:00Z")]
        gap = rc.gap_continuity(recs)[0]["gaps"][0]
        assert gap["witnessed"] is True, prec
        assert rc.precision_audit(recs)["unearned_claims"] == []


def test_the_audit_catches_a_witness_that_only_a_point_reading_supports():
    """The error class that IS reachable, via round 454's forward rule.

    Gap 1->2 has no LastSeen on its later record, so it leans on a forward
    reading (round 3's 09:00, at or before check 1). Round 4 reports a
    sighting at 14:00:30 -- half a minute after check 2's STATED time. Read as
    a point, that sighting is outside gap 1->2 and the forward witness stands.
    Read against check 2's own declared coarseness, the sighting falls inside
    the gap's widest possible extent, the two readings dispute each other, and
    the witness is not earned.
    """
    recs = [_rec("2026-01-01T10:00:00Z", "down", 1, precision="precise"),
            _rec("2026-01-01T14:00:00Z", "down", 2, precision="coarse"),
            _rec("2026-01-01T18:00:00Z", "down", 3, precision="precise",
                 last_seen="2026-01-01T09:00:00Z"),
            _rec("2026-01-01T22:00:00Z", "down", 4, precision="precise",
                 last_seen="2026-01-01T14:00:30Z")]
    aud = rc.precision_audit(recs)
    assert [(r["from_round"], r["to_round"]) for r in aud["unearned_claims"]] == [(1, 2)]
    assert aud["unearned_claims"][0]["point_strength"] == rc.WITNESS_FULL
    assert aud["unearned_claims"][0]["live_strength"] == rc.WITNESS_NONE
    assert "disputed" in aud["unearned_claims"][0]["live_note"]


def test_the_point_view_reproduces_the_pre_round_460_rules_exactly():
    """`_as_points` must be the OLD behaviour, not a third one. Zero-width
    brackets make every comparison collapse back to the point form, and an
    interval-valued LastSeen -- which had no meaning at all before this round
    -- is dropped rather than averaged into a value the old code never saw."""
    r = {"checked_at_utc": "2026-01-01T10:00:00Z", "precision": "coarse",
         "tailscale_last_seen_bounds_utc": ["2026-01-01T08:00:00Z",
                                            "2026-01-01T09:00:00Z"]}
    pt = rc._as_points([r])[0]
    lo, hi = rc.checked_at_bounds(pt)
    assert lo == hi
    assert rc.last_seen_bounds(pt) is None
    assert r["precision"] == "coarse", "must not mutate the caller's records"


def test_the_headline_outage_argmax_is_robust_and_says_so():
    """`max_unobserved_outage` prints exactly `14h00m00s` from two
    minute-truncated endpoints. The number is an artefact; the RANKING is not,
    because the runner-up is nowhere near. The audit has to distinguish those
    two statements -- a bracket on a value is not a doubt about its order."""
    aud = rc.precision_audit(rc.load_log(str(REAL_LOG)))
    m = aud["max_unobserved_outage"]
    assert (m["from_round"], m["to_round"]) == (142, 154)
    assert m["printed_s"] == 50400.0
    assert m["bracket_human"] == "13h59m00s .. 14h01m00s"
    assert m["argmax_robust"] is True
    assert m["lo_s"] > m["runner_up_s"]


def test_an_argmax_inside_its_own_bracket_is_reported_as_not_robust():
    """The falsifier for that: two coarse gaps 30 s apart cannot be ordered."""
    recs = [_rec("2026-01-01T10:00:00Z", "up", 1, precision="coarse", boot="2026-01-01T00:00:00Z"),
            _rec("2026-01-01T11:00:00Z", "up", 2, precision="coarse"),
            _rec("2026-01-01T12:00:30Z", "up", 3, precision="coarse")]
    aud = rc.precision_audit(recs)
    assert aud["max_unobserved_outage"]["argmax_robust"] is False


# --------------------------------------------------------------------------
# Round 460 / round 454's item 3: the UP side of the split-gap regression.
# --------------------------------------------------------------------------

def _up_streak_ignorance(recs):
    rep = rc.gap_continuity(recs)
    return sum(g["unobserved_s"] for s in rep for g in s["gaps"])


def test_inserting_a_bootless_observation_no_longer_raises_up_side_ignorance():
    """THE exhibit round 454 declined to build, and the regression it names.

    A -- B share a boot, so the gap scores `reboot_only`. Insert an
    observation M that carries no boot_utc and, before this round, BOTH halves
    fell to WITNESS_NONE: making one more observation of the box made the
    instrument report more ignorance. Same shape as the down-side bug round
    454 fixed, on the other axis.
    """
    a = _rec("2026-01-01T10:00:00Z", "up", 1, boot="2026-01-01T00:00:00Z")
    m = _rec("2026-01-01T11:00:00Z", "up", 2)                       # no boot_utc
    b = _rec("2026-01-01T12:00:00Z", "up", 3, boot="2026-01-01T00:00:00Z")
    without, with_m = rc.gap_continuity([a, b]), rc.gap_continuity([a, m, b])
    assert [g["witness_strength"] for g in without[0]["gaps"]] == [rc.WITNESS_REBOOT_ONLY]
    assert [g["witness_strength"] for g in with_m[0]["gaps"]] == [
        rc.WITNESS_REBOOT_ONLY, rc.WITNESS_REBOOT_ONLY]
    assert [g["witness_source"] for g in with_m[0]["gaps"]] == [
        "boot_utc_unchanged_bracketed", "boot_utc_unchanged_bracketed"]
    # and the property the regression violated
    assert _up_streak_ignorance([a, m, b]) == _up_streak_ignorance([a, b])


def test_the_bracketed_boot_rule_may_witness_but_may_not_accuse():
    """Round 454's asymmetry, carried onto the up side. When the bracketing
    readings disagree a reboot DID happen somewhere in the span -- but the
    span holds several gaps and nothing says which, so no gap is accused."""
    a = _rec("2026-01-01T10:00:00Z", "up", 1, boot="2026-01-01T00:00:00Z")
    m = _rec("2026-01-01T11:00:00Z", "up", 2)
    b = _rec("2026-01-01T12:00:00Z", "up", 3, boot="2026-01-01T09:00:00Z")
    rep = rc.gap_continuity([a, m, b])[0]
    assert [g["witness_strength"] for g in rep["gaps"]] == [rc.WITNESS_NONE,
                                                            rc.WITNESS_NONE]
    assert rep["missed_excursions"] == []
    assert "only part of it" in rep["gaps"][0]["witness_note"]


def test_the_bracketed_rule_needs_a_reading_on_BOTH_sides():
    """A bracket open at one end brackets nothing. Two half-cases, both NONE."""
    a = _rec("2026-01-01T10:00:00Z", "up", 1, boot="2026-01-01T00:00:00Z")
    m = _rec("2026-01-01T11:00:00Z", "up", 2)
    n = _rec("2026-01-01T12:00:00Z", "up", 3)
    assert rc.gap_continuity([a, m, n])[0]["gaps"][1]["witness_strength"] == rc.WITNESS_NONE
    assert rc.gap_continuity([n, m, a][::-1])  # smoke: ordering does not crash
    b = _rec("2026-01-01T13:00:00Z", "up", 4, boot="2026-01-01T00:00:00Z")
    first = _rec("2026-01-01T09:00:00Z", "up", 0)
    assert rc.gap_continuity([first, m, b])[0]["gaps"][0]["witness_strength"] == rc.WITNESS_NONE


def test_boot_jitter_applies_to_the_bracket_too():
    """The bracket is the same claim `boot_utc_unchanged` makes over a wider
    span, so it inherits round 376's 5 s same-boot sampling tolerance."""
    a = _rec("2026-01-01T10:00:00Z", "up", 1, boot="2026-01-01T00:00:00Z")
    m = _rec("2026-01-01T11:00:00Z", "up", 2)
    b = _rec("2026-01-01T12:00:00Z", "up", 3, boot="2026-01-01T00:00:04Z")
    assert rc.gap_continuity([a, m, b])[0]["gaps"][0]["witness_strength"] == \
        rc.WITNESS_REBOOT_ONLY
    b["boot_utc"] = "2026-01-01T00:00:06Z"        # past the tolerance
    assert rc.gap_continuity([a, m, b])[0]["gaps"][0]["witness_strength"] == rc.WITNESS_NONE


def test_a_bracketed_gap_is_reachable_by_the_journal_interior_upgrade():
    """Why the upgrade is worth anything. `_silence_upgrade` is keyed on
    REBOOT_ONLY, so a gap stuck at NONE could never be bounded no matter what
    journal evidence arrived. These seven can be."""
    a = _rec("2026-01-01T10:00:00Z", "up", 1, boot="2026-01-01T00:00:00Z")
    m = _rec("2026-01-01T11:00:00Z", "up", 2)
    b = _rec("2026-01-01T12:00:00Z", "up", 3, boot="2026-01-01T00:00:00Z")
    silence = lambda t1, t2: {"max_silence_s": 30.0, "n_entry_seconds": 1000}
    gap = rc.gap_continuity([a, m, b], silence=silence)[0]["gaps"][0]
    assert gap["witness_strength"] == rc.WITNESS_BOUNDED
    assert gap["witness_source"] == "boot_utc_unchanged_bracketed+journal"
    assert gap["bound_s"] == 30.0


def test_the_live_log_gains_seven_bracketed_gaps_and_no_headline_number_moves():
    """The honest live result. Rounds 202/220/226/250 all report boot
    `2026-08-27T11:50:48Z` -- the same boot, to the second -- and the five
    coarse rows between them carry no boot_utc at all. Seven gaps therefore go
    from 'boot_utc missing on one or both endpoints' to 'no reboot happened
    anywhere in the span'. `unobserved_total_s` does NOT move, because
    REBOOT_ONLY has never reduced it; what moves is that 16h49m of the log's
    ignorance is now one journal capture away from a bound instead of being
    permanently out of reach."""
    rep = rc.gap_continuity(rc.load_log(str(REAL_LOG)))
    bracketed = [g for s in rep for g in s["gaps"]
                 if g["witness_source"] == "boot_utc_unchanged_bracketed"]
    assert len(bracketed) == 7
    assert [(g["from_round"], g["to_round"]) for g in bracketed] == [
        (202, 208), (208, 214), (214, 220), (226, 232), (232, 238),
        (238, 244), (244, 250)]
    assert sum(g["unobserved_s"] for g in bracketed) == 60528.0
    assert all(g["witness_strength"] == rc.WITNESS_REBOOT_ONLY for g in bracketed)
    full = rc.continuity_report(rc.load_log(str(REAL_LOG)))
    assert full["unobserved_total_s"] == 396378.0
