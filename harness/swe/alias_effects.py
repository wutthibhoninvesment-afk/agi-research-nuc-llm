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

# v0.14.8 (round 294) added `rand`/"random" as a SECOND entry in the real
# parser's own `_EFFECTFUL_BUILTINS` — this dict is this module's
# independent mirror of that same ground truth, so it gains the identical
# second entry (round 299). `AliasEffectsGen` below stays frozen to its own
# documented v0.14.2 scope and never emits "rand" as source text, so the
# new entry is simply inert there — `ExtendedEffectGen` (round 299) is the
# one that actually exercises it, mirroring how `EFFECT_TAG_SETS` below is
# already shared plumbing between both generators without either being
# forced to use every combination it offers.
EFFECTFUL = {"print": "io", "rand": "random"}
EFFECT_TAG_SETS = (None, frozenset(), frozenset(["io"]), frozenset(["net"]),
                   frozenset(["io", "net"]), frozenset(["random"]),
                   frozenset(["io", "random"]), frozenset(["net", "random"]),
                   frozenset(["io", "net", "random"]))
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
# Round 287 (SWE-loop D): folded v0.14.6's `field_return_alias_scopes`
# (round 282/284) into this SAME generator/oracle rather than writing a
# third one — v0.14.6 is a fourth stack pushed/popped in lockstep with the
# other three at the EXACT same three call sites (verified directly
# against `whence/parser.py` line-by-line before writing a single line of
# generator code: `stmt_list` line ~204/232, the named-fn push/pop
# ~345/353, and the anonymous-`FnExpr` push/pop ~934/942 — all four
# `.append`/`.pop` calls appear together at each site, no exceptions), and
# its resolution (`_resolve_effectful_field_return`) is a direct textual
# mirror of `_resolve_effectful_field`, just walking
# `field_return_alias_scopes` instead. Round 281's own "can't simply be
# extended in place" reasoning was about ADDING return/field tracking to a
# generator (`AliasEffectsGen`) that had NEITHER — that reasoning does not
# apply here, since `ExtendedEffectGen` already carries the exact
# `return_alias_scopes` and `field_alias_scopes` machinery this fourth
# stack composes with (`_check_effect_call`'s own v0.14.6 branch is
# LITERALLY `box.run()(1)`, the `postfix()` loop's field-access callee
# check — v0.14.4's `_resolve_effectful_field` — immediately followed, on
# the SAME name, by v0.14.3's own return-chain check but resolved through
# `_resolve_effectful_field_return` instead of `_resolve_effectful_
# return`). See `record_call_field_return_chain`'s own docstring for the
# two-application ordering this mirrors.
#
# Design, same discipline as `AliasEffectsGen`'s own docstring: a SECOND,
# independently written implementation of `Parser._resolve_effectful_
# alias`/`_resolve_effectful_return`/`_resolve_effectful_field`/
# `_resolve_effectful_field_return`/`_check_effect_call`/
# `_if_tail_alias_tag`/`stmt_list`'s docstrings (read, not copied),
# predicting the parse verdict incrementally in the same left-to-right,
# single-pass order the spec documents — not a fixed-point analysis, not a
# call into `whence.parser` itself.
#
# Round 293 (SWE-loop D): folded v0.14.7's `nested_field_alias_scopes`
# (round 288, the container-field-value-flow-through-a-NESTED-record-
# literal shape, `outer.box.run(...)` where `box`'s own value is ITSELF a
# record literal) into this SAME generator/oracle, closing the gap round
# 288/289/290/291's own next-steps lists repeatedly named. Verified against
# `whence/parser.py` line-by-line first: `nested_field_alias_scopes` is a
# FIFTH stack pushed/popped at the identical three call sites the other
# four already use (`stmt_list` ~226/255, the named-fn push/pop ~379-395/
# 402-404, the anonymous-`FnExpr` push/pop), and `_check_effect_call`'s
# v0.14.7 branch is structurally distinct from (not composed with) the
# v0.14.4 branch — a callee whose own `.obj` is a `FieldAccess` can never
# also match the v0.14.4 branch's `callee.obj.__class__ is A.NameRef`
# guard (confirmed directly in round 288's own knowledge file and
# `_check_effect_call`'s docstring) — so `record_call_field_nested` below
# is a single check, unlike `record_call_field_return_chain`'s two-
# application chain. One genuine difference from `field_return_alias_
# scopes`: the real parser's `nested_field_alias_scopes` construction
# resolves its INNER dict via `_resolve_effectful_alias` only (parser.py's
# v0.14.7 `let`-branch comment) — there is no second, `_resolve_effectful_
# return`-based inner dict the way `field_alias_scopes`/`field_return_
# alias_scopes` form an independent pair — so `_gen_nested_record_fields`
# below mirrors that asymmetry rather than reusing `_stmt_let_record`'s
# own `returns`-then-`aliases`-then-`pool` cascade unchanged. Unlike round
# 287's v0.14.6 case (a genuinely rare compound event, ~0.047%, needing a
# dedicated statement AND reprioritized draw probabilities to become
# testable at all — see `_stmt_shadow_box_call_field_return`'s own
# docstring), this shape's inner precondition (`known_alias_names()`
# non-empty) is common from the start, so a single dedicated statement
# (`_stmt_shadow_box_call_field_nested`, mirroring the v0.14.6 one's
# shape) was sufficient without extra reprioritization — measured directly
# before sizing the mutation test below, ~9% of generated programs (not
# ~0.05%).
#
# Round 299 (SWE-loop D): v0.14.8 (round 294) added `rand` as a SECOND
# effectful builtin (tag "random", arity 0) — a genuinely different kind of
# extension from every prior round's own addition to this generator/oracle:
# rounds 281/287/293 each added a new ALIAS-TRACKING SHAPE (a new stack, a
# new `_resolve_effectful_*` mirror) for the SAME one builtin, `print`.
# `rand` is the opposite axis — the SAME five already-shipped shapes, but a
# SECOND source name that can flow through every one of them. No new stack,
# no new `resolve_*`/`record_call_*` method is needed: `known_alias_names()`,
# `_stmt_let_record`'s field-alias/field-return-alias pools, and every other
# helper already operate on whatever tag a tracked name resolves to, not on
# the name's own identity — verified directly, the same discipline every
# prior round's own comment uses, by reading `_check_effect_call` and all
# five `_resolve_effectful_*` methods in `whence/parser.py` line-by-line
# first: none of them special-case `print` by name, only by the tag
# `_EFFECTFUL_BUILTINS.get(name)` returns. The only three places in THIS
# generator that hardcoded the literal string `"print"` instead of drawing
# from a name pool are `_stmt_let_builtin_alias` (the ONE place a fresh
# alias is ever bound directly to a builtin, not a chain), `_stmt_call`
# (the direct, non-aliased call statement), and `gen_plain_tail_expr`'s own
# direct-call branch (the fn-tail mirror of `_stmt_call`) — all three now
# pick between `print`/`rand` instead of hardcoding `print`, and every
# downstream consumer (alias chains, field literals, field-return literals,
# nested-field literals, if/else-tail combination) picks up "random"-tagged
# names for free through the exact same pools it already used for
# "io"-tagged ones. `EFFECT_TAG_SETS` above gained the four `random`-
# inclusive combinations so the GRANTED path (not just the always-denied
# "declared io/net only" path) gets exercised for `rand` specifically, the
# same reason `[io, net]` exists there already for `print`.

