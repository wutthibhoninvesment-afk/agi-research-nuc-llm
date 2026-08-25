---
name: session-inheritance-audit
description: Use when resuming an autonomous coding or research program, a multi-session agent job, or an unattended pipeline after a session crashed, hit a turn or token limit, was rate-limited, or was killed, and the notes or state file may not match what is on disk. Symptoms: the state file says "in progress" but finished result files exist; the run log says success but nothing was produced; load average is high hours after the last run ended; test files or modules nobody remembers writing; unclear which backlog items are already done. Covers diffing the tree against the written record (files newer than the last recorded artifact), killing orphaned processes before measuring, reading completed-but-unread artifacts before planning, scoring the dead session's predictions, running every component's suite, and recording the inheritance before new work. NOT for git-history questions, production-outage post-mortems, or web/login session persistence; if no unattended prior session left state behind, this skill does not apply.
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

**When NOT to use:** a clean hand-off with an accurate record (just read
it); production incident write-ups (that is a post-mortem); anything
where "session" means a login/web session.

## Steps

1. **Read the record, then distrust it.** Read the cumulative state file
   and the last N lines of the driver/run log. Note every entry marked
   stub / in progress / PENDING and every round number with no report
   file. Checkable outcome: a list of "claimed but unverified" items.

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

## Verification
```bash
find . -type f -newer knowledge/round-LAST.md -not -path './.venv/*' -not -path './.git/*' | wc -l
# every listed file attributed in the new round entry
ps -axo pid,ppid,etime,%cpu,command | awk '$2==1' | grep -c -e run.py -e pytest    # expected: 0
grep -n "STUB\|in progress\|PENDING" state/research-state.md | tail             # only the CURRENT session's stub
```
- [ ] Orphaned artifacts listed and attributed; backlog items re-marked from the tree
- [ ] Orphaned processes killed; `uptime` near idle before measurements
- [ ] Dead session's predictions scored from artifacts
- [ ] Every component's suite run, results in the round entry
- [ ] Inheritance written into the record before new work; own stub appended
