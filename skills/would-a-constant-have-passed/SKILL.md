---
name: would-a-constant-have-passed
description: Use when a test, differential, or acceptance corpus is about to pin a value a system COMPUTES — a line number, an index, a count, a timestamp, an id, a retry delay, a resolved path — and you want to know whether the corpus can tell the computation from a hard-coded constant. Symptoms: every case in the fixture set happens to expect the same value; the expected value is 0, 1, or the first element; two numbers in the same assertion always differ by exactly one; a feature ships green and the first real input off the fixture's beaten path is wrong. Covers running the constant-substitution check, finding which constants survive, widening the corpus BEFORE measuring rather than after, and pinning the separation so a later round cannot narrow it back. NOT for a filter that excludes the interesting subjects (filter-shares-the-defect), an aggregate that hides an internal convergence (round 396), or an untested code path (untested-default-path).
---

# Would a constant have passed?

A corpus assembled to exercise a **rule** does not automatically exercise
the **values** the rule computes. These are different jobs and they are
easy to conflate, because a corpus that covers every branch feels like a
corpus that covers every output.

The failure is specific and quiet. You add a feature that computes a
number. You add cases that reach it. Every case goes green. But if every
case in the corpus expects the *same* number, the corpus has not tested the
computation at all — it has tested that something with the right shape is
printed there, and a `return 1` would have satisfied it identically.

Proven on `languages/whence` (round 402). A self-hosted guest parser was
taught to name the line of a name's first binding, closing the last
divergence from the host implementation. The differential's two relevant
cases were

```
let a = 1
let a = 2
```

and the same collision nested one block deeper. **Both bind on line 1.**
A guest that computed nothing and printed the constant `1` would have passed the
entire differential — and so would one that reported the *duplicate's*
line, since in both cases that differs from 1 by exactly one, in the
direction a plausible off-by-one produces. Two distinct wrong
implementations, both green, in a corpus of 54 programs.

## When to use (triggers)

- You are adding an assertion on a value the system derives rather than
  echoes: a line/column, an offset, an index, a duration, a generated id, a
  resolved path, a computed count.
- Every fixture in the relevant family expects the same expected value, or
  the value is `1`, `0`, `true`, or the first element of something.
- Two numbers in one message/record always sit at a fixed offset from each
  other in the corpus (`line 1` and `line 2`, `start` and `start+1`).
- A parity/differential harness just went from "differs" to "agrees" on a
  case whose agreement depends on a newly computed field.
- Someone is about to write "the corpus proves X is computed correctly".

**When NOT to use:** the value is genuinely constant by specification (then
pin it *as* a constant and say so); the concern is that interesting
subjects were filtered out before counting (`filter-shares-the-defect`);
the concern is an aggregate hiding a convergence inside a string (round
396's lesson); the path is simply never executed (`untested-default-path`).

## Steps

1. **Name the computed value and its type.** Write the sentence "the system
   computes V from S". If you cannot name S — the source the value is
   derived from — stop: you do not yet know what a wrong implementation
   would look like.

2. **Tabulate V across the whole corpus.** One row per case, expected V in
   a column. Do this literally; do not eyeball it. In the whence case the
   table was two rows and both said `1`.

3. **Ask the three constant questions.**
   - Is `|distinct(V)| == 1`? Then a literal passes.
   - Is V always the same function of a NEARBY value the code already has
     in hand (`other - 1`, `first element`, `len(x)`)? Then that confusion
     passes.
   - Is V always the identity/default the language would produce anyway
     (`0`, `""`, `None`, line 1)? Then doing nothing passes.

4. **If any of the three survives, widen the corpus BEFORE you measure.**
   Add cases that break each surviving constant — a case where V is not the
   default, a case where V and the nearby value are not one apart, and a
   case reaching V by a *different construction path* (in whence: the
   `shape` desugar, which builds the same node type from a different
   constructor). Widening after a green run is how a number becomes
   folklore.

5. **Check the widened cases against the reference, not against your
   implementation.** If there is a reference implementation, an oracle, or
   a prior version, derive the expected V from it. Deriving expectations
   from the code under test converts step 4 into a change-detector.

6. **Pin the separation itself, not just the values.** Add a test over the
   fixture table asserting `len(distinct(V)) >= 3` and "at least one case
   where V and the nearby value are not one apart". Without it, a later
   round trimming the corpus silently restores the blind spot and every
   test stays green.

7. **Record the widening in the round/PR text with both numbers.** "Corpus
   54 → 59, agreeing share 34/54 → 41/59." A corpus that grows without the
   denominator being republished lets a later reader mistake a wider
   measurement for a better result.

## Pitfalls

- **Widening after the feature is green proves nothing about the feature.**
  It proves the feature you already shipped passes cases you chose knowing
  the implementation. Order matters: widen, then measure.
- **A snippet that does not parse contributes zero cases and no error.** In
  the whence round, one hand-written probe snippet used a guessed effects
  syntax (`!io` for `effects [io]`) and silently added nothing. Print the
  rejects, do not trust the total.
- **The plausible wrong answer is usually adjacent, not random.** Off by
  one, the other end of the range, the enclosing scope's value. Design the
  widening cases against *those*, not against arbitrary values.
- **`0`, `1`, `""` and "the first line" are the constants that hide
  best**, because they are also the sentinels a correct implementation
  legitimately returns. If your sentinel and your common value coincide,
  add a case that distinguishes them.
- **Do not fix the corpus's stale pins before the first run.** Running the
  suite once with the pins as they are measures the change's blast radius;
  pre-emptively fixing them replaces a measurement with an assertion. (This
  cost round 402 a scorable prediction.)
- **A differential's own sanitisers may delete the new value.** Round 402's
  differential stripped a trailing `(line N)` implementation coordinate
  with a `$`-anchored regex; the new feature put `(line N)` *inside* the
  message. Only the anchor saved it. Grep the harness for normalisers that
  match the shape of the value you just added.

## Verification

Run these against the corpus you are about to trust.

1. **The distinctness check.** For the fixture family under test:
   ```
   python3 -c "import json,sys; v=[c[1] for c in CASES]; print(len(set(v)), sorted(set(v)))"
   ```
   `1` distinct value means step 4 is mandatory.

2. **The substitution check — the real one.** Replace the computed value in
   the implementation with each surviving constant and re-run the corpus.
   Every constant MUST produce at least one failure. If one still passes,
   the corpus is not yet wide enough. In whence this was done as a test
   that plants a divergence in the implementation and requires the sweep to
   catch it in *every* affected case, not just the first.

3. **The separation pin exists and fails when removed.** Delete one widened
   case; the meta-test from step 6 must go red. A guard on the guard that
   has never been seen red is not a guard.

4. **The denominator is published.** `grep` the round/PR text for the old
   and new corpus sizes appearing together. A share reported without its
   denominator changing is the failure mode this step exists to stop.
