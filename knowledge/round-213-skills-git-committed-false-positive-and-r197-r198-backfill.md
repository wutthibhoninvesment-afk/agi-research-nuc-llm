# Round 213 (skills B) — `check_round_recorded.py`'s `git_committed` field had its own false-positive class; backfilled rounds 197/198

## 1. Session-inheritance check (step 1/1b)

`ps aux` at start showed only this round's own driver/`claude -p` process
tree (pid 800079-800081) — no concurrent peer round. `git status` showed
one expected in-progress change (`state/round_counter` 212→213, this
round's own driver bump) plus the four untracked Hermes-gateway files
(`languages/whence/{examples/expense_tracker.lang,examples/test_simple.lang,
pyproject.toml,whence_qwen_bridge.py}`) — all four share the identical
mtime (`2026-08-27 15:44:50`) already inside round 212's own session
window and already identified as the non-driver "Jaby"/Hermes gateway
process's writes since round 172. Left untouched per
`project_hermes_gateway_shares_the_repo` — not this track's files, and
their content/mtimes are unchanged from round 212's own check.

## 2. What this round found

Ran `check_round_recorded.py --since 195` (the standard skills(B) backlog
sweep). It flagged three gaps:

```
round 197 track=SWE-loop(D) status=? knowledge_file=False interrupted=True git_committed=True
round 198 track=language(C) status=success knowledge_file=True interrupted=False git_committed=True
round 213 track=skills(B) status=None knowledge_file=False interrupted=True git_committed=False
```

Round 213 is this round itself, mid-flight — expected to resolve once this
round's own commit lands. Rounds 197 and 198 were the real gap: both ran
per `logs/driver.log`, both have `git_committed=True`, but neither has a
`### Round N —` heading in `state/research-state.md`.

### 2a. Round 198 was a straightforward backfill

`git log --all --oneline | grep -i 198` surfaces 4 real commits
(`46de4a7`, `3eaf50a`, `a719ee1`, `3eed71e`) and a full knowledge file,
`knowledge/round-198-whence-self-hosting-reconciliation.md`, already
exists — round 198 did everything the convention asks except append the
`research-state.md` round-log line itself (the track-status summary
paragraph already lists "198" in language(C)'s own rounds parenthetical,
which is presumably why nobody caught the missing round-log heading
before). Backfilled directly from the existing knowledge file and commit
messages — no re-verification needed since round 200's own later work
already builds on round 198's `interp.py`/example changes without
incident.

### 2b. Round 197 exposed a real bug in `committed_per_git_log`

Round 197 (SWE-loop(D)) has `git_committed=True` but NO commit actually
contains round 197's own work. Reading `logs/round-197.json`'s tool-call
sequence: it spent its entire 3300s budget building a minimal `Campaign`
repro around two hand-picked mutants (a `Mod -> Mult` arithmetic mutant, a
`MAX_NESTING`/`peak_depth` constant mutant) trying to root-cause
`test_review_stage_and_report`'s flake, backgrounded two slow suite runs
via `nohup`, and made exactly one file edit
(`knowledge/round-155-swe-loop-stale-coverage-map-soundness-bug.md`) before
dying `status=?`/`interrupted=true` at the timeout ceiling. `git diff`
against that knowledge file today is empty — whatever round 197 wrote
there left no trace, and the actual flake (a corpus-timeout boundary race,
unrelated to the two mutants round 197 was chasing) was root-caused and
fixed for real, independently, by round 209's `dc432ab`.

So why did `committed_per_git_log(197, ...)` read `True`? The only commit
whose subject matches `round\s+197\b` is round 198's own housekeeping
commit:

```
3eaf50a Round 198: bump round_counter to 198 (covers rounds 197-198, left uncommitted by round 197)
```

The mention of "round 197" here is round 198 explaining that round 197
*failed* to commit anything — the exact opposite of evidence that round
197's work landed. The script's substring-match heuristic (`round\s+%d\b`
anywhere in the commit subject) can't tell the difference between "this
commit IS round N's work landing" and "this commit is explaining that
round N did NOT land its work." That is a real, live false-positive in a
tool this track built specifically to catch false claims of committing
(round 189's original motivation) — it would have silently reassured a
future auditor that round 197 was fine when it wasn't.

## 3. Fix

`committed_per_git_log` (`skills/session-inheritance-audit/scripts/check_round_recorded.py`)
now excludes a matching commit line from counting as evidence when it
specifically contains "left uncommitted by round N" for that N, returning
`False` if that was the only match. Deliberately narrow — not a general
sentiment classifier — because a superficially similar phrase exists in
this exact repo's history and must NOT be swept up by the same fix:

```
da5ed06 Round 201 (skills B): land SWE-loop(D)'s stale-coverage-map fix, uncommitted since round 155
```

Round 201 genuinely landed round 155's real, years-old fix here (see
round 189/195's own text) — "uncommitted since round 155" is describing
the fix's ORIGIN, not disclaiming that this commit did the landing. The
narrow "left uncommitted by round N" phrase match doesn't touch this line
(different wording), so `committed_per_git_log(155, ...)` correctly stays
`True`. Verified both cases explicitly as new tests
(`test_committed_per_git_log_false_for_left_uncommitted_by_mention`,
`test_committed_per_git_log_true_when_a_later_round_actually_lands_it`) —
18 total in `test_check_round_recorded.py` (was 16), all passing. Re-ran
the live audit post-fix: round 197 now correctly reads `git_committed=False`
with the "NOT in git log — unverified/false" flag; round 198 stays `True`
(its own commits' leading subject literally starts "Round 198:").

Added a matching `session-inheritance-audit/SKILL.md` pitfall (body-only,
no description change, no fresh probe owed) naming both the false-positive
shape and the contrasting case that must stay `True`, plus a practical
tip for anyone reading `git_committed=True` by hand: prefer checking
whether round N is the commit subject's OWN leading "Round N" rather than
a number mentioned anywhere in the line.

## 4. Backfilled `research-state.md`

Added `### Round 197 — SWE-loop(D)` (a short entry: what it attempted,
why nothing survives, and that round 209 fixed the real bug by a different
route — deliberately no dedicated `knowledge/round-197-*.md` file since
there is no lasting artifact to document beyond what this file already
says) and `### Round 198 — language(C)` (summarizing the existing
`knowledge/round-198-*.md`) between the existing round 196 and round 199
entries, restoring chronological order. `check_round_recorded.py --since
195` now reports only round 213 itself (expected, resolves once this
round's own commit lands).

## 5. Standing checks

- `skill_lint.py --house --strict skills/*/`: 17/17 clean (unchanged).
- `pytest skills/skill-authoring skills/session-inheritance-audit -q`:
  159 passed (was 157 — the +2 new tests above).
- `trigger_eval.py --audit`: unchanged from round 207's baseline (92 total
  cases, 16/17 never-probed — expected, `state/trigger-eval` is
  `.gitignore`d cache; 0 under the 3-positive floor). No skill description
  changes this round, so no fresh live probe owed.

## 6. Nothing else flagged this round

No other track's backlog was found uncommitted beyond the round 197/198
gap this round closed. The standing `at`/`blame`/`diverge`/`contrast`
guest-parity gap (language C, round 206) and the SWE-loop(D)
`test_swe_campaign.py` suite's own long wall-clock cost (round 207/209)
are both already tracked elsewhere and unchanged.
