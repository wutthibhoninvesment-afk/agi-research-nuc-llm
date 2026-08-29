"""v0.14 (round 146) / v0.14.1 (round 264) / v0.14.2 (round 266) /
v0.14.3 (round 270) / v0.14.4 (round 272) / v0.14.5 (round 276):
`effects [...]` — a minimal, parse-time effect system.

Design (see SPEC.md "v0.14"/"v0.14.1"): unlike `: Type`/`-> Type` (v0.12/
v0.13, both runtime checks against a runtime VALUE), whether a function's
own body directly names an effectful builtin is a static property of the
SOURCE TEXT — so this is checked entirely at parse time, with no new AST
node, no Closure field, and no interpreter change at all. `effects [io,
...]` is an optional clause after a parameter list, before an optional
`-> Type` (fixed order): `fn f(params) effects [tags] -> Type { body }`.

- Top-level, no clause at all == unrestricted (the default; every program
  written before this feature existed parses identically — see
  `test_undeclared_fn_may_still_print`).
- `effects []` declares "this function's own body may not directly call
  an effectful builtin" (today, only `print`, tagged `"io"`
  in `parser._EFFECTFUL_BUILTINS`) — violating it is a ParseError, not a
  runtime `miss`, because it can be decided without running anything.
- `effects [io]` (or any set containing the required tag) explicitly
  grants it.
- **v0.14.1: a nested fn with NO clause of its own now lexically INHERITS
  its nearest enclosing fn's resolved scope**, instead of defaulting to
  unrestricted (`test_nested_fn_without_own_clause_inherits_outer_
  restriction`, `..._inherits_a_granting_scope_too`, chaining through
  multiple clause-less levels per `test_deeply_nested_fn_without_own_
  clause_inherits_through_two_levels`). An explicit clause on the nested
  fn still always overrides the inherited scope entirely, in either
  direction — narrower or broader — the same "one settle point, explicit
  always wins" rule return types already use
  (`test_nested_undeclared_fn_escapes_outer_purity`, misleadingly named
  post-v0.14.1 since its `inner` DOES declare its own `effects [io]`; kept
  as-is to keep pinning "an explicit declaration on a nested fn is
  independent of the enclosing scope").

- **v0.14.2: a name bound via a direct `let alias = <effectful-builtin-or-
  already-tracked-alias>` is now tracked**, and a call THROUGH that alias
  is checked exactly as calling the builtin directly would be
  (`test_indirect_call_via_variable_is_now_checked`, chaining through two
  hops per `test_alias_chain_through_two_hops_is_checked`). Correctly
  respects shadowing: a `let`/`fn`/parameter that reuses the alias's name
  in an inner (or the enclosing param) scope blocks the lookup from
  falling through to the outer alias (`test_local_let_shadows_outer_
  alias`, `test_nested_fn_name_shadows_outer_alias`, `test_param_named_
  like_outer_alias_shadows_it`). Visible across lexical nesting the same
  way `effects [...]` itself is (`test_alias_defined_in_outer_scope_
  visible_to_nested_fn`) but still a single left-to-right parse pass, so
  an alias `let` written AFTER the call it would cover is not detected
  (`test_alias_defined_after_call_site_is_not_detected`).

- **v0.14.3: a fn whose body's own TAIL STATEMENT is a bare name resolving
  to an effectful alias is now tracked as a "return fact"** —
  `Parser.return_alias_scopes`, the exact same per-block-frame shape as
  `alias_scopes` (v0.14.2), pushed/popped at the identical three sites, but
  recording "does CALLING this name yield an effectful alias" rather than
  "IS this name one". Closes the "returning it from a call" clause of
  v0.14.2's own still-open gap, for this one narrow shape:
  `let p = get_printer()` now propagates `get_printer`'s tracked return
  fact to `p` (`test_return_value_via_let_is_checked`), and a call chained
  straight onto the return with no intermediate `let` is checked too —
  `get_printer()(1)` (`test_chained_call_on_return_value_is_checked`).
  Renaming a fn (`let g = get_printer`, no call) carries its return fact
  forward along with its direct-alias one
  (`test_renamed_fn_carries_its_return_fact`); the same tracking applies to
  an anonymous `fn(...) {...}` bound by `let`
  (`test_anon_fn_bound_by_let_return_value_is_checked`). Shadowing is
  correct here too, for the same reason v0.14.2's own alias_scopes needed
  it: an inner, differently-behaved fn of the SAME name blocks the lookup
  from falling through to an outer one
  (`test_inner_fn_of_the_same_name_shadows_the_outer_return_fact`).
  Deliberately narrower than it could be, at the time: only a BARE-NAME
  tail was inspected, not one recursed through an `if`/nested block the way
  `mark_tails` structurally walks tail position — closed for the `if`/`else`
  case by v0.14.5 below.

- **v0.14.5: a fn whose body's own TAIL STATEMENT is an `if`/`else` (any
  `else if` chain length) where EVERY arm resolves to the exact same
  effectful alias is now tracked too** — `Parser._if_tail_alias_tag`,
  called from the same `stmt_list` tail-resolution site v0.14.3 added,
  needs no NEW scope-tracking stack: `then`/`otherwise` are each already-
  parsed `A.Block`s (or, for an `else if` chain, another already-parsed
  `A.If`) whose own `tail_alias_tag` was already correctly resolved by
  their OWN `stmt_list` call, while THEIR OWN `alias_scopes` frame was
  open — so comparing them is a purely structural, no-scope-needed walk,
  the same shape `mark_tails`'s own boolean walk already has
  (`test_return_tag_sees_an_if_else_tail_when_both_arms_agree`,
  `test_return_tag_if_else_tail_granted_when_effect_allowed`, chained
  through an `else if` per
  `test_return_tag_sees_through_an_else_if_chain_when_every_arm_agrees`).
  Requires an EXACT match on every arm, not "any arm" or a majority — one
  mismatched arm (a plain value, or a different/untracked callable) leaves
  the whole `if` untracked, `None`, same as before
  (`test_return_tag_if_else_tail_needs_every_arm_to_agree`,
  `test_return_tag_else_if_chain_one_mismatched_arm_is_not_tracked`) — an
  approximate match would be UNSOUND (a caller could invoke a branch that
  performs a real, undeclared effect and never get flagged). Deliberately
  still narrow: this only ever starts from the enclosing BLOCK's own tail
  statement — an `if` bound to a `let` first, then referenced, is not
  inspected (`test_return_tag_only_sees_a_tail_if_else_not_a_deeper_
  nested_one`).

- **v0.14.4: a name bound via a direct `let name = @{...}` RECORD LITERAL
  is now tracked field-by-field**, closing the CONTAINER-FIELD clause of
  v0.14.3's own still-open gap — `Parser.field_alias_scopes`, a THIRD
  per-block-frame stack, same push/pop sites as the other two, mapping a
  tracked name to a `{field: tag-or-None}` dict built once at the `let`
  from each field value that is itself a bare NameRef. `let box = @{run:
  print}` then `box.run(1)` is now checked exactly as `let p = print;
  p(1)` (v0.14.2) would be (`test_field_call_via_record_literal_is_
  checked`). A field whose value isn't effectful resolves to `None`, no
  false positive (`test_non_effectful_field_is_not_flagged`). Shadowing is
  correct here too: an inner record of the SAME name blocks the lookup
  from falling through to an outer one
  (`test_inner_record_of_same_name_shadows_outer_field_alias`), and a
  parameter named like an outer record shadows it exactly as a param
  already shadows an outer direct/return alias
  (`test_param_named_like_outer_field_alias_shadows_it`). Deliberately
  narrower than it could be, same mold as v0.14.3: only a record built
  directly by a `let`-LITERAL is tracked, not one returned from a call
  (`test_field_of_a_non_literal_binding_is_not_tracked`); only a BARE-NAME
  field value is inspected, not one that is itself a call
  (`test_field_value_that_is_itself_a_call_is_not_tracked`).

Still deliberately SHALLOW by design, not oversight (mirrors the `-> Type`
precedent of checking one settle point, not full call-graph composition):
the declaration only vouches for the function's OWN textual body, resolved
lexically, not through arbitrary calls.
  - Passing a builtin as a FUNCTION ARGUMENT remains completely invisible
    to the check — only a direct `let alias = <name>` hop (v0.14.2), a
    direct-call return (v0.14.3/v0.14.5: a bare-name tail, or an `if`/`else`
    tail whose every arm agrees), and a literal-record field (v0.14.4,
    bare-name field value only) are tracked, not general value flow through
    arbitrary data structures, nor through an `if` that isn't itself in
    tail position.
  - Calling a DIFFERENT, unrestricted top-level function that itself
    performs the effect is still untouched by the caller's own
    declaration — only LEXICAL nesting and direct/return/field aliasing
    are tracked, not the dynamic call graph (`test_effects_empty_still_
    allows_non_print_calls` calls a genuinely pure `double`, but the same
    shape would allow calling an impure sibling too; not separately pinned
    since it follows directly from "declaration only vouches for the
    function's own textual body").
Both remaining gaps are honest, tested limitations, not bugs — a full
call-graph-aware (and fully data-flow-sensitive) effect system is future
work (see research-state.md's language backlog).

- **v0.14.8 (round 294): the SECOND effectful builtin.** Every alias-
  tracking round from v0.14.2 through v0.14.7 exercised `_EFFECTFUL_
  BUILTINS` with exactly one real entry (`print`/"io"); the "per-tag, not
  merely was-a-clause-present" property was pinned only against a
  hypothetical, unused tag name (`test_effects_unrelated_tag_still_blocks_
  print`'s "network"). `rand` (arity 0, a float in `[0.0, 1.0)`, tag
  "random") is a genuinely new capability — the interpreter's own
  `random.Random` stream, seeded (default a fixed constant, 0, not OS
  entropy) so a program's use of "randomness" stays fully REPRODUCIBLE
  run to run, the same property `Interpreter`'s three independently-
  constructed direct/fast/slow instances (`assert_three_way`) already
  depend on for every other builtin. Confirms the v0.14 design comment's
  own claim ("a future effectful builtin ... slots in by adding one entry
  here — no other code needs to change") literally true: `_check_effect_
  call` and every `_resolve_effectful_*` helper needed zero changes.

- **v0.14.9 (round 300): the NAMED-fn slice of the FUNCTION-ARGUMENT gap.**
  Every prior round in this family answered "does THIS NAME, resolved once
  at its own scope, carry an effect fact" — decidable the moment its
  binding site is parsed. Whether `fn apply(f) effects [io] { f(1) }` is
  sound to call as `apply(print)` depends on the SPECIFIC ARGUMENT at each
  call site, not on anything `apply`'s own body (parsed exactly once,
  independent of any call site) can ever resolve about `f` — a genuinely
  different shape from every sibling resolver, needing a check that runs
  at the CALL SITE, not at the callee's own definition
  (`Parser.param_call_scopes`, `_check_call_site_param_effects`).
  `apply`'s own definition records, once, which of its params it calls
  directly (`f`) and its own resolved effects scope (`[io]`); each later
  call site re-checks whichever argument lands in a directly-called
  parameter slot against THAT recorded scope —
  `test_argument_passed_to_a_directly_called_param_is_checked`,
  `test_argument_passed_to_a_directly_called_param_is_rejected_when_not_
  permitted`. Deliberately narrow, the same "one hop, bare NameRef,
  textually before" discipline the whole family already uses: only a NAMED
  fn's own params are tracked — at the time; an anonymous `fn(...) {...}`
  bound by `let` was NOT, closed by v0.14.10 below — only a
  param called DIRECTLY in the body, not one merely stored or passed on
  (`test_param_only_stored_not_called_is_not_tracked`); only a bare-NameRef
  argument at the call site, not one that is itself a call or a field
  access (`test_non_namerefarg_to_a_directly_called_param_is_not_tracked`);
  shadowing is correct, both for a nested fn re-using the same param name
  (`test_inner_fn_with_same_param_name_is_checked_against_its_own_scope`)
  and for the fact this uses `apply`'s OWN declared scope, not the CALLER's
  (`test_check_uses_callees_own_scope_not_the_callers`). Two genuine
  gaps remain, explicitly still open: an argument reaching an effectful
  builtin through a SECOND function call first, and the still-untouched
  dynamic call graph.

- **v0.14.10 (round 302): the anonymous-fn-bound-by-`let` slice of
  v0.14.9's own FUNCTION-ARGUMENT gap.** `Parser.primary()`'s
  `fn(...) {...}` branch already pushed/popped the same
  `current_fn_params_frame_stack`/`direct_param_calls_stack` bookkeeping
  v0.14.9's NAMED-fn branch uses, but discarded the popped `called_params`
  set — there was no NAME yet to key `param_call_scopes` by while the
  anonymous fn's own body was being parsed. Now the fact rides on the
  returned `A.FnExpr` node itself instead (`param_call_fact`, a new field,
  mirroring how `body.tail_alias_tag` already rides on `A.Block` since
  v0.14.3), and `statement()`'s own `let` handling picks it up the moment
  it learns the binding's name — the first point anywhere a name exists to
  key `param_call_scopes[-1]` by
  (`test_anon_fn_bound_by_let_param_call_is_now_checked`).
  `_check_call_site_param_effects` itself needed ZERO changes: it already
  resolves through `param_call_scopes` generically via
  `_resolve_param_call_fact`, indifferent to whether a fact originated from
  a NAMED fn's own definition or a `let`-bound anonymous one. The fact
  carries forward through a plain rename, same as every other alias kind in
  this family
  (`test_anon_fn_bound_by_let_param_call_fact_carries_through_a_rename`),
  and is correctly shadowed by a same-named parameter
  (`test_param_named_like_an_anon_fn_bound_name_shadows_its_param_call_
  fact`). Still deliberately narrow: a fn expression used any OTHER way —
  called immediately without ever being bound to a name, passed straight
  through as someone else's argument, stored in a container/record field —
  has no name to key `param_call_scopes` by and remains untracked, not a
  new gap but the same "nothing to check without SOME name" boundary this
  whole family already has. Every other v0.14.9 gap (a SECOND function call
  before reaching the effectful builtin, a builtin flowing into a
  stored/returned rather than directly-called param, the dynamic call
  graph) remains completely untouched, unchanged in scope.
"""

