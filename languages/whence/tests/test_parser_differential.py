"""Structural differential testing between the HOST parser (`whence/
parser.py`, real Python) and the GUEST parser (`self_host.lang`/
`self_eval.lang`'s byte-identical shared copy, real Whence source executed
by the host interpreter) — same idea `test_self_eval.py` already applies at
the EVALUATOR layer (host-run vs guest-run VALUES must agree), but never
before applied to the PARSER layer's own AST SHAPE. Every prior self-hosting
round (158, 164, 176, 192, 206, 210, 218, 222, 224, 234, 252, ...) found its
gaps either by hand-written checkpoint assertions in `self_host.lang`'s own
66-check test section (which each check ONE hand-picked field, not the
whole tree) or by the guest-EVALUATOR-level why-shape fuzzer in
`harness/swe/guest.py` (which never runs the parser against a real, valid
program and compares it structurally to the host's own real AST — its
`GuestGen` only ever exercises the EVALUATOR's derivation shape, not the
parser's node shape). This file closes that gap: canonicalize both a real
host `A.*` AST and the guest's `@{kind: ..., ...}` record AST into the SAME
plain-tuple shape, and assert they are equal, field for field, across a
real corpus (every node kind the shared grammar supports, plus every
`examples/*.lang` file the guest parser can read).

**Round 338**: this paragraph used to end "...plus every `examples/*.lang`
file that does not use `shape` — the guest parser has no `shape` support at
all, a pre-existing, already-documented limitation, not a target of this
file." That limitation is gone: the shared parser section now implements the
`shape` statement, so `shapes.lang` — a real 93-line structural-typing
program — joined the corpus, and the `SHAPE:` arm of `canon_host_type`
below, previously unreachable by construction, is now reached on both
sides. This file's OWN failure is how that round learned its change altered
the guest AST's public `ret_type` shape (a spec NODE now, mirroring the
host's `_type_spec_expr`, where it used to be a bare tag string): both tests
here went red on a change whose in-language checks were all green, which is
precisely the layer round 320 built this file for.

**Round 320 finding, fixed the same round**: this tool immediately found a
real, previously-undocumented divergence — `self_host.lang`/`self_eval.lang`'s
`build_guards`/`apply_type_guards` (the v0.12 parameter-type-guard erasure,
guest parity round 158) never threaded the enclosing function's OWN NAME
into a parameter guard's label the way the host's `_apply_type_guards` does
(`"parameter '%s'%s" % (pname, suffix)`, `suffix = " of %s" % fn_name if
fn_name else ""`) — every NAMED function's typed-parameter guard produced
`"parameter 'x'"` on the guest where the host produces `"parameter 'x' of
foo"`. Invisible to every existing test (`examples/guess.lang`'s own
`needs_guess(g: guess)` — the exact shape that triggers it — has run green
for rounds without ever comparing its *label wording* against the host, and
self_host.lang's own checkpoint tests never parse a *named*, typed-param fn
through `parse_whence` and inspect the guard's label string). Anonymous
`fn(x: num) { ... }` guards were never affected (the host's own `fn_name`
is `None` there too, so both sides already agreed by construction) — this
is why the bug had zero blast radius on every `assert_three_way`/differential
campaign that ONLY ever fuzzes anonymous closures for this shape. Fixed by
adding a `suffix` parameter to `build_guards`/`apply_type_guards`, threaded
from the two call sites: `""` from the anonymous-fn (`fnexpr`) site, `" of "
+ nm.name` from the named-fn (`fndef`) site — identically in both
`self_host.lang` and `self_eval.lang`'s byte-identical shared section (see
`test_self_eval.py::test_parser_section_matches_self_host`), with the two
files' line counts unchanged (no new lines needed — the fix only extends
existing signatures/calls), so the `LIB_START, LIB_END`/section-slice
constants in `test_self_hosting.py`/`test_self_eval.py` needed no update.
"""

import os
import sys

import pytest

from whence.interp import Interpreter
from whence.parser import parse
from whence import ast_nodes as A
from whence.values import Miss, Record, WList

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "self_eval.lang")
EXAMPLES_DIR = os.path.join(ROOT, "examples")
MARKER = "# ==== SELF-TESTS"

