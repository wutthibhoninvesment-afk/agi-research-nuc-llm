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

5. **Write the sizing INTO the artifact**, next to the result: the sample, the
   projection, the budget granted, the wall time actually spent, and an
   explicit `complete` flag. Derive `complete` from evidence, not hope —
   "returned inside 95 % of its budget" is a usable rule. Without this, step 1
   of the next investigation is re-running everything.

6. **Cache per item, keyed on immutability.** If an item cannot change once
   finished (a closed log, a released tag, a merged commit), scan it once ever
   and skip it forever after. This is what turns a sweep too big for one
   session into one that is merely resumable — and it means a partial run is
   banked progress, not wasted work.

7. **Order the work cheapest-first** so a run that is cut short has banked the
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

Measured spread that motivated it: 7 boots of ONE machine, entry density
0.037/s to 58.85/s (**1605x**), projected scan cost 0.3 s to 1944 s. The
single 1400 s constant it replaced was ~100x too large for six of them and
too small for the seventh.
