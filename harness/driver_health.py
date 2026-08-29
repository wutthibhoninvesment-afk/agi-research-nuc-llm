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

    `interrupted`: round 163 found LIVE (round-162's own log: 220
    assistant turns / 136 tool calls / 38 minutes of real work, a
    thoroughly substantial round) that the round-145 fallback above has a
    gap of its own — it fixes the case where a `result` event exists but
    lacks per-turn thinking data, but does nothing when the process is
    killed (SIGKILL/OOM/outer `timeout`) before it ever WRITES a `result`
    event at all, which is exactly what round 162's log shows (ends
    mid-tool-call, no `type:"result"` line anywhere in the file). In that
    case `result_thinking_tokens` stays `None` and `thinking_tokens`
    reads 0 — visually IDENTICAL to the pre-145 always-0 bug this same
    field exists to detect, with no way to tell them apart from the
    number alone. `interrupted=True` names the cause directly so a future
    round scoring a `thinking_tokens: 0` reading (as round-145's own P3
    prediction asks a future round to do) checks this flag before
    concluding the fix regressed.
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
    saw_result = False
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
            saw_result = True
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
        "interrupted": not saw_result,
    }


_TRACK_BY_MOD6 = {
    1: "harness(A)",
    2: "language(C)",
    3: "skills(B)",
    4: "NUC-integration(E)",
    5: "SWE-loop(D)",
    0: "language(C)",
}


def track_name_for_round(round_num: int) -> str:
    """Pure port of `run_driver.sh`'s `track_name()` bash function — the
    6-way round-robin curriculum assignment (round % 6: 1=harness(A),
    2=language(C), 3=skills(B), 4=NUC-integration(E), 5=SWE-loop(D),
    0=language(C), so language(C) gets 2 of every 6 slots). Kept only so
    `tally_by_track` below can bucket historical `logs/round-NNN.json` files
    by track without re-invoking the shell script; if `run_driver.sh`'s
    mapping ever changes this needs the matching edit (there is no single
    source of truth to import from — bash and Python can't share one file
    here — so `test_driver_health.py` pins known rounds from `driver.log`
    directly as a drift check).
    """
    return _TRACK_BY_MOD6[round_num % 6]


def tally_by_track(paths: List[str]) -> dict:
    """Bucket a set of `logs/round-NNN.json` paths by track and count
    total/max_turns/interrupted per track.

    Built for the max-turns re-tally this project's backlog has asked for
    every ~10 rounds since the 120->135 raise (rounds 205, 211, 217) — round
    217 used this over `logs/round-{152..216}.json` and found every
    max-turns death on record (8/8: rounds 155/168/179/182/203/204/206/216)
    landed in language(C) or SWE-loop(D) — ZERO in the three lighter tracks
    (harness(A)/skills(B)/NUC-integration(E), 32 round-starts combined) even
    once. That's a real, reusable finding, not a one-off — the next re-tally
    would otherwise redo the same manual grep+arithmetic from scratch. Round
    number is parsed from each path's filename (`round-NNN.json` or
    `round-0NN.json`), not read from log content, since track isn't stored
    in the JSON itself; paths that don't match are silently skipped (e.g. a
    non-round file passed by mistake) rather than raising, since this is a
    reporting tool, not a correctness-critical path.
    """
    import re

    out: dict = {}
    for p in paths:
        m = re.search(r"round-0*(\d+)\.json$", p)
        if not m:
            continue
        round_num = int(m.group(1))
        track = track_name_for_round(round_num)
        bucket = out.setdefault(track, {"total": 0, "max_turns": 0, "interrupted": 0})
        bucket["total"] += 1
        if is_max_turns(p):
            bucket["max_turns"] += 1
        turns = summarize_turns(p)
        if turns and turns.get("interrupted"):
            bucket["interrupted"] += 1
    return out


_HEAVY_TRACKS = frozenset({"language(C)", "SWE-loop(D)"})


