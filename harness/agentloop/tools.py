"""Tool protocol, registry, and built-in tools.

Every tool:
  - declares name / description / a JSON-Schema-ish params dict (sent to the
    LLM so it knows the call signature),
  - implements run(**args) -> ToolResult,
  - NEVER raises for expected failures (missing file, non-zero exit): those
    come back as ToolResult(ok=False, output=...) so the model can react.
    Only programmer errors (bad tool wiring) raise.

File tools are sandboxed to a root directory: every path is resolved and
checked against the root, so "../../etc/passwd" is rejected, including
symlink escapes (realpath is checked, not just the lexical path).
"""

import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .usage import Usage


@dataclass
class ToolResult:
    ok: bool
    output: str
    # LLM tokens the tool ITSELF spent while running (a sub-agent, an
    # LLM-judge, a summarizer). The loop adds this into the run's usage and
    # re-checks the spend caps right after dispatch, so tool-side spending
    # is neither invisible to `AgentResult.usage` nor a way around
    # max_cost_usd / max_total_tokens. Zero for ordinary tools.
    usage: Usage = field(default_factory=Usage)
    # Extra fields merged into the `tool_result` trace event (e.g. a
    # sub-agent's steps / stop_reason / depth). Never sent to the model.
    meta: Optional[dict] = None

    def as_text(self) -> str:
        prefix = "" if self.ok else "ERROR: "
        return prefix + self.output


class SandboxViolation(ValueError):
    pass


class Tool:
    name = "tool"
    description = ""
    params: Dict[str, dict] = {}  # arg name -> {"type": ..., "description": ...}
    required: List[str] = []
    # May this tool run concurrently with other calls from the same turn?
    # Read-only tools say yes; anything that mutates the workspace says no,
    # and the loop then runs the whole batch serially, in call order.
    parallel_safe: bool = False

    def spec(self) -> dict:
        """Provider-neutral tool spec handed to the LLM."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.params,
                "required": list(self.required),
            },
        }

    def run(self, **args: object) -> ToolResult:
        raise NotImplementedError


class ToolRegistry:
    def __init__(self, tools: Optional[List[Tool]] = None):
        self._tools: Dict[str, Tool] = {}
        for t in tools or []:
            self.register(t)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError("duplicate tool name: %s" % tool.name)
        self._tools[tool.name] = tool

    def specs(self) -> List[dict]:
        return [t.spec() for t in self._tools.values()]

    def names(self) -> List[str]:
        return list(self._tools.keys())

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def dispatch(self, name: str, args: Dict[str, object]) -> ToolResult:
        """Run a tool by name. Unknown tool / bad args / tool crash all come
        back as failed ToolResults — the loop must survive a confused model."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(False, "unknown tool %r; available: %s"
                              % (name, ", ".join(sorted(self._tools))))
        missing = [k for k in tool.required if k not in args]
        if missing:
            return ToolResult(False, "tool %r missing required args: %s"
                              % (name, ", ".join(missing)))
        unexpected = [k for k in args if k not in tool.params]
        if unexpected:
            return ToolResult(False, "tool %r got unexpected args: %s"
                              % (name, ", ".join(unexpected)))
        try:
            return tool.run(**args)
        except Exception as e:  # noqa: BLE001 — tool bugs must not kill the loop
            return ToolResult(False, "tool %r crashed: %s: %s"
                              % (name, type(e).__name__, e))


# ---------------------------------------------------------------- sandbox --

class _Sandboxed:
    def __init__(self, root: str):
        self.root = os.path.realpath(root)
        if not os.path.isdir(self.root):
            raise ValueError("sandbox root is not a directory: %s" % root)

    def resolve(self, rel_path: str) -> str:
        """Map a tool-supplied path to an absolute path inside the sandbox.
        Raises SandboxViolation on escape attempts (.. or symlinks)."""
        if os.path.isabs(rel_path):
            candidate = os.path.realpath(rel_path)
        else:
            candidate = os.path.realpath(os.path.join(self.root, rel_path))
        if candidate != self.root and not candidate.startswith(self.root + os.sep):
            raise SandboxViolation("path escapes sandbox: %r" % rel_path)
        return candidate


# ------------------------------------------------------------- file tools --

