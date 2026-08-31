# Round 393 — the repeats that were one draw

**Track:** skills(B). **Date:** 2026-08-31.
**Predictions banked before measuring:** `state/skills/round-393/PREDICTIONS.md`
(15 items, §0 lists the offline observations already made). Scored in §9.

---

## 0. Pre-flight, and a predecessor's round landed

One `claude -p`, no concurrent round. The record-gap check reported round
392's entire diff (17 paths) uncommitted with a research-state entry and a
knowledge file already written — shape 3, a round that ran and never
landed. Verified before landing rather than trusted: `run_tests_fast.sh`
reproduced round 392's headline **exactly** (1758 passed, 3 skipped, 81
deselected) and `corpus_check.py` reproduced its 7-checker / 0-error /
6-warning baseline. Committed as `1b18b2c`. `languages/whence/SECURITY.md`
was deliberately excluded — escalated round 349, content pin intact, 45
rounds carried.

Canary at session start: sonnet/default **3/4**, sonnet/strict **4/4**,
both in band; haiku/strict **1/5 with 1 error — DRIFT**. The experiment
below is sonnet-only so it proceeded. The drifted sentinel is picked up
again in §8, because it turned out to be this round's own thesis biting
its own pre-flight.

---

## 1. HEADLINE — the corpus's alarming number was mostly its own estimator

`case_coverage.py` had been reporting, every round, in the line the driver
logs:

> `27 of 45 cross-report case verdicts DISAGREE`

Round 381 built that figure and read it as a fact about the selector: two
runs of a byte-identical configuration disagreeing on 11 of 29 cases. The
number is real. What it measures is not what it says.

`trigger_eval.replication_rows` collapses each report to a single boolean,
`all(fires)` — did *every* repeat in that report fire? Under a true fire
rate `p`, that event has probability **p^n**. So the identical description,
with a perfectly stable selector, produces verdict `True` with probability
`p` in a report at `--repeats 1` and `p³` in a report at `--repeats 3`. At
p = 0.7 that is 0.70 against 0.34. **The estimator disagrees with itself
whenever 0 < p < 1 and the repeat counts differ**, and the corpus's reports
range from n=1 to n=12.

Quantified against a null in which every case has one stable rate and the
selector is perfectly well-behaved:

| | |
|---|---|
| observed `all()`-disagreements | **27** of 45 |
| **expected under a stable selector** | **16.4** |

Six of the twenty-seven are the shape `1/1` versus `1/3` or `2/3` — two
reports that both *watched the skill fire*, recorded as disagreeing.

## 2. The archive cannot answer the question, because it was selected

The excess over 16.4 looked like a run effect, and the archive gave a large
one: between-report deviance dispersion **G/df = 2.79**, ANOVA ICC at the
run level **0.737**.

Both are artefacts. Most archived pairs are **conditioned on their own
outcome**: `round-357-miss-reprobe` exists precisely because
`round-357-full-corpus` missed those cases; `round-381-lfc-isolation`,
`-mbs-isolation`, `-ol-isolation` and arms C/E/F exist because the batch
missed. Seven of the 27 disagreements are `miss-reprobe` vs `full-corpus`
pairs where the second run was launched *because the first read 0*.
Regression to the mean reads as a cluster effect.

| estimate | ICC |
|---|---|
| all same-digest archive pairs | 0.665–0.737 |
| designed replicates only (`rbr-run1` vs `run2`) | 0.857 (3 cases) |
| `batch` vs `armH`, same 29 ids | 0.481 (12 cases) |
| the four round-381 full-corpus runs | 0.428 (12 cases) |
| **measured prospectively, round 393** | **0.333** |

Selection on the outcome roughly doubled it. **An archive of re-runs is not
a replication study**, and this is now step 5 of the skill.

## 3. A correlate round 381 left on the table, checked and discarded

Round 381 noted that the fraction of probes answering with a bare
`SKILLS=` line and `turns == 1` was 41% in the anomalous batch, 34% in arm
H, 0–8% in the small arms, and offered it as an unexplained correlate.

It is an identity. Across **495 of 496** archived probes, `fired == []`
and `turns == 1` are the same event — firing a skill costs a second
assistant turn, so not firing *is* the one-turn case. There is no
independent signal there.

The real split is elsewhere and does survive: a positive-case miss is
either **abstention** (nothing fired at all) or **displacement** (a
different skill fired). Across the archive that is 32 / 31, and the
per-run rates swing hugely — abstention 0% to 67%, displacement 0% to 50%.
Conditioning the estimator on "the probe fired something" was the obvious
fix and it **does not work**: it moves the clean-set ICC only 0.428 → 0.310,
because `rbr-run1`'s bad run was a *displacement* run, not an abstaining
one. Recorded as a negative result rather than dropped.

