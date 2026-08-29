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


# --- tail_transparency (round 337) -------------------------------------------
#
# The oracle form of round 336's (language C) finding: a `-> Type` contract
# reached through a TAIL call was blamed outermost-first and reported the
# outer call's line, where the same chain lifted out of tail position blamed
# the innermost contract at the tail call's own line. Round 336 fixed both
# and asked (its next-steps item 2) for the transform as a real oracle.

TAIL_CHAIN = ("fn c() -> bool { 1 }\n"
              "fn b() -> str { c() }\n"
              "fn a() -> list { b() }\n"
              "let r = a()\n")

TAIL_LOOP = ('fn f(n) -> num { if n == 0 { "s" } else { f(n - 1) } }\n'
             "let r = f(2)\n")


def _interp_mod(pkg):
    return sys.modules[pkg["name"] + ".interp"]


def test_tail_transparency_silent_on_typed_chains_and_loops():
    for src in (TAIL_CHAIN, TAIL_LOOP):
        o = O.run_oracle("tail_transparency", PKG, src)
        assert o.kind == "ok", (src, o.detail)
        assert "tail calls" in o.detail          # it really did compare


def test_tail_transparency_reports_when_there_is_nothing_to_compare():
    o = O.run_oracle("tail_transparency", PKG, "let x = 1 + 2\n")
    assert o.kind == "ok" and o.detail == "no tail calls"


def test_tail_transparency_fires_on_round_335_outermost_first_blame_order():
    """Restore round 335's order (the chain's contracts checked outermost
    first) and the oracle must report the WRONG FUNCTION being blamed."""
    pkg = K.load_whence(WHENCE_ROOT, "oracle_tail_order_bug")
    m = _interp_mod(pkg)
    orig = m._check_chain_rets

    def outermost_first(result, chain_rets):
        for spec, label, line in chain_rets:      # round 336 walks this backwards
            result = m._check_ret(result, spec, label, line)
        return result
    m._check_chain_rets = outermost_first
    try:
        o = O.run_oracle("tail_transparency", pkg, TAIL_CHAIN)
        assert o.kind == "mismatch", o.detail
        assert "vals[r]" in o.detail, o.detail
        # the tail form blames `b`, the lifted form blames `c`
        assert "return value of b" in o.detail and "return value of c" in o.detail
        # the three existing value oracles are structurally blind to this:
        # all of them compare the interpreter against itself with tail
        # position UNCHANGED, so both sides make the same wrong choice
        for name in ("fast_slow", "direct", "determinism"):
            assert O.run_oracle(name, pkg, TAIL_CHAIN).kind == "ok", name
    finally:
        m._check_chain_rets = orig
    assert O.run_oracle("tail_transparency", pkg, TAIL_CHAIN).kind == "ok"


def test_tail_transparency_fires_on_a_line_only_divergence():
    """Blame the right function at the OUTER call's line — round 336's
    second defect, and the one its own skill warns is easiest to strip
    away (612 of its 1740 divergences were line-only). Nothing but the
    line number differs here, so this pins that the oracle compares it."""
    pkg = K.load_whence(WHENCE_ROOT, "oracle_tail_line_bug")
    m = _interp_mod(pkg)
    orig = m._check_chain_rets

    def outer_line(result, chain_rets):
        line0 = chain_rets[0][2]                  # the OUTERMOST hop's line
        for i in range(len(chain_rets) - 1, -1, -1):
            spec, label, _ = chain_rets[i]
            result = m._check_ret(result, spec, label, line0)
        return result
    m._check_chain_rets = outer_line
    try:
        o = O.run_oracle("tail_transparency", pkg, TAIL_CHAIN)
        assert o.kind == "mismatch", o.detail
        assert o.detail.count("return value of c expected bool, got num") == 2
        assert "(line 3)" in o.detail and "(line 2)" in o.detail, o.detail
    finally:
        m._check_chain_rets = orig
    assert O.run_oracle("tail_transparency", pkg, TAIL_CHAIN).kind == "ok"


