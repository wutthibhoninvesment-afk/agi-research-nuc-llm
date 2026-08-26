---
name: self-updating-driver-loop
description: Use when a long-running bash driver loop (a `while...done` process launching an agent, build, or job each iteration) keeps running old logic after the on-disk script is edited. Symptoms — "the live process still acts like the old version after a bug fix", "the driver had to be killed and relaunched for the fix to take effect", "the running PID doesn't match the file on disk anymore", "a supervisor loop needs a live code update with no downtime". Why: bash parses `while...done` ONCE and never re-reads the script for that process's life. Fix: `exec bash "$0" "$@"` at the loop's tail — replaces the process image in place, same PID, fresh read from disk. Also: placement vs `continue`/`break` so retry state and cleanup stay correct, why plain shell variables don't survive the exec, and proving it live with a subprocess test, not a syntax check. NOT for one-shot scripts relaunched externally, systemd/supervisord services (use their restart hook), or interpreters re-reading source each statement.
---

# Self-updating bash driver loops

A bash `while ... done` loop is parsed into memory **once**, when the shell
reaches it, and never re-read from disk for the lifetime of that compound
command — even across hundreds of iterations spanning days. A long-running
driver script built as one big loop can therefore run a stale, pre-fix
version of itself indefinitely: every on-disk edit is invisible to the live
process until something external kills and relaunches it. Reference
implementation: `run_driver.sh` (the `exec bash "$0" "$@"` line at the loop's
tail) + `harness/tests/test_run_driver_selfexec.py` (real-subprocess proof).

## When to use (triggers)
- A bash (or similarly-loopy shell) process supervises repeated work — agent
  rounds, build/deploy cycles, polling jobs — as one long-lived `while` loop.
- A bug fix or behavior change to the driver script had no effect until the
  process was killed and restarted by hand or by a separate watcher script.
- Debugging "why does the log show the OLD log line format / OLD constant /
  pre-fix behavior even though `git diff` shows the fix is on disk."
- Designing a new always-on orchestration loop and want it to pick up its
  own future fixes without an external redeploy mechanism.

**When NOT to use:** a script that runs once and exits, then gets relaunched
by cron/systemd/a CI trigger for the next run — the fresh process already
reads the current file, nothing is cached across runs. A service already
under systemd/supervisord — use its own restart-on-change hook instead of
reinventing one in bash. Long-running processes in other languages that
already re-parse per iteration (this is a property of bash reusing one
parsed AST for a compound command, not a universal "long process" problem).

## Steps
1. **Confirm it's actually the caching bug, not a deploy/env problem.**
   Behavioral test: edit a harmless string constant in the on-disk script
   while the live process is mid-loop, wait for the next iteration, and
   check whether the new string shows up in its output/log. If it never
   does until the process restarts, this is the bug (`man bash`: `exec`
   "no new process is created" — the *lack* of an exec-per-iteration is
   exactly what leaves the old parse in memory).
2. **Place `exec bash "$0" "$@"` at the very end of the loop body,** as the
   last thing before `done`. `exec` replaces the current process image with
   a fresh invocation of the same script — same PID (confirm via `pid=$$`
   logged per iteration, or `ps -o pid=` before/after), but it re-reads
   `"$0"` off disk from scratch, so the very next iteration runs whatever is
   on disk *right now*, no external kill+relaunch required, structurally.
3. **Audit every `continue` and `break` in the loop against this new line.**
   `continue` points that should preserve in-process retry/backoff state
   (a rate-limit counter, an in-flight attempt count) must stay ABOVE the
   `exec` line — they loop back inside the same parsed compound command,
   never touching it. `break` points (shutdown, quota exhausted) must also
   stay above it, so any once-only cleanup code written *after* the loop
   still runs exactly once instead of being skipped or looped over.
