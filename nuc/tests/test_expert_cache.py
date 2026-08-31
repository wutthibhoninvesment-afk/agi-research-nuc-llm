"""Tests for nuc/expert_cache.py (round 376).

The point of this module is that every number is arithmetic over the allocator
in `/work/src/colibri-v170/c/qwen36.c`, not a fit. So the tests are mostly of
two kinds:

  * transcription checks -- recompute `slot_ensure_allocated` by hand, from the
    raw dims, and demand the module agree to the byte; and
  * closure checks against live NUC readings, which is what caught the bug this
    module exists to fix.

There is deliberately NO test asserting `slot_bytes == 3_342_336` as a bare
magic number with nothing behind it. Round 365 ("the pin that defended a false
claim") and this very round -- `test_fast_lane.py` pinned
`expert_bytes == 1_769_472`, the wrong constant, for 250+ rounds -- are the
same failure: a test that restates a constant cannot notice the constant is
wrong. Each check below either derives the value independently or ties it to a
measurement.
"""
import json
import math
import subprocess
import sys

import pytest

from nuc import expert_cache as ec


# --------------------------------------------------------- transcription

def test_slot_bytes_recomputed_from_dims_by_hand():
    """Independent recomputation of the two mallocs, spelled out longhand."""
    hidden, inter, gs = 2048, 512, 64
    # int8_t *w_block = malloc(ng + ng + nd)
    ng = inter * hidden
    nd = hidden * inter
    weights = ng + ng + nd
    # float *s_block = falloc(2*scale_count_gu + scale_count_d), falloc => *sizeof(float)
    scale_gu = inter * math.ceil(hidden / gs)
    scale_d = hidden * math.ceil(inter / gs)
    scales = 4 * (2 * scale_gu + scale_d)

    g = ec.SlotGeometry(hidden=hidden, inter=inter, expert_gs=gs)
    assert g.weight_bytes == weights == 3_145_728
    assert g.scale_bytes == scales == 196_608
    assert g.slot_bytes == weights + scales


def test_expert_gs_zero_means_per_row_scales():
    """`c->expert_gs ? grouped : per-row` -- the else branch of both helpers."""
    g = ec.SlotGeometry(expert_gs=0)
    assert g.scale_count_gu == g.inter
    assert g.scale_count_d == g.hidden
    assert g.scale_bytes == 4 * (2 * 512 + 2048)
    # per-row scales are far cheaper than gs=64, but the weights are unchanged
    assert g.weight_bytes == ec.QWEN36_SLOT.weight_bytes
    assert g.slot_bytes < ec.QWEN36_SLOT.slot_bytes


def test_scale_group_count_uses_ceiling_not_floor():
    """`(c->hidden + c->expert_gs - 1) / c->expert_gs` is integer-ceiling."""
    g = ec.SlotGeometry(hidden=100, inter=10, expert_gs=64)
    assert g.scale_count_gu == 10 * 2      # ceil(100/64) == 2, not 1
    assert g.scale_count_d == 100 * 1      # ceil(10/64) == 1


def test_unpack_ratio_is_the_correction_fast_lane_missed():
    g = ec.QWEN36_SLOT
    # the disk-side number fast_lane.py used as if it were the RAM cost
    assert g.packed_disk_bytes == 1_572_864 + 196_608
    assert g.packed_disk_bytes == ec.geometry_report()["fast_lane_pre_r376_expert_bytes"]
    # weights double, scales do not -- so the ratio is strictly between 1 and 2
    assert 1 < g.unpack_ratio < 2
    assert g.unpack_ratio == pytest.approx(17 / 9, rel=1e-12)


def test_cuda_shadow_is_not_charged_on_the_nuc():
    """`s->g4/u4/d4` are allocated only under qt_ready(); the NUC is CPU-only."""
    assert ec.SLOT_SHADOW_ON_NUC is False
    g = ec.QWEN36_SLOT
    assert g.int4_shadow_bytes == g.weight_bytes // 2
    assert g.slot_bytes == g.weight_bytes + g.scale_bytes   # shadow NOT included


# ------------------------------------------------------------ ceiling model

