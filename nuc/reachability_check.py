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
import re
import subprocess
import sys
import time
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


# --- Round 370: the suspend witness -------------------------------------
#
# Round 184 hypothesised that some of this box's reachability gaps are
# SUSPEND rather than power-off. Round 340 sharpened it into a soundness
# question about our own instrument: `boot_utc` is `now - /proc/uptime`, and
# reading "boot_utc unchanged" as "no reboot" assumes `/proc/uptime` keeps
# counting while the box is suspended. That was read from kernel
# documentation, never measured here, and round 340 queued "suspend the box,
# resume, and check" -- which needs an operator, so it never happened.
#
# Round 370's answer is to stop depending on the assumption instead of
# trying to verify it. The kernel keeps its own per-boot suspend counters in
# `/sys/power/suspend_stats/`, and `CLOCK_BOOTTIME - CLOCK_MONOTONIC` IS the
# accumulated suspend time for the current boot by definition of the two
# clocks. Record those next to `boot_utc` and the pair
# "boot_utc unchanged AND suspend_success == 0" is sound no matter which
# clock `/proc/uptime` reads. The assumption becomes irrelevant rather than
# unverified.
#
# NOTE the scope limit, which is real: `suspend_stats` and the
# BOOTTIME/MONOTONIC delta both reset at boot, so they witness the CURRENT
# boot only. For boots already in the past the witnesses are
# `classify_suspend_lines` (did the box LOG a suspend) and
# `max_interior_silence` (could it have suspended without logging one).

SUSPEND_REAL_RE = re.compile(
    r"PM: suspend entry|PM: suspend exit|PM: suspend-to-idle|"
    r"Freezing user space|Freezing remaining freezable|"
    r"Preparing to enter system sleep state|"
    r"Restoring platform NVS memory|"
    r"PM: hibernation: hibernation entry|PM: hibernation: hibernation exit|"
    r"Suspending console|PM: Image saved|s2idle",
    re.I)

# Round 364 found 7 of these on boot 0 and correctly refused to read them as
# suspends: `Registered nosave memory` is boot-time setup emitted by any
# kernel built with hibernation support, on a machine that has never slept.
# It is kept as an explicit exclusion rather than merely being absent from
# SUSPEND_REAL_RE so that a future widening of the "real" pattern cannot
# silently re-admit it.
SUSPEND_FALSE_POSITIVE_RE = re.compile(
    r"PM: hibernation: Registered nosave memory", re.I)

SUSPEND_BROAD_RE = re.compile(
    r"PM: suspend|PM: hibernation|Freezing|sleep state|Restoring platform NVS|"
    r"s2idle|suspend-to-idle|systemd-suspend|systemd-sleep|Suspending console",
    re.I)


def classify_suspend_lines(lines) -> dict:
    """Split kernel-log lines into real suspend evidence / known noise / rest.

    Pure, so the pattern set is testable without a box. `real` is the only
    bucket that means "this machine slept"; `false_positive` is round 364's
    `Registered nosave memory`; `other` is everything the broad net caught
    that neither pattern claims -- deliberately surfaced rather than dropped,
    because an unrecognised power-management line is exactly the shape of
    evidence this check exists to find.
    """
    real, false_pos, other = [], [], []
    for line in lines:
        if not SUSPEND_BROAD_RE.search(line):
            continue
        if SUSPEND_FALSE_POSITIVE_RE.search(line):
            false_pos.append(line)
        elif SUSPEND_REAL_RE.search(line):
            real.append(line)
        else:
            other.append(line)
    return {"n_scanned": len(lines), "real": real, "false_positive": false_pos,
            "other": other, "n_real": len(real),
            "n_false_positive": len(false_pos), "n_other": len(other),
            "slept": bool(real)}


def max_interior_silence(seconds) -> dict | None:
    """Longest gap between consecutive entry-seconds in one boot's capture.

    This is the witness that does NOT depend on the box logging anything: a
    suspend of duration D produces a journal silence of at least D, because
    nothing runs to write a record. So the longest interior silence is an
    upper bound on any suspend the box took without logging it.

    `seconds` is the `seconds` list of a journal-seconds capture (integer
    epoch seconds that had at least one journal entry). Returns None for a
    capture with fewer than two seconds in it -- one lone second bounds
    nothing.
    """
    uniq = sorted(set(int(s) for s in seconds or []))
    if len(uniq) < 2:
        return None
    best_gap, best_from = 0, uniq[0]
    for a, b in zip(uniq, uniq[1:]):
        if b - a > best_gap:
            best_gap, best_from = b - a, a
    return {"max_silence_s": best_gap, "from_epoch": best_from,
            "to_epoch": best_from + best_gap, "n_seconds": len(uniq),
            "covered_span_s": uniq[-1] - uniq[0]}


def silence_bound(captures) -> dict:
    """Per-boot and overall silence bounds across a set of journal captures.

    Only `complete` captures count toward the overall bound. An incomplete
    capture is one `journal-boots` could not finish inside the timeout it
    sized (round 358's trap: the probe returns [] for a client-side timeout
    and a truncated scan would otherwise read as a very quiet boot), and a
    truncated scan's biggest gap is not a bound on anything.
    """
    per_boot, incomplete = [], []
    for cap in captures:
        row = {"boot_id": cap.get("boot_id"), "boot_index": cap.get("boot_index"),
               "complete": bool(cap.get("complete"))}
        sil = max_interior_silence(cap.get("seconds") or [])
        row["silence"] = sil
        if not row["complete"] or sil is None:
            incomplete.append(row)
        per_boot.append(row)
    usable = [r for r in per_boot if r["complete"] and r["silence"]]
    usable.sort(key=lambda r: (r["boot_index"] is None, r["boot_index"]))
    overall = max((r["silence"]["max_silence_s"] for r in usable), default=None)
    covered = sum(r["silence"]["covered_span_s"] for r in usable)
    return {"n_captures": len(per_boot), "n_usable": len(usable),
            "n_unusable": len(incomplete),
            "max_silence_s": overall,
            "covered_running_time_s": covered,
            "per_boot": usable, "unusable": incomplete}


