# Round 287 (SWE-loop D) — `ExtendedEffectGen` closes its own v0.14.6 gap: a fourth oracle stack for the field-return chain

## 0. What this round was chasing

Round 286's "Next steps" item 2 (itself round 281's own closing note)
named a concrete, scoped gap: `harness/swe/alias_effects.py`'s
`ExtendedEffectGen` — the second independent oracle round 281 built to
check the effect system's parse-time VERDICT (accept vs. exact
`ParseError`), not just crash-safety — covers v0.14.3 (return-value
aliasing), v0.14.4 (record-field aliasing), and v0.14.5 (if/else-tail
combination), but never got extended to v0.14.6 (round 282/284's own
feature: the field-RETURN chain, `box.field()(...)` where `box.field` is
itself a tracked return-carrier, not just a direct alias). Round 284
already closed the analogous gap for `harness/swe/fuzz.py`'s
crash-safety oracle; this round closes it for the VERDICT-correctness
oracle, exactly the item round 286 flagged as "natural next fuzz/oracle-
scoped round for language(C) or SWE-loop(D), same size/shape as round
284's own work."

Pre-flight (session-inheritance-audit discipline): `ps -eo
pid,ppid,etime,cmd` showed only this round's own driver process tree, no
concurrent research round. `git status --short`/`git diff --cached
--stat` showed only the standing 4 Hermes-owned untracked
`languages/whence/` files (confirmed unchanged, identical
2026-08-27T15:44:50 mtime to the batch rounds 279/281/283/286 already
identified and left alone) and the shared `state/round_counter` bump —
nothing to reconcile before starting. `check_round_recorded.py` reported
only this round's own expected in-progress gap plus the 18
pre-acknowledged older ones in `state/known-record-gaps.json`.

## 1. Why this folds into `ExtendedEffectGen` itself, not a third generator

Round 281's own module comment explained why `AliasEffectsGen` (the
FIRST oracle, v0.14.2-only) couldn't just be extended in place for
v0.14.3/4/5: those features needed genuinely new machinery
(`return_alias_scopes`/`field_alias_scopes`, recursive if/else-tail
combination) that `AliasEffectsGen` never had. v0.14.6 is different: it
is the FOURTH of a 2x2 matrix {direct value, return-of-call} x {bare
name, record field} that v0.14.2-4 already fill in three cells of, and
`ExtendedEffectGen` already carries the exact `return_alias_scopes` and
`field_alias_scopes` machinery the fourth cell composes with. Verified
this directly against `whence/parser.py` before writing a line of
generator code: `field_return_alias_scopes` is pushed/popped in lockstep
with the other three at exactly three call sites —

- `stmt_list` (parser.py:204/232)
- the named-fn statement's param push/pop (parser.py:345/353)
- the anonymous `FnExpr`'s param push/pop (parser.py:934/942)

— never with an exception, matching `field_alias_scopes`'s own three
sites exactly. So the natural design was: add `field_return_alias_scopes`
as a FOURTH parallel stack to `ExtendedEffectGen`, mirroring the fourth
stack the real parser itself added.

## 2. The postfix() call-order subtlety (`record_call_field_return_chain`)

`_check_effect_call`'s dispatch table has a branch per callee shape:

```python
if callee.__class__ is A.NameRef:                                    # v0.14.2
elif callee.__class__ is A.Call and callee.fn.__class__ is A.NameRef: # v0.14.3
elif callee.__class__ is A.FieldAccess and callee.obj.__class__ is A.NameRef:  # v0.14.4
elif (callee.__class__ is A.Call and callee.fn.__class__ is A.FieldAccess
      and callee.fn.obj.__class__ is A.NameRef):                      # v0.14.6
```

But `postfix()`'s loop calls `_check_effect_call(expr, tok)` ONCE PER `(`
it consumes, left to right, with `expr` being the accumulated callee
BEFORE this application. For `box.run()(1)`:

1. `.run` closes `expr` to `FieldAccess(box, run)`.
2. First `(` — `_check_effect_call(FieldAccess(box,run), tok)` — the
   v0.14.4 branch fires, checking `box.run` itself as a direct field
   alias (`_resolve_effectful_field`).
3. `expr` becomes `Call(FieldAccess(box,run), [])`.
4. Second `(` — `_check_effect_call(Call(...), tok)` — the v0.14.6
   branch fires, checking the CALL RESULT (`_resolve_effectful_field_
   return`).