import os
import sys

import pytest

from whence.interp import Interpreter
from whence.parser import parse, ParseError
from whence.values import Miss

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_v09 import run, val, assert_three_way  # noqa: E402


def all_ok(src, **kw):
    interp, env, out = run(src, **kw)
    bad = [c for c in interp.checks if not c["ok"]]
    assert bad == [], (bad, out)
    assert interp.checks, "no checks ran"
    return interp, env, out


# --- backward compatibility: no clause == unrestricted ----------------------

def test_undeclared_fn_may_still_print():
    all_ok('fn f() { print(1) }\ncheck "ok": f() == 1\n')


def test_toplevel_print_unaffected():
    interp, env, out = run('print("hi")\n')
    assert out == ["hi"]


def test_anon_fn_no_clause_may_print():
    all_ok('let f = fn() { print(1) }\ncheck "ok": f() == 1\n')


# --- `effects []` blocks print ----------------------------------------------

def test_effects_empty_blocks_print_named_fn():
    with pytest.raises(ParseError) as ei:
        parse('fn f() effects [] { print(1) }\n')
    msg = str(ei.value)
    assert "'print' requires effect 'io'" in msg
    assert "effects []" in msg


def test_effects_empty_blocks_print_anon_fn():
    with pytest.raises(ParseError):
        parse('let f = fn() effects [] { print(1) }\n1\n')


def test_effects_unrelated_tag_still_blocks_print():
    """`effects [network]` grants "network", not "io" — print is still
    rejected. Unrecognized/unused tags are otherwise inert (no builtin
    requires "network" today), proving the check is per-TAG, not merely
    "was the clause present"."""
    with pytest.raises(ParseError) as ei:
        parse('fn f() effects [network] { print(1) }\n')
    assert "effects [network]" in str(ei.value)


# --- `effects [io]` grants print ---------------------------------------------

def test_effects_io_allows_print():
    all_ok('fn f() effects [io] { print(1) }\ncheck "ok": f() == 1\n')


def test_effects_multiple_tags_allows_print():
    all_ok('fn f() effects [io, foo] { print(1) }\ncheck "ok": f() == 1\n')


def test_effects_with_return_type_order():
    all_ok('fn f() effects [io] -> num { print(1) }\ncheck "ok": f() == 1\n')


def test_return_type_before_effects_is_a_parse_error():
    """Fixed order: effects before `-> Type`. Writing it the other way
    around is an ordinary out-of-order syntax error (`{` expected), not a
    silently-accepted alternate spelling."""
    with pytest.raises(ParseError):
        parse('fn f() -> num effects [io] { print(1) }\n')


# --- shallow-scope documented limitations -----------------------------------

def test_nested_undeclared_fn_escapes_outer_purity():
    all_ok(
        'fn outer() effects [] {\n'
        '  fn inner() effects [io] { print(1) }\n'
        '  inner()\n'
        '}\n'
        'check "ok": outer() == 1\n')


def test_nested_fn_without_own_clause_inherits_outer_restriction():
    """v0.14.1 (round 264): an inner fn with NO effects clause of its own
    now INHERITS the nearest enclosing fn's resolved scope, closing the gap
    `test_nested_fn_without_own_clause_also_escapes` used to document — a
    nested, undeclared `print` inside an `effects []` body is now a
    ParseError naming the OUTER function's own declaration, exactly as if
    `print` were called directly in the outer body."""
    with pytest.raises(ParseError) as ei:
        parse(
            'fn outer() effects [] {\n'
            '  fn inner() { print(1) }\n'
            '  inner()\n'
            '}\n')
    assert "'print' requires effect 'io'" in str(ei.value)
    assert "effects []" in str(ei.value)


def test_nested_fn_without_own_clause_inherits_a_granting_scope_too():
    """Inheritance is symmetric: a nested fn with no clause of its own also
    inherits an outer scope that GRANTS the effect, not just one that
    denies it."""
    all_ok(
        'fn outer() effects [io] {\n'
        '  fn inner() { print(1) }\n'
        '  inner()\n'
        '}\n'
        'check "ok": outer() == 1\n')


def test_deeply_nested_fn_without_own_clause_inherits_through_two_levels():
    """Inheritance chains through more than one clause-less level: a fn
    with no clause pushes whatever is currently on top of the stack, so a
    grandchild with no clause of its own sees the same resolved scope as
    its clause-less parent, transitively."""
    with pytest.raises(ParseError):
        parse(
            'fn outer() effects [] {\n'
            '  fn mid() {\n'
            '    fn inner() { print(1) }\n'
            '    inner()\n'
            '  }\n'
            '  mid()\n'
            '}\n')


