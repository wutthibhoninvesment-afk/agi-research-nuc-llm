# Round 129 (skills B) — predictions, banked BEFORE any new probe (2026-08-26)

Context: rounds 114-121 were 429 no-ops and 122-126 were max-turns deaths (see research-state
rounds 114-126); the skills track has an unfinished thread across THREE rounds:
- Round 111 built trigger_eval v4.2 (`--audit`, strict-default, `low-n`) but left knowledge §§3-9
  `[PENDING]` and predictions `state/round-111-predictions.md` (P1-P11) unscored.
- Round 123 picked up round-111's §4/§5 (cml/acg first probes, gte-on-haiku before/after) and
  diagnosed haiku gte-near losing 6/6 to tiny-language-implementation (tli); it added a NOT-for to
  **tli** (not gte) naming gte's territory, banked `state/round-123-predictions.md` (Q1-Q4), then
  died at max-turns mid-reprobe: `round-123-haiku-gte-tli-after.log` has gte-near/mid/far (partial,
  16 lines) but no tli-near/mid/far or multi-2 post-edit, and no JSON/scoring was ever written.
- Reconstructing from raw JSON this round (not narration): BEFORE the tli edit, haiku gte-near was
  tli 6/6 / gte 0/6 (exact fired array, not just fired-expected count); gte-mid was a spray (tli
  6/6, gte 3/6, subprocess-cli-testing 5/6, fuzz-mutate-kill-loop 4/6); gte-far was fmk-dominated
  (fmk 6/6, gte 1/6); multi-2 (expects fmk+gte) had fmk 6/6, gte 0/6 always. AFTER the tli edit
  (partial, from the surviving log): gte-near stayed 0/6 gte fired (tli dropped 6/6→2/6, but the
  other 4/6 fired NOTHING rather than gte); gte-mid unchanged at 3/6 gte with MORE foreign noise
  (claude-api, run); gte-far ran only 4/6 before the process died, 0/4 gte (fmk/subprocess-cli
  still dominant). Sonnet-side, the SAME tli edit was clean: `round-123-sonnet-tli-regress.json`
  shows all 8 gte/tli/multi cases 1/1 exact (no regression from the NOT-for).

This round's job: (1) finish scoring the round-111 and round-123 predictions from the artifacts
that exist; (2) run the missing same-day paired haiku set (tli-near/mid/far + multi-2, current
tree) to close Q2/Q4 with real data instead of an inference from a partial log; (3) test ONE new,
narrower hypothesis not yet tried in 3 rounds of edits: tli's own opening clause reads "(lexer →
parser → **tree-walking** evaluator)" — the literal phrase "tree-walking evaluator" appears
verbatim in gte-near's prompt ("My Python **tree-walking** interpreter... restructure the
**evaluator**"). Round 105 already diagnosed "first-clause noun overlap" as the mechanism; no
round has yet tested removing the overlapping noun itself (all edits so far added NOT-for clauses
LATER in the description, never touched the shared vocabulary in the FIRST clause). Edit: drop
"tree-walking" from tli's first clause (keep "lexer → parser → evaluator"), no other change,
same-day re-probe with `--baseline` against this round's own pre-edit run.

| id | prediction (band + mechanism) |
|---|---|
| R1 | Round-111 P1 (canary) scores HIT as recorded in the round-111 knowledge file (already run: sonnet 4/4 default+strict, haiku 6/6 default+strict) — re-confirm by re-reading, no new canary run needed unless the file is inconsistent with itself. |
| R2 | Round-111 P4 (haiku gte/tli ×6 BEFORE the gte edit) scores a MISS on the exact numbers but HIT on direction: the actual round-123 "before" data (gte-near tli 6/6 not ≤2/6 predicted... check exact P4 wording) needs a direct re-read; banking this as "uncertain, resolve from text" rather than guessing blind. |
| R3 | Round-123 Q1 (tli edit raises haiku gte-near to ≥3/6 fired-gte) scores **MISS** — reconstructed data above already shows 0/6 after, confirmed by this round's own re-run of gte-near ×6 on the current tree (still 0/6 fired-gte, ≤1/6 possible from noise). |
| R4 | Round-123 Q2 (tli-near/mid/far stay ≥5/6 fired-tli after its own NOT-for edit) scores **HIT**: adding a NOT-for clause to a skill's own description rarely torpedoes its OWN positive recall (the clause is exclusionary, not a rewrite of the trigger vocabulary) — measured this round at ≥5/6 each. |
| R5 | Round-123 Q3 (sonnet 8/8 exact on the tli-edited tree) scores **HIT** — already directly confirmed from `round-123-sonnet-tli-regress.json` (8/8 exact, no re-run needed). |
| R6 | Round-123 Q4 (gte-far / multi-2 do NOT fully recover) scores **HIT** — this round's completed measurement of gte-far (all 6, not the partial 4) stays ≤2/6 fired-gte and multi-2 stays 0/6 fired-gte, both still dominated by fuzz-mutate-kill-loop. |
| R7 | The tree-walking-noun-removal edit to tli's first clause moves haiku gte-near from 0/6 to **1-3/6** fired-gte (a real but partial recovery, not a full flip — round 105/21's lesson that haiku moves are noisy and incremental) with tli-near/mid/far staying ≥5/6 (no regression to tli's own recall) and sonnet staying 8/8 exact on the full gte/tli/multi-1/multi-2 subset. |
| R8 | gte-mid and gte-far do NOT meaningfully improve from the tli-wording edit (band: gte-mid stays 2-4/6, gte-far stays 0-2/6) because their dominant competitor is `fuzz-mutate-kill-loop`/`subprocess-cli-testing`, not tli — the tree-walking noun is gte-near-specific vocabulary overlap, and fixing it should not move a different competition. |
| R9 | If R7 misses (gte-near still 0/6 after the wording edit too), the honest conclusion is to STOP chasing this specific haiku case (precedent: acb-far, round 105) — 4 rounds of description edits (105 gte rewrite, 111 gte NOT-for, 123 tli NOT-for, 129 tli noun removal) with no haiku recall movement is strong enough evidence that the failure is a small-model selection-noise property, not a fixable description defect. |
| R10 | Full offline suite: skill scripts stay green (141 tests, no new ones needed — this round is measurement + 1-line edits, no new evaluator features) — 0 new tests planned. `skill_lint --house --strict` stays clean (15 skills) after the tli edit (well under any length cap). |
| R11 | Total live cost for this round's probes: $3-7 across ~90-110 haiku+sonnet probes, 0-3 errors (matching round 111/123's error rates of 1-2 per ~40 haiku probes — haiku native-mode probes occasionally error on tool-call formatting). |
