"""Fuzz-found regressions (round 5, re-landed in round 11 as v0.4.1).

Round 5's hardening (OverflowError -> miss, strict `num`) was applied to a
temp copy of the checkout and never shipped; the round-11 differential
oracle campaign re-found the whole family. These tests pin it in the real
checkout. Depth-related families (parser nesting, iterative deep_eq) were
independently fixed in round 9 and are pinned here as well.
"""
import pytest

from whence.interp import Interpreter
from whence.parser import ParseError
from whence.values import Miss

HUGE = "let huge = fold(fn(a, x) { a * 2 }, 1, range(1100))\n"
NEST = "fn nest(n) { if n == 0 { [] } else { [nest(n - 1)] } }\n"
WRAP = "fn wrap(n) { if n == 0 { @{v: 0} } else { @{v: wrap(n - 1)} } }\n"


def run(src, **kw):
    it = Interpreter(**kw)
    return it, it.run(src)


def val(src, name="result", **kw):
    return run(src, **kw)[1].vars[name].payload


def is_miss(p, text=""):
    return isinstance(p, Miss) and text in " | ".join(p.reasons)


# --- syntactic depth ------------------------------------------------------

def test_deep_syntactic_nesting_is_a_parse_error_not_a_crash():
    for src in ["let p = " + "(" * 400 + "1" + ")" * 400,
                "let n = " + "- " * 400 + "1",
                "let l = " + "[" * 400 + "]" * 400,
                "let w = " + "why " * 400 + "1"]:
        with pytest.raises(ParseError) as e:
            Interpreter().run(src)
        assert "nest" in str(e.value)


def test_moderate_nesting_still_parses():
    assert val("let result = " + "(" * 40 + "1" + ")" * 40) == 1
    assert val("let result = " + "- " * 40 + "1") == 1
    assert val("let result = " + "not " * 40 + "true") is True


# --- value depth ----------------------------------------------------------

def test_equality_on_deeply_nested_lists():
    assert val(NEST + "let d = nest(1500)\nlet result = d == d") is True
    assert val(NEST + "let result = nest(1500) == nest(1499)") is False
    assert val(NEST + "let result = nest(1500) != nest(1500)") is False


def test_equality_on_deeply_nested_records():
    assert val(WRAP + "let r = wrap(1500)\nlet result = r == r") is True
    assert val(WRAP + "let result = wrap(1500) == wrap(1501)") is False


def test_contains_on_deeply_nested_values():
    assert val(NEST + "let d = nest(1500)\nlet result = contains([d], d)") is True
    assert val(NEST + "let d = nest(1500)\nlet result = contains([nest(3)], d)") is False


def test_equality_with_miss_deep_inside_is_a_miss():
    src = "fn nest(n) { if n == 0 { [] } else { [nest(n - 0)] } }\nlet d = nest(1)\nlet result = d == d"
    assert is_miss(val(src, max_depth=50))


# --- float overflow -------------------------------------------------------

@pytest.mark.parametrize("expr", ["huge / 3", "huge / 1", "huge * 1.5", "huge % 0.5",
                                  "huge + 0.5", "huge - 0.5", "sqrt(huge)",
                                  "0.5 * huge", "huge / 0.5"])
def test_float_overflow_is_a_miss(expr):
    p = val(HUGE + "let result = " + expr)
    assert is_miss(p, "too large"), p


def test_float_overflow_miss_can_be_rescued_and_carries_blame():
    it, env = run(HUGE + "let result = (huge / 3 rescue -1)\nlet r = huge * 1.5\n"
                  'check "blamed on line 3": blame(r)[0].line == 3\n'
                  'check "reason names the overflow": contains(reasons(r)[0], "too large")\n')
    assert env.vars["result"].payload == -1
    assert [c["ok"] for c in it.checks] == [True, True], it.checks


def test_float_overflow_is_a_miss_on_the_fast_path_and_the_generator_path():
    src = HUGE + "let result = huge / 3\n"
    assert is_miss(val(src, fast=True), "too large")
    assert is_miss(val(src, fast=False), "too large")


def test_huge_int_arithmetic_that_stays_integral_works():
    assert val(HUGE + "let result = huge * 2 == huge + huge") is True
    assert val(HUGE + "let result = huge < 1.5") is False
    assert val(HUGE + "let result = abs(-huge) == huge") is True
    assert val(HUGE + "let result = huge % 7") == (2 ** 1100) % 7
    assert val(HUGE + "let result = 3 / huge") == 0.0     # underflow, not overflow


# --- num(): Whence syntax only -------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("12", 12), ("-1", -1), ("+7", 7), ("0", 0), ("1.5", 1.5), ("-0.25", -0.25),
    ("2e3", 2000.0), ("1E-2", 0.01), ("007", 7), (" 3.5 ", 3.5), ("3 ", 3),
])
def test_num_accepts_plain_decimal_syntax(text, expected):
    assert val('let result = num("%s")' % text) == expected


