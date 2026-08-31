r"""v0.36 (round 398), decision 45 --- what the GUEST calls the token it
stopped on.

Round 396 closed the want half of `expected X, got Y` by moving the HOST
(decision 44) and left the got half named, isolated and open: *"the guest
renders a number `'1'` and the EOF token `''` where the host says `1` and
`end of input`. That is v0.24's `_show`, which the guest never received."*

That description was right about the mechanism and short by two kinds. The
guest got the token wrong in THREE places, and only one of them is the one
round 396 could see:

  1. `expect_op` quoted UNCONDITIONALLY. The EOF token's `v` is the empty
     string, so `got ''`; a NUMBER is not text, so `got '1'`. Both name a
     field of the guest's own token record.
  2. `parse_primary`'s catch-all wrote `unexpected token 'X'` where the
     host writes `unexpected X`, and rendered the same two kinds the same
     wrong way (`unexpected token ''` for end of input).
  3. `expect_name` wrote NO got half at all, and was ONE function standing
     in for six different host `what=` spellings. `let r = @{a: 1,}` told
     a guest reader `expected a name` where the host says `expected field
     name, got '}'`. This is the kind round 396's want-half measurement
     could not see, BECAUSE its shared set is defined by having a got
     half --- the defect removed the programs from the population that
     would have shown it. Four of them had a want half that disagreed the
     whole time.

Kind 3 is the half with user-visible value; kinds 1 and 2 are the half
that makes the divergence set closed (see
`test_parse_error_differential.py::test_every_remaining_divergence_is_a_
hint_or_the_rebind_sentence`).

WHAT IS MEASURED HERE, and why it is not the 54-program differential.
A whole-program corpus fills the got slot with whatever token happens to
sit at a refusal point --- four kinds out of the lexer's 29. This file
compares the RENDERING FUNCTIONS directly, `whence.parser._show` against
the guest's `show_tok`, over every token of a corpus chosen to cover the
kinds (`bench/showtok.py`), and it checks that that harness can fail.
"""
import os
import re
import sys

import pytest

from whence.interp import Interpreter
from whence.lexer import KEYWORDS, ONE_CHAR_OPS, TWO_CHAR_OPS, tokenize
from whence.parser import ParseError, _show, parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bench"))
import showtok as S                                              # noqa: E402

EXAMPLE = os.path.join(ROOT, "examples", "self_eval.lang")
SELF_HOST = os.path.join(ROOT, "examples", "self_host.lang")


@pytest.fixture(scope="module")
def rows():
    r, misaligned = S.sweep()
    assert not misaligned, misaligned
    return r


# --------------------------------------------------------------------------
# 1. the renderers agree, on every kind the lexer can emit
# --------------------------------------------------------------------------

def test_the_renderer_agrees_on_every_token_in_the_corpus(rows):
    bad = [r for r in rows if not r.agrees]
    assert not bad, bad[:8]
    assert len(rows) >= 400, len(rows)


def test_the_corpus_reaches_every_token_type_the_lexer_can_emit(rows):
    """DERIVED from `whence/lexer.py`, not listed here.

    A hand-written list of token kinds is a second copy of the lexer that
    nobody re-executes --- round 396's `bench/expectsites.py` retired
    exactly that shape for `_CATEGORY_PROSE`. If a future version adds an
    operator, this goes red until the corpus reaches it, which is the
    point: `show_tok` renders by token KIND, so an unreached kind is an
    unverified rendering.
    """
    declared = (set(TWO_CHAR_OPS) | set(ONE_CHAR_OPS)
                | {"NUMBER", "STRING", "NAME", "KW", "NEWLINE", "EOF"})
    seen = {r.kind for r in rows}
    assert declared - seen == set(), sorted(declared - seen)
    assert seen - declared == set(), sorted(seen - declared)


def test_the_corpus_reaches_every_keyword(rows):
    """A KW token renders through its VALUE, so `and` and `rescue` are
    different renderings, not one."""
    seen = {r.value for r in rows if r.kind == "KW"}
    assert KEYWORDS - seen == set(), sorted(KEYWORDS - seen)


