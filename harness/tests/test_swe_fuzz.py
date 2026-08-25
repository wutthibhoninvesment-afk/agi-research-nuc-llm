"""swe.fuzz: generator determinism, oracle classification, shrinker."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe.fuzz import (ProgramGen, run_program, signature, shrink, ddmin_lines,
                      _minimize_ints, fuzz, WHENCE_ROOT)
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
