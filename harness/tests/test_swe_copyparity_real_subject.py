"""copyparity, pointed at the tree it was written for.

Round 425 (SWE-loop D). `harness/tests/test_swe_copyparity.py` has twelve
tests and every one of them builds a toy project under `tmp_path`. They pin
the MECHANISM and say nothing about the SUBJECT, so the module that exists to
keep `languages/whence` copy-safe had never once been run against
`languages/whence`. Round 419's own ledger entry names that gap in the
abstract — "the tools' tests are all pointed at TOY projects, so 'has tests'
and 'has tests about the thing it is used on' came apart and the defect landed
in the gap" — and then the round closed without closing it.

This file is the other half: the real subject, every round, at a price the
fast tier can pay. Measured on this box, the whole file is a few seconds,
which is what makes it promotable into `harness/tier-budget.json`. The
expensive mode (`run`, 283 s for the two suite runs, measured this round at
74x the static scan) deliberately is NOT here; `harness/swe/slowtier.py` is
where that belongs.

WHY A STATIC MODE AT ALL — the finding this file exists to keep true
--------------------------------------------------------------------
Both differential modes only see an escaping path once something USES it.
`os.path.dirname` never raises; it happily returns `/tmp`. So a subtree can
carry a fully-formed escaping expression and be green in `collect` AND in
`run`, forever, until the round that finally reads the variable.

That is not hypothetical — it is what round 425 found in this very tree:

  * `tests/test_v24.py:33`   `REPO = dirname(dirname(ROOT))`, assigned by
    round 360 and, after round 413 repointed every USE of it, read by
    nothing. A loaded gun with no trigger.
  * `tests/test_v31.py:421`  `sys.path.insert(0, dirname(dirname(ROOT)))`,
    written by round 380, and superseded TWO LINES BELOW by round 413's
    `curecheck.AGI_ROOT` block — which was added ALONGSIDE it instead of
    replacing it. Inserting a `/tmp` directory at `sys.path[0]` is harmless
    here only by luck.

`copyparity collect` called the tree `copy_safe` with both of those in it,
and so did `run`. Only the static mode could see them, because it is the only
one that does not need the defect to fire first.
"""
import json
import os
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.dirname(_HERE))

from swe.copyparity import (                                     # noqa: E402
    ROOT_ENV_VAR, compare, escapes_summary, scan_escapes)
from swe.fuzz import WHENCE_ROOT                                 # noqa: E402

#: The CLI, written as literal tokens on purpose. `harness/verb_audit.py`
#: reads SOURCE for a token naming an entry point followed by a verb, so
#: these two lines are what move `collect` and `escapes` out of V003
#: ("declares verbs; NONE is invoked anywhere in the closure"). They are the
#: real argv — each test below actually runs it, from `REPO_ROOT`, so the
#: token the audit reads and the command that runs are the same string.
ESCAPES_ARGV = [
    "harness/swe/copyparity.py", "escapes", "--root", "languages/whence",
]
COLLECT_ARGV = [
    "harness/swe/copyparity.py", "collect", "--root", "languages/whence",
]

#: A scan that read nothing reports "no findings" and looks exactly like a
#: clean tree. `languages/whence` had 84 `*.py` files when this was written;
#: the floor is far below that so ordinary growth or pruning does not trip
#: it, but a scan pointed at an empty or wrong directory does.
MIN_FILES_SCANNED = 40

#: Likewise for the differential: round 419's first run of this module
#: reported `0 node(s)` on both sides (two `-q` are `-qq`) and called the
#: whence tree copy_safe on the strength of it.
MIN_NODES_COLLECTED = 1500


@pytest.fixture(scope="module")
def real_scan():
    return scan_escapes(WHENCE_ROOT)


def test_the_real_whence_tree_has_no_unguarded_escape(real_scan):
    """The fail-closed one. A new file under `languages/whence` that resolves
    a path outside it fails HERE, at authoring time, instead of in a mutation
    campaign's baseline gate weeks later — which is how rounds 149, 413 and
    419 each found it."""
    findings, stats = real_scan
    assert stats["n_files"] >= MIN_FILES_SCANNED, (
        "only %d file(s) scanned — a scan that read nothing is not a verdict"
        % stats["n_files"])
    assert not stats["unreadable"], stats["unreadable"]
    real = [f for f in findings if not f["env_guarded"]]
    assert real == [], (
        "languages/whence has %d expression(s) resolving outside itself; "
        "they will point into /tmp in every mutation sandbox:\n%s"
        % (len(real), escapes_summary(findings, stats)))


def test_the_sanctioned_root_helper_is_still_what_the_tree_uses(real_scan):
    """The exemption is only sound while something actually uses it.

    Seven expressions in this tree reach the repo root THROUGH
    `AGI_RESEARCH_ROOT`, which `harness/swe/proc.py` exports into every
    sandbox, so they still resolve in the copy. If that count went to zero
    the exemption would be dead code and the previous test would be passing
    for the wrong reason — vacuously, over a tree that no longer reaches
    outside itself by any route."""
    findings, stats = real_scan
    assert stats["n_env_guarded"] > 0, (
        "no expression in %s reaches outside via %s any more — re-check that "
        "the exemption still describes this tree" % (WHENCE_ROOT, ROOT_ENV_VAR))
    guarded_files = {f["file"] for f in findings if f["env_guarded"]}
    assert "curecheck.py" in guarded_files, (
        "curecheck.py is where round 413 put the one home for the repo root; "
        "guarded files are %s" % sorted(guarded_files))


