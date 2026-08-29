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
    python3 nuc/reachability_check.py continuity
        (per-gap witness analysis: is each streak really unbroken?)
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


def _fmt_ts(dt: datetime) -> str:
    """Inverse of `_parse_ts` for the canonical form this module writes.

    Deliberately drops any sub-second part: every timestamp this function
    is applied to is a `checked_at_utc` (already whole-second) being echoed
    back into a human-readable note, and rendering "2026-08-29T02:13:07Z"
    rather than "...07+00:00" keeps those notes in the same shape as every
    other timestamp in the log.
    """
    return dt.strftime(TS_FORMAT)


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


# Verdict classes for which `tailscale_last_seen_utc` carries the meaning
# `gap_continuity` needs ("the last instant the peer was demonstrably
# alive"). Same set as `_LAST_SEEN_BOUNDS_START` and deliberately aliased
# to it rather than re-typed: the two rules ask different questions (when
# did the streak START vs was the streak CONTINUOUS) but they are only
# sound for the verdicts where LastSeen means "not seen since", so if that
# set ever changes it must change for both at once.
_LAST_SEEN_WITNESSES_GAP = _LAST_SEEN_BOUNDS_START

# Witness strengths, weakest first. Only "full" counts as witnessed.
WITNESS_NONE = "none"
WITNESS_REBOOT_ONLY = "reboot_only"
WITNESS_FULL = "full"

_BOOT_UTC_SUSPEND_CAVEAT = (
    "boot_utc unchanged rules out a REBOOT inside this gap, not an outage: "
    "/proc/uptime's first field is CLOCK_BOOTTIME-based and keeps counting "
    "across suspend, so a box that slept and woke reports the same boot "
    "time. Suspend is this box's own documented failure mode (round 184: "
    "ARP incomplete => 'the box itself is off/asleep, not a routing "
    "problem'), so this is explicitly NOT counted as a witness."
)


def _gap_witness(verdict: str, earlier: dict, later: dict,
                 t1: datetime, t2: datetime, boots: list | None = None) -> dict:
    """Classify ONE gap between two adjacent same-verdict records.

    Returns `{strength, source, note, missed_excursion}` where
    `missed_excursion` is either None or a dict describing POSITIVE
    evidence that the box changed state inside the gap (as opposed to the
    ordinary case, which is merely an absence of evidence that it did not).

    Fails closed: any datum that is missing, contradictory, or whose
    meaning is not established for this verdict yields `WITNESS_NONE`. A
    continuity claim is exactly the kind of thing that is cheap to assert
    and expensive to be wrong about, so the default answer is "we do not
    know", and only two named rules can move off it.
    """
    if verdict in _LAST_SEEN_WITNESSES_GAP:
        last_seen = later.get("tailscale_last_seen_utc")
        if not last_seen:
            return {"strength": WITNESS_NONE, "source": None,
                    "note": "no tailscale_last_seen_utc on the later record",
                    "missed_excursion": None}
        seen_dt = _parse_ts(last_seen)
        if seen_dt <= t1:
            # The peer was last seen alive at or before the EARLIER check,
            # as reported by a read taken at the LATER one. So it was not
            # seen on the tailnet at any instant in (t1, t2] -- the gap
            # cannot hide an up excursion tailscale would have noticed.
            # Note this is strictly more general than "LastSeen unchanged
            # across the two records": it needs no LastSeen at all on the
            # earlier record, which is what lets it witness the 184->196
            # gap, whose earlier record predates the field.
            return {"strength": WITNESS_FULL, "source": "tailscale_last_seen",
                    "note": ("peer last seen %s, at or before the earlier check "
                             "%s => not seen on the tailnet during the gap"
                             % (last_seen, _fmt_ts(t1))),
                    "missed_excursion": None}
        if t1 < seen_dt < t2:
            # Positive evidence of a MISSED EXCURSION: something saw the
            # peer alive strictly inside a span this log calls one
            # continuous outage. Reported, never silently dropped -- the
            # whole point of the field is that it can contradict us.
            return {"strength": WITNESS_NONE, "source": None,
                    "note": "tailscale saw the peer alive INSIDE this down gap",
                    "missed_excursion": {
                        "kind": "tailscale_last_seen_inside_gap",
                        "verdict": verdict,
                        "from_utc": _fmt_ts(t1), "to_utc": _fmt_ts(t2),
                        "evidence_utc": last_seen,
                        "evidence_field": "tailscale_last_seen_utc",
                        "from_round": earlier.get("round"),
                        "to_round": later.get("round"),
                    }}
        # seen_dt >= t2: the peer was seen alive at or after a check that
        # called it down. Round 334's `streak_bounds` drops this same shape
        # rather than clamping it; so does this, for the same reason -- it
        # implies more transitions than one gap can represent.
        return {"strength": WITNESS_NONE, "source": None,
                "note": ("contradictory: tailscale_last_seen %s is at or after "
                         "the later down check itself" % last_seen),
                "missed_excursion": None}

    # --- up streaks ---
    # The box's own boot history is consulted FIRST: it is the only source
    # here that was recorded continuously rather than sampled, so when it
    # has something to say it strictly dominates `boot_utc`, which is two
    # endpoint samples of the same underlying fact.
    if boots:
        from_history = _boot_history_witness(t1, t2, boots, earlier, later, verdict)
        if from_history is not None:
            return from_history
    # LastSeen is deliberately NOT consulted here. On an up record it means
    # "seen alive during this streak", which is evidence about the streak's
    # interior, not about whether the interior was unbroken -- the same
    # asymmetry round 334 encoded in `_LAST_SEEN_BOUNDS_START`.
    b1, b2 = earlier.get("boot_utc"), later.get("boot_utc")
    if not b1 or not b2:
        return {"strength": WITNESS_NONE, "source": None,
                "note": "boot_utc missing on one or both endpoints",
                "missed_excursion": None}
    d1, d2 = _parse_ts(b1), _parse_ts(b2)
    if d2 > d1:
        return {"strength": WITNESS_NONE, "source": None,
                "note": "the box rebooted inside this up gap",
                "missed_excursion": {
                    "kind": "boot_utc_advanced_inside_gap",
                    "verdict": verdict,
                    "from_utc": _fmt_ts(t1), "to_utc": _fmt_ts(t2),
                    "evidence_utc": b2,
                    "evidence_field": "boot_utc",
                    "from_round": earlier.get("round"),
                    "to_round": later.get("round"),
                }}
    if d2 < d1:
        return {"strength": WITNESS_NONE, "source": None,
                "note": ("contradictory: boot_utc moved backwards, %s -> %s"
                         % (b1, b2)),
                "missed_excursion": None}
    return {"strength": WITNESS_REBOOT_ONLY, "source": "boot_utc_unchanged",
            "note": _BOOT_UTC_SUSPEND_CAVEAT, "missed_excursion": None}