class ReadFileTool(Tool):
    name = "read_file"
    parallel_safe = True
    description = "Read a UTF-8 text file inside the workspace. Returns its contents."
    params = {"path": {"type": "string", "description": "path relative to workspace root"}}
    required = ["path"]

    def __init__(self, root: str, max_bytes: int = 256 * 1024):
        self._sb = _Sandboxed(root)
        self._max_bytes = max_bytes

    def run(self, path: str) -> ToolResult:
        try:
            abs_path = self._sb.resolve(path)
        except SandboxViolation as e:
            return ToolResult(False, str(e))
        if not os.path.isfile(abs_path):
            return ToolResult(False, "no such file: %s" % path)
        size = os.path.getsize(abs_path)
        if size > self._max_bytes:
            return ToolResult(False, "file too large (%d bytes > %d limit): %s"
                              % (size, self._max_bytes, path))
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            return ToolResult(True, f.read())


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write (create or overwrite) a UTF-8 text file inside the workspace."
    params = {
        "path": {"type": "string", "description": "path relative to workspace root"},
        "content": {"type": "string", "description": "full file contents"},
    }
    required = ["path", "content"]

    def __init__(self, root: str):
        self._sb = _Sandboxed(root)

    def run(self, path: str, content: str) -> ToolResult:
        try:
            abs_path = self._sb.resolve(path)
        except SandboxViolation as e:
            return ToolResult(False, str(e))
        os.makedirs(os.path.dirname(abs_path) or self._sb.root, exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        return ToolResult(True, "wrote %d chars to %s" % (len(content), path))


class EditFileTool(Tool):
    """Exact-match string replacement, mirroring Claude Code's own Edit tool.

    Exists because WriteFileTool requires resending the ENTIRE file to change
    one line — expensive in tokens, and a race against any edit the model
    forgot it already made earlier in the same turn. edit_file instead
    demands the model quote back the exact text it wants changed, and REFUSES
    to guess: an old_string that doesn't appear, or that appears more than
    once without replace_all, comes back as a failed ToolResult (never a
    silent wrong-occurrence edit) so the model can re-read and re-quote."""

    name = "edit_file"
    description = ("Replace an exact substring in a UTF-8 text file. old_string must "
                   "match exactly once in the file unless replace_all is set; a "
                   "0-match or (without replace_all) multi-match old_string fails "
                   "with no file change, so first read_file and quote back exact text.")
    params = {
        "path": {"type": "string", "description": "path relative to workspace root"},
        "old_string": {"type": "string", "description": "exact text to find (non-empty)"},
        "new_string": {"type": "string", "description": "text to replace it with"},
        "replace_all": {"type": "boolean", "description": "replace every occurrence instead of requiring exactly one; default false"},
    }
    required = ["path", "old_string", "new_string"]

    def __init__(self, root: str):
        self._sb = _Sandboxed(root)

    def run(self, path: str, old_string: str, new_string: str,
            replace_all: bool = False) -> ToolResult:
        try:
            abs_path = self._sb.resolve(path)
        except SandboxViolation as e:
            return ToolResult(False, str(e))
        if not os.path.isfile(abs_path):
            return ToolResult(False, "no such file: %s" % path)
        if not old_string:
            return ToolResult(False, "old_string must be non-empty")
        if old_string == new_string:
            return ToolResult(False, "old_string and new_string are identical: no-op edit")
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        count = content.count(old_string)
        if count == 0:
            return ToolResult(False, "old_string not found in %s (read_file it first and "
                              "quote the exact text)" % path)
        if count > 1 and not replace_all:
            return ToolResult(False, "old_string found %d times in %s; either quote more "
                              "surrounding context to make it unique, or set replace_all=true"
                              % (count, path))
        new_content = content.replace(old_string, new_string) if replace_all \
            else content.replace(old_string, new_string, 1)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        n = count if replace_all else 1
        return ToolResult(True, "replaced %d occurrence%s in %s"
                          % (n, "" if n == 1 else "s", path))


class ListDirTool(Tool):
    name = "list_dir"
    parallel_safe = True
    description = "List entries of a directory inside the workspace (dirs get a trailing /)."
    params = {"path": {"type": "string", "description": "directory, relative to workspace root; default '.'"}}
    required = []

    def __init__(self, root: str):
        self._sb = _Sandboxed(root)

    def run(self, path: str = ".") -> ToolResult:
        try:
            abs_path = self._sb.resolve(path)
        except SandboxViolation as e:
            return ToolResult(False, str(e))
        if not os.path.isdir(abs_path):
            return ToolResult(False, "no such directory: %s" % path)
        entries = []
        for name in sorted(os.listdir(abs_path)):
            full = os.path.join(abs_path, name)
            entries.append(name + "/" if os.path.isdir(full) else name)
        return ToolResult(True, "\n".join(entries) if entries else "(empty)")


# ------------------------------------------------------------- bash tool ---

class BashTool(Tool):
    name = "bash"
    description = ("Run a shell command with the workspace as cwd. "
                   "Returns stdout+stderr and exit code. Times out after a limit.")
    params = {"command": {"type": "string", "description": "shell command to run"}}
    required = ["command"]

    def __init__(self, root: str, timeout_s: float = 30.0):
        self._sb = _Sandboxed(root)
        self._timeout_s = timeout_s

    def run(self, command: str) -> ToolResult:
        # The child gets its own session (so it and every descendant that
        # does not setsid itself form one process group) and on timeout the
        # WHOLE group is SIGKILLed. `subprocess.run(timeout=)` kills only the
        # direct child, then drains the pipes again with NO timeout: a
        # grandchild that inherited stdout (`sleep 30 &`, a server the model
        # started, a test suite's own subprocess) holds the pipe open and the
        # tool blocks for as long as the grandchild lives — round 107 traced
        # 22,071-s "timeouts" in the SWE campaign to exactly this and fixed it
        # in swe/proc.py; this is the same fix for the generic tool. Seconds
        # are read on the monotonic clock, the one the cap itself uses.
        t0 = time.monotonic()
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=self._sb.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        )
        try:
            out, err = proc.communicate(timeout=self._timeout_s)
        except subprocess.TimeoutExpired as e:
            _kill_process_group(proc)
            partial_out = _as_text(e.stdout)
            partial_err = _as_text(e.stderr)
            for stream in (proc.stdout, proc.stderr):
                try:
                    stream.close()          # nothing that escaped the group can hold us
                except OSError:
                    pass
            proc.wait()                     # the child is dead: reap it promptly
            parts = ["command timed out after %.0fs (process group killed, %.1fs elapsed): %s"
                     % (self._timeout_s, time.monotonic() - t0, command)]
            if partial_out.strip():
                parts.append("[partial stdout]\n" + partial_out.rstrip("\n"))
            if partial_err.strip():
                parts.append("[partial stderr]\n" + partial_err.rstrip("\n"))
            return ToolResult(False, "\n".join(parts))
        parts = []
        if out:
            parts.append(out.rstrip("\n"))
        if err:
            parts.append("[stderr]\n" + err.rstrip("\n"))
        parts.append("[exit %d]" % proc.returncode)
        return ToolResult(proc.returncode == 0, "\n".join(parts))


