# Round 288 (language C) — Whence v0.14.7: effect-system CONTAINER-FIELD value flow through a NESTED record literal

## Pre-flight

`ps -eo pid,ppid,etime,cmd` showed only this round's own driver process
tree (`run_driver.sh` watcher + this session's `claude -p`) — no
concurrent research round, per [[feedback_check_for_concurrent_rounds]].
`git status --short` / `git diff --cached --stat` showed only the
standing 4 Hermes-owned untracked `languages/whence/` files (`examples/
expense_tracker.lang`, `examples/test_simple.lang`, `pyproject.toml`,
`whence_qwen_bridge.py`) rounds 279/281/283/286/287 already identified as
a separate autonomous system's own writes, plus the shared
`state/round_counter` bump — nothing to reconcile before starting, per
[[feedback_check_cached_diff_before_commit]].

## Task selection

Round 287's next-steps item 1 declared the effect-alias family's four
existing combinations {direct/return} x {bare-name/field} fully closed
for `ExtendedEffectGen`'s parse-time-VERDICT oracle across v0.14.2-6, and
item 2 restated (unchanged since round 270) that the two genuinely
multi-round-scale gaps — passing a builtin as a function ARGUMENT, and
the dynamic call graph — are correctly not attempted piecemeal.

Re-read `_check_effect_call`'s own docstring and v0.14.4's SPEC.md entry
for a THIRD kind of narrowly-scoped gap, the same way round 276 found the
if/else-tail shape and round 282 found the field-return-chain shape.
v0.14.4's docstring named it explicitly but never touched it: "a record
literal reached by a chain of hops (merged, copied, mutated) is likewise
invisible... a field whose value is itself a call (even one returning
`print`) resolves to `None`" — and separately, "the specific slice of
v0.14.4's own documented gap named but not touched" the v0.14.6 SPEC.md
entry restates as still open: **a field whose value is itself a NESTED
record literal**, e.g. `let outer = @{box: @{run: print}}` then
`outer.box.run(1)`. This is a genuinely different shape from anything
v0.14.4/6 already close: those track a record literal's field being a
bare NameRef (direct alias or return-carrier); this tracks a record
literal's field being ANOTHER record literal, one level of container
nesting deeper — the "structural" axis of this feature family, not the
"call" axis v0.14.3/5/6 explore.

## Mechanism

New FIFTH stack, `Parser.nested_field_alias_scopes` — identical shape and
the same three push/pop call sites as the other four (`stmt_list` itself,
and both fn-parameter scopes: named-fn statement, anonymous `FnExpr`).
Verified parity with a grep count before touching test files: every
`field_return_alias_scopes.append/.pop()` site (5 assignment sites in
`let`-branches, 3 append, 3 pop) now has a matching
`nested_field_alias_scopes` line.

Built at the exact same `let name = @{...}` LITERAL site
`field_alias_scopes`/`field_return_alias_scopes` already populate, but
keyed only on fields whose value is ITSELF an `A.RecordLit`:

```python
self.nested_field_alias_scopes[-1][name] = {
    fname: {
        inner_fname: self._resolve_effectful_alias(inner_fexpr.name)
        for inner_fname, inner_fexpr in fexpr.pairs
        if inner_fexpr.__class__ is A.NameRef
    }
    for fname, fexpr in expr.pairs
    if fexpr.__class__ is A.RecordLit
}
```

New resolver `_resolve_effectful_field_nested(name, outer_field,
inner_field)` mirrors the other four's innermost-first, first-frame-wins
walk on `name`, then TWO chained `.get`s (each individually guarded — a
missing/`None` intermediate must not raise on the next `.get`, unlike a
single-level lookup which only ever guards once).

`_check_effect_call` gained a fifth branch, structurally distinct from
(not a generalization of) v0.14.4's own field branch:

```python
elif (callee.__class__ is A.FieldAccess and
      callee.obj.__class__ is A.FieldAccess and
      callee.obj.obj.__class__ is A.NameRef):
    tag = self._resolve_effectful_field_nested(
        callee.obj.obj.name, callee.obj.name, callee.name)
    display = "%s.%s.%s" % (callee.obj.obj.name, callee.obj.name, callee.name)
```

v0.14.4's branch guards `callee.obj.__class__ is A.NameRef` — a class
check, mutually exclusive with this new branch's guard
(`callee.obj.__class__ is A.FieldAccess`) by construction, so there is no
ordering hazard and no risk of the new branch silently shadowing the old
one (confirmed by running the full pre-existing `test_v14.py` suite
unchanged before adding a single new test — see Verification).

Every `let`/named-`fn`/parameter binding site that already wrote an
explicit `None` into the other four stacks (for shadowing correctness)
got the identical `nested_field_alias_scopes[-1][name] = None` line added
alongside it — the same 6 sites `field_return_alias_scopes` uses (5
`let`-branch sites + the named-`fn` statement's own placeholder), plus
the two param-scope push sites (`dict.fromkeys(params)`, all `None`
values).

## Verified manually before writing tests

```
let outer = @{box: @{run: print}}
fn f() effects [] { outer.box.run(1) }
```
→ raises `'outer.box.run' requires effect 'io', not permitted by the
enclosing function's 'effects [] (no effects declared)'`.

```
let outer = @{box: @{run: print}}
fn f() effects [io] { outer.box.run(1) }
```
→ parses clean.

Both probes run directly via `python3 -c "from whence.parser import
parse, ParseError; ..."` before touching the test file, matching the
"probe first, test second" discipline round 282's own knowledge file
used.

## Tests

`tests/test_v14.py`, new "v0.14.7" section, 9 new tests:
- `test_nested_field_call_via_record_literal_is_checked` / `..._granted_
  when_effect_allowed` — the core positive/negative pair.
- `test_non_effectful_nested_field_is_not_flagged` — a non-effectful
  bare-NameRef inner field resolves to `None`, mirrors v0.14.4's own
  `test_non_effectful_field_is_not_flagged`.
- `test_inner_record_of_same_name_shadows_outer_nested_field_alias` /
  `test_param_named_like_outer_nested_field_alias_shadows_it` — shadowing
  at the OUTER name, mirroring v0.14.4/6's own equivalents exactly.
- `test_nested_field_of_a_non_literal_outer_binding_is_not_tracked` —
  one-hop-on-the-outer-binding boundary (a `make_outer()` call result
  stays untracked), mirrors `test_field_of_a_non_literal_binding_is_not_
  tracked`.
- `test_nested_field_where_middle_field_is_not_itself_a_record_literal` —
  new boundary specific to this shape: `outer.box.run(1)` where `box`'s
  own value was a bare NameRef (not a nested literal) parses CLEANLY (no
  restriction applies, `box` key simply absent from the nested dict) —
  pinned via `parse()` returning without raising, deliberately not
  calling `f()` since `box`'s runtime value (`print`) has no `run` field
  to actually invoke; this test is a parse-time-only claim.
- `test_nested_field_value_that_is_itself_a_call_is_not_tracked` — the
  "bare NameRef only" rule applied at the INNER level too.
- `test_three_way_nested_field_call` — direct/fast/slow-mode pin, same
  as every prior round in the family.

## Verification

- `pytest tests/test_v14.py -q`: **67 passed** (was 58; net +9, all new,
  zero pre-existing tests touched or broken).
- `languages/whence/run_tests_fast.sh`: **897 passed, 38 deselected** (was
  888; +9 exactly matches `test_v14.py`'s own net delta; no other file's
  count moved).
- Full unfiltered `pytest tests/` (`parser.py`'s `statement()`/`stmt_list`
  sit on every block-parse path, not just effects-declared code, the same
  reason round 276/282 each ran it): **935 passed in 382.40s**, zero
  regressions.
- Guest parity: unaffected, same reasoning as v0.14.2 through v0.14.6 —
  `print` is in `harness/swe/guest.py`'s `BANNED` regex, so any fuzz
  program mentioning it anywhere short-circuits to `parse_error` before
  either interpreter runs it.
- Fuzz coverage: same honest, now-SEVENTH-time-named gap —
  `harness/swe/fuzz.py`'s `ProgramGen` never emits a record literal whose
  field value is itself another record literal at all, so this round's
  own trigger shape is exercised only by `test_v14.py`'s hand-authored
  cases. `harness/swe/alias_effects.py`'s `ExtendedEffectGen` (round
  281/287's independent oracle) also does not yet cover this shape.
  Neither fixed this round, per the same precedent v0.14.2 through
  v0.14.6 each set — named here for a future language(C)/SWE-loop(D)
  round, same size/shape as round 284's own v0.14.6 fuzz-coverage
  extension and round 287's own oracle extension.

## Files changed

- `languages/whence/whence/parser.py` — new `nested_field_alias_scopes`
  stack (init comment, 3 push sites, 3 pop sites), 1 new `let`-branch
  assignment line added to 6 shadowing sites, new
  `_resolve_effectful_field_nested` method, new `_check_effect_call`
  branch + updated docstring.
- `languages/whence/tests/test_v14.py` — 9 new tests.
- `languages/whence/SPEC.md` — new "v0.14.7 (round 288)" section.

## What's still open (unchanged in kind from round 282's own list)

1. Passing a builtin as a function ARGUMENT — still untouched, still
   correctly scoped out as multi-round work.
2. The dynamic call graph — still untouched, still multi-round scale.
3. Fuzz coverage / `ExtendedEffectGen` oracle coverage for this round's
   new nested-field-literal shape — named, not fixed, matching the
   now-established "ship the checker, name the fuzz gap, close it in a
   later dedicated round" rhythm (round 278/279 closed the v0.14.3/4/5
   gap; round 284 closed v0.14.6's).
4. This round does NOT generalize to arbitrary nesting depth — a THIRD
   level (`a.b.c.run(...)`) is not tracked at all; the new branch's guard
   requires the chain to bottom out in a bare name exactly two `.field`
   hops up. A genuinely N-deep version would need a recursive walk over
   an arbitrarily long `FieldAccess` chain rather than one more
   hand-written branch — flagged here as a natural (but not yet
   justified-by-a-concrete-need) further extension, not attempted this
   round to keep the same "one hop past the existing frontier" discipline
   every prior version in this family has used.
