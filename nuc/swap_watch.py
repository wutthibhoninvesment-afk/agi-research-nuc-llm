#!/usr/bin/env python3
"""swap_watch.py — tight-interval poller for qwen36-colibri's swap growth.

Round 244 found passive `memory.swap.current` growth on this box is BURSTY,
not smoothly decelerating: a wide-window (hours) before/after delta can
disagree with the instantaneous rate by 6x+ depending on where the window
boundary falls relative to burst timing. That round's own recommendation
(closing this gap) was a tight poll of `memory.swap.current` every 10-30s
for 10-20 minutes to catch a burst in progress and measure its
size/duration directly, instead of re-deriving another wide-window average.

This script is that tool. Stdlib only (runs on the NUC's bare Python 3.12).
Read-only: it only `cat`s cgroup v2 accounting files and `/proc/vmstat` —
never touches the colibri/toolproxy processes or ports 8000/8080/8001.

Usage (run ON the box — cgroup paths are local-only, not network-reachable):
    python3 swap_watch.py --interval 15 --duration 900 --out swap-watch.json

Output: JSON with every raw sample plus a derived burst list (a "burst" is
any consecutive-sample delta > --burst-threshold-bytes, default 1 MiB —
comfortably above this cgroup file's effective read noise, which round 244
found to be exactly 0 bytes across a flat 3-minute control window).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field

DEFAULT_UNIT = "qwen36-colibri.service"
DEFAULT_SLICE = "user.slice/user-1000.slice/user@1000.service/app.slice"
DEFAULT_BURST_THRESHOLD_BYTES = 1024 * 1024  # 1 MiB; see module docstring
VMSTAT_PATH = "/proc/vmstat"


class SwapWatchError(RuntimeError):
    pass


def cgroup_dir(unit: str, slice_path: str) -> str:
    return f"/sys/fs/cgroup/{slice_path}/{unit}"


def read_int_file(path: str) -> int:
    with open(path) as f:
        return int(f.read().strip())


def read_vmstat_counters(path: str = VMSTAT_PATH) -> dict:
    out = {}
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2 and parts[0] in ("pswpin", "pswpout"):
                out[parts[0]] = int(parts[1])
    return out


@dataclass
class Sample:
    seq: int
    t_unix: float
    swap_bytes: int
    mem_current_bytes: int
    pswpin_pages: int
    pswpout_pages: int


@dataclass
class Burst:
    """A run of consecutive samples where swap strictly increased each step."""
    start_seq: int
    end_seq: int
    start_t: float
    end_t: float
    start_bytes: int
    end_bytes: int

    @property
    def duration_s(self) -> float:
        return self.end_t - self.start_t

    @property
    def delta_bytes(self) -> int:
        return self.end_bytes - self.start_bytes

    @property
    def rate_mb_per_hr(self) -> float:
        if self.duration_s <= 0:
            return float("inf")
        return (self.delta_bytes / 1e6) / (self.duration_s / 3600.0)


def collect(unit: str, slice_path: str, interval_s: float, duration_s: float,
            checkpoint_path: str | None = None) -> list:
    """Poll swap/mem/vmstat counters until duration_s elapses.

    If checkpoint_path is given, each sample is appended as one JSON line and
    flushed+fsynced immediately, so a run interrupted mid-flight (box reboot,
    OOM, session loss) leaves recoverable partial data on disk rather than
    losing everything — the final `--out` JSON is otherwise only written once,
    at the very end, which is fine for the short (<20 min) polls this script
    was originally built for but not for a genuinely multi-hour unattended run.
    """
    cg = cgroup_dir(unit, slice_path)
    swap_path = f"{cg}/memory.swap.current"
    mem_path = f"{cg}/memory.current"
    samples = []
    seq = 0
    t_start = time.time()
    ckpt_f = open(checkpoint_path, "a") if checkpoint_path else None
    try:
        while True:
            now = time.time()
            vmstat = read_vmstat_counters()
            sample = Sample(
                seq=seq,
                t_unix=now,
                swap_bytes=read_int_file(swap_path),
                mem_current_bytes=read_int_file(mem_path),
                pswpin_pages=vmstat.get("pswpin", -1),
                pswpout_pages=vmstat.get("pswpout", -1),
            )
            samples.append(sample)
            if ckpt_f is not None:
                ckpt_f.write(json.dumps(asdict(sample)) + "\n")
                ckpt_f.flush()
                os.fsync(ckpt_f.fileno())
            seq += 1
            if now - t_start >= duration_s:
                break
            time.sleep(interval_s)
    finally:
        if ckpt_f is not None:
            ckpt_f.close()
    return samples


def find_bursts(samples: list, threshold_bytes: int) -> list:
    """Group consecutive strictly-increasing-swap samples into bursts.

    A burst starts at the first sample of a growth run and ends at the last
    sample before growth stops (inclusive), so its duration spans exactly
    the polling window in which growth was observed — a lower bound on the
    true burst duration, since the real start/end can fall between polls.
    """
    bursts = []
    i = 1
    n = len(samples)
    while i < n:
        delta = samples[i].swap_bytes - samples[i - 1].swap_bytes
        if delta > threshold_bytes:
            start = i - 1
            end = i
            while end + 1 < n and samples[end + 1].swap_bytes > samples[end].swap_bytes:
                end += 1
            bursts.append(Burst(
                start_seq=samples[start].seq,
                end_seq=samples[end].seq,
                start_t=samples[start].t_unix,
                end_t=samples[end].t_unix,
                start_bytes=samples[start].swap_bytes,
                end_bytes=samples[end].swap_bytes,
            ))
            i = end + 1
        else:
            i += 1
    return bursts


def summarize(samples: list, bursts: list) -> dict:
    if not samples:
        return {"n_samples": 0}
    total_delta = samples[-1].swap_bytes - samples[0].swap_bytes
    total_span_s = samples[-1].t_unix - samples[0].t_unix
    flat_samples = len(samples) - 1 - sum(b.end_seq - b.start_seq for b in bursts)
    return {
        "n_samples": len(samples),
        "span_s": total_span_s,
        "total_delta_bytes": total_delta,
        "wide_window_rate_mb_per_hr": (
            (total_delta / 1e6) / (total_span_s / 3600.0) if total_span_s > 0 else 0.0
        ),
        "n_bursts": len(bursts),
        "flat_inter_sample_gaps": flat_samples,
        "burst_sizes_bytes": [b.delta_bytes for b in bursts],
        "burst_durations_s": [b.duration_s for b in bursts],
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--unit", default=DEFAULT_UNIT)
    p.add_argument("--slice-path", default=DEFAULT_SLICE)
    p.add_argument("--interval", type=float, default=15.0, help="seconds between polls")
    p.add_argument("--duration", type=float, default=900.0, help="total watch time, seconds")
    p.add_argument("--burst-threshold-bytes", type=int, default=DEFAULT_BURST_THRESHOLD_BYTES)
    p.add_argument("--out", default=None, help="write JSON here (default: stdout)")
    p.add_argument("--checkpoint", default=None,
                    help="append each sample as a JSON line here as it's collected "
                         "(recommended for runs longer than ~20 min, so an "
                         "interruption doesn't lose all samples)")
    args = p.parse_args(argv)

    try:
        samples = collect(args.unit, args.slice_path, args.interval, args.duration,
                           checkpoint_path=args.checkpoint)
    except OSError as e:
        raise SwapWatchError(f"failed reading cgroup/vmstat files: {e}") from e

    bursts = find_bursts(samples, args.burst_threshold_bytes)
    result = {
        "unit": args.unit,
        "interval_s": args.interval,
        "duration_s": args.duration,
        "burst_threshold_bytes": args.burst_threshold_bytes,
        "samples": [asdict(s) for s in samples],
        "bursts": [asdict(b) for b in bursts],
        "summary": summarize(samples, bursts),
    }
    text = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
