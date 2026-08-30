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


def test_generator_now_includes_guess_family_in_guest_output(pkg, harness):
    # v0.15 (round 168) added `guess`/`is_guess`/`confidence`/`sure` to the
    # shared BUILTIN_ARITY table (round 174), but self_eval.lang had no
    # runtime support yet, so GuestGen banned the names outright (a
    # `guess(...)` call is always a droppable expression-level line, never
    # syntax baked into a function signature like `: Type`/`effects [...]`,
    # so a blanket ban was the correct-scoped fix at the time). Round 176
    # gave self_eval.lang real Guess support (delegates straight to the
    # host builtins), closing that gap — this test replaces the old
    # never-leaks assertion with its mirror image: the guest generator DOES
    # emit these calls now, at close to the same rate as the unfiltered
    # host-only generator, and the oracle finds zero real mismatches
    # fuzzing them (the actual exercise-under-fuzz round 174 could not do).
    from swe.fuzz import ProgramGen
    guess_re = re.compile(r"\b(guess|is_guess|confidence|sure)\(")
    raw_hits = sum(1 for i in range(300)
                   if guess_re.search(ProgramGen(i, stress_rate=0.0).program()))
    assert raw_hits >= 15, raw_hits
    guest_hits = 0
    mismatches = []
    for i in range(300):
        src = G.generate_guest_program(i)
        if not guess_re.search(src):
            continue
        guest_hits += 1
        o = outcome(pkg, harness, src)
        if o.kind == "mismatch":
            mismatches.append((i, o.detail))
    assert guest_hits >= 10, guest_hits
    assert not mismatches, mismatches[:3]


# ==================================================== v0.14.8 (round 299) ==
# `rand` joined `BUILTIN_ARITY` (round 299, `harness/swe/fuzz.py`) as
# Whence's second effectful builtin (v0.14.8, round 294) — UNLIKE `guess`/
# `is_guess`/`confidence`/`sure` above, this one stays banned on purpose:
# `BANNED`'s own comment explains why (the guest's total non-enforcement of
# `effects [...]` declarations, not an execution-support gap — `self_eval.
# lang` has dispatched `rand()` straight to the host builtin since round
# 296, exactly like `print`).

