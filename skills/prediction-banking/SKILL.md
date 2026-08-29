---
name: prediction-banking
description: Use when the user is about to benchmark, optimize, A/B test, or experiment whose result will be compared with an expectation, and wants that expectation written down BEFORE the numbers exist so the result can be scored honestly. Symptoms: speedup estimates that are always 2–4× off; "did the optimization actually work or is this wishful thinking"; nobody agreed beforehand what would count as a win; "how confident should we be in this number"; "write down what we expect first". Covers a predictions file with explicit bands, two band classes (computed quantities: narrow bands centred on the computation; machine-state quantities: warm/cold branches, wide bands), lower bound = the floor worth betting on, base-rate bets, amendments logged before the measurement, and HIT/MISS scoring that names each miss's mechanism. NOT for statistical or ML forecasting, prediction-market code, or reporting an existing measurement; if no number will be measured and then compared with an expectation, this skill does not apply.
---

# Banking predictions before measuring

## When to use (triggers)
- A benchmark, profile, load test, A/B run, mutation score, trigger-rate
  probe or any measurement is about to be taken and someone will later say
  "it worked" or "it didn't".
- The user has noticed a pattern of optimistic claims ("2× → 1.3×",
  "tests will be green" → three red) and wants a process fix, not a pep talk.
- An autonomous run reports numbers nobody anchored in advance, so the
  report can't be wrong.

**When NOT to use:** forecasting as the *product* (time-series models,
demand forecasts, prediction markets); a measurement that already exists
and only needs reporting; one-off numbers nobody will act on.

## Steps

1. **List the quantities before touching code.** One line per number the
   run will produce: speedup ratio, wall time, kill rate, cost, count of
   failing tests. Checkable outcome: every number in the eventual report
   has a line in the predictions file, or is marked "unpredicted".

2. **Classify each quantity into one of two band classes.**
   - *Computed-by-you* (an effect you can derive: frames per call, bytes
     per node, tokens in a prompt, mutants per operator): a NARROW band
     centred on the computation. If you can't compute it, do the
     computation first — the band is the check on the arithmetic.
   - *Machine-state* (anything with a cold start, a cache, a network, a
     shared CPU, a stochastic model): state the precondition explicitly
     and predict BOTH branches ("warm: 45–60 s; first request after a
     restart: 90–150 s"). A single band for a two-state quantity is a
     coin flip dressed as a prediction.
   Checkable outcome: each line carries its class tag.

   **Pin the scope and the unit before the band.** If a quantity has both an
   OCCURRENCE form and a DISTINCT form, predict both or name which one the
   band is on. Round 345 predicted "60-85% of the 91 wikilink occurrences
   dangle" by reasoning about distinct items, and missed by an order of
   magnitude (5%): the 91 occurrences were only 8 distinct slugs cited ~11
   times each. Its next line then said "8-20 distinct dangling slugs" without
   naming a file set, and scores HIT at 11 corpus-wide but MISS at 3 for the
   subtree the previous line was explicitly about. **A band whose unit or
   scope is unpinned is half a prediction** — and it is unfalsifiable in the
   direction that flatters you, because you get to pick the reading
   afterwards.

3. **Set the lower bound at the floor you would bet on, not at the point
   estimate.** Write "≥1.4×" only if a 1.39× result would genuinely
   surprise you. Price an optimization off the *tottime* of what it
   removes (the profiler's self time), never the cumulative time — a
   change that removes 15 % of self time cannot deliver 40 %.
   Checkable outcome: for every ratio, the file shows the number it was
   derived from.

4. **Grep before betting on novelty.** Before predicting "no prior art in
   the tree" or "this is the first X", search (`grep -rl`, `git log -S`).
   Two rounds of a research program under-predicted prior art that a
   one-line grep would have found.

5. **Add base-rate bets on your own process.** "At least one of my new
   tests is wrong on first run", "the suite will be red in a component I
   didn't touch", "cost ≤ $X". These are the cheapest predictions to score
   and they track discipline drift over time.

6. **Freeze the file, then measure.** Write
   `state/round-NNN-predictions.md` (or `predictions.md` next to the
   benchmark) with a timestamp and "banked BEFORE …" in the first line.
   Anything learned after that goes under `## Amendments` with its own
   timestamp and the phrase "before the relevant measurement" — an
   amendment written after the number is a rationalisation, not a
   prediction.

7. **Score every line as HIT / MISS with the direction.** MISS (high) /
   MISS (low), and for each miss one sentence naming the mechanism ("cold
   start bit a timing band", "anchored on the optimistic edge of the smoke
   bound", "lower bound was the point estimate"). Vacuous lines ("precision
   ≥ 0.5" when zero claims were made) are *unscorable*, not hits.
   Checkable outcome: a ledger line `P k/n, A k/n` (predictions,
   amendments) in the report.

8. **Turn the miss pattern into a rule, once.** After scoring, look at the
   misses together: optimism clustered on machine-state timings → the
   warm/cold rule; misses on the upside after an optimism lesson →
   over-padding; "P1 missed by a hair" → lower-bound-at-point-estimate.
   Write the rule next to step 2/3 in your own copy of this file and stop
   re-learning it.

## Pitfalls
- **The amendment that anchors on the optimistic edge.** A smoke test
  gives a bound; the amendment narrows the band to its good end; the real
  run lands at the bad end. Amend toward the *centre* of new evidence, not
  its flattering edge.
- **Over-padding after an optimism lesson.** Two rounds after learning
  "you're optimistic on prefill", every band was padded and three
  computed quantities missed LOW. The lesson was class-specific: pad
  machine-state bands, not computed ones.
- **A timing band without a warm/cold precondition** is bitten by the
  first request after a restart, a cold disk cache, or a GC pause, every
  time. Predict both branches or record which one you're in.
- **Extrapolating on the wrong model.** A prefill projection extrapolated
  in seconds-per-token from a different context size missed by 2×;
  compute deltas from the real rendering/size, then convert.
- **The measurement that costs what it measures.** Counting a 26k-token
  prompt by sending it to the engine costs the 86-minute prefill you were
  trying to predict; build the count locally (a tokenizer, a formula)
  when the measurement itself is expensive.
- **Predictions never scored because the session died.** Score at the
  START of the next session, from whatever artifacts exist, before
  planning new work; an unscored prediction file is worth nothing.
- **A ratio over occurrences, reasoned from distinct items.** The clustering
  is the whole quantity: citations, log lines and error messages repeat a few
  values many times, so an occurrence rate is dominated by frequency and a
  distinct rate by the long tail. Reasoning about one and betting on the
  other is a category error, not a band that needs widening.
- **Bands so loose they can't miss** ("wall time 1–60 min") prove
  nothing; if a computable effect gets a 3× band, the computation was
  skipped.

## Verification
```bash
head -3 state/round-NNN-predictions.md     # first line contains "banked BEFORE"
grep -c "computed\|machine-state" state/round-NNN-predictions.md   # ≥ number of quantities
grep -n "HIT\|MISS\|unscorable" knowledge/round-NNN-*.md            # one verdict per prediction line
```
- [ ] Every quantity has a class tag and a band derived from a number in the file
- [ ] Amendments are timestamped and precede their measurement
- [ ] Ledger line `P k/n` present; each MISS has a direction and a mechanism
- [ ] One rule added or confirmed from this round's miss pattern
