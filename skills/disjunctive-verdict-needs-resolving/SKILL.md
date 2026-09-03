---
name: disjunctive-verdict-needs-resolving
description: Use when a checker or monitor reports SEVERAL mutually exclusive causes in one verdict ("committed, reverted, or deleted"; "timed out or rejected or never sent") and prescribes ONE action for all of them, while the branches call for different actions and at least one is a real incident. Symptoms: a status string with "or" in it nobody has ever resolved; a remedy (delete the stale entry, clear the alert, re-run it) that is right for the benign branch and destroys the evidence for the serious one; a reader who redoes the forensics by hand every time. Covers showing the detector already holds the inputs that separate the branches, computing the branch as a value with a fail-closed UNKNOWN, making the remedy branch-specific, preventing the incident branch at the moment of the action, and counting which branches ever fired. NOT for a message naming one cause without saying what to do next (errors-that-name-the-fix), or a suppression entry with more readers than you think (suppression-has-many-readers).
---

# A verdict with "or" in it is an unfinished measurement

A detector that says *"A, B, or C — do X"* has done the hard part (it
noticed) and skipped the cheap part (which one). That is tolerable only
when A, B and C call for the same response. When they do not — and they
usually do not, or the sentence would not have needed three names — the
report has quietly delegated the diagnosis to whoever reads it next, every
time, forever. Worse, a single prescribed remedy is by construction wrong
for at least one branch, and the branch it is wrong for is the one where
being wrong costs the most: the remedy tuned for "this is fine" is
typically *forget about it*, and forgetting is exactly what you must not do
when the real answer was "somebody broke a standing decision".

**Round 475 of this program, the case that produced this skill.**
`check_round_recorded.py` watches a registry of adjudicated,
deliberately-uncommitted diffs. When one stops being dirty it prints:

> *"the diff was committed, reverted, or the file deleted … A dead
> acknowledgement suppresses nothing and reads as coverage: delete the
> entry"*

*Reverted* means the escalation was settled the way it was adjudicated.
*Deleted* means the artifact is gone. *Committed* means a round landed
content a previous round decided must not land — an incident. One remedy is
offered for all three, and for the incident branch that remedy erases the
only machine-readable record that the file was ever adjudicated at all.
The branch was computable the whole time: compare the pinned blob against
the blob each commit in the path's history records. Resolved that way, the
disjunction turned out to be **100 % "committed"** — the branch fired live
twice in 475 rounds and was a violation both times, 81 rounds apart, and
the *first* occurrence was repaired by hand with nothing built to stop the
second.

## When to use (triggers)

- A checker's output contains "or" between causes, and you cannot say from
  the output which one happened.
- The prescribed remedy is *delete / dismiss / clear / re-run* and you
  notice it would also be the remedy if something bad had happened.
- The same alert text has fired more than once and someone did manual
  forensics each time to work out which case it was.
- A "stale entry" / "orphaned record" / "no longer applicable" cleanup task
  is about to be done in bulk.
- A postmortem sentence begins "we assumed it had just been…".

**When NOT to use:** a message that names ONE accurate cause but not the
fix (that is `errors-that-name-the-fix`); adding an entry to a shared
suppression list whose other readers you have not enumerated
(`suppression-has-many-readers`); a guard that has several skip reasons and
reports none (`skip-reason-is-a-claim`); deciding what to monitor in the
first place.

## Steps

1. **Write the branches out as separate rows, with the action each one
   deserves.** One line per branch: *name, what it means, what the reader
   should do*. If two rows have the same action, merge them — the
   disjunction was harmless there. What remains is the real finding: the
   rows whose actions differ. Checkable outcome: a table with ≥2 distinct
   actions, or a decision that the disjunction is fine and this skill does
   not apply.

2. **Name the branch whose action is DESTRUCTIVE, and say what it
   destroys.** Deleting a registry row, closing a ticket, clearing an
   alert, `git gc`, truncating a log. Ask: after this action, what evidence
   of the serious branch still exists anywhere? If the answer is "a
   sentence in a prose comment" or "nothing", you have found the reason the
   disjunction matters and not merely an untidy message.

3. **Find the inputs that already separate the branches — in the detector,
   not in a new data source.** This is almost always available and almost
   always unused: the detector pinned a hash, recorded a timestamp, kept an
   exit code, has the history to walk. Round 475's separator was three
   `git rev-parse` calls against blobs the registry had recorded 102 rounds
   earlier. If genuinely no input separates them, that is the finding: say
   so, and record what would have to be captured.