def boot_utc_crosscheck(records, boots, tolerance_s: int = 120) -> dict:
    """Compare each logged `boot_utc` against journald's own `first_entry`.

    Two independent instruments for one wall-clock instant. `boot_utc` comes
    from `/proc/uptime` over ssh; `first_entry` comes from the box's journal
    index, which never consults `/proc/uptime`. They can only disagree if
    uptime has lost or gained time relative to the realtime clock -- which is
    exactly the failure mode round 340 worried about, and the check catches
    it whatever the cause (suspend, a clock step, NTP slew).

    Expected sign is NEGATIVE and small: the kernel starts counting uptime
    before journald exists to write its first record, so a healthy
    `boot_utc` lands a few seconds BEFORE `first_entry`.

    Records whose instant predates the oldest boot still in the journal
    cannot be checked at all and are reported as `unmatched` rather than
    quietly dropped.
    """
    rows, unmatched = [], []
    # `parse_boot_history`'s normalised schema: ISO strings, whole seconds.
    # That 1 s quantisation is far below any tolerance worth setting here --
    # the effect being measured (an unlogged suspend) is minutes to hours.
    ordered = sorted(boots, key=lambda b: b["first_entry_utc"])
    for rec in records:
        if not rec.get("boot_utc"):
            continue
        checked = _parse_ts(rec["checked_at_utc"]).timestamp()
        boot_utc = _parse_ts(rec["boot_utc"]).timestamp()
        live = [b for b in ordered
                if _parse_ts(b["first_entry_utc"]).timestamp() <= checked]
        match = live[-1] if live else None
        # +1h of slack past `last_entry_utc`: the boot-history snapshot is
        # taken at one instant, so the OPEN boot's last_entry is already
        # stale by the time an earlier record is compared against it.
        if match is None or checked > _parse_ts(match["last_entry_utc"]).timestamp() + 3600:
            unmatched.append({"round": rec.get("round"),
                              "checked_at_utc": rec["checked_at_utc"],
                              "boot_utc": rec["boot_utc"],
                              "why": "no boot in the journal covers this instant"})
            continue
        delta = boot_utc - _parse_ts(match["first_entry_utc"]).timestamp()
        rows.append({"round": rec.get("round"),
                     "checked_at_utc": rec["checked_at_utc"],
                     "boot_utc": rec["boot_utc"],
                     "boot_index": match["index"], "boot_id": match["boot_id"],
                     "first_entry_utc": match["first_entry_utc"],
                     "delta_s": round(delta, 1),
                     "within_tolerance": abs(delta) <= tolerance_s,
                     "sign_ok": delta <= 0})
    return {"n_checked": len(rows), "n_unmatched": len(unmatched),
            "tolerance_s": tolerance_s,
            "n_out_of_tolerance": sum(1 for r in rows if not r["within_tolerance"]),
            "n_wrong_sign": sum(1 for r in rows if not r["sign_ok"]),
            "max_abs_delta_s": max((abs(r["delta_s"]) for r in rows), default=None),
            "checks": rows, "unmatched": unmatched}


SUSPEND_STATS_FIELDS = ("success", "fail", "last_failed_dev", "last_failed_step")


def suspend_probe(ssh_target: str = DEFAULT_SSH_TARGET, ssh_key: str = DEFAULT_SSH_KEY,
                  connect_timeout: int = DEFAULT_CONNECT_TIMEOUT_S,
                  runner=subprocess.run) -> dict | None:
    """The box's own suspend accounting for the CURRENT boot. READ-ONLY.

    Two independent kernel sources in one round-trip:
      * `/sys/power/suspend_stats/{success,fail}` -- how many suspends the
        kernel has entered and how many failed, this boot.
      * `CLOCK_BOOTTIME - CLOCK_MONOTONIC` -- accumulated suspend time this
        boot, by definition of the two clocks.
    Plus `/proc/uptime` against both clocks, which is what says WHICH clock
    our `boot_utc` instrument is actually reading.

    A separate ssh call for the same reason `boot_probe` is separate: it must
    not weaken `ssh_probe`'s exact-"UP"-stdout rule, which is the basis of
    the `up` verdict.

    Returns None -- never raises -- for every failure mode, exactly like
    `boot_probe`. A missing suspend record must degrade to "we don't know",
    never to "it didn't suspend".
    """
    remote = (
        "python3 -c \"import time;"
        "d={};"
        "d['boottime']=time.clock_gettime(time.CLOCK_BOOTTIME);"
        "d['monotonic']=time.clock_gettime(time.CLOCK_MONOTONIC);"
        "d['uptime']=float(open('/proc/uptime').read().split()[0]);"
        "d.update({k:open('/sys/power/suspend_stats/'+k).read().strip() "
        "for k in ('success','fail','last_failed_dev','last_failed_step')});"
        "import json;print(json.dumps(d))\""
    )
    argv = ["ssh", "-i", ssh_key, "-o", f"ConnectTimeout={connect_timeout}",
            "-o", "BatchMode=yes", ssh_target, remote]
    try:
        res = runner(argv, capture_output=True, text=True, timeout=connect_timeout + 20)
    except subprocess.TimeoutExpired:
        return None
    if res.returncode != 0:
        return None
    try:
        raw = json.loads((res.stdout or "").strip())
    except (json.JSONDecodeError, TypeError):
        return None
    try:
        success = int(raw["success"])
        fail = int(raw["fail"])
        boottime = float(raw["boottime"])
        monotonic = float(raw["monotonic"])
        uptime = float(raw["uptime"])
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "suspend_success": success,
        "suspend_fail": fail,
        "last_failed_dev": raw.get("last_failed_dev") or None,
        "last_failed_step": raw.get("last_failed_step") or None,
        "cumulative_suspend_s": round(boottime - monotonic, 6),
        "uptime_minus_boottime_s": round(uptime - boottime, 4),
        "uptime_minus_monotonic_s": round(uptime - monotonic, 4),
        # The one line a reader wants: did this boot ever sleep?
        "slept_this_boot": success > 0 or (boottime - monotonic) >= 1.0,
    }


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
    suspend = None
    if ssh_result["reachable"]:
        uptime_s = boot_probe(ssh_target, ssh_key, connect_timeout, runner=ssh_runner)
        if uptime_s is not None:
            boot_utc = boot_utc_from_uptime(now_fn(), uptime_s)
        # Round 370: `boot_utc` alone only means "no reboot" if uptime keeps
        # counting through a suspend. Recording the box's own suspend
        # counters beside it removes the dependency on that assumption --
        # see `suspend_probe`. None on a down check and on a failed read;
        # a missing record must read as "unknown", never as "did not sleep".
        suspend = suspend_probe(ssh_target, ssh_key, connect_timeout,
                                runner=ssh_runner)

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
        "suspend": suspend,
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
WITNESS_BOUNDED = "bounded"
WITNESS_FULL = "full"