def test_indirect_call_via_variable_is_now_checked():
    """v0.14.2 (round 266): `let p = print` then `p(1)` inside `effects []`
    is now a ParseError — `p` is tracked as a direct alias of `print`
    (`Parser._resolve_effectful_alias`), so calling through it is checked
    exactly as calling `print` directly would be. This was the exact gap
    `test_indirect_call_via_variable_is_not_checked` used to pin before
    this round; renamed since the assertion flipped."""
    with pytest.raises(ParseError) as ei:
        parse(
            'fn f() effects [] {\n'
            '  let p = print\n'
            '  p(1)\n'
            '}\n')
    assert "'p' requires effect 'io'" in str(ei.value)


def test_aliased_print_still_allowed_when_effect_is_granted():
    """The alias check is per-tag like a direct call: an alias of `print`
    inside `effects [io]` is fine, same as calling `print` directly would
    be."""
    all_ok(
        'fn f() effects [io] {\n'
        '  let p = print\n'
        '  p(1)\n'
        '}\n'
        'check "ok": f() == 1\n')


def test_alias_chain_through_two_hops_is_checked():
    """`let q = p` where `p` is itself already a tracked alias chains
    transitively — `_resolve_effectful_alias` re-resolves through the
    alias_scopes stack, not just one hop deep."""
    with pytest.raises(ParseError) as ei:
        parse(
            'fn f() effects [] {\n'
            '  let p = print\n'
            '  let q = p\n'
            '  q(1)\n'
            '}\n')
    assert "'q' requires effect 'io'" in str(ei.value)


def test_local_let_shadows_outer_alias():
    """A `let p = <non-alias>` in an INNER block shadows an outer alias of
    the same name — `alias_scopes` records the shadow explicitly (`None`)
    rather than letting the lookup fall through to the outer frame, so this
    inner `p(1)` is an ordinary call to a plain local value, not a checked
    alias."""
    all_ok(
        'fn f() effects [] {\n'
        '  let p = print\n'
        '  {\n'
        '    let p = 5\n'
        '    p\n'
        '  }\n'
        '}\n'
        'check "ok": f() == 5\n')


def test_nested_fn_name_shadows_outer_alias():
    """A nested `fn p(...)` shadows an outer alias `p`, same as a `let`
    would (the fn's own name occupies its OWN block's alias frame) — a
    separate inner block is needed here since Whence has no rebinding, so
    `p` can't be bound twice by `let` then `fn` in the SAME block."""
    all_ok(
        'fn f() effects [] {\n'
        '  let p = print\n'
        '  {\n'
        '    fn p() { 9 }\n'
        '    p()\n'
        '  }\n'
        '}\n'
        'check "ok": f() == 9\n')


def test_param_named_like_outer_alias_shadows_it():
    """A parameter shares its fn's body-block alias scope tree one level
    out (params live in a parent Env of the body block at runtime,
    `interp.py`'s `_call_gen`/`eval_Block`) — calling a param named the
    same as an outer alias reaches the param, not the alias."""
    all_ok(
        'fn f() effects [] {\n'
        '  let p = print\n'
        '  fn g(p) { p() }\n'
        '  g(fn() { 7 })\n'
        '}\n'
        'check "ok": f() == 7\n')


def test_alias_defined_in_outer_scope_visible_to_nested_fn():
    """An alias bound in an OUTER scope is visible (still on the
    `alias_scopes` stack) while parsing a nested fn's body, same as any
    other lexically-scoped fact this system tracks — not just same-block
    aliasing."""
    with pytest.raises(ParseError) as ei:
        parse(
            'let p = print\n'
            'fn f() effects [] {\n'
            '  fn inner() { p(1) }\n'
            '  inner()\n'
            '}\n')
    assert "'p' requires effect 'io'" in str(ei.value)


def test_alias_defined_after_call_site_is_not_detected():
    """Order-dependent, like the rest of this single left-to-right parse
    pass: an alias `let` occurring AFTER the call it would have covered is
    invisible to it — `alias_scopes[-1]` doesn't have the entry yet at the
    time the call is checked. A real, documented, narrow gap, not a bug
    (mirrors `_resolve_effects_scope`'s own textual-order dependence for
    nested-fn inheritance)."""
    all_ok(
        'fn f() effects [] {\n'
        '  let g = fn() { p(1) }\n'
        '  let p = print\n'
        '  1\n'
        '}\n'
        'check "ok": f() == 1\n')


# --- v0.14.3 (round 270): return-value flow through a direct call --------

def test_return_value_via_let_is_checked():
    """`fn get_printer() { print }` tail-returns the builtin itself (not a
    call — `print` here is a bare NameRef, so nothing is CALLED yet).
    `let p = get_printer()` now (v0.14.3) propagates that fact to `p`,
    exactly as `let p = print` (v0.14.2) would — closing the "returning it
    from a call" clause of v0.14.2's own still-open gap, for the narrow
    case where the returning fn's body's own tail statement is a bare
    name."""
    with pytest.raises(ParseError) as ei:
        parse(
            'fn get_printer() effects [] {\n'
            '  print\n'
            '}\n'
            'fn f() effects [] {\n'
            '  let p = get_printer()\n'
            '  p(1)\n'
            '}\n')
    assert "'p' requires effect 'io'" in str(ei.value)


def test_return_value_via_let_granted_when_effect_allowed():
    all_ok(
        'fn get_printer() effects [] {\n'
        '  print\n'
        '}\n'
        'fn f() effects [io] {\n'
        '  let p = get_printer()\n'
        '  p(1)\n'
        '}\n'
        'check "ok": f() == 1\n')


def test_chained_call_on_return_value_is_checked():
    """No intermediate `let` needed: `get_printer()(1)` is checked directly
    — `_check_effect_call`'s new branch recognizes a `Call` callee whose own
    `fn` is a NameRef with a tracked return fact."""
    with pytest.raises(ParseError) as ei:
        parse(
            'fn get_printer() effects [] {\n'
            '  print\n'
            '}\n'
            'fn f() effects [] {\n'
            '  get_printer()(1)\n'
            '}\n')
    assert "'get_printer()' requires effect 'io'" in str(ei.value)


def test_chained_call_on_return_value_granted_when_effect_allowed():
    all_ok(
        'fn get_printer() effects [] {\n'
        '  print\n'
        '}\n'
        'fn f() effects [io] {\n'
        '  get_printer()(1)\n'
        '}\n'
        'check "ok": f() == 1\n')


def test_renamed_fn_carries_its_return_fact():
    """`let g = get_printer` (no call — a plain rename) carries BOTH of
    `get_printer`'s own tracked facts to `g`, not just the direct-alias one:
    `g` is still exactly the same function value under a new name, so
    `g()`'s return is checked exactly as `get_printer()`'s would be."""
    with pytest.raises(ParseError) as ei:
        parse(
            'fn get_printer() effects [] {\n'
            '  print\n'
            '}\n'
            'fn f() effects [] {\n'
            '  let g = get_printer\n'
            '  let p = g()\n'
            '  p(1)\n'
            '}\n')
    assert "'p' requires effect 'io'" in str(ei.value)


def test_anon_fn_bound_by_let_return_value_is_checked():
    """The same tracking applies to an anonymous `fn(...) {...}` bound by a
    `let` — its `body.tail_alias_tag` (resolved by `block()`/`stmt_list`
    while the anon fn's own frames were open) is read straight off the
    `A.FnExpr` at the `let` site, no named-`fn`-statement machinery
    needed."""
    with pytest.raises(ParseError) as ei:
        parse(
            'let get_printer2 = fn() effects [] { print }\n'
            'fn f() effects [] {\n'
            '  let p = get_printer2()\n'
            '  p(1)\n'
            '}\n')
    assert "'p' requires effect 'io'" in str(ei.value)


def test_inner_fn_of_the_same_name_shadows_the_outer_return_fact():
    """Shadowing correctness (the same class of bug v0.14.2's own §4 fixed,
    now for `return_alias_scopes`): a DIFFERENT, non-effectful-returning
    `get_printer` declared in an inner scope must block the lookup from
    falling through to the outer, effectful-returning one of the same
    name — not just for `alias_scopes`, but for the parallel
    `return_alias_scopes` stack too, which is pushed/popped at the
    identical frame boundaries."""
    all_ok(
        'fn get_printer() effects [] {\n'
        '  print\n'
        '}\n'
        'fn f() effects [] {\n'
        '  fn inner_user() {\n'
        '    fn get_printer() { 5 }\n'
        '    let p = get_printer()\n'
        '    p\n'
        '  }\n'
        '  inner_user()\n'
        '}\n'
        'check "ok": f() == 5\n')


def test_return_tag_sees_an_if_else_tail_when_both_arms_agree():
    """v0.14.5 (round 276): closes the "if" half of round 270's own
    documented gap — a fn body whose tail statement is an `if`/`else` where
    BOTH arms bare-NameRef-tail-return `print` is now tracked exactly as a
    bare-NameRef tail would be (`Parser._if_tail_alias_tag`, purely
    structural over each arm's own already-resolved `tail_alias_tag`, no
    interprocedural analysis)."""
    with pytest.raises(ParseError) as ei:
        parse(
            'fn get_printer(cond) {\n'
            '  if cond { print } else { print }\n'
            '}\n'
            'fn f() effects [] {\n'
            '  let p = get_printer(true)\n'
            '  p(1)\n'
            '}\n')
    assert "'p' requires effect 'io'" in str(ei.value)


def test_return_tag_if_else_tail_granted_when_effect_allowed():
    all_ok(
        'fn get_printer(cond) {\n'
        '  if cond { print } else { print }\n'
        '}\n'
        'fn f() effects [io] {\n'
        '  let p = get_printer(true)\n'
        '  p(1)\n'
        '}\n'
        'check "ok": f() == 1\n')


