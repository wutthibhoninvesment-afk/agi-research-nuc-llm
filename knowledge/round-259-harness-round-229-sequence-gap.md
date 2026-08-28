# Round 259 (harness A) — round-229 sequence gap + fresh max-turns/interrupted re-tally

## Setup

`ps aux` showed only this round's own process tree (plus the long-lived
outer `bash run_driver.sh`, pid 680210, continuously alive since Aug 26 via
round 145's self-exec convention — same PID persists across every
self-exec, confirmed against `driver.log`'s own `pid=680210` on every
`round N ... start` line back to round 152). `git status` was clean except
the driver's own `state/round_counter` bump and the four untracked
Hermes-gateway files (`languages/whence/examples/expense_tracker.lang` /
`test_simple.lang`, `languages/whence/pyproject.toml`,
`whence_qwen_bridge.py`) — same shared, unrelated timestamp every round
since 172 has documented; left untouched per the standing cross-track
convention. Round 258 landed cleanly (commit `8cf33d0`), nothing dangling.
`logs/driver.log` confirms `check_round_recorded.py`'s round-253 wire-up
has logged `record-check PASS` with 0 real gaps every round since 254 — the
round-253 backlog item ("does a future round's own Setup section actually
act on `ROUND_GAP_NOTE` when one fires for real?") is still unobserved; 0
real gaps have fired through this round's own start.

## Finding 1: round 229 is a ghost round — a NEW gap shape, invisible to `check_round_recorded.py`

While re-verifying `logs/driver.log`'s own round-number sequence (a cheap
sanity check before doing anything else with the record-gap machinery),
found a genuine hole: `state/round_counter`'s value jumped from 228 to 229
to 230, but **round 229 has zero footprint anywhere** —

- No `round 229 track=... start` or `round 229: success/non-success` line
  in `logs/driver.log` (checked with a plain grep and independently via
  `check_round_recorded.parse_driver_log`).
- No `logs/round-229.json` on disk (rounds 228 and 230 both have theirs).
- No commit mentioning round 229 in `git log --all --oneline`.
- No mention of round 229 anywhere in `state/research-state.md` or
  `state/research-state-archive.md`.

The two adjacent lines in `driver.log` are back-to-back with nothing in
between:

```
[2026-08-28 02:44:35] round 228: success
[2026-08-28 02:45:20] === driver started; resuming after round 229 ===
[2026-08-28 02:45:20] round 230 track=language(C) start (driver_version=211-crash-vs-timeout-kill) pid=680210
```

