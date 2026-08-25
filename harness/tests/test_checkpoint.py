"""Round 31: crash-safe checkpoint / resume."""
import json
import os

import pytest

from agentloop import (Agent, AgentConfig, AssistantTurn, Checkpoint, ClaudeCLILLM, ContextBudget,
                       FlakyLLM, MockLLM, ReadFileTool, RetryPolicy, ToolCall, ToolRegistry,
                       TokenEstimator, TraceLogger)
from agentloop.checkpoint import strip_message
from agentloop.llm import text_turn
from agentloop.usage import Usage


class Crash(Exception):
    """Not an LLM error: simulates the process dying mid-LLM-call."""


class CrashingLLM(MockLLM):
    def __init__(self, script, crash_at):
        super().__init__(script)
        self.crash_at = crash_at

    def complete(self, messages, tools):
        if self._cursor + 1 == self.crash_at:
            raise Crash("died during call %d" % self.crash_at)
        return super().complete(messages, tools)


def _ws(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    for i in range(3):
        (ws / ("f%d.txt" % i)).write_text("line %d\n" % i * (40 * (i + 1)))
    return str(ws)


def _script(with_raw=False):
    def read(i, cid, usage):
        t = AssistantTurn(tool_calls=[ToolCall("read_file", {"path": "f%d.txt" % i}, cid)],
                          usage=usage)
        if with_raw:
            t.raw_content = [{"type": "thinking", "thinking": "hm %d" % i, "signature": "sig%d" % i},
                             {"type": "tool_use", "id": cid, "name": "read_file",
                              "input": {"path": "f%d.txt" % i}}]
        return t
    return [read(0, "c1", Usage(100, 10)), read(1, "c2", Usage(200, 10)),
            read(2, "c3", Usage(300, 10)), AssistantTurn(text="all read", usage=Usage(400, 5))]


def _cfg(budget):
    return AgentConfig(max_steps=10,
                       context_budget=ContextBudget(max_input_tokens=budget, keep_recent_results=1)
                       if budget else None)


def _wire(req):
    return json.dumps([strip_message(m) for m in req["messages"]], sort_keys=True)


@pytest.mark.parametrize("budget,with_raw", [(None, False), (120, True)])
def test_resume_sends_byte_identical_request(tmp_path, budget, with_raw):
    ws = _ws(tmp_path)
    tools = lambda: ToolRegistry([ReadFileTool(ws)])  # noqa: E731
    # A: uninterrupted reference run
    a_llm = MockLLM(_script(with_raw))
    a = Agent(a_llm, tools(), _cfg(budget)).run("read all")
    assert a.ok and a.steps == 4
    if budget:
        assert a.compactions >= 1
    # B: same run, process dies during the 3rd LLM call
    ck = Checkpoint(str(tmp_path / "ck.json"))
    b_llm = CrashingLLM(_script(with_raw), crash_at=3)
    with pytest.raises(Crash):
        Agent(b_llm, tools(), _cfg(budget)).run("read all", checkpoint=ck)
    st = ck.load()
    assert st["steps"] == 2 and st["tool_calls"] == 2 and not st["done"]
    assert all("_chars" not in m for m in st["messages"])
    # C: a fresh process — new Agent, new estimator, new LLM holding the rest of the script
    c_llm = MockLLM(_script(with_raw)[2:])
    trace = TraceLogger()
    c = Agent(c_llm, tools(), _cfg(budget), trace=trace).run("read all", checkpoint=ck)
    assert c.ok and c.final_text == "all read"
    assert c.steps == 4 and c.tool_calls == 3 and c.resumed_from == 2
    assert c.usage == a.usage                       # accumulated across the crash
    assert _wire(c_llm.requests[0]) == _wire(a_llm.requests[2])
    assert _wire(c_llm.requests[1]) == _wire(a_llm.requests[3])
    assert trace.count("run_resumed") == 1 and trace.count("run_start") == 0
    assert [e for e in trace.events if e["event"] == "run_end"][0]["resumed_from"] == 2
    assert ck.load()["done"] is True


def test_completed_checkpoint_replays_without_llm(tmp_path):
    ws = _ws(tmp_path)
    ck = Checkpoint(str(tmp_path / "ck.json"))
    first = Agent(MockLLM(_script()), ToolRegistry([ReadFileTool(ws)]), _cfg(None)).run("t", checkpoint=ck)
    empty = MockLLM([])
    trace = TraceLogger()
    again = Agent(empty, ToolRegistry([ReadFileTool(ws)]), _cfg(None), trace=trace).run("t", checkpoint=ck)
    assert empty.calls_made == 0
    assert again.stop_reason == "completed" and again.final_text == first.final_text
    assert again.usage == first.usage and again.cost_usd == first.cost_usd
    assert again.steps == 4 and again.resumed_from == 4
    assert trace.count("run_replayed") == 1 and trace.count("run_end") == 0


def test_task_mismatch_raises(tmp_path):
    ck = Checkpoint(str(tmp_path / "ck.json"))
    Agent(MockLLM([text_turn("a")]), ToolRegistry([]), _cfg(None)).run("task A", checkpoint=ck)
    with pytest.raises(ValueError):
        Agent(MockLLM([text_turn("b")]), ToolRegistry([]), _cfg(None)).run("task B", checkpoint=ck)


def test_max_steps_run_continues_with_a_bigger_cap(tmp_path):
    ws = _ws(tmp_path)
    ck = Checkpoint(str(tmp_path / "ck.json"))
    reg = ToolRegistry([ReadFileTool(ws)])
    r1 = Agent(MockLLM(_script()), reg, AgentConfig(max_steps=1)).run("t", checkpoint=ck)
    assert r1.stop_reason == "max_steps" and r1.steps == 1
    st = ck.load()
    assert st["done"] is False and st["last_stop_reason"] == "max_steps" and st["steps"] == 1
    llm2 = MockLLM(_script()[1:])
    r2 = Agent(llm2, reg, AgentConfig(max_steps=10)).run("t", checkpoint=ck)
    assert r2.ok and r2.steps == 4 and r2.resumed_from == 1 and llm2.calls_made == 3
    assert r2.usage == Usage(1000, 35)


def test_budget_exhausted_before_dispatch_does_not_persist_the_dangling_turn(tmp_path):
    ws = _ws(tmp_path)
    ck = Checkpoint(str(tmp_path / "ck.json"))
    reg = ToolRegistry([ReadFileTool(ws)])
    llm = MockLLM(_script())
    llm.model = "claude-opus-5"
    r1 = Agent(llm, reg, AgentConfig(max_steps=10, max_total_tokens=50)).run("t", checkpoint=ck)
    assert r1.stop_reason == "budget_exhausted" and r1.steps == 1
    assert r1.messages[-1]["role"] == "assistant"          # in the returned transcript...
    st = ck.load()
    assert [m["role"] for m in st["messages"]] == ["system", "user"]  # ...but not in the checkpoint
    assert st["usage"]["input_tokens"] == 100 and st["steps"] == 1
    llm2 = MockLLM(_script())                              # the turn is re-made on resume
    r2 = Agent(llm2, reg, AgentConfig(max_steps=10)).run("t", checkpoint=ck)
    assert r2.ok and len(llm2.requests[0]["messages"]) == 2
    assert r2.steps == 5                                   # the wasted step still counted


def test_llm_error_keeps_checkpoint_live_and_resumes_after_outage(tmp_path):
    ws = _ws(tmp_path)
    ck = Checkpoint(str(tmp_path / "ck.json"))
    reg = ToolRegistry([ReadFileTool(ws)])
    inner = MockLLM(_script())
    flaky = FlakyLLM(inner, fail_times=99)
    pol = RetryPolicy(max_attempts=2, base_delay=0)
    r1 = Agent(flaky, reg, AgentConfig(max_steps=10, retry_policy=pol), sleep=lambda s: None).run("t", checkpoint=ck)
    assert r1.stop_reason == "llm_error"
    st = ck.load()
    assert st["last_stop_reason"] == "llm_error" and "RetriesExhausted" in st["error"] and st["steps"] == 1
    r2 = Agent(MockLLM(_script()), reg, AgentConfig(max_steps=10)).run("t", checkpoint=ck)
    assert r2.ok and r2.resumed_from == 1


def test_estimator_calibration_and_step0_boundary_persist(tmp_path):
    ws = _ws(tmp_path)
    ck = Checkpoint(str(tmp_path / "ck.json"))
    est = TokenEstimator()
    Agent(MockLLM(_script()), ToolRegistry([ReadFileTool(ws)]), _cfg(None), estimator=est).run("t", checkpoint=ck)
    st = ck.load()
    assert st["estimator"] == {"chars_per_token": est.chars_per_token, "observations": 4}
    assert ck.saves == 1 + 3 + 1     # step-0 boundary, 3 tool steps, final done save
    est2 = TokenEstimator()
    Agent(MockLLM([]), ToolRegistry([ReadFileTool(ws)]), _cfg(None), estimator=est2).run("t", checkpoint=ck)
    assert est2.chars_per_token == est.chars_per_token and est2.observations == 4


def test_checkpoint_file_semantics(tmp_path):
    path = str(tmp_path / "sub" / "ck.json")
    ck = Checkpoint(path)
    assert not ck.exists() and ck.load() is None
    ck.save({"task": "t", "messages": [{"role": "user", "content": "x", "_chars": 9}], "steps": 0})
    assert ck.exists() and not os.path.exists(path + ".tmp")
    st = ck.load()
    assert st["version"] == 1 and st["messages"] == [{"role": "user", "content": "x"}]
    with open(path, "w") as f:
        f.write("{not json")
    with pytest.raises(ValueError):
        ck.load()
    with open(path, "w") as f:
        f.write(json.dumps({"version": 99}))
    with pytest.raises(ValueError):
        ck.load()
    ck.clear()
    assert not ck.exists()


def test_cli_session_id_round_trips_through_checkpoint(tmp_path):
    ws = _ws(tmp_path)
    calls = []

    def runner(argv, stdin_text, timeout_s):
        calls.append(argv)
        return 0, json.dumps({"result": "final", "session_id": "sess-42",
                              "usage": {"input_tokens": 5, "output_tokens": 1}}), ""

    ck = Checkpoint(str(tmp_path / "ck.json"))
    cli = ClaudeCLILLM(runner=runner)
    Agent(cli, ToolRegistry([ReadFileTool(ws)]), _cfg(None)).run("t", checkpoint=ck)
    assert ck.load()["llm_state"] == {"session_id": "sess-42"}
    cli2 = ClaudeCLILLM(runner=runner)
    cli2.restore_state(ck.load()["llm_state"])
    assert cli2.session_id == "sess-42"
    cli2.complete([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}], [])
    assert "--resume" in calls[-1] and calls[-1][calls[-1].index("--resume") + 1] == "sess-42"
    cli3 = ClaudeCLILLM(runner=runner)
    cli3.restore_state({})
    assert cli3.session_id is None
