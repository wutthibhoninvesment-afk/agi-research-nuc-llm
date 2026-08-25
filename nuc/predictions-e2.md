# E2 predictions — banked BEFORE measurement (D-013)

Date: 2026-08-24, round 22. Written after reading E1 results + adapter.py +
render_chat_qwen, but BEFORE reading any Hermes prompt-assembly code output,
BEFORE tokenizing any Hermes content, and BEFORE any new NUC requests.

Anchors I'm allowed to use (already banked knowledge):
- E1 curve: TTFT@134tok = 23.3 s, @904 = 143.1 s, @3998 = 770.3 s; marginal
  prefill ≈ 5.1 tok/s at 1k–8k; fixed overhead ≈ 2.4 s; convex.
- State file's standing figure: "a 26.5k-token Hermes turn" (round-10 estimate).
- E1 meta-lesson: I have been systematically optimistic; center predictions
  BELOW the optimistic edge.

## Predictions

- **P1 (tokenizer exactness).** Local HF-tokenizers count of the exact
  rendered prompt string == engine `usage.prompt_tokens`, delta 0, on both
  calibration prompts. (Fallback band: |delta| ≤ 2 counts as partial-hit;
  anything larger = MISS and the local pipeline is wrong somewhere.)
- **P2 (full Hermes turn size).** Default Hermes agent first-turn prompt
  (system prompt + tool schemas rendered through adapter + engine template,
  one short user message) lands in **22k–30k tokens**.
- **P3 (tools share).** Rendered tool-schema JSON (the TOOL_PROTOCOL block)
  accounts for **55–75 %** of total prompt tokens; the identity/instructions
  system prompt is the minority.
- **P4 (tool count).** Default Hermes toolset exposes **25–45 tools**.
- **P5 (nuc-mini feasibility).** A minimal-but-useful config (~4–6 tools:
  read/write/exec-ish + finish, trimmed system prompt) fits in
  **700–1100 tokens** total first-turn prompt.
- **P6 (projection accuracy).** Measured TTFT of the actual nuc-mini prompt
  will be within **±20 %** of the per-size-anchored projection
  `TTFT ≈ tok / 6.0` (gross rate interpolated from E1's 5.76 @134 /
  6.32 @904 — NOT the 1k–8k marginal formula, which over-predicts small
  prompts by ~25 %).
- **P7 (per-turn budget).** nuc-mini interactive per-turn wall time
  (prefill + ~60-token tool-call reply at ~5 tok/s decode) lands in
  **2.5–4 min** for turn 1, growing ~30–60 s per subsequent turn (history
  growth: one tool_result + one assistant call ≈ 200–400 tokens/turn at
  0.16–0.2 s/tok).

## A-series — live nuc-mini verification (banked AFTER local counting,
## BEFORE any live :8080 request; engine is warm from the k-probes)

Local counts already known when writing these: mini first-turn = 565
engine-tokens (n_engine), piecewise TTFT projection 90 s.

- **A1 (count exactness).** Proxy-reported `prompt_tokens` for the mini
  turn-1 request == local n_engine count == **565 exactly**.
- **A2 (turn-1 wall).** Wall time via :8080, engine warm: **85–125 s**
  (projection 90 s TTFT + ~6 s decode of a ~30-token tool call + proxy
  overhead; ±20 % band per P6).
- **A3 (behavior).** First reply is a valid tool_calls JSON, single
  run_shell call, command containing `df` (hit/miss).
- **A4 (turn 2).** With assistant marker + df tool_result appended:
  prompt_tokens **690–800**; wall **110–160 s**; final reply is plain text
  naming the free space (hit/miss).

- **A5 (micro tier, banked before its run; engine warm from turn 2).**
  Local n_engine = 343; engine has been counting ~3 % under my counter on
  JSON-bearing prompts, so: prompt_tokens **328–343**; wall **55–80 s**
  (piecewise projection 56 s + decode + overhead, warm); behavior: valid
  single run_shell tool_call containing `df` (hit/miss).

## Scoring (2026-08-24, after all measurements)

**P: 2 HIT / 5 MISS. A: 2 HIT / 3 MISS.**

- **P1 MISS.** Delta was +8, not 0. Cause: the colibri worker fails to match
  a special token directly preceded by punctuation and BPE-encodes its
  literal text (+4 per `<|im_end|>` after `.`). Root-caused via k-probes;
  emulator `n_engine` now reproduces all 19 pinned engine measurements.
- **P2 HIT.** 26,483 ∈ 22–30k (and dead on the standing 26.5k figure).
- **P3 HIT.** Tools block 74.3 % ∈ 55–75 % (at the very top of the band).
- **P4 MISS.** 22 tools < 25–45. This machine's config gates 18 toolsets
  down to 22 tools; I predicted against the 59-name default core.
- **P5 MISS (good direction).** 565 < 700–1100 — tight one-clause schemas
  are cheaper than I modeled even after designing them myself.
- **P6 MISS as written.** Turn-1 wall 142.3 s vs ~91 s projection (+56 %):
  idle cold start. The warm datapoint (turn 2: 646 tok, ~100 s prefill) hit
  the tok/6.0 model within 7 %. The projection model was right; its
  warm-engine precondition was unstated.
- **P7 MISS.** Turn 1 2.37 min just under the 2.5–4 band; growth ~16 s/turn
  vs predicted 30–60 (a small tool exchange is ~100 tokens, not 200–400).
- **A1 MISS.** 546 vs 565 (−3.4 %): worker BPE diverges from HF tokenizers
  on whitespace-heavy text — a SECOND, independent tokenizer discrepancy
  (m3/m4 probes), direction opposite to the specials bug.
- **A2 MISS.** 142.3 s > 125: idle cold start (~45–50 s over warm, larger
  than E1's 25.7 s cold figure).
- **A3 HIT.** Valid single run_shell tool_call, `df -h /`.
- **A4 MISS on both ranges** (646 < 690–800; 102.8 s < 110–160 — faster
  because the range was anchored on the cold turn 1); behavior sub-claim
  HIT (correct plain-text answer).
- **A5 HIT** on all three sub-claims (338 ∈ 328–343; 55.7 ∈ 55–80; valid
  df call).

**Meta-lesson (D-013):** after E1's "you are systematically optimistic" I
over-corrected into padded pessimism on quantities I compute myself (P5,
P7-growth, A4) while STILL missing machine-state effects (cold start,
twice). Split future predictions into (a) computed-by-me quantities —
center on the computation, narrow band; (b) machine-state quantities —
state the warm/cold precondition explicitly and predict both branches.
