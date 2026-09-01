---
name: evidence-unit-smaller-than-the-item
description: Use when a coverage or freshness instrument uses the SAME granularity for the work it schedules and the evidence it records — per file, per package, per service, per shard — and one item is too expensive to ever finish inside the budget. Symptoms: a planner that correctly refuses to start an item it cannot complete, so the item shows `unknown` forever and its N cheap children are invisible; a ledger with zero entries for one item across many runs; a status report whose recall denominator counts items, not the things inside them; a "just mark it slow / skip it" remedy that is already in place and changes nothing. Covers measuring the item's internal cost distribution, splitting one claim into two smaller ones, the fail-closed direction for a split, and the superset rule that decides which old evidence a split may inherit.
---

# When one item cannot fit, everything inside it goes dark

A tiering instrument usually gets built around one noun. Files get marked,
files get promoted, files get planned, files get a ledger row, files get a
freshness verdict. That is the right noun until exactly one item costs more
than any budget the system will ever grant. Then the planner does the correct
thing — it declines to start what it cannot finish — and the correct
behaviour, repeated for months, is **indistinguishable from never having
tried**.

The blind spot is not a bug in the planner, the marker, the budget or the
ledger. It is the absence of a noun smaller than the item.

## Trigger conditions

Any two of these together:

1. An instrument schedules work and records evidence at the **same**
   granularity, and that granularity is a container (file, package, module,
   service, shard, suite) rather than a leaf.
2. Some item's estimated cost exceeds the budget the scheduler is ever given.
   Check both the normal budget and a deliberately huge one — if the item is
   absent from BOTH picks, it is unreachable, not merely deprioritised.
3. The evidence store has **zero rows** for that item, over a history long
   enough that zero is a finding rather than a coincidence.
4. The proposed remedy in somebody's backlog is "mark it slow" / "skip it" /
   "deselect it" — a remedy that reduces coverage rather than granularity.

## Step 0, before anything: re-derive the remedy you were handed

A carried backlog item names a fix that was written when somebody read the
code, not when they ran it. Check whether it is already in place. The command
is usually one line — a `--collect-only`, a registry membership test, a grep
for the marker.

If the remedy is already in effect and the symptom persists, **that is the
finding**, and it is worth more than the fix: it says the problem was
misdiagnosed at the level of its vocabulary, not its configuration.

## Steps

1. **Measure the item's internal cost distribution, not its total.** One
   process, per-leaf timing, with the suspected expensive leaf excluded:

```bash
# per-leaf cost of the complement, one process, nothing else running
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:randomly --durations=0 \
    <item> --deselect <item>::<leaf>

# is the remedy you were handed already in place? (step 0)
python3 -m pytest -q -m "not <marker>" <item> --collect-only

# bound the expensive leaf; do NOT wait for it (step 2)
timeout --kill-after=60 <cap> python3 -m pytest -q <item>::<leaf>
```

   You want two numbers: what the complement costs, and how the complement's
   cost is distributed. A complement that fits the budget is the whole case
   for splitting. A complement dominated by ONE leaf means you picked the
   wrong leaf.

2. **Bound the expensive leaf; do not measure it.** Run it alone under a cap
   and record that it did not finish. A floor is enough to justify a split and
   costs a bounded amount of wall clock. Say in writing that it is a floor and
   that no upper bound was measured — a reader will otherwise quote your cap
   as a runtime.

3. **Find the mechanical difference.** An expensive leaf is expensive for a
   reason the cheap ones avoid, and naming it is what stops the registry from
   becoming a list of superstitions. Look for the setup every other leaf takes
   and this one does not: a seeded fixture, a fake command, a cached resume
   path. Write that reason into the registry entry.

4. **Define the unit: item plus selector.**
   - No declaration -> **one** unit whose id IS the item's id. This is the
     property that makes the change free: with an empty registry, every id,
     plan, row and printed figure is byte-for-byte what it was.
   - A declaration -> **two** units, `<item>[light]` and `<item>[heavy]`, each
     with its own evidence row, cost estimate and verdict.

5. **Make the split fail-closed, and check which direction that is.** A
   promotion registry ("this is cheaper than we thought") must fail toward the
   tier a human watches. A SPLIT registry fails the other way: it may only
   turn one claim into two smaller ones. The light unit's pass must assert
   strictly less than the whole item's pass did, and the heavy unit it leaves
   behind must start unknown and stay in the recall denominator. **Verify by
   construction that declaring a leaf cannot raise any number.**

6. **Write the superset rule for inherited evidence — both halves.**

   > An old whole-item row that **passed** is evidence for every unit of that
   > item: the run was a strict superset, and "everything passed" entails
   > "these passed".
   >
   > An old whole-item row that **failed** is evidence for the whole-item unit
   > ONLY. The exit code does not say WHO was red; attributing it to a unit
   > invents a verdict, and attributing a pass to the other unit invents the
   > opposite one.

   Evidence never flows sideways or upward: `[light]` passing says nothing
   about `[heavy]`. Flag an inherited row, and **forbid the scheduler from
   using its cost** — a whole item's wall clock is the exact number the split
   exists to stop believing.

