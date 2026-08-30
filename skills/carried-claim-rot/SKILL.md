---
name: carried-claim-rot
description: Use when a project keeps a ROLLING status document that each cycle rewrites by copying the last one — a "next steps" / open-items block, a sprint carryover list, a risk register, a README "current limitations" section. Symptoms: an item prefixed "still", "unchanged", "standing", or "Nth consecutive week carried"; a number or rule code re-stated verbatim across many revisions; a backlog item marked open whose own closure is recorded elsewhere in the same file; the carry COUNT being the only field anybody edits. The move is to treat "still N" as an executable assertion, re-derive it against the artefact, and report each claim's carry AGE so an unaudited copy-forward becomes a number. Covers picking the live revision when file order is not chronological, an allowlist claim grammar with zero false positives, and pinning the historical instance as a fixture so the fix cannot erase its own evidence. NOT for checking that links or citations RESOLVE, and NOT for verifying a code comment matches nearby code.
---

# Carried-claim rot

A rolling status document is written by copying the previous one and editing
the parts you touched. That is the correct way to write it, and it is also a
**silent copy-forward channel**: every item you did not touch gets re-asserted,
in a document dated today, over your name, with no step anywhere that
re-derives it.

The rot is therefore not caused by carelessness, and cannot be fixed by asking
people to be careful. Each individual author did the right thing — they left
alone what they had no reason to change. The claim was verified once, by the
round that first wrote it, and every revision since has been a **transcription
of a verification, presented as a verification**.

The tell is the vocabulary of non-change: *still*, *unchanged*, *standing*,
*as before*, *remains*, *Nth consecutive cycle carried*. Those words are the
only assertions in the document that are about the present tense — and they
are the only ones nobody re-runs.

## Trigger conditions
- A file contains several dated revisions of the same list (`## Next steps
  (as of round N)`, `## Open items — sprint 34`, `### Known limitations,
  v2.9`), and the newest one was produced by editing a copy of the previous.
- An item is prefixed with a non-change word: *still*, *unchanged*,
  *standing*, *as before*, *remains*, *pending*, *deferred again*.
