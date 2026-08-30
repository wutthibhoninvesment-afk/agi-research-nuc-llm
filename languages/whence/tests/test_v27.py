"""Whence v0.27 (round 368, language C) — a value's SIZE is a budget.

SPEC's "Limits that are errors, not crashes" got its entry for runaway TAIL
loops in v0.26 (round 366), which closed the last thing in that list that was
a hang. This file is about the axis that list never had: `max_depth` bounds
how DEEP a program goes, `max_iter` bounds how MANY TIMES it goes round, and
nothing bounded how BIG one value gets.

Five host exceptions were reachable from ordinary Whence source, all of them
tracebacks with exit code **1** — which is the "some check failed" code, so a
caller could not tell a program whose checks failed from one that killed the
interpreter (the third instance of the class round 350 found in `run.py`'s
LexError handling):

  1. `values._show` -> `repr(int)`: CPython caps `int.__str__` at 4300
     digits. So `print(x)`, EVERY `mk_miss` message that names its operands,
     a failing `check`'s report, and `why` all raised `ValueError` on an
     integer the language itself lets you build. In a language whose rule 2
     is "no exceptions" and whose one idea is that a failure can explain
     itself, the explanation crashed.
  2. `b_range` -> `str(i)` for each element's detail. `range(big, big + 2)`
     is a TWO-element range and it crashed: no memory pressure at all.
  3. `b_range` -> `"%d..%d" % (lo, hi)`, same cause, one line later.
  4. `b_num` -> `int(t)`, which has the same 4300-digit host limit.
  5. `_index` -> `"index %d out of range"`, i.e. `xs[big]`.

And two hangs, neither an error nor a crash:

  6. `s + s` in a tail loop: a raw `MemoryError` traceback (or the OOM
     killer, depending on which arrives first).
  7. `x * x` in a tail loop: no return in 60 s, because CPython's bigint
     multiply is Karatsuba and just grinds.
  8. `range(100000000000)`: no return in 20 s, then the OOM killer.

None of 1-5 needs a big machine or a long run; `sq(15, 3)` is five lines and
2 KB. What follows is (a) a SWEEP that drives one such integer through every
builtin in the registry in every argument position and through every
operator, asserting only that no host exception escapes — the test that
would have caught all five at once — and (b) the two budgets, `max_value`
(bytes: strings, lists, ranges, joins) and `max_int_bits` (bits: `*` and
`num`), which are two numbers and not one for a measured reason recorded in
`Interpreter.DEFAULT_MAX_INT_BITS`.
"""

import os
import subprocess
import sys

import pytest

from whence import interp as I
from whence.interp import Interpreter
from whence.lexer import LexError
from whence.parser import ParseError
from whence.values import (SHOW_INT_BITS, SHOW_INT_DIGITS, Miss, WList,
                           full_show, show_int, show_payload)

import run as cli

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 3 ** 32768 — 51937 bits, ~15600 decimal digits, built in 0.04 s and 2 KB.
# Over every rendering and round-trip boundary in the language and far UNDER
# both budgets, which is the point: these are crashes on a value the shipped
# defaults happily allow.
BIG = """fn sq(n, x) { if n <= 0 { x } else { sq(n - 1, x * x) } }
let big = sq(15, 3)
"""


def run(src, **kw):
    interp = Interpreter(out=lambda *a: None, **kw)
    return interp, interp.run(src)


def payload(src, name="result", **kw):
    _, env = run(src, **kw)
    v = env.get(name)
    return None if v is None else v.payload


def reason(p):
    assert isinstance(p, Miss), "expected a miss, got %r" % (p,)
    return "; ".join(p.reasons)


# ==========================================================================
# 1. the sweep: no host exception, anywhere, from a value the language allows
# ==========================================================================
# This is the oracle the five crash sites needed and never had. It asserts
# almost nothing about MEANING — only that evaluating the program, rendering
# every result, and reporting every check completes without a host exception.
# That is deliberate: each of the five was a `ValueError` or `MemoryError`
# raised while BUILDING A MESSAGE, so any test that checked wording would
# have had to already know which call sites to look at, and the whole problem
# was that nobody did.

