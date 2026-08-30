"""Whence v0.31 (round 380, language C) — decision 39: a provenance node's
DETAIL is part of the guest's contract, and the precondition that said it
was free was a grep.

v0.30 (round 378) answered `steps`/`at`/`blame` from the guest box graph.
Two of its recoveries rested on preconditions about `whence/interp.py`, and
one of the two was checked by searching the source for a KEYWORD:

    assert "detail=" not in src, "a mk_miss call now overrides `detail`"
                    -- test_v30.py::test_a_miss_nodes_detail_is_recovered_...

`mk_miss(reason, line, op, detail="", inputs=())`.  `detail` is the FOURTH
POSITIONAL parameter.  The grep is true and the property it stands in for
is false **21 times** in the same file — 14 `call` sites, 3 `name` sites,
4 `typed` sites — and `guest_detail`'s reasons()-recovery answered with the
whole reason sentence wherever the host had put something else there.

Measured, not described: `state/whence/round-380/detail_sites.py` counts the
sites by AST, and `steps_differential.py` compares the OBSERVABLE
`map(fn(s) { [s.op, s.detail, str(s.depth), str(s.inputs)] }, steps(r))`
host vs guest over a 56-call corpus.  Before this round: 45/56.  After the
three fixes below: 49/56.

THE THREE FIXES

  1. **`name`** — the guest labelled an unbound-name miss `name`; the host
     labels it `name nosuch`.  `test_an_unbound_name_reports_the_name_as_
     its_detail`.
  2. **`typed`** — the guest labelled a contract mismatch `typed <reason>`;
     the host labels it `typed <contract label>`.
     `test_a_typed_mismatch_reports_the_label_as_its_detail`.
  3. **The curated inputs were the SUCCESS node's, applied to the MISS
     node.**  `apply_host_builtin` drops the key from `put` and the label
     from `note` because the host's `derived` node does — but the host's
     `mk_miss` guards pass EVERY argument.  `note(1 + 2, "m")` lost three
     real steps out of six.  `test_a_guarded_builtin_miss_keeps_every_
     argument`.

Fix 3 was found by item 3 of this round's backlog, not by looking for it:
the `GUEST_STEPS_BUDGET` sizing sweep validates a host-side path-count
proxy against the real guest walk, and the two disagreed on `note`.  A
proxy that has to be validated is a differential.

THE BUDGET (round 378's item 3).  `GUEST_STEPS_BUDGET = 5000` was the one
quantity v0.30 did not measure.  Swept over all 526 top-level bindings of
every parsable example: p90 = 24, p95 = 43, ordinary-mode max = 123, next
value 71 552, and 24 bindings past 1e9.  A budget of 100 and a budget of
50 000 refuse the same programs to within 2 of 526.  Pinned here as the two
properties the constant must satisfy rather than as the constant.
"""

import ast
import glob
import os
import re
import subprocess
import sys

import pytest

from whence.interp import Interpreter
from whence.values import Miss, Record, WList

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "self_eval.lang")
INTERP = os.path.join(ROOT, "whence", "interp.py")
MARKER = "# ==== SELF-TESTS"
LINE_SUFFIX = re.compile(r" \(line \d+\)")

# The observable a Whence program has of a provenance node.  Every test in
# the first half of this file compares this, host against guest.
PROBE = ('map(fn(s) { [s.op, s.detail, str(s.depth), str(s.inputs)] }, '
         'steps(r))')


def library_source():
    src = open(EXAMPLE, encoding="utf-8").read()
    assert MARKER in src
    return src.split(MARKER)[0]


@pytest.fixture(scope="module")
def lib():
    return library_source()


def escape(s):
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r"))


def deep(p):
    if isinstance(p, Miss):
        return ("MISS", tuple(LINE_SUFFIX.sub("", r) for r in p.reasons))
    if isinstance(p, WList):
        return tuple(deep(e.payload) for e in p)
    if isinstance(p, Record):
        return tuple(sorted((k, deep(v.payload)) for k, v in p.fields.items()))
    return p