def test_generator_can_emit_rand_but_it_stays_banned():
    """The mirror image of `test_generator_emits_no_banned_tokens`: confirms
    the ban is actually EXERCISED, not vacuously true because the shared
    grammar never happens to produce `rand` text in the first place. The
    unfiltered host-only generator must emit `rand` at a real rate; the
    guest-filtered generator (same seeds) must never let it through."""
    from swe.fuzz import ProgramGen
    rand_re = re.compile(r"\brand\b")
    raw_hits = sum(1 for i in range(200)
                   if rand_re.search(ProgramGen(i, stress_rate=0.0).program()))
    assert raw_hits >= 15, raw_hits
    for i in range(200):
        src = G.generate_guest_program(i)
        assert not rand_re.search(src.split("let __result")[0]), (i, src)


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
    # round 164: `effects [...]` now parses on the guest (skip-and-ignore,
    # not enforced) — these never violate their own declaration, so
    # non-enforcement is invisible and both sides must still agree
    "fn f(a) effects [] { a + 1 }\nlet v = f(3)\n",
    "fn f(a) effects [io] -> num { a + 1 }\nlet v = f(3)\n",
    "let g = fn(a, b) effects [net, io] { a + b }\nlet v = g(2, 3)\n",
    # round 251: `guess()` given a LIST/RECORD value used to leak the guest's
    # own internal @{op,v,ins} boxes as the Guess's payload elements instead
    # of plain host values — found by a targeted guest-fuzz campaign
    # specifically generating Guess-carrying programs (round 234's own
    # flagged-but-never-run backlog item), minimized to
    # `guess([1,2,3], 0.5, "m")`. Root cause: `apply_host_builtin`'s "guess"
    # branch passed the bare `a0` (`args[0].v`) straight to the host
    # builtin — correct for a scalar (a literal box's `.v` already IS the
    # raw value) but wrong for a compound value, whose `.v` is a host
    # list/record of nested guest boxes, not unwrapped payloads. Fixed with
    # `strip(args[0])` (self_eval.lang), the same recursive unwrap already
    # used by `print`/`str`/`contains`/`join` in the same function.
    "let v = guess([1, 2, 3], 0.5, \"m\")\n",
    "let v = guess(@{a: 1, b: 2}, 0.5, \"m\")\n",
    # round 335: `matches`/`shapeof`/`typed` joined `BUILTIN_ARITY`, so
    # `GuestGen` emits them now too (nothing bans them -- self_eval.lang has
    # dispatched all three since rounds 158/224). The `typed` branch of the
    # guest's `apply_builtin` required `is_str(spec)`, so every RECORD spec
    # -- a first-class, hand-buildable structural spec on the host, SPEC
    # v0.12's "a record built entirely by hand ... matches it exactly as one
    # built from it" -- came back a miss on the guest while the host passed
    # the value straight through. Round 240 had already fixed exactly this
    # for `matches` (via `strip()`); the `typed` branch was never revisited.
    # The first case below is the minimized divergence; the rest pin the
    # neighbourhood (mismatch, nesting, `__shape` naming, and the why-shape
    # probe's own guest-only-`record`-op finding for a NON-record value).
    "let v = typed(@{a: 1}, @{a: \"num\"}, \"L\")\n",
    "let v = typed(@{a: 1, b: 2}, @{a: \"num\"}, \"L\")\n",
    "let v = typed(@{a: @{b: 1}}, @{a: @{b: \"num\"}}, \"L\")\n",
    "let v = typed(@{x: 1}, @{__shape: \"Pt\", x: \"num\"}, \"L\")\n",
    "let v = typed(@{a: \"s\"}, @{a: \"num\"}, \"L\")\n",
    "let v = missed(typed(1, @{a: \"num\"}, \"L\"))\n",
    "let v = str(typed(@{a: 1}, @{a: \"num\"}, \"L\"))\n",
    "let a = matches(@{a: 1}, @{a: \"num\"})\nlet b = matches(@{a: 1}, @{a: 5})\n",
    "let a = shapeof(@{a: 1})\nlet b = shapeof(fn(x) { x })\nlet c = shapeof(num(\"x\"))\n",
    "fn f(x) { typed(x, @{a: \"num\"}, \"p\") }\nlet v = f(@{a: 1})\nlet w = f(3)\n",
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


def test_run_oracle_forwards_kwargs_to_the_oracle_fn(pkg, harness):
    # round 289: `run_oracle` used to call `fn(pkg, src, max_depth=...)`
    # only — no way to also pass an oracle-specific kwarg like guest.py's
    # `harness=`. Confirms the forwarded `harness=` is the SAME shared
    # instance (not silently ignored / rebuilt), by mutating it first the
    # way `test_injected_arith_bug_fires` does.
    h = _broken_harness(pkg, 'if op == "-" { a.v - b.v }',
                        'if op == "-" { a.v + b.v }')
    src = ('let v = 10 - 3\nlet __result = @{v: (v rescue "&MISS&")}\n')
    o = O.run_oracle(G.GUEST_ORACLE, load_dict_with_root(pkg), src,
                     timeout_s=8.0, max_depth=2000, harness=h)
    assert o.kind == "mismatch", o.detail


