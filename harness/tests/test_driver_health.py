"""Tests for driver_health.py — see that module's docstring for the bug
(macOS BSD xargs silently ate the 3-consecutive-failure safety check in
run_driver.sh) this replaces.
"""

import json
import os
import subprocess
import sys

import pytest

from harness.driver_health import (
    RATE_LIMIT_BACKOFF_SCHEDULE,
    classify_round_log,
    count_consecutive_failures,
    exact_reset_wait_seconds,
    is_5xx,
    is_rate_limit,
    latest_rate_limit_reset_epoch,
    load_round_result,
    main,
    rate_limit_backoff_seconds,
    resolved_wait_seconds,
    round_status_text,
    round_succeeded,
    summarize_turns,
)

HERE = os.path.dirname(__file__)


def _write(tmp_path, name, content):
    p = os.path.join(tmp_path, name)
    if isinstance(content, str):
        with open(p, "w") as f:
            f.write(content)
    else:
        with open(p, "w") as f:
            json.dump(content, f)
    return p


def _write_ndjson(tmp_path, name, lines):
    """Write a stream-json-shaped log: one JSON object per line."""
    p = os.path.join(tmp_path, name)
    with open(p, "w") as f:
        for obj in lines:
            f.write(json.dumps(obj) + "\n")
    return p


def test_success_is_ok(tmp_path):
    p = _write(str(tmp_path), "a.json", {"is_error": False, "subtype": "success"})
    assert classify_round_log(p) == "ok"


def test_max_turns_error_is_bad(tmp_path):
    p = _write(str(tmp_path), "a.json", {"is_error": True, "subtype": "error_max_turns"})
    assert classify_round_log(p) == "bad"


def test_429_is_bad(tmp_path):
    p = _write(str(tmp_path), "a.json", {"is_error": True, "api_error_status": 429})
    assert classify_round_log(p) == "bad"


def test_5xx_status_is_ok_not_bad(tmp_path):
    # 5xx/529 is handled by the driver's own retry-with-backoff branch and
    # must not ALSO count toward the consecutive-failure stop.
    p = _write(str(tmp_path), "a.json", {"is_error": True, "api_error_status": 503})
    assert classify_round_log(p) == "ok"


def test_529_in_result_text_is_ok(tmp_path):
    p = _write(str(tmp_path), "a.json", {"is_error": True, "result": "overloaded_error: 529"})
    assert classify_round_log(p) == "ok"


def test_empty_file_is_bad(tmp_path):
    # A round still mid-flight (`> log 2>&1` truncates to 0 bytes at start)
    # must read as "bad", not crash the classifier and not silently pass.
    p = os.path.join(str(tmp_path), "empty.json")
    open(p, "w").close()
    assert classify_round_log(p) == "bad"


def test_missing_file_is_bad(tmp_path):
    p = os.path.join(str(tmp_path), "does-not-exist.json")
    assert classify_round_log(p) == "bad"


def test_malformed_json_is_bad(tmp_path):
    p = _write(str(tmp_path), "a.json", "{not json")
    assert classify_round_log(p) == "bad"


def test_count_consecutive_failures_mixed(tmp_path):
    good = _write(str(tmp_path), "g.json", {"is_error": False})
    bad1 = _write(str(tmp_path), "b1.json", {"is_error": True, "api_error_status": 429})
    bad2 = _write(str(tmp_path), "b2.json", {"is_error": True, "subtype": "error_max_turns"})
    assert count_consecutive_failures([bad1, bad2, good]) == 2
    assert count_consecutive_failures([good, good]) == 0
    assert count_consecutive_failures([bad1, bad2]) == 2


def test_count_consecutive_failures_empty_list():
    assert count_consecutive_failures([]) == 0


