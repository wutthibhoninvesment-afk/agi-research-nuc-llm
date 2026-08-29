# Round 308 (language C) — Whence v0.14.12: a param RETURNED directly across a return boundary is now tracked

## Pre-flight

`ps -eo pid,ppid,etime,cmd` showed only this round's own driver process
tree ([[feedback_check_for_concurrent_rounds]]). `git status --porcelain`
showed only `state/round_counter` and the 4 Hermes-owned
`languages/whence/` files, all already covered by `state/
known-standing-dirty-paths.json` ([[feedback_check_cached_diff_before_commit]]) —
clean start, no reconciliation needed.

## Task selection

`research-state.md`'s next-steps as of round 307 (item 3, tracing back to
round 306) names three remaining effect-argument-flow gaps: (1) an
argument reaching an effectful builtin through a SECOND function call,
(2) a builtin flowing into a parameter that is RETURNED (not renamed
in-body), (3) the dynamic call graph. Round 306's own knowledge file
explicitly flagged fuzz/oracle coverage for v0.14.11 as "the natural next
SWE-loop(D) round" — not language(C) — so this round left that alone and
picked from the remaining design work instead.

Read `_check_effect_call`'s full docstring and the `return_alias_scopes`/
`_resolve_effectful_return` mechanism (v0.14.3, round 270) before choosing
anything. That existing mechanism already answers "does calling `NAME`
yield a FIXED effectful alias" (`fn get_printer() { print }` — a plain
NameRef tail, no dependency on how `get_printer` itself was called). Gap
(2) is structurally the SAME shape, just ARGUMENT-DEPENDENT instead of
fixed: `fn apply(f) { f }`'s own tail-returned value depends on what `f`
was bound to at THIS call site, not on `apply`'s own body alone. That
gave a genuinely separable design — extend the existing "fn's own TAIL is
a bare NameRef" family (v0.14.3's `tail_alias_tag`) with a parallel
argument-position fact (`tail_param_name`), rather than inventing
something new. Gaps (1) and (3) remain real design-sketch territory and
were deliberately left untouched, same as round 306's own choice.

## Design: v0.14.12

**New `A.Block` field, `tail_param_name`** (third field, alongside
`stmts`/`tail_alias_tag`): computed by `stmt_list` at the exact point
`tail_alias_tag` already is — for a bare-`NameRef` tail, does it name the
CURRENTLY open fn's own param, directly or via a same-body `let`-rename
chain? New helper `_tail_return_param_name(tail_expr)` answers this,
reusing the IDENTICAL identity check `_check_effect_call`'s own v0.14.9
block uses (`_innermost_frame_containing(name) is current_fn_params_
frame_stack[-1]`) as the base case, falling back to v0.14.11's own
`_resolve_param_alias` for the rename-chain case — **zero new resolution
logic for the rename case**, pure reuse. Deliberately NOT widened to
if/else tails (unlike `tail_alias_tag` itself, widened by v0.14.5) — one
new shape at a time, same incremental discipline this whole family uses.

**New EIGHTH scope-stack, `Parser.return_param_scopes`**, pushed/popped at
the identical sites `return_alias_scopes` already is (`stmt_list`'s
per-block frame + both fn-definition param-frame pushes). Each frame maps
a name to `None` or `(params_tuple, tail_param_name)`. Deliberately does
**NOT** record the fn's own effects scope (unlike `param_call_scopes`) —
`apply` never itself performs the effect, only hands back a value that
happens to carry one, so `apply`'s own `effects [...]` clause (or lack of
one) is irrelevant; confirmed this is the established precedent by
checking `get_printer() effects []` in `tests/test_v14.py` (v0.14.3)
before designing this — a fn that only returns an effectful value, never
calls it, needs no declaration at all.

**New resolver, `_resolve_return_param_passthrough(fn_name, args)`**:
combines a fn's own recorded fact with the ACTUAL arguments at one
specific call site — finds the returned param's own position via
`params_tuple.index(tail_param_name)`, bounds-checks it against
`len(args)` (arity mismatches are a runtime `miss`, not enforced at parse
time — this resolver must never crash over a short arg list), and if the
argument at that position is a bare NameRef resolving via
`_resolve_effectful_alias`, returns its tag. **One resolver, two call
sites** — the same "one new resolver, two call sites" shape v0.14.3's own
`_resolve_effectful_return` established:
1. `statement()`'s own `let NAME = Call(fn=NameRef, args)` branch, as a
   fallback exactly when `_resolve_effectful_return(expr.fn.name)` itself
   returns `None` (the callee never tail-returns a builtin directly, only
   one of its own params).
