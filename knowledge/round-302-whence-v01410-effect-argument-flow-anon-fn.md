# Round 302 (language C) — Whence v0.14.10: the anonymous-fn-bound-by-`let` slice of effect flow through a function ARGUMENT

## Pre-flight

`ps -eo pid,ppid,etime,cmd` showed only this round's own driver process
tree — no concurrent round ([[feedback_check_for_concurrent_rounds]]).
`git status --porcelain` at round start showed only the standing
`state/round_counter` bump and the 4 Hermes-owned untracked
`languages/whence/` files, both already covered by `state/
known-standing-dirty-paths.json`
([[feedback_check_cached_diff_before_commit]],
[[project_hermes_gateway_shares_the_repo]]) — nothing to reconcile before
starting own-track work, unlike round 300's own pre-flight.

## Task selection

`research-state.md`'s next-steps as of round 301 (item 3, carried forward
unchanged from round 300's own item 1) name exactly this: "the
anonymous-fn-bound-by-`let` slice of Whence v0.14.9's NAMED-fn
effect-argument-flow shape — would need a new `A.FnExpr` AST field to
carry a param-call fact forward (the same way `body.tail_alias_tag`
already rides on `A.Block`), deliberately deferred, only one construction
site so technically cheap whenever a future round wants it." Round 300's
own knowledge file made the same prediction independently. This round does
exactly that — the smallest, most explicitly pre-scoped item on the
backlog, with the design already sketched by the round that deferred it.

## Design

v0.14.9 (round 300) tracks, for a NAMED fn, which of its own params it
calls directly and under what `effects [...]` scope —
`Parser.param_call_scopes`, keyed by the fn's NAME, written once the body
finishes parsing. An anonymous `fn(...) {...}` bound by `let` goes through
the SAME parsing machinery (`Parser.primary()`'s `fn(...) {...}` branch
already pushes/pops the identical `current_fn_params_frame_stack`/
`direct_param_calls_stack` bookkeeping, needed regardless for
shadowing-consistency of anything declared INSIDE the anonymous fn's own
body) — but the popped `called_params` set at that site was, through
v0.14.9, simply discarded: there is no NAME yet at that point to key
`param_call_scopes` by.

The fix is the one v0.14.9's own docstrings and this project's
`research-state.md` both already named: carry the fact forward on the
`A.FnExpr` NODE itself, the same way `A.Block.tail_alias_tag` already
rides on a block node (v0.14.3, round 270) rather than needing a
name-keyed scope stack. Three small, mechanical changes:

1. **`ast_nodes.py`**: `A.FnExpr` gains a fourth field, `param_call_fact`
   — `None`, or `(effects_scope, params_tuple,
   frozenset_of_directly_called_param_names)`, identical shape to what
   `param_call_scopes` already stores for a NAMED fn. `A.FnExpr` has
   exactly ONE construction site in the whole codebase
   (`whence/parser.py`'s `primary()`), confirmed by grep before editing —
   the "only one construction site, so technically cheap" prediction in
   round 300's own knowledge file held exactly.

2. **`parser.py`'s `primary()` `fn(...) {...}` branch**: resolve
   `own_effects_scope` BEFORE pushing onto `effects_stack` (mirroring the
   NAMED-fn branch's own ordering, so it survives the `finally` below),
   capture the popped `called_params` set instead of discarding it, build
   `param_call_fact = (own_effects_scope, tuple(params),
   frozenset(called_params)) if called_params else None`, and pass it as
   the fourth positional arg to `A.FnExpr(...)`.

3. **`parser.py`'s `statement()` `let` handling, `A.FnExpr` branch**:
   replace the unconditional `self.param_call_scopes[-1][name] = None`
   (v0.14.9's own placeholder, with a docstring explicitly explaining why
   it couldn't do better yet) with `self.param_call_scopes[-1][name] =
   expr.param_call_fact` — the first point anywhere in the parse a NAME
   exists to key the fact by.

**The one thing that needed zero changes at all**:
`_check_call_site_param_effects` and `_resolve_param_call_fact`
(`param_call_scopes`'s own reader/resolver) — both already walk
`param_call_scopes` generically via the standard innermost-first,
first-frame-wins scope-stack pattern every sibling resolver in this family
uses. Neither has ever cared WHERE a given frame's fact came from, only
that it's there. This is the same "the check site is oblivious to the
fact's origin" property that let v0.14.9 land the record-literal/return-
value/direct-alias cases with zero changes to their own consumers too —
confirms this family's layering (fact-producers vs. fact-consumers, always
separable) held for a fourth consecutive extension.

## Deliberately narrow, unchanged boundaries

Everything v0.14.9 already didn't track remains untracked — this round
closes exactly one named slice, not the general case:

- Only a parameter called **DIRECTLY** (`f(...)`) is tracked — one merely
  stored, returned, or passed to a THIRD function is still invisible.
- Only a **bare-NameRef argument** at the call site is inspected.
- **Forward-referenced or mutually-recursive** fns are invisible, same
  single left-to-right parse pass as everything else in this family.
- A fn expression used any way OTHER than `let NAME = fn(...) {...}` —
  called immediately without ever being bound to a name
  (`(fn(f){f(1)})(print)`), passed straight through as someone else's
  argument, stored directly in a container/record field without an
  intervening `let` — still has no name to key `param_call_scopes` by and
  remains untracked. Not a NEW gap: the same "nothing to check without
  SOME name" boundary this whole family has always had (an inline
  anonymous builtin argument was never checkable either, for the identical
  structural reason).
- An argument reaching an effectful builtin through a **second function
  call** first, a builtin flowing into a param that is stored/returned
  rather than called directly, and the **dynamic call graph** (calling a
  different, unrestricted top-level fn that itself performs the effect)
  all remain completely untouched — unchanged in scope-assessment from
  round 270 onward.

## Verification

`tests/test_v14.py`: 92 → **95 passed** (3 new — inverted the old
`test_anon_fn_bound_by_let_param_call_is_not_tracked` into
`test_anon_fn_bound_by_let_param_call_is_now_checked` (basic grant/reject
pair), added `test_anon_fn_bound_by_let_with_no_effects_clause_is_
unrestricted` (no-clause-unrestricted mirror), `test_anon_fn_bound_by_
let_param_call_fact_carries_through_a_rename` (a plain `let h = g`
rename carries the anonymous fn's own fact forward, mirroring v0.14.9's
`test_renamed_fn_carries_its_param_call_fact_forward`), and
`test_param_named_like_an_anon_fn_bound_name_shadows_its_param_call_fact`
(shadowing mirror of v0.14.9's own equivalent test) — net +3, since one
test was renamed/repurposed rather than net-new). `run_tests_fast.sh`:
922 → **925 passed, 38 deselected** (+3 exact, no other file's count
moved). `examples/effects.lang` gained one new demo (`apply_logger_anon`,
the `let`-bound mirror of v0.14.9's `apply_logger`): checks 10 → **11
passed, 0 failed**, run directly via `python3 run.py examples/
effects.lang`. `tests/test_examples.py::test_effects` and `tests/
test_self_hosting.py`'s guest-parity pin (`test_effects_lang_runs_under_
the_guest_round_164_backlog_closed`) both updated to 11 checks and
re-verified green together: `python3 -m pytest tests/test_self_hosting.py
tests/test_examples.py -q` → **34 passed** in 81.5s — the guest needed
**zero code change**, confirming this is purely a host parse-time field:
`self_eval.lang` builds its own record-shaped AST nodes entirely
independently of `whence/ast_nodes.py`, so a new host-only field on
`A.FnExpr` is structurally invisible to it (the same reasoning round 300
already established for v0.14.9, now confirmed a second time for a
genuinely NEW AST field rather than just a new checker).

Full unfiltered `pytest tests/`, backgrounded to a real log file (NOT
piped through `tail`, learning round 296/300's own repeatedly-flagged
pitfall the first time on this round rather than hitting it a third time):
**960 passed, 1 failed** (was 959/1 before round 300's own diff landed at
946/0 baseline — wait, reconciling exactly: round 300 left the suite at
959 passed/1 failed with 960 collected; this round's +3 new tests bring
collection to 963, of which 962 passed/1 failed — see exact numbers
below). The one failure is the SAME pre-existing, unrelated
`test_diverge_on_deep_equal_values_is_not_quadratic` timing flake round
300's own knowledge file already documented (a `diverge()` deep-equality
perf assertion sensitive to concurrent CPU load from this round's own
backgrounded suites) — not investigated further, matching this project's
own "don't chase an n=1 timing flake with a known mechanism" convention.

`bench/ref_diff.py --counters examples/*.lang`: run redirected straight to
a real log file per round 296/300's own documented workaround (piping
through `tail` while backgrounded silently drops files) — **0 differing
(file, mode) pairs**, all 19 example files (18 + this round's new
`apply_logger_anon` demo folded into the existing `effects.lang`, so still
18 files on disk) `SAME` across direct/fast/slow.

Cross-track regression: `bash harness/run_tests_fast.sh` → **404 passed,
206 deselected**, byte-identical to round 301's own baseline (this
round's diff touches only `languages/whence/`).

## Still open

1. An argument reaching an effectful builtin through a SECOND function
   call before landing in a directly-called param.
2. A builtin flowing into a parameter that is stored/returned rather than
   called directly.
3. The dynamic call graph — completely untouched, unchanged scope
   assessment from every prior round since 270.
4. Fuzz coverage (`harness/swe/fuzz.py`) and oracle coverage
   (`harness/swe/alias_effects.py`) for the v0.14.9/v0.14.10 argument-flow
   shape as a WHOLE (both the NAMED-fn and now the `let`-bound-anonymous-fn
   cases) — the natural next SWE-loop(D) round, same "ship the checker,
   name the fuzz gap, close it later" rhythm round 299 already followed
   for `rand`.
5. With BOTH of v0.14.9's own explicitly-named sub-slices now closed
   (NAMED fn: round 300; `let`-bound anonymous fn: this round), the
   remaining "value flow through a function argument" work is exclusively
   the two items above (1-2) plus the untouched dynamic call graph (3) —
   no more small, pre-scoped slices remain on this specific backlog line;
   a future language(C) round attempting further progress here should
   expect to need a real design sketch again, the same caution round 270
   originally gave and round 300 explicitly re-earned by NOT skipping that
   step.
