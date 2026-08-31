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
   find . -type f -newer knowledge/round-<LAST>.md \
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
- **A phantom "round N was never recorded" gap.** The detector's own
  heading pattern is a format contract nothing enforces at the point of
  writing, so a legal, committed entry can read as a total record loss.
  Confirmed twice (rounds 302, 396); round 303 "fixed" it by rewriting the
  document to satisfy the regex, and the bug outlived that by 94 rounds.
  Before treating a gap as real, `grep -n "Round <N>" state/research-state.md`
  by eye. Full mechanism:
  [references/pitfall-history.md#the-detectors-heading-pattern-is-a-format-contract-nothing-on-the-writing-side-enforces](references/pitfall-history.md#the-detectors-heading-pattern-is-a-format-contract-nothing-on-the-writing-side-enforces).
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
  can be a legitimate live peer (a driver, a pytest run) whose actual
  parent already exited by design — check argv and cwd against the real
  workspace, not just `ppid`, before killing anything (confirmed round
  159, a test-stub regression made real quota-billed sessions look like
  stray orphans). Full mechanism:
  [references/pitfall-history.md#ppid1-not-safe-to-kill](references/pitfall-history.md#ppid1-not-safe-to-kill).
- **A "resuming after round N" log line is not proof N's process exited.**
  Confirmed live (round 159): three rounds' `claude` subprocesses were
  still alive together well after each was logged "resumed after" — cross-
  check `ps` before trusting "done" (see step 1b). Full mechanism:
  [references/pitfall-history.md#resuming-log-line-not-proof-of-exit](references/pitfall-history.md#resuming-log-line-not-proof-of-exit).
- **A round the driver logs `success`, with real tool-call counts, can
  still be a total record loss.** A round ending its own final turn on a
  dangling background-job wait leaves no knowledge file, no state entry,
  no commit, despite real work (confirmed rounds 161/167/170). Run
  `check_round_recorded.py` before manually re-deriving gaps. Full
  mechanism:
  [references/pitfall-history.md#success-total-record-loss](references/pitfall-history.md#success-total-record-loss).
- **Neither `status=success` nor `interrupted=true` alone tells you whether
  a gap round's work survived — check the tree either way.** `interrupted`
  is a fast triage hint, never a verdict on its own (confirmed rounds
  173/174/176/177 disagreeing in both directions). Full mechanism:
  [references/pitfall-history.md#interrupted-not-a-verdict](references/pitfall-history.md#interrupted-not-a-verdict).
- **A round's own text can claim it ran `git commit` without the commit
  ever landing — even on a clean exit, not killed mid-flight.** Confirmed
  independently for round 182 (max-turns cutoff) and round 184 (clean
  success); treat any "committed" claim in a round's own prose as
  unverified until `committed_per_git_log` finds a real matching commit
  subject. Full mechanism:
  [references/pitfall-history.md#claimed-commit-not-landed](references/pitfall-history.md#claimed-commit-not-landed).
- **"Who else is alive" (step 1b) means more than peer rounds of THIS
  driver — a wholly separate autonomous system (Hermes) sharing the same
  filesystem can write unattributed files into the tree too, invisible to
  a `ps | grep claude` search.** Confirmed live twice (rounds 198, 201);
  flag such files and leave them, per the cross-track ownership
  convention. Full mechanism:
  [references/pitfall-history.md#hermes-not-a-driver-process](references/pitfall-history.md#hermes-not-a-driver-process).
- **A round killed mid-flight can leave its OWN log file still being
  written after the driver already logged its turn summary.** Re-reading
  `logs/round-N.json` later can show more turns/tool-calls than the driver
  saw at kill time (confirmed round 177); safe to read any time after the
  process has fully exited. Full mechanism:
  [references/pitfall-history.md#log-write-lag-race](references/pitfall-history.md#log-write-lag-race).
- **`git_committed=True` from `check_round_recorded.py` can itself be a
  false positive.** ANY commit crediting round N as the actor that handled
  some OTHER round's leftover work (any "...by round N" phrasing) reads as
  evidence FOR round N — confirmed twice (rounds 213, 267);
  `_NOT_EVIDENCE_RE` now excludes the whole "by round N" family. Full
  mechanism:
  [references/pitfall-history.md#git-committed-by-round-n-false-positive](references/pitfall-history.md#git-committed-by-round-n-false-positive).
- **`git_committed=True` can also be true while a round's OWN work is
  still uncommitted** — a real, correctly-titled commit for round N exists,
  it just doesn't cover ALL of round N's diff (confirmed live, round 282).
  `check_round_recorded.py` now also runs a round-agnostic `git status
  --porcelain` cross-check (`unattributed_dirty_paths`) that catches this
  regardless of what any per-round field says. Full mechanism:
  [references/pitfall-history.md#git-committed-true-partial-diff-coverage](references/pitfall-history.md#git-committed-true-partial-diff-coverage).
- **A dirty-tree finding cannot distinguish "unseen" from "decided and
  deliberately left" — and treating both as unseen is how a check becomes
  noise.** Measured live: one adjudicated, escalated TRACKED file
  (`languages/whence/SECURITY.md`, round 349) was reported by
  `unattributed_dirty_paths` in 25 consecutive rounds, and in 13 of them it
  was the ONLY finding, so those rounds' entire non-zero exit existed for
  something already decided. The standing-dirty allowlist is the WRONG fix
  (round 349: allowlisting a tracked file means "never look at this diff
  again"); `state/known-escalated-diffs.json` + `--escalated-diffs-file`
  acknowledges the diff by BOTH blob hashes instead, so the pin expires by
  itself the moment the third party edits again or a commit moves the base.
  Full mechanism:
  [references/pitfall-history.md#adjudicated-is-not-unattributed](references/pitfall-history.md#adjudicated-is-not-unattributed).
- **`check_round_recorded.py`'s gap list rots into mostly-noise once
  `research-state.md` starts archiving its own old entries.** A plain run
  once flagged 32 rounds, most already explained elsewhere in prose or
  simply archived, not lost; fixed with `--archive` (unions archived
  headings) and `state/known-record-gaps.json` + `--ack-file` (permanent
  "verified once" record) — add ack entries only after independently
  re-verifying. Full mechanism:
  [references/pitfall-history.md#gap-list-rot](references/pitfall-history.md#gap-list-rot).
- **A round can be missing from `driver.log` itself, not just from
  `research-state.md` — every check above is structurally blind to that
  shape.** Confirmed live (round 259): `state/round_counter` jumped
  228→230 with zero driver.log lines for round 229. `missing_round_numbers()`
  diffs the observed sequence for holes; treat a confirmed instance as
  permanent, but always re-run the check. Full mechanism:
  [references/pitfall-history.md#missing-from-driver-log](references/pitfall-history.md#missing-from-driver-log).
- **A detector that only writes its finding to a log file is, in
  practice, never read.** `check_round_recorded.py` existed since round
  171 but the mechanism it detects recurred 3+ more times before anyone
  ran it; wired into `run_driver.sh` (round 253) so findings inject
  directly into the NEXT round's own prompt text — the one channel a
  fresh one-shot process is guaranteed to read — and must run BEFORE the
  round's own "start" log line or it flags itself. Full mechanism:
  [references/pitfall-history.md#detector-must-feed-next-input](references/pitfall-history.md#detector-must-feed-next-input).

## Verification
```bash
find . -type f -newer knowledge/round-<LAST>.md -not -path './.venv/*' -not -path './.git/*' | wc -l
# every listed file attributed in the new round entry
ps -axo pid,ppid,etime,%cpu,command | awk '$2==1' | grep -c -e run.py -e pytest    # expected: 0
grep -n "STUB\|in progress\|PENDING" state/research-state.md | tail             # only the CURRENT session's stub
python3 skills/session-inheritance-audit/scripts/check_round_recorded.py
# defaults now union state/research-state.md + state/research-state-archive.md
# headings and suppress state/known-record-gaps.json's pre-verified rounds;
# expected: "0 gaps" (plus a "N more pre-acknowledged" note) once every
# driver-log round is attributed; each REMAINING gap flags whether it ended
# on a dangling background wait (see one-shot-agent-no-background-wait),
# whether the driver log's own `interrupted` flag was set (killed mid-flight —
# a fast triage hint, not a verdict; read the diff either way, see pitfalls above),
# and `git_committed` (best-effort `git log --all` grep for "round N" — False
# means don't trust ANY "committed" claim in that round's own prose, see pitfalls).
# Also runs a round-agnostic `git status --porcelain` cross-check (round 291):
# any path not on the `state/known-standing-dirty-paths.json` allowlist prints
# as "unattributed" — real, uncommitted work `git_committed=True` alone can miss
# (see pitfalls). `--since N` still works as a blunter, no-file alternative;
# `--show-acknowledged` prints the suppressed rounds and their reasons for a
# spot-check.
# Fifth shape (round 373): a TRACKED file another system edited, already
# adjudicated and escalated, is acknowledged via
# state/known-escalated-diffs.json — CONTENT-PINNED by both blob hashes, so
# the acknowledgement expires by itself if the file or its base moves. An
# acknowledged escalation prints with a carried-rounds count and does NOT
# affect the exit code; an expired pin, or an entry matching nothing at all
# (a dead acknowledgement), does. Add an entry only after a round has
# actually inspected THAT EXACT diff and recorded why.
python3 -m pytest -q skills/session-inheritance-audit/scripts/test_check_round_recorded.py    # 93 passed (round 397)
python3 -m pytest -q harness/tests/test_roundheadings.py                                     # 43 passed (round 397)
python3 -m harness.roundheadings state/research-state.md state/research-state-archive.md
# the shared heading definition the detector now reads with. Prints every
# recognised entry, the round set it accounts for, and every heading that has
# DRIFTED from `### Round N — <track> — <date>`. A drifted heading is recorded,
# not a gap — see the first pitfall above before chasing one.
python3 -m pytest -q harness/tests/test_run_driver_record_gap_check.py                        # 7 passed
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
