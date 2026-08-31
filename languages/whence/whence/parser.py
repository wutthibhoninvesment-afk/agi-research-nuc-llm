"""Recursive-descent parser for Whence.

Enforced at parse time (not runtime):
  - a block must end with an expression statement (expression-oriented, no null)
  - `if` must have `else`
  - a name may be bound (`let`/`fn`) only once per block; params must be unique
"""

from .lexer import tokenize
from . import ast_nodes as A
from .foreign import FOREIGN_NAMES, bound_anywhere


class ParseError(Exception):
    def __init__(self, message, line, col):
        super(ParseError, self).__init__(
            "%s at line %d, col %d" % (message, line, col))
        self.line = line
        self.col = col


# --- v0.22 (round 354): a parse error names the Whence spelling ------------
#
# Decision 32 says an error that can name the fix, names it. The builtin
# half of that lives in `interp.py` (`_order_hint`); this is the parser
# half, and it exists for the same reason and from the same evidence.
#
# The operator's v0.19 report had two halves. The second was "the parser
# requires explicit `{}` blocks for all if/else branches ... document this
# strictly and consider auto-fixing older scripts". Round 349 documented
# it. Round 354 measured the scripts: the ten Whence programs a separate
# system had left in `examples/` (all machine-written, none tracked by this
# program) fail to parse for SIX distinct reasons, of which the braces rule
# is TWO. Auto-fixing braces would have repaired a fifth of them and left
# the rest failing with errors that still named no cure. Every one of the
# six is the same mistake in different clothes — the author reached for a
# mainstream construct Whence deliberately does not have — so the answer is
# not to rewrite the programs but to make the error say what Whence writes
# instead.
#
# Unlike the interpreter half this needs NO guest mirror: host and guest
# parse errors are different mechanisms (an exception with line AND column
# vs a `miss` carrying a line only) and have never agreed on wording —
# `unexpected '=' at line 2, col 3` vs `unexpected token '=' at line 2`.
# `tests/test_v22.py::test_parse_error_wording_is_not_a_guest_contract`
# pins that as a deliberate, pre-existing difference rather than leaving a
# future round to discover it as a divergence.
_SYNTAX_HINTS = {
    # `x = 2`. An `=` is only ever legal directly after the NAME in a
    # `let`/`fn` header, so an `=` that reaches the primary fallback is
    # always an attempted assignment.
    "=": "Whence has no assignment; a name binds once "
         "\u2014 write `let name = value`",
    # `rescue { ... } catch ...`, the try/catch shape.
    "rescue": "`rescue` is infix: `risky rescue fallback`",
}

_BRACE_HINT = ("blocks are always braced: `if c { a } else { b }`, "
               "`fn f(x) { x }`")
_RECORD_HINT = "records are written `@{a: 1}`, not `{a: 1}`"
_JUXTAPOSE_HINT = ("two names in a row: Whence has no juxtaposition "
                   "\u2014 a call is `f(x)` and text must be quoted")
# v0.23 (round 356). Takes the offending token, already spelled by `_spell`.
_SEPARATOR_HINT = ("a line break is the only statement separator Whence has "
                   "\u2014 start `%s` on the next line")

# v0.23 (round 356): the tokens a STATEMENT can begin with. Read off the
# three dispatch sites that decide it and nowhere else --- `statement()`
# (`let`, `fn`, `check`, and the `shape` head, which is a NAME),
# `not_expr`/`unary` (`not`, `-`, `why`, `snip`, `miss`) and `primary`
# (NUMBER, STRING, NAME, `true`/`false`, `[`, `@{`, `(`, `{`, `if`, `fn`).
#
# The missing-separator error is raised ONLY for these. Every other token
# is not a second statement that needed a newline in front of it, it is a
# token that can never start a statement at all --- `x = 2` is an attempted
# assignment, not two statements, and `_SYNTAX_HINTS` has said the useful
# thing about it since v0.22. Falling through to `statement()` there keeps
# the more specific diagnosis, which is the whole point of decision 32; a
# separator rule that shadowed it would have made v0.22's own regression
# test go quiet. `test_v23.py::test_every_token_is_classified_by_whether_it
# _can_start_a_statement` derives both sets from the parser itself rather
# than trusting this comment.
_STARTS_STATEMENT_TYPES = frozenset(
    ("NUMBER", "STRING", "NAME", "[", "@{", "(", "{", "-"))
_STARTS_STATEMENT_KWS = frozenset(
    ("let", "fn", "check", "if", "true", "false", "why", "snip", "miss",
     "not"))


def _starts_statement(tok):
    if tok.type == "KW":
        return tok.value in _STARTS_STATEMENT_KWS
    return tok.type in _STARTS_STATEMENT_TYPES

# `shape` is a SOFT keyword: the lexer emits NAME for it (only the 14 words
# in `lexer.KEYWORDS` are KW), so `shape Foo` is the one legal NAME NAME
# adjacency in the grammar and must not draw the juxtaposition hint.
# `effects`, the other soft keyword, is always followed by `[`.
_NAME_INTRODUCERS = ("shape",)


def _spell(tok):
    """How a token should be quoted back at the author inside a hint."""
    if tok.type == "STRING":
        return '"%s"' % tok.value
    return "%s" % (tok.value,)


def _show(tok):
    """How a token is NAMED in the body of an error message.

    v0.24 (round 360). Two sites rendered the offending token with `%r`
    straight off `tok.value`, and the EOF token's value is Python `None` --
    an object of the implementation, not anything the author wrote. So
    `let x = (` reported `unexpected None at line 1, col 10` and
    `let x = (1` reported `expected ), got None`. Everything else is
    unchanged: `%r` of a string still quotes it (`got '='`), of a number
    still does not (`got 1`).

    This is NOT `_spell`, and the two must not be merged. `_spell` quotes a
    token back at the author INSIDE A HINT, where a string literal is shown
    with its own double quotes because the hint is telling them how to
    write it; `_show` names the token that stopped the parse. `_spell` has
    no EOF case because a hint is never about end of input -- v0.22's five
    hints all fire on a token the author typed.
    """
    if tok.type == "EOF":
        return "end of input"
    return repr(tok.value)


def _with_hint(message, hint):
    return message if hint is None else "%s (%s)" % (message, hint)


COMPARE_OPS = ("==", "!=", "<", "<=", ">", ">=")

# Recursive descent costs ~11 host frames per nesting level (60 levels ≈
# 660 frames, safe under CPython's default 1000 even inside a test runner);
# past this many nested expressions the parser reports an error instead of
# crashing with RecursionError (fuzz, round 9). Left-associative chains (`1 + 1 +
# …`) loop and are not nesting.
MAX_NESTING = 60

