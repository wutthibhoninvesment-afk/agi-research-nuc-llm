"""Prompt caching (cache_control breakpoints), server-side fallbacks
passthrough, and cache-damage accounting.

Round 19: the harness's monotonic in-place compaction was DESIGNED to keep
provider prompt caches warm (round 6), but nothing ever placed a
cache_control breakpoint, so on the API backend no cache entry was ever
created. apply_cache_markers() places: one marker on system (tools render
first, so this caches tools+system together), and moving markers on the last
two user-role wire messages (the second one keeps the lookup inside the
API's 20-block lookback window when a turn appends many tool_result blocks).
Markers are metadata, not content — moving them between requests does not
invalidate the cache — but a string<->block shape flip might, so user content
is always converted to block form while caching is on.

compact() now reports first_changed_index / invalidated_chars: mutating
message i invalidates the cached prefix from i onward, and the next request
re-writes that suffix at 1.25x instead of reading it at 0.1x —
usage.cache_invalidation_cost_usd() prices exactly that.
"""
import json

import pytest

from agentloop import Agent, AgentConfig, ContextBudget, ToolRegistry
from agentloop.adapters import (AnthropicAPILLM, apply_cache_markers,
                                CACHE_MAX_BREAKPOINTS, FALLBACK_BETA_ARRAY,
                                FALLBACK_BETA_DEFAULT, OAUTH_BETA)
from agentloop.context import TokenEstimator, compact
from agentloop.llm import FatalLLMError
from agentloop.tools import Tool, ToolResult
from agentloop.trace import TraceLogger
from agentloop.usage import Usage, cache_invalidation_cost_usd


def api_ok(content, stop="end_turn", usage=None):
    return 200, json.dumps(
        {"id": "msg_1", "type": "message", "role": "assistant",
         "model": "claude-opus-5", "content": content, "stop_reason": stop,
         "usage": usage or {"input_tokens": 100, "output_tokens": 10}}), {}


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, body, timeout_s):
        self.calls.append({"url": url, "headers": headers, "body": json.loads(body)})
        return self.responses.pop(0)


class Echo(Tool):
    name = "echo"
    description = "echo"
    params = {"text": {"type": "string", "description": "t"}}
    required = ["text"]
    parallel_safe = True

    def run(self, text):
        return ToolResult(True, "echo:" + text)


def make(responses, **kw):
    t = FakeTransport(responses)
    kw.setdefault("api_key", "sk-test")
    return AnthropicAPILLM(transport=t, **kw), t


CACHE = {"type": "ephemeral"}

HIST = [
    {"role": "system", "content": "sys prompt"},
    {"role": "user", "content": "the task"},
]
TOOLS = [{"name": "echo", "description": "e",
          "input_schema": {"type": "object", "properties": {}}}]


def markers_in(body):
    """(system_marked, tool_marked, [user msg indexes whose last block is marked])."""
    sys_marked = isinstance(body.get("system"), list) and \
        any("cache_control" in b for b in body["system"])
    tool_marked = any("cache_control" in t for t in body.get("tools") or [])
    user_marked = []
    for i, m in enumerate(body["messages"]):
        if m.get("role") == "user" and isinstance(m.get("content"), list) \
                and m["content"] and "cache_control" in m["content"][-1]:
            user_marked.append(i)
    return sys_marked, tool_marked, user_marked


# ------------------------------------------------------------- placement --

def test_system_marker_and_task_marker():
    llm, _ = make([], cache=CACHE)
    body = llm.build_body(HIST, TOOLS)
    sys_marked, tool_marked, user_marked = markers_in(body)
    assert sys_marked                      # covers tools+system (tools render first)
    assert not tool_marked                 # system marker already covers the tools
    assert user_marked == [0]              # the task message
    assert body["system"] == [{"type": "text", "text": "sys prompt",
                               "cache_control": CACHE}]


def test_no_system_marks_last_tool():
    llm, _ = make([], cache=CACHE)
    body = llm.build_body([{"role": "user", "content": "task"}], TOOLS)
    sys_marked, tool_marked, user_marked = markers_in(body)
    assert not sys_marked and tool_marked and user_marked == [0]


