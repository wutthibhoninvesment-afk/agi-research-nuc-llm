"""Round 445 (harness A). The guards on `tests/whence_anchor`.

Deliberately NOT named `test_swe_*`: `conftest.py`'s rule tiers that prefix
slow, and the whole finding this file exists for is that the broken copy of
the anchor lived in a slow-tier file and went unrun for 76 rounds. Every test
here is pure — no interpreter, no mutant execution — so the tier that runs
EVERY round is the one that polices the duplication.
"""
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.whence_anchor import (concat_arith_candidates, first_reachable,
                                 TWO_STRING_LITERALS)

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

#: The one module allowed to spell the anchor rule. Everything else must
#: import it.
ANCHOR_MODULE = "whence_anchor.py"


class _Kill(object):
    def __init__(self, found, tried=1):
        self.found = found
        self.tried = tried


class _Cand(object):
    def __init__(self, mid):
        self.id = mid


# ------------------------------------------------------------ the iteration --

def test_first_reachable_returns_the_first_candidate_that_actually_kills():
    cands = [_Cand("a"), _Cand("b"), _Cand("c")]
    seen = []

    def try_kill(m):
        seen.append(m.id)
        return _Kill(m.id == "b")

    m, k = first_reachable(cands, try_kill)
    assert m.id == "b" and k.found
    # stopped at the first hit; did not keep paying for "c"
    assert seen == ["a", "b"]


def test_first_reachable_reports_no_anchor_rather_than_falling_back():
    """The defect round 445 found, in one assertion.

    `test_swe_equivalence.py` took `candidates[0]` and got a mutant that does
    not kill. Silently returning a non-killing candidate is worse than
    failing, because the tests downstream then assert `corpus_gap_closed`
    against it and blame `escalate`.
    """
    cands = [_Cand("x"), _Cand("y")]
    try:
        first_reachable(cands, lambda m: _Kill(False))
    except AssertionError as e:
        msg = str(e)
    else:
        raise AssertionError("returned an anchor when nothing killed")
    assert "rule 7" in msg
    # names every candidate it tried, so the next re-anchor starts from data
    assert "x" in msg and "y" in msg


def test_first_reachable_refuses_an_empty_candidate_list():
    try:
        first_reachable([], lambda m: _Kill(True))
    except AssertionError as e:
        assert "rule 7" in str(e)
    else:
        raise AssertionError("accepted an empty candidate list")


# ----------------------------------------------------------------- the rule --

def test_the_rule_selects_on_the_marker_and_not_on_operand_spelling():
    """Round 368 deleted the one site spelled `x + y` and the fixture that
    named that spelling died with it. Two concat lines with different operand
    names must both qualify."""
    src = ('def f(a, b, l, r):\n'
           '    p = mk(op, "concat", line, x + y)\n'
           '    q = mk(op, "concat", line, l + r)\n'
           '    z = mk(op, "arith", line, l + r)\n')
    got = sorted(m.lineno for m in concat_arith_candidates(src, "f.py"))
    assert got == [2, 3], got


def test_the_live_anchor_rule_still_finds_candidates_in_interp_py():
    """Cheap half of the anchor's health: selection only, no kill. If this
    goes red, `interp.py` stopped building `"concat"` provenance with a binary
    `+` at all and BOTH callers need re-anchoring (rule 7)."""
    assert concat_arith_candidates()


def test_the_two_string_literal_corpus_really_contains_a_string_concat():
    assert any('"x" + "y"' in p for p in TWO_STRING_LITERALS)
    assert len(TWO_STRING_LITERALS) == 2


# ---------------------------------------------------------- the duplication --

#: The anchor's marker AS IT APPEARS IN `interp.py`'s source — quotes
#: included, because the selection expression tests for the six characters
#: `"concat"` inside a line of that file. Matched EXACTLY, not by substring:
#: the first draft of this guard used `"concat" in value` and flagged its own
#: `"reachable_concat_mutant" in f.read()` two functions below.
ANCHOR_LITERAL = '"concat"'


def _anchor_expressions(path):
    """`ast.Compare` nodes of the shape `'"concat"' in <something>` — the
    selection expression, found structurally so a COMMENT that merely
    discusses the anchor is not a false positive.

    Scoped on purpose to the shape both real copies actually had. A
    re-derivation spelled some other way (`line.find(...)`, a regex) would
    slip past; this guard is a pin on the KNOWN duplication, not a proof of
    uniqueness, and saying so here is cheaper than implying otherwise.
    """
    with open(path) as f:
        tree = ast.parse(f.read(), path)
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(o, ast.In) for o in node.ops):
            continue
        left = node.left
        if isinstance(left, ast.Constant) and left.value == ANCHOR_LITERAL:
            hits.append(node.lineno)
    return hits


def test_no_other_harness_test_file_reimplements_the_concat_anchor_inline():
    """The guard round 437 did not have.

    Round 437 re-anchored `test_swe_killers.py` and left
    `test_swe_equivalence.py`'s identical copy pinned to a spelling
    `interp.py` no longer contains. Nothing was wrong with the fix; the
    problem was that there were two copies and only one had a reader. This
    fails the moment a third appears.
    """
    offenders = {}
    for name in sorted(os.listdir(TESTS_DIR)):
        if not name.endswith(".py") or name == ANCHOR_MODULE:
            continue
        lines = _anchor_expressions(os.path.join(TESTS_DIR, name))
        if lines:
            offenders[name] = lines
    assert not offenders, (
        "the concat anchor is defined in tests/%s and nowhere else; "
        "import `reachable_concat_mutant` instead of re-deriving it. "
        "Inline copies found: %s" % (ANCHOR_MODULE, offenders))


def test_the_anchor_module_itself_does_define_the_rule():
    """The negative control for the test above: if `whence_anchor.py` ever
    stops carrying the expression, the duplication guard would pass
    vacuously against a repo with no anchor at all."""
    assert _anchor_expressions(os.path.join(TESTS_DIR, ANCHOR_MODULE))


def _imports_anchor(path):
    with open(path) as f:
        tree = ast.parse(f.read(), path)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module \
                and node.module.endswith("whence_anchor"):
            return True
    return False


def test_every_test_file_that_uses_the_anchor_imports_it_from_the_one_module():
    users = []
    for name in sorted(os.listdir(TESTS_DIR)):
        if not name.startswith("test_") or not name.endswith(".py"):
            continue
        with open(os.path.join(TESTS_DIR, name)) as f:
            if "reachable_concat_mutant" in f.read():
                users.append(name)
    # both known callers, and any future one, must go through the import
    assert "test_swe_killers.py" in users
    assert "test_swe_equivalence.py" in users
    missing = [n for n in users
               if n != os.path.basename(__file__) and not _imports_anchor(os.path.join(TESTS_DIR, n))]
    assert not missing, "name the helper but do not import it: %s" % missing