# Every `examples/*.lang` file EXCEPT: `shapes.lang` (declares `shape`,
# which the guest parser cannot parse at all — a pre-existing, documented
# limit, not this file's target), `self_eval.lang`/`self_host.lang`
# themselves (already covered by test_self_hosting.py's own dedicated,
# much slower whole-file parse test with its own 154-statement pin), and
# the two Hermes-gateway-owned files under this directory (a wholly
# separate autonomous system's output, not this project's own convention —
# see `state/known-standing-dirty-paths.json`).
REAL_EXAMPLE_FILES = [
    "hello.lang", "tco.lang", "checks_demo.lang", "failing_check.lang",
    "sales.lang", "history.lang", "provenance.lang", "blame.lang",
    "effects.lang", "guess.lang", "diverge.lang", "deep.lang", "meta.lang",
    # round 338: the guest parser learned `shape`, so the one real example
    # this corpus had to skip is now in it — and it is the densest source
    # available for the new code (7 shape declarations, nested shape
    # fields, shape params, `-> Shape` returns, and a typed tail loop).
    "shapes.lang",
]

# Synthetic snippets covering every node kind the shared grammar builds
# (num/str/bool/name/list/record/unary incl. why/snip/miss/rescue/binary/
# call/index/field/if/fnexpr/block/let/fndef/check/exprstmt/program), plus
# the specific named-fn-with-typed-param shape that repros this round's
# own finding directly (not just via `guess.lang`'s real-world instance).
SYNTHETIC = [
    'let x = 1 + 2 * 3 - 4 / 2',
    'let e = 1e5 + 1e-3 - 2.5E2',   # round 332: exponent-literal guest parity
    'let s = "hi" + "there"',
    'let b = true and false or not true',
    'let r = (miss "why") rescue 5',
    'let w = why (1 + 2)',
    'let n = snip (1 + 2)',
    'let lst = [1, 2, 3]',
    'let rec = @{a: 1, b: "x", c: [1, 2]}',
    'let lst2 = [1, 2, 3]\nlet idx = lst2[0]',
    'let rec2 = @{a: 1}\nlet fld = rec2.a',
    'let cond = if 1 > 0 { "yes" } else { "no" }',
    'fn add(a, b) { a + b }',
    'let f = fn(x) { x * 2 }',
    'fn chk() { check "label": 1 == 1\n0 }',
    'fn foo(x: num) { x }',                        # round 320's own repro
    'fn bar(a: num, b: str) { a }',                 # multi-param variant
    'let g2 = fn(x: num) { x * 2 }',                # anon control: unaffected
    'fn baz(x) -> num { x }',
    'fn eff() effects [io] { print("hi") }',
    'fn chain(a) { a.b.c[0](1, 2) }',
    'fn multi_if(x) { if x == 1 { "a" } else if x == 2 { "b" } else { "c" } }',
    'fn needs_guess(g: guess) { confidence(g) }',   # guess.lang's real shape
    # round 338: `shape` declarations and shape-typed annotations. The
    # desugaring (`let Name = @{__shape: "Name", ...}`) has to agree node
    # for node, and a shape-typed field/param/return has to canonicalize to
    # `SHAPE:<name>` on BOTH sides — a guest that emitted a copy of the
    # shape record instead of a NameRef would diverge right here.
    'shape P = @{x: num, y: num}',
    'shape P = @{}\nlet m = matches(@{q: 1}, P)',
    'shape P = @{x: num}\nshape L = @{a: P, b: P}',
    'shape P = @{x: num}\nfn mag(p: P) { p.x }',
    'shape P = @{x: num}\nfn mk() -> P { @{x: 1} }',
    'shape P = @{x: num}\nlet f = fn(a: P) -> P { a }',
    'shape P = @{x: num}\nfn both(a: P, b: num) -> P { a }',
    'let shape = 5\nlet z = shape + 1',           # contextual, not reserved
]


def eval_library_source():
    src = open(EXAMPLE).read()
    assert MARKER in src
    return src.split(MARKER)[0]


def escape(s):
    return (s.replace("\\", "\\\\").replace('"', '\\"')
              .replace("\n", "\\n").replace("\t", "\\t"))


def _corpus():
    items = list(SYNTHETIC)
    for fname in REAL_EXAMPLE_FILES:
        items.append(open(os.path.join(EXAMPLES_DIR, fname)).read())
    return items


