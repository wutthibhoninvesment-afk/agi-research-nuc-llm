#!/usr/bin/env python3
"""The box's own sysstat archive, read as an availability witness.

Round 400. `/var/log/sysstat/saNN` on pgain-nuc holds NINE days of samples at
10-minute resolution -- 2026-08-23 through 2026-08-31 -- written by
`sysstat-collect.timer` since long before this program started probing the box.
Nothing in this track had ever opened a file older than `sa30`.

Two things follow, and they are the reason this module exists:

1. **It is a retroactive uptime witness, at 10-minute resolution, that costs
   nothing to consult.** This track's `nuc/reachability_check.py` brackets
   outages from OUR ssh probes, which happen once per E-round -- roughly once
   an hour at best, and not at all for the 26 unwitnessed gaps in its log.
   `sadc` sampled every 10 minutes the whole time, from INSIDE the box, and
   writes a `LINUX RESTART` record at every boot. Where the two instruments
   overlap, one can check the other; where the probe log is silent, the
   archive still has an answer.

2. **The witness is of a fundamentally different kind.** A reachability probe
   answers "could I reach it from here", which conflates the box, the tailnet
   and the prober. A `sar` sample answers "was this kernel running", full
   stop. Round 340's next-step item 1 asked for retroactive gap witnessing and
   got `journalctl --list-boots`; this is a second, independent source for the
   same question, and unlike journald it is fixed-size and rotation-dated
   rather than subject to `SystemMaxUse` eviction.

WHAT THIS MODULE WILL NOT DO
----------------------------
It will not turn absence of data into downtime. `sadc` not writing a sample
has at least four causes -- the box was off, the box was suspended, the timer
was masked, or the day file is outside the retention window -- and only the
first two are outages. So:

* Gaps at the FIRST or LAST edge of the capture are `coverage_edge`, never
  downtime: `sa23` begins at 14:20 because `sa22` has been rotated away, not
  because the box was down until lunchtime.
* An interior gap with a `LINUX RESTART` marker inside it is `reboot`, and
  the marker dates the END of the outage exactly.
* An interior gap with NO restart marker is `unexplained_gap`, not `down`.
  A suspended box and a stopped `sysstat-collect.timer` produce the identical
  hole, and this module has no way to tell them apart. Naming it `down`
  would be inventing the distinction.

Pure text-in / dict-out, like `nuc/perturbation.py`: it opens no socket and
runs no command, so it can be imported from any track and cannot reach the
NUC's port 8001.

Usage:
    python3 -m nuc.sysstat_archive witness    --capture state/.../sar.txt
    python3 -m nuc.sysstat_archive crosscheck --capture ... --bounds bounds.json
    python3 -m nuc.sysstat_archive steps      --capture ... [--min-step-kb N]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone

try:                                     # importable as a module AND runnable
    from nuc.perturbation import parse_sar, commit_steps, PerturbationError
except ImportError:                      # pragma: no cover - script entry point
    from perturbation import parse_sar, commit_steps, PerturbationError


class ArchiveError(ValueError):
    """Raised when a capture cannot be read without guessing."""


# `sysstat-collect.timer` on this box: OnCalendar=*:00/10, so 600 s.
# Round 400 measured 220 `Starting sysstat-collect.service` entries against an
# uptime of 1d12h43m = 132,180 s; 132,180/220 = 600.8 s/sample.
SAMPLE_INTERVAL_S = 600

# How much late a sample may be before the slot counts as missed. Observed
# stamps drift a few seconds per day (00:10:02 .. 00:10:21 across the nine
# files) and `sar -W` on sa31 shows a 04:00:03 bucket where 04:00:05 was due.
SAMPLE_SLACK_S = 180

_BANNER_DATE = re.compile(r"\b(\d{2})/(\d{2})/(\d{2,4})\b")
_RESTART = re.compile(r"^(\d{2}:\d{2}:\d{2})\s+LINUX RESTART")
_SECTION = re.compile(r"^###\s+(\S+)\s*$")


# --------------------------------------------------------------- parsing


@dataclass(frozen=True)
class DayArchive:
    """One `saNN` file: when it sampled, and when the kernel restarted."""
    date: str                      # YYYY-MM-DD
    samples: tuple                 # tuple[datetime], UTC, ascending
    restarts: tuple                # tuple[datetime], UTC, ascending
    n_rows: int

    @property
    def first(self):
        return self.samples[0] if self.samples else None

    @property
    def last(self):
        return self.samples[-1] if self.samples else None

    def as_dict(self) -> dict:
        return {
            "date": self.date,
            "n_samples": len(self.samples),
            "n_restarts": len(self.restarts),
            "first_utc": _iso(self.first),
            "last_utc": _iso(self.last),
            "restarts_utc": [_iso(r) for r in self.restarts],
        }


def banner_date(text: str) -> str:
    """The `MM/DD/YY` on sar's banner line, as `YYYY-MM-DD`.

    Taking the date from the file's own banner rather than from the caller is
    deliberate: a capture that concatenates nine days is exactly where an
    off-by-one-day argument would go unnoticed, and the wrong date silently
    turns a 22-hour outage into a 2-hour one."""
    for line in text.splitlines():
        if not line.startswith("Linux "):
            continue
        m = _BANNER_DATE.search(line)
        if not m:
            break
        mm, dd, yy = m.groups()
        year = int(yy) if len(yy) == 4 else 2000 + int(yy)
        return f"{year:04d}-{int(mm):02d}-{int(dd):02d}"
    raise ArchiveError("no `Linux ... MM/DD/YY` banner in this capture; "
                       "sar was run with a locale or format this parser "
                       "does not know, and guessing the date is how a "
                       "22-hour outage becomes a 2-hour one")


def parse_day(text: str, date: str | None = None) -> DayArchive:
    """One day's `sar` table -> its sample instants and restart markers.

    Row parsing is delegated to `perturbation.parse_sar`, which already
    handles the banner, repeated headers, `Average:` and 12-hour stamps, and
    which RAISES on a short row rather than mis-aligning columns. The restart
    markers are scraped separately because `parse_sar` drops them -- they are
    not buckets, but they are the only exact timestamps in the file."""
    date = date or banner_date(text)
    try:
        table = parse_sar(text)
    except PerturbationError as exc:
        raise ArchiveError(f"{date}: {exc}") from exc
    day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    samples = tuple(day + _hms(r.time) for r in table.rows)
    restarts = tuple(day + _hms(m.group(1))
                     for m in (_RESTART.match(l) for l in text.splitlines())
                     if m)
    if list(samples) != sorted(samples):
        raise ArchiveError(f"{date}: samples are not ascending; the capture "
                           "probably concatenates two files under one banner")
    return DayArchive(date=date, samples=samples, restarts=restarts,
                      n_rows=len(table.rows))


def split_capture(text: str, prefix: str = "SAR_R_") -> dict:
    """Split a `### SECTION`-delimited multi-day capture into {section: text}.

    The capture format is this program's own (`ssh box 'echo "### X"; sar ...'`),
    so the splitter lives here rather than in `parse_day`, which stays able to
    read a bare `sar` file from anywhere."""
    out, cur, buf = {}, None, []
    for line in text.splitlines():
        m = _SECTION.match(line)
        if m:
            if cur is not None:
                out[cur] = "\n".join(buf)
            cur, buf = m.group(1), []
            continue
        if cur is not None:
            buf.append(line)
    if cur is not None:
        out[cur] = "\n".join(buf)
    return {k: v for k, v in out.items() if k.startswith(prefix)}


def parse_capture(text: str, prefix: str = "SAR_R_") -> list:
    """Every day in a multi-day capture, ascending by date, deduplicated.

    Deduplication is by date, not by section name: a capture that contains both
    `SAR_R_SA30` and `SAR_W_SA30` describes ONE day twice, and counting it
    twice would double every gap statistic."""
    days = {}
    for name, body in split_capture(text, prefix).items():
        if not body.strip():
            continue
        d = parse_day(body)
        if d.date in days and len(d.samples) < len(days[d.date].samples):
            continue
        days[d.date] = d
    return [days[k] for k in sorted(days)]


# ------------------------------------------------------------- availability


@dataclass(frozen=True)
class Gap:
    """A hole in the sample series, and the strongest thing it supports."""
    kind: str                      # coverage_edge | reboot | unexplained_gap
    after_utc: str                 # last sample before the hole ("" at start edge)
    before_utc: str                # first sample after the hole ("" at end edge)
    gap_s: float
    missed_slots: int
    restarts_utc: tuple = ()
    down_start_earliest_utc: str = ""
    down_start_latest_utc: str = ""
    down_end_earliest_utc: str = ""
    down_end_latest_utc: str = ""
    note: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["restarts_utc"] = list(self.restarts_utc)
        d["gap_human"] = _dur(self.gap_s)
        return d


def availability(days: list, interval_s: int = SAMPLE_INTERVAL_S,
                 slack_s: int = SAMPLE_SLACK_S) -> dict:
    """Turn a list of `DayArchive` into a witness report.

    The contract, stated because every number below depends on it:

    * every sample instant is a POSITIVE witness that this kernel was running
      at that instant -- it is `sadc` writing to disk from inside the box;
    * consecutive samples no more than `interval_s + slack_s` apart leave no
      room for a boot, so the interval between them is witnessed UP;
    * a longer hole is a GAP. Its `kind` is `coverage_edge` if it touches the
      first or last day of the capture, `reboot` if a `LINUX RESTART` marker
      falls inside it, and `unexplained_gap` otherwise;
    * for a `reboot` gap the outage END is the restart marker EXACTLY, and the
      outage START is bracketed to one sample interval. That is a 10-minute
      start bracket and a to-the-second end -- better on both ends than an
      hourly ssh probe can do.

    A `reboot` gap with TWO restart markers is still one gap, and
    `down_start_*` then brackets only the FIRST outage; `restarts_utc` carries
    the rest. Reporting a single bracket for two outages would be a lie of
    aggregation, so the note says so."""
    if interval_s <= 0:
        raise ArchiveError("interval_s must be > 0")
    if not days:
        return {"n_days": 0, "n_samples": 0, "gaps": [], "coverage": None}

    stamps = [s for d in days for s in d.samples]
    if not stamps:
        raise ArchiveError("capture contains no sar samples at all")
    restarts = sorted({r for d in days for r in d.restarts})
    first, last = stamps[0], stamps[-1]

    gaps = []
    # Interior gaps between consecutive samples, across day boundaries.
    for a, b in zip(stamps, stamps[1:]):
        delta = (b - a).total_seconds()
        if delta <= interval_s + slack_s:
            continue
        inside = tuple(r for r in restarts if a < r < b)
        # round(), not floor: the real stamps drift a few seconds, so a
        # one-slot hole measures 1198 s as often as 1200 s and floor division
        # reported 0 missed slots for the former and 1 for the latter -- the
        # same event, two answers. Found by running this on nine real days.
        missed = max(0, int(round(delta / interval_s)) - 1)
        if inside:
            note = ""
            if len(inside) > 1:
                note = (f"{len(inside)} restart markers inside one gap: at "
                        "least that many outages; down_start_* brackets only "
                        "the first")
            gaps.append(Gap(
                kind="reboot", after_utc=_iso(a), before_utc=_iso(b),
                gap_s=delta, missed_slots=missed, restarts_utc=tuple(_iso(r) for r in inside),
                down_start_earliest_utc=_iso(a),
                down_start_latest_utc=_iso(a + timedelta(seconds=interval_s)),
                down_end_earliest_utc=_iso(inside[0]),
                down_end_latest_utc=_iso(inside[0]),
                note=note))
        elif _is_rollover(a, b, missed):
            gaps.append(Gap(
                kind="rollover", after_utc=_iso(a), before_utc=_iso(b),
                gap_s=delta, missed_slots=missed,
                note=("sysstat file rollover, NOT downtime: exactly one slot "
                      "missing across a UTC midnight. sadc's first write into "
                      "a new saNN file is consumed as the rate baseline and "
                      "never displayed by sar, so every day boundary loses "
                      "its 00:00 sample. Round 400 saw this at 7 of the 7 day "
                      "boundaries its capture could observe -- 7/7, which is "
                      "why it is a rule and not a coincidence.")))
        else:
            gaps.append(Gap(
                kind="unexplained_gap", after_utc=_iso(a), before_utc=_iso(b),
                gap_s=delta, missed_slots=missed,
                down_start_earliest_utc=_iso(a),
                down_start_latest_utc=_iso(a + timedelta(seconds=interval_s)),
                down_end_earliest_utc=_iso(b - timedelta(seconds=interval_s)),
                down_end_latest_utc=_iso(b),
                note=("no LINUX RESTART marker: a suspended box and a stopped "
                      "sysstat-collect.timer make the identical hole, so this "
                      "is NOT graded down")))

    # Restart markers at the coverage edges are retention, not downtime.
    edge = [r for r in restarts if r < first]
    if edge:
        gaps.insert(0, Gap(
            kind="coverage_edge", after_utc="", before_utc=_iso(first),
            gap_s=(first - edge[0]).total_seconds(), missed_slots=0,
            restarts_utc=tuple(_iso(r) for r in edge),
            note="restart before the first retained sample; the previous day "
                 "file has rotated away, so nothing is witnessed before it"))

    witnessed_s = (last - first).total_seconds() - sum(
        g.gap_s for g in gaps if g.kind != "coverage_edge")
    return {
        "n_days": len(days),
        "n_samples": len(stamps),
        "n_restarts": len(restarts),
        "restarts_utc": [_iso(r) for r in restarts],
        "coverage": {"from_utc": _iso(first), "to_utc": _iso(last),
                     "span_s": (last - first).total_seconds(),
                     "span_human": _dur((last - first).total_seconds()),
                     "interval_s": interval_s,
                     "days": [d.as_dict() for d in days]},
        "witnessed_up_s": witnessed_s,
        "witnessed_up_human": _dur(witnessed_s),
        "gaps": [g.as_dict() for g in gaps],
        "n_gaps": len(gaps),
        "n_reboot_gaps": sum(1 for g in gaps if g.kind == "reboot"),
        "n_rollover_gaps": sum(1 for g in gaps if g.kind == "rollover"),
        "n_unexplained_gaps": sum(1 for g in gaps if g.kind == "unexplained_gap"),
        "up_intervals": [{"from_utc": _iso(x), "to_utc": _iso(y),
                          "span_s": (y - x).total_seconds()}
                         for x, y in _up_intervals(stamps, gaps, interval_s,
                                                  slack_s)],
    }


def _is_rollover(a, b, missed_slots: int) -> bool:
    """One missing slot, no restart marker, and a UTC midnight inside the hole.

    All three conditions, deliberately. Dropping the midnight test would
    swallow a genuine one-sample outage anywhere in the day; dropping the
    one-slot test would swallow a real overnight outage that happens to
    straddle midnight, which is exactly when an unattended box goes down."""
    if missed_slots != 1:
        return False
    midnight = (b.replace(hour=0, minute=0, second=0, microsecond=0))
    return a < midnight <= b and a.date() != b.date()


def _up_intervals(stamps, gaps, interval_s, slack_s):
    """Maximal runs of samples with no interior gap of ANY kind but rollover.

    A rollover hole is not a loss of witness: the box demonstrably ran at
    23:50 and at 00:10 and sadc's own timer fired at 00:00 -- what is missing
    is the DISPLAY of that sample, not the sample. Treating it as a break in
    the witness would fragment every day and understate coverage by design."""
    breaks = {g.after_utc for g in gaps if g.kind not in ("rollover", "coverage_edge")}
    out, start, prev = [], None, None
    for s in stamps:
        if start is None:
            start, prev = s, s
            continue
        if _iso(prev) in breaks:
            out.append((start, prev))
            start = s
        prev = s
    if start is not None and prev is not None:
        out.append((start, prev))
    return out


def witness_probe_gaps(report: dict, probe_gaps: list) -> list:
    """Can the sar archive close a gap the ssh probe log never witnessed?

    `probe_gaps` is the per-gap detail from
    `reachability_check.py continuity --gaps` (each with `from_utc`,
    `to_utc`, `witnessed`, `unobserved_s`). For each one, intersect it with
    the sar archive's witnessed-up intervals.

    This is the point of the whole module. `continuity`'s
    `max_unobserved_outage_s` is an upper bound on an outage that could have
    hidden inside an unwitnessed gap -- 14h00m00s as of round 400, in the
    round 142 -> 154 window. If `sar` sampled that entire window every ten
    minutes with no hole, no outage hid there, and the bound is retired by
    observation rather than by assumption.

    `verdict`:
      `closed`   -- the sar archive covers the whole probe gap with witnessed
                    UP time. No outage of any length hid in it.
      `partial`  -- covered in part; `uncovered_s` is what remains unobserved.
      `open`     -- the archive does not reach this window at all (before its
                    retention, or inside one of its own gaps).
    """
    ups = [(_parse(u["from_utc"]), _parse(u["to_utc"]))
           for u in report.get("up_intervals", [])]
    out = []
    for g in probe_gaps:
        a, b = _parse(g.get("from_utc")), _parse(g.get("to_utc"))
        if a is None or b is None or b <= a:
            continue
        total = (b - a).total_seconds()
        covered = sum(max(0.0, (min(b, y) - max(a, x)).total_seconds())
                      for x, y in ups)
        covered = min(covered, total)
        verdict = ("closed" if total - covered < 1e-6
                   else "open" if covered < 1e-6 else "partial")
        out.append({
            "from_round": g.get("from_round"), "to_round": g.get("to_round"),
            "from_utc": g.get("from_utc"), "to_utc": g.get("to_utc"),
            "probe_witnessed": g.get("witnessed"),
            "probe_unobserved_s": g.get("unobserved_s"),
            "gap_s": total,
            "sar_covered_s": covered,
            "sar_uncovered_s": total - covered,
            "verdict": verdict,
        })
    return out


# --------------------------------------------------------------- crosscheck


def cross_check(report: dict, streaks: list,
                tolerance_s: float = 60.0) -> list:
    """Compare each sar gap against this track's own ssh-probe brackets.

    `streaks` is the `streaks` list from
    `reachability_check.py bounds --verdict down` -- passed as plain dicts, so
    this module keeps no import dependency on the 113 KB reachability module
    and stays pure.

    Verdicts, and what each one means for the probe log:

    `agrees`           -- the sar gap sits inside the probe's bracket. Two
                          independent instruments, one answer.
    `sar_tightens`     -- sar's positive witness is INSIDE the probe's
                          uncertainty, so the probe's bracket can be narrowed.
                          This is the useful case and it is why the module
                          exists.
    `conflict`         -- sar witnessed the box UP at an instant the probe log
                          places inside a confirmed outage, or vice versa. One
                          of the two instruments is wrong and the finding is
                          the disagreement, not a merged number.
    `unknown_to_log`   -- sar sees a gap no probe streak overlaps. The probe
                          log simply was not looking; nothing is wrong, but a
                          claim like "the longest outage we have seen" has to
                          clear these too.
    """
    out = []
    for g in report.get("gaps", []):
        if g["kind"] == "coverage_edge":
            continue
        g_start = _parse(g["after_utc"])
        g_end = _parse(g["before_utc"])
        match = None
        for s in streaks:
            s_start = _parse(s.get("earliest_possible_start_utc")
                             or s.get("first_check_utc"))
            s_end = _parse(s.get("latest_possible_end_utc")
                           or s.get("last_check_utc"))
            if s_start is None or s_end is None:
                continue
            if g_start < s_end and s_start < g_end:      # any overlap
                match = (s, s_start, s_end)
                break
        if match is None:
            out.append({"gap": g, "verdict": "unknown_to_log", "streak": None,
                        "detail": "no down-streak in the probe log overlaps "
                                  "this gap"})
            continue
        s, s_start, s_end = match
        notes, verdict = [], "agrees"
        # sar witnessed UP at g_start; the probe log must not claim down then.
        if s_start < g_start:
            delta = (g_start - s_start).total_seconds()
            if delta > tolerance_s:
                verdict = "sar_tightens"
            notes.append(
                f"sar witnessed the kernel running at {g['after_utc']}, "
                f"{delta:.1f}s after the log's earliest possible start "
                f"({s.get('earliest_possible_start_utc')}); the start bracket "
                f"can be moved forward by that much")
        if g["kind"] == "reboot" and s.get("latest_possible_end_utc"):
            e_log = _parse(s["latest_possible_end_utc"])
            e_sar = _parse(g["down_end_earliest_utc"])
            d = abs((e_sar - e_log).total_seconds())
            notes.append(
                f"sar LINUX RESTART {g['down_end_earliest_utc']} vs log "
                f"boot_utc {s['latest_possible_end_utc']}: {d:.1f}s apart")
            if d > tolerance_s:
                verdict = "conflict"
        out.append({"gap": g, "verdict": verdict,
                    "streak": {"start_round": s.get("start_round"),
                               "end_round": s.get("end_round"),
                               "earliest_possible_start_utc":
                                   s.get("earliest_possible_start_utc"),
                               "latest_possible_end_utc":
                                   s.get("latest_possible_end_utc")},
                    "detail": "; ".join(notes) or "brackets coincide"})
    return out


# ------------------------------------------------------------ memory history


def multiday_steps(days_text: dict, min_step_kb: float = 500_000,
                   persist_buckets: int = 2) -> list:
    """Every large `kbcommit` step across a multi-day capture.

    `min_step_kb` defaults to 500 MB rather than `commit_steps`'s 50 MB: at
    this scale the question is "when did a multi-gigabyte allocation happen",
    and 50 MB over nine days returns hundreds of housekeeping blips.

    Both directions are reported. `commit_steps` finds only RISES, which is
    right for its question (a rise that persists is a heap that grew); here a
    30 GB FALL is the single most informative event in the file, because it is
    the engine's address space disappearing -- i.e. a restart, and therefore an
    expert cache reset to zero slots."""
    out = []
    for name, body in sorted(days_text.items()):
        if not body.strip():
            continue
        day = parse_day(body)
        table = parse_sar(body)
        if "kbcommit" not in table.columns:
            continue
        vals = table.column("kbcommit")
        for i in range(1, len(vals)):
            delta = vals[i] - vals[i - 1]
            if abs(delta) < min_step_kb:
                continue
            at = day.samples[i]
            near_restart = any(abs((at - r).total_seconds()) <= 2 * SAMPLE_INTERVAL_S
                               for r in day.restarts)
            out.append({
                "at_utc": _iso(at),
                "date": day.date,
                "bucket": table.rows[i].time,
                "delta_kb": delta,
                "delta_gib": delta / (1 << 20),
                "before_kb": vals[i - 1],
                "after_kb": vals[i],
                "direction": "alloc" if delta > 0 else "release",
                "near_restart": near_restart,
            })
    out.sort(key=lambda d: d["at_utc"])
    # Group consecutive allocs into load episodes: an engine start is one
    # multi-gigabyte step followed by smaller ones in adjacent buckets.
    for i, s in enumerate(out):
        prev = out[i - 1] if i else None
        s["starts_episode"] = (
            s["direction"] == "alloc"
            and (prev is None or prev["direction"] == "release"
                 or (_parse(s["at_utc"]) - _parse(prev["at_utc"])).total_seconds()
                 > 2 * SAMPLE_INTERVAL_S))
    return out


def load_episodes(steps: list) -> list:
    """Consecutive alloc steps grouped into one 'the engine came up' episode.

    Each episode's FIRST step is dominated by the model's resident weights and
    is not a per-request figure; the steps after it are what round 376 asked
    for -- per-request expert-cache growth, measured with no request sent."""
    eps, cur = [], None
    for s in steps:
        if s["direction"] == "release":
            if cur:
                eps.append(cur)
                cur = None
            continue
        if s["starts_episode"]:
            if cur:
                eps.append(cur)
            cur = {"start_utc": s["at_utc"], "date": s["date"], "steps": []}
        if cur is None:
            cur = {"start_utc": s["at_utc"], "date": s["date"], "steps": []}
        cur["steps"].append(s)
    if cur:
        eps.append(cur)
    for e in eps:
        e["n_steps"] = len(e["steps"])
        e["total_gib"] = sum(s["delta_gib"] for s in e["steps"])
        e["end_utc"] = e["steps"][-1]["at_utc"]
        tail = [s["delta_gib"] for s in e["steps"][1:]]
        e["post_load_steps_gib"] = tail
        e["decay_ratios"] = [round(b / a, 4) for a, b in zip(tail, tail[1:])
                             if a > 0]
    return eps


# ------------------------------------------------------------------ helpers


def _hms(hms: str) -> timedelta:
    h, m, s = (int(p) for p in hms.split(":"))
    return timedelta(hours=h, minutes=m, seconds=s)


def _iso(dt) -> str:
    return "" if dt is None else dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except ValueError:
        return None


def _dur(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(abs(seconds), 3600)
    m, s = divmod(rem, 60)
    sign = "-" if seconds < 0 else ""
    return f"{sign}{h}h{m:02d}m{s:02d}s"


def _load(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="mode", required=True)

    w = sub.add_parser("witness", help="uptime/gaps from the box's sar archive")
    w.add_argument("--capture", required=True)
    w.add_argument("--prefix", default="SAR_R_")
    w.add_argument("--interval-s", type=int, default=SAMPLE_INTERVAL_S)
    w.add_argument("--gaps-only", action="store_true")

    c = sub.add_parser("crosscheck",
                       help="sar gaps vs `reachability_check.py bounds` output")
    c.add_argument("--capture", required=True)
    c.add_argument("--bounds", required=True,
                   help="JSON from `reachability_check.py bounds --verdict down`")
    c.add_argument("--prefix", default="SAR_R_")

    s = sub.add_parser("steps", help="multi-GB Committed_AS steps, all days")
    s.add_argument("--capture", required=True)
    s.add_argument("--prefix", default="SAR_R_")
    s.add_argument("--min-step-kb", type=float, default=500_000)
    s.add_argument("--episodes", action="store_true")

    args = p.parse_args(argv)
    text = _load(args.capture)
    if args.mode == "witness":
        rep = availability(parse_capture(text, args.prefix),
                           interval_s=args.interval_s)
        if args.gaps_only:
            rep = {"gaps": rep["gaps"], "n_gaps": rep["n_gaps"]}
        print(json.dumps(rep, indent=2))
    elif args.mode == "crosscheck":
        bounds = json.loads(_load(args.bounds))
        streaks = bounds.get("streaks", bounds) if isinstance(bounds, dict) else bounds
        rep = availability(parse_capture(text, args.prefix))
        print(json.dumps(cross_check(rep, streaks), indent=2))
    elif args.mode == "steps":
        steps = multiday_steps(split_capture(text, args.prefix),
                               min_step_kb=args.min_step_kb)
        print(json.dumps(load_episodes(steps) if args.episodes else steps,
                         indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
