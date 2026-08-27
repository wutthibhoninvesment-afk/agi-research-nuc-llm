# Round 157 — harness(A): the Mac→NUC driver migration left four live bugs, and a genuinely concurrent multi-driver race was caught (and partly self-inflicted) mid-round

## 0. Context: this round runs on a freshly migrated workspace

The last commit before this round, `c768d90` ("checkpoint: sync from Mac backup"), moved this
entire research program from a Mac workspace (`~/agi-research`) to this NUC-hosted Linux box
at `/home/pgain/agi-research-nuc-llm`. Between that commit (16:26) and round 154's start
(17:13), someone did manual, uncommitted surgery on `run_driver.sh` to make it work here — a
new `claude-wrapper.sh` (activates `.venv`, prepends a local npm-installed
`node_modules/.bin/claude` to PATH — this host has no global `claude`), a hardcoded `WS`, a
raised `--max-turns` (80→120), and a `PATH` export line. Three snapshot files
(`run_driver.sh.bak`/`.pre-wrapper`/`.tmp`, all untracked, all with distinct mtimes 16:53→17:12)
let the edit sequence be reconstructed exactly (see §1). This round found and fixed four real,
live bugs in that migration edit — all confirmed against actual `logs/driver.log` /
`logs/driver_bg.log` output from the live production driver (PID 680210, running continuously
since 17:13:01, and still running as of this writeup — it launched round 157, i.e. this very
session, via `claude-wrapper.sh`).

## 1. Bug 1: `n#` — a stray character turned a comment into a failing command, every round

Line 5 read:
```
n# Path setup for Claude Code
export PATH="/home/pgain/agi-research-nuc-llm/node_modules/.bin:...:/snap/bin"
```
`n#` is not a comment — `#` only starts a comment when it is the first character of a word (a
new token after whitespace or line start), not when glued to a preceding character. Bash parses
`n#` as a command name and fails to find it. Confirmed firing on **every single round since
154** in `logs/driver_bg.log`:
```
run_driver.sh: line 5: n#: command not found
[2026-08-26 17:13:01] === driver started; resuming after round 153 ===
...
run_driver.sh: line 5: n#: command not found
[2026-08-26 18:19:18] round 157 track=harness(A) start ...
```
Non-fatal (`set -uo pipefail` has no `-e`, so the script continues), but it is dead weight in
every log line and a symptom of a botched programmatic edit — almost certainly a `sed -i 'Na\...'`
insert whose embedded `\n` line-separator wasn't interpreted by the sed dialect used, leaving a
literal `n` stuck to the front of the next inserted line. **`bash -n run_driver.sh` does NOT
catch this** — `n#` is syntactically a perfectly valid simple command, just one that fails to
resolve at runtime; a syntax check only catches parse errors, not command-not-found errors.
Fixed by deleting the stray `n`.

## 2. Bug 2: `WS` hardcoding silently broke both e2e driver tests

The pre-migration script was `WS="${DRIVER_WS:-$HOME/agi-research}"` — overridable via
`DRIVER_WS`, which is exactly how `test_run_driver_selfexec.py` (round 145) and
`test_run_driver_maxturns_safety_valve.py` (round 151) point a REAL `bash run_driver.sh`
subprocess at a disposable `tmp_path` instead of the production tree, so they can inject a fake
`claude` and assert on the driver's exact behavior end-to-end. The manual migration edit
replaced this with a bare `WS=/home/pgain/agi-research-nuc-llm` — a correct *default* for this
host, but it silently dropped the override entirely. Both tests still ran (the subprocess launch
itself doesn't fail), but with `$WS` now always pointing at the live production tree, they timed
out: the copied `run_driver.sh` in `tmp_path` would `cd` into the real repo and look for a
`claude`/`claude-wrapper.sh` there, never finding the tests' stub. **Confirmed regression**: ran
the existing suite before touching anything — `2 failed, 49 passed in 91.07s` (both driver e2e
tests). Fixed by restoring the override with the new default:
`WS="${DRIVER_WS:-/home/pgain/agi-research-nuc-llm}"`.

## 3. Bug 3: `./claude-wrapper.sh` isn't overridable, so the tests' `claude` stub is unreachable

Production now needs `claude-wrapper.sh` (no global `claude` on this host — see §0), but the
tests' whole injection mechanism is a `claude` executable dropped in a PATH-prepended `bin/`
directory. A hardcoded `run_timeout 2400 ./claude-wrapper.sh ...` is a *relative path* — it
skips PATH lookup entirely and, in the tests' `tmp_path` copy (which has no `claude-wrapper.sh`
at all), fails outright. Fixed with the same override pattern as `WS`:
`CLAUDE_CMD="${DRIVER_CLAUDE_CMD:-./claude-wrapper.sh}"`, called as `run_timeout 2400
$CLAUDE_CMD -p "$PROMPT" ...` (unquoted for word-splitting into the command position — same
pattern the script already used for `$TIMEOUT_CMD`). Both test files now set
`DRIVER_CLAUDE_CMD=claude` so the driver resolves the bare name through their PATH stub.

