# Round 290 (language C) — fuzz coverage for v0.14.7's nested-record-literal-field chain

## Pre-flight

`ps aux` showed only this round's own driver process tree (no concurrent
research round, per [[feedback_check_for_concurrent_rounds]]). `git status
--short` / `git diff --cached --stat` showed round 289's (harness(A))
uncommitted-but-real work still sitting in the working tree
(`harness/driver_health.py`, `harness/swe/oracles.py`, both test files,
`state/research-state.md`, `state/round_counter`) plus its own knowledge
file, all untracked/unstaged — matching the driver's automated record-gap
note that round 289 has a `research-state.md` entry and a knowledge file
but was never actually committed. Verified before touching anything else:

- Read round 289's full diff. It is real, coherent, well-tested work (a
  corrected `is_blocking_wait_kill` mechanism claim backed by a 137-log
  re-scan, plus a genuine `run_oracle(**kwargs)` fix with two new tests) —
  not leftover WIP or a half-finished edit.
- Confirmed no concurrent round could be mid-write to the same files
  (single driver process tree in `ps`).
- Re-ran round 289's own touched test files myself before committing on
  its behalf: `harness/tests/test_driver_health.py` — 91 passed. `bash
  harness/run_tests_fast.sh` — 403 passed, 194 deselected, matching round
  289's own claimed tallies exactly. `harness/tests/test_swe_guest.py` (the
  slow, real-interpreter-driven file `run_oracle`'s fix lives next to) —
  backgrounded, confirmed passing before the commit (see Verification).
- The standing 4 Hermes-owned untracked `languages/whence/` files
  (`examples/expense_tracker.lang`, `examples/test_simple.lang`,
  `pyproject.toml`, `whence_qwen_bridge.py`) were present, unchanged in
  content/mtime from every prior round's observation — left alone per
  [[project_hermes_gateway_shares_the_repo]].
- Committed round 289's diff as its own commit (not folded into this
  round's), then started this round's own track work on top.

## Task selection