def _plant_line(lib, needle, replacement):
    """Replace the ONE line of the guest library containing `needle`.

    v0.39 (round 408). The plants used to be (old_text, new_text) pairs
    written out in full, and the guest source they quote is Whence string
    literals inside Python string literals inside a docstring-bearing test
    file --- three levels of backslash. The v0.39 rewrite got one of them
    wrong in a way that PASSED its `lib.count(old) == 1` guard and then
    planted a real newline into a rendering, misaligning the sweep's
    `SEP.split`. Naming the line by a short unambiguous needle and
    replacing the whole line removes the level of escaping that was
    carrying the error.
    """
    lines = lib.splitlines(True)
    hits = [i for i, ln in enumerate(lines) if needle in ln]
    assert len(hits) == 1, (needle, hits)
    lines[hits[0]] = replacement
    return "".join(lines)


def test_the_sweep_can_actually_fail():
    """The negative control, and the reason the 0 above is a measurement.

    A parity harness that has never been observed red is a green light.
    One plant per branch of `show_tok`, plus one on the renderer it
    delegates to; each must be caught, and each must be caught in the
    RIGHT token kind.

    v0.39 (round 408): the STRING plant used to be *drop `repr`'s
    quote-switching rule*, and decision 48 deleted that rule, so the plant
    became a no-op edit. A plant that no longer perturbs anything asserts
    nothing about the sweep --- it asserts that the sweep sees a
    difference that is not there, and it goes red for a reason unrelated
    to blindness. The NEWLINE branch is new in v0.39 and gets its own.
    """
    lib = S.library_source()
    plants = [
        # the v0.24 defect this round fixed, put back
        ('{ "end of input" }', '  if k.t == "eof" { "the end" }\n', "EOF"),
        # quote a number, the other half of the same defect
        ('else if k.t == "num" { str(k.v) }',
         '  else if k.t == "num" { "<" + str(k.v) + ">" }\n', "NUMBER"),
        # v0.39: the prose decision 48 gives a line break
        ('{ "a line break" }', '  else if k.t == "nl" { "a newline" }\n',
         "NEWLINE"),
        # v0.39: perturb the STRING branch WITHOUT removing escaping.
        # `{ str(k.v) }` would be the obvious plant and it is unusable
        # here for the same reason `fn quote_str(s) { s }` is -- see
        # `test_the_plant_that_breaks_the_harness_instead_of_the_
        # comparison`. Any plant that stops escaping a newline
        # desynchronises `SEP` instead of diverging.
        ('{ quote_str(k.v) }',
         '  else if k.t == "str" { "<" + quote_str(k.v) + ">" }\n', "STRING"),
    ]
    for needle, replacement, kind in plants:
        rows, misaligned = S.sweep(library=_plant_line(lib, needle, replacement))
        assert not misaligned, (kind, misaligned)
        bad = [r for r in rows if not r.agrees]
        assert bad, "planting %r changed nothing --- the sweep is blind" % kind
        assert {r.kind for r in bad} == {kind}, (kind, sorted(
            {r.kind for r in bad}))


def test_the_plant_that_breaks_the_harness_instead_of_the_comparison():
    """The fifth plant, and the reason it is not in the list above.

    `guest_shows` gets the whole corpus back from ONE interpreter run as a
    single string joined by `SEP` (a newline), and splits it. That is safe
    only while no rendering can CONTAIN a newline -- which is true exactly
    because `quote_str` escapes one. So the single most direct plant on
    decision 48's renderer, `fn quote_str(s) { s }`, does not produce a
    divergence the comparison can see: it desynchronises the comparison.

    A parity harness whose records are joined by a character its subject
    may emit has TWO failure channels, and a negative control has to name
    which one it expects. This plant is caught, loudly, by the other one.
    Recorded as a test rather than as a comment because the day `SEP`
    changes, this is the thing that has to be re-derived.
    """
    lib = S.library_source()
    rows, misaligned = S.sweep(
        library=_plant_line(lib, 'fn quote_str(s)', 'fn quote_str(s) { s }\n'))
    assert misaligned, "the harness did not notice a renderer with no quotes"
    names = {n for n, _, _ in misaligned}
    assert names == {"string-with-newline-escape", "string-with-every-escape"}, \
        sorted(names)
    # ...and those are exactly the corpus snippets whose STRING value holds
    # a newline. Nothing else in the corpus can desynchronise it.
    from whence.lexer import tokenize as _tk
    holds_newline = {n for n, src in S.CORPUS
                     if any(t.type == "STRING" and "\n" in t.value
                            for t in _tk(src))}
    assert names == holds_newline, (sorted(names), sorted(holds_newline))


