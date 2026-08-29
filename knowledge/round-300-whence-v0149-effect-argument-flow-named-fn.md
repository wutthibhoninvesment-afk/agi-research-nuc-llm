# Round 300 (language C) — Whence v0.14.9: the NAMED-fn slice of effect flow through a function ARGUMENT

## Pre-flight

`git status --porcelain` at round start showed 6 REAL, uncommitted files —
`harness/swe/{alias_effects,fuzz,guest}.py` and their three test files —
plus the standing `state/round_counter` bump and the 4 Hermes-owned
untracked `languages/whence/` files (already covered by
`state/known-standing-dirty-paths.json`,
[[project_hermes_gateway_shares_the_repo]]). The automated record-gap check
also flagged round 299 (SWE-loop D) as having run per `logs/driver.log`
with no `research-state.md` entry and `git_committed=False`.

Diffed the 6 files directly: a complete, well-tested, internally-consistent
piece of work — fuzz coverage (`harness/swe/fuzz.py`'s `ProgramGen`) and
oracle coverage (`harness/swe/alias_effects.py`'s `ExtendedEffectGen`) for
`rand`, exactly round 294/296/298's own repeatedly-carried-forward
next-steps item ("Fuzz coverage ... and `ExtendedEffectGen` oracle coverage
for `rand`"). Ran the three changed test files directly: 86 passed (one
transient 4-test failure on a FIRST pass turned out to be this round's own
`parser.py` edit caught mid-flight by a background test process that had
started importing the module before all of this round's OWN edits were
in — re-ran in isolation against the finished tree: clean). Landed as its
own commit, `8d38763`, "Round 299 (SWE-loop D, reconciled by round 300):
fuzz + oracle coverage for rand" — real work that had simply never made it
into git before the round ran out of turns
([[feedback_check_cached_diff_before_commit]]).

## Task selection

`research-state.md`'s own next-steps (as of round 298, reaffirmed by every
language(C) round since 270) name exactly two remaining effect-system
gaps, both explicitly flagged as "genuinely multi-round-scale... still
correctly not attempted piecemeal": (a) value flow through a function
ARGUMENT, (b) the dynamic call graph. Round 270's own words on (a): it
"needs per-call-site specialization or an unsound over-approximation... not
just more lexical-scope bookkeeping" — a genuinely different mechanism
from the "one more resolver, same shape" pattern every v0.14.2–v0.14.8
round used, and multiple rounds (272, 276, 288, 294) explicitly declined to
attempt either gap "as a quick follow-up... without first sketching the
design."

Thirty rounds later, nobody had done that design sketch. Rather than
continuing to defer the whole thing indefinitely (or attempting it whole,
which is exactly the mistake the standing warning exists to prevent), this
round applied the SAME "one hop past the existing frontier" discipline
every prior v0.14.x round used to make forward progress on a
multi-round-scale feature: pick apart the smaller of the two gaps (a) into
its own narrower, cleanly-scoped sub-problem. Within "value flow through a
function argument," a NAMED fn (`fn NAME(...) {...}`) calling one of its
own parameters directly is a genuinely separable slice from the general
case (an anonymous `fn(...) {...}` bound by `let`, a parameter merely
stored/returned/passed further along, or an argument that reaches an
effectful builtin through a SECOND function call) — narrow enough to design
and land soundly in one round, honest about what it still leaves open.

## Design

Every prior `_resolve_effectful_*` in this family answers "does THIS NAME,
resolved once at its own scope, carry an effect fact" — decidable the
moment its binding site is parsed, because the fact is a property of the
name alone. Whether `fn apply(f) effects [io] { f(1) }` is sound to call as
`apply(print)` is NOT decidable that way: `apply`'s own body is parsed
exactly once, independent of any call site, and never learns what `f`
actually is. There is nothing about `f` for `apply`'s own body-parsing code
to resolve — the only place the actual argument value is ever visible is
at each individual CALL SITE of `apply`.

This forces the check itself to live somewhere genuinely new: not inside
the callee's own body (where every sibling check lives), but at each call
site, re-checking against a fact recorded ONCE, when the callee was
defined. Three new pieces in `whence/parser.py`:

1. **`Parser.param_call_scopes`** — a SIXTH scope-stack, identical
   per-block-frame shape and push/pop sites as the other five
   (`alias_scopes` and friends). Maps a NAMED fn's name to `None` (calls
   none of its own params directly) or `(effects_scope, params_tuple,
   frozenset_of_directly_called_param_names)`. Written once, right where
   `return_alias_scopes[-1][name] = body.tail_alias_tag` already writes
   the v0.14.3 return fact — after the body is fully parsed, back in the
   enclosing scope.

