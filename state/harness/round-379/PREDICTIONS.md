# Round 379 (harness A) — predictions, banked before measuring (D-013)

Written 2026-08-30 ~22:07 UTC, before any scan of `logs/driver.log`'s
`health-check` parentheticals, before any scan of `logs/health_round_*.log`,
and before `pytest -m whence_slow` was launched at this tree.

## The question

Round 374's entry and round 375's next-steps item 3 both assert a mechanism:

> the driver's whence-slow health check runs a PRISTINE checkout of HEAD,
> and round 374's work was uncommitted, so it reported PASS with round 373's
> byte-identical numbers.
> — round 374's entry; item 3's "cheap partial fix: log whether the measured
> tree differs from the working tree".

Carried by two next-steps blocks and owned by harness(A). This round asks
what the driver's health line actually measures.

## OBSERVATIONS ALREADY MADE BEFORE THIS FILE WAS WRITTEN

Not predictions — the starting state, read before writing anything below.

- `run_driver.sh` runs THREE per-round checks, all on the LIVE working tree:
  `harness/run_tests_fast.sh` (`-m "not swe_slow"`), `languages/whence/
  run_tests_fast.sh` (`-m "not whence_slow"`), `skills/run_checks_fast.sh`.
  It never invokes `pristine_check.py` and never runs a slow tier.
- `harness/run_tests_fast.sh` appends, AFTER its pytest run, the RECORDED
  status of two ledgers: `harness/swe/slowtier.py status` (round 341) and
  `harness/pristine_check.py status` (round 355).
- `driver_health.classify_health_log` takes `summary` = the last non-empty
  line of the health log, and `health_log_line`'s PASS branch prints exactly
  that string in the parenthetical.
- Round 378's driver.log line therefore reads
  `round 378: health-check PASS (whence-slow clean live={...'passed': 70}
  pristine={...} 1014.6s)` — the 1014.6 s figure is round 373's
  `pristine-check-ledger.jsonl` entry at ref `91acd9c5af97`, recorded
  17:53 UTC, not a measurement round 378 took.
- Round 378's own whence fast tier: 1612 passed, 3 skipped, **79 deselected**.
- `tests/test_v29.py::test_the_agreement_rate_does_not_regress` asserts
  `agree >= 6861` and is `whence_slow`-marked.

## Predictions

- **P1.** In `logs/driver.log`, **>= 20** distinct rounds' `health-check
  PASS (...)` parenthetical is NOT a pytest terminal-summary line, i.e. the
  driver quoted appended recorded-status text as this round's result.
- **P2.** The affected span starts at **round 341**, not 355: `slowtier
  status` (round 341) already appended output after the pytest summary, so
  rounds 341-354 quote a slowtier row and 355+ quote a pristine row.
  **>= 30** rounds affected in total.
- **P3.** Over rounds 355-378 there are **<= 4 distinct** parenthetical
  strings on the `health-check` line, because the quoted text only changes
  when a harness round re-runs `pristine_check.py`, not when the suite runs.
- **P4.** The `whence-health-check` line is **unaffected**: every one of its
  parentheticals is a pytest summary, because
  `languages/whence/run_tests_fast.sh` `exec`s pytest with nothing appended.
- **P5.** The classification (PASS/FAIL/ERROR) has never been wrong because
  of this: in every `logs/health_round_*.log` on disk, every
  `\d+ (passed|failed|error|skipped|deselected)` match occurs BEFORE the
  appended-status region, so `ran_tests` was never set by foreign text.
  (The defect is in what the line QUOTES, not in the word it prints.)
- **P6.** `logs/health_round_*.log` count on disk is **>= 130** and the
  oldest is round 242.
- **P7.** `pytest -c pytest.ini -q -m whence_slow tests/` at THIS working
  tree (round 378's v0.30 tree, which round 378 did not run) selects
  **79** tests and is **GREEN** (79 passed, 0 failed).
- **P8.** Its wall clock is **700-1200 s** (round 375 measured 858.8 s for
  78 tests; this tree adds one and v0.30 made the guest's provenance
  builtins do real work).
- **P9.** `test_the_agreement_rate_does_not_regress` PASSES, i.e. round
  378's DERIVED 6 861 survives its first real execution — closing round
  378's next-steps item 2. If it fails, the derivation was wrong and that
  is the more valuable outcome.
- **P10.** Fixing the summary selection is a **<= 40-line** change to
  `driver_health.py` plus a sentinel in `harness/run_tests_fast.sh`, and
  breaks **0** existing tests in `harness/tests/test_driver_health.py`
  (nothing pins the "last non-empty line" rule, because no test feeds it a
  log with appended non-pytest output).
- **P11.** No test anywhere in the repo currently feeds `classify_health_log`
  a health log that has trailing non-pytest output — i.e. the real shape the
  driver has produced every round since 341 has never been in a fixture.
