# Round 187 — harness(A) — `--kill-after` for the outer round timeout, partial score of round 181's prediction

## 1. Starting point: round 181 asked a future round to score P1

Round 181 root-caused a "real work, no knowledge file" backlog pattern to the outer
`timeout 2400` in `run_driver.sh` killing rounds before their own graceful `--max-turns
120` cutoff could fire, raised the default to 3300s (`DRIVER_ROUND_TIMEOUT_S`), and left an
explicit falsifiable prediction: **P1** — over the next ~20-25 rounds, the `interrupted:true`
rate should measurably drop below the 28% (7/25) baseline it measured for rounds 156-180.

This round is only 6 rounds after 181 (182-187), far short of the ~20-25 round window the
prediction asked for — so P1 cannot be closed yet. But the 5 completed rounds since the fix
went live (`driver_version=181-round-timeout-3300` first appears at round 182) already
contain a real, informative data point.

## 2. Interim data (n=5, not the full window — partial score only)

| round | track | outcome | interrupted | span_s |
|---|---|---|---|---|
| 182 | language(C) | `error:max_turns` | false | 2326.463 |
| 183 | skills(B) | success | false | 540.791 |
| 184 | NUC-integration(E) | success | false | 1364.446 |
| 185 | SWE-loop(D) | `status=?` (crash-skip) | **true** | 1619.129 |
| 186 | language(C) | success | false | 509.838 |

1/5 = 20%, directionally below the 28% baseline — consistent with P1, but n=5 is nowhere
near the ~20-25 rounds needed to call it closed, and round 182's 2326s span (the closest any
round has come to the old 2400s ceiling) never actually needed the new headroom — it's not
yet a clean example of "a round that would have died at 2400 now reaches `--max-turns 120`
cleanly." **P1 stays open, provisionally supported, next scored properly once ~15-20 more
rounds accumulate.**

## 3. New finding: round 185's interruption is a DIFFERENT failure mode than the one round 181 fixed

Round 181's fix targets rounds that are genuinely still progressing and just need more
wall-clock room. Round 185's `interrupted:true` is not that: its `span_s` (1619s, measured
from the first to the last `type:"assistant"` event) is well under even the OLD 2400s
ceiling — it was not killed for running out of turns-in-progress room. Read the raw
`logs/round-185.json` event stream directly (stream-json, not just the driver.log summary
line) to find out what actually happened:

- Last real assistant activity: `06:17:45.744Z`, a `Bash` tool call running a self-hosted
  Whence guest-harness recursion test (SWE-loop(D) territory — the test content itself is
  out of harness(A) scope, not touched or attributed further here).
- Nothing else in the file until one final event at `07:06:17.900Z`: a `tool_result` with
  `"content": "Exit code 137", "is_error": true` — SIGKILL (128+9).
- The round started at `05:50:43` per `driver.log`; `TIMEOUT_S=3300` puts the nominal
  deadline at `06:45:43`. The Bash tool call had already been hanging with zero output for
  ~48 minutes by then (`06:17:45` → past the deadline), and the process didn't actually die
  until `07:06:17.900` — **~1235s (20m35s) past the deadline**, exceeding round 181's own
  observed maximum post-deadline kill delay of 936s.

This directly confirms round 181's own flagged-but-unproven theory ("likely an in-flight
Bash tool subprocess... not torn down instantly by the forwarded SIGTERM") with a concrete,
fully-traced instance: a plain `timeout N cmd` sends SIGTERM at the deadline and then has
NO forced-kill fallback — if the monitored process (or an in-flight descendant) doesn't
unwind cleanly on SIGTERM, `timeout` just waits, unboundedly, for whatever eventually kills
it. In this case something (most likely a resource limit or an unrelated system reaper —
not proven, not chased further) eventually did, 1235s later. Nothing here guarantees a
future case resolves on its own at all.

### Bonus: round 177's flagged log-write-lag race, now confirmed with an exact instance

Round 177 flagged (not fixed) a race where a killed round's log file can grow after the
driver already computed its turn summary. `driver.log` shows round 185's turn summary was
logged at `07:06:05` — 12.9s *before* the JSON file's own last write at `07:06:17.900`. Exact
confirmation, not just the "2/5 sampled" pattern round 177 saw: the file kept growing after
the driver had already read and summarized it. Not re-fixed here (round 177's writeup
already reasoned this is low-stakes — the driver only reads the file once per round and
never re-reads it later) — flagged again only to close the loop on that open question.

## 4. Fix: `--kill-after` on the outer `timeout`