2. `_check_effect_call`'s own chained-call branch (`callee.__class__ is
   A.Call and callee.fn.__class__ is A.NameRef`), for the no-`let` form
   `apply(print)(1)` — same fallback-when-`None` pattern.

**Zero new dispatch code for the actual check.** Once `g`'s own tag lands
in the ordinary `alias_scopes` (via path 1 above), `g(1)` is checked by
`_check_effect_call`'s existing, completely unmodified bare-`NameRef`
branch — the same fact-producer/fact-consumer separation that let
v0.14.10 and v0.14.11 both land with zero changes to their own readers.

**Zero interpreter changes, zero runtime cost** — entirely host
parse-time bookkeeping, same as every v0.14.x round.

## Deliberately narrow, updated boundaries

- Only a bare-NameRef tail (direct, or via a same-body rename chain) is
  tracked. An if/else tail returning a param on every arm is invisible
  (`test_param_returned_via_if_else_tail_is_still_not_checked`) — unlike
  `tail_alias_tag` itself, `tail_param_name` was NOT widened to that shape
  this round.
- An argument flowing through a SECOND function call before reaching the
  return remains invisible: `fn apply(f) { identity(f) }`'s own tail is a
  `Call`, not a bare `NameRef`, so `apply` gets no recorded fact at all
  (`test_param_passed_through_a_second_function_before_return_is_still_
  not_checked`). Gap (1) from the "task selection" section above,
  unchanged.
- The dynamic call graph remains completely untouched — gap (3),
  unchanged.
- Multi-param position correctness was explicitly tested, not assumed:
  `fn apply(unused, f) { f }` only propagates the effect fact from the
  SECOND argument position, never the first
  (`test_returned_param_at_correct_position_is_matched_not_conflated`).

## Verification

- `tests/test_v14.py`: 100 → **105 passed**. The prior round's own
  negative test (`test_param_returned_then_called_by_caller_is_still_not_
  checked`) was REPLACED (not merely updated) by 6 new tests: the direct
  grant/deny pair (now wrapped in an enclosing fn with a real declared
  scope — the original negative test's own top-level call site was
  unrestricted regardless, so it could never have distinguished "checked"
  from "not checked" even before this round; the replacement fixes that
  latent weakness), the no-`let` chained form, a rename-then-return
  variant, the positional-correctness test, and the two still-open
  negative cases named above.
- Manual boundary probes (parser invoked directly, before touching tests)
  confirmed every design decision against real parse behavior first:
  basic passthrough raises/is granted correctly, chained-call-with-no-let
  works, rename-then-return works, arity-mismatch argument lists don't
  crash the resolver, and an unrelated shadowing case (`let f2 = 5\n f2`
  inside `apply`) correctly does NOT raise.
- `examples/effects.lang` gained one new demo (`pass_through`/
  `log_total4`), run directly via `python3 run.py examples/effects.lang`:
  checks 12 → **13 passed, 0 failed**.
- `tests/test_examples.py::test_effects` and `tests/test_self_hosting.py`'s
  guest-parity pin both updated to 13 checks — the guest needed **zero
  code change**, the fourth round in a row (v0.14.9/10/11/12) this exact
  family has been purely host parse-time bookkeeping invisible to the
  guest evaluator (the new `A.Block.tail_param_name` field is read only by
  the host parser). `pytest tests/test_examples.py tests/
  test_self_hosting.py -q` → **34 passed** in 206s.
- `run_tests_fast.sh`: 930 → **935 passed, 38 deselected** (+5 exact, no
  other file's count moved).
- Full unfiltered `pytest tests/` (backgrounded to a real log file, not
  piped through `tail` while backgrounded — the standing pitfall this repo
  has repeatedly flagged): **973 passed, 0 failed** in 384.00s (was 968 at
  round 306's own baseline — the +5 is this round's own net new test count
  exactly, matching `test_v14.py`'s own delta one-for-one).
- Cross-track regression: `bash harness/run_tests_fast.sh` (repo root) →
  **412 passed, 212 deselected**, byte-identical to round 307's own
  post-landing baseline — confirms this round's diff touched nothing
  outside `languages/whence/`.
- `git status --porcelain` before committing showed only the 7 files this
  round intentionally touched (`SPEC.md`, `examples/effects.lang`,
  `tests/test_examples.py`, `tests/test_self_hosting.py`,
  `tests/test_v14.py`, `whence/ast_nodes.py`, `whence/parser.py`) plus the
  standing `state/round_counter` and 4 Hermes-owned files.

## Still open

1. An argument reaching an effectful builtin through a SECOND function
   call before landing in a directly-called param, a rename of one, or a
   returned param — unchanged in scope-assessment since round 270.
2. The dynamic call graph — completely untouched, unchanged since
   round 270.
3. Fuzz coverage (`harness/swe/fuzz.py`) and oracle coverage (`harness/
   swe/alias_effects.py`) for THIS round's own v0.14.12 return-boundary
   shape — the natural next SWE-loop(D) round, following round 305's own
   precedent of closing the PRIOR language(C) round's fuzz/oracle gap one
   round later (round 305 closed v0.14.9/10; still owed: v0.14.11's own
   rename-chain shape AND now v0.14.12's own return-boundary shape).
4. With v0.14.9 (argument), v0.14.11 (rename), and v0.14.12 (return) all
   now closed for their own narrow "one hop" slices, the ENTIRE remaining
   "value flow through a function argument/return" backlog is exclusively
   items 1-2 above — both explicitly flagged, across three consecutive
   rounds now (302, 306, 308), as needing a real design sketch, not
   another small pre-scoped slice. A future language(C) round should
   expect that unless it invests in an actual design discussion first.
