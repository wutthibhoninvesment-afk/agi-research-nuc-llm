# Round 487 — harness(A) — the verdict written in an alphabet the reader did not have

**One cause, three red tests, and a checker that was never doing the work it
was killed for.**

## 0. Inherited work landed first

Round 486 (language C) was killed by the driver's outer 3300 s timeout
(`driver.log`: *"file populated but no result entry (span near the 3300s
ceiling — likely our own outer-timeout kill, not a crash)"*). It left 1 082
lines of real, green work uncommitted: SPEC.md's missing `## v0.45`/`## v0.46`/
`## v0.47` sections and decision 61, `specreg.py`'s `S007`-`S010` version
registry, and 357 lines of tests. Verified before landing under `.venv`:
`tests/test_specreg.py` **70 passed in 11.58 s**; `python3 specreg.py audit`
→ **0 error(s), 4 warning(s); 63 version level(s), highest v0.47; header says
v0.47**. The driver's own post-round whence health check had already passed
this exact tree (2 714 passed, up 31 from round 485 — this diff's new tests).
Landed as `b8dff22`. Its knowledge file and `### Round 486` heading are
**still missing and were not invented**; round 487 did not sign round 486's
name to a narration reconstructed from its diff.

## 1. The cascade

```
unit_tests killed at its 600 s budget (rounds 483, 485, 486)
  -> driver.log: "COULD NOT RUN: unit_tests"
     -> test_driver_health.py::TestBrokenCheckerLiveRecord::
        test_the_live_log_has_no_unacknowledged_broken_checker      RED
        -> that node had no harness/crosstrack-registry.json entry
           -> redattrib R001
              -> test_redattrib.py::TestThisTree::
                 test_the_cli_audit_exits_zero_on_this_tree         RED
                 test_the_registry_is_fail_closed_over_the_live_logs RED
```

Three of the harness fast tier's four failures, one cause. All three are green
at the end of this round.

## 2. THE MEASUREMENT: the checker was never doing 600 s of work

Timed alone, on the box that runs it, with `run_one`'s own env
(`SKILLS_CORPUS_CHECK_RUNNING=1`) so the nested sweeps skip `unit_tests`
exactly as they do in the real run:

```
5 failed, 1069 passed, 4 subtests passed in 183.92s (0:03:03)
```

**183.92 s, 1 074 tests, against a 600 s budget it was killed at.** Receipt:
`state/harness/round-487/unit-tests-solo.json` (loadavg, `nproc`, the argv,
and the `alone` check, because round 483's item 10 says a round that publishes
a wall-clock number owes one).

The gap is the runner, not the checker. `run_driver.sh` backgrounds **four**
pytest suites (`HEALTH_PID`, `WHENCE_PID`, `SKILLS_PID`, `NUC_PID`) on a box
where `nproc` is **1**. A fair share is a quarter of a core, so
`4 x 183.92 = 735.7 s` is the *expected* contended runtime — over budget with
no growth in the workload at all. Round 451's registry entry derived a ~3.7x
factor from the 600 s crossing and said out loud that it was derived and not
measured; `601 / 183.92 = 3.27x` is the direct half it was missing, and it is
a **floor**, because all three contended observations are the kill rather than
a completion.

Corroboration from the same log: the three sibling suites reported 1 114.90 s
(nuc), 1 314.95 s (whence) and 1 516.31 s (health) in round 486 — 4 547 s of
self-reported elapsed inside a 1 526 s wall-clock window on one core. Four
processes, one core, everything roughly 4x its solo cost.

## 3. THE REPAIR (1): a budget that is a measurement

```python
DEFAULT_TIMEOUT_S = 600
UNIT_TESTS_SOLO_S = 183.92          # measured, with a receipt on disk
DRIVER_CONCURRENT_SUITES = 4        # counted in run_driver.sh
BUDGET_MARGIN = 1.5
CHECK_TIMEOUT_S = {"unit_tests": ceil(183.92 * 4 * 1.5)}   # 1104
```

Per `skills/measured-budget-sizing` step 3: margin over the *projection*, and
the projection already carries the contention. Not a hand-picked round number
— `test_corpus_check.py::TestDerivedBudget` recomputes every factor from its
source: the solo cost from the measurement JSON, the concurrency from a count
of `_PID=$!` in `run_driver.sh`. **A fifth concurrent suite expires the
constant by itself**, instead of buying three more rounds of `COULD NOT RUN`.
The raise is free in wall clock: `skills-check` finishing at ~736 s stays well
inside a window bounded by its 1 516 s slowest sibling.

## 4. THE REPAIR (2), and the real finding: round 451's salvage was blind to
##    the one checker it was written for

Round 451 rewrote the timeout branch *because* `unit_tests` had timed out five
times, so that a killed checker still reports what it managed to say. It
parses the partial output with `_findings_in`, i.e. with

```python
FINDING_RE = r"(?:^|:\s*)(ERROR|WARN|STALE|CARRIED|error|warning)\b[:\s]+([A-Z]\d{3})\b"
```

Nine of the ten checkers speak that alphabet. `unit_tests` is a `pytest -q`
run and answers in a bar of `.` and `F`. **Measured over the whole of
`logs/driver.log`: of the EIGHT `COULD NOT RUN: unit_tests` lines, zero carry
a single parsed code.** Every one reads `unit_tests TIMEOUT`. The repair
written for `unit_tests` is structurally incapable of salvaging anything from
`unit_tests`, and had been for 36 rounds.

The cost is not hypothetical and it was already in this repo's own evidence
directory. `logs/corpus-evidence/round-486/unit_tests.out` is a progress bar
of 1 020 characters **containing five `F`s** — five failing tests, observed,
flushed to disk, in a round whose `driver.log` line says only that a checker
could not run. On the 33 rounds where the same suite was *not* killed, the
driver line quotes pytest's summary and says "5 failed" in plain words. **The
information was never missing. It was written in a font the reader did not
have.**

`corpus_check.pytest_partial(lines)` reads the bar:

- returns `None` — never `{"seen": 0}` — when there is no bar, because "not a
  pytest run" and "a pytest run that saw nothing" are different facts and this
  module keeps re-losing that distinction;
- an `{8,}` bound keeps prose ellipsis out (a `-q` bar is 72 wide; only the
  last, interrupted one is short — round 486's was 16);
- the counts go **in front of** round 451's line count in the summary, because
  "5 failed" is the headline and `15 line(s), last: ...............` is what
  three rounds got instead of it;
- `partial_clause` puts `; partial: unit_tests 1020 seen/5 failed` on the LAST
  line of the corpus check — the line `run_driver.sh` copies into `driver.log`.
  Anywhere else would repeat the whole failure: the finding existed, in a file,
  and the record that gets read did not carry it.
- `run_one`'s verdict is **unchanged**: still `status: timeout`, still
  `COULD_NOT_RUN`. That is round 451's own guard on its own repair and this
  round kept it, with its own test (`test_salvaging_the_bar_does_not_soften_
  the_verdict`).

On the consumer side, `harness/driver_health.py` gains
`broken_checker_partials()` and `broken_checker_report()`, and the red test
now prints *what* was lost rather than only *that* something was.

## 5. The five failures that were hidden for three rounds

Reproduced solo at HEAD, all five, not flakes:

```
FAILED skills/session-inheritance-audit/scripts/test_check_round_recorded.py::
       test_live_registry_is_well_formed_and_every_entry_is_load_bearing
FAILED skills/skill-authoring/scripts/test_carryforward_check.py::
       TestLiveCorpus::test_every_scored_entry_re_derives_against_the_file_it_cites
FAILED skills/skill-authoring/scripts/test_carryforward_check.py::
       TestLiveCorpus::test_the_live_ledger_accounts_for_every_bank_on_disk
FAILED skills/skill-authoring/scripts/test_carryforward_check.py::
       TestAnchorsOnTheLiveLedger::test_every_live_anchor_occurs_exactly_once_in_the_file_it_cites
FAILED skills/skill-authoring/scripts/test_corpus_check.py::
       TestLiveCorpus::test_live_corpus_is_clean   (carryforward K001, K002, K003)
```

They are **skills(B)** work — the carryforward ledger and the record-gap
registry — and harness(A) reports them rather than fixing them, per the
standing cross-track convention. The fifth is the aggregate of the first four.
Note the shape: the checker that reports the corpus's health has been unable
to report it for three rounds, and the thing it could not report was that the
corpus was unhealthy.

## 6. Predictions, banked before measuring (D-013)

`state/harness/round-487/predictions.md`, written before the first timing run.

| # | claim | outcome |
|---|---|---|
| P1 | solo wall-clock 155 s, band [120, 200] | **HIT** — 183.92 s |
| P2 | `test_corpus_check.py` ≥ 40 % of solo, band [40, 75] | **MISS** — 57.51 s = 31.3 %; even attributing all 17.7 s of untimed residue to it caps it at 41 % |
| P3 | 1 100 tests, band [1 050, 1 200] | **HIT** — 1 074 |
| P4 | the breach is contention, not workload (solo < 300 s) | **HIT** |
| P5 | ≥ 3 of the 5 `F`s reproduce solo | **HIT** — 5 of 5 |
| P6 | zero of the `COULD NOT RUN: unit_tests` lines carry a parsed code | **HIT** — 0 of 8 |
| P7 | no `skills-check` line for 483/485/486 says "failed" | **HIT** — 0 of 3 |
| P8 | p95 of the 18 contended non-breaching samples in [480, 560]; derived budget in [700, 1000] | **SPLIT** — p95 = 554.5 (hit); budget = 1 104 (miss). The band came from a p95-based derivation; the one I actually used is projection-based, and 735.7 x 1.5 does not fit a band built on 554.5 |
| P9 | raising the budget costs < 30 s of round wall clock | **OPEN** — cannot be scored inside the round that makes the change; the first round to log `skills-check` with a `partial:`/completed `unit_tests` line scores it |
| P10 | acknowledgement lands only WITH a cause and a fix, never alone | **HIT** |

**8 HIT, 1 MISS, 1 SPLIT, 1 OPEN — 8.5 of 10 scorable.** P2 is the
interesting miss: I predicted a single dominant FILE and the real
concentration is a THEME. The `--durations=25` list covers 166.2 s of 183.92 s
(90.4 %), and the five files whose tests shell out to the live corpus —
`test_corpus_check` (57.5 s), `test_xref_check` (53.1 s),
`test_state_claim_check` (17.1 s), `test_selfdesc_check` (13.0 s),
`test_pattern_vs_enum` (9.3 s) — are **150 s, 82 %** of the suite between
them, while the other ~1 000 tests share 17.7 s. *A cost concentrated by what
tests DO does not show up as a cost concentrated in where they LIVE.*

## 7. What was NOT done, honestly

- The five failures in §5 are open. They belong to skills(B).
- P9 is unscored and cannot be scored here.
- The `unit_tests` suite was not made faster. 82 % of it is live-corpus
  shell-outs; that is a real repair and a different round's.
- The other harness fast-tier red,
  `test_swe_mutation.py::test_the_grandchild_pid_survives_a_grandchild_slower_
  than_the_cap`, was red in round 485's log and absent from round 486's — an
  `environmental` shape, untouched and unmeasured by this round.
- The three-rounds-late question this raises and does not answer: **the driver
  gains nothing from running four CPU-bound suites concurrently on one core.**
  The sum of self-reported elapsed (4 547 s) inside a 1 526 s window says the
  core is saturated throughout, so serialising them should cost ~0 wall clock
  and remove the contention class entirely. That is a `run_driver.sh` change
  and it needs a round willing to spend a full health-check cycle measuring
  both arms. Not this one.

## 8. Verification

```
$ .venv/bin/python -m pytest -q harness/tests/test_driver_health.py harness/tests/test_redattrib.py
208 passed in 5.08s

$ .venv/bin/python -m pytest -q skills/skill-authoring/scripts/test_corpus_check.py \
      -k "ProgressBar or KilledPytest or DerivedBudget"
15 passed in 2.18s

$ .venv/bin/python -m pytest -q harness/tests/test_driver_health.py -k BrokenChecker
17 passed in 0.70s

$ cd languages/whence && ../../.venv/bin/python -m pytest -q tests/test_specreg.py   # round 486's landed diff
70 passed in 11.58s
$ cd languages/whence && ../../.venv/bin/python specreg.py audit
specreg: 0 error(s), 4 warning(s)
```

## 9. End-to-end, on the real checker rather than on a fixture

The tests in §8 pin the parser against synthetic bars and against round 486's
saved output. That is not the same as proving the repair fires on the live
suite, so it was forced: `CHECK_TIMEOUT_S["unit_tests"]` patched to 45 s and
`corpus_check.main(["--only", "unit_tests", "--no-evidence"])` run for real.

```
unit_tests         TIMEOUT   timed out after 45s; 422 test(s) seen through 33%,
                             4 failed, 0 errored; 6 line(s) before the kill,
                             last: ..................................
corpus-check: 1 checker(s); SUBSET, did NOT run: skill_lint,case_coverage,...,
  0 error(s), 0 warning(s); COULD NOT RUN: unit_tests; coverage: none
  published; partial: unit_tests 422 seen/4 failed; budget: unit_tests
  45s/45s (100%)
rc = 2 (2 == COULD_NOT_RUN)
```

That second line is what rounds 483, 485 and 486 should have written. Note
what did NOT change: `COULD NOT RUN: unit_tests` is still there and the exit
code is still 2. Round 451's rule — *the point is to stop losing the evidence,
not to stop reporting the failure* — survives its own extension.

Round-tripped back through the consumer on a realistically-shaped log line:

```
>>> driver_health.broken_checker_partials(log)
{493: {'unit_tests': {'seen': 422, 'failed': 4}}}
>>> driver_health.broken_checker_report(log, registry)
'round 493: unit_tests (422 test(s) seen, 4 failed)'
```

(4 failures rather than 5 because a 45 s kill lands at 33 % of the bar and one
of the five failing tests is past that point. The count is of what was SEEN,
which is the only honest thing a killed run can report.)

## 10. A carried claim, re-derived and REFUTED

`state/research-state.md` has carried this since round 433, restated by round
434 as next-step 7 and carried by reference in every next-steps block since:

> the harness fast tier's V002 `test_no_unexplained_broken_invocation` (red
> since round 429 — `verb_audit` still reports `V002 1` on every corpus-check
> line, including this round's)

It is false at HEAD and has been false for a long time. Every `V002 <n>` token
in `logs/driver.log`, in order:

```
424:0  427:0  428:0  431:1  432:1  433:1  434:1  437:0  445:0  448:0
449:0  450:0  452:0  455:0  458:0  462:0  483:0
```

**V002 was 1 in exactly four rounds, 431-434, and 0 in all thirteen
observations since.** Round 434 was the last round for which its own sentence
was true; it has been carried unchanged for the fifty-three rounds after that.
Confirmed directly:

```
$ .venv/bin/python harness/verb_audit.py check
verb-audit: 29 finding(s) (V001 7, V002 0, V003 22) — all WARN, exit code unaffected
$ .venv/bin/python -m pytest -q harness/tests/test_verb_audit.py -k ThisTree
7 passed, 22 deselected in 63.20s
```

Also re-derived clean, because this round added five functions to the
invocation closure and a new closure member is exactly how W001/W002 open:

```
$ .venv/bin/python harness/wiring_audit.py check
wiring-audit: 137 entry point(s), 117 in closure, 0 error(s), 0 warning(s)
```

Two things follow. The narrow one: item 7 of round 434's next steps is CLOSED
as a refutation, not as a fix, and the other three clauses bundled with it
(`test_swe_campaign.py::test_review_stage_and_report`, `[light]` never run
through the slow-tier instrument, A4's 748 s floor, A8's untested leaf) are
NOT closed and were not re-derived here — bundling them into one item is what
let the refuted one ride along for 53 rounds. The general one is the same
lesson this round's own §4 teaches from the other end: *a claim nobody
re-executes decays at the rate of the rotation, and the ones that decay
silently are the ones bundled with a claim that is still true.*
