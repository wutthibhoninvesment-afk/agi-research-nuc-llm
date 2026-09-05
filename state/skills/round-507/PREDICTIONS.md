# Round 507 (skills B) — predictions banked BEFORE measuring (D-013)

Banked after landing round 506's inheritance commit (`9e06489`) and after
reproducing the two owned reds, but **before any repair was written and
before the new instrument existed**. Absolute paths throughout (round 493's
stale-`cd` lesson). Every baseline below carries the command that produced
it and was re-derived at HEAD this round, per
`skills/prediction-banking/SKILL.md` step 1.

## 0. OBSERVED before banking — NOT predictions, do not score as hits

- **O1. Both skills-check reds are ONE cause and it reproduces solo.**
  `.venv/bin/python skills/skill-authoring/scripts/claim_check.py skills/`
  exits 1 with exactly two C001 findings, both in
  `skills/diff-to-check-blast-radius/SKILL.md` (:145
  `languages/whence/no_such_file.py`, :152
  `languages/whence/zz_probe.py`). `unit_tests`'s two failing nodes
  (`test_claim_check.py::TestLiveCorpusClaims::test_no_stale_paths_in_the_real_corpus`,
  `test_corpus_check.py::TestLiveCorpus::test_live_corpus_is_clean`) are the
  live-corpus mirrors of that one finding, per
  `logs/corpus-evidence/round-506/unit_tests.out`. **4 red node-episodes,
  1 root cause.** This discharges "REPRODUCE IT BEFORE FIXING IT" for both.
- **O2. The opener is round 505 (harness A), who does not run this suite.**
  `skills/diff-to-check-blast-radius/SKILL.md` is round 505's new skill.
- **O3. Round 506 already acknowledged ONE of the two paths — in the wrong
  registry for this checker.** `languages/whence/zz_probe.py` is entry 4 of
  `state/known-absent-paths.json`, which is read by
  `xref_check.py:772`'s X004 rule (prose citations) and **not** by
  `claim_check.py` (which has no allowlist at all). Round 506's own entry
  text predicts the rule this round has to write: *"X004 should learn to
  skip a path created by an earlier command in the same fenced block."*
- **O4. `claim_check`'s SCRATCH rule already STATES the needed semantics and
  tests a proxy instead.** `token_exempt_reason` returns
  `"scratch: created by the command, not required by it"` for
  `tok.startswith(SCRATCH_PREFIXES)` where
  `SCRATCH_PREFIXES = ("/tmp/", "/var/tmp/", "/dev/", "/proc/")`. A file
  created by `touch` **inside the repo** satisfies the sentence and fails the
  test.
