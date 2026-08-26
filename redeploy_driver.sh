#!/usr/bin/env bash
# Redeploy the driver loop so it actually picks up on-disk changes to
# run_driver.sh / harness/driver_health.py.
#
# WHY THIS EXISTS (found round 139, harness(A)): bash parses a `while ...
# do ... done` compound command into memory ONE TIME, the first time the
# interpreter reaches it, and every iteration re-executes that cached
# parse — it does NOT re-read the loop body from disk on later iterations.
# run_driver.sh is almost entirely one big `while true; do ... done` loop,
# so once the process starts, editing run_driver.sh on disk has ZERO
# effect on that already-running process, forever, no matter how many
# rounds pass. Confirmed live: the driver process running since
# 2026-08-25 22:27:32 was still launching every round with the pre-127
# xargs-based (silently-broken) failure check AND the pre-133
# `--output-format json` flag as late as round 139 (2026-08-26 09:28),
# roughly 11 hours and two harness(A) fix-rounds after both fixes landed
# on disk (round 127 at 00:03-00:41, round 133 at 07:54-08:08). Neither
# fix ever took effect in production. See
# knowledge/round-139-harness-driver-stale-process-safety-valve-dead.md.
#
# Safe by construction: this script takes the PID of the round CURRENTLY
# IN FLIGHT under the stale driver and does nothing but poll until that
# PID exits on its own — it never interrupts in-progress round work. Only
# after that does it stop the stale driver loop (by the exact PID passed
# in, never a pattern-based pkill that could match something unintended)
# and start a fresh one, which re-reads run_driver.sh from disk fresh.
#
# Usage: nohup bash redeploy_driver.sh ROUND_PID DRIVER_PID &
#   ROUND_PID  - pid of the in-flight `claude -p` round process (this
#                round's own process; find via `ps` before launching)
#   DRIVER_PID - pid of the stale run_driver.sh bash loop (ROUND_PID's
#                parent)
set -u
WS="$HOME/agi-research"
LOG="$WS/logs/watcher.log"
log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

if [ $# -ne 2 ]; then
  echo "usage: redeploy_driver.sh ROUND_PID DRIVER_PID" >&2
  exit 2
fi
ROUND_PID="$1"
DRIVER_PID="$2"

log "redeploy watcher started (pid $$); waiting for round pid $ROUND_PID to exit on its own (driver pid $DRIVER_PID is running a stale in-memory copy of run_driver.sh)"

# Poll every 5s for up to 4h. A round has a 2400s (40min) run_timeout cap
# in run_driver.sh plus up to ~45s cooldown, so 4h is generously bounded
# for a single round while still not looping forever if something goes
# very wrong.
for i in $(seq 1 2880); do
  if ! kill -0 "$ROUND_PID" 2>/dev/null; then
    log "round pid $ROUND_PID exited after ${i}x5s polls"
    break
  fi
  sleep 5
done

if kill -0 "$ROUND_PID" 2>/dev/null; then
  log "round pid $ROUND_PID still alive after max wait (4h) — aborting redeploy without touching the driver"
  exit 1
fi

# Give the stale driver a moment to finish its own end-of-round bookkeeping
# (writing the round log tail, its stale FAILS check, its 45s sleep) before
# we stop it, so we don't race a half-written log file.
sleep 3

if kill -0 "$DRIVER_PID" 2>/dev/null; then
  kill "$DRIVER_PID" 2>/dev/null
  sleep 2
  if kill -0 "$DRIVER_PID" 2>/dev/null; then
    kill -9 "$DRIVER_PID" 2>/dev/null
    log "stale driver pid $DRIVER_PID force-killed (SIGTERM was ignored)"
  else
    log "stale driver pid $DRIVER_PID stopped"
  fi
else
  log "driver pid $DRIVER_PID already gone (stopped by something else?) — not restarting to avoid a double driver"
  exit 1
fi

# Safety: never leave a stray claude round running into the handover.
if pgrep -f "claude -p.*research round" >/dev/null 2>&1; then
  log "WARNING: a claude round process is still alive after driver stop — leaving it alone, not killing (could be a legitimate concurrent session)"
fi

cd "$WS"
nohup bash "$WS/run_driver.sh" >> "$LOG" 2>&1 &
NEW_PID=$!
log "fresh driver launched (pid $NEW_PID), now reading the CURRENT run_driver.sh from disk"
