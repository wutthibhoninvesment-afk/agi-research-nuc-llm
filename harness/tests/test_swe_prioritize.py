"""swe.prioritize: kill-first ordering learned from a previous run."""
import json
import os
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe.mutation import generate, run_mutant, DEFAULT_TEST_CMD
from swe.prioritize import (Prioritizer, killed_by, learn, load_records,
                            default_test_files)
from swe.campaign import Campaign

MOD = textwrap.dedent('''
    def clamp(x, lo, hi):
        if x < lo:
            return lo
        if x > hi:
            return hi
        return x

    def is_even(n):
        return n % 2 == 0
''')


def make_project(tmp_path):
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    (root / "mod.py").write_text(MOD)
    (root / "tests" / "conftest.py").write_text(
        "import os, sys\nsys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n")
    # test_a only exercises is_even; test_b is the only killer of clamp mutants
    (root / "tests" / "test_a.py").write_text(
        "from mod import is_even\ndef test_even():\n    assert is_even(4) and not is_even(3)\n")
    (root / "tests" / "test_b.py").write_text(
        "from mod import clamp\ndef test_clamp():\n    assert clamp(5, 0, 3) == 3 and clamp(-1, 0, 3) == 0 and clamp(1, 0, 3) == 1\n")
    return str(root)


def test_killed_by_parses_first_failed_file():
    assert killed_by("FAILED tests/test_v09.py::test_x - assert 1 == 0\n1 failed") == "tests/test_v09.py"
    assert killed_by("1 failed, 3 passed") is None
    assert killed_by("") is None and killed_by(None) is None


def test_learn_keeps_only_killed_with_a_file():
    recs = [{"path": "m.py", "line": 3, "op": "cmp", "status": "killed",
             "detail": "FAILED tests/test_b.py::test_clamp - x"},
            {"path": "m.py", "line": 9, "op": "cmp", "status": "survived", "detail": ""},
            {"path": "m.py", "line": 4, "op": "const", "status": "timeout", "detail": "exceeded"}]
    assert learn(recs) == [("m.py", 3, "cmp", "tests/test_b.py")]


def test_order_for_nearest_line_first_then_default(tmp_path):
    root = make_project(tmp_path)
    files = default_test_files(root)
    assert files == ["tests/test_a.py", "tests/test_b.py"]
    learned = [("mod.py", 3, "cmp", "tests/test_b.py"), ("mod.py", 10, "arith", "tests/test_a.py")]
    pr = Prioritizer(learned, files, k=1)
    assert pr.order_for("mod.py", 4, "cmp") == ["tests/test_b.py", "tests/test_a.py"]
    assert pr.order_for("mod.py", 9, "arith") == ["tests/test_a.py", "tests/test_b.py"]
    # unknown file: default order; every file exactly once
    assert pr.order_for("other.py", 4, "cmp") == files
    # same distance: same-op record wins
    pr2 = Prioritizer([("mod.py", 5, "cmp", "tests/test_b.py"), ("mod.py", 3, "arith", "tests/test_a.py")], files, k=1)
    assert pr2.order_for("mod.py", 4, "cmp")[0] == "tests/test_b.py"


def test_cmd_for_replaces_tests_dir_and_verdict_is_unchanged(tmp_path):
    root = make_project(tmp_path)
    # `if x < lo` -> `if not x < lo`: clamp(1, 0, 3) returns 0, killed by test_b only.
    # (The first cmp mutant, `x < lo` -> `x <= lo`, is EQUIVALENT for clamp —
    # at x == lo both return lo — a wrong first pick of this test.)
    m = [x for x in generate(MOD, "mod.py") if x.op == "ifneg"][0]
    pr = Prioritizer([("mod.py", m.lineno, "ifneg", "tests/test_b.py")], default_test_files(root), k=1)
    cmd = pr.cmd_for(m, DEFAULT_TEST_CMD)
    assert cmd[:-2] == DEFAULT_TEST_CMD[:-1] and cmd[-2:] == ["tests/test_b.py", "tests/test_a.py"]
    run_mutant(m, root, cmd, timeout_s=60)
    assert m.status == "killed" and killed_by(m.detail) == "tests/test_b.py"
    m2 = [x for x in generate(MOD, "mod.py") if x.op == "ifneg"][0]
    run_mutant(m2, root, DEFAULT_TEST_CMD, timeout_s=60)
    assert m2.status == "killed"                       # same verdict either way


def test_campaign_records_first_file_and_killed_by(tmp_path):
    root = make_project(tmp_path)
    prior = tmp_path / "prior.jsonl"
    prior.write_text(json.dumps({"path": "mod.py", "line": 3, "op": "cmp", "status": "killed",
                                 "detail": "FAILED tests/test_b.py::test_clamp - x"}) + "\n")
    pr = Prioritizer.from_file(str(prior), root, k=1)
    c = Campaign(str(tmp_path / "camp"), root, ("mod.py",), prioritizer=pr, log=lambda s: None)
    data = c.stage_mutation(workers=2, timeout_s=60, limit=3)
    recs = [json.loads(l) for l in open(c.path("mutation.partial.jsonl"))]
    assert len(recs) == 3 and all("first_file" in r and "killed_by" in r for r in recs)
    assert all(r["first_file"] == "tests/test_b.py" for r in recs if r["op"] == "cmp")
    assert all((r["killed_by"] is not None) == (r["status"] == "killed") for r in recs)
    assert data["total"] == 3
