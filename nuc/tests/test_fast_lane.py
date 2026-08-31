"""Offline tests for nuc/fast_lane.py and nuc/fast_lane_sink.py."""
import hashlib
import math
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import fast_lane as fl  # noqa: E402
import fast_lane_sink as sink  # noqa: E402

PROBE_LOG = """\
Mon Aug 24 15:48:26 UTC 2026
== https://huggingface.co/allenai/OLMoE-1B-7B-0125-Instruct/resolve/main/model-00001-of-00003.safetensors
curl: (28) Operation timed out after 29585 milliseconds with 2000668947 out of 4997744872 bytes received
speed_B_s=66690821 bytes=2000668947 t=29.999165 http=200 ttfb=0.823773 ip=13.214.85.108
== https://speed.cloudflare.com/__down?bytes=2000000000
speed_B_s=8 bytes=1 t=0.116620 http=403 ttfb=0.116550 ip=2606:4700:7::da
== https://huggingface.co/allenai/OLMoE-1B-7B-0125-Instruct/resolve/main/model-00003-of-00003.safetensors
speed_B_s=8661883 bytes=259939300 t=30.009558 http=200 ttfb=0.771230 ip=13.229.7.180
== -4 https://huggingface.co/allenai/OLMoE-1B-7B-0125-Instruct/resolve/main/model-00003-of-00003.safetensors
speed_B_s=11564425 bytes=233979524 t=20.232697 http=200 ttfb=0.878842 ip=54.254.163.78
"""


# ----------------------------------------------------------------- guards

def test_probe_cmd_refuses_frontier_port():
    with pytest.raises(fl.FastLaneError):
        fl.probe_cmd("http://127.0.0.1:8001/v1/models")
    argv = fl.probe_cmd("https://example.org/x.bin", seconds=12, ipv=4)
    assert argv[0] == "curl" and argv[1] == "-4" and "--max-time" in argv and argv[-1].endswith("x.bin")
    assert argv[argv.index("--max-time") + 1] == "12"


def test_check_url_default_ports():
    assert fl.check_url("https://huggingface.co/a") == "https://huggingface.co/a"
    with pytest.raises(fl.FastLaneError):
        fl.check_url("http://192.168.1.37:8001/")


# ----------------------------------------------------------------- bandwidth

def test_parse_probe_log_pairs_urls_and_skips_curl_noise():
    samples = fl.parse_probe_log(PROBE_LOG)
    assert len(samples) == 4
    assert samples[0].url.endswith("model-00001-of-00003.safetensors")
    assert samples[0].bytes == 2000668947 and samples[0].http_code == 200
    assert abs(samples[0].mb_s - 66.69) < 0.05
    assert samples[1].http_code == 403
    # the "-4 <url>" form keeps only the URL
    assert samples[3].url.startswith("https://")


def test_summary_excludes_failures_and_reports_spread():
    s = fl.summarize(fl.parse_probe_log(PROBE_LOG))
    assert s.n == 3                       # the 403 sample is excluded
    assert abs(s.min_mb_s - 8.66) < 0.05 and abs(s.max_mb_s - 66.69) < 0.05
    assert 7.5 < s.spread < 7.8
    assert len(s.per_url_mb_s) == 2       # two distinct shard URLs


def test_summary_needs_a_success():
    with pytest.raises(fl.FastLaneError):
        fl.summarize([fl.parse_curl_w("speed_B_s=8 bytes=1 t=0.1 http=403 ttfb=0.1 ip=x")])


def test_parse_curl_w_rejects_garbage():
    with pytest.raises(fl.FastLaneError):
        fl.parse_curl_w("curl: (6) Could not resolve host")


def test_download_time_uses_per_object_rates_and_slowest_fallback():
    objects = {"a": 1000 * fl.MB, "b": 1000 * fl.MB, "c": 500 * fl.MB}
    rates = {"a": 50.0, "b": 10.0}
    # a: 20 s, b: 100 s, c falls back to the slowest measured (10 MB/s): 50 s
    assert fl.download_time_s(objects, rates) == pytest.approx(170.0)
    assert fl.download_time_s(objects, rates, fallback_mb_s=50.0) == pytest.approx(130.0)
    with pytest.raises(fl.FastLaneError):
        fl.download_time_s(objects, {})


def test_gate_threshold_and_disk_margin():
    ok = fl.gate_download(8.66, disk_free_gb=677, disk_needed_gb=21.3)
    assert ok.ok and ok.reasons == []
    slow = fl.gate_download(2.9, disk_free_gb=677, disk_needed_gb=21.3)
    assert not slow.ok and "MB/s" in slow.reasons[0]
    full = fl.gate_download(30.0, disk_free_gb=30, disk_needed_gb=21.3)
    assert not full.ok and full.reasons[0].startswith("disk")
    # exactly at the threshold is NOT "> 3 MB/s"
    assert not fl.gate_download(3.0, 677, 1).ok


# ----------------------------------------------------------------- RAM planner

RSS_FULL = 31_258_644 * 1024   # qwen36 worker, cap 256, measured