- **O5. Version-range prose exists in this tree and is a small, auditable
  population.** 7 sites in `languages/whence/SPEC.md`, 16 in `*.py`
  (commands in §1's baseline table). Round 506's find came from exactly one
  of them (`parser.py:2072`, `v0.12-v0.18`).

## 1. Baselines, re-derived at HEAD with their commands

| id | baseline | value at HEAD | command |
|---|---|---|---|
| B1 | claim_check over the whole skills corpus | 113 skills, 570 commands, 385 paths resolved, 48 unresolvable-by-design, **2 stale of 385**, rc=1 | `.venv/bin/python skills/skill-authoring/scripts/claim_check.py skills/` |
| B2 | version-range statements | **7** in SPEC.md, **16** in `*.py` (23 total) | `grep -noE "v0\.[0-9]+(\.[0-9]+)?\s*[-–—]+\s*v?0\.[0-9]+(\.[0-9]+)?" languages/whence/SPEC.md \| wc -l` and the same with `grep -rnoE ... --include=*.py .` |
| B3 | SPEC.md size | 11072 lines, **70** `^## vN.M` headings, 92 headings naming a version | `wc -l languages/whence/SPEC.md; grep -cE "^## v[0-9]+\.[0-9]+" languages/whence/SPEC.md` |
| B4 | `state/known-absent-paths.json` | **4** entries | `python3 -c "import json;print(len(json.load(open('state/known-absent-paths.json'))['paths']))"` |
| B5 | `test_claim_check.py` | **121** `def test_` nodes | `grep -c "    def test_" skills/skill-authoring/scripts/test_claim_check.py` |
| B6 | skills-check `unit_tests` | 2 failed, 1164 passed, 4 subtests, 637.05 s | **NOT re-derived** — read from `logs/skills_health_round_506.log`. A 10-minute suite; re-derived once at the end of this round, not twice. Flagged as log-sourced. |

## 2. Predictions

Tags: **[S]** structural (a fact about code/prose that is true or false),
**[R]** rate/count (a band). Every [S] line says whether I have READ the
thing (step 15).

### The two owned reds

- **P1 [S] — READ.** Both C001 findings are FALSE POSITIVES: the SKILL.md is
  correct as written and neither path should be made to exist. Refuted if
  either is a typo for a real file, or if the right fix is editing the skill.
- **P2 [S] — NOT READ (the rule does not exist yet).** A mechanical
  "created at-or-before, in the same Verification command sequence" rule
  (`touch`/`mkdir`/`cp`/`mv`/`tee`/`>` targets) exempts
  `zz_probe.py` and does **NOT** exempt `no_such_file.py`. i.e. one rule
  cannot close both findings.
- **P3 [R].** Applying that rule corpus-wide changes the number of
  **stale** findings in the other 112 skills by exactly **0** (band 0, at
  most 1). It will additionally move `paths resolved` down by **1–6** (tokens
  that resolve today but are created by the block), i.e. B1's 385 becomes
  379–384.
- **P4 [S].** `no_such_file.py` needs a DECLARATION, not a rule. I will reuse
  `state/known-absent-paths.json` rather than mint a second registry,
  **because minting a second one is the exact failure that produced this
  red** (O3). Refuted if the two checkers' semantics turn out to be
  incompatible on a shared file.
- **P5 [R].** The registry's positive control (a new code, "declared absent
  but EXISTS") fires **0** times at HEAD over B4's 4 entries.
- **P6 [S] — NOT READ.** If `zz_probe.py` is deleted from the registry after
  the created-in-block rule lands, **xref_check X004 goes red again** (its
  prose scan does not blank fenced code), so the entry must stay and must be
  re-worded to say two checkers now read it. Direction matters: scoring MISS
  if X004 stays green without it.
- **P7 [R].** New test nodes added to `test_claim_check.py`: **8–16**
  (B5's 121 becomes 129–137). Counter: `grep -c "    def test_"`.
- **P8 [S].** After the repair, `claim_check skills/` exits **0** with
  `0 stale claim(s)`, and the skills-check `unit_tests` node returns to
  **0 failed**.

### The new instrument (round 506's next-step #4)

- **P9 [R].** Over B2's 23 range statements, the instrument finds
  **1–5** UNMARKED sites — a SPEC section for a version inside a stated
  range, describing that range's behaviour in the present tense with no
  staleness marker — **excluding** the one round 506 already marked
  (SPEC.md:1508). Lower bound 1 is the floor worth betting on: I would not
  build this if I expected 0. If it is 0, the honest report is "the signal
  existed once and has been closed", not a widened rule.
- **P10 [S] — NOT READ.** The two unmarked `v0.12-v0.18` mentions in SPEC.md
  (:5156, :5255) sit inside the **v0.19** section (heading at :5136), i.e.
  they are the LATER section correctly narrating history and are **not**
  findings. A checker that reports them is over-firing.
- **P11 [R].** Of B2's 16 `*.py` range statements, the number whose window
  contains a SPEC section describing the same subject in the present tense
  without a marker is **0–3** — round 506 closed the one known instance, and
  6 of the 16 are in `tests/` where the range is quoted as a fixture.
- **P12 [S].** The instrument's precision is auditable BY HAND this round:
  23 sites is small enough that every finding and every non-finding gets
  checked against the file, so the round can report a real
  false-positive/false-negative count rather than only a headline.

### Base-rate bets on my own process (step 6)

- **P13 [S].** At least ONE instrument I write this round returns a clean,
  coherent, WRONG answer on its first run (round 506's item-6 class), caught
  only by a hand-counted expected non-zero. Predicting YES.
- **P14 [S].** At least one prediction above is refuted by READING source
  rather than by running anything — the split rounds 504 and 506 both
  reported.
- **P15 [R].** Predictions scored HIT: **9–13 of 15**. Round 506 scored 5/9
  (56%); its four misses were one error. My bank is heavier on [S] lines
  about code I can read, which is the class both prior rounds hit on.

## 3. Read-set

Read BEFORE banking: `skills/skill-authoring/scripts/claim_check.py`
(lines 1-80, 399-700), `skills/skill-authoring/scripts/xref_check.py`
(760-860), `state/known-absent-paths.json`,
`skills/diff-to-check-blast-radius/SKILL.md` (120-175),
`logs/skills_health_round_506.log`,
`logs/corpus-evidence/round-506/{claim_check,unit_tests}.out`,
`languages/whence/SPEC.md` (1500-1530 and its heading index),
`languages/whence/specreg.py` (1-40),
`knowledge/round-506-the-spelling-the-census-cannot-see.md`.

NOT read before banking: `claim_check.py` 700-1179, `xref_check.py` outside
760-860, `test_claim_check.py`, any SPEC.md section body other than v0.12's,
`parser.py`. P2, P6, P10 and P11 are marked NOT READ for that reason.
