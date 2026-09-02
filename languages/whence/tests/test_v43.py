"""v0.43 (round 450, language C) — what `print` promises, and what it kept.

v0.42 made a printed container OBSERVED, so that widening the drop report to
misses inside a discarded list could not fire on `examples/history.lang`'s
`print(culprits)`. That is a claim about text — *the reader has been shown
this* — and nothing in the repo compared it against the text. It was false
two different ways.

**One.** `full_show` rendered a nested miss as the bare token `miss`, so
`print([nosuch(1)])` printed `[miss]`: THAT there is a miss and not WHY. v0.42
knew and wrote it down as a deliberate residual. The sharpest statement of it
is the one nobody made:

    [nosuch(1)]          ->  (no output) + `dropped: ... unbound name 'nosuch'`
    print([nosuch(1)])   ->  `[miss]`    + nothing

**adding a `print` to a program REMOVED information about a miss** — because
the print suppressed the one mechanism that would have named the reason, and
replaced it with four characters that do not.

**Two, and nobody had named this one.** `full_show` stops at
`values.SHOW_NEST`. A miss nested deeper renders as nothing at all —
`print([[[[[nosuch(1)]]]]])` prints `[[[[[…]]]]]`, which does not contain the
substring `miss` — and v0.42 still marked the container observed, so the run
said NOTHING about that miss anywhere. The detector (`_misses_within`) has no
depth bound; the renderer has one. Detector and suppressor had different
shapes, which is precisely the class round 446 named in
`skills/suppressor-shares-the-detector-shape/SKILL.md` — and left an instance
of inside its own fix.

v0.43, decision 52, fixes both halves as one predicate:

  * `values._show` names the reason in the FULL rendering (`limit is None`),
    spelled as the Whence literal that produces it — `miss "reason"`, quoted
    because miss reasons contain commas. The BOUNDED snapshot keeps the bare
    token, because under a limit the reason would arrive as a 12-character
    slice; `show()` (decision 37) is that path and its contract is unchanged.
  * `b_print` no longer marks the container. It marks exactly the miss NODES
    the rendering NAMED, computed by `values.named_misses`, which mirrors the
    renderer branch for branch. The suppressor cannot claim more than the
    renderer did, and `test_the_renderer_and_the_suppressor_name_the_same_
    misses` holds the two together by differential rather than by comment.

`SHOW_NEST` itself is deliberately NOT lifted: it exists so that rendering a
2500-deep value costs O(1) host frames instead of O(depth), and a
`RecursionError` in the explanation path is the exact failure the language's
rule 2 forbids. The renderer is allowed to stop. What it is not allowed to do
is have someone else claim it didn't.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from whence.interp import Interpreter                           # noqa: E402
from whence.parser import parse                                 # noqa: E402
from whence.values import (                                     # noqa: E402
    FULL_SHOW_NEST, Miss, SHOW_NEST, full_show, named_misses, show_payload,
)
import run as RUNPY                                             # noqa: E402


def run(src, out=None, **kw):
    i = Interpreter(out=out if out is not None else (lambda s: None), **kw)
    i.run(src)
    return i


def printed(src, **kw):
    lines = []
    run(src, out=lines.append, **kw)
    return lines


def report(src, **kw):
    """Everything the program tells a reader: stdout, then the drop report."""
    lines = []
    i = run(src, out=lines.append, **kw)
    RUNPY.report_drops(i, lines.append)
    return "\n".join(lines)


def value_of(src):
    """The node the last statement evaluated to."""
    i = Interpreter(out=lambda s: None)
    env = type(i.globals)(i.globals)
    v = None
    for stmt in parse(src).stmts:
        v = i.exec_stmt(stmt, env)
    return v


# --------------------------------------------------------------------------
# 1. the rendering: a nested miss names its reason
# --------------------------------------------------------------------------

def test_a_nested_miss_names_its_reason_in_the_full_rendering():
    assert printed("print([nosuch(1)])\n") == [
        '[miss "unbound name \'nosuch\' (line 1)"]']
    assert printed("print(@{v: nosuch(1)})\n") == [
        '@{v: miss "unbound name \'nosuch\' (line 1)"}']
    assert printed('print(guess([nosuch(1)], 0.5, "s"))\n') == [
        'guess 0.5 (s): [miss "unbound name \'nosuch\' (line 1)"]']


def test_a_miss_printed_bare_still_uses_the_report_spelling():
    """`print(m)` is a message to a human and keeps `miss: reasons`; a miss
    INSIDE a value is a value and is spelled as the literal that makes one.
    Both name the reason, which is the whole promise."""
    assert printed("print(nosuch(1))\n") == [
        "miss: unbound name 'nosuch' (line 1)"]


def test_the_bounded_snapshot_still_says_just_miss():
    """Decision 37's contract, unchanged by v0.43: `show()` is the bounded
    renderer and in it `a miss is the word miss`. Under a limit the recursive
    calls pass `limit and 12`, so a reason would arrive as a twelve-character
    slice of a sentence."""
    assert printed("print(show([nosuch(1)]))\n") == ["[miss]"]
    assert show_payload(value_of("[nosuch(1)]\n").payload) == "[miss]"


def test_a_miss_message_naming_a_container_operand_is_unchanged():
    """The miss MESSAGES the interpreter builds go through `show_payload`, so
    v0.43 does not touch them. This is the line round 450's re-pin of
    `test_generated_killers.py` shows moving on one side and not the other,
    inside a single assertion."""
    out = printed('let v1 = @{a: [nosuch(1)], c: 0}\n'
                  'print(if v1 { 1 } else { 2 })\n')
    assert out == ['miss: if condition must be true/false, '
                   'got @{a: [miss], c: 0} (line 2)']


def test_a_reason_containing_a_comma_is_quoted_not_ambiguous():
    """Why the literal spelling is QUOTED rather than bare. Miss reasons
    contain commas — `if condition must be true/false, got [1]` is one, and
    `fold`'s arity hint (`arguments fit fold(fn, acc, xs)`) has two. Unquoted
    inside `[...]` there is no reading that recovers where the element ends,
    so the quotes are load-bearing and not decoration."""
    line = printed("print([if [1] { 1 } else { 2 }])\n")[0]
    assert line == ('[miss "if condition must be true/false, '
                    'got [1] (line 1)"]')
    assert line.count(",") == 1 and line.startswith('[miss "')


def test_the_rendering_is_source_SHAPED_and_not_a_round_trip():
    """`miss "text"` is real Whence syntax (SPEC 'Finding 5'), and the
    language's own cure sentence tells an author to write exactly it — which
    is why the nested rendering is spelled that way rather than, say,
    `miss(...)`.

    It is NOT a round trip and this pins the gap rather than implying one:
    the RUNTIME reason of `miss "gone"` is `gone (line 1)`, because a miss
    stamps the line it was made on, so re-reading the rendering back in gives
    a miss whose reason has gained a second stamp. Closing that would mean
    either dropping the stamp (which every drop report depends on) or
    teaching the renderer to strip it (which would lie about misses whose
    reason genuinely ends in a parenthesis). Neither is worth it; the
    property v0.43 needs is that the reason is THERE, not that it parses."""
    assert printed('print([miss "gone"])\n') == ['[miss "gone (line 1)"]']
    assert printed('print(@{a: miss "gone"})\n') == ['@{a: miss "gone (line 1)"}']


def test_an_embedded_quote_is_escaped():
    assert printed('print([num("3O")])\n') == [
        '[miss "num: cannot parse \\"3O\\" (line 1)"]']


# --------------------------------------------------------------------------
# 2. the property: a print never removes information
# --------------------------------------------------------------------------

MONOTONE_CASES = [
    "[nosuch(1)]",
    "@{v: nosuch(1)}",
    "[[nosuch(1)]]",
    "map(fn(x) { nosuch(x) }, [1, 2])",
    '[guess([nosuch(1)], 0.5, "s")]',
    "[[[[[nosuch(1)]]]]]",                      # past SHOW_NEST: the new half
]


@pytest.mark.parametrize("expr", MONOTONE_CASES)
def test_printing_a_value_never_removes_a_reason_from_the_output(expr):
    """THE PROPERTY v0.43 exists for. Everything the run tells a reader is
    stdout plus the drop report; wrapping the same expression in `print`
    must not shrink the set of reasons named in it.

    Under v0.42 the last two cases FAIL: the `guess` one because the walk
    refused to enter a `Guess`, the deep one because the renderer stopped
    before the miss and the suppressor claimed it hadn't."""
    bare = report(expr + "\n")
    shown = report("print(%s)\n" % expr)
    assert "unbound name 'nosuch'" in bare
    assert "unbound name 'nosuch'" in shown