def _as_text(data) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", "replace")
    return str(data)


def _kill_process_group(proc) -> None:
    """SIGKILL the child's whole group (its pgid == its pid thanks to
    start_new_session); fall back to killing the child alone."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass


# ------------------------------------------------------------ search tool --

class SearchTool(Tool):
    name = "search"
    parallel_safe = True
    description = ("Search workspace text files for a substring (case-sensitive). "
                   "Returns 'path:lineno: line' matches.")
    params = {
        "query": {"type": "string", "description": "substring to look for"},
        "path": {"type": "string", "description": "subdirectory to search; default '.'"},
    }
    required = ["query"]

    SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules"}

    def __init__(self, root: str, max_matches: int = 200):
        self._sb = _Sandboxed(root)
        self._max_matches = max_matches

    def run(self, query: str, path: str = ".") -> ToolResult:
        if not query:
            return ToolResult(False, "empty query")
        try:
            base = self._sb.resolve(path)
        except SandboxViolation as e:
            return ToolResult(False, str(e))
        if not os.path.isdir(base):
            return ToolResult(False, "no such directory: %s" % path)
        matches = []
        truncated = False
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in self.SKIP_DIRS)
            for fname in sorted(filenames):
                fpath = os.path.join(dirpath, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        for lineno, line in enumerate(f, 1):
                            if query in line:
                                rel = os.path.relpath(fpath, self._sb.root)
                                matches.append("%s:%d: %s" % (rel, lineno, line.rstrip("\n")))
                                if len(matches) >= self._max_matches:
                                    truncated = True
                                    break
                except (UnicodeDecodeError, OSError):
                    continue  # binary or unreadable file — skip
                if truncated:
                    break
            if truncated:
                break
        if not matches:
            return ToolResult(True, "no matches for %r" % query)
        out = "\n".join(matches)
        if truncated:
            out += "\n... [match limit %d reached]" % self._max_matches
        return ToolResult(True, out)
