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
import bisect
import json
import math
import os
import random
import re
import sys
from datetime import date as _date
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


class _Unset:
    """Distinguishes "caller passed nothing" from "caller passed None"."""
    def __repr__(self):
        return "<unset>"


_UNSET = _Unset()


# --------------------------------------------------------------- sar parsing

_BANNER = re.compile(r"^Linux\s")
_RESTART = re.compile(r"LINUX RESTART")
_TIME = re.compile(r"^(\d{2}:\d{2}:\d{2})(\s+(AM|PM))?$")


@dataclass(frozen=True)
class SarRow:
    """One sysstat bucket: its END timestamp plus the named columns.

    `restart_before` marks a row that sysstat wrote after a `LINUX RESTART`
    line with no intervening sample. Round 412: `parse_sar` used to DROP the
    restart marker, which is harmless for a RATE column (`pswpout/s` is
    self-contained per bucket) and corrupting for a LEVEL column
    (`kbcommit`), where a bucket's cost is a difference against the previous
    row and the previous row belongs to a different boot's address space.
    `sysstat_archive.parse_day` has always kept restarts; the two parsers
    disagreeing about whether a marker is representable is how a level
    channel would have silently booked a 30 GB reboot as one unit's cost."""
    time: str
    values: dict
    restart_before: bool = False

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
    banner, blank lines, the `LINUX RESTART` marker sysstat writes at boot
    (kept, as `restart_before` on the next row -- see `SarRow`), the
    trailing `Average:` row (dropped -- it is not a bucket), a repeated header
    row when sar re-prints it, and both 24-hour and `HH:MM:SS AM/PM` stamps.

    A `sar -n DEV`-style table with a leading label column is NOT supported;
    those need a per-interface split the caller should do first. We raise
    rather than silently mis-align, because a silently mis-aligned column is
    exactly how round 388's mystery would have been mis-attributed."""
    columns: tuple = ()
    rows: list = []
    pending_restart = False
    for raw in text.splitlines():
        line = raw.strip()
        if _RESTART.search(line):
            pending_restart = True
            continue
        if not line or _BANNER.match(line):
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
                           values={c: float(v) for c, v in zip(columns, body)},
                           restart_before=pending_restart))
        pending_restart = False
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

# Round 412. `cost_ledger` was written against `sar -W` and reads the literal
# column `pswpout/s`. Round 406's handoff item 4 asks whether that channel is
# simply too coarse to attribute anything on this box, which can only be
# answered by running the SAME fires against a DIFFERENT channel. The two
# channels banked for this boot are not the same shape:
#
#   `pswpout/s` is a RATE. Each bucket's value is self-contained: pages per
#   second over the interval, so cost = rate * interval * page_bytes, and a
#   bucket's cost is knowable from that bucket alone.
#
#   `kbcommit` is a LEVEL -- Committed_AS, the running total of address space
#   the kernel has promised. A bucket's cost is a DIFFERENCE against the
#   previous row, which means (a) the first row of a table has no cost at all,
#   not a cost of zero, and (b) a row after a `LINUX RESTART` has no cost
#   either, because its predecessor describes a different boot.
#
# Conflating those two is how a level channel books a 30 GB reboot as one
# housekeeping unit's cost. `Channel` makes the difference declarative, and
# `bucket_costs` returns `None` -- not `0` -- for a bucket whose cost is
# undefined, so `cost_ledger` can route fires there to `unclassified` instead
# of counting them as free. That is round 400's own rule ("a fire whose cost
# is unknown is not a fire that cost nothing") applied to the buckets.


@dataclass(frozen=True)
class Channel:
    """A sar column read as a perturbation cost, plus how to read it."""
    name: str
    column: str
    kind: str            # "rate" (self-contained per bucket) | "level" (delta)
    unit_bytes: float    # multiplier from the column's units to bytes
    direction: str = "both"   # level only: "rise" | "fall" | "both"

    def __post_init__(self):
        if self.kind not in ("rate", "level"):
            raise PerturbationError(f"unknown channel kind {self.kind!r}")
        if self.direction not in ("rise", "fall", "both"):
            raise PerturbationError(
                f"unknown channel direction {self.direction!r}")
        if self.kind == "rate" and self.direction != "both":
            raise PerturbationError(
                "direction is meaningless for a rate channel: a rate column "
                "has no predecessor to be signed against")


# The channel round 400/406 measured. `pswpout/s` counts pages written OUT to
# swap in the interval; it moves only under memory pressure, which is exactly
# why it is nearly always zero on this box and why K (the number of costly
# buckets) is 3 for a 36-hour boot.
SWAP_CHANNEL = Channel("swap", "pswpout/s", "rate", PAGE_BYTES)

# The channel item 4 proposes. `kbcommit` moves on every allocation whether or
# not it causes pressure, so it sees perturbations the swap channel cannot.
# `direction="rise"` because the question is what a housekeeping unit ALLOCATED;
# a fall is some other process exiting, and crediting a unit with a release
# would make the ledger's sign depend on who happened to die nearby.
COMMIT_CHANNEL = Channel("commit", "kbcommit", "level", KB, "rise")

# Round 418, from `sar -B`. Round 412 left the 04:00:03 perturbation
# "unexplained in a SPECIFIC way": the commit channel says nothing was
# ALLOCATED there, so whatever happened touched pages that were already
# committed. `pgsteal/s` is that event. It counts pages the reclaim path took
# BACK -- a page that is stolen was already promised and already resident, so
# stealing it moves neither `kbcommit` (the promise stands; the mapping is
# still there) nor necessarily `pswpout/s` (a clean file page is dropped, not
# written). The commit and swap channels are not "one coarser than the other";
# they are blind to eviction in two different ways, and this is the column
# that is not.
#
# A RATE channel, like swap: `pgsteal/s` is pages per second over the bucket,
# self-contained, so it needs no stitch and no predecessor.
STEAL_CHANNEL = Channel("steal", "pgsteal/s", "rate", PAGE_BYTES)

CHANNELS = {c.name: c for c in (SWAP_CHANNEL, COMMIT_CHANNEL, STEAL_CHANNEL)}


# ------------------------------------------------------------ stitching days

# `sar` reads ONE day-file. Round 412 found the consequence: a level channel
# has no cost for a day-file's first row, because the row it must difference
# against is in the PREVIOUS file. On `sa31` that swallows three real fires
# (`dpkg-db-backup`, `logrotate`, `sysstat-summary`, all at 00:00:05/00:07:05),
# which land in the 00:10:05 bucket and are reported `unclassified`.
#
# The fix is to carry the previous day's LAST row in as the predecessor. It is
# only legitimate when the two rows are genuinely adjacent samples of the same
# boot, so `stitch_from` refuses in four ways rather than one, and each refusal
# is a distinct way the naive version would have been wrong:
#
#   * the dates are not consecutive        -> a 24 h hole differenced as 10 min
#   * the later row follows a LINUX RESTART -> a 30 GB reboot booked as a cost
#   * the two rows are further apart than a sample gap can explain
#   * the two tables do not have the same columns -> `sar -r` into `sar -W`
#
# And it carries a SPAN, because the stitched bucket is not 10 minutes wide.
# `sar` consumes the first record of each file as its reference point and never
# prints it, so `sa30` ends at 23:50:05 and `sa31` begins at 00:10:05: the
# recovered bucket covers 1200 s, and a fire inside it shares that bucket with
# ten minutes of the previous day.
STITCH_MAX_SPAN_S = 2 * SAR_INTERVAL_S + 180


@dataclass(frozen=True)
class Stitch:
    """The previous day-file's last row, carried in as a predecessor."""
    prev_date: str
    prev_time: str
    next_date: str
    next_time: str
    span_s: int
    values: dict

    def as_dict(self) -> dict:
        return {"prev_date": self.prev_date, "prev_time": self.prev_time,
                "next_date": self.next_date, "next_time": self.next_time,
                "span_s": self.span_s,
                "spans_more_than_one_interval": self.span_s > SAR_INTERVAL_S}


def _date_ordinal(date: str) -> int:
    try:
        y, m, d = (int(x) for x in date.split("-"))
    except ValueError as exc:
        raise PerturbationError(
            f"date {date!r} is not YYYY-MM-DD; a stitch that guesses the date "
            "is how a 24-hour hole gets differenced as ten minutes") from exc
    return _date(y, m, d).toordinal()


def stitch_from(prev_table: SarTable, prev_date: str,
                next_table: SarTable, next_date: str,
                interval_s: int = SAR_INTERVAL_S,
                max_span_s: int = STITCH_MAX_SPAN_S) -> Stitch:
    """Carry `prev_table`'s last row in as `next_table`'s first predecessor.

    Raises `PerturbationError` -- never returns a degraded object -- when the
    join cannot be justified. See the block comment above for the four
    refusals and why each exists.
    """
    if not prev_table.rows:
        raise PerturbationError(f"{prev_date}: no rows to stitch FROM")
    if not next_table.rows:
        raise PerturbationError(f"{next_date}: no rows to stitch INTO")
    if tuple(prev_table.columns) != tuple(next_table.columns):
        raise PerturbationError(
            f"cannot stitch {prev_date} into {next_date}: different columns "
            f"({sorted(prev_table.columns)} vs {sorted(next_table.columns)}) "
            "-- these are two different sar activity types")
    gap_days = _date_ordinal(next_date) - _date_ordinal(prev_date)
    if gap_days != 1:
        raise PerturbationError(
            f"cannot stitch {prev_date} into {next_date}: they are "
            f"{gap_days} day(s) apart, not 1; only consecutive day-files "
            "have adjacent samples")
    last, first = prev_table.rows[-1], next_table.rows[0]
    if first.restart_before:
        raise PerturbationError(
            f"cannot stitch into {next_date} {first.time}: it follows a LINUX "
            "RESTART, so its predecessor describes a different boot's address "
            "space")
    span_s = _hms_to_s(first.time) + 86_400 - _hms_to_s(last.time)
    if span_s <= 0:
        raise PerturbationError(
            f"cannot stitch {prev_date} {last.time} -> {next_date} "
            f"{first.time}: non-positive span {span_s}s")
    if span_s > max_span_s:
        raise PerturbationError(
            f"cannot stitch {prev_date} {last.time} -> {next_date} "
            f"{first.time}: {span_s}s apart, more than max_span_s "
            f"({max_span_s}s). Samples that far apart are a gap in the "
            "record, not a bucket boundary")
    return Stitch(prev_date=prev_date, prev_time=last.time,
                  next_date=next_date, next_time=first.time,
                  span_s=span_s, values=dict(last.values))


def bucket_costs(table: SarTable, channel: Channel = SWAP_CHANNEL,
                 interval_s: int = SAR_INTERVAL_S,
                 stitch: "Stitch | None" = None) -> list:
    """[(bucket_end, raw_value, cost_bytes_or_None)], one per row, in order.

    `cost_bytes is None` means UNDEFINED, and only a level channel produces
    it: the table's first row, and any row sysstat marked `restart_before`.
    Callers must not treat `None` as `0` -- that is the whole reason it is not
    `0`.

    Round 418: `stitch` supplies the missing predecessor for the FIRST row, so
    a level channel can cost a day-file's opening bucket (see `stitch_from`).
    It is deliberately a NO-OP for a rate channel -- a `pswpout/s` bucket is
    self-contained and has no predecessor to be joined to -- and passing one
    there is not an error, because `channel_sweep` hands the same stitch to
    every channel it sweeps. Ask `stitch_applies(channel, stitch)` if you need
    to report whether it did anything.
    """
    if interval_s <= 0:
        raise PerturbationError("interval_s must be > 0")
    if channel.column not in table.columns:
        raise PerturbationError(
            f"channel {channel.name!r} needs column {channel.column!r}; this "
            f"table has {sorted(table.columns)}")
    out = []
    prev = None
    if stitch_applies(channel, stitch):
        if channel.column not in stitch.values:
            raise PerturbationError(
                f"stitch from {stitch.prev_date} {stitch.prev_time} has no "
                f"column {channel.column!r}; it carries "
                f"{sorted(stitch.values)}")
        prev = stitch.values[channel.column]
    for r in table.rows:
        v = r.get(channel.column)
        if channel.kind == "rate":
            cost = round(v * interval_s) * channel.unit_bytes
        elif prev is None or r.restart_before:
            cost = None
        else:
            delta = v - prev
            if channel.direction == "rise":
                delta = max(delta, 0.0)
            elif channel.direction == "fall":
                delta = max(-delta, 0.0)
            else:
                delta = abs(delta)
            cost = delta * channel.unit_bytes
        out.append((r.time, v, None if cost is None else int(cost)))
        prev = v
    return out


def stitch_applies(channel: Channel, stitch) -> bool:
    """Would this stitch change this channel's costs? Level only.

    Exists so that "a stitch was supplied" and "a stitch did something" are
    two different questions with two different answers, and a ledger can
    report the second rather than the first."""
    return stitch is not None and channel.kind == "level"


def bucket_spans(table: SarTable, interval_s: int = SAR_INTERVAL_S,
                 stitch=None, channel: Channel = SWAP_CHANNEL) -> dict:
    """{bucket_end: seconds the bucket actually covers}.

    Every bucket is `interval_s` wide EXCEPT a stitched first bucket, which is
    as wide as the gap the stitch crossed -- 1200 s on this record, because
    `sar` never prints a day-file's first sample. A caller that assumes 600 s
    there is dividing by the wrong number and, worse, is unaware that ten
    minutes of the PREVIOUS day fall inside the bucket it is attributing."""
    spans = {r.time: interval_s for r in table.rows}
    if stitch_applies(channel, stitch) and table.rows:
        spans[table.rows[0].time] = stitch.span_s
    return spans


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


# --------------------------------------------------------------- reclaim

# Round 418, answering round 412's handoff item 2. Round 412 established that
# `Committed_AS` does not move at 04:00:03 on sa31 and concluded: "the question
# is no longer 'which unit allocated' but 'what touched already-committed
# pages'". `sar -B` is the column family that can answer it, and it was banked
# in `state/nuc-capture-r400/sar-all.txt` nine rounds before anyone read it.
#
# The three columns that matter, and what each does NOT mean:
#
#   `pgscank/s` -- pages/s scanned by kswapd. Non-zero means the kernel crossed
#       a watermark and woke the background reclaimer. It does NOT mean any
#       allocation stalled.
#   `pgscand/s` -- pages/s scanned in DIRECT reclaim, i.e. inside an
#       allocation that could not be satisfied. This is the column that means
#       something waited. On this box's whole banked boot it is zero.
#   `pgsteal/s` -- pages/s actually reclaimed. A stolen page was already
#       committed and already resident, which is exactly why neither the commit
#       channel nor the swap channel sees a clean-page eviction.
#
# `%vmeff` is sysstat's `pgsteal / (pgscank + pgscand) * 100`. This record
# contains buckets where it EXCEEDS 100 -- 199.23 and 137.56 on sa31 -- which
# is impossible if the two columns counted the same pages. They do not: the
# steal and scan counters in `/proc/vmstat` have different member families, so
# pages can be reclaimed on paths that were never charged as scanned. This
# module reports the excess as `steal_exceeds_scan` instead of averaging it
# away, because a "reclaim efficiency" quoted from such a bucket is not one.

RECLAIM_SCAN_KSWAPD = "pgscank/s"
RECLAIM_SCAN_DIRECT = "pgscand/s"
RECLAIM_STEAL = "pgsteal/s"
RECLAIM_REQUIRED = (RECLAIM_SCAN_KSWAPD, RECLAIM_SCAN_DIRECT, RECLAIM_STEAL)


@dataclass(frozen=True)
class ReclaimEvent:
    """One `sar -B` bucket, read as a page-reclaim event."""
    time: str
    kind: str                  # "direct" | "mixed" | "kswapd" | "quiet"
    scan_kswapd_s: float
    scan_direct_s: float
    steal_s: float
    scanned_pages: int
    stolen_pages: int
    stolen_bytes: int
    paged_in_kb: int
    paged_out_kb: int
    major_faults: float
    vmeff_pct: float           # derived: steal/(scank+scand)*100, 0 if no scan
    vmeff_reported: float      # sysstat's own %vmeff column, for comparison
    steal_exceeds_scan: bool
    # Round 424. The divisor stopped being a hypothesis: `sadc` on the box
    # matches `pgsteal_` as a bare PREFIX and `pgscan_kswapd`/`pgscan_direct`
    # as full names (banked, `state/nuc-capture-r424/collector-evidence.txt`).
    # The reported columns above are still untouched -- round 418's rule, that
    # a silently halved byte count gets quoted without its caveat, is right and
    # survives. These are the corrected view, carried BESIDE the raw one so a
    # caller has to name which it is using.
    corrected_steal_s: float = 0.0
    corrected_stolen_pages: int = 0
    corrected_stolen_bytes: int = 0
    corrected_vmeff_pct: float = 0.0
    # Round 430. `vmeff_pct` is documented "0 if no scan", and a bucket that
    # stole 4 087 pages/s while scanning ZERO therefore renders as 0.000 % --
    # the BOTTOM of an efficiency ranking, when it is really an undefined
    # ratio and the sharpest possible violation of `steal <= scan`. Four such
    # buckets sit on sa23 alone. The flag exists so a caller can separate
    # "reclaimed inefficiently" from "the two columns do not describe the same
    # pages", which are opposite findings that sort adjacently.
    scan_free_steal: bool = False
    vmeff_defined: bool = True

    def as_dict(self) -> dict:
        return asdict(self)


def _opt(row: SarRow, column: str, default: float = 0.0) -> float:
    return row.values.get(column, default)


def reclaim_events(table: SarTable, interval_s: int = SAR_INTERVAL_S,
                   page_bytes: int = PAGE_BYTES,
                   include_quiet: bool = False) -> list:
    """Every bucket of a `sar -B` table, classified by which reclaim path ran.

    `include_quiet=False` (the default) returns only buckets that scanned or
    stole something. The quiet ones are not dropped from the analysis -- they
    are the denominator, and `reclaim_summary` counts them -- but a list of 138
    all-zero rows is not what a caller wants back.

    Raises rather than guessing if the table is not `sar -B`: the columns of
    `sar -W` parse perfectly well and would silently produce a table of zeros,
    i.e. "this box never reclaimed", which is the exact false negative this
    function exists to prevent."""
    if interval_s <= 0:
        raise PerturbationError("interval_s must be > 0")
    missing = [c for c in RECLAIM_REQUIRED if c not in table.columns]
    if missing:
        raise PerturbationError(
            f"not a `sar -B` table: missing {missing}; this table has "
            f"{sorted(table.columns)}. Reading a non -B table here would "
            "report zero reclaim everywhere, which is a false negative, not "
            "an empty result")
    out = []
    for r in table.rows:
        sk = r.get(RECLAIM_SCAN_KSWAPD)
        sd = r.get(RECLAIM_SCAN_DIRECT)
        st = r.get(RECLAIM_STEAL)
        scanned = round((sk + sd) * interval_s)
        stolen = round(st * interval_s)
        if sd > 0 and sk > 0:
            kind = "mixed"
        elif sd > 0:
            kind = "direct"
        elif sk > 0 or st > 0:
            kind = "kswapd"
        else:
            kind = "quiet"
        if kind == "quiet" and not include_quiet:
            continue
        out.append(ReclaimEvent(
            time=r.time, kind=kind,
            scan_kswapd_s=sk, scan_direct_s=sd, steal_s=st,
            scanned_pages=scanned, stolen_pages=stolen,
            stolen_bytes=stolen * page_bytes,
            paged_in_kb=round(_opt(r, "pgpgin/s") * interval_s),
            paged_out_kb=round(_opt(r, "pgpgout/s") * interval_s),
            major_faults=_opt(r, "majflt/s"),
            vmeff_pct=(st / (sk + sd) * 100.0) if (sk + sd) > 0 else 0.0,
            vmeff_reported=_opt(r, "%vmeff"),
            steal_exceeds_scan=st > (sk + sd),
            scan_free_steal=(sk + sd) == 0 and st > 0,
            vmeff_defined=(sk + sd) > 0,
            corrected_steal_s=st / RECLAIM_STEAL_DIVISOR,
            corrected_stolen_pages=round(st / RECLAIM_STEAL_DIVISOR * interval_s),
            corrected_stolen_bytes=round(
                st / RECLAIM_STEAL_DIVISOR * interval_s) * page_bytes,
            corrected_vmeff_pct=(
                (st / RECLAIM_STEAL_DIVISOR) / (sk + sd) * 100.0)
            if (sk + sd) > 0 else 0.0))
    return out


# Round 418. Six of the seven reclaim buckets in the r400 capture report
# `%vmeff > 100` -- pgsteal exceeding pgscank+pgscand, which is impossible if
# the two columns count the same pages. Halving `pgsteal` puts ALL SEVEN at or
# below 100 %, with the maximum landing on exactly 100.000 and five of seven
# within 1 % of that ceiling. A ceiling that sharp is not what a noisy
# undercount of `pgscan` would produce; it is what a factor-of-two DOUBLE
# COUNT of `pgsteal` produces.
#
# The mechanism this predicts, stated so it can be refuted rather than
# believed: modern kernels export `pgsteal_*` under two independent
# breakdowns in `/proc/vmstat` -- by actor (`pgsteal_kswapd`,
# `pgsteal_direct`, `pgsteal_khugepaged`) and by page type (`pgsteal_anon`,
# `pgsteal_file`) -- which sum to the same pages twice, while `pgscan_kswapd`
# and `pgscan_direct` are read as named singles. If sysstat totals the
# `pgsteal_*` family it charges every reclaimed page twice.
#
# THIS MODULE DOES NOT APPLY THE CORRECTION. `ReclaimEvent` reports what the
# file says, because a silently halved byte count is exactly the kind of
# number that ends up quoted without its caveat. `reclaim_double_count_check`
# reports the evidence and the corrected view side by side, and the round file
# quotes both.
#
# Falsified or confirmed on the next UP round by one read-only command:
#     grep -E '^pg(scan|steal)' /proc/vmstat
# Confirmed if `pgsteal_anon + pgsteal_file` equals
# `pgsteal_kswapd + pgsteal_direct + pgsteal_khugepaged` and sar's total is
# their sum; refuted if sar's `pgsteal` matches a single family.
RECLAIM_STEAL_DIVISOR_HYPOTHESIS = 2

# ---------------------------------------------------------------- round 424
# CONFIRMED, and NOT by the command round 418 wrote down.
#
# Round 418's falsification test was `grep -E '^pg(scan|steal)' /proc/vmstat`,
# to be checked for `pgsteal_anon + pgsteal_file == pgsteal_kswapd +
# pgsteal_direct + pgsteal_khugepaged`. Round 424 ran it on the first up
# window since, and every one of those fourteen counters read **0**: the box
# had rebooted 2 h 40 m earlier and had not reclaimed a single page. The
# identity held as 0 == 0 and settled nothing. A test that needs the
# phenomenon to have RECURRED is only as available as the phenomenon.
#
# What settled it was reading the collector instead of the kernel:
#
#     $ strings /usr/lib/sysstat/sadc | grep -E '^pg[a-z_]*$' | sort -u
#     pgscan_direct
#     pgscan_kswapd
#     pgsteal_
#
# Three literals, and the asymmetry is the whole finding. `pgsteal_` is a bare
# prefix; on kernel 6.8 it matches five fields forming TWO complete partitions
# of the same events (kswapd/direct/khugepaged, and anon/file), so every
# stolen page is counted exactly twice. `pgscan_kswapd` and `pgscan_direct`
# are full field names matching one partition each, so the denominator is
# counted once. `%vmeff = pgsteal / (pgscank + pgscand)` is therefore exactly
# 2x the true reclaim efficiency -- numerator doubled, denominator not.
#
# Those literals are in the binary whether or not the box ever reclaimed
# anything, which is why this route was available on a boot where the other
# one was not. Banked: `state/nuc-capture-r424/collector-evidence.txt`
# (sysstat 12.6.1-2, kernel 6.8.0-138-generic).
#
# The arithmetic in the r400 capture agrees to the digit: sa30 14:50:05 reads
# `pgscank/s 55.44, pgsteal/s 110.88` -- 2.000x exactly -- and five more
# buckets land within 1.4 % of 200 %.
RECLAIM_STEAL_DIVISOR = 2

# The literal `strings` output above, as data, so the claim is re-derivable
# from the banked file instead of trusted from this comment.
SADC_SCAN_LITERALS = ("pgscan_kswapd", "pgscan_direct")
SADC_STEAL_PREFIX = "pgsteal_"


