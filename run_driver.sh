#!/usr/bin/env bash
# AGI research driver — runs Claude Code rounds until weekly limit.
# Model: sonnet-5 (waiting for fable-5 weekly limit reset ~Sunday 2026-08-30)
set -uo pipefail

WS="${DRIVER_WS:-$HOME/agi-research}"
TIMEOUT_CMD=""
if command -v timeout >/dev/null 2>&1; then TIMEOUT_CMD="timeout"
elif command -v gtimeout >/dev/null 2>&1; then TIMEOUT_CMD="gtimeout"; fi
run_timeout() {
  if [ -n "$TIMEOUT_CMD" ]; then "$TIMEOUT_CMD" "$@"; else shift; "$@"; fi
}
LOG="$WS/logs/driver.log"
STATE_FILE="$WS/state/round_counter"
FINAL="$WS/state/FINAL-REPORT.md"

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

# Decide what to do about a round log that MAY be an HTTP 429 (usage limit).
# Pure w.r.t. process state (reads only $1, the round's JSON log; takes the
# retry count already spent on THIS round and the retry cap as plain args
# instead of touching globals) so it is testable standalone by sourcing this
# file with DRIVER_SOURCE_ONLY=1 and calling it directly — no real `claude`
# invocation, no mutation of logs/state, per round 127's lesson that a naive
# shell repro under the WRONG shell (zsh doesn't word-split; this script
# runs under bash) can hide exactly the bug it's meant to catch.
#
# 429 is ambiguous on its own: it could be the 5-hour rolling window
# (CLAUDE.md/CURRICULUM.md: "pace against the 5-hour rolling limit — sleep
# until reset") or the weekly cap (stop for good). Nothing in the JSON says
# which (round 113-121's real body was just "You've reached your Fable 5
# limit", no reset timestamp) — resolved empirically instead of guessed:
# retry with escalating backoff toward ~5h (`driver_health.rate_limit_
# backoff_seconds`); if it clears, it was transient; if it never clears
# within the retry budget it behaves exactly like the weekly-cap case, just
# later, having actually tried to wait it out per policy instead of
# stopping on the first hit.
#
# Prints "<action> <seconds>" on stdout: action is one of
#   not429   — $1 is not a 429; caller falls through to its usual handling
#   retry    — sleep <seconds> then re-attempt the SAME round
#   stop     — retry budget exhausted; treat as the weekly cap
rate_limit_action() {
  local rlog="$1" retries_so_far="$2" max_retries="$3"
  local is429
  is429=$(python3 -m harness.driver_health is429 "$rlog" 2>/dev/null || echo "no")
  if [ "$is429" != "yes" ]; then
    echo "not429 0"
    return
  fi
  local n=$(( retries_so_far + 1 ))
  if [ "$n" -le "$max_retries" ]; then
    local wait
    # Test seam only: production never sets this, so
    # `harness.driver_health wait` always decides — it prefers the CLI's
    # own exact reset timestamp (stream-json's `rate_limit_event`, see
    # `latest_rate_limit_reset_epoch`) and only falls back to the
    # escalating guess schedule when this round's log has none. A real
    # wait (minutes to ~2h) can't run end-to-end inside a test's timeout,
    # so smoke tests of the FULL retry loop (not just this function) set
    # this to make the same code path finish in milliseconds instead.
    if [ -n "${DRIVER_TEST_BACKOFF_SECONDS:-}" ]; then
      wait="$DRIVER_TEST_BACKOFF_SECONDS"
    else
      wait=$(python3 -m harness.driver_health wait "$rlog" "$n")
    fi
    echo "retry $wait"
  else
    echo "stop 0"
  fi
}

if [ "${DRIVER_SOURCE_ONLY:-0}" = "1" ]; then
  return 0 2>/dev/null || exit 0
fi

cd "$WS"

