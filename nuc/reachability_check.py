#!/usr/bin/env python3
"""reachability_check.py — durable, structured up/down log for pgain-nuc.

Rounds 184-304 tracked box reachability entirely in knowledge-file prose,
using `tailscale status`'s plain-text renderer as the only source ("offline,
last seen 1h ago"). That string is coarse (rounds to whole minutes/hours)
and, worse, is a SNAPSHOT recomputed fresh each round -- nothing durable
recorded the actual `LastSeen` timestamp `tailscale status --json` carries,
so reconstructing "is round 298's outage the same one as round 304's" (round
310 confirms below: yes, provably) has always required eyeballing prose
deltas across separate knowledge files rather than comparing two real
timestamps.

This module is the reusable version: one pure parser for
`tailscale status --json` output, one check function combining it with a
real SSH probe, and a durable JSONL log (`state/nuc-reachability-log.jsonl`)
that every future E round can append one line to and analyze directly
instead of re-deriving from prose.

Read-only, no colibri/toolproxy/port-8001 involvement: this only shells out
to `tailscale status --json` (local, no network needed for the tailscale
half) and one `ssh ... echo` probe against the standing tailnet target.

Usage:
    python3 nuc/reachability_check.py check --round 310
        (runs a real check, appends one record to the log, prints it)
    python3 nuc/reachability_check.py summarize
        (reads the whole log, prints outage-streak analysis)
    python3 nuc/reachability_check.py status
        (current streak's verdict + elapsed time as of now)
    python3 nuc/reachability_check.py bounds
        (per-streak [confirmed, max-possible] span brackets)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_HOSTNAME = "pgain-nuc"
DEFAULT_SSH_TARGET = "jab@100.78.44.111"
DEFAULT_SSH_KEY = str(Path.home() / ".ssh" / "id_ed25519")
DEFAULT_CONNECT_TIMEOUT_S = 10
DEFAULT_LOG_PATH = "state/nuc-reachability-log.jsonl"


class ReachabilityCheckError(RuntimeError):
    pass


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_tailscale_peer(status_json_text: str, hostname: str = DEFAULT_HOSTNAME) -> dict | None:
    """Pick one peer by HostName out of `tailscale status --json` output.

    Returns None if the peer isn't in the map at all (distinct from being
    present-but-offline, which returns a dict with online=False). Pure
    string-in/dict-out so it's testable with no real tailscale binary.
    """
    data = json.loads(status_json_text)
    for peer in data.get("Peer", {}).values():
        if peer.get("HostName") == hostname:
            return {
                "online": bool(peer.get("Online", False)),
                "last_seen": peer.get("LastSeen"),
                "last_write": peer.get("LastWrite"),
                "last_handshake": peer.get("LastHandshake"),
            }
    return None


def ssh_probe(ssh_target: str = DEFAULT_SSH_TARGET, ssh_key: str = DEFAULT_SSH_KEY,
              connect_timeout: int = DEFAULT_CONNECT_TIMEOUT_S,
              runner=subprocess.run) -> dict:
    """One `ssh ... echo UP` attempt. Never raises on unreachability -- a
    timed-out/refused connection is a normal, expected outcome here, not an
    exceptional one (this whole module exists to observe that outcome)."""
    argv = ["ssh", "-i", ssh_key, "-o", f"ConnectTimeout={connect_timeout}",
            "-o", "BatchMode=yes", ssh_target, "echo UP"]
    try:
        res = runner(argv, capture_output=True, text=True, timeout=connect_timeout + 5)
    except subprocess.TimeoutExpired:
        return {"reachable": False, "returncode": None, "stderr": "local timeout"}
    reachable = res.returncode == 0 and res.stdout.strip() == "UP"
    return {"reachable": reachable, "returncode": res.returncode, "stderr": res.stderr.strip()}


def boot_probe(ssh_target: str = DEFAULT_SSH_TARGET, ssh_key: str = DEFAULT_SSH_KEY,
               connect_timeout: int = DEFAULT_CONNECT_TIMEOUT_S,
               runner=subprocess.run) -> float | None:
    """Seconds since boot, read from the box's own `/proc/uptime`.

    Deliberately a SECOND ssh call rather than an extra command appended to
    `ssh_probe`'s: that probe's "stdout must be exactly UP" strictness is
    the whole basis of the `up` verdict (see
    `test_ssh_probe_unexpected_stdout_not_reachable`), and relaxing it to
    make room for a second output line would weaken the one check this
    module is actually built around. `check()` only calls this after the
    probe already returned reachable, so it costs one extra round-trip on
    up checks and nothing at all on down checks (where it would just sit
    through another connect timeout for no information).

    `/proc/uptime` rather than `uptime -s`: `uptime -s` prints the box's
    LOCAL time with no offset, so turning it into a UTC instant needs the
    box's timezone, which nothing in this log records (rounds 202-232 read
    it as UTC and the arithmetic happened to check out, but that was an
    assumption, never a verified fact). An elapsed-seconds float needs no
    timezone at all.

    Returns None -- never raises -- for every failure mode (unreachable,
    non-zero exit, unparseable/empty output, a negative value): a missing
    boot time simply leaves `streak_bounds` falling back to "next_check".
    """
    argv = ["ssh", "-i", ssh_key, "-o", f"ConnectTimeout={connect_timeout}",
            "-o", "BatchMode=yes", ssh_target, "cat /proc/uptime"]
    try:
        res = runner(argv, capture_output=True, text=True, timeout=connect_timeout + 5)
    except subprocess.TimeoutExpired:
        return None
    if res.returncode != 0:
        return None
    fields = (res.stdout or "").split()
    if not fields:
        return None
    try:
        uptime_s = float(fields[0])
    except ValueError:
        return None
    return uptime_s if uptime_s >= 0 else None


def boot_utc_from_uptime(now_iso: str, uptime_s: float) -> str:
    """`now_iso` minus `uptime_s`, as a whole-second UTC timestamp.

    Bias is deliberately toward LATER (a later boot time is the
    conservative direction: `streak_bounds` uses boot time as the UPPER
    bound on when a preceding outage ended, so overshooting late can only
    widen the bracket, never make it claim more than the evidence does).
    Two effects, both in that direction: `check()` reads `now_fn()` AFTER
    the probe returns, so `now_iso` is later than the instant `/proc/uptime`
    was actually read by the ssh round-trip; and truncating to whole
    seconds moves it back by under 1s, far less than that round-trip.
    """
    return (_parse_ts(now_iso) - timedelta(seconds=uptime_s)).strftime(TS_FORMAT)


def check(round_: int | None = None, hostname: str = DEFAULT_HOSTNAME,
          ssh_target: str = DEFAULT_SSH_TARGET, ssh_key: str = DEFAULT_SSH_KEY,
          connect_timeout: int = DEFAULT_CONNECT_TIMEOUT_S, notes: str = "",
          now_fn=now_utc_iso, tailscale_runner=subprocess.run,
          ssh_runner=subprocess.run) -> dict:
    """Combine a tailscale-peer read and a real SSH probe into one record.

    Verdict logic: "up" only if the SSH probe itself succeeded (the ground
    truth this whole track has always used); "down" if SSH failed AND
    tailscale agrees the peer is offline (or tailscale itself couldn't be
    read -- SSH failing is enough on its own to call it down, tailscale is
    corroborating evidence, not a requirement); "ambiguous" is reserved for
    the one case worth flagging loudly -- SSH failed but tailscale claims
    the peer IS online (would mean routing-only breakage, not box-down; not
    observed by this track through round 310, but worth being able to
    represent rather than silently coercing to "down").

    On an `up` verdict only, also records `boot_utc` (round 334) -- read
    from the box's own `/proc/uptime` via `boot_probe`. That single field
    is what lets `streak_bounds` close the END of the preceding outage
    tightly: without it the best upper bound available is "whenever a round
    next happened to look", which on this track's 1-2 hour check cadence
    has run to 2h23m of pure ignorance (the round-184/196 outage). `None`
    on every down check, and on an up check whose boot read failed.
    """
    checked_at = now_fn()
    ts_res = tailscale_runner(["tailscale", "status", "--json"], capture_output=True,
                               text=True, timeout=15)
    peer = None
    ts_error = None
    if ts_res.returncode == 0:
        try:
            peer = parse_tailscale_peer(ts_res.stdout, hostname)
        except (json.JSONDecodeError, AttributeError) as e:
            ts_error = str(e)
    else:
        ts_error = ts_res.stderr.strip()

    ssh_result = ssh_probe(ssh_target, ssh_key, connect_timeout, runner=ssh_runner)

    boot_utc = None
    if ssh_result["reachable"]:
        uptime_s = boot_probe(ssh_target, ssh_key, connect_timeout, runner=ssh_runner)
        if uptime_s is not None:
            boot_utc = boot_utc_from_uptime(now_fn(), uptime_s)

    if ssh_result["reachable"]:
        verdict = "up"
    elif peer is not None and peer["online"]:
        verdict = "ambiguous"
    else:
        verdict = "down"

    return {
        "checked_at_utc": checked_at,
        "round": round_,
        "track": "NUC-integration(E)",
        "verdict": verdict,
        "ssh_reachable": ssh_result["reachable"],
        "ssh_returncode": ssh_result["returncode"],
        "ssh_stderr": ssh_result["stderr"],
        "tailscale_online": peer["online"] if peer else None,
        "tailscale_last_seen_utc": peer["last_seen"] if peer else None,
        "tailscale_last_write_utc": peer["last_write"] if peer else None,
        "tailscale_error": ts_error,
        "boot_utc": boot_utc,
        "source": "live",
        "precision": "precise",
        "notes": notes,
    }


def append_record(record: dict, log_path: str = DEFAULT_LOG_PATH) -> None:
    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record) + "\n")


def load_log(log_path: str = DEFAULT_LOG_PATH) -> list:
    p = Path(log_path)
    if not p.exists():
        return []
    records = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _sort_key(record: dict):
    # Records without a real checked_at_utc (shouldn't happen for live
    # checks) sort last rather than crashing the summary.
    return record.get("checked_at_utc") or "9999"


def _build_streaks(records: list) -> list:
    """Time-order `records` and merge each maximal run of same-verdict
    checks into one streak dict, keeping the underlying records attached.

    Split out of `summarize_log` in round 334 so `streak_bounds` can reach
    the per-streak records (it needs each down check's own
    `tailscale_last_seen_utc`, which `summarize_log`'s public output
    deliberately drops). `summarize_log`'s own output shape is unchanged --
    it still projects these down to the same 7 public fields it always did.
    """
    ordered = sorted(records, key=_sort_key)
    streaks = []
    for rec in ordered:
        v = rec["verdict"]
        if streaks and streaks[-1]["verdict"] == v:
            streaks[-1]["records"].append(rec)
            streaks[-1]["end"] = rec["checked_at_utc"]
            streaks[-1]["end_round"] = rec.get("round")
        else:
            streaks.append({
                "verdict": v,
                "start": rec["checked_at_utc"],
                "end": rec["checked_at_utc"],
                "start_round": rec.get("round"),
                "end_round": rec.get("round"),
                "records": [rec],
            })
    return streaks


def summarize_log(records: list) -> dict:
    """Group time-ordered records into up/down streaks and report each
    streak's span. Adjacent records with the SAME verdict class (treating
    "ambiguous" as its own class) merge into one streak; "up" and
    "down"/"ambiguous" alternating boundaries are where a real transition
    is inferred to have happened, bounded by the two straddling records'
    own timestamps (not claimed to be exact for coarse/backfilled entries).
    """
    ordered = sorted(records, key=_sort_key)
    streaks = _build_streaks(ordered)
    out_streaks = []
    for s in streaks:
        out_streaks.append({
            "verdict": s["verdict"],
            "start": s["start"],
            "end": s["end"],
            "start_round": s["start_round"],
            "end_round": s["end_round"],
            "n_checks": len(s["records"]),
            "rounds": [r.get("round") for r in s["records"]],
        })
    return {
        "n_records": len(ordered),
        "n_streaks": len(out_streaks),
        "n_down_streaks": sum(1 for s in out_streaks if s["verdict"] == "down"),
        "streaks": out_streaks,
    }


# Written form (what this module emits); the parser below strips the "Z"
# before matching, so it parses against TS_FORMAT_NO_Z.
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
TS_FORMAT_NO_Z = "%Y-%m-%dT%H:%M:%S"


def _parse_ts(ts: str) -> datetime:
    """Parse an ISO-8601 UTC ("...Z") timestamp, tolerating a fractional-
    second part of ANY digit count.

    Until round 334 this was a bare `strptime(ts, "%Y-%m-%dT%H:%M:%SZ")`,
    which is exactly right for the `checked_at_utc` values this module
    writes itself -- and raises `ValueError` on the two fields tailscale
    supplies: `LastSeen` carries 1 fractional digit
    ("2026-08-29T02:10:00.1Z") and `LastWrite` carries 9
    ("2026-08-29T12:47:50.906797174Z"). Nothing parsed those fields before
    round 334's `streak_bounds` needed `LastSeen` as a real datum rather
    than a string copied into prose, so the limitation was invisible.

    `datetime.fromisoformat` handles both on Python 3.11+ but not on 3.9/
    3.10 (no "Z" suffix, only 3-or-6-digit fractions), and the nuc suite has
    run under both, so this stays a hand-rolled parse: strip the "Z",
    normalise any fraction to exactly 6 digits by TRUNCATION (never
    rounding, matching `format_duration_s`'s own choice -- a rounded
    ".9999999" must not roll a whole second forward), then strptime.
    """
    text = ts.strip()
    if text.endswith("Z"):
        text = text[:-1]
    if "." in text:
        whole, frac = text.split(".", 1)
        frac = frac[:6].ljust(6, "0")
        return datetime.strptime(f"{whole}.{frac}",
                                 TS_FORMAT_NO_Z + ".%f").replace(tzinfo=timezone.utc)
    return datetime.strptime(text, TS_FORMAT_NO_Z).replace(tzinfo=timezone.utc)


def _streak_span_seconds(streak: dict) -> float:
    return (_parse_ts(streak["end"]) - _parse_ts(streak["start"])).total_seconds()


def format_duration_s(seconds: float) -> str:
    """Render a non-negative second count as `"{h}h{mm:02d}m{ss:02d}s"`,
    matching the by-hand format every prior round has used in prose
    (round 322: 28821.0 -> "8h00m21s"; round 322: 18880.0 -> "5h14m40s";
    round 322: 9941 (a margin, not a streak span) -> "2h45m41s"). Hours are
    unpadded (single check can run past 99h with no format break), minutes
    and seconds are always 2 digits. Sub-second remainders are truncated,
    not rounded, so this can never report 60s/60m and roll over on its own
    -- matching `int()` truncation being the obvious, boring choice here
    and avoiding a 3599.9s -> "1h00m00s" (should be "59m59s") off-by-one.
    Every round from 322 on did this arithmetic by hand from raw
    `elapsed_s`; wiring it into the tool's own output removes a recurring
    manual-conversion step that was never actually verified against a test.
    """
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s"


def longest_completed_streak(records: list, verdict: str) -> dict | None:
    """Among `summarize_log`'s streaks matching `verdict`, the longest one
    that is NOT the very last streak in the log -- the last streak might
    still be ongoing (its "end" is just "whenever the last check happened
    to run", exactly the gap `current_streak_duration` exists to cover for
    the CURRENT streak). Excluding it here means this only ever compares
    against streaks the log has already seen END (a real verdict flip
    logged afterwards), never against itself mid-flight.

    Returns None if there is no completed streak of that verdict yet (e.g.
    `verdict` has only ever appeared as the log's own still-open final
    streak, or never at all).
    """
    summary = summarize_log(records)
    completed = summary["streaks"][:-1] if summary["streaks"] else []
    matching = [s for s in completed if s["verdict"] == verdict]
    if not matching:
        return None
    return max(matching, key=_streak_span_seconds)


# Verdict classes for which a record's own `tailscale_last_seen_utc` is
# evidence about when the streak BEGAN. For a down/ambiguous streak,
# LastSeen is the last instant the box was demonstrably alive, so the
# down transition must have happened AFTER it -- a strictly tighter lower
# bound on the outage start than "the previous up check". For an UP
# streak the same field means the opposite thing (evidence from INSIDE
# the streak that it was already up), so it is deliberately not used
# there; an up streak's start is bounded only by the preceding check.
_LAST_SEEN_BOUNDS_START = ("down", "ambiguous")


def streak_bounds(records: list) -> list:
    """Per-streak [confirmed, max-possible] span brackets.

    Every span this module reported before round 334 -- `summarize_log`'s
    streak `start`/`end`, `_streak_span_seconds`, `current_streak_duration`'s
    `elapsed_s` -- is measured check-to-check, i.e. it is the span over
    which the box was OBSERVED to hold a verdict. That is a strict LOWER
    bound on the real streak, never the real streak itself: the box went
    down at some unobserved instant between the last up check and the first
    down check, and comes back at some unobserved instant between the last
    down check and the first up check. With this track's ~6-round (1-2 hour)
    check cadence, that unobserved slack is HOURS, and it is invisible in
    every number the tool prints.

    This function makes both sides explicit:

      confirmed_span_s   last_check - first_check   (strict lower bound;
                                                     the pre-334 number)
      max_possible_span_s
                         latest_possible_end - earliest_possible_start
                                                    (strict upper bound)

    with the two ignorance windows broken out separately
    (`start_uncertainty_s`, `end_uncertainty_s`) so a reader can see WHICH
    side the imprecision comes from, and `*_source` fields naming the
    evidence each bound rests on rather than leaving it implicit:

      earliest_possible_start_source
        "boot_utc"            -- this streak's own first record carries a
                                 boot time; nothing before the box booted
                                 can belong to the streak
        "tailscale_last_seen" -- a LastSeen recorded during the streak
                                 itself (see `_LAST_SEEN_BOUNDS_START`)
        "previous_check"      -- the preceding streak's last check
        None                  -- no evidence at all; unbounded before
      latest_possible_end_source
        "boot_utc"            -- the next streak's first record carries a
                                 real boot time (tighter than its check:
                                 the box was demonstrably up at boot, which
                                 is generally well before we next looked)
        "next_check"          -- the next streak's first check
        None                  -- the streak is the log's last; still ongoing

    A `None` on either side leaves `max_possible_span_s` None: an unbounded
    side means there is genuinely no upper bound to report, and inventing
    one (e.g. "now") would silently turn an open interval into a claim.
    """
    streaks = _build_streaks(records)
    out = []
    for i, s in enumerate(streaks):
        first_str, last_str = s["start"], s["end"]
        first_dt, last_dt = _parse_ts(first_str), _parse_ts(last_str)
        confirmed_s = (last_dt - first_dt).total_seconds()

        start_str = start_src = start_dt = None
        if i > 0:
            start_str = streaks[i - 1]["end"]
            start_dt = _parse_ts(start_str)
            start_src = "previous_check"
        if s["verdict"] in _LAST_SEEN_BOUNDS_START:
            for rec in s["records"]:
                last_seen = rec.get("tailscale_last_seen_utc")
                if not last_seen:
                    continue
                seen_dt = _parse_ts(last_seen)
                # A LastSeen AFTER our own first down check would mean the
                # peer was seen alive after we had already called it down --
                # a flicker the log cannot resolve into streaks, and using
                # it would invert the bracket into a negative uncertainty.
                # Ignored rather than clamped.
                if seen_dt > first_dt:
                    continue
                if start_dt is None or seen_dt > start_dt:
                    start_str, start_src, start_dt = last_seen, "tailscale_last_seen", seen_dt
        # A boot time on this streak's OWN first record is the mirror image
        # of the LastSeen rule: it is evidence the box was alive at that
        # instant, so nothing that happened before it can belong to this
        # streak. For the up streak that follows an outage, that is a
        # strictly tighter start than "the last time we saw it down" -- and
        # for a log that OPENS on such a record it is the only start bound
        # available at all. A boot recorded later in the streak would be a
        # mid-streak reboot, which one bracket cannot represent, so only the
        # first record's is read (same rule the end side uses).
        first_boot = s["records"][0].get("boot_utc") if s["records"] else None
        if first_boot:
            boot_dt = _parse_ts(first_boot)
            if boot_dt <= first_dt and (start_dt is None or boot_dt > start_dt):
                start_str, start_src, start_dt = first_boot, "boot_utc", boot_dt

        end_str = end_src = end_dt = None
        if i + 1 < len(streaks):
            nxt = streaks[i + 1]
            end_str, end_src = nxt["start"], "next_check"
            end_dt = _parse_ts(end_str)
            boot = nxt["records"][0].get("boot_utc")
            if boot:
                boot_dt = _parse_ts(boot)
                # Only usable if the boot happened strictly inside our own
                # ignorance window. A boot_utc at or before our last check of
                # THIS streak would mean the box booted and we still observed
                # the old verdict afterwards -- more than one transition in
                # the gap, which no single bracket can represent.
                if last_dt < boot_dt < end_dt:
                    end_str, end_src, end_dt = boot, "boot_utc", boot_dt

        start_unc = None if start_dt is None else (first_dt - start_dt).total_seconds()
        end_unc = None if end_dt is None else (end_dt - last_dt).total_seconds()
        max_span = (None if (start_dt is None or end_dt is None)
                    else (end_dt - start_dt).total_seconds())
        out.append({
            "verdict": s["verdict"],
            "start_round": s["start_round"],
            "end_round": s["end_round"],
            "n_checks": len(s["records"]),
            "rounds": [r.get("round") for r in s["records"]],
            "first_check_utc": first_str,
            "last_check_utc": last_str,
            "confirmed_span_s": confirmed_s,
            "confirmed_span_human": format_duration_s(confirmed_s),
            "earliest_possible_start_utc": start_str,
            "earliest_possible_start_source": start_src,
            "latest_possible_end_utc": end_str,
            "latest_possible_end_source": end_src,
            "start_uncertainty_s": start_unc,
            "start_uncertainty_human": (None if start_unc is None
                                        else format_duration_s(start_unc)),
            "end_uncertainty_s": end_unc,
            "end_uncertainty_human": (None if end_unc is None
                                      else format_duration_s(end_unc)),
            "max_possible_span_s": max_span,
            "max_possible_span_human": (None if max_span is None
                                        else format_duration_s(max_span)),
            "ongoing": i == len(streaks) - 1,
        })
    return out


def longest_completed_streak_bounds(records: list, verdict: str) -> dict | None:
    """`longest_completed_streak`'s pick, as a `streak_bounds` entry.

    Selects by the SAME key (`confirmed_span_s` == `_streak_span_seconds`)
    over the SAME candidate set (all streaks but the log's own last), so it
    always returns the bracket of exactly the streak `longest_completed_
    streak` names -- `test_longest_completed_streak_bounds_agrees_with_
    longest_completed_streak` pins that correspondence rather than leaving
    it to two independently-maintained max() calls.
    """
    bounds = streak_bounds(records)
    completed = bounds[:-1] if bounds else []
    matching = [b for b in completed if b["verdict"] == verdict]
    if not matching:
        return None
    return max(matching, key=lambda b: b["confirmed_span_s"])


def current_streak_duration(records: list, now_fn=now_utc_iso) -> dict | None:
    """How long the box has held its LATEST observed verdict, measured
    against `now_fn()` rather than only the last two checks' own
    timestamps -- round 310 hand-computed this exact arithmetic in prose
    for its own single outage ("2026-08-29T02:10:00.1Z", "3h37m35s"); every
    round since has had to redo that subtraction by hand. This makes it a
    reusable, tested function that also accounts for time elapsed SINCE
    the last check, not just between checks, so an outage started three
    checks ago and still ongoing right now reports its real elapsed time
    rather than stopping at the last check's own timestamp the way
    `summarize_log`'s streak `end` field deliberately does (that field
    also serves backfilled/historical streaks where "now" is meaningless).

    Also reports whether the CURRENT streak already exceeds the longest
    COMPLETED streak of the same verdict the log has ever seen
    (`longest_completed_streak`) -- round 316's own next-steps flagged this
    comparison as "worth a line... once this outage finally ends", but an
    ongoing streak's elapsed-so-far is already a real lower bound on its
    true length, so it can be compared against completed history right
    now rather than waiting for a verdict flip that may be rounds away.

    Round 334 adds the bracket half of the same comparison. `elapsed_s` is
    a check-to-check span, so it is a strict LOWER bound on how long the
    box has actually held this verdict; `elapsed_upper_s` (measured from
    `streak_bounds`' `earliest_possible_start_utc`, i.e. from the last
    instant the box was demonstrably in the OTHER state) is the matching
    upper bound. `exceeds_longest_completed` compares this streak's lower
    bound against the previous record's lower bound -- a like-for-like
    comparison, but not a proof; `definitely_exceeds_longest_completed`
    compares it against the previous record's UPPER bound, which is a
    proof: the current streak already beats the old record even reading the
    old record as generously as the log allows.

    Returns None for an empty log. Walks the sorted log backwards from the
    most recent record, extending the streak start back through every
    immediately-preceding record that shares the SAME verdict class
    (matching `summarize_log`'s own adjacency rule) -- a real transition to
    a different verdict, or the start of the log, ends the walk.
    """
    if not records:
        return None
    ordered = sorted(records, key=_sort_key)
    verdict = ordered[-1]["verdict"]
    start = ordered[-1]["checked_at_utc"]
    start_round = ordered[-1].get("round")
    for rec in reversed(ordered):
        if rec["verdict"] != verdict:
            break
        start = rec["checked_at_utc"]
        start_round = rec.get("round")
    now = now_fn()
    start_dt = _parse_ts(start)
    now_dt = _parse_ts(now)
    elapsed_s = (now_dt - start_dt).total_seconds()
    prior = longest_completed_streak(ordered, verdict)
    prior_s = _streak_span_seconds(prior) if prior is not None else None
    margin_s = None if prior_s is None else elapsed_s - prior_s
    current_bounds = streak_bounds(ordered)[-1]
    start_unc_s = current_bounds["start_uncertainty_s"]
    elapsed_upper_s = None if start_unc_s is None else elapsed_s + start_unc_s
    prior_bounds = longest_completed_streak_bounds(ordered, verdict)
    prior_max_s = None if prior_bounds is None else prior_bounds["max_possible_span_s"]
    definite_margin_s = None if prior_max_s is None else elapsed_s - prior_max_s
    return {
        "verdict": verdict,
        "streak_start_utc": start,
        "streak_start_round": start_round,
        "latest_check_round": ordered[-1].get("round"),
        "as_of_utc": now,
        "elapsed_s": elapsed_s,
        "elapsed_human": format_duration_s(elapsed_s),
        "longest_completed_same_verdict_streak_s": prior_s,
        "longest_completed_same_verdict_streak_human": (
            None if prior_s is None else format_duration_s(prior_s)
        ),
        "exceeds_longest_completed": (
            None if prior_s is None else elapsed_s > prior_s
        ),
        "margin_s": margin_s,
        "margin_human": (
            None if margin_s is None else format_duration_s(abs(margin_s))
        ),
        # --- round 334: bracket half of the same two questions ---
        "earliest_possible_start_utc": current_bounds["earliest_possible_start_utc"],
        "earliest_possible_start_source": current_bounds["earliest_possible_start_source"],
        "start_uncertainty_s": start_unc_s,
        "start_uncertainty_human": (
            None if start_unc_s is None else format_duration_s(start_unc_s)
        ),
        "elapsed_upper_s": elapsed_upper_s,
        "elapsed_upper_human": (
            None if elapsed_upper_s is None else format_duration_s(elapsed_upper_s)
        ),
        "longest_completed_same_verdict_streak_max_possible_s": prior_max_s,
        "longest_completed_same_verdict_streak_max_possible_human": (
            None if prior_max_s is None else format_duration_s(prior_max_s)
        ),
        "definitely_exceeds_longest_completed": (
            None if prior_max_s is None else elapsed_s > prior_max_s
        ),
        "definite_margin_s": definite_margin_s,
        "definite_margin_human": (
            None if definite_margin_s is None
            else format_duration_s(abs(definite_margin_s))
        ),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="mode", required=True)

    cp = sub.add_parser("check")
    cp.add_argument("--round", type=int, default=None)
    cp.add_argument("--notes", default="")
    cp.add_argument("--hostname", default=DEFAULT_HOSTNAME)
    cp.add_argument("--ssh-target", default=DEFAULT_SSH_TARGET)
    cp.add_argument("--ssh-key", default=DEFAULT_SSH_KEY)
    cp.add_argument("--connect-timeout", type=int, default=DEFAULT_CONNECT_TIMEOUT_S)
    cp.add_argument("--log-path", default=DEFAULT_LOG_PATH)
    cp.add_argument("--no-append", action="store_true", help="print only, don't append to the log")

    sp = sub.add_parser("summarize")
    sp.add_argument("--log-path", default=DEFAULT_LOG_PATH)

    tp = sub.add_parser("status", help="current streak's verdict + elapsed time as of now")
    tp.add_argument("--log-path", default=DEFAULT_LOG_PATH)

    bp = sub.add_parser("bounds",
                        help="per-streak [confirmed, max-possible] span brackets")
    bp.add_argument("--log-path", default=DEFAULT_LOG_PATH)
    bp.add_argument("--verdict", default=None,
                    help="only report streaks with this verdict (e.g. down)")

    args = p.parse_args(argv)

    if args.mode == "check":
        record = check(round_=args.round, hostname=args.hostname, ssh_target=args.ssh_target,
                        ssh_key=args.ssh_key, connect_timeout=args.connect_timeout,
                        notes=args.notes)
        if not args.no_append:
            append_record(record, args.log_path)
        print(json.dumps(record, indent=2))
        return 0

    if args.mode == "status":
        records = load_log(args.log_path)
        print(json.dumps(current_streak_duration(records), indent=2))
        return 0

    if args.mode == "bounds":
        records = load_log(args.log_path)
        bounds = streak_bounds(records)
        if args.verdict:
            bounds = [b for b in bounds if b["verdict"] == args.verdict]
        print(json.dumps({"n_streaks": len(bounds), "streaks": bounds}, indent=2))
        return 0

    records = load_log(args.log_path)
    print(json.dumps(summarize_log(records), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
