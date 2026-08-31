#!/usr/bin/env python3
"""Attribute memory perturbations on pgain-nuc to named housekeeping runs.

Round 394 (NUC-integration E). Round 388 handed forward two items that turn out
to be the same item:

  * item 2 -- "the 01:50-02:00 bucket is unexplained: 67.7 MB swapped out,
    +147 MB `Committed_AS` that persisted, ~4 CPU-seconds, zero journald
    entries";
  * item 7 -- "`apt` is a first-class perturbation source on this box. Any
    future A/B must record whether a housekeeping timer fired inside the
    measurement window."

Round 388 read `sar -W` (swap) and `sar -B` (paging). Both events are visible
there. Only ONE of them is *explicable* there, and that is why the other was
recorded as a mystery:

    channel        instrument              signature
    -------------  ----------------------  ------------------------------------
    page cache     `sar -B` pgpgin/s       a surge of reads pulls the engine's
                   `sar -r` kbcached       anon pages out to swap. apt-daily,
                                           2026-08-31T03:50Z, 218 MB.
    commitment     `sar -r` kbcommit       a process's heap balloons, forcing
                                           reclaim, then is released with
                                           MADV_DONTNEED -- so RSS falls back,
                                           `kbcached` falls, and the only
                                           lasting trace is a STEP in
                                           Committed_AS. fwupd-refresh,
                                           2026-08-31T01:57Z, 67.7 MB.

`sar -r` is the missing instrument, it has sampled every 10 minutes since the
box booted, and nothing in this track had ever read it.

The module is pure text-in / dict-out: it parses sysstat tables and
`systemctl list-timers` / `systemctl cat` output that a caller has already
captured over ssh. It opens no socket and runs no command, so it is safe to
import from any track and there is no path by which it can contact port 8001.

CLI
    python3 nuc/perturbation.py steps    --sar-r FILE   # persistent commit steps
    python3 nuc/perturbation.py swap     --sar-w FILE   # swap-out excursions
    python3 nuc/perturbation.py channels --sar-r FILE --sar-w FILE --sar-b FILE
    python3 nuc/perturbation.py guard    --window-s 1800 [--timers FILE]
    python3 nuc/perturbation.py timers                  # the shipped NUC table
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from typing import Iterable, Sequence

# --------------------------------------------------------------- units

# The x86-64 base page, which `sar -W` counts in. NOT redeclared here: round
# 388 recorded `swap_analysis.DEFAULT_PAGE_BYTES` as one of the four constants
# that are legitimately bare, and `nuc/constant_audit.py` flagged this module's
# first draft for restating it. Two modules holding one constant is the shape
# rounds 382 and 388 each spent a round finding after the fact; here the audit
# caught it at authoring time, which is what the audit is for.
#
# The import is tried both ways because this file has TWO supported entry
# points -- `python3 -m nuc.perturbation` (package on sys.path) and
# `python3 nuc/perturbation.py` (script, `nuc` not importable). The first draft
# imported only the package form and broke the script form instantly; both are
# covered by tests now, because the module docstring documents both.
try:                                                        # noqa: E402
    from nuc.swap_analysis import DEFAULT_PAGE_BYTES as PAGE_BYTES
except ModuleNotFoundError:                                 # direct-script run
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from swap_analysis import DEFAULT_PAGE_BYTES as PAGE_BYTES

KB = 1024
SAR_INTERVAL_S = 600               # sysstat-collect.timer on this box, 10 min

# --------------------------------------------------------------- errors


class PerturbationError(ValueError):
    pass


# --------------------------------------------------------------- sar parsing

_BANNER = re.compile(r"^Linux\s")
_RESTART = re.compile(r"LINUX RESTART")
_TIME = re.compile(r"^(\d{2}:\d{2}:\d{2})(\s+(AM|PM))?$")


@dataclass(frozen=True)
class SarRow:
    """One sysstat bucket: its END timestamp plus the named columns."""
    time: str
    values: dict

    def get(self, column: str) -> float:
        if column not in self.values:
            raise PerturbationError(
                f"column {column!r} not in this row; have {sorted(self.values)}")
        return self.values[column]


@dataclass(frozen=True)
class SarTable:
    columns: tuple
    rows: tuple

    def column(self, name: str) -> list:
        return [r.get(name) for r in self.rows]

    def at(self, time: str) -> SarRow:
        for r in self.rows:
            if r.time == time:
                return r
        raise PerturbationError(f"no bucket at {time!r}")


def parse_sar(text: str) -> SarTable:
    """Parse one `sar -X -f saNN` table into named columns.

    Handles, because the real output contains all of them: the `Linux ...`
    banner, blank lines, the `LINUX RESTART` marker sysstat writes at boot, the
    trailing `Average:` row (dropped -- it is not a bucket), a repeated header
    row when sar re-prints it, and both 24-hour and `HH:MM:SS AM/PM` stamps.

    A `sar -n DEV`-style table with a leading label column is NOT supported;
    those need a per-interface split the caller should do first. We raise
    rather than silently mis-align, because a silently mis-aligned column is
    exactly how round 388's mystery would have been mis-attributed."""
    columns: tuple = ()
    rows: list = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or _BANNER.match(line) or _RESTART.search(line):
            continue
        parts = line.split()
        stamp = _TIME.match(parts[0])
        if not stamp:
            if parts[0] == "Average:":
                continue
            continue
        # `HH:MM:SS AM` -> the meridiem is its own token; drop it.
        body = parts[1:]
        if body and body[0] in ("AM", "PM"):
            body = body[1:]
        if not body:
            continue
        if _looks_like_header(body):
            if columns and tuple(body) != columns:
                raise PerturbationError(
                    f"header changed mid-table: {columns} -> {tuple(body)}")
            columns = tuple(body)
            continue
        if not columns:
            raise PerturbationError("data row before any header row")
        if len(body) != len(columns):
            raise PerturbationError(
                f"row at {parts[0]} has {len(body)} fields, header has "
                f"{len(columns)}: {body}")
        rows.append(SarRow(time=parts[0],
                           values={c: float(v) for c, v in zip(columns, body)}))
    if not columns:
        raise PerturbationError("no header row found; is this sar output?")
    return SarTable(columns=columns, rows=tuple(rows))


