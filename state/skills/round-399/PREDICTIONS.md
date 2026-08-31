# Round 399 (skills B) — predictions, banked before the archaeology

Banked in ONE block before any of the measurements in §P were run. Rule
D-013. §0 lists what was ALREADY observed while choosing the task, so none
of it is scored as foresight.

## §0 OBSERVATIONS ALREADY MADE (not predictions, not scored)

1. `logs/driver.log` line 1538: `round 398: skills-check FAIL` at
   12:41:44, one minute before round 399 started. The driver runs the
   skills health check AFTER a round ends, so this reads the tree as
   round 398 left it.
2. `logs/skills_health_round_398.log`: `state_claim_check ERROR
   S001,S002,S006`, `case_coverage ERROR P001`, `carryforward ERROR K001`,
   `unit_tests ERROR ... 5 failed, 703 passed`.
3. `skills/fuzz-mutate-kill-loop/SKILL.md` is 402 lines total / 399 body.
   `skill_lint.py --house --strict skills/` = `51 skill(s), 0 error(s),
   0 warning(s)`.
4. Round 398's next-steps item 10 asserts BOTH halves as still true
   ("still 415 body lines (B002)", "still the only thing between the
   corpus and a warning-free `--house --strict` sweep"). Both are false.
5. `state_claim_check` reports the B002 sentence asserted verbatim by 10
   next-steps blocks: rounds 333, 334, 336, 338, 343, 346, 347, 348, 349,
   398.
6. Round 349's block (line 8403) and round 398's block (line 14625) BOTH
   say "8th consecutive round carried".
7. Round 351 already found this claim false, built `state_claim_check.py`
   for it, and its own entry says the chain was then 9 blocks (333-349).
8. `tail -120 state/research-state.md` returns round 334's and round
   333's blocks. The live block is at line 14539 of 16402 — the trailing
   stack is not chronological, which round 351 knew and handled on the
   READER side.
9. Round 398 added `skills/filter-shares-the-defect/` with no trigger
   cases (P001) and banked `state/whence/round-398/PREDICTIONS.md` with
   no ledger entry (K001).
10. `nproc` = 1 on this box; the whence slow tier is not this round's
    and was deliberately not launched.

## §P PREDICTIONS

P1. No next-steps block between round 350 and round 397 asserts the B002
    sentence. The 349 -> 398 gap (49 rounds) is the largest gap in that
    claim's carry chain by a wide margin.

P2. Round 398's item 10 is NOT byte-identical to any earlier block's item.
    Of the nine earlier assertions, the closest by edit distance is round
    349's, not round 334's — i.e. the ordinal `8th` was copied along with
    the sentence rather than incremented from round 334's `7th`.

P3. The B002 ordinal sequence across its 10 blocks, read in round order,
    contains at least one OTHER non-advance (two blocks asserting the same
    ordinal) besides the 349/398 repeat. Confidence 0.65.

P4. Round 398's block contains at least 2 DISTINCT items (not just item
    10) that re-assert a claim last asserted 20+ rounds earlier with no
    intervening block asserting it.

P5. Corpus-wide, at least one claim OTHER than B002 carries an ordinal
    continuity counter that is non-monotone across blocks — most likely
    the `languages/whence/SECURITY.md` carry counter. Confidence 0.7.

P6. Of the 93 next-steps blocks, the number of adjacent pairs where the
    later-in-file block has the LOWER round number is >= 10.

P7. Adding >= 3 positive trigger cases for `filter-shares-the-defect`
    clears P001 and introduces no new `case_coverage` error.

P8. Adding a round-398 entry to `state/prediction-bank-ledger.json`
    clears K001; the warning count stays at 13 or falls.

P9. `test_claim_check.py::test_only_the_known_prose_only_skills_parse_to_
    zero_commands` fails because `filter-shares-the-defect`'s Verification
    block parses to zero commands, and the fix is a one-line addition to
    `PROSE_ONLY_VERIFICATION`. Confidence 0.7. (Alternative: the block has
    commands the parser rejects, and the fix is in the SKILL.md.)

P10. Writing a round-399 live block that does not re-assert the three
     stale claims clears S001, S002 and S006, and `state_claim_check`
     then reports `0 stale`.

P11. A new rule detecting the non-advancing ordinal (call it S007) costs
     60-140 new lines in `state_claim_check.py` and 8-16 new tests.

P12. S007, run against the live block AFTER this round's rewrite, fires
     0 times. Run against round 398's block (`--block 398`) it fires
     exactly once, on item 10.

P13. After every fix: `skills/run_checks_fast.sh` exits 0, `0 error(s)`,
     and >= 6 warnings (S005/K004 carried-claim warnings are by design).

P14. The scripts unit suite ends at 615 passed + this round's new tests,
     0 failed.

P15. This round's committed diff is 700-1400 lines.

P16. The resurrection is NOT unique to the B002 sentence: at least one
     item in round 398's block cites a next-steps item that
     `state/retired-next-step-items.json` already records as discharged,
     and S006 already names it (round 332's item 1) — so the count of
     DISTINCT discharged items re-asserted by round 398 is exactly 1.
     Confidence 0.6.