def test_run_oracle_kwargs_bounds_a_shared_harness_hang(pkg):
    """Round 185's own root cause, now fixable: a one-off script explored
    `GUEST_ORACLE` mismatches with ONE `GuestHarness` shared across several
    programs (avoiding a re-parse of the ~800-line self_eval.lang library
    per program) — a need `run_oracle`'s old signature had no hook for,
    forcing a bare `G.oracle_self_eval(pkg, src, harness=h)` call that
    skips `run_oracle`'s SIGALRM timeout entirely. That round's own
    self-recursive guest program (`fn f6() { let t7 = f6() ... }`, no base
    case) then ran for 2912s before the OUTER driver process timeout
    finally killed it.

    Round 289 manually re-ran that exact program bare (no `run_oracle`) and
    found its duration is genuinely load-dependent, not a fixed hang: one
    run exceeded a 6s bash `timeout` wrapper (exit 124), another completed
    in 7.8s — both consistent with round 185's true cause (the guest
    interpreter, built via `harness_for`/`GuestHarness.__init__` with no
    `max_depth` passed, recurses to `DEFAULT_MAX_DEPTH` = 20000 through the
    self-hosted, doubly-interpreted evaluator before the depth Miss even
    fires, not a true infinite loop) but too timing-dependent to assert on
    directly in a test. This test instead monkeypatches `eval_program` to
    block deterministically, isolating the actual fix under test — that
    `run_oracle`'s new `**kwargs` forwarding lets a caller reach `harness=`
    at all, so `run_oracle`'s existing SIGALRM wrapper can bound whatever
    that shared harness ends up doing, real recursion or not."""
    import time
    h = G.GuestHarness(WHENCE_ROOT, pkg)
    h.eval_program = lambda src: time.sleep(30)
    src = ('let v = 6 * 7\nlet __result = @{v: (v rescue "&MISS&")}\n')
    o = O.run_oracle(G.GUEST_ORACLE, load_dict_with_root(pkg), src,
                     timeout_s=0.5, max_depth=2000, harness=h)
    assert o.kind == "timeout", o.detail


def test_guest_harness_cache_evicted_after_a_mid_call_exception(pkg):
    """Round 149: `run_oracle`'s SIGALRM can fire at ANY point inside
    `h.eval_program`, which mutates the long-lived, CACHED `GuestHarness`
    shared across every program in a campaign (built once to avoid
    re-parsing the ~800-line self_eval.lang library per program). An
    interrupt mid-mutation can leave that shared harness in an unknown
    state that then corrupts a later, unrelated program's result.
    Found via 3 guest-differential 'mismatch' findings (round 137, seeds
    141/142) that reproduced neither standalone nor via an identical-
    sequence replay into a FRESH harness — the only remaining variable is
    a genuinely wall-clock-timed interrupt elsewhere in the same long-lived
    harness, and round 137 ran this campaign under heavy concurrent CPU
    load (a live 5-worker mutation campaign). Simulates the interrupt
    directly (no real SIGALRM needed) and checks the cache entry for a
    harness that raised is evicted, so the next call rebuilds fresh instead
    of inheriting whatever state the raise left behind."""
    # A genuinely distinctly-named package, not just a copied dict with a
    # relabeled "name" field: GuestHarness.__init__ re-imports
    # `pkg["name"] + ".values"` via `__import__`, which only resolves if a
    # module was actually registered under that name in `sys.modules` —
    # `load_whence` does that; overwriting "name" on a dict copy of the
    # module-scoped `pkg` fixture does not, and fails with
    # ModuleNotFoundError before this test's own logic ever runs.
    d = load_whence(WHENCE_ROOT, "guest_evict_test")
    h1 = G.harness_for(d)
    assert G._HARNESSES[d["name"]] is h1

    def boom(src):
        raise RuntimeError("simulated mid-flight interrupt")
    h1.eval_program = boom
    with pytest.raises(RuntimeError):
        G.oracle_self_eval(d, "let a = 1\n")
    assert d["name"] not in G._HARNESSES

    o = G.oracle_self_eval(d, "let b = 2 + 3\n")
    assert o.kind == "ok", o.detail
    assert G._HARNESSES[d["name"]] is not h1


def test_harness_for_default_max_depth_matches_oracle_default():
    """Round 289's flagged gap: `harness_for` used to build with
    `max_depth=None`, resolving to the raw interpreter's `DEFAULT_MAX_DEPTH`
    (20000) regardless of whatever cap the HOST side of the SAME comparison
    used (`oracle_self_eval`'s own default, 2000). Round 295's fix: both
    default to the same value."""
    d = load_whence(WHENCE_ROOT, "guest_depth_default_test")
    h = G.harness_for(d)
    assert h.max_depth == 2000
    assert h.interp.max_depth == 2000


