"""Targeted generator + independent ground-truth oracle for v0.14.2's
direct-alias effect tracking (`Parser.alias_scopes` /
`_resolve_effectful_alias`, round 266, landed round 267).

Round 257's own backlog (closing the guess-targeted campaign) named this
exact gap: `let alias = print` is not reachable from `harness/swe/fuzz.py`'s
general `ProgramGen` grammar (confirmed by grep there, not assumed — see
round 257's own knowledge file item 3, and this round's research-state.md
next-steps item 11), so the parse-time effect-alias check had zero fuzz
coverage beyond the ~14 hand-written cases in `tests/test_v14.py`.

Unlike `harness/swe/guest.py` (host vs. self-hosted-evaluator differential,
a RUNTIME question), this feature is entirely parse-time and static — there
is no guest/host split to exploit. The oracle here is a SECOND, independently
written implementation of the exact same spec (`Parser.alias_scopes`'s own
docstring and `SPEC.md`'s "v0.14.2" section): a scope-stack walk over a
small IR this module builds itself (not a call into `whence.parser`'s own
code), predicting whether `whence.parser.parse` should raise a ParseError
naming a specific alias/tag, or accept the program outright. A mismatch
between the two independent implementations is a candidate bug in either
(adjudicated by hand — see the campaign runner's own report).

Design constraint carried over from the spec text (`_resolve_effectful_
alias`'s docstring): this is a SINGLE left-to-right, order-dependent pass,
not a fixed-point analysis — the oracle below deliberately builds its
prediction incrementally, in the same left-to-right order it emits source
text, for exactly that reason (an alias `let` written after the call it
would cover must NOT be predicted as a violation, mirroring
`test_alias_defined_after_call_site_is_not_detected`).
"""
import os
import random
import sys

WHENCE_ROOT = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "languages", "whence"))

EFFECTFUL = {"print": "io"}
EFFECT_TAG_SETS = (None, frozenset(), frozenset(["io"]), frozenset(["net"]),
                   frozenset(["io", "net"]))
RESERVED = {"effects", "shape", "check", "let", "fn", "if", "else", "rescue",
            "true", "false", "and", "or", "not", "why", "snip"}


