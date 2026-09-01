---
name: decision-must-name-its-question
description: Use when a pipeline has ONE checker/decider/validator/scorer whose verdict is consumed by code handling several KINDS of case, and you are adding a second one. Symptoms: a verdict field called `status`, `ok` or `valid` with no field saying what was checked; a report line naming the condition from the CASE ("rests on: refusal") beside a verdict from a checker that knows only one condition; a dispatch table with one entry; a second validator added beside the first with no change to the consumer; `if status == BROKEN: excuse()` where `status` came from something that never saw what this case needed. Covers making each verdict carry the question it answered (`decided_over`), making the consumer compare that against the question the case asks, demoting on mismatch rather than trusting, measuring whether the mismatch has ever fired, and pinning that latency with a test that goes red when it stops being latent.
---

# A verdict that does not name its question is a verdict about the wrong case

One decider is always correct about which question it answered, so nobody
writes the question down. The consumer looks like this:

```python
row["needs"]  = case.required_condition      # from the CASE
row["status"] = decider(case)["status"]      # from the ONLY decider
...
if row["status"] == BROKEN:  excuse(row)
if row["status"] == HOLDS:   count_as_refuted(row)
```

Both halves of a comparison are present. The comparison is not. It costs
nothing while `decider` is the only one, and the day a second decider is
added — usually by the person closing "we should also check X" — every case
that needs X keeps being answered about Y, in whichever direction the Y
answer happens to fall. The failure is silent both ways: a case is EXCUSED
because an unrelated condition was broken, or counted as a hard refutation
because an unrelated condition held.

The tell is that the field naming the case's own requirement already exists.
Somebody wrote it down, put it in the report, and never joined it.

## The instance this came from

Round 420 of this program built a static analysis whose conclusions each
rest on one of three named preconditions (`refusal`, `append_only`,
`kind_stable`), and recorded per conclusion which one. Round 426 made ONE of
them decidable from the case's inputs and wired it into the consumer, which
then partitioned every counterexample into "strict / excused / undecided" by
that one decider's answer.

Round 428 measured the reference registry: **14 of 23 cases rest on
something other than the one condition being decided** — 9 on a different
condition, 5 on nothing at all, because their guardian is two-sided and its
requirement set is EMPTY. (The empty set is the case everybody forgets. It
does not contain your condition either.)

**And it had never once been wrong.** A case only reaches the partition by
being a counterexample, and none of the 14 ever had been. So the finding was
not a bug — it was a hazard that becomes reachable the moment the second
decider exists. The routing, the mismatch demotion and the second decider
all landed in the same change, and the write-up said "latent, no published
number is affected" rather than claiming a catch.

Routing had a second effect nobody predicted. Deciding the condition each
case ACTUALLY rests on moved five cases out of `undecided`, and the
contingency table the whole analysis rested on went from `p = 0.10` — which
the previous round had correctly shown was the MINIMUM ATTAINABLE p for a
split of that shape — to `p = 0.022`, with no new measurement. The previous
round had costed that improvement at a fresh experiment. It was already paid
for; the cases had been asked the wrong question.

## When to use

- You are adding a SECOND checker, validator, scorer, linter, policy engine
  or migration to a pipeline that has had exactly one.
- A verdict object crosses a module boundary carrying `status` but not
  `subject` / `criterion` / `version`.
- Cases in the input are heterogeneous — they declare a `type`, `kind`,
  `schema`, `requires` or `applies_to` field — and one code path handles all
  of them.
- A consumer branches on a verdict to EXCUSE, SUPPRESS or WAIVE something.
  Excusing on the wrong criterion is the direction that never gets noticed,
  because the case disappears from the report.
- A dispatch table, registry or strategy map has exactly one entry, or a
  `get(kind, default_handler)` whose default is the only real handler.

### NOT this skill

- **`precondition-must-be-decided`** — the condition is PRINTED rather than
  computed at all: one decider does not exist yet, so there is nothing to
  route. That skill is the prerequisite; this one is what its second
  application needs. Use both when adding decider number two.
- **`verdict-carries-its-threshold`** — a stored boolean whose other operand
  was dropped, so the verdict cannot be re-derived. Here every operand
  survives and the verdict is sound; it is about a different case.
- **`carried-claim-rot`** — a claim that was TRUE when written and went
  stale under a moving subject. Here the claim was never about this case.
- **`measured-exemption`** — a per-input exemption known in advance. Here
  the mis-routing is invisible to whoever configured it.
- **`filter-shares-the-defect`** — a filter and the thing it filters share a
  bug. Related in spirit; that one is about a common cause, this one about a
  missing join.

## Steps

1. **Find the two halves.** In the consumer, locate the field carrying the
   CASE's requirement and the field carrying the DECIDER's verdict, and grep
   for any expression mentioning both:

   ```
   $ grep -n 'requires\|applies_to\|\.pre\b\|criterion\|kind' <consumer>.py
   $ grep -n 'status\|verdict\|result\[' <consumer>.py
   ```

   If no line mentions both, the join is missing. That is the finding; the
   rest is mechanical.

2. **Make every verdict declare its question.** Add one field at each
   producer — a tuple, not a string, because a case may require several:

   ```python
   return {"status": status, ..., "decided_over": (COND_APPEND_ONLY,)}
   ```

   Give the field a DEFAULT at the consumer equal to what the single decider
   answered, so every verdict written before this change is read correctly
   rather than treated as unknown:

   ```python
   decided = tuple(row.get("decided_over", (COND_APPEND_ONLY,)))
   ```

   Pin the default with its own test. Back-compat here is not politeness —
   without it, historical records silently change meaning.

