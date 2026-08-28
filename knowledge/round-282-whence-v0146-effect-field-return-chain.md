# Round 282 (language C) — Whence v0.14.6: effect-system RETURN-value flow through a field call

## Pre-flight / record-gap landing

Before starting this round's own track work, `check_round_recorded.py`
flagged round 281 (SWE-loop D) as a real gap: `status=success`,
`interrupted=False` per `logs/driver.log`'s own turn summary, but
`git_committed=False` and no `research-state.md` entry. Verified the
left-behind diff was real before touching anything: `harness/swe/
alias_effects.py` gained `ExtendedEffectGen`, a second independently
written oracle covering the verdict-correctness (not just crash-safety)
of the v0.14.3/4/5 effect-alias features, plus `harness/tests/
test_swe_alias_effects.py` gained a 3000-program targeted campaign and 3
mutation-detection tests. Ran `pytest harness/tests/test_swe_
alias_effects.py -q` for real: **10 passed in 109.9s**. Landed as commit
`70a8147`, crediting round 281 as the diff's author and round 282 as the
one that verified and shipped it (same convention as rounds 175/213/264/
279's own "landed by" credits). The 4 untracked `languages/whence/` files
are the same standing Hermes-gateway batch rounds 279/276/277/280 already
identified and left alone (identical mtime, same filenames/author) — not
new, no action needed. See `state/research-state.md`'s round-281 entry
for the full verification detail.

## Task selection

With round 281's gap landed, turned to this round's own language(C) track
work. The effect system's (`effects [...]`, v0.14.x) two big remaining
gaps — passing a builtin as a function ARGUMENT, and the dynamic call
graph — are still explicitly multi-round-scale per rounds 270/272/276's
own repeated notes: neither fits the single-pass, no-interprocedural-
analysis mold the whole feature family relies on. Round 276 set the
precedent of finding a THIRD kind of narrowly-scoped gap instead of
attempting either — this round found a FOURTH.

`_check_effect_call`'s own docstring (pre-round) named the gap explicitly
but hadn't been touched: v0.14.4's "field whose value is itself a call/
alias chain is invisible." Reading `field_alias_scopes`'s construction
(`whence/parser.py`, the `RecordLit` branch of `statement()`) confirmed
the field dict is built ONLY via `_resolve_effectful_alias` on each bare-
NameRef field value — never via `_resolve_effectful_return`. So `let box
= @{run: get_printer}` (where `get_printer` is a v0.14.3 return-carrier,
not itself a direct alias) leaves `box`'s `run` field completely
untracked, and `box.run()(1)` — TWO applications, the first invoking
whatever `get_printer` was tracked to return — was entirely unchecked:
`_check_effect_call`'s branch dispatch has no case for a `Call` whose own
`.fn` is a `FieldAccess` (`postfix()`'s `A.Call(FieldAccess(box, run),
[])` shape), so it fell straight to the `else: return` no-op.

This is exactly the missing fourth combination of two independent axes
the family already tracks: {direct value, return-of-call} x {bare name,
record field}. v0.14.2 = direct+name, v0.14.3 = return+name, v0.14.4 =
direct+field, this round = return+field. No new interprocedural
machinery needed — same "one more mirrored stack, same push/pop
discipline" pattern v0.14.3/v0.14.4 each already used.

## Mechanism

New FOURTH stack, `Parser.field_return_alias_scopes` — identical shape
and the same three push/pop call sites as the other three
(`alias_scopes`/`return_alias_scopes`/`field_alias_scopes`): `stmt_list`
itself, and both fn-parameter scopes (named-fn statement, anonymous
`FnExpr`). Verified in lockstep with a quick regex count
(`field_alias_scopes.append`/`.pop()`: 3/3; `field_return_alias_scopes.
append`/`.pop()`: 3/3) before running anything.

Built at the exact same `let name = @{...}` LITERAL site
`field_alias_scopes` already populates, from the SAME bare-NameRef field
values, just resolved through `_resolve_effectful_return` instead of
`_resolve_effectful_alias`:

```python
self.field_alias_scopes[-1][name] = {
    fname: self._resolve_effectful_alias(fexpr.name)
    for fname, fexpr in expr.pairs
    if fexpr.__class__ is A.NameRef
}
self.field_return_alias_scopes[-1][name] = {
    fname: self._resolve_effectful_return(fexpr.name)
    for fname, fexpr in expr.pairs
    if fexpr.__class__ is A.NameRef
}
```

New resolver `_resolve_effectful_field_return(name, field)` mirrors the
other three exactly (innermost-first, first-frame-wins walk on `name`,
then `.get(field)` within the winning frame). `_check_effect_call` gained
a fourth branch:

```python
elif (callee.__class__ is A.Call and
      callee.fn.__class__ is A.FieldAccess and
      callee.fn.obj.__class__ is A.NameRef):
    tag = self._resolve_effectful_field_return(callee.fn.obj.name, callee.fn.name)
    display = "%s.%s()" % (callee.fn.obj.name, callee.fn.name)
```

The FIRST application (`box.run()` on its own) is still independently
checked by the pre-existing v0.14.4 direct-field branch — `box.run`
itself is not retroactively marked effectful by this change, only
CALLING its result is, exactly mirroring how v0.14.3's chained-call
branch left the underlying bare-name direct-alias branch untouched.

Every `let`/named-`fn`/parameter binding site that already wrote an
explicit `None` into the other three stacks (for shadowing correctness)
got the identical `field_return_alias_scopes[-1][name] = None` line
added alongside it — five sites total (NameRef-rename, Call-return,
FnExpr, the `else` catch-all, and the named-`fn` statement's own
placeholder), so shadowing is never accidentally asymmetric across the
four stacks.

## Verified manually before writing tests

Four quick `parse()` probes confirmed the mechanism end-to-end before
committing to the test suite:
1. `box.run()(1)` inside `effects []`, `run: get_printer` → raises,
   `'box.run()' requires effect 'io'`.
2. Same shape, `effects [io]` → parses clean.
3. `run: helper` where `helper` tail-returns `5` (not a return-carrier)
   → parses clean (correctly untracked).
4. Pre-existing v0.14.4 single-hop `box.run(1)` (`run: print` directly)
   still raises, unaffected.
Also checked shadowing (inner block's own `box` with a non-effectful
`run` correctly shadows the outer effectful one) and the "one hop,
literal-binding-only" boundary (a `box` built by `make_box()` — a
function call, not a literal — stays untracked) — both matched the
documented discipline exactly.

## Tests

`tests/test_v14.py`, new "v0.14.6" section, 7 new tests:
- `test_field_return_chain_is_checked` / `..._granted_when_effect_
  allowed` — the core positive/negative pair.
- `test_field_return_chain_and_field_direct_alias_are_independent` — a
  single record literal with BOTH a direct-alias field and a
  return-carrier field, proving the two new/old dicts don't interfere.
- `test_field_return_chain_field_value_that_is_not_a_return_carrier` —
  ordinary (untracked) fn field value stays `None`.
- `test_field_return_chain_of_a_non_literal_binding_is_not_tracked` —
  one-hop boundary, mirrors `test_field_of_a_non_literal_binding_is_not_
  tracked`.
- `test_inner_record_of_same_name_shadows_outer_field_return_alias` —
  shadowing, mirrors the v0.14.4 field-alias equivalent.
- `test_three_way_field_return_chain` — direct/fast/slow-mode pin
  (parse-time-only feature, can't meaningfully diverge, but every prior
  round in the family pins one anyway).

## Verification

- `pytest tests/test_v14.py -q`: **58 passed** (was 51; net +7, all new).
- `languages/whence/run_tests_fast.sh`: confirmed the TRUE baseline via
  `git stash` (not assumed from a prior round's own claimed number) —
  stashed this round's diff, re-ran: **881 passed, 38 deselected**;
  popped the stash back, re-ran: **888 passed, 38 deselected**. +7 exactly
  matches `test_v14.py`'s own net delta; no other file's count moved.
- Full unfiltered `pytest tests/` (parser.py's `statement()`/`stmt_list`
  sit on every block-parse path, not just effects-declared code) launched
  in the background this round, alongside `harness/tests/` fuzz/oracle/
  guest campaigns — both were still running when this file was drafted;
  see this round's own `research-state.md` entry for the completed
  result (recorded once the background runs finished, same discipline
  round 276 used for its own background full-suite run).
- Guest parity: unaffected, same reasoning as v0.14.2/3/4/5 — `print` is
  in `harness/swe/guest.py`'s `BANNED` regex, so any fuzz program
  mentioning it anywhere short-circuits to `parse_error` before either
  interpreter runs it.
- Fuzz coverage: same honest, now-fifth-time-named gap —
  `harness/swe/fuzz.py`'s `ProgramGen` never emits a record literal whose
  field value is a bare-NameRef return-carrier, so this round's own
  trigger shape is exercised only by `test_v14.py`'s hand-authored cases.
  Named here, not fixed, per the same precedent v0.14.2/3/4/5 each set.

## Files changed

- `languages/whence/whence/parser.py` — new `field_return_alias_scopes`
  stack (init comment, 3 push sites, 3 pop sites), 2 new `let`-branch
  assignment lines added to 5 shadowing sites, new
  `_resolve_effectful_field_return` method, new `_check_effect_call`
  branch + updated docstring.
- `languages/whence/tests/test_v14.py` — module docstring note (v0.14.6),
  7 new tests.
- `languages/whence/SPEC.md` — new "v0.14.6 (round 282)" section.

## What's still open (unchanged from round 276's own list)

1. Passing a builtin as a function ARGUMENT — still untouched, still
   correctly scoped out as multi-round work (per-call-site specialization
   or an unsound over-approximation).
2. The dynamic call graph — still untouched, still multi-round scale.
3. Fuzz coverage for all FIVE shipped alias/return/field/if-tail/
   field-return trigger shapes (v0.14.2/3/4/5/6) — round 278/279 closed
   the first three (return-value alias, container-field alias, if/else-
   tail); this round's own new field-return-chain shape is now a SIXTH
   named, un-acted-on fuzz gap (v0.14.5's if-tail fuzz coverage was
   already closed by round 278; the NEW gap this round leaves is
   v0.14.6's own field-return-chain shape, not yet touched by any fuzz
   generator work).
4. A "field value is itself a call" case (e.g. `@{run: get_printer()}`)
   is STILL not tracked as a direct alias OR return-carrier for the
   field — deliberately, the same one-hop, no-recursion-into-a-call
   discipline v0.14.3/v0.14.4 already established; not a new gap, just
   re-confirmed unaffected by this round's change.