_BOOT_UTC_SUSPEND_CAVEAT = (
    "boot_utc unchanged rules out a REBOOT inside this gap, not an outage: "
    "/proc/uptime's first field is CLOCK_BOOTTIME-based and keeps counting "
    "across suspend, so a box that slept and woke reports the same boot "
    "time. Suspend is this box's own documented failure mode (round 184: "
    "ARP incomplete => 'the box itself is off/asleep, not a routing "
    "problem'), so this is explicitly NOT counted as a witness."
)

# Round 358. `boot_history` endpoint coverage rules out EXACTLY what
# `boot_utc unchanged` rules out -- a reboot -- and no more. Round 340 gave
# it WITNESS_FULL anyway, which round 352 caught live: with it, the whole log
# reported `unwitnessed 0h00m00s` and `max_unobserved_outage: None`, i.e. it
# claimed to have ruled out the one failure mode (suspend) round 184 inferred
# for this box. Two rules that rule out the same thing must return the same
# strength, so endpoint coverage alone is now REBOOT_ONLY. FULL is not
# reachable from this source at all; the reachable upgrade is
# WITNESS_BOUNDED, which needs the journal's INTERIOR timestamps -- see
# `interior_silence`.
_BOOT_HISTORY_ENDPOINT_CAVEAT = (
    "the boot's [first_entry, last_entry] covers this gap, which rules out a "
    "REBOOT or power-off inside it and nothing else: a suspend/resume keeps "
    "the same boot and leaves the boot's endpoints straddling it, so an "
    "endpoint-coverage test reports a suspended box as continuously up. "
    "Supply journal interior timestamps (`interior_silence`) to upgrade this "
    "to a BOUNDED witness with a real number attached."
)

_BOUNDED_WITNESS_NOTE = (
    "%s ruled out a reboot, and the box's journal logged across this gap "
    "with no silent stretch longer than %s "
    "(%d entry-seconds inside the gap), so any excursion hiding here -- "
    "suspend included -- is at most that long. This is a BOUND, not a "
    "refutation: the probe cannot see a suspend, it can only cap how much of "
    "one could fit."
)


def _gap_witness(verdict: str, earlier: dict, later: dict,
                 t1: datetime, t2: datetime, boots: list | None = None,
                 silence=None) -> dict:
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

    return _up_gap_witness(verdict, earlier, later, t1, t2, boots, silence)


def _silence_upgrade(base: dict, t1: datetime, t2: datetime, silence) -> dict:
    """REBOOT_ONLY + a journal interior that covers the gap -> BOUNDED.

    Deliberately keyed on the STRENGTH, not on the source. Both rules that
    can return REBOOT_ONLY (`boot_utc_unchanged`, `boot_history`) mean the
    same thing -- a reboot is ruled out, an outage is not -- and the journal
    interior answers the second half for either of them. Round 358's first
    cut gated this behind boot-history endpoint coverage and measured
    `bounded_gap_count: 0` on the live log for exactly that reason: the
    r352 boot history's last entry predates this round's own check, so the
    one gap with a fresh interior capture was not covered by it. A journal
    entry proves the box was awake at that instant regardless of what any
    boot record says, so the bound needs no such licence.

    Never downgrades: if the base is NONE (a proven excursion) or FULL, it
    is returned untouched.
    """
    if base["strength"] != WITNESS_REBOOT_ONLY or not callable(silence):
        return base
    sil = silence(t1, t2)
    if sil is None:
        return base
    out = dict(base)
    out["strength"] = WITNESS_BOUNDED
    out["source"] = (base.get("source") or "unknown") + "+journal"
    out["bound_s"] = sil["max_silence_s"]
    out["silence"] = sil
    out["note"] = _BOUNDED_WITNESS_NOTE % (
        base.get("source"), format_duration_s(sil["max_silence_s"]),
        sil["n_entry_seconds"])
    return out


def _up_gap_witness(verdict: str, earlier: dict, later: dict,
                    t1: datetime, t2: datetime, boots, silence) -> dict:
    # --- up streaks ---
    # The box's own boot history is consulted FIRST: it is the only source
    # here that was recorded continuously rather than sampled, so when it
    # has something to say it strictly dominates `boot_utc`, which is two
    # endpoint samples of the same underlying fact.
    if boots:
        from_history = _boot_history_witness(t1, t2, boots, earlier, later, verdict)
        if from_history is not None:
            return _silence_upgrade(from_history, t1, t2, silence)
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
    return _silence_upgrade(
        {"strength": WITNESS_REBOOT_ONLY, "source": "boot_utc_unchanged",
         "note": _BOOT_UTC_SUSPEND_CAVEAT, "missed_excursion": None},
        t1, t2, silence)


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


# --------------------------------------------------------------------------
# Round 358: the journal's INTERIOR, which is what turns an endpoint claim
# into a bounded one.
#
# `--list-boots` gives each boot's first and last entry, and says nothing
# about what happened between them. A box that suspended for six hours in the
# middle of a boot has exactly the same first/last entry as one that ran the
# whole time, so endpoint coverage cannot distinguish them -- round 352 §2.
#
# The interior fixes that WITHOUT pretending to detect a suspend. Every
# journal entry is a moment the box was demonstrably awake and writing. So
# the longest stretch inside a gap with NO entry in it is an upper bound on
# any excursion hiding in that gap: a suspend longer than that stretch would
# have had to swallow an entry that exists. The claim goes from
#
#     "the box was up across this gap"        (unearned, suspend-blind)
# to
#     "any excursion here is at most G s"     (earned, and G is measured)
#
# and G is a number a reader can weigh, instead of a boolean they have to
# trust. G is never 0 and cannot be: an arbitrarily short excursion always
# fits between two entries. That is the honest ceiling of this method, and
# it is why the strength is BOUNDED and never FULL.
# --------------------------------------------------------------------------

_JOURNAL_SECONDS_CMD = (
    "journalctl --since @%d --until @%d -o short-unix --no-pager 2>/dev/null "
    "| awk '{ s=$1; sub(/[.].*/, \"\", s); if (s != p) { print s; p = s } }'"
)


def parse_journal_seconds(text: str) -> list:
    """Parse the remote probe's output into sorted, unique epoch seconds.

    One integer per line; anything that is not a positive integer is dropped
    rather than raising. Same fail-closed discipline as
    `parse_boot_history`: this feeds a witness rule, and a witness rule that
    can throw is a witness rule a caller can accidentally treat as evidence.

    Sorting is done here rather than trusted from journalctl. journald's
    output is in journal order, which is *usually* time order but is not
    guaranteed to be across a clock change, and a single out-of-order line
    would otherwise produce a negative interval and silently deflate the
    silence bound -- the one direction this must never fail in.
    """
    out = set()
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = int(line)
        except ValueError:
            continue
        if value > 0:
            out.add(value)
    return sorted(out)


