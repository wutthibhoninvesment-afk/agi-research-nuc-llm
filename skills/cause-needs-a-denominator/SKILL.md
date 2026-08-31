---
name: cause-needs-a-denominator
description: Use when an observed effect is about to be attributed to a named candidate cause because that candidate was the only one present — a slow request blamed on the one cron job in its window, a memory spike blamed on the single service that logged inside it, a regression blamed on the one commit that touched the file, a flaky test blamed on the one job sharing the runner, or any tool that emits a field like sole_attributable / only_candidate / unique_match. Symptoms: a causal sentence resting on a sample of one; a "the only X in the window" claim with no count of how often X occurs; an attribution inherited across reports until it reads as established; a suspect that is present at most incidents because it is present most of the time. Covers computing the candidate's own occurrence count, its quiet occurrences, its window occupancy, an exact chance model corrected for the fact that the suspect was chosen by being noticed, and the within-suspect replication that settles it without statistics.
---

# The only name in the window is not the cause

An effect happened. You look at the window it happened in, and exactly one
named candidate is there. Every instrument that reports this reports it the
same way — `sole_attributable: true`, "the only deploy that day", "the one job
on that runner" — and the sentence that comes next is always *"X caused it"*.

That sentence needs a number nobody has: **how often does X occur, and how
often does it occur without the effect?**

Uniqueness is a property of the *window*. Causation is a property of the
*candidate*. A candidate that occurs often enough is the only name in a great
many windows, including all the interesting ones, and no amount of staring at
one window reveals that. The measurement that does is the candidate's own
denominator.

Real instance (round 406 of this program). Round 394 attributed a 67.7 MB
swap-out on a memory-tight inference box to `fwupd-refresh`, the only systemd
unit that started inside the ten-minute bucket. Round 400 built a whole-boot
cost ledger, found 62 named fires and exactly one bucket with a single named
unit in it, and published `fwupd-refresh` as **the boot's only
sole-attributable event**. Two rounds, one report inheriting the other, and by
the third it read as established.

`fwupd-refresh` fired **36 times** across that same boot. **33 of the 36
buckets moved zero bytes.** On the first of the two days it fired 23 times for
23 zeroes and not one costly bucket — same box, same boot, same configuration,
the claimed cause present twenty-three times and the claimed effect absent
every time. The unit occupies 36 of the boot's 218 buckets, so it is within ten
minutes of **16.5%** of everything that ever happens on that machine. It was
not the explanation. It was the most frequent thing on the box, and frequency
is what "only name in the window" actually measures.

Nothing was wrong with the ledger. `sole_attributable` was computed correctly
and meant exactly what it said. The defect was reading a statement about a
window as a statement about a cause.

## When to use

Trigger on any of these:

1. A causal claim rests on "X was the only one there" — the only timer, commit,
   deploy, tenant, job, query, or process in the window.
2. A tool emits a uniqueness field (`sole_attributable`, `only_candidate`,
   `unique_match`, `n_candidates == 1`) and a report is about to quote it as
   attribution.
3. An attribution is being **inherited** — round N cites round N-1's
   attribution rather than the measurement under it. Inheritance is where a
   sample of one turns into a fact.
4. The same suspect keeps appearing across unrelated incidents. That is the
   signature of a frequent event, not a common root cause.
5. Someone is about to act on the attribution — mask the timer, revert the
   commit, drain the tenant.

Do **not** use this to refuse every attribution. The point is a gate that can
be passed, not a reason to believe nothing; step 5 is what passing looks like.
Skip it when the effect and the candidate are linked by a mechanism you can
demonstrate directly (a stack trace, a `strace`, a bisect that reproduces) —
a mechanism outranks any of the counting below.

## Steps

1. **Count the candidate's occurrences over the whole record, not the
   window.** This is the denominator, and it is almost never in the report,
   because the report was written from the incident outward. Widen to every
   day/boot/deploy the record covers. In the real instance, widening from one
   day to two took `fwupd-refresh` from 13 fires to 36 and added the 23-zero
   replication that settled it.

2. **Count the quiet occurrences — the times the candidate occurred and the
   effect did not.** Report it as a fraction:

   ```
   consistency = occurrences_with_effect / occurrences_total
   ```

   At 2/36 = 5.6%, the candidate does not determine the outcome; something
   else separates the expensive occurrences from the free ones, and that
   something is unmeasured. **This is the whole finding, and it needs no
   statistics.** Do the arithmetic before reaching for step 4.

3. **Compute occupancy — the share of all windows the candidate is in.**

   ```
   occupancy = distinct_windows_containing_candidate / total_windows
   ```

   36/218 = 16.5% means one window in six names this suspect no matter what
   happened in it. Occupancy is what makes a frequent candidate a false
   witness for *every* event, and it is the number to put in the report next to
   any uniqueness claim.