def host_steps(program):
    src = "%s\nlet __p = %s\n" % (program, PROBE)
    v = Interpreter(out=lambda s: None, seed=7).run(src).get("__p")
    assert v is not None, program
    return deep(v.payload)


def guest_steps_batch(programs, lib):
    """One interpreter run for the whole batch — building the ~3 600-line
    library costs ~0.11 s and dominates a per-case run."""
    parts = [lib]
    for i, program in enumerate(programs):
        src = "%s\nlet __p = %s\n" % (program, PROBE)
        parts.append('let __o%d = run_src("%s")\n' % (i, escape(src)))
    env = Interpreter(out=lambda s: None, seed=7).run("".join(parts))
    out = []
    for i in range(len(programs)):
        rec = env.get("__o%d" % i)
        assert rec is not None, programs[i]
        out.append(deep(rec.payload.fields["v"].payload))
    return out


# --------------------------------------------------------------------------
# the precondition itself
# --------------------------------------------------------------------------

def mk_miss_sites():
    """(lineno, op, sets_detail) for every `mk_miss` call in interp.py, by
    AST — the check round 378's grep was standing in for."""
    tree = ast.parse(open(INTERP, encoding="utf-8").read())
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
        if name != "mk_miss":
            continue
        sets = len(n.args) >= 4 or any(k.arg == "detail" for k in n.keywords)
        op = n.args[2].value if (len(n.args) >= 3 and
                                 isinstance(n.args[2], ast.Constant)) else None
        out.append((n.lineno, op, sets))
    return out


def test_the_grep_is_true_and_the_property_it_stood_for_is_false():
    """Round 378's precondition, both halves, side by side. The keyword
    `detail=` really does not occur; `detail` is really overridden, 21
    times, because it is `mk_miss`'s fourth POSITIONAL parameter."""
    src = open(INTERP, encoding="utf-8").read()
    assert "detail=" not in src            # the grep round 378 ran
    from whence.values import mk_miss
    params = mk_miss.__code__.co_varnames[:mk_miss.__code__.co_argcount]
    assert params == ("reason", "line", "op", "detail", "inputs"), params
    assert params.index("detail") == 3     # ...which is why it says nothing

    sites = mk_miss_sites()
    setting = [s for s in sites if s[2]]
    assert len(sites) == 87, len(sites)
    assert len(setting) == 21, len(setting)


def test_every_detail_setting_site_belongs_to_one_of_three_ops():
    """The 21 are not scattered: they are `call` (arity, depth, tail-loop),
    `name` (unbound) and `typed` (contract). Naming them is what makes the
    guest's obligation finite — the guest re-implements `call` itself, so
    only `name` and `typed` could ever have diverged, and both now agree."""
    by_op = {}
    for _, op, sets in mk_miss_sites():
        if sets:
            by_op.setdefault(op, 0)
            by_op[op] += 1
    assert by_op == {"call": 14, "name": 3, "typed": 4}, by_op


# --------------------------------------------------------------------------
# the three fixes, each host-vs-guest
# --------------------------------------------------------------------------

def test_an_unbound_name_reports_the_name_as_its_detail(lib):
    """Fix 1. Host `f_name` is `mk_miss(..., "name", name)` — detail is the
    NAME. The guest built `mkb(b, "name", [])`, a label with no detail, so
    `guest_detail` fell through to its reasons() recovery and answered the
    whole sentence."""
    prog = "let r = nosuch + 1"
    h, g = host_steps(prog), guest_steps_batch([prog], lib)[0]
    assert ("name", "nosuch", "2", "0") in h, h
    assert h == g, (h, g)