def _exercise(src):
    """Run `src`, then force every rendering path over `result`: `full_show`
    (what `print` uses), `show_payload` (what every miss message uses), the
    why-tree, and `report_checks` (the failing-check report, which lives in
    run.py and is not otherwise reachable from an in-process test)."""
    interp = Interpreter(out=lambda *a: None)
    env = interp.run(src)
    v = env.get("result")
    if v is not None:
        full_show(v.payload)
        show_payload(v.payload)
        show_payload(v.payload, None)
        v.show                       # the lazy snapshot on the Prov node
    cli.report_checks(interp.checks, out=lambda *a: None)
    return interp


def _builtin_arities():
    """name -> (min_args, max_args), read off the LIVE registry rather than a
    list in this file, so a builtin added later is swept automatically."""
    from whence.values import Builtin
    out = {}
    for name, v in Interpreter(out=lambda *a: None).globals.vars.items():
        b = v.payload
        if isinstance(b, Builtin):
            a = b.arity
            out[name] = a if isinstance(a, tuple) else (a, a)
    return out


ARITIES = _builtin_arities()
ALL_BUILTINS = sorted(ARITIES)


def _sig_positions(name):
    """Every (arity, position) pair a builtin can be called with."""
    lo, hi = ARITIES[name]
    return [(n, k) for n in range(lo, hi + 1) for k in range(n)]


def test_the_registry_is_not_empty_and_the_sweep_covers_all_of_it():
    # If this file's sweep silently stopped enumerating, every test below it
    # would still pass. Round 365's lesson: a negative claim about coverage
    # has to be pinned positively.
    assert len(ALL_BUILTINS) >= 36
    assert "range" in ALL_BUILTINS and "num" in ALL_BUILTINS
    # every registered builtin also declares a signature (v0.22)
    assert set(ALL_BUILTINS) == set(I._BUILTIN_SIGS)


@pytest.mark.parametrize("name", ALL_BUILTINS)
def test_no_builtin_raises_a_host_exception_on_a_huge_integer(name):
    """Every builtin, every arity in its range, every argument position."""
    for arity, pos in _sig_positions(name):
        args = ["1"] * arity
        args[pos] = "big"
        src = BIG + "let result = %s(%s)\n" % (name, ", ".join(args))
        try:
            _exercise(src)
        except (LexError, ParseError):
            raise
        except Exception as e:                        # noqa: BLE001
            raise AssertionError(
                "%s(%s) raised %s: %s" %
                (name, ", ".join(args), type(e).__name__, e)) from e


BINARY_OPS = ["+", "-", "*", "/", "%", "==", "!=", "<", "<=", ">", ">="]
OTHER_SIDES = ["1", '"s"', "[1]", "@{a: 1}", "true", "1.5", "big"]


@pytest.mark.parametrize("op", BINARY_OPS)
def test_no_binary_operator_raises_a_host_exception_on_a_huge_integer(op):
    for other in OTHER_SIDES:
        for src in (BIG + "let result = big %s %s\n" % (op, other),
                    BIG + "let result = %s %s big\n" % (other, op)):
            try:
                _exercise(src)
            except Exception as e:                    # noqa: BLE001
                raise AssertionError("%r raised %s: %s" %
                                     (src, type(e).__name__, e)) from e