def test_qwen36_geometry_is_the_ram_slot_not_the_disk_tensor():
    # ROUND 376. This test used to assert `expert_bytes == 1_769_472` and
    # `cache_bytes(256) ~= 18.119e9`, and it held green for 250+ rounds. Both
    # numbers were right about the CONTAINER ON DISK and wrong about RAM, which
    # is what `MoeGeometry.expert_bytes` is documented to mean ("bytes per
    # cached expert slot"). `qwen36.c:slot_ensure_allocated` mallocs int8, and
    # `load_expert_merged` unpacks the int4 nibbles into it. Assert BOTH figures
    # now, each labelled, so the next reader cannot re-conflate them.
    from nuc import expert_cache as ec
    slot = ec.QWEN36_SLOT
    on_disk_per_expert = 1_572_864 + 196_608          # int4 weights + f32 scales
    in_ram_per_slot = 3_145_728 + 196_608             # int8 weights + f32 scales
    assert slot.packed_disk_bytes == on_disk_per_expert
    assert slot.slot_bytes == in_ram_per_slot
    assert fl.QWEN36.expert_bytes == in_ram_per_slot
    # 20,480 expert tensors x 2 kinds → 18.119 GB ON DISK ...
    assert 256 * 40 * on_disk_per_expert == pytest.approx(18.119e9, rel=0.002)
    # ... and 34.2 GB IN RAM, which is why cap 256 cannot fit a 30 GiB cgroup.
    assert fl.QWEN36.cache_bytes(256) == pytest.approx(34.226e9, rel=0.002)
    assert fl.QWEN36.cache_bytes(256) == slot.cache_bytes(256)


def test_olmoe_footprint_anchors_on_upstream_comment():
    # chat_olmoe.sh: "~6GB cache + ~1.8GB dense =~ 7.8GB peak" at cap 64
    fp = fl.OLMOE.footprint(64, ctx=0)
    assert 7.6e9 < fp < 8.3e9
    # M3 bench row: cap 16 → RSS 1.5–1.81 GB (dense estimate dominates; ours is the upper bound)
    assert fl.OLMOE.cache_bytes(16) == pytest.approx(1.61e9, rel=0.01)
    assert fl.OLMOE.kv_bytes_per_token * 4096 == pytest.approx(1.074e9, rel=0.001)


# Round 376: RSS_FULL (32.01 GB) is smaller than a full cap-256 cache
# (34.23 GB), so it is not a physically possible anchor and `rss_at_cap` now
# rejects it. ANCHOR_36 is the resident+swap figure from PLAN-E4, the only one
# in this repo that clears the impossibility guard -- it is still unsound (see
# test_anchor_implied_dense_flags_every_qwen36_anchor), just not impossible.
ANCHOR_36 = fl.full_footprint(32_211_791_872, 4_214_800_384)

# ROUND 382. `rss_at_cap` now REFUSES an unsound anchor rather than answering
# with a warning printed one layer up, so every test below whose subject is the
# relative arithmetic has to say out loud that it is deliberately feeding the
# planner a known-bad anchor. That is the point of the keyword: an opt-in that
# has to be typed cannot be reached by accident from `plan_rows`, which is how
# round 376's warning was bypassed. Grep for UNSOUND to find every place this
# repo still computes a number it does not believe.
UNSOUND = {"allow_unsound_anchor": True}


def test_rss_at_cap_is_linear_and_bounded():
    assert fl.rss_at_cap(fl.QWEN36, ANCHOR_36, 256, 256, **UNSOUND) == ANCHOR_36
    one_slot = fl.QWEN36.layers * fl.QWEN36.expert_bytes
    assert fl.rss_at_cap(fl.QWEN36, ANCHOR_36, 256, 255, **UNSOUND) == ANCHOR_36 - one_slot
    assert fl.rss_at_cap(fl.QWEN36, ANCHOR_36, 256, 0, **UNSOUND) == ANCHOR_36 - 256 * one_slot
    with pytest.raises(fl.FastLaneError):
        fl.rss_at_cap(fl.QWEN36, ANCHOR_36, 256, 300, **UNSOUND)
    # ROUND 382: without the opt-in the SAME call refuses.
    with pytest.raises(fl.UnsoundAnchorError, match="short by"):
        fl.rss_at_cap(fl.QWEN36, ANCHOR_36, 256, 256)


def test_rss_at_cap_refuses_an_anchor_too_small_to_hold_its_own_cache():
    """ROUND 376. RSS_FULL was labelled "qwen36 worker, cap 256, measured" and
    used as an anchor for 250+ rounds. At the corrected int8 slot size it is
    2.2 GB SMALLER than the cache it claims to contain, so `rss_at_cap(..., 0)`
    went negative and `cap_for_free_bytes` read that as slack: asked for a cap
    that frees literally all of RAM it answered 7 instead of -1."""
    with pytest.raises(fl.FastLaneError, match="not full residency"):
        fl.rss_at_cap(fl.QWEN36, RSS_FULL, 256, 0)
    with pytest.raises(fl.FastLaneError):
        fl.cap_for_free_bytes(fl.QWEN36, RSS_FULL, 256, int(31.23 * fl.GIB), 0,
                              int(1.2 * fl.GB))


