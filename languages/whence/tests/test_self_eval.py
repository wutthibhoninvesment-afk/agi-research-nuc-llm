"""self_eval.lang (self-hosting round 4): a Whence evaluator written in
Whence, differentially tested against the host.

Layout of the checks:
  - the example itself runs (76 in-language checks, exit 0)
  - the parser section is byte-identical to self_host.lang's (they must not
    drift apart silently)
  - a corpus of programs is evaluated BOTH by the host interpreter and by
    the guest evaluator (running on the host); final values must agree at
    the payload level. Miss REASONS are exempt (wordings differ by design,
    documented in the example's header); missed-ness itself must agree.

The guest run is one big program: the library once, then one run_src per
corpus case, so the ~800-line library is parsed and loaded a single time.
"""

import os
import re
import subprocess
import sys

import pytest

from whence.interp import Interpreter, deep_eq
from whence.lexer import LexError
from whence.parser import ParseError
from whence.values import Miss, Record, WList

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "self_eval.lang")
SELF_HOST = os.path.join(ROOT, "examples", "self_host.lang")
MARKER = "# ==== SELF-TESTS"


def library_source():
    src = open(EXAMPLE).read()
    assert MARKER in src
    return src.split(MARKER)[0]


def escape(src):
    return (src.replace("\\", "\\\\").replace('"', '\\"')
               .replace("\n", "\\n").replace("\t", "\\t"))


# Every corpus program ends with `let result = <expr>`; the host side reads
# env["result"], the guest side reads run_src(...)'s final statement value
# (a let evaluates to the bound value in both).
CORPUS = [
    'let result = 1 + 2 * 3 - 4 / 8',
    'let result = (1 + 2) * (3 - 5)',
    'let result = 10 % 3 + 2.5',
    'let result = "ab" + "cd" + str(12)',
    'let result = [1, 2] + [3]',
    'let result = 3 > 2 and 2 >= 2 and not (1 == 2)',
    'let result = false or 3 < 1 or true',
    'let result = if 5 > 3 { "big" } else { "small" }',
    'let x = 2\nlet result = if x > 2 { 1 } else if x < 2 { 2 } else { 3 }',
    'let x = 1\nlet y = if true { let x = 9\nx } else { 0 }\nlet result = x + y',
    'fn sq(x) { x * x }\nlet result = sq(7)',
    'fn fib(n) { if n < 2 { n } else { fib(n - 1) + fib(n - 2) } }\n'
    'let result = fib(12)',
    'fn even(n) { if n == 0 { true } else { odd(n - 1) } }\n'
    'fn odd(n) { if n == 0 { false } else { even(n - 1) } }\n'
    'let result = even(9)',
    'fn adder(a) { fn(b) { a + b } }\nlet result = adder(3)(4) + adder(1)(1)',
    'fn a() { b() }\nfn b() { 41 }\nlet result = a() + 1',
    'fn a() { b() }\nlet r = a()\nfn b() { 1 }\nlet result = r',  # miss both
    'let result = map(fn(x) { x * x }, range(1, 6))',
    'let result = filter(fn(x) { x % 2 == 0 }, range(0, 10))',
    'let result = fold(fn(a, x) { a + x }, 0, range(1, 101))',
    'let result = find(fn(x) { x * x > 10 }, range(1, 10))',
    'let result = find(fn(x) { x > 99 }, [1, 2])',                # miss both
    'let result = fold(fn(a, x) { push(a, len(a)) }, [], range(0, 5))',
    'let r = @{name: "Ada", age: 36}\nlet result = r.name + str(r.age)',
    'let r = @{a: 1}\nlet result = (merge(r, @{b: 2})).b + r.a',
    'let result = get(put(@{x: 1}, "y", 2), "y")',
    'let result = keys(@{b: 1, a: 2})',
    'let xs = [10, 20, 30]\nlet result = xs[1] + xs[len(xs) - 1]',
    'let result = contains("whence", "hen") and contains([1, 2], 2)',
    'let result = join(map(str, range(1, 5)), ",")',
    'let result = num("3.5") + num(" 2 ")',
    'let result = num("3O") rescue -1',
    'let result = num("1e400")',                                  # miss both
    'let result = abs(0 - 7) + sqrt(16)',
    'let result = sqrt(0 - 1)',                                   # miss both
    'let result = trunc(3.9) + trunc(0 - 3.9) + trunc(9)',        # round 318
    'let result = 1 / 0',                                         # miss both
    'let result = nope + 1',                                      # miss both
    'let result = if 1 { 2 } else { 3 }',                         # miss both
    'let f = 3\nlet result = f(1)',                               # miss both
    'fn f(a, b) { a }\nlet result = f(1)',                        # miss both
    'fn f(x) { x }\nlet result = f == f',                         # miss both
    'let result = "abc" + 1',                                     # miss both
    'let result = [1, 2][5]',                                     # miss both
    'let result = (@{a: 1}).zz',                                  # miss both
    'let result = false and num("3O") == 1',
    'let result = fold(fn(a, r) { a + num(r) }, 0, ["1", "2O", "3"])',  # miss
    'fn f(a) { 7 }\nlet result = f(num("3O"))',   # miss arg still runs body
    'let result = miss "deliberate" rescue "saved"',
    'let result = note("waypoint", 5) + 1',
    'let result = str(missed(num("x"))) + str(reasons(num("x"))[0] == reasons(num("x"))[0])',
    'fn f(x) { x }\nlet result = len(f)',                         # miss both (r17)
    'fn f(x) { x }\nlet result = keys(f)',                        # miss both (r17)
    'fn f(x) { x }\nlet result = f.params',                       # miss both (r17)
    'fn f(x) { x }\nlet result = merge(@{a: 1}, f)',              # miss both (r17)
    'fn f(x) { x }\nlet result = get(f, "params")',               # miss both (r17)
    'fn f(a: num) { a + 1 }\nlet result = f(3)',                  # round 158
    'fn f(a: num) { a + 1 }\nlet result = f("x")',                # miss both
    'fn f(a) -> num { a + 1 }\nlet result = f(3)',
    'fn f() -> num { "oops" }\nlet result = f()',                 # miss both
    'let g = fn(a: str) -> str { a + "!" }\nlet result = g("hi")',
    'fn f(a: any) { a }\nlet result = f("x")',
    'fn f(a) effects [] { a + 1 }\nlet result = f(3)',            # round 164
    'fn f(a) effects [io] -> num { a + 1 }\nlet result = f(3)',
    'let g = fn(a, b) effects [net, io] { a + b }\nlet result = g(2, 3)',
    # AI-native primitives (v0.15 guest parity, round 176)
    'let result = sure(guess(5, 0.8, "s") + 1, 0)',
    'let result = guess(5, 0.8, "s") + []',                       # miss both
    'let result = confidence(guess(5, 0.8, "s"))',
    'let result = confidence(5)',                                 # miss both
    'let result = sure(guess(5, 0.3, "s"), 0.5)',                  # miss both
    'let result = is_guess(guess(5, 0.8, "s"))',
    'let result = is_guess(5)',
    'let result = guess(guess(5, 0.9, "a"), 0.4, "b")',
    'let result = guess(1, 0.9, "a") == guess(1, 0.8, "b")',
    'let result = [guess(1, 0.9, "a")] == [guess(1, 0.8, "b")]',
    'let result = [guess(1, 0.9, "a")] == [1]',
    'fn f(a: guess) { sure(a, 0) }\nlet result = f(guess(5, 0.9, "s"))',
    'fn f(a: guess) { a }\nlet result = f(5)',                     # miss both
    'let result = (guess([1, 2, 3], 0.9, "x"))[0]',                # miss both
    'fn f(x) { x }\nlet result = map(f, guess([1, 2], 0.9, "s"))',  # miss both
    'let result = if guess(true, 0.9, "s") { 1 } else { 2 }',      # miss both
]


