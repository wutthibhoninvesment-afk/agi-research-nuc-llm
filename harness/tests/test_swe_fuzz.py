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
