"""Crash-safe checkpoint / resume for agent runs.

The program's most common way to lose work is a process dying mid-run
(max-turns kills, OOM, a laptop lid): every step's LLM spend is gone and the
next attempt starts from an empty history. A Checkpoint persists the loop's
COMPLETE state after every step — the (possibly compacted) message history,
step/tool counters, accumulated usage, the estimator's calibration, and any
backend session state — so a fresh process can pick the run up at the step
boundary it died on.

Design decisions (each covered by a test):
  - State is saved at STEP BOUNDARIES only: right after a step's tool results
    are appended (i.e. "before step N+1"), plus once at run start. Everything
    inside a step (compaction, the LLM call, dispatch) is recomputed on
    resume, so a crash mid-step replays that step from its boundary. Tools
    with side effects may therefore run twice for the replayed step — the
    trace records `run_resumed` so a reader can tell.
  - Resume is BYTE-IDENTICAL on the wire: the restored history is the same
    list of dicts the crashed process would have sent (`_chars` caches are
    stripped on save and rebuilt lazily; `raw_content` blocks and elided
    stubs round-trip verbatim), so a resumed run keeps the provider's prompt
    cache warm exactly as an uninterrupted one would — as long as the cache
    TTL has not lapsed.
  - Writes are ATOMIC (tmp file + os.replace): a crash during save leaves
    the previous checkpoint intact, never a half-written JSON.
  - A checkpoint belongs to one task: resuming with a different task string
    raises instead of silently continuing someone else's run.
  - Only `stop_reason == "completed"` is terminal (`done`). Re-running a
    completed checkpoint returns the stored result with no LLM call
    (idempotent runs, cheap to re-invoke from a campaign driver). A run that
    ended on max_steps / budget_exhausted / llm_error keeps its checkpoint
    live: re-run it with a bigger cap, or after the outage, and it continues
    from where it stopped.
  - Backend session state goes through two optional LLM hooks:
    `llm.checkpoint_state() -> dict` and `llm.restore_state(dict)`.
    ClaudeCLILLM uses them for its `--resume` session id; stateless
    backends (AnthropicAPILLM, MockLLM) simply don't define them.
"""

import json
import os
from typing import Optional

VERSION = 1


def strip_message(m: dict) -> dict:
    """A copy of a history message without transient per-process keys."""
    return {k: v for k, v in m.items() if k != "_chars"}


class Checkpoint:
    def __init__(self, path: str):
        self.path = path
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        self.saves = 0

    # ------------------------------------------------------------- io ---
    def exists(self) -> bool:
        return os.path.exists(self.path)

    def load(self) -> Optional[dict]:
        """The stored state dict, or None when there is no checkpoint.
        A corrupt file raises ValueError (never silently starts over — that
        would burn the spend the checkpoint exists to protect)."""
        if not self.exists():
            return None
        with open(self.path, "r", encoding="utf-8") as f:
            text = f.read()
        try:
            state = json.loads(text)
        except ValueError as e:
            raise ValueError("corrupt checkpoint %s: %s" % (self.path, e))
        if not isinstance(state, dict) or state.get("version") != VERSION:
            raise ValueError("checkpoint %s: unsupported version %r"
                             % (self.path, state.get("version") if isinstance(state, dict) else None))
        return state

    def save(self, state: dict) -> None:
        state = dict(state)
        state["version"] = VERSION
        state["messages"] = [strip_message(m) for m in state.get("messages", [])]
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(state, ensure_ascii=False, sort_keys=True))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)   # atomic on POSIX: old file or new file, never neither
        self.saves += 1

    def clear(self) -> None:
        for p in (self.path, self.path + ".tmp"):
            if os.path.exists(p):
                os.remove(p)