def test_reproduces_the_actual_round_113_to_126_run(tmp_path):
    """Regression pin: the exact three-429 and three-max-turns stretches
    from logs/round-*.json (round 113-121, 122-126) that the broken xargs
    pipeline in run_driver.sh missed both times. Frozen copies, not reads
    of the live logs directory, so this stays a pin even if those files
    are pruned or the live driver runs further."""
    stretch_429 = [
        {"is_error": True, "api_error_status": 429, "subtype": "success"},
        {"is_error": True, "api_error_status": 429, "subtype": "success"},
        {"is_error": True, "api_error_status": 429, "subtype": "success"},
    ]
    stretch_max_turns = [
        {"is_error": True, "subtype": "error_max_turns"},
        {"is_error": True, "subtype": "error_max_turns"},
        {"is_error": True, "subtype": "error_max_turns"},
    ]
    for stretch in (stretch_429, stretch_max_turns):
        paths = [_write(str(tmp_path), "s%d.json" % i, d) for i, d in enumerate(stretch)]
        assert count_consecutive_failures(paths) == 3


def test_is_rate_limit_true_for_429(tmp_path):
    p = _write(str(tmp_path), "a.json", {"is_error": True, "api_error_status": 429})
    assert is_rate_limit(p) is True


def test_is_rate_limit_false_for_5xx(tmp_path):
    p = _write(str(tmp_path), "a.json", {"is_error": True, "api_error_status": 503})
    assert is_rate_limit(p) is False


def test_is_rate_limit_false_for_max_turns(tmp_path):
    p = _write(str(tmp_path), "a.json", {"is_error": True, "subtype": "error_max_turns"})
    assert is_rate_limit(p) is False


def test_is_rate_limit_false_on_missing_or_malformed(tmp_path):
    assert is_rate_limit(os.path.join(str(tmp_path), "nope.json")) is False
    p = _write(str(tmp_path), "bad.json", "{not json")
    assert is_rate_limit(p) is False


def test_reproduces_actual_round_114_429_shape(tmp_path):
    # Frozen shape of the real logs/round-114.json (a live 429 this driver
    # failed to notice, per this module's docstring).
    p = _write(str(tmp_path), "r114.json", {
        "is_error": True, "subtype": "success", "api_error_status": 429,
        "result": "You've reached your Fable 5 limit. Switch to another "
                   "model, or manage usage credits at claude.ai/settings/"
                   "usage?from=cc_cli_limit_message, to continue.",
    })
    assert is_rate_limit(p) is True
    assert classify_round_log(p) == "bad"  # true absent the driver's own retry-first handling


def test_rate_limit_backoff_seconds_schedule():
    assert rate_limit_backoff_seconds(1) == 300
    assert rate_limit_backoff_seconds(2) == 900
    assert rate_limit_backoff_seconds(3) == 1800
    assert rate_limit_backoff_seconds(4) == 3600
    assert rate_limit_backoff_seconds(len(RATE_LIMIT_BACKOFF_SCHEDULE)) == 3600


def test_rate_limit_backoff_seconds_clamps_below_and_above_schedule():
    assert rate_limit_backoff_seconds(0) == rate_limit_backoff_seconds(1)
    assert rate_limit_backoff_seconds(-5) == rate_limit_backoff_seconds(1)
    assert rate_limit_backoff_seconds(999) == RATE_LIMIT_BACKOFF_SCHEDULE[-1]


def test_rate_limit_backoff_total_matches_five_hour_rolling_window():
    total = sum(rate_limit_backoff_seconds(i) for i in range(1, len(RATE_LIMIT_BACKOFF_SCHEDULE) + 1))
    assert 4 * 3600 <= total <= 5 * 3600


def test_cli_backoff_subcommand(tmp_path):
    out = subprocess.run(
        [sys.executable, "-m", "harness.driver_health", "backoff", "2"],
        cwd=os.path.join(HERE, "..", ".."),
        capture_output=True, text=True, timeout=10,
    )
    assert out.returncode == 0
    assert out.stdout.strip() == "900"


def test_cli_backoff_subcommand_bad_arity():
    rc = main(["backoff"])
    assert rc == 2
    rc = main(["backoff", "1", "2"])
    assert rc == 2


# --- stream-json (round 133+) shape support -------------------------------

