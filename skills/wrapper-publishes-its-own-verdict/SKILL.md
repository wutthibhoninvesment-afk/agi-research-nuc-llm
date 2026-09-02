---
name: wrapper-publishes-its-own-verdict
description: Use when an aggregator SCRAPES fields (error codes, warnings, coverage clauses, metrics) out of each child process's output and one of those children is itself a RUNNER of the others - a test runner over tests that shell out, a make target, a CI matrix job, a lint wrapper. Symptoms: a row whose codes are the union of two other rows' codes; a total that exceeds the number of distinct findings; the same coverage/latency/percentage clause published twice under two names; an attribution or blame table crediting the wrapper for a failure it only reported; a row whose only honest value is a synthetic fallback like rc1 most of the time and someone else's code the rest. Covers proving the borrowing from the aggregate's own history, replacing the scraped fields with the wrapper's own verdict (exit code plus the identities its runner names), keeping the retained output that makes that verdict possible, and choosing a replacement token the downstream parsers already accept.
---

# A wrapper has no findings of its own

An aggregator that runs N children and parses each one's stdout is a good
design right up to the moment one child's job is *to run the other children*.
Then the parser, written to read a checker's own output, reads another
checker's output through a test runner's failure report — and the wrapper row
publishes fields that belong to somebody else.

This is not a parsing bug. The regex is correct; it is pointed at a stream
whose author is not who the row says it is. Widening or narrowing the pattern
cannot fix it, because there is no pattern that distinguishes "the checker I
ran printed P001" from "I printed P001" in a captured-stdout dump.

The damage is quiet and it compounds:

* **Double counting.** `n_err = sum(len(row.errors))` counts every borrowed
  code a second time. In the case this skill came from, a run with five
  distinct violations was logged as `9 error(s)` — and that line is the one
  the driver copies into its own log for a human to read.
* **A metric published twice under two names.** A `coverage 6/10 items` clause
  scraped off the wrapper appears in the summary as both `state_claim_check
  6/10` and `unit_tests 6/10`. Two names, one measurement, and nothing says
  so.
* **A wrong attribution.** Any tool that asks *which check found this* now
  has the wrapper in the answer set.

## When this triggers

All of the first three, or the fourth alone:

1. An aggregate has one row per child process and derives that row's fields
   by **parsing the child's output**, not by an API the child implements.
2. At least one child **invokes the other children** — a test runner over
   tests that shell out, a `make check` that calls each linter, a smoke job
   that curls the services it is aggregating.
3. The aggregate publishes a **sum, union or list** built from those fields.
4. Or, directly: you are looking at a row whose codes are visibly the
   **union of the rows above it**.

## Steps

1. **Find the wrapper rows by asking what each child RUNS**, not by reading
   the aggregate. One grep of the child's argv is usually enough
   (`-m pytest`, `make`, `xargs`, `run-parts`, a shell wrapper). Write the
   answer down as a table in the code, keyed by row name, with the reason —
   the next person will otherwise re-derive it from symptoms.

2. **Prove the borrowing from the aggregate's own history before changing
   anything.** The history is the evidence and it is usually already on disk.
   Two numbers make the case, and both are cheap:

   ```sh
   # (a) how many of this row's verdicts carry a code that is not its own
   grep -h '^<wrapper> *ERROR' logs/*.log | awk '{print $3}' | sort | uniq -c
   # (b) a specimen: one log where the wrapper's codes are the union of two
   #     other rows' codes, and the total exceeds the distinct count
   grep -c . logs/<the specimen>.log && cat logs/<the specimen>.log
   ```

   In the originating case (a) returned 19 honest `rc1` against 7 borrowed,
   over 26 red rows in 99 logs — so the defect fires on **27%** of the row's
   failures, which is exactly the rate that keeps it alive: too rare to be
   obviously wrong, too common to be a one-off.

3. **Decide what the wrapper's OWN verdict is.** It has two things and only
   two: its **exit code**, and the **identities its runner names** (pytest
   node ids, failing job names, the target that stopped `make`). Everything
   else in its output belongs to a child.

