# Round 389 (SWE-loop D) — predictions, written BEFORE any measurement

Rule D-013. Task: round 383's next-step items 1, 2, 3 and 5 — raise the oracle
suite's depth ceiling and re-run; report `render`'s silent pair cap; derive
`FRAME_SLACK` from `FAST_MAX_DEPTH`; put the injected-bug tests in the fast tier.

Experiment: a PAIRED A/B over the same `ProgramGen(seed, stress_rate=0.5)`
seeds, arm A `max_depth=500` (the suite's ceiling since round 110), arm B
`max_depth=5000` (round 383's ask). Both arms run at TODAY's tree, because
rounds 384/386/387 changed `languages/whence/` after round 383's sweep, so
round 383's rows are not a valid control.

| # | prediction | basis |
|---|---|---|
| P1 | Arm B's T-SPACE fire rate is **< 1.0 %** of usable rows (arm A: 10.8 % over 677) | round 383's ladder: 70 of 73 censored seeds demand <= 5000 |
| P2 | Arm A at today's tree reproduces round 383's T-SPACE fire SET on the shared seeds **exactly** (same seeds, not just same count) | tail semantics last moved at round 366; 384/386/387 touched rendering and miss messages |
| P3 | Arm B surfaces **0 new `mismatch`** verdicts on any oracle | the deeper comparisons are of a tail-vs-lifted answer the language has been hardened on since round 366 |
| P4 | Arm B produces **>= 1 new `timeout`** (kind flip ok -> timeout) at the unchanged `timeout_s=3.0` | a 10x ceiling on the same 3 s budget |
| P5 | Arm B produces **>= 1 new `crash`** whose `exc_type` is `RecursionError` | guest depth 5000 in direct mode against a host limit the oracle does not raise |
| P6 | Arm B's total wall time is **<= 3x** arm A's on the same seeds | only the 10.8 % censored tail runs longer, and it is bounded by `timeout_s` |
| P7 | Arm B's `T-SPACE` **conversions** (fired in A, not fired in B) are **>= 90 %** of A's fires | 70/73 = 95.9 % in round 383's ladder |
| P8 | The 3 unbounded seeds round 383 named (140, 273, 341) are **still censored** in arm B | round 383 measured them past 25000 |
| P9 | Deriving `FRAME_SLACK` from `Interpreter.FAST_MAX_DEPTH` reproduces **exactly 140** on today's tree (`FAST_MAX_DEPTH` is still 100) | round 383 measured excess == FAST_MAX_DEPTH - 2, and 140 = 100 + 40 |
| P10 | Reporting `render`'s skipped pairs makes **>= 35 %** of usable arm-A rows carry a non-zero `pairs_skipped` in the oracle's own `detail` | round 383's R-CAP fire rate 39.6 % |
| P11 | Lifting `render`'s pair cap from 6 to the full binding list surfaces **0** new mismatches | the property is a symmetry of `diverge`, and 7 083 pairs already exercised it |
| P12 | Adding the injected-bug tests to `run_tests_fast.sh` costs **< 15 s** wall | `test_swe_oracles.py` whole is 4.6 s (round 383) |
| P13 | At least one **other** oracle's verdict distribution moves between arms besides `tail_transparency` — i.e. the ceiling is not a tail-only parameter | `max_depth` is threaded into all 8 oracles' `_run_ast` |
| P14 | The `--max-depth` flag did not exist before this round, so **no** prior round could have run item 1 from the CLI even if it had tried | read: `main()` never passed `max_depth` to `sweep()` |
