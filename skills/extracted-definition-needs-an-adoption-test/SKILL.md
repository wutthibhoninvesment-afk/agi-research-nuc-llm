---
name: extracted-definition-needs-an-adoption-test
description: Use when a shared "single source of truth" has been extracted — a canonical parser, a validator, a date/ID/units helper, a config loader, a shared constant, a base class — and you are about to trust that the codebase now uses it. Symptoms: the module is correct, tested, documented, and has ONE caller (the one that shipped in the same commit); the old inline regex/lookup/constant is still sitting in three other modules; a docstring says "four tools parse this, so here is one definition" and nothing checks that the four agree; a bug the extraction was supposed to end recurs in a tool that never switched; grep finds the helper's NAME only in its own file and its own tests. The move is to measure adopters as a number, make every remaining implementation agree with the definition on a fixture that carries the historical defect, and DERIVE the implementation set from the repo so the next unadopted copy fails by name. NOT for a helper with no duplicates to absorb (nothing to adopt), a mirror kept deliberately separate (copied-mirror-drift), or a check nobody runs (unrun-checker-latency).
---

# Extracting the definition is half the fix; adoption is the other half

Extraction feels finished the moment the module is green. It has a
docstring explaining the bug it ends, a test suite, and a caller. What it
usually does not have is **the other callers** — and nothing in the build
distinguishes "one definition, N adopters" from "one definition, one
adopter, N-1 copies still deciding things".

The asymmetry is what makes this survive: the extraction lands loudly, in a
commit that narrates the bug and the fix, while the non-adoption is a
*non-event*. No file changed, no test went red, no reviewer saw a diff. The
old pattern keeps working most of the time, which is exactly the condition
under which the original bug was found in the first place.

Proven on: `harness/roundheadings.py` (round 397) — extracted after two
false "round N was never recorded" gap reports 94 rounds apart, with a
docstring tabulating **four** independent parsers and which headings each
accepted. Round 449 counted the adopters fifty-two rounds later: **one**,
the tool that shipped in the same commit. Two of the other three still held
their own regexes and one of them was blind to the newest entry in the
record.

## Trigger conditions

- A module, class or constant exists whose docstring says some version of
  *"one definition of X"*, *"the single source of truth for Y"*, *"do not
  reimplement this"*. That sentence is a claim about OTHER files and has no
  reader.
- A refactor commit's message names N places that duplicated some logic, and
  the diff touches fewer than N of them.
- `grep -rn "<helper_name>"` returns only the helper, its tests, and prose.
  One caller is the tell; zero callers is easier to spot and rarer.
- You are about to fix a bug in a shared helper and are unsure whether the
  fix will reach the reporting tool. It will not, if that tool never adopted
  the helper.
- A defect recurs in a tool that "we already fixed" — check whether the fix
  landed in the shared definition and the tool reads a copy.
- **The tolerant reader case.** The extraction was tolerance (accept more
  shapes than the old strict pattern). Then non-adopters are strictly more
  brittle than the definition, and they fail on exactly the inputs the
  extraction was written to accept — i.e. on the next real instance.
- NOT this skill: two implementations deliberately kept apart and compared
  (`copied-mirror-drift`); a hand-written list of members that has gone
  stale (`derived-subject-set` — though its census technique is step 4 here);
  a checker nobody runs (`unrun-checker-latency`).

## Steps

1. **Count the adopters before reading any code.** One command, one number:

   ```bash
   grep -rn "<definition_module>" --include=*.py --exclude-dir=.venv . \
     | grep -v "<definition_module>.py" | grep -v "test_" | wc -l
   ```

   Write the number down. "One" is a finding on its own and it is the number
   a future reader will re-run. Do not proceed on an impression.

2. **Recover the extraction's own list of duplicates.** The commit that
   created the definition almost always names them — a table in the module
   docstring, a bullet list in the message. That list is the population, and
   it was written by someone who had just surveyed the tree, so it is better
   than your grep. Check each entry against HEAD: adopted, still own
   pattern, or gone.

3. **Find a LIVE divergence and measure it before you repair anything.** A
   real input on which the definition and a non-adopter disagree is worth
   more than any argument, and it is perishable — normalising the input
   destroys the experiment. Record, per parser: what it answers, and what
   the difference costs downstream. Round 449 measured that its non-adopter
   did not merely DROP the entry it could not see; it **absorbed** it into
   the neighbouring entry's scope, so the prose of one round was served as
   another round's evidence.

4. **Decompose extent from impact — they are usually different defects.**
   Run the 2x2: fix A alone, fix B alone, both, neither, and diff the
   PUBLISHED output each time. Round 449's boundary defect moved 488 KB of
   prose (26.7% of everything the tool attributed to a round) and changed
   **zero** published findings; its drift defect moved no text at all and
   changed **one**. A big number is not a live consequence, and a tiny one
   can be the only thing that matters. Report both, and say which is which.

5. **Fix the READERS, then the input — in that order, and say so.** If a
   drifted input is what exposed the gap, normalising it first makes every
   assertion below vacuous and teaches the next round nothing. Fix the
   parsers, keep the offending input verbatim as a test fixture, and only
   then normalise. Note in the commit message that the order was deliberate
   — editing the document to satisfy the regex is the failure mode this
   whole skill exists to prevent, and it looks identical from the outside.

