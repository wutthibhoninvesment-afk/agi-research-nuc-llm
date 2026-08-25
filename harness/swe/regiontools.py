"""Region tools: let a model read a large source file the way an engineer does.

Round 23's live review died of a tool-design defect, not a model defect: the
trace shows 1 `read_file` of a 65k-char interp.py (truncated to 12k chars by
the observation cap, i.e. the model saw the imports and nothing else), then
17 consecutive `search` calls — two of them failing because `search` only
accepted a *directory* — and never a single `oracle_check`. The model was
trying to read code one grep line at a time.

These three tools make regions addressable:

  outline    an AST index of a Python file: every class/def with its 1-based
             line range and the first docstring line, nested defs indented.
  read_file  numbered lines of a window [start, end]; windows are capped at
             `max_lines` so an observation always fits; the header states the
             file length and where to continue.
  search     substring search over a directory OR a single file, with
             `context` lines around each match.

All are sandboxed to one root and read-only (`parallel_safe`).
"""

import ast
import os

from agentloop.tools import Tool, ToolResult, SandboxViolation, _Sandboxed


def outline_source(source, path="<file>"):
    """Return outline lines for Python `source`; raises SyntaxError."""
    tree = ast.parse(source, filename=path)
    lines = []

    def doc_head(node):
        d = ast.get_docstring(node)
        if not d:
            return ""
        return "  # " + d.strip().splitlines()[0][:70]

    def visit(body, depth):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = "class" if isinstance(node, ast.ClassDef) else "def"
                args = ""
                if kind == "def":
                    a = node.args
                    names = [x.arg for x in a.args]
                    if a.vararg:
                        names.append("*" + a.vararg.arg)
                    names += [x.arg for x in a.kwonlyargs]
                    if a.kwarg:
                        names.append("**" + a.kwarg.arg)
                    args = "(" + ", ".join(names) + ")"
                end = getattr(node, "end_lineno", node.lineno)
                lines.append("%s%s %s%s  [%d-%d]%s"
                             % ("  " * depth, kind, node.name, args, node.lineno, end,
                                doc_head(node)))
                visit(node.body, depth + 1)
    visit(tree.body, 0)
    return lines


class OutlineTool(Tool):
    name = "outline"
    parallel_safe = True
    description = ("Index of a Python file: every class/def with its 1-based line "
                   "range [start-end] and first docstring line, nested defs "
                   "indented. Use it to choose read_file windows instead of "
                   "searching for definitions one by one.")
    params = {"path": {"type": "string", "description": "file path relative to workspace root"}}
    required = ["path"]

    def __init__(self, root):
        self._sb = _Sandboxed(root)

    def run(self, path):
        try:
            full = self._sb.resolve(path)
        except SandboxViolation as e:
            return ToolResult(False, str(e))
        if not os.path.isfile(full):
            return ToolResult(False, "no such file: %s" % path)
        if not full.endswith(".py"):
            return ToolResult(False, "outline supports Python files only; use search on %s" % path)
        with open(full, encoding="utf-8", errors="replace") as f:
            src = f.read()
        try:
            lines = outline_source(src, path)
        except SyntaxError as e:
            return ToolResult(False, "cannot parse %s: %s" % (path, e))
        n = src.count("\n") + (0 if src.endswith("\n") or not src else 1)
        head = "%s: %d lines, %d definitions" % (path, n, len(lines))
        return ToolResult(True, head + "\n" + "\n".join(lines))


