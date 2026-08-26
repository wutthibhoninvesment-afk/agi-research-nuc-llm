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
  the box itself is off/asleep, not a routing problem; UP again round 124,
  2026-08-25 ~16:11 UTC, uptime 3h13m — no fixed schedule observed yet)
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
- [x] **E4 — Fast lane feasibility.** DONE round 124 (box reachable again;
  live cgroup snapshot confirms — see `/work/logs/nuc-fast-lane.md`, not yet
  at the 36 GB ceiling because the current uptime/load hasn't touched enough
  of the cap-256 expert cache; ceiling is traffic-diversity-dependent, not
  immediate). Verdict unchanged from rounds 100+106+112: bandwidth PASS
  (NUC→HF 8.7–66.7 MB/s per shard),
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
- [x] **E5 — Task-script DSL.** DONE round 124: first live run against :8080
  (`examples/answer_live_r124.errand` through the Mac:8600→NUC:8080 tunnel).
  3 samples: warm requests landed within 13% of the E1-curve projection
  (17.7s/19.85s and 25.0s/28.8s, both under); the first live completion after
  a >1-day idle gap paid a 2.08x cold penalty (85.4s vs 41.1s projected) —
  bigger than round-16's original 25.7s cold-start figure, flagged as a new
  E5 backlog item (a lane-level `cold_penalty` term, or a cheap probe call
  before pricing the real one). Budgets/preflight/ledger all behaved
  correctly regardless of the miss — see `/work/logs/nuc-taskscript.md`.
  **Errand** — `nuc/taskscript/` (SPEC.md,
  lexer/parser/interp/transport/run.py, 77 offline tests, 4 examples).
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

## Round 130 addendum (2026-08-26, box UP — same boot as round 124)

- **E4:** live cgroup snapshot at uptime 5h10m/5h18m found `qwen36-colibri`
  pinned exactly at its 30.0 GiB `memory.max` (round 124 had caught it at
  52% of that, uptime 3h13m, same boot) — confirms the RAM-FAIL verdict live,
  in real time, on this exact deployment. `memory.swap.current` was still
  0 B at both checkpoints even as system `MemAvailable` fell to 0.73 GB —
  new nuance: hitting the ceiling and swapping are sequential cgroup-v2
  events, not simultaneous. No restart performed (needs operator sign-off).
  Full tables appended to `/work/logs/nuc-fast-lane.md`.
- **E5:** ran the warm-up-decay sweep round 124 had flagged as unbuilt
  (gaps 0/30/90/180s) — flat within ~3%, no measurable penalty at any
  gap tested (contra round-124's own "graded" read of one confounded
  `tools yes` sample). Shipped `cold_penalty`/`cold_after` on Errand lanes
  (SPEC v0.2) as a single declared step, not a fitted curve — the data
  doesn't support a curve. Details: `knowledge/round-130-nuc-e-live-window-cold-penalty.md`.
- **Still open, needs an operator decision:** the E3 A/B and the OLMoE
  on-box NVMe check both need a restart/deploy on this shared box; the box
  was reachable this round and neither was attempted without sign-off.

## Round 136 addendum (2026-08-26, box UP — SAME boot as rounds 124/130, uptime 12h53m)

- **E4:** third live cgroup snapshot on the identical boot/session rounds
  124 (3h13m) and 130 (5h10m/5h18m) caught: `qwen36-colibri` still at its
  30.0 GiB ceiling, and this time `memory.swap.current` is **310.6 MB**,
  not 0 B — swap moved off zero given ~7-8 more hours of the same
  session, answering round 130's "needs more elapsed time or a different
  load mix" question (elapsed time alone was enough; still ~14x below
  round 106's original 4.2 GB reading, consistent with slow monotonic
  growth once the ceiling is first touched). No OOM kills found. New:
  one live `nuc/bench.py` point at 307 prompt tokens directly against
  `:8000` — prefill 5.23 tok/s and TTFT 58.6s both match the E1 curve
  (no degradation), decode 4.30 tok/s vs E1's 5.3 tok/s at a comparable
  KV size (~19% slower, TENTATIVE on n=1, plausible swap effect given
  decode's disk/cache-bound working set per round 112). Full tables:
  `/work/logs/nuc-fast-lane.md` "Round 136 addendum"; analysis:
  `knowledge/round-136-nuc-e-third-snapshot-swap-onset-decode-check.md`.
- **Still open, unchanged:** the E3 A/B and OLMoE NVMe check both still
  need an operator-approved restart of the live service. This round adds
  one new argument in favor (swap now nonzero and slowly growing) but
  that is evidence for the decision, not a substitute for it — not
  executed unilaterally.

## Round 142 addendum (2026-08-26, box UP — SAME boot as rounds 124/130/136, uptime 14h21m)

- **E4:** fourth live cgroup snapshot, only 88 minutes after round 136's —
  `qwen36-colibri` still pinned at its 30.0 GiB ceiling, and
  `memory.swap.current` jumped 310.6 MB → **2.96 GiB** (~10x) in that
  88-minute window (~1.82 GB/hour if sustained, ~35x round 136's own
  *average* rate) — corrects round 136's "slow, roughly monotonic" read:
  a same-moment `vmstat`/`/proc/pressure/memory` check shows the growth
  was a burst that had already finished by measurement time (si/so and
  PSI both ≈0), not an accelerating ramp caught mid-flight. System swap
  now 2.96G/4.0G used — only ~858 MB of headroom left. No OOM kills.
  **New decode-under-pressure point REVERSES round 136's tentative
  finding**: decode measured 5.07 tok/s (within 4% of the 5.3 tok/s E1
  baseline) despite ~10x more swap than round 136's run, which measured
  4.30 tok/s (19% below baseline) at 1/10th the swap — decode tok/s does
  not move monotonically with swap volume; round 136's "swap causes
  decode slowdown" hypothesis does not survive a second data point.
  Prefill/TTFT and repeat/fresh both again matched the established
  E1/E3 pattern with no new degradation. Full tables:
  `/work/logs/nuc-fast-lane.md` "Round 142 addendum"; analysis:
  `knowledge/round-142-nuc-e-fourth-snapshot-swap-burst-decode-reversal.md`.
- **Still open, unchanged:** the E3 A/B and OLMoE NVMe check both still
  need an operator-approved restart of the live service — box reachable
  a fourth time (124/130/136/142) without sign-off; swap now within
  ~858 MB of exhausting the swapfile is a louder version of the existing
  RAM-FAIL argument, not a new independent one.

## Done-criteria for any mission
Code runs (proof in round file), measurements banked in both places,
`state/nuc-missions.md` checkbox ticked with a one-line result summary.
