# Round 409 (harness A) — prediction bank

## 0. OBSERVATIONS ALREADY MADE before this bank was written

This bank is **NOT cold**, and saying so is the point of this section. It
was written partway through the round, immediately before launching the
verification tiers, and everything below was already known:

- `test_the_round_355_finding_reproduces_end_to_end` fails in `/tmp/wt-409`
  and passes in `/tmp/pristine-409`, both at `d71d7cd` — reproduced.
- The cause is the substring match in `recording_runner`; the fix is in and
  falsified against the old helper (`2 failed, 1 passed`).
- The four whence field-corpus tests fail in a pristine worktree and skip
  after the `field_corpus_absent` guard — measured in `/tmp/pristine-409`.
- `baseline --ref HEAD` had already been run once: `harness-fast green 961
  passed`, `whence-fast red 4 failed 1933 passed 10 skipped`.
- `classify_health_log` misreads a two-leg nuc log — measured on a
  hand-written log before the wiring existed.
- The real `nuc/run_checks_fast.sh` had run once: exit 0, 638 passed.
- `test_pristine_check.py` 84 passed, `test_nuc_health_line.py` 12 passed,
  `test_run_driver_nuc_health_check.py` 9 passed, in isolation.

Nothing in §1 may be scored as foresight about any of that. What §1 predicts
is what the WHOLE tiers do once these changes are combined, plus what the
post-commit baseline says.

## 1. Outcome predictions

- **P1** harness fast tier GREEN, **999** passed (961 at HEAD + 17 new in
  `test_pristine_check.py` + 12 `test_nuc_health_line.py` + 9
  `test_run_driver_nuc_health_check.py`)
- **P2** whence fast tier GREEN, **1947** passed (1944 + 3 net new in
  `test_field_corpus_selector.py`: 2 added, 1 split off)
- **P3** skills corpus check **0 errors**
- **P4** post-commit `baseline --ref HEAD` verdict **green**, BOTH suites
- **P5** no EXISTING harness test breaks from the `run_driver.sh` edit

## 2. Mechanism predictions

- **M1** the whence PRISTINE tier reports exactly **4 more skips** than the
  live tree (3 → 7) and 4 fewer passes — i.e. the four reds became skips and
  nothing else moved
- **M2** `logs/nuc_health_round_*.log` shows as **ignored**, not `??`
- **M3** the post-fix baseline's `harness-fast` leg stays **green** — the
  `/tmp/wt` collision is unreachable from this command at any commit, before
  OR after the fix, because its worktree path cannot prefix-match. This
  predicts the fix changes NOTHING this instrument reports, which is the
  evidence that §1 of the knowledge file has the mechanism right.
