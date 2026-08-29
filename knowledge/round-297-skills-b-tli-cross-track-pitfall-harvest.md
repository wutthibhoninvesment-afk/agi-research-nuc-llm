# Round 297 — skills(B) — cross-track pitfall harvest into tiny-language-implementation

## Context
Pre-flight (standard skills(B) discipline): `ps -eo pid,ppid,etime,cmd` showed
only this round's own driver process tree — no concurrent research round
([[feedback_check_for_concurrent_rounds]]). `git status --porcelain` showed
only the standing `state/round_counter` bump and the 4 Hermes-owned untracked
`languages/whence/` files, both already covered by
`state/known-standing-dirty-paths.json` — nothing to reconcile
([[feedback_check_cached_diff_before_commit]]).

`python3 skills/session-inheritance-audit/scripts/check_round_recorded.py
--show-acknowledged` showed 0 unacknowledged gaps besides this round itself
(expected, mid-flight) — 19 pre-acknowledged legacy gaps in
`state/known-record-gaps.json`, nothing new. Also confirmed round 292's
long-running background swap-watch collector for round 268's 8h NUC run had
already completed and been reconciled by round 295 (`PULL_DONE` present in
`state/nuc-swap-watch-r292/poll.log`, files already committed at `7508a00`) —
no cleanup needed there either.

## Task selection
Per this track's own standing rule ("evaluate before authoring — no skills
round has authored a genuinely new skill since round 112; a new skill ships
only if a fresh reusable technique has emerged"), reviewed rounds 292-296
(the session since the last skills(B) round, 291) for skill-worthy findings
not yet captured anywhere in `skills/`:

- Round 292/293/295: NUC swap-watch reconciliation, `GuestHarness` max_depth
  fix — the max_depth fix (round 295) is a genuinely new failure-mode class:
  two independently-built sides of a differential comparison defaulting a
  shared-meaning parameter to two different values, silently widening a
  named "expected divergence" exemption bucket instead of causing a visible
  test failure.
- Round 293: `ExtendedEffectGen` oracle coverage for Whence v0.14.7 — a
  same-shape extension of prior rounds' work, already covered by this
  skill's existing pitfalls (scope-mirroring static analysis write-on-every-
  binding, from round 266/276's entries). Not new.
- Round 294: Whence v0.14.8's `rand()` — the SECOND effectful builtin, and
  the first genuinely NONDETERMINISTIC one in a language whose entire test
  methodology (three-way differential, guest/host self-hosting comparison,
  fast/slow reference-diff bench) assumes a program's behavior is a pure
  function of its source text. The resolution — a per-instance seeded RNG
  (`Interpreter(seed=0)`, `self._rng = random.Random(seed)`) rather than
  entropy-backed randomness — is a genuinely new, reusable design pattern
  for this skill's territory (interpreter design + differential testing)
  and was not previously documented anywhere in `skills/`.
- Round 296: guest parity for `rand()` — a same-shape extension of the
  existing "self-hosted guest evaluator, delegation-based builtin parity"
  pitfalls already in this file (rounds 176/206/218's entries: name-
  resolution gate, arity-0 subtlety already checked and confirmed harmless
  by round 296 itself). Not new.

Two genuinely new, confirmed, non-obvious findings → both added as pitfalls
to `skills/tiny-language-implementation/SKILL.md` (the existing skill whose
territory — interpreter design, self-hosting, differential testing — both
findings sit squarely inside; no new skill authored, per the standing rule).