def test_harness_for_rebuilds_on_a_different_max_depth_and_reuses_on_a_match():
    """The cache used to be keyed on package name alone; a caller asking
    for a different `max_depth` than whatever happened to be cached would
    silently get the WRONG depth cap. Now a mismatched request rebuilds,
    and a matching one reuses the same instance."""
    d = load_whence(WHENCE_ROOT, "guest_depth_rebuild_test")
    h1 = G.harness_for(d, max_depth=500)
    assert h1.interp.max_depth == 500
    h2 = G.harness_for(d, max_depth=1500)
    assert h2 is not h1
    assert h2.interp.max_depth == 1500
    h3 = G.harness_for(d, max_depth=1500)
    assert h3 is h2


def test_oracle_self_eval_builds_guest_with_host_matching_max_depth():
    """The actual mechanism under test: with no explicit `harness=`
    override (the normal `fuzz_guest` campaign path), `oracle_self_eval`'s
    own `max_depth` argument — which bounds the HOST-side run — now also
    bounds the cached GUEST harness it builds, instead of the guest always
    getting the interpreter's unrelated 20000 default. Before round 295,
    this asymmetry meant a genuine mismatch surfacing only in a guest
    recursion between the host's (lower) cap and 20000 would be silently
    swallowed as an exempt `depth_skew`, not compared."""
    d = load_whence(WHENCE_ROOT, "guest_depth_symmetry_test")
    G.oracle_self_eval(d, "let v = 1\n", max_depth=777)
    assert G._HARNESSES[d["name"]].interp.max_depth == 777


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


def test_generator_now_emits_effects_clauses():
    # round 164 closed the round-162 no-op: GuestGen inherits ProgramGen's
    # real maybe_effects again once self_eval.lang/self_host.lang's shared
    # parser section could skip-parse the clause. Generated effects clauses
    # never survive the BANNED filter's own print-stripping with a live
    # print call left in the body (see GuestGen's docstring), so this must
    # still produce guest-safe, unbanned source.
    seen_effects = 0
    for seed in range(4000, 4100):
        src = G.generate_guest_program(seed)
        assert not G.BANNED.search(src.split("let __result")[0]), seed
        if "effects" in src:
            seen_effects += 1
    assert seen_effects >= 10, seen_effects


def test_generated_effects_programs_agree(pkg, harness):
    # pull actual GENERATOR output (not hand-written cases) through the
    # real oracle until an effects-bearing program turns up, confirming the
    # parse-skip mechanism works on genuinely random shapes, not just the
    # three hand-picked AGREE_CASES entries above.
    found = 0
    for seed in range(4000, 4200):
        src = G.generate_guest_program(seed)
        if "effects" not in src:
            continue
        found += 1
        o = outcome(pkg, harness, src)
        assert o.kind == "ok", (seed, src, o.detail)
        if found >= 8:
            break
    assert found >= 8, found


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


# Round 275: research-state.md carried a standing backlog note (dated to
# the round 167-171 era) claiming seed 4002 (`effects`) and seed 152
# (`why_shape`, a `guess`-family program) were confirmed-on-clean-HEAD
# divergences, never fixed. Round 271 tried to re-check it and couldn't
# (the file's real cost lives in its OTHER tests iterating hundreds of
# generated programs; this file's own presence was mistaken for the
# bottleneck). Round 275 isolated just these two seeds with a standalone
# script (~1s each, not the whole suite) and found both now report "ok" —
# already fixed by one of the many guest-parity rounds since 171 (204,
# 206, 218, 222, 246, 252, 266, 270, 272 all touched adjacent effects/
# guess-family code; no single round's commit message names either seed,
# so the exact fixing commit is not identifiable after the fact). Pinned
# here so a future regression is caught immediately instead of waiting
# for the next archaeology round.
@pytest.mark.parametrize("seed", [4002, 152])
def test_round167_backlog_seeds_now_agree(pkg, harness, seed):
    src = G.generate_guest_program(seed)
    o = outcome(pkg, harness, src)
    assert o.kind == "ok", (seed, o.detail)


# =========================================================== round 335 ==