def _looks_like_header(body: Sequence[str]) -> bool:
    for tok in body:
        try:
            float(tok)
        except ValueError:
            return True
    return False


# ------------------------------------------------------- the two channels


@dataclass(frozen=True)
class CommitStep:
    """A step in Committed_AS: the commitment channel's only lasting trace."""
    time: str
    delta_kb: float
    before_kb: float
    after_kb: float
    persistent: bool
    persisted_buckets: int

    def as_dict(self) -> dict:
        d = asdict(self)
        d["delta_bytes"] = int(self.delta_kb * KB)
        return d


def commit_steps(table: SarTable, min_step_kb: float = 50_000,
                 persist_buckets: int = 3,
                 column: str = "kbcommit") -> list:
    """Find rises in `kbcommit` and say which ones PERSIST.

    The distinction is the whole point. On this box a short-lived process --
    every ssh session this program opens, `sysstat-collect`, `debian-sa1` --
    produces a few-MB rise that is gone by the next bucket. What round 388
    could not explain was a rise that never came back, and a rise that never
    comes back means a still-live process grew its heap and kept the mapping
    even after freeing the contents (glibc trims with MADV_DONTNEED: RSS falls,
    the commitment does not).

    `persistent` = the next `persist_buckets` samples all stay at least
    `min_step_kb/2` above the pre-step level. Half, not all of it, because a
    real step is usually followed by small drift in both directions.

    Raises if `persist_buckets < 1`: a step with no lookahead cannot be graded,
    and returning `persistent=True` by default would launder the ssh blips this
    function exists to reject."""
    if persist_buckets < 1:
        raise PerturbationError("persist_buckets must be >= 1")
    if min_step_kb <= 0:
        raise PerturbationError("min_step_kb must be > 0")
    vals = table.column(column)
    out = []
    for i in range(1, len(vals)):
        delta = vals[i] - vals[i - 1]
        if delta < min_step_kb:
            continue
        tail = vals[i + 1:i + 1 + persist_buckets]
        floor = vals[i - 1] + min_step_kb / 2
        persistent = len(tail) == persist_buckets and all(v >= floor for v in tail)
        out.append(CommitStep(time=table.rows[i].time, delta_kb=delta,
                              before_kb=vals[i - 1], after_kb=vals[i],
                              persistent=persistent,
                              persisted_buckets=sum(1 for v in tail if v >= floor)))
    return out


