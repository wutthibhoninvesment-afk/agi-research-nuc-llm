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