def sadc_reclaim_literals(strings_text: str) -> dict:
    """Classify the `pg*` literals `sadc` carries into prefixes and full names.

    A literal is a PREFIX if some other exported vmstat field starts with it
    and is longer -- which is exactly the condition under which a `strncmp`
    accumulator over-collects. Deciding that needs the kernel's field list,
    so this returns the classification and `steal_double_count_evidence`
    joins it to `/proc/vmstat`.
    """
    lits = sorted({ln.strip() for ln in strings_text.splitlines()
                   if ln.strip().startswith("pg") and " " not in ln.strip()})
    return {
        "literals": lits,
        "scan_literals": [l for l in lits if l.startswith("pgscan")],
        "steal_literals": [l for l in lits if l.startswith("pgsteal")],
    }


def parse_vmstat_fields(vmstat_text: str, prefixes=("pgscan", "pgsteal")) -> dict:
    """`/proc/vmstat` -> {field: value} for the reclaim families."""
    out = {}
    for line in vmstat_text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].startswith(prefixes):
            try:
                out[parts[0]] = int(parts[1])
            except ValueError:
                continue
    return out


def steal_double_count_evidence(strings_text: str, vmstat_text: str) -> dict:
    """Is `pgsteal` double-counted, and does the KERNEL-state test say so too?

    Reports the two routes separately and refuses to merge them. The literal
    route is available whenever the collector is installed; the counter route
    needs the box to have reclaimed something since boot, and on round 424's
    fresh boot it had not. Calling an all-zero identity "confirmed" is how a
    vacuous test gets quoted as a measurement, so it is named `vacuous` here
    and `divisor` is decided by the literal route alone.
    """
    lits = sadc_reclaim_literals(strings_text)
    fields = parse_vmstat_fields(vmstat_text)

    def _over(lit):
        return sorted(f for f in fields if f.startswith(lit) and f != lit)

    # A literal counts the field it names ONLY if such a field exists.
    # `pgsteal_` names none -- it is a bare prefix -- so counting it as a
    # field inflated the total to 6 where the collector sums 5.
    def _n(lit):
        return len(_over(lit)) + (1 if lit in fields else 0)

    steal_over = {l: _over(l) for l in lits["steal_literals"]}
    scan_over = {l: _over(l) for l in lits["scan_literals"]}
    n_steal = sum(_n(l) for l in steal_over)
    n_scan_matched = {l: _n(l) for l in scan_over}

    actor = ("pgsteal_kswapd", "pgsteal_direct", "pgsteal_khugepaged")
    bytype = ("pgsteal_anon", "pgsteal_file")
    matched_steal = {f for v in steal_over.values() for f in v}
    matched_steal |= {l for l in steal_over if l in fields}
    # The doubling is not "matches a lot of fields", it is "matches BOTH of
    # two partitions that each already total every stolen page". Testing for
    # that directly means a kernel which drops one partition is reported as
    # single-counted rather than as a smaller double-count.
    hits_actor = sorted(matched_steal & set(actor))
    hits_type = sorted(matched_steal & set(bytype))
    doubled = bool(hits_actor) and bool(hits_type)

    # A second, far smaller asymmetry the same evidence exposes:
    # `pgscan_direct` is a full name but still a prefix of
    # `pgscan_direct_throttle`, a SUBSET counter, so throttled scans are
    # charged twice in the denominator. It reads 0 on this box and on any box
    # not under allocator pressure, which is why it has never shown up -- but
    # it biases %vmeff DOWNWARD, i.e. the opposite way to the numerator bug.
    scan_subset_overmatch = sorted(
        f for v in scan_over.values() for f in v if f.endswith("_throttle"))

    a_sum = sum(fields.get(f, 0) for f in actor)
    t_sum = sum(fields.get(f, 0) for f in bytype)
    all_zero = not any(fields.get(f, 0) for f in actor + bytype)

    return {
        "steal_literals": lits["steal_literals"],
        "scan_literals": lits["scan_literals"],
        "steal_fields_matched": steal_over,
        "scan_fields_matched": scan_over,
        "n_steal_fields_summed": n_steal,
        "n_scan_fields_per_literal": n_scan_matched,
        "steal_partitions_hit": {"actor": hits_actor, "by_type": hits_type},
        "scan_subset_overmatch": scan_subset_overmatch,
        "literal_route": "double-counted" if doubled else "single",
        "divisor": RECLAIM_STEAL_DIVISOR if doubled else 1,
        "actor_partition_sum": a_sum,
        "type_partition_sum": t_sum,
        "counter_route": ("vacuous -- every reclaim counter is 0 on this boot, "
                          "so the partition identity holds trivially and "
                          "measures nothing"
                          if all_zero else
                          "agree" if a_sum == t_sum else "disagree"),
        "counters_all_zero": all_zero,
        "why": ("`%s` is a bare prefix matching %d field(s) -- the actor "
                "partition %s AND the page-type partition %s, which total the "
                "same stolen pages -- while %s are full field names covering "
                "one partition only. Numerator doubled, denominator not, so "
                "%%vmeff reads %dx the true reclaim efficiency."
                % (SADC_STEAL_PREFIX, n_steal, hits_actor, hits_type,
                   "/".join(lits["scan_literals"]), RECLAIM_STEAL_DIVISOR)
                if doubled else
                "`%s` matches %d field(s) and hits only the %s partition; no "
                "double count is implied." % (
                    SADC_STEAL_PREFIX, n_steal,
                    "actor" if hits_actor else "page-type" if hits_type
                    else "no known")),
    }


# ---------------------------- round 430: the OTHER half of the same evidence

# Round 424 confirmed the numerator half of the %vmeff defect from
# `state/nuc-capture-r424/collector-evidence.txt` and validated it on the two
# day-files this track had ever opened, sa30 and sa31, where halving `pgsteal`
# puts every bucket at or under the ceiling. Run over all ten banked day-files
# the correction FAILS: of 108 reclaim buckets, 21 stole pages while scanning
# ZERO -- `pgscank/s 0.00, pgscand/s 0.00, pgsteal/s 4087.96` on sa23 21:40 --
# and 8 more still exceed 100 % after halving, the worst at 3053 %. The four
# days on which `ceiling_restored` is True are 08-28 to 08-31; every failing
# day is older than the window anyone had looked at.
#
# The mechanism is in the SAME banked file, one section below the one round
# 424 read. `PROC_VMSTAT_RECLAIM_FIELDS` lists `pgscan_khugepaged`, and
# `SADC_VMSTAT_LITERALS` does not contain it:
#
#     numerator   = sum of every `pgsteal_*`   = (kswapd+direct+khugepaged)
#                                              + (anon+file)        = 2 x T
#     denominator = pgscan_kswapd + pgscan_direct                   = S - S_khuge
#
# So the reported ratio is `2T / (S - S_khuge)`, not `2T / S`. Two consequences
# fall straight out and both are observed: whenever khugepaged does the
# reclaiming the denominator loses ground the numerator keeps, so the residual
# is UNBOUNDED rather than a second constant factor; and in the limit where
# khugepaged does all of it the denominator is 0 while the numerator is not,
# which is the scan-free bucket exactly.
#
# The divisor is therefore right and INCOMPLETE: `corrected_*` is an upper
# bound on the true efficiency, not the true efficiency, and it is only a
# correction at all on buckets where `pgscan_khugepaged` did not move.
#
# Falsifiable, on a box that has actually reclaimed (this one has not: every
# reclaim counter is 0 across the whole 8 h 30 m boot, so the direct test is
# as unavailable to round 430 as it was to round 424):
#     grep -E '^pg(scan|steal)' /proc/vmstat
# Confirmed if `pgscan_anon + pgscan_file` exceeds
# `pgscan_kswapd + pgscan_direct` by roughly `pgsteal_khugepaged`'s share, and
# if the residual buckets are the ones where `pgsteal_khugepaged` moved.
# Refuted if `pgscan_khugepaged` stays 0 while residual buckets keep appearing.

# The complete scan partition on kernel 6.8, against what sadc reads.
KERNEL_SCAN_ACTOR_FIELDS = ("pgscan_kswapd", "pgscan_direct",
                            "pgscan_khugepaged")
KERNEL_SCAN_TYPE_FIELDS = ("pgscan_anon", "pgscan_file")


def scan_undercount_evidence(strings_text: str, vmstat_text: str) -> dict:
    """Which reclaim-scan paths the collector's denominator leaves out.

    The mirror image of `steal_double_count_evidence`, from the same two
    inputs. That function asks "how many fields does the numerator's prefix
    over-collect"; this one asks "how many fields does the denominator's list
    of full names fail to collect", which is the question whose answer makes
    `%vmeff` unbounded instead of merely doubled.
    """
    lits = sadc_reclaim_literals(strings_text)
    fields = parse_vmstat_fields(vmstat_text)
    read = set(lits["scan_literals"])
    # A full-name literal collects its own field; a prefix collects every
    # field starting with it. Either way, what it collects is a field set.
    collected = set()
    for l in read:
        collected |= {f for f in fields if f == l or f.startswith(l)}
    actor_present = [f for f in KERNEL_SCAN_ACTOR_FIELDS if f in fields]
    omitted = [f for f in actor_present if f not in collected]
    return {
        "scan_literals": sorted(read),
        "kernel_scan_fields": sorted(f for f in fields
                                     if f.startswith("pgscan")),
        "actor_partition_present": actor_present,
        "actor_fields_collected": sorted(collected & set(actor_present)),
        "actor_fields_omitted": omitted,
        "n_omitted": len(omitted),
        "denominator_is_complete": not omitted,
        "steal_counterpart_collected": sorted(
            f for f in fields
            if f.startswith(SADC_STEAL_PREFIX)
            and f.replace("pgsteal", "pgscan") in omitted),
        "why": (
            "the denominator omits %s while the `%s` prefix collects its "
            "steal counterpart %s, so a bucket reclaimed by that path adds to "
            "%%vmeff's numerator and nothing to its denominator -- the ratio "
            "is unbounded, and is undefined when that path does ALL the work"
            % (omitted, SADC_STEAL_PREFIX,
               sorted(f for f in fields
                      if f.startswith(SADC_STEAL_PREFIX)
                      and f.replace("pgsteal", "pgscan") in omitted))
            if omitted else
            "the collector reads every actor-partition scan field the kernel "
            "exports; the denominator is complete and the only defect is the "
            "numerator's double count"),
    }


def reclaim_double_count_check(events: Iterable,
                               divisor: float = RECLAIM_STEAL_DIVISOR_HYPOTHESIS,
                               ceiling_pct: float = 100.0,
                               near_pct: float = 1.0) -> dict:
    """Does dividing `pgsteal` by `divisor` restore the %vmeff ceiling?

    The test has real content only because `%vmeff <= 100` is a THEOREM about
    reclaim, not a convention: you cannot steal a page you did not scan. Any
    divisor that leaves observations above the ceiling is refuted; a divisor
    that pushes every observation far BELOW it explains nothing, which is why
    `n_near_ceiling` is reported too -- a correct divisor should leave the
    efficient buckets pinned AT the ceiling, not scattered under it."""
    if divisor <= 0:
        raise PerturbationError("divisor must be > 0")
    events = list(events)
    evs = [e for e in events if (e.scan_kswapd_s + e.scan_direct_s) > 0]
    # Round 430. This filter was here from round 418 and it was SILENT: the
    # buckets it drops are precisely the ones where `pgsteal > 0` and
    # `pgscank + pgscand == 0`, i.e. the strongest counter-examples to the
    # very theorem the function tests. Dropping them without a count let
    # `ceiling_restored: True` be published from a set the violators had been
    # removed from. They are counted now, and their presence blocks the
    # verdict -- no divisor can rescue `x/0`.
    scan_free = [e for e in events if getattr(e, "scan_free_steal", False)]
    if not evs:
        return {"n_events": 0, "verdict": "no scanned buckets to test",
                "n_scan_free_steal": len(scan_free),
                "scan_free_steal_buckets": [e.time for e in scan_free],
                "divisor": divisor}
    rep = [e.vmeff_pct for e in evs]
    cor = [v / divisor for v in rep]
    restored = (all(v <= ceiling_pct + 1e-9 for v in cor) and not scan_free)
    return {
        "n_events": len(evs),
        "n_scan_free_steal": len(scan_free),
        "scan_free_steal_buckets": [e.time for e in scan_free],
        "divisor": divisor,
        "ceiling_pct": ceiling_pct,
        "max_reported_pct": max(rep),
        "max_corrected_pct": max(cor),
        "n_over_ceiling_reported": sum(1 for v in rep if v > ceiling_pct),
        "n_over_ceiling_corrected": sum(1 for v in cor if v > ceiling_pct),
        "n_near_ceiling": sum(1 for v in cor
                              if ceiling_pct - near_pct <= v <= ceiling_pct),
        "ceiling_restored": restored,
        "corrected_pct": cor,
        "why": ("dividing pgsteal by %g puts every bucket at or under the "
                "%g%% reclaim-efficiency ceiling (max %.3f%%), which %d of %d "
                "buckets violate as reported"
                % (divisor, ceiling_pct, max(cor),
                   sum(1 for v in rep if v > ceiling_pct), len(rep))
                if restored else
                "divisor %g does NOT restore the ceiling: %d scanned "
                "bucket(s) still exceed %g%%, and %d bucket(s) stole pages "
                "with ZERO scanned, which no divisor can fix"
                % (divisor, sum(1 for v in cor if v > ceiling_pct),
                   ceiling_pct, len(scan_free))),
    }


def reclaim_summary(table: SarTable, date: str = "",
                    interval_s: int = SAR_INTERVAL_S,
                    page_bytes: int = PAGE_BYTES) -> dict:
    """Totals over a `sar -B` day, with the denominator kept.

    `n_buckets` is every bucket in the file, not just the noisy ones: a
    reclaim rate with no denominator is round 417's finding in a new column."""
    events = reclaim_events(table, interval_s, page_bytes, include_quiet=True)
    loud = [e for e in events if e.kind != "quiet"]
    by_kind: dict = {}
    for e in events:
        by_kind[e.kind] = by_kind.get(e.kind, 0) + 1
    biggest = max(loud, key=lambda e: e.stolen_bytes, default=None)
    return {
        "date": date,
        "n_buckets": len(events),
        "n_reclaim_buckets": len(loud),
        "reclaim_bucket_fraction": (len(loud) / len(events)) if events else None,
        "by_kind": by_kind,
        "n_direct_reclaim_buckets": by_kind.get("direct", 0) + by_kind.get("mixed", 0),
        "total_scanned_pages": sum(e.scanned_pages for e in loud),
        "total_stolen_pages": sum(e.stolen_pages for e in loud),
        "total_stolen_bytes": sum(e.stolen_bytes for e in loud),
        "total_paged_in_kb": sum(e.paged_in_kb for e in events),
        "total_paged_out_kb": sum(e.paged_out_kb for e in events),
        "n_steal_exceeds_scan": sum(1 for e in loud if e.steal_exceeds_scan),
        "n_scan_free_steal": sum(1 for e in loud if e.scan_free_steal),
        "steal_exceeds_scan_buckets": [e.time for e in loud if e.steal_exceeds_scan],
        "largest_bucket": biggest.as_dict() if biggest else None,
        "double_count": reclaim_double_count_check(loud),
        "events": [e.as_dict() for e in loud],
    }


def eviction_gap(reclaim_table: SarTable, level_table: SarTable,
                 channel: Channel = COMMIT_CHANNEL,
                 interval_s: int = SAR_INTERVAL_S,
                 page_bytes: int = PAGE_BYTES,
                 stitch=None) -> list:
    """For every reclaim bucket, what the LEVEL channel said about it.

    This is round 412's item 2 as one number per event. If the commit channel
    is merely coarse, its cost at a reclaim bucket should be the same order of
    magnitude as the pages stolen there. If the two instruments are blind in
    different directions -- eviction moves residency, not commitment -- the
    ratio collapses, and the size of the collapse is the evidence.

    `ratio` is `commit_cost_bytes / stolen_bytes`, or `None` where the level
    channel has no defined cost for that bucket (first row, post-restart)."""
    costs = {name: b for name, _v, b in
             bucket_costs(level_table, channel, interval_s, stitch=stitch)}
    out = []
    for e in reclaim_events(reclaim_table, interval_s, page_bytes):
        if e.time not in costs:
            out.append({"time": e.time, "stolen_bytes": e.stolen_bytes,
                        "level_bytes": None, "ratio": None,
                        "why": f"no {channel.name} bucket at {e.time}"})
            continue
        b = costs[e.time]
        out.append({
            "time": e.time, "kind": e.kind,
            "stolen_bytes": e.stolen_bytes,
            "paged_in_kb": e.paged_in_kb,
            "level_channel": channel.name,
            "level_bytes": b,
            "ratio": (None if b is None or e.stolen_bytes == 0
                      else b / e.stolen_bytes),
            "why": (f"{channel.name} cost undefined for this bucket"
                    if b is None else ""),
        })
    return out


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
    """One named housekeeping fire, and what the bucket it fell in cost.

    Round 412 renamed `pswpout_s` -> `channel_value` and
    `bucket_swapped_bytes` -> `bucket_bytes`: the ledger is no longer
    swap-only, and a field called `bucket_swapped_bytes` holding a
    `Committed_AS` delta is a lie that survives into every JSON file it is
    written to. `attribution_evidence` still READS the old key, because
    ledgers written by rounds 400-406 exist on disk and a rename must not
    invalidate banked data."""
    at_utc: str
    unit: str
    bucket_end: str
    channel: str
    channel_value: float
    bucket_bytes: int
    bucket_shared_by: int        # DISTINCT UNITS in this bucket, not fires
    bucket_fires: int            # fires in it, which may exceed shared_by
    bucket_span_s: int           # 418: a stitched boundary bucket is WIDER
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

