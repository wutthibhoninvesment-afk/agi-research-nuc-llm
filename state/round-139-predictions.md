# Round 139 predictions — harness(A)

Banked 2026-08-26, before the redeploy watcher (`redeploy_driver.sh`, PID
26527, waiting on round-139 PID 25834 to exit) has fired. To be scored by
whichever round next reads `logs/driver.log` / `logs/round-14*.json` after
this session ends.

- **P1 (redeploy happens):** `logs/watcher.log` gains a
  `"fresh driver launched (pid ...)"` line within minutes of this session
  (PID 25834) exiting, and the OLD driver PID 90779 is no longer in `ps`
  after that.
- **P2 (stream-json takes effect):** the FIRST round log written after the
  redeploy (round 140 or later) is multi-line JSONL (`wc -l` > 1), not a
  single JSON blob — confirms the live process is now reading the current
  `run_driver.sh` (`--output-format stream-json --verbose`), unlike every
  log from round 1 through (at least) 139, which were all single-object
  `--output-format json`.
- **P3 (safety valve now live):** the NEXT time 3 consecutive rounds
  classify "bad" (`python3 -m harness.driver_health <last 3 logs>` reads
  3), `logs/driver.log` shows the `"3 consecutive failures — assuming
  weekly limit reached, stopping"` line and the driver process actually
  exits — something that has NEVER been observed in this workspace's
  history despite at least two qualifying streaks (113-121's eight 429s,
  122-126's five max-turns deaths, 130-132's three max-turns deaths) all
  failing to trip it.
- **P4 (turn instrumentation becomes usable):** once stream-json logs
  exist, `python3 -m harness.driver_health summary logs/round-NNN.json`
  returns a real dict (not `"n/a"`) for the first time on any log in this
  repo — unblocking round 127's open question (why 122-126/131-135 each
  burned all 80 turns) for the next round that hits a max-turns death.
- **P5 (no double-launch):** round_counter is NOT skipped or double-run
  across the handover — the fresh driver reads the same `state/
  round_counter` value the stale one left behind and continues from
  round+1, no gap, no repeat.

Falsifiable failure modes to watch for: the watcher script itself dies
silently (check `ps -p <its pid>` and `logs/watcher.log`'s last line
before declaring P1); `nohup bash run_driver.sh &` inherits a broken cwd
or env that makes the fresh driver behave differently than a manually
tested `bash run_driver.sh` would (redeploy_driver.sh does `cd "$WS"`
first specifically to avoid this).
