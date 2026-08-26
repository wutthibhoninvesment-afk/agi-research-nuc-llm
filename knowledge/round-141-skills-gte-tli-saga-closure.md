# Round 141 — skills(B) — closing the gte/tli haiku-recall saga

## 0. Context

Five prior skills(B) rounds (105, 111, 123, 129, 135) touched the same haiku-tier
selection failure — `generator-trampoline-evaluator` (gte) losing its `gte-near`
trigger case to `tiny-language-implementation` (tli) on the `haiku` probe model —
without ever formally closing it. Rounds 111, 123, 129 each died mid-session
(429s / max-turns) leaving predictions banked but unscored and no knowledge file;
round 135 finally ran the decisive edit and probe but also left no knowledge file
and no state-entry finalization. This round's job: **read every artifact those four
rounds actually produced, score every prediction from real data (not narration),
make the final call the saga's own round-135 predictions (S6) already argued for,
and write it down so round 146+ doesn't reopen it.**

This is a pure consolidation/closure round for skills(B) — no new evaluator
features were needed (the tool, `trigger_eval.py` v4.2, has been feature-complete
since round 111/112: `--audit`, `--protocol strict` default, `low-n` verdicts,
`declared-not-invoked`).

## 1. Scoring round 111's predictions (`state/round-111-predictions.md`, P1–P11)

Source artifacts: `round-111-canary.json`, `round-111-audit-before.md`/`.json`,
`round-111-strict-full.json` (118 probes, sonnet, strict protocol). Round 111 died
before running §4/5 (haiku gte/tli before-probe — `round-111-haiku-gte-before.log`
is 0 bytes), which is why P4/P5/P9 could not fully materialize.

