# Round 125 — SWE-loop(D) — predictions (banked 2026-08-25 ~23:50, BEFORE the fresh campaign runs)

Context: inheritance audit found round 113's campaign (`state/swe/round-113/`) ran its
`recheck` stage (22:15:23-23:11:34) concurrently with a DIFFERENT session's edits to
`whence/interp.py` (the "Time-Travel Debugger v0.7" commit `8637795`, landed 22:44:35,
+96/-27 lines: `_kind`/`_type_match` structural-types helpers + `typed` builtin, i.e. the
tree is now v0.12-ish though nothing bumped the version marker). `interp.py` is 2484
lines in round 113's baseline, 2580 lines now (confirmed stable — matches HEAD, nothing
uncommitted). Separately (before finding the file drift), forensics on round 113's own
20/20 `subset_flips` anomaly found a REAL, file-drift-independent bug: `_BUILTIN_TABLE`
is a process-wide lazy singleton (`@register(name, arity)` lines execute ONCE per pytest
process) and `tests/test_examples.py` runs every example via `subprocess` — both classes
are invisible to the by-file settrace coverage map, so `MapPrioritizer`'s `subset=True`
"a green covering subset is survived by construction" claim is unsound. Fix applied
(`campaign.py::stage_recheck`): every subset-basis survivor is now verified against the
full suite (not a 20-sample) before being reported `survived`; new regression test
`test_swe_bymap.py::test_subset_check_verifies_all_survivors_within_the_cap_not_a_sample`
(passed first run — already falsifies the standing "one new test wrong" base rate, see P10).
Fresh `generate()` count on the current tree: 1263 mutants (up from 1226).

| # | prediction | band |
|---|---|---|
| P1 | fresh v0.12-tree mutant count (`generate()` on current interp.py) | 1250-1400 |
| P2 | fresh by-file coverage collection wall time (23 test files, up from 20) | 300-550s |
| P3 | fresh mutation baseline wall time, workers=5 | 3000-4800s (50-80 min) |
| P4 | fresh mutation baseline raw score (first pass, before recheck) | 96.5-98.5% (r113: 97.39% pre-recheck) |
| P5 | subset-basis survivors that flip to killed under the NEW exhaustive recheck | >=60% of them (r113 sample: 20/20 = 100%) |
| P6 | TRUE final survivor count after exhaustive subset verification + timeout recheck | 5-25 (r113's naive "12" was mostly/all unverified false survivors) |
| P7 | recheck stage wall time (now exhaustive, not a 20-cap sample) | 15-60 min |
| P8 | standing host fuzz (2 seeds x400) + oracle fuzz (2 seeds x300, one at --limit 6000) findings | 0 (structural types/`typed` are new and likely outside the fuzz grammar, so this doesn't test them meaningfully) |
| P9 | guest differential (self_eval.lang) seeds 119+120 x300 | 0 divergences (p~=0.5 per the standing "not dry" rule) |
| P10 | at least one of my new tests wrong on first run (has held ~5 of last 6 rounds) | already MISS this round (test_swe_bymap.py's new test passed clean on first run) |
| P11 | live kill/repair reached this round given the campaign's wall-clock cost | more likely NOT reached within a single session (campaign alone is ~1.5-2.5h); if reached, kills 1-4 of a small n |
| P12 | full harness + whence suites stay green after the `stage_recheck` fix (besides the fix's own new/updated tests) | yes, 0 unrelated regressions |
