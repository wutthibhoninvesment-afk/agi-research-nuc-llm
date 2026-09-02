"""v0.44 (round 452, language C) — the cap that was two promises and one number.

Round 450's next step asked whether `full_show` should carry a
depth-bounded-but-deeper cap of its own, and said the question needed a
number nobody had taken: *the deepest value any corpus program actually
builds*. `depthcensus.py` takes it. The answer, over all 33 programs in
`examples/`, is **14** — `examples/self_host.lang`'s `let p7`, the AST the
Whence-in-Whence parser builds, spine

    Record>WList>Record>Record>WList>Record>Record>Record>WList>Record>
    Record>WList>Record>Record>str

against a full rendering that showed **4** levels. The language's own
self-hosting program built values three and a half times deeper than the
language could print, and `print(p7)` was 139 characters ending in
`stmts: […]`.

Decision 53 splits `SHOW_NEST` into two constants, because it was never one
cap — it was two promises (decision 37 wrote both down; decision 52 restated
them) reading one number:

    SHOW_NEST      = 3    the BOUNDED snapshot: `show()`, every miss message,
                          `Prov.show`. UNCHANGED, and this file pins that.
    FULL_SHOW_NEST = 24   the FULL rendering: `print`, `str`. 10 levels of
                          headroom over the deepest thing the corpus builds.
    FULL_SHOW_NODES = 20000  new, and required by the change — see below.

TWO MEASUREMENTS PAID FOR THE NEW NUMBER, and both are re-taken here rather
than quoted.

**Host frames.** `Interpreter.HOST_RESERVE`'s own comment lists "rendering
(depth-capped)" among the three things its 250-frame reserve covers, so
raising the cap spends that reserve. v0.43's full path cost 3 frames per
container level — one `_show`, one `show_payload`, one generator expression —
so 24 levels would have been ~79 frames, a third of the reserve against a
bound-by-construction of ~110 for everything else in it. v0.44's full path
calls `_show` directly from an explicit loop: **1 frame per level**, 27 at
the new cap versus 13 at v0.43's.

**Output size, which the cap was bounding without anyone saying so.** Round
450's next step said "`full_show` already pays O(n) in elements". That is
false for a value with SHARING, and Whence values share on purpose: `WList`
is a view over an append-only buffer, so the value graph is a DAG and a
renderer walks a DAG as a TREE — once per PATH. Twelve levels of `[v, v]`
render 108 characters at a cap of 3 and 40956 at a cap of 12. 2^n, not O(n).
So the depth cap had a second, undocumented job, and it does not survive
being raised 4 -> 25; `FULL_SHOW_NODES` takes that job over, and takes it
over in the WIDTH direction too, which v0.43 never bounded at all.

AND ONE THING WENT AWAY. v0.43 computed "the misses the rendering named" with
a SECOND walk (`values.named_misses`) written to mirror `_show` branch for
branch, held to it by a differential test — the shape
`skills/suppressor-shares-the-detector-shape/SKILL.md` exists to warn about.
Moving the renderer's bound is exactly the edit that breaks a mirror, so the
mirror is gone: `full_show_named` collects the misses AS IT RENDERS, and
`named_misses` is its second return value. The differential in test_v43.py
still passes and is now tautological, which is the intended end state — the
property stopped needing a guard.
"""
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import depthcensus                                              # noqa: E402
import depthcensus as DC                                        # noqa: E402
from whence.interp import Interpreter                           # noqa: E402
from whence.parser import parse                                 # noqa: E402
from whence import values as V                                  # noqa: E402
from whence.values import (                                     # noqa: E402
    FULL_SHOW_NEST, FULL_SHOW_NODES, Miss, Prov, Record, SHOW_NEST,
    full_show, full_show_named, named_misses, show_payload, wlist,
)


def run(src, out=None):
    i = Interpreter(out=out if out is not None else (lambda s: None))
    i.run(src)
    return i


def printed(src):
    lines = []
    run(src, out=lines.append)
    return lines


