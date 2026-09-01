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
import math
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
            steal_exceeds_scan=st > (sk + sd)))
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
    evs = [e for e in events if (e.scan_kswapd_s + e.scan_direct_s) > 0]
    if not evs:
        return {"n_events": 0, "verdict": "no scanned buckets to test",
                "divisor": divisor}
    rep = [e.vmeff_pct for e in evs]
    cor = [v / divisor for v in rep]
    return {
        "n_events": len(evs),
        "divisor": divisor,
        "ceiling_pct": ceiling_pct,
        "max_reported_pct": max(rep),
        "max_corrected_pct": max(cor),
        "n_over_ceiling_reported": sum(1 for v in rep if v > ceiling_pct),
        "n_over_ceiling_corrected": sum(1 for v in cor if v > ceiling_pct),
        "n_near_ceiling": sum(1 for v in cor
                              if ceiling_pct - near_pct <= v <= ceiling_pct),
        "ceiling_restored": all(v <= ceiling_pct + 1e-9 for v in cor),
        "corrected_pct": cor,
        "why": ("dividing pgsteal by %g puts every bucket at or under the "
                "%g%% reclaim-efficiency ceiling (max %.3f%%), which %d of %d "
                "buckets violate as reported"
                % (divisor, ceiling_pct, max(cor),
                   sum(1 for v in rep if v > ceiling_pct), len(rep))
                if all(v <= ceiling_pct + 1e-9 for v in cor) else
                "divisor %g does NOT restore the ceiling: %d bucket(s) still "
                "exceed %g%%" % (divisor,
                                 sum(1 for v in cor if v > ceiling_pct),
                                 ceiling_pct)),
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


# ------------------------------------------------------------------- CLI


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
    elif args.mode == "timers":
        print(json.dumps([asdict(t) | {"avoidable": t.avoidable}
                          for t in NUC_TIMERS], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
