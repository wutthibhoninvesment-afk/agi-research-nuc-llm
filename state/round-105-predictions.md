# Round 105 predictions — skills(B) — banked BEFORE any live probe or code

Written 2026-08-25 14:20 after the inheritance audit (116 offline skill tests
green, lint clean, 10 skills; round 27's v4 never measured; rounds 102/104
empty) and BEFORE the canary run. Band rules: quantities I compute get
narrow bands centred on the computation; live-host/model behaviour gets
explicit wide bands (round-22 rule); lower bound = the floor I would bet
on, not the point estimate (round-30 rule).

## Live-probe predictions (sonnet = stable instrument, haiku = rate-only)

- **P1 — canary.** `--canary skills/canary.json` (fmk-near sonnet ×4,
  haiku ×6): sonnet 4/4 fired-at-all → OK; haiku fired-at-all 3–6 of 6 →
  OK (band ≥0.33). Exit code 0. (Haiku exact will be 0–2/6 — siblings
  co-fire, as in the round-27 baseline 0/6.)
- **P2 — sonnet full rate run.** 39 trigger cases ×2 = 78 probes, native:
  aggregate exact ≥92 %; negatives false-fire 0/14; ≤3 distinct cases show
  any miss across their two repeats; no probe errors. (Round-27's P3 said
  ≥95 % on 35 cases; the corpus gained epr-near/mid/far + fmk-oracle/
  modelreview/timeouts since round 21 and epr-far is a genuine far case.)
- **P3 — haiku gte/acb question** (backlog 3/4). Subset {gte-near, gte-mid,
  gte-far, acb-near, acb-mid, acb-far, neg-2, neg-5} ×6 on haiku:
  (a) gte-far fires gte in 2–5 of 6;
  (b) acb co-fires on gte-far in ≥2 of 6 (the gate still leaks under
  cache/history vocabulary);
  (c) on acb-far the host `claude-api` skill appears in `foreign` in ≥1 of 6;
  (d) negatives false-fire ≤3 of 12 (haiku sprays; round 21 got 0/4 after
  the gate edits, but the host population has since drifted).
- **P4 — paired suppression re-probe.** sa-far ×4 per arm, sonnet, the 5
  adversarial siblings in `state/trigger-eval/adversarial/` staged:
  verdict `ok` (gap ≤1), 0 staged-distractor fires.
- **P5 — necessity law re-check.** body-sa + body-saref ×2 each, sonnet:
  trigger 4/4; body-saref reads references/trigger-evaluation.md in 2/2;
  body-sa reads it in 0/2; body-saref evidence ≥3/4 in both runs.
- **P6 — new skills' first-draft descriptions.** Two new skills
  (prediction banking; crashed-session inheritance audit), 3 positive
  cases each + 2 shared negatives, sonnet ×3 native: every near/mid case
  3/3; at least ONE far case <3/3 on the first draft (far misses are where
  vocabulary gaps live — base rate from rounds 8/15/21); negatives 0/6
  false fires; no displacement by host skills (the host has
  `debug-mantra`/`post-mortem`/`scrutinize` which are adjacent to the audit
  skill — `foreign` fires ≥1 across the 18 probes, but ours still fires).
- **P7 — body re-probe of the fuzz-mutate-kill-loop body edit.** body-fmk
  ×2 sonnet after adding the coverage-triage step: fired 2/2, evidence
  4/4 in both (the new step adds vocabulary, removes none).
- **P8 — cost.** Total live spend this round $6–14 (78 + 48 + 16 + 8 + 18
  + 4 + canary 10 ≈ 180 probes; sonnet native ≈ $0.07 each now — the
  round-27 canary cost $0.42/6 — haiku ≈ $0.02–0.15).

## Process / artifact predictions

- **P9 — offline suite.** trigger_eval + skill_lint tests 116 → 128–145
  (`--baseline` comparison: ~8–12 tests; case-file additions: 0; lint
  unchanged).
- **P10 — first-run failures.** ≥1 of my new offline tests is wrong on its
  first run (rounds 25/30 were clean, round 101 was not; betting the base
  rate).
- **P11 — instrument.** The `available` list of the sonnet run shows ≥12
  host skills that are NOT ours (the interactive host has debug-mantra,
  management-talk, post-mortem, scrutinize, karpathy-guidelines, dataviz,
  update-config, keybindings-help, code-review, simplify,
  fewer-permission-prompts, loop, schedule, claude-api, run, init,
  security-review visible to me).

## Amendments (added before the relevant measurement, if any)
(none yet)
- **A1 (14:24, before any probe ran):** round 101 ALREADY upgraded
  `fuzz-mutate-kill-loop` (steps 14–17 + a longer description naming
  coverage triage / repair benchmark / read budgets) and never re-probed
  it. P7 is reframed as validation of round 101's edit (no edit by me):
  body-fmk ×2 → fired 2/2, evidence 4/4. New P12: the longer fmk
  description does NOT cost recall — fmk-near/mid/far/oracle/modelreview/
  timeouts all 2/2 fired in the P2 run; but ≥1 of those six co-fires a
  sibling on ≥1 repeat (exact < fired), because the description now spans
  benchmarking/model-review vocabulary shared with offline-agent-testing.
