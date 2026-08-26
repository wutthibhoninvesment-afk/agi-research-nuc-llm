# Round 135 (skills B) — predictions, banked BEFORE the tli first-clause edit or any new probe (2026-08-26)

Context: finishing the gte/tli haiku saga inherited across rounds 105 -> 111 -> 123 -> 129 (all
unfinished: round 111 knowledge file has §§4/5/7/8/9 `[PENDING]`, round 123 and 129 both died with
banked-but-unscored predictions and no knowledge file). Scoring the existing artifacts BEFORE this
round's own new probe (done by direct JSON inspection, not narration):

- Round 111's own `round-111-strict-full.json` (20:08, sonnet, 59 cases x2 = 118 probes) already
  answers P2/P2b/P3(partial)/§4 in full: 118/118 exact, 0/24 negatives, 0 errors, $4.69 -- cml-near/
  mid/far/neg and acg-near/mid/far/neg ALL 2/2 exact including acg-far (P2b's fmk-co-fire worry on
  acg-far did not happen). This run existed the whole time; rounds 123/129 never looked for it.
- Round 123's `round-123-haiku-gte-tli.json` (23:03, haiku, BEFORE round 123's own tli-NOT-for edit,
  but AFTER round 111's gte symptom-first rewrite) is therefore the true measurement of round 111's
  own P5 ("after the gte rewrite, gte-near fires gte >= 4/6"): actual gte-near = 0/6 gte fired, 6/6
  tli fired. P5 MISS.
- Round 123's Q1 (tli edit raises gte-near to >=3/6 fired-gte) is confirmed MISS by the surviving
  partial after-log (`round-123-haiku-gte-tli-after.log`: gte-near still 0/6 gte across 6 probes)
  and round 129's independent same-day rerun (1/6, within noise of 0).
- This round's job: execute round 129's ONE still-untested hypothesis -- tli's own first clause
  contains the literal phrase "tree-walking evaluator", which also appears verbatim in gte-near's
  prompt wording ("My Python tree-walking interpreter... restructure the evaluator"). No prior edit
  (105 gte rewrite, 111 gte rewrite, 123 tli NOT-for, 129 banked-but-never-run) has touched this
  specific shared noun. Edit: drop "tree-walking" from tli's opening parenthetical (keep
  "lexer -> parser -> evaluator"), nothing else, then re-probe haiku x6 on the same 7-case subset
  (gte-near/mid/far, tli-near/mid/far, multi-2) with --baseline against round-123's before-edit
  json, plus a sonnet x1 regression check on the same subset.

| id | prediction (band + mechanism) |
|---|---|
| S1 | gte-near on haiku moves from 0/6 to at most 1-2/6 fired-gte (a small, inconclusive bump, not a flip) -- 4 description edits across 3 skills over 4 rounds with zero haiku movement on this exact case is strong prior evidence the failure is a small-model selection-noise property of "tree-walking interpreter" reading as tli's whole domain, not a single removable keyword. |
| S2 | tli-near/mid/far on haiku stay >=5/6 fired-tli each (no regression from trimming its own first clause -- the phrase "lexer -> parser -> evaluator" still reads as an interpreter-building trigger without the extra adjective). |
| S3 | gte-mid and gte-far do NOT improve (stay <=3/6 and <=1/6 fired-gte respectively) -- their dominant competitors are fuzz-mutate-kill-loop/subprocess-cli-testing vocabulary ("kill-stage", "crash", CLI testing), unrelated to tli or the word "tree-walking". |
| S4 | multi-2 stays 0/6 exact (fmk-dominated, unaffected by a tli-only edit). |
| S5 | Sonnet x1 on the 7-case subset stays 7/7 exact (no regression at the strong-model tier from a one-word trim). |
| S6 | Given S1 (no flip), this round's honest conclusion is FINAL for this specific case: stop editing tli/gte descriptions to chase haiku gte-near -- 5 distinct edits (105, 111 x2, 123, 129-this-round) across two skills over 5 rounds with the metric never leaving 0-1/6 is enough evidence to close it as a small-model base-rate property and redirect future skills-round effort elsewhere (the cml/acg native-probe gap this round's audit ALSO closes is the more productive use of the same probe budget). |
| S7 | Offline suite stays green (141 tests unless a genuine v4.x feature is added this round, which is not planned -- 0 new evaluator tests expected, this is a measurement + 1-line content edit round). `skill_lint --house --strict` stays clean (15 skills). |
| S8 | Total live cost for the new probe set (42 haiku + 7 sonnet = 49 probes): $2-4, 0-2 errors. |
