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

**E4 IS RETIRED** (round 378's item 1).  `diverge`/`contrast`, the last two
members of the provenance-query family, stopped delegating.  v0.30 deferred
them with two claims — `diverge` "decides sameness by `na is nb` and
memoises on `(id(na), id(nb))`" and `render_contrast` "column-aligns two
rendered histories", "neither a rule a Whence expression can state".  Priced
separately: `na is nb` is a pure optimisation (a node compared with itself
is structurally identical by definition), the MEMO is the only place
identity is load-bearing and only for MULTIPLICITY, and column alignment is
`s + spaces(w - len(s))`.  So option (b): a structural approximation that is
an UPPER BOUND on the host's origin list, never a lower one.

Measured, host against guest, on a 15-program corpus: 12 agree BYTE FOR
BYTE and the other 3 differ only in the `(line N)` suffix of a miss reason,
which is the language's oldest documented divergence.  Two new divergences
are named and pinned rather than described:

  4. no `count` origin — `go(5)` vs `go(7)` is 3 origins host, 7 guest
  5. every route, not the shortest — a value shared at two depths renders 1
     block of 5 rows host, 3 blocks (6, 6, 5) guest, the host's among them
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
# `$`-anchored since round 404 (v0.38): unanchored, this deletes a line
# number a message carries as a FACT, not just the implementation
# coordinate `miss` appends. Seven copies of this regex existed and all
# seven were unanchored — see `tests/test_self_eval.py`'s copy for the
# full account.
LINE_SUFFIX = re.compile(r" \(line \d+\)$")

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
    # v0.32 (round 384): 87 -> 85 and 21 -> 19. The unbound-name miss was
    # THREE copies of one literal (the compiled `f_name`, `eval_NameRef`,
    # and `f_bcall`'s dead `fnv is None` floor); v0.32 needed to append a
    # cure clause to it and gave it one constructor, `_unbound`. The census
    # is doing exactly its job here: a number that moves when the code moves
    # and states why. The PROPERTY it guards is unchanged — `detail` is
    # still set positionally and still says nothing about itself.
    # v0.33 (round 386): 85 -> 86, `setting` unchanged at 19. `_miss_lit`
    # gained a call for round 384's next-step 1 (`miss <bare unbound name>`
    # now carries decision 41's miss-reason clause instead of propagating a
    # complaint about scope). It passes `inputs=` and NOT `detail`, so it
    # joins the census's total and not its detail-setting subset — which is
    # the census reporting the shape of the change, not just its size.
    assert len(sites) == 86, len(sites)
    assert len(setting) == 19, len(setting)


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
    # v0.32: `name` 3 -> 1, for the reason above — one constructor, not
    # three copies. The guest's obligation is the same obligation and it is
    # now met at one site on each side (`_unbound` here,
    # `lookup`/`name_hint` in examples/self_eval.lang).
    assert by_op == {"call": 14, "name": 1, "typed": 4}, by_op


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
    # Round 413: `harness/` is OUTSIDE this tree, so a mutation copy of
    # `languages/whence` alone cannot import it from cwd. `curecheck.AGI_ROOT`
    # prefers `AGI_RESEARCH_ROOT` (exported by `harness/swe/proc.py` into every
    # such subprocess) and is a no-op in the checkout.
    import curecheck as _C
    if _C.AGI_ROOT not in sys.path:
        sys.path.insert(0, _C.AGI_ROOT)
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


# --------------------------------------------------------------------------
# E4's remainder: `diverge` / `contrast` from the guest history
# --------------------------------------------------------------------------

CONTRAST_LINE = re.compile(r"  \(line \d+\)")


def normalize_contrast(text):
    """`contrast` pads its left column to the widest left line, so removing
    the host's `  (line N)` suffix changes the padding too. Strip the
    suffix and re-normalise the column rule, on both sides."""
    out = []
    for line in text.split("\n"):
        line = CONTRAST_LINE.sub("", line)
        line = re.sub(r" +│ ", " │ ", line)
        out.append(line.rstrip())
    return "\n".join(out)


def host_value(program):
    v = Interpreter(out=lambda s: None, seed=7).run(program).get("r")
    assert v is not None, program
    return v.payload


def guest_values(programs, lib):
    parts = [lib]
    for i, program in enumerate(programs):
        parts.append('let __o%d = run_src("%s")\n' % (i, escape(program)))
    env = Interpreter(out=lambda s: None, seed=7).run("".join(parts))
    return [env.get("__o%d" % i).payload.fields["v"].payload
            for i in range(len(programs))]


# Every case binds `r`. Chosen to cover: value origins, step origins, the
# no-divergence case, lists, calls, the n-way form, and all three argument
# guards.
DIVERGE_CORPUS = [
    'let x = 1 + 2\nlet y = 1 + 3\nlet r = contrast(x, y)',
    'let x = 1 + 2\nlet y = 1 + 3\nlet r = len(diverge(x, y))',
    'let a = 2 * 3\nlet b = 2 * 4\nlet r = contrast(a, b)',
    'let x = 1 + 2\nlet y = 1 + 2\nlet r = contrast(x, y)',
    'let x = [1, 2]\nlet y = [1, 3]\nlet r = contrast(x, y)',
    'fn f(n) { n * 2 }\nlet x = f(3)\nlet y = f(4)\nlet r = contrast(x, y)',
    'let x = 1 + 2\nlet y = 1 + 3\nlet z = 1 + 4\nlet r = contrast([x, y, z])',
    'let x = 1 + 2\nlet y = 1 + 3\nlet z = 1 + 4\n'
    'let r = len(diverge([x, y, z]))',
    'let x = 1 + 2\nlet y = 2 + 2\nlet r = contrast(x, y)',
    'let x = (1 + 2) * (3 + 4)\nlet y = (1 + 9) * (3 + 8)\n'
    'let r = contrast(x, y)',
    'let x = (1 + 2) * (3 + 4)\nlet y = (1 + 9) * (3 + 8)\n'
    'let r = len(diverge(x, y))',
]


def test_the_guest_matches_the_host_byte_for_byte_on_a_diverging_corpus(lib):
    """v0.29 measured E4's remainder as `contrast(1 + 2, 1 + 3)` naming
    `let a0 (line 2893)` and `arg p (line 1743)` — self_eval.lang's own
    frames. Eleven programs that really diverge, every one now identical
    to the host's answer."""
    gs = guest_values(DIVERGE_CORPUS, lib)
    for program, g in zip(DIVERGE_CORPUS, gs):
        h = host_value(program)
        if isinstance(h, str):
            assert normalize_contrast(h) == normalize_contrast(g), program
            assert "a0" not in g and "arg p" not in g, (program, g)
        else:
            assert h == g, (program, h, g)


GUARDS = [
    ('let r = diverge(7)',
     "diverge needs two values or a list of runs, got 7"),
    ('let r = contrast(7)',
     "contrast needs two values or a list of runs, got 7"),
    ('let r = contrast(1 / 0)', "division by zero"),
    ('let r = diverge(1 / 0)', "division by zero"),
]


def test_the_argument_guards_say_what_the_host_says(lib):
    """The three shapes `test_v29.py`'s atlas DOES reach for this pair —
    its 104 diverge/contrast cases are all argument-shape cases. They
    agreed before this round because both sides delegated; they have to
    still agree now that one side does not."""
    progs = [p for p, _ in GUARDS]
    gs = guest_values(progs, lib)
    for (program, needle), g in zip(GUARDS, gs):
        h = host_value(program)
        assert isinstance(h, Miss) and isinstance(g, Miss), (program, h, g)
        assert any(needle in x for x in h.reasons), (program, h.reasons)
        assert any(needle in x for x in g.reasons), (program, g.reasons)
        # the only difference is the line, which is this evaluator's line
        assert ([LINE_SUFFIX.sub("", x) for x in h.reasons] ==
                [LINE_SUFFIX.sub("", x) for x in g.reasons]), (program, h, g)


def test_an_empty_run_list_and_a_single_run_have_no_origins(lib):
    progs = ['let r = len(diverge([]))',
             'let r = len(diverge([1 + 2]))',
             'let r = contrast([])',
             'let r = contrast([1 + 2])']
    for program, g in zip(progs, guest_values(progs, lib)):
        assert g == host_value(program), (program, g, host_value(program))


# --- divergence (4): the guest can never report a `count` origin ----------

COUNTER = ('fn go(i, a) { if i == 0 { a } else { go(i - 1, a + 1) } }\n'
           'let x = go(5, 0)\nlet y = go(7, 0)\nlet r = len(diverge(x, y))')


def test_the_guest_reports_a_merged_loop_difference_differently(lib):
    """Divergence (4), measured rather than described — and the measurement
    corrected the description. The host merges a tail loop into one node
    with `count`, and reports a `step` origin when two counts differ. The
    guest never merges, so that clause can never fire; what does NOT follow
    (and an early draft of the comment claimed) is that the guest reports
    FEWER origins. The unmerged runs differ in LENGTH, so the guest finds
    shape mismatches instead and reports MORE. Neither side is silent."""
    h = host_value(COUNTER)
    g = guest_values([COUNTER], lib)[0]
    assert h == 3, h
    assert g == 7, g


def test_no_guest_node_can_carry_a_count_above_one(lib):
    """The mechanism behind (4), pinned at the source: every step record
    the guest produces reports `count` 1, so the host's `na.count !=
    nb.count` clause has no guest counterpart to mirror."""
    prog = ('fn go(i, a) { if i == 0 { a } else { go(i - 1, a + 1) } }\n'
            'let x = go(5, 0)\n'
            'let r = map(fn(s) { s.count }, steps(x))')
    g = guest_values([prog], lib)[0]
    assert set(deep(g)) == {1}, deep(g)
    h = deep(host_value(prog))
    assert max(h) > 1, h        # the host really does merge this loop


# --- divergence (5): every route, not the shortest -----------------------

SHARED_AT_TWO_DEPTHS = ('let a = 1 + 2\nlet b = a + (a + a)\n'
                        'let c = 1 + 3\nlet d = c + (c + c)\n'
                        'let r = contrast(b, d)')


def test_the_guest_shows_every_route_and_the_hosts_is_among_them(lib):
    """Divergence (5). The host's `_pair_path` is breadth-first, so it
    renders the SHORTEST lockstep route to each origin, once. The guest
    descends once per path, so it renders every route — and the host's
    block is one of them, character for character. Upper bound, never a
    lower one: a reader of the guest's contrast sees everything the host
    would have shown."""
    h = normalize_contrast(host_value(SHARED_AT_TWO_DEPTHS))
    g = normalize_contrast(guest_values([SHARED_AT_TWO_DEPTHS], lib)[0])
    hb = [b for b in h.split("origin ") if b.strip()]
    gb = [b for b in g.split("origin ") if b.strip()]
    assert len(hb) == 1 and len(gb) == 3, (len(hb), len(gb))
    # 5 rendered rows in the host's block, 6/6/5 in the guest's
    assert [b.count("│") for b in hb] == [5], hb
    assert sorted(b.count("│") for b in gb) == [5, 6, 6], gb
    body = hb[0].split(":", 1)[1]
    assert any(b.split(":", 1)[1] == body for b in gb), (body, gb)


SHARED = ('let a = 1 + 2\nlet b = a + a\nlet c = 1 + 3\nlet d = c + c\n'
          'let r = len(diverge(b, d))')


def test_a_shared_origin_is_over_reported_never_under_reported(lib):
    """Divergence (1) for `diverge`: the host's memo is keyed on
    `(id(na), id(nb))` so each pair contributes one origin; the guest has
    no identity and contributes one per path. The DUPLICATE IS VISIBLE —
    two identical blocks — rather than a silently short list."""
    assert host_value(SHARED) == 1
    assert guest_values([SHARED], lib)[0] == 2


def test_identity_is_an_optimisation_and_not_a_rule(lib):
    """The claim v0.30's deferral rested on, checked directly. If `na is
    nb` were load-bearing, `diverge(v, v)` would answer differently from a
    structural walk of the same graph — it does not, on either side, for
    any of these."""
    progs = ['let x = 1 + 2\nlet r = len(diverge(x, x))',
             'let x = (1 + 2) * (3 + 4)\nlet r = len(diverge(x, x))',
             'let x = 1 / 0\nlet r = len(diverge(x, x))',
             'let x = [1, [2, 3]]\nlet r = len(diverge(x, x))',
             'fn f(n) { n * 2 }\nlet x = f(3)\nlet r = len(diverge(x, x))']
    gs = guest_values(progs, lib)
    for program, g in zip(progs, gs):
        assert host_value(program) == 0, program
        assert g == 0, (program, g)


def test_the_walk_refuses_rather_than_truncating(lib):
    """The same rule v0.30 set for `steps`: because the walk cannot dedup,
    a shared and deep history is exponential in its depth. The host answers
    in linear time; the guest REFUSES and names the number. A silently
    short origin list is the failure mode that would look like an answer."""
    lets = "\n".join("let x%d = x%d + x%d" % (i, i - 1, i - 1)
                     for i in range(1, 25))
    src = ("let x0 = 1 + 2\n%s\nlet y0 = 1 + 3\n%s\nlet r = len(diverge(x24, y24))"
           % (lets, lets.replace("x", "y")))
    h = host_value(src)
    assert isinstance(h, int) and h >= 1, h      # the host answers
    g = guest_values([src], lib)[0]
    assert isinstance(g, Miss), g
    assert any("5000" in x and "gave up" in x for x in g.reasons), g.reasons
    assert any("node pairs" in x for x in g.reasons), g.reasons


def test_nothing_in_the_provenance_family_delegates_any_more(lib):
    """What retires E4, stated as the absence of five call shapes rather
    than as a substring of a dispatch line — see `test_v30.py::
    test_diverge_and_contrast_no_longer_delegate` for why that distinction
    is this round's own subject."""
    src = library_source()
    for gone in ('{ diverge(a0) }', '{ contrast(a0) }',
                 'diverge(a0, (args[1]).v)', 'contrast(a0, (args[1]).v)',
                 '{ blame(a0) }', 'at(a0, (args[1]).v)',
                 'fn box_step_record(', 'fn box_diverge_record('):
        assert gone not in src, gone
    for fn in ('guest_steps', 'guest_at', 'guest_blame',
               'guest_diverge', 'guest_contrast'):
        assert ("fn %s(args) {" % fn) in src, fn
        assert ('else if name == "%s" { @{v: %s(args), st: st} }'
                % (fn[6:], fn)) in src, fn


def test_the_example_still_passes_its_own_self_tests():
    """`self_eval.lang` carries 17 new `check` lines for this feature, so
    the count moves; the property is that none of them fails.

    The EXACT count is pinned anyway, and deliberately: `0 failed` alone
    stays green if a `check` line is deleted or stops being reached, which
    is the one regression this file cannot otherwise see. The contract is
    that a round which adds or removes checks updates this number in the
    same commit -- round 390 took it 159 -> 166 (seven v0.33-parity checks)
    and round 416 took it 166 -> 172 (six killers for guest-EVALUATOR rules
    a `checkpin` campaign found unguarded in at least one direction).

    This is the THIRD copy of the number; the other two are
    `test_v23.py::test_both_self_hosting_examples_still_run_green` and
    `test_self_eval.py::test_self_eval_runs_green`. They share no literal,
    so a grep for one finds two -- which is how this one went red in round
    416 after the other two were updated.
    """
    r = subprocess.run([sys.executable, os.path.join(ROOT, "run.py"), EXAMPLE],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    assert "0 failed" in r.stdout, r.stdout[-3000:]
    assert "172 passed" in r.stdout, r.stdout[-400:]
