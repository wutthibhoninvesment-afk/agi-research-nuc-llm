"""Round-6 loop behaviours: parallel dispatch, spend caps, compaction in the
loop, usage in traces, estimator calibration, ok flag on tool messages."""
import threading
import time

import pytest

from agentloop import (Agent, AgentConfig, AssistantTurn, ContextBudget, MockLLM,
                       ToolCall, ToolRegistry, TokenEstimator, TraceLogger)
from agentloop.llm import text_turn, tool_turn, make_call_id, RetryableLLMError
from agentloop.tools import Tool, ToolResult
from agentloop.usage import Usage


class Slow(Tool):
    """parallel_safe tool that blocks on a shared barrier: only completes if
    N calls are in flight at once. Deterministic proof of concurrency."""
    name = "slow"
    description = "waits at a barrier"
    params = {"k": {"type": "string", "description": "key"}}
    required = ["k"]
    parallel_safe = True

    def __init__(self, parties, timeout=2.0):
        self.barrier = threading.Barrier(parties)
        self.timeout = timeout

    def run(self, k):
        try:
            self.barrier.wait(self.timeout)
        except threading.BrokenBarrierError:
            return ToolResult(False, "barrier timeout for %s" % k)
        return ToolResult(True, "ok " + k)


class Order(Tool):
    """Not parallel_safe: records call order."""
    name = "order"
    description = "records"
    params = {"k": {"type": "string", "description": "key"}}
    required = ["k"]

    def __init__(self):
        self.seen = []

    def run(self, k):
        self.seen.append(k)
        return ToolResult(True, k)


class Big(Tool):
    name = "big"
    description = "returns a big observation"
    params = {}
    parallel_safe = True

    def run(self):
        return ToolResult(True, "B" * 4000)


def multi(*calls):
    return AssistantTurn(tool_calls=[ToolCall(n, dict(a), make_call_id()) for n, a in calls])


def agent(llm, tools, **cfg):
    return Agent(llm, ToolRegistry(tools), AgentConfig(**cfg), trace=TraceLogger(clock=lambda: "T"),
                 sleep=lambda s: None, rng=lambda: 0.5)


# ------------------------------------------------------------- parallel ----

def test_parallel_dispatch_runs_safe_tools_concurrently_in_call_order():
    slow = Slow(parties=3)
    llm = MockLLM([multi(("slow", {"k": "a"}), ("slow", {"k": "b"}), ("slow", {"k": "c"})), text_turn("done")])
    r = agent(llm, [slow], parallel_tools=True).run("go")
    assert r.ok
    tool_msgs = [m for m in r.messages if m["role"] == "tool"]
    assert [m["content"] for m in tool_msgs] == ["ok a", "ok b", "ok c"]
    assert all(m["ok"] for m in tool_msgs)


def test_parallel_dispatch_event_and_serial_fallback_for_unsafe_tool():
    order = Order()
    slow = Slow(parties=2, timeout=0.2)
    llm = MockLLM([multi(("order", {"k": "1"}), ("slow", {"k": "x"}), ("order", {"k": "2"})), text_turn("done")])
    a = agent(llm, [order, slow], parallel_tools=True)
    r = a.run("go")
    disp = [e for e in a.trace.events if e["event"] == "dispatch"]
    assert disp == [{"ts": "T", "event": "dispatch", "step": 1, "mode": "serial", "n": 3}]
    assert order.seen == ["1", "2"]                       # call order preserved
    # the lone slow call timed out at its 2-party barrier -> observed as an error, loop survived
    assert r.ok and "ERROR: barrier timeout" in [m["content"] for m in r.messages if m["role"] == "tool"][1]


def test_serial_by_default_even_when_safe():
    slow = Slow(parties=2, timeout=0.2)
    llm = MockLLM([multi(("slow", {"k": "a"}), ("slow", {"k": "b"})), text_turn("done")])
    a = agent(llm, [slow])                                # parallel_tools=False
    r = a.run("go")
    modes = [e["mode"] for e in a.trace.events if e["event"] == "dispatch"]
    assert modes == ["serial"] and r.tool_calls == 2
    assert all(not m["ok"] for m in r.messages if m["role"] == "tool")   # barrier never met


def test_parallel_mode_logged_when_safe():
    slow = Slow(parties=2)
    llm = MockLLM([multi(("slow", {"k": "a"}), ("slow", {"k": "b"})), text_turn("done")])
    a = agent(llm, [slow], parallel_tools=True)
    r = a.run("go")
    assert r.ok and [e["mode"] for e in a.trace.events if e["event"] == "dispatch"] == ["parallel"]