@pytest.mark.parametrize("src", [
    "let result = -big",
    "let result = not big",
    "let result = [1, 2, 3][big]",
    'let result = "abc"[big]',
    "let result = big[0]",
    "let result = big.field",
    "let result = why big",
    "let result = snip big",
    'let result = note("n", big)',
    "let result = big rescue 0",
    "let xs = [big, big]\nlet result = xs[1]",
    "let result = @{a: big}",
    'let result = str(@{a: big})',
    "let result = str([big])",
    "let result = big()",
    "fn f(n) { n }\nlet result = f(big)",
    'let result = typed(big, "text", "label")',
    'check "fails on purpose": big == 0\nlet result = 1',
    'check "passes": big == big\nlet result = 1',
])
def test_no_other_construct_raises_a_host_exception_on_a_huge_integer(src):
    try:
        _exercise(BIG + src + "\n")
    except Exception as e:                            # noqa: BLE001
        raise AssertionError("%r raised %s: %s" %
                             (src, type(e).__name__, e)) from e


# ==========================================================================
# 2. the five crash sites, one named regression each
# ==========================================================================

def test_print_of_a_huge_integer_is_a_summary_not_a_valueerror():
    interp, env = run(BIG + "print(big)\n")
    assert interp.out_lines == []            # out= swallowed it; check direct
    assert full_show(env.get("big").payload) == "<integer, 51937 bits>"


def test_a_miss_about_a_huge_integer_can_state_its_own_reason():
    # `big + "x"` builds "cannot add %s and %s" out of BOTH operands. Before
    # v0.27 the miss could not be constructed at all.
    p = payload(BIG + 'let result = big + "x"\n')
    assert "cannot add <integer, 51937 bits>" in reason(p)


def test_a_failing_check_on_a_huge_integer_reports_instead_of_crashing():
    interp = Interpreter(out=lambda *a: None)
    interp.run(BIG + 'check "big is small": big < 10\n')
    lines = []
    failed = cli.report_checks(interp.checks, out=lines.append)
    assert failed == 1
    assert any("big is small" in ln for ln in lines)


def test_range_with_huge_bounds_and_a_tiny_count_does_not_crash():
    # TWO elements. The crash was in the per-element decimal detail, so the
    # size of the RESULT was never the problem.
    p = payload(BIG + "let result = range(big, big + 2)\n")
    assert isinstance(p, WList) and len(p) == 2
    assert p[0].detail == "<integer, 51937 bits>"


def test_num_of_a_long_digit_string_is_a_miss_not_a_valueerror():
    src = ('fn dbl(n, s) { if n <= 0 { s } else { dbl(n - 1, s + s) } }\n'
           'let digits = dbl(13, "1234")\n'
           'let result = num(digits)\n')
    assert "32768 digits is over the 4000-digit limit" in reason(payload(src))


def test_a_size_miss_about_a_huge_count_can_state_its_own_count():
    # v0.27's own new code had the same defect it was written to fix:
    # `_size_miss` formatted the element count with `%d`, and
    # `range(1, big)`'s count is a 51937-bit integer. Section 1's sweep found
    # it on the first run.
    p = payload(BIG + "let result = range(1, big)\n")
    assert "range too large: <integer, 51937 bits> elements" in reason(p)


def test_indexing_with_a_huge_integer_is_a_miss_not_a_valueerror():
    p = payload(BIG + "let result = [1, 2, 3][big]\n")
    assert "index <integer, 51937 bits> out of range (len 3)" in reason(p)


# ==========================================================================
# 3. rendering: integers were the one payload kind with no cap
# ==========================================================================

def test_every_other_payload_kind_already_had_a_cap_and_int_did_not():
    # The shape of the gap, stated as a test so it cannot be re-introduced:
    # strings are cut by `_quote`, containers by SHOW_NEST, and integers by
    # nothing at all until v0.27.
    from whence.values import wlist
    assert show_payload("x" * 500).endswith('…"')
    assert show_payload(wlist([])) == "[]"
    assert show_int(2 ** SHOW_INT_BITS) == "<integer, %d bits>" % (
        SHOW_INT_BITS + 1)


# NOTE: parametrize on the EXPONENT, never on the integer. pytest builds a
# test id with `str(val)`, so a 13286-bit parameter makes pytest itself raise
# the ValueError this file is about, during COLLECTION -- a sixth instance of
# the same class, in the test runner. Found the hard way writing this file.
@pytest.mark.parametrize("bits,sign", [(0, 1), (1, 1), (1, -1), (332, 1),
                                       (13286, 1), (13286, -1)])
