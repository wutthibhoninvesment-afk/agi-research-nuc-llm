"""Tests for `harness/swe/alias_effects.py` — the targeted differential
oracle for v0.14.2's direct-alias effect tracking (round 269).

Follows `test_swe_guest.py`'s own discipline (see its module docstring):
zero findings on random programs is only evidence if the oracle
demonstrably fires on an injected divergence, so half of this file runs
against a deliberately mutated copy of the real check.
"""
import os
import random
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from swe.alias_effects import (AliasEffectsGen, check_one, _import_parse,
                                ExtendedEffectGen, check_one_ext)
from swe.fuzz import WHENCE_ROOT


# --------------------------------------------------------------- generator --

def test_generator_produces_both_verdicts():
    """A healthy mix of ok/error programs — a generator that only ever
    predicts one verdict would make the campaign below vacuous."""
    oks = errs = 0
    for seed in range(300):
        _, expected = AliasEffectsGen(seed).gen_program()
        if expected[0] == "ok":
            oks += 1
        else:
            errs += 1
    assert oks > 50 and errs > 50, (oks, errs)


def test_generated_programs_are_well_formed_source():
    """Every generated program must at least LEX cleanly and never raise a
    Python exception from the generator itself — a crash here would be a
    generator bug, not a parser finding."""
    parse, ParseError = _import_parse(WHENCE_ROOT)
    for seed in range(300):
        src, _ = AliasEffectsGen(seed).gen_program()
        try:
            parse(src)
        except ParseError:
            pass  # expected outcome for many seeds; only non-ParseError escapes are bugs


# ----------------------------------------------------------- the campaign --

def test_targeted_campaign_no_mismatches():
    """The real regression: run a real batch of generated alias/effects
    programs through the actual `whence.parser.parse` and compare against
    the independent oracle's prediction. 2000 programs across varied
    depth/stmt budgets, seeded for determinism."""
    rng = random.Random(20269)
    mismatches = []
    for _ in range(2000):
        seed = rng.randrange(10 ** 9)
        depth = rng.choice([2, 3, 3, 4, 5])
        stmts = rng.choice([2, 3, 4, 5, 6])
        src, expected, actual, mismatch = check_one(seed, max_depth=depth, max_stmts=stmts)
        if mismatch:
            mismatches.append((seed, depth, stmts, src, expected, actual))
    assert not mismatches, mismatches[:3]


def test_oracle_detects_injected_shadowing_bug():
    """Mutation test: revert `_resolve_effectful_alias`'s None-sentinel
    shadowing behavior (the exact bug class `tiny-language-implementation/
    SKILL.md`'s "alias_scopes" pitfall names — an inner shadow no longer
    blocks fallthrough to an outer alias) and confirm the campaign fires.
    Without this, a clean run of `test_targeted_campaign_no_mismatches`
    would be unfalsifiable evidence."""
    sys.path.insert(0, WHENCE_ROOT)
    from whence import parser as P

    def buggy_resolve(self, name):
        for scope in reversed(self.alias_scopes):
            if name in scope and scope[name] is not None:
                return scope[name]
        return P._EFFECTFUL_BUILTINS.get(name)

    orig = P.Parser._resolve_effectful_alias
    P.Parser._resolve_effectful_alias = buggy_resolve
    try:
        rng = random.Random(42)
        mismatches = 0
        for _ in range(1500):
            seed = rng.randrange(10 ** 9)
            _, _, _, mismatch = check_one(seed, max_depth=4, max_stmts=5)
            mismatches += mismatch
    finally:
        P.Parser._resolve_effectful_alias = orig
    assert mismatches > 0, "mutated shadowing bug went undetected — oracle has no teeth"


# ========================================= v0.14.3/4/5/6 (rounds 281/287) ==
# `ExtendedEffectGen` covers the effect-alias features `AliasEffectsGen`
# doesn't: return-value aliasing (v0.14.3), record-field aliasing (v0.14.4),
# if/else-tail combination (v0.14.5) — round 281 — and, since round 287,
# the field-RETURN chain (v0.14.6, `box.field()(...)` where `box.field` is
# itself a tracked return-carrier) — see `alias_effects.py`'s own module
# comment for why v0.14.3/4/5 needed a genuinely new generator, and its
# `record_call_field_return_chain`/`_stmt_shadow_box_call_field_return`
# docstrings for why v0.14.6 folded into this SAME generator instead of a
# third one.