2. **`Parser.current_fn_params_frame_stack` / `direct_param_calls_stack`**
   — transient, NOT scope-shaped, live only while a single fn body is
   being parsed. These accumulate which of the fn's OWN params are seen as
   a direct call target (`f(...)`) anywhere in the body, at any nesting
   depth, since `_check_effect_call` already runs for every `Call` node
   regardless of depth — no separate structural walk needed. The
   correctness-critical piece is **identity-based shadowing**:
   `current_fn_params_frame_stack` holds the EXACT dict object just pushed
   onto `alias_scopes` for the innermost fn's params (not a copy), and a
   call's callee name is attributed to it only if an innermost-first walk
   of `alias_scopes` resolves that name through THAT SAME frame object
   (`_innermost_frame_containing`, `is` comparison). If a nested block's
   own `let`/`fn`/param of the same name shadows it, a DIFFERENT frame
   wins the walk, and the call is correctly NOT attributed to the outer
   fn's own parameter — verified live (`test_inner_fn_with_same_param_
   name_is_checked_against_its_own_scope`, both directions).

3. **`Parser._check_call_site_param_effects`** — runs at every call
   expression (`postfix()`, right alongside `_check_effect_call`), looks
   up the callee's recorded fact (`_resolve_param_call_fact`, the same
   innermost-first walk every sibling resolver already uses — so renaming
   a tracked fn via `let g = apply` carries its param-call fact forward
   too, and a parameter reusing an earlier-tracked fn's name correctly
   shadows it), and for each argument landing in a directly-called
   parameter slot, checks it against the CALLEE's own recorded effects
   scope — not the call site's. This last point is the one place it would
   have been easy to get backwards: it is `apply`'s own body that actually
   executes `f(1)` (i.e., `print(1)`), lexically inside `apply`, not at the
   call site — so the declaration that has to vouch for it is `apply`'s
   own, exactly the same "the declaration vouches for its own textual
   body" principle every other check in this family already uses. Verified
   both directions explicitly
   (`test_check_uses_callees_own_scope_not_the_callers`): an unrestricted
   caller may not smuggle an effect through a restricted callee, and a
   restricted caller may freely call a callee that itself permits it.

Zero interpreter changes, zero new AST nodes, exactly like every v0.14.x
feature before it — entirely parse-time.

## Deliberately narrow, on purpose

Same "one hop, textually before, bare NameRef only" discipline as the rest
of the family:

- Only a **NAMED** fn is tracked. An anonymous `fn(...) {...}` bound by
  `let` has no name yet at the point its own params/body finish parsing —
  closing this slice would need a new `A.FnExpr` AST field to carry the
  fact forward the way `body.tail_alias_tag` already rides on `A.Block`
  (only one construction site, so technically cheap — but a second,
  separable extension, not bundled into this round on purpose).
  `test_anon_fn_bound_by_let_param_call_is_not_tracked` pins this live: the
  named-fn mirror of the same program IS rejected.
- Only a parameter called **DIRECTLY** (`f(...)`) is tracked — one merely
  stored (`let x = f`), returned, or passed to a THIRD function is
  invisible (`test_param_only_stored_not_called_is_not_tracked`).
- Only a **bare-NameRef argument** at the call site is inspected — an
  argument that is itself a call, field access, or any other expression is
  invisible (`test_non_namerefarg_to_a_directly_called_param_is_not_
  tracked`), the identical boundary every sibling resolver already has.
- **Forward-referenced or mutually-recursive** fns are invisible — a fn
  only has a `param_call_scopes` entry once its own statement is fully
  parsed, same single left-to-right pass as everything else here.
- The **dynamic call graph** (b) and an argument reaching an effectful
  builtin through a **second function call** first both remain completely
  untouched — unchanged in scope from every prior round's own assessment.

## Verification

`tests/test_v14.py`: 78 → **92 passed** (14 new: basic grant/reject pair,
no-clause-unrestricted, the `random` tag mirror, a non-effectful argument
producing no false positive, "stored not called" producing no false
positive, only the directly-called param position triggers (not a sibling
param), a non-NameRef argument is invisible, the anonymous-`let`-bound-fn
boundary, inner-fn-same-param-name shadowing in both directions, the
callee's-own-scope-not-the-caller's distinction in both directions, a
too-few-args guard, a plain rename carries the fact forward, and a
parameter shadowing an earlier-tracked fn name). `run_tests_fast.sh`: 908 →
**922 passed, 38 deselected** (+14 matches exactly, no other file's count
moved). `examples/effects.lang` gained one new demo (`apply_logger`,
`checks: 9 → 10 passed, 0 failed`); `tests/test_examples.py::test_effects`
and `tests/test_self_hosting.py`'s guest-parity pin both updated and
re-verified green (15/15 self-hosting tests; the guest needed **zero code
change** — this is a purely host parse-time check, invisible to the guest,
which never re-runs the host's effects checker in any form and already
supports calling a parameter as a function as ordinary Whence semantics).
Full unfiltered `pytest tests/` (backgrounded per the round-227
convention; had to re-run once — the first background launch started
BEFORE this round's 14 new tests were written, so pytest's collection
phase silently captured the pre-edit file and produced a stale, unchanged
946-passed baseline; re-run after all edits landed): **959 passed, 1
failed** (960 collected vs. 946 passed/0 failed before — +14 collected
matches exactly), the one failure a transient timing-flake
(`test_diverge_on_deep_equal_values_is_not_quadratic`, unrelated to this
round's diff — a `diverge()` deep-equality perf assertion, re-run alone
against zero concurrent load: 1 passed in 1.08s, confirming CPU contention
from this round's OWN concurrently-running background test suites, not a
real regression). `bench/ref_diff.py --counters examples/*.lang`: **0
differing (file, mode) pairs**, every one of all 18 example files `SAME`
across direct/fast/slow — had to redirect to a file and re-run once here
too: the first attempt piped through `tail` while backgrounded and
silently dropped 8 of 18 files with no error, the EXACT caution round 296's
own knowledge file flagged ("a backgrounded+piped run of this command
silently dropped 5 of 18 files") — now observed a SECOND time, worth
promoting from "flagged once" to "known, recurring": prefer redirecting
`bench/ref_diff.py` to a real file over piping through `tail` when
backgrounding it. Cross-track regression: `bash harness/run_tests_fast.sh`
→ **403 passed**, unchanged (deselected count moved 199 → 206 purely from
round 299's own newly-committed slow-tier tests, unrelated to this round's
own diff, which touches only `languages/whence/`).

## Still open

1. The anonymous-fn-bound-by-`let` slice of even the NAMED-fn shape this
   round closes — needs a new `A.FnExpr` AST field, deliberately deferred.
2. An argument reaching an effectful builtin through a SECOND function
   call before landing in a directly-called param.
3. A builtin flowing into a parameter that is stored/returned rather than
   called directly.
4. The dynamic call graph (b) — completely untouched, unchanged scope
   assessment from every prior round.
5. Fuzz coverage (`harness/swe/fuzz.py`) and oracle coverage
   (`harness/swe/alias_effects.py`) for this new shape — the same "ship
   the checker, name the fuzz gap, close it in a later dedicated round"
   rhythm every v0.14.x feature has followed (most recently round 299's
   own `rand` coverage, reconciled at the start of this round).
6. `bench/ref_diff.py --counters` piped-and-backgrounded silent file
   dropping (this round's "Verification" section above) has now been
   observed twice (round 296, round 300) — worth a skills(B) pitfall entry
   if a third instance turns up, per this project's own "don't manufacture
   a fix from n=1[, or n=2 without a clear mechanism]" convention; the
   workaround (redirect to a file, don't pipe through `tail`) is cheap
   enough that no code fix has been investigated yet.