def report(src):
    """Everything the run tells a reader: stdout, then the drop report."""
    import run as RUNPY
    lines = []
    i = run(src, out=lines.append)
    RUNPY.report_drops(i, out=lines.append)
    return "\n".join(lines)


def node(payload):
    return Prov("lit", "", 1, (), value=payload)


def nest_list(depth, inner=None):
    """A list nested `depth` containers deep around a scalar (or `inner`)."""
    v = node(1) if inner is None else inner
    for _ in range(depth):
        v = node(wlist([v]))
    return v


# --------------------------------------------------------------------------
# 1. the split itself
# --------------------------------------------------------------------------

def test_the_two_caps_are_different_constants():
    """The one-line statement of decision 53."""
    assert SHOW_NEST == 3
    assert FULL_SHOW_NEST == 24
    assert FULL_SHOW_NEST > SHOW_NEST


def test_the_snapshot_cap_did_not_move():
    """`show()` is the published bounded renderer (decision 37) and eleven
    generated mutation killers quote its output. v0.44 changes `full_show`;
    if it had also changed this, the split would be pointless."""
    deep = nest_list(6)
    assert show_payload(deep.value) == "[[[[…]]]]"
    assert V._show(deep.value, V.SHOW_LIMIT, 0) == "[[[[…]]]]"


def test_the_full_rendering_now_shows_the_snapshot_plus_twenty_one_levels():
    """The two caps, measured against each other on the same value rather
    than read off the constants."""
    def levels(text):
        return text.count("[")
    v = nest_list(40).value
    assert levels(show_payload(v)) == SHOW_NEST + 1
    assert levels(full_show(v)) == FULL_SHOW_NEST + 2   # +1 truncated level


@pytest.mark.parametrize("depth", [1, 2, FULL_SHOW_NEST, FULL_SHOW_NEST + 1])
def test_every_depth_up_to_the_cap_renders_in_full(depth):
    v = nest_list(depth).value
    text = full_show(v)
    assert "…" not in text, (depth, text)
    assert text == "[" * depth + "1" + "]" * depth


def test_one_level_past_the_cap_is_where_it_stops():
    v = nest_list(FULL_SHOW_NEST + 2).value
    r = full_show_named(node(v))
    assert r.depth_stopped is True
    assert r.node_stopped is False
    assert "…" in r.text


# --------------------------------------------------------------------------
# 2. the corpus fact this version exists for
# --------------------------------------------------------------------------

def _self_host_deepest():
    """Rebuild `examples/self_host.lang`'s deepest value the way the census
    does. This is the finding, so it is re-derived rather than quoted."""
    path = os.path.join(ROOT, "examples", "self_host.lang")
    drops = []
    real = Interpreter._note_drop

    def hooked(self, v, at):
        drops.append(v)
        return real(self, v, at)

    Interpreter._note_drop = hooked
    try:
        it = Interpreter(out=lambda s: None, gc_relief=True)
        env = it.run(open(path).read())
    finally:
        Interpreter._note_drop = real
    roots = [v for v in env.vars.values() if depthcensus._is_node(v)]
    roots += [d for d in drops if depthcensus._is_node(d)]
    nodes, _ = depthcensus.reachable(roots)
    memo, alive = {}, []
    best = max(nodes, key=lambda n: depthcensus.depth_of(n, memo, alive))
    return best, memo[id(best)]


@pytest.mark.whence_slow
def test_the_deepest_value_in_the_corpus_is_a_self_hosted_ast_14_deep():
    best, d = _self_host_deepest()
    assert d == 14, "the corpus number moved — re-run depthcensus.py"
    assert isinstance(best.value, Record)
    assert depthcensus.spine_of(best)[:3] == ["Record", "WList", "Record"]
    assert "program" in full_show(best.value)


