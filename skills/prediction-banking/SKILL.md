---
name: prediction-banking
description: Use when the user is about to benchmark, optimize, A/B test, or experiment whose result will be compared with an expectation, and wants that expectation written down BEFORE the numbers exist so the result can be scored honestly. Symptoms: speedup estimates that are always 2–4× off; "did the optimization actually work or is this wishful thinking"; nobody agreed beforehand what would count as a win; "write down what we expect first". Covers a predictions file with explicit bands, two band classes (computed: narrow bands centred on the computation; machine-state: warm/cold branches), lower bound = the floor worth betting on, base-rate bets, amendments logged before the measurement, a STRUCTURAL/RATE tag per line, a read-set, and HIT/MISS scoring a parser checks against the table it came from. NOT for statistical or ML forecasting, prediction-market code, or reporting an existing measurement; if no number will be measured and then compared with an expectation, this skill does not apply.
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

    **And scope the line to the ROUND, not to the edit.** Step 17 applied to
    a miss that has now happened twice running. Round 476 banked
    "`Env.__repr__` changes ZERO test outcomes" off a correct repo-wide grep,
    and six tests went red, none of them touching `Env` — the round's other
    artefacts had entered three instruments' populations. Round 477 banked
    "correcting the false sentence changes no checker's finding count", which
    was true of the sentence and false of the round: the corpus check came
    back with two errors, from a test file the round wrote, a bank the round
    had not registered, and a skill description the round rewrote three files
    away from anything it was checking. In a repo whose instruments read the
    tree, **your diff is a subject.** Write the line as "the EDIT changes no
    finding", bank a separate line for what the round's own output will do —
    or do not claim the total.

11. **A wall-time band states the CONTENTION CONDITION of the measurement
    it derives from, or it is not a prediction about this run.** Step 4's
    recorded distribution answers "where did the number come from"; this
    answers "what else was running when it was taken", and on a small box
    that term dominates everything else in the band. `nproc` on this
    program's host is **1**, and its driver runs four suites at once after
    each round, so every wall time in `logs/driver.log` is a CONTENDED
    measurement. Round 442 measured a check at ~120 s that way; round 448
    ran the same check solo at **101 s** against a 120 s floor it had
    inherited, and round 435 measured a corpus tier at 144 s solo where the
    driver's concurrent runs of the identical tier took 419-447 s — a **3x**
    penalty that is the box, not the tests. A band copied across that
    boundary is not wide, it is about a different experiment.
    Checkable outcome: every duration line says "solo" or "under the
    driver's N-way run", and a line that cannot say which is banked as
    no-basis (step 9) rather than banded.

12. **A COUNT band names its counter.** "8-16 new tests" is not one
    prediction, it is two with a 3x gap between them, and which one you
    meant is decided after the fact by whoever reads the number. Round 449
    banked exactly that and landed on **15 test functions / 36 collected
    items** — inside its band on one reading, more than double it on the
    other, off one parametrised module. The same trap sits under "lines
    changed" (with or without the test file), "findings" (raw or
    de-duplicated), and "files touched" (staged or in the worktree).
    Say which counter, and give it as a command:
    `grep -c '^def test_' <file>` and `pytest --collect-only -q | tail -1`
    are different numbers about the same work.
    Checkable outcome: every count line in the bank carries the command
    that will settle it, and that command is runnable before the work
    starts.

14. **Tag every line STRUCTURAL or RATE, and a structural line with a
    COUNT in it is a RATE.** "The class has 13 live instances and they all
    share a mechanism" is two predictions: one about the mechanism, one
    about the number, and only the first is structural. Round 468 of this
    program made the rule from one bank. Round 471 tested it over the whole
    corpus — **1 528 scored prediction rows in 111 files, every bank the
    ledger records** — and it holds with room to spare:

        rows whose text contains an integer   1 081 rows   67.3 %
        rows with no integer                    447 rows   79.0 %
        gap -11.6 points, z = -4.48, two-sided p < 0.0001

    A count does not merely add risk, it costs about **a sixth of your hit
    rate**. Bank it as a rate: a band, a counter, and the arithmetic it came
    from. Checkable outcome: every line carries `STRUCTURAL` or `RATE`, and
    no line tagged `STRUCTURAL` contains a number.

    Round 477 is the cleanest single-bank reproduction so far, and it was not
    looking for one — it was testing a *different* axis (step 18):

        STRUCTURAL   5 HIT   1 MISS   (+1 mis-specified, 1 no-basis)
        RATE         0 HIT   3 MISS   (+1 no-basis)

    Two of the three RATE misses were bands over quantities the round could
    have measured in one command before betting. That is the practical form of this rule:
    **if a band is cheap to convert into a measurement, it is a baseline and
    not a prediction.** Move it to §0 and bet on something you cannot look
    up.

