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
                  ROUND 382: this is a RELATIVE model and it now REFUSES an
                  anchor that cannot be full residency (`anchor_soundness`),
                  rather than warning and answering. For pgain-nuc at cap 256
                  no sound anchor can exist — cap-256 residency is 44.00 GB
                  against a 32.21 GB `memory.max` — so `plan` with its default
                  arguments refuses and points at `nuc/expert_cache.py plan`,
                  which is absolute and needs no anchor. Give it a cap whose
                  residency actually fits (159) and it answers again.
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
import os
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


class UnsoundAnchorError(FastLaneError):
    """ROUND 382. The relative RAM planner was asked to extrapolate from an
    anchor that cannot be full residency.

    Round 376 established the fact and shipped it in the WRONG LAYER: the
    strong soundness test (`implied_dense >= geom.dense_bytes`) lived in
    `_plan_table` as a printed WARNING, while only its degenerate case
    (`implied_dense >= 0`) was enforced in the arithmetic. So the CLI warned
    and every library caller -- `plan_rows`, `cap_cost`, `cap_for_free_bytes`
    -- got an unwarned wrong number. Same predicate, two thresholds, two
    layers, two strengths. It is one predicate and it belongs in the
    arithmetic.
    """


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
#
# ROUND 376 CORRECTION. `expert_bytes` was 1_572_864 + 196_608 = 1,769,472 -- the
# size of the expert ON DISK. It is not what a cached expert costs in RAM.
# `qwen36.c:slot_ensure_allocated` mallocs `ng + ng + nd` *int8* bytes
# (= 3*inter*hidden = 3,145,728) and `load_expert_merged` unpacks the int4
# nibbles into it; the packed copy is freed unless the CUDA tier is live
# (`qt_ready()`, false on this CPU-only box). Round 370 found that mechanism but
# nothing here was re-derived from it, so every cap this module recommended was
# computed with a per-slot constant 1.889x too small -- including E4's headline
# `--cap 204`, which overshoots the engine's 30 GiB cgroup cap by 4.8 GB.
# Full derivation, inversion and tests: nuc/expert_cache.py (round 376).
# ROUND 382. `expert_bytes` was the only field round 376 re-derived. The other
# two size constants in this record were BARE LITERALS whose derivation lived
# in the comment above -- the same provenance grade the wrong one had, and the
# reason it survived 250 rounds. Both are now computed from the engine's own
# dimensions, read out of `/work/src/colibri-v170/c/qwen36.c` (read-only) and
# the `[meta] loaded:` / `[meta] DeltaNet:` banner lines. Verdicts:
#
#   kv_bytes_per_token  40,960  CORRECT, now derived.  `ensure_kv()` does
#       `K[i] = falloc(kv_heads * max_t * k_head_dim)` and the same again for
#       V, for each layer with `is_attn[i]`, where `is_attn[i] = (i % 4 == 3)`
#       -> 10 of 40 layers. `falloc` is `malloc(n * sizeof(float))`, so f32:
#       10 * 2 * (2 * 2 * 256 * 4) ... = 40,960 B/token exactly. Note V is
#       sized from `k_head_dim`, not `v_head_dim`; they are both 256 on this
#       checkpoint so it changes nothing here, and would if they ever differed.
#   fixed_bytes  65,900,000 -> 65,863,680.  Round 28's figure was a rounded
#       estimate ("65.9 MB"); the allocator is exact. Off by 36,320 B (0.055 %).
#
# And one term the model did NOT have at all: `ensure_kv` also allocates
# `attn_sc = falloc(attn_sc_thr * max_t)`, one attention-score row per OpenMP
# thread, and its own comment says it "grows with the context exactly like the
# KV cache does". That is context-proportional state the KV constant omitted.
# It is small (`nproc` = 4 on pgain-nuc, unset OMP_NUM_THREADS -> 16 B/token,
# 0.039 % of the KV term) but it is deployment-dependent, which a hard-coded
# byte count can never express -- hence `attn_score_bytes_per_token()`.
QWEN36_HIDDEN, QWEN36_INTER, QWEN36_EXPERT_GS = 2048, 512, 64
QWEN36_KV_HEADS, QWEN36_K_HEAD_DIM = 2, 256      # [meta] banner
QWEN36_ATTN_LAYERS = 10                          # is_attn[i] = (i % 4 == 3), 40 layers
QWEN36_DN_LAYERS = 30                            # the other 30
QWEN36_DN_VHEADS, QWEN36_DN_KDIM, QWEN36_DN_VDIM = 32, 128, 128
QWEN36_DN_CONV_DIM, QWEN36_DN_CONVK = 8192, 4
F32 = 4                                          # sizeof(float); `falloc`/`calloc(.., sizeof(float))`

