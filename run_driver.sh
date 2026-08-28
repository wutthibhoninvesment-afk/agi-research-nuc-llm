#!/usr/bin/env bash
# AGI research driver — runs Claude Code rounds until weekly limit.
# Model: sonnet-5 (waiting for fable-5 weekly limit reset ~Sunday 2026-08-30)
set -uo pipefail
# Path setup for Claude Code (this NUC host has no global `claude`; it's
# installed locally under node_modules/.bin — see claude-wrapper.sh).
# Round 157: this used to CLOBBER $PATH with a fixed list instead of
# extending the inherited one, silently dropping any directory a caller
# had put on PATH before invoking this script — including the fake-
# `claude` stub dir both e2e driver tests prepend to PATH before launching
# their `bash run_driver.sh` subprocess. Fixed to APPEND rather than even
# prepend: node_modules/.bin should be a fallback source for `claude`, not
# take priority over whatever the caller already resolved it to — a
# prepend still shadowed the tests' PATH-stub `claude` with the real one
# (confirmed live: both tests hung the full 45s until this changed to
# append).
export PATH="$PATH:/home/pgain/agi-research-nuc-llm/node_modules/.bin"

# Bumped by hand whenever this file changes in a way worth being able to
# see directly in driver.log (no cross-referencing watcher.log timestamps
# needed). Since round 145's self-re-exec fix (see the `exec bash "$0"
# "$@"` at the loop's end below), this now reliably reflects the ON-DISK
# script content for every round it produced, including rounds after a
# mid-run edit — round 139's live driver could not make that claim.
DRIVER_VERSION="253-record-gap-check"