def test_generator_now_emits_the_shape_builtins_into_guest_programs():
    """The mirror of `test_generator_now_includes_guess_family_in_guest_
    output`: `matches`/`shapeof`/`typed` joined the shared `BUILTIN_ARITY`
    table this round and are NOT banned for the guest (unlike `print`/
    `rand`), so they must actually reach guest-safe programs -- and the
    oracle must find zero mismatches on them."""
    from swe.fuzz import ProgramGen
    pat = re.compile(r"\b(matches|shapeof|typed)\(")
    raw_hits = sum(1 for i in range(300)
                   if pat.search(ProgramGen(i, stress_rate=0.0).program()))
    assert raw_hits >= 30, raw_hits
    guest_hits = sum(1 for i in range(300)
                     if pat.search(G.generate_guest_program(i)))
    assert guest_hits >= 20, guest_hits


# =========================================================== round 365 ==
#
# `test_no_shape_declaration_reaches_the_guest_generator` (round 347) used
# to stand here, asserting the OPPOSITE of the three tests below:
#
#     """`GuestGen` inherits `ProgramGen`'s grammar; the guest parser has no
#     `shape` support at all, so a generated declaration would be a one-sided
#     parse failure."""
#     for i in range(200):
#         assert not pat.search(G.generate_guest_program(i)), i
#
# Its premise was already false when it was written. Round 338 (language C)
# taught `self_eval.lang`/`self_host.lang`'s shared parser section the
# `shape` statement and taught the guest evaluator to resolve `-> Shape` at
# closure-creation time; `GuestGen`'s own class docstring says so, nine
# rounds before round 347 wrote "the guest parser has no `shape` support at
# all" into a test docstring two hundred lines below it. The test passed
# anyway because round 347 also added `_shape_decl` to `ProgramGen` and the
# grammar happened not to reach it from the guest seeds in `range(200)`.
#
# Round 361's slow-tier sweep found it RED and handed it to SWE-loop(D) as
# "a design call: a generator override, or teach the guest `shape`". It is
# neither: the guest was taught in round 338, and round 365 MEASURED that —
# 140 of 400 guest seeds declare a shape and all of them agree.
#
# So the negative pin is replaced by three positive ones. The rate pin
# (shapes must KEEP reaching the guest), the structural pin (the shape
# binding must be in the COMPARED record — round 365's real finding: it
# never was), and the differential itself.
SHAPE_DECL_RE = re.compile(r"(^|\n)\s*shape\s")


def test_shape_declarations_reach_the_guest_generator():
    """Round 338 gave the guest a real `shape` statement, so a generated
    declaration is guest-SAFE, not a one-sided parse failure. Measured at
    round 365: 70/200 seeds (35.0%) and 140/400 (35.0%). The bound is
    deliberately loose -- this pin exists to catch the declaration falling
    OUT of guest programs entirely (which is what `GuestGen` overriding
    `_shape_decl` would do), not to freeze a rate."""
    n = sum(1 for i in range(200) if SHAPE_DECL_RE.search(G.generate_guest_program(i)))
    assert 40 <= n <= 120, n


def test_every_declared_shape_binding_reaches_the_compared_record():
    """Round 365's finding, pinned. `shape S = @{...}` desugars to an
    ordinary top-level record binding on BOTH sides, but `_shape_decl`
    registers only its optional witness in `self.scope`, and
    `generate_guest_program` built the `__result` record from
    `scope + fns`. From round 347 to round 365 every shape-declaring guest
    program therefore ran, agreed, and compared everything EXCEPT the thing
    the declaration produced.

    This is the guard on the fix. It is structural, not statistical: if a
    single declared shape name is missing from `__result`, the coverage is
    silently back to zero and the two tests around this one would still
    pass."""
    checked = 0
    for i in range(200):
        src = G.generate_guest_program(i)
        declared = re.findall(r"(?m)^shape\s+(\w+)", src)
        if not declared:
            continue
        checked += 1
        compared = set(re.findall(r"(\w+): \(", src[src.index("let __result"):]))
        assert set(declared) <= compared, (i, declared, sorted(compared))
    assert checked >= 40, checked