def test_integers_up_to_the_boundary_still_render_as_digits(bits, sign):
    n = sign * ((1 << bits) if bits else 0)
    assert show_int(n) == repr(n)


@pytest.mark.parametrize("bits,sign", [(SHOW_INT_BITS, 1),
                                       (SHOW_INT_BITS, -1), (51936, 1)])
def test_integers_past_the_boundary_render_as_a_summary(bits, sign):
    n = sign * (1 << bits)
    assert show_int(n) == "<integer, %d bits>" % n.bit_length()


def test_the_boundary_stays_under_the_host_conversion_limit():
    # SHOW_INT_BITS exists to keep Whence's cap strictly BELOW CPython's, so
    # the host limit is never the thing a user meets. If CPython's default
    # ever drops, this is the test that says so.
    assert len(str(2 ** SHOW_INT_BITS - 1)) <= SHOW_INT_DIGITS
    assert SHOW_INT_DIGITS < sys.get_int_max_str_digits()


def test_bool_still_renders_as_true_false_not_as_an_integer():
    # `bool` is a subclass of `int`; splitting the int branch out of the
    # `(int, float)` test is where that could have broken.
    assert show_payload(True) == "true" and show_payload(False) == "false"


def test_num_and_str_are_inverses_at_the_same_boundary():
    # The reason `num`'s digit limit is SHOW_INT_DIGITS and not
    # `max_int_bits`: accepting more digits than `str` can print back would
    # mint a value the language cannot write out.
    ok = "9" * SHOW_INT_DIGITS
    assert payload('let result = num("%s")' % ok) == int(ok)
    p = payload('let result = num("%s")' % ("9" * (SHOW_INT_DIGITS + 1)))
    assert "over the %d-digit limit" % SHOW_INT_DIGITS in reason(p)


# ==========================================================================
# 4. the six growth sites
# ==========================================================================
# A growth site is a place where a value can come out BIGGER than the sum of
# its inputs' sizes. There are exactly six, and every one of them is
# multiplicative or number-driven — which is why `max_iter` cannot bound
# them: a doubling loop crosses any budget in log2(budget) < 60 steps, and
# `range` crosses it in ONE.

# Both comfortably above `MIN_MAX_INT_BITS`, so the floor is not what
# these tests are measuring.
SMALL = {"max_value": 4096, "max_int_bits": 1024}

# Each program below is sized to the SMALL budget, not to the machine: it
# must miss under `SMALL` and succeed with the budget off. The real runaway
# shapes -- the ones that used to hang -- are section 4b, run against the
# SHIPPED defaults, which is where "it terminates at all" is the claim.
GROWTH_SITES = {
    "str_concat": ('fn go(n, s) { if n <= 0 { s } else { go(n - 1, s + s) } }\n'
                   'let result = go(13, "ab")\n', "string too large"),
    "list_concat": ('fn go(n, xs) { if n <= 0 { xs } else '
                    '{ go(n - 1, xs + xs) } }\n'
                    'let result = go(13, [1, 2])\n', "list too large"),
    "push": ('fn go(n, xs) { if n <= 0 { xs } else '
             '{ go(n - 1, push(xs, n)) } }\n'
             'let result = go(1000, [])\n', "list too large"),
    "range": ('let result = range(100)\n', "range too large"),
    # A list of 20 SHARED pointers to one 1280-character string weighs 160
    # bytes; joining it materialises 25600. Nothing but the sum of the parts
    # can see that, which is why `join` needs a guard of its own.
    "join": ('fn dbl(n, s) { if n <= 0 { s } else { dbl(n - 1, s + s) } }\n'
             'let s = dbl(7, "0123456789")\n'
             'let result = join(map(fn(i) { s }, range(20)), "")\n',
             "string too large"),
    "int_mul": ('fn go(n, x) { if n <= 0 { x } else { go(n - 1, x * x) } }\n'
                'let result = go(10, 3)\n', "integer too large"),
}