def host_eval(src):
    return Interpreter().run(src).get("result")


def guest_eval_all(sources):
    """One host run: library + one run_src per corpus case."""
    lib = library_source()
    parts = [lib]
    for i, src in enumerate(sources):
        parts.append('let __out%d = run_src("%s")\n' % (i, escape(src)))
    interp = Interpreter()
    env = interp.run("".join(parts))
    outs = []
    for i in range(len(sources)):
        rec = env.get("__out%d" % i)
        assert rec is not None and isinstance(rec.payload, Record), i
        outs.append(rec.payload.fields["v"])
    return outs


def payloads_agree(h, g):
    hp, gp = h.payload, g.payload
    if isinstance(hp, Miss) or isinstance(gp, Miss):
        return isinstance(hp, Miss) and isinstance(gp, Miss)
    eq = deep_eq(hp, gp)
    return eq is True


@pytest.mark.whence_slow
def test_example_runs_green():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "run.py"), EXAMPLE],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "142 passed, 0 failed" in r.stdout
    assert "all in Whence" in r.stdout


def test_parser_section_matches_self_host():
    # the guest lexer+parser is self_host.lang lines 28..800, verbatim;
    # if one file changes, the other must change with it (round 158: grew
    # from 420 to 485 lines adding `: Type`/`-> Type` guest parity; round
    # 164: 485 to 533 adding `effects [...]` clause skipping; round 176:
    # 533 to 539 adding "guess" to the shared primitive-tag list; round 192:
    # 539 to 561 adding the token-continuation half of the newline-
    # suppression rule (`suppressed()` was bracket-depth-only, missing the
    # host's CONTINUES/CONTINUE_KWS check — found by running self_eval.lang's
    # guest evaluator ON self_host.lang's own source, the first genuine
    # "evaluator interprets the parser" self-hosting run); round 332:
    # 561 to 574 adding the `exp_end` exponent-literal-scan helper (guest
    # parity for the host's post-round-323 exponent-literal grammar); round
    # 338: 574 to 697 adding the `shape` statement (`is_shape_head` /
    # `shape_close` / `shapes_declared_before` / `parse_shape_fields` /
    # `parse_shape_def`, plus spec-NODE type annotations); round 342:
    # 697 to 743 making the shape table SCOPED (`shape_rel_depth` plus one
    # `shapes_before` replacing `shapes_declared_before`, v0.18); round 344:
    # 743 to 750, `build_param_contracts` replacing `build_guards`/
    # `apply_type_guards` so a parameter annotation rides on the fn NODE
    # instead of being desugared into the body (v0.19); round 350:
    # 750 to 800, the v0.21 lexer-parity block -- `pos_inf`/`lit_num`
    # (an overflowing literal is `inf`, as the host's own literal scan
    # makes it, not `num`'s out-of-range MISS), `\\r` in the whitespace
    # skip and in the escape decoder, a raw newline ending a string
    # literal unterminated, and `lex_str_body` reporting through an
    # `@{err: ...}` record instead of a `miss` literal whose reason
    # carried a line number out of THIS file
    host_lines = open(SELF_HOST).read().splitlines()
    section = "\n".join(host_lines[27:800])
    assert section.startswith("# ---- character classes")
    assert section.rstrip().endswith(
        "fn parse_whence(src) { parse_program(lex_all(src)) }")
    assert section in open(EXAMPLE).read()


@pytest.mark.whence_slow
def test_differential_host_vs_guest():
    guest = guest_eval_all(CORPUS)
    failures = []
    for src, g in zip(CORPUS, guest):
        h = host_eval(src)
        assert h is not None, "host did not bind result: %r" % src
        if not payloads_agree(h, g):
            failures.append((src, h.payload, g.payload))
    assert not failures, "\n".join(
        "%r\n  host : %r\n  guest: %r" % f for f in failures)


def test_differential_corpus_covers_misses():
    # a healthy share of the corpus must actually miss on the host, or the
    # differential barely tests error propagation
    miss_srcs = [src for src in CORPUS if isinstance(
        host_eval(src).payload, Miss)]
    assert len(miss_srcs) >= 12, len(miss_srcs)


