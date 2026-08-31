"""Whence v0.37 (round 402, language C), decision 46 —
the binding table records WHERE, not just WHETHER.

Round 398 closed the `expected X, got Y` sentence and named what was left:
of 54 rejected programs, 20 messages still differed from the host's, 18 of
them by a host-only HINT and **2** — `rebind` and `rebind-indented` — by
something else entirely. The host says

    'a' is already bound in this block (line 1); Whence has no rebinding

and the guest said `'a' already bound`. The gap was not wording. The host's
sentence carries a FACT about the program (the line where the name was
FIRST bound) and the guest's binding table, a flat list of names, did not
record it.

WHAT THIS ROUND CHANGED, AND WHERE

`whence/*.py` is byte-unchanged; this is a guest-only decision, like v0.36.
In the shared parser section of `examples/self_eval.lang` and
`examples/self_host.lang`, `bound` became a list of `@{n, ln}` records and
`bound_line` is the (linear, Whence has no dict) lookup.

THE MEASUREMENT THAT MADE IT POSSIBLE

The host fills that number from the AST node (`bound[name] = s.line`). The
guest has no AST line field at all — its nodes are records with `kind`,
`name` and `value` and nothing else — so it can only use the HEAD TOKEN of
the statement. Those two numbers agreeing is an empirical claim about every
`A.Let`/`A.FnDef`/shape-desugar constructor in a 2400-line parser, not a
thing to read off and believe. `bench/bindline.py` measures it: 1083
binding statements over the example corpus plus twelve targeted snippets,
0 divergences.

THE BLIND SPOT THE CORPUS HAD

`rebind` and `rebind-indented` both bind on line 1. A guest that computed
nothing and printed the constant `1` would have passed the entire
differential. That is round 398's own finding about the got slot ("the
corpus could only ever see four token kinds") landing in the one place
v0.37 added a number, so the corpus was widened first — five cases whose
first binding is not on line 1, or which reach the sentence by the shape
desugar path — and the feature measured against the widened one.
"""
import io
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "bench"))

import bindline                                     # noqa: E402
from whence import ast_nodes as A                   # noqa: E402
from whence import lexer as L                       # noqa: E402
from whence import parser as P                      # noqa: E402

SELF_EVAL = os.path.join(ROOT, "examples", "self_eval.lang")
SELF_HOST = os.path.join(ROOT, "examples", "self_host.lang")


def read(path):
    return io.open(path, encoding="utf-8").read()


# --------------------------------------------------------------------------
# 1. the premise: a head token's line IS the node's line
# --------------------------------------------------------------------------

def test_the_head_token_line_equals_the_node_line_everywhere():
    """The whole decision rests on this, so it is measured, not read."""
    r = bindline.sweep()
    assert r["divergences"] == [], r["divergences"]
    assert r["bindings"] >= 1000, r["bindings"]
    # both binding kinds have to be REACHED, or the zero is about one of
    # them. `Let` covers the shape desugar too, which is a third
    # constructor behind the same class.
    assert r["by_kind"].get("Let", 0) > 0 and r["by_kind"].get("FnDef", 0) > 0


def test_the_bindline_sweep_can_actually_fail():
    """A parity harness never observed red is a green light, not a
    measurement (round 395's item 6, round 398's `showtok.py`).

    The substituted `statement` shifts every binding node's line by one,
    which is exactly the failure the sweep exists to catch — and it must
    be caught in EVERY source that has a binding, not just the first.
    """
    original = P.Parser.statement

    def wrong(self):
        node = original(self)
        if isinstance(node, (A.Let, A.FnDef)):
            node.line += 1
        return node

    r = bindline.sweep(statement_impl=wrong)
    assert len(r["divergences"]) == r["bindings"], (
        len(r["divergences"]), r["bindings"])
    for d in r["divergences"]:
        assert d["node_line"] == d["head_line"] + 1, d


def test_the_bindline_corpus_reaches_the_shape_desugar_constructor():
    """`parser.py:2086` builds an `A.Let` for `shape S = …` from a DIFFERENT
    `tok` than the ordinary `let` branch does. A sweep that never parsed a
    shape declaration would report 0 divergences without ever having asked
    about that constructor."""
    labels = [lab for lab, src in bindline.corpus() if "shape" in src]
    assert labels, "no source in the sweep contains a shape declaration"
    recs = bindline._records_for("shape S = @{a: num}\nlet v = @{a: 1}\nv")
    assert any(name == "S" for _h, _n, name, _k in recs), recs


# --------------------------------------------------------------------------
# 2. the sentinel
# --------------------------------------------------------------------------

def test_zero_is_a_safe_absent_sentinel_for_a_line():
    """`bound_line` returns 0 for "not bound here", which is only safe
    because no real token can carry line 0. Whence's lexer is 1-based; this
    is what keeps that true, since the guest has no `option` type to use
    instead and a wrong sentinel would turn a first binding into a
    duplicate."""
    for src in ("let a = 1", "\n\n\nlet a = 1", "# c\nlet a = 1"):
        toks = L.tokenize(src)
        assert all(t.line >= 1 for t in toks), [(t.type, t.line) for t in toks]