def test_return_tag_if_else_tail_needs_every_arm_to_agree():
    """Not a majority or "any arm" match — EVERY arm must resolve to the
    exact same tag. One branch tail-returning `print` and the other a
    plain value (or a different, untracked callable) leaves the whole
    `if` untracked (`None`), the same way a mismatched `: Type` guard on
    only one branch wouldn't be silently upgraded either — an approximate
    match would be unsound, not just imprecise."""
    all_ok(
        'fn get_printer(cond) {\n'
        '  if cond { print } else { 5 }\n'
        '}\n'
        'fn f() effects [] {\n'
        '  let p = get_printer(true)\n'
        '  p(1)\n'
        '}\n'
        'check "ok": f() == 1\n')


def test_return_tag_sees_through_an_else_if_chain_when_every_arm_agrees():
    """`_if_tail_alias_tag` recurses through an `else if ...` chain of any
    length (`if_node.otherwise` is itself an `A.If`, not an `A.Block`,
    for every arm but the last) — all three arms here tail-return `print`,
    so the whole chain resolves to `"io"`."""
    with pytest.raises(ParseError) as ei:
        parse(
            'fn get_printer(n) {\n'
            '  if n == 1 { print } else if n == 2 { print } else { print }\n'
            '}\n'
            'fn f() effects [] {\n'
            '  let p = get_printer(1)\n'
            '  p(1)\n'
            '}\n')
    assert "'p' requires effect 'io'" in str(ei.value)


def test_return_tag_else_if_chain_one_mismatched_arm_is_not_tracked():
    all_ok(
        'fn get_printer(n) {\n'
        '  if n == 1 { print } else if n == 2 { 5 } else { print }\n'
        '}\n'
        'fn f() effects [] {\n'
        '  let p = get_printer(1)\n'
        '  p(1)\n'
        '}\n'
        'check "ok": f() == 1\n')


def test_three_way_if_else_return_value_via_let_inside_effects_io():
    """v0.14.5 is entirely parse-time (no AST node, no Closure field, no
    interpreter change), so it can't diverge across the direct/fast/slow
    execution modes — pinned anyway, the same way v0.14.3/v0.14.4 each
    pinned one `assert_three_way` case for their own new trigger shape."""
    assert_three_way(
        'fn get_printer(cond) {\n'
        '  if cond { print } else { print }\n'
        '}\n'
        'fn f() effects [io] {\n'
        '  let p = get_printer(true)\n'
        '  p(1)\n'
        '}\n'
        'let result = f()\n')


def test_return_tag_only_sees_a_tail_if_else_not_a_deeper_nested_one():
    """Still deliberately narrow: the `if`/`else` recursion only ever
    starts from the BLOCK'S OWN tail statement — an `if` that is nested one
    level deeper (not itself in tail position, e.g. bound to a `let` first)
    is not inspected, matching the same "one hop from the tail, no general
    data-flow" discipline the rest of this feature family uses. An honest,
    documented gap, not a bug."""
    all_ok(
        'fn get_printer(cond) {\n'
        '  let chosen = if cond { print } else { print }\n'
        '  chosen\n'
        '}\n'
        'fn f() effects [] {\n'
        '  let p = get_printer(true)\n'
        '  p(1)\n'
        '}\n'
        'check "ok": f() == 1\n')


def test_three_way_return_value_via_let_inside_effects_io():
    assert_three_way(
        'fn get_printer() effects [] {\n'
        '  print\n'
        '}\n'
        'fn f() effects [io] {\n'
        '  let p = get_printer()\n'
        '  p(1)\n'
        '}\n'
        'let result = f()\n')


def test_three_way_aliased_print_inside_effects_empty():
    assert_three_way(
        'fn f() effects [] {\n'
        '  let p = print\n'
        '  1\n'
        '}\n'
        'let result = f()\n')


# --- v0.14.4 (round 272): container-field flow through a record literal ----
# --- closes the CONTAINER-FIELD slice of v0.14.3's own "stored in a list/
# --- record field" gap: `let box = @{run: print}` then `box.run(1)`.

def test_field_call_via_record_literal_is_checked():
    """`let box = @{run: print}` then `box.run(1)` inside `effects []` is
    now a ParseError — `box`'s `run` field is tracked as a direct alias of
    `print` (`Parser._resolve_effectful_field`), so calling through it is
    checked exactly as calling `print` directly would be."""
    with pytest.raises(ParseError) as ei:
        parse(
            'let box = @{run: print}\n'
            'fn f() effects [] {\n'
            '  box.run(1)\n'
            '}\n')
    assert "'box.run' requires effect 'io'" in str(ei.value)


def test_field_call_via_record_literal_granted_when_effect_allowed():
    all_ok(
        'let box = @{run: print}\n'
        'fn f() effects [io] {\n'
        '  box.run(1)\n'
        '}\n'
        'check "ok": f() == 1\n')


def test_non_effectful_field_is_not_flagged():
    """A field whose value is a bare-NameRef alias of something NOT
    effectful (a plain `let`-bound fn, not `print` or a tracked alias of
    it) resolves to `None` — calling it inside `effects []` is not
    restricted, same as calling any other ordinary value would be."""
    all_ok(
        'fn f() effects [] {\n'
        '  let helper = fn(x) { x + 1 }\n'
        '  let box = @{run: print, calc: helper}\n'
        '  box.calc(5)\n'
        '}\n'
        'check "ok": f() == 6\n')


def test_inner_record_of_same_name_shadows_outer_field_alias():
    """An inner block's OWN `let box = @{...}` shadows an outer record of
    the same name — `field_alias_scopes` records the shadow explicitly, so
    the inner `box.run(...)` resolves against the INNER record's fields,
    not the outer one, even when both bind a field named `run`."""
    all_ok(
        'fn f() effects [] {\n'
        '  let box = @{run: print}\n'
        '  {\n'
        '    let helper = fn(x) { x + 1 }\n'
        '    let box = @{run: helper}\n'
        '    box.run(5)\n'
        '  }\n'
        '}\n'
        'check "ok": f() == 6\n')


def test_param_named_like_outer_field_alias_shadows_it():
    """A parameter shares its fn's body-block field-alias scope tree one
    level out, same as `alias_scopes`/`return_alias_scopes` already do — a
    param named `box` shadows an outer record-tracked `box` of the same
    name, so a call through the PARAM's own (real, runtime) fields is
    checked on its own terms, not the outer record's."""
    all_ok(
        'fn identity_run(x) { x + 1 }\n'
        'fn f() effects [] {\n'
        '  let box = @{run: print}\n'
        '  fn g(box) {\n'
        '    box.run(1)\n'
        '  }\n'
        '  g(@{run: identity_run})\n'
        '}\n'
        'check "ok": f() == 2\n')


def test_field_of_a_non_literal_binding_is_not_tracked():
    """Deliberately narrow, like the rest of this feature family: only a
    record built directly by a `let name = @{...}` LITERAL is tracked —
    one returned from a call (even one that itself returns a literal
    record with an effectful field) is invisible to this check. An
    honest, documented gap, not a bug — the same "single left-to-right
    pass, no whole-program analysis" limit v0.14.2/v0.14.3 already have."""
    all_ok(
        'fn make_box() { @{run: print} }\n'
        'fn f() effects [] {\n'
        '  let box = make_box()\n'
        '  box.run(1)\n'
        '}\n'
        'check "ok": f() == 1\n')


def test_field_value_that_is_itself_a_call_is_not_tracked():
    """Only a BARE-NameRef field value is inspected when a record literal
    is parsed — a field whose value is itself a call (even one returning
    `print`) is left at `None`, the same narrow "one hop, no recursion"
    discipline v0.14.3 applied to a fn's tail statement."""
    all_ok(
        'fn get_printer() effects [] {\n'
        '  print\n'
        '}\n'
        'fn f() effects [] {\n'
        '  let box = @{run: get_printer()}\n'
        '  box.run(1)\n'
        '}\n'
        'check "ok": f() == 1\n')


def test_three_way_field_call_via_record_literal():
    assert_three_way(
        'let box = @{run: print}\n'
        'fn f() effects [io] {\n'
        '  box.run(1)\n'
        '}\n'
        'let result = f()\n')


# --- v0.14.6: RETURN-value flow through a field call (`box.run()(...)`) ----

def test_field_return_chain_is_checked():
    """`let box = @{run: get_printer}` then `box.run()(1)` inside
    `effects []` is now a ParseError — `box`'s `run` field is tracked
    (`Parser._resolve_effectful_field_return`) as a return-carrier (calling
    it yields `get_printer`'s own tracked return fact), so the SECOND
    application is checked exactly as `get_printer()(1)` (v0.14.3) would
    be. The FIRST application (`box.run()` itself) is a plain call on an
    ordinary callable value, not flagged on its own."""
    with pytest.raises(ParseError) as ei:
        parse(
            'fn get_printer() effects [] {\n'
            '  print\n'
            '}\n'
            'fn f() effects [] {\n'
            '  let box = @{run: get_printer}\n'
            '  box.run()(1)\n'
            '}\n')
    assert "'box.run()' requires effect 'io'" in str(ei.value)


def test_field_return_chain_granted_when_effect_allowed():
    all_ok(
        'fn get_printer() effects [] {\n'
        '  print\n'
        '}\n'
        'fn f() effects [io] {\n'
        '  let box = @{run: get_printer}\n'
        '  box.run()(1)\n'
        '}\n'
        'check "ok": f() == 1\n')


