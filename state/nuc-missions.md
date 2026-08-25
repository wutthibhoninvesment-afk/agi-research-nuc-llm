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
- SSH: ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37 (key-based, works when
  the box is up; DOWN on 2026-08-25 14:44 and 20:09 — ARP incomplete, i.e.
  the box itself is off/asleep, not a routing problem)
- qwen36-colibri IS a systemd unit — a USER unit (`systemctl --user`), cgroup
  `user.slice/user-1000.slice/user@1000.service/app.slice/qwen36-colibri.service`
  (round 100); the "units no longer exist" line above was a scope error

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
- [ ] **E4 — Fast lane feasibility.** VERDICT REACHED (rounds 100+106+112,
  Mac-side; tick blocked only on the NUC-side log write — the box was down on
  both 08-25 E rounds): bandwidth PASS (NUC→HF 8.7–66.7 MB/s per shard),
  disk PASS (677 GB free vs 7.42 GB), RAM FAIL (qwen36 `--cap 256` is itself
  36.0 GB on a 31.2 GiB box, 4.2 GB in swap — every option incl. "no lane"
  needs one restart at a lower cap: 204 no-lane / 143 cap-16 lane / 75 cap-64).
  Lane rates measured on the Mac in the box's page-cache-cold regime: prefill
  8.0–9.6 prompt-tok/s (cap 16; compute-bound, flat in prompt length), decode
  1.20 tok/s (disk-bound; cap 64 = 0.30). Against qwen36 (E1 curve, 3.3 tok/s)
  the lane wins only above ~700 prompt tokens for a 60-token reply
  (`fast_lane.breakeven_prompt_tokens`); NVMe projection 3.6 tok/s would win
  everywhere and needs a 5-minute on-box measurement. Recommendation: restart
  at `--cap 204`, run the E3 A/B, treat OLMoE as a long-prompt/short-reply
  helper only. Plan + tables: `nuc/fast_lane/PLAN-E4.md`; hand-off script
  `fast_lane.py handoff`; NUC window checklist in knowledge/round-112 §7.
  Original brief: Measure NUC→HuggingFace bandwidth
  (curl a known file). If sustained >3 MB/s and disk allows, plan the
  OLMoE-1B-7B int8 lane (~7 GB container via colibri's olmoe engine, which
  has tool-friendly smaller prompts). Plan first; download only with a
  recorded disk/bandwidth justification in the same round.
- [ ] **E5 — Task-script DSL.** PROTOTYPE BUILT round 112 (Mac-side; tick
  blocked on one live run against :8080 to compare projected vs measured
  seconds + the NUC log write): **Errand** — `nuc/taskscript/` (SPEC.md,
  lexer/parser/interp/transport/run.py, 77 offline tests, 3 examples).
  Lanes carry measured curves (`prefill e1` = the E1 points), budgets are
  consumed ledgers, every task is priced and refused BEFORE any request when
  it does not fit the remaining budget, retries draw on the budget, results
  are ok/miss values with trails (`rescue`, `why`), JSONL telemetry, dry-run
  pricing with the box down, port 8001 refused at parse and send time.
  `run.py examples/triage.errand triage text=... --transport http` is the
  live check. Skill: `skills/preflight-priced-task-scripts/`.
  Original brief: Design a tiny task-script language for NUC
  agent ops (declare task → retries → budget → telemetry), informed by
  languages/whence and harness/ learnings. Spec + interpreter prototype.

## Done-criteria for any mission
Code runs (proof in round file), measurements banked in both places,
`state/nuc-missions.md` checkbox ticked with a one-line result summary.
