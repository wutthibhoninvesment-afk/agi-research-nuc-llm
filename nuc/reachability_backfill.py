#!/usr/bin/env python3
"""reachability_backfill.py — one-shot script (round 310) that seeds
`state/nuc-reachability-log.jsonl` with the up/down history reconstructed
by hand from `state/nuc-missions.md`'s round addenda (rounds 124-304), so
`reachability_check.py summarize` has a real multi-day dataset to analyze
instead of starting empty at round 310.

Every entry's `checked_at_utc` is derived from a stated boot time
(`uptime -s`) plus a stated elapsed uptime, or (for the two `down` rows) a
knowledge-file mtime / an explicitly-stated wall-clock reading in the
addendum's own prose -- never invented. `precision` is "coarse" for
uptime-derived arithmetic (uptime strings in the source prose are
themselves rounded to the minute) and "precise" only where the source
prose itself already gave a real timestamp (round 196's own explicit
"current time of 2026-08-27T10:54:40Z", round 202's own `uptime -s`
boot time, and both `down` rows' `tailscale_last_seen_utc`, which round
310's own live read confirms is UNCHANGED for round 298/304 since a
peer's LastSeen does not advance while it stays offline).

This script is meant to run exactly once (round 310). Re-running it would
duplicate every row -- `reachability_check.py`'s own `check` command is the
ongoing per-round tool from here forward, not this script.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reachability_check as rc  # noqa: E402

LOG_PATH = "state/nuc-reachability-log.jsonl"


def rec(round_, checked_at, verdict, notes, precision="coarse",
        last_seen=None, ssh_reachable=None):
    if ssh_reachable is None:
        ssh_reachable = (verdict == "up")
    return {
        "checked_at_utc": checked_at,
        "round": round_,
        "track": "NUC-integration(E)",
        "verdict": verdict,
        "ssh_reachable": ssh_reachable,
        "ssh_returncode": 0 if ssh_reachable else 255,
        "ssh_stderr": "" if ssh_reachable else "Connection timed out",
        "tailscale_online": (verdict == "up") if verdict != "ambiguous" else None,
        "tailscale_last_seen_utc": last_seen,
        "tailscale_last_write_utc": None,
        "tailscale_error": None,
        "source": f"backfill-prose-r{round_}",
        "precision": precision,
        "notes": notes,
    }


RECORDS = [
    rec(124, "2026-08-25T16:11:00Z", "up",
        "boot start ~12:58 UTC 08-25 (derived: 16:11 - 3h13m uptime); first "
        "reachable window this track ever found"),
    rec(130, "2026-08-25T18:08:00Z", "up", "same boot, uptime 5h10m/5h18m"),
    rec(136, "2026-08-26T01:51:00Z", "up", "same boot, uptime 12h53m"),
    rec(142, "2026-08-26T03:19:00Z", "up", "same boot, uptime 14h21m"),
    rec(154, "2026-08-26T17:19:00Z", "up", "same boot, uptime 1d4h21m"),
    rec(160, "2026-08-26T18:47:00Z", "up", "same boot, uptime 1d5h49m"),
    rec(166, "2026-08-26T20:54:00Z", "up",
        "service (not box) restarted 19:24 UTC 08-26, ~90min before this round's check"),
    rec(172, "2026-08-26T23:27:00Z", "up", "same restart, 4h03m post-restart"),
    rec(178, "2026-08-27T03:14:00Z", "up", "same restart, 7h50m post-restart"),
    rec(184, "2026-08-27T05:40:00Z", "down",
        "first down window this track ever found (round's own '40-46m ago' "
        "reading, midpoint used); box off/asleep, not a routing problem"),
    rec(196, "2026-08-27T10:54:40Z", "down",
        "same continuous outage as round 184 (reconciled by round 196 itself "
        "against tailscale LastSeen); round's own stated wall-clock 'current "
        "time' used verbatim, not derived",
        precision="precise", last_seen="2026-08-27T04:48:21.1Z"),
    rec(202, "2026-08-27T13:18:26Z", "up",
        "fresh reboot; uptime -s = 2026-08-27T11:50:48Z (round's own stated "
        "boot time, used verbatim); checked_at = sweep start timestamp, also "
        "stated verbatim -- bounds the round-184/196 outage end to between "
        "10:54:40 (still down) and 11:50:48 (already booted)",
        precision="precise"),
    rec(208, "2026-08-27T16:25:48Z", "up", "same boot (11:50:48), uptime 4h35m"),
    rec(214, "2026-08-27T19:14:48Z", "up", "same boot, uptime ~7h24m"),
    rec(232, "2026-08-28T03:15:48Z", "up", "same boot, uptime ~15h25m"),
    rec(238, "2026-08-28T05:54:48Z", "up", "same boot, uptime ~18h04m"),
    rec(244, "2026-08-28T07:50:48Z", "up", "same boot, uptime ~19h58m-20h02m"),
    rec(256, "2026-08-28T11:30:48Z", "up", "same boot, uptime ~23h32m-23h48m"),
    rec(262, "2026-08-28T13:44:48Z", "up", "same boot, uptime ~25h44m-26h04m"),
    rec(268, "2026-08-28T16:11:48Z", "up", "same boot, uptime ~28h21m"),
    rec(274, "2026-08-28T18:06:48Z", "up", "same boot, uptime ~30h16m"),
    rec(286, "2026-08-28T21:41:48Z", "up", "same boot, uptime ~1d9h51m"),
    rec(298, "2026-08-29T02:13:07Z", "down",
        "new outage begins; knowledge-file mtime used as checked_at proxy "
        "(round's own prose only gave 'last seen 1m ago'); "
        "tailscale_last_seen_utc back-derived from round 310's own live read "
        "of the SAME still-unchanged LastSeen field (a peer's LastSeen does "
        "not advance while offline, so this value is exact, not estimated)",
        precision="precise", last_seen="2026-08-29T02:10:00.1Z"),
    rec(304, "2026-08-29T04:14:03Z", "down",
        "same continuous outage as round 298 (confirmed by round 310: "
        "identical unchanged LastSeen); knowledge-file mtime (end of round) "
        "used as checked_at proxy; round's own prose said 'last seen 1h ago' "
        "at start / '2h ago' at end, consistent with mtime - LastSeen = 2h04m",
        precision="precise", last_seen="2026-08-29T02:10:00.1Z"),
]


def main() -> int:
    for r in RECORDS:
        rc.append_record(r, LOG_PATH)
    print(f"wrote {len(RECORDS)} backfilled records to {LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