def test_the_v042_shape_of_the_defect_is_reproducible(monkeypatch):
    """Falsified, not asserted. v0.42's suppressor claimed MORE than the
    renderer showed — a printed container observed everything inside it,
    whatever the rendering had actually reached. Restore exactly that claim
    (a `named_misses` with the DETECTOR's unbounded shape rather than the
    renderer's) and the deep case goes silent again, in a run whose stdout
    does not contain the substring `miss` anywhere.

    This is the whole thesis in one test: the report's answer is decided by
    whether the suppressor's walk has the renderer's bound. Reverting nothing
    else brings the defect back."""
    import whence.interp as I
    import whence.values as V

    def unbounded(node):                       # v0.42's claim, restated
        out, stack, seen = [], [node], set()
        while stack:
            n = stack.pop()
            if id(n) in seen:
                continue
            seen.add(id(n))
            p = getattr(n, "value", None)
            if isinstance(p, Miss):
                out.append(n)
            elif hasattr(p, "to_list"):
                stack.extend(p)
            elif hasattr(p, "fields"):
                stack.extend(v for _, v in p.fields.items())
        return out

    # v0.44 (round 452): the depth is taken from the constant, not written.
    # This test needs a value PAST the full rendering's cap and v0.43 spelled
    # that `5` — correct then, and wrong the moment decision 53 gave the full
    # rendering its own deeper constant. The thesis is about the boundary,
    # never about the number 5.
    deep = FULL_SHOW_NEST + 2
    src = "print(%snosuch(1)%s)\n" % ("[" * deep, "]" * deep)
    good_lines = []
    good = Interpreter(out=good_lines.append)
    good.run(src)
    # FULL_SHOW_NEST + 1 container levels render in full; the next one down
    # renders as the bare `[…]`, which contributes a bracket of its own. So
    # a value deeper than the cap shows FULL_SHOW_NEST + 2 brackets whatever
    # its real depth is.
    shown = FULL_SHOW_NEST + 2
    assert good_lines == ["[" * shown + "…" + "]" * shown]
    assert "miss" not in good_lines[0]
    assert good.dropped_total == 1, "the deep case stopped being reported"

    # v0.44: `b_print` reads `rendering.misses` from the one walk, so the
    # v0.42 claim is restored by making that walk's second half unbounded
    # rather than by replacing a separate `named_misses`. The falsification
    # is the same falsification; what it has to reach into changed, which is
    # itself the evidence that the two halves are now one thing.
    real_named = I.full_show_named

    def unbounded_rendering(node, *a, **kw):
        r = real_named(node, *a, **kw)
        return V.FullRendering(r.text, unbounded(node), r.depth_stopped,
                               r.node_stopped)

    monkeypatch.setattr(I, "full_show_named", unbounded_rendering)
    bad_lines = []
    bad = Interpreter(out=bad_lines.append)
    bad.run(src)
    assert bad_lines == good_lines, "the RENDERING is not what changed"
    assert bad.dropped_total == 0, "the falsification stopped falsifying"


