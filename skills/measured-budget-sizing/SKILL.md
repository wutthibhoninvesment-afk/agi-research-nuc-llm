---
name: measured-budget-sizing
description: Use when you must pick a timeout, page size, batch size, retry budget or memory cap for work whose per-item cost varies by orders of magnitude, so a single constant is at once far too large for most items and too small for one. Symptoms: a job returned an empty result after consuming almost exactly its timeout; a batch works on every input you tried and dies on the one in production; someone proposes doubling a constant after one timeout; a sweep cannot finish in one run and loses its work every attempt. Covers timing a small SAMPLE of each item on the machine that will do the work, extrapolating a per-item budget, applying a margin, and RECORDING the sizing inside the artifact so a later reader can tell a truncated result from a genuinely empty one. Also covers making such a sweep RESUMABLE, caching closed items while re-scanning the one still-open item. NOT for tuning one budget for one uniform workload (just measure it once); the technique earns its cost only when the per-item spread is large.
---

# A timeout is a measurement, not a constant

The failure this prevents is quiet. A job is given a constant budget, runs
against an item far more expensive than the one the constant was tuned on,
is killed, and its error handling — usually correct, usually fail-closed —
converts the kill into an *empty result*. An empty result is indistinguishable
from "there was nothing there". The record then says the thing you measured
does not exist.

Real instance (round 358 of this program): one `journalctl` capture over a
4.5-day span, client timeout 1400 s, actual 1417 s. The probe's own
"return `[]` on any failure" rule — deliberately fail-closed, and right —
turned 17 seconds of overrun into `n_seconds: 0` written to disk as a
measurement of a silent machine. Nothing downstream was fooled, because the
consumer refused an empty list; a human reading the directory would have been.

## Trigger conditions

- A job came back empty or zero **after consuming close to its whole budget**.
  Treat this as truncation until proven otherwise.
- You are about to write a timeout/batch/page constant that will be applied to
  items you have not measured, whose cost you believe varies "a lot".
- Someone proposes raising a constant because one run hit it. Ask what the
  *spread* is first; if it is 3x, raise the constant. If it is 1000x, no
  constant is correct.
- Your error path returns the same value for "failed" and for "found nothing".
- **A job crossed a budget it had sat comfortably under for dozens of runs,
  and nothing about its workload changed.** Suspect the RUNNER before the
  work. Measure the job alone before you touch the constant.
- **The budgeted work CONTAINS the code that sets the budget** — a test whose
  timeout wraps a run of the suite the test is in, a script whose cap covers a
  job that re-invokes the script. The constant's author cannot see the growth,
  because the people who spend it are every future round that adds an item.
  This is not "a constant that got stale": it is a constant that was never
  about anything, and it is guaranteed to expire.
- A sweep must be resumable across sessions/rounds because it cannot finish in
  one.

## Steps

1. **Enumerate the items and find a cheap proxy for each one's cost.** Span,
   row count and file size are proxies; they are often the WRONG proxy. In the
   round-364 instance two boots had comparable spans (34.6 h vs 39.8 h) and
   scan costs of 14.5 s and 1944 s — a 134x difference driven entirely by
   entry density, invisible to the span. Do not skip to step 2 on a proxy you
   have not validated against at least two items.

2. **Time a fixed-size SAMPLE of each item, on the machine that will do the
   work.** Fix the window (e.g. 300 s of log, 1000 rows) so samples are
   comparable. Time the operation ALONE, excluding connection setup:

   ```sh
   ssh -n host "s=$(date +%s%N); n=$(<work> | wc -l); e=$(date +%s%N); \
                echo \"$n $(( (e-s)/1000000 ))\""
   ```

   `ssh -n` matters: without it `ssh` consumes the driving loop's stdin and
   you silently sample only the first item.

3. **Extrapolate, apply a margin, and clamp.**
   `budget = clamp(floor, projected * margin + floor, ceiling)`.
   A margin of 3 is a good default. It absorbs the real failure mode — a
   sample landing in a quiet stretch of an otherwise expensive item, so the
   projection UNDER-estimates and the job is killed. Over-estimating costs
   only a ceiling you never reach. In round 364 the two expensive items came
   in at 53 % and 77 % of projection and the sweep finished inside its round;
   a tight margin would have deferred them.

