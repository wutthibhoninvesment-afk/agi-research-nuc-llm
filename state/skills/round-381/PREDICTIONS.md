# Round 381 (skills B) — PREDICTIONS (D-013)

Banked 2026-08-30, BEFORE the measurements below. Registered in
`state/prediction-bank-ledger.json` in the same turn (K001).

**Honest scope note, written before scoring.** The first measurement of this
round — the 87-probe batch over the six never-probed skills
(`state/trigger-eval/round-381-batch.json`) — ran *without* a banked
prediction. That is a D-013 miss by this round and it is scored as one in
P0 below rather than hidden. Everything from the batch onward is banked
here first. The batch's headline numbers are quoted in P1–P4 as *given*,
not predicted.

| # | prediction | band |
|---|---|---|
| P0 | this round breaks D-013 once, on the batch itself, and says so | self-scoring: HIT only if the knowledge file names it |
| P1 | **isolation test.** With ONLY `skills/lazy-fill-ceiling` staged (no siblings at all), `lfc-near` fires ≥ 2/3 | fires ≥2 of 3 |
| P2 | in the same isolation run, `lfc-mid` fires ≥ 2/3 — its prompt ("scaled it linearly to pick 204") is a near-verbatim symptom in the description | fires ≥2 of 3 |
| P3 | in isolation, **at least 3 of the 4** lfc positives reach ≥ 2/3. If this is false the description does not match its own cases and the fix is a rewrite, not a de-confliction | ≥3 of 4 cases |
| P4 | **the false-fire finding replicates across history.** Over every committed report in `state/trigger-eval/`, `measured-budget-sizing` — recall 0/3 on its own cases across two draws, carried in `known-weak-probes.json` as a known-bad description — has ≥ 1 false fire on ANOTHER skill's case in at least one report OTHER than round 381's | ≥1 fp in ≥1 prior report |
| P5 | across all committed reports, the skill with the most false fires is NOT the skill with the worst recall, i.e. the two rankings disagree at the top | top-1 differs |
| P6 | after the `lazy-fill-ceiling` description edit, a full-corpus re-probe of its 4 positives at n=3 yields ≥ 8/12 fires (from 0/12) | ≥8 of 12 |
| P7 | the same re-probe keeps both lfc negatives at 0 false fires (6 runs) | 0/6 |
| P8 | the same re-probe shows ≥ 1 sibling REGRESSION on a case that was clean at n=3 in the batch — de-confliction is not free | ≥1 regressed case |
| P9 | `measured-budget-sizing`'s false fires DROP after the edit (it currently takes 4 of the 12 lfc runs) | ≤2 of 12 |
| P10 | the six P006 re-probes (whole case sets) will show **≥ 2 skills** whose full set fires worse than the single case their `probed` status was asserted from | ≥2 skills |
| P11 | ≥ 1 of my own new tests / checks is wrong on first run, and I name it | ≥1, named |
| P12 | `bash skills/run_checks_fast.sh` ends this round at 0 errors, and the corpus-wide warning count is ≤ 7 (it is 7 now; discharging P004 for 6 skills should cut it, adding weak-probe entries should not raise it) | 0 errors, ≤7 warnings |
| P13 | total probe spend for the whole round ≤ $9 | ≤ $9 |

## Amendment, banked after P1–P3 were measured (12/12 in isolation vs 0/12 in corpus)

The isolation control is decisive and nobody in this program has ever run
one. `state/known-weak-probes.json` carries TWO skills adjudicated as
*known-bad descriptions* on the strength of a 0/3 that was never controlled
this way: `measured-budget-sizing` (0/3 twice, across a description edit)
and `obligation-ledger` (1/3 then 0/3 after an edit). Banked before running:

| # | prediction | band |
|---|---|---|
| P14 | `measured-budget-sizing` staged ALONE fires ≥ 2/3 on at least 2 of its 3 positives — i.e. the "known-bad description" verdict is an artifact of the corpus, not a property of the text | ≥2 of 3 cases at ≥2/3 |
| P15 | `obligation-ledger` staged ALONE likewise reaches ≥ 2/3 on at least 2 of its 3 positives | ≥2 of 3 cases at ≥2/3 |
| P16 | at least one of P14/P15 is FALSE — I expect the isolation result to split, because round 369 edited both descriptions and one of them plausibly is genuinely weak | ≥1 of P14/P15 false |

## Amendment 2, banked after P14/P15 (both 9/9 in isolation; P16 already MISS)

Three skills, 30 isolation probes, 30/30. The question is now the
MECHANISM: specific sibling overlap, or crowd size. Dose–response arms,
all `lazy-fill-ceiling` positives at n=3:

| # | prediction | band |
|---|---|---|
| P17 | **arm C** (lfc + the only two skills ever observed firing on an lfc case: `measured-budget-sizing`, `zero-rate-needs-a-distance`) — lfc still wins ≥ 8/12. If overlap were the mechanism, THIS is where it should break | ≥8 of 12 |
| P18 | **arm E** (lfc + 19 siblings, ~half the corpus) — lfc fires between 1 and 9 of 12, i.e. degraded but not extinguished; the effect is graded in crowd size, not a cliff at a particular sibling | 1–9 of 12 |
| P19 | across arms A(1 skill) → C(3) → E(20) → D(41), the fire count is MONOTONICALLY non-increasing | monotone |