def canon_host_type(spec):
    """host `ret_type`: None, an A.Str (primitive tag), or an A.NameRef (a
    shape name) -> a plain string ("" for none, the tag name for a
    primitive, "SHAPE:<name>" for a shape).

    Round 338: the "SHAPE:" arm used to be documented as unreachable by this
    corpus by construction, because the guest had no `shape` at all. It is
    now reached on both sides (see `canon_guest_type`), which is the whole
    point of `shapes.lang` joining `REAL_EXAMPLE_FILES` above."""
    if spec is None:
        return ""
    if isinstance(spec, A.Str):
        return spec.value
    if isinstance(spec, A.NameRef):
        return "SHAPE:" + spec.name
    raise AssertionError("unexpected ret_type node %r" % (spec,))


def canon_guest_type(prov):
    """guest `ret_type` -> the same plain string `canon_host_type` produces.

    Before round 338 the guest stored a bare tag STRING here and this was a
    plain `.value` read. It now stores the spec NODE the parser built —
    `@{kind: "str", value: tag}` or `@{kind: "name", value: Name}` —
    mirroring the host's `_type_spec_expr`, so that a shape annotation is a
    NameRef reading one shared binding rather than a copy of the record.
    "" is still the no-annotation sentinel."""
    payload = prov.value
    if isinstance(payload, str):
        assert payload == "", payload
        return ""
    fields = payload.fields
    kind = fields["kind"].value
    if kind == "str":
        return fields["value"].value
    if kind == "name":
        return "SHAPE:" + fields["value"].value
    raise AssertionError("unexpected guest ret_type node %r" % (payload,))


def canon_host(node):
    t = type(node)
    if t is A.Program:
        return ("program", tuple(canon_host(s) for s in node.stmts))
    if t is A.Num:
        return ("num", node.value)
    if t is A.Str:
        return ("str", node.value)
    if t is A.BoolLit:
        return ("bool", node.value)
    if t is A.NameRef:
        return ("name", node.name)
    if t is A.ListLit:
        return ("list", tuple(canon_host(i) for i in node.items))
    if t is A.RecordLit:
        return ("record", tuple((name, canon_host(v)) for name, v in node.pairs))
    if t is A.MissLit:
        return ("unary", "miss", canon_host(node.reason))
    if t is A.Unary:
        return ("unary", node.op, canon_host(node.operand))
    if t is A.Why:
        return ("unary", "why", canon_host(node.operand))
    if t is A.Snip:
        return ("unary", "snip", canon_host(node.operand))
    if t is A.Binary:
        return ("binary", node.op, canon_host(node.left), canon_host(node.right))
    if t is A.Rescue:
        return ("binary", "rescue", canon_host(node.left), canon_host(node.right))
    if t is A.Call:
        # `tail` (mark_tails's own compiler-only annotation) deliberately
        # excluded: the guest never computes or exposes an equivalent, and
        # it is not part of the SOURCE-level AST shape this file compares.
        return ("call", canon_host(node.fn), tuple(canon_host(a) for a in node.args))
    if t is A.Index:
        return ("index", canon_host(node.obj), canon_host(node.index))
    if t is A.FieldAccess:
        return ("field", canon_host(node.obj), node.name)
    if t is A.If:
        return ("if", canon_host(node.cond), canon_host(node.then),
                 canon_host(node.otherwise))
    if t is A.FnExpr:
        # `param_call_fact` (v0.14.9+ effect-system bookkeeping) likewise
        # excluded: parser-internal, no guest equivalent, not source shape.
        return ("fnexpr", tuple(node.params), canon_host_type(node.ret_type),
                 canon_host(node.body))
    if t is A.Block:
        # `tail_alias_tag`/`tail_param_name` excluded for the same reason.
        return ("block", tuple(canon_host(s) for s in node.stmts))
    if t is A.Let:
        return ("let", node.name, canon_host(node.expr))
    if t is A.FnDef:
        return ("fndef", node.name, tuple(node.params),
                 canon_host_type(node.ret_type), canon_host(node.body))
    if t is A.Check:
        return ("check", node.label, canon_host(node.expr))
    if t is A.ExprStmt:
        return ("exprstmt", canon_host(node.expr))
    raise AssertionError("unhandled host node type %r" % (t,))


