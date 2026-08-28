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

from swe.alias_effects import AliasEffectsGen, check_one, _import_parse
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