4. **Make an unmeasurable item fall back to the FLOOR, not to a large
   constant.** An item you could not sample should fail fast and be retried,
   not occupy the whole run. This is the direct antidote to the round-358
   failure.

5. **Before sizing the work, ask whether the work is DUPLICATED.** Raising a
   ceiling is the repair for a budget that is too small; it is the wrong
   repair for work that should not run. Round 496 of this program: the nested
   run under the timeout re-ran the whole `nuc/tests/` suite that the OUTER
   process was already running — the same tests, same interpreter, same
   commit, minutes apart — so the health check paid for that suite twice every
   round, 314 s of it, on a box with one core and three competing suites.
   Sizing the budget alone would have made the red go away and left the cost.
   Separate what the nested run is FOR (here: the script's own lines —
   interpreter resolution, both legs, the verdict line) from what it merely
   drags along (which tests the leg selects), and narrow the second. Measured:
   319.25 s -> 5.684 s, with every line of the script still executed.

6. **Write the sizing INTO the artifact**, next to the result: the sample, the
   projection, the budget granted, the wall time actually spent, and an
   explicit `complete` flag. Derive `complete` from evidence, not hope —
   "returned inside 95 % of its budget" is a usable rule. Without this, step 1
   of the next investigation is re-running everything.

7. **Cache per item, keyed on immutability.** If an item cannot change once
   finished (a closed log, a released tag, a merged commit), scan it once ever
   and skip it forever after. This is what turns a sweep too big for one
   session into one that is merely resumable — and it means a partial run is
   banked progress, not wasted work.

8. **Order the work cheapest-first** so a run that is cut short has banked the
   most items. Then defer whole items rather than truncating one: a deferred
   item costs the next run nothing extra, while a truncated one written as
   `complete` poisons the record permanently.

## Pitfalls

- **An empty result that consumed its whole budget is a truncation.** If your
  code cannot tell the two apart, it will publish silence as evidence.
- **Sampling the middle is not sampling the worst.** The bound you get is an
  estimate, not a guarantee; the margin in step 3 is what covers the
  difference. Say which one you have.
