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

# ---------------------------------------------- rendered LastSeen (round 460)
#
# Round 454 left this open and said exactly why: round 190's transcript has
# `offline, last seen 3h ago`, "coarse, and deliberately NOT converted, because
# an hour-derived LastSeen is exactly the 'rounded value walks into a gap'
# hazard round 448 found. The honest route is a precision-aware LastSeen, not
# a division."
#
# So: a bracket, never a point, and the bracket's width comes from a MEASURED
# contract rather than an assumed one. Round 460 calibrated `tailscale
# status`'s plain-text age renderer against `tailscale status --json`'s exact
# `LastSeen` on this host, same instant, all four offline peers
# (2026-09-02T19:37:38Z):
#
#   macbook-neo   age    458.3 s = 7.638 m  -> "7m"    floor 7,  round 8
#   pgain-nuc     age  90582.3 s = 1.0484 d -> "1d"    floor 1,  round 1
#   REDMI 15C     age 1184072.3 s = 13.7045 d -> "13d" floor 13, round 14
#   ROG_Phone6    age 2718719.3 s = 31.4667 d -> "31d" floor 31, round 31
#
# Two of the four discriminate floor from round-to-nearest and both say FLOOR.
# The renderer emits ONE integer and ONE unit -- the largest unit whose floor
# is non-zero -- and never a compound form. So a rendering of `N<unit>` read at
# R means the true age was in [N*u, (N+1)*u).
#
# The read instant R is itself a bracket: the transcript's timestamp is
# truncated to the second by `_to_z`, so R_true is in [R, R+1). Composing:
#
#     LastSeen = R_true - age_true  in  [R - (N+1)*u,  R + 1 - N*u]
#
# closed at both ends because widening our own stated ignorance by a second is
# the safe direction. `reachability_check.last_seen_bounds` consumes this, and
# every rule there evaluates the bracket at whichever end makes its claim
# harder, so a one-hour-wide reading can WITNESS a gap it clears entirely and
# can never ACCUSE across a boundary it straddles.
RENDERED_AGE_RE = re.compile(r"last seen (\d+)([smhd]) ago")
RENDERED_AGE_UNIT_S = {"s": 1, "m": 60, "h": 3600, "d": 86400}

# The read instant's own truncation, in seconds. Same quantity as
# `reachability_check.PRECISION_RESOLUTION_S["precise"]` and deliberately not
# imported from it: that constant is about a LOG ROW's `checked_at_utc`, this
# one is about a TRANSCRIPT timestamp. They agree today for the same reason
# (both are whole-second truncations) and there is no rule saying they must.
READ_INSTANT_RESOLUTION_S = 1


def rendered_age_bounds(read_at_utc: str, n: int, unit: str):
    """`(lo, hi)` ISO-Z strings bracketing the LastSeen behind one rendering.

    `read_at_utc` is the transcript's own truncated-to-the-second timestamp
    for the reading. Raises on an unknown unit rather than guessing a width.
    """
    u = RENDERED_AGE_UNIT_S[unit]
    r = datetime.fromisoformat(read_at_utc.replace("Z", "+00:00"))
    lo = r - timedelta(seconds=(n + 1) * u)
    hi = r + timedelta(seconds=READ_INSTANT_RESOLUTION_S - n * u)
    return (lo.strftime("%Y-%m-%dT%H:%M:%SZ"), hi.strftime("%Y-%m-%dT%H:%M:%SZ"))


def intersect_bounds(brackets: list):
    """Fold several brackets for the SAME LastSeen into one.

    Two readings of one unchanging value must agree, so their brackets
    intersect -- and the intersection is strictly tighter than either whenever
    the reads are not exactly one unit apart. Round 190 read `3h` twice,
    6m18s apart, which narrows a 3601 s bracket to 3223 s.

    An EMPTY intersection is not an error to be papered over: it is positive
    evidence that the value moved between reads, which is round 448's
    recomputation finding arriving through the plain-text door. Returns None,
    and the caller says so in the row's notes rather than picking a favourite.
    """
    if not brackets:
        return None
    lo = max(b[0] for b in brackets)
    hi = min(b[1] for b in brackets)
    return (lo, hi) if lo <= hi else None


def transcript_lastseen_readings(text: str) -> list:
    """Every rendered `pgain-nuc ... last seen N<unit> ago` in one transcript.

    Deliberately NOT restricted to ssh probes the way `transcript_probes` is:
    round 190's two readings came from two different Bash calls and only one
    of them ran ssh. Scanning every tool result is what finds both, and the
    second reading is exactly what tightens the bracket.
    """
    out, pending = [], {}
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
                pending[b.get("id")] = ts
            elif b.get("type") == "tool_result":
                if pending.pop(b.get("tool_use_id"), None) is None:
                    continue
                for m in TS_PEER_RE.finditer(_result_text(b)):
                    a = RENDERED_AGE_RE.search(m.group(0))
                    if not a:
                        continue
                    read_at = _to_z(ts)
                    if not read_at:
                        continue
                    n, unit = int(a.group(1)), a.group(2)
                    out.append({"read_at_utc": read_at, "n": n, "unit": unit,
                                "rendering": "%d%s" % (n, unit),
                                "bounds": rendered_age_bounds(read_at, n, unit),
                                "line": m.group(0).strip()})
    return out


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