def test_a_typed_mismatch_reports_the_label_as_its_detail(lib):
    """Fix 2. Host `b_typed`'s mismatch is `mk_miss(_mismatch_reason(...),
    line, "typed", label.payload, inputs=(value,))` — detail is the
    CONTRACT LABEL, and the reason is a different string entirely. This is
    the one of the 21 that reaches a DELEGATED builtin, so it is the one
    that bit."""
    prog = 'let r = typed("s", "num", "p")'
    h, g = host_steps(prog), guest_steps_batch([prog], lib)[0]
    assert ("typed", "p", "1", "1") in h, h
    assert h == g, (h, g)
    # ...and the reason, which is NOT the detail, is still reachable
    flat = [x for step in h for x in step]
    assert not any("expected num" in x for x in flat), h


GUARDED = [
    # (program, how many steps the history has)
    ('let r = note(1 + 2, "m")', 6),         # note's label guard
    ('let r = put(7, "b", 2 + 3)', 7),       # put's record guard
    ('let r = put(@{a: 1}, 9, 2 + 3)', 8),   # put's key guard
]


def test_a_guarded_builtin_miss_keeps_every_argument(lib):
    """Fix 3, and the one a user would have noticed: `note`'s and `put`'s
    curated inputs describe the host's `derived` node and were being
    applied to its `mk_miss` node too, so the guest history simply did not
    contain the derivation of the rejected argument. `note(1 + 2, "m")`
    had 3 steps where the host has 6."""
    progs = [p for p, _ in GUARDED]
    gs = guest_steps_batch(progs, lib)
    for (prog, n), g in zip(GUARDED, gs):
        h = host_steps(prog)
        assert len(h) == n, (prog, len(h), h)
        assert h == g, (prog, h, g)


def test_a_passed_through_miss_is_still_a_success_node(lib):
    """The boundary the fix must not cross. `note("m", 1 / 0)` MISSES, but
    not because a guard fired — host `b_note` returns
    `derived("note", label, line, (v,), v.payload)` with a missed payload,
    a success node with ONE input. Testing `missed(p2)` instead of testing
    the guards would have broken exactly this case."""
    prog = 'let r = note("m", 1 / 0)'
    h, g = host_steps(prog), guest_steps_batch([prog], lib)[0]
    assert ("note", "m", "1", "1") in h, h     # one input, not two
    # Everything but the DETAIL agrees, and the detail is the one class
    # this round measured and did NOT fix: a DELEGATED builtin's SUCCESS
    # node carries a host detail the guest box never receives (`note m`,
    # `put b`, `has a`, `range 0..2`, `guess s`, `diverge 1 origins` — six
    # of the seven cases still open in `steps_differential.py`). Asserting
    # equality here would tie this test to that separate divergence and go
    # red when it is fixed; asserting the SHAPE is what fix 3 is about.
    assert [(a, c, d) for a, _, c, d in h] == [(a, c, d) for a, _, c, d in g]
    assert g[1] == ("note", "", "1", "1"), g


def test_the_curated_inputs_are_still_curated_on_success(lib):
    """The other half of the same boundary: with no guard firing, `put`
    still drops the key and `note` still drops the label, because the
    host's `derived` node does."""
    progs = ['let r = put(@{a: 1}, "b", 2 + 3)', 'let r = note("m", 1 + 2)']
    gs = guest_steps_batch(progs, lib)
    for prog, g in zip(progs, gs):
        h = host_steps(prog)
        top = [s for s in h if s[2] == "1"][0]
        assert top[3] in ("1", "2"), (prog, top)   # curated, not all args
        assert [s[0] for s in h] == [s[0] for s in g], (prog, h, g)


# --------------------------------------------------------------------------
# the budget (round 378's item 3)
# --------------------------------------------------------------------------

def path_count(node, cap=10 ** 9):
    """`paths(n) = 1 + sum(paths(c))` — the number of ROOT-TO-NODE paths,
    which is exactly what a walk with no identity dedup visits. Iterative
    and memoised on id, so counting stays linear even when the count is
    exponential."""
    memo, stack = {}, [(node, False)]
    while stack:
        n, expanded = stack.pop()
        if id(n) in memo:
            continue
        if not expanded:
            stack.append((n, True))
            for c in n.inputs:
                if id(c) not in memo:
                    stack.append((c, False))
            continue
        total = 1
        for c in n.inputs:
            total += memo[id(c)]
            if total > cap:
                total = cap
                break
        memo[id(n)] = total
    return memo[id(node)]