@pytest.mark.parametrize("text", ["1_000", "nan", "inf", "-inf", "infinity", "3 4",
                                  "1.", ".5", "0x10", "1e", "", " ", "١٢", "1,000", "--1"])
def test_num_rejects_host_only_syntax(text):
    assert is_miss(val('let result = num("%s")' % text), "cannot parse")


def test_num_out_of_range_float_is_a_miss():
    assert is_miss(val('let result = num("1e400")'), "out of range")
    assert is_miss(val('let result = num("-1e400")'), "out of range")


def test_num_of_number_is_identity():
    assert val("let result = num(3)") == 3
    assert val("let result = num(2.5)") == 2.5


# --- history walkers on deep values (round 11: oracle timeouts) ----------

def _nest_pair(n):
    it, env = run(NEST + "let d1 = nest(%d)\nlet d2 = nest(%d)\n" % (n, n), max_depth=5000)
    return env.vars["d1"], env.vars["d2"]


def test_diverge_of_a_value_with_itself_is_identity_fast():
    from whence.values import diverge, render_contrast
    d1, _ = _nest_pair(1500)
    assert diverge(d1, d1) == []
    assert render_contrast(d1, d1) == "no divergence"


def test_diverge_on_deep_equal_values_is_not_quadratic():
    """Before v0.4.1 `same_payload` re-ran a full structural compare at every
    node pair: nest(800) vs nest(800) took 26s. Relative timing: 8x the depth
    must cost well under 8x quadratic (64x) — a real regression of that shape
    reproduces at 100x+ (see the 26s/nest(800) baseline above vs. today's
    sub-0.1s), so this only needs to reject "back to O(n^2)", not pin an exact
    exponent.

    Round 233 found this flaky on this host at the original `20 *` threshold
    with a single untimed 3-rep sum: measuring the SAME code 30 times gave
    ratios from 2.4 to 65.5 (18/30 "failures"). Root cause was the
    measurement, not `diverge`: the very first `diverge()` call of the whole
    process happened inside the `small` timing window, so `small` sometimes
    paid a one-time warm-up cost (CPython's specializing adaptive
    interpreter, page-in, etc.) that `big` never paid — inflating `t_small`
    and swinging the ratio in both directions. An untimed warm-up call before
    timing either side, plus min-of-9 instead of a single 3-rep sum, cuts the
    same 30-trial spread to 7.1-32.5 — still consistently above 8x (this
    implementation is mildly superlinear, ~n^1.5, not the old bug's ~n^2),
    which is why the threshold below is 40x (60 trials measured this way:
    max 31.5) rather than tightened to match the old code's nominal 20x."""
    import gc
    import time
    from whence.values import diverge

    def best_of(pair, reps=9):
        gc.collect()
        gc.disable()
        try:
            times = []
            for _ in range(reps):
                t0 = time.perf_counter()
                assert diverge(*pair) == []
                times.append(time.perf_counter() - t0)
        finally:
            gc.enable()
        return min(times)

    small = _nest_pair(200)
    big = _nest_pair(1600)
    diverge(*small)   # untimed warm-up: let both sides pay any one-time cost
    diverge(*big)      # before either is on the clock, not just `small`
    t_small = best_of(small)
    t_big = best_of(big)
    assert t_big < 40 * max(t_small, 1e-4), (t_small, t_big)


def test_diverge_still_finds_a_value_origin_deep_inside():
    from whence.values import diverge
    src = NEST + "let d1 = nest(300)\nlet d2 = [nest(299), 7]\n"
    it, env = run(src, max_depth=5000)
    o = diverge(env.vars["d1"], env.vars["d2"])
    assert o and o[0][2] in ("step", "value")


def test_deep_eq_memo_does_not_change_semantics():
    from whence.interp import deep_eq
    it, env = run("fn f(x) { x }\nlet a = [f]\nlet b = [f]\nlet c = [[1, 2], [1, 2]]\nlet d = [[1, 2], [1, 3]]\n")
    a, b, c, d = (env.vars[k].payload for k in "abcd")
    assert deep_eq(a, b) is None and deep_eq(a, b, {}) is None      # functions: incomparable
    memo = {}
    assert deep_eq(c, c, memo) is True and memo                     # equal pairs recorded
    assert deep_eq(c, d, {}) is False
    assert deep_eq(c, d, memo) is False                             # memo never fakes equality
    assert val("let result = [f] == [f]\nfn f(x) { x }\n" if False else
               "fn f(x) { x }\nlet result = ([f] == [f] rescue \"miss\")") == "miss"
