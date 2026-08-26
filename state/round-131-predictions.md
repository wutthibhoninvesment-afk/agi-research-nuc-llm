# Round 131 — SWE-loop(D) — predictests (banked 2026-08-26, BEFORE the fresh campaign runs)

Context: inheritance audit found round 113's and round 125's campaigns both hit the SAME
undocumented bug independently — `campaign.py`'s `corpus`/`verify`/`triage`/`oracle_kill`
stages regenerate Mutant objects (and AST site indices) from the LIVE file on disk
(`rebuild_mutants(self.root, ...)`), not from a pinned copy of what `stage_mutation`
actually generated ids against. Both campaigns' `mutation`/`recheck` stages ran for ~1 hour
while a concurrent language-track session edited `whence/interp.py` (round 113: the "Time-
Travel Debugger v0.7" commit `8637795` landing mid-recheck at 22:44:35; round 125: the same
commit already landed, but a *further* uncommitted "v0.13" WIP edit from a concurrent
`round-126` session landed mid-mutation-run) — so every later-stage id lookup silently
matched nothing (`if m is None: continue`), producing `found=0`/`no_killer=0`/`seconds≈0`
misread as "ran clean, nothing new" instead of "never ran". Confirmed directly: regenerating
`generate()` on the CURRENT tree matches NONE of round-125's 35 survivor ids. Fixed
(`campaign.py`): `self.files`' content is frozen into `<out>/snapshot/` the moment
`stage_mutation` reads it; every downstream stage rebuilds Mutant objects (and, for
`corpus`/`oracle_kill`, the "original" package used for behavioural diffing) from that
snapshot instead of the live tree. New regression test
`test_swe_campaign.py::test_downstream_stages_survive_a_concurrent_edit_to_the_mutated_file`
(falsified against the pre-fix code: fails immediately with `FileNotFoundError` — no
snapshot exists — confirming the test actually exercises the bug).

`whence/interp.py` is now 2687 lines (v0.11 SPEC committed + an uncommitted v0.13 WIP:
`_check_ret` written by round 127 as a from-a-different-track fix so the tree would import
at all). `generate()` on the current tree yields 1276 mutants (already measured while
diagnosing the drift bug above — NOT a blind guess, excluded from scoring below).

| # | prediction | band |
|---|---|---|
| P1 | fresh mutation baseline wall time, workers=5, timeout=240s (round 125: 3226.4s for 1263 mutants / 730 tests; suite is now 777 tests) | 3100-4100s (52-68 min) |
| P2 | fresh mutation baseline raw score (first pass, before recheck) | 96.0-98.0% |
| P3 | subset-basis survivors that flip to killed under the (now-fixed, exhaustive) recheck | 30-70% of them |
| P4 | TRUE final survivor count after the fixed recheck+corpus+triage+oracle_kill pipeline | 15-40 |
| P5 | coverage stage wall time (full suite, 777 tests, settrace) | 350-750s |
| P6 | corpus-kill stage: survivors killed by the differential corpus search (now that the pipeline can actually run instead of silently no-op'ing) | 0-15% of survivors (r107: 4.5%, r113/r125 both corrupted-0%) |
| P7 | triage: `other` (unclassified) share of survivors, now that site indices resolve against the pinned snapshot instead of a possibly-shifted live file | within +/-10pp of round-113's LAST valid-looking triage-adjacent read (untested this round; treat as exploratory, not banked from a real prior number) |
| P8 | oracle-kill stage (modes/frames/counters) on no_killer survivors | 1-8 kills |
| P9 | standing host fuzz (2 seeds x400) + oracle fuzz (2 seeds x300, one at --limit 6000) | 0 findings (p lower than usual: v0.13's WIP `_check_ret` is new, untested-beyond-suite code on every call's return path) |
| P10 | guest differential (self_eval.lang) 2 fresh seeds x300 | 0 divergences (not confident either way -- standing rule says "not dry") |
| P11 | live kill/repair reached this round given campaign wall-clock cost | more likely NOT reached in this single session (campaign alone is ~1-1.5h before live stages) |
| P12 | full harness + whence suites stay green after the campaign.py snapshot fix (besides its own new/updated tests) | yes, 0 unrelated regressions |
| P13 | at least one of my new tests wrong on first run (standing base rate) | already TRUE this round (the triage `other==0` assertion was wrong on first attempt, fixed before this file was even banked -- noting honestly rather than re-predicting a known outcome) |
