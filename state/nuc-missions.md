# NUC missions (track E) — pick the FIRST unchecked, in order

Context: pgain-nuc (i5-7260U 2c/4t, 31 GB RAM, NVMe) runs Colibri v1.7.0 with
Qwen3.6-35B-A3B: engine on :8000 (unit qwen36-colibri), tool-proxy on :8080
(unit qwen36-toolproxy), Mac tunnel on localhost:8600. Goal: make it genuinely
usable for Hermes Agent workloads.

Known facts (measured 2026-08-24, E1 full curve — /work/logs/nuc-bench.md):
- prefill ~5.1 tok/s marginal (TTFT ≈ 196 s per 1k prompt tokens, convex);
  fixed overhead ≈ 2.4 s; engine cold start after idle 25.7 s
- decode falls with KV size: 5.3 tok/s @ ~300 KV, 4.8 @ ~1k, 3.3 @ ~4k
  (streaming-exact; colibri streams one SSE chunk per token)
- no cross-turn KV reuse measured: repeat/fresh 0.90–0.98 at 100/1k/4k
  (`serve_one` resets kv_len per request); 26.5k Hermes turn ⇒ ~87 min
  prefill re-paid every turn; usable interactive ceiling ≈ 1k-token prompt
- deployment drift: systemd units qwen36-colibri/qwen36-toolproxy no longer
  exist; same engine runs as user processes (coli serve :8000, adapter :8080)
- SSH: ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.42 (key-based, works)

## Missions

- [x] **E1 — Benchmark harness.** DONE rounds 10+16: prefill 5.1 tok/s
  marginal / TTFT 23 s @134 tok, 143 s @904, 770 s @3998, 1551 s @8k
  (extrap.); decode 5.3→3.3 tok/s as KV grows 300→4k; repeat/fresh 0.90–0.98
  = no prefix reuse; results in /work/logs/nuc-bench.md + knowledge/round-016.
  Write `bench.py` locally, deploy to
  `~/nuc-research/` on the NUC, measure TTFT / prefill tok/s / decode tok/s at
  prompt sizes 100 / 1k / 4k / 8k tokens against :8000 (non-streaming).
  Write PREDICTIONS first, then measure, then score misses (house rule D-013).
  Results → `/work/logs/nuc-bench.md` on the NUC AND the round knowledge file.
  If 4k prefill already exceeds 5 min, extrapolate — do NOT burn an hour on 8k.
- [x] **E2 — Prompt budget for Hermes.** DONE round 22: real Hermes turn =
  26,483 engine tokens (tools 74.3 %, system 25.6 %) ⇒ ~86 min TTFT — even
  maximal trimming leaves ≥5.5k (~18 min): stock Hermes is a no-go. Built
  nuc-mini profile instead (`~/nuc-research/nuc_mini.py`): micro tier 338 tok
  / 55.7 s, mini 546–646 tok / 1.7–2.4 min per turn, 2-turn agent loop
  verified correct end-to-end via :8080. Bonus: colibri worker tokenizer
  mis-matches specials after punctuation (+4 tok/frame, text-spelled
  <|im_end|>) — upstream fix candidate. Results in
  /work/logs/nuc-prompt-budget.md + knowledge/round-022.
  Original brief: Measure the token cost of a Hermes
  agent turn (system prompt + tool schemas — source at ~/.hermes/hermes-agent,
  count with a real tokenizer or a word-based estimate stated as such). Design
  a minimal "nuc-mini" setup (fewest tools that still allow a useful agent
  turn). Project its prefill time using the E1 curve. Deliverable: a concrete
  config recommendation + projected seconds-per-turn.
- [x] **E3 — Prefix/KV reuse analysis (READ-ONLY).** DONE round 28: NO —
  `serve_one` resets per request, SUBMIT slot is `(void)`, registry caps
  qwen36 at 1 KV slot (only non-GLM engine without the shared `kv_prefix.h`);
  live triple 48.3/47.6/47.6 s (ratio 1.00). Drafted + compile-verified
  `nuc/kv_reuse/qwen36-prefix-reuse.patch` (+250 lines: fed-token record,
  grow-preserving KV, two 65.9 MB DeltaNet snapshots at gateway-hinted
  boundaries; 37/37 shaped-model checks, upstream tests + 144 server tests
  green, warning set identical) + `openai_server-prefix-hint.patch`;
  projected nuc-mini turns 2–4: 67–86 s → 8–17 s prefill, Hermes 26.5k: 86 min
  → 9–18 s after turn 1. NOT run with weights (needs an operator-approved
  restart; A/B recipe in `nuc/kv_reuse/PROPOSAL.md`). Results in
  /work/logs/nuc-kv-reuse.md + knowledge/round-028.
  Original brief: Read
  /work/src/colibri-v170/c/qwen36.c + openai_server.py. Question: can KV state
  persist across requests so a stable system-prompt prefix is computed once?
  Document findings + draft an upstream proposal. NO edits to colibri sources.
- [ ] **E4 — Fast lane feasibility.** Measure NUC→HuggingFace bandwidth
  (curl a known file). If sustained >3 MB/s and disk allows, plan the
  OLMoE-1B-7B int8 lane (~7 GB container via colibri's olmoe engine, which
  has tool-friendly smaller prompts). Plan first; download only with a
  recorded disk/bandwidth justification in the same round.
- [ ] **E5 — Task-script DSL.** Design a tiny task-script language for NUC
  agent ops (declare task → retries → budget → telemetry), informed by
  languages/whence and harness/ learnings. Spec + interpreter prototype.

## Done-criteria for any mission
Code runs (proof in round file), measurements banked in both places,
`state/nuc-missions.md` checkbox ticked with a one-line result summary.