def test_extended_generator_produces_both_verdicts():
    oks = errs = 0
    for seed in range(300):
        _, expected = ExtendedEffectGen(seed).gen_program()
        if expected[0] == "ok":
            oks += 1
        else:
            errs += 1
    assert oks > 50 and errs > 50, (oks, errs)


def test_extended_generated_programs_are_well_formed_source():
    parse, ParseError = _import_parse(WHENCE_ROOT)
    for seed in range(300):
        src, _ = ExtendedEffectGen(seed).gen_program()
        try:
            parse(src)
        except ParseError:
            pass  # expected for many seeds; only a non-ParseError escape is a bug


def test_extended_generator_reaches_field_return_chain_shape():
    """Round 287: a coverage guard, not a correctness check — confirms the
    v0.14.6 `box.field()(...)` shape (a TWO-application call whose callee
    is a field access) is actually reachable from the generator at a real
    rate, not just theoretically wired up. A future refactor that
    accidentally starved `known_field_return_names()`/`any_field_return_
    carrier_names()` (e.g. by changing `_stmt_let_record`'s draw
    probabilities) would silently make `test_extended_targeted_campaign_
    no_mismatches` below vacuous for this one shape without this guard."""
    pat = re.compile(r"\.\w+\(\)\(")
    hits = 0
    n = 4000
    for seed in range(n):
        src, _ = ExtendedEffectGen(seed, max_depth=4, max_stmts=5).gen_program()
        if pat.search(src):
            hits += 1
    assert hits > n * 0.1, (hits, n)


def test_extended_targeted_campaign_no_mismatches():
    """The real regression: 7000 generated programs spanning return/field/
    if-tail/field-return-chain/nested-field alias shapes (plus their
    interaction with v0.14.2's own direct aliasing) against the real
    parser, compared to the independent oracle's prediction. Bumped from
    round 281's original 3000 to 5000 when round 287 folded the v0.14.6
    field-return-chain shape into this same generator, and to 7000 when
    round 293 folded v0.14.7's nested-field shape in too, to keep
    per-shape sample size comparable."""
    rng = random.Random(281269)
    mismatches = []
    for _ in range(7000):
        seed = rng.randrange(10 ** 9)
        depth = rng.choice([2, 3, 3, 4, 5])
        stmts = rng.choice([2, 3, 4, 5, 6])
        src, expected, actual, mismatch = check_one_ext(seed, max_depth=depth, max_stmts=stmts)
        if mismatch:
            mismatches.append((seed, depth, stmts, src, expected, actual))
    assert not mismatches, mismatches[:3]


def test_extended_oracle_detects_injected_return_alias_shadowing_bug():
    """Mutation test 1/3: revert `_resolve_effectful_return`'s None-sentinel
    shadowing (mirrors `test_oracle_detects_injected_shadowing_bug` above,
    but for the SECOND stack, `return_alias_scopes`)."""
    sys.path.insert(0, WHENCE_ROOT)
    from whence import parser as P

    def buggy_resolve(self, name):
        for scope in reversed(self.return_alias_scopes):
            if name in scope and scope[name] is not None:
                return scope[name]
        return None

    orig = P.Parser._resolve_effectful_return
    P.Parser._resolve_effectful_return = buggy_resolve
    try:
        rng = random.Random(111)
        mismatches = 0
        for _ in range(3000):
            seed = rng.randrange(10 ** 9)
            _, _, _, mismatch = check_one_ext(seed, max_depth=4, max_stmts=5)
            mismatches += mismatch
    finally:
        P.Parser._resolve_effectful_return = orig
    assert mismatches > 0, "mutated return-alias shadowing bug went undetected"