@dataclass(frozen=True)
class SwapExcursion:
    time: str
    pswpout_s: float
    pages: int
    bytes: int

    def as_dict(self) -> dict:
        return asdict(self)


def swap_excursions(table: SarTable, interval_s: int = SAR_INTERVAL_S,
                    page_bytes: int = PAGE_BYTES,
                    min_pages: int = 1) -> list:
    """Every bucket with a non-zero `pswpout/s`, converted to bytes.

    `sar -W` reports a RATE over the bucket, so bytes = rate * interval *
    page_bytes. The interval is a property of `sysstat-collect.timer`, not of
    the file -- pass it explicitly if the collection period ever changes,
    because getting it wrong scales every figure this module reports."""
    if interval_s <= 0:
        raise PerturbationError("interval_s must be > 0")
    out = []
    for row in table.rows:
        rate = row.get("pswpout/s")
        pages = round(rate * interval_s)
        if pages < min_pages:
            continue
        out.append(SwapExcursion(time=row.time, pswpout_s=rate, pages=pages,
                                 bytes=pages * page_bytes))
    return out


def classify_bucket(pgpgin_s: float, pgpgin_baseline_s: float,
                    commit_delta_kb: float, swapped_bytes: int,
                    surge_factor: float = 10.0,
                    min_step_kb: float = 50_000,
                    min_pgpgin_s: float = 50.0) -> str:
    """Name the channel a perturbation arrived through.

    `page_cache`  -- reads surged, commitment did not move. apt-daily.
    `commitment`  -- commitment stepped, reads did not surge. fwupd-refresh.
    `both`        -- both.
    `unattributed`-- pages left for swap and NEITHER channel shows anything.
                     Round 388's state for the 02:00 bucket, reachable only
                     because it lacked `sar -r`; kept as a distinct verdict so
                     a future gap is named rather than forced into a channel.
    `quiet`       -- nothing happened.

    A surge needs BOTH a ratio and an absolute floor, and the floor is the part
    that is easy to leave out. This box idles at `pgpgin/s` 0.00-0.20, so the
    ratio test alone fires on anything at all: the 02:00 bucket read 4.17 KB/s
    -- 2.5 MB, a firmware metadata download -- which is 41x a 0.1 baseline and
    would be graded a page-cache surge next to apt's 333 MB. `min_pgpgin_s`
    defaults to 50 KB/s (30 MB per 10-minute bucket), the same order as
    `min_step_kb`, so the two channels are held to comparable evidence. The
    first version of this function had the ratio and a 1.0 KB/s floor, and its
    own test on the real capture is what caught it."""
    if surge_factor <= 1:
        raise PerturbationError("surge_factor must be > 1")
    if min_pgpgin_s <= 0:
        raise PerturbationError("min_pgpgin_s must be > 0")
    cache = (pgpgin_s >= pgpgin_baseline_s * surge_factor
             and pgpgin_s >= min_pgpgin_s)
    commit = commit_delta_kb >= min_step_kb
    if cache and commit:
        return "both"
    if cache:
        return "page_cache"
    if commit:
        return "commitment"
    if swapped_bytes > 0:
        return "unattributed"
    return "quiet"


# ------------------------------------------------------------- timer windows


@dataclass(frozen=True)
class Timer:
    """A systemd timer, reduced to what decides whether you can schedule around it."""
    unit: str
    period_s: int                 # shortest interval between consecutive fires
    randomized_delay_s: int = 0   # RandomizedDelaySec
    note: str = ""

    def __post_init__(self):
        if self.period_s <= 0:
            raise PerturbationError(f"{self.unit}: period_s must be > 0")
        if self.randomized_delay_s < 0:
            raise PerturbationError(f"{self.unit}: randomized_delay_s must be >= 0")

    @property
    def avoidable(self) -> bool:
        """False when the randomization covers the whole period.

        `fwupd-refresh.timer` is `OnCalendar=*-*-* *:00:00` with
        `RandomizedDelaySec=1h`: the delay equals the period, so the fire time
        is uniform over every hour and there is no quiet slot to aim at.
        `apt-daily.timer` is worse -- `6,18:00` with `RandomizedDelaySec=12h`,
        i.e. uniform over the entire day. Round 388's handoff said to RECORD
        whether a timer fired in the window. This property is why that is the
        only available move: you cannot SCHEDULE around either of them."""
        return self.randomized_delay_s < self.period_s

    def p_fire_in_window(self, window_s: float) -> float:
        """Probability at least one fire lands in an arbitrary window.

        Uniform-fire approximation, exact for a randomization that spans the
        period and conservative otherwise. Capped at 1.0 -- a window longer
        than the period always contains a fire."""
        if window_s < 0:
            raise PerturbationError("window_s must be >= 0")
        return min(1.0, window_s / self.period_s)


