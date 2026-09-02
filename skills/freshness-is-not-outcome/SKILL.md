---
name: freshness-is-not-outcome
description: Use when an audit, dashboard, coverage report or status registry summarises a check as probed / tested / scanned / verified / up-to-date — a field that records that a measurement HAPPENED and is read as if it recorded what the measurement SAID. Symptoms: a headline count of "N covered" that nobody can trace to a pass; a status computed from the most recent run when re-runs are triggered by failures; a per-item status derived from a run that touched only some of that item's inputs; a repeat of one input counted as breadth. Covers separating did-we-look from what-did-we-see, counting distinct inputs rather than results, naming retry bias in a newest-wins rule, and pricing the fix before choosing error or warning.
---

# "Probed" answers did we look, not what we saw

A status field is cheap to add while you are building the instrument that
fills it, and the natural thing to record is *provenance of the
measurement*: which run, when, against which version. That field then gets
counted — "35 of 36 probed", "412 files scanned", "every service checked
this week" — and the count is read as a **quality** number by everyone
including its author, because there is no other number in the report.

The gap is not that the field lies. It is true and it answers a different
question from the one its readers ask.

## Trigger conditions

Any one of these:

1. A registry, audit or dashboard reports a per-item status drawn from a
   vocabulary of *recency* — `probed`, `STALE`, `never`, `checked`,
   `scanned`, `up-to-date`, `unverified` — and a summary line counts the
   good ones.
2. The per-item status is computed from **the most recent run that touched
   that item**, and re-runs in this system are triggered by failures
   (a re-probe, a retry, a "let me just re-run the flaky one").
3. The run the status came from covered only PART of the item's inputs, and
   the report shows the part count in a column nobody reads.
4. Repeats are possible: one input measured n times can inflate a count of
   "measurements" that is being read as a count of "inputs covered".
5. Someone has already written down the gap in prose — a note, a comment, a
   next-step — and no code reads it. That note is the specification.

Not this skill when the outcome genuinely is unavailable offline (the run
kept no per-item result). Then the job is to make the runner record one;
this skill assumes the outcomes are already on disk and unread.

## Why the outcome half is usually free

The instrument almost always already stores what it saw — a per-case
`expect`/`fired` pair, a per-file pass/fail, an exit code — because it
needed it to print its own report. The reason nothing reads it is that the
status field was added for a *different* question (has this gone stale?)
and answered it correctly. So the cost of closing the gap is a few lines
over data you already committed, and the reason it stayed open for years is
that the field was never wrong.

## Steps

1. **Find the status vocabulary.** Grep the audit for the strings it puts
   in its status column. If every value is about recency or provenance and
   none is about a result, the gap is total.
2. **Confirm nothing reads the outcome.** Grep the audit path for the field
   that holds the result (`fired`, `passed`, `rc`, `verdict`). Zero hits in
   the code — fixture-only hits in the tests — is the finding. Record it as
   a finding; it is stronger evidence than the numbers you are about to
   compute.
3. **Compute the two axes separately, over DISTINCT inputs.**
   - `covered` = distinct inputs of this item that the chosen run touched
   - `recalled` = of those, the ones that passed on *every* repeat
   - `flaky` = of those, the ones that passed on some repeats and not others

   Counting results instead of distinct inputs is the specific error that
   hides the worst cases: one input repeated four times reports
   `probes=4` against `inputs=3` and reads as over-covered.
4. **Ask why the chosen run is the chosen run.** If the rule is "newest run
   that touched this item", list the runs. A run whose name contains
   `reprobe`, `retry`, `-after`, `rerun` or `fix` exists *because* the
   previous one failed, and a newest-wins rule hands the item its retry.
   That is survivorship bias, not a stale number, and it is the part worth
   writing down: **the most recent measurement is the one that was run
   because the previous one failed.**
5. **Price the fix before choosing a severity.** If closing the debt costs
   money or a long run, an ERROR is a check that can only go green by a
   spend, and a check that can never go green gets uninstalled. Emit
   WARNINGs against an owned baseline instead, and mirror whatever the
   existing baseline in this repo already does so there is one idiom.
6. **Give the baseline a content pin and a rot check.** An entry records
   `owner`, `why`, and the exact RUN it was adjudicated against. Make it an
   ERROR when the item now measures clean (the debt is paid and the entry
   is a mute button), and when the pinned run is no longer the newest one
   (someone re-measured and did not re-adjudicate).