#   K and V per attention layer per token, both sized from k_head_dim
QWEN36_KV_BYTES_PER_TOKEN = (QWEN36_ATTN_LAYERS * 2
                             * QWEN36_KV_HEADS * QWEN36_K_HEAD_DIM * F32)
#   DeltaNet recurrent state + conv ring, per non-attention layer, context-free
QWEN36_DN_BYTES = QWEN36_DN_LAYERS * (
    QWEN36_DN_VHEADS * QWEN36_DN_KDIM * QWEN36_DN_VDIM * F32      # DN_rec
    + QWEN36_DN_CONV_DIM * (QWEN36_DN_CONVK - 1) * F32)           # DN_conv


def attn_score_bytes_per_token(threads: int) -> int:
    """`ensure_kv`: `attn_sc = falloc(attn_sc_thr * max_t)`, one score row per
    OpenMP thread, each `max_t` floats. ROUND 382 -- context-proportional state
    the KV constant does not include. `threads` is `omp_get_max_threads()`,
    i.e. `nproc` unless `OMP_NUM_THREADS` is set; 4 on pgain-nuc."""
    if threads < 1:
        raise FastLaneError("threads >= 1")
    return threads * F32


#   ROUND 382: `expert_bytes` was the field round 376 CORRECTED, but it stayed
#   two magic numbers -- the same provenance grade that let the wrong value
#   live for 250 rounds. The derivation existed all along in the module round
#   376 wrote; it just never came back here. `slot_ensure_allocated` mallocs
#   `ng + ng + nd` int8 = 3*inter*hidden, and `falloc`s
#   `2*scale_count_gu + scale_count_d` f32 where each scale_count is
#   inter*hidden/expert_gs. Cross-checked against `expert_cache.SlotGeometry`
#   by `test_fast_lane_and_expert_cache_agree_on_the_slot`.
QWEN36_SLOT_WEIGHT_BYTES = 3 * QWEN36_INTER * QWEN36_HIDDEN          # int8
QWEN36_SLOT_SCALE_BYTES = (3 * QWEN36_INTER * QWEN36_HIDDEN
                           // QWEN36_EXPERT_GS) * F32                # f32
QWEN36_SLOT_BYTES = QWEN36_SLOT_WEIGHT_BYTES + QWEN36_SLOT_SCALE_BYTES

QWEN36 = MoeGeometry("qwen36", layers=40, experts=256, expert_bytes=QWEN36_SLOT_BYTES,
                     dense_bytes=int(9.25 * GB),
                     kv_bytes_per_token=QWEN36_KV_BYTES_PER_TOKEN,
                     fixed_bytes=QWEN36_DN_BYTES)

# OLMoE-1B-7B int8 merged container: 16 layers x 64 experts, hidden 2048, inter 1024.
#   dense ~1.8 GB f32 (chat_olmoe.sh comment: "~6GB cache + ~1.8GB dense = 7.8GB peak").
#   KV: layers x ctx x heads(16) x head_dim(128) x 2 x 4 B  (family_registry _olmoe_geometry).
#
# ROUND 382, and the honest caveat that makes this record different from
# QWEN36's. The values below are unchanged; the EXPRESSIONS now name their
# dimensions, so which side of a packing transform each one sits on is legible
# instead of being asserted in a comment. But the provenance grade is NOT the
# same as QWEN36's: qwen36's dimensions were read out of the engine's own
# allocator on the box this round, whereas OLMoE's come from a container README
# and a shell-script comment. **That is exactly the state qwen36 was in before
# round 376 found `expert_bytes` 1.889x wrong.** OLMoE has never been deployed
# here, so no allocator exists to read; if the lane is ever built, read
# `slot_ensure_allocated`'s equivalent FIRST and re-derive, because "int8 in
# the container" does not by itself establish "int8 in the slot".
OLMOE_LAYERS, OLMOE_EXPERTS = 16, 64
OLMOE_HIDDEN, OLMOE_INTER = 2048, 1024
OLMOE_HEADS, OLMOE_HEAD_DIM = 16, 128
#   3 matrices (gate/up/down), int8 in the container
OLMOE_SLOT_WEIGHT_BYTES = 3 * OLMOE_HIDDEN * OLMOE_INTER
#   row scales, f32: gate 1024 + up 1024 + down 2048
OLMOE_SLOT_SCALE_BYTES = (OLMOE_INTER + OLMOE_INTER + OLMOE_HIDDEN) * F32
OLMOE_SLOT_BYTES = OLMOE_SLOT_WEIGHT_BYTES + OLMOE_SLOT_SCALE_BYTES
#   K and V for every layer, f32
OLMOE_KV_BYTES_PER_TOKEN = OLMOE_LAYERS * OLMOE_HEADS * OLMOE_HEAD_DIM * 2 * F32

OLMOE = MoeGeometry("olmoe", layers=OLMOE_LAYERS, experts=OLMOE_EXPERTS,
                    expert_bytes=OLMOE_SLOT_BYTES,
                    dense_bytes=int(1.8 * GB),
                    kv_bytes_per_token=OLMOE_KV_BYTES_PER_TOKEN)


def anchor_soundness(geom: MoeGeometry, rss_full: int, cap_full: int) -> dict:
    """Is `rss_full` a physically possible reading of `geom` at full residency?

    ROUND 382. A sound anchor has to leave at least the engine's measured
    non-expert weight behind once its whole cache is subtracted:

        implied_dense = rss_full - cap_full * layers * expert_bytes
        sound         <=> implied_dense >= geom.dense_bytes

    Three grades, because they mean different things:
      * `impossible`  implied_dense < 0 -- the anchor is smaller than the
        cache it claims to hold. Refused unconditionally; extrapolating from
        it produced round 376's "cap 7 where -1 was owed".
      * `unsound`     0 <= implied_dense < dense_bytes -- arithmetically
        coherent, physically a MID-FILL reading mislabelled full residency.
        Refused by default, openable with `allow_unsound_anchor=True` for
        callers whose subject IS the wrong answer (the disagreement witness).
      * `sound`       implied_dense >= dense_bytes.

    Why this is a refusal and not a deletion. The arithmetic is correct for a
    sound anchor; what does not exist is a sound qwen36 anchor *at cap 256*,
    because cap-256 residency is 44.00 GB and `memory.max` is 32.21 GB. That
    is a property of the CAP, not of the model. Restart at the round-376
    recommendation and the anchor becomes observable and sound:
    cap_full 159 terminates at 31.03 GB, whose implied dense is 9.77 GB
    against a measured 9.25 GB. `test_a_cap_159_anchor_is_sound` pins exactly
    that, so the day the operator acts, this planner works again -- and if it
    had been deleted, nothing would record that it could.
    """
    implied = anchor_implied_dense(geom, rss_full, cap_full)
    if implied < 0:
        grade = "impossible"
    elif implied < geom.dense_bytes:
        grade = "unsound"
    else:
        grade = "sound"
    return {"grade": grade, "sound": grade == "sound",
            "implied_dense_bytes": implied,
            "measured_dense_bytes": geom.dense_bytes,
            "shortfall_bytes": max(0, geom.dense_bytes - implied),
            "cache_bytes": cap_full * geom.layers * geom.expert_bytes}


def _refuse_unsound(geom: MoeGeometry, rss_full: int, cap_full: int,
                    allow_unsound_anchor: bool) -> None:
    """Shared gate for every entry point into the relative planner."""
    v = anchor_soundness(geom, rss_full, cap_full)
    if v["grade"] == "impossible":
        raise UnsoundAnchorError(
            f"anchor {rss_full} B cannot hold a cap-{cap_full} cache of "
            f"{v['cache_bytes']} B: the reading was not full residency. For "
            f"qwen36 no such reading exists -- cap-256 residency is 44.0 GB, "
            f"past the cgroup cap. Use "
            f"expert_cache.SlotGeometry.terminal_bytes instead.")
    if v["grade"] == "unsound" and not allow_unsound_anchor:
        raise UnsoundAnchorError(
            f"anchor {rss_full} B implies {v['implied_dense_bytes'] / GB:.2f} GB of "
            f"non-expert weights for {geom.name}, but it measures "
            f"{geom.dense_bytes / GB:.2f} GB (engine journal: 'RSS after load') "
            f"-- short by {v['shortfall_bytes'] / GB:.2f} GB. This is a MID-FILL "
            f"reading labelled full residency, so every cap derived from it is "
            f"too high. Use `python3 nuc/expert_cache.py plan` (absolute, no "
            f"anchor) -> cap 167 at zero margin, 159 with 1 GiB. Pass "
            f"allow_unsound_anchor=True only to reproduce the wrong answer "
            f"deliberately.")


def rss_at_cap(geom: MoeGeometry, rss_full: int, cap_full: int, cap: int,
               *, allow_unsound_anchor: bool = False) -> int:
    """Engine RSS when the cache holds `cap` instead of `cap_full` experts/layer.

    CAVEAT (round 376): this is a *relative* model anchored on `rss_full`, and
    every anchor this repo has ever passed for qwen36 is a mid-fill reading
    mislabelled "cap 256, measured" -- PLAN-E4's 36.01 GB (round 124's 31.8 GB
    resident + 4.2 GB swap) and this module's test anchor of 32.01 GB alike.
    Because `slot_ensure_allocated` fills lazily, an engine only reaches
    `cap_full` residency after enough routing diversity to touch every expert;
    round 124's box hit the cgroup wall and exhausted swap at ~77 % fill, and
    round 376's is plateaued at ~62 %. Full cap-256 residency is 44.0 GB and is
    unreachable on this box at all. Prefer
    `expert_cache.SlotGeometry.terminal_bytes`, which is absolute
    (baseline + cap * layers * slot_bytes) and needs no anchor, whenever the
    question is "does this cap fit"."""
    if not (0 <= cap <= geom.experts and 0 < cap_full <= geom.experts):
        raise FastLaneError("cap out of range")
    # Round 376 refused the `impossible` grade here; round 382 moved the whole
    # soundness test into `_refuse_unsound` so the CLI and the library apply
    # the SAME predicate at the SAME threshold.
    _refuse_unsound(geom, rss_full, cap_full, allow_unsound_anchor)
    return rss_full - (cap_full - cap) * geom.layers * geom.expert_bytes


def anchor_implied_dense(geom: MoeGeometry, rss_full: int, cap_full: int) -> int:
    """What `rss_full` implies the engine's non-expert bytes are.

    Round 376. A sound anchor satisfies `implied >= geom.dense_bytes`; every
    qwen36 anchor in this repo fails that by ~7 GB, because each was taken
    mid-fill and labelled full residency.

    ROUND 382: this is now the RAW number behind `anchor_soundness`, which is
    what every entry point actually gates on. Round 376 left this test living
    only in `_plan_table` as a printed warning, one layer above the arithmetic
    it was about."""
    return rss_full - cap_full * geom.layers * geom.expert_bytes


def cap_for_free_bytes(geom: MoeGeometry, rss_full: int, cap_full: int,
                       ram_total: int, need_free: int, os_reserve: int,
                       *, allow_unsound_anchor: bool = False) -> int:
    """Largest cap such that ram_total - os_reserve - RSS(cap) >= need_free.
    Returns -1 when even cap 0 cannot make room.

    ROUND 382: refuses an unsound anchor (via `rss_at_cap`) rather than
    silently answering. This is the call site that mattered -- `plan_rows`
    reaches the arithmetic through here, never through the CLI's warning."""
    budget = ram_total - os_reserve - need_free
    empty = rss_at_cap(geom, rss_full, cap_full, 0,
                       allow_unsound_anchor=allow_unsound_anchor)
    if budget < empty:
        return -1
    slack = budget - empty
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
             prefill_layers_touch_all: bool = True,
             *, allow_unsound_anchor: bool = False) -> CapCost:
    """What the production engine pays at a reduced cap.
    decode: misses/token x expert_bytes / disk rate.
    prefill: a batched prefill touches ~every expert per layer, so every slot
    the cache lacks streams once per request."""
    rss = rss_at_cap(geom, rss_full, cap_full, cap,
                     allow_unsound_anchor=allow_unsound_anchor)
    miss = expected_miss_fraction(cap, geom.experts, skew)
    per_byte_s = 1.0 / (nvme_mb_s * MB)
    decode = miss * topk * geom.layers * geom.expert_bytes * per_byte_s
    missing = (geom.experts - cap) if prefill_layers_touch_all else int(miss * geom.experts)
    prefill = missing * geom.layers * geom.expert_bytes * per_byte_s
    return CapCost(cap=cap, rss_gb=rss / GB, freed_gb=(rss_full - rss) / GB,
                   miss_fraction=miss, decode_penalty_s_per_token=decode,
                   prefill_penalty_s_per_request=prefill)