# Round 157: a manual post-migration edit (made outside any round,
# between the Mac->NUC sync commit c768d90 and round 154) hardcoded this
# to the new absolute path, which silently dropped the `DRIVER_WS`
# override both `test_run_driver_selfexec.py` and
# `test_run_driver_maxturns_safety_valve.py` rely on to run the real
# driver against a disposable tmp_path instead of the production
# workspace — both went from passing to failing (confirmed: they still
# ran, but timed out, because $WS pointed at the live tree with no
# fake-`claude` stub reachable at the copied script's relative path). The
# override existed before the migration (`WS="${DRIVER_WS:-$HOME/agi-
# research}"`) and just needed its *default* updated, not removing.
WS="${DRIVER_WS:-/home/pgain/agi-research-nuc-llm}"
# Round 157: same story as WS above, for the `claude` invocation itself.
# This host has no global `claude` on PATH, so production needs the local
# wrapper (`claude-wrapper.sh`: activates .venv, prepends node_modules/
# .bin, then execs the real CLI) — but the two e2e driver tests inject a
# fake `claude` via a PATH-prepended stub dir, and a hardcoded
# `./claude-wrapper.sh` call skips PATH lookup entirely (it's a relative
# path) and fails outright in the tests' tmp_path copy, which has no
# wrapper script at all. Overridable so tests can point this back at a
# bare `claude` and hit their PATH stub, same as before the migration.
CLAUDE_CMD="${DRIVER_CLAUDE_CMD:-./claude-wrapper.sh}"
TIMEOUT_CMD=""
if command -v timeout >/dev/null 2>&1; then TIMEOUT_CMD="timeout"
elif command -v gtimeout >/dev/null 2>&1; then TIMEOUT_CMD="gtimeout"; fi
# Round 187: round 185 caught the outer `timeout` (below, wrapping the whole
# `claude -p` invocation) NOT killing a hung round promptly even after its
# deadline — a live Bash tool call inside the round (a self-hosted Whence
# guest-harness recursion test, SWE-loop(D) territory, unrelated to this
# fix) hung with zero output for ~48 minutes; the plain `timeout 3300`
# forwarded SIGTERM at the deadline but round 185's own log shows the
# process didn't actually die until ~1235s (20m35s) later — busting round
# 181's own "~936s max post-deadline delay" assumption that sized the 3300s
# default in the first place. Plain GNU/BSD `timeout` has no forced-kill
# fallback unless told to: without `--kill-after`, a SIGTERM-ignoring (or
# merely slow-to-unwind) descendant can make `timeout` wait indefinitely.
# `--kill-after` sends SIGKILL if the command is still alive this long after
# the initial SIGTERM, bounding the overrun instead of leaving it open-
# ended. Same override convention as DRIVER_ROUND_TIMEOUT_S/DRIVER_WS/etc.
KILL_AFTER_S="${DRIVER_KILL_AFTER_S:-120}"
run_timeout() {
  if [ -n "$TIMEOUT_CMD" ]; then "$TIMEOUT_CMD" --kill-after="$KILL_AFTER_S" "$@"; else shift; "$@"; fi
}
LOG="$WS/logs/driver.log"
STATE_FILE="$WS/state/round_counter"
FINAL="$WS/state/FINAL-REPORT.md"
# Overridable only for tests exercising the self-re-exec loop below end to
# end without a real 45s wait per round; production always uses 45.
LOOP_SLEEP_S="${DRIVER_LOOP_SLEEP_S:-45}"
# Round 181: wall-clock backstop for the whole `claude -p` invocation below
# (belt-and-suspenders against a genuine hang; `--max-turns` (135 as of
# round 205, was 120) is meant to be the PRIMARY, graceful stopgap — it
# writes a real `type:"result"` event
# so driver_health.summarize_turns can read real thinking-token/turn data
# and the round still gets classified as `error:max_turns`, not silently
# discarded). Was a hardcoded 2400 since round 133; round 181 found LIVE,
# from `logs/driver.log`'s last 25 rounds, that this was too tight and had
# become the DOMINANT cause of `interrupted=true`/`status=?` round deaths
# (7 of 25, 28%): every one of the 18 non-interrupted rounds in that window
# finished in <=2067s wall time, while EVERY interrupted round's wall time
# (driver.log's own "start" to "turn summary" timestamps) was >=2401s — a
# clean gap with zero overlap, and zero counterexamples (no round died
# `interrupted` for any other reason, e.g. OOM/crash, in this whole
# window). Each of those 7 rounds had done 127-220 real assistant turns of
# substantive work (edited files, ran tests) before being killed mid-flight
# with NO `result` event — exactly the "real work, no knowledge file, no
# research-state entry" backlog pattern rounds 144/157/159/162/165/171/175
# each independently found and had to reconcile after the fact for OTHER
# causes (one-shot no-background-wait, forgetfulness); this is a mechanical
# root cause for a meaningful share of those incidents that none of those
# reconciliation rounds identified. Also found: the outer `timeout` does
# NOT always kill within its nominal window — observed kill-completion
# delay ranged from ~1s to 936s past the deadline (likely an in-flight Bash
# tool subprocess, e.g. a slow test run, not torn down instantly by the
# forwarded SIGTERM) — so 2400 was doubly too tight: some rounds were
# killed before reaching their own graceful cutoff, AND the actual kill
# itself was not prompt. Raised to 3300 (900s more headroom, matching the
# largest observed post-deadline kill delay) so more organically-slow-but-
# still-progressing rounds reach `--max-turns 120`'s own clean stop instead
# of the wall-clock guillotine. UPDATE (round 187): the 936s max held for
# only 4 more rounds — round 185 hung on a genuinely stuck Bash tool call
# (zero output for ~48min, nowhere near a slow-but-progressing test run)
# and its own log shows a ~1235s post-deadline kill-completion delay, busting
# the 936s assumption this 3300s default was sized against. Round 187 added
# `--kill-after` (see `KILL_AFTER_S` below) to bound this going forward
# instead of raising the wall-clock timeout again, which would only recreate
# the same open-ended-wait problem at a larger number. Original text below,
# now PARTIALLY scored (see round 187's knowledge file for the full
# writeup): this should measurably reduce (not necessarily eliminate — a
# round can still be genuinely stuck) the `interrupted=true` rate over the
# next ~20-25 rounds. Overridable so tests can inject a tiny value instead
# of waiting 55 real minutes to prove the kill path still works.
TIMEOUT_S="${DRIVER_ROUND_TIMEOUT_S:-3300}"