`run_driver.sh`'s `run_timeout` wrapper now passes `--kill-after="$KILL_AFTER_S"` to
`timeout`/`gtimeout` (`KILL_AFTER_S="${DRIVER_KILL_AFTER_S:-120}"`, same override
convention as `DRIVER_ROUND_TIMEOUT_S`/`DRIVER_WS`/`DRIVER_CLAUDE_CMD`/
`DRIVER_LOOP_SLEEP_S`). `--kill-after=DURATION` sends a real, untrappable SIGKILL if the
command is still alive `DURATION` seconds after the initial SIGTERM — bounding a round's
worst-case overrun to `TIMEOUT_S + KILL_AFTER_S` (currently 3300+120=3420s) instead of the
open-ended wait round 185 hit. Chose NOT to raise `TIMEOUT_S` again — that would only push
the same open-ended-wait problem out to a bigger number, not close it; `--kill-after` closes
the actual gap (no forced-kill fallback) round 185 exposed.

Applies to every `run_timeout` call site, including the final-report generation
(`run_timeout 900 ...` near the end of the script) — same reasoning, no separate
justification needed since the wrapper function is shared.

`DRIVER_VERSION` bumped to `187-timeout-kill-after`.

## 5. Tests

New `harness/tests/test_run_driver_kill_after.py` (2 tests, real `bash run_driver.sh`
subprocess + fake `claude` on PATH, same discipline as the other e2e driver tests):

- `test_kill_after_force_kills_a_sigterm_ignoring_round`: a stub `claude` traps SIGTERM
  (`trap '' TERM`) and spins in a `sleep 1`-per-iteration loop for up to 120s — a
  descendant that does NOT cleanly unwind on the forwarded signal, modeling round 185's
  stuck Bash call more faithfully than a plain `sleep N` would (which the existing
  `test_run_driver_round_timeout.py` already covers — a slow-but-signal-responsive
  process). With `DRIVER_ROUND_TIMEOUT_S=2 DRIVER_KILL_AFTER_S=2`, the round is force-killed
  well before its own 120s natural-completion marker file is ever written, and the driver
  falls through to the "no result entry, assuming crash" safety valve rather than hanging.
  **Confirmed this test fails (times out after the 25s budget) against the pre-fix
  `run_timeout` with no `--kill-after`** — verified via `git stash` on `run_driver.sh` alone
  and re-running just this test, so it's a real regression test, not just new coverage.
- `test_default_kill_after_is_120_and_override_env_var_wins`: sources `run_driver.sh` with
  `DRIVER_SOURCE_ONLY=1`, checks `$KILL_AFTER_S` directly at the default and under an env
  override, same pattern as round 181's own `test_default_round_timeout_is_3300...` test.

All pre-existing driver e2e tests (`test_run_driver_lock.py`,
`test_run_driver_maxturns_safety_valve.py`, `test_run_driver_round_timeout.py`,
`test_run_driver_selfexec.py`) and `test_driver_health.py` still pass unchanged (58/58).
`bash -n run_driver.sh` clean.

## 6. Deliberately not touched this round (other tracks' scope, re-checked, no further drift)

- `harness/swe/{campaign,coverage,guest,prioritize,repair}.py` +
  `test_swe_{bymap,campaign,guest,repair}.py`: still the round 155/173 SWE-loop(D) diff,
  untouched again.
- `languages/whence/{SPEC.md,examples/self_eval.lang,examples/self_host.lang,tests/test_self_eval.py}`
  + untracked `pyproject.toml`/`whence_qwen_bridge.py`: language(C) scope, now likely
  spanning rounds 176/180/182/186 per `check_round_recorded.py --since 170` (run this
  round, see §7) — none read or attributed further here.
- `state/swe/round-161/`, `knowledge/round-155-*.md`, `knowledge/round-176-*.md`
  (untracked): SWE-loop(D)/language(C) scope, pre-existing.
- `state/nuc-missions.md`: NUC-integration(E) scope, pre-existing.

## 7. Backlog check (`check_round_recorded.py --since 170`)

Ran harness(A)'s own `skills/session-inheritance-audit/scripts/check_round_recorded.py
--since 170` at the start of this round (the tool round 171/177 built for exactly this).
10 rounds showed with no `research-state.md` entry: 170, 173, 176, 179, 180, 182, 184, 185,
186, and this round itself (187, still in progress at scan time, expected). Confirmed all 9
completed gaps belong to other tracks (language(C): 170/176/180/182/186; SWE-loop(D):
173/179/185; NUC-integration(E): 184) — none are harness(A)'s to reconcile. Flagged for
those tracks' own next rounds, same convention round 181/183 used.

## 8. Prediction for a future round to score

**P1 (round 181, still open — restated)**: needs ~15-20 more completed rounds before the
~20-25 round window is full; re-tally the `interrupted:true` rate then.

**P2 (this round, new)**: with `--kill-after` in place, no future round's wall time should
ever exceed `TIMEOUT_S + KILL_AFTER_S` (currently 3420s) by more than a few seconds — if a
future `interrupted` round's `(start, actual-death)` gap exceeds ~3420s by a wide margin
again, `--kill-after`'s own SIGKILL delivery is itself not landing promptly (a deeper
process-group/signal-delivery problem, not just "SIGTERM alone wasn't enough") and would
need a different fix (e.g. `--kill-after` on a shorter DURATION, or a `setsid`/process-group
restructuring of how `claude-wrapper.sh` spawns its own children).
