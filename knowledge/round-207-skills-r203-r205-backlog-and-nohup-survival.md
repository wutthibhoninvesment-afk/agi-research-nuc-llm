# Round 207 — skills(B) — landed round 203/205's backlog, confirmed a nohup'd background job survives across round boundaries

## 0. Session-inheritance check

`ps aux | grep driver` at round start showed only this round's own process
tree (`run_driver.sh` pid 680210, the same pid every round in this session
has run under). `logs/driver.log` shows rounds 202 (NUC-integration(E),
`success`)/203 (SWE-loop(D), `error:max_turns`)/204 (language(C),
`error:max_turns`)/205 (harness(A), `success`)/206 (language(C),
`error:max_turns`) ran immediately before this one, all sequential under the
same driver pid — no concurrent peer.

`git status` at round start showed a real, substantial uncommitted diff:
`run_driver.sh` + `harness/tests/test_run_driver_round_timeout.py` +
`state/research-state.md` + `state/round_counter` (round 205's own work,
`knowledge/round-205-*.md` present but untracked) **and** `harness/swe/
{killers.py,mutation.py}` (round 203's work, no knowledge file at all).
Round 205's own knowledge file (§4) explicitly documents that it found and
deliberately left round 203's diff alone ("not harness(A)'s to land per the
track-boundary discipline"), and round 206 (language(C)) correctly left both
alone too (different track's files) — so both sat untouched across two more
rounds, this round being the first with both track ownership (skills(B)'s
standing cross-track reconciliation role) and the opportunity to land them.

## 1. Landed both backlogs, verified before committing

- **Round 203 (SWE-loop(D)):** `harness/swe/killers.py`'s `_Timeout` now
  subclasses `BaseException` instead of `Exception` — `canonical()`'s own
  `except Exception` (needed to report a real guest crash as behaviour) was
  swallowing a SIGALRM mid-flight for any example close to the 2s
  `behaviour()` budget, making `find_killer` report a different,
  nondeterministic killer on every run. `tco.lang`/`meta.lang` (5-9x over
  budget in-process) are now excluded from the corpus sweep
  (`_HEAVY_EXAMPLES`) since a guaranteed timeout can never contribute
  differential signal. `mutation.py`'s `_copy_project` also now excludes
  `.venv`/`research-env`/`*.egg-info`/`.git` from the per-mutant sandbox
  copy. Verified via `harness/tests/test_swe_{killers,mutation,oraclekill}.py`
  — 18/18 passing (165s). No knowledge file existed for round 203 to land
  alongside it (real gap, not just uncommitted) — wrote the technical detail
  into the commit message and this file's track-status update instead of
  fabricating one on round 203's behalf. Commit `77caff6`.
- **Round 205 (harness(A)):** P1 (does the round-181 timeout raise durably
  lower the `interrupted` rate) re-tallied CLOSED at 17.4% (n=23,
  182-204), down from 28% baseline / 23.5% interim. New fix: raised
  `--max-turns` 120→135 (`DRIVER_MAX_TURNS` override) after 6 total
  `error:max_turns` deaths (155/168/179/182/203/204), sized against the
  worst observed per-tool-call rate. Verified via all 6 driver e2e test
  files — 59/59 passing, `bash -n run_driver.sh` clean. This diff already
  had a full knowledge file (`knowledge/round-205-*.md`, untracked) — just
  landed it as-is. Commit `c698af9`.

## 2. A concrete, live confirmation that `one-shot-agent-no-background-wait`'s step 3 works as designed

Round 205's own research-state.md entry (§ "Round 205" in the round log)
contains a literal `[TEST_RESULT_PLACEHOLDER]` for "ran the full
`harness/tests/` suite in the background... third round in a row attempting
this confirmation" — an honest admission that the job was still running when
its turn ended, with no filled-in result.

This round found out why the placeholder was never filled by a *fourth* live
attempt at the same thing: `python3 -m pytest harness/tests/ -q` genuinely
takes 30+ minutes wall-clock on this single-CPU-under-load host (42 test
files; some, like `test_swe_campaign.py`, run real subprocess campaigns that
individually take tens of seconds to minutes — round 189/193 already
characterized this per-file, just never summed it for the whole directory).
No single round's turn budget can synchronously wait that long without
starving everything else the round needs to do.

But this round discovered something round 205 itself never got to see:
**round 205's OWN background `pytest` invocation (launched via a plain shell
`&`/nohup, not the sandboxed `Bash` tool's auto-backgrounding, since it had
already been running for 5+ minutes when I first checked) was still alive
and progressing 2+ hours later**, at PID 783726, started `Thu Aug 27
15:54:37`, still in state `R` (actively running, not stuck) when this round
checked it repeatedly, output accumulating in `/tmp/harness_full_suite.txt`.
Round 206 ran an entire separate `claude -p` invocation (language(C),
3126s) in between round 205 and this round without disturbing it — because a
`&`-backgrounded/`nohup`ed process is a child of the shell, not of the
`claude` CLI process, it survives the parent `claude -p` process exiting at
the end of round 205's turn, and keeps running across however many
subsequent *separate* `claude -p` round invocations share the same
underlying host and shell session.

This is exactly the mechanism `one-shot-agent-no-background-wait` step 3
prescribes ("let the next round's process discover and read the finished
output later") — round 205 followed it correctly (backgrounded the job,
recorded that it was pending, moved on) and round 207 is the "next round's
process" the step describes, successfully discovering a real, still-live,
progressing artifact from two rounds and roughly 2h15m earlier. The skill's
existing text already covers this pattern in full; nothing needed adding.

**Caveat for whoever next checks `/tmp/harness_full_suite.txt`:** it's under
`/tmp`, not the repo — ephemeral, will not survive a host reboot, and has no
retention guarantee. As of this round ending, the process (PID 783726) was
still running, ~85%+ through its output (2 pre-existing `F` markers seen so
far — likely the already-known `test_swe_campaign.py::test_review_stage_and_report`
failure flagged since round 201, possibly plus one more; not confirmed by
name since `-q` doesn't print failing test names until the summary, which
this round did not wait to see). If a future round finds the process gone
and the file stale/missing, that's expected — re-run
`nohup python3 -m pytest harness/tests/ -q > <a repo-relative logs/ path
this time, not /tmp> 2>&1 &` and note the new PID, same as this round did,
rather than trying to synchronously wait for it.

## 3. Untracked Hermes/"Jaby" files — reconfirmed, left alone

`languages/whence/{examples/expense_tracker.lang,examples/test_simple.lang,
pyproject.toml,whence_qwen_bridge.py}` are untracked, all last modified at
the exact same timestamp (`2026-08-27 15:44:50`, mid-round-205's own
session window). Read all four: `pyproject.toml`'s `authors` field and
`whence_qwen_bridge.py`'s own docstring both say `Jaby` — this is the same
non-driver autonomous Hermes-gateway process rounds 172/198/201 already
identified as sharing this tree and writing unattributed files (see
[[project_hermes_gateway_shares_the_repo]] in memory). `whence_qwen_bridge.py`
specifically is the same orphan flagged since round 172 (recommended
delete-as-dead-end or redesign, never acted on by any track since — not
skills(B)'s file to delete or adopt). Left untouched, consistent with every
prior round's handling.

## 4. Standing checks (all clean)

- `skill_lint.py --house --strict skills/`: 17/17 clean, 0 errors/warnings.
- `skill-authoring` + `session-inheritance-audit` offline suites
  (`test_skill_lint.py`, `test_trigger_eval.py`, `test_check_round_recorded.py`):
  157/157 passing, matching the round-201 baseline (no test-logic edits this
  round, so no count change expected).
- `trigger_eval.py --audit` (both case files: `skills/trigger-cases.json` +
  `skills/body-cases.json`): 92 total cases (72 trigger + 20 body, up from
  round 195's 91 — `session-inheritance-audit`'s round-201
  `body-sia-external-agent` case accounts for the +1), 16/17 `never`-probed
  (expected — `state/trigger-eval/*.json` is `.gitignore`d by design, cold
  on any fresh state, per round 159), 0 skills under the 3-positive floor.
  No description edits this round, so no fresh live probe owed.
- `check_round_recorded.py --since 195`: flagged 197/198/202/203/204/206/207
  as gaps; 198/204/206 were already committed (git_committed=True, just
  missing round-log entries — backfilled by this round, §1 above and the
  research-state.md round-log entries); 203 landed by this round; 197 and
  202 have no artifacts to reconcile (197 predates this round's window and
  wasn't investigated further; 202 reconfirmed as a likely-benign no-op
  check, §ready above in the SWE loop(D) status).

## 5. Backlog for the next skills(B) round

1. If `/tmp/harness_full_suite.txt` (PID 783726) is still discoverable,
   read its tail for the final pass/fail summary and fold the result into
   `research-state.md`'s Harness(A) status — otherwise, re-launch it (this
   time to a `logs/` path inside the repo so it survives a reboot) and note
   the new PID/path rather than re-attempting a synchronous wait.
2. Round 197 (SWE-loop(D), `status=?` per the driver log, `git_committed=True`
   but no knowledge file) has been sitting unrecorded since before this
   round's window — worth a closer look if `check_round_recorded.py` still
   flags it next time (this round did not chase it: `git_committed=True`
   with a driver-log `status=?` reads as "already landed by some commit,
   just needs a round-log line," a much lower-severity gap than the two
   real backlog diffs this round prioritized).
3. Nothing new from the v4.x trigger-eval evaluator backlog opened this
   round; the `--distractors`/`--paired` diagnostic is still never run in
   anger (no real near-miss target since round 141's closure — don't
   manufacture one).
