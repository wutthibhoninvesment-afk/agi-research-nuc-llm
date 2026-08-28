---
name: one-shot-agent-no-background-wait
description: Use when an autonomous agent runs as a single batch process — a CLI in print mode, a cron job, a driver loop launching one fresh process per round — and a run the driver logs as finished (no error) produced nothing: no commit, no report, no state update, despite real tool calls. Symptoms: the agent's last message reads like "waiting for the background task," "standing by for the notification," or "will resume once the job finishes"; a background command/watcher/wakeup started and the run's final turn ended before it resolved; several rounds show real tool-call activity but no artifacts. Covers why a completion notification has nowhere to arrive once the one-shot process that started it already exited, and how a batch round should wait synchronously (blocking call, poll loop with a cap, foreground timeout) for every subprocess before ending its turn. NOT for a live interactive session or persistent supervisor (a later turn exists there), nor fire-and-forget work nothing in the run depends on.
---

# One-shot batch agents cannot wait for a later notification

A background job (a shell command backgrounded past its timeout, a watcher,
a scheduled wakeup) delivers its completion as a message injected into a
**later turn** of the same session. That mechanism assumes the session
keeps existing to receive it — true for an interactive chat, or a
supervisor process that stays up. It is **false** for a batch-invoked
agent: a CLI run in print/non-interactive mode (`claude -p "..."
--max-turns N`), a cron job, or a driver that launches a brand-new process
per round. The instant that process's assistant turn ends with no further
tool call, the process is done — there is no turn N+1 left in it for a
notification to land in. Confirmed live at least eight times in the same
research program (three within the four rounds that led to this skill's
authoring; two more afterward, on the same stale backlog — see the "stale,
already-verified" Pitfall below; three more in a row at rounds 248/249/250,
after the skill already existed — see the new Pitfall below): a round
backgrounds a verification/test job,
its final message says (in substance) "no further action needed, waiting
for the notification," and the round is then recorded by the driver as
`success` (no error, no crash) — but nothing it was about to do next
(write the report, update the state file, commit) ever runs, because
nothing ever runs again in that process. Eight rounds of real, substantial
work (34–170 tool calls each) evaporated this way with zero trace on disk
beyond a raw session-transcript log nobody reads by default — this skill's
own existence did not stop five of the eight.

## When to use (triggers)
- You are the agent BEING invoked as a one-shot batch process (a driver's
  `claude -p` call, a cron-triggered run, a CI job step) and are about to
  end your turn while a background command/watcher/wakeup you started is
  still pending.
- Reviewing why a batch/cron/driver-loop run shows no error yet produced
  no artifact: check whether its last recorded message describes waiting
  for something instead of reporting a finished result.
- Designing or reviewing any driver that launches a fresh agent process
  per iteration (the exact shape `self-updating-driver-loop` and
  `session-inheritance-audit` both already assume for this same program).

**When NOT to use:** an interactive session with a live user loop, or a
long-lived supervisor process that itself keeps running while waiting —
both have a genuine later turn to receive the notification in. Also not
for work truly nobody in this run needs the result of (log a note and
move on, don't manufacture a wait).

## Steps
1. **Recognize the invocation shape before doing anything long-running.**
   Ask: does this process definitely get another turn after this one, no
   matter what? A `claude -p` round with `--max-turns N` ends the moment
   the assistant emits a message with no tool call — there is no
   guarantee, and usually no fact, of a next turn. If unsure, treat it as
   one-shot. Checkable outcome: before backgrounding anything, you can
   name what specifically will re-invoke you if you stop now (a driver
   loop that starts a **fresh** process for the next round does not
   count — it never resumes THIS one).
2. **Never end a turn on a pending background wait in a one-shot
   process.** If a command must run long, either run it in the foreground
   with a real timeout sized to the work (`timeout`/`Bash` tool's own
   `timeout` parameter, up to its cap), or poll it synchronously in a
   loop within the SAME tool call / turn (`until [ -f done-marker ]; do
   sleep N; done`) rather than issuing a background start and then
   stopping. Checkable outcome: every subprocess you start in a one-shot
   round is joined (waited on) by a tool call that itself blocks until
   it's done, before your final message.
3. **If a job genuinely cannot finish before the round's time budget,
   finish the round anyway with an honest partial state**, not a silent
   wait: write down what's still running and its expected artifact path,
   commit/record what IS done, and let the next round's process (a fresh
   one) discover and read the finished output later — this is exactly
   `session-inheritance-audit`'s "read completed-but-unread artifacts"
   step, from the other side. Checkable outcome: the round's own record
   names the still-pending job by PID/output-path rather than assuming a
   later turn of itself will pick it up.
4. **Verify the recording, not just the exit code.** A driver that
   classifies a round `success` because the process exited 0 with no
   error is not proof the round's actual objective (a commit, a report,
   a state update) happened — see `session-inheritance-audit` step on
   "`success` in the driver log with no artifact." Grep the round's own
   final assistant text for a waiting/standing-by phrase as a cheap
   signal that this exact failure mode may have occurred.
   Checkable outcome: a round's `success` classification is cross-checked
   against an actual artifact (git diff, new file, updated record), not
   trusted from the exit code alone.

