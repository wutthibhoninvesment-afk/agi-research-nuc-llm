---
name: invalidation-ceiling-from-history
description: Before building a finer-grained freshness, cache-key, incremental-build or test-selection rule, measure its CEILING against the project's own commit history — the refinement can only help on changes it can tell apart, and that fraction is computable in twenty lines before you write the rule. Trigger when a cached or recorded result is being invalidated too often ("everything goes stale on every commit", "the ledger never accumulates", "0% cache hits"), when someone proposes per-file/per-module/per-package digests instead of a whole-tree one, when a test-impact or affected-targets selector is being designed, when the test tree lives INSIDE the tree it tests, or when a coverage instrument's recall is near zero and a smarter key is the proposed fix.
---

# A finer key is worth exactly the changes it can distinguish

You have a recorded result — a cached build, a ledger row, a coverage
verdict, a test-selection decision — gated on a digest. The digest covers too
much, so every commit invalidates everything, so the record never
accumulates. The obvious fix is a finer key: split the digest, hash per
module, follow the dependency graph.

That fix has a **ceiling**, and the ceiling is not an engineering property of
your key. It is a property of how the project is actually edited. If two
thirds of commits touch the thing every consumer genuinely depends on, then
no key — however perfect — keeps more than a third of your records alive.
That number is sitting in `git log` and takes about twenty lines to compute.
Measure it first, because it decides whether the refinement is *the* fix or a
14% improvement wearing the clothes of one.

The trap is that the refinement is genuinely correct and locally impressive.
Round 469 of this program built a role-split digest for a test tier, tested
it, and it worked exactly as designed: an edit to an unrelated test file left
a unit fresh where the whole-tree rule would have staled it. Then the history
said the split changes the verdict on **15% of commits** and cuts total
invalidations by **14%**, because 85% of commits touch the subject anyway.
The refinement shipped — it is strictly better and it costs nothing to keep —
but the round's *conclusion* had to be the opposite of the one it set out to
write: the tier's 0% recall was never a freshness problem. Nothing was
running the tests.

## When this triggers

* A cache, ledger, or freshness gate has near-zero hit rate and "make the key
  finer" is the proposed remedy.
* Someone is designing test impact analysis, affected-target selection, or an
  incremental build key, and the design argument is about *correctness of the
  key* with no number attached to *how often it will fire*.
* A record is invalidated by edits to files its consumers provably cannot
  read.
* **The test tree is inside the tree under test** (`proj/tests/` under
  `proj/`) and freshness is keyed on a whole-tree digest. This case has a
  guaranteed 0: every test edit invalidates every unit's record, including
  units that cannot import the edited file.
* A status report says "N units, 0 conclusive" and has said it for a while.

## Steps

1. **Name the roles inside the tree, before writing any key.** Not
   directories — roles. "Subject" (the thing under test), "deps" (what a
   record's own consumer reads), "irrelevant". Write the list down; a key you
   cannot state in three role names is a key nobody will maintain.

2. **Compute the ceiling from history.** For the last N commits touching the
   tree, classify each by which roles it touched, and count. Twenty lines:

   ```sh
   git log -n 200 --format=%H -- <tree> | while read s; do
     git show --pretty= --name-only "$s" | grep "^<tree>/" 
   done
   ```
   then bucket each commit into *touches the subject* / *touches only the
   test half* / *touches neither*. The refinement's ceiling is the second
   bucket's share. **Do this before you write the key**, because it is the
   only input that can tell you not to.

3. **Decompose the subject bucket too, once.** "Subject" is usually two
   things: the artefact everything depends on, and tools/benches that only a
   few consumers touch. Split it and re-count. Round 469 found 80 of 120
   commits touched the true core and 22 touched only top-level tools that 14
   of 27 units never import — so the reachable ceiling was 33% of commits,
   not the 15% the first cut suggested and not the 100% the design implied.

4. **State the ceiling as a sentence with a number in it, in the design.**
   "This key can help on at most 33% of commits" belongs in the module
   docstring, next to the key. It is what stops the next round from
   proposing the same refinement again.

5. **If the ceiling is low, say what the real fix is in the same breath.**
   A low ceiling is not a reason to skip the refinement — it is cheap and
   strictly better — it is a reason to stop calling it the fix. When the
   subject legitimately moves under every record, the only thing that raises
   recall is *taking the measurement more often*, and that is a scheduling
   and budget question, not a hashing one.

6. **Follow the dependency closure, transitively, or the split is
   fail-open.** The moment you exclude anything from a digest you are
   claiming it cannot affect the result. In a test tree that claim is usually
   false: test files import each other for shared helpers. Round 469's tree
   has `test_v11 → test_v10 → test_v09`; a depth-1 closure would have left
   six units reading `fresh_pass` across an edit to the `run()` helper they
   all call. Compute the closure by parsing imports, and pin the real chain
   in a test so it goes red if the tree stops being what you measured.

7. **Re-derive the ceiling when you next touch the rule.** It is a rate over
   recent history, so it drifts. It is not a constant; do not carry it
   forward as one.

## Pitfalls

* **Measuring the ceiling on commits that touch anything, rather than
  commits that touch SOURCE.** Doc- and JSON-only commits move no key and
  belong in neither bucket; leaving them in the denominator flatters the
  refinement.
* **Reporting the per-commit win instead of the aggregate.** "26 of 27 units
  survive" is true for the commits the split distinguishes and is the number
  you will want to quote. The honest headline is the aggregate over all
  commits — here, 86% of the invalidations remained.
* **Assuming the test half is small because it is one directory.** Measure
  it. Test trees are often the most-edited part of a repo.
* **Excluding a directory from a digest without a transitive closure over
  what is left.** That is fail-open, and it fails silently in the direction
  of green.
* **Letting the refinement's success stand in for the outcome.** The tests
  for the key will pass. The recall number is a different measurement and it
  is the one the instrument exists to report.
* **Building the key because the current one is obviously wrong.** It can be
  obviously wrong and still not be what is costing you. Obviousness is not a
  measurement.
* **Taking the ceiling from one repo's history and applying it to a sibling
  tree.** Round 469's two tiers sit in one repo and have different churn
  profiles; the same key would score differently in each.

## Verification

Run from the repo root. Both must exit 0.

```sh
# 1. the split, the transitive closure and the fail-open direction are pinned
python3 -m pytest -q harness/tests/test_whenceslow.py -k "closure or UNRELATED or IMPORTED or excludes"

# 2. the instrument reports its own recall, so a low ceiling stays visible
python3 harness/whenceslow.py status | head -1
```

Expected from (2): a single line of the form
`whence slow tier: N units / M marked (AST), K conclusive against subject
<digest> (P% recall), F failing`. The point of the line is that `P` can be
0 and *say so*; an instrument whose recall is not in its own output cannot
tell you the refinement did not work.

Found in round 469
(`knowledge/round-469-the-tier-that-had-no-slot.md`). Companion rules:
`skills/measured-not-declared-dependencies` (measure the read-set rather than
declaring it), `skills/evidence-unit-smaller-than-the-item` (when one item
cannot fit any budget), `skills/freshness-is-not-outcome` (a freshness field
is not a result), and `skills/matcher-defines-the-population` (three ways of
counting a tier's membership gave three answers).
