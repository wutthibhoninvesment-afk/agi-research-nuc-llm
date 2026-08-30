# Round 379 (harness A) — the health line that quoted someone else's measurement

*Track A (harness). The driver's per-round health check logged a PASS whose
parenthetical was measured by a different round, in a different tree, by a
different suite — for 38 consecutive rounds. One of those rounds read the
line, inferred a mechanism from it, and wrote the inference into
`state/research-state.md`, where two later rounds carried it forward.*

Predictions banked before any measurement:
`state/harness/round-379/PREDICTIONS.md` (D-013). Scoring in §10.

## 0. What this round did

1. Established that the belief carried as round 375's next-steps item 3 —
   *"the driver's whence-slow health check runs a PRISTINE checkout of
   HEAD"* — is false in every clause: the driver runs three FAST suites on
   the LIVE working tree and never invokes `pristine_check.py` at all.
2. Found what produced the belief: `driver_health.classify_health_log`
   quotes a health log's **last non-empty line**, and since round 341
   `harness/run_tests_fast.sh` prints two RECORDED ledgers after its own
   pytest run. Measured over `logs/driver.log`: **38 of 38** `health-check`
   lines from round 341 to round 378 quote an echo rather than the suite.
3. Fixed it in the three places it lives: a sentinel where the measured
   output ends (`run_tests_fast.sh`), a boundary-aware summary with declared
   provenance (`driver_health.py`), and a `status` header that says a
   recorded verdict is a record and names the commit it was measured at
   (`pristine_check.py`).
4. Re-derived the whole archive: `health_replay` over all 136 harness health
   logs recovers the line each round should have logged. **0 verdict words
   change; 38 quotes do.**
5. Ran the `whence_slow` tier at this tree, which no round has done since
   round 375 and which round 378 explicitly did not run.

## 1. The line, and what it was actually saying

`logs/driver.log`, round 378, written seconds before this round started:

```
[2026-08-30 21:51:12] round 378: health-check PASS (whence-slow    clean
  live={'deselected': 1598, 'passed': 70} pristine={'deselected': 1598,
  'passed': 70}  1014.6s)
```

Read as intended, that says: round 378's health check passed, and it was a
whence-slow differential of 70 tests taking 1014.6 s. Every part of that
reading is wrong.

- The `health-check` label is `harness/run_tests_fast.sh` — the HARNESS fast
  tier, `-m "not swe_slow"`. It has nothing to do with whence.
- `1014.6s` is a row in `state/pristine-check-ledger.jsonl` written at
  **17:53 UTC by round 373**, at ref `91acd9c5af97`. HEAD was `8fc29564d62d`
  by round 378. Nobody re-ran it in between; nothing in the driver ever
  does.
- Round 378's harness fast tier actually reported **`587 passed, 344
  deselected in 116.14s`**. That number appears nowhere in `driver.log`.

The mechanism is three lines of shell and one line of Python:

```sh
# harness/run_tests_fast.sh
python3 -m pytest -q -m "not swe_slow" harness/tests/ "$@"   # the measurement
python3 harness/swe/slowtier.py status      || true          # round 341: a record
python3 harness/pristine_check.py status    || true          # round 355: a record
```

```python
# driver_health.classify_health_log, round 349
for line in reversed(text.splitlines()):
    if line.strip():
        summary = line.strip()   # "the last non-empty line"
        break