3. **Route, and make the routing conjunctive.** The case's requirement set
   may name more than one condition; the verdict holds only if all of them
   do, and breaks if any does:

   ```python
   if any(s == BROKEN for s in per_condition): status = BROKEN
   elif all(s == HOLDS for s in per_condition): status = HOLDS
   else: status = UNKNOWN
   ```

4. **Leave undecidable conditions ABSENT from the dispatch table, not
   stubbed.** A stub that returns `HOLDS` is the failure this skill is
   about, wearing a hat. An absent entry yields `no_decider`, which combines
   as `UNKNOWN`, which excuses nothing:

   ```python
   DECIDERS = {COND_A: decide_a, COND_B: decide_b}    # COND_C deliberately absent
   assert COND_C not in DECIDERS       # a test, so nobody "completes" the table
   ```

5. **Distinguish "no condition applies" from "could not decide".** A case
   whose requirement set is EMPTY is not undecided — nothing was asked. Give
   it its own status (`inapplicable`). Collapsing it into `unknown` inflates
   an undecided count and makes coverage look worse than it is; in the
   instance above it turned 13 undecided into a published "18 unknown".

6. **DEMOTE on mismatch; never promote.** At the consumer, a verdict decided
   over the wrong condition must fall to undecided regardless of which way
   it fell:

   ```python
   row["mismatch"] = bool(row["needs"]) and not set(row["needs"]) <= set(decided)
   excused = [r for r in rows if r["status"] == BROKEN and not r["mismatch"]]
   strict  = [r for r in rows if r["status"] == HOLDS  and not r["mismatch"]]
   ```

   Two tests, one per direction. The `BROKEN` one matters more: it is the
   path that makes a case vanish from the report.

7. **Measure whether the mismatch has EVER fired, over every artefact you
   have.** This decides what you are shipping and what you write down:

   ```
   for each recorded run:
       count rows where mismatch is True
   ```

   Zero means the hazard is LATENT — the guard is prophylactic and no
   published number is wrong. Say that plainly instead of writing it up as a
   caught bug; a reader who later checks will find the zero.

8. **Pin the latency, not just the guard.** A test asserting "mismatch count
   is 0 across all recorded artefacts" is the one that goes red when the
   hazard stops being latent, which is the moment somebody needs to re-read
   the partition:

   ```python
   def test_the_hazard_is_latent_in_every_recorded_artefact():
       assert n_off_criterion == 14        # the exposure
       for run in RECORDED: assert mismatched(run) == []   # and the zero
   ```

   Assert BOTH numbers. The exposure count going to 0 means somebody deleted
   the cases; the mismatch count leaving 0 means the guard started working.

9. **Re-run every aggregate the old verdict fed.** Routing changes which
   cases are decided, and decided-case counts are usually the denominator of
   something — a coverage percentage, a contingency table, a pass rate.
   Recompute them and diff against the published numbers. Reproduce the OLD
   number with the unrouted path first, as a check on your arithmetic,
   before believing the new one.

## Pitfalls

* **The empty requirement set.** A case that requires NOTHING fails
  `criterion in case.needs` for every criterion, so a naive count of
  "cases not covered by decider A" silently includes them. Round 428
  predicted 9 and measured 14 for exactly this reason. Count the three
  classes separately: needs-A, needs-something-else, needs-nothing.
* **Extending a decider after seeing the outcomes.** The decider cannot read
  a verdict — that is the point — but its AUTHOR can, and will, while
  looking at which cases came back undecided. That is legitimate and must be
  DISCLOSED: name the rule you added after looking, and re-run the headline
  with it removed to show the result survives.
* **Reusing the first decider's traversal.** The two conditions are about
  different structure. In the instance, the first decider flattened
  concatenation chains (right for "is this an append", wrong for anything
  else) and emitted whole lists when their lengths differed (which loses the
  commonest shape of the second condition). Share only the sub-decisions
  that must agree — a shared helper for the one edit shape both read — and
  write the second traversal separately.
* **A verdict that is a proof, not a decision.** If your decider says
  `False` for "not shown" as well as for "shown false", document which, and
  make the three-way return explicit. `holds / broken / unknown` beats
  `bool` for the same reason `decided_over` beats no field.
* **Fixing the join without fixing the report.** The report line that names
  the case's condition next to the wrong verdict is what a human reads. It
  needs a visible `DEMOTED to undecided: that verdict was decided over X,
  which is not what this case rests on` — otherwise the guard works and
  nobody can tell it did.

## Verification

Run all of these; each fails loudly if the corresponding step was skipped.

```
# 2 — every producer declares its question, and the default is pinned
$ grep -c 'decided_over' <module>.py            # >= one per producer + consumer
$ pytest -k 'no_decided_over_is_read_as'        # back-compat default

# 4 — the undecidable condition is absent, and stays absent
$ pytest -k 'no_decider'

# 5 — inapplicable is its own status
$ pytest -k 'not_blind or inapplicable'

# 6 — both demotion directions
$ pytest -k 'wrong_precondition or mismatch'

# 7/8 — the latency measurement, asserted in both halves
$ pytest -k 'latent_in_every_recorded_artefact'

# 9 — the old aggregate reproduces, then the new one
$ pytest -k 'reproduces_round_426 or below_p_of_five_hundredths'
```

Reference implementation: `languages/whence/polarity.py`
(`routed_precondition`, `PRECONDITION_DECIDERS`, `check_law`'s
`pre_mismatch`) and `languages/whence/tests/test_polarity.py`
(`test_a_broken_decided_over_the_wrong_precondition_does_not_excuse`,
`test_the_wrong_question_hazard_is_latent_in_every_recorded_artefact`).
Round 428's knowledge file, §1 and §3, records the measurement and the
three controls on the p-value it moved.
