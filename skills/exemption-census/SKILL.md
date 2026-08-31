---
name: exemption-census
description: Use when auditing ALL the places a checker, oracle, linter, test suite or monitor declines to check something — exemption branches, suppression lists, tolerance bands, silent caps like `items[:6]`, early returns on a no-op case, `# noqa` families, timeout budgets — rather than one exemption in isolation. Triggers on "which of our suppressions actually matter", "audit the exemptions in this checker", "how much does this oracle really cover", a green campaign whose coverage nobody has quantified, or a review that turns up a second exemption after the first. The move is to build a registry of sites verified against the source, then measure THREE numbers per site — fire rate, cost per firing (how much comparison surface it removes), and distance from the corpus's demand to the threshold — and to name the population each rate divides by. NOT for designing a single new exemption (that is measured-exemption) and NOT for interpreting one zero (that is zero-rate-needs-a-distance).
---

# Census the exemptions: rate, cost, distance — and name the population

One exemption you can reason about. Six you cannot. A checker accumulates
them one review at a time, each locally justified, and after a few years the
honest answer to "what does this oracle cover?" is nobody knows. The
aggregate verdict — `render ok 677` — is reported identically whether the
check ran on everything or on half of it.

A census fixes that, and it needs three numbers per site because the three
are independent:

```
fire rate   how often the branch is taken          -> is this site live?
cost        how much comparison it removes         -> does taking it matter?
distance    corpus demand vs the threshold         -> could this change?
```

An exemption firing on 60 % of inputs and dropping one field of forty is a
different instrument from one firing on 3 % and dropping everything, and the
fire rate alone renders them the same.

Real instance (round 383 of this program). Eight sites across four
differential oracles. `tail_transparency`'s taint exemption fires on **92 %**
of the corpus and keeps 66 % of the surface; `T-ALL` fires on 2 % and keeps
nothing; `render`'s `names[:6]` fires on 40 % of programs but skips **48 % of
all comparison pairs**; `param_erasure`'s exemption is 6.8 % of the corpus and
**62 %** of the population it can apply to. Not one of those numbers is
derivable from any of the others.

## When to use (triggers)

- Auditing the real coverage of a checker/oracle/suite that has more than one
  exemption, suppression, tolerance or cap.
- A campaign reports "N ok" and nobody can say what fraction of the available
  comparisons that N represents.
- You find a second exemption while reviewing the first — that is the signal
  the population is a set, not an instance.
- A cap written as a literal in a loop bound (`names[:6]`, `head -20`,
  `LIMIT 100`) with no report of what it dropped.
- Someone proposes deleting, widening or tightening one exemption and there is
  no baseline for any of them.
- A tolerance band (`slack`, `epsilon`, `max_retries`) whose margin nobody has
  measured against real demand.

**When NOT to use:** you are designing ONE new exemption — see
`../measured-exemption/SKILL.md`; or you have one zero to interpret — see
`../zero-rate-needs-a-distance/SKILL.md`. This skill is the plural of both.

## Steps

1. **Enumerate the sites by reading the code, and write them down as a
   registry.** One record per branch that declines to compare something:
   an id, the function it lives in, and its `kind` — `predicate` (a boolean
   about the input), `threshold` (a number compared to a constant),
   `silent cap` (a slice or limit in a loop bound), `no-op` (the transform had
   nothing to do). Do not skip the no-op branches: they are how you learn the
   feature is unused.
   *Outcome:* a table whose row count is the answer to "how many are there".

2. **Make the registry self-verifying.** Each record names a LITERAL substring
   of the source and the exact number of times it must occur, and a
   `verify_sites()` raises if any count is off. A registry that silently
   measures a branch that has moved reports numbers that look like results.
   Expect this to fail on its first run — it did in round 383, where a
   4-space `if not a["vals"] and not whole:` turned out to be a substring of
   an 8-space copy in a different oracle.
   *Outcome:* a check that fails loudly on drift instead of quietly.

3. **Record `polarity`.** For most sites, firing SUPPRESSES a comparison. For
   a tolerance band, firing PRODUCES a verdict and the exemption is the
   silent side. Getting this backwards inverts every reading of the table.
   *Outcome:* each row says which direction "fired" points.

4. **Measure by re-using the checker's own predicates, then cross-check
   against the checker's own output.** Calling `provenance_tainted_names` is
   how the measurement tracks a semantic change; but it re-implements the
   BRANCH ORDER, which the anchor check cannot catch. So assert, per input,
   that your row matches what the real checker's `detail` string says.
   *Outcome:* a test that fails when the map and the instrument disagree.

