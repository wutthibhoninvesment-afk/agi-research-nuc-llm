---
name: copied-mirror-drift
description: Use when a second implementation was created by COPYING a first one and both are still maintained — a subclass reimplementing its parent's orchestrating method, a reference/guest/mock interpreter mirroring a real one, a golden-file generator beside the real one, a test FIXTURE or anchor duplicated across two test files. Symptoms: the copy never gained what the original gained since; A BUG FIX LANDED IN ONE COPY AND NOT THE OTHER and the fixing commit never names the second file; coverage of the copy's pathway is silently zero while the suite is green; a docstring on the copy explains why it is separate, or ASSERTS IT IS THE SAME AS the original ("same anchor X uses"), and that claim has no reader. Covers dating the fork in git, checking whether the fix is even PORTABLE (copies drift in strength, not only content), turning the copy into a narrow PREDICATE the original calls, and an AST guard — in the tier that runs every round — that fails when the fork returns. NOT for duplication you merely want to DRY up.
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
- **A copy's docstring asserts PARITY** — "same anchor X uses", "mirrors Y",
  "kept in sync with Z". That is a cross-file claim, and in a Python
  docstring it has no reader: markdown claim-checkers do not parse it and
  import graphs do not encode it. Treat every such sentence as unverified
  until a test makes it true by construction.
- **A fix you are about to apply matches more than one site.** Before
  editing, `grep` the fix's *anchor* (the token or shape it keys on) across
  the tree. Round 437 re-anchored one of two identical mutation fixtures;
  the other stayed red for a further seven rounds.
- Proven on: `harness/swe/guest.py`'s `GuestGen.program` vs
  `harness/swe/fuzz.py`'s `ProgramGen.program` (round 347) — the base gained
  a typed-tail-chain recipe in round 337 to close round 336's bug class, and
  the guest differential saw **0 of 400** of them for the next ten rounds.
- Proven on: `harness/tests/test_swe_killers.py` vs
  `harness/tests/test_swe_equivalence.py` (round 445) — the same
  `"concat"`-line mutation anchor in both, both broken by round 368's
  deletion of the `x + y` site they named, **only one repaired by round
  437**. The second was found 76 rounds later by a driver slice, and its
  docstring had claimed parity the whole time.

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
3a. **Before porting a fix across, check that it WORKS there.** Copies drift
   in STRENGTH as well as in content, and the fix is written against the
   healthy copy's strength. Round 445: killers' fixture *iterates* its
   candidates until one really kills; equivalence's took `candidates[0]`.
   Deleting the stale clause — the whole of round 437's fix — leaves
   equivalence red, because at HEAD `candidates[0]` does not kill
   (`found=False`) and `candidates[1]` does. Run the ported fix in isolation
   and watch it pass BEFORE you conclude the copies were interchangeable.
   If it does not pass, you have learned the more useful thing: the copies
   were never the same, so removing one is the only repair that holds.
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
6a. **Put the guard in the tier that runs EVERY round.** A guard sharing the
   broken copy's tier inherits its latency. Round 445's copies were both in
   a slow tier gated behind a filename prefix (`test_swe_*`), which is why
   one sat red for 69 rounds and the other for 76; the guard is therefore a
   pure-AST file named to fall *outside* that prefix and costs 0.4 s. Make
   the guard cheap enough that no tiering rule ever wants to defer it —
   inject the expensive step (`first_reachable(candidates, try_kill)`) so
   the guard tests the logic and not the subject.
7. **Budget for unrelated findings on the first run after reconnecting.**
   A starved comparator resumes sampling *everything* it never sampled, not
   only the feature you just restored. Round 347's first campaign after the
   fix found a defect in a builtin from v0.3, unrelated to the fork.

## Pitfalls
- **Fixing the copy instead of removing it.** Porting the missing feature
  across leaves the mechanism intact and buys one release of correctness.
  Round 445's version of this is sharper: the port would not even have
  bought that, because the two copies differed in strength (step 3a).
- **A duplication detector that matches by substring flags itself.** Round
  445's first draft looked for `"concat" in <expr>` and reported two hits in
  its own body — its detector predicate, and `"reachable_concat_mutant" in
  f.read()`, whose identifier merely *contains* the token. Match the anchor
  EXACTLY (`'"concat"'`, quotes included, as it appears in the subject), and
  write the guard's scope limit into its docstring: an AST shape-match pins
  the KNOWN duplication, not uniqueness. A copy spelled `line.find(...)` or
  as a regex still slips past, and claiming otherwise is the larger error.
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

Round 445's run of the same recipe, on a duplicated test fixture. Every
command is runnable from the repo root:

```
# 1. date the fork: which commit invalidated the anchor both copies named?
git log --oneline -S'x + y' -- languages/whence/whence/interp.py
git show f568a79^:languages/whence/whence/interp.py | grep -c '.*"concat".*x + y'   # -> 1
git show f568a79:languages/whence/whence/interp.py  | grep -c '.*"concat".*x + y'   # -> 0

# 2. show the fix landed in ONE copy: round 437's 15-file diff
git show ce7a89d --stat | grep -c equivalence          # -> 0

# 3. the asymmetry that makes the fix unportable (step 3a) — first
#    candidate does NOT kill, second does
cd harness && python3 -c "
import sys; sys.path.insert(0,'.')
from tests.whence_anchor import concat_arith_candidates, TWO_STRING_LITERALS
from swe.killers import load_whence, find_killer
from swe.fuzz import WHENCE_ROOT
o = load_whence(WHENCE_ROOT, 'probe')
for i, m in enumerate(concat_arith_candidates()):
    print(i, m.id, find_killer(m, TWO_STRING_LITERALS, o, WHENCE_ROOT).found)"
#   -> 0 interp.py:2059:arith#1294 False
#      1 interp.py:2014:arith#1441 True

# 4. the guard, in the fast tier, and falsified
python3 -m pytest -q harness/tests/test_whence_anchor.py       # -> 9 passed (~14s)
#   add a third inline copy under harness/tests/ -> 1 failed, naming the file
#   and line; remove it -> 1 passed

# 5. both former copies green off the one definition
python3 -m pytest -q harness/tests/test_swe_equivalence.py     # -> 11 passed (76.00s)
python3 -m pytest -q harness/tests/test_swe_killers.py         # -> 21 passed (31.18s)
```
Before the repair `test_swe_equivalence.py` was `3 failed, 8 passed in
58.16s` — three failures, one fixture.