# The swap threshold above is DERIVED from two labelled events on that
# channel. `Committed_AS` has no such pair on this record: there is no bucket
# independently known to be noise-and-must-be-rejected paired with a smallest
# event independently known to be real. Round 412 therefore refuses to invent
# one. A channel with `None` here has no defensible default and `cost_ledger`
# demands an explicit `min_bytes`, so that every commit-channel verdict in the
# record carries the number it was produced with. Use `channel_sweep` to see
# how much the verdict depends on it -- if it moves, the threshold IS the
# result and no single run should be quoted.
# Round 418 adds `steal` with the same `None`, and for the same reason: this
# record has no bucket independently labelled "reclaim noise" to pair against a
# smallest real reclaim. Every one of its three non-zero scan buckets is large.
# A threshold invented here would be the result.
CHANNEL_MIN_BYTES = {"swap": LEDGER_MIN_BYTES, "commit": None, "steal": None}

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
                min_bytes=_UNSET,
                exclude_units: Iterable = LEDGER_EXCLUDE_UNITS,
                boundary_slack_s: int = LEDGER_BOUNDARY_SLACK_S,
                channel: Channel = SWAP_CHANNEL,
                stitch=None) -> dict:
    """Join every named unit start to the sar bucket it fell in.

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
    if min_bytes is _UNSET:
        min_bytes = CHANNEL_MIN_BYTES.get(channel.name)
        if min_bytes is None:
            raise PerturbationError(
                f"channel {channel.name!r} has no derived costly-threshold on "
                f"this record (see CHANNEL_MIN_BYTES); pass min_bytes "
                f"explicitly and report it, or use channel_sweep")
    if min_bytes < 0:
        raise PerturbationError("min_bytes must be >= 0")
    excluded = set(exclude_units or ())
    costs = bucket_costs(swap_table, channel, interval_s, stitch=stitch)
    spans = bucket_spans(swap_table, interval_s, stitch, channel)
    # A bucket's window is (end - its OWN span, end]. Only a stitched first
    # bucket differs from `interval_s`, and using `interval_s` for it would
    # leave a real 10-minute hole that no bucket claims.
    ends = [(name, _hms_to_s(name) - spans[name], _hms_to_s(name), value)
            for name, value, _b in costs]
    bucket_bytes = {name: b for name, _v, b in costs}
    # A level channel's undefined buckets (first row, post-restart row) are
    # not part of the denominator: they are buckets whose cost is UNKNOWN, and
    # counting them as free would inflate N and deflate every base rate.
    defined = {name for name, b in bucket_bytes.items() if b is not None}

    placed, unclassified, skipped = [], [], 0
    for f in fires:
        at, unit = (f.at_utc, f.label) if hasattr(f, "at_utc") else (f[0], f[1])
        if date and not at.startswith(date):
            continue
        if unit in excluded:
            skipped += 1
            continue
        t = _hms_to_s(at.split("T")[-1][:8]) + boundary_slack_s
        hit = next(((name, rate) for name, start, end, rate in ends
                    if start < t <= end), None)
        if hit is None:
            unclassified.append({"at_utc": at, "unit": unit,
                                 "why": "no sar bucket covers this instant"})
            continue
        if hit[0] not in defined:
            unclassified.append({"at_utc": at, "unit": unit,
                                 "why": f"bucket {hit[0]} has no defined "
                                        f"{channel.name} cost (first row of "
                                        f"the table, or a post-restart row)"})
            continue
        placed.append((at, unit, hit[0], hit[1]))

    # Round 412: `share` counts DISTINCT UNITS, not fires. It used to count
    # fires, which made two fires of the SAME unit in one bucket set
    # `sole_attributable = False` -- the flag reporting "nothing is separable"
    # about a bucket in which exactly one unit is implicated. No bucket in the
    # r400 capture has same-unit repeats, so every published number is
    # unchanged; the defect was latent, not active, and is pinned as both.
    share_units: dict = {}
    fires_in: dict = {}
    for _at, unit, name, _rate in placed:
        share_units.setdefault(name, set()).add(unit)
        fires_in[name] = fires_in.get(name, 0) + 1
    share = {name: len(u) for name, u in share_units.items()}

    entries = []
    for at, unit, name, rate in placed:
        b = bucket_bytes[name]          # never None: `placed` filtered by `defined`
        costly = b >= min_bytes
        entries.append(LedgerEntry(
            at_utc=at, unit=unit, bucket_end=name, channel=channel.name,
            channel_value=rate,
            bucket_bytes=b, bucket_shared_by=share[name],
            bucket_fires=fires_in[name], bucket_span_s=spans[name],
            costly=costly, sole_attributable=costly and share[name] == 1))

    by_unit = {}
    for e in entries:
        u = by_unit.setdefault(e.unit, {"fires": 0, "in_costly_bucket": 0,
                                        "sole_attributable": 0,
                                        "sole_attributable_bytes": 0})
        u["fires"] += 1
        u["in_costly_bucket"] += int(e.costly)
        u["sole_attributable"] += int(e.sole_attributable)
        u["sole_attributable_bytes"] += e.bucket_bytes if e.sole_attributable else 0

    costly_buckets = sorted({e.bucket_end for e in entries if e.costly})
    all_costly = sorted(n for n in defined if bucket_bytes[n] >= min_bytes)
    return {
        "date": date,
        "channel": channel.name,
        "channel_column": channel.column,
        "channel_kind": channel.kind,
        "n_undefined_buckets": len(bucket_bytes) - len(defined),
        "stitch": stitch.as_dict() if stitch is not None else None,
        "stitch_applied": stitch_applies(channel, stitch),
        "n_wide_buckets": sum(1 for v in spans.values() if v != interval_s),
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
        "n_buckets": len(defined),
        "n_costly_buckets": len(all_costly),
        "n_costly_buckets_with_a_named_fire": len(costly_buckets),
        "costly_buckets_without_a_named_fire":
            [n for n in all_costly if n not in set(costly_buckets)],
        "total_cost_bytes": sum(bucket_bytes[n] for n in all_costly),
        "by_unit": by_unit,
        "entries": [e.as_dict() for e in entries],
        "unclassified": unclassified,
    }


# --------------------------------------------------- attribution evidence

# Round 406. `cost_ledger`'s `sole_attributable` flag means exactly one named
# unit STARTED in a bucket that moved more than `LEDGER_MIN_BYTES`. Round 400
# read that flag as a licence for the sentence "unit X cost this", and named
# `fwupd-refresh` at 2026-08-31T01:57:33Z the only sole-attributable event of
# the boot -- 67.68 MB, inherited from round 394, which had a sample of ONE.
#
# The flag cannot support that sentence, because it has no denominator.
# `fwupd-refresh` fired **36 times** across the same boot and **33 of those 36
# buckets moved zero bytes**; on sa30 alone it fired 23 times for 23 zeroes and
# not one costly bucket. A unit whose own modal cost, measured 36 times, is
# nothing is not the explanation for a 67 MB step -- and one that occupies 36
# of the boot's 218 buckets is within 10 minutes of 16.5% of everything that
# ever happens on this box, so being "the only name in the bucket" is what
# chance looks like for it, not evidence.
#
# This function is the missing denominator. It pools one or more per-day
# ledgers and asks, of each unit, the three questions the flag skips:
#
#   1. CONSISTENCY -- of this unit's own fires, what fraction cost anything?
#      Attribution claims a cause, and a cause absent from the majority of its
#      own occurrences is not the cause; something else is separating the
#      expensive fires from the free ones, and that something is unmeasured.
#   2. CHANCE -- given that the unit occupies `n_distinct` of `N` buckets, how
#      often would a unit placed at random cover this many of the `K` costly
#      ones? Hypergeometric, then Bonferroni over every unit in the ledger,
#      because the unit under test was CHOSEN by having been noticed.
#   3. SEPARABILITY -- how many of its costly buckets does it hold alone? A
#      hit shared with four other units carries no attributional information;
#      that is round 400's own finding about the 04:00:03 bucket, applied to
#      the one entry round 400 exempted from it.
#
# It deliberately cannot return "supported" from a single fire. One
# observation has no within-unit replication, which is precisely the state
# round 394 was in when the 67.7 MB attribution was first written down.

ATTRIBUTION_MAX_FAMILY_P = 0.05      # conventional, and Bonferroni-corrected
ATTRIBUTION_MIN_CONSISTENCY = 0.5    # a cause absent from most of its own
                                     # occurrences is not the cause; 0.5 is the
                                     # weakest line that can be defended at all
ATTRIBUTION_MIN_FIRES = 2            # below this there is no replication


def _hypergeom_atleast(N: int, K: int, n: int, h: int) -> float:
    """P(a uniformly random n-subset of N buckets covers >= h of the K costly).

    Exact, via `math.comb` -- the numbers here are tiny (N <= a few hundred)
    and an exact tail beats a normal approximation that would be wrong in
    exactly the small-K regime this box lives in (K is 1, 2 or 3 per day).
    """
    if n < 0 or h < 0 or K < 0 or n > N or K > N:
        raise PerturbationError("hypergeometric arguments out of range")
    if h <= 0:
        return 1.0
    lo, hi = h, min(K, n)
    if lo > hi:
        return 0.0
    return sum(math.comb(K, i) * math.comb(N - K, n - i)
               for i in range(lo, hi + 1)) / math.comb(N, n)


def best_case_p(N: int, K: int, d: int) -> float:
    """The SMALLEST `p_chance` a unit of occupancy `d` can possibly attain.

    Its best outcome is covering every costly bucket it could -- `min(K, d)`
    of them. Nothing it does can produce a smaller tail than that, so this is
    the arithmetic ceiling on how much evidence the record can carry about
    that unit, before any observation is made.
    """
    return _hypergeom_atleast(N, K, d, min(K, d))


def power_floor(N: int, K: int, n_units_tested: int,
                max_family_p: float = ATTRIBUTION_MAX_FAMILY_P) -> dict:
    """Which occupancies could EVER be graded `supported` in a record of this
    shape -- computed from (N, K, n_units_tested) alone, before any data.

    Round 412. Round 406 ran `attribution_evidence` over the whole boot,
    reported `supported: []`, and wrote "this instrument, over this record,
    licenses no causal claim at all". That sentence reads as a fact about the
    box. It is at least partly a fact about the arithmetic, and nothing in the
    output separated the two.

    The separation is cheap. Bonferroni over `n_units_tested` units puts the
    per-unit bar at `max_family_p / n_units_tested`. A unit of occupancy `d`
    cannot beat `best_case_p(N, K, d)`. If that exceeds the bar, the unit is
    UNTESTABLE: no arrangement of its fires could have been supported, and
    "not supported" says nothing about it.

    Two consequences worth stating because both surprised me:

    * The testable set is NOT an interval starting at 1. `d = 1` is untestable
      whenever `K * n_units_tested / N > max_family_p`, while `d = 2` may be
      testable, because covering 2 of K by chance is much rarer than covering
      1. Occupancy that is too LOW is as fatal as occupancy that is too high.
    * When `K` is small enough the testable set is EMPTY and the instrument
      has no power at all. On this box, `K = 1` with 16 units and N = 218
      gives `min_p = 1/218 = 0.00459`, and `0.00459 * 16 = 0.073 > 0.05`:
      a record with a single costly bucket can never support anything,
      whatever happens in it.
    """
    if N <= 0:
        raise PerturbationError("power_floor needs N > 0")
    if not 0 <= K <= N:
        raise PerturbationError("power_floor needs 0 <= K <= N")
    if n_units_tested <= 0:
        raise PerturbationError("power_floor needs n_units_tested > 0")
    bar = max_family_p / n_units_tested
    testable = [d for d in range(1, N + 1) if best_case_p(N, K, d) <= bar]
    return {
        "n_buckets": N,
        "n_costly_buckets": K,
        "n_units_tested": n_units_tested,
        "max_family_p": max_family_p,
        "per_unit_bar": bar,
        "any_testable": bool(testable),
        "min_testable_occupancy": testable[0] if testable else None,
        "max_testable_occupancy": testable[-1] if testable else None,
        "n_testable_occupancies": len(testable),
        "testable_fraction_of_N": len(testable) / N,
        "best_p_at_occupancy_1": best_case_p(N, K, 1),
        "why": ("no occupancy can clear the Bonferroni bar: this record "
                "cannot support any attribution, whatever it contains"
                if not testable else
                f"occupancies {testable[0]}..{testable[-1]} can clear the bar "
                f"(contiguous)" if testable[-1] - testable[0] + 1 == len(testable)
                else f"{len(testable)} occupancies in [{testable[0]}, "
                     f"{testable[-1]}] can clear the bar"),
    }


@dataclass(frozen=True)
class AttributionEvidence:
    """Whether a ledger licenses "unit X cost this", and why or why not."""
    unit: str
    n_fires: int
    n_distinct_buckets: int
    n_costly: int
    n_costly_distinct: int
    n_clean: int                 # costly buckets this unit holds ALONE
    n_zero_byte: int             # its fires whose bucket moved nothing
    max_bucket_bytes: int
    n_buckets: int
    n_costly_buckets: int
    occupancy: float             # n_distinct_buckets / n_buckets
    consistency: float           # n_costly / n_fires
    p_chance: float
    n_units_tested: int
    p_family: float
    p_best: float                # the smallest p this occupancy could attain
    testable: bool               # could ANY outcome have supported this unit?
    verdict: str
    why: str

    def as_dict(self) -> dict:
        return asdict(self)


def attribution_evidence(ledgers: Iterable,
                         max_family_p: float = ATTRIBUTION_MAX_FAMILY_P,
                         min_consistency: float = ATTRIBUTION_MIN_CONSISTENCY,
                         min_fires: int = ATTRIBUTION_MIN_FIRES) -> dict:
    """Pool `cost_ledger` results and grade every unit's attribution claim.

    `ledgers` is one or more dicts as returned by `cost_ledger` -- typically
    one per sar day-file, since `sar` writes one file per day and the costly
    threshold is a property of the boot, not the day. Pooling is the point:
    sa30 contributes 23 free `fwupd-refresh` fires that sa31 alone cannot see,
    and those 23 are the whole refutation.

    Buckets are pooled by `(date, bucket_end)` so two days' `02:00:05` are two
    buckets, not one.
    """
    ledgers = list(ledgers)
    if not ledgers:
        raise PerturbationError("attribution_evidence needs at least one ledger")

    N = sum(int(l["n_buckets"]) for l in ledgers)
    K = sum(int(l["n_costly_buckets"]) for l in ledgers)

    agg: dict = {}
    for l in ledgers:
        date = l.get("date") or ""
        for e in l["entries"]:
            u = agg.setdefault(e["unit"], {
                "n_fires": 0, "n_costly": 0, "n_zero_byte": 0, "n_clean": 0,
                "max_bytes": 0, "buckets": set(), "costly_buckets": set()})
            key = (date, e["bucket_end"])
            # `bucket_swapped_bytes` is the round 400-406 name; ledgers written
            # under it are on disk, so the rename must not orphan them.
            byts = int(e["bucket_bytes"] if "bucket_bytes" in e
                       else e["bucket_swapped_bytes"])
            u["n_fires"] += 1
            u["buckets"].add(key)
            u["max_bytes"] = max(u["max_bytes"], byts)
            if byts == 0:
                u["n_zero_byte"] += 1
            if e["costly"]:
                u["n_costly"] += 1
                u["costly_buckets"].add(key)
                if int(e["bucket_shared_by"]) == 1:
                    u["n_clean"] += 1

    n_tested = len(agg)
    out = []
    for unit, u in agg.items():
        n_distinct = len(u["buckets"])
        n_costly_distinct = len(u["costly_buckets"])
        p_chance = _hypergeom_atleast(N, K, n_distinct, n_costly_distinct)
        p_family = min(1.0, p_chance * n_tested)
        p_best = best_case_p(N, K, n_distinct)
        testable = p_best * n_tested <= max_family_p
        consistency = u["n_costly"] / u["n_fires"] if u["n_fires"] else 0.0

        if u["n_fires"] < min_fires:
            verdict, why = "insufficient-data", (
                f"{u['n_fires']} fire(s): no within-unit replication, so a cost "
                f"and a coincidence are indistinguishable")
        elif u["n_costly"] == 0:
            verdict, why = "no-evidence", "never fired into a costly bucket"
        elif u["n_clean"] == 0:
            verdict, why = "shared-only", (
                f"all {u['n_costly']} costly hit(s) shared the bucket with "
                f"another unit; nothing separates them")
        elif not testable:
            verdict, why = "untestable", (
                f"occupies {n_distinct}/{N} buckets against {K} costly one(s); "
                f"the best p this occupancy can attain is {p_best:.4g} "
                f"({p_best * n_tested:.4g} over {n_tested} units), so NO "
                f"outcome could have been supported -- this is a fact about "
                f"the record's shape, not about the unit")
        elif p_family > max_family_p:
            verdict, why = "coincidence", (
                f"occupies {n_distinct}/{N} buckets, so covering "
                f"{n_costly_distinct} of {K} costly ones happens by chance with "
                f"p={p_chance:.4f} (p={p_family:.4f} over {n_tested} units)")
        elif consistency < min_consistency:
            verdict, why = "coincidence", (
                f"only {u['n_costly']} of its own {u['n_fires']} fires cost "
                f"anything ({consistency:.1%}); {u['n_zero_byte']} moved zero "
                f"bytes, so the unit alone does not determine the cost")
        else:
            verdict, why = "supported", (
                f"{u['n_costly']} of {u['n_fires']} fires costly "
                f"({consistency:.1%}), {u['n_clean']} in a bucket it holds "
                f"alone, p={p_family:.4f}")

        out.append(AttributionEvidence(
            unit=unit, n_fires=u["n_fires"], n_distinct_buckets=n_distinct,
            n_costly=u["n_costly"], n_costly_distinct=n_costly_distinct,
            n_clean=u["n_clean"], n_zero_byte=u["n_zero_byte"],
            max_bucket_bytes=u["max_bytes"], n_buckets=N, n_costly_buckets=K,
            occupancy=n_distinct / N if N else 0.0, consistency=consistency,
            p_chance=p_chance, n_units_tested=n_tested, p_family=p_family,
            p_best=p_best, testable=testable,
            verdict=verdict, why=why))

    out.sort(key=lambda e: (-e.n_fires, e.unit))
    by_verdict: dict = {}
    for e in out:
        by_verdict[e.verdict] = by_verdict.get(e.verdict, 0) + 1
    floor = power_floor(N, K, n_tested, max_family_p)
    n_testable = sum(1 for e in out if e.testable)
    return {
        "dates": [l.get("date") for l in ledgers],
        "channels": sorted({l.get("channel", "swap") for l in ledgers}),
        "n_buckets": N,
        "n_costly_buckets": K,
        "power": floor,
        "n_testable_units": n_testable,
        "untestable_units": sorted(e.unit for e in out if not e.testable),
        # The single most important field here. `supported: []` from a run
        # where this is False is not a result.
        "supported_was_reachable": n_testable > 0,
        "n_units_tested": n_tested,
        "max_family_p": max_family_p,
        "min_consistency": min_consistency,
        "min_fires": min_fires,
        "by_verdict": by_verdict,
        "supported": sorted(e.unit for e in out if e.verdict == "supported"),
        "units": [e.as_dict() for e in out],
    }


def auto_stitches(tables: Iterable, interval_s: int = SAR_INTERVAL_S,
                  max_span_s: int = STITCH_MAX_SPAN_S) -> dict:
    """{date: Stitch} for every day-file whose PREDECESSOR is also present.

    Refusals are swallowed here and only here, because "these two days cannot
    be joined" is the normal case for a nine-day capture with holes in it --
    but the reason is kept, so a caller can print why a day was not stitched
    rather than wondering whether it tried."""
    tables = sorted(list(tables), key=lambda td: td[1])
    out = {}
    for (pt, pd), (nt, nd) in zip(tables, tables[1:]):
        try:
            out[nd] = stitch_from(pt, pd, nt, nd, interval_s, max_span_s)
        except PerturbationError as exc:
            out[nd] = str(exc)
    return out


def channel_sweep(fires: Iterable, tables: Iterable, channel: Channel,
                  thresholds: Iterable,
                  interval_s: int = SAR_INTERVAL_S,
                  max_family_p: float = ATTRIBUTION_MAX_FAMILY_P,
                  exclude_units: Iterable = LEDGER_EXCLUDE_UNITS,
                  stitch: bool = False) -> list:
    """Re-grade the whole record at each costly-threshold, and report the
    verdict AS A FUNCTION of it.

    Round 412. `LEDGER_MIN_BYTES` on the swap channel is derived from two
    labelled events. On any other channel there is no such pair, so the
    threshold is a CHOICE -- and a verdict that moves with an unpinned choice
    is not a verdict, it is a setting. This runs the choice out over a range
    and shows what survives it.

    `tables` is an iterable of `(SarTable, date)`, one per sar day-file.
    """
    tables = list(tables)
    stitches = auto_stitches(tables, interval_s) if stitch else {}
    out = []
    for mb in thresholds:
        ledgers = [cost_ledger(fires, t, date, interval_s, min_bytes=int(mb),
                               exclude_units=exclude_units, channel=channel,
                               stitch=(stitches.get(date)
                                       if isinstance(stitches.get(date), Stitch)
                                       else None))
                   for t, date in tables]
        try:
            ev = attribution_evidence(ledgers, max_family_p=max_family_p)
        except PerturbationError:
            continue
        out.append({
            "channel": channel.name,
            "min_bytes": int(mb),
            "stitched_days": sorted(d for d, v in stitches.items()
                                    if isinstance(v, Stitch)),
            "unstitchable_days": {d: v for d, v in stitches.items()
                                  if not isinstance(v, Stitch)},
            "n_buckets": ev["n_buckets"],
            "n_costly_buckets": ev["n_costly_buckets"],
            "n_units_tested": ev["n_units_tested"],
            "max_testable_occupancy": ev["power"]["max_testable_occupancy"],
            "min_testable_occupancy": ev["power"]["min_testable_occupancy"],
            "n_testable_units": ev["n_testable_units"],
            "supported_was_reachable": ev["supported_was_reachable"],
            "supported": ev["supported"],
            "by_verdict": ev["by_verdict"],
        })
    return out


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


# --------------------------------------------------- round 430: the window

# Every ledger, evidence, sweep and power-floor number this program published
# before round 430 was computed on TWO of the nine banked sar day-files, and on
# a journal covering ONE boot. Round 412 found the second half of that ("the
# journal, not `sar`, bounds attribution"); round 424 banked a journal covering
# the whole retention window, which is what makes a wide run possible at all.
#
# Widening is not free, and its risk points the wrong way. `attribution_evidence`
# pools N over its ledgers and tests each unit's d costly hits against a
# hypergeometric null on (N, K, n_distinct). A day whose sar table is present
# but whose journal is SILENT contributes buckets to N and fires to nothing.
# N rises, the null gets more diffuse, and every surviving unit's `p_chance`
# FALLS -- so pooling an unpaired day makes an attribution look MORE
# significant on strictly less evidence. Widening a window is therefore a
# false-POSITIVE hazard, not the conservative move it looks like, and the
# pairing has to be established before the pooling, not after.
#
# `skills/elimination-needs-its-frame/SKILL.md` (round 429) is the rule and
# this is the first instrument built to it. The candidate set of day-files is
# derived from the capture's OWN section headers; each day's date is read from
# that section's OWN `Linux ...` banner rather than from the `SA<DD>` filename;
# and the two are reconciled, so a banner/name disagreement raises instead of
# silently booking a day of buckets against the wrong date.

_SECTION_HEAD = re.compile(r"^###\s+(\S+)\s*$")
_BANNER_DATE = re.compile(r"^Linux\s+\S+\s+\(\S+\)\s+(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
_SECTION_DAY = re.compile(r"^SAR_[A-Z]+_SA(\d{2})$")

# Which `sar` invocation each Channel's column comes out of. The capture banks
# one section per (invocation, day); a channel that names no section cannot be
# run over a window at all, and saying so beats a KeyError.
CHANNEL_SECTION_PREFIX = {"swap": "SAR_W_", "commit": "SAR_R_", "steal": "SAR_B_"}

# Pooling verdicts. `sar-only` is the dangerous one -- see the note above.
PAIRING_PAIRED = "paired"
PAIRING_SAR_ONLY = "sar-only"
PAIRING_JOURNAL_ONLY = "journal-only"


def sar_sections(text: str) -> dict:
    """`### NAME` -> body, over a capture's `sar-all.txt`.

    Lived in `nuc/tests/test_perturbation.py` as `_sar_sections` from round 418
    to round 429: three rounds of analysis reached the banked day-files only
    through a test helper, which is why nine days of data sat unused behind a
    CLI that takes one `--sar-w FILE` at a time."""
    secs: dict = {}
    cur = None
    for line in text.splitlines():
        m = _SECTION_HEAD.match(line)
        if m:
            cur = m.group(1)
            secs[cur] = []
        elif cur is not None:
            secs[cur].append(line)
    return {k: "\n".join(v) for k, v in secs.items()}


def sar_banner_date(section_text: str) -> str:
    """The `MM/DD/YY` in a sar table's own banner, as `YYYY-MM-DD`.

    This is the honest source for a day-file's date. The alternative -- reading
    `31` out of the section name `SAR_W_SA31` -- gives a day of month and no
    month or year, and `capture_manifest.journal_span_coverage` had to join on
    day-of-month for exactly that reason. The banner carries all three."""
    for line in section_text.splitlines():
        m = _BANNER_DATE.match(line.strip())
        if m:
            mm, dd, yy = m.groups()
            year = int(yy) if len(yy) == 4 else 2000 + int(yy)
            return f"{year:04d}-{int(mm):02d}-{int(dd):02d}"
    raise PerturbationError(
        "no `Linux ... MM/DD/YY` banner in this section; a sar table without "
        "its banner cannot be dated and must not be pooled")


@dataclass(frozen=True)
class WindowDay:
    """One day-file's place in the window, and whether it may be pooled."""
    date: str
    section: str
    n_rows: int
    n_restarts: int
    first_sample: str
    last_sample: str
    n_fires: int
    n_fires_excluded: int
    pairing: str
    why: str

    def as_dict(self) -> dict:
        return asdict(self)


def window_frame(sar_text: str, journal_text: str,
                 channel: Channel = SWAP_CHANNEL,
                 exclude_units: Iterable = LEDGER_EXCLUDE_UNITS) -> dict:
    """Enumerate the capture's day-files and pair each against the journal.

    Returns the FRAME, not the answer: which days exist, where each date came
    from, how many unit fires the journal holds on that date, and which days
    are therefore poolable. `n_buckets_if_unpaired_pooled` is reported so the
    size of the hazard is visible even when the hazard is avoided.
    """
    prefix = CHANNEL_SECTION_PREFIX.get(channel.name)
    if prefix is None:
        raise PerturbationError(
            f"channel {channel.name!r} names no sar section prefix; have "
            f"{sorted(CHANNEL_SECTION_PREFIX)}")
    secs = sar_sections(sar_text)
    fires = parse_unit_starts(journal_text)
    excluded = tuple(exclude_units)

    per_date_fires: dict = {}
    per_date_excluded: dict = {}
    for f in fires:
        d = f.at_utc[:10]
        if any(f.label.startswith(x) for x in excluded):
            per_date_excluded[d] = per_date_excluded.get(d, 0) + 1
        else:
            per_date_fires[d] = per_date_fires.get(d, 0) + 1

    days = []
    seen_dates = set()
    for name in sorted(s for s in secs if s.startswith(prefix)):
        body = secs[name]
        date = sar_banner_date(body)
        dm = _SECTION_DAY.match(name)
        if dm and int(dm.group(1)) != int(date[8:10]):
            raise PerturbationError(
                f"section {name} banners {date}: the file name says day "
                f"{dm.group(1)} and the table says day {date[8:10]}")
        table = parse_sar(body)
        n_fires = per_date_fires.get(date, 0)
        n_exc = per_date_excluded.get(date, 0)
        if n_fires > 0:
            pairing, why = PAIRING_PAIRED, (
                f"{n_fires} non-instrument unit start(s) in the journal on "
                f"{date}; buckets and fires come from the same day")
        else:
            pairing, why = PAIRING_SAR_ONLY, (
                f"{len(table.rows)} bucket(s) but ZERO non-instrument unit "
                f"starts on {date} ({n_exc} instrument fire(s) excluded); "
                f"pooling this day would raise N and lower every unit's p")
        seen_dates.add(date)
        days.append(WindowDay(
            date=date, section=name, n_rows=len(table.rows),
            n_restarts=sum(1 for r in table.rows if r.restart_before),
            first_sample=table.rows[0].time if table.rows else "",
            last_sample=table.rows[-1].time if table.rows else "",
            n_fires=n_fires, n_fires_excluded=n_exc,
            pairing=pairing, why=why))

    for date in sorted(set(per_date_fires) - seen_dates):
        days.append(WindowDay(
            date=date, section="", n_rows=0, n_restarts=0,
            first_sample="", last_sample="",
            n_fires=per_date_fires[date],
            n_fires_excluded=per_date_excluded.get(date, 0),
            pairing=PAIRING_JOURNAL_ONLY,
            why=(f"{per_date_fires[date]} unit start(s) on {date} with no "
                 f"{prefix}* section; those fires can never be costed")))

    days.sort(key=lambda d: (d.date, d.section))
    paired = [d for d in days if d.pairing == PAIRING_PAIRED]
    sar_only = [d for d in days if d.pairing == PAIRING_SAR_ONLY]
    jrnl_only = [d for d in days if d.pairing == PAIRING_JOURNAL_ONLY]
    stamps = [f.at_utc for f in fires]
    return {
        "channel": channel.name,
        "section_prefix": prefix,
        "date_source": "each section's own `Linux ...` banner",
        "n_sections_total": len(secs),
        "n_day_files": len(days) - len(jrnl_only),
        "journal_first_event_utc": min(stamps) if stamps else None,
        "journal_last_event_utc": max(stamps) if stamps else None,
        "n_journal_fires": len(fires),
        "n_journal_fires_excluded": sum(per_date_excluded.values()),
        "excluded_units": sorted(excluded),
        "n_paired": len(paired),
        "n_sar_only": len(sar_only),
        "n_journal_only": len(jrnl_only),
        "poolable_dates": [d.date for d in paired],
        "dropped_dates": [d.date for d in sar_only],
        "n_buckets_poolable": sum(d.n_rows for d in paired),
        "n_buckets_if_unpaired_pooled": sum(d.n_rows for d in paired + sar_only),
        "days": [d.as_dict() for d in days],
    }


