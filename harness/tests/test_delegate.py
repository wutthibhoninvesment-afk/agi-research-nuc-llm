"""Round 31: ToolResult.usage/meta roll-up, DelegateTool sub-agents, tagged
nested traces, caps re-checked after dispatch."""
import os
import threading

import pytest

from agentloop import (Agent, AgentConfig, AssistantTurn, ChildSpec, DelegateTool, ListDirTool,
                       MockLLM, ReadFileTool, ToolCall, ToolRegistry, TraceLogger)
from agentloop.llm import text_turn, tool_turn
from agentloop.tools import Tool, ToolResult
from agentloop.usage import Usage


class Spender(Tool):
    """A tool that reports LLM spend of its own (an LLM-judge, say)."""
    name = "spend"
    description = "spends tokens"
    params = {"n": {"type": "integer", "description": "tokens"}}
    required = ["n"]
    parallel_safe = True

    def run(self, n: int) -> ToolResult:
        return ToolResult(True, "spent %d" % n, usage=Usage(input_tokens=n, output_tokens=n // 10),
                          meta={"kind": "judge", "n": n})


def _agent(script, tools, cfg=None, trace=None, model="claude-opus-5"):
    llm = MockLLM(script)
    llm.model = model
    return Agent(llm, ToolRegistry(tools), cfg or AgentConfig(max_steps=10), trace=trace), llm


# ----------------------------------------------------------- ToolResult --

def test_toolresult_defaults_are_backwards_compatible():
    r = ToolResult(False, "boom")
    assert r.usage.is_zero and r.meta is None and r.as_text() == "ERROR: boom"


def test_tool_usage_rolls_into_run_usage_cost_and_trace():
    agent, llm = _agent([tool_turn("spend", n=1000), text_turn("done")], [Spender()],
                        AgentConfig(max_steps=5))
    res = agent.run("go")
    assert res.ok
    assert res.usage == Usage(input_tokens=1000, output_tokens=100)
    assert res.cost_usd == pytest.approx((1000 * 5.0 + 100 * 25.0) / 1e6)
    ev = [e for e in agent.trace.events if e["event"] == "tool_result"][0]
    assert ev["usage"]["input_tokens"] == 1000
    assert ev["meta"] == {"kind": "judge", "n": 1000}
    # the model-visible observation carries none of that
    assert llm.requests[1]["messages"][-1]["content"] == "spent 1000"


def test_cost_cap_is_checked_right_after_dispatch():
    agent, llm = _agent([tool_turn("spend", n=1_000_000), text_turn("never")], [Spender()],
                        AgentConfig(max_steps=5, max_cost_usd=1.0))
    res = agent.run("go")
    assert res.stop_reason == "budget_exhausted"
    assert res.error.startswith("cost cap")
    assert llm.calls_made == 1                      # no further completion
    assert res.messages[-1]["role"] == "tool"        # the observation was still appended
    assert res.tool_calls == 1


def test_token_cap_after_dispatch_and_ordinary_tools_are_unaffected():
    agent, llm = _agent([tool_turn("spend", n=500), tool_turn("spend", n=600), text_turn("x")],
                        [Spender()], AgentConfig(max_steps=5, max_total_tokens=1000))
    res = agent.run("go")
    assert res.stop_reason == "budget_exhausted" and res.steps == 2 and llm.calls_made == 2
    assert res.usage.total == 550 + 660
    ev = [e for e in agent.trace.events if e["event"] == "tool_result"]
    assert all("usage" in e for e in ev)


# ---------------------------------------------------------- DelegateTool --

def _child_factory(ws, scripts, trace=None, cfg=None, wire_child_tool=None, seen=None):
    """scripts: list of MockLLM scripts handed out in creation order."""
    made = []

    def factory(spec: ChildSpec) -> Agent:
        if seen is not None:
            seen.append(spec)
        script = scripts[len(made)]
        made.append(script)
        llm = MockLLM(script)
        llm.model = "claude-opus-5"
        tools = [ListDirTool(ws), ReadFileTool(ws)]
        if wire_child_tool is not None:
            ct = wire_child_tool.child_tool()
            if ct is not None:
                tools.append(ct)
        t = trace.tagged(spec.child_id) if trace is not None else None
        return Agent(llm, ToolRegistry(tools), cfg or AgentConfig(max_steps=6), trace=t)
    factory.made = made
    return factory


def test_delegate_runs_child_with_fresh_history_and_reports_only_final_text(tmp_path):
    ws = str(tmp_path)
    open(os.path.join(ws, "a.txt"), "w").write("x")
    seen = []
    child_turns = [AssistantTurn(tool_calls=[ToolCall("list_dir", {"path": "."}, "c1")],
                                 usage=Usage(200, 20)),
                   AssistantTurn(text="1 file: a.txt", usage=Usage(300, 30))]
    factory = _child_factory(ws, [child_turns], seen=seen)
    tool = DelegateTool(factory)
    agent, llm = _agent([AssistantTurn(tool_calls=[ToolCall("delegate", {"task": "count files", "context": "dir is ."}, "p1")],
                                       usage=Usage(1000, 10)),
                         AssistantTurn(text="answer: 1", usage=Usage(1100, 5))],
                        [tool], AgentConfig(max_steps=5))
    res = agent.run("how many files?")
    assert res.ok and res.final_text == "answer: 1"
    # the child saw a fresh history: system + framed task only
    child_llm_req = None
    spec = seen[0]
    assert spec.depth == 1 and spec.child_id == "d1.1" and spec.raw_task == "count files"
    assert "depth 1" in spec.task and "count files" in spec.task
    assert spec.task.endswith("Context from the caller:\ndir is .")
    # parent observation = child's final text + footer, nothing of its history
    obs = llm.requests[1]["messages"][-1]
    assert obs["role"] == "tool" and obs["ok"] is True
    assert obs["content"] == "1 file: a.txt\n[sub-agent d1.1: completed after 2 steps / 1 tool calls, $%.4f]" % (
        (500 * 5.0 + 50 * 25.0) / 1e6)
    # cost roll-up: parent turns + child turns
    assert res.usage == Usage(2100, 15) + Usage(500, 50)
    ev = [e for e in agent.trace.events if e["event"] == "tool_result"][0]
    assert ev["meta"]["child_stop_reason"] == "completed" and ev["meta"]["child_steps"] == 2
    assert ev["usage"] == Usage(500, 50).as_dict()
    assert tool.results[0].final_text == "1 file: a.txt"


def test_delegate_rejects_empty_task_without_spawning(tmp_path):
    factory = _child_factory(str(tmp_path), [[text_turn("never")]])
    r = DelegateTool(factory).run(task="   ")
    assert not r.ok and "non-empty" in r.output and factory.made == []


def test_depth_limit_and_child_tool():
    factory = _child_factory(".", [])
    top = DelegateTool(factory, depth=1, max_depth=2)
    child = top.child_tool()
    assert child is not None and child.depth == 2 and child.max_depth == 2 and child.factory is factory
    assert child.child_tool() is None
    assert top.child_tool(owner="d1.7").owner == "d1.7"
    over = DelegateTool(factory, depth=3, max_depth=2)
    r = over.run(task="anything")
    assert not r.ok and "depth limit 2" in r.output and factory.made == []
    with pytest.raises(ValueError):
        DelegateTool(factory, depth=0)


def test_nested_delegation_tags_trace_and_stops_at_max_depth(tmp_path):
    ws = str(tmp_path)
    trace = TraceLogger()
    # child (depth 1) delegates once more; grandchild (depth 2) just answers.
    child_script = [tool_turn("delegate", task="inner"), text_turn("child done")]
    grandchild_script = [text_turn("grandchild done")]
    holder = {}

    def factory(spec):
        script = child_script if spec.depth == 1 else grandchild_script
        llm = MockLLM(script)
        tools = [ListDirTool(ws)]
        ct = holder["top"].child_tool(owner=spec.child_id) if spec.depth == 1 else None
        if ct is not None:
            tools.append(ct)
        # a depth-2 child must not carry a delegate tool at all
        if spec.depth == 2:
            assert all(t.name != "delegate" for t in tools)
        return Agent(llm, ToolRegistry(tools), AgentConfig(max_steps=4), trace=trace.tagged(spec.child_id))

    holder["top"] = DelegateTool(factory, max_depth=2)
    agent = Agent(MockLLM([tool_turn("delegate", task="outer"), text_turn("top done")]),
                  ToolRegistry([holder["top"]]), AgentConfig(max_steps=4), trace=trace)
    res = agent.run("nest")
    assert res.ok and res.final_text == "top done"
    assert trace.count("run_end") == 3
    assert trace.count("run_end", agent=None) == 1
    tags = sorted({e.get("agent") for e in trace.events if e["event"] == "run_end"}, key=str)
    assert tags == [None, "d1.1", "d1.1/d2.1"]
    # the parent's own tool_result carries the child's summary meta
    ev = [e for e in trace.events if e["event"] == "tool_result" and e.get("agent") is None][0]
    assert ev["meta"]["child_id"] == "d1.1" and ev["meta"]["child_tool_calls"] == 1


def test_child_stopping_early_is_an_error_observation(tmp_path):
    ws = str(tmp_path)
    factory = _child_factory(ws, [[tool_turn("list_dir"), tool_turn("list_dir"), text_turn("late")]],
                             cfg=AgentConfig(max_steps=1))
    agent, llm = _agent([tool_turn("delegate", task="t"), text_turn("gave up")],
                        [DelegateTool(factory)], AgentConfig(max_steps=4))
    res = agent.run("x")
    assert res.ok
    obs = llm.requests[1]["messages"][-1]
    assert obs["ok"] is False
    assert obs["content"].startswith("ERROR: sub-agent stopped early: max_steps")
    assert "[sub-agent d1.1: max_steps after 1 steps / 1 tool calls" in obs["content"]


def test_factory_crash_becomes_tool_crash_observation():
    def factory(spec):
        raise RuntimeError("no llm today")
    agent, llm = _agent([tool_turn("delegate", task="t"), text_turn("ok")],
                        [DelegateTool(factory)], AgentConfig(max_steps=4))
    res = agent.run("x")
    assert res.ok
    assert "tool 'delegate' crashed: RuntimeError: no llm today" in llm.requests[1]["messages"][-1]["content"]


def test_parallel_safety_is_opt_in_and_children_run_concurrently(tmp_path):
    ws = str(tmp_path)
    barrier = threading.Barrier(2, timeout=0.3)

    def factory(spec):
        class Wait(Tool):
            name, description, params, required, parallel_safe = "wait", "w", {}, [], True

            def run(self):
                barrier.wait()          # only passes if both children are in flight
                return ToolResult(True, "waited")
        return Agent(MockLLM([tool_turn("wait"), text_turn("child " + spec.child_id)]),
                     ToolRegistry([Wait()]), AgentConfig(max_steps=3))

    two = AssistantTurn(tool_calls=[ToolCall("delegate", {"task": "a"}, "p1"),
                                    ToolCall("delegate", {"task": "b"}, "p2")])
    # default: not parallel_safe -> serial -> each child's barrier wait times
    # out INSIDE the child (its own tool-crash observation); the parent only
    # ever sees the children's final reports.
    tool = DelegateTool(factory)
    agent, llm = _agent([two, text_turn("done")], [tool],
                        AgentConfig(max_steps=3, parallel_tools=True))
    res = agent.run("x")
    modes = [e["mode"] for e in agent.trace.events if e["event"] == "dispatch"]
    assert modes == ["serial"]
    for child in tool.results:
        assert "BrokenBarrierError" in child.messages[3]["content"]
    obs = [m["content"] for m in llm.requests[1]["messages"] if m["role"] == "tool"]
    assert [o.split("\n")[0] for o in obs] == ["child d1.1", "child d1.2"]
    barrier.reset()
    tool = DelegateTool(factory, parallel_safe=True)
    agent, llm = _agent([two, text_turn("done")], [tool],
                        AgentConfig(max_steps=3, parallel_tools=True))
    res = agent.run("x")
    assert res.ok
    assert [e["mode"] for e in agent.trace.events if e["event"] == "dispatch"] == ["parallel"]
    for child in tool.results:
        assert child.messages[3]["content"] == "waited"      # both passed the barrier together
    obs = [m["content"] for m in llm.requests[1]["messages"] if m["role"] == "tool"]
    assert [o.split("\n")[0] for o in obs] == ["child d1.1", "child d1.2"]   # call order kept


def test_parent_cap_stops_run_after_child_overspend(tmp_path):
    ws = str(tmp_path)
    factory = _child_factory(ws, [[AssistantTurn(text="pricey", usage=Usage(2_000_000, 0))]])
    agent, llm = _agent([tool_turn("delegate", task="t"), text_turn("never")],
                        [DelegateTool(factory)], AgentConfig(max_steps=4, max_cost_usd=5.0))
    res = agent.run("x")
    assert res.stop_reason == "budget_exhausted" and llm.calls_made == 1
    assert res.usage.input_tokens == 2_000_000 and res.cost_usd == pytest.approx(10.0)


def test_spec_shape_and_tool_spec_is_wire_ready():
    spec = DelegateTool(lambda s: None).spec()
    assert spec["name"] == "delegate"
    assert set(spec["input_schema"]["properties"]) == {"task", "context"}
    assert spec["input_schema"]["required"] == ["task"]
