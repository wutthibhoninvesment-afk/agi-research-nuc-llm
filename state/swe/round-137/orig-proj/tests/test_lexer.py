import pytest

from whence.lexer import tokenize, LexError


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
