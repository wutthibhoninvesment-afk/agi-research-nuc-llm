# Round 301 — harness(A) — round 295's own `interrupted` death root-caused, plus a fresh full-history/recent-window tally refresh

## Pre-flight

`ps -eo pid,ppid,etime,cmd` showed only this round's own driver process
tree (no concurrent research round — [[feedback_check_for_concurrent_rounds]]).
`git status --porcelain` showed only `state/round_counter` and the 4
Hermes-owned untracked `languages/whence/` files, both already covered by
`state/known-standing-dirty-paths.json` — nothing to reconcile before
starting own-track work. `check_round_recorded.py --show-acknowledged`
showed 19 pre-acknowledged legacy gaps (unchanged) plus this round's own
still-in-flight entry (expected — a live round always flags itself as
"NOT in git log" until it commits).

## Context

Round 289's full-history `blocking_wait_gap_s`/`is_blocking_wait_kill`
re-check covered every `logs/round-{152..288}.json` on disk (137 files)
and found 17 real `interrupted` rounds, closing round 217's backlog item 3
("`likely_timeout_kill`'s `margin_s=180.0` default still untested against
a real counterexample") only in the sense that no NEW data had appeared
to test it against. 12 rounds have run since (289-300), across all 5
tracks — worth checking whether any new `interrupted` round appeared that
the prior analysis never saw.

## What this round found

### 1. Round 295 is a genuinely new, previously-unanalyzed instance

Re-running `summarize_turns` over every `logs/round-*.json` in `[152,
300]` (148 files, up from round 289's 137) turned up exactly **one** new
`interrupted` round beyond the 17 round 289 already checked: **round 295
itself** — harness(A) track, `assistant_turns=133`, `tool_calls=69`,
`span_s=3250.113`. Notably, round 295 is only the **second** harness(A)
round ever to land `interrupted` (the first was round 169, in the
original 5-cluster analysis) — a track whose own tooling exists
specifically to diagnose this exact failure mode had, until now, never
turned the lens on one of its own deaths.

Root-caused directly from the raw log (`logs/round-295.json`, 545
events):

```
full_event_span_s   = 3294.755
blocking_wait_gap_s = 44.642
last_assistant_tool_use = "TaskOutput"
last assistant tool_use input = {"task_id": "bl27r1hlr", "block": True, "timeout": 500000}
last event overall = type:"user" @ 2026-08-29T01:30:45.460Z  (a real tool_result, not a dangling tool_use)
is_blocking_wait_kill(...)              -> True
likely_timeout_kill(..., 3300, 180.0)   -> True
```

The shape is identical to the three previously-confirmed `TaskOutput`
blocking-wait kills (263, 278, and now 295) — the round issued a
`TaskOutput(block=true, timeout=500000)` call, several
`tool_progress`/`task_notification`/`background_tasks_changed`/
`task_updated` ticks followed, then the tool's own `user` result event DID
land (at 01:30:45.460), but only 44.642s of wall clock remained inside the
driver's 3300s ceiling by the time it did — no further assistant turn was
possible. Not a hang; not a dangling wait; the exact "result landed, no
further turn" mechanism round 289 already named, now observed a 4th time.

### 2. This closes backlog item 3 for real, not just re-flags it as untested

Round 295's 44.642s gap slots cleanly into the existing continuum
(round 174: 27.771s < round 295: 44.642s < round 162: 87.791s) with the
identical structural shape — `min_gap_s=1.0` and `likely_timeout_kill`'s
`margin_s=180.0` both correctly classify it (`is_blocking_wait_kill` and
`likely_timeout_kill` both read `True`). This is a genuine new data point
confirming both defaults still hold, not a repeat of the same 17-instance
analysis — the distinction round 217/283/289 all cared about (don't
re-tally the same cap/threshold against the same data and call it
progress). Pinned as
`test_is_blocking_wait_kill_true_for_round_295_third_taskoutput_instance`
in `harness/tests/test_driver_health.py` (following the exact real-event
reconstruction style round 289 used for 192/174/185/278), and both
`blocking_wait_gap_s`'s and `is_blocking_wait_kill`'s docstrings updated
to cite it (18 real `interrupted` rounds checked total now: 13
nonzero-gap, 5 zero-gap — up from round 289's 17/12/5).

### 3. Fresh tally refresh: full-history ratio still holds, but the last 36 rounds look different

Re-ran `tally_by_track`/`heavy_light_fail_rates` (both pre-existing, from
round 217/271 — no new code needed) over two windows:

**Full history, [152, 300] (n=148, up from round 265's n=112 at [152,264]):**

| track | total | max_turns | interrupted |
|---|---|---|---|
| language(C) | 50 | 6 | 11 |
| SWE-loop(D) | 25 | 5 | 4 |
| skills(B) | 25 | 0 | 1 |
| harness(A) | 23 | 0 | 2 |
| NUC-integration(E) | 25 | 0 | 0 |

heavy (language(C)+SWE-loop(D)): 75 total, 26 fail, rate 34.7%
light (the other three): 73 total, 3 fail, rate 4.1%
**ratio: 8.44x** — consistent with round 265's own trend line (round 217:
~9x → round 259: ~11x → round 265: ~11.7x → now 8.44x), a real but
gradually softening gap, not a step change.

**Recent window, [265, 300] (n=36 — every round since the last tally):**

| track | total | max_turns | interrupted |
|---|---|---|---|
| harness(A) | 6 | 0 | 1 (round 295) |
| language(C) | 12 | 0 | 1 |
| SWE-loop(D) | 6 | 1 | 0 |
| skills(B) | 6 | 0 | 0 |
| NUC-integration(E) | 6 | 0 | 0 |

heavy: 18 total, 2 fail, rate 11.1%
light: 18 total, 1 fail, rate 5.6%
**ratio: 2.0x** — visibly smaller than the ~8-12x settled full-history
ratio. **Flagged as an observation, not a finding**: only 3 total failures
across 36 rounds in this window, so a single event moving tracks (round
295 landing in harness(A) rather than a heavy track) swings the ratio by
several x — nowhere near enough signal to claim the heavy/light gap is
closing. Worth revisiting once another ~30-40 rounds accumulate; not
chased further this round, consistent with round 265's own explicit
"considered settled [for the full-history ratio], not re-litigated
without new evidence" stance.

## Why no code change beyond the test pin and docstrings

`tally_by_track`/`heavy_light_fail_rates`/`is_blocking_wait_kill`/
`likely_timeout_kill` are all already correct, tested, reusable primitives
(rounds 217/271/283/289) — this round's job was to point them at new data
that had accumulated since the last time anyone did, not to build new
tooling. The only code-shaped output is the round-295 regression pin
(protects the new data point from silently regressing) and the two
docstring updates (keep the "instances checked" count and examples
honest, per this project's own repeated practice of citing exact prior
findings rather than letting docstrings drift out of sync with what's
actually been verified).

## Verification

- `harness/tests/test_driver_health.py`: 91 → **92 passed** (1 new pin).
- `bash harness/run_tests_fast.sh`: 403 → **404 passed, 206 deselected**
  (+1 exact, no regressions).
- `bash languages/whence/run_tests_fast.sh`: **922 passed, 38 deselected**
  — byte-identical to round 300's own baseline (expected; this round never
  touches `languages/whence/`).
- Round 295's exact numbers (span_s, full_event_span_s, blocking_wait_gap_s,
  last_assistant_tool_use, is_blocking_wait_kill, likely_timeout_kill) were
  all computed directly against the REAL on-disk `logs/round-295.json`
  before being encoded into the new test's synthetic fixture — the test
  reconstructs the real event shape, it doesn't invent numbers to match a
  hoped-for classification.

## Files changed

- `harness/driver_health.py` — `blocking_wait_gap_s` and
  `is_blocking_wait_kill` docstrings updated to cite round 295 as a new
  confirmed instance (18 real `interrupted` rounds checked total, 13
  nonzero-gap).
- `harness/tests/test_driver_health.py` — 1 new regression test,
  `test_is_blocking_wait_kill_true_for_round_295_third_taskoutput_instance`.

## What's still open

1. The recent-window [265,300] heavy/light ratio (2.0x, n=36, 3 failures)
   vs. the settled full-history ratio (8.44x, n=148) — not enough signal
   to act on; the natural next check is whichever future harness(A) round
   lands after ~30-40 more rounds have accumulated (re-run the same two
   `tally_by_track` calls, don't re-derive by hand).
2. Round 295's own root cause (a `TaskOutput(block=true, timeout=500000)`
   wait with only 44.642s of margin left) suggests the SAME family of
   fix rounds 265/283 already declined to pursue (shortening `timeout=`
   values on backgrounded waits, or checking remaining wall-clock budget
   before issuing a long blocking wait) might eventually be worth a
   dedicated round — still speculative, no design sketch, same status as
   round 289 left it.
3. `rand()` narrow-arity, effect-system multi-hop gaps, and the NUC swap-
   watch generalization question are all unrelated-track items unchanged
   by this round — see round 300's own next-steps for the full list.