def test_return_type_guard_label_agrees_host_vs_guest():
    # Round 326's own dedicated pin, isolated from the broader corpus sweep
    # (payloads_agree() above deliberately exempts miss REASON text — see
    # this file's module docstring). An anonymous fn's failed `-> Type`
    # check must say just "return value" on BOTH sides (the host's
    # `_closure_ret` only appends " of %s" when the closure has a name,
    # i.e. never for an `A.FnExpr`); a NAMED fn's must say "return value of
    # <name>" on both sides. Before round 326's fix, the guest's
    # `check_ret` unconditionally appended "of " + fn_name, so the
    # anonymous case read "return value of (anonymous)" on the guest vs.
    # plain "return value" on the host — invisible until now because
    # self_eval.lang's own pre-existing "guest anonymous fn honors both
    # param and return types" check only ever exercised the SUCCESS path.
    anon_src = 'let g = fn() -> num { "oops" }\nlet result = g()'
    named_src = 'fn g() -> num { "oops" }\nlet result = g()'

    h_anon, h_named = host_eval(anon_src), host_eval(named_src)
    assert isinstance(h_anon.payload, Miss) and isinstance(h_named.payload, Miss)
    assert h_anon.payload.reasons[0].startswith(
        "return value expected num, got str")
    assert h_named.payload.reasons[0].startswith(
        "return value of g expected num, got str")

    g_anon, g_named = guest_eval_all([anon_src, named_src])
    assert isinstance(g_anon.payload, Miss) and isinstance(g_named.payload, Miss)
    assert g_anon.payload.reasons[0].startswith(
        "return value expected num, got str")
    assert g_named.payload.reasons[0].startswith(
        "return value of g expected num, got str")


@pytest.mark.whence_slow
def test_guess_confidence_and_sources_agree_host_vs_guest():
    # deep_eq's Guess-vs-Guess case deliberately compares the ANSWER only
    # (interp.py: "confidence/sources are metadata, not identity"), so
    # test_differential_host_vs_guest's payloads_agree() would pass even if
    # the guest silently produced the WRONG confidence or sources — it goes
    # through the same code path as any other list/record member compare.
    # This test checks the one thing deep_eq can't: render both sides with
    # the real host `show_payload` (confidence/sources are baked into the
    # string, "guess %.2g (%s): %s") and require an exact match.
    from whence.values import show_payload
    cases = [
        'let result = guess(5, 0.8, "s") + 1',            # single source
        'let result = guess(1, 0.9, "a") == guess(1, 0.8, "b")',  # union + min
        'let result = guess(guess(5, 0.9, "a"), 0.4, "b")',       # flatten
        'let result = sure(guess(5, 0.9, "s"), 0.5)',             # unwrapped
    ]
    guest = guest_eval_all(cases)
    for src, g in zip(cases, guest):
        h = host_eval(src)
        assert show_payload(h.payload) == show_payload(g.payload), (
            src, show_payload(h.payload), show_payload(g.payload))


def test_guest_check_report():
    lib = library_source()
    src = lib + ('let __r = run_src("check \\"g\\": 1 == 1\\n'
                 'check \\"b\\": 1 == 2\\n0")\n')
    env = Interpreter().run(src)
    rec = env.get("__r").payload
    checks = rec.fields["checks"].payload
    assert isinstance(checks, WList) and len(checks) == 2
    c0, c1 = checks[0].payload, checks[1].payload
    assert c0.fields["label"].payload == "g" and c0.fields["pass"].payload is True
    assert c1.fields["pass"].payload is False


def test_two_level_blame():
    # a guest program's failure has a host blame trail whose origin is the
    # num miss created two interpretation levels down
    lib = library_source()
    src = lib + ('let __sick = gv("fold(fn(a, r) { a + num(r) }, 0,'
                 ' [\\"1\\", \\"2O\\", \\"3\\"])")\n')
    interp = Interpreter()
    env = interp.run(src)
    sick = env.get("__sick")
    assert isinstance(sick.payload, Miss)
    assert any("cannot parse" in r for r in sick.payload.reasons)


# ---- guest-level provenance (self-hosting round 5) --------------------------
# Guest boxes label ops with the same strings as the host's Prov.label()
# ("let x", "call fib", "arg n", "if then branch", "+", "literal", ...), so
# provenance itself can be compared across evaluators: hand-picked labels
# must appear in BOTH the host DAG and the guest box graph, and both blame
# walks must name the same origin op. Exact multiset equality is NOT expected
# (the host shares literal nodes and merges tail-loop/if runs; the guest
# does neither).

from whence.values import walk_steps, is_origin_miss


def guest_box(src):
    """Evaluate `src` under the guest evaluator, keeping the boxes: returns
    the final statement's box as a host Record (fields v/op/ins)."""
    lib = library_source()
    interp = Interpreter()
    env = interp.run(lib + 'let __p = gp("%s")\n' % escape(src))
    rec = env.get("__p").payload
    assert isinstance(rec, Record), rec
    return rec


def guest_labels(rec):
    out, stack = set(), [rec]
    while stack:
        r = stack.pop()
        out.add(r.fields["op"].payload)
        stack.extend(ch.payload for ch in r.fields["ins"].payload)
    return out


def host_labels(root):
    return set(n.label() for n, _ in walk_steps(root))


def test_provenance_labels_agree_host_vs_guest():
    cases = [
        ("let x = 2 + 3\nlet y = x * 10\nlet result = y",
         ["let result", "let y", "let x", "*", "+", "literal"]),
        ("fn fib(n) { if n < 2 { n } else { fib(n - 1) + fib(n - 2) } }\n"
         "let result = fib(3)",
         ["let result", "call fib", "arg n", "if took then-branch",
          "if took else-branch", "<", "+", "-", "literal"]),
    ]
    for src, expected in cases:
        h = host_labels(host_eval(src))
        g = guest_labels(guest_box(src))
        for label in expected:
            assert label in h, "host lacks %r for %r (has %s)" % (
                label, src, sorted(h))
            assert label in g, "guest lacks %r for %r (has %s)" % (
                label, src, sorted(g))


