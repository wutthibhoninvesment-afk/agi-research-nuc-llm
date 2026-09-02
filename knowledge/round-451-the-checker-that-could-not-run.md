# Round 451 (harness A) — the checker that could not run, and the test that could not see it

**Track:** harness(A). **Subject:** `unit_tests`, the last checker in
`skills/skill-authoring/scripts/corpus_check.py`, which reported `TIMEOUT`
in rounds 431, 445, 448, 449 and 450.
**Predictions:** `state/harness/round-451/PREDICTIONS.md`, banked and
committed at `b144bf1` before any timing run. **6 HIT, 2 MISS of 8**, plus 3
claims recorded as DERIVED-by-reading. One of the HITs is the round's worst
line and §7 says why.

---

## 0. Inherited first

Round 450 was killed by the driver's outer 3300 s timeout — `driver.log`
09:24:39, *"file populated but no result entry (span near the 3300s ceiling
— likely our own outer-timeout kill, not a crash)"* — after its parts 1-4
had landed (`d486aca..f856bae`) and before its final commit. Ten paths were
left uncommitted: its knowledge file, its new skill
`differential-repin-of-a-generated-oracle`, its upgrade to
`suppressor-shares-the-detector-shape`, and six state/registry updates.

Verified rather than assumed before landing. The one number in that diff
that could have rotted is `SPEC.md`'s v0.43 yield line, which claims
`run_tests_fast.sh` goes `2245 -> 2286 passed, 97 -> 98 deselected`; the
driver's own post-round `whence-health-check` at 09:39:18 independently
reports `2286 passed, 3 skipped, 98 deselected`. It agrees. Landed at
`d72dc5b`.

