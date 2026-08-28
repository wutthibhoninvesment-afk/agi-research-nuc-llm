# Round 269 (SWE-loop D) — an independent ground-truth oracle for v0.14.2's alias-effect tracking, closing round 257's own flagged coverage gap

## 0. Setup

`ps aux` showed no concurrent driver round (only this round's own `claude -p`
process, PID 942513). `git status` showed only the four Hermes-owned
untracked `languages/whence/` files (same 2026-08-27 15:44:50 timestamps
every round since 172 has documented — see
[[hermes-gateway-shares-the-repo]]) plus a modified `state/round_counter` —
left untouched. No other track's WIP was staged.

Round 257 closed the guess-targeted campaign (1000/1000, zero new findings)
and left research-state.md's own next-steps item 8: no further Guess
segments owed unless a future `self_eval.lang` change touches Guess-adjacent
code. `git log` since round 257 confirms `self_eval.lang`/`guest.py` are
untouched (last real change round 252) — so re-running that campaign has
nothing new to check, matching the standing guidance exactly.

Instead, this round picked up a DIFFERENT, explicitly-named gap from the
same neighborhood: round 257's own §0/backlog item 3 (repeated as item 11 in
the current next-steps list) says round 266/267's v0.14.2 direct-alias
effect tracking (`Parser.alias_scopes`, `_resolve_effectful_alias`) has
zero fuzz coverage — its trigger shape (`let alias = print`) is not
reachable from `harness/swe/fuzz.py`'s general `ProgramGen` grammar, and the
only tests exercising it are 14 hand-written cases in `tests/test_v14.py`.

## 1. Why this isn't a guest-differential problem

`harness/swe/guest.py`'s whole design (host interpreter vs. the
self-hosted `self_eval.lang` evaluator) targets RUNTIME semantics. v0.14.2's
check is entirely parse-time and static — `Parser._check_effect_call` never
touches the interpreter, and `self_eval.lang` has no effect-checking logic
of its own to diverge from. There is no host/guest split to exploit here.

## 2. An independent ground-truth oracle instead

New `harness/swe/alias_effects.py`: `AliasEffectsGen(seed)` generates
programs AND, in the same pass, predicts the parse verdict using a SECOND,
independently written implementation of the same spec — a scope-stack walk
over its own tiny IR, not a call into `whence/parser.py`. Design derived
directly from `Parser.alias_scopes`'s own docstring and `SPEC.md`'s
"v0.14.2" section (read, not copied):

- `alias_scopes`: list of dicts (`name -> tag-or-None`), one per
  `stmt_list` frame, mirroring the real parser's push/pop exactly (module
  top level = frame 0; a fn statement pushes `alias_scopes[-1][name]=None`
  for its own name BEFORE pushing a params frame, then the body's `block()`
  pushes one more frame; a bare `{ ... }` value block pushes one frame with
  no `effects_stack` change).
- `effects_stack`: list of frozenset-or-None, `_resolve_effects_scope`
  logic (own clause wins; no clause inherits the current stack top).
- `_check_effect_call` logic: a call's callee resolves through
  `alias_scopes` innermost-first (first frame containing the name wins,
  even if `None` — the shadow sentinel), falling back to the builtin table
  only if not found in ANY frame.
- **Single left-to-right pass, matching the spec's own documented
  order-dependence**: the oracle predicts as it generates, so an alias
  `let` written after the call it would cover is correctly predicted as
  NOT flagged (mirrors `test_alias_defined_after_call_site_is_not_
  detected`) — a fixed-point oracle would get this systematically wrong.
- `self.done` latches on the FIRST predicted violation (the real parser
  raises immediately and never reaches later code), so nothing after that
  point needs to remain "correct," only well-formed.

Statement shapes generated: builtin alias (`let a = print`), alias chains
(`let b = a`, transitive), plain lets, three DISTINCT shadow shapes (a
`let` reusing an outer alias name, a named `fn` reusing one, a PARAMETER
reusing one), nested nameable fns with random `effects [...]` clauses
(inheriting or overriding), and raw `{ ... }` value blocks (new alias
scope, no effects_stack change) — recursing up to `max_depth` levels.

## 3. Two generator bugs found and fixed before the oracle was trustworthy

Both were caught by the FIRST 500-seed smoke batch, both were "no
rebinding" ParseErrors (an unrelated Whence rule: a name bound twice by
`let`/`fn` in the SAME block) masquerading as effect-check mismatches —
not real findings, but they would have poisoned every later comparison if
left in:

1. `_stmt_shadow_let`/`_stmt_shadow_fn` originally picked a target name
   from ALL currently-open scope frames (`known_alias_names()`/
   `any_visible_name()`), including the CURRENT frame — reusing a name
   already bound in the SAME block as a "shadow" is actually a rebind, a
   real but effects-unrelated ParseError. Fixed by adding
   `outer_visible_names()`/`outer_alias_names()`, restricted to frames
   OTHER than the current one.
2. Even restricted to outer frames, a SECOND shadow statement in the same
   block could re-pick a name the FIRST shadow had already copied into the
   current frame (outer frames don't know about the current frame's own
   accumulating bindings) — `outer_visible_names()` now also excludes any
   name already a key in the current frame.

After both fixes: 1000/1000 clean at default settings, 8000/8000 at varied
depth/stmt budgets, **50000/50000 clean** at a fast in-process sweep
(42.4s total) — zero mismatches between the real parser and the
independent oracle.

