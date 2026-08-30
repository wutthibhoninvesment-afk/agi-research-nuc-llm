"""Whence v0.30 (round 378, language C) — decision 38: the provenance-query
family answers from the GUEST history.

v0.29 (round 374) recorded **E4**, the fourth and largest exemption in the
host-vs-guest miss-message differential, in these words:

    the guest answers the provenance-query family from the wrong history.
    ... `apply_host_builtin` calls the host `steps` on the guest's PAYLOAD,
    and that payload's host provenance is the evaluator's, not the
    program's.

`len(steps(1 + 2))` was 4 on the host and **284** in the guest — 280 of
those steps being `self_eval.lang`'s own execution: its line numbers, its
locals `a0`/`p0`, its internal probe misses. Rounds 206 and 218 wired the
family through with the comment "`a0`'s real host provenance is already
there for free". The provenance that was there belonged to the wrong
program.

v0.29 left it as an exemption rather than a fix because a host step record
is `@{op, detail, line, show, depth, inputs, count, value}` and a guest box
is `@{v, op, ins}`, and predicted the shipping form would be "the guest's
`steps` may over-report a SHARED node, and says so". That is what shipped,
plus two recoveries v0.29 did not expect:

  * **`Prov.label()` is invertible.** A label is `op + " " + detail` and no
    host op contains a space, so splitting the guest's label at the FIRST
    space recovers both halves — no `mkb` widening, no edit at its several
    hundred call sites. `test_the_label_split_is_exact_for_every_non_miss_op`.
  * **A miss node's `detail` IS its reason.** `mk_miss` stores the reason
    sentence as the detail and no call site in the tree overrides it
    (`detail=` appears zero times), so `reasons()` plus dropping the
    `(line N)` suffix recovers the detail the guest label does not carry.
    `test_a_miss_nodes_detail_is_recovered_from_its_reason`.

THE THREE DIVERGENCES THAT REMAIN, one test each, all measured:

  1. **No identity, so a count is an UPPER bound** —
     `test_a_shared_node_is_over_reported_never_under_reported`.
  2. **No lines** — `test_every_guest_step_reports_line_zero`.
  3. **No merging** — `test_the_guest_never_merges_a_tail_loop`.

And `diverge`/`contrast` were still delegated and still E4. **v0.31 (round
380) retired them too**, so E4 is gone entirely and the two tests that
pinned it are now its retirement notice:
`test_diverge_and_contrast_no_longer_delegate` and
`test_diverge_and_contrast_now_answer_from_the_guest_history`. See
`tests/test_v31.py`.
"""

import os
import re
import subprocess
import sys

import pytest

from whence.interp import Interpreter
from whence.values import Miss, Record, WList

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "self_eval.lang")
MARKER = "# ==== SELF-TESTS"
LINE_SUFFIX = re.compile(r" \(line \d+\)")
# `contrast` renders two columns, and the left one is padded to the width
# of the WIDEST left line. Removing the host's `  (line N)` suffix therefore
# changes the padding too, so a suffix-stripped host string is not
# comparable to the guest's character for character until the column rule is
# re-normalised. This does both, on either side.
CONTRAST_LINE = re.compile(r"  \(line \d+\)")


def normalize_contrast(text):
    out = []
    for line in text.split("\n"):
        line = CONTRAST_LINE.sub("", line)
        line = re.sub(r" +\u2502 ", " \u2502 ", line)
        out.append(line.rstrip())
    return "\n".join(out)



def library_source():
    src = open(EXAMPLE, encoding="utf-8").read()
    assert MARKER in src
    return src.split(MARKER)[0]


def escape(s):
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r"))


def deep(p):
    """A payload as comparable plain Python. Miss reasons lose their
    `(line N)` suffix: a guest miss carries a self_eval.lang line, which is
    this evaluator's one long-documented provenance divergence and is not
    what any test in this file is about."""
    if isinstance(p, Miss):
        return ("MISS", tuple(LINE_SUFFIX.sub("", r) for r in p.reasons))
    if isinstance(p, WList):
        return tuple(deep(e.payload) for e in p)
    if isinstance(p, Record):
        return tuple(sorted((k, deep(v.payload))
                            for k, v in p.fields.items()))
    return p


def host(src):
    box = Interpreter(out=lambda s: None, seed=7).run(src).get("r")
    assert box is not None, src
    return deep(box.payload)


def guest_batch(sources, lib):
    """One interpreter run for the whole batch — a per-case run re-parses
    the ~3 500-line library each time (0.11 s/build, measured round 377),
    which for a 13-case list is most of the wall clock."""
    parts = [lib]
    for i, src in enumerate(sources):
        parts.append('let __out%d = run_src("%s")\n' % (i, escape(src)))
    env = Interpreter(out=lambda s: None, seed=7).run("".join(parts))
    out = []
    for i, src in enumerate(sources):
        rec = env.get("__out%d" % i)
        assert rec is not None, src
        out.append(deep(rec.payload.fields["v"].payload))
    return out


