"""v0.20 (round 348, language C) — a type miss names the FIELD, plus the
v0.19 parameter-contract coverage round 344 never got to write.

Two families, and they belong in one file because decision 29 is what ties
them: v0.19 made a parameter contract and a return contract ONE rule, and
v0.20 is the first change that pays out on that — one edit to
`_mismatch_reason`, four surfaces improved (`typed`, `-> Type`, `p: Type`,
every `shape` in every example).

What is deliberately pinned here that nothing else pins:

  * the miss REASON TEXT, host vs guest. The ordinary guest differential
    (`test_self_eval.py::test_differential_host_vs_guest`) compares payloads
    and explicitly EXEMPTS miss wordings (round 17), so a guest whose
    `check_contract` produced a completely different sentence would still
    rate "agree". That exemption is what hid round 326's anonymous-fn label
    bug and round 338's six-errors-one-message bug; v0.19 shipped a whole
    new message family with no wording pin at all.
  * the three-way host mode agreement on those same texts. `_check_params`
    is called from three separate sites (`_call_direct`, `_closure_inline`,
    `_call_gen`) — round 128's bug was one such site silently missing its
    check entirely.
"""

import os
import re

import pytest

from whence.interp import Interpreter
from whence.values import Miss, Record

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "self_eval.lang")
MARKER = "# ==== SELF-TESTS"

# The guest's misses carry a line in self_eval.lang, not in the program under
# test — structural and pre-existing, pinned as such by round 338's
# `test_shape_line_divergence_is_pre_existing_not_new`. Everything else in
# the sentence must match byte for byte.
LINE_RE = re.compile(r" \(line \d+\)")


def reason(v):
    """The first reason of a miss, minus its line; or a marker for a value."""
    p = v.payload
    if not isinstance(p, Miss):
        return "VALUE"
    return LINE_RE.sub("", p.reasons[0])


def host_modes(src):
    """(generator, fast-path-disabled, default) results for one program.

    `fast=False` forces everything onto the trampoline (`_call_gen`);
    `direct=False` disables `_call_direct`, which routes call-free bodies
    through `_closure_inline`; the default uses all three. Between them the
    three settings reach every site that binds a parameter.
    """
    return tuple(Interpreter(**kw).run(src).get("result")
                 for kw in ({"fast": False}, {"direct": False}, {}))


def host_reason(src):
    vs = host_modes(src)
    rs = [reason(v) for v in vs]
    assert len(set(rs)) == 1, ("host modes disagree", src, rs)
    return rs[0]


def _library_source():
    src = open(EXAMPLE).read()
    assert MARKER in src
    return src.split(MARKER)[0]


def _escape(src):
    return (src.replace("\\", "\\\\").replace('"', '\\"')
               .replace("\n", "\\n").replace("\t", "\\t"))


def guest_eval_all(sources):
    """One host run: the ~1900-line library once, then one run_src per case.

    Same shape as test_self_eval.py's helper and for the same reason — the
    library is far more expensive to parse than any corpus program, so one
    program with N run_src calls is the only affordable way to do this.
    """
    parts = [_library_source()]
    for i, src in enumerate(sources):
        parts.append('let __out%d = run_src("%s")\n' % (i, _escape(src)))
    env = Interpreter().run("".join(parts))
    out = []
    for i in range(len(sources)):
        rec = env.get("__out%d" % i)
        assert rec is not None and isinstance(rec.payload, Record), i
        out.append(rec.payload.fields["v"])
    return out


# --- v0.20: the field clause -------------------------------------------------

SHAPES = 'shape P = @{x: num}\n'
NESTED = 'shape P = @{x: num}\nshape Q = @{p: P}\n'