def test_anchor_implied_dense_flags_every_qwen36_anchor():
    """Both anchors imply far less non-expert weight than the engine's own
    journal reports ("RSS after load: 9.25 GB"), which is the signature of a
    mid-fill snapshot."""
    assert fl.anchor_implied_dense(fl.QWEN36, ANCHOR_36, 256) < fl.QWEN36.dense_bytes
    assert fl.anchor_implied_dense(fl.QWEN36, RSS_FULL, 256) < 0
    # a sound anchor would be baseline + full cache; check the helper is not
    # simply always negative
    from nuc import expert_cache as ec
    sound = ec.QWEN36_SLOT.terminal_bytes(256)
    assert fl.anchor_implied_dense(fl.QWEN36, sound, 256) >= fl.QWEN36.dense_bytes


def test_qwen36_kv_and_deltanet_constants_derive_from_the_engine_source():
    """ROUND 382 -- the sweep round 376's next-steps item 5 asked for.

    `expert_bytes` was the only field round 376 re-derived. The other two size
    constants in `QWEN36` were bare literals with their derivation in a
    comment, which is the exact provenance grade the wrong one had. Both were
    checked against `/work/src/colibri-v170/c/qwen36.c` (read-only) this round:

      `ensure_kv()`   K[i] = falloc(kv_heads * max_t * k_head_dim), same for
                      V, for each `is_attn[i]`, and `is_attn[i] = (i%4==3)`
                      over 40 layers -> 10. `falloc` = malloc(n*sizeof(float)).
      allocation      DN_rec[i]  = calloc(dn_vheads*dn_kdim*dn_vdim, f32)
                      DN_conv[i] = calloc(dn_conv_dim*(dn_convk-1), f32)
                      for each non-attention layer -> 30.

    Verdict: KV was CORRECT at 40,960; the DeltaNet figure was round 28's
    rounded "65.9 MB" against an exact 65,863,680.
    """
    assert fl.QWEN36.kv_bytes_per_token == 40_960 == (
        10                       # is_attn[i] = (i % 4 == 3), 40 layers
        * 2                      # K and V
        * 2                      # kv_heads
        * 256                    # k_head_dim (V is sized from k_head_dim too)
        * 4)                     # falloc -> sizeof(float)
    assert fl.QWEN36.fixed_bytes == 65_863_680 == 30 * (
        32 * 128 * 128 * 4       # DN_rec: dn_vheads * dn_kdim * dn_vdim
        + 8192 * (4 - 1) * 4)    # DN_conv: dn_conv_dim * (dn_convk - 1)
    # round 28's rounded value, and how far off it was
    assert 65_900_000 - fl.QWEN36.fixed_bytes == 36_320


def test_fast_lane_and_expert_cache_agree_on_the_slot():
    """ROUND 382. Round 376 fixed `expert_bytes`' VALUE and left its PROVENANCE
    unchanged -- two magic numbers, which is precisely the grade that let the
    wrong value survive 250 rounds. It is now derived from raw dimensions and
    tied to `expert_cache.SlotGeometry`, the module round 376 wrote to hold
    exactly this derivation and then never wired back."""
    from nuc import expert_cache as ec
    assert fl.QWEN36.expert_bytes == ec.QWEN36_SLOT.slot_bytes == 3_342_336
    assert fl.QWEN36_SLOT_WEIGHT_BYTES == ec.QWEN36_SLOT.weight_bytes
    assert fl.QWEN36_SLOT_SCALE_BYTES == ec.QWEN36_SLOT.scale_bytes
    # and the on-disk figure it was confused with is still 1.889x smaller
    assert fl.QWEN36.expert_bytes / ec.QWEN36_SLOT.packed_disk_bytes == pytest.approx(17 / 9)


