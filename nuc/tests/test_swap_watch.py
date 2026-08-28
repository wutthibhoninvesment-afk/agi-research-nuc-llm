"""Offline tests for nuc/swap_watch.py.

The real script only reads cgroup v2 accounting files and /proc/vmstat, which
don't exist on a non-NUC host, so these tests monkeypatch swap_watch's own
read_int_file/read_vmstat_counters/time.sleep to drive collect() with a fake,
scripted counter sequence instead of touching the filesystem or the clock.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import swap_watch  # noqa: E402


def fake_reader(swap_seq, mem_seq, vmstat_seq, sleeps):
    """Build monkeypatch targets from parallel per-poll sequences.

    swap_seq/mem_seq/vmstat_seq are lists, one entry per poll (indexed by
    call count); vmstat_seq entries are {"pswpin": int, "pswpout": int}.
    """
    state = {"i": 0}

    def read_int_file(path):
        i = state["i"]
        if "swap" in path:
            return swap_seq[i]
        return mem_seq[i]

    def read_vmstat_counters(path=None):
        return vmstat_seq[state["i"]]

    def fake_sleep(_s):
        state["i"] += 1
        sleeps.append(_s)

    return state, read_int_file, read_vmstat_counters, fake_sleep


def test_collect_polls_duration_over_interval(monkeypatch):
    """duration_s=45, interval_s=15 -> polls at t=0,15,30,45 (4 samples)."""
    n = 4
    swap_seq = [1000 + 10 * i for i in range(n)]
    mem_seq = [5000] * n
    vmstat_seq = [{"pswpin": 1, "pswpout": 100 + i} for i in range(n)]
    sleeps = []
    state, rif, rvc, fsleep = fake_reader(swap_seq, mem_seq, vmstat_seq, sleeps)
    monkeypatch.setattr(swap_watch, "read_int_file", rif)
    monkeypatch.setattr(swap_watch, "read_vmstat_counters", rvc)
    monkeypatch.setattr(swap_watch.time, "sleep", fsleep)

    # first value is consumed by collect()'s own `t_start = time.time()` call,
    # before the polling loop's per-sample `now = time.time()` calls begin
    times = iter([0.0, 0.0, 15.0, 30.0, 45.0, 999.0])
    monkeypatch.setattr(swap_watch.time, "time", lambda: next(times))

    samples = swap_watch.collect("unit", "slice", 15.0, 45.0)
    assert [s.swap_bytes for s in samples] == swap_seq
    assert len(samples) == n
    assert sleeps == [15.0, 15.0, 15.0]


def test_checkpoint_writes_one_json_line_per_sample(tmp_path, monkeypatch):
    n = 3
    swap_seq = [500, 600, 700]
    mem_seq = [9000, 9000, 9000]
    vmstat_seq = [{"pswpin": 0, "pswpout": 10 * i} for i in range(n)]
    sleeps = []
    state, rif, rvc, fsleep = fake_reader(swap_seq, mem_seq, vmstat_seq, sleeps)
    monkeypatch.setattr(swap_watch, "read_int_file", rif)
    monkeypatch.setattr(swap_watch, "read_vmstat_counters", rvc)
    monkeypatch.setattr(swap_watch.time, "sleep", fsleep)
    times = iter([0.0, 0.0, 10.0, 20.0, 999.0])
    monkeypatch.setattr(swap_watch.time, "time", lambda: next(times))

    ckpt = tmp_path / "checkpoint.jsonl"
    samples = swap_watch.collect("unit", "slice", 10.0, 20.0, checkpoint_path=str(ckpt))

    assert len(samples) == 3
    lines = ckpt.read_text().splitlines()
    assert len(lines) == 3
    parsed = [json.loads(l) for l in lines]
    assert [p["swap_bytes"] for p in parsed] == swap_seq
    # checkpoint content matches the in-memory samples exactly
    for p, s in zip(parsed, samples):
        assert p == {
            "seq": s.seq, "t_unix": s.t_unix, "swap_bytes": s.swap_bytes,
            "mem_current_bytes": s.mem_current_bytes,
            "pswpin_pages": s.pswpin_pages, "pswpout_pages": s.pswpout_pages,
        }


def test_checkpoint_survives_interruption_partial_data(tmp_path, monkeypatch):
    """Simulate a crash after 2 of 5 planned samples: the checkpoint file
    must contain exactly the samples collected before the interruption,
    since that's the whole point of --checkpoint (recovering partial data
    from a multi-hour run that never reaches its own final --out write)."""
    n = 5
    swap_seq = [100, 200, 300, 400, 500]
    mem_seq = [1] * n
    vmstat_seq = [{"pswpin": 0, "pswpout": 0} for _ in range(n)]
    sleeps = []
    state, rif, rvc, fsleep = fake_reader(swap_seq, mem_seq, vmstat_seq, sleeps)
    monkeypatch.setattr(swap_watch, "read_int_file", rif)
    monkeypatch.setattr(swap_watch, "read_vmstat_counters", rvc)

    call_count = {"n": 0}

    def crashing_sleep(s):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise KeyboardInterrupt("simulated interruption")
        fsleep(s)

    monkeypatch.setattr(swap_watch.time, "sleep", crashing_sleep)
    times = iter([0.0] + [float(i) for i in range(1, 10)])
    monkeypatch.setattr(swap_watch.time, "time", lambda: next(times))

    ckpt = tmp_path / "checkpoint.jsonl"
    with pytest.raises(KeyboardInterrupt):
        swap_watch.collect("unit", "slice", 1.0, 100.0, checkpoint_path=str(ckpt))

    lines = ckpt.read_text().splitlines()
    # 2 samples were collected before the sleep that raises on its 2nd call
    assert len(lines) == 2
    parsed = [json.loads(l) for l in lines]
    assert [p["swap_bytes"] for p in parsed] == [100, 200]


def test_find_bursts_groups_consecutive_growth():
    samples = [
        swap_watch.Sample(0, 0.0, 1000, 0, 0, 0),
        swap_watch.Sample(1, 15.0, 1000, 0, 0, 0),   # flat
        swap_watch.Sample(2, 30.0, 3_000_000, 0, 0, 0),  # burst start
        swap_watch.Sample(3, 45.0, 5_000_000, 0, 0, 0),  # burst continues
        swap_watch.Sample(4, 60.0, 5_000_000, 0, 0, 0),  # flat again
    ]
    bursts = swap_watch.find_bursts(samples, threshold_bytes=1024 * 1024)
    assert len(bursts) == 1
    b = bursts[0]
    assert b.start_seq == 1 and b.end_seq == 3
    assert b.delta_bytes == 5_000_000 - 1000
    assert b.duration_s == 30.0


def test_find_bursts_none_when_flat():
    samples = [swap_watch.Sample(i, float(i), 1000, 0, 0, 0) for i in range(5)]
    assert swap_watch.find_bursts(samples, threshold_bytes=1024) == []


def test_summarize_matches_wide_window_arithmetic():
    samples = [
        swap_watch.Sample(0, 0.0, 1_000_000, 0, 0, 0),
        swap_watch.Sample(1, 3600.0, 1_050_000, 0, 0, 0),
    ]
    bursts = swap_watch.find_bursts(samples, threshold_bytes=1024 * 1024)
    summary = swap_watch.summarize(samples, bursts)
    assert summary["n_samples"] == 2
    assert summary["total_delta_bytes"] == 50_000
    assert summary["span_s"] == 3600.0
    assert summary["wide_window_rate_mb_per_hr"] == pytest.approx(0.05, rel=1e-6)