# --------------------------------------------------------------------------
# Round 340: witnesses that come from the BOX's own continuous records
# rather than from our probes.
#
# `gap_continuity` shows the ceiling of the probe-based approach: a down gap
# can be witnessed (tailscale's LastSeen is itself a continuously-maintained
# record) but an UP gap cannot, because nothing we sample at check time says
# anything about the interval between checks. No cadence fixes that -- every
# cadence leaves gaps, and halving the gap only halves the blind spot.
#
# The way out is evidence the box generates while we are not looking.
# `journalctl --list-boots` is exactly that: each boot carries the timestamp
# of its first and last journal entry, so the box's own log says when it was
# running and, by subtraction, when it was not -- retroactively, for gaps
# arbitrarily far in the past.
#
# What it CAN witness: reboots and power-offs. A gap fully inside one boot's
# [first_entry, last_entry] is a gap the box spent running and logging.
# What it CANNOT witness: SUSPEND. A suspend/resume keeps the same boot_id
# and leaves the boot's first/last entries straddling it, so this source
# reports a suspended box as continuously up. That matters here specifically
# because suspend is the failure mode round 184 inferred for this box, so
# `boot_history` closes the reboot half of the blind spot and leaves the
# suspend half open. Naming that here rather than shipping it as "the fix"
# is the point -- see `knowledge/round-340-*` for the deferred design of the
# suspend half (it needs the box's real journal to pick a signal, and the
# box has been down for 15h).
# --------------------------------------------------------------------------