def _unwrap(prov):
    return prov.value


def _guest_list(prov, elem_fn):
    lst = prov.value
    assert isinstance(lst, WList), "expected a guest WList, got %r" % (lst,)
    return tuple(elem_fn(x) for x in lst)


def canon_guest(prov):
    """A guest AST node is a real host `Record` (`@{kind: ..., ...}`,
    built by real `put`/record-literal calls self_host.lang's own parser
    performs) — so this walks real host `Prov`/`Record`/`WList` objects
    directly, the same free-delegation property round 176/206/218 already
    relied on for `guess`/`steps`/`at`/etc: no guest-box unwrapping needed,
    because the guest parser's OWN output was never boxed in the first
    place (unlike a value produced by running self_eval.lang's EVALUATOR,
    which self_host.lang's checkpoint 47 finding, round 206, discovered
    IS boxed — a materially different representation this file never
    touches, since it only runs the parser, never `run_src`)."""
    v = prov.value
    assert isinstance(v, Record), "expected an AST node record, got %r" % (v,)
    f = v.fields
    kind = f["kind"].value
    if kind == "num":
        return ("num", f["value"].value)
    if kind == "str":
        return ("str", f["value"].value)
    if kind == "bool":
        return ("bool", f["value"].value)
    if kind == "name":
        return ("name", f["value"].value)
    if kind == "list":
        return ("list", _guest_list(f["items"], canon_guest))
    if kind == "record":
        pairs = _guest_list(
            f["pairs"],
            lambda p: (p.value.fields["name"].value,
                       canon_guest(p.value.fields["value"])))
        return ("record", pairs)
    if kind == "unary":
        return ("unary", f["op"].value, canon_guest(f["operand"]))
    if kind == "binary":
        return ("binary", f["op"].value, canon_guest(f["left"]),
                 canon_guest(f["right"]))
    if kind == "call":
        return ("call", canon_guest(f["func"]), _guest_list(f["args"], canon_guest))
    if kind == "index":
        return ("index", canon_guest(f["obj"]), canon_guest(f["index"]))
    if kind == "field":
        return ("field", canon_guest(f["obj"]), f["name"].value)
    if kind == "if":
        return ("if", canon_guest(f["cond"]), canon_guest(f["then"]),
                 canon_guest(f["otherwise"]))
    if kind == "fnexpr":
        return ("fnexpr", _guest_list(f["params"], _unwrap),
                 canon_guest_type(f["ret_type"]), canon_guest(f["body"]))
    if kind == "block":
        return ("block", _guest_list(f["stmts"], canon_guest))
    if kind == "let":
        return ("let", f["name"].value, canon_guest(f["value"]))
    if kind == "fndef":
        return ("fndef", f["name"].value, _guest_list(f["params"], _unwrap),
                 canon_guest_type(f["ret_type"]), canon_guest(f["body"]))
    if kind == "check":
        return ("check", f["label"].value, canon_guest(f["expr"]))
    if kind == "exprstmt":
        return ("exprstmt", canon_guest(f["expr"]))
    if kind == "program":
        return ("program", _guest_list(f["stmts"], canon_guest))
    raise AssertionError("unhandled guest kind %r" % (kind,))


def guest_parse_all(sources):
    """One host run: the shared parser library once, then one
    `parse_whence(...)` call per corpus source — the same batching
    discipline `test_self_eval.py::guest_eval_all` already uses, applied to
    the cheaper (host-level, no `run_src` evaluator layer) parser-only
    call, so the ~530-line library's own parse+eval cost is paid once for
    the whole corpus, not once per item."""
    lib = eval_library_source()
    parts = [lib]
    for i, src in enumerate(sources):
        parts.append('let __ast%d = parse_whence("%s")\n' % (i, escape(src)))
    env = Interpreter().run("".join(parts))
    return [env.get("__ast%d" % i) for i in range(len(sources))]