def heavy_light_fail_rates(paths: List[str]) -> dict:
    """Aggregate `tally_by_track`'s per-track buckets into the two-way
    HEAVY (language(C)+SWE-loop(D)) vs. LIGHT (harness(A)+skills(B)+
    NUC-integration(E)) split this project's backlog has re-derived by
    hand at least three separate times (rounds 217, 259, 265 — each one a
    fresh ad hoc script summing `interrupted+max_turns` over the two
    track groups and computing a ratio) without ever promoting the
    aggregation itself into this module. `fail` per track is
    `interrupted + max_turns` (a round log is never both at once: a
    max-turns death produces a real `type:"result"` event with
    `subtype:"error_max_turns"`, while `interrupted` specifically means
    NO such event exists — see `summarize_turns`/`is_max_turns`), matching
    the exact definition round 265's own Finding 3 table used. Returns
    `{"heavy": {...}, "light": {...}, "ratio": float|None}` where each
    inner dict has `total`/`fail`/`rate` and `ratio` is
    `heavy["rate"] / light["rate"]` (`None` if light's rate is 0, since a
    finite ratio would misleadingly imply light's true rate is nonzero).
    """
    tally = tally_by_track(paths)
    heavy = {"total": 0, "fail": 0}
    light = {"total": 0, "fail": 0}
    for track, d in tally.items():
        bucket = heavy if track in _HEAVY_TRACKS else light
        bucket["total"] += d["total"]
        bucket["fail"] += d["interrupted"] + d["max_turns"]
    for bucket in (heavy, light):
        bucket["rate"] = (bucket["fail"] / bucket["total"]) if bucket["total"] else 0.0
    ratio = (heavy["rate"] / light["rate"]) if light["rate"] else None
    return {"heavy": heavy, "light": light, "ratio": ratio}


