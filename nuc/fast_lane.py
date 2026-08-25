#!/usr/bin/env python3
"""fast_lane.py — feasibility planner for a second, small model lane next to a
RAM-saturated production engine (mission E4: OLMoE-1B-7B int8 beside Qwen3.6).

Stdlib only. Three questions, each answerable offline from facts gathered
read-only on the target box:

  1. bandwidth  — parse `curl -w` samples, model the download time of a set of
                  objects from PER-OBJECT rates (HF's CDN serves different
                  shards at 7x different rates), gate against a threshold.
  2. ram        — the production engine's expert cache is the only knob:
                  RSS(cap) = RSS_full - (cap_full - cap) * layers * expert_bytes.
                  Given the small lane's footprint, compute the cap the big
                  engine would have to run at, and what that costs it.
  3. lane       — project a lane turn (prefill + decode) against the E1 curve
                  of the production engine for the same prompt.

Plus the transfer helper: `transfer_cmd()` streams a local file to the box
through ssh into `fast_lane_sink.py`, which writes with fdatasync +
posix_fadvise(DONTNEED) per chunk so a multi-GB copy never grows the page
cache under an engine that already sits at its cgroup ceiling.

Safety: refuses any URL/base on port 8001 (frontier lane rule).
"""
from __future__ import annotations

import argparse
import json
import math
import shlex
import statistics
import sys
from dataclasses import asdict, dataclass, field
from typing import Iterable, Optional, Sequence
from urllib.parse import urlparse

FORBIDDEN_PORTS = {8001}
MB = 1_000_000
GB = 1_000_000_000
GIB = 1024 ** 3

# curl -w template used by every probe; parse_curl_w() reads it back.
CURL_W = ("speed_B_s=%{speed_download} bytes=%{size_download} t=%{time_total} "
          "http=%{http_code} ttfb=%{time_starttransfer} ip=%{remote_ip}\\n")


class FastLaneError(RuntimeError):
    pass


def check_url(url: str) -> str:
    """Reject forbidden ports (defaults: 80/443 by scheme)."""
    parsed = urlparse(url)
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    if port in FORBIDDEN_PORTS:
        raise FastLaneError(f"refusing to touch port {port} (frontier lane rule)")
    return url


# ------------------------------------------------------------------ bandwidth

@dataclass
class BandwidthSample:
    url: str
    bytes: int
    seconds: float
    http_code: int = 0
    ttfb_s: float = 0.0
    remote_ip: str = ""
    label: str = ""

    @property
    def mb_s(self) -> float:
        return self.bytes / self.seconds / MB if self.seconds > 0 else 0.0


def probe_cmd(url: str, seconds: float = 30.0, ipv: Optional[int] = None,
              user_agent: str = "fast-lane-probe") -> list[str]:
    """argv for one bandwidth sample: download to /dev/null for `seconds`."""
    check_url(url)
    argv = ["curl", "-sSL", "-A", user_agent, "--max-time", str(seconds),
            "-o", "/dev/null", "-w", CURL_W]
    if ipv in (4, 6):
        argv.insert(1, f"-{ipv}")
    argv.append(url)
    return argv


def parse_curl_w(line: str, url: str = "", label: str = "") -> BandwidthSample:
    """Parse one CURL_W output line (`speed_B_s=… bytes=… t=… http=… ttfb=… ip=…`)."""
    fields = {}
    for tok in line.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            fields[k] = v
    try:
        nbytes = int(float(fields["bytes"]))
        secs = float(fields["t"])
    except (KeyError, ValueError) as exc:
        raise FastLaneError(f"unparseable curl line: {line!r}") from exc
    return BandwidthSample(url=url, bytes=nbytes, seconds=secs,
                           http_code=int(fields.get("http", 0) or 0),
                           ttfb_s=float(fields.get("ttfb", 0) or 0),
                           remote_ip=fields.get("ip", ""), label=label)


def parse_probe_log(text: str) -> list[BandwidthSample]:
    """Parse the `== <url>` / curl -w line pairs the probe loops print."""
    samples, url = [], ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("== "):
            url = line[3:].split()[-1]
        elif line.startswith("speed_B_s="):
            samples.append(parse_curl_w(line, url=url))
    return samples


@dataclass
class BandwidthSummary:
    n: int
    min_mb_s: float
    median_mb_s: float
    max_mb_s: float
    spread: float                     # max/min — 1.0 means one stable rate
    per_url_mb_s: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