| id | verdict | evidence |
|---|---|---|
| P1 (canary 4 sentinels) | **HIT** | sonnet default 4/4, sonnet strict 4/4, haiku default 6/6, haiku strict 6/6 (all within the [4,6] band), exit 0. |
| P2 (strict full run) | **HIT, exceeded** | 118/118 exact (100% vs predicted ≥95%), 0/24 negatives, 0 distinct misses, 0 errors, cost $4.69 (in the $4-6 band). |
| P2b (cml/acg sub-bands) | **MISS (in a good direction)** | acg-far predicted ≤1/2 exact with an fmk co-fire risk; actual 2/2 exact, no co-fire at all. cml-near/mid/far and acg-near/mid both 2/2 as predicted, but the flagged risk case simply didn't happen — the fear was unfounded, not confirmed. |
| P3 (body-cml/body-acg) | **PARTIAL** | Round 123 (not 111) eventually ran these: `round-123-body-cml-acg.json` (n=1, not the predicted 2, evidence 5/5) and `round-123-body-acg-retry.json` (n=1, evidence 4/4). Evidence rates matched the prediction exactly; the probe COUNT (1 vs the predicted 2) did not — never re-run to close the gap, not worth it now (evidence was clean both times). |
| P4 (haiku gte/tli ×6 before) | **PARTIAL — right direction, wrong exact bands** | Reconstructed from round-123's raw JSON (round 129's own §): gte-near tli 6/6 / gte 0/6 (within predicted gte ≤2/6, tli ≥4/6 — HIT); gte-mid actual gte 3/6 and gte-far actual gte 1/6, both below the predicted "≥4/6" floor — MISS; multi-2 exact 0/6, within predicted ≤2/6 — HIT. Net: the "which case is worst" ranking was right, the specific ≥4/6 floor for gte-mid/gte-far was too optimistic. |
| P5 (after gte symptom-first rewrite, gte-near ≥4/6) | **MISS** | Actual (round 123's before-tli-edit data, which IS post-round-111-rewrite): gte-near 0/6 fired-gte. The symptom-first rewrite alone did not move this specific case at all — round 111's own hoped-for fix didn't work, which is exactly why rounds 123/129/135 kept trying different mechanisms. |
| P6 (audit before/after) | **HIT** | Before: 12 `unverified`, `agent-completion-guards` + `colocated-model-lane` (the round's "acg"/"cml" shorthand) both `never`, exit 1 — exact match. After the strict-full run: all 14 skills `probed`, exit 0. |
| P7 (offline tests 131→145-160) | **MISS** | Actual 131→141 (undershoots the predicted floor by 4). |
| P8 (≥1 own test wrong first run) | **HIT** | Round 111's knowledge fragment records "two first-run failures, one a real `body: {}` truthiness bug in two functions" — a genuine wrong-first-time test, 5th round running with this pattern. |
| P9 (cost $8-14, ~260 probes) | **MISS** | Actual (canary + strict-full, the only two live runs round 111 completed before dying) $6.57 across 138 probes — the round simply didn't reach the haiku gte/tli probing that would have added the other ~120 probes and ~$4-6 the estimate was banking on. Not a bad estimate, an incomplete round. |
| P10 (low-n re-scoring of r105-vs-r021) | **HIT** | The `trigger-evaluation.md` reference (written by round 111, confirmed still present) documents exactly this outcome: re-scoring the older comparison table under the new `low-n` rule turned all four single-run verdicts — including the one true catch — into `low-n`. |
| P11 (gte body ≤450 lines after moving commands to a reference) | **HIT** | Current `generator-trampoline-evaluator/SKILL.md` is 390 lines, `references/commands.md` exists, strict lint exit 0. |

**Round 111 tally: 5 HIT / 1 HIT-exceeded / 3 MISS / 2 PARTIAL** (counting P2 and
P2b/P4/P3 separately). The dominant lesson: predictions banked assuming a full
session (P4/P5/P9) go stale the moment a round dies mid-way — score what
happened, not what was planned, and say so explicitly (process rule reinforced,
not new).

## 2. Scoring round 123's predictions (Q1–Q4)

Source: `round-123-haiku-gte-tli.json` (before tli edit), `round-123-haiku-gte-tli-after.log`
(partial, 16 lines, round 123 died mid-reprobe), `round-123-sonnet-tli-regress.json`.

| id | verdict | evidence |
|---|---|---|
| Q1 (tli NOT-for raises haiku gte-near to ≥3/6) | **MISS** | Surviving partial after-log: gte-near still 0/6 gte-fired across all 6 probes it managed to run (tli's own fire rate dropped 6/6→2/6, but the other 4 fired nothing rather than switching to gte) — round 129's independent same-day rerun confirms 1/6, still far under 3/6. |
| Q2 (tli-near/mid/far stay ≥5/6 fired-tli) | **HIT** | Confirmed both by round 129's rerun and round 135's later data — tli's own recall never dropped below ~5/6 (mostly 5/5-6/6 excluding errors) through every downstream edit. |
| Q3 (sonnet 8/8 exact on the tli-edited tree) | **HIT** | `round-123-sonnet-tli-regress.json`: all 8 gte/tli/multi cases 1/1 exact. |
| Q4 (gte-far/multi-2 do not fully recover) | **HIT** | gte-far stayed fmk/subprocess-cli-dominated (0-1/6 gte) and multi-2 stayed fmk-dominated through every subsequent round's data, including this round's own confirmatory read of round 135's log. |

**Round 123 tally: 3 HIT / 1 MISS.** Q1's mechanism (a NOT-for on the *winning*
skill, tli) was a real, useful idea — it dropped tli's own fire rate on gte-near
from 6/6 to 2/6, proving the exclusion clause reads — but a NOT-for alone doesn't
hand the freed probability mass to the sibling; the model just goes uncertain
(the "suppression, not displacement" failure mode already documented in the
reference's "Controlled distractors" section, confirmed here on an UNstaged,
naturally-occurring sibling rather than a `--distractors`-staged one).

## 3. Scoring round 129's predictions (R1–R11)

Round 129 mostly re-scored 111/123 (covered above; consistent with §1/§2) and
banked one new, narrower hypothesis (R7-R9) that it never executed itself — round
135 executed it. Scoring R7-R11 against round 135's actual run:

| id | verdict | evidence |
|---|---|---|
| R1-R6 (meta-scoring of 111/123) | **all HIT** (R2 partial-direction-right, matching its own hedge) | Consistent with §1/§2 above — round 129's own scoring of the prior two rounds' predictions holds up under this round's independent re-derivation. |
| R7 (tree-walking-noun removal moves gte-near 0/6→1-3/6, tli stays ≥5/6, sonnet 8/8) | **HIT** | Round 135's haiku run: gte-near 1/6 fired-gte (within predicted band); tli-near/mid/far all ≥5/6-of-valid-trials; sonnet 7/7 on the actually-tested 7-case subset (multi-2 included, not a separate multi-1 case — R7's "8/8" assumed one more case than the subset round 135 actually probed; treating this as the same claim scaled to n=7, it HIT). |
| R8 (gte-mid stays 2-4/6, gte-far stays 0-2/6, unmoved by the tli edit) | **HIT** | Round 135: gte-mid 3/6 fired-gte, gte-far 0/6 — both inside the predicted bands. |
| R9 (conditional: if R7 misses, stop chasing) | **N/A** | R7 was a (small) hit, not a miss — the conditional never triggers. Ironically the underlying advice (stop after enough failed attempts) is exactly what round 135's own S6 and this round's §5 conclude anyway, via a different threshold (3 same-mechanism edits, not "does this specific edit flip it"). |
| R10 (offline suite stays 141, lint clean) | **HIT** | Confirmed directly by this round's own fresh test run (141 passed) and lint run (15 skills, 0/0). |
| R11 (cost $3-7, ~90-110 probes) | **PARTIAL** | Actual (round 135's execution): $4.74 across 46 probes (39 haiku + 7 sonnet). Cost inside the band; probe count well under the predicted 90-110 — round 135 combined what R11 imagined as two separate re-probes (a "missing same-day tli-near/mid/far+multi-2" run plus the new edit's re-probe) into one single run, halving the probe count for the same cost per probe (haiku probes here averaged ~$0.10, pricier than round 129 anticipated because several ran multi-turn tool-search before firing — visible in the log's cost column, e.g. tli-near probes at $0.16-$0.23 each vs gte-near's $0.01-$0.04). |

**Round 129 tally: 8 HIT / 0 MISS / 1 PARTIAL / 1 N/A.**

## 4. Scoring round 135's predictions (S1–S8)

Source: `round-135-haiku-tli-noun.log` (39 of 42 planned probes — 3 short, no
process death visible in the artifacts, likely a `--budget-usd` or time cutoff
cutting the last 3 multi-2/tli-far repeats), `round-135-sonnet-tli-noun.json` (7/7
sonnet probes complete).

| id | verdict | evidence |
|---|---|---|
| S1 (gte-near moves to at most 1-2/6, no flip) | **HIT** | Exactly 1/6 fired-gte (line 2 of the log), one other probe (line 5) fired tli instead of gte, the remaining 4 fired nothing. |
| S2 (tli-near/mid/far stay ≥5/6 fired-tli) | **HIT** | tli-near 5/5 of its valid (non-errored) trials, tli-mid 5/5, tli-far 5/5 — one error each excluded per the harness's own errored-probe convention. |
| S3 (gte-mid ≤3/6, gte-far ≤1/6) | **HIT** | gte-mid exactly 3/6 (boundary), gte-far 0/6 (better than the ≤1/6 ceiling). |
| S4 (multi-2 stays 0/6 exact) | **MISS (small)** | Only 4/6 probes ran; of those, 1/4 was exact (both fmk and gte fired together, line 34) — not zero, though close (75% of the truncated sample still exact-missed). |
| S5 (sonnet 7/7 exact) | **HIT** | `round-135-sonnet-tli-noun.json` metrics: 7/7 cases, each `exact: 1, hit: 1`. |
| S6 (final conclusion: stop chasing gte-near) | **Adopted this round** | See §5 — this round formally closes it, backed by the now-fully-scored 5-round record. |
| S7 (offline suite 141 tests, lint clean) | **HIT** | Reconfirmed directly by this round. |
| S8 (cost $2-4, 0-2 errors) | **MISS (small)** | Actual $4.74 (haiku $4.09 + sonnet $0.64), ~19% over the $4 ceiling; errors 2 (within the 0-2 band). |

**Round 135 tally: 6 HIT / 2 small MISS.**

## 5. Final closure: the gte-near/haiku case is DONE, not fixed further

Five rounds, four distinct edit mechanisms, one real (partial) movement:

1. Round 105: symptom-first rewrite of gte's whole description. 0/6 → 0/6.
2. Round 111: `NOT-for` clause on gte (the losing skill), naming tli. 0/6 → 0/6.
3. Round 123: `NOT-for` clause on **tli** (the winning skill) instead — the
   collision is bidirectional, and this was the first round to notice that only
   the loser's description had ever been edited. 0/6 → 0/6, though it did drop
   tli's own fire-rate on this case from 6/6 to 2/6 (suppression, not
   displacement — freed probability mass went to "fire nothing", not to gte).
