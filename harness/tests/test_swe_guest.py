"""Tests for the guest-differential oracle (swe/guest.py, round 17).

The oracle compares the host interpreter against the self-hosted evaluator
(examples/self_eval.lang). Zero findings on random programs is only evidence
if the oracle demonstrably fires on injected divergences — so half of these
tests run against a deliberately broken copy of the guest library.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from swe import guest as G
from swe import oracles as O
from swe.killers import load_whence
from swe.fuzz import WHENCE_ROOT


@pytest.fixture(scope="module")
def pkg():
    p = load_whence(WHENCE_ROOT, "guesttest")
    assert p["root"] == WHENCE_ROOT
    return p


@pytest.fixture(scope="module")
def harness(pkg):
    return G.GuestHarness(WHENCE_ROOT, pkg)


def outcome(pkg, harness, src):
    return G.oracle_self_eval(pkg, src, harness=harness)


# ----------------------------------------------------------- the generator --

def test_generator_emits_no_banned_tokens():
    for seed in range(60):
        src = G.generate_guest_program(seed)
        body = src.split("let __result")[0]
        assert not G.BANNED.search(body), (seed, body)


def test_generated_programs_mostly_parse(pkg):
    parsed = 0
    for seed in range(40):
        src = G.generate_guest_program(seed)
        try:
            O._parse(pkg, src)
            parsed += 1
        except (pkg["LexError"], pkg["ParseError"]):
            pass
    # statement-level filtering must not leave dangling fragments behind
    assert parsed >= 36, parsed


def test_guest_safe_strips_banned_lines():
    src = "let a = 1\nprint(why a)\nlet b = steps(a)\nlet c = a + 1\n"
    assert G.guest_safe(src) == "let a = 1\nlet c = a + 1\n"


def test_escape_roundtrip(pkg, harness):
    # a program full of string escapes must survive embedding into run_src
    src = ('let s = "a\\nb" + "\\"q\\"" + "back\\\\slash"\n'
           'let n = len(s)\n'
           'let __result = @{s: (s rescue "&MISS&"), n: (n rescue "&MISS&")}\n')
    o = outcome(pkg, harness, src)
    assert o.kind == "ok", o.detail


# ------------------------------------------------- agreement on real cases --

AGREE_CASES = [
    "let a = 1 + 2 * 3\nlet b = a / 4\ncheck \"c\": b > 1\n",
    "fn fib(n) { if n < 2 { n } else { fib(n - 1) + fib(n - 2) } }\nlet v = fib(9)\n",
    "let xs = fold(fn(acc, x) { push(acc, x * x) }, [], range(6))\nlet y = xs[3]\n",
    "let r = @{name: \"Ada\", age: 36}\nlet v = r.name + str(r.age)\n",
    "let m = num(\"3O\")\nlet saved = m rescue -1\n",           # miss + rescue
    "let bad = nope + 1\nlet alsobad = bad * 2\n",             # unbound name
    "fn f(x) { x }\nlet g = f\nlet h = fold\n",                # function bindings
    "let e = 1 / 0\ncheck \"z\": missed(e)\n",
    # v0.6 `has`: present / absent / miss-valued field / opaque closures
    "let r = @{a: 1}\nlet p = has(r, \"a\")\nlet q = has(r, \"zz\")\n",
    "let r = put(@{}, \"m\", num(\"xx\"))\nlet p = has(r, \"m\")\n",
    "fn f(x) { x }\nlet p = has(f, \"body\")\nlet saved = p rescue false\n",
    "let e = fold(fn(a, i) { put(a, \"k\" + str(i), i) }, @{}, range(4))\n"
    "let g = get(e, \"k2\")\nlet h = has(e, \"k9\")\n",
]


@pytest.mark.parametrize("body", AGREE_CASES)
def test_agreement_on_handpicked_cases(pkg, harness, body):
    names = re.findall(r"^(?:let|fn) (\w+)", body, re.M)
    scrub = ('%s: (%s rescue (if contains(join(reasons(%s), "|"), "depth") '
             '{ "&DEPTHMISS&" } else { "&MISS&" }))')
    src = body + "let __result = @{%s}\n" % ", ".join(
        scrub % (n, n, n) for n in names)
    o = outcome(pkg, harness, src)
    assert o.kind == "ok", (body, o.detail)


def test_depth_skew_is_exempt(pkg):
    # a shallow guest interpreter runs out of host depth while the host-side
    # run succeeds; the depth sentinel must absorb the difference
    shallow = G.GuestHarness(WHENCE_ROOT, pkg, max_depth=800)
    src = ("fn c(n) { if n == 0 { 0 } else { 1 + c(n - 1) } }\n"
           "let v = c(120)\n"
           'let __result = @{v: (v rescue (if contains(join(reasons(v), "|"), '
           '"depth") { "&DEPTHMISS&" } else { "&MISS&" }))}\n')
    o = G.oracle_self_eval(load_dict_with_root(pkg), src, harness=shallow)
    assert o.kind == "ok", o.detail


def load_dict_with_root(pkg):
    d = dict(pkg)
    d.setdefault("root", WHENCE_ROOT)
    return d


# --------------------------------------------------- injected-bug firing --

def _lib_source():
    with open(os.path.join(WHENCE_ROOT, "examples", "self_eval.lang"),
              encoding="utf-8") as f:
        return f.read().split(G.LIB_MARKER)[0]


def _broken_harness(pkg, old, new):
    lib = _lib_source()
    assert lib.count(old) == 1, old
    return G.GuestHarness(WHENCE_ROOT, pkg, lib_source=lib.replace(old, new))


def test_injected_arith_bug_fires(pkg):
    h = _broken_harness(pkg, 'if op == "-" { a.v - b.v }',
                        'if op == "-" { a.v + b.v }')
    src = ('let v = 10 - 3\n'
           'let __result = @{v: (v rescue "&MISS&")}\n')
    o = G.oracle_self_eval(load_dict_with_root(pkg), src, harness=h)
    assert o.kind == "mismatch"
    assert o.detail.startswith("value"), o.detail
    assert O.signature(o)[0] == "mismatch"


def test_injected_check_bug_fires(pkg):
    # invert the guest's check recording: pass becomes fail
    h = _broken_harness(pkg, "@{label: stmt.label, pass: ok}",
                        "@{label: stmt.label, pass: not ok}")
    src = ('check "good": 1 + 1 == 2\nlet v = 0\n'
           'let __result = @{v: (v rescue "&MISS&")}\n')
    o = G.oracle_self_eval(load_dict_with_root(pkg), src, harness=h)
    assert o.kind == "mismatch"
    assert o.detail.startswith("checks"), o.detail


def test_injected_missedness_bug_fires(pkg):
    # make the guest rescue the div-by-zero into 0 where the host misses:
    # `1 / 0` then diverges in missed-ness, which the sentinel scrub exposes
    h = _broken_harness(pkg, 'else if op == "/" { a.v / b.v }',
                        'else if op == "/" { (a.v / b.v) rescue 0 }')
    src = ('let v = 1 / 0\n'
           'let __result = @{v: (v rescue "&MISS&")}\n')
    o = G.oracle_self_eval(load_dict_with_root(pkg), src, harness=h)
    assert o.kind == "mismatch"
    assert o.detail.startswith("value"), o.detail


def test_reified_reason_strings_are_exempt(pkg, harness):
    # reasons() turns miss WORDINGS (design-exempt) into ordinary strings;
    # first campaign's dominant false-positive family (line numbers point
    # into the guest library). Both reason-shaped -> agree.
    src = ('let r = reasons(len(1))\nlet s = str(1 / 0)\n'
           'let __result = @{r: (r rescue "&MISS&"), s: (s rescue "&MISS&")}\n')
    o = outcome(pkg, harness, src)
    assert o.kind == "ok", o.detail


def test_reason_string_vs_plain_value_still_mismatches():
    assert G._both_exempt_strings("len of 1 (line 3)", "len of 1 (line 700)")
    assert G._both_exempt_strings("miss: x", "miss: totally different words")
    assert not G._both_exempt_strings("len of 1 (line 3)", "4")
    assert not G._both_exempt_strings("plain", "also plain")


def test_function_render_strings_are_exempt():
    assert G._both_exempt_strings("<fn fib>", '@{__tag: "closure", params: ...}')
    assert G._both_exempt_strings("miss: sqrt of <fn f1> (line 4)",
                                  'miss: sqrt of @{__tag: "closure"...')
    assert not G._both_exempt_strings("<fn fib>", "fib")


def test_guest_closures_are_opaque_after_fix(pkg, harness):
    # round-17 finding: len/keys/field pierced guest closure records
    src = ('fn f(x) { x }\nlet a = len(f)\nlet b = keys(f)\nlet c = f.params\n'
           'let d = merge(@{q: 1}, f)\n')
    o = outcome(pkg, harness, src)
    assert o.kind == "ok", o.detail


# ------------------------------------------------------------ oracle wiring --

def test_registered_in_oracles_table():
    assert G.GUEST_ORACLE in O.ORACLES
    assert O.ORACLES[G.GUEST_ORACLE] is G.oracle_self_eval
    # the default oracle set is unchanged: self_eval is opt-in (guest-safe
    # programs only; host-grammar programs would spray false positives)
    assert G.GUEST_ORACLE not in O.ORACLE_NAMES


def test_result_record_auto_appended_for_plain_programs(pkg, harness):
    # a model submits a plain program; the oracle builds the scrub record
    o = outcome(pkg, harness, "let a = 2 + 3\nfn f(x) { x * a }\nlet b = f(4)\n")
    assert o.kind == "ok", o.detail


def test_non_guest_safe_program_is_rejected_not_diverged(pkg, harness):
    o = outcome(pkg, harness, "let a = 1\nlet w = why a\n")
    assert o.kind == "parse_error"
    assert "not guest-safe" in o.detail


def test_bindingless_program_is_rejected(pkg, harness):
    o = outcome(pkg, harness, "1 + 1\n")
    assert o.kind == "parse_error"


def test_run_oracle_path_works(pkg):
    src = ('let v = 6 * 7\nlet __result = @{v: (v rescue "&MISS&")}\n')
    o = O.run_oracle(G.GUEST_ORACLE, load_dict_with_root(pkg), src,
                     timeout_s=8.0, max_depth=2000)
    assert o.kind == "ok", o.detail


# ------------------------------------------------------ why-shape probe --

def test_why_probe_fires_on_injected_mirror_bug(pkg):
    # re-inject the REAL bug the probe caught in round 20: guest range
    # elements labelled "literal" where the host labels them "range"
    h = _broken_harness(
        pkg, 'else if name == "range" { map(fn(x) { mkb(x, "range", []) }, p) }',
        'else if name == "range" { map(fn(x) { mkb(x, "literal", []) }, p) }')
    src = ('let y = (range(4))[2]\n'
           'let __result = @{y: (y rescue "&MISS&")}\n')
    o = G.oracle_self_eval(load_dict_with_root(pkg), src, harness=h)
    assert o.kind == "mismatch"
    assert o.detail.startswith("why_shape"), o.detail
    assert "literal" in o.detail


def test_why_probe_can_be_disabled(pkg):
    h = _broken_harness(
        pkg, 'else if name == "range" { map(fn(x) { mkb(x, "range", []) }, p) }',
        'else if name == "range" { map(fn(x) { mkb(x, "literal", []) }, p) }')
    src = ('let y = (range(4))[2]\n'
           'let __result = @{y: (y rescue "&MISS&")}\n')
    o = G.oracle_self_eval(load_dict_with_root(pkg), src, harness=h,
                           why_probe=False)
    assert o.kind == "ok", o.detail


def test_why_probe_ok_on_clean_guest(pkg, harness):
    src = ('let xs = map(fn(i) { @{id: i} }, range(3))\n'
           'let y = (find(fn(r) { r.id == 2 }, xs)).id\n'
           'let __result = @{y: (y rescue "&MISS&")}\n')
    o = outcome(pkg, harness, src)
    assert o.kind == "ok", o.detail


def test_new_templates_reach_has_put_and_are_guest_safe(pkg):
    seen_has = seen_put = 0
    for seed in range(3000, 3080):
        src = G.generate_guest_program(seed)
        assert not G.BANNED.search(src.split("let __result")[0]), seed
        if "has(" in src:
            seen_has += 1
        if "put(" in src:
            seen_put += 1
    assert seen_has >= 5 and seen_put >= 5, (seen_has, seen_put)


def test_campaign_smoke():
    camp = G.fuzz_guest(seed=5, n=6, do_shrink=False)
    assert camp.programs == 6
    kinds = set(k for (_, k) in camp.counts)
    assert kinds <= {"ok", "parse_error", "timeout", "mismatch", "crash"}


# Round 107: three divergences found by guest-differential seed 115 (all
# pre-existing in self_eval.lang): functions nested in lists/records under
# `==` compared structurally (host: miss at any depth), `contains` with a
# function needle missed (host: false), and `num(number)` derived a `num`
# node (host: pass-through). Each source was a `mismatch` before the fix.
ROUND107_SOURCES = [
    'fn even(n) { if n == 0 { true } else { odd(n - 1) } }\n'
    'fn odd(n) { if n == 0 { false } else { even(n - 1) } }\n'
    'let v1 = [odd, even]\nlet v2 = odd\nlet v3 = @{a: odd}\n'
    'check "q_v1": v1 == v1\ncheck "q_v2": v2 == v2\ncheck "q_v3": v3 == v3\n'
    'let r1 = (v1 == v1) rescue "m"\nlet r3 = (v3 != v3) rescue "m"\n',
    'fn odd(n) { n }\nlet c1 = contains([odd], odd)\nlet c2 = contains([1, odd], 1)\n'
    'let c3 = contains([[odd]], [odd])\nlet c4 = (contains("abc", odd)) rescue "m"\n',
    'fn adder(a) { fn(b) { a + b } }\nlet addv = adder(0)(0) + adder(0)(0)\n'
    'let v1 = num(addv)\nlet v2 = num("5")\nlet v3 = num(3.5)\n',
]


@pytest.mark.parametrize("src", ROUND107_SOURCES)
def test_round107_guest_divergences_fixed(pkg, src):
    out = G.oracle_self_eval(pkg, src)
    assert out.kind == "ok", out.detail
