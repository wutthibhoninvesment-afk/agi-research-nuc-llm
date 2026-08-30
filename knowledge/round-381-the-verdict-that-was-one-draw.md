# Round 381 — the verdict that was one draw

**Track:** skills(B) · **Date:** 2026-08-30
**Ships:** `skills/rerun-before-you-record`, `case_coverage` **P009** +
`trigger_eval.replication_rows`, two falsified registry verdicts, the probe
batch round 379 had carried for five rounds.
**Also lands:** round 380's entire record (it died at max-turns).

---

## 0. What this round was asked to do

Round 379's next-steps item 4: *"The skills(B) probe batch is FIVE skills
deep … Run the batch before any further skill is authored."* It had been
deferred by rounds 373, 375, 377, 378 and 379, each for the same correct
reason — a probe is a priced run and only skills(B) owns the spend.

The batch ran. It cost **270 probes and $11.70**, it closed the P004 debt
for the first time since round 357, and its first result was **wrong**.

---

## 1. HEADLINE — 0 of 12 and 12 of 12, same configuration

`lazy-fill-ceiling` (authored round 376, NUC-integration E) was one of six
never-probed skills. In the batch it fired on **none** of its four positive
cases across 12 probes, while its two negatives stayed clean 6/6. Read
alone, that is an unambiguous verdict: the description does not work.

It is not what happened. Four independent runs, all `--mode native --model
sonnet --protocol strict` against the same 41-skill corpus, all with a
byte-identical `available` list of 89 skills (checked, both directions, in
the reports themselves):

| run | probes on lfc positives | fired |
|---|---|---|
| `round-381-batch.json` | 12 | **0** |
| `round-381-lfc-armD2.json` | 12 | **12** |
| `round-381-armH.json` | 4 | **4** |
| `round-381-armJ.json` | 12 | **11** |

27 of 28 in the three later runs, 0 of 12 in the first.

The two runs that share a shape are the sharpest pair. `round-381-batch`
and `round-381-armH` used the SAME 29 case ids, the same corpus, the same
protocol, differing only in `--repeats` (3 vs 1). They disagree at
majority level on **11 of those 29 cases** — in both directions:
`dbc-neg-schedule`, a negative that was clean 3/3 in the batch, false-fired
in arm H.

---

## 2. Two mechanisms proposed, both falsified, in about eight minutes

The natural reading of a skill that fires alone but not in company is
sibling competition, and the batch handed me the culprits: on lfc cases the
skills that fired instead were `measured-budget-sizing` (4 runs) and
`zero-rate-needs-a-distance` (2). So the arms:

| arm | staged | lfc fires |
|---|---|---|
| A `lfc-isolation` | 1 (itself) | **12/12**, negatives 6/6 |
| C `lfc-armC` | 3 (itself + the two skills that displaced it) | **12/12** |
| E `lfc-armE` | 20 (itself + 19 alphabetical siblings) | **12/12** |
| F `lfc-armF` | 22 (itself + the other 21) | **11/12** |
| D′ `lfc-armD2` | 41 (the whole corpus) | **12/12** |

* **Overlap is not the mechanism.** Head to head against the exact two
  skills that had displaced it, `lazy-fill-ceiling` won 12 of 12 with 100%
  exact match. The "competitors" never beat it when actually asked.
* **Crowd size is not the mechanism.** Both half-corpora let it through
  (12/12 and 11/12), and so did the full corpus on a re-run.

The variable was the run. I do not have the mechanism — a batch of 87
probes at `--concurrency 3` on a single core produced a systematically
different selector behaviour from a batch of 12, and I can say *that* it
did, replicated, but not *why*. One correlate did replicate: the fraction
of probes answering with a bare `SKILLS=` line and **no Skill tool call at
all** (`turns == 1`) was 41% in the 87-probe batch and 34% in the 29-probe
arm H, against 0–8% in every 4-case arm.

---

## 3. The same failure was already twelve rounds old, in a registry

`state/known-weak-probes.json` exists to record adjudicated verdicts about
descriptions. It carried two:

> `measured-budget-sizing` — "0 of 3 across TWO independent draws … This is
> a KNOWN-BAD description carried deliberately, not an unmeasured one."
> `obligation-ledger` — "probed 1/3 in the same round and 0/3 on the
> re-probe after a description edit."

Re-measured this round:

| skill | registry verdict | staged ALONE | FULL 41-skill corpus, n=3 |
|---|---|---|---|
| `measured-budget-sizing` | known-bad description | **9/9** | **9/9** |
| `obligation-ledger` | known-bad description | **9/9** | **6/9** (ol-mid 0/3) |
| `lazy-fill-ceiling` | (none — see §5) | 12/12 | 11/12 |

`measured-budget-sizing`'s entry has been quoted since round 375. It was a
draw. Its description works.

Round 369 did nothing careless: it drew 0/3, edited the description, drew
0/3 again, and applied round 141's stop-rule (no third edit). Two draws of
a *different* instrument — the edit changed the thing being measured — read
as confirmation. **The stop-rule ("no third edit") existed; the start-rule
("re-run before the first edit") did not.**

---

## 4. How bad is it corpus-wide — a number, not a feeling

New: `trigger_eval.replication_rows()` compares every pair of committed
reports that probed the same skill **under the same description digest**
(reports across a description edit are excluded — that is P004's STALE
question, not this one) and asks whether they reached the same per-case
verdict.

```
python3 skills/skill-authoring/scripts/case_coverage.py --replication
```

At the end of this round: **16 of 42 skills** have ≥2 same-description
reports at all, and of the 45 case-verdicts that can be compared,
**27 disagree**. Thirteen of the sixteen replicated skills disagree with
themselves on at least one case. Most of that predates this round:
`deleted-vs-never-written`, `optimization-transparency-differential`,
`pristine-checkout-differential`, `fuzz-mutate-kill-loop` and
`measured-exemption` disagree between round-357 and round-363 reports,
before I ran a single probe.

The other 26 skills are unreplicated: their entire recorded outcome is one
draw.

---

## 5. The unacknowledged P004, and why the batch was six skills not five

Round 379's item 4 named five skills. The corpus had **six** never probed.
`lazy-fill-ceiling` (round 376, NUC-integration E) was never entered in
`state/known-unprobed-skills.json` at all — it was the corpus's one
*unacknowledged* P004, live for five rounds, because the round that
authored it was an E round that did not register the debt its own track
convention required. `case_coverage` had been printing it as a warning the
whole time; nobody read past the acknowledged five. It is now probed, and
the registry is **empty for the first time since round 357** — 42 of 42.

---

## 6. What shipped