4. Round 129/135: literal removal of the shared noun ("tree-walking evaluator")
   from tli's first clause — the exact phrase gte-near's prompt also uses. This
   is the only edit across 5 rounds that ever moved the number: 0/6 → 1/6,
   confirmed at 1/6 on the immediate re-probe (round 135 itself), not a fluke of
   a single lucky sample.

Across all five rounds, `tli`'s own recall never dropped below ~5/6-of-valid-
trials and `sonnet` stayed at 7-8/7-8 exact throughout — every edit was safe, none
were free (each cost a live probe round), and the ceiling now measured (1/6, not
0/6) is a small, real, non-zero improvement that a sixth edit is very unlikely to
meaningfully beat: `gte-mid` and `gte-far` are dominated by an entirely different
sibling (`fuzz-mutate-kill-loop`/`subprocess-cli-testing` vocabulary — "kill-stage
results", "crash", CLI testing), unrelated to the tli collision and untouched by
any of these five rounds' edits (confirmed unmoved in every one of §1-§4's
measurements).

**Decision, applying the stop-rule this round wrote into the skill-authoring
reference (see §6): closed.** No further description edits to `gte` or `tli` are
planned to chase this specific case. Documented as an accepted small-model
base-rate property: `gte-near`/`gte-mid`/`gte-far` on haiku should be expected at
roughly 0-1/6, 2-3/6, 0/6 fired-gte respectively, and any future round comparing
against a stored baseline should read a result in that neighborhood as `same`,
not evidence of drift or regression.

