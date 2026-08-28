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


# ============================================================= v0.14.3-5 ===
# Round 281 (SWE-loop D): a SECOND independent oracle, extending the same
# idea to the three effect-alias features round 269's own backlog left
# untouched — `return_alias_scopes` (v0.14.3, round 270: does CALLING a
# name yield an effectful alias — a fn tail-returning a bare name, or a
# `let g = fn(){...}` closure doing the same), `field_alias_scopes`
# (v0.14.4, round 272: `box.field(...)` where `box` is a record-literal
# `let` whose field value is a bare effectful name), and the if/else-tail
# combination rule (v0.14.5, round 276: `_if_tail_alias_tag`, every arm of
# a tail `if`/`else`, any `else if` chain length, must resolve to the
# EXACT same tag). All three shipped with only ~14-51 hand-written
# `tests/test_v14.py` cases each and, per rounds 266/270/272/276/277/279's
# own repeated next-steps notes, round 278's `fuzz.py` generator additions
# only gave the CRASH-safety (totality) oracle reachability into these
# shapes — nothing has ever independently checked whether the effect
# system's VERDICT (accept vs. the exact right ParseError) is correct for
# any of the three. `AliasEffectsGen` above can't simply be extended in
# place: `return_alias_scopes`/`field_alias_scopes` are pushed/popped in
# lockstep with `alias_scopes` at three call sites in the real parser
# (`stmt_list`, and both fn-parameter pushes), and a fn body's own tail
# tag is a genuinely recursive fact (an `if`/`else` tail's combined tag
# depends on both arms' OWN already-resolved tails) that `AliasEffectsGen`
# never needed to compute, since v0.14.2 has no notion of a function
# "returning" anything.
#
# Design, same discipline as `AliasEffectsGen`'s own docstring: a SECOND,
# independently written implementation of `Parser._resolve_effectful_
# alias`/`_resolve_effectful_return`/`_resolve_effectful_field`/
# `_check_effect_call`/`_if_tail_alias_tag`/`stmt_list`'s docstrings
# (read, not copied), predicting the parse verdict incrementally in the
# same left-to-right, single-pass order the spec documents — not a
# fixed-point analysis, not a call into `whence.parser` itself.