def test_moving_markers_last_two_users_only_and_max_four():
    hist = list(HIST)
    for i in range(3):  # three completed steps
        hist.append({"role": "assistant", "content": "step %d" % i,
                     "tool_calls": [{"name": "echo", "args": {"text": str(i)},
                                     "call_id": "c%d" % i}]})
        hist.append({"role": "tool", "content": "echo:%d" % i,
                     "tool_call_id": "c%d" % i, "tool_name": "echo", "ok": True})
    llm, _ = make([], cache=CACHE)
    body = llm.build_body(hist, TOOLS)
    sys_marked, _, user_marked = markers_in(body)
    users = [i for i, m in enumerate(body["messages"]) if m["role"] == "user"]
    assert len(users) == 4                       # task + 3 tool-result messages
    assert user_marked == users[-2:]             # only the newest two
    total = int(sys_marked) + len(user_marked)
    assert total == 3 <= CACHE_MAX_BREAKPOINTS


def test_all_user_strings_become_blocks_for_shape_stability():
    hist = list(HIST) + [
        {"role": "assistant", "content": "a", "tool_calls": []},
        {"role": "user", "content": "follow-up 1"},
        {"role": "assistant", "content": "b", "tool_calls": []},
        {"role": "user", "content": "follow-up 2"},
    ]
    llm, _ = make([], cache=CACHE)
    body = llm.build_body(hist, ())
    users = [m for m in body["messages"] if m["role"] == "user"]
    # every user message is block-form, marked or not — no string<->block flips
    assert all(isinstance(m["content"], list) for m in users)
    assert "cache_control" not in users[0]["content"][-1]     # 3 users: oldest unmarked
    assert all("cache_control" in m["content"][-1] for m in users[-2:])


def test_cache_off_no_markers_anywhere():
    llm, _ = make([])
    body = llm.build_body(HIST, TOOLS)
    assert "cache_control" not in json.dumps(body)
    assert isinstance(body["system"], str)       # untouched legacy shape


def test_assistant_raw_content_never_mutated():
    raw = [{"type": "thinking", "thinking": "hm", "signature": "sig"},
           {"type": "tool_use", "id": "c1", "name": "echo", "input": {"text": "x"}}]
    hist = list(HIST) + [
        {"role": "assistant", "content": "", "tool_calls": [
            {"name": "echo", "args": {"text": "x"}, "call_id": "c1"}],
         "raw_content": raw},
        {"role": "tool", "content": "echo:x", "tool_call_id": "c1",
         "tool_name": "echo", "ok": True},
    ]
    before = json.dumps(raw, sort_keys=True)
    llm, _ = make([], cache=CACHE)
    llm.build_body(hist, TOOLS)
    assert json.dumps(raw, sort_keys=True) == before
    assert "cache_control" not in before


def test_markers_move_across_turns_in_full_loop():
    llm, t = make([
        api_ok([{"type": "tool_use", "id": "t1", "name": "echo", "input": {"text": "a"}}],
               stop="tool_use"),
        api_ok([{"type": "tool_use", "id": "t2", "name": "echo", "input": {"text": "b"}}],
               stop="tool_use"),
        api_ok([{"type": "text", "text": "done"}]),
    ], cache=CACHE)
    agent = Agent(llm, ToolRegistry([Echo()]), AgentConfig(max_steps=5))
    result = agent.run("cache me")
    assert result.ok
    # request 1: one user msg (task) -> marked; requests grow monotonically
    _, _, m1 = markers_in(t.calls[0]["body"])
    assert len(m1) == 1
    # request 3: users = [task, result1, result2] -> newest two marked, task not
    body3 = t.calls[2]["body"]
    sys_marked, _, m3 = markers_in(body3)
    users3 = [i for i, m in enumerate(body3["messages"]) if m["role"] == "user"]
    assert len(users3) == 3 and m3 == users3[-2:]
    assert sys_marked
    # the tool_result block itself carries the marker (a cacheable block type)
    marked_block = body3["messages"][m3[-1]]["content"][-1]
    assert marked_block["type"] == "tool_result"


# ------------------------------------------------------------- fallbacks --

def test_fallbacks_default_form():
    llm, t = make([api_ok([{"type": "text", "text": "hi"}])], fallbacks="default")
    llm.complete(HIST, ())
    call = t.calls[0]
    assert call["body"]["fallbacks"] == "default"
    assert call["headers"]["anthropic-beta"] == FALLBACK_BETA_DEFAULT