FIELD_CLAUSE_CASES = [
    # (source, exact expected reason text)
    ('shape P = @{x: num, a: str}\nfn f(p: P) { p }\n'
     'let result = f(@{x: 1})',
     "parameter 'p' of f expected P, got record (no field 'a')"),

    (SHAPES + 'fn f(p: P) { p }\nlet result = f(@{x: "s"})',
     "parameter 'p' of f expected P, got record "
     "(field 'x' expected num, got str)"),

    # the SAME improvement from the other end of the same contract
    (SHAPES + 'fn f() -> P { @{x: "s"} }\nlet result = f()',
     "return value of f expected P, got record "
     "(field 'x' expected num, got str)"),

    (SHAPES + 'fn f() -> P { 1 }\nlet result = f()',
     # a non-record payload: "got num" already says why, no clause
     "return value of f expected P, got num"),

    (NESTED + 'fn f(q: Q) { q }\nlet result = f(@{p: @{x: "s"}})',
     "parameter 'q' of f expected Q, got record "
     "(field 'p'.'x' expected num, got str)"),

    (NESTED + 'fn f(q: Q) { q }\nlet result = f(@{p: @{}})',
     "parameter 'q' of f expected Q, got record (no field 'p'.'x')"),

    ('shape A = @{n: num}\nshape B = @{a: A}\nshape C = @{b: B}\n'
     'fn f(c: C) { c }\nlet result = f(@{b: @{a: @{n: "s"}}})',
     "parameter 'c' of f expected C, got record "
     "(field 'b'.'a'.'n' expected num, got str)"),

    (SHAPES + 'fn f(p: P) { p }\nlet result = f(@{x: 1/0})',
     "parameter 'p' of f expected P, got record (field 'x' is a miss)"),

    # the `typed` builtin, third surface, with a HAND-BUILT record spec —
    # legal by SPEC's "structural, not nominal" rule, and the case that
    # used to read "expected record, got record" and say nothing at all
    ('let result = typed(@{y: 1}, @{y: "str"}, "v")',
     "v expected record, got record (field 'y' expected str, got num)"),

    ('let result = typed(@{}, @{y: "str"}, "v")',
     "v expected record, got record (no field 'y')"),

    # a primitive spec is untouched: the v0.12 sentence is already complete
    ('let result = typed(3, "str", "v")', "v expected str, got num"),
    ('fn f(p: num) { p }\nlet result = f("s")',
     "parameter 'p' of f expected num, got str"),

    # a callable against a record spec: not a Record, so no clause
    (SHAPES + 'fn f(p: P) { p }\nlet result = f(fn() { 1 })',
     "parameter 'p' of f expected P, got fn"),
]


@pytest.mark.parametrize("src,want", FIELD_CLAUSE_CASES,
                         ids=[str(i) for i in range(len(FIELD_CLAUSE_CASES))])
def test_field_clause_text_and_mode_agreement(src, want):
    assert host_reason(src) == want


def test_fields_are_visited_in_sorted_order_not_declaration_order():
    """Decision 30's one arbitrary choice, pinned because it is arbitrary.

    `P` declares `b` before `a` and BOTH fail; the clause must name `a`.
    Declaration order is not recoverable through `keys()` (which sorts), so
    a declaration-order rule is one `self_eval.lang` could not mirror — see
    decision 27. If this ever flips, the host and guest stop agreeing on
    every multi-field mismatch, silently, because miss wordings are exempt
    from the ordinary differential.
    """
    src = ('shape P = @{b: num, a: num}\nfn f(p: P) { p }\n'
           'let result = f(@{b: "s", a: "s"})')
    assert host_reason(src) == ("parameter 'p' of f expected P, got record "
                                "(field 'a' expected num, got str)")


def test_a_satisfied_contract_still_leaves_no_node():
    """v0.20 touches only the FAILURE path. `_type_match` is unchanged, and
    a passing check is still `_check_contract` returning its input — the
    identical Prov node, no `typed` node in the why-tree."""
    env = Interpreter().run('shape P = @{x: num}\n'
                            'fn f(p: P) { p }\nlet result = f(@{x: 1})')
    v = env.get("result")
    assert not isinstance(v.payload, Miss)
    ops = set()

    def walk(n, seen):
        if id(n) in seen:
            return
        seen.add(id(n))
        ops.add(n.op)
        for i in n.inputs or ():
            walk(i, seen)

    walk(v, set())
    assert "typed" not in ops, sorted(ops)


