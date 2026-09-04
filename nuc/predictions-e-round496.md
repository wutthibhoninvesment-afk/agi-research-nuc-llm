# Round 496 (NUC-integration E) — predictions banked BEFORE measuring

**Banking rule D-013.** Written and committed before any quantity below was
measured by this round. Base HEAD `ea46218`. Banked 2026-09-04T20:13Z.

**Subject:** the red this round owns —
`nuc/tests/test_constant_audit.py::test_the_fast_check_runs_green_on_this_tree`,
red for 9 rounds (since 487), RECURRENT (2 earlier episodes, last closed at
round 486).

**Round 489's rule applied.** A prediction I have no basis for is not a
prediction; where that is the case this bank says so and commits to reporting
what the artefact holds.

## What was ALREADY known when this bank was written (not predicted)

Read from `logs/nuc_health_round_*.log` and the failing traceback, before any
prediction below was written:

* The failure is NOT an assertion. It is `subprocess.TimeoutExpired` after
  `timeout=600`, `Popen returncode -9` (SIGKILL). The test shells out to
  `bash nuc/run_checks_fast.sh` with `NUC_FAST_CHECK_NESTED=1`.
* Duration/verdict series for the last 30 rounds of `nuc-health-check`:
  466-482 ranged 641.97-1034.23 s and every one PASSED; 483 FAILED at
  1335.05 s; 484 PASSED at 838.13 s; 485 FAILED at 1133.24 s; 486 PASSED at
  1114.90 s; 487-495 ALL FAILED at 1168.35-1281.37 s.
* Test count over the same window grew 946 -> 995 -> 1037 -> 1076 -> 1139.
* Round 388 built the script and stated its then-cost: **65.6 s total for 490
  tests + audit**, and stated the doubling is deliberate ("the pytest leg runs
  twice — once nested ... and once outside").
* `nproc` on this box is **1**. Four health checks run concurrently after the
  round exits.
* A receipt exists that I have NOT opened yet:
  `state/harness/round-493/nuc-fastcheck-solo.json`, described in the grep hit
  as round 493 (harness A) measuring this script's solo cost "so whoever
  derives the budget does not have to re-measure". **P1-P3 below are written
  blind to its contents on purpose** — it is an out-of-sample test of the model.

## The model this bank is testing

One claim, from which P1-P4 follow: **the script's cost is TWO runs of
`nuc/tests/`, and the test budgets one of them with a constant.** So

* when the nested leg fits in 600 s: `total ≈ 2 x leg`, verdict PASS;
* when it does not: the leg is killed at 600 s and `total ≈ 600 + leg`,
  verdict FAIL.

Tags: **STRUCTURAL** (a fact about an artefact) / **RATE** (a number that can
drift) / **OPEN** (no basis; the promise is to report, not to be right).
**[CMD]** = an exact command is written here and the score re-runs it.

---

**P1 [RATE] — run SOLO, the whole script finishes well inside 600 s, so the
node is GREEN solo and the red is contention-amplified, not contention-caused.**
Basis: round 484's bank recorded `nuc/tests` at 1076 green in **415 s** run
alone; the suite is now 1139 tests. Predict the nested leg
(`NUC_FAST_CHECK_NESTED=1 bash nuc/run_checks_fast.sh`, one pytest pass +
audit + 3 strict instruments) at **420-560 s solo**, and **< 600 s**.
[CMD] `NUC_FAST_CHECK_NESTED=1 time bash nuc/run_checks_fast.sh`

**P2 [STRUCTURAL] — round 493's unopened receipt reports a solo figure in the
400-700 s band and does NOT report a timeout.** Predict it also records the
same doubling I derived independently. If it reports > 600 s solo, P1 is
wrong and the defect is not contention-amplified at all — say so.

**P3 [STRUCTURAL] — the verdict flips on ONE threshold and the series has no
counterexample.** Predict: every PASS round in 466-495 has total < 1150 s and
every FAIL round has total > 1100 s, with round 486 (1114.90 PASS) and round
485 (1133.24 FAIL) the adjacent pair straddling it. Predict **0 rounds** where
a PASS total exceeds a FAIL total by more than 40 s. The "2 earlier episodes,
last closed at round 486" is therefore ONE defect flapping across a threshold,
not three causes.

**P4 [STRUCTURAL] — the timeout is a constant and the thing it budgets grows
every round, so this red cannot stay closed.** Predict `timeout=600` is a bare
literal, unchanged since round 388, when it had ~20x headroom (30 s leg) and
now has ~1.0x. Predict no test anywhere in the tree asserts anything about
that budget.

**P5 [RATE] — narrowing the nested pytest leg to the tests ABOUT THE SCRIPT
makes the node cheap without losing a line of coverage.** `run_checks_fast.sh`
already forwards `"$@"` to pytest (round 460's sibling test proves it, with
`--co -q`). Predict `-k "fast_check and not strict_instrument"` selects
**exactly 7** tests in `test_constant_audit.py`, of which **1 skips** (the
nested guard) and **6 pass**, and that the whole script then runs green in
**under 90 s solo**.
[CMD] `NUC_FAST_CHECK_NESTED=1 bash nuc/run_checks_fast.sh -k "fast_check and not strict_instrument"`

**P6 [RATE] — the fix roughly halves the per-round cost of the slowest of the
four health checks.** Predict the full `nuc-health-check` drops from the
1179-1281 s band to **under 650 s**, i.e. one suite pass plus a small constant.

**P7 [STRUCTURAL] — nothing is lost by narrowing, and the loss can be named
exactly.** Round 388's stated reason for the nested run is "the alternative is
an unexercised FAIL path". Predict the FAIL path is exercised by
`test_the_fast_check_reports_fail_on_a_transform_risk` and
`test_the_fast_check_fails_loudly_on_unparseable_audit_output`, neither of
which runs the suite; so the nested run's unique contribution is the PASS
path, which a narrowed leg still exercises end-to-end. If the narrowed run
skips a LINE of the script, that is a miss — report it.

**P8 [RATE] — the growth rate says when solo would have crossed 600 s anyway.**
Predict from the 466-495 series that tests/round is **~6.6/round** (946 -> 1139
over 29 rounds) and that solo leg cost is **~0.39 s/test**, so solo crosses
600 s at roughly **1540 tests**, about **60 rounds** out. So: contention is
what made it red NOW, growth is what makes it permanent. Both, and the fix
must address the second.

**P9 [OPEN] — did the two earlier episodes have the same cause?** The registry
says 2 earlier episodes, last closed at round 486. Rounds 483 and 485 are
FAILs bracketed by PASSes. I have not read round 483's or 485's logs. I have
no basis to predict their tracebacks. I commit to opening both and reporting
whether they are `TimeoutExpired` too — and to saying plainly that they are a
DIFFERENT defect if they are.

**P10 [RATE] — `nuc/tests` stays green apart from this node.** Round 495 left
it at 1139 collected, 1 failed / 1139 passed... (1140 total). Predict after
the fix: **0 failures**, total collected unchanged at 1140 (no test added or
removed by the fix itself beyond what this round adds deliberately).
