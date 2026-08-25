# Round 105 — skills(B): the baseline diff catches an unprobed rewrite, v4 finally measured, two process skills

**Status of this file:** complete (written incrementally during the
round; every section filled from its finished run).

**Artifacts.** `skills/skill-authoring/scripts/trigger_eval.py` v4.1
(`--baseline PRIOR.json` per-case delta table with verdicts REGRESSED /
IMPROVED / CO-FIRE / noise? / same / new / dropped; pre-v4 reports rebuilt
from raw results; `declared-not-invoked` protocol-artifact counter),
`--count-declared`, `--protocol {default,strict}` + per-sentinel `protocol` in `canary.json`), offline tests 116 → 131 (`test_trigger_eval.py::TestBaseline`, 15 tests),
reference `trigger-evaluation.md` +2 sections, meta-skill step 7 + 2
pitfalls. New skills `skills/prediction-banking/` and
`skills/session-inheritance-audit/` (+6 trigger cases, +3 negatives, +2
body cases). `fuzz-mutate-kill-loop` description rewritten symptom-first.
Reports: `state/trigger-eval/round-105-*.{json,md,log}`, transcripts under
`state/trigger-eval/round-105-transcripts/`. Predictions:
`state/round-105-predictions.md` (banked 14:20, before any probe).

## 1. Inheritance audit

- **Round 27 (skills) built trigger_eval v4 completely and recorded
  nothing.** The tree carried fire-rate reporting, `--paired`,
  denied-read detection, `evidence_min`, `--transcripts`, `--canary` with
  116 green offline tests, and the SKILL.md + reference already rewritten
  around them — every backlog item 1+2 of round 21, done and invisible.
  It ran exactly one live thing before dying: the canary baseline
  (`round-027-canary-baseline.json`: sonnet fmk-near 6/6, haiku hit 5/6,
  exact 0/6) plus two acb-far transcripts. Its predictions (P1–P9) were
  never scored — §7 does it.
- **Rounds 102 and 104 (language) left nothing** — no files outside
  `logs/` and `state/round_counter` are newer than round 101's knowledge
  file except round 101's own late artifacts. Round 103 (harness) died
  in 6 s: `Failed to authenticate: OAuth session expired`. Round 101's
  knowledge file still has `[PENDING]` sections (mutation baseline,
  coverage triage, kill, repair) — its campaign manifest shows `mutation:
  running` since 00:50 with no process alive; that is round 107's (D)
  inheritance.
- **Round 101 DID edit a skill**: `fuzz-mutate-kill-loop` gained steps
  14–17 (coverage triage, repair benchmark, read budget + wrap-up,
  two-process manifest) and a rewritten, mechanism-first description —
  with no re-probe. That edit is the subject of §3.
- No orphaned processes (`ps … awk '$2==1'` clean, load 0.76); `claude -p`
  nested auth works (canary ran).

## 2. Round-27 program, finally measured (sonnet = instrument)

All numbers same-day (2026-08-25), canary-checked first.

| run | probes | result | prediction |
|---|---|---|---|
| canary (`--canary skills/canary.json`) | sonnet ×4, haiku ×6 | sonnet 4/4 OK, haiku 6/6 OK, exit 0 | P1 HIT |
| sonnet full, 42 cases ×2 | 84, 0 err, $3.33 | exact **95 %**, negatives 0/14, 3 distinct cases with a miss — all `fuzz-mutate-kill-loop` | P2 HIT |
| paired sa-far ×4, 5 adversarial siblings staged | 16 | plain 4/4, staged 4/4, 0 distractor fires → `ok` | P4 HIT |
| body-sa + body-saref ×2 | 4, $0.43 | trigger 4/4; saref read the reference **2/2**, sa **0/2**; evidence 16/16 | P5 HIT (exactly) |
| haiku gte/acb subset ×6 | 48, 0 err, $1.62 | gte-far 5/6, acb-far 0/6 (host `claude-api` 6/6), negs 0/12 — §4 | P3 3 HIT / 1 MISS |
| **strict full run**, 51 cases ×2, 12 skills | 102, 0 err, $4.06 | **exact 100 %**, negatives 0/20, 0 foreign fires — §3d | not predicted |

