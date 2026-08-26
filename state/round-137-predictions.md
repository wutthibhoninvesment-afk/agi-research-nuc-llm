# Round 137 predictions — SWE-loop(D), fresh campaign under the round-131 snapshot fix

Banked before launching `state/swe/round-137/` (mutation -> recheck -> coverage ->
corpus -> verify -> triage -> oracle_kill -> live_kill -> repair -> report), reusing
`state/swe/round-125/mutation.json` for --prioritize-from and
`state/swe/round-125/coverage-by-file.json` for --coverage-map (stale by a few commits
of v0.13 WIP growth, used only for test-file ORDERING — stage_recheck's exhaustive
subset-check, per round 125's fix, makes the final verdict independent of map staleness).

Context: round 131 fixed the snapshot/drift bug (harness/swe/campaign.py, uncommitted)
but never ran its own fresh campaign (§4 of knowledge/round-131 left PENDING, no
state/swe/round-131/ directory exists). Rounds 113 and 125 both produced CORRUPTED
corpus/verify/triage/oracle_kill stages under the bug (found=0/no_killer=0 in seconds).
This round's job: get the first TRUSTWORTHY end-to-end numbers since round 107.

- **P1 (mutant count):** 1270-1320 (interp.py grew from 2580 to 2687 lines since
  round 125's 1263-mutant count; roughly proportional growth).
- **P2 (mutation baseline wall time, --workers 5 --timeout 240,
  --prioritize-from round-125/mutation.json):** 35-55 min (kill-first ordering should
  beat round 125's unordered 3226s baseline).
- **P3 (raw mutation score):** 96.5-98.5% (consistent with rounds 107/113/125's band).
- **P4 (recheck subset self-check):** 0-2 flips out of subset-basis survivors now that
  the `_BUILTIN_TABLE`/subprocess-invisible-coverage bug is fixed (round 125's own
  fresh 0/35 result, at n=1, is the base rate).
- **P5 (corpus stage, NOW TRUSTWORTHY):** found >= 1 (not 0 — the corrupted-report
  0/0/0.0s pattern should be gone; genuine "found=0" is possible but should come with
  nonzero seconds and a nonzero no_killer count).
- **P6 (triage counts):** `error_message` + `counter` + `budget` + `none_guard`
  together account for >=20% of survivors once the position-index bug is fixed (round
  125's corrupted 80%-`other` was diagnosed as the site-index misclassification, not a
  real distribution).
- **P7 (oracle_kill, frames mode specifically):** finds >=1 additional kill among
  survivors that the corpus/behavioural stages missed (backlog item 6's whole premise:
  the frame-charge oracle catches budget-arithmetic-equivalent mutants no value-based
  oracle can).
- **P8 (live_kill, n=16):** >=6/16 real kills at the model's first attempt (round 107's
  live kill was 0/8 with equivalence claims + prose-tool-call failures now partly
  mitigated by the completion guards built in round 109 — expect improvement, not parity).
- **P9 (live_repair, n=6):** >=4/6 exact reverts (round 107's repair was 5/6 at $0.05
  each; the completion guards should hold or improve this).
- **P10 (standing fuzz/oracle/guest campaigns, run after the main campaign):** 0 crash
  / finding / divergence signatures on 2 fresh seeds each — the standing base rate has
  held every round since 107 (round 107's own seed 115 was the one exception).
