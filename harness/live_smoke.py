#!/usr/bin/env python3
"""Live smoke test for the real-model backends. Costs money; needs credentials.

    python3 live_smoke.py api   # AnthropicAPILLM: needs ANTHROPIC_API_KEY (or _AUTH_TOKEN)
    python3 live_smoke.py cli   # ClaudeCLILLM:    needs the `claude` CLI logged in
    python3 live_smoke.py cli-delegate   # round 31: parent + DelegateTool sub-agent, both via the CLI
    python3 live_smoke.py cli-resume     # round 31: crash after step 1, resume from the checkpoint

Each mode runs one small agentic task (read a file, count something, answer)
with a token cap and prints the AgentResult stop reason, usage, cost, and the
trace path. Exits 0 on a completed run, 2 when credentials are missing (skip),
1 on failure. Nothing here is a unit test — the unit tests use fakes.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentloop import (Agent, AgentConfig, AnthropicAPILLM, Checkpoint, ClaudeCLILLM,  # noqa: E402
                       ContextBudget, DelegateTool, ListDirTool, ReadFileTool, SearchTool,
                       ToolRegistry, TraceLogger, WriteFileTool)
from agentloop.adapters import _default_runner  # noqa: E402
from agentloop.llm import FatalLLMError  # noqa: E402

TASK = ("The workspace contains notes/*.txt. Read every notes file (you may read "
        "several in one turn), then write summary.txt containing one line per file "
        "in the form '<name>: <number of words>'. Finish with a one-sentence answer.")


def make_workspace():
    ws = tempfile.mkdtemp(prefix="agentloop-live-")
    os.makedirs(os.path.join(ws, "notes"))
    for name, words in (("alpha", 7), ("beta", 12), ("gamma", 3)):
        with open(os.path.join(ws, "notes", name + ".txt"), "w") as f:
            f.write(" ".join("w%d" % i for i in range(words)) + "\n")
    return ws


DELEGATE_TASK = (
    "The workspace contains notes/*.txt. Use the `delegate` tool ONCE to hand a sub-agent this job: "
    "read every notes file and report one line per file in the form '<name>: <number of words>'. "
    "Then write the sub-agent's report verbatim to summary.txt and finish with a one-sentence answer.")


class Crash(Exception):
    pass


def run_cli_delegate() -> int:
    ws = make_workspace()
    trace_path = os.path.join(ws, "trace.jsonl")
    trace = TraceLogger(trace_path)
    model = os.environ.get("AGENTLOOP_MODEL", "claude-sonnet-5")

    def factory(spec):
        child = ClaudeCLILLM(model=model)           # its own CLI session = fresh context
        reg = ToolRegistry([ReadFileTool(ws), ListDirTool(ws), SearchTool(ws)])
        return Agent(child, reg, AgentConfig(max_steps=10, max_total_tokens=300_000),
                     trace=trace.tagged(spec.child_id))

    tool = DelegateTool(factory, max_depth=1)
    parent = ClaudeCLILLM(model=model)
    registry = ToolRegistry([ReadFileTool(ws), ListDirTool(ws), WriteFileTool(ws), tool])
    agent = Agent(parent, registry, AgentConfig(max_steps=10, max_total_tokens=400_000), trace=trace)
    result = agent.run(DELEGATE_TASK)
    print("stop_reason:", result.stop_reason, "| steps:", result.steps, "| tool_calls:", result.tool_calls)
    print("delegate calls:", len(tool.results), "| child stop reasons:", [r.stop_reason for r in tool.results],
          "| child steps:", [r.steps for r in tool.results])
    print("usage (parent+children):", result.usage.as_dict(), "| cost_usd:", result.cost_usd)
    cli_cost = parent.usage["cost_usd"] + sum(c.get("child_cost", 0) for c in [])
    print("cli-reported cost_usd: parent %.4f + children %s" % (
        cli_cost, ["%.4f" % r.cost_usd if r.cost_usd is not None else "?" for r in tool.results]))
    print("trace agents:", sorted({str(e.get("agent")) for e in trace.events}))
    print("final:", result.final_text[:300])
    summary = os.path.join(ws, "summary.txt")
    print("summary.txt:", open(summary).read().strip() if os.path.exists(summary) else "(missing)")
    print("trace:", trace_path)
    return 0 if (result.ok and tool.results) else 1


def run_cli_resume() -> int:
    ws = make_workspace()
    trace_path = os.path.join(ws, "trace.jsonl")
    ck = Checkpoint(os.path.join(ws, "checkpoint.json"))
    model = os.environ.get("AGENTLOOP_MODEL", "claude-sonnet-5")
    calls = {"n": 0}

    def crashing_runner(argv, stdin_text, timeout_s):
        calls["n"] += 1
        if calls["n"] == 2:
            raise Crash("simulated process death before CLI call 2")
        return _default_runner(argv, stdin_text, timeout_s)

    registry = ToolRegistry([ReadFileTool(ws), ListDirTool(ws), SearchTool(ws), WriteFileTool(ws)])
    cfg = AgentConfig(max_steps=12, max_total_tokens=400_000)
    first = ClaudeCLILLM(model=model, runner=crashing_runner)
    try:
        Agent(first, registry, cfg, trace=TraceLogger(trace_path)).run(TASK, checkpoint=ck)
        print("no crash happened (the model answered in one turn?) — nothing to resume")
        return 1
    except Crash as e:
        print("crashed as planned:", e)
    st = ck.load()
    print("checkpoint: steps=%d tool_calls=%d session=%s" % (st["steps"], st["tool_calls"],
                                                             st.get("llm_state")))
    second = ClaudeCLILLM(model=model)
    trace = TraceLogger(trace_path + ".resumed")
    result = Agent(second, registry, cfg, trace=trace).run(TASK, checkpoint=ck)
    resumed_argv = second.calls[0]["argv"] if second.calls else []
    print("resumed with --resume:", "--resume" in resumed_argv,
          "| session:", resumed_argv[resumed_argv.index("--resume") + 1] if "--resume" in resumed_argv else None)
    print("stop_reason:", result.stop_reason, "| steps:", result.steps, "| resumed_from:", result.resumed_from,
          "| tool_calls:", result.tool_calls)
    print("usage:", result.usage.as_dict(), "| cost_usd:", result.cost_usd)
    print("final:", result.final_text[:300])
    summary = os.path.join(ws, "summary.txt")
    print("summary.txt:", open(summary).read().strip() if os.path.exists(summary) else "(missing)")
    print("checkpoint done:", ck.load().get("done"), "| trace:", trace_path)
    return 0 if result.ok and result.resumed_from else 1


def main(mode: str) -> int:
    if mode in ("cli-delegate", "cli-resume"):
        if not shutil.which("claude"):
            print("SKIP: claude CLI not on PATH")
            return 2
        return run_cli_delegate() if mode == "cli-delegate" else run_cli_resume()
    if mode == "api":
        try:
            # AGENTLOOP_SERVER_COMPACTION=1 additionally sends the
            # compact-2026-01-12 beta (harmless on a short run — the trigger
            # threshold is far above this task; the point is that the request
            # is accepted and any compaction block replays cleanly).
            llm = AnthropicAPILLM(model=os.environ.get("AGENTLOOP_MODEL", "claude-opus-5"),
                                  max_tokens=4096, effort="low",
                                  cache={"type": "ephemeral"},
                                  server_compaction=bool(os.environ.get("AGENTLOOP_SERVER_COMPACTION")))
        except FatalLLMError as e:
            print("SKIP: %s" % e)
            return 2
    elif mode == "cli":
        if not shutil.which("claude"):
            print("SKIP: claude CLI not on PATH")
            return 2
        llm = ClaudeCLILLM(model=os.environ.get("AGENTLOOP_MODEL", "claude-sonnet-5"))
    else:
        print(__doc__)
        return 1

    ws = make_workspace()
    trace_path = os.path.join(ws, "trace.jsonl")
    registry = ToolRegistry([ReadFileTool(ws), ListDirTool(ws), SearchTool(ws), WriteFileTool(ws)])
    cfg = AgentConfig(max_steps=12, parallel_tools=True, max_total_tokens=400_000,
                      context_budget=ContextBudget(max_input_tokens=60_000, keep_recent_results=3))
    agent = Agent(llm, registry, cfg, trace=TraceLogger(trace_path))
    result = agent.run(TASK)

    print("stop_reason:", result.stop_reason, "| steps:", result.steps, "| tool_calls:", result.tool_calls)
    print("usage:", result.usage.as_dict(), "| cost_usd:", result.cost_usd)
    if mode == "api":
        # >0 from step 2 onward proves the breakpoint placement works on the
        # real cache; ~0 on a multi-step run means a silent invalidator.
        print("cache_hit_rate:", round(result.usage.cache_hit_rate, 3))
    if mode == "cli":
        print("cli-reported cost_usd:", round(llm.usage["cost_usd"], 4))
    print("dispatch modes:", [e["mode"] for e in agent.trace.events if e["event"] == "dispatch"])
    print("final:", result.final_text[:300])
    summary = os.path.join(ws, "summary.txt")
    print("summary.txt:", open(summary).read().strip() if os.path.exists(summary) else "(missing)")
    print("trace:", trace_path)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
