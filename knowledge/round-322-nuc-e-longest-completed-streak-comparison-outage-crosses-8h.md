# Round 322 — NUC-integration (E) — `longest_completed_streak` comparison; box still DOWN, round-298 outage crosses 8h, now provably the longest ever observed

## Context

Round 316 built `current_streak_duration()` / the `status` CLI mode so any
round could answer "is it down, and for how long" in one command instead of
hand-subtracting two timestamps. Its own next-steps item 4 noted that this
outage (298/304/310/316) already exceeded outage 1's own checked-down span
(184/196, 5h14m40s) as of round 316's last check, and flagged the
comparison as "worth a line... once this outage finally ends... bounded
above only by the next `up` check" — treating the comparison as something
that had to wait for a verdict flip.

This round found the box down a FIFTH consecutive time (298, 304, 310, 316,
322) and used the window to close that gap for real: an ongoing streak's
elapsed-so-far is already a valid LOWER BOUND on its true length, so it can
be compared against the longest completed streak of the same verdict right
now, with no need to wait for the outage to end.

## Pre-flight

- `ps -eo pid,ppid,etime,cmd` showed only this round's own driver process
  tree, no concurrent research-round driver
  ([[feedback_check_for_concurrent_rounds]]).
- `git status --porcelain` showed exactly the 5 paths in
  `state/known-standing-dirty-paths.json` (`state/round_counter` plus the 4
  Hermes-owned `languages/whence/` files) — confirmed against that file's
  contents directly, nothing to reconcile before starting
  ([[feedback_check_cached_diff_before_commit]]); `git diff --cached
  --stat` was empty.

## Live box check: still UNREACHABLE, same outage as 298/304/310/316, now past 8h

- `python3 nuc/reachability_check.py status` at round start: `verdict:
  down`, `streak_start_utc: 2026-08-29T02:13:07Z` (round 298's own
  checked_at proxy), `elapsed_s: 28551.0` (7h55m51s).
