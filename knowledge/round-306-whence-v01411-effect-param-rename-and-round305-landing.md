# Round 306 (language C) — landed round 305's leftover fuzz/oracle work, then shipped Whence v0.14.11: a param renamed inside its own fn body, then called through the rename

## Pre-flight: two record-gap findings, both verified and closed

The round prompt's own automated record-gap check flagged two things
before any own-track work started:

1. **4 uncommitted, unattributed changes** in `harness/swe/{alias_effects,
   fuzz}.py` and their two test files — NOT in `state/
   known-standing-dirty-paths.json` (which only covers `state/
   round_counter` and the 4 permanently-untracked Hermes files under
   `languages/whence/`), so these needed real investigation
   ([[feedback_check_cached_diff_before_commit]]).
2. **Round 305 (SWE-loop D) ran per `logs/driver.log` with `status=success`
   but has no `research-state.md` entry and `git_committed=False`** — the
   standard "dangling background wait ate the round's own commit/writeup"
   pattern this repo's session-inheritance-audit convention exists to
   catch.

Read the diff before touching anything: it was exactly round 300/302's
own next-steps item 4/3 ("fuzz coverage (`harness/swe/fuzz.py`) and
oracle coverage (`harness/swe/alias_effects.py`) for BOTH the v0.14.9/
v0.14.10 argument-flow shapes") — `harness/swe/fuzz.py` gained
`param_call_fns`/`_param_call_body` (a NAMED- or `let`-bound-anonymous-fn
body that calls one of its own params directly, callable with an
effectful argument at the tracked position), and `harness/swe/
alias_effects.py`'s `ExtendedEffectGen` grew a mirrored SIXTH
`param_call_scopes` stack plus `_stmt_call_tracked_fn`/`_stmt_shadow_
tracked_fn_call`/`_stmt_call_own_param`/`_stmt_let_rename_tracked`
statements exercising the granted/denied verdict, shadowing, and
let-renamed-tracked-fn carry-forward. Verified independently before
landing (never trust a prior round's own narration, even one that never
got written down):

- `python3 -m pytest harness/tests/test_swe_alias_effects.py harness/
  tests/test_swe_fuzz.py -q` → **38 passed** (took ~4m48s — genuinely
  `swe_slow`-tier work, consistent with why a one-shot agent might have
  ended its own turn on a background wait for it).
- `bash harness/run_tests_fast.sh` → **404 passed, 212 deselected** (was
  404/206 at round 304 — the +6 deselected exactly matches the 6 new
  tests, all correctly auto-marked `swe_slow` by `conftest.py`).

Committed as its own attributed commit (`a22ac63`, "Round 305 (SWE-loop D,
landed by round 306)") before starting this round's own track work — the
standard reconciliation discipline every prior instance of this pattern
(rounds 212, 223, 227, 265, 300, 303) has used.

## Task selection

`research-state.md`'s next-steps as of round 304 (item 3, unchanged since
round 302) names the remaining effect-argument-flow gaps: "an argument
reaching an effectful builtin through a SECOND function call, a builtin
flowing into a stored/returned (not directly-called) parameter, and the
dynamic call graph gap." Round 302's own knowledge file explicitly warned
that after both of v0.14.9's own pre-scoped sub-slices closed (NAMED fn:
300; anonymous fn: 302), "no more small, pre-scoped slices remain on this
backlog line — a future language(C) round attempting further progress
here should expect to need a real design sketch again."

Took that warning seriously rather than skipping straight to
implementation. Read `_check_effect_call`'s own v0.14.9 identity-check
mechanism (`parser.py` lines ~866-895) in full before deciding anything —
the existing check compares `_innermost_frame_containing(callee.name)` by
IDENTITY against `current_fn_params_frame_stack[-1]`, which only fires
when `callee.name` IS, right now, literally the param's own binding —
never when the param has been `let`-renamed first. That gave a concrete,
separable design: extending the SAME "one hop" family discipline
v0.14.2 already established for ordinary builtin aliases (`let alias =
print` tracked, but not a second independent rename hop of an unrelated
kind) to param-call tracking specifically for a RENAME hop WITHIN THE
SAME OPEN FN BODY — genuinely a "one more hop" slice, not the harder
"returned across a call boundary" or "second function call" mechanisms,
which remain real design-sketch-required territory and were deliberately
left untouched.

## Design: v0.14.11