# Round 205: `--max-turns 120` (below) is meant to be the PRIMARY, graceful
# stopgap ahead of the wall-clock `TIMEOUT_S` guillotine above — a max-turns
# death still writes a real `type:"result"` event (`error_max_turns`), so
# driver_health can classify it and the round's own thinking/tool-call data
# survives, unlike a wall-clock `interrupted=true` kill which leaves no
# `result` event at all. Flagged as a possible raise since round 145 (a
# comment in the invocation below); round 205 found LIVE that this stopped
# being hypothetical: `logs/driver.log` now shows SIX max-turns deaths
# (rounds 155, 168, 179, 182, 203, 204), each discarding 120-132 real tool
# calls of substantive work with no commit — and 203/204 were BACK TO BACK,
# the first time two consecutive rounds both hit it. Every one of the six is
# a heavy track (SWE-loop(D) campaigns, language(C) self-hosting) that ran
# well under the 3300s wall-clock cap (1173-2776s) — turn budget, not wall
# time, was the actual binding constraint, so there was slack to spend.
# Raised the default by 15 turns (120 -> 135), sized conservatively against
# the WORST observed per-tool-call rate in that six-round sample (round 203:
# 120 tool calls / 2776.258s = 23.14 s/call) so even that slowest round would
# land at ~3123s, ~177s inside the 3300s wall-clock ceiling rather than
# trading one graceful-death mechanism for the worse ungraceful one. A
# bigger raise was deliberately NOT taken: pushing the binding constraint
# from max-turns to wall-clock for the heaviest rounds would undo round
# 181's own P1 finding (this round re-tallied it CLOSED: interrupted rate
# fell from a 28% baseline to 17.4% at n=23, rounds 182-204) by converting
# max-turns' graceful, result-event-preserving deaths back into the
# no-result-event `interrupted` kind for exactly the rounds most likely to
# need the extra turns. Overridable, same convention as
# DRIVER_ROUND_TIMEOUT_S/DRIVER_KILL_AFTER_S/DRIVER_WS.
MAX_TURNS="${DRIVER_MAX_TURNS:-135}"

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

