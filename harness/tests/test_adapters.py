"""ClaudeCLILLM with a fake CLI runner — argv construction, session resume,
tool-block parsing, error mapping. No network, no subprocess."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentloop import Agent, AgentConfig, ToolRegistry, RetryableLLMError, FatalLLMError
from agentloop.adapters import ClaudeCLILLM, parse_turn, render_tools
from agentloop.tools import Tool, ToolResult


def cli_json(result, session="sess-1", **extra):
    d = {"is_error": False, "result": result, "session_id": session,
         "usage": {"input_tokens": 10, "output_tokens": 5}, "total_cost_usd": 0.001}
    d.update(extra)
    return json.dumps(d)


class FakeRunner:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def __call__(self, argv, stdin_text, timeout_s):
        self.calls.append((list(argv), stdin_text))
        rc, out, err = self.outputs.pop(0)
        return rc, out, err


class Echo(Tool):
    name = "echo"
    description = "echo text back"
    params = {"text": {"type": "string", "description": "t"}}
    required = ["text"]

    def run(self, text):
        return ToolResult(True, "echo:" + text)


def test_parse_turn_extracts_single_tool_block():
    t = parse_turn('I will look.\n```tool\n{"name": "echo", "args": {"text": "hi"}}\n```')
    assert t.text == "I will look." and t.tool_calls[0].name == "echo"
    assert t.tool_calls[0].args == {"text": "hi"}
    assert parse_turn("all done").tool_calls == []


def test_malformed_tool_block_becomes_an_error_call_not_a_crash():
    t = parse_turn('```tool\n{not json}\n```')
    assert t.tool_calls[0].name == "__malformed_tool_block__"


def test_bare_unfenced_tool_call_is_recovered():
    # observed live (round 17): the model dropped the ```tool fence and the
    # run ended early with the call as its "final answer"
    t = parse_turn('{"name": "read_file", "args": {"path": "notes/alpha.txt"}}')
    assert t.tool_calls and t.tool_calls[0].name == "read_file"
    assert t.tool_calls[0].args == {"path": "notes/alpha.txt"}
    assert t.text == ""


def test_bare_tool_call_inside_generic_json_fence_is_recovered():
    t = parse_turn('```json\n{"name": "echo", "args": {"text": "hi"}}\n```')
    assert t.tool_calls and t.tool_calls[0].name == "echo"
    t2 = parse_turn('```\n{"name": "echo"}\n```')     # args optional
    assert t2.tool_calls and t2.tool_calls[0].args == {}


def test_task_final_answers_are_not_mistaken_for_tool_calls():
    for final in (
        '{"claims": [{"title": "x", "program": "let a = 1"}]}',
        '```json\n{"verdict": "killed", "program": "let a = 1"}\n```',
        '{"name": "x", "args": {}, "extra": 1}',      # extra key -> not a call
        '{"name": 3, "args": {}}',                    # non-string name
        'Prose first. {"name": "echo", "args": {}}',  # not the whole reply
    ):
        t = parse_turn(final)
        assert t.tool_calls == [], final
        assert t.text


def test_render_tools_marks_optional_args():
    text = render_tools([Echo().spec()])
    assert "echo(text: string)" in text
    spec = Echo().spec()
    spec["input_schema"]["required"] = []
    assert "text?: string" in render_tools([spec])


def test_full_agent_run_through_cli_adapter_resumes_session():
    runner = FakeRunner([
        (0, cli_json('```tool\n{"name": "echo", "args": {"text": "ping"}}\n```'), ""),
        (0, cli_json("final: got it", session="sess-1"), ""),
    ])
    llm = ClaudeCLILLM(model="claude-test", runner=runner)
    agent = Agent(llm, ToolRegistry([Echo()]), config=AgentConfig(max_steps=4))
    r = agent.run("please echo ping")
    assert r.ok and r.final_text == "final: got it" and r.tool_calls == 1
    argv1, prompt1 = runner.calls[0]
    argv2, prompt2 = runner.calls[1]
    assert "--resume" not in argv1 and prompt1 == "please echo ping"
    assert argv2[argv2.index("--resume") + 1] == "sess-1"
    assert prompt2 == "Tool result (echo):\necho:ping"        # only the new observation
    assert argv1[argv1.index("--model") + 1] == "claude-test"
    assert argv1[argv1.index("--tools") + 1] == ""             # built-in tools off
    sys_prompt = argv1[argv1.index("--system-prompt") + 1]
    assert "echo(text: string)" in sys_prompt and "```tool" in sys_prompt
    assert llm.usage["output_tokens"] == 10 and llm.usage["cost_usd"] == pytest.approx(0.002)


def test_cli_failures_map_to_retryable_or_fatal():
    llm = ClaudeCLILLM(runner=FakeRunner([(1, "", "rate limit exceeded")]))
    with pytest.raises(RetryableLLMError):
        llm.complete([{"role": "user", "content": "x"}], [])
    llm = ClaudeCLILLM(runner=FakeRunner([(1, "", "invalid api key")]))
    with pytest.raises(FatalLLMError):
        llm.complete([{"role": "user", "content": "x"}], [])
    llm = ClaudeCLILLM(runner=FakeRunner([(0, "not json", "")]))
    with pytest.raises(FatalLLMError):
        llm.complete([{"role": "user", "content": "x"}], [])
    llm = ClaudeCLILLM(runner=FakeRunner([(0, cli_json("boom", is_error=True), "")]))
    with pytest.raises(RetryableLLMError):
        llm.complete([{"role": "user", "content": "x"}], [])


def test_cli_turn_carries_per_turn_usage():
    runner = FakeRunner([(0, cli_json("done", usage={"input_tokens": 10, "output_tokens": 5,
                                                     "cache_read_input_tokens": 100}), "")])
    llm = ClaudeCLILLM(runner=runner)
    turn = llm.complete([{"role": "user", "content": "u"}], [])
    assert turn.usage.input_tokens == 10 and turn.usage.cache_read_input_tokens == 100
    assert turn.usage.output_tokens == 5 and llm.usage["input_tokens"] == 110