def summarize(samples: Sequence[BandwidthSample]) -> BandwidthSummary:
    ok = [s for s in samples if s.http_code == 200 and s.bytes > 0]
    if not ok:
        raise FastLaneError("no successful samples")
    rates = [s.mb_s for s in ok]
    per_url: dict[str, list[float]] = {}
    for s in ok:
        per_url.setdefault(s.url, []).append(s.mb_s)
    return BandwidthSummary(
        n=len(ok), min_mb_s=min(rates), median_mb_s=statistics.median(rates),
        max_mb_s=max(rates), spread=(max(rates) / min(rates)) if min(rates) > 0 else math.inf,
        per_url_mb_s={u: statistics.median(v) for u, v in per_url.items()})


def download_time_s(objects: dict[str, int], rates_mb_s: dict[str, float],
                    fallback_mb_s: Optional[float] = None) -> float:
    """Seconds to fetch `objects` (name -> bytes) when each object streams at
    its OWN measured rate (name -> MB/s). Objects without a rate use the
    fallback (default: the slowest measured rate — the honest choice)."""
    if not rates_mb_s:
        raise FastLaneError("no rates")
    fb = fallback_mb_s if fallback_mb_s is not None else min(rates_mb_s.values())
    total = 0.0
    for name, size in objects.items():
        rate = rates_mb_s.get(name, fb)
        if rate <= 0:
            raise FastLaneError(f"non-positive rate for {name}")
        total += size / (rate * MB)
    return total


@dataclass
class GateDecision:
    ok: bool
    reasons: list[str]
    min_rate_mb_s: float
    threshold_mb_s: float
    disk_free_gb: float
    disk_needed_gb: float


def gate_download(min_rate_mb_s: float, disk_free_gb: float, disk_needed_gb: float,
                  threshold_mb_s: float = 3.0, disk_margin_gb: float = 20.0) -> GateDecision:
    """Mission gate: sustained rate > threshold AND disk allows (with margin)."""
    reasons = []
    if min_rate_mb_s <= threshold_mb_s:
        reasons.append(f"slowest sustained rate {min_rate_mb_s:.2f} MB/s <= {threshold_mb_s} MB/s")
    if disk_free_gb - disk_needed_gb < disk_margin_gb:
        reasons.append(f"disk: {disk_free_gb:.0f} GB free - {disk_needed_gb:.1f} GB needed "
                       f"< {disk_margin_gb} GB margin")
    return GateDecision(ok=not reasons, reasons=reasons, min_rate_mb_s=min_rate_mb_s,
                        threshold_mb_s=threshold_mb_s, disk_free_gb=disk_free_gb,
                        disk_needed_gb=disk_needed_gb)


# ------------------------------------------------------------------ RAM planner

@dataclass(frozen=True)
class MoeGeometry:
    """What a streamed-MoE engine keeps in RAM per cached expert."""
    name: str
    layers: int
    experts: int
    expert_bytes: int          # bytes per cached expert slot (weights + scales)
    dense_bytes: int           # resident dense weights (after load)
    kv_bytes_per_token: int    # context-proportional state per token
    fixed_bytes: int = 0       # context-independent state (recurrent etc.)

    def cache_bytes(self, cap: int) -> int:
        cap = max(0, min(cap, self.experts))
        return cap * self.layers * self.expert_bytes

    def footprint(self, cap: int, ctx: int, workspace_bytes: int = 0) -> int:
        return (self.dense_bytes + self.cache_bytes(cap) + self.kv_bytes_per_token * ctx
                + self.fixed_bytes + workspace_bytes)


# Qwen3.6-35B-A3B int4 gs64 container on pgain-nuc (read from the shard headers):
#   expert = 1,572,864 B U8 merged + 196,608 B F32 scales; 40 layers x 256 experts.
#   dense 2.862 GB + embed 2.034 GB on disk; "RSS after load: 9.25 GB" (journal).
#   K/V 40,960 B/token (10 attention layers, 2 KV heads x 256 x fp32 x 2), DeltaNet
#   state 65.9 MB context-independent (round 28).
QWEN36 = MoeGeometry("qwen36", layers=40, experts=256, expert_bytes=1_572_864 + 196_608,
                     dense_bytes=int(9.25 * GB), kv_bytes_per_token=40_960,
                     fixed_bytes=65_900_000)