def window_attribution(sar_text: str, journal_text: str,
                       channel: Channel = SWAP_CHANNEL,
                       min_bytes=_UNSET,
                       interval_s: int = SAR_INTERVAL_S,
                       exclude_units: Iterable = LEDGER_EXCLUDE_UNITS,
                       stitch: bool = False,
                       include_unpaired: bool = False,
                       max_family_p: float = ATTRIBUTION_MAX_FAMILY_P,
                       min_consistency: float = ATTRIBUTION_MIN_CONSISTENCY) -> dict:
    """Pooled attribution over every poolable day-file in one capture.

    The whole of `cost_ledger` -> `attribution_evidence` -> `power_floor`, run
    over a window instead of over the two day-files somebody happened to pass
    on the command line. `frame` rides beside the verdict and names every day
    that was dropped and why; `include_unpaired` exists so the hazard can be
    MEASURED (run it both ways and compare `p_family`), not so it can be
    switched off.
    """
    frame = window_frame(sar_text, journal_text, channel, exclude_units)
    secs = sar_sections(sar_text)
    fires = parse_unit_starts(journal_text)

    use = [d for d in frame["days"]
           if d["pairing"] == PAIRING_PAIRED
           or (include_unpaired and d["pairing"] == PAIRING_SAR_ONLY)]
    if not use:
        raise PerturbationError(
            "no poolable day-file: every sar day is unpaired with the journal")
    tables = [(parse_sar(secs[d["section"]]), d["date"]) for d in use]
    stitches = auto_stitches(tables, interval_s) if stitch else {}
    ledgers = [cost_ledger(fires, t, date, interval_s, min_bytes=min_bytes,
                           exclude_units=exclude_units, channel=channel,
                           stitch=(stitches.get(date)
                                   if isinstance(stitches.get(date), Stitch)
                                   else None))
               for t, date in tables]
    ev = attribution_evidence(ledgers, max_family_p=max_family_p,
                              min_consistency=min_consistency)
    frame["include_unpaired"] = include_unpaired
    frame["stitched_days"] = sorted(d for d, v in stitches.items()
                                    if isinstance(v, Stitch))
    frame["unstitchable_days"] = {d: v for d, v in stitches.items()
                                  if not isinstance(v, Stitch)}
    return {
        "frame": frame,
        "evidence": ev,
        "gates": verdict_floor(ev),
        "cofires": costly_bucket_cofires(ledgers),
        "clusters": cluster_evidence(ledgers, max_family_p=max_family_p,
                                     min_consistency=min_consistency),
        "per_day": [{"date": l["date"],
                     "n_buckets": l["n_buckets"],
                     "n_costly_buckets": l["n_costly_buckets"],
                     "n_fires": l["n_fires"],
                     "n_unclassified": l["n_unclassified"],
                     "n_undefined_buckets": l["n_undefined_buckets"],
                     "total_cost_bytes": l["total_cost_bytes"],
                     "min_bytes": l["min_bytes"]}
                    for l in ledgers],
    }


def unpaired_inflation(sar_text: str, journal_text: str,
                       channel: Channel = SWAP_CHANNEL,
                       min_bytes=_UNSET, **kw) -> dict:
    """Run the window both ways and report what the unpaired days did to p.

    The point of this function is that it can come back EMPTY. If a capture has
    no `sar-only` day, the hazard is not present and `delta` is all zeros --
    which is itself the thing to publish, because it says the wide number was
    not bought with an inflated denominator.
    """
    tight = window_attribution(sar_text, journal_text, channel, min_bytes,
                               include_unpaired=False, **kw)
    try:
        wide = window_attribution(sar_text, journal_text, channel, min_bytes,
                                  include_unpaired=True, **kw)
    except PerturbationError as exc:
        return {"comparable": False, "why": str(exc)}
    t_units = {u["unit"]: u for u in tight["evidence"]["units"]}
    w_units = {u["unit"]: u for u in wide["evidence"]["units"]}
    moved = []
    for unit in sorted(set(t_units) & set(w_units)):
        a, b = t_units[unit], w_units[unit]
        if a["p_family"] != b["p_family"] or a["verdict"] != b["verdict"]:
            moved.append({"unit": unit,
                          "p_family_paired": a["p_family"],
                          "p_family_with_unpaired": b["p_family"],
                          "verdict_paired": a["verdict"],
                          "verdict_with_unpaired": b["verdict"]})
    return {
        "comparable": True,
        "n_dropped_days": tight["frame"]["n_sar_only"],
        "dropped_dates": tight["frame"]["dropped_dates"],
        "n_buckets_paired": tight["evidence"]["n_buckets"],
        "n_buckets_with_unpaired": wide["evidence"]["n_buckets"],
        "n_costly_paired": tight["evidence"]["n_costly_buckets"],
        "n_costly_with_unpaired": wide["evidence"]["n_costly_buckets"],
        "supported_paired": tight["evidence"]["supported"],
        "supported_with_unpaired": wide["evidence"]["supported"],
        "units_whose_p_moved": moved,
    }


# ------------------------------------- round 430: the other two gates

# Round 412 built `power_floor` because round 406 published `supported: []`
# without checking whether `supported` was reachable. `power_floor` answers
# that for the CHANCE gate: which occupancies could ever clear a Bonferroni
# bar. `attribution_evidence` has SIX gates and a unit must pass all of them:
#
#     1 min_fires     >= 2 fires, or a cost and a coincidence are the same thing
#     2 any_costly    >= 1 fire into a costly bucket
#     3 separable     >= 1 costly bucket the unit holds ALONE   <-- unmodelled
#     4 testable      power_floor's gate                        <-- modelled
#     5 chance        p_family <= max_family_p
#     6 consistency   >= min_consistency of its own fires cost   <-- unmodelled
#
# So `supported_was_reachable: True` has meant "gate 4 was reachable" while
# being read as "a supported verdict was reachable", which is a strictly
# stronger claim and the one a reader takes away. On the round-424 capture's
# full window it is exactly wrong: seventeen units are testable, four clear
# the chance gate at p_family down to 5.3e-06, and the three gate-sets are
# DISJOINT -- the units that fire alone fire hourly, and the units that are
# surprising never fire alone. `supported: []` was structurally guaranteed
# before any p was computed.
#
# `verdict_floor` reports the gates as SETS and intersects them. An empty
# intersection is a fact about the record, publishable on its own, and it is
# a different fact from "no unit happened to pass".

SUPPORT_GATES = ("min_fires", "any_costly", "separable", "testable",
                 "chance", "consistency")


def verdict_floor(evidence: dict) -> dict:
    """Per-gate pass sets over an `attribution_evidence` result, and their AND.

    Takes the evidence dict rather than the ledgers so it re-reads exactly the
    numbers that produced the verdicts -- a second derivation from the same
    inputs would be a second chance to disagree with the thing it is auditing.
    """
    units = evidence["units"]
    max_family_p = evidence["max_family_p"]
    min_consistency = evidence["min_consistency"]
    min_fires = evidence["min_fires"]

    def passes(u: dict) -> dict:
        return {
            "min_fires": u["n_fires"] >= min_fires,
            "any_costly": u["n_costly"] > 0,
            "separable": u["n_clean"] > 0,
            "testable": bool(u["testable"]),
            "chance": u["p_family"] <= max_family_p,
            "consistency": u["consistency"] >= min_consistency,
        }

    by_gate = {g: [] for g in SUPPORT_GATES}
    per_unit = []
    for u in units:
        gp = passes(u)
        for g, ok in gp.items():
            if ok:
                by_gate[g].append(u["unit"])
        failed = [g for g in SUPPORT_GATES if not gp[g]]
        per_unit.append({
            "unit": u["unit"], "verdict": u["verdict"],
            "gates_passed": [g for g in SUPPORT_GATES if gp[g]],
            "gates_failed": failed,
            "first_gate_failed": failed[0] if failed else None,
            "n_gates_failed": len(failed),
        })

    survivors = set(u["unit"] for u in units)
    for g in SUPPORT_GATES:
        survivors &= set(by_gate[g])
    # Which single gate, removed, would let somebody through -- the cheapest
    # honest statement of "what would have to change".
    near = {}
    for g in SUPPORT_GATES:
        s = set(u["unit"] for u in units)
        for h in SUPPORT_GATES:
            if h != g:
                s &= set(by_gate[h])
        if s:
            near[g] = sorted(s)
    return {
        "gates": list(SUPPORT_GATES),
        "n_units": len(units),
        "pass_counts": {g: len(by_gate[g]) for g in SUPPORT_GATES},
        "pass_sets": {g: sorted(by_gate[g]) for g in SUPPORT_GATES},
        "all_gates_passed": sorted(survivors),
        "supported_reachable_all_gates": bool(survivors),
        "single_gate_from_supported": near,
        "blocking_gate_histogram": _hist(
            p["first_gate_failed"] for p in per_unit),
        "per_unit": per_unit,
        "why": (
            "`supported` is empty because the gate sets do not intersect"
            if not survivors else
            "at least one unit clears every gate"),
    }


def _hist(items) -> dict:
    out: dict = {}
    for i in items:
        if i is not None:
            out[i] = out.get(i, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def costly_bucket_cofires(ledgers: Iterable, min_bytes=None) -> dict:
    """Who shares each costly bucket, and which units are never seen apart.

    `shared-only` reports a fact about a UNIT; the fact is really about a PAIR.
    `packagekit` is not unattributable in general -- it is unattributable
    *from* `apt-daily`, because on this box `apt-daily` starts it. Naming the
    confounder converts "nothing separates them" into a statement about what a
    future window would have to contain in order to separate them, which is
    the only form of the claim a next round can act on.
    """
    ledgers = list(ledgers)
    buckets: dict = {}
    occupancy: dict = {}
    for l in ledgers:
        date = l.get("date") or ""
        for e in l["entries"]:
            key = (date, e["bucket_end"])
            occupancy.setdefault(e["unit"], set()).add(key)
            if e["costly"]:
                b = buckets.setdefault(key, {
                    "date": date, "bucket_end": e["bucket_end"],
                    "bytes": int(e.get("bucket_bytes",
                                       e.get("bucket_swapped_bytes", 0))),
                    "units": set()})
                b["units"].add(e["unit"])

    costly_of: dict = {}
    for key, b in buckets.items():
        for u in b["units"]:
            costly_of.setdefault(u, set()).add(key)

    never_without: dict = {}
    for u, keys in costly_of.items():
        companions = None
        for k in keys:
            others = buckets[k]["units"] - {u}
            companions = others if companions is None else (companions & others)
        never_without[u] = sorted(companions or ())

    rows = [{"date": b["date"], "bucket_end": b["bucket_end"],
             "bytes": b["bytes"], "n_units": len(b["units"]),
             "units": sorted(b["units"])}
            for b in buckets.values()]
    rows.sort(key=lambda r: (r["date"], r["bucket_end"]))
    # The load-bearing asymmetry. `u` never without `v` while `v` IS seen
    # without `u` means merging them into one hypothesis does not make either
    # sole: the pair is confounded in one direction only, so `u`'s cost is
    # unattributable AND `v`'s attribution is not rescued by absorbing `u`.
    # On the round-424 window this is exactly the apt trio against
    # `packagekit`, and it is why `cluster_evidence` still returns
    # `shared-only` after merging the class the record does say is mutual.
    one_way = {u: [v for v in vs if u not in never_without.get(v, ())]
               for u, vs in never_without.items()}
    return {
        "n_costly_buckets_with_a_named_fire": len(rows),
        "one_way_confounders": {u: v for u, v in sorted(one_way.items()) if v},
        "n_sole_occupied": sum(1 for r in rows if r["n_units"] == 1),
        "max_units_in_one_bucket": max((r["n_units"] for r in rows), default=0),
        "never_without": {u: v for u, v in sorted(never_without.items()) if v},
        "sole_occupants": sorted({r["units"][0] for r in rows
                                  if r["n_units"] == 1}),
        "buckets": rows,
    }


# ------------------------------------- round 430: testing what IS separable

# Nine days of data get three units past the chance gate and none past the
# separability gate, because `apt-daily` STARTS `apt-news`, `esm-cache` and
# `packagekit` and the four are never in a costly bucket apart. That is not a
# measurement failure to be worked around; it is the deployment's actual
# causal structure, and `sar`'s 600 s bucket is far too coarse to resolve it.
#
# The hypothesis the record CAN carry is the composite one: "the apt cluster
# costs", not "packagekit costs". `inseparable_classes` derives the clusters
# from the co-firing structure -- never from which grouping would pass --
# and `cluster_evidence` relabels every member to its cluster and re-runs the
# same grader. Two things move and both are honest: the union occupies more
# buckets (a bigger n, which HURTS), and there are fewer hypotheses, so the
# Bonferroni bar loosens (which helps). Nothing else changes.
#
# The trap, and it is why `min_costly_buckets` defaults to 2: a unit with ONE
# costly bucket is "never without" everything else in that bucket, so the four
# boot-time units that share the 08-30 restart bucket look like a perfect
# cluster on a single observation. A class needs two distinct costly buckets
# before "they always co-occur" is a claim rather than a restatement.

CLUSTER_MIN_COSTLY_BUCKETS = 2


def inseparable_classes(cofires: dict,
                        min_costly_buckets: int = CLUSTER_MIN_COSTLY_BUCKETS
                        ) -> list:
    """Connected components of the MUTUAL never-without relation.

    `never_without[u]` containing `v` says every costly bucket holding `u`
    also holds `v`. That alone is one-directional -- `v` may fire in costly
    buckets `u` is absent from -- so it is the symmetric closure that means
    "this record cannot tell these two apart", and only that is merged.
    """
    nw = cofires["never_without"]
    costly_of: dict = {}
    for b in cofires["buckets"]:
        for u in b["units"]:
            costly_of.setdefault(u, set()).add((b["date"], b["bucket_end"]))

    adj: dict = {}
    for u, others in nw.items():
        for v in others:
            if u in nw.get(v, ()):
                adj.setdefault(u, set()).add(v)
                adj.setdefault(v, set()).add(u)

    seen, classes = set(), []
    for u in sorted(adj):
        if u in seen:
            continue
        stack, comp = [u], set()
        while stack:
            x = stack.pop()
            if x in comp:
                continue
            comp.add(x)
            stack.extend(adj.get(x, ()))
        seen |= comp
        union = set()
        for m in comp:
            union |= costly_of.get(m, set())
        classes.append({
            "label": "+".join(sorted(comp)),
            "members": sorted(comp),
            "n_members": len(comp),
            "n_costly_buckets_of_class": len(union),
            "testable_as_a_class": len(union) >= min_costly_buckets,
            "why": (f"{len(union)} distinct costly bucket(s); a class needs "
                    f"{min_costly_buckets} before mutual co-occurrence is a "
                    f"claim rather than a restatement of one observation"),
        })
    classes.sort(key=lambda c: (-c["n_costly_buckets_of_class"], c["label"]))
    return classes


def cluster_evidence(ledgers: Iterable,
                     min_costly_buckets: int = CLUSTER_MIN_COSTLY_BUCKETS,
                     **kw) -> dict:
    """Re-grade with each inseparable class relabelled as one hypothesis."""
    ledgers = [dict(l) for l in ledgers]
    classes = inseparable_classes(costly_bucket_cofires(ledgers),
                                  min_costly_buckets)
    merged = [c for c in classes if c["testable_as_a_class"]]
    rename = {m: c["label"] for c in merged for m in c["members"]}
    if not rename:
        return {"classes": classes, "n_merged": 0, "evidence": None,
                "why": "no inseparable class has enough costly buckets to test"}
    relabelled = []
    for l in ledgers:
        l = dict(l)
        seen_keys: dict = {}
        entries = []
        for e in l["entries"]:
            e = dict(e)
            e["unit"] = rename.get(e["unit"], e["unit"])
            # One class firing three units into one bucket is ONE occupancy of
            # that bucket, not three; collapse duplicates or the union's own
            # members inflate its fire count and destroy `consistency`.
            key = (e["unit"], e["bucket_end"])
            if key in seen_keys:
                continue
            seen_keys[key] = True
            entries.append(e)
        l["entries"] = entries
        relabelled.append(l)
    ev = attribution_evidence(relabelled, **kw)
    return {"classes": classes, "n_merged": len(merged),
            "merged_labels": [c["label"] for c in merged],
            "rename": rename, "evidence": ev,
            "why": ("each class is ONE hypothesis: union occupancy (which "
                    "hurts) against a looser Bonferroni bar (which helps)")}


# ============================================================ round 436
# The engine's own log, and the section that was a copy of another section
#
# Round 430's next-E item 5 named `journal-user-full.txt` (456 kB, banked by
# round 424, never opened) as the candidate explanation for the 33 of 52
# costly swap buckets that hold no named fire, and proposed "a second parser
# for `systemd[1057]:`, not a change to `parse_unit_starts`".
#
# Both halves of that are wrong, and the file says so on its own first read.
#
# 1. THE USER MANAGER STARTS ALMOST NOTHING. Over the ten-day window it
#    emits FIFTEEN `Starting` lines: seven `dbus.socket`, seven
#    `gpg-agent-ssh.socket` and one `dbus.service`, two per login session.
#    A population of 15 socket activations cannot account for 33 costly
#    buckets, and `parse_user_unit_starts` below exists mainly to MEASURE
#    that refutation rather than to leave it as an assertion.
#
# 2. THE SECTION LABELLED `### USER_MANAGER` CONTAINS NO `systemd[` LINE AT
#    ALL. It is 329 `coli[...]` lines -- the inference engine's own log, and
#    that is what the command under it asked for: `capture_plan` step 3b runs
#    `journalctl _SYSTEMD_USER_UNIT=qwen36-colibri.service`, under a COMMENT
#    that calls it "the USER manager, which owns the engine". The header
#    records the comment's intent and the section holds the command's output.
#    The phrase was then cited for six rounds without anyone opening the file.
#
# 3. AND IT IS A COPY. Every one of those 329 lines already appears in the
#    file's unlabelled lead section; `### USER_MANAGER` is a filtered VIEW of
#    text the file already contains, appended after it. A `grep -c` over the
#    whole file therefore reports 26 engine loads where there are 13, and 363
#    chat completions where there are 182. The inflation is not a clean
#    factor of two either: the duplicated view starts at 2026-08-23T21:30:22,
#    so events before that instant are counted once and events after it
#    twice, which makes the late window look twice as busy as the early one.
#    That is the shape of error that survives a sanity check on totals.
#
# `journal_sections` keeps the unlabelled lead (which `sar_sections` drops on
# the floor, because `sar-all.txt` has a header before its first byte and this
# file does not), and `redundant_sections` reports any section whose lines are
# all present in an earlier one. The redundancy test is done per SECTION and
# never per line: two genuine `[api]` requests can share a second, and a
# line-level dedup would silently delete the second one.

JOURNAL_LEAD_SECTION = "(unlabelled lead)"
_BOOT_MARKER = re.compile(r"^-- Boot [0-9a-f]{32} --\s*$")


def journal_sections(text: str) -> dict:
    """`### NAME` -> body, KEEPING any text that precedes the first header.

    `sar_sections` returns {} for a file with no `###` line, which is correct
    for `sar-all.txt` and catastrophic for `journal-user-full.txt`: 3731 of
    its 4067 lines sit above the only header it has.
    """
    secs: dict = {JOURNAL_LEAD_SECTION: []}
    cur = JOURNAL_LEAD_SECTION
    for line in text.splitlines():
        m = _SECTION_HEAD.match(line)
        if m:
            cur = m.group(1)
            secs.setdefault(cur, [])
        else:
            secs[cur].append(line)
    if not secs[JOURNAL_LEAD_SECTION]:
        del secs[JOURNAL_LEAD_SECTION]
    return {k: "\n".join(v) for k, v in secs.items()}


def _record_lines(body: str) -> list:
    """Journal record lines: no blanks, no `-- Boot <id> --` separators."""
    return [l for l in body.splitlines()
            if l.strip() and not _BOOT_MARKER.match(l)]


def redundant_sections(secs: dict) -> dict:
    """Sections whose every record line already appears in an EARLIER one.

    Returns {redundant_name: covering_name}. Order is the dict's order, which
    is file order, because "earlier" is what makes one of the two the copy.
    A section is redundant only if it is a SUBSET; a section that adds even
    one line is kept whole, since dropping it would lose that line.
    """
    names = list(secs)
    sets = {n: set(_record_lines(secs[n])) for n in names}
    out: dict = {}
    for i, n in enumerate(names):
        if not sets[n]:
            continue
        for m in names[:i]:
            if sets[n] <= sets[m]:
                out[n] = m
                break
    return out


def dedupe_journal(text: str) -> tuple:
    """(text of the non-redundant sections, a report of what was dropped).

    The report is the deliverable, not a side effect: "this file's counts are
    inflated and here is by how much" is the finding, and a function that
    quietly returned clean text would have hidden it.
    """
    secs = journal_sections(text)
    dup = redundant_sections(secs)
    kept = [n for n in secs if n not in dup]
    n_all = sum(len(_record_lines(b)) for b in secs.values())
    n_kept = sum(len(_record_lines(secs[n])) for n in kept)
    dropped_first = {}
    for n in dup:
        lines = _record_lines(secs[n])
        dropped_first[n] = lines[0][:19] if lines else ""
    return "\n".join(secs[n] for n in kept), {
        "n_sections": len(secs),
        "sections": names_of(secs),
        "n_redundant_sections": len(dup),
        "redundant_sections": dup,
        "n_record_lines_all": n_all,
        "n_record_lines_kept": n_kept,
        "n_record_lines_dropped": n_all - n_kept,
        "inflation_factor_naive": (round(n_all / n_kept, 4) if n_kept else None),
        "duplicated_view_starts_utc": dropped_first,
        "why": ("a section whose lines all appear in an earlier section is a "
                "VIEW of that section, and counting both double-counts every "
                "event inside the view's own time span -- not the whole file, "
                "which is why a totals check does not catch it"),
    }


def names_of(secs: dict) -> list:
    return list(secs)


# ---- the user manager, so its irrelevance is measured and not asserted

_USER_UNIT_START = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:[+-]\d{2}:\d{2}|Z)?\s+"
    r"\S+\s+systemd\[(\d+)\]:\s+Starting\s+(\S+?)\.(service|socket|target|timer)\b")


def parse_user_unit_starts(text: str, include_kinds=("service",)) -> list:
    """`systemd[<pid != 1>]: Starting <unit>.<kind>` -> `Event`.

    `parse_unit_starts` pins `systemd\\[1\\]` and so returns [] on this file;
    that is correct for it and is why the 456 kB contributed nothing to any
    published number. Labels are prefixed `user:` so a user unit can never be
    confused with, or pooled into, a PID-1 unit of the same name.

    `include_kinds` defaults to services only, matching `parse_unit_starts`.
    Pass `("service", "socket")` to see the socket activations -- on this
    record that is 13 of the 15 lines, which is the measurement that refutes
    round 430's item 5.
    """
    out = []
    for line in text.splitlines():
        m = _USER_UNIT_START.match(line)
        if m and m.group(2) != "1" and m.group(4) in include_kinds:
            out.append(Event(at_utc=m.group(1) + "Z",
                             label=f"user:{m.group(3)}.{m.group(4)}"))
    return out


# ---- the engine, which is what the file actually holds

# Three line shapes, and they do NOT share event semantics. `parse_unit_starts`
# yields START instants and `cost_ledger` adds `LEDGER_BOUNDARY_SLACK_S` to
# them because a unit that starts at T has done nothing at T. Two of the three
# engine shapes are COMPLETION lines, logged after the work, so the slack
# pushes them the wrong way.
#
#   [load]   `resident weights loaded in 13.2s | RSS after load: 9.25 GB`
#            a completion line that CARRIES ITS DURATION, so the start is
#            derivable from the line itself and no convention is invented.
#   [listen] `OpenAI-compatible API listening on http://127.0.0.1:8000/v1`
#            a start instant: the process is up and has done its allocation.
#   [api]    `[api] 127.0.0.1 - "POST /v1/chat/completions HTTP/1.1" 200 -`
#            a completion line with NO duration. Nothing in the record says
#            how far back the work began, and on this box a single 26.5k-token
#            Hermes turn prefills for ~87 minutes -- eight buckets. There is no
#            honest single placement, so `completion_shift_s` is an explicit
#            argument with no default that hides it, and
#            `engine_placement_sensitivity` reports which buckets survive the
#            choice instead of a run that pretends the choice was free.

ENGINE_LOAD = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:[+-]\d{2}:\d{2}|Z)?\s+\S+\s+"
    r"coli\[\d+\]:\s+resident weights loaded in ([\d.]+)s\s*\|\s*"
    r"RSS after load:\s*([\d.]+)\s*GB")
ENGINE_LISTEN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:[+-]\d{2}:\d{2}|Z)?\s+\S+\s+"
    r"coli\[\d+\]:\s+OpenAI-compatible API listening on "
    r"http://[\d.]+:(\d+)/")
ENGINE_API = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:[+-]\d{2}:\d{2}|Z)?\s+\S+\s+"
    r"coli\[\d+\]:\s+\[api\]\s+\S+\s+-\s+\"(\w+)\s+(/\S*)\s+HTTP/[\d.]+\"\s+(\d+)")

