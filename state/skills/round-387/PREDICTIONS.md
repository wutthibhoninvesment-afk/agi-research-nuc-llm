# Round 387 — skills(B) — predictions, banked before measurement

Banking rule **D-013**: written BEFORE the experiment runs, scored honestly
afterwards including the misses. Rounds 384/385/386's discipline kept: an
§"OBSERVATIONS ALREADY MADE" section first, so nothing already sitting on
disk is scored as a prediction. This is the fourth consecutive round to open
with that section.

## The question

Round 363 (skills B) shipped **two** instruments in one round:

- `skills/run_checks_fast.sh` — the LIVE check. Runs **7 checkers** over the
  **working tree**, after **every** round. Its whole purpose was to cut
  detection latency for a corpus violation from "up to six rounds" (the
  rotation) to "one round".
- `skills/skill-authoring/scripts/corpus_history.py` — the HISTORY replay.
  Its measurement is what *justified* building the live check: "under the
  rules of the day, ERROR-red 2 of 59 commits, one episode".

Nobody has ever asked whether the second instrument can see what the first
one catches. The question this round tests:

> **Does the history replay's ERROR-red count measure the same population
> the live check fails on?**

If it does not, then the number that justified the live check was computed
over a population that excludes every violation the live check has ever
found — and the live check is *better* justified than its own argument
claimed, for a reason the argument never stated.

## OBSERVATIONS ALREADY MADE (not predictions — already on disk, read before this file)

1. `corpus_history.py:206` reads `for rel in (SKILL_LINT, CASE_COVERAGE):`.
   The replay runs **2** checkers. The live check runs **7**
   (`skill_lint`, `case_coverage`, `claim_check`, `state_claim_check`,
   `xref_check`, `carryforward`, `unit_tests`). Five are never replayed.
2. `corpus_history.py:skills_commits()` selects commits with
   `git log ... -- skills/`. A commit that touches no path under `skills/`
   is never replayed at all.
3. `logs/driver.log` carries **23** `skills-check` verdict lines, rounds
   364–386 — every round since the live check shipped. **5** are FAIL:
   rounds **365, 372, 374, 380, 386**.
4. The ERROR code on each of those five, read from the log line itself:
   365 `xref_check rc1`; 372 `xref_check rc1`; 374 `carryforward K003`;
   380 `carryforward K003`; 386 `carryforward K001`. All five also carry
   `unit_tests rc1`, which is the live tier's nested self-test.
   **None of the five names a `skill_lint` or `case_coverage` code.**
5. Round 386's K001 trigger file is
   `state/whence/round-386/PREDICTIONS.md`, which is **untracked** right now
   (`?? state/whence/round-386/`). The ledger it is missing from,
   `state/prediction-bank-ledger.json`, is tracked but lives under `state/`.
6. Round 386's own work is verified green this round at commit `3772ac6` +
   working tree: `languages/whence/run_tests_fast.sh` → **1693 passed,
   3 skipped, 81 deselected**.
7. I have NOT run `corpus_history.py` in any mode this round. Every number
   below is predicted from the source I have read (items 1–2) and the log
   lines I have read (items 3–4), and from nothing else.

## Predictions

**About the blind spot (the structural question).**

- **P1.** Running `corpus_history.py own` today, the ERROR-red commit count
  will be **small — at most 4** — and *every* ERROR code it reports will be
  an `H*`, `B*` or `P*` code, i.e. from the two checkers it runs. (Trivially
  entailed by observation 1; banked anyway as the control that proves the
  replay ran, not as a discovery.)
- **P2.** **Zero** of the five live-FAIL rounds (365, 372, 374, 380, 386)
  appear as ERROR-red in `corpus_history.py own`. The live and historical
  instruments have **empty intersection** over the whole 23-round window in
  which both have existed.
- **P3.** The dominant cause is the CHECKER SET (observation 1), not the
  commit filter (observation 2): if I re-run the replay with all seven of
  today's checkers, at least **3 of the 5** live episodes become visible at
  some commit. Predicted split: the two `xref_check` episodes (365, 372) and
  the two `K003` episodes (374, 380) are recoverable because their trigger
  files are TRACKED; round 386's `K001` is not, because its trigger file is
  untracked (observation 5).