def test_extended_oracle_detects_injected_field_alias_shadowing_bug():
    """Mutation test 2/3: same shadowing-revert bug class, for the THIRD
    stack, `field_alias_scopes`. Rarer to trigger than the other two (needs
    a record-literal name specifically re-shadowed in an inner frame before
    a `.field(...)` call) — uses a larger N (25000) to keep the false-negative
    (flake) rate low: the real per-program hit rate is ~0.03% (6/20000 in
    this round's own manual scaling check), so at N=25000 the expected hit
    count is comfortably >1 and P(zero hits by chance) is negligible."""
    sys.path.insert(0, WHENCE_ROOT)
    from whence import parser as P

    def buggy_resolve(self, name, field):
        for scope in reversed(self.field_alias_scopes):
            if name in scope and scope[name]:
                fields = scope[name]
                v = fields.get(field)
                if v is not None:
                    return v
        return None

    orig = P.Parser._resolve_effectful_field
    P.Parser._resolve_effectful_field = buggy_resolve
    try:
        rng = random.Random(222)
        mismatches = 0
        for _ in range(25000):
            seed = rng.randrange(10 ** 9)
            depth = rng.choice([3, 4, 4, 5, 5])
            stmts = rng.choice([3, 4, 5, 6, 7])
            _, _, _, mismatch = check_one_ext(seed, max_depth=depth, max_stmts=stmts)
            mismatches += mismatch
    finally:
        P.Parser._resolve_effectful_field = orig
    assert mismatches > 0, "mutated field-alias shadowing bug went undetected"


def test_extended_oracle_detects_injected_if_tail_unsound_match_bug():
    """Mutation test 3/3: weaken `_if_tail_alias_tag`'s EXACT-match
    requirement (v0.14.5's own soundness rule — see its docstring) to an
    unsound "then wins if non-None, else ignored" approximation. Only
    observable if something later actually CALLS the mistracked name via
    the return-chain — `ExtendedEffectGen.any_return_carrier_names()`
    (a wider candidate pool than `known_return_names()`, needed
    specifically for this case: a fn whose CORRECT return tag is None
    can never be chosen by the narrower, non-None-filtered pool) is what
    makes this reachable at all; see `record_call_return_chain`'s own
    docstring for why the wider pool in turn needed its own inner-call
    fix (a name in the wide pool can independently be a direct alias,
    not just a return-carrier)."""
    sys.path.insert(0, WHENCE_ROOT)
    from whence import parser as P

    def buggy_if_tail(self, if_node):
        then_tag = if_node.then.tail_alias_tag
        otherwise = if_node.otherwise
        else_tag = (self._if_tail_alias_tag(otherwise)
                    if otherwise.__class__.__name__ == "If"
                    else otherwise.tail_alias_tag)
        return then_tag if then_tag is not None else else_tag

    orig = P.Parser._if_tail_alias_tag
    P.Parser._if_tail_alias_tag = buggy_if_tail
    try:
        rng = random.Random(333)
        mismatches = 0
        for _ in range(3000):
            seed = rng.randrange(10 ** 9)
            depth = rng.choice([3, 4, 4, 5, 5])
            stmts = rng.choice([3, 4, 5, 6, 7])
            _, _, _, mismatch = check_one_ext(seed, max_depth=depth, max_stmts=stmts)
            mismatches += mismatch
    finally:
        P.Parser._if_tail_alias_tag = orig
    assert mismatches > 0, "mutated if-tail unsound-match bug went undetected"


# ==================================================== v0.14.6 (round 287) ==

def test_extended_oracle_detects_injected_field_return_shadowing_bug():
    """Mutation test 4/4: same shadowing-revert bug class as test 2/3
    (`_resolve_effectful_field`'s own None-sentinel shadowing), now for
    `_resolve_effectful_field_return` — v0.14.6's fourth stack,
    `field_return_alias_scopes`. Only observable when a box carrying a
    REAL (non-None) field-return tag in an OUTER frame gets shadowed by an
    all-None rebinding in an INNER frame and then something in that inner
    frame calls THROUGH the shadowed name (`box.field()(...)`) — the buggy
    resolver incorrectly falls through past the falsy inner dict to
    recover the outer frame's real tag. This is a rarer compound event
    than test 2/3's own field-alias case (needs a record field bound
    SPECIFICALLY to a return-carrier name, itself uncommon — see
    `_stmt_let_record`'s own comment on `known_return_names()` being
    non-empty at all only ~0.7% of the time it's called): even with
    `ExtendedEffectGen._stmt_shadow_box_call_field_return` deliberately
    targeting this exact scenario (see its own docstring), the measured
    hit rate this round was ~0.017% (5/30000 in a manual scaling check) —
    N=60000 here for comfortable headroom (~10 expected hits, P(zero hits
    by chance) well under 1%)."""
    sys.path.insert(0, WHENCE_ROOT)
    from whence import parser as P

    def buggy_resolve(self, name, field):
        for scope in reversed(self.field_return_alias_scopes):
            if name in scope and scope[name]:
                fields = scope[name]
                v = fields.get(field)
                if v is not None:
                    return v
        return None

    orig = P.Parser._resolve_effectful_field_return
    P.Parser._resolve_effectful_field_return = buggy_resolve
    try:
        rng = random.Random(287555)
        mismatches = 0
        for _ in range(60000):
            seed = rng.randrange(10 ** 9)
            depth = rng.choice([3, 4, 4, 5, 5])
            stmts = rng.choice([3, 4, 5, 6, 7])
            _, _, _, mismatch = check_one_ext(seed, max_depth=depth, max_stmts=stmts)
            mismatches += mismatch
    finally:
        P.Parser._resolve_effectful_field_return = orig
    assert mismatches > 0, "mutated field-return shadowing bug went undetected"