- **Do not cache the still-changing item.** Exactly one thing in a sweep is
  usually open (the current boot, today's partition, `HEAD`). Re-scan it every
  time and extend its window to *now* — a stale end-point leaves a hole at the
  most recent moment, which is where the interesting question always is.
- **Re-deriving a rate from someone else's published figure is risky.** Round
  358 reported "81 991 entries (2733/s)"; 81 991 entries in a 30-minute window
  is 2733 per MINUTE. Sixty-fold. Re-measure rather than re-divide.
- **Do not compare a rollup computed over an append-only file across runs.**
  The input grew. Compare methods on ONE snapshot, and quote the snapshot's
  size next to the number.
- **Bound the TOTAL, not only the per-item budget.** Round 370 launched a
  7-item sweep under a 900 s outer timeout while its own inner per-item
  timeouts allowed up to 600 s EACH — a worst case of 4200 s under a 900 s
  cap. It was killed part-way and produced nothing. Per-item sizing and a
  total budget are two separate numbers; deriving one and assuming the other
  is the same mistake as using a constant, one level up. Write both down and
  check that `n_items x per_item_max <= total`, or make the runner emit
  partial results as it goes so a kill still leaves evidence.
- **The most accessible item is usually the cheapest one, which makes it the
  worst sample.** Round 370 timed the sweep on the CURRENT boot (11 s) because
  it was the easiest to reach, and projected from it; the deep-history boots
  cost >100 s each and never finished. Cost frequently correlates with
  distance from whatever index/head the tool seeks from, and the item you
  reach for first is the one nearest that head. Sample the item your proxy
  says is worst, not the one in front of you.
- **A budget is a property of the RUNNER as much as of the work, and the
  runner is the half nobody measures.** Round 487 of this program: the
  `unit_tests` checker in `skills/skill-authoring/scripts/corpus_check.py`
  reported `COULD NOT RUN` in three rounds after 32 rounds inside its 600 s
  budget. Timed ALONE on the same box it takes **183.92 s**. Nothing had
  grown. `run_driver.sh` backgrounds FOUR pytest suites on a machine where
  `nproc` is 1, so a fair share is a quarter core and `4 x 183.92 = 735.7 s`
  is the expected contended runtime — over budget with a workload that never
  moved. The repair is `solo_cost x concurrency x margin`, with the
  concurrency COUNTED in the runner's own source (`grep -c '_PID=\$!'`) so a
  fifth concurrent job expires the constant instead of quietly re-breaking it.
  A budget derived only from the item's cost is right about the item and
  wrong about the machine.
- **A budget crossed and re-crossed reads as several defects, and it is one.**
  Round 496: a node's red-attribution record said "RECURRENT — 2 earlier
  episodes, last closed at round 486", which invites you to look for something
  that keeps coming back. Plotting the check's VERDICT against its own WALL
  TIME across 30 rounds of logs showed a single threshold: every PASS total
  below 1150 s, every FAIL total above 1100 s, the adjacent pair 18.34 s
  apart, and no PASS total exceeding any FAIL total. One defect, one
  threshold, a wall time wandering across it. Before you hunt a recurrence,
  sort the runs by the quantity the budget bounds and see whether the verdict
  is just its sign. Two minutes of `grep` over the existing logs; it also
  tells you the contended cost you need for step 3 without running anything.

- **A partial result is a verdict, but only if you can read the alphabet it
  is written in.** Round 451 of this program made a killed checker report
  what it had already said — by parsing its partial output for
  `ERROR <CODE>` lines. It was written *because* one particular checker kept
  timing out, and that checker is a `pytest -q` run whose findings are `F`
  characters in a bar of dots. Result: eight killed runs over 36 rounds, zero
  salvaged findings, and five real test failures sitting in the evidence file
  unread. If you add a salvage path, name the format each subject actually
  speaks and check that the parser handles the ONE you wrote it for.
- **Killing the local client does not kill the remote work.** When round 370's
  `ssh` was killed at its budget, the `journalctl` processes on the far side
  kept running for another 6 minutes, drove the load average on a shared box,
  and were then briefly misread as organic traffic by the same round. Any
  budget enforced by killing a local process needs a matching reap on the
  remote side — and any load/latency measured after such a kill is suspect
  until you have confirmed nothing of yours is still running.

## Verification

On a repo with a per-item cost spread, the technique is working when:

1. `--plan` (sample + project, run nothing) prints per-item budgets that
   differ by roughly the cost spread, not by the size spread.
2. A second run of the same sweep does approximately zero work except the one
   open item.
3. Every artifact on disk answers "was this scan complete?" without re-running
   it.

Worked instance, `nuc/reachability_check.py journal-boots` (round 364):

```
$ python3 nuc/reachability_check.py journal-boots \
    --boot-history state/nuc-boot-history-r364/list-boots-r364.json \
    --cache-dir state/nuc-journal-cache --plan
# expected: per-boot timeout_s spanning ~60 to 3600, every row sized_from=measured

$ python3 -m pytest nuc/tests/test_reachability_check.py -q
# expected: >= 230 passed (round 459)
```

Second worked instance, the runner-side sizing (round 487):

```
$ .venv/bin/python -m pytest -q skills/skill-authoring/scripts/test_corpus_check.py \
      -k DerivedBudget
# expected: 5 passed — the budget equals ceil(solo x concurrency x margin),
# the solo cost matches state/harness/round-487/unit-tests-solo.json, and the
# concurrency matches a count of `_PID=$!` in run_driver.sh
```

Third worked instance, the self-referential budget (round 496):

```
$ .venv/bin/python3 -m pytest -q nuc/tests/test_constant_audit.py \
      -k "budget or narrow or selector"
# expected: 6 passed — the budget equals ceil(solo x concurrency x margin)
# against state/nuc/round-496/fast-check-solo.json, the concurrency matches a
# count of `_PID=$!` in run_driver.sh, the nested leg still carries its `-k`,
# and pytest ITSELF confirms the selector excludes the test that re-spawns the
# script (a hand-rolled `in` check let that mutant live).

$ NUC_FAST_CHECK_NESTED=1 bash nuc/run_checks_fast.sh \
      -k "fast_check and not strict_instrument"
# expected: nuc-checks PASS in ~6 s, where the unnarrowed leg takes ~319 s
```

Measured spread that motivated it: 7 boots of ONE machine, entry density
0.037/s to 58.85/s (**1605x**), projected scan cost 0.3 s to 1944 s. The
single 1400 s constant it replaced was ~100x too large for six of them and
too small for the seventh.