# Measured on pgain-nuc, 2026-08-31T09:1xZ, from `systemctl cat` + the observed
# fire history in this boot's journal. `period_s` is the OnCalendar period;
# `randomized_delay_s` is the unit's own RandomizedDelaySec.
NUC_TIMERS = (
    Timer("fwupd-refresh.timer", period_s=3600, randomized_delay_s=3600,
          note="OnCalendar=*-*-* *:00:00; fired 34x this boot, downloaded 26x, "
               "stepped Committed_AS once (+147 MB, 2026-08-31T01:57Z)"),
    Timer("apt-daily.timer", period_s=12 * 3600, randomized_delay_s=12 * 3600,
          note="OnCalendar=*-*-* 6,18:00; 2026-08-31T03:50Z cost the engine "
               "218 MB of resident weights, the largest perturbation of the boot"),
    Timer("apt-daily-upgrade.timer", period_s=24 * 3600,
          randomized_delay_s=3600,
          note="OnCalendar=*-*-* 6:00; fired 2026-08-31T06:20:33Z and cost "
               "ZERO swap -- round 394's control arm"),
    Timer("motd-news.timer", period_s=12 * 3600, randomized_delay_s=12 * 3600,
          note="fired 2026-08-31T05:10:05Z, zero swap"),
    Timer("sysstat-collect.timer", period_s=600, randomized_delay_s=0,
          note="the instrument itself; deterministic, ~0 cost"),
    Timer("logrotate.timer", period_s=24 * 3600, randomized_delay_s=3600),
    Timer("man-db.timer", period_s=24 * 3600, randomized_delay_s=12 * 3600),
    Timer("fstrim.timer", period_s=7 * 24 * 3600, randomized_delay_s=6000),
    Timer("e2scrub_all.timer", period_s=7 * 24 * 3600, randomized_delay_s=3600),
    Timer("dpkg-db-backup.timer", period_s=24 * 3600, randomized_delay_s=3600),
    Timer("update-notifier-download.timer", period_s=24 * 3600,
          randomized_delay_s=3600),
    Timer("systemd-tmpfiles-clean.timer", period_s=24 * 3600,
          randomized_delay_s=0),
)


def window_guard(window_s: float, timers: Iterable = NUC_TIMERS) -> dict:
    """Can this measurement window be scheduled clean? On this box: no.

    Returns the per-timer fire probability, the subset that cannot be avoided
    by choosing a start time, and a verdict. The verdict is deliberately never
    `clean` while any unavoidable timer exists, because "I picked a quiet hour"
    is exactly the reasoning that would have reported rounds 370/376/382's
    identical readings as an A/B result."""
    timers = list(timers)
    rows = []
    for t in timers:
        rows.append({"unit": t.unit, "period_s": t.period_s,
                     "randomized_delay_s": t.randomized_delay_s,
                     "avoidable": t.avoidable,
                     "p_fire_in_window": round(t.p_fire_in_window(window_s), 6),
                     "note": t.note})
    unavoidable = [r for r in rows if not r["avoidable"]]
    expected = sum(r["p_fire_in_window"] for r in rows)
    return {
        "window_s": window_s,
        "timers": rows,
        "unavoidable_units": [r["unit"] for r in unavoidable],
        "expected_fires_in_window": round(expected, 4),
        "verdict": "contaminated_by_construction" if unavoidable else "schedulable",
        "required_practice": (
            "record the fire history for the window and reject contaminated "
            "arms post hoc; scheduling around these timers is not possible"),
    }


# ------------------------------------------------------- journal attribution


@dataclass(frozen=True)
class Event:
    """A named thing that happened, from the journal or a filesystem mtime."""
    at_utc: str
    label: str
    source: str = "journal"


