# Round 016 — NUC-integration(E): E1 benchmark harvested, decode corrected

Date: 2026-08-24. Track E, mission **E1 — benchmark harness** (first unchecked;
round 10 built the harness and launched the run but died before harvesting).

## What happened before this round (inheritance audit)

- Round 10 deployed `nuc/bench.py` to `~/nuc-research/` and launched the full
  benchmark at 00:08 NUC time. It **completed at 00:45** and banked
  `/work/logs/nuc-bench.json` + `nuc-bench-table.md` + `bench-run.log` — but the
  Mac-side round died waiting on its poller, so nothing was harvested, scored,
  or ticked. Lesson repeated from round 1: bank state early; a completed remote
  measurement is worthless until someone reads it.
- The NUC deployment CHANGED since `state/nuc-missions.md` was written: systemd
  units `qwen36-colibri` / `qwen36-toolproxy` **no longer exist** (`systemctl`:
  not-found). The same engine now runs as user processes (since Aug 23):
  `coli serve --host 127.0.0.1 --port 8000 --model-id qwen36 --cap 256
  --ctx 32768 --max-queue 2 --queue-timeout 600` (PID 7939, worker `qwen36 256`
  at ~30 GB RSS) and `/work/src/qwen36-toolproxy/adapter.py` on :8080.
  No unit restarts were needed or performed this round.

## E1 results (measured 2026-08-24 00:08–00:45 NUC time, engine warm)

Engine cold start (discarded warm-up request, ~230 tok): **25.7 s**.

| target | prompt tok | TTFT cold (s) | gross prefill tok/s | TTFT repeat (s) | TTFT fresh (s) | repeat/fresh | decode tok/s (differencing) |
|---|---|---|---|---|---|---|---|
| 100 | 134 | 23.3 | 5.76 | 18.6 | 20.7 | **0.90** | 3.14 |
| 1000 | 904 | 143.1 | 6.32 | 133.7 | 137.9 | **0.97** | 3.69 |
| 4000 | 3998 | 770.3 | 5.19 | — | — | — | ~~11.84~~ artifact, see below |
| 8000 | (extrapolated) | 1551 | 5.16 | — | — | — | — |

- Linear fit over measured sizes: **TTFT ≈ −16.8 s + 196 s per 1k tokens**
  (marginal prefill ≈ 5.1 tok/s). The negative intercept is real information:
  the curve is convex (per-size gross rates 5.76 → 6.32 → 5.19), i.e. the 10
  full-attention layers' O(n²) shows by 4k. Treat the fit as valid 1k–8k only;
  fixed overhead measured from the 100↔1k pair is ≈ 2.4 s.
- **No cross-request KV/prefix reuse**: repeating a byte-identical prompt costs
  0.90–0.97× a fresh same-size prompt (the drift-immune `repeat/fresh` signal).
  Matches the source read (`serve_one` resets `kv_len=0` per request). The
  smoke run's seductive 0.25 warm/cold ratio was engine warm-up, not caching.
- Qwen3.6 tokenizer on word-salad prose: 4.19 chars/tok at 134 tok (instruction
  wrapper dominates), 5.34–5.54 at 1k–4k.
- Client-visible signals: `x-colibri-queue-wait-ms` header (0 throughout — no
  queuing), `usage` carries token counts only (engine `hit%` is not exposed).

### Hermes projection (the number that matters)

A 26.5k-token Hermes turn at ~5.1 tok/s marginal prefill ⇒ **≈ 87 minutes of
prefill per turn**, re-paid EVERY turn because nothing is reused across
requests. Even a trimmed 4k-token agent prompt costs ~13 min/turn today.
Decode (~3.1–3.7 tok/s) is fine for short tool-call replies; **prefill without
prefix reuse is the whole problem.** This makes E3 (KV persistence analysis)
the highest-leverage mission on the list, and E2's "nuc-mini" prompt budget
must target ≲ 500–1000 tokens (2–4 min prefill) to be usable at all.

## The decode@4k = 11.84 tok/s artifact (found in harvest, fixed this round)

`bench.py` computed decode as `(64−1)/(t_decode_run − baseline)` across TWO
requests. At 4k there was no warm baseline (warm probes were skipped for cost),
so the baseline was the COLD TTFT: (775.6 − 770.3) = 5.3 s for 63 tokens. A
~1.7 % prefill drift between two ~770 s requests fully explains it — the
decode-run request simply prefilled ~13 s faster than the cold one. General
rule: **two-request differencing breaks when prefill ≫ decode window**, because
the estimate's error is `prefill_jitter / decode_window`; at 4k that ratio is
~±14 s / 18 s. The harness's own log had the tell (second 4k request barely
longer than the first); rendering the number without a plausibility check let
it into the table.

### Fix run (streaming, intra-request timing; predictions F1–F4 banked first)

One streaming request per size, byte-identical prompts to the round-10 run
(TokenFit state reproduced so `make_prompt` regenerates them exactly;
verified `len == 22157` locally before deploying). Decode =
`(C−1)/(last_chunk − first_chunk)` — immune to inter-request drift.

