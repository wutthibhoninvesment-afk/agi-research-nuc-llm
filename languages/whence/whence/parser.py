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
# "guess" (v0.15) joins the primitive set so a parameter/return contract
# can require an UNCOMMITTED value ("this must still carry a confidence
# score, call it yourself") the same way it can require a "num" or "str" —
# `_kind` in interp.py maps a `Guess` payload to this same string.
PRIMITIVE_TYPES = frozenset(
    ["num", "str", "bool", "list", "record", "fn", "guess", "any"])

# Effect system (v0.14): builtins whose call is a directly-observable side
# effect, mapped to the capability tag `effects [...]` names them by. Only
# `print` (writes to the host) exists today; a future effectful builtin
# (randomness, a clock, real I/O) slots in by adding one entry here — no
# other code needs to change. See `Parser._check_effect_call`.
_EFFECTFUL_BUILTINS = {"print": "io"}


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
        # Effect system (v0.14/v0.14.1): stack of the nearest enclosing fn's
        # RESOLVED `effects [...]` scope while parsing its body — a
        # frozenset (possibly empty, i.e. `effects []` = "no effects
        # allowed"), or None (unrestricted). "Resolved" means a fn with its
        # own clause pushes exactly that; a fn with NO clause of its own
        # pushes the CURRENT top of this same stack (`_resolve_effects_
        # scope`), i.e. lexical inheritance, not always None. Empty stack
        # (module top level, outside any fn) still behaves exactly like a
        # None top: no program written before v0.14 existed changes
        # behavior, since inheritance only ever reads an already-pushed
        # frame.
        self.effects_stack = []
        # Effect system (v0.14.2, round 266): stack of dicts mirroring
        # lexical block nesting (one dict per `stmt_list` frame, innermost
        # last), name -> tag-or-None, tracking which in-scope names are
        # currently a direct alias of an effectful builtin. `None` means
        # "this name is bound to something else in this scope" (a plain
        # `let`, a nested `fn`, or a parameter) — recorded explicitly so a
        # local binding correctly SHADOWS an outer alias of the same name
        # instead of the lookup falling through to it. See
        # `_resolve_effectful_alias`.
        self.alias_scopes = []

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
        # v0.14.2: one alias-tracking frame per block scope, pushed/popped
        # around this same statement run so `let`s here can be looked up by
        # nested blocks (still on the stack while a nested block is being
        # parsed) but never leak to a SIBLING block once this one is done.
        self.alias_scopes.append({})
        try:
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
        finally:
            self.alias_scopes.pop()

    def statement(self):
        tok = self.peek()
        if tok.type == "KW" and tok.value == "let":
            self.next()
            name = self.expect("NAME").value
            self.expect("=")
            expr = self.expression()
            # v0.14.2: record whether `name` is now a direct alias of an
            # effectful builtin (or of an already-tracked alias) — `None`
            # if not, which still occupies the slot so this `let` correctly
            # shadows any outer alias of the same name (see
            # `_resolve_effectful_alias`).
            self.alias_scopes[-1][name] = (
                self._resolve_effectful_alias(expr.name)
                if expr.__class__ is A.NameRef else None)
            return A.Let(tok.line, name, expr)
        if tok.type == "KW" and tok.value == "fn" and self.peek(1).type == "NAME":
            self.next()
            name = self.expect("NAME").value
            # A named fn is never itself an alias, but it DOES shadow an
            # outer alias of the same name for the rest of this scope.
            self.alias_scopes[-1][name] = None
            params, types = self.param_list()
            effects_spec = self.parse_effects_clause()
            ret_type = self.parse_return_type()
            self.effects_stack.append(self._resolve_effects_scope(effects_spec))
            # Params live one scope out from the body block's own `let`s at
            # runtime (`Env(p.env, self)` for params vs. the body Block's own
            # child `inner` env, interp.py `eval_Block`) — mirror that here
            # so a param shadows an outer alias but is never itself treated
            # as one.
            self.alias_scopes.append(dict.fromkeys(params))
            try:
                body = self.block()
            finally:
                self.effects_stack.pop()
                self.alias_scopes.pop()
            self._apply_type_guards(body, params, types, name)
            mark_tails(body)
            return A.FnDef(tok.line, name, params, body, ret_type)
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

    def parse_return_type(self):
        """`-> Type` after a parameter list (v0.13), optional. Returns the
        same kind of spec-expression `_type_spec_expr` builds for a param
        (an `A.Str` for a primitive tag, an `A.NameRef` for a shape), or
        None — the interpreter resolves it to a runtime spec ONCE per
        Closure at creation time (`_closure_ret`), never touching the
        body's AST, so tail position is exactly as `mark_tails` already
        computes it (see `_apply_type_guards`'s docstring: THAT is param
        types' whole cost story; a return type has none of its own)."""
        if not self.at("->"):
            return None
        tok = self.next()
        name = self.parse_type()
        return self._type_spec_expr(name, tok.line)

    def parse_effects_clause(self):
        """`effects [name, ...]` after a parameter list, before an optional
        `-> Type` (v0.14, fixed order — a program that writes them the
        other way around gets an ordinary "expected '{'" ParseError, same
        as any other out-of-order clause in this parser). `effects` is a
        contextual keyword like `shape`: only "NAME('effects') [" triggers
        it, so a program that binds something called `effects` elsewhere
        (there is none in this corpus, checked) is unaffected. Returns a
        frozenset of declared effect names (empty for `effects []`, i.e.
        "this function's own body may not directly call an effectful
        builtin"), or None if the clause is absent — None means
        unrestricted, the default, so every program written before this
        feature existed keeps parsing identically."""
        if not (self.at("NAME") and self.peek().value == "effects" and
                self.peek(1).type == "["):
            return None
        self.next()   # 'effects'
        self.next()   # '['
        names = []
        if not self.at("]"):
            while True:
                tok = self.expect("NAME", what="effect name")
                names.append(tok.value)
                if self.at(","):
                    self.next()
                    continue
                break
        self.expect("]")
        return frozenset(names)

    def _resolve_effects_scope(self, own_spec):
        """v0.14.1 (round 264): a fn with NO clause of its own (`own_spec is
        None`) lexically inherits the nearest enclosing fn's OWN resolved
        scope, rather than defaulting to unrestricted — closing the
        "nested fn escapes outer purity" gap v0.14 shipped as a documented,
        deliberate limitation (see SPEC.md "v0.14.1"). A fn WITH its own
        clause (empty or not) always uses exactly that clause, ignoring the
        enclosing scope entirely — an explicit declaration is still the one
        settle point that fully determines a function's own contract, the
        same "explicit always wins" rule v0.13 return types use. Top-level
        fns (module scope, `effects_stack` empty) are unaffected either
        way: `own_spec is None` there resolves to `None` (unrestricted),
        exactly as before this round."""
        if own_spec is not None:
            return own_spec
        return self.effects_stack[-1] if self.effects_stack else None

    def _resolve_effectful_alias(self, name):
        """v0.14.2 (round 266): does `name`, AS CURRENTLY IN SCOPE, refer to
        an effectful builtin — either the builtin itself, or a name bound
        earlier (in a visible enclosing or the same scope) via `let alias =
        <effectful-name-or-alias>`? Returns the effect tag (e.g. `"io"`) or
        None.

        Scope frames are checked innermost-first and the FIRST frame that
        contains `name` at all wins, even if its value there is None (a
        plain `let`/`fn`/parameter shadowing an outer alias) — this is why
        `_EFFECTFUL_BUILTINS` is consulted LAST, not first: a local
        `let print = 5` (however unusual) correctly shadows the real
        builtin for the rest of its scope, exactly as it would for any
        other name. Only a hop through a literal `let x = <NameRef>`
        assignment is tracked (`_check_effect_call`'s docstring lists what
        this still doesn't see — passed as an argument, returned, or
        stored in a list/record); and only one written BEFORE the call
        site, textually, in a currently-open scope — this is a single
        left-to-right parse pass, not a fixed-point/whole-program
        analysis, the same order-dependence `_resolve_effects_scope`
        already has for nested-fn inheritance."""
        for scope in reversed(self.alias_scopes):
            if name in scope:
                return scope[name]
        return _EFFECTFUL_BUILTINS.get(name)

    def _check_effect_call(self, callee, tok):
        """Effect system (v0.14/v0.14.2): a direct call `name(...)` where
        `name` resolves (`_resolve_effectful_alias`) to an effectful
        builtin — either `name` IS that builtin, or `name` is a tracked
        alias of it — is checked against the nearest enclosing fn's
        `effects [...]` declaration (`self.effects_stack[-1]`) — resolved
        ENTIRELY at parse time, no AST node, no interpreter change, no
        runtime cost. This is a ParseError rather than a runtime `miss`
        (unlike a `: Type`/`-> Type` mismatch) because whether a function's
        OWN body directly names an effectful builtin is a static property
        of the source text, not something that depends on a runtime value —
        the same reasoning that makes rebinding and "block must end in an
        expression" parse errors rather than misses.

        Still deliberately SHALLOW, by design, not by oversight, even after
        v0.14.2's alias tracking: only a direct `let alias = <name-or-
        alias>` hop is followed. Passing a builtin as a FUNCTION ARGUMENT,
        returning it from a call, or storing it in a list/record field and
        calling it back out are all still invisible — those are genuine
        value-flow-through-data-structures questions, not "is this name a
        plain alias" ones. Calling into a DIFFERENT function that itself
        performs the effect is *also* still untouched by the caller's own
        declaration — only LEXICAL nesting and direct aliasing are tracked,
        not the dynamic call graph. A real call-graph-aware (transitive)
        effect system tracking effects through arbitrary data flow is
        future work, not this round's scope; see SPEC.md "v0.14"/"v0.14.1"/
        "v0.14.2" for the honest remaining limitations and examples.
        `self.effects_stack[-1]` is already the fn's fully RESOLVED scope by
        the time this runs — a nested fn with no clause of its own
        inherited its enclosing scope in `_resolve_effects_scope` at push
        time (v0.14.1, round 264), so this method itself needed no change
        to pick that up."""
        if callee.__class__ is not A.NameRef:
            return
        tag = self._resolve_effectful_alias(callee.name)
        if tag is None:
            return
        scope = self.effects_stack[-1] if self.effects_stack else None
        if scope is None or tag in scope:
            return
        declared = "effects [%s]" % ", ".join(sorted(scope)) if scope \
            else "effects [] (no effects declared)"
        raise ParseError(
            "'%s' requires effect '%s', not permitted by the enclosing "
            "function's '%s'" % (callee.name, tag, declared),
            tok.line, tok.col)

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
                self._check_effect_call(expr, tok)
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
            effects_spec = self.parse_effects_clause()
            ret_type = self.parse_return_type()
            self.effects_stack.append(self._resolve_effects_scope(effects_spec))
            self.alias_scopes.append(dict.fromkeys(params))
            try:
                body = self.block()
            finally:
                self.effects_stack.pop()
                self.alias_scopes.pop()
            self._apply_type_guards(body, params, types, None)
            mark_tails(body)
            return A.FnExpr(tok.line, params, body, ret_type)
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
