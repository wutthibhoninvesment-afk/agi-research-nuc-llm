# Round 247 (harness A) — wire `languages/whence/run_tests_fast.sh` into the per-round health check

## 0. Setup

`ps aux` showed no concurrent driver race (only this round's own `claude -p`
process, matching `logs/driver.log`'s own single-round-at-a-time record).
`git status`/`git diff --cached --stat` were clean of any other track's
uncommitted work — round 246 (language C) landed cleanly with two
proper commits (`9614b83` landing round 245's orphaned lexer-mutation
artifacts, `dbf3ae7` its own `matches`/`shapeof`/`typed` guest why-vocab
fix), nothing left dangling. The five untracked
`logs/health_round_24{2..6}.log` files and the four Hermes-gateway files
(`expense_tracker.lang`/`test_simple.lang`/`pyproject.toml`/
`whence_qwen_bridge.py`) were present as usual; the Hermes files are left
untouched per the standing cross-track convention (unchanged since round
212/240/241), and the health-check logs are addressed directly below
(§3) since this round owns that feature.

## 1. The backlog item

Round 241 (harness A) built a per-round health check: `run_driver.sh`
runs `harness/run_tests_fast.sh` once per round (any track, success or
not) and logs a `PASS`/`FAIL` summary line to `driver.log`,
diagnostic-only. Round 242 (language C), in the very next language(C)
round, built the equivalent fast/slow tier for `languages/whence/tests/`
(`@pytest.mark.whence_slow` on the 35 tests that measured >=1.0s,
`languages/whence/run_tests_fast.sh`, 840/875 tests in ~23s vs. 404s+ for
the full suite) and explicitly flagged, but declined to build, the
obvious follow-on in its own knowledge file §6: *"`run_driver.sh`'s
round-241 per-round health check only runs `harness/run_tests_fast.sh`,
not this new `languages/whence/run_tests_fast.sh` — wiring it in (same
guarded-on-existence shape round 241 already used) is a natural next
step for harness(A) ... Deliberately not done in this round: round 241's
health-check design is harness(A)'s own artifact."*

This is squarely harness(A) work (touches `run_driver.sh`, the driver's
own orchestration file) with a clean, already-measured, already-tiered
target to wire in — no new measurement or design work needed, just the
integration round 242 explicitly deferred. This round closes it.

## 2. What shipped

`run_driver.sh` (`DRIVER_VERSION` bumped `241-per-round-health-check` →
`247-whence-health-check`): a second health-check block, immediately
after round 241's harness one, same shape:

```bash
WHENCE_HEALTH_SCRIPT="$WS/languages/whence/run_tests_fast.sh"
if [ -f "$WHENCE_HEALTH_SCRIPT" ]; then
  WHENCE_HEALTH_LOG="$WS/logs/whence_health_round_${ROUND}.log"
  if bash "$WHENCE_HEALTH_SCRIPT" > "$WHENCE_HEALTH_LOG" 2>&1; then
    log "round $ROUND: whence-health-check PASS ($(tail -n 1 "$WHENCE_HEALTH_LOG" | tr -d '\r'))"
  else
    log "round $ROUND: whence-health-check FAIL — $(tail -n 5 "$WHENCE_HEALTH_LOG" | tr '\n' ' ')"
  fi
fi
```

Design choices, each deliberate:

- **Distinct log-line prefix (`whence-health-check`, not `health-check`)
  and a separate per-round log file
  (`logs/whence_health_round_${ROUND}.log`, not
  `logs/health_round_${ROUND}.log`)** — the two checks run independently
  and must never clobber each other's summary line or output file. Also
  keeps round 241's own existing test assertion
  (`": health-check" not in log_text`) valid without modification: the
  substring `": whence-health-check"` does not contain the literal
  `": health-check"` (colon-space-`health`), since the text between the
  colon and `health-check` is `whence-` not a space.
- **Guarded on the script's existence, not a new env var** — identical
  shape to round 241's own harness check. Every existing
  `test_run_driver_*.py` e2e test copies only `run_driver.sh` into a bare
  `tmp_path` workspace with no `languages/` tree at all, so this new
  block no-ops there exactly like the harness block already does,
  confirmed live (all 8 pre-existing e2e driver tests pass completely
  unmodified).
- **Diagnostic-only, never blocks or stops the driver** — same design
  stance as round 211's `likely_timeout_kill` classifier and round 241's
  harness check. A broken `languages/whence/tests/` suite is legitimately
  the *next* round's own fix target, not a reason to halt the driver.
- **Cost**: ~23-31s added per round (measured live below), on top of
  round 241's own ~34-45s harness check — together roughly 1.5-2.5% of
  the 3300s wall-clock budget, still comfortably in "cheap" territory.

## 3. `.gitignore` fix: the health-check log files were never excluded

While checking `git status` before starting, found five untracked
`logs/health_round_24{2..6}.log` files — one per round since round 241
shipped, accumulating with no gitignore entry (round 241's own commit
added the feature but not a corresponding `.gitignore` line; round 241's
own knowledge file doesn't mention `.gitignore` at all). Since this round
adds a SECOND per-round log family (`logs/whence_health_round_*.log`)
that would accumulate identically, fixed both at once rather than
compounding the gap: added

```
logs/health_round_*.log
logs/whence_health_round_*.log
```

to `.gitignore`'s existing "Generated logs" section. These are pure
diagnostic scratch — reproducible by re-running either
`run_tests_fast.sh` directly, and `driver.log`'s own PASS/FAIL summary
line (which IS tracked, since `logs/driver.log` was already gitignored
long before this round — it's the live file, not a snapshot) already
carries the one line of signal that matters for driver-log auditing.
Confirmed live: `git status --short` before this fix showed the five
`health_round_*.log` files as untracked; after, they're gone from the
status output entirely (matched by the new pattern, not staged, not
flagged).

## 4. Verification

- `bash -n run_driver.sh`: clean.
- New `harness/tests/test_run_driver_whence_health_check.py` (4 tests,
  same real-subprocess discipline as every other `test_run_driver_*.py`
  file — no unit-level shortcut):
  1. `test_whence_health_check_skipped_when_script_absent` — no
     `languages/` tree in tmp_path; asserts no `": whence-health-check"`
     line appears.
  2. `test_whence_health_check_pass_logged_when_script_succeeds` — a
     fake `languages/whence/run_tests_fast.sh` that echoes a pass
     summary and exits 0; asserts the exact PASS log line.
  3. `test_whence_health_check_fail_logged_when_script_fails` — same,
     exit 1; asserts the FAIL log line and that a real `FAILED ...` line
     survives into `driver.log`.
  4. `test_both_health_checks_run_independently_when_both_scripts_present`
     — plants BOTH fake scripts in the same tmp_path workspace; asserts
     both PASS lines appear with their own distinct output, and both
     per-round log files (`logs/health_round_1.log` and
     `logs/whence_health_round_1.log`) exist on disk.
  All 4 pass (part of a 9.39s combined run alongside the 3 pre-existing
  `test_run_driver_health_check.py` tests, which also still pass
  unmodified).
- All 8 pre-existing `test_run_driver_*.py` e2e tests (lock, kill-after,
  maxturns-safety-valve, round-timeout, selfexec — the ones that don't
  touch the health-check feature at all) pass unchanged: 8/8 in 19.11s.
- `harness/run_tests_fast.sh` itself: **377 passed, 176 deselected in
  44.02s** (was 373 — +4 new tests, deselected count unchanged, confirming
  nothing was accidentally marked `swe_slow`).
- `languages/whence/run_tests_fast.sh` (sanity check — this round makes
  no code changes under `languages/whence/`, just wires the existing
  script in): **842 passed, 36 deselected in 30.89s** (round 242's own
  measurement was 840/35; the 2-test delta is round 246's own new
  `test_guest_matches_shapeof_typed_why_shape_matches_host_exactly` plus
  one other addition landed since round 242 — both fast-tier, confirms
  the fast/slow split still holds cleanly after two more language(C)
  rounds' worth of test additions).
- `harness/tests/test_tiering.py` + `harness/tests/test_driver_health.py`:
  72/72 (cross-check that this round's changes don't touch either file
  and both remain green).
- `git status --short` post-change: only `run_driver.sh`, `.gitignore`,
  `state/round_counter` modified, plus the new test file and this
  knowledge file untracked — the five stale health-check logs are gone
  from the listing (now gitignored), the four Hermes-gateway files
  untouched.

## 5. Not built / flagged for a future round

- Round 241's own §3 (its own knowledge file) named a narrower,
  potentially cheaper alternative that's now moot: "whether
  self_eval.lang-touching rounds specifically should be required to run
  `tests/test_self_eval.py` ... before landing." With the whence fast
  tier now wired into every round automatically (not just
  self_eval.lang-touching ones), this narrower proposal is superseded —
  `tests/test_self_eval.py` isn't itself `whence_slow`-marked (its two
  tests didn't cross the 1.0s cutoff in round 242's measurement), so it
  already runs inside the fast tier on every round regardless of track.
- Did not attempt to also wire in `harness/swe/`'s own guest-differential/
  fuzz/oracle CLI campaigns (`harness/swe/{guest,fuzz,oracles}.py` invoked
  directly, distinct from `pytest harness/tests/test_swe_*.py`) — those
  are on-demand research tools, not a pytest-collected suite, and
  round 242's own §6 already scoped that question to SWE-loop(D)
  territory, not touched here either.
- The two health-check blocks in `run_driver.sh` are now near-identical
  boilerplate (script-exists guard, run-and-capture, PASS/FAIL log line).
  A third language/subsystem gaining its own `run_tests_fast.sh` in a
  future round would make a strong case for factoring this into a small
  bash function or a `harness/driver_health.py` helper instead of a third
  copy-pasted block — deliberately NOT done now, since factoring two call
  sites ahead of a proven third need would be the premature abstraction
  this program's own ground rules warn against.