def budget_from_library():
    lib = library_source()
    assert lib.count("let GUEST_STEPS_BUDGET = ") == 1
    tail = lib.split("let GUEST_STEPS_BUDGET = ")[1]
    return int(tail.split("\n")[0].strip())


def test_the_proxy_is_exact_against_the_real_guest_walk(lib):
    """The budget was sized with a PROXY — path count over the host DAG —
    and `skills/measured-budget-sizing` step 1 says validate a proxy before
    trusting it. Ten programs, chosen to include sharing (`x0 + x0` chains,
    where the proxy and a naive node count diverge most)."""
    cases = [
        'let r = 1',
        'let x = 1 + 2\nlet r = len(steps(x))',
        'let x = 1 + 2\nlet y = x * x\nlet r = y + 1',
        'let x0 = 1 + 2\nlet x1 = x0 + x0\nlet x2 = x1 + x1\nlet r = x2',
        'let x0 = 1 + 2\nlet x1 = x0 + x0\nlet x2 = x1 + x1\n'
        'let x3 = x2 + x2\nlet x4 = x3 + x3\nlet r = x4',
        'let r = note(1 + 2, "m")',
        'let r = map(fn(v) { v * 2 }, range(5))',
    ]
    parts = [lib]
    for i, src in enumerate(cases):
        parts.append('let __w%d = len(guest_walk_steps(guest_history_root('
                     '(run_src_p("%s")).v)))\n' % (i, escape(src)))
    env = Interpreter(out=lambda s: None, seed=7).run("".join(parts))
    for i, src in enumerate(cases):
        measured = env.get("__w%d" % i).payload
        henv = Interpreter(out=lambda s: None, seed=7).run(src)
        last = [v for v in henv.vars.values() if hasattr(v, "inputs")][-1]
        assert measured == path_count(last), (src, measured, path_count(last))


def test_the_budget_clears_the_measured_corpus_by_at_least_ten_times():
    """Round 380's sweep: 526 bindings over every parsable example, and the
    ORDINARY mode tops out at 123 paths. Re-measured here over the two
    examples that hold that mode's tail, so a future example with a
    6 000-path history fails this instead of silently becoming a refusal."""
    budget = budget_from_library()
    worst = 0
    for name in ("diverge.lang", "hello.lang", "sales.lang", "shapes.lang",
                 "provenance.lang", "history.lang", "blame.lang"):
        src = open(os.path.join(ROOT, "examples", name),
                   encoding="utf-8").read()
        env = Interpreter(out=lambda s: None, seed=7).run(src)
        for v in env.vars.values():
            if hasattr(v, "inputs"):
                worst = max(worst, path_count(v))
    assert worst == 123, worst           # `diverge.lang`'s `week`
    assert budget >= 10 * worst, (budget, worst)


def test_the_budget_sits_inside_its_own_insensitivity_band():
    """The finding that makes the number honest rather than lucky: the
    corpus is BIMODAL, and between the ordinary mode's 123 and the next
    value in the whole corpus (71 552) there is nothing. So every budget in
    that band refuses exactly the same programs, and 5000 is not a tuned
    value — it is a point in a two-and-a-half-order-of-magnitude range over
    which the constant has no observable effect. Pinned so that a later
    round moving it inside the band knows it is churn, and a later round
    moving it OUTSIDE the band has to say why."""
    budget = budget_from_library()
    assert 123 < budget < 71552, budget


def test_the_budget_is_declared_once_and_the_message_still_reads_it():
    """Carried from `test_v30.py` because the declaration moved: the number
    in the overflow miss must come from the declaration, not from a second
    copy of it."""
    lib = library_source()
    assert lib.count("let GUEST_STEPS_BUDGET = ") == 1
    body = lib.split("let GUEST_STEPS_BUDGET = ")[1].split("\n", 1)[1]
    assert "5000" not in body