# --------------------------------------------------------------------------
# the agreement corpus
# --------------------------------------------------------------------------
# Every case binds `r`, so `host()` and the guest's `run_src` result are the
# same observable. Kept small and hand-picked on purpose: this is the fast
# tier, and the wide statement about the family lives in
# `test_v29.py`'s 11 326-case atlas, which this round moves off E4.

AGREE = [
    # the two v0.29 pins, verbatim
    'let x = 1 + 2\nlet r = len(steps(x))',
    'let x = 1 / 0\nlet r = len(blame(x))',
    # every field of every step record, for a value and for a miss
    'let x = 1 + 2\nlet r = map(fn(s) { s.op }, steps(x))',
    'let x = 1 + 2\nlet r = map(fn(s) { s.detail }, steps(x))',
    'let x = 1 + 2\nlet r = map(fn(s) { s.show }, steps(x))',
    'let x = 1 + 2\nlet r = map(fn(s) { s.depth }, steps(x))',
    'let x = 1 + 2\nlet r = map(fn(s) { s.inputs }, steps(x))',
    'let x = 1 + 2\nlet r = map(fn(s) { s.count }, steps(x))',
    # (`s.line` is deliberately NOT here — see divergence (2) below)
    'let x = 1 / 0\nlet r = map(fn(s) { s.op }, steps(x))',
    'let x = 1 / 0\nlet r = map(fn(s) { s.detail }, steps(x))',
    'let x = 1 / 0\nlet r = map(fn(s) { s.show }, steps(x))',
    'let x = 1 + "a"\nlet r = map(fn(s) { s.detail }, steps(x))',
    # `value` is the historic value itself, so it can be computed with
    'let x = 1 + 2\nlet r = fold(fn(a, s) { a + s.value }, 0, steps(x))',
    # the pattern form: label, op and detail all address a step
    'let x = 1 + 2\nlet r = len(steps(x, "+"))',
    'let x = 1 + 2\nlet r = len(steps(x, "let x"))',
    'let x = 1 + 2\nlet r = len(steps(x, "let"))',
    'let x = 1 + 2\nlet r = len(steps(x, "x"))',
    'let x = 1 + 2\nlet r = len(steps(x, "literal"))',
    'let x = 1 + 2\nlet r = len(steps(x, "nope"))',
    'let x = 1 / 0\nlet r = len(steps(x, "division by zero"))',
    # argument checking: a miss pattern propagates, a non-string misses
    # with the v0.22 order hint, and both are TOTAL in their first argument
    'let x = 1 + 2\nlet r = steps(x, 1)',
    'let x = 1 + 2\nlet r = steps(x, 1 / 0)',
    'let r = steps("a", 1)',
    'let r = at(1 + 2, 5)',
    'let r = at(1 + 2, 1 / 0)',
    'let r = at(1 + 2, "nope")',
    # `at` returns the historic value itself
    'let x = 1 + 2\nlet r = (at(x, "+")).show',
    'let x = 1 + 2\nlet r = (at(x, "+")).inputs',
    'let x = 1 + 2\nlet r = (at(x, "+")).depth',
    'let x = 1 + 2\nlet r = at(x, "+") + 0',
    'let x = 1 / 0\nlet r = (at(x, "division by zero")).op',
    # a query accepts `why value` as well as a value
    'let x = 1 + 2\nlet r = len(steps(why x))',
    # calls, records, lists, and totality on plain values
    'fn f(n) { n * 2 }\nlet y = f(3)\nlet r = map(fn(s) { s.op }, steps(y))',
    'fn f(n) { n * 2 }\nlet y = f(3)\nlet r = map(fn(s) { s.detail }, steps(y))',
    'let r = len(steps(1))',
    'let r = len(steps([1, 2]))',
    'let r = len(blame(1))',
    'let r = len(steps(1 / 0))',
    'let x = 1 + "a"\nlet r = map(fn(s) { s.op }, blame(x))',
    'let x = [1, 2][9]\nlet r = len(blame(x))',
]


@pytest.fixture(scope="module")
def lib():
    return library_source()


@pytest.fixture(scope="module")
def agree_pairs(lib):
    return list(zip(AGREE, (host(s) for s in AGREE), guest_batch(AGREE, lib)))


def test_the_provenance_family_agrees_with_the_host(agree_pairs):
    """E4's core claim, inverted. Before this round every one of these
    answered from `self_eval.lang`'s own execution."""
    bad = [(s, h, g) for s, h, g in agree_pairs if h != g]
    assert bad == [], bad[:3]


