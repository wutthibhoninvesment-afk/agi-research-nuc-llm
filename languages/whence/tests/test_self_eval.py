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
import subprocess
import sys

from whence.interp import Interpreter, deep_eq
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


def test_example_runs_green():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "run.py"), EXAMPLE],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "76 passed, 0 failed" in r.stdout
    assert "all in Whence" in r.stdout


def test_parser_section_matches_self_host():
    # the guest lexer+parser is self_host.lang lines 28..533, verbatim;
    # if one file changes, the other must change with it (round 158: grew
    # from 420 to 485 lines adding `: Type`/`-> Type` guest parity; round
    # 164: 485 to 533 adding `effects [...]` clause skipping)
    host_lines = open(SELF_HOST).read().splitlines()
    section = "\n".join(host_lines[27:533])
    assert section.startswith("# ---- character classes")
    assert section.rstrip().endswith(
        "fn parse_whence(src) { parse_program(lex_all(src)) }")
    assert section in open(EXAMPLE).read()


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
