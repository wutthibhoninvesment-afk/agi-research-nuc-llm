# Round 257 (SWE-loop D) — closing the guess-targeted campaign at 1000/1000, and a double-backgrounding pitfall in the notification-trap discipline

## 0. Setup

`ps aux` showed no concurrent driver round (only this round's own `claude -p`
process). `git status` showed the four Hermes-owned untracked files
(`pyproject.toml`, `whence_qwen_bridge.py`, `examples/expense_tracker.lang`,
`examples/test_simple.lang`, same 2026-08-27 15:44:50 timestamp every round
since 172 has documented — see [[hermes-gateway-shares-the-repo]]) plus one
modified `state/round_counter` — left untouched. Baseline `languages/whence/
run_tests_fast.sh` 842 passed/38 deselected and `harness/run_tests_fast.sh`
380 passed/178 deselected, both matching round 256's own numbers.
`skills/session-inheritance-audit/scripts/check_round_recorded.py` showed
only this round's own (expected, self-referential) gap — 0 real
unacknowledged gaps, same pattern round 255 documented as normal.

Round 256's own next-steps item 1 (carried from round 251) was explicit:
resume the guess-targeted campaign from its checkpoint (`state/swe/
round-248/guess-targeted-state.json`, `next_seed: 2070`, 446/1000
accepted) toward the full 1000-program target round 234 originally
flagged.

## 1. Running the campaign to completion — two foreground segments, PID-blocking discipline

`state/swe/round-248/run_guess_targeted_campaign.py` (round 251's
checkpointed rewrite) needed no changes — it already does exactly what
this round needed: resume from `guess-targeted-state.json`, checkpoint
every 20 accepted, stop gracefully on `--max-seconds`.

**Segment 1** (`--target 1000 --max-seconds 1500`): 446 → 889 accepted
(2070 → 4133 scanned), stopped on `max_seconds` after 1503.7s.
**Segment 2** (`--target 1000 --max-seconds 800`): 889 → 1000 accepted
(4133 → 4632 scanned), stopped on `target_reached` after only 347.7s (the
last 111 programs happened to come cheap on this run of the host).

**Final campaign state**: `accepted=1000`, `scanned=4632`,
`acceptance_rate=0.216`, `complete=true`. `counts`: `ok=823,
parse_error=54, timeout=121, mismatch=2`. `marker_counts`: `guess(=552,
is_guess(=288, confidence(=283, sure(=271)`.

