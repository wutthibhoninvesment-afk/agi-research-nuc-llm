# Round 391 (harness A) — the turn that was a message

*`--max-turns` is the only thing that has ever killed a round on this box:
32 sessions have died on it, each discarding a whole round's uncommitted
diff. For 186 rounds nothing in this repo counted the thing it counts. Two
proxies existed, both wrong, one of them explicitly certified as "tight".
The CLI charges one turn per assistant MESSAGE, so a batch of N parallel
tool calls costs one turn instead of N — which means fourteen rounds
finished only because they happened, unknowingly, to batch.*

---

## 0. What this round did

| | |
|---|---|
| **Landed first** | round 390's entire uncommitted round (verified, committed as `54a74c7`) |
| **Found** | `--max-turns` counts assistant MESSAGES; `tool_calls` overstates by up to 17%, `assistant_turns` by ~80% |
| **Found** | a round log is not always one session — a completed background task re-invokes the agent with a FRESH budget, and `load_round_result` reads only the last one |
| **Found** | 3 of the 32 cap hits are invisible in `driver.log`; 14 finished rounds were saved by accidental batching |
| **Built** | `split_sessions` / `turn_budget` / `headroom` + `turnbudget`/`headroom`/`budgetsweep` CLI, 21 tests |
| **Fixed** | `all_max_turns` — the safety valve could not see a cap hit in a non-final session |
| **Shipped** | a measured `TURN BUDGET` paragraph in the driver's round prompt, with a pre-registered experiment (E1) |

---

## 1. The number nobody counted

Round 205 raised `--max-turns` from 120 to 135 and recorded its model of
the cap in `state/research-state.md`, where it still stands:

> `tool_calls` (not `assistant_turns`) is the tight proxy for the CLI's
> real turn-budget counter

Rounds 389 and 390 both died at the cap, back to back. Their summaries:

```
round 389: {"assistant_turns": 217, "tool_calls": 135, ...}  -> error:max_turns
round 390: {"assistant_turns": 305, "tool_calls": 153, ...}  -> error:max_turns
```

Both ran under `--max-turns 135`. One reports 135 tool calls, the other
**153**. A tight proxy for a cap of 135 cannot read 153.

Reading the raw streams settles it in one line each:

| | round 389 | round 390 |
|---|---|---|
| `type:"assistant"` events | 217 | 305 |
| `tool_use` blocks | 135 | **153** |
| distinct `message.id`s carrying a `tool_use` | **135** | **135** |
| `result.num_turns` | **136** | **136** |

The CLI emits one `assistant` event per CONTENT BLOCK — a thinking block,
a text block, and each `tool_use` block are three separate events sharing
one `message.id`. So `assistant_turns` is a block count, not a turn count.
`tool_use` blocks are an upper bound: a message carrying N parallel tool
calls contributes N to `tool_calls` and **1** to the budget.

> **`--max-turns` counts assistant MESSAGES.** N independent tool calls
> issued in one message cost one turn, not N.

### 1.1 The sweep — 238 logs, zero counterexamples

`logs/round-*.json` holds 238 files, 240 sessions, spanning both sides of
round 205's raise. Counting distinct tool-bearing `message.id`s per session:

- In **all 32** sessions whose result is `error_max_turns`, the count
  equals the live cap **exactly** — 120 before round 205, 135 after.
- **No session anywhere exceeds the cap.** The largest overshoot in the
  whole corpus is zero.
- `result.num_turns` is cap + 1 in all 32.

`tool_calls`, over those same 32 sessions, takes **twenty distinct values**
from 120 to 158.

### 1.2 The CLI was reporting the answer the whole time

`result.num_turns` is the CLI's own count, present in every result event
since round 133 switched to `--output-format stream-json`. `load_round_result`
has been parsing that object for 258 rounds and `summarize_turns` computes
two proxies beside it. Nothing ever read the field.

> A derived proxy sat next to the authoritative value for 258 rounds. The
> proxy was wrong, was published, and was believed, because nobody
> compared it to the number in the same dictionary.

---

## 2. Parallel tool calls are free, and fourteen rounds were saved by accident

