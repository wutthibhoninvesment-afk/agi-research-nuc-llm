# Round 312 (language C) — Whence v0.14.13: an argument forwarded through a SECOND function call, then called directly, is now tracked

## Pre-flight

`git status --porcelain` at the start of this round showed round 311's own
uncommitted diff (`harness/swe/alias_effects.py`, `harness/swe/fuzz.py`,
`harness/tests/test_swe_alias_effects.py`, `harness/tests/test_swe_fuzz.py`,
`state/research-state.md`, `state/round_counter`) plus an untracked round
311 knowledge file — round 311's own work was fully documented (a complete
`### Round 311` section already in `research-state.md`, plus its knowledge
file) but had never been `git commit`-ted, exactly the
`recorded_but_uncommitted_rounds` gap the automated pre-flight check named.
Verified the staged diff matched round 311's own documented summary
exactly, confirmed the untracked `languages/whence/` files were the
already-allowlisted standing Hermes-owned ones
([[project_hermes_gateway_shares_the_repo]]), and committed round 311's
diff as its own commit before starting this round's own work
([[feedback_check_cached_diff_before_commit]]). `ps -eo pid,ppid,etime,cmd`
showed only this round's own driver process tree
([[feedback_check_for_concurrent_rounds]]) — no concurrent round running.

## Task selection

`research-state.md`'s next-steps as of round 311 (item 1) named the two
remaining "value flow through a function argument/return" gaps — an
argument reaching an effectful builtin through a SECOND function call, and
the dynamic call graph — as flagged across FOUR consecutive language(C)
rounds (302, 306, 308, 311) as needing "a real design sketch, not another
small pre-scoped slice." Took that seriously: read `_check_effect_call`'s
full docstring, `_check_call_site_param_effects`'s full docstring, and the
whole `param_call_scopes`/`param_alias_scopes`/`return_param_scopes`
mechanism end to end before choosing anything.