4. **Put a chance model on it, and correct it for how the suspect was
   chosen.** Exact hypergeometric tail — the counts are small and a normal
   approximation is wrong in exactly the small-K regime these problems live in:

   ```python
   def p_at_least(N, K, n, h):        # N windows, K "costly", n occupied, h hits
       return sum(math.comb(K, i) * math.comb(N - K, n - i)
                  for i in range(h, min(K, n) + 1)) / math.comb(N, n)
   ```

   Then multiply by the number of candidates that *could* have been noticed
   (Bonferroni). This correction is not pedantry: the suspect was selected by
   having been noticed, so the naive p-value answers a question nobody asked.

5. **State the verdict as one of several, not as yes/no.** The distinctions
   carry the reasoning:

   | verdict | when | what it means |
   |---|---|---|
   | `insufficient-data` | occurrences < 2 | no within-candidate replication; a cause and a coincidence are indistinguishable |
   | `no-evidence` | never coincided with the effect | |
   | `shared-only` | every coincidence shared the window with another candidate | nothing separates them |
   | `coincidence` | corrected p above threshold, or consistency below it | frequency explains it |
   | `supported` | consistent, separable, and rare | |

   `insufficient-data` is the one that matters most and the one every ad-hoc
   analysis omits. It is the state round 394 was actually in, and had it been
   named, two later rounds would not have inherited the claim.

6. **Put the gate in the tool, next to the flag that caused the error.** A
   uniqueness field and its denominator should be unable to travel separately.
   If the gate lives in a knowledge file it will be re-derived by hand, wrongly,
   by whoever reads the flag next.

7. **Pin the refutation to the real data as a test.** Assert the counts (36
   fires, 33 quiet) and the verdict, not just the code path. A regression here
   is silent and reads like a finding.

## Pitfalls

- **Uniqueness is not rarity.** `sole_attributable` says one candidate was
  present. It says nothing about how often that candidate is present, which is
  the only thing that makes presence informative.
- **A hit in a shared window carries no attributional information at all.** In
  the real instance the suspect was in *both* costly buckets, which looks like
  strong evidence until you notice one of the two was shared with four other
  units and cannot separate them. Count clean hits separately from all hits.
- **The chance model is the weaker argument. Lead with the replication.**
  "23 occurrences, 23 times no effect" is a measurement; a p-value is a model
  with assumptions. Round 406 had both and the replication is what settled it.
- **Widening the record can strengthen the claim, and you must be equally
  willing to publish that.** Step 1 is not a way to get to "coincidence".
- **Do not let the filter share the defect.** If you filter the record to
  windows where the effect occurred, every candidate has consistency 1.0. The
  denominator must come from the unfiltered record.
- **Watch for an instrument in its own numbers.** A unit that *writes* the
  measurement is in 100% of measured windows by construction. Exclude it
  explicitly and name the exclusion, or it dominates every base rate.
- **Absence of a named candidate is a live outcome.** In the real instance the
  other day's single costly bucket had *no* named unit in it at all — direct
  proof that these events do occur unattributed, which is precisely the null
  the uniqueness flag cannot represent.

## Verification

You have applied this correctly when all of these hold:

1. The report states the candidate's total occurrence count and its quiet
   count, adjacent to any uniqueness claim. `grep` your write-up for the
   uniqueness phrase; every hit should have a denominator within a sentence.
2. A single-occurrence candidate cannot reach `supported`, and there is a test
   asserting that. In round 406:

   ```
   test_a_single_fire_can_never_be_supported_however_expensive
   test_a_unit_whose_own_fires_are_mostly_free_is_a_coincidence
   test_a_costly_hit_shared_with_another_unit_is_never_attributable
   test_a_unit_that_is_consistent_clean_and_rare_IS_supported
   ```

   The fourth is not optional — a gate nothing can pass is a way of never
   believing anything, and it will be removed by whoever needs an answer.
3. Running the gate over the *whole* record reports a verdict for every
   candidate, not just the suspect. Round 406's run graded 16 units and
   returned `supported: []` — the boot licensed no causal claim at all, which
   is a publishable result and was not what the round set out to find.
4. The exact commands and their output are in the round file, including the
   predictions that missed. Round 406 predicted the suspect would be in
   **one** costly bucket; it was in **both**, which briefly looked like
   evidence for the claim being refuted.

Run it against a candidate you believe *is* the cause. If that also comes back
`coincidence`, your window count or occupancy is wrong — most often because
the record was filtered to interesting windows before counting.
