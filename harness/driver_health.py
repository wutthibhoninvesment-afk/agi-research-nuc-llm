"""Health checks for `run_driver.sh` — the meta-harness that runs each
research round as a `claude -p` subprocess and decides whether to keep going.

Extracted from an inline `xargs -I{} python3 -c "..."` pipeline in
run_driver.sh that silently NEVER RAN on this machine: macOS ships BSD
xargs, whose `-I` mode reconstructs and re-execs the whole command line per
input line under a small internal buffer (independent of ARG_MAX) — a
python3 one-liner of a few hundred characters overflows it and xargs prints
"xargs: command line cannot be assembled, too long" to stderr and exits
nonzero, emitting NOTHING on stdout. The driver redirected that stderr to
/dev/null and piped stdout into `grep -c bad || true`, so the failure was
invisible: `grep -c` on empty input returns 0, `FAILS` read as 0 forever,
and the "stop after 3 consecutive failures" safety valve never fired —
confirmed live on rounds 113-121 (8 consecutive HTTP 429s in ~6 minutes) and
122-126 (5 consecutive max-turns deaths, ~$17 of quota) despite both being
exactly the 3-in-a-row failure pattern the check exists to catch.

Fix: do the classification in ONE python3 process invoked with the log
paths as argv, no xargs at all.
"""

import json
import sys
import time
from datetime import datetime
from typing import List, Optional


def load_round_result(path: str) -> Optional[dict]:
    """Return the round's final `type: "result"` object, or None if the
    file is missing/unreadable/has no such object. Note: when the CLI
    emits `--output-format stream-json --verbose`, the result object is
    just the LAST event among many intermediate ones (system, assistant,
    user, tool_progress, rate_limit_event); use `load_round_events()` to
    inspect those intermediate events for diagnosing interrupted sessions.

    Two on-disk shapes exist and both must keep working: (1) the original
    `--output-format json` shape, the WHOLE FILE is that one object (every
    round through 133 on disk is this shape); (2) `--output-format
    stream-json --verbose` (round 133+, see `latest_rate_limit_reset_epoch`
    for why), where the file is newline-delimited JSON events and the
    result object is the LAST line. Tried as (1) first — a single
    `json.load` succeeds immediately on shape 1 and fails fast on shape 2
    (trailing data after the first object) without scanning every line.
    """
    try:
        with open(path) as f:
            text = f.read()
    except Exception:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    result = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("type") == "result":
            result = obj
    return result


def load_round_events(path: str) -> Optional[list]:
    """Return ALL JSON events from a round log (stream-json or single-format).

    Useful for diagnosing interrupted sessions where no final result was emitted.
    """
    try:
        with open(path) as f:
            text = f.read()
    except Exception:
        return None

    # Try single-JSON first
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return [obj]
    except Exception:
        pass

    # Fall back to newline-delimited JSON
    events = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
            if isinstance(obj, dict):
                events.append(obj)
        except Exception:
            continue

    return events if events else None


def has_real_ratelimit_signal(path: str) -> bool:
    """True iff the round log shows a REAL, structured rate-limit signal —
    either a 429 API error (`is_rate_limit`) or a `rate_limit_event` whose
    `utilization` for some window is >= 0.8.

    Replaces `run_driver.sh`'s former informational check, a blind
    `grep -qiE "usage limit|rate.?limit|weekly.*limit|5-hour|..."` over the
    ENTIRE round log text. That matches any embedded transcript CONTAINING
    those words, which is unavoidable the moment a round Reads
    `state/research-state.md` (whose own prose narrates the driver's
    rate-limit history at length) or this very module (whose docstrings
    say "rate limit" repeatedly) — nothing to do with whether a rate limit
    was actually hit. Confirmed live: rounds 146/147/149/150 all logged
    "quota/limit signal detected" from exactly this false-positive path
    while their real (and only) failure was an unrelated `error_max_turns`
    death; the misleading wording is what led a human operator to
    (wrongly) conclude the weekly limit had been reached, producing a
    premature `state/FINAL-REPORT.md` and two manual restarts. This
    function only fires on the CLI's own structured signals, which cannot
    be triggered by a round merely reading or writing text about limits.
    """
    if is_rate_limit(path):
        return True
    events = load_round_events(path) or []
    for e in events:
        if e.get("type") != "rate_limit_event":
            continue
        windows = (e.get("rate_limit_info") or {}).get("unifiedWindows") or {}
        for w in windows.values():
            if w.get("utilization", 0.0) >= 0.8:
                return True
    return False