def test_shape_declaring_guest_programs_agree(pkg, harness):
    """The differential over the shapes themselves.

    Goes through `O.run_oracle` rather than `outcome`/`oracle_self_eval`
    because `oracle_self_eval` has no timeout of its own -- the SIGALRM
    lives in `run_oracle` -- which is exactly round 185's root cause,
    pinned two hundred lines above this by
    `test_run_oracle_kwargs_bounds_a_shared_harness_hang`. Round 365's own
    first sweep script called the bare oracle and lost 131 of 141 seeds to
    one slow program, so this is a mistake with a measured cost, not a
    hypothetical.

    ROUND 371 CORRECTION. This docstring used to say "ONE of the seeds it
    covers does not terminate: seed 31 ... runs for >90s in the HOST
    interpreter alone", and the `<= 2` bound below was justified as
    "measured at round 365: seed 31 only". Both statements were true when
    written and stopped being true at round 366, which bounded tail loops
    with `DEFAULT_MAX_ITER`. Seed 31 now terminates -- ~10 s in a fresh
    process, longer in a loaded one -- and this round measured the real
    timeout count over 200 seeds at a 30 s budget (see
    `state/swe/round-371/sweep.txt`).

    A `timeout` outcome is still ACCEPTED here, and counted: this test is
    about agreement, and a program neither side finished is not a
    disagreement. The bound stays at `<= 2` as HEADROOM, not as a
    measurement -- the duration of any one seed depends on the heap it
    runs in, which is precisely the trap the old seed-31 pin fell into."""
    checked, mismatches, timeouts = 0, [], []
    d = load_dict_with_root(pkg)
    for i in range(200):
        src = G.generate_guest_program(i)
        if not SHAPE_DECL_RE.search(src):
            continue
        checked += 1
        if checked > 25:
            break
        o = O.run_oracle(G.GUEST_ORACLE, d, src, timeout_s=20.0,
                         max_depth=2000, harness=harness)
        if o.kind == "mismatch":
            mismatches.append((i, o.detail[:300]))
        elif o.kind == "timeout":
            timeouts.append(i)
    assert checked >= 25, checked
    assert not mismatches, mismatches
    # Headroom, not a measurement -- see the round-371 note above.
    assert len(timeouts) <= 2, timeouts


def test_seed31_terminates_and_its_runaway_is_a_max_iter_miss(pkg):
    """Round 365's pin, flipped as its own docstring instructed.

    Round 365 (D) pinned `generate_guest_program(31)` as a program the HOST
    interpreter does not finish, and wrote: "If a future round fixes it,
    this test goes red and that is the intended signal -- flip it to assert
    termination and record the fix."

    Round 366 (language C) fixed it, four rounds ago, without knowing this
    test existed: it bisected the same program to line 7 (`tl3(tr5)` with
    `tr5 == 0.5`, decrementing past a `== 0` base case it can never equal),
    found the class was "a non-terminating TAIL recursion is unbounded
    because `max_depth` cannot charge a tail call", and added
    `Interpreter.DEFAULT_MAX_ITER`. Round 368 raised it to 1000000.

    THE SIGNAL NEVER FIRED, and round 371 measured why: run alone this test
    failed, run in its own file it PASSED. The old assertion was a WALL-CLOCK
    budget (`timeout_s=25.0`), and by the time pytest reaches this test the
    process holds ~9M live objects from the 69 tests before it, which makes
    the same terminating program take longer than 25 s of CPython GC. Cold:
    10.3 s. After 20 further oracle calls in one process: 18.4 s. After 40:
    21.0 s. So the pin read "still hanging" from a heap, not from a program.

    The replacement therefore asserts SEMANTICS, never a duration:
    the runaway binding is a miss, its reason names the ITERATION budget
    (not depth), and the loop stopped exactly at `DEFAULT_MAX_ITER`."""
    src = G.generate_guest_program(31)
    program = O._parse(pkg, src)
    interp, env, _out = O._run_ast(pkg, program, max_depth=2000)
    assert interp.peak_tail == pkg["Interpreter"].DEFAULT_MAX_ITER, \
        interp.peak_tail
    fields = env.get("__result").payload.fields
    # `v7 = tl3(tr5)` is the runaway; the scrub maps a miss whose reasons
    # mention "depth" to &DEPTHMISS& and everything else to &MISS&, so a
    # plain &MISS& here IS the assertion that this is not a depth miss.
    assert fields["v7"].payload == G.MISS_SENTINEL, fields["v7"].payload
    # and unscrubbed, the reason names the budget that actually stopped it
    bare = O._parse(pkg, "fn tl3(p4) { if p4 == 0 { 0.5 } else { tl3(p4 - 1) } }\n"
                         "let v7 = tl3(0.5)\n")
    _i2, env2, _o2 = O._run_ast(pkg, bare, max_depth=2000)
    reasons = " | ".join(env2.get("v7").payload.reasons)
    assert "tail loop too long" in reasons, reasons
    assert "depth" not in reasons, reasons