5. **Report the COST, not just the rate — for every site, including the
   threshold ones.** Cost is the fraction of the comparison surface the branch
   removes when taken: pairs skipped over pairs available, fields dropped over
   fields present, 1.0 for a whole-verdict early return. A no-op branch's cost
   is zero and saying so is a result.
   *Outcome:* two independent columns, never one.

6. **For a threshold site, measure the distance — and check whether the demand
   is CENSORED.** Follow `zero-rate-needs-a-distance`. The trap specific to a
   census: an instrument that STOPS at its threshold reports demand equal to
   the threshold, so the ratio is 100 % by construction. That is an artefact
   in true digits. Mark the row censored and run a ladder that moves the
   ceiling until the input stops hitting it.
   *Outcome:* a demand distribution, with the censored rows labelled.

7. **Name the population each rate divides by, and give the narrow one too.**
   A rate over "all inputs" can be an order of magnitude below the rate over
   "inputs the site can possibly apply to". Round 383's param exemption is
   6.8 % of the corpus and 62.2 % of the programs that use the feature it
   keys on. Report both; the second is the one that describes the instrument.
   *Outcome:* every percentage in the write-up has a denominator beside it.

8. **Rank by `rate x cost`, not by either alone, and say what you did not
   measure.** That product is the coverage the checker is actually losing.
   Then list the sites the sweep could not reach and why — a census that
   silently omits a site reads as "there are seven" when there are eight.
   *Outcome:* an ordered list of what to fix, and an explicit gap list.

## Pitfalls

- **Reading a cap off the loop bound instead of counting it live.** `names[:6]`
  looks like 15 pairs; whether the checker really made 15 comparisons is a
  different question. Wrap the comparison function, count calls, and
  discriminate self-checks from cross-checks by object identity — a helper
  may call it again internally and double your count.
- **A measurement that is not a pure function of its input.** Round 383's
  frame-excess probe disagreed with the oracle (8 vs 11) because the
  interpreter caches compiled closures ON the AST, so measuring an
  already-executed tree skips the compilation frames. Any profiler, cache,
  JIT or memo makes "run it twice" a different measurement. Build the input
  fresh per measurement, and let step 4's cross-check tell you when you did
  not.
- **A skipped witness is a zero that looks like a pass.** A constructed input
  written in syntax the system rejects, wrapped in `skip`, reports the same
  green as one that fired. Assert the witness PARSES and FIRES before
  trusting any row it produces.
- **Generalising one measured distance into a prior.** After measuring one
  corpus at 6 % of its ceiling, the next five thresholds feel far away too.
  They are unrelated constants chosen for unrelated reasons — one for a
  stack budget, one for a loop's cost, one for a recursion limit. Read each
  constant's PURPOSE before predicting anything about it.
- **A tolerance whose ceiling lives in another tree.** A slack is sound only
  while it exceeds the largest legitimate value, and that value is often
  fixed by a constant the checker never reads. Assert the RELATION between
  the two, computed live, not either number.
- **Unguarded sweeps.** A census runs the system several times per input, so
  one runaway input costs more here than anywhere else. Per-input wall-clock
  guard, one flushed row per input, and report the guard's skip COUNT — a
  silently dropped input biases the very distribution you are measuring.
- **Pinning the census's rates in a test.** They are true of one checkout on
  one day. Pin the structure — site count, anchors, the slack-vs-ceiling
  relation, the cap's arithmetic — and leave the rates in the round record.

## Verification

```
# the registry, verified against the source
python3 -m harness.swe.exemptmap sites
# rate + cost + distance for every site, resumable and budgeted
python3 -m harness.swe.exemptmap sweep 500 --budget-s 600
python3 -m harness.swe.exemptmap report
# un-censor the threshold sites the sweep clipped
python3 -m harness.swe.exemptmap depth --budget-s 300
# the constructed inputs, through the real instrument
python3 -m harness.swe.exemptmap witnesses
python3 -m harness.swe.exemptmap paircap --bindings 20
```

Expected shape: `sites` prints every site with a `kind`, `metric` and
`polarity` and confirms the anchors; `report` prints a fire % AND a cost % per
site plus a distance for the threshold ones, with censored rows labelled; a
site that never fires still reports a distance; `witnesses` shows each
constructed input firing the site it was built for.

- [ ] every declining branch in the checker has a registry row, no-ops included
- [ ] the registry verifies its anchors against the source and raises on drift
- [ ] each row records polarity, so "fired" is unambiguous
- [ ] the map is cross-checked against the checker's own output per input
- [ ] cost reported for every site, not only the ones that look expensive
- [ ] threshold sites carry a distance, with censored demands labelled and
      re-measured on a ladder
- [ ] every rate is stated with the population it divides by, narrow one too
- [ ] sites ranked by rate x cost, and the unmeasured sites listed