def record_from_probes(round_: int, probes: list, extra_note: str = "",
                       readings: list = ()) -> dict:
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

    # ROUND 460. `tailscale_last_seen_utc` stays null -- a rendered `3h ago` is
    # not that field and must never be written into it -- and the bracket goes
    # in beside it under its own name. Emitted only when a reading exists, so
    # the six recovered rows with no rendering re-derive byte-identically and
    # this round's diff touches exactly one row.
    ls_bounds = intersect_bounds([r["bounds"] for r in readings]) if readings else None
    ls_note = None
    if readings and ls_bounds is None:
        ls_note = ("%d rendered LastSeen reading(s) in this transcript (%s) whose "
                   "brackets do NOT intersect -- the value moved between reads, so "
                   "no bracket is emitted." % (
                       len(readings), ", ".join(sorted({r["rendering"] for r in readings}))))
    elif readings:
        ls_note = ("tailscale_last_seen_bounds_utc from %d plain-text reading(s) "
                   "(%s) at %s. `tailscale_last_seen_utc` stays null on purpose: the "
                   "renderer gives an AGE, not the JSON field's instant, and round "
                   "454 refused to divide one into the other. The bracket is the "
                   "honest form -- see reachability_recover.rendered_age_bounds for "
                   "the renderer contract and the calibration behind it." % (
                       len(readings),
                       ", ".join("%s@%s" % (r["rendering"], r["read_at_utc"])
                                 for r in readings),
                       readings[0]["read_at_utc"]))

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
    if ls_note:
        notes.append(ls_note)
    if extra_note:
        notes.append(extra_note)

    out = {
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
    if ls_bounds:
        out["tailscale_last_seen_bounds_utc"] = list(ls_bounds)
    return out


def recover(round_: int, transcript_dir: str = "logs", extra_note: str = "") -> dict:
    p = Path(transcript_dir) / ("round-%d.json" % round_)
    if not p.exists():
        raise FileNotFoundError("no transcript for round %d at %s" % (round_, p))
    text = p.read_text()
    return record_from_probes(round_, transcript_probes(text), extra_note,
                              transcript_lastseen_readings(text))


def rewrite_plan(log_path: str, transcript_dir: str = "logs") -> dict:
    """What re-deriving every `transcript-r*` row would change, key by key.

    The log is append-only for OBSERVATIONS -- a live check never edits an
    older row -- but a recovered row is not an observation, it is a DERIVATION
    from a file that is still on disk, and `test_every_recovered_row_in_the_
    live_log_still_re_derives` already demands the two agree byte-for-byte. So
    when the derivation learns something (round 460: a bracket the transcript
    always carried), the row has to move with it or that test goes red.

    The safety rule, and the reason this is a `plan` before it is a write:
    a rewrite may only ADD keys. Any changed or removed key means the
    derivation's MEANING moved, not just its coverage, and that is a thing a
    human should read about before it lands -- so it is reported as
    `unsafe` and `rewrite` refuses the whole batch.
    """
    rows = rc.load_log(log_path)
    changes, unsafe = [], []
    for i, row in enumerate(rows):
        if not str(row.get("source", "")).startswith("transcript-r"):
            continue
        fresh = recover(row["round"], transcript_dir)
        if fresh == row:
            continue
        added = sorted(set(fresh) - set(row))
        removed = sorted(set(row) - set(fresh))
        changed = sorted(k for k in set(row) & set(fresh) if row[k] != fresh[k])
        # `notes` is the one field a safe rewrite may touch, and only in one
        # direction: the new prose must EXTEND the old, character for
        # character. A recovered row's notes exist to explain the row's own
        # fields, so a rewrite that adds a field has to add the sentence that
        # describes it -- refusing that would make the add-only rule
        # unsatisfiable in exactly the case it was written for. Requiring a
        # prefix keeps it from becoming a loophole: nothing already said about
        # this row can be edited away under cover of "just the notes".
        notes_appended = ("notes" in changed
                          and isinstance(row.get("notes"), str)
                          and isinstance(fresh.get("notes"), str)
                          and fresh["notes"].startswith(row["notes"]))
        blocking = [k for k in changed if not (k == "notes" and notes_appended)]
        entry = {"round": row["round"], "index": i, "added": added,
                 "removed": removed, "changed": changed,
                 "notes_appended_only": notes_appended,
                 "blocking": blocking,
                 "added_values": {k: fresh[k] for k in added}}
        changes.append(entry)
        if removed or blocking:
            unsafe.append(entry)
    return {"n_rows": len(rows), "n_changes": len(changes),
            "changes": changes, "unsafe": unsafe,
            "safe": not unsafe}


def rewrite(log_path: str, transcript_dir: str = "logs", apply: bool = False) -> dict:
    plan = rewrite_plan(log_path, transcript_dir)
    if not plan["safe"]:
        plan["applied"] = False
        plan["refused"] = ("a rewrite may only ADD keys, plus APPEND to `notes`; "
                           "these rows would have a key removed, or a key changed "
                           "in a way that is not a pure notes extension")
        return plan
    if apply and plan["changes"]:
        rows = rc.load_log(log_path)
        for c in plan["changes"]:
            rows[c["index"]] = recover(rows[c["index"]]["round"], transcript_dir)
        with open(log_path, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
    plan["applied"] = bool(apply and plan["changes"])
    return plan


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
    rw = sub.add_parser("rewrite", help="re-derive every transcript-sourced row "
                                       "in place; add-only, refuses otherwise")
    rw.add_argument("--transcript-dir", default="logs")
    rw.add_argument("--log-path", default=rc.DEFAULT_LOG_PATH)
    rw.add_argument("--apply", action="store_true")

    args = ap.parse_args(argv)

    if args.mode == "rewrite":
        out = rewrite(args.log_path, args.transcript_dir, args.apply)
        print(json.dumps(out, indent=2))
        return 0 if out["safe"] else 1

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