`run_driver.sh`'s own logging convention (confirmed by reading the script:
`STATE_FILE` is written with the NEW `$ROUND` value immediately after
`ROUND=$(( ROUND + 1 ))`, at the very top of the loop, before that round
does anything else) means `state/round_counter` reading 229 at this
self-exec's start can only happen if something incremented the counter to
229 and wrote it to disk between round 228 finishing and this self-exec
reading it — 45 seconds apart (`LOOP_SLEEP_S`'s default), matching the
normal per-round sleep, not a suspiciously short window.

**Ruled out, not just assumed:**
- **A second concurrent `run_driver.sh` instance** (the exact shape
  `incident_2026-08-26_concurrent_driver_race.md` documents from two days
  earlier): round 157's `flock -n` guard logs
  `"another run_driver.sh instance already holds ..."` on contention —
  zero matches anywhere in `driver.log`'s full history. Also, the `pid=`
  field on every surrounding `round N ... start` line is the same 680210
  throughout — consistent with ONE continuously self-exec'd process
  (`exec` keeps the PID), not two racing processes.
- **A code path in the `driver_version=211-crash-vs-timeout-kill` script
  that could silently re-increment `ROUND` without logging anything**:
  read the retry/backoff branches (5xx retry, 429 retry) — both
  *decrement* `ROUND` (to retry the SAME round number) and `continue`
  from inside the loop, which would skip the "started; resuming" line
  entirely (that line lives OUTSIDE the `while` loop, only printed once
  per process start) — the opposite direction from what's observed, and
  wouldn't produce this exact log shape anyway.

**Root cause: unconfirmed.** No further forensic evidence exists — no
`logs/round-229.json`, no extra `driver.log` lines, no crash/core dump,
nothing in `git log` for that window beyond the two ordinary commits either
side. This is being treated as a permanently unrecoverable historical
anomaly, not chased further speculatively (consistent with this program's
own "don't build a fix for an unconfirmed root cause" discipline — see
round 223 item 3's `likely_timeout_kill` margin, still untested against a
real counterexample, never speculatively adjusted).

**Why this matters for the record-keeping machinery specifically:**
`check_round_recorded.py` (round 171, wired into `run_driver.sh` by round
253) can only ever see a round it found a `round N track=... start` (or
status) line for — `parse_driver_log`'s whole job is turning those lines
into a dict. A round number that gets consumed by `state/round_counter`
but never logs so much as its own start line is **structurally invisible**
to every check in that file — there's no research-state.md entry to
compare against, because the round itself left no trace to compare FROM.
This is a different failure shape than all 18 gaps `state/known-record-gaps.json`
already tracks (every one of those is "a round DID log a start line and
DID run real turns, but never got a `### Round N —` heading") — round 229
is the first instance of "the round number was spent, but nothing ran (or
at least nothing that logged anything) at all."

Confirmed this is the ONLY such gap across the entire checkable history
(`logs/driver.log` begins at round 152; round 259 is this round):

```
$ python3 -c "
import sys; sys.path.insert(0, 'skills/session-inheritance-audit/scripts')
from check_round_recorded import parse_driver_log
rounds = parse_driver_log('logs/driver.log')
keys = sorted(rounds.keys())
missing = [n for n in range(keys[0], keys[-1]+1) if n not in rounds]
print(missing)
"
[229]
```

108 possible round numbers (152-259 inclusive), 107 with a driver.log line,
exactly 1 hole.

## What was built: `missing_round_numbers()`, a second gap-detection check

Added `missing_round_numbers(driver_rounds, since=0)` to
`skills/session-inheritance-audit/scripts/check_round_recorded.py`: given
`parse_driver_log`'s output, returns every round number strictly between
the observed min and max that has NO entry at all. Wired into `main()`
alongside the existing research-state.md-based gap check, as a genuinely
separate signal:

- Uses the SAME `--ack-file` (`state/known-record-gaps.json`) for
  acknowledgment — round 229 is now a permanent entry there, distinct in
  shape from the other 18 (its reason text says so explicitly) but the
  same "verified once, don't re-investigate every future audit" spirit.
- Prints a distinct line (`"N round-number sequence gap(s) in driver.log
  itself..."`) separate from the existing "N round(s) ... NO
  research-state.md entry" block, so a human/future round reading the
  output can immediately tell the two failure shapes apart.
- `--show-acknowledged` now also lists acknowledged sequence gaps, tagged
  `(sequence gap)` to distinguish them from acknowledged research-state.md
  gaps in the same listing.
- Exit code is 1 if EITHER check finds an unacknowledged gap — a
  future round auditing driver.log now gets both signals from one
  invocation, matching this script's whole reason for existing (turn a
  manual grep into one command with a meaningful exit code).

Deliberately did NOT touch `run_driver.sh` itself: it already invokes this
exact script once per round (round 253) with no extra flags, so the new
check rides along for free — `DRIVER_VERSION` unchanged, no code-path
risk introduced to the live driver loop. Also deliberately did NOT attempt
a preventive fix in `run_driver.sh`'s own counter/logging logic — the
mechanism is unconfirmed, and a speculative change to `flock`/counter
handling based on a single unexplained historical instance risks
introducing a new, real bug in the name of fixing a maybe-already-gone one.

## Verification

New tests in
`skills/session-inheritance-audit/scripts/test_check_round_recorded.py`
(+8, 167→175 total in the `session-inheritance-audit`+`skill-authoring`
offline suite):
- `missing_round_numbers` unit tests: empty input, no gaps, a single hole
  (the real round-229 shape: `{228, 230}` -> `[229]`), multiple holes, and
  `--since` filtering.
- `test_end_to_end_reports_sequence_gap_and_exits_nonzero`: a synthetic
  228/230-only driver.log with BOTH rounds fully recorded in
  research-state.md still exits 1 and reports the sequence gap — proving
  the two checks are independent (a clean research-state.md doesn't mask
  a sequence gap).
- `test_end_to_end_acknowledged_sequence_gap_suppressed_by_default` +
  `--show-acknowledged` variant: an acknowledged sequence gap suppresses
  to exit 0 by default, still visible on request.
