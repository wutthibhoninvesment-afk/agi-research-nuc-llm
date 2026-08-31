---
name: derived-subject-set
description: Use when an anti-rot test is green and you are about to trust that green — a test asserting "every X is registered/owned/covered", a schema-vs-code consistency check, an exhaustiveness list, a fixture registry. Symptoms: the check's LEFT-HAND SIDE is a literal in the test (a list of constants, a hard-coded count, an enum copied by hand) while its right-hand side is the real artefact; a docstring promises "a new X arrives here as a failure" and nobody has added an X since; a new member of the family shipped and the suite never went red; a tool dies on a member missing from a hand-written MODULES tuple. The move is to DERIVE the subject set from the artefact (AST, module namespace, directory listing, DB catalogue) so membership is a fact not a memory, then cross-check it against an independent read so it cannot silently shrink. NOT for a checker nothing invokes (unrun-checker-latency), a rule with no tool (unenforced-documented-rule), or a rolling prose claim (carried-claim-rot).
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

## A derived set can go EMPTY, and that is worse than stale (round 395)

Deriving the set is necessary and not sufficient. The derivation reads an
**artefact**, and it is really reading a *proxy for a fact*; when the proxy's
meaning changes without the fact changing, the set does not go stale, it goes
**empty**.

Worked example. `curecheck.field_programs()` selected "the programs a separate
system leaves in `examples/`" with

```python
subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "examples"])
```

— untracked status, derived from git, with an explicit argument in its own
docstring for why a hand-written list would be worse. Three rounds later a
`git add -A` sweep tracked all fourteen files. Not one byte of any file
changed. The selector returned `[]`.

What that costs, and why it is worse than a stale list:

| | stale set | empty set |
|---|---|---|
| `assert all(P(x) for x in S)` | fails on the item it missed | **vacuously true** |
| `assert len(S) == N` | fails, naming the extra item | fails, naming `0 == N` |
| `S["known_member"]` | works | `KeyError`, naming the member not the cause |

Two of the four tests that broke here were the vacuous kind's siblings and
two were the loud kind, and **none of the four failure messages contained the
word "empty" or the name of the selector.**

The moves:

1. **Name the fact, then ask whether the artefact is the fact or a proxy for
   it.** "Written by another system" is the fact; "untracked" is a proxy, and
   proxies are what other people's commits change.
2. **Prefer a declaration the repo already has over a fresh proxy.** Here a
   frozen census (`state/whence/round-384/field-names.json`) had listed the
   fourteen names for eleven rounds and a *different* guard already trusted
   it. Reading it is not "a hand-written list": it is the existing
   declaration, read instead of re-derived from something weaker.
3. **Keep the live derivation as a REPORT, not as the source.** The original
   argument — "if the gateway adds a program tomorrow this picks it up" — is
   real and worth keeping. It became `field_corpus_drift()`, which returns
   `(undeclared, missing)`. The property survives; the failure mode does not.
4. **Assert non-emptiness at the derivation, not at the assertion sites.** A
   selector that can legitimately return zero should say so; one that cannot
   should raise there, where the message can name the selector.

## Pitfalls

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

## Verification

Run these against your own instance; the numbers are the Whence round-392
ones and are here as the SHAPE of an answer, not as values to expect.

```bash
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

*Provenance: Whence round 392. `test_the_parsers_hint_constants_are_all_
owned_by_a_cure_rule` promised in its own docstring that "an eighth hint
added by a future round arrives here as a failure"; the round added eight
and the fast suite stayed green, because the test named four constants.
The same reflex had also killed `bench/ref_diff.py` — a hand-written
`MODULES` tuple that never gained a module added six rounds earlier, so
every invocation since had died on import before comparing anything. One
family, two literals, two symptoms.*