def journal_seconds_probe(since_utc: str, until_utc: str,
                          ssh_target: str = DEFAULT_SSH_TARGET,
                          ssh_key: str = DEFAULT_SSH_KEY,
                          connect_timeout: int = DEFAULT_CONNECT_TIMEOUT_S,
                          timeout_s: int = 180,
                          runner=None) -> list:
    """Whole-second timestamps of journal entries in [since_utc, until_utc].

    ONE ssh call for the entire window, not one per gap: the reduction to
    distinct seconds happens on the box (`awk`, run-length dedup of an
    already-ordered stream), so the payload is one short line per second
    that carries at least one entry -- measured at ~1.9k lines/day on this
    box, i.e. ~20 kB/day, against ~50k raw entries/day.

    Returns [] on ANY failure, exactly like `boot_history_probe`: no
    evidence is the safe answer, and [] makes every downstream
    `interior_silence` call return None rather than a fabricated bound.
    """
    try:
        t_from = int(_parse_ts(since_utc).timestamp())
        t_to = int(_parse_ts(until_utc).timestamp())
    except Exception:
        return []
    if t_to < t_from:
        return []
    run = runner or (lambda cmd: subprocess.run(cmd, capture_output=True,
                                                text=True, timeout=timeout_s))
    cmd = ["ssh", "-i", ssh_key, "-o", "BatchMode=yes",
           "-o", f"ConnectTimeout={connect_timeout}",
           "-o", "StrictHostKeyChecking=accept-new",
           ssh_target, _JOURNAL_SECONDS_CMD % (t_from, t_to)]
    try:
        proc = run(cmd)
    except Exception:
        return []
    if getattr(proc, "returncode", 1) != 0:
        return []
    return parse_journal_seconds(getattr(proc, "stdout", "") or "")


# --------------------------------------------------------------------------
# Per-boot journal capture, cached.  (round 364)
#
# Round 358 tried ONE capture over the whole reachability-log span and it
# fail-closed to `n_seconds: 0` after 1417 s against a 1400 s client timeout
# -- the probe's own "return [] on any failure" rule turning a too-small
# timeout into a silent absence of evidence.  Its closing handoff was "one
# scan per boot_id, cached, timeout sized from that rate".  This is that.
#
# Three properties, each earning its place:
#
# 1. PER BOOT, because a closed boot's journal is IMMUTABLE.  Boot -2 costs a
#    projected 1955 s to scan on this box; paying that once ever, rather than
#    once per E-round, is the difference between the sweep being affordable
#    and it never being run.  The open boot (index 0) is re-scanned every
#    time and is the only one that ever is.
#
# 2. TIMEOUT SIZED FROM A MEASURED RATE, not from a constant.  A 300 s window
#    in the middle of the boot is timed ON THE BOX (`date +%s%N` around
#    journalctl alone, so ssh setup is excluded), and the boot's timeout is
#    extrapolated from it with a 3x + 60 s margin.  Measured on this box
#    2026-08-30, the per-boot scan cost spans 0.3 s to 1955 s -- a 6000x
#    range.  No single constant can serve that; round 358's 1400 s was too
#    big for six boots and too small for one.
#
# 3. THE SIZING IS RECORDED IN THE CACHE, so a later round can see whether a
#    scan that returned few seconds was sparse or was truncated.  `complete`
#    is False whenever the scan did not demonstrably run to completion, and
#    `make_multi_silence_fn` refuses to use an incomplete capture for a
#    window it does not fully cover.
#
# Why the entry-density matters more than the span: boot -5 logs 0.037
# entries/s and boot -2 logs 58.9/s, a 1605x spread across boots of the SAME
# machine days apart.  Round 358 reported boot -1 at "2733/s" and projected
# ~10 min for it; the projection was right (it came from a timed scan) but
# the rate was 2733 entries per MINUTE -- 45.5/s -- which is what this
# round's mid-boot probe measures directly.  Corrected here rather than
# repeated.
# --------------------------------------------------------------------------

_JOURNAL_RATE_PROBE_CMD = (
    "s=$(date +%%s%%N); "
    "n=$(journalctl --since @%d --until @%d -o short-unix --no-pager 2>/dev/null | wc -l); "
    "e=$(date +%%s%%N); echo \"$n $(( (e-s)/1000000 ))\""
)

RATE_PROBE_WINDOW_S = 300
# Multiplier + floor applied to the extrapolated scan time.  3x absorbs a
# mid-boot probe landing in a quiet stretch of an otherwise busy boot, which
# is the failure mode that actually bites: the probe UNDER-estimates and the
# scan gets killed.  Over-estimating only costs a longer ceiling we never hit.
RATE_PROBE_MARGIN = 3.0
RATE_PROBE_FLOOR_S = 60


def parse_rate_probe(text: str) -> dict | None:
    """`"<n_entries> <wall_ms>"` -> {n_entries, wall_ms}, or None."""
    parts = (text or "").split()
    if len(parts) < 2:
        return None
    try:
        return {"n_entries": int(parts[0]), "wall_ms": int(parts[1])}
    except ValueError:
        return None


def size_scan_timeout(probe: dict | None, span_s: float,
                      window_s: int = RATE_PROBE_WINDOW_S,
                      margin: float = RATE_PROBE_MARGIN,
                      floor_s: int = RATE_PROBE_FLOOR_S,
                      ceiling_s: int = 3600) -> dict:
    """Extrapolate a per-boot scan timeout from one timed sample window.

    Returns the timeout AND the projection it came from, because the round
    file has to be able to say why a scan was given the budget it was given.
    A missing/unparseable probe falls back to the floor rather than to a
    large constant: an unmeasured boot should fail fast and be retried, not
    occupy the whole round the way round 358's did.
    """
    if not probe or probe.get("wall_ms") is None or span_s <= 0:
        return {"timeout_s": floor_s, "projected_s": None, "sized_from": "fallback"}
    projected = (probe["wall_ms"] / 1000.0) * (float(span_s) / float(window_s))
    timeout = int(min(ceiling_s, max(floor_s, projected * margin + floor_s)))
    return {"timeout_s": timeout, "projected_s": projected, "sized_from": "measured"}


