# Round 517 (harness A) — predictions, banked before measuring

CLAUDE.md rule D-013: written BEFORE the measurement, scored honestly after.
Banked at the point where the RED DEBT had been *reproduced* (that run is
reported below as ALREADY OBSERVED, not predicted) and before a line of
`harness/hookaudit.py` existed.

## Already observed before this bank was written — NOT predictions

* O1. `skills/skill-authoring/scripts/corpus_check.py` run SOLO on an idle
  box reproduces both red nodes: `carryforward ERROR K002` and
  `unit_tests ERROR rc1` (4 failed / 1210 passed / 182.99 s). Not the
  runner, not contention. All four failing `unit_tests` nodes are
  carryforward nodes, so the two reds are ONE cause.
* O2. The K002 error is round 516's own ledger entry. Its quote
  `**30 keys across four gates, 7 seen — 23.3%.** No gate was total over its
  own document.` IS in `knowledge/round-516-the-check-that-ranged-over-a-
  fragment.md` — at line 83, hard-wrapped, with a NEWLINE where the ledger
  quote has a space. `carryforward_check.py` tests `e["quote"] not in body`,
  a raw substring test.
* O3. The live `.git/hooks/pre-commit` is `ours` and byte-identical to
  `escalationguard.hook_script()` (5166 bytes both sides, 0 diff lines), so
  the `stale` state round 515's next-step #2 asks for would be GREEN today.
* O4. All four hook steps exit 0 today under the interpreter `python3`
  resolves to in this session (`.venv/bin/python3`, 3.12.3).
* O5. `git rev-parse --git-path hooks` inside a linked worktree returns the
  MAIN repo's `.git/hooks` (probed on a throwaway repo). So a fast-tier node
  that reads the installed hook reads the same file from a
  `pristine_check.py` worktree as from the live tree.

## P — the carryforward red

* P1. The wrap is the WHOLE cause. Collapsing whitespace runs to a single
  space on both sides makes round 516's quote match, and no other scored
  entry's verdict changes under that normalisation.
* P2. Exactly ONE of the 189 scored entries matches under whitespace
  normalisation but not literally (round 516's). Predicted count: 1.
* P3. There IS no established convention of embedding a literal newline in a
  ledger quote: **zero** of the 189 scored entries has a `\n` inside its
  `quote` field. If that is wrong and some do, the honest reading flips —
  516 broke a convention rather than tripping a blind checker.
* P4. Most quotes are short enough never to be at risk: I predict **fewer
  than 25** of the 189 quotes are longer than 76 characters (the corpus's
  hard-wrap column), i.e. long enough that a wrapped source file MUST break
  them.
* P5. The prior episodes of this node are NOT this cause. I predict at most
  one earlier K002 episode in the retained record was a line-wrap; the
  recurrence is the node, not the defect. (Round 515 established that the
  `RECURRENT` count and the underlying cause are different questions.)
* P6. Normalising K002 requires normalising K005 (`body.count`) and K006
  (`foreign_scopes`) in the same pass, or a quote can pass K002 and report
  `occurs 0 times`. I predict the K005/K006 verdicts over the whole ledger
  are UNCHANGED by the normalisation (0 new K005, 0 new K006).

## P — the harness capability (`harness/hookaudit.py`)

* P7. Both of round 515's next-step #2 states exist in the tree today with
  nothing checking them, and I predict a THIRD, unnamed by that next step:
  the installed hook names four script paths and four verbs, and NOTHING
  checks that those paths resolve. Step 1 is guarded by
  `[ -f "$top/…" ] || exit 0`, so moving `harness/escalationguard.py`
  silently disables the only BLOCKING guard, and every existing test —
  which asserts about `hook_script()`, a string — still passes.
* P8. All four script paths named by the installed hook DO resolve at HEAD
  (4/4 present). The gap is unguarded, not currently violated.
* P9. `hook_script()` first appears in `harness/escalationguard.py` at the
  round-475 commit and in no earlier revision, and the number of DISTINCT
  generated bodies over the whole file history is between 4 and 8 (four
  step-adding rounds 475/499/501/515 plus comment edits).
* P10. Step count per generation is monotonically non-decreasing over
  history and ends at 4; exactly one step is blocking in every generation.
* P11. A parser keyed on the invocation SHAPE (`<python> "$top/<rel>" <verb>`)
  parses every historical generation without a special case. If it does not,
  that is the same staleness defect one level up and I will say so.
* P12. Adding a `stale` state to `hook_status()` changes no existing
  `harness/tests/test_escalationguard.py` verdict — all 41 nodes stay green.

## P — the tiers

* P13. `languages/whence/run_tests_fast.sh` (round 516's next-step #1, left
  unrun by that round) completes GREEN: 0 failed, and between 3020 and 3040
  passed (round 515 measured 2999 passed / 3 skipped; round 516 added +31
  nodes in `tests/test_checkscope.py`).
* P14. `harness/run_tests_fast.sh` completes green with this round's new
  nodes: 0 failed, ≥ 1680 passed, wall clock 440–560 s serialised.
* P15. Re-running `corpus_check.py` after the carryforward repair returns
  `carryforward` and `unit_tests` to non-ERROR, i.e. `2 error(s)` → `0
  error(s)`, with the seven warnings unchanged.
* P16. `harness/readset.py blast` on this round's working-tree diff names
  `harness/tests/test_escalationguard.py` among its suites, and does NOT
  name the new `harness/tests/test_hookaudit.py` (round 505: a read set
  cannot name a file you just added).
