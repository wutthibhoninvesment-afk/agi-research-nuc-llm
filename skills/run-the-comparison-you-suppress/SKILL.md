---
name: run-the-comparison-you-suppress
description: Use when a check, oracle, differential, linter or alert has an EXEMPTION branch that fires often and returns "ok" without comparing anything — a "skip if X" in a test oracle, a suppression rule in a scanner, an allowlist entry, a `continue` that drops a case, a known-flaky guard, a "not applicable" verdict. The move is to run the comparison the branch refuses to make, on every input where it fires, and report the REALIZED cost (how often it hid an actual difference) beside the potential cost (what it could hide). Covers splitting one exemption into the population it is correct for and the population it is dropping for nothing, finding the discriminating signal that is usually already computed and thrown away, tightening the branch behind a named constant, and keeping the alarm class that says the tightening was wrong. NOT for an exemption that has never fired (measure the distance instead) and NOT for deciding whether to delete a check.
---

# An exemption's cost is what it hid, not what it could hide

A suppression branch is reported by its **fire rate** and, if the reporting is
good, by its **surface**: how much of the comparison it drops when it fires.
Both are properties of the branch. Neither is a property of the *finding you
did not get*.

The number that is:

> On every input where the branch fired, run the comparison anyway.
> How many times would it have found something?

Call that the **realized cost**. Potential cost is an upper bound and is
usually 1.0 by construction — "when this fires we return ok without looking".
Realized cost is a measurement, it is almost always lower, and the gap between
them is the set of inputs your instrument is blind to for no benefit.

Real instance (round 401 of this program). A tail-transparency oracle runs a
program twice — as written, and with tail-call optimisation disabled — and
requires the same answer. Because the optimisation saves stack, the second run
can exhaust `max_depth` where the first did not, so the oracle exempts any
program whose second run hits the ceiling. Two prior rounds measured its fire
rate (13.4 % of the corpus) and recorded its surface as 0.0 (it drops
everything). Round 401 ran `first_difference(a, b)` on all 44 firings anyway:

* **27** — only the second run hit the ceiling; the answers differ; the
  difference *is* the ceiling. Correct exemption, doing its job.
* **17** — the answers were **identical**. The branch dropped a valid
  comparison and bought nothing.

Realized cost **61.4 %**, not 100 %. And 14 of the 17 free firings shared one
signal: **both** runs hit the ceiling, so neither got further than the other
and the comparison was on equal footing all along.

## The discriminating signal is usually already computed

This is the part that generalises. In every instance found so far, the number
that splits the two populations was **already produced by the code and thrown
away one line above the branch**:

```python
a, _ = _answer(...)        # <- the original run's depth. Discarded.
b, peak = _answer(...)
if peak >= max_depth:      # <- decides using ONE side of a two-sided fact
    return ok("space-exempt")
```

The suppression rule was written from the *asymmetric* case its author had in
mind, and expressed as a test on one side only. It therefore also covers the
symmetric case, silently, and nobody notices because the branch returns `ok`
and `ok` is what everyone expected. Look for the discarded half before you
build anything.

## When to use (triggers)

- An oracle, differential, property test or scanner has a branch that returns
  pass/ok/"not applicable" **without comparing**, and it fires on a
  non-trivial fraction of inputs.
- A suppression, allowlist, `# noqa`, `skipif`, known-flaky guard or
  "environment not supported" path is being reported by fire rate alone.
- Someone is about to widen an exemption to kill a false positive, or raise a
  budget/ceiling to convert exemptions, without knowing what the exemptions
  were hiding.
- A report prints "cost 100 %" / "surface 0.0" for a branch — that is a
  definition, not a measurement, and it is the tell.
- A "skip" count appears in a summary next to a pass count.

**When NOT to use:** the branch has **never fired** — then you have a zero and
the right move is a distance, see `../zero-rate-needs-a-distance/SKILL.md`;
or you are deciding whether to delete the check entirely, which is a
different question (this skill narrows branches, it does not remove them).

```
fire rate      how often the branch ran.
surface        what it COULD have hidden.       <- both about the branch
realized cost  what it DID hide.                <- about the findings
```

## Steps

1. **Find the branch and read what it returns.** You want the ones that
   return a PASSING verdict with no comparison. A branch that returns
   "inconclusive" is already honest; a branch that returns `ok` is the one
   that launders a skip into a pass.

2. **Look one line up for a discarded value.** `_`, an unused tuple element,
   a variable computed and not read, a field the row does not carry. That is
   your candidate discriminator, and using it costs nothing.