# --------------------------------------------------------------------------
# 2. the two residuals, which v0.39 removed rather than re-measured
# --------------------------------------------------------------------------
# v0.36 recorded two exemptions in the `skills/measured-exemption`
# discipline and asserted both ABSENT from the corpus. Decision 48 (v0.39,
# round 408) took both out of the exemption list, and only one of them is
# now clean. What is below is the pair of tests that replaces
# `test_the_two_known_residuals_are_absent_from_the_corpus`.


def _tok(type_, value):
    from whence.lexer import Token
    return Token(type_, value, 1, 1)


def test_the_first_residual_is_now_in_the_corpus_and_agrees(rows):
    """The non-printable one. It is no longer exempt, it is COVERED.

    `quote_str` renders an unspellable byte by copying it, so the guest
    renders it correctly without being able to name it -- an exemption
    removed by deleting the rule that needed it rather than by testing
    harder. The assertion is the inverse of v0.36's: the corpus must now
    CONTAIN such a byte, and every row must agree.
    """
    unspellable = [r for r in rows
                   if isinstance(r.value, str)
                   and any(not ch.isprintable() and ch not in "\n\t\r"
                           for ch in r.value)]
    assert unspellable, "the corpus stopped covering the first residual"
    assert all(r.agrees for r in unspellable), [r for r in unspellable
                                                if not r.agrees]
    seen = set("".join(r.value for r in unspellable))
    assert {"\x00", "\x07", "\x1b", "\x7f"} <= seen, sorted(map(ord, seen))


def test_v36s_unreachability_argument_was_false():
    """v0.36 said a non-printable byte was *"unreachable from source,
    because a literal cannot CONTAIN a byte it cannot spell"*, and offered
    `tokenize('let s = "a\\x00b"')` raising `bad escape` as the evidence.

    A literal cannot ESCAPE such a byte. It can contain one: the string
    scanner's fall-through is `out.append(ch)`, guarded only against `"`,
    `\\` and a raw newline. The escape form and the raw form are different
    programs and only one of them was ever run.
    """
    from whence.lexer import LexError
    with pytest.raises(LexError) as e:
        tokenize('let s = "a\\x00b"')          # the ESCAPE: \, x, 0, 0
    assert "bad escape" in str(e.value)

    toks = tokenize('let s = "a\x00b"')        # the RAW byte
    assert [t.value for t in toks if t.type == "STRING"] == ["a\x00b"]
    # ...and v0.36's own rendering of it, which decision 48 replaced
    assert repr("a\x00b") == "'a\\x00b'"       # what `_show` used to write
    assert _show(_tok("STRING", "a\x00b")) == '"a\x00b"'


def test_the_second_residual_was_a_lexer_divergence_wearing_a_renderer_name():
    """The integer one, and the reason it is still open.

    v0.36 described it as a RENDERING difference -- `str` summarises past
    `SHOW_INT_BITS`, `repr` does not -- and decision 48 closed exactly that
    by routing `_show` through `show_int`. What the description concealed
    is a divergence one layer down, in the LEXER, which is still there:

      * `num()` refuses numeric text past `SHOW_INT_DIGITS` (4000), which
        round 368 recorded as "Whence never accepts digits it could not
        print back";
      * `whence/lexer.py` accepts a literal of ANY length, so the rule
        holds at one door and not at the other;
      * the guest's `lit_num` is `num(text)` with `pos_inf` for a miss, so
        it walks through the door that refuses.

    The boundary is exact and it is asserted here rather than described.
    Closing it is a decision about what the language ACCEPTS, which is not
    what decision 48 is about.
    """
    from whence.values import SHOW_INT_DIGITS
    assert SHOW_INT_DIGITS == 4000
    assert S.KNOWN_DIVERGENT, "the exemption stopped being executable"
    for name, src, kind, why in S.KNOWN_DIVERGENT:
        rows, misaligned = S.sweep(cases=[(name, src)])
        assert not misaligned, (name, misaligned)
        bad = [r for r in rows if not r.agrees]
        assert bad, "%s no longer diverges -- %s" % (name, why)
        assert {r.kind for r in bad} == {kind}, sorted({r.kind for r in bad})
        assert bad[0].guest == "inf", bad[0]
        assert bad[0].host.startswith("<integer,"), bad[0]

    # ...and one digit fewer agrees, on both sides, which is what makes the
    # boundary a measurement instead of an anecdote. That case is in the
    # clean CORPUS, so this only has to name it.
    assert any(n == "integer-just-under-the-cap" for n, _ in S.CORPUS)


