---
name: pointer-is-not-the-evidence
description: Use when a checker decides an obligation was DISCHARGED by pattern-matching prose -- was this prediction bank scored, was this incident post-mortemed, does this ADR record a decision -- and the prose it matches may be a POINTER rather than the thing. Symptoms: a record saying "scored in §10", "see the RCA", "documented below" whose target does not exist; a scanner with a rich vocabulary for "was NOT done" and none for "was done OVER THERE"; a suggest or autofix mode proposing an item be marked complete, quoting the sentence that PROMISES the completion; a green checker on an item whose evidence nobody has opened. Covers separating a promise from a deed, resolving the pointer before accepting it, keeping the veto fail-safe for a DEBT tracker, publishing vetoed candidates rather than dropping them, and re-scanning after the fix because one bad filter masks the next. NOT for a quote matching in the wrong file (matching-is-not-locating) or an obligation with no detector at all (obligation-ledger).
---

# A pointer to the evidence is not the evidence

A checker that asks *did somebody do X?* by scanning prose is really asking
*does this text contain the vocabulary people use when they have done X?*
Those are different questions, and the gap between them has a specific,
recurring shape: **the vocabulary of doing X and the vocabulary of saying
where X was done are the same words.**

    Scored in §10.                    <- no §10 was ever written
    Full RCA in the incident doc.     <- the doc was never created
    See the appendix for the numbers. <- there is no appendix

Each of those sentences *is* a claim that the work happened. None of them is
the work. A scanner built from a frequency count over text written by people
who did the work will match all three, because people who did the work write
sentences exactly like these — and so do people who meant to.

The tell is asymmetric vocabulary. Nearly every such scanner grows a negation
list early, because "we never scored this" is a sentence the corpus writes
often and misreading it is loud and embarrassing. Almost none grows a
*pointer* list, because misreading a promise is silent: it marks an item
complete, the item stops being reported, and nobody looks at it again. The
error mode that gets fixed is the one that makes noise.

## When this triggers

- A completeness checker reports green and its evidence is a sentence you
  have not followed to its target.
- A scanner has a `NEGATION_RE` / "not done" pattern list and nothing
  symmetric for "done elsewhere".
- A `--suggest`, `--fix` or autofix mode proposes recording an item as
  complete, and the quote it offers contains a section number, a file name,
  or the words *see*, *below*, *above*, *in the*.
- A record cites its evidence by location rather than by content.
- An obligation is discharged in two phases and the second phase's artifact
  is *cross-referenced* rather than inlined.
- You just repaired an evidence filter. Re-run before believing the result:
  a bad filter high in the chain hides whatever is under it.

## Steps

1. **Find the vocabulary asymmetry.** List the patterns the scanner accepts
   as evidence, and the patterns it rejects. If there is a negation list and
   no pointer list, you have found the gap without running anything.

2. **Enumerate the pointer forms your corpus actually uses.** Do not invent
   them. Grep the prose for the accepted patterns and read the matches by
   hand — the promises stand out immediately because they carry no outcome.
   Typical: `§N`, `section N`, `see X`, `below`, `above`, `in <file>`.

3. **Add a verdict-on-the-line escape hatch FIRST.** A real record often
   points at where the rest of it lives: *"13 HIT / 1 MISS of 15 (P14 in
   §10)"* is a scoring that also happens to be a pointer. If the line carries
   its own outcome, it is the deed; stop. Without this guard the new rule
   throws away real evidence for mentioning a cross-reference, which is a
   worse bug than the one you are fixing.

4. **Resolve the pointer.** A pointer is evidence only if its target exists.
   Section numbers resolve against headings in the same document; file
   references resolve against the filesystem. If it resolves, accept and fall
   through to the existing logic — the rule is about resolution, not about
   the word.

5. **Choose the veto's direction deliberately, and say why in the code.**
   For a DEBT tracker the fail-safe direction is to find LESS evidence: an
   unresolvable pointer means the item stays open, stays visible, and someone
   looks again. Prefer accidental acceptance over accidental rejection only
   when the checker's error mode is *nagging*; prefer the reverse when it is
   *forgetting*. Resolve against whatever context you actually have and note
   that a false ACCEPT merely restores the old behaviour.

6. **Publish what you vetoed.** A filter nobody can enumerate is a filter
   nobody can check. Count the vetoes per item and expose them through
   whatever audit mode already exists, with the offending line. If there is
   no audit mode, the count belongs in the summary line.

7. **Re-run the whole scan and read the NEW evidence for the same items.**
   This is the step people skip. Removing the top filter promotes the next
   candidate, which has never been looked at by anyone.

8. **Record the adjudication where the checker will re-derive it**, naming
   the round/PR that inspected it, what the target was, and that it was
   absent. "Unscored" with a reason outlives "unscored".

## Pitfalls

- **Fixing the promise instead of the record.** The temptation on finding
  *"Scored in §10"* with no §10 is to write §10. You cannot: you would be
  authoring the verdicts, and a bank scored after the results are known is
  not scored. Record the debt honestly and give it an owner.

- **Trusting the suggester you just fixed.** A `--suggest` mode is a
  hypothesis generator. Re-derive every field it proposes. In the episode
  behind this skill, `--suggest` offered three entries, two good and one that
  would have laundered a real debt into a recorded discharge.

- **Assuming one fix is the fix.** Repairing the pointer rule immediately
  exposed a second false positive that had been masked by it — a scoring
  table row whose subject was the *table owner's* item id, mentioning
  another item in a description cell. Two independent defects, same symptom,
  and only the second was visible after the first was gone.

- **Letting the new rule reach the wrong scope.** A veto designed for
  cross-reference evidence must not apply to an item's own record. Gate it on
  the same flag that distinguishes the two paths, and test both directions.

- **The recursion.** The registry where you record a broken pointer will
  itself contain that broken pointer, and a checker over that registry will
  flag it. Either declare a named blind spot for the recording surface, or
  refer to the target by coordinate rather than spelling it. Do not silently
  exempt the registry.

## Verification

```bash
# 1. the rule fires on an unresolvable pointer, stays silent on a resolvable
#    one, never vetoes a line carrying its own verdict, and does not reach
#    the item's own scope; plus the second defect the fix uncovered
python3 -m pytest -q \
  skills/skill-authoring/scripts/test_carryforward_check.py \
  -k "PointerToAScoring or TableRowScores or SuggestIsHonest"

# 2. the suggester now tells the truth about the bank that was never scored
python3 skills/skill-authoring/scripts/carryforward_check.py --suggest

# 3. every vetoed candidate is published rather than dropped
python3 skills/skill-authoring/scripts/carryforward_check.py --audit-evidence
```

Expected: the `-k` selection is green; `--suggest` proposes
`"status": "unscored"` for round 492 (it proposed `"scored"` before the fix,
quoting `Scored in §10.` from a file that ends at §9); `--audit-evidence`
carries a `rejected_unkept_pointer` count.

Worked example and both defects in full:
`knowledge/round-495-a-pointer-to-a-scoring-is-not-a-scoring.md`.