# ------------------------------------------------------------------ lane projection

OLMOE_TOPK = 8


def lane_disk_bound_tok_s(miss_fraction: float, disk_mb_s: float, geom: MoeGeometry = OLMOE,
                          topk: int = OLMOE_TOPK) -> float:
    """Decode ceiling when every expert-cache miss is a disk read: the lane
    performs layers x topk lookups per token (OLMoE: 16 x 8 = 128; measured
    127.4 on the Mac), each miss streams one expert. At cap 16 the Mac
    measured miss 0.511 -> 411 MB/token -> 1.2 tok/s at its ~500 MB/s
    page-fault path; the same arithmetic with the box's NVMe rate is the
    NUC projection. Returns inf when nothing misses (compute-bound)."""
    if not 0.0 <= miss_fraction <= 1.0 or disk_mb_s <= 0:
        raise FastLaneError("miss_fraction in [0,1], disk_mb_s > 0")
    mb_per_token = geom.layers * topk * miss_fraction * geom.expert_bytes / MB
    return math.inf if mb_per_token == 0 else disk_mb_s / mb_per_token


def measured_miss_fraction(hits: int, misses: int) -> float:
    tot = hits + misses
    if tot <= 0:
        raise FastLaneError("no lookups")
    return misses / tot


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


LANE_PREFILL_MAC_CAP16 = 8.8      # round 112: 9.6 / 8.0 prompt-tok/s at 200, 6.7 @50, 8.6 @800 (Mac, cap 16, n_new=1)
LANE_DECODE_MAC_CAP16 = 1.2       # round 106: disk-bound regime (hit 48.9 %, sys share 85 %)


