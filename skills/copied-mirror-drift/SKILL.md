---
name: copied-mirror-drift
description: Use when a second implementation was created by COPYING a first one and both are still maintained — a subclass reimplementing its parent's orchestrating method, a reference/guest/mock interpreter mirroring a real one, a golden-file generator beside the real one, a fixture builder duplicating a factory. Symptoms: the copy diverged not by being wrong but by never gaining what the original gained since; a feature added specifically to close a bug class is absent from the copy and nobody noticed for many releases; coverage of the copy's pathway is silently zero while the suite is green; a docstring on the copy explains WHY it is separate and the reason has since stopped being true. Covers dating the fork against version control, converting the copy into a narrow PREDICATE the original calls, and pinning it with an AST-level guard that fails when the fork returns. NOT for ordinary code duplication you would merely like to DRY up, and NOT for intentional forks that are no longer maintained.
---

# Copied-mirror drift

A mirror maintained by copying has already drifted. The useful question is
never "is the copy correct?" — it usually is, for the version it was copied
from — but **"what has the original gained since?"**

The failure is silent by construction. The copy still runs, still passes,
still produces plausible output. What is missing is a code path that was
never in it, so no assertion fails and no coverage number moves: the copy's
pathway is exercised at full volume and simply never reaches the new thing.

## Trigger conditions
- A class overrides its parent's *orchestrating* method (the one that
  decides WHAT gets produced) rather than a leaf method, and the override's
  body is recognisably the parent's body plus one local change.
- A reference, guest, mock or golden implementation exists to be compared
  against a real one, and both are edited by hand.
- A comment on the copy explains why it must be separate. Reasons rot faster
  than code; check whether the reason still holds before anything else.
- A feature was added in release N specifically to close a bug class, and
  `git log -- <copy path>` shows release N never touched the copy.
- You are about to add a recipe/case/branch to the original and there is a
  second thing shaped like it somewhere in the tree.
- Proven on: `harness/swe/guest.py`'s `GuestGen.program` vs
  `harness/swe/fuzz.py`'s `ProgramGen.program` (round 347) — the base gained
  a typed-tail-chain recipe in round 337 to close round 336's bug class, and
  the guest differential saw **0 of 400** of them for the next ten rounds.

## Steps
1. **Date the fork before reading either side.** `git log --oneline -- <copy>`
   and `git log --oneline -- <original>`, then diff the commit sets. Every
   commit that touched the original and not the copy is a candidate gap.
   Do this first: it costs one command and it tells you whether you are
   looking at drift or at a deliberate divergence.
2. **Measure the gap as a count, not as a diff.** Generate/execute a real
   sample through the copy and grep for the artefact the original's new code
   produces (`sum(1 for s in corpus if pat.search(s))`). "0 of 400" is a
   fact a future round can re-run; "the copy is missing a feature" is not.
   A zero here is the whole finding — record it verbatim in the round file.
3. **Ask what the copy is FOR.** Almost always it exists for one narrow
   decision (filter these out, use smaller sizes, ban these names). That
   decision is the only thing that should survive.
4. **Turn the copy into a predicate the original calls.** Give the original
   a hook whose name is a question about ONE item —
   `keep_stmt(stmt)`, `is_allowed(case)`, `size_for(kind)` — defaulting to
   the permissive answer, and delete the override. A subclass that answers
   "keep this?" **cannot** also decide which items exist, so the class of
   drift is gone rather than repaired.
5. **Pin it structurally, over the AST.** A grep for the feature's NAME in
   the copy finds nothing and proves nothing; the property is a SHAPE — "no
   subclass of X defines method M". Walk the tree with `ast`, collect
   `ClassDef`s whose bases include the parent, and fail on any that define
   the orchestrating method.
6. **Make the guard non-vacuous, and prove it fails.** Assert that at least
   one subclass was found (a renamed base silently empties the search), then
   reintroduce the override by hand, watch the test fail, and restore. An
   unfalsified guard is a comment.
7. **Budget for unrelated findings on the first run after reconnecting.**
   A starved comparator resumes sampling *everything* it never sampled, not
   only the feature you just restored. Round 347's first campaign after the
   fix found a defect in a builtin from v0.3, unrelated to the fork.

## Pitfalls
- **Fixing the copy instead of removing it.** Porting the missing feature
  across leaves the mechanism intact and buys one release of correctness.
- **Trusting the copy's own docstring.** It states the reason for the fork
  as of the day it was written. In the proven case the reason ("the guest
  parser has no `shape` support") had been false for nine rounds, and a
  *different* file already said so.
- **Assuming a passing suite is evidence.** The copy's tests pass because
  they test the copy. Coverage of a path that was never generated is not
  distinguishable from coverage of a path that always passes.
- **Grepping for the feature name.** See step 5 — you are looking for a
  shape, not a token.
- **Refactoring the original's algorithm at the same time.** The hook must
  preserve the original's output exactly when the predicate is the default;
  verify that first, then let the subclass's stream change.
- **Forgetting that the predicate changes the copy's random stream.**
  Downstream tests that pin counts from a shared generator will move. That
  is the fragile-floor class, not a regression — re-measure and widen the
  floor rather than restoring the old stream.

## Verification
```
# 1. the gap, as a count, before the fix
python3 -c "...generate 400 through the COPY; grep the original's artefact..."
#   -> 0

# 2. the same count after the fix
#   -> non-zero, at a rate comparable to the original's

# 3. the structural guard passes, and fails when the fork returns
python3 -m pytest -q harness/tests/test_swe_fuzz.py -k fork
#   -> 1 passed
#   (reintroduce the override by hand -> 1 failed, then restore)

# 4. the comparator, re-run on the newly reachable inputs
python3 -m harness.swe.guest -n 60 --seed 3
```
Round 347 measured, in this order: 0/400 → 118/400 typed tail chains through
the guest; guard `1 passed`, `1 failed` on a hand-reintroduced fork; and one
new comparator finding (`fold`'s miss dropping its accumulator) on the 21st
program of the first campaign after the fix.
