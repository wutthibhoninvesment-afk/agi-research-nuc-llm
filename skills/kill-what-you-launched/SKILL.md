---
name: kill-what-you-launched
description: Stop a background run you started and prove it stopped, before deleting anything it was using. Use when a round launches a long suite/benchmark in the background, when a selector-based kill (ps|grep|kill, pkill -f) is about to run, before removing a worktree or temp tree a run may still be in, and when a previous round's processes are found still alive.
---

# Kill what you launched — and prove it

A background run you did not watch stop is still running. On a one-CPU box
it is also taking the next round's CPU, and the result it is still producing
is going somewhere nobody will read.

## When to use this

- You are about to background a suite (`nohup ... &`, `setsid`, `&`).
- You are about to kill something by pattern (`ps | grep | kill`, `pkill -f`).
- You are about to `rm -rf` a worktree, `/tmp` tree, or checkout that a run
  might still be inside.
- A round starts and `uptime` shows load a fresh box should not have.
- You are reading a previous round's write-up that says a suite "did not
  finish" — check whether it finished after the round ended.

## The three failures this prevents

Measured on this repo, round 402 → 403, all three in one round.

1. **A selector that matches nothing exits 0.**
   `ps -eo pid,args | grep '[w]t-402' | awk '{print $1}' | while read p; do
   kill "$p"; done` matched zero processes. The `while` body ran zero times.
   The pipeline succeeded. At the shell level this is byte-identical to
   having killed everything.
2. **argv does not identify a run.** Every suite in this program has the
   same argv (`python3 -m pytest -c pytest.ini -q tests/`). What
   distinguishes runs is **cwd** and **open files** — neither of which `ps
   -o args` shows.
3. **Teardown that does not wait.** The tree was deleted while the run was
   still in it. The suite carried on for twelve minutes, logged 149
   `FileNotFoundError`s, and wrote a completed-looking summary line
   (`112 failed ... in 1676.12s`) that was an artefact of the deletion.

## Steps

1. **Before launching**, choose a durable log path *inside the repo*, not
   `/tmp`, and write that path into the round file in the same edit that
   launches the run. A path recorded only in the driver transcript is a
   path nothing reads.
   ```sh
   LOG=$PWD/state/round-NNN/logs/<suite>.log
   mkdir -p "$(dirname "$LOG")"
   PYTHONDONTWRITEBYTECODE=1 setsid nohup python3 -m pytest -q tests/ > "$LOG" 2>&1 &
   echo "launched pid $! -> $LOG at $(date -u +%H:%M:%S)"
   ```
2. **Record the PID** in the round file next to the path. `$!` is free at
   launch and unrecoverable later.
3. **To find a run, ask where it is, not what it is called:**
   ```sh
   python3 harness/procreap.py scan --under /tmp/wt-NNN
   ```
   `scan` keys on cwd and open files, excludes your own driver→shell
   ancestor chain, and prints each match **with its log path** — recovered
   from `/proc/PID/fd`, which is how you find a log whose path nobody wrote
   down.
4. **To stop it, confirm it stopped:**
   ```sh
   python3 harness/procreap.py reap --under /tmp/wt-NNN   # or --pid N --pid M
   ```
   Verdicts: `stopped` (non-empty request, every pid confirmed gone),
   `survived` (something outlived SIGKILL), `nothing_to_do` (**the request
   was empty — this is not success**).
5. **Before deleting anything:**
   ```sh
   python3 harness/procreap.py guard-rm /tmp/wt-NNN && rm -rf /tmp/wt-NNN
   ```
   Exit 0 = safe, 1 = blocked (it prints who), 2 = inconclusive.
6. **Read the log before you kill.** Copy it somewhere durable *first*. A
   killed process's output is whatever had been flushed, and you get one
   chance at it.

## Pitfalls

- **`cat /proc/PID/fd/1` is not the log.** Under `--capture=fd`, pytest
  `dup()`s the real stdout aside and puts an anonymous `O_TMPFILE` inode on
  fd 1. That inode reads `links=0 size=0 pos=0` and looks like destroyed
  output. The real log is on the dup'd fds. **Always `ls -l /proc/PID/fd/`
  and look at every entry**, not just 1 and 2.
- **`pkill -f <pattern>` matches the shell running it** — the opposite of
  failure 1, and it kills the rest of your compound command (exit 144).
- **A worktree path is not in argv.** `git worktree list` also will not help
  once the directory is gone; `ls -d` and `git worktree list` disagree.
- **Do not report a background run's percentage as its result.** A run at
  "14%, zero failures" can have its first `F` at 33%. If it has not
  finished, say it has not finished and give the path.
- **A fail-closed check whose "unknown" bucket has permanent residents is
  not conservative, it is off.** `scan`'s first version reported
  `INCONCLUSIVE — 116 processes unreadable` for an empty directory. Scope by
  uid, and split "vanished mid-scan" and kernel-`protected` out of
  "unknown", each pinned by a test.

## Recovering a result nobody recorded

If a previous round's process is still alive, its log path is recoverable
and its output may contain findings the round never saw:

```sh
python3 harness/procreap.py scan --under "$PWD"      # log paths, by location
ls -l /proc/<pid>/fd/                                # every fd, not just 1/2
```

`-q` names no failing test, but the position is exact: strip the `[ NN%]`
markers, count progress characters, and index that number into
`pytest --collect-only -q`. Verify the total by checking that **every**
percent marker matches `72k/N`. Round 403 located a real regression this
way, at character 617 of 1942.

## Verification

```sh
python3 -m pytest harness/tests/test_procreap.py -q     # 45 passed
python3 harness/procreap.py scan --no-record            # rc 0 clean / 1 residue
python3 harness/procreap.py status                      # "no recorded scan" if none
```

`harness/run_tests_fast.sh` prints the `scan` line every run, after the
`slowtier` and `pristine_check` status lines.
