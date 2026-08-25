import json
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lane_bench as lb  # noqa: E402

SAMPLE = """== Streaming C engine v2.2 | cache=16/layer bits=8 pilot=0 wide=1 guard=1 hot=0 smooth=0.30 conf=0.92 fused3=0 ==
resident weights loaded in 0.7s | RSS after load: 1.98 GB

Reference: 0 0 0
C engine : 7785 15 187
Matching tokens: 0/3

PEAK RSS: 3.49 GB
Expert cache hit rate: 41.2%  (hit=1234 miss=1760)
Speed: 4.60 tok/s (43.5s for 200 tokens)
TUNE decode: 200 tokens in 43.478s
"""


def test_make_ref_and_prompt_cycle():
    ref = lb.make_ref((1, 2, 3), 4)
    assert ref["prompt_ids"] == [1, 2, 3]
    assert ref["full_ids"] == [1, 2, 3, 0, 0, 0, 0]
    assert lb.prompt_of_length(7, base=(9, 8)) == [9, 8, 9, 8, 9, 8, 9]
    with pytest.raises(lb.LaneBenchError):
        lb.make_ref((), 1)
    with pytest.raises(lb.LaneBenchError):
        lb.make_ref((1,), 0)


def test_parse_prefers_tune_line_full_precision():
    st = lb.parse_engine_output(SAMPLE)
    assert st.tokens == 200 and st.seconds == 43.478
    assert st.tok_s == pytest.approx(200 / 43.478)
    assert st.hit_rate_pct == 41.2 and st.hits == 1234 and st.misses == 1760
    assert st.peak_rss_gb == 3.49 and st.rss_after_load_gb == 1.98 and st.load_s == 0.7
    assert st.matching == 0


def test_parse_falls_back_to_speed_line_and_rejects_garbage():
    no_tune = "\n".join(l for l in SAMPLE.splitlines() if not l.startswith("TUNE"))
    st = lb.parse_engine_output(no_tune)
    assert st.tokens == 200 and st.seconds == 43.5
    with pytest.raises(lb.LaneBenchError):
        lb.parse_engine_output("resident weights loaded in 0.7s\n")
    with pytest.raises(lb.LaneBenchError):
        lb.parse_engine_output("Speed: 1.00 tok/s (0.0s for 0 tokens)")


def test_case_parse_forms():
    c = lb.Case.parse("cap=16")
    assert (c.name, c.cap, c.bits, c.env) == ("cap=16", 16, 8, {})
    c = lb.Case.parse("drop:cap=64,EXPERT_DROP=1,OMP_NUM_THREADS=4,bits=8")
    assert c.name == "drop" and c.cap == 64 and c.env == {"EXPERT_DROP": "1", "OMP_NUM_THREADS": "4"}
    with pytest.raises(lb.LaneBenchError):
        lb.Case.parse("EXPERT_DROP=1")
    with pytest.raises(lb.LaneBenchError):
        lb.Case.parse("cap=16,garbage")


