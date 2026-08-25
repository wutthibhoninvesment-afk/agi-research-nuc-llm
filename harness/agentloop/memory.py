"""Scratchpad memory: a persistent notes file the agent reads/writes via a tool.

Why a file and not a dict: the scratchpad must survive process restarts (a
resumed run keeps its notes) and be human-inspectable next to the trace.

Operations are deliberately tiny — append / read / clear — because the model
uses this as an episodic notebook, not a database.
"""

import io
import os
from typing import Optional

from .tools import Tool, ToolResult


class Scratchpad:
    def __init__(self, path: str):
        self.path = path
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)

    def append(self, note: str) -> int:
        """Append one note (newline-terminated). Returns total note count."""
        with io.open(self.path, "a", encoding="utf-8") as f:
            f.write(note.rstrip("\n") + "\n")
        return len(self.read_all().splitlines())

    def read_all(self) -> str:
        if not os.path.exists(self.path):
            return ""
        with io.open(self.path, "r", encoding="utf-8") as f:
            return f.read()

    def clear(self) -> None:
        with io.open(self.path, "w", encoding="utf-8"):
            pass


class ScratchpadTool(Tool):
    name = "scratchpad"
    description = ("Persistent notes across steps. op='append' saves a note, "
                   "op='read' returns all notes, op='clear' wipes them.")
    params = {
        "op": {"type": "string", "enum": ["append", "read", "clear"],
               "description": "append | read | clear"},
        "note": {"type": "string", "description": "text to append (op='append' only)"},
    }
    required = ["op"]

    def __init__(self, scratchpad: Scratchpad):
        self._pad = scratchpad

    def run(self, op: str, note: Optional[str] = None) -> ToolResult:
        if op == "append":
            if not note:
                return ToolResult(False, "op='append' requires a non-empty 'note'")
            count = self._pad.append(note)
            return ToolResult(True, "noted (%d notes total)" % count)
        if op == "read":
            content = self._pad.read_all()
            return ToolResult(True, content if content else "(scratchpad empty)")
        if op == "clear":
            self._pad.clear()
            return ToolResult(True, "scratchpad cleared")
        return ToolResult(False, "unknown op %r (want append|read|clear)" % op)
