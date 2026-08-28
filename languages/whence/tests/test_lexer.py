import pytest

from whence.lexer import tokenize, LexError, Token


def types(src):
    return [t.type for t in tokenize(src)]


def test_numbers():
    toks = tokenize("12 3.5 0")
    assert [t.value for t in toks[:3]] == [12, 3.5, 0]
    assert isinstance(toks[0].value, int)
    assert isinstance(toks[1].value, float)


def test_number_then_dot_is_not_float():
    # "1.foo" lexes as NUMBER '.' NAME (field access on a number)
    toks = tokenize("1.foo")
    assert [t.type for t in toks[:3]] == ["NUMBER", ".", "NAME"]


def test_string_escapes():
    toks = tokenize('"a\\nb\\"c\\\\d"')
    assert toks[0].value == 'a\nb"c\\d'


def test_unterminated_string():
    with pytest.raises(LexError):
        tokenize('"abc')
    with pytest.raises(LexError):
        tokenize('"abc\ndef"')


def test_bad_escape():
    with pytest.raises(LexError):
        tokenize('"a\\qb"')


def test_keywords_vs_names():
    toks = tokenize("let letx fn fnord miss missed")
    assert [(t.type, t.value) for t in toks[:6]] == [
        ("KW", "let"), ("NAME", "letx"), ("KW", "fn"),
        ("NAME", "fnord"), ("KW", "miss"), ("NAME", "missed")]


def test_comments_skipped():
    toks = tokenize("1 # a comment\n2")
    assert [t.type for t in toks] == ["NUMBER", "NEWLINE", "NUMBER", "EOF"]


def test_newlines_collapse():
    toks = tokenize("1\n\n\n2")
    assert [t.type for t in toks] == ["NUMBER", "NEWLINE", "NUMBER", "EOF"]


def test_no_leading_newline():
    toks = tokenize("\n\n1")
    assert [t.type for t in toks] == ["NUMBER", "EOF"]


def test_newlines_suppressed_in_parens_brackets_records():
    assert "NEWLINE" not in types("(1 +\n 2)")
    assert "NEWLINE" not in types("[1,\n2,\n3]")
    assert "NEWLINE" not in types('@{a: 1,\nb: 2}')


def test_newlines_kept_in_blocks():
    assert "NEWLINE" in types("{ let x = 1\nx }")


def test_two_char_ops():
    toks = tokenize("== != <= >= @{")
    assert [t.type for t in toks[:5]] == ["==", "!=", "<=", ">=", "@{"]


def test_positions():
    toks = tokenize('let x = 1\nlet y = 2')
    assert (toks[0].line, toks[0].col) == (1, 1)
    y = [t for t in toks if t.value == "y"][0]
    assert (y.line, y.col) == (2, 5)


def test_unexpected_char():
    with pytest.raises(LexError):
        tokenize("let x = $")


def test_newline_after_operator_or_colon_continues_line():
    from whence.interp import Interpreter
    src = 'let a = 1 +\n  2\ncheck "x":\n  a ==\n  3\nlet b = true and\n  false\nlet c = [1,\n 2]'
    interp = Interpreter()
    env = interp.run(src)
    assert env.get("a").payload == 3
    assert env.get("b").payload is False
    assert interp.checks[0]["ok"] is True


def test_newline_after_value_still_separates():
    toks = tokenize("let a = 1\nlet b = 2")
    assert [t.type for t in toks if t.type == "NEWLINE"] == ["NEWLINE"]