class ExtendedEffectGen(object):
    """Generates (source, verdict) pairs covering v0.14.2/3/4/5 together
    (the three later features build on frames v0.14.2 already pushes, so
    exercising them in isolation from v0.14.2's own alias tracking would
    both duplicate work and miss real interactions, e.g. a `let g = alias`
    rename copying BOTH the alias tag and the return tag in one step —
    `Parser.statement`'s NameRef branch, line ~234).

    Mirrors three parallel stacks (`alias_scopes`, `return_alias_scopes`,
    `field_alias_scopes`), pushed/popped together at every frame boundary,
    exactly matching the real parser's own three call sites (`gen_frame`
    below plays the role of one `stmt_list` invocation; the fn-statement
    and fn-expression generators each push/pop a params frame the same way
    `Parser.statement`'s fn case and `Parser.primary`'s anonymous-fn case
    both do).
    """

    def __init__(self, seed, max_depth=3, max_stmts=4):
        self.r = random.Random(seed)
        self.max_depth = max_depth
        self.max_stmts = max_stmts
        self.counter = 0
        self.done = False
        self.verdict = ("ok",)
        self.alias_scopes = []
        self.return_alias_scopes = []
        self.field_alias_scopes = []
        self.effects_stack = []

    def fresh(self, prefix="v"):
        self.counter += 1
        name = "%s%d" % (prefix, self.counter)
        assert name not in RESERVED
        return name

    # -- resolution: mirrors the three Parser._resolve_effectful_* ------
    def resolve_alias(self, name):
        for scope in reversed(self.alias_scopes):
            if name in scope:
                return scope[name]
        return EFFECTFUL.get(name)

    def resolve_return(self, name):
        for scope in reversed(self.return_alias_scopes):
            if name in scope:
                return scope[name]
        return None

    def resolve_field(self, name, field):
        for scope in reversed(self.field_alias_scopes):
            if name in scope:
                fields = scope[name]
                return fields.get(field) if fields else None
        return None

    def resolve_effects_scope(self, own_spec):
        if own_spec is not None:
            return own_spec
        return self.effects_stack[-1] if self.effects_stack else None

    # -- name-visibility helpers ------------------------------------
    def known_alias_names(self):
        return [n for scope in self.alias_scopes for n, t in scope.items() if t is not None]

    def known_return_names(self):
        return [n for scope in self.return_alias_scopes for n, t in scope.items() if t is not None]

    def known_field_names(self):
        out = []
        for scope in self.field_alias_scopes:
            for name, fields in scope.items():
                if fields:
                    out.extend((name, f) for f, t in fields.items() if t is not None)
        return out

    def any_visible_name(self):
        return [n for scope in self.alias_scopes for n in scope]

    def outer_visible_names(self):
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
        return [n for n in self.outer_visible_names() if self.resolve_alias(n) is not None]

    def outer_return_names(self):
        return [n for n in self.outer_visible_names() if self.resolve_return(n) is not None]

    def any_return_carrier_names(self):
        """Every name currently registered as a return-carrier SLOT in any
        open frame, regardless of its own tag value — unlike
        `known_return_names()` (filtered to non-None tags only), this
        includes names whose CORRECTLY-resolved return tag is None, e.g.
        a fn whose tail is an `if`/`else` with mismatched arms. Needed so
        the campaign can still generate a call THROUGH such a name: a
        buggy `_if_tail_alias_tag` (an unsound arm match) only produces an
        observable divergence from the real parser if something later
        actually calls the mistracked name — `known_return_names()` alone
        can never select it, since its own correct tag is None."""
        return [n for scope in self.return_alias_scopes for n in scope]

    # -- effect-check side, mirrors `_check_effect_call` -----------------
    def check_effect(self, tag, display):
        if self.done or tag is None:
            return
        scope = self.effects_stack[-1] if self.effects_stack else None
        if scope is None or tag in scope:
            return
        self.done = True
        self.verdict = ("error", display, tag)

    def record_call_direct(self, name):
        self.check_effect(self.resolve_alias(name), name)

    def record_call_return(self, fname):
        self.check_effect(self.resolve_return(fname), "%s()" % fname)

    def record_call_return_chain(self, fname):
        """Models `fname()(...)` — TWO applications, `postfix()` builds
        (and `_check_effect_call`s) them left-to-right: the INNER `fname()`
        is itself an ordinary direct call, checked via `_resolve_effectful_
        alias(fname)` first (a name drawn from the wide `any_return_
        carrier_names()` pool can independently BE an effectful alias, not
        just a return-carrier) — only if that doesn't already raise does
        the OUTER application's own return-chain check
        (`_resolve_effectful_return`) run. A bare `record_call_return`
        alone silently skips the inner check, which is unobservable for
        genuine fn/closure names (never also a direct alias — see
        `known_return_names()`'s callers) but wrong for the wider pool."""
        self.record_call_direct(fname)
        if self.done:
            return
        self.record_call_return(fname)

    def record_call_field(self, boxname, field):
        self.check_effect(self.resolve_field(boxname, field), "%s.%s" % (boxname, field))

    def bind(self, name, alias_tag, return_tag, field_dict):
        self.alias_scopes[-1][name] = alias_tag
        self.return_alias_scopes[-1][name] = return_tag
        self.field_alias_scopes[-1][name] = field_dict

    # -- generation -------------------------------------------------
    _EXPR_MARK = "\x00EXPR\x00"

    def _mk_expr(self, text):
        return self._EXPR_MARK + text

    def _strip_marks(self, lines):
        return [l[len(self._EXPR_MARK):] if l.startswith(self._EXPR_MARK) else l
                for l in lines]

    def gen_program(self):
        lines, _ = self.gen_frame(0, self.r.randint(min(3, self.max_stmts), max(3, self.max_stmts)),
                                   is_block_body=False)
        lines = self._strip_marks(lines)
        return "\n".join(lines) + "\n", self.verdict

    def gen_frame(self, depth, n, is_block_body):
        """One `stmt_list` frame: pushes/pops all three stacks together.
        If `is_block_body` (a real `{...}` block, per `block()`'s own
        "must end with an expression" rule), the FINAL slot is always an
        expression statement and its resolved tail tag is returned as the
        second value — mirroring `stmt_list`'s own `(stmts, tail_tag)`."""
        self.alias_scopes.append({})
        self.return_alias_scopes.append({})
        self.field_alias_scopes.append({})
        try:
            lines = []
            tail_tag = None
            produced_tail = False
            budget = max(n, 1)
            while budget > 0:
                budget -= 1
                is_last_slot = (budget == 0)
                if self.done and not is_last_slot and self.r.random() < 0.7:
                    break
                if is_block_body and is_last_slot:
                    line, tail_tag = self.gen_tail_stmt(depth)
                    lines.append(line)
                    produced_tail = True
                else:
                    lines.append(self.gen_one_stmt(depth))
            if is_block_body and not produced_tail:
                line, tail_tag = self.gen_tail_stmt(depth)
                lines.append(line)
            elif not is_block_body and not lines:
                lines.append(self.gen_one_stmt(depth))
            return lines, (tail_tag if is_block_body else None)
        finally:
            self.alias_scopes.pop()
            self.return_alias_scopes.pop()
            self.field_alias_scopes.pop()

    def gen_cond(self):
        return self.r.choice(["true", "false", "1 < 2", "2 < 1"])

    def gen_tail_stmt(self, depth):
        r = self.r
        choices = ["plain"]
        names = self.any_visible_name()
        if names:
            choices += ["bare_name"] * 2
        if depth < self.max_depth:
            choices += ["if_tail"] * 4
        kind = r.choice(choices)
        if kind == "bare_name":
            name = r.choice(names)
            return self._mk_expr(name), self.resolve_alias(name)
        if kind == "if_tail":
            src, tag = self._gen_if_tail_inner(depth)
            return self._mk_expr(src), tag
        return self.gen_plain_tail_expr()

    def _gen_if_tail_inner(self, depth):
        """Mirror of `_if_tail_alias_tag`: builds `if C {..} else {..}`,
        recursing into an `else if` chain, and combines tags requiring an
        EXACT match across every arm (an approximate match would be
        unsound — see `_if_tail_alias_tag`'s own docstring)."""
        r = self.r
        cond = self.gen_cond()
        then_lines, then_tag = self.gen_frame(depth + 1, r.randint(1, self.max_stmts), True)
        then_src = "{ " + "\n    ".join(self._strip_marks(then_lines)) + " }"
        if depth + 2 < self.max_depth and r.random() < 0.35:
            else_src, else_tag = self._gen_if_tail_inner(depth + 1)
        else:
            else_lines, else_tag = self.gen_frame(depth + 1, r.randint(1, self.max_stmts), True)
            else_src = "{ " + "\n    ".join(self._strip_marks(else_lines)) + " }"
        combined = then_tag if (then_tag is not None and then_tag == else_tag) else None
        return "if %s %s else %s" % (cond, then_src, else_src), combined

    def gen_plain_tail_expr(self):
        """A tail that is a Call/literal, never a bare NameRef or If —
        always contributes `tail_tag=None` (see `stmt_list`'s docstring:
        only those two shapes are inspected for a tail fact)."""
        r = self.r
        aliases, returns, fields = (self.known_alias_names(), self.known_return_names(),
                                     self.known_field_names())
        choice = r.random()
        if choice < 0.25 and aliases:
            name = r.choice(aliases)
            self.record_call_direct(name)
            return self._mk_expr("%s(0)" % name), None
        if choice < 0.45:
            self.record_call_direct("print")
            return self._mk_expr("print(0)"), None
        if choice < 0.55 and returns:
            fname = r.choice(returns)
            self.record_call_return_chain(fname)
            return self._mk_expr("%s()(0)" % fname), None
        carriers = self.any_return_carrier_names()
        if choice < 0.65 and carriers:
            fname = r.choice(carriers)
            self.record_call_return_chain(fname)
            return self._mk_expr("%s()(0)" % fname), None
        if choice < 0.75 and fields:
            boxname, field = r.choice(fields)
            self.record_call_field(boxname, field)
            return self._mk_expr("%s.%s(0)" % (boxname, field)), None
        return self._mk_expr(str(r.randint(0, 9))), None

    def gen_one_stmt(self, depth):
        r = self.r
        choices = ["let_builtin_alias", "let_plain", "call", "let_record"]
        if self.known_alias_names():
            choices += ["let_alias_chain", "call_alias"]
        if self.known_return_names():
            choices += ["let_call_return", "call_return_chain"] * 3
        if self.any_return_carrier_names():
            choices += ["call_return_chain_any"] * 3
        if self.known_field_names():
            choices += ["call_field"]
        if self.outer_visible_names():
            choices += ["shadow_let"]
        if depth < self.max_depth:
            choices += ["nested_fn", "nested_block", "let_fn_expr"]
            if self.outer_alias_names() or self.outer_return_names():
                choices += ["shadow_fn"]
            if self.known_alias_names() or self.known_return_names():
                choices += ["shadow_param"]
        kind = r.choice(choices)
        return getattr(self, "_stmt_" + kind)(depth)

    def _stmt_let_builtin_alias(self, depth):
        name = self.fresh("a")
        self.bind(name, EFFECTFUL.get("print"), None, None)
        return "let %s = print" % name

    def _stmt_let_alias_chain(self, depth):
        # NameRef RHS (`Parser.statement`, ~line 234): copies BOTH the
        # alias tag AND the return tag forward under the new name.
        src = self.r.choice(self.known_alias_names())
        name = self.fresh("a")
        self.bind(name, self.resolve_alias(src), self.resolve_return(src), None)
        return "let %s = %s" % (name, src)

    def _stmt_let_call_return(self, depth):
        # `let a = get()` where `get` is a tracked return-carrier
        # (~line 237-244): `a` becomes an ordinary alias of whatever tag
        # `get` was tracked to return; NOT itself a return-carrier.
        fname = self.r.choice(self.known_return_names())
        name = self.fresh("a")
        self.bind(name, self.resolve_return(fname), None, None)
        return "let %s = %s()" % (name, fname)

    def _stmt_let_fn_expr(self, depth):
        # `let g = fn(...) {...}` (~line 245-252): `g` is a callable, not
        # itself an effectful value; its return fact is the body's tail.
        name = self.fresh("g")
        n_params = self.r.randint(0, 2)
        params = [self.fresh("p") for _ in range(n_params)]
        own_spec = self.r.choice(EFFECT_TAG_SETS)
        self.effects_stack.append(self.resolve_effects_scope(own_spec))
        self.alias_scopes.append(dict.fromkeys(params))
        self.return_alias_scopes.append(dict.fromkeys(params))
        self.field_alias_scopes.append(dict.fromkeys(params))
        try:
            body_lines, body_tag = self.gen_frame(depth + 1, self.r.randint(1, self.max_stmts), True)
        finally:
            self.effects_stack.pop()
            self.alias_scopes.pop()
            self.return_alias_scopes.pop()
            self.field_alias_scopes.pop()
        effects_txt = "" if own_spec is None else " effects [%s]" % ", ".join(sorted(own_spec))
        header = "fn(%s)%s {" % (", ".join(params), effects_txt)
        src = header + "\n  " + "\n  ".join(self._strip_marks(body_lines)) + "\n}"
        self.bind(name, None, body_tag, None)
        return "let %s = %s" % (name, src)

    def _stmt_let_record(self, depth):
        # `let box = @{f1: name1, f2: 5, ...}` (~line 253-270): only
        # bare-NameRef field VALUES are tracked; other field shapes are
        # simply absent from the dict (not recorded as None).
        r = self.r
        name = self.fresh("box")
        pool = self.any_visible_name()
        aliases = self.known_alias_names()
        parts = []
        field_dict = {}
        for i in range(1, r.randint(1, 3) + 1):
            fname = "f%d" % i
            src_name = None
            if aliases and r.random() < 0.5:
                src_name = r.choice(aliases)
            elif pool and r.random() < 0.7:
                src_name = r.choice(pool)
            if src_name is not None:
                parts.append("%s: %s" % (fname, src_name))
                field_dict[fname] = self.resolve_alias(src_name)
            else:
                parts.append("%s: %d" % (fname, r.randint(0, 9)))
        self.bind(name, None, None, field_dict)
        return "let %s = @{%s}" % (name, ", ".join(parts))

    def _stmt_let_plain(self, depth):
        name = self.fresh("v")
        self.bind(name, None, None, None)
        return "let %s = %d" % (name, self.r.randint(0, 9))

    def _stmt_shadow_let(self, depth):
        name = self.r.choice(self.outer_visible_names())
        self.bind(name, None, None, None)
        return "let %s = %d" % (name, self.r.randint(0, 9))

    def _stmt_call(self, depth):
        self.record_call_direct("print")
        return self._mk_expr("print(0)")

    def _stmt_call_alias(self, depth):
        name = self.r.choice(self.known_alias_names())
        self.record_call_direct(name)
        return self._mk_expr("%s(0)" % name)

    def _stmt_call_return_chain(self, depth):
        fname = self.r.choice(self.known_return_names())
        self.record_call_return_chain(fname)
        return self._mk_expr("%s()(0)" % fname)

    def _stmt_call_return_chain_any(self, depth):
        fname = self.r.choice(self.any_return_carrier_names())
        self.record_call_return_chain(fname)
        return self._mk_expr("%s()(0)" % fname)

    def _stmt_call_field(self, depth):
        boxname, field = self.r.choice(self.known_field_names())
        self.record_call_field(boxname, field)
        return self._mk_expr("%s.%s(0)" % (boxname, field))

    def _stmt_nested_block(self, depth):
        name = self.fresh("blk")
        inner_lines, _ = self.gen_frame(depth + 1, self.r.randint(1, 3), True)
        body = "{ " + "\n    ".join(self._strip_marks(inner_lines)) + " }"
        self.bind(name, None, None, None)
        return "let %s = %s" % (name, body)

    def _stmt_nested_fn(self, depth):
        return self._gen_fn_stmt(depth, name=self.fresh("f"))

    def _stmt_shadow_fn(self, depth):
        pool = self.outer_alias_names() + self.outer_return_names()
        name = self.r.choice(pool)
        return self._gen_fn_stmt(depth, name=name, shadow_precheck=True)

    def _gen_fn_stmt(self, depth, name, shadow_precheck=False):
        r = self.r
        if shadow_precheck:
            self.bind(name, None, None, None)
        else:
            self.alias_scopes[-1][name] = None
            self.return_alias_scopes[-1][name] = None
            self.field_alias_scopes[-1][name] = None
        params = [self.fresh("p") for _ in range(r.randint(0, 2))]
        own_spec = r.choice(EFFECT_TAG_SETS)
        self.effects_stack.append(self.resolve_effects_scope(own_spec))
        self.alias_scopes.append(dict.fromkeys(params))
        self.return_alias_scopes.append(dict.fromkeys(params))
        self.field_alias_scopes.append(dict.fromkeys(params))
        try:
            body_lines, body_tag = self.gen_frame(depth + 1, r.randint(1, self.max_stmts), True)
        finally:
            self.effects_stack.pop()
            self.alias_scopes.pop()
            self.return_alias_scopes.pop()
            self.field_alias_scopes.pop()
        self.return_alias_scopes[-1][name] = body_tag
        effects_txt = "" if own_spec is None else " effects [%s]" % ", ".join(sorted(own_spec))
        header = "fn %s(%s)%s {" % (name, ", ".join(params), effects_txt)
        return header + "\n  " + "\n  ".join(self._strip_marks(body_lines)) + "\n}"

    def _stmt_shadow_param(self, depth):
        r = self.r
        name = self.fresh("f")
        pool = self.known_alias_names() + self.known_return_names()
        shadow_name = r.choice(pool)
        self.alias_scopes[-1][name] = None
        self.return_alias_scopes[-1][name] = None
        self.field_alias_scopes[-1][name] = None
        own_spec = r.choice(EFFECT_TAG_SETS)
        self.effects_stack.append(self.resolve_effects_scope(own_spec))
        self.alias_scopes.append({shadow_name: None})
        self.return_alias_scopes.append({shadow_name: None})
        self.field_alias_scopes.append({shadow_name: None})
        try:
            body_lines, body_tag = self.gen_frame(depth + 1, r.randint(1, self.max_stmts), True)
        finally:
            self.effects_stack.pop()
            self.alias_scopes.pop()
            self.return_alias_scopes.pop()
            self.field_alias_scopes.pop()
        self.return_alias_scopes[-1][name] = body_tag
        effects_txt = "" if own_spec is None else " effects [%s]" % ", ".join(sorted(own_spec))
        header = "fn %s(%s)%s {" % (name, shadow_name, effects_txt)
        return header + "\n  " + "\n  ".join(self._strip_marks(body_lines)) + "\n}"


def check_one_ext(seed, max_depth=3, max_stmts=4):
    """Same contract as `check_one`, against `ExtendedEffectGen`."""
    parse, ParseError = _import_parse()
    gen = ExtendedEffectGen(seed, max_depth=max_depth, max_stmts=max_stmts)
    src, expected = gen.gen_program()
    try:
        parse(src)
        actual = ("ok",)
    except ParseError as e:
        actual = ("error", str(e))
    if expected[0] == "ok":
        mismatch = actual[0] != "ok"
    else:
        _, display, tag = expected
        mismatch = not (actual[0] == "error" and
                         ("'%s' requires effect '%s'" % (display, tag)) in actual[1])
    return src, expected, actual, mismatch