@pytest.mark.whence_slow
def test_host_and_guest_parsers_agree_on_ast_shape():
    corpus = _corpus()
    guest_asts = guest_parse_all(corpus)
    failures = []
    for src, guest_ast in zip(corpus, guest_asts):
        host_ast = parse(src)  # every corpus source is known-valid; a raise
        # here is this test's own bug, not a finding — let it propagate.
        if isinstance(guest_ast.value, Miss):
            failures.append((src[:60], "guest missed",
                              guest_ast.value.reasons))
            continue
        h, g = canon_host(host_ast), canon_guest(guest_ast)
        if h != g:
            failures.append((src[:60], h, g))
    assert not failures, "\n".join(
        "%r:\n  host:  %r\n  guest: %r" % f for f in failures)


def test_named_fn_typed_param_guard_label_includes_enclosing_fn_name():
    """Round 320's own dedicated pin, isolated from the broader sweep
    above: a NAMED function's typed-parameter guard label must say which
    function the parameter belongs to (`"parameter 'g' of needs_guess"`),
    matching the host's own `_apply_type_guards` wording exactly — checked
    on both sides independently, not just via the canonical-form diff."""
    src = "fn needs_guess(g: guess) { confidence(g) }"
    host_label = parse(src).stmts[0].body.stmts[0].expr.args[2].value
    assert host_label == "parameter 'g' of needs_guess"

    guest_ast = guest_parse_all([src])[0]

    def field(prov, name):
        return prov.value.fields[name]

    fndef = field(guest_ast, "stmts").value.buf[0]
    guard_let = field(field(fndef, "body"), "stmts").value.buf[0]
    call = field(guard_let, "value")
    guest_label = field(call, "args").value.buf[2]
    assert field(guest_label, "value").value == "parameter 'g' of needs_guess"

    # an ANONYMOUS fn's typed param must stay suffix-free on both sides —
    # confirms the fix is scoped to NAMED fns only, matching the host's own
    # `fn_name is None` -> `suffix = ""` branch.
    anon_src = "let g = fn(x: num) { x }"
    host_anon_label = parse(anon_src).stmts[0].expr.body.stmts[0].expr.args[2].value
    assert host_anon_label == "parameter 'x'"
    guest_anon_ast = guest_parse_all([anon_src])[0]
    anon_let = field(guest_anon_ast, "stmts").value.buf[0]
    anon_fnexpr = field(anon_let, "value")
    anon_guard = field(field(anon_fnexpr, "body"), "stmts").value.buf[0]
    anon_call = field(anon_guard, "value")
    anon_label = field(anon_call, "args").value.buf[2]
    assert field(anon_label, "value").value == "parameter 'x'"


# ===================================================== round 324 (language C) =
# Round 320's own next-steps item, repeated unchanged through 321-323: "wire
# `harness/swe/fuzz.py`'s program generator into this file for a randomized
# host-vs-guest parser sweep" instead of relying only on the hand-picked
# SYNTHETIC list and curated `examples/*.lang` corpus above. `ProgramGen`'s
# own grammar (`literal`/`some_name`/list/record literals, unary `-`/`not`/
# `why`/`snip`/`miss`, binary ops, `if`, `call`, index, field access,
# `rescue`, `fnexpr`) was confirmed by direct reading to be a strict SUBSET
# of the node kinds `canon_host`/`canon_guest` above already handle (it never
# emits a `shape` declaration or a `matches`/`shapeof`/`typed` builtin call —
# the one construct this file's own module docstring already documents as
# out of scope) — so no new node-kind coverage is needed to wire it in.


def _agi_root():
    """`ROOT` is `languages/whence`; `harness/` is a sibling of `languages/`
    in a real checkout, but this file may run from a tempdir copy of just
    `languages/whence` (a mutation/repair run) — `AGI_RESEARCH_ROOT` (set by
    `harness/swe/proc.py` on every test subprocess it spawns) names the real
    repo in that case. Same fallback `test_v10.py`'s own `ProgramGen` import
    already uses."""
    return os.environ.get("AGI_RESEARCH_ROOT") or os.path.dirname(os.path.dirname(ROOT))


def _import_program_gen():
    harness = os.path.join(_agi_root(), "harness")
    sys.path.insert(0, harness)
    try:
        from swe.fuzz import ProgramGen
    finally:
        sys.path.pop(0)
    return ProgramGen


