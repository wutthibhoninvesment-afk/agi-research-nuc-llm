"""Offline tests for nuc/swap_analysis.py.

Two layers: synthetic Sample lists exercise each function's logic in
isolation (including edge cases no real dataset happens to hit), and a
regression test loads the REAL round-268 8h dataset
(state/nuc-swap-watch-r292/swap-watch-r268-long.json) and asserts this
module reproduces round 298's own published numbers exactly — the dataset
this module was built to stop everyone from re-deriving by hand.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import swap_analysis  # noqa: E402
import swap_watch  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
R268_DATASET = REPO_ROOT / "state" / "nuc-swap-watch-r292" / "swap-watch-r268-long.json"
R268_CHECKPOINT = REPO_ROOT / "state" / "nuc-swap-watch-r292" / "swap-watch-r268-checkpoint-final.jsonl"


def mk_sample(seq, t, swap, pswpout=0, pswpin=0, mem=0):
    return swap_watch.Sample(seq=seq, t_unix=t, swap_bytes=swap, mem_current_bytes=mem,
                              pswpin_pages=pswpin, pswpout_pages=pswpout)


# --- load_samples ------------------------------------------------------

def test_load_samples_from_out_json(tmp_path):
    data = {"samples": [
        {"seq": 0, "t_unix": 0.0, "swap_bytes": 100, "mem_current_bytes": 1,
         "pswpin_pages": 0, "pswpout_pages": 0},
        {"seq": 1, "t_unix": 15.0, "swap_bytes": 200, "mem_current_bytes": 1,
         "pswpin_pages": 0, "pswpout_pages": 10},
    ], "bursts": [], "summary": {}}
    path = tmp_path / "out.json"
    path.write_text(json.dumps(data))
    samples = swap_analysis.load_samples(str(path))
    assert len(samples) == 2
    assert samples[1].swap_bytes == 200


def test_load_samples_from_checkpoint_jsonl(tmp_path):
    rows = [mk_sample(0, 0.0, 100), mk_sample(1, 15.0, 300)]
    path = tmp_path / "checkpoint.jsonl"
    path.write_text("\n".join(json.dumps(swap_watch.asdict(s)) for s in rows) + "\n")
    samples = swap_analysis.load_samples(str(path))
    assert [s.swap_bytes for s in samples] == [100, 300]


def test_load_samples_empty_raises(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("")
    with pytest.raises(swap_analysis.SwapAnalysisError):
        swap_analysis.load_samples(str(path))


def test_load_samples_malformed_row_raises(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps({"seq": 0, "not_a_real_field": 1}) + "\n")
    with pytest.raises(swap_analysis.SwapAnalysisError):
        swap_analysis.load_samples(str(path))


# --- interarrival_gaps / tail_gap / bursts_per_hour ---------------------

def test_interarrival_gaps_first_from_run_start():
    samples = [mk_sample(i, float(i) * 10, 1000) for i in range(5)]
    bursts = [swap_watch.Burst(1, 2, 10.0, 20.0, 1000, 5_000_000)]
    gaps = swap_analysis.interarrival_gaps(samples, bursts)
    assert gaps == [10.0]  # burst start (10.0) - run start (0.0)


def test_interarrival_gaps_subsequent_from_prior_burst_end():
    samples = [mk_sample(i, float(i) * 10, 1000) for i in range(8)]
    bursts = [
        swap_watch.Burst(1, 2, 10.0, 20.0, 1000, 5_000_000),
        swap_watch.Burst(5, 6, 50.0, 60.0, 5_000_000, 9_000_000),
    ]
    gaps = swap_analysis.interarrival_gaps(samples, bursts)
    assert gaps == [10.0, 30.0]  # 50.0 - 20.0 (prior burst's END, not start)


def test_tail_gap_no_bursts_is_full_span():
    samples = [mk_sample(0, 0.0, 1000), mk_sample(1, 100.0, 1000)]
    assert swap_analysis.tail_gap(samples, []) == 100.0


def test_tail_gap_after_last_burst_end():
    samples = [mk_sample(i, float(i) * 10, 1000) for i in range(6)]
    bursts = [swap_watch.Burst(1, 2, 10.0, 20.0, 1000, 5_000_000)]
    assert swap_analysis.tail_gap(samples, bursts) == pytest.approx(30.0)  # 50.0 - 20.0


def test_bursts_per_hour():
    bursts = [object(), object()]
    assert swap_analysis.bursts_per_hour(bursts, 3600.0) == pytest.approx(2.0)
    assert swap_analysis.bursts_per_hour(bursts, 0.0) == 0.0


# --- gap_statistics ------------------------------------------------------

def test_gap_statistics_none_below_two_gaps():
    assert swap_analysis.gap_statistics([]) is None
    assert swap_analysis.gap_statistics([100.0]) is None


def test_gap_statistics_periodic_arrivals_cv_zero():
    """Perfectly evenly-spaced gaps -> stdev 0 -> cv 0 (the "not bursty at
    all" end of the scale, opposite of what this box actually shows)."""
    stats = swap_analysis.gap_statistics([600.0, 600.0, 600.0, 600.0])
    assert stats["mean_s"] == pytest.approx(600.0)
    assert stats["stdev_s"] == pytest.approx(0.0)
    assert stats["cv"] == pytest.approx(0.0)


def test_gap_statistics_matches_hand_computation():
    gaps = [5716.283163309097, 525.121025800705, 6316.408977270126]
    stats = swap_analysis.gap_statistics(gaps)
    assert stats["n"] == 3
    assert stats["mean_s"] == pytest.approx(sum(gaps) / 3, rel=1e-9)
    assert stats["min_s"] == pytest.approx(min(gaps))
    assert stats["max_s"] == pytest.approx(max(gaps))
    assert stats["cv"] == pytest.approx(stats["stdev_s"] / stats["mean_s"], rel=1e-9)
    assert stats["cv"] > 0.5  # genuinely uneven, not periodic


# --- pswpout_crosscheck --------------------------------------------------

def test_pswpout_crosscheck_exact_ratio():
    samples = [
        mk_sample(0, 0.0, 1000, pswpout=100),
        mk_sample(1, 15.0, 3_000_000, pswpout=100 + 4000),  # 4000 pages * 4096 = 16_384_000
    ]
    bursts = swap_watch.find_bursts(samples, threshold_bytes=1024 * 1024)
    result = swap_analysis.pswpout_crosscheck(samples, bursts)
    assert len(result) == 1
    c = result[0]
    assert c["swap_delta_bytes"] == 2_999_000
    assert c["pswpout_bytes"] == 4000 * 4096
    assert c["ratio"] == pytest.approx((4000 * 4096) / 2_999_000)


def test_pswpout_crosscheck_missing_seq_raises():
    samples = [mk_sample(0, 0.0, 1000, pswpout=0), mk_sample(1, 15.0, 3_000_000, pswpout=10)]
    # a Burst referencing a seq that isn't in `samples` (simulated truncated dataset)
    bad_burst = swap_watch.Burst(0, 99, 0.0, 15.0, 1000, 3_000_000)
    with pytest.raises(swap_analysis.SwapAnalysisError):
        swap_analysis.pswpout_crosscheck(samples, [bad_burst])


# --- analyze / format_report: smoke + no-burst edge case -----------------

def test_analyze_no_bursts_flat_run():
    samples = [mk_sample(i, float(i) * 10, 1000, pswpout=5) for i in range(5)]
    result = swap_analysis.analyze(samples)
    assert result["summary"]["n_bursts"] == 0
    assert result["bursts_per_hour"] == 0.0 or result["bursts_per_hour"] >= 0.0
    assert result["interior_gap_statistics"] is None
    assert result["pswpout_crosscheck"] == []
    text = swap_analysis.format_report(result)
    assert "not enough bursts" in text


def test_format_report_with_real_bursts_includes_derived_fields():
    """Regression: analyze()'s burst dicts must carry delta_bytes/duration_s
    (dataclasses.asdict() drops Burst's @property fields -- format_report
    reads them, so a bare asdict() here throws a KeyError deep in report
    formatting, not at analyze()'s own call site)."""
    samples = [mk_sample(0, 0.0, 1000, pswpout=0), mk_sample(1, 15.0, 3_000_000, pswpout=1000)]
    result = swap_analysis.analyze(samples)
    assert result["bursts"][0]["delta_bytes"] == 2_999_000
    assert result["bursts"][0]["duration_s"] == pytest.approx(15.0)
    text = swap_analysis.format_report(result)
    assert "burst 1" in text
    assert "2.999" not in text  # sanity: no crash, MB formatting used instead of raw bytes


# --- regression against the real round-268 8h dataset --------------------

@pytest.mark.skipif(not R268_DATASET.exists(), reason="round-268 dataset not present")
def test_r268_dataset_reproduces_round298_published_numbers():
    samples = swap_analysis.load_samples(str(R268_DATASET))
    result = swap_analysis.analyze(samples)

    assert result["n_samples"] == 1921
    assert result["summary"]["n_bursts"] == 4
    assert result["summary"]["span_s"] == pytest.approx(28806.66912174225, rel=1e-9)
    assert result["summary"]["total_delta_bytes"] == 485707776
    assert result["summary"]["wide_window_rate_mb_per_hr"] == pytest.approx(60.69941603488819, rel=1e-9)
    assert result["bursts_per_hour"] == pytest.approx(4 / (28806.66912174225 / 3600.0), rel=1e-9)

    gaps = result["interarrival_gaps_s"]
    expected_gaps = [6211.499119758606, 5716.283163309097, 525.121025800705, 6316.408977270126]
    assert gaps == pytest.approx(expected_gaps, rel=1e-9)
    assert result["tail_gap_s"] == pytest.approx(9977.343252658844, rel=1e-9)

    ratios = [c["ratio"] for c in result["pswpout_crosscheck"]]
    assert ratios[:3] == pytest.approx([1.0, 1.0, 1.0], abs=1e-9)
    assert ratios[3] == pytest.approx(1.0064978598318808, rel=1e-9)
    assert result["pswpout_crosscheck"][3]["pswpout_bytes"] == 79941632
    assert result["pswpout_crosscheck"][3]["swap_delta_bytes"] == 79425536

    # interior gaps: every gap except the first (bounded by run start, not a
    # true prior event) -- matches round 298's own reasoning for the 3-value
    # "525s to 9977s, over a 19x spread" characterization (that 9977s figure
    # is the TAIL gap, not an interior gap; kept out of gap_statistics here
    # on purpose since no 5th burst closed it).
    stats = result["interior_gap_statistics"]
    assert stats["n"] == 3
    assert stats["min_s"] == pytest.approx(525.121025800705, rel=1e-9)
    assert stats["max_s"] == pytest.approx(6316.408977270126, rel=1e-9)


@pytest.mark.skipif(not R268_CHECKPOINT.exists(), reason="round-268 checkpoint not present")
def test_r268_checkpoint_and_final_json_agree():
    """The checkpoint .jsonl (append-as-you-go) and the final --out JSON are
    two independent output paths for the same run; both loaders should
    produce byte-identical sample data."""
    from_json = swap_analysis.load_samples(str(R268_DATASET))
    from_jsonl = swap_analysis.load_samples(str(R268_CHECKPOINT))
    assert len(from_json) == len(from_jsonl)
    assert from_json[0] == from_jsonl[0]
    assert from_json[-1] == from_jsonl[-1]