def test_the_escapes_cli_runs_on_the_real_subject_and_exits_on_its_verdict():
    p = subprocess.run([sys.executable] + ESCAPES_ARGV, cwd=REPO_ROOT,
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "copyparity(escapes): copy_safe" in p.stdout, p.stdout
    assert "file(s) scanned" in p.stdout


def test_the_collect_differential_runs_on_the_real_subject():
    """The cheap differential against the real tree — ~4 s, both sides. This
    is the mode that would have caught round 413's `FileNotFoundError` (a
    module-level read aborts collection, so the node vanishes)."""
    p = subprocess.run([sys.executable] + COLLECT_ARGV, cwd=REPO_ROOT,
                       capture_output=True, text=True, timeout=600)
    assert p.returncode == 0, p.stdout[-3000:] + p.stderr[-2000:]
    assert "copyparity(collect): copy_safe" in p.stdout, p.stdout[-3000:]
    n = [int(t) for t in p.stdout.split() if t.isdigit()]
    assert n and max(n) >= MIN_NODES_COLLECTED, (
        "collected %s node(s) — a differential over an empty node set reports "
        "parity for any tree at all" % n)


def test_both_differentials_are_blind_to_an_escape_nothing_uses(tmp_path):
    """The claim that justifies a third mode, pinned rather than argued.

    A project that COMPUTES an escaping path and never opens it is green in
    `collect` (nothing fails to import) and green in `run` (nothing fails at
    all) — and `escapes` sees it. This is round 425's own finding reduced to
    a toy: `tests/test_v24.py:33` was exactly this shape and had been in the
    tree since round 360, through two differential-based investigations."""
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_latent.py").write_text(
        "import os\n"
        "ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n"
        "REPO = os.path.dirname(os.path.dirname(ROOT))\n\n"
        "def test_passes_anyway():\n"
        "    assert isinstance(REPO, str)\n", encoding="utf-8")
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"]

    findings, stats = scan_escapes(str(root))
    real = [f for f in findings if not f["env_guarded"]]
    assert [(f["file"], f["level"], f["kind"]) for f in real] == [
        (os.path.join("tests", "test_latent.py"), -2, "import_time")]

    for mode in ("collect", "run"):
        rep = compare(root=str(root), mode=mode, test_cmd=cmd, timeout_s=120)
        assert rep.verdict == "copy_safe", (
            "%s mode saw the latent escape; if that is now true the "
            "third mode's justification has changed" % mode)


def test_the_scan_reports_the_runtime_and_import_time_split(tmp_path):
    """`kind` is where the expression SITS, which is not where it would fail.
    Both are reported because they need different confirmations: an
    import-time escape that is used aborts collection, a runtime one does
    not."""
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_two.py").write_text(
        "import os\n"
        "ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n"
        "TOP = os.path.join(ROOT, '..', '..', 'state')\n\n"
        "def test_one():\n"
        "    inner = os.path.join(ROOT, os.pardir, os.pardir, 'x')\n"
        "    assert TOP and inner\n", encoding="utf-8")
    findings, stats = scan_escapes(str(root))
    kinds = sorted(f["kind"] for f in findings if not f["env_guarded"])
    assert kinds == ["import_time", "runtime"], escapes_summary(findings, stats)
    assert stats["n_import_time"] == 1 and stats["n_runtime"] == 1


def test_an_escape_through_the_root_env_var_is_not_a_finding(tmp_path):
    """Round 413's fix reaches outside the subtree ON PURPOSE and survives the
    copy, because the env var still names the real checkout there. Reporting
    it would make the checker cry wolf at the one pattern it wants people to
    use."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "helper.py").write_text(
        "import os\n"
        "_HERE = os.path.dirname(os.path.abspath(__file__))\n"
        "AGI_ROOT = os.environ.get('AGI_RESEARCH_ROOT') or "
        "os.path.dirname(os.path.dirname(_HERE))\n"
        "FALLBACK = os.environ.get('AGI_RESEARCH_ROOT', "
        "os.path.dirname(os.path.dirname(_HERE)))\n", encoding="utf-8")
    findings, stats = scan_escapes(str(root))
    assert stats["n_findings"] == 0, escapes_summary(findings, stats)
    assert stats["n_env_guarded"] == 2, escapes_summary(findings, stats)


def test_an_unreadable_component_pushes_away_from_a_finding(tmp_path):
    """A component the scanner cannot evaluate counts +1, never -1. A static
    check that guesses toward findings gets uninstalled."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "m.py").write_text(
        "import os\n"
        "_HERE = os.path.dirname(os.path.abspath(__file__))\n"
        "A = os.path.join(_HERE, '..', some_name())\n"
        "B = os.path.join(_HERE, '..', '..', 'x')\n", encoding="utf-8")
    findings, stats = scan_escapes(str(root))
    lines = {f["line"] for f in findings}
    assert lines == {4}, escapes_summary(findings, stats)


def test_empty_scan_is_not_a_pass(tmp_path):
    """Exit 2, not 0: `n_files == 0` is 'no verdict', the same rule the
    differential applies to a timeout."""
    empty = tmp_path / "nothing"
    empty.mkdir()
    p = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "harness", "swe", "copyparity.py"),
         "escapes", "--root", str(empty)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    assert "NO FILE WAS SCANNED" in p.stdout


def test_json_output_carries_every_finding_field(tmp_path):
    out = tmp_path / "r.json"
    p = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "harness", "swe", "copyparity.py"),
         "escapes", "--root", os.path.join(REPO_ROOT, "languages", "whence"),
         "--json", str(out)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stdout + p.stderr
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["mode"] == "escapes"
    assert doc["stats"]["n_findings"] == 0
    for f in doc["findings"]:
        assert set(f) == {"file", "line", "level", "kind", "env_guarded", "expr"}
        assert f["level"] < 0 and f["kind"] in ("import_time", "runtime")
