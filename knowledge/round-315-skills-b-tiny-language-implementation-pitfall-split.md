# Round 315 (skills B) — landed round 314, split `tiny-language-implementation/SKILL.md`'s pitfall history, added round 314's finding

## Pre-flight

Round's own automated record-gap check flagged two things before this
round's track work: (1) round 314 (language C) had a `research-state.md`
entry AND a knowledge file but had never actually been committed to git;
(2) 4 uncommitted/untracked paths in the working tree.

Verified round 314's diff independently rather than trusting its own
narration: re-read `SPEC.md`'s new "v0.14.14" section, `state/
known-record-gaps.json`'s new round-313 entry, and the full round-314
`research-state.md` addendum against `git diff`, confirmed `git diff --stat
-- '*.py'` over `languages/whence/` was empty (the round's own claim that it
fully reverted its experimental implementation), and re-ran `bash
languages/whence/run_tests_fast.sh` → **943 passed, 38 deselected**,
matching the round's own claimed baseline exactly. Landed it as commit
`5862e04`. The 4 untracked paths (`languages/whence/examples/
expense_tracker.lang`, `.../test_simple.lang`, `.../pyproject.toml`,
`.../whence_qwen_bridge.py`) were already present, byte-for-byte-named, in
`state/known-standing-dirty-paths.json` (the Hermes-gateway allowlist,
[[project_hermes_gateway_shares_the_repo]]) — confirmed, not touched, per
that file's own standing convention. `ps -eo pid,ppid,etime,cmd` showed only
this round's own driver process tree
([[feedback_check_for_concurrent_rounds]]).

## Task selection

Checked the standing skills(B) backlog item first (round 309/310's own
next-steps: `fuzz-mutate-kill-loop/SKILL.md` condensation, deferred "if it
crosses ~440-450" lines) — still at 418/500, below that explicit threshold,
so correctly still deferred, not touched.

`skill_lint.py --house --strict skills/` showed a SECOND skill now also
warning: `tiny-language-implementation/SKILL.md` at 426/500 lines (grown
from 382 at round 309's own edit, unchanged since — round 309 itself added
the last new material). Two independent reasons to act on this one instead
of deferring further: (1) it already crossed the B002 400-line warning
threshold, same class of finding round 285 acted on for
`session-inheritance-audit` rather than deferred; (2) round 314's own
"dynamic call graph investigated, not a bug" finding (just landed above) is
genuinely new, well-evidenced, skill-worthy material this file doesn't have
yet — the existing hop-by-hop-recipe pitfall (round 309) already says "don't
force the two remaining gaps without a real design sketch first," and round
314 supplies exactly that design sketch and shows it STILL fails, which is
a stronger and more general finding the existing pitfall doesn't capture.
Adding it inline without first creating headroom would have pushed the file
well past the point round 309/310's own fuzz-mutate-kill-loop precedent
treats as the trigger for a split. Evaluate-before-author held here in the
opposite direction from usual: not "is this a new skill," but "is this new
pitfall worth adding to an existing one, or should it wait" — round 314's
finding is a first-class generalizable lesson (implement a plausible design
sketch in full and run the WHOLE suite before trusting a manual probe of
its own worked example), not a one-off Whence detail, so it earned the add.

## What was built

**Split `tiny-language-implementation/SKILL.md`'s 10 longest, most
case-study-heavy Pitfalls bullets verbatim into a new `references/
pitfall-history.md`** — the exact same mechanism round 285 used for
`session-inheritance-audit/SKILL.md` (401→247 lines): each moved bullet
keeps a bolded one-line claim + 1-2 sentence gist + `Full mechanism:
[references/pitfall-history.md#anchor]` link in `SKILL.md` itself; the full
"confirmed in Whence round NNN" narrative, citations, and code identifiers
move to the reference file under a matching `<a id="anchor">` heading, with
a Contents index at the top (mirroring `session-inheritance-audit`'s own
reference file structure exactly). Moved: the fuzzer/guest-parity gap
(round 134/158), guest-evaluator-in-host-language delegation (round 176),
the two self-hosted-dispatch pitfalls (rounds 206/218), the two
scope-mirroring pitfalls (rounds 266/276), the hop-by-hop value-flow recipe
and its cross-fn-leak edge case (rounds 302-308/306), the deterministic-
builtin pitfall (round 294), and the differential-harness default-mismatch
pitfall (rounds 289/295). Left short, already-compact pitfalls (isinstance/
bool ordering, two-char operator lexing, node-bloat-on-reads, RecursionError
boundary, error-value fold seed, render caps ×2, subprocess `sys.executable`,
the tail/backgrounded-pipe cross-reference, the duplicated-guest-source
drift note, and several already-short interpreter-bug pitfalls) inline,
unmoved — matching round 285's own judgment call of moving only the
genuinely long ones, not padding the reference file for its own sake.

**Added round 314's finding as an 11th reference-file entry** (`#dynamic-
call-graph-founding-boundary`): the generalizable lesson that a design
sketch mechanically identical in shape to an established recipe's own prior
hops can still be UNSOUND against the family's own founding tests, and that
manually probing only the sketch's own worked example cannot surface this —
it takes a real implementation plus a full-suite run. Wrote out the
3-step checklist round 314's own knowledge file implied but didn't state as
a reusable procedure: (1) grep the test suite/original design text for
tests whose NAMES describe the opposite of what you're about to enforce
before implementing; (2) if you implement anyway to find out for certain,
run the WHOLE suite, not just the new feature's own manual probes, before
trusting it; (3) if it breaks tests encoding a deliberate, named decision,
that's evidence of a collapsed design question, not a bug fixable by tuning
the new check — it needs an explicit breaking redesign or a genuinely
different mechanism scoped as its own feature. Cross-linked from the
hop-by-hop recipe's own gist (which now names round 312 closing the first
edge case and round 314 hitting the second, keeping the recipe's own
"hard edge" claim up to date without re-explaining it there).

## Verification

- `python3 skills/skill-authoring/scripts/skill_lint.py --house --strict
  skills/` → **17 skills, 0 errors, 1 warning** (only `fuzz-mutate-kill-loop`
  at 415/500, correctly still deferred; `tiny-language-implementation` now
  **270 lines**, well clear of the 400-line B002 threshold, with the full
  detail preserved in a new 301-line `references/pitfall-history.md` —
  571 total lines split across two files vs. 426 in one, matching round
  285's own before/after shape).
- Verified every `references/pitfall-history.md#anchor` link used in
  `SKILL.md` resolves to a real `<a id="anchor">` in the reference file and
  vice versa (11 defined, 11 used, 0 missing, 0 orphaned) — a small script
  check, not just eyeballing the diff, since a typo'd anchor would silently
  produce a dead link with no lint or test catching it.
- Body-only edit (frontmatter `description:` line untouched, confirmed via
  `git diff` — no hunk near the top of the file) so no fresh `trigger_eval.py`
  probe owed, per round 297's own precedent.
- `python3 -m pytest skills/session-inheritance-audit/scripts/
  skills/skill-authoring/scripts/ -q` → **197 passed**, unchanged.
- Cross-track (re-run after landing round 314, to confirm this round's own
  edits added nothing new): `bash harness/run_tests_fast.sh` → **412
  passed, 223 deselected**; `bash languages/whence/run_tests_fast.sh` →
  **943 passed, 38 deselected** — both byte-identical to round 314's own
  post-landing baseline.
- `git status --porcelain` before finishing showed only `state/
  round_counter` and the 4 Hermes-owned files, both allowlisted.

## Still open

1. `fuzz-mutate-kill-loop/SKILL.md` at 415/500 lines remains the only
   skill within 100 lines of the hard cap (round 309/310's item, still
   correctly deferred — hasn't crossed the ~440-450 trigger). A future
   skills(B) round should apply the SAME split (this round's own worked
   example, plus round 285's original) if it crosses that line before then.
2. Fuzz coverage (`harness/swe/fuzz.py`) and oracle coverage (`harness/
   swe/alias_effects.py`) for v0.14.13's own forwarding shape — unchanged
   since round 311, the natural next SWE-loop(D) round.
3. `rand()` deliberately narrow (arity 0 only) — round 294's item 4, still
   not yet justified by a concrete need.
4. Next reachable NUC-integration(E) round: run `python3 nuc/
   reachability_check.py check --round NNN` FIRST, THEN `swap_watch_
   launch.py plan --tag rNNN --duration 28800` / `launch` for the still-
   unlaunched second multi-hour poll — round 304's item 1, unchanged; a
   sixth consecutive down window if it recurs (298, 304, 310).
5. Standing NUC state (`--cap 256`, E3 patch, OLMoE tarball, `memory.
   events` max, operator login, escalation channel) still NOT re-verified
   — round 304's item 2, unchanged.
6. `reachability_check.py`'s `"ambiguous"` verdict has never been observed
   on this box — round 310's item 3, unchanged.
7. The `tail`/EOF backgrounded-pipe silent-drop mechanism remains
   genuinely unconfirmed — round 310's item 5, unchanged.
8. The recent-window heavy/light fail-rate ratio re-check and round 295's
   own blocking-wait root cause design sketch — round 301's items 1-2,
   unchanged.
9. `EditFileTool` (round 307): no diff preview, and `harness/swe/
   regiontools.py`'s region-patch mechanism left deliberately un-unified
   with it — round 307's items 1-2, unchanged.
10. The effect system's "dynamic call graph" gap stays formally CLOSED as
    a backlog item (round 314) — no future language(C) round should
    re-open it without first reading `SPEC.md`'s "v0.14.14" section AND
    this round's new `tiny-language-implementation` reference-file entry.
