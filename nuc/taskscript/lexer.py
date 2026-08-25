"""Errand lexer: tokenize(src) -> [Token(type, value, line, col)].

Token types: NAME NUMBER DURATION STRING LPAREN RPAREN LBRACE RBRACE COMMA
EQ EQEQ NEQ NEWLINE EOF. DURATION values are seconds (float). Newlines are
statement separators; they are suppressed inside parentheses (data) but not
inside braces (blocks), consecutive newlines collapse, none is emitted first.
"""
from __future__ import annotations

from dataclasses import dataclass


class LexError(Exception):
    def __init__(self, msg: str, line: int, col: int):
        super().__init__(f"{msg} at {line}:{col}")
        self.line, self.col = line, col


@dataclass(frozen=True)
class Token:
    type: str
    value: object
    line: int
    col: int

    def __repr__(self) -> str:
        return f"Token({self.type}, {self.value!r}, {self.line}:{self.col})"


_SIMPLE = {"(": "LPAREN", ")": "RPAREN", "{": "LBRACE", "}": "RBRACE", ",": "COMMA"}
_DURATION_UNITS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


def tokenize(src: str) -> list[Token]:
    toks: list[Token] = []
    i, line, col = 0, 1, 1
    depth = 0  # parentheses depth: newlines inside are data separators, not statements
    n = len(src)

    def emit(t: str, v: object, ln: int, c: int) -> None:
        toks.append(Token(t, v, ln, c))

    while i < n:
        ch = src[i]
        if ch == "#":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if ch == "\n":
            if depth == 0 and toks and toks[-1].type != "NEWLINE":
                emit("NEWLINE", None, line, col)
            i += 1
            line += 1
            col = 1
            continue
        if ch in " \t\r":
            i += 1
            col += 1
            continue
        start_col = col
        if ch in _SIMPLE:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            emit(_SIMPLE[ch], ch, line, start_col)
            i += 1
            col += 1
            continue
        if src.startswith("==", i):
            emit("EQEQ", "==", line, start_col); i += 2; col += 2; continue
        if src.startswith("!=", i):
            emit("NEQ", "!=", line, start_col); i += 2; col += 2; continue
        if ch == "=":
            emit("EQ", "=", line, start_col); i += 1; col += 1; continue
        if ch == '"':
            j = i + 1
            buf: list[str] = []
            while True:
                if j >= n or src[j] == "\n":
                    raise LexError("unterminated string", line, start_col)
                c = src[j]
                if c == '"':
                    break
                if c == "\\":
                    if j + 1 >= n or src[j + 1] not in _ESCAPES:
                        raise LexError("bad escape in string", line, start_col + (j - i))
                    buf.append(_ESCAPES[src[j + 1]])
                    j += 2
                    continue
                buf.append(c)
                j += 1
            emit("STRING", "".join(buf), line, start_col)
            col += j + 1 - i
            i = j + 1
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and src[i + 1].isdigit()):
            j = i
            seen_dot = False
            while j < n and (src[j].isdigit() or (src[j] == "." and not seen_dot)):
                seen_dot = seen_dot or src[j] == "."
                j += 1
            num_text = src[i:j]
            k = j
            while k < n and src[k].isalpha():
                k += 1
            unit = src[j:k]
            if unit:
                if unit not in _DURATION_UNITS:
                    raise LexError(f"unknown duration unit {unit!r}", line, start_col)
                emit("DURATION", float(num_text) * _DURATION_UNITS[unit], line, start_col)
                col += k - i
                i = k
                continue
            value = float(num_text) if seen_dot else int(num_text)
            emit("NUMBER", value, line, start_col)
            col += j - i
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            emit("NAME", src[i:j], line, start_col)
            col += j - i
            i = j
            continue
        raise LexError(f"unexpected character {ch!r}", line, start_col)
    if toks and toks[-1].type != "NEWLINE":
        emit("NEWLINE", None, line, col)
    emit("EOF", None, line, col)
    return toks
