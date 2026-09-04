"""Tests for driver_health.py — see that module's docstring for the bug
(macOS BSD xargs silently ate the 3-consecutive-failure safety check in
run_driver.sh) this replaces.
"""

import json
import os
import subprocess
import sys
import unittest
import tempfile
import shutil

import pytest

from harness import driver_health
from harness.driver_health import (
    RATE_LIMIT_BACKOFF_SCHEDULE,
    all_max_turns,
    MEASURED_END_SENTINEL,
    classify_health_log,
    split_measured_output,
    blocking_wait_gap_s,
    classify_round_log,
    count_consecutive_failures,
    exact_reset_wait_seconds,
    full_event_span_s,
    health_log_line,
    has_real_ratelimit_signal,
    heavy_light_fail_rates,
    is_5xx,
    is_blocking_wait_kill,
    is_max_turns,
    is_rate_limit,
    last_assistant_tool_use,
    latest_rate_limit_reset_epoch,
    likely_timeout_kill,
    load_round_result,
    main,
    rate_limit_backoff_seconds,
    resolved_wait_seconds,
    round_status_text,
    round_succeeded,
    summarize_turns,
    split_sessions,
    turn_budget,
    headroom,
    _span_seconds,
    tally_by_track,
    track_name_for_round,
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


def test_summarize_turns_marks_interrupted_when_no_result_event(tmp_path):
    """Round 163's fix, found live on round-162's own log: a session
    killed mid-round (SIGKILL/OOM/outer timeout) never writes a `result`
    event, so the round-145 result-aggregate fallback has nothing to fall
    back to and `thinking_tokens` reads 0 — indistinguishable from the
    pre-145 bug by the number alone. `interrupted=True` names the real
    cause so a future round doesn't misread this as a fix regression.
    """
    p = _write_ndjson(str(tmp_path), "a.json", [REAL_INIT_LINE, REAL_ASSISTANT_LINE])
    s = summarize_turns(p)
    assert s["interrupted"] is True
    assert s["thinking_tokens"] == 0


def test_summarize_turns_not_interrupted_on_clean_result(tmp_path):
    p = _write_ndjson(str(tmp_path), "a.json", [REAL_INIT_LINE, REAL_ASSISTANT_LINE, REAL_RESULT_LINE])
    s = summarize_turns(p)
    assert s["interrupted"] is False


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


# --- round 151: max-turns must not be conflated with a quota/outage stop --

def test_status_text_reports_max_turns_not_generic_err(tmp_path):
    p = _write(str(tmp_path), "a.json", {"is_error": True, "subtype": "error_max_turns"})
    assert round_status_text(p) == "error:max_turns"


def test_is_max_turns_true_only_for_error_max_turns_subtype(tmp_path):
    mt = _write(str(tmp_path), "mt.json", {"is_error": True, "subtype": "error_max_turns"})
    other = _write(str(tmp_path), "other.json", {"is_error": True, "api_error_status": 429})
    ok = _write(str(tmp_path), "ok.json", {"is_error": False, "subtype": "success"})
    missing = os.path.join(str(tmp_path), "missing.json")
    assert is_max_turns(mt) is True
    assert is_max_turns(other) is False
    assert is_max_turns(ok) is False
    assert is_max_turns(missing) is False


def test_all_max_turns_true_only_when_every_log_is_a_max_turns_death(tmp_path):
    mt1 = _write(str(tmp_path), "mt1.json", {"is_error": True, "subtype": "error_max_turns"})
    mt2 = _write(str(tmp_path), "mt2.json", {"is_error": True, "subtype": "error_max_turns"})
    mt3 = _write(str(tmp_path), "mt3.json", {"is_error": True, "subtype": "error_max_turns"})
    err429 = _write(str(tmp_path), "e.json", {"is_error": True, "api_error_status": 429})
    ok = _write(str(tmp_path), "ok.json", {"is_error": False, "subtype": "success"})

    assert all_max_turns([mt1, mt2, mt3]) is True
    # a mix (one real error alongside max-turns deaths) must NOT read as an
    # all-workload cluster — the safety valve should still stop for this one
    assert all_max_turns([mt1, mt2, err429]) is False
    # a successful round in the window means there is no 3-failure cluster
    # at all in the first place, but the predicate itself must still say
    # False rather than accidentally True
    assert all_max_turns([mt1, ok, mt3]) is False
    assert all_max_turns([]) is False


def test_all_max_turns_reproduces_the_actual_round_146_to_150_pattern(tmp_path):
    """Regression pin: rounds 146/147 (then 149/150 on a second restart)
    were each a genuine `error_max_turns` death after 140-160 real turns of
    work, not a quota/outage — `all_max_turns` must certify a cluster shaped
    exactly like that so `run_driver.sh` does not stop the whole program on
    it, matching CURRICULUM.md's "stop only when the WEEKLY limit is
    reached." Frozen shapes, not reads of the live logs directory."""
    stretch = [
        {"is_error": True, "subtype": "error_max_turns", "num_turns": 81,
         "stop_reason": "tool_use"},
        {"is_error": True, "subtype": "error_max_turns", "num_turns": 81,
         "stop_reason": "tool_use"},
        {"is_error": True, "subtype": "error_max_turns", "num_turns": 81,
         "stop_reason": "tool_use"},
    ]
    paths = [_write(str(tmp_path), "r%d.json" % i, d) for i, d in enumerate(stretch)]
    assert count_consecutive_failures(paths) == 3  # still counts as "bad"...
    assert all_max_turns(paths) is True            # ...but is certified all-workload


def test_has_real_ratelimit_signal_true_for_structured_429(tmp_path):
    p = _write(str(tmp_path), "a.json", {"is_error": True, "api_error_status": 429})
    assert has_real_ratelimit_signal(p) is True


def test_has_real_ratelimit_signal_true_for_high_utilization_event(tmp_path):
    high_util = dict(REAL_RATE_LIMIT_LINE)
    high_util["rate_limit_info"] = {
        "status": "allowed",
        "unifiedWindows": {"five_hour": {"utilization": 0.95, "resetsAt": 1787723400}},
    }
    p = _write_ndjson(str(tmp_path), "a.json", [REAL_INIT_LINE, high_util, REAL_RESULT_LINE])
    assert has_real_ratelimit_signal(p) is True


def test_has_real_ratelimit_signal_false_for_low_utilization_or_prose(tmp_path):
    # a normal round's routine, low-utilization telemetry event...
    ok = _write_ndjson(str(tmp_path), "ok.json",
                        [REAL_INIT_LINE, REAL_RATE_LIMIT_LINE, REAL_ASSISTANT_LINE, REAL_RESULT_LINE])
    assert has_real_ratelimit_signal(ok) is False

    # ...and text that merely MENTIONS rate limits (e.g. a round reading
    # research-state.md's own history, or this module's docstrings) must
    # not trip the structured check the way the old blind grep did.
    prose_line = {
        "type": "assistant",
        "message": {"role": "assistant", "content": [
            {"type": "text", "text": "Discussing the weekly limit and 5-hour "
                                      "rolling rate limit / usage_policies..."}]},
    }
    prosy = _write_ndjson(str(tmp_path), "prosy.json", [REAL_INIT_LINE, prose_line, REAL_RESULT_LINE])
    assert has_real_ratelimit_signal(prosy) is False


def test_cli_is_max_turns_and_all_max_turns_and_ratelimit_signal(tmp_path):
    mt = _write(str(tmp_path), "mt.json", {"is_error": True, "subtype": "error_max_turns"})
    ok = _write(str(tmp_path), "ok.json", {"is_error": False, "subtype": "success"})

    def run(*args):
        out = subprocess.run(
            [sys.executable, "-m", "harness.driver_health"] + list(args),
            cwd=os.path.join(HERE, "..", ".."),
            capture_output=True, text=True, timeout=10,
        )
        assert out.returncode == 0, out.stderr
        return out.stdout.strip()

    assert run("is_max_turns", mt) == "yes"
    assert run("is_max_turns", ok) == "no"
    assert run("all_max_turns", mt, mt, mt) == "yes"
    assert run("all_max_turns", mt, ok, mt) == "no"
    assert run("ratelimit_signal", ok) == "no"


# --- full_event_span_s / likely_timeout_kill (round 211) -------------------
#
# Round 210's own log (no `result` event) is the motivating case: driver.log
# shows a ~3301s wall-clock gap between its "start" and "turn summary" lines
# (essentially the full 3300s `DRIVER_ROUND_TIMEOUT_S`), but
# `summarize_turns`'s `span_s` — which only walks `type: "assistant"`
# timestamps — read 3174.154, ~123s short, because non-assistant events
# (system/tool_progress/user) preceded the first assistant turn and trailed
# the last one. `full_event_span_s` fixes that by spanning every timestamped
# event regardless of type; `likely_timeout_kill` uses it to tell a
# near-ceiling kill apart from a genuine early crash.

def test_full_event_span_s_uses_all_timestamped_events_not_just_assistant(tmp_path):
    system_no_ts = {"type": "system", "subtype": "init"}  # no timestamp, like REAL_INIT_LINE
    first = dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T17:22:04.850Z")
    # a non-assistant event with a timestamp LATER than the last assistant
    # turn — this is what round 210's real log looked like (a
    # `task_updated`/`killed` system event right before the final,
    # truncated assistant message).
    late_system = {"type": "system", "subtype": "task_updated",
                   "timestamp": "2026-08-27T18:17:00.000Z"}
    last_assistant = dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T18:17:01.596Z")
    p = _write_ndjson(str(tmp_path), "a.json", [system_no_ts, first, late_system, last_assistant])
    span = full_event_span_s(p)
    assert span == pytest.approx(3296.746, abs=0.01)
    # summarize_turns's own span_s (assistant-only) is the SAME here since
    # the latest timestamp happens to also be an assistant event — the
    # divergence only shows up when a later NON-assistant event trails the
    # last assistant one, which is exactly what round 210 had and this
    # fixture's `late_system` (with an earlier timestamp than the final
    # assistant line) does not reproduce; see the dedicated regression test
    # below for the real shape.


def test_full_event_span_s_can_exceed_assistant_only_span(tmp_path):
    first = dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T17:22:04.850Z")
    last_assistant = dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T18:15:00.000Z")
    # a trailing non-assistant event (e.g. a killed-background-task
    # notification) with a LATER timestamp than the final assistant turn —
    # this is round 210's actual shape.
    trailing_system = {"type": "system", "subtype": "task_updated",
                        "timestamp": "2026-08-27T18:17:01.000Z"}
    p = _write_ndjson(str(tmp_path), "a.json", [first, last_assistant, trailing_system])
    s = summarize_turns(p)
    full_span = full_event_span_s(p)
    assert s["span_s"] < full_span
    assert full_span == pytest.approx(3296.15, abs=0.01)


def test_full_event_span_s_none_below_two_timestamps(tmp_path):
    p = _write_ndjson(str(tmp_path), "a.json", [{"type": "system", "subtype": "init"}])
    assert full_event_span_s(p) is None


def test_full_event_span_s_none_on_missing_file(tmp_path):
    assert full_event_span_s(os.path.join(str(tmp_path), "nope.json")) is None


def test_likely_timeout_kill_true_when_span_near_ceiling(tmp_path):
    first = dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T17:22:04.850Z")
    last = dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T18:17:01.596Z")
    p = _write_ndjson(str(tmp_path), "a.json", [first, last])  # no result event
    assert likely_timeout_kill(p, timeout_s=3300) is True


def test_likely_timeout_kill_false_when_span_well_under_ceiling(tmp_path):
    first = dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T17:22:04.850Z")
    last = dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T17:22:14.850Z")  # 10s later
    p = _write_ndjson(str(tmp_path), "a.json", [first, last])  # no result event, died early
    assert likely_timeout_kill(p, timeout_s=3300) is False


def test_likely_timeout_kill_none_when_span_unavailable(tmp_path):
    # Fewer than 2 timestamped events (e.g. a round that dies before its
    # first assistant turn even lands) — not enough data to claim EITHER
    # a crash or a timeout kill, so this reads None ("unknown"), not a
    # silent default to "genuine crash".
    p = _write_ndjson(str(tmp_path), "a.json", [{"type": "system", "subtype": "init"}])
    assert likely_timeout_kill(p, timeout_s=3300) is None


def test_likely_timeout_kill_respects_custom_margin(tmp_path):
    first = dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T17:22:04.850Z")
    last = dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T18:00:04.850Z")  # 2280s later
    p = _write_ndjson(str(tmp_path), "a.json", [first, last])
    # 2280s is 1020s short of a 3300s ceiling: outside the default 180s
    # margin (False) but inside a wider, explicitly-passed 1200s margin.
    assert likely_timeout_kill(p, timeout_s=3300) is False
    assert likely_timeout_kill(p, timeout_s=3300, margin_s=1200) is True


def test_reproduces_actual_round_210_no_result_near_ceiling_kill(tmp_path):
    """Regression pin: round 210's real log (`logs/round-210.json`, first
    event 2026-08-27T17:22:04.850Z, last event 2026-08-27T18:17:01.596Z, no
    `result` line anywhere) against this driver's real 3300s
    `DRIVER_ROUND_TIMEOUT_S` default — must read as a likely timeout kill,
    not a "?" genuine-crash guess, per round 211's investigation.
    """
    system_no_ts = {"type": "system", "subtype": "init"}
    first_assistant = dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T17:22:04.850Z")
    trailing_task_killed = {"type": "system", "subtype": "task_updated",
                             "timestamp": "2026-08-27T18:17:00.000Z"}
    last_assistant = dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T18:17:01.596Z")
    events = [system_no_ts, first_assistant, trailing_task_killed, last_assistant]
    p = _write_ndjson(str(tmp_path), "round-210.json", events)
    assert all(e.get("type") != "result" for e in events)
    assert likely_timeout_kill(p, timeout_s=3300) is True


def test_reproduces_actual_round_222_no_result_near_ceiling_kill(tmp_path):
    """Regression pin: round 222's real log (`logs/round-222.json`, first
    assistant 2026-08-27T22:17:52.506Z, last assistant 2026-08-27T23:07:46.457Z,
    last event overall a `type: "user"` tool-result at 23:12:49.969Z, no
    `result` line anywhere) — a SECOND real counterexample for round 211's
    classifier, found by round 223 while landing round 222's uncommitted
    work. Distinct from round 210's fixture in two ways worth pinning
    separately rather than treating as a duplicate: (1) the trailing event
    is `type: "user"` (a tool_result flowing back from a backgrounded Bash
    wait on a slow pytest run — round 222 died mid-wait on exactly the kind
    of dangling background call skills(B)'s round 171 named for the
    IN-session turn-ending mechanism, except here it's the driver's OWN
    outer timeout that fired, not the CLI ending its turn), not round 210's
    `system`/`task_updated`; (2) the assistant-only vs. full-event span gap
    is much larger here (303.5s vs. round 210's ~123s) because the dangling
    wait's tool_result took over 5 minutes to land after the last assistant
    text, so this is also a stronger real-world demonstration of why
    `full_event_span_s` (not `summarize_turns`'s assistant-only span) is the
    right primitive for this classifier.
    """
    first_assistant = dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T22:17:52.506Z")
    last_assistant = dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T23:07:46.457Z")
    trailing_tool_result = {"type": "user", "message": {"role": "user", "content": []},
                             "timestamp": "2026-08-27T23:12:49.969Z"}
    events = [first_assistant, last_assistant, trailing_tool_result]
    p = _write_ndjson(str(tmp_path), "round-222.json", events)
    assert all(e.get("type") != "result" for e in events)
    s = summarize_turns(p)
    full_span = full_event_span_s(p)
    assert s["span_s"] == pytest.approx(2993.951, abs=0.01)
    assert full_span == pytest.approx(3297.463, abs=0.01)
    assert full_span - s["span_s"] == pytest.approx(303.512, abs=0.01)
    assert likely_timeout_kill(p, timeout_s=3300) is True


# --- blocking_wait_gap_s / last_assistant_tool_use / is_blocking_wait_kill
# (round 283) ---------------------------------------------------------------
#
# Promotes a diagnosis manually re-derived by hand three times (round 223 on
# round 222, round 265 on round 263, round 283 on round 278) into reusable
# primitives: does an `interrupted` round's wall clock end with the model
# genuinely still generating (round 224: last event IS an assistant tool_use
# call, zero trailing events, gap == 0.0) or synchronously blocked on a
# still-in-flight tool result (rounds 222/263/278: trailing tool_progress/
# system/user events after the last assistant timestamp, gap > 100s)?

def _tool_use_assistant(timestamp, tool_name):
    return {
        "type": "assistant",
        "message": {
            "model": "claude-sonnet-5", "role": "assistant",
            "content": [{"type": "tool_use", "id": "toolu_x", "name": tool_name, "input": {}}],
            "usage": {"output_tokens": 4, "output_tokens_details": {"thinking_tokens": 0}},
        },
        "timestamp": timestamp,
    }


def test_blocking_wait_gap_s_zero_when_last_event_is_the_assistant_tool_use(tmp_path):
    # Round 224's real shape: the tool_use call is the LAST event in the
    # entire log, no trailing tool_progress/system/user at all.
    first = _tool_use_assistant("2026-08-27T23:51:45.115Z", "Read")
    last = _tool_use_assistant("2026-08-28T00:46:40.971Z", "Bash")
    p = _write_ndjson(str(tmp_path), "a.json", [first, last])
    assert blocking_wait_gap_s(p) == pytest.approx(0.0, abs=1e-9)


def test_blocking_wait_gap_s_positive_with_trailing_non_assistant_events(tmp_path):
    first = _tool_use_assistant("2026-08-27T22:17:52.506Z", "Bash")
    last = _tool_use_assistant("2026-08-27T23:07:46.457Z", "TaskOutput")
    tick = {"type": "tool_progress"}
    trailing_user = {"type": "user", "message": {"role": "user", "content": []},
                      "timestamp": "2026-08-27T23:12:49.969Z"}
    p = _write_ndjson(str(tmp_path), "a.json", [first, last, tick, tick, trailing_user])
    gap = blocking_wait_gap_s(p)
    assert gap == pytest.approx(303.512, abs=0.01)


def test_blocking_wait_gap_s_none_when_span_unavailable(tmp_path):
    p = _write_ndjson(str(tmp_path), "a.json", [{"type": "system", "subtype": "init"}])
    assert blocking_wait_gap_s(p) is None


def test_blocking_wait_gap_s_none_on_missing_file(tmp_path):
    assert blocking_wait_gap_s(os.path.join(str(tmp_path), "nope.json")) is None


def test_last_assistant_tool_use_reads_the_final_assistant_events_tool(tmp_path):
    first = _tool_use_assistant("2026-08-27T22:17:52.506Z", "Bash")
    last = _tool_use_assistant("2026-08-27T23:07:46.457Z", "TaskOutput")
    p = _write_ndjson(str(tmp_path), "a.json", [first, last])
    assert last_assistant_tool_use(p) == "TaskOutput"


def test_last_assistant_tool_use_none_for_text_only_final_turn(tmp_path):
    p = _write_ndjson(str(tmp_path), "a.json", [
        _tool_use_assistant("2026-08-27T22:17:52.506Z", "Bash"),
        dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T23:07:46.457Z"),
    ])
    assert last_assistant_tool_use(p) is None


def test_last_assistant_tool_use_none_when_no_assistant_events(tmp_path):
    p = _write_ndjson(str(tmp_path), "a.json", [{"type": "system", "subtype": "init"}])
    assert last_assistant_tool_use(p) is None


def test_is_blocking_wait_kill_true_for_the_222_263_278_shape(tmp_path):
    first = _tool_use_assistant("2026-08-27T22:17:52.506Z", "Bash")
    last = _tool_use_assistant("2026-08-27T23:07:46.457Z", "TaskOutput")
    trailing_user = {"type": "user", "message": {"role": "user", "content": []},
                      "timestamp": "2026-08-27T23:12:49.969Z"}
    p = _write_ndjson(str(tmp_path), "a.json", [first, last, trailing_user])  # no result event
    assert is_blocking_wait_kill(p) is True


def test_is_blocking_wait_kill_false_for_the_224_shape(tmp_path):
    first = _tool_use_assistant("2026-08-27T23:51:45.115Z", "Read")
    last = _tool_use_assistant("2026-08-28T00:46:40.971Z", "Bash")
    p = _write_ndjson(str(tmp_path), "a.json", [first, last])  # no result event, no trailing events
    assert is_blocking_wait_kill(p) is False


def test_is_blocking_wait_kill_none_when_not_interrupted(tmp_path):
    p = _write_ndjson(str(tmp_path), "a.json", [
        dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T22:17:52.506Z"),
        REAL_RESULT_LINE,
    ])
    assert is_blocking_wait_kill(p) is None


def test_is_blocking_wait_kill_respects_custom_min_gap(tmp_path):
    first = _tool_use_assistant("2026-08-27T22:17:52.506Z", "Bash")
    last = _tool_use_assistant("2026-08-27T23:07:46.457Z", "TaskOutput")
    trailing_user = {"type": "user", "message": {"role": "user", "content": []},
                      "timestamp": "2026-08-27T23:07:46.957Z"}  # only 0.5s gap
    p = _write_ndjson(str(tmp_path), "a.json", [first, last, trailing_user])
    assert is_blocking_wait_kill(p) is False  # 0.5s < default 1.0s floor
    assert is_blocking_wait_kill(p, min_gap_s=0.1) is True


def test_reproduces_actual_round_278_taskoutput_block_kill_fourth_instance(tmp_path):
    """Regression pin: round 278's real log (`logs/round-278.json`, first
    assistant 2026-08-28T18:52:23.511Z, last assistant
    2026-08-28T19:43:51.256Z — a `TaskOutput` call with `block: true` — last
    event overall a `type: "user"` tool-result at 19:47:18.449Z, no
    `result` line anywhere) — a FOURTH real instance of the same mechanism
    round 223 first named on round 222 and round 265 confirmed on round
    263, found while re-tallying `interrupted` rounds per round 279's own
    next-steps item 4. Distinct gap size (207.193s) from both prior
    instances (303.512s, 338.59s) but the same qualitative shape: last
    assistant event is a `TaskOutput(block=true)` call, several untimestamped
    `tool_progress` ticks follow, then a single trailing `user` event lands
    after the driver's own wall-clock ceiling already fired.
    """
    first_assistant = dict(REAL_ASSISTANT_LINE, timestamp="2026-08-28T18:52:23.511Z")
    last_assistant = _tool_use_assistant("2026-08-28T19:43:51.256Z", "TaskOutput")
    ticks = [{"type": "tool_progress"} for _ in range(6)]
    trailing_tool_result = {"type": "user", "message": {"role": "user", "content": []},
                             "timestamp": "2026-08-28T19:47:18.449Z"}
    events = [first_assistant, last_assistant] + ticks + [trailing_tool_result]
    p = _write_ndjson(str(tmp_path), "round-278.json", events)
    assert all(e.get("type") != "result" for e in events)
    s = summarize_turns(p)
    full_span = full_event_span_s(p)
    assert s["span_s"] == pytest.approx(3087.745, abs=0.01)
    assert full_span == pytest.approx(3294.938, abs=0.01)
    assert blocking_wait_gap_s(p) == pytest.approx(207.193, abs=0.01)
    assert last_assistant_tool_use(p) == "TaskOutput"
    assert is_blocking_wait_kill(p) is True
    assert likely_timeout_kill(p, timeout_s=3300) is True


def test_is_blocking_wait_kill_true_for_the_smallest_known_real_gap(tmp_path):
    """Round 289: full-history re-check (logs/round-{152..288}.json, not
    just the 5 previously examined) found round 192's real log has the
    IDENTICAL "tool result landed, no further turn" shape as 222/263/278,
    just with a 9.214s gap — an ordinary-speed Bash call, not a hang. Under
    the pre-289 default (min_gap_s=100.0) this read False, silently
    grouping a structurally-identical instance with round 224's genuinely
    different "still generating" shape. Pinned so the corrected default
    (1.0) doesn't regress back to that misclassification.
    """
    first = _tool_use_assistant("2026-08-27T08:16:57.870Z", "Read")
    last = _tool_use_assistant("2026-08-27T09:11:42.515Z", "Bash")
    trailing_user = {"type": "user", "message": {"role": "user", "content": []},
                      "timestamp": "2026-08-27T09:11:51.729Z"}
    p = _write_ndjson(str(tmp_path), "round-192.json", [first, last, trailing_user])
    assert blocking_wait_gap_s(p) == pytest.approx(9.214, abs=0.01)
    assert is_blocking_wait_kill(p) is True


def test_is_blocking_wait_kill_true_for_round_174s_mid_continuum_gap(tmp_path):
    """Round 289: another of the 4 rounds (162/173/174/192) the pre-289
    100s default silently misclassified — same shape, 27.771s gap."""
    first = _tool_use_assistant("2026-08-27T00:17:48.847Z", "Read")
    last = _tool_use_assistant("2026-08-27T00:57:14.603Z", "Bash")
    trailing_user = {"type": "user", "message": {"role": "user", "content": []},
                      "timestamp": "2026-08-27T00:57:42.374Z"}
    p = _write_ndjson(str(tmp_path), "round-174.json", [first, last, trailing_user])
    assert blocking_wait_gap_s(p) == pytest.approx(27.771, abs=0.01)
    assert is_blocking_wait_kill(p) is True


def test_is_blocking_wait_kill_true_for_round_185s_extreme_gap(tmp_path):
    """Round 289: round 185's real log is the most extreme instance found
    in the full-history re-check — a 2912.156s gap (48.5 minutes), nearly
    the round's entire budget, spent inside a SINGLE Bash tool call with no
    `timeout` param set: a one-off `python3 -c` script exploring
    `swe.guest.oracle_self_eval` mismatches with a shared `GuestHarness`
    across several test cases, one of which was a self-recursive guest
    program (`fn f6() { let t7 = f6() ... }`, no base case). Unlike
    162/173/174/192/278 etc., this magnitude IS worth a second look at the
    underlying tool call — see `harness/swe/oracles.py`'s `run_oracle`
    (round 289: now accepts `**kwargs`, closing the exact gap that forced
    this script to bypass `run_oracle`'s SIGALRM timeout in the first
    place)."""
    first = _tool_use_assistant("2026-08-27T05:50:46.615Z", "Read")
    last = _tool_use_assistant("2026-08-27T06:17:45.744Z", "Bash")
    trailing_user = {"type": "user", "message": {"role": "user", "content": []},
                      "timestamp": "2026-08-27T07:06:17.900Z"}
    p = _write_ndjson(str(tmp_path), "round-185.json", [first, last, trailing_user])
    assert blocking_wait_gap_s(p) == pytest.approx(2912.156, abs=0.01)
    assert is_blocking_wait_kill(p) is True


def test_is_blocking_wait_kill_true_for_round_295_third_taskoutput_instance(tmp_path):
    """Round 301: round 295 (harness(A) itself — only the 2nd harness(A)
    round ever to land `interrupted`, after round 169) is the first new
    real instance since round 289's full-history re-check stopped at round
    288. Re-reading its actual log confirms the identical structural shape
    (last assistant event a `TaskOutput` call — `{"block": true, "timeout":
    500000}`, exactly the mechanism round 265 named for round 263 — then a
    run of `tool_progress`/`task_notification`/`background_tasks_changed`/
    `task_updated` ticks, then one real `user` tool-result at the very end,
    45.460 into the following minute), not a dangling wait or a fresh
    mechanism. Gap is 44.642s — falls between round 174's 27.771s and round
    162's 87.791s in the existing continuum, reconfirming (not just
    repeating) that `min_gap_s=1.0` and `likely_timeout_kill`'s
    `margin_s=180.0` both still classify a genuinely new data point
    correctly, closing backlog item 3 from round 217's list ("margin_s=180
    default still untested against a real counterexample since it was
    set") with an actual new confirming instance rather than leaving it
    perpetually flagged untested.
    """
    first_assistant = dict(REAL_ASSISTANT_LINE, timestamp="2026-08-29T00:35:50.705Z")
    last_assistant = _tool_use_assistant("2026-08-29T01:30:00.818Z", "TaskOutput")
    ticks = [{"type": "tool_progress"} for _ in range(4)]
    trailing_tool_result = {"type": "user", "message": {"role": "user", "content": []},
                             "timestamp": "2026-08-29T01:30:45.460Z"}
    events = [first_assistant, last_assistant] + ticks + [trailing_tool_result]
    p = _write_ndjson(str(tmp_path), "round-295.json", events)
    assert all(e.get("type") != "result" for e in events)
    s = summarize_turns(p)
    full_span = full_event_span_s(p)
    assert s["span_s"] == pytest.approx(3250.113, abs=0.01)
    assert full_span == pytest.approx(3294.755, abs=0.01)
    assert blocking_wait_gap_s(p) == pytest.approx(44.642, abs=0.01)
    assert last_assistant_tool_use(p) == "TaskOutput"
    assert is_blocking_wait_kill(p) is True
    assert likely_timeout_kill(p, timeout_s=3300, margin_s=180.0) is True


def test_is_blocking_wait_kill_true_for_round_311_new_taskoutput_instance(tmp_path):
    """Round 331: the next scheduled `tally_by_track`/`heavy_light_fail_
    rates` re-tally (round 301's own ~30-40-round check-in target,
    [301,330] is 30 rounds later) found exactly 3 new `interrupted`/
    `max_turns` deaths in that window (rounds 311, 318, 323), all 3 in
    HEAVY tracks (SWE-loop(D)/language(C)) — zero in the three light
    tracks, extending round 301's own "settled, heavy fails far more
    often" finding rather than contradicting it. Round 311 (SWE-loop(D))
    is the only NEW `interrupted` (not `max_turns`) instance among the 3,
    so it's the one worth re-confirming against this module the same way
    round 301 did for round 295. Real log shape: last assistant event a
    `TaskOutput` call at 2026-08-29T06:43:18.411Z, then 7
    `tool_progress` ticks, then 3 `system` events (a structural variant
    not seen in round 295's shape — extra bookkeeping lines with no
    timestamp, which `full_event_span_s` correctly ignores since they
    carry none), then one real `user` tool-result at
    2026-08-29T06:47:04.041Z — gap 225.63s. Slots into the continuum just
    above round 278's 207.193s, tightening what was previously the
    biggest known jump (207.193s straight to round 185's 2912.156s)."""
    first_assistant = _tool_use_assistant("2026-08-29T05:52:07.445Z", "Read")
    last_assistant = _tool_use_assistant("2026-08-29T06:43:18.411Z", "TaskOutput")
    ticks = [{"type": "tool_progress"} for _ in range(7)]
    system_lines = [{"type": "system"} for _ in range(3)]
    trailing_tool_result = {"type": "user", "message": {"role": "user", "content": []},
                             "timestamp": "2026-08-29T06:47:04.041Z"}
    events = [first_assistant, last_assistant] + ticks + system_lines + [trailing_tool_result]
    p = _write_ndjson(str(tmp_path), "round-311.json", events)
    assert all(e.get("type") != "result" for e in events)
    s = summarize_turns(p)
    assert s["span_s"] == pytest.approx(3070.966, abs=0.01)
    assert full_event_span_s(p) == pytest.approx(3296.596, abs=0.01)
    assert blocking_wait_gap_s(p) == pytest.approx(225.63, abs=0.01)
    assert last_assistant_tool_use(p) == "TaskOutput"
    assert is_blocking_wait_kill(p) is True
    assert likely_timeout_kill(p, timeout_s=3300, margin_s=180.0) is True


def test_cli_blocking_wait_gap_and_is_blocking_wait_kill_subcommands(tmp_path):
    first = _tool_use_assistant("2026-08-27T22:17:52.506Z", "Bash")
    last = _tool_use_assistant("2026-08-27T23:07:46.457Z", "TaskOutput")
    trailing_user = {"type": "user", "message": {"role": "user", "content": []},
                      "timestamp": "2026-08-27T23:12:49.969Z"}
    blocked = _write_ndjson(str(tmp_path), "blocked.json", [first, last, trailing_user])
    generating = _write_ndjson(str(tmp_path), "generating.json", [
        _tool_use_assistant("2026-08-27T23:51:45.115Z", "Read"),
        _tool_use_assistant("2026-08-28T00:46:40.971Z", "Bash"),
    ])

    def run(*args):
        out = subprocess.run(
            [sys.executable, "-m", "harness.driver_health"] + list(args),
            cwd=os.path.join(HERE, "..", ".."),
            capture_output=True, text=True, timeout=10,
        )
        assert out.returncode == 0, out.stderr
        return out.stdout.strip()

    assert float(run("blocking_wait_gap", blocked)) == pytest.approx(303.512, abs=0.01)
    assert float(run("blocking_wait_gap", generating)) == pytest.approx(0.0, abs=1e-9)
    assert run("is_blocking_wait_kill", blocked) == "yes"
    assert run("is_blocking_wait_kill", generating) == "no"
    # explicit MIN_GAP_S arg wired through
    assert run("is_blocking_wait_kill", blocked, "1000") == "no"


def test_cli_blocking_wait_gap_bad_arity():
    assert main(["blocking_wait_gap"]) == 2


def test_cli_is_blocking_wait_kill_bad_arity():
    assert main(["is_blocking_wait_kill", "a", "b", "c"]) == 2


def test_cli_likely_timeout_kill_subcommand(tmp_path):
    near_ceiling = _write_ndjson(str(tmp_path), "near.json", [
        dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T17:22:04.850Z"),
        dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T18:17:01.596Z"),
    ])
    early_crash = _write_ndjson(str(tmp_path), "early.json", [
        dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T17:22:04.850Z"),
        dict(REAL_ASSISTANT_LINE, timestamp="2026-08-27T17:22:14.850Z"),
    ])

    def run(*args):
        out = subprocess.run(
            [sys.executable, "-m", "harness.driver_health"] + list(args),
            cwd=os.path.join(HERE, "..", ".."),
            capture_output=True, text=True, timeout=10,
        )
        assert out.returncode == 0, out.stderr
        return out.stdout.strip()

    assert run("likely_timeout_kill", near_ceiling, "3300") == "yes"
    assert run("likely_timeout_kill", early_crash, "3300") == "no"
    # explicit MARGIN_S arg wired through
    assert run("likely_timeout_kill", early_crash, "3300", "3290") == "yes"


def test_cli_likely_timeout_kill_bad_arity():
    assert main(["likely_timeout_kill"]) == 2
    assert main(["likely_timeout_kill", "a.json"]) == 2


def test_track_name_for_round_matches_run_driver_sh_cycle():
    # Pins run_driver.sh's `track_name()` bash function (round % 6) against
    # rounds actually seen in logs/driver.log, so a future edit to either
    # side is caught by a red test instead of silent drift between the two
    # copies of the same mapping.
    assert track_name_for_round(211) == "harness(A)"    # round % 6 == 1
    assert track_name_for_round(217) == "harness(A)"
    assert track_name_for_round(206) == "language(C)"   # round % 6 == 2
    assert track_name_for_round(216) == "language(C)"   # round % 6 == 0
    assert track_name_for_round(207) == "skills(B)"      # round % 6 == 3
    assert track_name_for_round(208) == "NUC-integration(E)"  # round % 6 == 4
    assert track_name_for_round(209) == "SWE-loop(D)"    # round % 6 == 5


def test_track_name_for_round_language_c_gets_two_of_six_slots():
    counts = {}
    for r in range(1, 61):
        counts.setdefault(track_name_for_round(r), 0)
        counts[track_name_for_round(r)] += 1
    assert counts["language(C)"] == 20  # 2 of every 6 rounds
    for track in ("harness(A)", "skills(B)", "NUC-integration(E)", "SWE-loop(D)"):
        assert counts[track] == 10  # 1 of every 6 rounds


def test_tally_by_track_counts_max_turns_and_interrupted_per_track(tmp_path):
    # round 206 (language(C)): a real max-turns death.
    maxturns = _write_ndjson(str(tmp_path), "round-206.json", [
        REAL_INIT_LINE, REAL_ASSISTANT_LINE,
        dict(REAL_RESULT_LINE, is_error=True, subtype="error_max_turns"),
    ])
    # round 210 (language(C)): killed with no result event at all.
    interrupted = _write_ndjson(str(tmp_path), "round-210.json", [REAL_INIT_LINE, REAL_ASSISTANT_LINE])
    # round 211 (harness(A)): clean success.
    clean = _write_ndjson(str(tmp_path), "round-211.json", [REAL_INIT_LINE, REAL_ASSISTANT_LINE, REAL_RESULT_LINE])

    tally = tally_by_track([maxturns, interrupted, clean])
    assert tally["language(C)"] == {"total": 2, "max_turns": 1, "interrupted": 1}
    assert tally["harness(A)"] == {"total": 1, "max_turns": 0, "interrupted": 0}
    assert "skills(B)" not in tally  # no rounds passed in for that track


def test_tally_by_track_skips_unparseable_paths(tmp_path):
    clean = _write_ndjson(str(tmp_path), "round-211.json", [REAL_INIT_LINE, REAL_ASSISTANT_LINE, REAL_RESULT_LINE])
    tally = tally_by_track([clean, "not-a-round-file.json", "logs/driver.log"])
    assert tally == {"harness(A)": {"total": 1, "max_turns": 0, "interrupted": 0}}


def test_tally_by_track_zero_padded_filenames():
    # `logs/round-NNN.json` uses %03d padding in production (e.g. round-007.json).
    assert tally_by_track([]) == {}


def test_cli_tally_subcommand(tmp_path):
    p = _write_ndjson(str(tmp_path), "round-207.json", [REAL_INIT_LINE, REAL_ASSISTANT_LINE, REAL_RESULT_LINE])
    out = subprocess.run(
        [sys.executable, "-m", "harness.driver_health", "tally", p],
        cwd=os.path.join(HERE, "..", ".."),
        capture_output=True, text=True, timeout=10,
    )
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == {"skills(B)": {"total": 1, "max_turns": 0, "interrupted": 0}}


def test_heavy_light_fail_rates_splits_and_sums_correctly(tmp_path):
    # round 206 (language(C), HEAVY): max-turns death.
    maxturns = _write_ndjson(str(tmp_path), "round-206.json", [
        REAL_INIT_LINE, REAL_ASSISTANT_LINE,
        dict(REAL_RESULT_LINE, is_error=True, subtype="error_max_turns"),
    ])
    # round 209 (SWE-loop(D), HEAVY): interrupted (no result event).
    interrupted = _write_ndjson(str(tmp_path), "round-209.json", [REAL_INIT_LINE, REAL_ASSISTANT_LINE])
    # round 211 (harness(A), LIGHT): clean success.
    clean_a = _write_ndjson(str(tmp_path), "round-211.json", [REAL_INIT_LINE, REAL_ASSISTANT_LINE, REAL_RESULT_LINE])
    # round 207 (skills(B), LIGHT): clean success.
    clean_b = _write_ndjson(str(tmp_path), "round-207.json", [REAL_INIT_LINE, REAL_ASSISTANT_LINE, REAL_RESULT_LINE])

    out = heavy_light_fail_rates([maxturns, interrupted, clean_a, clean_b])
    assert out["heavy"] == {"total": 2, "fail": 2, "rate": 1.0}
    assert out["light"] == {"total": 2, "fail": 0, "rate": 0.0}
    assert out["ratio"] is None  # light's rate is 0 — a finite ratio would be misleading


def test_heavy_light_fail_rates_computes_a_finite_ratio_when_light_has_failures(tmp_path):
    # round 168 (language(C), HEAVY): max-turns death.
    maxturns = _write_ndjson(str(tmp_path), "round-168.json", [
        REAL_INIT_LINE, REAL_ASSISTANT_LINE,
        dict(REAL_RESULT_LINE, is_error=True, subtype="error_max_turns"),
    ])
    clean_heavy = _write_ndjson(str(tmp_path), "round-174.json", [REAL_INIT_LINE, REAL_ASSISTANT_LINE, REAL_RESULT_LINE])
    # round 169 (harness(A), LIGHT): interrupted.
    light_interrupted = _write_ndjson(str(tmp_path), "round-169.json", [REAL_INIT_LINE, REAL_ASSISTANT_LINE])
    clean_light = _write_ndjson(str(tmp_path), "round-171.json", [REAL_INIT_LINE, REAL_ASSISTANT_LINE, REAL_RESULT_LINE])

    out = heavy_light_fail_rates([maxturns, clean_heavy, light_interrupted, clean_light])
    assert out["heavy"] == {"total": 2, "fail": 1, "rate": 0.5}
    assert out["light"] == {"total": 2, "fail": 1, "rate": 0.5}
    assert out["ratio"] == pytest.approx(1.0)


def test_heavy_light_fail_rates_empty_input():
    assert heavy_light_fail_rates([]) == {
        "heavy": {"total": 0, "fail": 0, "rate": 0.0},
        "light": {"total": 0, "fail": 0, "rate": 0.0},
        "ratio": None,
    }


def test_cli_heavy_light_subcommand(tmp_path):
    p = _write_ndjson(str(tmp_path), "round-206.json", [
        REAL_INIT_LINE, REAL_ASSISTANT_LINE,
        dict(REAL_RESULT_LINE, is_error=True, subtype="error_max_turns"),
    ])
    out = subprocess.run(
        [sys.executable, "-m", "harness.driver_health", "heavy_light", p],
        cwd=os.path.join(HERE, "..", ".."),
        capture_output=True, text=True, timeout=10,
    )
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == {
        "heavy": {"total": 1, "fail": 1, "rate": 1.0},
        "light": {"total": 0, "fail": 0, "rate": 0.0},
        "ratio": None,
    }


# ------------------------------------------------------- round 349 (harness A) --
#
# `classify_health_log` splits run_driver.sh's PASS/FAIL health-check line
# into PASS / FAIL / ERROR. Round 348 produced the first non-green health
# check in the program's recorded history — an untracked `pyproject.toml`
# with a duplicate TOML table made pytest exit 4 during config discovery,
# taking all 1043 whence fast-tier tests down — and the driver logged
# `whence-health-check FAIL`, which reads as "round 348 broke the tests" and
# was false twice over. Across all 206 health logs on this host the FAIL
# branch had fired exactly once ever: that one.
#
# The two literals below are the REAL last lines of
# logs/whence_health_round_348.log and logs/whence_health_round_347.log.
# Those files are gitignored (see .gitignore's round-241/247 note), so they
# are transcribed here rather than referenced.

REAL_348_ERROR = (
    "ERROR: /home/pgain/agi-research-nuc-llm/languages/whence/pyproject.toml: "
    "Cannot declare ('project', 'optional-dependencies') twice "
    "(at line 29, column 31)\n"
)
REAL_347_PASS = (
    "........................................................................ [ 98%]\n"
    "..............                                                           [100%]\n"
    "1022 passed, 48 deselected in 35.62s\n"
)


def _health_log(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def test_classify_health_log_pass_on_the_real_round_347_log(tmp_path):
    p = _health_log(tmp_path, "h.log", REAL_347_PASS)
    for rc in (0, None):                      # exit code present or inferred
        c = classify_health_log(p, rc)
        assert c["outcome"] == "pass", (rc, c)
        assert c["ran_tests"] is True
        assert c["summary"] == "1022 passed, 48 deselected in 35.62s"


def test_classify_health_log_error_on_the_real_round_348_log(tmp_path):
    p = _health_log(tmp_path, "h.log", REAL_348_ERROR)
    c = classify_health_log(p, 4)
    assert c["outcome"] == "error"
    assert c["ran_tests"] is False
    assert "pytest exit 4" in c["reason"]
    # And with no exit code at all — the text alone has to be enough, which
    # is what let round 349 replay the verdict over 206 archived logs that
    # never recorded one.
    c2 = classify_health_log(p, None)
    assert c2["outcome"] == "error" and c2["ran_tests"] is False


def test_classify_health_log_fail_is_reserved_for_tests_that_actually_ran(tmp_path):
    p = _health_log(tmp_path, "h.log",
                    "F...\n1 failed, 1041 passed, 52 deselected in 22.06s\n"
                    "FAILED tests/test_tiering.py::test_partitions\n")
    for rc in (1, None):
        c = classify_health_log(p, rc)
        assert c["outcome"] == "fail", (rc, c)
        assert c["ran_tests"] is True


def test_classify_health_log_calls_zero_collected_an_error_not_a_pass(tmp_path):
    # pytest exit 5. Nothing failed, so the old any-nonzero-is-FAIL rule and
    # a naive "no 'failed' in the text" rule both get this wrong in opposite
    # directions. No test ran, so it is neither a pass nor a failure.
    p = _health_log(tmp_path, "h.log", "no tests ran in 0.01s\n")
    assert classify_health_log(p, 5)["outcome"] == "error"
    assert classify_health_log(p, None)["outcome"] == "error"


def test_classify_health_log_flags_an_exit_1_with_no_test_counts(tmp_path):
    # A wrapper that rewrites its own exit status would land here. Trusting
    # rc alone would call it FAIL; the log says no test ever ran.
    p = _health_log(tmp_path, "h.log", "wrapper: something went sideways\n")
    c = classify_health_log(p, 1)
    assert c["outcome"] == "error"
    assert "no test counts" in c["reason"]


def test_classify_health_log_handles_missing_and_empty_logs(tmp_path):
    c = classify_health_log(str(tmp_path / "nope.log"), None)
    assert c["outcome"] == "unknown" and "unreadable" in c["reason"]
    p = _health_log(tmp_path, "empty.log", "")
    assert classify_health_log(p, None)["outcome"] == "unknown"
    # With an exit code we can still answer even for an empty log.
    assert classify_health_log(p, 0)["outcome"] == "pass"
    assert classify_health_log(p, 4)["outcome"] == "error"


def test_classify_health_log_treats_a_signal_death_as_an_error(tmp_path):
    p = _health_log(tmp_path, "h.log", "collecting ...\n")
    c = classify_health_log(p, -9)
    assert c["outcome"] == "error" and "runner died" in c["reason"]


def test_health_log_line_matches_the_pre_349_pass_wording_exactly(tmp_path):
    # The PASS line is unchanged on purpose: rounds 242-348 of driver.log
    # are parsed by eye and by `check_round_recorded`, and 205 of the 206
    # archived health logs are passes.
    p = _health_log(tmp_path, "h.log", REAL_347_PASS)
    assert health_log_line("round 9: whence-health-check", p, 0) == (
        "round 9: whence-health-check PASS (1022 passed, 48 deselected in 35.62s)")


def test_health_log_line_says_error_and_why_for_round_348s_log(tmp_path):
    p = _health_log(tmp_path, "h.log", REAL_348_ERROR)
    line = health_log_line("round 348: whence-health-check", p, 4)
    assert line.startswith("round 348: whence-health-check ERROR — "
                           "suite did not run (pytest exit 4) — ")
    assert "optional-dependencies" in line
    assert "FAIL" not in line


# ------------------------------------------------------- round 379 (harness A) --
#
# The health log the HARNESS check writes has not been a bare pytest log
# since round 341. `harness/run_tests_fast.sh` echoes two RECORDED ledgers
# after its own run (round 341's slow tier, round 355's pristine
# differential), so "the last non-empty line" — round 349's rule for
# `summary` — stopped being this run's result three rounds after round 349
# shipped, and nobody noticed for 38 rounds because round 349's two
# fixtures (above) are both transcribed from `whence_health_round_34*.log`,
# and the WHENCE script `exec`s pytest and appends nothing.
#
# Measured over `logs/driver.log`: 38 of 38 `health-check` lines from round
# 341 to round 378 quote an echo. 14 quote `slowtier status`'s trailing
# NOTE, 18 quote `fails in both (not this class) tests/test_self_eval.py::
# test_shape_needs_three_adjacent_tokens_on_both_sides` — a RECORDED FAILURE
# printed under the word PASS — and 6 quote a pristine row measured once, at
# round 373, at a commit the tree had since left.
#
# The two literals below are transcribed from the real
# `logs/health_round_378.log` and `logs/health_round_362.log` on this host
# (gitignored, hence transcribed, same convention as REAL_347_PASS).

REAL_378_HARNESS = (
    "........................................................................ [ 98%]\n"
    "...........                                                              [100%]\n"
    "587 passed, 323 deselected in 47.51s\n"
    "\n"
    "slow tier (recorded, not run here)\n"
    "  test_swe_repair.py                 stale_checkout     102s  26.2h ago\n"
    "  test_swe_review.py                 stale_checkout     81s  14.9h ago\n"
    "  NOTE: 18 file(s) are NOT evidence about this checkout.\n"
    "\n"
    "ref HEAD (91acd9c5af97)   verdict clean\n"
    "  17 untracked path(s) exist here and in no fresh clone\n"
    "  whence-slow    clean                  live={'deselected': 1598, "
    "'passed': 70} pristine={'deselected': 1598, 'passed': 70}  1014.6s\n"
)

# Round 362: the ONE genuine harness-side FAIL in the program's history.
REAL_362_HARNESS = (
    "F....\n"
    "FAILED harness/tests/test_run_driver_whence_health_check.py::"
    "test_whence_health_check_fail_logged_when_script_fails\n"
    "1 failed, 544 passed, 316 deselected in 854.14s (0:14:14)\n"
    "\n"
    "ref HEAD (aaaaaaaaaaaa)   verdict both_failed\n"
    "  whence-slow    both_failed            live={'passed': 53} "
    "pristine={'passed': 53}  586.3s\n"
    "      fails in both (not this class)  tests/test_self_eval.py::"
    "test_shape_needs_three_adjacent_tokens_on_both_sides\n"
)


def test_the_summary_is_this_runs_own_result_not_an_echoed_ledger(tmp_path):
    """Round 378's real log. `pass` was already right; the QUOTE was not."""
    p = _health_log(tmp_path, "h.log", REAL_378_HARNESS)
    c = classify_health_log(p, 0)
    assert c["outcome"] == "pass"
    assert c["summary"] == "587 passed, 323 deselected in 47.51s"
    assert c["summary_source"] == "count-line-guess"   # inferred, not read
    assert c["echoed_lines"] == 7          # everything below the run's own
    # The three strings the driver actually printed for rounds 373-378.
    assert "1014.6s" not in c["summary"]
    assert "NOTE:" not in c["summary"]


def test_health_line_for_round_378s_log_stops_quoting_round_373s_ledger(tmp_path):
    p = _health_log(tmp_path, "h.log", REAL_378_HARNESS)
    assert health_log_line("round 378: health-check", p, 0) == (
        "round 378: health-check PASS (587 passed, 323 deselected in 47.51s)")


def test_a_failing_run_names_the_test_that_actually_failed(tmp_path):
    """Round 362's real log.

    The driver logged `FAIL — tests ran and failed — fails in both (not this
    class) tests/test_self_eval.py::test_shape_needs_three_adjacent_tokens_
    on_both_sides`: a whence test, from a ledger, for a harness suite whose
    real failure was in `test_run_driver_whence_health_check.py`. The word
    was right and every other part of the line pointed at the wrong tree.
    """
    p = _health_log(tmp_path, "h.log", REAL_362_HARNESS)
    c = classify_health_log(p, 1)
    assert c["outcome"] == "fail"
    assert c["summary"] == "1 failed, 544 passed, 316 deselected in 854.14s (0:14:14)"
    assert c["failing"] == [
        "harness/tests/test_run_driver_whence_health_check.py::"
        "test_whence_health_check_fail_logged_when_script_fails"]
    line = health_log_line("round 362: health-check", p, 1)
    assert "test_run_driver_whence_health_check" in line
    assert "test_self_eval" not in line


def test_an_echoed_status_cannot_make_ran_tests_true(tmp_path):
    """The contamination path, which has never fired and is one wording
    change away from firing.

    `ran_tests` used to scan the WHOLE file. Today neither `slowtier status`
    nor `pristine_check status` prints a bare `<n> passed` pair (checked
    against all 136 archived harness health logs: zero), so no verdict was
    ever wrong — but a run that aborts before collecting anything, followed
    by an echo that happens to print one, would be classified as a suite
    that ran and failed. The boundary removes the possibility instead of
    re-checking the wording each time either printer changes.
    """
    text = ("wrapper: something went sideways\n"
            + MEASURED_END_SENTINEL + "\n"
            + "recorded: 70 passed in 509.47s\n")
    p = _health_log(tmp_path, "h.log", text)
    c = classify_health_log(p, 1)
    assert c["outcome"] == "error"
    assert c["ran_tests"] is False
    assert "no test counts" in c["reason"]


def test_the_sentinel_recovers_a_boundary_a_count_line_cannot(tmp_path):
    """Round 348's shape (pytest exit 4, no counts at all) with the echo
    below it. Without the sentinel the fallback is the last line, which is
    the echo; with it, the config error is quoted."""
    text = (REAL_348_ERROR + MEASURED_END_SENTINEL + "\n"
            + "ref HEAD (91acd9c5af97)   verdict clean\n")
    p = _health_log(tmp_path, "h.log", text)
    c = classify_health_log(p, 4)
    assert c["outcome"] == "error"
    assert "optional-dependencies" in c["summary"]
    assert c["summary_source"] == "last-line"    # honest: not a pytest line
    assert "verdict clean" not in health_log_line("x", p, 4)


def test_split_measured_output_leaves_a_plain_pytest_log_alone(tmp_path):
    """Round 349's fixtures must keep meaning exactly what they meant: the
    whence check appends nothing, and 130 of its lines in driver.log are
    correct."""
    measured, echoed, boundary = split_measured_output(REAL_347_PASS)
    assert echoed == "" and boundary == "none"
    assert measured.strip().endswith("1022 passed, 48 deselected in 35.62s")
    measured, echoed, boundary = split_measured_output(REAL_348_ERROR)
    assert echoed == "" and measured == REAL_348_ERROR and boundary == "none"


def test_run_tests_fast_prints_the_sentinel_driver_health_looks_for():
    """The printer and the parser are in different languages and different
    files; this is the only thing that keeps them the same string."""
    harness_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(harness_dir, "run_tests_fast.sh")
    text = open(script, encoding="utf-8").read()
    assert 'echo "%s"' % MEASURED_END_SENTINEL in text, script
    # ...and that it is printed BEFORE the two status echoes, or the
    # boundary is in the wrong place.
    assert text.index(MEASURED_END_SENTINEL) < text.index("slowtier.py status")
    assert text.index(MEASURED_END_SENTINEL) < text.index("pristine_check.py status")


def test_the_sentinel_upgrades_the_guess_to_a_read_boundary(tmp_path):
    """Same log, with and without the line round 379 taught the script to
    print. The QUOTE is the same either way; what changes is whether the
    module had to infer where the run ended."""
    without = _health_log(tmp_path, "a.log", REAL_378_HARNESS)
    head, _, tail = REAL_378_HARNESS.partition(
        "587 passed, 323 deselected in 47.51s\n")
    with_sentinel = _health_log(
        tmp_path, "b.log", head + "587 passed, 323 deselected in 47.51s\n"
        + MEASURED_END_SENTINEL + "\n" + tail)
    a, b = classify_health_log(without, 0), classify_health_log(with_sentinel, 0)
    assert a["summary"] == b["summary"] == "587 passed, 323 deselected in 47.51s"
    assert a["summary_source"] == "count-line-guess"
    assert b["summary_source"] == "pytest-summary"


def test_a_non_pytest_log_is_out_of_contract_and_says_so(tmp_path):
    """`skills/run_checks_fast.sh` writes a log whose LAST line is its real
    verdict and whose second-to-last line happens to be a pytest count from
    a checker it ran. Round 363 gave that check its own formatter
    (`corpus_check.py --line`) precisely because this classifier is
    pytest-shaped, so the driver never brings such a log here — but a round
    replaying `logs/` might, and the count-line boundary would silently drop
    the verdict line. It is reported as a guess for that reason.

    Transcribed from the real `logs/skills_health_round_378.log`.
    """
    text = ("carryforward       warn K004              carryforward: 58 bank(s)\n"
            "unit_tests         ok                     610 passed in 104.27s (0:01:44)\n"
            "corpus-check: 7 checker(s), 0 error(s), 4 warning(s)\n")
    p = _health_log(tmp_path, "s.log", text)
    c = classify_health_log(p, 1)
    assert c["summary_source"] == "count-line-guess"
    assert c["summary"].startswith("unit_tests")


def test_health_replay_re_derives_one_line_per_log(tmp_path, capsys):
    """`driver.log`'s health lines were written once, live, and 38 of them
    quote an echo. The logs they were written from are still on disk, so the
    history is recoverable — this is the command that recovers it."""
    a = _health_log(tmp_path, "health_round_378.log", REAL_378_HARNESS)
    b = _health_log(tmp_path, "health_round_362.log", REAL_362_HARNESS)
    rc = driver_health.main(["health_replay", a, b])
    out = capsys.readouterr().out.splitlines()
    assert rc == 0
    assert out[0] == "round 378 PASS (587 passed, 323 deselected in 47.51s)"
    assert out[1].startswith("round 362 FAIL — tests ran and failed — "
                             "1 failed, 544 passed, 316 deselected")
    assert "test_run_driver_whence_health_check" in out[1]
    # A path with no round number in it still produces a line, not a crash.
    c = _health_log(tmp_path, "other.log", REAL_347_PASS)
    driver_health.main(["health_replay", c])
    assert capsys.readouterr().out.startswith("round ? PASS (1022 passed")


def test_health_replay_without_arguments_is_a_usage_error(capsys):
    assert driver_health.main(["health_replay"]) == 2
    assert "usage" in capsys.readouterr().err


# --- Round 391 (harness A): the turn budget ---------------------------------
#
# Every fixture below is shaped from a REAL log on this box, not invented.
# Round 145's lesson is the reason: the original per-turn thinking-token
# test passed against a fixture whose STRUCTURE had never been checked
# against a call that exercised the path, and the always-0 bug survived it
# for twelve rounds. `logs/round-*.json` is gitignored, so these carry the
# real shapes inline rather than reading the files.

# The shape a BATCHED turn really has, copied from `logs/round-390.json`:
# two separate `type:"assistant"` events sharing ONE `message.id`, each
# carrying exactly one `tool_use` block. This is the whole finding — the
# CLI charges one turn for the pair.
BATCHED_A = {
    "type": "assistant", "parent_tool_use_id": None,
    "session_id": "2cc8af67", "request_id": "req_1",
    "message": {
        "id": "msg_011CeaLRG4Gk1ABt2kMAaD1Q", "role": "assistant",
        "model": "claude-opus-5",
        "content": [{"type": "tool_use", "name": "Bash", "id": "t1", "input": {}}],
        "usage": {"output_tokens": 40},
    },
    "timestamp": "2026-08-31T06:20:00.000Z",
}
BATCHED_B = {
    "type": "assistant", "parent_tool_use_id": None,
    "session_id": "2cc8af67", "request_id": "req_1",
    "message": {
        "id": "msg_011CeaLRG4Gk1ABt2kMAaD1Q", "role": "assistant",
        "model": "claude-opus-5",
        "content": [{"type": "tool_use", "name": "Bash", "id": "t2", "input": {}}],
        "usage": {"output_tokens": 40},
    },
    "timestamp": "2026-08-31T06:20:10.000Z",
}
# The two block kinds that inflate `assistant_turns` without spending a
# turn: both are their own events, both share the batch's message id.
THINKING_EVENT = {
    "type": "assistant", "parent_tool_use_id": None,
    "message": {
        "id": "msg_011CeaLRG4Gk1ABt2kMAaD1Q", "role": "assistant",
        "content": [{"type": "thinking", "thinking": "", "signature": "x"}],
        "usage": {"output_tokens": 2},
    },
    "timestamp": "2026-08-31T06:19:50.000Z",
}
TEXT_EVENT = {
    "type": "assistant", "parent_tool_use_id": None,
    "message": {
        "id": "msg_011CeaLRG4Gk1ABt2kMAaD1Q", "role": "assistant",
        "content": [{"type": "text", "text": "Checking both at once."}],
        "usage": {"output_tokens": 9},
    },
    "timestamp": "2026-08-31T06:19:55.000Z",
}


def _turn(msg_id, ts, n_blocks=1, parent=None):
    return {
        "type": "assistant", "parent_tool_use_id": parent,
        "message": {
            "id": msg_id, "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "Bash", "id": "%s-%d" % (msg_id, i), "input": {}}
                for i in range(n_blocks)
            ],
            "usage": {"output_tokens": 40},
        },
        "timestamp": ts,
    }


# `result.terminal_reason` and `stop_reason` copied from
# `logs/round-339.json`'s real max-turns result.
MAXTURNS_RESULT = {
    "type": "result", "subtype": "error_max_turns", "is_error": True,
    "num_turns": 136, "session_id": "b1516798", "stop_reason": "tool_use",
    "terminal_reason": "max_turns", "queued_turn_count": 0,
}
SECOND_INIT = {
    "type": "system", "subtype": "init", "session_id": "b1516798",
    "cwd": "/home/pgain/agi-research-nuc-llm", "claude_code_version": "2.1.246",
    "model": "claude-opus-5",
}


def test_split_sessions_charges_one_turn_for_a_batch(tmp_path):
    """THE finding. Two parallel Bash calls arrive as two assistant events
    sharing one `message.id`; `--max-turns` charges ONE. `tool_calls`
    (round 205's "tight proxy") reads 2 for the same turn.
    """
    p = _write_ndjson(str(tmp_path), "a.json",
                      [REAL_INIT_LINE, BATCHED_A, BATCHED_B, REAL_RESULT_LINE])
    (s,) = split_sessions(p)
    assert s["turns"] == 1
    assert s["tool_calls"] == 2
    assert s["batch_ratio"] == 2.0


def test_split_sessions_charges_one_turn_for_a_multi_block_message(tmp_path):
    """The other on-disk spelling of the same thing: one assistant event
    whose `content` holds two `tool_use` blocks. Same verdict, and it is
    the shape `test_summarize_turns_counts_thinking_tokens_and_tool_calls`
    has asserted `tool_calls == 2` against since round 133 — that
    assertion stays true and stays a tool-call count, not a turn count.
    """
    p = _write_ndjson(str(tmp_path), "a.json",
                      [REAL_INIT_LINE, _turn("m1", "2026-08-31T06:20:00.000Z", n_blocks=2),
                       REAL_RESULT_LINE])
    (s,) = split_sessions(p)
    assert s["turns"] == 1
    assert s["tool_calls"] == 2


def test_split_sessions_ignores_thinking_and_text_events(tmp_path):
    """Why `assistant_turns` overstates by ~80% on real logs: thinking and
    text blocks are their own events. Four assistant events here, ONE turn.
    """
    p = _write_ndjson(str(tmp_path), "a.json",
                      [REAL_INIT_LINE, THINKING_EVENT, TEXT_EVENT, BATCHED_A,
                       BATCHED_B, REAL_RESULT_LINE])
    (s,) = split_sessions(p)
    assert s["assistant_blocks"] == 4
    assert s["turns"] == 1
    assert s["tool_calls"] == 2
    assert summarize_turns(p)["assistant_turns"] == 4


def test_split_sessions_splits_at_a_second_init(tmp_path):
    """`logs/round-339.json`'s real shape: a max-turns death, then a fresh
    `system/init` under the SAME session_id (the harness re-invoking the
    agent after a background task finished), then more turns and no second
    result because the outer timeout killed it.
    """
    p = _write_ndjson(str(tmp_path), "a.json", [
        REAL_INIT_LINE,
        _turn("m1", "2026-08-31T06:00:00.000Z"),
        _turn("m2", "2026-08-31T06:41:12.918Z"),
        MAXTURNS_RESULT,
        SECOND_INIT,
        _turn("m3", "2026-08-31T06:45:00.000Z"),
        _turn("m4", "2026-08-31T06:48:39.499Z"),
    ])
    first, second = split_sessions(p)
    assert first["turns"] == 2
    assert first["result_subtype"] == "error_max_turns"
    assert first["interrupted"] is False
    assert first["span_s"] == pytest.approx(2472.918, abs=0.01)
    assert second["turns"] == 2
    assert second["result_subtype"] is None
    assert second["interrupted"] is True
    assert second["span_s"] == pytest.approx(219.499, abs=0.01)


def test_summarize_turns_interrupted_is_still_whole_file(tmp_path):
    """Round 334's item 5, applied: `interrupted` keeps its published
    meaning (no result ANYWHERE in the file) even though that reads False
    for round 339, whose round really did die with no result. The
    per-session truth is reachable and is NOT a redefinition of a field
    three rounds of driver.log figures already use.
    """
    p = _write_ndjson(str(tmp_path), "a.json", [
        REAL_INIT_LINE, _turn("m1", "2026-08-31T06:00:00.000Z"), MAXTURNS_RESULT,
        SECOND_INIT, _turn("m2", "2026-08-31T06:45:00.000Z"),
    ])
    assert summarize_turns(p)["interrupted"] is False
    assert split_sessions(p)[-1]["interrupted"] is True


def test_split_sessions_excludes_subagent_turns(tmp_path):
    """A turn made by a delegated subagent carries `parent_tool_use_id` and
    does not spend the main loop's budget.

    FORWARD-GUARD ONLY, and this test is the only thing that exercises it:
    zero events in the 238 `logs/round-*.json` on this box have a truthy
    `parent_tool_use_id`, because the driver's `--allowedTools` list has
    never included a delegating tool. If that list ever gains one, this is
    what keeps `turns` comparable to `--max-turns`.
    """
    p = _write_ndjson(str(tmp_path), "a.json", [
        REAL_INIT_LINE,
        _turn("m1", "2026-08-31T06:00:00.000Z"),
        _turn("sub1", "2026-08-31T06:00:10.000Z", parent="toolu_abc"),
        _turn("sub2", "2026-08-31T06:00:20.000Z", n_blocks=3, parent="toolu_abc"),
        REAL_RESULT_LINE,
    ])
    (s,) = split_sessions(p)
    assert s["turns"] == 1
    assert s["tool_calls"] == 1
    assert s["assistant_blocks"] == 3


def test_turn_budget_sees_a_max_turns_death_that_is_not_the_last_result(tmp_path):
    """Rounds 349 and 378 on this box: hit `--max-turns`, were re-invoked
    when a background task completed, finished cleanly, and were logged as
    plain successes. `is_max_turns` goes through `load_round_result`, which
    takes the LAST result, so it cannot see the death.
    """
    p = _write_ndjson(str(tmp_path), "a.json", [
        REAL_INIT_LINE, _turn("m1", "2026-08-31T06:00:00.000Z"), MAXTURNS_RESULT,
        SECOND_INIT, _turn("m2", "2026-08-31T06:45:00.000Z"),
        dict(REAL_RESULT_LINE, num_turns=27),
    ])
    assert is_max_turns(p) is False
    assert classify_round_log(p) == "ok"
    tb = turn_budget(p)
    assert tb["max_turns_hit"] is True
    assert tb["sessions"] == 2
    assert tb["num_turns"] == 27


def test_turn_budget_turns_is_the_last_session_and_turns_all_is_the_sum(tmp_path):
    p = _write_ndjson(str(tmp_path), "a.json", [
        REAL_INIT_LINE,
        _turn("m1", "2026-08-31T06:00:00.000Z"),
        _turn("m2", "2026-08-31T06:00:10.000Z"),
        MAXTURNS_RESULT,
        SECOND_INIT,
        _turn("m3", "2026-08-31T06:45:00.000Z"),
        REAL_RESULT_LINE,
    ])
    tb = turn_budget(p)
    assert tb["turns"] == 1
    assert tb["turns_all"] == 3
    assert tb["sessions"] == 2


def test_turn_budget_single_session_turns_equals_turns_all(tmp_path):
    """234 of the 238 logs on this box are this case, where the old
    whole-file reading and the session-aware one agree.
    """
    p = _write_ndjson(str(tmp_path), "a.json", [
        REAL_INIT_LINE, BATCHED_A, BATCHED_B,
        _turn("m9", "2026-08-31T06:30:00.000Z"), REAL_RESULT_LINE,
    ])
    tb = turn_budget(p)
    assert tb["sessions"] == 1
    assert tb["turns"] == tb["turns_all"] == 2
    assert tb["tool_calls"] == 3
    assert tb["batch_ratio"] == 1.5
    assert tb["max_turns_hit"] is False


def test_headroom_reports_the_work_the_budget_did_not_charge_for(tmp_path):
    p = _write_ndjson(str(tmp_path), "a.json",
                      [REAL_INIT_LINE, BATCHED_A, BATCHED_B, REAL_RESULT_LINE])
    h = headroom(p, 135)
    assert h["turns"] == 1
    assert h["tool_calls"] == 2
    assert h["turns_saved"] == 1
    assert h["remaining"] == 134
    assert h["serial_would_have_died"] is False


def test_headroom_flags_a_round_batching_alone_kept_alive(tmp_path):
    """Round 345's real numbers: 107 turns, 137 tool calls, cap 135. It
    finished. Un-batched it would have needed 137 turns and died — one of
    FOURTEEN finished rounds on this box in that position, none of which
    batched on purpose.
    """
    events = [REAL_INIT_LINE]
    for i in range(107):
        n = 2 if i < 30 else 1
        events.append(_turn("m%d" % i, "2026-08-31T06:%02d:00.000Z" % (i % 60), n_blocks=n))
    events.append(REAL_RESULT_LINE)
    p = _write_ndjson(str(tmp_path), "a.json", events)
    h = headroom(p, 135)
    assert h["turns"] == 107
    assert h["tool_calls"] == 137
    assert h["turns_saved"] == 30
    assert h["remaining"] == 28
    assert h["serial_would_have_died"] is True
    assert h["max_turns_hit"] is False


def test_summarize_turns_keeps_its_four_original_keys_unchanged(tmp_path):
    """Round 334's item 5 as a regression pin: the keys rounds have already
    published keep their exact prior values. `assistant_turns` still counts
    EVENTS (4 here, not 1); `tool_calls` still counts BLOCKS (2, not 1);
    `span_s` still spans the whole file across a session boundary.
    """
    p = _write_ndjson(str(tmp_path), "a.json", [
        REAL_INIT_LINE, THINKING_EVENT, TEXT_EVENT, BATCHED_A, BATCHED_B,
        MAXTURNS_RESULT, SECOND_INIT,
        _turn("m2", "2026-08-31T06:50:00.000Z"), REAL_RESULT_LINE,
    ])
    s = summarize_turns(p)
    assert s["assistant_turns"] == 5
    assert s["tool_calls"] == 3
    assert s["span_s"] == pytest.approx(1810.0, abs=0.01)
    assert s["interrupted"] is False


def test_summarize_turns_gains_the_turn_budget_keys(tmp_path):
    """`run_driver.sh` logs this dict verbatim, so `driver.log` gains the
    real turn count with no change to the driver script.
    """
    p = _write_ndjson(str(tmp_path), "a.json",
                      [REAL_INIT_LINE, BATCHED_A, BATCHED_B, MAXTURNS_RESULT])
    s = summarize_turns(p)
    assert s["turns"] == 1
    assert s["sessions"] == 1
    assert s["num_turns"] == 136
    assert s["max_turns_hit"] is True
    assert s["batch_ratio"] == 2.0
    # and the old keys are still there, in their original order
    assert list(s)[:5] == [
        "assistant_turns", "thinking_tokens", "tool_calls", "span_s", "interrupted",
    ]


def test_split_sessions_handles_a_log_with_no_init(tmp_path):
    """Older on-disk shapes (and a stream truncated at the head) have no
    `init`; that is still exactly one session, not zero.
    """
    p = _write_ndjson(str(tmp_path), "a.json",
                      [_turn("m1", "2026-08-31T06:00:00.000Z"), REAL_RESULT_LINE])
    (s,) = split_sessions(p)
    assert s["turns"] == 1
    assert s["result_subtype"] == "success"


def test_split_sessions_drops_a_trailing_empty_session(tmp_path):
    """A log ending in an `init` with nothing after it (the driver killed
    between re-invocation and the first turn) must not produce a phantom
    zero-turn session — `turn_budget`'s `turns` reads the LAST one.
    """
    p = _write_ndjson(str(tmp_path), "a.json", [
        REAL_INIT_LINE, _turn("m1", "2026-08-31T06:00:00.000Z"),
        MAXTURNS_RESULT, SECOND_INIT,
    ])
    sessions = split_sessions(p)
    assert len(sessions) == 1
    assert turn_budget(p)["turns"] == 1


def test_split_sessions_none_on_missing_file(tmp_path):
    assert split_sessions(os.path.join(str(tmp_path), "nope.json")) is None
    assert turn_budget(os.path.join(str(tmp_path), "nope.json")) is None
    assert headroom(os.path.join(str(tmp_path), "nope.json"), 135) is None


def test_split_sessions_empty_on_plain_json_shape(tmp_path):
    """The pre-round-133 `--output-format json` shape has no per-event data
    at all, so there is no turn budget to read — and `summarize_turns`
    keeps returning None for it, exactly as before.
    """
    p = _write(str(tmp_path), "a.json", {"is_error": False, "subtype": "success"})
    assert turn_budget(p) is None
    assert summarize_turns(p) is None


def test_turn_budget_batch_ratio_is_none_when_no_turns(tmp_path):
    p = _write_ndjson(str(tmp_path), "a.json",
                      [REAL_INIT_LINE, TEXT_EVENT, REAL_RESULT_LINE])
    tb = turn_budget(p)
    assert tb["turns"] == 0
    assert tb["batch_ratio"] is None


def test_span_seconds_helper(tmp_path):
    assert _span_seconds([]) is None
    assert _span_seconds(["2026-08-31T06:00:00.000Z"]) is None
    assert _span_seconds(
        ["2026-08-31T06:00:00.000Z", "2026-08-31T06:00:10.500Z"]
    ) == pytest.approx(10.5, abs=0.001)
    assert _span_seconds(["not-a-time", "2026-08-31T06:00:10.000Z"]) is None


def test_turn_budget_cli_subcommands(tmp_path):
    def run(*args):
        out = subprocess.run(
            [sys.executable, "-m", "harness.driver_health", *args],
            cwd=os.path.join(HERE, "..", ".."), capture_output=True, text=True, timeout=30,
        )
        assert out.returncode == 0, out.stderr
        return out.stdout.strip()

    p = _write_ndjson(str(tmp_path), "round-390.json",
                      [REAL_INIT_LINE, BATCHED_A, BATCHED_B, MAXTURNS_RESULT])
    tb = json.loads(run("turnbudget", p))
    assert tb["turns"] == 1 and tb["max_turns_hit"] is True
    h = json.loads(run("headroom", p, "135"))
    assert h["turns_saved"] == 1 and h["remaining"] == 134

    old = _write_ndjson(str(tmp_path), "round-182.json",
                        [REAL_INIT_LINE, _turn("m1", "2026-08-31T06:00:00.000Z"),
                         MAXTURNS_RESULT])
    sweep = run("budgetsweep", p, old).splitlines()
    assert sweep[0].split()[:3] == ["round", "cap", "turns"]
    # round 205 raised --max-turns 120 -> 135, so the cap a sweep compares
    # against depends on the round number in the filename.
    assert sweep[1].split()[:2] == ["390", "135"]
    assert sweep[2].split()[:2] == ["182", "120"]


def test_budgetsweep_reports_na_for_a_log_with_no_events(tmp_path):
    p = _write(str(tmp_path), "round-152.json", {"is_error": False, "subtype": "success"})
    out = subprocess.run(
        [sys.executable, "-m", "harness.driver_health", "budgetsweep", p],
        cwd=os.path.join(HERE, "..", ".."), capture_output=True, text=True, timeout=30,
    )
    assert out.returncode == 0, out.stderr
    # cap 120, not 135: round 152 is on the pre-round-205 side of the raise,
    # which is also what the 34 real event-less logs on this box look like.
    assert out.stdout.splitlines()[1].split()[:3] == ["152", "120", "n/a"]


def test_all_max_turns_sees_a_cap_hit_in_a_non_final_session(tmp_path):
    """Round 391's widening of the safety valve. A log whose FIRST session
    died at the cap and whose second session failed some other way reads
    `is_max_turns == False` (that goes through `load_round_result`, which
    takes the last result), so the valve would have called a still
    workload-driven cluster a quota outage and stopped the driver — the
    exact false positive that cost two manual restarts at rounds 146/147
    and 149/150.
    """
    logs = []
    for i in range(3):
        logs.append(_write_ndjson(str(tmp_path), "round-%d.json" % (400 + i), [
            REAL_INIT_LINE, _turn("m1", "2026-08-31T06:00:00.000Z"), MAXTURNS_RESULT,
            SECOND_INIT, _turn("m2", "2026-08-31T06:45:00.000Z"),
            {"type": "result", "subtype": "error_during_execution",
             "is_error": True, "num_turns": 4},
        ]))
    for p in logs:
        assert classify_round_log(p) == "bad"
        assert is_max_turns(p) is False          # the blind spot
        assert driver_health._hit_max_turns_anywhere(p) is True
    assert all_max_turns(logs) is True           # valve keeps the driver alive


def test_all_max_turns_still_stops_on_a_genuine_non_max_turns_cluster(tmp_path):
    """The widening must not make the valve stop stopping. A cluster with
    no cap hit anywhere is still a quota/outage signal.
    """
    logs = [
        _write(str(tmp_path), "round-%d.json" % (410 + i),
               {"is_error": True, "subtype": "error", "api_error_status": 429})
        for i in range(3)
    ]
    for p in logs:
        assert classify_round_log(p) == "bad"
    assert all_max_turns(logs) is False


def test_all_max_turns_unchanged_for_single_session_logs(tmp_path):
    """234 of the 238 logs on this box: the widened test and the original
    agree exactly.
    """
    hit = _write_ndjson(str(tmp_path), "round-420.json", [
        REAL_INIT_LINE, _turn("m1", "2026-08-31T06:00:00.000Z"), MAXTURNS_RESULT])
    other = _write(str(tmp_path), "round-421.json",
                   {"is_error": True, "subtype": "error_during_execution"})
    assert is_max_turns(hit) is driver_health._hit_max_turns_anywhere(hit) is True
    assert is_max_turns(other) is driver_health._hit_max_turns_anywhere(other) is False
    assert all_max_turns([hit]) is True
    assert all_max_turns([hit, other]) is False


# --------------------------------------------------------------------------
# Round 451 (harness A) — the corpus check's blind spot, watched from outside.
#
# `skills/.../test_corpus_check.py::TestLiveCorpus::test_every_checker_
# actually_ran` asserts `status == "ran"` for every checker and CANNOT see
# `unit_tests`: it runs inside `unit_tests`, so the re-entry guard drops that
# checker from `checks()`, and the test asserts `assertNotIn("unit_tests")` to
# make the exclusion explicit. `unit_tests` then timed out in rounds 431, 445,
# 448, 449 and 450 with nothing in the repo going red.
#
# These tests read `driver.log`, which holds the OUTER verdict the guard never
# touches. They live in `harness/` for the same reason: a checker cannot be
# its own witness.

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
DRIVER_LOG = os.path.join(REPO, "logs", "driver.log")
BROKEN_REGISTRY = os.path.join(REPO, "state", "known-broken-checker-rounds.json")

_PASS_LINE = ("[2026-09-02 04:00:00] round 444: skills-check PASS "
              "(corpus-check: 10 checker(s), 0 error(s), 7 warning(s); "
              "coverage: verb_audit 20/103 verbs)\n")
_BROKEN_LINE = ("[2026-09-02 08:28:43] round 449: skills-check ERROR — a "
                "checker could not run — unit_tests TIMEOUT timed out after "
                "600s corpus-check: 10 checker(s), 0 error(s), 8 warning(s); "
                "COULD NOT RUN: unit_tests; coverage: verb_audit 20/105 verbs\n")


def _log(tmp_path, text):
    p = os.path.join(str(tmp_path), "driver.log")
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


class TestBrokenCheckerHistory:
    def test_a_broken_round_is_found_and_attributed_to_its_checker(self, tmp_path):
        h = driver_health.corpus_check_broken_history(
            _log(tmp_path, _PASS_LINE + _BROKEN_LINE))
        assert h["rounds"] == {449: ["unit_tests"]}
        assert h["checkers"] == {"unit_tests": [449]}

    def test_the_denominator_is_published(self, tmp_path):
        """Round 339's rule. A sweep that finds nothing has to be able to say
        whether it looked at anything — otherwise a log the parser cannot read
        at all reports exactly like a clean one."""
        h = driver_health.corpus_check_broken_history(
            _log(tmp_path, _PASS_LINE + _BROKEN_LINE))
        assert h["n_skills_check_lines"] == 2

    def test_a_clean_log_and_an_absent_log_do_not_read_the_same(self, tmp_path):
        clean = driver_health.corpus_check_broken_history(
            _log(tmp_path, _PASS_LINE))
        missing = driver_health.corpus_check_broken_history(
            os.path.join(str(tmp_path), "nope.log"))
        assert clean["rounds"] == missing["rounds"] == {}
        assert clean["n_skills_check_lines"] == 1
        assert missing["n_skills_check_lines"] == 0

    def test_several_broken_checkers_on_one_line_all_land(self, tmp_path):
        line = _BROKEN_LINE.replace("COULD NOT RUN: unit_tests",
                                    "COULD NOT RUN: unit_tests,xref_check")
        h = driver_health.corpus_check_broken_history(_log(tmp_path, line))
        assert h["rounds"] == {449: ["unit_tests", "xref_check"]}
        assert sorted(h["checkers"]) == ["unit_tests", "xref_check"]

    def test_a_health_check_line_that_is_not_skills_check_is_ignored(self, tmp_path):
        # `health-check` and `whence-health-check` lines share the log and
        # must not be counted into this denominator.
        other = ("[2026-09-02 08:28:43] round 449: health-check PASS "
                 "(1238 passed, 352 deselected in 888.64s)\n")
        h = driver_health.corpus_check_broken_history(_log(tmp_path, other))
        assert h["n_skills_check_lines"] == 0


class TestBrokenCheckerAcknowledgement:
    def test_an_acknowledged_round_is_quiet(self, tmp_path):
        reg = os.path.join(str(tmp_path), "reg.json")
        with open(reg, "w", encoding="utf-8") as f:
            json.dump({"acknowledged_rounds": [449]}, f)
        assert driver_health.unacknowledged_broken_checker_rounds(
            _log(tmp_path, _BROKEN_LINE), reg) == {}

    def test_an_unacknowledged_round_is_loud(self, tmp_path):
        reg = os.path.join(str(tmp_path), "reg.json")
        with open(reg, "w", encoding="utf-8") as f:
            json.dump({"acknowledged_rounds": [431]}, f)
        assert driver_health.unacknowledged_broken_checker_rounds(
            _log(tmp_path, _BROKEN_LINE), reg) == {449: ["unit_tests"]}

    def test_a_missing_registry_acknowledges_nothing(self, tmp_path):
        """Failing OPEN here would mean deleting one file turns the check
        green — the exact failure this check exists to prevent."""
        assert driver_health.unacknowledged_broken_checker_rounds(
            _log(tmp_path, _BROKEN_LINE),
            os.path.join(str(tmp_path), "gone.json")) == {449: ["unit_tests"]}

    def test_a_corrupt_registry_acknowledges_nothing(self, tmp_path):
        reg = os.path.join(str(tmp_path), "reg.json")
        with open(reg, "w", encoding="utf-8") as f:
            f.write("{not json")
        assert driver_health.unacknowledged_broken_checker_rounds(
            _log(tmp_path, _BROKEN_LINE), reg) == {449: ["unit_tests"]}


@pytest.mark.skipif(not os.path.exists(DRIVER_LOG),
                    reason="no driver.log in this checkout")
class TestBrokenCheckerLiveRecord:
    def test_the_live_log_has_no_unacknowledged_broken_checker(self):
        """THE ENFORCEMENT, and the thing that was missing for five rounds.

        Red means `skills-check` reported COULD NOT RUN in a round that
        `state/known-broken-checker-rounds.json` does not account for. The
        repair is to find out why that checker could not run — not to append
        the round number here.
        """
        found = driver_health.unacknowledged_broken_checker_rounds(
            DRIVER_LOG, BROKEN_REGISTRY)
        assert found == {}, (
            "skills-check reported COULD NOT RUN in unacknowledged round(s): "
            "%s\n%s\nThe repair is to find out why -- round 487 measured the "
            "first three: 183.92 s of work killed at a 600 s budget by the "
            "driver's own four-way concurrency on nproc 1."
            % (found, driver_health.broken_checker_report(
                DRIVER_LOG, BROKEN_REGISTRY)))

    def test_the_acknowledgement_is_not_vacuous(self):
        """Guards the assertion above against passing because the parser
        stopped finding anything — the failure mode a health check must not
        have. Every acknowledged round must still be visible in the log.
        """
        history = driver_health.corpus_check_broken_history(DRIVER_LOG)
        assert history["n_skills_check_lines"] > 0
        with open(BROKEN_REGISTRY, encoding="utf-8") as f:
            known = {int(r) for r in json.load(f)["acknowledged_rounds"]}
        assert known, "registry acknowledges nothing; the check is vacuous"
        assert known <= set(history["rounds"]), (
            "registry acknowledges round(s) the log does not show as broken: "
            "%s — a stale acknowledgement is a silencer nobody is watching"
            % sorted(known - set(history["rounds"])))


class TestBrokenCheckerPartialVerdict(unittest.TestCase):
    """Round 487 (harness A). WHAT the killed checker saw, not just THAT it died.

    Rounds 483, 485 and 486 each logged `unit_tests TIMEOUT` and nothing
    else, while `logs/corpus-evidence/round-486/unit_tests.out` held a pytest
    progress bar with five `F`s already in it. `corpus_check.partial_clause`
    now writes those counts onto the aggregate line the driver copies into
    `driver.log`; these read them back.
    """

    LINE = ("[t] round 490: skills-check ERROR — a checker could not run — "
            "unit_tests TIMEOUT timed out after 1104s; 1020 test(s) seen "
            "through 93%, 5 failed, 0 errored; 15 line(s) before the kill "
            "corpus-check: 10 checker(s), 0 error(s), 8 warning(s); "
            "COULD NOT RUN: unit_tests; coverage: none published; "
            "partial: unit_tests 1020 seen/5 failed; budget: unit_tests "
            "1105s/1104s (100%)")

    def _log(self, *lines):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "driver.log")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return path, tmp

    def test_the_counts_are_read_back_off_the_driver_line(self):
        path, _ = self._log(self.LINE)
        self.assertEqual(driver_health.broken_checker_partials(path),
                         {490: {"unit_tests": {"seen": 1020, "failed": 5}}})

    def test_a_round_with_no_clause_is_absent_not_zero(self):
        # The distinction this whole round is about. A round logged before
        # the clause existed said NOTHING about failures; rendering that as
        # `failed: 0` would invent the reassuring half of the record.
        path, _ = self._log(
            "[t] round 486: skills-check ERROR — a checker could not run — "
            "unit_tests TIMEOUT timed out after 600s; 15 line(s) before the "
            "kill; COULD NOT RUN: unit_tests")
        self.assertEqual(driver_health.broken_checker_partials(path), {})

    def test_an_unreadable_log_is_empty_and_never_raises(self):
        self.assertEqual(driver_health.broken_checker_partials(
            os.path.join(tempfile.gettempdir(), "no-such-driver-487.log")), {})

    def test_the_report_names_the_failures_when_the_record_has_them(self):
        path, tmp = self._log(self.LINE)
        reg = os.path.join(tmp, "known.json")
        with open(reg, "w", encoding="utf-8") as f:
            f.write('{"acknowledged_rounds": []}')
        text = driver_health.broken_checker_report(path, reg)
        self.assertIn("round 490", text)
        self.assertIn("1020 test(s) seen, 5 failed", text)

    def test_the_report_says_so_when_the_record_has_none(self):
        path, tmp = self._log(
            "[t] round 486: skills-check ERROR — unit_tests TIMEOUT timed out "
            "after 600s; COULD NOT RUN: unit_tests")
        reg = os.path.join(tmp, "known.json")
        with open(reg, "w", encoding="utf-8") as f:
            f.write('{"acknowledged_rounds": []}')
        self.assertIn("no partial verdict in the record",
                      driver_health.broken_checker_report(path, reg))

    def test_an_acknowledged_round_is_not_reported(self):
        path, tmp = self._log(self.LINE)
        reg = os.path.join(tmp, "known.json")
        with open(reg, "w", encoding="utf-8") as f:
            f.write('{"acknowledged_rounds": [490]}')
        self.assertEqual(driver_health.broken_checker_report(path, reg), "")