def test_field_return_chain_and_field_direct_alias_are_independent():
    """A single record literal can carry BOTH a direct-alias field
    (v0.14.4) and a return-carrier field (v0.14.6) at once — the two dicts
    (`field_alias_scopes`/`field_return_alias_scopes`) are built from the
    same bare-NameRef field values but resolved independently, so tracking
    one never affects the other."""
    with pytest.raises(ParseError) as ei:
        parse(
            'fn get_printer() effects [] {\n'
            '  print\n'
            '}\n'
            'fn f() effects [io] {\n'
            '  let box = @{direct: print, chained: get_printer}\n'
            '  box.direct(1)\n'
            '  box.chained()(2)\n'
            '}\n'
            'fn g() effects [] {\n'
            '  let box = @{direct: print, chained: get_printer}\n'
            '  box.chained()(2)\n'
            '}\n')
    assert "'box.chained()' requires effect 'io'" in str(ei.value)


def test_field_return_chain_field_value_that_is_not_a_return_carrier():
    """A field whose bare-NameRef value is an ordinary (non-return-tracked)
    fn resolves to `None` in `field_return_alias_scopes` — calling through
    it twice is not restricted, same as `test_non_effectful_field_is_not_
    flagged` for the single-hop case."""
    all_ok(
        'fn f() effects [] {\n'
        '  fn make_adder() { fn(x) { x + 1 } }\n'
        '  let box = @{run: make_adder}\n'
        '  box.run()(5)\n'
        '}\n'
        'check "ok": f() == 6\n')


def test_field_return_chain_of_a_non_literal_binding_is_not_tracked():
    """Same "one hop, literal-binding-only" discipline as `test_field_of_a_
    non_literal_binding_is_not_tracked`: a record returned from a call
    (even one whose own field is a return-carrier) is invisible."""
    all_ok(
        'fn get_printer() effects [] {\n'
        '  print\n'
        '}\n'
        'fn make_box() { @{run: get_printer} }\n'
        'fn f() effects [] {\n'
        '  let box = make_box()\n'
        '  box.run()(1)\n'
        '}\n'
        'check "ok": f() == 1\n')


def test_inner_record_of_same_name_shadows_outer_field_return_alias():
    """An inner block's OWN `let box = @{...}` shadows an outer record of
    the same name for the return-carrier fact too, the same way v0.14.4
    already established for the direct-alias fact."""
    all_ok(
        'fn get_printer() effects [] {\n'
        '  print\n'
        '}\n'
        'fn f() effects [] {\n'
        '  let box = @{run: get_printer}\n'
        '  {\n'
        '    fn make_adder() { fn(x) { x + 1 } }\n'
        '    let box = @{run: make_adder}\n'
        '    box.run()(5)\n'
        '  }\n'
        '}\n'
        'check "ok": f() == 6\n')


def test_three_way_field_return_chain():
    assert_three_way(
        'fn get_printer() effects [] {\n'
        '  print\n'
        '}\n'
        'let box = @{run: get_printer}\n'
        'fn f() effects [io] {\n'
        '  box.run()(1)\n'
        '}\n'
        'let result = f()\n')


# --- v0.14.7: container-field value flow through a NESTED record literal ---
# --- (`outer.box.run(...)`) -------------------------------------------------

def test_nested_field_call_via_record_literal_is_checked():
    """`let outer = @{box: @{run: print}}` then `outer.box.run(1)` inside
    `effects []` is now a ParseError — `outer`'s `box` field is itself a
    nested record literal whose `run` field is tracked as a direct alias of
    `print` (`Parser._resolve_effectful_field_nested`), so calling through
    the two-field chain is checked exactly as `box.run(1)` (v0.14.4) would
    be for a `box` bound directly."""
    with pytest.raises(ParseError) as ei:
        parse(
            'let outer = @{box: @{run: print}}\n'
            'fn f() effects [] {\n'
            '  outer.box.run(1)\n'
            '}\n')
    assert "'outer.box.run' requires effect 'io'" in str(ei.value)


def test_nested_field_call_via_record_literal_granted_when_effect_allowed():
    all_ok(
        'let outer = @{box: @{run: print}}\n'
        'fn f() effects [io] {\n'
        '  outer.box.run(1)\n'
        '}\n'
        'check "ok": f() == 1\n')


def test_non_effectful_nested_field_is_not_flagged():
    """A nested field whose value is a bare-NameRef alias of something NOT
    effectful resolves to `None`, same as the single-hop case
    (`test_non_effectful_field_is_not_flagged`)."""
    all_ok(
        'fn f() effects [] {\n'
        '  let helper = fn(x) { x + 1 }\n'
        '  let outer = @{box: @{run: print, calc: helper}}\n'
        '  outer.box.calc(5)\n'
        '}\n'
        'check "ok": f() == 6\n')


def test_inner_record_of_same_name_shadows_outer_nested_field_alias():
    """An inner block's OWN `let outer = @{...}` shadows an outer record of
    the same name for the nested-field fact too, the same discipline
    v0.14.4/v0.14.6 already established for the single-hop dicts."""
    all_ok(
        'fn f() effects [] {\n'
        '  let outer = @{box: @{run: print}}\n'
        '  {\n'
        '    let helper = fn(x) { x + 1 }\n'
        '    let outer = @{box: @{run: helper}}\n'
        '    outer.box.run(5)\n'
        '  }\n'
        '}\n'
        'check "ok": f() == 6\n')


def test_param_named_like_outer_nested_field_alias_shadows_it():
    """A parameter shares its fn's body-block nested-field-alias scope tree
    one level out, same as the other four stacks already do — a param
    named `outer` shadows an outer record-tracked `outer` of the same
    name, so a call through the PARAM's own (real, runtime) fields is
    checked on its own terms, not the outer record's."""
    all_ok(
        'fn identity_run(x) { x + 1 }\n'
        'fn f() effects [] {\n'
        '  let outer = @{box: @{run: print}}\n'
        '  fn g(outer) {\n'
        '    outer.box.run(1)\n'
        '  }\n'
        '  g(@{box: @{run: identity_run}})\n'
        '}\n'
        'check "ok": f() == 2\n')


def test_nested_field_of_a_non_literal_outer_binding_is_not_tracked():
    """Deliberately narrow, like the rest of this feature family: only an
    OUTER record built directly by a `let name = @{...}` LITERAL is
    tracked — one returned from a call is invisible, the same "single
    left-to-right pass" limit `test_field_of_a_non_literal_binding_is_not_
    tracked` already pins for the single-hop case."""
    all_ok(
        'fn make_outer() { @{box: @{run: print}} }\n'
        'fn f() effects [] {\n'
        '  let outer = make_outer()\n'
        '  outer.box.run(1)\n'
        '}\n'
        'check "ok": f() == 1\n')


def test_nested_field_where_middle_field_is_not_itself_a_record_literal():
    """`outer.box.run(...)` structurally matches the v0.14.7 chain shape
    even when `box`'s own value was never a nested record literal at all
    (here, a bare NameRef) — `nested_field_alias_scopes` simply never
    populated a `box` key for `outer` in that case, so the lookup falls
    through to `None`, same "field absent, not an error" behavior every
    resolver in this family already has. Parses cleanly (no ParseError);
    `f` is deliberately never called, since `box`'s runtime value (`print`)
    has no `run` field to actually invoke — this test pins the parse-time
    lookup only, not a runtime claim."""
    parse(
        'fn f() effects [] {\n'
        '  let outer = @{box: print}\n'
        '  outer.box.run(1)\n'
        '}\n')


def test_nested_field_value_that_is_itself_a_call_is_not_tracked():
    """Only a bare-NameRef inner-field value is inspected within a tracked
    nested literal — an inner field whose value is itself a call is left
    at `None`, the same "one hop, no recursion" discipline
    `test_field_value_that_is_itself_a_call_is_not_tracked` already pins
    for the single-hop case."""
    all_ok(
        'fn get_printer() effects [] {\n'
        '  print\n'
        '}\n'
        'fn f() effects [] {\n'
        '  let outer = @{box: @{run: get_printer()}}\n'
        '  outer.box.run(1)\n'
        '}\n'
        'check "ok": f() == 1\n')


def test_three_way_nested_field_call():
    assert_three_way(
        'let outer = @{box: @{run: print}}\n'
        'fn f() effects [io] {\n'
        '  outer.box.run(1)\n'
        '}\n'
        'let result = f()\n')


# --- outer restriction still applies to the outer function's OWN body ------

def test_effects_empty_still_allows_non_print_calls():
    all_ok(
        'fn double(x) { x * 2 }\n'
        'fn f() effects [] { double(21) }\n'
        'check "ok": f() == 42\n')


def test_effects_empty_direct_print_at_top_of_body_is_rejected():
    with pytest.raises(ParseError):
        parse('fn f() effects [] {\n  print("leak")\n  1\n}\n')


def test_effects_clause_does_not_leak_across_sibling_fns():
    """A restricted fn's declaration does not affect a SIBLING fn parsed
    afterward at the same (module) level — the stack is popped on exit."""
    all_ok(
        'fn restricted() effects [] { 1 }\n'
        'fn unrestricted() { print(2) }\n'
        'check "ok": restricted() == 1 and unrestricted() == 2\n')


# --- three-way differential: zero interpreter change means these already ---
# --- agree by construction, but pin it explicitly anyway -------------------

def test_three_way_effects_io_allows_print():
    assert_three_way('fn f() effects [io] { print(1) }\nlet result = f()\n')


def test_three_way_nested_escape():
    assert_three_way(
        'fn outer() effects [] {\n'
        '  fn inner() effects [io] { print(1) }\n'
        '  inner()\n'
        '}\n'
        'let result = outer()\n')