@pytest.mark.parametrize("site", sorted(GROWTH_SITES))
def test_every_growth_site_answers_the_budget(site):
    src, wording = GROWTH_SITES[site]
    assert wording in reason(payload(src, **SMALL))


@pytest.mark.parametrize("site", sorted(GROWTH_SITES))
def test_every_growth_site_is_unbounded_when_its_own_budget_is_off(site):
    """Turning the site's OWN budget off must let the same program through --
    which also proves the two budgets are not aliases of each other."""
    src, wording = GROWTH_SITES[site]
    owner = "max_int_bits" if "integer" in wording else "max_value"
    other = "max_value" if owner == "max_int_bits" else "max_int_bits"
    kw = dict(SMALL)
    kw[owner] = None
    assert not isinstance(payload(src, **kw), Miss), (site, "own budget off")
    kw = dict(SMALL)
    kw[other] = None
    assert wording in reason(payload(src, **kw)), (site, "other budget off")


# --------------------------------------------------------------------------
# 4b. the three shapes that used to hang, against the SHIPPED defaults
# --------------------------------------------------------------------------
# These are the point of v0.27. Each one is 2-3 lines of Whence, each one had
# no upper bound at all before it, and the assertion is that they now FINISH.
# Wall-clock and RSS figures from `bench/value_size.py --runaway`.

def test_a_runaway_string_doubling_finishes_as_a_miss():
    # was: a raw MemoryError traceback out of `f_add`, exit 1.
    # now: 0.54 s, ~540 MB peak RSS, one miss.
    src = ('fn go(n, s) { if n <= 0 { s } else { go(n - 1, s + s) } }\n'
           'let result = go(60, "ab")\n')
    assert "string too large" in reason(payload(src))


def test_a_runaway_integer_squaring_finishes_as_a_miss():
    # was: no return in 60 s (CPython bigint multiply grinding).
    # now: 0.76 s, 17 MB.
    src = ('fn go(n, x) { if n <= 0 { x } else { go(n - 1, x * x) } }\n'
           'let result = go(60, 3)\n')
    assert "integer too large" in reason(payload(src))


def test_a_runaway_range_finishes_as_a_miss():
    # was: no return in 20 s, then the OOM killer. now: 0.04 s.
    assert "range too large: 100000000000 elements" in reason(
        payload("let result = range(100000000000)\n"))


def test_the_two_budgets_are_independent():
    mul = GROWTH_SITES["int_mul"][0]
    cat = GROWTH_SITES["str_concat"][0]
    # max_value off, max_int_bits on: the integer still misses.
    assert "integer too large" in reason(
        payload(mul, max_value=None, max_int_bits=1024))
    # max_int_bits off, max_value on: the string still misses.
    assert "string too large" in reason(
        payload(cat, max_value=4096, max_int_bits=None))


def test_every_size_miss_names_the_flag_that_raises_it():
    # v0.22's rule: an error that can name the fix, names it.
    for site, (src, _) in sorted(GROWTH_SITES.items()):
        r = reason(payload(src, **SMALL))
        flag = "--max-int-bits" if "integer too large" in r else "--max-value"
        assert flag in r and "0 for unbounded" in r, (site, r)


def test_addition_grows_an_integer_by_one_bit_and_is_guarded_anyway():
    """`x + x` doubles, so `+`/`-` DO grow an integer -- by one bit a step.
    `max_iter` already bounds that (1e6 iterations buys 1e6 bits, and
    DEFAULT_MAX_ITER < DEFAULT_MAX_INT_BITS, asserted below), so at the
    shipped defaults addition can never cross the ceiling. v0.27 guards it
    anyway: "can never" there is a relationship between two numbers a caller
    may change, and an invariant that holds only at the defaults is not an
    invariant. Both operators, both directions."""
    assert Interpreter.DEFAULT_MAX_ITER < Interpreter.DEFAULT_MAX_INT_BITS
    for expr in ("x + x", "x - (0 - x)"):     # both double, one per operator
        src = ('fn go(n, x) { if n <= 0 { x } else { go(n - 1, %s) } }\n'
               'let result = go(2000, 3)\n') % expr
        assert "integer too large" in reason(
            payload(src, max_int_bits=1024)), expr
        assert not isinstance(payload(src, max_int_bits=None), Miss), expr