def test_anonymous_fn_call_label_agrees_host_vs_guest():
    # Round 326 left this as an open question ("named, not chased"): does
    # the "call <name>" op-LABEL (not the miss REASON text, which
    # payloads_agree() deliberately exempts) match between host and guest
    # for an ANONYMOUS closure call? test_provenance_labels_agree_host_vs_
    # guest above never exercises this — its only call case is named
    # ("call fib"). It did not: the host's `_call_direct`/`_call_gen`
    # (interp.py) label every call `p.name or "<fn>"`, so an anonymous
    # closure's call node is literally "call <fn>"; the guest's
    # `apply_closure` (self_eval.lang) built the label as `"call " +
    # c.name` UNCONDITIONALLY, and an anonymous closure's `c.name` is
    # always the sentinel string "(anonymous)" (`eval_FnExpr`'s own
    # `name: "(anonymous)"`) — so the guest said "call (anonymous)",
    # never matching the host. Fixed by giving `apply_closure` the same
    # "(anonymous)" -> "<fn>" substitution `check_ret`'s own `label`
    # already applies (round 326's fix), via a new `call_op_name` helper,
    # at all three places `apply_closure` builds this op tag: the arity-
    # mismatch miss, the depth-guard miss, and the ordinary success wrap.
    success_src = "let g = fn(n) { n + 1 }\nlet result = g(4)"
    arity_src = "let g = fn(n) { n + 1 }\nlet result = g(4, 5)"
    named_src = "fn g(n) { n + 1 }\nlet result = g(4)"
    for src, expected in (
        (success_src, "call <fn>"),
        (arity_src, "call <fn>"),
        (named_src, "call g"),
    ):
        h = host_labels(host_eval(src))
        g = guest_labels(guest_box(src))
        assert expected in h, "host lacks %r for %r (has %s)" % (
            expected, src, sorted(h))
        assert expected in g, "guest lacks %r for %r (has %s)" % (
            expected, src, sorted(g))
        assert "call (anonymous)" not in g, sorted(g)


def test_get_of_a_callable_mirrors_field_not_a_bespoke_get_node():
    """Round 150: `get(r, name)` has EXACTLY `.field` semantics on the host
    (`b_get` delegates straight to `_field` — same op "field", same
    single-input shape, `get(r, "a")` and `r.a` are indistinguishable node
    for node, by design since round 24). self_eval.lang's own `get`
    special-cased a CALLABLE first argument (needed: a guest closure is an
    ordinary record under the hood and would otherwise let `get` pierce
    it) with a bespoke "get" node naming BOTH arguments as inputs — an
    op/arity the host's real `_field` helper never produces for ANY
    non-record object, callable or not. Found live by the guest-
    differential why-shape probe (`harness/swe/guest.py`, seed
    602001893): `guest ops: ['get', 'literal']` vs `host ops: ['field',
    'fn', 'let', 'record']` — the guest invented an op and leaked the key
    argument's own `literal` node into the tree, neither of which the host
    derivation for the same program ever produces.

    Round 156: a bare "field" op tag (round 150's own fix) still diverged
    from the host, because `Prov.label()` is "op + ' ' + detail" and
    `_field`'s non-record branch defaults `detail` to the reason string
    itself (`mk_miss`'s `detail if detail else reason` fallback) — so the
    host's real label for this node is the full
    "field cannot access .b on <fn adder>", not bare "field". Fixed by
    folding the (already-correct) miss reason into the op tag too, via a
    new `show_callable` guest helper mirroring `whence/values.py`'s
    `show_payload` rendering of a `Closure` (`str()` on the raw guest
    closure record would otherwise dump its `@{__tag: "closure", ...}`
    fields instead of "<fn adder>")."""
    src = ('fn adder(a) { fn(b) { a + b } }\n'
           'let result = @{c: get(adder, "b")}')
    h = host_labels(host_eval(src))
    g = guest_labels(guest_box(src))
    assert "field cannot access .b on <fn adder>" in g, sorted(g)
    assert "field" not in g, sorted(g)   # the op alone, undecorated, is not a real host label
    assert "get" not in g, sorted(g)
    assert "literal" not in g, sorted(g)   # the key "b" is not a derivation input
    assert g - h == set(), "guest invented ops the host never used: %s (guest=%s host=%s)" % (
        sorted(g - h), sorted(g), sorted(h))


def test_dot_field_access_on_callable_mirrors_host_label():
    """The `.field` DOT-SYNTAX path (`eval_field`, a different guest
    function from `get()` above) hits the exact same host `_field`
    non-record branch and must produce the identical label. This was a
    second, previously-untested instance of the same gap the `get()` test
    above closes: `eval_field`'s callable branch had a hardcoded
    "on a function" string (no callee name at all), which never matched a
    real host label for a NAMED closure — fixed the same round, via the
    same `show_callable` helper."""
    src = 'fn adder(a) { fn(b) { a + b } }\nlet result = @{c: adder.b}'
    h = host_labels(host_eval(src))
    g = guest_labels(guest_box(src))
    assert "field cannot access .b on <fn adder>" in g, sorted(g)
    assert g - h == set(), "guest invented ops the host never used: %s (guest=%s host=%s)" % (
        sorted(g - h), sorted(g), sorted(h))


