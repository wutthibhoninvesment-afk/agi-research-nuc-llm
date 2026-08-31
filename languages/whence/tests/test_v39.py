r"""Whence v0.39 (round 408, language C) — decision 48: the got slot speaks
Whence.

Decision 44 (v0.35, round 396) fixed the WANT half of `expected X, got Y`:
a want is either a quoted literal the author can type verbatim or a
category rendered as prose, never a bare token and never an implementation
identifier. The GOT half stayed `repr(tok.value)` — Python's syntax, in
four different ways at once:

  * `repr` picks its quote character by INSPECTING the value, so a KEYWORD
    and a STRING carrying the same text render identically. `let let = 1`
    and `let "let" = 1` both said `expected a name, got 'let'`.
  * `repr` writes `\x00` for a byte Whence's escape table cannot spell —
    a spelling no Whence program can contain — and that byte IS reachable
    (see `test_a_raw_unspellable_byte_reaches_a_string_token`).
  * `repr` of the NEWLINE token wrote `'\n'`, a Python escape sitting in
    the same slot as the prose `end of input`.
  * `repr` of an int ignores `values.SHOW_INT_BITS`, so a 4000-digit
    literal at a refusal point emitted a 4146-character parse error.

And `_spell`, the HINT-side renderer, was `'"%s"' % value` with no escaping
at all, so its instruction could not be followed.

These tests are host-side and cost milliseconds. The guest half is measured
in `tests/test_v36.py` (renderer parity, via `bench/showtok.py`) and
`tests/test_parse_error_differential.py` (whole programs).
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from whence import values                                        # noqa: E402
from whence.lexer import LexError, Token, tokenize               # noqa: E402
from whence.parser import (ParseError, _show, _spell, parse,     # noqa: E402
                           quote_str)


def reason(src):
    """The host's parse-error sentence, position stripped."""
    try:
        parse(src)
    except ParseError as e:
        return re.sub(r" at line \d+, col \d+$", "", str(e))
    raise AssertionError("parsed, but should not have: %r" % src)


def position(src):
    try:
        parse(src)
    except ParseError as e:
        return (e.line, e.col)
    raise AssertionError("parsed, but should not have: %r" % src)


# --------------------------------------------------------------------------
# 1. the renderer is round-trip exact, by construction and by exhaustion
# --------------------------------------------------------------------------

def test_every_byte_round_trips():
    """The property the whole decision rests on, over the whole domain.

    `quote_str` escapes the five characters `whence/lexer.py:_ESCAPES` can
    spell and copies everything else. So for EVERY single-byte value —
    printable, control, or a byte no Whence escape can name — the
    rendering is a Whence string literal whose value is the input. 256
    cases, not a sample: the domain is small enough to exhaust, so
    exhausting it is the honest test.
    """
    bad = []
    for i in range(256):
        ch = chr(i)
        lit = quote_str(ch)
        try:
            toks = tokenize("let s = %s" % lit)
        except LexError as e:
            bad.append((i, lit, "LexError: %s" % e))
            continue
        strings = [t for t in toks if t.type == "STRING"]
        if len(strings) != 1 or strings[0].value != ch:
            bad.append((i, lit, [(t.type, t.value) for t in toks]))
    assert bad == [], bad[:8]


def test_the_round_trip_test_can_fail():
    """An instrument never seen red is a green light (round 398's rule).

    Drop the backslash row — the one that must run first — and the byte
    that needs it stops round-tripping.
    """
    def broken(s):
        for raw, esc in (('"', '\\"'), ("\n", "\\n")):
            s = s.replace(raw, esc)
        return '"%s"' % s
    with pytest.raises(LexError):
        tokenize("let s = %s" % broken("\\"))
    # ...and the ORDER inside the real table is what makes it work: if the
    # backslash pass ran last it would re-escape the escapes the earlier
    # passes introduced.
    assert quote_str('a"b') == '"a\\"b"'
    assert quote_str("a\\b") == '"a\\\\b"'