def test_unknown_tool_in_batch_forces_serial_and_is_observed():
    slow = Slow(parties=1)
    llm = MockLLM([multi(("nope", {}), ("slow", {"k": "a"})), text_turn("done")])
    a = agent(llm, [slow], parallel_tools=True)
    r = a.run("go")
    assert [e["mode"] for e in a.trace.events if e["event"] == "dispatch"] == ["serial"]
    tool_msgs = [m for m in r.messages if m["role"] == "tool"]
    assert tool_msgs[0]["ok"] is False and "unknown tool" in tool_msgs[0]["content"]


# ---------------------------------------------------------- spend caps -----

def priced(turn, inp, out):
    turn.usage = Usage(inp, out)
    return turn


class PricedMock(MockLLM):
    model = "claude-opus-5"


def test_token_cap_stops_with_budget_exhausted_and_keeps_totals():
    llm = PricedMock([priced(tool_turn("big"), 1000, 100), priced(tool_turn("big"), 1000, 100),
                      text_turn("never")])
    a = agent(llm, [Big()], max_total_tokens=2000)
    r = a.run("go")
    assert r.stop_reason == "budget_exhausted" and not r.ok
    assert r.usage == Usage(2000, 200) and r.steps == 2 and r.tool_calls == 1
    assert "token cap" in r.error
    end = a.trace.events[-1]
    assert end["event"] == "run_end" and end["usage"]["input_tokens"] == 2000
    assert end["cost_usd"] == pytest.approx(Usage(2000, 200).cost_usd("claude-opus-5"))


def test_cost_cap_uses_model_pricing():
    llm = PricedMock([priced(tool_turn("big"), 1_000_000, 0), text_turn("never")])
    r = agent(llm, [Big()], max_cost_usd=4.0).run("go")      # opus-5 input = $5/M
    assert r.stop_reason == "budget_exhausted" and "cost cap" in r.error


def test_cost_cap_on_unpriced_model_stops_rather_than_running_blind():
    llm = MockLLM([priced(tool_turn("big"), 10, 1), text_turn("never")])   # no .model
    r = agent(llm, [Big()], max_cost_usd=1.0).run("go")
    assert r.stop_reason == "budget_exhausted" and "unpriced" in r.error
    assert r.cost_usd is None


def test_final_text_turn_is_not_cut_by_the_cap():
    """The cap is checked before dispatching tools; a completed answer that
    happens to cross the line is still returned as completed."""
    llm = PricedMock([priced(text_turn("answer"), 5000, 5000)])
    r = agent(llm, [Big()], max_total_tokens=10).run("go")
    assert r.ok and r.final_text == "answer"


# ---------------------------------------------------------- compaction -----

def test_compaction_in_loop_keeps_requests_under_budget_and_traces_it():
    est = TokenEstimator(4.0)
    budget = ContextBudget(max_input_tokens=2500, keep_recent_results=1)
    llm = MockLLM([tool_turn("big") for _ in range(6)] + [text_turn("done")])
    a = Agent(llm, ToolRegistry([Big()]), AgentConfig(context_budget=budget, max_observation_chars=100_000),
              trace=TraceLogger(clock=lambda: "T"), estimator=est, sleep=lambda s: None, rng=lambda: 0.5)
    r = a.run("go")
    assert r.ok and r.compactions >= 1
    # every request the LLM actually saw was within budget (estimate on the wire)
    for req in llm.requests:
        assert est.estimate(req["messages"], req["tools"]) <= budget.target
    ev = [e for e in a.trace.events if e["event"] == "context_compacted"]
    assert ev and all(e["fits"] for e in ev)
    # the newest observation before the final answer was left intact
    tools = [m for m in r.messages if m["role"] == "tool"]
    assert tools[-1]["content"] == "B" * 4000 and tools[0].get("elided")


def test_estimator_calibrates_from_reported_usage():
    est = TokenEstimator(4.0)
    llm = MockLLM([priced(tool_turn("big"), 100, 1), priced(text_turn("done"), 1000, 1)])
    a = Agent(llm, ToolRegistry([Big()]), estimator=est, sleep=lambda s: None, rng=lambda: 0.5)
    a.run("x" * 400)
    assert est.observations == 2 and est.chars_per_token != 4.0
    ev = [e for e in a.trace.events if e["event"] == "llm_response"]
    assert ev[0]["usage"]["input_tokens"] == 100 and "duration_s" in ev[0]


def test_run_end_carries_usage_even_on_llm_error():
    from agentloop.llm import FatalLLMError
    llm = MockLLM([priced(tool_turn("big"), 7, 3)])   # second call exhausts the script -> Fatal
    a = agent(llm, [Big()])
    r = a.run("go")
    assert r.stop_reason == "llm_error" and r.usage == Usage(7, 3)
    assert a.trace.events[-1]["usage"] == Usage(7, 3).as_dict()