def classify_round_log(path: str) -> str:
    """Return "bad" (a genuine failure the driver should count) or "ok".

    Enhanced for stream-json logs (round ≥133+): if the file has events
    (assistant turns, thinking tokens, etc.) but no final `type:"result"`
    object, treat it as a likely interrupted session (rate limit / network
    drop / process kill) rather than a hard failure — it's retryable ("ok").
    Only mark truly empty/corrupt files as "bad" in that no-result case.

    When a final result DOES exist, matches run_driver.sh's original
    per-file semantics exactly (this branch was silently DROPPED by an
    uncommitted, untested edit sometime around round 146-150 while adding
    the no-result handling above — the function fell off the end and
    returned `None` for every log with a result, success or failure alike,
    which made `count_consecutive_failures` unable to ever count a real
    failure; caught by 10 already-written tests going red, none of which
    had been run before this bug shipped): an `is_error` result whose
    `api_error_status` (or embedded `result` text) does not look like a
    transient 5xx/529 is "bad" — 5xx/529 is handled separately by the
    driver's own retry-with-backoff branch and must NOT also count toward
    the consecutive-failure stop, or a run of retryable server overloads
    would look identical to a real outage. A `max_turns` death also reads
    "bad" here (it IS a failed round) — see `is_max_turns`/`all_max_turns`
    for how the driver's safety valve avoids conflating a workload-driven
    max-turns cluster with an actual quota outage before deciding to stop.
    """
    d = load_round_result(path)
    if d is None:
        # For stream-json: check if Claude started working before being cut short
        events = load_round_events(path)
        if events and any(e.get("type") == "assistant" for e in events):
            # Has assistant content → Claude was working → likely rate-limited/interrupted
            return "ok"  # Retryable, not a fatal failure

        # Truly empty or corrupted file → genuine problem
        return "bad"
    try:
        is_err = bool(d.get("is_error", False))
        status = str(d.get("api_error_status", ""))
        result_text = str(d.get("result", ""))
        is_5xx = status.startswith("5") or "529" in result_text
        return "bad" if (is_err and not is_5xx) else "ok"
    except Exception:
        return "bad"


def count_consecutive_failures(paths: List[str]) -> int:
    """How many of the given round logs (most-recent-first) are "bad"."""
    return sum(1 for p in paths if classify_round_log(p) == "bad")


def is_max_turns(path: str) -> bool:
    """True iff the round log's final result is specifically a
    `--max-turns` interruption (`subtype == "error_max_turns"`), as
    opposed to a real API/quota error.

    Why this distinction exists (round 151): CURRICULUM.md says to stop
    the whole driver "only when the WEEKLY limit is reached" — a max-turns
    death is a WORKLOAD signal (the round needed more turns than the cap
    allows), not a quota signal, and conflating the two is exactly what
    happened live: rounds 146/147 (and again 149/150 on a second restart)
    each did 140-160 real turns of substantive work — SWE-loop campaigns,
    language work — hit `--max-turns 80`, and were misread by a human
    operator watching `driver.log`'s "3 consecutive failures — assuming
    weekly limit reached" message as an actual weekly-quota exhaustion.
    That produced a premature `state/FINAL-REPORT.md` and two manual
    restarts, both later noted as a "false-positive quota detection (not
    actual weekly limit)". See `all_max_turns` for how the safety valve
    uses this to stop only on a genuine outage/quota cluster.
    """
    d = load_round_result(path)
    if d is None:
        return False
    return d.get("subtype") == "error_max_turns"


def all_max_turns(paths: List[str]) -> bool:
    """True iff every one of the given round logs is BOTH classified "bad"
    (a real failure) AND specifically a max-turns death — i.e. the
    3-consecutive-failures cluster is entirely workload-driven, not a
    quota/outage cluster. False for an empty list (nothing to certify) and
    for any mix that includes a 429, a hard error, or a truly empty/corrupt
    log alongside the max-turns deaths — those cases keep the original
    "assume weekly limit, stop" behavior.
    """
    return bool(paths) and all(
        classify_round_log(p) == "bad" and is_max_turns(p) for p in paths
    )