def test_quote_str_never_invents_a_spelling_whence_lacks():
    """No `\\xNN`, no `\\0`, no `\\a` — the escape table is closed at five.

    The characters `quote_str` may introduce a backslash before are
    exactly `whence/lexer.py:_ESCAPES`' keys, read from the lexer rather
    than restated here, so widening the lexer without widening this
    renderer cannot go unnoticed.
    """
    from whence.lexer import _ESCAPES
    introduced = set()
    for i in range(256):
        out = quote_str(chr(i))[1:-1]
        if out.startswith("\\"):
            introduced.add(out[1])
    assert introduced == set(_ESCAPES), (introduced, set(_ESCAPES))
    assert introduced == {"n", "t", "r", '"', "\\"}


# --------------------------------------------------------------------------
# 2. the collision decision 48 exists to remove
# --------------------------------------------------------------------------

def test_a_keyword_and_a_string_spelled_alike_no_longer_collide():
    """The headline. Two different programs, two different token KINDS,
    byte-identical messages before this version."""
    kw = reason("let let = 1")
    st = reason('let "let" = 1')
    assert kw == "expected a name, got 'let'"
    assert st == 'expected a name, got "let"'
    assert kw != st


def test_the_collision_was_real_and_not_theoretical():
    """…and here is the pre-v0.39 rendering, so the claim above is a
    measurement of a change rather than an assertion about the present.

    `repr` is what both kinds used to go through, and `repr` of a
    3-character keyword and of a 3-character string value are the same
    five characters.
    """
    assert repr("let") == repr("let") == "'let'"
    assert _show(Token("KW", "let", 1, 1)) == "'let'"
    assert _show(Token("STRING", "let", 1, 1)) == '"let"'


@pytest.mark.parametrize("src,want", [
    ('fn f("a") { 1 }', 'expected parameter name, got "a"'),
    ('let "a" = 1', 'expected a name, got "a"'),
    ('let r = @{"a": 1}', 'expected field name, got "a"'),
    ('let x = (1 "a")', 'expected \')\', got "a"'),
    ('let r = @{a: 1}\nlet v = r."a"', 'expected field name after \'.\', got "a"'),
])
def test_a_string_in_the_got_slot_is_a_whence_literal(src, want):
    """Five reachable programs, one per `_show` call path that a STRING can
    reach. Round 398 measured the got slot as filled by four token kinds
    across 51 programs and STRING was not among them — these are the
    programs that put it there."""
    assert reason(src) == want


def test_a_newline_in_the_got_slot_is_prose():
    assert reason("let x\nlet y = 1") == "expected '=', got a line break"
    assert "\\n" not in reason("let x\nlet y = 1")


def test_the_number_slot_still_reads_as_a_number():
    """Decision 48 does not re-quote what decision 44 and v0.24 settled."""
    assert reason("check 1: 1 == 1") == \
        "expected a string label after 'check', got 1"
    assert reason("check 1.5: 1 == 1") == \
        "expected a string label after 'check', got 1.5"


# --------------------------------------------------------------------------
# 3. the language's own integer cap, in the one renderer that ignored it
# --------------------------------------------------------------------------

def test_a_huge_literal_in_the_got_slot_honours_show_int_bits():
    """Round 368 gave Whence a rule: an integer past `SHOW_INT_BITS` is
    summarised, because rendering it in full is what made `print` of an
    unbounded integer a raw host traceback. `_show` was the one renderer
    that had never heard of it, so the PARSER could emit what the RUNTIME
    is forbidden to.
    """
    digits = "9" * 4100
    n = int(digits)
    assert n.bit_length() > values.SHOW_INT_BITS, n.bit_length()
    msg = reason("fn f(%s) { 1 }" % digits)
    assert msg == "expected parameter name, got <integer, %d bits>" % n.bit_length()
    assert len(msg) < 80, len(msg)
    assert digits[:50] not in msg
    # ...and the boundary is the language's, not the host's: a literal just
    # UNDER the cap still renders in full.
    small = "9" * 100
    assert reason("fn f(%s) { 1 }" % small) == \
        "expected parameter name, got %s" % small


def test_the_summary_is_the_same_function_the_runtime_uses():
    """Not a re-implementation of the rule — the rule itself. If round
    368's cap moves, both move together."""
    n = int("9" * 4100)
    assert values.show_int(n) in reason("fn f(%s) { 1 }" % ("9" * 4100))


# --------------------------------------------------------------------------
# 4. the hint half: an instruction that can be followed
# --------------------------------------------------------------------------