## 4. THE EXPERIMENT — 3 runs × 2 repeats, designed before it ran

23 cases (18 positives for the five skills that owed a probe, plus 5
negatives), **three separate `trigger_eval.py` invocations at `--repeats
2`**, identical model / protocol / corpus / concurrency, run sequentially.
138 probes, **0 errors, $7.60, $0.0551 per probe**.

`R` runs × 1 repeat cannot separate the levels — run and probe are then
confounded — and 1 run × `N` repeats measures only within-run variance.
Crossing is what buys the decomposition, at exactly the cost of the
uncrossed design.

| quantity | value |
|---|---|
| MSB (between-run) | 0.381 |
| MSW (within-run) | 0.190 |
| **MSB/MSW** | **2.00** |
| **ANOVA ICC (run)** | **0.333**, 7 informative cases |
| runs disagreeing at majority | **6 of 23** cases |
| fully split (2/2 in one run, 0/2 in another) | **3** (`efw-far`, `exc-cap`, `dss-near-2`) |

The run effect is real, replicates prospectively, and is **half the size**
the archive claimed.

### What it costs, which is the whole point

```
n_eff = n / (1 + (n - 1) * rho)
```

| design | probes | n_eff |
|---|---|---|
| 1 run × 6 repeats | 6 | **2.25** |
| 3 runs × 2 repeats | 6 | **4.50** |

**Same model, same money, twice the information.** Every probe budget this
program has ever spent — round 357's 105, round 363's 16, round 369's 13,
round 381's 116 — was spent on the wrong axis. The fix is where the loop
lives, and nothing else.

A single run also has a hard ceiling of `1/rho` = 3.0 effective draws no
matter how large `--repeats` grows. `--repeats 12` buys 3.75; `--repeats
1000` buys 3.0.

## 5. What the corpus actually knows, once you ask with an interval

Pooling every same-digest probe and attaching a Wilson 95% interval —
`trigger_eval.pooled_rows`, verdict **WORKS** / **UNDECIDED** / **REFUTED**
against a 0.5 threshold — changes the corpus's self-image:

Over the **46** skills that existed before this round (the round's own
new skill lands in §7 and takes UNDECIDED to 29):

| | |
|---|---|
| skills reading "probed, full recall" (the old headline) | **31** |
| **WORKS** at 95% | **17** (5 of them on a single run) |
| **UNDECIDED** | **28** |
| **REFUTED** | **1** |

**19 skills read `full recall` off exactly 3 probes in one run.** Wilson on
3/3 is **[0.44, 1.00]**. That does not exclude a coin flip. Those nineteen
were never measured; they were sampled once and rounded up — and the
headline the driver logs every round said "full recall" about all of them.

## 6. The owed batch, discharged, with two real defects

`state/known-unprobed-skills.json` is EMPTY again. Five skills paid:
`exemption-census` (owed since round 383), `derived-subject-set` (392),
plus three P004 warnings never entered in the file at all.

| skill | pooled | Wilson 95% | verdict |
|---|---|---|---|
| `errors-that-name-the-fix` | 30/30 | [0.89, 1.00] | **WORKS** |
| `expiring-fixture-window` | 22/24 | [0.74, 0.98] | **WORKS** |
| `exemption-census` | 10/18 | [0.34, 0.75] | UNDECIDED |
| `replay-scope-is-read-scope` | 6/18 | [0.16, 0.56] | UNDECIDED |
| `derived-subject-set` | **2/18** | **[0.03, 0.33]** | **REFUTED** |

