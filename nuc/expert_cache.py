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
3.  **Fill is monotone and capped.** The miss path is
    `if (lc->n < lc->cap) { s = &lc->slots[lc->n++]; slot_ensure_allocated(...); }`
    -- a new block is malloc'd only while the layer has unused slots; past that
    the LRU reuses an existing block. So footprint climbs from `baseline` to
    `baseline + n_layers*cap*slot_bytes` and then stops. `--cap` is a hard
    ceiling on RSS, and any snapshot taken before the ceiling is reached is a
    *mid-fill* reading, not the engine's footprint. Rounds 124 and 364 both
    read a mid-fill snapshot and reported it as a steady state.

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

# cgroup user.slice/.../qwen36-colibri.service, round 376 19:55:44Z.
NUC_MEMORY_MAX = 32_212_254_720          # 30 GiB, memory.max
NUC_MEMORY_CURRENT = 30_870_429_696      # memory.current (byte-identical to r370)
NUC_MEMORY_PEAK = 31_670_497_280         # memory.peak
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


def fill_from_current(current: int, baseline: int = NUC_BASELINE,
                      geom: SlotGeometry = QWEN36_SLOT) -> Fill:
    """Invert an observed `memory.current` into "how many slots are populated".

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

def wall(current: int = NUC_MEMORY_CURRENT, baseline: int = NUC_BASELINE,
         memory_max: int = NUC_MEMORY_MAX, swap_total: int = NUC_SWAP_TOTAL,
         requests_so_far: float = 2.0, geom: SlotGeometry = QWEN36_SLOT) -> dict:
    """How far is this deployment from `memory.max`, in slots and in requests?

    `swap_total` is folded in because the cgroup has `memory.swap.max = max`:
    reclaim of a ~all-anonymous working set can only go to swap, so the real
    order of events is (1) memory.max reached, (2) swap fills, (3) cgroup OOM
    kill. The two numbers are reported separately, never summed into one
    reassuring total."""
    f = fill_from_current(current, baseline, geom)
    headroom = memory_max - current
    if headroom < 0:
        raise ExpertCacheError(f"current {current} already exceeds memory.max {memory_max}")
    slots_to_max = headroom // geom.slot_bytes
    slots_to_swap_exhausted = (headroom + swap_total) // geom.slot_bytes
    unfilled = geom.total_slots - f.slots_loaded

    out = {
        "fill": f.as_dict(),
        "headroom_bytes": headroom,
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
         margins=(0, GIB, 2 * GIB), geom: SlotGeometry = QWEN36_SLOT) -> dict:
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
    return {
        "memory_max": memory_max,
        "baseline": baseline,
        "bytes_per_cap_unit": geom.bytes_per_cap_unit,
        "rows": rows,
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

    args = p.parse_args(argv)
    geom = SlotGeometry(hidden=args.hidden, inter=args.inter, expert_gs=args.expert_gs,
                        layers=args.layers, experts=args.experts)

    if args.mode == "geometry":
        print(json.dumps(geometry_report(geom), indent=2))
    elif args.mode == "plan":
        print(json.dumps(plan(args.memory_max, args.baseline, geom=geom), indent=2))
    elif args.mode == "fill":
        print(json.dumps(fill_from_current(args.current, args.baseline, geom).as_dict(),
                         indent=2))
    elif args.mode == "wall":
        print(json.dumps(wall(args.current, args.baseline, args.memory_max,
                              args.swap_total, args.requests, geom), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
