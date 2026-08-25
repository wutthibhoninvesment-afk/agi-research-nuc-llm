"""settrace line coverage (swe.coverage): executable lines, collection, triage."""
import json
import os
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import swe.coverage as CV
from swe.fuzz import WHENCE_ROOT

MOD = textwrap.dedent('''
    """module docstring"""

    def used(x):
        """doc"""
        if x > 0:
            return 1
        else:
            return 2

    def unused(y):
        return (y +
                1)

    class K:
        def m(self):
            return 3
''')

TEST = textwrap.dedent('''
    import pkg.mod as M

    def test_used():
        assert M.used(1) == 1
        assert M.K().m() == 3
''')


def _project(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "mod.py").write_text(MOD)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "conftest.py").write_text(
        "import os, sys\nsys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n")
    (tmp_path / "tests" / "test_mod.py").write_text(TEST)
    return str(tmp_path)


def test_executable_lines_skip_docstrings_blank_lines_and_nest():
    ex = CV.executable_lines(MOD)
    lines = MOD.splitlines()
    by_text = dict((i + 1, t.strip()) for i, t in enumerate(lines))
    assert all(by_text[ln] for ln in ex)                       # never a blank line
    assert not any(by_text[ln].startswith('"""doc') for ln in ex if by_text[ln] != '"""module docstring"""')
    # the nested function bodies and the class method are executable
    assert any(by_text[ln] == "return 1" for ln in ex)
    assert any(by_text[ln] == "return 3" for ln in ex)


def test_collect_records_executed_lines_only(tmp_path):
    root = _project(tmp_path)
    cov = CV.collect(root, ["pkg/mod.py"], ("-q", "-p", "no:cacheprovider", "tests"))
    assert cov["_meta"]["returncode"] == 0 and "1 passed" in cov["_meta"]["pytest_tail"]
    hits = cov["pkg/mod.py"]
    lines = MOD.splitlines()
    ln = lambda text: [i + 1 for i, t in enumerate(lines) if t.strip() == text][0]   # noqa: E731
    assert hits[ln("return 1")] == 1
    assert ln("return 2") not in hits
    assert hits[ln("return 3")] == 1
    assert ln("return (y +") not in hits and ln("1)") not in hits
    # the def lines run at import time
    assert hits[ln("def unused(y):")] == 1


def test_file_summary_reports_pct_and_never_called_defs(tmp_path):
    root = _project(tmp_path)
    cov = CV.collect(root, ["pkg/mod.py"], ("-q", "-p", "no:cacheprovider", "tests"))
    s = CV.file_summary(root, "pkg/mod.py", cov)
    assert s["executable"] > s["executed"] > 0 and 0 < s["pct"] < 100
    assert s["never_executed_defs"] == ["unused"]
    by = dict((d["name"], d) for d in s["defs"])
    assert by["used"]["executed"] < by["used"]["executable"]        # else-branch missed
    assert by["K.m"]["pct"] == 100.0
    assert "unused" in CV.render_summary(s)


def test_save_load_roundtrip_and_line_hits_with_end_line(tmp_path):
    cov = {"a.py": {3: 2, 7: 1}, "_meta": {"seconds": 1}}
    p = str(tmp_path / "cov.json")
    CV.save(cov, p)
    back = CV.load(p)
    assert back["a.py"] == {3: 2, 7: 1} and back["_meta"] == {"seconds": 1}
    assert CV.line_hits(back, "a.py", 3) == 2
    assert CV.line_hits(back, "a.py", 5) == 0
    assert CV.line_hits(back, "a.py", 5, end_line=7) == 1        # a later line of the node ran
    assert CV.line_hits(back, "b.py", 3) == 0


def test_triage_splits_survivors_and_flags_instrument_errors():
    cov = {"m.py": {10: 5, 20: 1}}
    ms = [
        {"id": "a", "path": "m.py", "line": 10, "status": "survived"},
        {"id": "b", "path": "m.py", "line": 30, "status": "survived"},
        {"id": "c", "path": "m.py", "line": 18, "end_line": 20, "status": "killed"},
        {"id": "d", "path": "m.py", "line": 40, "status": "killed"},   # killed on an unexecuted line
        {"id": "e", "path": "m.py", "line": 41, "status": "timeout"},
    ]
    t = CV.triage(ms, cov)
    assert t["covered"] == 2 and t["uncovered"] == 3
    assert t["survived_covered"] == 1 and t["survived_uncovered"] == 1
    assert t["killed_on_uncovered"] == 2 and t["killed_on_uncovered_ids"] == ["d", "e"]
    assert ms[2]["covered"] is True and ms[2]["hits"] == 1
    assert ms[1]["covered"] is False and ms[1]["hits"] == 0


