---
name: evidence-must-name-its-subject
description: Use when a checker, linter, alert or audit reports a VERDICT together with the EVIDENCE it found — a matched line, an offending file:line, a "because:" string — and someone is about to act on the verdict. Symptoms; a finding whose quoted line is plainly about a different object than the finding names; a detector that returns the FIRST match and stops; a rejection rule that only rejects candidates naming someone else, so an anonymous candidate passes by default; a stale-record warning "fixed" from the summary without reading the excerpt; a suite that pins which findings fire and never pins what they cite; a red check carried for weeks because every reader read only the verdict. The move; read the evidence as a claim in its own right, ask whether it would establish the verdict if the verdict were unknown, and audit the evidence with a WIDER predicate than the detector's own filter. Covers surfacing skipped candidates, publishing attribution beside the verdict, and pricing the queue before choosing a severity.
---

# The verdict gets tested. The evidence does not.

A detector that reports `(verdict, evidence)` is making **two** claims:

* *this subject is in state X* — the verdict, which tests pin, which
  reviewers argue about, which drives the fix;
* *and here is the text that shows it* — the evidence, which nothing checks.

While the verdict is right, a broken evidence line is invisible. It is not
harmless: it is the **same** broken line that produces a clean false positive
the moment the verdict would have been "no". A detector whose evidence is
wrong is not a detector that is 95% right; it is a detector that has not been
observed failing yet.

```
The iron law:  an evidence line that does not name its subject
               is not evidence, even when the verdict is correct.
```

## The measured instance (round 489)

`carryforward_check.py`'s **K003** asks whether a prediction bank recorded
`unscored` has since been scored. It searches the round's own prose for a
scoring-shaped line, rejecting any line that credits another round, and
reports the first survivor.

For round 479 it reported, for four consecutive rounds:

> round 479: recorded `unscored`, but a scoring now reads as present
> (own/tally: `author); round 473's 17-row bank, scored **10 HIT / 6 MISS / 1`)

**The verdict was right.** Round 479's bank *had* been scored — by round 485,
in round 485's own file, and round 479's knowledge file even says so.

**The evidence was about round 473.** It is a sentence in which round 479
scores *somebody else's* bank. The rejection rule required the possessive to
be followed by `P<n>` or `prediction`; the corpus had written `bank`. Two
qualifier words and a synonym were the whole gap.

Nobody noticed for four rounds, because every reader read the verdict.

Had round 485 never scored that bank, the identical line would have produced
a **false positive**, and the prescribed repair — flip the ledger to
`scored` — would have recorded a scoring that never happened. The wrong
evidence was one coincidence away from writing a lie into the record.

## When to use (triggers)

- A finding, alert or lint message carries a quoted snippet, a `file:line`,
  a matched pattern or a "because" clause, and you are about to act on it.
- Writing or reviewing a detector that returns "the first match" — a
  `for … : return`, `next(...)`, `head -1`, `re.search` over a document.
- A rule of the form *reject if the candidate names someone else*: it is a
  negative filter, so anything anonymous passes by default.
- A check has been red for several review cycles and each reviewer acted on
  the summary line.
- Widening a matcher and wondering what the blast radius is.

**When NOT to use:** the detector reports no evidence at all (that is a
different, easier problem — make it report some); or the evidence is an
anchor citing the wrong *coordinate* while being the right text
(`matching-is-not-locating`).

## Steps

1. **Read the evidence line on its own, with the verdict covered.** Say out
   loud what object it is about. Outcome: a named subject, or the admission
   that you cannot tell — both are results.

2. **Run the counterfactual.** *If the verdict were unknown, would this line
   establish it?* If the answer needs a fact from outside the line, the line
   is not the evidence; something else is, and the detector has not shown it
   to you. Outcome: a yes/no written down beside the finding.

3. **Find the rejection rule and check its polarity.** Most evidence filters
   are *negative* — they discard a candidate that explicitly points
   elsewhere. Every anonymous candidate therefore survives. Outcome: the one
   line of code that decides, and a sentence naming what it lets through.

4. **Audit with a predicate WIDER than the detector's filter.** An auditor
   that reuses the detector's own rule can only agree with it. Use a coarser
   net — every identifier mentioned, not every identifier *credited* — and
   treat disagreement between net and filter as the review queue. Outcome: a
   count of subjects where the published evidence names something other than
   the subject.