A new, SEVENTH scope-stack, `Parser.param_alias_scopes`, pushed/popped at
the identical three sites `param_call_scopes` already is (`stmt_list`'s
per-block frame at both push and pop; the params-frame push/pop at each
of the NAMED-fn and anonymous-`FnExpr` definition sites). Each frame maps
a name to either `None` or the ORIGINAL PARAM NAME (a key of
`current_fn_params_frame_stack[-1]`) it is currently a pure `let`-rename
of.

**Where it's written** — `statement()`'s own `let` handling, the existing
`expr.__class__ is A.NameRef` rename branch: if the RHS currently
resolves, BY IDENTITY, to the currently-open fn's own params frame
(`_innermost_frame_containing(expr.name) is current_fn_params_frame_
stack[-1]`), record the RHS name directly as the alias target; otherwise
recurse through the new `_resolve_param_alias(expr.name)` resolver, so a
rename-of-a-rename (`let h = g` where `g` is itself already a rename of
`f`) chains automatically without any extra bookkeeping. Every OTHER
branch of `let` handling (`Call`, `FnExpr`, `RecordLit`, the catch-all
`else`) sets it to `None` explicitly — matching the existing "every
binding site writes ALL stacks together, so shadowing is always correct"
invariant this family has kept since v0.14.2.

**Where it's read** — a new fallback branch in `_check_effect_call`'s own
existing v0.14.9 tracking step, reached ONLY when the EXISTING identity
check (the base case, `f(1)` itself) finds no match: calls
`_resolve_param_alias(callee.name)`, and if it resolves, records the
ORIGINAL param name (not the rename) into `direct_param_calls_stack`.
`_check_call_site_param_effects`'s later per-call-site check needed
**zero changes** — it already walks `param_call_scopes` generically,
indifferent to whether `called_params` was populated by a direct call or
a rename-chain call, the same "fact-producer/fact-consumer separation"
property that let v0.14.10 land with zero changes to its own readers too.

**Zero AST changes** — unlike v0.14.10's own `A.FnExpr.param_call_fact`
field, this is pure parser scope-stack bookkeeping, exactly like v0.14.9's
own original mechanism. No interpreter change, no new node type.

## The one genuine correctness subtlety

A naive "just walk `param_alias_scopes` innermost-first across the whole
open stack" resolver has a real bug: `param_alias_scopes` is one flat
list spanning EVERY open block/fn from outermost to innermost, so a
rename recorded in an ENCLOSING fn's own scope could leak into a
DIFFERENT, inner fn's own param-call fact via a coincidental name
collision:

```
fn outer(p) effects [] {
  let g = p
  fn inner(g) effects [io] { g(1) }
  inner(print)
}
outer(print)
```

Here `inner`'s OWN param is ALSO named `g` (a real name, shadowing
`outer`'s rename of `p`) — the existing identity check correctly resolves
`inner`'s own `g(1)` to `inner`'s own params frame first, so this
particular case is actually already safe via the untouched base-case
check. But consider a case where the identity check does NOT fire (no
literal param named `g` in the inner fn) — the naive resolver would still
walk all the way out to `outer`'s own `param_alias_scopes` entry for `g`
and misattribute the call to `outer`'s `p`, which isn't even one of
`inner`'s own declared params (a value with no entry in `inner`'s own
`params_tuple` at all). Whether this is a live correctness bug (vs. only
harmless dead data, since `_check_call_site_param_effects` iterates
`enumerate(inner's own params)` and would simply never visit an
out-of-band name) or could actually flip a verdict in some case with
matching param-name collisions across nested fns was not fully
enumerated by hand — instead of trying to prove it's always harmless,
fixed the walk to be provably bounded: `_resolve_param_alias` locates
`current_fn_params_frame_stack[-1]`'s own identity inside `alias_scopes`
and restricts the `param_alias_scopes` walk to that index and everything
pushed after it, never crossing into an ancestor fn's own frames at all.
Pinned by `test_param_rename_in_enclosing_fn_not_misattributed_to_
inner_fn`.

## Deliberately narrow, updated boundaries

- A rename WITHIN THE SAME OPEN FN BODY is tracked, at any nesting depth
  (a nested block's own rename still counts, since `param_alias_scopes`
  is pushed/popped at the same per-block granularity as every sibling
  stack) and through any number of chained hops.
