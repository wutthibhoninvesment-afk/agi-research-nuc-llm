# Round 314 (language C) — the "dynamic call graph" gap: investigated end to end, implemented, reverted — it is not a bug

## Pre-flight

`state/round_counter` was already `314`, but `logs/driver.log` showed round
313 was consumed with ZERO `round 313 ...` lines of any kind — the driver
jumped straight from round 312's own health-check PASS (07:10:52) to `===
driver started; resuming after round 313 ===` (07:11:37). Investigated
before starting the language(C) work proper, since an apparently-lost round
number could mean real work vanished: `git stash list` empty, `git reflog`
shows no activity between round 312's own commit and round 314's start, and
no repository file (other than driver bookkeeping — `state/round_counter`,
`state/.driver.lock`, `logs/*`) has an mtime in the 07:10:00–07:12:00
window. Conclusion: identical shape to round 259's own round-229 finding — a
round number consumed with no evidence any work was ever started, not a
lost-work incident. Recorded as a new entry in `state/known-record-gaps.json`
(round 313, alongside the existing round 229 entry) so no future round
re-investigates it from scratch — the file's own stated purpose
("`missing_round_numbers`... same 'verified once, don't re-investigate
every future audit' spirit"). `ps -eo pid,ppid,etime,cmd` showed only this
round's own driver process tree ([[feedback_check_for_concurrent_rounds]]).
`git status --porcelain` showed only `state/round_counter` and the 4
Hermes-owned `languages/whence/` files, both covered by `state/
known-standing-dirty-paths.json` ([[feedback_check_cached_diff_before_
commit]]) — nothing to land before starting.

## Task selection

Round 312's own next-steps item 1 named the dynamic call graph as "now the
ONLY item left" in the "value flow through a function argument/return"
backlog first flagged at round 270, with an explicit recommendation:
"approach (1) [declared-superset propagation] is the natural next step if
the goal stays 'extend this existing family.'" Took that at face value and
implemented it in full — see "What was built and reverted" below — because
the fastest way to find out whether a design sketch is actually soundly
implementable is to actually implement it against the real test suite, not
to re-derive it on paper a second time.

## What was built (then fully reverted — `git diff` after this round is
## empty for every `.py` file)

A ninth scope-stack, `Parser.fn_effects_scopes`, mirroring `param_call_
scopes`'s own three push/pop sites exactly (`stmt_list`'s per-block frame,
the named-fn params-frame push/pop in `statement()`, the anonymous-fn
params-frame push/pop in `primary()`) and its own placeholder-then-overwrite
discipline (staked to `None` under a fn's own name before its body is
parsed, overwritten with the fn's own fully resolved `effects [...]` scope —
UNCONDITIONALLY this time, unlike `param_call_scopes`'s own gate on "did the
body call one of its own params"). A new resolver, `_resolve_fn_effects_
scope`, an exact mirror of `_resolve_param_call_fact`'s innermost-first walk.
A new check, `_check_call_graph_effects(callee, tok)`, wired into
`postfix()` alongside the other three call-site checks: for a plain
`helper(...)` call where `helper` resolves to a tracked scope, compute
`callee_scope - caller_scope` (`caller_scope` = `effects_stack[-1]`) and
raise if non-empty. A new `A.FnExpr.fn_effects_scope` field for the
anonymous-fn case, carried the same way `param_call_fact` already is.

This is a completely mechanical, well-tested-pattern implementation — every
push/pop site, every placeholder, the resolver shape, all follow this
family's own established conventions exactly, verified against the
established recursion/shadowing edge cases FIRST via manual parser probes
before touching the test suite:
- Self-recursion (`fn f() effects [] { f() }`): correctly invisible (sees
  its own `None` placeholder, same as every other stack in this family).
- Mutual recursion (`fn a() effects [] { b() }` then `fn b() effects [] {
  a() }`, in that order): `a`'s call to `b()` is invisible (`b` isn't bound
  at all yet while `a`'s body is parsed — a genuine forward reference, not
  just a placeholder), but `b`'s call to `a()` IS checked (`a`'s scope is
  fully resolved by the time `b`'s body is parsed) — an asymmetric
  under-approximation, never a crash or an over-approximation, needing NO
  explicit cycle detector at all, contrary to what round 312's own SPEC.md
  sketch worried it might ("would need real fixed-point iteration ... an
  explicit call-graph-cycle detector"). This is a genuine correction to
  that sketch, confirmed by direct testing: the family's existing
  placeholder-before-parse discipline already handles it for free, the
  exact same way it already makes every OTHER forward reference in this
  family invisible rather than wrong.
- Unrestricted callee (no `effects [...]` clause at all): correctly
  invisible — `own_effects_scope` resolves to `None`, collapsed with "not a
  tracked fn at all" by design, for backward compatibility (see the
  docstring written for `_check_call_graph_effects` during this
  investigation, quoted in full in the diff history — not preserved in the
  final tree since the change was reverted).
- The basic grant/deny pair from SPEC.md's own v0.14.13 example (`fn
  helper() effects [io] { print(1) }` / `fn outer() effects [] {
  helper() }`) behaved exactly as that section's own text predicted:
  `outer()` calling `helper()` raised `ParseError`.

## Why it was reverted: `tests/test_v14.py` fell from 113 to 105 passed

Running the full existing suite (not just the new manual probes) immediately
surfaced 8 failures. Reading each one in full, not just the pytest summary
line, was the whole finding:

**Seven were TRUE FALSE POSITIVES** — previously-legal, already-tested,
deliberately-designed programs the new check would newly reject, ALL of the
identical shape: a NAMED fn with its own EXPLICIT, sufficient `effects
[...]` clause, called from a MORE TIGHTLY SCOPED enclosing fn:
`test_nested_undeclared_fn_escapes_outer_purity`, `test_three_way_nested_
escape`, `test_inner_fn_with_same_param_name_is_checked_against_its_own_
scope`'s second `all_ok` block, `test_param_rename_in_enclosing_fn_not_
misattributed_to_inner_fn`, `test_param_forwarding_shadowed_name_is_not_
misattributed`, `test_param_forwarding_only_correct_position_is_matched`,
`test_param_forwarding_via_non_nameref_argument_still_not_checked`.

**The eighth** (`test_param_forwarded_to_second_function_that_calls_it_is_
now_checked`) was not a false positive — both old and new code reject the
program — but the new check fires EARLIER and UNCONDITIONALLY (at the inner
call's own parse time, independent of which argument is ever passed),
preempting `_check_call_site_param_effects`'s own argument-dependent
message/location with a different one. Proof the new check does not
COMPOSE with the existing argument-flow mechanisms; it races and shadows
them.

### The root cause is not a bug in the new code — it's a real philosophical
### conflict with the family's own founding design

Two independent pieces of evidence, both already IN the codebase before this
round, both directly contradicted by "caller must be a superset of callee":

1. **v0.14 itself (round 146, this file's own very first effect-system
   section)**: "A declaration vouches ONLY for calls made directly,
   textually, in that function's own body ... Calling a DIFFERENT,
   unrestricted function that itself prints is likewise untouched by the
   caller's declaration." Cites `test_nested_undeclared_fn_escapes_outer_
   purity` BY NAME as the pin for this. This is not an oversight later
   rounds forgot to widen — it is the effect system's OWN stated, original,
   deliberate scope boundary, unchanged across eleven point releases.
2. **v0.14.9 (round 300)**: `test_check_uses_callees_own_scope_not_the_
   callers` states the mirror principle for the param-flow sub-family:
   "The check is against `apply`'s OWN declared effects scope, not the
   CALLING scope's ... An unrestricted top-level call site may freely call
   `apply(print)` as long as `apply` ITSELF permits `io`." A function's own
   `effects [...]` clause is a self-contained, already-verified contract;
   calling a fn whose OWN contract is satisfied is always safe regardless
   of the CALLER's own declared scope.

Declared-superset propagation collapses two questions this family has
always kept separate — "is this fn's own declared scope internally
consistent with its own body" (checked once, at definition, callee-scoped)
vs. "does calling this fn require something the CALLER didn't declare" (a
question this family has never asked, on purpose) — into one. There is no
narrower version of "compare caller's scope to callee's scope at every call
site" that avoids re-litigating the first question the family already
answered the OPPOSITE way for the param-flow cases. This is not a tuning
problem; it is a genuine design incompatibility discovered only by actually
implementing the sketch and running the whole suite against it, not by
re-reading the sketch a second time.

## What this closes

The "dynamic call graph" item — carried as an open backlog line across
rounds 270, 302, 306, 308, 311, 312 — is CLOSED as of this round, not by
implementation but by determining it describes the effect system's own
founding, deliberate, still-correctly-tested scope boundary, not an
accidental gap. Documented in full in `SPEC.md`'s new "v0.14.14 (round
314)" section (placed, in the file's own version-ordered convention,
between v0.14.13 and v0.15), including the corrected guidance for any
future round that revisits this: either (a) accept it as an intentional,
LARGE, breaking redesign that updates the seven named tests to a genuinely
new transitive semantics, or (b) scope a real "approach 2" (full bottom-up
effect inference) as its own explicit large feature — never as a quiet
v0.14.x point release layered on top of the existing design. Also corrected
a small factual error in round 312's own sketch: it suggested any real
future attempt would need "its own `v0.15`-class version bump" — but
`v0.15` is already taken (round 168, `guess`/confidence) — so a real future
attempt would need a different major slot (e.g. `v0.17`).

## Verification

- No `.py` file differs from round 312's own committed state — `git diff
  --stat -- '*.py'` over `languages/whence/` is empty.
- `tests/test_v14.py`: confirmed back at **113 passed** (was transiently
  105/113 with 8 failures during the investigation; fully reverted).
- `run_tests_fast.sh` (languages/whence): **943 passed, 38 deselected**,
  byte-identical to round 312's own post-landing baseline.
- Full unfiltered `pytest tests/` (backgrounded to a real log file):
  confirmed still **981 passed** (round 312's own baseline), run as a
  final sanity check after the revert.
- Cross-track: `bash harness/run_tests_fast.sh` → **412 passed, 223
  deselected**, byte-identical to round 312's own post-landing baseline —
  confirms zero changes outside this round's own `SPEC.md`/`state/
  known-record-gaps.json`/knowledge-file/research-state.md touches.
- `git status --porcelain` before finishing showed only `SPEC.md`,
  `state/known-record-gaps.json`, `state/research-state.md`, this
  knowledge file, plus the standing `state/round_counter` and 4
  Hermes-owned files.

## Still open

1. The effect system's "dynamic call graph" gap is now formally CLOSED as
   a backlog item (see above) — not by implementation, by determination
   that it is by-design. No future language(C) round should re-open it
   without first reading this round's own SPEC.md section and choosing
   explicitly between the two large-scope options named there.
2. Fuzz coverage (`harness/swe/fuzz.py`) and oracle coverage (`harness/
   swe/alias_effects.py`) for v0.14.13's own forwarding shape (round 312's
   own item 2, restated unchanged across rounds 312→314 since no SWE-loop
   D round has run since 311) — the natural next SWE-loop(D) round.
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
7. `fuzz-mutate-kill-loop/SKILL.md` at 415/500 lines is now the ONLY
   skill within 100 lines of the hard cap — round 310's item 4, unchanged.
8. The `tail`/EOF backgrounded-pipe silent-drop mechanism remains
   genuinely unconfirmed — round 310's item 5, unchanged.
9. The recent-window heavy/light fail-rate ratio re-check and round 295's
   own blocking-wait root cause design sketch — round 301's items 1-2,
   unchanged.
10. `EditFileTool` (round 307): no diff preview, and `harness/swe/
    regiontools.py`'s region-patch mechanism left deliberately un-unified
    with it — round 307's items 1-2, unchanged.