REAL_INIT_LINE = {
    "type": "system", "subtype": "init", "session_id": "943a6152",
    "model": "claude-sonnet-5",
}
# Pinned verbatim from a real `claude -p --output-format stream-json
# --verbose` call made live 2026-08-26 (see driver_health.py's
# `latest_rate_limit_reset_epoch` docstring) — resetsAt decoded against
# wall-clock `now` at capture time to confirm epoch SECONDS, not guessed.
REAL_RATE_LIMIT_LINE = {
    "type": "rate_limit_event",
    "rate_limit_info": {
        "status": "allowed",
        "unifiedWindows": {
            "five_hour": {"utilization": 0.01, "resetsAt": 1787723400},
            "seven_day": {"utilization": 0.64, "resetsAt": 1787954400},
        },
    },
    "session_id": "943a6152",
}
REAL_ASSISTANT_LINE = {
    "type": "assistant",
    "message": {
        "model": "claude-sonnet-5", "role": "assistant",
        "content": [{"type": "text", "text": "pong"}],
        "usage": {"output_tokens": 4, "output_tokens_details": {"thinking_tokens": 0}},
    },
    "timestamp": "2026-08-26T01:04:12.933Z",
}
REAL_RESULT_LINE = {
    "type": "result", "is_error": False, "subtype": "success",
    "num_turns": 1, "result": "pong", "api_error_status": None,
    "total_cost_usd": 0.049,
}


def test_load_round_result_plain_json_shape(tmp_path):
    p = _write(str(tmp_path), "a.json", {"is_error": False, "subtype": "success"})
    assert load_round_result(p) == {"is_error": False, "subtype": "success"}


def test_load_round_result_stream_json_shape_takes_last_result_line(tmp_path):
    p = _write_ndjson(str(tmp_path), "a.json",
                       [REAL_INIT_LINE, REAL_RATE_LIMIT_LINE, REAL_ASSISTANT_LINE, REAL_RESULT_LINE])
    assert load_round_result(p) == REAL_RESULT_LINE


def test_load_round_result_missing_file(tmp_path):
    assert load_round_result(os.path.join(str(tmp_path), "nope.json")) is None


def test_load_round_result_no_result_line(tmp_path):
    p = _write_ndjson(str(tmp_path), "a.json", [REAL_INIT_LINE, REAL_ASSISTANT_LINE])
    assert load_round_result(p) is None


def test_classify_and_rate_limit_work_on_stream_json_shape(tmp_path):
    ok = _write_ndjson(str(tmp_path), "ok.json", [REAL_INIT_LINE, REAL_ASSISTANT_LINE, REAL_RESULT_LINE])
    assert classify_round_log(ok) == "ok"
    assert is_rate_limit(ok) is False

    err_429 = dict(REAL_RESULT_LINE, is_error=True, api_error_status=429, subtype="success")
    bad = _write_ndjson(str(tmp_path), "bad.json", [REAL_INIT_LINE, err_429])
    assert classify_round_log(bad) == "bad"
    assert is_rate_limit(bad) is True


def test_round_succeeded_and_status_text(tmp_path):
    ok = _write(str(tmp_path), "ok.json", {"is_error": False, "subtype": "success"})
    assert round_succeeded(ok) is True
    assert round_status_text(ok) == "success"

    err = _write(str(tmp_path), "err.json", {"is_error": True, "api_error_status": 429})
    assert round_succeeded(err) is False
    assert round_status_text(err) == "error:429"

    missing = os.path.join(str(tmp_path), "missing.json")
    assert round_succeeded(missing) is False
    assert round_status_text(missing) == "?"


def test_is_5xx_status_and_result_text(tmp_path):
    p1 = _write(str(tmp_path), "a.json", {"is_error": True, "api_error_status": 503})
    assert is_5xx(p1) is True
    p2 = _write(str(tmp_path), "b.json", {"is_error": True, "result": "overloaded_error: 529"})
    assert is_5xx(p2) is True
    p3 = _write(str(tmp_path), "c.json", {"is_error": True, "api_error_status": 429})
    assert is_5xx(p3) is False


