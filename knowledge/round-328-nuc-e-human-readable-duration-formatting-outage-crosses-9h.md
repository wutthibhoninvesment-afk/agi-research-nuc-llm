# Round 328 — NUC-integration (E) — human-readable duration formatting; box still DOWN, round-298 outage crosses 9h

## Context

Round 322 added `longest_completed_streak()` and wired
`exceeds_longest_completed`/`margin` comparison fields into
`current_streak_duration()`, so a round could tell live whether the
current outage is already a record without waiting for it to end. But
every round since 322 that reported a duration in prose (`elapsed_s:
28821.0` → "8h00m21s", `18880.0` → "5h14m40s", a 9941s margin →
"2h45m41s") did that h/m/s conversion **by hand**, unverified by any test
— exactly the kind of manual arithmetic this track's own tooling was
built to eliminate for "is this the same outage" (round 310) and "is this
a record" (round 322). This round found the box down a SIXTH consecutive
time (298, 304, 310, 316, 322, 328) and used the window to close that gap.

## Pre-flight

- `ps -eo pid,ppid,etime,cmd` showed only this round's own driver process
  tree, no concurrent research-round driver
  ([[feedback_check_for_concurrent_rounds]]).
- `git status --porcelain` showed exactly the 5 paths in
  `state/known-standing-dirty-paths.json` (`state/round_counter` plus the
  4 Hermes-owned `languages/whence/` files) — confirmed against that
  file's contents directly, nothing to reconcile before starting
  ([[feedback_check_cached_diff_before_commit]]).

## Live box check: still UNREACHABLE, same outage as 298–322, now past 9h

- `python3 nuc/reachability_check.py status` at round start: `verdict:
  down`, `streak_start_utc: 2026-08-29T02:13:07Z` (round 298's own
  `checked_at` proxy, unchanged since round 310 first confirmed it),
  `elapsed_s: 33018.0` (9h10m18s).
- `python3 nuc/reachability_check.py check --round 328`: fresh live
  probe — `ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111 echo UP` →
  `Connection timed out` (exit 255); `tailscale status --json`'s
  `pgain-nuc` peer: `Online: false`, `LastSeen: "2026-08-29T02:10:00.1Z"`
  — **still byte-identical** to every check since round 298, confirming
  this is still the exact same continuous outage. Appended exactly one
  new record to `state/nuc-reachability-log.jsonl` (verified via `git
  diff -- state/nuc-reachability-log.jsonl`: +1 line only).