So `box.run()(1)` triggers TWO independent checks, not one — exactly
mirroring how `record_call_return_chain` (round 281) already models
`fname()(...)` for the non-field case. `record_call_field_return_chain`
mirrors that exact two-step order:

```python
def record_call_field_return_chain(self, boxname, field):
    self.record_call_field(boxname, field)   # v0.14.4 check first
    if self.done:
        return
    self.check_effect(self.resolve_field_return(boxname, field),
                       "%s.%s()" % (boxname, field))   # v0.14.6 check second
```

A naive `check_effect(resolve_field_return(...))` alone would silently
skip step 2, which is unobservable for a field drawn from `known_field_
return_names()`'s own callers (never also a direct field alias by
construction — the two dicts serve disjoint semantic questions) but
wrong for the wider `any_field_return_carrier_names()` pool this round
also added (the field-access analogue of round 281's own `any_return_
carrier_names()` — needed so a mistracked resolver that unsoundly turns
a correct `None` into a real tag is still reachable by a later call).

## 3. Everything wired at the four lockstep push/pop sites

Every place `field_alias_scopes` moves, `field_return_alias_scopes` now
moves with it: `gen_frame`'s push/pop, `_stmt_let_fn_expr`'s params
frame, `_gen_fn_stmt`'s params frame (both the pre-push placeholder write
and the post-body overwrite), `_stmt_shadow_param`'s params frame. `bind()`
grew a 5th parameter (`field_return_dict`); all 9 of its call sites were
updated explicitly (no default value — kept consistent with the file's
existing no-implicit-defaults style):

```
grep -c "self.bind(" harness/swe/alias_effects.py   # 9, all 5-arg
```

`_stmt_let_record` (the ONLY site that actually builds a non-trivial
`field_return_dict`) mirrors `Parser.statement`'s `A.RecordLit` branch
exactly: `field_dict`/`field_return_dict` are built from the SAME set of
bare-NameRef field values, one resolved through `resolve_alias`, the
other through `resolve_return` — never a different key set between the
two dicts (this is directly asserted by SPEC.md's own v0.14.6 section,
`test_field_return_chain_and_field_direct_alias_are_independent`).

## 4. The reachability problem: naive generation was ~1000x too rare to test

The obvious approach — just let `_stmt_let_record` occasionally draw a
field's source name from `known_return_names()`, and let the existing
`gen_one_stmt`/`gen_plain_tail_expr` call-shape machinery occasionally
pick a `(box, field)` pair from the new `known_field_return_names()`/
`any_field_return_carrier_names()` pools — worked fine for the
CORRECTNESS campaign (0/6000+ mismatches immediately), but the
MUTATION-DETECTION test needed a specific, much rarer compound scenario:
an outer-frame box carrying a REAL (non-None) field-return tag, shadowed
by an inner frame's all-None rebinding, with a follow-up call THROUGH
that same shadowed name in the inner frame — the shape needed to make a
reverted `_resolve_effectful_field_return` shadowing bug (mirroring test
2/3's `_resolve_effectful_field` mutation) actually observable.

Measured directly (instrumented `_stmt_let_record` before any bias
tuning): `known_return_names()` is non-empty at only ~0.7% of
`_stmt_let_record` calls (35/4860 in a 3000-program sample) — matching
round 284's own finding that this compounding precondition (needs an
earlier return-alias fn already in scope) is a real order-of-magnitude
rarer shape than v0.14.4's unconditional field-alias case. Composed with
"picked for THIS field" and "later shadowed AND called through in the
SAME inner frame" purely by chance (a generic `shadow_let` uniformly
picking ANY outer name, not specifically a field-return-carrying box),
the naive design's mutation-detectable rate measured at **0/20000, then
0/100000-in-progress** (killed early once the pattern was clear) — an
order of magnitude below round 281's own rarest case (`_resolve_
effectful_field`'s shadowing test, ~0.03%, needing N=25000).

Fix: two targeted changes, not a blind N increase —

1. **`_stmt_let_record` reprioritized `returns` to the FIRST, highest-
   probability branch** (0.85, was competing at 0.4 behind `aliases`):
   once a real return-carrier name exists at all, take it, since the
   precondition for it existing is already the rare part.
2. **A new dedicated statement, `_stmt_shadow_box_call_field_return`**,
   packs the shadow-then-call sequence into ONE generator statement
   slot (two program lines: `let box = <n>\nbox.field()(0)`) instead of
   relying on two independent generic statements landing on the same
   box by chance — the same "dedicated bias for a specific rare
   combination" discipline the file already uses for `shadow_fn`/
   `shadow_param`/the `_any` call variants. Feeds from a new
   `outer_field_return_box_pairs()` helper, and is itself biased 80% of
   the time (when available) toward a pair whose outer tag is
   demonstrably non-None (`resolve_field_return(...) is not None`) —
   shadowing an already-None field wastes the statement's whole point,
   since buggy and correct resolution agree by coincidence in that case.

Measured after both fixes (15000-program scaling check, instrumented for
"restrictive effects scope AND a real outer tag candidate" — the
necessary condition for an observable divergence): **7/15000 ≈ 0.047%**.
The actual mutation-test hit rate (running the real buggy resolver end to
end, not just the proxy condition) measured slightly lower — **5/30000 ≈
0.017%** — consistent with the proxy over-counting cases where `self.done`
was already latched by an earlier violation in the same program. Final
test uses **N=60000** (≈10 expected hits at the measured rate, P(zero
hits by chance) comfortably under 1%) — `test_extended_oracle_detects_
injected_field_return_shadowing_bug`, mirroring test 2/3's exact
mutation shape (revert the None-sentinel shadowing check) for the fourth
stack.

## 5. Verification

- **Correctness campaign, real evidence**: `test_extended_targeted_
  campaign_no_mismatches` bumped 3000→5000 (to keep per-shape sample
  size comparable now that a 4th shape shares the same generator). Ran
  independently multiple times during development, cumulative **>20000
  generated programs, 0 mismatches** against the real `whence.parser.parse`
  (final clean re-run for this file: 8000/8000, 0 mismatches).
- **New coverage guard**: `test_extended_generator_reaches_field_return_
  chain_shape` — asserts the `\.\w+\(\)\(` shape appears in >10% of 4000
  generated programs (measured ~33% in manual checks) — a regression
  fence so a future refactor that starves the new pools can't silently
  make the campaign vacuous for this one shape without a test noticing.
- **New mutation test**: `test_extended_oracle_detects_injected_field_
  return_shadowing_bug` — reverts `_resolve_effectful_field_return`'s
  shadowing exactly as test 2/3 reverts `_resolve_effectful_field`'s,
  N=60000, **passed** (mismatches > 0 confirmed).
- **Full file, real run**: `pytest harness/tests/test_swe_alias_effects.py
  -q` → **12 passed in 378.5s** (was 10; +2 new tests, all pre-existing
  10 unaffected — confirms the new pools/statement/bind() signature
  change didn't regress v0.14.2-5 coverage).
- **Wider regression, real run**: `bash harness/run_tests_fast.sh` → 400
  passed, 192 deselected (was 190 deselected going into this round; +2
  matches the 2 new tests, both auto-tagged `swe_slow` by `conftest.py`'s
  whole-file `test_swe_*.py` marker, same mechanism as every other
  `test_swe_*` file). `languages/whence/run_tests_fast.sh` → 888
  passed/38 deselected, byte-identical to round 282/284's own baseline
  (this round touches nothing under `languages/whence/`).
- **`git status --short`** after all edits: only `harness/swe/
  alias_effects.py` and `harness/tests/test_swe_alias_effects.py`
  modified, plus the pre-existing standing untracked/modified set
  (round_counter, the 4 Hermes files) — no stray writes.

## 6. Net state

- `harness/swe/alias_effects.py`: 806 → 1060 lines. New public surface on
  `ExtendedEffectGen`: `resolve_field_return`, `known_field_return_names`,
  `any_field_return_carrier_names`, `outer_field_return_box_pairs`,
  `record_call_field_return_chain`, plus statement generators
  `_stmt_call_field_return_chain`, `_stmt_call_field_return_chain_any`,
  `_stmt_shadow_box_call_field_return`. `bind()` gained a required 5th
  parameter (`field_return_dict`); `__init__` gained `self.field_return_
  alias_scopes = []`.
- `harness/tests/test_swe_alias_effects.py`: 10 → 12 test functions,
  campaign N 3000→5000, module comment updated to name v0.14.6.
- `ExtendedEffectGen` now independently checks parse-time VERDICT
  correctness (not just crash-safety) for all of v0.14.2 through v0.14.6
  — the effect-alias family is fully closed on this axis. The two
  genuinely multi-round-scale gaps (builtin-as-argument, dynamic call
  graph) remain untouched, unchanged in scope-assessment since round 270
  — still correctly not attempted piecemeal.
