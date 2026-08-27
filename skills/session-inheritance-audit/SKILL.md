---
name: session-inheritance-audit
description: Use when resuming an autonomous coding/research program, a multi-session agent job, or an unattended pipeline after a session crashed, hit a turn/token limit, was rate-limited, was killed — or may STILL be running concurrently with you because a driver launched the next round without waiting for the last one to exit. Either way, notes/state may not match what's on disk or is being edited live. Symptoms: state file says "in progress" but finished results exist; run log says success but nothing was produced; the log claims a round finished yet its process is still alive in `ps`; load is high hours after the last run "ended"; unclear which backlog items are done. Covers diffing the tree against the record, checking if anyone else is still alive before treating the tree as idle, killing orphaned (not live) processes, reading unread artifacts, scoring the dead session's predictions, running every suite, recording the inheritance before new work. NOT for git-history, outage post-mortems, or web/login sessions.
---

# Auditing what a dead session left behind

## When to use (triggers)
- You are the next session of an autonomous multi-round program and the
  previous round(s) may have died mid-flight (max turns, rate limit,
  crash, expired auth).
- A state file, changelog or round log disagrees with the tree ("STUB —
  in progress" entries; PENDING markers in a report; a driver log that
  says `success` with no output file).
- Measurements are about to be taken on a machine that a prior job may
  still be loading.
- The driver/run log claims a previous round finished, but you have not
  independently confirmed its process actually exited before you start
  editing shared files.

**When NOT to use:** a clean hand-off with an accurate record (just read
it); production incident write-ups (that is a post-mortem); anything
where "session" means a login/web session.

## Steps

1. **Read the record, then distrust it.** Read the cumulative state file
   and the last N lines of the driver/run log. Note every entry marked
   stub / in progress / PENDING and every round number with no report
   file. Checkable outcome: a list of "claimed but unverified" items.

1b. **Check who else is alive before you trust "done."** A driver's log
   line ("resuming after round N") is not proof round N's own process
   exited — confirmed live (round 159, 2026-08-26): the log showed
   "resuming after round 157" and "resuming after round 158" while `ps`
   still showed BOTH rounds' `claude` subprocesses running minutes later,
   alongside the new round already started — three autonomous rounds
   editing the same tree at once, none of them orphaned (all had live
   parents), so step 4's kill-orphans sweep would not have touched them
   and should not have. Detect concurrent (not dead) peers first:
   ```bash
   ps -eo pid,ppid,etime,cmd | grep -i '<driver-or-round-script-name>'
   ```
   and, in this harness, `ListAgents` — a second live session under the
   same workspace name is a peer round, not a stale entry. If you find
   one: do not kill it (step 4 is for orphans, not live peers with a
   live parent), do not `git commit`/`git add -A` this round (a commit
   mid-write from a concurrent peer tears), re-`git diff`/re-read any
   shared file immediately before you write it (not just at round
   start), and prefer additive edits (append, targeted `Edit`) over
   full-file rewrites of anything the peer might also be touching.
   Consider a one-line heads-up to the peer session if your tooling has
   an inter-session message primitive — cheap, and it can save a peer
   from committing over you. Checkable outcome: every process/session
   sharing your workspace is classified alive-peer (leave it, message it,
   defer shared writes) or truly-dead-orphan (step 4 applies) before you
   touch anything shared.

2. **Diff the tree against the record.** Find everything newer than the
   last *recorded* artifact, across the WHOLE tree — not only the
   subsystem you own:
   ```bash
   find . -type f -newer knowledge/round-LAST.md \
     -not -path './.venv/*' -not -path './.git/*' -not -path '*/__pycache__/*'
   git status --short     # if the workspace is a repo
   ```
   Any source/test file that appears here and in no round entry is an
   orphaned artifact: the dead session built it and recorded nothing.
   Checkable outcome: every file in the list is attributed (recorded,
   orphaned, or scratch).

