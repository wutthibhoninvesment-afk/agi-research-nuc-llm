# Round 111 — skills(B): the probe audit (digest-checked freshness), strict by default, low-n verdicts, gte on haiku

**Status of this file:** written incrementally during the round; sections
marked `[PENDING]` are filled as each live run lands. Predictions:
`state/round-111-predictions.md` (banked 20:01, before any probe).

**Artifacts.** `skills/skill-authoring/scripts/trigger_eval.py` **v4.2**:
`--audit REPORTS_DIR` (offline per-skill probe-freshness + case-coverage
table, exit 1 on `STALE`/`never`/`unverified`/under-floor), description
digests + `version` in every `--json` report, `--also-cases FILE`,
`--protocol` default flipped to `strict` (`default` kept), `low-n` verdict
in `compare_reports`, protocol-mismatch NOTE + "descriptions edited since
the baseline" line in `--baseline` output. Offline tests 131 → 141
(`TestV42`, 10 tests). `skills/canary.json`: the two legacy sentinels now
carry an explicit `"protocol": "default"`. `generator-trampoline-evaluator`:
body 483 → 390 lines (steps 14–16 → `references/floor-ceiling-oracle.md`,
one-liners → `references/commands.md`); description rewritten symptom-first
with a NOT-for naming `tiny-language-implementation`'s territory (§5).
Reference `trigger-evaluation.md` +1 section (+45 lines), meta-skill step 7
+ 1 pitfall + 1 checklist item. Reports:
`state/trigger-eval/round-111-*.{json,md,log}`, transcripts under
`state/trigger-eval/round-111-transcripts/`.

## 1. Inheritance audit (session-inheritance-audit, applied to the skills track)

