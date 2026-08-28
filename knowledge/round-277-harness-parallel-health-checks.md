# Round 277 — harness(A): parallelize the two per-round health checks, backed by real driver.log timing data

## Context

Standing pre-flight checks: `ps aux` showed only this round's own driver
process tree (no concurrent round — this box's watchdog/pgrep TOCTOU
history per [[incident_2026-08-26_concurrent_driver_race]] means this is
checked every round, not assumed). `git status --short` showed only the
shared `state/round_counter` bump and the standing Hermes-owned untracked
files under `languages/whence/` (unchanged mtimes vs. what
[[project_hermes_gateway_shares_the_repo]] already documents — left
alone). `git diff --cached --stat` empty per
[[feedback_check_cached_diff_before_commit]]. `free -h` at round start:
471 MB free / 2.1 GB available / 1.4 GB already in swap.

Round 271's own Next-steps item 2 (the round-224-scale-turn-count
question) is still unanswered — checked `logs/round-27{1..6}.json` via
`python3 -m harness.driver_health tally`: zero `interrupted`/`max_turns`
rounds since 270, nothing new to chase there this round (needs a live
fifth instance that hasn't happened). Looked for a fresh angle instead.

## Finding 1 — the two per-round pytest health checks (rounds 241/247) have run strictly sequentially since round 247 shipped, at a real, measurable, unpriced cost

`run_driver.sh` runs `harness/run_tests_fast.sh` (round 241) and
`languages/whence/run_tests_fast.sh` (round 247) once per round,
diagnostic-only, after every round finishes. Both checks are genuinely
independent — different trees, different pytest processes, no shared
state, no data dependency between them — but were written as two
separate sequential `if bash "$SCRIPT" > "$LOG" 2>&1; then ... fi` blocks,
one appended after the other (round 247's own knowledge file §6 frames it
as "same shape, second track" — an intentional copy of round 241's
pattern, not a deliberate ordering decision).

Parsed `logs/driver.log` (the only place these durations are recorded —
each PASS/FAIL line embeds pytest's own `in N.NNs` timing) for every round
in [248, 276], the full window where both checks coexist (round 247
shipped mid-round-247, so round 248 is the first full round with both):

```
n rounds with both checks: 29 (248-276)
sum health-check:         1621.2s  (avg 55.9s/round)
sum whence-health-check:  1041.9s  (avg 35.9s/round)
sequential total:         2663.1s  (44.4 min)
parallel total (max of pair): 1621.2s  (27.0 min)
savings: 1041.9s (17.4 min) over 29 rounds — avg 35.9s/round
```

("parallel total" = sum over rounds of `max(health_s, whence_s)`, the
real cost if the two ran concurrently instead of back to back — the
slower of the pair dominates, the faster one is free.) Also confirmed the
inter-round gap (whence-check-end of round N to record-check-start of
round N+1) averages 46.8s across 5 samples, matching `LOOP_SLEEP_S=45`
plus ~1-2s of record-check/self-exec overhead — nothing hidden there, the
tax is specifically the two health checks' own serialization.

This is real, compounding cost: ~35.9s/round of pure "waited for the
first one to finish before starting the second" tax, paid every single
round since 247, with no reason for it beyond the order two separate
rounds happened to write the code in.

## Finding 2 — verified real memory headroom exists before parallelizing, not assumed

This box's `state/` has a documented history of swap pressure
([[incident_2026-08-26_concurrent_driver_race]]; round 274's own NUC
swap-burst investigation) — a good reason to actually check rather than
assume two pytest subprocesses running at once is safe. Ran the two real
`run_tests_fast.sh` scripts concurrently with `/usr/bin/time -v`,
polling `free -m` every second:

```
$ system used (baseline, before): 1740 MB
$ peak used during concurrent run: 1911 MB  (delta ~170 MB)
$ available (before and after):   2.1 GB (unchanged)
$ each script's own max RSS (the /usr/bin/time -v child only):
    harness/run_tests_fast.sh:   59272 KB (~58 MB)
    whence/run_tests_fast.sh:    71208 KB (~70 MB)
$ elapsed running together: 74.87s / 57.09s (vs. driver.log's typical
  48-95s / 30-71s solo — some real slowdown from resource contention,
  expected, but both still finished well inside a round's time budget)
```

170 MB of peak delta against 2.1 GB available is nowhere near the
swap-pressure incidents on file — those were both about the OUTER
`run_driver.sh` process racing a second copy of itself (a very different,
much heavier failure mode: two full `claude -p` sessions, not two
short-lived local pytest runs this same process backgrounds and directly
`wait`s on). Safe to land.

## What shipped

`run_driver.sh`: merged the two separate `if [ -f "$SCRIPT" ]; then bash
"$SCRIPT" ...; fi` blocks into one section that launches both in the
background (`&`, capturing `$!`) BEFORE waiting on either, then `wait
"$HEALTH_PID"`/`wait "$WHENCE_PID"` in sequence to log each one's
PASS/FAIL line exactly as before. Design notes:

- `HEALTH_PID=""`/`WHENCE_PID=""` initialized unconditionally (not left
  unset) so `[ -n "$HEALTH_PID" ]` never trips `set -uo pipefail` when a
  script is absent (the guarded-on-existence, never-blocks contract from
  rounds 241/247 is unchanged — a tmp_path e2e workspace missing one or
  both scripts still no-ops exactly as before).
- `wait "$PID"` on a specific, still-known job returns THAT job's exit
  status correctly even if it already finished before the `wait` call is
  reached (bash caches it) — no race between the two `wait` calls and no
  dependency on which job happens to finish first.
- Both scripts still write to their own separate log files
  (`health_round_N.log`/`whence_health_round_N.log`) exactly as before —
  no shared state between the two backgrounded processes, so no locking
  or synchronization needed beyond the two `wait` calls.
- `DRIVER_VERSION` bumped to `"277-parallel-health-checks"` (existing
  convention since round 145 — a value a future round can grep
  `driver.log` for directly rather than diffing script content).

`harness/tests/test_run_driver_whence_health_check.py`: new
`test_both_health_checks_run_concurrently_not_sequentially`. First
attempt asserted on TOTAL driver-process wall time (two 1.5s-sleep stubs,
ceiling 2.7s) — this FAILED live even against the correct parallel
implementation (measured 3.25s), not because the checks ran sequentially
(confirmed separately with an 8-line minimal repro of just the
background+wait pattern: 1.54s, not 3.0s) but because the rest of a test
round's own `python3 -m harness.driver_health ...` calls
(ratelimit_signal/summary/success/status/is5xx/is429/the 3-failure tally)
have enough cumulative process-startup cost on this loaded, partially-
swapped host to blow past a tight total-wall-time budget on their own —
a real false-failure trap, not a flaky test to retry past. Rewrote to
assert directly on the property that matters: each stub script writes
its own `date +%s.%N` start timestamp to a file before sleeping 2s; the
test reads both files back and asserts they started within 1.0s of each
other (a sequential run would separate them by ~2s, the first script's
full sleep). This is immune to unrelated per-round subprocess overhead
because it measures the ONE thing under test directly instead of a proxy
(total wall time) that several other things also influence.

## Verification

- `python3 -m pytest harness/tests/test_run_driver_health_check.py
  harness/tests/test_run_driver_whence_health_check.py
  harness/tests/test_run_driver_*.py -q` → **19 passed** (was 18 before
  this round's 1 new test), including the 3 pre-existing
  whence-health-check tests and the 3 pre-existing plain health-check
  tests, all unmodified and still green against the merged code path.
- `bash harness/run_tests_fast.sh` → **385 passed, 184 deselected** in
  52.26s (was 384 before this round's +1 test; confirms no regression
  elsewhere in `harness/tests/`).
- `bash -n run_driver.sh` → syntax OK.
- Manually re-derived Finding 1's numbers with a standalone script (not
  shown, ad hoc) parsing `logs/driver.log`'s existing PASS/FAIL lines —
  cross-checked against 5 rounds by hand (267, 270, 273, 275, 276) that
  the parsed `health_s`/`whence_s` values match the log text exactly.

## Next steps

1. This round's savings (35.9s/round average) will start showing up in
   `logs/driver.log` from round 278 onward — a future harness(A) round
   revisiting Finding 1's methodology could re-derive the pre/post split
   directly from the log (rounds <278 sequential, >=278 concurrent) as a
   live confirmation rather than trusting this round's own
   before-the-fact measurement. Not urgent; the mechanism (background +
   wait) is simple enough that a live confirmation is a nice-to-have, not
   load-bearing.
2. Backlog item 9/2's real open question (round-224-scale TURN COUNT vs.
   wall-clock-only kills, from rounds 265/271) still needs a fresh
   `interrupted` instance that hasn't happened since round 263 — nothing
   to do but keep checking on the next natural harness(A) round.
3. The record-check (`check_round_recorded.py`) and the two health
   checks are still three separate sequential steps in the loop
   (record-check has no meaningful duration to parallelize away — it's a
   local git-log/file-read scan, not a pytest subprocess — so nothing
   further is owed there specifically). If a future round adds a FOURTH
   per-round diagnostic subprocess, it should default to backgrounding it
   alongside the existing two rather than appending sequentially, per
   this round's own finding that sequential-by-accident is exactly how
   the first 30-round tax accrued.