Excluded deliberately: `languages/whence/SECURITY.md` (escalated round 349,
pinned `61248e50a3f5`, the operator's decision, now carried 102 rounds) and
`state/round_counter` (a standing dirty path).

**This is the second round in a row whose predecessor's work had to be
landed by its successor**, and the two causes are different — round 449's
was a driver-written ledger append after the round exited, round 450's was
an outer-timeout kill. The first is structural and named in round 450's §0.
The second is not, and it is worth saying plainly: a round killed at the
ceiling loses nothing only because the NEXT round happens to check. Nothing
enforces that; the standing cross-track convention is a convention.

---

## 1. The headline

`unit_tests` runs the `skills/` test suites and is the tenth and last
checker in the corpus check. Its own source comment calls it *"the slow one
(~37s vs ~3s for the five above)"*. It timed out at 600 s in rounds 431,
445, 448, 449 and 450 — four of the last six — and every one of those
rounds logged this and nothing else:

```
unit_tests         TIMEOUT                timed out after 600s
corpus-check: 10 checker(s), 0 error(s), 8 warning(s); COULD NOT RUN: unit_tests; ...
```

Ten minutes of computation per round, five rounds, reported as one
sentence. **The timeout branch returned empty `errors`, empty `warnings`,
empty `coverage` and a fixed string.** A checker killed during its 501st
test knows 500 things and this branch threw all of them away.

And nothing in the repository went red across those five rounds — for a
reason that is the better half of this round's finding, in §4.

---

## 2. What it actually costs, measured

Solo, on this box, idle, with the exact argv the checker uses:

```
$ SKILLS_CORPUS_CHECK_RUNNING=1 PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q \
    skills/skill-authoring/scripts skills/session-inheritance-audit/scripts --durations=30
2 failed, 914 passed in 162.34s (0:02:42)
```

**162.34 s against a 600 s budget.** So it does not time out because it is
slow; it times out because it is slow *and* it does not run alone.
`run_driver.sh` launches four pytest suites as concurrent background jobs
(`HEALTH_PID`, `WHENCE_PID`, `SKILLS_PID`, `NUC_PID`) and `nproc` on this
box is **1**.

That contention factor was carried as "roughly 3x" from round 435's
next-step 8. This round measured it directly, on a different suite, as a
by-product of verifying its own change:

| suite | solo (this round) | under the driver (round 450) | factor |
|---|---|---|---|
| `harness/run_tests_fast.sh` | 254.37 s | 875.37 s | **3.44x** |

Apply it:

```
unit_tests before:  162.34s solo -> 558.7s projected under the driver   (7% margin)
unit_tests after:   100.24s solo -> 345.0s projected under the driver  (43% margin)
```

**558.7 s against a 600 s budget is a 7% margin, and that is the finding.**
It explains something a flat "it grew too big" does not — the
*intermittency*. The skills-check verdict by round:

```
443 PASS   444 PASS   445 ERROR   446 PASS   447 PASS   448 ERROR   449 ERROR   450 ERROR
```

That is not a checker that broke. That is a checker sitting on its budget
line, going over or not depending on how the four suites happened to
interleave. Which is also why no round diagnosed it: each round saw a
one-off.

---

## 3. Where the 162 s was, and the warning that was already written down

`--durations=30`, top four:

```
25.35s  test_corpus_check.py::TestLiveCoverageOnTheDriverLine::test_the_line_still_carries_the_error_and_warning_counts
24.51s  test_corpus_check.py::TestLiveCoverageOnTheDriverLine::test_the_aggregate_line_names_each_checker_that_published_coverage
24.29s  test_corpus_check.py::TestLiveCorpus::test_every_checker_actually_ran
23.57s  test_corpus_check.py::TestLiveCorpus::test_live_corpus_is_clean
```

**97.72 s of 162.34 s — 60% — in four tests, and they are the same test
four times.** Each calls `corpus_check.main(["--repo-root", ROOT, ...])` on
the live repo, and each of those spawns all nine other checkers. So
`unit_tests`, the tenth checker, internally re-ran the other nine **four
times**. Every checker added to `checks()` and every skill added to the
corpus was multiplied by five.

The repository had already written this warning down. `TestLiveCorpus`'s
own docstring:

> without it each of these tests spawns the whole ~40s `skills/` suite, so
> the suite's own runtime would grow by a multiple of itself every time a
> live-corpus test is added

That is exactly right, one level down, and blind one level up. It is about
tests spawning the *suite*; nobody wrote the same sentence about tests
spawning the *sweep*. The `~40s` in it is stale too.

The corpus does not change while pytest runs, so four invocations sample one
state four times. They now share one snapshot (`live_run()`, memoised at
module scope because the callers are two different `TestCase` classes). No
assertion is weakened: each of the four already asserted over a single
snapshot, and none asserted anything *across* runs, so there was no
stability property to lose.

```
before:  2 failed, 914 passed in 162.34s
after:   928 passed in 100.24s
```

−62.1 s, −38%. (928 = 916 + the 12 tests this round added; the 2 failures
were this round's own, see §6.)

---

## 4. The blind spot — why five rounds passed with nobody noticing

`test_corpus_check.py` contains a test whose entire stated job is to catch a
checker that has silently stopped running:

```python
def test_every_checker_actually_ran(self):
    """Guards the assertion above against passing because the checkers
    silently went missing — the failure mode a health check has to not have."""
    ...
    self.assertNotIn("unit_tests", [r["check"] for r in report["results"]])
    for r in report["results"]:
        self.assertEqual(r["status"], "ran", r)
```

That test **runs inside the `unit_tests` checker**. So `REENTRY_ENV` is set,
so `checks()` drops `unit_tests`, so the subject is not in
`report["results"]` — and the test writes the exclusion down as an
assertion.

**The one checker the audit cannot see is the only checker that stopped
running.**

Nobody wrote a bug here. The re-entry guard (round 363) is correct and
load-bearing: without it, `unit_tests` runs the suite, the suite calls
`main()`, `main()` runs `unit_tests`, and the round that built it watched it
spin. The audit is correct too. Two correct decisions, made for unrelated
reasons, composed into a blind spot with a test standing in front of it.

Worse, the defence that usually saves you makes it *harder* to see. The
test's count assertion is **derived**, not literal —
`assertEqual(len(report["results"]), len(corpus_check.checks(ROOT)))` — with
a long comment explaining that round 369 had turned a health check red for a
number rather than a defect. Deriving it is better engineering and it is
completely blind here, because `checks()` consults the same guard. *A
derivation inherits the assumption it derives from.*

The fix cannot be "run it again with the guard off" — that is the regress,
and it doubles the cost of the thing already over budget. The subject
already ran unguarded, when the *outer* caller invoked it, and its verdict
is in `driver.log`, which the guard never touches. So the witness went into
`harness/driver_health.py`:

```python
corpus_check_broken_history(path)            -> {"rounds": {...}, "checkers": {...},
                                                 "n_skills_check_lines": N}
unacknowledged_broken_checker_rounds(path, registry)
```

against `state/known-broken-checker-rounds.json`, which acknowledges the
five adjudicated rounds with their cause and expires by construction: a
sixth round is unacknowledged and loud.

Two properties, both of which are the point:

* **It publishes its denominator** (`n_skills_check_lines`, currently 87). A
  parser that can no longer read the log finds zero broken rounds, which is
  precisely what a healthy log looks like.
* **It fails closed.** An absent or corrupt registry acknowledges *nothing*.
  Failing open would mean deleting one file turns the check green — the
  failure mode the check exists to prevent.

Falsified in both directions before it was trusted, because a watchdog that
has never barked is indistinguishable from a broken one:

```
empty registry            -> [431, 445, 448, 449, 450]   (all five go loud)
missing registry          -> [431, 445, 448, 449, 450]   (fails closed)
registry with round 999   -> non-vacuity guard rejects it (stale acknowledgement)
live log, real registry   -> {}                          (green, and not vacuously)
```

---

## 5. The kill leaked grandchildren

`subprocess.run(timeout=)` kills the process it started and nothing below
it. `unit_tests` **is** a process tree — pytest spawning the nine checkers —
so each of the five timeouts SIGKILLed pytest and orphaned live checker
subprocesses onto a 1-core box, where they went on competing with the rest
of the round.

This repo had written the pitfall down **twice** before this file ignored
it: `skills/fuzz-mutate-kill-loop/references/pitfalls.md` ("`subprocess.run
(timeout=)` kills the child, not its children") and
`claim_check.run_command`'s docstring, which fixed the identical bug in the
identical tree and says so — *"Reading a pitfall is not the same as applying
it."* It is now applied here: own process group, `killpg` the group, pinned
by `test_the_kill_reaps_grandchildren_not_just_the_child`, which leaves a
marker file if a grandchild outlives its parent's budget.

I cannot quantify what those orphans cost the five rounds. Nothing recorded
the process table at the time and I am not going to reconstruct a number
from nothing. It is a mechanism, measured to exist, of unmeasured size.

---

## 6. What was fixed, and the error this round caused itself

Four changes, none of which is raising the timeout — the disposition was
fixed in the bank *before* the numbers, precisely so no measurement could
choose it:

1. **The timeout branch reports what the run achieved.** Output goes to a
   file rather than a pipe, so it survives the kill however the child died,
   and the branch parses it with the same `_findings_in` the normal path
   uses. **The verdict is unchanged** — `status` stays `timeout`, `main()`
   still returns `COULD_NOT_RUN` — and `test_a_timeout_is_still_could_not_run`
   guards the repair against softening into one, which is the way this
   repair goes wrong. Silence and "it never got going" no longer render the
   same: `output_lines: 0` and "said nothing before the kill" is itself a
   finding.
2. **The kill reaps the tree** (§5).
3. **The four live-corpus tests share one snapshot** (§3).
4. **The margin is published every round.** `elapsed_s` was computed from
   `t0` and then dropped on three of `run_one`'s four branches, so no round
   could say how close a checker was to its budget until it was over it. It
   is on every branch now, and `budget_clause()` names any checker past 50%
   of its own timeout on the line the driver logs. 50% and not 90%
   deliberately: at 3.44x contention a checker at half its budget solo is
   already over it under the driver.

**The error this round caused itself.** Part 1 committed a predictions bank
with no `state/prediction-bank-ledger.json` entry, and `carryforward_check`
reported `ERROR K001` within minutes — which turned up as the 2 failures in
§2's before-run (`test_the_live_ledger_accounts_for_every_bank_on_disk` and
`test_live_corpus_is_clean`). The checker did its job on this round faster
than this round noticed. Recorded rather than quietly fixed, because "the
suite was red when I measured it and I caused that" is part of the
measurement.

**Suites, run:**

```
skills unit_tests (solo)            928 passed in 100.24s        (was 2 failed, 914 passed in 162.34s)
test_corpus_check.py                40 passed in 38.07s          (was 28)
harness/run_tests_fast.sh           1249 passed, 361 deselected in 254.37s   EXIT=0
test_driver_health.py -k BrokenChecker  11 passed, 137 deselected
skill_lint --house --strict (new skill)  1 skill(s), 0 error(s), 0 warning(s)
```

And the one that settles it — the full corpus check, UNGUARDED, all ten
checkers, which is the invocation the driver makes and the one that has
reported `COULD NOT RUN` in four of the last six rounds:

```
unit_tests         ok                     928 passed in 99.06s (0:01:39)
corpus-check: 10 checker(s), 0 error(s), 7 warning(s); coverage: ...
RC=0
```

No `COULD NOT RUN` clause, and no `; budget:` clause either — every checker
is now inside half its budget when measured this way. Note what that second
absence means and does not mean: it is a solo run, and the driver's is not.
The projection in §2 is what says the margin holds under contention, and
that projection carries the transferred half flagged in §8.

---

## 7. Predictions, scored

Banked at `b144bf1`. **6 HIT, 2 MISS of 8.**

| | claim | outcome |
|---|---|---|
| P1 | finishes under 600 s solo | **HIT** — 162.34 s |
| P2 | >150 s solo, and the "~37s" comment stale by ≥4x | **HIT** — 162.34 s, 4.39x |
| P3 | slowest 3 tests are >50% of total | **MISS** — 74.15 s of 162.34 s = 45.7% |
| P4 | mechanism is tests invoking a checker against the REAL repo root | **HIT** — the top four are all live `corpus_check.main()` calls |
| P5 | `test_check_round_recorded.py` among the two slowest FILES | **MISS** — its slowest test is 0.85 s |
| P6 | >600 tests collected | **HIT** — 916 |
| P7 | nothing in `test_driver_health.py` asserts checkers actually ran | **HIT, and it is this round's worst line** — see below |
| P8 | the 600 s timeout is an unpinned constant, untested | **HIT** — one occurrence in the file, zero mentions in its test file |

Recorded as DERIVED BY READING and not scorable as predictions: D1 (the
timeout branch returns empty findings), D2 (the re-entry guard drops
`unit_tests`), D3 (the driver only prints per-checker lines when
skills-check is non-PASS, so *"`unit_tests` has never reported ok"* would
have been a log-format artefact — checked, 60 PASS lines exist, before the
claim was made rather than after).

**P3 is the useful miss.** I predicted concentration and got it — four
tests, 60% — but predicted it in the wrong *unit*. Three tests is 45.7%;
four is 60.2%. The bank picked 3 because "top 3" is the idiom, not because
anything suggested three. A threshold chosen for its familiarity is a
threshold nothing measured.

**P5 is the clean miss.** `test_check_round_recorded.py` is the biggest file
in the suite (1548 lines) and reads `git log` and the whole `knowledge/`
tree, so I bet on it. Its slowest test is 0.85 s. Size and I/O surface
predicted nothing; *what spawns subprocesses* predicted everything, and P4
said so in the same bank. Two predictions about the same mechanism, one
right and one wrong, and the wrong one reasoned from the file's shape.

**P7 is a HIT I should not be pleased with.** As worded it is true —
nothing in `test_driver_health.py` asserted that the corpus check's checkers
ran. But I scoped it to one file, and the honest question behind it was
*"would any test have gone red?"* The answer to that is far more
interesting than the answer to mine: a test named
`test_every_checker_actually_ran` exists, does exactly that job, and is
structurally incapable of seeing the subject (§4). **My prediction's scope
was narrow enough to be right and too narrow to be informative.** I found
the real thing four turns later by reading the test list rather than by
scoring the bank — the bank would have paid me for a green tick and moved
on. A prediction scoped to a file measures the file; scope it to the
question.

---

## 8. Honest residuals

* **The contention factor is measured once, on one suite.** 3.44x is
  `harness/run_tests_fast.sh` at 254.37 s solo against 875.37 s in round
  450. It is applied to `unit_tests` by assumption. The projections
  (558.7 s before, 345.0 s after) are therefore one measured half and one
  transferred half. Measuring the skills suite under the driver's own
  four-way concurrency needs a round willing to spend ~15 min doing nothing
  else; it is recorded in `state/known-broken-checker-rounds.json` as the
  next step rather than estimated again.
* **The fix buys headroom; it does not stop the growth.** The corpus grows
  every round and `test_every_checker_actually_ran` still costs 25.7 s
  because it still runs the sweep once, which is correct and irreducible
  without weakening it. The margin is now 43% instead of 7%, and
  `budget_clause()` is what will say when it is going again — the first
  round to cross 50% gets told, on the line the driver logs.
* **The orphaned grandchildren are unquantified** (§5).
* **`state/round_counter` reads 443 at HEAD and 451 in the tree.** It is a
  registered standing dirty path so this is not a gap, but the committed
  value has been eight rounds stale for eight rounds and anyone reading the
  file in git gets a wrong answer. Not touched: it is the driver's file.
* **Round 435's next-step 7 partly self-closed and I nearly carried it.**
  It lists the harness fast tier's V002
  `test_no_unexplained_broken_invocation` as "red since round 429 —
  `verb_audit` still reports `V002 1` on every corpus-check line". At HEAD
  `verb_audit` reports `V001 6, V002 0, V003 12`, and this round's harness
  tier is 1249 passed / 0 failed. V002 is 0 and the item is closed. It was
  still being carried forward in round 435's text; re-deriving cost one
  grep. That is the fourth consecutive round in which re-deriving a carried
  item changed its answer.

---

## 9. Artifacts

* `skills/skill-authoring/scripts/corpus_check.py` — `run_one` rewritten
  (file sink, process-group kill, partial-findings salvage, `elapsed_s` and
  `timeout_s` on every branch); new `_findings_in`, `budget_clause`,
  `BUDGET_WARN_FRAC`.
* `skills/skill-authoring/scripts/test_corpus_check.py` — `live_run()`
  memoised; `TestTimeoutKeepsWhatTheCheckerSaid` (7, one shared killed run
  via `setUpClass` — the round's own finding applied to its own tests),
  `TestTimeoutReapsTheWholeTree` (1), `TestBudgetClause` (4). 28 → 40.
* `harness/driver_health.py` — `corpus_check_broken_history`,
  `unacknowledged_broken_checker_rounds`, `BROKEN_CHECKER_RE`.
* `harness/tests/test_driver_health.py` — `TestBrokenCheckerHistory` (5),
  `TestBrokenCheckerAcknowledgement` (4), `TestBrokenCheckerLiveRecord` (2,
  the enforcement plus its non-vacuity guard). 137 → 148.
* `state/known-broken-checker-rounds.json` — new acknowledgement registry.
* `skills/witness-must-sit-outside-the-guard/SKILL.md` — new, with 3
  positive trigger cases and 1 negative in `skills/trigger-cases.json`
  (P001), and a Verification block whose 5 commands were all executed this
  round with their outputs quoted from those runs (C001).
* `state/known-unprobed-skills.json` — the new skill registered unprobed;
  batch re-derived at this commit as **30 skills / 103 cases / $30.07**
  (round 450: 29 / 100 / $29.20; round 447: 26 / 91 / $26.57 — growth is
  ~$0.88 a round).
* `state/harness/round-451/PREDICTIONS.md`;
  `state/prediction-bank-ledger.json` row 451.
* `knowledge/round-450-...md` + `skills/differential-repin-of-a-generated-oracle/`
  — round 450's, landed by this round (§0).