def breakeven_prompt_tokens(reply_tokens: int, prefill_tps: float = LANE_PREFILL_MAC_CAP16,
                            decode_tps: float = LANE_DECODE_MAC_CAP16, overhead_s: float = 0.5,
                            qwen_decode_tps: float = 3.3, limit: int = 8000, step: int = 5) -> Optional[int]:
    """Smallest prompt length at which a lane turn is faster than the qwen36
    turn for the same reply length; None when the lane never wins below
    `limit`. Round 112: with the measured lane rates (8.8 / 1.2 tok/s) the
    lane wins only above ~700 prompt tokens for a 60-token reply — its decode
    is 2.75x slower than qwen36's, so short replies are the only regime where
    it is a "fast" lane, and only for long prompts."""
    if reply_tokens < 0 or limit <= 0 or step <= 0:
        raise FastLaneError("reply_tokens >= 0, limit > 0, step > 0")
    for p in range(0, limit + 1, step):
        if lane_turn(p, reply_tokens, prefill_tps, decode_tps, overhead_s).total_s < \
                qwen36_turn(p, reply_tokens, qwen_decode_tps).total_s:
            return p
    return None


# ------------------------------------------------------------------ transfer

def transfer_cmd(local_path: str, ssh_target: str, remote_path: str,
                 ssh_key: Optional[str] = None, sink: str = "~/nuc-research/fast_lane_sink.py",
                 chunk_mb: int = 8, sync_every_mb: int = 256) -> str:
    """Shell pipeline: stream a local file into the page-cache-safe sink on the box."""
    ssh = ["ssh"] + (["-i", ssh_key] if ssh_key else []) + [ssh_target]
    remote = (f"python3 {sink} --out {remote_quote(remote_path)} "
              f"--chunk-mb {int(chunk_mb)} --sync-every-mb {int(sync_every_mb)}")
    return f"cat {shlex.quote(local_path)} | {' '.join(ssh)} {shlex.quote(remote)}"