def is_rate_limit(path: str) -> bool:
    """True iff the round log is an HTTP 429 (usage-limit) API error.

    A 429 is ambiguous FROM `api_error_status` ALONE: the CLI's error
    message (round 113-121's actual text was "You've reached your Fable 5
    limit...") names a MODEL's limit, but doesn't itself say whether that
    is the 5-hour rolling window CLAUDE.md/CURRICULUM.md say to "sleep
    until reset" for, or the weekly cap that should stop the driver for
    good. `latest_rate_limit_reset_epoch` resolves this with the CLI's own
    `rate_limit_event` data when available (stream-json logs only);
    `rate_limit_backoff_seconds` is the escalating-guess fallback for the
    older plain-json shape, which never emits that event at all. Any
    read/parse failure is NOT a rate limit — falls through to
    `classify_round_log`'s "bad" handling instead.
    """
    d = load_round_result(path)
    if d is None:
        return False
    return d.get("api_error_status") == 429


def latest_rate_limit_reset_epoch(path: str, window: str = "five_hour") -> Optional[float]:
    """Scan a `--output-format stream-json` round log for `rate_limit_event`
    lines and return the MOST RECENT one's `resetsAt` (epoch seconds) for
    the given window ("five_hour" or "seven_day"), or None if the log has
    no such event (the plain-json shape never does — it has no
    intermediate events at all, only the final result) or the window is
    absent from the last event seen.

    Verified live 2026-08-26 against a real `claude -p --output-format
    stream-json --verbose` call: `{"type":"rate_limit_event",
    "rate_limit_info":{"unifiedWindows":{"five_hour":{"utilization":0.01,
    "resetsAt":1787723400}, "seven_day":{"utilization":0.64,
    "resetsAt":1787954400}}}}` — `resetsAt` decodes (via
    `datetime.fromtimestamp(..., tz=utc)`) to a plausible near-future UTC
    instant (confirmed against wall-clock `now`, not assumed), settling
    that it is epoch SECONDS, not milliseconds.
    """
    try:
        with open(path) as f:
            text = f.read()
    except Exception:
        return None
    found = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("type") != "rate_limit_event":
            continue
        windows = (obj.get("rate_limit_info") or {}).get("unifiedWindows") or {}
        w = windows.get(window)
        if w and "resetsAt" in w:
            found = w["resetsAt"]
    return found


def exact_reset_wait_seconds(path: str, now: Optional[float] = None,
                              window: str = "five_hour",
                              floor_s: int = 30, ceiling_s: int = 7200) -> Optional[int]:
    """Seconds to sleep until the CLI's own reported reset time for
    `window`, clamped to [floor_s, ceiling_s] (a reset that already passed,
    or is absurdly far off from a clock skew or wrong window, must not
    turn into a zero-wait busy-retry or an unbounded sleep). None if no
    `rate_limit_event` was captured for this round (older plain-json logs,
    or a 429 that hit before the CLI ever emitted one) — caller should fall
    back to `rate_limit_backoff_seconds`'s guess schedule.
    """
    resets_at = latest_rate_limit_reset_epoch(path, window=window)
    if resets_at is None:
        return None
    if now is None:
        now = time.time()
    wait = int(resets_at - now)
    if wait < floor_s:
        wait = floor_s
    elif wait > ceiling_s:
        wait = ceiling_s
    return wait


# Escalating backoff for consecutive same-round 429 retries: 5m, 15m, 30m,
# 60m, 60m, 60m, 60m — sums to ~4.9h, matched to the "5-hour rolling limit"
# language in CLAUDE.md/CURRICULUM.md so a transient rolling-window block
# gets a real chance to clear before the caller gives up and treats it as
# the (unrecoverable-this-session) weekly cap.
RATE_LIMIT_BACKOFF_SCHEDULE = [300, 900, 1800, 3600, 3600, 3600, 3600]


