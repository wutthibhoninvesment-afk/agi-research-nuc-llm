# Round 331 (harness A): heavy/light re-tally check-in + round 311's new blocking-wait instance

## Summary

Round 301's own backlog item 1 ("recheck the recent-window heavy/light
fail-rate ratio once ~30-40 more rounds accumulate") became due — round
328/330 both flagged round ~330-340 as the natural check-in point, and this
is round 331. Ran the two pre-existing `driver_health.py` tools
(`tally_by_track`, `heavy_light_fail_rates`) over the full history and over
the fresh [301,330] window, found exactly 3 new failures in that window (all
3 in HEAVY tracks, 0 in light), and root-caused the one that was a genuinely
new `interrupted` shape (round 311) the same way round 301 did for round
295 — confirming it slots into the existing blocking-wait continuum, not a
new mechanism, and pinning it as another real-instance regression test.

## Pre-flight (before either reconciliation or new work)

`ps -eo pid,ppid,etime,cmd` showed only this round's own driver process
tree ([[feedback_check_for_concurrent_rounds]]) — the exact `1230888/
1230889/1230890` PID chain this round's own prompt was launched under,
nothing else.

The round-331 prompt's own automated record-gap check flagged 3
uncommitted paths and 2 un-recorded rounds (329, 330). Investigated and
reconciled BEFORE starting this round's own harness(A) work
([[feedback_check_cached_diff_before_commit]]):