# OLMoE-1B-7B int8 merged container: 16 layers x 64 experts, hidden 2048, inter 1024.
#   expert = 3 x 2048 x 1024 int8 = 6,291,456 B + 3 x 1024 f32 scales (2048-row gate/up,
#   1024-row down ... row scales: gate 1024 + up 1024 + down 2048 = 4096 x 4 B).
#   dense ~1.8 GB f32 (chat_olmoe.sh comment: "~6GB cache + ~1.8GB dense = 7.8GB peak").
#   KV: layers x ctx x heads(16) x head_dim(128) x 2 x 4 B  (family_registry _olmoe_geometry).
OLMOE = MoeGeometry("olmoe", layers=16, experts=64, expert_bytes=6_291_456 + 4096 * 4,
                    dense_bytes=int(1.8 * GB), kv_bytes_per_token=16 * 16 * 128 * 2 * 4)


def rss_at_cap(geom: MoeGeometry, rss_full: int, cap_full: int, cap: int) -> int:
    """Engine RSS when the cache holds `cap` instead of `cap_full` experts/layer."""
    if not (0 <= cap <= geom.experts and 0 < cap_full <= geom.experts):
        raise FastLaneError("cap out of range")
    return rss_full - (cap_full - cap) * geom.layers * geom.expert_bytes