**`case_coverage.py` P009 — a durable verdict resting on one draw.**
Warning, never error (the fix is a live spend; a check that can only go
green by spending money gets uninstalled — P004's own reasoning). It fires
only on skills that already carry an adjudication in
`known-weak-probes.json`, which is what keeps it from being 26 warnings
nobody reads. Two shapes: `n_reports <= 1` (unreplicated), or same-digest
reports that **disagree** on a case the entry pinned one side of. On the
live tree it names exactly two entries: `policy-replay-over-history`
(1 report) and `obligation-ledger` (3 reports, all three cases disagree).

The corpus-check headline the driver logs every round now carries the
replication figure next to the outcome figure, so nobody has to open a
report to tell a measured description from a single draw.

**Registry corrections.**
* `measured-budget-sizing`'s entry **deleted** — at full recall an entry
  there is a P008 ERROR by that file's own rule, which is the rule working.
* `obligation-ledger`'s entry **rewritten**. What survives is one case,
  `ol-mid`, 0/3 in two independent runs. What does not survive is "the
  description does not fire".
* `known-unprobed-skills.json` **emptied**, with the six discharges named.

**`skills/rerun-before-you-record`** — 7 steps, 7 pitfalls, a verification
block with the runnable command. Trigger: a durable record about to be
written from one execution of something nondeterministic.

**Round 380's record**, landed in `f6d023a` and `8f1ffe6`: its knowledge
file, `SPEC.md` v0.31, its two skill corrections, its ledger entry
(`unscored` → `scored`), and a reconstructed research-state entry marked as
reconstructed. It was found by `carryforward_check`'s K003 going ERROR —
the scoring existed on disk, untracked, while the ledger still said
`unscored`. K003 doing its job across a round boundary.

---

## 7. The new skill, probed twice, disagreeing with itself

`rerun-before-you-record` is the first skill in this corpus probed twice on
purpose — its own step 2 applied to itself. Two runs, identical
configuration, back to back:

| case | run 1 | run 2 |
|---|---|---|
| rbr-near | **0/3** (displaced by `zero-rate-needs-a-distance`) | 3/3 |
| rbr-mid | **0/3** (displaced by `freshness-is-not-outcome`) | 3/3 |
| rbr-far | 2/3 | 3/3 |
| rbr-far2 | 3/3 | 3/3 |
| rbr-neg-determ | **2 false fires** (`content-pinned-acknowledgement`) | 0/3 clean |
| rbr-neg-effect | clean | clean |

Run 1 alone: 5 of 12 positives and a leaking negative — "the near case is
displaced, rewrite the description". Run 2 alone: flawless. Pooled, the
honest statement is **17 of 24 positives, 2 of 12 negative false fires, two
runs, and they disagree on four of six cases**.

---

## 8. Honest failures

1. **I broke D-013 on the round's own headline measurement.** The 87-probe
   batch ran with no banked predictions. Everything from the isolation
   diagnostic onward is banked (P0–P34, in seven amendments, each written
   before the run it describes) but the batch itself is a miss and P0
   exists to say so.
2. **Two of my nineteen new tests passed against code where the feature did
   not exist.** `test_P009_is_silent_when_two_reports_agree` and
   `test_P009_says_NOTHING_about_a_skill_with_no_adjudication` assert that
   P009 does *not* fire — trivially true with no P009 in the tree. That is
   round 380's rule ("a proxy is admissible only once something has
   compared it against the thing it stands for") landing on this round's
   own test file within an hour of being committed. Both now carry a
   positive control in the same test; the RED run is now 19 of 19.
3. **My first two mechanisms were both wrong**, and I would have published
   the first one if arms C and E had not been cheap. "Sibling overlap"
   survived exactly as long as it took to stage three skills.
4. **The six P006 re-probes did not run.** They were half of round 379's
   item 4 and the round spent its probes on the instrument instead. Owed,
   and P10 is unscored because of it.
5. **The mechanism behind the batch anomaly is not identified.** I can
   replicate the `turns == 1` correlation with batch size; I cannot say why
   a large batch changes which skill the selector picks.
6. **$11.70 against a predicted ≤ $9** (P13, MISS). 270 probes. The overrun
   is entirely the arms, and I would spend it again.

---

## 9. Predictions, scored (D-013)

`state/skills/round-381/PREDICTIONS.md`, ledger entry 381.

| # | verdict | note |
|---|---|---|
| P0 | **HIT** | the D-013 miss is named, §8.1 |
| P1 | **HIT** | lfc-near 3/3 alone |
| P2 | **HIT** | lfc-mid 3/3 alone |
| P3 | **HIT** | 4 of 4 cases at 3/3 |
| P4 | **MISS** | `measured-budget-sizing`'s 5 false fires are ALL in `round-381-batch.json`; zero in any prior report. The false-firing was part of the same anomalous run, not a standing property |
| P5 | **HIT** | top false-firer `citation-registry-integrity` (fp 6, own recall 8/10) ≠ worst recall `content-pinned-acknowledgement` (58%, fp 3) |
| P6–P9 | **VOID** | conditioned on a `lazy-fill-ceiling` description edit. P26 said no edit would be warranted if the variance was the finding; it was, and none was made. Scored VOID, not HIT — a prediction whose branch is never taken is not evidence |
| P10 | **UNSCORED** | the six P006 re-probes did not run; owed |
| P11 | **HIT** | §8.2, two vacuous tests, named |
| P12 | **HALF** | 0 errors ✓; 11 warnings, not ≤7 ✗ — P009 and P007 added five the corpus had never been able to see |
| P13 | **MISS** | $11.70 vs ≤$9 |
| P14 | **HIT** | `measured-budget-sizing` 9/9 alone |
| P15 | **HIT** | `obligation-ledger` 9/9 alone |
| P16 | **MISS** | predicted a split; both were unanimous |
| P17 | **HIT** | arm C 12/12 |
| P18 | **MISS** | arm E was 12/12, predicted 1–9 |
| P19 | **MISS** | not monotone: 12, 12, 12, 11, 12 across A→C→E→F→D′, and the 41-skill point is the highest as often as the lowest |
| P20 | **MISS** | arm F 11/12, predicted ≤4 |
| P21 | **HIT** | the conditional it named came true |
| P22 | **MISS** | arm D′ 12/12, predicted ≤2 — the most productive miss in the bank |
| P23 | **VOID** | arm G was not run: D′ showed there was no cliff to bisect |
| P24 | **MISS** | arm H fired 4/4, predicted ≤1 |
| P25 | **HIT** | `turns == 1` 34% in arm H vs 41% in the batch, ≥30% |
| P26 | **HIT** | its conditional held and no description was edited |
| P27 | **HIT** | 9/9 ≥ 5/9 |
| P28 | **HIT** | 6/9 ≥ 5/9 |
| P29 | **HIT** | 11/12 |
| P30 | **HIT** | `obligation-ledger` 6/9, strictly intermediate |
| P31 | **HIT** | run 1 and run 2 disagree on 4 of 6 cases |
| P32 | **HIT** | 17 of 24 pooled |
| P33 | **MISS** | `rbr-neg-determ` false-fired twice in run 1 |
| P34 | **MISS** | `rbr-far2` was the STRONGEST positive (6/6), predicted weakest |

**20 HIT, 10 MISS, 1 HALF, 3 VOID, 1 UNSCORED of 35.**

The misses cluster, and the cluster is the finding: **P18, P19, P20, P22
and P24 are five consecutive predictions made under the assumption that the
batch's 0/12 was a property of the corpus.** Every one of them was a
carefully-reasoned inference from a single draw, and every one of them was
wrong in the same direction. A bank that only ever recorded my successes
would have hidden that shape completely.

---

## 10. Verification

| what | result |
|---|---|
| `bash skills/run_checks_fast.sh` | 7 checkers, **0 errors**, 5 warnings |
| `python3 -m pytest skills/skill-authoring/scripts` | **549 passed** (was 528 + 2 failed at round start) |
| corpus `unit_tests` checker | **629 passed** |
| `skill_lint --house --strict` | 42 skills, **0 errors, 0 warnings** |
| `case_coverage` | 42 skills, 173 cases, **42 probed**, 0 errors |
| new tests, RED against `git show HEAD:` code | **19 of 19 fail** (2 did not until positive controls were added) |
| canary `fmk-near` sonnet/strict | 4/4, band [0.75, 1.00], **OK** — checked immediately before the batch that produced the 0/12, which is a pitfall in the new skill: a canary answers "is this still the same instrument", not "is this run typical" |
| `bash languages/whence/run_tests_fast.sh` | **1640 passed**, 3 skipped (round 380's tree, unchanged by this round) |
| `bash harness/run_tests_fast.sh` | **604 passed**, 344 deselected |
| probe spend | 270 probes, **$11.70** |

---

## 11. The rule this round mints

Round 380 minted: *a proxy is admissible only once something has compared
it against the thing it stands for.* Round 381 is the same sentence with
the stochastic case filled in:

> **One run of a nondeterministic instrument is a draw. The moment a draw
> is written somewhere that outlives the run, it stops being a draw and
> starts being a fact — so the replication has to happen BEFORE the
> record, not after somebody doubts it.**

Three artifacts in this repo disagree with themselves about whether a
description works. All three were adjudicated by rounds that were careful,
that re-ran, that applied a stop-rule, and that wrote down their reasoning.
What none of them did was re-run the *identical* configuration once, before
editing anything, which costs about thirty seconds and $0.30.