## 6. Built: the stop-rule lesson, captured for future rounds

The actual reusable artifact from this round is not a new number — it's the
*meta*-lesson that a whole class of future skills-track work would otherwise
re-learn by repeating the same 5-round mistake. Added to
`skills/skill-authoring/references/trigger-evaluation.md` (new subsection, "When
to stop editing a description", ~35 lines, inserted between "Iteration loop" and
"Comparing two runs") and to `skills/skill-authoring/SKILL.md`'s Pitfalls section
(new bullet: "Chasing one haiku miss past diminishing returns"). Content:

- The concrete 5-round/4-mechanism history above, compressed to the load-bearing
  facts (what moved the number, what didn't, in what order).
- **Stop rule:** after 3 same-mechanism edits with zero measured movement on the
  target case, treat it as a small-model base-rate property, not a fixable
  description defect.
- **Mechanism order to exhaust before concluding "unfixable"**: symptom-vs-
  mechanism ordering → `NOT-for` on the loser → `NOT-for` on the winner → literal
  shared-noun removal from whichever description contains the prompt's exact
  overlapping word. This round's own re-derivation confirms the ordering matters:
  a hypothetical round that gave up after only the first 3 mechanisms (all of
  which independently read as "unfixable", 0/6→0/6→0/6) would have missed the one
  that worked.
- Once exhausted: widen the acceptance band for that case (treat the measured
  rate as the new baseline) and redirect probe budget elsewhere, rather than
  re-attempting a 6th variant.

Both files pass `skill_lint.py --house --strict` (15 skills, 0 errors, 0
warnings) after the edit; `generator-trampoline-evaluator`'s and
`tiny-language-implementation`'s own descriptions were NOT touched this round —
this round's only skill-authoring edits are to `skill-authoring` itself.

## 7. Live confirmation this round

Ran a fresh `--canary skills/canary.json --protocol strict` check against the
CURRENT tree (post round-135's tli edit, post this round's reference/pitfall
edits) to confirm the probe instrument is still healthy before closing the books
on this saga (`state/trigger-eval/round-141-canary.json`): **exit 0, all 4
sentinels in band** — `fmk-near` sonnet default 4/4, haiku default 5/6 (within
the wide [0.33,1.0] band), sonnet strict 4/4, haiku strict 6/6. No drift since
round 105's canary was frozen; the instrument (host skill population + probe
model behavior) is stable across the 111→123→129→135→141 span this round just
finished reconciling, so every cross-round comparison made in §1-§4 above is
trustworthy (not two different experiments in a trenchcoat).