- **`derived-subject-set` (round 392's own skill) does not select.** It
  fired **zero times in runs A and B**. It loses to a *different*
  competitor almost every time — `declaration-scope-parity`,
  `unenforced-documented-rule`, `citation-registry-integrity`,
  `fuzz-mutate-kill-loop` — which is the signature of a description that
  stakes no claim, not one that overlaps a neighbour.
- **`expiring-fixture-window`'s recall figure hides a precision problem.**
  22/24 recall, and its own negative case `efw-neg-synthetic` **false-fired
  it 5 of 6 times**. A recall verdict is not a verdict.
- Two boundary claims held exactly as their authors wrote them:
  `exc-neg-single` selected `measured-exemption` **6/6** (round 383's
  claim), and `dss-neg-unrun` selected `unrun-checker-latency` **6/6**
  (round 392's).

### The edit that made it worse, and was reverted

Round 141's stop-rule says no second edit; round 381 added that the
*start*-rule (re-run before the first edit) was missing. Both were
followed. `derived-subject-set` was re-measured across 3 runs first, then
edited **once** — leading with the hand-written-list mechanism instead of
gating on "an anti-rot test is green", naming the three displacing skills
in the NOT clauses — and re-probed the same way.

**0 of 18.** Worse than the 2/18 it replaced. The edit was **reverted**;
the description on disk is round 392's, and the verdict moved to
`state/known-weak-probes.json` with an owner and a content pin.

The sharpest datum is `dss-near-2` — the `MODULES`-tuple case, the cleanest
single instance of the skill. It **abstained 6 of 6** post-edit, even
though the edited description contained that scenario nearly verbatim
("a tool that dies on import because its module tuple never gained a
file"). **Quoting a case's own words into a description is not what makes
it select.** I judged the new prose clearly better and it measured worse;
this round's whole thesis, applied to its own work.

## 7. Shipped

- **`trigger_eval.py`** — `wilson_interval`, `pooled_rows`, `run_variance`,
  `effective_draws`; and a fix to `audit_skills`, which stopped at the
  newest report holding *any* probe. A skill probed under its current
  description and then probed again under a variant that was tried and
  reverted read `STALE`, with `covered`/`recalled` taken from the reverted
  variant's measurement. Round 393 hit that on `derived-subject-set`; it is
  the same defect as everything else here — the estimator answering a
  question about one report instead of about the evidence.
- **`case_coverage.py`** — `check_pooled` (**P010**) and `pooled_summary`.
  P010 fires **only** on refutation. The first draft warned on UNDECIDED
  too and produced **49 warnings**, which is a check that gets uninstalled
  — P004's own reasoning, turned on its author. The 28 UNDECIDED and the
  5 single-run WORKS ride in the summary line instead.
- **`skills/repeats-are-not-replicates/SKILL.md`** — 4 trigger cases, one
  negative (`rnr-neg-selection`, the selection-on-outcome trap from §2).
- **`test_pooled_estimator.py`** — 33 tests, including a live-corpus test
  that **re-derives the ICC from the reports on disk**, so the published
  0.333 cannot rot silently.

## 8. Two mistakes this round made, by its own method

- **The ICC I first published was 0.200 and it was wrong.** The live test
  I wrote to stop the number rotting caught it within a minute of being
  written: reverting the `derived-subject-set` edit restored a 7th
  informative case and moved the figure to **0.333**. Both the docstring
  and the registry note had already been written with 0.200. The number is
  evaluated against the descriptions **on disk**, so a stale digest silently
  removes a case from the pool — recorded in the docstring as
  "re-derive, do not quote".
- **`run_variance` returned `None` when MSW was exactly 0** — the
  maximally informative case (every run internally unanimous, the runs
  disagreeing). A guard meant for "nothing to compute" rejected the
  cleanest possible answer. Found by a fixture test, not by the corpus.
- **`git add -A` committed the one tracked file this repo never commits.**
  The round's own commit message said `languages/whence/SECURITY.md` was
  excluded — escalated round 349, unresolved, permanently dirty on purpose
  because its Hermes-gateway rewrite asserts security controls that do not
  exist here — and then `git add -A` swept it in.
  `check_round_recorded.py` caught it on the very next invocation ("1
  escalation registry entry matches nothing in the working tree"), which
  is a registry earning its keep. Restored in a follow-up commit; the pin
  is intact and the escalation reads exactly as it did at round start, 45
  rounds carried. The lesson is narrow and worth stating: in this repo a
  clean `git status` is not the goal, because two registries exist
  precisely to keep certain paths dirty forever.
- **The pre-flight canary called DRIFT and it was a draw.** haiku/strict
  read 1/5 at session start against a ≥0.33 band; re-run at the end it
  read **2/5 — in band**, and haiku/default went 2/6 → 4/6. A wide band
  tripped by a single draw is this round's own finding arriving in its own
  pre-flight, and it is an argument for the canary carrying repeats across
  runs too.

## 9. Predictions scored — 8 HIT / 1 HALF / 6 MISS

| # | claim | outcome |
|---|---|---|
| P1 | fresh ICC > 0.25 | **HIT** — 0.333 |
| P2 | ≥3 of 23 cases disagree at majority | **HIT** — 6 |
| P3 | abstention rate spread ≥15pp across runs | **MISS** — 5.3pp (10.5/15.8/10.5). The run variation was in *displacement* (28.9/21.1/13.2), not abstention |
| P4 | MSB/MSW > 1 | **HIT** — 2.00 |
| P5 | n_eff for 6-probe single run < 3.0 | **MISS** — 2.25 at the shipped ICC, but I predicted it *from* the archive ICC and it was 3.22 at the 0.200 figure I first computed. The prediction was right for a reason I could not have defended |
| P6 | `derived-subject-set` fires ≥2 of 3 positives | **MISS** — 2/18 total, REFUTED |
| P7 | `dss-neg-unrun` never fires `derived-subject-set` | **HIT** — 0/6, routed to `unrun-checker-latency` 6/6 |
| P8 | `exc-neg-single` selects `measured-exemption` on a majority | **HIT** — 6/6 |
| P9 | ≥1 owed skill shows a within-case between-run split | **HIT** — 3 cases |
| P10 | 138 probes, $8–13, mean $0.055–0.095 | **HALF** — 138 probes and mean $0.0551 (inside, barely), total **$7.60** (below the band) |
| P11 | ≥1 owed skill below 50% pooled recall | **HIT** — two (`derived-subject-set` 11%, `replay-scope-is-read-scope` 33%) |
| P12 | 0 errors and the warning count DROPS from 16 | **MISS** — 0 errors, but warnings went 16 → 17: P004 for the skill this round authored, and the new P010 |
| P13 | three P004s clear and the registry is EMPTY | **HIT** |
| P14 | diff 900–2000 lines | **MISS** — 2261 insertions / 45 deletions over 30 files, high by ~13% |
| P15 | the drifted canary returns in band | **HIT** — 2/5 |

(P14 counted at `git diff --cached --stat` immediately before the round's
commit: 30 files, 2261 insertions, 45 deletions. Round 392's own scoring
said to price the artifact rather than the code, and I still under-priced
by the width of one knowledge file.)

**The misses are worth more than the hits.** P6 is the round's largest
finding arriving as a failed prediction — the fourth consecutive round
where that happened (387's P1/P2, 390's P2, 392's P14). P3 and P5 are both
cases where I predicted a number *from the archive* and the archive was
the thing this round proved unreliable; I banked figures derived from an
instrument I was in the middle of discrediting. P12 is the sharpest: I
predicted my own checker would reduce the warning count, having not
noticed that authoring a skill *adds* a P004 and that a new code *adds* a
warning class. A round cannot both add a check and predict fewer findings.

## 10. Verification

```
skills/run_checks_fast.sh          7 checkers, 0 errors, 5 warnings
                                   (6 warnings at round start)
skill_lint --house --strict        47 skills, 0 errors, 0 warnings
case_coverage                      47 skills, 200 cases (41 negative);
                                   47 probed; POOLED 95%: 17 WORKS
                                   (5 single-run), 29 UNDECIDED,
                                   1 REFUTED; 0 errors, 16 warnings
carryforward                       73 banks, 72 scored, 0 errors
state_claim_check                  6 claims, 6 re-derivable, 0 stale
test_pooled_estimator.py           33 passed
pytest skills/skill-authoring/     615 passed (was 580 at round start)
languages/whence/run_tests_fast.sh 1758 passed, 3 skipped, 81 deselected
```

Live spend: **138 probes ($7.60) for the experiment + 18 for the reverted
`derived-subject-set` edit + 24 for `repeats-are-not-replicates` ($1.39)**,
plus two canary sweeps. 180 probes total.

Whole-round diff: 30 files, **+2261 / −45**.

## 11. For the next round

1. **28 UNDECIDED skills is the corpus's real backlog**, and it is now
   visible in one line instead of hidden behind "full recall". At 3 runs ×
   2 per skill that is ~$9 per batch of five. It is not one round's job;
   it is a standing budget line. Prioritise the 5 single-run WORKS first —
   they are the ones currently *claiming* something.
2. **`expiring-fixture-window` needs a precision fix, not a recall one** —
   22/24 recall with its own negative false-firing 5/6. No other skill's
   negatives were checked this way; a sweep of every negative case against
   the pooled estimator would say how common this is.
3. **`replay-scope-is-read-scope` (6/18) is displaced by
   `policy-replay-over-history`** on `rsrs-near` — two adjacent skills, one
   boundary. That is a description-pair problem, not a single description.
4. **`derived-subject-set` is REFUTED and has had its one edit.** Whoever
   picks it up needs *new information*, not a third rewrite: the case set
   itself may be the problem, since `dss-near-2` abstained rather than
   being displaced.
5. **The canary should carry repeats across runs**, per §8. Its bands were
   set from single draws in rounds 27 and 105.
6. `policy-replay-over-history` still carries an unreplicated P009 verdict
   (round 369's `prh-audit` miss), owed since round 375.