def test_matches_is_untouched_and_still_a_bool():
    """`matches` has no message to improve and must not grow one: it is
    total by contract (never itself a miss) and returns a plain bool."""
    for src, want in (
            ('shape P = @{x: num}\nlet result = matches(@{x: "s"}, P)', False),
            ('shape P = @{x: num}\nlet result = matches(@{x: 1}, P)', True),
            ('shape P = @{x: num}\nlet result = matches(3, P)', False),
            # a malformed spec still simply does not match (round 335)
            ('let result = matches(@{a: 1}, @{a: 5})', False)):
        v = Interpreter().run(src).get("result")
        assert v.payload is want, (src, v.payload)


def test_match_why_is_total_on_a_record_that_actually_matches():
    """`_match_why` is only ever called after a failure, but it is written
    to be total: asked about a record that matches, it answers None rather
    than inventing a clause. Called directly, since no program can reach it
    that way."""
    from whence.interp import _match_why
    env = Interpreter().run('shape P = @{x: num}\nlet result = @{x: 1}\n'
                            'let spec = P')
    val = env.get("result").payload
    spec = env.get("spec").payload
    assert _match_why(val, spec) is None
    # and a primitive spec never produces a clause, matched or not
    assert _match_why(val, "num") is None
    assert _match_why(3, "str") is None


# --- v0.19: the parameter half, host vs guest, by WORDING --------------------

PARAM_CONTRACT_CASES = [
    # named / anonymous label forms — the `of <fn>` suffix is appended only
    # for a named fn, exactly as `_closure_ret`'s is (round 326 found the
    # guest getting the RETURN half of this wrong; nothing pinned the
    # parameter half until now)
    'fn f(p: num) { p }\nlet result = f("s")',
    'let g = fn(p: num) { p }\nlet result = g("s")',
    'let g = fn(a, p: str) { p }\nlet result = g(1, 2)',

    # a failing check binds the miss and the body still runs (asymmetry 4)
    'fn f(p: num) { 42 }\nlet result = f("s")',

    # `not _spec_ok`: round 335 called this unreachable, round 344 measured
    # it raising AttributeError. Both ends, both now ordinary misses.
    'shape S = @{a: num}\nfn h() { let S = 3\n  fn g(p: S) { p }\n  g(2) }\n'
    'let result = h()',
    'shape S = @{a: num}\nfn h() { let S = 3\n  fn g() -> S { 1 }\n  g() }\n'
    'let result = h()',

    # a shadowing `let` that IS a well-formed record spec: no guard fires,
    # the annotation simply means the shadowing record (round 342 §7's
    # late-binding case, now decided in the DEFINING env)
    'shape S = @{a: num}\nfn h() { let S = @{y: "str"}\n'
    '  fn g(p: S) { p }\n  g(@{x: 1}) }\nlet result = h()',

    # tail chains: the parameter half is re-read on every hop (asymmetry 2)
    'fn c(n: num) { n }\nfn b(n) { c(n) }\nfn a(n) { b(n) }\n'
    'let result = a("s")',
    'fn a(n: num) { if n <= 0 { "done" } else { b(n - 1) } }\n'
    'fn b(n: str) { a(n) }\nlet result = a(3)',

    'fn f(a: num, b: str) { str(a) + str(b) }\nlet result = f("x", 1)',
    'shape P = @{x: num}\nfn f(p: P) { p.x }\nlet result = f(@{x: 5})',
    'shape P = @{x: num}\nfn f(p: P) { p }\nlet result = f(3)',
    'fn f(p: guess) { p }\nlet result = f(3)',
    'fn f(p: any) { p }\nlet result = f("s")',
    # decision 2: an already-missed argument propagates before inspection,
    # so the contract does NOT paint a "wrong type" gloss over it
    'fn f(p: num) { p }\nlet result = f(1/0)',
    'fn f(p: num) -> str { 1 }\nlet result = f("s")',
]