def remote_quote(path: str) -> str:
    """Quote a path for the REMOTE shell. A leading `~/` must survive as an
    expansion there, so it becomes `"$HOME"/…` (the outer ssh argument is
    single-quoted by the caller, which keeps the local shell out of it).
    Round 100's `transfer_cmd` single-quoted `'~/x'` — the box would have
    created a directory literally named `~`."""
    if path == "~":
        return '"$HOME"'
    if path.startswith("~/"):
        return '"$HOME"/' + shlex.quote(path[2:])
    return shlex.quote(path)


@dataclass
class FileXfer:
    relpath: str
    size: int
    remote_have: int          # bytes already in <remote>.part (or the finished file)
    action: str               # "skip" | "resume" | "send"
    command: str = ""


def transfer_plan(files: Sequence[tuple[str, int]], remote_have: dict,
                  local_dir: str, ssh_target: str, remote_dir: str,
                  ssh_key: Optional[str] = None, sink: str = "~/nuc-research/fast_lane_sink.py",
                  chunk_mb: int = 8, sync_every_mb: int = 256) -> list[FileXfer]:
    """Per-file, resumable transfer of a directory (a container is 18 shards +
    config + tokenizer). `remote_have` maps relpath -> bytes already on the box:
    equal to size → skip; 0 < have < size → `tail -c +have+1` into the sink with
    --resume; else send whole. A stream of separate files can resume where a
    tar stream cannot (its headers carry mtimes, so a re-run is not byte-identical)."""
    ssh = ["ssh"] + (["-i", ssh_key] if ssh_key else []) + [ssh_target]
    plan = []
    for rel, size in files:
        have = int(remote_have.get(rel, 0))
        remote_path = remote_dir.rstrip("/") + "/" + rel
        local_path = os.path.join(local_dir, rel)
        if have >= size and size > 0:
            plan.append(FileXfer(rel, size, have, "skip"))
            continue
        action = "resume" if have > 0 else "send"
        src = (f"tail -c +{have + 1} {shlex.quote(local_path)}" if have > 0
               else f"cat {shlex.quote(local_path)}")
        remote = (f"python3 {sink} --out {remote_quote(remote_path)} --chunk-mb {int(chunk_mb)} "
                  f"--sync-every-mb {int(sync_every_mb)}" + (" --resume" if have > 0 else ""))
        cmd = f"{src} | {' '.join(ssh)} {shlex.quote(remote)}"
        plan.append(FileXfer(rel, size, have, action, cmd))
    return plan


