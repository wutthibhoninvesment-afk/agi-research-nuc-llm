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

   **Every BASELINE in the bank is re-derived at HEAD, with the command that
   produced it printed beside it.** A baseline is not context; it is the
   thing your band is measured against, so a stale one moves every verdict
   under it and does so invisibly. The failure mode is not laziness — it is
   that the previous round's number is sitting in a status file, correct
   *when written*, in a sentence that reads like a fact. Round 433 of this
   program made the rule; round 434 followed it and the very first baseline
   it re-derived was already stale (`broken 2, holds 8 …` in the status
   file; `broken 2, holds 9 …` at HEAD), because a fix had landed in the
   same round that printed the pre-fix number. The command is the whole
   control: a band derived from a number nobody can re-run is a band nobody
   can audit. Checkable outcome: the bank has a baseline table and every row
   in it carries a runnable command, not a citation.

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

4. **A wall-clock band comes from a RECORDED DISTRIBUTION, or it is not
   banked at all.** This is the one class where "name your source" was
   tried and failed. Three rounds of this program in seven missed a
   duration re-quoted out of an earlier round's PROSE — the last by 40x
   (30-45 minutes predicted, 54 seconds measured) — and that bank had named
   its source and flagged itself as its own weakest line. Naming the source
   is not the control; refusing the prediction is.
   - A recorded distribution is a machine-written log of the SAME quantity:
     CI job durations, a benchmark ledger, `/usr/bin/time` output, a
     run-record JSON. Prose in a report is not one, even your own, even
     from last week. A sentence records one run, and duration is the
     widest-spread quantity you will ever bet on.
   - Quote three numbers from it, never one: **median, p25-p75, and whether
     the recent window has moved.** If you cannot get all three you have a
     sample, not a distribution, and the honest bank line is
     "unpredicted — no recorded prior".
   - The prior is usually already on disk and unread. Here it is
     `logs/round-NNN.json`, the driver's raw stream, whose terminal
     `result` object carries `duration_ms`: **232 of 276 round logs have
     one and nothing had ever read them** (round 429). Median 20.9 min,
     p25-p75 11.4-34.3 — a 3x spread — while the last 20 rounds sit at a
     35.5 min median. No prose sentence can carry that, which is precisely
     why re-quoting one keeps missing by multiples.
   Checkable outcome: every duration line in the bank cites a file a
   MACHINE wrote, and states a spread rather than a point.

5. **Grep before betting on novelty.** Before predicting "no prior art in
   the tree" or "this is the first X", search (`grep -rl`, `git log -S`).
   Two rounds of a research program under-predicted prior art that a
   one-line grep would have found.

6. **Add base-rate bets on your own process.** "At least one of my new
   tests is wrong on first run", "the suite will be red in a component I
   didn't touch", "cost ≤ $X". These are the cheapest predictions to score
   and they track discipline drift over time.

7. **Freeze the file, then measure.** Write
   `state/round-NNN-predictions.md` (or `predictions.md` next to the
   benchmark) with a timestamp and "banked BEFORE …" in the first line.
   Anything learned after that goes under `## Amendments` with its own
   timestamp and the phrase "before the relevant measurement" — an
   amendment written after the number is a rationalisation, not a
   prediction.