# Structural types (v0.12): the primitive tags a `: Type` annotation may
# name besides a previously declared `shape`. Resolved at parse time to a
# spec EXPRESSION (`_type_spec_expr`) carried on the FnDef/FnExpr node —
# `param_types` for parameters (v0.19, `_param_contracts`), `ret_type` for
# a `-> Type` — so the interpreter never sees a "type", only an `A.Str`
# tag or an `A.NameRef` to a shape binding, resolved once per closure.
# v0.12-v0.18 erased a PARAMETER annotation further, into a prepended
# `typed(...)` guard statement; SPEC decision 29 explains why it no
# longer is.
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
        # v0.33 (round 386), decision 42: names this file BINDS, so a
        # foreign-word clause is never printed about a name the program
        # defines. One whole-file token scan, done once here rather than
        # per error, because it is the same answer every time and an error
        # path is not where a linear scan belongs. See `whence/foreign.py`
        # for why it is a token scan (the file does not parse --- that is
        # the situation) and why it errs toward suppression.
        self._bound_names = bound_anywhere(tokens)
        # v0.18 (round 342): the type namespace is the VALUE namespace, so
        # it obeys the value namespace's scope rule. One frame per block,
        # pushed/popped by `stmt_list` alongside the alias stacks below —
        # frame 0 is the module. Each frame maps name -> [(field,
        # type_name), …] in declaration order; a shape may only reference
        # shapes declared earlier (single pass, no forward refs — the
        # field's spec value must already be bound at the point a later
        # shape's record literal reads it by name).
        #
        # Before v0.18 this was ONE flat file-global dict, which made
        # `parse_type` accept a name whose desugared `let` binding was not
        # lexically visible at the use site; the three ways that went wrong
        # at runtime instead of at the annotation are catalogued in SPEC.md
        # § v0.18.
        self.shape_scopes = []
        # every shape name whose declaration COMPLETED anywhere earlier in
        # the file, never popped. Diagnostics only: it is what separates
        # "unknown type 'L'" (never declared) from "type 'L' is not in
        # scope here" (declared, in a block that has closed). Nothing about
        # acceptance is decided here — `_shape_in_scope` decides that.
        self.shapes_seen = set()
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
        # v0.14.11 (round 306): a SEVENTH stack, same push/pop sites as the
        # first six (stmt_list's per-block frame, plus the params-frame
        # push at each of the two fn-definition sites) — closes HALF of
        # v0.14.9's own explicitly-named remaining gap, "a builtin flowing
        # into a param that is stored ... rather than called directly":
        # `fn apply(f) effects [io] { let g = f\n g(1) }` now counts as
        # `apply` calling its OWN param `f` directly, exactly as `f(1)`
        # itself already does, extended through any number of further
        # `let`-rename hops WITHIN THE SAME OPEN FN BODY (`let h = g` then
        # `h(1)` too). Each frame maps name -> either `None` (not a
        # rename of the currently-open fn's own param, or a fact
        # deliberately shadowed by THIS binding) or the ORIGINAL PARAM
        # NAME (a key of `current_fn_params_frame_stack[-1]`) it is
        # currently a pure rename of. Does NOT replace `_check_effect_
        # call`'s own existing identity check (the base case, `f(1)`
        # itself, is untouched) — only extends it via `_resolve_param_
        # alias`, consulted as a fallback exactly when that check finds no
        # direct match. Deliberately does NOT cross a fn-body boundary
        # (see `_resolve_param_alias`'s own boundary guard) — a rename
        # recorded in an ENCLOSING fn's own scope must never be
        # misattributed to a DIFFERENT, inner fn's own param-call fact,
        # even if a coincidental name collision would otherwise make the
        # naive innermost-first walk cross into it. The OTHER half of the
        # "stored" gap — a param RETURNED (directly, not necessarily
        # renamed first), so a caller ends up holding the alias instead of
        # `apply` calling it directly itself — was a value-flow-ACROSS-A-
        # RETURN-BOUNDARY question, a genuinely different mechanism from
        # this stack; v0.14.12 (round 308) closes the direct-bare-tail
        # slice of it via `return_param_scopes` below — see
        # `_check_effect_call`'s own docstring for the honest updated
        # scope statement.
        self.param_alias_scopes = []
        # v0.14.12 (round 308): an EIGHTH stack, same shape and push/pop
        # sites as `return_alias_scopes` (`stmt_list`'s per-block frame,
        # plus the params-frame push at each of the two fn-definition
        # sites) — closes the OTHER half of v0.14.9's own explicitly-named
        # "stored/returned" gap that v0.14.11 left fully open: a param
        # RETURNED directly by the callee's own body (not called inside
        # it at all), so the CALLER ends up holding the alias itself. `fn
        # apply(f) { f }` then `let g = apply(print)\n g(1)` is now
        # checked, exactly as `let g = print\n g(1)` already was — because
        # `apply`'s own body's TAIL is a bare `NameRef` to one of `apply`'s
        # own params (`_tail_return_param_name`, called from `stmt_list`
        # the same way `_resolve_effectful_alias` already is for
        # `tail_alias_tag`), so the `let` binding `g` can look up WHICH
        # argument `apply` was actually called with at THIS call site and
        # carry ITS effect fact forward onto `g` — an argument-dependent
        # return fact, unlike `return_alias_scopes`'s own fixed one.
        # Each frame maps a name to either `None` (not a tracked fn, or one
        # whose tail doesn't directly return one of its own params) or
        # `(params_tuple, tail_param_name)` — deliberately NOT the fn's own
        # effects scope (unlike `param_call_scopes`): `apply` itself never
        # CALLS the builtin, only hands it back untouched, so `apply`'s own
        # `effects [...]` clause is irrelevant to this check (the same
        # reasoning `get_printer() effects []` already established in
        # v0.14.3 — returning an effectful value is not itself performing
        # the effect). The actual check still happens where it always has:
        # at `g(1)`'s own call site, via `_check_effect_call`'s ordinary
        # `alias_scopes` lookup, once `g`'s tag is recorded there — this
        # stack only supplies the missing fact needed to compute that tag
        # in the first place. See `_resolve_return_param_fact`,
        # `_resolve_return_param_passthrough`. Deliberately still narrow,
        # same family discipline: only a bare-NameRef TAIL (no if/else
        # nesting, unlike `tail_alias_tag`'s own v0.14.5 widening) is
        # tracked, and only ONE hop of call (an argument flowing through a
        # SECOND function call before reaching the return is still
        # invisible) — see `_check_effect_call`'s own docstring for the
        # honest updated scope statement.
        self.return_param_scopes = []

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
            raise ParseError(
                _with_hint("expected %s, got %s" % (want, _show(tok)),
                           self._expect_hint(want, tok)),
                tok.line, tok.col)
        return self.next()

    def _foreign_hint(self, tok):
        """v0.33 (round 386), decision 42: the clause naming a foreign word.

        The most specific thing a parse error can say about `for d in xs` is
        not that two names are adjacent; it is that Whence has no loops.
        That sentence has existed since v0.32 --- in `interp.py`, reachable
        only from a RUNTIME unbound name, which a program that does not
        parse never reaches. This is the same table, read from the other
        side.

        Two candidate tokens, in this order:

        ONE candidate token, and which one depends on the shape:

          - when the offending token is a NAME directly after another NAME
            --- the juxtaposition adjacency `_expect_hint` and
            `_separator_hint` already test --- the candidate is the EARLIER
            one, and only the earlier one. `for d` stops the parse at `d`;
            `for` is the word that created the adjacency, and `catch Miss`
            is the same shape with both tokens in the table.
          - otherwise the candidate is the offending token itself.
            `... "HIGH_RISK" then` stops at `then`, whose predecessor is a
            STRING.

        Trying BOTH was this round's own bug, and the corpus caught it. An
        earlier draft tried `prev` and then `tok`, which made
        `safe_divide one_hundred, zero_point_zero` --- a paren-less call,
        round 354's tenth case --- report "Whence has no spelled-out
        numbers; write the literal `100`". True about the word, and it
        SHADOWED the juxtaposition hint, which is the one message that
        describes the actual parse mistake there. The rule that fixes it is
        the rule that was already implicit: a foreign word explains an
        error when it is what put the two names next to each other, not
        when it merely happens to be one of them. Round 386 measured 15 of
        45 corpus parse errors changed by this clause; before the fix one
        of the 15 was a regression.

        Silent for any name the file binds (`self._bound_names`) and for
        any name not in the table --- decision 32's standing rule that a
        cure is computed or absent, never guessed.
        """
        prev = self.tokens[self.pos - 1] if self.pos > 0 else None
        if (tok.type == "NAME" and prev is not None and prev.type == "NAME"
                and prev.value not in _NAME_INTRODUCERS):
            cands = [prev]
        elif tok.type == "NAME":
            cands = [tok]
        else:
            cands = []
        for cand in cands:
            if cand.value in self._bound_names:
                continue
            sentence = FOREIGN_NAMES.get(cand.value)
            if sentence is not None:
                return sentence
        return None

    def _expect_hint(self, want, tok):
        """v0.22: the clause `expect` appends, or None.

        Two rules, both exact rather than heuristic:
          - anything that wanted a `{` is the braced-block rule, which is
            the half of the operator's v0.19 report round 349 could only
            document;
          - a NAME that failed to match, sitting immediately after another
            NAME, is juxtaposition — an unquoted string (`[Hardware Unit]`,
            `print(Calculating total)`) or a paren-less call (`f x`). The
            adjacency itself is what identifies it, not the token that
            happened to be expected, which is why this is `)`-and-`]`-proof.
        """
        foreign = self._foreign_hint(tok)
        if foreign is not None:
            return foreign
        if want == "'{'":
            return _BRACE_HINT
        prev = self.tokens[self.pos - 1] if self.pos > 0 else None
        if (tok.type == "NAME" and prev is not None and prev.type == "NAME"
                and prev.value not in _NAME_INTRODUCERS):
            return _JUXTAPOSE_HINT
        return None

    def _separator_hint(self, tok):
        """v0.23: the clause the missing-separator error appends. Never None.

        `statement()`'s own comment says "no other legal statement starts
        with two bare names in a row" -- that sentence was only true of the
        SHAPE head until v0.23, because two statements could sit on one line
        and make any `NAME NAME` pair legal by splitting it. Now that the
        pair really is illegal except at a shape head, this site inherits
        `_expect_hint`'s juxtaposition rule verbatim: a NAME immediately
        after a NAME is a paren-less call or an unquoted string, and saying
        "put it on the next line" would be advice for a mistake the author
        did not make.

        The shape head is excluded by the same three-token test `statement()`
        uses, not by `_NAME_INTRODUCERS` alone: here `tok` is the START of
        the offending statement, so `shape P = @{...}` after another
        statement on the same line is a real separator error whose cure IS
        the newline, and only `prev` (the previous statement's last token)
        is a `shape` that could have introduced a name.
        """
        prev = self.tokens[self.pos - 1] if self.pos > 0 else None
        shape_head = (tok.type == "NAME" and tok.value == "shape"
                      and self.peek(1).type == "NAME"
                      and self.peek(2).type == "=")
        if not shape_head:
            # v0.33: `for d in xs` and `return AUTHORIZED` both arrive here,
            # and both have a table entry saying something truer than
            # "two names in a row". A shape head is excluded for the reason
            # the juxtaposition test excludes it: it is the one legal
            # NAME NAME adjacency in the grammar.
            foreign = self._foreign_hint(tok)
            if foreign is not None:
                return foreign
        if (tok.type == "NAME" and not shape_head
                and prev is not None and prev.type == "NAME"
                and prev.value not in _NAME_INTRODUCERS):
            return _JUXTAPOSE_HINT
        return _SEPARATOR_HINT % _spell(tok)

    def skip_newlines(self):
        """Consume any run of NEWLINEs; return True if there was at least one.

        The return value is v0.23's (round 356). `stmt_list` needs to know
        whether a separator was actually PRESENT between two statements, not
        merely that it has arrived at the next one \u2014 those were the same
        question for as long as the separator was optional. Every other
        caller ignores the value, unchanged.
        """
        seen = False
        while self.at("NEWLINE"):
            self.next()
            seen = True
        return seen

    # --- statements ----------------------------------------------------
    def parse_program(self):
        stmts, _, _ = self.stmt_list(end="EOF")
        tok = self.expect("EOF")
        return A.Program(1, stmts)

    def stmt_list(self, end):
        """Parse statements until `end` token type; check duplicate bindings.
        Returns `(stmts, tail_alias_tag, tail_param_name)` — the second value
        (v0.14.3, round 270) is the effect tag (or None) the LAST statement
        resolves to via `_resolve_effectful_alias`, if that statement is a
        bare `NameRef` expression, resolved while THIS block's own
        `alias_scopes` frame is still on the stack (i.e. sees this block's
        own `let`s, not just outer ones). The third value (v0.14.12, round
        308) is, for that SAME bare-NameRef tail, whether it names one of
        the currently-open fn's own params (directly or via a same-body
        rename chain — `_tail_return_param_name`) — `None` for every other
        tail shape, including an `if`/`else` tail (unlike `tail_alias_tag`,
        deliberately not widened to that shape this round).

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
        self.shape_scopes.append({})
        self.alias_scopes.append({})
        self.return_alias_scopes.append({})
        self.field_alias_scopes.append({})
        self.field_return_alias_scopes.append({})
        self.nested_field_alias_scopes.append({})
        self.param_call_scopes.append({})
        self.param_alias_scopes.append({})
        self.return_param_scopes.append({})
        try:
            separated = self.skip_newlines()
            started = False
            while not self.at(end):
                # v0.23 (round 356), decision 33: a line break is the only
                # statement separator Whence has, and it is REQUIRED between
                # two statements. Only between them -- nothing is required
                # before the first statement or after the last, which is why
                # the `at(end)` test above is what closes the block and this
                # check sits inside the loop rather than after `statement()`.
                if started and not separated and _starts_statement(self.peek()):
                    tok = self.peek()
                    raise ParseError(
                        _with_hint("two statements on one line",
                                   self._separator_hint(tok)),
                        tok.line, tok.col)
                # v0.24 (round 360): the token the statement STARTS at,
                # captured before parsing it, is what the no-rebinding
                # error points at. It used to pass a literal `0` for the
                # column -- every other column in this file is 1-based, and
                # `col 0` is not a position in any source file. The LINE is
                # unchanged (a `let`/`fn` node's `line` is its head token's
                # line), which `test_v24.py` pins so this stays a column fix
                # and not a quiet relocation of the whole message.
                start = self.peek()
                s = self.statement()
                name = getattr(s, "name", None) if isinstance(s, (A.Let, A.FnDef)) else None
                if name is not None:
                    if name in bound:
                        raise ParseError(
                            "'%s' is already bound in this block (line %d); "
                            "Whence has no rebinding" % (name, bound[name]),
                            start.line, start.col)
                    bound[name] = s.line
                stmts.append(s)
                started = True
                separated = self.skip_newlines()
            tail = stmts[-1] if stmts else None
            tail_expr = tail.expr if isinstance(tail, A.ExprStmt) else None
            if tail_expr is not None and tail_expr.__class__ is A.NameRef:
                tail_tag = self._resolve_effectful_alias(tail_expr.name)
                tail_param = self._tail_return_param_name(tail_expr)
            elif tail_expr is not None and tail_expr.__class__ is A.If:
                tail_tag = self._if_tail_alias_tag(tail_expr)
                tail_param = None
            else:
                tail_tag = None
                tail_param = None
            return stmts, tail_tag, tail_param
        finally:
            self.shape_scopes.pop()
            self.alias_scopes.pop()
            self.return_alias_scopes.pop()
            self.field_alias_scopes.pop()
            self.field_return_alias_scopes.pop()
            self.nested_field_alias_scopes.pop()
            self.param_call_scopes.pop()
            self.param_alias_scopes.pop()
            self.return_param_scopes.pop()

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
                # v0.14.11 (round 306): does `expr.name`, right now, refer
                # to one of the CURRENTLY open fn's own params (directly,
                # or itself already a rename hop away) — if so, `name` is
                # now ALSO such a rename, one hop further; see
                # `_resolve_param_alias`'s own docstring for why the base
                # case (a literal param, not yet renamed) is resolved via
                # `_innermost_frame_containing` here rather than folded
                # into that method itself.
                if self.current_fn_params_frame_stack and \
                        self._innermost_frame_containing(expr.name) is \
                        self.current_fn_params_frame_stack[-1]:
                    self.param_alias_scopes[-1][name] = expr.name
                else:
                    self.param_alias_scopes[-1][name] = self._resolve_param_alias(expr.name)
                # v0.14.12 (round 308): a renamed fn's own "returns one of
                # its params" fact carries forward too, same reasoning as
                # every other fact above.
                self.return_param_scopes[-1][name] = self._resolve_return_param_fact(expr.name)
            elif expr.__class__ is A.Call and expr.fn.__class__ is A.NameRef:
                # v0.14.3 (round 270): `let p = get_printer()` — closes part
                # of v0.14.2's own "returning it from a call" gap. `p` is an
                # ordinary effectful-VALUE alias now (not itself a callable
                # fact) — whatever `get_printer` was tracked to return.
                tag = self._resolve_effectful_return(expr.fn.name)
                if tag is None:
                    # v0.14.12 (round 308): `get_printer`'s own FIXED return
                    # fact missed it (it never tail-returns a builtin
                    # itself) — but if `expr.fn.name` is tracked as a fn
                    # that hands back one of ITS OWN params directly (`fn
                    # apply(f) { f }`), the ARGUMENT actually passed at
                    # THIS call site (`expr.args`) may itself carry an
                    # effect fact — argument-dependent, unlike every other
                    # fact this branch already forwards.
                    tag = self._resolve_return_param_passthrough(expr.fn.name, expr.args)
                self.alias_scopes[-1][name] = tag
                self.return_alias_scopes[-1][name] = None
                self.field_alias_scopes[-1][name] = None
                self.field_return_alias_scopes[-1][name] = None
                self.nested_field_alias_scopes[-1][name] = None
                # v0.14.9: `p` is a plain VALUE (whatever the call returned),
                # not itself a named fn with its own param-call facts.
                self.param_call_scopes[-1][name] = None
                # v0.14.11: a call's RESULT is never itself a pure rename of
                # one of the currently-open fn's own params.
                self.param_alias_scopes[-1][name] = None
                # v0.14.12: nor is it itself a fn with its own "returns a
                # param" fact — `p` is a VALUE, not a callable.
                self.return_param_scopes[-1][name] = None
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
                # v0.14.10 (round 302): `primary()`'s `fn(...) {...}` branch
                # has no NAME to record a per-param-call fact under while
                # the anonymous fn's own body is being parsed, so it carries
                # the fact forward on the node itself (`expr.param_call_
                # fact`, set right before `A.FnExpr` is constructed) — NOW,
                # the moment this `let` learns `name`, is the first point
                # anywhere to key `param_call_scopes` by it. Exactly the
                # v0.14.9 NAMED-fn slice's own fact shape, just sourced from
                # the node instead of a scope-stack lookup.
                self.param_call_scopes[-1][name] = expr.param_call_fact
                # v0.14.11: a freshly-defined (anonymous or not) fn is never
                # itself a rename of one of the currently-open fn's params.
                self.param_alias_scopes[-1][name] = None
                # v0.14.12 (round 308): same node-carried-fact shape as
                # `param_call_fact` just above, sourced from `expr.body.
                # tail_param_name` (set by `block()`/`stmt_list` while the
                # anonymous fn's own params frame was still open) instead of
                # a scope-stack lookup — an anonymous fn has no name to key
                # `return_param_scopes` by until this exact `let` gives it
                # one, mirroring `tail_alias_tag`'s own `return_alias_
                # scopes[-1][name] = expr.body.tail_alias_tag` line above.
                self.return_param_scopes[-1][name] = (
                    (tuple(expr.params), expr.body.tail_param_name)
                    if expr.body.tail_param_name else None)
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
                # v0.14.11: nor is it ever a rename of a param.
                self.param_alias_scopes[-1][name] = None
                # v0.14.12: nor does it ever hand back one of a fn's params.
                self.return_param_scopes[-1][name] = None
            else:
                self.alias_scopes[-1][name] = None
                self.return_alias_scopes[-1][name] = None
                self.field_alias_scopes[-1][name] = None
                self.field_return_alias_scopes[-1][name] = None
                self.nested_field_alias_scopes[-1][name] = None
                self.param_call_scopes[-1][name] = None
                self.param_alias_scopes[-1][name] = None
                self.return_param_scopes[-1][name] = None
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
            # v0.14.11: a fn's own NAME is never a rename of a param either.
            self.param_alias_scopes[-1][name] = None
            # v0.14.12: same placeholder discipline as `param_call_scopes` —
            # overwritten once the body is fully parsed, below.
            self.return_param_scopes[-1][name] = None
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
            self.param_alias_scopes.append({})
            self.return_param_scopes.append(dict.fromkeys(params))
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
                self.param_alias_scopes.pop()
                self.return_param_scopes.pop()
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
            # v0.14.12 (round 308): record whether `name`'s own body just
            # hands back one of ITS OWN params directly, same overwrite-the-
            # placeholder timing as `return_alias_scopes` just above — `body.
            # tail_param_name` was resolved by `stmt_list` while this fn's
            # own params frame was still open.
            self.return_param_scopes[-1][name] = (
                (tuple(params), body.tail_param_name)
                if body.tail_param_name else None)
            param_types = self._param_contracts(body, params, types, name)
            mark_tails(body)
            return A.FnDef(tok.line, name, params, body, ret_type,
                           param_types)
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
        computes it. Since v0.19 a PARAMETER spec is resolved at the same
        moment by the same code (`_param_contracts` / `_closure_params`),
        so the two halves of a contract no longer differ in cost, timing,
        or the environment they name their shape in."""
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

    def _resolve_return_param_fact(self, name):
        """v0.14.12 (round 308): does `name`, AS CURRENTLY IN SCOPE, refer to
        a fn whose body's own TAIL directly returns one of ITS OWN params
        (see `_tail_return_param_name`)? Mirror of `_resolve_effectful_
        return`, over `return_param_scopes` instead of `return_alias_scopes`:
        same innermost-first, first-frame-wins walk. Returns `None` (nothing
        to check) or `(params_tuple, tail_param_name)` — the fn's own full
        param list (needed to find which ARGUMENT position at a call site
        corresponds to `tail_param_name`) and the specific param name its
        body hands back unchanged. See `_resolve_return_param_passthrough`,
        which combines this fact with an actual call's arguments."""
        for scope in reversed(self.return_param_scopes):
            if name in scope:
                return scope[name]
        return None

    def _resolve_return_param_passthrough(self, fn_name, args):
        """v0.14.12 (round 308): if `fn_name` is a tracked "returns one of
        its own params directly" fn (`_resolve_return_param_fact`), and the
        ARGUMENT at that param's own position in `args` is itself a bare
        `NameRef` resolving to an effectful alias, return that alias's tag —
        the effect fact CALLING `fn_name(args...)` actually yields, argument-
        dependent unlike every fact `_resolve_effectful_return` itself
        tracks. `None` whenever any link in that chain is missing: `fn_name`
        isn't tracked, `args` is too short for the returned param's own
        position (a parse-time arity mismatch is a separate, later runtime
        `miss` — this resolver never raises over it), or the matching
        argument isn't a bare-NameRef effectful alias. Shared by both call
        sites that need it: a `let`-bound call result (`statement()`'s own
        `A.Call` branch) and an immediately chained call (`_check_effect_
        call`'s own `A.Call` callee branch, e.g. `apply(print)(1)` with no
        intermediate `let` at all)."""
        fact = self._resolve_return_param_fact(fn_name)
        if fact is None:
            return None
        params_tuple, tail_param_name = fact
        try:
            idx = params_tuple.index(tail_param_name)
        except ValueError:
            return None
        if idx >= len(args):
            return None
        arg = args[idx]
        if arg.__class__ is not A.NameRef:
            return None
        return self._resolve_effectful_alias(arg.name)

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
        expression's own callee, never its arguments) to check there.
        v0.14.11 (round 306) closes HALF of one further gap: a param
        `let`-renamed inside the SAME fn body (`let g = f\n g(1)`, any
        number of further rename hops) is now recognized as still calling
        `f` directly, via `_resolve_param_alias`. v0.14.12 (round 308)
        closes the OTHER half: a param RETURNED directly by the callee's
        own body (`fn apply(f) { f }`), so the CALLER ends up holding the
        alias itself (`let g = apply(print)\n g(1)`), is now ALSO tracked
        — a genuinely separate, argument-DEPENDENT mechanism
        (`Parser.return_param_scopes`, `_resolve_return_param_passthrough`)
        from every fact this method's own dispatch below inspects: whether
        `g(1)` is checkable depends on WHICH argument `apply` was actually
        called with (`print` here), not just on `apply`'s own body, so the
        fact-computation happens at the CALL SITE (the `let`, or an
        immediately chained call handled right in the branch below), and
        by the time `g(1)` itself is reached, `g` is already an ordinary
        tracked alias — no new dispatch branch needed for the call being
        checked itself, only for producing `g`'s own fact. Still narrow:
        only a bare-NameRef tail (no `if`/`else`) is tracked, and an
        argument passed through a SECOND function call before reaching a
        RETURN is still invisible (`Parser.return_param_scopes`'s own
        remaining scope statement) — a genuinely separate shape from the
        one v0.14.13 (round 312) closes just below (`_check_param_
        forwarding`): an argument passed through a second function call
        before reaching a DIRECT CALL. Calling into a DIFFERENT,
        unrestricted top-level function that itself performs the effect —
        the dynamic call graph — remains the one gap this whole family has
        never started; see `_check_param_forwarding`'s own docstring and
        SPEC.md's "v0.14.13" section for why it is a fundamentally larger
        problem than every fact-composition slice that came before it.
        Only LEXICAL nesting and direct/return/field/argument/param-
        rename/return-param/forwarding aliasing are tracked, not the
        dynamic call graph. A real call-graph-aware (transitive) effect
        system tracking effects through arbitrary data flow remains future
        work; see SPEC.md "v0.14"/"v0.14.1"/"v0.14.2"/"v0.14.3"/"v0.14.4"/
        "v0.14.6"/"v0.14.7"/"v0.14.9"/"v0.14.11"/"v0.14.12"/"v0.14.13" for
        the honest remaining limitations and examples.
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
        # exact call target is one of ITS OWN params, called directly — or,
        # since v0.14.11, a `let`-renamed alias of one (any number of hops,
        # within this same fn body) — via the shared `_resolve_current_fn_
        # param` helper (factored out in v0.14.13; see its own docstring
        # for the frame-identity boundary that keeps a nested shadow from
        # being misattributed).
        if callee.__class__ is A.NameRef:
            resolved_param = self._resolve_current_fn_param(callee.name)
            if resolved_param is not None:
                self.direct_param_calls_stack[-1].add(resolved_param)
        if callee.__class__ is A.NameRef:
            tag = self._resolve_effectful_alias(callee.name)
            display = callee.name
        elif callee.__class__ is A.Call and callee.fn.__class__ is A.NameRef:
            tag = self._resolve_effectful_return(callee.fn.name)
            if tag is None:
                # v0.14.12 (round 308): `apply(print)(1)` — no intermediate
                # `let` at all, so `apply`'s own FIXED return fact
                # (`_resolve_effectful_return`, always None here since
                # `apply` never tail-returns a builtin ITSELF, only one of
                # its own params) misses it; the argument-DEPENDENT
                # passthrough fact does not.
                tag = self._resolve_return_param_passthrough(
                    callee.fn.name, callee.args)
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

    def _resolve_param_alias(self, name):
        """v0.14.11 (round 306): does `name`, AS CURRENTLY IN SCOPE, refer
        — through one or more `let`-rename hops, all WITHIN THE SAME
        currently-open fn body — to one of that fn's own params? A
        companion to `_check_effect_call`'s own existing identity check
        (the base case, `f(1)` where `f` IS literally the param, is
        untouched and unaffected by this method); this only extends it to
        `let g = f` (then `g(1)`), and transitively `let h = g` (then
        `h(1)`), etc.

        Deliberately bounded to the CURRENTLY open fn's own params frame
        and everything pushed AFTER it — never the frames of an
        ENCLOSING fn. Without this boundary, a coincidental name
        collision could misattribute a call: e.g. `fn outer(p) { let g =
        p\n fn inner() { g(1) } }` must NOT count as `inner` calling some
        param of its own (`inner` takes none), even though `g` resolves,
        walking naively all the way out, to `outer`'s own `p` — `inner`'s
        own `current_fn_params_frame_stack[-1]` is a different (empty)
        frame than `outer`'s, and `g` was never rebound inside `inner`'s
        own body at all, so this must return `None` for `inner`, not leak
        `outer`'s unrelated fact into `inner`'s own `direct_param_calls_
        stack`. Found by locating `current_fn_params_frame_stack[-1]`'s
        own identity inside `alias_scopes` (pushed at the exact same
        index `param_alias_scopes`'s own matching frame was) and refusing
        to walk any frame BELOW that boundary."""
        if not self.current_fn_params_frame_stack:
            return None
        top_params_frame = self.current_fn_params_frame_stack[-1]
        boundary = None
        for i in range(len(self.alias_scopes) - 1, -1, -1):
            if self.alias_scopes[i] is top_params_frame:
                boundary = i
                break
        if boundary is None:
            return None
        for scope in reversed(self.param_alias_scopes[boundary:]):
            if name in scope:
                return scope[name]
        return None

    def _resolve_current_fn_param(self, name):
        """v0.14.13 (round 312): does `name`, AS CURRENTLY IN SCOPE, refer
        to one of the CURRENTLY open fn's own params — directly, or
        through a same-body rename chain (`_resolve_param_alias`)? Factored
        out of two call sites that had this exact "innermost-first frame-
        identity check, else fall back to `_resolve_param_alias`" shape
        duplicated: `_check_effect_call`'s own leading v0.14.9 block (a
        call's CALLEE) and `_tail_return_param_name` (v0.14.12, a block's
        TAIL expression). `_check_param_forwarding` (v0.14.13) is now a
        third caller, applied to a call's own ARGUMENTS. `None` at module
        top level (`current_fn_params_frame_stack` empty) and for any name
        not currently a param/rename of one — including a param of an
        ENCLOSING (not the innermost open) fn, the same boundary
        `_resolve_param_alias` itself already enforces, so a nested
        shadow is never misattributed."""
        if not self.current_fn_params_frame_stack:
            return None
        owning_frame = self._innermost_frame_containing(name)
        if owning_frame is self.current_fn_params_frame_stack[-1]:
            return name
        return self._resolve_param_alias(name)

    def _tail_return_param_name(self, tail_expr):
        """v0.14.12 (round 308): does this bare-`NameRef` TAIL expression
        name one of the CURRENTLY open fn's own params — directly, or
        through a same-body rename chain? Called from `stmt_list` exactly
        where `tail_alias_tag` itself is computed, while the relevant
        scopes are still open. Thin wrapper over `_resolve_current_fn_
        param` (factored out in v0.14.13) applied to a tail position's own
        name."""
        return self._resolve_current_fn_param(tail_expr.name)

    def _check_call_site_param_effects(self, callee, args, tok):
        """v0.14.9 (round 300): closes the NAMED-fn slice of the effect
        system's long-flagged "passing a builtin as a function ARGUMENT"
        gap (`test_v14.py`'s own module docstring, unchanged since v0.14;
        `research-state.md`'s language(C) track backlog, unchanged since
        round 270). v0.14.10 (round 302) extends the SAME mechanism to a
        `let`-bound anonymous fn too — see `A.FnExpr.param_call_fact` and
        the `A.FnExpr` branch in `statement()`'s own `let` handling; nothing
        in THIS method changed, since `_resolve_param_call_fact` already
        walks `param_call_scopes` generically, indifferent to whether the
        recorded fact came from a NAMED fn's own definition or a `let`.

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
          - Only a call whose callee is a bare NameRef to a name with a
            recorded param-call fact is checked — either a NAMED fn (`fn
            NAME(...) {...}`) or, as of v0.14.10, a `let NAME = fn(...)
            {...}`-bound anonymous fn. A fn used any OTHER way (called
            inline without ever being bound to a name, passed straight
            through as someone else's argument, stored in a container) has
            no name to key `param_call_scopes` by and is still invisible —
            not a new gap, the same "nothing to check without SOME name"
            boundary every resolver in this family already has.
          - Only an ARGUMENT that is itself a bare NameRef resolving via
            `_resolve_effectful_alias` is inspected — an argument that is
            itself a call, a field access, or any other expression shape
            is invisible here, same as every other resolver's own
            "bare-NameRef only" boundary.
          - A PARAMETER the callee's body calls DIRECTLY (`f(...)`), OR
            through a `let`-rename of it WITHIN THE SAME BODY (`let g =
            f\n g(1)`, any number of further hops — v0.14.11, round 306,
            `_resolve_param_alias`), is checked BY THIS METHOD — a
            parameter RETURNED (so a CALLER, not the fn's own body, ends
            up holding it) is still invisible HERE, but is no longer a
            total gap: `Parser.return_param_scopes`/`_resolve_return_
            param_passthrough` (v0.14.12, round 308) is a genuinely
            SEPARATE mechanism covering exactly that returned-param shape,
            checked at the point the caller's own alias is created (the
            `let`, or a chained call), not by this method. A parameter
            passed further along to ANOTHER function (not called, not
            renamed, not returned — just forwarded as someone else's own
            argument) remains fully invisible everywhere, the exact same
            "one hop [now: one hop OR a same-body rename chain, OR a
            direct return], no propagation ACROSS a call boundary"
            discipline v0.14.2's own docstring uses for `let alias =
            print`.
          - An argument that flows through a SECOND function call before
            landing in a directly-called param — `outer(f) { inner(f) }`
            where `inner(g) { g(1) }` — is now ALSO checked, but by a
            genuinely SEPARATE mechanism (`_check_param_forwarding`,
            v0.14.13, round 312), not by this method: it augments
            `outer`'s OWN `direct_param_calls_stack` while `outer`'s body
            is being parsed, so `outer`'s own `param_call_scopes` entry
            already reflects the forward by the time THIS method runs at
            `outer(print)`'s own call site — no changes needed here at
            all, same "one resolver produces the fact, this method just
            consumes it generically" shape as every fact source above.
            The one remaining gap — the dynamic call graph (calling a
            different, unrestricted top-level fn that itself performs the
            effect DIRECTLY, no param involved at all) — is still
            completely untouched; see `_check_param_forwarding`'s own
            docstring for why it needs a fundamentally different design,
            not just one more fact-composition slice like this family's
            other additions.
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

    def _check_param_forwarding(self, callee, args, tok):
        """v0.14.13 (round 312): closes the FIRST of the two remaining
        "value flow through a function argument" gaps named across four
        consecutive language(C) rounds (302, 306, 308, 311) as needing "a
        real design sketch" — an argument reaching an effectful builtin
        through a SECOND function call, e.g. `fn inner(g) effects [io] {
        g(1) }` then `fn outer(f) effects [io] { inner(f) }`: `outer`'s own
        body never calls `f` directly (or through a same-body rename/
        return — v0.14.9/11/12's own mechanisms), it FORWARDS `f` as
        `inner`'s own argument, and it is `inner`'s body, not `outer`'s,
        that actually calls it. `outer(print)` was invisible to every
        prior check.

        The design insight that makes this tractable WITHOUT a whole new
        fixed-point/interprocedural analysis: `Parser.param_call_scopes`
        already records, for EVERY named fn (or `let`-bound anonymous
        one), "which of my own params does my body call directly"
        (v0.14.9) — a fact fully resolved by the time that fn's OWN body
        finishes parsing, strictly BEFORE any caller of it can be parsed
        (single left-to-right pass, forward refs already invisible
        everywhere else in this family — see `_resolve_effectful_alias`'s
        own docstring). So when `outer`'s body itself calls `inner(f)`,
        checking whether `f` (or a same-body rename of it —
        `_resolve_current_fn_param` covers both) lands in one of `inner`'s
        own DIRECTLY-called param positions is enough: if it does, `outer`
        ITSELF now also counts as "calling `f` directly" for the purposes
        of `outer`'s OWN `param_call_scopes` entry — recorded into the
        exact same `direct_param_calls_stack[-1]` v0.14.9's leading block
        already populates. `_check_call_site_param_effects` at
        `outer(print)`'s own call site needs ZERO changes: it already
        walks `_resolve_param_call_fact("outer")` generically, indifferent
        to whether `f`'s membership in `outer`'s own `called_params` came
        from a direct call, a same-body rename, or (now) a one-level-
        removed forward.

        This composes to ARBITRARY depth for free, the same "record once,
        read at every later call site" discipline `param_call_scopes`
        already relies on for everything else: if `innermost(h) effects
        [io] { h(1) }`, `inner(g) effects [io] { innermost(g) }`,
        `outer(f) effects [io] { inner(f) }` are declared in that
        (bottom-up) textual order, `inner`'s own `param_call_scopes` entry
        already reflects the forward through `innermost` by the time
        `outer`'s body is parsed, so `outer`'s own forward-through-`inner`
        check transitively picks it up too — no explicit recursion is
        needed here, single-pass composition does it automatically.
        Declaration order still matters exactly as much as it already does
        everywhere else: a forward reference, or a genuinely (mutually)
        recursive chain, is invisible, unchanged in scope from every prior
        v0.14.x round.

        Deliberately still narrow, the same "one hop, bare NameRef only"
        discipline as every sibling check: only a call whose callee is a
        bare NameRef with a recorded `param_call_fact` is inspected (a fn
        used any other way has nothing to key off); only an ARGUMENT that
        is itself a bare NameRef (or a same-body rename chain of one) is
        checked (an argument that is itself a call, field access, or any
        other expression shape is invisible); a param that is FORWARDED
        then RETURNED (or renamed, or forwarded a second time) by the
        callee, not called, remains invisible — v0.14.12's `return_param_
        scopes` and this method are still two genuinely separate
        mechanisms, not unified (see `test_param_passed_through_a_second_
        function_before_return_is_still_not_checked`, unchanged by this
        round: that shape is a RETURN, not a direct call, so it is outside
        this method's own scope).

        The dynamic call graph gap named alongside this one since round
        270 (calling a different, unrestricted top-level fn that itself
        performs an effect DIRECTLY — no param, no argument, involved at
        all) is a fundamentally different, larger problem this method does
        NOT touch: see SPEC.md's "v0.14.13" section for why it needs a
        real interprocedural effect-propagation design, not a bounded
        fact-composition slice like this one, and remains this family's
        one deliberately-unstarted gap."""
        if callee.__class__ is not A.NameRef:
            return
        fact = self._resolve_param_call_fact(callee.name)
        if fact is None:
            return
        _effects_scope, params, called_params = fact
        for i, pname in enumerate(params):
            if i >= len(args) or pname not in called_params:
                continue
            arg = args[i]
            if arg.__class__ is not A.NameRef:
                continue
            resolved_param = self._resolve_current_fn_param(arg.name)
            if resolved_param is not None:
                self.direct_param_calls_stack[-1].add(resolved_param)

    def parse_type(self):
        """A type name in annotation position: a primitive tag, or a
        `shape` declared earlier AND still in scope here (single pass, no
        forward refs — see `self.shape_scopes`). v0.18 (round 342) added
        the "in scope" half: before it, any shape declared anywhere earlier
        in the FILE was accepted, including one whose block had closed, and
        the failure surfaced at run time as one of three different misses
        (or, for a nested shape's own field spec, as a silently
        miss-valued field) instead of here."""
        tok = self.peek()
        if tok.type == "KW" and tok.value == "fn":
            self.next()
            name = "fn"
        elif tok.type == "NAME":
            self.next()
            name = tok.value
        else:
            raise ParseError("expected a type name", tok.line, tok.col)
        if name not in PRIMITIVE_TYPES and not self._shape_in_scope(name):
            if name in self.shapes_seen:
                # declared, but its block has closed: the same sentence the
                # runtime used to produce for the `-> Shape` half of this
                # case (interp's `_UnboundRetType`), now said once, here,
                # for every annotation position.
                raise ParseError("type '%s' is not in scope here" % name,
                                 tok.line, tok.col)
            raise ParseError("unknown type '%s'" % name, tok.line, tok.col)
        return name

    def _shape_in_scope(self, name):
        """Is `name` a shape declared in this block or an enclosing one?
        Innermost-out, exactly like the value lookup the desugared `let`
        will do at runtime — that correspondence is the whole point (v0.18,
        decision 28)."""
        for frame in reversed(self.shape_scopes):
            if name in frame:
                return True
        return False

    def _type_spec_expr(self, type_name, line):
        """The AST expression a `typed`/`matches` call reads its spec
        from: a primitive tag is a string literal; a shape name is a
        NameRef to the record `shape` bound it to (so nested shapes are
        the SAME value, not a copy — real structural composition)."""
        if type_name in PRIMITIVE_TYPES:
            return A.Str(line, type_name)
        return A.NameRef(line, type_name)

    def _param_contracts(self, body, params, types, fn_name):
        """v0.19 (round 344): the parameter half of a function's type
        contract, as a value carried on the FnDef/FnExpr node — `None` when
        no parameter is annotated, else a tuple of
        `(index, param_name, spec_expr, label)`.

        v0.12-v0.18 instead PREPENDED one `let <param> = typed(<param>,
        <spec>, <label>)` statement per annotated parameter to the body, so
        the spec expression was re-evaluated in the CALL env on every call
        while a `-> Type` spec (v0.13) was resolved once, in the DEFINING
        env, at closure creation. One signature could therefore name two
        different shapes with one name (round 342 §7 pinned it). This
        returns the same information the guards carried, in the same shape
        `ret_type` already uses, so `interp._closure_params` can resolve it
        with the same `_closure_spec` at the same moment as `ret_type`
        (SPEC decision 29).

        `body` is still the argument (not just `body.line`) because the
        LINE an annotation's miss is reported at is unchanged from v0.12 —
        the body's opening line, not the call site's — and keeping the
        parameter makes that continuity explicit rather than incidental.
        An unannotated function returns `None` here and its body is
        byte-identical to v0.11's, exactly as before."""
        if not any(t is not None for t in types):
            return None
        suffix = " of %s" % fn_name if fn_name else ""
        line = body.line
        out = []
        for i, (pname, tname) in enumerate(zip(params, types)):
            if tname is None:
                continue
            out.append((i, pname, self._type_spec_expr(tname, line),
                        "parameter '%s'%s" % (pname, suffix)))
        return tuple(out)

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
        if self.shape_scopes and name in self.shape_scopes[-1]:
            # THIS block only (v0.18): a shape in an enclosing block is
            # shadowed, not redeclared, exactly as a `let` of the same name
            # would be. Redundant with `stmt_list`'s general no-rebinding
            # check (a shape reaches it as an ordinary `A.Let`) and kept
            # deliberately: it fires first, with the more specific message,
            # and that message is a host/guest wording witness — see
            # SPEC.md § v0.18.
            raise ParseError("shape '%s' is already declared in this block"
                             % name, name_tok.line, name_tok.col)
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
        # registered only now, after `expect("}")` — that is what makes
        # `shape Foo = @{x: Foo}` an "unknown type", and the guest's
        # token-stream reconstruction of this table depends on it
        # (decision 27, SPEC.md § round 338).
        self.shape_scopes[-1][name] = fields
        self.shapes_seen.add(name)
        return A.Let(tok.line, name, A.RecordLit(tok.line, pairs))

    def block(self):
        open_tok = self.expect("{", what="'{'")
        # v0.22: `{a: 1}` is a BLOCK whose first statement is the name `a`,
        # so without this the error lands on the `:` two tokens later and
        # says "unexpected ':'" — true, useless, and three characters away
        # from the actual mistake. A block statement can never begin
        # `NAME :` or `STRING :` (an annotation only appears inside a
        # parameter list; `check` takes a KEYWORD first), so these two
        # token pairs identify a record literal missing its `@`
        # unambiguously.
        k = 0
        while self.peek(k).type == "NEWLINE":
            k += 1
        nxt, after = self.peek(k), self.peek(k + 1)
        if nxt.type in ("NAME", "STRING") and after.type == ":":
            raise ParseError(_with_hint("unexpected ':'", _RECORD_HINT),
                             after.line, after.col)
        stmts, tail_tag, tail_param = self.stmt_list(end="}")
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
        return A.Block(open_tok.line, stmts, tail_tag, tail_param)

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
                self._check_param_forwarding(expr, args, tok)
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
            # v0.14.10 (round 302): resolved BEFORE pushing onto
            # `effects_stack` (not read back off it after popping), same
            # ordering the NAMED-fn branch above uses, so it survives the
            # `finally` below to be recorded on the returned `A.FnExpr`
            # node itself afterward.
            own_effects_scope = self._resolve_effects_scope(effects_spec)
            self.effects_stack.append(own_effects_scope)
            params_alias_frame = dict.fromkeys(params)
            self.alias_scopes.append(params_alias_frame)
            self.return_alias_scopes.append(dict.fromkeys(params))
            self.field_alias_scopes.append(dict.fromkeys(params))
            self.field_return_alias_scopes.append(dict.fromkeys(params))
            self.nested_field_alias_scopes.append(dict.fromkeys(params))
            self.param_call_scopes.append(dict.fromkeys(params))
            self.param_alias_scopes.append({})
            self.return_param_scopes.append(dict.fromkeys(params))
            # v0.14.9: pushed for shadowing/tracking consistency inside this
            # anonymous fn's own body (e.g. a NAMED fn declared inside it
            # gets a correctly fn-scoped `current_fn_params_frame_stack`
            # top).
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
                self.param_alias_scopes.pop()
                self.return_param_scopes.pop()
                self.current_fn_params_frame_stack.pop()
                called_params = self.direct_param_calls_stack.pop()
            param_types = self._param_contracts(body, params, types, None)
            mark_tails(body)
            # v0.14.10 (round 302): unlike the NAMED-fn branch above (which
            # has a name to key `param_call_scopes[-1]` by the moment its
            # body finishes), an anonymous fn has none yet — the fact is
            # carried on the NODE itself instead, mirroring how
            # `body.tail_alias_tag` already rides on `A.Block`. Whichever
            # statement ends up binding this `A.FnExpr` (only `let ... =
            # fn(...) {...}` does anything with it; an anonymous fn used any
            # other way, e.g. called immediately or passed inline, has
            # nowhere to attach a name-keyed fact to and the field is simply
            # never read) decides what to do with `param_call_fact`.
            param_call_fact = (
                (own_effects_scope, tuple(params), frozenset(called_params))
                if called_params else None)
            return A.FnExpr(tok.line, params, body, ret_type,
                            param_call_fact, param_types)
        raise ParseError(
            _with_hint("unexpected %s" % (_show(tok),),
                       _SYNTAX_HINTS.get(tok.value)
                       or self._foreign_hint(tok)), tok.line, tok.col)

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