5. **Surface the candidates the detector skipped.** Split the first-match
   loop into an enumerator plus a filter, so *rejected* candidates and the
   reason for each are reachable. Outcome: `<detector> --audit-evidence`
   (or equivalent) printing per subject: candidates, rejected, published.

6. **Publish the attribution beside the verdict.** When the published
   evidence names some other subject and never its own, say so *in the
   finding*. This is the only step with live consequence: it reaches the
   person about to act. Outcome: a test that the caveat appears, and a test
   that it does not appear on clean evidence.

7. **Price the queue before giving it a severity.** Hand-classify every row
   the wider net surfaces. A review queue at 33% precision is a queue, not
   an ERROR. Outcome: a published precision and an explicit severity
   decision. (Round 489: 9 of 143 surfaced, 3 genuinely wrong evidence, all
   9 on records the detector could not act on — so it shipped with no
   severity code at all, and the caveat carried the value.)

## Pitfalls

- **Fixing the filter moves the wrong evidence; it does not make the
  evidence right.** After round 489 widened the rejection rule, round 479's
  published evidence became `| debt | outcome |` — a markdown table with an
  "outcome" column, from a section about cross-track debts. Still not a
  scoring. A first-match detector always has a next candidate.

- **The evidence is a function of DOCUMENT ORDER, and nothing says so.**
  "First match" means the line that happens to appear earliest. Insert a
  paragraph at the top of the subject's file and the published evidence
  changes with no change to the subject's state.

- **A negative filter has no floor.** *Reject if it credits another subject*
  accepts a line crediting nobody — which is most prose. State the rule as
  what it admits, not what it blocks, and the gap is obvious.

- **Widening a matcher breaks the case that already worked.** Round 489
  allowed qualifier words before the noun and added a word-boundary escape
  after a single-digit prediction-id alternative. One digit is all that
  alternative matches, so `P14` stopped matching and every two-digit foreign
  attribution was silently re-admitted. Caught only because an existing
  frozen fixture was re-run. Re-run the old cases *in the same command* as
  the new one.

- **"The verdict is right, so the finding is fine."** The verdict being
  right is what makes the evidence bug undetectable. Treat a correct verdict
  with unrelated evidence as a *bug report about the detector*, not as a
  finding to close.

- **Measuring the blast radius of a matcher change with the matcher.** Run
  the audit twice — once with the old predicate monkeypatched back in — and
  diff the published evidence per subject. Round 489's widening changed 1
  of 165. A number that small is only believable because it was measured
  both ways.

## Verification

```bash
# 1. The detector can show its rejected candidates at all.
python3 skills/skill-authoring/scripts/carryforward_check.py --audit-evidence | tail -1
# expected: "evidence-audit: N bank(s), M with evidence, K foreign line(s)
#            rejected, S SUSPECT [...]"   -- K and S both reachable

# 2. The wider net and the filter disagree somewhere, i.e. the audit is not
#    just the detector wearing a hat.
python3 skills/skill-authoring/scripts/carryforward_check.py --audit-evidence \
  | grep -c SUSPECT
# expected: >= 2 at round 489 it prints 10 -- the 9 flagged rows plus the
#           summary line, which also carries the word. 1 means only the
#           summary matched, i.e. the auditor shares the detector's predicate.

# 3. The live invariant: no record the detector CAN act on publishes
#    evidence about a different subject.
python3 -m pytest skills/skill-authoring/scripts/test_carryforward_check.py \
  -k "EvidenceAudit or EvidenceAttribution or K003Publishes" -q
# expected: all pass

# 4. The frozen regressions still hold after any matcher change.
python3 -m pytest skills/skill-authoring/scripts/test_carryforward_check.py \
  -k "ScannerRegressions or widening" -q
# expected: all pass
```

- [ ] the evidence line was read with the verdict covered (step 1)
- [ ] the rejection rule is stated as what it ADMITS (step 3)
- [ ] the auditing predicate is wider than the detector's (step 4)
- [ ] the queue's precision is published before any severity is chosen (7)
- [ ] the matcher change's blast radius was measured both ways
