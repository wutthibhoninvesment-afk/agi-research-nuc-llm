"""Recursive-descent parser for Whence.

Enforced at parse time (not runtime):
  - a block must end with an expression statement (expression-oriented, no null)
  - `if` must have `else`
  - a name may be bound (`let`/`fn`) only once per block; params must be unique
"""

from .lexer import tokenize
from . import ast_nodes as A


class ParseError(Exception):
    def __init__(self, message, line, col):
        super(ParseError, self).__init__(
            "%s at line %d, col %d" % (message, line, col))
        self.line = line
        self.col = col


COMPARE_OPS = ("==", "!=", "<", "<=", ">", ">=")

# Recursive descent costs ~11 host frames per nesting level (60 levels ≈
# 660 frames, safe under CPython's default 1000 even inside a test runner);
# past this many nested expressions the parser reports an error instead of
# crashing with RecursionError (fuzz, round 9). Left-associative chains (`1 + 1 +
# …`) loop and are not nesting.
MAX_NESTING = 60

# Structural types (v0.12): the primitive tags a `: Type` annotation may
# name besides a previously declared `shape`. Erased entirely at parse
# time into `typed(...)` guard calls (see `_apply_type_guards`) — the
# interpreter never sees a "type", only ordinary Let/Call/Str nodes.
PRIMITIVE_TYPES = frozenset(["num", "str", "bool", "list", "record", "fn", "any"])


