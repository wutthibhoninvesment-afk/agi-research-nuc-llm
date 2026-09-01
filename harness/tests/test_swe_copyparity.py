"""Round 419 (SWE-loop D) — `harness/swe/copyparity.py`.

Every test here builds a TOY project on tmp_path, so the whole file runs in
a few seconds and does not depend on the state of `languages/whence`. The
one thing it cannot fake is the defect it exists for, so it constructs that
directly: a project whose test reads a file that lives OUTSIDE the project
root, resolved from `__file__`. In place the file is there; in a
`_copy_project` copy the same expression points at the copy's parent, and
the read fails.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe.copyparity import (Report, compare, main, parse_collect, parse_junit,   # noqa: E402
                            strip_exitfirst)

PYTEST_CMD = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "tests"]

#: The escaping expression, spelled the way the real defect was spelled:
#: three `dirname`s off `__file__` (tests/x.py -> tests -> proj -> parent).
_ESCAPE = (
    "import os\n"
    "OUTSIDE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(\n"
    "    os.path.abspath(__file__)))), 'outside.json')\n"
)


def _project(tmp_path, escape_at=None):
    """A tiny green project. `escape_at` in (None, 'import', 'runtime')."""
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    (tmp_path / "outside.json").write_text(json.dumps({"pins": 3}), encoding="utf-8")
    (root / "tests" / "test_ok.py").write_text(
        "def test_one():\n    assert 1 + 1 == 2\n\n"
        "def test_two():\n    assert 'a' < 'b'\n", encoding="utf-8")
    if escape_at == "runtime":
        (root / "tests" / "test_escape.py").write_text(
            _ESCAPE +
            "def test_reads_the_registry():\n"
            "    with open(OUTSIDE) as f:\n"
            "        assert f.read()\n", encoding="utf-8")
    elif escape_at == "import":
        (root / "tests" / "test_escape.py").write_text(
            _ESCAPE +
            "PINS = open(OUTSIDE).read()\n\n"
            "def test_reads_the_registry():\n"
            "    assert PINS\n", encoding="utf-8")
    return str(root)


def test_a_clean_project_is_copy_safe(tmp_path):
    rep = compare(root=_project(tmp_path), mode="run", test_cmd=PYTEST_CMD, timeout_s=120)
    assert rep.verdict == "copy_safe" and rep.copy_safe
    assert rep.in_place.n_nodes == rep.copied.n_nodes == 2
    assert rep.in_place.returncode == rep.copied.returncode == 0
    assert "no node changed verdict" in rep.summary()


def test_run_mode_names_the_node_that_is_red_only_in_the_copy(tmp_path):
    rep = compare(root=_project(tmp_path, escape_at="runtime"), mode="run",
                  test_cmd=PYTEST_CMD, timeout_s=120)
    assert rep.verdict == "copy_breaks"
    assert [n for n, _, _, _ in rep.regressions] == ["tests.test_escape::test_reads_the_registry"]
    node, a, b, detail = rep.regressions[0]
    assert a == "passed" and b == "failed"
    assert "outside.json" in detail or "FileNotFoundError" in detail
    # The in-place side stayed green: this is a copy defect, not a broken test.
    assert rep.in_place.returncode == 0 and rep.copied.returncode != 0
    assert "REGRESSED" in rep.summary()


def test_run_mode_strips_exitfirst_so_the_two_runs_stop_at_the_same_place(tmp_path):
    rep = compare(root=_project(tmp_path, escape_at="runtime"), mode="run",
                  test_cmd=PYTEST_CMD, timeout_s=120)
    assert rep.stripped_x and "-x" not in rep.test_cmd
    # With -x the copied run would have reported 1 node; without it, all 3.
    assert rep.copied.n_nodes == 3


def test_collect_mode_catches_the_import_time_class_and_run_mode_also_does(tmp_path):
    root = _project(tmp_path, escape_at="import")
    coll = compare(root=root, mode="collect", test_cmd=PYTEST_CMD, timeout_s=120)
    assert coll.verdict == "copy_breaks"
    assert coll.vanished == {"tests/test_escape.py::test_reads_the_registry"}
    assert coll.in_place.n_nodes == 3 and coll.copied.n_nodes == 2
    assert "VANISHED" in coll.summary()


def test_collect_mode_is_blind_to_the_runtime_class(tmp_path):
    """The cheap mode is cheap because it does not run anything. Round 419's
    own defect (`tests/test_checkpin.py`) was invisible to it — that is the
    reason `run` exists, and it is pinned rather than left as prose."""
    rep = compare(root=_project(tmp_path, escape_at="runtime"), mode="collect",
                  test_cmd=PYTEST_CMD, timeout_s=120)
    assert rep.verdict == "copy_safe"
    assert rep.in_place.n_nodes == rep.copied.n_nodes == 3


def test_collect_cmd_carries_exactly_one_q(tmp_path):
    """`-q -q` is `-qq`, which suppresses the node listing entirely — the
    first run of this module reported `0 node(s)` on both sides and called
    the whence tree copy_safe. Measured, then pinned."""
    rep = compare(root=_project(tmp_path), mode="collect", test_cmd=PYTEST_CMD, timeout_s=120)
    assert rep.test_cmd.count("-q") == 1
    assert rep.in_place.n_nodes == 2


def test_strip_exitfirst():
    out, did = strip_exitfirst(["pytest", "-q", "-x", "tests"])
    assert out == ["pytest", "-q", "tests"] and did
    out, did = strip_exitfirst(["pytest", "-q", "--exitfirst"])
    assert out == ["pytest", "-q"] and did
    out, did = strip_exitfirst(["pytest", "-q"])
    assert out == ["pytest", "-q"] and not did


def test_parse_collect_ignores_error_output():
    out = parse_collect(
        "tests/test_a.py::test_one\n"
        "tests/test_a.py::test_two[x::y]\n"
        "E   FileNotFoundError: /tmp/state/whence/round-414/check-pins.json\n"
        "=== ERRORS ===\n"
        "\n2 tests collected in 0.5s\n")
    assert out == ["tests/test_a.py::test_one", "tests/test_a.py::test_two[x::y]"]


def test_parse_junit_reads_every_status(tmp_path):
    p = tmp_path / "j.xml"
    p.write_text(
        '<testsuites><testsuite name="pytest">'
        '<testcase classname="tests.test_a" name="ok"/>'
        '<testcase classname="tests.test_a" name="bad"><failure message="assert 0"/></testcase>'
        '<testcase classname="tests.test_a" name="boom"><error message="FileNotFoundError"/></testcase>'
        '<testcase classname="tests.test_a" name="skip"><skipped message="no"/></testcase>'
        '</testsuite></testsuites>', encoding="utf-8")
    got = {k: v[0] for k, v in parse_junit(str(p)).items()}
    assert got == {"tests.test_a::ok": "passed", "tests.test_a::bad": "failed",
                   "tests.test_a::boom": "error", "tests.test_a::skip": "skipped"}
    assert parse_junit(str(tmp_path / "missing.xml")) == {}


def test_report_json_round_trips_and_names_the_mode(tmp_path):
    rep = compare(root=_project(tmp_path, escape_at="runtime"), mode="run",
                  test_cmd=PYTEST_CMD, timeout_s=120)
    d = json.loads(json.dumps(rep.as_dict()))
    assert d["mode"] == "run" and d["verdict"] == "copy_breaks" and d["copy_safe"] is False
    assert d["stripped_exitfirst"] is True
    assert d["regressions"][0]["node"].endswith("test_reads_the_registry")
    assert d["in_place"]["where"] == "in_place" and d["copied"]["where"] == "copied"


def test_cli_exit_code_is_the_verdict(tmp_path, capsys):
    clean, broken = _project(tmp_path / "a"), _project(tmp_path / "b", escape_at="runtime")
    out_json = str(tmp_path / "rep.json")
    assert main(["run", "--root", clean, "--test-args", "-q tests", "--timeout", "120"]) == 0
    assert main(["run", "--root", broken, "--test-args", "-q tests", "--timeout", "120",
                 "--json", out_json]) == 1
    assert json.load(open(out_json))["verdict"] == "copy_breaks"
    assert "copyparity(run)" in capsys.readouterr().out


def test_mode_is_validated():
    with pytest.raises(ValueError):
        compare(mode="sideways")


def test_timeout_is_a_non_verdict_not_a_pass(tmp_path):
    """A cap that fires is not evidence of anything — `verdict` says so
    rather than letting an empty node set read as `copy_safe`."""
    root = _project(tmp_path)
    slow = [sys.executable, "-c", "import time; time.sleep(30)"]
    rep = compare(root=root, mode="run", test_cmd=slow, timeout_s=1.0)
    assert rep.verdict == "no_verdict_timeout"
    assert rep.in_place.timed_out and rep.in_place.returncode == -9


def test_report_flags_a_node_green_only_in_the_copy(tmp_path):
    """The other direction is also a defect (a test that passes only when
    the tree is somewhere else), and it gets its own bucket rather than
    being counted as a regression."""
    rep = Report("run", _Side(), _Side(), set(), set(), [],
                 [("tests.t::x", "failed", "passed")], ["pytest"], False)
    assert not rep.copy_safe and rep.verdict == "copy_breaks"
    assert "ONLY-GREEN-IN-COPY" in rep.summary()
    assert rep.as_dict()["improvements"][0]["copied"] == "passed"


class _Side(object):
    where, root, returncode, seconds, timed_out, tail, n_nodes = ("x", "/x", 0, 0.0, False, "", 0)
    nodes = {}

    def as_dict(self, with_nodes=False):
        return {"where": self.where, "n_nodes": 0}
