"""swe.fuzz: generator determinism, oracle classification, shrinker."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe.fuzz import (ProgramGen, run_program, signature, shrink, ddmin_lines,
                      _minimize_ints, fuzz, WHENCE_ROOT, GUESS_CONFIDENCES)
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
    Measured ~21% (42/200) in this round's own manual scaling check."""
    pat = re.compile(r"\bp\d+\(")
    seen = sum(1 for i in range(200) if pat.search(ProgramGen(i).program()))
    assert seen >= 15, seen


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