def list_container(local_dir: str) -> list[tuple[str, int]]:
    out = []
    for name in sorted(os.listdir(local_dir)):
        path = os.path.join(local_dir, name)
        if os.path.isfile(path) and not name.startswith("."):
            out.append((name, os.path.getsize(path)))
    if not out:
        raise FastLaneError(f"no files in {local_dir}")
    return out


def handoff_script(files: Sequence[tuple[str, int]], remote_have: dict, local_dir: str,
                   ssh_target: str, remote_dir: str, local_md5: dict,
                   ssh_key: Optional[str] = None, log_path: str = "/work/logs/nuc-fast-lane.md",
                   sink_local: str = "nuc/fast_lane_sink.py") -> str:
    """The exact shell sequence the next round runs once the box answers:
    guard (host up, no 8001), stage the sink, per-file resumable copies,
    remote md5 verification against the local digests, then a log stub."""
    ssh = "ssh" + (f" -i {ssh_key}" if ssh_key else "") + f" {ssh_target}"
    scp = "scp" + (f" -i {ssh_key}" if ssh_key else "")
    plan = transfer_plan(files, remote_have, local_dir, ssh_target, remote_dir, ssh_key=ssh_key)
    total = sum(f.size for f in plan)
    todo = sum(f.size - f.remote_have for f in plan if f.action != "skip")
    lines = ["#!/bin/sh", "# generated by fast_lane.py handoff — run from the Mac; every step is idempotent",
             "set -e",
             f"# {len(plan)} files, {total / GB:.2f} GB total, {todo / GB:.2f} GB still to send "
             f"({sum(1 for f in plan if f.action == 'skip')} skip / "
             f"{sum(1 for f in plan if f.action == 'resume')} resume / "
             f"{sum(1 for f in plan if f.action == 'send')} send)",
             f"{ssh} 'echo HOST_OK; grep MemAvailable /proc/meminfo; df -h /work | tail -1' || {{ echo 'host down — stop'; exit 2; }}",
             f"{ssh} 'mkdir -p {remote_quote(remote_dir)} \"$HOME\"/nuc-research'",
             f"{scp} {shlex.quote(sink_local)} {ssh_target}:~/nuc-research/fast_lane_sink.py"]
    for f in plan:
        if f.action == "skip":
            lines.append(f"# skip {f.relpath} ({f.size} B already on the box)")
        else:
            lines.append(f"# {f.action} {f.relpath}: {f.size - f.remote_have} B to go")
            lines.append(f.command)
    lines.append("# verify every file against the local digests")
    for rel, digest in sorted(local_md5.items()):
        remote_path = remote_dir.rstrip("/") + "/" + rel
        check = 'test "$(md5sum ' + remote_quote(remote_path) + ' | cut -d" " -f1)" = ' + digest
        lines.append(f"{ssh} {shlex.quote(check)} || {{ echo 'md5 mismatch {rel}'; exit 3; }}")
    note = (f'echo "- $(date -u +%FT%TZ) container verified in {remote_dir} '
            f'({total / GB:.2f} GB, {len(plan)} files)" >> {log_path}')
    lines.append(f"{ssh} {shlex.quote(note)}")
    lines.append("echo HANDOFF_OK")
    script = "\n".join(lines) + "\n"
    if ":8001" in script or " 8001" in script:
        raise FastLaneError("handoff script mentions port 8001")
    return script