def test_the_host_lexer_and_num_disagree_about_the_same_text():
    """The mechanism above, on the HOST alone, with no guest involved --
    so it survives any future rewrite of `self_eval.lang`."""
    from whence.values import SHOW_INT_DIGITS
    for digits, num_misses in ((SHOW_INT_DIGITS, False),
                               (SHOW_INT_DIGITS + 1, True)):
        text = "9" * digits
        toks = tokenize("let a = %s" % text)
        lexed = [t.value for t in toks if t.type == "NUMBER"]
        assert len(lexed) == 1 and isinstance(lexed[0], int), lexed
        env = Interpreter().run('let a = num("%s")\n' % text)
        from whence.values import Miss
        # the binding is a provenance node; the miss is its PAYLOAD
        assert isinstance(env.get("a").payload, Miss) is num_misses, digits


# --------------------------------------------------------------------------
# 3. the guest's own renderer, unit by unit
# --------------------------------------------------------------------------

QUOTE_CASES = [
    "", "a", "hello world", "1", "1.5", "-", "a'b", 'a"b', "a'b\"c",
    "a\\b", "a\tb", "a\nb", "a\rb", "'", '"', "''", '""', "'\"",
    # v0.39: the bytes v0.36 said a guest could not compare against
    "a\x00b", "\x07", "\x1b\x7f", "a\x00\\\"b",
]


@pytest.fixture(scope="module")
def guest_quotes():
    lib = S.library_source()
    prog = [lib]
    for k, v in enumerate(QUOTE_CASES):
        prog.append('let __r%d = quote_str("%s")' % (k, S.escape(v)))
    env = Interpreter().run("\n".join(prog) + "\n")
    return [env.get("__r%d" % k).payload for k in range(len(QUOTE_CASES))]


def test_the_guest_quote_matches_the_host_quote_on_every_case(guest_quotes):
    """v0.36 asserted the guest matched Python's `repr`, quote-switching
    rule and all. The subject of the comparison is now the HOST's
    `quote_str`, which is Whence's own rule -- the guest mirrors this
    language, not the implementation language."""
    from whence.parser import quote_str
    for v, got in zip(QUOTE_CASES, guest_quotes):
        assert got == quote_str(v), (v, got, quote_str(v))
    # there is no quote-switching rule left to exercise: every rendering
    # opens and closes with a double quote, whatever the value holds.
    assert all(g.startswith('"') and g.endswith('"') for g in guest_quotes), \
        [g for g in guest_quotes if not g.startswith('"')]
    # ...and the guest's answers round-trip through the HOST's lexer.
    for v, got in zip(QUOTE_CASES, guest_quotes):
        assert [t.value for t in tokenize("let s = %s" % got)
                if t.type == "STRING"] == [v], (v, got)


# --------------------------------------------------------------------------
# 4. the want half: one guest helper is no longer six host spellings
# --------------------------------------------------------------------------

# Each LIVE host `what=` site, the smallest program that reaches it, and
# the sentence BOTH sides must now produce. `'{'` and `a name` are the two
# spellings that need no `what` on either side and are here as controls.
# `shape name` is deliberately NOT here --- see
# `test_the_dead_shape_name_site_is_dead_on_both_sides`.
WHAT_SITES = [
    ("field name after '.'", "let r = @{a: 1}\nlet v = r.1",
     "expected field name after '.', got 1"),
    ("field name (record)", "let r = @{1: 2}",
     "expected field name, got 1"),
    ("field name (shape)", "shape P = @{a: num, 1: num}",
     "expected field name, got 1"),
    ("parameter name", "fn f(1) { 1 }",
     "expected parameter name, got 1"),
    ("effect name", "fn f() effects [1] { 1 }",
     "expected effect name, got 1"),
    ("'@{' after shape name", "shape P = 1",
     "expected '@{' after shape name, got 1"),
    ("a name (control)", "let 1 = 2",
     "expected a name, got 1"),
    ("'{' (control)", "fn f(a)",
     "expected '{', got end of input"),
]


@pytest.fixture(scope="module")
def what_site_messages():
    lib = S.library_source()
    prog = [lib]
    for k, (_, src, _) in enumerate(WHAT_SITES):
        prog.append('let __w%d = str(parse_whence("%s"))' % (k, S.escape(src)))
    env = Interpreter().run("\n".join(prog) + "\n")
    return [env.get("__w%d" % k).payload for k in range(len(WHAT_SITES))]