def cap_for_free_bytes(geom: MoeGeometry, rss_full: int, cap_full: int,
                       ram_total: int, need_free: int, os_reserve: int) -> int:
    """Largest cap such that ram_total - os_reserve - RSS(cap) >= need_free.
    Returns -1 when even cap 0 cannot make room."""
    budget = ram_total - os_reserve - need_free
    if budget < rss_at_cap(geom, rss_full, cap_full, 0):
        return -1
    slack = budget - rss_at_cap(geom, rss_full, cap_full, 0)
    cap = int(slack // (geom.layers * geom.expert_bytes))
    return max(0, min(cap, cap_full))


def expected_miss_fraction(cap: int, experts: int, skew: float = 0.0) -> float:
    """Fraction of routed-expert lookups that miss an LRU cache of `cap` slots.
    skew=0 → uniform routing (miss = 1 - cap/experts); skew in (0,1] moves the
    hot mass into the cache (an optimistic, pinned-hot-set model)."""
    if not 0 <= cap <= experts:
        raise FastLaneError("cap out of range")
    uniform_hit = cap / experts
    hit = uniform_hit + skew * (1.0 - uniform_hit)
    return max(0.0, 1.0 - hit)


@dataclass
class CapCost:
    cap: int
    rss_gb: float
    freed_gb: float
    miss_fraction: float
    decode_penalty_s_per_token: float
    prefill_penalty_s_per_request: float


def cap_cost(geom: MoeGeometry, rss_full: int, cap_full: int, cap: int,
             topk: int, nvme_mb_s: float, skew: float = 0.0,
             prefill_layers_touch_all: bool = True) -> CapCost:
    """What the production engine pays at a reduced cap.
    decode: misses/token x expert_bytes / disk rate.
    prefill: a batched prefill touches ~every expert per layer, so every slot
    the cache lacks streams once per request."""
    rss = rss_at_cap(geom, rss_full, cap_full, cap)
    miss = expected_miss_fraction(cap, geom.experts, skew)
    per_byte_s = 1.0 / (nvme_mb_s * MB)
    decode = miss * topk * geom.layers * geom.expert_bytes * per_byte_s
    missing = (geom.experts - cap) if prefill_layers_touch_all else int(miss * geom.experts)
    prefill = missing * geom.layers * geom.expert_bytes * per_byte_s
    return CapCost(cap=cap, rss_gb=rss / GB, freed_gb=(rss_full - rss) / GB,
                   miss_fraction=miss, decode_penalty_s_per_token=decode,
                   prefill_penalty_s_per_request=prefill)


# ------------------------------------------------------------------ lane projection

@dataclass
class LaneTurn:
    prompt_tokens: int
    reply_tokens: int
    prefill_s: float
    decode_s: float
    total_s: float


E1_POINTS = ((0, 2.4), (134, 23.3), (904, 143.1), (3998, 770.3))   # (prompt tokens, TTFT s)


def qwen36_prefill_s(tokens: int) -> float:
    """Measured E1 curve (round 16): piecewise-linear through the measured
    points (fixed overhead 2.4 s at 0 tokens; 23.3 s @134, 143.1 s @904,
    770.3 s @3998), extrapolated beyond 4k with the last segment's slope
    (0.203 s/token → 1581 s @8k; E1's least-squares extrapolation said 1551).
    Decided in round 100: a fitted line under-/over-shoots the measured points
    by up to 12 %, so the projection uses the points themselves."""
    if tokens < 0:
        raise FastLaneError("tokens must be >= 0")
    pts = E1_POINTS
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if tokens <= x1:
            return y0 + (y1 - y0) * (tokens - x0) / (x1 - x0)
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    return y1 + (y1 - y0) / (x1 - x0) * (tokens - x1)


def lane_turn(prompt_tokens: int, reply_tokens: int, prefill_tps: float,
              decode_tps: float, overhead_s: float = 0.5) -> LaneTurn:
    if prefill_tps <= 0 or decode_tps <= 0:
        raise FastLaneError("rates must be positive")
    pre = overhead_s + prompt_tokens / prefill_tps
    dec = reply_tokens / decode_tps
    return LaneTurn(prompt_tokens, reply_tokens, pre, dec, pre + dec)


def qwen36_turn(prompt_tokens: int, reply_tokens: int, decode_tps: float = 3.3) -> LaneTurn:
    pre = qwen36_prefill_s(prompt_tokens)
    dec = reply_tokens / decode_tps
    return LaneTurn(prompt_tokens, reply_tokens, pre, dec, pre + dec)


# ------------------------------------------------------------------ transfer

def transfer_cmd(local_path: str, ssh_target: str, remote_path: str,
                 ssh_key: Optional[str] = None, sink: str = "~/nuc-research/fast_lane_sink.py",
                 chunk_mb: int = 8, sync_every_mb: int = 256) -> str:
    """Shell pipeline: stream a local file into the page-cache-safe sink on the box."""
    ssh = ["ssh"] + (["-i", ssh_key] if ssh_key else []) + [ssh_target]
    remote = (f"python3 {sink} --out {shlex.quote(remote_path)} "
              f"--chunk-mb {int(chunk_mb)} --sync-every-mb {int(sync_every_mb)}")
    return f"cat {shlex.quote(local_path)} | {' '.join(ssh)} {shlex.quote(remote)}"


# ------------------------------------------------------------------ CLI

def full_footprint(resident_bytes: int, swapped_bytes: int) -> int:
    """The engine's true size at its current cap: what the cgroup holds in RAM
    PLUS what it pushed to swap. On pgain-nuc (2026-08-24) the qwen36 worker
    sat at memory.max (32.21 GB) with 4.21 GB in swap — RSS alone under-states
    the footprint by 13 % and every cap computed from it is wrong."""
    return int(resident_bytes) + int(swapped_bytes)


def plan_rows(geom: MoeGeometry, lane: MoeGeometry, rss_full: int, cap_full: int,
              ram: int, reserve: int, lane_caps: Iterable[int], lane_ctx: int,
              nvme_mb_s: float, skew: float, topk: int = 8,
              lane_workspace: int = int(0.3 * GB)) -> list[tuple[int, int, int, Optional[CapCost]]]:
    """(lane_cap, lane_bytes, big_cap, cost) per lane size; lane cap 0 = no lane,
    i.e. the cap at which the production engine merely stops swapping."""
    rows = []
    for lane_cap in lane_caps:
        need = 0 if lane_cap == 0 else lane.footprint(lane_cap, lane_ctx, workspace_bytes=lane_workspace)
        cap = cap_for_free_bytes(geom, rss_full, cap_full, ram, need, reserve)
        cost = cap_cost(geom, rss_full, cap_full, cap, topk=topk,
                        nvme_mb_s=nvme_mb_s, skew=skew) if cap >= 0 else None
        rows.append((lane_cap, need, cap, cost))
    return rows


def _plan_table(args) -> str:
    geom = QWEN36
    rss_full = full_footprint(int(args.resident_gb * GB), int(args.swapped_gb * GB))
    ram = int(args.ram_gib * GIB)
    reserve = int(args.os_reserve_gb * GB)
    rows = plan_rows(geom, OLMOE, rss_full, args.cap_full, ram, reserve, (0, 16, 32, 64),
                     args.lane_ctx, args.nvme_mb_s, args.skew)
    out = [f"# RAM plan: {geom.name} cap {args.cap_full} = {rss_full / GB:.2f} GB "
           f"(resident {args.resident_gb:.2f} + swapped {args.swapped_gb:.2f}); "
           f"RAM {args.ram_gib} GiB; OS reserve {args.os_reserve_gb} GB; lane ctx {args.lane_ctx}; "
           f"NVMe {args.nvme_mb_s:.0f} MB/s; routing skew {args.skew}",
           "| lane cap | lane needs GB | qwen36 cap | qwen36 GB | miss % | decode +s/tok | prefill +s/req |",
           "|---|---|---|---|---|---|---|"]
    for lane_cap, need, cap, cost in rows:
        label = "none (stop swapping)" if lane_cap == 0 else str(lane_cap)
        if cost is None:
            out.append(f"| {label} | {need / GB:.2f} | impossible | — | — | — | — |")
        else:
            out.append(f"| {label} | {need / GB:.2f} | {cap} | {cost.rss_gb:.2f} | "
                       f"{cost.miss_fraction * 100:.0f} | {cost.decode_penalty_s_per_token:.3f} | "
                       f"{cost.prefill_penalty_s_per_request:.1f} |")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("parse", help="summarize a probe log (== url / curl -w lines)")
    p.add_argument("log")
    p.add_argument("--json", action="store_true")

    g = sub.add_parser("gate", help="apply the download gate")
    g.add_argument("--min-rate", type=float, required=True)
    g.add_argument("--disk-free-gb", type=float, required=True)
    g.add_argument("--disk-needed-gb", type=float, required=True)
    g.add_argument("--threshold", type=float, default=3.0)

    r = sub.add_parser("plan", help="RAM/cap plan for the OLMoE lane beside qwen36")
    # pgain-nuc 2026-08-24: cgroup memory.current 32,211,791,872 B (= memory.max),
    # memory.swap.current 4,214,800,384 B, MemTotal 32,751,620 kB.
    r.add_argument("--resident-gb", type=float, default=32.212)
    r.add_argument("--swapped-gb", type=float, default=4.215)
    r.add_argument("--cap-full", type=int, default=256)
    r.add_argument("--ram-gib", type=float, default=31.234)
    r.add_argument("--os-reserve-gb", type=float, default=1.2)
    r.add_argument("--lane-ctx", type=int, default=2048)
    r.add_argument("--nvme-mb-s", type=float, default=1500.0)
    r.add_argument("--skew", type=float, default=0.0)

    t = sub.add_parser("turn", help="project a lane turn vs qwen36")
    t.add_argument("--prompt", type=int, default=600)
    t.add_argument("--reply", type=int, default=150)
    t.add_argument("--prefill-tps", type=float, default=30.0)
    t.add_argument("--decode-tps", type=float, default=6.0)

    x = sub.add_parser("transfer-cmd", help="print the page-cache-safe transfer pipeline")
    x.add_argument("local")
    x.add_argument("target")
    x.add_argument("remote")
    x.add_argument("--key", default=None)

    a = ap.parse_args(argv)
    if a.cmd == "parse":
        with open(a.log, encoding="utf-8", errors="replace") as fh:
            s = summarize(parse_probe_log(fh.read()))
        print(json.dumps(s.as_dict(), indent=2) if a.json else
              f"n={s.n} min={s.min_mb_s:.2f} median={s.median_mb_s:.2f} max={s.max_mb_s:.2f} "
              f"MB/s spread={s.spread:.1f}x")
    elif a.cmd == "gate":
        d = gate_download(a.min_rate, a.disk_free_gb, a.disk_needed_gb, a.threshold)
        print(json.dumps(asdict(d), indent=2))
        return 0 if d.ok else 2
    elif a.cmd == "plan":
        print(_plan_table(a))
    elif a.cmd == "turn":
        lane = lane_turn(a.prompt, a.reply, a.prefill_tps, a.decode_tps)
        big = qwen36_turn(a.prompt, a.reply)
        print(json.dumps({"lane": asdict(lane), "qwen36": asdict(big),
                          "speedup": big.total_s / lane.total_s}, indent=2))
    elif a.cmd == "transfer-cmd":
        print(transfer_cmd(a.local, a.target, a.remote, ssh_key=a.key))
    return 0


if __name__ == "__main__":
    sys.exit(main())