def test_a_growth_site_crosses_any_budget_in_under_60_iterations():
    # The structural claim: growth is multiplicative, so the iterations
    # needed are log2(budget) — never enough for `max_iter` to see. Measured
    # against a SMALL budget and then extended to the shipped one by
    # arithmetic; running the real 500 MB doubling 28 times over would copy
    # about a gigabyte to learn a number log2 already knows.
    src = ('fn go(n, s) { if n <= 0 { s } else { go(n - 1, s + s) } }\n'
           'let result = go(%d, "ab")\n')
    first_miss = None
    for n in range(1, 24):
        if isinstance(payload(src % n, max_value=1000000), Miss):
            first_miss = n
            break
    assert first_miss == 19, first_miss          # 2**19 * 2 = 1048576 > 1e6
    # the same loop against the shipped default misses 9 doublings later, and
    # `max_iter` is 1e6: five orders of magnitude of ceiling it never reaches.
    default_doublings = Interpreter.DEFAULT_MAX_VALUE.bit_length()
    assert default_doublings < 60
    assert Interpreter.DEFAULT_MAX_ITER > 1000 * default_doublings


# ==========================================================================
# 5. the two numbers, and the contracts that sized them
# ==========================================================================

def test_range_of_max_iter_elements_fits_the_default_value_budget():
    # THE constraint that sized DEFAULT_MAX_VALUE, pinned as arithmetic so it
    # costs nothing to check: Whence has no `while`, so the two ways to say
    # "do this a million times" are a tail loop (allowed, exactly
    # DEFAULT_MAX_ITER) and `map(f, range(1000000))`. Permitting one and
    # refusing the other would be incoherent.
    floor = Interpreter.DEFAULT_MAX_ITER * I._RANGE_BYTES_PER_ELEM
    assert Interpreter.DEFAULT_MAX_VALUE >= floor
    # ... and the margin `skills/measured-budget-sizing` asks for.
    assert Interpreter.DEFAULT_MAX_VALUE >= floor * 3


def test_the_int_budget_is_sized_from_time_not_from_the_byte_budget():
    # If a future round "simplifies" the two budgets into one, this is the
    # test that says why it cannot: the byte budget would license integers
    # ~500x bigger than the time budget allows, and CPython's multiply is
    # superlinear, so that last multiply is the hang v0.27 removed.
    as_bytes = Interpreter.DEFAULT_MAX_VALUE * I._INT_BITS_PER_BYTE
    assert as_bytes > Interpreter.DEFAULT_MAX_INT_BITS * 100


def test_the_defaults_are_reachable_from_the_library_and_the_cli():
    i = Interpreter()
    assert i.max_value == Interpreter.DEFAULT_MAX_VALUE
    assert i.max_int_bits == Interpreter.DEFAULT_MAX_INT_BITS


def test_peak_counters_report_what_the_budgets_bound():
    # Round 366's rule: a budget whose consumption is not reported can only
    # be argued about. `peak_value` is `peak_tail` for size.
    interp, _ = run('let result = range(100)\n')
    assert interp.peak_value == 100 * I._RANGE_BYTES_PER_ELEM
    interp, _ = run(BIG)
    assert interp.peak_int_bits >= 51937
    interp, _ = run('let result = 1 + 1\n')
    assert interp.peak_value == 0 and interp.peak_int_bits == 0