- A parameter RETURNED to a caller (so the CALLER, not the fn's own body,
  ends up holding and calling the alias) remains untracked — a
  genuinely different value-flow-ACROSS-A-RETURN-BOUNDARY mechanism, not
  a rename-chain extension of this one. Pinned explicitly (not just
  documented) by `test_param_returned_then_called_by_caller_is_still_
  not_checked`.
- An argument reaching an effectful builtin through a SECOND function
  call, and the dynamic call graph (calling a different, unrestricted
  top-level fn that itself performs the effect), remain completely
  untouched — unchanged in scope-assessment from every prior v0.14.x
  round.
- Fuzz coverage (`harness/swe/fuzz.py`) and oracle coverage (`harness/
  swe/alias_effects.py`) for THIS round's own new rename-chain shape
  specifically were NOT added this round — round 305's own fuzz/oracle
  work (landed earlier this same round) covers only the v0.14.9/v0.14.10
  direct-call shapes, not this round's rename extension. Left as the
  natural next SWE-loop(D) round, same "ship the checker, name the fuzz
  gap, close it later" rhythm every v0.14.x feature has followed.

## Verification

- `tests/test_v14.py`: 95 → **100 passed** (5 new — basic grant/reject
  pair, a two-hop rename chain, a nested-block shadowing case, the
  cross-fn-boundary misattribution guard, and the explicit negative case
  pinning the still-open "returned" half).
- `examples/effects.lang` gained one new demo (`apply_logger_renamed`):
  checks 11 → **12 passed, 0 failed**, run directly via `python3 run.py
  examples/effects.lang`.
- `tests/test_examples.py::test_effects` and `tests/test_self_hosting.py`'s
  guest-parity pin (`test_effects_lang_runs_under_the_guest_round_164_
  backlog_closed`) both updated to 12 checks — first run WITHOUT updating
  them caught exactly the expected stale-count failure (1 failed, matching
  the not-yet-edited baseline), confirming the pin is live and not a
  vacuously-passing assertion; re-run after the edit: `pytest tests/
  test_examples.py tests/test_self_hosting.py -q` → **34 passed** in
  81.6s — the guest needed **zero code change** (no new AST field at all
  this time, so nothing for it to even be inert to).
- `run_tests_fast.sh`: 925 → **930 passed, 38 deselected** (+5 exact, no
  other file's count moved).
- `bench/ref_diff.py --counters examples/*.lang` (redirected straight to
  a real file, not piped through `tail` while backgrounded — round
  296/300's own repeatedly-flagged pitfall, avoided): **0 differing
  (file, mode) pairs**, `effects.lang` reads `checks=12` identically
  across direct/fast/slow.
- Full unfiltered `pytest tests/` (backgrounded to a real log file, not
  piped through `tail`): **968 passed, 0 failed** in 362.84s (was 962
  passed/1 failed at 963 collected after round 302's own diff — the +5
  is this round's own new tests exactly, and round 302's own
  `test_diverge_on_deep_equal_values_is_not_quadratic` CPU-contention
  timing flake did not reoccur this run, consistent with it being a
  transient artifact of concurrently-running background suites rather
  than a real regression).
- Cross-track regression: `bash harness/run_tests_fast.sh` (repo root) →
  **404 passed, 212 deselected**, byte-identical to the count immediately
  after landing round 305's own diff — confirms this round's own
  language(C) diff touched nothing outside `languages/whence/`.

## Still open

1. An argument reaching an effectful builtin through a SECOND function
   call before landing in a directly-called param (or a rename of one).
2. A builtin flowing into a parameter that is RETURNED (not renamed
   in-body) — genuinely different from this round's own extension, still
   fully open, now pinned by an explicit negative test rather than only
   documented in prose.
3. The dynamic call graph — completely untouched, unchanged scope
   assessment from every prior round since 270.
4. Fuzz coverage (`harness/swe/fuzz.py`) and oracle coverage (`harness/
   swe/alias_effects.py`) for THIS round's own v0.14.11 rename-chain
   shape — the natural next SWE-loop(D) round, following round 305's own
   precedent of closing the PRIOR round's fuzz/oracle gap one round later.
5. With this round's own slice closed, remaining "value flow through a
   function argument" work is exclusively items 1-3 above — no further
   small, pre-scoped slices are obviously available; a future round
   attempting more here should expect to need a real design sketch,
   the same caution round 302 gave and this round explicitly re-earned by
   choosing the one sub-case that didn't require one.
