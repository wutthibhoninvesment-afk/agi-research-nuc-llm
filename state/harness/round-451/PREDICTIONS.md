# Round 451 (harness A) — predictions, banked before measuring

Subject: `unit_tests`, the last checker in
`skills/skill-authoring/scripts/corpus_check.py`, which has reported
`TIMEOUT ... timed out after 600s` in rounds 431, 445, 448, 449 and 450 —
four of the last six — making `skills-check` report ERROR / `COULD NOT RUN`
each of those rounds. Its own source comment calls it "the slow one (~37s
vs ~3s for the five above)".

Banked at this commit BEFORE any timing run. Scored in the round file.

## DISPOSITION, fixed before the numbers (round 419's rule)

Whatever the measurement shows, I will NOT:

* raise the 600 s timeout — that converts a visible regression into an
  invisible one and buys back nothing;
* delete or `-k`-deselect tests to fit the budget — the checker's job is to
  run them;
* mark the checker `absent`/exempt.

What I WILL do, and am committing to here so no number can choose it: make
the timeout branch report what the run ACHIEVED instead of nothing. As
written, `run_one` catches `subprocess.TimeoutExpired` and returns a result
with `errors: []`, `warnings: []`, `coverage: ""` and the summary "timed out
after 600s" — i.e. 600 seconds of computation is discarded and the corpus
check says only that it could not run. That is true and useless. A checker
that ran 500 tests and got killed during the 501st knows 500 things.

The one thing that could change the disposition: if the suite is FAST solo
and only slow under the driver's concurrency, the partial-report fix is
still correct but the headline is contention, not growth, and I must say so.

## Predictions

P1. Run solo on this idle 1-core box, the exact `unit_tests` argv finishes
    in UNDER 600 s. (The driver runs four suites concurrently on `nproc`=1;
    round 435 next-step 8 measured a ~3x contention penalty.) Confidence:
    medium-low. If it exceeds 600 s solo, contention is not the story.

P2. It nevertheless takes MORE than 150 s solo — i.e. the "~37s" in the
    source comment is stale by at least 4x, and there is real growth on top
    of any contention. Confidence: high.

P3. The runtime is concentrated, not spread: the slowest 3 tests account for
    >50% of total test time as reported by `--durations`. Confidence: medium.

P4. The mechanism of the slow tests is that they invoke a checker against
    the REAL repo root (or spawn a subprocess that does) rather than against
    a tmp_path fixture — so their cost grows with the corpus every round,
    which is why a "~37s" comment rotted without anyone editing the tests.
    Confidence: high.

P5. `test_check_round_recorded.py` (1548 lines, the session-inheritance-audit
    suite, which reads `git log` and the whole knowledge/ tree) is among the
    two slowest FILES. Confidence: medium.

P6. The collected test count is > 600. The last ERROR line that carried a
    count (an early round) said "2 failed, 608 passed". Confidence: medium.

P7. Nothing in `harness/tests/test_driver_health.py` asserts that the
    corpus check's checkers actually RAN — i.e. there is no test that would
    have gone red across the five timeout rounds. Confidence: high.

P8. The timeout is a per-checker constant with no test pinning it, and
    `run_one`'s `timeout=600` default is not referenced anywhere else.
    Confidence: medium-high.

## Recorded as DERIVED BY READING, not predicted

D1. `run_one`'s timeout branch returns empty `errors`/`warnings`/`coverage`
    and a fixed summary string — read at lines 221-224 before any run. The
    claim "600 s of computation is discarded" is READ, not measured.

D2. `unit_tests` is skipped entirely on re-entry (`REENTRY_ENV`), so the
    nested invocation inside `test_corpus_check.py` does not recurse. Read
    at lines 202-208.

D3. The driver's per-checker lines only appear in `driver.log` when
    `skills-check` is non-PASS, so the absence of a `unit_tests ok` line in
    the log is a LOG-FORMAT artefact and NOT evidence the checker has never
    passed. Checked before it was asserted; 60 PASS lines exist.