def parse_boot_history(text: str) -> list:
    """Parse `journalctl --list-boots -o json` into normalised boot records.

    Output rows carry `index`, `boot_id`, `first_entry_utc`,
    `last_entry_utc`. systemd emits `first_entry`/`last_entry` as
    MICROSECONDS since the epoch, as a JSON number on some versions and a
    decimal string on others; both are accepted, and a row missing either
    endpoint is dropped rather than guessed at (a boot whose journal was
    rotated away cannot bound anything, and inventing an endpoint for it
    would manufacture a witness).

    Empty input, `[]`, and unparseable JSON all yield `[]`: this parser
    feeds a witness rule, and the fail-closed default for a witness rule is
    "no evidence", never an exception that a caller might catch and treat
    as one.
    """
    text = (text or "").strip()
    if not text:
        return []
    try:
        rows = json.loads(text)
    except (ValueError, TypeError):
        return []
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        first = _usec_to_utc(row.get("first_entry"))
        last = _usec_to_utc(row.get("last_entry"))
        if first is None or last is None or first > last:
            continue
        out.append({
            "index": row.get("index"),
            "boot_id": row.get("boot_id"),
            "first_entry_utc": first,
            "last_entry_utc": last,
        })
    out.sort(key=lambda b: b["first_entry_utc"])
    return out


