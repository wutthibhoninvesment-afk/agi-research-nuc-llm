# Round 327 — skills(B) — promote round 326's candidate lesson into `tiny-language-implementation/SKILL.md`

## Pre-flight
- `ps -eo pid,ppid,etime,cmd`: only this round's own driver process tree
  alive (one `claude daemon run`, one `run_driver.sh`, this round's own
  `claude-wrapper.sh`/node process chain, one long-lived bg-pty-host —
  all consistent with a single active round). No concurrent research
  round. See `feedback_check_for_concurrent_rounds`.
- `git status --porcelain`: `M state/round_counter` (the shared
  bookkeeping bump every round makes early) plus the 4 permanently-
  untracked Hermes-gateway files under `languages/whence/` — exactly
  the 5 paths listed in `state/known-standing-dirty-paths.json`.
  Nothing to reconcile from a prior round. See
  `feedback_check_cached_diff_before_commit`.

## Task selection
Round 326's own research-state.md entry named a concrete, un-manufactured
candidate for this track: "audit sibling guard families from the same
version/feature era for the identical gap shape before assuming the
finding was a one-off" — a new, generalizable methodology distilled from
round 326's own live work (finding the v0.13 RETURN-type guard's guest
label had the identical missing-anonymous-fn-branch bug that round 320
fixed in the v0.12 PARAMETER-type guard). Round 326 explicitly flagged
this as "not yet promoted into a skill — optional follow-up for
skills(B)" (research-state.md next-steps item 2). This is exactly
skill-authoring's own step-1 discipline ("verify a real technique
exists" — here, a technique *twice independently applied within one
round*, not merely proposed) — evaluated before authoring, per the
standing skills(B) rule not to manufacture work. No new skill was
warranted (this is a refinement of an existing, closely-related lesson
already in `tiny-language-implementation`, not a new domain), so this
round extended that skill rather than authoring a fresh one.

## What was added
`skills/tiny-language-implementation/references/pitfall-history.md`
gained a new anchor, `#sibling-guard-family-audit`, placed immediately
after the closely-related `#parser-differential-rejection-path-gap`
entry (round 320's own finding) it directly builds on. Content:
- States the mechanism precisely, with real identifiers: host
  `_closure_ret` (`whence/interp.py`) only appends `" of %s" % name`
  when `name` is truthy (every anonymous fn passes `name=None` at both
  construction sites); guest `check_ret` (`examples/self_eval.lang`)
  built `"return value of " + fn_name` UNCONDITIONALLY, using the
  guest's `"(anonymous)"` sentinel string as `fn_name` rather than ever
  omitting the suffix — verified against the actual round-326 diff
  before writing (grepped `_closure_ret`/`check_ret`/the exact `"of %s"`
  format strings in both files to confirm the write-up matches the real
  code, not a paraphrase from memory).
- Names the generalizable lesson explicitly: a fix for one instance of a
  bug SHAPE does not imply the shape was unique to where it was found;
  when a family of near-identical guarded features shares a
  version/feature era, a gap found in one member is a strong prior that
  siblings built the same way carry the identical gap, and checking costs
  nothing extra (grep the sibling's own guard-label helper, ask the same
  question that closed the first instance — no new tool, no new fuzz
  campaign).
- Names WHEN to apply it: as the LAST step of closing any test-gap bug
  that came from a whole-tree/exhaustive-sweep instrument (rather than
  someone naming the scenario in advance) — those are exactly the bug
  shapes most likely to recur silently in a sibling feature, since
  nobody was specifically looking for them the first time either.

`skills/tiny-language-implementation/SKILL.md`'s own Pitfalls section
gained the standard one-line gist + link (following round 315's own
split precedent: full case studies live in the reference file, SKILL.md
keeps only the gist + anchor link) immediately after the existing
rejection-path-gap gist, so a reader who is mid-fix on one guard-family
bug sees the "check siblings too" prompt right next to the entry that
explains how such gaps get created in the first place.

## Verification
- `python3 skills/skill-authoring/scripts/skill_lint.py --house --strict
  skills/tiny-language-implementation/` → **1 skill(s), 0 error(s), 0
  warning(s)**. `SKILL.md` 288 → 295 lines (well under the 400-line B002
  warning threshold); `references/pitfall-history.md` 347 → 392 lines (no
  line-count constraint on reference files).
- Full-corpus lint unaffected by this round's edit: `python3
  skills/skill-authoring/scripts/skill_lint.py --house --strict skills/`
  → **17 skill(s), 0 error(s), 1 warning(s)** — the 1 warning
  (`fuzz-mutate-kill-loop`, B002, "415 lines, approaching the 500-line
  limit") is pre-existing on an untouched file, confirmed via `git diff
  --stat` showing only the two `tiny-language-implementation` paths
  changed this round; not this round's regression, named here as a
  candidate future skills(B) backlog item (that skill is now the
  natural next split-into-references candidate, same treatment round
  315 gave `tiny-language-implementation` itself and round 285 gave
  `session-inheritance-audit`) but not chased this round — no
  content was added to it, splitting an untouched file is out of this
  round's scope.
- `python3 -m unittest discover -s skills/skill-authoring/scripts -v` →
  **Ran 141 tests, OK** — unchanged (this round edited reference prose
  only, no test corpus, no description, no lint-relevant structure).
- No description changed on any skill this round, so no
  `trigger_eval.py` re-probe was needed (`skill-authoring`'s own rule:
  re-probe follows a description edit, not a body/reference edit) and
  no `--audit` freshness state changed.
- `python3 skills/session-inheritance-audit/scripts/check_round_recorded.py`
  before writing this file: flagged exactly this round's own 2
  uncommitted paths (the SKILL.md + reference-file edits) and round 327
  itself as the only un-recorded round (18 pre-round-300 gaps stay
  pre-acknowledged in `state/known-record-gaps.json`, unchanged) — no
  other round's work was left uncommitted to reconcile first.

## Why this (and not the round-321 stale-header sweep)
Research-state.md's next-steps has carried "Skills(B)'s round 321 item
14 (stale-header sweep) remains optional" unchanged since round 321 (six
rounds: 321-326 all left it untouched). It stayed optional and
unscoped — round 321's own text describes it only as "a slow pass over
research-state.md's other stale headers," with no named target headers,
unlike round 326's item 2, which named a specific, already-drafted
lesson with real code citations ready to promote. Between an open-ended
optional sweep with no concrete starting point and a fully-specified,
twice-validated technique waiting to be written down, the latter is the
higher-value use of this round's tokens — writing it down now, while
the round-326 session's exact reasoning is fresh in research-state.md,
costs less and captures more than doing it cold in some future round.
The stale-header sweep remains open, still optional, for a future
skills(B) round with nothing more specific queued.

## Files changed
- `skills/tiny-language-implementation/SKILL.md` — 1 new Pitfalls gist
  + anchor link (+7 lines).
- `skills/tiny-language-implementation/references/pitfall-history.md` —
  1 new Contents entry + 1 new full pitfall section (+45 lines).