@pytest.mark.whence_slow
def test_v043_truncated_that_value_and_v044_does_not():
    """THE POINT OF THE VERSION, as a differential on one real value.

    `show_payload(p, None)` is v0.43's full path, still live and unchanged
    for exactly this comparison: same function, same value, old cap."""
    best, d = _self_host_deepest()
    new = full_show(best.value)                   # v0.44's cap
    cap = V.FULL_SHOW_NEST
    try:
        V.FULL_SHOW_NEST = SHOW_NEST              # exactly v0.43's cap
        old = full_show(best.value)
    finally:
        V.FULL_SHOW_NEST = cap
    # 139 -> 589 characters, measured round 452. The v0.43 rendering stops
    # inside the AST's second `stmts` and never reaches the expression the
    # function actually evaluates.
    assert old.endswith('stmts: […]}, kind: "fndef", name: "go", '
                        'param_types: [], params: ["n"], ret_type: ""}]}')
    assert "…" not in new
    assert len(new) > 4 * len(old)
    assert d <= FULL_SHOW_NEST + 1
    # and the SNAPSHOT, which decision 53 did not move, is shallower still
    assert len(show_payload(best.value, None)) < len(old)


# --------------------------------------------------------------------------
# 3. the two measurements that set the constants
# --------------------------------------------------------------------------

def _frames_for(fn, val):
    """Smallest host-frame headroom at which `fn(val)` survives. Bisection,
    not instrumentation: a counting wrapper adds a frame per level and
    inflates the number being taken (round 452 read 4/level that way and 3
    by bisection)."""
    base, f = 0, sys._getframe()
    while f is not None:
        base += 1
        f = f.f_back
    old = sys.getrecursionlimit()
    lo, hi = 1, 600
    try:
        while lo < hi:
            mid = (lo + hi) // 2
            sys.setrecursionlimit(base + mid)
            try:
                fn(val)
                hi = mid
            except RecursionError:
                lo = mid + 1
            finally:
                sys.setrecursionlimit(old)
    finally:
        sys.setrecursionlimit(old)
    return lo


def test_the_full_rendering_costs_one_host_frame_per_level():
    """The measurement that made the deeper cap affordable. Deltas, not
    absolutes: the absolute depends on the caller's own stack."""
    a = _frames_for(full_show, nest_list(5).value)
    b = _frames_for(full_show, nest_list(20).value)
    assert b - a == 15, (a, b)
    assert _frames_for(full_show, nest_list(FULL_SHOW_NEST).value) < 40


def test_the_old_path_cost_three_frames_per_level_and_still_does():
    """v0.43's full path is `show_payload(p, None)` with no ctx, and v0.44
    left it byte-identical — so the comparison behind the new constant can
    be re-run rather than believed."""
    old = lambda v: show_payload(v, None)          # noqa: E731
    a = _frames_for(old, nest_list(1).value)
    b = _frames_for(old, nest_list(3).value)
    assert b - a == 6, (a, b)                      # 3 frames x 2 levels


def test_rendering_a_shared_dag_is_exponential_in_depth_not_linear():
    """Round 450's "already pays O(n) in elements", falsified.

    Sixteen `let v = [v, v]` over a 2-element list is 33 distinct nodes and
    2^16 rendering PATHS. Measured across the OLD cap's range, where the
    growth is visible; the nesting is 16 deep so that even the widest cap
    measured here is still truncating, or the curve flattens because the
    value bottomed out rather than because anything bounded it."""
    v = node(wlist([node(1), node(2)]))
    for _ in range(16):
        v = node(wlist([v, v]))
    # The budget is lifted for this measurement on purpose: the point is
    # what the DEPTH cap alone does and does not bound. With the real budget
    # in force the last step reads 5.7x instead of 8x, which is the budget
    # doing the job this test exists to show it has to do.
    sizes = []
    for cap in (3, 6, 9, 12):
        sizes.append(len(full_show_named(v, cap=cap, budget=10 ** 9).text))
    for a, b in zip(sizes, sizes[1:]):
        assert b > 7 * a, sizes           # doubling per level => 8x per 3
    assert sizes == [108, 892, 7164, 57340]
    # At cap 12 the budget does NOT fire (2+4+...+2^13 = 16382 rendered
    # nodes, under 20000) and the text is the full 57340 characters — the
    # depth cap alone was enough there. One level further and it is not.
    assert len(full_show_named(v, cap=12).text) == sizes[-1]
    unbounded14 = full_show_named(v, cap=14, budget=10 ** 9).text
    assert len(full_show_named(v, cap=14).text) < len(unbounded14)