def test_fallbacks_array_form_and_oauth_beta_join():
    llm = AnthropicAPILLM(auth_token="tok", transport=FakeTransport(
        [api_ok([{"type": "text", "text": "hi"}])]),
        fallbacks=[{"model": "claude-opus-4-8"}])
    t = llm._transport
    llm.complete(HIST, ())
    call = t.calls[0]
    assert call["body"]["fallbacks"] == [{"model": "claude-opus-4-8"}]
    assert call["headers"]["anthropic-beta"] == OAUTH_BETA + "," + FALLBACK_BETA_ARRAY


def test_fallbacks_invalid_value_raises():
    with pytest.raises(FatalLLMError):
        make([], fallbacks={"model": "claude-opus-4-8"})  # bare dict: wrong shape


def test_count_tokens_strips_fallbacks():
    llm, t = make([(200, json.dumps({"input_tokens": 42}), {})], fallbacks="default")
    assert llm.count_tokens(HIST, TOOLS) == 42
    assert "fallbacks" not in t.calls[0]["body"]
    assert "max_tokens" not in t.calls[0]["body"]


# ------------------------------------------------------- cache accounting --

def test_cache_hit_rate():
    assert Usage().cache_hit_rate == 0.0
    u = Usage(input_tokens=100, output_tokens=5,
              cache_read_input_tokens=900, cache_creation_input_tokens=0)
    assert u.cache_hit_rate == pytest.approx(0.9)


def test_cache_invalidation_cost():
    # 1M invalidated tokens on opus-5 ($5/MTok input): rewrite 1.25x vs read 0.1x
    assert cache_invalidation_cost_usd(1_000_000, "claude-opus-5") == pytest.approx(5.0 * 1.15)
    assert cache_invalidation_cost_usd(1_000_000, "not-a-model") is None
    assert cache_invalidation_cost_usd(0, "claude-opus-5") == 0.0


def _history_with_steps(n, obs_chars=400):
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "task"}]
    for i in range(n):
        msgs.append({"role": "assistant", "content": "", "tool_calls": [
            {"name": "echo", "args": {"i": i}, "call_id": "c%d" % i}]})
        msgs.append({"role": "tool", "content": "x" * obs_chars,
                     "tool_call_id": "c%d" % i, "tool_name": "echo", "ok": True})
    return msgs


def test_compaction_reports_invalidation():
    est = TokenEstimator(chars_per_token=1.0)  # tokens == chars, deterministic
    msgs = _history_with_steps(5)
    total = est.estimate(msgs, ())
    budget = ContextBudget(max_input_tokens=total - 300, keep_recent_results=2)
    report = compact(msgs, budget, est, ())
    assert report.changed and report.elided_results >= 1
    # first elided observation is the oldest tool message, index 3
    assert report.first_changed_index == 3
    assert report.invalidated_chars == sum(est.chars_of([m]) for m in msgs[3:])
    d = report.as_dict()
    assert d["first_changed_index"] == 3 and d["invalidated_chars"] > 0


def test_compaction_no_change_reports_none():
    est = TokenEstimator(chars_per_token=1.0)
    msgs = _history_with_steps(2)
    budget = ContextBudget(max_input_tokens=est.estimate(msgs, ()) + 1000)
    report = compact(msgs, budget, est, ())
    assert not report.changed
    assert report.first_changed_index is None and report.invalidated_chars == 0


def test_compaction_drop_stage_tracks_first_changed():
    est = TokenEstimator(chars_per_token=1.0)
    msgs = _history_with_steps(6, obs_chars=2000)
    # small enough that elision alone cannot fit -> steps get dropped
    budget = ContextBudget(max_input_tokens=1500, keep_recent_results=1,
                           min_steps_kept=1)
    report = compact(msgs, budget, est, ())
    assert report.dropped_steps >= 1
    # the drop replaced messages starting at the first step (index 2)
    assert report.first_changed_index == 2
    assert report.invalidated_chars == sum(est.chars_of([m]) for m in msgs[2:])


def test_run_end_trace_reports_cache_hit_rate():
    llm, _ = make([api_ok([{"type": "text", "text": "done"}],
                          usage={"input_tokens": 100, "output_tokens": 10,
                                 "cache_read_input_tokens": 300})], cache=CACHE)
    trace = TraceLogger()
    agent = Agent(llm, ToolRegistry([]), AgentConfig(max_steps=2), trace=trace)
    result = agent.run("t")
    assert result.ok
    end = [e for e in trace.events if e["event"] == "run_end"][0]
    assert end["cache_hit_rate"] == pytest.approx(0.75)
