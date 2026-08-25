# Round 113 — SWE-loop(D) — predictions (banked 2026-08-25 20:55, BEFORE any measurement)

Context: HEAD interp.py is exactly v0.9 (regenerates round 107's 1056 mutant ids); the
working tree is v0.11 (2484 lines) and yields 1226 mutants → a full re-baseline is due.
6 CPUs / 8 GB. Suite ≈ 66 s idle (654 tests, 20 files).

| # | prediction | band |
|---|---|---|
| P1 | v0.11 corrected mutation score (after recheck) | 86–90 % (v0.9: 87.5 %) |
| P2 | one FULL-trace run of the suite recording per-test-file hits (settrace, every line of interp.py) | 12–30 min wall |
| P3 | map fidelity: share of killed mutants whose `killed_by` file covers the mutated line (from the map) | ≥ 99 % (r107 instrument error 2/267) |
| P4 | covering-subset verdicts: aggregate survivor suite-time vs. full suite for the same survivors | ≤ 0.6× ; median survivor ≤ 80 s (was 116 s) |
| P5 | baseline campaign wall time, 5 workers, map-driven kill-first order + covering subset | 25–50 min (r107: 62 min, no ordering) |
| P6 | subset self-check: subset-survivors re-run with the full suite that flip to killed | ≤ 1 of 20 |
| P7 | survivors that are `const`; tunable allow-list (budget/cache constants keyed on enclosing name) | const 30–50 % of survivors; allow-list removes 20–40; score over remaining ≥ raw + 1.5 pp |
| P8 | oracle-kill stage (frames + direct + fast_slow + totality at limit 6000) on no_killer survivors | 3–12 kills, ≥ 3 by `frames` alone |
| P9 | corpus killers over survivors | 3–8 % (r107 4.5 %) |
| P10 | live kill n=16 (sonnet, guards on) | kills 1–4; equivalence claims ≥ 6; prose-tool-call FAILURES 0; guard_recoveries ≥ 1; $5–9 |
| P11 | live repair n=6 | ≥ 4 exact; ≤ $0.50 |
| P12 | guest differential seeds 117 + 118 (300 each) | 0 divergences (p ≈ 0.55) — the standing rule says it is NOT dry |
| P13 | host fuzz 2 seeds × 400 + oracle fuzz 2 seeds × 300 (one at --limit 6000) | 0 findings |
| P14 | kill-first with the map: share of kills landing in the FIRST file run | 60–85 % (r107 prioritizer: 66 %) |
| P15 | session turn budget (--max-turns 80) | finish with ≤ 75 turns used |
| P16 | at least one of my new tests is wrong on first run (rule: has held 4 of the last 5 rounds) | yes |