ENGINE_LOAD_LABEL = "engine:weights-load"
ENGINE_LISTEN_LABEL = "engine:listen"
ENGINE_CHAT_LABEL = "engine:chat-completion"
ENGINE_COMPLETION_LABEL = "engine:completion"
ENGINE_OTHER_LABEL = "engine:api-other"

# The GLM frontier lane. CLAUDE.md forbids this program from ever SENDING to
# port 8001; it does not forbid noticing that the box served on it, and the
# distinction matters here because a :8001 listen is a DIFFERENT model with a
# different resident size (`[RAM_GB=20.0] ... projected peak 19.7 GB` against
# qwen36's `RSS after load: 9.25 GB`). Pooling the two under one label would
# average two memory footprints that differ by more than a factor of two.
FRONTIER_PORT = "8001"


@dataclass(frozen=True)
class EngineEvent:
    at_utc: str                # the instant this event is placed at
    label: str
    logged_utc: str            # the instant the line was written
    semantics: str             # "start" | "completion"
    duration_s: float          # 0.0 when the line carries none
    detail: str

    def as_dict(self) -> dict:
        return asdict(self)


def _shift_utc(stamp: str, seconds: float) -> str:
    """`YYYY-MM-DDTHH:MM:SSZ` shifted by `seconds`, without a tz library."""
    d, _, t = stamp.rstrip("Z").partition("T")
    secs = _hms_to_s(t[:8]) + int(round(seconds))
    ordinal = _date_ordinal(d)
    while secs < 0:
        secs += 86400
        ordinal -= 1
    while secs >= 86400:
        secs -= 86400
        ordinal += 1
    nd = _date.fromordinal(ordinal).isoformat()
    return f"{nd}T{secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}Z"


def parse_engine_events(text: str, completion_shift_s: float = 0.0,
                        dedupe: bool = True) -> list:
    """The engine's own log lines as placed events.

    `dedupe` runs `dedupe_journal` first, because on the banked capture the
    same 329 lines appear twice and a caller who forgets would double every
    engine count after 2026-08-23T21:30:22.

    `completion_shift_s` moves the two completion-line classes earlier by that
    many seconds. It is 0.0 by default -- meaning "placed where it was logged",
    the only placement the record actually states -- and any other value is a
    modelling choice the caller has to make and report.
    """
    if dedupe:
        text, _ = dedupe_journal(text)
    out = []
    for line in text.splitlines():
        m = ENGINE_LOAD.match(line)
        if m:
            logged, dur, rss = m.group(1) + "Z", float(m.group(2)), m.group(3)
            out.append(EngineEvent(
                at_utc=_shift_utc(logged, -dur), label=ENGINE_LOAD_LABEL,
                logged_utc=logged, semantics="completion", duration_s=dur,
                detail=f"RSS after load {rss} GB"))
            continue
        m = ENGINE_LISTEN.match(line)
        if m:
            logged, port = m.group(1) + "Z", m.group(2)
            out.append(EngineEvent(
                at_utc=logged,
                label=(ENGINE_LISTEN_LABEL + ":" + port
                       if port == FRONTIER_PORT else ENGINE_LISTEN_LABEL),
                logged_utc=logged, semantics="start", duration_s=0.0,
                detail=f"port {port}"))
            continue
        m = ENGINE_API.match(line)
        if m:
            logged, verb, path, status = (m.group(1) + "Z", m.group(2),
                                          m.group(3), m.group(4))
            if verb == "POST" and path.endswith("/chat/completions"):
                label = ENGINE_CHAT_LABEL
            elif verb == "POST" and path.endswith("/completions"):
                label = ENGINE_COMPLETION_LABEL
            else:
                label = ENGINE_OTHER_LABEL
            out.append(EngineEvent(
                at_utc=_shift_utc(logged, -completion_shift_s),
                label=label, logged_utc=logged, semantics="completion",
                duration_s=0.0, detail=f"{verb} {path} {status}"))
    out.sort(key=lambda e: (e.at_utc, e.label))
    return out


def engine_event_summary(events: Iterable) -> dict:
    events = list(events)
    by_label: dict = {}
    by_date: dict = {}
    for e in events:
        by_label[e.label] = by_label.get(e.label, 0) + 1
        by_date[e.at_utc[:10]] = by_date.get(e.at_utc[:10], 0) + 1
    return {
        "n_events": len(events),
        "by_label": dict(sorted(by_label.items())),
        "by_date": dict(sorted(by_date.items())),
        "n_completion_semantics": sum(1 for e in events
                                      if e.semantics == "completion"),
        "n_with_derivable_start": sum(1 for e in events if e.duration_s > 0),
        "first_utc": events[0].at_utc if events else None,
        "last_utc": events[-1].at_utc if events else None,
    }


def engine_placement_sensitivity(text: str, sar_text: str,
                                 channel: Channel = SWAP_CHANNEL,
                                 min_bytes=_UNSET,
                                 shifts=(0.0, 300.0, 600.0),
                                 interval_s: int = SAR_INTERVAL_S) -> dict:
    """Which engine attributions survive the completion-placement choice.

    An `[api]` line says when a request FINISHED. The bucket that paid for it
    is the one the work ran in, and the record does not say which that was.
    Rather than pick a shift and publish one ledger, this runs the whole
    window at each candidate shift and reports, per label, the set of costly
    buckets it lands in at EVERY shift (`stable`) against the ones it lands in
    at some (`unstable`). Only the stable set is evidence.
    """
    secs = sar_sections(sar_text)
    prefix = CHANNEL_SECTION_PREFIX[channel.name]
    days = []
    for name in sorted(s for s in secs if s.startswith(prefix)):
        body = secs[name]
        days.append((parse_sar(body), sar_banner_date(body)))
    per_shift = {}
    for sh in shifts:
        events = parse_engine_events(text, completion_shift_s=sh)
        hits: dict = {}
        for table, date in days:
            led = cost_ledger(events, table, date, interval_s,
                              min_bytes=min_bytes, exclude_units=(),
                              channel=channel)
            for e in led["entries"]:
                if e["costly"]:
                    hits.setdefault(e["unit"], set()).add(
                        (date, e["bucket_end"]))
        per_shift[sh] = hits
    labels = sorted({l for h in per_shift.values() for l in h})
    rows = []
    for label in labels:
        sets = [per_shift[sh].get(label, set()) for sh in shifts]
        stable = set.intersection(*sets) if sets else set()
        union = set().union(*sets) if sets else set()
        rows.append({
            "label": label,
            "n_costly_buckets_stable": len(stable),
            "n_costly_buckets_any_shift": len(union),
            "stable": sorted(f"{d} {b}" for d, b in stable),
            "unstable": sorted(f"{d} {b}" for d, b in (union - stable)),
            "placement_dependent": len(union) != len(stable),
        })
    return {
        "channel": channel.name,
        "shifts_s": list(shifts),
        "min_bytes": (CHANNEL_MIN_BYTES.get(channel.name)
                      if min_bytes is _UNSET else min_bytes),
        "n_days": len(days),
        "labels": rows,
        "why": ("an `[api]` line is logged when the request finished; the "
                "bucket that paid is the one the work ran in, and only an "
                "attribution that holds at every candidate shift is evidence"),
    }


# ---- round 436: the direct measurement that was in the record all along
#
# Every attribution number this track has published -- `p_chance`, the six
# gates, `power_floor`, the whole `shared-only` verdict class -- is INFERRED,
# by asking whether a unit's fires land in costly `sar` buckets more often
# than chance allows over a 600 s grid. Round 430 dropped the `fwupd`
# attribution on a powered null and called `packagekit` a one-way confounder
# nothing could ever separate.
#
# systemd measured all of it directly, per invocation, and wrote the answer
# into the same two banked journals:
#
#   fwupd.service: Consumed 3.661s CPU time, 209.7M memory peak,
#                  6.2M memory swap peak.
#   qwen36-colibri.service: Consumed 27min 46.334s CPU time, 30.0G memory
#                  peak, 3.9G memory swap peak.
#
# That is cgroup accounting: a per-unit, per-run high-water mark with no
# bucket, no threshold, no confounder and no hypergeometric null. It is not a
# substitute for the ledger -- a peak is not the same quantity as pages
# written out in an interval, and only a minority of runs carry it -- but it
# is an INDEPENDENT check on the inferences, and every one it can reach it
# agrees with.
#
# The reason nobody used it is the same reason the engine was invisible:
# `parse_unit_starts` matches `systemd[1]: Starting`, and these lines are
# `Consumed`, on units whose journal is the USER manager's.

_SIZE_UNITS = {"B": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3,
               "T": 1024 ** 4}
_SIZE = re.compile(r"^([\d.]+)([BKMGT])$")
_RESOURCE_LINE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:[+-]\d{2}:\d{2}|Z)?\s+\S+\s+"
    r"systemd\[(\d+)\]:\s+(\S+?):\s+Consumed\s+(.+?)\.\s*$")
_CPU = re.compile(r"([\d.]+)\s*(h|min|s|ms)")
_MEM_PEAK = re.compile(r"([\d.]+[BKMGT])\s+memory peak")
_SWAP_PEAK = re.compile(r"([\d.]+[BKMGT])\s+memory swap peak")
_CPU_SCALE = {"h": 3600.0, "min": 60.0, "s": 1.0, "ms": 0.001}


def parse_size(text: str) -> int:
    m = _SIZE.match(text.strip())
    if not m:
        raise PerturbationError(f"not a systemd size literal: {text!r}")
    return int(round(float(m.group(1)) * _SIZE_UNITS[m.group(2)]))


def _parse_cpu(text: str) -> float:
    total, seen = 0.0, False
    for value, unit in _CPU.findall(text):
        total += float(value) * _CPU_SCALE[unit]
        seen = True
    if not seen:
        raise PerturbationError(f"no CPU time in {text!r}")
    return round(total, 3)


@dataclass(frozen=True)
class ResourceAccounting:
    """One `<unit>: Consumed ...` line: systemd's own cgroup accounting."""
    unit: str
    at_utc: str
    manager: str                  # "system" (pid 1) | "user"
    cpu_s: float
    memory_peak_bytes: object     # int, or None when the line omits it
    memory_swap_peak_bytes: object

    @property
    def has_memory(self) -> bool:
        return self.memory_peak_bytes is not None

    def as_dict(self) -> dict:
        return asdict(self) | {"has_memory": self.has_memory}


def parse_resource_accounting(text: str, kinds=("service",),
                              dedupe: bool = True) -> list:
    """`systemd[N]: <unit>: Consumed <cpu>[, <peak> memory peak, ...]` lines.

    `kinds` filters on the unit suffix; `.scope` and `.slice` are excluded by
    default because a slice's peak is the SUM over its children (`app.slice`
    reports the same 30.0G as the engine inside it) and pooling both would
    double-count the one measurement that matters.
    """
    if dedupe:
        text, _ = dedupe_journal(text)
    out = []
    for line in text.splitlines():
        m = _RESOURCE_LINE.match(line)
        if not m:
            continue
        at, pid, unit, body = (m.group(1) + "Z", m.group(2), m.group(3),
                               m.group(4))
        suffix = unit.rpartition(".")[2]
        if kinds and suffix not in kinds:
            continue
        mp = _MEM_PEAK.search(body)
        sp = _SWAP_PEAK.search(body)
        out.append(ResourceAccounting(
            unit=unit.rpartition(".")[0] if suffix == "service" else unit,
            at_utc=at, manager=("system" if pid == "1" else "user"),
            cpu_s=_parse_cpu(body),
            memory_peak_bytes=parse_size(mp.group(1)) if mp else None,
            memory_swap_peak_bytes=parse_size(sp.group(1)) if sp else None))
    out.sort(key=lambda r: (r.at_utc, r.unit))
    return out


def direct_cost_table(records: Iterable) -> dict:
    """Per unit, what systemd actually measured -- no inference anywhere."""
    records = list(records)
    per: dict = {}
    for r in records:
        u = per.setdefault(r.unit, {
            "unit": r.unit, "managers": set(), "n_invocations": 0,
            "n_with_memory": 0, "cpu_s_total": 0.0,
            "max_memory_peak_bytes": None, "max_swap_peak_bytes": None,
            "swap_peaks_bytes": []})
        u["managers"].add(r.manager)
        u["n_invocations"] += 1
        u["cpu_s_total"] = round(u["cpu_s_total"] + r.cpu_s, 3)
        if r.has_memory:
            u["n_with_memory"] += 1
            u["max_memory_peak_bytes"] = max(
                u["max_memory_peak_bytes"] or 0, r.memory_peak_bytes)
            u["max_swap_peak_bytes"] = max(
                u["max_swap_peak_bytes"] or 0, r.memory_swap_peak_bytes or 0)
            u["swap_peaks_bytes"].append(r.memory_swap_peak_bytes or 0)
    rows = []
    for u in per.values():
        u = dict(u, managers=sorted(u["managers"]))
        rows.append(u)
    rows.sort(key=lambda u: (-(u["max_swap_peak_bytes"] or -1),
                             -(u["max_memory_peak_bytes"] or -1), u["unit"]))
    measured = [u for u in rows if u["n_with_memory"]]
    return {
        "n_records": len(records),
        "n_units": len(rows),
        "n_units_with_a_memory_measurement": len(measured),
        "n_records_with_memory": sum(1 for r in records if r.has_memory),
        "units": rows,
        "why": ("`memory swap peak` is a cgroup high-water mark over one "
                "invocation; `pswpout/s` is pages written out in a 600 s "
                "bucket. They are different quantities and only their ORDER "
                "may be compared -- which is enough, because the orders here "
                "differ by 10^3"),
    }


def direct_vs_inferred(evidence: dict, records: Iterable,
                       costly_threshold_bytes: int = LEDGER_MIN_BYTES) -> dict:
    """Cross-check every graded unit against its own direct measurement.

    For each unit the ledger machinery produced a verdict for, ask whether the
    record ALSO contains systemd's cgroup accounting for it, and whether the
    two agree. `agrees` is deliberately weak: a direct swap peak below the
    costly threshold agrees with any verdict that is not `supported`, and a
    peak above it agrees with any verdict that is not `no-evidence`. The point
    is to find CONTRADICTIONS, not to relabel anything.
    """
    table = {u["unit"]: u for u in direct_cost_table(records)["units"]}
    rows, contradictions = [], []
    for u in evidence["units"]:
        d = table.get(u["unit"])
        measured = d["max_swap_peak_bytes"] if d and d["n_with_memory"] else None
        row = {
            "unit": u["unit"],
            "inferred_verdict": u["verdict"],
            "inferred_n_costly": u["n_costly"],
            "inferred_max_bucket_bytes": u["max_bucket_bytes"],
            "has_direct_measurement": measured is not None,
            "direct_max_swap_peak_bytes": measured,
            "direct_max_memory_peak_bytes":
                (d["max_memory_peak_bytes"] if d else None),
            "direct_n_invocations": (d["n_invocations"] if d else 0),
        }
        if measured is not None:
            row["direct_says_costly"] = measured >= costly_threshold_bytes
            if u["verdict"] == "supported" and not row["direct_says_costly"]:
                row["agrees"] = False
                contradictions.append(u["unit"])
            elif u["verdict"] == "no-evidence" and row["direct_says_costly"]:
                row["agrees"] = False
                contradictions.append(u["unit"])
            else:
                row["agrees"] = True
        rows.append(row)
    covered = [r for r in rows if r["has_direct_measurement"]]
    return {
        "costly_threshold_bytes": costly_threshold_bytes,
        "n_graded_units": len(rows),
        "n_with_a_direct_measurement": len(covered),
        "coverage": (round(len(covered) / len(rows), 4) if rows else 0.0),
        "n_contradictions": len(contradictions),
        "contradictions": sorted(contradictions),
        "units_never_graded_but_measured": sorted(
            set(table) - {u["unit"] for u in evidence["units"]}),
        "rows": rows,
        "why": ("a direct cgroup measurement cannot be confounded, cannot be "
                "shared with another unit, and needs no threshold sweep; "
                "where it exists it is the better evidence, and where it "
                "contradicts an inferred verdict the inference loses"),
    }


# ---- round 436: the fires `parse_unit_starts` cannot see, and why

# `parse_unit_starts` matches `Starting`, with a docstring saying `Started`
# "fires for the same unit and would double every count". That is true of the
# 74 units in this journal that emit both -- and FALSE of the six that emit
# only `Started`, which systemd does for a unit with no startup phase to
# announce (`Type=simple` and friends log `Started` alone). Those six have
# been absent from every ledger, every base rate and every denominator this
# program has published, and one of them is `unattended-upgrades`.
#
# The fix is a second pass, not a looser regex: collect the units that emit
# `Starting` anywhere in the text, then admit `Started` fires only for units
# that never do. That preserves the no-double-count property exactly, and it
# is why `parse_unit_starts` itself is left untouched -- a silent widening
# would move every published number without saying so.

_UNIT_VERB = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:[+-]\d{2}:\d{2}|Z)?\s+"
    r"\S+\s+systemd\[(\d+)\]:\s+(Starting|Started)\s+(\S+?)\.service")


def unit_start_verb_audit(text: str) -> dict:
    """Which units announce `Starting`, which only ever say `Started`."""
    starting: dict = {}
    started: dict = {}
    for line in text.splitlines():
        m = _UNIT_VERB.match(line)
        if not m:
            continue
        d = starting if m.group(3) == "Starting" else started
        d[m.group(4)] = d.get(m.group(4), 0) + 1
    only = {u: n for u, n in sorted(started.items()) if u not in starting}
    return {
        "n_units_with_starting": len(starting),
        "n_starting_fires": sum(starting.values()),
        "n_units_with_started": len(started),
        "n_started_fires": sum(started.values()),
        "units_started_only": only,
        "n_units_started_only": len(only),
        "n_fires_invisible_to_parse_unit_starts": sum(only.values()),
        "why": ("systemd logs `Starting` only for a unit with a startup phase "
                "to announce; a `Type=simple` unit logs `Started` alone, so a "
                "parser pinned to `Starting` drops it entirely rather than "
                "half-counting it"),
    }


def parse_unit_starts_complete(text: str) -> list:
    """Every unit start, with `Started` admitted only where `Starting` never is.

    Same `Event` shape as `parse_unit_starts`, and identical output on any
    text where every unit announces itself. The added fires are labelled with
    the plain unit name, because they ARE the unit's start -- the verb is
    systemd's choice, not a different event.
    """
    audit = unit_start_verb_audit(text)
    only = set(audit["units_started_only"])
    out = list(parse_unit_starts(text))
    for line in text.splitlines():
        m = _UNIT_VERB.match(line)
        if m and m.group(3) == "Started" and m.group(2) == "1" \
                and m.group(4) in only:
            out.append(Event(at_utc=m.group(1) + "Z", label=m.group(4)))
    out.sort(key=lambda e: (e.at_utc, e.label))
    return out


def engine_verdict_stability(sar_text: str, journal_text: str,
                             engine_journal_text: str,
                             channel: Channel = STEAL_CHANNEL,
                             min_bytes=_UNSET,
                             shifts=(0.0, 150.0, 300.0, 600.0, 1200.0),
                             interval_s: int = SAR_INTERVAL_S,
                             **kw) -> dict:
    """Re-grade with the engine pooled in at every candidate placement.

    An `[api]` line is logged when a request FINISHED, so the bucket that paid
    for it is unknown to the record. A verdict that appears at one shift and
    not another is a property of the shift. This runs them all and reports,
    per label, at how many placements each verdict held -- and the CONSISTENCY
    series, because a consistency that falls monotonically as the event is
    moved away from where it was logged is the record choosing the placement
    rather than the analyst choosing it.
    """
    secs = sar_sections(sar_text)
    prefix = CHANNEL_SECTION_PREFIX[channel.name]
    days = [(parse_sar(secs[n]), sar_banner_date(secs[n]))
            for n in sorted(x for x in secs if x.startswith(prefix))]
    base = list(parse_unit_starts(journal_text))
    per_shift = {}
    for sh in shifts:
        fires = base + list(parse_engine_events(engine_journal_text,
                                                completion_shift_s=sh))
        ledgers = [cost_ledger(fires, t, d, interval_s, min_bytes=min_bytes,
                               channel=channel) for t, d in days]
        per_shift[sh] = attribution_evidence(ledgers, **kw)
    labels = sorted({u["unit"] for e in per_shift.values() for u in e["units"]
                     if u["unit"].startswith("engine:")})
    rows = []
    for label in labels:
        series = []
        for sh in shifts:
            u = next((x for x in per_shift[sh]["units"] if x["unit"] == label),
                     None)
            series.append({"shift_s": sh,
                           "verdict": u["verdict"] if u else None,
                           "n_fires": u["n_fires"] if u else 0,
                           "n_costly": u["n_costly"] if u else 0,
                           "n_clean": u["n_clean"] if u else 0,
                           "consistency": round(u["consistency"], 4) if u else None,
                           "p_family": u["p_family"] if u else None})
        cons = [r["consistency"] for r in series if r["consistency"] is not None]
        n_sup = sum(1 for r in series if r["verdict"] == "supported")
        rows.append({
            "label": label,
            "n_shifts": len(shifts),
            "n_shifts_supported": n_sup,
            "supported_at_every_shift": n_sup == len(shifts),
            "supported_at_a_majority": n_sup * 2 > len(shifts),
            "verdicts": [r["verdict"] for r in series],
            "consistency_series": cons,
            "consistency_falls_monotonically_with_shift":
                all(a >= b for a, b in zip(cons, cons[1:])) and len(cons) > 1,
            "series": series,
        })
    rows.sort(key=lambda r: (-r["n_shifts_supported"], r["label"]))
    return {
        "channel": channel.name,
        "min_bytes": (CHANNEL_MIN_BYTES.get(channel.name)
                      if min_bytes is _UNSET else min_bytes),
        "shifts_s": list(shifts),
        "n_days": len(days),
        "labels": rows,
        "supported_at_every_shift": [r["label"] for r in rows
                                     if r["supported_at_every_shift"]],
        "supported_at_a_majority": [r["label"] for r in rows
                                    if r["supported_at_a_majority"]],
        "why": ("only a verdict that survives the placement it cannot pin is "
                "evidence; a monotone fall in consistency as the event is "
                "moved earlier says the logged instant is close to the truth"),
    }


# ---- round 436: the box OOM-killed, three times, and nobody had looked
#
# The largest costly bucket in the record that no fire explains is
# `2026-08-23 21:20:02`, 2.34 GiB of swap-out. Eight minutes later systemd
# wrote `tmux-spawn-....scope: Failed with result 'oom-kill'`, and a minute
# after that `-.slice: A process of this unit has been killed by the OOM
# killer`. On 2026-08-24 the same line names the engine itself:
# `qwen36-colibri.service: A process of this unit has been killed by the OOM
# killer` / `Failed with result 'oom-kill'`.
#
# Three OOM episodes in a ten-day window on the machine this whole track
# exists to make usable, and no round had grepped for the word. They are not
# an attribution problem -- an OOM kill is systemd naming the cgroup out loud,
# with no bucket, no threshold and no null hypothesis. What the `sar` record
# adds is the SIZE of the episode, which is why this pairs the two.

_OOM_LINE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:[+-]\d{2}:\d{2}|Z)?\s+\S+\s+"
    r"systemd\[(\d+)\]:\s+(\S+?):\s+"
    r"(A process of this unit has been killed by the OOM killer|"
    r"Failed with result 'oom-kill')")

OOM_KILLED = "oom-killed"
OOM_FAILED = "oom-failed"


@dataclass(frozen=True)
class OomEvent:
    at_utc: str
    unit: str
    manager: str
    kind: str          # OOM_KILLED (a child died) | OOM_FAILED (the unit died)

    def as_dict(self) -> dict:
        return asdict(self)


def parse_oom_kills(text: str, dedupe: bool = True) -> list:
    """systemd's OOM lines, from either manager's journal.

    Two shapes and they are NOT the same event: "A process of this unit has
    been killed" is reported by every cgroup ANCESTOR of the victim (so one
    kill appears against the scope, the slice and `user@1000.service`), while
    "Failed with result 'oom-kill'" is the unit that actually died. Keeping
    both and labelling them is what lets `oom_episodes` collapse the ancestors
    without losing the name of the victim.
    """
    if dedupe:
        text, _ = dedupe_journal(text)
    out = []
    for line in text.splitlines():
        m = _OOM_LINE.match(line)
        if m:
            out.append(OomEvent(
                at_utc=m.group(1) + "Z", unit=m.group(3),
                manager=("system" if m.group(2) == "1" else "user"),
                kind=(OOM_FAILED if m.group(4).startswith("Failed")
                      else OOM_KILLED)))
    out.sort(key=lambda e: (e.at_utc, e.unit))
    return out


