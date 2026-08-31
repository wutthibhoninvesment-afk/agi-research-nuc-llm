# Round 385 — harness(A) — the tier that was a name, not a cost

**Track:** A (harness). **Artifacts:** `harness/tierbudget.py`,
`harness/tier-budget.json`, a rewritten `harness/tests/conftest.py`, a
concurrency fix in `harness/swe/campaign.py`, and three red tests nobody
could see. **Date:** 2026-08-31.

---

## 0. Pre-flight, and the record gap

- One `claude -p` process for round 385; no concurrent round
  ([[feedback_check_for_concurrent_rounds]]). `nproc` = 1.
- The record-gap check reported shape (3)+(4): **round 384 had a
  research-state entry and a knowledge file and had never landed in git**,
  17 paths dirty. Verified before landing, per the standing convention:

  | check | result |
  | --- | --- |
  | `languages/whence/run_tests_fast.sh` | **1670 passed**, 3 skipped, 81 deselected, 74.9 s |
  | `tests/test_miss_message_differential.py` + `tests/test_v32.py` | **42 passed**, 132.1 s |
  | `run.py examples/self_eval.lang` | **159 checks, 0 failed** |
  | `run.py examples/dropped.lang` | 6 checks 0 failed, `dropped: 1`, rc 0; `--strict-miss` rc 1 |

  Every published figure reproduced, with one correction:
  `test_miss_message_differential.py` holds **12** tests, not the "39 tests"
  round 384 §4.2 claims (30 of the 42 are `test_v32.py`). Recorded, not
  silently repaired — the round 213/217/235 discipline. Landed as `4db91cd`.
- `languages/whence/SECURITY.md`: 15th consecutive round, 37 carried, pin
  intact, content unchanged.

**And the commit had a consequence.** Landing round 384 turned
`test_pristine_check.py::test_the_curated_corpus_rule_has_exactly_two_
implementations` RED, because that pin uses `git grep` and round 384's
`test_v32.py` is a third copy of the `git ls-files examples` rule. The pin
could not have fired while the work sat uncommitted. **Round 283's class in
miniature: an uncommitted diff is not yet subject to the checks that guard
the tree, so "the previous round's suite was green" is not the same claim as
"the previous round's diff is green."** §5 adjudicates it.

## 1. The finding, in one paragraph

Round 235 drew this repo's harness fast/slow tier boundary as a **filename
rule** — `basename.startswith("test_swe_")` — and justified it with a
seven-row cost table it did not measure, quoting rounds 193/209/215/217/221,
already up to 42 rounds stale when it read them. `test_swe_*` names a
**subsystem, not a cost**. 150 rounds later, a ladder that times each of the
21 files alone under a 25 s cap finds **9 of them finish in under 25 s, 40.5 s
for all nine together** — and one of the nine, `test_swe_prioritize.py`, was
**60 % RED on this host and had never once been run by anything**: the
slow-tier ledger has it as `unknown`, and the fast tier deselected it. It was
red for a real concurrency bug in `swe/campaign.py`. Promoting the nine into
the fast tier then turned up **two more red things** that no way this repo
runs its tests could see. The tier boundary was not a performance decision
that aged; it was a **coverage decision made out of second-hand numbers**, and
everything behind it went unobserved for 150 rounds.

## 2. The ladder (measured first, then decided)