class ExtendedEffectGen(object):
    """Generates (source, verdict) pairs covering v0.14.2/3/4/5/6 together
    (the later features build on frames v0.14.2 already pushes, so
    exercising them in isolation from v0.14.2's own alias tracking would
    both duplicate work and miss real interactions, e.g. a `let g = alias`
    rename copying BOTH the alias tag and the return tag in one step —
    `Parser.statement`'s NameRef branch, line ~234).

    Mirrors four parallel stacks (`alias_scopes`, `return_alias_scopes`,
    `field_alias_scopes`, `field_return_alias_scopes`), pushed/popped
    together at every frame boundary, exactly matching the real parser's
    own three call sites (`gen_frame` below plays the role of one
    `stmt_list` invocation; the fn-statement and fn-expression generators
    each push/pop a params frame the same way `Parser.statement`'s fn case
    and `Parser.primary`'s anonymous-fn case both do).
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
        self.field_return_alias_scopes = []
        self.nested_field_alias_scopes = []
        self.effects_stack = []
        # v0.14.9/v0.14.10 (round 305): a SIXTH stack, `param_call_scopes`,
        # mirroring `Parser.param_call_scopes` — see this class's own
        # "Round 299" comment block above for why this needed a genuinely
        # different kind of extension from every prior round's own addition
        # (a per-CALL-SITE check, not a per-NAME resolver). `current_fn_
        # params_frame_stack`/`direct_param_calls_stack` mirror the real
        # parser's identically-named attributes exactly: the first tracks
        # the SAME dict object pushed onto `alias_scopes` for the
        # currently-open fn's own params frame (identity, not a copy,
        # matters for `_innermost_frame_containing`'s comparison — see
        # `whence/parser.py`'s own `current_fn_params_frame_stack`
        # docstring); the second accumulates, per currently-open fn, which
        # of ITS OWN params its body calls directly.
        self.param_call_scopes = []
        self.current_fn_params_frame_stack = []
        self.direct_param_calls_stack = []
        # v0.14.11 (round 306): a SEVENTH stack, mirroring `Parser.param_
        # alias_scopes`, pushed/popped at the SAME sites `param_call_scopes`
        # already is (`gen_frame`'s own per-block frame, plus the params
        # frame pushed at each of the two fn-definition sites — pushed as
        # `{}`, NOT `dict.fromkeys(params)`, exactly matching the real
        # parser: a param is never itself a rename of a param, only a
        # LATER `let`-rename can be). Each frame maps a name to either
        # `None` or the ORIGINAL PARAM NAME it is currently a pure
        # `let`-rename of, within the SAME open fn body.
        self.param_alias_scopes = []
        # v0.14.12 (round 308): an EIGHTH stack, mirroring `Parser.return_
        # param_scopes`, pushed/popped at the SAME sites `return_alias_
        # scopes` already is (`gen_frame`'s own per-block frame gets `{}`;
        # the params frame pushed at each fn-definition site gets
        # `dict.fromkeys(params)`). Each frame maps a name to either `None`
        # or `(params_tuple, tail_param_name)` — a fn whose body's own tail
        # directly returns one of its own params, unchanged.
        self.return_param_scopes = []

    def fresh(self, prefix="v"):
        self.counter += 1
        name = "%s%d" % (prefix, self.counter)
        assert name not in RESERVED
        return name

    def _random_effectful_builtin(self):
        """Round 299: `print`/`rand`, picked uniformly, for the three call
        sites (`_stmt_let_builtin_alias`, `_stmt_call`, `gen_plain_tail_
        expr`'s own direct-call branch) that reference a builtin BY NAME
        rather than through a tracked-alias pool. Returns `(name,
        call_text)` — `rand` is arity 0 (`rand()`) where `print` is arity 1
        (`print(0)`), but this split is purely cosmetic: `whence/parser.py`
        has no arity check at all (only `whence/interp.py` does, at
        runtime), so parse-time verdict correctness never depends on
        argument count here."""
        return self.r.choice((("print", "print(0)"), ("rand", "rand()")))

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

    def resolve_field_return(self, name, field):
        """Mirror of `_resolve_effectful_field_return`, exactly as
        `resolve_field` mirrors `_resolve_effectful_field`: same
        innermost-first, first-frame-wins walk on `name`, over
        `field_return_alias_scopes` instead."""
        for scope in reversed(self.field_return_alias_scopes):
            if name in scope:
                fields = scope[name]
                return fields.get(field) if fields else None
        return None

    def resolve_field_nested(self, name, outer_field, inner_field):
        """Mirror of `_resolve_effectful_field_nested`: same innermost-
        first, first-frame-wins walk on `name` over `nested_field_alias_
        scopes`, then a `.get(outer_field)` into the winning frame's dict,
        then a further guarded `.get(inner_field)` on WHATEVER that
        returns (missing/falsy at either level, or `name` not tracked at
        all, all fall out to `None` the same way `_resolve_effectful_
        field`/`_resolve_effectful_field_return` guard their own single
        `.get`)."""
        for scope in reversed(self.nested_field_alias_scopes):
            if name in scope:
                outer = scope[name]
                if not outer:
                    return None
                inner = outer.get(outer_field)
                return inner.get(inner_field) if inner else None
        return None

    def resolve_effects_scope(self, own_spec):
        if own_spec is not None:
            return own_spec
        return self.effects_stack[-1] if self.effects_stack else None

    def resolve_param_call_fact(self, name):
        """Mirror of `Parser._resolve_param_call_fact`: same innermost-
        first, first-frame-wins walk on `name`, over `param_call_scopes`
        instead of `return_alias_scopes`. Returns `None` or `(effects_
        scope, params_tuple, frozenset_of_called_param_names)`."""
        for scope in reversed(self.param_call_scopes):
            if name in scope:
                return scope[name]
        return None

    def _innermost_frame_containing(self, name):
        """Mirror of `Parser._innermost_frame_containing`: the exact frame
        OBJECT (not a copy) in `alias_scopes` an innermost-first walk would
        resolve `name` through, for an identity comparison against
        `current_fn_params_frame_stack[-1]` — `None` if `name` isn't bound
        in any open scope at all."""
        for scope in reversed(self.alias_scopes):
            if name in scope:
                return scope
        return None

    def resolve_param_alias(self, name):
        """Mirror of `Parser._resolve_param_alias`: does `name`, AS
        CURRENTLY IN SCOPE, refer — through one or more `let`-rename hops,
        all WITHIN THE SAME currently-open fn body — to one of that fn's
        own params? Bounded to the CURRENTLY open fn's own params frame and
        everything pushed AFTER it (never an ENCLOSING fn's own frames),
        found by locating `current_fn_params_frame_stack[-1]`'s own
        identity inside `alias_scopes` and refusing to walk any
        `param_alias_scopes` frame below that boundary — the exact
        cross-fn-collision guard `_resolve_param_alias`'s own docstring
        explains."""
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

    def _resolve_param_identity_then_alias(self, name):
        """Shared identity-then-rename-chain check used by BOTH the `let`
        rename branch (is the RHS literally one of the currently-open fn's
        own params, or already a rename of one?) and `_tail_return_param_
        name` (is a bare-NameRef tail the same thing?) — the real parser
        duplicates this exact two-step check at both sites rather than
        factoring it out (see `_tail_return_param_name`'s own docstring:
        "mirrors `_check_effect_call`'s own leading v0.14.9 block
        exactly"), so this oracle names the shared shape once instead."""
        if not self.current_fn_params_frame_stack:
            return None
        owning_frame = self._innermost_frame_containing(name)
        if owning_frame is self.current_fn_params_frame_stack[-1]:
            return name
        return self.resolve_param_alias(name)

    def resolve_return_param_fact(self, name):
        """Mirror of `Parser._resolve_return_param_fact`: does `name`, AS
        CURRENTLY IN SCOPE, refer to a fn whose body's own tail directly
        returns one of its own params? Same innermost-first, first-frame-
        wins walk as every other resolver in this family, over `return_
        param_scopes`. Returns `None` or `(params_tuple, tail_param_name)`."""
        for scope in reversed(self.return_param_scopes):
            if name in scope:
                return scope[name]
        return None

    def resolve_return_param_passthrough(self, fn_name, arg_infos):
        """Mirror of `Parser._resolve_return_param_passthrough`: if
        `fn_name` is a tracked "returns one of its own params directly" fn,
        and the ARGUMENT at that param's own position in `arg_infos` is
        itself a bare NameRef resolving to an effectful alias, return that
        alias's tag — `None` whenever any link in the chain is missing
        (untracked fn, out-of-range position, or a non-NameRef/non-
        effectful argument at that position)."""
        fact = self.resolve_return_param_fact(fn_name)
        if fact is None:
            return None
        params_tuple, tail_param_name = fact
        try:
            idx = params_tuple.index(tail_param_name)
        except ValueError:
            return None
        if idx >= len(arg_infos):
            return None
        is_nameref, argname = arg_infos[idx]
        if not is_nameref:
            return None
        return self.resolve_alias(argname)

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

    def known_field_return_names(self):
        out = []
        for scope in self.field_return_alias_scopes:
            for name, fields in scope.items():
                if fields:
                    out.extend((name, f) for f, t in fields.items() if t is not None)
        return out

    def any_field_return_carrier_names(self):
        """`known_field_return_names()` widened to include (box, field)
        pairs whose CORRECTLY-resolved field-return tag is None — the
        field-access analogue of `any_return_carrier_names()`, needed for
        the same reason: a mistracked `_resolve_effectful_field_return`
        that unsoundly turns a None into a real tag is only observable if
        something later actually calls THROUGH that specific (box, field)
        pair, and the narrower non-None-filtered pool can never select a
        pair whose correct tag is None."""
        out = []
        for scope in self.field_return_alias_scopes:
            for name, fields in scope.items():
                if fields:
                    out.extend((name, f) for f in fields)
        return out

    def outer_field_return_box_pairs(self):
        """(box, field) pairs for OUTER-frame box bindings carrying a
        field-return-carrier field slot (any tag value — the widened
        `any_...` form), excluding any box name already rebound in the
        CURRENT frame — the field-return analogue of `outer_visible_
        names`'s own "no rebind, only a true first-time shadow" rule.
        Feeds `_stmt_shadow_box_call_field_return` below: picking the
        right box purely by chance out of `outer_visible_names()` (as
        plain `_stmt_shadow_let` does) and THEN happening to make a
        follow-up call through that exact name is a compound-rare event —
        measured at roughly 1-in-15000 generated programs — so that
        statement targets this pool directly instead."""
        current = self.field_return_alias_scopes[-1]
        seen = set()
        out = []
        for scope in self.field_return_alias_scopes[:-1]:
            for name, fields in scope.items():
                if fields and name not in current and name not in seen:
                    seen.add(name)
                    out.extend((name, f) for f in fields)
        return out

    def known_nested_field_names(self):
        """(boxname, outer_field, inner_field) triples whose resolved
        v0.14.7 tag is non-None — the two-hop-deeper analogue of
        `known_field_names()`, over `nested_field_alias_scopes`."""
        out = []
        for scope in self.nested_field_alias_scopes:
            for name, outer in scope.items():
                if not outer:
                    continue
                for outer_field, inner in outer.items():
                    if not inner:
                        continue
                    out.extend((name, outer_field, inner_field)
                                for inner_field, tag in inner.items() if tag is not None)
        return out

    def any_nested_field_carrier_names(self):
        """`known_nested_field_names()` widened to include triples whose
        CORRECTLY-resolved tag is None — the nested-field analogue of
        `any_field_return_carrier_names()`, needed for the same reason: a
        mistracked `_resolve_effectful_field_nested` that unsoundly turns
        a None into a real tag is only observable if something later
        actually calls THROUGH that specific (box, outer_field,
        inner_field) triple."""
        out = []
        for scope in self.nested_field_alias_scopes:
            for name, outer in scope.items():
                if not outer:
                    continue
                for outer_field, inner in outer.items():
                    if inner:
                        out.extend((name, outer_field, inner_field) for inner_field in inner)
        return out

    def outer_nested_field_box_triples(self):
        """(box, outer_field, inner_field) triples for OUTER-frame box
        bindings carrying a nested-field-carrier slot (any tag value),
        excluding any box name already rebound in the CURRENT frame — the
        nested-field analogue of `outer_field_return_box_pairs()`, feeding
        `_stmt_shadow_box_call_field_nested` below for the same
        compound-rarity reason that statement's own docstring explains."""
        current = self.nested_field_alias_scopes[-1]
        seen = set()
        out = []
        for scope in self.nested_field_alias_scopes[:-1]:
            for name, outer in scope.items():
                if not outer or name in current or name in seen:
                    continue
                seen.add(name)
                for outer_field, inner in outer.items():
                    if inner:
                        out.extend((name, outer_field, inner_field) for inner_field in inner)
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

    def known_param_call_names(self):
        """Names currently visible (any frame) with a recorded, non-None
        `param_call_scopes` fact — a NAMED fn or `let`-bound anonymous fn
        that directly calls at least one of its own params. Candidates for
        `_stmt_call_tracked_fn` below, the statement that actually
        exercises `_check_call_site_param_effects`'s verdict."""
        return [n for scope in self.param_call_scopes for n, f in scope.items() if f is not None]

    def outer_param_call_names(self):
        """`outer_visible_names()` (names bound in an OUTER frame, not yet
        rebound in the CURRENT one) filtered to ones that CURRENTLY resolve
        a non-None param-call fact — same "filter through the real resolve
        walk, not a raw scope scan" pattern `outer_alias_names()`/
        `outer_return_names()` already use, so what this returns is
        guaranteed still resolvable (no closer, already-open frame has
        re-shadowed it to `None`). Feeds `_stmt_shadow_tracked_fn_call`
        below: a FRESH binding in the CURRENT frame must then correctly
        shadow it, so a call through the shadowed name is NOT checked
        against the outer fact."""
        return [n for n in self.outer_visible_names() if self.resolve_param_call_fact(n) is not None]

    def known_return_param_names(self):
        """Names currently visible (any frame) with a recorded, non-None
        `return_param_scopes` fact — a NAMED fn or `let`-bound anonymous
        fn whose body's own tail directly returns one of its own params.
        Candidates for `_stmt_let_call_return_param_passthrough`/`_stmt_
        call_return_param_passthrough_chain` below, the two statements
        that actually exercise `_resolve_return_param_passthrough`'s own
        verdict."""
        return [n for scope in self.return_param_scopes for n, f in scope.items() if f is not None]

    def current_fn_own_params(self):
        """The param names of the CURRENTLY-open innermost fn (NAMED or
        anonymous) being generated, straight off `current_fn_params_frame_
        stack[-1]` — candidates for `_stmt_call_own_param` below, the
        statement that actually populates `direct_param_calls_stack` (a fn
        body can only ever be OBSERVED to call one of its own params
        directly if something inside it actually does)."""
        if not self.current_fn_params_frame_stack:
            return []
        return list(self.current_fn_params_frame_stack[-1].keys())

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
        # v0.14.9 (round 305): mirrors `_check_effect_call`'s own
        # unconditional param-tracking step, which runs BEFORE (and
        # regardless of) the ordinary tag branch below for every call whose
        # callee is a bare NameRef — real `_check_effect_call` does this
        # for EVERY such call, not just ones this oracle specifically
        # targets at a tracked fn (see `_track_direct_param_call`'s own
        # docstring for why this is a safe no-op for the other callers of
        # this method).
        self._track_direct_param_call(name)
        self.check_effect(self.resolve_alias(name), name)

    def _track_direct_param_call(self, name):
        """Mirror of `_check_effect_call`'s v0.14.9 addition: if `name`
        resolves (innermost-first) to the SAME frame object currently on
        top of `current_fn_params_frame_stack` — i.e. `name` is one of the
        CURRENTLY-open fn's own params, not a nested block's/fn's own
        shadow of that name — record that this fn's body calls it
        directly. A no-op whenever `name` is a builtin, a tracked alias, or
        any other name that never resolves to the top params frame — which
        is every existing caller of `record_call_direct` except this
        round's own `_stmt_call_own_param`, since no other pool in this
        generator ever draws a bare, untagged param name (a param's own
        alias tag is always `None`, so it can never appear in
        `known_alias_names()`/`EFFECTFUL` — the pools every OTHER caller of
        `record_call_direct` draws from)."""
        if not self.current_fn_params_frame_stack:
            return
        owning_frame = self._innermost_frame_containing(name)
        if owning_frame is self.current_fn_params_frame_stack[-1]:
            self.direct_param_calls_stack[-1].add(name)
        else:
            # v0.14.11 (round 306): not the param itself directly, but
            # perhaps a `let`-renamed alias of it (one or more hops, within
            # this same fn body) — mirror of `_check_effect_call`'s own
            # v0.14.11 addition. Recorded under the ORIGINAL param name
            # (what `resolve_param_alias` returns), not `name` itself,
            # since `direct_param_calls_stack`/`param_call_scopes` are
            # keyed by the fn's own declared param names.
            aliased_param = self.resolve_param_alias(name)
            if aliased_param is not None:
                self.direct_param_calls_stack[-1].add(aliased_param)

    def check_call_site_param_effects(self, callee_name, arg_infos):
        """Mirror of `Parser._check_call_site_param_effects`: `arg_infos`
        is a list of `(is_nameref, name_or_None)` pairs, one per positional
        argument, matching `args[i].__class__ is A.NameRef` in the real
        parser — this oracle never constructs an actual AST, so the
        generator itself records whether each argument text it emitted was
        a bare name. A no-op if a violation was ALREADY found by the
        ordinary `_check_effect_call`-mirroring step (`record_call_direct`)
        on this SAME call — exactly mirroring `postfix()`'s own sequencing
        (`_check_effect_call` raises and `_check_call_site_param_effects`
        is simply never reached), via the same `self.done` latch every
        other `record_*` method already checks first."""
        if self.done:
            return
        fact = self.resolve_param_call_fact(callee_name)
        if fact is None:
            return
        effects_scope, params, called_params = fact
        for i, pname in enumerate(params):
            if i >= len(arg_infos) or pname not in called_params:
                continue
            is_nameref, argname = arg_infos[i]
            if not is_nameref:
                continue
            tag = self.resolve_alias(argname)
            if tag is None:
                continue
            if effects_scope is None or tag in effects_scope:
                continue
            self.done = True
            self.verdict = ("error_param", argname, tag, callee_name, pname)
            return

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

    def record_call_field_return_chain(self, boxname, field):
        """Models `boxname.field()(...)` — TWO applications, exactly
        mirroring `record_call_return_chain` but for the field-access
        case: `postfix()`'s loop runs `_check_effect_call` once per `(`
        it consumes, left to right. The FIRST `(` (closing `boxname.field`
        into a `Call`) checks `boxname.field` itself as an ordinary
        FieldAccess callee — v0.14.4's `_resolve_effectful_field` — via
        `record_call_field` below. Only if that doesn't already raise does
        the SECOND `(` (the call-result application) run its own check,
        this time through `_resolve_effectful_field_return` — v0.14.6's
        new branch in `_check_effect_call`. A bare `check_effect(self.
        resolve_field_return(...))` alone would silently skip the first
        check, which is unobservable for a field drawn from `known_field_
        return_names()`'s own callers (never also a direct field alias —
        the two dicts are built from disjoint concerns per field) but
        wrong for the wider `any_field_return_carrier_names()` pool."""
        self.record_call_field(boxname, field)
        if self.done:
            return
        self.check_effect(self.resolve_field_return(boxname, field),
                           "%s.%s()" % (boxname, field))

    def record_call_field_nested(self, boxname, outer_field, inner_field):
        """Models `boxname.outer_field.inner_field(...)` — v0.14.7's
        NESTED field call. Unlike `record_call_field_return_chain`, this
        is a SINGLE check, not a two-application chain: round 288/289's
        own `_check_effect_call` docstring/verification confirmed the
        v0.14.7 branch (`callee.obj.__class__ is A.FieldAccess and
        callee.obj.obj.__class__ is A.NameRef`) is mutually exclusive with
        every other branch by construction (a `FieldAccess` callee whose
        own `.obj` is itself a `FieldAccess` can never also match the
        v0.14.4 branch's `callee.obj.__class__ is A.NameRef` guard), and
        `postfix()` only calls `_check_effect_call` once per `(` — there
        is exactly one `(` in `outer.box.run(...)`, so exactly one check
        fires, unlike `box.field()(...)`'s two."""
        self.check_effect(self.resolve_field_nested(boxname, outer_field, inner_field),
                           "%s.%s.%s" % (boxname, outer_field, inner_field))

    def bind(self, name, alias_tag, return_tag, field_dict, field_return_dict,
             nested_field_dict, param_call_fact=None, param_alias_target=None,
             return_param_fact=None):
        self.alias_scopes[-1][name] = alias_tag
        self.return_alias_scopes[-1][name] = return_tag
        self.field_alias_scopes[-1][name] = field_dict
        self.field_return_alias_scopes[-1][name] = field_return_dict
        self.nested_field_alias_scopes[-1][name] = nested_field_dict
        self.param_call_scopes[-1][name] = param_call_fact
        self.param_alias_scopes[-1][name] = param_alias_target
        self.return_param_scopes[-1][name] = return_param_fact

    # -- generation -------------------------------------------------
    _EXPR_MARK = "\x00EXPR\x00"

    def _mk_expr(self, text):
        return self._EXPR_MARK + text

    def _strip_marks(self, lines):
        return [l[len(self._EXPR_MARK):] if l.startswith(self._EXPR_MARK) else l
                for l in lines]

    def gen_program(self):
        lines, _, _ = self.gen_frame(0, self.r.randint(min(3, self.max_stmts), max(3, self.max_stmts)),
                                      is_block_body=False)
        lines = self._strip_marks(lines)
        return "\n".join(lines) + "\n", self.verdict

    def gen_frame(self, depth, n, is_block_body):
        """One `stmt_list` frame: pushes/pops all stacks together. If
        `is_block_body` (a real `{...}` block, per `block()`'s own "must
        end with an expression" rule), the FINAL slot is always an
        expression statement and its resolved tail tag/tail param name are
        returned as the second/third values — mirroring `stmt_list`'s own
        `(stmts, tail_alias_tag, tail_param_name)`."""
        self.alias_scopes.append({})
        self.return_alias_scopes.append({})
        self.field_alias_scopes.append({})
        self.field_return_alias_scopes.append({})
        self.nested_field_alias_scopes.append({})
        self.param_call_scopes.append({})
        self.param_alias_scopes.append({})
        self.return_param_scopes.append({})
        try:
            lines = []
            tail_tag = None
            tail_param = None
            produced_tail = False
            budget = max(n, 1)
            while budget > 0:
                budget -= 1
                is_last_slot = (budget == 0)
                if self.done and not is_last_slot and self.r.random() < 0.7:
                    break
                if is_block_body and is_last_slot:
                    line, tail_tag, tail_param = self.gen_tail_stmt(depth)
                    lines.append(line)
                    produced_tail = True
                else:
                    lines.append(self.gen_one_stmt(depth))
            if is_block_body and not produced_tail:
                line, tail_tag, tail_param = self.gen_tail_stmt(depth)
                lines.append(line)
            elif not is_block_body and not lines:
                lines.append(self.gen_one_stmt(depth))
            return (lines, (tail_tag if is_block_body else None),
                    (tail_param if is_block_body else None))
        finally:
            self.alias_scopes.pop()
            self.return_alias_scopes.pop()
            self.field_alias_scopes.pop()
            self.field_return_alias_scopes.pop()
            self.nested_field_alias_scopes.pop()
            self.param_call_scopes.pop()
            self.param_alias_scopes.pop()
            self.return_param_scopes.pop()

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
            return (self._mk_expr(name), self.resolve_alias(name),
                    self._resolve_param_identity_then_alias(name))
        if kind == "if_tail":
            # v0.14.12: an `if`/`else` tail is deliberately NOT widened
            # here, exactly as `_tail_return_param_name` documents itself —
            # `tail_param_name` is `None` for every shape but a bare
            # NameRef, unlike `tail_alias_tag` itself (v0.14.5's own
            # widening was specific to the alias-tag mechanism only).
            src, tag = self._gen_if_tail_inner(depth)
            return self._mk_expr(src), tag, None
        line, tag = self.gen_plain_tail_expr()
        return line, tag, None

    def _gen_if_tail_inner(self, depth):
        """Mirror of `_if_tail_alias_tag`: builds `if C {..} else {..}`,
        recursing into an `else if` chain, and combines tags requiring an
        EXACT match across every arm (an approximate match would be
        unsound — see `_if_tail_alias_tag`'s own docstring). Each arm's own
        `tail_param_name` (v0.14.12) is deliberately discarded here — it is
        never combined across arms, exactly as `stmt_list`'s own docstring
        says only a bare-NameRef tail (not an `if`) ever yields one."""
        r = self.r
        cond = self.gen_cond()
        then_lines, then_tag, _ = self.gen_frame(depth + 1, r.randint(1, self.max_stmts), True)
        then_src = "{ " + "\n    ".join(self._strip_marks(then_lines)) + " }"
        if depth + 2 < self.max_depth and r.random() < 0.35:
            else_src, else_tag = self._gen_if_tail_inner(depth + 1)
        else:
            else_lines, else_tag, _ = self.gen_frame(depth + 1, r.randint(1, self.max_stmts), True)
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
        if choice < 0.2 and aliases:
            name = r.choice(aliases)
            self.record_call_direct(name)
            return self._mk_expr("%s(0)" % name), None
        if choice < 0.35:
            builtin, call_text = self._random_effectful_builtin()
            self.record_call_direct(builtin)
            return self._mk_expr(call_text), None
        if choice < 0.45 and returns:
            fname = r.choice(returns)
            self.record_call_return_chain(fname)
            return self._mk_expr("%s()(0)" % fname), None
        carriers = self.any_return_carrier_names()
        if choice < 0.55 and carriers:
            fname = r.choice(carriers)
            self.record_call_return_chain(fname)
            return self._mk_expr("%s()(0)" % fname), None
        if choice < 0.65 and fields:
            boxname, field = r.choice(fields)
            self.record_call_field(boxname, field)
            return self._mk_expr("%s.%s(0)" % (boxname, field)), None
        field_returns = self.known_field_return_names()
        if choice < 0.75 and field_returns:
            boxname, field = r.choice(field_returns)
            self.record_call_field_return_chain(boxname, field)
            return self._mk_expr("%s.%s()(0)" % (boxname, field)), None
        field_return_carriers = self.any_field_return_carrier_names()
        if choice < 0.85 and field_return_carriers:
            boxname, field = r.choice(field_return_carriers)
            self.record_call_field_return_chain(boxname, field)
            return self._mk_expr("%s.%s()(0)" % (boxname, field)), None
        nested_fields = self.known_nested_field_names()
        if choice < 0.92 and nested_fields:
            boxname, outer_field, inner_field = r.choice(nested_fields)
            self.record_call_field_nested(boxname, outer_field, inner_field)
            return self._mk_expr("%s.%s.%s(0)" % (boxname, outer_field, inner_field)), None
        nested_field_carriers = self.any_nested_field_carrier_names()
        if choice < 0.97 and nested_field_carriers:
            boxname, outer_field, inner_field = r.choice(nested_field_carriers)
            self.record_call_field_nested(boxname, outer_field, inner_field)
            return self._mk_expr("%s.%s.%s(0)" % (boxname, outer_field, inner_field)), None
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
        if self.known_field_return_names():
            choices += ["call_field_return_chain"] * 3
        if self.any_field_return_carrier_names():
            choices += ["call_field_return_chain_any"] * 3
        if self.known_nested_field_names():
            choices += ["call_field_nested"] * 3
        if self.any_nested_field_carrier_names():
            choices += ["call_field_nested_any"] * 3
        if self.outer_visible_names():
            choices += ["shadow_let"]
        if self.outer_field_return_box_pairs():
            choices += ["shadow_box_call_field_return"] * 4
        if self.outer_nested_field_box_triples():
            choices += ["shadow_box_call_field_nested"] * 4
        if self.known_param_call_names():
            choices += ["call_tracked_fn"] * 3
            choices += ["let_rename_tracked"]
        if self.outer_param_call_names():
            choices += ["shadow_tracked_fn_call"] * 2
        if self.current_fn_own_params():
            choices += ["call_own_param"] * 2
            choices += ["let_rename_own_param"] * 2
        if self.known_return_param_names():
            choices += ["let_call_return_param_passthrough"] * 3
            choices += ["call_return_param_passthrough_chain"] * 3
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
        builtin, _ = self._random_effectful_builtin()
        self.bind(name, EFFECTFUL.get(builtin), None, None, None, None)
        return "let %s = %s" % (name, builtin)

    def _stmt_let_alias_chain(self, depth):
        # NameRef RHS (`Parser.statement`, ~line 234): copies BOTH the
        # alias tag AND the return tag forward under the new name — but
        # NOT any of the three field dicts (parser lines 254-255/359: all
        # explicitly reset to None for a rename, same as every other
        # non-RecordLit RHS shape). v0.14.9 (round 305): also copies the
        # param-call fact forward — in practice always `None` here (`src`
        # is drawn from `known_alias_names()`, and a fn name's own alias
        # tag is always `None`, so it can never ALSO appear in that pool),
        # but included for fidelity; `_stmt_let_rename_tracked` below is
        # the statement that actually exercises a NON-None carry-forward.
        src = self.r.choice(self.known_alias_names())
        name = self.fresh("a")
        self.bind(name, self.resolve_alias(src), self.resolve_return(src), None, None, None,
                  self.resolve_param_call_fact(src),
                  self._resolve_param_identity_then_alias(src),
                  self.resolve_return_param_fact(src))
        return "let %s = %s" % (name, src)

    def _stmt_let_rename_tracked(self, depth):
        """`let h = g` where `g` is itself a tracked NAMED/anonymous fn
        (`known_param_call_names()`) — the fuzz-able form of `tests/
        test_v14.py`'s `test_renamed_fn_carries_its_param_call_fact_
        forward`/`test_anon_fn_bound_by_let_param_call_fact_carries_
        through_a_rename`: `h` carries `g`'s own recorded param-call fact
        forward (along with its alias/return facts, same NameRef-RHS
        branch as `_stmt_let_alias_chain` above), so a LATER call through
        `h` is checked exactly as one through `g` would be."""
        src = self.r.choice(self.known_param_call_names())
        name = self.fresh("a")
        self.bind(name, self.resolve_alias(src), self.resolve_return(src), None, None, None,
                  self.resolve_param_call_fact(src),
                  self._resolve_param_identity_then_alias(src),
                  self.resolve_return_param_fact(src))
        return "let %s = %s" % (name, src)

    def _stmt_let_call_return(self, depth):
        # `let a = get()` where `get` is a tracked return-carrier
        # (~line 237-244): `a` becomes an ordinary alias of whatever tag
        # `get` was tracked to return; NOT itself a return-carrier.
        fname = self.r.choice(self.known_return_names())
        name = self.fresh("a")
        self.bind(name, self.resolve_return(fname), None, None, None, None)
        return "let %s = %s()" % (name, fname)

    def _stmt_let_fn_expr(self, depth):
        # `let g = fn(...) {...}` (~line 245-252): `g` is a callable, not
        # itself an effectful value; its return fact is the body's tail.
        # v0.14.10 (round 305): also records `g`'s own param-call fact —
        # `primary()`'s anonymous-`fn` branch has no NAME yet to key
        # `param_call_scopes` by while the body is open, so the real
        # parser carries it on the `A.FnExpr` node itself
        # (`param_call_fact`) and this `let` is the first point that reads
        # it back off; this oracle mirrors that by simply computing the
        # SAME fact locally (own_effects_scope/params/called_params) the
        # instant the body finishes, since it never builds an actual node.
        name = self.fresh("g")
        n_params = self.r.randint(0, 2)
        params = [self.fresh("p") for _ in range(n_params)]
        own_spec = self.r.choice(EFFECT_TAG_SETS)
        own_effects_scope = self.resolve_effects_scope(own_spec)
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
        self.current_fn_params_frame_stack.append(params_alias_frame)
        self.direct_param_calls_stack.append(set())
        try:
            body_lines, body_tag, body_tail_param = self.gen_frame(
                depth + 1, self.r.randint(1, self.max_stmts), True)
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
        effects_txt = "" if own_spec is None else " effects [%s]" % ", ".join(sorted(own_spec))
        header = "fn(%s)%s {" % (", ".join(params), effects_txt)
        src = header + "\n  " + "\n  ".join(self._strip_marks(body_lines)) + "\n}"
        param_call_fact = (
            (own_effects_scope, tuple(params), frozenset(called_params))
            if called_params else None)
        # v0.14.12: an anonymous fn has no name to key `return_param_scopes`
        # by until THIS `let` gives it one — mirrors `param_call_fact` just
        # above, sourced from the body's own already-resolved tail-param
        # fact instead of a scope-stack lookup.
        return_param_fact = (tuple(params), body_tail_param) if body_tail_param else None
        self.bind(name, None, body_tag, None, None, None, param_call_fact,
                  None, return_param_fact)
        return "let %s = %s" % (name, src)

    def _gen_nested_record_fields(self):
        """Build 1-2 inner fields for a NESTED record literal (`@{g1:
        <src>, ...}`) used as an OUTER record-literal field's own VALUE
        (`let outer = @{box: @{g1: <src>}}`) — v0.14.7. Mirrors
        `_stmt_let_record`'s own field loop, but only ever resolves
        through `resolve_alias`: the real parser's `nested_field_alias_
        scopes` construction (parser.py's `let`-branch v0.14.7 comment)
        keys the inner dict via `self._resolve_effectful_alias(inner_
        fexpr.name)` ONLY — unlike the outer `field_alias_scopes`/
        `field_return_alias_scopes` pair, there is no second `resolve_
        return`-based dict at the inner level."""
        r = self.r
        aliases = self.known_alias_names()
        pool = self.any_visible_name()
        parts = []
        inner_dict = {}
        for i in range(1, r.randint(1, 2) + 1):
            gname = "g%d" % i
            src_name = None
            if aliases and r.random() < 0.6:
                src_name = r.choice(aliases)
            elif pool and r.random() < 0.5:
                src_name = r.choice(pool)
            if src_name is not None:
                parts.append("%s: %s" % (gname, src_name))
                inner_dict[gname] = self.resolve_alias(src_name)
            else:
                parts.append("%s: %d" % (gname, r.randint(0, 9)))
        return parts, inner_dict

    def _stmt_let_record(self, depth):
        # `let box = @{f1: name1, f2: 5, ...}` (~line 253-270): only
        # bare-NameRef field VALUES are tracked; other field shapes are
        # simply absent from the dict (not recorded as None). v0.14.6
        # (~line 295-306): `field_dict`/`field_return_dict` are built from
        # the EXACT same set of bare-NameRef field values, just resolved
        # through `resolve_alias`/`resolve_return` respectively — never a
        # different key set between the two dicts. v0.14.7 (~line 335-353):
        # a THIRD dict, `nested_field_dict`, keyed only on fields whose OWN
        # value is ANOTHER record literal — mutually exclusive with the
        # other two by AST construction (a field's value is either a bare
        # NameRef or a RecordLit, never both), so this branch `continue`s
        # past the NameRef-only logic below rather than composing with it.
        r = self.r
        name = self.fresh("box")
        pool = self.any_visible_name()
        aliases = self.known_alias_names()
        returns = self.known_return_names()
        parts = []
        field_dict = {}
        field_return_dict = {}
        nested_field_dict = {}
        for i in range(1, r.randint(1, 3) + 1):
            fname = "f%d" % i
            if r.random() < 0.35:
                inner_parts, inner_dict = self._gen_nested_record_fields()
                parts.append("%s: @{%s}" % (fname, ", ".join(inner_parts)))
                nested_field_dict[fname] = inner_dict
                continue
            src_name = None
            # `returns` checked FIRST and with a high draw probability:
            # `known_return_names()` non-empty at all is already rare
            # (measured ~0.7% of `_stmt_let_record` calls this round —
            # needs an earlier fn/closure whose tail happens to resolve a
            # real return tag), so once available it should be taken, or
            # the field-return-carrier shape (the whole point of this
            # statement, v0.14.6) would almost never get generated at all.
            if returns and r.random() < 0.85:
                src_name = r.choice(returns)
            elif aliases and r.random() < 0.4:
                src_name = r.choice(aliases)
            elif pool and r.random() < 0.7:
                src_name = r.choice(pool)
            if src_name is not None:
                parts.append("%s: %s" % (fname, src_name))
                field_dict[fname] = self.resolve_alias(src_name)
                field_return_dict[fname] = self.resolve_return(src_name)
            else:
                parts.append("%s: %d" % (fname, r.randint(0, 9)))
        self.bind(name, None, None, field_dict, field_return_dict, nested_field_dict)
        return "let %s = @{%s}" % (name, ", ".join(parts))

    def _stmt_let_plain(self, depth):
        name = self.fresh("v")
        self.bind(name, None, None, None, None, None)
        return "let %s = %d" % (name, self.r.randint(0, 9))

    def _stmt_shadow_let(self, depth):
        name = self.r.choice(self.outer_visible_names())
        self.bind(name, None, None, None, None, None)
        return "let %s = %d" % (name, self.r.randint(0, 9))

    def _stmt_call(self, depth):
        builtin, call_text = self._random_effectful_builtin()
        self.record_call_direct(builtin)
        return self._mk_expr(call_text)

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

    def _stmt_call_field_return_chain(self, depth):
        boxname, field = self.r.choice(self.known_field_return_names())
        self.record_call_field_return_chain(boxname, field)
        return self._mk_expr("%s.%s()(0)" % (boxname, field))

    def _stmt_call_field_return_chain_any(self, depth):
        boxname, field = self.r.choice(self.any_field_return_carrier_names())
        self.record_call_field_return_chain(boxname, field)
        return self._mk_expr("%s.%s()(0)" % (boxname, field))

    def _stmt_call_field_nested(self, depth):
        boxname, outer_field, inner_field = self.r.choice(self.known_nested_field_names())
        self.record_call_field_nested(boxname, outer_field, inner_field)
        return self._mk_expr("%s.%s.%s(0)" % (boxname, outer_field, inner_field))

    def _stmt_call_field_nested_any(self, depth):
        boxname, outer_field, inner_field = self.r.choice(self.any_nested_field_carrier_names())
        self.record_call_field_nested(boxname, outer_field, inner_field)
        return self._mk_expr("%s.%s.%s(0)" % (boxname, outer_field, inner_field))

    def _stmt_shadow_box_call_field_return(self, depth):
        """Deliberately targets `resolve_field_return`'s (and the real
        `_resolve_effectful_field_return`'s) shadowing edge: shadow an
        OUTER box that carries a real field-return-carrier field with a
        fresh all-None binding in THIS frame, then immediately call
        `box.field()(...)` through that SAME name — first-frame-wins must
        resolve the fresh (always-None) shadow, never fall through to the
        outer box's real fact. Packs the `let`-shadow and the follow-up
        call into ONE statement slot (two program lines) so the scenario
        is reliably reachable — see `outer_field_return_box_pairs`'s own
        docstring for why leaving this to chance (a generic `shadow_let`
        happening to pick this exact box, AND a later independent
        statement happening to call through it) is impractically rare.

        Biased 80-of-the-time toward a pair whose OUTER (about-to-be-
        shadowed) tag actually resolves non-None: `outer_field_return_
        box_pairs()` itself is unfiltered (any tag value, matching the
        `any_...` convention elsewhere), but a shadow-then-fallthrough bug
        is only OBSERVABLE when the outer fact being wrongly recovered is
        a real tag — shadowing a field whose own correct value is already
        None makes the buggy and correct resolutions agree by coincidence.
        Still leaves 20% on the unfiltered pool so the None/None case
        (correctness, not just bug-detection) stays covered too."""
        r = self.r
        pairs = self.outer_field_return_box_pairs()
        real_pairs = [(n, f) for (n, f) in pairs if self.resolve_field_return(n, f) is not None]
        name, field = (r.choice(real_pairs) if real_pairs and r.random() < 0.8
                       else r.choice(pairs))
        self.bind(name, None, None, None, None, None)
        self.record_call_field_return_chain(name, field)
        return self._mk_expr("let %s = %d\n%s.%s()(0)" % (name, r.randint(0, 9), name, field))

    def _stmt_shadow_box_call_field_nested(self, depth):
        """v0.14.7 analogue of `_stmt_shadow_box_call_field_return`:
        shadow an OUTER box that carries a real nested-field-carrier slot
        with a fresh all-None binding in THIS frame, then immediately call
        `box.outer_field.inner_field(...)` through that SAME name —
        first-frame-wins must resolve the fresh shadow, never fall through
        to the outer box's real fact. Same 80/20 real-tag bias and same
        one-slot-packs-two-lines shape as that statement, for the same
        compound-rarity reason (see `outer_nested_field_box_triples`'s own
        docstring)."""
        r = self.r
        triples = self.outer_nested_field_box_triples()
        real_triples = [(n, of, iff) for (n, of, iff) in triples
                         if self.resolve_field_nested(n, of, iff) is not None]
        name, outer_field, inner_field = (r.choice(real_triples)
                                           if real_triples and r.random() < 0.8
                                           else r.choice(triples))
        self.bind(name, None, None, None, None, None)
        self.record_call_field_nested(name, outer_field, inner_field)
        return self._mk_expr("let %s = %d\n%s.%s.%s(0)" %
                              (name, r.randint(0, 9), name, outer_field, inner_field))

    def _stmt_nested_block(self, depth):
        name = self.fresh("blk")
        inner_lines, _, _ = self.gen_frame(depth + 1, self.r.randint(1, 3), True)
        body = "{ " + "\n    ".join(self._strip_marks(inner_lines)) + " }"
        self.bind(name, None, None, None, None, None)
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
            self.bind(name, None, None, None, None, None, None, None, None)
        else:
            self.alias_scopes[-1][name] = None
            self.return_alias_scopes[-1][name] = None
            self.field_alias_scopes[-1][name] = None
            self.field_return_alias_scopes[-1][name] = None
            self.nested_field_alias_scopes[-1][name] = None
            self.param_call_scopes[-1][name] = None
            self.param_alias_scopes[-1][name] = None
            self.return_param_scopes[-1][name] = None
        params = [self.fresh("p") for _ in range(r.randint(0, 2))]
        own_spec = r.choice(EFFECT_TAG_SETS)
        own_effects_scope = self.resolve_effects_scope(own_spec)
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
        self.current_fn_params_frame_stack.append(params_alias_frame)
        self.direct_param_calls_stack.append(set())
        try:
            body_lines, body_tag, body_tail_param = self.gen_frame(
                depth + 1, r.randint(1, self.max_stmts), True)
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
        self.return_alias_scopes[-1][name] = body_tag
        self.param_call_scopes[-1][name] = (
            (own_effects_scope, tuple(params), frozenset(called_params))
            if called_params else None)
        self.return_param_scopes[-1][name] = (
            (tuple(params), body_tail_param) if body_tail_param else None)
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
        self.field_return_alias_scopes[-1][name] = None
        self.nested_field_alias_scopes[-1][name] = None
        self.param_call_scopes[-1][name] = None
        self.param_alias_scopes[-1][name] = None
        self.return_param_scopes[-1][name] = None
        own_spec = r.choice(EFFECT_TAG_SETS)
        own_effects_scope = self.resolve_effects_scope(own_spec)
        self.effects_stack.append(own_effects_scope)
        # v0.14.9 (round 305): `shadow_name` is now `name`'s own SOLE
        # param — `current_fn_own_params()`/`_stmt_call_own_param` can
        # therefore reach it (calling a param that happens to reuse an
        # outer tracked name), and if the body does, `name` ITSELF becomes
        # a genuine param-call-tracked fn — exactly `test_param_named_
        # like_a_tracked_fn_shadows_its_param_call_fact`'s shape, reachable
        # under fuzzing instead of only hand-written.
        params_alias_frame = {shadow_name: None}
        self.alias_scopes.append(params_alias_frame)
        self.return_alias_scopes.append({shadow_name: None})
        self.field_alias_scopes.append({shadow_name: None})
        self.field_return_alias_scopes.append({shadow_name: None})
        self.nested_field_alias_scopes.append({shadow_name: None})
        self.param_call_scopes.append({shadow_name: None})
        self.param_alias_scopes.append({})
        self.return_param_scopes.append({shadow_name: None})
        self.current_fn_params_frame_stack.append(params_alias_frame)
        self.direct_param_calls_stack.append(set())
        try:
            body_lines, body_tag, body_tail_param = self.gen_frame(
                depth + 1, r.randint(1, self.max_stmts), True)
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
        self.return_alias_scopes[-1][name] = body_tag
        self.param_call_scopes[-1][name] = (
            (own_effects_scope, (shadow_name,), frozenset(called_params))
            if called_params else None)
        self.return_param_scopes[-1][name] = (
            ((shadow_name,), body_tail_param) if body_tail_param else None)
        effects_txt = "" if own_spec is None else " effects [%s]" % ", ".join(sorted(own_spec))
        header = "fn %s(%s)%s {" % (name, shadow_name, effects_txt)
        return header + "\n  " + "\n  ".join(self._strip_marks(body_lines)) + "\n}"

    def _stmt_call_own_param(self, depth):
        """Calls one of the CURRENTLY-open fn's own params directly
        (`paramname(0)`) — the statement that actually populates
        `direct_param_calls_stack`, since no other statement in this
        generator ever draws a bare, untagged param name (see
        `_track_direct_param_call`'s own docstring)."""
        name = self.r.choice(self.current_fn_own_params())
        self.record_call_direct(name)
        return self._mk_expr("%s(0)" % name)

    def _stmt_let_rename_own_param(self, depth):
        """v0.14.11 (round 306): `let g = p` where `p` is one of the
        CURRENTLY-open fn's own params — the ONLY statement in this
        generator that ever draws a bare, untagged param name as a `let`
        RHS (every other pool only ever contains TAGGED names — see
        `_track_direct_param_call`'s own docstring), so it is the sole
        producer of a non-None `param_alias_scopes` entry. Immediately
        follows with a call through the new name (`g(0)`), and 40% of the
        time a SECOND rename hop (`let h = g` then `h(0)` instead of `g(0)`)
        — exercising `resolve_param_alias`'s own multi-hop chaining. Packed
        into one statement slot (multiple program lines), the same
        "no other pool would ever hand back a bare param name by chance"
        compound-rarity reasoning `_stmt_shadow_box_call_field_return`'s
        own docstring already gives for its family of statements — this is
        the ONLY route to a non-None `param_alias_scopes` entry, so leaving
        it to a generic `let_plain`/`let_alias_chain` statement stumbling
        onto a param name would never happen at all."""
        r = self.r
        pname = r.choice(self.current_fn_own_params())
        name = self.fresh("a")
        target = self._resolve_param_identity_then_alias(pname)
        self.bind(name, None, None, None, None, None, None, target, None)
        lines = ["let %s = %s" % (name, pname)]
        call_name = name
        if r.random() < 0.4:
            name2 = self.fresh("a")
            target2 = self._resolve_param_identity_then_alias(call_name)
            self.bind(name2, None, None, None, None, None, None, target2, None)
            lines.append("let %s = %s" % (name2, call_name))
            call_name = name2
        self.record_call_direct(call_name)
        lines.append("%s(0)" % call_name)
        return self._mk_expr("\n".join(lines))

    def _stmt_let_call_return_param_passthrough(self, depth):
        """v0.14.12 (round 308): `let g = apply(print)` where `apply` is a
        tracked "returns one of its own params directly" fn
        (`known_return_param_names()`) — 70% of the time the ARGUMENT at
        the returned param's own position is an effectful builtin/alias
        (so both the tag-flows-through and tag-stays-None paths of
        `resolve_return_param_passthrough` get real coverage), the rest a
        plain literal. `g` becomes an ordinary tracked alias afterward
        (mirrors `statement()`'s own `A.Call` `let`-branch), immediately
        followed by a call through it (`g(0)`) so the resulting tag is
        actually OBSERVABLE — packed into one statement slot, same
        let-then-call pattern `_stmt_let_rename_own_param` above uses for
        the identical reachability reason. `resolve_return(fname)` is
        always None for a fn drawn from this pool (its tail is a bare
        PARAM name, never itself an alias — see `resolve_alias`'s own
        `EFFECTFUL`/scope walk, which never tags a param), so the
        passthrough fallback is unconditionally exercised here, exactly
        the branch order `statement()`'s own `A.Call` handling uses.

        Genuine bug this exact statement caught before it ever reached a
        campaign: parsing `fname(ARGS)` as an EXPRESSION always runs
        `postfix()`'s own ORDINARY per-`(` checks first — the direct-call
        check plus `_check_call_site_param_effects` — regardless of where
        the resulting `Call` node ends up (a `let` RHS here); a `let`-
        bound-fn drawn from `known_return_param_names()` can ALSO
        independently carry its OWN `param_call_scopes` fact (its body
        both calls a param directly AND tail-returns one, not mutually
        exclusive), so skipping straight to the return/passthrough tag
        computation missed a call site where THAT check fires first. Fixed
        by running the same two-step ordinary-call sequence `_stmt_call_
        return_param_passthrough_chain` below already used, before ever
        touching `resolve_return`/`resolve_return_param_passthrough`."""
        r = self.r
        fname = r.choice(self.known_return_param_names())
        fact = self.resolve_return_param_fact(fname)
        if fact is None:
            # `known_return_param_names()` is a raw multi-frame scan (same
            # convention as `known_return_names()` etc.) — a CLOSER frame
            # may since have shadowed this exact name with a fresh `None`
            # fact; re-resolve rather than trust the pool, same fallback
            # `_stmt_call_tracked_fn`'s own docstring already explains.
            self.record_call_direct(fname)
            return self._mk_expr("%s(0)" % fname)
        params_tuple, tail_param_name = fact
        idx = params_tuple.index(tail_param_name)
        args = []
        arg_infos = []
        for i in range(len(params_tuple)):
            if i == idx and r.random() < 0.7:
                builtin, _ = self._random_effectful_builtin()
                args.append(builtin)
                arg_infos.append((True, builtin))
            else:
                args.append(str(r.randint(0, 9)))
                arg_infos.append((False, None))
        self.record_call_direct(fname)
        if not self.done:
            self.check_call_site_param_effects(fname, arg_infos)
        tag = None
        if not self.done:
            tag = self.resolve_return(fname)
            if tag is None:
                tag = self.resolve_return_param_passthrough(fname, arg_infos)
        name = self.fresh("a")
        self.bind(name, tag, None, None, None, None)
        self.record_call_direct(name)
        call_src = "let %s = %s(%s)\n%s(0)" % (name, fname, ", ".join(args), name)
        return self._mk_expr(call_src)

    def _stmt_call_return_param_passthrough_chain(self, depth):
        """v0.14.12 (round 308): `apply(print)(1)` — a chained call with NO
        intermediate `let` at all, mirroring `_check_effect_call`'s own
        `Call`-callee branch. `postfix()` runs its checks left to right at
        each `(`: the FIRST closes `apply(print)` into a `Call` — an
        ordinary direct-call check on `apply` itself (`record_call_direct`,
        almost always a no-op tag-wise since `apply` is never itself an
        alias, but it DOES feed `_track_direct_param_call` in case `apply`
        happens to also be one of an ENCLOSING fn's own params) followed by
        `_check_call_site_param_effects` (a no-op unless `apply` ALSO
        independently carries a `param_call_scopes` fact of its own — a
        genuinely separate, composable mechanism from the one this
        statement targets). Only if NEITHER of those already raised does
        the SECOND `(` run its own check, this time through
        `resolve_return`-then-`resolve_return_param_passthrough` — the
        mechanism actually under test here."""
        r = self.r
        fname = r.choice(self.known_return_param_names())
        fact = self.resolve_return_param_fact(fname)
        if fact is None:
            # Same shadow-fallback reasoning as `_stmt_let_call_return_
            # param_passthrough` above.
            self.record_call_direct(fname)
            return self._mk_expr("%s(0)" % fname)
        params_tuple, tail_param_name = fact
        idx = params_tuple.index(tail_param_name)
        args = []
        arg_infos = []
        for i in range(len(params_tuple)):
            if i == idx and r.random() < 0.7:
                builtin, _ = self._random_effectful_builtin()
                args.append(builtin)
                arg_infos.append((True, builtin))
            else:
                args.append(str(r.randint(0, 9)))
                arg_infos.append((False, None))
        self.record_call_direct(fname)
        if not self.done:
            self.check_call_site_param_effects(fname, arg_infos)
        if not self.done:
            tag = self.resolve_return(fname)
            if tag is None:
                tag = self.resolve_return_param_passthrough(fname, arg_infos)
            self.check_effect(tag, "%s()" % fname)
        return self._mk_expr("%s(%s)(0)" % (fname, ", ".join(args)))

    def _stmt_call_tracked_fn(self, depth):
        """Calls a tracked NAMED/anonymous fn (`known_param_call_names()`)
        with one argument per its own recorded param — for a position the
        fn calls directly, 70% of the time supplies an effectful bare name
        (a builtin, or an existing alias) instead of a plain literal, so
        both the GRANTED and DENIED paths of `_check_call_site_param_
        effects` get real coverage, not just the "never triggers" case.
        The one statement that actually exercises the round 300/302
        feature's own VERDICT correctness — every other addition in this
        round's own diff exists to make ONE of its preconditions
        (a tracked fact existing, a param actually called, a shadow to
        test) reachable at all."""
        r = self.r
        name = r.choice(self.known_param_call_names())
        # `known_param_call_names()` scans every open frame directly (the
        # same "not itself shadow-aware" convention `known_alias_names()`/
        # `known_return_names()` already use) — a CLOSER frame may since
        # have shadowed this exact name with a fresh `None` fact. Re-
        # resolve (innermost-first, the real walk) rather than trust the
        # pool: if shadowed, there is genuinely nothing to check here (the
        # correct, sound outcome), so fall back to an ordinary untracked
        # call, the same way `record_call_direct`/`check_effect` already
        # treat a `None`-resolving name as a safe no-op everywhere else.
        fact = self.resolve_param_call_fact(name)
        if fact is None:
            self.record_call_direct(name)
            return self._mk_expr("%s(0)" % name)
        effects_scope, params, called_params = fact
        args = []
        arg_infos = []
        for i, pname in enumerate(params):
            if pname in called_params and r.random() < 0.7:
                if r.random() < 0.5:
                    builtin, _ = self._random_effectful_builtin()
                    args.append(builtin)
                    arg_infos.append((True, builtin))
                else:
                    aliases = self.known_alias_names()
                    if aliases:
                        aname = r.choice(aliases)
                        args.append(aname)
                        arg_infos.append((True, aname))
                    else:
                        args.append(str(r.randint(0, 9)))
                        arg_infos.append((False, None))
            else:
                args.append(str(r.randint(0, 9)))
                arg_infos.append((False, None))
        self.record_call_direct(name)
        if not self.done:
            self.check_call_site_param_effects(name, arg_infos)
        return self._mk_expr("%s(%s)" % (name, ", ".join(args)))

    def _stmt_shadow_tracked_fn_call(self, depth):
        """Shadow an OUTER tracked fn (real, non-None param-call fact) with
        a fresh all-None rebinding in THIS frame, then immediately call
        `name(...)` through that SAME name — first-frame-wins must resolve
        the fresh (always-None) shadow, never fall through to the outer
        fn's own real fact. Packs the `let`-shadow and the follow-up call
        into ONE statement slot (two program lines), same reason as
        `_stmt_shadow_box_call_field_return`'s own docstring: leaving this
        to chance (a generic `shadow_let` happening to pick this exact
        name, AND a later independent statement happening to call it) is
        impractically rare. Biased toward filling CALLED-param positions
        with an effectful builtin so a resolver bug that leaks past the
        shadow (recovers the outer fact instead of the correct `None`) is
        actually OBSERVABLE as a wrong `error_param` verdict, not silently
        masked by every position happening to be non-effectful."""
        r = self.r
        name = r.choice(self.outer_param_call_names())
        effects_scope, params, called_params = self.resolve_param_call_fact(name)
        args = []
        arg_infos = []
        for pname in params:
            if pname in called_params and r.random() < 0.8:
                builtin, _ = self._random_effectful_builtin()
                args.append(builtin)
                arg_infos.append((True, builtin))
            else:
                args.append(str(r.randint(0, 9)))
                arg_infos.append((False, None))
        self.bind(name, None, None, None, None, None, None)
        self.record_call_direct(name)
        if not self.done:
            self.check_call_site_param_effects(name, arg_infos)
        call_src = "%s(%s)" % (name, ", ".join(args))
        return self._mk_expr("let %s = %d\n%s" % (name, r.randint(0, 9), call_src))


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
    elif expected[0] == "error":
        _, display, tag = expected
        mismatch = not (actual[0] == "error" and
                         ("'%s' requires effect '%s'" % (display, tag)) in actual[1])
    else:
        # v0.14.9/v0.14.10 (round 305): `_check_call_site_param_effects`'s
        # OWN error message shape is deliberately different wording from
        # `_check_effect_call`'s (`Parser._check_call_site_param_effects`'s
        # own docstring), so it needs its own substring match, same
        # discipline as the "error" branch above — a distinguishing
        # PREFIX of the real message, not the full string (the real
        # message's tail, `... is not permitted by 'NAME''s own 'DECLARED'`,
        # is redundant with what this substring already pins down).
        assert expected[0] == "error_param"
        _, arg_name, tag, callee_name, pname = expected
        mismatch = not (actual[0] == "error" and
                         ("argument '%s' (effect '%s') passed to '%s' for parameter '%s'"
                          % (arg_name, tag, callee_name, pname)) in actual[1])
    return src, expected, actual, mismatch