def test_peak_value_records_a_refused_value_too():
    # Sizing a budget needs the number the program ASKED for, not the number
    # it was allowed. Round 366 could not size DEFAULT_MAX_ITER until
    # `peak_tail` existed; the same applies here.
    interp = Interpreter(out=lambda *a: None, max_value=1000)
    interp.run("let result = range(1000000)\n")
    assert interp.peak_value == 1000000 * I._RANGE_BYTES_PER_ELEM


def test_the_mul_fast_cut_is_a_module_constant_with_a_matching_floor():
    # v0.27's drafts derived this threshold per Interpreter twice and it was
    # wrong twice: from `max_value` it is a 250 MB integer built by every
    # `Interpreter()` constructor, and read from the live interpreter it
    # costs an Env walk on the numeric hot path. A constant costs neither,
    # and `MIN_MAX_INT_BITS` is the price: the floor must be exactly the
    # product the constant admits, or `fast=True` and `fast=False` disagree.
    assert I.MIN_MAX_INT_BITS == 2 * I._MUL_FAST_CUT.bit_length() - 2
    assert Interpreter(max_int_bits=1).max_int_bits == I.MIN_MAX_INT_BITS
    assert Interpreter(max_int_bits=None).max_int_bits is None


def test_a_compiled_closure_uses_the_interpreter_that_is_RUNNING():
    # The v0.7 shared-AST determinism rule. `binop` was effectively pure
    # until v0.27 gave it the budgets and the peak counters, so a captured
    # bound method would charge one interpreter for another's run. Compile
    # the AST under a generous budget, then run the SAME AST under a tiny
    # one: the second run must miss.
    from whence.interp import Env
    from whence.parser import parse

    # ONE AST, compiled by the first interpreter (its `.fast`/`.direct`
    # closures are cached on the nodes), then executed by a second one with a
    # tighter budget. `Interpreter.run` re-parses, so the sharing has to be
    # built by hand -- which is exactly why nothing had caught this.
    src = 'let result = range(200)\n'
    ast = parse(src)

    def exec_with(i):
        env = Env(i.globals)
        for stmt in ast.stmts:
            i.exec_stmt(stmt, env)
        return env

    generous = Interpreter(out=lambda *a: None, max_value=None)
    assert isinstance(exec_with(generous).get("result").payload, WList)

    tight = Interpreter(out=lambda *a: None, max_value=4096)
    p = exec_with(tight).get("result").payload
    assert isinstance(p, Miss) and "range too large" in reason(p)

    # ... and the peak counter follows the RUNNING interpreter: the tight run
    # must not have charged the generous one.
    assert generous.peak_value == 200 * I._RANGE_BYTES_PER_ELEM
    assert tight.peak_value == 200 * I._RANGE_BYTES_PER_ELEM


def test_the_fast_closure_never_decides_a_size_miss_itself():
    # `_compile_binop`'s own docstring promises the compiled closure never
    # decides a miss, so that the two paths cannot disagree on wording. Both
    # spellings of every growth site must give byte-identical reasons.
    for src, _ in GROWTH_SITES.values():
        fast = reason(payload(src, fast=True, **SMALL))
        slow = reason(payload(src, fast=False, **SMALL))
        direct = reason(payload(src, direct=False, **SMALL))
        assert fast == slow == direct, src


# ==========================================================================
# 6. the CLI
# ==========================================================================

def _cli(src, *flags):
    path = os.path.join(ROOT, "tests", "__pycache__", "v27_tmp.lang")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(
        [sys.executable, os.path.join(ROOT, "run.py")] + list(flags) + [path],
        capture_output=True, text=True, timeout=300)
    return p.returncode, p.stdout + p.stderr


def test_cli_reports_a_size_miss_and_not_a_traceback():
    # The runaway shape, at the SHIPPED defaults, through the real CLI: this
    # is the program that used to end in a MemoryError traceback and exit 1.
    rc, out = _cli('fn go(n, s) { if n <= 0 { s } else { go(n - 1, s + s) } }\n'
                   'let result = go(60, "ab")\nprint(result)\n')
    assert rc == 0 and "Traceback" not in out
    assert "string too large" in out