4. **You cannot publish identities you threw away — fix retention in the same
   change.** This is the step that gets deferred and must not be. A runner's
   identities live in its output; if the aggregator streams that output to a
   temp file and unlinks it, the honest verdict is unavailable and you will
   fall back to scraping. Keep a NOT-CLEAN child's output under a
   round/run-scoped path, cap it head-and-tail (the tail holds the short
   summary — a head-only cap retains a file and still loses the answer), and
   put the path on the row so a reader can open it.

5. **Keep what you replaced; do not delete it.** Move the scraped fields to a
   `borrowed` key on the structured result. "What did this row used to say?"
   is the first question a future reader of an old log will ask, and deleting
   the answer repeats the original mistake one level up.

6. **Choose a replacement token the existing parsers already accept.** This
   is where a correct fix turns into a silent regression. Enumerate the
   downstream readers first — `grep -rn` for the row's format, for the codes
   alphabet, for the log-file glob — and check the new token against each
   one. A richer, more descriptive token (`5-failed`) that fails a
   downstream `([A-Z]\d{3}|rc1)` alternation drops the row from that reader
   entirely, trading a visible over-count for an invisible under-count.

7. **Re-run the aggregate's headline number and say which way it moved.** The
   total should DROP by exactly the borrowed count. If it did not, you have
   found a second borrower.

## Pitfalls

* **Treating it as a false positive to suppress.** The codes are real; the
  attribution is wrong. An exemption list hides the row instead of fixing
  whose it is, and the double-count survives.
* **Deleting the scraped fields with nothing to replace them.** A row that
  now says nothing is worse than a row that says something borrowed, because
  the exit code is still real and someone must be able to act on it. Step 3
  before step 5.
* **Assuming the wrapper never goes green-with-warnings.** Check. If it can,
  its warnings are borrowed too and are inflating a second total that nobody
  is looking at.
* **Cap-by-head-only when retaining output.** Test runners print the summary
  last. See step 4.
* **Fixing the aggregate and not the aggregate's readers.** The row shape is
  a public interface the moment a second program parses it. Step 6.
* **Believing the aggregate's own history is a control.** It was produced by
  the code you are changing. It proves the DEFECT existed; it cannot
  validate the fix. Pin the fix against a reconstructed specimen of the real
  output instead.

## Verification

Run from the repo root. Both commands must exit 0.

```sh
# 1. the contract: a runner row publishes rc1 + its failing node ids, keeps
#    the borrowed fields under `borrowed`, retains a not-clean run's output,
#    caps it so the TAIL survives, and cannot be re-read as a checker row
python3 -m pytest -q harness/tests/test_corpus_evidence.py

# 2. the reader, over the live logs: every row that predates retention is
#    reported as unrecoverable BY CONSTRUCTION rather than as a coverage gap
python3 harness/redattrib.py evidence | tail -3
```

Expected from (2): a `corpus-evidence: N not-green row(s) ...` line and a
line naming the first retained round, with the pre-retention rows counted
separately from the rows the mechanism is answerable for.

## Where this came from

Round 463 (harness A). `skills/skill-authoring/scripts/corpus_check.py` runs
ten checkers and parses each one's stdout; the tenth, `unit_tests`, is
`pytest -q` over tests that invoke the other nine. Over 99 driver logs the
`unit_tests` row was red 26 times, and 7 of those rows published other
checkers' codes — round 398's is the clean specimen, where the row is the
literal union of the two rows above it and the summary says `9 error(s)` for
5 distinct violations. 21 of the 99 aggregate lines also carried a
`unit_tests <coverage clause>` that belonged to another checker.

Related: [`number-belongs-to-its-runner`](../number-belongs-to-its-runner/SKILL.md)
is the same confusion about a NUMBER cited from a test's name;
[`echoed-record-vs-measurement`](../echoed-record-vs-measurement/SKILL.md) is
about a recorded verdict printed into a measured stream;
[`recorder-in-the-record`](../recorder-in-the-record/SKILL.md) is about the
collector's own footprint in what it collects. This one is about a row whose
subject is a runner.