## Amendment 3, banked after arm E (12/12 at 20 skills — P18 already MISS)

Arms A(1), C(3) and E(20) are all 12/12; arm D(41) is 0/12. The cliff is
between 20 and 41 staged skills, or it is a specific suppressor living in
the alphabetical second half (arm E took the first 19 siblings).

| # | prediction | band |
|---|---|---|
| P20 | **arm F** = lfc + the 21 siblings arm E did NOT stage. If a specific suppressor exists it is here, so I predict arm F fires ≤ 4/12 | ≤4 of 12 |
| P21 | if arm F is instead ≥ 8/12, the effect is SIZE and neither half contains a suppressor — the two half-corpora each let it through and only the union kills it | conditional, scored as stated |

## Amendment 4, banked after arm F (11/12 at 22 skills — P20 MISS, P21 HIT)

Arm E (20 skills, alphabetical first half) 12/12 and arm F (22 skills,
second half) 11/12. Neither half contains a suppressor; only the union of
41 extinguishes it. Two controls left:

| # | prediction | band |
|---|---|---|
| P22 | **arm D', the control that matters.** Re-run the FULL 41-skill corpus on the 4 lfc cases ALONE at n=3 (the batch ran 29 cases in one invocation; the arms ran 4). If the 0/12 is real and not an artifact of the batch's shape, this reproduces at ≤ 2/12 | ≤2 of 12 |
| P23 | **arm G** = lfc + 30 siblings (bisecting 22 → 41). Graded, not a cliff: fires ≥ 1 and ≤ 11 of 12 | 1–11 of 12 |

## Amendment 5, banked after arm D' (12/12 — P22 MISS, and the finding inverted)

Arm D' re-ran the FULL 41-skill corpus on the 4 lfc cases alone and got
**12/12**, against the batch's 0/12 with a byte-identical `available` list
of 89 skills (verified from both reports). The staged catalog is NOT the
variable. The only differences between the two invocations are `--only`
(29 ids vs 4) and `--transcripts`. So the suppression tracks the BATCH
SHAPE, not the corpus — or the instrument has run-level nondeterminism
nobody has measured.

| # | prediction | band |
|---|---|---|
| P24 | **arm H** — the batch's exact 29-case `--only` set, full corpus, at `--repeats 1`. If the batch shape is causal, the 4 lfc positives fire ≤ 1 of 4 | ≤1 of 4 |
| P25 | in the same arm H, the `turns == 1` (declared-or-nothing, no Skill call) fraction is ≥ 30% of probes, matching the batch's 36/87 = 41% and unlike every 4-case arm (0–8%) | ≥30% |
| P26 | if P24 is false (lfc fires ≥ 3 of 4 in arm H), then the instrument's run-level variance is the finding, and NO description edit is warranted this round | conditional |

## Amendment 6, banked after arm H (lfc 4/4 — P24 MISS, P25 HIT, P26 triggered)

The batch's 0/12 did not replicate in TWO independent re-runs of the same
configuration (arm D' 12/12 at n=3, arm H 4/4 at n=1, both at the full
41-skill corpus). The finding is now the INSTRUMENT, not the description.
One effect DID replicate: the `turns == 1` rate (a bare `SKILLS=` line with
no Skill call) is 41% in the batch and 34% in arm H, against 0–8% in every
4-case arm.

Arm J re-probes, at the FULL corpus and n=3, the own-cases of the two
skills `state/known-weak-probes.json` adjudicates as KNOWN-BAD DESCRIPTIONS
(`measured-budget-sizing` 0/3 twice, `obligation-ledger` 1/3 then 0/3),
plus the 4 lfc cases a third time.

| # | prediction | band |
|---|---|---|
| P27 | `measured-budget-sizing` fires ≥ 5/9 on its own cases at the full corpus — the "known-bad description" verdict does not survive a third draw | ≥5 of 9 |
| P28 | `obligation-ledger` likewise ≥ 5/9 | ≥5 of 9 |
| P29 | lfc's third full-corpus draw is ≥ 8/12, making the batch's 0/12 a 1-in-3 outlier rather than the modal result | ≥8 of 12 |
| P30 | at least one of the three skills lands strictly between 2/9 and 7/9, i.e. the true rate is intermediate and NEITHER 0/3 nor 3/3 was ever a measurement | ≥1 intermediate |

## Amendment 7, banked before the new skill's probes

`skills/rerun-before-you-record` is authored with 4 positives and 2
negatives. It is probed TWICE — two independent runs of an identical
configuration, which is the skill's own step 2 applied to itself, and the
first skill in this corpus ever probed that way on purpose.

| # | prediction | band |
|---|---|---|
| P31 | run 1 and run 2 DISAGREE on at least one case at majority level — the corpus-wide rate is 24 of 41, so a 6-case pair disagreeing on ≥1 is the modal outcome | ≥1 case |
| P32 | pooled over both runs, the 4 positives fire ≥ 16 of 24 | ≥16 of 24 |
| P33 | `rbr-neg-determ` (a deterministic static linter) draws 0 false fires across both runs — it is the nearest wrong answer and the description names it | 0 of 6 |
| P34 | `rbr-far2` ("we edited it and the second run was bad too") is the WEAKEST positive, because it reads as a decision-to-abandon question | lowest of the 4 |