def test_seed31_agrees_between_host_and_guest_now_that_it_terminates(pkg):
    """The other half of round 365's pin: with the loop bounded, the
    guest-differential can finally RUN this seed instead of timing out.

    It reports `ok` -- but round 371 measured that the agreement is
    EXEMPTED, not real (see the tail-ceiling tests below), so this test
    pins the exemption's report string as well. If a future round teaches
    the guest tail calls, `depth_exempt` disappears from the detail and
    this test goes red, which is the intended signal."""
    o = O.run_oracle(G.GUEST_ORACLE, load_dict_with_root(pkg), G.generate_guest_program(31),
                     timeout_s=120.0, max_depth=2000)
    assert o.kind == "ok", (o.kind, o.detail[:300])
    assert O.signature(o) == ("ok",), O.signature(o)


# ------------------------------------------- the guest's TAIL-call ceiling --
# Round 371 (SWE-loop D). Flipping the seed-31 pin above answered "why did
# the host hang" and immediately raised "why did the GUEST not". It did not
# hang because it refused the program 2500x earlier, on a budget the host
# does not have — and the differential's depth exemption hid that.
#
# `self_eval.lang`'s `apply_closure` charges one guest frame per CALL, and a
# tail bounce is a call. The host charges a tail call NOTHING (SPEC rule 8),
# which is the whole of Whence's tail-call story: `deep.lang` pins
# `count_tail(200000, 0) == 200000` as a language property and `tco.lang`
# pins three more. So the two evaluators disagree about whether the language
# has tail calls at all, by a factor of 500, and every oracle said `ok`.

TAIL_LOOP = ('fn go(i) { if i == 0 { 42 } else { go(i - 1) } }\n'
             'let r = go(%d)\n' +
             G.scrub_record_line(["r"]))


def _host_r(pkg, src):
    program = O._parse(pkg, src)
    interp, env, _out = O._run_ast(pkg, program, max_depth=2000)
    return env.get("__result").payload.fields["r"].payload, interp.peak_tail


def _guest_r(harness, src):
    gv = harness.eval_program(src).fields["v"].payload
    if not isinstance(gv, harness.V.Record):
        return "GUEST_INTERNAL_MISS"
    return gv.fields["r"].payload


def test_the_guest_refuses_tail_loops_the_host_answers(pkg, harness):
    """The measured boundary, bisected by
    `state/swe/round-371/tail_parity.py ceiling`: the guest answers
    `go(399)` and refuses `go(400)`, matching `self_eval.lang`'s
    `GUEST_MAX_DEPTH = 400`. The host answers BOTH, and would answer up to
    `DEFAULT_MAX_ITER` (1000000), because it spends no depth on a tail
    call at all.

    This is not a "the guest is slower/deeper" skew. It is the two
    evaluators giving different ANSWERS to a program with a value."""
    assert _guest_r(harness, TAIL_LOOP % 399) == 42
    assert _guest_r(harness, TAIL_LOOP % 400) == G.DEPTH_SENTINEL
    for n in (399, 400, 1000):
        hv, peak = _host_r(pkg, TAIL_LOOP % n)
        assert hv == 42, (n, hv)
        assert peak == n + 1, (n, peak)


