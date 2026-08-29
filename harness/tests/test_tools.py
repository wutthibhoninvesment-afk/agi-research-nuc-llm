import os
import shutil
import tempfile
import unittest

from agentloop import (
    BashTool,
    EditFileTool,
    ListDirTool,
    ReadFileTool,
    SearchTool,
    Tool,
    ToolRegistry,
    ToolResult,
    WriteFileTool,
)


class SandboxedToolTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="agentloop-test-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def write(self, rel, content):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    # -- read_file ----------------------------------------------------------

    def test_read_file_roundtrip(self):
        self.write("a/b.txt", "hello\nworld\n")
        res = ReadFileTool(self.root).run(path="a/b.txt")
        self.assertTrue(res.ok)
        self.assertEqual(res.output, "hello\nworld\n")

    def test_read_missing_file_is_failed_result_not_exception(self):
        res = ReadFileTool(self.root).run(path="nope.txt")
        self.assertFalse(res.ok)
        self.assertIn("no such file", res.output)

    def test_read_rejects_parent_escape(self):
        res = ReadFileTool(self.root).run(path="../../etc/passwd")
        self.assertFalse(res.ok)
        self.assertIn("escapes sandbox", res.output)

    def test_read_rejects_absolute_path_outside_sandbox(self):
        res = ReadFileTool(self.root).run(path="/etc/passwd")
        self.assertFalse(res.ok)
        self.assertIn("escapes sandbox", res.output)

    def test_read_rejects_symlink_escape(self):
        outside = tempfile.mkdtemp(prefix="agentloop-outside-")
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        with open(os.path.join(outside, "secret.txt"), "w") as f:
            f.write("secret")
        os.symlink(outside, os.path.join(self.root, "link"))
        res = ReadFileTool(self.root).run(path="link/secret.txt")
        self.assertFalse(res.ok)
        self.assertIn("escapes sandbox", res.output)

    def test_read_enforces_size_limit(self):
        self.write("big.txt", "x" * 1000)
        res = ReadFileTool(self.root, max_bytes=100).run(path="big.txt")
        self.assertFalse(res.ok)
        self.assertIn("file too large", res.output)

    # -- write_file ---------------------------------------------------------

    def test_write_creates_parent_dirs(self):
        res = WriteFileTool(self.root).run(path="deep/nested/f.txt", content="hi")
        self.assertTrue(res.ok)
        with open(os.path.join(self.root, "deep/nested/f.txt")) as f:
            self.assertEqual(f.read(), "hi")

    def test_write_rejects_escape(self):
        res = WriteFileTool(self.root).run(path="../evil.txt", content="x")
        self.assertFalse(res.ok)
        self.assertFalse(os.path.exists(os.path.join(self.root, "..", "evil.txt")))

    # -- edit_file ------------------------------------------------------------

    def test_edit_replaces_unique_match(self):
        self.write("f.txt", "hello world\ngoodbye world\n")
        res = EditFileTool(self.root).run(path="f.txt", old_string="hello world",
                                          new_string="hi world")
        self.assertTrue(res.ok)
        self.assertIn("replaced 1 occurrence in f.txt", res.output)
        with open(os.path.join(self.root, "f.txt")) as f:
            self.assertEqual(f.read(), "hi world\ngoodbye world\n")

    def test_edit_success_includes_diff_preview(self):
        self.write("f.txt", "hello world\ngoodbye world\n")
        res = EditFileTool(self.root).run(path="f.txt", old_string="hello world",
                                          new_string="hi world")
        self.assertTrue(res.ok)
        # unified-diff shape: a removed line, an added line, no a/ b/ prefix
        # cruft (just the bare path), and the unchanged line is NOT repeated
        # as noise beyond the diff's own context window.
        self.assertIn("-hello world", res.output)
        self.assertIn("+hi world", res.output)
        self.assertNotIn("--- f.txt", res.output)  # header pair dropped
        self.assertNotIn("+++ f.txt", res.output)

    def test_edit_replace_all_diff_preview_shows_every_hunk(self):
        self.write("f.txt", "x\ny\nx\nz\nx\n")
        res = EditFileTool(self.root).run(path="f.txt", old_string="x", new_string="q",
                                          replace_all=True)
        self.assertTrue(res.ok)
        self.assertEqual(res.output.count("-x"), 3)
        self.assertEqual(res.output.count("+q"), 3)

    def test_edit_missing_file_is_failed_result_not_exception(self):
        res = EditFileTool(self.root).run(path="nope.txt", old_string="a", new_string="b")
        self.assertFalse(res.ok)
        self.assertIn("no such file", res.output)

    def test_edit_zero_matches_fails_without_touching_file(self):
        self.write("f.txt", "hello world\n")
        res = EditFileTool(self.root).run(path="f.txt", old_string="not present",
                                          new_string="x")
        self.assertFalse(res.ok)
        self.assertIn("not found", res.output)
        with open(os.path.join(self.root, "f.txt")) as f:
            self.assertEqual(f.read(), "hello world\n")

    def test_edit_ambiguous_match_rejected_without_replace_all(self):
        self.write("f.txt", "x\nx\nx\n")
        res = EditFileTool(self.root).run(path="f.txt", old_string="x", new_string="y")
        self.assertFalse(res.ok)
        self.assertIn("found 3 times", res.output)
        with open(os.path.join(self.root, "f.txt")) as f:
            self.assertEqual(f.read(), "x\nx\nx\n")   # unchanged: no partial edit

    def test_edit_replace_all_rewrites_every_occurrence(self):
        self.write("f.txt", "x\nx\nx\n")
        res = EditFileTool(self.root).run(path="f.txt", old_string="x", new_string="y",
                                          replace_all=True)
        self.assertTrue(res.ok)
        self.assertIn("replaced 3 occurrences in f.txt", res.output)
        with open(os.path.join(self.root, "f.txt")) as f:
            self.assertEqual(f.read(), "y\ny\ny\n")

    def test_edit_identical_strings_rejected_as_noop(self):
        self.write("f.txt", "same\n")
        res = EditFileTool(self.root).run(path="f.txt", old_string="same", new_string="same")
        self.assertFalse(res.ok)
        self.assertIn("identical", res.output)

    def test_edit_empty_old_string_rejected(self):
        self.write("f.txt", "content\n")
        res = EditFileTool(self.root).run(path="f.txt", old_string="", new_string="x")
        self.assertFalse(res.ok)
        self.assertIn("non-empty", res.output)

    def test_edit_rejects_escape(self):
        res = EditFileTool(self.root).run(path="../evil.txt", old_string="a", new_string="b")
        self.assertFalse(res.ok)
        self.assertIn("escapes sandbox", res.output)

    # -- list_dir -----------------------------------------------------------

    def test_list_dir_marks_directories(self):
        self.write("sub/f.txt", "x")
        self.write("top.txt", "y")
        res = ListDirTool(self.root).run()
        self.assertTrue(res.ok)
        self.assertEqual(res.output.splitlines(), ["sub/", "top.txt"])

    def test_list_missing_dir_fails_cleanly(self):
        res = ListDirTool(self.root).run(path="ghost")
        self.assertFalse(res.ok)

    # -- bash ---------------------------------------------------------------

    def test_bash_captures_stdout_and_exit_code(self):
        res = BashTool(self.root).run(command="echo hello")
        self.assertTrue(res.ok)
        self.assertIn("hello", res.output)
        self.assertIn("[exit 0]", res.output)

    def test_bash_nonzero_exit_is_failed_result_with_stderr(self):
        res = BashTool(self.root).run(command="echo oops >&2; exit 3")
        self.assertFalse(res.ok)
        self.assertIn("[stderr]", res.output)
        self.assertIn("oops", res.output)
        self.assertIn("[exit 3]", res.output)

    def test_bash_runs_in_sandbox_cwd(self):
        res = BashTool(self.root).run(command="pwd")
        self.assertEqual(os.path.realpath(res.output.splitlines()[0]),
                         os.path.realpath(self.root))

    def test_bash_timeout(self):
        res = BashTool(self.root, timeout_s=0.2).run(command="sleep 5")
        self.assertFalse(res.ok)
        self.assertIn("timed out", res.output)

    # -- search -------------------------------------------------------------

    def test_search_reports_path_line_and_text(self):
        self.write("src/x.py", "def foo():\n    return 42\n")
        self.write("src/y.py", "# nothing here\n")
        res = SearchTool(self.root).run(query="return 42")
        self.assertTrue(res.ok)
        self.assertEqual(res.output, "src/x.py:2:     return 42")

    def test_search_no_matches_is_ok_result(self):
        self.write("a.txt", "abc\n")
        res = SearchTool(self.root).run(query="zzz")
        self.assertTrue(res.ok)
        self.assertIn("no matches", res.output)

    def test_search_skips_binary_and_caps_matches(self):
        with open(os.path.join(self.root, "bin.dat"), "wb") as f:
            f.write(b"\x00\xffneedle\x00")
        for i in range(10):
            self.write("f%d.txt" % i, "needle\n" * 5)
        res = SearchTool(self.root, max_matches=7).run(query="needle")
        self.assertTrue(res.ok)
        self.assertIn("match limit 7 reached", res.output)
        self.assertEqual(
            sum(1 for line in res.output.splitlines() if ": needle" in line), 7)

    def test_search_empty_query_rejected(self):
        res = SearchTool(self.root).run(query="")
        self.assertFalse(res.ok)