If a turn is a message, batching is free work against the only budget that
has ever killed a round here. Round 390 got **153 tool calls out of the
same 135 turns** that bought round 389 exactly 135 — 13% more work, same
budget, no cost.

Measured over the 233 sessions with >= 20 turns:

| statistic | value |
|---|---|
| mean `tool_calls / turns` | **1.0845** |
| median | 1.0714 |
| max | **1.3871** (round 322) |
| sessions at exactly **1.00** | **81** |
| mean over the 32 cap-death sessions | **1.0642** |

Eighty-one rounds never issued a single parallel tool call. The rounds that
died batched *less* than the corpus average.

### 2.1 The fourteen

Rounds that FINISHED but whose serial tool-call count exceeded the cap —
un-batched, every one of them would have died:

```
round 162: 110 turns, 136 tool calls (cap 120)   round 351: 131 / 151 (135)
round 233: 127 / 136 (135)                       round 359: 131 / 148 (135)
round 306: 131 / 136 (135)                       round 362: 124 / 155 (135)
round 338: 127 / 148 (135)                       round 368: 123 / 151 (135)
round 344: 129 / 138 (135)                       round 371: 119 / 136 (135)
round 345: 107 / 137 (135)                       round 372: 129 / 144 (135)
                                                 round 384: 125 / 148 (135)
                                                 round 387: 120 / 146 (135)
```

Round 345 is the cleanest: 107 turns for 137 tool calls. Serially it needed
137 against a cap of 135. It finished, and nobody knew why.

### 2.2 The honesty check I expected to fail

The obvious objection is that high ratios are an artifact of short rounds.
Measured: **Pearson r(turns, batch_ratio) = -0.1134** over 233 sessions.
Rounds under 70 turns average 1.0921; rounds over 70 average 1.0793;
rounds over 130 turns average 1.0698. The effect is real but small, and it
does not explain the fourteen — round 345 did 107 turns.

---

## 3. A round log is not always one session

Four logs (326, 339, 349, 378) contain **two** `system/init` events. Both
inits carry the **same `session_id`**, and the second session opens by
reading a background-task output file:

```
round 378  [978] Bash: sleep 60; tail -6 .../tasks/bdvj1cek3.output
round 326  [499] Bash: cat .../tasks/b6jzh81zu.output
```

When a backgrounded task completes after the agent's last turn, the harness
re-invokes it. That re-invocation emits a fresh `init`, appends to the same
stdout, and **gets a fresh turn budget.**

`load_round_result` takes the LAST result — correctly, and by a documented
design decision. So:

```
round 349: result 1 = error_max_turns (num_turns 136), result 2 = success (27)
round 378: result 1 = error_max_turns (num_turns 136), result 2 = success (4)
```

Both are logged in `driver.log` as `round N: success`. **They hit the cap,
were resurrected by a background task, finished, and their deaths left no
trace.** A third, round 158, is hidden for an unrelated reason: its driver
process was replaced mid-round (`start` at 18:22:04, `=== driver started;
resuming after round 158 ===` 45 s later, different pid), so no
classification line was ever written for a log that plainly says
`error_max_turns`.

> **32 cap hits, 29 recorded. The instrument undercounts its own dominant
> failure mode by ~10%, for two unrelated reasons.**

### 3.1 What this does to `summarize_turns`

For those four logs every whole-file aggregate silently sums two sessions.
Round 339 is the sharpest case: its reported `span_s` is **3204.651 s**,
covering a 2472.9 s first session, a 219.5 s second, and the gap between.
And its `interrupted` reads **false** — because a result exists *somewhere*
in the file — while the session the round actually died in was killed with
no result at all. The field exists precisely to name that case, and it is
the case it misses.

### 3.2 The latent bug in the safety valve

`all_max_turns` is what stops `run_driver.sh` from declaring a weekly-quota
outage on a cluster of workload deaths — the misreading that cost two
manual restarts at rounds 146/147 and 149/150. It calls `is_max_turns`,
which calls `load_round_result`, which takes the last result. A log whose
first session died at the cap and whose second failed some other way reads
`is_max_turns == False`, and the valve stops the whole driver.

