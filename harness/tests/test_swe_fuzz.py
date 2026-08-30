"""swe.fuzz: generator determinism, oracle classification, shrinker."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe.fuzz import (ProgramGen, run_program, signature, shrink, ddmin_lines,
                      _minimize_ints, fuzz, WHENCE_ROOT, GUESS_CONFIDENCES,
                      BUILTIN_ARITY, SPEC_POOL, TYPED_LABELS)
from tests.synthetic_crash import install as install_crash, CRASH_PROGRAM


def test_generator_is_deterministic_per_seed():
    a = ProgramGen(42).program()
    b = ProgramGen(42).program()
    c = ProgramGen(43).program()
    assert a == b and a != c and a.endswith("\n")


def test_generated_programs_mostly_parse():
    from swe.fuzz import _import_whence
    _, LexError, ParseError, _, _ = _import_whence()
    from whence.parser import parse
    ok = 0
    for i in range(60):
        try:
            parse(ProgramGen(i, stress_rate=0.0).program())
            ok += 1
        except (LexError, ParseError):
            pass
    assert ok >= 50, ok   # the grammar-directed generator should rarely misparse


def test_generator_now_emits_guess_family_calls():
    # v0.15 (round 168) backlog closed round 174: `guess`/`is_guess`/
    # `confidence`/`sure` joined BUILTIN_ARITY so the grammar-directed
    # fuzzer, not just the hand-written corpus (tests/test_v15.py), reaches
    # `_guess_binop`'s weakest-link path against fast/direct/trampoline.
    guess_re = re.compile(r"\b(guess|is_guess|confidence|sure)\(")
    seen = sum(1 for i in range(200)
               if guess_re.search(ProgramGen(i).program()))
    assert seen >= 15, seen


def test_guess_and_sure_builtins_are_total_under_fuzz_confidences():
    # GUESS_CONFIDENCES mixes valid (str, num-out-of-range) and invalid
    # confidences deliberately (see fuzz.py's comment) so both the success
    # path and the "confidence must be a num in [0, 1]" miss path are real,
    # exercised host behaviour, not just generator output that happens to
    # parse — every one of them must still be a TOTAL, non-crashing run.
    for conf in GUESS_CONFIDENCES:
        src = ('let g = guess(1, %s, "model")\n'
               'let s = sure(g, 0.5) rescue -1\n'
               'print(str(is_guess(g)) + str(confidence(g) rescue -1))\n') % conf
        o = run_program(src)
        assert o.kind == "ok", (conf, o)


# ==================================================== v0.14.8 (round 299) ==
# `rand()` (v0.14.8, round 294) joined `BUILTIN_ARITY` (round 299) as the
# ONLY arity-0 entry, and `_alias_source`/`statement`'s own direct-builtin-
# alias branch now pick between `print`/`rand` — closing round 294's own
# next-steps item 2, the crash-fuzz-coverage half of the gap (the parse-
# time VERDICT-correctness half lives in `harness/swe/alias_effects.py`'s
# `ExtendedEffectGen`, see `test_swe_alias_effects.py`).

def test_generator_now_emits_rand_calls():
    """Mirrors `test_generator_now_emits_guess_family_calls` above: a
    coverage guard confirming `rand` is actually reachable from the
    grammar-directed generator (bare `rand()`/`rand(x)` calls, or a
    `let x = rand` alias later called through), not just theoretically
    wired into `BUILTIN_ARITY`."""
    rand_re = re.compile(r"\brand\b")
    seen = sum(1 for i in range(200) if rand_re.search(ProgramGen(i).program()))
    assert seen >= 15, seen


def test_rand_builtin_is_total_and_seed_reproducible_under_fuzz():
    """`rand()` must be TOTAL (never raises) like every other builtin, and
    — since v0.14.8 made it a REPRODUCIBLE draw from a per-`Interpreter`
    seeded stream rather than true entropy, specifically so the fuzzer's
    own differential oracles keep working — two fresh runs of the exact
    same source at the same default seed must agree exactly, not just both
    merely succeed."""
    from swe.fuzz import _import_whence
    Interpreter, _, _, _, full_show = _import_whence()
    src = ('let a = rand()\n'
           'let b = rand()\n'
           'print(str(a) + "," + str(b))\n')
    o1 = run_program(src)
    o2 = run_program(src)
    assert o1.kind == "ok" and o2.kind == "ok", (o1, o2)
    v1 = full_show(Interpreter().run(src))
    v2 = full_show(Interpreter().run(src))
    assert v1 == v2, (v1, v2)


def test_effect_tag_sets_now_include_random_combinations():
    """Round 299: `EFFECT_TAG_SETS` gained four `random`-inclusive
    combinations alongside the pre-existing `io`/`net` ones, so a generated
    `effects [...]` clause can actually GRANT `rand`'s own tag, not just
    the always-denied `net`-only path."""
    from swe.fuzz import EFFECT_TAG_SETS
    assert EFFECT_TAG_SETS == ("[]", "[io]", "[net]", "[io, net]", "[random]",
                                "[io, random]", "[net, random]", "[io, net, random]")


# =========================================================== round 323 ==
# `trunc()` (v0.17, round 318) joined `BUILTIN_ARITY` this round, closing
# the gap named in round 318's own next-steps item 6 (repeated in every
# SWE-loop(D)-adjacent round's list through 322).

def test_generator_now_emits_trunc_calls():
    """Mirrors `test_generator_now_emits_rand_calls` above: a coverage
    guard confirming `trunc` is actually reachable from the grammar-
    directed generator, not just theoretically wired into
    `BUILTIN_ARITY`.

    Round 337 sample-size note (shared by the five guards its audit found
    sitting under 1.2 sd above their own floor -- trunc, param-call, and
    the three shape builtins): these floors used to be measured at n=200,
    where the EXPECTED count sat at or barely above the floor, so any
    perturbation of the generator's random stream failed them.
    `param-call`'s margin was +0.18 sd -- a coin flip. Round 337's
    `_typed_tail_chain` was such a perturbation: it left the underlying
    rates alone (measured at n=2000 before and after -- trunc 6.4% ->
    6.8%, param-call 8.0% -> 7.7%, rand 34.6% -> 35.6%, sqrt 13.5% ->
    13.2%) and still failed two of them. Generation is cheap (1000
    programs in 0.12s), so these now measure at n=2000 with the floor at
    roughly HALF the measured rate -- which is what "reachable at a real
    rate" actually claims, and can only fail if the rate really halves.
    """
    trunc_re = re.compile(r"\btrunc\(")
    seen = sum(1 for i in range(2000) if trunc_re.search(ProgramGen(i).program()))
    assert seen >= 60, seen        # ~5.8% measured (round 337), floor at half


def test_trunc_builtin_is_total_under_fuzz_inputs():
    """`trunc` must be TOTAL like every other builtin across the input
    shapes the generic `call()` fallback can hand it: numbers (positive,
    negative, already-int, huge-overflowing-exponent), and the non-numeric
    types that should propagate to a miss instead. Also the regression
    case for round 323's own `interp.py` fix: `trunc(1e400)` used to be an
    uncaught host `OverflowError` (`int(inf)`), reachable ONLY via a
    contrived huge-digit-string literal until this round's lexer fix
    (`1e400` was previously unparseable as a single token at all -- see
    `test_lexer.py`'s `test_exponent_literal_is_one_float_token`) made it
    trivially reachable."""
    cases = ["5", "-5", "3.7", "-3.7", "0", "1e400", "-1e400", "1e5",
             '"abc"', "true", "[1, 2]", "@{a: 1}"]
    for c in cases:
        src = "let x = trunc(%s) rescue -999\nprint(str(x))\n" % c
        o = run_program(src)
        assert o.kind == "ok", (c, o.kind, o.exc_type, o.message)


def test_oracle_classifies_ok_parse_error_and_crash(monkeypatch):
    assert run_program("let x = 1 + 2\nprint(x)\n").kind == "ok"
    assert run_program("let x = \n").kind == "parse_error"
    assert run_program('let s = "unterminated\n').kind == "lex_error"
    # deep nesting is a clean parse error since whence v0.4, not a crash
    o = run_program("let p = " + "(" * 400 + "1" + ")" * 400 + "\n")
    assert o.kind == "parse_error" and "nested" in o.message
    assert run_program(CRASH_PROGRAM).kind == "ok"
    original = install_crash("whence.interp", WHENCE_ROOT)
    try:
        o = run_program(CRASH_PROGRAM)
    finally:
        sys.modules["whence.interp"].deep_eq = original
    assert o.kind == "crash" and o.exc_type == "RecursionError" and o.phase == "run"
    assert run_program(CRASH_PROGRAM).kind == "ok"      # restored


def test_oracle_timeout_is_reported_not_raised():
    src = "fn loop(n) { loop(n + 1) }\nlet r = loop(0)\n"
    o = run_program(src, max_depth=10 ** 7, timeout_s=0.2)
    assert o.kind == "timeout"


def test_signature_of_recursion_error_is_stack_depth_independent():
    src = CRASH_PROGRAM
    original = install_crash("whence.interp", WHENCE_ROOT)
    try:
        s1 = signature(run_program(src))

        def deeper(k):
            return signature(run_program(src)) if k == 0 else deeper(k - 1)
        assert s1 == deeper(25)
    finally:
        sys.modules["whence.interp"].deep_eq = original
    # the cycle names the recurring function; the single-occurrence entry
    # frames (binop, _drive, …) are excluded
    assert s1[2] == "cycle:deep_eq" and s1[3] == "run"


def test_ddmin_lines_keeps_minimal_subset():
    lines = ["a", "b", "c", "d", "e", "f"]
    keep = lambda ls: "c" in ls and "e" in ls
    assert sorted(ddmin_lines(lines, keep)) == ["c", "e"]


def test_minimize_ints_binary_searches_each_literal():
    keep = lambda line: int(line.split()[-1]) >= 37
    assert _minimize_ints("let n = 1000", keep) == "let n = 37"


def test_shrink_reduces_a_real_crasher():
    src = ("let junk = 1\n" + "let p = " + "(" * 400 + "1" + ")" * 400 + "\n"
           + "print(junk)\nlet more = [1, 2]\n")
    sig = signature(run_program(src))
    small = shrink(src, lambda c: signature(run_program(c)) == sig)
    assert small.count("\n") == 1 and small.count("(") < 400
    assert signature(run_program(small)) == sig


def test_shrink_returns_none_when_predicate_false_on_input():
    assert shrink("let a = 1\n", lambda c: False) is None


def test_campaign_groups_crashes_by_signature(tmp_path):
    camp = fuzz(seed=2, n=40, do_shrink=False)
    assert camp.programs == 40
    assert sum(camp.counts.values()) == 40
    for sig, cr in camp.crashers.items():
        assert signature(run_program(cr.src)) == sig


# ============================================ v0.14.9/10 (round 305) ======
# `param_call_fns` (fuzz.py's own "Round 305" `__init__` comment) closes the
# crash-fuzz-coverage half of round 300/302's own "passing a builtin as a
# function ARGUMENT" gap — `ProgramGen`'s generic grammar never previously
# called a bare local PARAM as a function at all, so this shape (a fn body
# calling one of its own params directly, then a call site passing an
# effectful name for exactly that param) was unreachable before this round.

def test_generator_now_emits_param_call_shape():
    """Coverage guard, mirroring `test_generator_now_emits_rand_calls`:
    confirms the `pN(...)` call-your-own-param shape is actually reachable
    at a real rate, not just theoretically wired into `param_call_fns`.
    The "~21% (42/200)" this docstring claimed when round 311 wrote it no
    longer holds: round 337 measures 7.85% at n=4000.

    Round 337 sample-size note (shared by the five guards its audit found
    sitting under 1.2 sd above their own floor -- trunc, param-call, and
    the three shape builtins): these floors used to be measured at n=200,
    where the EXPECTED count sat at or barely above the floor, so any
    perturbation of the generator's random stream failed them.
    `param-call`'s margin was +0.18 sd -- a coin flip. Round 337's
    `_typed_tail_chain` was such a perturbation: it left the underlying
    rates alone (measured at n=2000 before and after -- trunc 6.4% ->
    6.8%, param-call 8.0% -> 7.7%, rand 34.6% -> 35.6%, sqrt 13.5% ->
    13.2%) and still failed two of them. Generation is cheap (1000
    programs in 0.12s), so these now measure at n=2000 with the floor at
    roughly HALF the measured rate -- which is what "reachable at a real
    rate" actually claims, and can only fail if the rate really halves.
    """
    pat = re.compile(r"\bp\d+\(")
    seen = sum(1 for i in range(2000) if pat.search(ProgramGen(i).program()))
    assert seen >= 80, seen        # ~7.9% measured (round 337), floor at half


def test_param_call_shape_is_total_under_fuzz():
    """The real regression for this shape: 800 generated programs (a mix
    of NAMED-fn and `let`-bound-anonymous-fn param-call bodies, plus call
    sites deliberately targeting the tracked param position with an
    effectful argument) must all stay TOTAL — `ok`, `parse_error`,
    `lex_error`, or `timeout`, never `crash` — the same invariant this
    module's whole docstring polices for every other shape."""
    for i in range(800):
        o = run_program(ProgramGen(i, stress_rate=0.15).program(), timeout_s=2.0)
        assert o.kind != "crash", (i, o.exc_type, o.message)


def test_param_call_argument_check_reports_parse_error_not_crash():
    """A hand-written grant/deny pair (mirrors `tests/test_v14.py`'s own
    `test_argument_passed_to_a_directly_called_param_is_{checked,rejected_
    when_not_permitted}`): the GRANTED case must run clean, the DENIED case
    must be a clean `parse_error`, not a crash — confirming the new check's
    own ParseError path is exercised as a normal, expected outcome by the
    fuzz harness's oracle, not something that would be misclassified."""
    granted = run_program(
        'fn apply(f) effects [io] { f(1) }\napply(print)\ncheck "ok": true\n')
    assert granted.kind == "ok", granted
    denied = run_program(
        'fn silent(f) effects [] { f(1) }\nsilent(print)\n')
    assert denied.kind == "parse_error", denied
    denied_anon = run_program(
        'let g = fn(f) effects [] { f(1) }\ng(print)\n')
    assert denied_anon.kind == "parse_error", denied_anon


# ========================================= v0.14.11/v0.14.12 (round 311) ===

def test_generator_now_emits_param_rename_call_shape():
    """Coverage guard, mirroring `test_generator_now_emits_param_call_
    shape`: confirms the v0.14.11 rename-then-call shape (`let gN = pM`
    immediately followed by a call through `gN`) is actually reachable at
    a real rate from `ProgramGen`'s own grammar, not just theoretically
    wired into `_param_rename_call_body`."""
    pat = re.compile(r"let g\d+ = p\d+\n")
    seen = sum(1 for i in range(400) if pat.search(ProgramGen(i).program()))
    assert seen >= 15, seen


def test_param_rename_call_shape_is_total_under_fuzz():
    """The real regression for this shape: 800 generated programs (a mix
    of NAMED-fn and `let`-bound-anonymous-fn bodies that call one of their
    own params through a rename, plus call sites deliberately targeting
    the tracked param position with an effectful argument) must all stay
    TOTAL, never `crash`."""
    for i in range(800):
        o = run_program(ProgramGen(i, stress_rate=0.15).program(), timeout_s=2.0)
        assert o.kind != "crash", (i, o.exc_type, o.message)


def test_generator_now_emits_return_param_shape():
    """Coverage guard: confirms the v0.14.12 `fn apply(f) { f }`-shaped
    body (a bare-param tail) is actually reachable from `ProgramGen`'s own
    grammar, not just theoretically wired into `_return_param_body`/
    `return_param_fns`."""
    seen = 0
    for i in range(400):
        g = ProgramGen(i)
        g.program()
        if g.return_param_fns:
            seen += 1
    assert seen >= 10, seen


def test_return_param_shape_is_total_under_fuzz():
    """The real regression for this shape: 800 generated programs (a mix
    of NAMED-fn and `let`-bound-anonymous-fn bodies that return one of
    their own params unchanged, plus both consumption shapes -- a `let`-
    bound call and a no-`let` chained call -- deliberately targeting the
    returned param's own position with an effectful argument) must all
    stay TOTAL, never `crash`."""
    for i in range(800):
        o = run_program(ProgramGen(i, stress_rate=0.15).program(), timeout_s=2.0)
        assert o.kind != "crash", (i, o.exc_type, o.message)


def test_return_param_passthrough_reports_parse_error_not_crash():
    """A hand-written grant/deny pair mirroring `tests/test_v14.py`'s own
    v0.14.12 corpus: the GRANTED case must run clean, the DENIED case must
    be a clean `parse_error`, not a crash -- both the `let`-bound and the
    no-`let` chained-call consumption shapes."""
    granted = run_program(
        'fn apply(f) { f }\nfn user() effects [io] { let g = apply(print)\n g(1) }\n'
        'user()\ncheck "ok": true\n')
    assert granted.kind == "ok", granted
    denied = run_program(
        'fn apply(f) { f }\nfn user() effects [] { let g = apply(print)\n g(1) }\n'
        'user()\n')
    assert denied.kind == "parse_error", denied
    denied_chain = run_program(
        'fn apply(f) { f }\nfn user() effects [] { apply(print)(1) }\nuser()\n')
    assert denied_chain.kind == "parse_error", denied_chain


# ==================================== v0.14.13 (round 312, coverage 317) ===
# No new list -- `_param_forward_body` reuses `self.param_call_fns` itself
# (see its own docstring), closing the crash-fuzz-coverage half of round
# 312's v0.14.13 gap: an argument forwarded through a SECOND function call,
# before landing in a directly-called param (`_check_param_forwarding`).
# `ProgramGen`'s generic grammar never
# previously placed a bare local PARAM as an ARGUMENT to another tracked
# fn's call at all -- every existing consumer of a param only ever called it
# directly (`_param_call_body`) or through a same-body rename (`_param_
# rename_call_body`), so this specific "hand it to someone else who calls
# it" shape was genuinely unreachable before this round.

def test_generator_now_emits_param_forward_shape():
    """Coverage guard, mirroring `test_generator_now_emits_param_rename_
    call_shape`: confirms `_param_forward_body` is actually reachable at a
    real rate, not just theoretically wired in. A source-text regex can't
    distinguish a forwarded argument (a bare `pN` name passed to a tracked
    fn's call) from any other bare-name argument, so this instruments
    `ProgramGen._param_forward_body` itself with a counting wrapper instead
    -- the same reasoning `test_swe_alias_effects.py`'s own `test_extended_
    generator_reaches_param_forwarding_fact` already gives for the oracle
    side. Measured 25/6000 (~0.42%) in this round's own manual scaling
    check -- rarer than the other shapes in this file since it needs an
    EARLIER fn already registered in `self.param_call_fns` before the 34%
    draw is even offered."""
    from swe.fuzz import ProgramGen as G
    orig = G._param_forward_body
    seen = [0]

    def wrapped(self, params, *target):
        seen[0] += 1
        return orig(self, params, *target)
    G._param_forward_body = wrapped
    try:
        n = 6000
        for i in range(n):
            G(i).program()
    finally:
        G._param_forward_body = orig
    assert seen[0] >= 10, seen[0]


def test_param_forward_shape_is_total_under_fuzz():
    """The real regression for this shape: 800 generated programs (a mix of
    NAMED-fn and `let`-bound-anonymous-fn bodies that forward one of their
    own params into an already-tracked fn's own called-param position, plus
    call sites deliberately targeting the (now doubly-tracked) fn with an
    effectful argument) must all stay TOTAL, never `crash`."""
    for i in range(800):
        o = run_program(ProgramGen(i, stress_rate=0.15).program(), timeout_s=2.0)
        assert o.kind != "crash", (i, o.exc_type, o.message)


def test_param_forwarding_reports_parse_error_not_crash():
    """A hand-written grant/deny pair mirroring `tests/test_v14.py`'s own
    `test_param_forwarded_to_second_function_that_calls_it_is_now_checked`:
    the GRANTED case must run clean, the DENIED case must be a clean
    `parse_error`, not a crash -- `outer`'s own body never calls `f`
    directly, it forwards it to `inner`, which does."""
    granted = run_program(
        'fn inner(g) effects [io] { g(1) }\n'
        'fn outer(f) effects [io] { inner(f) }\n'
        'outer(print)\ncheck "ok": true\n')
    assert granted.kind == "ok", granted
    denied = run_program(
        'fn inner(g) effects [io] { g(1) }\n'
        'fn outer(f) effects [] { inner(f) }\n'
        'outer(print)\n')
    assert denied.kind == "parse_error", denied


# =========================================================== round 335 ==
# `matches`/`shapeof`/`typed` (v0.12, rounds 122-128) joined `BUILTIN_ARITY`
# this round -- the last three of `interp._make_builtin_table()`'s 36
# registered builtins the generator could not reach. Found by running the
# re-diff round 323's own next-steps item 3 asked for ("re-diff
# BUILTIN_ARITY's keys against whence/interp.py's actual registered
# builtins before assuming there are no gaps"). Both bugs the totality
# sweep below then found were real and are fixed in `whence/interp.py`.

SHAPE_BUILTINS = ("matches", "shapeof", "typed")


def test_builtin_arity_covers_every_registered_host_builtin():
    """The check itself, kept as a test so the next builtin added to
    `whence/interp.py` fails HERE instead of silently going un-fuzzed for
    another few hundred rounds. `trunc` went 5 rounds unnoticed; these
    three went ~200."""
    sys.path.insert(0, WHENCE_ROOT)
    from whence import interp as _interp     # noqa: PLC0415
    registered = set(n for n, _ in _interp._make_builtin_table())
    assert set(BUILTIN_ARITY) == registered, {
        "unfuzzed": sorted(registered - set(BUILTIN_ARITY)),
        "not a builtin": sorted(set(BUILTIN_ARITY) - registered)}


def test_generator_now_emits_the_shape_builtins():
    """Coverage guard, mirroring `test_generator_now_emits_trunc_calls`.

    Round 337 sample-size note (shared by the five guards its audit found
    sitting under 1.2 sd above their own floor -- trunc, param-call, and
    the three shape builtins): these floors used to be measured at n=200,
    where the EXPECTED count sat at or barely above the floor, so any
    perturbation of the generator's random stream failed them.
    `param-call`'s margin was +0.18 sd -- a coin flip. Round 337's
    `_typed_tail_chain` was such a perturbation: it left the underlying
    rates alone (measured at n=2000 before and after -- trunc 6.4% ->
    6.8%, param-call 8.0% -> 7.7%, rand 34.6% -> 35.6%, sqrt 13.5% ->
    13.2%) and still failed two of them. Generation is cheap (1000
    programs in 0.12s), so these now measure at n=2000 with the floor at
    roughly HALF the measured rate -- which is what "reachable at a real
    rate" actually claims, and can only fail if the rate really halves.
    """
    corpus = [ProgramGen(i).program() for i in range(2000)]
    for name in SHAPE_BUILTINS:
        pat = re.compile(r"\b%s\(" % name)
        seen = sum(1 for src in corpus if pat.search(src))
        assert seen >= 50, (name, seen)   # 5.1-5.9% measured, floor at half


def test_generator_emits_shape_declarations():
    """Round 347 inverted `test_generator_emits_no_shape_declaration`.

    That test pinned "the grammar never emits a `shape` statement" and
    gave the reason: "the guest parser has no `shape` support at all".
    Round 338 gave `self_eval.lang`/`self_host.lang` the `shape` statement
    and `swe/guest.py`'s docstring recorded that the restriction had become
    "a GENERATOR choice rather than a guest limitation" — but this test,
    `fuzz.py`'s own comment, and `TYPE_TAGS`'s comment all still asserted
    the old reason, so the choice was never revisited. Measured before the
    change: 0 of 400 generated programs contained the word `shape`, which
    left `_closure_spec`'s NameRef branch, both of `_check_contract`'s
    pre-`_type_match` guards and the guest's `resolve_spec` reachable only
    from the hand-written corpus.

    Floor at half the measured rate, per
    `test_generator_now_emits_the_shape_builtins`'s own sample-size note.
    """
    corpus = [ProgramGen(i).program() for i in range(2000)]
    decl = re.compile(r"(^|\n)shape S\d+ = @\{")
    ann = re.compile(r"(->|:) S\d+\b")
    # round 359 split the shadow recipe by PLACEMENT: `{ let S1 =` is the
    # original (shadow first), `\n  let S1 =` is the new late one (shadow
    # after the annotated fn, the only placement that can separate a spec
    # resolved at closure creation from one resolved per call). Both floors
    # are load-bearing and mean different things — the EARLY half is what
    # reaches `_check_contract`'s `not _spec_ok` guard, the LATE half is
    # what reaches round 342 §7's hazard.
    shadow = re.compile(r"\{ let S\d+ =")
    late_shadow = re.compile(r"\n  let S\d+ =")
    n_decl = sum(1 for s in corpus if decl.search(s))
    n_ann = sum(1 for s in corpus if ann.search(s))
    n_shadow = sum(1 for s in corpus if shadow.search(s))
    n_late = sum(1 for s in corpus if late_shadow.search(s))
    assert n_decl >= 150, n_decl        # ~36% measured
    assert n_ann >= 90, n_ann           # ~20% measured
    assert n_shadow >= 55, n_shadow     # ~6.6% measured (was ~12% undivided)
    assert n_late >= 55, n_late         # ~6.1% measured


def test_declared_shape_annotations_are_total():
    """Every program the new shape recipes can produce stays total: a
    shape annotation is a MISS when it does not match, never a host
    exception. The `not _spec_ok` branch (`_shadowed_shape_stmt`) is the
    one this most needs to hold for — round 344 measured it raising
    `AttributeError: 'int' object has no attribute 'fields'` straight out
    of the interpreter before it added the guard."""
    from swe.fuzz import SHADOW_BINDINGS
    for bind in SHADOW_BINDINGS:
        for ann in ("fn g() -> S1 { 1 }\n  g()",
                    "fn g(q: S1) { q }\n  g(1)"):
            src = ("shape S1 = @{a: num}\n"
                   "fn h() { let S1 = %s\n  %s }\n"
                   "let r = h()\n"
                   "print(str(r))\n") % (bind, ann)
            o = run_program(src)
            assert o.kind == "ok", (bind, ann, o.kind, o.exc_type, o.message)
            assert "object at 0x" not in "".join(o.out), o.out


def test_shape_witnesses_really_satisfy_their_shape():
    """`_witness_for` exists so the annotation SUCCESS path is not dead —
    the branch where `_check_contract` returns its input unchanged and
    leaves no node in the why-tree at all. If a witness stopped matching,
    every generated shape annotation would quietly become a miss and the
    coverage would look identical from the outside."""
    for seed in range(60):
        g = ProgramGen(seed)
        for _ in range(3):
            g._shape_decl()
        for name in g.shape_names():
            src = ("\n".join("shape %s = @{%s}" % (
                       n, ", ".join("%s: %s" % (f, t) for f, t in fs))
                   for n, fs in g.shapes) +
                   "\nlet w = %s\n"
                   "fn f(p: %s) { p }\n"
                   "let r = f(w)\n"
                   "print(missed(r))\n" % (g._witness_for(name), name))
            o = run_program(src)
            assert o.kind == "ok", (seed, name, o.kind, o.message)
            assert list(o.out) == ["false"], (seed, name, g.shapes, o.out)


def test_program_recipe_has_no_subclass_fork():
    """Structural guard (round 347): no subclass of `ProgramGen` anywhere
    under `harness/` may define its own `program`.

    `GuestGen` used to carry a hand-copied `program`, so every recipe the
    base gained afterwards silently missed the guest differential. Round
    337's `_typed_tail_chain` went in that way and was invisible to the
    guest for ten rounds (0 of 400 guest programs contained one, measured
    round 347); round 347's shape declarations would have been the second
    instance the same day. Subclasses now override `keep_stmt`, which
    answers "keep this statement?" and cannot answer "which statements
    exist?".

    Asserted over the AST rather than by grep, for round 343's reason: a
    grep for a NAME cannot find a SHAPE, and the shape is "a class whose
    bases include ProgramGen and whose body defines program"."""
    import ast as _ast
    harness_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    offenders, subclasses = [], []
    for dirpath, _dirs, files in os.walk(harness_dir):
        if "__pycache__" in dirpath:
            continue
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, encoding="utf-8") as fh:
                tree = _ast.parse(fh.read(), path)
            for node in _ast.walk(tree):
                if not isinstance(node, _ast.ClassDef):
                    continue
                bases = [b.id for b in node.bases if isinstance(b, _ast.Name)]
                if "ProgramGen" not in bases:
                    continue
                subclasses.append(node.name)
                for item in node.body:
                    if isinstance(item, _ast.FunctionDef) and item.name == "program":
                        offenders.append("%s.%s (%s)" % (node.name, item.name, path))
    assert subclasses, "no ProgramGen subclass found -- the guard would be vacuous"
    assert not offenders, offenders