def test_the_depth_exemption_covers_a_difference_of_kind_not_degree(pkg, harness):
    """The blind spot itself, pinned so it cannot go quiet again.

    `agree()` exempts any field where either side scrubbed to
    `&DEPTHMISS&`. For a NON-tail runaway both sides refuse and the
    exemption is exactly right (`both_missed`). For a tail loop the host
    has an answer and only the guest refuses (`host_valued`) — the same
    exemption, a different situation. Round 371 left the VERDICT alone
    (a known divergence must not redden the standing campaign) and made
    the exemption report which class it fired on."""
    V = harness.V
    notes = []
    assert G.agree(V, 42, G.DEPTH_SENTINEL, notes) == (True, "")
    assert notes == ["host_valued"]
    notes = []
    assert G.agree(V, G.MISS_SENTINEL, G.DEPTH_SENTINEL, notes) == (True, "")
    assert notes == ["both_missed"]
    notes = []
    assert G.agree(V, G.DEPTH_SENTINEL, 42, notes) == (True, "")
    assert notes == ["guest_valued"]
    # default stays byte-identical for every pre-round-371 caller
    assert G.agree(V, 42, G.DEPTH_SENTINEL) == (True, "")

    o = G.oracle_self_eval(pkg, TAIL_LOOP % 500, harness=harness)
    assert o.kind == "ok", (o.kind, o.detail[:200])
    assert "depth_exempt" in o.detail and "host_valued" in o.detail, o.detail
    # ... and reporting it adds no campaign signature
    assert O.signature(o) == ("ok",), O.signature(o)


def test_the_corpus_tail_contracts_the_self_hosted_definition_cannot_meet(pkg, harness):
    """`self_eval.lang`'s round-210 comment justifies `GUEST_MAX_DEPTH = 400`
    with "no example or self-hosting test corpus this project has ever run
    comes close to 400 real guest-level call frames". Measured against the
    examples' own tail-loop assertions, that is false four times over — and
    it is `apply_closure`, the one function the guard sits in, that every
    tail bounce goes through.

    Verbatim from `examples/deep.lang` and `examples/tco.lang`; the examples
    themselves are not guest-safe (`print`/`why`/`steps` are banned), which
    is why nothing had ever put these through the guest."""
    cases = [
        ('fn count_tail(n, acc) { if n == 0 { acc } else '
         '{ count_tail(n - 1, acc + 1) } }\nlet r = count_tail(200000, 0)\n',
         200000),
        ('fn sum_to(i, acc) { if i == 0 { acc } else '
         '{ sum_to(i - 1, acc + i) } }\nlet r = sum_to(100000, 0)\n',
         5000050000),
        ('fn even(n) { if n == 0 { true } else { odd(n - 1) } }\n'
         'fn odd(n) { if n == 0 { false } else { even(n - 1) } }\n'
         'let r = even(100001)\n', False),
    ]
    for body, want in cases:
        src = body + G.scrub_record_line(["r"])
        hv, _peak = _host_r(pkg, src)
        assert hv == want, (want, hv)
        assert _guest_r(harness, src) == G.DEPTH_SENTINEL, body[:40]
    # the control: a genuinely NON-tail runaway, where both sides refuse and
    # the exemption is the right answer.
    nontail = ('fn count(n) { if n == 0 { 0 } else { 1 + count(n - 1) } }\n'
               'let r = count(15000)\n') + G.scrub_record_line(["r"])
    assert _host_r(pkg, nontail)[0] == G.DEPTH_SENTINEL
    assert _guest_r(harness, nontail) == G.DEPTH_SENTINEL


def test_record_spec_agreement_over_a_generated_batch(pkg, harness):
    """The regression campaign for this round's `self_eval.lang` fix, run
    over generated programs rather than only the hand-picked cases above:
    every guest program that calls one of the three must agree."""
    pat = re.compile(r"\b(matches|shapeof|typed)\(")
    checked = 0
    mismatches = []
    for i in range(250):
        src = G.generate_guest_program(i)
        if not pat.search(src):
            continue
        checked += 1
        o = outcome(pkg, harness, src)
        if o.kind == "mismatch":
            mismatches.append((i, o.detail[:300]))
    assert checked >= 15, checked
    assert not mismatches, mismatches[:3]
