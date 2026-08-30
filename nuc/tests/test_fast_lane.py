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


def test_rss_at_cap_is_linear_and_bounded():
    assert fl.rss_at_cap(fl.QWEN36, ANCHOR_36, 256, 256) == ANCHOR_36
    one_slot = fl.QWEN36.layers * fl.QWEN36.expert_bytes
    assert fl.rss_at_cap(fl.QWEN36, ANCHOR_36, 256, 255) == ANCHOR_36 - one_slot
    assert fl.rss_at_cap(fl.QWEN36, ANCHOR_36, 256, 0) == ANCHOR_36 - 256 * one_slot
    with pytest.raises(fl.FastLaneError):
        fl.rss_at_cap(fl.QWEN36, ANCHOR_36, 256, 300)


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
    cap64 = fl.cap_for_free_bytes(fl.QWEN36, ANCHOR_36, 256, ram, need64, reserve)
    assert 150 <= cap64 <= 175
    # cap-16 lane (~2.3 GB)
    need16 = fl.OLMOE.footprint(16, ctx=1024, workspace_bytes=int(0.3 * fl.GB))
    cap16 = fl.cap_for_free_bytes(fl.QWEN36, ANCHOR_36, 256, ram, need16, reserve)
    assert cap16 > cap64
    # the freed bytes really cover the need
    freed = ANCHOR_36 - fl.rss_at_cap(fl.QWEN36, ANCHOR_36, 256, cap64)
    assert freed >= need64 - (ram - reserve - ANCHOR_36)
    # impossible when the lane wants more than everything
    assert fl.cap_for_free_bytes(fl.QWEN36, ANCHOR_36, 256, ram, ram, reserve) == -1


def test_cap_cost_monotone_and_zero_at_full():
    full = fl.cap_cost(fl.QWEN36, ANCHOR_36, 256, 256, topk=8, nvme_mb_s=1500)
    assert full.miss_fraction == 0 and full.decode_penalty_s_per_token == 0
    assert full.prefill_penalty_s_per_request == 0
    half = fl.cap_cost(fl.QWEN36, ANCHOR_36, 256, 128, topk=8, nvme_mb_s=1500)
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
    skewed = fl.cap_cost(fl.QWEN36, ANCHOR_36, 256, 128, topk=8, nvme_mb_s=1500, skew=0.5)
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
    rows = fl.plan_rows(fl.QWEN36, fl.OLMOE, full, 256, ram, reserve, (0, 16, 64), 2048, 1500.0, 0.0)
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
                              reserve)


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
                        256, ram, reserve, (0,), 2048, 1500.0, 0.0)
    relative_cap = rows[0][2]
    absolute_cap = ec.QWEN36_SLOT.max_cap()
    assert absolute_cap == 167
    assert relative_cap > absolute_cap
    # the relative planner's answer does NOT fit; the absolute one's does
    assert ec.QWEN36_SLOT.terminal_bytes(relative_cap) > ec.NUC_MEMORY_MAX
    assert ec.QWEN36_SLOT.terminal_bytes(absolute_cap) <= ec.NUC_MEMORY_MAX


def test_cli_plan_and_turn_and_gate(tmp_path, capsys):
    assert fl.main(["plan"]) == 0
    table = capsys.readouterr().out
    assert "| 64 |" in table and "| 16 |" in table and "qwen36 cap" in table
    assert "none (stop swapping)" in table and "resident 32.21" in table
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