3. **Write the classifier before the fix.** Enumerate the populations the
   branch covers and give each a NAME, including the one that would be a real
   bug. In round 401 that was six classes; the one that mattered most was the
   empty one, `suppressed_at_ceiling` — "the branch fired, and the comparison
   would have failed for a reason that is not the exemption's". Naming it is
   what lets a future round tell an interpreter bug from a bad tightening.

4. **Run the suppressed comparison over the whole corpus** and report
   realized cost beside potential cost. Write one flushed row per input, so
   an interrupted run is a smaller sample and not a false zero.

5. **Check whether the free population is bounded or unbounded.** Some free
   firings convert if you raise a budget; some never will. Run a LADDER of
   ceilings and look at whether the demand is censored at every rung. Round
   401 found 11 of 14 free firings converted at a higher ceiling and 3 did
   not — those 3 were the ones a previous round had spent its budget failing
   to convert.

6. **Tighten behind a named constant, not silently.** `SPACE_EXEMPT_WHEN_
   BOTH_AT_CEILING = False` with the measurement in its comment. A future
   round that hits a false positive should flip a switch and read why, not
   re-derive your reasoning from a diff.

7. **Move every mirror of the predicate in the same commit,** and let the
   existing cross-check prove you did. Predicates like this are usually
   duplicated in a reporting/mapping layer; if a test asserts the two agree,
   that test is your verification, and if no such test exists, write it
   before the tightening.

8. **Say what the tightening can cost.** "Zero false positives on this
   corpus" is the honest claim. "Safe" is not.

## Pitfalls

- **Potential cost looks like a measurement.** `surface: 0.0`, `cost 100 %`,
  `skipped: N` are all true and all definitional. If a number falls out of
  the branch's *shape* rather than out of the inputs, it cannot tell you
  anything about the inputs.
- **The free population is not evidence the branch is wrong.** It is evidence
  the branch is *too wide*. The correct output is a narrower predicate, not a
  deleted one — round 401's exemption is still right for 27 of 44 firings.
- **A class-preserving shrinker will destroy the mechanism you are
  investigating.** Round 401 shrank three witnesses while holding the CLASS
  fixed; the integer minimiser turned `nest(n - 1)` into `nest(n - 0)`,
  which is still unbounded and is a completely different cause. Shrink for
  the reader, but read the ORIGINAL for the mechanism, and say which one the
  explanation came from.
- **Zero alarms is a result about your corpus.** Report it as such and keep
  the alarm class in the classifier. A tightening with no alarm class is a
  tightening you cannot audit later.
- **Don't tighten while a long sweep is running against the same file.** The
  sweep's rows and your new predicate are two instruments in one file. Freeze
  the source for the sweep's duration or stop the sweep first.
- **The reporting layer can drop the very rows the exemption lives in.** If a
  summary skips rows with an error/timeout field, and those are the slow
  inputs, then the exemption's population and the summary's population differ
  — and every rate you publish is about the wrong denominator. Count from the
  paired rows, not from the summary.
- **Two exemptions can look like one.** If the branch has an `or` in it, the
  realized cost of each disjunct is a different number. Split first.

## Verification

Against your own exemption, in order:

```
# 1. classify every input the branch fires on, incrementally written
python3 -m harness.swe.spacewitness scan 360 --max-depth 500
# 2. realized cost beside potential cost
python3 -m harness.swe.spacewitness report
# 3. is the free population convertible by a bigger budget, or never?
python3 -m harness.swe.spacewitness bracket --seeds 140,273,341
# 4. a minimal witness per class (read the ORIGINAL for the mechanism)
python3 -m harness.swe.spacewitness shrink --seeds 140,273,341
# 5. the mirrored predicate still agrees with the branch
python3 -m pytest -q harness/tests/test_swe_spacewitness.py
```

Expected shape: `report` prints a realized cost strictly below the potential
cost, a non-zero `tightenable` count and an `ALARM` count you can state;
`bracket` says `unbounded: true` for exactly the seeds no ceiling converts.

- [ ] the branch's return value identified as a PASS, not an "inconclusive"
- [ ] the discarded value one line above the branch found and named
- [ ] every population the branch covers has a name, including the alarm one
- [ ] realized cost measured over the whole corpus, printed beside potential
- [ ] the free population split into convertible and never-convertible by a
      ladder, not by argument
- [ ] the tightening sits behind a named constant whose comment carries the
      measurement
- [ ] every mirror of the predicate moved in the same commit, with a test
      that asserts they agree
- [ ] the alarm class kept, its count reported, and "zero on this corpus"
      written rather than "safe"