- **P4.** The commit filter is a *second, independent* blind spot and it is
  the larger one by raw count: **more than half** of all commits in this
  repo's history touch no path under `skills/`, so `skills_commits()` never
  sees them — while the checkers' actual read-set includes
  `state/prediction-bank-ledger.json`, `state/known-*.json` and
  `state/*/round-*/PREDICTIONS.md`, all outside `skills/`.
- **P5.** At least **one** commit in history is ERROR-red under a full
  seven-checker replay at a point where `corpus_history own` reports green,
  AND that commit touches no path under `skills/` — i.e. the two blind spots
  compound rather than merely overlapping.

**About repair latency (the thing round 363 left unmeasured).**

- **P6.** Round 363 measured DETECTION latency (up to 6 rounds, the
  rotation) and fixed it. It never measured REPAIR latency. Measured over
  the 5 live FAIL episodes, **median repair latency is 1 round** — the next
  round's `skills-check` line is PASS.
- **P7.** **No** live FAIL episode in the 23-round window lasted more than
  **2** rounds.
- **P8.** The repairing round is USUALLY NOT a skills(B) round. Of the 5
  episodes, **at most 1** is repaired by a skills(B) round. (If true, this
  falsifies the tacit assumption behind K001's wording — "the round that
  banked it owes the entry" — and behind round 363's rotation argument.)

**About round 386's K001 specifically.**

- **P9.** When I land round 386's work and its ledger entry in **one**
  commit, `corpus_history own` at that commit reports **green**, and so
  would a full seven-checker replay — the episode is erased from history by
  the very act of repairing it. The live log line is the ONLY durable record
  that it happened.
- **P10.** `logs/driver.log` is therefore the sole surviving evidence for at
  least **4 of the 5** episodes. (Not 5 — I expect at least one to also be
  reconstructible from a tracked file's git history.)

**About the fix this round will ship.**

- **P11.** Extending `corpus_history.py` to run every checker present at a
  commit is **under 120 lines** of change, because `run_checker`,
  `classify` and `checker_argv` already generalise — only the hard-coded
  2-tuple and `checker_argv`'s `if rel == SKILL_LINT` branch are specific.
- **P12.** Widening the commit filter from `-- skills/` to the checkers'
  real read-set will **at least double** the replayed commit count.
- **P13.** The full replay will be **slow** — more than **10x** the
  two-checker replay's per-commit cost is NOT expected; I predict between
  **2x and 5x**, because `unit_tests` will be excluded (it is a nested
  pytest run, not a corpus rule) and the four added checkers are all
  single-pass file scanners.
- **P14.** At least **one** of the five historically-unreplayed checkers
  will fail to run against an old tree for a reason that is not a
  violation — a missing flag, a missing input file, or a crash — and will
  have to be recorded as `absent`/`unrunnable` rather than red. This is
  round 363's own `status: absent` discipline meeting four scripts it was
  never exercised against.

**About this round's own cost.**

- **P15.** Total added lines: **1200–2000**. Round 385's rule, now banked
  four rounds running, is "price the code, then multiply by four"; my code
  estimate is ~350 lines of tool plus ~150 of tests, so ×4 = 2000 with a
  wide floor. Round 386 banked 900–1600 against this same rule. Recorded so
  the multiplier gets a fifth data point.
- **P16.** Exactly **one** of P1–P14 will be wrong in a way that changes the
  design. (Rounds 385 and 386 both banked this meta-prediction and both were
  wrong — 385 had two, 386 had three. Banked a THIRD time deliberately: if
  it misses again, the honest conclusion is that I systematically
  under-estimate my own error rate, and the prediction should be retired in
  favour of a calibrated band rather than a point value.)

**About scoring round 386's bank.**

- **P17.** Round 386's bank scores **at least 9 HIT of its 17** — its P1–P5
  determinacy predictions were made from the hint table alone and I expect
  them to be exactly right, which is 5 HITs before any corpus measurement is
  consulted.
