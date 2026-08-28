"""v0.14 (round 146) / v0.14.1 (round 264): `effects [...]` — a minimal,
parse-time effect system.

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

Still deliberately SHALLOW by design, not oversight (mirrors the `-> Type`
precedent of checking one settle point, not full call-graph composition):
the declaration only vouches for the function's OWN textual body, resolved
lexically, not through arbitrary calls.
  - Passing a builtin as a value (`let p = print`) and calling THAT is
    invisible to the check, since only a literal `name(...)` callee is
    inspected (`test_indirect_call_via_variable_is_not_checked`) — this
    needs value-flow analysis, not lexical scoping, and stays open.
  - Calling a DIFFERENT, unrestricted top-level function that itself
    performs the effect is still untouched by the caller's own
    declaration — only LEXICAL nesting is tracked, not the dynamic call
    graph (`test_effects_empty_still_allows_non_print_calls` calls a
    genuinely pure `double`, but the same shape would allow calling an
    impure sibling too; not separately pinned since it follows directly
    from "declaration only vouches for the function's own textual body").
Both remaining gaps are honest, tested limitations, not bugs — a full
call-graph-aware effect system is future work (see research-state.md's
language backlog).
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


def test_indirect_call_via_variable_is_not_checked():
    """`let p = print` then `p(1)`: the callee at the call site is the
    NameRef `p`, not `print`, so the effect table lookup misses and the
    call is allowed even inside `effects []` — a real, documented gap in
    this shallow design, not a bug."""
    all_ok(
        'fn f() effects [] {\n'
        '  let p = print\n'
        '  p(1)\n'
        '}\n'
        'check "ok": f() == 1\n')


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
