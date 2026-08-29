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
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
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


def summarize_log(records: list) -> dict:
    """Group time-ordered records into up/down streaks and report each
    streak's span. Adjacent records with the SAME verdict class (treating
    "ambiguous" as its own class) merge into one streak; "up" and
    "down"/"ambiguous" alternating boundaries are where a real transition
    is inferred to have happened, bounded by the two straddling records'
    own timestamps (not claimed to be exact for coarse/backfilled entries).
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


def _parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


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

    records = load_log(args.log_path)
    print(json.dumps(summarize_log(records), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
