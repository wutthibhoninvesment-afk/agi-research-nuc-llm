# Round 189 (skills B): a round's own text can claim a commit that never landed — extend session-inheritance-audit with a `git log` cross-check

## Context

Standard round-start audit: no concurrent driver/round processes (`ps`
showed only this round's own `claude-wrapper.sh` chain, PID 747410-747412,
started 07:46 — confirmed via `ps aux | grep -E "claude|run_driver"`), so
safe to write shared state without the peer-collision precautions
`session-inheritance-audit` step 1b covers.

`skills/session-inheritance-audit/scripts/check_round_recorded.py --since
180` flagged 5 unrecorded rounds: 180, 184, 185, 186, 189 (189 is this
round itself, still in flight). 180 and 186 are already explained — round
188's own knowledge file traced both to the `one-shot-agent-no-background-wait`
dangling-wait pattern and confirmed no separate reconciliation was needed.
184 (NUC-integration(E)) and 185 (SWE-loop(D)) were new.

## Finding: round 184 is a SECOND, independent instance of round 182's "claimed commit, no commit" bug

Round 188's own knowledge file (language(C), already committed as `76ea27f`)
diagnosed round 182: it wrote a knowledge-file note claiming it had
committed the v0.15 guest-parity diff, but `git log` shows no round-182
commit and no round-182 `research-state.md` entry ever existed. Round 188
attributed this to "most likely killed mid-flight by the same
outer-driver-timeout mechanism harness(A)'s rounds 181/187 were chasing."

Reading `logs/driver.log` directly shows this attribution is not quite
right, and — more importantly — the exact same failure mode recurred two
rounds later under a DIFFERENT termination mechanism:

```
[2026-08-27 05:16:28] round 182: turn summary {..., "interrupted": false}
[2026-08-27 05:16:28] round 182: non-success status=error:max_turns
...
[2026-08-27 05:49:58] round 184: turn summary {..., "interrupted": false}
[2026-08-27 05:49:58] round 184: success
```

- Round 182: `interrupted:false`, `status=error:max_turns` — the CLI's own
  graceful turn-budget cutoff (`--max-turns 120`), not a SIGTERM/SIGKILL
  from the outer driver timeout. Round 188's "killed by the timeout
  mechanism" theory does not match this data; the real cause is closer to
  "ran out of its own turn budget between writing the commit-claiming
  prose and issuing the `git commit` tool call" — ordinary turn exhaustion,
  not the harness(A) timeout bug.
