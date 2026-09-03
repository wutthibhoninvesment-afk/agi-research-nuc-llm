---
name: ratchet-needs-a-conservation-invariant
description: Use when a quality bound is a one-way number — "residual <= 100", "coverage >= 90%", "warnings <= 3", "p95 < 200ms" — and the only evidence it protects anything is that it has never gone up. Symptoms - a threshold that has been lowered several times and never raised; a test named after a count; a "we fixed 12 of 13" claim where the thirteenth left no trace; a bucket that has a counter but no row you can open; a regression that made a metric BETTER. Covers turning an aggregate bound into a per-unit accounting claim - naming the population, giving every outcome a positioned record rather than a counter, and falsifying the invariant against the code from before the change. NOT for choosing a threshold value, and NOT for finding which test would catch a bug (that is falsifier-must-kill-something).
---

# A ratchet cannot tell a fix from a suppression

A **ratchet** is a bound on an aggregate that is only ever allowed to move
one way:

```python
assert residual <= 100        # 166 -> 114 -> 100 over four rounds
assert coverage >= 0.90
assert len(warnings) <= 3
```

It is cheap, it is popular, and it is protecting less than it looks. A
ratchet passes for **two** reasons that it cannot tell apart:

| the number fell because | what happened |
|---|---|
| the work got better | a real fix |
| a unit stopped being counted | **a suppression, which the ratchet REWARDS** |

The second is not hypothetical and it is not rare. It is the normal shape of
a regression in any instrument that classifies things: a bug that makes one
unit invisible removes it from the numerator, the ratchet gets *greener*, and
the test named after the number goes green on the regression that broke it.

Round 474 of this program watched exactly that. `residual <= 100` had fallen
166 → 114 → 100 across four rounds. The step to 100 was a REGRESSION: a
binding-environment bug let one call site borrow another's resolved values,
so a residual row that belonged to an unreadable loop disappeared. The row
was not fixed. It was hidden — and the assertion that existed to protect the
number went green on it, because the number went down.

**The repair is not a better threshold. It is a second claim of a different
shape.**

## The two claims, side by side

* **Aggregate (the ratchet).** "The residual is at most 101." Cheap to
  check, cheap to game, says nothing about any individual unit.
* **Conservation (the invariant).** "Every unit of the population lands in
  exactly one accounted outcome, and each outcome carries a coordinate a
  reader can open."

A suppression bug always violates the second and often improves the first.
Ship them together or the ratchet is decoration.

## When to use (triggers)

* A threshold in a test or CI gate has been tightened several times and
  never loosened, and nobody can say what would happen if a unit vanished.
* A test is named after a count (`test_the_residual_fell_...`,
  `test_no_X_survives`, `test_zero_warnings`).
* A report says "we closed 12 of the 13" and the thirteenth's disappearance
  was never traced to a specific fix.
* A dashboard number improved right after a refactor nobody expected to move
  it.
* A bucket in your accounting has a COUNTER but no per-item record —
  "skipped: 259", "deduped: 21", "ignored: 7".
* You are about to RAISE a ratchet (make it looser) and want to know whether
  that is honest.

**Not** for picking the threshold's value, and not for asking which test
would have caught a bug — that is `falsifier-must-kill-something`, which
this pairs with naturally: a ratchet is a test that can go green for the
wrong reason, and that skill finds tests that cannot go red at all.

## Steps

1. **Name the population and its unit, in one sentence, before writing any
   assertion.** "Every `for` statement in the corpus whose target name
   reaches a runner call inside its own body." If the sentence needs an
   "and usually", the invariant will have the same hole.

2. **Enumerate the outcomes a unit can have. All of them.** Not the
   interesting ones. Round 474's were: produced a program, was a residual,
   was excluded, was a duplicate. Four, and the fourth is the one that had
   been invisible for six rounds.

3. **Give every outcome a POSITIONED RECORD, not a counter.** This is the
   step that is usually skipped and it is the one that makes the invariant
   possible. A counter closes the arithmetic and loses the coordinate: you
   can prove `a + b + c = n` and still be unable to say *which* unit is in
   `c`. Round 468 of this program gave a dedup bucket a counter for exactly
   the right reason and left the position unrecorded; six call sites then sat
   outside the record entirely until round 474 gave the bucket a row.