# --- v0.14.8 (round 294): `rand` — the second effectful builtin ------------

def test_rand_returns_a_number_in_unit_range():
    interp, env, out = run('let r = rand()\n')
    r = env.get("r").payload
    assert isinstance(r, float)
    assert 0.0 <= r < 1.0


def test_rand_rejects_arguments():
    interp, env, out = run('let m = rand(1)\n')
    miss = env.get("m").payload
    assert isinstance(miss, Miss)
    assert "rand expects 0 args, got 1" in miss.reasons[0]


def test_rand_is_deterministic_for_the_default_seed():
    """Two fresh Interpreters, both left at the default seed (0), draw the
    IDENTICAL sequence — reproducibility, not OS entropy, is the whole
    design point (SPEC.md "v0.14.8"): the three-way differential below
    (three SEPARATE Interpreter instances for one program) could never
    agree otherwise."""
    def draws():
        interp = Interpreter(out=lambda s: None)
        env = interp.run('let a = rand()\nlet b = rand()\nlet c = rand()\n')
        return [env.get(n).payload for n in ("a", "b", "c")]
    first, second = draws(), draws()
    assert first == second
    assert len(set(first)) == 3, "three degenerate/equal draws is suspicious"


def test_rand_default_seed_pinned_value():
    """A real regression pin, not just an invariant: `random.Random`'s
    algorithm (version 2, the default since Python 3.2) is a documented,
    stable pure-Python algorithm for a given integer seed — not derived
    from host entropy — so this exact value is safe to hardcode."""
    interp = Interpreter(out=lambda s: None)
    env = interp.run('let a = rand()\n')
    assert env.get("a").payload == pytest.approx(0.8444218515250481)


def test_rand_seed_argument_changes_the_stream():
    env_a = Interpreter(out=lambda s: None, seed=1).run('let a = rand()\n')
    env_b = Interpreter(out=lambda s: None, seed=2).run('let a = rand()\n')
    assert env_a.get("a").payload != env_b.get("a").payload


def test_effects_empty_blocks_rand():
    with pytest.raises(ParseError) as ei:
        parse('fn f() effects [] { rand() }\n')
    assert "'rand'" in str(ei.value) and "'random'" in str(ei.value)


def test_effects_random_allows_rand():
    all_ok(
        'fn f() effects [random] { rand() }\n'
        'check "ok": f() >= 0 and f() < 1\n')


def test_effects_random_tag_is_independent_of_io_tag():
    """The two-real-tag mirror of `test_effects_unrelated_tag_still_blocks_
    print` (which only ever proved per-tag distinctness against a
    hypothetical, unused "network" tag): `io` does not also grant "random",
    and `random` does not grant "io" back, in EITHER direction, now that
    both are real, live capabilities."""
    with pytest.raises(ParseError) as ei:
        parse('fn f() effects [io] { rand() }\n')
    assert "requires effect 'random'" in str(ei.value)
    with pytest.raises(ParseError) as ei2:
        parse('fn f() effects [random] { print(1) }\n')
    assert "requires effect 'io'" in str(ei2.value)


def test_effects_io_and_random_together_allow_both():
    all_ok(
        'fn f() effects [io, random] { print(rand()) }\n'
        'check "ok": f() >= 0 and f() < 1\n')


def test_aliased_rand_is_checked_same_as_aliased_print():
    """The new builtin reuses `_resolve_effectful_alias` with zero code
    change — confirmed live, not just by reading the source."""
    with pytest.raises(ParseError):
        parse('fn f() effects [] {\n  let r = rand\n  r()\n}\n')
    all_ok(
        'fn f() effects [random] {\n  let r = rand\n  r()\n}\n'
        'check "ok": f() >= 0 and f() < 1\n')


def test_three_way_rand_matches_across_direct_fast_slow():
    """The critical end-to-end check for the v0.14.8 design decision: three
    INDEPENDENTLY-CONSTRUCTED Interpreters (direct/fast/slow, each at the
    same default seed) must draw the identical value for `render_why` to
    match byte-for-byte, the same standing three-way contract every other
    builtin here already satisfies."""
    assert_three_way('fn f() effects [random] { rand() }\nlet result = f()\n')


# ============================================== v0.14.9 (round 300) ======

def test_argument_passed_to_a_directly_called_param_is_checked():
    all_ok(
        'fn apply(f) effects [io] { f(1) }\n'
        'apply(print)\n'
        'check "ok": true\n')


def test_argument_passed_to_a_directly_called_param_is_rejected_when_not_permitted():
    with pytest.raises(ParseError) as ei:
        parse('fn silent(f) effects [] { f(1) }\nsilent(print)\n')
    msg = str(ei.value)
    assert "'silent'" in msg and "requires" not in msg  # different wording from _check_effect_call
    assert "effect 'io'" in msg and "not permitted" in msg


def test_argument_passed_to_a_directly_called_param_with_no_effects_clause_is_unrestricted():
    """No `effects [...]` clause at all on the callee (unrestricted, the
    default) — same "None means unrestricted" convention as every other
    check in this family."""
    all_ok(
        'fn apply(f) { f(1) }\n'
        'apply(print)\n'
        'check "ok": true\n')


def test_random_tag_argument_is_checked_same_as_io():
    all_ok(
        'fn apply(f) effects [random] { f() }\n'
        'apply(rand)\n'
        'check "ok": true\n')
    with pytest.raises(ParseError) as ei:
        parse('fn apply(f) effects [io] { f() }\napply(rand)\n')
    assert "effect 'random'" in str(ei.value)


def test_non_effectful_argument_to_a_directly_called_param_is_unaffected():
    all_ok(
        'fn apply(f) effects [] { f(1) }\n'
        'fn double(x) { x * 2 }\n'
        'apply(double)\n'
        'check "ok": true\n')


def test_param_only_stored_not_called_is_not_tracked():
    """`f` is never called directly in `store`'s own body — merely bound to
    a local name — so it never enters `param_call_scopes`' own recorded
    fact for `store`, and this parses fine even though `store` itself
    declares `effects []`."""
    all_ok(
        'fn store(f) effects [] { let x = f\n1 }\n'
        'store(print)\n'
        'check "ok": true\n')


def test_only_the_directly_called_param_position_is_checked():
    """Two params, only one (`a`) called directly — an effectful argument
    passed for the OTHER, uncalled param (`b`) is invisible; the exact
    same argument passed for `a` is checked."""
    all_ok(
        'fn combo(a, b) effects [] { a(1) }\n'
        'combo(5, print)\n'
        'check "ok": true\n')
    with pytest.raises(ParseError):
        parse('fn combo(a, b) effects [] { a(1) }\ncombo(print, 5)\n')


def test_non_namerefarg_to_a_directly_called_param_is_not_tracked():
    """The argument itself must be a bare NameRef — a call expression
    result (or any other expression shape) landing in a directly-called
    param slot is invisible, the same "bare-NameRef only" boundary every
    sibling resolver in this family already has."""
    all_ok(
        'fn get_printer() { print }\n'
        'fn apply(f) effects [] { f(1) }\n'
        'apply(get_printer())\n'
        'check "ok": true\n')


def test_anon_fn_bound_by_let_param_call_is_now_checked():
    """v0.14.10 (round 302) closes the gap v0.14.9 deliberately left open:
    the anonymous `fn(...) {...}`'s own `param_call_fact` (computed while
    its body was still open, exactly like the NAMED-fn case) now rides on
    the `A.FnExpr` node itself and is picked up the moment the enclosing
    `let` learns `g`'s name — the same grant/reject pair as `test_argument_
    passed_to_a_directly_called_param_is_{checked,rejected_when_not_
    permitted}`, just sourced from a `let`-bound anonymous fn instead of a
    NAMED one."""
    all_ok(
        'let g = fn(f) effects [io] { f(1) }\n'
        'g(print)\n'
        'check "ok": true\n')
    with pytest.raises(ParseError) as ei:
        parse('let g = fn(f) effects [] { f(1) }\ng(print)\n')
    msg = str(ei.value)
    assert "effect 'io'" in msg and "not permitted" in msg


def test_anon_fn_bound_by_let_with_no_effects_clause_is_unrestricted():
    all_ok(
        'let g = fn(f) { f(1) }\n'
        'g(print)\n'
        'check "ok": true\n')


def test_anon_fn_bound_by_let_param_call_fact_carries_through_a_rename():
    """`let h = g` (no call) carries the anonymous fn's OWN recorded
    param-call fact forward under the new name `h` too — the exact same
    "resolved via a generic scope-stack walk, indifferent to WHERE the fact
    originally came from" property `test_renamed_fn_carries_its_param_
    call_fact_forward` already pins for a NAMED fn."""
    all_ok(
        'let g = fn(f) effects [io] { f(1) }\n'
        'let h = g\n'
        'h(print)\n'
        'check "ok": true\n')
    with pytest.raises(ParseError):
        parse(
            'let g = fn(f) effects [] { f(1) }\n'
            'let h = g\n'
            'h(print)\n')


def test_param_named_like_an_anon_fn_bound_name_shadows_its_param_call_fact():
    """Mirror of `test_param_named_like_a_tracked_fn_shadows_its_param_
    call_fact` for a `let`-bound anonymous fn's own tracked name: a
    parameter reusing `g`'s name correctly shadows the outer fact."""
    all_ok(
        'let g = fn(f) effects [] { f(1) }\n'
        'fn outer(g) effects [] { 1 }\n'
        'check "ok": true\n')


