"""Round 31: CachingSimLLM — a double that bills like a prefix-caching provider."""
import json

from agentloop import (Agent, AgentConfig, CachingSimLLM, ContextBudget, MockLLM, ReadFileTool,
                       SimCache, ToolRegistry)
from agentloop.llm import text_turn, tool_turn
from agentloop.sim import common_prefix_len, render_request
from agentloop.usage import Usage


def test_render_order_is_tools_system_messages():
    msgs = [{"role": "user", "content": "u", "_chars": 3}, {"role": "system", "content": "s"}]
    tools = [{"name": "t", "description": "d", "input_schema": {}}]
    r = render_request(msgs, tools).split("\n")
    assert json.loads(r[0])["name"] == "t"
    assert json.loads(r[1])["role"] == "system"
    assert json.loads(r[2]) == {"role": "user", "content": "u"}


def test_common_prefix_len():
    assert common_prefix_len("", "abc") == 0
    assert common_prefix_len("abc", "abc") == 3
    assert common_prefix_len("abcd", "abxy") == 2
    assert common_prefix_len("abc", "abcdef") == 3


def test_second_request_reads_first_request_as_cached_prefix():
    inner = MockLLM([text_turn("hello"), text_turn("bye")])
    sim = CachingSimLLM(inner, chars_per_token=4.0)
    tools = [{"name": "t", "description": "d", "input_schema": {}}]
    m1 = [{"role": "system", "content": "sys"}, {"role": "user", "content": "task"}]
    t1 = sim.complete(m1, tools)
    r1 = sim.requests[0]
    assert t1.text == "hello"
    assert t1.usage.cache_read_input_tokens == 0
    assert t1.usage.cache_creation_input_tokens == round(r1["chars"] / 4)
    assert t1.usage.output_tokens == round(len("hello") / 4)
    m2 = m1 + [{"role": "assistant", "content": "hello", "tool_calls": []},
               {"role": "user", "content": "more"}]
    t2 = sim.complete(m2, tools)
    r2 = sim.requests[1]
    assert r2["cached_chars"] == r1["chars"]
    assert t2.usage.cache_read_input_tokens == round(r1["chars"] / 4)
    assert t2.usage.cache_creation_input_tokens == round((r2["chars"] - r1["chars"]) / 4)
    assert sim.usage == t1.usage + t2.usage


def test_shared_cache_across_agents_matches_only_the_common_prefix():
    cache = SimCache()
    tools = [{"name": "t", "description": "d" * 200, "input_schema": {}}]
    a = CachingSimLLM(MockLLM([text_turn("a")]), cache=cache)
    b = CachingSimLLM(MockLLM([text_turn("b")]), cache=cache)
    a.complete([{"role": "system", "content": "parent prompt"}, {"role": "user", "content": "x"}], tools)
    b.complete([{"role": "system", "content": "child prompt"}, {"role": "user", "content": "x"}], tools)
    tools_chars = len(json.dumps(tools[0], sort_keys=True))
    shared = b.requests[0]["cached_chars"]
    # everything up to the divergence inside the system message, i.e. the
    # tools line plus the common head of the two system lines
    assert shared > tools_chars
    assert shared < tools_chars + 1 + len(json.dumps({"role": "system", "content": "parent prompt"}, sort_keys=True))


def test_elision_in_the_loop_shows_up_as_cache_damage(tmp_path):
    ws = tmp_path
    for i in range(4):
        (ws / ("f%d.txt" % i)).write_text("data " * 300)
    script = [tool_turn("read_file", path="f%d.txt" % i) for i in range(4)] + [text_turn("done")]
    sim = CachingSimLLM(MockLLM(script), chars_per_token=4.0)
    cfg = AgentConfig(max_steps=10, context_budget=ContextBudget(max_input_tokens=1200, keep_recent_results=1))
    res = Agent(sim, ToolRegistry([ReadFileTool(str(ws))]), cfg).run("read them")
    assert res.ok and res.compactions >= 1
    reqs = sim.requests
    # before any compaction, each request is the previous one plus new text
    assert reqs[1]["cached_chars"] == reqs[0]["chars"]
    # the compacting step rewrote an early message: its cached prefix is
    # SHORTER than the previous request's full rendering
    damaged = [i for i in range(1, len(reqs)) if reqs[i]["cached_chars"] < reqs[i - 1]["chars"]]
    assert damaged, [r["cached_chars"] for r in reqs]
    assert isinstance(res.usage, Usage) and res.usage.cache_read_input_tokens > 0
    assert res.cost_usd is not None                      # sim exposes a priced model