# --------------------------------------------- round-13: exact token check --
# Opt-in ground-truth check near a budget boundary: when the backend exposes
# count_tokens() and the heuristic estimate is close to the target, spend one
# exact call, recalibrate immediately, and compact again if it turns out the
# heuristic undercounted. Agent._maybe_exact_check is unit-tested directly
# (control over messages/target/exact-count without reverse-engineering the
# char/json.dumps arithmetic); one end-to-end test proves the wiring through
# the real loop.

class StubCountingLLM:
    """Not a full LLM double -- just enough surface for _maybe_exact_check:
    a count_tokens() that is either scripted or raises."""
    def __init__(self, exact_tokens=None, raises=None):
        self.exact_tokens = exact_tokens
        self.raises = raises
        self.calls = 0

    def count_tokens(self, messages, tools=()):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self.exact_tokens

    def complete(self, messages, tools):
        raise AssertionError("not exercised by these tests")


def test_exact_check_noop_when_llm_has_no_count_tokens():
    a = agent(MockLLM([]), [], exact_token_check=True)
    n = a._maybe_exact_check([{"role": "system", "content": "s"}], [],
                             ContextBudget(max_input_tokens=5), step=1)
    assert n == 0


def test_exact_check_skipped_when_heuristic_far_from_target():
    stub = StubCountingLLM(exact_tokens=999999)
    a = Agent(stub, ToolRegistry([]), AgentConfig(exact_token_check=True, exact_token_margin=1),
             trace=TraceLogger(clock=lambda: "T"))
    messages = [{"role": "system", "content": "s" * 4000}, {"role": "user", "content": "u"}]
    n = a._maybe_exact_check(messages, [], ContextBudget(max_input_tokens=100_000), step=1)
    assert n == 0 and stub.calls == 0   # margin gate: never even called count_tokens


def test_exact_check_recalibrates_without_a_second_compaction_when_exact_fits():
    stub = StubCountingLLM(exact_tokens=50)
    a = Agent(stub, ToolRegistry([]), AgentConfig(exact_token_check=True, exact_token_margin=100_000),
             trace=TraceLogger(clock=lambda: "T"))
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    before_ratio = a.estimator.chars_per_token
    n = a._maybe_exact_check(messages, [], ContextBudget(max_input_tokens=1000), step=1)
    assert n == 0 and stub.calls == 1
    assert a.estimator.observations == 1 and a.estimator.chars_per_token != before_ratio
    ev = [e for e in a.trace.events if e["event"] == "exact_token_check"]
    assert ev and ev[0]["exact"] == 50 and ev[0]["target"] == 1000


def test_exact_check_triggers_a_second_compaction_when_exact_exceeds_target():
    stub = StubCountingLLM(exact_tokens=2000)
    a = Agent(stub, ToolRegistry([]), AgentConfig(exact_token_check=True, exact_token_margin=100_000),
             trace=TraceLogger(clock=lambda: "T"))
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"name": "echo", "args": {"text": "hi"}, "call_id": "c1"}]},
        {"role": "tool", "content": "y" * 2000, "tool_call_id": "c1", "tool_name": "echo", "ok": True},
    ]
    budget = ContextBudget(max_input_tokens=50, keep_recent_results=0)
    n = a._maybe_exact_check(messages, [], budget, step=1)
    assert n == 1
    assert messages[3].get("elided") is True   # the recalibrated compact() actually acted
    assert any(e["event"] == "context_compacted" and e.get("exact_triggered") for e in a.trace.events)


def test_exact_check_failure_is_non_fatal_and_traced():
    stub = StubCountingLLM(raises=RetryableLLMError("count_tokens endpoint down"))
    a = Agent(stub, ToolRegistry([]), AgentConfig(exact_token_check=True, exact_token_margin=100_000),
             trace=TraceLogger(clock=lambda: "T"))
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    n = a._maybe_exact_check(messages, [], ContextBudget(max_input_tokens=1000), step=1)
    assert n == 0
    assert any(e["event"] == "exact_token_check_failed" for e in a.trace.events)


def test_exact_check_off_by_default_costs_nothing():
    # AgentConfig() default: exact_token_check=False. Even with a
    # count_tokens-capable backend and a budget, the loop never calls it --
    # this is an opt-in feature, not a silent extra network call per step.
    stub = StubCountingLLM(exact_tokens=1)
    llm = MockLLM([text_turn("done")])  # complete() is used, not count_tokens
    a = Agent(llm, ToolRegistry([]), AgentConfig(context_budget=ContextBudget(max_input_tokens=100_000)),
             trace=TraceLogger(clock=lambda: "T"), sleep=lambda s: None, rng=lambda: 0.5)
    r = a.run("go")
    assert r.ok
    assert not any(e["event"].startswith("exact_token_check") for e in a.trace.events)