# --------------------------------------------------------------------------
# 3. the suppressor is derived from the renderer
# --------------------------------------------------------------------------

DIFFERENTIAL_CASES = [
    "[nosuch(1)]",
    "@{v: nosuch(1)}",
    "[[nosuch(1)]]",
    "[[[nosuch(1)]]]",
    "[[[[nosuch(1)]]]]",
    "[[[[[nosuch(1)]]]]]",
    "@{a: @{b: @{c: @{d: nosuch(1)}}}}",
    "[1, nosuch(2), @{k: nosuch(3)}]",
    '[guess([nosuch(1)], 0.5, "s")]',
    'guess([nosuch(1)], 0.5, "s")',
    "map(fn(x) { nosuch(x) }, [1, 2, 3])",
    "[[1], [nosuch(2)], [[nosuch(3)]]]",
    "nosuch(1)",
    "[1, 2, 3]",
    "@{}",
]


@pytest.mark.parametrize("expr", DIFFERENTIAL_CASES)
def test_the_renderer_and_the_suppressor_name_the_same_misses(expr):
    """THE ANTI-DRIFT DEVICE. `named_misses` is a second walk over the same
    value as `full_show`, so it can drift from it; a docstring saying "these
    agree" cannot fail. This renders the value and asserts, for EVERY miss
    node reachable inside it, that its reason appears in the text if and only
    if `named_misses` claims it.

    `full_show`'s own container branch renders elements one level shallower
    than `show_payload` would, and `_show`'s `Guess` branch has no nest guard
    of its own; both are exactly the kind of detail a mirrored walk gets
    wrong, and both are covered by a case above."""
    node = value_of(expr + "\n")
    text = full_show(node.payload)
    named = {id(n) for n in named_misses(node)}

    reachable = []
    stack = [node]
    seen = set()
    while stack:
        n = stack.pop()
        if id(n) in seen:
            continue
        seen.add(id(n))
        p = getattr(n, "value", None)
        if isinstance(p, Miss):
            reachable.append(n)
        elif hasattr(p, "to_list"):
            stack.extend(p)
        elif hasattr(p, "fields"):
            stack.extend(v for _, v in p.fields.items())
        elif hasattr(p, "confidence"):
            stack.append(p.node)

    assert reachable or expr in ("[1, 2, 3]", "@{}"), "case names no miss"
    for n in reachable:
        spelled = '; '.join(n.value.reasons)
        assert (spelled in text) == (id(n) in named), (
            "%r: rendered=%s named=%s\n%s"
            % (expr, spelled in text, id(n) in named, text))


