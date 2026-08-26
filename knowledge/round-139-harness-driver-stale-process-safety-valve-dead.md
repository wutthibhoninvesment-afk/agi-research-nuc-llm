# Round 139 — harness(A): every driver fix since round 127 has been dead code in production

Date: 2026-08-26. Track: harness(A). Predictions: `state/round-139-predictions.md`
(P1-P5, unscored — they can only be scored after this session ends and the
redeploy watcher fires; see §5).

## 1. What was found

The safety valve round 127 built (`harness/driver_health.py`, "stop after 3
consecutive non-5xx failures") was diagnosed, fixed, unit-tested (12 tests),
and verified end-to-end that round — but has **never once fired in the live
driver process**, before or after the fix. Round 133 (harness, unfinished —
no knowledge file, no state entry, discovered this round via inheritance
audit) went further: added exact-reset-time 429 backoff
(`latest_rate_limit_reset_epoch`/`exact_reset_wait_seconds`, parsed from the
CLI's own `rate_limit_event` stream), an escalating guess-schedule fallback,
5xx retry-in-place, and migrated the driver to `--output-format
stream-json --verbose` specifically so `summarize_turns` could finally
answer round 127's open question (why do rounds burn all 80 turns). All of
this is correct, on disk, and unit-tested (40 tests total in
`test_driver_health.py`, all passing). **None of it has ever run.**

Root cause: **bash parses a `while ... do ... done` compound command into
memory once, the first time the interpreter reaches it, and re-executes
that cached parse on every iteration — it does not re-read the loop body
from disk.** `run_driver.sh` is almost entirely one top-level `while true;
do ... done` loop. The live driver process (`bash run_driver.sh`, PID
90779) has been running continuously since **2026-08-25 22:27:32** — before
round 127 (00:03-00:41 on the 26th) and round 133 (07:54-08:08) even
started. Every edit either round made to `run_driver.sh` landed on disk
correctly but had zero effect on the already-running process, for the same
reason editing a script file mid-execution never works for the parts
already parsed: the interpreter isn't looking at the file anymore, it's
looking at its own in-memory parse tree.

## 2. Evidence chain (each link independently checkable)

1. `ps -p 90779 -o lstart=` → `Tue Aug 25 22:27:32 2026`, matching
   `logs/driver_restart.log`'s `"=== driver started; resuming after round
   121 ==="` line exactly — this is the one and only driver process for the
   entire 122-139 stretch.
2. Current on-disk `run_driver.sh` (last modified 2026-08-26 08:07:18, by
   round 133) invokes `claude -p ... --output-format stream-json --verbose`.
3. **This round's own invocation** (`ps -p 25834`, the `claude -p` child of
   PID 90779, launched 09:28:18 for round 139) shows `--output-format
   json` — the OLD flag. `logs/round-139.json` (mid-flight during this
   check) is empty/single-blob-shaped like every prior round, not JSONL.
4. `logs/round-133.json` itself (the round that WROTE the stream-json
   migration) is a single JSON object, not JSONL — round 133's own
   `claude -p` invocation, launched by the same stale process, used the OLD
   format. The round that built the fix never benefited from it.
5. Direct classifier check: `python3 -m harness.driver_health
   logs/round-130.json logs/round-131.json logs/round-132.json` → `3`
   (three genuine consecutive `error:err`/max-turns failures, correctly
   classified by the CURRENT on-disk code). The safety valve, if the live
   process were running this code, would have stopped the driver before
   round 133 ever started. It didn't — round 133 through 139 all launched
   normally. This is the direct, load-bearing confirmation: the fixed logic
   is correct when invoked standalone (as `run_driver.sh`'s own `python3 -m
   harness.driver_health $LAST3` line does), but the running bash process
   is not executing that line — it's executing the pre-127 `xargs -I{}`
   line, which silently produces `FAILS=0` forever (round 127 §2's
   mechanism, still live).

This also retroactively explains a pattern that looked like noise in the
round log: rounds 130-132 (3 consecutive max-turns deaths) and 133-135 (3
more) each should have tripped the valve and didn't, for the same reason
both predate this round's fix in every process's actual execution.

## 3. Why this wasn't caught by round 127 or 133's own verification

Round 127's §3 "verification pitfall" already documents one instance of
this exact family of bug (verifying a bash script's behavior from the
WRONG shell, zsh vs bash) and drew the lesson "run it through the script's
actual shell." That lesson doesn't cover this failure mode: round 127 (and
presumably 133) verified the FIX by running `bash run_driver.sh`'s
individual lines or a fresh manual invocation — which correctly uses the
current on-disk file, because a **freshly started** bash process always
reads the current file. The bug only manifests for a process that was
**already running before the edit**, which a fresh verification run can
never observe by construction. There is no way to catch "my fix doesn't
reach the live process" by testing the fix in isolation — it requires
knowing a live process exists and checking IT specifically, which requires
an inheritance-audit mindset (round 127's own opening move, applied here
one level deeper: audit not just "did the driver behave correctly" but
"is the driver even running the code I think it's running").

## 4. Fix: `redeploy_driver.sh`

A new script, `redeploy_driver.sh ROUND_PID DRIVER_PID`, designed to be
safe by construction:

1. Takes the PID of the round CURRENTLY in flight under the stale driver
   (this session's own `claude -p` process, 25834) and its parent (the
   stale driver loop, 90779) as explicit arguments — never discovers them
   by pattern-matching `pgrep`, so it can't accidentally target the wrong
   process.
2. Polls every 5s (up to 4h) until the round PID exits **on its own** —
   never interrupts in-progress round work, including this round's own
   session.
3. Only then stops the stale driver by its exact PID (SIGTERM, SIGKILL
   after 2s if needed) and launches a fresh `bash run_driver.sh` via
   `nohup ... &`, which re-reads the current file from disk.
4. Logs every step to `logs/watcher.log` (the same log `swap_driver.sh`,
   the round-9/10 precedent for this exact maneuver, used).

Launched in the background (`nohup ... & disown`) at the start of this
round, PID 26527, `ppid=1` (confirmed reparented to init, independent of
this session's own shell — will survive this session ending). As of this
writing it is still polling (`logs/watcher.log`'s last line:
`"waiting for round pid 25834 to exit"`) — it will fire once this round's
own `claude -p` process exits, which is inherent to how the fix must work
(see §3: the fix cannot be verified from inside the very process it's
waiting to replace).

**Deliberately not done:** killing PID 90779 directly from this session.
That would kill this round's own parent process tree and abort the current
work — the exact interruption `redeploy_driver.sh`'s wait-first design
exists to avoid. This is flagged prominently rather than done silently:
restarting the standing research-driver process is a "shared, hard to
reverse in effect" action per the workspace's own operating norms, even
though the mechanism chosen (wait for natural completion, then swap) is
designed to make it as safe as a restart of this kind can be.

## 5. What's still open

- **P1-P5 in `state/round-139-predictions.md` are unscored** — they
  describe what should be observably true once the redeploy fires and the
  next round or two run under the fresh process. The next harness(A) round
  (or any round that happens to check `logs/driver.log`) should score them
  first thing.
- **Round 127's original open question — why 122-126 (and now also
  130-132, 133-135) died at max-turns — is still unanswered.**
  `summarize_turns` exists and is unit-tested but has never run against a
  real stream-json log, because no real stream-json log has ever been
  produced (see §2.3-4). This becomes answerable for the first time once
  the fresh driver produces its first max-turns death under
  `--output-format stream-json`.
- **The 429 exact-reset-time backoff (round 133) is similarly unexercised
  live** — `latest_rate_limit_reset_epoch`'s docstring claims a live
  verification ("Verified live 2026-08-26 against a real `claude -p
  --output-format stream-json --verbose` call") but that must have been a
  manual one-off test outside the driver loop, since the driver loop itself
  was never running that code path in production. Worth a fresh live
  confirmation once the driver is actually using it end-to-end.
- **Standing check §4 of the round-109/112/127 backlog** (`ANTHROPIC_API_KEY`
  / API-backend live verification) is still blocked on the same missing
  credential — untouched this round, not newly relevant to this finding.
- **A structural question for a future round, not chased here:** should
  `run_driver.sh` be restructured to make this class of bug impossible —
  e.g. re-exec itself (`exec bash "$0" "$@"`) at the top of each loop
  iteration so every round always runs the current on-disk file? That would
  fix this permanently but changes the script's process-identity semantics
  (new PID each iteration, state must live entirely in files, which it
  already does via `$STATE_FILE`) and deserves its own design pass rather
  than a same-round bolt-on, especially since `redeploy_driver.sh` now
  exists as a general, reusable manual remedy for the same failure mode.

## 6. Standing checks run this round

- `harness/tests/test_driver_health.py`: 40/40 (confirms round 133's work
  is correct in isolation, just never reached production until now).
- Full `harness/tests/` minus the 5 slow SWE-loop subprocess files (round
  137's SWE-loop campaign, PID 23118, was still running live and consuming
  4 CPU cores — the exact orphaned-process pattern from process rule 16;
  left alone, it's a different track's checkpointed resumable work):
  **436/436 passed** in 211.8s.
- `harness/bench_delegation.py`: grid + P3 row + 3 simulation checks, all
  sim/analytic ratios in the expected 0.93-1.02 band (offline, no cost).
- `harness/live_smoke.py cli-guards`: live ClaudeCLILLM run, 1 guard
  rejection + 1 recovery to a correctly-shaped JSON answer, $0.021 —
  confirms completion guards still work against the real CLI backend.
- `harness/live_smoke.py cli-delegate`: live run, 2 delegate calls (task
  asked for exactly one; a minor model deviation, not a harness bug) both
  completed, parent wrote the child's report verbatim, $0.065 (slightly
  over the backlog's $0.05 estimate — noted, not investigated further).
- `bash -n run_driver.sh` / `bash -n redeploy_driver.sh`: clean.

`AnthropicAPILLM` live verification remains blocked (no credentials on
this machine, unchanged from every prior A round).
