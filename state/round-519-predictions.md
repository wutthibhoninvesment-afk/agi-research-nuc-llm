# Round 519 (skills B) — predictions, banked BEFORE measuring

Subject: round 516's next-step #5 / round 518's next-step #7 — run
`languages/whence/checkscope.py --selfref` over `harness/tests/` and
`skills/`, which round 516 called "mechanical", and round 518's next-step
#3, which names a live assertion (`x == f(x)`) that `--selfref` cannot see.

Banked before any sweep of `harness/tests/` or `skills/` was run and before
a line of `checkscope.py` was edited. D-013.

## ALREADY OBSERVED (facts, not predictions — stated so they are not scored)

- `cd languages/whence && python3 checkscope.py --selfref` at HEAD:
  **7 rows** — `test_assertshadow.py:455`, `test_subjprov.py:504/588/591/632/683`,
  `test_testcorpus_contributions.py:159`. Three of them `[via a JOIN]`.
- `languages/whence/tests/test_testcorpus_contributions.py:431`
  (`test_the_ledger_on_disk_round_trips_through_its_own_encoding`,
  `assert raw == again`) is **NOT** among those 7. Round 518 #3 names it as
  the shape nobody's checker sees; that it is absent from the baseline is
  read off the baseline above, not predicted.
- File counts: `harness/tests/test_*.py` 96, `languages/whence/tests/test_*.py`
  78, `skills/skill-authoring/scripts/test_*.py` 13.
  (`ls <dir>/test_*.py | wc -l`)
- `ls skills/test_*.py` → "No such file or directory".
- `checkscope.DECLARED_SOURCES` = 6 names, `LIVE_SOURCES` = 10,
  `JOIN_SOURCES` = 1. Read from the source at HEAD.

## Baseline table (re-derived at HEAD, with the command)

| # | quantity | value at HEAD | command |
|---|----------|---------------|---------|
| B1 | `--selfref` rows, whence tree | 7 | `cd languages/whence && python3 checkscope.py --selfref` |
| B2 | test files, harness / whence / skills-scripts | 96 / 78 / 13 | `ls <dir>/test_*.py \| wc -l` |
| B3 | `corpus_check.py --precommit` wall time | 36.4 s (round 513, NOT re-derived — see P12) | `python3 skills/skill-authoring/scripts/corpus_check.py --precommit` |

## Predictions

| # | class | prediction | band |
|---|-------|-----------|------|
| P1 | STRUCTURAL | `--selfref --tests harness/tests` reports **0** rows — an empty population, not a clean tree. Cause: `_classify` returns OTHER unless one of the 17 hard-coded whence helper names is CALLED, so `_derived_operands` returns <2 operands for every assert in a tree that does not use those helpers. | exactly 0 |
| P2 | STRUCTURAL | `--selfref --tests skills/skill-authoring/scripts` reports **0** rows, same cause. | exactly 0 |
| P3 | STRUCTURAL | `--selfref --tests skills` reports 0 by a SECOND and independent mechanism — `selfref_asserts` does a non-recursive `os.listdir` for `test_*.py` and `skills/` has none at top level. It will not crash. | 0 rows, exit 0 |
| P4a | RATE | The six `DECLARED_SOURCES` names appear **0** times as calls in `harness/tests/` and `skills/skill-authoring/scripts/` combined. | 0 |
| P4b | RATE | At least one `LIVE_SOURCES` name (`census`, `registry`, `scan_file`, …) DOES appear in those two trees — so some asserts there classify LIVE and are skipped by the `== LIVE: continue` branch, i.e. the zero has two causes and not one. | ≥1 file |
| P5 | STRUCTURAL | The blindness in P1/P2 and the blindness round 518 #3 names are THE SAME DEFECT, not two: both are "the document was read the plain way (`open()` / `json.load()`) instead of through a named helper". A repair that fixes one fixes the other. | one repair, both close |
| P6 | STRUCTURAL | After widening DECLARED detection to direct disk reads, the whence baseline grows strictly: `test_the_ledger_on_disk_round_trips_through_its_own_encoding:431` becomes reported. | ≥8 rows, and line 431 present |
| P7 | STRUCTURAL | A naive widening (any `open`/`json.load` counts as DECLARED) OVER-fires on `harness/tests/`, because those tests write a tmp file and read it back — which is `x == f(x)` on data the test itself created and is NOT a vacuous gate. | naive run over `harness/tests` > 40 rows |
| P8 | STRUCTURAL | Therefore the repair needs a guard: a path the same function WROTE (or that derives from `tmp_path`/`tempfile`/`mkdtemp`) is not the declared document. With the guard, `harness/tests/` reports far fewer. | guarded harness count < 1/4 of the naive count |
| P9 | — | **NO BASIS.** I have not opened `languages/whence/tests/test_checkscope.py` and cannot say how many nodes pin `--selfref` counts, nor how many rows the guarded sweep finds in each tree. I will report the numbers rather than bet on them. Recorded so the report cannot claim a hit it never risked. | report only |
| P10 | STRUCTURAL | ≥1 existing test node will need editing. Round 518 banked the opposite (P13: "no existing test needs editing") and was REFUTED; the shape is that a count-pinning node moves whenever the count moves, and `--selfref` output is exactly a count. | ≥1 node edited |
| P11 | RATE | Of the rows the guarded repair adds across all three trees, the MAJORITY are round-trip/encoding shapes (`raw == dumps(load(raw))`, `json.load(a) == json.load(b)`) rather than the whence baseline's totals-sum-to-themselves shape. | >50% of new rows |
| P12 | machine-state | `corpus_check.py --precommit` re-derived at HEAD on this `nproc=1` box, nothing else running: 30–75 s (B3 is round 513's 36.4 s and six rounds of checkers have landed since). If another pytest is running concurrently, 2–3× that. | solo 30–75 s |