@pytest.mark.whence_slow
def test_sure_on_a_plain_value_is_a_pass_through_not_a_bespoke_node():
    """Round 192->194: the guest-differential why-shape fuzzer (seed 9205,
    `harness/swe/guest.py`) found `sure([], 0.0)` — a plain, non-Guess
    value, threshold irrelevant — diverging: guest-only op `literal` vs
    host ops `{let, list}`. `sure`'s host implementation (interp.py
    `b_sure`) is a PASS-THROUGH when its value was never a Guess ("already
    certain: sure() is a no-op escape hatch") — no new provenance node at
    all, so the host derivation for `let v = sure([], 0.0)` is exactly the
    same two nodes as `let v = []` (`let` + the list literal's own `list`
    node). Before this round `sure` fell through to `apply_builtin`'s
    generic catch-all, which unconditionally wraps a fresh "sure" box
    (labelled "literal" once reified — the box's raw payload, an empty
    list, has no host-mirroring op of its own to report), regardless of
    whether the host itself created a node. Fixed with a dedicated
    `apply_builtin` branch mirroring `typed`'s existing pass-through
    shape."""
    cases = [
        'let result = @{c: sure([], 0.0)}',                  # list, seed 9205027725
        'let result = @{c: sure((@{} rescue 0), 1.0)}',       # record, seed 9205027720
        'let result = @{c: sure(5, 0.9)}',                    # num
        'let result = @{c: sure("s", 0.0)}',                  # str
    ]
    for src in cases:
        h = host_labels(host_eval(src))
        g = guest_labels(guest_box(src))
        assert "sure" not in g, (src, sorted(g))
        assert g - h == set(), (
            "guest invented ops the host never used: %s (src=%r guest=%s host=%s)"
            % (sorted(g - h), src, sorted(g), sorted(h)))


@pytest.mark.whence_slow
def test_sure_below_threshold_and_bad_threshold_still_derive_a_sure_node():
    # the two branches that DO create a real host "sure" node (a genuine
    # Guess below threshold, and an invalid threshold) must still show up
    # as a "sure"-headed label on both sides — only the plain-value
    # pass-through above should vanish. Full label text is NOT required to
    # match (guest.py's own module docstring: "miss REASON wordings differ
    # between host and guest" by design) — only the bare leading op token,
    # the same granularity the why-shape oracle itself checks.
    cases = [
        'let result = @{c: sure(guess(5, 0.2, "s"), 0.9)}',   # below threshold
        'let result = @{c: sure(5, 7)}',                      # bad threshold
    ]
    for src in cases:
        h = host_labels(host_eval(src))
        g = guest_labels(guest_box(src))
        assert any(l.split(" ")[0] == "sure" for l in h), (src, sorted(h))
        assert any(l.split(" ")[0] == "sure" for l in g), (src, sorted(g))


def guest_origin(rec):
    """The guest-side blame walk: descend into the first missed input until
    no input is missed — the node that created the miss."""
    while True:
        nxt = None
        for ch in rec.fields["ins"].payload:
            if isinstance(ch.payload.fields["v"].payload, Miss):
                nxt = ch.payload
                break
        if nxt is None:
            return rec
        rec = nxt


def test_blame_origin_agrees_host_vs_guest():
    src = ('let rows = ["12", "3O", "7"]\n'
           'let result = fold(fn(a, r) { a + num(r) }, 0, rows)')
    h = host_eval(src)
    assert isinstance(h.payload, Miss)
    h_origins = [n for n, _ in walk_steps(h) if is_origin_miss(n)]
    assert h_origins and all(n.op == "num" for n in h_origins), \
        [(n.op, n.detail) for n in h_origins]
    g = guest_origin(guest_box(src))
    assert isinstance(g.fields["v"].payload, Miss)
    assert g.fields["op"].payload == "num"


def test_boxes_are_well_formed_and_stripped_output_has_none():
    rec = guest_box("let result = [1, @{a: 2 + 3}, [4]]")
    stack = [rec]
    n = 0
    while stack:
        r = stack.pop()
        n += 1
        assert set(r.fields) == {"v", "op", "ins"}, sorted(r.fields)
        assert isinstance(r.fields["op"].payload, str)
        assert isinstance(r.fields["ins"].payload, WList)
        stack.extend(ch.payload for ch in r.fields["ins"].payload)
    assert n >= 8, n
    # and the stripped path exposes no box records at any depth
    lib = library_source()
    env = Interpreter().run(
        lib + 'let __s = gv("let result = [1, @{a: 2 + 3}, [4]]")\n')
    stack = [env.get("__s").payload]
    while stack:
        p = stack.pop()
        if isinstance(p, WList):
            stack.extend(e.payload for e in p)
        elif isinstance(p, Record):
            assert set(p.fields) != {"v", "op", "ins"}, "leaked box"
            stack.extend(f.payload for f in p.fields.values())


# ==================================== round 335 (SWE-loop D) ===============
# `typed`'s guest branch (`apply_builtin`, self_eval.lang) required
# `is_str(spec)`, on the stated assumption that "the guest has no `shape`
# records, so a record spec simply never matches". That conflates a shape
# DECLARATION (which the guest parser indeed has none of) with a spec
# VALUE: a hand-built record IS a legal structural spec on the host by
# design (SPEC v0.12, "structural, not nominal"), and an ordinary record
# literal is something any guest program can write. Round 240 had already
# found and fixed exactly this for `matches`; the `typed` branch was never
# revisited. Found by the guest-differential oracle the moment round 335
# put `matches`/`shapeof`/`typed` into `harness/swe/fuzz.py`'s
# `BUILTIN_ARITY`; minimized to `typed(@{a: 1}, @{a: "num"}, "L")`.

RECORD_SPEC_CASES = [
    'let result = typed(@{a: 1}, @{a: "num"}, "L")',              # passes
    'let result = typed(@{a: 1, b: "s"}, @{a: "num"}, "L")',      # width
    'let result = typed(@{a: @{b: 1}}, @{a: @{b: "num"}}, "L")',  # nested
    'let result = typed(@{x: 1}, @{__shape: "Pt", x: "num"}, "L")',
    'let result = typed(@{a: "s"}, @{a: "num"}, "L")',            # mismatch
    'let result = typed(1, @{a: "num"}, "L")',                    # not a record
    'let result = typed(@{}, @{a: "num"}, "L")',                  # missing field
    'let result = typed(fn(x) { x }, @{a: "num"}, "L")',          # callable
    'let result = typed(@{a: 1}, @{a: 5}, "L")',                  # malformed spec
    'let result = matches(@{a: 1}, @{a: "num"})',
    'let result = matches(@{a: 1}, @{a: 5})',
    'let result = shapeof(@{a: 1})',
]


