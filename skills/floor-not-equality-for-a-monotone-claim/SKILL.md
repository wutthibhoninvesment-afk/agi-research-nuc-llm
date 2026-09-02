---
name: floor-not-equality-for-a-monotone-claim
description: A documented expectation about a number that can only move one way must be written as a bound in that direction, not as an equality. Trigger when writing or repairing an "expected: N" claim in a Verification block, README, docstring or test — especially a test count, corpus size, case count, or any other tally that only grows — and whenever a checker reports such a claim stale.
---

# A claim on a monotone number belongs as a bound, not an equality

An equality claim about a number that can only move one way is not a fact
about the artefact. It is a fact about the artefact **and the moment it was
read**, and the moment is not written down. It will go stale, the only
question is when, and re-deriving it writes a fresh equality that starts the
same clock again.

The measurement behind this skill: round 441 executed this workspace's
`claim_check --run` tier over the whole skills corpus — the first and, until
round 459, only time it ever ran. It found **15 stale claims across 10
skills. Every one understated. Every one was a suite size or a corpus size**,
and those only grow. Round 441 wrote them up and corrected **none**, saying
correcting them needed a quiet box. Round 459 re-ran the tier on a quiet box
**18 rounds later**: all 15 sites were textually unchanged and all 15 were
still stale — and 13 of the observed values had grown AGAIN in the interval.
Correcting them as equalities would have bought about eighteen rounds.

## When this triggers

* You are writing `# expected: N passed` under a command in a Verification
  block, or `Ran N tests, OK`, or `N skill(s), N case(s)`.
* A checker reports such a claim stale and you are about to re-derive it.
* You are writing `assert len(REGISTRY) == 103` about a registry that entries
  are added to and never removed from.
* A README says "the corpus holds 27 X" and X is a directory people add to.

## When it does NOT trigger — the negative case

A number that can genuinely move in **both** directions must stay an
equality, because a bound in either direction throws away half the signal.
`0 error(s)`, `0 warning(s)`, `exit 0`, a checksum, a percentage, a wall-clock
duration, a count of KNOWN exceptions that a round may add to or discharge —
all of these are two-sided and all of them belong as `==`. `0 error(s)` in
particular is already the tightest possible bound; rewriting it as `<= 0`
changes nothing and hides that you thought about it.

## Steps

1. **Name the two events.** Write down, in one clause each, what would make
   the number go up and what would make it go down. If you cannot name a
   plausible down-event, the number is monotone.
2. **If monotone, write the bound in the direction of travel**, and make the
   claim state the event it still reports: `>= 207 passed` fails only when
   somebody DELETES a test, which is exactly what a reader wants to hear.
3. **Check that the tool which reads the claim understands the syntax.** A
   bound the checker parses as an equality, or not at all, is not a weaker
   check — it is no check. This is the step that fails silently: round 459
   had to teach `claim_check.claim_constraints()` four spellings (`>=`,
   `≥`, `at least N`, `N+`) before a single floor in the corpus meant
   anything, and one of the four did not match at all until a test asked for
   all four.
4. **Anchor the bound.** Record when and from what it was derived
   (`>= 207 passed (round 459)`), so a later reader can tell a deliberate
   floor from a stale measurement someone forgot to update.
5. **Leave the two-sided numbers alone.** Converting `0 error(s)` to a bound
   is the failure mode of this skill applied without step 1.

## Pitfalls

* **A floor is not a mute button.** If no realistic event can push the number
  below the floor, the claim is unfalsifiable and you have deleted a check
  while appearing to keep one. Set the floor at the value you observed, not
  at some comfortable margin below it — a floor of `>= 1 passed` on a
  207-test suite reports nothing.
* **Re-deriving an equality is not a fix.** It resets a clock. Between round
  441 measuring these 15 and round 459 repairing them, every one of them was
  correct on the day it was written.
* **The direction is a property of the process, not the number.** Test counts
  grow *in this program* because rounds add tests and never delete them; in a
  repo that prunes, `passed` is two-sided and the equality is right. Justify
  the direction from the workflow, not from the last three observations.
* **A bound written where the checker cannot see it is worse than none.** An
  expectation written as a bare output line rather than a `#` comment parses
  as a *command* in this workspace's Verification format; the real command
  above it then has an empty claim and is never number-checked at all. Two
  such sites existed in this corpus; the first was found by hand in round 441
  and never given a detector, so the second sat undiscovered until round 459
  wrote `claim_check`'s `C005`.

## Verification

Run from the repo root. Every command below was run as written, solo, in
round 459.

```bash
# 1. The checker understands a floor, and a floor still goes red DOWNWARD.
python3 -m pytest -q skills/skill-authoring/scripts/test_claim_check.py \
  -k "TestFloorClaims or TestFloorComparison or TestBareExpectationDetector"
# expected: >= 13 passed (a floor, per this skill's own step 2)

# 2. The corpus states no expectation the number tier cannot see.
python3 skills/skill-authoring/scripts/claim_check.py skills/
# expected: 0 stale claim(s), exit 0, and NO `C005` line. `0 stale` is an
#           EQUALITY on purpose: staleness is two-sided, so a bound would
#           hide a repair as readily as a regression.

# 3. The repairs are bounds, not fresh equalities. Round 459 converted
#    fourteen sites; a later round adding one should see this rise.
grep -c "expected: >=\|# >= \|Ran >= " skills/*/SKILL.md | grep -vc ":0$"
# expected: >= 10 skill file(s) carrying at least one floor claim
```

A floor that never fires is a deleted check, so the honest test of this skill
is step 1's `test_a_floor_ABOVE_the_observation_is_still_a_finding`: it pins
that `>= 9 passed` against an observed 7 is reported, not swallowed.
