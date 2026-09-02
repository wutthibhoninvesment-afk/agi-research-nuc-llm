# Round 441 (skills B) — predictions banked BEFORE measurement

Rule D-013: written before any of the runs below. Scored honestly in
`knowledge/round-441-*.md`. Where I have no basis I say so rather than
guessing (round 439's rule 7 / round 438's D8).

**Target.** Two things the pre-flight and the corpus check put in front of
this round:

1. The record-gap check reports `languages/whence/examples/agi_buy_and_hold.lang`
   as an unattributed working-tree path and tells me to put a
   foreign-system leftover in `state/known-standing-dirty-paths.json`. Its
   fourteen siblings are in that registry **and** in `.gitignore`. Round 440
   separately recorded that `test_field_corpus_selector.py::
   test_the_live_tree_has_no_drift` is RED for this same file.
2. `claim_check` has published `coverage … 0/336 commands` on every
   corpus-check line for as long as the standing item has been carried. It
   owns a `--run` tier that executes the `auto`-classified commands and
   diffs their real output against the `# expected:` claim. Nothing has ever
   run it over the corpus.

## Baselines, re-derived at HEAD this session, each with its command

| baseline | value | command |
|---|---|---|
| corpus check, whole | `10 checker(s), 0 error(s), 6 warning(s)` | `./skills/run_checks_fast.sh` (2m51.9s wall) |
| claim_check line | `206 path(s) resolved, 37 unresolvable-by-design; 0 stale claim(s) of 206 checked; coverage 206/243 paths, 0/336 commands` | same run |
| corpus unit tests | `894 passed in 148.41s` | same run |
| skills on disk | 81 entries, 77 with a SKILL.md per `skill_lint` | same run |
| `verb_audit` V002 | **0** (the round-433/439 carried red is green at HEAD) | same run |
| slow-tier per-round logs on disk | exactly 1 (`logs/slowtier_round_440.log`) | `ls logs/slowtier_round_*.log` |

## What I have already READ at bank time

- `curecheck.field_corpus_drift()` (`languages/whence/curecheck.py:1044-1061`)
  — it shells out to `git ls-files --others --exclude-standard examples`.
- `.gitignore`'s fourteen `languages/whence/examples/*.lang` lines and their
  round-402 rationale.
- `state/known-standing-dirty-paths.json`'s `_comment` and
  `_round_349_addendum`.
- `run_driver.sh:647-661` (the slow-tier slice call site) and `.gitignore`'s
  four existing `logs/*_round_*.log` patterns.
- `claim_check.py`'s docstring, `classify()`, and
  `n_ran = n_auto if args.run else 0`.

I have NOT run `claim_check --list` or `--run`, have not counted the `auto`
set, and have not run any git command with an extra exclude file.

## Predictions

**P1 — the ignore line is a silencer.** Adding
`languages/whence/examples/agi_buy_and_hold.lang` to `.gitignore` — the move
`.gitignore`'s own fourteen sibling lines and the record-gap check's advice
both point at — turns `test_field_corpus_selector.py::
test_the_live_tree_has_no_drift` **from RED to GREEN with the census still
declaring 14 files and the fifteenth still on disk**. Basis: `--exclude-standard`
honours `.gitignore`, and `field_corpus_drift` computes `untracked - declared`.
So the two records stay in contradiction and the detector stops saying so.
Confidence: high — read the code, not yet run.

**P2 — and `known-standing-dirty-paths.json` is not.** Adding the same path
to that registry instead suppresses the record-gap check's unattributed-path
line and leaves `test_the_live_tree_has_no_drift` RED, because nothing in
`curecheck.py` reads that registry. Confidence: high.

**P3 — the slow-tier log has exactly one reader.** `logs/slowtier_round_*.log`
is written by `run_driver.sh` and read by nothing else in-tree, so ignoring
it is NOT a P1-shaped silencer. Prediction: `grep -rn "slowtier_round"` over
tracked source (excluding `logs/`) returns exactly ONE hit, `run_driver.sh:649`.

**P4 — the `auto` set is small.** Of the 336 commands `claim_check` counts,
I predict **fewer than 80** classify `auto`. Basis: the allowlist fails
closed and the corpus is 77 skills of mostly repo-specific scripts.
Point estimate: **45**.

**P5 — the dominant `manual` reason is the fail-closed one.** The single
largest `manual` reason bucket will be `unknown program: allowlist has no
entry (fails closed)`, with more instances than all other reasons combined.

**P6 — `--run` finds at least one stale claim.** A tier that has never run
over 77 skills authored across ~100 rounds will report **>= 1** C002
finding. Point estimate **3**. If it reports 0 I will say so and treat the
zero as the finding (`zero-rate-needs-a-distance`).

**P7 — some `auto` command fails to EXECUTE, not just to match.** At least
one allowlisted command will return non-zero or time out rather than
produce output that can be diffed against a claim — i.e. C002 is not the
only way `--run` goes red. Confidence: medium.

**P8 — `--run` is affordable.** Whole-corpus `--run` completes in under
**300 s** on this 1-core box. Basis: no basis beyond the allowlist's
"cheap, offline, read-only" contract; this is the weakest prediction in
the bank and I flag it as such.

**P9 — 0/336 is structural.** Neither `corpus_check.py` nor
`run_checks_fast.sh` has any flag, env var or config that would pass
`--run` through to `claim_check`; the 0 is unreachable from the wired
entry point rather than turned off. Confidence: high.

**P10 — no basis, and I will measure rather than guess.** (a) Whether any
C002 finding, if one exists, is in a skill this program authored versus in
`skill-authoring`'s own Verification block. (b) Whether the `auto` commands
are concentrated in a few skills or spread across many. I have read nothing
that bears on either; both will be reported as measurements.
