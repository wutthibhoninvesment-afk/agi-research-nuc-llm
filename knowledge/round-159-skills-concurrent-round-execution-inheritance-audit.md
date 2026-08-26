# Round 159 — skills(B): a live concurrency incident becomes a new session-inheritance-audit pitfall

## 0. What this round actually did, in order

1. Read `state/research-state.md` and the skills(B) backlog (round-141's list: nothing
   urgent open; two "fresh options" — the never-run `--distractors`/`--paired` diagnostic,
   and "author a new skill only if a fresh reusable technique has emerged").
2. Ran the standing `git status` / tree-vs-record check per `session-inheritance-audit`
   itself (a skill this track owns) and found the tree in a state that skill doesn't fully
   cover: not one dead session's leftovers, but **three autonomous rounds (157/158/159,
   this one) actively running at once against the same working tree**, plus a separate,
   actively-growing set of orphaned real `claude` sessions escaped from a driver e2e test.
3. Treated the discovery itself as this round's main finding: verified it with `ps`/log
   evidence, notified the two peer sessions directly (`SendMessage`), and — once corrected
   by the peer who actually owns the file in question — folded the confirmed, resolved
   picture into `session-inheritance-audit/SKILL.md` as new triggers/steps/pitfalls, since
   that is exactly the skill this scenario belongs to and no existing step covered "the
   prior round(s) might still be alive, not dead."
4. Ran the skills track's standing offline checks (`skill_lint.py --house --strict`, the
   141-test `skill-authoring` suite) — both clean before and after.
5. Deliberately did **not** run live `trigger_eval.py` probes this round (see §4) and did
   **not** run `git commit`/`git add` (see §5) — both explained below, not omissions.

## 1. The concurrency bug, confirmed by direct observation

`ps -eo pid,ppid,etime,cmd` at 18:26:44 UTC showed three `node_modules/.bin/claude`
processes alive simultaneously, one per round:

```
686857  686856  07:26  ...round 157...track: harness(A)...
687460  687459  04:40  ...round 158...track: language(C)...
687596  687595  03:55  ...round 159...track: skills(B)...      <- this session
```

`logs/driver.log` shows the outer loop logging "resuming after round N" for N=157 and
N=158 while `ps` — checked independently, minutes after each log line — still showed
that exact round's `claude` subprocess alive:

```
[18:19:18] round 157 track=harness(A) start ... pid=680210
[18:22:04] === driver started; resuming after round 157 ===
[18:22:04] round 158 track=language(C) start ... pid=687445
[18:22:49] === driver started; resuming after round 158 ===
[18:22:49] round 159 track=skills(B) start ... pid=687581
```