def rate_limit_backoff_seconds(attempt: int) -> int:
    """Seconds to sleep before the Nth (1-indexed) consecutive same-round
    429 retry. Clamped to the schedule's ends: attempt < 1 behaves as 1,
    attempt beyond the schedule's length repeats its last (plateau) value
    rather than raising — the caller is responsible for capping the
    NUMBER of retries (`len(RATE_LIMIT_BACKOFF_SCHEDULE)`), not this
    function, so a caller with a bug in its own cap fails safe (a bounded
    1-hour sleep) instead of unbounded/instant retry.
    """
    idx = attempt - 1
    if idx < 0:
        idx = 0
    elif idx >= len(RATE_LIMIT_BACKOFF_SCHEDULE):
        idx = len(RATE_LIMIT_BACKOFF_SCHEDULE) - 1
    return RATE_LIMIT_BACKOFF_SCHEDULE[idx]


def summarize_turns(path: str) -> Optional[dict]:
    """Per-turn instrumentation for the OUTER `claude -p` round session —
    the piece round 127 flagged as missing (`agentloop/trace.py` already
    does this for the IN-harness agent loop, nothing did it for the round
    sessions the driver launches). Requires `--output-format stream-json`
    (the plain-json shape has no per-turn events at all, so this returns
    None for every log on disk before round 133); walks every `type:
    "assistant"` line, counting `tool_use` content blocks and spanning the
    first-to-last event `timestamp` for wall time.

    `thinking_tokens`: round 145 found LIVE, against 5 real round-133+ logs
    (140-144, one a genuine max-turns death with 33773 real thinking
    tokens per the final result), that no per-turn `assistant` event's
    `message.usage` EVER carries an `output_tokens_details` key at all —
    every one of 150+150+... real turns across those 5 logs lacks it
    entirely, not just zeros it. The original per-turn-sum implementation
    (round 133) was unit-tested against a fixture claiming to be "pinned
    verbatim from a real call" that happened to be a trivial ping/pong
    smoke test whose thinking_tokens really was 0 — the fixture's
    STRUCTURE (key present) was never checked against a call that actually
    thought, so the always-0 bug passed every test while reading 0 on
    every real production log since round 133 (driver.log rounds 140-144
    all show `"thinking_tokens": 0` despite real extensive reasoning).
    Fixed here by falling back to the final `type: "result"` event's
    aggregate `usage.output_tokens_details.thinking_tokens` (verified
    present and correct there) whenever the per-turn sum is 0 — the
    per-turn summation itself is left in place in case a future CLI
    version starts populating it per-turn, which would then win over the
    coarser aggregate automatically.
    """
    try:
        with open(path) as f:
            text = f.read()
    except Exception:
        return None
    assistant_turns = 0
    thinking_tokens = 0
    tool_calls = 0
    timestamps = []
    saw_assistant = False
    result_thinking_tokens = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("type") == "result":
            r_usage = obj.get("usage") or {}
            result_thinking_tokens = (r_usage.get("output_tokens_details") or {}).get("thinking_tokens")
            continue
        if obj.get("type") != "assistant":
            continue
        saw_assistant = True
        assistant_turns += 1
        msg = obj.get("message") or {}
        usage = msg.get("usage") or {}
        thinking_tokens += (usage.get("output_tokens_details") or {}).get("thinking_tokens", 0) or 0
        for block in msg.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tool_calls += 1
        ts = obj.get("timestamp")
        if ts:
            timestamps.append(ts)
    if not saw_assistant:
        return None
    if thinking_tokens == 0 and result_thinking_tokens:
        thinking_tokens = result_thinking_tokens
    span_s = None
    if len(timestamps) >= 2:
        try:
            t0 = datetime.fromisoformat(timestamps[0].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(timestamps[-1].replace("Z", "+00:00"))
            span_s = (t1 - t0).total_seconds()
        except Exception:
            span_s = None
    return {
        "assistant_turns": assistant_turns,
        "thinking_tokens": thinking_tokens,
        "tool_calls": tool_calls,
        "span_s": span_s,
    }


def resolved_wait_seconds(path: str, attempt: int, now: Optional[float] = None) -> int:
    """The wait the driver should actually sleep before retrying: the
    CLI's own exact reset time if this round's log captured one, else the
    escalating-guess schedule. Single entry point so the bash caller makes
    ONE python3 call per retry decision instead of branching between two.
    """
    exact = exact_reset_wait_seconds(path, now=now)
    if exact is not None:
        return exact
    return rate_limit_backoff_seconds(attempt)


def round_succeeded(path: str) -> bool:
    """True iff the round log's final result is a clean success — the
    exact predicate `run_driver.sh` used to gate its "success" log line
    when it read the file itself with `json.load`; centralized here so it
    also works on stream-json logs via `load_round_result`.
    """
    d = load_round_result(path)
    if d is None:
        return False
    return d.get("subtype") == "success" and not d.get("is_error", False)


def round_status_text(path: str) -> str:
    """Human-readable one-line status, matching `run_driver.sh`'s original
    `SUB` variable exactly: `"error:<api_error_status>"` when `is_error`,
    else the `subtype`, else `"?"` if the result is unreadable.

    `api_error_status` is absent for a max-turns death (it's not an API
    error at all), which used to fall back to the generic literal "err" —
    indistinguishable in `driver.log` from any other unclassified failure.
    Reports "max_turns" instead when `subtype == "error_max_turns"`, so a
    human reading the log (or `all_max_turns` reasoning about a cluster of
    these lines) doesn't have to open the round's raw JSON to tell a
    workload-driven max-turns death apart from a real API error.
    """
    d = load_round_result(path)
    if d is None:
        return "?"
    if d.get("is_error"):
        if d.get("subtype") == "error_max_turns":
            return "error:max_turns"
        return "error:" + str(d.get("api_error_status", "err"))
    return str(d.get("subtype", "?"))


def is_5xx(path: str) -> bool:
    """True iff the round log looks like a transient 5xx/529 server
    overload — `api_error_status` starting with "5", or "529" appearing in
    the embedded `result` text (the CLI sometimes reports 529s as text
    inside a 200-wrapped error rather than as `api_error_status`).
    """
    d = load_round_result(path)
    if d is None:
        return False
    status = str(d.get("api_error_status", ""))
    result_text = str(d.get("result", ""))
    return status.startswith("5") or "529" in result_text


def main(argv: List[str]) -> int:
    if argv[:1] == ["success"]:
        if len(argv) != 2:
            print("usage: driver_health.py success ROUND_LOG", file=sys.stderr)
            return 2
        print("yes" if round_succeeded(argv[1]) else "no")
        return 0
    if argv[:1] == ["status"]:
        if len(argv) != 2:
            print("usage: driver_health.py status ROUND_LOG", file=sys.stderr)
            return 2
        print(round_status_text(argv[1]))
        return 0
    if argv[:1] == ["is5xx"]:
        if len(argv) != 2:
            print("usage: driver_health.py is5xx ROUND_LOG", file=sys.stderr)
            return 2
        print("yes" if is_5xx(argv[1]) else "no")
        return 0
    if argv[:1] == ["backoff"]:
        if len(argv) != 2:
            print("usage: driver_health.py backoff ATTEMPT", file=sys.stderr)
            return 2
        print(rate_limit_backoff_seconds(int(argv[1])))
        return 0
    if argv[:1] == ["is429"]:
        if len(argv) != 2:
            print("usage: driver_health.py is429 ROUND_LOG", file=sys.stderr)
            return 2
        print("yes" if is_rate_limit(argv[1]) else "no")
        return 0
    if argv[:1] == ["is_max_turns"]:
        if len(argv) != 2:
            print("usage: driver_health.py is_max_turns ROUND_LOG", file=sys.stderr)
            return 2
        print("yes" if is_max_turns(argv[1]) else "no")
        return 0
    if argv[:1] == ["all_max_turns"]:
        print("yes" if all_max_turns(argv[1:]) else "no")
        return 0
    if argv[:1] == ["ratelimit_signal"]:
        if len(argv) != 2:
            print("usage: driver_health.py ratelimit_signal ROUND_LOG", file=sys.stderr)
            return 2
        print("yes" if has_real_ratelimit_signal(argv[1]) else "no")
        return 0
    if argv[:1] == ["wait"]:
        if len(argv) != 3:
            print("usage: driver_health.py wait ROUND_LOG ATTEMPT", file=sys.stderr)
            return 2
        print(resolved_wait_seconds(argv[1], int(argv[2])))
        return 0
    if argv[:1] == ["summary"]:
        if len(argv) != 2:
            print("usage: driver_health.py summary ROUND_LOG", file=sys.stderr)
            return 2
        s = summarize_turns(argv[1])
        print(json.dumps(s) if s is not None else "n/a")
        return 0
    print(count_consecutive_failures(argv))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