def test_the_two_v29_pins_are_exact(agree_pairs):
    """`test_v29.py::test_the_provenance_family_is_still_exempt_and_still_
    wrong` asserted `guest_steps > 50` and `guest_blame > 1` against host
    4 and 1. Named separately from the corpus above because these two
    numbers are the ones v0.29 published."""
    by_src = {s: (h, g) for s, h, g in agree_pairs}
    assert by_src['let x = 1 + 2\nlet r = len(steps(x))'] == (4, 4)
    assert by_src['let x = 1 / 0\nlet r = len(blame(x))'] == (1, 1)


# --------------------------------------------------------------------------
# the two recoveries
# --------------------------------------------------------------------------

def test_the_label_split_is_exact_for_every_non_miss_op(lib):
    """`Prov.label()` is `op + " " + detail`. Splitting at the FIRST space
    inverts it iff no host `op` contains a space. Asserted over the host's
    OWN vocabulary rather than over the guest's, so widening the host is
    what makes it red."""
    from whence.values import walk_steps
    seen = set()
    for src in ('let a = 1 + 2\nlet b = a * 10\nlet r = b - 1',
                'fn f(n) { if n < 2 { n } else { f(n - 1) } }\nlet r = f(3)',
                'let r = len([1, 2]) + (@{a: 1}).a + [3, 4][0]',
                'let r = (1 / 0) rescue 9'):
        root = Interpreter(out=lambda s: None, seed=7).run(src).get("r")
        for node, _d in walk_steps(root):
            seen.add((node.op, node.detail, node.label()))
    assert seen
    bad = [t for t in seen if " " in t[0]]
    assert bad == [], bad
    # and the inversion itself, on every label collected
    for op, detail, label in seen:
        head, _, tail = label.partition(" ")
        if detail and op:
            assert (head, tail) == (op, detail), (op, detail, label)
        elif not detail:
            assert (head, tail) == (op, ""), (op, detail, label)


def test_a_miss_nodes_detail_is_recovered_from_its_reason():
    """The one place the split under-reports, and why it is repairable:
    `mk_miss` uses the reason AS the detail **when no caller overrides it**.

    v0.31 (round 380) CORRECTED this test. It used to read

        assert "detail=" not in src, "a mk_miss call now overrides `detail`"

    and take that as proof that nothing overrides the detail. The grep is
    true and the conclusion is false: `detail` is `mk_miss`'s FOURTH
    POSITIONAL parameter, and 21 of the 87 call sites in `whence/interp.py`
    pass it positionally. Two of the three ops involved reached the guest,
    and `guest_detail` answered with the reason sentence where the host had
    put a name. `tests/test_v31.py::test_the_grep_is_true_and_the_property_
    it_stood_for_is_false` now owns the real check, by AST; what belongs
    here is the DEFAULT behaviour this file's recovery actually rests on."""
    from whence.values import mk_miss
    node = mk_miss("division by zero", 7, "/")
    assert node.detail == "division by zero"
    assert node.label() == "/ division by zero"
    assert list(node.value.reasons) == ["division by zero (line 7)"]
    # ...and the override, so the two halves of the story sit together
    override = mk_miss("unbound name 'x'", 7, "name", "x")
    assert override.detail == "x"
    assert override.label() == "name x"


# --------------------------------------------------------------------------
# the three divergences that remain
# --------------------------------------------------------------------------

SHARING = [
    ('let a = 1 + 2\nlet b = a + a\nlet r = len(steps(b))', 6),
    ('let a = 1 + 2\nlet b = a + a\nlet c = b + b\n'
     'let r = len(steps(c))', 8),
]


def test_a_shared_node_is_over_reported_never_under_reported(lib):
    """Divergence (1). `walk_steps` dedups on `id(node)`; Whence's `==` is
    structural, so no guest walk can. The guest visits a shared node once
    per PATH — an UPPER bound on the host's count, never a lower one, and
    that direction is the whole safety argument for shipping it."""
    srcs = [s for s, _ in SHARING]
    guests = guest_batch(srcs, lib)
    for (src, expected_host), g in zip(SHARING, guests):
        h = host(src)
        assert h == expected_host, (src, h)
        assert g > h, (src, h, g)
    # and it must never go the other way on the agreement corpus either
    counts = [s for s in AGREE if s.startswith('let r = len(steps')
              or 'len(steps' in s or 'len(blame' in s]
    for src, g in zip(counts, guest_batch(counts, lib)):
        h = host(src)
        if isinstance(h, int) and isinstance(g, int):
            assert g >= h, (src, h, g)