def md5_of_files(local_dir: str, files: Sequence[tuple[str, int]], chunk: int = 1 << 20) -> dict:
    import hashlib
    out = {}
    for rel, _ in files:
        h = hashlib.md5()
        with open(os.path.join(local_dir, rel), "rb") as fh:
            for block in iter(lambda: fh.read(chunk), b""):
                h.update(block)
        out[rel] = h.hexdigest()
    return out


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
              lane_workspace: int = int(0.3 * GB),
              *, allow_unsound_anchor: bool = False) -> list[tuple[int, int, int, Optional[CapCost]]]:
    """(lane_cap, lane_bytes, big_cap, cost) per lane size; lane cap 0 = no lane,
    i.e. the cap at which the production engine merely stops swapping."""
    rows = []
    for lane_cap in lane_caps:
        need = 0 if lane_cap == 0 else lane.footprint(lane_cap, lane_ctx, workspace_bytes=lane_workspace)
        cap = cap_for_free_bytes(geom, rss_full, cap_full, ram, need, reserve,
                                 allow_unsound_anchor=allow_unsound_anchor)
        cost = cap_cost(geom, rss_full, cap_full, cap, topk=topk,
                        nvme_mb_s=nvme_mb_s, skew=skew,
                        allow_unsound_anchor=allow_unsound_anchor) if cap >= 0 else None
        rows.append((lane_cap, need, cap, cost))
    return rows


