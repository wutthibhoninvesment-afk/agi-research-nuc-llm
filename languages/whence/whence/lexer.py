"""Lexer for Whence.

Newlines are statement separators, but are suppressed inside ( ), [ ] and
record literals @{ } so multi-line data and argument lists read naturally.
Block braces { } keep their newlines (blocks contain statements).
A newline directly after a token that cannot end a statement (a binary
operator, `=`, `:`, `,`, `and`/`or`/`not`/`rescue`) is a line continuation.

Source text is UTF-8 and STRINGS and COMMENTS hold any character; NAMES and
NUMERIC LITERALS are ASCII (v0.21, round 350) -- see `_DIGITS`/`_NAME_START`
below for why that is a narrowing and not just a spelling.
"""

KEYWORDS = {
    "let", "fn", "if", "else", "check", "rescue",
    "why", "snip", "miss", "true", "false", "and", "or", "not",
}

# v0.21 (round 350). These three sets were `str.isdigit()`, `str.isalpha()`
# and `str.isalnum()` -- Python's UNICODE classifications -- from the
# lexer's first commit until this round. Two things were wrong with that,
# and they are the same defect at two severities:
#
#   1. `str.isdigit()` is True for 798 characters. `let x = ٣` (Arabic-Indic
#      three) lexed to `NUMBER 3`, because `int()` accepts it too -- an
#      undocumented, unspecified numeral system nobody chose. SPEC.md's
#      "Limits that are errors, not crashes" has said the opposite since
#      v0.4.1: Whence number syntax is "optional sign, ASCII digits,
#      optional fraction, optional exponent", and `interp.py`'s `_NUM_RE`
#      enforces exactly that for `num(text)` -- with a comment naming
#      "non-ASCII digits" as one of the host-only spellings that is NOT a
#      number here. The literal grammar and the documented grammar
#      disagreed.
#   2. For 128 of those 798 characters `int()` RAISES. `let x = ²` was an
#      uncaught `ValueError` escaping `tokenize()` -- a Python traceback
#      out of `run.py`, not a `LexError`, not exit 2, not a miss. That is
#      the discipline SPEC's "errors, not crashes" section exists to state.
#
# Round 323 found and fixed the exponent half of the SAME literal-grammar-
# vs-`_NUM_RE` gap (`1e5` had no lexer support at all while `num("1e5")`
# worked); this is the digit-set half of it, left behind.
#
# `_NAME_START`/`_NAME_CONT` narrow for a third reason on top of those two:
# `examples/self_eval.lang`'s guest lexer -- the language's own reference
# implementation, and the arbiter round 336 used for tail-position order --
# has only ever had `contains("abcdefghijklmnopqrstuvwxyz...", c)`. A guest
# written in Whence cannot enumerate Unicode, so host/guest parity on names
# is unreachable in the widening direction and free in the narrowing one.
# Zero of the 30 `.lang` files in this tree contain a non-ASCII NAME token.
_DIGITS = "0123456789"
_NAME_START = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
_NAME_CONT = _NAME_START + _DIGITS

TWO_CHAR_OPS = ("==", "!=", "<=", ">=", "@{", "->")
ONE_CHAR_OPS = "+-*/%()[]{},:.=<>"

# Token types / keyword values after which a newline is a continuation.
CONTINUES = set("+-*/%,:=<>") | {"==", "!=", "<=", ">=", "->"}
CONTINUE_KWS = {"and", "or", "not", "rescue"}


class LexError(Exception):
    def __init__(self, message, line, col):
        super(LexError, self).__init__("%s at line %d, col %d" % (message, line, col))
        self.line = line
        self.col = col


class Token(object):
    __slots__ = ("type", "value", "line", "col")

    def __init__(self, type_, value, line, col):
        self.type = type_    # NUMBER STRING NAME KW NEWLINE EOF or the op itself
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self):
        return "Token(%s, %r, %d:%d)" % (self.type, self.value, self.line, self.col)


# v0.21 (round 350) adds `\r`. The lexer has SKIPPED a carriage return
# in source since its first commit (`if c in " \\t\\r"`, so a CRLF file
# lexes), yet the escape table had no way to WRITE one -- a character
# the language knew about but could not name. That hole is what made
# `examples/self_eval.lang`'s guest lexer unable to mirror the skip:
# a guest written in Whence cannot spell the character it must test
# for. See the guest `lex`'s whitespace branch.
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