def test_record_spec_typed_agrees_host_vs_guest():
    guests = guest_eval_all(RECORD_SPEC_CASES)
    for src, g in zip(RECORD_SPEC_CASES, guests):
        h = host_eval(src)
        assert payloads_agree(h, g), (src, h.payload, g.payload)


def test_the_minimized_divergence_is_a_pass_through_on_both_sides():
    # the exact bug: the host passed the record through untouched, the
    # guest returned a miss. Assert the VALUE, not just agreement, so a
    # future regression that breaks BOTH sides identically still fails.
    src = 'let result = typed(@{a: 1}, @{a: "num"}, "L")'
    h = host_eval(src)
    g = guest_eval_all([src])[0]
    assert isinstance(h.payload, Record) and not isinstance(h.payload, Miss)
    assert {k: n.payload for k, n in h.payload.fields.items()} == {"a": 1}
    assert isinstance(g.payload, Record)
    assert {k: n.payload for k, n in g.payload.fields.items()} == {"a": 1}


def test_record_spec_mismatch_keeps_only_the_value_as_a_guest_input():
    # the why-shape half of the same bug: the reject branch kept all THREE
    # args as inputs, so the spec record's own `record` op showed up as a
    # guest-only op the host's single-input `typed` miss never has.
    rec = guest_box('let result = typed(1, @{a: "num"}, "L")')
    labels = guest_labels(rec)
    assert "record" not in labels, sorted(labels)
    h = host_eval('let result = typed(1, @{a: "num"}, "L")')
    assert "record" not in host_labels(h), sorted(host_labels(h))


# --- round 336: host/guest agreement on WHICH contract a tail chain blames ---
#
# The corpus differential above compares payloads and exempts miss REASON
# wordings by design (they differ between host and guest — see the module
# docstring). That exemption is what hid round 336's bug for ~200 rounds:
# in a merged tail chain the host blamed the OUTERMOST violated `-> Type`
# contract while the guest — which has no tail-call merging at all, so
# `apply_closure` runs `check_ret` once per real frame, inside out —
# blamed the innermost. Both sides missed, so the oracle said `ok`.
#
# These cases deliberately break the exemption for one narrow, well-defined
# slice: the "return value of <fn>" prefix of a `-> Type` miss, which the
# guest's `check_ret` builds with the same wording the host's `_check_ret`
# does. Nothing else about the reason string is compared.

RET_CHAIN_CASES = [
    # (source, the function both sides must blame)
    ('fn f() -> num { "s" }\n'
     'fn outer() { f() }\n'
     'let result = outer()\n', "f"),
    ('fn c() -> bool { 1 }\n'
     'fn b() -> str { c() }\n'
     'fn a() -> list { b() }\n'
     'let result = a()\n', "c"),
    ('fn c() -> bool { 1 }\n'
     'fn b() -> str { c() }\n'
     'fn a() { b() }\n'
     'let result = a()\n', "c"),
    ('fn c() -> num { "s" }\n'
     'fn b() -> num { c() }\n'
     'fn a() { b() }\n'
     'let result = a()\n', "c"),
    ('fn c() -> num { "s" }\n'
     'fn b() { c() }\n'
     'fn a() -> num { b() }\n'
     'let result = a()\n', "c"),
    ('fn a(n) -> num { if n <= 0 { "s" } else { b(n - 1) } }\n'
     'fn b(n) -> num { a(n) }\n'
     'let result = a(4)\n', "a"),
    ('fn d() -> num { "s" }\n'
     'fn c() -> any { d() }\n'
     'fn b() -> num { c() }\n'
     'fn a() { b() }\n'
     'let result = a()\n', "d"),
]


def blamed_fn(miss):
    assert isinstance(miss, Miss), miss
    first = miss.reasons[0]
    assert first.startswith("return value of "), first
    return first[len("return value of "):].split(" ")[0]


@pytest.mark.whence_slow
def test_tail_chain_return_miss_blames_the_same_function_on_both_sides():
    sources = [src for src, _ in RET_CHAIN_CASES]
    guest = guest_eval_all(sources)
    rows = []
    for (src, want), g in zip(RET_CHAIN_CASES, guest):
        h = host_eval(src)
        rows.append((src, want, blamed_fn(h.payload), blamed_fn(g.payload)))
    bad = [r for r in rows if not (r[1] == r[2] == r[3])]
    assert bad == [], bad


# --- `shape` guest parity (round 338) ----------------------------------------
#
# Until this round the guest had no `shape` support at all: `expect_type_name`
# accepted primitive tags only, and `shape` at statement start was not a
# statement, so the guest parser stopped at the `=` with "unexpected token
# '='". Round 335's next-steps item 2 (carried by round 336 as item 4) asked
# for it as the last piece of v0.12/v0.13 guest parity.
#
# WHY THESE TESTS COMPARE REASON WORDINGS AND NOT JUST MISSED-NESS. The
# corpus differential above (`payloads_agree`) deliberately exempts miss
# REASONS, because guest wordings differ by design. That exemption is exactly
# what hid this gap: on the PRE-338 guest all six declaration-error programs
# in SHAPE_PARSE_ERRORS below miss on both sides, so a missed-ness-only
# comparison rates all six "agree" — while the guest is in fact reporting one
# single reason, "unexpected token '=' at line 1", for six different host
# errors, because it never recognised the statement at all. Measured, not
# assumed: the full case list below scores 14/32 agreeing against the
# pre-round guest and 32/32 against this one, and 6 of those 14 are these
# blind ones. So the reason WORDING is the observable that carries the
# information here, and these tests pin it (modulo the `(line N)` suffix,
# which is the guest's one genuinely-documented provenance divergence —
# `test_shape_line_divergence_is_pre_existing` below shows it predates this
# round by exhibiting it on a PRIMITIVE return type).