8. **Score every line as HIT / MISS with the direction.** MISS (high) /
   MISS (low), and for each miss one sentence naming the mechanism ("cold
   start bit a timing band", "anchored on the optimistic edge of the smoke
   bound", "lower bound was the point estimate"). Vacuous lines ("precision
   ≥ 0.5" when zero claims were made) are *unscorable*, not hits.
   Checkable outcome: a ledger line `P k/n, A k/n` (predictions,
   amendments) in the report.

9. **A quantity you have NO BASIS for is not a prediction target — say so
   and report it.** "Bank predictions before measuring" is not "guess at
   everything the run will print". A file nobody has opened, a corpus
   nobody has counted, a box that has been down all week: writing five
   numbers about it produces five misses that share one cause and teach
   nothing, and it makes the bank's HIT rate a measure of how much you
   declined to bet rather than of how well you understand the system. The
   honest line is *"I have no basis here and will report what it holds"* —
   which is still a commitment (you must report it), can still be broken
   (by quietly not reporting), and scores as **no-basis-reported**. It is
   also the only line that gets *better* with honesty rather than worse.

   **And a band may not be laid over a SUM one of whose terms you have
   just declared unpredictable.** Round 447 of this program banded "28 →
   70-110 prose fields" four lines above a no-basis line saying it could
   not predict how many of those fields lived at depth — and depth was the
   dominant term. The answer was 663. Decompose the sum and band only the
   terms you can reason about (the top-level term in that bank was fine:
   reasoned to "two dense files plus some", came in at 24), or drop the
   band and report the total. Checkable outcome: no banded quantity
   contains a term another line calls unpredictable.

10. **Predict what the INSTRUMENT will report, not what the world
    contains.** When the run's output comes from something you are about
    to build or change, the world and the measurement are two different
    predictions and only the second one is scored. Round 447 predicted "a
    new rule will fire on ZERO live fields" as a claim about the corpus —
    and was RIGHT about the corpus: after the rule was debugged its live
    yield was 0. It scored a MISS because the rule as first written fired
    twice, both times wrongly. A new instrument's first output is at least
    as likely to be about the instrument as about the subject. If you mean
    the world, bank both lines: "the corpus contains no true instance"
    AND "the first run of the new rule reports N false ones".

11. **Turn the miss pattern into a rule, once.** After scoring, look at the
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
- **A duration re-quoted from prose.** The failure step 4 bans outright.
  It survives every softer control — the three misses that forced the ban
  had each NAMED their source, and one had labelled itself the weakest line
  in its own bank. The tell is a band whose two endpoints are the two
  numbers in somebody's sentence.
- **A baseline quoted from the status file.** The sibling of the
  re-quoted duration, and more dangerous because it is invisible: a
  duration miss shows up as a miss, while a stale baseline silently
  re-centres every band above it and the bank still scores well. Sweep
  baselines by what they DERIVE FROM — a corpus rate drifts every round, a
  constant does not — and re-run the corpus ones.
- **Bands so loose they can't miss** ("wall time 1–60 min") prove
  nothing; if a computable effect gets a 3× band, the computation was
  skipped.

## Verification
```bash
head -3 state/round-NNN-predictions.md     # first line contains "banked BEFORE"
# every baseline row carries a runnable command, not a citation (round 433):
# count the table rows, then the ones holding a command
grep -c '^| ' state/round-NNN-predictions.md
grep '^| ' state/round-NNN-predictions.md | grep -c 'python3\|bash\|grep'
grep -c "computed\|machine-state" state/round-NNN-predictions.md   # ≥ number of quantities
# step 9: a bank that declines to bet must SAY it declines, and the scoring
# must carry the verdict back. Both halves, or the decline is just a silence:
grep -c "no basis\|no-basis" state/round-NNN-predictions.md
grep -c "no-basis-reported" knowledge/round-NNN-*.md
# At round 447 these printed 3 and 2: one no-basis line banked (P10), and the
# verdict `no-basis-reported` carried back into both the round file's headline
# and its scoring table. Checked before being written down -- the first draft
# of this comment said "3 and 3".
grep -n "HIT\|MISS\|unscorable" knowledge/round-NNN-*.md            # one verdict per prediction line
python3 -c "
import glob, json
d = []
for p in glob.glob('logs/round-*.json'):
    r = [json.loads(l) for l in open(p, errors='replace') if '\"duration_ms\"' in l]
    r = [o for o in r if o.get('type') == 'result']
    if r: d.append(r[-1]['duration_ms'] / 60000.0)
d.sort(); n = len(d)
print('%d of %d rounds recorded; median %.1f min; p25-p75 %.1f-%.1f min'
      % (n, len(glob.glob('logs/round-*.json')), d[n//2], d[n//4], d[3*n//4]))"
# expected: the step-4 prior, re-derived rather than re-quoted. At round 429
# it printed `232 of 276 rounds recorded; median 20.9 min; p25-p75
# 11.4-34.3 min`. The numbers WILL drift; that is the point of the command.
```
- [ ] Every quantity has a class tag and a band derived from a number in the file
- [ ] Every baseline row carries the command that produced it, run this session
- [ ] Amendments are timestamped and precede their measurement
- [ ] Ledger line `P k/n` present; each MISS has a direction and a mechanism
- [ ] One rule added or confirmed from this round's miss pattern
- [ ] Every quantity with no basis says so and promises a report, instead of
      carrying a number
- [ ] No banded quantity is a sum containing a term another line calls
      unpredictable
- [ ] Where a new or changed instrument produces the number, the bank says
      whether it is predicting the instrument or the world
- [ ] No duration band without a machine-written prior behind it
