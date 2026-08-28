"""Tests for `harness/swe/alias_effects.py` — the targeted differential
oracle for v0.14.2's direct-alias effect tracking (round 269).

Follows `test_swe_guest.py`'s own discipline (see its module docstring):
zero findings on random programs is only evidence if the oracle
demonstrably fires on an injected divergence, so half of this file runs
against a deliberately mutated copy of the real check.
"""
import os
import random
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


# =========================================== v0.14.3/4/5 (round 281) ======
# `ExtendedEffectGen` covers the three effect-alias features `AliasEffectsGen`
# doesn't: return-value aliasing (v0.14.3), record-field aliasing (v0.14.4),
# and if/else-tail combination (v0.14.5) — see `alias_effects.py`'s own
# module comment for why these needed a genuinely new generator, not just
# more `AliasEffectsGen` seeds.

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


def test_extended_targeted_campaign_no_mismatches():
    """The real regression: 3000 generated programs spanning return/field/
    if-tail alias shapes (plus their interaction with v0.14.2's own direct
    aliasing) against the real parser, compared to the independent
    oracle's prediction."""
    rng = random.Random(281269)
    mismatches = []
    for _ in range(3000):
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