def test_the_node_budget_is_what_bounds_that_and_it_says_so():
    v = node(wlist([node(1), node(2)]))
    for _ in range(20):
        v = node(wlist([v, v]))
    t0 = time.time()
    r = full_show_named(v)
    elapsed = time.time() - t0
    assert r.node_stopped is True
    assert r.depth_stopped is False, "20 < FULL_SHOW_NEST: depth is not why"
    assert r.text.count(",") <= FULL_SHOW_NODES
    assert len(r.text) < 20 * FULL_SHOW_NODES
    assert elapsed < 5.0
    assert ", …" in r.text, "a rendering that stopped must say so"


def test_the_deepest_value_this_repo_builds_is_max_depth_not_fourteen():
    """WHY A DEEPER CAP AND NOT NO CAP. The corpus reading (14) is a fact
    about `examples/`, and the tempting conclusion from it — that the bound
    could simply go away — is refuted by a program already in this tree.

    A runaway recursion whose unwind builds one record per frame has a
    value depth of exactly the `max_depth` it is RUN at. At 1 host frame per
    level an unbounded renderer needs 20000 frames — past CPython's default
    1000 and past run.py's raised 6000.

    Round 458 corrected two sentences that stood here, both about
    attribution. This docstring named
    `tests/test_generated_killers.py::test_kill_values_py_139_arith_120` as
    the builder of the 20000-deep value; that file's `canonical()` defaults
    to `max_depth=500`, so it builds a 500-deep one, and the test that
    reaches 20000 is THIS one, which constructs its own `Interpreter()` at
    the default two lines below. And "`max_depth` is the real upper bound on
    value depth in Whence" is false — see the test underneath, and
    SPEC.md § Decision 55."""
    src = ("fn wrap(n) { if n == 0 { @{v: 0} } else { @{v: wrap(n - 0)} } }\n"
           "let rec = wrap(1)\n")
    from whence.interp import Env
    it = Interpreter(out=lambda s: None)
    env = it.run(src)
    rec = env.vars["rec"]
    assert DC.depth_of(rec) == it.max_depth == 20000
    r = full_show_named(rec)
    assert r.depth_stopped is True
    assert r.text.count("@{") == FULL_SHOW_NEST + 2
    assert len(r.text) < 400, "the cap is what makes this printable at all"


def test_max_depth_bounds_recursion_and_not_value_depth():
    """Round 458. `max_depth` caps what a runaway RECURSION builds; ordinary
    code then wraps the result and nothing stops it, so it is not a bound on
    value depth at all. The repo already held the refutation:
    `test_v04.py::test_deep_eq_is_iterative` asks `[rec] == [rec]` and so
    builds a value `max_depth + 1` deep -- 20001 at the interpreter default,
    one past FULL_SHOW_NODES."""
    base = "fn wrap(n) { @{v: wrap(n)} }\nlet rec = wrap(1)\n"
    seen = []
    for tail in ("let result = rec", "let result = [rec]",
                 "let result = [[rec]]", "let result = [[[[[rec]]]]]"):
        it = Interpreter(out=lambda s: None, max_depth=300)
        env = it.run(base + tail)
        seen.append(DC.depth_of(env.vars["result"]))
    assert seen == [300, 301, 302, 305]


def test_the_budget_bounds_width_which_v043_did_not_bound_at_all():
    """A contract change, stated. v0.43 rendered every element of a list of
    any size; the corpus's largest full rendering is 30 nodes, so 20000 is
    666x the live maximum and this is a safety valve, not a limit anyone
    reaches."""
    wide = node(wlist([node(i) for i in range(FULL_SHOW_NODES + 500)]))
    r = full_show_named(wide)
    assert r.node_stopped is True
    assert r.text.endswith(", …]")
    small = node(wlist([node(i) for i in range(100)]))
    assert full_show_named(small).node_stopped is False


