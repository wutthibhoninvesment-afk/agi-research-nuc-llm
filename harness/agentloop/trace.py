"""JSONL trace logging.

One event per line so traces stream, tail, and grep cleanly. Every event has
`ts` (wall clock, ISO-8601 UTC), `event`, and event-specific fields. The
clock is injectable for deterministic tests.

Event types emitted by the agent loop:
    run_start, llm_request, llm_response, llm_retry, tool_call, tool_result,
    run_end
"""

import io
import json
import os
from datetime import datetime, timezone
from typing import Callable, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TraceLogger:
    def __init__(self, path: Optional[str] = None, clock: Callable[[], str] = _utc_now_iso,
                 tag: Optional[str] = None):
        """path=None -> in-memory only (tests read .events).

        `tag`, when set, is stamped on every record as `agent` — see
        tagged(). A top-level run normally has no tag."""
        self._path = path
        self._clock = clock
        self.tag = tag
        self.events = []  # kept in memory too, for assertions and summaries
        if path:
            parent = os.path.dirname(os.path.abspath(path))
            os.makedirs(parent, exist_ok=True)
            # truncate: one file per run
            with io.open(path, "w", encoding="utf-8"):
                pass

    def tagged(self, tag: str) -> "TraceLogger":
        """A logger that shares this one's file AND in-memory event list but
        stamps `agent: <tag>` on every record it writes. Sub-agents
        (delegate.py) log through one of these so a nested run's events
        interleave in the parent's trace and stay attributable — one JSONL
        per top-level run, `agent` absent on the parent's own records.
        Nested tags chain: parent.tagged("d1").tagged("d1.2") -> "d1/d1.2"."""
        child = TraceLogger.__new__(TraceLogger)   # no truncation of the file
        child._path = self._path
        child._clock = self._clock
        child.tag = (self.tag + "/" + tag) if self.tag else tag
        child.events = self.events
        return child

    def log(self, event: str, **fields: object) -> dict:
        record = {"ts": self._clock(), "event": event}
        if self.tag is not None:
            record["agent"] = self.tag
        record.update(fields)
        self.events.append(record)
        if self._path:
            with io.open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=repr) + "\n")
        return record

    def count(self, event: str, agent: object = "*") -> int:
        """Events of this type; `agent="*"` counts every logger sharing the
        list, `agent=None` only untagged (top-level) records, a string only
        that tag."""
        return sum(1 for e in self.events
                   if e["event"] == event and (agent == "*" or e.get("agent") == agent))
