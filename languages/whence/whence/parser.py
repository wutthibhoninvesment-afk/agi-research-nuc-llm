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
# effect, mapped to the capability tag `effects [...]` names them by.
# `print` (writes to the host, tag "io") was the only entry through v0.14.7.
# v0.14.8 (round 294) added the second: `rand` (draws from the interpreter's
# own seeded stream, tag "random") — the exact slot-in this comment
# anticipated back at v0.14 ("a future effectful builtin ... slots in by
# adding one entry here — no other code needs to change"), confirmed true:
# `_check_effect_call` and every `_resolve_effectful_*` helper below were
# already generic over the tag, needing no change at all. See
# `Parser._check_effect_call`.
_EFFECTFUL_BUILTINS = {"print": "io", "rand": "random"}


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
        # Effect system (v0.14.3, round 270): a SECOND stack, the exact same
        # shape as `alias_scopes` (one frame per lexical block, pushed and
        # popped at the identical three call sites: `stmt_list` itself, and
        # both fn-parameter scopes), but tracking a different fact per name:
        # "does CALLING this name — a named `fn` statement, or a `let NAME =
        # fn(...) {...}` binding — yield a value that is itself an effectful
        # alias?" (the mirror image of `alias_scopes`, which tracks "IS this
        # name directly an effectful value"). Populated only from a fn's own
        # textual TAIL statement (`stmt_list`'s `tail_tag` return value,
        # resolved while that body's own frames are still open — see
        # `stmt_list`'s docstring). Kept as a genuinely separate stack rather
        # than folded into `alias_scopes`'s own dict values so the two,
        # already-tested v0.14.2 read/write sites don't need to change shape;
        # every push/pop of `alias_scopes` below has a `return_alias_scopes`
        # counterpart right next to it, on purpose, so the two can never
        # silently drift out of frame-for-frame sync. See
        # `_resolve_effectful_return`.
        self.return_alias_scopes = []
        # Effect system (v0.14.4, round 272): a THIRD stack, same shape and
        # push/pop sites as the other two, tracking a third fact per name:
        # "is this name bound to a record literal, and if so, which of ITS
        # fields are themselves effectful aliases?" (`let box = @{run:
        # print}` then `box.run(1)`). Each frame maps name -> either `None`
        # (not a record-literal binding, or one this pass doesn't track) or
        # a dict `{field: tag-or-None}` resolved once, at the `let`, from
        # each field VALUE that is itself a bare `NameRef` — the same "bare
        # name only, no recursion into deeper shapes" discipline v0.14.3
        # applied to a fn's tail statement. See `_resolve_effectful_field`.
        self.field_alias_scopes = []
        # Effect system (v0.14.6): a FOURTH stack, same shape and push/pop
        # sites as the other three, tracking a fourth fact per name: "is
        # this name bound to a record literal, and if so, which of ITS
        # fields are themselves CALLABLE facts (does calling that field
        # yield an effectful value)?" — the field-level mirror of
        # `return_alias_scopes`, built from the SAME bare-NameRef field
        # values `field_alias_scopes` already inspects, just resolved
        # through `_resolve_effectful_return` instead of
        # `_resolve_effectful_alias`. Closes the gap v0.14.4's own
        # docstring named but didn't touch: `let box = @{run: get_printer}`
        # then `box.run()(1)` — TWO applications, the first (`box.run()`)
        # invoking whatever `get_printer` was tracked to return — was
        # entirely unchecked before this, since `_check_effect_call` had no
        # branch for a `Call` whose own callee is a `FieldAccess`. See
        # `_resolve_effectful_field_return`.
        self.field_return_alias_scopes = []
        # Effect system (v0.14.7): a FIFTH stack, same shape and push/pop
        # sites as the other four, tracking a fifth fact per name: "is this
        # name bound to a record literal that itself has a field whose OWN
        # value is a NESTED record literal, and if so, which of THAT inner
        # literal's fields are themselves effectful aliases?" — one hop
        # deeper than `field_alias_scopes`, closing the specific slice of
        # v0.14.4's own documented gap ("a field whose value is itself a
        # ... nested-record[/shape] is invisible") for a literal directly
        # nested inside a literal. `let outer = @{box: @{run: print}}` then
        # `outer.box.run(1)` — a TWO-FIELD chain reaching all the way down
        # to a bare-NameRef effectful alias — is now checked exactly as
        # `box.run(1)` (v0.14.4) would be, for a `box` bound one level
        # further out. Each frame maps name -> either `None` (not tracked)
        # or a dict `{outer_field: {inner_field: tag-or-None}}`, built once,
        # at the outer `let`, only for a field whose value is ITSELF an
        # `A.RecordLit` (any other field shape — a bare NameRef, a call, a
        # number — is simply absent from this dict, the same "one hop, no
        # recursion" discipline every prior version in this family applies
        # to its own new shape; that field may of course still populate
        # `field_alias_scopes`/`field_return_alias_scopes` on its own merits
        # if it happens to be a bare NameRef instead). See
        # `_resolve_effectful_field_nested`.
        self.nested_field_alias_scopes = []
        # Effect system (v0.14.9, round 300): a SIXTH stack, same shape and
        # push/pop sites as the other five, tracking a sixth fact per name:
        # "is this name a NAMED fn that directly calls one or more of its
        # OWN parameters, and if so, which ones, under what `effects [...]`
        # scope?" Closes the NAMED-fn slice of the long-flagged "passing a
        # builtin as a function ARGUMENT" gap (SPEC.md v0.14/test_v14.py's
        # own docstring, unchanged since v0.14): `fn apply(f) effects [io]
        # { f(1) }` then `apply(print)` is now checked — not by tracking
        # what `f` IS inside `apply`'s own body (impossible in one pass;
        # `apply`'s body is parsed exactly once, independent of any call
        # site), but by recording, once, at `apply`'s OWN definition, WHICH
        # of its params are ever called directly (`f(...)`, a bare-NameRef
        # callee), then re-checking each matching ARGUMENT at every
        # subsequent CALL SITE of `apply` against `apply`'s own (already
        # fully resolved) effects scope. Each frame maps name -> either
        # `None` (not a tracked fn, or one that calls none of its own
        # params directly) or `(effects_scope, params_tuple,
        # frozenset_of_directly_called_param_names)`. See
        # `_check_call_site_param_effects`, `_resolve_param_call_fact`.
        self.param_call_scopes = []
        # v0.14.9: transient (NOT scope-shaped like the six stacks above)
        # bookkeeping used only WHILE a single named-fn or anonymous-fn
        # body is being parsed, to discover which of ITS OWN params are
        # called directly anywhere in that body (at any nesting depth —
        # `_check_effect_call` already runs for every `Call` node
        # regardless of depth, so no separate structural walk is needed).
        # `current_fn_params_frame_stack` holds the exact SAME dict object
        # just pushed onto `alias_scopes` for the innermost enclosing fn's
        # params (not a copy) so a call's callee can be identity-compared
        # against it — this is what makes shadowing correct: if a nested
        # block's own `let`/`fn`/param re-binds the same name, THAT frame
        # (a different dict object) is found first by the innermost-first
        # walk, so the call is correctly NOT attributed to the outer fn's
        # own parameter. `direct_param_calls_stack` holds one growing set
        # per currently-open fn body, the param names actually seen as a
        # direct call target. Both are pushed/popped at the same two sites
        # `effects_stack` itself is (named fn, anonymous `fn(...) {...}`)
        # — NOT at `stmt_list`'s per-block frame, since these track a
        # whole FN body's own accumulated fact, not a per-block one.
        self.current_fn_params_frame_stack = []
        self.direct_param_calls_stack = []

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
        stmts, _ = self.stmt_list(end="EOF")
        tok = self.expect("EOF")
        return A.Program(1, stmts)

    def stmt_list(self, end):
        """Parse statements until `end` token type; check duplicate bindings.
        Returns `(stmts, tail_alias_tag)` — the second value (v0.14.3, round
        270) is the effect tag (or None) the LAST statement resolves to via
        `_resolve_effectful_alias`, if that statement is a bare `NameRef`
        expression, resolved while THIS block's own `alias_scopes` frame is
        still on the stack (i.e. sees this block's own `let`s, not just
        outer ones).

        v0.14.5 (round 276): a tail that is itself an `if`/`else` is now
        ALSO inspected, via `_if_tail_alias_tag` — but only structurally,
        after the fact: `then`/`otherwise` are each already-fully-parsed
        `A.Block`s (or, for an `else if` chain, another already-parsed
        `A.If`) by the time this stmt_list's own tail is examined, and each
        such nested block already resolved its OWN `tail_alias_tag` while
        ITS OWN `alias_scopes` frame was open (this same method, called
        recursively by `block()` while parsing `then`/`otherwise`). So no
        scope context is needed here at all — unlike a bare-NameRef tail,
        which must be resolved through `_resolve_effectful_alias` while
        still inside this frame, an `if` tail only needs to compare
        ALREADY-RESOLVED child tags, exactly the "no scope context needed"
        shape `mark_tails`'s own boolean structural walk already has. Any
        other tail shape (a `Call`, etc.) still resolves to `None`,
        unchanged."""
        stmts = []
        bound = {}
        # v0.14.2/v0.14.3: one alias-tracking frame (each) per block scope,
        # pushed/popped around this same statement run so `let`s here can be
        # looked up by nested blocks (still on the stack while a nested block
        # is being parsed) but never leak to a SIBLING block once this one is
        # done. The two stacks are pushed/popped together, always — see
        # `self.return_alias_scopes`'s own comment in `__init__`.
        self.alias_scopes.append({})
        self.return_alias_scopes.append({})
        self.field_alias_scopes.append({})
        self.field_return_alias_scopes.append({})
        self.nested_field_alias_scopes.append({})
        self.param_call_scopes.append({})
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
            tail = stmts[-1] if stmts else None
            tail_expr = tail.expr if isinstance(tail, A.ExprStmt) else None
            if tail_expr is not None and tail_expr.__class__ is A.NameRef:
                tail_tag = self._resolve_effectful_alias(tail_expr.name)
            elif tail_expr is not None and tail_expr.__class__ is A.If:
                tail_tag = self._if_tail_alias_tag(tail_expr)
            else:
                tail_tag = None
            return stmts, tail_tag
        finally:
            self.alias_scopes.pop()
            self.return_alias_scopes.pop()
            self.field_alias_scopes.pop()
            self.field_return_alias_scopes.pop()
            self.nested_field_alias_scopes.pop()
            self.param_call_scopes.pop()

    def statement(self):
        tok = self.peek()
        if tok.type == "KW" and tok.value == "let":
            self.next()
            name = self.expect("NAME").value
            self.expect("=")
            expr = self.expression()
            # v0.14.2/v0.14.3: record whether `name` is now a direct alias
            # of an effectful builtin (`alias_scopes`) and/or a callable
            # whose CALL RESULT is one (`return_alias_scopes`) — `None` in
            # whichever slot doesn't apply still occupies it, so this `let`
            # correctly shadows any outer fact of the same name in EITHER
            # stack (see `_resolve_effectful_alias`/`_resolve_effectful_
            # return`).
            if expr.__class__ is A.NameRef:
                # Renaming (`let g = get_printer`, no call): `g` carries
                # BOTH of the source name's own facts forward — it is still
                # exactly the same value, just under a new name.
                self.alias_scopes[-1][name] = self._resolve_effectful_alias(expr.name)
                self.return_alias_scopes[-1][name] = self._resolve_effectful_return(expr.name)
                self.field_alias_scopes[-1][name] = None
                self.field_return_alias_scopes[-1][name] = None
                self.nested_field_alias_scopes[-1][name] = None
                # v0.14.9: a renamed NAMED fn carries its own param-call
                # fact forward too, same reasoning as the direct/return
                # facts above.
                self.param_call_scopes[-1][name] = self._resolve_param_call_fact(expr.name)
            elif expr.__class__ is A.Call and expr.fn.__class__ is A.NameRef:
                # v0.14.3 (round 270): `let p = get_printer()` — closes part
                # of v0.14.2's own "returning it from a call" gap. `p` is an
                # ordinary effectful-VALUE alias now (not itself a callable
                # fact) — whatever `get_printer` was tracked to return.
                self.alias_scopes[-1][name] = self._resolve_effectful_return(expr.fn.name)
                self.return_alias_scopes[-1][name] = None
                self.field_alias_scopes[-1][name] = None
                self.field_return_alias_scopes[-1][name] = None
                self.nested_field_alias_scopes[-1][name] = None
                # v0.14.9: `p` is a plain VALUE (whatever the call returned),
                # not itself a named fn with its own param-call facts.
                self.param_call_scopes[-1][name] = None
            elif expr.__class__ is A.FnExpr:
                # v0.14.3: `let g = fn() {...}` — `g` is a callable, not
                # itself an effectful value; its return fact comes straight
                # off the body `block()` already resolved (`tail_alias_tag`)
                # while that body's own frames were still open.
                self.alias_scopes[-1][name] = None
                self.return_alias_scopes[-1][name] = expr.body.tail_alias_tag
                self.field_alias_scopes[-1][name] = None
                self.field_return_alias_scopes[-1][name] = None
                self.nested_field_alias_scopes[-1][name] = None
                # v0.14.9: deliberately NOT tracked — an anonymous fn bound
                # by `let` has no NAME at the point its own params/body are
                # parsed (`primary()`'s `fn(...) {...}` branch), so there is
                # nowhere to record a per-param-call fact until AFTER this
                # `let` already knows `name` — closing this specific slice
                # would need a new `A.FnExpr` field to carry the fact
                # forward (the same way `body.tail_alias_tag` already rides
                # on `A.Block`), deliberately out of scope for this round;
                # see `_check_call_site_param_effects`'s own docstring.
                self.param_call_scopes[-1][name] = None
            elif expr.__class__ is A.RecordLit:
                # v0.14.4 (round 272): `let box = @{run: print, other: 5}`
                # — closes the CONTAINER-FIELD slice of v0.14.3's own still-
                # open "stored in a list/record field" gap. `box` itself is
                # not an effectful value or a callable, but a later
                # `box.FIELD(...)` call needs to resolve through here (see
                # `_check_effect_call`'s new `FieldAccess` branch). Only a
                # bare-`NameRef` field VALUE is inspected — a field whose
                # value is itself a call/alias-chain/nested-record is left
                # at `None`, the same narrow "one hop, no recursion into a
                # nested shape" discipline v0.14.3 used for a fn's tail.
                #
                # v0.14.6: a SECOND dict, from the exact same bare-NameRef
                # field values, resolved through `_resolve_effectful_return`
                # instead — "is this field itself a callable whose call
                # result is effectful?" (`let box = @{run: get_printer}`
                # then `box.run()(1)`, the field-access mirror of v0.14.3's
                # own `get_printer()(1)`). The two dicts are independent:
                # a field can be a direct alias, a return-carrier, both (if
                # the name is somehow tracked as both, though no builtin is),
                # or neither.
                self.alias_scopes[-1][name] = None
                self.return_alias_scopes[-1][name] = None
                self.field_alias_scopes[-1][name] = {
                    fname: self._resolve_effectful_alias(fexpr.name)
                    for fname, fexpr in expr.pairs
                    if fexpr.__class__ is A.NameRef
                }
                self.field_return_alias_scopes[-1][name] = {
                    fname: self._resolve_effectful_return(fexpr.name)
                    for fname, fexpr in expr.pairs
                    if fexpr.__class__ is A.NameRef
                }
                # v0.14.7: a THIRD dict, this time keyed only on fields
                # whose OWN value is ANOTHER record literal — `let outer =
                # @{box: @{run: print}}` — one hop deeper than
                # `field_alias_scopes` above, resolving that inner
                # literal's own bare-NameRef fields the exact same way a
                # top-level record literal's fields already are. A field
                # absent here (its value wasn't itself a record literal)
                # is simply not a key in this dict, `.get` falling through
                # to `None` in `_resolve_effectful_field_nested` the same
                # way every other resolver in this family already does.
                self.nested_field_alias_scopes[-1][name] = {
                    fname: {
                        inner_fname: self._resolve_effectful_alias(inner_fexpr.name)
                        for inner_fname, inner_fexpr in fexpr.pairs
                        if inner_fexpr.__class__ is A.NameRef
                    }
                    for fname, fexpr in expr.pairs
                    if fexpr.__class__ is A.RecordLit
                }
                # v0.14.9: a record literal is never itself a named fn.
                self.param_call_scopes[-1][name] = None
            else:
                self.alias_scopes[-1][name] = None
                self.return_alias_scopes[-1][name] = None
                self.field_alias_scopes[-1][name] = None
                self.field_return_alias_scopes[-1][name] = None
                self.nested_field_alias_scopes[-1][name] = None
                self.param_call_scopes[-1][name] = None
            return A.Let(tok.line, name, expr)
        if tok.type == "KW" and tok.value == "fn" and self.peek(1).type == "NAME":
            self.next()
            name = self.expect("NAME").value
            # A named fn is never itself an alias, but it DOES shadow an
            # outer alias of the same name for the rest of this scope.
            self.alias_scopes[-1][name] = None
            # v0.14.3: also stake a placeholder in the ENCLOSING return-fact
            # frame BEFORE parsing params/body — shadows an outer return-fact
            # of the same name (mirrors the `alias_scopes` line above) and
            # keeps a directly-recursive call inside this fn's OWN body from
            # ever seeing a stale outer fact under its own name. Overwritten
            # with the real, resolved tag once the body is fully parsed,
            # below — `None` here is never observable from outside this fn's
            # own body, since nothing can call it before its own statement
            # finishes parsing.
            self.return_alias_scopes[-1][name] = None
            # v0.14.4/v0.14.6/v0.14.7: a fn name is never a record-literal
            # binding either, in any of the three field dicts.
            self.field_alias_scopes[-1][name] = None
            self.field_return_alias_scopes[-1][name] = None
            self.nested_field_alias_scopes[-1][name] = None
            # v0.14.9: same placeholder discipline as the other five —
            # overwritten once the body is fully parsed, below.
            self.param_call_scopes[-1][name] = None
            params, types = self.param_list()
            effects_spec = self.parse_effects_clause()
            ret_type = self.parse_return_type()
            # v0.14.9: resolved BEFORE pushing onto `effects_stack` (not
            # read back off it after popping) so it survives the `finally`
            # below to be recorded under `name` afterward.
            own_effects_scope = self._resolve_effects_scope(effects_spec)
            self.effects_stack.append(own_effects_scope)
            # Params live one scope out from the body block's own `let`s at
            # runtime (`Env(p.env, self)` for params vs. the body Block's own
            # child `inner` env, interp.py `eval_Block`) — mirror that here
            # so a param shadows an outer alias but is never itself treated
            # as one.
            params_alias_frame = dict.fromkeys(params)
            self.alias_scopes.append(params_alias_frame)
            self.return_alias_scopes.append(dict.fromkeys(params))
            self.field_alias_scopes.append(dict.fromkeys(params))
            self.field_return_alias_scopes.append(dict.fromkeys(params))
            self.nested_field_alias_scopes.append(dict.fromkeys(params))
            self.param_call_scopes.append(dict.fromkeys(params))
            # v0.14.9: `params_alias_frame` is the SAME object just pushed
            # onto `alias_scopes` above (not a copy) — see
            # `current_fn_params_frame_stack`'s own `__init__` comment for
            # why identity matters here.
            self.current_fn_params_frame_stack.append(params_alias_frame)
            self.direct_param_calls_stack.append(set())
            try:
                body = self.block()
            finally:
                self.effects_stack.pop()
                self.alias_scopes.pop()
                self.return_alias_scopes.pop()
                self.field_alias_scopes.pop()
                self.field_return_alias_scopes.pop()
                self.nested_field_alias_scopes.pop()
                self.param_call_scopes.pop()
                self.current_fn_params_frame_stack.pop()
                called_params = self.direct_param_calls_stack.pop()
            # v0.14.3 (round 270): now that the body is fully parsed and
            # `body.tail_alias_tag` is resolved (computed by `block()`/
            # `stmt_list` while the body's own frames were still open),
            # record what CALLING `name()` yields — back in the frame this
            # fn's own NAME lives in (the enclosing scope, now that the
            # params frame is popped), overwriting the placeholder above.
            self.return_alias_scopes[-1][name] = body.tail_alias_tag
            # v0.14.9: record which of `name`'s own params (if any) its body
            # calls directly, alongside `name`'s own resolved effects scope
            # — `None` (not `(scope, params, frozenset())`) when the body
            # calls none of its params directly, the same "absent means
            # nothing to check" convention every sibling resolver uses.
            self.param_call_scopes[-1][name] = (
                (own_effects_scope, tuple(params), frozenset(called_params))
                if called_params else None)
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

    def _if_tail_alias_tag(self, if_node):
        """v0.14.5 (round 276): does an `if`/`else` USED AS A TAIL STATEMENT
        resolve to an effectful alias — because EVERY arm, all the way
        through any `else if` chain, resolves to the exact same tag?
        `if_node.then` is always an already-parsed `A.Block` (`block()`
        always returns one); `if_node.otherwise` is either another
        already-parsed `A.Block` (a plain `else { ... }`) or an already-
        parsed `A.If` (an `else if ...` chain — recursed into here, purely
        structurally, no scope needed since each arm's own `tail_alias_tag`
        was already resolved correctly by `stmt_list` while THAT arm's own
        `alias_scopes` frame was open). Requires an exact match, not just
        "not None" — `if c { print } else { 5 }` correctly resolves to
        `None` (5 is not effectful), same as `if c { print } else {
        get_logger() }` does when `get_logger` returns a DIFFERENT
        effect tag (or isn't tracked as returning one at all) — an
        approximate or majority match would be unsound (a caller in an
        `effects [io]` scope could then call a branch that actually
        performs an untracked, undeclared effect)."""
        then_tag = if_node.then.tail_alias_tag
        otherwise = if_node.otherwise
        else_tag = (self._if_tail_alias_tag(otherwise)
                    if otherwise.__class__ is A.If
                    else otherwise.tail_alias_tag)
        if then_tag is not None and then_tag == else_tag:
            return then_tag
        return None

    def _resolve_effectful_return(self, name):
        """v0.14.3 (round 270): does CALLING `name` — a `fn` statement's own
        name, or a `let`-bound anonymous fn — yield an effectful alias?
        Mirror of `_resolve_effectful_alias`, over `return_alias_scopes`
        instead of `alias_scopes`: same innermost-first, first-frame-wins
        walk. No `_EFFECTFUL_BUILTINS` fallback here — this fact only ever
        comes from a user-written fn body's own TAIL position (`stmt_list`'s
        `tail_tag`), never a builtin itself (a builtin isn't "called" to
        produce another builtin)."""
        for scope in reversed(self.return_alias_scopes):
            if name in scope:
                return scope[name]
        return None

    def _resolve_effectful_field(self, name, field):
        """v0.14.4 (round 272): does `name.field`, AS CURRENTLY IN SCOPE,
        resolve to an effectful builtin — because `name` was bound (`let
        name = @{..., field: <effectful-name-or-alias>, ...}`) to a record
        literal whose `field` value was a tracked bare-NameRef alias?
        Mirror of `_resolve_effectful_alias`/`_resolve_effectful_return`,
        over `field_alias_scopes`: same innermost-first, first-frame-wins
        walk on `name` itself; the field lookup within the winning frame's
        dict is a plain `.get` (missing field, or `name` not a tracked
        record binding at all, both fall out to `None` the same way)."""
        for scope in reversed(self.field_alias_scopes):
            if name in scope:
                fields = scope[name]
                return fields.get(field) if fields else None
        return None

    def _resolve_effectful_field_return(self, name, field):
        """v0.14.6: does CALLING `name.field` — `name.field()`, i.e. `field`
        holds a callable whose call result is an effectful alias — resolve
        to an effectful builtin? The field-access mirror of
        `_resolve_effectful_return`, exactly as `_resolve_effectful_field`
        mirrors `_resolve_effectful_alias`: same innermost-first,
        first-frame-wins walk on `name` over `field_return_alias_scopes`,
        then a plain `.get(field)` within the winning frame's dict."""
        for scope in reversed(self.field_return_alias_scopes):
            if name in scope:
                fields = scope[name]
                return fields.get(field) if fields else None
        return None

    def _resolve_effectful_field_nested(self, name, outer_field, inner_field):
        """v0.14.7: does `name.outer_field.inner_field`, AS CURRENTLY IN
        SCOPE, resolve to an effectful builtin — because `name` was bound
        to a record literal whose `outer_field` value was ITSELF a nested
        record literal, and THAT inner literal's `inner_field` value was a
        tracked bare-NameRef alias? One hop deeper than
        `_resolve_effectful_field`, over `nested_field_alias_scopes`: same
        innermost-first, first-frame-wins walk on `name`, then a `.get
        (outer_field)` into the winning frame's dict (missing, or `name`
        not tracked at all, both fall out to `None`), then a further `.get
        (inner_field)` on WHATEVER that returns — `.get` on `None` would
        raise, so the outer lookup result is guarded exactly the same way
        `_resolve_effectful_field`/`_resolve_effectful_field_return` guard
        their own single `.get`."""
        for scope in reversed(self.nested_field_alias_scopes):
            if name in scope:
                outer = scope[name]
                if not outer:
                    return None
                inner = outer.get(outer_field)
                return inner.get(inner_field) if inner else None
        return None

    def _check_effect_call(self, callee, tok):
        """Effect system (v0.14/v0.14.2/v0.14.3/v0.14.4): a direct call
        `name(...)` where `name` resolves (`_resolve_effectful_alias`) to an
        effectful builtin — either `name` IS that builtin, or `name` is a
        tracked alias of it — is checked against the nearest enclosing fn's
        `effects [...]` declaration (`self.effects_stack[-1]`). So is a
        CHAINED call `f()(...)` where `f`'s own tracked return fact
        (`_resolve_effectful_return`) says calling `f()` yields such a
        value — v0.14.3, round 270, e.g. `get_printer()(1)` where
        `get_printer`'s body tail-returns `print` (or a tracked alias of
        it). So, now, is a FIELD call `box.run(...)` where `box` was bound
        to a record literal whose `run` field is itself a tracked alias —
        v0.14.4, round 272, `_resolve_effectful_field`. All of this is
        resolved ENTIRELY at parse time, no AST node, no interpreter change,
        no runtime cost. This is a ParseError rather than a runtime `miss`
        (unlike a `: Type`/`-> Type` mismatch) because whether a function's
        OWN body directly names an effectful builtin is a static property of
        the source text, not something that depends on a runtime value —
        the same reasoning that makes rebinding and "block must end in an
        expression" parse errors rather than misses.

        Still deliberately SHALLOW, by design, not by oversight, even after
        v0.14.5's if/else-tail tracking: `_resolve_effectful_return` sees a
        fn body whose TAIL STATEMENT is a bare NameRef, or an `if`/`else`
        (any `else if` chain length) whose every arm agrees on the exact
        same tag (`stmt_list`'s docstring, `_if_tail_alias_tag`) — but nests
        no further than that one `if`: a tail that is itself a `Call`, or
        an `if` nested one level deeper INSIDE a non-tail statement, is
        still invisible, unlike `mark_tails`'s fuller structural walk (see
        `stmt_list`'s docstring). `_resolve_effectful_field` only ever sees
        a record LITERAL bound directly by a `let`, with a bare-NameRef
        field value — a record built any other way (returned from a call,
        merged, mutated, or one whose field value is itself a call/alias
        chain) is invisible. So, now, is a CHAINED field call
        `box.run()(...)` where `box.run` was tracked (`_resolve_effectful_
        field_return`) as itself a callable whose call result is such a
        value — v0.14.6, e.g. `box.run()(1)` where `box = @{run:
        get_printer}` and `get_printer`'s body tail-returns `print` — the
        field-access mirror of v0.14.3's own `get_printer()(1)`, closing
        the gap v0.14.4's own docstring named ("a field whose value is
        itself a call/alias chain is invisible") for the specific case
        where that field value is a bare-NameRef return-carrier rather than
        a direct alias. So, now, is a NESTED field call `outer.box.run(...)`
        where `outer` was bound to a record literal whose `box` field is
        ITSELF a nested record literal, and THAT literal's `run` field is a
        tracked bare-NameRef alias — v0.14.7, `_resolve_effectful_field_
        nested`, one hop deeper than v0.14.4's own single-field case, the
        same "field value is a record literal" shape v0.14.4's own docstring
        named as invisible ("a nested-record[/shape]") but did not touch.
        Passing a builtin as a FUNCTION ARGUMENT was, through v0.14.8,
        completely untouched — v0.14.9 (round 300) closes the NAMED-fn
        slice of it: `fn apply(f) effects [io] { f(1) }` then
        `apply(print)` is now checked, via a genuinely SEPARATE mechanism
        (`Parser.param_call_scopes`, `_check_call_site_param_effects`) run
        at each CALL SITE of `apply`, not inside this method — `apply`'s
        own body never learns what `f` actually is, so there is nothing
        for THIS method (which only ever inspects a single call
        expression's own callee, never its arguments) to check there. Two
        genuine value-flow-through-data-structures questions still remain
        completely open: an argument passed through a SECOND function
        before reaching an effectful builtin, and a builtin flowing into a
        param that is stored/returned rather than called directly.
        Calling into a DIFFERENT function that itself performs the effect
        is *also* still untouched by the caller's own declaration — only
        LEXICAL nesting and direct/return/field/argument aliasing are
        tracked, not the dynamic call graph. A real call-graph-aware
        (transitive) effect system tracking effects through arbitrary data
        flow is future work, not this round's scope; see SPEC.md "v0.14"/
        "v0.14.1"/"v0.14.2"/"v0.14.3"/"v0.14.4"/"v0.14.6"/"v0.14.7"/
        "v0.14.9" for the honest remaining limitations and examples.
        `self.effects_stack[-1]` is already the fn's fully RESOLVED scope by
        the time this runs — a nested fn with no clause of its own
        inherited its enclosing scope in `_resolve_effects_scope` at push
        time (v0.14.1, round 264), so this method itself needed no change
        to pick that up."""
        # v0.14.9 (round 300): unconditionally, regardless of `tag` below —
        # a param is never itself tracked as an effectful alias (its value
        # is unknown at parse time), so the ordinary branch below always
        # sees `tag is None` for one. Record, for the CURRENTLY innermost
        # enclosing fn (`current_fn_params_frame_stack[-1]`), that this
        # exact call target is one of ITS OWN params, called directly —
        # but ONLY if `callee.name` resolves (innermost-first, exactly the
        # way every other resolver in this family already walks) to THAT
        # SAME frame object, not a closer one: a nested block's own `let`/
        # `fn`/param of the same name correctly shadows the outer fn's own
        # parameter, so a call through it is correctly NOT attributed here
        # (`test_v14.py`'s existing shadowing tests for the other five
        # stacks all have this same shape).
        if callee.__class__ is A.NameRef and self.current_fn_params_frame_stack:
            owning_frame = self._innermost_frame_containing(callee.name)
            if owning_frame is self.current_fn_params_frame_stack[-1]:
                self.direct_param_calls_stack[-1].add(callee.name)
        if callee.__class__ is A.NameRef:
            tag = self._resolve_effectful_alias(callee.name)
            display = callee.name
        elif callee.__class__ is A.Call and callee.fn.__class__ is A.NameRef:
            tag = self._resolve_effectful_return(callee.fn.name)
            display = "%s()" % callee.fn.name
        elif callee.__class__ is A.FieldAccess and callee.obj.__class__ is A.NameRef:
            tag = self._resolve_effectful_field(callee.obj.name, callee.name)
            display = "%s.%s" % (callee.obj.name, callee.name)
        elif (callee.__class__ is A.Call and
              callee.fn.__class__ is A.FieldAccess and
              callee.fn.obj.__class__ is A.NameRef):
            tag = self._resolve_effectful_field_return(callee.fn.obj.name, callee.fn.name)
            display = "%s.%s()" % (callee.fn.obj.name, callee.fn.name)
        elif (callee.__class__ is A.FieldAccess and
              callee.obj.__class__ is A.FieldAccess and
              callee.obj.obj.__class__ is A.NameRef):
            # v0.14.7: a NESTED field call, `outer.box.run(...)` — the
            # callee's own `.obj` is itself a `FieldAccess`, not a bare
            # NameRef, one level of container nesting deeper than the
            # v0.14.4 branch just above.
            tag = self._resolve_effectful_field_nested(
                callee.obj.obj.name, callee.obj.name, callee.name)
            display = "%s.%s.%s" % (callee.obj.obj.name, callee.obj.name, callee.name)
        else:
            return
        if tag is None:
            return
        scope = self.effects_stack[-1] if self.effects_stack else None
        if scope is None or tag in scope:
            return
        declared = "effects [%s]" % ", ".join(sorted(scope)) if scope \
            else "effects [] (no effects declared)"
        raise ParseError(
            "'%s' requires effect '%s', not permitted by the enclosing "
            "function's '%s'" % (display, tag, declared),
            tok.line, tok.col)

    def _innermost_frame_containing(self, name):
        """v0.14.9: the exact frame OBJECT (not a copy) in `alias_scopes`
        that an innermost-first walk would resolve `name` through — the
        same walk `_resolve_effectful_alias` already does, except this
        returns the frame itself, for an identity comparison, rather than
        the tag stored in it. `None` if `name` isn't bound in any open
        scope at all (a genuinely free/undefined name, or one this parser
        hasn't reached the binding site of yet)."""
        for scope in reversed(self.alias_scopes):
            if name in scope:
                return scope
        return None

    def _resolve_param_call_fact(self, name):
        """v0.14.9: does `name`, AS CURRENTLY IN SCOPE, refer to a NAMED fn
        that directly calls one or more of its own params — and if so,
        under what effects scope, with what full param list, and which
        params specifically? Mirror of `_resolve_effectful_return`, over
        `param_call_scopes` instead of `return_alias_scopes`: same
        innermost-first, first-frame-wins walk. Returns `None` (nothing to
        check) or `(effects_scope, params_tuple, frozenset_of_called_
        param_names)`. See `_check_call_site_param_effects`."""
        for scope in reversed(self.param_call_scopes):
            if name in scope:
                return scope[name]
        return None

    def _check_call_site_param_effects(self, callee, args, tok):
        """v0.14.9 (round 300): closes the NAMED-fn slice of the effect
        system's long-flagged "passing a builtin as a function ARGUMENT"
        gap (`test_v14.py`'s own module docstring, unchanged since v0.14;
        `research-state.md`'s language(C) track backlog, unchanged since
        round 270).

        Why this needs a genuinely DIFFERENT mechanism from every other
        resolver in this family, not just one more stack: every other
        `_resolve_effectful_*` answers "does THIS NAME, resolved once at
        its OWN scope, carry an effect fact" — a property of the name
        alone, decidable the moment its binding site is parsed. Whether
        `apply(f) effects [io] { f(1) }` is SOUND to call as `apply(print)`
        depends on BOTH `apply`'s own body (parsed exactly once, long
        before any call site exists) AND the specific argument at THIS
        call site — `apply`'s body itself never learns `f`'s identity, so
        there is nothing to check there; the check can only happen HERE,
        at each call site, against whatever `apply`'s OWN definition
        already recorded about which of its params it calls directly
        (`Parser.param_call_scopes`, `_check_effect_call`'s own v0.14.9
        tracking).

        Deliberately narrow, the same "one hop, textually before, bare
        NameRef only" discipline the whole v0.14.x family already uses for
        every other shape:
          - Only a call whose callee is a bare NameRef to a NAMED fn (`fn
            NAME(...) {...}`) is checked — an anonymous `fn(...) {...}`
            bound by `let` is not (see the `A.FnExpr` branch in
            `statement()`'s own `let` handling for why: no name exists yet
            at the point its own param-call fact would need to be
            recorded under).
          - Only an ARGUMENT that is itself a bare NameRef resolving via
            `_resolve_effectful_alias` is inspected — an argument that is
            itself a call, a field access, or any other expression shape
            is invisible here, same as every other resolver's own
            "bare-NameRef only" boundary.
          - Only a PARAMETER the callee's body calls DIRECTLY (`f(...)`)
            is checked — a parameter merely stored, returned, or passed
            further along to ANOTHER function is invisible, the exact
            same "one hop, no further propagation" discipline v0.14.2's
            own docstring uses for `let alias = print`.
          - The two other remaining gaps — an argument that flows through
            a SECOND function call before reaching an effectful builtin,
            and the dynamic call graph (calling a different, unrestricted
            top-level fn that itself performs the effect) — are still
            completely untouched, unchanged in scope from every prior
            v0.14.x round's own assessment.
          - Forward-referenced or mutually-recursive fns are invisible the
            same way `_resolve_effectful_alias`'s own docstring says an
            alias defined AFTER its call site is: `param_call_scopes` only
            has an entry for a fn once its OWN `fn NAME(...) {...}`
            statement has been fully parsed, single left-to-right pass,
            no fixed-point/whole-program analysis.

        The check itself is against `apply`'s OWN resolved effects scope
        (recorded at `apply`'s definition, `own_effects_scope` above) —
        NOT the calling scope's `effects_stack[-1]` — because it is
        `apply`'s own body, not the caller's, that performs the effect
        (`f(1)`, i.e. `print(1)`, executes lexically inside `apply`, not
        at the call site). This is exactly the same "the declaration
        vouches for its own textual body" principle every sibling check in
        this family already uses; only the SOURCE of the effect fact
        (a call-site argument, not a body-local alias) differs."""
        if callee.__class__ is not A.NameRef:
            return
        fact = self._resolve_param_call_fact(callee.name)
        if fact is None:
            return
        effects_scope, params, called_params = fact
        for i, pname in enumerate(params):
            if i >= len(args) or pname not in called_params:
                continue
            arg = args[i]
            if arg.__class__ is not A.NameRef:
                continue
            tag = self._resolve_effectful_alias(arg.name)
            if tag is None:
                continue
            if effects_scope is None or tag in effects_scope:
                continue
            declared = "effects [%s]" % ", ".join(sorted(effects_scope)) if effects_scope \
                else "effects [] (no effects declared)"
            raise ParseError(
                "argument '%s' (effect '%s') passed to '%s' for parameter "
                "'%s', which '%s' calls directly, is not permitted by "
                "'%s''s own '%s'"
                % (arg.name, tag, callee.name, pname, callee.name,
                   callee.name, declared),
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
        stmts, tail_tag = self.stmt_list(end="}")
        close = self.expect("}")
        if not stmts:
            raise ParseError("block must contain at least one expression",
                             open_tok.line, open_tok.col)
        if not isinstance(stmts[-1], A.ExprStmt):
            raise ParseError("block must end with an expression",
                             close.line, close.col)
        # v0.14.3 (round 270): `tail_alias_tag` is a real `Block` field (see
        # ast_nodes.py), set directly at construction since — unlike `Call.
        # tail` (set later by `mark_tails`, a separate structural pass) —
        # `stmt_list` has already fully resolved it by the time we get here.
        # Consumed only by whichever fn-parsing code just called `block()`,
        # to learn what effect tag (if any) this body's own RETURN value
        # aliases.
        return A.Block(open_tok.line, stmts, tail_tag)

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
                self._check_call_site_param_effects(expr, args, tok)
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
            params_alias_frame = dict.fromkeys(params)
            self.alias_scopes.append(params_alias_frame)
            self.return_alias_scopes.append(dict.fromkeys(params))
            self.field_alias_scopes.append(dict.fromkeys(params))
            self.field_return_alias_scopes.append(dict.fromkeys(params))
            self.nested_field_alias_scopes.append(dict.fromkeys(params))
            self.param_call_scopes.append(dict.fromkeys(params))
            # v0.14.9: pushed for shadowing/tracking consistency inside this
            # anonymous fn's own body (e.g. a NAMED fn declared inside it
            # gets a correctly fn-scoped `current_fn_params_frame_stack`
            # top), but the popped `called_params` set below is discarded —
            # an anonymous `fn(...) {...}` bound by `let` has no name at
            # this point to record a param-call fact UNDER (see the
            # `A.FnExpr` branch in `statement()`'s own `let` handling).
            self.current_fn_params_frame_stack.append(params_alias_frame)
            self.direct_param_calls_stack.append(set())
            try:
                body = self.block()
            finally:
                self.effects_stack.pop()
                self.alias_scopes.pop()
                self.return_alias_scopes.pop()
                self.field_alias_scopes.pop()
                self.field_return_alias_scopes.pop()
                self.nested_field_alias_scopes.pop()
                self.param_call_scopes.pop()
                self.current_fn_params_frame_stack.pop()
                self.direct_param_calls_stack.pop()
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