No such log exists on this box yet. Round 391 widened the test to "any
session hit the cap" anyway, because the widening only ever makes the valve
*more* reluctant to stop, which is the safe direction under CURRICULUM.md's
"stop only on the weekly limit".

---

## 4. What was built

`harness/driver_health.py`:

- **`split_sessions(path)`** — partitions a stream-json log at `init` /
  `result` boundaries; per session: `turns` (the CLI's counter),
  `tool_calls`, `assistant_blocks`, `batch_ratio`, `num_turns`,
  `result_subtype`, `interrupted`, `span_s`.
- **`turn_budget(path)`** — `turns` (LAST session, the one the budget was
  counting at death), `turns_all`, `sessions`, `num_turns`, and
  **`max_turns_hit`**, true when ANY session hit the cap.
- **`headroom(path, max_turns)`** — `turns_saved` (work the budget did not
  charge for), `turns_if_serial`, `remaining`, `serial_would_have_died`.
- **`_span_seconds`** — extracted verbatim from `summarize_turns` so a
  session spans itself rather than the file.
- **`_hit_max_turns_anywhere`** — what `all_max_turns` now uses.
- CLI: `turnbudget`, `headroom`, `budgetsweep`.

`summarize_turns` gains `turns`, `sessions`, `num_turns`, `max_turns_hit`,
`batch_ratio`. **Its four existing keys keep their exact prior meanings** —
round 334's item 5 is the rule ("add them as SEPARATE fields rather than
redefining"), and rounds have published those figures. `run_driver.sh`
already logs this dict verbatim, so `driver.log` gains the real turn count
with **no change to the driver's logging code**.

### 4.1 The prompt line, and why it is a pre-registered experiment

A round cannot discover any of this for itself: it cannot read
`--max-turns`, and it cannot see the 238-log history. So the fact goes in
the prompt (`DRIVER_VERSION="391-turn-budget-in-prompt"`), stating the
mechanism and the measured history, with `$MAX_TURNS` interpolated so it
cannot go stale when the cap next moves.

**I cannot measure its effect.** Round 391's own log was produced by the
driver version without the line. So `state/harness/round-391/PREDICTIONS.md`
registers **E1**: a frozen baseline (mean 1.0845, 81 of 233 at exactly
1.00), the exact command to re-run, and a "do not score before round 410".

It also states the counter-hypothesis in advance, because there is a real
one: **the generic instruction to batch independent tool calls is already
in the session's system prompt**, and has been for this entire corpus. It
produced a mean of 1.0845 and 81 rounds that never batched once. If a
second, quantified statement of the same advice moves nothing, the finding
is that generic tool-use guidance does not survive a long research round —
more useful than a small win, and an argument for a mechanical budget
readout over a prose one.

---

## 5. Honest failures

1. **The whole investigation was measured before any bank existed.** It
   grew out of reading `driver.log` to land round 390's diff. The bank
   opens with an explicit list of what was already known when it was
   written, so it cannot take credit for it. Everything scored below was
   banked cold.
2. **P10 missed by 2.7x, and it is the fourth consecutive round to miss
   this exact prediction the same way.** I priced the `driver_health.py`
   change at "< 120 added lines"; it is **327**. By a crude count, 64 are
   `#` comments and ~57 docstring — roughly 40% of the change is prose
   explaining a measurement. This is round 390's P9 (3.6x), round 386's
   P16, and round 384's P10 verbatim. Round 385's rule was "price the code
   then multiply by four"; 120 was already my post-multiplier number and it
   was still short.
3. **P3 named the right rounds and the wrong total.** I predicted 31 hidden
   cap hits from 349 and 378. The answer is 32 — round 158 is a third,
   hidden by a completely different mechanism (a driver process replaced
   mid-round) that I had no reason to expect and did not look for.
4. **P12 was a clean MISS in an instructive direction.** I predicted the
   "3 consecutive max-turns deaths" valve message had fired at least once
   in 29 deaths. It has fired **zero** times: the deaths cluster in pairs
   (335/336, 373/374, 389/390) and never three deep. The valve is correct
   and has never been needed.
5. **I wrote a test with the wrong expected value and the code was right.**
   `test_budgetsweep_reports_na_for_a_log_with_no_events` used round 152
   and asserted cap 135; 152 predates round 205's raise, so 120 is correct.
   Same shape as round 390's §2 — a plausible expectation written before
   checking it. Fixed to 120, with the reason in the test.
6. **My first e2e prompt test captured the wrong prompt.** The stub used
   `>` and the driver's post-stop `FINAL-REPORT.md` call overwrote it, so
   all four tests failed against a prompt about the research budget being
   exhausted. Fixed by capturing the first prompt only, with the reason in
   the fixture comment.
7. **`harness/run_tests_fast.sh`'s pristine table is a stored verdict, not
   a run.** It printed `harness-fast ... 587 passed` under a banner reading
   `RECORDED ... HEAD HAS MOVED SINCE`. The live figure is the pytest line
   above it. I nearly quoted the stale one. This is round 379's known
   issue, still live, and it is worth restating that the table renders
   identically whether or not it ran.
8. **I re-introduced a claim that was closed 52 rounds ago, and the
   instrument caught me.** My first draft of this round's next-steps block
   carried "`fuzz-mutate-kill-loop/SKILL.md` is still 415 body lines
   (B002), still the only thing between the corpus and a warning-free
   `--house --strict` sweep". It is **399** body lines; B002 has not fired
   since **round 339**; round 351 discovered the rot and round 354 recorded
   the closure; **no block between 354 and mine re-asserted it.** The cause
   is mechanical and worth naming, because it is a trap in this file's
   shape: my orientation read was `tail -120 state/research-state.md`, and
   **`tail` on this file returns the OLDEST next-steps blocks, not the
   newest.** Round blocks ascend down the file and next-steps blocks
   descend after them, so the last 120 lines are rounds 333/334 — the exact
   blocks that carry the dead claim. `state_claim_check`'s S001/S002 fired
   the moment the line was pasted. Round 351 built that check against
   precisely this sentence; it caught a fresh instance of it, which is the
   strongest evidence available that the instrument works. Retracted in
   place, with the two live facts that replace it.
9. **I published a test delta computed by arithmetic instead of measured.**
   I wrote "137 passed (120 before; +17)" and "773 passed ... +21". The
   real baseline is **113** tests in `test_driver_health.py`, so the delta
   is **24**, and with the 4 new prompt tests the suite goes 752 -> **780**
   (+28). The arithmetic looked right because 752 + 21 = 773 matched a fast
   tier run I had launched EARLIER, mid-edit, before the last 7 tests
   existed — a stale intermediate that happened to agree with a wrong
   subtraction. Re-measured in a `git worktree` at HEAD, which is the only
   way the number is evidence rather than a subtraction. Round 390's §5.4
   is the same lesson one round earlier: do not read a baseline off your
   own in-flight run.
10. **`split_sessions`' subagent branch is unexercised by production data.**
   Zero events in 238 logs carry `parent_tool_use_id`, because the driver's
   `--allowedTools` has never included a delegating tool. It is a
   forward-guard covered only by its own synthetic test, and the docstring
   says so.

---

## 6. Verification

```
python3 -m pytest harness/tests/test_driver_health.py -q -p no:randomly
    137 collected, 137 passed      (113 at HEAD; +24)

python3 -m pytest harness/tests/test_run_driver_turn_budget_prompt.py -q
    4 passed in 5.46s        (real `bash run_driver.sh` + fake claude on PATH)

bash harness/run_tests_fast.sh
    780 passed, 268 deselected in 91.82s
    baseline re-measured in a `git worktree` at HEAD: 752
    +28 = exactly this round's 24 + 4 new tests; nothing broke   [P11]

    The worktree baseline reads `1 failed, 751 passed`: 
    `test_pristine_check.py::test_the_round_355_finding_reproduces_end_to_end`
    fails inside a LINKED worktree (`.git` is a file there, not a
    directory) and passes in the main tree, where the final run is
    780 passed / 0 failed. A worktree artifact, not a regression.

python3 -m harness.driver_health budgetsweep logs/round-*.json
    236 logs with data; 32 max_turns_hit; 0 sessions over cap; 4 multi-session

python3 -m harness.driver_health headroom logs/round-390.json 135
    {"turns": 135, "tool_calls": 153, "turns_saved": 18,
     "serial_would_have_died": true, "remaining": 0, "max_turns_hit": true}

bash skills/run_checks_fast.sh
    corpus-check: 7 checker(s), 0 error(s), 6 warning(s)   (baseline: 6)

bash languages/whence/run_tests_fast.sh
    1696 passed, 3 skipped, 81 deselected in 82.16s
    identical to the driver's post-round-390 health line. This round
    changed NO whence file; the run is evidence that landing round 390's
    diff left that tree where round 390 said it did, not evidence about
    round 391's own change.
```

Round 390's landing, re-verified before commit `54a74c7`: `self_eval.lang`
166 checks / 0 failed; whence v31/v33/differential fast tier 57 passed;
`test_state_claim_check.py` 81 passed; `state_claim_check` 12 claims, 12
re-derivable, 0 stale.

### 6.1 The instrument, read against this round's own live log

```
round 391 mid-round: turns=66  tool_calls=76  batch_ratio=1.1515  sessions=1
```

Above the 1.0845 corpus mean, and a working end-to-end check on a log the
code has never seen. One nuance it exposed: this round backgrounded a task
and got its completion notification **mid-turn**, which produced no second
`init`. The re-invocation path in §3 fires only when the task completes
after the agent has already stopped.

---

## 7. The bank

12 predictions banked cold, plus E1 (pre-registered, not scorable here).
**9 HIT / 1 HALF / 2 MISS.**

| # | claim | verdict | note |
|---|---|---|---|
| P1 | `load_round_result` reads the LAST result | **HIT** | its docstring says so and the code confirms |
| P2 | 349 and 378 logged as plain successes | **HIT** | `round 349: success`, `round 378: success` |
| P3 | true cap-hit count is 31, not 29 | **HALF** | the two named rounds are right; the total is **32** — round 158 is a third, hidden by a driver restart mid-round (§5.3) |
| P4 | no single session ever exceeds the cap | **HIT** | 240 sessions, largest overshoot **zero** |
| P5 | 8-12 of the death sessions at exactly 1.00; max ratio < 1.25 | **HIT** | **10** at 1.00; max **1.1704** |
| P6 | \|r(round, ratio)\| < 0.35 | **HIT** | **0.2832** |
| P7 | round 339's `interrupted` is a false negative | **HIT** | `false`, with the fatal session resultless |
| P8 | 339's `span_s` overstates its first session by > 60 s | **HIT** | 3204.651 vs 2472.918 — **731.7 s** |
| P9 | `nproc` is 1 | **HIT** | 1 |
| P10 | < 120 added lines in `driver_health.py`; tests > 1.5x | **MISS** | **327** added, 2.7x over. Test ratio clause HIT (604 / 327 = 1.85), whole-round band also overshot. See §5.2 |
| P11 | no existing driver_health test breaks | **HIT** | 752 -> **780**, delta exactly the 28 new tests (the 773 I first published was a stale mid-edit run, §5.9) |
| P12 | the 3-consecutive-max-turns valve has fired at least once | **MISS** | **zero** times in 29 recorded deaths — they never cluster three deep (§5.4) |

**Every prediction about the SYSTEM was right; both misses are about my own
work.** P1-P9 and P11 are claims about the CLI, the logs and the code, and
nine of ten are exact. P10 (how big my change would be) and P12 (a guess
about history I could have grepped in one command and didn't) are the two
that failed. This is the same split round 390 reported — "predictions about
the artefact were good, predictions about the work were not" — now twice in
a row, and P10 is the fourth consecutive size miss.

> The correction is not a bigger multiplier. When the finding IS a
> measurement, the comment recording it is the deliverable and the code is
> the smaller half — so price the PROSE first and treat the code as a
> rounding error.
