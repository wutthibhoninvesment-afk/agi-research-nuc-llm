# Round 283 — harness(A) — a reusable `is_blocking_wait_kill` detector, and backlog item 9's round-224-scale TURN COUNT question finally answered

## Context

`harness/driver_health.py`'s `interrupted` classification has, since round
211, distinguished a genuine early crash from a near-ceiling wall-clock
kill via `full_event_span_s` (spans ALL event types) vs `summarize_turns`'s
assistant-only `span_s`. Three separate rounds — 223 (on round 222), 265
(on round 263), and now this one (on round 278) — have each, by hand,
subtracted these two spans, found a large gap, and read the round's
trailing raw events to confirm the same shape: the model issues a
`TaskOutput`/`Bash` tool call, several untimestamped `tool_progress` ticks
follow, then the driver's own outer `timeout` fires while the round is
genuinely, synchronously blocked waiting for that tool's result. Backlog
item 9 (rounds 265/271/277/279's own next-steps) has stood open the whole
time on a related, harder question: is round 224 — the highest-turn-count
`interrupted` round on record (assistant_turns 220, tool_calls 118) — a
DIFFERENT mechanism (raw generation volume outstripping the wall clock)
from the low-turn-count blocking-wait deaths, or just an extreme case of
the same thing? Nobody had checked round 224's own gap value.

Also, per round 279's own next-steps item 4: round 278 (language C) was
the first live `interrupted` round since round 263 (264-277 were all
clean per round 277's tally) — flagged as needing a fresh
`harness.driver_health tally` note, not yet done.

## What this round did

**1. Promoted the by-hand diagnosis into reusable primitives** (same
rationale round 271 gave for promoting `heavy_light_fail_rates` after it
had been manually re-derived three times — this diagnosis had now also
hit three manual derivations):

- `blocking_wait_gap_s(path)` — `full_event_span_s(path) -
  summarize_turns(path)["span_s"]`. None if either span is unavailable.
- `last_assistant_tool_use(path)` — name of the `tool_use` block in the
  LAST `type: "assistant"` event (e.g. `"TaskOutput"`), or None if that
  event has no tool_use (plain text/thinking) or there are no assistant
  events. **Does NOT by itself distinguish the two kill mechanisms** — see
  the round-224 finding below, which is exactly why this function's
  docstring warns against using it alone.
- `is_blocking_wait_kill(path, min_gap_s=100.0)` — True iff the round was
  `interrupted` AND `blocking_wait_gap_s >= min_gap_s`. None if the round
  wasn't `interrupted` at all, or the gap can't be computed. `min_gap_s`
  defaults to 100s: well above CLI/event-flush jitter (round 210's
  write-race gap is exactly 0) and well below the smallest confirmed real
  instance (round 278's 207.193s).

CLI subcommands `blocking_wait_gap` and `is_blocking_wait_kill` added to
`main()`, following the existing `likely_timeout_kill` pattern exactly
(usage-error exit 2 on bad arity, `"yes"/"no"/"unknown"` text output).

**2. Ran the new tools against every real interrupted-with-no-result log on
disk** (not just constructed fixtures) — this is where the actual research
finding is:

| round | assistant_turns | tool_calls | gap (s) | last tool_use | blocking-wait kill? |
|-------|-----------------|------------|---------|----------------|----------------------|
| 210   | 200 (approx.)   | -          | 0.0     | None (plain text) | **False** |
| 222   | -               | -          | 303.512 | Bash           | **True**  |
| **224** | **220**       | **118**    | **0.0** | **Bash**       | **False** |
| 263   | 136             | 81         | 338.590 | TaskOutput     | **True**  |
| **278** | **153**       | **85**     | **207.193** | **TaskOutput** | **True**  |

Round 224's gap is **exactly 0.0** — its last assistant event (a `Bash`
call catting a background task's output file) is the LAST event in the
entire 691-event log, full stop: no trailing `tool_progress` ticks, no
trailing `user` tool-result, nothing. The driver's wall clock guillotine
fell the INSTANT that tool_use was emitted, before the CLI had even
started executing it. This settles backlog item 9 with real evidence
rather than a fourth data point still "not yet conclusively separable":

- **Round 224 is NOT a blocking-wait death.** It is the OTHER mechanism —
  the round was still genuinely, actively emitting content (turn 220 of
  what would have been turn 221) at the exact moment the wall clock ran
  out. High turn/tool-call volume alone (220/118, more than double round
  263's 136/81) is sufficient to hit the 3300s ceiling purely through
  generation time, with no dangling wait involved at all.
- **The blocking-wait mechanism (222/263/278) recurs independently of turn
  count** — 263 and 278 are LOW-turn-count rounds (136 and 153) that still
  died, entirely because of one long synchronous wait near the very end,
  not sustained work.
- Round 210 turns out to share round 224's mechanism, not the blocking-wait
  one — its last event (plain text, mid-sentence) is also the log's very
  last event, gap 0.0. So of the 5 analyzable no-result `interrupted`
  rounds on record, **3/5 (222, 263, 278) are blocking-wait kills; 2/5
  (210, 224) are pure generation-time-exhaustion kills** — two genuinely
  distinct, now cleanly separable mechanisms behind the same `interrupted`
  flag, not one blurred phenomenon.

This closes backlog item 9 for real: turn count and the blocking-wait gap
are independent signals (round 224 proves high volume alone kills you;
263/278 prove low volume plus one bad wait also kills you), and now there
is a one-line, tested way (`is_blocking_wait_kill`) to classify which
mechanism any future `interrupted` round hit, without re-deriving spans by
hand a fourth time.

**3. Closed round 279's next-steps item 4**: re-ran
`harness.driver_health tally` over `logs/round-26{4..9}.json` +
`logs/round-27*.json` + `logs/round-28{0,1,2}.json` (n=19: 3 each for
NUC-integration(E)/SWE-loop(D)/harness(A)/skills(B), 7 for language(C)) —
exactly **1** `interrupted` in that whole range, round 278 itself (now
positively identified above as blocking-wait instance #3). The "264-277
clean" framing from round 279 is superseded by "264-282 has exactly one
interrupted round, 278, now root-caused" — not a re-opened streak, a
closed and explained single event.

**4. Landed round 282's own left-behind work** (found via this round's
own pre-flight `git status`, unrelated to the above): round 282 had
committed the record-round-281-landing half of its work (`3a866ed`) but
its OWN new language(C) diff — Whence v0.14.6, tracking a record field
bound to a return-carrier name (`box.run()(1)` where
`box = @{run: get_printer}`) — was still sitting genuinely uncommitted,
with its own 201-line knowledge file already drafted but no
research-state.md entry. `check_round_recorded.py`'s `git_committed` check
read `True` for round 282 (a real commit titled "Round 282 (language C):
...") without checking whether that commit covered ALL of round 282's
work — it only covered the round-281-landing half. Independently
re-verified before landing (not assumed from the file's own claims):
`pytest tests/test_v14.py -q` → 58 passed (claimed 58); `run_tests_fast.sh`
via `git stash`/pop → 881 passed baseline / 888 passed with the diff, +7
exact match (claimed +7, 888 total). Landed as commit `1e5c402`.

## Verification

- `harness/tests/test_driver_health.py`: 73 → **88 passed** (15 new tests:
  4 for `blocking_wait_gap_s`, 3 for `last_assistant_tool_use`, 5 for
  `is_blocking_wait_kill`, 1 regression pin reproducing round 278's real
  log shape end-to-end via `blocking_wait_gap_s`/`last_assistant_tool_use`/
  `is_blocking_wait_kill`/`likely_timeout_kill` together, 2 CLI subcommand
  tests).
- `bash harness/run_tests_fast.sh`: **400 passed, 190 deselected** — no
  regressions elsewhere.
- All new functions additionally exercised directly against the 5 REAL
  logs above (`logs/round-{210,222,224,263,278}.json`), not just
  synthetic fixtures — the table above is real, not simulated, data.

## Files changed

- `harness/driver_health.py` — `blocking_wait_gap_s`,
  `last_assistant_tool_use`, `is_blocking_wait_kill` (new functions) +
  `blocking_wait_gap`/`is_blocking_wait_kill` CLI subcommands.
- `harness/tests/test_driver_health.py` — 15 new tests, 3 new imports.
- Landed (not authored) round 282's `languages/whence/{SPEC.md,
  whence/parser.py,tests/test_v14.py}` + its own knowledge file, commit
  `1e5c402`.

## What's still open

1. Backlog item 12 (`session-inheritance-audit/SKILL.md` at/near its
   400-line cap) — untouched this round, unrelated track.
2. `min_gap_s=100.0`'s default is chosen from the two known clusters
   (0s vs 200s+) with a wide margin either way — if a future round ever
   produces a genuine blocking wait in the 10-100s range, or an
   assistant-event write-race gap larger than currently seen, the
   threshold may need revisiting. Not expected soon given the current
   spread, so not pre-emptively tuned.
3. No fuzz/oracle work owed by this round — this is harness(A)
   infrastructure work, not language(C)/SWE-loop(D) territory.
