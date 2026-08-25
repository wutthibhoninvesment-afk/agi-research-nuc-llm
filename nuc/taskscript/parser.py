"""Errand AST + recursive-descent parser + link checks (SPEC §Grammar, §6).

`parse(src)` returns a linked Program or raises ParseError; every static
discipline (duplicate names, unknown lane/budget, arity, undefined names,
interpolation of undeclared names, the forbidden frontier port) is enforced
here so the interpreter only ever sees a consistent program.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Union
from urllib.parse import urlparse

from .lexer import LexError, Token, tokenize

FORBIDDEN_PORTS = (8001,)          # GLM frontier lane on pgain-nuc: one stray request evicts a 550 s KV cache
LANE_KEYS = ("url", "model", "prefill", "decode", "fixed", "ctx", "tools")
EXPECT_KINDS = ("one_of", "contains", "nonempty", "json")
BUILTINS = {"why": 1, "missed": 1, "len": 1, "lower": 1, "trim": 1}
KEYWORDS = {"lane", "budget", "task", "flow", "on", "within", "retry", "backoff",
            "let", "if", "else", "emit", "rescue", "true", "false"}


class ParseError(Exception):
    def __init__(self, msg: str, line: int, col: int = 0):
        super().__init__(f"{msg} at line {line}" + (f":{col}" if col else ""))
        self.line, self.col = line, col


# ------------------------------------------------------------------ AST

@dataclass
class Str:
    parts: list            # str literal chunks and ("name",) interpolations, in order
    line: int


@dataclass
class Num:
    value: Union[int, float]
    line: int


@dataclass
class Bool:
    value: bool
    line: int


@dataclass
class Name:
    name: str
    line: int


@dataclass
class Call:
    name: str
    args: list
    line: int


@dataclass
class Rescue:
    left: object
    right: object
    line: int


@dataclass
class Cmp:
    op: str
    left: object
    right: object
    line: int


@dataclass
class Let:
    name: str
    expr: object
    line: int


@dataclass
class If:
    cond: object
    then: list
    else_: list
    line: int


@dataclass
class Emit:
    expr: object
    line: int


@dataclass
class Expect:
    kind: str
    args: list
    line: int


@dataclass
class Lane:
    name: str
    url: str
    model: str
    prefill: Union[float, str]       # tokens/s or "e1"
    decode: float
    fixed: float
    ctx: Optional[int]
    tools: bool
    line: int


@dataclass
class Budget:
    name: str
    time_s: Optional[float]
    tokens: Optional[int]
    line: int


@dataclass
class Task:
    name: str
    params: list
    lane: str
    budget: Optional[str]
    retry: int
    backoff_s: float
    system: Optional[Str]
    user: Str
    reply: int
    expect: Optional[Expect]
    line: int


@dataclass
class Flow:
    name: str
    params: list
    budget: Optional[str]
    body: list
    line: int


@dataclass
class Program:
    lanes: dict = field(default_factory=dict)
    budgets: dict = field(default_factory=dict)
    tasks: dict = field(default_factory=dict)
    flows: dict = field(default_factory=dict)


# ------------------------------------------------------------------ strings

_INTERP = re.compile(r"\{\{|\}\}|\{([A-Za-z_][A-Za-z0-9_]*)\}|\{|\}")


def split_interpolation(text: str, line: int) -> list:
    """'a {x} b {{c}}' -> ['a ', ('x',), ' b {c}']; lone braces are errors."""
    parts: list = []
    buf: list[str] = []
    pos = 0
    for m in _INTERP.finditer(text):
        buf.append(text[pos:m.start()])
        tok = m.group(0)
        if tok == "{{":
            buf.append("{")
        elif tok == "}}":
            buf.append("}")
        elif m.group(1):
            if buf:
                parts.append("".join(buf))
                buf = []
            parts.append((m.group(1),))
        else:
            raise ParseError(f"lone {tok!r} in string (use {tok*2!r} for a literal brace)", line)
        pos = m.end()
    buf.append(text[pos:])
    joined = "".join(buf)
    if joined or not parts:
        parts.append(joined)
    return parts


def interpolated_names(s: Str) -> list[str]:
    return [p[0] for p in s.parts if isinstance(p, tuple)]


# ------------------------------------------------------------------ parser

class Parser:
    def __init__(self, tokens: list[Token]):
        self.toks = tokens
        self.i = 0

    # -- token helpers
    def peek(self, k: int = 0) -> Token:
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def advance(self) -> Token:
        t = self.toks[self.i]
        if t.type != "EOF":
            self.i += 1
        return t

    def at(self, type_: str, value: object = None) -> bool:
        t = self.peek()
        return t.type == type_ and (value is None or t.value == value)

    def at_kw(self, word: str) -> bool:
        return self.at("NAME", word)

    def expect(self, type_: str, value: object = None, what: str = "") -> Token:
        t = self.peek()
        if t.type != type_ or (value is not None and t.value != value):
            want = what or (repr(value) if value is not None else type_)
            got = repr(t.value) if t.value is not None else t.type
            raise ParseError(f"expected {want}, got {got}", t.line, t.col)
        return self.advance()

    def expect_kw(self, word: str) -> Token:
        return self.expect("NAME", word)

    def skip_newlines(self) -> None:
        while self.at("NEWLINE"):
            self.advance()

    def name(self, what: str = "name") -> Token:
        t = self.expect("NAME", what=what)
        if t.value in KEYWORDS:
            raise ParseError(f"{t.value!r} is a keyword, not a {what}", t.line, t.col)
        return t

    # -- program
    def program(self) -> Program:
        prog = Program()
        self.skip_newlines()
        while not self.at("EOF"):
            t = self.peek()
            if self.at_kw("lane"):
                self._add(prog.lanes, self.lane(), "lane")
            elif self.at_kw("budget"):
                self._add(prog.budgets, self.budget(), "budget")
            elif self.at_kw("task"):
                self._add(prog.tasks, self.task(), "task")
            elif self.at_kw("flow"):
                self._add(prog.flows, self.flow(), "flow")
            else:
                raise ParseError(f"expected lane/budget/task/flow, got {t.value!r}", t.line, t.col)
            self.skip_newlines()
        return prog

    @staticmethod
    def _add(table: dict, node, kind: str) -> None:
        if node.name in table:
            raise ParseError(f"duplicate {kind} {node.name!r} (first at line {table[node.name].line})", node.line)
        table[node.name] = node

    def _number(self, what: str) -> Union[int, float]:
        return self.expect("NUMBER", what=what).value

    def _duration(self, what: str) -> float:
        t = self.peek()
        if t.type == "DURATION":
            return self.advance().value
        if t.type == "NUMBER":                # bare number = seconds
            return float(self.advance().value)
        raise ParseError(f"expected a duration (e.g. 90s, 2m) for {what}, got {t.value!r}", t.line, t.col)

    # -- lane
    def lane(self) -> Lane:
        head = self.expect_kw("lane")
        nm = self.name("lane name")
        self.expect("LBRACE")
        fields: dict = {}
        self.skip_newlines()
        while not self.at("RBRACE"):
            key = self.expect("NAME", what="lane key")
            if key.value not in LANE_KEYS:
                raise ParseError(f"unknown lane key {key.value!r} (want one of {', '.join(LANE_KEYS)})", key.line, key.col)
            if key.value in fields:
                raise ParseError(f"duplicate lane key {key.value!r}", key.line, key.col)
            if key.value in ("url", "model"):
                fields[key.value] = self.expect("STRING", what=f"string for {key.value}").value
            elif key.value == "prefill":
                if self.at_kw("e1"):
                    self.advance()
                    fields["prefill"] = "e1"
                else:
                    fields["prefill"] = float(self._number("prefill tokens/s"))
            elif key.value == "decode":
                fields["decode"] = float(self._number("decode tokens/s"))
            elif key.value == "fixed":
                fields["fixed"] = self._duration("fixed")
            elif key.value == "ctx":
                fields["ctx"] = int(self._number("ctx tokens"))
            elif key.value == "tools":
                t = self.expect("NAME", what="yes|no")
                if t.value not in ("yes", "no"):
                    raise ParseError(f"tools wants yes|no, got {t.value!r}", t.line, t.col)
                fields["tools"] = t.value == "yes"
            self.skip_newlines()
        self.expect("RBRACE")
        for req in ("url", "decode"):
            if req not in fields:
                raise ParseError(f"lane {nm.value!r} needs {req}", head.line)
        if "prefill" not in fields:
            raise ParseError(f"lane {nm.value!r} needs prefill (tokens/s or e1)", head.line)
        url = fields["url"]
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ParseError(f"lane {nm.value!r}: url must be http(s)://host[:port], got {url!r}", head.line)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port in FORBIDDEN_PORTS:
            raise ParseError(f"lane {nm.value!r}: port {port} is the frontier lane (forbidden by rule)", head.line)
        for k in ("decode",):
            if fields[k] <= 0:
                raise ParseError(f"lane {nm.value!r}: {k} must be positive", head.line)
        if fields["prefill"] != "e1" and fields["prefill"] <= 0:
            raise ParseError(f"lane {nm.value!r}: prefill must be positive", head.line)
        return Lane(nm.value, url, fields.get("model", nm.value), fields["prefill"], fields["decode"],
                    fields.get("fixed", 0.0), fields.get("ctx"), fields.get("tools", False), head.line)

    # -- budget
    def budget(self) -> Budget:
        head = self.expect_kw("budget")
        nm = self.name("budget name")
        self.expect("LBRACE")
        time_s: Optional[float] = None
        tokens: Optional[int] = None
        self.skip_newlines()
        while not self.at("RBRACE"):
            key = self.expect("NAME", what="time|tokens")
            if key.value == "time":
                if time_s is not None:
                    raise ParseError("duplicate time", key.line, key.col)
                time_s = self._duration("time")
            elif key.value == "tokens":
                if tokens is not None:
                    raise ParseError("duplicate tokens", key.line, key.col)
                tokens = int(self._number("tokens"))
            else:
                raise ParseError(f"budget key must be time or tokens, got {key.value!r}", key.line, key.col)
            self.skip_newlines()
        self.expect("RBRACE")
        if time_s is None and tokens is None:
            raise ParseError(f"budget {nm.value!r} declares nothing", head.line)
        if (time_s is not None and time_s <= 0) or (tokens is not None and tokens <= 0):
            raise ParseError(f"budget {nm.value!r}: limits must be positive", head.line)
        return Budget(nm.value, time_s, tokens, head.line)

    # -- params
    def params(self) -> list[str]:
        self.expect("LPAREN")
        out: list[str] = []
        if not self.at("RPAREN"):
            while True:
                p = self.name("parameter")
                if p.value in out:
                    raise ParseError(f"duplicate parameter {p.value!r}", p.line, p.col)
                out.append(p.value)
                if self.at("COMMA"):
                    self.advance()
                    continue
                break
        self.expect("RPAREN")
        return out

    # -- task
    def task(self) -> Task:
        head = self.expect_kw("task")
        nm = self.name("task name")
        params = self.params()
        self.expect_kw("on")
        lane = self.name("lane name").value
        budget = None
        retry = 0
        backoff = 1.0
        seen: set = set()
        while self.peek().type == "NAME" and self.peek().value in ("within", "retry", "backoff"):
            kw = self.advance().value
            if kw in seen:
                raise ParseError(f"duplicate {kw}", head.line)
            seen.add(kw)
            if kw == "within":
                budget = self.name("budget name").value
            elif kw == "retry":
                retry = int(self._number("retry count"))
                if retry < 0:
                    raise ParseError("retry must be >= 0", head.line)
            else:
                backoff = self._duration("backoff")
                if backoff < 0:
                    raise ParseError("backoff must be >= 0", head.line)
        self.expect("LBRACE")
        system: Optional[Str] = None
        user: Optional[Str] = None
        reply = 64
        expect: Optional[Expect] = None
        fields: set = set()
        self.skip_newlines()
        while not self.at("RBRACE"):
            key = self.expect("NAME", what="system|user|reply|expect")
            if key.value in fields:
                raise ParseError(f"duplicate {key.value} in task {nm.value!r}", key.line, key.col)
            fields.add(key.value)
            if key.value == "system":
                system = self.string()
            elif key.value == "user":
                user = self.string()
            elif key.value == "reply":
                reply = int(self._number("reply tokens"))
                if reply < 1:
                    raise ParseError("reply must be >= 1", key.line, key.col)
            elif key.value == "expect":
                expect = self.expect_clause()
            else:
                raise ParseError(f"task key must be system/user/reply/expect, got {key.value!r}", key.line, key.col)
            self.skip_newlines()
        self.expect("RBRACE")
        if user is None:
            raise ParseError(f"task {nm.value!r} needs a user prompt", head.line)
        t = Task(nm.value, params, lane, budget, retry, backoff, system, user, reply, expect, head.line)
        for s in (system, user):
            if s is not None:
                for ref in interpolated_names(s):
                    if ref not in params:
                        raise ParseError(f"task {nm.value!r} interpolates {{{ref}}} which is not a parameter", s.line)
        return t

    def expect_clause(self) -> Expect:
        kind = self.expect("NAME", what="|".join(EXPECT_KINDS))
        if kind.value not in EXPECT_KINDS:
            raise ParseError(f"expect wants {'|'.join(EXPECT_KINDS)}, got {kind.value!r}", kind.line, kind.col)
        args: list = []
        if kind.value == "one_of":
            while self.at("STRING"):
                args.append(self.advance().value)
            if not args:
                raise ParseError("expect one_of needs at least one string", kind.line, kind.col)
        elif kind.value == "contains":
            args.append(self.expect("STRING", what="string").value)
        return Expect(kind.value, args, kind.line)

    def string(self) -> Str:
        t = self.expect("STRING", what="string")
        return Str(split_interpolation(t.value, t.line), t.line)

    # -- flow
    def flow(self) -> Flow:
        head = self.expect_kw("flow")
        nm = self.name("flow name")
        params = self.params()
        budget = None
        if self.at_kw("within"):
            self.advance()
            budget = self.name("budget name").value
        body = self.block()
        return Flow(nm.value, params, budget, body, head.line)

    def block(self) -> list:
        self.expect("LBRACE")
        stmts: list = []
        self.skip_newlines()
        while not self.at("RBRACE"):
            stmts.append(self.stmt())
            if not self.at("RBRACE"):
                self.expect("NEWLINE", what="newline or '}'")
            self.skip_newlines()
        self.expect("RBRACE")
        return stmts

    def stmt(self):
        t = self.peek()
        if self.at_kw("let"):
            self.advance()
            nm = self.name("binding name")
            self.expect("EQ")
            return Let(nm.value, self.expr(), t.line)
        if self.at_kw("if"):
            return self.if_stmt()
        if self.at_kw("emit"):
            self.advance()
            return Emit(self.expr(), t.line)
        raise ParseError(f"expected let/if/emit, got {t.value!r}", t.line, t.col)

    def if_stmt(self) -> If:
        head = self.expect_kw("if")
        cond = self.expr()
        then = self.block()
        else_: list = []
        if self.at_kw("else"):
            self.advance()
            if self.at_kw("if"):
                else_ = [self.if_stmt()]
            else:
                else_ = self.block()
        return If(cond, then, else_, head.line)

    # -- expressions
    def expr(self):
        return self.rescue()

    def rescue(self):
        left = self.cmp()
        while self.at_kw("rescue"):
            t = self.advance()
            left = Rescue(left, self.cmp(), t.line)
        return left

    def cmp(self):
        left = self.unary()
        if self.at("EQEQ") or self.at("NEQ"):
            t = self.advance()
            right = self.unary()
            if self.at("EQEQ") or self.at("NEQ"):
                u = self.peek()
                raise ParseError("chained comparison is not allowed", u.line, u.col)
            return Cmp(t.value, left, right, t.line)
        return left

    def unary(self):
        t = self.peek()
        if t.type == "STRING":
            self.advance()
            return Str(split_interpolation(t.value, t.line), t.line)
        if t.type == "NUMBER":
            self.advance()
            return Num(t.value, t.line)
        if t.type == "LPAREN":
            self.advance()
            e = self.expr()
            self.expect("RPAREN")
            return e
        if t.type == "NAME":
            if t.value in ("true", "false"):
                self.advance()
                return Bool(t.value == "true", t.line)
            if t.value in KEYWORDS:
                raise ParseError(f"unexpected keyword {t.value!r}", t.line, t.col)
            self.advance()
            if self.at("LPAREN"):
                self.advance()
                args: list = []
                if not self.at("RPAREN"):
                    while True:
                        args.append(self.expr())
                        if self.at("COMMA"):
                            self.advance()
                            continue
                        break
                self.expect("RPAREN")
                return Call(t.value, args, t.line)
            return Name(t.value, t.line)
        got = repr(t.value) if t.value is not None else t.type
        raise ParseError(f"expected an expression, got {got}", t.line, t.col)


# ------------------------------------------------------------------ link

def link(prog: Program) -> Program:
    """Static checks across declarations; returns prog for chaining."""
    for t in prog.tasks.values():
        if t.lane not in prog.lanes:
            raise ParseError(f"task {t.name!r}: unknown lane {t.lane!r}", t.line)
        if t.budget is not None and t.budget not in prog.budgets:
            raise ParseError(f"task {t.name!r}: unknown budget {t.budget!r}", t.line)
        if t.name in BUILTINS:
            raise ParseError(f"task {t.name!r} shadows a builtin", t.line)
        lane = prog.lanes[t.lane]
        if lane.ctx is not None and t.reply >= lane.ctx:
            raise ParseError(f"task {t.name!r}: reply {t.reply} cannot fit lane {lane.name!r} ctx {lane.ctx}", t.line)
    for f in prog.flows.values():
        if f.budget is not None and f.budget not in prog.budgets:
            raise ParseError(f"flow {f.name!r}: unknown budget {f.budget!r}", f.line)
        if f.name in prog.tasks or f.name in BUILTINS:
            raise ParseError(f"flow {f.name!r} collides with a task or builtin", f.line)
        _check_block(prog, f.body, set(f.params))
    return prog


def _check_block(prog: Program, stmts: list, scope: set) -> None:
    scope = set(scope)
    for s in stmts:
        if isinstance(s, Let):
            _check_expr(prog, s.expr, scope)
            if s.name in scope:
                raise ParseError(f"{s.name!r} is already bound in this block (no rebinding)", s.line)
            scope.add(s.name)
        elif isinstance(s, If):
            _check_expr(prog, s.cond, scope)
            _check_block(prog, s.then, scope)
            _check_block(prog, s.else_, scope)
        elif isinstance(s, Emit):
            _check_expr(prog, s.expr, scope)


def _check_expr(prog: Program, e, scope: set) -> None:
    if isinstance(e, Str):
        for ref in interpolated_names(e):
            if ref not in scope:
                raise ParseError(f"{{{ref}}} is not bound here", e.line)
    elif isinstance(e, Name):
        if e.name not in scope:
            raise ParseError(f"{e.name!r} is not bound here", e.line)
    elif isinstance(e, Call):
        for a in e.args:
            _check_expr(prog, a, scope)
        if e.name in prog.tasks:
            want = len(prog.tasks[e.name].params)
        elif e.name in prog.flows:
            want = len(prog.flows[e.name].params)
        elif e.name in BUILTINS:
            want = BUILTINS[e.name]
        else:
            raise ParseError(f"unknown task/flow/builtin {e.name!r}", e.line)
        if len(e.args) != want:
            raise ParseError(f"{e.name!r} takes {want} argument(s), got {len(e.args)}", e.line)
    elif isinstance(e, (Rescue, Cmp)):
        _check_expr(prog, e.left, scope)
        _check_expr(prog, e.right, scope)
    elif isinstance(e, (Num, Bool)):
        pass
    else:
        raise ParseError(f"internal: unknown expression node {type(e).__name__}", getattr(e, "line", 0))


def parse_program(src: str) -> Program:
    """Parse without link checks (used by tests that want the raw tree)."""
    try:
        toks = tokenize(src)
    except LexError as ex:
        raise ParseError(str(ex).rsplit(" at ", 1)[0], ex.line, ex.col) from None
    p = Parser(toks)
    prog = p.program()
    if not p.at("EOF"):
        t = p.peek()
        raise ParseError(f"unexpected {t.value!r}", t.line, t.col)
    return prog


def parse(src: str) -> Program:
    return link(parse_program(src))