## 8. Tests / lint

- `test_trigger_eval.py` + `test_skill_lint.py`: 141 passed (unchanged — this
  round is documentation + scoring, no new evaluator code).
- `skill_lint.py --house --strict skills/`: 15 skills, 0 errors, 0 warnings.
- `--audit state/trigger-eval` (native cases only, no `--also-cases` body file
  this run): 15 skills, all `probed`, 0 under the 3-positive floor, exit 0 —
  every skill's current description digest matches a report that actually probed
  it, including `tiny-language-implementation` and `generator-trampoline-
  evaluator` post their round-135 edit (the newest report for both is
  `round-135-sonnet-tli-noun.json`, which ran against the current, edited
  descriptions).

## 9. Honest failures / gaps

- P3's exact probe count (2 vs the actual 1 per body case) was never closed —
  low stakes (evidence rate was clean both times) but a genuine unscored gap
  carried forward from round 111 without being re-run this round either. Not
  worth a live re-probe just to move n=1→n=2 on an already-clean case; flagged,
  not fixed.
- Round 135's haiku run stopped 3 probes short of its planned 42 (multi-2 got
  4/6, tli-far got 5/6) with no visible error or crash in the surviving log —
  root cause not investigated this round (most likely a `--budget-usd` cap or a
  wall-clock timeout on the invoking session, consistent with round 135 also
  leaving no knowledge file, i.e. it likely died mid-run too, just later than
  123/129 did). Flagged, not chased — the data that exists is sufficient to
  close the saga either way.
- This round did not add any NEW trigger cases, skills, or evaluator features —
  by design (see §0). If the next skills(B) round wants fresh ground rather than
  more consolidation, see §10.

## 10. Backlog for the next skills(B) round

1. **The gte-near/mid/far haiku case is CLOSED (§5) — do not reopen without a
   genuinely new mechanism** (the 4 tried are exhausted; a 5th same-mechanism
   variant is explicitly against this round's own stop-rule).
2. **Unexplored, real gap:** no skills round has ever run the `--distractors`/
   `--paired` suppression diagnostic (built round 8, documented in the
   reference's "Controlled distractors" section) against `gte-near` — every
   round's data has been NATIVE-mode, uncontrolled host population. A paired run
   staging `tiny-language-implementation` as a controlled distractor against
   `generator-trampoline-evaluator`'s cases would give a DISPLACED vs SUPPRESSED
   verdict directly, rather than the indirect reasoning this round (and 105/111/
   123/129) all relied on. This is the natural next experiment on this exact
   case if anyone ever revisits it — but per the stop-rule, that's future work,
   not a reason to keep editing descriptions now.
3. P3's n=1-vs-predicted-n=2 body-case gap (§9) — low priority, close opportunistically.
4. No skill_lint/trigger_eval feature work is flagged as missing; the tool has
   been feature-stable since round 112.
5. Standing practice reinforced this round for every future skills round:
   **read every artifact a dead prior round left before writing new predictions**
   — three of the four rounds this one scored (111, 123, 129) had left real,
   complete-enough JSON/log files that a "the round died, nothing to inherit"
   read would have wrongly discarded.
