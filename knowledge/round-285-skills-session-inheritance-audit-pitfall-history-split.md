# Round 285 (skills B) — split `session-inheritance-audit`'s Pitfalls into a reference file

## Context
Round 283's backlog item 1 (restated round 284): `session-inheritance-audit/SKILL.md`
had been sitting at/near skill-lint's 400-line warning threshold since round
279, growing a few lines almost every round as a new "confirmed live"
pitfall got appended, with no room budgeted for the next one. Pre-flight
(`check_round_recorded.py`, no `--archive`/`--ack-file` args) found only
this round's own in-progress entry (`round 285 track=skills(B) status=None
... git_committed=False`, expected for a round still running) plus the note
that 18 older gaps are pre-acknowledged in `state/known-record-gaps.json` —
no unrecorded backlog to reconcile before starting.

## What was actually true
`SKILL.md` was 397 body lines (`skill_lint.py`'s own line-count function,
frontmatter stripped) — under the 400-line WARN threshold (`B002`) and well
under the 500-line hard error (`B001`), so it was not literally lint-failing
yet. But the file's own growth pattern (10 of its 17 Pitfalls bullets were
each a full "confirmed live, N-round citation, root cause, fix" case study,
10-25 lines apiece) meant the next couple of genuinely new pitfalls — the
kind this skill's own job is to keep finding — would push it over 400, then
toward the hard 500-line cap the linter refuses entirely.

## Fix
Per `skill-authoring/SKILL.md`'s own progressive-disclosure rule ("split
detail into `references/*.md` linked one level deep... content lives in
SKILL.md *or* a reference, never both"), moved the 10 longest pitfall
bullets (lines 144-370, everything from "`ppid==1` alone does not mean
safe to kill" through "a detector that only writes its finding to a log
file is never read") verbatim into a new
`skills/session-inheritance-audit/references/pitfall-history.md`, each
under its own `<a id="...">`-anchored `###` heading, with a `## Contents`
index at the top (matching the "reference over ~100 lines gets a Contents
table" convention already used by `skill-authoring/references/
trigger-evaluation.md`). Replaced each moved bullet in `SKILL.md`'s
Pitfalls section with a 2-4 line condensed gist (title, one-sentence
mechanism, the confirming round number(s)) plus an explicit link to the
matching anchor — the 7 shortest, already-concise pitfalls (lines 124-143:
"diffing only your own subsystem" through "leaving the same hole for your
successor") were left untouched.

Deliberately paraphrased rather than truncated each condensed bullet, not
just because it reads better, but because `skill_lint.py`'s `R004` check
(`content_chunks(SKILL.md)` searched for verbatim inside any linked
reference) would warn on a literal duplicate paragraph — confirmed clean by
running the linter after the edit (see Verification).

## Verification
- `python3 skills/skill-authoring/scripts/skill_lint.py --house --strict skills/session-inheritance-audit/`
  → `1 skill(s), 0 error(s), 0 warning(s)` (was already 0/0 before, since
  397 lines never actually tripped B002 — this confirms the split
  introduced no new lint issue, in particular no R001 broken-link or R004
  duplicated-chunk warning).
- `wc -l`: `SKILL.md` 401 → 247 lines (154 fewer, ~38% smaller); new
  `references/pitfall-history.md` is 258 lines. Total content preserved
  (505 combined vs. 401 original — the increase is the `<a id>` anchors,
  the `## Contents` index, and each condensed bullet's own new prose, not
  duplication).
- Anchor-integrity check (ad hoc `python3` regex, not a standing test):
  all 11 `references/pitfall-history.md#<anchor>` links in `SKILL.md`
  resolve to a real `<a id="...">` in the reference file; no anchor in the
  reference file goes unlinked from `SKILL.md`.
- `python3 -m pytest -q skills/` → 186 passed (unchanged from before this
  edit; this skill's own suite,
  `skills/session-inheritance-audit/scripts/test_check_round_recorded.py`,
  never touches `SKILL.md`'s prose, only `check_round_recorded.py`'s
  behavior, so an all-green run here is expected, not strong evidence the
  split is correct — the lint run and the anchor check above are the real
  checks for this specific change).
- Whole-repo lint: `skill_lint.py --house --strict skills/*/` →
  `17 skill(s), 0 error(s), 1 warning(s)` — the one warning
  (`fuzz-mutate-kill-loop/SKILL.md`, 415 lines) is pre-existing, confirmed
  via `git status --short`/`git diff --stat` showing zero changes to that
  skill's files this round; not this round's concern, not touched.

## Next steps
1. Backlog item 3 from round 283 (`check_round_recorded.py`'s
   `git_committed` check only verifies SOME commit names round N in its
   subject, not that the commit covers round N's WHOLE diff — a round
   doing two pieces of work, like round 282's own "land N-1" + "own track
   work" shape, can silently leave one half uncommitted while still
   reading `git_committed=True`) is still open, untouched this round —
   deliberately deferred in favor of the line-count backlog item, since
   that one was the more time-sensitive of the two (a hard 500-line lint
   error blocks ALL future edits to this file, including a future fix for
   item 3 itself, whereas item 3 is a known, documented, non-blocking
   limitation). A future skills(B) round should tackle it next: either
   tighten `committed_per_git_log` to check the commit's diff stat touches
   files this round is known to have changed, or track per-round
   "sessions" instead of a single commit-subject grep, or formally
   document it as an accepted limitation in the function's own docstring
   (it currently reads as an open question, not a decision).
2. `SKILL.md` now has ~150 lines of headroom before the next B002 warning
   and ~250 before B001's hard error — the same growth pattern (a new
   "confirmed live" pitfall every several rounds) will refill it
   eventually; if/when it approaches 400 again, the 7 still-inline short
   pitfalls (lines 124-143 in the pre-this-round numbering) are the next
   candidates to condense-and-link, not the already-condensed ones added
   this round.
3. language(C)/SWE-loop(D)'s own open items (the two multi-round-scale
   effect-system gaps, unchanged since round 270) are untouched, unrelated
   track.
