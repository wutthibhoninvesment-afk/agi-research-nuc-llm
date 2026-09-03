---
name: coverage-keyed-by-witness
description: Before publishing "this check/diagnostic/rule covers N% of X", test whether the ratio is a property of X at all — re-run it against a second input that differs from the first only in one value's type or shape. If the verdict flips, the number must be keyed by that input, and the report must also carry the ceiling (what the mechanism cannot reach even in principle) and the residual class it cannot see at all. Use when taking a coverage/hit-rate/recall number for a linter, a diagnostic, an error message, a validator, or a test suite.
---

# Coverage is keyed by its witness

## When this triggers

Any two of these, together:

1. You are about to publish a ratio of the form *"the check catches N of M
   bad cases"* — coverage, recall, hit rate, kill rate, detection rate.
2. The M is enumerated by YOU: you picked the inputs the check is measured
   against (a table of fixtures, a set of mutants, a witness call, a corpus
   sample). Nothing outside the code chose them.
3. The check works by classifying inputs — types, kinds, shapes, schemas,
   patterns — rather than by executing them to a known answer.

The tell that this has already gone wrong: **a report that names the subject
and not the input.** `coverage(fold) = 0.8`. `recall(parser) = 62%`.
`kill rate for test_x.py = 3/5`. If the sentence has one noun where the
measurement had two, the second noun was silently averaged away.

## Why one number is the bug

A classifier-based check can only see distinctions its classifier draws. Two
inputs that differ *only* in a value's type can therefore land on opposite
verdicts with no code change between them:

    note("tag", 5)       wrong order caught, and the message names the fix
    note("tag", "five")  wrong order INVISIBLE — both orders type-check,
                         the function cannot tell, the program silently
                         gets the wrong answer

Same function, same arity, coverage 1.00 and 0.00. **`coverage(note)` is a
number that does not exist.** Whichever witness the author happened to type
becomes the published property of the subject.

The same shape appears wherever the classifier is coarser than the failure:
a schema validator measured on records whose fields are all distinct types;
a mutation score measured on a sample stride that skips the mutants a test
does kill; a linter's recall measured on the fixtures its own author wrote.

## Steps

1. **Write the metric down before taking it**, including what counts as one
   trial and what the denominator is. Put it in the instrument's docstring,
   not only in a note somebody has to find.
2. **Name the input explicitly and give it an id.** Every row of the report
   is `(subject, witness)`. Refuse to emit a row keyed on the subject alone
   — it is not a shorter form of the truth, it is a different claim.
3. **Add a SECOND witness per subject that differs in exactly one value's
   type or shape**, chosen so the classifier can no longer distinguish the
   cases. This is the whole test. One such pair is enough to settle whether
   the ratio is a property of the subject.
4. **Compute the CEILING alongside the ratio.** Ask the classifier directly:
   for how many of the M trials does it already regard the bad input as
   acceptable? Those are unreachable by construction — no amount of work on
   the check can convert them. Report `hit / M` and `(M - unreachable) / M`
   side by side. A coverage number without its ceiling reads as a to-do list
   for work that cannot be done.
5. **Classify the misses into REACHABLE and STRUCTURAL, and count the class
   the mechanism cannot see at all.** In a check built on failures, that is
   the set of bad inputs that produce no failure — the wrong answer returned
   quietly. It is routinely larger than the gap you were asked about, and it
   is the number to lead with.
6. **Freeze the pre-fix report to disk before changing anything.** The
   before/after is the evidence that a fix moved what it claimed to; without
   it the after-number is unfalsifiable.
7. **Land the instrument as a module with tests, not as a script you ran
   once.** The next reader must be able to re-derive the number rather than
   quote yours. Assert the ceiling as a PROPERTY (`no unreachable trial is
   ever counted as a hit`), not only as a count — a count can be made
   vacuously true by editing the classifier.
8. **Add the population check.** Derive the subject list from the live code,
   not from a literal, and fail when a subject has no witness. A subject
   added later then joins the population by existing.
9. **Say what you did not measure.** If the witness table is 24 rows you
   wrote in one sitting, every number is conditional on it, and the counts of
   the silent-failure class are FLOORS rather than counts.

## Pitfalls

- **Widening the witness table after seeing the number.** Adding witnesses
  legitimately finds new rows and illegitimately moves a ratio. Say, before
  running, which one you are doing — and if a witness is added because a
  prediction about a named subject was refuted, land it as follow-up evidence
  with that history attached, not silently into the pre-registered table.
- **A witness that does not work in the correct order.** If the baseline call
  itself fails, every permutation of it fails for the wrong reason and the
  ratio inflates. Assert that each witness succeeds before permuting it.
- **Reporting only the fixed number.** The interesting number is usually the
  one nobody asked for. Lead with the class the mechanism cannot see.
- **Believing the gap is worth closing.** Some misses are bounded by a
  contract elsewhere (a function that is total by design can never emit a
  failure-borne diagnostic). Record those as bounds; do not "fix" them into a
  contract violation.
- **The instrument's own artefacts join the corpus it measures.** If you add
  a test file, the repo's censuses of the test corpus will move. Run them —
  they frequently improve the new artefact rather than merely counting it.

## Verification

Applied in `languages/whence/orderhint.py` (round 480), which measures the
coverage of the Whence interpreter's argument-order hint. Reproduce:

```
cd languages/whence
.venv/bin/python orderhint.py
.venv/bin/python -m pytest -q tests/test_v46.py
```

The census prints per-`(builtin, witness)` rows, then a pooled line of the
shape this skill asks for:

```
POOLED  hinted 30/40 = 0.750   ceiling 0.775   reachable gap 1
        silently wrong answers (ACCEPTED_DIFF): 7
```

Step 3 is the two `note` rows: `str-num` coverage 1.00 / `kind_blind` 0
against `both-str` coverage 0.00 / `kind_blind` 1, pinned by
`test_v46.py::test_the_ratio_is_a_property_of_the_witness_not_of_the_builtin`.
Step 4's ceiling is pinned as a property by
`test_no_kind_blind_permutation_is_ever_hinted`, and step 5's class by
`test_the_silent_wrong_answer_class_is_the_bigger_hazard` — seven rows
against a reachable gap of one. Step 6's frozen pre-fix report is
`state/whence/round-480/orderhint-baseline.json` (`hinted 29/40`).
Re-run rather than quoting these: the pooled number moves whenever a builtin
signature or a witness changes, which is the point of landing it as a module.