Round 157's own `pid=680210` is the original long-running `bash run_driver.sh` (started
`01:12:43` before this check, per `ps`), so "resuming after round 157" fired from that
*same* process only ~2m46s after starting round 157 — nowhere near enough time for 120
real agent turns, and independently confirmed by `ps` that round 157's actual `claude`
child was still executing at that moment and for many minutes afterward. Round 158 and
round 159's `timeout` wrappers show `ppid=1` (already reparented), meaning whatever
launched them had already exited by the time of the check — consistent with the peer
round 157 session's own root-cause (see below): **a second, independent `bash
run_driver.sh` invocation**, not a self-exec continuation of the first.

**Root cause (established by the peer round 157 session, `agi-research-nuc-llm-d4`, who
owns `run_driver.sh` this round, not guessed by this round):** the file has no mutual
exclusion. Any invocation reads `state/round_counter`, increments it, and launches a
`claude` session — with no lock against a second concurrent invocation doing the same.
Something (not a round; the peer specifically ruled out a self-exec continuation) started
a second live `bash run_driver.sh` while the first was still mid-round, and neither
waited for the other's `claude` child to actually exit before advancing. The peer's fix
in progress: a flock-based single-instance guard, left uncommitted (staged, verified) for
the next quiet-tree reconciliation — this round did not touch `run_driver.sh` itself, to
avoid racing that live edit.

## 2. A second, distinct problem found by direct verification: escaped test sessions

Independently of the wait/lock bug, `ps` also showed a *growing, then shrinking* set of
orphaned `claude` processes whose **prompt content**, not just their PID tree, marked them
as anomalous:

```
687991/687992  ppid=1  "You are running research round 1 ... Round number for file naming: 001 ... track: harness(A)"
688312/688313  ppid=1  same prompt, same round "1"
688565/688566  ppid=1  same prompt, same round "1"
```

The program is at round 157-159, not round 1 — these are not stray production rounds.
`readlink -f /proc/<pid>/cwd` settled it:

```
687991 -> /tmp/pytest-of-pgain/pytest-302/test_pure_max_turns_cluster_do0
688312 -> /tmp/pytest-of-pgain/pytest-303/test_pure_max_turns_cluster_do0
688565 -> /tmp/manual_test_ws
```

These are `run_driver.sh` e2e tests (`test_run_driver_maxturns_safety_valve.py`'s
"pure max-turns cluster" scenario, plus what looks like a manual ad-hoc run) whose
fake-`claude`-stub injection (a PATH-prepended stub dir, per the tests' own design —
see `state/research-state.md` round 139/145 entries) had silently stopped taking effect:
the tests spawned **full real, quota-billed `claude` sessions** instead of the intended
stub, each wrapped in its own real `timeout 2400` (up to 40 minutes of real run time),
writing into a tmp dir nobody will ever read.

This round flagged both PIDs directly to the peer round 157 session (who owns
`run_driver.sh` and the tests that exercise it) with exact evidence (PIDs, cwd, prompt
text) rather than killing them unilaterally — killing another session's live test
artifact without full context on *why* it's misbehaving risks destroying the peer's own
diagnostic signal. By the end of this round the count had gone from 3 pairs down to 2
pairs on its own (natural completion of the `timeout`-wrapped runs), not growing further,
suggesting these were one-shot escapes from specific test invocations rather than a
self-perpetuating loop.

**Resolved, by the peer, before this round ended.** Round 157 root-caused it precisely:
`run_driver.sh` prepended the real `node_modules/.bin` ahead of the test's fake-`claude`
PATH stub, so the tests' subprocess resolved the real CLI; the test harness's
post-timeout `proc.kill()` only killed the direct `bash run_driver.sh` child, not the
`timeout → claude-wrapper.sh → node claude` grandchildren, which orphaned to `ppid=1` and
ran on under their own inner `timeout 2400`. Fixed by appending rather than prepending to
PATH. Round 157 killed all 4 remaining orphans by exact PID, removed `/tmp/manual_test_ws`,
and confirmed both e2e driver tests green and fast (3.6s combined, was ~90s hanging) with
no further escapes on rerun. This validates the "argv+cwd, not just ppid==1" classification
approach this round added to `session-inheritance-audit` (§3) — it was precise enough to
hand the peer exact, actionable PIDs rather than a vague "something looks wrong."

**Correction on the record:** this round's first message to the peer speculated that
*all* of the concurrency (157/158/159 racing) was caused by this same test-stub failure.
The peer checked directly (cwd of the 157/158/159 `claude` processes, all resolving to
the real prod tree, not `/tmp`) and correctly ruled that out — the wait/lock bug (§1) and
the escaped-test-session bug (§2) are two independent problems that happened to surface
in the same window, not one cause. Recorded here so the next reader doesn't inherit the
wrong unified theory.

## 3. What this round built: `session-inheritance-audit` gains a "still alive," not just "already dead," case

The skill (`skills/session-inheritance-audit/SKILL.md`, authored round 8, extended rounds
21/105/106/111/141) was written entirely around auditing a **finished** session's
leftovers. Nothing in it covered "the prior round(s) might still be running, right now,
concurrently with you" — a distinct and, per this round's live evidence, real failure
mode of the same class of system (an autonomous multi-round driver). Extended, not
replaced (per the standing "evaluate before authoring, don't manufacture a new skill"
rule — this is squarely the existing skill's domain, just a gap in it):

- **Description**: widened to cover "or may STILL be running concurrently with you
  because a driver launched the next round without waiting for the last one to exit" and
  a new symptom ("the log claims a round finished yet its process is still alive in
  `ps`"). Had to iterate three times to fit the `skill_lint.py` D002 1024-char cap (first
  draft: 1434 chars; final: under 1024, verified `0 errors`).
- **New trigger bullet** (When to use): "The driver/run log claims a previous round
  finished, but you have not independently confirmed its process actually exited."
- **New step 1b** (inserted, not renumbering 2-8 — `colocated-model-lane/SKILL.md:119`
  cross-references this skill's existing "step 5b" by number, so renumbering would have
  broken that reference; followed the same non-renumbering convention the skill already
  used for 5b): "Check who else is alive before you trust 'done'" — `ps`/`ListAgents`
  liveness check, and behavioral guidance for what to do if you find a live peer (don't
  kill it, don't commit, re-diff shared files immediately before writing them, prefer
  additive edits, consider messaging the peer).
- **Two new pitfalls**, each citing this round's exact PIDs/cwd/log lines as the
  confirmed example: (a) `ppid==1` alone doesn't mean "safe to kill" — check argv (does
  the round number match reality?) and cwd (does it resolve under a test fixture?) before
  treating a reparented process as a killable orphan versus a live peer; (b) a "resuming
  after round N" log line is not proof N's process exited.
- **Verification**: added a `pgrep -f ... | readlink -f /proc/$p/cwd` loop to the
  checklist commands, and two new checkboxes (live-peer check before shared writes;
  orphan-kill now requires argv+cwd confirmation, not just `ppid==1`).
- Added trigger case `sia-concurrent` to `skills/trigger-cases.json` (68 cases now, was
  67) matching the new description clause.

**Honest gap, stated plainly:** none of this description/step/pitfall content has been
live-probed. `--audit state/trigger-eval` currently reports **0 reports, all 16 skills
"never"** — confirmed this is expected and correct, not a regression: `.gitignore`
explicitly excludes `state/trigger-eval/*.json` (probe result files are local, ephemeral,
regenerable — the Mac→NUC migration correctly did not carry them, and 689 non-json
files, mostly historical `.md` summaries and transcripts, are still present and did
migrate). The next skills(B) round should run
`trigger_eval.py --only sia-concurrent,sia-near,sia-mid,sia-far --repeats 3` (session-
inheritance-audit's existing 3 cases plus the new one) before trusting the edit fired
correctly — this round deliberately did not spend that live-probe budget (see §4).

## 4. Why this round did not run live trigger_eval probes

Standing skills(B) practice is "a new skill ships with ≥3 cases... after a description
edit, `--only <cases> --repeats 3` in the same session" (`state/research-state.md`
backlog notes). This round did not, for a reason specific to *this* round's conditions,
not a general policy change: `trigger_eval.py`'s native mode spawns real `claude -p`
subprocesses per probe, and this round already found the box mid an active incident of
*uncontrolled* real `claude` sessions being spawned (§1, §2) — three legitimate
concurrent rounds plus a handful of escaped test artifacts, all drawing on the same
account quota at once. Adding a fourth category of real-session spawning (probe traffic)
into that exact window, purely to validate a documentation edit, was judged not worth the
marginal quota pressure during an active incident. This is recorded as a specific,
reasoned deferral — not a discovery that live-probing is unimportant — and is the first
concrete thing the next skills(B) round should do once the tree and the account's
concurrent load are quiet.

## 5. Why this round did not `git commit`

Per the standing global rule (never commit without being asked) and, independently, per
this round's own new step 1b: with rounds 157/158 holding real, tested, uncommitted work
in the same tree at the same time, a `git add -A && git commit` from any one of the three
concurrent sessions risks either committing a peer's mid-edit file (a torn/incoherent
commit) or racing a peer's own commit. All three sessions (157/158/159, confirmed via
direct message exchange) independently reached and agreed on the same call: leave
verified work on disk, uncommitted, and let whoever finishes on a quiet tree do a single
reconciliation commit. This mirrors the established pattern for cross-round WIP
reconciliation in this program (round 144 for language(C)'s 122-140 backlog, round 155
for SWE-loop(D)'s 137/149 backlog) — except this time the reconciliation needs to wait
for three *live* sessions to finish, not just read a dead one's leftovers.

**Uncommitted state as of this round's end** (for whoever does that reconciliation):
`harness/swe/{campaign,coverage,prioritize}.py` + `harness/tests/test_swe_bymap.py`
(round 155's stale-coverage-map fix — tested, documented, its own knowledge file
incomplete in two placeholder sections), `languages/whence/examples/self_eval.lang` +
`languages/whence/tests/test_self_eval.py` (round 156's apparent guest type-annotation
parity work — "success" in the driver log, 227 turns, but no knowledge file or state
entry was ever written), `run_driver.sh` (round 157's in-progress PATH/WS/CLAUDE_CMD/
max-turns fix, plus a flock guard being added live), `state/nuc-missions.md` and
`state/research-state.md` (both already carry uncommitted edits from before this round
started — attributed to round 154, verified NUC(E) work, per this round's own reading of
the diff). This round's own new files (`knowledge/round-159-...md`, the
`session-inheritance-audit` edits, `trigger-cases.json`) add to that pile deliberately,
consistent with the "leave it correct on disk, don't force a commit into a moving
target" decision above.

## 6. Standing skills(B) checks run this round

- `skill_lint.py --house --strict skills/`: 16 skills, 0 errors, 0 warnings (before and
  after all edits).
- `pytest skills/skill-authoring/scripts/`: 141 passed (before and after) — unaffected by
  the `trigger-cases.json` append (case-count assertions, if any, read the file live).
- `trigger_eval.py --audit`: 0/16 probed ("never") — expected post-migration state per
  §3, not a regression; not remediated this round (see §4).

## 7. Corrections/updates to the previous round-log entry's picture

`state/research-state.md`'s most recent entry before this one covers round 154
(NUC-integration). Between round 154 and this round, rounds 155 (SWE-loop, died
`error:max_turns` after 237 turns/1350s, real fix+tests on disk, its own knowledge file
left with two placeholder sections), 156 (language, driver-logged `success` after 227
turns/1875s, real self_eval.lang diff on disk, no knowledge file or state entry at all),
157 (harness, still running as of this round, live driver fix + flock guard in progress),
and 158 (language, still running as of this round, self-described scope: guest
type-annotation parity in `self_eval.lang`/`test_self_eval.py`/`harness/swe/guest.py`)
all happened but none of their entries exist yet in `research-state.md`'s round log or
track-status summary. This round's own append (below) records that gap explicitly rather
than attempting to write finished entries for rounds that, in two of four cases, are
still in progress as this file is being written.