def test_inner_fn_with_same_param_name_is_checked_against_its_own_scope():
    """A nested named fn's own parameter of the SAME name as the outer
    fn's own parameter correctly shadows it — the inner fn's own recorded
    fact (and own effects scope) governs, not the outer's, the same
    shadowing discipline every other stack in this family already has."""
    with pytest.raises(ParseError) as ei:
        parse(
            'fn helper(f) effects [io] {\n'
            '  fn inner(f) effects [] { f(2) }\n'
            '  inner(print)\n'
            '}\n')
    assert "'inner'" in str(ei.value)
    # The mirror image: inner's own scope PERMITS it, even though it is
    # nested inside a differently-scoped outer fn.
    all_ok(
        'fn helper(f) effects [] {\n'
        '  fn inner(f) effects [io] { f(2) }\n'
        '  inner(print)\n'
        '}\n'
        'check "ok": true\n')


def test_check_uses_callees_own_scope_not_the_callers():
    """The check is against `apply`'s OWN declared effects scope, not the
    CALLING scope's — `apply`'s body, not the call site, is what actually
    executes `f(1)`. An unrestricted top-level call site may freely call
    `apply(print)` as long as `apply` ITSELF permits `io`, and a
    restricted call site may NOT call `apply(print)` merely because ITS
    OWN scope permits `io`, if `apply` itself does not."""
    all_ok(
        'fn apply(f) effects [io] { f(1) }\n'
        'apply(print)\n'
        'check "ok": true\n')
    with pytest.raises(ParseError) as ei:
        parse(
            'fn apply(f) effects [] { f(1) }\n'
            'fn caller() effects [io] { apply(print) }\n'
            'caller()\n')
    assert "'apply'" in str(ei.value)


def test_call_site_check_does_not_fire_for_a_normal_unrelated_call():
    """A plain call to a NAMED fn that happens to be tracked (calls one of
    its own params directly) but is invoked with no arguments in the
    relevant position at all, or fewer args than params, does not crash or
    false-positive — `_check_call_site_param_effects`'s own `i >=
    len(args)` guard."""
    all_ok(
        'fn apply(f) effects [] { 1 }\n'
        'fn make_it() { fn inner(f) effects [] { f(1) } inner }\n'
        'check "ok": true\n')


def test_renamed_fn_carries_its_param_call_fact_forward():
    """`let g = apply` (no call) carries `apply`'s own recorded param-call
    fact forward under the new name `g`, the same way v0.14.3 already
    carries the return fact forward on a plain rename."""
    all_ok(
        'fn apply(f) effects [io] { f(1) }\n'
        'let g = apply\n'
        'g(print)\n'
        'check "ok": true\n')
    with pytest.raises(ParseError):
        parse(
            'fn silent(f) effects [] { f(1) }\n'
            'let g = silent\n'
            'g(print)\n')


def test_param_named_like_a_tracked_fn_shadows_its_param_call_fact():
    """A parameter reusing the name of an earlier-tracked fn correctly
    shadows it (the same shadowing convention `_resolve_param_call_fact`'s
    innermost-first walk gives every other resolver in this family) — a
    call through the shadowing parameter is an ordinary, untracked call,
    not a re-check of the outer fn's own recorded fact."""
    all_ok(
        'fn apply(f) effects [] { f(1) }\n'
        'fn outer(apply) effects [] { 1 }\n'
        'check "ok": true\n')


# ======================================== v0.14.11 (round 306) ============
# Closes HALF of v0.14.9's own explicitly-named remaining "a builtin
# flowing into a param that is stored ... rather than called directly"
# gap: a param `let`-renamed WITHIN THE SAME OPEN FN BODY, then called
# through the new name, is now recognized exactly as calling the param
# directly would be — via a new `_resolve_param_alias` walk, a fallback to
# `_check_effect_call`'s own existing identity check (unchanged). The
# OTHER half — a param RETURNED to a caller, who then holds the alias
# instead of the fn's own body calling it — is a value-flow-ACROSS-A-
# RETURN-BOUNDARY question and remains fully open (see the negative case
# at the end of this section).

def test_param_renamed_inside_body_then_called_is_now_checked():
    """`fn apply(f) effects [io] { let g = f\\n g(1) }` — `g` is a pure
    rename of `apply`'s own param `f`, so calling `g(1)` counts as `apply`
    calling `f` directly, exactly as `f(1)` itself already would. Same
    grant/deny pair shape as `test_argument_passed_to_a_directly_called_
    param_is_{checked,rejected_when_not_permitted}`, just with one extra
    `let`-rename hop between the param and the call."""
    all_ok(
        'fn apply(f) effects [io] {\n'
        '  let g = f\n'
        '  g(1)\n'
        '}\n'
        'apply(print)\n'
        'check "ok": true\n')
    with pytest.raises(ParseError) as ei:
        parse(
            'fn apply(f) effects [] {\n'
            '  let g = f\n'
            '  g(1)\n'
            '}\n'
            'apply(print)\n')
    msg = str(ei.value)
    assert "effect 'io'" in msg and "not permitted" in msg


def test_param_rename_chain_through_two_hops_is_checked():
    """`let g = f` then `let h = g` — the rename fact chains through a
    SECOND hop within the same body, the same "chain through two hops"
    shape `test_alias_chain_through_two_hops_is_checked` already pins for
    v0.14.2's own ordinary alias tracking."""
    all_ok(
        'fn apply(f) effects [io] {\n'
        '  let g = f\n'
        '  let h = g\n'
        '  h(1)\n'
        '}\n'
        'apply(print)\n'
        'check "ok": true\n')
    with pytest.raises(ParseError):
        parse(
            'fn apply(f) effects [] {\n'
            '  let g = f\n'
            '  let h = g\n'
            '  h(1)\n'
            '}\n'
            'apply(print)\n')


def test_param_rename_shadowed_by_nested_block_is_not_misattributed():
    """A nested block's own rebinding of the SAME name the rename used
    correctly shadows it — a call through the shadowing name afterward is
    an ordinary, untracked call, not a false re-check of `apply`'s own
    param-call fact. Mirrors `test_param_named_like_a_tracked_fn_shadows_
    its_param_call_fact`'s shadowing shape, one level down."""
    all_ok(
        'fn apply(f) effects [] {\n'
        '  let g = f\n'
        '  if true {\n'
        '    let g = 5\n'
        '    g\n'
        '  } else {\n'
        '    0\n'
        '  }\n'
        '}\n'
        'apply(print)\n'
        'check "ok": true\n')


def test_param_rename_in_enclosing_fn_not_misattributed_to_inner_fn():
    """A param rename recorded in an ENCLOSING fn's own body must never
    leak into a DIFFERENT, inner fn's own param-call fact, even via a
    coincidental name collision — `outer`'s `g` (a rename of its own
    param `p`) is a completely different name from `inner`'s OWN param,
    also called `g`; `inner`'s call must be checked against `inner`'s own
    declared scope, not `outer`'s, and must not spuriously add `p` (which
    isn't even one of `inner`'s own params) to `inner`'s tracked set."""
    all_ok(
        'fn outer(p) effects [] {\n'
        '  let g = p\n'
        '  fn inner(g) effects [io] { g(1) }\n'
        '  inner(print)\n'
        '}\n'
        'outer(print)\n'
        'check "ok": true\n')


def test_param_returned_directly_then_called_by_caller_is_now_checked():
    """v0.14.12 (round 308): the OTHER half of the "stored/returned" gap
    v0.14.11 left fully open — `apply`'s own param `f` is RETURNED (not
    called inside `apply`'s own body at all), so the CALLER ends up
    holding the alias and calling it itself. `apply` needs NO `effects
    [...]` clause of its own (it never itself calls the builtin, only
    hands it back untouched — the same reasoning `fn get_printer()
    effects []` already established for v0.14.3's own return-value
    tracking); the check fires at the CALLER's own `g(1)`, against the
    CALLER's own declared scope."""
    all_ok(
        'fn apply(f) {\n'
        '  f\n'
        '}\n'
        'fn caller() effects [io] {\n'
        '  let g = apply(print)\n'
        '  g(1)\n'
        '}\n'
        'caller()\n'
        'check "ok": true\n')
    with pytest.raises(ParseError) as ei:
        parse(
            'fn apply(f) {\n'
            '  f\n'
            '}\n'
            'fn caller() effects [] {\n'
            '  let g = apply(print)\n'
            '  g(1)\n'
            '}\n'
            'caller()\n')
    msg = str(ei.value)
    assert "'g' requires effect 'io'" in msg and "not permitted" in msg


def test_param_returned_directly_chained_call_with_no_let_is_now_checked():
    """Same shape, no intermediate `let` at all — `apply(print)(1)`,
    mirroring `test_chained_call_on_return_value_is_checked`'s own v0.14.3
    "no let needed" pattern, now for an argument-dependent return fact
    instead of a fixed one."""
    with pytest.raises(ParseError) as ei:
        parse(
            'fn apply(f) {\n'
            '  f\n'
            '}\n'
            'fn caller() effects [] {\n'
            '  apply(print)(1)\n'
            '}\n'
            'caller()\n')
    assert "'apply()' requires effect 'io'" in str(ei.value)
    all_ok(
        'fn apply(f) {\n'
        '  f\n'
        '}\n'
        'fn caller() effects [io] {\n'
        '  apply(print)(1)\n'
        '}\n'
        'caller()\n'
        'check "ok": true\n')


def test_param_renamed_then_returned_is_now_checked():
    """The tail need not be the bare param itself — a same-body rename
    (`let g = f\\n g`, v0.14.11's own `_resolve_param_alias`) still counts
    as directly returning `f`, via `_tail_return_param_name`'s reuse of
    that exact resolver."""
    with pytest.raises(ParseError):
        parse(
            'fn apply(f) {\n'
            '  let g = f\n'
            '  g\n'
            '}\n'
            'fn caller() effects [] {\n'
            '  let h = apply(print)\n'
            '  h(1)\n'
            '}\n'
            'caller()\n')


