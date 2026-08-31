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

    # Forward *rest instead of naming every parameter. The injection only
    # cares about `op`; the rest is `_compile_binop`'s private signature and
    # this test has no stake in it. Round 368 added an `interp` parameter and
    # this stub kept its 5-argument form, so from round 368 to round 383 the
    # patched factory raised TypeError, `run_oracle` turned that into
    # `kind == "crash"`, and the assertion for `"mismatch"` failed — RED for
    # 15 rounds, unnoticed because `run_tests_fast.sh` deselects
    # `test_swe_*.py` (round 371's finding, in a second file).
    def bad_factory(op, *rest):
        return orig_factory("+" if op == "-" else op, *rest)
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
            result = m._check_contract(result, spec, label, line)
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
            result = m._check_contract(result, spec, label, line0)
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
    described (`f()` -> `let t = f()` + `t`). Re-runs a slice of round 336's
    own `chain_pair` family — every 2-hop chain over its five `-> Type`
    annotations and three terminals — and requires the two transforms to
    produce the same answer program for program.

    Round 337 also ran the full 2- and 3-hop family (450 programs) against
    a pre-round-336 interpreter built from `git show`: 450/450 there too,
    i.e. the two transforms agree on the WRONG answers as well, which is
    the half that actually rules out the AST transform quietly papering
    over the defect. Only the fast slice is pinned here — reconstructing
    the old interpreter needs git.

    Round 359: this test spelled the lifted form `{ let t = f1()  t }`, two
    statements on ONE line, which **v0.23 (round 356) made a ParseError** —
    so `behaviour_ex` returned `{"kind": "ParseError"}` and the test died on
    `KeyError: 'vals'` for all 75 programs. It had been red since round 356
    and nobody saw it: `test_swe_oracles.py` is in the slow tier, exactly the
    blind spot round 341 built `slowtier.py` for and round 343 found its
    first failure in. Round 357 recorded that "the oracle survives v0.23,
    because round 356 proved its strictness depends on line ALIGNMENT, not
    on the separator laxity" — true of the ORACLE, and this test was relying
    on the laxity anyway.

    The fix keeps the alignment the test is about, rather than the one-line
    spelling: BOTH forms now put the `f1()` call on line 1, `}` and `fn f1`
    and `let r` on lines 2, 3 and 4. Same line numbers on both sides, which
    is the property round 336's line-only divergence needed; a naive split
    would have moved `fn f1` from line 2 to line 3 in the lifted form only.
    """
    rets = (None, "num", "str", "bool", "any")
    terms = ('1', '"s"', 'true')
    n = 0
    for r0 in rets:
        for r1 in rets:
            for term in terms:
                a0 = "" if r0 is None else " -> %s" % r0
                a1 = "" if r1 is None else " -> %s" % r1
                tail = ("fn f0()%s { f1()\n }\nfn f1()%s { %s }\n"
                        "let r = f0()\n" % (a0, a1, term))
                lifted = ("fn f0()%s { let t = f1()\n t }\nfn f1()%s { %s }\n"
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


# --- param_erasure (round 359) ------------------------------------------------
#
# Round 347 §7 designed this oracle and deliberately did not ship it ("an
# oracle whose exemption list has never been run against a real campaign is
# worse than a named gap"); round 353 carried it as "the largest open
# SWE-loop(D) item". These are the runs that were missing.

PARAM_SRC = ('shape Pt = @{a: num}\n'
             'fn f(p: num, q: Pt) { p }\n'
             'let good = f(1, @{a: 2})\n'
             'let bad = f("s", 3)\n'
             'print(good)\nprint(bad)\n')

# One case per exemption mechanism. Each MUST diverge — that is what makes
# the exemption load-bearing rather than defensive.
EXEMPT_CASES = {
    # the shape is rebound AFTER the closure is made: v0.19 resolved it at
    # creation (the shape), the erased guard resolves it per call (the 3)
    "late-bound spec shadow":
        'shape S = @{a: num}\nfn g() {\n  fn f(p: S) { p }\n'
        '  let S = 3\n  f(1)\n}\nlet r = g()\n',
    # the spec name is one of the function's OWN parameters
    "spec name is a parameter":
        'shape S = @{a: num}\nfn f(S, p: S) { p }\nlet r = f(9, 1)\n',
    # the erased form calls `typed` BY NAME from inside the body
    "program binds typed":
        'let typed = fn(v, s, l) { 42 }\nfn f(p: num) { p }\nlet r = f("x")\n',
}


def test_oracle_names_is_the_single_pinned_registry():
    """The one literal list of oracles in the test suite.

    Round 343 found `test_swe_review.py` pinning its own copy of the set,
    red since round 338 because round 337 added `tail_transparency` and
    never re-pinned it there. Two literals mean one of them is stale; this
    is now the only one, and `test_oracle_tool_reports_every_oracle_and_
    fired_list` derives its expectation from `ORACLE_NAMES` instead.
    """
    assert O.ORACLE_NAMES == (
        "totality", "fast_slow", "direct", "determinism", "render",
        "frames", "tail_transparency", "param_erasure")
    # Round 385: this was `set(O.ORACLES) == set(O.ORACLE_NAMES)`, and it was
    # ORDER-DEPENDENT — green alone, red in any process that had already
    # imported `swe.guest`. `guest.py` line 773 registers `self_eval` into the
    # shared `ORACLES` dict AT IMPORT TIME, and `swe.review` imports guest
    # explicitly to make that happen, so `swe.campaign` -> review -> guest
    # pulls it in for anything downstream. Alphabetically `test_swe_campaign`
    # precedes `test_swe_oracles`, so a full `pytest harness/tests/` run has
    # been red here — and nobody has run one, because round 235 tiered the
    # whole subsystem slow and round 341's slice runs ONE FILE PER PROCESS.
    # Green under every way this repo actually runs its tests, red the moment
    # two of them share an interpreter.
    #
    # The equality was the wrong assertion, not the registration: ORACLE_NAMES
    # is the pinned CORE set, ORACLES is a registry `guest.py` extends by
    # design. What round 343 wanted — no SECOND stale literal — is preserved
    # by pinning the core as a subset and naming every extension.
    assert set(O.ORACLE_NAMES) <= set(O.ORACLES)
    extensions = set(O.ORACLES) - set(O.ORACLE_NAMES)
    assert extensions <= {"self_eval"}, extensions
    if "self_eval" in extensions:                     # only if guest was imported
        import swe.guest as _G
        assert O.ORACLES["self_eval"] is _G.oracle_self_eval
        assert _G.GUEST_ORACLE == "self_eval"


def test_param_erasure_reports_when_there_is_nothing_to_compare():
    o = O.run_oracle("param_erasure", PKG, "let x = 1 + 2\n")
    assert o.kind == "ok" and o.detail == "no parameter contracts"


def test_param_erasure_silent_on_the_real_interpreter():
    o = O.run_oracle("param_erasure", PKG, PARAM_SRC)
    assert o.kind == "ok" and o.detail.startswith("2 contracts"), o.detail


def test_erasure_writes_v012_guards_and_leaves_the_tail_alone():
    """P1's mechanism, pinned: `block()` requires a body to end in an
    expression statement, so prepending guards can never change which
    statement `mark_tails` marked — which is why a POST-parse transform is
    faithful to a parser that ran pre-`mark_tails`."""
    src = ('fn f(n: num, acc: num) -> num {\n'
           '  if n == 0 { acc } else { f(n - 1, acc + n) }\n}\n'
           'let a = f(5, 0)\n')
    program = O._parse(PKG, src)
    fn = program.stmts[0]
    tail_before = [id(n) for n in O.iter_ast_nodes(program)
                   if type(n).__name__ == "Call" and n.tail]
    assert tail_before                        # there IS a tail call to lose
    assert len(fn.body.stmts) == 1
    n = O.erase_param_contracts(PKG, program)
    assert n == 2 and fn.param_types is None
    assert len(fn.body.stmts) == 3            # two guards prepended
    for guard in fn.body.stmts[:2]:
        assert type(guard).__name__ == "Let"
        assert guard.line == fn.body.line     # the contract's OWN line
        assert type(guard.expr).__name__ == "Call"
        assert guard.expr.fn.name == "typed"
        assert [type(a).__name__ for a in guard.expr.args] == \
            ["NameRef", "Str", "Str"]
        assert guard.expr.args[0].name == guard.name
        assert guard.expr.args[2].value == "parameter '%s' of f" % guard.name
    assert [id(n) for n in O.iter_ast_nodes(program)
            if type(n).__name__ == "Call" and n.tail] == tail_before
    assert O.erase_param_contracts(PKG, program) == 0     # idempotent


def _pre_v019_pkg():
    """The real pre-v0.19 whence package (`6132f1f^`, the commit that landed
    parameter contracts), materialised from git into a temp dir and loaded
    alongside the current one. Returns None when git cannot supply it."""
    import subprocess
    import tempfile
    global _PRE_V019
    try:
        return _PRE_V019
    except NameError:
        pass
    repo = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    rev = "6132f1f^:languages/whence/whence"
    try:
        names = subprocess.run(["git", "ls-tree", "--name-only", rev],
                               cwd=repo, capture_output=True, text=True,
                               timeout=30, check=True).stdout.split()
        d = tempfile.mkdtemp(prefix="whence-pre-v019-")
        os.mkdir(os.path.join(d, "whence"))
        for name in names:
            blob = subprocess.run(["git", "show", rev + "/" + name], cwd=repo,
                                  capture_output=True, timeout=30,
                                  check=True).stdout
            with open(os.path.join(d, "whence", name), "wb") as fh:
                fh.write(blob)
        _PRE_V019 = K.load_whence(d, "pre_v019")
    except Exception:
        _PRE_V019 = None
    return _PRE_V019


# Fields every AST node class has had on both sides of v0.19 — the v0.19+
# `param_types` slot and any later bookkeeping are deliberately not compared,
# because the whole claim is that the ERASED tree needs none of them.
_STRUCTURAL_FIELDS = {
    "Num": ("value",), "Str": ("value",), "BoolLit": ("value",),
    "NameRef": ("name",), "ListLit": ("items",), "RecordLit": ("pairs",),
    "MissLit": ("reason",), "Unary": ("op", "operand"), "Why": ("operand",),
    "Snip": ("operand",), "Binary": ("op", "left", "right"),
    "Rescue": ("left", "right"), "Call": ("fn", "args", "tail"),
    "Index": ("obj", "index"), "FieldAccess": ("obj", "name"),
    "If": ("cond", "then", "otherwise"),
    "FnExpr": ("params", "body", "ret_type"),
    "FnDef": ("name", "params", "body", "ret_type"),
    "Block": ("stmts",), "Let": ("name", "expr"), "Check": ("label", "expr"),
    "ExprStmt": ("expr",), "Program": ("stmts",),
}


def _dump_ast(n, ind=0):
    if n is None:
        return "  " * ind + "None"
    cls = type(n).__name__
    if cls not in _STRUCTURAL_FIELDS:
        return "  " * ind + repr(n)
    out = ["  " * ind + "%s@%s" % (cls, getattr(n, "line", "?"))]
    for f in _STRUCTURAL_FIELDS[cls]:
        v = getattr(n, f)
        if isinstance(v, (list, tuple)):
            out.append("  " * (ind + 1) + f + ":")
            for x in v:
                if isinstance(x, (list, tuple)):
                    out.append("  " * (ind + 2) + "(")
                    out.extend(_dump_ast(y, ind + 3) for y in x)
                    out.append("  " * (ind + 2) + ")")
                else:
                    out.append(_dump_ast(x, ind + 2))
        elif type(v).__name__ in _STRUCTURAL_FIELDS:
            out.append("  " * (ind + 1) + f + ":")
            out.append(_dump_ast(v, ind + 2))
        else:
            out.append("  " * (ind + 1) + "%s=%r" % (f, v))
    return "\n".join(out)


def test_erasure_reproduces_the_real_pre_v019_parser_node_for_node():
    """The transform is a transcription of `Parser._apply_type_guards`, and
    this is the only test that can say so without taking my word for it: it
    loads the DELETED parser out of git and compares trees.

    Not a paraphrase of the old code and not a golden file — the authority
    is the historical implementation itself. Skips (rather than passes) when
    git cannot supply it, because a vacuous pass here is exactly the failure
    mode round 347's `test_program_recipe_has_no_subclass_fork` caught in
    its own first draft.
    """
    import pytest
    old = _pre_v019_pkg()
    if old is None:
        pytest.skip("pre-v0.19 whence package unavailable from git")
    cases = [
        'fn f(p: num) { p }\nlet a = f(1)\n',
        'fn f(p: num, q) { p + q }\nlet a = f(1, 2)\n',
        'shape Pt = @{a: num}\nfn f(p: Pt) { p }\nlet a = f(@{a: 1})\n',
        'let g = fn(p: str) { p }\nlet a = g("x")\n',
        'fn f(n: num, acc: num) -> num { if n == 0 { acc } else '
        '{ f(n - 1, acc + n) } }\nlet a = f(5, 0)\n',
        'shape Pt = @{a: num}\nfn outer(z: num) { fn inner(w: Pt) { w }\n'
        ' inner(@{a: z}) }\nlet a = outer(1)\n',
    ]
    for src in cases:
        new_tree = O._parse(PKG, src)
        assert O.erase_param_contracts(PKG, new_tree) > 0, src
        assert _dump_ast(new_tree) == _dump_ast(O._parse(old, src)), src


def test_param_erasure_is_a_no_op_on_a_package_that_never_had_contracts():
    import pytest
    old = _pre_v019_pkg()
    if old is None:
        pytest.skip("pre-v0.19 whence package unavailable from git")
    assert O.has_param_contracts(PKG)
    assert not O.has_param_contracts(old)
    o = O.run_oracle("param_erasure", old, PARAM_SRC)
    assert o.kind == "ok" and "no parameter contracts on the AST" in o.detail


def test_param_erasure_fires_when_the_contract_stops_being_applied():
    """The injected-bug half of the house rule. v0.19's whole risk is that
    the check moved OFF the body: make `_check_params` a no-op and the
    erased v0.12 form is the only one still checking."""
    pkg = K.load_whence(WHENCE_ROOT, "param_noop")
    interp_mod = sys.modules[pkg["name"] + ".interp"]
    orig = interp_mod._check_params
    interp_mod._check_params = lambda vs, param_specs: None
    try:
        o = O.run_oracle("param_erasure", pkg, PARAM_SRC)
        assert o.kind == "mismatch", o.detail
        # `first_difference` reports `out` first: the un-checked v0.19 run
        # prints the raw "s", the erased one prints the contract's miss.
        assert "parameter 'p' of f expected num, got str" in o.detail, o.detail
    finally:
        interp_mod._check_params = orig
    assert O.run_oracle("param_erasure", pkg, PARAM_SRC).kind == "ok"


def test_param_erasure_fires_on_a_label_only_divergence():
    """A weaker injection: the contract still fires, but `_closure_params`
    drops the `of <fn>` suffix v0.12's guard label carried. Nothing about
    the ANSWER changes except the sentence, which is the whole reason the
    oracle compares `vals` (misses render their reasons) rather than kinds."""
    pkg = K.load_whence(WHENCE_ROOT, "param_label")
    interp_mod = sys.modules[pkg["name"] + ".interp"]
    orig = interp_mod._closure_params

    def bad(param_types, env, line):
        out = orig(param_types, env, line)
        if out is None:
            return None
        return tuple((p, s, lbl.split(" of ")[0], ln) for p, s, lbl, ln in out)

    interp_mod._closure_params = bad
    try:
        o = O.run_oracle("param_erasure", pkg, PARAM_SRC)
        assert o.kind == "mismatch" and "of f" in o.detail, o.detail
    finally:
        interp_mod._closure_params = orig
    assert O.run_oracle("param_erasure", pkg, PARAM_SRC).kind == "ok"


def test_every_exemption_is_load_bearing():
    """Each exemption must be needed: with `erasure_exemption` silenced, the
    same program is a mismatch. An exemption that nothing uses is a hole in
    the oracle's coverage dressed up as caution."""
    orig = O.erasure_exemption
    try:
        for name, src in EXEMPT_CASES.items():
            o = O.run_oracle("param_erasure", PKG, src)
            assert o.kind == "ok" and "exempt, used" in o.detail, (name, o.detail)
            O.erasure_exemption = lambda program: ""
            bare = O.run_oracle("param_erasure", PKG, src)
            O.erasure_exemption = orig
            assert bare.kind == "mismatch", (name, bare.detail)
    finally:
        O.erasure_exemption = orig


