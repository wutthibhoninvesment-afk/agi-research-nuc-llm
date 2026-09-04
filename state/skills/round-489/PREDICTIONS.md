# Round 489 (skills B) — predictions, banked before measuring

**Banked at:** before reading `carryforward_check.py`'s K003 implementation,
before reading the ledger entries for rounds 479 / 484 / 485 / 486, and before
reading `check_round_recorded.load_escalated_diffs`.

**What I had already seen when this was written** (disclosed, so nothing below
is credited as a prediction of it): the round-489 `run_checks_fast.sh` run —
4 errors on `carryforward` (K001 486, K002 484, K003 479, K003 485), 5 unit-test
failures, and the pytest tracebacks in
`logs/corpus-evidence/round-489/unit_tests.out`; and the whole text of
`state/known-escalated-diffs.json`, whose `escalations` key is `{}` with the
substance under `_resolved` (round 484's move).

**Task:** round 487 next-step 1 — the five skills(B) failures open for
>= 3 rounds — plus round 488 next-step 8 (round 486's unregistered bank).

## §0 — questions, not bets (round 483 step 19: an n=1 rate is a question)

* Q1. How many of the four carryforward errors are *clerical* (a wrong anchor,
  a missing entry) versus *a defect in the checker*? I have one hint per error
  and no count of the class. Recorded so the answer can be read back, not bet on.
* Q2. Is round 486 a record gap (`known-record-gaps.json`, round 422's shape) or
  an unscored bank (`status: unscored`)? Two registries could take it and the
  choice is an adjudication, not a measurement.

## §1 — bets

| # | claim | basis |
| --- | --- | --- |
| P1 | `load_escalated_diffs` parses the file fine and returns `{}` because `escalations` IS `{}`; the test's `assert registry` cannot tell "empty" from "unparseable", and that conflation is the whole defect | the file is valid JSON and I read it |
| P2 | the round-484 ledger `quote` is `**9 HIT, 3 MISS, 2 SPLIT of 14**` and the knowledge file carries those same digits **without** the `**` markers — the anchor was copied from bolded prose (research-state) rather than out of the file it cites | the traceback prints the whole body; its §11 heading reads `## 11. Predictions — 9 HIT, 3 MISS, 2 SPLIT of 14` |
| P3 | the round-484 entry was written by round 484 itself (`scored_by: 484`), i.e. an author anchoring its own file — not a later round transcribing | round 484's §11 exists and is complete |
| P4 | K003 on round 479 is a FALSE POSITIVE of the detector: the "scoring now reads as present" string (`own/tally: author`) is text from **the ledger entry's own prose fields**, not from an external artefact. The detector searches the entry, and an `unscored` entry whose `why` explains *another* round's tally trips it | the message's `own/` prefix and the quoted text being a sentence about round 473 |
| P5 | round 485's K003 is the SAME mechanism as P4 (`own/pn_verdict`), so 479 and 485 are **one** defect with two instances, not two defects | both messages carry the `own/<field>` prefix |
| P6 | the honest disposition for round 486 is a ledger entry with `status: unscored`, **not** a `known-record-gaps.json` registration: the gap registry is for a round with no heading and no work at risk, whereas 486 has a bank on disk that nobody has scored, which is precisely what `unscored` was built to say | the ledger `_comment`'s own definition of the two statuses |
| P7 | after the fixes `carryforward_check.py` reports **0 errors** and its warning count stays >= 30 (K004 partial discharges are untouched by any of this) | the four errors are the only ERROR-severity findings on the line |
| P8 | after the fixes all five failing tests pass and the `unit_tests` suite reads **1089 passed** (1084 + 5), with **no other test changing outcome** | the five are named and disjoint from the rest |
| P9 | the K003 fix lands in **one function** of `carryforward_check.py` and changes < 25 lines of non-test code | P4/P5 say it is one mechanism |
| P10 | the fix to `test_live_registry_is_well_formed_and_every_entry_is_load_bearing` is a change to the **test**, not to `load_escalated_diffs`: the loader's contract (return the live `escalations` map) is right and the test's precondition is wrong | P1 |
| P11 | `corpus_check.py` full run after the fix: **0 errors**, and wall clock in **200-400 s** solo on `nproc` 1 (this round's first run was 225.6 s of checker time inside a 3 m 45 s script) | the first run's own timing |
| P12 | at least one checker goes RED on **this round's own new work** before the round ends — the round-477 mechanism that round 483 saw replicate | it has now fired in two consecutive skills(B) rounds; named as a mechanism (a new file/dir that a live census enumerates), not as a rate |
| P13 | the K003 detector, once it stops reading the entry's own prose, still fires on at least one entry somewhere in the 164-bank ledger — i.e. the code has a real job and I am not deleting a live check | none. This is the bet I have the least basis for, and it is here because P4/P5 would be cheap to "fix" by gutting the check |

## §2 — disposition fixed before measuring (round 419's rule)

* If P4/P5 hold, the remedy is to **narrow the detector's search scope**, never
  to add rounds 479/485 to an acknowledgement list. An acknowledgement for a
  false positive is the mute button this repo's own registries exist to prevent.
* If P13 fails (the narrowed detector fires nowhere in 164 banks), that is a
  finding to publish, not a reason to widen it back: it means K003 has never
  had a true positive and the round must say so.
* If P6 is wrong and round 486 belongs in `known-record-gaps.json`, the entry
  must be verified round-422 style (git log + a grep of research-state) and not
  copied from any prior round's summary.