class AliasEffectsGen(object):
    """Generates (source, verdict) pairs. `verdict` is either `("ok",)` or
    `("error", name, tag)` — the first callee name/tag the independent
    oracle predicts will raise, or `("ok",)` if none will.

    One instance == one program. `self.done` latches True the moment the
    oracle predicts a violation; no further statement CHOICES are made
    after that (the real parser would already have raised), though open
    scopes already entered are still closed out so the emitted source stays
    syntactically well-formed up to (and past, harmlessly) that point.
    """

    def __init__(self, seed, max_depth=3, max_stmts=4):
        self.r = random.Random(seed)
        self.max_depth = max_depth
        self.max_stmts = max_stmts
        self.counter = 0
        self.done = False
        self.verdict = ("ok",)
        # mirrors Parser.alias_scopes: list of dict name -> tag-or-None
        self.alias_scopes = []
        # mirrors Parser.effects_stack: list of frozenset-or-None
        self.effects_stack = []

    def fresh(self, prefix="v"):
        self.counter += 1
        name = "%s%d" % (prefix, self.counter)
        assert name not in RESERVED
        return name

    def resolve_alias(self, name):
        for scope in reversed(self.alias_scopes):
            if name in scope:
                return scope[name]
        return EFFECTFUL.get(name)

    def known_alias_names(self):
        """Names currently visible (any frame) that resolve to a non-None
        tag — candidates for a chained `let q = <name>` or a call site."""
        out = []
        for scope in self.alias_scopes:
            for name, tag in scope.items():
                if tag is not None:
                    out.append(name)
        return out

    def any_visible_name(self):
        """Any bound name at all (alias or not) — candidates for a shadow
        test, which deliberately reuses a name regardless of its tag."""
        out = []
        for scope in self.alias_scopes:
            out.extend(scope.keys())
        return out

    def outer_visible_names(self):
        """`any_visible_name()` restricted to frames OTHER than the current
        innermost one, AND excluding any name that (from an EARLIER shadow
        statement already emitted in this same current frame) is now also
        a key there — safe targets to REBIND (a `let`/`fn` of the same
        name inside the CURRENT frame is Whence's "no rebinding" error, a
        real but effects-UNRELATED ParseError that would otherwise
        confound the comparison; reusing an OUTER frame's name for the
        FIRST time is a true shadow, not a rebind)."""
        current = self.alias_scopes[-1]
        seen = set()
        out = []
        for scope in self.alias_scopes[:-1]:
            for name in scope:
                if name not in current and name not in seen:
                    seen.add(name)
                    out.append(name)
        return out

    def outer_alias_names(self):
        return [n for n in self.outer_visible_names()
                if self.resolve_alias(n) is not None]

    def record_call(self, name):
        """Mirror `_check_effect_call`: a call `name(...)` is a violation
        iff `name` resolves to a tag not granted by the nearest enclosing
        (already-resolved) effects scope. Only the FIRST violation in
        program order matters — the real parser raises immediately."""
        if self.done:
            return
        tag = self.resolve_alias(name)
        if tag is None:
            return
        scope = self.effects_stack[-1] if self.effects_stack else None
        if scope is None or tag in scope:
            return
        self.done = True
        self.verdict = ("error", name, tag)

    def record_let(self, name, alias_of):
        """`alias_of` is the resolved tag if the RHS was a bare NameRef,
        else None. Occupies the slot regardless (shadow bookkeeping)."""
        self.alias_scopes[-1][name] = alias_of

    def resolve_effects_scope(self, own_spec):
        if own_spec is not None:
            return own_spec
        return self.effects_stack[-1] if self.effects_stack else None

    # -- generation ---------------------------------------------------
    def gen_program(self):
        lines = self.gen_stmt_list(depth=0, n=self.r.randint(2, self.max_stmts))
        lines = self._strip_marks(lines)
        return "\n".join(lines) + "\n", self.verdict

    def gen_stmt_list(self, depth, n, is_block_body=False):
        """One `stmt_list` frame: pushes/pops one alias_scopes dict, mirrors
        `Parser.stmt_list`. If `is_block_body`, the last emitted statement
        must be a bare expression (block-ending rule) — satisfied here by
        always finishing with a trivial call or literal."""
        self.alias_scopes.append({})
        try:
            lines = []
            budget = n
            while budget > 0:
                budget -= 1
                if self.done and self.r.random() < 0.7:
                    break
                lines.append(self.gen_one_stmt(depth))
            if is_block_body:
                if not lines or not self._is_expr_stmt(lines[-1]):
                    lines.append(self.gen_tail_expr())
            elif not lines:
                lines.append(self.gen_tail_expr())
            return lines
        finally:
            self.alias_scopes.pop()

    _EXPR_MARK = "\x00EXPR\x00"

    def _is_expr_stmt(self, line):
        return line.startswith(self._EXPR_MARK)

    def _mk_expr(self, text):
        return self._EXPR_MARK + text

    def _strip_marks(self, lines):
        return [l[len(self._EXPR_MARK):] if l.startswith(self._EXPR_MARK) else l
                for l in lines]

    def gen_tail_expr(self):
        r = self.r
        aliases = self.known_alias_names()
        if aliases and r.random() < 0.5:
            name = r.choice(aliases)
            self.record_call(name)
            return self._mk_expr("%s(0)" % name)
        if r.random() < 0.3:
            self.record_call("print")
            return self._mk_expr("print(0)")
        return self._mk_expr(str(r.randint(0, 9)))

    def gen_one_stmt(self, depth):
        r = self.r
        choices = ["let_builtin_alias", "let_plain", "call"]
        if self.known_alias_names():
            choices += ["let_alias_chain", "call_alias"]
        if self.outer_visible_names():
            choices += ["shadow_let"]
        if depth < self.max_depth:
            choices += ["nested_fn", "nested_block"]
            if self.outer_alias_names():
                choices += ["shadow_fn"]
            if self.known_alias_names():
                choices += ["shadow_param"]
        kind = r.choice(choices)
        return getattr(self, "_stmt_" + kind)(depth)

    def _stmt_let_builtin_alias(self, depth):
        name = self.fresh("a")
        self.record_let(name, EFFECTFUL.get("print"))
        return "let %s = print" % name

    def _stmt_let_alias_chain(self, depth):
        src = self.r.choice(self.known_alias_names())
        name = self.fresh("a")
        self.record_let(name, self.resolve_alias(src))
        return "let %s = %s" % (name, src)

    def _stmt_let_plain(self, depth):
        name = self.fresh("v")
        self.record_let(name, None)
        return "let %s = %d" % (name, self.r.randint(0, 9))

    def _stmt_shadow_let(self, depth):
        """Reuse an existing OUTER-frame name as a fresh binding in the
        CURRENT (innermost) frame — a plain, non-alias shadow. Must be an
        outer name specifically: rebinding a name already in the CURRENT
        frame is Whence's "no rebinding" error, unrelated to effects."""
        name = self.r.choice(self.outer_visible_names())
        self.record_let(name, None)
        return "let %s = %d" % (name, self.r.randint(0, 9))

    def _stmt_call(self, depth):
        self.record_call("print")
        return self._mk_expr("print(0)")

    def _stmt_call_alias(self, depth):
        name = self.r.choice(self.known_alias_names())
        self.record_call(name)
        return self._mk_expr("%s(0)" % name)

    def _stmt_nested_block(self, depth):
        """A raw `{ ... }` value block: new alias_scopes frame, NO
        effects_stack change (only `fn` pushes that)."""
        name = self.fresh("blk")
        inner = self.gen_stmt_list(depth + 1, self.r.randint(1, 3), is_block_body=True)
        inner = self._strip_marks(inner)
        body = "{ " + "\n    ".join(inner) + " }"
        # A block used as a `let` RHS is never itself a bare NameRef, so it
        # never becomes an alias target — matches `expr.__class__ is
        # A.NameRef` gating in the real parser.
        self.record_let(name, None)
        return "let %s = %s" % (name, body)

    def _stmt_nested_fn(self, depth):
        return self._gen_fn_stmt(depth, name=self.fresh("f"))

    def _stmt_shadow_fn(self, depth):
        """A named fn whose name collides with an OUTER alias (never the
        current frame's own name — that would be an unrelated "no
        rebinding" error) — the fn name itself is never an alias
        (`alias_scopes[-1][name] = None` before params/body), but it DOES
        shadow the outer alias for the rest of this scope."""
        name = self.r.choice(self.outer_alias_names())
        return self._gen_fn_stmt(depth, name=name, shadow_precheck=True)

    def _gen_fn_stmt(self, depth, name, shadow_precheck=False):
        r = self.r
        if shadow_precheck:
            # A named fn's OWN name occupies the CURRENT frame before its
            # params/body are parsed — mirror that ordering exactly.
            self.record_let(name, None)
        else:
            self.alias_scopes[-1][name] = None
        n_params = r.randint(0, 2)
        params = [self.fresh("p") for _ in range(n_params)]
        own_spec = r.choice(EFFECT_TAG_SETS)
        resolved = self.resolve_effects_scope(own_spec)
        self.effects_stack.append(resolved)
        # params frame (dict.fromkeys(params)) pushed BEFORE the body's own
        # stmt_list frame, exactly mirroring `Parser.statement`'s fn case.
        self.alias_scopes.append(dict.fromkeys(params))
        try:
            body_lines = self.gen_stmt_list(depth + 1, r.randint(1, self.max_stmts),
                                             is_block_body=True)
        finally:
            self.effects_stack.pop()
            self.alias_scopes.pop()
        body_lines = self._strip_marks(body_lines)
        effects_txt = "" if own_spec is None else \
            " effects [%s]" % ", ".join(sorted(own_spec))
        header = "fn %s(%s)%s {" % (name, ", ".join(params), effects_txt)
        return header + "\n  " + "\n  ".join(body_lines) + "\n}"

    def _stmt_shadow_param(self, depth):
        """A fn whose PARAMETER name collides with an outer alias — the
        param frame is pushed after (outside) the name-shadow check, so the
        param shadows the alias for the whole body regardless of the fn's
        own name."""
        name = self.fresh("f")
        alias_name = self.r.choice(self.known_alias_names())
        self.alias_scopes[-1][name] = None
        own_spec = self.r.choice(EFFECT_TAG_SETS)
        resolved = self.resolve_effects_scope(own_spec)
        self.effects_stack.append(resolved)
        self.alias_scopes.append({alias_name: None})
        try:
            body_lines = self.gen_stmt_list(depth + 1, self.r.randint(1, self.max_stmts),
                                             is_block_body=True)
        finally:
            self.effects_stack.pop()
            self.alias_scopes.pop()
        body_lines = self._strip_marks(body_lines)
        effects_txt = "" if own_spec is None else \
            " effects [%s]" % ", ".join(sorted(own_spec))
        header = "fn %s(%s)%s {" % (name, alias_name, effects_txt)
        return header + "\n  " + "\n  ".join(body_lines) + "\n}"


def _import_parse(root=WHENCE_ROOT):
    if root not in sys.path:
        sys.path.insert(0, root)
    from whence.parser import parse, ParseError   # noqa: E402
    return parse, ParseError


def check_one(seed, max_depth=3, max_stmts=4):
    """Generate one program, run it through the real parser, and return
    (src, expected_verdict, actual, mismatch: bool). `actual` is `("ok",)`
    or `("error", message)`."""
    parse, ParseError = _import_parse()
    gen = AliasEffectsGen(seed, max_depth=max_depth, max_stmts=max_stmts)
    src, expected = gen.gen_program()
    try:
        parse(src)
        actual = ("ok",)
    except ParseError as e:
        actual = ("error", str(e))
    if expected[0] == "ok":
        mismatch = actual[0] != "ok"
    else:
        _, name, tag = expected
        mismatch = not (actual[0] == "error" and
                         ("'%s' requires effect '%s'" % (name, tag)) in actual[1])
    return src, expected, actual, mismatch