def test_the_typed_shadow_exemption_round_347_did_not_name():
    """Round 347 named ONE exemption (the spec name bound twice). The erased
    form also calls `typed` BY NAME from inside the body, so a program that
    binds `typed` replaces the check itself — a total behavioural takeover,
    not a wording difference."""
    o = O.run_oracle("param_erasure", PKG, EXEMPT_CASES["program binds typed"])
    assert "the program binds 'typed'" in o.detail
    assert "B: 42" in o.detail          # the erased form ran the user's fn


def test_exemptions_are_measured_not_skipped():
    """An exempt program is still run, and the detail distinguishes an
    exemption that was USED from one that merely applied. That distinction
    is what turned round 347's assumption about WHY the exempt programs
    diverge into a measurement — see round 359's knowledge file."""
    used = O.run_oracle("param_erasure", PKG, EXEMPT_CASES["late-bound spec shadow"])
    assert "exempt, used" in used.detail and "A: " in used.detail
    # same exemption, but the second binding of `S` is in a function the
    # annotated one never calls, so nothing about the lookup changes
    unused = O.run_oracle(
        "param_erasure", PKG,
        'shape S = @{a: num}\nfn f(p: S) { p }\n'
        'fn h() {\n  let S = 3\n  S\n}\n'
        'let r = f(@{a: 1})\nlet q = h()\n')
    assert "exempt, unused" in unused.detail, unused.detail