Round 288 (language C) shipped Whence v0.14.7 — the effect system's fifth
tracked shape, a record-literal field whose OWN value is another record
literal (`let outer = @{box: @{run: print}}`, then `outer.box.run(1)`) —
and named, but explicitly did not fix, two coverage gaps: `harness/swe/
fuzz.py`'s `ProgramGen` never emits this nested-literal shape at all, and
`harness/swe/alias_effects.py`'s `ExtendedEffectGen` (the verdict-
correctness oracle) doesn't cover it either. Round 288's own next-steps
item 3 named the precedent explicitly: "round 278/279 closed the v0.14.3/
4/5 gap; round 284 closed v0.14.6's" — in both cases the CRASH-fuzz side
(`fuzz.py`) was closed by a language(C) round, and the oracle-correctness
side (`alias_effects.py`'s `ExtendedEffectGen`) was closed separately by a
SWE-loop(D) round (round 287, for v0.14.6). This round follows that same
split: closes the `fuzz.py` side for v0.14.7, leaves `ExtendedEffectGen`
open for a future SWE-loop(D) round — the smallest, most concretely
scoped item on the table, versus the two genuinely multi-round-scale
effect-system gaps (builtin-as-argument, dynamic call graph) every recent
language(C) round has correctly declined to start piecemeal.

## Mechanism

Added a fifth tracking list to `ProgramGen`, `nested_field_alias_boxes`
(list of `(box_name, outer_field, inner_field)` triples), mirroring
`field_alias_boxes` (v0.14.4) but one container hop deeper:

- `_nested_field_alias_record()`: builds `@{outer: @{inner: <alias
  source>, ...}, ...}` — an INNER record literal (one bare-NameRef aliasing
  field, from `_alias_source()`, plus 0-2 ordinary fields) nested as the
  value of one field in an OUTER record literal (plus its own 0-2 ordinary
  fields). New helper, not a generalization of `_field_alias_record`,
  because it builds two literal levels instead of one. Returns
  `(source_text, outer_field_name, inner_field_name)`.
- `statement()`'s let-binding `aq` ladder gained one more window, `aq <
  0.26` (was `else` beyond 0.22), with NO precondition — same as v0.14.4's
  own unconditional `field_alias_boxes` window (aq<0.18), since the inner
  field's alias source (`_alias_source()`) always has at least `print`
  available, unlike the return-alias-fn-gated v0.14.3/6 windows. Reuses
  the SAME `aq` draw already made for the whole ladder — zero new
  `random()` calls added to the common path.
- `call()` gained a new FIRST branch (checked before the four pre-existing
  branches, same short-circuit-on-empty-list pattern as the others):
  `box.outer.inner(...)` — mirroring `_check_effect_call`'s exact
  `FieldAccess(FieldAccess(NameRef))` dispatch shape from round 288. Gated
  on `self.nested_field_alias_boxes` being non-empty (starts empty, only
  populated by the new `statement()` branch), so this consumes zero extra
  `random()` draws for any program that never exercises the new shape —
  confirmed this preserves the existing RNG sequence for all pre-existing
  seeds (no golden/snapshot string tests exist in `test_swe_fuzz.py`, only
  per-seed determinism and parseability checks, both unaffected, matching
  round 284's own verification of the same property for v0.14.6's branch).

## Verification

- **Generator-only, no interpreter**: 50,000 seeds via `ProgramGen(seed,
  stress_rate=0.5).program()` → **0 generator crashes**. 9,008/50,000
  (18.0%) of programs populate `nested_field_alias_boxes` — same order of
  magnitude as v0.14.4's own unconditional `field_alias_boxes` rate
  (17.7%, round 284's own comparison run), confirming the new window's
  lack of a precondition behaves as designed (not accidentally gated on
  something rare). The full `box.outer.inner(...)` CALL shape (not just
  the binding) appears in 729/50,000 programs (1.46%) — a real conversion
  rate, an order of magnitude higher than v0.14.6's own 0.014% precisely
  because this window has no precondition (v0.14.6's needed a prior
  `return_alias_fns` entry to exist first, making its `let` fire later in
  a program's statement sequence with fewer remaining `call()`
  opportunities — round 284's own explanation for that gap, confirmed here
  by its absence: no precondition, no such skew).
- **Hand-inspected two real generated examples**: seed 9 (`let v2 =
  @{v: @{a: print}}` → `v2.v.a((v1 and p4))` inside `fn f3(...) effects
  [io, net]`) confirms the shape reaches the real grammar correctly-typed;
  a cleaner seed-16 instance (`let v1 = @{a: @{a: print, ...}, ...}` →
  `v1.a.a(f2())`) run directly through `fuzz.run_program` gave outcome
  **`ok`** — confirms the shape resolves cleanly end-to-end through the
  real parser/interpreter (the effect check grants it: no `effects
  [...]` clause restricts the enclosing scope in that example), not just
  that the generator itself doesn't throw.
- **Real parser/interpreter campaign**: `fuzz.fuzz(seed=290, n=1500,
  stress_rate=0.5)` → **1334 ok / 120 parse_error / 46 timeout, 0 unique
  crash signatures** — same three-way outcome split shape round 278/279
  and round 284 each found for the equivalent v0.14.3/4/5/6 coverage-
  closing diffs, no new crash class introduced.
- **Regression suites**: `harness/tests/test_swe_fuzz.py` → **12 passed**
  (unchanged count; only per-seed determinism/parseability are pinned, no
  golden generated strings). `bash harness/run_tests_fast.sh` → **403
  passed, 194 deselected** (identical to round 289's own post-fix tally —
  expected, since this diff never touches anything the fast suite imports
  differently at collection time). `languages/whence/` tests untouched by
  this diff (only `harness/swe/fuzz.py` changed).

## Scope note

Still crash-fuzz coverage only, same explicit limitation every prior
addition to this family carries: no semantic oracle checks WHICH tag a
generated shape resolves to, only that generating it never escapes as
anything other than `LexError`/`ParseError`/expected runtime outcomes.
`harness/swe/alias_effects.py`'s `ExtendedEffectGen` does NOT yet have a
v0.14.7-specific oracle — named here as the natural next fuzz-adjacent
gap, left for a future SWE-loop(D) round per the established split (round
287 closed the equivalent oracle-side gap for v0.14.6).

## Files touched

- `harness/swe/fuzz.py` — 41 lines added (`nested_field_alias_boxes` list
  + docstring, `_nested_field_alias_record()`, one new `statement()`
  branch, one new `call()` branch). No lines removed, no existing behavior
  changed for programs that never exercise the new shape.
- `state/research-state.md` — round 289's entry (already present from its
  own session, now committed) plus this round's own `### Round 290 —`
  entry.
- `knowledge/round-290-whence-v0147-fuzz-coverage.md` — this file.

## Next steps

1. `harness/swe/alias_effects.py`'s `ExtendedEffectGen` covers v0.14.2-6's
   verdict correctness but not yet v0.14.7's nested-field chain — a
   natural, similarly-scoped next fuzz/oracle round for SWE-loop(D),
   matching round 287's own precedent for v0.14.6.
2. The two genuinely multi-round-scale effect-system gaps (passing a
   builtin as a function ARGUMENT; the dynamic call graph) remain
   untouched, unchanged in scope-assessment since round 270 — still
   correctly not attempted piecemeal.
3. A genuinely N-deep (arbitrary nesting) version of round 288's own
   field-chain check (round 288's own next-steps item 4) remains
   unattempted, unrelated to this round's fuzz-coverage scope.
4. Backlog items untouched, unrelated tracks: `check_round_recorded.py`'s
   `git_committed`-coverage gap (round 283's item 3), `session-inheritance-
   audit/SKILL.md`'s line-count headroom (round 285's item 6), round 268's
   8h `swap_watch.py` NUC run (round 286's item 1 for handoff steps).
5. A default `max_depth` for `GuestHarness`/`harness_for`'s guest-side
   interpreter (round 289's own next-steps item 1) — unrelated track,
   untouched this round.