ROUND=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
RATE_LIMIT_ROUND=0
RATE_LIMIT_RETRIES=0
MAX_RATE_LIMIT_RETRIES="${DRIVER_MAX_RATE_LIMIT_RETRIES:-7}"

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

  # Run with sonnet-5 (fable-5 hit weekly limit; resets ~Sunday 2026-08-30).
  # stream-json (needs --verbose) instead of json: (1) the final `result`
  # line has the SAME shape driver_health.py always classified, so nothing
  # downstream changes; (2) it ALSO emits `rate_limit_event` lines with the
  # CLI's own exact reset timestamp — round 133 found live that a 429 no
  # longer has to be an unexplained guess (see `driver_health.
  # latest_rate_limit_reset_epoch`); (3) per-turn `assistant` events let
  # `driver_health.summarize_turns` answer round 127's open "why did
  # 122-126 burn all 80 turns" question with real data next time it happens.
  run_timeout 2400 claude -p "$PROMPT" \
    --model claude-sonnet-5 \
    --dangerously-skip-permissions \
    --allowedTools "Read,Edit,Write,Bash,Glob,Grep" \
    --output-format stream-json \
    --verbose \
    --max-turns 80 \
    > "$RLOG" 2>&1
  RC=$?

  # quota / stop detection
  if grep -qiE "usage limit|rate.?limit|weekly.*limit|5-hour|usage_policies|maximum.*usage" "$RLOG"; then
    log "round $ROUND: quota/limit signal detected (rc=$RC) — checking state"
  fi

  TURN_SUMMARY=$(python3 -m harness.driver_health summary "$RLOG" 2>/dev/null || echo "n/a")
  log "round $ROUND: turn summary $TURN_SUMMARY"

  # These three checks all go through harness.driver_health so both the
  # plain-json shape (every log through round 132) and stream-json (round
  # 133+, see the invocation above) classify identically — the module's
  # `load_round_result` is the one place that knows how to read either.
  if [ $RC -eq 0 ] && [ "$(python3 -m harness.driver_health success "$RLOG" 2>/dev/null || echo no)" = "yes" ]; then
    log "round $ROUND: success"
  else
    SUB=$(python3 -m harness.driver_health status "$RLOG" 2>/dev/null || echo "parse-error/rc=$RC")
    log "round $ROUND: non-success status=$SUB"

    # Check if this was a temporary 529 overload / 5xx server error
    IS_5XX=$(python3 -m harness.driver_health is5xx "$RLOG" 2>/dev/null || echo "no")
    if [ "$IS_5XX" = "yes" ]; then
      log "round $ROUND: server overloaded (529/5xx) — waiting 90s before retrying round"
      ROUND=$(( ROUND - 1 ))
      echo "$ROUND" > "$STATE_FILE"
      sleep 90
      continue
    fi

    if [ "$RATE_LIMIT_ROUND" != "$ROUND" ]; then
      RATE_LIMIT_ROUND=$ROUND
      RATE_LIMIT_RETRIES=0
    fi
    read -r RL_ACTION RL_WAIT <<< "$(rate_limit_action "$RLOG" "$RATE_LIMIT_RETRIES" "$MAX_RATE_LIMIT_RETRIES")"
    if [ "$RL_ACTION" = "retry" ]; then
      RATE_LIMIT_RETRIES=$(( RATE_LIMIT_RETRIES + 1 ))
      log "round $ROUND: rate limit (429), retry $RATE_LIMIT_RETRIES/$MAX_RATE_LIMIT_RETRIES after ${RL_WAIT}s"
      ROUND=$(( ROUND - 1 ))
      echo "$ROUND" > "$STATE_FILE"
      sleep "$RL_WAIT"
      continue
    elif [ "$RL_ACTION" = "stop" ]; then
      log "round $ROUND: rate limit persisted past $MAX_RATE_LIMIT_RETRIES retries (~5h of backoff) — treating as the weekly cap, stopping"
      break
    fi

    if echo "$SUB" | grep -qiE "budget|limit"; then
      log "quota exhausted — stopping"
      break
    fi
  fi

  # stop if the last 3 rounds all look like genuine failures (not 5xx/529,
  # which the branch above already retries in place). This used to be an
  # `xargs -I{} python3 -c "..."` pipeline; on macOS's BSD xargs, -I mode
  # rejects command lines over its own small internal buffer regardless of
  # ARG_MAX, so it printed "xargs: command line cannot be assembled, too
  # long" to a stderr this script discarded and produced NO stdout — grep -c
  # on empty input is 0, so FAILS silently read 0 forever and this safety
  # valve never fired (confirmed: rounds 113-121 ran 8 straight 429s and
  # 122-126 ran 5 straight max-turns deaths without it tripping once). Fixed
  # by doing the classification in one python3 process, no xargs.
  LAST3=$(ls -t "$WS"/logs/round-*.json 2>/dev/null | head -3)
  FAILS=$(python3 -m harness.driver_health $LAST3 2>/dev/null || echo 0)
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