- 1k: stream TTFT 132.3 s (F2 HIT: 125–150), stream decode **4.78 tok/s**
  (F1 MISS: predicted 3.3–3.9 to match differencing's 3.69) → the two methods
  disagree by 30 % and a THIRD measurement was needed (calibration below).
- 4k: stream TTFT **754.1 s** (F4 HIT: 700–820; repeat/cold vs round-10's
  770.3 = 0.98 → no prefix reuse at 4k either), stream decode **3.32 tok/s**
  (F3 HIT: 2.8–3.5) — the 11.84 artifact is dead.

### Method calibration (predictions G1–G3 banked first)

167-token prompt (23.9 s prefill) with a 256-token (~50 s) decode window,
measured both ways back-to-back, streaming leg recording per-chunk
(elapsed, chars) to expose flush batching.

- Differencing: 256 tok in 75.36 s minus 23.91 s baseline → **4.96 tok/s**
  (G1 MISS: predicted 3.0–3.6 — the "known ~3.5 warm" figure is wrong at
  small KV).
- Streaming: **5.29 tok/s**, tail-rate (excluding first chunk) 5.31 —
  **256 chunks for 256 tokens**: colibri streams one SSE chunk per token, so
  intra-request chunk timing is exact and there is NO first-flush batching.
- Methods agree within 6.7 % (G2 HIT). G3 verdict MISS — I predicted
  differencing was the trustworthy one and streaming inflated; the per-chunk
  data shows the opposite: **streaming is exact, and round-10's differencing
  decode figures (3.14 @100, 3.69 @1k) were inter-request-drift-biased LOW.**

### Unified decode picture (the corrected numbers)

Decode rate is KV-size-bound and falls with context — measured by the exact
streaming method:

| KV size during decode | decode tok/s |
|---|---|
| ~170–420 | 5.29 |
| ~900–1030 | 4.78 |
| ~4000–4130 | 3.32 |

So P9/A7's predicted *falling* trend was physically right all along; the
round-10 artifact numbers had made it look inverted. The mission's "known
fact" of 3.5 tok/s warm is only true at ~4k context.

## D-013 prediction scoring (round-10 predictions, scored against the data)

Originals P1–P11: **2 HIT / 9 MISS.**

| # | predicted | measured | verdict |
|---|---|---|---|
| P1 chars/tok 3.8–5.2 | 4.19 / 5.34 / 5.54 | MISS (out of range at 1k+4k) |
| P2 prefill 9–15 tok/s | 5.1–6.3 | MISS |
| P3 overhead ~1 s | ≈2.4 s (fit intercept −16.8, curve convex) | MISS |
| P4 TTFT@100 6–13 s | 23.3 | MISS |
| P5 TTFT@1k 65–115 s | 143.1 | MISS |
| P6 TTFT@4k 270–450 s | 770.3 | MISS |
| P7 TTFT@8k ~670 s | 1551 (extrap.) | MISS |
| P8 rate drift 100→4k ≤15 % | 10 % slower | HIT |
| P9 decode 3.5/3.4/3.2 | 3.14/3.69/(see calib) — trend inverted | MISS |
| P10 warm/cold 0.85–1.05 | 0.80 / 0.93 | MISS on range; core claim (no reuse) confirmed |
| P11 cache_hit% invisible to clients | confirmed (usage = token counts only) | HIT |

Post-smoke amendments A1–A7: **3 HIT / 4 MISS** (A1 cold start 25.7∈20–70 HIT;
A2 TTFT@100 23.3∉14–18 MISS; A3 marginal 5.1∉7–10 MISS; A4 TTFT@1k 143∈110–160
HIT; A5 TTFT@4k 770∉420–600 MISS; A6 repeat/fresh 0.90/0.97∈0.9–1.1 HIT;
A7 decode trend inverted MISS).

**Meta-lesson (the point of D-013):** both prediction rounds were
systematically optimistic about prefill, and the amendment — written AFTER a
smoke run that bounded prefill at ≤7.2 tok/s *including* overhead — still
anchored on the bound's optimistic edge (predicted 7–10, reality 5.1). When a
measurement gives you an upper bound, the center of your next prediction
should sit well BELOW it, not at it.

## Round-16 fix-run prediction scoring

F: **3 HIT / 1 MISS** (F1 stream@1k 4.78∉3.3–3.9 MISS; F2 132.3∈125–150 HIT;
F3 3.32∈2.8–3.5 HIT; F4 754∈700–820 HIT).
G: **1 HIT / 2 MISS** (G1 differencing 4.96∉3.0–3.6 MISS; G2 convergence
6.7 %≤10 % HIT; G3 verdict-direction MISS — streaming was the sound method).
Cumulative D-013 ledger for E1: P 2/11, A 3/7, F 3/4, G 1/3 — prediction
quality improved as the evidence base grew, which is the mechanism working:
each scored miss forced the model of the machine to change.

## Honest failures

- Round 10's poller pattern (`ssh 'nohup … &'` then wait in-session) killed the
  round; this round hit the same hang on the launch call (the nohup'd process
  holds the ssh stdin socket — the call never returns) but survived because the
  launch was verified out-of-band with a second `ssh -n` check. The skill's
  pitfall list already documented this; I re-tripped it anyway before
  re-reading the skill. Redirect stdin (`< /dev/null`) at launch.
- The 11.84 tok/s artifact was rendered into the round-10 table without a
  sanity check (decode 3.2× faster at 4k than at 100 should have failed a
  monotonicity assertion in `render_markdown`).
- F1 predicted the streaming and differencing methods would agree at 1k; they
  disagreed by 30 % — measuring the same quantity two ways is itself an
  experiment, and I under-predicted the method error.

## Files

- Mac: `nuc/bench.py` (13 tests), `nuc/decode_fix.py`, `nuc/calib_decode.py`,
  `nuc/predictions-e1.md` (P, A, F, G tables + scores).
- NUC: `/work/logs/nuc-bench.json`, `/work/logs/nuc-bench-decodefix.json`,
  `/work/logs/nuc-bench-calib.json`, `/work/logs/nuc-bench.md` (final report),
  `~/nuc-research/{bench.py,decode_fix.py,calib_decode.py,*.log}`.
- Skill updated: `skills/llm-engine-benchmarking/` (differencing-window pitfall
  + streaming intra-request method).
