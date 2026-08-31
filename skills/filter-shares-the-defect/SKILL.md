---
name: filter-shares-the-defect
description: Use when a measurement, dashboard, differential or anti-rot test SELECTS its subjects with a predicate — "the rows that have both fields", "the sessions that reached checkout", "the requests that emitted a completion event" — and reports a rate, a count, or an "all N agree" claim over that filtered population. Symptoms: a fix lands and the headline number does not move; a defect is reported as ABSENT and later found widespread; a test says "all N cases now agree" and the interesting cases are not among the N; a metric looks healthy while users report the opposite. Covers spotting when the filter predicate reads the same field the defect corrupts or removes, measuring the excluded set instead of assuming it is small, and re-pinning the claim so the population is asserted with the number. NOT for sampling error (zero-rate-needs-a-distance), a hand-written subject list that fails to grow (derived-subject-set), or a deliberate documented skip (measured-exemption).
---

# When the filter and the defect read the same field

A measurement over a filtered population answers a narrower question than
the one it is written up as. That is usually harmless: the filter drops
irrelevant subjects. It is *not* harmless when the filter's predicate and
the defect touch the same field — because then the defect **decides its own
sample**, and every subject it hit is gone before the count begins.

The result is not noise. It is a confident, specific, wrong claim in the
right direction: "all ten agree", "the error rate is 0.3%", "the two
implementations are equivalent on everything comparable". Each is true of
what survived the filter.

Proven on `languages/whence` (round 398). A host/guest parse-error
differential asserted *"all ten want halves now agree"*. Membership in
those ten was decided by a regex requiring the substring `, got ` on both
sides — and the guest's defect was that it **wrote no `got` half at all**
at seven sites. Four of those seven had a want half that had disagreed the
whole time. The population was selected by the exact field the defect
removed. When the defect was fixed the set went 10 → 20 and the four
disagreements appeared, having been invisible to a green test whose
docstring named them as closed.

## When to use (triggers)

- A test or report claims "all N agree" / "0 differ" and N is the result of
  a filter rather than the whole corpus.
- A fix demonstrably landed and the headline metric moved by zero.
- A rate is computed over "the ones we could measure", "the complete
  records", "the rows present in both", "the sessions that finished".
- Two implementations are being compared and one of them is known to omit,
  truncate, or default a field that the comparison keys on.
- A defect is being written up as absent, rare, or closed on the strength
  of a filtered count.

**When NOT to use:** the filter drops subjects for a reason unrelated to
the defect (a date range, a tenant id); the population is the whole corpus
already; the concern is a hand-maintained subject list that never grew
(`derived-subject-set`); the skip is deliberate, documented, and you want
it counted (`measured-exemption`).

## Steps

1. **Write the filter predicate down as a sentence, field by field.**
   `_EXPECTED_SHAPE.match(h) and _EXPECTED_SHAPE.match(g)` is not a
   sentence; *"both sides produced a message containing `, got `"* is.
   Do the same for the defect: *"the guest omits the `, got ` clause"*.
   Put the two sentences next to each other. If they name the same field,
   stop — the measurement is unsound as written, regardless of its value.

2. **Count the excluded set before you look at anything else.** Not its
   size relative to the total — its size, and its members by name.
   ```
   included = [s for s in subjects if predicate(s)]
   excluded = [s for s in subjects if not predicate(s)]
   print(len(included), len(excluded), sorted(excluded)[:20])
   ```
   `excluded` is the population the claim silently declines to make. A
   claim over `included` may be published only alongside `len(excluded)`.

3. **Ask what the excluded subjects WOULD have answered.** Usually there
   is a weaker comparison that still works on them: compare a prefix
   instead of the whole record, normalise the missing field to a sentinel,
   compare a shape instead of a value. In the whence case the four
   excluded programs could be compared on the `expected X` half alone —
   and they disagreed. One weaker comparison over the excluded set is
   worth more than a stronger one over the survivors.

4. **Fix the defect, then re-run and watch the POPULATION, not the rate.**
   The population size moving is the evidence the filter was
   defect-shaped. 10 → 20 shared cases is a stronger statement than any
   agreement percentage, because a rate can stay flat while membership
   turns over completely.

5. **Re-pin the claim with the population in it.** Assert the size of the
   filtered set as well as the agreement within it, so that a future
   change which shrinks the population fails instead of reporting a
   better rate:
   ```python
   assert len(shared) == 20, sorted(shared)          # the population
   assert sorted(want_agree) == sorted(shared)       # the claim
   assert sorted(got_agree) == sorted(shared)
   ```
   A claim without its denominator pinned is re-derivable to anything.

6. **State the residual classes by name.** After the fix, every remaining
   member of the FULL population should fall into an enumerated class
   ("18 carry a host-only hint, 2 carry a fact the guest does not
   compute"). An unclassified remainder is where the next
   defect-shaped filter hides; assert that no third class exists, so its
   appearance is a red test rather than a shrug.

## Pitfalls

- **"The excluded set is small."** Unmeasured. And smallness is not the
  issue: a defect-shaped filter concentrates the affected subjects into
  the excluded set, so a 7-of-51 exclusion held 4 of the 4 real
  disagreements.
- **The docstring makes the claim the code does not.** The whence test's
  prose said "all ten want halves now agree"; the code said "of the
  messages that both sides gave a got half to, the want halves agree".
  Read the assertion, then read the sentence someone will quote from it.
- **Aggregates hide convergence as well as divergence.** The same round's
  companion finding: a whole-string inequality count reported a fix that
  corrected eight of ten strings as a change of zero. Filtering and
  aggregating fail in opposite directions and often sit in the same file.
- **Re-pinning only the rate.** `assert agree_ratio > 0.9` survives the
  population halving. Pin the pair.
- **Fixing the filter instead of the defect.** Widening the regex makes
  the excluded subjects appear as failures — which is right — but the
  temptation is to widen it *and* relax the assertion. The population
  belongs in the test; the tolerance does not.
- **A green test that has never been red.** If the filtered comparison has
  never failed, it may not be able to. Plant a divergence in the subject
  under test and require the measurement to catch it, in the right
  category, before trusting a zero.

## Verification

- [ ] The filter predicate and the defect are written as two sentences and
      do not name the same field — or, if they do, the finding is recorded.
- [ ] `len(excluded)` and the excluded members' names are printed, not
      estimated.
- [ ] At least one comparison was run over the excluded set.
- [ ] The population size is asserted alongside the agreement claim.
- [ ] Every member of the full population after the fix belongs to a named
      class, and "no third class" is asserted.
- [ ] The measurement has been observed FAILING on a planted defect.

Worked example, with the code and the before/after populations:
[references/whence-round-398.md](references/whence-round-398.md).