def attribute(excursions: Iterable, events: Iterable,
              interval_s: int = SAR_INTERVAL_S, date: str = "") -> list:
    """Put each named event into the sar bucket it falls in.

    Buckets are labelled by their END time, so an event at 01:57:33 belongs to
    the bucket ending 02:00:05 -- an off-by-one that is easy to make and that
    would have moved fwupd out of the window it caused."""
    ev = [e for e in events]
    out = []
    for x in excursions:
        end = _hms_to_s(x.time)
        start = end - interval_s
        inside = [e for e in ev
                  if start < _hms_to_s(e.at_utc.split("T")[-1][:8]) <= end
                  and (not date or e.at_utc.startswith(date))]
        out.append({"bucket_end": x.time,
                    "bucket_start_s": start,
                    "bytes": getattr(x, "bytes", None),
                    "delta_kb": getattr(x, "delta_kb", None),
                    "events": [{"at_utc": e.at_utc, "label": e.label,
                                "source": e.source} for e in inside],
                    "attributed": bool(inside)})
    return out


@dataclass(frozen=True)
class LedgerEntry:
    """One named housekeeping fire, and what the bucket it fell in cost."""
    at_utc: str
    unit: str
    bucket_end: str
    pswpout_s: float
    bucket_swapped_bytes: int
    bucket_shared_by: int
    costly: bool
    sole_attributable: bool

    def as_dict(self) -> dict:
        return asdict(self)


# A bucket has to move by more than sampling noise before a fire in it is
# called costly, and the floor is DERIVED from the boot's own two extremes
# rather than picked. `sar -W` gave exactly one sub-megabyte non-zero bucket
# (0.14 pswpout/s, three fires shared it, and none of them plausibly swapped a
# third of a megabyte of a 30 GB engine) and one smallest real event (27.54
# pswpout/s, the 67.7 MB fwupd step round 394 attributed). The floor is their
# GEOMETRIC MEAN: the value furthest, in log space, from both the largest
# thing that must be rejected and the smallest thing that must be kept. Its
# margin is 14.0x in each direction, so the grading does not turn on a
# judgement call about either endpoint.
LEDGER_NOISE_BUCKET_RATE = 0.14          # sar -W sa31, the 00:40:05 bucket
LEDGER_SMALLEST_REAL_RATE = 27.54        # sar -W sa31, the 02:00:05 bucket
LEDGER_NOISE_BUCKET_BYTES = round(LEDGER_NOISE_BUCKET_RATE
                                  * SAR_INTERVAL_S) * PAGE_BYTES
LEDGER_SMALLEST_REAL_EVENT_BYTES = round(LEDGER_SMALLEST_REAL_RATE
                                         * SAR_INTERVAL_S) * PAGE_BYTES
LEDGER_MIN_BYTES = int((LEDGER_NOISE_BUCKET_BYTES
                        * LEDGER_SMALLEST_REAL_EVENT_BYTES) ** 0.5)

# `sysstat-collect` is what WRITES the bucket. It is present in every costly
# bucket by construction, so including it makes the base rate a statement
# about the instrument rather than about the box. Excluded by default and
# named here so the exclusion is a documented decision, not a silent filter.
LEDGER_EXCLUDE_UNITS = ("sysstat-collect",)

# A sample taken at instant T summarises (T-interval, T]. A unit that STARTS
# at T has done nothing yet at T, so its cost belongs to the next bucket.
# This is not a corner case on this box: `sysstat-collect.timer` and every
# `OnCalendar=*-*-* HH:MM:SS` housekeeping timer fire on the same :00:0x
# cadence, so a fire and the sample that closes its bucket are routinely
# within seconds. Without the slack, `apt-daily` at 03:50:05 was credited to
# the 03:50:05 bucket -- zero pages -- while the 218 MB it caused landed in
# 04:00:03 and got attributed to `packagekit` instead. 5 s covers the observed
# spread (fires at :05, samples at :03..:21) without reaching a real 10-minute
# bucket boundary.
LEDGER_BOUNDARY_SLACK_S = 5


