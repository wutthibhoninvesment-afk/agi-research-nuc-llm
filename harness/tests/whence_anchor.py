"""The string-concat mutation anchor, in ONE place (round 445, harness A).

Why this module exists
----------------------
Two harness test files need the same fixture: *an arith mutant on a line of
`whence/interp.py` that builds a `"concat"` provenance*, which turns `+` into
`-` and therefore crashes on two strings. `test_swe_killers.py` uses it to
prove `find_killer` finds a real semantic kill; `test_swe_equivalence.py`
uses it to prove `escalate`/`run_equivalence`/`summarize` report
`corpus_gap_closed`.

Both files carried their own copy of the selection expression, and
`test_swe_equivalence.py`'s copy said so in a docstring — *"Same anchor
swe.killers' own test uses"*. That sentence was a cross-file claim with no
reader, and round 437 made it false: it re-anchored killers (dropping an
`and "x + y" in ...` clause that round 368's v0.27 had invalidated by
deleting the inline `Prov("+", "concat", ..., x + y)` site) and its 15-file
diff never mentions `equivalence`. The equivalence copy stayed pinned to a
spelling that no longer exists in `interp.py`, and stayed red for 76 rounds
because `test_swe_*` files are slow-tier and nothing ran that one until the
round-439 driver slice reached it after round 444.

THE ANCHOR RULE (process rule 7's standing instruction, verbatim): *every
arith mutant on a line containing `"concat"` is a legitimate anchor*. Pin to
that behaviour, never to one line's spelling of its operands.

WHY REACHABILITY IS PART OF THE RULE, not a refinement of it
------------------------------------------------------------
Not every `"concat"` line is reachable from two string literals. Measured at
round 445's HEAD, the rule yields two candidates and the FIRST ONE DOES NOT
KILL:

    interp.py:2059:arith#1294  line 2059  derived(op, "concat", ...)   found=False
    interp.py:2014:arith#1441  line 2014  Prov(op, "concat", ...)      found=True

`test_swe_killers.py` already knew this ("a concat site can be unreachable
for two string literals ... 'no anchor at all' is the failure worth
reporting, not 'the first one I tried'") and iterates. The equivalence copy
took `candidates[0]`. So porting round 437's diff verbatim into it would
have produced a test that was STILL RED — the naive fix is not the fix. That
asymmetry between two copies of "the same" fixture is the whole reason
selection and reachability live together here, behind one call.
"""
import os
import sys

_HARNESS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HARNESS_DIR not in sys.path:
    sys.path.insert(0, _HARNESS_DIR)

from swe.fuzz import WHENCE_ROOT
from swe.killers import find_killer, load_whence
from swe.mutation import generate

#: The two-program corpus both callers use: one string concat, one control.
#: A killer must be reachable from THIS, which is what makes the fixture a
#: statement about behaviour rather than about `interp.py`'s line numbers.
TWO_STRING_LITERALS = ['let a = "x" + "y"\n', "let b = 1\n"]

_RULE7 = "re-anchor (rule 7)"


def interp_source(root=WHENCE_ROOT):
    """`whence/interp.py`'s text, read the same way both callers read it."""
    with open(os.path.join(root, "whence", "interp.py")) as f:
        return f.read()


def concat_arith_candidates(src=None, path="whence/interp.py"):
    """Every arith mutant on a line containing `"concat"` — the rule, whole.

    Deliberately NOT narrowed by how a given line spells its operands. That
    narrowing is what round 368 invalidated and round 437 removed.
    """
    if src is None:
        src = interp_source()
    lines = src.splitlines()
    return [m for m in generate(src, path)
            if m.op == "arith" and '"concat"' in lines[m.lineno - 1]]


def first_reachable(candidates, try_kill):
    """`(mutant, killer)` for the first candidate `try_kill` actually kills.

    Pure iteration, with the kill injected, so the failure path can be tested
    without running a single Whence program. Raises `AssertionError` naming
    every candidate it tried: "no anchor at all" is the report worth having,
    not a silent fallback to a candidate that does not kill.
    """
    if not candidates:
        raise AssertionError(
            'no arith mutant on a `"concat"` line — %s' % _RULE7)
    for m in candidates:
        k = try_kill(m)
        if k.found:
            return m, k
    raise AssertionError(
        'no `"concat"` arith mutant is reachable from two string literals — '
        "%s; tried %s" % (_RULE7, [c.id for c in candidates]))


_CACHE = {}


def reachable_concat_mutant(root=WHENCE_ROOT, progs=None, tag="concat_anchor"):
    """`(mutant, killer)` — the anchor, resolved against the real interpreter.

    Memoised per (root, tag, corpus): resolving costs a `load_whence` plus one
    `find_killer` per candidate (~30 s at round 445's HEAD, two candidates),
    and `test_swe_equivalence.py` alone asks for it three times.
    """
    progs = list(TWO_STRING_LITERALS if progs is None else progs)
    key = (root, tag, tuple(progs))
    if key not in _CACHE:
        src = interp_source(root)
        orig = load_whence(root, tag)
        _CACHE[key] = first_reachable(
            concat_arith_candidates(src),
            lambda m: find_killer(m, progs, orig, root))
    return _CACHE[key]
