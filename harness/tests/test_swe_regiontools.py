"""Region tools (swe.regiontools): outline / windowed read_file / file-scoped search."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe.regiontools import OutlineTool, ReadRangeTool, GrepTool, outline_source, region_tools
from swe.fuzz import WHENCE_ROOT
from agentloop import ToolRegistry

SRC = '''"""module doc"""
import os


class A(object):
    """A class.
    more"""

    def m(self, x, *args, k=1, **kw):
        return x


def f(a, b):
    """f doc"""
    def inner():
        return 1
    return inner()
'''


def test_outline_source_lists_defs_with_ranges_and_nesting():
    lines = outline_source(SRC)
    assert lines == [
        "class A  [5-10]  # A class.",
        "  def m(self, x, *args, k, **kw)  [9-10]",
        "def f(a, b)  [13-17]  # f doc",
        "  def inner()  [15-16]",
    ]


def test_outline_tool_on_the_real_interpreter_and_error_paths(tmp_path):
    r = OutlineTool(WHENCE_ROOT).run("whence/interp.py")
    assert r.ok and r.output.startswith("whence/interp.py: ")
    assert "class Interpreter" in r.output and "def binop(self, op, left, right, line)" in r.output
    assert "[" in r.output.splitlines()[1]
    assert not OutlineTool(WHENCE_ROOT).run("SPEC.md").ok
    assert not OutlineTool(WHENCE_ROOT).run("nope.py").ok
    assert not OutlineTool(WHENCE_ROOT).run("../../etc/passwd").ok
    (tmp_path / "bad.py").write_text("def (:\n")
    assert "cannot parse" in OutlineTool(str(tmp_path)).run("bad.py").output


def test_read_range_windows_are_capped_numbered_and_resumable(tmp_path):
    (tmp_path / "f.txt").write_text("".join("line %d\n" % i for i in range(1, 501)))
    t = ReadRangeTool(str(tmp_path), max_lines=100)
    r = t.run("f.txt")
    assert r.ok
    head, body = r.output.split("\n", 1)
    assert head == "f.txt: lines 1-100 of 500 (continue with start=101)"   # default window: not "capped"
    assert "capped at 100" in t.run("f.txt", start=1, end=400).output.splitlines()[0]
    assert body.splitlines()[0] == "  1| line 1" and body.splitlines()[-1] == "100| line 100"
    r = t.run("f.txt", start=480, end=490)
    assert r.output.splitlines()[0] == "f.txt: lines 480-490 of 500 (continue with start=491)"
    assert len(r.output.splitlines()) == 12
    r = t.run("f.txt", start=495)
    assert r.output.splitlines()[0] == "f.txt: lines 495-500 of 500"
    assert not t.run("f.txt", start=501).ok
    assert not t.run("f.txt", start=10, end=5).ok
    assert not t.run("f.txt", start="x").ok
    assert not t.run("missing.txt").ok
    assert not t.run("../f.txt").ok
    (tmp_path / "e.txt").write_text("")
    assert t.run("e.txt").output == "e.txt: empty file"


def test_read_range_never_exceeds_cap_on_the_real_file():
    t = ReadRangeTool(WHENCE_ROOT, max_lines=200)
    r = t.run("whence/interp.py", start=1, end=100000)
    assert r.ok and len(r.output.splitlines()) == 201       # header + 200 lines
    assert "capped at 200" in r.output.splitlines()[0]


def test_search_accepts_files_and_directories_with_context(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\ny = needle\nz = 3\n")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("needle here\n")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "c.txt").write_text("needle cached\n")
    t = GrepTool(str(tmp_path))
    r = t.run("needle")
    assert r.ok and r.output.splitlines()[0] == "2 match(es)"
    assert "a.py:2: y = needle" in r.output and "sub/b.txt:1: needle here" in r.output
    assert "cached" not in r.output
    r = t.run("needle", "a.py", context=1)
    assert r.output.splitlines() == ["1 match(es)", "a.py-1- x = 1", "a.py:2: y = needle",
                                     "a.py-3- z = 3", "--"]
    assert t.run("absent").output.startswith("no matches")
    assert not t.run("", "a.py").ok
    assert not t.run("x", "nope").ok
    assert not t.run("x", "../").ok
    t2 = GrepTool(str(tmp_path), max_matches=1)
    assert "truncated at 1" in t2.run("needle").output


def test_region_tools_register_under_the_classic_names():
    reg = ToolRegistry(region_tools(WHENCE_ROOT))
    assert reg.names() == ["outline", "read_file", "search"]
    r = reg.dispatch("search", {"query": "def binop", "path": "whence/interp.py", "context": 1})
    assert r.ok and "def binop(self, op, left, right, line)" in r.output
    # unexpected args are refused by the registry, not the tool
    assert not reg.dispatch("read_file", {"path": "SPEC.md", "lines": 3}).ok