def cost_ledger(fires: Iterable, swap_table: SarTable, date: str,
                interval_s: int = SAR_INTERVAL_S,
                page_bytes: int = PAGE_BYTES,
                min_bytes: int = LEDGER_MIN_BYTES,
                exclude_units: Iterable = LEDGER_EXCLUDE_UNITS,
                boundary_slack_s: int = LEDGER_BOUNDARY_SLACK_S) -> dict:
    """Join every named unit start to the `sar -W` bucket it fell in.

    Round 394 asked whether the identity of a housekeeping timer predicts what
    it costs the engine. It had one case (`fwupd-refresh` at 01:57, 67.7 MB)
    and three controls, and concluded "attribute to the bucket that MOVED; let
    the unit name be corroboration". This function is that conclusion turned
    into a measurement over every fire in a boot.

    Unlike `attribute`, which starts from the excursions and asks which events
    are in them, this starts from the FIRES and asks what each one cost --
    including the many fires whose bucket is zero. That inversion is the whole
    point: a base rate needs a denominator, and the denominator is the quiet
    fires nobody writes down.

    THREE THINGS IT REFUSES TO DO, each because the first draft did it and the
    real capture caught it:

    * It does not divide a shared bucket's cost among the fires in it.
      `bucket_swapped_bytes` is a property of the BUCKET; when three units fire
      into one bucket all three carry the same figure and `bucket_shared_by` is
      3. `sole_attributable` is the only flag that licenses "unit X cost this",
      and `total_swapped_bytes` sums DISTINCT BUCKETS. Summing per-fire bytes
      gave 799 MB for a day whose real total is 289 MB.
    * It does not count the instrument. See `LEDGER_EXCLUDE_UNITS`.
    * It does not call a 344 kB bucket costly. See `LEDGER_MIN_BYTES`.

    `unclassified` holds fires with no covering bucket -- the boot's first
    partial bucket, or a fire on a day this table does not cover. They are
    reported separately rather than counted as free, because a fire whose cost
    is unknown is not a fire that cost nothing.
    """
    if interval_s <= 0:
        raise PerturbationError("interval_s must be > 0")
    if min_bytes < 0:
        raise PerturbationError("min_bytes must be >= 0")
    excluded = set(exclude_units or ())
    ends = [(r.time, _hms_to_s(r.time), r.get("pswpout/s"))
            for r in swap_table.rows]
    bucket_bytes = {name: round(rate * interval_s) * page_bytes
                    for name, _end, rate in ends}

    placed, unclassified, skipped = [], [], 0
    for f in fires:
        at, unit = (f.at_utc, f.label) if hasattr(f, "at_utc") else (f[0], f[1])
        if date and not at.startswith(date):
            continue
        if unit in excluded:
            skipped += 1
            continue
        t = _hms_to_s(at.split("T")[-1][:8]) + boundary_slack_s
        hit = next(((name, rate) for name, end, rate in ends
                    if end - interval_s < t <= end), None)
        if hit is None:
            unclassified.append({"at_utc": at, "unit": unit,
                                 "why": "no sar bucket covers this instant"})
            continue
        placed.append((at, unit, hit[0], hit[1]))

    share = {}
    for _at, _unit, name, _rate in placed:
        share[name] = share.get(name, 0) + 1

    entries = []
    for at, unit, name, rate in placed:
        b = bucket_bytes[name]
        costly = b >= min_bytes
        entries.append(LedgerEntry(
            at_utc=at, unit=unit, bucket_end=name, pswpout_s=rate,
            bucket_swapped_bytes=b, bucket_shared_by=share[name],
            costly=costly, sole_attributable=costly and share[name] == 1))

    by_unit = {}
    for e in entries:
        u = by_unit.setdefault(e.unit, {"fires": 0, "in_costly_bucket": 0,
                                        "sole_attributable": 0,
                                        "sole_attributable_bytes": 0})
        u["fires"] += 1
        u["in_costly_bucket"] += int(e.costly)
        u["sole_attributable"] += int(e.sole_attributable)
        u["sole_attributable_bytes"] += e.bucket_swapped_bytes if e.sole_attributable else 0

    costly_buckets = sorted({e.bucket_end for e in entries if e.costly})
    all_costly = sorted(n for n, b in bucket_bytes.items() if b >= min_bytes)
    return {
        "date": date,
        "n_fires": len(entries),
        "n_excluded_fires": skipped,
        "excluded_units": sorted(excluded),
        "min_bytes": min_bytes,
        "boundary_slack_s": boundary_slack_s,
        "n_fires_in_costly_bucket": sum(1 for e in entries if e.costly),
        "n_sole_attributable": sum(1 for e in entries if e.sole_attributable),
        "n_unclassified": len(unclassified),
        "base_rate": (None if not entries
                      else sum(1 for e in entries if e.costly) / len(entries)),
        "n_buckets": len(ends),
        "n_costly_buckets": len(all_costly),
        "n_costly_buckets_with_a_named_fire": len(costly_buckets),
        "costly_buckets_without_a_named_fire":
            [n for n in all_costly if n not in set(costly_buckets)],
        "total_swapped_bytes": sum(bucket_bytes[n] for n in all_costly),
        "by_unit": by_unit,
        "entries": [e.as_dict() for e in entries],
        "unclassified": unclassified,
    }