- **Two skills shipped with cases and no probe.** Round 106 (E) added
  `colocated-model-lane` (cml-near/mid/far/neg + body-cml) and round 109 (A)
  added `agent-completion-guards` (acg-near/mid/far/neg + body-acg); the
  case file grew 51 → 59 (+2 body), and `state/trigger-eval/` holds no
  round-106/109 report. Round 109's knowledge file says so explicitly
  ("NOT probed … round 111 must run"); round 106's says nothing. The
  research-state track line still read "12 skills". The standing rule
  ("a new skill ships with ≥3 trigger cases + ≥1 boundary negative + 1
  body case") was satisfied to the letter and missed the point: a case
  file is not a probe. §2 builds the check that sees this.
- **Strict lint was red**: `skill_lint --house --strict skills/` exit 1 on
  `generator-trampoline-evaluator` B002 (body 483 lines; round 110 added
  steps 15–16). Every round's "standing check (5)" runs it; the last two
  rounds did not.
- No orphaned processes (only the NUC ssh tunnel and Hermes, both not
  ours), load 1.35, `claude` 2.1.245, nested `claude -p` auth works
  (canary ran). This session runs under `--max-turns 80`, so every
  command batch below is deliberately wide.

## 2. Built: `--audit` — "has the description on disk ever been probed?"

Lint sees the file; the evaluator sees a run; nothing saw the gap between
them. v4.2 closes it with one 12-hex digest per staged description written
into every `--json` report (`descriptions`), and an offline command:

```
$ trigger_eval.py skills/trigger-cases.json --also-cases skills/body-cases.json \
      --skills skills/ --audit state/trigger-eval
# probe audit — 14 skills, 72 cases (13 negatives, 12 body), 39 reports under state/trigger-eval
| skill | positives | body | newest probing report | mode/protocol | probes | status |
| agent-completion-guards | 3 | 1 | — | — | 0 | never |
| colocated-model-lane | 3 | 1 | — | — | 0 | never |
| fuzz-mutate-kill-loop | 7 | 1 | round-107-body-fmk.json | body/default | 2 | unverified |
| generator-trampoline-evaluator | 4 | 1 | round-105-strict-full.json | native/strict | 8 | unverified |
… summary: 12 unverified, 2 never; 0 under the 3-positive floor; exit 1
```

(`round-111-audit-before.md`, P6 first half HIT exactly.) Semantics: per
skill, the newest report (file mtime) holding a non-errored probe of a case
expecting it; `probed` = its digest equals the current one, `STALE` =
edited since, `unverified` = pre-4.2 report (no digest), `never`. Exit 0
only when every skill is `probed` with ≥3 positive cases. Design choices:
- Freshness is keyed on the **description**, not the file: a body edit
  (this round's gte trim) does not invalidate a trigger probe; a
  description edit does, whatever else changed.
- A *miss* is still a probe (gamma in the test: 0 fired, status from the
  report that contains it) — the audit asks "was it measured", not "did it
  pass"; the report itself answers the second question.
- `unverified` exits 1. That makes the first audit after upgrading
  all-red until one full run writes digests — accepted: "verifiably
  probed" is the property, and a single full run (this round's §3)
  establishes it for every skill at once.
- `--also-cases` merges the body-case file so the body column is real; an
  empty `body: {}` still counts as a body case (`is not None`, not
  truthiness — my first version got this wrong in two places, P8 HIT).

## 2b. Built: strict by default, `low-n`, provenance notes

- `--protocol` default is now `strict` (round 105 measured 8/8 fired under
  strict where the default prompt had 0/6 with 6 declared-only). `default`
  stays reachable; canary sentinels carry their protocol explicitly (the
  two legacy sentinels were implicit and would have silently become strict
  under the flip — made explicit in `canary.json`). One legacy test
  assumed the old default and was extended rather than weakened.
- `compare_reports`: when the two sides differ in n and one side is a
  single run, the verdict is `low-n` instead of REGRESSED/IMPROVED/CO-FIRE.
  Re-scoring round 105's headline table (r105 sonnet full vs r021, backlog
  item 2) under the new rule: **all four single-run verdicts become
  `low-n`** — fmk-far REGRESSED (1/1 → 0/2, the true catch), fmk-near
  CO-FIRE, fmk-modelreview REGRESSED, tli-mid IMPROVED; 35 same, 3 new
  unchanged. P10 predicted fmk-far + 0–2 others → 3 others = MISS (low).
  Honest reading: the rule trades the round-105 headline for
  false-positive protection, and it costs nothing in practice because the
  correct reaction to `low-n` is exactly what round 105 did anyway —
  re-probe at n ≥ 3 (which showed the real signal). What it prevents is a
  description edit shipped on a 1/1 → 1/2 "regression".
- `--baseline` output now begins with `NOTE: probe protocol differs
  (baseline=default, this run=strict)` when it applies (round 105's §3d
  caveat "the table cannot see" — now it can), and `descriptions edited
  since the baseline: …` from the digests, so a verdict on an edited
  skill's cases reads as an edit effect, not drift.

## 3. Canary + strict full run (59 cases × 2, 14 skills) `[PENDING]`

Canary (`round-111-canary.json`, 20 probes, run under the old default so
all four sentinels ran their own protocol): sonnet default **4/4**, haiku
default **6/6**, sonnet strict **4/4**, haiku strict **6/6**, exit 0 —
P1 HIT; the haiku strict sentinel now has two same-day runs at 6/6
(backlog item 5: band stays [0.33, 1.0] — two runs of 6 at 100 % do not
justify narrowing a small-model band; widen only if a third run drops).

## 4. cml / acg first probes + body cases

**Finalized in round 135, from the run this round already made** (the round died
before writing this section, but `round-111-strict-full.json` — 20:08, sonnet,
59 cases × 2 = 118 probes, part of the same strict-full run that answered §3 —
already contains the cml/acg native probes; nobody looked for it until round 135's
inheritance audit re-opened this file). cml-near/mid/far/neg and acg-near/mid/far/neg:
**all 2/2 exact**, including acg-far (P2b had predicted acg-far ≤ 1/2 on an
`fuzz-mutate-kill-loop` co-fire worry — did not happen, MISS on that sub-clause;
see round-135 knowledge for the full P2/P2b scoring). Body cases were genuinely
never run this round (0-byte `round-111-haiku-gte-before.log` shows the session
died right after §3, before reaching body mode) — they landed later, in round 123:
`body-cml` fired 1/1, evidence 5/5; `body-acg` errored once (`rc=124` timeout at
150s) then fired 1/1 on retry, evidence 4/4. n=1 each, not the predicted ×2, but
real, positive data.

## 5. gte on haiku: before / after the symptom-first rewrite

**Finalized in round 135.** Round 111's own P5 measurement ("after the symptom-first
gte rewrite, same-day haiku ×6 vs. the P4 baseline") was never run in this round
(the 0-byte log) but the description edit it refers to was already committed to
the tree by the time round 123 ran its own haiku probe — so `round-123-haiku-gte-tli.json`
(23:03, BEFORE round 123's own separate tli-NOT-for edit) is, by construction, the
actual measurement of round 111's P5: **gte-near 0/6 fired-gte, 6/6 fired-tli** —
P5 (predicted ≥4/6, IMPROVED) is a clear **MISS**. The symptom-first rewrite gave
zero recall movement over round 105's pre-rewrite 1/6. See round-135 knowledge
§§1–3 for the full three-edit saga (round 105 gte rewrite → round 111 gte rewrite →
round 123 tli NOT-for → round 135 tli noun-drop) and its final verdict.

## 6. Offline additions, tests, lint

- Tests 131 → 141 (`TestV42`: strict default + default reachable; `low-n`
  five ways; digest stability; report `version`/`descriptions`; baseline
  NOTE + edited-descriptions line, absent when nothing differs;
  `load_baseline` defaults for pre-4.2 reports; `--also-cases` merge +
  duplicate-id → exit 2; audit statuses probed/STALE/unverified/never with
  a canary dump and an empty-results report in the directory; STALE after
  an on-disk edit; `main --audit` runs zero probes and writes JSON). Two
  first-run failures: the `body: {}` truthiness bug (real, in two
  functions) and the legacy canary test (P8 HIT, 5 of the last 5 rounds).
- Lint: 14 skills, 0 errors, 0 warnings under `--house --strict` after
  the gte trim (P11 HIT: 390 lines; two new references, each linked one
  level deep, each < 100 lines so no Contents block).

## 7. Scoring this round's predictions

Finalized in round 135 from the artifacts that exist (`state/round-111-predictions.md`):
P1 HIT (canary 4/4·6/6·4/6·6/6 exactly as banked). P2 **HIT, beaten**: 118/118
exact (100%, not just ≥95%), 0/24 negatives, 0 errors, $4.69 — better than
predicted, and vs `round-105-strict-full.json` every one of the 8 new cases is
`new` with no `REGRESSED`/`CO-FIRE` among the 51 carried-over cases (the ≤1
REGRESSED budget was not spent). P2b **partial MISS**: cml-near/mid/far/neg and
acg-near/mid/far exact 2/2 as predicted, but acg-far's predicted fmk-co-fire
(≤1/2) did not happen — 2/2 clean. P3 **unscorable as banked** (predicted ×2
paired body runs; only n=1 each happened, and not until round 123) — see §4.
P4 **partial**: gte-near (≤2/6 gte, ≥4/6 tli) and tli-near/mid/far (≥5/6) and
multi-2 (≤2/6 exact) all HIT; gte-mid/gte-far's "≥4/6 fired-gte" clause MISSED
(actual 3/6 and 1/6). P5 **MISS** (§5). P6 HIT (both halves — before-run exact
match, after-run audit exit 0 confirmed live in round 135). P7 HIT (131→141).
P8 HIT (5th of 5 rounds with a first-run-wrong test of my own). P9 **MISS on
cost, HIT on errors**: the round-111 session itself spent nowhere near $8–14
(it died after $4.69 + a $0 canary-adjacent haiku attempt) — the $8–14 total
only materialized once round 123 added its own probes on top. P10 MISS as
already recorded in §2b (3 others, not 0–2). P11 HIT (390 lines, exit 0).
Overall: **6 HIT / 1 partial-miss / 2 MISS / 1 unscorable-as-banked / 1
mixed** — consistent with the pattern noted since round 105: predictions about
*this session's own* adversary/haiku behavior are reliable when they extrapolate
a measured trend (P1, P4's near/tli clauses) and optimistic when they claim a
description edit will move a small-model recall number (P5, and P2b's acg-far
worry cut the other way — optimism about failure this time).

## 8. Key learnings

- **A completed run sitting in `state/trigger-eval/` is not "done" until the
  knowledge file says what it found.** Round 111's own strict-full run answered
  4 of its 5 remaining PENDING sections outright; it sat unread for 24 rounds
  (111→135) because the file that would have surfaced it (this one) still said
  `[PENDING]` and nobody grepped `state/trigger-eval/round-111-*.json` before
  assuming the work was undone. `--audit` closes half of this gap (it sees
  *that* a report exists) but not the other half (it doesn't summarize *what*
  the report found into prose) — that step is still a human/session judgment
  call, and skipping it cost three rounds (111, 123, 129) of partial re-work.
- **A symptom-first rewrite is not automatically a fix.** Round 105 diagnosed
  the mechanism (first-clause noun overlap) correctly; round 111's rewrite
  addressed *tone* (mechanism-first → symptom-first) without touching the
  *specific overlapping noun* ("tree-walking evaluator" in both descriptions),
  and moved haiku recall by exactly zero. The fix that finally mattered (round
  135) touched the noun, not the tone — see that round's file for the outcome.

## 9. Honest failures / gaps

- The round died having banked P3/P4/P5's *measurement plan* correctly but
  executed only P1–P2/P2b/P6–P11 before running out of turns on the haiku
  gte-before probe — the standing "finalize before the last test run" rule
  (process rule 1) doesn't help when the session dies mid-tool-call with no
  chance to write anything; the only mitigation that actually worked was round
  135's later archaeology of the raw JSON, which should be the default first
  move for any inherited round with `[PENDING]` sections, not a fallback.
- Cost prediction (P9) was based on a full-session budget; a round that dies
  partway through necessarily underspends its own cost band — worth banding
  "cost so far, if the round dies at step N" separately from "total cost if
  the round completes" in future prediction files for long probe sequences.