def test_real_checkout_lexer_tests_cover_the_lexer():
    cov = CV.collect(WHENCE_ROOT, ["whence/lexer.py", "whence/interp.py"],
                     ("-q", "-p", "no:cacheprovider", "tests/test_lexer.py"))
    assert cov["_meta"]["returncode"] == 0
    lex = CV.file_summary(WHENCE_ROOT, "whence/lexer.py", cov)
    interp = CV.file_summary(WHENCE_ROOT, "whence/interp.py", cov)
    assert lex["pct"] > 90
    assert interp["pct"] < 40 and len(interp["never_executed_defs"]) > 20


def test_cli_analyses_an_existing_coverage_file(tmp_path, capsys):
    cov = CV.collect(WHENCE_ROOT, ["whence/lexer.py"], ("-q", "-p", "no:cacheprovider", "tests/test_lexer.py"))
    p = str(tmp_path / "cov.json")
    CV.save(cov, p)
    mj = tmp_path / "m.json"
    mj.write_text(json.dumps({"mutants": [
        {"id": "x", "path": "whence/lexer.py", "line": 1, "status": "survived"}]}))
    assert CV.main(["--load", p, "--files", "whence/lexer.py", "--mutation-json", str(mj)]) == 0
    out = capsys.readouterr().out
    assert "whence/lexer.py:" in out and "survivors" in out


def test_targeted_collection_traces_only_code_objects_holding_interest_lines(tmp_path):
    root = _project(tmp_path)
    lines = MOD.splitlines()
    ln = lambda text: [i + 1 for i, t in enumerate(lines) if t.strip() == text][0]   # noqa: E731
    interest = {"pkg/mod.py": [ln("return 2")]}
    cov = CV.collect(root, ["pkg/mod.py"], ("-q", "-p", "no:cacheprovider", "tests"), interest=interest)
    assert cov["_meta"]["targeted"] is True and cov["_interest"] == {"pkg/mod.py": [ln("return 2")]}
    hits = cov["pkg/mod.py"]
    assert hits[ln("return 1")] == 1                       # same code object as the interest line
    assert ln("return 3") not in hits                       # K.m was never traced
    assert CV.line_hits(cov, "pkg/mod.py", ln("return 2")) == 0
    assert CV.line_hits(cov, "pkg/mod.py", ln("return 3")) is None    # untraced -> unknown
    ms = [{"id": "a", "path": "pkg/mod.py", "line": ln("return 2"), "status": "survived"},
          {"id": "b", "path": "pkg/mod.py", "line": ln("return 3"), "status": "killed"},
          {"id": "c", "path": "pkg/mod.py", "line": ln("return 1"), "status": "killed"}]
    t = CV.triage(ms, cov)
    assert t["survived_uncovered"] == 1 and t["unknown"] == 2 and t["killed_traced"] == 0
    assert ms[1]["covered"] is None and ms[2]["covered"] is None
    s = CV.file_summary(root, "pkg/mod.py", cov)
    assert s["targeted"] and [d["name"] for d in s["defs"]] == ["used"] and s["never_executed_defs"] == []
    assert "targeted run" in CV.render_summary(s)


def test_interest_from_mutants_takes_every_survivor_and_a_seeded_killed_sample():
    ms = [{"id": "s1", "path": "m.py", "line": 5, "end_line": 6, "status": "survived"},
          {"id": "s2", "path": "m.py", "line": 9, "status": "survived"},
          {"id": "t1", "path": "m.py", "line": 30, "status": "timeout"}] + \
         [{"id": "k%d" % i, "path": "m.py", "line": 100 + i, "status": "killed"} for i in range(20)]
    it = CV.interest_from_mutants(ms, killed_sample=3, seed=1)
    got = it["m.py"]
    assert {5, 6, 9}.issubset(got) and len([x for x in got if x >= 30]) == 3      # timeouts sit in the killed pool
    assert CV.interest_from_mutants(ms, 3, 1) == it and CV.interest_from_mutants(ms, 3, 2) != it