def test_cache_bytes_is_linear_and_capped():
    g = ec.QWEN36_SLOT
    assert g.cache_bytes(0) == 0
    assert g.cache_bytes(1) == g.bytes_per_cap_unit == 40 * g.slot_bytes
    assert g.cache_bytes(256) == 256 * 40 * g.slot_bytes
    for bad in (-1, 257):
        with pytest.raises(ec.ExpertCacheError):
            g.cache_bytes(bad)


def test_cap_256_terminal_does_not_fit_the_cgroup():
    """The round's headline, as an assertion: full residency is unreachable."""
    g = ec.QWEN36_SLOT
    terminal = g.terminal_bytes(256)
    assert terminal > ec.NUC_MEMORY_MAX
    # ... and not by a rounding margin: ~11.8 GB over a 30 GiB cap
    assert terminal - ec.NUC_MEMORY_MAX > 11 * ec.GB
    # not even memory.max PLUS every byte of swap on the box gets there
    assert terminal > ec.NUC_MEMORY_MAX + ec.NUC_SWAP_TOTAL


def test_max_cap_is_the_largest_that_fits_and_the_next_one_does_not():
    g = ec.QWEN36_SLOT
    cap = g.max_cap()
    assert cap == 167
    assert g.terminal_bytes(cap) <= ec.NUC_MEMORY_MAX
    assert g.terminal_bytes(cap + 1) > ec.NUC_MEMORY_MAX


def test_max_cap_respects_margin_monotonically():
    g = ec.QWEN36_SLOT
    caps = [g.max_cap(margin=m) for m in (0, ec.GIB, 2 * ec.GIB, 4 * ec.GIB)]
    assert caps == sorted(caps, reverse=True)
    assert caps[0] == 167 and caps[1] == 159 and caps[2] == 151
    with pytest.raises(ec.ExpertCacheError):
        g.max_cap(margin=-1)


def test_max_cap_returns_minus_one_when_even_the_dense_weights_do_not_fit():
    g = ec.QWEN36_SLOT
    assert g.max_cap(budget=ec.NUC_BASELINE - 1) == -1
    # and it is NOT confused with a legitimate cap of 0
    assert g.max_cap(budget=ec.NUC_BASELINE) == 0


def test_e4_headline_recommendation_does_not_fit():
    """E4/round 124 recommended `--cap 204`. Under the corrected slot size it
    overshoots memory.max by ~4.8 GB, so that restart would have OOMed too."""
    g = ec.QWEN36_SLOT
    assert g.terminal_bytes(204) > ec.NUC_MEMORY_MAX
    assert (g.terminal_bytes(204) - ec.NUC_MEMORY_MAX) / ec.GB == pytest.approx(4.83, abs=0.05)
    # E4's lower two rows do survive the correction
    assert g.terminal_bytes(143) < ec.NUC_MEMORY_MAX
    assert g.terminal_bytes(75) < ec.NUC_MEMORY_MAX


# ------------------------------------------------------------- inversion

def test_fill_inverts_cache_bytes_exactly():
    g = ec.QWEN36_SLOT
    for cap in (0, 1, 17, 143, 167, 256):
        current = g.terminal_bytes(cap)
        f = ec.fill_from_current(current)
        assert f.slots_loaded == cap * g.layers
        assert f.cap_equivalent == pytest.approx(cap)


def test_fill_on_the_live_round_376_reading():
    f = ec.fill_from_current(ec.NUC_MEMORY_CURRENT)
    assert f.slots_loaded == 6313
    assert f.total_slots == 10240
    assert f.fraction == pytest.approx(0.6165, abs=5e-4)
    # the cache is ~62% full while the cgroup is ~96% full: that gap IS the
    # finding, so assert both halves together.
    assert ec.NUC_MEMORY_CURRENT / ec.NUC_MEMORY_MAX == pytest.approx(0.958, abs=1e-3)


def test_fill_rejects_a_current_below_baseline():
    with pytest.raises(ec.ExpertCacheError):
        ec.fill_from_current(ec.NUC_BASELINE - 1)
    assert ec.fill_from_current(ec.NUC_BASELINE).slots_loaded == 0


