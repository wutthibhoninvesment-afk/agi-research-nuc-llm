---
name: carried-claim-rot
description: Use when a project keeps a ROLLING status document that each cycle rewrites by copying the last one — a "next steps" / open-items block, a sprint carryover list, a risk register, a README "current limitations" section. Symptoms: an item prefixed "still", "unchanged", or "Nth week carried"; an open item naming what is MISSING ("still has no X") that a later cycle quietly built; a number or rule code re-stated verbatim across revisions; a backlog item marked open whose closure is recorded elsewhere in the same file; the carry COUNT being the only field anybody edits. The move is to treat "still N" as an executable assertion, re-derive it, and report each claim's carry AGE so an unaudited copy-forward becomes a number. Covers picking the live revision when file order is not chronological, an allowlist grammar with zero false positives, and pinning the instance as a fixture so the fix cannot erase its evidence. NOT for checking that links or citations RESOLVE, nor that a code comment matches nearby code.
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
  Q2"). Measured across one claim's ten assertions, that counter went 6, 6,
  7, 8, -, 7, 8, 9, 8, 8 — it does not count carries. Each author derived it
  from whichever earlier revision they happened to read, so its VALUE
  identifies the source copy, and a counter that fails to advance is proof
  the item was transcribed rather than re-derived. **A counter that DOES
  advance is not the converse.** See "the ordinal that advanced" below: the
  worst instance this skill has found had a perfectly maintained counter.
- An item asserts a **reference count** — "nothing calls X", "X has 0
  references in Y", "no caller anywhere", "not wired into Z". This shape is a
  single command away from being re-derived and is the one most likely to be
  missing from an existing claim grammar.
- An item cites a **number** (line count, test count, failure rate) or a
  **rule code** (`B002`, `SC-14`, `RUBY-021`) as currently true.
- An item asserts something is **BROKEN** — a named failing test, a red
  check, "still failing since cycle N". It looks like the most checkable
  claim in the document and is the least checked, because a fix lands in a
  different file and never touches the sentence. See "a carried RED" below.
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
8. **Audit the carry COUNTER against its own history — it is the one field
   everybody edits and the one nobody can get right.** An ordinal
   ("Nth consecutive cycle") is a claim about a history, and in a document
   whose revisions are not in order it is computed from whatever copy the
   author opened. Compare it against the ordinal on the most recent EARLIER
   revision asserting the same claim, sorted by declared cycle, never by file
   position. If it did not go UP, the item was transcribed. This has no false
   positives by construction: had the author derived the count from that
   revision, the number would have risen. Two rules keep it honest —
   **compare like with like** ("8th consecutive round" and "7th consecutive
   skills(B) round" have different denominators, so report that separately
   and never as an error), and **do not check the ordinal against the LENGTH
   of the carry chain**, because "consecutive cycles of type X" and "revisions
   in this file" are different denominators and asserting they are equal makes
   the checker the thing it audits.

9. **Publish the coverage gap in the same breath as the result.** "0 stale"
   is not the honest line. "9 items, 2 with a checkable claim, 2 re-derived,
   0 stale" is. A checker nobody is watching must have a zero false-positive
   rate even at the cost of recall, and must report the recall it gave up.
10. **Fix the live revision at the source, then pin the historical instance as
   a test fixture.** Correcting the document makes the checker exit 0 — which
   deletes the only evidence it works. Copy the offending historical text into
   a unit-test fixture so "this tool catches the bug it was written for" stays
   a re-executed claim. Keep the wrong text in the frozen older revisions:
   rewriting them hides the mechanism and teaches nothing.
11. **Wire the live check into the suite that already runs every cycle.** The
    fix for a claim nobody re-executes is a test that re-executes it — not a
    sweep somebody has to remember. One test, asserting the live revision has
    zero stale claims, in whatever suite the next cycle is guaranteed to run.