HINT = re.compile(r"start `(.*)` on the next line")


@pytest.mark.parametrize("value", [
    "hi", 'he said "hi"', "back\\slash", "it's", "a\tb", "a\x00b", "",
])
def test_the_separator_hint_can_be_followed(value):
    """`_spell` was `'"%s"' % value`. For a value holding a `"` the hint
    said *start `"he said "hi""` on the next line*, which lexes as a
    string, a name and an empty string; for one holding a `\\` following it
    is a `bad escape`. This test does what the hint says — pastes the
    backticked text onto the next line — and requires the result to be one
    STRING token with the original value.
    """
    src = "let a = 1 %s" % quote_str(value)
    m = HINT.search(reason(src))
    assert m, reason(src)
    toks = tokenize("let a = 1\n%s" % m.group(1))
    strings = [t for t in toks if t.type == "STRING"]
    assert len(strings) == 1, [(t.type, t.value) for t in toks]
    assert strings[0].value == value


def test_the_hint_and_the_got_slot_now_use_one_renderer():
    """Two renderings of one idea was the shape; one is the fix. `_spell`
    differs from `_show` on a STRING in NOTHING, which is worth pinning
    because the two functions carry a comment saying they must not be
    merged — they must not, and they must agree here."""
    for v in ["a", 'a"b', "a\\b", "a'b", "a\nb", "a\x00b"]:
        tok = Token("STRING", v, 1, 1)
        assert _spell(tok) == _show(tok) == quote_str(v), v


# --------------------------------------------------------------------------
# 5. what v0.36's exemption got wrong
# --------------------------------------------------------------------------

def test_a_raw_unspellable_byte_reaches_a_string_token():
    """v0.36 recorded a NON-PRINTABLE character as an exemption and gave a
    reachability argument: *"a literal cannot CONTAIN a byte it cannot
    spell"*. It cannot ESCAPE one. It can contain one, because
    `whence/lexer.py`'s string scanner copies every byte except `"`, `\\`
    and a raw newline straight into the value.

    Both spellings, in one test, because the difference between them is
    the whole error: the escape form is a different program.
    """
    with pytest.raises(LexError) as e:
        tokenize('let s = "a\\x00b"')          # the ESCAPE: \, x, 0, 0
    assert "bad escape" in str(e.value)

    toks = tokenize('let s = "a\x00b"')        # the RAW byte
    strings = [t for t in toks if t.type == "STRING"]
    assert len(strings) == 1
    assert strings[0].value == "a\x00b"

    # ...and it reaches a rendered message, end to end.
    assert reason('fn f("a\x00b") { 1 }') == \
        'expected parameter name, got "a\x00b"'


@pytest.mark.parametrize("ch", ["\x00", "\t", "\r", "\x07", "\x1b", "\x7f"])
def test_the_reachable_set_is_every_byte_but_three(ch):
    toks = tokenize('let s = "a%sb"' % ch)
    assert [t.value for t in toks if t.type == "STRING"] == ["a%sb" % ch]


@pytest.mark.parametrize("ch", ["\n"])
def test_the_three_that_are_not_reachable_raw(ch):
    with pytest.raises(LexError):
        tokenize('let s = "a%sb"' % ch)


def test_the_exemption_is_gone_rather_than_re_measured():
    """The point of decision 48 for the guest: there is no `\\xNN` rule
    left to mirror, so rendering an unspellable byte is the IDENTITY and a
    guest can do it without being able to name the byte. Stated as the
    property: `quote_str` of a string containing only unspellable bytes
    contains those bytes verbatim and introduces no backslash."""
    v = "\x00\x07\x1b\x7f"
    out = quote_str(v)
    assert out == '"%s"' % v
    assert "\\" not in out


# --------------------------------------------------------------------------
# 6. what the change is NOT allowed to have done
# --------------------------------------------------------------------------

@pytest.mark.parametrize("src", [
    "let let = 1", "let = 2", "let x = (1", 'fn f("a") { 1 }',
    "let x\nlet y = 1", "let a = 1 \"hi\"", "let r = @{a: 1,}",
])
def test_no_position_moved(src):
    """Decision 34 rule 2: a version that changes a message must say
    whether it moved a position. This one says no, with the numbers — the
    positions below are the ones HEAD produced, recorded before the edit."""
    expected = {
        "let let = 1": (1, 5),
        "let = 2": (1, 5),
        "let x = (1": (1, 11),
        'fn f("a") { 1 }': (1, 6),
        "let x\nlet y = 1": (1, 6),
        "let a = 1 \"hi\"": (1, 11),
        "let r = @{a: 1,}": (1, 16),
    }
    assert position(src) == expected[src]