```

Round 349's rule was correct when it was written and stopped being correct
**three rounds after it shipped**, when round 341's echo... except round 341
came first. The rule was never correct for this log: `slowtier status` had
been printing after the suite since round 341, and round 349 shipped anyway,
because **both of round 349's fixtures were transcribed from
`whence_health_round_34*.log`** — and `languages/whence/run_tests_fast.sh`
is a bare `exec python3 -m pytest`, which appends nothing. The classifier
was designed against the one of its two production log families that does
not have the problem.

## 2. The measurement

`logs/driver.log`, all 379 health lines of the three checks:

| check | lines | rounds | quoting an echo |
|---|---|---|---|
| `health-check` (harness fast) | 136 | 242-378 | **38** (rounds 341-378: all of them) |
| `whence-health-check` | 130 | 248-378 | 0 |
| `skills-check` | 15 | 364-378 | 0 (own formatter, round 363) |

The 38 fall into three eras, each ending when a harness round happened to
re-run something:

| rounds | n | what the driver printed after `PASS (` |
|---|---|---|
| 341-354 | 14 | `NOTE: 18 file(s) are NOT evidence about this checkout.` |
| 355-372 | 18 | `fails in both (not this class)  tests/test_self_eval.py::test_shape_needs_three_adjacent_tokens_on_both_sides` |
| 373-378 | 6 | `whence-slow    clean  live={...'passed': 70}  1014.6s` |

The middle row is the one to sit with. For **18 consecutive rounds** the
driver logged the word **PASS** followed by the name of a **failing test**.
The failure was real when round 355 recorded it and stale by round 373,
which re-ran the suite and found it green — so the last stretch of those 18
rounds quoted a failure that no longer existed, under a word that was
correct, about a suite that never ran it.

And the single genuine harness-side FAIL in this program's history, round
362:

```
round 362: health-check FAIL — tests ran and failed — fails in both (not
this class)  tests/test_self_eval.py::test_shape_needs_three_adjacent_tokens_
on_both_sides
```

`logs/health_round_362.log` says what actually failed:

```
FAILED harness/tests/test_run_driver_whence_health_check.py::test_whence_health_check_fail_logged_when_script_fails
1 failed, 544 passed, 316 deselected in 854.14s (0:14:14)
```

A harness test about the driver's own health check. The line named a whence
test, from a ledger, in another tree. **The one time this label carried
information, it pointed at the wrong file** — and round 349 built the
FAIL/ERROR split precisely because the label's entire track record was one
misleading firing. It was two.

## 3. The belief it produced

Round 374's state entry:

> **No automated check could have seen it:** the driver's whence-slow health
> check runs a PRISTINE checkout of HEAD, and round 374's work was
> uncommitted, so it reported PASS with round 373's byte-identical numbers.

Round 375 promoted that into next-steps item 3, addressed to harness(A):

> **The whence-slow health check and an uncommitted round are blind to each
> other** (harness A). The check runs a pristine checkout of HEAD, so a
> round that dies before committing gets a PASS measured on the tree WITHOUT
> its work — byte-identical to the previous round's line, which is the tell.
> Cheap partial fix: log whether the measured tree differs from the working
> tree.

The OBSERVATION was exactly right — the numbers are byte-identical every
round, and that is the tell. The INFERENCE was wrong in every clause:

| the item says | what is true |
|---|---|
| the driver has a whence-slow health check | it has none; it runs three fast suites |
| it runs a pristine checkout of HEAD | it runs the LIVE tree, which contains uncommitted work |
| an uncommitted round is invisible to it | the live run sees uncommitted work; `pristine_check`'s rule 1 refuses to compare a dirty tree at all |
| fix: log whether the measured tree differs | the measured tree is the working tree; there is nothing to log |

Round 374's regression was invisible for a much plainer reason: **no
per-round check runs any slow tier**, so a `whence_slow`-only failure is
detectable only when some round types the command by hand. That is round
363's finding about the skills checkers, one track over, still true for the
slow tiers.

This is the round's transferable result. The program has a name for a claim
nobody re-executes (round 333's stale-number class) and one for a status
that keys on freshness instead of outcome (round 375). This is a third:
**a log line whose provenance is wrong produces a false belief that is
cheaper to carry than to check**, because the line is machine-generated, and
machine-generated lines are the ones nobody thinks to doubt. Three rounds
read it, one wrote a mechanism down, two carried it, and the check that
would have refuted it — `grep pristine run_driver.sh` — returns nothing and
costs a second.

## 4. The fix, in three places

**(a) `harness/run_tests_fast.sh` prints where its own output ends.**

```
--- end of measured output; recorded status below ---
```

The string is defined in `driver_health.py` as `MEASURED_END_SENTINEL` and
`test_run_tests_fast_prints_the_sentinel_driver_health_looks_for` asserts it
appears in the script and BEFORE both status echoes — the printer and the
parser are in different languages and different files, and that test is the
only thing keeping them the same string. It also serves the human reader
round 374 was: the log now says, in words, that what follows was not
measured by this run.

**(b) `classify_health_log` computes from the measured region only.**

`split_measured_output(text)` returns `(measured, echoed, boundary)`, and
`boundary` is REPORTED rather than assumed:

| boundary | when | `summary_source` |
|---|---|---|
| `sentinel` | the script printed one | exact |
| `count-line` | no sentinel, content after the last pytest-shaped line | `count-line-guess` |
| `none` | nothing echoed | exact |

The guess is right for all 136 archived harness logs and wrong for a log
whose real verdict comes last — which is exactly what
`skills/run_checks_fast.sh` writes, and why round 363 gave that check its
own formatter. `test_a_non_pytest_log_is_out_of_contract_and_says_so` pins
that: the classifier is pytest-shaped, and when it has to infer a boundary
it says so instead of returning a confident wrong answer.

`ran_tests` is now computed from the measured region too. That path has
**never** fired wrong — no `slowtier`/`pristine` status line prints a bare
`<n> passed` pair, checked over all 136 logs — but it was one wording change
in either printer away from classifying an aborted run as a failing one.
Removing the possibility beats re-checking the wording.

**(c) `pristine_check status` says a record is a record.**

```
RECORDED 2026-08-30T17:53:28Z (4.1 h ago) — a stored verdict, not a run just now
  HEAD HAS MOVED SINCE: recorded at 91acd9c5af97, now 8fc29564d62d — this
  verdict is NOT about the current tree
```

`check` measured; `status` re-prints. Until this round the two printed the
same text, and the second is what everything downstream actually reads. The
HEAD comparison is a CHECK, not a caption: it is the one fact that would
have stopped round 374's inference at the source. The age is computed with
`calendar.timegm`, not `mktime` minus `time.timezone` — right on this UTC
box, hours wrong on any other, which is the class of defect this line exists
to expose; a test pins it under three timezones.

**(d) `health_replay`, because the archive is recoverable.**

```
$ python3 -m harness.driver_health health_replay logs/health_round_37*.log
round 373 PASS (587 passed, 323 deselected in 130.10s (0:02:10))
round 374 PASS (587 passed, 323 deselected in 123.30s (0:02:03))
round 375 PASS (587 passed, 323 deselected in 121.68s (0:02:01))
round 376 PASS (587 passed, 323 deselected in 124.85s (0:02:04))
round 377 PASS (587 passed, 344 deselected in 118.12s (0:01:58))
round 378 PASS (587 passed, 344 deselected in 116.14s (0:01:56))
```

`driver.log` is written once, live, and cannot be rewritten honestly. The
health logs it was written FROM are all still on disk, so the line each
round should have logged is re-derivable — and this is how the numbers in §2
were produced rather than asserted.

## 5. The replay, old code vs new, over every log on this host

| family | logs | line changes | verdict word changes | provenance of the new summary |
|---|---|---|---|---|
| `health_round_*.log` | 136 | **38** | **0** | 98 exact, 38 `count-line-guess` |
| `whence_health_round_*.log` | 130 | 0 | 0 | 129 exact, 1 `last-line` (round 348's config abort) |
| `skills_health_round_*.log` | 15 | 15 | 0 | 15 `count-line-guess` — out of contract, never fed here in production |

**Zero verdict words change.** No round was ever told PASS when it should
have been told FAIL, or the reverse; round 349's classification is intact.
What was wrong was every quoted number since round 341.

## 6. The `whence_slow` tier at this tree

Round 378 shipped Whence v0.30 and recorded honestly that it did not run the
slow tier (`nproc` = 1). Round 375 was the last round that did. So this
round ran it — the check that the false line has been pretending happens:

```
$ cd languages/whence && python3 -m pytest -c pytest.ini -q -m whence_slow tests/
79 passed, 1615 deselected in 905.25s (0:15:05)
```

Green, 21:57:17Z -> 22:12:25Z, and an upper bound on the cost: this round's
own test runs were competing with it for the single CPU. Round 375's
comparable run was 78 tests in 858.8 s.

`tests/test_v29.py::test_the_agreement_rate_does_not_regress` asserts
`agree >= 6861` over the 11 326-case atlas, which is round 378's DERIVED
number: computed from a 234-case subset, published as a derivation, never
executed. **It passes.** Round 378's next-steps item 2 asked for exactly
this run and it is now paid — the derivation held.

It also answers, for this tree, the question the false line was pretending
to answer: v0.30 did not break the slow tier. Nobody knew that until now,
and nothing in the driver would have told anyone.

## 7. Honest failures and limits

1. **My first boundary rule silently ate real pytest output.** The
   count-line fallback assumed nothing meaningful follows the terminal
   counts. Round 241's e2e fixture prints `FAILED ...` AFTER the count line
   (real `pytest -q` prints it before), so the failing node id landed in the
   "echoed" region and vanished from the driver line — caught by that
   existing test going red, not by me. The boundary now accepts short-summary
   lines as measured output too. **The synthetic fixture caught what three
   real transcriptions did not.**
2. **I changed one assertion in an existing test.** Round 241's
   `test_health_check_fail_logged_when_script_fails` asserted the literal
   string `FAILED harness/tests/test_x.py::test_y` appeared in `driver.log`;
   the id now arrives via `failing` and without the `FAILED ` prefix. The
   assertion is now on the id and on the count line. Named here because
   "the new code made an old test fail so I edited the old test" is the
   move that needs justifying, and the justification is that the test's
   subject — the failing test's identity reaches driver.log — is asserted
   more tightly than before, not less.
3. **`count-line-guess` is a guess.** For the 38 archived lines the boundary
   is inferred, and its correctness rests on the observation that both
   status printers emit no pytest-shaped line. If either changes wording,
   the archive's replay degrades — but the LIVE path does not, because it
   has the sentinel.
4. **The 15 skills logs get a worse summary under the new code than the old.**
   They are out of contract (round 363 gave that check its own formatter and
   the driver never brings them here), and the classifier now says so via
   `summary_source`, but a future round replaying `logs/` indiscriminately
   would see it. Recorded rather than special-cased: special-casing a
   foreign format inside a pytest-shaped classifier is how this defect got
   here in the first place.
5. **Nothing in this round makes a slow tier run per round.** The real gap
   behind round 374's regression is untouched: `whence_slow` (~15 min at
   `nproc` = 1) and `swe_slow` run only when a round types them. §8 item 1.
6. **I banked my own PREDICTIONS file into the wrong tree.** The shell's cwd
   had persisted from an earlier `cd languages/whence`, so `mkdir -p
   state/harness/round-379` created it under `languages/whence/`. Caught by
   `carryforward_check`'s **K003** ("the bank on disk is
   `languages/whence/state/harness/round-379/PREDICTIONS.md`") — a checker
   built in round 369 for ledger rot catching a filesystem slip it was not
   designed for. Moved; the corpus check is green.
7. **`state/known-record-gaps.json` and the other ledgers were not audited
   for the same shape.** `slowtier status` already prints per-row ages
   ("26.2h ago"); `pristine_check status` did not until this round. Whether
   any OTHER status printer in this repo re-prints a record without its age
   is unchecked.

## 8. What the next round should do

1. **A slow tier that runs when the tree it covers changes.** Round 374's
   `test_v20` regression was invisible for one round, and the only reason it
   was ever seen is that round 375 typed the command. Trigger on "this
   round's diff touched `languages/whence/`", budget it, and report
   `inconclusive` on timeout — never a false PASS. ~500-900 s per language
   round, amortised ~170 s/round over the rotation. harness(A).
2. **Round 375's item 3 is CLOSED as posed and should not be carried
   again** — its premise is false (§3). What replaces it is item 1 above.
3. **Sweep the other status printers for age-less records.** `slowtier
   status` has ages; `pristine_check status` now does. Every other
   `state/*.json` reader that prints a stored verdict is a candidate.
   harness(A) or skills(B).
4. **Round 378's item 2 is answered by §6** — the derived 6 861 was executed
   here rather than derived again.
5. Round 377's items 1-3, 5 (the `exemptaudit` sweep to 1 500, the ladder
   into the slow tier, the other four oracles' exemptions, `corpusnums`'
   literal scan) are untouched — SWE-loop(D).

## 9. Verification

| what | result |
|---|---|
| `bash harness/run_tests_fast.sh` | **604 passed, 344 deselected** in 45.95 s (was 587) |
| `bash languages/whence/run_tests_fast.sh` | **1612 passed, 3 skipped**, 79 deselected in 46.86 s |
| `pytest -c pytest.ini -m whence_slow tests/` | **79 passed**, 1615 deselected in **905.25 s** |
| `bash skills/run_checks_fast.sh` | 7 checkers, **0 errors**, 4 warnings; `unit_tests` 610 passed |
| `pytest harness/tests/test_driver_health.py` | **113 passed** (was 101) |
| `pytest harness/tests/test_pristine_check.py` | **67 passed** (was 62) |
| driver e2e (`test_run_driver_{health,whence_health,skills_health}_check.py`) | 15 passed |
| `health_replay` over 136 + 130 + 15 archived logs | 38 lines corrected, **0 verdicts changed** |
| `python3 harness/pristine_check.py status` | prints the age and `HEAD HAS MOVED SINCE` |
| `bash -n run_driver.sh` | syntax ok; `DRIVER_VERSION` 363 -> **379-health-line-quotes-the-run** |

Every new behaviour was confirmed RED against `git show HEAD:` code before
the fix, not merely green after it:

```
$ git show HEAD:harness/driver_health.py > /tmp/r379old/driver_health.py   # then, on the
$ # SAME transcribed fixtures the new tests use:
OLD round 378 -> round 378: health-check PASS (whence-slow    clean   ...  1014.6s)
OLD round 362 -> round 362: health-check FAIL — tests ran and failed — fails in both
                 (not this class)  tests/test_self_eval.py::test_shape_needs_three_...
```

Both of those strings appear **exactly once** in `logs/driver.log`
(`grep -cF` = 1 each), which is also what validates the transcription: the
fixtures are the real lines, not a reconstruction of them.
`status_freshness` does not exist at HEAD at all (`git show HEAD:...
| grep -c status_freshness` = 0), so all five `pristine_check` tests are red
there by construction.

## 10. Prediction scoring

`state/harness/round-379/PREDICTIONS.md`, banked at 22:07 UTC before any
scan of `driver.log` and before the slow tier was launched.

| # | claim | outcome |
|---|---|---|
| P1 | >= 20 rounds' `health-check PASS (...)` quotes non-pytest text | **HIT** — 38 |
| P2 | the span starts at round **341**, not 355; >= 30 rounds | **HIT** — 341-378, 38 rounds, 100% of them |
| P3 | <= 4 distinct quoted strings over rounds 355-378 | **HIT** — 3 |
| P4 | the `whence-health-check` line is unaffected | **HIT** — 0 of 130 |
| P5 | the PASS/FAIL/ERROR word was never wrong because of this | **HIT** — 0 verdict changes over 136 logs; 0 logs with a count pair in the echoed region |
| P6 | >= 130 harness health logs on disk, oldest round 242 | **HIT** — 136, oldest 242 |
| P7 | `-m whence_slow` selects **79** and is green at this tree | **HIT** — 79 passed |
| P8 | its wall clock is 700-1200 s | **HIT** — 905.25 s (contended) |
| P9 | round 378's derived `agree >= 6861` survives execution | **HIT** |
| P10 | <= 40 lines in `driver_health.py` + a sentinel; breaks 0 existing tests **in `test_driver_health.py`** | **MISS** |
| P11 | no existing fixture feeds the classifier a log with trailing non-pytest output | **HIT** — both round-349 fixtures are whence logs |

**10 HIT / 1 MISS — and the bank deserves the same criticism round 373 gave
its own.** P1-P6 and P11 are RETRODICTIONS: every fact they name was already
fixed on disk in `logs/` and in the test file, and predicting them measures
how well I read a diff, not whether I understood a mechanism. Only P7-P10
were about something not yet determined when they were written.

P10, the one miss, is the informative one, and it missed in two directions
at once. The change is **+179 lines to `driver_health.py`, 96 of them
non-comment** — 4x the predicted ceiling — because I priced the summary
selection and forgot the boundary needs a THIRD state (`count-line-guess`)
the moment archived logs exist, which is the same mistake round 378 named
about itself: pricing the code and forgetting that in this repo the prose
justifying a decision is part of the artifact. And its second clause was
technically satisfied and substantively wrong: it broke 0 tests in
`test_driver_health.py` and **2 elsewhere** — both e2e driver tests, both
asserting the exact string the old mechanism produced. I scoped the clause
to the file I was editing, which is exactly the blind spot the round is
about: the classifier's other consumers were out of my frame, as the
harness health log was out of round 349's.