6. **Write the agreement test as a parametrised cross-product.** Every
   remaining implementation × a fixture set that includes the historical
   defect, asserting all of them equal the definition. Add the negatives
   too: inputs no implementation may accept. This is the test that would
   have caught the original.

7. **Derive the implementation set from the repo, not from your list.**
   Walk the tree's ASTs for the shape (a compiled pattern, a call to the
   thing being duplicated, a literal constant) and fail on any file that is
   neither declared nor exempt. A hand-written roster of the tools that
   might have a hand-written roster is the same bug one level up
   (`derived-subject-set`). Then assert the census actually FINDS the known
   ones — a derived set that finds nothing is indistinguishable from a
   broken scanner.

8. **Falsify both halves in place.** Revert each fix, confirm exactly the
   new tests redden and no pre-existing one does, restore, and `md5sum -c`.
   Plant a fake unadopted implementation, confirm the census names it by
   path, delete it. A guard that has never been seen to fail is not a guard.

9. **Expect the published output not to move.** If it did move, someone
   would have fixed this already. State the unchanged-output result in the
   round file as the *explanation for the latency*, not as a reason the work
   was unnecessary.

## Pitfalls

- **Editing the input first.** It makes the live assertion vacuous and the
  finding unreproducible in one step, and it is what previous rounds did
  twice. Measure, fix readers, keep the fixture, then normalise.
- **Assuming the non-adopter simply misses the input.** Parsers that slice a
  document into ranges will hand the unrecognised region to its NEIGHBOUR.
  Check for absorption explicitly: `assert "<marker of B>" not in scope[A]`.
- **Counting a delegating caller as a duplicate.** A tool that wholly
  delegates has nothing to test for agreement; declare it and say why, or
  the cross-product asserts against a lambda that just calls the definition.
- **Treating a boundary-stop as a parser.** A regex that only needs to know
  "is this line a heading" is not deciding the same question and does not
  belong in the agreement test. Say where the line is, in the test file.
- **Scoring extent as impact.** "26.7% of attributed text was foreign" is
  arresting and moved nothing. Publish the counterfactual, not the size.
- **A test whose subject is the live defect.** Once you normalise, the live
  assertion can only fail on a FUTURE regression. Keep a fixture carrying
  the historical shape verbatim, or the knowledge is gone with the input.
- **The promoted-copy import.** If the non-adopter can be copied somewhere
  the definition is not importable, guard the import and make the fallback
  loud — a silent fallback to the strict pattern reintroduces the bug in the
  one deployment nobody tests.

## Verification

```bash
# 1. the adopter count — the number this skill is about
grep -rn "roundheadings" --include=*.py --exclude-dir=.venv . \
  | grep -v "roundheadings.py" | grep -v "test_" | cut -d: -f1 | sort -u
# round 449 (after adoption): three files —
#   ./harness/swe/toolliveness.py
#   ./skills/session-inheritance-audit/scripts/check_round_recorded.py
#   ./skills/skill-authoring/scripts/carryforward_check.py
# before it: one. The `expected: 2` on the census probe below is measured,
# not guessed: pytest prints the offending path twice, once in the assertion
# diff and once in the short summary. The first draft of this block said 1.

# 2. the agreement + census suite, and its falsification
.venv/bin/python3 -m pytest harness/tests/test_headingparser_adoption.py -q
# expected: 30 passed  (9 test functions; parametrisation is the difference)

# 3. the census must NAME a planted implementation, not just go red
printf 'import re\nF = re.compile(r"^### Round (\\\\d+) - ")\n' \
  > harness/_adoption_probe.py
.venv/bin/python3 -m pytest harness/tests/test_headingparser_adoption.py \
  -q -k undeclared 2>&1 | grep -c "_adoption_probe.py"   # expected: 2
rm -f harness/_adoption_probe.py
.venv/bin/python3 -m pytest harness/tests/test_headingparser_adoption.py \
  -q -k undeclared 2>&1 | tail -1                        # expected: 1 passed

# 4. the divergence, re-derivable from the fixture rather than the record
.venv/bin/python3 -c "
import sys; sys.path[:0] = ['.', 'skills/skill-authoring/scripts']
from harness import roundheadings as rh
import carryforward_check as cf
H = '## Round 448 (NUC-integration E) - 2026-09-02, box DOWN'
print('definition:', rh.parse_heading(H).rounds[0])
print('adopter   :', list(cf.round_sections(H + chr(10) + 'body' + chr(10))))"
# expected: definition: 448 / adopter: [448]. Before round 449 the second
# line was [] — the entry existed and belonged to nobody.
```

- [ ] The adopter count is a number in the round file, taken before the fix
- [ ] A live divergence was measured while it was still live
- [ ] Extent and impact are reported separately, with a counterfactual
- [ ] Readers were fixed before the input was normalised, and the commit says so
- [ ] The historical input survives verbatim as a test fixture
- [ ] The implementation set is derived from the repo and proven non-empty
- [ ] Every fix was reverted in place and the right tests went red