7. **Do not pre-fill the baseline with everything the new check finds.** An
   entry means *decided and carried*. Acknowledging the whole first run
   converts the check into the silence it was built to break. Acknowledge
   only what a round actually adjudicated; leave the rest as live warnings
   with an owner named in the file.
8. **Change the headline.** The summary line is the one thing downstream
   readers quote. Add the outcome count beside the freshness count, in the
   same sentence, so the weaker number cannot be quoted alone.
9. **Pin invariants, not counts.** Assert `0 <= recalled <= covered <=
   inputs` over the live data. Do NOT assert "N items are weak": paying the
   debt is the good outcome and it must not turn a test red.

## Pitfalls

- **Fixing the status vocabulary instead of adding a field.** Folding the
  outcome into the existing status (`probed-but-failing`) breaks every
  consumer that switches on it and destroys the freshness answer, which was
  correct. Add fields; leave the old one alone.
- **Widening a cited exit code.** If a checklist or doc cites the audit's
  exit code for the freshness question, changing it silently re-scopes a
  contract. Carry the new codes in the checker that runs every build, and
  say in the docstring why the exit code was left alone.
- **Inferring the answer from prose.** If the registry has a free-text
  field being used for two meanings, add a second FIELD. A regex that
  decides which meaning a sentence has is the classifier you are replacing.
- **Three warnings for one item.** Suppress the outcome codes for items the
  freshness code already flags (`never`, `STALE`). A warning list nobody
  finishes reading is not a signal.
- **Trusting your own test fixtures' schema.** A fixture that writes
  `{"case": ...}` where the real writer writes `{"id": ...}` passes forever
  while no reader looks at the field, and produces zeroes the moment one
  does. Re-derive the key from the code that WRITES the artifact.
- **Predicting the breakage before measuring it.** The outcome numbers are
  usually much better than the argument for measuring them implies; the
  finding is the *shape*, not the size. Bank the prediction, then measure.
- **Asserting the absence of a ROW when you mean the absence of EVIDENCE.**
  The same confusion, written into a test instead of a dashboard. A round
  pinned "this unit has never produced a ledger row" as `unit not in seen`,
  meaning "it has never been evidence". Two rounds later a scheduled slice
  attempted the unit, it timed out at 3000 s, and the runner appended a row
  with `outcome: "timeout"` — membership arrived, evidence did not, and the
  assertion went red while everything it was written to protect was still
  true. A timeout row is neither a pass nor a fail; the state machine
  reading it already classified it as inconclusive and was right. Write the
  predicate over the OUTCOME field (`outcome in ("passed", "failed")`), and
  pin the row's actual value positively as well, so that the day the unit
  really finishes the test breaks on purpose rather than by accident.

## Verification

Run these three; the first is the finding, the other two are the fix.

```sh
# 1. step 2 of the method: show that nothing reads the outcome. Run against
#    the PRE-FIX revision, because the whole point is that the fix adds the
#    first reader -- on the current tree the same grep now matches 4 times.
git show fab139b:skills/skill-authoring/scripts/case_coverage.py \
  | grep -c "fired"
#   -> 0   (the checker never looked; the only hit anywhere in the file's
#           tests was fixture setup, and that fixture had the key wrong)

# 2. the two axes, separately, over distinct inputs
python3 skills/skill-authoring/scripts/case_coverage.py | tail -1
#   -> "37 skill(s), 146 case(s) (27 negative); 35 probed under the
#       description on disk, 26 of those on every positive case with full
#       recall; 0 error(s), 6 warning(s)"
#   The two numbers differ by NINE. Before this, only the 35 was printed.
#   They are re-derived per round by skills/run_checks_fast.sh, so this
#   line is not a number nobody re-executes.

# 3. the codes, the baseline, its rot check and the live invariants
python3 -m pytest skills/skill-authoring/scripts/test_case_coverage.py -q
#   -> 35 passed  (P006 subset, P007 recall, repeats-are-not-coverage,
#      flaky, acknowledged-is-silent, debt-paid is P008, expired pin is
#      P008, unowned is P008, deleted skill is P008, live invariants,
#      baseline schema)
```
