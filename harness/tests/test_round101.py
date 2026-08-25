"""Round 101: wrap-up turn on max_steps, shared read budgets for region tools."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentloop import Agent, AgentConfig, ToolRegistry, MockLLM
from agentloop.llm import text_turn, tool_turn, FatalLLMError
from agentloop.tools import Tool, ToolResult
from swe.fuzz import WHENCE_ROOT
from swe.regiontools import CallBudget, BudgetedTool, region_tools, ReadRangeTool
import swe.review as R


class Echo(Tool):
    name = "echo"
    description = "echo"
    params = {"s": {"type": "string", "description": "text"}}
    required = ["s"]
    parallel_safe = True

    def __init__(self):
        self.calls = 0

    def run(self, s):
        self.calls += 1
        return ToolResult(True, "echo:" + s)


# ----------------------------------------------------------------- wrap-up --

def test_wrap_up_turn_asks_for_the_answer_without_tools():
    llm = MockLLM([tool_turn("echo", s="a"), tool_turn("echo", s="b"),
                   text_turn('```json\n{"claims": []}\n```')])
    tool = Echo()
    cfg = AgentConfig(max_steps=2, wrap_up_on_max_steps=True)
    r = Agent(llm, ToolRegistry([tool]), config=cfg).run("go")
    assert r.stop_reason == "max_steps" and r.steps == 2 and tool.calls == 2
    assert r.final_text == '```json\n{"claims": []}\n```'
    assert llm.calls_made == 3
    last = llm.requests[-1]
    assert last["tools"] == []                                     # nothing offered
    assert last["messages"][-1]["role"] == "user"
    assert "budget is exhausted" in last["messages"][-1]["content"]
    assert r.messages[-1] == {"role": "assistant", "content": r.final_text, "tool_calls": []}


def test_wrap_up_ignores_tool_calls_the_model_still_emits_and_is_off_by_default():
    llm = MockLLM([tool_turn("echo", s="a"), tool_turn("echo", s="z")])
    tool = Echo()
    r = Agent(llm, ToolRegistry([tool]), config=AgentConfig(max_steps=1, wrap_up_on_max_steps=True)).run("go")
    assert r.stop_reason == "max_steps" and r.final_text == "" and tool.calls == 1   # 'z' never ran
    llm2 = MockLLM([tool_turn("echo", s="a")])
    r2 = Agent(llm2, ToolRegistry([Echo()]), config=AgentConfig(max_steps=1)).run("go")
    assert r2.stop_reason == "max_steps" and llm2.calls_made == 1


def test_wrap_up_failure_is_recorded_not_raised():
    llm = MockLLM([tool_turn("echo", s="a")])               # script exhausted at the wrap-up call
    r = Agent(llm, ToolRegistry([Echo()]),
              config=AgentConfig(max_steps=1, wrap_up_on_max_steps=True)).run("go")
    assert r.stop_reason == "max_steps" and r.final_text == ""
    assert r.error and "wrap-up failed" in r.error
    assert r.messages[-1]["role"] == "tool"                 # the wrap-up user turn was rolled back


def test_wrap_up_is_traced_and_counted_in_usage(tmp_path):
    from agentloop import TraceLogger
    from agentloop.usage import Usage
    t = text_turn("final")
    t.usage = Usage(input_tokens=10, output_tokens=5)
    llm = MockLLM([tool_turn("echo", s="a"), t])
    trace = TraceLogger(str(tmp_path / "t.jsonl"))
    r = Agent(llm, ToolRegistry([Echo()]), config=AgentConfig(max_steps=1, wrap_up_on_max_steps=True),
              trace=trace).run("go")
    assert r.usage.output_tokens == 5
    events = [json.loads(l) for l in open(str(tmp_path / "t.jsonl"))]
    w = [e for e in events if e["event"] == "wrap_up"]
    assert len(w) == 1 and w[0]["step"] == 2 and w[0]["text_chars"] == 5 and w[0]["ignored_tool_calls"] == []


# ------------------------------------------------------------- read budget --

def test_call_budget_refuses_after_n_calls_and_marks_the_tail():
    b = CallBudget(2, "answer now")
    t = BudgetedTool(Echo(), b)
    assert t.name == "echo" and "read budget of 2 calls" in t.description
    r1 = t.run(s="x")
    assert r1.ok and r1.output.startswith("echo:x") and "1 call(s) left" in r1.output
    r2 = t.run(s="y")
    assert r2.ok and "0 call(s) left" in r2.output
    r3 = t.run(s="z")
    assert not r3.ok and "read budget exhausted (2 calls used)" in r3.output and "answer now" in r3.output
    assert b.left == 0 and b.refused == 1 and t.tool.calls == 2


def test_region_tools_share_one_budget():
    b = CallBudget(2)
    tools = region_tools(WHENCE_ROOT, budget=b)
    reg = ToolRegistry(tools)
    assert reg.dispatch("outline", {"path": "whence/lexer.py"}).ok
    assert reg.dispatch("read_file", {"path": "whence/lexer.py", "start": 1, "end": 5}).ok
    r = reg.dispatch("search", {"query": "def tokenize", "path": "whence/lexer.py"})
    assert not r.ok and "exhausted" in r.output
    assert all(isinstance(t, BudgetedTool) for t in tools)
    assert not any(isinstance(t, BudgetedTool) for t in region_tools(WHENCE_ROOT))


def test_review_task_with_read_budget_states_it_and_enforces_it():
    registry, prompt = R.review_task(WHENCE_ROOT, ("whence/interp.py",), max_steps=10, read_budget=1)
    assert "hard budget of 1 calls" in prompt and "budget of 10 tool steps" in prompt
    assert registry.dispatch("outline", {"path": "whence/interp.py"}).ok
    r = registry.dispatch("read_file", {"path": "whence/interp.py", "start": 1, "end": 3})
    assert not r.ok and "oracle_check" in r.output
    # the probing tools are untouched by the budget
    assert registry.dispatch("oracle_check", {"source": "let a = 1\n", "oracles": "totality"}).ok
    reg2, prompt2 = R.review_task(WHENCE_ROOT, ("whence/interp.py",), max_steps=10)
    assert "hard budget" not in prompt2