def test_the_depth_boundary_is_a_constant_and_is_measured_not_assumed():
    """`FULL_SHOW_NEST + 1` levels of list are named; one more is not.

    v0.43 wrote this as "four are named, five are not" and asserted
    `SHOW_NEST == 3` beside it, because the full rendering and the bounded
    snapshot shared one constant. v0.44 (decision 53) split them, and the
    literal 4/5 was the whole cost of the split: three tests in this file
    pinned a boundary at a number rather than at the thing that decides it.
    The property is unchanged and it is the one worth pinning — there IS a
    boundary, the rendering stops at it, and the suppressor stops with it.

    `full_show_named`'s own branch renders a top-level container's elements
    at nest 0 and `_show` descends while nest < FULL_SHOW_NEST, so the full
    rendering shows FULL_SHOW_NEST + 1 container levels.
    """
    cap = FULL_SHOW_NEST + 1
    for depth in (1, 2, cap - 1, cap):
        expr = "[" * depth + "nosuch(1)" + "]" * depth
        assert len(named_misses(value_of(expr + "\n"))) == 1, depth
        assert "unbound" in printed("print(%s)\n" % expr)[0], depth
    expr = "[" * (cap + 1) + "nosuch(1)" + "]" * (cap + 1)
    assert named_misses(value_of(expr + "\n")) == []
    shown = cap + 1          # the truncated level contributes its own bracket
    assert printed("print(%s)\n" % expr) == ["[" * shown + "…" + "]" * shown]


def test_the_snapshot_boundary_is_still_show_nest_and_did_not_move():
    """The other half of decision 53: `show()` and every miss MESSAGE are
    the BOUNDED path, and v0.44 did not touch their cap. Eleven generated
    mutation killers and `show()`'s published contract depend on it, and
    a change to `full_show` that quietly moved this one would be exactly the
    regression splitting the constants exists to make impossible."""
    assert SHOW_NEST == 3
    node = value_of("[" * 5 + "1" + "]" * 5 + "\n")
    assert show_payload(node.payload) == "[[[[…]]]]"
    assert FULL_SHOW_NEST > SHOW_NEST, "the split is the point"


def test_a_miss_past_the_render_depth_is_reported_as_a_drop():
    deep = FULL_SHOW_NEST + 2
    i = run("print(%snosuch(1)%s)\n" % ("[" * deep, "]" * deep))
    assert i.dropped_total == 1
    assert i.dropped[0]["reasons"] == ("unbound name 'nosuch' (line 1)",)


def test_printing_a_harmless_container_marks_nothing():
    """v0.42 spent one `_observed_aggr` slot per printed container, which is
    why it needed a second bounded dict at all. v0.43 spends none: a
    container with no miss inside it names no miss."""
    i = run("".join("print([%d])\n" % k for k in range(50)))
    assert i._observed_aggr == {}
    assert i.dropped_total == 0


def test_observation_is_compositional():
    """v0.42 gave two programs carrying the same information to the reader
    different answers, because in one case `print`'s argument was the miss
    and in the other it was the container around it. Both are 0 now."""
    assert run("[print(nosuch(1)), 1]\n").dropped_total == 0
    assert run("print([nosuch(1)]) + [2]\n").dropped_total == 0


def test_a_new_miss_built_around_a_printed_one_is_still_a_drop():
    """v0.32's `1 + print(y)` rule, unchanged: `+` on a miss builds a NEW
    miss node, and nothing showed that one."""
    i = run("print(nosuch(1)) + 1\n")
    assert i.dropped_total == 1


def test_a_second_miss_with_the_same_reason_is_still_a_drop():
    """The gate is node identity, not reason text — otherwise printing one
    `unbound name 'nosuch'` would silence every later one."""
    i = run("print([nosuch(1)])\n[nosuch(1)]\n")
    assert i.dropped_total == 1
    assert i.dropped[0]["at"] == 2