OOM_EPISODE_GAP_S = 300


def oom_episodes(events: Iterable, gap_s: int = OOM_EPISODE_GAP_S) -> list:
    """Group OOM lines within `gap_s` into one episode, naming its victim.

    A single kill fans out across the cgroup ancestry and across BOTH
    journals; counting lines would report ten OOMs where there were three.
    """
    events = sorted(events, key=lambda e: e.at_utc)
    episodes = []
    for e in events:
        if episodes and (_hms_to_s(e.at_utc[11:19])
                         - _hms_to_s(episodes[-1]["last_utc"][11:19])
                         <= gap_s) and e.at_utc[:10] == episodes[-1]["date"]:
            ep = episodes[-1]
        else:
            ep = {"date": e.at_utc[:10], "first_utc": e.at_utc,
                  "last_utc": e.at_utc, "units": [], "victims": [],
                  "managers": set(), "n_lines": 0}
            episodes.append(ep)
        ep["last_utc"] = max(ep["last_utc"], e.at_utc)
        ep["n_lines"] += 1
        ep["managers"].add(e.manager)
        if e.unit not in ep["units"]:
            ep["units"].append(e.unit)
        if e.kind == OOM_FAILED and e.unit not in ep["victims"]:
            ep["victims"].append(e.unit)
    for ep in episodes:
        ep["managers"] = sorted(ep["managers"])
        ep["named_victim"] = ep["victims"][0] if ep["victims"] else None
        ep["why"] = ("`Failed with result 'oom-kill'` names the unit that died; "
                     "the other lines are its cgroup ancestors reporting the "
                     "same kill"
                     if ep["victims"] else
                     "no unit reported `Failed with result 'oom-kill'`: the "
                     "victim was a bare process inside a cgroup that survived")
    return episodes


def oom_cost_context(episodes: Iterable, sar_text: str,
                     channel: Channel = SWAP_CHANNEL,
                     min_bytes=_UNSET,
                     interval_s: int = SAR_INTERVAL_S,
                     window_s: int = 1800) -> dict:
    """What the channel recorded around each OOM episode.

    The OOM line says WHO; the sar record says HOW BIG. `rank` is the
    episode's bucket among all costly buckets of the window, which is the form
    of the claim that survives being read out of context.
    """
    if min_bytes is _UNSET:
        min_bytes = CHANNEL_MIN_BYTES.get(channel.name)
        if min_bytes is None:
            raise PerturbationError(
                f"channel {channel.name!r} has no derived costly-threshold; "
                f"pass min_bytes explicitly and report it")
    secs = sar_sections(sar_text)
    prefix = CHANNEL_SECTION_PREFIX[channel.name]
    per_bucket: dict = {}
    for name in sorted(x for x in secs if x.startswith(prefix)):
        body = secs[name]
        date = sar_banner_date(body)
        for bn, _v, byts in bucket_costs(parse_sar(body), channel, interval_s):
            if byts is not None:
                per_bucket[(date, bn)] = byts
    costly = {k: v for k, v in per_bucket.items() if v >= min_bytes}
    ranked = sorted(costly.items(), key=lambda kv: -kv[1])
    rank = {k: i + 1 for i, (k, _v) in enumerate(ranked)}

    rows = []
    for ep in episodes:
        d, t = ep["date"], _hms_to_s(ep["first_utc"][11:19])
        hit = [(bn, v) for (dd, bn), v in per_bucket.items()
               if dd == d and _hms_to_s(bn) - interval_s < t <= _hms_to_s(bn)]
        near = [(bn, v) for (dd, bn), v in per_bucket.items()
                if dd == d and abs(_hms_to_s(bn) - t) <= window_s]
        bn, byts = (hit[0] if hit else (None, None))
        rows.append({
            "first_utc": ep["first_utc"],
            "named_victim": ep["named_victim"],
            "units": ep["units"],
            "bucket": bn,
            "bucket_bytes": byts,
            "bucket_is_costly": bool(bn and (d, bn) in costly),
            "rank_among_costly": rank.get((d, bn)),
            "n_costly_buckets": len(costly),
            "window_s": window_s,
            "n_buckets_in_window": len(near),
            "bytes_in_window": sum(v for _b, v in near),
            "why_no_bucket": (None if bn else
                              "no bucket of this day-file covers the instant "
                              "with a defined cost (first row, post-restart "
                              "row, or a gap in collection)"),
        })
    rows.sort(key=lambda r: r["first_utc"])
    return {
        "channel": channel.name,
        "min_bytes": min_bytes,
        "n_episodes": len(rows),
        "n_episodes_in_a_costly_bucket": sum(1 for r in rows
                                             if r["bucket_is_costly"]),
        "n_episodes_with_no_covering_bucket": sum(1 for r in rows
                                                  if r["bucket"] is None),
        "episodes": rows,
        "why": ("an OOM kill is systemd naming the cgroup out loud -- no "
                "bucket, no threshold, no null. The sar record adds only the "
                "SIZE of the episode, and `rank` is the honest form of that"),
    }


# ---- round 430 item 4: the steal channel needs a swept window, not one run

def window_sweep(sar_text: str, journal_text: str,
                 channel: Channel = STEAL_CHANNEL,
                 thresholds: Iterable = (),
                 interval_s: int = SAR_INTERVAL_S,
                 exclude_units: Iterable = LEDGER_EXCLUDE_UNITS,
                 extra_fires: Iterable = (),
                 stitch: bool = False,
                 max_family_p: float = ATTRIBUTION_MAX_FAMILY_P,
                 min_consistency: float = ATTRIBUTION_MIN_CONSISTENCY) -> dict:
    """`window_attribution` re-run at every threshold, with the gate table.

    Round 430 left the steal channel as the one channel never pooled, and
    said to sweep it because `CHANNEL_MIN_BYTES["steal"]` is `None` -- this
    record has no bucket independently labelled "reclaim noise" to derive one
    from, so any single threshold IS the result.

    `channel_sweep` already sweeps, but it reports `supported_was_reachable`,
    which round 430 proved is a claim about ONE of six gates while being read
    as a claim about all of them. This carries `verdict_floor` at every
    threshold instead, so "no unit was supported" comes with which gate said
    so, at each setting.
    """
    extra_fires = list(extra_fires)
    frame = window_frame(sar_text, journal_text, channel, exclude_units)
    secs = sar_sections(sar_text)
    fires = list(parse_unit_starts(journal_text)) + extra_fires
    use = [d for d in frame["days"] if d["pairing"] == PAIRING_PAIRED]
    if not use:
        raise PerturbationError(
            "no poolable day-file: every sar day is unpaired with the journal")
    tables = [(parse_sar(secs[d["section"]]), d["date"]) for d in use]
    stitches = auto_stitches(tables, interval_s) if stitch else {}
    rows = []
    for mb in thresholds:
        ledgers = [cost_ledger(fires, t, date, interval_s, min_bytes=int(mb),
                               exclude_units=exclude_units, channel=channel,
                               stitch=(stitches.get(date)
                                       if isinstance(stitches.get(date), Stitch)
                                       else None))
                   for t, date in tables]
        ev = attribution_evidence(ledgers, max_family_p=max_family_p,
                                  min_consistency=min_consistency)
        gates = verdict_floor(ev)
        cof = costly_bucket_cofires(ledgers)
        rows.append({
            "min_bytes": int(mb),
            "n_buckets": ev["n_buckets"],
            "n_costly_buckets": ev["n_costly_buckets"],
            "n_units_tested": ev["n_units_tested"],
            "n_testable_units": ev["n_testable_units"],
            "testable_band": [ev["power"]["min_testable_occupancy"],
                              ev["power"]["max_testable_occupancy"]],
            "by_verdict": ev["by_verdict"],
            "supported": ev["supported"],
            "supported_was_reachable_one_gate": ev["supported_was_reachable"],
            "supported_reachable_all_gates":
                gates["supported_reachable_all_gates"],
            "pass_counts": gates["pass_counts"],
            "pass_sets": gates["pass_sets"],
            "single_gate_from_supported": gates["single_gate_from_supported"],
            "blocking_gate_histogram": gates["blocking_gate_histogram"],
            "n_costly_with_a_named_fire":
                cof["n_costly_buckets_with_a_named_fire"],
            "n_costly_unnamed": (ev["n_costly_buckets"]
                                 - cof["n_costly_buckets_with_a_named_fire"]),
            "n_sole_occupied": cof["n_sole_occupied"],
        })
    ever = sorted({u for r in rows for u in r["supported"]})
    all_gate_rows = [r for r in rows if r["supported_reachable_all_gates"]]
    blocking = sorted({g for r in rows
                       for g in r["single_gate_from_supported"]})
    return {
        "frame": frame,
        "channel": channel.name,
        "n_extra_fires": len(extra_fires),
        "thresholds": [int(t) for t in thresholds],
        "rows": rows,
        "supported_at_any_threshold": ever,
        "n_thresholds_where_all_gates_reachable": len(all_gate_rows),
        "blocking_gates_seen": blocking,
        "verdict_is_a_setting": len({tuple(r["supported"]) for r in rows}) > 1,
        "why": ("a channel with no derived costly-threshold has no single "
                "verdict; if `supported` changes across the sweep the "
                "threshold IS the result and no single run may be quoted"),
    }


# ------------------------------------------------------------------- CLI


# ===========================================================================
# Round 466: the population that was the observer
#
# Round 436 established that `parse_unit_starts` sees only what its regex
# chose, fixed the VERB half of that (`Starting` vs `Started`), and left an
# item 6 open for five E rounds: `session-*.scope` records "were skipped by
# this round's `.service`-only default", and 14 costly buckets / 4.25 GiB were
# named by no fire at all.
#
# The `.service` half is a bigger hole than the verb half was. In round 424's
# ten-day journal PID 1 logs 1652 `Starting <unit>.service` lines -- the entire
# published fire population -- and 1401 `Started session-N.scope` lines, which
# no instrument in this tree has ever read. Not one `.scope` emits `Starting`,
# so round 436's two-pass rule (admit `Started` only for units that never say
# `Starting`) generalises to them with no new decision about double-counting:
# only the unit-kind alternation has to widen. `parse_unit_starts_any_kind`
# is that widening and nothing else, and it is pinned to agree with
# `parse_unit_starts_complete` exactly when `kinds == {"service"}`.
#
# Widening it moves every headline: costly-bucket coverage goes 19/52 -> 44/52
# and named bytes 8.42 GiB -> 29.65 GiB (26.7% -> 94.0% of the window's
# swap-out). THAT NUMBER IS A TRAP, and the trap is why the rest of this
# section exists.
#
# A fire population "names" a bucket by landing in it. 1401 extra fires over a
# 991-bucket grid will name a great many buckets whatever they are, so coverage
# is only evidence against a null that holds the population's SIZE and SHAPE
# fixed. Which null is not a detail -- it reverses the answer:
#
#   * uniform-random placement of 1401 fires over 991 buckets expects to name
#     ~39 of the 52 costly ones. Against that null the observed 29 is BELOW
#     chance and every population in this record looks anti-informative.
#   * a CIRCULAR SHIFT of the whole fire train -- rigidly translate every fire
#     by one offset and wrap inside the pooled window -- preserves burst
#     structure, cadence and count exactly and destroys only alignment. Against
#     that null the observed 29 sits against a mean of 6.8.
#
# The uniform null is the wrong one and it is wrong in the flattering
# direction: these fires arrive in bursts, so a uniform draw touches far more
# DISTINCT buckets than a real population of the same size ever could. Use the
# shift null. `shift_null` reports `n_identity_draws` because at this effect
# size the only draws that tie the observation are the ones that happened to
# draw offset 0 (mod span), and a p-value at its floor should say why.
#
# And then the finding, which is not about systemd at all. The 1401 scopes are
# ssh logins: median session lifetime 1 s, 89.8% under 5 s, every one of them
# "Session N of User jab". 33 of the 35 successful probes in
# `state/nuc-reachability-log.jsonl` have a scope start within 120 s and 15 of
# them within +/-1 s -- the log and the journal are two instruments recording
# THE SAME EVENTS. On the dates the log covers, 13 of the 14 scope-named costly
# buckets fall inside an E-round window against 5 of the other 19
# (Fisher two-sided p = 2.5e-4).
#
# So the strongest single "explanation" of costly swap on this box over ten
# days is this research program's own measurement traffic. `observer_trace` is
# the test for that, and it exists because the alternative was to publish
# "94% of swapped bytes are now attributed" and be worse off than before.
# `LEDGER_EXCLUDE_UNITS` already carries the precedent -- `sysstat-collect` is
# excluded because it WRITES the bucket -- but a session scope needs excluding
# for a different reason (it is the observer, not the instrument), and a
# different reason has to be measured before it is applied, not assumed.

_UNIT_VERB_ANY = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:[+-]\d{2}:\d{2}|Z)?\s+"
    r"\S+\s+systemd\[(\d+)\]:\s+(Starting|Started)\s+(\S+?)"
    r"\.(service|scope|socket|timer|target|mount|path|slice|swap)\b")

# `service` alone is the published population. Naming the default here rather
# than defaulting to "everything" keeps the widening an explicit argument at
# every call site.
UNIT_KINDS_PUBLISHED = ("service",)


def unit_kind_census(text: str) -> dict:
    """Every `systemd[1]` start line in the text, by (verb, unit kind).

    The measurement that says how much of a journal the published population
    can see. Reported per kind rather than pooled, because the answer for
    `.scope` (1401 lines, none of them `Starting`) and the answer for `.timer`
    (84 lines, none of them `Starting`) have different consequences and a
    single total would hide both.
    """
    by: dict = {}
    starting: dict = {}
    for line in text.splitlines():
        m = _UNIT_VERB_ANY.match(line)
        if not m or m.group(2) != "1":
            continue
        verb, unit, kind = m.group(3), m.group(4), m.group(5)
        k = by.setdefault(kind, {"Starting": 0, "Started": 0, "units": set()})
        k[verb] += 1
        k["units"].add(unit)
        if verb == "Starting":
            starting.setdefault(kind, set()).add(unit)
    out = {}
    for kind, k in sorted(by.items()):
        never = sorted(k["units"] - starting.get(kind, set()))
        out[kind] = {
            "n_starting": k["Starting"],
            "n_started": k["Started"],
            "n_distinct_units": len(k["units"]),
            "n_units_never_announcing_starting": len(never),
            "visible_to_parse_unit_starts": kind == "service",
        }
    return {
        "by_kind": out,
        "n_lines_visible_to_published_population":
            out.get("service", {}).get("n_starting", 0),
        "n_lines_invisible": sum(
            v["n_starting"] + v["n_started"] for k, v in out.items()
            if k != "service") + (out.get("service", {}).get("n_started", 0)),
        "why": ("`parse_unit_starts` matches `systemd[1]: Starting "
                "<unit>.service` and nothing else. A unit kind with no "
                "`Starting` line at all is not half-counted by that regex, it "
                "is absent from every ledger, base rate and denominator this "
                "program has published."),
    }


def parse_unit_starts_any_kind(text: str,
                               kinds: Iterable = UNIT_KINDS_PUBLISHED) -> list:
    """Round 436's start-verb rule, applied to any set of unit kinds.

    `Started` is admitted only for a (unit, kind) that never announces
    `Starting` anywhere in the text -- round 436's exact no-double-count rule,
    with the kind added to the key so a `foo.service` that announces itself
    cannot suppress a `foo.scope` that never does.

    Labels: a `.service` keeps its bare name, so this function is a drop-in for
    `parse_unit_starts_complete`. Every other kind is labelled `<unit>.<kind>`,
    because `session-407` and `session-407.scope` are not obviously the same
    thing to a reader of a ledger and the suffix costs nothing.

    Pinned by `test_widening_to_services_only_reproduces_round_436_exactly`:
    with the default `kinds` this returns byte-identical events to
    `parse_unit_starts_complete`, so the widening cannot silently move a
    published number.
    """
    want = set(kinds)
    bad = want - {"service", "scope", "socket", "timer", "target", "mount",
                  "path", "slice", "swap"}
    if bad:
        raise PerturbationError(f"unknown unit kind(s): {sorted(bad)}")
    announced = set()
    rows = []
    for line in text.splitlines():
        m = _UNIT_VERB_ANY.match(line)
        if not m or m.group(2) != "1":
            continue
        at, verb, unit, kind = (m.group(1) + "Z", m.group(3), m.group(4),
                                m.group(5))
        if verb == "Starting":
            announced.add((unit, kind))
        rows.append((at, verb, unit, kind))
    out = []
    for at, verb, unit, kind in rows:
        if kind not in want:
            continue
        if verb == "Starting" or (unit, kind) not in announced:
            out.append(Event(at_utc=at,
                             label=unit if kind == "service"
                             else f"{unit}.{kind}"))
    out.sort(key=lambda e: (e.at_utc, e.label))
    return out


