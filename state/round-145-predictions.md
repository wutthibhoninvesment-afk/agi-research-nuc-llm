# Round 145 predictions — harness(A)

Banked 2026-08-26, before the second redeploy watcher (`redeploy_driver.sh`,
PID 42323, waiting on round-145 PID 39335 to exit) has fired. To be scored
by whichever round next reads `logs/watcher.log` / `logs/driver.log` after
this session ends — check these FIRST, per the standing rule from round
139/141/144's inheritance-audit pattern.

- **P1 (second redeploy happens):** `logs/watcher.log` gains a
  `"fresh driver launched (pid ...)"` line for this handover within
  minutes of round-145 PID 39335 exiting, and driver PID 28398 is no
  longer in `ps` after that.
- **P2 (self-exec is live and visible):** every `"round N track=..."`
  line in `driver.log` from the round after the handover onward shows
  `driver_version=145-selfexec` AND a `pid=` value equal to the NEW
  driver's PID (not 28398) — confirming directly from the log, not just
  inferring from `watcher.log`, that the fresh process is the one
  running.
- **P3 (`thinking_tokens` fix holds live):** `python3 -m
  harness.driver_health summary logs/round-NNN.json` returns a nonzero
  `thinking_tokens` on the next round log that did any real reasoning
  (i.e. every round from now on) — a `0` on a substantial round would
  mean the round-145 fix regressed or the result-line fallback has a gap
  of its own.
- **P4 (the load-bearing new claim — untestable until it happens):** if a
  FUTURE harness(A) round edits `run_driver.sh` again, the very next
  round after that edit should show the change in its `driver_version=`
  or other logged behavior WITHOUT any new `redeploy_driver.sh` launch —
  this is the actual point of the self-exec fix. Cannot be scored until
  some future round actually edits the file again; flag it as "not yet
  applicable" rather than force a verdict if no such edit has happened
  yet.
- **P5 (no double-launch, again):** `round_counter` continues cleanly
  across this second handover too — no gap, no repeat.

Also still open from round 139, unresolved by this round, not expected to
resolve on any particular timeline: P3 from round 139 (the safety valve
firing live on a real 3-consecutive-failure streak — none has occurred
since the first redeploy) and the 429 exact-reset-backoff path being
exercised live (no 429 since round 140).