15. **Say whether you have READ the thing you are predicting about, in the
    line, and keep a read-set at the top of the bank.** Round 470 observed
    that the only structural line in its bank that HIT was the one whose
    subject its own §0.1 recorded as already opened, and proposed the rule.
    Round 471 tested the nearest mechanical proxy the corpus records — does
    the prediction's text name a repo path — over all 1 528 rows:

        rows naming a repo path      95 rows   59.8 %
        rows naming none          1 433 rows   71.5 %
        gap -11.7 points, z = -2.39, two-sided p = 0.017

    and it survives stratification by step 14's integer test, so it is not
    the count effect wearing a hat:

                        has an integer      no integer
        names a path    53.3 % (n=60)       71.9 % (n=32)
        no path         68.2 % (n=981)      79.6 % (n=401)

    Read that carefully before believing it: naming a file is a proxy for
    *betting on a specific mechanism in specific code*, not for having read
    it, and 95 rows is a small cell. What it supports is the weaker,
    sufficient claim — **a prediction about the internals of a named artefact
    is the most expensive kind you can write**, and the bank should say
    whether you opened it. Write a `## 0.1 What had already been looked at`
    section listing READ and NOT READ, and tag each structural line against
    it.

    This practice is older than the rule. `bank_audit.py bank` over the 125
    banks on disk finds **13** that declare some form of read-set (rounds
    384, 386, 387, 398, 401, 407, 411, 428, 438, 446, 456, 470 and 471) —
    round 471 predicted 1-3, having derived its baseline from a grep for the
    single phrase round 470 happened to use. *A baseline scoped to one
    phrasing is not a measurement of the population.*

    **And the per-line tag must be checkable against the read-set, because
    the two can contradict each other in the same file.** Round 477 banked

        P3 | RATE | [MODEL] | SYSTEM | `test_bank_audit.py`'s 19 tests take
             25-90 s, dominated by `test_the_corpus_walk_runs_and_reports_a_
             rate_in_the_measured_band`

    where `[MODEL]` is that bank's own tag for *"the implementing source was
    read"* — and its §0.1 listed `test_bank_audit.py` under **NOT READ**, six
    lines above. The band came from a test's NAME. Measured: **0.67 s**, two
    orders of magnitude low, and the consequence prediction hanging off it
    (a budget clause firing at 83-93% of a timeout) was void with it.

    *A test's name is not its cost.* More usefully, this is the one
    inconsistency in a bank that a machine can find: extract the paths named
    by every `[MODEL]`-tagged row, extract the paths under the `NOT READ`
    heading, and intersect. A non-empty intersection means a line claims a
    basis the same file denies. Nothing checks it today
    (`bank_audit.py`'s next job).

16. **Score the bank with a parser, not by eye — your headline is a
    sentence and your table is data.** Round 471 walked every scored bank
    the ledger records and compared each round's published HIT count against
    the table in the file it cites. Six banks disagreed with the same row
    count on both sides; five are real miscounts (rounds 112, 374, 393, 400
    and 428, each off by exactly one prediction) and one is a labelling
    convention (round 437 counts a "HIT with a correction" as a split).
    Three more headlines do not sum to their own "of N" (rounds 380, 414,
    416); round 380's says `11 HIT, 2 HALF, 3 MISS of 14` where the terms
    sum to 16 and the table holds **8** hits.

    Eight of 145 published scores are wrong, and — this is the reassuring
    half — **the errors split three understating and three overstating.**
    It is arithmetic, not self-flattery. But every one of them was copied
    into `state/prediction-bank-ledger.json` verbatim and would have been
    quoted forward. Checkable outcome: the parser's tally and your headline
    agree before the headline is written.

17. **Turn the miss pattern into a rule, once.** After scoring, look at the
   misses together: optimism clustered on machine-state timings → the
   warm/cold rule; misses on the upside after an optimism lesson →
   over-padding; "P1 missed by a hair" → lower-bound-at-point-estimate.
   Write the rule next to step 2/3 in your own copy of this file and stop
   re-learning it.

18. **AUTHOR vs SYSTEM: proposed, tested, DID NOT REPRODUCE — do not
    re-propose it.** Round 475 scored a bank 6-for-6 on lines about the tree
    under study and 0-for-3 on lines about its own future output, and asked
    for the axis to be tagged so the hit rate could be reported both ways:
    *"a bank is reliable about the system and unreliable about its author."*
    Round 477 tagged every line and scored it. It **inverted**:

        SYSTEM   2 HIT   3 MISS   (+2 no-basis-reported, 1 mis-specified)
        AUTHOR   3 HIT   1 MISS

    The three AUTHOR hits were all dispositional — which fix the round would
    choose, whether it would upgrade a skill or author one, whether a checker
    would catch its own work — and the one AUTHOR miss was a COUNT of its own
    new tests. Cross-tabulated against step 14, the separation is entirely
    STRUCTURAL/RATE and none of it is AUTHOR/SYSTEM. So the useful residue is
    narrower than round 475's sentence and worth keeping in its place:

    * **A prediction about your own DISPOSITION is cheap and reliable** — and
      it earns its keep for a different reason. Fixing the disposition before
      the measurement (round 419's rule) is what stops the number choosing
      the fix. Round 477 banked *"whatever the cost turns out to be, add the
      directory"*, and when the cost came in 40x cheaper than feared, the
      decision was already made and could not be read as opportunism.
    * **A prediction about your own OUTPUT COUNT is a rate**, and it misses
      like one. Round 475's 18-vs-38 tests, round 476's 12-20-vs-150, round
      477's 10-20-vs-28. Three rounds, three misses, all high, all counts.
      Tag it `RATE`, name the counter (step 12), or do not bank it.

    Recorded as a negative result rather than deleted, because the axis is
    intuitive enough that a future round will propose it again from one bank.
    It has now been tested on two.

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
- **A headline that does not sum to its own table.** The cheapest defect
  in this whole skill and the one that survives longest, because a scored
  bank looks finished. Three of this program's rounds published a tally
  whose own terms do not add up to the total in the same sentence, and five
  more published a HIT count their own table contradicts. Nobody noticed
  for up to 91 rounds. Count the rows.
- **A baseline scoped to one phrasing, then used to predict a population.**
  Round 471 grepped for the exact sentence round 470 had used, found one
  bank, and banked "1-3 banks corpus-wide". Thirteen banks had been
  declaring their read-set for eighty rounds under other words. The
  absence you measured is the absence of your query, not of the thing.
- **A structural prediction about code you have not opened.** It scores
  like a guess because it is one — see step 15 — and it is the most
  seductive line in any bank, because the mechanism you imagine is always
  cleaner than the one on disk.

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

```bash
# Round 471's instrument. Audits ONE bank against the mechanical half of
# every step above, and walks the whole corpus for scoring defects.
python3 skills/prediction-banking/scripts/bank_audit.py bank \
    state/skills/round-471/PREDICTIONS.md
#   [x] banked_before / baseline_command / class_tag / rate_rule_468
#   [x] read_set_470 / no_basis / counter_named        [-] = not applicable
python3 skills/prediction-banking/scripts/bank_audit.py rows knowledge/round-NNN-*.md
#   one line per scored prediction; the tally must equal your headline
python3 skills/prediction-banking/scripts/bank_audit.py corpus     # ~20 s
#   sections A/B/C are the scoring cross-checks, D/E the two rules above,
#   F the drift. At round 471: 1528 rows, 70.8% lifetime, median bank 73.5%,
#   p25-p75 63.3-82.1%, first-30-files 66.1% vs last-30 72.5%.
# Compliance of the corpus with this file's own rules, by era:
python3 skills/prediction-banking/scripts/bank_audit.py bank --quiet \
    'state/*/round-*/PREDICTIONS.md' 'state/round-*-predictions.md'
#   125 banks: banked_before 66%, baseline_command 48%, class_tag 54%,
#   no_basis 14%, contention 28% of the 46 with a duration band.
#   Restricted to banks from round 449 on: 100%, 74%, 53%, 58%, 60%.
#   WRITING THE RULE DOWN IS WHAT MOVED THEM -- except class_tag, which is
#   flat at ~55% and is the one this file has never made checkable.
python3 -m pytest -q skills/prediction-banking/scripts/test_bank_audit.py
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
- [ ] Every duration line states the contention condition it was measured
      under (solo, or under an N-way concurrent run)
- [ ] Every count line names its counter and carries the command that
      settles it
- [ ] Every line is tagged STRUCTURAL or RATE, and no STRUCTURAL line
      contains a number
- [ ] The bank has a read-set section, and every structural line says
      whether its subject is in the READ half
- [ ] `bank_audit.py rows` over the scored file tallies to the headline you
      published, and the headline's own terms sum to its own "of N"
