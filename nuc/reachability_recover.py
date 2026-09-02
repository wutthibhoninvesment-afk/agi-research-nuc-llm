#!/usr/bin/env python3
"""reachability_recover.py — rebuild missing `state/nuc-reachability-log.jsonl`
rows from the rounds' OWN transcripts (`logs/round-<N>.json`).

Round 310 seeded the log by hand from `state/nuc-missions.md`'s round addenda
(`reachability_backfill.py`, a deliberately one-shot script). That source is
prose, and it only covers rounds that WROTE an addendum -- so every E round
that probed the box and then died, or simply skipped the addendum, left no row
at all. Round 454 measured the result: of the 55 E rounds in [124, 448], eight
had no row (148, 190, 220, 226, 250, 280, 292, 442), and seven of the eight
have a full `logs/round-<N>.json` transcript sitting on disk carrying the
exact SSH command, the exact output, and a millisecond timestamp.

That transcript is a STRICTLY better source than the prose the backfill read:
it is the observation itself rather than a later summary of it. This module
reads it.

Design rules, because a shell transcript is not a structured API:

1. A probe is any Bash tool call whose command contains `ssh` and one of the
   two documented NUC targets. Nothing else is looked at.
2. DOWN evidence is the ssh client's own failure line for that target
   (`ssh: connect to host <target> port 22: ...`). Only the client emits it.
3. UP evidence is a `HH:MM:SS up ...` line in the output -- the remote
   `uptime`'s own rendering. This is the weakest link in the chain, so:
   - a probe whose output contains BOTH a failure line for a NUC target and
     an uptime line is returned as `conflict`, never silently as `up`;
   - every derived record carries the exact `evidence` line it used, so the
     verdict can be re-checked against the transcript by eye, and round 454
     did exactly that for all seven rows before committing them.
4. `boot_utc` is emitted ONLY from an absolute `uptime -s` line
   (second precision). `uptime`'s own "up 1 day, 8:16" and `who -a`'s
   "system boot 2026-08-27 11:50" are rounded to the minute, and
   `reachability_check.boot_utc_crosscheck` runs a 120 s tolerance against
   this field -- feeding it minute-rounded values would manufacture drift.
   Rounds whose transcript has only the coarse form get `boot_utc: null`
   and the coarse reading in `notes`.
5. The record's `checked_at_utc` is the DECIDING probe's result timestamp:
   the first successful probe on an `up` round (when the box was confirmed
   alive), the last failed probe on a `down` round (when the round gave up).
   Stated here because the choice is arbitrary and a later reader will care.

Unlike `reachability_backfill.py` this module is re-runnable: it derives from
files on disk rather than a hardcoded list, and `append` refuses to write a
round that already has a row.

Usage:
    python3 nuc/reachability_recover.py show --round 280
    python3 nuc/reachability_recover.py recover --round 280 --append
    python3 nuc/reachability_recover.py recover --round 280 --round 292 --append
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reachability_check as rc  # noqa: E402

TAILNET_TARGET = "100.78.44.111"
LAN_TARGET = "192.168.1.37"
NUC_TARGETS = (TAILNET_TARGET, LAN_TARGET)

SSH_FAIL_RE = re.compile(r"ssh: connect to host (\S+) port 22: (.+?)\s*$", re.M)
UPTIME_RE = re.compile(r"^\s*(\d{2}:\d{2}:\d{2})\s+up\s+(.+?),\s+\d+\s+users?,.*$", re.M)
UPTIME_S_RE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})\s*$", re.M)
WHO_BOOT_RE = re.compile(r"system boot\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", re.M)
KEY_MISSING_RE = re.compile(r"Identity file (\S+) not accessible")
TS_PEER_RE = re.compile(r"^\S+\s+pgain-nuc\s+.*$", re.M)


def _blocks(rec: dict) -> list:
    msg = rec.get("message") or {}
    c = msg.get("content")
    return c if isinstance(c, list) else []


def _result_text(block: dict) -> str:
    c = block.get("content")
    if isinstance(c, list):
        return "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
    return c if isinstance(c, str) else ""


def transcript_probes(text: str) -> list:
    """Every NUC ssh probe in one round transcript, in order.

    Pure: text in, list of dicts out. `text` is the transcript's JSONL
    content, so this is testable against a three-line fixture.
    """
    pending, probes = {}, []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = rec.get("timestamp")
        for b in _blocks(rec):
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                cmd = (b.get("input") or {}).get("command") or ""
                pending[b.get("id")] = (cmd, ts)
            elif b.get("type") == "tool_result":
                got = pending.pop(b.get("tool_use_id"), None)
                if got is None:
                    continue
                cmd, use_ts = got
                if "ssh" not in cmd:
                    continue
                targets = [t for t in NUC_TARGETS if t in cmd]
                if not targets:
                    continue
                probes.append(_classify(cmd, _result_text(b), targets, use_ts, ts))
    return probes


def _classify(cmd: str, out: str, targets: list, use_ts, result_ts) -> dict:
    failures = {t: why for t, why in SSH_FAIL_RE.findall(out) if t in NUC_TARGETS}
    up_m = UPTIME_RE.search(out)
    boot_m = UPTIME_S_RE.search(out)
    who_m = WHO_BOOT_RE.search(out)

    if up_m and failures:
        verdict = "conflict"
    elif up_m:
        verdict = "up"
    elif failures:
        verdict = "down"
    else:
        verdict = "unknown"

    ts_line = TS_PEER_RE.search(out)
    ts_online = None
    if ts_line:
        ts_online = "offline" not in ts_line.group(0)

    return {
        "at_utc": _to_z(result_ts),
        "issued_utc": _to_z(use_ts),
        "targets": targets,
        "verdict": verdict,
        "failures": failures,
        "evidence": (up_m.group(0).strip() if up_m
                     else "ssh: connect to host %s port 22: %s" % next(iter(failures.items()))
                     if failures else ""),
        "uptime_text": up_m.group(2).strip() if up_m else None,
        "remote_clock": up_m.group(1) if up_m else None,
        "boot_utc_exact": ("%sT%sZ" % (boot_m.group(1), boot_m.group(2))) if boot_m else None,
        "boot_coarse": who_m.group(1) if who_m else None,
        "key_missing": KEY_MISSING_RE.search(out).group(1) if KEY_MISSING_RE.search(out) else None,
        "tailscale_online": ts_online,
        "tailscale_line": ts_line.group(0).strip() if ts_line else None,
        "command_head": cmd.strip().splitlines()[0][:200] if cmd.strip() else "",
    }


def _to_z(ts):
    """Transcript timestamps are ISO-8601 with milliseconds; the log uses
    whole seconds and a `Z`. Truncate, never round -- a rounded-up
    `checked_at_utc` can cross a real boundary."""
    if not ts:
        return None
    s = str(ts).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s).astimezone(timezone.utc)
    except ValueError:
        return None
    return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def verdict_from_probes(probes: list) -> dict:
    """Round-level verdict, plus the single probe that decided it.

    `up` if ANY probe reached the box (the box was demonstrably alive during
    the round); `down` only if probes were made and none reached it. A
    `conflict` probe never contributes an `up` -- it is surfaced.
    """
    conflicts = [p for p in probes if p["verdict"] == "conflict"]
    ups = [p for p in probes if p["verdict"] == "up"]
    downs = [p for p in probes if p["verdict"] == "down"]
    if conflicts:
        return {"verdict": None, "why": "conflicting probe(s); resolve by hand",
                "deciding": None, "conflicts": conflicts}
    if ups:
        return {"verdict": "up", "why": "first probe that reached the box",
                "deciding": ups[0], "conflicts": []}
    if downs:
        # NOT simply `downs[-1]`. The LAN path is unusable from the driver
        # host (no `id_ed25519_nuc` key), so its timeout is not a box-down
        # signal at all -- round 442's own knowledge file makes exactly that
        # point, and taking its last probe would have pinned that round's
        # `checked_at_utc` to the weaker of its two observations. The deciding
        # probe is the last FAILURE on a path that could have worked.
        tailnet = [p for p in downs if TAILNET_TARGET in p["failures"]]
        return {"verdict": "down",
                "why": ("last tailnet failure (the only usable path)" if tailnet
                        else "last probe before the round gave up; NO tailnet "
                             "probe failed, so this verdict rests on an "
                             "unusable path -- treat with suspicion"),
                "deciding": (tailnet or downs)[-1], "conflicts": []}
    return {"verdict": None, "why": "no NUC ssh probe in this transcript",
            "deciding": None, "conflicts": []}


def record_from_probes(round_: int, probes: list, extra_note: str = "") -> dict:
    v = verdict_from_probes(probes)
    if v["verdict"] is None:
        raise ValueError("round %s: %s" % (round_, v["why"]))
    d = v["deciding"]
    up = v["verdict"] == "up"

    # An absolute `uptime -s` date can only have come from the box, so on an
    # `up` round it is usable wherever in the transcript it appears -- not
    # only in the probe that happened to carry the `uptime` line. On a `down`
    # round nothing reached the box, so there is nothing to read.
    boot_exact = (next((p["boot_utc_exact"] for p in probes if p["boot_utc_exact"]), None)
                  if up else None)
    boot_coarse = (next((p["boot_coarse"] for p in probes if p["boot_coarse"]), None)
                   if up else None)
    key_missing = next((p["key_missing"] for p in probes if p["key_missing"]), None)

    ts_online = next((p["tailscale_online"] for p in probes
                      if p["tailscale_online"] is not None), None)

    stderr = ""
    rccode = 0 if up else 255
    if not up:
        tgt, why = next(iter(d["failures"].items()))
        stderr = "ssh: connect to host %s port 22: %s" % (tgt, why)

    notes = [
        "Recovered by round 454 from this round's own transcript logs/round-%d.json, "
        "which round 310's prose backfill never read. Deciding probe issued %s, "
        "answered %s: `%s`. Evidence line: %s" % (
            round_, d["issued_utc"], d["at_utc"], d["command_head"], d["evidence"] or "(none)"),
        "%d NUC ssh probe(s) in the transcript (%d up, %d down)." % (
            len(probes), sum(p["verdict"] == "up" for p in probes),
            sum(p["verdict"] == "down" for p in probes)),
    ]
    if boot_exact:
        notes.append("boot_utc from an absolute `uptime -s` line, second precision.")
    elif boot_coarse:
        notes.append("boot_utc left null on purpose: this transcript's only boot reading is "
                     "minute-rounded (%s), and boot_utc_crosscheck runs a 120 s tolerance "
                     "against that field." % boot_coarse)
    if key_missing:
        notes.append("LAN path unusable, not merely unreachable: %s does not exist on the "
                     "driver host." % key_missing)
    if extra_note:
        notes.append(extra_note)

    return {
        "checked_at_utc": d["at_utc"],
        "round": round_,
        "track": "NUC-integration(E)",
        "verdict": v["verdict"],
        "ssh_reachable": up,
        "ssh_returncode": rccode,
        "ssh_stderr": stderr,
        "tailscale_online": ts_online,
        "tailscale_last_seen_utc": None,
        "tailscale_last_write_utc": None,
        "tailscale_error": None,
        "boot_utc": boot_exact,
        "suspend": None,
        "source": "transcript-r%d" % round_,
        "precision": "precise",
        "notes": " ".join(notes),
    }


def recover(round_: int, transcript_dir: str = "logs", extra_note: str = "") -> dict:
    p = Path(transcript_dir) / ("round-%d.json" % round_)
    if not p.exists():
        raise FileNotFoundError("no transcript for round %d at %s" % (round_, p))
    return record_from_probes(round_, transcript_probes(p.read_text()), extra_note)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="mode", required=True)
    for name in ("show", "recover"):
        sp = sub.add_parser(name)
        sp.add_argument("--round", type=int, action="append", required=True)
        sp.add_argument("--transcript-dir", default="logs")
        sp.add_argument("--log-path", default=rc.DEFAULT_LOG_PATH)
        if name == "recover":
            sp.add_argument("--append", action="store_true")
    args = ap.parse_args(argv)

    if args.mode == "show":
        for n in args.round:
            p = Path(args.transcript_dir) / ("round-%d.json" % n)
            probes = transcript_probes(p.read_text())
            print(json.dumps({"round": n, "n_probes": len(probes),
                              "verdict": verdict_from_probes(probes)["verdict"],
                              "probes": probes}, indent=2))
        return 0

    existing = {r.get("round") for r in rc.load_log(args.log_path)}
    out, wrote = [], 0
    for n in args.round:
        if n in existing:
            out.append({"round": n, "skipped": "already has a row"})
            continue
        rec = recover(n, args.transcript_dir)
        out.append(rec)
        if args.append:
            rc.append_record(rec, args.log_path)
            wrote += 1
    print(json.dumps({"n_written": wrote, "records": out}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