7. **Every registry refusal returns the WHOLE item.** A declared leaf that no
   longer exists, an unparsable item, a declaration covering every leaf, a
   malformed registry file: all fall back to one whole-item unit, because that
   is the strongest claim and therefore the safe one. A broken registry must
   cost wall clock, never coverage. Print the error in the status report — a
   silent fallback means the split a human asked for is not in effect while
   the recall percentage is over a denominator they no longer know.

8. **Select the heavy unit by exact id, never by substring.** A `-k`-style
   name filter matches `test_q_and_more` when you meant `test_q`, silently
   widening the heavy unit and shrinking the light one by a leaf nobody
   deselected — and both units still go green. Pin the complement property in
   a test: the light unit's exclusions are exactly the heavy unit's selections.

9. **Prorate any per-item prior.** Size, line count and file bytes are
   per-ITEM quantities, so both units of a split inherit the same tie-break
   and sort adjacently. Scale the light unit by its share of leaves and leave
   the heavy unit at the full prior — being expensive is why it was named. Say
   in the docstring that both are priors and a real measurement beats them.

10. **Bump the record's schema and keep the old key.** Leave the item field
    holding an item id so every existing reader and every hand-grep still
    works, and add the unit id beside it. For an unsplit item the two strings
    are equal, which is what makes migration unnecessary rather than merely
    deferred.

## Pitfalls

- **"Just mark it slow."** The remedy that removes the item from a run does
  not create evidence about it; it removes the pressure to. Check whether it
  is already in place before you write it again (step 0).
- **Splitting to hide a red.** A split does not deselect anything. Both units
  still have to go green for the item to be covered. If a round proposes a
  declaration right after a leaf turned red, that is the failure mode; the
  registry comment should say so out loud.
- **Inheriting a failure.** The tempting symmetry — a whole-item failure marks
  both units failed — is wrong, and it is wrong in the direction that invents
  verdicts. Half of step 6 exists only to stop this.
- **Believing the inherited cost.** An inherited row carries the whole item's
  seconds. Used as a unit estimate it reproduces the original problem inside
  the fix.
- **Recall over the wrong denominator.** After a split, "N of M covered" is
  over UNITS. Print items and units side by side and never let one silently
  replace the other in a figure that has been published before.
- **A leaf-count prior.** Prorating the HEAVY unit by leaf count gives it a
  tiny prior and sorts it first, which is exactly backwards.

## Verification

1. With an empty registry, the unit list equals the item list, one for one,
   and every id is an item id. Assert it.
2. A declared leaf that is not in the item yields one whole unit and a
   registry error string naming the missing leaf. Assert the error text
   reaches the status report.
3. A malformed / missing / wrong-shaped registry raises nothing and splits
   nothing.
4. Rule 6 in three tests: whole-pass inherited by both units; whole-fail
   inherited by neither; light-pass inherited by neither.
5. The scheduler, given an inherited row with a large `seconds` and a real
   row with a small one, orders the real one first and does NOT treat the
   inherited row as expensive.
6. The complement property: the light unit's exclusion set equals the heavy
   unit's selection set, and the heavy unit's arguments contain no substring
   filter.
7. A live check against the real registry that every declared leaf still
   exists — a rename silently disables the split, and this is the only place
   that failure is loud.
8. Re-run the instrument's own existing suite. If nothing but a deliberate
   schema pin breaks, the "empty registry changes nothing" property held.

```bash
# the split, as the instrument sees it
python3 harness/swe/slowtier.py units
python3 harness/swe/slowtier.py status | head -1
# -> "slow tier: 31 files / 32 units, ..." — both denominators, never one
python3 -m pytest -q -p no:randomly harness/tests/test_slowtier.py
```

## Worked instance

Round 433, `harness/swe/slowtier.py` + `harness/tier-units.json`. The slow test
tier scheduled, recorded and freshened per FILE.
`harness/tests/test_swe_campaign.py` holds 20 tests: 19 cost 571.32 s together
and the 20th did not finish in 748 s, because it is the only one that does not
seed a green baseline and so runs two full unfiltered interpreter suites. The
planner correctly refused it at a 900 s budget AND at 3600 s; the ledger held
0 rows for it across 26 rows and 92 rounds; and a real failure
(`test_review_stage_and_report`) sat red inside it, unobservable. The backlog
remedy on file was "add a slow marker" — already in place, and a
`--collect-only` showed all 20 tests already deselected. See
`knowledge/round-433-the-unit-that-was-a-file.md`.