def test_shape_builtins_are_total_under_fuzz_inputs():
    """The regression for round 335's own two `interp.py` fixes, driven
    across the value/spec/label matrix the generator can now produce.

    `matches(@{a: 1}, @{a: 5})` used to be an uncaught host
    `AttributeError`: `_type_match` recursed into a nested field spec
    assuming a str-or-Record and got an int. A hand-built record spec is
    documented, first-class Whence (SPEC v0.12's "structural, not
    nominal"), so this needed no contrivance at all -- and `matches` is
    documented TOTAL, "never itself a miss, even on ... a malformed spec".
    """
    values = ["5", "-5", "3.7", "0", '"abc"', '""', "true", "[1, 2]", "[]",
              "@{a: 1}", "@{}", "@{a: @{b: 1}}", "fn(x) { x }", 'miss "no"',
              "len(1)", 'guess(1, 0.5, "m")', "range(3)"]
    for v in values:
        assert run_program("let x = shapeof(%s)\nprint(str(x))\n" % v).kind == "ok", v
        for s in SPEC_POOL:
            src = ("let a = matches(%s, %s)\n"
                   "let b = typed(%s, %s, \"L\") rescue -1\n"
                   "print(str([a, b]))\n") % (v, s, v, s)
            o = run_program(src)
            assert o.kind == "ok", (v, s, o.kind, o.exc_type, o.message)