def _usec_to_utc(value) -> str | None:
    """Microseconds-since-epoch (int or decimal string) -> canonical UTC.

    Truncates to whole seconds, matching `format_duration_s` and `_fmt_ts`:
    every other timestamp in this module is whole-second, and a boot record
    that rounded UP could push `last_entry_utc` past an instant the box was
    demonstrably not logging.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        usec = int(value)
    except (TypeError, ValueError):
        return None
    if usec <= 0:
        return None
    return _fmt_ts(datetime.fromtimestamp(usec // 1_000_000, tz=timezone.utc))


def boot_history_probe(ssh_target: str = DEFAULT_SSH_TARGET,
                       ssh_key: str = DEFAULT_SSH_KEY,
                       connect_timeout: int = DEFAULT_CONNECT_TIMEOUT_S,
                       runner=None) -> list:
    """Read the box's boot history over ssh. Returns [] on ANY failure.

    Same discipline as round 334's `boot_probe`: a separate ssh call rather
    than extra output bolted onto `ssh_probe` (whose strict `== "UP"` stdout
    check IS the up verdict), and every failure mode -- unreachable,
    non-zero exit, empty or unparseable output, journal storage set to
    volatile so only the current boot is listed -- degrades to "no
    witnesses", never to an exception or a fabricated one.

    NOT RUN LIVE as of round 340: the box has been unreachable since
    2026-08-29T02:10Z. `runner` is injectable precisely so the parse and
    witness logic could be built and tested in full while it is down.
    """
    run = runner or (lambda cmd: subprocess.run(cmd, capture_output=True,
                                                text=True, timeout=connect_timeout + 20))
    cmd = ["ssh", "-i", ssh_key, "-o", "BatchMode=yes",
           "-o", f"ConnectTimeout={connect_timeout}",
           "-o", "StrictHostKeyChecking=accept-new",
           ssh_target, "journalctl --list-boots -o json"]
    try:
        proc = run(cmd)
    except Exception:
        return []
    if getattr(proc, "returncode", 1) != 0:
        return []
    return parse_boot_history(getattr(proc, "stdout", "") or "")


def _boot_history_witness(t1: datetime, t2: datetime, boots: list,
                          earlier: dict, later: dict, verdict: str) -> dict | None:
    """Witness an UP-streak gap from the box's own boot history, or report
    the excursion it proves. Returns None when the history says nothing.

    Two outcomes, and the asymmetry between them is the whole value:

    - Some boot's [first_entry, last_entry] fully covers [t1, t2] => the box
      was running and logging across the entire gap. A FULL witness, from a
      continuous record, for an interval nobody probed.
    - A boot boundary falls strictly inside [t1, t2] => the box demonstrably
      stopped and restarted inside a span this log calls one unbroken up
      streak. That is a missed excursion WITH EXACT BOUNDS -- the outage ran
      from the earlier boot's last entry to the later boot's first entry --
      which is strictly more than any probe-based rule can ever produce.

    Anything else (history too short, gap straddling a boot we have no
    record of) returns None and leaves the existing rules to answer.
    """
    for b in boots:
        if _parse_ts(b["first_entry_utc"]) <= t1 and t2 <= _parse_ts(b["last_entry_utc"]):
            return {"strength": WITNESS_FULL, "source": "boot_history",
                    "note": ("boot %s logged continuously from %s to %s, "
                             "covering this gap"
                             % (b.get("boot_id"), b["first_entry_utc"],
                                b["last_entry_utc"])),
                    "missed_excursion": None}
    for prev, nxt in zip(boots, boots[1:]):
        down_from = _parse_ts(prev["last_entry_utc"])
        down_to = _parse_ts(nxt["first_entry_utc"])
        if t1 < down_to and down_from < t2:
            return {"strength": WITNESS_NONE, "source": "boot_history",
                    "note": ("the box stopped logging %s and resumed %s, "
                             "inside this gap"
                             % (prev["last_entry_utc"], nxt["first_entry_utc"])),
                    "missed_excursion": {
                        "kind": "boot_history_gap_inside_up_streak",
                        "verdict": verdict,
                        "from_utc": _fmt_ts(t1), "to_utc": _fmt_ts(t2),
                        "evidence_utc": nxt["first_entry_utc"],
                        "evidence_field": "boot_history",
                        "outage_from_utc": prev["last_entry_utc"],
                        "outage_to_utc": nxt["first_entry_utc"],
                        "from_round": earlier.get("round"),
                        "to_round": later.get("round"),
                    }}
    return None


def gap_continuity(records: list, boots: list | None = None) -> list:
    """Per-streak continuity analysis: is each streak actually unbroken?

    Round 334 bracketed each streak's DURATION. This is the adjacent
    question it left open, and the same class of error one level up:
    `summarize_log`'s `n_streaks` is a LOWER bound on the number of state
    transitions, exactly as `confirmed_span_s` was a lower bound on
    duration. Every record here is a probe fired at a moment the driver's
    round rotation picked, never the box; between two same-verdict checks
    the box can flip and flip back, and the log renders that as one
    unbroken streak with no hint that it might not be.

    So each intra-streak gap is classified:

      WITNESS_FULL         some datum rules out a round-trip excursion
                           inside the gap
      WITNESS_REBOOT_ONLY  a reboot is ruled out; an outage is not
                           (see `_BOOT_UTC_SUSPEND_CAVEAT`)
      WITNESS_NONE         no evidence either way -- an entire outage of
                           up to `gap_s` could have happened here

    and `witnessed` means `WITNESS_FULL` alone. The per-streak
    `max_unwitnessed_gap_s` is the headline number: the longest excursion
    this log could be hiding inside a streak it reports as continuous.

    Transition gaps (last check of one streak -> first check of the next)
    are NOT counted here: those are the boundaries round 334's
    `streak_bounds` already brackets, and double-counting them as
    continuity ignorance would mix two different unknowns.
    """
    streaks = _build_streaks(records)
    out = []
    for s in streaks:
        recs = s["records"]
        gaps = []
        for earlier, later in zip(recs, recs[1:]):
            t1, t2 = _parse_ts(earlier["checked_at_utc"]), _parse_ts(later["checked_at_utc"])
            gap_s = (t2 - t1).total_seconds()
            w = _gap_witness(s["verdict"], earlier, later, t1, t2, boots)
            gaps.append({
                "from_round": earlier.get("round"),
                "to_round": later.get("round"),
                "from_utc": earlier["checked_at_utc"],
                "to_utc": later["checked_at_utc"],
                "gap_s": gap_s,
                "gap_human": format_duration_s(gap_s),
                "witnessed": w["strength"] == WITNESS_FULL,
                "witness_strength": w["strength"],
                "witness_source": w["source"],
                "witness_note": w["note"],
            })
        unwitnessed = [g for g in gaps if not g["witnessed"]]
        worst = max(unwitnessed, key=lambda g: g["gap_s"], default=None)
        out.append({
            "verdict": s["verdict"],
            "start_round": s["start_round"],
            "end_round": s["end_round"],
            "n_checks": len(recs),
            "n_gaps": len(gaps),
            "witnessed_gap_count": len(gaps) - len(unwitnessed),
            "unwitnessed_gap_count": len(unwitnessed),
            "unwitnessed_total_s": sum(g["gap_s"] for g in unwitnessed),
            "unwitnessed_total_human": format_duration_s(
                sum(g["gap_s"] for g in unwitnessed)),
            "max_unwitnessed_gap_s": None if worst is None else worst["gap_s"],
            "max_unwitnessed_gap_human": (None if worst is None
                                          else worst["gap_human"]),
            "max_unwitnessed_gap_from_round": None if worst is None else worst["from_round"],
            "max_unwitnessed_gap_to_round": None if worst is None else worst["to_round"],
            "max_unwitnessed_gap_from_utc": None if worst is None else worst["from_utc"],
            "max_unwitnessed_gap_to_utc": None if worst is None else worst["to_utc"],
            # A single-check streak has no gaps at all, so it is trivially
            # continuous in the only sense this function can speak to. Said
            # explicitly because `all([])` being True is exactly the kind of
            # vacuous truth a reader is right to distrust.
            "continuous_confirmed": len(unwitnessed) == 0,
            "missed_excursions": [w for w in
                                  (_gap_witness(s["verdict"], e, l,
                                                _parse_ts(e["checked_at_utc"]),
                                                _parse_ts(l["checked_at_utc"]),
                                                boots)["missed_excursion"]
                                   for e, l in zip(recs, recs[1:]))
                                  if w is not None],
            "gaps": gaps,
        })
    return out


def continuity_report(records: list, boots: list | None = None) -> dict:
    """Whole-log rollup of `gap_continuity`, plus the two numbers that
    change how this track's own history should be read.

    `max_unobserved_outage_s` -- the longest unwitnessed gap inside any UP
    streak -- is an upper bound on an outage the log could have missed in
    its entirety. Any claim of the form "this is the longest outage we have
    ever seen" has to clear it, not just clear the outages we did see.
    Its mirror, `max_unobserved_uptime_s`, is the same bound for an
    up excursion hiding inside a reported outage.

    `transition_count_upper_bound` is None whenever any gap is unwitnessed,
    for round 334's reason: an unwitnessed gap admits arbitrarily many
    round trips, so there is genuinely no upper bound, and printing one
    would be inventing it.

    The three time buckets (`witnessed_total_s`, `unwitnessed_total_s`,
    `transition_gap_total_s`) partition the log's whole span exactly --
    `test_continuity_report_time_buckets_partition_the_log_span` pins it,
    which is what makes `unwitnessed_fraction` a fraction of something real
    rather than of a denominator chosen to flatter it.
    """
    ordered = sorted(records, key=_sort_key)
    streaks = gap_continuity(ordered, boots)
    all_gaps = [g for s in streaks for g in s["gaps"]]
    unwitnessed = [g for g in all_gaps if not g["witnessed"]]
    unwitnessed_total = sum(g["gap_s"] for g in unwitnessed)
    witnessed_total = sum(g["gap_s"] for g in all_gaps) - unwitnessed_total
    span_s = (0.0 if len(ordered) < 2 else
              (_parse_ts(ordered[-1]["checked_at_utc"])
               - _parse_ts(ordered[0]["checked_at_utc"])).total_seconds())
    transition_total = span_s - witnessed_total - unwitnessed_total

    def _worst(verdict_filter):
        cands = [g for s in streaks if verdict_filter(s["verdict"])
                 for g in s["gaps"] if not g["witnessed"]]
        return max(cands, key=lambda g: g["gap_s"], default=None)

    # An outage can only hide inside a streak we called UP, and vice versa.
    hidden_outage = _worst(lambda v: v == "up")
    hidden_uptime = _worst(lambda v: v != "up")
    any_unwitnessed = bool(unwitnessed)
    return {
        "n_records": len(ordered),
        "n_streaks": len(streaks),
        "n_gaps": len(all_gaps),
        "witnessed_gap_count": len(all_gaps) - len(unwitnessed),
        "unwitnessed_gap_count": len(unwitnessed),
        "log_span_s": span_s,
        "log_span_human": format_duration_s(span_s),
        "witnessed_total_s": witnessed_total,
        "witnessed_total_human": format_duration_s(witnessed_total),
        "unwitnessed_total_s": unwitnessed_total,
        "unwitnessed_total_human": format_duration_s(unwitnessed_total),
        "transition_gap_total_s": transition_total,
        "transition_gap_total_human": format_duration_s(transition_total),
        "unwitnessed_fraction": (None if span_s <= 0
                                 else unwitnessed_total / span_s),
        "max_unobserved_outage_s": None if hidden_outage is None else hidden_outage["gap_s"],
        "max_unobserved_outage_human": (None if hidden_outage is None
                                        else hidden_outage["gap_human"]),
        "max_unobserved_outage_window": (None if hidden_outage is None else {
            "from_round": hidden_outage["from_round"],
            "to_round": hidden_outage["to_round"],
            "from_utc": hidden_outage["from_utc"],
            "to_utc": hidden_outage["to_utc"],
        }),
        "max_unobserved_uptime_s": None if hidden_uptime is None else hidden_uptime["gap_s"],
        "max_unobserved_uptime_human": (None if hidden_uptime is None
                                        else hidden_uptime["gap_human"]),
        "confirmed_transitions": max(0, len(streaks) - 1),
        "transition_count_upper_bound": (None if any_unwitnessed
                                         else max(0, len(streaks) - 1)),
        "all_streaks_confirmed_continuous": not any_unwitnessed,
        "missed_excursions": [m for s in streaks for m in s["missed_excursions"]],
        "streaks": [{k: v for k, v in s.items() if k != "gaps"} for s in streaks],
    }


def max_unobserved_streak_s(records: list, verdict: str,
                            boots: list | None = None) -> dict | None:
    """The longest streak of `verdict` that could exist in this log without
    ever having been observed -- i.e. the largest unwitnessed gap inside a
    streak of the OPPOSITE verdict, since that is the only place such a
    streak could hide.

    Returns the gap dict (so the caller can name the window), or None if
    every opposite-verdict gap is witnessed. `verdict="up"` deliberately
    treats "ambiguous" as a place an up excursion could hide, matching
    `continuity_report`'s `!= "up"` split rather than inventing a third
    rule for a verdict class the real log has never contained.
    """
    streaks = gap_continuity(records, boots)
    if verdict == "up":
        cands = [g for s in streaks if s["verdict"] != "up"
                 for g in s["gaps"] if not g["witnessed"]]
    else:
        cands = [g for s in streaks if s["verdict"] == "up"
                 for g in s["gaps"] if not g["witnessed"]]
    return max(cands, key=lambda g: g["gap_s"], default=None)


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
    # Round 340: the third competitor, and the one no prior round compared
    # against -- a streak of this same verdict that the log never observed
    # at all, hiding inside an unwitnessed gap of the opposite verdict.
    hidden = max_unobserved_streak_s(ordered, verdict)
    hidden_s = None if hidden is None else hidden["gap_s"]
    unobserved_margin_s = None if hidden_s is None else elapsed_s - hidden_s
    if prior_max_s is None or hidden_s is None:
        # Abstain rather than guess: an unbounded prior record or an
        # unbounded hidden competitor means the question "is this the
        # longest" has no answer the log can support, and False would read
        # as "we checked and it is not".
        longest_including_unobserved = None
    else:
        longest_including_unobserved = elapsed_s > prior_max_s and elapsed_s > hidden_s
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
        # --- round 340: the unobserved competitor ---
        "max_unobserved_same_verdict_streak_s": hidden_s,
        "max_unobserved_same_verdict_streak_human": (
            None if hidden_s is None else format_duration_s(hidden_s)
        ),
        "max_unobserved_same_verdict_streak_window": (None if hidden is None else {
            "from_round": hidden["from_round"], "to_round": hidden["to_round"],
            "from_utc": hidden["from_utc"], "to_utc": hidden["to_utc"],
        }),
        "unobserved_margin_s": unobserved_margin_s,
        "unobserved_margin_human": (
            None if unobserved_margin_s is None
            else format_duration_s(abs(unobserved_margin_s))
        ),
        "definitely_longest_including_unobserved": longest_including_unobserved,
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

    gp = sub.add_parser("continuity",
                        help="per-gap witness analysis: is each streak really unbroken?")
    gp.add_argument("--log-path", default=DEFAULT_LOG_PATH)
    gp.add_argument("--verdict", default=None,
                    help="only report streaks with this verdict (e.g. up)")
    gp.add_argument("--gaps", action="store_true",
                    help="include the per-gap detail, not just the rollup")
    gp.add_argument("--boot-history", default=None,
                    help="path to saved `journalctl --list-boots -o json` output "
                         "from the box; witnesses up-streak gaps from the box's "
                         "own continuous record instead of our probes")

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

    if args.mode == "continuity":
        records = load_log(args.log_path)
        boots = (parse_boot_history(Path(args.boot_history).read_text())
                 if args.boot_history else None)
        report = continuity_report(records, boots)
        report["boot_history_boots"] = 0 if not boots else len(boots)
        if args.gaps:
            detail = gap_continuity(records, boots)
            if args.verdict:
                detail = [s for s in detail if s["verdict"] == args.verdict]
            report["streaks"] = detail
        elif args.verdict:
            report["streaks"] = [s for s in report["streaks"]
                                 if s["verdict"] == args.verdict]
        print(json.dumps(report, indent=2))
        return 0

    records = load_log(args.log_path)
    print(json.dumps(summarize_log(records), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
