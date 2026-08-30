# Round 373 (harness A) — predictions, banked before measuring (D-013)

Written 2026-08-30 ~17:12 UTC, before any `grep` of `logs/driver.log` for
`record-check` lines and before a line of the fifth gap shape existed.

## The question

Round 370's next-steps item 7, restated as round 371's item 5 and round
369's item 10, addressed to the track that owns the checker:

> A process cost worth naming: the record-gap check has flagged this same
> known, deliberately-unresolved file at the top of ten straight rounds,
> each paying the same inspection. A third category — *known-escalated
> tracked-file diffs*, distinct from both "leftover work" and "standing
> untracked" — would let the checker report it as acknowledged. Belongs to
> harness(A)/skills(B), who own the checker.

Round 349's own objection is the constraint the design has to satisfy:
allowlisting a TRACKED file another system edits "would mean 'never look at
this diff again', which is the wrong answer".

## OBSERVATIONS ALREADY MADE BEFORE THIS FILE WAS WRITTEN

Not predictions. This is the starting state, read before writing anything
below (round 361's P2 was VOIDed for blurring this line).

- This round's own injected note flags **3** unattributed dirty paths:
  `languages/whence/SECURITY.md`, `languages/whence/SPEC.md`,
  `languages/whence/examples/self_eval.lang`. Two of the three are round
  372's genuinely uncommitted leftover work (v0.28 SPEC section + the
  `is_compound` cost gate in the guest evaluator); one is the escalation.
- `languages/whence/SECURITY.md` mtime is 2026-08-29 23:32:41 UTC, the same
  second as the Hermes-gateway files allowlisted in
  `state/known-standing-dirty-paths.json`.
- `check_round_recorded.py` is 721 lines and carries FOUR gap shapes
  (rounds 171/259/273/291). `unattributed_dirty_paths` is shape 4.
- `run_driver.sh` injects the checker's stdout into the next round's prompt
  under a fixed preamble naming only shape 1 ("the round(s) below ran per
  logs/driver.log but have no state/research-state.md entry yet").
- whence fast tier at the working tree: **1595 passed, 3 skipped,
  70 deselected** in 42.59 s.

## Predictions

- **P1.** `logs/driver.log`'s own `record-check FOUND gap(s)` lines mention
  `languages/whence/SECURITY.md` in **>= 10** distinct rounds. (Rounds 369
  and 370 say "twelfth"/"tenth consecutive round" in prose; nothing has
  checked that against the log.)
- **P2.** In **more than half** of those rounds, SECURITY.md is the *only*
  unattributed dirty path in the line — i.e. the check fired entirely on an
  item already adjudicated and deliberately left open.
- **P3.** The FIRST `record-check` line naming SECURITY.md is **round 349**
  (the round that escalated it), not 350.
- **P4.** SECURITY.md is the ONLY tracked file in this repo that qualifies
  as a known-escalated third-party diff today; the new registry ships with
  exactly **1** entry. (`CLAUDE.md` was the other candidate and round 349
  committed it.)
- **P5.** SECURITY.md's working-tree content has not moved since round 349:
  no commit touching `languages/whence/SECURITY.md` exists after round
  349's, and its mtime is still 23:32:41 — so a content fingerprint taken
  today is the same diff round 349 adjudicated.
- **P6.** No test anywhere in the repo asserts that the injected NOTE's
  preamble matches the gap shape actually reported. The mis-framing (a
  working-tree finding announced as "the round(s) below ran ... but have no
  research-state.md entry") is untested and unremarked in any round file.
- **P7.** No test in the repo greps for the preamble substring `have no
  state/research-state.md entry yet`, so rewording the preamble needs
  **zero** edits to existing tests.
- **P8.** The checker's own unit tests live under
  `skills/session-inheritance-audit/`, not `harness/tests/`, and number
  **>= 20**.
- **P9.** After this round lands (round 372's leftover committed + the fifth
  shape shipped), a live `check_round_recorded.py` run prints **0**
  unattributed dirty paths and **1** acknowledged escalation, and still
  exits **1** — because round 372's missing research-state.md entry is a
  real, separate gap that this round does not manufacture an entry for.
- **P10.** The `resolved` state (a registry entry whose path is no longer
  dirty — a dead acknowledgement, the analogue of round 372's
  `test_each_exemption_is_load_bearing`) has **zero** live instances today.

## Scoring

Scored in `knowledge/round-373-*.md` and in this round's research-state.md
entry; the bank is registered in `state/prediction-bank-ledger.json`.

## Supplementary prediction, banked mid-round

Added ~17:55 UTC, AFTER P1-P8 were scored and the fifth shape was
implemented, but BEFORE the counterfactual below was computed. Banked
separately so the ordering is visible rather than implied.

- **P11.** Replaying rounds 349-373's own `record-check FOUND gap(s)` lines
  with the fifth shape in place: in **at least 10** of the 25 rounds the
  check would have produced NO finding at all (exit 0, no NOTE injected
  into that round's prompt), because SECURITY.md was the only unattributed
  path AND the line carried no other gap section.