def test_typed_label_pool_covers_the_non_string_label_miss():
    """`TYPED_LABELS` exists so the host's own "typed label must be a
    string" branch -- unreachable from a parameter guard, which always
    builds a `A.Str` label -- is fuzzed too."""
    for label in TYPED_LABELS:
        o = run_program('let x = typed(1, "num", %s) rescue -1\n'
                        'print(str(x))\n' % label)
        assert o.kind == "ok", (label, o.kind, o.message)


def test_a_non_string_shape_name_does_not_leak_a_python_repr():
    """`SPEC_POOL`'s `@{__shape: 5, a: "num"}` entry earns its place: a
    non-str `__shape` used to render through `%s` into the miss message,
    leaking the payload's Python repr and, for a Record/WList, its HEAP
    ADDRESS -- so two runs of one program disagreed and the determinism,
    fast_slow and direct oracles all fired. This is the fuzz-side pin;
    `languages/whence/tests/test_v12.py` holds the semantic one."""
    src = ('let r = typed(@{a: "z"}, @{__shape: @{q: 1}, a: "num"}, "L")\n'
           'print(join(reasons(r), "|"))\n')
    first = run_program(src)
    second = run_program(src)
    assert first.kind == "ok" and second.kind == "ok"
    assert first.out == second.out, (first.out, second.out)
    assert "object at 0x" not in "".join(first.out), first.out


def test_shape_builtin_programs_stay_total_end_to_end():
    """400 generated programs: total, never a crash -- the same invariant
    every other shape in this module polices. ~66/400 (16.5%) actually
    contain one of the three calls at this stress rate, measured; the floor
    below is set under that so ordinary RNG drift cannot flake it."""
    pat = re.compile(r"\b(matches|shapeof|typed)\(")
    seen = 0
    for i in range(400):
        src = ProgramGen(i, stress_rate=0.15).program()
        if pat.search(src):
            seen += 1
        o = run_program(src, timeout_s=2.0)
        assert o.kind != "crash", (i, o.exc_type, o.message)
    assert seen >= 40, seen
