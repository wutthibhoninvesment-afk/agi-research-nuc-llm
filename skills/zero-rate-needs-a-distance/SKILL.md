---
name: zero-rate-needs-a-distance
description: Use when a count of zero is being read as evidence that a bug class, failure mode or exception does not occur — a fuzz campaign that found no instances, an exemption or filter that has never fired, an alert that has never triggered, a check someone wants to delete because it never fires, a "0 findings" scan, or a green suite cited as proof a class is absent. The move is to stop reporting the rate and start measuring the DISTANCE between what the corpus/workload actually produces and the threshold that would produce the class, then pin the distance instead of the count. Covers naming the boundary as an inequality, measuring demand dynamically rather than reading the generator, constructing one input inside the band to prove the instrument works, and writing a tripwire that fires when the corpus moves toward the boundary. NOT for a class that has been observed at least once (that is a rate, and rates are fine), and NOT for deciding whether a bug matters.
---

# A zero is a fact about the corpus until you measure the distance

A sweep reports `0 occurrences`. Two very different worlds produce that
line:

1. the condition is genuinely rare or impossible in the system, or
2. **the inputs never got close enough to the boundary to try.**

The count cannot tell them apart, and every reporting convention there is —
"0 findings", "never fired", "no regressions" — renders both worlds with the
same characters. The distinguishing measurement is not a bigger sweep. It is
the *distance* from what the corpus demands to the threshold at which the
class appears. Distance separates "does not happen" from "cannot happen
here", and it is the only one of the two numbers that stays meaningful when
somebody edits the generator.

Real instance (round 377 of this program). The guest-differential oracle
exempts any field where either evaluator ran out of depth. Round 371 split
that exemption into `both_missed` (fine) and `host_valued` (a real
divergence: the host answers, the guest refuses) and owed a rate. Measured
over the fuzz corpus, `host_valued` fired **zero** times. The rate was not
the finding. The generator draws its recursion counts from `[3, 5, 8, 12,
20]` against a guest ceiling of **400** and a host ceiling of **1000000**,
so the entire band in which the class can exist — `(400, 1000000]` — sits
20x above the largest number the corpus ever asks for. The zero was a fact
about the grammar. One hand-built program inside the band fired the class
immediately.

## When to use (triggers)

- A campaign, fuzzer, scanner or linter reports **0** of some class and that
  is being summarised as "clean", "not an issue", or "doesn't happen".
- An exemption, allowlist entry, feature flag branch or error handler **has
  never fired** and someone proposes deleting it, or trusting it.
- A monitoring alert or tripwire has never triggered and is being cited as
  evidence of health.
- A green test suite is offered as proof that a bug class is absent.
- A rate is quoted with no statement of which population it describes.
- The inputs come from a generator, corpus or synthetic workload whose
  parameter ranges are in code you can read.

**When NOT to use:** the class has been observed at least once (you have a
rate, and a rate is a real measurement); or you are deciding whether a
finding is worth fixing — this skill is about what a zero means, not about
severity.

```
count == 0  is a statement about the INPUTS.
distance    is a statement about the SYSTEM.
Report the second; the first is only its shadow.
```

| Excuse | Reality |
|---|---|
| "2000 seeds, zero occurrences — it doesn't happen." | 2000 draws from a distribution whose support excludes the class. Sample size cannot fix support. |
| "The exemption has never fired, so it's safe to widen it." | An exemption that never fires is untested code holding a verdict. Widening untested code is how the class becomes invisible instead of absent. |
| "The alert never triggered, so the system is healthy." | Or the alert cannot fire. Fire it deliberately once; that is the only thing that distinguishes the two. |
| "Bigger sweep, same answer — that's convergent evidence." | Convergent on the corpus, not on the system. Two zeroes from the same generator are one measurement. |
| "The suite is green." | Check the suite RUNS the file. A deselected test contributes a zero indistinguishable from a pass. |
| "We can compute it from the grammar — max literal is 100." | A static read of a generator is a LOWER bound. Composition (`100 * 100`) reaches past every literal in the pool. |

## Steps

1. **Write the class as an inequality with a threshold.** Not "the oracle
   sometimes exempts a real bug" but "the class exists exactly when
   `iterations > guest_ceiling` and `iterations <= host_ceiling`". If you
   cannot write the inequality, you do not yet know what the zero counted.
   *Outcome:* one boundary condition, in terms of named constants.

2. **Find both constants in the code, not in the docs.** A band has two
   edges and they usually live in different files, often in different
   languages. Record file and line for each.
   *Outcome:* the band, with its width, as an explicit number.

3. **Measure what the corpus DEMANDS, dynamically.** Reading the generator
   gives a lower bound only. Make the threshold a parameter (a patched
   constant, an injected limit, a config override), re-run the corpus on a
   descending ladder of thresholds, and record for each input the value at
   which its behaviour first changes. That value is its demand.
   *Outcome:* a demand distribution, not a single number.

4. **Report the distance as a ratio and name the population.**
   "`max demand 21` against a threshold of `400`, so the corpus runs at
   5 % of the boundary" is checkable. "0 occurrences in 500 seeds" is not.
   *Outcome:* one sentence a later round can falsify.