4. **Persist anything that must survive the exec boundary to a file, not a
   shell variable.** `exec` starts a brand-new bash process from the top of
   the script — every plain variable assigned before or during the loop
   (counters, flags) is gone; only what was written to disk (a state file)
   or literals re-derived identically each pass survive. `run_driver.sh`'s
   `ROUND` is read fresh from `state/round_counter` at the top of every
   fresh image on purpose; its `RATE_LIMIT_ROUND`/`RATE_LIMIT_RETRIES`
   plain-variable counters are allowed to reset on exec only because they
   are unconditionally re-derived from `ROUND` immediately afterward, and
   the exec line sits after every path that needs them within one round.
5. **Bump a hand-maintained version string, logged every iteration.** A
   `DRIVER_VERSION="..."` constant near the top, printed in each round's log
   line, turns "is the fix actually live?" into one `grep` instead of
   cross-referencing file-edit timestamps against process-start timestamps.
6. **Prove it end-to-end with a real subprocess, not `bash -n`.** Syntax
   validation says nothing about whether the re-read happens. Launch the
   real script with a stub standing in for its expensive dependency (e.g. a
   fake `claude`/`docker`/`ssh` on `PATH`); from inside the stub, edit the
   driver script's own on-disk copy mid-run (synchronous — no timing race,
   since the edit happens strictly before the loop reaches its `exec` line
   for that iteration); assert the **next** iteration's observable output
   reflects the edit while the OS process never restarted (same PID
   end-to-end). See `test_run_driver_selfexec.py`'s `_pid_from_round_line`
   pattern for how to pull the PID out of the driver's own log rather than a
   child process's `$PPID` (unreliable if `timeout`/`gtimeout` wraps the
   child on some platforms and not others).

## Pitfalls
- **Trusting `ps` to prove staleness or freshness.** `ps` shows the same PID
  whether the process is running the old cached parse or a freshly
  `exec`'d one — it cannot distinguish them. Only a behavioral probe (a
  changed constant showing up, or a logged version string) can.
- **Placing `exec` before a `continue`-based retry path.** Every retry
  becomes a full process restart, silently discarding in-memory backoff
  counters and repeating the same escalating-delay schedule from scratch
  on every single retry within what should be one escalating sequence.
- **Placing `exec` after a `break`, or letting a `break` path reach it.**
  Once-only cleanup code below the loop either never runs (the shutdown
  path detoured through the exec line back to the top) or the loop never
  actually terminates from that path at all — trace every escape point.
- **Assuming a shell variable's value survives the exec.** It does not; a
  bug where a counter mysteriously resets to its initial value every few
  iterations, with the reset always aligned to the same loop-turn boundary,
  is this. Move it to a file or confirm it's meant to reset on purpose.
- **"I edited the file, it must be live now."** This exact assumption cost
  a real driver 12+ iterations running a pre-fix copy of itself before
  anyone noticed — two separate earlier on-disk fixes to the same script
  had zero live effect, discovered only by comparing the live log's output
  shape against what the current on-disk code should have produced.
- **Verifying with a syntax check only.** `bash -n script.sh` passing proves
  the file parses; it does not exercise the exec at all, so a wrong
  placement relative to `continue`/`break` ships unnoticed.

## Commands
```bash
bash -n run_driver.sh                                   # syntax only — NOT sufficient, see pitfalls
grep -n 'exec bash "\$0"' run_driver.sh                  # confirm the line exists and where
grep -n 'driver_version=' logs/driver.log | tail -5      # cheapest live "is the fix active" check
```

## Verification
```bash
perl -e 'alarm 60; exec @ARGV' python3 -m pytest -q harness/tests/test_run_driver_selfexec.py   # 1 passed
```
- [ ] `exec bash "$0" "$@"` sits after every `continue` and before every `break` in the loop
- [ ] a real-subprocess test edits the on-disk script mid-run via a stub and asserts the NEXT iteration reflects the edit under the SAME PID
- [ ] anything that must persist across iterations is read from/written to a file, never held only in a loop-scoped shell variable
- [ ] a hand-bumped version string is logged every iteration and greppable
