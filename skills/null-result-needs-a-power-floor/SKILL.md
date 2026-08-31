---
name: null-result-needs-a-power-floor
description: Use when a negative or "nothing found" result is about to be reported as a fact about the system under test — a significance sweep that returns no significant units, an A/B test that "showed no difference", a bisect that blames nothing, a scan that finds no vulnerabilities, a flaky-test hunt that clears every test, a correlation matrix with nothing above threshold, or any tool that prints an empty list of positives. Symptoms: an empty results array quoted as evidence of absence; a multiple-comparisons correction applied without checking the corrected bar is reachable; a per-candidate verdict of "not significant" when no outcome for that candidate could have been significant; a threshold or window size chosen once and never swept; a summary that cannot distinguish "the effect is absent" from "the instrument could not have seen it". Covers computing each candidate's best possible outcome before looking at the data, reporting reachability beside the null, and sweeping the constants the verdict depends on.
---

# `supported: []` is not a result until you show it was reachable

A detector ran over a record and returned nothing. The sentence that comes
next is always some form of *"there is nothing there"*.

That sentence has two readings and the output almost never separates them:

1. **The effect is absent.** A fact about the system.
2. **The instrument could not have detected the effect if it were present.**
   A fact about the arithmetic.

Only the first is a finding. The second is a measurement of your own tooling
wearing a finding's clothes, and it is *more* likely the longer the pipeline —
because every filter, every correction, every threshold narrows what the run
could possibly have said, and none of them announce that they did.

The fix is cheap and it does not need the data: **compute, for each candidate,
the best outcome it could possibly have achieved, and check whether that best
outcome would have cleared your bar.** If it would not, that candidate is
*untestable* in this record, and "not significant" says nothing about it.

## The instance this came from

Round 406 of this program built an attribution grader for a memory-tight
inference box: which systemd unit, if any, is responsible for the swap-out
events in a 36-hour boot? It pooled two `sar` day-files (218 ten-minute
buckets, 3 of them "costly"), tested 16 units with an exact hypergeometric
tail Bonferroni-corrected over the family, and published:

> 16 units tested, **`supported: []`** — this instrument, over this record,
> licenses no causal claim at all.

Careful, hedged, and it reads as a fact about the box. Round 412 computed the
power floor and found:

* **8 of the 16 units could never have been supported.** Seven because they
  fired *once* — occupancy 1 — and covering one of three costly buckets by
  chance has `p = 3/218 = 0.014`, which times 16 is 0.22. One because it fired
  *36 times*, and occupancy that high makes covering costly buckets unremarkable.
* The prime suspect, `fwupd-refresh`, had `p_best × 16 = 0.067 > 0.05`.
  **Even if it had hit all three costly buckets, the verdict would still have
  read "coincidence".** Its result was fixed before the data was read.
* Run per-day instead of pooled, one of the two days has **one** costly
  bucket, and then `p_best = 1/218 × 16 = 0.073`: **no candidate at any
  occupancy could have been supported, whatever happened that day.** The tool
  returns the same confident empty list.
* The suite's own test for the "consistency" rule used a fixture in exactly
  that vacuous regime. It asserted the right verdict *string* while the branch
  it was named after was unreachable behind an earlier one.

Nothing was miscomputed. Every p-value was correct. The missing quantity was
whether the bar was reachable at all.

## When to use — trigger conditions

Any time you are about to write "no X found", "not significant", "no
regression detected", "clean", or ship an empty positives list — and
especially when a **multiple-comparisons correction** is involved, because
dividing the bar by the family size is the single most common way to make a
result unreachable without noticing.

## Steps

1. **Write down the bar, explicitly.** Not "p < 0.05" — the *effective*
   per-candidate bar after every correction. Bonferroni over `m` candidates
   makes it `α/m`. If you cannot state this number, stop here; you do not yet
   know what your run was testing.

2. **For each candidate, compute its best possible outcome.** Not what it did
   — what it *could* have done. In a hypergeometric setting that is covering
   `min(K, d)` of the K positives given occupancy `d`. In an A/B test it is
   the effect size your `n` can resolve. In a scan it is the smallest finding
   the rule can match. This never needs the observed data.

3. **Compare, and label.** `best_case > bar` ⇒ **untestable**. Emit that as a
   distinct verdict, not as "not significant". They are different claims and
   collapsing them is the whole defect.

4. **Emit a run-level reachability flag.** One boolean —
   `supported_was_reachable` — that is false when *no* candidate was testable.
   A null from a run where this is false must never be quoted as evidence.
   Make it impossible to read the output without seeing it.

5. **Check both ends of the range, not just one.** The testable set is often
   **not** an interval starting at the smallest exposure. Covering *one*
   positive by chance is common; covering *two* is rare. So a candidate seen
   once can be untestable while a candidate seen twice is testable. "Too
   little exposure to test" is as real as "too much", and only the second is
   intuitive.