@pytest.mark.parametrize("index", range(len(WHAT_SITES)),
                         ids=[w[0] for w in WHAT_SITES])
def test_each_host_what_site_has_the_same_guest_sentence(index,
                                                         what_site_messages):
    label, src, want = WHAT_SITES[index]
    try:
        parse(src)
        pytest.fail("[%s] the host accepted %r" % (label, src))
    except ParseError as e:
        host = re.sub(r" at line \d+, col \d+$", "", str(e))
    # the host may append a hint; the want/got halves are what is pinned
    assert host.split(" (")[0] == want, (label, host)
    guest = what_site_messages[index]
    guest = re.sub(r" \(line \d+\)$", "", guest.strip())
    guest = re.sub(r" at line \d+, col \d+$", "", guest[len("miss: "):])
    assert guest == want, (label, guest)


def test_the_dead_shape_name_site_is_dead_on_both_sides():
    """`bench/expectsites.py` classifies `parser.py:2044`
    (`what="shape name"`) as **never-fails**: executed 16 times over
    round 396's 3120-program mutation corpus and never once raised,
    because `shape` is CONTEXTUAL and `is_shape_head` has already tested
    that a NAME follows. That was a claim about the host, measured by
    mutation.

    The guest is an independently written grammar that reaches the same
    verdict from the same guard, which is a stronger corroboration than
    another 3000 host mutants would be: `shape 1 = @{a: num}` is not a
    shape at all on either side, it is two statements on one line, and
    both say so. The guest's `expect_name_as(..., "shape name")` is
    therefore as unobservable as the host's --- kept, like the host's, so
    that a grammar change which makes it reachable finds a sentence
    already written rather than `expected a name`.
    """
    src = "shape 1 = @{a: num}"
    try:
        parse(src)
        raise AssertionError("the host accepted %r" % src)
    except ParseError as e:
        assert str(e).startswith("two statements on one line"), str(e)
    lib = S.library_source()
    env = Interpreter().run(
        lib + 'let out = str(parse_whence("%s"))\n' % S.escape(src))
    assert "two statements on one line" in env.get("out").payload
    for text in (open(EXAMPLE, encoding="utf-8").read(),
                 open(SELF_HOST, encoding="utf-8").read()):
        assert '"shape name"' in text


def test_expect_name_no_longer_answers_six_questions_with_one_sentence():
    """The user-visible half of decision 45, stated as the regression it
    was rather than as a string comparison.

    Before this round every one of these said `expected a name` on the
    guest --- the same six words for a record key, a shape field, a
    parameter, an effect, a shape name and a `let` name, with no mention
    of the token that actually stopped the parse."""
    wants = {w for _, _, w in WHAT_SITES if w.startswith("expected ")}
    assert len(wants) == 7, sorted(wants)
    lib = S.library_source()
    assert "expected a name" in lib          # still there, as the DEFAULT
    assert lib.count('expect_name_as(toks, ') >= 6


# --------------------------------------------------------------------------
# 5. the two guest files stay one file
# --------------------------------------------------------------------------

def test_both_guest_files_carry_the_same_renderer():
    """`test_self_eval.py::test_parser_section_matches_self_host` pins the
    whole shared section; this names the three functions decision 45 added,
    so a partial sync fails with the reason rather than with a diff."""
    ev = open(EXAMPLE, encoding="utf-8").read()
    sh = open(SELF_HOST, encoding="utf-8").read()
    for fn in ("fn quote_body(s, i, acc) {", "fn quote_str(s) {",
               "fn show_tok(k) {", "fn expect_op_as(toks, pos, o, what) {",
               "fn expect_name_as(toks, pos, what) {"):
        assert ev.count(fn) == 1, (fn, ev.count(fn))
        assert sh.count(fn) == 1, (fn, sh.count(fn))
    # ...and the spelling the guest no longer writes. Comment lines are
    # excluded on purpose: both files RECALL the old wording in prose (the
    # round-164 effects note, the round-360 lex-error note), which is
    # history and stays.
    for text in (ev, sh):
        code = "\n".join(ln for ln in text.splitlines()
                         if not ln.lstrip().startswith("#"))
        assert "unexpected token" not in code, [
            ln for ln in code.splitlines() if "unexpected token" in ln]
        # v0.39: and the renderer decision 48 replaced. `repr_str` mirrored
        # Python's quote-switching rule; there is no such rule to mirror.
        assert "repr_str" not in code, [
            ln for ln in code.splitlines() if "repr_str" in ln]