def journal_rate_probe(mid_from_s: int, mid_to_s: int,
                       ssh_target: str = DEFAULT_SSH_TARGET,
                       ssh_key: str = DEFAULT_SSH_KEY,
                       connect_timeout: int = DEFAULT_CONNECT_TIMEOUT_S,
                       timeout_s: int = 120, runner=None) -> dict | None:
    """Time ONE short journalctl window on the box.  None on any failure."""
    run = runner or (lambda cmd: subprocess.run(cmd, capture_output=True,
                                                text=True, timeout=timeout_s))
    cmd = ["ssh", "-n", "-i", ssh_key, "-o", "BatchMode=yes",
           "-o", f"ConnectTimeout={connect_timeout}",
           "-o", "StrictHostKeyChecking=accept-new",
           ssh_target, _JOURNAL_RATE_PROBE_CMD % (mid_from_s, mid_to_s)]
    try:
        proc = run(cmd)
    except Exception:
        return None
    if getattr(proc, "returncode", 1) != 0:
        return None
    return parse_rate_probe(getattr(proc, "stdout", "") or "")


def boot_scan_targets(boots: list, cache_dir, now_s: float | None = None) -> list:
    """One work item per boot: what to scan, and whether the cache covers it.

    `boots` is `parse_boot_history` output.  A CLOSED boot (any boot that is
    not the newest) whose cache file exists and is `complete` needs no work
    -- its journal cannot change.  The newest boot is always re-scanned; its
    journal is still growing, which is exactly why round 358's single capture
    of it went stale the moment it was written.
    """
    from pathlib import Path as _P
    cache_dir = _P(cache_dir)
    out = []
    newest = max((b.get("index", 0) for b in boots), default=0)
    for b in boots:
        bid = b.get("boot_id") or "unknown"
        f_s = int(_parse_ts(b["first_entry_utc"]).timestamp())
        l_s = int(_parse_ts(b["last_entry_utc"]).timestamp())
        if b.get("index") == newest and now_s:
            l_s = max(l_s, int(now_s))
        path = cache_dir / ("journal-seconds-%s.json" % bid)
        cached, reason = None, "no cache"
        if path.exists():
            try:
                cached = json.loads(path.read_text())
            except Exception:
                cached, reason = None, "unreadable cache"
        is_open = b.get("index") == newest
        if cached and cached.get("complete") and not is_open:
            reason = "cached (closed boot, immutable)"
        elif cached and is_open:
            reason = "open boot, rescan"
        elif cached:
            reason = "cached but incomplete, rescan"
        out.append({
            "index": b.get("index"), "boot_id": bid, "path": str(path),
            "from_s": f_s, "to_s": l_s, "span_s": l_s - f_s,
            "open": is_open,
            "needs_scan": not (cached and cached.get("complete") and not is_open),
            "reason": reason,
            "cached_n_seconds": (cached or {}).get("n_seconds"),
        })
    return sorted(out, key=lambda t: t["span_s"])


def merge_captures(captures: list) -> dict:
    """Union many per-boot captures into ONE the existing consumer accepts.

    `continuity --journal-seconds` and `make_silence_fn` take a single
    `{covers_from_utc, covers_to_utc, seconds}`.  Rather than teach every
    consumer about a list, the per-boot captures are unioned here.

    This is sound, and the reason is worth stating because it is NOT obvious:
    the merged `covers` window spans the inter-boot stretches when the box
    was OFF, and those stretches contain no journal seconds.  A gap landing
    there gets a silence bound equal to its own length -- i.e. no better than
    unwitnessed, which is the correct answer for a period the box was off.
    `interior_silence` only ever produces an UPPER bound on a hidden
    excursion, so a hole in the merged coverage can only WEAKEN the bound,
    never overstate the box's liveness.  Merging cannot err in the unsafe
    direction; it can only decline to help.
    """
    caps = [c for c in captures if c and c.get("seconds")]
    if not caps:
        return {"covers_from_utc": None, "covers_to_utc": None,
                "n_seconds": 0, "seconds": [], "sources": []}
    secs = set()
    for c in caps:
        secs.update(c["seconds"])
    froms = [_parse_ts(c["covers_from_utc"]) for c in caps if c.get("covers_from_utc")]
    tos = [_parse_ts(c["covers_to_utc"]) for c in caps if c.get("covers_to_utc")]
    return {
        "covers_from_utc": _fmt_ts(min(froms)) if froms else None,
        "covers_to_utc": _fmt_ts(max(tos)) if tos else None,
        "n_seconds": len(secs),
        "seconds": sorted(secs),
        "sources": [{"boot_id": c.get("boot_id"), "n_seconds": c.get("n_seconds"),
                     "complete": c.get("complete")} for c in caps],
    }


def interior_silence(t1: datetime, t2: datetime, seconds: list,
                     covers_from: str | None = None,
                     covers_to: str | None = None) -> dict | None:
    """Longest stretch inside (t1, t2) with no journal entry, or None.

    Returns None -- not a number -- whenever the seconds list does not
    provably cover [t1, t2]. A probe window that starts after t1 would make
    the box's silence before the window indistinguishable from real silence,
    and reporting the second as the first is exactly the overstatement this
    function exists to remove.

    Conservative on the truncation, deliberately. `parse_journal_seconds`
    gives whole seconds, and an entry stamped S happened somewhere in
    [S, S+1). The widest silence consistent with two adjacent markers is
    therefore `later.hi - earlier.lo`, so a journal entry contributes S as
    its earliest-liveness and S+1 as its latest. The two probe timestamps
    t1/t2 are exact (we saw the box up at those instants), so they
    contribute themselves for both. The result is an UPPER bound on the
    silence, which is the only direction a bound on a hidden outage may
    ever err in.
    """
    if covers_from is None or covers_to is None:
        return None
    if _parse_ts(covers_from) > t1 or _parse_ts(covers_to) < t2:
        return None
    lo, hi = t1.timestamp(), t2.timestamp()
    if hi < lo:
        return None
    inside = [s for s in seconds if lo <= s <= hi]
    # (earliest-liveness, latest-liveness) per marker.
    markers = [(lo, lo)] + [(float(s), float(s) + 1.0) for s in inside] + [(hi, hi)]
    worst_s, worst_from, worst_to = 0.0, lo, hi
    for (a_lo, _a_hi), (b_lo, b_hi) in zip(markers, markers[1:]):
        span = b_hi - a_lo
        if span > worst_s:
            worst_s, worst_from, worst_to = span, a_lo, b_lo
    # A gap shorter than the silence bound cannot be bounded BELOW its own
    # length; clamp so the bound is never a claim wider than the gap itself.
    gap_s = hi - lo
    if worst_s > gap_s:
        worst_s = gap_s
    return {
        "max_silence_s": worst_s,
        "max_silence_human": format_duration_s(worst_s),
        "silence_from_utc": _fmt_ts(datetime.fromtimestamp(worst_from, tz=timezone.utc)),
        "silence_to_utc": _fmt_ts(datetime.fromtimestamp(worst_to, tz=timezone.utc)),
        "n_entry_seconds": len(inside),
        "gap_s": gap_s,
    }