# Single-instance guard (round 157): two `bash run_driver.sh` processes
# racing on the same $STATE_FILE is a real, OBSERVED live bug, not a
# hypothetical — round 157's own session (this one) caught driver.log
# showing round 158 start while round 157's `claude` session was still
# running, then round 159 start 45s later (production's default
# LOOP_SLEEP_S, ruling out a test artifact) — a second, independent
# `bash run_driver.sh` invocation reading round_counter mid-round,
# incrementing it, and launching its OWN session with nothing waiting for
# the prior round to finish. `flock -n` on a fixed lock file makes any
# second concurrent invocation exit immediately instead of racing. fd 9
# stays open (and the lock held) across the self-exec near the bottom of
# this file's loop — `exec` preserves already-open file descriptors that
# aren't close-on-exec, and bash's `exec N>file` redirection doesn't set
# close-on-exec — so the lock covers the driver's entire lifetime, not
# just one round, with no gap between rounds for a second process to slip
# through.
mkdir -p "$WS/state" 2>/dev/null
LOCK_FILE="$WS/state/.driver.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "another run_driver.sh instance already holds $LOCK_FILE — exiting without racing it"
  exit 0
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

  # Round 253: automated record-gap check, closing round 171/195's own
  # long-standing backlog item — `check_round_recorded.py` (skills(B)'s
  # round 171 detector for "a round ran real turns, got logged as success,
  # and still left zero trace in state/research-state.md/knowledge/git" —
  # confirmed live 3x MORE in a row as recently as rounds 248/249/250, the
  # exact `one-shot-agent-no-background-wait` mechanism the detector was
  # built to name) has existed since round 171 but "still requires a
  # human/round to actually RUN it" (round 171/195's own words) — nobody
  # unilaterally wired it into the driver's own loop because that's
  # harness(A)'s file to touch, not skills(B)'s. Deliberately run BEFORE
  # this round's own "start" line is logged below: `check_round_recorded.py`
  # reads driver.log's `round N track=... start` lines as its signal that
  # round N ran, so logging this round's OWN start line first would make
  # every round flag itself as an unrecorded gap before it had done
  # anything (confirmed by hand: a bare run at this exact point in round
  # 253's own session flagged round 253 itself, zero real gaps otherwise).
  # Guarded on the script's existence, same never-blocks/diagnostic
  # convention as the two run_tests_fast.sh checks below — a tmp_path e2e
  # test workspace with no `skills/` tree at all no-ops here exactly like
  # those do for their own missing scripts. Findings are BOTH logged (for
  # driver.log-reading rounds, the existing convention) AND appended to
  # this round's own prompt (below) — logging alone reproduces the same
  # "requires someone to go read it" gap the backlog item named in the
  # first place; putting it directly in front of the round that's about to
  # start is what actually closes the loop.
  RECORD_CHECK_SCRIPT="$WS/skills/session-inheritance-audit/scripts/check_round_recorded.py"
  ROUND_GAP_NOTE=""
  if [ -f "$RECORD_CHECK_SCRIPT" ]; then
    RECORD_CHECK_OUT=$(python3 "$RECORD_CHECK_SCRIPT" 2>&1)
    RECORD_CHECK_RC=$?
    if [ "$RECORD_CHECK_RC" -eq 0 ]; then
      log "round $ROUND: record-check PASS ($(echo "$RECORD_CHECK_OUT" | tr -d '\r'))"
    elif [ "$RECORD_CHECK_RC" -eq 1 ]; then
      log "round $ROUND: record-check FOUND gap(s) — $(echo "$RECORD_CHECK_OUT" | tr '\n' ' ')"
      ROUND_GAP_NOTE="

NOTE (automated record-gap check, run before this round started — see skills/session-inheritance-audit/SKILL.md): the round(s) below ran per logs/driver.log but have no state/research-state.md entry yet. Before starting your own track's work, check whether their real work (uncommitted diffs, orphaned background processes from a dangling wait) needs to be verified and landed, per the standing cross-track convention:
$RECORD_CHECK_OUT"
    else
      log "round $ROUND: record-check errored (rc=$RECORD_CHECK_RC) — $(echo "$RECORD_CHECK_OUT" | tr '\n' ' ')"
    fi
  fi

  log "round $ROUND track=$TRACK start (driver_version=$DRIVER_VERSION) pid=$$"

  PROMPT="You are running research round $ROUND of the AGI software-engineering program.