4. **Check that the coordinate actually identifies the unit.** A record with
   a coordinate that under-determines it is only half a record. Measure the
   collision rate rather than assuming one: `file:line` looked adequate and
   41.7 % of the population shared one. Adding a column recovered 0.6 % of
   that, because the real relation was one-to-many — one call site denoting
   thirty-two units. Where the relation IS one-to-many, say so and add an
   ordinal (`file:line:col#k`) rather than pretending a position is a key.

5. **State the invariant per-unit AT ITS OWN COORDINATE.** "Something is
   recorded inside this loop's own line span" — not "the counts add up".
   Span-local is what makes a borrowed answer visible, because a unit
   answered for by its neighbour has nothing at its own coordinate.

6. **FALSIFY IT against the code from before the change.** Non-negotiable,
   and the step that turns a plausible invariant into a measured one:

   ```bash
   git show <old-rev>:path/to/instrument.py > /tmp/old_instrument.py
   # run the SAME invariant against the old module and count violations
   ```

   Round 474: 74 units, **7 unaccounted** against the old module, **0**
   against HEAD. An invariant that reports 0 on both versions has not been
   shown to detect anything.

7. **Only now move the ratchet, in the same commit as the invariant.**
   Write the reason into the assertion, not into a commit message that
   nobody reads next to the failing line. A raise with no invariant beside
   it is a debt.

8. **Say out loud that the ratchet is now weaker.** It is a trade — a bound
   a suppression bug can satisfy, exchanged for an invariant a suppression
   bug cannot — and the next person to raise it should know it has already
   been spent once.

## Pitfalls

- **Raising the ratchet and stopping there.** The number moved for a reason.
  If you cannot name the unit that moved, you have not finished.
- **A counter used as a bucket.** "deduped: 259" is arithmetic, not
  accounting. The test is whether a reader can open the file at the thing
  the counter counted; if not, that outcome is a hole and the invariant that
  quantifies over it is unstatable.
- **Conservation over a subset, published as total.** Round 474's invariant
  is PER-FILE, because only in-file duplicates got a row; a unit first seen
  in another file would still be unaccounted. That is a real limit and it is
  written down rather than discovered later.
- **Asserting the SHAPE where the VALUE is what matters.** `len(set(lines))
  == 1` is satisfied by every unit at the WRONG coordinate just as well as
  by every unit at the right one. Round 470 wrote that as a mis-attribution
  check and it was the one assertion its own fix did not move.
- **Naming the wrong counter as your falsifier.** A prediction that says "if
  counter X moves, my claim is wrong" has to name the counter the claim is
  actually about. Round 474 banked "if a count pin goes red, my
  corpus-invariance predictions are wrong" — and the pin that went red was
  on the RESIDUAL count, not the CORPUS count, which would have retracted
  two correct predictions.
- **Believing a conservation run taken under contention.** It walks the
  whole population and is one of the slower checks in a suite. On a
  single-core box, run it solo or report the number as an upper bound.

## Verification

```bash
cd ~/agi-research-nuc-llm/languages/whence

# the ratchet and the invariant, in the same file, both green at HEAD
python3 -m pytest -q -c pytest.ini -p no:cacheprovider \
    tests/test_testcorpus_census.py \
    -k "residual_fell or accounted_for_at_its_own_span"

# the invariant reports 0 violations at HEAD ...
python3 -m pytest -q -c pytest.ini -p no:cacheprovider \
    tests/test_testcorpus_census.py \
    -k accounted_for_at_its_own_span

# ... and step 6 is what makes that mean something: against the module from
# before the fix the same walk reports 7 of 74 unaccounted.
git show 4231bc3:languages/whence/depthcensus.py | head -1
```

Green is not the interesting outcome here. The number to look for is step
6's pair: **a violation count that differs between the old module and the
new one.** If it is 0 on both, the invariant is not yet evidence, and the
ratchet it was written to protect is still alone.