def parse_unit_starts(text: str) -> list:
    """`journalctl -o short-iso` lines -> `Event(at_utc, unit)`.

    Matches only `systemd[1]: Starting <unit>.service`, i.e. PID 1 starting a
    system unit. The narrower match is deliberate: `Started` fires for the same
    unit and would double every count, and a user-manager line
    (`systemd[1057]:`) is not a housekeeping timer."""
    pat = re.compile(
        r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:[+-]\d{2}:\d{2}|Z)?\s+"
        r"\S+\s+systemd\[1\]:\s+Starting\s+(\S+?)\.service")
    out = []
    for line in text.splitlines():
        m = pat.match(line)
        if m:
            out.append(Event(at_utc=m.group(1) + "Z", label=m.group(2)))
    return out


def _hms_to_s(hms: str) -> int:
    h, m, s = (int(p) for p in hms.split(":"))
    return h * 3600 + m * 60 + s


# ------------------------------------------------------------------- CLI


def _load(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="mode", required=True)

    sp = sub.add_parser("steps", help="persistent Committed_AS steps (sar -r)")
    sp.add_argument("--sar-r", required=True)
    sp.add_argument("--min-step-kb", type=float, default=50_000)
    sp.add_argument("--persist-buckets", type=int, default=3)

    sw = sub.add_parser("swap", help="swap-out excursions (sar -W)")
    sw.add_argument("--sar-w", required=True)
    sw.add_argument("--interval-s", type=int, default=SAR_INTERVAL_S)

    sg = sub.add_parser("guard", help="can a window of this length be scheduled clean")
    sg.add_argument("--window-s", type=float, required=True)

    sub.add_parser("timers", help="the measured NUC timer table")

    sl = sub.add_parser("ledger",
                        help="round 400: what every housekeeping fire cost")
    sl.add_argument("--sar-w", required=True)
    sl.add_argument("--journal", required=True,
                    help="`journalctl -b -o short-iso` text (or a grep of it)")
    sl.add_argument("--date", required=True, help="YYYY-MM-DD the sar file covers")
    sl.add_argument("--interval-s", type=int, default=SAR_INTERVAL_S)
    sl.add_argument("--min-bytes", type=int, default=LEDGER_MIN_BYTES)
    sl.add_argument("--include-instrument", action="store_true",
                    help="do NOT exclude sysstat-collect (see LEDGER_EXCLUDE_UNITS)")

    args = p.parse_args(argv)
    if args.mode == "steps":
        table = parse_sar(_load(args.sar_r))
        steps = commit_steps(table, args.min_step_kb, args.persist_buckets)
        print(json.dumps([s.as_dict() for s in steps], indent=2))
    elif args.mode == "swap":
        table = parse_sar(_load(args.sar_w))
        print(json.dumps([x.as_dict()
                          for x in swap_excursions(table, args.interval_s)],
                         indent=2))
    elif args.mode == "guard":
        print(json.dumps(window_guard(args.window_s), indent=2))
    elif args.mode == "ledger":
        table = parse_sar(_load(args.sar_w))
        fires = parse_unit_starts(_load(args.journal))
        print(json.dumps(cost_ledger(
            fires, table, args.date, args.interval_s,
            min_bytes=args.min_bytes,
            exclude_units=() if args.include_instrument
            else LEDGER_EXCLUDE_UNITS), indent=2))
    elif args.mode == "timers":
        print(json.dumps([asdict(t) | {"avoidable": t.avoidable}
                          for t in NUC_TIMERS], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