def test_every_guest_step_reports_line_zero(lib):
    """Divergence (2). A guest box carries no line because the guest AST
    carries none — the parser section of self_eval.lang is pinned
    byte-identical to self_host.lang, which has no line tracking. The host
    reports a real line for the same program, so this is the one field of
    the step record that is a documented constant rather than a mirror."""
    src = 'let a = 1\nlet b = 2\nlet c = a + b\nlet r = map(fn(s) { s.line }, steps(c))'
    g = guest_batch([src], lib)[0]
    assert set(g) == {0}, g
    h = host(src)
    assert set(h) - {0}, ("the host must report real lines here", h)


def test_the_guest_never_merges_a_tail_loop(lib):
    """Divergence (3). The host collapses a run of identical steps into one
    `MergedProv` with `count > 1`; the guest has no merging, so `count` is
    always 1 and the run appears as its individual steps. Pinned as
    `max(host count) > 1 and set(guest counts) == {1}` rather than as two
    numbers, so it survives a change to how many steps the loop takes."""
    src = ('fn g(n) { if n == 0 { 0 } else { g(n - 1) } }\n'
           'let y = g(4)\nlet r = map(fn(s) { s.count }, steps(y))')
    h = host(src)
    g = guest_batch([src], lib)[0]
    assert max(h) > 1, ("the host must merge this loop", h)
    assert set(g) == {1}, g


def test_diverge_and_contrast_no_longer_delegate():
    """RETIRED by v0.31 (round 380), and kept here rather than deleted
    because this is where the exemption was published.

    This test used to assert that the guest still delegates, like so:

        assert 'else if name == "diverge" {' in lib_src

    It did NOT go red when the delegation was removed, because
    `apply_builtin`'s new dispatch line spells the same nine characters:

        else if name == "diverge" { @{v: guest_diverge(args), st: st} }

    That is this round's own headline mechanism, one file over — a
    substring standing in for a property. So the check is now on the
    DELEGATION CALL, which is a different string in each case and cannot
    be produced by a dispatch line."""
    lib_src = library_source()
    for gone in ('{ diverge(a0) }', '{ contrast(a0) }',
                 'diverge(a0, (args[1]).v)', 'contrast(a0, (args[1]).v)',
                 'else if name == "blame" { blame(a0) }',
                 'else if name == "at" { at(a0, (args[1]).v) }'):
        assert gone not in lib_src, gone
    for present in ('fn guest_diverge(args) {', 'fn guest_contrast(args) {'):
        assert present in lib_src, present


def test_diverge_and_contrast_now_answer_from_the_guest_history(lib):
    """E4's remainder, retired at its own pin. Round 378 wrote this test to
    prove the guest names `self_eval.lang`'s OWN frames (`a0`, `arg p`) for
    a comparison of two histories that really diverge. It now names the
    program's, and matches the host byte for byte once the `(line N)`
    suffix — the language's oldest documented divergence — is removed."""
    src = 'let x = 1 + 2\nlet y = 1 + 3\nlet r = contrast(x, y)'
    h = host(src)
    g = guest_batch([src], lib)[0]
    assert "let x" in h and "let y" in h and "literal" in h, h
    assert "a0" not in g and "arg p" not in g, g
    assert normalize_contrast(h) == normalize_contrast(g), (h, g)


# --------------------------------------------------------------------------
# bounded rather than truncated
# --------------------------------------------------------------------------

def test_a_history_over_the_budget_misses_instead_of_truncating(lib):
    """Because the walk cannot dedup, a shared and deep history is
    exponential in its depth: this program's history is 2**24 paths. The
    host answers it in linear time; the guest REFUSES and names the number,
    which is the only honest answer available to it. A silently short list
    is the failure mode here that would look like an answer."""
    lets = "\n".join("let x%d = x%d + x%d" % (i, i - 1, i - 1)
                     for i in range(1, 25))
    src = "let x0 = 1 + 2\n%s\nlet r = len(steps(x24))" % lets
    h = host(src)
    assert h == 52, h        # 4 for `x0`, then one `let` and one `+` per level
    g = guest_batch([src], lib)[0]
    assert g[0] == "MISS", g
    assert "5000" in g[1][0] and "gave up" in g[1][0], g


def test_the_budget_is_declared_once_and_the_message_reads_it(lib):
    """The number in the miss must come from the declaration, not from a
    second copy of it — the shape round 321 item 14 keeps finding."""
    assert lib.count("let GUEST_STEPS_BUDGET = ") == 1
    assert "5000" not in lib.split("let GUEST_STEPS_BUDGET = ")[1].split("\n", 1)[1]


# --------------------------------------------------------------------------
# the example still runs
# --------------------------------------------------------------------------

@pytest.mark.whence_slow
def test_self_eval_example_still_passes_its_own_self_tests():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "run.py"),
                        EXAMPLE], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    assert "0 failed" in r.stdout, r.stdout[-3000:]