def test_round_124_observation_was_the_wall_not_the_ceiling():
    """31.8 GB resident + 4.2 GB swap, reported by E4 as "the footprint of
    --cap 256". Resident alone is 98.7% of memory.max and swap was 98%
    exhausted, yet the cache was only ~77% full."""
    resident_fill = ec.fill_from_current(ec.R124_RESIDENT)
    both_fill = ec.fill_from_current(ec.R124_RESIDENT + ec.R124_SWAP)
    assert ec.R124_RESIDENT / ec.NUC_MEMORY_MAX == pytest.approx(0.987, abs=2e-3)
    assert ec.R124_SWAP / ec.NUC_SWAP_TOTAL == pytest.approx(0.98, abs=0.02)
    assert resident_fill.fraction == pytest.approx(0.644, abs=5e-3)
    assert both_fill.fraction == pytest.approx(0.766, abs=5e-3)
    assert both_fill.fraction < 1.0        # never reached full residency


# --------------------------------------------------------- fill dynamics

def test_uniform_and_saturating_curves_round_trip():
    for frac in (0.01, 0.25, 0.6164942124310662, 0.9):
        t = ec.uniform_tokens_for_fraction(frac)
        assert ec.uniform_fraction_after_tokens(t) == pytest.approx(frac, rel=1e-9)
        x = ec.saturating_exposure_for_fraction(frac)
        assert ec.saturating_fraction_after_exposure(x) == pytest.approx(frac, rel=1e-9)
    assert ec.uniform_fraction_after_tokens(0) == 0.0
    assert ec.saturating_fraction_after_exposure(0) == 0.0


def test_uniform_model_is_falsified_by_the_observation():
    """Kept as an explicit test because the module ships the model anyway.

    Uniform routing says 61.65% distinct experts needs only ~31 tokens of
    traffic. The two requests that produced it ran 113 s and longer against a
    ~5 tok/s engine, i.e. hundreds of tokens. So routing is strongly skewed and
    the uniform curve must be read as a lower bound on tokens, never as an
    estimate."""
    tokens = ec.uniform_tokens_for_fraction(0.6164942124310662)
    assert tokens < 40
    # the honest consequence: uniform is wildly optimistic about how fast the
    # cache fills per token, so it must not be the model used for the warning.
    assert tokens < 113 * 5 / 10


def test_curves_reject_out_of_range_input():
    for fn in (ec.uniform_tokens_for_fraction, ec.saturating_exposure_for_fraction):
        for bad in (-0.1, 1.0, 1.5):
            with pytest.raises(ec.ExpertCacheError):
                fn(bad)
    with pytest.raises(ec.ExpertCacheError):
        ec.uniform_fraction_after_tokens(-1)
    with pytest.raises(ec.ExpertCacheError):
        ec.saturating_fraction_after_exposure(-1)


# ----------------------------------------------------------------- the wall

def test_wall_on_the_live_reading():
    w = ec.wall()
    assert w["headroom_bytes"] == ec.NUC_MEMORY_MAX - ec.NUC_MEMORY_CURRENT
    assert w["slots_to_memory_max"] == 401
    assert w["slots_still_unfilled"] == 10240 - 6313
    # only ~10% of the still-unfilled slots fit before the hard cap
    assert w["slots_to_memory_max"] / w["slots_still_unfilled"] == pytest.approx(0.102, abs=0.01)
    assert w["cap_fits_in_memory_max"] == 167
    assert w["terminal_overshoot_bytes"] > 11 * ec.GB


def test_wall_says_the_third_request_blows_the_cap():
    w = ec.wall()
    s = w["saturating"]
    assert 0 < s["requests_to_memory_max"] < 1.0
    assert s["requests_to_memory_max"] == pytest.approx(0.225, abs=0.01)
    # one more request of the same diversity wants ~3.7 GB more than the cap allows
    assert s["bytes_after_one_more_request"] > ec.NUC_MEMORY_MAX
    assert (s["bytes_after_one_more_request"] - ec.NUC_MEMORY_MAX) > 3 * ec.GB


def test_wall_reports_swap_separately_and_does_not_sum_it_away():
    w = ec.wall()
    assert w["slots_to_swap_exhausted"] > w["slots_to_memory_max"]
    # even swap-exhausted is far short of filling the cache
    assert w["slots_to_swap_exhausted"] < w["slots_still_unfilled"]
    assert "headroom_including_swap" not in w      # no single reassuring total


def test_wall_refuses_a_current_over_memory_max():
    with pytest.raises(ec.ExpertCacheError):
        ec.wall(current=ec.NUC_MEMORY_MAX + 1)