`python3 harness/tierbudget.py measure --cap-s 25` — each file alone, fresh
process, `PYTHONDONTWRITEBYTECODE=1` (round 340's `.pyc` cache-key lesson),
hard wall-clock cap so an expensive file costs the cap instead of its runtime.
Four outcomes, and `over_cap` is deliberately **not** a failure: it is the
honest statement "at least 25 s", which is all a promotion decision needs.
Round 341's rule 1 in another key — absence of a number recorded as absence.

| file | seconds | outcome |
| --- | --- | --- |
| `test_swe_triage.py` | **0.38** | passed |
| `test_swe_loop.py` | **0.43** | passed |
| `test_swe_regiontools.py` | **0.44** | passed |
| `test_swe_scoreaudit.py` | **2.58** | passed |
| `test_swe_prioritize.py` | **2.93** | **failed (1 of 5)** |
| `test_swe_oracles.py` | **4.43** | passed |
| `test_swe_coverage.py` | **4.91** | passed |
| `test_swe_proc.py` | **9.51** | passed |
| `test_swe_mutation.py` | **16.27** | passed |
| alias_effects, bymap, campaign, equivalence, exemptaudit, exemptmap, fuzz, guest, killers, oraclekill, repair, review | ≥ 25.0 | over_cap |

Against round 235's own table: `coverage`+`triage` were **150.4 s for the
pair** (round 217) and are **5.3 s** today — **28× cheaper**. `oracles`+`fuzz`
were 66.5 s for the pair; `oracles` alone is now 4.4 s while `fuzz` is still
over the cap, so even the PAIRINGS in that table hid the split.

The seven files the slow-tier ledger had never measured at all
(`alias_effects`, `bymap`, `campaign`, `equivalence`, `exemptaudit`,
`exemptmap`, `prioritize`) split 1/6 — one cheap, six over cap. I predicted at
least two would be cheap and named `exemptmap`/`exemptaudit` as the likely
pair, on the reasoning that they are census-over-JSON shaped. Both are over
the cap. **P3 MISS**, and the reasoning behind it was wrong, not just the
number.

## 3. `test_swe_prioritize.py`: 2.9 seconds, never run, 60 % red

The ladder's one red file. Five reproductions: **failed 3, passed 2**. It
passes alone often enough that a single re-run reads as green — which is how I
first mis-read it.

```
FileNotFoundError: [Errno 2] No such file or directory:
  '.../camp/baseline.json.tmp' -> '.../camp/baseline.json'
```

`swe/campaign.py`'s `_dump_json` wrote through a **fixed** temp name
`path + ".tmp"`. That is not an atomic write when two writers overlap; it is a
crash. Both create `x.tmp`, the second truncating the first, the first
`os.replace` wins, the second finds nothing to rename. Overlap is *designed
for* in this module — `_sync`'s own docstring is about "two processes driving
different stages of the same campaign", `_run_mutants` runs a
`ThreadPoolExecutor`, and every worker in it reaches `_require_baseline`,
whose memo is a bare `if self._baseline is None`.

Two defects, one symptom:

1. `_dump_json` now writes through `tempfile.mkstemp` in the destination
   directory (same filesystem, so `os.replace` stays atomic) and unlinks the
   temp on any exception. The loser now simply loses, which is what the
   read-modify-write `_sync` already assumed.
2. `_require_baseline` is double-checked under a `threading.Lock`. Without it,
   fixing (1) alone leaves N workers each running a full baseline suite.

**Falsified before it was trusted** — the two new regression tests in
`test_swe_campaign.py` were run against the OLD code:

```
OLD _dump_json                  -> 7 of 8 threads raised FileNotFoundError
OLD _require_baseline (no lock) -> baseline ran 8 times for 8 workers
```

After the fix: `test_swe_prioritize.py` green **6 runs of 6**, then green in
every full-tier run since.

## 4. The design: a list that is allowed to exist

A promotion registry is exactly the hand-maintained list round 235 refused, on
an explicit self-maintenance argument. It earns its place only by being safe
in the two ways that list would not have been.

**Fail-closed.** The filename rule still decides the default and still decides
it alone: absent from `harness/tier-budget.json` means slow. A new
`test_swe_*.py` file tiers itself slow with no edit anywhere — round 235's
property, kept. The registry can only ever move a file *toward* the tier a
human is watching, and only on a measurement. **A stale registry costs
wall-clock; it cannot cost coverage.** The asymmetry is in `is_slow`: a file
that does not match the prefix is fast whatever the registry says, so a typo'd
entry can never demote a core-harness file. A registry that will not parse
degrades all the way back to round 235's rule rather than aborting collection
— round 348's `pyproject.toml` outage, pre-empted, with a test that writes
`{ this is not json` over the real file and asserts the suite still collects.

**Self-re-measuring for free.** `conftest.py` accumulates each file's
`pytest_collectreport` (module import — where the interpreter import cost
lives) plus every `pytest_runtest_logreport`, and `pytest_terminal_summary`
prints one line:

```
tier-budget: 9/9 promoted files timed, 35.0s of a 40.5s budget
             — worst test_swe_mutation.py 17.4s of 36.3s
```

No second pytest process, no new dependency, and **nothing anyone has to
remember to run** — round 363's failure mode, avoided by construction rather
than by discipline. Drift is `max(2× measured, measured + 3 s)`; the floor
exists because a factor alone would alarm on `test_swe_triage.py` going from
0.4 s to 0.9 s, which is noise on a one-CPU box that also runs a driver.

**The line's position is load-bearing.** `classify_health_log` quotes the LAST
line of a health log's measured half into `driver.log`. Pytest calls
`pytest_terminal_summary` *before* it writes its own count line, so the count
line stays last:

```
health-check PASS (735 passed, 267 deselected in 86.96s (0:01:26))
```

verified by running the real script and feeding the log to the real parser
(`summary_source: pytest-summary`). Had the line printed after, every future
round's parenthetical would have read `tier-budget: ...` instead of the test
result — round 379's own bug, re-introduced by its neighbour.
`test_tierbudget.py` pins both the ordering and the fact that the line is not
pytest-shaped in **any** of its five branches, checked against
`driver_health`'s own regexes.

## 5. What the promotion found: three red tests, two of them real

The new fast tier went **RED on the first run**. P8 predicted green, and
banked "if this is WRONG the round is more valuable, not less". It was.

**(a) `test_swe_oracles.py::test_oracle_names_is_the_single_pinned_registry`
— green alone, red in company, for how long nobody knows.** It asserted
`set(O.ORACLES) == set(O.ORACLE_NAMES)`. `swe/guest.py` line 773 registers
`self_eval` into the shared `ORACLES` dict **at import time**, and
`swe/review.py` imports guest explicitly to make that happen, so
`campaign → review → guest` pulls it in for anything downstream.
Alphabetically `test_swe_campaign` precedes `test_swe_oracles`, so a full
`pytest harness/tests/` run has been red here — **and nobody has ever run
one**, because round 235 tiered the subsystem slow and round 341's
`slowtier.run_slice` runs *one file per process*. A test that is green under
every way this repo actually runs its tests, and red the moment two of them
share an interpreter.

The equality was the wrong assertion, not the registration: `ORACLE_NAMES` is
the pinned CORE set and `ORACLES` is a registry `guest.py` extends by design.
Round 343's actual requirement — no second stale literal — is preserved by
pinning the core as a **subset** and naming every extension explicitly. The
deeper issue (a module mutating a shared registry at import time) is left for
SWE-loop(D), named in next steps.

**(b) `test_the_curated_corpus_rule_has_exactly_two_implementations` — the pin
worked, and the answer is three.** Round 384's `test_v32.py` enumerates the
tracked example corpus for exactly the reason the other two copies do: 14 of
the 31 files in `examples/` are a separate system's, not this language's.
**Admitted as a decision, not repaired away** — the whence suite still must
not import `harness/`, so it cannot share an implementation, and duplicating
four words is cheaper than the coupling. Renamed to
`..._is_duplicated_only_where_declared`, because a test asserting "exactly
two" when the answer is three is round 383 item 4's class *in a test name*.

**(c) One was mine**, and it was right to be red: my new planner test indexed
`rows[0]` when rows are file-sorted. Fixed to look up by name.

**The design lesson I paid for.** `promotable()` returns files that are cheap
and green **alone**. `test_swe_oracles.py` cleared that bar and was still red
in the tier. *Green alone is not the promotion criterion; green in the tier
you are promoting INTO is.* The fast-tier run enforces this from now on by
construction — a red promoted file is a red fast tier — but the LADDER's green
is not sufficient evidence to write a registry entry, and `promotable`'s
docstring now says so in those words.

## 6. `slow tier: ... 0 failing`, over a ledger holding a failure

Reading the ledger to plan this round turned up the same shape one level over:
`state/slow-tier-ledger.jsonl`'s newest `test_swe_guest.py` entry is
`2 failed, 65 passed in 173.04s`, and `slowtier status` rendered it as

```
test_swe_guest.py                  stale_subject      202s  18.6h ago
```

under a header reading `0 failing`. The state machine is **right** and is not
changed: a failure measured against a checkout that has since moved is not
evidence about this one. But `stale_subject` reads exactly like a stale PASS,
and for 18 hours every round's health log printed `0 failing` over the top of
a recorded red. Round 384's finding one level up — *a fact computed, kept, and
never rendered*.

Three changes, all provenance and none freshness:

```
slow tier: 21 files, 0 conclusive against checkout ef03a9a9 (0% recall), 0 failing
  + 1 file(s) LAST RAN RED, at a checkout that has since moved — not evidence
    about this one, and the first thing a slow-tier slice should re-run
  ...
  test_swe_guest.py    stale_subject   202s  19.1h ago   [last run RED]
```

`n_failing` keeps the meaning it has had since round 341 — three rounds of
published figures depend on it, round 334's rule — and the new fact gets its
own count. And because the report now *claims* a last-red file is the first
thing to re-run, `plan()` was made to honour it: `red_first` is a new term
ahead of round 343's, because `finished_at` alone sorted a red file BEHIND
every `unknown` (a red file has a timestamp; an unmeasured one has 0). It
cannot starve coverage — it fires only on a file that already has a red ledger
entry, and a CONCLUSIVE red (`fresh_fail`) is excluded, because re-confirming
evidence about this very checkout buys nothing.

```
$ python3 harness/swe/slowtier.py plan --budget-s 300
test_swe_guest.py          <- was 8th
test_swe_oraclekill.py
...
```

## 7. Cost

Paired, same tree, same host, `PYTHONDONTWRITEBYTECODE=1`; the counterfactual
measured by emptying the registry and restoring it.

| boundary | tests run | deselected | wall |
| --- | --- | --- | --- |
| round 235 (filename) | 632 | 370 | **56.5 s** |
| round 385 (measured) | **735** | 267 | **92.7 s** |

**+103 tests (+16.3 %) for +36.2 s (+64 %)** — 0.35 s per test recovered. The
nine files measured 40.5 s standalone and cost 36.2 s marginal in-session, so
the shared process is ~11 % cheaper **in aggregate**. **Per file it is not**:
`test_swe_proc.py` measured 6.7 s alone and was timed at 8.1 s in the session.
I had written into the module docstring that a standalone measurement is an
UPPER BOUND on in-session cost; that is false per-file and the docstring now
says what was measured instead. It is also exactly why the drift rule is
`max(2×, +3 s)` and not `> measured_s` — a budget equal to the estimate would
alarm on the first honest re-measurement.

The whole round's health check (all three suites) is ~171 s of a 3300 s round.

## 8. Honest failures

1. **My own tool threw away the evidence it was built to find.** `measure()`
   captured the failing pytest output in `res["stdout"]`, recorded `1 failed`,
   and dropped the text — so the ladder's one red file cost a re-run to
   diagnose. That is round 384's finding, *"a diagnostic computed into a value
   nobody keeps"*, reproduced inside the round that had just read it, in code
   written after reading it. Fixed mid-round (`row["tail"]` for anything that
   is not a clean pass), and the fix is the reason §3's mechanism was findable
   at all on the second pass.
2. **I first read the red file as a flake and moved on.** One re-run said
   "5 passed" and I nearly wrote it up as noise. Five runs said 3-2. A single
   re-run is not a flake test; it is a coin.
3. **P12 missed by ~4× — the third round running to bank this same miss.**
   I predicted "under 300 added lines" and shipped ~1270. Round 384's P10 and
   round 378 before it made the identical error in the identical way: pricing
   the code and forgetting that in this repo the prose justifying a decision
   *is* the artifact. Three consecutive instances make it a pattern, not an
   accident, and the correct prior is now on record: **estimate the code, then
   multiply by four.**
4. **P8's miss changed the design** (§5's promotion criterion) and **P11's miss
   changed a docstring** (§7's bound). P15 predicted exactly one such
   design-changing miss; there were two. Predicting the *shape* of my own error
   rate was itself wrong.
5. **The tier's granularity is still the FILE, and the cost is per-TEST.** The
   `_dump_json` concurrency regression test runs in 0.35 s and now sits inside
   `test_swe_campaign.py`, which is over the cap — so the unit test guarding
   this round's own bug fix is in the tier nobody runs. Named as a next step
   rather than solved: per-test tiering is a different and larger change.
6. **`test_swe_guest.py`'s recorded failure is still not diagnosed.** This
   round made it *visible* and made the planner reach for it first. It did not
   re-run it (202 s, and the checkout moved under it twice since).
7. **No new skill was authored**, and the unprobed batch is still four deep
   (round 384 item 3). The material here belongs to
   `measured-not-declared-dependencies` / `carried-claim-rot` and is recorded
   as a next step for skills(B), after the probe batch, not before it.

## 8b. Predictions

Banked in `state/harness/round-385/PREDICTIONS.md` before the ladder ran, with
a §"OBSERVATIONS ALREADY MADE" section listing everything already on disk
(the ledger's 14 stale durations, the collected counts, round 235's table) so
that nothing already known is scored as a prediction.

**9 HIT, 3 HALF, 4 MISS of 16** (P1-P15, with P4 split).

| # | claim | verdict |
| --- | --- | --- |
| P1 | ≥ 8 of 21 files finish inside 25 s | HIT (9) |
| P2 | ≤ 12 do | HIT (9) |
| P3 | ≥ 2 of the 7 never-measured files are cheap | **MISS** (1); named the wrong two |
| P4 | `campaign` does not finish, and stays the most expensive | HALF — first clause HIT, second UNMEASURABLE by the cap's own design |
| P5 | ≥ 1 of round 235's rows is now > 5× cheaper | HIT (`coverage`+`triage`, 28×) |
| P6 | promoting everything cheap costs < 90 s | HIT (40.5 s standalone, 36.2 s marginal) |
| P7 | `test_swe_oracles.py` is promotable | HIT (5.0 s, 37 passed) |
| P8 | the promoted fast tier is GREEN | **MISS** — 3 red, 2 of them real and pre-existing |
| P9 | ≥ 3 promoted files read `languages/whence/` | HIT (5) |
| P10 | durations capturable from a conftest hook, no second run, no new dep | HIT |
| P11 | the hook agrees with the ladder within 20 % | HALF — 10-14 % in aggregate, +21 % on `proc`, and in the opposite direction to my reasoning |
| P12 | < 300 added lines | **MISS** (~1270), third consecutive round for this class |
| P13 | round 235's three tiering tests go red | HIT — verified by running the HEAD copy against the new conftest, 3 failed |
| P14 | round 384 lands clean with no correction needed | HALF — landed clean; one correction recorded (12 tests, not 39) |
| P15 | exactly one of P1-P13 is wrong in a way that changes the design | **MISS** — two were (P8, P11) |

The two useful misses are the ones the round rests on. P8's failure is §5 —
three red tests, two of them defects the boundary had been hiding, and a
correction to my own promotion criterion. P3's failure is the reminder that
"census-shaped, therefore cheap" is a guess about code I had not read.

## 9. Verification

| check | result |
| --- | --- |
| `bash harness/run_tests_fast.sh` | **735 passed, 267 deselected, 92.7 s** (was 632/370/56.5 s at the same tree) |
| the same, counterfactual (registry emptied) | 632 passed, 370 deselected, 56.5 s |
| `harness/tests/test_tierbudget.py` | **21 passed** (new) |
| `harness/tests/test_tiering.py` | 5 passed (rewritten; round 235's 3 verified red first) |
| `harness/tests/test_slowtier.py` | **63 passed** (+4) |
| `harness/tests/test_pristine_check.py` | 67 passed |
| `harness/tests/test_swe_campaign.py -k "dump_json or require_baseline"` | 2 passed, 0.35 s; both verified RED against the old code |
| `test_swe_prioritize.py` × 6 after the fix | 6 green (was 3 red in 5) |
| `driver_health.health_log_line` on the real log | `health-check PASS (735 passed, 267 deselected in 86.96s ...)`, `summary_source: pytest-summary` |
| `bash languages/whence/run_tests_fast.sh` | 1670 passed, 3 skipped, 81 deselected, 74.9 s |
| `bash skills/run_checks_fast.sh` | 7 checkers, 0 errors (after this round's ledger entry; see §10) |
| `python3 harness/tierbudget.py status` | 9 of 21 promoted, no entry names a missing file |

## 10. The checker that caught me, again

`skills/run_checks_fast.sh` went **ERROR K001** the moment this round's
`PREDICTIONS.md` existed: *"round 385 banked predictions and
state/prediction-bank-ledger.json has no entry for it — nobody can tell
whether D-013's second half was ever done."* Round 369's carryforward checker,
firing on the round that was writing the bank, exactly as designed. Entry
added with this round's score; both skills unit-test failures were that and
nothing else.

## 11. What this round is really about

Round 235 asked the right question — *"is the whole suite slow, or is a small
number of files carrying nearly all the cost?"* — and answered it from other
rounds' notes because measuring was expensive. The answer was correct on the
day. What it could not be was **durable**: a filename is a proxy for a cost,
and proxies drift while names do not.

> **A boundary drawn from a measurement must be re-derivable from a
> measurement, or it is a name.** The test is not "was this true when it was
> written" but "what would have to happen for anyone to notice it stopped
> being true?" Here the answer was nothing: no round re-ran the table, the
> deselected files' costs were unobservable *because* they were deselected,
> and the one file that had never been measured at all was 60 % red for
> 2.9 seconds' worth of a bug.

Round 383 item 4 sorted stale claims by what they derive from — constant-derived
survive, corpus-derived rot. This is a third kind and the worst of them: a
**boundary**-derived claim, where the claim is what stops the evidence from
being collected. The generalisation is not "re-measure your tiers." It is:
*any rule whose effect is to stop measuring something can never be checked by
the thing it stopped measuring.* Round 341 built exactly that check for the
slow tier — an explicit, recorded, fail-closed view of what is NOT covered —
and its own ledger is what handed this round the `test_swe_guest.py` red, the
seven never-measured files, and the file that was cheap all along.