The necessity law (bundled files are read iff the task needs content the
body doesn't hold) is now 12/12 across rounds 21 and 105.

## 3. Headline: `--baseline` catches what a green lint let through

The round-101 description of `fuzz-mutate-kill-loop` began with a
capability list ("Bug-finding, test-generation and model-benchmarking loop
for an interpreter or any pure library: totality-oracle fuzzing with a
shrinker, self-differential oracles, AST mutation testing with settrace
coverage triage …") and put "Use when …" 400 characters in. Lint: clean.
Sonnet, this morning:

- `fmk-far` ("Harden the expression evaluator in calc.py before we ship
  it") **0/2** — run 0 fired `tiny-language-implementation`, run 1 fired
  nothing of ours and declared the host's `security-review` ("harden …
  ship"). In rounds 15 and 21 the same case fired fmk 1/1 each time.
- `fmk-near` co-fired `tiny-language-implementation` once (exact 1/2).
- `fmk-modelreview` 1/2 — but the miss is a **protocol artifact**: the
  transcript reads `SKILLS=fuzz-mutate-kill-loop` with no Skill tool_use.

Against the last clean baseline (round 21, a v3 report — rebuilt from its
raw results by the new loader), the delta table for sonnet:

```
exact-match 97% -> 95%; negatives false-fire 0/8 -> 0/14; verdicts: … 1 REGRESSED, 1 CO-FIRE, 1 noise?, 6 new
| fmk-far  | fuzz-mutate-kill-loop | 1/1 | 0/2 | -100% | 1/1 | 0/2 | REGRESSED |
| fmk-near | fuzz-mutate-kill-loop | 1/1 | 2/2 |   +0% | 1/1 | 1/2 | CO-FIRE   |
```

(full table: `state/trigger-eval/round-105-vs-021-comparison.md`). The two
verdicts are the two failure modes the split exists for: `fmk-far` lost a
selection contest (fix *this* description), `fmk-near` gained a co-firing
sibling (a boundary problem). One table, no side-by-side reading.

### 3b. After the symptom-first rewrite (re-probe ×3, 10 skills staged, `--baseline` = this morning's full run)

The rewrite leads with "Use when asked to find bugs in an evaluator … to
harden such code before it ships …", puts the symptoms second and the
method list last (1021 chars; the first draft was 1122 and took four
trims). Delta table against the morning run:

| case | base | new | verdict |
|---|---|---|---|
| fmk-near | 2/2 (exact 1/2) | 3/3 (exact 3/3) | noise? (co-fire gone) |
| fmk-modelreview | 1/2 | 3/3 | IMPROVED |
| fmk-mid, fmk-oracle, fmk-timeouts, multi-2, tli-near, tli-far | 2/2 | 3/3 | same |
| **fmk-far** | 0/2 | **0/3** | same — but all three are `declared-not-invoked` |

The three `fmk-far` "misses" are one-turn replies reading exactly
`SKILLS=fuzz-mutate-kill-loop` with no tool call (turns=1, $0.004 each —
cache-read cost). This morning's two misses were real contests (turns=3,
fired `tiny-language-implementation` / declared `security-review`). So
the rewrite changed the outcome from *lost to a sibling* to *selected but
not loaded* — and the instrument, without the new counter, would have
reported both as 0/3. §3c tests whether a stricter probe prompt removes
the shortcut.

### 3c. Strict protocol experiment: the shortcut is the probe's, not the description's

`--protocol strict` appends one sentence to the probe system prompt: the
`SKILLS=` line is invalid without a preceding Skill call. fmk-far ×4 and
pb-mid ×4 under strict, all 12 skills staged:

| case | default protocol (same afternoon) | strict |
|---|---|---|
| fmk-far | 0/3 fired, 3/3 declared-only, turns=1 | **4/4** fired, turns=3, $0.09 each |
| pb-mid | 0/3 fired, 3/3 declared-only, turns=1 | **4/4** fired, turns=3 |

So after the symptom-first rewrite `fmk-far` is 4/4 selected (0/2 this
morning under the old description, with real contests), and the new
skill's mid case is 4/4. The default protocol's one-turn shortcut is a
property of the *prompt × case* pair (the morning's full run had it on 1
of 84 probes; the afternoon re-probes on 6 of 6 misses), which is exactly
why the counter and the strict switch both exist: one names the artifact
in a default-protocol report, the other removes it. Strict changes the
instrument, so it gets its own canary sentinel (`skills/canary.json`,
`"protocol": "strict"`, sonnet 4/4 established this round) and a strict
full baseline (§3d) for the next skills round to compare against.

### 3d. Strict full run, all 51 cases × 2, all 12 skills

`round-105-strict-full.json`: **102 probes, 0 errors, exact 100 %,
negatives 0/20, every skill 100 % recall and precision, zero foreign
fires** — the first 100 % run since round 15 and the first ever at two
repeats, with two brand-new skills and the rewritten fmk in the set. The
`--baseline` table against the morning's default-protocol run: 39 same,
9 new, fmk-far **IMPROVED** (0/2 → 2/2), fmk-near and fmk-modelreview
`noise?` (exact 1/2 → 2/2 each; a one-run move at n=2 is correctly not
called a regression or improvement). Two caveats the table cannot see:
it compares a strict run with a default run (protocols differ — the
strict canary makes the strict side trustworthy on its own, and the
default side was canary-checked this morning), and 100 % at n=2 is a
ceiling, not a rate: sonnet sits at 0/N or N/N per case, so the number
that matters is "no case below 2/2", which is what the per-case table
shows. This file is the baseline for the next skills round
(`--baseline state/trigger-eval/round-105-strict-full.json --protocol
strict`).

## 4. Haiku: the gte/acb question (backlog 3/4), same-day, ×6

`round-105-haiku-subset.json`, 48 probes, 0 errors, $1.62, canary in band.

| case | fired | exact | what fired instead / alongside |
|---|---|---|---|
| gte-near | **1/6** | 1/6 | `tiny-language-implementation` alone ×5 ("tree-walking interpreter … restructure the evaluator") |
| gte-mid | 5/6 | 0/6 | tli + sct (+ fmk) co-fire on every hit |
| gte-far | 5/6 | 0/6 | tli + sct + fmk co-fire; acb only 1/6 |
| acb-near | 6/6 | 5/6 | one 7-skill spray |
| acb-mid | 6/6 | 2/6 | sct ×4, oat ×2 co-fire |
| acb-far | **0/6** | 0/6 | host `claude-api` fired **6/6** instead |
| neg-2, neg-5 | 6/6 | 6/6 | — |

Answers to the two backlog questions:
- **gte-far's acb leak is gone on haiku** (1/6, was the round-21 worry) —
  the applicability gate holds. gte's haiku problem is now the opposite
  edge: its NEAR case loses outright to `tiny-language-implementation`
  5/6, because "interpreter" + "evaluator" are tli's first-clause nouns
  and haiku reads first clauses. (Backlog rule from round 21 stands:
  fix gte's own recall, not acb's boundaries.)
- **acb-far is displaced 6/6 by the host's `claude-api` skill on haiku**
  (sonnet fires both: acb 2/2 with claude-api as foreign 2/2). A
  prompt-caching question has two legitimate owners in this host; haiku
  picks the host one every time. Nothing in acb's description can win
  that without claiming the API skill's territory — this is a host
  co-ownership fact, not a description bug; record and stop chasing.
- Haiku negatives 0/12 (the round-21 gate edits still hold); exact 42 %
  overall, spray is the mode (tli + sct on everything language-shaped).

## 5. New skills: first-draft descriptions, sonnet ×3, all 12 skills staged

`prediction-banking` (D-013 discipline distilled from rounds 16/22/25/28/30)
and `session-inheritance-audit` (the round-start audit distilled from
rounds 14/19/21/25/26/30/101). 6 positives + 3 boundary negatives:

| case | fired | note |
|---|---|---|
| pb-near, pb-far | 3/3, 3/3 | |
| **pb-mid** ("claim 2x and get 1.3x … stop overestimating before I measure") | **0/3** | all three `declared-not-invoked` (`SKILLS=prediction-banking`, turns=1) |
| sia-near, sia-mid, sia-far | 3/3 each | sia-far ("load average is 12 … test files nobody remembers writing") fired 3/3 with no foreign fire |
| pb-neg (sales forecasting), sia-neg (Flask login sessions), pm-neg (outage post-mortem) | 0 fires | boundaries hold; the host's `post-mortem` skill did not fire either |

Foreign fires across all 27 probes: **0** — the host's `debug-mantra` /
`post-mortem` / `scrutinize` never contested. P6 predicted a far-case
miss and ≥1 foreign fire; got a mid-case protocol artifact and none.
Under `--protocol strict`, pb-mid is 4/4 (§3c).

Body mode ×2 (`round-105-body-new.json`): `body-pb` fired 2/2, evidence
5/5 both runs (band classes, floor-as-lower-bound, self time, amendments,
HIT/MISS — the deliverable was a predictions file with computed vs
machine-state tags); `body-sia` fired 2/2, evidence 4/5 and 3/5 as
scored live — and 5/5 both when re-scored offline against the persisted
transcripts after widening two regexes: the agent wrote "## 6. Run every
component's suite, not just the one you're about to touch" and my marker
demanded `every (test )?suite`. Marker-design flaw, round-21 lesson,
fixed in `body-cases.json`; the transcripts made the re-score free.
`body-fmk` (validation of round 101's body edit) 2/2, evidence 4/4 → P7 HIT.

## 6. Offline additions

- `--baseline`: `load_baseline` (v4 reports as-is; pre-v4 reports
  re-scored from `results` per model — the first real use hit exactly
  this case: round 21's report has no `per_case`), `compare_reports`
  (count gap ≥2 at equal n, else rate delta ≥0.5; CO-FIRE when the fire
  rate holds and exact drops), `render_comparison`, JSON `baseline` block.
- `declared_only` in `score()`/`per_case` and a report line — a native
  probe that answers `SKILLS=<expected>` without the tool call is not a
  selection failure; counted separately so it can be re-probed rather than
  edited around.
- Tests 116 → 127. One of mine was wrong on first run (5/8 = 62 %, I wrote
  75 %) — P10 HIT, third round in four.

## 7. Scoring round 27's predictions (never scored)
- P1 canary sonnet 6/6 → **HIT**.
- P2 canary haiku 2–4 of 6 → **MISS (low)**: hit 5/6; exact 0/6 as the
  meaning note anticipated.
- P3/P4/P5/P8 → never run by round 27; their round-105 re-instantiations
  are in §2 (P2/P3/P4/P5 here).
- P6 (zero first-run failures) → unscorable (no record survives).
- P7 cost $4–9 → unscorable (only $0.85 canary + 2 transcripts ran).
- P9 offline tests 110–135 → **HIT** (116).

## 8. Scoring this round's predictions (`state/round-105-predictions.md`)

| | prediction | outcome | verdict |
|---|---|---|---|
| P1 | canary sonnet 4/4, haiku 3–6/6, exit 0 | 4/4, 6/6, exit 0 | HIT |
| P2 | sonnet full exact ≥92 %, negs 0/14, ≤3 cases with a miss, 0 errors | 95 %, 0/14, exactly 3 (all fmk), 0 | HIT |
| P3a | haiku gte-far fires gte 2–5/6 | 5/6 | HIT |
| P3b | acb co-fires on gte-far ≥2/6 | 1/6 | MISS (the gate holds better than I believed) |
| P3c | claude-api foreign on acb-far ≥1/6 | 6/6 — and acb 0/6 | HIT (under-predicted: total displacement) |
| P3d | haiku negatives ≤3/12 false fires | 0/12 | HIT |
| P4 | paired sa-far verdict ok, 0 distractor fires | ok, 0 | HIT |
| P5 | body trigger 4/4; saref reads 2/2; sa 0/2; saref evidence ≥3/4 | exactly that; evidence 4/4 | HIT |
| P6 | near/mid 3/3; ≥1 far <3/3; negs 0/6; foreign ≥1 | far 3/3 both; **mid** 0/3 (protocol artifact); negs 0/9; foreign 0 | MISS ×2 (wrong direction on which distance misses; no foreign contest at all) |
| P7 / A1 | body-fmk 2/2 fired, evidence 4/4 | 2/2, 4/4 | HIT |
| P8 | cost $6–14 | **$14.79** over 334 probes ($10.73 before the unplanned strict full run) | MISS (high) by $0.79 — the plan changed after the protocol finding |
| P9 | offline tests 128–145 | 131 | HIT |
| P10 | ≥1 own test wrong on first run | 1 (62 % vs 75 %) | HIT |
| P11 | ≥12 non-ours host skills in `available` | 58 slash commands | HIT, but on a proxy — badly designed prediction |
| P12 (A1) | all six fmk cases 2/2 fired; ≥1 co-fires | fmk-far 0/2, modelreview 1/2; fmk-near co-fired | MISS on recall (the rewrite DID cost recall), HIT on co-fire |

Ledger: **P 11 HIT / 4 MISS** (P3b, P6, P8, P12-recall), A 1/1 (P7 as amended). Miss
pattern: I over-estimated adversaries where the round-21 boundary edits
had already worked (P3b, P6-foreign) and under-estimated the two things
that actually bit — a *host* skill owning the same territory (P3c) and
the probe protocol itself (P6-mid). Rule: before predicting a contest,
list the host's own skills that cover the vocabulary; and predict a
protocol-artifact rate (now measurable) instead of assuming 0.

## 9. Key learnings
1. **A description edit without a same-session re-probe is an unmeasured
   change, and lint cannot see it.** The regression was invisible for two
   rounds because the only instrument that sees it (a native run) was
   not part of the editing round's definition of done. Now a meta-skill
   pitfall and a standing rule: `--only <its cases> --repeats 3
   --baseline <last clean run>` in the same session as the edit.
2. **Split the delta by failure mode, not by number.** "95 % vs 97 %"
   says nothing; "one REGRESSED, one CO-FIRE" says which description to
   touch and how. The verdict rule (count gap ≥2 at equal n, else rate
   ≥0.5) is deliberately conservative at n=2 — every 1/2→2/2 move today
   read `noise?`, which is right.
3. **The probe has its own failure mode, and it looks exactly like a
   description miss.** Six of six afternoon "misses" were one-turn
   `SKILLS=<expected>` replies with no tool call. Count it
   (`declared-not-invoked`), then remove it (`--protocol strict`: 8/8
   fired). Any instrument built on "did the model do X" needs a
   "did the model *say* X without doing it" column, or it will be
   edited around.
4. **Symptom-first ordering is not a style preference; it is where the
   far case lives.** The mechanism-first fmk description lost "harden
   calc.py before we ship" to `tiny-language-implementation` (first-clause
   noun "interpreter") and the host's `security-review` ("harden",
   "ship"). Leading with "Use when asked to find bugs in an evaluator …
   to harden such code before it ships" won it back 4/4 under strict.
5. **Host skills are co-owners, not distractors.** On haiku a prompt
   about prompt caching goes to the host's `claude-api` skill 6/6; sonnet
   fires both. No description edit fixes co-ownership; record the
   territory and stop chasing (backlog item 4 closed).
6. **Persisted transcripts make marker fixes free.** `body-sia`'s two
   "misses" were regex misses on text the agent actually wrote; the fix
   was verified by re-scoring the saved transcripts, no probe spent.
7. **Distilling process rules into skills works when the rules have
   mechanisms.** Both new skills went 6/6 positives and 0/9 negatives
   under strict on the first draft, and their body cases scored 5/5 —
   because every step came from a named failure in rounds 14–101, not
   from an imagined problem (meta-skill step 1).

## 10. Honest failures / gaps
- **Process rule 10 broken a fifth time**: a `cd skills/…/scripts &&
  python3 …` compound command moved the session cwd and the next three
  commands read "No such file". Absolute paths only.
- **Chained `lint && probe` in the background does not tell you the
  probe never ran**: both launches after the description trims exited 0
  (the trailing `echo exit=$?` succeeded) while lint had failed on a
  1026-char description; ten minutes lost. Check the check before
  trusting the run, or write the sentinel *inside* the chain.
- P8 cost over by $0.79 and P11 was a proxy prediction (slash commands,
  not the skill index) — both are prediction-design misses, recorded.
- `compare_reports` calls 1/1 → 1/2 REGRESSED (unequal n → rate rule,
  −50 %); with a v3 single-run baseline the rate rule is trigger-happy.
  Acceptable this round (the case was a real protocol artifact) but the
  rule should require the smaller n ≥ 2 for a REGRESSED verdict — next
  skills round.
- Strict protocol is not yet the default: the change is one word, but
  every prior baseline is default-protocol. Both strict sentinels
  (sonnet 4/4, haiku 6/6) and a strict full baseline now exist, so the
  next skills round can flip it with a canary-checked comparison.
- The haiku strict sentinel is banded on one run of 6; widen after a
  second same-day run before trusting a DRIFT verdict from it.
- Nothing in this round is a live-API verification of the harness (still
  no key); the skills track uses the CLI, which works.
- Three new descriptions each needed 3–4 rounds of trimming to fit 1024
  chars — I wrote first and measured length after; the lint's D002 is
  the check, but a `wc -c` before writing would have saved two launches
  (the chained `lint && probe` commands silently did not run when lint
  failed; both had to be relaunched).
- `P11`'s "host skills present" is measured on `slash_commands` from the
  init event (58 entries incl. `clear`, `compact`), a weak proxy for the
  skill index — HIT trivially, and the prediction was badly designed.