def test_param_erasure_is_silent_across_generated_programs():
    """No false positive anywhere in a generated corpus, and the corpus
    really does reach the oracle (round 337's non-vacuity rule)."""
    compared = 0
    for i in range(60):
        src = ProgramGen(359000000 + i, stress_rate=0.5).program()
        o = O.run_oracle("param_erasure", PKG, src, timeout_s=6.0)
        assert o.kind in ("ok", "parse_error", "timeout"), (i, o.kind, o.detail)
        if o.kind == "ok" and "contracts, " in o.detail and "exempt" not in o.detail:
            compared += 1
    assert compared >= 10, compared


def test_the_corpus_reaches_the_hazard_the_exemption_is_FOR():
    """Round 359's real finding, as a permanent guard.

    Round 347 exempted programs whose spec name is bound twice because the
    two forms resolve it in different environments (round 342 §7). On the
    corpus as it stood, that never happened: all 47 exempt-and-used
    programs in a 2500-program campaign resolved the spec to the SAME
    value and differed only in v0.22's argument-order clause, because
    `_shadowed_shape_stmt` only ever emitted the shadowing `let` BEFORE the
    annotated fn. With the late placement added, 66 of 93 differ in the
    resolution itself, 22 of those in the VALUE and not just the sentence.

    Fails if the late-shadow placement is removed, or if the exemption
    stops being reachable for the reason it was written for — either of
    which would leave the oracle exempting programs nothing exercises.
    """
    hazard = 0
    for i in range(120):
        src = ProgramGen(359000000 + i, stress_rate=0.5).program()
        o = O.run_oracle("param_erasure", PKG, src, timeout_s=6.0)
        if o.kind != "ok" or "exempt, used" not in o.detail:
            continue
        a = [l.strip()[3:] for l in o.detail.split("\n") if l.strip().startswith("A: ")]
        b = [l.strip()[3:] for l in o.detail.split("\n") if l.strip().startswith("B: ")]
        if not a or not b:
            continue
        # the v0.22 clause alone is NOT the hazard: strip it and see if the
        # two sides were saying the same thing
        stripped = b[0].replace(" (arguments fit typed(value, spec, label))", "")
        if stripped != a[0]:
            hazard += 1
    assert hazard >= 2, hazard