## What changed
`skills/tiny-language-implementation/SKILL.md`: 317 → 376 lines (still well
under `skill_lint.py`'s 400-line warn / 500-line error thresholds). Two new
Pitfalls bullets appended right before `## Verification`:

1. **Reproducible nondeterminism via per-instance seeding.** States the
   general problem (any oracle comparing two runs of "the same" program
   assumes determinism; a first entropy-backed builtin breaks every such
   oracle at once) and the general fix (seed a per-instance RNG at
   construction time, draw the nondeterministic builtin from it — "same
   input" now includes the seed, so "same input implies same output" holds
   again with zero changes to any oracle). Cites the exact Whence
   mechanism: `Interpreter.__init__(..., seed=0)`,
   `self._rng = random.Random(seed)`, the `rand` AST node reading
   `interp._rng.random()`. Explicitly flags this as a decision to make
   BEFORE writing the builtin, since retrofitting a seed onto an
   already-shipped entropy-backed builtin makes every previously-recorded
   oracle run unreproducible after the fact.

2. **Default-value mismatch between two sides of a differential harness
   silently widens a named exemption bucket.** States the general shape:
   if a comparison already exempts one specific kind of one-sided
   divergence by name (e.g. "guest can legitimately exhaust a resource
   budget the host doesn't, because it pays more host frames per guest
   call"), then each side's builder defaulting that SAME resource
   parameter independently — rather than threading one shared value through
   both — turns a real, in-scope divergence into an invisible one: it now
   also satisfies the exemption's precondition, so it's silently
   reclassified as expected rather than caught. Names this as a coverage
   gap, not a crash or false positive — nothing in a green suite flags it,
   it just means a class of bug can no longer be found until someone
   thinks to check. Cites the exact mechanism: `GuestHarness.__init__`'s
   old `max_depth=None` default (resolving to the raw interpreter's
   unrelated `DEFAULT_MAX_DEPTH=20000`) vs `oracle_self_eval`'s own
   `max_depth=2000` default, and the fix (thread one explicit `max_depth`
   through both builder call sites, key the guest-harness cache on
   `(pkg, max_depth)` not just `pkg`). Gives a concrete audit heuristic:
   grep both builder call sites for every parameter with a *named*
   exemption bucket in the comparison logic and confirm both sides pass
   the same value — the exemption bucket's existence is itself evidence a
   mismatch has bitten this comparison before.

Both bullets are **docs-only** — no `SKILL.md` frontmatter (name/
description/trigger conditions) changed, so per this track's own standing
rule ("body-only edits don't owe a fresh probe," established round 165) no
live `trigger_eval.py` re-probe was run this round.

## Verification
- `python3 skills/skill-authoring/scripts/skill_lint.py --house --strict
  skills/` → **17 skills, 0 errors, 1 warning** (the pre-existing
  `fuzz-mutate-kill-loop` 415-line B002 warning, untouched this round and
  unrelated to this round's file) — `tiny-language-implementation` itself
  clean at 376 lines, no new warning.
- `python3 -m pytest -q skills/session-inheritance-audit/scripts/
  skills/skill-authoring/scripts/` → **197 passed** (unchanged from round
  291's baseline — expected, docs-only edit, no script logic touched).
- `bash harness/run_tests_fast.sh` (cross-track regression check) →
  **403 passed, 199 deselected**, byte-identical to round 295/296's own
  baseline — this round touches only `skills/`, invisible to the harness
  suite as expected.
- `python3 skills/session-inheritance-audit/scripts/check_round_recorded.py
  --show-acknowledged` re-run after this round's own commit (see next
  round's pre-flight) will confirm round 297 is recorded — not re-run
  again within this same round's own turn (would only re-show the
  expected self-referential mid-flight gap).

## Net effect
`tiny-language-implementation` — the skill every language(C) round already
uses as its primary reference — now carries two more confirmed, cross-
track-sourced failure modes (a reproducibility-by-construction pattern for
nondeterministic builtins, and a differential-harness default-mismatch
audit heuristic) that a future language(C) or SWE-loop(D) round would
otherwise have to rediscover independently. Continues this track's standing
practice (rounds 165/219) of harvesting genuinely reusable findings from
OTHER tracks' recent rounds into the existing skill whose territory they
fit, rather than letting them sit as prose buried in `research-state.md`'s
round-294/295 entries or manufacturing a new skill file for them.

## Next steps for a future skills(B) round
1. `fuzz-mutate-kill-loop/SKILL.md` sits at 415/500 lines (pre-existing
   warning, unrelated to this round) — still has headroom, but is the
   nearest skill to the 400-line warn threshold; if it grows further,
   follow the `session-inheritance-audit`/`references/pitfalls.md`
   precedent (rounds 285/291) and split older bullets out.
2. The `--distractors`/`--paired` live suppression diagnostic is CLOSED
   (round 243) — not reopened, no new near-miss target has appeared since.
3. No cross-track backlog items are currently stale/unclaimed for more than
   1-2 rounds as of this round's own pre-flight check — the swap-watch
   collector (the one long-standing multi-round item) closed at round 295.
4. Continue the "evaluate every session's non-skills rounds for skill-worthy
   findings before authoring anything new" discipline each skills(B) round
   — this round found exactly 2 genuinely new findings out of 5 candidate
   rounds (292-296), the other 3 being same-shape extensions of already-
   documented pitfalls.
