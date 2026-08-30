---
name: unenforced-documented-rule
description: Use when a system's own documentation states a REQUIREMENT its implementation never checks — a spec sentence, a module docstring, a README grammar summary — and violating inputs are quietly accepted. Symptoms: a docstring says "X are Y-separated" / "must" / "always" / "only", and the smallest violating input parses or validates fine; a bug report that cannot be diagnosed where the mistake is, because a permissive rule swallowed the evidence and the error surfaces several tokens later; a comment claiming "no legal input starts with A B" that is only true of one special case; a reference/guest implementation agreeing with the real one because BOTH are permissive. Covers turning requirement sentences into falsifiable probes, measuring the corpus before tightening, deriving the fire set from the code so the new refusal cannot shadow a better existing diagnosis, finding the tests that DEPEND on the laxity, and mirroring into every implementation.
---

# Enforcing a rule the documentation already states

A rule can be written down and unenforced for a long time without anyone
noticing, because the documentation is *right* and the implementation is
*permissive*: every conforming input behaves exactly as documented, so no
test, no user and no reviewer is ever in a position to see the gap. It shows
up indirectly — as a bug report that cannot be diagnosed at the mistake,
because the permissive rule absorbed the evidence before any diagnosis ran.

Enforcing it is usually the SMALLER system, not the larger one: nothing is
added, one permission is withdrawn. The work is almost entirely in the two
questions the withdrawal raises — who was relying on it, and what better
error does the new refusal shadow.

## When to use (triggers)

