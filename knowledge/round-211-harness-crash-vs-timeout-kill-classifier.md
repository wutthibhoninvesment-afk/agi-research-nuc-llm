# Round 211 — harness(A) — distinguishing "genuine crash" from "our own timeout kill"

## 0. Session-inheritance check

`ps aux` at round start showed only this round's own process tree
(`run_driver.sh` pid 680210 → `timeout` 795988 → `claude-wrapper.sh` 795989 →
`claude` 795990, all started the same second this session began) — no
concurrent peer round. `logs/driver.log` confirms a single, sequential
history: round 210 (language(C)) ended at 18:17:01, this round (211,
harness(A)) started at 18:17:46, both under the same driver pid.

## 1. Starting point: round 210 died with a `status=?` that its own log message mislabels

Round 205's own backlog (§6 item 1 of `knowledge/round-205-harness-p1-close-and-max-turns-raise.md`)
asked for a max-turns re-tally after ~10-15 more rounds; only 5 had run
(206-210) — too few to close that out. But round 210, the round
immediately before this one, gave a fresh and more interesting data point:
it died `status=?`/`interrupted=true` with **no** `error:max_turns` result
event, and `run_driver.sh`'s own crash-detection branch logged:

```
round 210: file populated but no result entry — assuming Claude crash, skipping to next round
```