def test_cli_max_value_flag_lowers_the_budget():
    rc, out = _cli("let result = range(100)\nprint(result)\n",
                   "--max-value", "1000")
    assert rc == 0 and "range too large: 100 elements" in out


def test_cli_max_int_bits_flag_lowers_the_budget():
    rc, out = _cli(BIG + "print(big)\n", "--max-int-bits", "1000")
    assert rc == 0 and "integer too large" in out


def test_cli_zero_restores_unbounded_on_both_flags():
    # `--max-value 0` / `--max-int-bits 0` are the explicit opt-outs, exactly
    # like v0.26's `--max-iter 0`. A small program that WOULD miss under a
    # tiny budget must succeed when the same flag is zeroed.
    rc, out = _cli("let result = range(100)\nprint(len(result))\n",
                   "--max-value", "0")
    assert rc == 0 and "100" in out and "too large" not in out
    rc, out = _cli(BIG + "print(big)\n", "--max-int-bits", "0")
    assert rc == 0 and "<integer, 51937 bits>" in out


def test_cli_usage_names_both_new_flags():
    rc, out = _cli("let x = 1\n", "--help")
    assert "--max-value" in out and "--max-int-bits" in out


def test_cli_rejects_a_non_numeric_budget():
    rc, out = _cli("let x = 1\n", "--max-value", "big")
    assert rc == 2 and "usage:" in out


# ==========================================================================
# 7. the corpus still runs, with margin
# ==========================================================================

EXAMPLES = sorted(
    n for n in os.listdir(os.path.join(ROOT, "examples")) if n.endswith(".lang"))


@pytest.mark.whence_slow
def test_every_example_stays_under_both_defaults_with_margin():
    """Round 366 shipped a `max_iter` default that broke four examples
    because the derivation was principled and the corpus was never
    consulted. This is that lesson, applied to two more numbers: every
    example that runs today must stay a factor of 3 under BOTH budgets."""
    worst_value, worst_bits, where = 0, 0, {}
    for name in EXAMPLES:
        path = os.path.join(ROOT, "examples", name)
        interp = Interpreter(out=lambda *a: None, gc_relief=True,
                             max_value=None, max_int_bits=None)
        try:
            interp.run(open(path, encoding="utf-8").read())
        except (LexError, ParseError):
            continue          # 8 of the untracked .lang files do not parse
        if interp.peak_value > worst_value:
            worst_value, where["value"] = interp.peak_value, name
        if interp.peak_int_bits > worst_bits:
            worst_bits, where["bits"] = interp.peak_int_bits, name
    assert worst_value * 3 <= Interpreter.DEFAULT_MAX_VALUE, (worst_value, where)
    assert worst_bits * 3 <= Interpreter.DEFAULT_MAX_INT_BITS, (worst_bits, where)


def test_the_largest_range_in_the_tree_is_far_under_the_default():
    # `range(3000)` is the biggest anywhere in this repo, tests included.
    assert 3000 * I._RANGE_BYTES_PER_ELEM * 3 <= Interpreter.DEFAULT_MAX_VALUE


def test_the_longest_loop_and_the_largest_value_are_not_the_same_program():
    # Measured: deep.lang merges 200001 tail iterations and peaks at a
    # 20-byte value; self_eval.lang peaks at 15700 B with a longest loop of
    # 143. Neither budget predicts the other — which is the empirical reason
    # `max_iter` could not have been re-tuned to cover this class. Pinned on
    # the two cheap examples so the claim is re-executed, not just asserted.
    i1 = Interpreter(out=lambda *a: None, gc_relief=True)
    i1.run(open(os.path.join(ROOT, "examples", "tco.lang"),
                encoding="utf-8").read())
    assert i1.peak_tail > 10000 and i1.peak_value < 1000
