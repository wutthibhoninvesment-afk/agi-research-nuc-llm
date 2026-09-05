# Round 514 (NUC-integration E) — predictions banked BEFORE measuring (D-013)

Written 2026-09-05 ~19:10 UTC, before any of the measurements below were run.
Context: `nuc/tests/test_survivor_impact.py::TestThisTree::
test_the_committed_report_is_about_the_subject_at_head` has been RED for six
rounds (since round 508, opened by this track). Reproduced this round:
`state/nuc/round-502/survivor-impact.json` carries `subject_digest`
`8082749f...` and `nuc/perturbation.py` at HEAD is `3b3923df...`. Round 508
(NUC E) added 243 lines to the subject and changed `survivor_impact.BATTERY`
and did not regenerate the report.

Box status this round: tailnet SSH to 100.78.44.111 timed out (connect
timeout 10 s). Offline round.

## The mutant-identity problem, stated before it is measured

A mutant id is `basename:line:op#i` and `i` is POSITIONAL among the mutants
`mutation.generate` emits. Round 497's `load_ledger` docstring already says
the same id on a moved source is a different mutant. So the ledger's 32
standing survivors cannot simply be re-read at the new digest; they have to
be RE-IDENTIFIED by content.

- **P1.** A content key of `(op, description, stripped source line, owner
  qualname)` will find a HEAD counterpart for **>= 28 of the 32** standing
  survivors. MISS if fewer than 28 match.
- **P2.** **>= 20 of the 32** will have a DIFFERENT id at HEAD than in the
  ledger (line shift and/or `#i` shift). MISS if fewer than 20 change.
- **P3.** Some content key will be AMBIGUOUS (two or more HEAD mutants share
  it) for **at least 1** survivor. MISS if the key is unique for all 32.
- **P4.** Re-scoring the matched mutants against `nuc/tests/
  test_perturbation.py` — whose sha256 is `7ac31f49...`, unchanged since
  round 502, so the grading suite is the SAME suite — will return `survived`
  for **>= 30** of them. MISS if 3 or more flip to `killed`.

## The report at HEAD

- **P5.** The new audit will move **>= 3** survivors out of
  `unreached_by_battery`, because round 508 put `reclaim_all` and
  `gap_commit` into the battery and fixed `wsweep_swap`'s channel (it had
  been running `steal`). MISS if 0-2 move.
- **P6.** `n_lines_executed_by_battery` will be **> 1105** (round 502's
  figure) for the same reason. MISS if it is <= 1105.
- **P7.** `moves_published_number` will be **>= 11** (round 502's count):
  a wider battery is more chances for a mutant to move an output.
  MISS if < 11.
- **P8.** One battery run is 7 subprocesses; measured cold this round at
  0.39 + 0.85 + 0.85 + 0.85 + 26.38 + 0.15 + 0.16 s, i.e. `population_swap`
  is ~89% of it. Predicted audit wall time **13-20 min** for 32 survivors
  (n+2 battery runs). MISS outside that band.

## The gate that did not exist

- **P9.** There is NO committed test comparing the report's `battery` /
  `battery_gap` fields against `survivor_impact.BATTERY` / `BATTERY_GAP`.
  The report says 5 battery names and `BATTERY` holds 7. So round 508's
  report staleness was invisible along a SECOND axis that no red reported.
  A gate added this round would have been red at HEAD before this round.
  MISS if such a test already exists.

---

## Scored, after measuring (D-013)

**2 HIT, 7 MISS.** Full table and the analysis in
`knowledge/round-514-the-report-that-was-stale-in-its-own-commit.md` §10.

| | outcome | measured |
|---|---|---|
| P1 | MISS | the population did not exist: 5 standing survivors, not 32 |
| P2 | MISS as stated | 81 of 87 ids changed (not "20 of 32") |
| P3 | MISS | 0 of 87 keys ambiguous |
| P4 | MISS as stated | 5 of 5 re-scored still `survived` |
| P5 | MISS | 0 survivors left `unreached_by_battery` |
| P6 | **HIT** | `n_lines_executed_by_battery` 1105 -> 1319 |
| P7 | MISS | `moves_published_number` 0, not >= 11 |
| P8 | MISS as stated | 366 s (6.1 min) for 5 survivors |
| P9 | **HIT** | no such gate existed; both new gates red at HEAD |

**Six of the seven misses share one cause.** P1, P2, P4, P5, P7 and P8 are all
denominated in "the 32 standing survivors", a number this file took from the
committed report instead of re-deriving it from the ledger — which is the
exact defect the round then found. A prediction's DENOMINATOR is a carried
claim and has to be re-derived like any other.