class Parser(object):
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.nesting = 0
        # name -> [(field, type_name), …], in declaration order; a shape
        # may only reference shapes declared earlier (single pass, no
        # forward refs — the field's spec value must already be bound at
        # the point a later shape's record literal reads it by name).
        self.shapes = {}

    def _enter(self):
        self.nesting += 1
        if self.nesting > MAX_NESTING:
            tok = self.peek()
            raise ParseError("expression nested more than %d levels deep" %
                             MAX_NESTING, tok.line, tok.col)

    # --- token helpers -------------------------------------------------
    def peek(self, offset=0):
        i = min(self.pos + offset, len(self.tokens) - 1)
        return self.tokens[i]

    def next(self):
        tok = self.tokens[self.pos]
        if tok.type != "EOF":
            self.pos += 1
        return tok

    def at(self, type_, value=None):
        tok = self.peek()
        if tok.type != type_:
            return False
        return value is None or tok.value == value

    def expect(self, type_, value=None, what=None):
        tok = self.peek()
        if not self.at(type_, value):
            want = what or (value if value is not None else type_)
            raise ParseError("expected %s, got %r" % (want, tok.value),
                             tok.line, tok.col)
        return self.next()

    def skip_newlines(self):
        while self.at("NEWLINE"):
            self.next()

    # --- statements ----------------------------------------------------
    def parse_program(self):
        stmts = self.stmt_list(end="EOF")
        tok = self.expect("EOF")
        return A.Program(1, stmts)

    def stmt_list(self, end):
        """Parse statements until `end` token type; check duplicate bindings."""
        stmts = []
        bound = {}
        self.skip_newlines()
        while not self.at(end):
            s = self.statement()
            name = getattr(s, "name", None) if isinstance(s, (A.Let, A.FnDef)) else None
            if name is not None:
                if name in bound:
                    raise ParseError(
                        "'%s' is already bound in this block (line %d); "
                        "Whence has no rebinding" % (name, bound[name]),
                        s.line, 0)
                bound[name] = s.line
            stmts.append(s)
            self.skip_newlines()
        return stmts

    def statement(self):
        tok = self.peek()
        if tok.type == "KW" and tok.value == "let":
            self.next()
            name = self.expect("NAME").value
            self.expect("=")
            expr = self.expression()
            return A.Let(tok.line, name, expr)
        if tok.type == "KW" and tok.value == "fn" and self.peek(1).type == "NAME":
            self.next()
            name = self.expect("NAME").value
            params, types = self.param_list()
            body = self.block()
            self._apply_type_guards(body, params, types, name)
            mark_tails(body)
            return A.FnDef(tok.line, name, params, body)
        if tok.type == "KW" and tok.value == "check":
            self.next()
            label = self.expect("STRING", what="a string label after 'check'").value
            self.expect(":")
            expr = self.expression()
            return A.Check(tok.line, label, expr)
        # `shape` is a contextual keyword, not a reserved word: only
        # "NAME NAME =" at the start of a statement triggers it (no other
        # legal statement starts with two bare names in a row), so a
        # program that happens to bind something called `shape` is
        # unaffected.
        if tok.type == "NAME" and tok.value == "shape" and \
                self.peek(1).type == "NAME" and self.peek(2).type == "=":
            return self.shape_def()
        expr = self.expression()
        return A.ExprStmt(expr.line, expr)

    def param_list(self):
        """`(a, b: num, c: Point)` -> (["a","b","c"], [None,"num","Point"])."""
        self.expect("(")
        params = []
        types = []
        if not self.at(")"):
            while True:
                p = self.expect("NAME", what="parameter name")
                if p.value in params:
                    raise ParseError("duplicate parameter '%s'" % p.value,
                                     p.line, p.col)
                params.append(p.value)
                if self.at(":"):
                    self.next()
                    types.append(self.parse_type())
                else:
                    types.append(None)
                if self.at(","):
                    self.next()
                    continue
                break
        self.expect(")")
        return params, types

    def parse_type(self):
        """A type name in annotation position: a primitive tag or a
        `shape` declared earlier in this file (single pass, no forward
        refs — see `self.shapes`)."""
        tok = self.peek()
        if tok.type == "KW" and tok.value == "fn":
            self.next()
            name = "fn"
        elif tok.type == "NAME":
            self.next()
            name = tok.value
        else:
            raise ParseError("expected a type name", tok.line, tok.col)
        if name not in PRIMITIVE_TYPES and name not in self.shapes:
            raise ParseError("unknown type '%s'" % name, tok.line, tok.col)
        return name

    def _type_spec_expr(self, type_name, line):
        """The AST expression a `typed`/`matches` call reads its spec
        from: a primitive tag is a string literal; a shape name is a
        NameRef to the record `shape` bound it to (so nested shapes are
        the SAME value, not a copy — real structural composition)."""
        if type_name in PRIMITIVE_TYPES:
            return A.Str(line, type_name)
        return A.NameRef(line, type_name)

    def _apply_type_guards(self, body, params, types, fn_name):
        """Prepend one `let <param> = typed(<param>, <spec>, <label>)` per
        annotated parameter to the body's statement list (v0.12). This is
        the WHOLE feature's runtime cost: an untyped function's body is
        untouched, byte-identical to v0.11. A typed one is ordinary sugar
        over the existing miss/propagation machinery — no interpreter
        change, no new AST node, no effect on tail position (mark_tails
        only ever looks at the LAST statement, and this only prepends)."""
        if not any(t is not None for t in types):
            return
        suffix = " of %s" % fn_name if fn_name else ""
        guards = []
        for pname, tname in zip(params, types):
            if tname is None:
                continue
            spec = self._type_spec_expr(tname, body.line)
            label = A.Str(body.line, "parameter '%s'%s" % (pname, suffix))
            call = A.Call(body.line, A.NameRef(body.line, "typed"),
                         [A.NameRef(body.line, pname), spec, label], False)
            guards.append(A.Let(body.line, pname, call))
        body.stmts[0:0] = guards

    def shape_def(self):
        """`shape Name = @{field: type, …}` — pure sugar for `let Name =
        @{__shape: "Name", field: <spec>, …}` (see `_type_spec_expr`): a
        `shape` is a real, ordinary runtime record, so `matches(x, Name)`
        and nested shape fields work by reading an ordinary binding, and
        the ordinary parser rule against rebinding a name already applies
        to it (it reaches `stmt_list`'s duplicate-name check as an
        `A.Let`, indistinguishable from a hand-written one)."""
        tok = self.next()   # 'shape'
        name_tok = self.expect("NAME", what="shape name")
        name = name_tok.value
        if name in PRIMITIVE_TYPES:
            raise ParseError("'%s' is a reserved type name" % name,
                             name_tok.line, name_tok.col)
        if name in self.shapes:
            raise ParseError("shape '%s' is already declared" % name,
                             name_tok.line, name_tok.col)
        self.expect("=")
        self.expect("@{", what="'@{' after shape name")
        fields = []
        pairs = [("__shape", A.Str(tok.line, name))]
        seen = set()
        if not self.at("}"):
            while True:
                f = self.expect("NAME", what="field name")
                if f.value in seen:
                    raise ParseError("duplicate field '%s'" % f.value,
                                     f.line, f.col)
                seen.add(f.value)
                self.expect(":")
                ftype = self.parse_type()
                fields.append((f.value, ftype))
                pairs.append((f.value, self._type_spec_expr(ftype, tok.line)))
                if self.at(","):
                    self.next()
                    continue
                break
        self.expect("}")
        self.shapes[name] = fields
        return A.Let(tok.line, name, A.RecordLit(tok.line, pairs))

    def block(self):
        open_tok = self.expect("{", what="'{'")
        stmts = self.stmt_list(end="}")
        close = self.expect("}")
        if not stmts:
            raise ParseError("block must contain at least one expression",
                             open_tok.line, open_tok.col)
        if not isinstance(stmts[-1], A.ExprStmt):
            raise ParseError("block must end with an expression",
                             close.line, close.col)
        return A.Block(open_tok.line, stmts)

    # --- expressions (precedence low -> high) --------------------------
    def expression(self):
        self._enter()
        try:
            return self.rescue_expr()
        finally:
            self.nesting -= 1

    def rescue_expr(self):
        left = self.or_expr()
        while self.at("KW", "rescue"):
            tok = self.next()
            right = self.or_expr()
            left = A.Rescue(tok.line, left, right)
        return left

    def or_expr(self):
        left = self.and_expr()
        while self.at("KW", "or"):
            tok = self.next()
            right = self.and_expr()
            left = A.Binary(tok.line, "or", left, right)
        return left

    def and_expr(self):
        left = self.not_expr()
        while self.at("KW", "and"):
            tok = self.next()
            right = self.not_expr()
            left = A.Binary(tok.line, "and", left, right)
        return left

    def not_expr(self):
        if self.at("KW", "not"):
            tok = self.next()
            return A.Unary(tok.line, "not", self.not_expr())
        return self.comparison()

    def comparison(self):
        left = self.additive()
        if self.peek().type in COMPARE_OPS:
            tok = self.next()
            right = self.additive()
            if self.peek().type in COMPARE_OPS:
                bad = self.peek()
                raise ParseError(
                    "comparisons do not chain; use 'and'", bad.line, bad.col)
            return A.Binary(tok.line, tok.type, left, right)
        return left

    def additive(self):
        left = self.multiplicative()
        while self.peek().type in ("+", "-"):
            tok = self.next()
            right = self.multiplicative()
            left = A.Binary(tok.line, tok.type, left, right)
        return left

    def multiplicative(self):
        left = self.unary()
        while self.peek().type in ("*", "/", "%"):
            tok = self.next()
            right = self.unary()
            left = A.Binary(tok.line, tok.type, left, right)
        return left

    def unary(self):
        tok = self.peek()
        if tok.type == "-" or (tok.type == "KW" and
                               tok.value in ("why", "snip", "miss")):
            self.next()
            self._enter()          # prefix operators nest too: `- - - … 1`
            try:
                operand = self.unary()
            finally:
                self.nesting -= 1
            if tok.type == "-":
                return A.Unary(tok.line, "-", operand)
            if tok.value == "why":
                return A.Why(tok.line, operand)
            if tok.value == "snip":
                return A.Snip(tok.line, operand)
            return A.MissLit(tok.line, operand)
        return self.postfix()

    def postfix(self):
        expr = self.primary()
        while True:
            if self.at("("):
                tok = self.next()
                args = []
                if not self.at(")"):
                    while True:
                        args.append(self.expression())
                        if self.at(","):
                            self.next()
                            continue
                        break
                self.expect(")")
                expr = A.Call(tok.line, expr, args, False)
            elif self.at("["):
                tok = self.next()
                index = self.expression()
                self.expect("]")
                expr = A.Index(tok.line, expr, index)
            elif self.at("."):
                tok = self.next()
                name = self.expect("NAME", what="field name after '.'").value
                expr = A.FieldAccess(tok.line, expr, name)
            else:
                return expr

    def primary(self):
        tok = self.peek()
        if tok.type == "NUMBER":
            self.next()
            return A.Num(tok.line, tok.value)
        if tok.type == "STRING":
            self.next()
            return A.Str(tok.line, tok.value)
        if tok.type == "KW" and tok.value in ("true", "false"):
            self.next()
            return A.BoolLit(tok.line, tok.value == "true")
        if tok.type == "NAME":
            self.next()
            return A.NameRef(tok.line, tok.value)
        if tok.type == "[":
            self.next()
            items = []
            if not self.at("]"):
                while True:
                    items.append(self.expression())
                    if self.at(","):
                        self.next()
                        continue
                    break
            self.expect("]")
            return A.ListLit(tok.line, items)
        if tok.type == "@{":
            self.next()
            pairs = []
            names = set()
            if not self.at("}"):
                while True:
                    key = self.expect("NAME", what="field name")
                    if key.value in names:
                        raise ParseError("duplicate field '%s'" % key.value,
                                         key.line, key.col)
                    names.add(key.value)
                    self.expect(":")
                    pairs.append((key.value, self.expression()))
                    if self.at(","):
                        self.next()
                        continue
                    break
            self.expect("}")
            return A.RecordLit(tok.line, pairs)
        if tok.type == "(":
            self.next()
            expr = self.expression()
            self.expect(")")
            return expr
        if tok.type == "KW" and tok.value == "if":
            return self.if_expr()
        if tok.type == "{":
            return self.block()
        if tok.type == "KW" and tok.value == "fn":
            self.next()
            params, types = self.param_list()
            body = self.block()
            self._apply_type_guards(body, params, types, None)
            mark_tails(body)
            return A.FnExpr(tok.line, params, body)
        raise ParseError("unexpected %r" % (tok.value,), tok.line, tok.col)

    def if_expr(self):
        tok = self.expect("KW", "if")
        cond = self.expression()
        then = self.block()
        self.skip_newlines()
        if not self.at("KW", "else"):
            bad = self.peek()
            raise ParseError("'if' requires 'else' (every expression has a value)",
                             bad.line, bad.col)
        self.next()
        if self.at("KW", "if"):
            self._enter()      # `else if` chains recurse outside expression()
            try:
                otherwise = self.if_expr()
            finally:
                self.nesting -= 1
        else:
            otherwise = self.block()
        return A.If(tok.line, cond, then, otherwise)


def mark_tails(body):
    """Flag every call in tail position of a function body (v0.3).

    Tail positions: the final expression of the body block, and recursively
    the branches of an `if` / the final expression of a nested block found
    there. Nothing else — a call under `let`, `rescue`, an operator, an
    argument list, `why`/`snip` or a `check` needs its result back, so it
    is not a tail. Nested `fn` literals mark their own bodies when parsed.
    Iterative: bodies can nest `if … else if …` arbitrarily deep.
    """
    todo = [body]
    while todo:
        node = todo.pop()
        if isinstance(node, A.Block):
            todo.append(node.stmts[-1].expr)   # parser: last stmt is ExprStmt
        elif isinstance(node, A.If):
            todo.append(node.then)
            todo.append(node.otherwise)
        elif isinstance(node, A.Call):
            node.tail = True


def parse(src):
    return Parser(tokenize(src)).parse_program()
