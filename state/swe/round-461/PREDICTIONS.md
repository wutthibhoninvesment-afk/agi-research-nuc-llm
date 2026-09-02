# Round 461 (SWE-loop D) — predictions, banked BEFORE measuring

Rule D-013. Written at the start of the round, before any of the commands
below were run. Scored honestly in
`knowledge/round-461-the-checker-that-was-a-suite.md`.

## What this round is doing

Round 455's next-steps item 2, verbatim: "`skills-check` has no per-node
ground truth, so the headline rate is over THREE checks, not four. Its logs
are a checker/verdict table. `redattrib.py` prints a GRAMMAR GAP line on
every run saying so; teaching it that grammar would let round 453's 16
episodes be reproduced or refuted inside the same instrument."

Plus round 455's item 6: one registry classification deliberately left at its
weaker reading (`test_run_driver_whence_health_check.py::
test_whence_health_check_fail_logged_when_script_fails`, declared
`own-suite`, arguably `shared-file-own-content`).

## Already OBSERVED before this file was written — NOT predictions

These were read while deciding what to do and are recorded here so no HIT
below is claimed for something already seen:

- `logs/skills_health_round_*.log` — 97 files exist.
- `logs/driver.log` records skills-check PASS 67, FAIL 25, ERROR 5.
- The log grammar is `"%-18s %-22s %s" % (check, flag, summary)` from
  `corpus_check.py` main(), with `flag` one of `ok`, `warn <codes>`,
  `ERROR <codes>`, or a bare status word `TIMEOUT`/`ABSENT`/`ERROR`.
- `run_one()` writes each checker's stdout to a `tempfile.mkstemp` sink and
  `os.unlink`s it in a `finally`, so `unit_tests`'s failing pytest node ids
  are not retained anywhere.
- Round 453 reported, for rounds 364-452: 24 red runs of 89 (27%), 16
  episodes, mean 1.50, longest 4; openers language(C) 7, SWE-loop(D) 6,
  harness(A) 2, NUC(E) 1, skills(B) 0; closed by skills(B) 9 of 15.

## Predictions

### The instrument at HEAD (baseline, not yet run)

- **P1** `python3 harness/redattrib.py attribute` at HEAD reports an
  invisible-open rate of **15/28 = 54%**, i.e. round 455's published headline
  re-derives UNCHANGED five rounds later. Confidence: low-medium. Rounds
  456-460 each added four per-round logs and any new red opens a new episode.
- **P2** `python3 harness/redattrib.py audit` exits **0** at HEAD (no R001:
  nothing has gone red since round 455 that is undeclared). Confidence:
  medium.
- **P3** `harness/tests/test_redattrib.py` is **19 passed** at HEAD.
  Confidence: high.
- **P4** `logs_read` at HEAD is **greater than 554** (round 455's number) —
  specifically **574** (554 + 5 rounds x 4 checks). Confidence: medium; a
  check that did not run in some round makes this an over-estimate.

### Reproducing round 453 inside the instrument

- **P5** Restricting the new parser to rounds 364-452 reproduces round 453's
  **24 red runs of 89** EXACTLY. Confidence: medium-high — both read the
  same files, but 453 anchored on the `corpus-check:` summary line's
  `N error(s)` token and this round will anchor on the per-row `ERROR` flag,
  which is a different derivation of the same quantity.
- **P6** The same restriction reproduces **16 episodes**. Confidence: medium.
- **P7** The opener distribution reproduces exactly: language(C) 7,
  SWE-loop(D) 6, harness(A) 2, NUC(E) 1, skills(B) **0**. Confidence: medium.
- **P8** Any disagreement between the row-level and summary-level
  derivations, if one exists, is caused by a `TIMEOUT` row: a checker killed
  mid-run contributes to neither `N error(s)` nor a per-row `ERROR` flag in
  the same way. Confidence: medium.

### The new per-checker measurement

- **P9** The number of DISTINCT checkers that have ever carried an `ERROR`
  flag in a retained log is **7** (of the ten that exist today).
  Confidence: low.
- **P10** `unit_tests` is the checker with the most red rounds.
  Confidence: high.
- **P11** Exactly **5** retained skills-check logs carry a `TIMEOUT` row,
  and they are rounds **431, 445, 448, 449, 450** — `run_one`'s own
  docstring names those five. Confidence: high (re-derivation of a source
  comment, not a guess).
- **P12** Zero skills-check episodes are `born_red` (the check's first
  retained run, round 364, was green). Confidence: medium.

### The headline that changes

- **P13** Folding skills-check in RAISES the overall invisible-open rate
  above round 455's 54%, to **>= 70%**. Reason: round 453 measured 0 of 16
  episodes opened by skills(B), and `skills` is in no other track's
  `_track_suites` row, so essentially every skills-check episode is
  invisible by construction. Confidence: medium-high on the direction, low
  on the number.
- **P14** The whole-tree vs own-suite contingency result of round 455
  (12/16 vs 1/9, Fisher two-sided p = 0.0036) STRENGTHENS — p gets smaller —
  once skills-check episodes are added, because they are whole-tree and
  invisible. Confidence: medium.
- **P15** At least one new R001 finding fires when the skills-check nodes
  first enter the fail-closed registry, i.e. the registry must be extended
  before `audit` can exit 0 again. Confidence: high (that is the design).

### Round 455 item 6

- **P16** Reclassifying `test_whence_health_check_fail_logged_when_script_
  fails` from `own-suite` to `shared-file-own-content` moves own-suite's
  invisible count from **1/9 to 0/9**. Confidence: medium-high (round 455
  states this; it is a re-derivation).
- **P17** The reclassification does NOT change the overall invisible-open
  rate, because `visible_to_opener` is computed from the hosting SUITE and
  the opening track, never from `subject_scope`. Confidence: high.

### Process

- **P18** The `unit_tests` row is the granularity floor: no retained
  artefact anywhere in the repo names which pytest nodes failed inside a red
  `unit_tests` row, for any round. Confidence: high.
