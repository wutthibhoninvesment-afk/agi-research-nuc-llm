---
name: derived-subject-set
description: Use when an anti-rot test is green and you are about to trust it — "every X is registered/owned/covered", a schema-vs-code check, an exhaustiveness list. Symptoms: the check's LEFT-HAND SIDE is a literal (constants, a count, a copied enum) and its right side is the real artefact; the list is in PROSE (a next-step, a doc) run as a work order; a docstring promises "a new X arrives here as a failure" and none has; a new member shipped and the suite stayed green; a tool dies on a member missing from a hand-written MODULES tuple. DERIVE the subject set from the artefact, then cross-check against an independent read — a derivation can itself return a SUBSET, making every property vacuous. ONE EXCEPTION, check FIRST: if a STATIC ANALYSER also reads the literal (a closure auditor, a bundler), deriving hides it — keep the literal, derive the ORACLE. Symptom: a description claiming a derivation the code does not do. NOT for an uninvoked checker (unrun-checker-latency) or a rolling prose claim (carried-claim-rot).
---

# A hand-written list of the things a hand-written list might miss is not an anti-rot check

Anti-rot tests are written at the moment a family is complete. `HINTS = [A,
B, C, D]`, `MODULES = ("a", "b", "c")`, `ALL_HANDLERS = {...}` — every one
correct on the day it lands, every one carrying a docstring that promises
the next member will arrive as a failure. Completeness is exactly the
property that does not survive the next change.

The failure is quiet in a way that a red checker is not. The test runs, in
the fast tier, in milliseconds, every single build. It is **green**, and it
is green *because* the thing it guards grew and it did not.

## Trigger conditions

- A test named `test_every_X_is_...` / `test_all_X_have_...` whose `X` set
  is a literal in the test file rather than read from the artefact.
- A docstring or comment promising "a new X added by a future change fails
  here", written more than one change ago, with no record of it ever firing.
- You just added a member to a family (a new error hint, a new module, a
  new subclass, a new migration) and the suite stayed green when you
  expected it to complain.
- A hand-maintained tuple/list/dict that mirrors something enumerable:
  files in a directory, `_`-prefixed module constants, enum members,
  `Raise` sites, subclasses, DB tables, route handlers.
- Two lists of the same family in different files, either of which could be
  the stale one.
- A tool dies on import/startup for a member that exists in production and
  not in the list — the same defect, arriving as a crash instead of a green
  test.
- **A DESCRIPTION that claims a pattern while the code names members.** A
  docstring, a `--help` string, a config comment or a registry `_comment`
  saying "every `X/*/y`" next to an argv, an `include:` list or a `MODULES`
  tuple that spells three of them out. The prose is a promise about a family;
  the code is a list; nobody checks them against each other.
- **The list is in PROSE, not in a test** — a carried next-step, an ADR,
  the "candidates" paragraph of the write-up that found the defect. Nobody
  treats it as an anti-rot check because it is not a check, and the next
  change executes it as the work order. See the round-482 section below.
- **You are about to replace such a list with a glob** and something else in
  the tree reads that list statically. Stop and read the section on the
  bounded exception below before you do.
- **The set of members is derived and the FIXTURE that instantiates them is
  not** — a crawler rooted at one hand-written input, a fuzzer over a fixed
  corpus, a conformance suite whose cases are typed out. The roster is
  live; the witness is a list wearing a program.
- **You reverted the fix and the check still passed.** The check keeps one
  arbitrary witness per member, and the violating one is a different member
  of the same class. See the round-488 section.
- **Every stress/scale case in the suite varies the same axis** — all of
  them make the value big, none makes the NAME big; all deepen the tree,
  none widens it. A "however large X is" claim checked on one axis is a
  claim about that axis.

**When NOT to use:** the check does not exist (write it); the check exists
and nothing runs it (`unrun-checker-latency`); the rule is documented and
implemented by no tool (`unenforced-documented-rule`); the claim is prose
in a rolling status document (`carried-claim-rot`); the list is a
deliberate ALLOWLIST whose whole purpose is to be smaller than the family
(then the job is `exemption-census` — measure it, do not derive it).