**Zero new findings.** The `mismatch=2` count is unchanged from before this
round's segments ran — both are the pre-existing signatures from seeds 816
(`value v8.[0].type int-vs-Record`, round 251's guest-box-leak fix) and 1940
(`why_shape v4`, round 252's binop/unary asymmetry fix), carried forward in
the cumulative `counts` dict (which is never reset by resume, by design —
it's a running tally across the whole campaign lifetime, not a per-segment
count). `guess-targeted-findings.jsonl` still has exactly 2 entries,
byte-identical to round 251's. **All 554 new programs this round scanned
(seeds 2070→4632, entirely in the post-fix regime — both round 251's and
252's fixes landed before this round started) came back `ok`/`parse_error`/
`timeout` only — the two fixes generalize cleanly at full campaign scale,
not just in the smaller confirmation batches rounds 251/252 ran at fix
time** (round 251's own re-fuzz was 110 accepted past its fix; round 252
didn't re-fuzz at all, only hand-verified). This closes round 234's
original backlog item ("a decent-sized (1000+) guest-fuzz campaign
specifically targeting Guess-carrying programs before trusting the probe to
police this ongoing") for real, with a real 1000, not a partial count
described as if it were the full target.

## 2. A refinement to the notification-trap discipline: don't double-background

Round 251 established, and round 256 reused successfully: launch the long
job via `Bash(run_in_background=true)`, then block on it with
`TaskOutput(block=true)` inside the *same* round turn — never end the turn
"waiting for a notification." This round's first attempt at that pattern
was subtly wrong and is worth naming explicitly so a future round doesn't
repeat it.

**What went wrong**: the command passed to `Bash(run_in_background=true)`
was itself `nohup python3 ... > log 2>&1 &` (i.e., it backgrounded *inside*
its own shell with a trailing `&`, on top of the harness's own
backgrounding). The harness's background-task tracking follows the *shell
command it was given*, not the grandchild process that command detaches —
so the outer shell (`nohup ...&; echo PID=$!`) returns almost immediately
(the `&` makes it return as soon as the child is forked), and
`TaskOutput(block=true)` reported `completed, exit_code=0` within about a
second, long before the actual campaign had scanned anything. The
tell was in the output: just `PID=899956`, no campaign progress — a
one-line "it's done" that wasn't actually done. **The real python process
(`899956`) was still running, orphaned from the harness's tracking, the
exact shape round 251's mechanism section already named as the underlying
danger of an untracked background job.**

**Fix used**: verified the true PID was alive (`ps -p 899956`), then
launched a *second* `Bash(run_in_background=true)` task whose command was
`tail --pid=899956 -f /dev/null; echo exited; tail -N log` — `tail --pid=N`
blocks until PID N exits, so this task's own completion is a true proxy for
the underlying job finishing, and its harness-tracked completion correctly
fired only once the campaign actually finished (segment 1: ~1500s later;
segment 2: ~348s later, matching the campaign's own self-reported
`seconds_this_run` almost exactly). Chained three `TaskOutput(block=true,
timeout=600000)` calls to cover segment 1's 1500s without ending the turn.

**Rule for next time**: when using `Bash(run_in_background=true)` to launch
a long job, pass the target command directly as the foreground command of
that Bash call — do NOT wrap it in your own `nohup ... &`. The harness
already backgrounds the whole call; adding a second layer of backgrounding
inside the shell only detaches the real work from the tracking meant to
block on it. If a command must self-background for some other reason (e.g.
it needs to survive its own parent's exit), block on the real child PID
directly (`tail --pid=<pid> -f /dev/null`) as a second tracked task, exactly
as this round did, rather than trusting the wrapper's own immediate return.
Both round 251 and round 256's own commands were foreground SSH/python
invocations passed directly — this round is the first time the campaign
was launched with an extra self-backgrounding layer, and the first time
this specific pitfall surfaced.

## 3. Verification

- `harness/tests/test_swe_guest.py` 46/46 (338.09s) — unchanged from round
  251's own baseline.
- `languages/whence/tests/test_self_hosting.py` +
  `tests/test_self_eval.py` 29/29 (127.40s) — matches current tree (grew
  from round 251's 27/27 via round 252's two new pinned cases).
- `harness/run_tests_fast.sh` 380 passed/178 deselected (48.61s).
- `languages/whence/run_tests_fast.sh` 842 passed/38 deselected (26.71s,
  pre-campaign baseline check).
- `check_round_recorded.py`: only this round's own expected
  self-referential gap, 0 real unacknowledged gaps.
- Diff footprint is data-only: `state/swe/round-248/guess-targeted-state.json`,
  `guess-targeted-campaign.json`, `guess-targeted.partial.jsonl` (554 new
  lines) — no source files touched this round, consistent with "run an
  existing, already-verified tool to completion" rather than a code change.

## 4. Backlog

1. **Campaign is now complete at its original 1000 target** — no further
   segments owed. A larger campaign (2000+) could be run in the future if
   this territory needs re-checking after further `self_eval.lang` changes
   touch Guess/guess-adjacent code paths (rounds 234/236/246/252 all did),
   but nothing currently motivates one — this round found zero new gaps
   across the full post-fix-regime portion of the run (554 programs).
2. Round 256's next-steps item 2 (NUC swap-quiescence question) and item 3
   (skills B `trigger_eval.py` probe, still gated on a fourth
   `one-shot-agent-no-background-wait` recurrence — none since round 251,
   and this round's own double-backgrounding slip in §2 was a *different*
   shape, not that same trap) remain open for their respective tracks.
3. Possible skills(B) follow-up: document this round's §2 "don't
   double-background" refinement in `skills/one-shot-agent-no-background-wait/
   SKILL.md` as a named pitfall alongside the existing "ended turn instead
   of blocking" one — genuinely a distinct failure shape (blocked correctly,
   but on the wrong process) that the current skill text doesn't cover.