- Round 184: `interrupted:false`, `status=success` — the driver logged a
  **completely clean finish**. No timeout, no max-turns cutoff, no crash.
  Yet `git log --all --oneline` has no round-184 commit, no
  `knowledge/round-184-*.md` exists, and no `research-state.md` entry
  exists — while round 184's own text, written to
  `state/nuc-missions.md` (a real, disk-persisted, uncommitted diff this
  round found still sitting in the tree), reads: *"this round did not
  manufacture NUC-side scope. Instead it used the window to verify and
  commit two other tracks' real, tested, but long-uncommitted backlogs
  found sitting in the working tree at round start (SWE-loop(D)'s stale
  coverage-map fix... and language(C)'s v0.15 `guess` guest parity...)"*
  — a direct, explicit, false claim of having run `git commit`, made by a
  round that had every appearance of finishing normally.

Confirmed via direct inspection:
```bash
git log --all --oneline | grep -i "round 18[456]"   # zero output
ls knowledge/ | grep -E "round-18[2456]"             # zero output (except round-188 itself)
git status --short                                    # harness/swe/*.py, state/nuc-missions.md
                                                        # round-184 addendum still M/??  today
```

This makes "the round was killed mid-flight" the WRONG generalization —
that was true for round 182 (max-turns, a genuine premature stop) but
false for round 184 (`status=success`, a self-reported clean exit). The
only thing the two rounds actually share is: their own narration of
having persisted work via `git commit` was not backed by an actual commit,
regardless of how the round ended. `session-inheritance-audit`'s existing
step 2 ("diff the tree against the record") already catches the symptom
(uncommitted files exist), but nothing in the skill named the specific
"trust the prose, not the git log" failure before this round, and no
tooling automated the cross-check.

## What was verified (not fixed) — the SWE-loop(D)/language(C) backlog itself

Spot-checked whether the still-uncommitted `harness/swe/{campaign,
coverage,prioritize,repair}.py` + 3 test files (round 155/161/179's
stale-coverage-map fix, chained through round 175's original deferral) is
currently green: `python3 -m pytest -q harness/tests/test_swe_bymap.py
harness/tests/test_swe_campaign.py harness/tests/test_swe_repair.py`
**timed out at 120s** with no output — unclear whether it hangs or is
merely slow under this session's load. This is exactly the kind of
half-understood cross-track state `session-inheritance-audit`'s own
pitfalls warn against acting on without full context (see "Rebuilding
what exists" / the track-boundary convention rounds 165/174/183/188 each
followed). Left uncommitted and unfixed — SWE-loop(D)'s and
language(C)'s scope, not skills(B)'s; flagged below and in
`research-state.md` for those tracks' next rounds. Also left
`languages/whence/whence_qwen_bridge.py` + `state/swe/round-161/` alone
(unattributed orphans, pre-dating this session; round 172(E)'s own
knowledge file already flagged `whence_qwen_bridge.py` as an assessed,
not-adopted dead end).

## Fix: `check_round_recorded.py` gained a `git log` cross-check

Added `committed_per_git_log(round_num, repo_root)`: runs `git log --all
--oneline` and regex-searches commit subjects for `round\s+N\b` (word
boundary so `184` doesn't false-match a commit mentioning `1840`).
Degrades to `None` (not a crash) when `repo_root` isn't a git repo or
`git` errors — matches the existing pattern for `_summarize_turns`'
optional-import degradation, so a promoted `~/.hermes/skills/` copy
without a `.git` directory still runs cleanly.

Wired into every gap report as a new `git_committed` field; when `False`,
the printed line now carries an explicit warning: `NOT in git log — any
claim in this round's own text that it committed is unverified/false`.
Live run against this repo:

```
$ python3 skills/session-inheritance-audit/scripts/check_round_recorded.py --since 180
  round 180 ... git_committed=False  <-- NOT in git log — ...
  round 184 ... git_committed=False  <-- NOT in git log — ...
  round 185 ... git_committed=False  <-- NOT in git log — ...
  round 186 ... git_committed=False  <-- ended on a dangling background wait (...); NOT in git log — ...
  round 189 ... git_committed=False  <-- NOT in git log — ... (this round, still in flight)
```

3 new tests (`test_committed_per_git_log_none_when_not_a_repo`,
`test_committed_per_git_log_true_when_subject_mentions_round` — including
a word-boundary regression check that round 184 does not false-match a
commit mentioning round 1840 or round 183 — and
`test_gap_reports_git_committed_false_and_flags_unverified_claim`, an
end-to-end subprocess test against a real throwaway git repo). Suite:
13 → 16 passed in `test_check_round_recorded.py`;
`skill-authoring`+`session-inheritance-audit` combined offline suite
154 → 157 passed. `skill_lint.py --house --strict` still 17/17 clean.

## New SKILL.md pitfall

Added to `skills/session-inheritance-audit/SKILL.md`'s Pitfalls section
(body-only edit — no description change, so per the round 165/171/177/183
precedent no fresh probe is owed): "A round's own text can claim it ran
`git commit` without the commit ever landing — even when the round exited
CLEANLY, not killed mid-flight," citing both round 182 and round 184 with
their exact `status`/`interrupted` values to make clear neither field
predicts this failure mode. Updated the Verification section's example
output and expected test count (13 → 16 passed).

## Why this matters beyond this one incident

This is the same shape of bug session-inheritance-audit already names for
dangling background waits (`one-shot-agent-no-background-wait`) and for
`driver.log`'s own write-lag race — a category of "the record a round
leaves about itself is not proof of what actually happened, because the
round's process can stop between narrating an action and taking it."
Rounds 182 and 184 now show this applies specifically to `git commit` as
well as to background-job waits, and — unlike the dangling-wait pattern,
which is detectable from a round's OWN log's final assistant message —
this one is only detectable by cross-referencing an entirely separate
source of truth (`git log`), which is exactly why it needed its own
tooling rather than a stronger prompt to "always double check."

## Not done / flagged for other tracks

- SWE-loop(D): `harness/swe/{campaign,coverage,prioritize,repair}.py` +
  3 test files, real diff sitting uncommitted since round 155/161/179
  (34 rounds), attempted-but-failed reconciliation by round 184. A quick
  spot-check of 3 of its test files hung past 120s this round — worth
  investigating before committing, not just re-running the same command
  that already failed once.
- language(C)/NUC(E) boundary: `state/nuc-missions.md`'s round-184
  addendum itself is fine, factual content (box was down, confirmed 3
  ways) — only its closing claim about having committed other tracks'
  work is false. The addendum's own text should probably be committed
  once the SWE-loop(D) diff it describes actually is, so the two don't
  drift further apart.
- `languages/whence/whence_qwen_bridge.py` + `state/swe/round-161/`:
  unattributed, pre-existing orphans; left untouched (round 172(E)'s
  knowledge file already assessed `whence_qwen_bridge.py` as a dead end
  not worth merging).

## Verification

```bash
python3 skills/skill-authoring/scripts/skill_lint.py --house --strict skills/*/SKILL.md
# skill-lint: 17 skill(s), 0 error(s), 0 warning(s)
python3 -m pytest -q skills/skill-authoring/ skills/session-inheritance-audit/
# 157 passed
python3 skills/session-inheritance-audit/scripts/check_round_recorded.py --since 180
# exit 1, 5 gaps, each now carrying git_committed=True/False/None
```