@pytest.mark.whence_slow
def test_param_contract_wording_agrees_host_vs_guest():
    """v0.19's whole message family, compared by TEXT and not by
    missed-ness — the comparison the ordinary corpus differential cannot
    make (round 17 exempts miss reasons by design).

    Round 344 built both sides of this and was killed before it could pin
    them against each other; this is that pin. It also carries the two
    v0.20 surfaces the guest had to grow (`guest_match_why`,
    `guest_mismatch_reason`), since three of the cases below fail a record
    spec and therefore now carry a field clause on both sides.
    """
    guest = guest_eval_all(PARAM_CONTRACT_CASES)
    bad = []
    for src, g in zip(PARAM_CONTRACT_CASES, guest):
        h = Interpreter().run(src).get("result")
        if reason(h) != reason(g):
            bad.append((src, reason(h), reason(g)))
    assert bad == [], bad


@pytest.mark.whence_slow
def test_field_clause_agrees_host_vs_guest():
    """The v0.20 corpus, host vs guest, by text. `keys()` sorts on both
    sides, which is the whole reason the host walks `sorted(spec.fields)`
    rather than its own declaration order."""
    srcs = [src for src, _ in FIELD_CLAUSE_CASES]
    guest = guest_eval_all(srcs)
    bad = []
    for (src, want), g in zip(FIELD_CLAUSE_CASES, guest):
        if reason(g) != want:
            bad.append((src, want, reason(g)))
    assert bad == [], bad


@pytest.mark.whence_slow
def test_sorted_field_order_agrees_host_vs_guest():
    """The pin that makes decision 30's arbitrary choice load-bearing: if
    either side ever walked declaration order instead, this is the test
    that would go red rather than the two sides drifting in silence."""
    src = ('shape P = @{b: num, a: num}\nfn f(p: P) { p }\n'
           'let result = f(@{b: "s", a: "s"})')
    want = ("parameter 'p' of f expected P, got record "
            "(field 'a' expected num, got str)")
    assert host_reason(src) == want
    assert reason(guest_eval_all([src])[0]) == want


# --- v0.19: every site that binds a parameter also checks it ----------------

def test_every_arg_binding_site_applies_the_parameter_half():
    """Round 128's bug, in its parameter-half form, made structural.

    `_check_contract` was once missing from `_closure_inline` — a THIRD
    place a call settles — so a `-> Type` on a call-free-bodied function
    was silently never checked. The audit that catches that class is not
    "every call path named in a docstring" but "every site that binds a
    `Prov('arg', …)`": each one must be followed by a `_check_params`.
    Read off the source, so a new call path added without the check fails
    here rather than in whichever mode happens to route through it.
    """
    src = open(os.path.join(ROOT, "whence", "interp.py")).read()
    lines = src.splitlines()
    bind_lines = [i for i, ln in enumerate(lines) if 'Prov("arg"' in ln]
    assert len(bind_lines) >= 3, bind_lines
    # group consecutive binding lines (the unrolled 1-arg/2-arg/n-arg
    # branches of `_call_direct` are one site, not three)
    groups = []
    for i in bind_lines:
        if groups and i - groups[-1][-1] <= 4:
            groups[-1].append(i)
        else:
            groups.append([i])
    for g in groups:
        window = "\n".join(lines[g[-1]:g[-1] + 6])
        assert "_check_params(" in window, (
            "an arg-binding site with no parameter-contract check near "
            "interp.py:%d" % (g[-1] + 1), window)
    assert len(groups) == 3, [g[0] + 1 for g in groups]