def _fake_engine(tmp_path: Path, burn_sys: bool = False) -> str:
    """A stand-in that checks its argv/env contract and prints the harness format."""
    script = tmp_path / "fake_olmoe.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "cap, bits, ref = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]\n"
        "assert os.environ['SNAP'] == 'SNAPDIR', os.environ.get('SNAP')\n"
        "assert 'CHAT' not in os.environ and 'SERVE' not in os.environ\n"
        "r = json.load(open(ref))\n"
        "n_new = len(r['full_ids']) - len(r['prompt_ids'])\n"
        "drop = os.environ.get('EXPERT_DROP', '0')\n"
        "x = 0\n"
        "for _ in range(200000): x += 1\n"  # a little user time
        "print('resident weights loaded in 0.5s | RSS after load: 1.50 GB')\n"
        "print('Matching tokens: 0/%d' % n_new)\n"
        "print('PEAK RSS: %.2f GB' % (1.5 + cap * 0.03))\n"
        "print('Expert cache hit rate: %.1f%%  (hit=%d miss=%d)' % (100.0 * cap / 64, cap, 64 - cap))\n"
        "secs = n_new * (0.2 if drop == '1' else 0.1)\n"
        "print('Speed: %.2f tok/s (%.1fs for %d tokens)' % (n_new / secs, secs, n_new))\n"
        "print('TUNE decode: %d tokens in %.3fs' % (n_new, secs))\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_run_case_passes_env_and_captures_rusage(tmp_path):
    engine = _fake_engine(tmp_path)
    ref = lb.write_ref(str(tmp_path / "ref.json"), lb.make_ref(lb.DEFAULT_PROMPT_IDS, 50))
    os.environ["CHAT"] = "1"  # must be scrubbed for the harness mode
    try:
        r = lb.run_case(engine, "SNAPDIR", lb.Case.parse("cap=16"), ref, 5, 50)
        d = lb.run_case(engine, "SNAPDIR", lb.Case.parse("drop:cap=16,EXPERT_DROP=1"), ref, 5, 50)
    finally:
        del os.environ["CHAT"]
    assert r.stats["tok_s"] == pytest.approx(10.0) and d.stats["tok_s"] == pytest.approx(5.0)
    assert r.stats["hit_rate_pct"] == 25.0 and r.stats["peak_rss_gb"] == pytest.approx(1.98)
    assert r.user_s >= 0 and r.sys_s >= 0 and r.wall_s > 0
    assert 0.0 <= r.sys_share <= 1.0
    assert r.n_prompt == 5 and r.n_new == 50 and d.env == {"EXPERT_DROP": "1"}


def test_run_case_raises_on_engine_failure(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("#!/usr/bin/env python3\nimport sys; sys.stderr.write('boom'); sys.exit(3)\n")
    bad.chmod(bad.stat().st_mode | stat.S_IEXEC)
    ref = lb.write_ref(str(tmp_path / "ref.json"), lb.make_ref((1,), 1))
    with pytest.raises(lb.LaneBenchError, match="exited 3"):
        lb.run_case(str(bad), "SNAPDIR", lb.Case.parse("cap=1"), ref, 1, 1)


def test_prefill_rate_only_for_single_token_cases():
    stats = {"seconds": 10.0, "tok_s": 0.1, "tokens": 1}
    one = lb.CaseResult("p", 16, 8, {}, 200, 1, 10.5, 9.0, 1.0, stats, 0)
    many = lb.CaseResult("d", 16, 8, {}, 5, 200, 10.5, 9.0, 1.0, {**stats, "tokens": 200}, 0)
    assert lb.prefill_tok_s(one) == pytest.approx(20.0)
    assert lb.prefill_tok_s(many) is None
    table = lb.markdown_table([one, many])
    assert "20.0 (prefill)" in table and "| 0.10 |" in table and "10 %" in table


def test_cli_end_to_end_writes_json_and_table(tmp_path, capsys):
    engine = _fake_engine(tmp_path)
    out = tmp_path / "res.jsonl"
    rc = lb.main(["--engine", engine, "--snap", "SNAPDIR", "--case", "cap=16", "--case", "cap=64",
                  "--n-new", "10", "--prompt-tokens", "12", "--ref", str(tmp_path / "r.json"),
                  "--json", str(out), "--repeats", "2"])
    assert rc == 0
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    assert [r["name"] for r in rows] == ["cap=16#1", "cap=64#1", "cap=16#2", "cap=64#2"]
    assert all(r["n_prompt"] == 12 and r["n_new"] == 10 for r in rows)
    ref = json.loads((tmp_path / "r.json").read_text())
    assert len(ref["prompt_ids"]) == 12 and len(ref["full_ids"]) == 22
    table = capsys.readouterr().out
    assert table.count("\n") == 6 and "| cap=64#2 | 64 |" in table   # header + rule + 4 rows