def _fuzzer_corpus(n, seed):
    """`n` grammar-directed program sources, `stress_rate=0.0` — the
    generator's own stress TEMPLATES (deep recursion, huge lists, very long
    chains, `k` up to 3000) exist to probe evaluator stack/performance
    limits, not parser AST shape; every stress template's own handful of
    statement shapes (fn defs, `let`, arithmetic) is already covered many
    times over by the ordinary statement/expr grammar this corpus draws
    from, so including them would only slow down the guest run (an
    interpreter running a hand-written parser written IN the language it is
    parsing) for zero extra shape coverage.

    A source that fails to HOST-parse is skipped, not a failure: the
    generator deliberately emits some invalid effect/param-usage shapes to
    exercise the parser's own ParseError paths (`_check_call_site_param_
    effects` and friends) — exactly the `parse_error` outcome class `fuzz.
    py`'s own `run_program` oracle already expects for these programs. This
    file only ever compares two SUCCESSFUL parses' AST shapes (see the
    module docstring's "every corpus source is known-valid" comment on the
    hand-picked corpus above), so a ParseError here is out of scope by
    construction, the same way it already is for that corpus."""
    ProgramGen = _import_program_gen()
    out = []
    for i in range(n):
        src = ProgramGen(seed * 1000 + i, stress_rate=0.0).program()
        try:
            parse(src)
        except Exception:
            continue
        out.append(src)
    return out


@pytest.mark.whence_slow
def test_host_and_guest_parsers_agree_on_fuzzer_generated_programs():
    """The randomized counterpart to `test_host_and_guest_parsers_agree_on_
    ast_shape` above: same canonicalization, same comparison, a fuzzer-
    generated corpus instead of a hand-picked one. Seed fixed (324) for
    reproducibility, matching every other seeded campaign in this project."""
    corpus = _fuzzer_corpus(n=60, seed=324)
    # Not every generated program host-parses (see `_fuzzer_corpus`'s own
    # docstring) — a floor, not an exact count, guards against a future
    # grammar change silently making almost everything a ParseError and
    # this test quietly comparing zero programs.
    assert len(corpus) >= 30, (
        "too few host-parseable programs generated (%d/60) — grammar "
        "change in fuzz.py's ProgramGen?" % len(corpus))
    guest_asts = guest_parse_all(corpus)
    failures = []
    for src, guest_ast in zip(corpus, guest_asts):
        host_ast = parse(src)
        if isinstance(guest_ast.value, Miss):
            failures.append((src[:80], "guest missed", guest_ast.value.reasons))
            continue
        h, g = canon_host(host_ast), canon_guest(guest_ast)
        if h != g:
            failures.append((src[:80], h, g))
    assert not failures, "\n".join(
        "%r:\n  host:  %r\n  guest: %r" % f for f in failures)


def test_corpus_actually_reaches_the_shape_arm():
    """Coverage guard for round 338, mirroring `test_swe_fuzz.py`'s
    `test_generator_now_emits_*` idiom: the two differential tests above
    would still pass if `shapes.lang` and every synthetic `shape` snippet
    quietly left the corpus, because agreement on a corpus that exercises
    nothing is free. `canon_host_type`'s "SHAPE:" arm was unreachable by
    construction for 18 rounds; pin that it is now reached, and reached in
    both the real-example and synthetic halves, so neither can be dropped
    without a failure."""
    from_synthetic = sum(repr(canon_host(parse(src))).count("SHAPE:")
                         for src in SYNTHETIC)
    from_examples = sum(
        repr(canon_host(parse(open(os.path.join(EXAMPLES_DIR, f)).read())
                        )).count("SHAPE:")
        for f in REAL_EXAMPLE_FILES)
    assert from_synthetic >= 3, from_synthetic
    assert from_examples >= 2, from_examples
    # and a shape-typed PARAMETER canonicalizes as a NameRef inside the
    # erased guard, not as a "SHAPE:" tag — the two spellings are different
    # by design (`_type_spec_expr` builds the same NameRef for both, but a
    # param guard puts it in ARGUMENT position). Pinned so the guard above
    # is not silently satisfied by param annotations alone.
    param_only = canon_host(parse('shape P = @{x: num}\nfn mag(p: P) { p.x }'))
    assert "SHAPE:" not in repr(param_only), param_only
    assert "('name', 'P')" in repr(param_only), param_only