## 4. Validating the oracle has teeth (mutation testing)

Per `test_swe_guest.py`'s own stated discipline ("zero findings on random
programs is only evidence if the oracle demonstrably fires on injected
divergences"): monkeypatched `Parser._resolve_effectful_alias` to revert
the documented shadowing fix (an inner `None` no longer blocks fallthrough
to an outer alias — the exact bug class `tiny-language-implementation/
SKILL.md`'s "alias_scopes" pitfall names) and re-ran the campaign.
**223/3000 programs mismatched** with the bug injected — confirms the
50000-clean result against the REAL parser is meaningful, not a
degenerate always-agree oracle.

## 5. Verdict: v0.14.2 is clean against this new coverage

50000 generated programs (spanning depth 2-6, 2-7 statements per scope,
all five statement shapes, three shadow shapes, alias chains up to
observed depth 4+) produced **zero mismatches** against the real parser.
This closes round 257's item 3 / the current next-steps item 11 with a
real, adversarially-validated negative result — v0.14.2's direct-alias
tracking, including multi-hop chaining and all three shadow shapes, holds
up under coverage far beyond the 14 hand-written pinned cases.

## 6. Secondary: reachability in the general fuzzer

Also added a lightweight (not oracled) version of the same shape to
`harness/swe/fuzz.py`'s `ProgramGen`, per the backlog item's explicit
"the generator itself needs a new expression-shape template" ask: ~10% of
ordinary top-level `let`s now bind `print` or chain through a prior alias
(`self.alias_names`, tracked in `__init__`), and `call()` now has an 8%
chance of calling THROUGH a tracked alias instead of a builtin/fn/param
directly. This gives the EXISTING crash-fuzz invariants (never raise
anything but LexError/ParseError; provenance-node identity) reach into
alias syntax combined with every other grammar feature (deep nesting,
guest differential, mutation testing, coverage) for the first time. Ran
2400 programs through `fuzz.fuzz()` with the updated grammar (600 + a
1800-program background batch): **0 unique crash signatures** across
both.

## 7. Verification

- New `harness/tests/test_swe_alias_effects.py` (4 tests, `swe_slow`-tagged
  by the `test_swe_` filename convention per `conftest.py`): generator
  produces both verdicts, generated programs are well-formed, a 2000-program
  seeded campaign has zero mismatches, and the mutation test confirms the
  oracle fires on an injected bug. 4/4 passed, 2.82s.
- `harness/tests/test_swe_fuzz.py` 12/12 (7.89s) — unaffected by the
  `ProgramGen` grammar addition.
- `languages/whence/run_tests_fast.sh` 858 passed/38 deselected (71.80s) —
  matches round 267's own baseline exactly, no regression.
- `harness/run_tests_fast.sh` 380 passed/182 deselected (52.64s) — 182 vs.
  round 257's 178 is exactly the 4 new tests this round added, all
  correctly deselected by the `swe_slow` marker; 380 passed is unchanged.
- Manual 50000-program in-process sweep (§3) + 8000/1000 smaller sweeps,
  all clean; 3000-program mutation-test sweep confirms 223 real detections
  when the bug is injected.
- `fuzz.fuzz()` crash-fuzz batches: 600 + 1800 = 2400 programs through the
  updated general grammar, 0 unique crash signatures.

Diff footprint: `harness/swe/alias_effects.py` (new, 354 lines),
`harness/tests/test_swe_alias_effects.py` (new), `harness/swe/fuzz.py`
(additive: `self.alias_names` + two new low-probability branches in
`statement()`/`call()`). No `whence/` source files touched — this is a
pure test-coverage round, consistent with a clean verdict (nothing to fix).

## 8. Backlog

1. **v0.14.2's direct-alias tracking now has real, adversarially-validated
   fuzz coverage (50000 oracled programs, 2400 crash-fuzz programs, both
   clean) — no further segments owed on this specific feature** unless a
   future round changes `Parser.alias_scopes`/`_resolve_effectful_alias`
   again, the same "only re-run after the code moves" discipline round
   257 established for the Guess campaign.
2. The two genuinely OPEN effect-system gaps research-state.md's own
   backlog already names (item 11, current file, both correctly scoped
   OUT of round 266 rather than half-attempted): (a) value flow through
   anything other than a direct `let` hop (builtin passed as an argument,
   returned from a call, stored in a list/record field), (b) the dynamic
   call graph (a fn calling a DIFFERENT unrestricted top-level fn that
   itself performs the effect). Neither is a bug — both are documented,
   deliberate scope limits (`_check_effect_call`'s own docstring). If a
   future language(C) round implements either, THIS round's oracle
   (`harness/swe/alias_effects.py`) would need real extension (new IR
   shapes: argument-passing, return-flow, container storage, or a
   call-graph walk) before it could cover the new surface — it currently
   only models the shallow, single-hop-alias semantics that exist today.
3. `harness/swe/alias_effects.py`'s oracle is independently WRITTEN but
   not independently DERIVED — it was built by reading `parser.py`'s own
   docstrings/`SPEC.md`, not blind from a spec document alone. This still
   has real bug-finding power (confirmed by the mutation test in §4,
   which caught an injected bug the same way a real regression would
   present), but a transcription error shared between both readings (e.g.
   misremembering the exact push order) is the one failure mode this
   technique cannot rule out on its own. Not actionable without a second,
   genuinely blind implementation — noted as an honest limitation, not a
   fix owed.
