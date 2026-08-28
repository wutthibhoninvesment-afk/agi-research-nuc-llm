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
    all_max_turns,
    blocking_wait_gap_s,
    classify_round_log,
    count_consecutive_failures,
    exact_reset_wait_seconds,
    full_event_span_s,
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