def tokenize(src):
    tokens = []
    i = 0
    line = 1
    col = 1
    n = len(src)
    brackets = []  # stack of "(", "[", "@{", "{"

    def suppressed():
        if brackets and brackets[-1] in ("(", "[", "@{"):
            return True
        if not tokens:
            return False
        last = tokens[-1]
        return last.type in CONTINUES or \
            (last.type == "KW" and last.value in CONTINUE_KWS)

    while i < n:
        c = src[i]

        if c == "#":
            while i < n and src[i] != "\n":
                i += 1
            continue

        if c == "\n":
            if not suppressed():
                if tokens and tokens[-1].type != "NEWLINE":
                    tokens.append(Token("NEWLINE", "\n", line, col))
            i += 1
            line += 1
            col = 1
            continue

        if c in " \t\r":
            i += 1
            col += 1
            continue

        if c in _DIGITS:
            start = i
            start_col = col
            while i < n and src[i] in _DIGITS:
                i += 1
            if i < n and src[i] == "." and i + 1 < n and src[i + 1] in _DIGITS:
                i += 1
                while i < n and src[i] in _DIGITS:
                    i += 1
            # Optional exponent, mirroring `interp.py`'s own `_NUM_RE`
            # ("Whence decimal syntax": sign, digits, optional fraction,
            # optional exponent) -- SPEC.md's "Limits" section already
            # documents that grammar for `num(text)`'s STRING parsing, but
            # a raw SOURCE literal like `1e5` had no exponent handling at
            # all here: it silently split into `NUMBER(1)` followed by a
            # bare `NAME("e5")` token, an inconsistency between the
            # documented number syntax and the actual literal grammar
            # (found round 323, fuzzing `trunc`'s totality with `1e400` --
            # invisible to ~318 rounds of fuzzing because `fuzz.py`'s own
            # `STR_POOL` only ever feeds `"1e400"`/`"1e5"` through `num()`
            # as quoted STRING content, never as a raw source literal).
            # Only consumed when a full, valid exponent follows (optional
            # sign then at least one digit) so a bare trailing `e`/`E` that
            # isn't a number (the start of a NAME, e.g. `5experiment`)
            # lexes exactly as before.
            if i < n and src[i] in "eE":
                j = i + 1
                if j < n and src[j] in "+-":
                    j += 1
                if j < n and src[j] in _DIGITS:
                    while j < n and src[j] in _DIGITS:
                        j += 1
                    i = j
            text = src[start:i]
            # An exponent literal is always a float (`1e5` == `100000.0`,
            # not `100000`), matching `_NUM_RE`'s own `float(t) if
            # (m.group(2) or m.group(3))` rule (group 3 is the exponent).
            # An overflowing exponent (`1e400`) becomes Python's `inf`,
            # same as the PRE-EXISTING (and already fuzz-covered, see
            # `test_fuzz_regressions.py`) overflow path for a huge
            # digit-string-plus-fraction literal with no exponent at all
            # -- literal overflow silently becomes `inf`, unlike
            # `num("1e400")`'s "out of range" MISS, which is a string-
            # conversion-specific rule, not a literal-grammar one.
            value = (float(text) if ("." in text or "e" in text or "E" in text)
                     else int(text))
            col += i - start
            tokens.append(Token("NUMBER", value, line, start_col))
            continue

        if c in _NAME_START:
            start = i
            start_col = col
            while i < n and src[i] in _NAME_CONT:
                i += 1
            word = src[start:i]
            col += i - start
            if word in KEYWORDS:
                tokens.append(Token("KW", word, line, start_col))
            else:
                tokens.append(Token("NAME", word, line, start_col))
            continue

        if c == '"':
            start_line, start_col = line, col
            i += 1
            col += 1
            out = []
            while True:
                if i >= n or src[i] == "\n":
                    raise LexError("unterminated string", start_line, start_col)
                ch = src[i]
                if ch == '"':
                    i += 1
                    col += 1
                    break
                if ch == "\\":
                    if i + 1 >= n:
                        raise LexError("unterminated string", start_line, start_col)
                    esc = src[i + 1]
                    if esc not in _ESCAPES:
                        raise LexError("bad escape '\\%s'" % esc, line, col)
                    out.append(_ESCAPES[esc])
                    i += 2
                    col += 2
                    continue
                out.append(ch)
                i += 1
                col += 1
            tokens.append(Token("STRING", "".join(out), start_line, start_col))
            continue

        two = src[i:i + 2]
        if two in TWO_CHAR_OPS:
            if two == "@{":
                brackets.append("@{")
            tokens.append(Token(two, two, line, col))
            i += 2
            col += 2
            continue

        if c in ONE_CHAR_OPS:
            if c in "([{":
                brackets.append(c)
            elif c in ")]}":
                if brackets:
                    brackets.pop()
            tokens.append(Token(c, c, line, col))
            i += 1
            col += 1
            continue

        raise LexError("unexpected character %r" % c, line, col)

    tokens.append(Token("EOF", None, line, col))
    return tokens