def test_latest_rate_limit_reset_epoch_finds_five_hour_window(tmp_path):
    p = _write_ndjson(str(tmp_path), "a.json", [REAL_INIT_LINE, REAL_RATE_LIMIT_LINE])
    assert latest_rate_limit_reset_epoch(p, window="five_hour") == 1787723400
    assert latest_rate_limit_reset_epoch(p, window="seven_day") == 1787954400


def test_latest_rate_limit_reset_epoch_uses_the_most_recent_event(tmp_path):
    older = dict(REAL_RATE_LIMIT_LINE)
    newer = {
        "type": "rate_limit_event",
        "rate_limit_info": {"unifiedWindows": {"five_hour": {"resetsAt": 1787730000}}},
    }
    p = _write_ndjson(str(tmp_path), "a.json", [older, newer])
    assert latest_rate_limit_reset_epoch(p, window="five_hour") == 1787730000


def test_latest_rate_limit_reset_epoch_none_on_plain_json(tmp_path):
    p = _write(str(tmp_path), "a.json", {"is_error": True, "api_error_status": 429})
    assert latest_rate_limit_reset_epoch(p) is None


def test_exact_reset_wait_seconds_computes_delta_and_clamps(tmp_path):
    p = _write_ndjson(str(tmp_path), "a.json", [REAL_RATE_LIMIT_LINE])
    now = 1787723400 - 500  # 500s before the real reset time
    assert exact_reset_wait_seconds(p, now=now) == 500
    # already past reset -> clamps to the floor, never a zero/negative sleep
    assert exact_reset_wait_seconds(p, now=1787723400 + 999) == 30
    # far-future event (bad clock/window) -> clamps to the ceiling
    assert exact_reset_wait_seconds(p, now=1787723400 - 100000) == 7200


def test_exact_reset_wait_seconds_none_when_no_event(tmp_path):
    p = _write(str(tmp_path), "a.json", {"is_error": True, "api_error_status": 429})
    assert exact_reset_wait_seconds(p) is None


def test_resolved_wait_seconds_prefers_exact_over_guess(tmp_path):
    p = _write_ndjson(str(tmp_path), "a.json", [REAL_RATE_LIMIT_LINE])
    now = 1787723400 - 120
    assert resolved_wait_seconds(p, attempt=1, now=now) == 120  # not 300 (schedule attempt 1)


def test_resolved_wait_seconds_falls_back_to_schedule_without_event(tmp_path):
    p = _write(str(tmp_path), "a.json", {"is_error": True, "api_error_status": 429})
    assert resolved_wait_seconds(p, attempt=1) == rate_limit_backoff_seconds(1)
    assert resolved_wait_seconds(p, attempt=4) == rate_limit_backoff_seconds(4)


def test_summarize_turns_counts_thinking_tokens_and_tool_calls(tmp_path):
    turn2 = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "thinking..."},
                {"type": "tool_use", "name": "Read", "input": {}},
                {"type": "tool_use", "name": "Bash", "input": {}},
            ],
            "usage": {"output_tokens_details": {"thinking_tokens": 150}},
        },
        "timestamp": "2026-08-26T01:04:20.000Z",
    }
    p = _write_ndjson(str(tmp_path), "a.json", [REAL_INIT_LINE, REAL_ASSISTANT_LINE, turn2, REAL_RESULT_LINE])
    s = summarize_turns(p)
    assert s["assistant_turns"] == 2
    assert s["thinking_tokens"] == 150
    assert s["tool_calls"] == 2
    assert s["span_s"] == pytest.approx(7.067, abs=0.01)


