# E1 predictions — written BEFORE measurement (house rule D-013)

Date: 2026-08-24. Target: pgain-nuc :8000, Colibri v1.7.0, Qwen3.6-35B-A3B
i4 gs64, engine env `OMP_NUM_THREADS=2 NGEN=8192 KV_SLOTS=1`, `--cap 256`.

Evidence used: mission "known facts" (decode ~3.5 tok/s warm; ≤20-token
prompts answer in 2–5 s; 26.5k-token prefill >30 min ⇒ prefill < 14.7 tok/s);
source reads: `qwen36.c serve_one` resets `kv_len=0` per request; STAT `tps`
is measured after the prefill `step()`; `hit%` is the expert-cache hit rate.

| # | Metric | Prediction | Basis |
|---|--------|-----------|-------|
| P1 | chars/token of the word-salad prompt | 4.5 ± 0.7 | English ≈1.3 tok/word |
| P2 | Prefill rate (steady, 1k+) | 12 tok/s (range 9–15) | 26.5k>30min bound; MoE prefill on 2 cores ≈3× decode |
| P3 | Fixed per-request overhead | ~1.0 s | HTTP + tokenizer + reset; 20-tok prompts answering in 2–5 s |
| P4 | TTFT @100 tok (cold) | 9 s (6–13) | 100/12 + 1 |
| P5 | TTFT @1k tok (cold) | 85 s (65–115) | 1000/12 + 1 |
| P6 | TTFT @4k tok (cold) | 330 s (270–450) | >300 s ⇒ 8k SKIPPED and extrapolated |
| P7 | TTFT @8k (extrapolated) | ~670 s | linear; 30/40 layers are linear attention ⇒ ≈O(n) |
| P8 | Prefill rate drift 100→4k | ≤ 15 % slower at 4k | 10 full-attention layers add O(n²) but small at 4k |
| P9 | Decode @100 / @1k / @4k | 3.5 / 3.4 / 3.2 tok/s | known warm figure; mild KV growth cost |
| P10 | Warm repeat TTFT / cold TTFT | 0.85–1.05 (NO KV reuse) | `kv_len=0` per request; expert cache may shave a little |
| P11 | Engine cache_hit% is not client-visible | true | `usage()` returns only token counts |

Falsification rules: a prediction "misses" if the measured value falls outside
the stated range; P10 misses if warm/cold < 0.5 (that would mean real prefix
reuse exists and the source read was wrong).

## Post-smoke amendment (written after ONE smoke run at 100 tok, BEFORE the full run)

The smoke run (seed 99, 114 tok) measured: first request after ~10 h idle 62.9 s,
identical repeat 15.8 s, streaming TTFT 15.7 s; the model answered "OK" + EOS
so decode was unmeasurable. Consequences, recorded before the full run:

| # | Metric | Revised prediction | Why |
|---|--------|-------------------|-----|
| A1 | Engine cold start (first request after idle, ~230 tok warm-up prompt) | 20–70 s | 63 s seen once; expert cache / page cache refill, amortised by the warm-up |
| A2 | TTFT @100 (cold prefix, warm engine) | 14–18 s | 15.8 s seen; P4's 9 s is already a MISS |
| A3 | Prefill marginal rate (1k+) | 7–10 tok/s | 114 tok in 15.8 s ⇒ ≤7.2 tok/s incl. overhead; P2's 12 likely a miss |
| A4 | TTFT @1k | 110–160 s | 1000/8 + ~2 |
| A5 | TTFT @4k | 420–600 s → 8k skipped, extrapolated 850–1200 s | linear |
| A6 | repeat/fresh (prefix-reuse signal) | 0.9–1.1 | kv_len reset per request; the 0.25 warm/cold was engine warm-up, not KV reuse |
| A7 | decode @100/1k/4k | 3.5 / 3.3 / 3.0 tok/s | unchanged from P9, slightly wider |

Original P1–P11 stay on the record and are scored as written.

## Decode-fix predictions (round 16, written BEFORE the fix run)

Context: the round-10 full run banked decode@4k = 11.84 tok/s, computed as
(64−1)/(775.6−770.3) — a difference of two ~770 s requests, where ~1.7 % prefill
drift swamps the decode signal. Fix run: ONE streaming request per size
(identical byte-equal prompts to the round-10 run), decode = (C−1)/(last−first
chunk). 1k first to validate the method against the trusted 3.69, then 4k.

| # | Metric | Prediction | Basis |
|---|--------|-----------|-------|
| F1 | stream decode @1k | 3.3–3.9 tok/s | must match differencing 3.69 if method sound |
| F2 | stream TTFT @1k (repeat prompt) | 125–150 s | round-10 repeat 133.7 s; no KV reuse |
| F3 | stream decode @4k | 2.8–3.5 tok/s | P9 said mild KV-growth slowdown; 11.84 is an artifact |
| F4 | stream TTFT @4k (repeat prompt) | 700–820 s | cold was 770 s; kv_len reset ⇒ repeat ≈ cold |

Falsification: F3 ≥ 5 tok/s would mean 4k decode genuinely speeds up (and the
artifact theory is wrong).

## Method-calibration predictions (round 16, after the 1k fix leg, BEFORE the calib run)

Observed so far: stream decode @1k = 4.78 (F1 MISS — 30 % above differencing's
3.69). Two candidate artifacts: (a) server buffers the first chunk(s) → first
token timestamp late → streaming overestimates; (b) inter-request prefill drift
→ differencing at 1k had a 17 s window with ±3 s jitter. Calibration: ~130-token
prompt (prefill ≈ 20 s, jitter ≤ ±0.5 s), max_tokens=256 (~70 s decode window),
measured BOTH ways back-to-back. Long window + small jitter ⇒ both artifacts
shrink ⇒ the two estimates must converge on the true rate.

| # | Metric | Prediction | Basis |
|---|--------|-----------|-------|
| G1 | differencing decode, 256-tok window @130-tok prompt | 3.0–3.6 tok/s | mission known ~3.5; round-10 @100 gave 3.14 with a clean 20 s window |
| G2 | streaming decode, same request | within ±10 % of G1 | both artifacts are window-size effects; at 70 s they vanish |
| G3 | implied verdict | differencing@1k (3.69) was closer than streaming (4.78); streaming's first-chunk delay is the bigger artifact | smoke run showed stream TTFT ≈ full non-stream wall for a 1-token reply, hinting at flush batching |
