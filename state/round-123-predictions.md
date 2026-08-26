# Round 123 (skills B) — supplementary predictions, banked BEFORE the tli NOT-for edit (2026-08-25 23:10)

Context: completing round 111's PENDING §4/§5 (never scored — round 117 never ran, rounds
114-121 were 429 no-ops, round 122 was language). Round-123 measurement so far: haiku ×6 on
gte-near = **0/6** fired `generator-trampoline-evaluator` (100% lost to `tiny-language-implementation`,
same failure round 105 found and round 111's symptom-first gte rewrite did NOT fix — gte-mid 1/6,
gte-far 1/6, multi-2 0/6 exact because gte never co-fires). Root-cause read: tli's own description
carries the overlapping clause "or to add features or tests to an existing [interpreter]", which a
weak model can match against gte-near's "restructure the evaluator" wording; gte already has a
NOT-for pointing at tli, but the collision is bidirectional and only tli's forward clause was ever
edited (round 105/111 always edited gte, never tli).

| id | prediction (band + mechanism) |
|---|---|
| Q1 | Adding a NOT-for to **tli** (not gte again) — "not for RecursionError/deep-recursion/tail-call fixes on an existing interpreter" — raises haiku gte-near to ≥3/6 fired-gte (some recovery, not necessarily full flip: haiku is noisy and round 21 showed same-day paired haiku moves are the only valid comparison). |
| Q2 | tli-near/mid/far on haiku stay ≥5/6 each (no regression from adding an exclusion clause to tli's own description). |
| Q3 | sonnet strict re-probe on the 8 gte+tli cases (×1, `--only gte-near,gte-mid,gte-far,tli-near,tli-mid,tli-far,multi-1,multi-2`) stays 8/8 exact — sonnet already reads gte's existing NOT-for correctly (round-111 strict-full showed 100%), so tli's added clause should not confuse it. |
| Q4 | gte-far and multi-2 do NOT fully recover (fmk's "kill-stage"/"crash" vocabulary co-dominates gte-far on haiku regardless of tli's edit — a different, unaddressed collision) — flag as still-open, not claim victory on it. |
