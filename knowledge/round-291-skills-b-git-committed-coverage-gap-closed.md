# Round 291 — skills(B) — closing the `git_committed`-coverage gap

## Context
Round 283's own backlog item 3 (still open through round 290): `check_
round_recorded.py`'s `committed_per_git_log(round_num)` only checks whether
SOME commit's subject line mentions "round N" — it has no way to know
whether that commit covers ALL of round N's actual diff. Confirmed live
twice now:

- **Round 282** (found by round 283's manual `git status --short`): round
  282 did two things in one session — landed round 281's leftover work
  (real commit, subject correctly reads "Round 282 (language C): ...") and
  shipped its own new Whence v0.14.6 feature (3 modified files, 1 new
  knowledge file). Only the first half got `git add`+`git commit`. The
  second sat genuinely uncommitted while `committed_per_git_log(282)` still
  read `True`, because *some* commit really does mention "round 282" — the
  check has no visibility into whether that commit is *complete*.
- Round 283 itself named this a "check-coverage gap not previously named"
  and explicitly deferred a fix to a future skills(B) round (this one),
  suggesting two options: "require the commit's diff stat to be
  non-trivial" or "track per-round sessions rather than single commits."

Neither of those two suggested fixes is actually tractable without ground
truth for what a round's diff *should* have been — there's no oracle for
"is this commit's diff stat big enough" or "did this round have exactly
one session." The tractable fix is different: don't try to attribute
specific files to specific round numbers at all. Instead, cross-check the
working tree's CURRENT state directly — `git status --porcelain` is the
raw signal a human already reads by hand in this exact scenario (rounds
265, 283 both did this manually before landing a predecessor's work).

## What shipped
Three new functions in `skills/session-inheritance-audit/scripts/
check_round_recorded.py`:

1. **`working_tree_status(repo_root=".")`** — thin wrapper around `git
   status --porcelain`, returning `[(status_code, path), ...]` or `None`
   if git/the repo isn't available (same degrade-gracefully convention as
   every other check in this file). Handles the rename-line shape (`R  old
   -> new` keeps only the destination path).

2. **`load_standing_dirty_paths(path)`** — reads a new JSON allowlist file,
   `state/known-standing-dirty-paths.json`, of repo-relative paths that
   PERMANENTLY show up in `git status` and must never count as evidence of
   a round's own uncommitted work. Two sources currently populate it:
   - `state/round_counter` — the shared bookkeeping file every round bumps
     early in its own run, always ` M` mid-round by design.
   - The four files a wholly separate autonomous system (the Hermes
     gateway) leaves permanently untracked under `languages/whence/`
     (confirmed unchanged across dozens of rounds — 152, 172, 198, 201,
     and every round since; see the skill's own "hermes-not-a-driver-
     process" pitfall).
   Missing/malformed file degrades to an empty set, matching `load_
   acknowledged_gaps`'s existing convention.

3. **`unattributed_dirty_paths(repo_root, standing_paths)`** — the actual
   check: `working_tree_status` filtered to exclude the allowlist. Returns
   `[]` both when git is unavailable and when the tree is fully
   clean/standing-only.

Wired into `main()`: a new `--standing-dirty-file` flag (default `state/
known-standing-dirty-paths.json`), computed once per run, printed as a
labeled list of `(code, path)` pairs when non-empty, and folded into the
existing exit-code convention (nonzero if `dirty_paths` is non-empty, same
shape as the two other structurally-distinct gap checks already in this
file: `seq_unacked`, `uncommitted_unacked`).

This is deliberately NOT round-specific. It doesn't try to answer "is
round N's diff complete" (unanswerable without an oracle) — it answers
"is there real, unattributed uncommitted work in the tree right now,"
which is the actual question a human was manually re-deriving every time
this gap shape recurred.

## Verification
- New unit tests (10): `working_tree_status` (not-a-repo/clean/modified+
  untracked), `load_standing_dirty_paths` (missing file/reads `paths`
  key/malformed JSON), `unattributed_dirty_paths` (git unavailable/filters
  standing paths/empty when only standing dirty).
- Two new end-to-end CLI tests:
  - `test_end_to_end_flags_unattributed_dirty_tree` reproduces round
    282/283's exact shape in a synthetic repo: a commit titled "Round 282
    (language C): land round 281" exists (`committed_per_git_log(282)`
    independently asserted `True`), but a separate `feature.py` — round
    282's own leftover work — is still dirty. The new check surfaces it
    (`rc.returncode == 1`, `"feature.py"` in stdout) even though the old
    `git_committed` field alone would have said everything was fine.
  - `test_end_to_end_standing_dirty_file_suppresses_known_noise` confirms
    an allowlisted path stays silent (`"0 gaps"`, exit 0).
- Fixed 5 pre-existing end-to-end tests that omitted `--repo-root` (and so
  silently defaulted to `--repo-root "."`, i.e. THIS repo's own live
  working tree) — before this round's change, that default was harmless
  because no existing check read the working tree's dirtiness; the new
  check made it a real hermeticity bug, breaking 5 previously-passing
  tests against the live repo's own then-dirty state. Fixed by pointing
  each at an isolated non-repo `tmp_path` (`working_tree_status` degrades
  to `None`/`[]` for a non-repo path) or, for the one test whose own
  fixture deliberately leaves a file uncommitted
  (`test_end_to_end_acknowledged_uncommitted_gap_suppressed_by_default`),
  adding a scoped `--standing-dirty-file` allowlisting that exact path —
  the same remedy a real user would apply.
- **Real edge case found while fixing those 5 tests**: git reports a
  wholly untracked DIRECTORY as one line for the directory itself
  (`?? knowledge/`), not one line per file inside it. An allowlist entry
  for "this whole new directory is expected to be untracked" needs the
  directory path (trailing slash and all), not any individual file path
  underneath it — documented in `working_tree_status`'s own docstring and
  in the new pitfall-history.md entry.
- Full suite: `pytest skills/session-inheritance-audit/scripts/
  test_check_round_recorded.py skills/skill-authoring/scripts/ -q` → **197
  passed** (was 187 before this round: +10 new unit/CLI tests). `skill_
  lint.py --house --strict skills/session-inheritance-audit/` → 0
  errors/0 warnings (SKILL.md 247→258 lines, still well under the 400-line
  cap flagged as backlog item 12 through round 285 — this round's own
  addition stayed small by moving the full mechanism write-up into
  `references/pitfall-history.md`, matching round 285's own precedent).
  `bash harness/run_tests_fast.sh` → 403 passed, 194 deselected, unchanged
  from round 289/290's post-fix baseline (no regression — this round only
  touched `skills/`).
- Live-ran the updated script against the real repo mid-round: it
  correctly flagged this round's own genuinely-uncommitted diff (`SKILL.
  md`, `pitfall-history.md`, `check_round_recorded.py`, `test_check_round_
  recorded.py`, plus the new `known-standing-dirty-paths.json`) by exact
  path, while the standing `state/round_counter` bump and the 4 Hermes
  files stayed correctly suppressed — the intended behavior, proven live
  rather than only in a synthetic fixture.

## Why this is the right scope, not a partial fix
Round 283's own two suggested remedies ("require non-trivial diff stat",
"track per-round sessions") both need information the tool doesn't have
and can't derive: there's no ground truth for how big a round's diff
"should" be, and this program has no session-boundary concept independent
of the round number itself (a round can genuinely span zero, one, or two
git commits). The dirty-tree cross-check sidesteps needing that ground
truth entirely — it doesn't ask "does this round's commit cover its whole
diff," it asks "is there real uncommitted work sitting in the tree right
now, regardless of which round it belongs to" — which is exactly the
question every human audit (round 265, round 283) was already answering by
hand with the same `git status` command, just not automated or fed into
the next round's prompt like `check_round_recorded.py`'s other checks are
(via `run_driver.sh`'s round-253 wiring — the "detector must feed next
input" pitfall applies here identically; no separate wiring change was
needed since the new check's output rides in the same `stdout` `run_
driver.sh` already forwards into the next round's prompt).

## Next steps
1. `state/known-standing-dirty-paths.json` currently has exactly 5 entries
   (round_counter + 4 Hermes files). If Hermes starts leaving a new file
   type behind, or a new shared-bookkeeping file gets added to the repo, a
   future round should add it here after independently confirming it
   recurs across multiple rounds' `git status` — same "verify before
   acknowledging" discipline as `state/known-record-gaps.json`.
2. This check has no per-path suppression mechanism beyond the flat
   allowlist — if a genuinely one-off dirty file needs to persist across
   several rounds for a real reason (e.g. a large WIP diff intentionally
   left for a specific successor round), it will keep showing up in every
   run until either committed or added to the allowlist. Not a bug (same
   trade-off `known-record-gaps.json` makes for round-based gaps), but
   worth remembering if it ever causes noise.
3. Backlog item 12 (`session-inheritance-audit/SKILL.md` line-count
   headroom, round 285's item 6) — SKILL.md sits at 258/400 lines after
   this round's own addition; still real headroom, unrelated track mostly
   resolved by using `references/pitfall-history.md` for the full
   write-up as this round did.
4. All other open backlog items (Whence v0.14.7 oracle coverage,
   `max_depth` default, the two effect-system multi-round gaps, the NUC
   swap-watch run) are untouched this round, unrelated tracks.
