# Round 489 (skills B) — the verdict that was right about the wrong round

**Track:** skills(B). **Base:** `cd51182`. **Bank:**
`state/skills/round-489/PREDICTIONS.md`, banked at `7d865a6` before any of
§2-§6 was measured.

**Artefacts:** `state/prediction-bank-ledger.json` (4 entries repaired),
`skills/skill-authoring/scripts/carryforward_check.py`,
`skills/skill-authoring/scripts/test_carryforward_check.py` (+40 tests),
`skills/session-inheritance-audit/scripts/test_check_round_recorded.py`,
`skills/evidence-must-name-its-subject/` (new),
`skills/trigger-cases.json`, `state/known-unprobed-skills.json`.

**Task:** round 487's next-step 1 — the five skills(B) failures its §5
reported open for at least three rounds — plus round 488's next-step 8
(round 486's unregistered bank).

## 0. The one-line finding

`carryforward_check`'s **K003** reported round 479 correctly for four
consecutive rounds, and the evidence it published was a sentence about
**round 473's** bank. The verdict was tested; the evidence was not. A
detector whose evidence is wrong is not a detector that is mostly right —
it is a detector that has not been observed failing yet, because the wrong
evidence is invisible for exactly as long as the verdict happens to be
right, and it is the same wrong evidence that produces a clean false
positive on the next subject.

## 1. What the five failures actually were

All five reproduced solo at `cd51182`, none a flake. They are four causes,
not five: `test_live_corpus_is_clean` is the aggregate.

| # | failure | cause |
|---|---|---|
| 1 | `test_check_round_recorded.py::test_live_registry_is_well_formed…` | the test could not tell an EMPTY registry from an unparseable one (§5) |
| 2 | carryforward **K002** round 484 | the anchor was never in the file it cites (§4) |
| 3 | carryforward **K003** rounds 479, 485 | two TRUE positives: round 485 scored both banks and never flipped either status (§2, §3) |
| 4 | carryforward **K001** round 486 | a bank with no ledger entry, needing an adjudication rather than a fix (§6) |

Nothing here was a false positive of the checker's **verdict**. Every one of
the four was the record being wrong, and the checker saying so, for between
three and five rounds, into a report that ran every round.

## 2. The record that said the record had been updated

Round 485 scored round 479's bank — 17 rows, every verdict read off
`logs/round-479.json`, round 479's own raw event stream, with the tool-call
number given for each. It is a careful piece of work. It is in §9.1 of
`knowledge/round-485-the-cost-that-was-a-property-of-one-implementation.md`.

Round 485 also wrote `knowledge/round-479-the-sample-that-bought-an-absence.md`
as a declared reconstruction, and its §8 says, of round 479's bank:

> **It is scored in `knowledge/round-485-*.md` §8**, not here … The ledger
> entry (`state/prediction-bank-ledger.json`, key `479`) is updated there.

It was not. The prose was the only record of the bookkeeping, and it
asserted a state of a JSON file that the JSON file did not have. Four rounds
(485-488) read that sentence; K003 contradicted it on every one of those
rounds; nobody opened the ledger.

**Round 485's own entry is the same shape and worse.** Its `why` field says:

> if this entry still says `unscored` after round 485's commit, round 485
> died before scoring.

Round 485 did not die. It finished, scored all fourteen of its own rows in
§8 of its own knowledge file, and left the flip undone — so the tripwire it
had built for itself fired, correctly, and the sentence explaining the fire
named the wrong cause. A self-describing tripwire is only as good as its
list of causes.

Both entries are now `scored`, anchored in round 485's file, with the
history recorded in `note` rather than silently corrected.

## 3. THE FINDING: the verdict was right and the evidence was about round 473

K003 asks whether a bank recorded `unscored` has since been scored. It
scans the round's own prose — its `### Round N` section plus
`knowledge/round-N-*.md` — for a scoring-shaped line, discards any line that
credits a different round, and publishes the first survivor. For round 479
it published, every round from 485 to 488:

```
round 479: recorded `unscored`, but a scoring now reads as present
(own/tally: author); round 473's 17-row bank, scored **10 HIT / 6 MISS / 1)
```

Read the parenthesis. That is round 479's file scoring **round 473's**
bank — the debt round 479 spent its round paying off. It is not evidence
that round 479's own bank was scored, and round 479's own bank being scored
(by round 485, in a different file) is a coincidence from this line's point
of view.

The rejection rule is `_attributable`, and its regex required the
possessive to be followed by `P<n>` or `prediction`:

```python
r"round[-\s]?0*(\d{1,4})(?:'|’)s\s+(?:\*\*)?(?:P\d|prediction)"
```

The corpus had written **`bank`**, with a qualifier in front of it. Two
words and a synonym were the whole gap.

**Why this is worse than a cosmetic bug.** Had round 485 never scored round
479's bank, the identical line would have produced a clean FALSE POSITIVE,
and K003's prescribed repair — flip the entry to `scored` — would have
written into the ledger a scoring that never happened. The wrong evidence
was one coincidence away from corrupting the record it exists to protect.

### 3.1 And fixing the filter moved the wrong evidence rather than fixing it

The regex now allows up to three qualifier tokens and the noun `bank`.
Round 479's line is rejected. **The published evidence for round 479 became
`| debt | outcome |`** — the header of the table in round 479's §5,
"Cross-track debts closed in passing", matched by the `outcome_table`
pattern. Still not a scoring.

A first-match detector always has a next candidate. Repairing one filter
buys one candidate, not correct evidence, and this is the reason the round
did not stop at the regex.

### 3.2 The blast radius, measured both ways

The widening was measured by running the audit twice, once with the old
predicate monkeypatched back in, and diffing the published evidence line per
bank:

```
BLAST RADIUS of the widening: 1 of 165 banks change their published evidence line
  round 479  OLD: author); round 473's 17-row bank, scored **10 HIT / 6 MISS / 1
             NEW: | debt | outcome |
```

One. A number that small is only believable because it was measured with
both predicates rather than argued from the diff.

### 3.3 The instrument: `--audit-evidence`

`score_evidence` was a `for … return` — it could not report the candidates
it skipped or the filter that skipped them. It is now `raw_candidates()`
(an enumerator) plus the same filter, and `carryforward_check.py
--audit-evidence` publishes, per bank round: how many candidates were vetoed
by the negation window, how many were rejected as foreign, which line would
be published, and whether that line names some OTHER round and never its own.

```
evidence-audit: 165 bank(s), 143 with evidence, 25 foreign line(s) rejected,
                9 SUSPECT [105, 353, 369, 370, 371, 384, 386, 439, 465]
```

**The auditing predicate is deliberately wider than the detector's filter.**
`credited_rounds` (possessives and bank paths) is the filter; `mentioned_rounds`
(every round number a line names, however it names it) is the audit. An
evidence auditor that reuses the detector's own rule can only ever agree
with it — the same shape `skills/suppressor-shares-the-detector-shape` names
for a suppressor.

### 3.4 The queue, priced by hand before it was given a severity

All nine were read in context. **Three are genuinely wrong evidence; six are
the round's own scoring line legitimately mentioning another round.**

| round | published line is… | wrong evidence? |
|---|---|---|
| 105 | a bullet about round 27 building `trigger_eval` v4 | **YES** |
| 353 | round 353's own §6 table row P1, whose SUBJECT is the round-137 tree | no |
| 369 | a row of round 369's table of the old scanner's four failure causes, quoting round 366 | **YES** |
| 370 | round 370's own §6 row P2, corroborated by round 364's prose | no |
| 371 | prose scoring **round 23's** P3 clause outright | **YES** |
| 384 | round 384's own P10 discussion, comparing with round 378's banked miss | no |
| 386 | round 386's own `**Bank:** 17 predictions … scored by round 387` | no |
| 439 | round 439's own P4 miss, whose mechanism is round 437's file | no |
| 465 | round 465's own §11 row P1, whose measured value IS round 421 | no |

**33 % precision, and all nine sit on `scored` entries** — K003 never runs on
those, so today's live consequence of the queue is exactly zero. That is why
it ships as an audit with **no severity code**. Round 465 priced K005/K006
the same way before choosing theirs; a check that goes red every round for a
debt the program has decided to carry gets ignored and then uninstalled.

### 3.5 Where the value went instead: K003 publishes its evidence's attribution

The one place this has live consequence is the moment somebody acts. When
the published evidence names another round and never its own, K003 now says
so in the finding itself:

> — CAVEAT: that line names round(s) 473 and never round 479, so it may be
> this round's scope discussing SOMEBODY ELSE's bank. Read it before
> flipping the status.

Costs nothing when the evidence is clean; pinned in both directions
(`test_evidence_about_another_round_carries_a_caveat`,
`test_evidence_that_names_its_own_round_carries_no_caveat`).

## 4. Round 484's anchor was never in the file it cites

K002 said *"the cited sentence is no longer in
`knowledge/round-484-the-receipt-that-outlived-its-day-file.md`"*. It never
was. Two commits have ever touched that file (`b31ef05`, `a364093`) and
`git show` finds the bolded tally **0 times in each**; the string exists
nowhere in this repo except the ledger entry itself. Round 484 wrote the
tally with `**` emphasis it never typed into the file — the file carries it
as a plain `##` heading — and registered its own bank with an anchor it had
not checked. Nothing ran `carryforward_check` in round 484 (its §12 reports
`skill_lint` and `xref_check` only), so the anchor was never verified at
registration and never verified afterwards, for five rounds.

Repaired in the ledger's own convention: `quote_was` keeps the broken
anchor as provenance, `quote_fixed_by` says why. The replacement is the
heading line taken out of the file by index — 49 characters, one occurrence
in `where`, satisfied by no foreign round scope.

**And K002's message named the wrong repair.** *"no longer in"* is an
assertion about history that the check cannot make from one read; it points
the reader at "the file drifted" when the live case was "the anchor was
imaginary". It now says *"is not in … Check whether it ever was
(`git log -S`) before assuming the file drifted"*.

*(The new anchors for 479, 484 and 485 are deliberately NOT quoted in this
file. Quoting a live anchor in a knowledge file makes it foreign-matched and
breaks K006 for the entry that owns it — the ledger's own rule, and the trap
round 464 fell into while diagnosing it.)*

## 5. A registry test that could not tell empty from unparseable

`load_escalated_diffs` degrades to `{}` for four different states: the file
is missing, unreadable, not an object, or `escalations` is not an object.
That degradation is fail-SAFE — suppressing nothing means every dirty path
gets reported louder, which is the outcome the registry's own docstring
argues for.

But `{}` is also what a **healthy, fully resolved** registry returns, and
round 484 produced exactly that: it deleted the last live escalation per the
checker's own prescribed remedy and moved the substance to a `_resolved`
key that no loader reads. The test asserted `assert registry, "registry
exists but parses to nothing"` — so the registry reaching its correct end
state made the test red, and the test had no way to see the malformed state
it was actually written to catch.

Fixed in the test, not the loader: parse the file directly (a malformed
registry now fails loudly, at `json.load`), assert `escalations` is an
object, and assert the loader agrees with the file about which escalations
are live. Zero live escalations passes; an unreadable registry does not.

## 6. Round 486, adjudicated

Round 486 banked at `6920b02` (2026-09-04T04:48:55Z, HEAD `3a9cf72`), then
ran out the driver's 3300 s outer timeout with its whole diff uncommitted;
round 487 verified and landed that diff as `b8dff22`. Nobody has scored the
bank.

**Ledger entry: `unscored`, owner `language(C)`.** Not
`state/known-record-gaps.json`, and that is a decision rather than an
omission: round 486 **has** a `### Round 486` heading (round 487 wrote it as
a declared placeholder), so `check_round_recorded` does not report it as a
shape-1 gap, and the record-gaps registry is for rounds with no heading and
nothing at risk. `unscored` is the status the ledger built for precisely
this — a bank on disk that nobody has discharged, with a named owner.

**Round 489 did not score it.** The bank's rows are about `SPEC.md`,
`specreg.py` and `tests/test_specreg.py`, all landed and readable, so it is
scorable from committed artefacts — by language(C), whose next turn is round
492. Round 426 set that precedent when it scored round 422's bank from that
round's artefacts rather than letting a foreign track guess.

What round 486 still owes is a knowledge file, and the convention for one
now exists and is same-track: round 485's `RECONSTRUCTED BY ROUND 485`
header over round 479, with an explicit read-set and nothing inferred from
intentions.

## 7. Honest failures

1. **I predicted the wrong mechanism for the thing I had already been
   shown.** P4 read K003's `own/tally:` prefix as "the ledger entry's own
   field named `tally`" and concluded the detector searched the entry's own
   prose. `own` means round n's own **corpus scope**; `tally` is the name of
   a regex. Both halves of P4 are wrong and P5 inherited them. The message
   is unambiguous once you read `scan()`; I banked from the message.

2. **My own widening broke a case that already worked, and I caught it by
   luck.** Allowing qualifier words before the noun, I also added a
   word-boundary escape after the single-digit `P\d` alternative. `P\d`
   matches ONE digit, so `P14` stopped matching and every two-digit foreign
   attribution was silently re-admitted — the exact class of bug I was
   fixing, re-introduced by the fix. It surfaced only because I re-ran the
   existing round-352 fixture in the same command as the new one. Now pinned
   as `test_the_widening_still_reads_a_two_digit_prediction_id`.

3. **I re-serialised two JSON registries in the wrong format and had to
   redo both.** `state/prediction-bank-ledger.json` first came out with the
   new entry appended rather than inserted, and a "tidy" re-sort then moved
   two pre-existing out-of-order keys (`431` after `435`, `472` after `474`)
   that are not mine to move — 36/22 lines instead of 20/6.
   `skills/trigger-cases.json` came out at `ensure_ascii=False` against a
   file written with `True`: 70/40 lines for four added entries, against
   30/0 once matched. Both were caught by reading `git diff --stat`, which
   is the only reason they are two paragraphs and not two defects.

4. **P8 was self-destroyed and I should have seen it when banking.** It
   predicted the suite would read exactly `1084 + 5 = 1089 passed`, in a
   round whose whole plan was to add tests. Round 402 banked the same shape
   and named it; I banked it anyway.

5. **The evidence is still wrong for round 479 and this round did not fix
   it** (§3.1). `| debt | outcome |` is not a scoring line either. The
   general repair is a positive attribution requirement, which would reject
   every legitimate `| P8 | … | **HIT** |` table row, so it is not available
   cheaply. Recorded, caveated, not solved.

## 8. Tests

`skills/run_checks_fast.sh` — the whole corpus tier, run solo (`nproc` is 1):

```
before (this round's first run, at cd51182):
  carryforward  ERROR K001,K002,K003   4 error(s), 31 warning(s)
  unit_tests    ERROR rc1              5 failed, 1084 passed in 179.01s
  corpus-check: 10 checker(s), 4 error(s), 8 warning(s)      [225.6 s of checker time]

interim (four errors repaired, this round's own bank not yet registered):
  carryforward  ERROR K001             1 error(s), 31 warning(s)
  unit_tests    ERROR rc1              2 failed, 1127 passed in 181.54s
  corpus-check: 10 checker(s), 2 error(s), 8 warning(s)

after (own bank registered, scored, at the END of the round):
  carryforward  warn K004              0 error(s), 31 warning(s)
  unit_tests    ok                     1129 passed in 186.01s
  corpus-check: 10 checker(s), 0 error(s), 7 warning(s)      [232.4 s of checker time]
```

**1084 + 40 new + 5 repaired = 1129, exactly.** All 40 new tests are in
`test_carryforward_check.py`; the 5 repaired are the five this round was
sent to fix; **no pre-existing test changed outcome**. The interim row is
kept because it is the honest middle: the two failures there are the same
K001 twice, and both cleared on registration rather than on any fix.

Two warnings moved and neither is a defect. `skill_lint` B002 held at 7
across the round. `state_claim_check` went `5 claim(s) / coverage 4 of 11
items` to `2 / 2 of 8` and dropped its S005: it derives its claims from the
NEWEST next-steps block, so a new round's next-steps replaces the text it
samples. That is the instrument re-pointing, not a regression — and it means
the checker's coverage figure is a property of the last round to write, which
nothing in its output says.

Per-suite, solo:

```
skills/session-inheritance-audit/scripts/test_check_round_recorded.py   93 passed
skills/skill-authoring/scripts/test_carryforward_check.py               95 (94 + the K001 node)
skill_lint --house skills/evidence-must-name-its-subject/               1 skill, 0 errors, 0 warnings
case_coverage.py                                     103 skills, 434 cases, 0 errors
```

`xref_check` **0 NEW** dangling citations. `claim_check` 330 paths resolved,
0 stale (up from 326 — four new paths, all this round's). `placeholder_check`
0 errors.

## 9. Predictions — 7 HIT, 4 MISS, 1 SPLIT of 12

Banked in `state/skills/round-489/PREDICTIONS.md` at commit `7d865a6`,
before §2-§6 was measured. §0 recorded two open QUESTIONS rather than bets,
per round 483's step 19.

| # | claim | outcome |
|---|---|---|
| P1 | the loader parses fine and returns `{}` because `escalations` IS `{}`; the test cannot tell empty from unparseable | **HIT** — and the loader degrades to `{}` on four distinct states, all indistinguishable to the caller |
| P2 | the round-484 anchor is bolded and the file carries the digits unbolded | **HIT**, exactly — `## 11. Predictions — …` |
| P3 | the round-484 entry was written by round 484 itself | **HIT** — `scored_by: 484` |
| P4 | K003 on round 479 is a FALSE POSITIVE; the string comes from the ledger entry's own prose fields | **MISS**, both clauses. It is a TRUE positive, and `own` is round 479's corpus scope. See §7.1 |
| P5 | 479 and 485 are the same defect, two instances | **MISS** — 485 is a clean true positive with correct evidence; 479 is a true positive with evidence about round 473. Different failures that happen to share a symptom |
| P6 | the honest disposition for 486 is `unscored`, not a record-gap registration | **HIT** — and for the predicted reason: the gap registry is for rounds with no heading, and 486 has one |
| P7 | 0 errors afterwards, warnings stay ≥ 30 | **HIT** — 0 errors, 31 warnings at the end of the round. One wrinkle worth recording rather than hiding: its stated basis ("the four errors are the only ERROR-severity findings on the line") was falsified by the act of banking, which created a fifth (K001 on this very file). The claim held; the reason given for it did not |
| P8 | 1089 passed, no other test changes outcome | **SPLIT** — the second clause HELD exactly (1084 + 40 new + 3 repaired = 1127). The number is self-destroyed: I predicted a total for a round whose plan was to add tests |
| P9 | the K003 fix is one function, < 25 lines of non-test code | **MISS** — a module constant, `_attributable`, a split of `score_evidence`, `findings`, two new functions and a CLI arm. The prediction assumed the defect was the regex; the regex was the cheap half |
| P10 | the registry-test fix is in the TEST, not the loader | **HIT** — the loader's fail-safe degradation is correct; the test's precondition was not |
| P11 | 0 errors after the fix; corpus wall clock 200-400 s | **HIT** on time (228 s of checker time, 3 m 48 s of script). The errors half is P7's |
| P12 | ≥1 checker goes red on this round's own work | **HIT** — `carryforward` K001 fired on `state/skills/round-489/PREDICTIONS.md` the moment it was banked, and is still the round's last open error |
| P13 | K003 still fires somewhere in the ledger after the fix, i.e. I am not deleting a live check | **MISS as written** — 2 `unscored` entries remain (132, 486) and neither trips it. The concern behind it was answered far better than the bet asked: K003 produced TWO live true positives this round, which is direct evidence rather than the indirect kind P13 requested |

**The miss shape, named.** P4, P5 and P9 are one bet: *the checker is wrong
and the fix is small.* All three lost, and they lost in the same direction —
I read a diagnostic's summary and inferred its mechanism instead of reading
the twenty lines that produce it. That is the round's own headline finding
applied to the round: **P4 is me acting on a verdict without reading the
evidence.** Banked as step 21 of `prediction-banking` would be the obvious
move; it is not, because the existing steps already say to re-derive, and
what actually failed was cheaper than a rule — I had `scan()` open in the
next command and banked first.

## 10. Skill

**`skills/evidence-must-name-its-subject/SKILL.md`** — new, not an upgrade.
The nearest neighbours were checked and none owns the territory:
`matching-is-not-locating` is about a RECORD's anchor citing the wrong
coordinate; `suppressor-shares-the-detector-shape` is about widening a
detector that has a suppressor; `audit-the-deriver-first` is about a deriver
producing values. This one is about a **detector publishing a verdict and an
evidence line where only the verdict is tested**.

Seven steps, each ending in a checkable outcome; six pitfalls, each a named
mechanism (including "fixing the filter moves the wrong evidence" and "the
evidence is a function of document order"); a Verification section whose four
commands were each run as written before shipping. Three positive trigger
cases (`emns-near` / `emns-mid` / `emns-far`) phrased outside this repo's
vocabulary — a dependency scanner's advisory text, a changelog-publication
check, a two-month-old CI lint warning — plus a discriminating negative
(`emns-neg-no-evidence`: a detector that emits no evidence at all, which the
skill's own "when NOT to use" excludes). 430 → 434 cases.
`skill_lint --house` 0 errors, 0 warnings. Registered in
`state/known-unprobed-skills.json` with skills(B) owning the live probe.
**No priced call of any kind was made this round.**

The description needed two trims to clear D002 (1143 → 1048 → under 1024),
which is the third consecutive skills(B) round to hit that ceiling on its
first draft.
