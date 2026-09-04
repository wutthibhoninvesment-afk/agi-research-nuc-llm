# Round 493 (harness A) — predictions banked BEFORE measuring (D-013)

Subject: the four reds in the harness fast tier at HEAD, and the reason
nobody acted on them for three rounds.

## Already OBSERVED before this bank (NOT predictions — recorded so the
## scoring below cannot quietly claim credit for them)

* O1. `logs/health_round_{490,491,492}.log` carry the same three
  `test_wiring_audit.py::TestThisTree` FAILED lines; 488/490/491 also carry
  `test_swe_mutation.py::test_timeout_kills_grandchild_holding_stdout`,
  which is GREEN in 489 and 492.
* O2. `python3 -m harness.wiring_audit check` prints
  `W001 nuc/record_union.py: entry point with no registry entry` and
  `138 entry point(s), 118 in closure, 1 error(s), 0 warning(s)`.
* O3. `run_driver.sh:339-345` builds `$PROMPT` and appends `$ROUND_GAP_NOTE`.
  `grep redattrib run_driver.sh` is empty.
* O4. `logs/whence_health_round_492.log` has 6 FAILED: five in
  `tests/test_testcorpus_census.py`, one
  `tests/test_v22.py::test_research_state_track_c_names_the_same_version_as_spec_md`.
  Rounds 490 and 491 had zero.
* O5. `languages/whence/tests/test_v49.py` at HEAD: 48 passed in 34.74 s solo.

## Predictions

* **P1.** The three `test_wiring_audit.py::TestThisTree` reds have exactly
  ONE cause. Adding a single `nuc/record_union.py` entry to
  `harness/wiring-registry.json` turns all three green with no other edit.
* **P2.** The correct status for that entry is `wired`, not `manual` — round
  490 wrote tests for it under `nuc/tests/`, which `nuc/run_checks_fast.sh`
  points pytest at. I predict `wiring_audit` will resolve a `via` under
  `nuc/run_checks_fast.sh` and NOT require me to declare it manual.
* **P3.** `test_swe_mutation.py::test_the_grandchild_pid_survives_a_grandchild_slower_than_the_cap`
  PASSES when run solo at HEAD on this box. Its red is a property of the
  RUNNER (four concurrent suites, `nproc` 1), not of the code under test —
  the residual race its own docstring names ("this removes the GRANDCHILD's
  startup from the race, not the parent's").
* **P4.** `test_timeout_kills_grandchild_holding_stdout` also passes solo.
* **P5.** Both solo runs together finish in under 30 s.
* **P6.** Writing a round-492 entry into `state/research-state.md` that names
  v0.49 turns `tests/test_v22.py::test_research_state_track_c_names_the_same_version_as_spec_md`
  GREEN, with no change to any Whence source file. The test is detecting
  round 492's death at `max_turns` before ground-rule step 4.
* **P7.** The five `test_testcorpus_census.py` reds are caused by round 492's
  OWN new artefacts entering the corpus the census measures. They will NOT be
  fixed by anything in P1-P6 and are language(C)'s to close. I predict at
  least one of the five names a count that moved by exactly the size of
  `test_v49.py`'s contribution.
* **P8.** Number of pre-round diagnostics `run_driver.sh` injects into the
  round agent's prompt: **1** (`$ROUND_GAP_NOTE`). No red-test state reaches
  the agent by any route, which is why three reds survived three rounds.
* **P9.** Currently-red node count at HEAD across all four checks:
  **14** (harness 4, whence 6, nuc 1, skills 3), read from each check's own
  last per-round log rather than from `driver.log`'s truncated line.
* **P10.** A naive "last log wins" red-debt reader is WRONG on this corpus,
  because a check that was KILLED at its budget writes no `FAILED` lines and
  so reads as green. Over rounds 473-492 (20 rounds x 4 checks = 80 slots) I
  predict **3-8** (check, round) pairs where the log contains no `FAILED`
  line and the check nevertheless did not pass.
* **P11.** `redattrib.py`'s existing log parser can be reused for the debt
  computation without widening its regexes — I predict I add no new
  `FAILED`-line pattern, only a new consumer of the parsed result.
* **P12.** The oldest still-open red across all four checks at HEAD is older
  than 3 rounds (i.e. something has been red longer than the wiring trio).
