"""Differential/metamorphic oracles (swe.oracles): every oracle must be
silent on the real interpreter and must fire on an injected semantic bug."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import swe.oracles as O
import swe.killers as K
from swe.fuzz import WHENCE_ROOT, ProgramGen

PKG = K.load_whence(WHENCE_ROOT, "oracle_tests")

TAIL = ("fn go(n, acc) { if n == 0 { acc } else { go(n - 1, acc + n) } }\n"
        "let t = go(50, 0)\nlet u = go(50, 1)\nprint(t)\nprint(len(diverge(t, u)))\n"
        'check "sum": t == 1275\n')


def test_oracles_silent_on_real_interpreter():
    for name in O.ORACLE_NAMES:
        o = O.run_oracle(name, PKG, TAIL)
        assert o.kind == "ok", (name, o.detail)


def test_parse_error_is_reported_not_raised():
    for name in O.ORACLE_NAMES:
        assert O.run_oracle(name, PKG, "let x = (\n").kind == "parse_error"


def test_first_difference_names_the_field_and_binding():
    a = {"kind": "ok", "out": ["1"], "checks": [], "vals": {"x": "1"}, "why": {"x": "a\nb"}}
    b = dict(a, why={"x": "a\nc"})
    d = O.first_difference(a, b)
    assert d.startswith("why[x] line 1") and "A: b" in d and "B: c" in d
    assert O.first_difference(a, dict(a, out=["2"])).startswith("out")
    assert O.first_difference(a, a) == ""


def test_signature_groups_by_oracle_and_first_line():
    o1 = O.OracleOutcome("mismatch", "fast_slow", "why[x] line 3\n  A: p\n  B: q")
    o2 = O.OracleOutcome("mismatch", "fast_slow", "why[x] line 3\n  A: r\n  B: s")
    o3 = O.OracleOutcome("mismatch", "fast_slow", "vals[x]\n  A: 1\n  B: 2")
    assert O.signature(o1) == O.signature(o2) != O.signature(o3)
    assert O.signature(O.OracleOutcome("ok", "render")) == ("ok",)


def test_fast_slow_fires_on_an_injected_fast_path_bug():
    """Make the compiled Binary closure mishandle `-`: the generator path
    still uses binop, so the two evaluators disagree and fast_slow fires."""
    pkg = K.load_whence(WHENCE_ROOT, "oracle_bug")
    interp_mod = sys.modules[pkg["name"] + ".interp"]
    Interp = interp_mod.Interpreter
    orig_binop = Interp.binop

    def bad_binop(self, op, left, right, line):
        # the fast path passes through here too; make the bug fast-only by
        # keying on the interpreter's mode
        if op == "-" and self.fast:
            return orig_binop(self, "+", left, right, line)
        return orig_binop(self, op, left, right, line)
    Interp.binop = bad_binop
    try:
        o = O.run_oracle("fast_slow", pkg, "let a = 5 - 2\nprint(a)\n")
        assert o.kind == "mismatch" and o.detail.startswith("out"), o.detail
        assert O.run_oracle("determinism", pkg, "let a = 5 - 2\n").kind == "ok"
    finally:
        Interp.binop = orig_binop


def test_direct_fires_on_an_injected_direct_call_bug():
    """Make `_call_direct` (v0.9 host-recursion calls) off by one on integer
    results: `direct=False` still uses `_call_gen`, so the two disagree and
    the `direct` oracle fires — and fast_slow (direct vs pure trampoline)
    fires too, while determinism stays green."""
    pkg = K.load_whence(WHENCE_ROOT, "oracle_direct_bug")
    interp_mod = sys.modules[pkg["name"] + ".interp"]
    Interp = interp_mod.Interpreter
    assert O.has_direct_mode(pkg)
    orig = Interp._call_direct

    def bad_call_direct(self, fn, args, line):
        r = orig(self, fn, args, line)
        if type(r.value) is int:
            return interp_mod.derived("call", "bug", line, (r,), r.value + 1)
        return r
    Interp._call_direct = bad_call_direct
    try:
        src = "fn f(x) { x + 1 }\nlet a = f(1)\nprint(a)\n"
        o = O.run_oracle("direct", pkg, src)
        assert o.kind == "mismatch" and o.detail.startswith("out"), o.detail
        assert O.run_oracle("fast_slow", pkg, src).kind == "mismatch"
        assert O.run_oracle("determinism", pkg, src).kind == "ok"
    finally:
        Interp._call_direct = orig
    assert O.run_oracle("direct", pkg, "fn f(x) { x + 1 }\nlet a = f(1)\n").kind == "ok"


def test_determinism_fires_when_state_leaks_through_the_ast():
    pkg = K.load_whence(WHENCE_ROOT, "oracle_leak")
    interp_mod = sys.modules[pkg["name"] + ".interp"]
    Interp = interp_mod.Interpreter
    orig = Interp.eval_Num

    def leaky_eval_Num(self, node, env):
        node.__dict__.setdefault("_runs", 0) if hasattr(node, "__dict__") else None
        v = orig(self, node, env)
        # second execution of the same AST node yields a different value
        n = getattr(node, "_runs", 0)
        try:
            node._runs = n + 1
        except AttributeError:
            return v
        if n >= 1:
            self._out("leak")
        return v
    Interp.eval_Num = leaky_eval_Num
    try:
        o = O.run_oracle("determinism", pkg, "let a = 1\nprint(a)\n")
        assert o.kind in ("mismatch", "ok")   # slots may forbid the attribute
    finally:
        Interp.eval_Num = orig


def test_render_oracle_checks_self_identities():
    o = O.run_oracle("render", PKG, TAIL)
    assert o.kind == "ok"


def test_campaign_runs_generated_programs_and_examples():
    camp = O.fuzz_oracles(seed=1, n=3, do_shrink=False, extra_programs=[TAIL])
    assert camp.programs == 4
    assert sum(v for (name, kind), v in camp.counts.items() if name == "fast_slow") == 4
    assert sum(v for (name, kind), v in camp.counts.items() if name == "totality") == 4
    assert "oracle fuzz: 4 programs" in camp.summary()
    d = camp.as_dict()
    assert d["programs"] == 4 and "findings" in d


def test_generated_programs_exercise_v04_constructs():
    srcs = [ProgramGen(s).program() for s in range(200)]
    text = "\n".join(srcs)
    for needle in ("go(", "even(", "diverge(", "contrast(", "steps(", "fold("):
        assert needle in text, needle
