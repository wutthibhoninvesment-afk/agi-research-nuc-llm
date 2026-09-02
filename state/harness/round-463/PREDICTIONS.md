# Round 463 (harness A) — predictions banked BEFORE any measurement

Rule D-013: written before the baseline was run, before any code changed.
Subject: round 461's next-step 1 — *`corpus_check.run_one` unlinks its
`tempfile.mkstemp` sink in a `finally`, so no round can say WHICH test failed
inside any red `unit_tests` row, ever.* Owner split named there: skills(B)
owns the file, **harness(A) owns the log-retention convention**. This round
is harness(A).

Everything below was derived from code READ (`skills/skill-authoring/scripts/
corpus_check.py`, `harness/redattrib.py`, `run_driver.sh`, `.gitignore`) and
from `state/research-state.md`. Where I have no basis I say so instead of
guessing — round 435's next-step 7.

## A. Re-derivations of carried numbers (round 460 item 5 / 461 item 9)

- **P1.** Round 461 says "`unit_tests` is 25 of the 60 red checker-rows".
  I predict that pair does NOT reproduce at HEAD: two more skills-health
  logs (462, and 461's own) have landed since, so both numbers should be
  **>= 25 and >= 60**. Sixth-consecutive-round rule says the carried number
  is more likely stale than exact.
- **P2.** `unit_tests` is still the single reddest checker row in
  `logs/skills_health_round_*.log` — more red rows than any other checker.

## B. The evidence loss itself

- **P3.** ZERO of the historical red `unit_tests` rows can be resolved to a
  failing test nodeid from anything in the repo today. The `finally:
  os.unlink(sink_path)` has no exception, so the child's output is gone on
  every branch, including the timeout branch round 451 explicitly repaired
  for *parsing*.
- **P4.** What IS recoverable from a red `unit_tests` row is (a) the codes
  token, which for a pytest child is the synthetic `rc1` (`run_one` sets
  `errors = ["rc1"]` when rc==1 and `_findings_in` parsed nothing), and (b)
  the `summary` field, which is pytest's own LAST line — under `-q` a count
  line. So the COUNT of failures survives and the IDENTITIES do not.
  Confidence: high on (a), medium on (b) — I have not opened a red log.
- **P5.** No file in the repo currently mentions `corpus-evidence`
  (`git grep -c corpus-evidence` == 0). The path is new, so no ignore line,
  no reader, and no `state/known-standing-dirty-paths.json` entry exists.

## C. What the fix must not break

- **P6.** Adding a line of the form `evidence: <checker> -> <path> (...)` to
  `corpus_check.py`'s stdout does NOT match `redattrib.CORPUS_ROW`
  (`^(\w[\w.]*) {2,}(ok|warn|ERROR|TIMEOUT|ABSENT)`): the name group is
  followed by `:` rather than two spaces, so `parse_corpus_row` returns None
  and the historical row counts are unchanged.
- **P7.** `driver_line`'s FAIL branch joins `lines[-5:]`, so with the
  `corpus-check:` summary last and at most four evidence lines above it, a
  round with a single red checker gets its evidence PATH into `driver.log`
  with no change to `run_driver.sh` at all.
- **P8.** The round number can be read from `state/round_counter` rather
  than passed by the driver: `run_driver.sh` writes `ROUND` to that file at
  the top of the loop iteration (line ~258) and launches the four health
  checks later in the SAME iteration (line ~542). Therefore this fix takes
  effect on **round 463's own skills-check**, with no one-round re-exec lag
  of the kind round 457's item 1 had to warn about.

## D. Baselines I will measure (no basis for the value — I will report what
## it holds)

- **P9.** Byte size of a red `unit_tests` pytest `-q` output. I have never
  seen one. No prediction; I will cap retention and report the real number.
- **P10.** Whether `harness/` fast tier is green at HEAD. No basis: round
  462 was a language round and the last recorded harness-tier state I have
  is round 457's "exited 0, count lost". I will run it and report.
- **P11.** Whether any red row in the corpus logs is a checker OTHER than
  `unit_tests` whose evidence would also have been worth keeping. No basis
  — I will print the per-checker red table rather than guess.

## E. Scope commitments

- **P12.** The `.gitignore` line lands in the SAME commit as the wiring.
  Rounds 363/365, 409 and 441 all wired a per-round log without one and all
  three tripped the NEXT round's record-gap check as an unattributed `??`.
- **P13.** Retention is conditional on the run being NOT CLEAN. A green
  corpus check writes zero bytes and creates no directory, so a repo whose
  checks pass never grows this tree at all.