## Steps

1. **Find the literal.** In the failing-to-fail test, identify which side
   of the assertion is data and which is code. Write down the family in one
   sentence: *"every X such that P"*. If you cannot state `P` without
   listing members, the family is not enumerable and this skill does not
   apply — say so and stop.

2. **Prove it is stale before fixing it.** Add one new member to the family
   the way a normal change would, run the check, and confirm it stays
   green. This costs a minute and converts "I think this is a list" into a
   demonstrated defect. Record the observation; it is the evidence, and it
   is what stops a reviewer reading the fix as a refactor.

3. **Pick the derivation, cheapest first.**
   - directory listing (`os.listdir` of a package) — for module/file sets;
   - module namespace (`vars(mod)` filtered by a naming convention) — for
     constant families that already share a prefix or suffix;
   - AST walk of the source (`ast.walk` for `Raise` / `ClassDef` /
     decorated functions) — for call/raise/definition sites;
   - runtime reflection (`__subclasses__`, a registry decorator, an
     `Enum`'s members, `information_schema`) — where the framework already
     keeps the list.
   Prefer the one whose failure mode is *too many* rather than *too few*: a
   derivation that over-collects makes the check noisy, which someone
   fixes; one that under-collects makes it green, which nobody sees.

4. **If the derivation needs a naming convention, enforce the convention.**
   Deriving `_..._HINT` constants means a hint NOT named that way is
   invisible — the same defect one level down. Promote the stragglers into
   the convention (a message literal becomes a named constant) and check
   that the artefact's observable output is byte-identical before and
   after, so the promotion is provably cosmetic.

5. **Cross-check the derivation against an independent read.** This is the
   step that makes the fix trustworthy: a derived set can silently shrink
   too. Assert the derived count against a *different* mechanism — a `grep`
   of the source when the derivation is reflection, or reflection when the
   derivation is a grep — and pin the number. Two independent readings that
   agree is a fact; one reading is a preference.

6. **Keep a registry for the members that legitimately opt out, with a
   REASON each.** Derivation turns "which members exist" into a fact and
   leaves "which members need the property" a judgement. Make the
   judgement explicit: `{member: why_it_is_exempt}`, classified into a
   small closed set of reasons, plus a test that every registry key is a
   live member (no stale entries). Disagreeing then requires editing a
   written claim.

7. **Re-run and pin the counts on both sides.** `assert hinted == 7 and
   unhinted == 13`, not `assert unhinted > 0`. An exact pin is what catches
   a member that silently stops being covered; a future change that moves
   it must say so in the diff.

8. **Sweep for the same shape.** A repo that has one hand-written subject
   set usually has several, written by the same reflex. Grep for tuple/list
   assignments in ALL-CAPS near the top of tooling files, and for tests
   whose left-hand side is a literal collection. Fix the ones whose family
   demonstrably grows; leave and annotate the ones that are genuinely
   closed.

## Commands

Derive, cross-check, and prove the old check could not see the new member:

```bash
# 1. the family, three common derivations
python3 -c "import os; print(sorted(f[:-3] for f in os.listdir('pkg') if f.endswith('.py')))"
python3 -c "import pkg.mod as m; print(sorted(k for k in vars(m) if k.endswith('_HINT')))"
python3 - <<'EOF'
import ast
t = ast.parse(open("pkg/mod.py").read())
print([(n.lineno, ast.unparse(n.exc.args[0])[:60]) for n in ast.walk(t)
       if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call)
       and getattr(n.exc.func, "id", None) == "MyError"])
EOF

# 2. the independent read that keeps the derivation honest
grep -cE '^_[A-Z0-9_]+_HINT = ' pkg/mod.py

# 3. prove the OLD check was blind: add a member, run, expect green
pytest tests/test_antirot.py -q      # green with the new member present = stale

# 4. the sweep for the same reflex elsewhere
grep -rnE '^[A-Z][A-Z0-9_]+ = [([]' --include='*.py' . | head -40
```

## A derived set can go EMPTY, and that is worse than stale

A derivation that returns nothing makes every `for x in derived: assert ...`
loop pass vacuously. A stale literal at least still asserts something. Every
derived subject set needs a floor — `assert len(derived) >= N` with `N`
justified, or an explicit "this family is empty and here is why".

Worked instance and the shape of the floor:
`references/prose-lists-and-lying-derivations.md`.

## The list is often in PROSE, and prose is where it is least checkable

A carried next-step, an ADR, the "candidates" paragraph of the write-up that
found the defect: nobody treats those as anti-rot checks because they are not
checks, and the next change runs them as the work order. Round 482 measured
one — an eight-item remembered list against a derived crawl — and it was
wrong in BOTH directions: two members it waved through as already fine were
the two largest violations, and nine violators were on no list at all.

Two further ways a derivation lies, both from that round: the derivation
silently returns a SUBSET (an `id()`-keyed walk that drops its own objects; a
crawl budget reported as completeness), and a rule set derived from one known
failure finds that failure again.

Worked instances, code and the counts:
`references/prose-lists-and-lying-derivations.md`.

## You derived the MEMBERS. Did you derive the WITNESS? (round 488)

Deriving the subject set is half the job. The other half is the thing you
instantiate each member WITH, and it is usually still hand-written, because
it does not look like a list.

Whence's `reprsweep.py` audits every class it can REACH by crawling a live
object graph — no list of classes anywhere. It crawled that graph from
`PROBE`, fifteen hand-written lines. **7 of the language's 23 AST node
classes appeared in those lines**, so the crawl was exhaustive over one
program and read as exhaustive over the language, and the pinned-set test
guarding it was green on all nineteen classes it did reach. Four distinct
defects, all of which reported a CLEAN result:

1. **The fixture is the list.** Derive the generator, not just the roster:
   for each derived member, emit the input that constructs it, and assert
   the member is actually produced. "There is a line for it" is not the
   property — *the line constructs it* is. In this instance the emitted
   calls came from an argument-KIND table the tree already kept for another
   purpose, so 28 of 37 needed no hand-written entry.
2. **One arbitrary WITNESS per member.** The walk kept the FIRST object of
   each class it hit. For a property that varies *within* a member — a repr
   whose length depends on the identifier in it — the first witness you
   reach is not the one that violates. Symptom, and it is unmistakable:
   **you revert the fix and the check still passes.** Keep the extremum
   (longest, deepest, oldest), not the first.
3. **A derived witness row that constructs nothing.** Two rows of the value
   table ran before the row they depended on and bound a MISS; both classes
   were reached anyway by a second path and the sweep reported clean. Gate
   it: assert no generated binding is an error value. If one half of your
   generator has that gate (the builtin half did) and the other does not,
   that asymmetry is the bug report.
4. **A module-level fixture captured as a default argument.**
   `def reachable(source=PROBE, ...)` binds the string once at def time, so
   a caller who rebinds `module.PROBE` silently audits the old fixture and
   gets a plausible answer. `source=None` plus `source or PROBE`.

### A stress case varies ONE axis: the one the known failure was on

Same round, and it is where the live defects actually were. The rule under
audit read *"bounded, however large the VALUE is"*. Eleven hand-written
scale cases made the value large in every way anyone could think of — a
3,000-element list, a 400-key record, a 5,000-character string, a
60-parameter closure. Not one made a NAME large. Three renderings
interpolate an identifier, and all three were unbounded: **559 characters
for a scope holding one 400-character name, 442 for the value bound to it,
against a 240 cap.**

Both classes were the ones the rule had been written FOR, both had been
audited on every previous run, and both carried a written sentence asserting
their compliance — one in the constant's own comment, one in the shared
helper's docstring, both written by the round that introduced the rule.
Neither sentence was careless. Each was true of every input anybody had
built.

> **Widening the subject set and widening the stress case are different
> jobs. A rule set derived from one known failure varies the axis that
> failure was on; the coverage gap and the defect are usually not in the
> same place.**

Before you trust a "however large X is" claim, list the inputs that reach
the renderer and ask which of them the author sizes. Value, name, count,
depth, arity, path — each is an axis, and the cheap tell is that your
fixtures all vary the same one.

## The bounded exception: when a static reader needs your literal (round 477)

Step 3 says derive the subject set. There is exactly one condition under
which that is the wrong move, it is common in tooling repos, and it is cheap
to check before you act: **something else reads your literal statically.**

Worked example, and note that the prose was already right — this is not a
case of nobody having written the rule down. `corpus_check.py` described its
own test-runner check as:

```python
"unit_tests": "pytest over skills/*/scripts/test_*.py, whose tests drive "
              "the other checkers; …"
```

and its argv named **two** directories. The glob matched **fifteen files in
three**. The missing directory held 19 tests that nothing ran, and a later
round read the DESCRIPTION, declared the tool underneath it "wired" on the
strength of that sentence, and left an ERROR standing for two rounds.

The obvious fix is step 3: `glob.glob(...)` in place of the two literals.
**Measured, that fix is worse than the defect.** A separate tool
(`wiring_audit.py`) folds `os.path.join(root, "skills", "x", "scripts")` into
a graph edge and cannot fold a `glob` call — its own docstring names "a
`glob`" as a documented under-approximation. Making the argv derived:

| | before | after the "fix" |
|---|---|---|
| files in the invocation closure | 109 | **95** |
| `wired` declarations that became errors | 0 | **12** |
| the entry the edit existed to wire | reachable | **unreachable** |
| the drift test comparing argv to glob | can go red | **tautology** |

That last row is the one that would have gone unnoticed. Derive the argv from
the glob and the test comparing them asserts `glob == glob` — this skill's own
second pitfall ("deriving from the thing the check is about"), reached by
following this skill's own step 3.

### The move

**Keep the literal. Derive the oracle. Bind them with a test.**

1. **Ask who else reads the literal**, before touching it. `grep` for the
   directory names, then for the tools that could plausibly resolve them
   statically. In this repo the answer was one auditor and 24 registry
   entries downstream of it.
2. **Hoist the pattern into ONE constant** and build the prose FROM it, so
   the description cannot claim a pattern the oracle does not use:

   ```python
   SKILL_TEST_GLOB = os.path.join("skills", "*", "scripts", "test_*.py")

   def skill_test_dirs(root):
       """The ORACLE for the argv — deliberately not the argv."""
       return sorted({os.path.relpath(os.path.dirname(q), root)
                      for q in glob.glob(os.path.join(root, SKILL_TEST_GLOB))})

   RUNNER_CHECKS = {"unit_tests": "pytest over the directories that hold a "
                                  + SKILL_TEST_GLOB + " file — a LITERAL "
                                  "enumeration in `checks()`, held equal to "
                                  "that glob by test_corpus_check.py"}
   ```

3. **Assert set EQUALITY, not membership**, in both directions. A literal
   naming a directory with no members is as much a defect as a member the
   literal omits — the first is an argument that will start erroring the day
   the directory moves.
4. **Pin the static property too.** Assert that every element of the literal
   still resolves to a real edge in the other tool's graph, so the next round
   to "simplify" the enumeration into the glob its own description names
   fails with a message that says why. Assert the PROPERTY, not the absence
   of the string `glob`; that also covers the next clever way of losing it.
5. **Expect the falsifier to fire on you.** Round 477 wrote a new skill
   script with a test file, the family went from three to four, the equality
   test went red naming the new directory, and the argv gained it — inside
   the same round. That is the promise the prose description had been making
   for four rounds and could not keep.

### Do not generalise the detector past what it can decide

The tempting next step is a checker for every dead pattern in prose. Round
477 measured that corpus first: **61 distinct glob patterns that expand to
zero paths, 12 at a present-tense site — and 10 of those 12 sit in sentences
asserting the file does not exist** ("`knowledge/round-281-*.md`, and there
should not be one"). A dead glob is ambiguous between a rotted reference and
a correct absence claim, and absence claims won 10 to 3. The decidable rule
is narrower and worth having: *the pattern expands, the code names at least
one member of what it expands to, and the named set is a strict subset.*
`skills/derived-subject-set/scripts/pattern_vs_enum.py` is that rule; its
population on a clean tree is zero, which is why its enforcement rides in a
test rather than in a checker slot.

## Pitfalls

- **Deriving the roster and hand-writing the witness.** The members come
  off a live table and the inputs that instantiate them are still typed out,
  so the audit is exhaustive over the fixture and reads as exhaustive over
  the family. Ask what the derived set is instantiated WITH.
- **Keeping the first witness instead of the worst.** Fine when every member
  of a class behaves identically; wrong the moment a property varies with a
  field. The tell is a fix you cannot falsify.
- **Fixing the list instead of the mechanism.** Adding the eight missing
  members to the literal makes the suite green and leaves the ninth to the
  same fate. If the family can grow, derive it.
- **Deriving from the thing the check is about.** If the check is "every
  hint is owned by a rule", derive the hints from the *parser* and the
  owners from the *rule table* — never both from the same file, or the
  check asserts a tautology.
- **A derivation that reads a stale copy.** Reflecting over an imported
  module reads whatever is importable, which in a repo with a vendored or
  duplicated copy may not be the shipped one. Assert the module's
  `__file__` if there is any chance of two.
- **Losing the tombstone.** When a member moves from "exempt" to "covered",
  deleting its registry row erases the record that it moved. Keep the row
  with a marker and a test that it is now on the other side.
- **Assuming green-and-fast means checked.** Cheapness is not coverage. A
  millisecond test over a stale list is worse than a slow one over a live
  set, because its speed is what buys it trust.
- **Treating the crash and the green test as different problems.** A tool
  that dies with `ModuleNotFoundError` on a member missing from a
  hand-written `MODULES` tuple is the SAME defect as the green anti-rot
  test — one family, two literals, two symptoms. Fix them in one pass.
- **Deriving a set a static analyser also reads.** The round-477 case above:
  the derivation is invisible to the other tool, the graph shrinks, and
  declarations elsewhere in the repo become errors. Ask who reads the literal
  BEFORE replacing it, and if the answer is "an analyser", derive the oracle.
- **Believing a description that claims a derivation.** "pytest over
  `pkg/*/tests/*.py`" in a docstring is prose. Three separate path-checkers in
  this repo skip a glob-bearing token BY DESIGN — one truncates its match at
  the `*` and counts the token unchecked, one reads only `.json` prose, one
  folds no glob — so a pattern claim is the least-verified sentence a tooling
  repo can contain. Run the glob and diff it against the code.
- **Writing the tests as a mirror of the live tree.** Round 477's first draft
  of `test_pattern_vs_enum.py` asserted against the real `skills/` layout and
  broke within the hour, when the round's own new file grew the family from
  three to four. Build a synthetic root with a controlled family; keep exactly
  one live-tree assertion, as the enforcement.

## Verification

Run these against your own instance; the numbers are the Whence round-392
ones and are here as the SHAPE of an answer, not as values to expect.

```bash
# 0. the bounded exception (round 477), runnable in THIS repo
python3 -m pytest -q skills/skill-authoring/scripts/test_corpus_check.py \
    -k TestSkillTestDirs                       # 7 passed: argv == glob
python3 skills/derived-subject-set/scripts/pattern_vs_enum.py audit
                                               # pattern-vs-enum: 0 error(s)
python3 -m pytest -q \
    skills/derived-subject-set/scripts/test_pattern_vs_enum.py  # 21 passed
python3 skills/derived-subject-set/scripts/pattern_vs_enum.py census
       # 354 live, 61 dead; 12 dead patterns at a present-tense site (~60 s)

# 1. the derivation and an independent read agree, and both are pinned
python3 -m pytest tests/test_v34.py -k "derived_and_not_a_list" -q

# 2. every member is covered or carries a written reason, counts exact
python3 -m pytest tests/test_v34.py \
    -k "hinted_or_has_a_written_reason or no_stale_entries or seven_sites" -q

# 3. the promise the original docstring made, made true: a synthetic new
#    member must turn the check RED. Add one, run, expect failure, revert.
python3 -m pytest tests/test_v33.py -k "owned_by_a_cure_rule" -q

# 4. the sweep — every other hand-written subject set in the tree
grep -rnE '^[A-Z][A-Z0-9_]+ = [([]' --include='*.py' . | head -40

# 5. round 488: the WITNESS half. The manifest reports coverage of each
#    derived axis and exits 1 on a gap or a stale exception, so "how much
#    of the family does this audit actually instantiate" is a CLI line
#    rather than something you have to import the module to learn.
cd languages/whence && python3 reprsweep.py --manifest
       # derived probe: 23 node class(es) / 37 builtin(s) / 19 runtime class(es)
       # universe 42, reached 34, declared unreachable 8, gaps 0, stale
       #   exception(s) 0
python3 -m pytest -c pytest.ini -q tests/test_v48.py     # 65 passed
#    the falsifier: revert the fix in-process and the audit must name the
#    exact members it kills, or the witness selection is wrong
python3 -m pytest -c pytest.ini -q tests/test_v48.py \
    -k "reverting_the_three_reprs or worst_instance"      # 2 passed

# 5. round 482: the derived set is pinned as a SET, and the crawl that
#    produces it reports whether it FINISHED
cd languages/whence && .venv/bin/python reprsweep.py          # 19 classes, complete
cd languages/whence && .venv/bin/python -m pytest tests/test_v47.py -q \
    -k "reached_set or stops_at_the_edge or retain_every_object"   # 3 passed
```

You have done this when all of the following are true:

1. **The staleness was demonstrated, not inferred.** You have a recorded
   run in which the pre-fix check is green against a family member it does
   not know about (step 2).
2. **The derivation and an independent read agree**, and both numbers are
   pinned (step 5). Deleting the derivation's filter makes the count change.
3. **Every opt-out has a written reason**, and a test fails if a registry
   key stops being a live member (step 6).
4. **A synthetic new member fails the check.** Add one, run, see red,
   revert. This is the promise the original docstring made; make it true
   before writing it down again.
5. **The counts are exact**, not inequalities, on both the covered and the
   exempt side.
6. **The sweep is recorded** — which other hand-written subject sets you
   found, and for each, derived or annotated-as-closed with a reason.
7. **If the list was in prose, you said so in the diff.** A next-step, a
   doc or a decision write-up that named members is now either deleted or
   annotated as superseded by the derivation — otherwise the next change
   reads the stale list, which is the failure this skill is about, one
   layer up from the code.
8. **The derivation reports whether it finished**, and a test asserts that
   it did. A traversal that hit its budget, or one that lost objects to
   `id()` reuse, returns a subset and every property you assert over it
   holds vacuously.
9. **You asked who else reads the literal** before deriving it, and wrote
   down the answer. If an analyser does, you derived the ORACLE and pinned
   the static property (round 477's section above), and you can state the
   measured cost of the alternative rather than the reason you avoided it.

*Provenance: Whence round 392. `test_the_parsers_hint_constants_are_all_
owned_by_a_cure_rule` promised in its own docstring that "an eighth hint
added by a future round arrives here as a failure"; the round added eight
and the fast suite stayed green, because the test named four constants.
The same reflex had also killed `bench/ref_diff.py` — a hand-written
`MODULES` tuple that never gained a module added six rounds earlier, so
every invocation since had died on import before comparing anything. One
family, two literals, two symptoms.*
