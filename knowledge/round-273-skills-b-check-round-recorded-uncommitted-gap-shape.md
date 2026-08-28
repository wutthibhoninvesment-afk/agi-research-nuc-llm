# Round 273 (skills B) — closing the third `check_round_recorded.py` gap shape

## Context

Round 267 found and named, but deliberately did not fix, a third gap shape
that `skills/session-inheritance-audit/scripts/check_round_recorded.py` is
structurally blind to: a round whose research-state.md heading AND
knowledge file both exist (so `main`'s own `if in_state: continue` skips
computing anything else for it) but whose real work never actually landed
in git. Round 266 was the confirmed live instance — its heading and
knowledge file were both written to disk before the round's process
ended, so nothing about the existing checks (missing heading; missing
driver-log line entirely) ever fired for it; round 267 only found the
real, uncommitted diff via a manual `git status` audit. This round
(273) implements the fix round 267's own knowledge file spec'd: "flag
`in_state=True, has_knowledge_file=True` rounds whose `git_committed`
reads `False`, not just rounds missing a heading entirely."

This file is `skills/session-inheritance-audit/scripts/check_round_recorded.py`
itself, and its author is `session-inheritance-audit/SKILL.md` — squarely
this round's own track.

## What shipped

1. **`recorded_but_uncommitted_rounds(driver_rounds, state_rounds,
   knowledge_dir, repo_root, since)`** — new top-level function, same
   testable-unit style as `missing_round_numbers`. For every round with
   BOTH a research-state.md heading and a `knowledge/round-N-*.md` file,
   checks whether that knowledge file itself ever appeared in any commit's
   tree. If none of a round's knowledge files were ever tracked, the round
   number is returned as a gap.

2. **`_file_ever_tracked(path, repo_root)`** / **`_cached_tracked_paths
   (repo_root)`** — the actual git check. Deliberately does NOT reuse
   `committed_per_git_log`'s subject-line-text-match approach.

3. **`main()`** wiring: a third gap category alongside the existing
   "no research-state.md entry" list and the `missing_round_numbers`
   sequence-gap list, same `--ack-file` suppression convention, same
   `--show-acknowledged` printing, folded into the overall exit code.

4. **`committed_per_git_log`** itself got a small, unrelated-but-adjacent
   perf fix while touching this file: its `git log --all --oneline`
   subprocess call is now memoized per `repo_root`
   (`_cached_git_log_lines`), since round 273's new check calls
   git-log-derived functions far more often per run than before.

## The false-positive trap this round found and fixed BEFORE shipping

