"""Whence v0.38 (round 404, language C) — decision 47: the OTHER
duplicate-name sentence names its line, and a line number is not a hint.

v0.37 (round 402) gave the guest the fact the host's first duplicate-name
sentence carries — `'a' is already bound in this block (line 1)` — and
recorded, in its own "what this version deliberately does NOT do", that the
host owns a SECOND sentence for the same idea:

    shape 'S' is already declared in this block

which named the scope and no position at all, even though `shape_scopes`
had the line available and had had it since v0.18. This is that change, on
both sides at once, plus the thing it walked into: **the host's hint
renderer and a sentence that ends by naming a line produce the same six
characters**, and one of the differential's classifiers reads that shape
off the STRING.

The tests here are host-side and cost milliseconds. The guest half is
measured in `tests/test_parse_error_differential.py`, which is where the
two implementations are compared and where this round widened the corpus
by six programs before writing a line of the feature.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_parse_error_differential import (          # noqa: E402
    IMPL_COORD, POSITION, _strip_hint)
from whence.parser import ParseError, Parser, parse        # noqa: E402
from whence.lexer import tokenize                          # noqa: E402


def reason(src):
    """The host's parse-error sentence with its ` at line L, col C` gone."""
    try:
        parse(src)
    except ParseError as e:
        # `ParseError` keeps `.line`/`.col` but no `.message`; the sentence
        # is only ever reassembled from `str(e)`, which is why every
        # reader of it in this repo strips the position with a regex.
        return POSITION.sub("", str(e))
    raise AssertionError("parsed, but should not have: %r" % src)


def position(src):
    try:
        parse(src)
    except ParseError as e:
        return (e.line, e.col)
    raise AssertionError("parsed, but should not have: %r" % src)


# --------------------------------------------------------------------------
# the sentence
# --------------------------------------------------------------------------

def test_the_shape_sentence_names_the_line_of_the_first_declaration():
    assert reason("shape S = @{a: num}\nshape S = @{b: num}\nS") == \
        "shape 'S' is already declared in this block (line 1)"
    assert reason("let k = 0\n\nshape S = @{a: num}\n"
                  "shape S = @{b: num}\nS") == \
        "shape 'S' is already declared in this block (line 3)"


def test_neither_a_constant_nor_the_duplicates_line_would_have_passed():
    """`skills/would-a-constant-have-passed`, applied to the number this
    version adds.

    The pre-v0.38 corpus reached this sentence from exactly two programs
    (`test_parse_error_differential.py::shape-redeclare` and
    `shape-redeclared`) plus one in `test_self_eval.py` and two in
    `test_v13.py`, and in FOUR of the five the first declaration is on
    line 1 and the duplicate on line 2. So three distinct wrong
    implementations — print `1`, print the duplicate's line, print the
    duplicate's line minus one — were all green.

    This test is the widening, stated as the property rather than as a
    list of cases: over the programs this version added, the reported
    number is not constant, is never the duplicate's own line, and is not
    always one less than it.
    """
    cases = [
        # (source, first declaration's line, the DUPLICATE's line)
        ("shape S = @{a: num}\nshape S = @{b: num}\nS", 1, 2),
        ("let k = 0\n\nshape S = @{a: num}\nshape S = @{b: num}\nS", 3, 4),
        ("\nshape S = @{a: num}\nlet k = 0\n# c\nshape S = @{b: num}\nS", 2, 5),
        ("let z = fn() {\n shape S = @{a: num}\n\n shape S = @{b: num} }", 2, 4),
    ]
    got = []
    for src, first, dup in cases:
        m = re.search(r"\(line (\d+)\)$", reason(src))
        assert m, reason(src)
        n = int(m.group(1))
        assert n == first, (src, n, first)
        got.append((n, dup))
    assert len({n for n, _ in got}) > 1, "a constant would have passed: %r" % got
    assert all(n != dup for n, dup in got), got
    assert any(n != dup - 1 for n, dup in got), (
        "every case is adjacent, so an off-by-one would pass: %r" % got)


def test_a_shadowing_declaration_is_the_one_that_gets_named():
    """The top frame, not any frame.

    `shape S` outside a block, shadowed by `shape S` inside it, redeclared
    again inside it. The sentence must name the INNER declaration (line 3),
    because that is the one in this block; naming line 1 would mean the
    check had read `shapes_seen` or walked the whole frame stack, and v0.18
    made that distinction the difference between an error and legal
    shadowing.
    """
    src = ("shape S = @{a: num}\nfn f() {\n shape S = @{b: num}\n\n"
           " shape S = @{c: num}\n 1 }\nf()")
    assert reason(src) == "shape 'S' is already declared in this block (line 3)"


