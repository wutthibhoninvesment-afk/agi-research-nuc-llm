"""v0.14 (round 146): `effects [...]` — a minimal, parse-time effect system.

Design (see SPEC.md "v0.14"): unlike `: Type`/`-> Type` (v0.12/v0.13, both
runtime checks against a runtime VALUE), whether a function's own body
directly names an effectful builtin is a static property of the SOURCE
TEXT — so this is checked entirely at parse time, with no new AST node, no
Closure field, and no interpreter change at all. `effects [io, ...]` is an
optional clause after a parameter list, before an optional `-> Type`
(fixed order): `fn f(params) effects [tags] -> Type { body }`.

- No clause at all == unrestricted (the default; every program written
  before this feature existed parses identically — see
  `test_undeclared_fn_may_still_print`).
- `effects []` declares "this function's own body may not directly call
  an effectful builtin" (today, only `print`, tagged `"io"`
  in `parser._EFFECTFUL_BUILTINS`) — violating it is a ParseError, not a
  runtime `miss`, because it can be decided without running anything.
- `effects [io]` (or any set containing the required tag) explicitly
  grants it.

Deliberately SHALLOW by design, not oversight (mirrors the `-> Type`
precedent of checking one settle point, not full composition): the
declaration only vouches for the function's OWN textual body.
  - A nested `fn` defined inside a restricted body is a separate closure
    with its own (absent, hence unrestricted) declaration — it can print
    freely even though it is lexically inside an `effects []` function
    (`test_nested_undeclared_fn_escapes_outer_purity`).
  - Passing a builtin as a value (`let p = print`) and calling THAT is
    invisible to the check, since only a literal `name(...)` callee is
    inspected (`test_indirect_call_via_variable_is_not_checked`).
Both gaps are honest, tested limitations, not bugs — a call-graph-aware
effect system is future work (see research-state.md's language backlog).
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


def test_nested_fn_without_own_clause_also_escapes():
    """Even an inner fn with NO effects clause of its own (unrestricted by
    default) may print inside an outer `effects []` body — the outer
    declaration only ever checks calls made directly in ITS OWN body."""
    all_ok(
        'fn outer() effects [] {\n'
        '  fn inner() { print(1) }\n'
        '  inner()\n'
        '}\n'
        'check "ok": outer() == 1\n')


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
