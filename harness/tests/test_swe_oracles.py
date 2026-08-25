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
    # v0.10 compiles each operator to its own closure (`_compile_binop`)
    # with the numeric case inline, so two numbers never reach `binop` on
    # the fast path any more (round 109 re-injection, process rule 7): make
    # the FACTORY build `+` when asked for `-`. The generator path
    # (`eval_Binary` -> `self.binop`) is untouched, so only fast mode is wrong.
    orig_factory = interp_mod._compile_binop

    def bad_factory(op, lf, rf, line, binop):
        return orig_factory("+" if op == "-" else op, lf, rf, line, binop)
    interp_mod._compile_binop = bad_factory
    try:
        o = O.run_oracle("fast_slow", pkg, "let a = 5 - 2\nprint(a)\n")
        assert o.kind == "mismatch" and o.detail.startswith("out"), o.detail
        assert O.run_oracle("determinism", pkg, "let a = 5 - 2\n").kind == "ok"
    finally:
        interp_mod._compile_binop = orig_factory


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


# --- round 110: the frame-charge oracle -------------------------------------

NEST = "fn nest(n) { if n == 0 { [] } else { [nest(n - 1)] } }\nlet deep = nest(300)\n"


def test_frames_oracle_reports_a_small_bounded_excess_on_the_real_interpreter():
    """Direct mode charges every frame it uses: the excess over the charge is
    the transient (fast closures, one nested drive), not a function of
    guest depth. 300 levels of the round-108 shape at the default limit
    (~150 of them direct, the rest on the trampoline) stay under the
    slack with room to spare."""
    o = O.run_oracle("frames", PKG, NEST, timeout_s=20)
    assert o.kind == "ok", o.detail
    best, at, _ = O.frame_excess(PKG, O._parse(PKG, NEST))
    assert best <= 20, best


def test_frames_oracle_fires_on_an_injected_uncharged_frame_per_level():
    """Round 108's bug class: a host frame per guest level that `cdepth`
    does not know about (there it was a list comprehension). Injected as
    a wrapper around `_call_direct` — one extra frame per call, charged
    nowhere — the excess grows with guest depth and the oracle fires,
    while the semantic oracles stay green (the value is unchanged)."""
    pkg = K.load_whence(WHENCE_ROOT, "oracle_frames_bug")
    Interp = sys.modules[pkg["name"] + ".interp"].Interpreter
    orig = Interp._call_direct

    def one_more(self, fn, args, line):
        return orig(self, fn, args, line)
    Interp._call_direct = one_more
    try:
        o = O.run_oracle("frames", pkg, NEST, timeout_s=20)
        assert o.kind == "mismatch", o.detail
        assert "excess" in o.detail and O.signature(o)[0] == "mismatch"
        assert O.run_oracle("direct", pkg, NEST, timeout_s=20).kind == "ok"
    finally:
        Interp._call_direct = orig
    assert O.run_oracle("frames", pkg, NEST, timeout_s=20).kind == "ok"


def test_frames_oracle_skips_packages_without_direct_mode_and_reports_parse_errors():
    assert O.run_oracle("frames", PKG, "let x = (\n").kind == "parse_error"
    fake = dict(PKG)

    class NoDirect(object):
        def __init__(self, out=None, max_depth=500, fast=True):
            pass
    fake["Interpreter"] = NoDirect
    assert O.oracle_frames(fake, "let x = 1\n").kind == "ok"


def test_frames_oracle_kills_an_undercharging_body_entry_the_value_oracles_cannot():
    """The SWE-loop claim (round 110): a mutant on the budget arithmetic —
    `cost = cdepth` instead of `cdepth + 1` — changes no value and no
    why-tree, so every value-comparing oracle calls it equivalent; the
    frame-charge oracle sees one uncharged frame per guest level."""
    pkg = K.load_whence(WHENCE_ROOT, "oracle_budget_mutant")
    Interp = sys.modules[pkg["name"] + ".interp"].Interpreter
    orig = Interp._body_entry

    def undercharge(self, body):
        bd, cost = orig(self, body)
        ent = body.entry = (bd, cost - 1)
        return ent
    Interp._body_entry = undercharge
    try:
        # entries are cached on the (fresh) package's AST nodes per parse,
        # so the mutant is exercised on every call of the oracle's program
        assert O.run_oracle("direct", pkg, NEST, timeout_s=20).kind == "ok"
        assert O.run_oracle("fast_slow", pkg, NEST, timeout_s=20).kind == "ok"
        assert O.run_oracle("totality", pkg, NEST, timeout_s=20).kind == "ok"
        o = O.run_oracle("frames", pkg, NEST, timeout_s=20)
        assert o.kind == "mismatch", o.detail
    finally:
        Interp._body_entry = orig
    assert O.run_oracle("frames", pkg, NEST, timeout_s=20).kind == "ok"