def test_the_two_duplicate_name_sentences_name_the_same_line():
    """Two sentences, one fact, and it had better be the same fact.

    `stmt_list`'s sentence reads `bound[name] = s.line`, and a `shape`
    reaches it as the `A.Let(tok.line, ...)` that `shape_def` returns.
    `shape_def`'s own sentence now reads the line it wrote into the frame.
    Both are `tok.line`, the `shape` KEYWORD — so for the SAME declaration,
    collided with two different ways, the two sentences must name the same
    line. If a future round ever unifies them (round 402's item 2 in its
    stronger form), this is the test that says the unification changed no
    fact, only a wording.
    """
    decl_on_2_then_let = "\nshape S = @{a: num}\nlet k = 0\nlet S = 1\nS"
    decl_on_2_then_shape = "\nshape S = @{a: num}\nlet k = 0\nshape S = @{b: num}\nS"
    assert reason(decl_on_2_then_let) == \
        "'S' is already bound in this block (line 2); Whence has no rebinding"
    assert reason(decl_on_2_then_shape) == \
        "shape 'S' is already declared in this block (line 2)"


def test_the_position_did_not_move():
    """Decision 34 rule 2 is untouched by this version.

    The sentence grew; the `at line L, col C` it ends in is the NAME token
    exactly as it was in v0.37, and the guest reports `tok_at(toks, pos+1)`
    — the same token. A version that changes a message MUST say whether it
    moved a position, and this one says no, with the numbers.
    """
    assert position("shape S = @{a: num}\nshape S = @{b: num}\nS") == (2, 7)
    assert position("let z = fn() {\n shape S = @{a: num}\n\n"
                    " shape S = @{b: num} }") == (4, 8)


# --------------------------------------------------------------------------
# the frame
# --------------------------------------------------------------------------

def test_the_frame_carries_the_line_and_the_fields_still_reach_the_record():
    """`shape_scopes[-1][name]` is `(fields, line)` from v0.38 on.

    The `fields` half has never been read by anything — every use of a
    frame in `whence/parser.py` is a membership test — which is what let
    the line ride along instead of needing a tenth stack in `stmt_list`.
    The half that DOES matter, the field specs, reaches the program
    through the desugared record, not through the frame; this test uses
    both halves to say so.
    """
    seen = {}
    real = Parser.shape_def

    def spy(self):
        node = real(self)
        seen.update(self.shape_scopes[-1])
        return node

    Parser.shape_def = spy
    try:
        parse('shape P = @{x: num, y: str}\n'
              'check "m": matches(@{__shape: "P", x: 1, y: "a"}, P)\n')
    finally:
        Parser.shape_def = real
    assert list(seen) == ["P"]
    fields, line = seen["P"]
    assert fields == [("x", "num"), ("y", "str")]
    assert line == 1


def test_zero_is_still_a_safe_absent_sentinel_for_a_line():
    """v0.37's pin, now load-bearing for a SECOND guest table.

    `bound_line` returns `0` for "not found" and v0.38 made it the lookup
    for `shapes_before`'s records as well as for `bound`'s. That is only
    safe while no real line is 0.
    """
    toks = tokenize("shape S = @{a: num}\nshape S = @{b: num}\nS")
    assert toks, "the lexer produced nothing"
    assert min(t.line for t in toks) == 1, sorted({t.line for t in toks})


# --------------------------------------------------------------------------
# a line number is not a hint
# --------------------------------------------------------------------------

def test_a_trailing_line_number_is_not_a_hint():
    """The finding this version is named for.

    `_with_hint` renders `"%s (%s)" % (message, hint)`. A sentence that
    ends by naming a line renders `"%s (line %d)"`. Those are the same
    string shape, and `_strip_hint` — which decides, for the whole
    host/guest divergence census, whether a difference is "a host-only
    cure" or "something nobody has classified" — reads the shape off the
    string.

    Unguarded, `_strip_hint` would turn this version's host sentence into
    the v0.37 sentence, and a host/guest divergence in the new number
    would be filed as `hint_only`. `other` would stay `[]` and the census
    would report the divergence as understood. THE FAILURE MODE IS A GREEN
    TEST, which is why this one asserts the guard directly.
    """
    host = reason("let k = 0\n\nshape S = @{a: num}\nshape S = @{b: num}\nS")
    assert host.endswith(")")
    assert _strip_hint(host) == host, _strip_hint(host)
    # ...and v0.37's mid-sentence number was never at risk from THIS
    # function, only from `IMPL_COORD`. Both directions, one test.
    v37 = reason("let a = 1\nlet a = 2")
    assert not v37.endswith(")")
    assert _strip_hint(v37) == v37