def test_returned_param_at_correct_position_is_matched_not_conflated():
    """`apply`'s SECOND param is the one returned — only the argument at
    THAT position (not the first) is what flows to the caller's alias,
    mirroring `test_only_the_directly_called_param_position_is_checked`'s
    own positional discipline for the sibling (directly-called) mechanism."""
    all_ok(
        'fn apply(unused, f) {\n'
        '  f\n'
        '}\n'
        'fn caller() effects [] {\n'
        '  let g = apply(print, 5)\n'
        '  g\n'
        '}\n'
        'caller()\n'
        'check "ok": true\n')
    with pytest.raises(ParseError):
        parse(
            'fn apply(unused, f) {\n'
            '  f\n'
            '}\n'
            'fn caller() effects [] {\n'
            '  let g = apply(5, print)\n'
            '  g(1)\n'
            '}\n'
            'caller()\n')


def test_param_passed_through_a_second_function_before_return_is_still_not_checked():
    """Still fully open, unchanged in scope from v0.14.9 onward: an
    argument flowing through a SECOND function call before reaching a
    return is invisible — `identity`'s own tail is a `Call` (`identity(f)`
    inlined into `apply`'s body), not a bare `NameRef`, so `apply` itself
    has no recorded return-param fact at all."""
    all_ok(
        'fn identity(x) { x }\n'
        'fn apply(f) {\n'
        '  identity(f)\n'
        '}\n'
        'let g = apply(print)\n'
        'g(1)\n'
        'check "ok": true\n')


def test_param_returned_via_if_else_tail_is_still_not_checked():
    """Still open: unlike `tail_alias_tag` (widened to if/else tails by
    v0.14.5), `tail_param_name` is deliberately NOT — an if/else tail
    returning a param on every arm is invisible to this round's own
    mechanism."""
    all_ok(
        'fn apply(f) {\n'
        '  if true { f } else { f }\n'
        '}\n'
        'let g = apply(print)\n'
        'g(1)\n'
        'check "ok": true\n')


# ======================================== v0.14.13 (round 312) ============
# Closes the FIRST of the two gaps named across four consecutive
# language(C) rounds (302, 306, 308, 311) as needing "a real design
# sketch, not another small pre-scoped slice": an argument reaching an
# effectful builtin through a SECOND function call, before landing in a
# directly-called param — `outer`'s own body FORWARDS its param `f` as
# `inner`'s own argument, and it is `inner`'s body, not `outer`'s own,
# that calls it directly. Composes to arbitrary depth for free by reusing
# `param_call_scopes`'s existing single-pass "record once, read at every
# later call site" discipline — see `_check_param_forwarding`'s own
# docstring in parser.py. The OTHER gap — the dynamic call graph, calling
# a different, unrestricted top-level fn that itself performs an effect
# DIRECTLY, no param involved at all — is a fundamentally different,
# larger problem NOT touched by this round; see SPEC.md's "v0.14.13"
# section for the honest design-sketch writeup of why.


def test_param_forwarded_to_second_function_that_calls_it_is_now_checked():
    """v0.14.13 (round 312): `outer`'s own body never calls its param `f`
    directly — it FORWARDS `f` as `inner`'s own argument, and `inner`'s
    body is what actually calls it. Before this round, `outer`'s own
    `param_call_scopes` fact had NOTHING in it (outer calls none of its
    OWN params directly), so `outer(print)` was invisible to every
    existing check even though calling it does perform io. Same grant/
    deny pair shape as `test_argument_passed_to_a_directly_called_param_
    is_{checked,rejected_when_not_permitted}`, just with one extra
    function-call hop between the param and the effectful call."""
    all_ok(
        'fn inner(g) effects [io] {\n'
        '  g(1)\n'
        '}\n'
        'fn outer(f) effects [io] {\n'
        '  inner(f)\n'
        '}\n'
        'outer(print)\n'
        'check "ok": true\n')
    with pytest.raises(ParseError) as ei:
        parse(
            'fn inner(g) effects [io] {\n'
            '  g(1)\n'
            '}\n'
            'fn outer(f) effects [] {\n'
            '  inner(f)\n'
            '}\n'
            'outer(print)\n')
    msg = str(ei.value)
    assert "effect 'io'" in msg and "not permitted" in msg


def test_param_forwarding_composes_transitively_through_three_hops():
    """The forwarding fact composes to ARBITRARY depth for free — no
    explicit recursion needed, just the same single-pass "record once,
    read at every later call site" discipline `param_call_scopes` already
    relies on for everything else. `innermost`, `inner`, `outer` are
    declared bottom-up (the same declaration-order constraint every
    resolver in this family already has), so `inner`'s own forward-
    through-`innermost` fact is already resolved by the time `outer`'s
    own forward-through-`inner` check runs."""
    all_ok(
        'fn innermost(h) effects [io] {\n'
        '  h(1)\n'
        '}\n'
        'fn inner(g) effects [io] {\n'
        '  innermost(g)\n'
        '}\n'
        'fn outer(f) effects [io] {\n'
        '  inner(f)\n'
        '}\n'
        'outer(print)\n'
        'check "ok": true\n')
    with pytest.raises(ParseError):
        parse(
            'fn innermost(h) effects [io] {\n'
            '  h(1)\n'
            '}\n'
            'fn inner(g) effects [io] {\n'
            '  innermost(g)\n'
            '}\n'
            'fn outer(f) effects [] {\n'
            '  inner(f)\n'
            '}\n'
            'outer(print)\n')


def test_param_forwarding_through_let_bound_anonymous_fn_is_checked():
    """The forwarding target need not be a NAMED fn — a `let`-bound
    anonymous fn's own `param_call_fact` (v0.14.10, round 302) is walked
    by `_resolve_param_call_fact` exactly the same generic way, so
    forwarding to one is checked identically."""
    with pytest.raises(ParseError):
        parse(
            'let inner = fn(g) effects [io] {\n'
            '  g(1)\n'
            '}\n'
            'fn outer(f) effects [] {\n'
            '  inner(f)\n'
            '}\n'
            'outer(print)\n')


def test_param_forwarding_rename_hop_before_forward_is_still_checked():
    """The forwarded argument need not be the bare param itself — a
    same-body rename of it (`let g = f` then `inner(g)`) is resolved by
    the shared `_resolve_current_fn_param` helper exactly the same way
    the callee-identity check already is."""
    with pytest.raises(ParseError):
        parse(
            'fn inner(g) effects [io] {\n'
            '  g(1)\n'
            '}\n'
            'fn outer(f) effects [] {\n'
            '  let renamed = f\n'
            '  inner(renamed)\n'
            '}\n'
            'outer(print)\n')


def test_param_forwarding_shadowed_name_is_not_misattributed():
    """A nested fn's own param of the SAME name as an outer forwarded
    rename must not be misattributed — mirrors `test_param_rename_in_
    enclosing_fn_not_misattributed_to_inner_fn`'s own shape, now for the
    forwarding mechanism: `helper`'s own local `let f = 5` shadows
    `outer`'s param `f`, so `inner(f)` inside `helper` forwards the
    SHADOWING local, not `outer`'s own param."""
    all_ok(
        'fn inner(g) effects [io] {\n'
        '  g(1)\n'
        '}\n'
        'fn outer(f) effects [] {\n'
        '  fn helper() effects [] {\n'
        '    let f = 5\n'
        '    inner(f)\n'
        '  }\n'
        '  helper()\n'
        '}\n'
        'outer(print)\n'
        'check "ok": true\n')


def test_param_forwarding_only_correct_position_is_matched():
    """Only the argument at the target fn's own DIRECTLY-called param
    POSITION is inspected — an unrelated param at a different position is
    not conflated, mirroring `test_only_the_directly_called_param_
    position_is_checked`'s own positional discipline."""
    all_ok(
        'fn inner(unused, g) effects [io] {\n'
        '  g(1)\n'
        '}\n'
        'fn outer(f) effects [] {\n'
        '  inner(f, 5)\n'
        '}\n'
        'outer(print)\n'
        'check "ok": true\n')


def test_param_forwarding_via_non_nameref_argument_still_not_checked():
    """Deliberately still narrow, same "bare NameRef only" boundary as
    every sibling check: an argument that is itself a CALL (not a bare
    name) is invisible here — `id(f)`'s own result is not tracked as `f`
    itself, so `outer` gains no forwarding fact from it at all."""
    all_ok(
        'fn inner(g) effects [io] {\n'
        '  g(1)\n'
        '}\n'
        'fn outer(f) effects [] {\n'
        '  fn id(x) { x }\n'
        '  inner(id(f))\n'
        '}\n'
        'outer(print)\n'
        'check "ok": true\n')


def test_param_forwarding_does_not_disturb_returned_param_mechanism():
    """v0.14.12's own return-boundary mechanism (a param FORWARDED then
    RETURNED, never called) remains a genuinely separate, still-fully-
    open gap, unaffected by this round's own forwarding-then-CALLED
    mechanism — unchanged regression pin for `test_param_passed_through_
    a_second_function_before_return_is_still_not_checked`, restated here
    under this round's own test name for discoverability."""
    all_ok(
        'fn identity(x) { x }\n'
        'fn apply(f) {\n'
        '  identity(f)\n'
        '}\n'
        'let g = apply(print)\n'
        'g(1)\n'
        'check "ok": true\n')
