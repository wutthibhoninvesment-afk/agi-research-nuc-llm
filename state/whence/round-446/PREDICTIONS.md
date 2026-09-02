# Round 446 (language C) — predictions, banked BEFORE measuring

Rule D-013: written before the command was run. Scored honestly below in the
round's knowledge file. Round 435's next-step 7 applies too: where I have no
basis I say so rather than guessing, and an abstention is recorded as an
abstention, not as a hit.

Subject: round 444's next-step 4 — "the exit contract is misleading for 3 of
the 5 field programs that run ... `--strict-miss` (round 384) exists and
nothing in the corpus tooling uses it; `curecheck.survey` records `rc` and not
whether anything was dropped."

## Already DERIVED by reading, therefore NOT predictions (recorded so I cannot
## later re-label them as hits)

- D1. `curecheck.replay` DOES call `run_program(tmp, strict=True)` and records
  `strict_rc` (curecheck.py:765-766), and `main`'s `replay` branch prints
  `%d clean under --strict-miss`. So round 444's clause "nothing in the corpus
  tooling uses it" is FALSE as written; its second clause (`survey` records
  `rc` only) is TRUE. Read at curecheck.py:706-786, 1218-1241, 1330-1350.
- D2. `Interpreter.DROP_CAP`'s justifying comment (interp.py:577-582) says
  "the whole tracked example corpus drops 0". `examples/dropped.lang` is
  tracked and `tests/test_examples.py::test_dropped_reports_the_one_miss_it_
  drops_on_purpose` asserts it prints `dropped: 1 miss value ...`. The comment
  cannot be true at HEAD.

## Predictions

- P1. Sweeping all **18 tracked** `examples/*.lang` under `--strict-miss`,
  exactly **1** (`dropped.lang`) will exit 1 *because of a drop* (i.e. exits 0
  without the flag and 1 with it). Basis: D2's comment claims 0 and is stale by
  exactly the deliberate one; nothing else in the tracked corpus is documented
  to drop. Confidence: medium — the comment is already known wrong once.
- P2. At least one tracked example OTHER than `dropped.lang` prints a
  `dropped:` line. Basis: none beyond suspicion of D2's staleness. This
  DIRECTLY CONTRADICTS P1; both are banked on purpose so that whichever way it
  falls, one of them is a scored miss. Confidence: low.
- P3. `python3 curecheck.py corpus` summary line will read
  `15 file(s): 5 parse, 5 reach a value (rc=0), 3 mechanical edit(s) in total`.
  Basis: SPEC.md's recorded 14-file line is `4 parse, 4 reach a value (rc=0),
  3 mechanical`; round 444 says 5 field programs run; the 15th program
  (`agi_buy_and_hold.lang`) is unread by me. Confidence: low on the first two
  integers, medium on `3 mechanical`.
- P4. Re-deriving round 444's number: of the field programs that reach a value,
  exactly **3** drop a miss (`expense_tracker`, `mini_agi_guardian`,
  `prod_showcase_final`). Confidence: medium — it is a carried number, and
  three consecutive rounds have found carried numbers change on re-derivation.
- P5. `agi_buy_and_hold.lang` (the 15th gateway program, which I have not
  opened): **I have no basis and will report what it holds.** Not a guess.
- P6. The `len(interp._observed) < interp.DROP_CAP` guard in `b_print`
  (interp.py:3317) has **no test** — nothing exercises the documented
  "past the cap the recorder errs toward REPORTING" behaviour. Basis: none;
  I have not opened `tests/test_v32.py`. Confidence: low.
- P7. `grep -rn "reach a value" tests/` will return **0** matches — i.e. no
  test pins `_fmt_survey`'s summary sentence, so adding a column to it breaks
  nothing. Confidence: medium.
