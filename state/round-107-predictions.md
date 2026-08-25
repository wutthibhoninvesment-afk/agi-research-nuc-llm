# Round 107 — predictions BEFORE measuring (banked 2026-08-25 ~15:20)

Track D (SWE-loop). Context held, not predicted (read from the tree at round
start, before any new measurement):
- Round 101's mutation stage checkpointed **519 of 1056** v0.9 mutants
  (`state/swe/round-101/mutation.partial.jsonl`, ids prefix-identical to a
  fresh `generate()` over the unchanged `interp.py` of 2026-08-24 21:20):
  458 killed, 42 survived, 19 timeout. Three "timeouts" took 22,071 s (6.1 h),
  three more 1030–2020 s: `subprocess.run(timeout=)` killed pytest but a
  grandchild `run.py` held the stdout pipe, so the post-kill `communicate()`
  blocked. Remaining 537 mutants: const 163, cmp 131, arith 81, ifneg 69,
  bool 51, not 42.
- Survivors under 5-way load cost 83–178 s each (suite 48 s idle); the
  slowest KILLED mutant took 1074 s.
- An orphaned round-106 `nuc/lane_bench.py` (PID 33941, `olmoe` child at
  111 % CPU) is running at round start; it will end on its own (3 cases left).
- Nested `claude -p` auth verified: sonnet-5, $0.023, 3.2 s.
- Round-101 P7 already scored in its file (A: MISS/MISS/MISS/HIT; B: HIT/HIT/MISS/HIT).

- **P1 (v0.9 baseline, all 1056, after recheck):** score **90–93 %**,
  survivors **75–105**. The checkpointed half is 91.9 % (42 survivors in 519)
  and the remaining half is const-heavy (163 of 537); const mutants on
  budgets/cache sizes survive most. Round 101's 93–96 % is already
  contradicted by the partial. Conf 60 %.
- **P2 (recheck of timeouts, serial, 600 s, idle-ish):** ≥50 % of the
  timeouts flip (killed or survived); ≥1 stays a real timeout (an `ifneg` on
  the driver loop is an infinite loop). Conf 65 %.
- **P3 (process-group fix):** after the fix, no mutant's wall time exceeds
  `timeout + 15 s` and `ps` shows no orphaned `run.py`/pytest after the run.
  The regression test (grandchild holding stdout) fails on the OLD code and
  passes on the new one. Conf 80 %.
- **P4 (coverage triage, targeted):** 30–60 % of survivors sit on lines the
  suite never executes (conf 50 %); corpus kill rate on uncovered survivors
  > on covered ones (conf 60 %); `killed_on_uncovered` = 0–2 (multi-line
  expressions only) (conf 60 %).
- **P5 (corpus: 300 random + examples + round-29 extra programs):** kills
  **25–45 %** of survivors. Conf 55 %.
- **P6 (live kill, sonnet, 8 `no_killer` survivors, 20 steps):** kills 3–6 of
  8; ≥1 `equivalent_claimed`; ≥1 claimed-equivalent is genuinely equivalent
  on my reading. Conf 55 %.
- **P7 (repair bench, sonnet, 6 killed mutants, 25 steps, read budget 12):**
  green 3–5 of 6; exact 2–4; ≥1 green-not-exact; 0 cheated; mean cost
  ≤ $0.60 per attempt. Conf 50 %.
- **P8 (pins):** 100 % of corpus- and model-found killers re-kill their
  mutant from the pinned file alone. Conf 70 %.
- **P9 (standing campaigns, after mutation to avoid load skew):** host fuzz
  2 × 400 → 0 crash signatures (70 %); oracle fuzz 2 × 300 → 0 findings
  (65 %); guest differential 1 × 300 → 0 divergences (70 %).
- **P10 (cost):** whole live lane (kills + repairs; review already paid by
  round 101) ≤ **$12** CLI-reported. Conf 60 %.
- **P11 (process):** ≥1 of my own new tests fails on first run. Conf 55 %.
- **P12 (wall, mutation resume: 537 mutants, 4 workers, 400 s timeout, one
  core taken by the orphan for the first ~10 min):** **40–80 min**
  (~60 survivors × ~140 s / 4 workers ≈ 35 min + killed tail). Conf 55 %.
- **P13 (campaign completes end-to-end this round for the first time since
  round 29 — report.md written):** yes. Conf 65 % (four D rounds died).

**Amendment (15:45, before any campaign result):** the pipe-hang mechanism
stated in the context block above was FALSIFIED by running the grandchild
scenario through the OLD `run_mutant` (`git show HEAD:harness/swe/mutation.py`):
Python 3.9's `subprocess.run` returns after `timeout` (kill + `wait()`, no
drain), leaving the grandchild ALIVE — that is round 30's orphan finding, and
the process-group fix stands for it. The 22,071-s durations (three mutants
ending within 20 ms of each other at 07:04:38) need another explanation;
hypothesis now: the Mac slept overnight (`time.time()` deltas include the
sleep). P3 is unchanged (no wall > timeout+15 s, no orphans); P12 unchanged.

**P14 (added 16:00, before writing the code — kill-first test ordering
learned from the baseline's own `FAILED tests/<file>` details, nearest
mutated line, leave-one-out):** on a 30-mutant random sample of KILLED
mutants re-run paired (default file order vs learned order, same load):
verdicts identical 30/30 (conf 90 %); the learned order's FIRST file kills
≥ 70 % of them (conf 60 %); median paired time ratio learned/default ≤ 0.5
and mean ≤ 0.6 (conf 55 %). Basis: 646 kills so far — 428 by
`test_examples.py` (already first alphabetically, median 2.2 s) and 218 by
later files (median 34–60 s each); the ordering can only move the second
group, so the aggregate gain is bounded (~2×), not the ~10× a per-test
coverage map would give.
