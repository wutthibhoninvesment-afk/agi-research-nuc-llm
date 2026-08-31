#!/usr/bin/env python3
"""Expert-cache RAM model for colibri's qwen36 engine, derived from the C source.

Round 376 (track E). Round 370 found the mechanism -- `qwen36.c` unpacks int4
experts *in-slot to int8*, so a demand-loaded expert costs 2x its on-disk size
-- but nothing in this repo was re-derived from it. `nuc/fast_lane.py`'s
`QWEN36.expert_bytes` still counted the packed int4 tensor, so every `--cap`
recommendation E4 ever made was computed with a per-slot constant 1.889x too
small.

This module is the corrected model, and it is *arithmetic over the allocator*,
not a curve fit. Everything here traces to two functions in
`/work/src/colibri-v170/c/qwen36.c` (read-only, round 376):

    static int64_t scale_count_gu(const Cfg *c){
        return c->expert_gs ? (int64_t)c->inter * ((c->hidden + c->expert_gs - 1) / c->expert_gs)
                            : c->inter; }
    static int64_t scale_count_d (const Cfg *c){
        return c->expert_gs ? (int64_t)c->hidden * ((c->inter + c->expert_gs - 1) / c->expert_gs)
                            : c->hidden; }

    static void slot_ensure_allocated(Model *m, Slot *s) {
        if (s->g) return;                       /* <- lazy: slots fill on demand */
        int64_t ng = (int64_t)c->inter * c->hidden;
        int64_t nd = (int64_t)c->hidden * c->inter;
        int8_t *w_block = malloc(ng + ng + nd);          /* INT8, not int4 */
        float  *s_block = falloc(2*scale_count_gu(c) + scale_count_d(c));   /* f32 */
        ...
        s->g4 = s->u4 = s->d4 = NULL;
    }

and `falloc(n) = malloc(n*sizeof(float))` (qwen36.c:693), i.e. the scales are
f32, four bytes each.

Three facts about that code drive every number below.

1.  **The slot is int8.** `malloc(ng + ng + nd)` with ng = nd = inter*hidden.
    The container on disk is int4-packed (half that), and `load_expert_merged`
    detects it by size and unpacks nibble-by-nibble into the int8 block. The
    RAM cost of a cached expert is therefore the *unpacked* size.
2.  **The packed copy is NOT kept.** `s->g4/u4/d4` are allocated only under
    `qt_ready()` (the CUDA tier). pgain-nuc is CPU-only, so there is no
    +50% packed-shadow term there. `int4_shadow_bytes` models it for
    completeness; `SLOT_SHADOW_ON_NUC` is False.
3.  **ALLOCATION is monotone and capped; RESIDENCY is neither.** The miss path
    is
    `if (lc->n < lc->cap) { s = &lc->slots[lc->n++]; slot_ensure_allocated(...); }`
    -- a new block is malloc'd only while the layer has unused slots; past that
    the LRU reuses an existing block (qwen36.c:1320-1330). So the *allocated*
    footprint climbs from `baseline` to `baseline + n_layers*cap*slot_bytes` and
    then stops, and never decreases below `cap`. Rounds 124 and 364 both read a
    mid-fill snapshot and reported it as a steady state.

    **Round 388: `memory.current` is NOT that quantity.** With zero requests
    served, `memory.current` fell 458,207,232 B between 2026-08-31T00:05Z and
    04:52Z, because global `kswapd` reclaim (not cgroup reclaim -- `memory.events
    max` stayed 0 and `pgscan_direct` was 0) pushed 274,530,304 B of the
    engine's anonymous pages to swap and dropped ~184 MB of kernel/file charge.
    Inverting `memory.current` therefore reported the expert cache *shrinking by
    137 slots*, which the C source above says cannot happen.

    The allocation-faithful observable is **`anon + swap.current`**, and it was
    byte-identical across that event: 30,600,970,240 at both readings. Use
    `fill_from_snapshot()` / `CgroupSnapshot`; `fill_from_current()` is kept for
    the pre-reclaim readings that rounds 364/376 took, and warns when it is
    handed a reading it cannot vouch for.

Offline only: no ssh, no engine contact, no I/O outside argv. The defaults
describe pgain-nuc as measured in round 376; pass flags for any other box.

CLI:
    python3 nuc/expert_cache.py geometry
    python3 nuc/expert_cache.py plan            # largest --cap that fits the cgroup
    python3 nuc/expert_cache.py fill --current 30870429696
    python3 nuc/expert_cache.py wall --current 30870429696 --requests 2
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, asdict

GB = 1_000_000_000
GIB = 1 << 30

# ---------------------------------------------------------------- measured NUC

# All from round 376's read-only snapshot of pgain-nuc, boot 43e0c767.
# config.hf.json text_config: hidden_size 2048, num_hidden_layers 40,
# num_experts 256, moe_intermediate_size 512; qwen36_meta.json expert_gs 64
# (engine banner: "group-scaled experts: gs=64").
NUC_HIDDEN = 2048
NUC_INTER = 512
NUC_EXPERT_GS = 64
NUC_LAYERS = 40
NUC_EXPERTS = 256
NUC_TOPK = 8
# qwen36.c:2000/2005 -- the PILOT prefetch thread collects at most 128 candidate
# experts per layer (`int idx[128]`, `if (max_cand > 128) max_cand = 128`), and
# `expert_get` has a distinct code path for "every slot in this layer is in
# flight" (qwen36.c:1338-1355) that is reachable only when `cap` is at or below
# that depth. In colibri v1.7.0 that path is a 1 ms sleep-and-rescan loop, i.e.
# a liveness/latency concern rather than a correctness one -- but its own
# comment records that the previous last resort (`lru = 0`) stole a slot
# mid-load and "corrupts silently rather than crashing". Round 388 reads this
# as a FLOOR on any --cap recommendation, not as a live defect.
PILOT_QUEUE_DEPTH = 128

# cgroup user.slice/.../qwen36-colibri.service, round 376 19:55:44Z.
NUC_MEMORY_MAX = 32_212_254_720          # 30 GiB, memory.max
NUC_MEMORY_CURRENT = 30_870_429_696      # memory.current (byte-identical to r370)
NUC_MEMORY_PEAK = 31_670_497_280         # memory.peak
# Round 388, 04:52:43Z, SAME boot, SAME two completions, after a kswapd event.
# `memory.current` moved; `anon + swap.current` did not. Both readings are kept
# so the invariant below is checkable rather than asserted.
NUC_ANON_PLUS_SWAP = 30_600_970_240      # r382 anon+0 == r388 anon+swap, to the byte
R388_MEMORY_CURRENT = 30_412_222_464
R388_ANON = 30_326_439_936
R388_SWAP_CURRENT = 274_530_304
R388_KERNEL = 85_000_192                 # memory.stat `kernel` (slab, stacks, pagetables)
R388_FILE = 458_752
R382_MEMORY_CURRENT = 30_870_429_696
R382_ANON = 30_600_970_240
R382_SWAP_CURRENT = 0
# memory.current on the SAME boot before the first inference: round 364 polled
# this 1921 times over 8.002 h and got the identical value every time. That is
# the true zero-slot baseline -- the engine had served no completion yet.
NUC_BASELINE = 9_770_594_304
NUC_SWAP_TOTAL = 4_194_300 * 1024        # /proc/meminfo SwapTotal, 4.295 GB
NUC_MODEL_DISK_BYTES = 23_031_269_773    # du -sb /work/models/qwen36_i4_gs64

# Round 124 (E4) read 31.8 GB resident + 4.2 GB swap and called it "the
# footprint of --cap 256". `wall` below shows why that was the *wall*, not the
# ceiling: swap was exhausted at 4.19 GB total.
R124_RESIDENT = int(31.8 * GB)
R124_SWAP = int(4.2 * GB)

SLOT_SHADOW_ON_NUC = False               # qt_ready() is false on a CPU-only box


class ExpertCacheError(ValueError):
    pass


# ------------------------------------------------------------------- geometry

def _ceil_div(a: int, b: int) -> int:
    return (a + b - 1) // b


@dataclass(frozen=True)
class SlotGeometry:
    """One layer-cache slot, byte-for-byte as `slot_ensure_allocated` mallocs it."""
    hidden: int = NUC_HIDDEN
    inter: int = NUC_INTER
    expert_gs: int = NUC_EXPERT_GS
    layers: int = NUC_LAYERS
    experts: int = NUC_EXPERTS

    def __post_init__(self):
        for name in ("hidden", "inter", "layers", "experts"):
            if getattr(self, name) <= 0:
                raise ExpertCacheError(f"{name} must be positive")
        if self.expert_gs < 0:
            raise ExpertCacheError("expert_gs must be >= 0 (0 = per-row scales)")

    # --- the two scale_count_* helpers, transcribed ---
    @property
    def scale_count_gu(self) -> int:
        if self.expert_gs:
            return self.inter * _ceil_div(self.hidden, self.expert_gs)
        return self.inter

    @property
    def scale_count_d(self) -> int:
        if self.expert_gs:
            return self.hidden * _ceil_div(self.inter, self.expert_gs)
        return self.hidden

    # --- the malloc calls ---
    @property
    def weight_bytes(self) -> int:
        """malloc(ng + ng + nd), one int8 byte per element."""
        ng = self.inter * self.hidden
        nd = self.hidden * self.inter
        return ng + ng + nd

    @property
    def scale_bytes(self) -> int:
        """falloc(2*scale_count_gu + scale_count_d) -- f32, 4 bytes each."""
        return 4 * (2 * self.scale_count_gu + self.scale_count_d)

    @property
    def slot_bytes(self) -> int:
        return self.weight_bytes + self.scale_bytes

    @property
    def int4_shadow_bytes(self) -> int:
        """g4+u4+d4, allocated ONLY when qt_ready() (CUDA tier). Zero on the NUC."""
        return self.weight_bytes // 2

    @property
    def packed_disk_bytes(self) -> int:
        """What the same expert occupies in the int4 container: half the weights,
        same f32 scales. This is the number `fast_lane.QWEN36.expert_bytes` used
        as if it were the RAM cost."""
        return self.weight_bytes // 2 + self.scale_bytes

    @property
    def unpack_ratio(self) -> float:
        return self.slot_bytes / self.packed_disk_bytes

    @property
    def bytes_per_cap_unit(self) -> int:
        """Raising --cap by 1 costs this much: one slot in every layer."""
        return self.layers * self.slot_bytes

    @property
    def total_slots(self) -> int:
        return self.layers * self.experts

    def cache_bytes(self, cap: int) -> int:
        if not 0 <= cap <= self.experts:
            raise ExpertCacheError(f"cap {cap} outside 0..{self.experts}")
        return cap * self.bytes_per_cap_unit

    def terminal_bytes(self, cap: int, baseline: int = NUC_BASELINE) -> int:
        """Footprint once every layer's cache is full at `cap`. Monotone ceiling."""
        return baseline + self.cache_bytes(cap)

    def max_cap(self, budget: int = NUC_MEMORY_MAX, baseline: int = NUC_BASELINE,
                margin: int = 0) -> int:
        """Largest cap whose TERMINAL footprint fits `budget - margin`.

        Returns -1 when even cap 0 (dense weights alone) does not fit, so the
        caller cannot mistake "nothing fits" for "cap 0 fits"."""
        if margin < 0:
            raise ExpertCacheError("margin must be >= 0")
        slack = budget - margin - baseline
        if slack < 0:
            return -1
        return min(self.experts, slack // self.bytes_per_cap_unit)


QWEN36_SLOT = SlotGeometry()


# ----------------------------------------------------------------- inversion

@dataclass(frozen=True)
class Fill:
    slots_loaded: int
    total_slots: int
    fraction: float
    cap_equivalent: float
    bytes_in_slots: int

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CgroupSnapshot:
    """The fields of one cgroup-v2 memory reading that the model actually needs.

    Round 388 exists because the model previously took `memory.current`, which
    is a RESIDENCY figure: it drops when the kernel reclaims, and it counts
    kernel/page-cache charge that was never an expert slot. Two derived
    quantities separate those effects:

      `allocated_anon`  = anon + swap.current -- what the process has malloc'd
                          and not freed, wherever the pages currently live.
                          Monotone below `cap`, per `slot_ensure_allocated`.
      `committed_bytes` = allocated_anon + kernel + file -- everything that must
                          be resident again if every page is touched, i.e. the
                          figure `memory.max` will actually be compared against.
    """
    memory_current: int
    anon: int
    swap_current: int = 0
    kernel: int = 0
    file: int = 0
    memory_max: int = NUC_MEMORY_MAX
    at_utc: str = ""

    def __post_init__(self):
        for name in ("memory_current", "anon", "swap_current", "kernel", "file",
                     "memory_max"):
            if getattr(self, name) < 0:
                raise ExpertCacheError(f"{name} must be >= 0")
        if self.anon > self.memory_current:
            raise ExpertCacheError(
                f"anon {self.anon} exceeds memory.current {self.memory_current}: "
                "anon is a subset of the cgroup's resident charge")

    @property
    def allocated_anon(self) -> int:
        return self.anon + self.swap_current

    @property
    def non_anon_resident(self) -> int:
        """Resident charge that is NOT expert slots: kernel, slab, page cache."""
        if self.kernel or self.file:
            return self.kernel + self.file
        return self.memory_current - self.anon

    @property
    def committed_bytes(self) -> int:
        return self.allocated_anon + self.non_anon_resident

    @property
    def headroom_bytes(self) -> int:
        """Against `memory.max`, counting swapped-out anon as still owed."""
        return self.memory_max - self.committed_bytes

    @property
    def naive_headroom_bytes(self) -> int:
        """`memory.max - memory.current`: what rounds 376/382 reported."""
        return self.memory_max - self.memory_current

    @property
    def headroom_overstatement_bytes(self) -> int:
        """How much the naive figure flatters the box. Zero before any reclaim."""
        return self.naive_headroom_bytes - self.headroom_bytes

    def as_dict(self) -> dict:
        d = asdict(self)
        d.update(allocated_anon=self.allocated_anon,
                 non_anon_resident=self.non_anon_resident,
                 committed_bytes=self.committed_bytes,
                 headroom_bytes=self.headroom_bytes,
                 naive_headroom_bytes=self.naive_headroom_bytes,
                 headroom_overstatement_bytes=self.headroom_overstatement_bytes)
        return d


# The two readings that proved the point, as data rather than prose.
R382_SNAPSHOT = CgroupSnapshot(
    memory_current=R382_MEMORY_CURRENT, anon=R382_ANON,
    swap_current=R382_SWAP_CURRENT, at_utc="2026-08-31T00:05:32Z")
R388_SNAPSHOT = CgroupSnapshot(
    memory_current=R388_MEMORY_CURRENT, anon=R388_ANON,
    swap_current=R388_SWAP_CURRENT, kernel=R388_KERNEL, file=R388_FILE,
    at_utc="2026-08-31T04:52:43Z")


def fill_from_current(current: int, baseline: int = NUC_BASELINE,
                      geom: SlotGeometry = QWEN36_SLOT) -> Fill:
    """Invert an observed `memory.current` into "how many slots are populated".

    **Prefer `fill_from_snapshot`.** `memory.current` is residency, not
    allocation: it falls under reclaim (round 388 watched it fall 458 MB with
    zero requests served) and it includes kernel/page-cache charge that is not
    expert slots. This entry point is kept because rounds 364/376/382 read it
    when `swap.current` was 0, where the two agree to within the non-anon term.

    Accurate to about +/-1 slot per 3.3 MB of unmodelled drift (page cache,
    malloc arena slop), i.e. a 200 MB uncertainty is ~60 slots out of 10,240.
    Do not read the last two digits of `slots_loaded` as significant."""
    if current < baseline:
        raise ExpertCacheError(
            f"current {current} is below baseline {baseline}: the baseline must be "
            "a zero-slot reading (before the first completion of the boot)")
    in_slots = current - baseline
    slots = in_slots / geom.slot_bytes
    return Fill(slots_loaded=round(slots), total_slots=geom.total_slots,
                fraction=slots / geom.total_slots,
                cap_equivalent=slots / geom.layers,
                bytes_in_slots=in_slots)


def fill_from_snapshot(snap: CgroupSnapshot, baseline: int = NUC_BASELINE,
                       geom: SlotGeometry = QWEN36_SLOT) -> Fill:
    """Invert `anon + swap.current` -- the allocation-faithful observable.

    `baseline` must be a zero-slot reading of the SAME quantity. Round 364's
    9,770,594,304 was taken with `swap.current == 0`, so it serves for both."""
    return fill_from_current(snap.allocated_anon, baseline, geom)


class MonotonicityVerdict(str):
    """`ok` | `instrument_error` | `over_cap`. A str subclass so it JSON-encodes."""


def check_monotone(earlier: Fill, later: Fill, cap: int = NUC_EXPERTS,
                   tolerance_slots: float = 1.0) -> dict:
    """Allocation below `cap` cannot decrease. A decrease is an instrument bug.

    This is the check that would have caught round 388's reading immediately:
    inverting two `memory.current` values across the kswapd event says the cache
    lost 137 slots, and `slot_ensure_allocated` has no path that frees a block
    while `lc->n <= lc->cap`.

    `tolerance_slots` absorbs the ~1-slot rounding of the inversion itself; it
    is NOT a licence to explain away a real drop."""
    if tolerance_slots < 0:
        raise ExpertCacheError("tolerance_slots must be >= 0")
    delta = later.cap_equivalent - earlier.cap_equivalent
    delta_slots = later.slots_loaded - earlier.slots_loaded
    if delta_slots < -tolerance_slots:
        verdict = "instrument_error"
        why = ("allocated slots cannot decrease below cap; the observable used is "
               "residency (memory.current), not allocation (anon + swap.current)")
    elif later.cap_equivalent > cap + tolerance_slots:
        verdict = "over_cap"
        why = f"inverted cap-equivalent {later.cap_equivalent:.1f} exceeds --cap {cap}"
    else:
        verdict = "ok"
        why = ""
    return {"verdict": MonotonicityVerdict(verdict), "why": why,
            "delta_slots": delta_slots, "delta_cap_equivalent": delta,
            "earlier_slots": earlier.slots_loaded, "later_slots": later.slots_loaded}


# ------------------------------------------------------------- fill dynamics
#
# Two models, both crude, kept BOTH because they bracket the answer and because
# the observation falsifies one of them.
#
#   uniform     -- routing picks topk experts uniformly at random per token per
#                  layer, so distinct-expert count is a coupon-collector curve
#                  in cumulative tokens. This is the OPTIMISTIC-fill /
#                  PESSIMISTIC-time model and round 376 shows it is wrong: it
#                  says 31 tokens produce the observed 61.7% fill, while the
#                  traffic that produced it was plainly hundreds of tokens.
#                  Real routing is skewed; a few experts absorb most draws.
#   saturating  -- fraction(x) = 1 - exp(-x) in a dimensionless "exposure" x,
#                  fitted to the ONE observation we have (requests -> fraction).
#                  Makes no claim about tokens, only "another request like the
#                  ones already seen". Sub-linear, which is the property that
#                  matters.

def uniform_fraction_after_tokens(tokens: float, experts: int = NUC_EXPERTS,
                                  topk: int = NUC_TOPK) -> float:
    if tokens < 0:
        raise ExpertCacheError("tokens must be >= 0")
    return 1.0 - (1.0 - 1.0 / experts) ** (topk * tokens)


def uniform_tokens_for_fraction(fraction: float, experts: int = NUC_EXPERTS,
                                topk: int = NUC_TOPK) -> float:
    if not 0.0 <= fraction < 1.0:
        raise ExpertCacheError("fraction must be in [0, 1)")
    return math.log1p(-fraction) / (topk * math.log1p(-1.0 / experts))


def saturating_exposure_for_fraction(fraction: float) -> float:
    if not 0.0 <= fraction < 1.0:
        raise ExpertCacheError("fraction must be in [0, 1)")
    return -math.log1p(-fraction)


def saturating_fraction_after_exposure(exposure: float) -> float:
    if exposure < 0:
        raise ExpertCacheError("exposure must be >= 0")
    return 1.0 - math.exp(-exposure)


# ------------------------------------------------------------------ the wall

def probe_budget(headroom_bytes: int, fill_fraction: float,
                 topk: int = NUC_TOPK, geom: SlotGeometry = QWEN36_SLOT) -> dict:
    """How large a request can be sent WITHOUT risking `memory.max`?

    Every decode step routes each token to `topk` experts in each of `layers`
    layers, so one token can demand at most `layers * topk` slots that are not
    yet cached (`topk = 8` and `n_experts = 256` are literals in qwen36.c:920).

    `worst_case_tokens` assumes every routed expert is a miss -- the only bound
    that is safe against an adversarial prompt. `expected_tokens` discounts by
    the fraction already cached, which is the number an optimist would quote.
    Both are reported because the interesting fact about this deployment is that
    they are within a factor of ~3 of each other and BOTH are tiny: there is no
    probe size where the optimistic and pessimistic models disagree about
    whether sending traffic is safe."""
    if not 0.0 <= fill_fraction <= 1.0:
        raise ExpertCacheError("fill_fraction must be in [0, 1]")
    if headroom_bytes < 0:
        raise ExpertCacheError("headroom_bytes must be >= 0")
    if topk <= 0:
        raise ExpertCacheError("topk must be positive")
    slots = headroom_bytes // geom.slot_bytes
    worst_per_token = geom.layers * topk
    expected_per_token = worst_per_token * (1.0 - fill_fraction)
    return {
        "headroom_slots": int(slots),
        "slots_per_token_worst_case": worst_per_token,
        "slots_per_token_expected": expected_per_token,
        "worst_case_tokens": int(slots // worst_per_token),
        "expected_tokens": int(slots // expected_per_token) if expected_per_token > 0
                           else None,
        "note": ("a prompt is priced in TOKENS here, prefill included; a "
                 "single-token probe is not a probe"),
    }


def cap_band(baseline: int = NUC_BASELINE, memory_max: int = NUC_MEMORY_MAX,
             pilot_depth: int = PILOT_QUEUE_DEPTH,
             geom: SlotGeometry = QWEN36_SLOT) -> dict:
    """The closed interval of `--cap` values that are sound on this box.

    Two independent constraints, from two different places in the same C file:

      upper  `terminal_bytes(cap) <= memory.max`  -- above this the engine's own
             LRU can never engage and the kernel decides instead (`bound_by`).
      lower  `cap > PILOT_QUEUE_DEPTH`            -- at or below the prefetch
             depth a layer can have every slot in flight at once, which is the
             one `expert_get` path with no LRU victim to take.

    Round 124 (E4) proposed a `--cap 16` and a `--cap 64` fast-lane variant on
    RAM grounds alone. Both sit below the floor. Nothing in this repo had read
    the prefetcher when those numbers were written."""
    if pilot_depth < 0:
        raise ExpertCacheError("pilot_depth must be >= 0")
    upper = geom.max_cap(memory_max, baseline)
    lower = pilot_depth + 1
    return {
        "lower_cap": lower,
        "upper_cap": upper,
        "empty": lower > upper,
        "width": max(0, upper - lower + 1),
        "pilot_queue_depth": pilot_depth,
        "why_lower": "cap must exceed the PILOT prefetch depth (qwen36.c:2005)",
        "why_upper": "terminal footprint must fit memory.max so the engine's LRU binds",
    }


def cap_verdict(cap: int, baseline: int = NUC_BASELINE,
                memory_max: int = NUC_MEMORY_MAX, swap_total: int = NUC_SWAP_TOTAL,
                pilot_depth: int = PILOT_QUEUE_DEPTH,
                geom: SlotGeometry = QWEN36_SLOT) -> dict:
    """`bound_by` plus the prefetch floor: the whole answer for one cap."""
    out = bound_by(cap, baseline, memory_max, swap_total, geom)
    band = cap_band(baseline, memory_max, pilot_depth, geom)
    out["above_pilot_floor"] = cap > pilot_depth
    out["in_sound_band"] = band["lower_cap"] <= cap <= band["upper_cap"]
    out["band"] = band
    out["healthy"] = bool(out["healthy"] and out["above_pilot_floor"])
    return out


def bound_by(cap: int, baseline: int = NUC_BASELINE,
             memory_max: int = NUC_MEMORY_MAX, swap_total: int = NUC_SWAP_TOTAL,
             geom: SlotGeometry = QWEN36_SLOT) -> dict:
    """Which mechanism stops this cache growing: the engine's LRU, or the kernel?

    This is the operator-facing reframing round 388 arrived at. `--cap` is not a
    memory budget, it is a choice of *bounding mechanism*:

      * `terminal <= memory.max`      -> the engine's own LRU eviction
        (qwen36.c:1322-1330) engages first. Steady state, no swap, no OOM risk.
      * `memory.max < terminal <= memory.max + swap` -> the cgroup limit
        engages first. The cache keeps growing, reclaim pushes expert weights to
        swap, and every subsequent hit on a swapped expert is a major fault.
        Survivable, and the decode rate is not.
      * `terminal > memory.max + swap` -> nothing bounds it but the OOM killer.

    At `--cap 256` the engine's own ceiling (44.00 GB) sits above BOTH kernel
    limits, so the LRU that qwen36.c implements can never run on this box."""
    terminal = geom.terminal_bytes(cap, baseline)
    ram_plus_swap = memory_max + swap_total
    if terminal <= memory_max:
        mech, healthy = "engine_lru", True
    elif terminal <= ram_plus_swap:
        mech, healthy = "cgroup_limit_then_swap", False
    else:
        mech, healthy = "oom_killer", False
    return {
        "cap": cap,
        "terminal_bytes": terminal,
        "memory_max": memory_max,
        "ram_plus_swap": ram_plus_swap,
        "over_memory_max_bytes": terminal - memory_max,
        "over_ram_plus_swap_bytes": terminal - ram_plus_swap,
        "fits_ram": terminal <= memory_max,
        "fits_ram_plus_swap": terminal <= ram_plus_swap,
        "bounded_by": mech,
        "healthy": healthy,
    }


def wall(current: int = NUC_MEMORY_CURRENT, baseline: int = NUC_BASELINE,
         memory_max: int = NUC_MEMORY_MAX, swap_total: int = NUC_SWAP_TOTAL,
         requests_so_far: float = 2.0, geom: SlotGeometry = QWEN36_SLOT,
         snap: "CgroupSnapshot | None" = None) -> dict:
    """How far is this deployment from `memory.max`, in slots and in requests?

    `swap_total` is folded in because the cgroup has `memory.swap.max = max`:
    reclaim of a ~all-anonymous working set can only go to swap, so the real
    order of events is (1) memory.max reached, (2) swap fills, (3) cgroup OOM
    kill. The two numbers are reported separately, never summed into one
    reassuring total."""
    if snap is not None:
        current = snap.memory_current
        memory_max = snap.memory_max
        f = fill_from_snapshot(snap, baseline, geom)
        headroom = snap.headroom_bytes
        naive_headroom = snap.naive_headroom_bytes
    else:
        f = fill_from_current(current, baseline, geom)
        headroom = naive_headroom = memory_max - current
    if headroom < 0:
        raise ExpertCacheError(f"current {current} already exceeds memory.max {memory_max}")
    slots_to_max = headroom // geom.slot_bytes
    slots_to_swap_exhausted = (headroom + swap_total) // geom.slot_bytes
    unfilled = geom.total_slots - f.slots_loaded

    out = {
        "fill": f.as_dict(),
        "observable": "anon+swap.current" if snap is not None else "memory.current",
        "headroom_bytes": headroom,
        "naive_headroom_bytes": naive_headroom,
        "headroom_overstatement_bytes": naive_headroom - headroom,
        "headroom_pct_of_max": 100.0 * headroom / memory_max,
        "slots_to_memory_max": int(slots_to_max),
        "slots_to_swap_exhausted": int(slots_to_swap_exhausted),
        "slots_still_unfilled": unfilled,
        "terminal_bytes_at_current_cap": geom.terminal_bytes(geom.experts, baseline),
        "terminal_overshoot_bytes": geom.terminal_bytes(geom.experts, baseline) - memory_max,
        "cap_fits_in_memory_max": geom.max_cap(memory_max, baseline),
    }

    # Fraction at which the cgroup hits memory.max.
    frac_at_max = (f.slots_loaded + slots_to_max) / geom.total_slots
    out["fraction_at_memory_max"] = frac_at_max
    out["probe"] = probe_budget(headroom, f.fraction, geom=geom)

    if requests_so_far > 0 and 0.0 < f.fraction < 1.0 and frac_at_max < 1.0:
        x_now = saturating_exposure_for_fraction(f.fraction)
        x_max = saturating_exposure_for_fraction(frac_at_max)
        per_request = x_now / requests_so_far
        out["saturating"] = {
            "requests_so_far": requests_so_far,
            "exposure_now": x_now,
            "exposure_per_request": per_request,
            "requests_to_memory_max": (x_max - x_now) / per_request,
            "fraction_after_one_more_request":
                saturating_fraction_after_exposure(x_now + per_request),
            "bytes_after_one_more_request": baseline + geom.slot_bytes * round(
                geom.total_slots * saturating_fraction_after_exposure(x_now + per_request)),
        }
    if 0.0 < f.fraction < 1.0:
        out["uniform"] = {
            "tokens_implied_by_observed_fill": uniform_tokens_for_fraction(f.fraction),
            "tokens_to_memory_max": uniform_tokens_for_fraction(frac_at_max),
        }
    return out


def plan(memory_max: int = NUC_MEMORY_MAX, baseline: int = NUC_BASELINE,
         margins=(0, GIB, 2 * GIB), geom: SlotGeometry = QWEN36_SLOT,
         swap_total: int = NUC_SWAP_TOTAL) -> dict:
    rows = []
    for m in margins:
        cap = geom.max_cap(memory_max, baseline, m)
        rows.append({
            "margin_bytes": m,
            "max_cap": cap,
            "terminal_bytes": geom.terminal_bytes(cap, baseline) if cap >= 0 else None,
            "terminal_pct_of_max": (100.0 * geom.terminal_bytes(cap, baseline) / memory_max)
                                    if cap >= 0 else None,
        })
    caps = sorted({geom.experts, 204, geom.max_cap(memory_max + swap_total, baseline),
                   geom.max_cap(memory_max, baseline), 159})
    return {
        "memory_max": memory_max,
        "swap_total": swap_total,
        "baseline": baseline,
        "bytes_per_cap_unit": geom.bytes_per_cap_unit,
        "rows": rows,
        "max_cap_fits_ram": geom.max_cap(memory_max, baseline),
        "max_cap_fits_ram_plus_swap": geom.max_cap(memory_max + swap_total, baseline),
        "bound_by": [cap_verdict(c, baseline, memory_max, swap_total,
                                 geom=geom) for c in caps],
        "sound_band": cap_band(baseline, memory_max, geom=geom),
    }


def geometry_report(geom: SlotGeometry = QWEN36_SLOT) -> dict:
    return {
        "hidden": geom.hidden, "inter": geom.inter, "expert_gs": geom.expert_gs,
        "layers": geom.layers, "experts": geom.experts,
        "scale_count_gu": geom.scale_count_gu, "scale_count_d": geom.scale_count_d,
        "weight_bytes_int8": geom.weight_bytes,
        "scale_bytes_f32": geom.scale_bytes,
        "slot_bytes": geom.slot_bytes,
        "packed_disk_bytes": geom.packed_disk_bytes,
        "unpack_ratio": geom.unpack_ratio,
        "int4_shadow_bytes_if_cuda": geom.int4_shadow_bytes,
        "shadow_active_on_nuc": SLOT_SHADOW_ON_NUC,
        "bytes_per_cap_unit": geom.bytes_per_cap_unit,
        "total_slots": geom.total_slots,
        "cache_bytes_at_cap_256": geom.cache_bytes(geom.experts),
        "terminal_bytes_at_cap_256": geom.terminal_bytes(geom.experts),
        # fast_lane.py's pre-round-376 constant, kept here so the correction is
        # checkable rather than asserted.
        "fast_lane_pre_r376_expert_bytes": 1_572_864 + 196_608,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="mode", required=True)

    def common(sp):
        sp.add_argument("--hidden", type=int, default=NUC_HIDDEN)
        sp.add_argument("--inter", type=int, default=NUC_INTER)
        sp.add_argument("--expert-gs", type=int, default=NUC_EXPERT_GS)
        sp.add_argument("--layers", type=int, default=NUC_LAYERS)
        sp.add_argument("--experts", type=int, default=NUC_EXPERTS)

    gp = sub.add_parser("geometry", help="per-slot byte accounting from the C source")
    common(gp)

    pp = sub.add_parser("plan", help="largest --cap whose TERMINAL footprint fits")
    common(pp)
    pp.add_argument("--memory-max", type=int, default=NUC_MEMORY_MAX)
    pp.add_argument("--baseline", type=int, default=NUC_BASELINE)

    fp = sub.add_parser("fill", help="invert an observed memory.current into slots")
    common(fp)
    fp.add_argument("--current", type=int, default=NUC_MEMORY_CURRENT)
    fp.add_argument("--baseline", type=int, default=NUC_BASELINE)

    wp = sub.add_parser("wall", help="distance to memory.max in slots and requests")
    common(wp)
    wp.add_argument("--current", type=int, default=NUC_MEMORY_CURRENT)
    wp.add_argument("--baseline", type=int, default=NUC_BASELINE)
    wp.add_argument("--memory-max", type=int, default=NUC_MEMORY_MAX)
    wp.add_argument("--swap-total", type=int, default=NUC_SWAP_TOTAL)
    wp.add_argument("--requests", type=float, default=2.0)
    wp.add_argument("--anon", type=int, default=None,
                    help="memory.stat anon; with --swap-current switches `wall` to "
                         "the allocation-faithful observable (round 388)")
    wp.add_argument("--swap-current", type=int, default=0)
    wp.add_argument("--kernel", type=int, default=0)
    wp.add_argument("--file", type=int, default=0)

    sp = sub.add_parser("snapshot", help="residency vs allocation for one cgroup reading")
    sp.add_argument("--current", type=int, default=R388_MEMORY_CURRENT)
    sp.add_argument("--anon", type=int, default=R388_ANON)
    sp.add_argument("--swap-current", type=int, default=R388_SWAP_CURRENT)
    sp.add_argument("--kernel", type=int, default=R388_KERNEL)
    sp.add_argument("--file", type=int, default=R388_FILE)
    sp.add_argument("--memory-max", type=int, default=NUC_MEMORY_MAX)

    bp = sub.add_parser("bound", help="which mechanism bounds the cache at a given --cap")
    common(bp)
    bp.add_argument("--cap", type=int, default=NUC_EXPERTS)
    bp.add_argument("--baseline", type=int, default=NUC_BASELINE)
    bp.add_argument("--memory-max", type=int, default=NUC_MEMORY_MAX)
    bp.add_argument("--swap-total", type=int, default=NUC_SWAP_TOTAL)

    args = p.parse_args(argv)
    geom = SlotGeometry(
        hidden=getattr(args, "hidden", NUC_HIDDEN),
        inter=getattr(args, "inter", NUC_INTER),
        expert_gs=getattr(args, "expert_gs", NUC_EXPERT_GS),
        layers=getattr(args, "layers", NUC_LAYERS),
        experts=getattr(args, "experts", NUC_EXPERTS))

    if args.mode == "snapshot":
        snap = CgroupSnapshot(memory_current=args.current, anon=args.anon,
                              swap_current=args.swap_current, kernel=args.kernel,
                              file=args.file, memory_max=args.memory_max)
        out = snap.as_dict()
        out["fill_from_allocation"] = fill_from_snapshot(snap).as_dict()
        out["fill_from_residency"] = fill_from_current(snap.memory_current).as_dict()
        out["monotonicity_if_compared_by_residency"] = check_monotone(
            fill_from_current(R382_MEMORY_CURRENT),
            fill_from_current(snap.memory_current))
        print(json.dumps(out, indent=2))
        return 0
    if args.mode == "bound":
        print(json.dumps(cap_verdict(args.cap, args.baseline, args.memory_max,
                                     args.swap_total, geom=geom), indent=2))
        return 0
    if args.mode == "geometry":
        print(json.dumps(geometry_report(geom), indent=2))
    elif args.mode == "plan":
        print(json.dumps(plan(args.memory_max, args.baseline, geom=geom), indent=2))
    elif args.mode == "fill":
        print(json.dumps(fill_from_current(args.current, args.baseline, geom).as_dict(),
                         indent=2))
    elif args.mode == "wall":
        snap = None
        if args.anon is not None:
            snap = CgroupSnapshot(memory_current=args.current, anon=args.anon,
                                  swap_current=args.swap_current, kernel=args.kernel,
                                  file=args.file, memory_max=args.memory_max)
        print(json.dumps(wall(args.current, args.baseline, args.memory_max,
                              args.swap_total, args.requests, geom, snap), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