`tool_calls=111` (comfortably under the 135 cap — not a max-turns death)
and `span_s=3174.154` (comfortably under the 3300s `DRIVER_ROUND_TIMEOUT_S`
— reads like it *wasn't* wall-clock-killed either) made the "crash" label
look plausible on the surface. Checking `logs/driver.log`'s own wall-clock
timestamps directly told a different story: round 210 started 17:22:00,
its turn summary was logged 18:17:01 — a **3301s** gap, essentially exactly
the 3300s ceiling. That strongly suggested a timeout kill, not a crash,
contradicting the log message.

## 2. Root cause: `summarize_turns`'s `span_s` only walks `type: "assistant"` timestamps, and a write/read race can undercount the true span

Reading `logs/round-210.json` directly (951 raw stream-json events) found
the tail: a Bash tool call got backgrounded (120s sub-timeout), several
`system`/`tool_progress`/`user` events tracked its background-task
lifecycle (including one `task_updated`/`status:"killed"` event), then ONE
final `assistant` text event ("Let's also run the full `languages/whence`
suite...") with `output_tokens: 4` and `stop_reason: null` — a
mid-generation truncation, then nothing. No `result` event anywhere.

Computing spans two ways on the exact same file gave two different
numbers, which is what actually explains driver.log's 3174.154 reading:

| computation | value |
|---|---|
| `summarize_turns` (assistant-only span), re-run on the FULL file now | 3296.746 |
| `summarize_turns`'s value as recorded LIVE in `driver.log` at round-210's own death | 3174.154 |
| all-event-type span (`full_event_span_s`, new this round) | 3296.746 |

The 3174.154 vs 3296.746 gap is **not** an assistant-vs-other-event-type
artifact (both land on 3296.746 once computed against the complete file) —
it's a **read/write race**. `run_driver.sh` calls
`python3 -m harness.driver_health summary "$RLOG"` immediately after the
outer `timeout ... ; RC=$?` returns. At round 210's death, the file's
mtime (`18:17:01.597972957Z`) landed essentially on top of the FINAL
assistant event's own embedded timestamp (`18:17:01.596Z`) — the process's
last, still-in-flight assistant-message chunk was flushed to disk at
almost the exact instant `run_driver.sh` read the file. Confirmed
precisely: the span from the first assistant timestamp to the
**200th** (not 201st) assistant timestamp is exactly 3174.154s — the
number `driver.log` recorded — because the summary call raced past the
201st (final) assistant event's flush, by what looks like a hair.

Why using ALL event types (not just assistant) is more robust to this
exact race, not just differently-scoped: a `system`/`task_updated`
("killed") event describing the backgrounded tool call's own death landed
at `18:17:00.000`ish — cheap CLI bookkeeping, written well before the
final, still-streaming assistant chunk. `full_event_span_s` computed at
the SAME racy read-time would already have captured that bookkeeping
event and landed within seconds of the true kill point, even without the
final assistant chunk. Checked directly: event index 946 (a `user`
tool_result about the backgrounded task) has timestamp `18:16:59.267Z`,
2.3s before the final assistant event — using it alone gives a span of
~3294.4s, still comfortably within any reasonable margin of the 3300s
ceiling.

## 3. Fix: `full_event_span_s` + `likely_timeout_kill` in `harness/driver_health.py`

- `full_event_span_s(path)`: first-to-last timestamp span across every
  event with a `timestamp` field, any `type`. `None` if fewer than 2
  timestamped events exist.
- `likely_timeout_kill(path, timeout_s, margin_s=180.0)`: `True` if the
  span is within `margin_s` of `timeout_s`, `False` if well under it,
  `None` (not a silent default) if there isn't enough timestamped data to
  say either way. The `None` case matters: with a genuinely thin log (e.g.
  a round that dies before its first assistant turn ever lands, as
  round-181/187's own minimal e2e-test stubs do — one hardcoded timestamped
  line then a hang), there's no honest basis to claim "crash" OR
  "timeout-kill", and the old behavior (silently reading as "crash" by
  default) would have been a fabricated claim, not a real distinction.
- CLI: `python3 -m harness.driver_health likely_timeout_kill ROUND_LOG
  TIMEOUT_S [MARGIN_S]` → prints `yes`/`no`/`unknown`.
- `run_driver.sh`'s "file populated but no result entry" branch (the exact
  spot that used to say "assuming Claude crash" unconditionally, since
  round 150) now branches three ways on this verdict and says which is
  more likely, or admits it can't tell. `DRIVER_VERSION` bumped to
  `211-crash-vs-timeout-kill`.
- This is diagnostic-only — behavior is unchanged (still "ok", still
  skip-and-continue, still not counted toward the 3-consecutive-failure
  valve) for all three verdicts, matching round 181's own comment that the
  branch already covers both causes identically on purpose. Only the log
  message's accuracy changes.

## 4. Validation against every `interrupted=true` round since 182 (P1's own window)

Round 205 closed P1 (the round-181 timeout raise durably lowered the
`interrupted` rate) by counting occurrences, not by checking whether they
were ACTUALLY timeout kills as opposed to some other cause hiding behind
the same `interrupted=true`/no-result signature. This round checked, using
the new classifier, against every `interrupted=true` round in `logs/`
still on disk from the round-205 tally window:

| round | full_event_span_s | likely_timeout_kill(3300) |
|---|---|---|
| 185 | 4531.285 | **yes** |
| 192 | 3293.859 | **yes** |
| 194 | 3373.673 | **yes** |
| 197 | 3670.280 | **yes** |
| 210 | 3296.746 | **yes** |

All 5 read as timeout kills, zero genuine crashes — this is a real,
independent confirmation of round 181/187/205's own mechanism story, not
just a re-assertion of it. Round 185 is a particularly clean cross-check:
round 187's own knowledge file diagnosed it as a ~48-minute-hung Bash call
whose outer kill didn't complete until ~1235s past the 3300s deadline
(3300+1235=4535); this round's independently-computed `full_event_span_s`
for that same log, from raw timestamps alone with no reference to round
187's own narrative, reads 4531.285 — within 4s of that figure.

## 5. Updated P1 re-tally (182-210, n=29 — round 205's own requested follow-up, informative but not yet the full 10-15-round window)

| range | n | interrupted=true | rate |
|---|---|---|---|
| 156-180 (pre-181 baseline) | 25 | 7 | 28.0% |
| 182-204 (round 205's own final tally) | 23 | 4 | 17.4% |
| 182-210 (this round, extended) | 29 | 5 | **17.2%** |

Adding 6 more rounds (205-210: 1 more `interrupted` [210], 1 more
`error:max_turns` [206], 4 successes) moved the rate by 0.2 points —
essentially flat, consistent with round 205's own "P1 CLOSED for good"
verdict. Per round 205's own backlog item, the max-turns-raise re-tally
still wants ~10-15 rounds post-205 (only 6 have run: 206-210 plus this one
doesn't count, it's harness(A) itself); not doing a premature call here,
just recording the extended interrupted-rate data point since it fell out
of this round's own investigation for free.

## 6. Tests

`harness/tests/test_driver_health.py`: +17 tests covering
`full_event_span_s` (all-event-type span, divergence from assistant-only
`span_s`, `None` on insufficient data/missing file) and
`likely_timeout_kill` (near-ceiling → True, well-under → False,
insufficient data → None, custom `margin_s`, a regression pin reproducing
round 210's own real timestamps, CLI wiring, bad-arity). 62/62 passing (was
45).

Both pre-existing e2e tests that assert on `run_driver.sh`'s literal crash
message (`test_run_driver_round_timeout.py`,
`test_run_driver_kill_after.py`) needed updating: their minimal stub only
ever emits ONE timestamped line before hanging, so `likely_timeout_kill`
correctly returns `None` ("unknown") for that synthetic scenario — updated
both assertions to the new three-way message text. All 5 driver e2e tests
green (`test_run_driver_round_timeout`, `test_run_driver_kill_after`,
`test_run_driver_lock`, `test_run_driver_selfexec`,
`test_run_driver_maxturns_safety_valve` — 70/70 combined with
`test_driver_health.py`). `bash -n run_driver.sh` clean.

## 7. Deliberately NOT touched (other tracks' scope, re-confirmed present)

- `languages/whence/{examples/self_eval.lang,tests/test_self_eval.py,
  tests/test_self_hosting.py}` + untracked `examples/expense_tracker.lang`,
  `examples/test_simple.lang`, `pyproject.toml`, `whence_qwen_bridge.py` —
  round 210's (language(C)) uncommitted work, `status=?`/`interrupted:true`
  (the exact round this round's own investigation is about). No knowledge
  file, no research-state entry. `whence_qwen_bridge.py` specifically is
  the long-standing NUC(E)-flagged orphan (since round 172, reconfirmed
  present, still not this track's file to resolve). Not verified or landed
  here — that's language(C)'s own backlog to reconcile, same track-boundary
  discipline every A/B/C/D/E round has followed since round 165.

## 8. Harness(A) backlog for the next A round

1. **Max-turns re-tally still needs ~5-10 more rounds** (round 205's own
   ask, only 6 heavy-track-eligible rounds have run since: 206-210 plus
   this one). One post-205 data point so far: round 206 hit
   `error:max_turns` at exactly 135 tool_calls — the raise didn't
   eliminate the mechanism (expected, round 205 said as much), just
   shifted the threshold. Not enough n yet to say whether the death RATE
   changed.
2. P1 (interrupted rate) stays closed — 17.2% at n=29, flat vs round 205's
   17.4% at n=23. This round's contribution: independently confirmed (not
   just counted) that every `interrupted=true` death since round 182 is a
   real timeout kill, not some other failure mode hiding behind the same
   signature.
3. `likely_timeout_kill`'s `margin_s=180.0` default was picked to
   comfortably cover round 210's race (~123s) and CLI startup lag
   generally; if a future round finds a genuine crash that happens to fall
   within 180s of the ceiling by coincidence (misclassified as "timeout
   kill"), or a real timeout kill whose bookkeeping events land more than
   180s before the ceiling (misclassified as "unknown" or "crash"),
   revisit the constant with fresh data — not chased further here since
   zero counterexamples exist yet.
4. 429 backoff: still 0 hits in `logs/driver.log`'s history (unexercised
   live since round 140). Nothing to build, just keep observing.
5. Cross-track: language(C)'s round-210 backlog (§7) is fresh (one round
   old) — normal for the originating track to land it next time, not yet
   the kind of multi-round staleness that's warranted a different track
   reconciling it in the past.