def test_the_hint_stripper_still_strips_every_real_hint():
    """The guard is narrow, and here is the population it must not touch.

    Every hinted `raise ParseError` site in `whence/parser.py` reached
    through a real program: if `_HINT_IS_A_LINE` were written loosely
    enough to spare a hint, this goes red.
    """
    hinted = [
        "let a = 1\na = 2",
        "let y = if true 1 else 2",
        "let r = {a: 1}",
        "let f = fn(x) { x }\nlet d = f 1",
        "let a = 1 let b = 2",
        "let f = fn() { }",
        "let f = fn() { let a = 1 }",
        "let g = fn adder(a, b) { a + b }",
    ]
    for src in hinted:
        h = reason(src)
        assert h.endswith(")"), (src, h)
        stripped = _strip_hint(h)
        assert stripped != h, (src, h)
        assert not stripped.endswith(")") or "(" in stripped, (src, stripped)


def test_the_impl_coord_sanitiser_does_not_eat_the_new_number():
    """The guest side of the same hazard, as an exact string.

    A guest parse error is `<sentence><position><impl coordinate>`, in that
    order, because `miss` appends the raising line LAST. So the
    `$`-anchored `IMPL_COORD` lands on the implementation coordinate and
    this version's `(line 3)` survives — even though, unlike v0.37's, it
    now sits at the very end of the SENTENCE. One `sub` removes one
    trailing match; that is the whole reason this works, and it is worth a
    test rather than a comment because the two numbers are three characters
    apart in the same string.
    """
    raw = ("shape 'S' is already declared in this block (line 3) "
           "at line 4, col 7 (line 953)")
    assert IMPL_COORD.sub("", POSITION.sub("", raw)) == \
        "shape 'S' is already declared in this block (line 3)"


def test_the_hint_census_did_not_change():
    """v0.38 adds a FACT to a sentence, not a cure. The hinted/unhinted
    split in `whence/parser.py` is 7/13 before and after, and
    `test_v34.py` owns that census — this is the cross-check that says
    this version did not quietly move a site across the line, which is
    exactly what a string-shaped hint test would have concluded."""
    from tests.test_v34 import _parse_error_sites
    sites = _parse_error_sites()
    assert sum(1 for _, h, _ in sites if h) == 7
    assert sum(1 for _, h, _ in sites if not h) == 13
    templates = [t for _, h, t in sites if not h]
    assert "shape '%s' is already declared in this block (line %d)" in templates
    assert "shape '%s' is already declared in this block" not in templates


# --------------------------------------------------------------------------
# the survey — `bench/sanitisers.py`
# --------------------------------------------------------------------------
# Round 404 found seven unanchored copies of one normaliser by grepping its
# NAME. A name-grep cannot see a copy called something else, and there were
# two: `test_v20.py` and `test_v22.py` spell it `LINE_RE`. The survey below
# walks each test module's AST for `re.compile` and decides membership by
# RUNNING the pattern against a rendered ` (line N)`, so two spellings of
# one hazard are one row. It found the last two, and one of them was dead
# code. These tests are what keep the count re-executed rather than
# recorded.

def _survey():
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "bench", "sanitisers.py")
    spec = importlib.util.spec_from_file_location("sanitisers_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_no_normaliser_in_the_suite_eats_a_fact_bearing_line_number():
    """The census, re-executed. `bench/sanitisers.py check` exits nonzero
    if any `re.compile` in `tests/` would delete a parenthesised line
    number that one of this language's messages carries as DATA."""
    mod = _survey()
    rows, rejects = mod.survey()
    assert rejects == [], rejects
    facts = mod.fact_messages()
    assert sorted(facts) == ["v0.37 rebind", "v0.38 shape"], sorted(facts)
    bad = [(r["file"], r["line"], r["name"]) for r in rows
           if any(mod.eats_a_fact(r["pattern"], m) for m in facts.values())]
    assert bad == [], bad
    # ...and the survey is not vacuous: it must still be FINDING the
    # normalisers, not reporting an empty population.
    assert len(rows) >= 9, [(r["file"], r["name"]) for r in rows]


def test_the_survey_can_fail():
    """An instrument that has never been seen red is not an instrument.

    The unanchored form of the very pattern this round anchored, against a
    message the live parser produces, must be reported as eating a fact.
    """
    mod = _survey()
    facts = mod.fact_messages()
    assert mod.eats_a_fact(r" \(line \d+\)", facts["v0.38 shape"]) is True
    assert mod.eats_a_fact(r" \(line \d+\)$", facts["v0.38 shape"]) is False


def test_the_survey_sees_past_the_identifier():
    """Why the AST survey exists and `grep LINE_SUFFIX` does not suffice.

    The population must span more than one identifier — that difference is
    exactly what a name-grep loses, and it is what made round 404's first
    count (seven) wrong by two.
    """
    mod = _survey()
    rows, _ = mod.survey()
    names = {r["name"] for r in rows}
    assert len(names) >= 3, names
    assert "LINE_SUFFIX" in names and "IMPL_COORD" in names, names
    assert any(n == "LINE_RE" for n in names), names