12. **Give a RETIRED item a tombstone, because deleting its line is
    indistinguishable from never writing one.** The normal way to close a
    carried item is to drop it from the next revision — which records
    nothing. Omission and retirement are the same edit, so any later
    revision that re-expands a compressed list ("the rest of team X's
    standing items are unchanged") back into names can resurrect a paid
    debt, and every checker stays green because the pointer still resolves.
    Keep a small registry — `{item id, discharged-by, evidence}` — and make
    a live-revision citation of a registered item an ERROR. Two rules keep
    it honest: **a tombstone is a claim** (its evidence must name a file,
    commit or artefact a reader can open, and a test should re-derive that
    the path exists), and **register only what you verified**, because a
    wrong tombstone silences a real debt — the one failure mode worse than
    the rot.

## Pitfalls
- **"Unchanged" and "not checked" are different sentences, and most rolling
  documents cannot tell them apart.** When you carry an item forward, say
  which one it is, per item, with the derivation: *re-derived by reading /
  by absence / arithmetically*, or plainly *not re-derived this cycle, and
  here is what it would take*. One bulk "standing and unchanged" line
  collapses both into the reassuring one.
- **Fixing the live document is not the fix.** Editing "415" to "399" clears
  today's finding and changes nothing about the channel. The next cycle will
  copy your corrected line forward without re-deriving it either. Only step 10
  closes it.
- **Replacing a rotted claim with a better SENTENCE rots faster than the
  claim did.** Whence's SPEC.md carried a stale version enumeration for ~80
  cycles; round 348 replaced it with a header that names the level once and
  explains, in prose, why enumerations rot. Round 350 added a new version
  section and left the header alone. Round 354 found it two levels stale —
  **the anti-rot sentence lasted one cycle.** An explanation of the failure
  mode is still a claim nobody re-runs. Whatever you write in place of a
  rotted line, ship the re-derivation next to it in the same change: here,
  a test that parses every version heading and compares the maximum against
  the header (sorting on the numeric parts, or v0.22 loses to v0.2).
- **The carry count is the most seductive false comfort in the document, and
  it is not even a count.** "8th consecutive round carried" reads like
  diligence — somebody has been tracking this. Measured across all ten
  assertions of one such claim, the ordinal ran 6, 6, 7, 8, -, 7, 8, 9, 8, 8:
  it repeated twice and fell twice. Round 349's "8th" was wrong because it
  counted carries of an item closed on round 339; round 398's "8th", 49
  rounds later, was wrong because it was round 349's "8th", copied. The
  counter is a FINGERPRINT of the revision the author read, which is what
  makes it useful: round 398's `8` rules out the two physically last blocks
  in the file (both `6`) and points at the three that say `8`.
- **Exempt the acknowledgement, or the check punishes the cure.** The
  sentence a well-behaved revision writes is *"item 5 is CLOSED and must not
  be carried again"* — which cites the item, and which a naive registry check
  flags as a re-assertion. The one thing that fixes the rot becomes the thing
  that trips the alarm, and the next author deletes the sentence to get green.
  Exempt a citation whose own item text says `closed` / `retired` /
  `discharged` / `superseded`. Be generous about it: a checker nobody watches
  must be zero-false-positive even at the cost of recall.
- **A gap in the carry list is a resurrection, and the age report already
  shows it.** A carry age of "16 revisions" hides the shape; the LIST of
  revisions does not. `rounds 333, 334, 336, 338, 346, 347, 348, 375, 377,
  …` has the answer in it — the item was dropped for twenty-three cycles and
  came back. That is a different defect from a never-noticed closure and it
  needs a different fix (a tombstone, not a re-read), so read the list rather
  than the count. Note the age report is correctly INFORMATIONAL and never an
  error: a long carry is not itself a defect, which is exactly why nobody
  reads it. If the discontinuity matters, promote it to its own finding —
  round 399 did, after a 49-cycle gap put a closed item back in the live
  revision with its old counter attached, and the promoted rule is the
  ordinal check in step 8 rather than a gap threshold, because "how big a
  gap is suspicious" has no principled answer and "the counter went
  backwards" needs none.
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

### The ordinal that advanced

The skill above reads a stalled carry counter as proof of transcription. The
inverse does not hold, and the instance that proves it is worse than any
stalled one.

    round 409  wired `nuc/run_checks_fast.sh` into the driver and recorded the
               closure in bold in its own entry: "is wired into run_driver.sh
               — SIXTH round carried, 0 references in-tree, closed".
    round 411  "still has 0 references in run_driver.sh — FOURTH round carried"
    round 412  "… FIFTH round carried"
    round 414  "… SIXTH round carried"

`grep -c run_checks_fast run_driver.sh` was **4** throughout. The ordinal went
up on schedule, every cycle, because incrementing it is the one edit a
copy-forward author reliably makes — it is the field that *looks* like the
maintenance. The claim beside it was false the whole time.

So: **the carry ordinal is a fact about the ledger, not about the artefact.**
A well-maintained counter is evidence that somebody read the item, and nothing
more. Where a stalled counter is a cheap detector, an advancing one is not
even weak evidence in the other direction — treat it as absent information.

Two corollaries, both measured on the same document:

* **A recall gap reads as a clean bill.** The checker's verdict on the block
  containing that item was `7 claim(s): 7 re-derivable, 0 skipped; 0 stale`.
  Its finding classes were body-line counts, lint codes, carry ordinals,
  inline `cmd -> result` pairs and retired-item pointers; a reference count is
  in none of them, so the item produced **no finding of any kind**. Never
  quote a stale count without its denominator: the honest sentence is "0
  stale of the 7 we can check, out of 13 items".
* **The true and false halves can be in one sentence.** The item read: *"X
  still has 0 references in run_driver.sh … `skills/run_checks_fast.sh` IS
  wired (round 363), so a basename grep lies."* Re-derived: the first clause
  is false (2 mentions, 1 invocation), the second true on identical evidence,
  because nobody ran either. Extract claims per CLAUSE, not per item.

### A reference count has two right answers

`refs X --in Y` on the file above returns **2 raw, 1 code-only**: one mention
is the comment explaining the wiring and one is the wiring. "How many
references" is ambiguous and the item picked neither. Report both and let the
claim say which it meant; a checker that silently picks one is right half the
time and unfalsifiable the other half.

### The claim a status document is MADE of is the absence claim

Every grammar above re-derives an assertion that something **is** so — a
count, a line total, a lint code, a pointer. That is the wrong polarity. An
open item, by construction, says what is **missing**, and absence fails
differently. A presence claim is closed by whoever wrote it: you fix the
count. An absence claim is closed **by a different round, in a different
file** — someone implements the missing thing, the ticket is satisfied in
code, and the sentence describing the hole is never touched. Nothing notices.

Round 423 found this in the checker's own status block. Round 415 wrote *"no
finding class for a REFERENCE claim"* (true); round 417 **implemented it** —
S009 and S010, documented, 30 tests; rounds 416, 419 and 421 carried it
anyway, and 421 *sharpened* it to name `S009`: the exact code live for four
rounds. The checker reported `0 stale of 7 checked` each time, correctly — the
sentence was in its published recall gap, and **absence is where a
forward-looking document does its rotting**.

**Re-derivation**, the cheapest there is: resolve the named file, look for
the named token in it, keeping the raw/code split from the reference grammar
— a file may mention a token in a comment saying the thing does not exist
*yet*. Token in CODE -> **STALE**, the thing exists and the sentence is false.
In PROSE only -> **WARN**, documented-not-built; say which you meant. Absent
-> clean.

**One direction is strong, one is weak.** STALE is near-certain: the token is
right there, in code, in the file the sentence named. CLEAN is weak — the
token may be spelled differently, or live elsewhere. So: certain when it fires
and silent when it is not, and **never let an unreadable or unresolvable
container come back clean**. "Not found" is the verdict the claim wants, so an
unreadable container must be UNCHECKED, never agreed with — the one bug in
this class that testing would not show you.

**Gate it on a literal token, then bill the gap.** The sentence must name a
**string you can look for** — backticked, or a bare house code (`S009`,
`D-013`). *"has no caller"* names a concept; there is no exact re-derivation
for a concept, so there is no claim, and widening until one matches is how a
checker becomes the heuristic it replaced. Measured when the class shipped:
**13 absence-shaped sentences across 336 files, 3 naming a literal token —
precision 3/3, recall 3/13 = 23%.** Publish that on the *same line* as the
zero, because aggregators quote the last line:

    ... 1 stale of 8 checked; coverage 7/12 items (58%), 8/8 claims,
    1 absence sentence(s) declined for want of a literal token

The declined count is an invoice, not a backlog. Three of the 10 declined were
the *same claim* that fired, written by 415/416/419 without the token: **it
became false in round 417 and became CHECKABLE when 421 sharpened it.**

### A carried RED is an absence claim wearing a presence claim's clothes

The section above is about a sentence saying something is MISSING. This is
its twin, and it is the more expensive one: a sentence saying something is
BROKEN. It reads like a presence claim — it names a test, a rule code, an
exact assertion — so every grammar above treats it as re-derivable and every
author treats it as verified. It is not. A red is closed **by a different
round, in a different file**: someone fixes the code, the suite goes green,
and the status document's sentence describing the failure is never touched by
the fix. Exactly the absence polarity, with a token attached that makes it
look safe.

The instance, from this program's round 439. Two harness reds sat on the
carry list:

* `test_swe_campaign.py::test_review_stage_and_report` — carried from round
  433 with a standing instruction, *"two candidate shapes … do not guess
  between them, run the file"*, re-listed by 434, 435 and 436.
* `test_verb_audit.py::…::test_no_unexplained_broken_invocation`, the
  broken-invocation finding of that program's verb audit — carried as
  *"red since round 429, fix the RULE not an exemption"*.

**Both had been green since round 437**, which ran them, fixed them, and
wrote both up in its own knowledge file — a file committed and sitting in the
tree when round 439 started. Round 439 re-derived the first one from scratch
(≈10 minutes of wall clock) and bet a banked prediction on a question round
437 had already answered. The carry list was the index it read; nothing
updates a carried item when a later round closes it.

**Two moves, in order of cost.**

1. **Re-derive against the newest round that touched the item, not the round
   that raised it.** A carried item cites its ORIGIN by construction — that
   is what "carried from round 433" means — and the origin is the one
   revision guaranteed to be superseded. Cost: seconds.

       grep -l 'test_review_stage_and_report' knowledge/round-4*.md | tail -3

   Read the newest hit before re-deriving anything. Round 439 skipped this
   and paid.

2. **Give the red a mechanism that retires it, because discipline will not.**
   A red retires only when something re-runs it, and the reds that rot are
   precisely the ones too expensive to re-run casually — that is *why* they
   were carried. A per-cycle recorded slice with a bounded budget (this
   program's `harness/run_slowtier_slice.sh`, 240 s a round against a
   76-minute tier) converts "somebody should re-run it" into an entry with a
   timestamp and a freshness verdict. Until it exists, a status document's
   red section is a set of assertions nobody can afford to check, and its
   staleness grows without bound.

**The asymmetry to remember:** a stale-open red is *more* expensive than a
stale-closed one. A carried item that understates progress gets re-escalated
by every reader and re-derived by every actor, and each re-derivation costs
the full price of the measurement it re-does. It also reads as a program
standing still when it is not.

## Verification
```
# 1. the live revision, static (no command execution at all)
python3 skills/skill-authoring/scripts/state_claim_check.py state/research-state.md
# expected: 0 stale, exit 0. Reports the live block's round number, how many
# items it has, and how many carry a re-derivable claim.

# 2. the same, executing the allowlisted command claims
python3 skills/skill-authoring/scripts/state_claim_check.py --run --timeout 120 state/research-state.md
# expected: identical verdict; `--run` adds S003/S004 for `cmd -> result`

# 3. every claim with its verdict and skip reason (the coverage detail)
python3 skills/skill-authoring/scripts/state_claim_check.py --list state/research-state.md
# expected: exit 0, one line per extracted claim, tagged with its kind

# 4. a historical block, to reproduce a finding the live document no longer has
python3 skills/skill-authoring/scripts/state_claim_check.py --block 349 state/research-state.md
# expected: exit 1, S001 (415 vs 399), S002 (B002 no longer emitted) and
# S007 (its ordinal 8 is below round 348's 9)

# 5. the tombstone registry — a retired item re-asserted as open
python3 skills/skill-authoring/scripts/state_claim_check.py state/research-state.md
# expected: S006 for any live-block citation of an item
# state/retired-next-step-items.json records as discharged; SILENT when the
# citing item's own text acknowledges the closure. With round 389 live it
# fired exactly once (round 332's item 1, discharged by 350, resurrected at
# 375) and stayed silent on round 383's item 5, which says "is CLOSED".

# 6. the carry counter, against its own history
python3 skills/skill-authoring/scripts/state_claim_check.py --block 398 state/research-state.md
# expected: exit 1, S007 naming the previous asserting block and printing the
# sequence by cycle: `333:6 .. 348:9 round, 349:8 round, 398:8 round`

# 7. the ABSENCE polarity — the claim the document is made of
python3 skills/skill-authoring/scripts/state_claim_check.py --block 421 state/research-state.md
# expected: exit 1, exactly one S011 — `S009` claimed absent from
# state_claim_check.py, found in CODE. Round 423 corrected the live block;
# this reproduces the finding against frozen history.

# 8. the same claim one revision earlier, written without the token
python3 skills/skill-authoring/scripts/state_claim_check.py --block 419 state/research-state.md
# expected: exit 0, summary ending `1 absence sentence(s) declined for want
# of a literal token` — the recall gap billed on the quoted line.

# 9. the re-derivation an S011 finding hands you, verbatim
python3 harness/wiring_audit.py token-refs S009 \
  --in skills/skill-authoring/scripts/state_claim_check.py --expect-absent
# expected: exit 1, `ABSENCE REFUTED: ... occurs in code on line(s) ...`;
# exit 0 and `ABSENCE HOLDS` against a file that really lacks it.

# 10. the guard that makes this run every cycle
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

Round 399 added step 8 and measured it over the same document: sweeping all
**93** revisions, each treated in turn as the live one, **3** would be
ERROR-red on S007 (rounds 334, 349, 398) and **2** more WARN on S008 (rounds
318, 346 — the counter fell and its denominator moved with it). The rule is
therefore not a one-instance rule, and none of the five was ever noticed by
the rounds that wrote them. The sets, not the counts, are pinned in
`TestLiveCorpusOrdinals`, so a new instance names itself.

Round 415 added the two sections above and measured the instance behind them:
`python3 harness/wiring_audit.py refs nuc/run_checks_fast.sh --in
run_driver.sh --expect 0` exits **1** with `EXPECT MISS: claimed 0,
re-derived 2`, and the same command against `skills/run_checks_fast.sh` with
`--expect 1 --code-only` exits **0**. Both clauses come from one sentence in
one item of one block, and `state_claim_check.py` reported that block `0
stale`.