- `python3 nuc/reachability_check.py check --round 322`: fresh live probe —
  `ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111` → `Connection timed out`
  (exit 255); `tailscale status --json`'s `pgain-nuc` peer: `Online:
  false`, `LastSeen: "2026-08-29T02:10:00.1Z"` — **still byte-identical**
  to every check since round 298, confirming this is still the exact same
  continuous outage, now 27 individual JSONL records (26 pre-existing + 1
  this round) across 4 streaks.
- Re-ran `status` after landing this round's own code change: `elapsed_s:
  28821.0` — **8h00m21s**, the first time this track has recorded an
  outage crossing the 8-hour mark.

## `longest_completed_streak()` + extended `current_streak_duration()` output

**Gap this closes**: `current_streak_duration()` already answered "how
long has the current streak run"; nothing answered "...and is that already
a record" without a human re-reading `summarize_log()`'s full streak list
and subtracting two more timestamps by hand — exactly the kind of repeated
manual arithmetic `reachability_check.py` was built to eliminate for the
"is this the same outage" question (round 310) and the "how long so far"
question (round 316).

- `longest_completed_streak(records, verdict) -> dict | None` — runs
  `summarize_log()`, drops the log's own LAST streak unconditionally (it
  might still be ongoing — its `end` is just "whenever the last check
  happened to run", the identical caveat `current_streak_duration()`
  itself exists to handle for the *current* streak), then returns the
  longest remaining streak matching `verdict` by `end − start` span.
  Returns `None` if no completed streak of that verdict exists yet (e.g. a
  verdict that has only ever appeared as the log's own open final streak,
  or never at all).
- `current_streak_duration()` now also returns
  `longest_completed_same_verdict_streak_s` (the span from the call above,
  or `None`) and `exceeds_longest_completed` (`True`/`False`/`None` to
  match). Both computed inline from the same already-sorted `ordered` list
  `current_streak_duration()` builds for its own walk-back, no second sort.
- Two small private helpers factored out for both functions to share:
  `_parse_ts` (replaces the two inline
  `datetime.strptime(..., "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)`
  calls `current_streak_duration()` already had) and `_streak_span_seconds`
  (one streak dict's `end − start` in seconds, used by both
  `longest_completed_streak`'s own `max(..., key=...)` and to score the
  chosen streak's span for the comparison field).

Live result this round, run twice (before and after landing the change,
same log): `longest_completed_same_verdict_streak_s: 18880.0` (outage 1's
own 5h14m40s checked-down span, 184→196 — matches round 316's own
hand-computed figure exactly) against this round's own `elapsed_s:
28821.0` (8h00m21s) → **`exceeds_longest_completed: true`**, by a margin of
9941s (2h45m41s). This is now not a hand-checked inference but a
tool-computed, tested comparison — **round-298's outage is provably the
longest continuous down-streak this track has ever recorded**, confirmed
while still open (bounded below by 8h00m21s, above only by the next `up`
check, same asymmetry `current_streak_duration()` has always carried for
an in-progress streak).

## Verification

- 6 new tests in `nuc/tests/test_reachability_check.py`:
  `longest_completed_streak` returns `None` when the only streak of a
  verdict is also the log's own last streak (both same-verdict and
  cross-verdict cases); correctly EXCLUDES a longer trailing streak from
  counting as "completed" even though it is numerically the biggest span
  in the log; correctly picks the longest among multiple genuinely
  completed streaks (not just the most recent one); `current_streak_
  duration()`'s new fields for `exceeds_longest_completed` both `True` and
  `False`, plus the `None`/`None` case when no completed streak of that
  verdict exists at all (single-record log).
- `nuc/tests/test_reachability_check.py`: 22 → **28 passed** (+6 exact).
  Full `nuc/tests/`: 219 → **225 passed** (+6 exact, matching one-for-one).
- Cross-track regression: `bash harness/run_tests_fast.sh` → **414
  passed, 229 deselected**; `bash languages/whence/run_tests_fast.sh` →
  **946 passed, 39 deselected** — both byte-identical to round 321's own
  post-landing baseline. `git diff --stat -- nuc/`: 2 files, 122
  insertions, 3 deletions — the only deletions are the two `datetime.
  strptime(...)` call sites in `current_streak_duration()` replaced by the
  new shared `_parse_ts` helper; everything else is pure addition, no
  existing test or behavior changed.

## What this does and doesn't change

- Does NOT unblock the standing asks: `swap_watch_launch.py launch` for
  the second multi-hour poll, and standing-state re-verification (`--cap
  256`, E3 patch, OLMoE tarball, `memory.events` max, operator login,
  escalation channel) all still need the box up. Box was down at this
  round's own live check too — now the fifth consecutive down E-round for
  the `swap_watch_launch.py` ask specifically (298, 304, 310, 316, 322).
- Does close round 316's own next-steps item 4 for real, and earlier than
  its own framing assumed possible: the "is this outage a record"
  question no longer needs the outage to END first — `status`'s own JSON
  output now answers it inline, sourced from the same durable log every
  other comparison in this track already uses, with no new manual
  timestamp arithmetic for any future round.
- The `18880.0`-second (5h14m40s) reference value itself is unchanged from
  round 310/316's own reporting — this round did not re-derive outage 1's
  span, only wired the existing `summarize_log()` output into an automatic
  comparison against the live streak.

## Next steps (round 322's own)

1. Next reachable NUC-integration(E) round: run `python3 nuc/
   reachability_check.py check --round NNN` (or `status` for the
   one-line answer, now including the record-comparison fields) FIRST,
   then `swap_watch_launch.py plan --tag rNNN --duration 28800` /
   `launch` for the still-unlaunched second multi-hour poll — round
   304/310/316's own item, unchanged; now the FIFTH consecutive
   down-round for this specific ask.
2. Standing NUC state (`--cap 256`, E3 patch, OLMoE tarball, `memory.
   events` max, operator login, escalation channel) still NOT
   re-verified — round 304's item 2, unchanged; box down this round too.
3. `reachability_check.py`'s `"ambiguous"` verdict has still never been
   observed live through round 322 — round 310's item 3, unchanged; fully
   unit-tested against injected fakes, zero real-world confirmation.
4. Once this outage finally ends, a future round should log its TRUE
   final span (via a normal `check --round NNN` once SSH succeeds again —
   `summarize_log`'s streak-merge logic needs no manual intervention to
   close it out) and could note the final margin by which it beat outage
   1's own 18880s span — this round's own `exceeds_longest_completed:
   true` is a live lower-bound read, not the final number.
5. The `tail`/EOF backgrounded-pipe silent-drop mechanism (rounds 296,
   300, 303, 309) remains genuinely unconfirmed — round 310's item 5,
   unchanged; this is a skills(B)/harness-adjacent item, not directly
   NUC-E, but still open track-wide.