5. **Construct one input inside the band and run it through the real
   instrument.** If the class does not appear, the zero was measuring your
   detector, not the system — stop and fix the detector first. Keep the
   constructed input as a test; it is the proof the zero is about reach and
   not about capability.
   *Outcome:* a passing test that exhibits the class on demand.

6. **Pin the DISTANCE, not the rate.** A test asserting "the measured rate
   is 0.0 %" is a stale number waiting to happen and tells a future reader
   nothing about why. A test asserting "no generated input asks for more
   than N, and the threshold is M" goes red the moment somebody widens the
   generator — which is the exact moment the zero stops being true.
   *Outcome:* a tripwire that fires before the class does, not after.

7. **Say what the zero does and does not license.** In the record: "no
   instance in this corpus; the corpus cannot produce one; here is the
   constructed instance; here is the tripwire." Never let it compress to
   "not observed".
   *Outcome:* a claim whose scope is written down beside it.

## Pitfalls

- **Pinning the measured rate manufactures a stale claim.** The number was
  true of one checkout on one day. Six rounds later it is a line no one
  re-executes and everyone cites. Pin the structural distance, and leave
  the rate in the round record where its date is visible.
- **A static scan of the generator is a lower bound, and reads like an
  upper one.** Literal pools compose: a grammar whose largest literal is
  100 still reaches 10000 through `100 * 100`. Use the static scan as the
  cheap tripwire, and the dynamic ladder as the evidence.
- **Zero rows and a zero rate are different results.** A sweep killed before
  it wrote anything reports the same "nothing found" as a sweep that
  completed. Write results incrementally — one flushed row per input — so
  an interrupted run degrades to a smaller sample rather than to no sample.
- **Zero can mean the instrument never ran.** Check that the file, the
  check, or the alert is actually executed by whatever you believe executes
  it. Deselected test files, filtered log queries and disabled rules all
  produce a confident zero.
- **The exemption that swallows the class is usually correct for a
  different reason.** Before calling it a bug, split it: the same branch
  often covers one situation legitimately (a difference of DEGREE) and one
  illegitimately (a difference of KIND). Measure each half separately —
  see `../measured-exemption/SKILL.md`.
- **Don't redden a known divergence just because you can now see it.** Once
  the class is visible, the temptation is to make it fail. If it is known
  and deliberate, report it in the passing verdict instead; a standing
  campaign that is red for a known reason buries the unknown ones.
- **Sizing the sweep from nothing wastes the round.** Measure per-input cost
  on a pilot of ~10 first, then set N from the budget you actually have.

- **A demand equal to the threshold is CENSORED, not measured.** If the
  instrument stops AT the boundary — a depth budget, a max-iteration cap, a
  truncated log — every input that reaches it reports exactly the threshold,
  and the distance ratio comes out 100 % by construction. That is an artefact
  printed in true digits. Mark the row censored and run the ladder in the
  other direction: raise the ceiling until the input stops hitting it. Round
  383 found 73 seeds all reporting demand 500 against a threshold of 500;
  un-censored, their median demand was 1501 and their maximum 3001.

- **Do not generalise one measured distance into a prior.** Round 377 measured
  a corpus at 6.25 % of its ceiling. Round 383 predicted five more thresholds
  would be similarly far and was wrong about four of them — one cap sat
  exactly at the corpus median, one threshold sat six times BELOW the corpus
  demand. The constants were chosen for unrelated reasons (a guest stack
  budget, a loop's cost, a host recursion limit). Read what a constant is FOR
  before predicting anything about the distance to it.

- **The band may be unreachable by construction, and then the witness has to
  move the ceiling.** If two constants in files the checker never reads cap
  the input below the threshold, no program can enter the band — step 5's
  constructed input will not fire, and a bare "did not fire" reads as a broken
  detector when it is the result. Rewrite the CONSTANT instead, show the class
  appearing, and report the coupling: that is the real finding, because
  whoever raises that constant next will not know the checker depends on it.

## Verification

Against your own zero, in order:

```
# 1. the two edges of the band, from code
python3 -m harness.swe.exemptaudit band
# 2. what the corpus asks for, statically (cheap, lower bound)
python3 -m harness.swe.exemptaudit corpusnums 500
# 3. what the corpus asks for, dynamically (the real evidence)
python3 -m harness.swe.exemptaudit ladder 40 --budget-s 400
# 4. the rate itself, incrementally written and resumable
python3 -m harness.swe.exemptaudit sweep 500 --budget-s 900
python3 -m harness.swe.exemptaudit summary
```

Expected shape: `band` prints two constants and their gap; `ladder` prints a
demand distribution whose maximum is far below the band's lower edge; the
sweep's `host_valued` count is 0 **and** the round record says why that zero
is about the corpus.

- [ ] the class written as an inequality naming both threshold constants
- [ ] each constant cited by file and line, from code not docs
- [ ] demand measured dynamically on a ladder, not inferred from the grammar
- [ ] distance reported as a ratio, with the population named
- [ ] one constructed input inside the band exhibits the class through the
      real instrument, kept as a test
- [ ] the tripwire asserts the distance, not the rate
- [ ] results written incrementally, so an interrupted run is a smaller
      sample and not a false zero