# --------------------------------------------------------------------------
# 4. v0.43's property still holds at the new bounds
# --------------------------------------------------------------------------

MONOTONE_CASES = [
    "[nosuch(1)]",
    "[" * (FULL_SHOW_NEST + 1) + "nosuch(1)" + "]" * (FULL_SHOW_NEST + 1),
    "[" * (FULL_SHOW_NEST + 5) + "nosuch(1)" + "]" * (FULL_SHOW_NEST + 5),
]


@pytest.mark.parametrize("expr", MONOTONE_CASES)
def test_a_print_still_never_removes_a_reason(expr):
    """v0.43's property, re-run at v0.44's boundary — including one case ON
    the new cap (rendered, so the reason is in stdout) and one PAST it
    (not rendered, so the drop report has it). The property is that the
    reader is told either way."""
    bare = report(expr + "\n")
    shown = report("print(%s)\n" % expr)
    assert "unbound name 'nosuch'" in bare
    assert "unbound name 'nosuch'" in shown


def test_a_miss_the_budget_did_not_reach_is_still_reported_as_a_drop():
    """THE NEW BOUND'S VERSION OF THE V0.43 DEFECT. A miss past the NODE
    budget is exactly as unrendered as one past the depth cap, and the
    suppressor must not claim it. It cannot, because the collector is the
    renderer — this test is here to prove the new bound did not open a hole
    the old one closed."""
    src = ("let big = map(fn(i) { i }, range(1, %d))\n"
           "print(push(big, nosuch(1)))\n" % (FULL_SHOW_NODES + 200))
    i = run(src)
    assert i.dropped_total == 1, "the unrendered miss went unreported"
    assert "unbound name 'nosuch'" in i.dropped[0]["reasons"][0]


def test_the_suppressor_cannot_outrun_the_renderer_by_construction():
    """`named_misses` is `full_show_named(...).misses` — one walk. Asserted
    on identity of the walk, not on agreement of two walks: the v0.43
    differential (still in test_v43.py, still passing) is what agreement
    looked like when there were two."""
    src = "[" * 3 + "nosuch(1)" + "]" * 3 + "\n"
    prog = parse(src)
    it = Interpreter(out=lambda s: None)
    from whence.interp import Env
    env = Env(it.globals, it)
    v = it.exec_stmt(prog.stmts[0], env)
    r = full_show_named(v)
    assert [id(n) for n in named_misses(v)] == [id(n) for n in r.misses]
    for n in r.misses:
        assert "; ".join(n.value.reasons) in r.text


def test_printing_a_harmless_container_still_marks_nothing():
    i = run("print([1, [2, [3]]])\n")
    assert i._observed_aggr == {}


# --------------------------------------------------------------------------
# 5. the corpus is unmoved, which is the honest half of the result
# --------------------------------------------------------------------------

CORPUS_UNCHANGED = [
    "hello.lang", "show.lang", "history.lang", "blame.lang", "sales.lang",
    "provenance.lang", "guess.lang", "shapes.lang", "effects.lang",
]


@pytest.mark.parametrize("name", CORPUS_UNCHANGED)
def test_raising_the_cap_changed_no_corpus_output(name):
    """The stake, measured. Max PRINTED depth across all 33 programs is 2,
    so a cap of 4 and a cap of 25 render every corpus print identically.
    v0.44 is a change to what the language CAN show, not to what it does
    show — and that is worth a test rather than a sentence, because the
    sentence is what a reader would doubt."""
    path = os.path.join(ROOT, "examples", name)
    src = open(path).read()
    new_lines = []
    run(src, out=new_lines.append)

    old_cap, old_budget = V.FULL_SHOW_NEST, V.FULL_SHOW_NODES
    old_lines = []
    try:
        V.FULL_SHOW_NEST, V.FULL_SHOW_NODES = SHOW_NEST, 10 ** 9
        run(src, out=old_lines.append)
    finally:
        V.FULL_SHOW_NEST, V.FULL_SHOW_NODES = old_cap, old_budget
    assert new_lines == old_lines
