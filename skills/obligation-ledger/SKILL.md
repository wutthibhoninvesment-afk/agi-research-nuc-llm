---
name: obligation-ledger
description: Use when a process rule has TWO halves, do A then later do B about A, and only A leaves an artifact, so nobody can tell which Bs were done: predictions banked then scored, an incident owed a postmortem, an ADR or RFC owed a decision record, a migration owed a rollback drill. Symptoms: the obligation is checked by no tool; the A-artifacts sit under several naming conventions in different directories because no registry forced one; the debt is discussed in prose then falls out of the next revision; handed-over work has its code picked up while its open questions are dropped. Covers sweeping by FILENAME PATTERN not known locations, hand-adjudicating once into a declared ledger of who discharged each item and with what sentence, and making an artifact with no ledger entry the error. The question is WHICH ITEMS ARE OWED, not whether an ID resolves (citation-registry-integrity), whether a rolling doc's items went stale (carried-claim-rot), or whether an existing checker runs (unrun-checker-latency).
---

# An obligation whose second half leaves nothing behind

Plenty of process rules are shaped *do A, then later do B about A*:

| A leaves an artifact | B leaves | rule |
|---|---|---|
| a predictions file | a tally, somewhere in prose | bank before measuring, score honestly |
| an incident ticket | a postmortem doc, eventually | every SEV gets an RCA |
| an RFC | a decision record | no RFC merges undecided |
| a migration plan | a rollback drill | every migration is reversible |
| a perf claim | a re-run | claims expire |

A is auditable: the file is on disk, dated, in git. **B is not.** It lands as
a sentence in a document about something else, in whatever words that day's
author chose, and nothing anywhere pairs it back to its A. So the debt is
invisible in both directions — you cannot list what is owed, and you cannot
prove what was paid.

This is not the same as a rule nobody enforces. The rule here is *followed*,
visibly, half the time, which is exactly what makes the gap survive: every
audit finds a corpus full of correctly banked artifacts and concludes the
practice is healthy.

## When to use this (triggers)

- A process document states an obligation with a "then" in it, and you cannot
  name the tool that checks the "then".
- The A-artifacts live under more than one naming convention, or in more than
  one top-level directory. **This is the strongest single signal.** A
  registry forces one convention; the absence of a registry is what let three
  grow, and it means no list of "the places these live" is complete.
- Work gets interrupted or handed over, and the successor picks up the code
  while the conclusions evaporate.
- The debt has been *discussed* — "carried as a next step for team X" — in a
  document whose next revision does not mention it.

## Steps

1. **Sweep the whole repo by filename pattern. Do not enumerate locations.**
   Walk the tree, match names against the artifact's word (`prediction`,
   `postmortem`, `rfc`), skip vendored trees, and extract the key (round,
   ticket, ADR number) from the WHOLE relative path — some conventions put it
   in the filename and some in a directory. Read the worktree, not
   `git ls-files`: an obligation belongs to the work, not to the file's
   tracked-ness, and gitignored trees hold real artifacts.
2. **Publish the convention count.** If the sweep finds N naming conventions,
   say N out loud in the finding. It is the measurement that explains why
   nobody could enumerate the debt before, and it is the argument for the
   ledger.
3. **Write a first-pass prose scanner and DO NOT TRUST IT.** Grep the corpus
   for how discharges are actually phrased — a frequency count over the real
   text, not invented patterns. Use it to propose, never to conclude.
4. **Hand-adjudicate every artifact, once.** For each A, find the sentence
   that discharged it, or establish that none exists. Budget for this; it is
   the round's real work and it is not automatable, which is the whole point.
5. **Write the ledger as a declared file**, one entry per artifact:
   `status` (discharged / owed), and for discharged, WHO discharged it, in
   WHICH file, and a QUOTE that must still be findable there. For owed, an
   `owner` and a `why`.
6. **Re-derive, never trust.** The checker re-reads each cited file and looks
   for the quote. A ledger of claims is exactly the kind of document that
   goes stale silently; a ledger nobody re-executes is the problem wearing a
   different hat.
7. **Make an artifact with NO ledger entry the ERROR.** This is what makes
   the scheme robust to a seventh naming convention appearing next year: the
   sweep finds the file, the ledger has no entry, the check goes red. The
   ledger is the record; the sweep is the authority.
8. **Record a `remainder` for partial discharges.** A discharge that names
   the sub-items it did *not* reach is common and honest; capture it as a
   field and raise it as a WARNING. Erasing it makes a partial look complete.
9. **Warnings never set the exit code.** Age-of-debt and partial-discharge
   are warnings whose COUNT rides in the summary line. A check that goes FAIL
   every cycle for a debt the team decided to carry gets ignored and then
   uninstalled.
10. **Wire it into whatever already runs**, in the same invocation as the
    other checks. A new obligation-checker that is itself only run by
    convention has reproduced its own subject.

## Pitfalls

- **Enumerating from the places you already know about.** The first draft of
  this technique globbed four patterns under one directory and missed a
  fifth convention in a sibling directory, which made four correctly-banked
  items read as never banked. An obligation nobody registered cannot be
  enumerated from a list of known locations — that is the same reasoning
  error the obligation is made of. Sweep by pattern.
- **Believing a prose classifier.** A hand-check of the first scanner's 13
  findings found 5 wrong, in both directions, from four independent causes:
  a case-sensitive verdict word (the author wrote "hit", not "HIT"); three
  items discharged in ONE sentence, which no per-item pattern reached; a
  document quoting a *different* item's discharge inside its own section; and
  one negation word ("unscorable") vetoing four real verdicts on the same
  line. Each fix is one line, and fixing them one at a time is over-fitting.
- **Scoping the negation guard to a whole line.** Discharges routinely say
  "P1, P2, P4 HIT; P3 still unscorable". Scope the negation to a character
  window around the match, not the line, or one honest caveat erases the
  work.
- **Treating a bare mention as an attribution.** "As round 365 measured" in a
  results row does not credit round 365 with the row. Only a possessive over
  the artifact, or the artifact's path, attributes. Rejecting on bare
  mentions throws away real evidence; accepting any mention invents it.
- **Erroring on an era that could not have complied.** If the registry did
  not exist, the work was ungoverned, not in violation. Split the two views
  and publish the historical population as a counted observation rather than
  as findings nobody can act on.
- **A hard-coded count in the runner's own test.** Adding a checker to a
  suite whose test asserts `len(checks) == 5` turns a health check red for a
  number instead of a defect. Derive the count from the thing being counted.
- **Skipping the artifacts your key-extractor cannot parse.** Some A-files
  legitimately have no key (a mission-scoped rather than cycle-scoped one).
  Report them as unkeyed; do not silently drop them.

## Verification

From the repo root:

```
python3 skills/skill-authoring/scripts/carryforward_check.py --list
python3 skills/skill-authoring/scripts/carryforward_check.py ; echo "rc=$?"
```

`--list` prints one line per artifact with its ledger status and who
discharged it. The bare form prints findings and a summary; `rc=0` means no
ERRORs, `rc=1` means at least one.

Round 369's live corpus, for reference — the numbers here are what that round
measured and a later round should expect them to have MOVED, not to match:

```
carryforward: 49 bank(s) (+2 unnumbered), 45 scored, 4 unscored,
              0 error(s), 6 warning(s)
```

The tests, including the four frozen scanner regressions:

```
cd skills/skill-authoring/scripts && python3 -m pytest -q test_carryforward_check.py
```

To check the technique transfers rather than just this instance: delete one
entry from the ledger and re-run. The corresponding artifact must come back
as a K001 ERROR naming its path, which is the property that survives a new
naming convention appearing.