The very first working draft built `recorded_but_uncommitted_rounds`
directly on top of `committed_per_git_log` — i.e., "flag a recorded round
if no commit subject anywhere mentions `round N`". Running that draft
against the REAL repo (not just synthetic fixtures) surfaced 3 live
"gaps": rounds 154, 160, 162. All three turned out to be false positives,
and each is a distinct sub-shape of the same underlying problem
(subject-line text matching is the wrong signal for "did this SPECIFIC
FILE land"):

- Round 154 and 160's knowledge files were both committed by round 166's
  commit (`c0a65a7`, subject "seventh live window — service restart by the
  actual box operator, warm-up-curve finding, backlog reconciliation") —
  a real, later round's batched reconciliation commit that never mentions
  either round number by digit anywhere in its subject line at all.
- Round 162's knowledge file was committed by round 164's commit
  (`6f56fcc`, subject "...retroactive round-146/162 knowledge files") —
  the round number IS in the subject, but spelled `round-162` (a HYPHEN)
  rather than `round 162` (a space), which `committed_per_git_log`'s own
  `r"round\s+%d\b"` pattern requires and does not match.

Verified each with `git log --oneline --all -- <path>`, which shows the
exact landing commit for all three:
```
$ git log --oneline --all -- knowledge/round-154-nuc-e-fifth-snapshot-swap-plateau-decode-confirmed.md
c0a65a7 Round 166 (NUC-integration E): seventh live window ...
$ git log --oneline --all -- knowledge/round-162-whence-v14-reconciliation-and-effects-fuzzing.md
6f56fcc Round 164 (language C, reconciled by round 168): effects guest parity + retroactive round-146/162 knowledge files
```

This directly validates a pattern already named in `session-inheritance-
audit`'s own pitfalls list for `git_committed=True` false positives (the
"by round N" family, rounds 213/267) — the SAME class of bug (naive
text-matching against commit prose) can bite in the opposite direction too
(false NEGATIVE: a real, safely-landed file reads as missing) once the
matching target changes from "any evidence this round happened" to "prove
THIS SPECIFIC round's artifact is present". The fix: check the artifact's
own presence in git history (`git log --all -- <path>`, or equivalently, a
full `git log --all --name-only` scan checked for membership), which
cannot be fooled by how a later round chose to word its own commit
subject.

## Performance: don't spawn one subprocess per historical round

A second draft of `_file_ever_tracked` called `git log --all --oneline --
<path>` once per candidate round (i.e., once per round with a heading AND
a knowledge file — currently ~250+ and growing forever). Timed against the
real repo: 0.75s baseline (before this round's change) → 4.83s with this
naive per-file-per-round approach. Fixed by replacing it with ONE `git log
--all --name-only --pretty=format:` call, memoized (`_cached_tracked_paths`,
`functools.lru_cache` keyed on `repo_root`), producing a `frozenset` of
every path ever committed; membership checks after that are O(1) in-
process set lookups. Re-timed: back to 0.82s — a single amortized
`git log` call regardless of how many rounds are checked, instead of one
call per round. This keeps the per-round driver overhead (this script runs
once at the START of every round via `run_driver.sh`, see its own comment
block around the `RECORD_CHECK_SCRIPT` invocation) flat as the round count
keeps growing, rather than degrading linearly forever.

## Result against the real repo

```
$ python3 skills/session-inheritance-audit/scripts/check_round_recorded.py --show-acknowledged
... (19 pre-acknowledged rounds + round 229's sequence gap, all pre-existing, unchanged)
check_round_recorded: 1 round(s) ran per the driver log with NO research-state.md entry (18 more pre-acknowledged, ...):
  round 273 track=skills(B) status=None knowledge_file=False interrupted=True git_committed=False  <-- ...
```

Zero new "recorded but uncommitted" gaps in the real 152-273 history once
the false-positive-prone subject-text-matching draft was replaced with
file-presence checking — i.e., round 266 (the confirmed live instance that
motivated this whole check) is ALREADY reconciled (round 267 landed its
real diff for real, see research-state.md's round-267 entry), so this
round's new check correctly reports it clean. The only thing flagged is
round 273 itself, which is expected and transient (this round's own
research-state.md heading doesn't exist yet at the moment this command was
run mid-round) — the same documented behavior
`test_real_repo_acknowledges_round_229_sequence_gap` already covers for
the sequence-gap check.

## Tests

`skills/session-inheritance-audit/scripts/test_check_round_recorded.py`:
34 → **45 passed** (11 new): `recorded_but_uncommitted_rounds` (flags a
genuinely uncommitted file; clean when the file IS committed under an
UNRELATED subject line, directly encoding the round-154/160/162 lesson;
ignores a round with no knowledge file; skips rather than false-flags when
git itself is unavailable), `_file_ever_tracked` (True/False/None), two
new end-to-end CLI tests (flags the gap; suppresses it via `--ack-file`
and shows it via `--show-acknowledged`), and a `_cached_git_log_lines`
memoization regression test (stale-until-`cache_clear()`, proving the
subprocess really isn't re-run). Also ran the adjacent
`harness/tests/test_run_driver_record_gap_check.py` (3 passed, unchanged)
since it exercises this script end-to-end via a copy of the real driver
wiring.

## SKILL.md — deliberately NOT touched beyond one number

`session-inheritance-audit/SKILL.md` sat at 399/400 lines per round 267's
own note (confirmed still 399 at this round's start). Per that round's
explicit warning ("the next non-trivial addition to this specific file
needs to trim or archive an older pitfall FIRST, not append"), this round
did not add a new pitfall bullet for the false-positive trap above even
though it's a genuinely reusable lesson — it lives in this knowledge file
instead. The only SKILL.md edit was updating the Verification section's
test count (34 → 45 passed), a same-line edit that doesn't change the
line count (still 399/400 after this round).

## Backlog

- Item 13 (round 267's own next-steps list) is now CLOSED: the fix it
  spec'd is implemented, tested against synthetic fixtures AND the real
  repo's full history, and the false-positive trap the naive version of
  it would have introduced was caught and fixed before shipping, not
  after.
- Item 14 (round 261's own "first real record-gap, check if it was acted
  on" watch item) is UNCHANGED — still 0 real gaps of the ORIGINAL
  heading-based shape since round 253 shipped that injection. This round's
  new gap shape is a different mechanism (git-presence, not heading-
  presence) and has its own, now-empty history to watch going forward: if
  a future round ever gets `in_state=True, has_knowledge_file=True,
  git_committed=False` flagged for real, whether the in-prompt injection
  (round 253's own mechanism, which surfaces ANY `check_round_recorded.py`
  gap regardless of shape) actually gets acted on is exactly as
  unobserved for this shape as it was for the original one.
- `session-inheritance-audit/SKILL.md`'s 399/400-line ceiling (round 267's
  finding, reconfirmed this round) is now a standing blocker for adding
  ANY new pitfall bullet, not just a one-off note — a future skills(B)
  round should budget time to trim/archive an older pitfall (round 261's
  own precedent: SKILL.md files can move older, less-actionable pitfalls
  to a dedicated reference doc the main file links to) specifically so
  this round's false-positive-trap lesson (and the next one) has somewhere
  to go besides a knowledge file nobody reads without already knowing to
  look.
- Not attempted: auditing the OTHER historical acknowledged-gap entries in
  `state/known-record-gaps.json` for the same "commit subject doesn't
  mention this round, but the file/work DID land" false-positive shape —
  those were all verified via different, mostly-manual methods across
  rounds 231/253/259/267 before this round's `_file_ever_tracked` existed,
  and re-auditing 19 historical entries with the new, more precise tool
  was out of scope for the specific backlog item this round closed. If a
  future round wants extra confidence in the ack file's own correctness,
  `_file_ever_tracked` per knowledge-file path is now available as a
  cheap way to do it against the FULL 152-273 history in well under a
  second (this round's own measurement above).