# --------------------------------------------------------------------------
# 3. the guest computes it — three ways it could have faked it
# --------------------------------------------------------------------------

REBIND_CASES = [
    # (source, expected first-binding line, expected duplicate position)
    ("let a = 1\nlet a = 2\na",                       1, (2, 1)),
    ("\n\nlet a = 1\nlet a = 2\na",                   3, (4, 1)),
    ("# c\n\n\nfn f() { 1 }\nfn f() { 2 }\nf()",      4, (5, 1)),
    ("let z = fn() {\n let b = 1\n\nlet b = 2 }",     2, (4, 1)),
    ("let S = 1\nshape S = @{a: num}\nS",             1, (2, 1)),
]


@pytest.mark.parametrize("src,first,pos", REBIND_CASES)
def test_the_host_names_the_first_bindings_line(src, first, pos):
    with pytest.raises(P.ParseError) as ei:
        P.parse(src)
    msg = str(ei.value)
    assert "is already bound in this block (line %d)" % first in msg, msg
    assert msg.endswith("at line %d, col %d" % pos), msg
    # the two numbers must actually be DIFFERENT in at least the cases that
    # exist to separate them — otherwise the parametrisation proves nothing
    assert "(line %d)" % pos[0] not in msg or first == pos[0]


def test_the_corpus_separates_a_computed_line_from_the_constant_one():
    """Guard on the guard. If every case above bound on line 1, all five
    would pass against an implementation that printed `1`."""
    firsts = {first for _s, first, _p in REBIND_CASES}
    assert len(firsts) >= 3 and firsts != {1}, firsts
    # ...and at least one case where the first-binding line is NOT one less
    # than the duplicate's, which is the other way to fake it
    assert any(pos[0] - first != 1 for _s, first, pos in REBIND_CASES)


# --------------------------------------------------------------------------
# 4. the two guest files stay one file
# --------------------------------------------------------------------------

def test_bound_line_is_in_the_shared_section_of_both_guests():
    """`bound_line` is parser code, so it belongs to the section
    `test_self_eval.py::test_parser_section_matches_self_host` keeps
    byte-identical. A copy that drifted into only one file would leave
    `self_eval.lang` and `self_host.lang` disagreeing about the language."""
    for path in (SELF_EVAL, SELF_HOST):
        src = read(path)
        assert src.count("fn bound_line(bound, nm, i) {") == 1, path
        assert src.count(
            '"\' is already bound in this block (line "') == 1, path
        assert "contains(bound, nm)" not in src, (
            "%s still carries the pre-v0.37 name-only lookup" % path)


def test_the_guest_records_a_record_not_a_bare_name():
    """The data change is the decision. A guest that kept pushing bare
    names and derived the line some other way would be a different design
    and this test is where that would have to be argued."""
    src = read(SELF_EVAL)
    assert "push(bound, @{n: nm, ln: head.line})" in src
    assert "let head = t_at(toks, pos)" in src


# --------------------------------------------------------------------------
# 5. the host did not move
# --------------------------------------------------------------------------

def test_the_host_is_byte_unchanged_by_this_decision():
    """v0.36 and v0.37 are both guest-only. The claim is cheap to make and
    cheap to check, and it is the difference between "the guest caught up"
    and "the two were quietly moved together until they matched"."""
    p = subprocess.run(["git", "diff", "--name-only", "HEAD", "--",
                        "whence/"], cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        pytest.skip("not a git checkout")
    assert p.stdout.strip() == "", p.stdout


# --------------------------------------------------------------------------
# 6. the sanitiser that could have eaten the new fact
# --------------------------------------------------------------------------

def test_the_sanitiser_does_not_eat_a_line_number_inside_the_sentence():
    """`tests/test_parse_error_differential.py` strips the guest's trailing
    implementation coordinate with `IMPL_COORD = r" \\(line \\d+\\)$"`.

    v0.37 put a parenthesised line number INSIDE a guest message for the
    first time. The `$` anchor is the only thing that keeps the sanitiser
    from deleting the very fact the decision added — an unanchored
    `\\(line \\d+\\)` would strip `(line 1)` from the guest side, leave it on
    the host side, and report the closed divergence as still open.

    This is not hypothetical tidiness: the same file's `position_of` was
    already written `findall`-last rather than `search`-first for exactly
    this message, so the hazard was known one function away.
    """
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import test_parse_error_differential as D
    sentence = ("'a' is already bound in this block (line 1); "
                "Whence has no rebinding")
    guest_raw = sentence + " at line 2, col 1 (line 918)"
    assert D.IMPL_COORD.sub("", D.POSITION.sub("", guest_raw)) == sentence
    # and the unanchored form really would have broken it
    assert re.sub(r" ?\(line \d+\)", "", D.POSITION.sub("", guest_raw)) \
        != sentence


def test_position_of_reads_the_last_coordinate_not_the_first():
    """The companion hazard, pinned from this side too."""
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import test_parse_error_differential as D
    msg = ("'a' is already bound in this block (line 1); "
           "Whence has no rebinding at line 7, col 3")
    assert D.position_of(msg) == (7, 3)