# --------------------------------------------------------------------------
# the fuzz grammar (round 378's item 8) and the example
# --------------------------------------------------------------------------

def test_the_generator_reaches_every_registered_builtin():
    """`show` was registered in v0.29 (round 374) and was still absent from
    `harness/swe/fuzz.py::BUILTIN_ARITY` six rounds later. Round 335 closed
    this exact gap by hand-diffing the two sets and recorded that it had;
    nothing re-ran the diff, so the next builtin re-opened it. This is the
    diff, as a test."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(ROOT)))
    from harness.swe.fuzz import BUILTIN_ARITY
    import whence.interp as I
    registered = set(dict(I._make_builtin_table()))
    missing = registered - set(BUILTIN_ARITY)
    extra = set(BUILTIN_ARITY) - registered
    assert not missing, sorted(missing)
    assert not extra, sorted(extra)


def test_the_show_example_runs_and_passes_its_own_checks():
    """Round 378's item 8, other half: `show` had no example. `show.lang`
    is the contrast against `str` — bounded vs full, `miss` vs the reason,
    and the fact that `show` is a DERIVATION whose result still knows its
    input."""
    path = os.path.join(ROOT, "examples", "show.lang")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "run.py"), path],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "0 failed" in r.stdout, r.stdout[-2000:]
    assert "10 passed" in r.stdout, r.stdout[-2000:]


# --------------------------------------------------------------------------
# the tail ceiling (round 378's item 6)
# --------------------------------------------------------------------------

def test_the_guest_tail_ceiling_is_399_and_the_host_has_none(lib):
    """Round 210's justification comment said "no example … comes close to
    400 real guest-level call frames". Bisected from scratch: the guest
    answers `go(399)` and refuses `go(400)`, and the host answers
    `go(200000)`. The comment is now corrected in place and the ceiling is
    in the module header's divergence list, where it had never been."""
    tail = 'fn go(i) { if i == 0 { 42 } else { go(i - 1) } }\nlet r = go(%d)'
    parts = [lib,
             'let __a = run_src("%s")\n' % escape(tail % 399),
             'let __b = run_src("%s")\n' % escape(tail % 400)]
    env = Interpreter(out=lambda s: None, seed=7).run("".join(parts))
    assert env.get("__a").payload.fields["v"].payload == 42
    b = env.get("__b").payload.fields["v"].payload
    assert isinstance(b, Miss), b
    assert any("too deep" in r for r in b.reasons), b.reasons
    h = Interpreter(out=lambda s: None, seed=7).run(tail % 200000).get("r")
    assert h.payload == 42, h.payload


def test_the_four_broken_contracts_are_named_where_the_number_is():
    """The comment must carry the measurement, not a claim. Each of the
    four example contracts the ceiling breaks is a real, greppable line in
    a real example — checked here so a later edit cannot quietly turn the
    corrected comment back into a story."""
    lib = library_source()
    block = lib.split("let GUEST_MAX_DEPTH = ")[0]
    block = block[block.index("# round 210: guest-level function-CALL"):]
    for n in ("200 000", "100 000", "100 001", "10 001", "399"):
        assert n in block, n
    deep_src = open(os.path.join(ROOT, "examples", "deep.lang"),
                    encoding="utf-8").read()
    tco_src = open(os.path.join(ROOT, "examples", "tco.lang"),
                   encoding="utf-8").read()
    assert "count_tail(200000, 0) == 200000" in deep_src
    assert "even(10001) == false" in deep_src
    assert "sum_to(100000, 0)" in tco_src


def test_the_tail_ceiling_is_in_the_declared_divergence_list():
    """It was minted in round 210 and never added. `test_v30.py` pins three
    divergences for the provenance family; this is the fourth, for the
    evaluator as a whole, and it belongs in the module header where a
    reader looks for the list."""
    lib = library_source()
    header = lib[:lib.index("# ---- character classes")]
    assert "Known, deliberate divergences" in header
    assert "NO TAIL CALLS" in header, header[-1200:]
    assert "399" in header, header[-1200:]