def test_wall_at_baseline_has_no_saturating_block():
    """Zero fill => no exposure to fit; the module must omit the extrapolation
    rather than divide by zero or emit a fabricated one."""
    w = ec.wall(current=ec.NUC_BASELINE, requests_so_far=0)
    assert "saturating" not in w
    assert "uniform" not in w
    assert w["fill"]["slots_loaded"] == 0


# --------------------------------------------------------------------- CLI

@pytest.mark.parametrize("mode", ["geometry", "plan", "fill", "wall"])
def test_cli_modes_emit_json(mode):
    r = subprocess.run([sys.executable, "nuc/expert_cache.py", mode],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    import json
    json.loads(r.stdout)


def test_cli_geometry_accepts_another_box_geometry():
    r = subprocess.run([sys.executable, "nuc/expert_cache.py", "geometry",
                        "--hidden", "2048", "--inter", "1024", "--expert-gs", "0",
                        "--layers", "16", "--experts", "64"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    import json
    g = json.loads(r.stdout)
    # OLMoE-1B-7B: 3 x 2048 x 1024 int8, per-row scales
    assert g["weight_bytes_int8"] == 3 * 2048 * 1024
    assert g["total_slots"] == 16 * 64


# ------------------------------------------------- round 388: residency vs allocation
#
# These tests exist because round 388 measured `memory.current` falling
# 458,207,232 B on pgain-nuc with ZERO requests served between the two readings,
# and the previous inversion turned that into "the expert cache lost 137 slots"
# -- which `slot_ensure_allocated` makes impossible below `cap`. The fixture is
# the real r382/r388 pair, and the assertions are about the *relationship*
# between the two readings, not about either one's digits.


def test_the_two_live_readings_disagree_on_residency_and_agree_on_allocation():
    a, b = ec.R382_SNAPSHOT, ec.R388_SNAPSHOT
    assert b.memory_current < a.memory_current           # residency fell...
    assert a.memory_current - b.memory_current == 458_207_232
    assert b.allocated_anon == a.allocated_anon          # ...allocation did not
    # and the whole anon shortfall is accounted for by swap, to the byte
    assert a.anon - b.anon == b.swap_current


def test_inverting_residency_reports_an_impossible_shrink():
    earlier = ec.fill_from_current(ec.R382_MEMORY_CURRENT)
    later = ec.fill_from_current(ec.R388_MEMORY_CURRENT)
    verdict = ec.check_monotone(earlier, later)
    assert verdict["verdict"] == "instrument_error"
    assert verdict["delta_slots"] < -100


def test_inverting_allocation_is_flat_across_the_same_event():
    earlier = ec.fill_from_snapshot(ec.R382_SNAPSHOT)
    later = ec.fill_from_snapshot(ec.R388_SNAPSHOT)
    assert earlier.slots_loaded == later.slots_loaded
    assert ec.check_monotone(earlier, later)["verdict"] == "ok"


def test_check_monotone_does_not_launder_a_real_drop_through_tolerance():
    earlier = ec.fill_from_current(ec.R382_MEMORY_CURRENT)
    later = ec.fill_from_current(ec.R388_MEMORY_CURRENT)
    # even a 100-slot tolerance -- 334 MB, far past any plausible arena slop --
    # must not turn the observed 137-slot drop into "ok"
    assert ec.check_monotone(earlier, later, tolerance_slots=100)["verdict"] \
        == "instrument_error"
    with pytest.raises(ec.ExpertCacheError):
        ec.check_monotone(earlier, later, tolerance_slots=-1)


def test_check_monotone_flags_an_inversion_above_the_configured_cap():
    small = ec.fill_from_current(ec.NUC_BASELINE + 1)
    big = ec.fill_from_current(ec.NUC_BASELINE + 200 * ec.QWEN36_SLOT.bytes_per_cap_unit)
    assert ec.check_monotone(small, big, cap=159)["verdict"] == "over_cap"
    assert ec.check_monotone(small, big, cap=256)["verdict"] == "ok"


def test_naive_headroom_overstates_by_exactly_the_swapped_bytes():
    b = ec.R388_SNAPSHOT
    # the two headroom figures differ by swapped anon minus the kernel/file
    # charge that the naive figure was wrongly counting as headroom's opposite
    assert b.naive_headroom_bytes > b.headroom_bytes
    assert b.headroom_overstatement_bytes == (
        b.swap_current + b.non_anon_resident - (b.memory_current - b.anon))
    # before any reclaim the two agree exactly
    assert ec.R382_SNAPSHOT.headroom_overstatement_bytes == 0


def test_snapshot_rejects_anon_larger_than_the_resident_charge():
    with pytest.raises(ec.ExpertCacheError):
        ec.CgroupSnapshot(memory_current=10, anon=11)
    with pytest.raises(ec.ExpertCacheError):
        ec.CgroupSnapshot(memory_current=10, anon=1, swap_current=-1)


def test_non_anon_falls_back_to_current_minus_anon_when_unbroken_out():
    # round 382 read no `kernel`/`file`; the snapshot must still be usable
    assert ec.R382_SNAPSHOT.non_anon_resident == (
        ec.R382_MEMORY_CURRENT - ec.R382_ANON)


def test_wall_on_the_allocation_observable_reports_both_headrooms():
    w = ec.wall(snap=ec.R388_SNAPSHOT)
    assert w["observable"] == "anon+swap.current"
    assert w["naive_headroom_bytes"] > w["headroom_bytes"]
    assert w["headroom_overstatement_bytes"] == \
        ec.R388_SNAPSHOT.headroom_overstatement_bytes
    # and the legacy path is unchanged
    legacy = ec.wall(current=ec.R388_MEMORY_CURRENT)
    assert legacy["observable"] == "memory.current"
    assert legacy["headroom_bytes"] == legacy["naive_headroom_bytes"]


# ----------------------------------------------------------------- probe budget


def test_one_token_can_demand_layers_times_topk_slots():
    b = ec.probe_budget(10**12, 0.0)
    assert b["slots_per_token_worst_case"] == ec.NUC_LAYERS * ec.NUC_TOPK == 320


def test_the_live_deployment_has_room_for_one_token_worst_case():
    b = ec.wall(snap=ec.R388_SNAPSHOT)["probe"]
    assert b["worst_case_tokens"] == 1
    # the optimistic model does not rescue it either -- same order of magnitude
    assert b["expected_tokens"] < 10
    assert b["expected_tokens"] >= b["worst_case_tokens"]


def test_probe_budget_expected_beats_worst_case_only_when_partly_filled():
    empty = ec.probe_budget(10**10, 0.0)
    assert empty["expected_tokens"] == empty["worst_case_tokens"]
    half = ec.probe_budget(10**10, 0.5)
    assert half["expected_tokens"] == 2 * empty["worst_case_tokens"]
    full = ec.probe_budget(10**10, 1.0)
    assert full["expected_tokens"] is None      # nothing left to miss on


@pytest.mark.parametrize("kwargs", [
    {"headroom_bytes": -1, "fill_fraction": 0.5},
    {"headroom_bytes": 10, "fill_fraction": 1.5},
    {"headroom_bytes": 10, "fill_fraction": 0.5, "topk": 0},
])
def test_probe_budget_rejects_nonsense(kwargs):
    with pytest.raises(ec.ExpertCacheError):
        ec.probe_budget(**kwargs)


# --------------------------------------------------- which mechanism bounds it


def test_cap_256_is_bounded_by_the_oom_killer_not_the_engine():
    b = ec.bound_by(256)
    assert b["bounded_by"] == "oom_killer"
    assert not b["fits_ram"] and not b["fits_ram_plus_swap"]


def test_e4_cap_204_survives_ram_plus_swap_by_far_less_than_r376_said():
    """Round 376 graded cap 204 'over by 4.83 GB' against `memory.max` alone.

    Against RAM+swap -- which is what round 124 actually measured the box doing,
    31.8 GB resident PLUS 4.2 GB swapped -- the overshoot is an order of
    magnitude smaller. The verdict (does not fit) survives; the margin does not.
    """
    b = ec.bound_by(204)
    assert b["over_memory_max_bytes"] == 4_831_801_344      # round 376's number
    assert b["over_ram_plus_swap_bytes"] == 536_838_144     # ~9x smaller
    assert b["bounded_by"] == "oom_killer"


def test_there_is_a_cap_band_that_survives_but_is_not_healthy():
    ram_only = ec.QWEN36_SLOT.max_cap(ec.NUC_MEMORY_MAX, ec.NUC_BASELINE)
    with_swap = ec.QWEN36_SLOT.max_cap(
        ec.NUC_MEMORY_MAX + ec.NUC_SWAP_TOTAL, ec.NUC_BASELINE)
    assert with_swap > ram_only
    assert ec.bound_by(ram_only)["bounded_by"] == "engine_lru"
    assert ec.bound_by(with_swap)["bounded_by"] == "cgroup_limit_then_swap"
    assert ec.bound_by(with_swap)["healthy"] is False


def test_the_recommended_cap_makes_the_engines_own_lru_the_binding_mechanism():
    b = ec.bound_by(159)
    assert b["bounded_by"] == "engine_lru" and b["healthy"] is True


def test_plan_reports_both_axes():
    pl = ec.plan()
    assert pl["max_cap_fits_ram"] < pl["max_cap_fits_ram_plus_swap"]
    mechs = {r["cap"]: r["bounded_by"] for r in pl["bound_by"]}
    assert mechs[256] == "oom_killer"
    assert mechs[159] == "engine_lru"


@pytest.mark.parametrize("mode", ["snapshot", "bound"])
def test_new_cli_modes_emit_json(mode):
    out = subprocess.run([sys.executable, "nuc/expert_cache.py", mode],
                         capture_output=True, text=True, check=True)
    payload = json.loads(out.stdout)
    assert payload


def test_cli_wall_switches_observable_when_given_anon():
    out = subprocess.run(
        [sys.executable, "nuc/expert_cache.py", "wall",
         "--current", str(ec.R388_MEMORY_CURRENT), "--anon", str(ec.R388_ANON),
         "--swap-current", str(ec.R388_SWAP_CURRENT),
         "--kernel", str(ec.R388_KERNEL), "--file", str(ec.R388_FILE)],
        capture_output=True, text=True, check=True)
    payload = json.loads(out.stdout)
    assert payload["observable"] == "anon+swap.current"
    assert payload["fill"]["slots_loaded"] == 6232


# ------------------------------------------------- the prefetch floor (round 388)


def test_the_sound_cap_band_is_closed_at_both_ends():
    band = ec.cap_band()
    assert band["lower_cap"] == ec.PILOT_QUEUE_DEPTH + 1 == 129
    assert band["upper_cap"] == ec.QWEN36_SLOT.max_cap(ec.NUC_MEMORY_MAX, ec.NUC_BASELINE)
    assert not band["empty"]
    assert band["width"] == band["upper_cap"] - band["lower_cap"] + 1


@pytest.mark.parametrize("cap", [16, 64, 128])
def test_e4s_small_lane_caps_sit_below_the_prefetch_floor(cap):
    """Round 124 proposed cap 16 and cap 64 on RAM grounds alone.

    Both fit RAM comfortably -- `bounded_by` says `engine_lru` for each -- and
    both are nonetheless unsound, because a layer whose whole cache is smaller
    than the 128-deep PILOT queue can have every slot in flight at once. The
    RAM axis cannot see this, which is exactly why it needs its own field."""
    v = ec.cap_verdict(cap)
    assert v["fits_ram"] and v["bounded_by"] == "engine_lru"   # the old verdict
    assert not v["above_pilot_floor"]                          # the new one
    assert not v["in_sound_band"] and v["healthy"] is False


def test_the_recommended_cap_is_inside_the_band():
    v = ec.cap_verdict(159)
    assert v["in_sound_band"] and v["above_pilot_floor"] and v["healthy"]


def test_the_band_is_empty_when_ram_cannot_reach_the_prefetch_floor():
    """A smaller box has no sound cap at all, and must say so rather than
    rounding down into the in-flight path."""
    tiny = ec.NUC_BASELINE + 100 * ec.QWEN36_SLOT.bytes_per_cap_unit
    band = ec.cap_band(memory_max=tiny)
    assert band["upper_cap"] == 100 < band["lower_cap"]
    assert band["empty"] and band["width"] == 0


def test_cap_band_rejects_a_negative_pilot_depth():
    with pytest.raises(ec.ExpertCacheError):
        ec.cap_band(pilot_depth=-1)


def test_a_cap_above_ram_is_unhealthy_even_though_it_clears_the_floor():
    v = ec.cap_verdict(256)
    assert v["above_pilot_floor"] and not v["in_sound_band"]
    assert v["healthy"] is False


def test_plan_carries_the_band():
    assert ec.plan()["sound_band"]["lower_cap"] == 129


# ------------------------------------ round 394: the baseline was residency too
#
# Round 388 replaced the inversion's NUMERATOR with `anon + swap.current` and
# left the DENOMINATOR -- `NUC_BASELINE` -- as a `memory.current` reading, on
# the stated grounds that "round 364's was taken with swap.current == 0, so it
# serves for both". `swap.current == 0` makes `anon + swap == anon`; it does not
# make `memory.current == anon`. These tests tie the correction to a
# measurement, not to a second model.


def test_the_measured_fill_is_the_sum_of_two_observed_steps_not_an_inversion():
    """`sar -r` bracketed each of the boot's two completions with a bucket."""
    assert ec.R394_REQ1_STEP_KB == ec.R394_COMMIT_POST_REQ1_KB - ec.R394_COMMIT_PRE_REQ1_KB
    assert ec.R394_REQ2_STEP_KB == ec.R394_COMMIT_POST_REQ2_KB - ec.R394_COMMIT_PRE_REQ2_KB
    assert ec.R394_MEASURED_FILL_BYTES == (
        ec.R394_REQ1_STEP_KB + ec.R394_REQ2_STEP_KB) * 1024


def test_the_witness_rejects_the_residency_baseline_and_keeps_all_three_others():
    w = ec.baseline_witness()
    assert w["verdict"] == "resolved"
    assert w["candidates"]["modelled_residency"]["survives"] is False
    assert sorted(w["survivors"]) == ["anon", "commit", "disk"]


def test_the_residency_baseline_is_wrong_by_nineteen_percent_not_by_rounding():
    """The gap is 4.9 GB. The three corrected routes disagree by 0.22 GB."""
    w = ec.baseline_witness()["candidates"]
    assert abs(w["modelled_residency"]["error_fraction"]) > 0.15
    for name in ("disk", "commit", "anon"):
        assert abs(w[name]["error_fraction"]) < 0.01


def test_the_three_corrected_routes_are_independent_of_each_other():
    """Disk geometry, Committed_AS and sar's kbmemused share no input."""
    assert ec.ALLOC_BASELINE_FROM_DISK == (
        ec.NUC_MODEL_DISK_BYTES
        - ec.QWEN36_SLOT.total_slots * ec.QWEN36_SLOT.packed_disk_bytes)
    assert ec.ALLOC_BASELINE_FROM_COMMIT == (
        ec.R394_COMMIT_PRE_REQ1_KB
        - (ec.R394_SYSTEM_COMMIT_KB - ec.R394_QWEN36_VMDATA_KB)) * 1024
    assert ec.ALLOC_BASELINE_FROM_ANON == (
        ec.R394_MEMUSED_PRE_REQ1_KB
        - (ec.R394_MEMUSED_NOW_KB - ec.R394_CGROUP_ANON_KB)) * 1024


def test_cap_sizing_takes_the_LARGEST_baseline_in_the_band():
    b = ec.alloc_baseline_band()
    assert b["recommended_for_cap_sizing"] == b["hi_bytes"] == ec.NUC_ALLOC_BASELINE
    assert b["spread_cap_units"] < 2      # the band is under two cap units wide


def test_the_corrected_band_reaches_204_and_stops_there():
    band = ec.cap_band(baseline=ec.NUC_ALLOC_BASELINE)
    assert band["lower_cap"] == ec.PILOT_QUEUE_DEPTH + 1 == 129
    assert band["upper_cap"] == 204
    assert ec.bound_by(204, ec.NUC_ALLOC_BASELINE)["bounded_by"] == "engine_lru"
    assert ec.bound_by(205, ec.NUC_ALLOC_BASELINE)["bounded_by"] != "engine_lru"


def test_round_124s_cap_204_headline_is_recovered_not_asserted():
    """Rounds 376 and 388 rejected 204 against the residency baseline.

    This is not a restatement of 204 -- it recomputes the largest cap whose
    terminal footprint fits `memory.max` from the corrected baseline and
    demands it land there."""
    largest = int((ec.NUC_MEMORY_MAX - ec.NUC_ALLOC_BASELINE)
                  // ec.QWEN36_SLOT.bytes_per_cap_unit)
    assert largest == 204


def test_the_recommendation_keeps_a_margin_far_wider_than_the_baseline_spread():
    r = ec.recommend_cap()
    assert r["verdict"] == "recommend"
    assert ec.PILOT_QUEUE_DEPTH < r["cap"] <= r["band"]["upper_cap"]
    assert r["actual_margin_bytes"] >= r["margin_bytes"]
    assert r["actual_margin_bytes"] > 4 * ec.alloc_baseline_band()["spread_bytes"]
    assert r["bounded_by"]["bounded_by"] == "engine_lru"


def test_a_margin_that_swallows_the_band_says_so_instead_of_recommending():
    r = ec.recommend_cap(margin_bytes=ec.NUC_MEMORY_MAX - ec.NUC_ALLOC_BASELINE)
    assert r["cap"] is None
    assert r["verdict"] == "margin_excludes_the_whole_band"


def test_a_negative_margin_is_rejected():
    with pytest.raises(ec.ExpertCacheError):
        ec.recommend_cap(margin_bytes=-1)


def test_the_measured_curve_agrees_with_the_corrected_inversion_not_the_old_one():
    """Two routes to "how many slots are loaded", which must now agree.

    Sum of the two measured request steps vs (allocation - corrected baseline).
    Under the residency baseline they differ by ~1,470 slots."""
    from_curve = sum(s.slots for s in ec.fill_curve())
    from_inversion = ec.fill_from_snapshot(
        ec.R388_SNAPSHOT, baseline=ec.NUC_ALLOC_BASELINE).slots_loaded
    assert abs(from_curve - from_inversion) < 60          # < 0.8 %
    old = ec.fill_from_snapshot(ec.R388_SNAPSHOT).slots_loaded
    assert from_curve - old > 1_400


def test_the_per_request_cost_decays_and_the_third_request_still_does_not_fit():
    head = ec.NUC_MEMORY_MAX - (ec.NUC_ANON_PLUS_SWAP + ec.R388_KERNEL + ec.R388_FILE)
    s = ec.request_cost_series(head)
    assert s["observed"][0]["slots"] > s["observed"][1]["slots"]
    assert 0 < s["decay_ratio"] < 1
    assert s["verdict"] == "unsafe"
    assert s["next_over_headroom"] > 1.5


def test_the_docstrings_robustness_claim_is_the_one_the_arithmetic_supports():
    """The claim is 1.906x, i.e. the fit must be overstated by 47.5 % to flip.

    Written first as "wrong by half", which 1.906 does not support: halving
    870.2 gives 435.1, BELOW the 456.5 slots of headroom, so the verdict would
    have flipped. Asserting the true factor keeps prose and arithmetic tied."""
    head = ec.NUC_MEMORY_MAX - (ec.NUC_ANON_PLUS_SWAP + ec.R388_KERNEL + ec.R388_FILE)
    s = ec.request_cost_series(head)
    assert s["next_request_slots_est"] * 0.5 < s["headroom_slots"]
    assert s["next_request_slots_est"] / 1.9 > s["headroom_slots"]
    assert s["next_over_headroom"] == pytest.approx(1.906, abs=0.001)


def test_request_cost_needs_two_observations_and_rejects_a_negative_step():
    with pytest.raises(ec.ExpertCacheError):
        ec.request_cost_series(1, step_kb=(100,))
    with pytest.raises(ec.ExpertCacheError):
        ec.fill_curve(step_kb=(100, -1))
    with pytest.raises(ec.ExpertCacheError):
        ec.fill_curve(step_kb=())


def test_a_baseline_at_or_above_the_allocation_is_an_error_not_a_negative_fill():
    with pytest.raises(ec.ExpertCacheError):
        ec.baseline_witness(candidates={"absurd": ec.NUC_ANON_PLUS_SWAP})
    with pytest.raises(ec.ExpertCacheError):
        ec.baseline_witness(measured_fill=0)


def test_the_new_cli_modes_run():
    for mode in ("baseline", "curve", "recommend"):
        out = subprocess.run([sys.executable, "-m", "nuc.expert_cache", mode],
                             capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        json.loads(out.stdout)
