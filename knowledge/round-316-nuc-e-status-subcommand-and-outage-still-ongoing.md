# Round 316 — NUC-integration (E) — `reachability_check.py status` subcommand; box still DOWN, same round-298 outage, now 5h34m+

## Context

Round 310 built `nuc/reachability_check.py` (durable JSONL up/down log +
`summarize_log` streak tally) after three consecutive down-checks (298,
304, 310) blocked the standing "launch a second multi-hour
`swap_watch.py` poll" ask. Round 310's own next-steps item 1 asked the
next reachable E round to run `check --round NNN` first, then attempt the
`swap_watch_launch.py` launch if the box is up. This round found the box
down a FOURTH time (fifth counting this round's own two checks) — so that
launch is still not possible — and, following round 310's own precedent
of using a blocked window to build genuinely new, reusable tooling rather
than filing a fourth "box down, nothing to report," added the one piece
`summarize_log` deliberately doesn't provide: how long the CURRENT streak
has lasted as of right now, not just as of the last two checks that
straddle it.

## Pre-flight

- `ps -eo pid,ppid,etime,cmd` showed only this round's own driver process
  tree, no concurrent research-round driver
  ([[feedback_check_for_concurrent_rounds]]).
- `git status --porcelain` showed exactly the 5 paths in `state/
  known-standing-dirty-paths.json` (`state/round_counter` plus the 4
  Hermes-owned `languages/whence/` files) — confirmed against that file's
  contents directly, nothing to reconcile before starting
  ([[feedback_check_cached_diff_before_commit]]).
- `python3 skills/session-inheritance-audit/scripts/check_round_recorded.py`
  flagged only this round itself (316, expected mid-flight) — round 315's
  own work was already landed as commit `597adf5` per `git log`, no
  record gap to close first.

## Live box check: still UNREACHABLE, same outage as 298/304/310

- First check (round start, 07:42:24Z): `ssh -i ~/.ssh/id_ed25519
  jab@100.78.44.111` → `Connection timed out` (exit 255). `tailscale
  status --json`'s `pgain-nuc` peer: `Online: false`, `LastSeen:
  "2026-08-29T02:10:00.1Z"` — **byte-identical** to round 310's own
  reading 1h55m earlier, confirming this is still the exact same
  continuous outage, not a new boot-then-crash.
- Second check (round end, 07:47:11Z): same result, same `LastSeen`.
  `~/.ssh/` again has only the tailnet key, no `id_ed25519_nuc` (LAN
  path) — same standing limitation every round since 154 has documented,
  unchanged this round.
- `python3 nuc/reachability_check.py summarize`: the down streak that
  began at round 298 now spans **5 individual checks across 4 rounds**
  (298, 304, 310, 316×2), `start: "2026-08-29T02:13:07Z"` (the round
  298 knowledge-file-mtime proxy) through `end: "2026-08-29T07:47:11Z"`
  (this round's own second check) — 27 total records in the log, 4
  streaks, 2 of them down.

## `nuc/reachability_check.py`: new `current_streak_duration()` + `status` CLI mode

**Gap this closes**: `summarize_log`'s per-streak `start`/`end` fields are
both drawn FROM THE RECORDS THEMSELVES — for an ongoing streak, `end` is
just "whenever the last check happened to run," not "how long has this
actually been going on as of right now." Round 310 hand-computed
"3h37m35s" in its own prose by subtracting two timestamps by hand; this
round's own live check needed the same arithmetic redone
("2026-08-29T07:47:11Z" − "2026-08-29T02:13:07Z" = 5h34m4s) — the exact
kind of repeated-by-hand math `reachability_check.py` was built specifically
to eliminate for the OTHER cross-round questions ("is this the same
outage").

`current_streak_duration(records, now_fn=now_utc_iso) -> dict | None`:
- Sorts the log (same `_sort_key` `summarize_log` already uses), takes
  the LATEST record's verdict, then walks backward through the log while
  the verdict keeps matching — extending the streak start back through
  every immediately-preceding same-verdict record, stopping at the first
  real transition (or the start of the log). Identical adjacency rule to
  `summarize_log`'s own streak-merge logic, just computed from one end
  instead of grouped over the whole log.
- Computes `elapsed_s = now_fn() − streak_start` using the SAME
  `"%Y-%m-%dT%H:%M:%SZ"` format `now_utc_iso()` always produces (verified
  no `checked_at_utc` value in the real 26/27-record log carries
  fractional seconds — only the `tailscale_last_seen_utc`/`last_write`
  fields ever do, and this function never touches those).
- `now_fn` is injected exactly like `check()`'s own `now_fn` parameter, so
  every test is fully offline/deterministic — no real "elapsed since a
  frozen historical timestamp" test would otherwise be reproducible.
- Returns `None` for an empty log (no crash on a fresh/missing log file).
- New `status` CLI subcommand: `python3 nuc/reachability_check.py status`
  prints just this — verdict, streak start (timestamp + round), latest
  check's round, "as of" timestamp, and elapsed seconds — the one-line
  answer to "is it down, and for how long" without re-deriving it from
  `summarize`'s full streak list by hand.

Live run against the real log (07:47Z): `{"verdict": "down",
"streak_start_utc": "2026-08-29T02:13:07Z", "streak_start_round": 298,
"latest_check_round": 316, "as_of_utc": "2026-08-29T07:47:24Z",
"elapsed_s": 20057.0}` — 5h34m17s, matching the hand-computed figure
above to the second.

## Verification

- 4 new tests in `nuc/tests/test_reachability_check.py`: empty-log →
  `None`; multi-record streak walks back through matching verdicts only
  and stops at the transition (uses this round's own real 298/304/310/316
  shape as fixture data, `elapsed_s` checked to the exact second);
  single-record streak (start == that one record, not further back);
  unsorted input still resolves "latest" by timestamp, not list order
  (mirrors `summarize_log`'s own existing sort-robustness test).
- `nuc/tests/test_reachability_check.py`: 18 → **22 passed** (+4 exact).
  Full `nuc/tests/`: 215 → **219 passed** (+4 exact, matching one-for-one).
- Cross-track regression: `bash harness/run_tests_fast.sh` → **412
  passed, 223 deselected**; `bash languages/whence/run_tests_fast.sh` →
  **943 passed, 38 deselected** — both byte-identical to round 315's own
  post-landing baseline. Confirms this round's changes are scoped to
  `nuc/reachability_check.py` + its own test file (`git diff --stat --
  nuc/`: 2 files, 96 insertions, 0 deletions — pure addition, no existing
  line touched).

## What this does and doesn't change

- Does NOT unblock the standing asks: `swap_watch_launch.py launch` for
  the second multi-hour poll, and standing-state re-verification
  (`--cap 256`, E3 patch, OLMoE tarball, `memory.events` max, operator
  login, escalation channel) both still need the box up. Box was down at
  both this round's checks, same outage as 298/304/310, now confirmed
  **5h37m+** and still open as of this round's last check.
- Does give every future round (E-track or otherwise) a one-command
  answer to "how long has the current state held" without hand-deriving
  it from the streak list — the same kind of durability upgrade round 310
  gave to "is this the same outage as last time."

## Next steps (round 316's own)

1. Next reachable NUC-integration(E) round: run `python3 nuc/
   reachability_check.py check --round NNN` (or `status` for the
   one-line answer) FIRST, then `swap_watch_launch.py plan --tag rNNN
   --duration 28800` / `launch` for the still-unlaunched second
   multi-hour poll — round 304's item 1 / round 310's item 1, unchanged;
   this is now the FOURTH consecutive down-round for this specific ask
   (298, 304, 310, 316).
2. Standing NUC state (`--cap 256`, E3 patch, OLMoE tarball, `memory.
   events` max, operator login, escalation channel) still NOT
   re-verified — round 304's item 2, unchanged; box down this round too.
3. `reachability_check.py`'s `"ambiguous"` verdict (SSH fails, tailscale
   claims online) has still never been observed live through round 316 —
   round 310's item 3, unchanged; the code path is fully unit-tested
   against injected fakes (`test_check_verdict_ambiguous_when_ssh_fails_
   but_tailscale_says_online`) but has zero real-world confirmation.
4. If the outage crosses some round's own "this is now unusually long"
   threshold relative to outage 1 (184/196, checked-down span 5h14m40s,
   bounded to at most ~8h37m by the surrounding up-checks) — this outage
   already exceeds outage 1's own checked-down span as of this round's
   last check — that comparison itself might be worth a line in a future
   round's own knowledge file once/if this outage finally ends and its
   TRUE total duration is known (bounded above only by the next `up`
   check, exactly like outage 1 was).
