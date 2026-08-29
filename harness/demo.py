#!/usr/bin/env python3
"""Offline end-to-end demo of the agentloop harness.

Runs a 3-task eval suite against MockLLM-scripted agents in a temp workspace —
no network, no API key. Prints the eval report and the JSONL trace location.

    python3 demo.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentloop import (  # noqa: E402
    Agent,
    AgentConfig,
    BashTool,
    ContextBudget,
    EditFileTool,
    EvalTask,
    MockLLM,
    ReadFileTool,
    Scratchpad,
    ScratchpadTool,
    ToolRegistry,
    TraceLogger,
    WriteFileTool,
    run_evals,
)
from agentloop.llm import text_turn, tool_turn  # noqa: E402


def main() -> int:
    workspace = tempfile.mkdtemp(prefix="agentloop-demo-")
    trace_dir = os.path.join(workspace, "traces")
    pad = Scratchpad(os.path.join(workspace, "scratchpad.md"))

    # Scripted "model behavior" per task. In a real deployment the factory
    # would return an Agent wired to an API-backed LLM instead of MockLLM.
    scripts = {
        "write-and-verify": [
            tool_turn("write_file", path="greeting.txt", content="hello, demo\n"),
            tool_turn("bash", command="cat greeting.txt"),
            text_turn("greeting.txt written and verified"),
        ],
        "recover-from-error": [
            tool_turn("read_file", path="does-not-exist.txt"),   # fails...
            tool_turn("write_file", path="recovered.txt",         # ...model adapts
                      content="created after noticing the read error\n"),
            text_turn("recovered from missing file"),
        ],
        "edit-existing-file": [
            tool_turn("write_file", path="config.txt", content="mode=draft\n"),
            tool_turn("edit_file", path="config.txt", old_string="mode=draft",
                      new_string="mode=final"),
            text_turn("flipped config.txt to final mode"),
        ],
        "use-scratchpad": [
            tool_turn("scratchpad", op="append", note="demo ran in %s" % workspace),
            text_turn("noted the workspace path"),
        ],
        # Six 1500-char observations against a ~1200-token budget: the loop
        # must elide old observations to keep every request under budget,
        # while the file written at the end proves the run stayed coherent.
        "long-run-compaction": [
            tool_turn("bash", command="head -c 1500 /dev/zero | tr '\\0' 'x'")
            for _ in range(6)
        ] + [
            tool_turn("write_file", path="compacted.txt", content="survived 6 big observations\n"),
            text_turn("finished the long run"),
        ],
    }

    def make_agent(task: EvalTask) -> Agent:
        registry = ToolRegistry([
            ReadFileTool(workspace), WriteFileTool(workspace), EditFileTool(workspace),
            BashTool(workspace), ScratchpadTool(pad),
        ])
        trace = TraceLogger(path=os.path.join(trace_dir, task.name + ".jsonl"))
        budget = ContextBudget(max_input_tokens=1200, keep_recent_results=1) \
            if task.name == "long-run-compaction" else None
        return Agent(MockLLM(scripts[task.name]), registry,
                     config=AgentConfig(max_steps=10, max_observation_chars=2000,
                                        context_budget=budget, parallel_tools=True),
                     trace=trace, scratchpad=pad)

    def file_has(ws, rel, needle):
        path = os.path.join(ws, rel)
        if not os.path.exists(path):
            return False, "%s missing" % rel
        with open(path, encoding="utf-8") as f:
            content = f.read()
        return needle in content, "%s: %r" % (rel, content.strip())

    tasks = [
        EvalTask("write-and-verify", "Create greeting.txt and verify it.",
                 lambda r, ws: file_has(ws, "greeting.txt", "hello, demo")),
        EvalTask("recover-from-error", "Read a file; if missing, create recovered.txt.",
                 lambda r, ws: file_has(ws, "recovered.txt", "noticing")),
        EvalTask("edit-existing-file", "Write config.txt in draft mode, then edit it to final mode.",
                 lambda r, ws: file_has(ws, "config.txt", "mode=final")),
        EvalTask("use-scratchpad", "Save a note about this run.",
                 lambda r, ws: ("demo ran" in pad.read_all(), "pad has note")),
        EvalTask("long-run-compaction", "Run six noisy commands, then write compacted.txt.",
                 lambda r, ws: (file_has(ws, "compacted.txt", "survived")[0] and r.compactions > 0,
                                "compactions=%d, elided=%d" % (
                                    r.compactions,
                                    sum(1 for m in r.messages if m.get("elided"))))),
    ]

    report = run_evals(tasks, make_agent, workspace)
    print(report.summary())
    print("\ntraces: %s" % trace_dir)
    print("scratchpad: %s" % pad.path)
    return 0 if report.passed == report.total else 1


if __name__ == "__main__":
    raise SystemExit(main())
