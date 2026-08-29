#!/usr/bin/env python3
"""swap_analysis.py — offline analysis for datasets `swap_watch.py` collected.

Rounds 244/256/262/268/274/280/286/298 each hand-rolled a fresh one-off
Python snippet (burst tally, inter-arrival gaps, the `pswpout` cross-check)
against whatever partial or final `swap_watch.py` output they had on hand —
round 298's own knowledge file says so explicitly ("this round re-derived
[the burst/summary fields] independently from raw samples as a cross-check").
This module is that snippet, promoted to a tested, reusable tool: given any
`swap_watch.py` output (a final `--out` JSON, or a `--checkpoint` `.jsonl`
that never reached a final write), it reproduces the same burst tally,
inter-arrival-gap statistics, and `pswpout`-vs-`memory.swap.current`
cross-check every one of those rounds computed by hand — validated against
round 268's own complete 8h dataset (`state/nuc-swap-watch-r292/
swap-watch-r268-long.json`) to reproduce round 298's exact published numbers
byte-for-byte.

Stdlib only. Pure analysis — never touches the network or the NUC.

Usage:
    python3 swap_analysis.py <path-to-swap-watch-output.json|.jsonl>
    python3 swap_analysis.py <path> --json   # machine-readable, full detail
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import asdict
from pathlib import Path

# swap_watch.py lives next to this file on both the NUC and in this repo.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import swap_watch  # noqa: E402

DEFAULT_PAGE_BYTES = 4096


class SwapAnalysisError(RuntimeError):
    pass


def load_samples(path: str) -> list:
    """Load a list of `swap_watch.Sample` from either output shape.

    A `--checkpoint` file is a `.jsonl` (one Sample dict per line, no
    trailing bursts/summary — the run may never have reached a final `--out`
    write, which is exactly the case a checkpoint exists to survive). A
    `--out` file is a single JSON object with a top-level "samples" list of
    the same per-sample dicts. Both use the identical field set (whatever
    `dataclasses.asdict(Sample(...))` produces), so one Sample(**d) works
    for either source.
    """
    p = Path(path)
    text = p.read_text()
    if p.suffix == ".jsonl" or (text.lstrip()[:1] == "{" and "\n{" in text):
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        obj = json.loads(text)
        rows = obj["samples"] if isinstance(obj, dict) and "samples" in obj else obj
    if not rows:
        raise SwapAnalysisError(f"{path}: no samples found")
    try:
        return [swap_watch.Sample(**row) for row in rows]
    except TypeError as e:
        raise SwapAnalysisError(f"{path}: sample row missing/extra fields: {e}") from e


def interarrival_gaps(samples: list, bursts: list) -> list:
    """Seconds of flat (non-burst) time before each burst started.

    Gap for burst 0 is measured from the run's first sample (a lower bound —
    the true prior event, if any, predates the run's own start). Gap for
    burst i>0 is measured from burst i-1's END (its own duration is real
    growth time, not part of the quiescent gap). This is the exact
    definition round 298's "gap since prior event" column used.
    """
    gaps = []
    prev_t = samples[0].t_unix
    for b in bursts:
        gaps.append(b.start_t - prev_t)
        prev_t = b.end_t
    return gaps


def tail_gap(samples: list, bursts: list) -> float:
    """Seconds of flat time between the last burst's end and the run's end
    (or the whole run's span, if no burst was ever observed)."""
    if not bursts:
        return samples[-1].t_unix - samples[0].t_unix
    return samples[-1].t_unix - bursts[-1].end_t


def bursts_per_hour(bursts: list, span_s: float) -> float:
    if span_s <= 0:
        return 0.0
    return len(bursts) / (span_s / 3600.0)


def gap_statistics(gaps: list) -> dict | None:
    """mean/min/max/stdev/coefficient-of-variation over a list of gap
    seconds. Returns None if fewer than 2 gaps (stdev is undefined, and a
    single gap says nothing about variability). CV (stdev/mean) is the
    formal version of the ad hoc "Nx spread" framing prior rounds used —
    for a Poisson (memoryless-arrival) process, inter-arrival CV -> 1;
    CV > 1 indicates clustering beyond what pure randomness predicts, CV < 1
    indicates more regular/periodic spacing than randomness predicts. NOTE:
    with the single 8h dataset this module was validated against, there are
    only 3 "interior" gaps (see `analyze`'s docstring) — nowhere near enough
    to treat CV as a real statistical claim; it is reported as a descriptive
    number, not a hypothesis-test result.
    """
    if len(gaps) < 2:
        return None
    mean = statistics.mean(gaps)
    stdev = statistics.stdev(gaps)
    return {
        "n": len(gaps),
        "mean_s": mean,
        "min_s": min(gaps),
        "max_s": max(gaps),
        "stdev_s": stdev,
        "cv": (stdev / mean) if mean > 0 else None,
    }


def pswpout_crosscheck(samples: list, bursts: list, page_bytes: int = DEFAULT_PAGE_BYTES) -> list:
    """Per-burst: does `vmstat`'s `pswpout` counter (system-wide pages
    swapped out) agree with the cgroup's own `memory.swap.current` delta for
    that burst? Rounds 286/298 found 3/4 bursts exact (ratio 1.0000) and one
    persistently ~0.65% high — this reproduces that computation generically
    against any dataset instead of the one-off it started as.
    """
    by_seq = {s.seq: s for s in samples}
    out = []
    for b in bursts:
        s0, s1 = by_seq.get(b.start_seq), by_seq.get(b.end_seq)
        if s0 is None or s1 is None:
            raise SwapAnalysisError(
                f"burst references seq {b.start_seq}/{b.end_seq} not present in samples "
                "(mismatched/truncated dataset)")
        pswpout_bytes = (s1.pswpout_pages - s0.pswpout_pages) * page_bytes
        swap_delta = b.delta_bytes
        out.append({
            "start_seq": b.start_seq,
            "end_seq": b.end_seq,
            "swap_delta_bytes": swap_delta,
            "pswpout_bytes": pswpout_bytes,
            "ratio": (pswpout_bytes / swap_delta) if swap_delta else None,
        })
    return out


def analyze(samples: list, threshold_bytes: int = swap_watch.DEFAULT_BURST_THRESHOLD_BYTES,
            page_bytes: int = DEFAULT_PAGE_BYTES) -> dict:
    """Full report: burst list, summary, inter-arrival gaps (+ statistics
    over the "interior" gaps only — every gap except the first, which is
    bounded by the run's own start rather than a true prior event, matching
    round 298's own reasoning for excluding it from a rate claim), the tail
    gap since the last burst, and the pswpout cross-check.
    """
    bursts = swap_watch.find_bursts(samples, threshold_bytes)
    summary = swap_watch.summarize(samples, bursts)
    gaps = interarrival_gaps(samples, bursts)
    interior_gaps = gaps[1:]  # exclude the run-start-bounded first gap
    # dataclasses.asdict() only captures Burst's real fields, not its
    # duration_s/delta_bytes/rate_mb_per_hr @property helpers -- add those
    # in explicitly so callers (format_report, --json consumers) get them
    # without re-deriving from start/end fields themselves.
    burst_dicts = [{**asdict(b), "duration_s": b.duration_s, "delta_bytes": b.delta_bytes,
                     "rate_mb_per_hr": b.rate_mb_per_hr} for b in bursts]
    return {
        "n_samples": len(samples),
        "bursts": burst_dicts,
        "summary": summary,
        "bursts_per_hour": bursts_per_hour(bursts, summary["span_s"]),
        "interarrival_gaps_s": gaps,
        "interior_gap_statistics": gap_statistics(interior_gaps),
        "tail_gap_s": tail_gap(samples, bursts),
        "pswpout_crosscheck": pswpout_crosscheck(samples, bursts, page_bytes),
    }


def format_report(result: dict) -> str:
    lines = [
        f"samples: {result['n_samples']}, span: {result['summary']['span_s'] / 3600.0:.3f}h",
        f"bursts: {result['summary']['n_bursts']} "
        f"({result['bursts_per_hour']:.3f}/hour average over the full span)",
        f"wide-window rate: {result['summary']['wide_window_rate_mb_per_hr']:.2f} MB/hr",
    ]
    for i, (b, g) in enumerate(zip(result["bursts"], result["interarrival_gaps_s"])):
        lines.append(
            f"  burst {i + 1}: +{b['delta_bytes'] / 1e6:.2f} MB over "
            f"{b['duration_s']:.1f}s, gap since prior event {g:.1f}s")
    lines.append(f"  tail gap (last burst -> run end): {result['tail_gap_s']:.1f}s")
    stats = result["interior_gap_statistics"]
    if stats:
        lines.append(
            f"interior gap stats (n={stats['n']}): mean={stats['mean_s']:.1f}s "
            f"min={stats['min_s']:.1f}s max={stats['max_s']:.1f}s cv={stats['cv']:.3f}")
    else:
        lines.append("interior gap stats: not enough bursts (need >= 2 interior gaps)")
    lines.append("pswpout cross-check:")
    for c in result["pswpout_crosscheck"]:
        ratio = f"{c['ratio']:.4f}" if c["ratio"] is not None else "n/a"
        lines.append(
            f"  seq {c['start_seq']}-{c['end_seq']}: swap_delta={c['swap_delta_bytes']} "
            f"pswpout_bytes={c['pswpout_bytes']} ratio={ratio}")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("path", help="swap_watch.py --out JSON, or --checkpoint .jsonl")
    p.add_argument("--burst-threshold-bytes", type=int,
                    default=swap_watch.DEFAULT_BURST_THRESHOLD_BYTES)
    p.add_argument("--page-bytes", type=int, default=DEFAULT_PAGE_BYTES)
    p.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = p.parse_args(argv)

    try:
        samples = load_samples(args.path)
        result = analyze(samples, args.burst_threshold_bytes, args.page_bytes)
    except SwapAnalysisError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2) if args.json else format_report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
