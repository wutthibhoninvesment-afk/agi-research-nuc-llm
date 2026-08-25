#!/usr/bin/env bash
# Wait for round 9 to finish, swap to the updated driver (new 6-track rotation),
# then resume. Logs to ~/agi-research/logs/watcher.log
set -u
WS="$HOME/agi-research"
LOG="$WS/logs/watcher.log"
log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

log "watcher started; waiting for round 9 (language) to finish"
for i in $(seq 1 720); do                       # max ~4h
  if [ -s "$WS/logs/round-009.json" ] && ! pgrep -f "claude -p.*round 9" >/dev/null 2>&1; then
    log "round 9 finished"
    break
  fi
  sleep 20
done

# stop old driver (old rotation) if still alive
if pgrep -f "run_driver.sh" >/dev/null 2>&1; then
  pkill -f "run_driver.sh" && log "old driver stopped"
  sleep 3
fi

# safety: never leave a stray claude round running into the new cycle
if pgrep -f "claude -p.*research round" >/dev/null 2>&1; then
  log "stray claude round still running — killing for clean handover"
  pkill -f "claude -p.*research round"
  sleep 5
fi

# if the old driver already claimed round 10 (empty/partial result), roll the
# counter back so the NEW rotation redoes round 10 as NUC-integration(E)
if [ -f "$WS/logs/round-010.json" ] && [ ! -s "$WS/logs/round-010.json" ]; then
  rm -f "$WS/logs/round-010.json"
  echo 9 > "$WS/state/round_counter"
  log "rolled counter back to 9 (killed stray round 10)"
fi

log "starting updated driver (6-track rotation)"
nohup bash "$WS/run_driver.sh" >> "$LOG" 2>&1 &
log "new driver launched (pid $!)"