class EchoTool(Tool):
    name = "echo"
    description = "echo back"
    params = {"text": {"type": "string"}}
    required = ["text"]

    def run(self, text):
        return ToolResult(True, text)


class CrashTool(Tool):
    name = "crash"
    description = "always crashes"
    params = {}
    required = []

    def run(self):
        raise RuntimeError("kaboom")


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.reg = ToolRegistry([EchoTool(), CrashTool()])

    def test_specs_have_provider_neutral_shape(self):
        specs = {s["name"]: s for s in self.reg.specs()}
        self.assertEqual(specs["echo"]["input_schema"]["required"], ["text"])
        self.assertIn("text", specs["echo"]["input_schema"]["properties"])

    def test_dispatch_runs_tool(self):
        res = self.reg.dispatch("echo", {"text": "hi"})
        self.assertTrue(res.ok)
        self.assertEqual(res.output, "hi")

    def test_unknown_tool_lists_available(self):
        res = self.reg.dispatch("ghost", {})
        self.assertFalse(res.ok)
        self.assertIn("unknown tool", res.output)
        self.assertIn("echo", res.output)

    def test_missing_required_arg_rejected(self):
        res = self.reg.dispatch("echo", {})
        self.assertFalse(res.ok)
        self.assertIn("missing required args: text", res.output)

    def test_unexpected_arg_rejected(self):
        res = self.reg.dispatch("echo", {"text": "x", "bogus": 1})
        self.assertFalse(res.ok)
        self.assertIn("unexpected args: bogus", res.output)

    def test_tool_crash_becomes_failed_result(self):
        res = self.reg.dispatch("crash", {})
        self.assertFalse(res.ok)
        self.assertIn("RuntimeError", res.output)
        self.assertIn("kaboom", res.output)

    def test_duplicate_registration_rejected(self):
        with self.assertRaises(ValueError):
            self.reg.register(EchoTool())


if __name__ == "__main__":
    unittest.main()