def full_event_span_s(path: str) -> Optional[float]:
    """First-to-last timestamp span across ALL events in a stream-json log,
    not just `type: "assistant"` ones (contrast `summarize_turns`'s
    `span_s`, which only walks assistant-event timestamps).

    Round 211 found LIVE, on round 210's own log (`status=?`/`interrupted:
    true`, no `result` event), that these two spans can diverge — and
    root-caused WHY, rather than just observing the gap. driver.log's own
    "turn summary" line for round 210 recorded `assistant_turns: 200`,
    `span_s: 3174.154`; re-reading the SAME file after the round had fully
    finished shows 201 assistant events and `summarize_turns`'s own
    (assistant-only) span at 3296.746 — a full extra assistant turn simply
    wasn't on disk yet at the moment `run_driver.sh` ran its summary call.
    This is a real write/read race, not an event-type artifact: the file's
    mtime (18:17:01.597972957Z) lands right on top of that 201st event's
    own embedded timestamp (18:17:01.596Z), meaning the process's last,
    still-in-flight assistant-message chunk was flushed to disk at
    essentially the same instant `run_driver.sh` read the file immediately
    after the outer `timeout`'s `RC=$?` — a coin-flip on which happens
    first. Using ALL event types (not just assistant) makes this
    classification more ROBUST to that exact race in practice: a
    background-tool-call "killed" notification (`type: "system"`,
    `subtype: "task_updated"`) landed at 18:17:00.000ish — cheap CLI
    bookkeeping, not model-generated content, so far less likely to be the
    one write still in flight at kill time — putting `full_event_span_s`
    within seconds of the true kill point even if computed at the exact
    same racy moment `summarize_turns`'s 3174.154 was. This function exists
    so a caller trying to tell "genuinely crashed early" apart from "died
    right at our own wall-clock ceiling" isn't misled by a race that can
    make the LAST assistant-only event look artificially early.
    """
    events = load_round_events(path)
    if not events:
        return None
    timestamps = [e.get("timestamp") for e in events if e.get("timestamp")]
    if len(timestamps) < 2:
        return None
    try:
        t0 = datetime.fromisoformat(timestamps[0].replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(timestamps[-1].replace("Z", "+00:00"))
    except Exception:
        return None
    return (t1 - t0).total_seconds()


def likely_timeout_kill(path: str, timeout_s: float, margin_s: float = 180.0) -> Optional[bool]:
    """True/False iff a round log with NO `result` event (see run_driver.sh's
    "file populated but no result entry — assuming Claude crash" branch)
    looks like it was actually killed by the driver's own outer wall-clock
    `timeout $DRIVER_ROUND_TIMEOUT_S` rather than a genuine process crash;
    `None` when there isn't enough timestamped data to tell either way
    (fewer than 2 timestamped events — too little to trust a claim in
    either direction, so callers should report "unknown" rather than
    silently defaulting to "genuine crash").

    That branch's log message has said "assuming Claude crash" since round
    150, but its own comment (run_driver.sh, round 181) already documents
    that the branch covers BOTH causes — a real crash AND a timeout-killed
    round produce an identical on-disk shape (file has events, no `result`
    line) and were never actually distinguished. Round 211 confirmed round
    210 was the timeout-kill case (full_event_span_s ~3296.7s against a
    3300s ceiling — the round ran essentially the whole budget and was cut
    off, not a crash at some arbitrary earlier point).

    `margin_s` (default 180s) absorbs CLI startup latency before the first
    stream-json event is written (observed a few seconds to ~2 minutes) —
    a genuine early crash (e.g. a few hundred seconds in) reads False; a
    round whose last event lands within `margin_s` of the ceiling reads
    True. Not exact (a crash that happens to occur late in a long round
    would also read True), but far better than treating every no-result
    log identically.
    """
    span = full_event_span_s(path)
    if span is None:
        return None
    return span >= (timeout_s - margin_s)


def blocking_wait_gap_s(path: str) -> Optional[float]:
    """`full_event_span_s(path) - summarize_turns(path)["span_s"]` — how much
    of a round's wall clock landed AFTER the model's last assistant
    timestamp. For every nonzero-gap real instance found so far (round 289:
    12 of 17 checked), this is the time between issuing the last tool call
    and that tool's OWN result event arriving — the tool did return; see
    `is_blocking_wait_kill`'s docstring for why "still waiting on it" is not
    an accurate description of that shape.

    Promotes a diagnosis manually re-derived by hand three separate times
    (round 265 on round 263: 338.59s; round 223 on round 222: 303.512s;
    round 283 on round 278: 207.193s — each requiring pulling both spans
    and subtracting by hand) into a reusable primitive, same rationale
    round 271 gave for promoting `heavy_light_fail_rates`. A near-zero gap
    (round 224: 0.0s exactly) means the round was still actively
    generating right up to the wall-clock kill — see `last_assistant_tool_use`
    and `is_blocking_wait_kill` for turning this into a same/different-
    mechanism verdict.

    Returns None if either underlying span is unavailable (see
    `full_event_span_s`/`summarize_turns`), rather than a possibly-
    misleading 0 or negative number.
    """
    full_span = full_event_span_s(path)
    turns = summarize_turns(path)
    if full_span is None or not turns or turns.get("span_s") is None:
        return None
    return full_span - turns["span_s"]


def last_assistant_tool_use(path: str) -> Optional[str]:
    """Name of the `tool_use` block in the LAST `type: "assistant"` event of
    a round log — e.g. "TaskOutput" or "Bash" — or None if that event
    carries no tool_use (plain text/thinking) or the log has no assistant
    events at all.

    On its own this does NOT distinguish the two known kill shapes — round
    224's final event was ALSO a tool_use (`Bash`, catting a background
    task's output file), same as rounds 222/263/278 — the real
    discriminator is `blocking_wait_gap_s`/`is_blocking_wait_kill`: round
    224's tool_use event was the very LAST event in the entire log (killed
    the instant it was emitted, before a single trailing `tool_progress`
    tick), while 222/263/278 each have a run of trailing non-assistant
    events (ticks, then eventually a `user` tool-result) after their last
    assistant event, producing a real gap. Use this function to report
    WHAT the round was calling when killed, not whether it was blocked.
    """
    events = load_round_events(path)
    if not events:
        return None
    for event in reversed(events):
        if event.get("type") != "assistant":
            continue
        content = event.get("message", {}).get("content", [])
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                return block.get("name")
        return None
    return None


def is_blocking_wait_kill(path: str, min_gap_s: float = 1.0) -> Optional[bool]:
    """True iff an `interrupted` round's last-event shape is "tool result
    landed, no further turn" rather than "still working when the wall
    clock fell" (round 224/210's shape: gap == 0.0, reads False here).

    Round 289 corrected the mechanism this was originally documented as
    (round 223 on 222, round 265 on 263, round 283 on 278): re-reading
    those same three logs' raw events shows each one's LAST event overall
    is a `type: "user"` tool-result that DID arrive — not a dangling
    `tool_use` the driver's `timeout` cut off mid-flight. The round wasn't
    stuck waiting forever; its last tool call (of whatever duration)
    finished, and there simply wasn't wall-clock budget left for one more
    assistant turn. `blocking_wait_gap_s` in that shape is dominated by how
    long that specific last tool happened to take — informative when
    anomalously large (round 185, found this round: 2912.156s, a Bash
    subprocess with no `timeout` param evaluating a self-recursive guest
    program with no base case), unremarkable when it's an ordinary command
    duration (round 192: 9.214s for a ordinary Bash call).

    Round 289 also extended the analysis back to round 152 (previously only
    5 logs — 210/222/224/263/278 — had ever been checked) and found the
    full, real gap distribution is a SMOOTH continuum from 9.214s (round
    192) to 2912.156s (round 185), not two clusters separated by a wide
    margin as originally believed — the prior 100s default sat in the
    middle of that continuum, meaning rounds 162 (87.79s), 173 (88.91s),
    174 (27.77s), and 192 (9.21s) — 4 of the then-17 known real instances —
    were silently misclassified `False` under it despite sharing the exact
    same "result landed, no further turn" event shape as the confirmed
    instances. There is no evidence of a genuine intermediate mechanism at
    those magnitudes: every nonzero-gap instance found (12/17 real
    `interrupted` rounds checked) has the identical structural shape, only
    varying in how long the last tool took. `min_gap_s` now defaults to
    1.0s — still comfortably above float/CLI jitter around exact 0.0, and
    below every confirmed nonzero gap on record (smallest: 9.214s) — so the
    boolean now tracks the real structural split (`gap > 0` vs `gap == 0`)
    instead of an arbitrary magnitude cutoff partway through one continuum.

    Round 301 checked the one real `interrupted` round to land since 289's
    analysis (round 295, gap 44.642s — a `TaskOutput(block=true,
    timeout=500000)` call, the exact mechanism round 265 named for round
    263) and confirmed it slots into the SAME continuum (between round
    174's 27.771s and round 162's 87.791s) with the identical event shape
    — 18 real `interrupted` rounds checked total now (13 nonzero-gap, 5
    zero-gap), `min_gap_s=1.0` still correctly tracks the structural split
    with no new intermediate mechanism found.

    Returns None (not False) when the round was not `interrupted` at all,
    or when `blocking_wait_gap_s` itself can't be computed — a clean
    round or one with too little data isn't evidence either way.
    """
    turns = summarize_turns(path)
    if not turns or not turns.get("interrupted"):
        return None
    gap = blocking_wait_gap_s(path)
    if gap is None:
        return None
    return gap >= min_gap_s


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
    if argv[:1] == ["tally"]:
        print(json.dumps(tally_by_track(argv[1:]), sort_keys=True))
        return 0
    if argv[:1] == ["heavy_light"]:
        print(json.dumps(heavy_light_fail_rates(argv[1:]), sort_keys=True))
        return 0
    if argv[:1] == ["likely_timeout_kill"]:
        if len(argv) not in (3, 4):
            print("usage: driver_health.py likely_timeout_kill ROUND_LOG TIMEOUT_S [MARGIN_S]", file=sys.stderr)
            return 2
        margin = float(argv[3]) if len(argv) == 4 else 180.0
        verdict = likely_timeout_kill(argv[1], float(argv[2]), margin_s=margin)
        print("unknown" if verdict is None else ("yes" if verdict else "no"))
        return 0
    if argv[:1] == ["blocking_wait_gap"]:
        if len(argv) != 2:
            print("usage: driver_health.py blocking_wait_gap ROUND_LOG", file=sys.stderr)
            return 2
        gap = blocking_wait_gap_s(argv[1])
        print("n/a" if gap is None else gap)
        return 0
    if argv[:1] == ["is_blocking_wait_kill"]:
        if len(argv) not in (2, 3):
            print("usage: driver_health.py is_blocking_wait_kill ROUND_LOG [MIN_GAP_S]", file=sys.stderr)
            return 2
        min_gap = float(argv[2]) if len(argv) == 3 else 100.0
        verdict = is_blocking_wait_kill(argv[1], min_gap_s=min_gap)
        print("unknown" if verdict is None else ("yes" if verdict else "no"))
        return 0
    print(count_consecutive_failures(argv))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
