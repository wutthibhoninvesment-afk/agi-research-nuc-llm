#!/usr/bin/env bash
# AGI research driver — runs Claude Code rounds until weekly limit.
# Model: sonnet-5 (waiting for fable-5 weekly limit reset ~Sunday 2026-08-30)
set -uo pipefail

WS="$HOME/agi-research"
TIMEOUT_CMD=""
if command -v timeout >/dev/null 2>&1; then TIMEOUT_CMD="timeout"
elif command -v gtimeout >/dev/null 2>&1; then TIMEOUT_CMD="gtimeout"; fi
run_timeout() {
  if [ -n "$TIMEOUT_CMD" ]; then "$TIMEOUT_CMD" "$@"; else shift; "$@"; fi
}
LOG="$WS/logs/driver.log"
STATE_FILE="$WS/state/round_counter"
FINAL="$WS/state/FINAL-REPORT.md"
cd "$WS"

ROUND=$(cat "$STATE_FILE" 2>/dev/null || echo 0)

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

track_name() {
  local r=$1
  local m=$(( r % 6 ))
  case $m in
    1) echo "harness(A)" ;;
    2) echo "language(C)" ;;
    3) echo "skills(B)" ;;
    4) echo "NUC-integration(E)" ;;
    5) echo "SWE-loop(D)" ;;
    0) echo "language(C)" ;;
  esac
}

log "=== driver started; resuming after round $ROUND ==="

while true; do
  ROUND=$(( ROUND + 1 ))
  echo "$ROUND" > "$STATE_FILE"
  TRACK=$(track_name "$ROUND")
  RLOG="$WS/logs/round-$(printf '%03d' "$ROUND").json"
  log "round $ROUND track=$TRACK start"

  PROMPT="You are running research round $ROUND of the AGI software-engineering program.
Your track this round: $TRACK. Follow CLAUDE.md ground rules and CURRICULUM.md exactly.
Round number for file naming: $(printf '%03d' "$ROUND").
First: read state/research-state.md. Then do the work, test it, write the knowledge file,
update research-state.md. Be relentless and thorough — this is deep research, spend the tokens."

  # Run with sonnet-5 (fable-5 hit weekly limit; resets ~Sunday 2026-08-30)
  run_timeout 2400 claude -p "$PROMPT" \
    --model claude-sonnet-5 \
    --dangerously-skip-permissions \
    --allowedTools "Read,Edit,Write,Bash,Glob,Grep" \
    --output-format json \
    --max-turns 80 \
    > "$RLOG" 2>&1
  RC=$?

  # quota / stop detection
  if grep -qiE "usage limit|rate.?limit|weekly.*limit|5-hour|usage_policies|maximum.*usage" "$RLOG"; then
    log "round $ROUND: quota/limit signal detected (rc=$RC) — checking state"
  fi

  if [ $RC -eq 0 ] && python3 -c "
import json,sys
d=json.load(open('$RLOG'))
sys.exit(0 if (d.get('subtype')=='success' and not d.get('is_error', False)) else 1)
" 2>/dev/null; then
    log "round $ROUND: success"
  else
    SUB=$(python3 -c "import json; d=json.load(open('$RLOG')); print('error:' + str(d.get('api_error_status', 'err')) if d.get('is_error') else d.get('subtype','?'))" 2>/dev/null || echo "parse-error/rc=$RC")
    log "round $ROUND: non-success status=$SUB"
    
    # Check if this was a temporary 529 overload / 5xx server error
    IS_5XX=$(python3 -c "import json; d=json.load(open('$RLOG')); print('yes' if str(d.get('api_error_status','')).startswith('5') or '529' in str(d.get('result','')) else 'no')" 2>/dev/null || echo "no")
    if [ "$IS_5XX" = "yes" ]; then
      log "round $ROUND: server overloaded (529/5xx) — waiting 90s before retrying round"
      ROUND=$(( ROUND - 1 ))
      echo "$ROUND" > "$STATE_FILE"
      sleep 90
      continue
    fi

    if echo "$SUB" | grep -qiE "budget|limit"; then
      log "quota exhausted — stopping"
      break
    fi
  fi

  # stop if two consecutive failures look quota-shaped; keep simple: check last 3 logs
  FAILS=$(ls -t "$WS"/logs/round-*.json 2>/dev/null | head -3 | xargs -I{} python3 -c "
import json,sys
try:
    d=json.load(open('{}'))
    is_err = d.get('is_error', False)
    is_5xx = str(d.get('api_error_status','')).startswith('5') or '529' in str(d.get('result',''))
    print('bad' if (is_err and not is_5xx) else 'ok')
except Exception: print('bad')
" 2>/dev/null | grep -c bad || true)
  if [ "$FAILS" -ge 3 ]; then
    log "3 consecutive failures — assuming weekly limit reached, stopping"
    break
  fi

  # pace against 5h rolling limit: brief cool-down between rounds
  sleep 45
done

log "=== driver stopping at round $ROUND ==="

# Final consolidation round (cheap, one shot)
if [ ! -f "$FINAL" ]; then
  run_timeout 900 claude -p "The research budget is exhausted. Read all files in state/ and knowledge/
and write state/FINAL-REPORT.md: summary of every round, what was built, key learnings per track,
what remains. Make it comprehensive." \
    --model claude-sonnet-5 \
    --dangerously-skip-permissions \
    --allowedTools "Read,Write,Bash,Glob,Grep" \
    --max-turns 30 > "$WS/logs/final-report.json" 2>&1
  log "final report round done"
fi

touch "$WS/state/DONE"
log "=== driver finished ==="