- A spec / docstring / README states a requirement ("statements are
  newline-separated", "keys must be unique", "the header is required") and
  nobody has checked the implementation refuses violations.
- A diagnosis lands several tokens, fields or lines away from the mistake
  and the reason is "the grammar accepted it".
- A comment asserts an invariant about legal inputs that is only true of a
  special case ("no other legal statement starts with two names").
- Someone proposes fixing user confusion by rewriting the docs, or by
  auto-repairing users' inputs, when the docs were already correct.
- A reference/guest implementation and the real one agree on an input both
  should reject.

**When NOT to use:** the doc describes behaviour that has since changed
(that is a stale claim — re-derive the claim, don't tighten the code); the
rule was never documented and you are inventing validation; the "rule" is a
style preference with no downstream diagnosis riding on it.

## Steps

1. **Harvest requirement sentences into probes.** Grep the system's own
   prose for declarative shape — `must`, `required`, `always`, `only`,
   `never`, `are <X>-separated`, `exactly one`. Take module docstrings and
   header comments as seriously as the spec; they are usually older and
   more precise. For each sentence write the SMALLEST input that violates
   it and run it.

   ```bash
   grep -rniE "\bmust\b|\brequired\b|\balways\b|\bonly\b|\bnever\b|-separated" \
        SPEC.md src/*.py | head -40
   ```

   Outcome: a list of (sentence, violating input, accepted?/refused?). Every
   `accepted` row is an unenforced rule. Stop here and report if there are
   several — each is its own change.

2. **Measure the corpus before deciding to enforce.** Run the violating-input
   check over every artefact the project owns, and count. This is the number
   that decides whether enforcement is a tightening or a rewrite, and it is
   cheap:

   ```python
   for path in tracked_files():          # ask the VCS, not the directory
       try:    parse(open(path).read()); ok += 1
       except: print(path, "relies on the laxity"); bad += 1
   ```

   Enumerate from version control (`git ls-files`), not a directory scan —
   a directory can hold another system's files, and their count must not
   become a fact about yours. 15-of-16 conforming says the rule already
   describes how the system is written; 4-of-16 says you are proposing a
   migration and should say so.

3. **Define the DEFERENCE set before writing the check.** A new refusal
   fires on inputs that previously reached some *other* code path with its
   own, more specific error. Enumerate the inputs the new rule must NOT
   claim, and make the check fall through for them.

   The rule of thumb: refuse only when the offending input could legitimately
   have been the thing the new rule is about. Everything else is not "a
   missing separator" — it is a token/field/value that can never be valid
   there at all, and it must keep the message it already had.

   ```python
   # fires only for a token that could actually START a statement;
   # `x = 2` keeps its "Whence has no assignment" hint instead
   if started and not separated and _starts_statement(self.peek()):
       raise ParseError(...)
   ```

4. **Derive the fire set from the code, then pin the derivation.** The set in
   step 3 is a cache of something the implementation already knows. Write a
   test that re-derives it exhaustively over every input class and compares:

   ```python
   def _empirically_in_set(text):
       """True iff the parser will try to build a statement out of `text`."""
       try:    parse(text + "\n"); return True
       except ParseError as e:
           return not str(e).startswith("unexpected %r" % value)

   for text, value in every_token():          # all 40 of them
       assert _empirically_in_set(text) == (text in DECLARED_SET)
   ```

   Without this the check silently stops firing the moment the grammar gives
   some input a new role, and the symptom is invisible: the input goes back
   to being accepted.

5. **Find what DEPENDS on the laxity — usually a test, not a user.** Run the
   whole suite and read every failure as a question: is this artefact
   relying on the permission, and what property did it actually need?

   The common answer is that the dependent needed something *weaker* than
   the laxity and reached for it because the laxity was free. Preserve the
   weaker property directly.

   > A tail-vs-lifted differential rewrote `f()` to `let t = f()  t` on the
   > SAME line so both forms reported the same line number. The mandatory
   > separator forbids the one-line spelling — but the oracle needed line
   > ALIGNMENT, not one-line-ness. Padding the untransformed form with a
   > blank line restored alignment exactly, and the differential lost
   > nothing. Then pin the alignment, which until now was self-evident from
   > the source and is now an assumption.

6. **Mirror into every implementation, and fix the copy-identity bounds.** A
   reference implementation, guest evaluator, mock, or second parser must
   gain the same rule. If a test asserts one file's section is byte-identical
   to another's, the line bounds move — update them and say what grew, in the
   same comment that records every previous growth.

7. **Update the old permission's own regression test rather than deleting
   it.** If a previous cycle pinned the laxity as a known property, that test
   is where the decision was recorded. Rewrite it to assert the refusal *and*
   the diagnosis the input now gets; deleting it destroys the evidence for
   why the change was made.

8. **Document the honest limit.** Almost every tightening has inputs it
   cannot reach, because an earlier stage consumes them first. Enumerate
   them, write a test that pins the accepted behaviour, and put the list in
   the spec — an unwritten limit is discovered later as a bug.

   > `-`, `(` and `[` both start a statement and continue an expression, so
   > `let a = 1 -2` is one statement binding `-1` and no separator error is
   > possible. Three tokens, named, rather than a claim of totality.

## Pitfalls

- **The new refusal shadows a better error.** The most specific diagnosis a
  system has is usually the newest one, and a check inserted *earlier* in
  the pipeline silently outranks it. Symptom: an existing regression test
  for the good message starts asserting your new message instead. That test
  going red is the signal — do not update it to match; add the deference of
  step 3.
- **Enumerating the corpus with a directory scan.** `glob("examples/*")`
  counts files another process left there; the resulting rule is partly
  about a directory you do not own. Ask version control.
- **A count or line number baked into an assertion.** Tightening moves
  things: an example gains lines, an in-language check count goes 109 → 112,
  an error's reported line shifts by one. Derive the number from the source
  in the test (`lines.index(...) + 1`) rather than restating it, or the next
  change makes the test a puzzle.
- **Believing an invariant comment.** "No other legal input starts with A B"
  is often true only of the one special case its author had in mind, and
  false in general precisely BECAUSE of the laxity. Enforcing the rule can
  make such a comment true for the first time — check, and say so.
- **A mutation-testing script killed by a timeout leaves a mutant in the
  tree.** `try/finally` does not run on SIGTERM. Snapshot the files to a
  temp dir and write a standalone `restore.sh` *before* the first mutation,
  and scope each mutant's test run so the whole sweep fits the timeout.
- **Only checking the real implementation.** Guest/reference implementations
  are where the laxity survives; their own self-tests may even ASSERT it
  ("two statements with no separator both parse"). Grep the mirror for the
  rule's own words before assuming it is unaffected.

## Verification

Run all of these; each must produce the stated shape of output.

```bash
# 1. every artefact the project owns still conforms (enumerated from VCS)
python3 - <<'PY'
# ... parse each `git ls-files` artefact ...
PY
# expect: "N tracked: N parse, 0 fail"

# 2. the fire-set derivation, exhaustive
pytest -q -k "classified_by_whether"        # expect: passed

# 3. the deference cases keep their old messages
pytest -q -k "keeps_its_own_diagnosis"      # expect: passed

# 4. every refusal is a MISSING <rule> and nothing else: inserting the
#    thing the error asks for makes the identical input valid
pytest -q -k "parses_once_the"              # expect: passed

# 5. mutation: each new pin dies when its code is reverted
bash restore.sh && python3 mutate.py        # expect: 0 SURVIVED
```

Checklist:

- [ ] Every requirement sentence harvested in step 1 is either enforced or
      recorded as deliberately unenforced with its reason.
- [ ] Corpus count reported (`X of Y artefacts already conformed`).
- [ ] The fire set is re-derived by a test, not restated by a comment.
- [ ] Each dependent found in step 5 kept the property it actually needed,
      and that property is now asserted rather than inferred.
- [ ] Every implementation (real + reference/guest) refuses the same inputs;
      wording differences are pinned as deliberate if they exist.
- [ ] The honest limit is enumerated, tested, and in the spec.
