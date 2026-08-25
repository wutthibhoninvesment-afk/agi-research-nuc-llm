"""Offline tests for nuc/fast_lane.py and nuc/fast_lane_sink.py."""
import hashlib
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
        fl.check_url("http://192.168.1.42:8001/")


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


def test_qwen36_geometry_matches_container_header():
    # 20,480 expert tensors x 2 kinds → 18.119 GB on disk at 1,769,472 B/expert
    assert fl.QWEN36.cache_bytes(256) == pytest.approx(18.119e9, rel=0.002)
    assert fl.QWEN36.expert_bytes == 1_769_472


def test_olmoe_footprint_anchors_on_upstream_comment():
    # chat_olmoe.sh: "~6GB cache + ~1.8GB dense =~ 7.8GB peak" at cap 64
    fp = fl.OLMOE.footprint(64, ctx=0)
    assert 7.6e9 < fp < 8.3e9
    # M3 bench row: cap 16 → RSS 1.5–1.81 GB (dense estimate dominates; ours is the upper bound)
    assert fl.OLMOE.cache_bytes(16) == pytest.approx(1.61e9, rel=0.01)
    assert fl.OLMOE.kv_bytes_per_token * 4096 == pytest.approx(1.074e9, rel=0.001)


def test_rss_at_cap_is_linear_and_bounded():
    assert fl.rss_at_cap(fl.QWEN36, RSS_FULL, 256, 256) == RSS_FULL
    one_slot = fl.QWEN36.layers * fl.QWEN36.expert_bytes
    assert fl.rss_at_cap(fl.QWEN36, RSS_FULL, 256, 255) == RSS_FULL - one_slot
    assert fl.rss_at_cap(fl.QWEN36, RSS_FULL, 256, 0) == RSS_FULL - 256 * one_slot
    with pytest.raises(fl.FastLaneError):
        fl.rss_at_cap(fl.QWEN36, RSS_FULL, 256, 300)


def test_cap_for_free_bytes_prediction_p5():
    ram = int(31.23 * fl.GIB)
    reserve = int(1.2 * fl.GB)
    # cap-64 lane (~8.5 GB incl. KV/workspace) → P5 said cap ≈ 130 (115–145)
    need64 = fl.OLMOE.footprint(64, ctx=2048, workspace_bytes=int(0.3 * fl.GB))
    cap64 = fl.cap_for_free_bytes(fl.QWEN36, RSS_FULL, 256, ram, need64, reserve)
    assert 100 <= cap64 <= 150
    # cap-16 lane (~2.3 GB) → P5 said ≈ 220 (210–230)
    need16 = fl.OLMOE.footprint(16, ctx=1024, workspace_bytes=int(0.3 * fl.GB))
    cap16 = fl.cap_for_free_bytes(fl.QWEN36, RSS_FULL, 256, ram, need16, reserve)
    assert cap16 > cap64
    # the freed bytes really cover the need
    freed = RSS_FULL - fl.rss_at_cap(fl.QWEN36, RSS_FULL, 256, cap64)
    assert freed >= need64 - (ram - reserve - RSS_FULL)
    # impossible when the lane wants more than everything
    assert fl.cap_for_free_bytes(fl.QWEN36, RSS_FULL, 256, ram, ram, reserve) == -1


def test_cap_cost_monotone_and_zero_at_full():
    full = fl.cap_cost(fl.QWEN36, RSS_FULL, 256, 256, topk=8, nvme_mb_s=1500)
    assert full.miss_fraction == 0 and full.decode_penalty_s_per_token == 0
    assert full.prefill_penalty_s_per_request == 0
    half = fl.cap_cost(fl.QWEN36, RSS_FULL, 256, 128, topk=8, nvme_mb_s=1500)
    assert half.miss_fraction == pytest.approx(0.5)
    # 0.5 x 8 x 40 x 1.769 MB / 1500 MB/s ≈ 0.189 s per token
    assert half.decode_penalty_s_per_token == pytest.approx(0.1887, rel=0.01)
    # 128 missing x 40 x 1.769 MB / 1500 MB/s ≈ 6.0 s per request
    assert half.prefill_penalty_s_per_request == pytest.approx(6.04, rel=0.01)
    skewed = fl.cap_cost(fl.QWEN36, RSS_FULL, 256, 128, topk=8, nvme_mb_s=1500, skew=0.5)
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
    cmd = fl.transfer_cmd("/tmp/a b.bin", "jab@192.168.1.42", "~/nuc-research/models/x.st",
                          ssh_key="~/.ssh/k")
    assert cmd.startswith("cat '/tmp/a b.bin' | ssh -i ~/.ssh/k jab@192.168.1.42 ")
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
    # no lane: the cap that just stops the swapping (measured overshoot ≈ 4 GB → ≈ 60 slots)
    assert 180 <= caps[0] <= 205
    # lanes take slots on top of that, monotonically
    assert caps[0] > caps[16] > caps[64] >= 0
    # the RSS-only planner (P5) would have said ~130 for the cap-64 lane; the truth is far lower
    rss_only = fl.cap_for_free_bytes(fl.QWEN36, resident, 256, ram,
                                     fl.OLMOE.footprint(64, 2048, workspace_bytes=int(0.3 * fl.GB)), reserve)
    assert rss_only - caps[64] > 40


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