class ReadRangeTool(Tool):
    name = "read_file"
    parallel_safe = True
    description = ("Read a window of a UTF-8 text file as numbered lines. `start`/`end` "
                   "are 1-based inclusive line numbers (default: from the top). At most "
                   "max_lines lines per call — the header says how long the file is and "
                   "where to continue. Use outline to find the window of a definition.")
    params = {
        "path": {"type": "string", "description": "file path relative to workspace root"},
        "start": {"type": "integer", "description": "first line (1-based, default 1)"},
        "end": {"type": "integer", "description": "last line inclusive (default start+max_lines-1)"},
    }
    required = ["path"]

    def __init__(self, root, max_lines=200, max_bytes=2 * 1024 * 1024):
        self._sb = _Sandboxed(root)
        self.max_lines = max_lines
        self._max_bytes = max_bytes

    def run(self, path, start=None, end=None):
        try:
            full = self._sb.resolve(path)
        except SandboxViolation as e:
            return ToolResult(False, str(e))
        if not os.path.isfile(full):
            return ToolResult(False, "no such file: %s" % path)
        if os.path.getsize(full) > self._max_bytes:
            return ToolResult(False, "file too large (> %d bytes): %s" % (self._max_bytes, path))
        with open(full, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        n = len(lines)
        try:
            s = int(start) if start is not None else 1
            e = int(end) if end is not None else s + self.max_lines - 1
        except (TypeError, ValueError):
            return ToolResult(False, "start/end must be integers")
        if s < 1:
            s = 1
        if n == 0:
            return ToolResult(True, "%s: empty file" % path)
        if s > n:
            return ToolResult(False, "start %d beyond end of file (%d lines): %s" % (s, n, path))
        if e < s:
            return ToolResult(False, "end %d < start %d" % (e, s))
        clamped = False
        if e - s + 1 > self.max_lines:
            e = s + self.max_lines - 1
            clamped = True
        e = min(e, n)
        head = "%s: lines %d-%d of %d" % (path, s, e, n)
        if clamped:
            head += " (window capped at %d lines; continue with start=%d)" % (self.max_lines, e + 1)
        elif e < n:
            head += " (continue with start=%d)" % (e + 1)
        width = len(str(e))
        body = "\n".join("%*d| %s" % (width, i, lines[i - 1]) for i in range(s, e + 1))
        return ToolResult(True, head + "\n" + body)


class GrepTool(Tool):
    name = "search"
    parallel_safe = True
    SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".pytest_cache"}
    description = ("Search a directory OR a single file for a substring (case-sensitive). "
                   "Returns `path:lineno: line` matches with `context` lines around each "
                   "(default 0, max 10). Prefer outline + read_file for reading code; "
                   "use search to find call sites and string literals.")
    params = {
        "query": {"type": "string", "description": "substring to look for"},
        "path": {"type": "string", "description": "file or directory to search; default '.'"},
        "context": {"type": "integer", "description": "lines of context before/after (0-10)"},
    }
    required = ["query"]

    def __init__(self, root, max_matches=100, max_context=10):
        self._sb = _Sandboxed(root)
        self.max_matches = max_matches
        self.max_context = max_context

    def _files(self, base):
        if os.path.isfile(base):
            yield base
            return
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in self.SKIP_DIRS)
            for fname in sorted(filenames):
                yield os.path.join(dirpath, fname)

    def run(self, query, path=".", context=0):
        if not query:
            return ToolResult(False, "empty query")
        try:
            base = self._sb.resolve(path)
        except SandboxViolation as e:
            return ToolResult(False, str(e))
        if not os.path.exists(base):
            return ToolResult(False, "no such file or directory: %s" % path)
        try:
            ctx = max(0, min(int(context or 0), self.max_context))
        except (TypeError, ValueError):
            return ToolResult(False, "context must be an integer")
        out = []
        count = 0
        truncated = False
        for fpath in self._files(base):
            try:
                with open(fpath, encoding="utf-8") as f:
                    lines = f.read().splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            rel = os.path.relpath(fpath, self._sb.root)
            hits = [i for i, line in enumerate(lines) if query in line]
            for i in hits:
                if count >= self.max_matches:
                    truncated = True
                    break
                count += 1
                if ctx == 0:
                    out.append("%s:%d: %s" % (rel, i + 1, lines[i]))
                    continue
                lo, hi = max(0, i - ctx), min(len(lines) - 1, i + ctx)
                for j in range(lo, hi + 1):
                    mark = ":" if j == i else "-"
                    out.append("%s%s%d%s %s" % (rel, mark, j + 1, mark, lines[j]))
                out.append("--")
            if truncated:
                break
        if not out:
            return ToolResult(True, "no matches for %r in %s" % (query, path))
        head = "%d match(es)%s" % (count, " (truncated at %d)" % self.max_matches if truncated else "")
        return ToolResult(True, head + "\n" + "\n".join(out))


class CallBudget(object):
    """A shared counter: N tool calls across every tool that carries it.

    Round 101's live review spent 28 of 30 steps on outline/read_file/search
    (23 windowed reads = the whole 2227-line file) and ran the oracle once —
    a budget note in the prompt did nothing. This makes the budget a fact
    the tools enforce: once it is spent, every read tool answers with an
    error that says so and names what is left to do."""

    def __init__(self, n, exhausted_hint="use the probing/verification tools and give your answer"):
        self.total = int(n)
        self.left = int(n)
        self.hint = exhausted_hint
        self.refused = 0

    def take(self):
        if self.left <= 0:
            self.refused += 1
            return False
        self.left -= 1
        return True

    def note(self):
        return " (shares a read budget of %d calls with the other read tools)" % self.total


class BudgetedTool(Tool):
    """Wrap a read-only tool so it draws from a CallBudget."""

    def __init__(self, tool, budget):
        self.tool = tool
        self.budget = budget
        self.name = tool.name
        self.description = tool.description + budget.note()
        self.params = tool.params
        self.required = tool.required
        self.parallel_safe = tool.parallel_safe

    def run(self, **args):
        if not self.budget.take():
            return ToolResult(False, "read budget exhausted (%d calls used): no more %s; %s"
                              % (self.budget.total, self.name, self.budget.hint))
        r = self.tool.run(**args)
        if self.budget.left <= 3 and r.ok:
            r = ToolResult(True, r.output + "\n[read budget: %d call(s) left]" % self.budget.left)
        return r


def region_tools(root, max_lines=200, budget=None):
    """The three tools, ready for a ToolRegistry; `budget` (a CallBudget)
    makes them share one call allowance."""
    tools = [OutlineTool(root), ReadRangeTool(root, max_lines=max_lines), GrepTool(root)]
    if budget is not None:
        tools = [BudgetedTool(t, budget) for t in tools]
    return tools
