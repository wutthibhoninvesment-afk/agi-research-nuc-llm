# E1 — NUC benchmark: TTFT / prefill / decode / prefix-reuse (FINAL)

Machine: pgain-nuc, Colibri v1.7.0, Qwen3.6-35B-A3B (`coli serve --cap 256
--ctx 32768`, user processes on :8000/:8080 — the old systemd unit names are
gone). Measured 2026-08-24: full curve 00:08–00:45 (round 10's run, harvested
round 16), decode fix + method calibration 08:05–08:24 (round 16).
Method: `~/nuc-research/bench.py` + `decode_fix.py` + `calib_decode.py`;
predictions banked before every run in the Mac-side `nuc/predictions-e1.md`.

## Headline numbers

- **Prefill: ~5.1 tok/s marginal** — TTFT ≈ 196 s per 1k prompt tokens,
  slightly convex (gross rate 5.76 @134 tok, 6.32 @904, 5.19 @3998; the 10
  full-attention layers show by 4k). Fixed overhead ≈ 2.4 s. Engine cold
  start (idle → first request) 25.7 s, then stable.
- **No cross-request KV/prefix reuse**: byte-identical repeat prompts cost
  0.90–0.98× a fresh same-size prompt (repeat/fresh 0.90 @100, 0.97 @1k;
  repeat TTFT 754 s vs cold 770 s @4k). Matches `serve_one` resetting
  `kv_len=0` per request.
- **Decode falls with KV size**: 5.3 tok/s @ ~300-token KV, 4.8 @ ~1k,
  3.3 @ ~4k (exact streaming measurement; colibri emits one SSE chunk per
  token, so intra-request chunk timing has no batching bias).
- Tokenizer: 5.3–5.5 chars/token on English prose at 1k+.

## The curve

| prompt tok | TTFT cold (s) | TTFT repeat (s) | repeat/fresh | decode tok/s (stream-exact) |
|---|---|---|---|---|
| 134 | 23.3 | 18.6 | 0.90 | ~5.3 (at this KV size; calib @167 tok) |
| 904 | 143.1 | 133.7 | 0.97 | 4.78 |
| 3998 | 770.3 | 754.1 | ~0.98 (repeat/cold) | 3.32 |
| 8000 | 1551 (extrapolated: TTFT ≈ −16.8 + 0.196·tok) | — | — | ~2.5–3 (extrapolated) |

## Corrections to earlier banked numbers

- The 00:45 table's decode@4k = **11.84 tok/s is an artifact**: it differenced
  two ~770 s requests ((64−1)/(775.6−770.3)) and ~1.7 % inter-request prefill
  drift swamped the 18 s decode window. Streaming re-measurement: 3.32.
- The differencing decode figures 3.14 @100 / 3.69 @1k were drift-biased LOW
  (calibration at 167 tok: differencing 4.96 vs exact streaming 5.29,
  converging within 6.7 % once the decode window reached ~50 s).
- Rule for future benches: differencing error ≈ prefill_jitter/decode_window;
  when prefill ≫ decode window, measure decode inside one streaming request.

## What this means for Hermes on this box

- A 26.5k-token Hermes turn ⇒ **≈ 87 min prefill, re-paid every turn** (no
  reuse). Unusable, as suspected — now quantified.
- A trimmed 4k-token agent prompt still costs ~13 min/turn; **≲ 1k tokens
  (~2.5 min) is the ceiling for a usable interactive agent turn** (E2 target).
- Highest-leverage fix is **persistent KV for a stable system-prefix** (E3):
  90–97 % of a repeat turn's wall time is re-prefilling identical tokens.
- Decode is adequate (3–5 tok/s) for short tool-call replies once prefill is
  paid; long generations at big contexts run at ~3.3 tok/s.

## D-013 prediction ledger (details in Mac nuc/predictions-e1.md)

Round-10 originals P1–P11: 2 HIT / 9 MISS (systematically optimistic on
prefill). Post-smoke amendments A1–A7: 3 HIT / 4 MISS (still anchored on the
optimistic edge of the smoke bound). Round-16 fix F1–F4: 3/4. Method
calibration G1–G3: 1/3 (G3's "streaming is the biased one" verdict was
backwards — per-chunk data settled it).

Raw data: `/work/logs/nuc-bench.json`, `/work/logs/nuc-bench-decodefix.json`,
`/work/logs/nuc-bench-calib.json`, run logs in `~/nuc-research/`.