def test_summarize_turns_falls_back_to_result_aggregate_thinking_tokens(tmp_path):
    """Pins round 145's fix: real production stream-json logs (round-140
    through round-144 on disk, verified live) never put
    `output_tokens_details` on a per-turn `assistant` event's `usage` at
    all — the per-turn sum is always 0 even when the round did real
    thinking — but the final `result` event's aggregate usage DOES carry
    the true total. Turn shape below is copied field-for-field from a real
    `logs/round-140.json` assistant event (no `output_tokens_details`
    key), unlike `REAL_ASSISTANT_LINE` above which was a trivial
    ping/pong call that never exercised this gap.
    """
    real_shape_turn = {
        "type": "assistant",
        "message": {
            "model": "claude-sonnet-5", "role": "assistant",
            "content": [{"type": "thinking", "thinking": "", "signature": "x"}],
            "usage": {
                "input_tokens": 2, "cache_creation_input_tokens": 11283,
                "cache_read_input_tokens": 26138,
                "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 11283},
                "output_tokens": 2, "service_tier": "standard",
                "inference_geo": "not_available",
            },
        },
        "timestamp": "2026-08-26T02:41:01.631Z",
    }
    result_with_usage = dict(
        REAL_RESULT_LINE,
        usage={"output_tokens_details": {"thinking_tokens": 33773}},
    )
    p = _write_ndjson(str(tmp_path), "a.json", [REAL_INIT_LINE, real_shape_turn, result_with_usage])
    s = summarize_turns(p)
    assert s["assistant_turns"] == 1
    assert s["thinking_tokens"] == 33773  # not 0 — the pre-fix bug's reading


def test_summarize_turns_none_on_plain_json_shape(tmp_path):
    p = _write(str(tmp_path), "a.json", {"is_error": False, "subtype": "success"})
    assert summarize_turns(p) is None


def test_summarize_turns_none_on_missing_file(tmp_path):
    assert summarize_turns(os.path.join(str(tmp_path), "nope.json")) is None


def test_cli_success_status_is5xx_wait_summary_subcommands(tmp_path):
    ok = _write(str(tmp_path), "ok.json", {"is_error": False, "subtype": "success"})
    err = _write(str(tmp_path), "err.json", {"is_error": True, "api_error_status": 503})
    stream = _write_ndjson(str(tmp_path), "s.json",
                            [REAL_INIT_LINE, REAL_RATE_LIMIT_LINE, REAL_ASSISTANT_LINE, REAL_RESULT_LINE])

    def run(*args):
        out = subprocess.run(
            [sys.executable, "-m", "harness.driver_health", *args],
            cwd=os.path.join(HERE, "..", ".."), capture_output=True, text=True, timeout=10,
        )
        assert out.returncode == 0, out.stderr
        return out.stdout.strip()

    assert run("success", ok) == "yes"
    assert run("success", err) == "no"
    assert run("status", err) == "error:503"
    assert run("is5xx", err) == "yes"
    assert run("is5xx", ok) == "no"
    # `wait` uses the REAL wall clock (no `now=` override at the CLI layer),
    # and the fixture's resetsAt is a fixed past timestamp by the time this
    # runs, so only the clamped bounds are deterministic here — the exact
    # arithmetic is already pinned against a fixed `now` in the unit tests
    # above (test_exact_reset_wait_seconds_computes_delta_and_clamps).
    wait_out = int(run("wait", stream, "1"))
    assert 30 <= wait_out <= 7200
    assert run("summary", stream) == json.dumps(summarize_turns(stream))
    assert run("summary", ok) == "n/a"


def test_cli_matches_library(tmp_path):
    """The `python3 -m harness.driver_health <paths...>` entry point
    run_driver.sh actually shells out to — proves the CLI wiring, not just
    the importable function, works end to end (no xargs involved)."""
    p1 = _write(str(tmp_path), "a.json", {"is_error": True, "api_error_status": 429})
    p2 = _write(str(tmp_path), "b.json", {"is_error": False})
    out = subprocess.run(
        [sys.executable, "-m", "harness.driver_health", p1, p2],
        cwd=os.path.join(HERE, "..", ".."),
        capture_output=True, text=True, timeout=10,
    )
    assert out.returncode == 0
    assert out.stdout.strip() == "1"