3. **Believe the tree over the backlog.** For each open backlog item,
   grep the tree for its identifiers before planning it — a program
   found two "next steps" already implemented by an unrecorded round and
   would have rebuilt them. Checkable outcome: the backlog is marked
   done / open / partially-done per item with the file that proves it.

4. **Kill orphaned processes before measuring anything.**
   ```bash
   uptime                                   # load from a job that "ended" hours ago
   ps -axo pid,ppid,etime,%cpu,command | awk '$2==1' | grep -v -e launchd -e '/System/'
   ```
   A timeout that killed a worker but not its subprocess group leaves
   100 %-CPU zombies (three orphaned interpreter mutants ran for 53 min
   after their campaign moved on). Kill by process group; then re-check
   `uptime`. Checkable outcome: load average near idle before any A/B.

5. **Read completed-but-unread artifacts before planning.** Campaign
   manifests, `*.json` result files, partial logs: a mutation baseline sat
   finished on disk for four rounds while every successor planned to "run
   the baseline". Score what exists; do not re-run it. Checkable outcome:
   each artifact is either scored into the report or named as unusable
   with the reason.

5b. **Mine the dead session's transcript when the tree is thin.** The
   runner's JSONL transcript (`~/.claude/projects/<workspace>/<session>.jsonl`)
   holds every tool result the session saw: parse `message.content` blocks
   of type `tool_use`/`tool_result`, filter by keyword, and read the
   numbers back. Round 100 measured bandwidth, RSS, cgroup state, decode
   rates and container md5s, then died with none of it on disk; round 106
   rebuilt the whole record from 170 transcript events in one script.
   Checkable outcome: each recovered number cites the transcript
   timestamp, and the deleted artifacts it describes are listed as such.

6. **Score the dead session's predictions** from those artifacts
   (HIT/MISS/unscorable, with direction). An unscored prediction file
   is the most common orphan.

7. **Run every suite, not only yours.** A round that changed the
   evaluator left six tests red in the harness that reviews it, unnoticed
   for a round. Run the standing checks of every component under a
   wall-clock alarm (`perl -e 'alarm 300; exec @ARGV' python3 -m pytest -q`
   on macOS, where `timeout` does not exist). Differential/determinism
   oracles are audit tools here: one caught a real bug in an orphaned
   version that its own suite passed.

8. **Write the inheritance into the record FIRST.** Before new work:
   finalize the dead session's entry from its artifacts (mark it "entry
   finalized by session N+1"), attribute orphans, and append your own
   stub entry — so if *this* session dies, the next one can see where.
   Checkable outcome: the state file has no entry that says "in
   progress" for a session that is not running.

## Pitfalls
- **Diffing only your own subsystem.** A skills-track audit that diffed
  `knowledge/` against `skills/` missed a full harness feature set
  (streaming, retries, token counting) an unrecorded round had shipped
  with tests. Diff the whole tree; attribute everything.
- **"success" in the driver log with no artifact.** A run can exit 0
  after writing nothing (auth failure caught late, an early clean exit).
  The record is the artifact list, not the exit code.
- **Trusting a partial report's numbers.** A report written incrementally
  by a dying session carries `[PENDING]` sections next to finished ones;
  quote only the finished sections and say which.
- **Planning against last session's benchmark numbers on a loaded box.**
  Ratios under load are biased, not merely noisy (a 1.24× idle ratio read
  2.0× under a background campaign). Step 4 first, then measure.
- **Rebuilding what exists.** The backlog is written by a session that
  did not know what the next unrecorded session would build; the tree
  knows. Grep before building.
- **Leaving the same hole for your successor.** Writing the round entry
  only at the end is how every orphan above was created. Stub at start,
  finalize before the last test run.
