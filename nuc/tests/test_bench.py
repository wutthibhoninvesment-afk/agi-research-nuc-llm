"""Offline tests for nuc/bench.py against a fake OpenAI-compatible engine.

The fake engine tokenizes at a fixed 4 chars/token (+12 template tokens),
"prefills" at PREFILL tok/s and "decodes" at DECODE tok/s using a virtual
clock: it reports the elapsed virtual time in a header instead of sleeping,
and the test's opener patches time.perf_counter accordingly.
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bench  # noqa: E402

PREFILL, DECODE, OVERHEAD = 12.0, 3.5, 1.0
CHARS_PER_TOK, TEMPLATE = 4, 12


def fake_tokens(text):
    return len(text) // CHARS_PER_TOK + TEMPLATE


class FakeEngine(BaseHTTPRequestHandler):
    warm_factor = 1.0          # 1.0 = no prefix reuse; 0.1 = real KV reuse
    seen = set()

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = body["messages"][0]["content"]
        ptok = fake_tokens(prompt)
        pre = OVERHEAD + ptok / PREFILL
        if prompt in FakeEngine.seen:
            pre = OVERHEAD + (ptok / PREFILL) * FakeEngine.warm_factor
        FakeEngine.seen.add(prompt)
        ctok = min(body["max_tokens"], 64)
        dec = (ctok - 1) / DECODE if ctok > 1 else 0.0
        virtual = pre + dec
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("x-virtual-first", f"{pre:.6f}")
            self.send_header("x-virtual-last", f"{virtual:.6f}")
            self.end_headers()
            for i in range(ctok):
                chunk = {"choices": [{"delta": {"content": "OK " if i == 0 else "x"}}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            usage = {"choices": [], "usage": {"prompt_tokens": ptok, "completion_tokens": ctok}}
            self.wfile.write(f"data: {json.dumps(usage)}\n\ndata: [DONE]\n\n".encode())
            return
        payload = {"choices": [{"message": {"content": "OK"}, "finish_reason": "length"}],
                   "usage": {"prompt_tokens": ptok, "completion_tokens": ctok,
                             "total_tokens": ptok + ctok}}
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("x-colibri-queue-wait-ms", "250")
        self.send_header("x-request-id", "req-1")
        self.send_header("x-virtual-last", f"{virtual:.6f}")
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def engine(monkeypatch):
    FakeEngine.seen = set()
    FakeEngine.warm_factor = 1.0
    srv = HTTPServer(("127.0.0.1", 0), FakeEngine)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    # virtual clock: the opener advances it by the engine-reported virtual time
    clock = {"t": 0.0}
    monkeypatch.setattr(bench.time, "perf_counter", lambda: clock["t"])
    real_post = bench._post

    class VirtualResp:
        def __init__(self, resp):
            self.resp, self.headers = resp, resp.headers
            self._first = float(resp.headers.get("x-virtual-first", 0) or 0)
            self._last = float(resp.headers.get("x-virtual-last", 0) or 0)
            self._n = 0

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.resp.close()

        def read(self):
            clock["t"] += self._last + 0.25       # + queue wait, reported in the header
            return self.resp.read()

        def __iter__(self):
            for line in self.resp:
                if line.startswith(b"data:"):
                    self._n += 1
                    # first content chunk arrives at virtual-first, later ones spaced at DECODE
                    clock["t"] = base + self._first + max(self._n - 1, 0) / DECODE
                yield line

    def opener(url, body, timeout, stream=False):
        nonlocal base
        base = clock["t"]
        return VirtualResp(real_post(url, body, timeout, stream))

    base = 0.0
    yield f"http://127.0.0.1:{srv.server_address[1]}", opener, clock
    srv.shutdown()


def test_refuses_frontier_port():
    with pytest.raises(bench.BenchError):
        bench.check_base_url("http://127.0.0.1:8001")
    with pytest.raises(bench.BenchError):
        bench.check_base_url("http://192.168.1.42:8001/")
    assert bench.check_base_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000"


def test_prompts_are_deterministic_and_prefix_distinct():
    a, b = bench.make_prompt(2000, 7), bench.make_prompt(2000, 7)
    assert a == b and len(a) >= 2000
    head = bench.make_prompt(10, 7).index("\n\n") + 2
    c = bench.make_prompt(2000, 8)
    assert c[head:head + 40] != a[head:head + 40]   # salads diverge right after the fixed header
    d = bench.make_prompt(4000, 7)
    assert d[:head + 200] == a[:head + 200]         # same seed shares a prefix by design


def test_token_fit_converges():
    fit = bench.TokenFit()
    for chars in (400, 4000):
        fit.observe(chars, fake_tokens("x" * chars))
    assert abs(fit.slope - 1 / CHARS_PER_TOK) < 1e-9
    assert abs(fit.intercept - TEMPLATE) < 1e-6
    assert fake_tokens("x" * fit.chars_for(1000)) in range(997, 1004)


def test_chat_once_times_and_subtracts_queue(engine):
    url, opener, clock = engine
    r = bench.chat_once(url, "m", bench.make_prompt(400, 1), 1, opener=opener)
    assert r.completion_tokens == 1 and r.prompt_tokens == fake_tokens(bench.make_prompt(400, 1))
    assert r.queue_wait_s == pytest.approx(0.25)
    assert r.service_s == pytest.approx(OVERHEAD + r.prompt_tokens / PREFILL, abs=1e-6)
    assert r.request_id == "req-1" and r.text == "OK"


def test_measure_recovers_prefill_and_decode(engine):
    url, opener, _ = engine
    fit = bench.TokenFit()
    res = bench.measure_size(url, "m", 1000, fit, seed=3, decode_tokens=64, log=lambda *a: None, opener=opener)
    assert res.decode_tok_s == pytest.approx(DECODE, rel=1e-6)
    assert res.warm_over_cold == pytest.approx(1.0)
    assert res.repeat_over_fresh == pytest.approx(1.0, abs=0.02)   # fresh prompt ≈ same size
    assert res.ttft_cold_s == pytest.approx(OVERHEAD + res.prompt_tokens / PREFILL)
    assert res.decode_tokens == 64


def test_warm_probe_detects_prefix_reuse(engine):
    url, opener, _ = engine
    FakeEngine.warm_factor = 0.1
    res = bench.measure_size(url, "m", 1000, bench.TokenFit(), seed=3, decode_tokens=8,
                             log=lambda *a: None, opener=opener)
    assert res.warm_over_cold < 0.5 and res.repeat_over_fresh < 0.5
    assert res.decode_tok_s == pytest.approx(DECODE, rel=1e-6)   # decode uses the warm baseline


def test_engine_warmup_is_discarded_but_recorded(engine):
    url, opener, _ = engine
    meta = {}
    logs = []
    results = bench.run_bench(url, "m", sizes=(100,), decode_tokens=8, log=logs.append,
                              opener=opener, meta=meta)
    assert meta["engine_cold_start_s"] > 0 and logs[0].startswith("[warmup]")
    assert results[0].warm_over_cold == pytest.approx(1.0)      # warm-up did not leak into size 100
    assert results[0].ttft_fresh_s is not None and results[0].ttft_warm_s is not None


def test_run_bench_skips_and_extrapolates_past_cutoff(engine):
    url, opener, _ = engine
    logs = []
    results = bench.run_bench(url, "m", sizes=(100, 1000, 4000, 8000), decode_tokens=8,
                              cutoff_s=200.0, log=logs.append, opener=opener)
    assert [r.target_tokens for r in results] == [100, 1000, 4000, 8000]
    assert [r.extrapolated for r in results] == [False, False, False, True]
    # 4000/12 + 1 ≈ 334 s > 200 → 8k extrapolated from a linear fit of the measured points
    r8 = results[-1]
    assert r8.ttft_cold_s == pytest.approx(OVERHEAD + 8000 / PREFILL, rel=0.02)
    assert any("SKIPPED" in m for m in logs)
    # sizes hit within 10 % once the fit has two points
    for r in results[1:3]:
        assert abs(r.prompt_tokens - r.target_tokens) / r.target_tokens < 0.10


def test_warm_sizes_subset_and_decode_without_warm(engine):
    url, opener, _ = engine
    results = bench.run_bench(url, "m", sizes=(100, 1000), decode_tokens=8, warm_sizes={100},
                              log=lambda *a: None, opener=opener)
    assert results[0].ttft_warm_s is not None and results[1].ttft_warm_s is None
    assert results[1].decode_tok_s == pytest.approx(DECODE, rel=1e-6)


def test_stream_check_measures_first_chunk(engine):
    url, opener, _ = engine
    res = bench.measure_size(url, "m", 100, bench.TokenFit(), seed=5, decode_tokens=16, warm=False,
                             stream_check=True, log=lambda *a: None, opener=opener)
    assert res.stream_ttft_s == pytest.approx(OVERHEAD + res.prompt_tokens / PREFILL, abs=1e-6)
    assert res.stream_decode_tok_s == pytest.approx(DECODE, rel=1e-6)


def test_linear_fit_and_markdown():
    assert bench.linear_fit([(100, 9.0)]) == (0.0, 0.09)
    a, b = bench.linear_fit([(100, 1 + 100 / 12), (1000, 1 + 1000 / 12)])
    assert a == pytest.approx(1.0, abs=1e-6) and 1 / b == pytest.approx(12.0, rel=1e-6)
    rows = [bench.SizeResult(100, 112, 400, 10.3, 10.1, 64, 28.1, 3.5, 10.9, 0.98),
            bench.SizeResult(8000, 8000, 0, 667.0, None, 0, None, 3.2, 12.0, None, extrapolated=True, note="fit")]
    md = bench.render_markdown(rows, {"base_url": "http://x:8000"})
    assert "| 100 | 112 | 10.3 | 10.90 | 10.1 | — | — | 3.50 | 28.1 |  |" in md
    assert "EXTRAPOLATED: fit" in md and "| — |" in md
    assert "Prefill model" not in md      # only one measured row → no fit line


def test_main_cli_writes_outputs(engine, tmp_path, monkeypatch):
    url, opener, _ = engine
    monkeypatch.setattr(bench, "_post", opener)
    j, m = tmp_path / "r.json", tmp_path / "r.md"
    rc = bench.main(["--base-url", url, "--sizes", "100,1000", "--decode-tokens", "8",
                     "--json-out", str(j), "--md-out", str(m)])
    assert rc == 0
    data = json.loads(j.read_text())
    assert len(data["results"]) == 2 and data["meta"]["mode"] == "non-streaming"
    assert data["meta"]["engine_cold_start_s"] > 0 and "finished" in data["meta"]
    assert "Prefill model" in m.read_text()


def test_main_refuses_8001(capsys):
    assert bench.main(["--base-url", "http://127.0.0.1:8001", "--sizes", "100"]) == 2
    assert "refusing" in capsys.readouterr().err