SHAPE_VALUE_CASES = [
    # (source, expected host+guest payload)
    ('shape P = @{x: num, y: num}\nfn mag(p: P) { p.x + p.y }\n'
     'let result = mag(@{x: 3, y: 4})', 7),
    # width subtyping: extra fields are ignored, on both sides
    ('shape P = @{x: num, y: num}\nfn mag(p: P) { p.x + p.y }\n'
     'let result = mag(@{x: 3, y: 4, z: 9})', 7),
    ('shape P = @{x: num}\nlet result = matches(@{x: 1}, P)', True),
    ('shape P = @{x: num}\nlet result = matches(@{x: "s"}, P)', False),
    # a shape IS an ordinary runtime record (host `shape_def`'s whole point)
    ('shape P = @{x: num}\nlet result = P.__shape', "P"),
    # an empty shape matches anything record-shaped
    ('shape P = @{}\nlet result = matches(@{q: 1}, P)', True),
    # nested shapes: `L.a` must BE `P`, not a structural copy of it — the
    # host builds a NameRef, so the same binding is read, and the guest has
    # to as well or `L.a.__shape` would not survive
    ('shape P = @{x: num}\nshape L = @{a: P}\nlet result = L.a.__shape', "P"),
    ('shape P = @{x: num}\nshape L = @{a: P}\n'
     'let result = matches(@{a: @{x: 1}}, L)', True),
    ('shape P = @{x: num}\nshape L = @{a: P}\n'
     'let result = matches(@{a: @{x: "s"}}, L)', False),
    ('shape P = @{x: num, y: num}\nshape L = @{a: P, b: P}\n'
     'fn dx(l: L) { l.b.x - l.a.x }\n'
     'let result = dx(@{a: @{x: 0, y: 0}, b: @{x: 3, y: 4}})', 3),
    # `-> Shape` return types
    ('shape P = @{x: num}\nfn mk() -> P { @{x: 1} }\nlet result = mk().x', 1),
    ('shape P = @{x: num}\nlet f = fn(a: P) { a.x }\nlet result = f(@{x: 7})', 7),
    # `shape` is a CONTEXTUAL keyword on both sides, never reserved
    ('let shape = 5\nlet result = shape + 1', 6),
    ('let result = @{shape: 3}.shape', 3),
    # untyped and primitive-typed code is untouched by any of this
    ('fn add(a, b) { a + b }\nlet result = add(1, 2)', 3),
    ('fn t(a: num) -> num { a * 2 }\nlet result = t(21)', 42),
    # v0.18 (round 342): shapes are block-scoped, exactly like the `let`
    # each one desugars to. All three of these were REFUSED or broken
    # before it — the first worked, the second and third were "shape 'S'
    # is already declared" parse errors on both sides.
    ('fn mk() { shape L = @{x: num}\nfn f(p: L) -> L { p }\n'
     '(f(@{x: 7})).x }\nlet result = mk()', 7),
    ('fn a() { shape S = @{x: num}\nfn f(p: S) { p.x }\nf(@{x: 1}) }\n'
     'fn b() { shape S = @{y: num}\nfn g(p: S) { p.y }\ng(@{y: 2}) }\n'
     'let result = a() + b()', 3),
    ('shape S = @{x: num}\n'
     'fn inner() { shape S = @{y: num}\nfn g(p: S) { p.y }\ng(@{y: 5}) }\n'
     'let result = inner()', 5),
    # and the inner declaration really is a DIFFERENT shape, not the outer
    # one seen twice: the outer annotation still wants `x`
    ('shape S = @{x: num}\n'
     'fn inner() { shape S = @{y: num}\n1 }\n'
     'fn outer(p: S) { p.x }\nlet result = outer(@{x: 2})', 2),
]

SHAPE_MISS_CASES = [
    'shape P = @{x: num, y: num}\nfn mag(p: P) { p.x + p.y }\n'
    'let result = mag(@{x: 3})',
    'shape P = @{x: num}\nfn mk() -> P { @{y: 1} }\nlet result = mk()',
    'shape P = @{x: num}\nlet f = fn() -> P { 5 }\nlet result = f()',
]
# round 342 (v0.18): the out-of-scope `-> L` case used to live here, as a
# RUN-time miss on both sides (host: the `_UnboundRetType` sentinel; guest:
# `__unbound_ret`). It is now a PARSE error on both sides and has moved to
# SHAPE_PARSE_ERRORS below, together with the parameter and shape-field
# annotations that used to fail two other ways from the same mistake.

# (source, the host's exact reason with its `(line N)` suffix removed)
SHAPE_PARSE_ERRORS = [
    ('shape Foo = @{x: Foo}\nlet result = 1', "unknown type 'Foo'"),
    ('shape A = @{b: B}\nshape B = @{x: num}\nlet result = 1',
     "unknown type 'B'"),
    ('shape num = @{x: num}\nlet result = 1',
     "'num' is a reserved type name"),
    ('shape P = @{x: num}\nshape P = @{y: num}\nlet result = 1',
     "shape 'P' is already declared in this block"),
    ('shape P = @{x: num, x: str}\nlet result = 1', "duplicate field 'x'"),
    ('fn f(a: Nope) { a }\nlet result = 1', "unknown type 'Nope'"),
    ('fn f() -> Nope { 1 }\nlet result = 1', "unknown type 'Nope'"),
    # v0.18 (round 342): a shape whose BLOCK has closed. All three
    # annotation positions are one `parse_type` and now give one sentence;
    # before v0.18 the host accepted all three and produced three different
    # RUN-time outcomes (a `_UnboundRetType` miss, an "unbound name" miss,
    # and a silently miss-valued shape field).
    ('fn g() { shape L = @{x: num}\n1 }\nfn f() -> L { 1 }\nlet result = 1',
     "type 'L' is not in scope here"),
    ('fn g() { shape L = @{x: num}\n1 }\nfn f(p: L) { p }\nlet result = 1',
     "type 'L' is not in scope here"),
    ('fn g() { shape L = @{x: num}\n1 }\nshape W = @{i: L}\nlet result = 1',
     "type 'L' is not in scope here"),
]

LINE_SUFFIX = re.compile(r" \(line \d+\)")


