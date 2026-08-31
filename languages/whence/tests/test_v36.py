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


def test_the_sweep_can_actually_fail():
    """The negative control, and the reason the 0 above is a measurement.

    A parity harness that has never been observed red is a green light.
    Three plants, one per rule `show_tok` implements; each must be caught,
    and each must be caught in the RIGHT token kind.
    """
    lib = S.library_source()
    plants = [
        # the v0.24 defect this round fixed, put back
        ('  if k.t == "eof" { "end of input" }', '  if k.t == "eof" { "\'\'" }',
         "EOF"),
        # quote a number, the other half of the same defect
        ('  else if k.t == "num" { str(k.v) }',
         '  else if k.t == "num" { "\'" + str(k.v) + "\'" }', "NUMBER"),
        # drop `repr`'s quote-switching rule
        ('  let q = if contains(s, "\'") and not contains(s, "\\"") { "\\"" } '
         'else { "\'" }',
         '  let q = "\'"', "STRING"),
    ]
    for old, new, kind in plants:
        assert lib.count(old) == 1, (lib.count(old), old)
        rows, misaligned = S.sweep(library=lib.replace(old, new))
        assert not misaligned, (kind, misaligned)
        bad = [r for r in rows if not r.agrees]
        assert bad, "planting %r changed nothing --- the sweep is blind" % kind
        assert {r.kind for r in bad} == {kind}, (kind, sorted(
            {r.kind for r in bad}))


# --------------------------------------------------------------------------
# 2. the two residuals, measured rather than shrugged at
# --------------------------------------------------------------------------

def test_the_two_known_residuals_are_absent_from_the_corpus(rows):
    """`skills/measured-exemption` (round 359): an exemption nobody
    measured is a shrug.

    `repr_str` mirrors Python `repr` for printable ASCII, including its
    quote-switching rule. Two things it cannot mirror:

      * a NON-PRINTABLE character. `repr` writes `\x00`; `whence/lexer.py`'s
        `_ESCAPES` can spell exactly `\n \t \r \" \\`, so a guest cannot
        write the character to compare against, let alone render it. It is
        also unreachable from source for the same reason --- a literal
        cannot CONTAIN a byte it cannot spell.
      * an integer past `values.SHOW_INT_BITS` (13287 bits, ~4000 digits),
        which `str` summarises as `<integer, N bits>` by design (round 368)
        and `repr` does not.

    Both are asserted absent here, so "the sweep is clean" is not resting
    on a corpus that quietly avoids the hard cases.
    """
    from whence.values import SHOW_INT_BITS
    for r in rows:
        if isinstance(r.value, str):
            assert all(ch.isprintable() or ch in "\n\t\r" for ch in r.value), r
        if isinstance(r.value, int) and not isinstance(r.value, bool):
            assert r.value.bit_length() < SHOW_INT_BITS, r


def test_the_first_residual_is_real_and_not_theoretical():
    """`_show` and `show_tok` DO diverge on a non-printable, and the
    divergence is unreachable from Whence source. Both halves asserted:
    the first says the exemption names something real, the second says it
    cannot bite."""
    from whence.lexer import LexError
    assert _show(_tok("STRING", "a\x00b")) == "'a\\x00b'"
    with pytest.raises(LexError) as e:
        tokenize('let s = "a\\x00b"')
    assert "bad escape" in str(e.value)


def _tok(type_, value):
    from whence.lexer import Token
    return Token(type_, value, 1, 1)


# --------------------------------------------------------------------------
# 3. the guest's own renderer, unit by unit
# --------------------------------------------------------------------------

REPR_CASES = [
    "", "a", "hello world", "1", "1.5", "-", "a'b", 'a"b', "a'b\"c",
    "a\\b", "a\tb", "a\nb", "a\rb", "'", '"', "''", '""', "'\"",
]


@pytest.fixture(scope="module")
def guest_reprs():
    lib = S.library_source()
    prog = [lib]
    for k, v in enumerate(REPR_CASES):
        prog.append('let __r%d = repr_str("%s")' % (k, S.escape(v)))
    env = Interpreter().run("\n".join(prog) + "\n")
    return [env.get("__r%d" % k).payload for k in range(len(REPR_CASES))]


def test_the_guest_repr_matches_python_repr_on_every_case(guest_reprs):
    """Including the rule most hand-written mirrors miss: Python switches
    to DOUBLE quotes when the value contains a single quote and no double
    quote, and only then."""
    for v, got in zip(REPR_CASES, guest_reprs):
        assert got == repr(v), (v, got, repr(v))
    # the switching rule is exercised in both directions, not just present
    assert guest_reprs[REPR_CASES.index("a'b")].startswith('"')
    assert guest_reprs[REPR_CASES.index("a'b\"c")].startswith("'")


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
    for fn in ("fn repr_body(s, i, acc, q) {", "fn repr_str(s) {",
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