def test_clearing_tail_flags_matches_round_336s_textual_lifted_form():
    """The transform this oracle uses (clear `parser.mark_tails`'s own
    `Call.tail`) must agree with the SOURCE rewrite round 336's item 2
    described (`f()` -> `let t = f()  t`, same line). Re-runs a slice of
    round 336's own `chain_pair` family — every 2-hop chain over its five
    `-> Type` annotations and three terminals — and requires the two
    transforms to produce the same answer program for program.

    Round 337 also ran the full 2- and 3-hop family (450 programs) against
    a pre-round-336 interpreter built from `git show`: 450/450 there too,
    i.e. the two transforms agree on the WRONG answers as well, which is
    the half that actually rules out the AST transform quietly papering
    over the defect. Only the fast slice is pinned here — reconstructing
    the old interpreter needs git.
    """
    rets = (None, "num", "str", "bool", "any")
    terms = ('1', '"s"', 'true')
    n = 0
    for r0 in rets:
        for r1 in rets:
            for term in terms:
                a0 = "" if r0 is None else " -> %s" % r0
                a1 = "" if r1 is None else " -> %s" % r1
                tail = ("fn f0()%s { f1() }\nfn f1()%s { %s }\nlet r = f0()\n"
                        % (a0, a1, term))
                lifted = ("fn f0()%s { let t = f1()  t }\nfn f1()%s { %s }\n"
                          "let r = f0()\n" % (a0, a1, term))
                prog = O._parse(PKG, tail)
                assert O.clear_tail_flags(prog) == 1
                ast_lifted = O.behaviour_ex(PKG, tail, program=prog)["vals"]["r"]
                txt_lifted = O.behaviour_ex(PKG, lifted)["vals"]["r"]
                assert ast_lifted == txt_lifted, (tail, lifted, ast_lifted, txt_lifted)
                n += 1
    assert n == len(rets) ** 2 * len(terms) == 75


def test_tail_transparency_exempts_the_space_optimisation_it_is_testing():
    """A tail loop deeper than `max_depth` answers `true` merged and
    `miss: recursion too deep` unmerged. That is the optimisation doing
    its job, not a defect — the oracle must say so, with the number."""
    src = ("fn even(n) { if n == 0 { true } else { odd(n - 1) } }\n"
           "fn odd(n) { if n == 0 { false } else { even(n - 1) } }\n"
           "let par = even(1500)\n")
    o = O.run_oracle("tail_transparency", PKG, src, timeout_s=20.0)
    assert o.kind == "ok" and "space-exempt" in o.detail, o.detail
    assert "depth 500 >= max_depth 500" in o.detail, o.detail


def test_provenance_taint_narrows_the_exemption_instead_of_dropping_programs():
    """`ProgramGen.probe` ends most generated programs with
    `print(str(steps(v)))`, and `steps` reifies the merged `call f xN` node
    into an ordinary value — so a provenance-reflecting program's `out` is
    NOT comparable. Exempting such programs whole cost round 337 more than
    half its corpus (213 of 400); taint keeps the clean bindings."""
    src = TAIL_CHAIN + "let s = steps(r)\nlet clean = 1 + 1\nprint(len(s))\n"
    prog = O._parse(PKG, src)
    tainted = O.provenance_tainted_names(prog)
    assert "s" in tainted and "clean" not in tainted and "r" not in tainted
    o = O.run_oracle("tail_transparency", PKG, src)
    assert o.kind == "ok" and "untainted vals only" in o.detail, o.detail
    # and the reflection-free program next door is compared in full
    assert "all fields" in O.run_oracle("tail_transparency", PKG, TAIL_CHAIN).detail


def test_provenance_taint_reaches_a_fn_defined_after_its_caller():
    """Whence resolves function names at call time, so a single forward
    pass would under-taint `a` here. The fixpoint must not."""
    src = ("fn a() { b() }\nfn b() { steps(1) }\nlet v = a()\nlet w = 2\n")
    tainted = O.provenance_tainted_names(O._parse(PKG, src))
    assert {"a", "b", "v"} <= tainted and "w" not in tainted


def test_tail_transparency_is_silent_across_generated_programs():
    """The real check: no false positive anywhere in a generated corpus.
    Round 337 ran 1500 seeds this way; 60 is what fits a test."""
    checked = 0
    for i in range(60):
        src = ProgramGen(9000 + i, stress_rate=0.5).program()
        o = O.run_oracle("tail_transparency", PKG, src, timeout_s=6.0)
        assert o.kind in ("ok", "parse_error", "timeout"), (i, o.kind, o.detail)
        if o.kind == "ok" and "vals" in o.detail or "all fields" in o.detail:
            checked += 1
    assert checked >= 15, checked      # the corpus really does reach the oracle


def test_generated_programs_now_contain_typed_tail_chains():
    """Round 336's item 1: `-> TAG` landed on ~25% of generated fns but
    nothing ever made a fn's TAIL a call to another typed fn, so the whole
    bug class was outside the grammar. Round 337 confirmed the gap by
    running this oracle over 400 programs against a pre-336 interpreter and
    getting zero findings on a build with the bug still in it; with
    `_typed_tail_chain` the same 400 seeds produce 58."""
    import re
    hits = 0
    for i in range(60):
        if re.search(r"fn (tc|tl|tm)\d+\(", ProgramGen(700 + i, stress_rate=0.0).program()):
            hits += 1
    assert hits >= 10, hits