6. **Record the family the candidate was graded against.** Under Bonferroni,
   testability is a property of the **run**, not of the candidate: the same
   evidence is testable in a family of 1 and untestable in a family of 16.
   Widening the family can retract a claim with no new observation. The
   correction is still right — the candidate was chosen by being noticed — but
   a verdict without its `n_candidates` is not reproducible.

7. **Sweep every threshold the verdict depends on.** Re-run the whole grading
   across a range of each magic constant. If the null holds everywhere, say
   so and give the range — that is what makes it a result. If it moves, **the
   threshold is the result** and no single run may be quoted.

8. **If a constant has no derivation, refuse to invent one.** A threshold
   derived from two labelled events is a measurement. The same threshold on a
   channel with no labels is a choice. Make the code *raise* and demand the
   number explicitly rather than shipping a default with a derivation-shaped
   comment and no derivation.

9. **Prefer the instrument with more events in it.** Given two channels over
   the same record, the one with more positives has more power and degrades
   more gracefully — its bar stays reachable as thresholds tighten. Round 412
   predicted the opposite and was wrong: the sparse channel was the one that
   collapsed to zero power, because there was nothing left to be improbably
   covered.

## Pitfalls

- **Quoting an empty list as a finding.** The failure this skill exists for.
  "No unit was supported" is only publishable next to "and here is the
  occupancy band that could have been".
- **Reporting `untestable` as `not significant`.** The second implies a test
  ran and the candidate lost it. When the bar was unreachable, no test ran.
- **Assuming the testable set starts at the lowest exposure.** See step 5. The
  single-occurrence candidate feels like the cleanest case and is usually the
  one that can never be decided.
- **Asserting a verdict string in a test instead of the branch.** A test whose
  fixture cannot reach the rule it is named after will still pass, forever,
  and will only be caught when someone inserts a branch above it. Assert the
  discriminating quantity too, not just the label.
- **Aggregating to buy power without saying so.** Pooling days/shards/runs to
  lift K out of the vacuous regime is legitimate and often necessary — but it
  changes what the null is about, and the pooled and per-shard runs can return
  the same empty list for opposite reasons.
- **Letting a parser drop a marker the new consumer needs.** A record split
  by an event (a reboot, a schema change, a restart) is not one series. If the
  parser silently discards the marker, a later metric that differences across
  it will book the discontinuity as a real effect, and nothing downstream can
  tell.
- **Treating an undefined bucket as a zero.** A window whose cost is unknown
  is not a window that cost nothing. Return `None` and route it to
  `unclassified`; a zero silently inflates every denominator.

## Verification

You have applied this correctly when all of the following hold:

1. The output carries a per-candidate `testable` (or equivalent) field **and**
   a run-level reachability boolean.
2. There is a test that constructs a record in which **no** candidate is
   testable, and asserts the run-level flag is false.
3. There is a test that the new `untestable` verdict cannot capture anything
   that would otherwise have been positive — i.e. the null is unchanged by
   introducing it.
4. There is a test that the same evidence flips verdict when the family size
   changes, so the dependence is documented rather than discovered later.
5. Every threshold the verdict depends on has either a written derivation from
   labelled data, or a sweep in the round record showing the verdict across
   its range, or a hard refusal to default.

```bash
# 1. can a record of this shape support ANYTHING? no data needed -- run it
#    BEFORE the capture, not after
python3 -m nuc.perturbation power --n-buckets 218 --n-costly-buckets 1 \
    --n-units-tested 16
# -> "any_testable": false  =>  an empty result here is arithmetic, not evidence

# 2. the verdict as a function of every threshold it depends on
python3 -m nuc.perturbation sweep --day sa30.txt:2026-08-30 \
    --day sa31.txt:2026-08-31 --journal unit-starts.txt --channel commit

# 3. the tests that pin all five verification points below
python3 -m pytest -q nuc/tests/test_perturbation.py
```

Reference implementation: `power_floor` and `best_case_p` in
`nuc/perturbation.py`; sweep in `channel_sweep`; CLI
`python3 -m nuc.perturbation power --n-buckets N --n-costly-buckets K
--n-units-tested M`, which answers "could a record of this shape support
anything?" **with no data at all** — so it can be run before the capture, not
after. Tests: `nuc/tests/test_perturbation.py`, the round-412 block.

## Related

- `cause-needs-a-denominator` — the positive-direction twin. That skill stops
  you attributing an effect to the only candidate present; this one stops you
  concluding absence from a detector that could not have detected presence.
  Both failures are the same missing quantity: what the candidate's exposure
  makes likely by chance.
- `measured-exemption` — for the "refuse to invent a constant" half of step 8.
