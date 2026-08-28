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
"""

import os
import sys

import pytest

from whence.parser import parse, ParseError

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