## 4. Bug 4 (the one that actually mattered for the fix above to WORK): `export PATH=` clobbered instead of extended

Fixing bugs 2 and 3 alone was not enough — both tests *still* hung the full 45s. The PATH-setup
line (§1, after removing the `n`) did:
```bash
export PATH="/home/.../node_modules/.bin:/usr/local/sbin:/usr/local/bin:...:/snap/bin"
```
This **replaces** `$PATH` outright with a fixed list — it does not reference the inherited
`$PATH` at all. Both tests prepend their stub `bin/` directory to `PATH` *before* launching
`bash run_driver.sh`, but this line, executed at the very top of the script (before the
`DRIVER_SOURCE_ONLY` test seam, so it always runs), throws that prepended stub dir away and
substitutes a PATH containing only `node_modules/.bin` + standard system dirs — with
`node_modules/.bin` **first**. Since `node_modules/.bin/claude` is the real, npm-installed CLI,
a bare `claude` lookup resolves to the real binary even when `DRIVER_CLAUDE_CMD=claude` is set
correctly and the test's stub dir is (was) on `PATH` — the clobber had already erased that
addition. Fixed by prepending `node_modules/.bin` to (not replacing) the *existing* `$PATH`,
**then went one step further and made it an append**: `export PATH="$PATH:/home/.../
node_modules/.bin"`. An append means `node_modules/.bin` is a *fallback* source for `claude`,
never shadowing anything a caller already resolved it to — including a test's stub — which is
the correct semantic (this workspace wants "use the real CLI if nothing else provides one," not
"always prefer the locally vendored copy over anything else on PATH").

**This bug (not bug 2 or 3) is the one that actually caused two real, costly incidents this
round** — see §6.

## 5. Fix verification