The key realization: the "second function call" gap and the "dynamic call
graph" gap, despite being named together since round 270, are NOT the same
shape. The former is a DATA-FLOW question — does a specific argument reach
a directly-called sink through one more hop — answerable by composing an
EXISTING fact (`param_call_scopes` already records, per fn, "which of my
own params do I call directly") across one more call boundary. The latter
is a CONTROL-FLOW/DECLARATION question — does calling an unrestricted
function that unconditionally performs an effect (no parameter involved at
all) violate the CALLER's own declared scope — and would need the family's
first ever scope-vs-scope comparison, a structurally different check. This
round closes the first (implemented, tested, shipped as v0.14.13) and
writes an honest design sketch for the second (SPEC.md's "v0.14.13"
section — analysis only, deliberately not implemented this round).

## Design: v0.14.13

**The core insight**: `Parser.param_call_scopes` already records, for
EVERY named fn (or `let`-bound anonymous one), "which of my own params
does my body call directly" (v0.14.9, round 300) — a fact fully resolved
by the time that fn's OWN body finishes parsing, strictly BEFORE any
caller of it can be parsed (single left-to-right pass, forward refs
already invisible everywhere else in this family). So when `outer`'s body
itself calls `inner(f)` (where `f` is one of `outer`'s own params), all
that is needed is: does `f`'s ARGUMENT POSITION at this call match one of
`inner`'s own recorded DIRECTLY-called param positions? If so, `outer`
ITSELF now counts as "calling `f` directly" too — recorded into the exact
same `direct_param_calls_stack[-1]` v0.14.9's leading block already
populates for a truly direct call.

**New method, `_check_param_forwarding(callee, args, tok)`**, called from
`postfix()` alongside `_check_effect_call`/`_check_call_site_param_
effects` at every call expression (`whence/parser.py`). For a callee with
a recorded `param_call_fact` (`_resolve_param_call_fact(callee.name)`), it
walks each of the target fn's own directly-called param positions; if the
argument AT that position resolves — identity, or a same-body rename
chain via the new `_resolve_current_fn_param` helper — to one of the
CURRENTLY open fn's own params, that param is added to the current fn's
own `direct_param_calls_stack[-1]`.

**Zero new scope-stack** — the first addition in this family (v0.14.4
through v0.14.12 each added at least one new stack) that needed none at
all: this is pure composition of a fact this family already computes,
not a new kind of fact.

**New shared helper, `_resolve_current_fn_param(name)`**, factored out of
duplicated logic: `_check_effect_call`'s own leading v0.14.9 block (an
identity check against `current_fn_params_frame_stack[-1]`, falling back
to `_resolve_param_alias` for a same-body rename) and `_tail_return_param_
name` (v0.14.12) had the IDENTICAL "innermost-first frame-identity check,
else `_resolve_param_alias`" shape duplicated. `_check_param_forwarding`
is now a third caller, applied to a call's ARGUMENTS instead of its
callee or a block's tail — refactored both existing call sites to use the
shared helper (behavior-preserving; ran the full `test_v14.py` suite
immediately after the refactor, before writing any new code, to confirm
zero regressions from the dedup alone).

**`_check_call_site_param_effects` needed ZERO changes** — the exact same
"one resolver produces the fact, this method just consumes it generically"
separation this family has kept since v0.14.9: it already walks
`_resolve_param_call_fact("outer")` indifferent to whether `f`'s
membership in `outer`'s own `called_params` came from a direct call, a
same-body rename, or (now) a one-level-removed forward.

**Composes to ARBITRARY depth for free.** If `innermost(h) effects [io] {
h(1) }`, `inner(g) effects [io] { innermost(g) }`, `outer(f) effects [io]
{ inner(f) }` are declared bottom-up (the same declaration-order
constraint already binding every fact in this family), `inner`'s own
`param_call_scopes` entry already reflects the forward through
`innermost` by the time `outer`'s body is parsed — so `outer`'s own
forward-through-`inner` check transitively picks it up too, with no
explicit recursion in the new code at all. Verified directly (manual
parser probes, before writing any test) with a real 3-hop chain before
committing to the design.

## Verification narrative (design confirmed against real parse behavior first)

Before touching `tests/test_v14.py`, ran the design against six manual
probes via the parser directly:
1. Basic 2-hop forward, `outer effects []`: correctly raises.
2. Same shape, `outer effects [io]`: correctly granted (outer's own scope
   already permits it, same as v0.14.9's own baseline).
3. 3-hop transitive chain (`innermost`/`inner`/`outer`), `outer effects
   []`: correctly raises — confirms the "composes for free" claim above
   against real parser state, not just reasoning about it.
4. Shadow safety: a nested `helper` fn with its own local `let f = 5`
   forwards the SHADOWING local into `inner(f)`, not `outer`'s own param
   — correctly does NOT raise.
5. Forwarding target is a `let`-bound anonymous fn (v0.14.10's own shape),
   not a named one: correctly raises — confirms `_resolve_param_call_
   fact`'s existing genericity extends here with zero extra code.
6. Non-NameRef argument (`inner(id(f))`, wrapped through a third fn):
   correctly does NOT raise — confirms the deliberate "bare NameRef only"
   boundary holds.

The first attempt at these probes (an early debugging pass) initially
reported all six as failing — traced to a test-design mistake, not a code
bug: the first draft's "should be denied" cases declared `outer` with
`effects [io]` (which already grants io regardless of any forwarding
mechanism, per `_check_call_site_param_effects`'s own "check against the
CALLEE's own declared scope" design, v0.14.9) instead of `effects []`.
Corrected the test scenarios (not the implementation) and re-ran; all six
passed as designed. Recorded here since it is exactly the kind of mistake
[[debug-mantra]]-style tracing catches quickly — re-reading the actual
check being exercised, not just the shape of the source, before
concluding the code was wrong.

## Deliberately narrow, updated boundaries

- Only a call whose callee is a bare NameRef with a recorded `param_call_
  fact` is inspected — a fn used any OTHER way has nothing to key off,
  same "nothing to check without SOME name" boundary this whole family
  already has.
- Only an ARGUMENT that is itself a bare NameRef (or a same-body rename
  chain of one) is checked — an argument that is itself a call, field
  access, or any other expression shape is invisible
  (`test_param_forwarding_via_non_nameref_argument_still_not_checked`).
- A param that is FORWARDED then RETURNED (or renamed, or forwarded a
  second time) by the callee, not called, remains invisible —
  v0.14.12's `return_param_scopes` and this mechanism are still two
  genuinely separate mechanisms, not unified
  (`test_param_forwarding_does_not_disturb_returned_param_mechanism`,
  restating the pre-existing `test_param_passed_through_a_second_
  function_before_return_is_still_not_checked` under this round's own
  section for discoverability — unchanged regression pin, not a new
  finding).
- Forward-referenced or mutually-recursive fns are invisible, same as
  every other fact in this family: single left-to-right pass, no
  fixed-point/whole-program analysis.
- **The dynamic call graph remains the ONE gap this family has never
  started** — see SPEC.md's "v0.14.13" section for the full honest design
  sketch: why it needs the family's first ever scope-vs-scope comparison
  (not a per-argument tag comparison), why it cannot be closed the same
  way as this round's own fix, and two structurally different approaches
  a future round could choose between (declared-superset propagation with
  explicit cycle detection, vs. full bottom-up effect inference — the
  latter a substantially larger feature, likely warranting its own
  `v0.15`-class version bump rather than a `v0.14.x` point release).

## Verification

- `tests/test_v14.py`: 105 → **113 passed** (8 new: the direct grant/deny
  pair, a 3-hop transitive-composition pair, a let-bound-anonymous-fn-
  target case, a rename-before-forward case, a shadow-safety case, a
  positional-correctness case, a non-NameRef-argument negative case, and
  a restated regression pin for the still-open return-boundary-via-
  second-call gap).
- `examples/effects.lang`: gained one new demo (`apply_logger_via`,
  forwarding `f` into `apply_logger`'s own directly-called argument), run
  directly via `python3 run.py examples/effects.lang`: checks 13 → **14
  passed, 0 failed**.
- `tests/test_examples.py::test_effects` and `tests/test_self_hosting.py`'s
  guest-parity pin both updated to 14 checks — the guest needed **zero
  code change**, the fifth round in a row (v0.14.9/10/11/12/13) this exact
  family has been purely host parse-time bookkeeping invisible to the
  guest evaluator (no new AST field at all this round, unlike v0.14.10's
  `A.FnExpr.param_call_fact` or v0.14.12's `A.Block.tail_param_name`).
  `pytest tests/test_examples.py tests/test_self_hosting.py -q` →
  **34 passed** in 83.22s.
- `run_tests_fast.sh`: 935 → **943 passed, 38 deselected** (+8 exact, no
  other file's count moved).
- `bench/ref_diff.py --counters examples/*.lang` (redirected to a real
  file, not piped through `tail` while backgrounded — the standing
  pitfall this repo has repeatedly flagged): **0 differing pairs**,
  `effects.lang` reads `checks=14` identically across direct/fast/slow.
- Full unfiltered `pytest tests/` (backgrounded to a real log file, not
  piped through `tail` while backgrounded): **981 passed, 0 failed** in
  316.79s (was 973 at round 308's own baseline — the +8 is this round's
  own net new test count exactly, matching `test_v14.py`'s own delta
  one-for-one).
- Cross-track regression: `bash harness/run_tests_fast.sh` (repo root)
  unchanged from round 311's own post-landing baseline — confirms this
  round's diff touched nothing outside `languages/whence/`.
- `git status --porcelain` before committing showed only the files this
  round intentionally touched (`SPEC.md`, `examples/effects.lang`,
  `tests/test_examples.py`, `tests/test_self_hosting.py`,
  `tests/test_v14.py`, `whence/parser.py`) plus the standing `state/
  round_counter` and 4 Hermes-owned files.

## Still open

1. The dynamic call graph — completely untouched; a fundamentally
   different, larger problem than every fact-composition slice that
   came before it in this family, sketched (not implemented) in SPEC.md's
   "v0.14.13" section. With this round's own gap closed, this is now the
   ONLY item left in the "value flow through a function argument/return"
   backlog first flagged at round 270 — no longer paired with a sibling
   gap, so the next language(C) round attempting it should expect to
   make (and document) an explicit choice between the two sketched
   approaches (declared-superset propagation vs. full effect inference)
   rather than treating it as one more incremental slice.
2. Fuzz coverage (`harness/swe/fuzz.py`) and oracle coverage (`harness/
   swe/alias_effects.py`) for THIS round's own new v0.14.13 forwarding
   shape — the natural next SWE-loop(D) round, following the exact rhythm
   round 311 itself set for v0.14.11/v0.14.12 (round 305 covered v0.14.9/
   10; round 311 covered v0.14.11/12; this round's own v0.14.13 is now
   the next gap in that same sequence).
3. `rand()` deliberately narrow (arity 0 only) — round 294's item 4, still
   not yet justified by a concrete need.
