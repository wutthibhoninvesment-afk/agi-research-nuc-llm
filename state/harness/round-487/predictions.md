# Round 487 (harness A) — predictions, banked BEFORE measuring (D-013)

Subject: the `unit_tests` checker of `skills/skill-authoring/scripts/corpus_check.py`,
which reported `COULD NOT RUN` (killed at its 600 s budget) in rounds 483, 485 and
486, reddening `test_driver_health.py::TestBrokenCheckerLiveRecord::
test_the_live_log_has_no_unacknowledged_broken_checker` and, through it,
`test_redattrib.py::TestThisTree::{test_the_cli_audit_exits_zero_on_this_tree,
test_the_registry_is_fail_closed_over_the_live_logs}` — three reds, one cause.

Basis available to me at banking time, and named so a miss can be scored:
- 36 `budget:` clauses in `logs/driver.log`, rounds 451-486, all under the
  driver's own FOUR-way pytest concurrency on an `nproc` 1 box.
  451-464 sit at 324-382 s; 465-482 at 371-491 s; 483/485/486 at 601-602 s,
  which is the KILL and not a runtime.
- `state/known-broken-checker-rounds.json` `_why`: round 451 measured 162.34 s
  solo, removed 71 s of it, and DERIVED (not measured) a ~3.7x contention
  factor from the 600 s crossing.
- `logs/corpus-evidence/round-486/unit_tests.out`: 15 progress lines,
  1 096 test characters, FIVE `F`s, no summary line.

P1. **Solo wall-clock of the exact `unit_tests` argv at HEAD, alone on this
    box.** Point 155 s, band [120, 200]. Reasoning: round 482's 473 s under
    contention / round 451's derived 3.7 = 128 s, plus four rounds of growth.
P2. **`skills/skill-authoring/scripts/test_corpus_check.py` is the single
    dominant file**, ≥ 40 % of the solo total, because its tests shell out
    to whole `corpus_check` sweeps. Band [40 %, 75 %].
P3. **Collected test count at HEAD: 1 100**, band [1 050, 1 200] (the
    round-486 progress bar shows 1 096 characters and was killed before the
    bar ended, so HEAD is at or above that).
P4. **The breach is CONTENTION, not workload.** Concretely: solo runtime is
    below 300 s, i.e. below half the budget, so the checker that "went over
    600 s" never came close to 600 s of its own work. If P1 holds, P4 holds.
P5. **The five `F`s are REAL failures still red at HEAD**, not flakes and not
    contention artefacts: ≥ 3 of the 5 fail again when the suite is run solo.
P6. **Round 451's salvage cannot salvage `unit_tests`.** `_findings_in` reads
    `FINDING_RE`, `(ERROR|WARN|STALE|CARRIED|error|warning)\s+([A-Z]\d{3})`.
    A `pytest -q` progress bar contains no such token, so the timeout branch
    returns `errors=[], warnings=[]` for the ONE checker that has ever timed
    out — the checker round 451's fix was written for. Predict: over all
    rounds in `driver.log`, the number of `COULD NOT RUN: unit_tests` lines
    that carry ANY error code parsed out of the partial output is **zero**.
P7. **The 5 failures are invisible in `driver.log`.** Predict the string
    `failed` does not appear in any `skills-check` line of any of rounds
    483/485/486, i.e. three rounds of driver record report ten minutes of
    computation and five known-failing tests as "no information".
P8. **Budget sizing.** Predict the honest new budget is NOT a round number
    chosen by hand: with 36 rounds of contended samples the 483-486 breach
    rate is 3/4 of the newest four rounds, and the p95 of rounds 465-482
    (18 non-breaching contended samples) lands in [480, 560] s, so a budget
    derived as `ceil(p95 x safety)` lands in [700, 1000] s, NOT at 600.
P9. **Cost of the raise.** Predict raising the `unit_tests` budget alone does
    NOT lengthen a normal round: `skills-check` is one of four suites the
    driver runs concurrently and the other three take 1 114-1 516 s, so the
    round's skills-check wall clock is bounded by the SLOWEST sibling, not by
    this checker. Band: median round-over-round change < 30 s.
P10. **What I will NOT do.** I predict the wrong repair here is appending
    483/485/486 to `acknowledged_rounds` and stopping; the registry's own
    `_expiry` forbids it ("do not add a round number here to silence a red
    test"). Acknowledgement lands only WITH a named cause and a named fix.