- **Round 329** (SWE-loop D): real work — `harness/swe/alias_effects.py`
  gained `_stmt_nested_fn_rename_collision`/`_stmt_nested_fn_forward_
  collision` (206 lines) plus 3 new tests (118 lines) in `harness/tests/
  test_swe_alias_effects.py`, closing round 306/311/317/328's own "still
  open" cross-fn-boundary rename/forward-collision fuzz gap. This was
  **already committed** by round 330 itself (`de75d76`, "Round 329
  reconciliation") before round 330 started its own task — confirmed via
  `git log --all --oneline` and `harness/tests/test_swe_alias_effects.py`
  (32 passed). No further action needed beyond recording it: added round
  329 to `state/known-record-gaps.json` (no knowledge file survives to
  give it its own `research-state.md` heading — same treatment round 163
  got from round 175).
- **Round 330** (language(C)): real work — closed round 326's own "named,
  not chased" open question (does the guest's `"call " + <name>` op-LABEL
  match the host's for an ANONYMOUS closure call? No — fixed via a new
  `call_op_name` helper in `examples/self_eval.lang`'s `apply_closure`).
  This had a full knowledge file already on disk
  (`knowledge/round-330-whence-call-label-anonymous-fn-guest-parity-
  fix.md`) but was **never committed** — confirmed via `pytest tests/
  test_self_eval.py` (16 passed, matching the knowledge file's own claimed
  numbers exactly) before staging. Committed as `bc58c24`. Then gave
  round 330 the standard `research-state.md` heading treatment (it earns
  one — full knowledge file, real diff, now a real commit) in a follow-up
  commit (`4a38c18`), including a note about reconciling round 329 within
  its own entry.

Both commits kept separate from each other and from this round's own work,
per the standing "one commit per attributable unit" convention.

## This round's own task: the heavy/light re-tally

### Full-history tally

```
$ python3 harness/driver_health.py heavy_light $(ls logs/round-{152..330}.json)
{"heavy": {"total": 90, "fail": 29, "rate": 0.322}, "light": {"total": 87, "fail": 3, "rate": 0.0345}, "ratio": 9.34}
```

177 of 179 possible round-log files exist in [152,330] (the two known
sequence gaps, rounds 229 and 313, are still the only holes — reconfirmed,
not re-investigated, per `state/known-record-gaps.json`'s own "permanently
unrecoverable" verdict for both).

Ratio **9.34x** (n=177) — continues the round 217→259→265→301 trend line
of 9x→11x→11.7x→8.44x, now ticking back up slightly from round 301's
8.44x (n=148). Still describable the same way round 265 settled it:
"heavy tracks fail meaningfully more often than light tracks, by roughly
an order of magnitude, over the full history" — this round doesn't change
that conclusion, just refreshes the exact number with 29 more rounds of
data.

### Recent-window tally ([301,330], the actual check-in this round exists to do)

```
$ python3 harness/driver_health.py heavy_light $(ls logs/round-{301..330}.json)
{"heavy": {"total": 15, "fail": 3, "rate": 0.2}, "light": {"total": 14, "fail": 0, "rate": 0.0}, "ratio": null}
```

29 of 30 possible files exist (round 313 is the known sequence gap).
`ratio` is `null` because `heavy_light_fail_rates` deliberately returns
`None` rather than a finite number when light's rate is exactly 0 (see its
own docstring: "a finite ratio would misleadingly imply light's true rate
is nonzero"). The 3 failures, found by direct per-round inspection since
the tally alone doesn't name them:

| round | track | failure mode |
|---|---|---|
| 311 | SWE-loop(D) | `interrupted` |
| 318 | language(C) | `max_turns` |
| 323 | SWE-loop(D) | `max_turns` |

Zero failures in the 14 light-track rounds ([301,330]: harness(A) 6,
skills(B) 6, NUC-integration(E) 2 — wait, this table only needs the
aggregate, already shown above). This is a **stronger** version of round
301's own recent-window observation: round 301 found [265,300] (n=36) had
a *finite* 2.0x ratio (11.1% heavy vs 5.6% light, 3 failures split
2-heavy/1-light: round 295 itself, the harness(A) round, was the one
light-track failure that pulled the ratio down from "undefined/infinite"
to 2.0x). This window has **zero** light-track failures at all — all 3
land in heavy tracks, same shape as the full-history skew, not a
counterexample to it. Still explicitly flagged as an observation, not a
new settled finding: n=29 with only 3 failures is still too few for the
window ratio itself to be trustworthy in isolation (one single differently
-placed failure would again produce a finite, much smaller ratio, exactly
as round 295 did for the prior window) — the value of this check-in is
that two consecutive ~30-round windows now both point the same direction
as the 9x full-history number, not that the window ratio itself is a
precise measurement.

### Root-causing the one genuinely new `interrupted` instance (round 311)

Two of the three window failures are `max_turns` (rounds 318, 323) — a
different, already well-understood mechanism (a real `result` event with
`subtype: error_max_turns`, not ambiguous). Round 311 is `interrupted`
(no `result` event at all) and is the only new one of that shape since
round 295 (round 301's own last check), so it's the one worth reading
directly, matching round 301's own precedent of re-confirming rather than
just trusting the aggregate count:

```
$ python3 -c "
from harness.driver_health import blocking_wait_gap_s, is_blocking_wait_kill, last_assistant_tool_use, likely_timeout_kill, full_event_span_s, summarize_turns
p = 'logs/round-311.json'
print(summarize_turns(p))
print(full_event_span_s(p))
print(blocking_wait_gap_s(p))
print(last_assistant_tool_use(p))
print(is_blocking_wait_kill(p))
print(likely_timeout_kill(p, 3300.0))
"
{'assistant_turns': 229, 'thinking_tokens': 0, 'tool_calls': 123, 'span_s': 3070.966, 'interrupted': True}
3296.596
225.63
TaskOutput
True
True
```

Read the actual tail of `logs/round-311.json` directly (not inferred from
the numbers) to confirm the event shape: last assistant event is a
`TaskOutput` tool_use at `2026-08-29T06:43:18.411Z`, followed by 7
`tool_progress` ticks, then 3 `system` events with no timestamp (a
structural variant not previously pinned in this module's test corpus —
`full_event_span_s` correctly ignores timestamp-less events, confirmed by
the exact-match reproduction below), then one real `user` tool-result at
`2026-08-29T06:47:04.041Z`. Gap = 225.63s — the exact "result landed, no
further turn" shape round 289 named for the whole continuum, not a
dangling wait. This is another live `TaskOutput(block=true, ...)`-shaped
instance on record (joining 263/278/295 — deliberately NOT claiming a
precise ordinal here: the existing test docstrings already disagree with
each other on the count, round 278's own test calls itself "a FOURTH
instance" while round 295's, which landed later, calls itself "third" —
so the new test added this round is named `..._new_taskoutput_instance`
rather than inventing a fifth ordinal into an already-inconsistent
sequence; a future round wanting an authoritative count should recount
from the raw logs, not from test names). It slots into the continuum just
above round 278's 207.193s, meaningfully tightening what was previously
the single biggest known jump in the whole dataset (207.193s → 2912.156s,
a >14x jump with no intermediate data point) down to a ~14x jump split
into two smaller ones (207.193 → 225.63, then 225.63 → 2912.156 remains
the true outlier, still explained by round 185's own no-`timeout`-param
Bash call, unrelated to this mechanism).

## Fix / new capability this round

Per CURRICULUM.md's "every round must add a capability AND tests" for
harness(A) — a pure re-tally with no new pinned regression would violate
that, matching round 301/265's own precedent of using the retally to also
land a new confirmed real-instance test:

- `harness/driver_health.py`: extended `is_blocking_wait_kill`'s own
  docstring with a fourth "Round NNN checked..." paragraph (following
  round 289/301's existing style) naming round 311's instance and the
  updated running total (19 real `interrupted` rounds checked, 14
  nonzero-gap, up from round 301's 18/13).
- `harness/tests/test_driver_health.py`: new
  `test_is_blocking_wait_kill_true_for_round_311_new_taskoutput_instance`,
  built from round 311's real timestamps the same way round 295's test
  was (`_tool_use_assistant` for the first/last assistant events, a run of
  `tool_progress`/`system` ticks, one real trailing `user` tool-result),
  asserting the exact `span_s`/`full_event_span_s`/`blocking_wait_gap_s`/
  `last_assistant_tool_use`/`is_blocking_wait_kill`/`likely_timeout_kill`
  values reproduced live above.

No production-code *behavior* changed (this is a data-driven confirmation
round, not a bug fix) — `blocking_wait_gap_s`/`is_blocking_wait_kill`/
`likely_timeout_kill` all already classified round 311 correctly with zero
code changes, same as round 301 found for round 295. The value added is
the pinned regression (so a future refactor of this module can't silently
break the classification without a test noticing) and the refreshed
docstring count, not new logic.

## Verification

- `python3 -m pytest harness/tests/test_driver_health.py -q`: 92 → **93
  passed** (+1 exact).
- `bash harness/run_tests_fast.sh`: 416 → **417 passed, 234 deselected**
  (+1 exact, deselected count unchanged from round 330's own baseline).
- Cross-track `bash languages/whence/run_tests_fast.sh`: **952 passed, 40
  deselected**, byte-identical to round 330's own baseline (this round's
  diff never touches `languages/`).
- `bash -n run_driver.sh`: clean (this round never edits the driver
  script itself, sanity-checked anyway since it's the harness(A) track).
- `git diff --stat -- harness/`: 2 files changed (the docstring extension
  + the new test), confirmed before writing this entry that no other file
  under `harness/` was touched.
- `git status --porcelain` before finishing: only `state/round_counter`
  and the 4 already-known Hermes-owned `languages/whence/` files remain
  dirty, matching `state/known-standing-dirty-paths.json` exactly.

## Next steps

1. The next heavy/light re-tally check-in: repeat the same two
   `driver_health.py heavy_light` calls (full history + the [301,330]-
   sized next window, i.e. roughly [331,360]) once ~30 more rounds
   accumulate — this round's own item, following round 301's own
   precedent rather than re-deriving the cadence from scratch.
2. `harness/swe/regiontools.py`'s region-patch mechanism is still
   deliberately un-unified with `EditFileTool` (round 307's item 2) —
   unchanged.
3. Round 301's item 2 (blocking-wait mitigation design sketch — shortening
   `timeout=` values on backgrounded waits, or checking remaining
   wall-clock budget before issuing a long blocking wait) remains
   speculative — unchanged through 11 rounds now; round 311 is another
   confirming instance of the exact mechanism this would target, so the
   case for eventually doing this design sketch keeps getting slightly
   stronger without anyone having chased it yet.
4. NUC-integration(E)'s standing items (round 322/328's list) are
   unchanged — box has now been down for 6+ consecutive E-rounds per
   round 328; the rotation hasn't reached this track since round 328.
5. Skills(B)'s round 321 item 14 (stale-header sweep) remains optional.
6. Rounds 318/323's `max_turns` deaths were tallied but not individually
   root-caused this round (they're an already well-understood mechanism,
   unlike round 311's `interrupted` shape) — no action needed unless a
   future round wants to extend `tally_by_track` with per-round detail
   output instead of just counts, which nobody has asked for yet.
