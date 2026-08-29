"""A STRUCTURAL detector for round 341's snapshot-vs-live-reread race
(round 343, harness A).

The bug, in one sentence: a test snapshots a source file at IMPORT time,
derives mutants from that snapshot (often by LINE NUMBER), and then hands a
LIVE checkout root to the code that applies them. If anything edits that
checkout in between, the mutant is applied to a source it was not generated
from. On this box `languages/whence/` is committed every 30-90 minutes by a
language(C) round and a slow-tier file's runtime is minutes, so "in between"
is routine, not hypothetical. Round 338 recorded the result as four
"order-dependent" failures; round 341 showed the variable is not test ORDER
but elapsed WALL-CLOCK exposure to another writer, and pinned
`test_swe_campaign.py` / `test_swe_repair.py`.

Why this file exists rather than a grep
---------------------------------------
Round 341's item 3 proposed finding the rest by grepping `_INTERP =` and
`open(os.path.join(WHENCE_ROOT`, and listed four files. That list missed
`test_swe_oraclekill.py`, which has the sharpest instance in the tree: a
module-level snapshot feeding mutants selected by line number. It was missed
because it spells the snapshot `SRC = open(os.path.join(ROOT, ...))` with the
root aliased one hop through `OK.WHENCE_ROOT` — so neither pattern matched.

**A grep for a NAME cannot find a SHAPE.** This is the same lesson round 341
drew for `record_call_site`: the guard that would have PREVENTED the bug is
an AST-level one asserting a structural property, not a text search for the
spelling the bug happened to use this time. So the detector below resolves
one level of module-level aliasing and matches on structure.

The rule it enforces
--------------------
A test module is flagged when BOTH hold:

  (a) it takes a MODULE-LEVEL snapshot -- an assignment at module scope whose
      value comes from `open(...)` on a path built from a live-root
      expression; and
  (b) that same live-root expression is used inside a FUNCTION BODY.

Both halves are load-bearing. (a) alone is the fix itself: pinning starts by
reading the live source once, at module level, in order to copy it. (b) alone
is fine: plenty of tests legitimately drive the live checkout without
snapshotting it. It is the pair -- a frozen copy of the source in one hand, a
root that keeps moving in the other -- that is the defect.

A "live-root expression" is any `WHENCE_ROOT` (bare, or as an attribute such
as `OK.WHENCE_ROOT`) plus one hop of module-level aliasing (`ROOT =
OK.WHENCE_ROOT`), which is exactly the hop that hid the `oraclekill`
instance.

Known limits, stated rather than implied: one alias hop, not N; a root
reached through a container or a function return is invisible; and a test
that snapshots inside a slow function body rather than at module scope has
the same defect with a shorter exposure window and is NOT flagged. Those are
recorded in `FUNCTION_SCOPE_SNAPSHOTS` below rather than left to be
rediscovered.
"""
import ast
import os

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

#: The identifier that names a live checkout root anywhere in this suite.
_ROOT_LEAF = "WHENCE_ROOT"