# ==================================================== v0.14.7 (round 293) ==
# `ExtendedEffectGen` closes the last named gap in the effect-alias family:
# v0.14.7's NESTED field shape (`outer.box.run(...)` where `box`'s own
# value is ITSELF a record literal — round 288). See `alias_effects.py`'s
# own module comment (the "Round 293" paragraph) for why this folded into
# the SAME generator/oracle rather than a new one, and for the one genuine
# asymmetry versus the v0.14.6 case it otherwise mirrors: the real parser's
# `nested_field_alias_scopes` inner dict is built via `_resolve_effectful_
# alias` only, never `_resolve_effectful_return`.

def test_extended_generator_reaches_nested_field_chain_shape():
    """Coverage guard, not a correctness check — confirms the v0.14.7
    `outer.box.run(0)` shape (a two-hop `FieldAccess` chain callee) is
    actually reachable from the generator at a real rate. Measured ~20%
    (402/2000) in this round's own manual scaling check, well above the
    same 10% floor `test_extended_generator_reaches_field_return_chain_
    shape` uses for the v0.14.6 shape."""
    pat = re.compile(r"\.\w+\.\w+\(")
    hits = 0
    n = 4000
    for seed in range(n):
        src, _ = ExtendedEffectGen(seed, max_depth=4, max_stmts=5).gen_program()
        if pat.search(src):
            hits += 1
    assert hits > n * 0.1, (hits, n)


def test_extended_oracle_detects_injected_field_nested_shadowing_bug():
    """Mutation test 5/5: same shadowing-revert bug class as tests 2/3/4
    (`_resolve_effectful_field`/`_resolve_effectful_field_return`'s own
    None-sentinel shadowing), now for `_resolve_effectful_field_nested` —
    v0.14.7's fifth stack, `nested_field_alias_scopes`. Only observable
    when a box carrying a REAL (non-None) nested-field tag in an OUTER
    frame gets shadowed by an all-None rebinding in an INNER frame and
    then something in that inner frame calls THROUGH the shadowed name
    (`box.outer_field.inner_field(0)`) — the buggy resolver incorrectly
    falls through past the falsy inner dict to recover the outer frame's
    real tag. Unlike test 4/4's v0.14.6 case (a genuinely rare compound
    event needing reprioritized draw probabilities to become testable at
    all, ~0.017%), this shape's precondition (`known_alias_names()`
    non-empty) is common from the start: measured ~0.42% (21/5000) in this
    round's own manual scaling check with
    `ExtendedEffectGen._stmt_shadow_box_call_field_nested` deliberately
    targeting the scenario — N=8000 here for comfortable headroom (~34
    expected hits, P(zero hits by chance) negligible)."""
    sys.path.insert(0, WHENCE_ROOT)
    from whence import parser as P

    def buggy_resolve(self, name, outer_field, inner_field):
        for scope in reversed(self.nested_field_alias_scopes):
            if name in scope and scope[name]:
                outer = scope[name]
                inner = outer.get(outer_field)
                if inner:
                    v = inner.get(inner_field)
                    if v is not None:
                        return v
        return None

    orig = P.Parser._resolve_effectful_field_nested
    P.Parser._resolve_effectful_field_nested = buggy_resolve
    try:
        rng = random.Random(293555)
        mismatches = 0
        for _ in range(8000):
            seed = rng.randrange(10 ** 9)
            depth = rng.choice([3, 4, 4, 5, 5])
            stmts = rng.choice([3, 4, 5, 6, 7])
            _, _, _, mismatch = check_one_ext(seed, max_depth=depth, max_stmts=stmts)
            mismatches += mismatch
    finally:
        P.Parser._resolve_effectful_field_nested = orig
    assert mismatches > 0, "mutated nested-field shadowing bug went undetected"