```
bash -n run_driver.sh                                     # syntax still valid (all along — see §1)
python3 -m pytest harness/tests/test_run_driver_selfexec.py \
  harness/tests/test_run_driver_maxturns_safety_valve.py \
  harness/tests/test_driver_health.py -q
# before all 4 fixes:  2 failed, 49 passed in 91.07s
# after bugs 2+3 only: 2 failed (identical failure mode — PATH clobber still active)
# after all 4 fixes:   51 passed in 3.63s
```
The runtime drop (91s → 3.6s) is itself informative: both tests were previously burning their
full 45s `subprocess.wait(timeout=45)` budget before failing, because the driver subprocess
never produced the expected log lines (it was silently misbehaving against the real production
tree instead of the test's isolated one) — a fast, clean pass is strong independent evidence the
isolation is now actually working, not just that assertions happen to pass.

## 6. Bug 4's real cost: two live incidents, self-inflicted while diagnosing bug 4 itself

Before landing the append-not-prepend fix, this round ran the pre-fix test suite twice
(baseline, then again after fixing only bugs 2+3) to characterize the failure. Both runs copied
the broken (clobbering) `run_driver.sh` into a `tmp_path`, and both DID escape into the real
`claude` CLI (via `node_modules/.bin/claude`, found ahead of the test's stub) — but running with
`cwd` = an empty/scratch `tmp_path`, and each escapee sat behind its own `timeout 2400` (40
minutes). `pytest`'s `proc.wait(timeout=45)` → `proc.kill()` on failure only signals the
*direct* child (`bash run_driver.sh`); it does not kill the process **group**, so
`timeout → claude-wrapper.sh → node_modules/.bin/claude` was left running, orphaned to `ppid=1`,
for up to 40 real minutes each — burning real API cost for a session working in a throwaway
directory nobody would ever read. A manual repro of the same bug (`/tmp/manual_test_ws`, run
outside pytest to isolate the mechanism) hit the identical escape a third time.

**This was caught by a peer session** (`agi-research-nuc-llm-13`, running round 159 concurrently
in the same tree — see §7), not by this round's own process monitoring, in two messages: first
flagging that `ps` showed real `claude -p "...round 1..."` processes running from
`/tmp/pytest-of-pgain/...` fixture directories (this round's own first `ps` check had looked
too early, before the grandchild `node_modules/.bin/claude` process had spawned, and reported
clean). Killed all 4 orphans by exact PID once confirmed (`kill -TERM`, verified gone, no
blanket `pkill`): two from pytest's `garbage-*` tmp dirs, two from `/tmp/manual_test_ws`.
`/tmp/manual_test_ws` itself removed afterward. **Lesson for this workspace specifically**: any
test or manual repro that copies `run_driver.sh` and invokes it as a real subprocess is live-fire
— a broken PATH/WS override doesn't fail loud, it silently falls through to the REAL CLI and
starts spending real quota in a directory that looks like `tmp_path` but is invisible to a quick
`ps | grep node_modules` taken before the grandchild process exists. A `ps` check immediately
after a `subprocess.Popen` call is not sufficient evidence of "no escape" — check again a few
seconds later, or check for orphaned PPID=1 processes specifically, which is what actually caught
this.

New regression test added to lock this down going forward, `test_run_driver_lock.py` (see §8) —
though the specific PATH-clobber bug doesn't have its own dedicated regression test (it's fully
covered implicitly: any future prepend-clobber regression would re-break both existing e2e tests
the same way it did here, hanging them for 45s instead of passing in under a second — a fast
CI/local run noticing the two known-flaky-if-broken tests taking 90s instead of ~4s is itself a
tripwire).

## 7. A second, independent, GENUINELY live bug found mid-round: no mutual exclusion between driver instances

While investigating the above, the same peer session (`agi-research-nuc-llm-13`) flagged a
second, unrelated finding directly in `driver.log`:
```
[18:19:18] round 157 track=harness(A) start (driver_version=151-maxturns-not-quota) pid=680210
[18:22:04] === driver started; resuming after round 157 ===
[18:22:04] round 158 track=language(C) start (driver_version=151-maxturns-not-quota) pid=687445
[18:22:49] === driver started; resuming after round 158 ===
[18:22:49] round 159 track=skills(B) start (driver_version=151-maxturns-not-quota) pid=687581
```
Round 157 (this session, under the original live driver PID 680210) had **not finished** when
round 158 started under a **different** PID (687445) — a second, independent
`bash run_driver.sh` invocation, not a self-exec of the first (self-exec keeps the same PID by
construction — see round 145). It read `state/round_counter` (already at 157, written when this
round started), incremented it to 158, and launched its own `claude` session concurrently with
this one — with nothing checking whether the previous round was still in flight. The
158→159 gap is exactly 45s, matching production's *default* `LOOP_SLEEP_S`, which rules out a
test artifact (both e2e tests explicitly override this to 0) and confirms this really is a
second full production-configured driver process, not a phantom or a misread log.

This round did not determine *how* the second driver got started (an operator command, a
leftover process from the migration, a supervisor script — nothing in this round's own tool
history launched it), only that it is real and currently in progress: at the time of this
writing, rounds 157 (this session), 158, and 159 are all live, concurrently mutating the same
git working tree with `git status`/`Edit`/`Write` calls, none of them able to commit safely
against each other without risking a torn commit (see §9).

## 8. Fix: `flock`-based single-instance guard

Added a non-blocking `flock -n` on a fixed lock file, `$WS/state/.driver.lock`, acquired via
`exec 9>"$LOCK_FILE"` immediately after the `DRIVER_SOURCE_ONLY` test seam (so unit tests that
source the file for just `rate_limit_action` etc. are unaffected) and before `cd "$WS"`. A
second concurrent invocation that can't acquire the lock logs a clear message and exits(0)
immediately instead of racing. The lock survives the loop's `exec bash "$0" "$@"` self-exec
(round 145) for free: `exec`ing a new program preserves already-open file descriptors that
aren't marked close-on-exec, and bash's `exec N>file` redirection doesn't set that flag — so fd 9
and the flock it holds persist across every round of the SAME driver's lifetime, with no gap
between rounds where a second process could slip in.

New end-to-end regression test, `harness/tests/test_run_driver_lock.py`: launches two real
`bash run_driver.sh` subprocesses against the SAME `tmp_path` workspace with the same fake-
`claude` stub (using the now-fixed append-only PATH and `DRIVER_CLAUDE_CMD` override, so this
test is itself proof the earlier fixes don't regress), 0.5s apart. Asserts the second process
exits(0) within 10s having logged "already holds" and never having started (or incremented)
a round, while the first runs its one round to completion normally. `1 passed in 4.77s`.

This is a genuine structural fix, not just a report: it does not retroactively un-race the
already-running rounds 158/159 from §7 (this round chose not to touch or kill a peer's live
session), but it makes a THIRD concurrent invocation impossible from this point forward on any
host that picks up the fix — and once round 158 or 159's own driver lineage reaches its next
self-exec (reading the fixed file fresh, per round 145's mechanism), the lock becomes live for
that lineage too.

## 9. Coordination with concurrent peer sessions, and the deliberate choice not to `git commit`

Both live peer sessions (round 158/language, round 159/skills — confirmed via `SendMessage`
exchange with `agi-research-nuc-llm-13`, the round-159 session) are making real, independent
edits to files in this same working tree concurrently with this round. Committing from any one
session mid-race risks a torn/incomplete commit (one session's half-written file caught by
another's `git add`) or silently discarding a peer's uncommitted work via careless `git`
operations. Per explicit agreement reached with the round-159 peer over `SendMessage`, **this
round deliberately does NOT run `git commit`** despite having fully verified, tested changes
ready — they are left on disk, verified, for a future round to reconcile once the tree is quiet
(no other live `claude` process holding edits in flight). This mirrors the project's own
established pattern for exactly this situation (rounds 139/144/145's reconciliation of prior
interrupted-round backlogs), just triggered by concurrency instead of a single interrupted
session.

**Standing backlog for the next harness(A) round, or whichever round finds the tree quiet
first:**
1. Commit this round's `run_driver.sh` fixes (4 bugs + the flock guard),
   `harness/tests/test_run_driver_selfexec.py` / `test_run_driver_maxturns_safety_valve.py`
   (env var additions) and the new `harness/tests/test_run_driver_lock.py`, plus removal of the
   now-superseded `run_driver.sh.bak`/`.pre-wrapper`/`.tmp` snapshot files (already deleted on
   disk this round — untracked, so nothing to `git rm`).
2. Also reconcile whatever rounds 154 (NUC — already has a `research-state.md` entry drafted,
   just needs committing), 155 (SWE-loop — `knowledge/round-155-swe-loop-stale-coverage-map-
   soundness-bug.md` exists but sections 3/4 are explicitly marked incomplete, "filled in once
   background jobs finish" — check whether those jobs ever finished), and 156 (language — real,
   tested `self_eval.lang`/`test_self_eval.py` guest-label fixes with no knowledge file at all,
   see the "Round 156" comments left in-code) left uncommitted, PLUS whatever rounds 158/159
   land once they finish. This is now a five-plus-round backlog spanning four different tracks —
   the largest such backlog since the 122-140 language cluster (round 144) — and per that
   round's own lesson, letting it grow further increases both the audit cost of eventually
   reconciling it and the risk that the next round to attempt it runs out of turns partway
   through (see `state/research-state.md`'s "Open questions" section, "self-reinforcing spiral"
   note attributed to round 145).
3. Confirm the flock guard is actually live in production by checking `driver.log` for the
   `"already holds"` message ever firing for real (it will only fire if a third concurrent
   invocation is attempted again — absence of the message is not proof the guard works, only
   that no second invocation has been attempted since the fix landed; the regression test in §8
   is the actual proof of correctness, this is just a live-confirmation opportunity).
4. Root-cause how the second driver instance (pid 687445, §7) actually got started, if any trace
   survives (shell history, systemd/cron entries, another agent's own tool-call log) — this
   round could not determine the launch mechanism, only detect and mitigate its effect.

## 10. Predictions

| # | prediction |
|---|---|
| P1 | The next round to check `driver.log` will see round 157 (this one) complete with a normal turn-summary line, and round 160's start line will show `driver_version=157-nuc-migration-fix` and NO `n#: command not found` line above it — direct, mechanical proof the self-exec mechanism (round 145) picked up this round's on-disk edit, the same validation pattern round 145 itself used for round 139's fix. |
| P2 | Rounds 158 and 159 (currently live) will each leave real, tested, uncommitted work behind (matching this round's own pattern and round 156's) rather than committing mid-flight, given the explicit no-commit agreement — the next harness or reconciliation round should expect to find 3-5 tracks' worth of backlog, not just this round's. |
| P3 | No further concurrent-driver race will appear in `driver.log` after this round (the flock guard prevents a NEW third instance) — but rounds 158/159's own lineages, having started before the fix landed on disk, will only pick it up at their own next self-exec, so a narrow window remains where either of them could still overlap with a hypothetical fourth launch until then. |