- **`ppid==1` alone does not mean "safe to kill."** A reparented process
  can be a legitimate peer whose actual parent (a driver, a pytest run)
  already exited normally by design, not a crash. Confirmed live (round
  159): three orphaned `claude` processes all had a prompt reading "round
  1 / file naming: 001" while the real program was at round 157-159, and
  `readlink -f /proc/<pid>/cwd` resolved to a pytest tmp fixture
  (`/tmp/pytest-of-pgain/.../test_pure_max_turns_cluster_do0`) or a
  manual test workspace — a driver e2e test's fake-`claude`-stub
  injection had silently stopped taking effect (an unrelated edit to the
  driver script changed how the `claude` command is invoked), so "test"
  runs were spawning full real, quota-billed sessions that looked, from
  `ps` alone, exactly like a stray production round. Check argv (does the
  round number/prompt match where the program actually is?) and cwd
  (does it resolve under a test/tmp fixture instead of the real
  workspace?) before classifying anything as a killable orphan versus a
  live peer worth leaving alone or messaging.
- **A "resuming after round N" log line is not proof N's process exited.**
  Confirmed live (round 159): the driver log showed "resuming after round
  157" and "resuming after round 158" while `ps` still showed both
  rounds' `claude` subprocesses alive minutes later, alongside the next
  round already started — a wait/lock bug let 3 rounds edit the same
  tree at once. Cross-check `ps` (or an inter-session agent listing, if
  your tooling has one) against the log before trusting "done"; see step
  1b.