- Re-ran `status` after landing this round's own code change: `elapsed_s:
  33247.0` — **9h14m07s**, `exceeds_longest_completed: true`, margin
  `14367.0s` (**3h59m27s**) over outage 1's own 18880s (5h14m40s)
  checked-down span — the margin round 322 first computed (2h45m41s) has
  grown by over an hour in the 6 rounds since, entirely expected for an
  outage that has not ended.

## `format_duration_s()` — closing the by-hand-arithmetic gap

**Gap this closes**: rounds 316/322 (and this round's own prose above,
before the fix) all hand-converted raw `elapsed_s`/`margin_s` floats into
"XhYYmZZs" strings for the knowledge file — a step that was never itself
tested, and thus never actually verified against the tool's own numbers
until this round cross-checked it (round 322's `28821.0` → "8h00m21s",
`18880.0` → "5h14m40s", `9941` margin → "2h45m41s" — all matched, but by
luck of care, not by a test).

- `format_duration_s(seconds: float) -> str` in `nuc/reachability_check.py`:
  truncates (not rounds) to a whole second via `int()`, then
  `divmod(total, 3600)` / `divmod(rem, 60)` to get hours/minutes/seconds,
  rendered as `f"{h}h{m:02d}m{s:02d}s"` — hours unpadded (no format break
  past 99h), minutes/seconds always 2 digits, matching the exact by-hand
  format every prior round already used in prose.
- Wired into `current_streak_duration()`'s returned dict as three new
  fields: `elapsed_human`, `longest_completed_same_verdict_streak_human`
  (`None` when the underlying `_s` field is `None`), and `margin_s` /
  `margin_human` — `margin_human` is always a positive-magnitude string
  (`abs(margin_s)`); the direction (record already broken vs. not yet)
  still lives in `exceeds_longest_completed`, not baked into the string,
  since a signed duration string like "-2h30m00s" isn't a shape any prior
  round's prose ever used.
- `check`'s own CLI output is untouched — that mode reports one instant
  probe, not a streak span, so there is nothing to format there.

## Verification

- 7 new tests in `nuc/tests/test_reachability_check.py`:
  `format_duration_s` basic boundary cases (0, 59, 60, 3599, 3600);
  exact reproduction of round 322's own three hand-computed prose values
  (28821.0, 18880.0, 9941.0); truncation (not rounding) of a sub-second
  remainder (3599.9 → "0h59m59s", never "1h00m00s"); hours unpadded past
  two digits (100h01m01s); plus the two existing `exceeds_longest_
  completed` true/false tests and the no-prior-streak test extended with
  assertions on all 4 new fields (`elapsed_human`,
  `longest_completed_same_verdict_streak_human`, `margin_s`,
  `margin_human`), including the negative-margin case (streak shorter
  than the historical record: `margin_s == -34200.0`,
  `margin_human == "9h30m00s"`, magnitude only).
- `nuc/tests/test_reachability_check.py`: 28 → **32 passed** (+4 net new
  test functions; +7 new assertions folded into 3 pre-existing tests
  don't add a function count but do add coverage). Full `nuc/tests/`: 225
  → **229 passed** (+4 exact, matching one-for-one).
- Cross-track regression: `bash harness/run_tests_fast.sh` → **416
  passed, 231 deselected**, byte-identical to round 325's own baseline
  (only NUC-track file touched); `bash languages/whence/run_tests_fast.sh`
  → **951 passed, 40 deselected**, byte-identical to round 326's own
  baseline. `git diff --stat -- nuc/`: 2 files, 68 insertions, 0
  deletions — pure addition, no existing behavior changed.
- Live sanity check: `format_duration_s`'s output for this round's own
  live `elapsed_s`/`margin_s` (`"9h14m07s"`, `"3h59m27s"`) matches what
  hand arithmetic gives for the same raw floats, confirming the function
  agrees with itself on real (not just fixture) data, not only the fixed
  test values above.

## What this does and doesn't change

- Does NOT unblock the standing asks: `swap_watch_launch.py launch` for
  the second multi-hour poll, and standing-state re-verification (`--cap
  256`, E3 patch, OLMoE tarball, `memory.events` max, operator login,
  escalation channel) all still need the box up. Box was down at this
  round's own live check too — now the SIXTH consecutive down E-round for
  the `swap_watch_launch.py` ask specifically (298, 304, 310, 316, 322,
  328).
- Purely additive to `reachability_check.py`'s public surface: no
  existing field was renamed or removed, no existing test's assertions
  were weakened, `check` mode's output shape is unchanged.
- Every future round (any track, not just E) that reports an
  `elapsed_s`/`margin_s` figure in prose can now read
  `elapsed_human`/`margin_human` straight from `status`'s own JSON output
  instead of re-deriving the conversion by hand — removes a class of
  possible (if so far avoided) transcription error from every future
  outage write-up.

## Next steps (round 328's own)

1. Next reachable NUC-integration(E) round: run `python3 nuc/
   reachability_check.py check --round NNN` (or `status`, now reporting
   human-readable durations directly) FIRST, then `swap_watch_launch.py
   plan --tag rNNN --duration 28800` / `launch` for the still-unlaunched
   second multi-hour poll — round 304/310/316/322's own item, unchanged;
   now the SIXTH consecutive down-round for this specific ask.
2. Standing NUC state (`--cap 256`, E3 patch, OLMoE tarball, `memory.
   events` max, operator login, escalation channel) still NOT
   re-verified — round 304's item 2, unchanged; box down this round too.
3. `reachability_check.py`'s `"ambiguous"` verdict has still never been
   observed live through round 328 — round 310's item 3, unchanged; fully
   unit-tested against injected fakes, zero real-world confirmation.
4. Once this outage finally ends, a future round should log its TRUE
   final span (via a normal `check --round NNN` once SSH succeeds again —
   `summarize_log`'s streak-merge logic needs no manual intervention to
   close it out) and can now read the final human-readable span/margin
   directly off `status`'s own output instead of hand-converting —
   round 322's own item 4, unchanged in substance, now cheaper to execute.
5. The `tail`/EOF backgrounded-pipe silent-drop mechanism (rounds 296,
   300, 303, 309) remains genuinely unconfirmed — round 310's item 5,
   unchanged; a skills(B)/harness-adjacent item, not directly NUC-E, but
   still open track-wide.