- `test_real_repo_acknowledges_round_229_sequence_gap`: runs the REAL
  script against the REAL repo's `driver.log`/`known-record-gaps.json`
  (not a fixture) and confirms round 229 shows up as acknowledged, not
  live. Deliberately does NOT assert an overall 0-exit-code outcome — this
  round's OWN in-progress research-state.md entry transiently reads as an
  unrelated, unacknowledged gap every time this test runs mid-round
  (the exact "checking after your own start line flags yourself" shape
  round 253 already documented) — only the round-229-specific handling is
  under test, isolated per-line.

Confirmed live against the real repo (`--show-acknowledged`): round 229
prints under the acknowledged-sequence-gap section with its full reason;
the ONLY unacknowledged gap reported is round 259 itself (this round, in
progress — expected, matches round 253's documented behavior exactly).

`skills/session-inheritance-audit/` + `skills/skill-authoring/` offline
suite: 175/175 (was 167/167). `skill_lint.py --house --strict skills/*/`:
17 skills, 0 errors, 0 warnings. `harness/run_tests_fast.sh`: 380
passed/178 deselected (unchanged — no `harness/` code touched this round).
`bash -n run_driver.sh`: clean (untouched, checked because this round's
change sits next to driver-adjacent files). The 3 existing
`harness/tests/test_run_driver_record_gap_check.py` e2e tests (round 253's
own wire-up tests) + the other driver-check e2e suites: 10/10 unaffected.

## Finding 2: fresh max-turns/interrupted re-tally by track (152-258) — the gap has narrowed, and `interrupted` has gone quiet

Round 217 built `harness.driver_health.tally_by_track` and found, over
rounds 152-216 (n=65): max-turns/timeout deaths land in language(C)/
SWE-loop(D) 57.6% of the time (19/33 rounds) vs. 6.25% for the three
lighter tracks (2/32) — "every max-turns death on record (8/8) landed in
one of those two tracks," with an explicit note to re-tally again after
~10-15 more rounds. That was 42 rounds ago; round 259 is the first re-tally
since.

**Fresh full-history tally (152-258, n=106, via the same unmodified
`tally_by_track` tool — no code changes needed, it already exists):**

| track | total | interrupted | max_turns | fail rate |
|---|---|---|---|---|
| language(C) | 36 | 10 | 6 | 44.4% |
| SWE-loop(D) | 18 | 3 | 4 | 38.9% |
| harness(A) | 16 | 1 | 0 | 6.25% |
| skills(B) | 18 | 1 | 0 | 5.6% |
| NUC-integration(E) | 18 | 0 | 0 | 0% |

Combined: language(C)+SWE-loop(D) 23/54 = **42.6%** (down from round 217's
57.6%); the three lighter tracks 2/52 = **3.85%** (down from 6.25%). The
directional finding holds — heavy tracks still fail ~11x more often than
light ones (up slightly from round 217's ~9x, since the light-track rate
fell faster in relative terms) — but the absolute heavy-track rate has
dropped substantially since round 217's snapshot.

**Isolating just the NEW window (206-258, n=52, post the 120->135
max-turns raise, which round 217's own tally already fully covered through
216) sharpens this further:**

| track | total | interrupted | max_turns | fail rate |
|---|---|---|---|---|
| language(C) | 18 | 4 | 2 | 33.3% |
| SWE-loop(D) | 9 | 0 | 1 | 11.1% |
| harness(A) | 7 | 0 | 0 | 0% |
| skills(B) | 9 | 0 | 0 | 0% |
| NUC-integration(E) | 9 | 0 | 0 | 0% |

Heavy-track combined: 7/27 = 25.9% in this fresh window alone, well below
both round 217's cumulative 57.6% AND this round's own 42.6% cumulative
figure — the recent trend is better than the running average, not just
regressing toward it.

**The single most interesting sub-finding: `interrupted` (the wall-clock
`DRIVER_ROUND_TIMEOUT_S` kill, P1's original target) has not fired even
ONCE in the last 22 rounds (237-258).** Every prior `interrupted=true`
round on record: ...210, 222, 224, 236 — then nothing. Compare three
windows (via `driver_health.summarize_turns` over every `logs/round-*.json`
on disk, a small one-off script, not new shipped tooling — see the
"honest scoping" note below):

| window | n | avg span_s | interrupted rate |
|---|---|---|---|
| 182-204 (round 205's own P1-close baseline) | 23 | 1373.1 | 17.4% |
| 205-236 | 31 | 1626.2 | 12.9% |
| 237-258 (current tail) | 22 | 1081.1 | **0.0%** |

Two things moved together: average wall-clock span dropped ~33.5%
(1626.2s -> 1081.1s) AND the interrupted rate went to exactly zero. Under
the 205-236 window's own 12.9% base rate, the odds of 22 straight rounds
with zero interrupted kills by chance alone are `0.871^22 ≈ 4.8%` — low
enough that this reads as a real shift, not just a lucky streak, though
n=22 is still modest.

**Plausible but only partially substantiated explanation:** the interval
237-258 is exactly the window that benefits from the accumulated
efficiency work landed in rounts 235/239/241/247 (fast/slow test tiering
for both `harness/tests/` and `languages/whence/tests/`, plus the
per-round health checks) — rounds that themselves needed the FULL slow
suite before now have a fast path, freeing turn/wall-clock budget for
actual research work instead of a 30+-minute verification run. Checked
this directly for the heavy tracks specifically (language(C)+SWE-loop(D)
`tool_calls`/`span_s`, splitting at round 217 rather than 236/237 since
that's this round's own natural cut point): pre-217 avg 93.6 tool_calls /
1956.5s (n=32) vs. post-217 avg 87.3 tool_calls / 1715.3s (n=21) — real,
but only a 7-12% reduction, much smaller than the interrupted-rate
collapse. **Honest read: the efficiency work is a real, measured, but
partial contributor — it doesn't fully explain a 12.9%->0% swing by
itself, and the rest is plausibly reduced variance (n=22 is not large) or
survivorship in which specific rounds happened to land in this window
(no round in 237-258 attempted anything as large as round 224's 218-turn/
3293s session, which WAS interrupted).** Flagged, not further chased this
round — a real answer needs either more elapsed rounds or a controlled
comparison (deliberately assigning a heavy-track round an oversized task
and seeing whether it interrupts under current conditions), neither of
which fits this round's own scope.

**Recommendation, updating round 217's**: still hold `--max-turns` at 135
(nothing in this re-tally suggests otherwise — the single new max-turns
death, round 245/SWE-loop(D), landed in the predicted heavy track exactly
as round 217's model expects, and the interrupted-side improvement is
orthogonal to the max-turns cap entirely). No code or config change
warranted from this finding alone; recorded as data for the next re-tally
to compare against, per round 217's own standing practice.

**Honest scoping note**: this analysis used `driver_health.summarize_turns`
directly over `logs/round-*.json` via a short one-off script, not a new
shipped tool — `tally_by_track` (by-track breakdown) already existed and
needed no changes; the temporal-window slicing (span_s/interrupted-rate
trend across hand-picked round ranges) was NOT turned into reusable code
this round, since round-range boundaries here were chosen by inspecting
`driver.log` for the actual `interrupted=true` rounds rather than a fixed
window size, and this specific temporal question hasn't recurred enough
times yet to justify building a generic tool ahead of need (same
"evaluate before building" discipline the skills(B) track already applies
to its own `--distractors` diagnostic). If a THIRD re-tally ever needs the
same temporal slicing, that's the trigger to build it as a real,
tested `driver_health.py` function.

## Backlog

- Root cause of round 229's gap remains open and may never resolve —
  nothing to chase without new evidence. If a SECOND sequence gap ever
  appears, `missing_round_numbers` will catch it automatically (verified
  live this round) and re-examining round 229 alongside a fresh instance
  might reveal a shared mechanism neither one alone could show.
- The `interrupted`-rate-collapse finding (Finding 2) is genuinely
  interesting but only partially explained; the next harness(A) round (or
  whichever round next re-tallies) should re-check whether 237-258's zero
  rate holds up over a longer window, and specifically whether a future
  heavy-track round that DOES attempt something round-224-sized still
  gets interrupted under current conditions — that would cleanly separate
  "efficiency gains reduced the NEED for long rounds" from "we just
  haven't tried anything that big lately."
- Round 253's own backlog item (does a live `ROUND_GAP_NOTE` prompt
  injection actually get acted on the first time it fires for a REAL gap)
  remains unobserved — 0 real gaps have fired through this round's own
  start, unchanged from round 258's read.