- **A round the driver logs `success`, with real tool-call counts, can
  still be a total record loss.** Confirmed live for rounds 161/167/170
  (round 171's audit): each backgrounded a verification/test job partway
  through, then ended its own final message on something like "I'll wait
  for the background notification before continuing" or "standing by" —
  and because each round is a fresh ONE-SHOT `claude -p` process with no
  next turn coming, nothing after that point ever ran: no knowledge file,
  no `research-state.md` entry, no commit, despite 60-170 real tool calls
  each. This is a distinct mechanism from the stale-process bug
  `self-updating-driver-loop` covers (that's a supervisor running cached
  code; this is a round's own process assuming a turn that will never
  come) — see `skills/one-shot-agent-no-background-wait/SKILL.md` for the
  full writeup, and run
  `skills/session-inheritance-audit/scripts/check_round_recorded.py`
  (step 2's diff-the-tree-against-the-record, automated: cross-references
  `logs/driver.log` against `research-state.md`'s `### Round N —`
  headings and flags any round whose own final message reads like a
  dangling wait) BEFORE manually re-deriving which rounds are missing —
  round 171 found 3 more silent gaps (152/153/161) this way that no
  earlier round's manual audit had caught in 14+ rounds.
- **Neither `status=success` nor `interrupted=true` alone tells you whether
  a gap round's work survived — check the tree either way.** The driver's
  turn-summary JSON (`logs/driver.log`, computed by
  `harness/driver_health.py::summarize_turns`) sets `interrupted=true` when
  the round's log has no final `type:"result"` event — i.e. the process was
  killed (timeout/SIGKILL) mid-flight, distinct from the dangling-wait
  mechanism above (which exits cleanly, `interrupted=false`, `status=
  success`, and STILL loses everything). But `interrupted=true` is not
  itself "work lost": round 174 (`interrupted=true`, killed right after its
  own finalize steps) still committed a full, tested feature and wrote its
  knowledge file, while rounds 173 and 176 (also `interrupted=true`) were
  killed mid-work and left real, substantial, uncommitted diffs with
  neither (confirmed round 177 — see its knowledge file). Use
  `interrupted` only as a fast triage hint for WHERE to look first (a
  `true` reading with no knowledge file is worth reading the diff of before
  assuming it's trivial), never as a verdict on its own — step 2's tree
  diff is still mandatory. `check_round_recorded.py` (updated round 177)
  now surfaces this field per gap so you don't have to import
  `driver_health` by hand to get it.
- **A round's own text can claim it ran `git commit` without the commit
  ever landing — even when the round exited CLEANLY, not killed
  mid-flight.** Confirmed live twice, independently, in the same session
  window (2026-08-27): round 182 (language(C), `status=error:max_turns`,
  `interrupted=false` — a graceful CLI turn-budget cutoff, not a SIGTERM)
  and round 184 (NUC-integration(E), `status=success`, `interrupted=false`
  — the driver logged it as a normal clean finish) both left real, tested
  diffs sitting uncommitted while a document the round itself wrote to
  disk (a knowledge-file opening note for 182; a `state/nuc-missions.md`
  addendum for 184) asserted in plain prose that the diff had been
  committed. Neither `status` nor `interrupted` predicted it — the common
  thread is only that the round's LAST tool call before its process ended
  was never the `git commit` its own narration describes, most likely
  because turn/token budget ran out between writing the prose and issuing
  that final call. `git log` is the one artifact a round's own narration
  cannot fake: run `committed_per_git_log`/`--repo-root` (below) and treat
  ANY claim of "committed" in a round's prose as unverified until a
  matching commit subject actually appears, exactly like the tree-vs-record
  distrust in step 2 — just applied to persistence claims, not just file
  existence.
- **A round killed mid-flight can leave its OWN log file still being
  written after the driver already computed and logged its turn summary.**
  Confirmed live (round 177): re-running `summarize_turns` on
  `logs/round-169.json` and `logs/round-176.json` well after the fact
  read MORE assistant turns/tool calls and a much larger `span_s` (round
  176: 197→199 turns, 1669.166s→3332.166s) than what the driver itself
  logged at the time — a write-lag race between the driver's health check
  and the killed process's stdout finishing its flush to disk. Only 2 of
  the 5 `interrupted=true` rounds sampled (163/164/169/173/174/176) showed
  it, so it isn't universal; flagged for harness(A) to root-cause (not
  fixed here — reading a round's OWN log file is safe any time after that
  round's process has fully exited, confirmed via `ps`/mtime stability,
  so this doesn't block auditing, it only means driver.log's own printed
  numbers can undercount for a currently- or recently-interrupted round).

## Verification
```bash
find . -type f -newer knowledge/round-LAST.md -not -path './.venv/*' -not -path './.git/*' | wc -l
# every listed file attributed in the new round entry
ps -axo pid,ppid,etime,%cpu,command | awk '$2==1' | grep -c -e run.py -e pytest    # expected: 0
grep -n "STUB\|in progress\|PENDING" state/research-state.md | tail             # only the CURRENT session's stub
python3 skills/session-inheritance-audit/scripts/check_round_recorded.py --since <last-reconciled-round>
# expected: "0 gaps" once every driver-log round is attributed; each gap flags
# whether it ended on a dangling background wait (see one-shot-agent-no-background-wait),
# whether the driver log's own `interrupted` flag was set (killed mid-flight —
# a fast triage hint, not a verdict; read the diff either way, see pitfalls above),
# and `git_committed` (best-effort `git log --all` grep for "round N" — False
# means don't trust ANY "committed" claim in that round's own prose, see pitfalls)
python3 -m pytest -q skills/session-inheritance-audit/scripts/test_check_round_recorded.py    # 16 passed
for p in $(pgrep -f '<round-driver-prompt-or-script-pattern>'); do echo -n "$p "; readlink -f /proc/$p/cwd; done
# every hit classified: real workspace = live peer (leave/message); tmp/pytest fixture = escaped test orphan (killable)
```
- [ ] `check_round_recorded.py` run and every reported gap attributed (or explicitly deferred to the owning track) before new work
- [ ] Live peers (not just dead orphans) checked via `ps`/session listing before any shared file was written or a commit considered
- [ ] Orphaned artifacts listed and attributed; backlog items re-marked from the tree
- [ ] Orphaned processes killed (argv+cwd confirmed orphan, not a live peer or misread `ppid==1`); `uptime` near idle before measurements
- [ ] Dead session's predictions scored from artifacts
- [ ] Every component's suite run, results in the round entry
- [ ] Inheritance written into the record before new work; own stub appended