def _plan_table(args) -> str:
    """ROUND 382: REFUSES on an unsound anchor instead of warning and answering.

    Round 376 left this warning-but-answering and asked a later round to
    decide whether a model with no sound anchor should answer at all. It
    should not. A warning above a table is read as a caveat on a number; the
    number is not caveated, it is wrong -- 225 against a true 167. The
    refusal names the absolute tool, and it is not permanent: pass a cap_full
    whose full residency actually fits (`--cap-full 159 --resident-gb 31.03
    --swapped-gb 0`, after the recommended restart) and this table answers
    again, soundly. The default arguments are the unsound 2026-08-24 anchor,
    so the default invocation is exactly the one that must refuse.
    """
    geom = QWEN36
    rss_full = full_footprint(int(args.resident_gb * GB), int(args.swapped_gb * GB))
    ram = int(args.ram_gib * GIB)
    reserve = int(args.os_reserve_gb * GB)
    rows = plan_rows(geom, OLMOE, rss_full, args.cap_full, ram, reserve, (0, 16, 32, 64),
                     args.lane_ctx, args.nvme_mb_s, args.skew)
    out = []
    out += [f"# RAM plan: {geom.name} cap {args.cap_full} = {rss_full / GB:.2f} GB "
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

    h = sub.add_parser("handoff", help="resumable per-file transfer script + md5 verification for the next round")
    h.add_argument("local_dir")
    h.add_argument("target")
    h.add_argument("remote_dir")
    h.add_argument("--key", default=None)
    h.add_argument("--remote-sizes", default=None,
                   help="JSON {relpath: bytes_on_box} from `fast_lane_sink.py --part-size` / stat; default: nothing there")
    h.add_argument("--md5", action="store_true", help="hash the local files (slow on 7 GB) and emit verify steps")
    h.add_argument("--log-path", default="/work/logs/nuc-fast-lane.md")

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
        # ROUND 382: the refusal is the answer. Exit 2 like `gate`, so a
        # script that pipes this table cannot mistake a refusal for a plan.
        try:
            print(_plan_table(a))
        except UnsoundAnchorError as exc:
            print(f"# REFUSED (round 382): {exc}")
            return 2
    elif a.cmd == "turn":
        lane = lane_turn(a.prompt, a.reply, a.prefill_tps, a.decode_tps)
        big = qwen36_turn(a.prompt, a.reply)
        print(json.dumps({"lane": asdict(lane), "qwen36": asdict(big),
                          "speedup": big.total_s / lane.total_s}, indent=2))
    elif a.cmd == "transfer-cmd":
        print(transfer_cmd(a.local, a.target, a.remote, ssh_key=a.key))
    elif a.cmd == "handoff":
        files = list_container(a.local_dir)
        have = {}
        if a.remote_sizes:
            with open(a.remote_sizes, encoding="utf-8") as fh:
                have = json.load(fh)
        digests = md5_of_files(a.local_dir, files) if a.md5 else {}
        print(handoff_script(files, have, a.local_dir, a.target, a.remote_dir, digests,
                             ssh_key=a.key, log_path=a.log_path), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