def test_a_miss_shown_inside_a_printed_container_is_not_a_drop_when_dropped_bare():
    """`_note_drop`'s bare-miss branch asks `_seen_by_print`, not `_observed`
    alone. Before v0.43 the two spellings were equivalent because nothing
    ever put a MISS node in the second dict; now one does."""
    i = run("let m = nosuch(1)\nprint([m])\nm\n")
    assert i.dropped_total == 0


# --------------------------------------------------------------------------
# 4. Guess: v0.42's written reason named a program that never built one
# --------------------------------------------------------------------------

def test_the_program_v042_cites_for_the_guess_decision_never_builds_a_guess():
    """v0.42's `_misses_within` docstring and SPEC § v0.42 both say the case
    was MEASURED: *"Round 446 measured the case (`guess(nosuch(1), 0.5, [])`
    as a dropped statement) and chose to leave it"*. That program has two
    defects and neither leaves a `Guess` anywhere:

      * `guess` propagates a miss ARGUMENT (`_propagate`), so `nosuch(1)`
        comes straight back out; and
      * a guess source must be a string, so `[]` is a miss of its own.

    The value measured was a `Miss`, and a dropped `Miss` was already
    reported by v0.32. The written argument for not walking a `Guess` was
    anchored on a program in which the branch it justifies is unreachable."""
    i = run("guess(nosuch(1), 0.5, [])\n")
    assert i.dropped_total == 1                       # v0.32's plain case
    assert i.dropped[0]["within"] is None             # not "inside a guess"
    assert i.dropped[0]["reasons"] == ("unbound name 'nosuch' (line 1)",)

    # the same expression with a legal source: still a bare Miss.
    assert not isinstance(value_of('guess(nosuch(1), 0.5, "s")\n').payload,
                          type(value_of('guess(1, 0.5, "s")\n').payload))


def test_the_program_that_does_build_a_guess_around_a_miss():
    """The case the decision is actually about, written down for the first
    time: the miss has to be INSIDE the guessed value, not the guessed value
    itself."""
    g = value_of('guess([nosuch(1)], 0.5, "s")\n')
    assert type(g.payload).__name__ == "Guess"
    assert full_show(g.payload) == \
        'guess 0.5 (s): [miss "unbound name \'nosuch\' (line 1)"]'


def test_a_discarded_guess_around_a_miss_is_a_drop():
    """v0.43's decision, and the reason: the drop rule's predicate is
    REACHABILITY after the statement, not the value's epistemic status. A
    `Guess` is interrogable through `confidence`/`sources` only by a program
    that has a NAME for it, and a discarded statement leaves none — which is
    v0.32's own argument, unchanged. v0.42's sentence conflated *a value
    built to be interrogated* with *a value someone can still interrogate*."""
    i = run('guess([nosuch(1)], 0.5, "s")\n')
    assert i.dropped_total == 1
    assert i.dropped[0]["within"] == "guess s"

    i = run('[guess([nosuch(1)], 0.5, "s")]\n')       # and through a container
    assert i.dropped_total == 1


def test_a_printed_guess_is_observed_like_any_other_container():
    i = run('print(guess([nosuch(1)], 0.5, "s"))\n')
    assert i.dropped_total == 0


def test_a_guess_around_a_bare_value_is_untouched():
    """The feature still works: a guess is not a defect."""
    i = run('guess(1, 0.5, "s")\n')
    assert i.dropped_total == 0
    assert full_show(value_of('guess(1, 0.5, "s")\n').payload) == \
        "guess 0.5 (s): 1"


# --------------------------------------------------------------------------
# 5. the corpus, before and after — round 446's next-step 1 asked for it
# --------------------------------------------------------------------------

@pytest.mark.whence_slow
def test_the_tracked_corpus_still_drops_exactly_the_deliberate_one():
    """Measured before and after decision 52 and unmoved: 1, in
    `examples/dropped.lang`. The class v0.43 closes is real and demonstrable
    in three lines; its yield on this corpus is zero, and that is published
    rather than described."""
    total = 0
    ex = os.path.join(ROOT, "examples")
    import subprocess
    for name in sorted(os.listdir(ex)):
        if not name.endswith(".lang"):
            continue
        r = subprocess.run([sys.executable, os.path.join(ROOT, "run.py"),
                            os.path.join(ex, name)],
                           capture_output=True, text=True, timeout=300)
        for line in r.stdout.splitlines():
            if line.startswith("dropped: "):
                total += int(line.split()[1])
    assert total == 13, "tracked 1 + field 12; re-derive with curecheck.py corpus"