def test_the_exact_deltanet_figure_was_already_in_this_repo():
    """ROUND 382, and the reason the sweep was worth running.

    `nuc/kv_reuse_model.py` (round 28) derives the SAME physical quantity from
    the same dimensions and gets it exactly right; `nuc/fast_lane.py` (round
    ~30 onward) carried a rounded restatement of it. Two modules, one constant,
    no cross-check between them for ~350 rounds -- so the repo already held the
    correct value while the planner used an approximation of it. The defect is
    not the 36,320 B; it is that nothing would have noticed a larger gap.

    `kv_reuse_model` also derives `conv_dim` (2*kheads*kdim + vheads*vdim =
    8192) rather than taking it from the banner, so this is a real second
    derivation and not a copied literal.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import kv_reuse_model as krm

    assert krm.kv_bytes_per_token() == fl.QWEN36.kv_bytes_per_token
    assert krm.dn_snapshot_bytes() == fl.QWEN36.fixed_bytes
    # the independent conv_dim derivation agrees with the engine banner
    g = krm.QWEN36
    assert 2 * g["dn_kheads"] * g["dn_kdim"] + g["dn_vheads"] * g["dn_vdim"] == 8192


def test_attention_score_rows_are_context_proportional_state_the_kv_constant_omits():
    """ROUND 382. `ensure_kv` allocates `attn_sc = falloc(attn_sc_thr * max_t)`
    beside K and V, and the C comment says it "grows with the context exactly
    like the KV cache does". `kv_bytes_per_token` does not include it, and
    could not: the size depends on `omp_get_max_threads()`, a property of the
    box rather than the model. Small on pgain-nuc (nproc 4, OMP_NUM_THREADS
    unset -> 16 B/token, 0.039 %), which is why it stays a separate function
    instead of being folded into the constant and silently wrong elsewhere."""
    assert fl.attn_score_bytes_per_token(4) == 16
    assert fl.attn_score_bytes_per_token(64) == 256
    frac = fl.attn_score_bytes_per_token(4) / fl.QWEN36.kv_bytes_per_token
    assert frac < 0.0005
    # it is NOT negligible at every plausible thread count -- the point of
    # keeping it visible
    assert fl.attn_score_bytes_per_token(256) / fl.QWEN36.kv_bytes_per_token > 0.02
    with pytest.raises(fl.FastLaneError):
        fl.attn_score_bytes_per_token(0)


def test_anchor_soundness_grades_the_three_cases():
    """ROUND 382. Round 376 enforced `implied_dense >= 0` in the arithmetic and
    checked `implied_dense >= dense_bytes` only in `_plan_table`'s printed
    warning. They are the same predicate at two thresholds; `anchor_soundness`
    is the one place that grades it."""
    from nuc import expert_cache as ec
    impossible = fl.anchor_soundness(fl.QWEN36, RSS_FULL, 256)
    assert impossible["grade"] == "impossible"
    assert impossible["implied_dense_bytes"] < 0

    unsound = fl.anchor_soundness(fl.QWEN36, ANCHOR_36, 256)
    assert unsound["grade"] == "unsound" and not unsound["sound"]
    assert 0 <= unsound["implied_dense_bytes"] < fl.QWEN36.dense_bytes
    assert unsound["shortfall_bytes"] == pytest.approx(7.05e9, rel=0.01)

    sound = fl.anchor_soundness(fl.QWEN36, ec.QWEN36_SLOT.terminal_bytes(256), 256)
    assert sound["grade"] == "sound" and sound["sound"]
    assert sound["shortfall_bytes"] == 0


def test_the_opt_in_never_opens_the_impossible_grade():
    """`allow_unsound_anchor` permits "arithmetically coherent but mid-fill".
    It must NOT permit an anchor smaller than its own cache -- that produces a
    negative RSS, which is what round 376's guard existed to stop and what
    made `cap_for_free_bytes` answer 7 where -1 was owed. One flag, two
    grades, and only one of them is openable."""
    with pytest.raises(fl.UnsoundAnchorError, match="not full residency"):
        fl.rss_at_cap(fl.QWEN36, RSS_FULL, 256, 0, allow_unsound_anchor=True)
    # ...and the round-376 behaviour is unchanged without the flag, too
    with pytest.raises(fl.UnsoundAnchorError, match="not full residency"):
        fl.rss_at_cap(fl.QWEN36, RSS_FULL, 256, 0)


def test_a_cap_159_anchor_is_sound_which_is_why_this_planner_is_refused_not_deleted():
    """ROUND 382 -- the load-bearing argument for keeping the relative planner.

    Round 376 asked whether a model with no sound anchor should answer at all.
    "No sound anchor exists" is true of qwen36 *at cap 256* and is a property
    of the CAP, not of the model: cap-256 residency is 44.00 GB against a
    32.21 GB `memory.max`, so it can never be observed. At the round-376
    recommendation of cap 159 the terminal footprint is 31.03 GB, which fits,
    is observable, and yields a SOUND anchor. So the arithmetic is not dead
    code -- it is code waiting on an operator action this track has been
    asking for since round 376.

    The cross-check is the real content: a sound anchor's implied dense weight
    must reproduce `expert_cache`'s independently-measured zero-slot baseline.
    Two models, one shared constant, no circularity in that step.
    """
    from nuc import expert_cache as ec
    cap_full = 159
    anchor = ec.QWEN36_SLOT.terminal_bytes(cap_full)
    assert anchor <= ec.NUC_MEMORY_MAX

    v = fl.anchor_soundness(fl.QWEN36, anchor, cap_full)
    assert v["grade"] == "sound"
    # implied dense == expert_cache's measured zero-slot baseline, exactly
    assert v["implied_dense_bytes"] == ec.NUC_BASELINE

    # and the planner answers, with no opt-in anywhere
    ram, reserve = int(31.234 * fl.GIB), int(1.2 * fl.GB)
    rows = fl.plan_rows(fl.QWEN36, fl.OLMOE, anchor, cap_full, ram, reserve,
                        (0,), 2048, 1500.0, 0.0)
    assert rows[0][2] == cap_full          # nothing to give back: it already fits
    assert fl.rss_at_cap(fl.QWEN36, anchor, cap_full, cap_full) == anchor


def test_plan_rows_refuses_instead_of_warning_one_layer_up():
    """ROUND 382, the defect this round fixed. Round 376's warning lived in
    `_plan_table`; `plan_rows` is the library entry point and never saw it, so
    any caller that was not the CLI got 225 with nothing said."""
    ram, reserve = int(31.234 * fl.GIB), int(1.2 * fl.GB)
    with pytest.raises(fl.UnsoundAnchorError, match="short by"):
        fl.plan_rows(fl.QWEN36, fl.OLMOE, ANCHOR_36, 256, ram, reserve,
                     (0, 16), 2048, 1500.0, 0.0)
    with pytest.raises(fl.UnsoundAnchorError, match="short by"):
        fl.cap_cost(fl.QWEN36, ANCHOR_36, 256, 128, topk=8, nvme_mb_s=1500)
    # the opt-in still reproduces the wrong answer, on purpose
    rows = fl.plan_rows(fl.QWEN36, fl.OLMOE, ANCHOR_36, 256, ram, reserve,
                        (0,), 2048, 1500.0, 0.0, **UNSOUND)
    assert rows[0][2] == 225


def test_cap_for_free_bytes_prediction_p5():
    ram = int(31.23 * fl.GIB)
    reserve = int(1.2 * fl.GB)
    # ROUND 376: these bounds moved. With the corrected int8 slot size a given
    # cap reduction frees 1.889x more, so this RELATIVE planner now returns a
    # HIGHER cap for the same lane -- cap-64 went 130 -> 190. That is the wrong
    # direction, and it is not a regression in the arithmetic: it is the
    # anchor. `rss_at_cap` subtracts from `RSS_FULL`, an alleged cap-256
    # residency that was really a ~77 %-full cache pinned against the cgroup
    # wall, so the model starts ~12 GB below the true cap-256 footprint and a
    # bigger slope only walks it further off. See
    # test_relative_planner_disagrees_with_the_absolute_model.
    need64 = fl.OLMOE.footprint(64, ctx=2048, workspace_bytes=int(0.3 * fl.GB))
    cap64 = fl.cap_for_free_bytes(fl.QWEN36, ANCHOR_36, 256, ram, need64, reserve, **UNSOUND)
    assert 150 <= cap64 <= 175
    # cap-16 lane (~2.3 GB)
    need16 = fl.OLMOE.footprint(16, ctx=1024, workspace_bytes=int(0.3 * fl.GB))
    cap16 = fl.cap_for_free_bytes(fl.QWEN36, ANCHOR_36, 256, ram, need16, reserve, **UNSOUND)
    assert cap16 > cap64
    # the freed bytes really cover the need
    freed = ANCHOR_36 - fl.rss_at_cap(fl.QWEN36, ANCHOR_36, 256, cap64, **UNSOUND)
    assert freed >= need64 - (ram - reserve - ANCHOR_36)
    # impossible when the lane wants more than everything
    assert fl.cap_for_free_bytes(fl.QWEN36, ANCHOR_36, 256, ram, ram, reserve, **UNSOUND) == -1


def test_cap_cost_monotone_and_zero_at_full():
    full = fl.cap_cost(fl.QWEN36, ANCHOR_36, 256, 256, topk=8, nvme_mb_s=1500, **UNSOUND)
    assert full.miss_fraction == 0 and full.decode_penalty_s_per_token == 0
    assert full.prefill_penalty_s_per_request == 0
    half = fl.cap_cost(fl.QWEN36, ANCHOR_36, 256, 128, topk=8, nvme_mb_s=1500, **UNSOUND)
    assert half.miss_fraction == pytest.approx(0.5)
    # ROUND 376: the streamed bytes are the int8 SLOT, not the int4 tensor on
    # disk -- a miss has to fill `slot_ensure_allocated`'s block. Both penalties
    # rise by the 1.889x unpack ratio. (A disk read moves the packed bytes; the
    # engine then spends CPU unpacking them. The old figures modelled neither
    # cost correctly, and this is the conservative of the two.)
    # 0.5 x 8 x 40 x 3.342 MB / 1500 MB/s ≈ 0.357 s per token
    assert half.decode_penalty_s_per_token == pytest.approx(0.3565, rel=0.01)
    assert half.decode_penalty_s_per_token == pytest.approx(0.1887 * 17 / 9, rel=0.01)
    # 128 missing x 40 x 3.342 MB / 1500 MB/s ≈ 11.4 s per request
    assert half.prefill_penalty_s_per_request == pytest.approx(11.41, rel=0.01)
    skewed = fl.cap_cost(fl.QWEN36, ANCHOR_36, 256, 128, topk=8, nvme_mb_s=1500, skew=0.5,
                         **UNSOUND)
    assert skewed.miss_fraction == pytest.approx(0.25)
    assert skewed.decode_penalty_s_per_token < half.decode_penalty_s_per_token


def test_expected_miss_fraction_bounds():
    assert fl.expected_miss_fraction(0, 256) == 1.0
    assert fl.expected_miss_fraction(256, 256) == 0.0
    assert fl.expected_miss_fraction(64, 256, skew=1.0) == 0.0
    with pytest.raises(fl.FastLaneError):
        fl.expected_miss_fraction(300, 256)


# ----------------------------------------------------------------- lane projection

def test_qwen36_curve_matches_e1_points():
    # E1: 134 tok → 23.3 s cold, 904 → 143.1 s, 3998 → 770.3 s; 8k extrapolated ≈ 1551
    assert fl.qwen36_prefill_s(0) == pytest.approx(2.4)
    assert fl.qwen36_prefill_s(134) == pytest.approx(23.3)
    assert fl.qwen36_prefill_s(904) == pytest.approx(143.1)
    assert fl.qwen36_prefill_s(3998) == pytest.approx(770.3)
    assert fl.qwen36_prefill_s(600) == pytest.approx(23.3 + (143.1 - 23.3) * 466 / 770)
    assert fl.qwen36_prefill_s(8000) == pytest.approx(1551, rel=0.03)
    with pytest.raises(fl.FastLaneError):
        fl.qwen36_prefill_s(-1)


def test_lane_turn_and_speedup():
    lane = fl.lane_turn(600, 150, prefill_tps=30, decode_tps=6)
    assert lane.prefill_s == pytest.approx(20.5) and lane.decode_s == pytest.approx(25.0)
    big = fl.qwen36_turn(600, 150)
    assert big.total_s > lane.total_s
    with pytest.raises(fl.FastLaneError):
        fl.lane_turn(600, 150, 0, 6)


# ----------------------------------------------------------------- transfer + sink

def test_transfer_cmd_shape():
    cmd = fl.transfer_cmd("/tmp/a b.bin", "jab@192.168.1.37", "~/nuc-research/models/x.st",
                          ssh_key="~/.ssh/k")
    assert cmd.startswith("cat '/tmp/a b.bin' | ssh -i ~/.ssh/k jab@192.168.1.37 ")
    assert "fast_lane_sink.py" in cmd and "--sync-every-mb 256" in cmd


def test_sink_round_trip_md5_and_rename(tmp_path):
    payload = os.urandom(3_000_000 + 12345)
    out = tmp_path / "sub" / "blob.bin"
    res = sink.sink(io.BytesIO(payload), str(out), chunk_bytes=1_000_000, sync_every=1_000_000)
    assert out.read_bytes() == payload
    assert not (tmp_path / "sub" / "blob.bin.part").exists()
    assert res["bytes"] == len(payload)
    assert res["md5"] == hashlib.md5(payload).hexdigest()


def test_sink_cli_prints_json(tmp_path):
    payload = b"x" * 2_500_000
    out = tmp_path / "cli.bin"
    proc = subprocess.run([sys.executable, str(ROOT / "fast_lane_sink.py"), "--out", str(out),
                           "--chunk-mb", "1", "--sync-every-mb", "1", "--quiet"],
                          input=payload, capture_output=True, check=True)
    info = json.loads(proc.stdout.decode().strip().splitlines()[-1])
    assert info["bytes"] == len(payload) and out.stat().st_size == len(payload)


# ----------------------------------------------------------------- CLI

def test_full_footprint_and_plan_rows_use_resident_plus_swap():
    resident, swapped = 32_211_791_872, 4_214_800_384
    full = fl.full_footprint(resident, swapped)
    assert full == resident + swapped
    ram, reserve = int(31.234 * fl.GIB), int(1.2 * fl.GB)
    rows = fl.plan_rows(fl.QWEN36, fl.OLMOE, full, 256, ram, reserve, (0, 16, 64), 2048, 1500.0,
                        0.0, **UNSOUND)
    caps = {lane: cap for lane, _, cap, _ in rows}
    # ROUND 376: was 180..205, now 225, for the anchor reason documented in
    # test_cap_for_free_bytes_prediction_p5.
    assert 215 <= caps[0] <= 235
    # lanes take slots on top of that, monotonically
    assert caps[0] > caps[16] > caps[64] >= 0
    # The RSS-only planner ignores the swap the box was already doing. That used
    # to show up as "it returns a cap ~40 higher"; round 376 makes it sharper --
    # resident-only (32.21 GB) cannot even hold a cap-256 cache (34.23 GB), so
    # the anchor is now rejected outright rather than quietly over-allocating.
    with pytest.raises(fl.FastLaneError, match="not full residency"):
        fl.cap_for_free_bytes(fl.QWEN36, resident, 256, ram,
                              fl.OLMOE.footprint(64, 2048, workspace_bytes=int(0.3 * fl.GB)),
                              reserve, **UNSOUND)


def test_relative_planner_disagrees_with_the_absolute_model():
    """ROUND 376. `plan_rows`' "no lane" cap and `expert_cache`'s `max_cap` are
    answers to the same question -- what cap fits this box -- and they differ by
    58 slots (225 vs 167). They are NOT both usable.

    `max_cap` is absolute: baseline (a measured zero-slot `memory.current`) plus
    cap x layers x slot_bytes, compared to `memory.max`. It needs no anchor and
    every input is a live reading or a source constant.

    `plan_rows` is relative: it subtracts freed slots from an `rss_full` the
    caller asserts is cap-256 residency. No such reading exists for this engine
    -- cap-256 residency is 44.0 GB, ~12 GB past the cgroup cap, so it can never
    be observed. Every anchor ever passed here was a mid-fill snapshot, which
    makes the relative planner optimistic by construction.

    This test exists to keep that gap visible rather than to bless either
    number: if a later round re-anchors `plan_rows`, this should start failing
    and be re-derived, not deleted."""
    from nuc import expert_cache as ec
    resident, swapped = 32_211_791_872, 4_214_800_384
    ram, reserve = int(31.234 * fl.GIB), int(1.2 * fl.GB)
    rows = fl.plan_rows(fl.QWEN36, fl.OLMOE, fl.full_footprint(resident, swapped),
                        256, ram, reserve, (0,), 2048, 1500.0, 0.0, **UNSOUND)
    relative_cap = rows[0][2]
    absolute_cap = ec.QWEN36_SLOT.max_cap()
    assert absolute_cap == 167
    assert relative_cap > absolute_cap
    # the relative planner's answer does NOT fit; the absolute one's does
    assert ec.QWEN36_SLOT.terminal_bytes(relative_cap) > ec.NUC_MEMORY_MAX
    assert ec.QWEN36_SLOT.terminal_bytes(absolute_cap) <= ec.NUC_MEMORY_MAX


def test_cli_plan_and_turn_and_gate(tmp_path, capsys):
    """ROUND 382: `plan` with its DEFAULT arguments now refuses and exits 2.
    The defaults are the unsound 2026-08-24 anchor, so the default invocation
    is precisely the one that must not answer. The table is asserted below
    from a sound anchor instead, which keeps the formatting covered."""
    assert fl.main(["plan"]) == 2
    refusal = capsys.readouterr().out
    assert refusal.startswith("# REFUSED (round 382)")
    assert "expert_cache.py plan" in refusal and "short by 7.05 GB" in refusal

    # A sound anchor -- what a `--cap 159` restart would actually read back --
    # and the table comes out normally.
    assert fl.main(["plan", "--cap-full", "159",
                    "--resident-gb", "31.028", "--swapped-gb", "0"]) == 0
    table = capsys.readouterr().out
    assert "| 64 |" in table and "| 16 |" in table and "qwen36 cap" in table
    assert "none (stop swapping)" in table and "resident 31.03" in table
    assert fl.main(["turn", "--prompt", "600", "--reply", "150"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["speedup"] > 1
    log = tmp_path / "probe.log"
    log.write_text(PROBE_LOG)
    assert fl.main(["parse", str(log)]) == 0
    assert "spread=" in capsys.readouterr().out
    assert fl.main(["gate", "--min-rate", "8.66", "--disk-free-gb", "677",
                    "--disk-needed-gb", "21.3"]) == 0
    assert fl.main(["gate", "--min-rate", "2", "--disk-free-gb", "677",
                    "--disk-needed-gb", "21.3"]) == 2


# ---------------------------------------------------------------- round 106: resume + handoff

def test_sink_resume_appends_and_reports_offsets(tmp_path):
    payload = os.urandom(2_500_000)
    out = tmp_path / "blob.bin"
    part = tmp_path / "blob.bin.part"
    part.write_bytes(payload[:1_000_000])                      # a transfer that died
    res = sink.sink(io.BytesIO(payload[1_000_000:]), str(out), chunk_bytes=300_000,
                    sync_every=500_000, resume=True)
    assert out.read_bytes() == payload and not part.exists()
    assert res["start"] == 1_000_000 and res["appended"] == 1_500_000 and res["bytes"] == 2_500_000
    assert res["md5"] == hashlib.md5(payload[1_000_000:]).hexdigest() and res["md5_covers"] == "appended"
    fresh = sink.sink(io.BytesIO(payload), str(tmp_path / "b2.bin"), 300_000, 500_000)
    assert fresh["start"] == 0 and fresh["md5_covers"] == "file"


def test_sink_without_resume_truncates_a_stale_part(tmp_path):
    out = tmp_path / "x.bin"
    (tmp_path / "x.bin.part").write_bytes(b"stale")
    sink.sink(io.BytesIO(b"fresh"), str(out), 1_000, 1_000)
    assert out.read_bytes() == b"fresh"


def test_sink_cli_part_size_and_resume_flag(tmp_path):
    out = tmp_path / "y.bin"
    (tmp_path / "y.bin.part").write_bytes(b"abc")
    r = subprocess.run([sys.executable, sink.__file__, "--out", str(out), "--part-size"],
                       capture_output=True, text=True)
    assert r.stdout.strip() == "3"
    r = subprocess.run([sys.executable, sink.__file__, "--out", str(out), "--resume", "--quiet"],
                       input=b"def", capture_output=True)
    d = json.loads(r.stdout)
    assert out.read_bytes() == b"abcdef" and d["start"] == 3 and d["appended"] == 3
    r = subprocess.run([sys.executable, sink.__file__, "--out", str(tmp_path / "none.bin"), "--part-size"],
                       capture_output=True, text=True)
    assert r.stdout.strip() == "0"


FILES = [("model-00000.safetensors", 400), ("model-00001.safetensors", 400), ("config.json", 50)]


def test_transfer_plan_skip_resume_send():
    have = {"model-00000.safetensors": 400, "model-00001.safetensors": 150}
    plan = fl.transfer_plan(FILES, have, "/loc/dir", "jab@box", "~/models/olmoe", ssh_key="~/.ssh/k")
    by = {p.relpath: p for p in plan}
    assert by["model-00000.safetensors"].action == "skip" and by["model-00000.safetensors"].command == ""
    r = by["model-00001.safetensors"]
    assert r.action == "resume" and r.command.startswith("tail -c +151 /loc/dir/model-00001.safetensors | ssh -i ~/.ssh/k jab@box ")
    assert "--resume" in r.command and '--out "$HOME"/models/olmoe/model-00001.safetensors' in r.command
    assert "'~" not in r.command                                   # tilde must expand on the box
    s = by["config.json"]
    assert s.action == "send" and s.command.startswith("cat /loc/dir/config.json | ") and "--resume" not in s.command


def test_handoff_script_guards_and_verifies(tmp_path):
    d = tmp_path / "snap"
    d.mkdir()
    (d / "a.safetensors").write_bytes(b"x" * 100)
    (d / "config.json").write_bytes(b"{}")
    (d / ".hidden").write_bytes(b"no")
    files = fl.list_container(str(d))
    assert files == [("a.safetensors", 100), ("config.json", 2)]
    md5s = fl.md5_of_files(str(d), files)
    assert md5s["config.json"] == hashlib.md5(b"{}").hexdigest()
    script = fl.handoff_script(files, {"a.safetensors": 40}, str(d), "jab@box", "~/m", md5s, ssh_key="k")
    lines = script.splitlines()
    assert lines[0] == "#!/bin/sh" and "set -e" in lines
    assert any("HOST_OK" in l and "exit 2" in l for l in lines)          # host guard before any copy
    assert any(l.startswith("tail -c +41 ") for l in lines)             # resume offset = have + 1
    assert any(l.startswith("cat ") and "config.json" in l for l in lines)
    assert sum("md5sum" in l for l in lines) == 2 and "exit 3" in script
    assert "nuc-fast-lane.md" in script and lines[-1] == "echo HANDOFF_OK"
    assert "8001" not in script
    assert "1 resume / 1 send" in script
    assert "'~" not in script and '"$HOME"/m' in script
    assert "test \"$(md5sum \"$HOME\"/m/config.json | cut -d\" \" -f1)\" = " in script


def test_remote_quote_tilde_and_spaces():
    assert fl.remote_quote("~/a b/c") == '"$HOME"/\'a b/c\''
    assert fl.remote_quote("~") == '"$HOME"'
    assert fl.remote_quote("/work/logs/x") == "/work/logs/x"


def test_handoff_refuses_frontier_port_anywhere():
    with pytest.raises(fl.FastLaneError):
        fl.handoff_script([("a", 1)], {}, "/d", "jab@box", "~/m", {}, log_path="/work/logs/x:8001")


def test_cli_handoff_reads_remote_sizes(tmp_path, capsys):
    d = tmp_path / "snap"
    d.mkdir()
    (d / "b.safetensors").write_bytes(b"y" * 10)
    sizes = tmp_path / "sizes.json"
    sizes.write_text(json.dumps({"b.safetensors": 4}))
    assert fl.main(["handoff", str(d), "jab@box", "~/m", "--remote-sizes", str(sizes), "--md5"]) == 0
    out = capsys.readouterr().out
    assert "tail -c +5 " in out and "md5sum" in out and out.endswith("echo HANDOFF_OK\n")


def test_lane_disk_bound_decode_matches_mac_measurement():
    # lane-bench-r106 case cap=16: 205 tokens, hit=12771 miss=13341 → miss 0.511, 84.2 GB read in 166 s ≈ 507 MB/s
    miss = fl.measured_miss_fraction(12_771, 13_341)
    assert miss == pytest.approx(0.511, abs=0.002)
    assert fl.lane_disk_bound_tok_s(miss, 507) == pytest.approx(1.23, abs=0.03)
    assert fl.lane_disk_bound_tok_s(miss, 1500) == pytest.approx(3.6, abs=0.1)
    assert fl.lane_disk_bound_tok_s(0.0, 500) == math.inf
    with pytest.raises(fl.FastLaneError):
        fl.lane_disk_bound_tok_s(1.2, 500)
    with pytest.raises(fl.FastLaneError):
        fl.measured_miss_fraction(0, 0)


def test_breakeven_prompt_tokens_round_112():
    # measured Mac lane rates: the lane beats qwen36 only for long prompts with short replies
    assert 600 <= fl.breakeven_prompt_tokens(60) <= 800
    assert fl.breakeven_prompt_tokens(20) < fl.breakeven_prompt_tokens(60)     # shorter reply -> earlier win
    assert fl.breakeven_prompt_tokens(60, decode_tps=3.6) == 0                 # NVMe projection: wins everywhere
    assert fl.breakeven_prompt_tokens(60, prefill_tps=5.0) is None             # slower than qwen36 prefill: never
    with pytest.raises(fl.FastLaneError):
        fl.breakeven_prompt_tokens(-1)