def test_the_parameter_half_is_re_read_per_hop_and_the_return_half_is_not():
    """Asymmetry 2 of decision 29, as behaviour rather than as prose.

    `a` and `b` tail-call each other with incompatible parameter contracts.
    The blamed contract must be the one of the closure being ENTERED at the
    hop that fails — `b`'s — not the originally-called `a`'s, which is what
    a captured-once parameter spec would have produced.
    """
    src = ('fn a(n: num) { if n <= 0 { "done" } else { b(n - 1) } }\n'
           'fn b(n: str) { a(n) }\nlet result = a(3)')
    assert host_reason(src).startswith("parameter 'n' of b expected str")

    # and the mirror: a RETURN contract belongs to the originally-called
    # closure, checked after the whole merged chain settles, innermost
    # first (round 336) — the chain's contracts are not simply dropped
    ret = ('fn c() -> bool { 1 }\nfn b() -> str { c() }\n'
           'fn a() -> list { b() }\nlet result = a()')
    assert host_reason(ret).startswith("return value of c expected bool")


def test_a_failing_parameter_does_not_abort_the_call():
    """Asymmetry 4, inherited unchanged from the v0.12 guards so that
    moving the check did not also change what it means. A function that
    never reads a badly-typed parameter still returns normally."""
    env = Interpreter().run('fn f(p: num) { 42 }\nlet result = f("s")')
    assert env.get("result").payload == 42


def test_a_parameter_annotation_no_longer_changes_the_body():
    """v0.19's structural claim: the annotation rides on the node, so an
    annotated function's BODY is byte-identical to the unannotated one's.
    Before v0.19 the parser prepended a `let p = typed(p, …)` statement."""
    from whence.parser import parse
    plain = parse('fn f(p) { p }').stmts[0]
    typed_ = parse('fn f(p: num) { p }').stmts[0]
    assert plain.param_types is None
    assert typed_.param_types is not None
    assert len(plain.body.stmts) == len(typed_.body.stmts) == 1
    assert type(plain.body.stmts[0]) is type(typed_.body.stmts[0])
    # and the index the parser records is the position in `params`, kept
    # for `self_eval.lang`'s positional `bind_params` and dropped at
    # resolution because every host call path binds by NAME
    two = parse('fn f(a, b: num) { b }').stmts[0]
    assert len(two.param_types) == 1
    assert two.param_types[0][0] == 1
    assert two.param_types[0][1] == "b"
    assert two.param_types[0][3] == "parameter 'b' of f"


@pytest.mark.whence_slow
def test_a_builtin_inside_a_spec_record_renders_differently_and_that_is_old():
    """A pre-existing host/guest divergence, found by accident while
    building the corpus above and recorded rather than left to be
    rediscovered.

    `let S = @{y: str}` binds the BUILTIN `str`, not the type-name string
    (only a `shape` declaration reads a bare `str` as a type name). The
    record is therefore not a usable spec, both sides say so, and both
    RENDER the offending spec into the sentence — the host through
    `show_payload`, the guest through its own `str`/`show_spec`. They
    disagree on how a builtin renders, and on nothing else:

        host  : ... got @{y: <builtin str>}
        guest : ... got @{y: @{__tag: "builtin", name: "str"}}

    That is the guest's closure/builtin representation leaking through its
    renderer, and it predates v0.19 and v0.20 — neither round touched
    `show_payload`, `show_spec`, or the `_spec_ok` message. Pinned as a
    KNOWN difference so the corpus test above stays an exact-equality test
    instead of being weakened to accommodate it.
    """
    src = ('shape S = @{a: num}\nfn h() { let S = @{y: str}\n'
           '  fn g(p: S) { p }\n  g(@{x: 1}) }\nlet result = h()')
    h = host_reason(src)
    g = reason(guest_eval_all([src])[0])
    prefix = "typed spec must be a type name or a shape, got "
    assert h.startswith(prefix) and g.startswith(prefix)
    assert h == prefix + "@{y: <builtin str>}"
    assert g == prefix + '@{y: @{__tag: "builtin", name: "str"}}'