Your track this round: $TRACK. Follow CLAUDE.md ground rules and CURRICULUM.md exactly.
Round number for file naming: $(printf '%03d' "$ROUND").
First: read state/research-state.md. Then do the work, test it, write the knowledge file,
update research-state.md. Be relentless and thorough — this is deep research, spend the tokens.$ROUND_GAP_NOTE"

  # Run with sonnet-5 (fable-5 hit weekly limit; resets ~Sunday 2026-08-30).
  # stream-json (needs --verbose) instead of json: (1) the final `result`
  # line has the SAME shape driver_health.py always classified, so nothing
  # downstream changes; (2) it ALSO emits `rate_limit_event` lines with the
  # CLI's own exact reset timestamp — round 133 found live that a 429 no
  # longer has to be an unexplained guess (see `driver_health.
  # latest_rate_limit_reset_epoch`); (3) per-turn `assistant` events let
  # `driver_health.summarize_turns` answer round 127's open "why did
  # 122-126 burn all 80 turns" question with real data next time it happens.
  run_timeout "$TIMEOUT_S" $CLAUDE_CMD -p "$PROMPT" \
    --model claude-sonnet-5 \
    --dangerously-skip-permissions \
    --allowedTools "Read,Edit,Write,Bash,Glob,Grep" \
    --output-format stream-json \
    --verbose \
    --max-turns "$MAX_TURNS" \
    > "$RLOG" 2>&1
  RC=$?

  # quota / stop detection — structured signal only (round 151). Used to be
  # a blind `grep -qiE "usage limit|rate.?limit|weekly.*limit|5-hour|..."`
  # over the WHOLE round log, which matches any embedded transcript text
  # CONTAINING those words — guaranteed the moment a round Reads
  # `state/research-state.md` (its own prose narrates this driver's
  # rate-limit history at length) regardless of whether a rate limit was
  # ever actually hit. Confirmed live: rounds 146/147/149/150 all logged
  # "quota/limit signal detected" this way while their real failure was an
  # unrelated `error_max_turns` death, and a human operator reading
  # driver.log took the message at face value — wrongly concluding the
  # weekly limit had been reached, which produced a premature
  # `state/FINAL-REPORT.md` and two manual restarts. `ratelimit_signal`
  # only looks at the CLI's own structured `api_error_status`/
  # `rate_limit_event` data, which a round's own text output cannot fake.
  if [ "$(python3 -m harness.driver_health ratelimit_signal "$RLOG" 2>/dev/null || echo no)" = "yes" ]; then
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

  # Round 241: cheap per-round harness health check, flagged as backlog
  # item 2 by round 235 ("consider whether driver_health.py or
  # run_driver.sh itself should invoke run_tests_fast.sh automatically").
  # Runs the fast core-harness smoke suite (round 235: 370 tests, ~34-45s,
  # vs. 30+ min for the full `harness/tests/` suite including SWE-loop(D)'s
  # real-interpreter campaigns) once every round, regardless of which
  # track ran or whether it succeeded — this catches a round that broke
  # the agent-harness core itself (agent loop, tool registry, driver,
  # retry/backoff, driver_health) even though only round-level `success`/
  # `status` is otherwise ever recorded. Diagnostic-only by design, same
  # as round 211's `likely_timeout_kill` classifier: logs PASS/FAIL, never
  # blocks or stops the driver — a driver that can't proceed past its own
  # test suite failing would be strictly worse than one that just notes
  # it and moves on, since a broken test can itself be the NEXT round's
  # legitimate fix target. Guarded on the script's existence (not a new
  # env var) so both e2e driver tests below (`test_run_driver_*.py`) that
  # copy only `run_driver.sh` itself into a bare tmp_path workspace — with
  # no `harness/` tree at all — no-op here exactly like every other
  # `$WS`-relative path in this script already does when its target is
  # absent, instead of needing yet another DRIVER_* override to suppress
  # a ~35-45s real pytest subprocess inside a 45s-timeout test.
  HEALTH_SCRIPT="$WS/harness/run_tests_fast.sh"
  if [ -f "$HEALTH_SCRIPT" ]; then
    HEALTH_LOG="$WS/logs/health_round_${ROUND}.log"
    if bash "$HEALTH_SCRIPT" > "$HEALTH_LOG" 2>&1; then
      log "round $ROUND: health-check PASS ($(tail -n 1 "$HEALTH_LOG" | tr -d '\r'))"
    else
      log "round $ROUND: health-check FAIL — $(tail -n 5 "$HEALTH_LOG" | tr '\n' ' ')"
    fi
  fi

  # Round 247: same shape, second track. Round 242 (language C) built
  # `languages/whence/run_tests_fast.sh` (840/875 tests, ~23s, vs. 404s+ for
  # the full whence suite) and flagged, but did not wire in, this exact
  # follow-on — "round 241's health-check design is harness(A)'s own
  # artifact" (round 242's own knowledge file §6). Separate log line
  # ("whence-health-check", not "health-check") and separate per-round log
  # file so the two checks never collide or overwrite each other; same
  # guarded-on-existence, diagnostic-only, never-blocks design as the
  # harness check above — a tmp_path e2e test workspace with no
  # `languages/` tree at all (every existing test_run_driver_*.py test)
  # no-ops here exactly as it already does for the harness check.
  WHENCE_HEALTH_SCRIPT="$WS/languages/whence/run_tests_fast.sh"
  if [ -f "$WHENCE_HEALTH_SCRIPT" ]; then
    WHENCE_HEALTH_LOG="$WS/logs/whence_health_round_${ROUND}.log"
    if bash "$WHENCE_HEALTH_SCRIPT" > "$WHENCE_HEALTH_LOG" 2>&1; then
      log "round $ROUND: whence-health-check PASS ($(tail -n 1 "$WHENCE_HEALTH_LOG" | tr -d '\r'))"
    else
      log "round $ROUND: whence-health-check FAIL — $(tail -n 5 "$WHENCE_HEALTH_LOG" | tr '\n' ' ')"
    fi
  fi

  # Safety valve (round 150+): if the log file exists but contains ZERO "type":"result""
  # entries, Claude Code likely crashed before sending its final response. Skip this round
  # and move on instead of treating it as a genuine failure (which could trigger false
  # weekly-limit detection via the 3-consecutive-failures check below).
  #
  # Round 181: found LIVE, while testing the round-timeout fix above, that this NEVER
  # actually fired for the one case it exists for. `grep -c PATTERN FILE` prints "0" to
  # stdout on a clean no-match AND exits 1 (grep's exit status distinguishes "found
  # nothing" from "found something", not success/failure) — so the old `|| echo 0`
  # fallback ALSO ran on every no-match, appending a SECOND "0" on its own line.
  # `_HAS_RESULT` ended up as the two-line string "0\n0", which fails `[ ... -eq 0 ]`
  # with "integer expression expected" (a silent, discarded error under `set -uo
  # pipefail` — no `-e`) and skips this whole if-block. Net effect: every crashed/
  # timeout-killed round (see the DRIVER_ROUND_TIMEOUT_S comment above — the exact
  # rounds this branch is FOR) fell through to the 3-consecutive-failures counter
  # below as a genuine counted failure instead of being exempted, silently
  # reintroducing round 151's "false weekly-limit stop on a workload cluster, not a
  # quota exhaustion" risk for crash/timeout clusters specifically (never observed
  # live only because no 3 crash-kills have happened back-to-back yet). Fixed by not
  # invoking a fallback command at all on the common "ran fine, 0 matches" path —
  # `${_HAS_RESULT:-0}` only substitutes when grep produced NO stdout at all (e.g. the
  # file itself is unreadable), which is the actual error case the `|| echo 0` was
  # meant to guard against.
  _HAS_RESULT=$(grep -c '"type":"result"' "$RLOG" 2>/dev/null)
  _HAS_RESULT="${_HAS_RESULT:-0}"
  if [ "$_HAS_RESULT" -eq 0 ] && [ -s "$RLOG" ]; then
    # Round 211: this branch's message said "assuming Claude crash" since
    # round 150, but the comment on TIMEOUT_S above already documents that
    # a no-result log is produced by TWO distinct causes with an identical
    # on-disk shape — a genuine process crash, AND a round killed by our
    # OWN outer `timeout $TIMEOUT_S` (confirmed live: round 210's log has
    # no result event, and its full first-to-last event span, 3296.7s, is
    # within 3s of this driver's own 3300s ceiling — almost certainly our
    # timeout firing, not a crash). Both causes get the same treatment
    # (skip, don't count as a failure) so nothing behavioral changes here —
    # this only makes the log line say which is more likely, so a future
    # round auditing driver.log doesn't have to hand-compute the span vs.
    # $TIMEOUT_S itself to tell them apart, the way round 211 had to.
    _TIMEOUT_VERDICT=$(python3 -m harness.driver_health likely_timeout_kill "$RLOG" "$TIMEOUT_S" 2>/dev/null || echo unknown)
    case "$_TIMEOUT_VERDICT" in
      yes) log "round $ROUND: file populated but no result entry (span near the ${TIMEOUT_S}s ceiling — likely our own outer-timeout kill, not a crash), skipping to next round" ;;
      no)  log "round $ROUND: file populated but no result entry (span well under the ${TIMEOUT_S}s ceiling — likely a genuine crash), skipping to next round" ;;
      *)   log "round $ROUND: file populated but no result entry (too little timestamped data to tell a crash from a timeout kill), skipping to next round" ;;
    esac
    sleep "$LOOP_SLEEP_S"
    continue
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
    # Round 151: a 3-in-a-row failure cluster is ambiguous the same way a
    # single 429 was before `is429`/`rate_limit_event` resolved that
    # ambiguity — CURRICULUM.md says stop the whole driver "only when the
    # WEEKLY limit is reached", but a max-turns death is a WORKLOAD signal,
    # not a quota one. Confirmed live: rounds 146+147 (then again 149+150
    # on a second restart) each did 140-160 real turns of substantive work
    # before hitting `--max-turns 120`, tripped this exact valve, and were
    # taken at face value as "weekly limit reached" — producing a
    # premature `state/FINAL-REPORT.md` and two manual restarts. Only
    # stop here when the cluster is NOT entirely max-turns deaths (a real
    # mix, or all genuine API errors) — a pure max-turns cluster logs
    # clearly and the driver keeps going, since nothing about it indicates
    # the account's quota is actually exhausted.
    ALL_MAXTURNS=$(python3 -m harness.driver_health all_max_turns $LAST3 2>/dev/null || echo no)
    if [ "$ALL_MAXTURNS" = "yes" ]; then
      log "round $ROUND: 3 consecutive max-turns deaths — NOT a quota signal (CURRICULUM.md: stop only on the weekly limit); continuing. If this persists, consider raising --max-turns or reducing state/research-state.md's size (flagged since round 145)."
    else
      log "3 consecutive failures — assuming weekly limit reached, stopping"
      break
    fi
  fi

  # pace against 5h rolling limit: brief cool-down between rounds
  sleep "$LOOP_SLEEP_S"

  # Structural fix (round 145, per round 139's §6 backlog item): re-exec
  # this SAME script from disk before starting the next round, instead of
  # looping via bash's cached in-memory parse of `while ... done`. Round
  # 139 found the live driver had been running a pre-round-127 copy of
  # this exact loop for 12+ rounds because bash parses a compound command
  # like this ONCE and never re-reads it — every on-disk fix from rounds
  # 127/133 had zero live effect until an external watcher killed and
  # relaunched the process. `exec` replaces the process image in place
  # (same PID, per `man bash`: "no new process is created"), so a script
  # edit landed between rounds now takes effect on the very next round
  # with no external redeploy needed — this class of bug becomes
  # structurally impossible rather than something a future round has to
  # notice and fix again. Deliberately placed AFTER the loop's `continue`
  # points (429/5xx in-round retries) so escalating-backoff state
  # (`RATE_LIMIT_ROUND`/`RATE_LIMIT_RETRIES`) is untouched by this change —
  # those paths never reach this line, only a fully-finished round does,
  # and `RATE_LIMIT_ROUND`/`RATE_LIMIT_RETRIES` are unconditionally
  # re-derived from `$ROUND` at the top of the script on the next pass
  # anyway (see the `if [ "$RATE_LIMIT_ROUND" != "$ROUND" ]` reset above),
  # identical to what already happens when a genuinely new round starts.
  # `break` paths (safety valve / budget-exhausted / rate-limit-exhausted)
  # never reach this line either, so the FINAL report step below the loop
  # still runs exactly once, as before.
  exec bash "$0" "$@"
done

log "=== driver stopping at round $ROUND ==="

# Final consolidation round (cheap, one shot)
if [ ! -f "$FINAL" ]; then
  run_timeout 900 $CLAUDE_CMD -p "The research budget is exhausted. Read all files in state/ and knowledge/
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