class BucketMap:
    """Every second of the pooled window -> the costly bucket it falls in.

    Built BY `cost_ledger`, not beside it: one synthetic fire per second per
    day is run through the real ledger and the answer is read off its entries.
    That is slower than reimplementing the placement rule and it is the whole
    point -- the first draft of this class DID reimplement it, and the
    self-check below caught two separate divergences (a mishandled
    post-restart row, and `LEDGER_EXCLUDE_UNITS` not being applied to the
    population). A null that measures a paraphrase of the instrument is not a
    null on the instrument.
    """

    def __init__(self, sar_text: str, journal_text: str,
                 channel: Channel = SWAP_CHANNEL, min_bytes=_UNSET,
                 interval_s: int = SAR_INTERVAL_S,
                 exclude_units: Iterable = LEDGER_EXCLUDE_UNITS):
        frame = window_frame(sar_text, journal_text, channel, exclude_units)
        secs = sar_sections(sar_text)
        self.tables = [(parse_sar(secs[d["section"]]), d["date"])
                       for d in frame["days"]
                       if d["pairing"] == PAIRING_PAIRED]
        if not self.tables:
            raise PerturbationError(
                "no poolable day-file: every sar day is unpaired")
        self.days = [d for _, d in self.tables]
        self.span_s = len(self.days) * 86400
        self.channel = channel
        self.interval_s = interval_s
        self.exclude_units = tuple(exclude_units)
        self._map: dict = {}
        # round 472: the same ledger entries, kept for EVERY bucket rather
        # than only the costly ones. A dose-response needs an untruncated
        # response variable -- restricting it to buckets above the costly
        # threshold would censor exactly the cheap windows the hypothesis
        # predicts for cheap rounds. Filled from the same `cost_ledger`
        # entries as `_map`, so it inherits `verify()` for free.
        self._map_any: dict = {}
        self.all_bucket_bytes: dict = {}
        self.costly: set = set()
        self.bucket_bytes: dict = {}
        for di, (t, date) in enumerate(self.tables):
            probes = [Event(at_utc="%sT%02d:%02d:%02dZ"
                            % (date, s // 3600, s % 3600 // 60, s % 60),
                            label="__bucketmap_probe__")
                      for s in range(86400)]
            led = cost_ledger(probes, t, date, interval_s,
                              min_bytes=min_bytes, exclude_units=(),
                              channel=channel)
            self.min_bytes = led["min_bytes"]
            for e in led["entries"]:
                sod = _hms_to_s(e["at_utc"].split("T")[1][:8])
                key = (date, e["bucket_end"])
                self._map[(di, sod)] = key if e["costly"] else None
                self._map_any[(di, sod)] = key
                self.all_bucket_bytes[key] = e["bucket_bytes"]
                if e["costly"]:
                    self.costly.add(key)
                    self.bucket_bytes[key] = e["bucket_bytes"]
        self.n_buckets = sum(
            cost_ledger([], t, d, interval_s, min_bytes=min_bytes,
                        exclude_units=(), channel=channel)["n_buckets"]
            for t, d in self.tables)
        self._build_runs()

    # -- round 472: contiguous-run index over `_map_any`, for span queries
    def _build_runs(self) -> None:
        """`_map_any` collapsed to maximal runs of one bucket key.

        Read OFF the finished map, never recomputed from the sar rows, so it
        inherits whatever `cost_ledger` decided about post-restart rows, wide
        buckets and undefined ones. It exists because the honest per-second
        scan is O(window) and the circular-shift null over 30 windows x 2000
        offsets is 216 million lookups -- minutes of wall clock on a 1-core
        box for an answer that is 7 buckets wide. `verify_runs()` re-derives
        the scan's answer for a sample of spans and must agree exactly.
        """
        self._starts: list = []
        self._run_keys: list = []
        prev = object()
        for s in range(self.span_s):
            k = self._map_any.get((s // 86400, s % 86400))
            if k != prev:
                self._starts.append(s)
                self._run_keys.append(k)
                prev = k
        self._starts.append(self.span_s)

    def _runs_in(self, a: int, b: int) -> set:
        i = bisect.bisect_right(self._starts, a) - 1
        hit = set()
        while i < len(self._run_keys) and self._starts[i] <= b:
            k = self._run_keys[i]
            if k is not None:
                hit.add(k)
            i += 1
        return hit

    def verify_runs(self, spans: Iterable) -> dict:
        """The run index against the per-second scan, for given spans."""
        bad = []
        for a, b in spans:
            fast = self.span_buckets(a, b)
            slow = set()
            for s in range(a, b + 1):
                v = self._map_any.get(((s % self.span_s) // 86400,
                                       (s % self.span_s) % 86400))
                if v is not None:
                    slow.add(v)
            if fast != slow:
                bad.append({"span": [a, b], "only_fast": sorted(map(str, fast - slow)),
                            "only_slow": sorted(map(str, slow - fast))})
        return {"n_spans": len(list(spans)) if not isinstance(spans, list)
                            else len(spans),
                "n_divergent": len(bad), "identical": not bad,
                "divergences": bad}

    # -- population -> absolute seconds, with the ledger's own exclusions ----
    def seconds(self, fires: Iterable) -> list:
        out = []
        for ev in fires:
            if ev.label in self.exclude_units:
                continue
            date, rest = ev.at_utc.split("T")
            if date not in self.days:
                continue
            out.append(self.days.index(date) * 86400
                       + _hms_to_s(rest[:8]))
        return out

    def cover(self, seconds: Iterable, shift_s: int = 0) -> set:
        hit = set()
        for s in seconds:
            s = (s + shift_s) % self.span_s
            v = self._map.get((s // 86400, s % 86400))
            if v is not None:
                hit.add(v)
        return hit

    # -- round 472: an ISO instant, and a contiguous span, in map coordinates
    def abs_second(self, at_utc: str):
        """Absolute offset of an ISO instant in the pooled window, or None.

        `None` means the instant's DATE is not one of the pooled day-files --
        not that it is quiet. Callers must report those as untestable.
        """
        date, rest = at_utc.split("T")
        if date not in self.days:
            return None
        return self.days.index(date) * 86400 + _hms_to_s(rest[:8])

    def span_buckets(self, a: int, b: int, shift_s: int = 0) -> set:
        """Every bucket any second of [a, b] falls in, wrapped in the window.

        Costly or not. `b` is inclusive; a zero-length span is one second, not
        zero, because an instant still lands in a bucket.
        """
        if b < a:
            a, b = b, a
        if b - a + 1 >= self.span_s:
            return {k for k in self._run_keys if k is not None}
        lo = (a + shift_s) % self.span_s
        hi = lo + (b - a)
        if hi < self.span_s:
            return self._runs_in(lo, hi)
        # the shift wrapped the window past the end of the pooled span
        return self._runs_in(lo, self.span_s - 1) | self._runs_in(
            0, hi - self.span_s)

    def span_bytes(self, a: int, b: int, shift_s: int = 0) -> int:
        """Channel bytes of the distinct buckets [a, b] touches.

        Distinct: a bucket is charged ONCE however many of its seconds the
        span covers. `bucket_bytes` is a property of the bucket -- the same
        refusal to divide that `cost_ledger` documents.
        """
        return sum(self.all_bucket_bytes[k]
                   for k in self.span_buckets(a, b, shift_s))

    def verify(self, fires: Iterable) -> dict:
        """The map's answer against `cost_ledger`'s own, for one population."""
        mine = self.cover(self.seconds(fires))
        theirs = set()
        for t, date in self.tables:
            led = cost_ledger(fires, t, date, self.interval_s,
                              min_bytes=self.min_bytes,
                              exclude_units=self.exclude_units,
                              channel=self.channel)
            for e in led["entries"]:
                if e["costly"]:
                    theirs.add((date, e["bucket_end"]))
        return {"map": len(mine), "cost_ledger": len(theirs),
                "identical": mine == theirs,
                "only_in_map": sorted(f"{a} {b}" for a, b in mine - theirs),
                "only_in_cost_ledger":
                    sorted(f"{a} {b}" for a, b in theirs - mine)}


SHIFT_NULL_TRIALS = 2000


def shift_null(bmap: BucketMap, fires: Iterable, trials: int = SHIFT_NULL_TRIALS,
               seed: int = 20260903, target: Iterable = None,
               shifts: Iterable = None) -> dict:
    """Is this population's costly-bucket coverage more than its shape buys?

    Rigidly translate the whole fire train by a random offset and wrap inside
    the pooled window. Count, cadence, burst structure and inter-fire spacing
    survive untouched; only the alignment with the buckets is destroyed. That
    is the null a density argument needs, and it is not the uniform one -- see
    this section's header for the case where they disagree in opposite
    directions.

    `target` restricts the count to a subset of the costly buckets (e.g. the
    ones some other population left unnamed), so "does THIS explain what THAT
    could not" is one call rather than a hand-rolled intersection.

    `n_identity_draws` is reported because at a large effect size the only
    draws that tie the observation are those that drew offset 0 mod the span.
    A p-value sitting on its floor should be able to say whether its ties were
    real reshuffles or the null accidentally drawing the identity.

    `shifts` replaces the random draws with an explicit list of offsets. That
    exists so the identity branch above is REACHABLE by a caller: with a random
    generator over a 864 000-second span, offset 0 is drawn about once in a
    million trials, so `n_identity_draws` was a field no test could ever
    exercise -- round 466's falsifier F7 deleted the branch and nothing went
    red. It is also the deterministic-reproduction hook for a published p.
    """
    if shifts is None and trials <= 0:
        raise PerturbationError("trials must be > 0")
    rng = random.Random(seed)
    secs = bmap.seconds(fires)
    tgt = set(bmap.costly if target is None else target)
    obs = len(bmap.cover(secs) & tgt)
    offsets = ([int(x) for x in shifts] if shifts is not None
               else [rng.randrange(bmap.span_s) for _ in range(trials)])
    if not offsets:
        raise PerturbationError("no shift offsets to draw")
    trials = len(offsets)
    draws, identity, ge = [], 0, 0
    for d in offsets:
        n = len(bmap.cover(secs, d) & tgt)
        draws.append(n)
        if n >= obs:
            ge += 1
            if d % bmap.span_s == 0:
                identity += 1
    draws.sort()
    mean = sum(draws) / len(draws)
    return {
        "n_fires": len(secs),
        "n_target_buckets": len(tgt),
        "observed": obs,
        "null_mean": round(mean, 3),
        "null_p05": draws[int(0.05 * trials)],
        "null_p95": draws[int(0.95 * trials)],
        "null_max": draws[-1],
        "trials": trials,
        "n_draws_ge_observed": ge,
        "n_identity_draws": identity,
        "p_value": ge / trials,
        "p_floor": 1.0 / trials,
        "offsets_were_explicit": shifts is not None,
        "null": "circular shift of the whole fire train, wrapped in the "
                "pooled window: count, cadence and burst structure preserved, "
                "alignment destroyed",
    }


def shift_null_covered(bmap: BucketMap, fires: Iterable,
                       trials: int = SHIFT_NULL_TRIALS,
                       seed: int = 20260903,
                       restrict_to_population_days: bool = True,
                       shifts: Iterable = None) -> dict:
    """`shift_null`, with the record's own holes taken out of the null.

    Round 472. `shift_null` counts DISTINCT costly buckets named, and shifts
    the fire train over the whole pooled span. Both choices leak:

    * a fire shifted onto a stretch the sar record does not cover lands in NO
      bucket, so it can never be costly. The box was down for hours inside
      this window (rounds 184/190/196 and the whole 298-346 outage), so a
      sizeable share of every null draw is spent on ground where a hit is
      impossible. That depresses the null and inflates every effect measured
      against it.
    * a population that only exists on some days -- this program's own logins
      begin when the driver does -- is compared against draws that place it on
      days it could not occupy.

    So this scores a RATE over LANDED fires: of the fires a draw places on
    fully-recorded ground, what fraction sit in a costly bucket? Observed and
    null are then the same quantity and the holes cancel. It is strictly a
    companion to `shift_null`, not a replacement: the distinct-bucket count
    answers "how much of the record does this population reach", which is a
    real question with a real answer. It is the CAUSAL reading of that count
    that needs this.
    """
    secs = bmap.seconds(fires)
    if not secs:
        raise PerturbationError("population has no fire in the pooled window")
    if restrict_to_population_days:
        day_lo, day_hi = min(secs) // 86400, max(secs) // 86400
        base, span = day_lo * 86400, (day_hi - day_lo + 1) * 86400
    else:
        day_lo, day_hi = 0, len(bmap.days) - 1
        base, span = 0, bmap.span_s

    def rate(shift):
        landed = hot = 0
        for x in secs:
            t = base + (x - base + shift) % span
            k = bmap._map_any.get((t // 86400, t % 86400))
            if k is None:
                continue
            landed += 1
            if k in bmap.costly:
                hot += 1
        return landed, hot

    obs_landed, obs_hot = rate(0)
    if not obs_landed:
        raise PerturbationError("no fire of this population lands on covered "
                                "ground")
    obs = obs_hot / obs_landed
    rng = random.Random(seed)
    # `shifts` replaces the random draws with explicit offsets -- round 466's
    # F7 lesson, applied here on purpose. It is what makes WHOLE-DAY shifts
    # reachable: a random offset destroys time-of-day alignment along with
    # everything else, so a population and a bucket set driven by a COMMON
    # daily period would be scored as an effect. Whole-day offsets preserve
    # time-of-day exactly and destroy only the day-to-day alignment.
    offsets = ([int(x) for x in shifts] if shifts is not None
               else [rng.randrange(span) for _ in range(trials)])
    trials = len(offsets)
    draws, ge, skipped, identity = [], 0, 0, 0
    for off in offsets:
        landed, hot = rate(off)
        if not landed:
            skipped += 1
            continue
        r = hot / landed
        draws.append(r)
        if r >= obs - 1e-12:
            ge += 1
            if off % span == 0:
                identity += 1
    if not draws:
        raise PerturbationError("no draw landed a fire on covered ground")
    draws.sort()
    n = len(draws)
    return {
        "n_fires": len(secs),
        "shift_group_days": [bmap.days[day_lo], bmap.days[day_hi]],
        "n_landed_on_covered_ground": obs_landed,
        "frac_landed": round(obs_landed / len(secs), 4),
        "observed_fires_in_a_costly_bucket": obs_hot,
        "observed_rate": round(obs, 5),
        "trials": trials,
        "offsets_were_explicit": shifts is not None,
        "n_draws_scored": n,
        "n_draws_skipped": skipped,
        "null_mean_rate": round(sum(draws) / n, 5),
        "null_median_rate": round(draws[n // 2], 5),
        "null_p95_rate": round(draws[min(n - 1, int(0.95 * n))], 5),
        "n_draws_ge_observed": ge,
        # Round 466's F7 field, and it earns its keep on the FIRST use here:
        # whole-day offsets over a population whose own day range is 7 days
        # include 7 x 86400, which is the identity mod the span. Without this
        # the one tie it produces reads as a draw that beat the observation.
        "n_identity_draws": identity,
        "n_draws_ge_observed_excluding_identity": ge - identity,
        "p_value": ge / n,
        "p_value_excluding_identity": (ge - identity) / n,
        "p_floor": 1.0 / n,
        "null": "circular shift within the population's own day range, scored "
                "as a rate over the fires each draw places on fully-recorded "
                "ground",
    }


def lead_lag_profile(bmap: BucketMap, fires: Iterable,
                     offsets_s: Iterable = None,
                     interval_s: int = SAR_INTERVAL_S) -> dict:
    """The costly-bucket rate of a population displaced by +/- k buckets.

    Round 472. A circular-shift null says the alignment is not chance; it does
    not say the alignment is CAUSAL, because a population and a bucket set
    driven by a common period are aligned without either causing the other,
    and a random shift destroys that alignment exactly as it destroys a causal
    one.

    A cause has a shape the coincidence does not: it should peak at zero and
    it should not be symmetric. Memory pressure created by a login is in the
    login's own bucket and the ones after it, never in the bucket twenty
    minutes BEFORE. So the profile is the discriminator -- a sharp peak at
    zero with a heavier right tail is what a cost looks like; a flat or
    periodic profile, or one as high at -3 as at +3, is what a shared clock
    looks like.

    Displacement is NOT circular here: a fire pushed off the recorded ground
    is dropped from that offset's denominator, which is why the rate is
    reported with its own `n_landed` at every offset.
    """
    secs = bmap.seconds(fires)
    if not secs:
        raise PerturbationError("population has no fire in the pooled window")
    if offsets_s is None:
        offsets_s = [k * interval_s for k in range(-6, 7)]
    rows = []
    for off in offsets_s:
        landed = hot = 0
        for x in secs:
            t = x + off
            if not (0 <= t < bmap.span_s):
                continue
            k = bmap._map_any.get((t // 86400, t % 86400))
            if k is None:
                continue
            landed += 1
            if k in bmap.costly:
                hot += 1
        rows.append({"offset_s": off, "offset_buckets": off / interval_s,
                     "n_landed": landed, "n_costly": hot,
                     "rate": (hot / landed) if landed else None})
    at0 = next((r for r in rows if r["offset_s"] == 0), None)
    have = [r for r in rows if r["rate"] is not None and r["offset_s"] != 0]
    peak = max((r for r in rows if r["rate"] is not None),
               key=lambda r: r["rate"])
    left = [r["rate"] for r in have if r["offset_s"] < 0]
    right = [r["rate"] for r in have if r["offset_s"] > 0]
    return {
        "n_fires": len(secs),
        "interval_s": interval_s,
        "profile": rows,
        "rate_at_zero": at0["rate"] if at0 else None,
        "peak_offset_s": peak["offset_s"],
        "peak_is_at_zero": bool(at0 and peak["offset_s"] == 0),
        "mean_rate_before": (sum(left) / len(left)) if left else None,
        "mean_rate_after": (sum(right) / len(right)) if right else None,
        "asymmetry_after_minus_before": (
            (sum(right) / len(right)) - (sum(left) / len(left))
            if left and right else None),
        "why": ("a shift null rejects chance; only the SHAPE of the "
                "displacement profile separates a cost from a shared clock"),
    }


def population_coverage(sar_text: str, journal_text: str,
                        populations: dict,
                        channel: Channel = SWAP_CHANNEL,
                        min_bytes=_UNSET,
                        trials: int = SHIFT_NULL_TRIALS,
                        seed: int = 20260903,
                        bmap: BucketMap = None) -> dict:
    """What each fire population covers, and whether that is more than chance.

    Deliberately refuses to report a coverage figure without its null. Round
    436 published "33 of 52 costly buckets hold no named fire" for five rounds
    as a fact about the deployment; the number is real, and on its own it says
    nothing at all, because no one had asked what a population of that size and
    shape names when it is pointed at the wrong times.
    """
    bmap = bmap or BucketMap(sar_text, journal_text, channel, min_bytes)
    total_bytes = sum(bmap.bucket_bytes.values())
    rows = []
    for name, fires in populations.items():
        secs = bmap.seconds(fires)
        hit = bmap.cover(secs)
        rows.append({
            "population": name,
            "n_fires": len(secs),
            "n_costly_named": len(hit),
            "bytes_named": sum(bmap.bucket_bytes[b] for b in hit),
            "frac_bytes_named": (sum(bmap.bucket_bytes[b] for b in hit)
                                 / total_bytes if total_bytes else None),
            "shift_null": shift_null(bmap, fires, trials, seed),
            "shift_null_covered": shift_null_covered(bmap, fires, trials,
                                                     seed),
            "unnamed": sorted(f"{a} {b}" for a, b in bmap.costly - hit),
        })
    return {
        "channel": channel.name,
        "min_bytes": bmap.min_bytes,
        "n_days": len(bmap.days),
        "n_buckets": bmap.n_buckets,
        "n_costly_buckets": len(bmap.costly),
        "total_costly_bytes": total_bytes,
        "populations": rows,
        "why": ("coverage without a null is not evidence: a population large "
                "enough will name every bucket there is. The null holds the "
                "population's size AND shape fixed and moves only its "
                "alignment."),
    }


_SESSION_SCOPE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:[+-]\d{2}:\d{2}|Z)?\s+"
    r"\S+\s+systemd\[1\]:\s+Started\s+(session-\d+)\.scope")
_SESSION_END = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:[+-]\d{2}:\d{2}|Z)?\s+"
    r"\S+\s+systemd\[1\]:\s+(session-\d+)\.scope:\s+Deactivated successfully")

# A round is bounded by the driver's `DRIVER_ROUND_TIMEOUT_S` (3300 s) and its
# reachability probe is the FIRST thing it does, so a login caused by round N
# lands in [probe - 300 s, probe + 3300 s]. The 300 s of slack before the probe
# covers a round whose row was written after its first ssh call.
OBSERVER_WINDOW_BEFORE_S = 300
OBSERVER_WINDOW_AFTER_S = 3300
# Two clocks, both truncated to the second, and 20 of the log's rows are
# declared `coarse` (round 460). 120 s is comfortably outside that and well
# inside the ~59 s median spacing of this program's own logins.
OBSERVER_MATCH_S = 120


def session_scope_sessions(journal_text: str) -> dict:
    """The login sessions in a PID-1 journal, with their lifetimes.

    A session scope is not a service: nothing starts it, a login creates it.
    Its LIFETIME is what distinguishes an agent from a human -- `ssh host cmd`
    opens and closes one in about a second, and a person's shell does not.
    """
    starts = []
    ends: dict = {}
    for line in journal_text.splitlines():
        m = _SESSION_SCOPE.match(line)
        if m:
            starts.append((m.group(1) + "Z", m.group(2)))
        m = _SESSION_END.match(line)
        if m:
            ends.setdefault(m.group(2), []).append(m.group(1) + "Z")
    durations = []
    for at, unit in starts:
        later = sorted(x for x in ends.get(unit, []) if x >= at)
        if later:
            durations.append(
                _iso_seconds(later[0]) - _iso_seconds(at))
    durations.sort()
    n = len(durations)
    return {
        "n_sessions": len(starts),
        "n_with_a_measured_lifetime": n,
        "median_lifetime_s": (durations[n // 2] if n else None),
        "n_lifetime_le_5s": sum(1 for d in durations if d <= 5),
        "frac_lifetime_le_5s": (sum(1 for d in durations if d <= 5) / n
                                if n else None),
        "max_lifetime_s": (durations[-1] if n else None),
        "first": starts[0][0] if starts else None,
        "last": starts[-1][0] if starts else None,
        "why": ("a sub-5-second login session is a non-interactive "
                "`ssh host 'cmd'`, which is how every capture in this program "
                "was taken"),
    }


def _iso_seconds(at: str) -> int:
    d, rest = at.split("T")
    y, mo, da = (int(x) for x in d.split("-"))
    return ((y * 372 + mo * 31 + da) * 86400) + _hms_to_s(rest[:8])


def observer_trace(journal_text: str, reachability_rows: Iterable,
                   match_s: int = OBSERVER_MATCH_S) -> dict:
    """Are this journal's login sessions THIS PROGRAM's own ssh probes?

    `state/nuc-reachability-log.jsonl` records one row per E round with the
    instant its probe ran. The journal records one scope per login. If the two
    line up, then a fire population that includes session scopes is a
    population of the observer's own footprints, and any bucket it "explains"
    is explained by the act of measuring.

    Returns the match rate rather than a verdict. The log holds one row per
    ROUND and a round makes many logins, so a low session-side rate is not
    evidence against -- the probe-side rate is the one that discriminates.
    """
    starts = [at for at, _ in
              ((m.group(1) + "Z", m.group(2)) for m in
               (_SESSION_SCOPE.match(l) for l in journal_text.splitlines())
               if m)]
    if not starts:
        return {"n_sessions": 0, "n_probes_in_window": 0, "matched": [],
                "why": "no session scopes in this journal"}
    secs = sorted(_iso_seconds(a) for a in starts)
    lo, hi = secs[0], secs[-1]
    matched, unmatched = [], []
    n_probes = 0
    for r in reachability_rows:
        at = r.get("checked_at_utc")
        if not at or not r.get("ssh_reachable"):
            continue
        t = _iso_seconds(at)
        if not (lo <= t <= hi):
            continue
        n_probes += 1
        delta = min(secs, key=lambda s: abs(s - t)) - t
        (matched if abs(delta) <= match_s else unmatched).append(
            {"round": r.get("round"), "checked_at_utc": at,
             "nearest_session_start_delta_s": delta,
             "precision": r.get("precision")})
    return {
        "n_sessions": len(starts),
        "session_window": [starts[0], starts[-1]],
        "n_probes_in_window": n_probes,
        "n_probes_matched": len(matched),
        "frac_probes_matched": (len(matched) / n_probes if n_probes else None),
        "match_s": match_s,
        "n_probes_matched_within_1s":
            sum(1 for m in matched
                if abs(m["nearest_session_start_delta_s"]) <= 1),
        "matched": matched,
        "unmatched": unmatched,
        "why": ("a successful ssh probe IS a login and a login IS a session "
                "scope; if the reachability log's instants sit on the "
                "journal's scope starts, the two files are recording the same "
                "events and the scopes are this program's own footprints"),
    }


def observer_confounding(bmap: BucketMap, journal_text: str,
                         reachability_rows: Iterable,
                         before_s: int = OBSERVER_WINDOW_BEFORE_S,
                         after_s: int = OBSERVER_WINDOW_AFTER_S) -> dict:
    """Do the costly buckets a scope population names sit in E-ROUND windows?

    The question `observer_trace` cannot answer. That the scopes are our
    logins makes them a suspect population; this asks whether the buckets they
    name are concentrated where this program was working, which is what turns
    "suspect" into "confounded".

    Dates before the reachability log's first row are reported as UNTESTABLE
    rather than as negatives -- absence of a probe row on 2026-08-23 is the log
    not existing yet, not the box being quiet.
    """
    probes = sorted(_iso_seconds(r["checked_at_utc"])
                    for r in reachability_rows
                    if r.get("checked_at_utc") and r.get("ssh_reachable"))
    if not probes:
        raise PerturbationError("no successful probe in the reachability rows")
    first_date = min(r["checked_at_utc"][:10] for r in reachability_rows
                     if r.get("checked_at_utc") and r.get("ssh_reachable"))
    scopes = parse_unit_starts_any_kind(journal_text, ("scope",))
    named = bmap.cover(bmap.seconds(scopes))

    def in_window(b):
        t = _iso_seconds(f"{b[0]}T{b[1]}")
        return any(-before_s <= (t - p) <= after_s for p in probes)

    testable = sorted(b for b in bmap.costly if b[0] >= first_date)
    untestable = sorted(b for b in bmap.costly if b[0] < first_date)
    a = sum(1 for b in testable if b in named and in_window(b))
    bq = sum(1 for b in testable if b in named and not in_window(b))
    c = sum(1 for b in testable if b not in named and in_window(b))
    d = sum(1 for b in testable if b not in named and not in_window(b))
    return {
        "first_probe_date": first_date,
        "n_costly": len(bmap.costly),
        "n_testable": len(testable),
        "n_untestable_before_the_log_existed": len(untestable),
        "untestable": sorted(f"{x} {y}" for x, y in untestable),
        "window_s": [before_s, after_s],
        "table": {"scope_named_in_window": a, "scope_named_outside": bq,
                  "other_in_window": c, "other_outside": d},
        "fisher_two_sided_p": _fisher_2x2(a, bq, c, d),
        "why": ("a scope population that names buckets uniformly over the "
                "window is measuring the box; one whose buckets sit inside "
                "this program's own round windows is measuring the program"),
    }


# Round 466 refused to take this decision alone and said exactly why:
# `sysstat-collect` is excluded from the fire population because it WRITES the
# bucket it would be charged for; a session scope would be excluded because it
# IS the observer. Those are different reasons and the second one deserves a
# written decision with both tables published, not a silent filter.
SESSION_SCOPE_RE = re.compile(r"^session-\d+\.scope$")


def is_session_scope(label: str) -> bool:
    return bool(SESSION_SCOPE_RE.match(label))


def session_exclusion_tables(sar_text: str, journal_text: str,
                             kinds: Iterable = ("service", "scope"),
                             channel: Channel = SWAP_CHANNEL,
                             min_bytes=_UNSET,
                             trials: int = SHIFT_NULL_TRIALS,
                             seed: int = 20260903,
                             bmap: BucketMap = None) -> dict:
    """Round 466 item 2: BOTH tables for the session-scope exclusion.

    Returns the widened population's coverage with session scopes IN and with
    them OUT, the delta each way, and what the decision would do to every
    number round 466 published. It does not apply an exclusion anywhere --
    `LEDGER_EXCLUDE_UNITS` is untouched by this function on purpose, so that
    reading the tables cannot move a published figure by itself.
    """
    kinds = tuple(kinds)
    bmap = bmap or BucketMap(sar_text, journal_text, channel, min_bytes)
    widened = parse_unit_starts_any_kind(journal_text, kinds)
    kept = [e for e in widened if not is_session_scope(e.label)]
    dropped = [e for e in widened if is_session_scope(e.label)]
    pops = {
        "published (PID-1 `Starting` .service)": parse_unit_starts(journal_text),
        f"widened ({','.join(kinds)}) WITH session scopes": widened,
        f"widened ({','.join(kinds)}) WITHOUT session scopes": kept,
        "session scopes ONLY": dropped,
    }
    cov = population_coverage(sar_text, journal_text, pops, channel,
                              min_bytes, trials, seed, bmap=bmap)
    by = {r["population"]: r for r in cov["populations"]}
    a = by[f"widened ({','.join(kinds)}) WITH session scopes"]
    b = by[f"widened ({','.join(kinds)}) WITHOUT session scopes"]
    return {
        "n_widened_fires": len(widened),
        "n_session_scope_fires": len(dropped),
        "frac_of_widened_that_is_session_scopes":
            (len(dropped) / len(widened) if widened else None),
        "n_costly": len(bmap.costly),
        "total_costly_bytes": sum(bmap.bucket_bytes.values()),
        "coverage": cov,
        "delta_if_excluded": {
            "n_costly_named": b["n_costly_named"] - a["n_costly_named"],
            "bytes_named": b["bytes_named"] - a["bytes_named"],
            "frac_bytes_named": (None if a["frac_bytes_named"] is None
                                 else round(b["frac_bytes_named"]
                                            - a["frac_bytes_named"], 4)),
        },
        "decision_is_load_bearing": (a["n_costly_named"]
                                     != b["n_costly_named"]),
        "why": ("both tables, because the exclusion is not obviously right: "
                "if this program's own traffic really costs the box four "
                "gigabytes of swap, that is a fact about the deployment and "
                "hiding it is worse than naming it"),
    }


def _fisher_2x2(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact, by summing tables no likelier than observed."""
    n = a + b + c + d
    if n == 0:
        return 1.0
    comb = math.comb
    p0 = comb(a + b, a) * comb(c + d, c) / comb(n, a + c)
    tot = 0.0
    for i in range(0, min(a + b, a + c) + 1):
        k = a + c - i
        if k < 0 or k > c + d:
            continue
        p = comb(a + b, i) * comb(c + d, k) / comb(n, a + c)
        if p <= p0 * (1 + 1e-9):
            tot += p
    return min(1.0, tot)


def _load(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _stitch_arg(spec, next_table: SarTable, next_date: str,
                interval_s: int):
    """`--stitch-prev FILE:DATE` -> a `Stitch`, or None when not asked for.

    The date of the file being stitched INTO must be known; when the verb has
    no `--date` (the `gap` verb does not), it is derived as prev_date + 1 day,
    which is the only date a legitimate stitch could have."""
    if not spec:
        return None
    path, _, prev_date = spec.rpartition(":")
    if not path or not prev_date:
        raise SystemExit(f"--stitch-prev wants FILE:DATE, got {spec!r}")
    prev = parse_sar(_load(path))
    if not next_date:
        nxt = _date.fromordinal(_date_ordinal(prev_date) + 1)
        next_date = nxt.isoformat()
    return stitch_from(prev, prev_date, next_table, next_date, interval_s)


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
    sl.add_argument("--min-bytes", type=int, default=None,
                    help="default: the channel's derived threshold, if it has "
                         "one (the commit channel does not -- see "
                         "CHANNEL_MIN_BYTES)")
    sl.add_argument("--include-instrument", action="store_true",
                    help="do NOT exclude sysstat-collect (see LEDGER_EXCLUDE_UNITS)")
    sl.add_argument("--channel", default="swap", choices=sorted(CHANNELS),
                    help="swap = sar -W pswpout/s (default); commit = sar -r "
                         "kbcommit; steal = sar -B pgsteal/s. --sar-w takes "
                         "whichever file matches.")
    sl.add_argument("--stitch-prev", default=None, metavar="FILE:DATE",
                    help="round 418: the PREVIOUS day-file and its date, so a "
                         "level channel can cost this file's first bucket. "
                         "Refused unless the two days are consecutive, the "
                         "columns match, and no LINUX RESTART sits between "
                         "them. No-op on a rate channel.")

    se = sub.add_parser("evidence",
                        help="round 406: does a ledger actually license "
                             "\"unit X cost this\"?")
    se.add_argument("--ledger", action="append", required=True,
                    metavar="FILE",
                    help="JSON from `perturbation.py ledger`; repeat once per "
                         "sar day-file -- pooling days is the point")
    se.add_argument("--unit", default=None,
                    help="report only this unit (default: every unit)")
    se.add_argument("--max-family-p", type=float,
                    default=ATTRIBUTION_MAX_FAMILY_P)
    se.add_argument("--min-consistency", type=float,
                    default=ATTRIBUTION_MIN_CONSISTENCY)

    sf = sub.add_parser(
        "power",
        help="round 412: could ANY unit have been supported in a record of "
             "this shape? Pure arithmetic -- no data needed")
    sf.add_argument("--n-buckets", type=int, required=True)
    sf.add_argument("--n-costly-buckets", type=int, required=True)
    sf.add_argument("--n-units-tested", type=int, required=True)
    sf.add_argument("--max-family-p", type=float,
                    default=ATTRIBUTION_MAX_FAMILY_P)

    ss = sub.add_parser(
        "sweep",
        help="round 412: re-grade the record at every costly-threshold, so a "
             "verdict that is really a setting shows up as one")
    ss.add_argument("--day", action="append", required=True, metavar="FILE:DATE",
                    help="a sar day-file and the date it covers; repeat per day")
    ss.add_argument("--journal", required=True)
    ss.add_argument("--channel", default="swap", choices=sorted(CHANNELS))
    ss.add_argument("--thresholds", default=None,
                    help="comma-separated byte thresholds (default: a decade "
                         "sweep from one page to 1 GiB)")
    ss.add_argument("--interval-s", type=int, default=SAR_INTERVAL_S)
    ss.add_argument("--stitch", action="store_true",
                    help="round 418: join consecutive --day files so a level "
                         "channel can cost each day's first bucket")

    sr = sub.add_parser(
        "reclaim",
        help="round 418: what the page-reclaim path did (sar -B). Answers "
             "\"what touched already-committed pages\" -- the question left "
             "when the commit channel says nothing was allocated")
    sr.add_argument("--sar-b", required=True, help="`sar -B` text")
    sr.add_argument("--date", default="")
    sr.add_argument("--interval-s", type=int, default=SAR_INTERVAL_S)

    sy = sub.add_parser(
        "gap",
        help="round 418: per reclaim bucket, what the LEVEL channel said "
             "about it -- the eviction-vs-allocation blindness, as a ratio")
    sy.add_argument("--sar-b", required=True)
    sy.add_argument("--sar-r", required=True, help="the same day's `sar -r`")
    sy.add_argument("--channel", default="commit", choices=sorted(CHANNELS))
    sy.add_argument("--interval-s", type=int, default=SAR_INTERVAL_S)
    sy.add_argument("--stitch-prev", default=None, metavar="FILE:DATE",
                    help="previous day's file for the LEVEL table")

    swin = sub.add_parser(
        "window",
        help="round 430: pooled attribution over EVERY poolable day-file in a "
             "capture, with the frame that says which days were dropped")
    swin.add_argument("--capture", required=True,
                      help="a state/nuc-capture-* directory, or the "
                           "`sar-all.txt` inside one")
    swin.add_argument("--journal", default=None,
                      help="default: <capture>/journal-pid1-full.txt")
    swin.add_argument("--channel", default="swap", choices=sorted(CHANNELS))
    swin.add_argument("--min-bytes", type=int, default=None)
    swin.add_argument("--interval-s", type=int, default=SAR_INTERVAL_S)
    swin.add_argument("--stitch", action="store_true")
    swin.add_argument("--include-unpaired", action="store_true",
                      help="pool sar days the journal is silent on. This RAISES "
                           "N and LOWERS every p; it is here to measure the "
                           "hazard, not to switch it off")
    swin.add_argument("--frame-only", action="store_true",
                      help="print the day/journal pairing and stop")
    swin.add_argument("--inflation", action="store_true",
                      help="run it both ways and report what the unpaired days "
                           "did to every unit's p_family")
    swin.add_argument("--max-family-p", type=float,
                      default=ATTRIBUTION_MAX_FAMILY_P)
    swin.add_argument("--min-consistency", type=float,
                      default=ATTRIBUTION_MIN_CONSISTENCY)
    swin.add_argument("--strict", action="store_true",
                      help="exit 1 if any day-file was dropped as unpaired")

    sj = sub.add_parser(
        "journal",
        help="round 436: what a banked journal file actually holds, and "
             "which of its sections are copies of another")
    sj.add_argument("--journal", required=True)

    sen = sub.add_parser(
        "engine",
        help="round 436: the engine's own log lines as placed events")
    sen.add_argument("--journal", required=True)
    sen.add_argument("--completion-shift-s", type=float, default=0.0,
                     help="move COMPLETION-semantics events this many seconds "
                          "earlier; 0.0 = placed where they were logged, the "
                          "only placement the record states")
    sen.add_argument("--events", action="store_true",
                     help="print every event, not just the summary")
    sen.add_argument("--user-units", action="store_true",
                     help="also report `systemd[pid != 1]: Starting` lines, "
                          "services AND sockets -- round 430's item-5 "
                          "hypothesis, measured")

    spl = sub.add_parser(
        "place",
        help="round 436: which engine attributions survive the "
             "completion-placement choice")
    spl.add_argument("--journal", required=True)
    spl.add_argument("--capture", required=True)
    spl.add_argument("--channel", default="swap", choices=sorted(CHANNELS))
    spl.add_argument("--min-bytes", type=int, default=None)
    spl.add_argument("--shifts", default="0,300,600",
                     help="comma-separated seconds")

    so = sub.add_parser(
        "oom",
        help="round 436: the OOM kills in a capture, and what the channel "
             "recorded around each")
    so.add_argument("--journal", action="append", required=True,
                    metavar="FILE", help="repeat for system AND user journals")
    so.add_argument("--capture", default=None)
    so.add_argument("--channel", default="swap", choices=sorted(CHANNELS))
    so.add_argument("--min-bytes", type=int, default=None)

    sst = sub.add_parser(
        "stability",
        help="round 436: does the engine's verdict survive the placement the "
             "record cannot pin?")
    sst.add_argument("--capture", required=True)
    sst.add_argument("--engine-journal", required=True)
    sst.add_argument("--channel", default="steal", choices=sorted(CHANNELS))
    sst.add_argument("--min-bytes", type=int, default=None)
    sst.add_argument("--shifts", default="0,150,300,600,1200")

    sws = sub.add_parser(
        "wsweep",
        help="round 436: `window` re-run at every threshold, carrying the "
             "six-gate table -- for a channel with no derived threshold")
    sws.add_argument("--capture", required=True)
    sws.add_argument("--journal", default=None)
    sws.add_argument("--channel", default="steal", choices=sorted(CHANNELS))
    sws.add_argument("--thresholds", default=None)
    sws.add_argument("--interval-s", type=int, default=SAR_INTERVAL_S)
    sws.add_argument("--stitch", action="store_true")
    sws.add_argument("--engine-journal", default=None,
                     help="a user journal whose engine events are pooled in "
                          "as extra fires (round 436 item 5)")
    sws.add_argument("--completion-shift-s", type=float, default=0.0)
    sws.add_argument("--max-family-p", type=float,
                     default=ATTRIBUTION_MAX_FAMILY_P)
    sws.add_argument("--min-consistency", type=float,
                     default=ATTRIBUTION_MIN_CONSISTENCY)

    spop = sub.add_parser(
        "population",
        help="round 466: what each fire population covers, WITH the "
             "circular-shift null that says whether the coverage is more "
             "than its size and shape buy")
    spop.add_argument("--capture", required=True)
    spop.add_argument("--journal", default=None,
                      help="default: <capture>/journal-pid1-full.txt")
    spop.add_argument("--engine-journal", default=None,
                      help="pool the engine's own events in as a population")
    spop.add_argument("--channel", default="swap", choices=sorted(CHANNELS))
    spop.add_argument("--min-bytes", type=int, default=None)
    spop.add_argument("--trials", type=int, default=SHIFT_NULL_TRIALS)
    spop.add_argument("--seed", type=int, default=20260903)
    spop.add_argument("--kinds", default="service,scope",
                      help="comma-separated unit kinds to add as a widened "
                           "population (default service,scope)")
    spop.add_argument("--verify", action="store_true",
                      help="print the BucketMap self-check against "
                           "`cost_ledger` for every population and exit 1 on "
                           "any divergence")

    sobs = sub.add_parser(
        "observer",
        help="round 466: are this journal's login sessions THIS PROGRAM's own "
             "ssh probes, and do the buckets they name sit in E-round windows")
    sobs.add_argument("--journal", required=True)
    sobs.add_argument("--log", default="state/nuc-reachability-log.jsonl")
    sobs.add_argument("--capture", default=None,
                      help="also run the confounding test, which needs the "
                           "bucket grid")
    sobs.add_argument("--channel", default="swap", choices=sorted(CHANNELS))
    sobs.add_argument("--min-bytes", type=int, default=None)
    sobs.add_argument("--census", action="store_true",
                      help="also print the unit-kind census")
    sobs.add_argument("--strict", action="store_true",
                      help="exit 1 if the journal's session scopes match this "
                           "program's own probes, i.e. if a scope-inclusive "
                           "fire population would be measuring the observer")

    sx = sub.add_parser(
        "exclusion",
        help="round 466 item 2: both tables for the `session-*.scope` "
             "exclusion decision, and what excluding would move")
    sx.add_argument("--capture", required=True)
    sx.add_argument("--journal", default=None)
    sx.add_argument("--channel", default="swap", choices=sorted(CHANNELS))
    sx.add_argument("--min-bytes", type=int, default=None)
    sx.add_argument("--trials", type=int, default=SHIFT_NULL_TRIALS)
    sx.add_argument("--seed", type=int, default=20260903)
    sx.add_argument("--kinds", default="service,scope")

    sd = sub.add_parser(
        "direct",
        help="round 436: systemd's own per-invocation cgroup accounting, and "
             "how it compares with the inferred verdicts")
    sd.add_argument("--journal", action="append", required=True,
                    metavar="FILE",
                    help="repeat for the system AND user journals")
    sd.add_argument("--capture", default=None,
                    help="cross-check against the window verdicts from this "
                         "capture")
    sd.add_argument("--channel", default="swap", choices=sorted(CHANNELS))
    sd.add_argument("--min-bytes", type=int, default=None)
    sd.add_argument("--verbs", action="store_true",
                    help="also report which units only ever say `Started`")

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
            min_bytes=_UNSET if args.min_bytes is None else args.min_bytes,
            exclude_units=() if args.include_instrument
            else LEDGER_EXCLUDE_UNITS,
            channel=CHANNELS[args.channel],
            stitch=_stitch_arg(args.stitch_prev, table, args.date,
                               args.interval_s)), indent=2))
    elif args.mode == "reclaim":
        print(json.dumps(reclaim_summary(
            parse_sar(_load(args.sar_b)), args.date, args.interval_s),
            indent=2))
    elif args.mode == "gap":
        level = parse_sar(_load(args.sar_r))
        print(json.dumps(eviction_gap(
            parse_sar(_load(args.sar_b)), level,
            channel=CHANNELS[args.channel], interval_s=args.interval_s,
            stitch=_stitch_arg(args.stitch_prev, level, "", args.interval_s)),
            indent=2))
    elif args.mode == "power":
        print(json.dumps(power_floor(
            args.n_buckets, args.n_costly_buckets, args.n_units_tested,
            args.max_family_p), indent=2))
    elif args.mode == "sweep":
        tables = []
        for spec in args.day:
            path, _, date = spec.rpartition(":")
            if not path or not date:
                raise SystemExit(f"--day wants FILE:DATE, got {spec!r}")
            tables.append((parse_sar(_load(path)), date))
        fires = parse_unit_starts(_load(args.journal))
        ths = ([int(x) for x in args.thresholds.split(",")]
               if args.thresholds
               else [4096, 1 << 15, 1 << 17, 1 << 19, LEDGER_MIN_BYTES,
                     1 << 23, 1 << 25, 1 << 27, 1 << 30])
        print(json.dumps(channel_sweep(
            fires, tables, CHANNELS[args.channel], ths,
            interval_s=args.interval_s, stitch=args.stitch), indent=2))
    elif args.mode == "evidence":
        result = attribution_evidence(
            [json.loads(_load(f)) for f in args.ledger],
            max_family_p=args.max_family_p,
            min_consistency=args.min_consistency)
        if args.unit:
            result = dict(result, units=[u for u in result["units"]
                                         if u["unit"] == args.unit])
        print(json.dumps(result, indent=2))
    elif args.mode == "window":
        cap = args.capture
        sar_path = (cap if cap.endswith(".txt")
                    else os.path.join(cap, "sar-all.txt"))
        jrnl_path = args.journal or (
            sar_path if sar_path.endswith(".txt") and args.journal
            else os.path.join(os.path.dirname(sar_path) or ".",
                              "journal-pid1-full.txt"))
        sar_text, jrnl_text = _load(sar_path), _load(jrnl_path)
        chan = CHANNELS[args.channel]
        mb = _UNSET if args.min_bytes is None else args.min_bytes
        if args.frame_only:
            out = window_frame(sar_text, jrnl_text, chan)
        elif args.inflation:
            out = unpaired_inflation(sar_text, jrnl_text, chan, mb,
                                     interval_s=args.interval_s,
                                     stitch=args.stitch,
                                     max_family_p=args.max_family_p,
                                     min_consistency=args.min_consistency)
        else:
            out = window_attribution(
                sar_text, jrnl_text, chan, mb,
                interval_s=args.interval_s, stitch=args.stitch,
                include_unpaired=args.include_unpaired,
                max_family_p=args.max_family_p,
                min_consistency=args.min_consistency)
        print(json.dumps(out, indent=2))
        frame = out.get("frame", out if "n_sar_only" in out else {})
        if args.strict and frame.get("n_sar_only", 0):
            print(f"perturbation window: {frame['n_sar_only']} day-file(s) "
                  f"dropped as unpaired: {frame.get('dropped_dates')}",
                  file=sys.stderr)
            return 1
    elif args.mode == "journal":
        text = _load(args.journal)
        _clean, rep = dedupe_journal(text)
        rep["user_unit_starts_services_only"] = [
            e.label for e in parse_user_unit_starts(_clean)]
        rep["user_unit_starts_all_kinds"] = _hist(
            e.label for e in parse_user_unit_starts(
                _clean, ("service", "socket", "target", "timer")))
        rep["pid1_unit_starts_in_this_file"] = len(parse_unit_starts(_clean))
        clean_ev = engine_event_summary(parse_engine_events(_clean,
                                                             dedupe=False))
        naive_ev = engine_event_summary(parse_engine_events(text,
                                                            dedupe=False))
        rep["engine"] = clean_ev
        # The line-level inflation factor is the WRONG number to quote here.
        # The redundant view is 329 of 4054 record lines (1.088x) because the
        # file is mostly `sshd`, while the events it duplicates inflate by
        # very nearly 2x. A reader who checks the totals sees 9% and moves on.
        rep["engine_inflation_if_not_deduped"] = {
            "n_events_naive": naive_ev["n_events"],
            "n_events_deduped": clean_ev["n_events"],
            "factor_events": (round(naive_ev["n_events"]
                                    / clean_ev["n_events"], 4)
                              if clean_ev["n_events"] else None),
            "factor_record_lines": rep["inflation_factor_naive"],
            "by_label": {k: [naive_ev["by_label"].get(k, 0), v]
                         for k, v in clean_ev["by_label"].items()},
            "why": ("the line-level factor is diluted by 2774 `sshd` lines "
                    "the duplicated view does not contain; the per-EVENT "
                    "factor is the one a count is exposed to"),
        }
        print(json.dumps(rep, indent=2))
    elif args.mode == "engine":
        text = _load(args.journal)
        evs = parse_engine_events(text,
                                  completion_shift_s=args.completion_shift_s)
        out = {"completion_shift_s": args.completion_shift_s,
               "summary": engine_event_summary(evs)}
        if args.user_units:
            clean, _ = dedupe_journal(text)
            out["user_units"] = {
                "services": _hist(e.label for e in
                                  parse_user_unit_starts(clean)),
                "all_kinds": _hist(
                    e.label for e in parse_user_unit_starts(
                        clean, ("service", "socket", "target", "timer"))),
                "pid1_starts_found_by_parse_unit_starts":
                    len(parse_unit_starts(clean)),
            }
        if args.events:
            out["events"] = [e.as_dict() for e in evs]
        print(json.dumps(out, indent=2))
    elif args.mode == "place":
        cap = args.capture
        sar_path = (cap if cap.endswith(".txt")
                    else os.path.join(cap, "sar-all.txt"))
        print(json.dumps(engine_placement_sensitivity(
            _load(args.journal), _load(sar_path),
            channel=CHANNELS[args.channel],
            min_bytes=(_UNSET if args.min_bytes is None else args.min_bytes),
            shifts=tuple(float(x) for x in args.shifts.split(","))), indent=2))
    elif args.mode == "wsweep":
        cap = args.capture
        sar_path = (cap if cap.endswith(".txt")
                    else os.path.join(cap, "sar-all.txt"))
        jrnl_path = args.journal or os.path.join(
            os.path.dirname(sar_path) or ".", "journal-pid1-full.txt")
        extra = ()
        if args.engine_journal:
            extra = parse_engine_events(
                _load(args.engine_journal),
                completion_shift_s=args.completion_shift_s)
        ths = ([int(x) for x in args.thresholds.split(",")]
               if args.thresholds
               else [4096, 1 << 15, 1 << 17, 1 << 19, LEDGER_MIN_BYTES,
                     1 << 23, 1 << 25, 1 << 27, 1 << 30])
        print(json.dumps(window_sweep(
            _load(sar_path), _load(jrnl_path), CHANNELS[args.channel], ths,
            interval_s=args.interval_s, stitch=args.stitch,
            extra_fires=extra, max_family_p=args.max_family_p,
            min_consistency=args.min_consistency), indent=2))
    elif args.mode == "population":
        cap = args.capture
        sar_path = (cap if cap.endswith(".txt")
                    else os.path.join(cap, "sar-all.txt"))
        jrnl_path = args.journal or os.path.join(
            os.path.dirname(sar_path) or ".", "journal-pid1-full.txt")
        sar_t, jr_t = _load(sar_path), _load(jrnl_path)
        bmap = BucketMap(sar_t, jr_t, CHANNELS[args.channel],
                         (_UNSET if args.min_bytes is None else args.min_bytes))
        kinds = tuple(x.strip() for x in args.kinds.split(",") if x.strip())
        pops = {
            "published (PID-1 `Starting` .service)": parse_unit_starts(jr_t),
            "round 436 complete (+ `Started`-only .service)":
                parse_unit_starts_complete(jr_t),
            f"widened ({','.join(kinds)})":
                parse_unit_starts_any_kind(jr_t, kinds),
        }
        for k in kinds:
            if k != "service":
                pops[f"{k} ONLY"] = parse_unit_starts_any_kind(jr_t, (k,))
        if args.engine_journal:
            pops["engine events"] = parse_engine_events(
                _load(args.engine_journal))
        if args.verify:
            checks = {k: bmap.verify(v) for k, v in pops.items()}
            print(json.dumps({"verify": checks}, indent=2))
            return 0 if all(c["identical"] for c in checks.values()) else 1
        print(json.dumps(population_coverage(
            sar_t, jr_t, pops, CHANNELS[args.channel],
            (_UNSET if args.min_bytes is None else args.min_bytes),
            trials=args.trials, seed=args.seed, bmap=bmap), indent=2))
    elif args.mode == "exclusion":
        cap = args.capture
        sar_path = (cap if cap.endswith(".txt")
                    else os.path.join(cap, "sar-all.txt"))
        jrnl_path = args.journal or os.path.join(
            os.path.dirname(sar_path) or ".", "journal-pid1-full.txt")
        sar_t, jr_t = _load(sar_path), _load(jrnl_path)
        print(json.dumps(session_exclusion_tables(
            sar_t, jr_t,
            tuple(x.strip() for x in args.kinds.split(",") if x.strip()),
            CHANNELS[args.channel],
            (_UNSET if args.min_bytes is None else args.min_bytes),
            trials=args.trials, seed=args.seed), indent=2))
    elif args.mode == "observer":
        jr_t = _load(args.journal)
        rows = [json.loads(x) for x in _load(args.log).splitlines() if x.strip()]
        out = {"sessions": session_scope_sessions(jr_t),
               "trace": observer_trace(jr_t, rows)}
        if args.census:
            out["census"] = unit_kind_census(jr_t)
        if args.capture:
            cap = args.capture
            sar_path = (cap if cap.endswith(".txt")
                        else os.path.join(cap, "sar-all.txt"))
            bmap = BucketMap(
                _load(sar_path), jr_t, CHANNELS[args.channel],
                (_UNSET if args.min_bytes is None else args.min_bytes))
            out["confounding"] = observer_confounding(bmap, jr_t, rows)
        print(json.dumps(out, indent=2))
        if args.strict:
            t = out["trace"]
            return 1 if (t["n_probes_in_window"]
                         and t["frac_probes_matched"] >= 0.5) else 0
    elif args.mode == "direct":
        texts = [_load(f) for f in args.journal]
        recs = [r for t in texts for r in parse_resource_accounting(t)]
        out = {"journals": args.journal, "direct": direct_cost_table(recs)}
        if args.verbs:
            out["verb_audit"] = [unit_start_verb_audit(t) for t in texts]
        if args.capture:
            cap = args.capture
            sar_path = (cap if cap.endswith(".txt")
                        else os.path.join(cap, "sar-all.txt"))
            jrnl_path = os.path.join(os.path.dirname(sar_path) or ".",
                                     "journal-pid1-full.txt")
            win = window_attribution(
                _load(sar_path), _load(jrnl_path), CHANNELS[args.channel],
                (_UNSET if args.min_bytes is None else args.min_bytes))
            out["cross_check"] = direct_vs_inferred(
                win["evidence"], recs,
                costly_threshold_bytes=(
                    win["per_day"][0]["min_bytes"] if win["per_day"]
                    else LEDGER_MIN_BYTES))
        print(json.dumps(out, indent=2, default=str))
    elif args.mode == "stability":
        cap = args.capture
        sar_path = (cap if cap.endswith(".txt")
                    else os.path.join(cap, "sar-all.txt"))
        jrnl_path = os.path.join(os.path.dirname(sar_path) or ".",
                                 "journal-pid1-full.txt")
        print(json.dumps(engine_verdict_stability(
            _load(sar_path), _load(jrnl_path), _load(args.engine_journal),
            CHANNELS[args.channel],
            (_UNSET if args.min_bytes is None else args.min_bytes),
            shifts=tuple(float(x) for x in args.shifts.split(","))), indent=2))
    elif args.mode == "oom":
        evs = [e for f in args.journal for e in parse_oom_kills(_load(f))]
        eps = oom_episodes(evs)
        out = {"journals": args.journal, "n_oom_lines": len(evs),
               "n_episodes": len(eps), "episodes": eps}
        if args.capture:
            cap = args.capture
            sar_path = (cap if cap.endswith(".txt")
                        else os.path.join(cap, "sar-all.txt"))
            out["context"] = oom_cost_context(
                eps, _load(sar_path), CHANNELS[args.channel],
                (_UNSET if args.min_bytes is None else args.min_bytes))
        print(json.dumps(out, indent=2, default=str))
    elif args.mode == "timers":
        print(json.dumps([asdict(t) | {"avoidable": t.avoidable}
                          for t in NUC_TIMERS], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