def guest_reason(payload):
    assert isinstance(payload, Miss), payload
    return LINE_SUFFIX.sub("", payload.reasons[0])


def host_parse_error(src):
    """The host raises on a bad `shape`; the guest returns a miss (it is a
    Whence program, and a parse failure is an ordinary value there). Both
    are the same event, so normalise the host side to the guest's shape."""
    try:
        Interpreter().run(src)
    except (ParseError, LexError) as e:
        return str(e).split(" at line ")[0]
    return None


@pytest.mark.whence_slow
def test_shape_values_agree_host_vs_guest():
    sources = [src for src, _ in SHAPE_VALUE_CASES]
    guest = guest_eval_all(sources)
    bad = []
    for (src, want), g in zip(SHAPE_VALUE_CASES, guest):
        h = host_eval(src)
        assert h is not None, src
        if not (deep_eq(h.payload, g.payload) is True):
            bad.append((src, h.payload, g.payload))
        elif h.payload != want or type(h.payload) is not type(want):
            # pinning the literal too, so a case that agrees for the wrong
            # reason (both sides missing, both sides 0) cannot pass quietly
            bad.append((src, "expected %r" % (want,), h.payload))
    assert bad == [], bad


@pytest.mark.whence_slow
def test_shape_misses_agree_host_vs_guest_including_the_wording():
    """Stronger than `payloads_agree`: the reason TEXT must match too, not
    just missed-ness. The `-> Shape` mismatch message goes through the
    host's `_type_match` `desc` (the shape's `__shape` name, not "record")
    and the guest's `guest_spec_name`; the unbound case goes through the
    host's `_UnboundRetType` branch and the guest's `__unbound_ret`
    sentinel. Both wordings are reproduced exactly."""
    guest = guest_eval_all(SHAPE_MISS_CASES)
    bad = []
    for src, g in zip(SHAPE_MISS_CASES, guest):
        h = host_eval(src)
        if not isinstance(h.payload, Miss) or not isinstance(g.payload, Miss):
            bad.append((src, h.payload, g.payload))
        elif guest_reason(h.payload) != guest_reason(g.payload):
            bad.append((src, h.payload.reasons[0], g.payload.reasons[0]))
    assert bad == [], bad
    # and the message round 338 was actually about, spelled out
    h_ret = host_eval(SHAPE_MISS_CASES[1]).payload
    # v0.20 (round 348) appended the field clause; round 338's own point —
    # that the message names the SHAPE and not "record" — is the prefix.
    assert guest_reason(h_ret) == ("return value of mk expected P, "
                                   "got record (no field 'x')")
    # its companion — the out-of-scope `-> L` miss — is gone from this list
    # since v0.18 (round 342): the annotation no longer parses, so the pair
    # is checked by wording in `SHAPE_PARSE_ERRORS` instead.


@pytest.mark.whence_slow
def test_shape_declaration_errors_agree_host_vs_guest_by_wording():
    """The six-way blind spot described in this section's header. Every one
    of these misses on BOTH sides even on the pre-338 guest, so only the
    wording distinguishes a guest that understands `shape` from one that
    stopped at the `=`."""
    sources = [src for src, _ in SHAPE_PARSE_ERRORS]
    guest = guest_eval_all(sources)
    bad = []
    for (src, want), g in zip(SHAPE_PARSE_ERRORS, guest):
        assert host_parse_error(src) == want, (src, host_parse_error(src))
        if guest_reason(g.payload) != want:
            bad.append((src, want, g.payload.reasons[0]))
    assert bad == [], bad


@pytest.mark.whence_slow
def test_shape_needs_three_adjacent_tokens_on_both_sides():
    """`shapes_declared_before` matches `shape` NAME `=` ADJACENTLY, which
    is what the host's own `peek(1)`/`peek(2)` require — neither skips a
    NEWLINE. So `shape` alone on a line is NOT a declaration anywhere, and
    both sides refuse the same program. This is the load-bearing premise of
    recovering the host's mutable `self.shapes` from the token stream: were
    the host to skip newlines here, the guest's scan would over-accept."""
    src = 'shape\nP = @{x: num}\nlet result = 1'
    # Was `== "unexpected '='"`. v0.22 (round 354, decision 32) appends a
    # named cure to this exact parse error, so the host string is no longer
    # EQUAL to the guest's — it starts with it, and the guest assertion
    # below has always been a containment. Relaxed to a prefix rather than
    # deleted, because the premise being tested is "both sides refuse the
    # same program at the same token", which the prefix still carries.
    # The second line keeps the relaxation honest: it pins that the ONLY
    # difference is v0.22's hint, so this cannot silently absorb some other
    # change to the message. `tests/test_v22.py` owns the hint's wording;
    # this is deliberately a weaker check than that one, not a copy of it.
    host = host_parse_error(src)
    assert host.startswith("unexpected '='"), host
    assert "no assignment" in host, host
    g, = guest_eval_all([src])
    assert isinstance(g.payload, Miss), g.payload
    assert "unexpected token '='" in g.payload.reasons[0]


@pytest.mark.whence_slow
def test_shape_line_divergence_is_pre_existing_not_new():
    """Every reason comparison above strips a `(line N)` suffix, because the
    guest AST carries no line numbers and the host attaches self_eval.lang's
    OWN line to a miss the guest constructs (this file's module docstring
    and the example's header both document it). Pinned as pre-existing
    rather than asserted away: the identical divergence appears on a
    PRIMITIVE `-> num` return, which has behaved this way since round 158."""
    src = 'fn t(a: num) -> num { "x" }\nlet result = t(1)'
    h = host_eval(src)
    g, = guest_eval_all([src])
    assert h.payload.reasons[0] == "return value of t expected num, got str (line 2)"
    assert LINE_SUFFIX.sub("", g.payload.reasons[0]) == \
        "return value of t expected num, got str"
    assert LINE_SUFFIX.search(g.payload.reasons[0]) is not None
    assert g.payload.reasons[0] != h.payload.reasons[0]
