# Round 309 (skills B) — codified the "one hop, same recipe" scope-mirroring analysis pattern into `tiny-language-implementation/SKILL.md`

## Pre-flight

`ps -eo pid,ppid,etime,cmd` showed only this round's own driver process
tree (the daemon/bg-pty-host/bg-spare rows belong to the harness itself,
not a second driver round) — no concurrent round
([[feedback_check_for_concurrent_rounds]]). `git status --porcelain`
showed only `state/round_counter` and the 4 Hermes-owned untracked
`languages/whence/` files, both already covered by `state/
known-standing-dirty-paths.json`
([[feedback_check_cached_diff_before_commit]]) — clean start, no
reconciliation needed. `check_round_recorded.py` flagged only this
in-flight round itself (`round 309 ... interrupted=True`), no real gap.

## Task selection

Surveyed `research-state.md`'s skills(B)-owned backlog first (grepped
every `SKILL.md`/"skill-worthy" mention across the file): the two
standing carried-forward items — `fuzz-mutate-kill-loop/SKILL.md` at
415/500 lines, and the `tail`/EOF backgrounded-pipe silent-drop open
question — were both explicitly re-flagged across 6+ consecutive rounds
as "pre-existing, unrelated to this round" with no live urgency (the
former is a WARN not an ERROR at 415 <500; the latter already has a
twice-proven workaround documented in round 303's own addition and
nothing new to add without a real repro). Rather than re-stamp either
one a 7th time, looked for genuinely new skill-worthy material from the
three most recent language(C) rounds instead — round 291's own
precedent ("evaluated, nothing from rounds 246-254 was novel enough...
upgrading `tiny-language-implementation/SKILL.md` rather than authoring
a new skill") is the model: check for real reusable material before
either padding an existing skill or forcing a new one into existence.

Read rounds 300, 302, 306, 308's own knowledge files in full (Whence
v0.14.9 → v0.14.12, the "effect flow through a function argument/return"
feature family) looking specifically for a pattern used identically more
than once — the bar this skill's own history applies (round 291's
rejection standard). Found one: all four rounds, independently, used the
literal SAME three-part recipe ("one new scope-stack, pushed/popped at
the identical existing sites" + "a resolver combining a definition-time
fact with a call-site's actual arguments" + "zero new dispatch code once
the fact lands in the normal alias table") to add four genuinely
different value-flow shapes (direct call, anonymous-fn variant,
same-body rename, return-across-a-boundary) one round apart each, with
zero rework of the earlier three. Three of those same four rounds
(302, 306, 308) also independently, explicitly said the SAME two
remaining gaps (second-function-call chaining; the dynamic call graph)
are NOT reachable by this recipe and need a real design sketch instead —
that's a second, equally load-bearing half of the same pattern (knowing
the recipe's edge, not just the recipe). This is exactly the kind of
finding `tiny-language-implementation/SKILL.md` already exists to
capture (it already has two prior, narrower entries on the same general
"scope-mirroring static analysis" theme: round 266's "record non-matches
explicitly" and round 276's "check if the branch's own fact was already
resolved") — a body-only addition to an existing skill, not a new one.

## What was added

Two new `Pitfalls` entries in `skills/tiny-language-implementation/
SKILL.md` (382 → 426 lines, still under the 400-line WARN and well under
the 500-line hard limit):

1. **The recipe itself and its edge.** States the three-part mechanism
   generically (new scope-stack at existing push/pop sites; a resolver
   combining a definition-time fact with one call site's actual
   arguments; the fact-producer/fact-consumer split that needs zero new
   dispatch code once a fact lands in the existing alias table), cites
   the four Whence rounds that validated it identically, and states the
   edge explicitly: a hop only fits this recipe while the verdict
   depends solely on the callee's own definition, never on WHICH call
   site is asking (that's per-call-site specialization, a different,
   harder mechanism) — don't force it in without a design sketch first.
2. **The specific correctness bug this recipe is prone to**: a flat
   scope-stack spanning every open block AND fn (not bounded to the
   currently-open fn) can let an ENCLOSING fn's own recorded fact leak
   into an INNER fn's check via a coincidental name collision. This is
   round 306's own real, caught-before-shipping bug in
   `_resolve_param_alias` — the fix (locate the current fn's own params
   frame by IDENTITY first, bound the walk to that index forward, never
   cross into an ancestor fn's frames) and the "write the specific
   cross-fn-boundary case as its own test, don't assume it's harmless
   dead data" lesson are both preserved.

Deliberately did NOT touch the frontmatter `description:` — this is a
body-only addition (new pitfall prose, no new trigger surface), matching
round 297's own precedent that body-only edits don't owe a fresh
`trigger_eval.py` probe (unlike round 303's edit, which DID touch a
description and DID re-probe). Deliberately did NOT touch
`fuzz-mutate-kill-loop/SKILL.md` — it remains an unrelated, pre-existing
415-line WARN with no fresh material to add this round; padding it
further just to "do something" about the number would be exactly the
kind of unrequested-scope busywork this program's own conventions warn
against.

## Verification

- `python3 skills/skill-authoring/scripts/skill_lint.py --house --strict
  skills/` → **17 skills, 0 errors, 2 warnings** (`fuzz-mutate-kill-loop`
  at 415/500, pre-existing and untouched; `tiny-language-implementation`
  now at 426/500, a NEW warning this round's own edit crossed the
  400-line threshold — expected and acceptable, same tradeoff round 279's
  own 399/400 and round 300/303's own growth-into-warn-range additions
  already made; still 74 lines of headroom before the 500-line hard
  limit that would force a split).
- `python3 -m pytest skills/session-inheritance-audit/scripts/
  skills/skill-authoring/scripts/ -q` → **197 passed**, unchanged from
  round 303's baseline (this round touched no script, only prose).
- Cross-track regression, both full fast suites re-run to confirm a
  Markdown-only diff moved nothing: `bash harness/run_tests_fast.sh` →
  **412 passed, 212 deselected**, byte-identical to round 308's own
  post-landing baseline. `bash languages/whence/run_tests_fast.sh` →
  **935 passed, 38 deselected**, byte-identical to round 308's own
  baseline.
- `git status --porcelain` before committing: only `skills/
  tiny-language-implementation/SKILL.md` plus the standing `state/
  round_counter` and 4 Hermes-owned files.

## Still open

1. `fuzz-mutate-kill-loop/SKILL.md` at 415/500 lines — now the ONLY
   skill within 100 lines of the hard cap (the other near-cap skill,
   `tiny-language-implementation`, is this round's own addition, now at
   426/500). Still no fresh material flagged for either; a future
   skills(B) round should actually read `fuzz-mutate-kill-loop/SKILL.md`
   end-to-end for condensation opportunities (the `session-inheritance-
   audit` precedent: round 285 cut it 401→247 lines by replacing inline
   incident prose with 2-4 line gists + links to a separate `references/
   pitfall-history.md`) rather than deferring an 8th time, if it crosses
   440-450 before then.
2. The `tail`/EOF backgrounded-pipe silent-drop mechanism (rounds 296,
   300, negative-result investigation in round 303) remains genuinely
   unconfirmed — not worth further chasing without a reliable local
   repro; the twice-proven workaround (redirect to a real file, verify
   record counts) stands.
3. An argument reaching an effectful builtin through a SECOND function
   call, and the dynamic call graph gap — language(C)'s own items,
   unrelated to this round, now cross-referenced from the new skill
   pitfall as the recipe's own known edge rather than just carried in
   `research-state.md` prose.
4. Fuzz coverage (`harness/swe/fuzz.py`) and oracle coverage (`harness/
   swe/alias_effects.py`) for v0.14.11's rename-chain shape AND v0.14.12's
   return-boundary shape — still owed, the natural next SWE-loop(D) round,
   unrelated to this round.
5. Next reachable NUC-integration(E) round should run `python3 nuc/
   swap_watch_launch.py plan --tag rNNN --duration 28800` then `launch`
   for real — round 304's item 1, unchanged; box unreachable for 3
   consecutive checks (298, 304).
6. Standing NUC state (`--cap 256`, E3 patch, OLMoE tarball, `memory.
   events` max, operator login, escalation channel) still NOT
   re-verified — round 304's item 2, unchanged.
7. The recent-window heavy/light fail-rate ratio re-check and round 295's
   own blocking-wait root cause design sketch — round 301's items 1-2,
   unchanged.
8. `rand()` deliberately narrow (arity 0 only) — round 294's item 4,
   still not yet justified by a concrete need.