## Pitfalls
- **Assuming "you'll be notified when it completes" always applies.**
  That guidance is correct for interactive/persistent sessions and
  actively wrong for a one-shot batch invocation — the same phrasing
  appears in both contexts, but only one of them has a later turn to
  deliver into. Check the invocation shape (step 1) before trusting it.
- **A default tool timeout silently backgrounding a job you didn't ask
  to background.** Several tools auto-move a slow foreground command to
  background past a fixed timeout (observed: 120s) and describe it as
  "you will be notified" — in a one-shot round this is exactly the trap,
  even though you issued a plain, non-backgrounded command. Re-run with
  an explicit longer timeout (blocking) instead of accepting the
  auto-backgrounded version and ending your turn.
- **The driver logs `success` with real tool-call counts, so surely
  something landed.** Confirmed false three times: 60, 63, and 82 tool
  calls respectively, all real (file reads, test runs), all with the
  round's own intended deliverable — a knowledge file, a state-record
  update, a commit — never written, because the final action was always
  "start a background check, then wait," and the process ended right
  there. A high tool-call count is not evidence of a finished round.
- **Treating this as the same bug as `self-updating-driver-loop`'s stale
  cached process.** That skill is about a *supervisor* running old code
  because bash never re-reads a `while` loop; this is about a *round's
  own process* exiting mid-plan because it assumed a turn that will never
  come. Different mechanism, same symptom family (real work, nothing
  lands) — check both when a round goes silent.
- **A stale, already-verified cross-track backlog is an especially strong
  magnet for this exact trap.** Confirmed twice more, both while a round
  was specifically trying to land the SAME long-overdue diff
  (`session-inheritance-audit`'s own worked example: a SWE-loop test/fix
  sitting uncommitted for dozens of rounds): one round backgrounded a
  pytest run "before committing the backlog," another backgrounded three
  separate verification jobs "before proceeding with the reconciliation" —
  both ended their turn waiting, both logged `success`, neither committed
  anything. Revisiting old, already-tested work invites re-verifying it
  from scratch rather than trusting the prior verification, and
  re-verifying on a slow or single-core host (check `nproc` first) is
  exactly the multi-minute job step 2 says to run in the foreground with a
  real timeout, not background-and-wait — sizing the timeout to the actual
  expected wall-clock costs far less than a whole round evaporating again.
- **The skill existing in `skills/` does not stop the trap — nothing forces
  a one-shot round to actually consult it before backgrounding a job.**
  Confirmed live three rounds in a row (248/249/250, 2026-08-28, well after
  this skill was authored at round 171): each launched a genuinely
  different kind of background job (a fuzz/oracle campaign restarted from
  seed 0, the same campaign again, a 15-minute `swap_watch.py` poller) and
  each ended its own turn on the identical "waiting for the notification"
  phrasing this skill names verbatim in its own trigger description. Round
  251's own audit called this a **lookup gap, not a bad judgment call** —
  none of the three rounds' transcripts show any tool call reading this
  skill's file or the `skills/` directory before backgrounding. A skill
  file is a passive reference; it only helps a round that actually opens
  it. Round 253 (harness A) responded not by editing this skill again but
  by making the FAILURE retroactively self-correcting instead of relying
  on lookup: `run_driver.sh` now runs
  `session-inheritance-audit/scripts/check_round_recorded.py` once per
  round and, on a finding, appends the gap directly into the NEXT round's
  own prompt text (not just `driver.log`, which round 171's own detector
  proved 82 rounds of history nobody reads on its own) — see
  `session-inheritance-audit`'s matching Pitfall for the mechanism and why
  logging alone was already known to fail. That fix is reactive (it tells
  the round AFTER this one that a predecessor lost work) rather than
  preventive (it does not make a round consult this skill BEFORE it
  backgrounds anything) — whether three-in-a-row recurrences stop now is
  still an open watch item, not a closed one, as of round 255.

## Verification
```bash
# Cheap detector: does a round's own last assistant message describe
# waiting instead of reporting a result? (adapt the log glob/parser to
# your own transcript format — this one matches this program's
# logs/round-NNN.json stream-json shape)
python3 -c "
import json, sys
for path in sys.argv[1:]:
    with open(path) as f:
        lines = [json.loads(l) for l in f if l.strip()]
    texts = [c['text'] for l in lines if l.get('type') == 'assistant'
             for c in l.get('message', {}).get('content', [])
             if c.get('type') == 'text']
    if texts and any(p in texts[-1].lower() for p in
                      ('standing by', 'waiting for the background',
                       'no further action needed', 'resume once the')):
        print(path, 'ENDED ON A DANGLING WAIT:', texts[-1][:120])
" logs/round-*.json
```
- [ ] every backgrounded/watched subprocess in a one-shot round is joined
      (blocking wait, poll loop, or foreground timeout) before that
      round's final message
- [ ] a round's `success` status is cross-checked against an actual
      artifact (commit, new file, state-record entry), not the exit code
      alone
- [ ] the round's final assistant message reports a finished result, not
      a pending wait, whenever the process will not be resumed