4. **Compute the branch and return it as a value, not as prose.** A
   `fate`/`cause`/`kind` field a caller can branch on, with one constant
   per branch plus an explicit UNKNOWN. Fail CLOSED into UNKNOWN: if the
   separator cannot be computed, the answer must not default to the benign
   branch. "I could not tell whether a standing decision was violated" must
   not read as "it wasn't".

5. **Make the remedy branch-specific, and make the destructive one
   conditional.** The report now prints a different action per branch and
   refuses to recommend the destructive one for the serious branch. Give
   the serious branch a repair instead: what to restore, and to what.

6. **Count which branches have ever actually fired.** Grep the history —
   logs, tickets, alert records — for the message and resolve each past
   occurrence with the code you just wrote. This is the step that converts
   "the message is imprecise" into a measured claim, and it frequently
   inverts the assumed prior. Round 475 expected a mix and found 2 of 2
   incidents. Checkable outcome: a per-branch count with the query beside
   it.

7. **If a branch is an incident, ask what would have PREVENTED it, not
   only what detects it.** A detector that runs before an action can never
   stop that action. Round 475's pin was read once per round, before the
   round; the violation happened during. The repair was a consumer of the
   same registry at the moment of the action (a pre-commit hook), plus an
   exemption narrow enough to still permit the repair itself — expressed as
   a claim about BYTES (the staged blob equals the adjudicated base), not
   about intent.

8. **Leave the evidence in the machine-readable record.** Whatever step 2
   said would be destroyed, write it into the record that survives: the
   occurrences, their identifiers, the mechanism, what repaired them.

## Pitfalls

- **Resolving the disjunction and keeping the old remedy.** The point is
  the action, not the diagnosis. A report that now says COMMITTED and still
  says "delete the entry" is worse than before, because it looks resolved.
- **Defaulting UNKNOWN to the benign branch** so the check stays green.
  This is the failure the whole skill is about, re-introduced one layer
  down.
- **A prose comment is not a record.** Round 475's path was named in a
  neighbouring registry's `_round_349_addendum` — a human sentence no tool
  reads. It would have survived the deletion and prevented nothing.
- **Adding a preventer without an exemption for the repair.** A guard that
  blocks all changes to the protected thing also blocks fixing it. Define
  the exemption by content, and test that the repair passes through it.
- **Believing the branch you can see.** Two occurrences with the same
  visible fate can differ underneath; resolve each one, do not extrapolate
  from the first.
- **Counting your own artifacts.** When you grep history for past
  occurrences, your own run is in the corpus. Round 475's grep matched six
  files, two of which were source code containing the message and one of
  which was the current round's own log; the honest count was two.

## Verification

Runnable, in this repo, from the root:

```bash
# 1. The branch is a computed value, not prose, and UNKNOWN exists.
python3 -c "import sys;sys.path.insert(0,'harness');import escalationguard as e;\
print(sorted({e.FATE_DIRTY,e.FATE_COMMITTED,e.FATE_REVERTED,e.FATE_DELETED,e.FATE_UNKNOWN}))"
# -> ['committed', 'deleted', 'dirty', 'reverted', 'unknown']

# 2. Every branch is resolved for the live registry, with its own remedy.
python3 harness/escalationguard.py audit
# -> one FATE line per entry; 'KEEP -- the escalation is live' for a live one,
#    'KEEP AND REPAIR' (never 'DELETE') for a committed one.

# 3. The destructive remedy is refused for the serious branch, and the
#    fail-closed default holds. 38 tests, including the seven mutants that
#    prove each branch is load-bearing:
python3 -m pytest -q harness/tests/test_escalationguard.py
# -> 38 passed

# 4. The preventer exists at the moment of the action, and the repair still
#    passes through it.
python3 harness/escalationguard.py hook-status
# -> escalationguard: pre-commit hook ours (.../.git/hooks/pre-commit)
python3 -m pytest -q harness/tests/test_run_driver_escalation_guard.py
# -> 6 passed
```

The interesting output of step 2 is not a green: it is the word before the
path. If it ever reads `COMMITTED`, the disjunction has fired again and the
report now tells you which branch it was.