def _boot_history_witness(t1: datetime, t2: datetime, boots: list,
                          earlier: dict, later: dict, verdict: str) -> dict | None:
    """Witness an UP-streak gap from the box's own boot history, or report
    the excursion it proves. Returns None when the history says nothing.

    Two outcomes, and the asymmetry between them is the whole value:

    - Some boot's [first_entry, last_entry] fully covers [t1, t2] => the box
      did not REBOOT across the gap. Round 340 called that FULL; round 358
      demoted it to WITNESS_REBOOT_ONLY, because it rules out exactly what
      `boot_utc unchanged` rules out and leaves the suspend half open (see
      `_BOOT_HISTORY_ENDPOINT_CAVEAT`). `_gap_witness` upgrades that to
      WITNESS_BOUNDED when a journal-interior capture is available -- that
      upgrade deliberately lives one level up, because a journal entry
      proves liveness on its own and needs no boot record to license it.
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
            return {"strength": WITNESS_REBOOT_ONLY, "source": "boot_history",
                    "note": ("boot %s logged from %s to %s, covering this gap "
                             "at both endpoints. %s"
                             % (b.get("boot_id"), b["first_entry_utc"],
                                b["last_entry_utc"],
                                _BOOT_HISTORY_ENDPOINT_CAVEAT)),
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


def make_silence_fn(capture: dict | None):
    """`{covers_from_utc, covers_to_utc, seconds}` -> a `(t1, t2)` callable.

    Returns None for a missing/empty capture so callers can pass the result
    straight through: `silence=None` is the round-340 behaviour verbatim,
    which keeps the journal-interior upgrade strictly opt-in and keeps every
    pre-358 test meaningful rather than merely still-passing.
    """
    if not capture:
        return None
    seconds = capture.get("seconds") or []
    if not seconds:
        return None
    cf, ct = capture.get("covers_from_utc"), capture.get("covers_to_utc")
    return lambda t1, t2: interior_silence(t1, t2, seconds, cf, ct)


def gap_unobserved_s(gap: dict) -> float:
    """Upper bound on an excursion that could hide inside ONE gap.

    The quantitative axis round 358 added next to the existing boolean one:

      FULL      0.0    -- something rules out an excursion outright
      BOUNDED   bound  -- the measured longest silence inside the gap
      otherwise gap_s  -- the whole gap could be the excursion

    `witnessed` (== FULL) is deliberately left alone, so the
    witnessed/unwitnessed time buckets still partition the log span exactly.
    A BOUNDED gap is NOT witnessed and still contributes its full length to
    `unwitnessed_total_s`; what it contributes here is only its bound. The
    two numbers answer different questions -- "did we rule it out?" and "how
    much could be hiding?" -- and round 340 had only the first, which is why
    a suspend-blind rule could report `max_unobserved_outage: None`.
    """
    if gap.get("witness_strength") == WITNESS_FULL:
        return 0.0
    if gap.get("witness_strength") == WITNESS_BOUNDED and gap.get("bound_s") is not None:
        return min(float(gap["bound_s"]), float(gap["gap_s"]))
    return float(gap["gap_s"])


def gap_continuity(records: list, boots: list | None = None,
                   silence=None) -> list:
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
            w = _gap_witness(s["verdict"], earlier, later, t1, t2, boots, silence)
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
                "bound_s": w.get("bound_s"),
                "interior_silence": w.get("silence"),
            })
            gaps[-1]["unobserved_s"] = gap_unobserved_s(gaps[-1])
            gaps[-1]["unobserved_human"] = format_duration_s(gaps[-1]["unobserved_s"])
        unwitnessed = [g for g in gaps if not g["witnessed"]]
        bounded = [g for g in gaps if g["witness_strength"] == WITNESS_BOUNDED]
        worst = max(unwitnessed, key=lambda g: g["gap_s"], default=None)
        worst_unobs = max((g for g in gaps if g["unobserved_s"] > 0),
                          key=lambda g: g["unobserved_s"], default=None)
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
            "bounded_gap_count": len(bounded),
            "unobserved_total_s": sum(g["unobserved_s"] for g in gaps),
            "unobserved_total_human": format_duration_s(
                sum(g["unobserved_s"] for g in gaps)),
            "max_unobserved_gap_s": (None if worst_unobs is None
                                     else worst_unobs["unobserved_s"]),
            "max_unobserved_gap_human": (None if worst_unobs is None
                                         else worst_unobs["unobserved_human"]),
            "continuous_confirmed": len(unwitnessed) == 0,
            "missed_excursions": [w for w in
                                  (_gap_witness(s["verdict"], e, l,
                                                _parse_ts(e["checked_at_utc"]),
                                                _parse_ts(l["checked_at_utc"]),
                                                boots, silence)["missed_excursion"]
                                   for e, l in zip(recs, recs[1:]))
                                  if w is not None],
            "gaps": gaps,
        })
    return out


def continuity_report(records: list, boots: list | None = None,
                      silence=None) -> dict:
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
    streaks = gap_continuity(ordered, boots, silence)
    all_gaps = [g for s in streaks for g in s["gaps"]]
    unwitnessed = [g for g in all_gaps if not g["witnessed"]]
    unwitnessed_total = sum(g["gap_s"] for g in unwitnessed)
    witnessed_total = sum(g["gap_s"] for g in all_gaps) - unwitnessed_total
    span_s = (0.0 if len(ordered) < 2 else
              (_parse_ts(ordered[-1]["checked_at_utc"])
               - _parse_ts(ordered[0]["checked_at_utc"])).total_seconds())
    transition_total = span_s - witnessed_total - unwitnessed_total

    bounded = [g for g in all_gaps if g["witness_strength"] == WITNESS_BOUNDED]
    unobserved_total = sum(g["unobserved_s"] for g in all_gaps)

    def _worst(verdict_filter):
        # Round 358: ranked by `unobserved_s`, not `gap_s`. A BOUNDED gap of
        # 14 h whose longest interior silence is 20 min can hide 20 min, and
        # ranking it by its 14 h length would answer a question nobody asked.
        # An unwitnessed gap has unobserved_s == gap_s, so this reduces to
        # the round-340 behaviour exactly when no journal interior is
        # supplied -- the change is a refinement, not a redefinition.
        cands = [g for s in streaks if verdict_filter(s["verdict"])
                 for g in s["gaps"] if g["unobserved_s"] > 0]
        return max(cands, key=lambda g: g["unobserved_s"], default=None)

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
        "bounded_gap_count": len(bounded),
        "unobserved_total_s": unobserved_total,
        "unobserved_total_human": format_duration_s(unobserved_total),
        "max_unobserved_outage_s": (None if hidden_outage is None
                                    else hidden_outage["unobserved_s"]),
        "max_unobserved_outage_human": (None if hidden_outage is None
                                        else hidden_outage["unobserved_human"]),
        "max_unobserved_outage_strength": (None if hidden_outage is None
                                           else hidden_outage["witness_strength"]),
        "max_unobserved_outage_window": (None if hidden_outage is None else {
            "from_round": hidden_outage["from_round"],
            "to_round": hidden_outage["to_round"],
            "from_utc": hidden_outage["from_utc"],
            "to_utc": hidden_outage["to_utc"],
        }),
        "max_unobserved_uptime_s": (None if hidden_uptime is None
                                    else hidden_uptime["unobserved_s"]),
        "max_unobserved_uptime_human": (None if hidden_uptime is None
                                        else hidden_uptime["unobserved_human"]),
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

    jp = sub.add_parser("journal-seconds",
                        help=("LIVE: capture the box's journal entry seconds over "
                              "a window, for `continuity --journal-seconds`"))
    jp.add_argument("--since", required=True, help="UTC ISO, e.g. 2026-08-25T16:11:00Z")
    jp.add_argument("--until", required=True, help="UTC ISO")
    jp.add_argument("--ssh-target", default=DEFAULT_SSH_TARGET)
    jp.add_argument("--ssh-key", default=DEFAULT_SSH_KEY)
    jp.add_argument("--connect-timeout", type=int, default=DEFAULT_CONNECT_TIMEOUT_S)
    jp.add_argument("--timeout", type=int, default=300)
    jp.add_argument("--out", default=None, help="write the capture JSON here too")

    jb = sub.add_parser("journal-boots",
                        help=("LIVE: per-boot journal-seconds capture, CACHED; "
                              "each boot's timeout sized from a measured rate probe"))
    jb.add_argument("--boot-history", required=True,
                    help="saved `journalctl --list-boots -o json` from the box")
    jb.add_argument("--cache-dir", default="state/nuc-journal-cache")
    jb.add_argument("--ssh-target", default=DEFAULT_SSH_TARGET)
    jb.add_argument("--ssh-key", default=DEFAULT_SSH_KEY)
    jb.add_argument("--connect-timeout", type=int, default=DEFAULT_CONNECT_TIMEOUT_S)
    jb.add_argument("--budget-s", type=int, default=None,
                    help=("stop starting new scans once this many seconds of "
                          "wall clock have been spent; the cache makes a "
                          "partial sweep a resumable one, not a wasted one"))
    jb.add_argument("--max-boot-s", type=int, default=None,
                    help="skip any boot whose PROJECTED scan exceeds this")
    jb.add_argument("--plan", action="store_true",
                    help="rate-probe and print the plan; run no full scan")
    jb.add_argument("--merge-out", default=None,
                    help=("union every cached capture into ONE file that "
                          "`continuity --journal-seconds` accepts as-is"))

    gp = sub.add_parser("continuity",
                        help="per-gap witness analysis: is each streak really unbroken?")
    gp.add_argument("--log-path", default=DEFAULT_LOG_PATH)
    gp.add_argument("--verdict", default=None,
                    help="only report streaks with this verdict (e.g. up)")
    gp.add_argument("--gaps", action="store_true",
                    help="include the per-gap detail, not just the rollup")
    gp.add_argument("--journal-seconds", default=None,
                    help=("path to a `journal-seconds` capture JSON "
                          "{covers_from_utc, covers_to_utc, seconds}; upgrades "
                          "boot_history witnesses from reboot_only to bounded"))
    gp.add_argument("--boot-history", default=None,
                    help="path to saved `journalctl --list-boots -o json` output "
                         "from the box; witnesses up-streak gaps from the box's "
                         "own continuous record instead of our probes")

    ap = sub.add_parser("suspend-audit",
                        help="round 370: did this box ever sleep? Answers from "
                             "LOCAL cached data only -- no ssh, no cost.")
    ap.add_argument("--log-path", default=DEFAULT_LOG_PATH)
    ap.add_argument("--boot-history", required=True,
                    help="saved `journalctl --list-boots -o json` from the box")
    ap.add_argument("--cache-dir", default="state/nuc-journal-cache",
                    help="journal-seconds captures, for the silence bound")
    ap.add_argument("--tolerance-s", type=int, default=120,
                    help="max |boot_utc - first_entry| before a check is flagged")
    ap.add_argument("--sweep", default=None,
                    help="optional per-boot kernel-log sweep JSON to fold in")

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

    if args.mode == "journal-seconds":
        seconds = journal_seconds_probe(args.since, args.until,
                                        ssh_target=args.ssh_target,
                                        ssh_key=args.ssh_key,
                                        connect_timeout=args.connect_timeout,
                                        timeout_s=args.timeout)
        capture = {"covers_from_utc": args.since, "covers_to_utc": args.until,
                   "n_seconds": len(seconds), "seconds": seconds}
        # Round 358: an EMPTY capture is never written to --out. The probe
        # returns [] for every failure mode including a client-side timeout,
        # and a file on disk saying "covers 4.5 days, 0 entry-seconds" looks
        # exactly like a measurement of a silent box. `make_silence_fn`
        # already refuses an empty list, so nothing downstream would have
        # been fooled -- but a human reading the directory would have been,
        # and the first wide capture this round produced exactly that file.
        if args.out and seconds:
            Path(args.out).write_text(json.dumps(capture))
        # stdout stays small: the seconds list belongs in --out, not a terminal.
        print(json.dumps({k: v for k, v in capture.items() if k != "seconds"},
                         indent=2))
        return 0 if seconds else 1

    if args.mode == "journal-boots":
        boots = parse_boot_history(Path(args.boot_history).read_text())
        cache_dir = Path(args.cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        targets = boot_scan_targets(boots, cache_dir, now_s=time.time())
        started = time.time()
        results = []
        for t in targets:
            row = {k: t[k] for k in ("index", "boot_id", "span_s", "open",
                                     "needs_scan", "reason")}
            if not t["needs_scan"]:
                results.append(row | {"action": "skip"})
                continue
            if args.budget_s and (time.time() - started) > args.budget_s:
                results.append(row | {"action": "deferred", "why": "budget spent"})
                continue
            mid = (t["from_s"] + t["to_s"]) // 2
            probe = journal_rate_probe(mid, mid + RATE_PROBE_WINDOW_S,
                                       ssh_target=args.ssh_target, ssh_key=args.ssh_key,
                                       connect_timeout=args.connect_timeout)
            sizing = size_scan_timeout(probe, t["span_s"])
            row["rate_probe"] = probe
            row["entries_per_s"] = (round(probe["n_entries"] / RATE_PROBE_WINDOW_S, 4)
                                    if probe else None)
            row |= sizing
            if args.max_boot_s and (sizing["projected_s"] or 0) > args.max_boot_s:
                results.append(row | {"action": "deferred", "why": "over --max-boot-s"})
                continue
            if args.plan:
                results.append(row | {"action": "planned"})
                continue
            t0 = time.time()
            seconds = journal_seconds_probe(
                _fmt_ts(datetime.fromtimestamp(t["from_s"], tz=timezone.utc)),
                _fmt_ts(datetime.fromtimestamp(t["to_s"], tz=timezone.utc)),
                ssh_target=args.ssh_target, ssh_key=args.ssh_key,
                connect_timeout=args.connect_timeout,
                timeout_s=sizing["timeout_s"])
            wall = time.time() - t0
            # `journal_seconds_probe` returns [] for EVERY failure, including
            # a client timeout -- round 358's trap. The one signal that
            # separates "the boot really was silent" from "we got cut off" is
            # whether we came back well inside the budget we sized, so that
            # is what `complete` records, and it is recorded per capture
            # rather than inferred later.
            complete = bool(seconds) and wall < sizing["timeout_s"] * 0.95
            row |= {"action": "scanned", "wall_s": round(wall, 1),
                    "n_seconds": len(seconds), "complete": complete}
            if seconds:
                (cache_dir / ("journal-seconds-%s.json" % t["boot_id"])).write_text(
                    json.dumps({
                        "boot_id": t["boot_id"], "boot_index": t["index"],
                        "covers_from_utc": _fmt_ts(datetime.fromtimestamp(t["from_s"], tz=timezone.utc)),
                        "covers_to_utc": _fmt_ts(datetime.fromtimestamp(t["to_s"], tz=timezone.utc)),
                        "n_seconds": len(seconds), "complete": complete,
                        "scan_wall_s": round(wall, 1),
                        "timeout_s": sizing["timeout_s"],
                        "projected_s": sizing["projected_s"],
                        "rate_probe": probe, "seconds": seconds}))
            results.append(row)
        out = {"n_boots": len(targets), "elapsed_s": round(time.time() - started, 1),
               "results": results}
        if args.merge_out:
            caps = []
            for f in sorted(cache_dir.glob("journal-seconds-*.json")):
                try:
                    caps.append(json.loads(f.read_text()))
                except Exception:
                    continue
            merged = merge_captures(caps)
            Path(args.merge_out).write_text(json.dumps(merged))
            out["merged"] = {k: v for k, v in merged.items() if k != "seconds"}
        print(json.dumps(out, indent=2))
        return 0

    if args.mode == "suspend-audit":
        boots = parse_boot_history(Path(args.boot_history).read_text())
        records = load_log(args.log_path)
        caps = []
        for f in sorted(Path(args.cache_dir).glob("journal-seconds-*.json")):
            try:
                caps.append(json.loads(f.read_text()))
            except Exception:
                continue
        bound = silence_bound(caps)
        cross = boot_utc_crosscheck(records, boots, tolerance_s=args.tolerance_s)
        report = {
            "n_boots_in_history": len(boots),
            # Witness B: could a suspend have happened WITHOUT being logged?
            "silence_bound": {k: v for k, v in bound.items() if k != "per_boot"},
            "per_boot_silence": [
                {"boot_index": r["boot_index"], "boot_id": r["boot_id"],
                 "max_silence_s": r["silence"]["max_silence_s"],
                 "covered_span_s": r["silence"]["covered_span_s"]}
                for r in bound["per_boot"]],
            # Witness C: do our two clocks agree about when each boot started?
            "boot_utc_crosscheck": {k: v for k, v in cross.items()
                                    if k not in ("checks",)},
            "boot_utc_checks": cross["checks"],
        }
        if args.sweep:
            sweep = json.loads(Path(args.sweep).read_text())
            # Witness A: did the box LOG a suspend, per boot?
            per = []
            for b in sweep.get("boots", []):
                per.append({"boot_index": b["index"], "boot_id": b["boot_id"],
                            "kernel_lines": b.get("kernel_lines"),
                            "n_real": len(b.get("real_hits") or []),
                            "n_false_positive": b.get("false_pos_hits"),
                            "n_other": len(b.get("other_hits") or []),
                            "userspace_lines": b.get("userspace_total_lines"),
                            "real_hits": b.get("real_hits") or [],
                            "other_hits": b.get("other_hits") or []})
            report["kernel_log_sweep"] = {
                "n_boots": len(per),
                "n_boots_with_real_hits": sum(1 for r in per if r["n_real"]),
                "total_real_hits": sum(r["n_real"] for r in per),
                "total_false_positives": sum(r["n_false_positive"] or 0 for r in per),
                "total_other": sum(r["n_other"] for r in per),
                "total_userspace_lines": sum(r["userspace_lines"] or 0 for r in per),
                "per_boot": per}
            report["current_boot"] = sweep.get("current_boot")

        # The verdict is deliberately conjunctive across the witnesses that
        # ACTUALLY ran, and `unknown` when a witness is missing rather than
        # defaulting to the reassuring answer.
        logged = report.get("kernel_log_sweep")
        verdict_bits = {
            "no_logged_suspend": (None if logged is None
                                  else logged["total_real_hits"] == 0),
            "max_unlogged_suspend_s": bound["max_silence_s"],
            "clocks_agree": (cross["n_out_of_tolerance"] == 0
                             if cross["n_checked"] else None),
        }
        report["verdict"] = verdict_bits
        print(json.dumps(report, indent=2))
        return 0

    if args.mode == "continuity":
        records = load_log(args.log_path)
        boots = (parse_boot_history(Path(args.boot_history).read_text())
                 if args.boot_history else None)
        capture = (json.loads(Path(args.journal_seconds).read_text())
                   if getattr(args, "journal_seconds", None) else None)
        silence = make_silence_fn(capture)
        report = continuity_report(records, boots, silence)
        report["journal_seconds_loaded"] = 0 if not capture else len(capture.get("seconds") or [])
        report["boot_history_boots"] = 0 if not boots else len(boots)
        if args.gaps:
            detail = gap_continuity(records, boots, silence)
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