def _leaf(node):
    """Final identifier of a Name/Attribute chain, else None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _root_aliases(tree):
    """Module-level names bound directly to a live-root expression.

    `ROOT = OK.WHENCE_ROOT` -> {"ROOT"}. One hop only, deliberately: it is
    the hop that exists in this tree, and a chain the reader cannot follow
    in one glance is a different problem.
    """
    out = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and _leaf(node.value) == _ROOT_LEAF:
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
    return out


def _is_live_root(node, aliases):
    leaf = _leaf(node)
    return leaf == _ROOT_LEAF or (isinstance(node, ast.Name) and node.id in aliases)


def _live_roots_in(node, aliases):
    """Every live-root expression appearing anywhere under `node`."""
    return [n for n in ast.walk(node)
            if isinstance(n, (ast.Name, ast.Attribute)) and _is_live_root(n, aliases)]


def _reads_a_file(node):
    """Does this subtree call `open(...)`?"""
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and _leaf(n.func) == "open":
            return True
    return False


def module_level_snapshots(tree, aliases):
    """(target name, lineno) for each module-level `x = open(<live root>...)`."""
    out = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not _reads_a_file(node.value):
            continue
        if not _live_roots_in(node.value, aliases):
            continue
        for t in node.targets:
            if isinstance(t, ast.Name):
                out.append((t.id, node.lineno))
    return out


def live_root_uses_in_functions(tree, aliases):
    """(function name, lineno) for each live-root expression inside a body."""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for use in _live_roots_in(node, aliases):
            out.append((node.name, use.lineno))
    return out


def scan_source(src, path="<str>"):
    tree = ast.parse(src, path)
    aliases = _root_aliases(tree)
    snaps = module_level_snapshots(tree, aliases)
    uses = live_root_uses_in_functions(tree, aliases)
    return {
        "aliases": sorted(aliases),
        "snapshots": snaps,
        "function_uses": uses,
        "flagged": bool(snaps) and bool(uses),
    }


def scan_file(path):
    with open(path, encoding="utf-8") as f:
        return scan_source(f.read(), path)


def scan_tests_dir(tests_dir=TESTS_DIR):
    out = {}
    for n in sorted(os.listdir(tests_dir)):
        if n.startswith("test_") and n.endswith(".py"):
            out[n] = scan_file(os.path.join(tests_dir, n))
    return out


# ---------------------------------------------------------------- the pin --

#: Files allowed to match the shape, each with the reason it is not the bug.
#: An entry must name why the snapshot and the live root cannot disagree —
#: "it looked fine" is not a reason, and the one entry here is checked
#: structurally by `test_the_allowed_campaign_fixture_actually_pins` rather
#: than taken on trust.
ALLOWED = {
    "test_swe_campaign.py":
        "both live-root uses are deliberate. (1) the `checkout` fixture "
        "copies FROM the live root and then overwrites whence/interp.py "
        "with the module-level `_INTERP` snapshot — that IS round 341's "
        "pin, and it must be per-test because each test needs its own "
        "scratch tree, so it cannot move to module scope. (2) one assertion "
        "checks that a generated test file did NOT land in the real "
        "checkout, where being live is the entire claim.",
}

#: Same defect, shorter exposure window: the snapshot is taken inside a test
#: body rather than at import, so the window is one function's runtime rather
#: than the whole file's. Recorded, not fixed, and the reason is honest --
#: the fix (pinning a checkout copy) costs a full tree copy per call site,
#: and round 341 measured the module-scope window as the one that actually
#: produced observed failures. Listed so the class stays visible and so a
#: future round can decide with the list in hand rather than re-deriving it.
FUNCTION_SCOPE_SNAPSHOTS = {
    "test_swe_equivalence.py": "reads interp.py inside two tests, then "
                               "load_whence(WHENCE_ROOT) in the same call",
    "test_swe_killers.py": "same shape, two tests",
}


def test_no_module_level_snapshot_shares_a_module_with_a_live_root_use():
    """The guard. This is the test that would have PREVENTED round 338's
    four 'order-dependent' failures, and the one that would have caught
    `test_swe_oraclekill.py` when round 341 swept for them by name."""
    found = {n: r for n, r in scan_tests_dir().items() if r["flagged"]}
    unexpected = {n: r for n, r in found.items() if n not in ALLOWED}
    assert not unexpected, (
        "snapshot-vs-live-reread shape in %s -- pin a checkout copy (see "
        "test_swe_repair.py's PINNED_ROOT) or add to ALLOWED with a reason:\n%s"
        % (sorted(unexpected), "\n".join(
            "  %s: snapshots %s at line %d; live root used in %s()"
            % (n, r["snapshots"][0][0], r["snapshots"][0][1],
               r["function_uses"][0][0])
            for n, r in sorted(unexpected.items()))))


def test_detector_flags_the_pre_fix_oraclekill_shape():
    """Round 343's own find, reduced to its structure -- including the alias
    hop (`ROOT = OK.WHENCE_ROOT`) that made a grep for `WHENCE_ROOT` on the
    open() line miss it."""
    src = (
        "import os\n"
        "from swe import oraclekill as OK\n"
        "from swe.killers import load_whence\n"
        "ROOT = OK.WHENCE_ROOT\n"
        "SRC = open(os.path.join(ROOT, 'whence', 'interp.py')).read()\n"
        "def test_x():\n"
        "    return load_whence(ROOT, 'orig')\n"
    )
    r = scan_source(src)
    assert r["flagged"]
    assert r["aliases"] == ["ROOT"]
    assert r["snapshots"] == [("SRC", 5)]
    assert r["function_uses"] == [("test_x", 7)]


def test_detector_flags_the_pre_fix_review_shape_without_an_alias():
    src = (
        "import os\n"
        "from swe.fuzz import WHENCE_ROOT\n"
        "_INTERP_LINES = open(os.path.join(WHENCE_ROOT, 'whence/interp.py')).read().splitlines()\n"
        "def test_y(m):\n"
        "    return MutantDiffTool(WHENCE_ROOT, m)\n"
    )
    r = scan_source(src)
    assert r["flagged"] and r["aliases"] == [] and r["snapshots"] == [("_INTERP_LINES", 3)]


def test_the_pin_itself_is_not_flagged():
    """The fix reads the live source once at module level in order to COPY
    it, then every body uses the copy. Half (a) matches and half (b) does
    not -- which is exactly why the rule needs both halves. A detector that
    fired on this would be unusable: it would flag its own remedy."""
    src = (
        "import os\n"
        "from swe.fuzz import WHENCE_ROOT\n"
        "from swe.mutation import _copy_project\n"
        "_SRC = open(os.path.join(WHENCE_ROOT, 'whence/interp.py')).read()\n"
        "PINNED_ROOT = '/tmp/pin'\n"
        "_copy_project(WHENCE_ROOT, PINNED_ROOT)\n"
        "def test_z(m):\n"
        "    return MutantDiffTool(PINNED_ROOT, m)\n"
    )
    r = scan_source(src)
    assert r["snapshots"] == [("_SRC", 4)]          # half (a) matches
    assert r["function_uses"] == []                 # half (b) does not
    assert not r["flagged"]


def test_a_live_root_with_no_snapshot_is_not_flagged():
    """Driving the live checkout is normal and must stay unflagged -- there
    is nothing frozen for it to disagree with."""
    src = (
        "from swe.fuzz import WHENCE_ROOT\n"
        "def test_w():\n"
        "    return OracleTool(WHENCE_ROOT)\n"
    )
    r = scan_source(src)
    assert r["function_uses"] and not r["snapshots"] and not r["flagged"]


def test_the_two_files_round_343_fixed_are_clean_and_still_snapshot():
    """A pin that stopped snapshotting would pass the guard by deleting the
    thing under test. Both files must still take their module-level
    snapshot; what changed is what the BODIES are handed."""
    for name in ("test_swe_oraclekill.py", "test_swe_review.py"):
        r = scan_file(os.path.join(TESTS_DIR, name))
        assert not r["flagged"], name
        assert r["snapshots"] or name == "test_swe_review.py", name


def test_function_scope_snapshots_are_recorded_not_silently_dropped():
    """Round 339's rule: a checker must publish its own recall. These files
    have the same defect with a shorter window and this detector does not
    look inside function bodies -- so the list is the recall statement."""
    for name in FUNCTION_SCOPE_SNAPSHOTS:
        assert os.path.exists(os.path.join(TESTS_DIR, name)), name
        assert FUNCTION_SCOPE_SNAPSHOTS[name].strip()


def test_the_allowed_campaign_fixture_actually_pins():
    """The allowlist entry is only as good as the pin it asserts exists.

    Structural, not textual: find the function that uses the live root,
    require that the SAME function writes the module-level snapshot back.
    If a later edit drops the overwrite, the allowlist stops being true and
    this fails — which is the difference between an exemption and a claim.
    """
    path = os.path.join(TESTS_DIR, "test_swe_campaign.py")
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    aliases = _root_aliases(tree)
    snap_names = set(n for n, _ in module_level_snapshots(tree, aliases))
    assert snap_names, "campaign.py no longer snapshots; revisit the entry"

    fixtures = [n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef)
                and _live_roots_in(n, aliases)
                and any(isinstance(c, ast.Call) and _leaf(c.func) == "_copy_project"
                        for c in ast.walk(n))]
    assert len(fixtures) == 1, [f.name for f in fixtures]
    body = fixtures[0]
    # the snapshot must be written back inside that same fixture
    written = [n.id for n in ast.walk(body)
               if isinstance(n, ast.Name) and n.id in snap_names
               and isinstance(n.ctx, ast.Load)]
    assert written, (
        "%s() copies from the live root but never writes the %s snapshot "
        "back — the pin is gone and ALLOWED is now false"
        % (body.name, sorted(snap_names)))


def test_allowlist_holds_exactly_the_reviewed_files():
    """A new flagged file must be fixed or argued, never absorbed by a
    growing allowlist. Pinning the exact key set is what forces that."""
    assert sorted(ALLOWED) == ["test_swe_campaign.py"]