def test_newline_after_keyword_value_still_separates():
    # test_newline_after_value_still_separates above only exercises a NUMBER
    # as the line-ending token. suppressed()'s `last.type == "KW" and
    # last.value in CONTINUE_KWS` check is easy to over-broaden into
    # "any KW ends a continuation" (e.g. `and`/`bool`-mutating the guard),
    # which this NUMBER-ending case can't catch since a KW never appears
    # there. `true`/`false`/`miss` are ordinary VALUE keywords, not
    # continuation keywords (and/or/not/rescue) -- a newline right after one
    # must still separate statements.
    toks = tokenize("let a = true\nlet b = 2")
    assert [t.type for t in toks if t.type == "NEWLINE"] == ["NEWLINE"]
    assert [(t.type, t.value) for t in toks] == [
        ("KW", "let"), ("NAME", "a"), ("=", "="), ("KW", "true"),
        ("NEWLINE", "\n"), ("KW", "let"), ("NAME", "b"), ("=", "="),
        ("NUMBER", 2), ("EOF", None)]


def test_comment_at_eof_with_no_trailing_newline():
    # the comment-skip loop's `while i < n and src[i] != "\n": i += 1` bound
    # must stop exactly at `i == n`, not read one past it, when the source
    # ends inside a comment with no final newline.
    toks = tokenize("let x = 1\n# trailing comment, no newline after")
    assert [t.type for t in toks] == ["KW", "NAME", "=", "NUMBER", "NEWLINE", "EOF"]


def test_number_immediately_followed_by_dot_at_eof():
    # a NUMBER whose digit run ends exactly at end-of-source must not probe
    # past the string when checking for a following float '.': the digit
    # loop leaves i == n, so the float-lookahead's own `i < n` guard is what
    # keeps `src[i]` in bounds.
    toks = tokenize("let x = 1\n5.")
    assert [(t.type, t.value) for t in toks] == [
        ("KW", "let"), ("NAME", "x"), ("=", "="), ("NUMBER", 1),
        ("NEWLINE", "\n"), ("NUMBER", 5), (".", "."), ("EOF", None)]


def test_unterminated_string_ending_in_backslash_at_eof_raises_lexerror():
    # a string that never closes and whose very last source character is a
    # bare backslash must still raise the controlled LexError, not crash
    # with an IndexError from probing src[i + 1] past the end of the source.
    with pytest.raises(LexError, match="unterminated string"):
        tokenize('"\\')


def test_token_repr():
    # Token.__repr__ is never exercised by tokenize() itself or by any other
    # test (it's a debug-only path); pin it directly so it isn't silently
    # dead code the suite can't tell apart from a broken one.
    assert repr(Token("NUMBER", 5, 3, 7)) == "Token(NUMBER, 5, 3:7)"


def test_positions_after_string_and_op_tokens_on_one_line():
    # test_positions above only checks two tokens near the start of a line.
    # `col` is advanced by a separate `col += N` at each of: entering a
    # string's first char, every ordinary string char, a 2-char escape
    # sequence, the closing quote, a two-char op, and a one-char op -- each
    # is independently capable of drifting by a fixed amount that only shows
    # up in a LATER same-line token's column (a trailing newline resets col
    # to 1 and hides it). One line exercising all six col-tracking sites,
    # cross-checked by hand. (The escape-sequence site, line 134's
    # `col += 2`, is a 7th col-drift mutation-testing gap this round found
    # that round 245's original 19-survivor report didn't list -- an
    # earlier draft of this same test used a plain "ab" string with no
    # escape sequence in it, which structurally can't reach line 134 at
    # all; confirmed as a real kill by direct in-process token-stream
    # diffing against the mutant, no subprocess/pytest involved.)
    toks = tokenize('12 "a\\nb" == c + (1)\n')
    assert [(t.type, t.value, t.line, t.col) for t in toks] == [
        ("NUMBER", 12, 1, 1),
        ("STRING", "a\nb", 1, 4),
        ("==", "==", 1, 11),
        ("NAME", "c", 1, 14),
        ("+", "+", 1, 16),
        ("(", "(", 1, 18),
        ("NUMBER", 1, 1, 19),
        (")", ")", 1, 20),
        ("NEWLINE", "\n", 1, 21),
        ("EOF", None, 2, 1),
    ]
