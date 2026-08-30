---
name: rerun-before-you-record
description: Use when a DURABLE record is about to be written from ONE execution of something nondeterministic — a baseline or suppression entry, a "known-bad"/"flaky"/"unused" label, a decision to delete, disable or rewrite an artifact, a published rate, or a regression verdict. Symptoms: "it fired 0 of 3, the description must be wrong", "the eval says this prompt is worse", "that test failed once, mark it flaky", "the newest report says X so X is current", a benchmark quoted from a single run, or an A/B call at small n. Covers asking whether the instrument is deterministic at all, re-running the IDENTICAL configuration before recording, adding an isolation or ablation arm to localise a swing, reporting both draws and the pooled n instead of the latest one, and making the stored record carry its own replication count. NOT for a deterministic checker (re-running proves nothing), and NOT for deciding whether a difference MATTERS once it replicates.
---

# One run is a draw. A record made from it is a guess with a filename.

A nondeterministic instrument answers a slightly different question every
time you ask it: an LLM-based evaluator, a sampled benchmark, a load test, a
scheduler-sensitive integration test, an A/B at small n. Reading one of its
answers is fine. **Writing one of its answers into a place that outlives the
run** — a baseline file, a suppression list, a status field, a design doc, a
label like `known-bad` or `flaky` — converts a draw into a fact, and nothing
downstream can tell the difference afterwards.

The failure is not that the run was wrong. The run was real. The failure is
that the record does not carry *how many times you asked*, so the next reader
inherits a coin flip as a measurement.

## The instance this was written from (round 381 of this program)

A skill-trigger evaluator runs `claude -p` against a staged skill corpus and
reports which skills fired. `lazy-fill-ceiling` was probed across four
independent runs of a **byte-identical** configuration — same 41-skill
catalog (verified: the `available` list in both reports is the same 89
names), same cases, same model, same `--protocol strict`:

| run | probes | fired |
|---|---|---|
| `round-381-batch.json` | 12 | **0** |
| `round-381-lfc-armD2.json` | 12 | 12 |
| `round-381-armH.json` | 4 | 4 |
| `round-381-armJ.json` | 12 | 11 |

The first run alone would have supported — and nearly did support — a
rewrite of a description that is in fact working. Two runs of the same
29-case configuration disagreed at majority level on **11 of 29 cases**.

It had already happened twice. `state/known-weak-probes.json` carried
`measured-budget-sizing` and `obligation-ledger` as **KNOWN-BAD
DESCRIPTIONS**, each adjudicated from a 0-of-3 draw after a description edit
did not move it. Re-measured at the same corpus: **9/9** and **6/9**. One of
those entries had been quoted, carried and re-cited for twelve rounds.

## When this triggers

- You are about to write a verdict into a file that other runs will read:
  a baseline, an allowlist, a `known-*.json`, a status field, a README table.
- You are about to **edit an artifact because one run looked bad** — a
  prompt, a description, a threshold, a heuristic.
- You are about to **delete or disable** something because it "never fires"
  or "always fails".
- Two reports disagree and you are reaching for the newest one.
- Someone quotes a benchmark, win-rate or eval score with no `n`.

## Steps

1. **Ask the determinism question out loud, before anything else.** Same
   input, same output, byte for byte? If yes, stop — re-running proves
   nothing and this skill does not apply. If you cannot answer, the answer
   is no.
2. **Re-run the identical configuration.** Not a variant, not a subset, not
   "the same thing but smaller". The single most common way this step gets
   skipped is by improving the run while repeating it, which produces a
   second draw of a *different* instrument.
3. **Compare verdicts, not averages.** Record what each run said. If two
   runs agree, say "2 of 2 runs". If they disagree, that IS the finding,
   and it outranks whatever either run said.
4. **When a swing is large, add an isolation or ablation arm** before
   theorising about its cause. In the instance above the natural theory —
   "the corpus got too crowded, siblings are stealing the fire" — was
   tested with four arms (1, 3, 20, 22 and 41 staged skills) and was
   **wrong**: the skill won 12/12 head-to-head against the very siblings
   that had displaced it. The crowd was innocent; the run was the variable.
   Two plausible mechanisms were falsified in about four minutes each.
5. **Never edit the artifact after the first bad draw.** An edit changes
   the thing being measured, so a second bad draw can no longer tell you
   whether the original was bad — you have spent your control. Re-run
   first, edit second. (Programs that already have a *stop* rule — "no
   third edit" — usually have no *start* rule; this is it.)
6. **Make the record carry its own n.** The stored verdict names every
   report it rests on, not the newest. A record that cannot say how many
   draws it saw will be re-quoted as though it saw enough.
7. **Give the checker the same question.** If a file holds these verdicts,
   add a check that flags an entry resting on a single report — otherwise
   step 6 is a convention, and conventions decay silently.

## Pitfalls

- **"The newest report wins."** A rich run (n=3 per case) can be overridden
  by a thin one (n=1) simply for being newer. That was a live defect in this
  program's own `audit_skills`, which reads every outcome off *the newest
  report holding a probe*. Prefer pooling; if you must pick one, pick on n.
- **A passing drift-canary is not a representative run.** The instrument
  canary in the instance above was checked immediately before the batch and
  came back in band, 4/4. The batch that followed still produced the 0/12.
  A canary answers "is the instrument still the same instrument", not "is
  this particular run typical".
- **Vacuous negative tests.** Writing `assertNotIn("P009", codes)` before
  `P009` exists passes for the wrong reason, forever. Two of the nineteen
  tests written for this very finding did exactly that on their RED run.
  Every "it does not fire" assertion needs a positive control in the same
  test.
- **Reading a swing as a size or load effect without an ablation.** Both are
  plausible, both are cheap to test, and in the instance above both were
  false.
- **Averaging draws into one number and reporting only the mean.** Two runs
  at 0% and 100% and two runs at 50% both average to 50% and mean entirely
  different things.
- **Spending the re-run on a bigger sample instead of a second run.** n=6 in
  ONE invocation does not answer a between-run question. Two runs of n=3 do.
- **Assuming the second run settles it.** Two disagreeing runs give you a
  disagreement, not a rate. Say so, and price a third rather than picking a
  winner.

## Verification

You have applied this skill correctly when:

- [ ] The determinism question is answered in writing, not assumed.
- [ ] At least two runs of an **identical** configuration exist, and the
      record names both — file paths or ids, not "we re-ran it".
- [ ] A disagreement between runs is reported as the headline, above either
      run's own number.
- [ ] No artifact was edited between the first and second run.
- [ ] Any stored verdict carries its replication count, and a checker can
      detect one that does not.
- [ ] If a large swing was explained by a cause, at least one arm was run
      that would have falsified that cause.

In this repo the mechanised half is:

```
python3 skills/skill-authoring/scripts/case_coverage.py --replication
```

which prints, per skill, how many same-description reports probed it and
which cases they disagree on, and raises **P009** on any
`state/known-weak-probes.json` entry that rests on one report or that pins
one side of a disagreement. At round 381 it read: 15 of 41 skills
replicated, **24 of 41 cross-report case verdicts disagree**.