def test_show_no_longer_calls_repr_on_anything_but_a_float():
    """Read off the SOURCE's AST rather than off a grep, because a grep for
    `repr(` finds it in comments and docstrings too, and round 404's rule
    is to classify from the structure.

    One `repr` call may remain in `_show`: the float branch, where Python's
    float repr IS the language's rule (`values._show` uses the same one).
    """
    import ast
    import inspect
    from whence import parser as P
    tree = ast.parse(inspect.getsource(P._show))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    names = sorted(n.func.id for n in calls)
    assert names == ["isinstance", "quote_str", "repr", "show_int"], names
    assert names.count("repr") == 1, names
    # ...and the surviving `repr` is under a float guard, not a fallthrough.
    src = inspect.getsource(P._show)
    i = src.index("return repr(tok.value)")
    assert "isinstance(tok.value, int)" in src[:i]
    assert src.rindex('tok.type == "NUMBER"', 0, i) > src.index("EOF")


def test_the_check_that_would_have_stayed_green():
    """`examples/self_host.lang` carried a check named *"a string in the
    got slot switches quotes when it holds a single one"*, asserting
    `got "a'b"`. Decision 48 DELETED the quote-switching rule, and the
    assertion still passes: a string is now always double-quoted, so
    `"a'b"` comes out either way.

    A check whose name states a mechanism and whose body cannot see the
    mechanism go away is not a check on that mechanism. This test is the
    evidence for the replacement, and it is the reason the replacement is
    a PAIR of programs (a keyword and a string) rather than one.
    """
    assert reason('let f = fn(x) { x }\nlet v = f(1 "a\'b")') == \
        'expected \')\', got "a\'b"'          # true before AND after
    assert repr("a'b") == '"a\'b"'            # ...for the OLD reason
    assert quote_str("a'b") == '"a\'b"'       # ...and the NEW one


def test_the_language_has_one_string_rendering_rule_and_two_implementations():
    """`whence/values.py:_quote` renders a string for the RUNTIME (`print`,
    `why`, a failing check's report). It is Whence-native and predates this
    version — and it is not the same function, deliberately.

    Pinned here rather than shared, with the exact difference, so a future
    round unifying them knows what it is changing: `values._quote`
    truncates to a `limit` and does not escape `\\t` or `\\r`, both of which
    are wrong for a diagnostic that is quoting what the author typed.
    """
    assert values._quote("a\tb", None) == '"a\tb"'      # raw tab, no escape
    assert quote_str("a\tb") == '"a\\tb"'               # escaped
    assert values._quote("a\rb", None) == '"a\rb"'
    assert quote_str("a\rb") == '"a\\rb"'
    # they AGREE on the three that matter to both
    for v in ["a\\b", 'a"b', "a\nb", "plain"]:
        assert values._quote(v, None) == quote_str(v), v
    # ...and only `quote_str`'s output re-lexes for the tab.
    assert [t.value for t in tokenize("let s = %s" % quote_str("a\tb"))
            if t.type == "STRING"] == ["a\tb"]


def test_the_bare_quote_is_repr_for_every_token_the_lexer_can_emit():
    """`_show`'s fallthrough is `"'%s'" % value`, replacing `repr(value)`.
    That is only safe while no KW, NAME or operator value can contain a
    quote or a backslash — which is a claim about the LEXER, so it is
    measured against the lexer's own tables rather than asserted.
    """
    from whence.lexer import KEYWORDS, ONE_CHAR_OPS, TWO_CHAR_OPS
    vals = set(KEYWORDS) | set(ONE_CHAR_OPS) | set(TWO_CHAR_OPS)
    vals |= {"x", "someName", "_a1", "shape", "effects"}
    for v in sorted(vals):
        assert "'" not in v and "\\" not in v, v
        assert _show(Token("NAME", v, 1, 1)) == repr(v) == "'%s'" % v