- An item states a **carry count** ("8th consecutive round", "carried since
  Q2"). A counter that increments while its subject is never re-read is the
  clearest possible signal: the only field anybody edited was the counter.
- An item cites a **number** (line count, test count, failure rate) or a
  **rule code** (`B002`, `SC-14`, `RUBY-021`) as currently true.
- You are about to write the next revision of such a document. Run the check
  BEFORE you copy the previous one forward, not after.
- Proven on: `state/research-state.md`, round 351. Round 339 split
  `fuzz-mutate-kill-loop/SKILL.md` from 415 body lines to 399 and recorded
  the closure in bold in the same file. The next-steps blocks of rounds 343,
  346, 347, 348 and 349 re-asserted "still 415 body lines (B002)" anyway;
  round 349 added "8th consecutive round carried". Nine blocks in the file
  carry that sentence verbatim. The linter it cites had been silent for ten
  rounds.

## Steps
1. **Find the live revision, and do not assume it is the last one in the
   file.** Sort the revisions by their own declared cycle number, not by file
   position. In the corpus this skill was built on, the trailing stack of
   next-steps blocks is only roughly reverse-chronological — round 341's block
   sits physically *between* round 343's and round 349's — so "last block"
   would have picked one of the oldest present. If two revisions declare the
   same cycle, stop and say so; picking one silently makes every later finding
   unattributable.
2. **Check the live revision only.** Older revisions are a frozen record. A
   figure that was true when it was written is not rot, and flagging it
   produces permanent noise that gets the whole check muted. This is the same
   authoritative-vs-historical split a citation checker needs (see
   `skills/citation-registry-integrity`).
3. **Unwrap before you parse.** Hard-wrapped markdown breaks claims across
   lines, including inside backticks: `` (`grep -c mutation_test↵
   harness/swe/campaign.py` -> 0) `` is one claim on two source lines. Join
   an item's continuation lines into a single string, and keep a
   character→source-line map so a finding still points at the line the claim
   *starts* on rather than at the top of a twelve-line item.
4. **Extract claims with an allowlist grammar, not a heuristic.** Write one
   regex per claim SHAPE you can re-derive exactly, and treat everything else
   as prose. Two shapes cover most rolling documents:
   - ``  `<path>` is still <N> body lines (<CODE>) `` → re-derive `<N>` from
     the file, and assert `<CODE>` is still emitted by the tool that owns it.
   - ``  `<command>` -> <result> `` → re-run the command and diff.
   Resist "any sentence containing a number". The tool must not itself become
   a thing that asserts figures nobody can reproduce.
5. **Re-derive by CALLING the owning tool, never by reimplementing it.** A
   claim about "body lines (B002)" must be checked with the linter's own
   frontmatter split and the linter's own findings list. Reimplementing the
   count creates a second definition to keep in sync — the failure mode in
   `skills/copied-mirror-drift`, introduced by the tool meant to prevent it.
6. **Gate execution behind an explicit flag and a fail-closed allowlist.**
   Static extraction always; running commands only on `--run`, and only for
   programs on an allowlist. A rolling status document cites commands that
   ssh to other hosts, spend model tokens and write into the checkout. An
   allowlist can only fail by declining to check something; a denylist
   eventually bills somebody.
7. **Report the carry AGE of every claim, not just its truth.** For each
   extracted claim, count how many revisions assert it *verbatim* (normalise
   whitespace and case; match exactly, never fuzzily). Age 1 means this cycle
   derived it. Age 9 means nine authors signed a sentence none of them ran.
   Age is not an error — it is the recall side of the report, and it is what
   turns "we should re-check things" into a number with names on it.
8. **Publish the coverage gap in the same breath as the result.** "0 stale"
   is not the honest line. "9 items, 2 with a checkable claim, 2 re-derived,
   0 stale" is. A checker nobody is watching must have a zero false-positive
   rate even at the cost of recall, and must report the recall it gave up.
9. **Fix the live revision at the source, then pin the historical instance as
   a test fixture.** Correcting the document makes the checker exit 0 — which
   deletes the only evidence it works. Copy the offending historical text into
   a unit-test fixture so "this tool catches the bug it was written for" stays
   a re-executed claim. Keep the wrong text in the frozen older revisions:
   rewriting them hides the mechanism and teaches nothing.
10. **Wire the live check into the suite that already runs every cycle.** The
    fix for a claim nobody re-executes is a test that re-executes it — not a
    sweep somebody has to remember. One test, asserting the live revision has
    zero stale claims, in whatever suite the next cycle is guaranteed to run.

## Pitfalls
- **Fixing the live document is not the fix.** Editing "415" to "399" clears
  today's finding and changes nothing about the channel. The next cycle will
  copy your corrected line forward without re-deriving it either. Only step 10
  closes it.
- **The carry count is the most seductive false comfort in the document.**
  "8th consecutive round carried" reads like diligence — somebody has been
  tracking this. It is the opposite: it is proof that the only field anybody
  touched was the counter. Round 349's "8th" was itself wrong, because it was
  counting carries of an item closed on round 339.
- **A closure recorded elsewhere in the SAME file does not propagate.** Round
  339's entry says, in bold, that it closed the backlog item. That entry sits
  ~1000 lines above the next-steps block that re-opens it. Nothing reads
  backwards. Do not assume a well-written record is a self-consistent one.
- **A comment or entry that is true *of a part* is a hazard when the part is
  the half that was done.** A reader auditing the sentence finds it accurate
  and moves on. Check the claim the reader actually has, not the one the
  author scoped.
- **Fuzzy matching for carry age makes the tool the thing it audits.** A
  similarity threshold produces an age nobody can reproduce. Exact match on a
  short normalised span costs a little recall (two of this corpus's eleven
  restatements used different wording and score as separate claims) and buys
  a number you can defend.
- **Unresolvable paths in prose are not findings.** Status documents name
  files that do not exist yet ("if a `pyproject.toml` ever appears at the repo
  root…"). Flag those and the check gets muted, and then it never catches the
  real one. Count them as skipped, with a reason, in the coverage line.
- **A heading-level stop rule silently truncates.** If revisions are
  interleaved with other sections, ending a revision at "the next heading of
  level ≤ 2" can swallow a following entry, and ending it at level ≤ 3 can
  truncate a revision that contains its own sub-heading. Whichever you pick,
  assert against the real document that no revision loses content — do not
  reason about it.
- **`subprocess.run(timeout=)` kills the shell, not its children.** If step 6
  executes anything, start the child in its own process group and kill the
  group. An orphaned test-runner grandchild reparents to init and keeps
  burning CPU through the rest of the sweep.
- **A checker that prints only at the end is all-or-nothing.** Round 351's
  corpus-wide executing sweep was killed by a 20-minute cap and produced zero
  output — not even a partial list of what it had got through. Stream each
  finding as it is produced, and offer a way to check one item at a time, or
  the expensive mode is one nobody can afford to start.

## Verification
```
# 1. the live revision, static (no command execution at all)
python3 skills/skill-authoring/scripts/state_claim_check.py state/research-state.md
# expected: 0 stale, exit 0. Reports the live block's round number, how many
# items it has, and how many carry a re-derivable claim.

# 2. the same, executing the allowlisted command claims
python3 skills/skill-authoring/scripts/state_claim_check.py --run --timeout 120 state/research-state.md
# expected: identical verdict; `--run` adds S003/S004 for `cmd -> result` claims

# 3. every claim with its verdict and skip reason (the coverage detail)
python3 skills/skill-authoring/scripts/state_claim_check.py --list state/research-state.md
# expected: exit 0, one `body-lines`/`command` line per extracted claim

# 4. a historical block, to reproduce a finding the live document no longer has
python3 skills/skill-authoring/scripts/state_claim_check.py --block 349 state/research-state.md
# expected: exit 1, S001 (415 vs 399) and S002 (B002 no longer emitted)

# 5. the guard that makes this run every cycle
python3 -m unittest discover -s skills/skill-authoring/scripts -p 'test_state_claim_check.py'
# expected: exit 0, OK. TestLiveCorpus is the live assertion;
# TestRound349Regression pins the historical text so correcting the document
# does not erase the proof.
```
Round 351 measured, in this order: 2 stale claims (S001 415→399, S002 B002 no
longer emitted) on a live block whose only other checkable claim (`grep -c
mutation_test harness/swe/campaign.py` -> 0) re-ran clean; carry age **9
blocks** (rounds 333, 334, 336, 338, 343, 346, 347, 348, 349) for the stale
sentence; coverage 9 items, 2 with a checkable claim. After the correction the
live document exits 0 and `--block 349` still exits 1.
