"""Lexer for Whence.

Newlines are statement separators, but are suppressed inside ( ), [ ] and
record literals @{ } so multi-line data and argument lists read naturally.
Block braces { } keep their newlines (blocks contain statements).
A newline directly after a token that cannot end a statement (a binary
operator, `=`, `:`, `,`, `and`/`or`/`not`/`rescue`) is a line continuation.
"""

KEYWORDS = {
    "let", "fn", "if", "else", "check", "rescue",
    "why", "snip", "miss", "true", "false", "and", "or", "not",
}

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


_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


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

        if c.isdigit():
            start = i
            start_col = col
            while i < n and src[i].isdigit():
                i += 1
            if i < n and src[i] == "." and i + 1 < n and src[i + 1].isdigit():
                i += 1
                while i < n and src[i].isdigit():
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
                if j < n and src[j].isdigit():
                    while j < n and src[j].isdigit():
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

        if c.isalpha() or c == "_":
            start = i
            start_col = col
            while i < n and (src[i].isalnum() or src[i] == "_"):
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
