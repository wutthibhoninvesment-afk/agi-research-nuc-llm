"""Round 25: TTL-keyed cache-write pricing, server-side compaction beta,
cache-aware elision ordering.

Pricing: cache writes cost 1.25x input at the default 5m TTL and 2x at 1h.
The attribution is layered — a per-TTL breakdown in the response usage wins;
without one, everything is priced at the TTL the CLIENT configured (it chose
what it sent in cache_control, so single-TTL attribution is exact).

Server compaction (beta compact-2026-01-12): the adapter sends the beta
header + context_management edit; the returned `compaction` content block
rides raw_content and must be replayed verbatim (that replay is how the API
substitutes the compacted history on later requests).

Elision order: stage-1 compaction can elide newest-eligible-first, keeping
the mutation near the transcript tail so the warm cache prefix survives.
bench_elision.py measures the sizes; these tests pin the mechanics.
"""
import json

import pytest

from agentloop import Agent, AgentConfig, ToolRegistry
from agentloop.adapters import (AnthropicAPILLM, COMPACTION_BETA, accumulate_stream,
                                parse_api_message, to_anthropic_messages)
from agentloop.context import ContextBudget, TokenEstimator, compact
from agentloop.llm import MockLLM, AssistantTurn
from agentloop.usage import (Usage, cache_invalidation_cost_usd,
                             CACHE_WRITE_FACTOR, CACHE_WRITE_FACTOR_1H)


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


def make(responses, **kw):
    t = FakeTransport(responses)
    kw.setdefault("api_key", "sk-test")
    return AnthropicAPILLM(transport=t, **kw), t


HIST = [
    {"role": "system", "content": "sys prompt"},
    {"role": "user", "content": "the task"},
]


# ------------------------------------------------------- usage pricing ---

def test_from_api_parses_cache_creation_breakdown():
    u = Usage.from_api({"input_tokens": 10, "output_tokens": 5,
                        "cache_read_input_tokens": 100,
                        "cache_creation_input_tokens": 30,
                        "cache_creation": {"ephemeral_5m_input_tokens": 20,
                                           "ephemeral_1h_input_tokens": 10}})
    assert u.cache_creation_5m_tokens == 20
    assert u.cache_creation_1h_tokens == 10
    assert u.total_input == 140          # breakdown is not double-counted


def test_from_api_without_breakdown_leaves_zeroes():
    u = Usage.from_api({"input_tokens": 10, "cache_creation_input_tokens": 30})
    assert u.cache_creation_5m_tokens == 0 and u.cache_creation_1h_tokens == 0


def test_cost_uses_breakdown_when_present():
    u = Usage(input_tokens=0, output_tokens=0, cache_read_input_tokens=0,
              cache_creation_input_tokens=1_000_000,
              cache_creation_5m_tokens=600_000, cache_creation_1h_tokens=400_000)
    inp = 5.00  # claude-opus-5 $/MTok input
    expected = (0.6 * CACHE_WRITE_FACTOR + 0.4 * CACHE_WRITE_FACTOR_1H) * inp
    assert u.cost_usd("claude-opus-5") == pytest.approx(expected)
    # write_ttl is ignored when the breakdown covers all writes
    assert u.cost_usd("claude-opus-5", write_ttl="1h") == pytest.approx(expected)


def test_cost_without_breakdown_prices_at_configured_ttl():
    u = Usage(cache_creation_input_tokens=1_000_000)
    assert u.cost_usd("claude-opus-5") == pytest.approx(5.00 * CACHE_WRITE_FACTOR)
    assert u.cost_usd("claude-opus-5", write_ttl="1h") == pytest.approx(5.00 * CACHE_WRITE_FACTOR_1H)


def test_cost_prices_breakdown_remainder_at_configured_ttl():
    # a backend that reports a PARTIAL breakdown: the uncovered remainder is
    # priced at the caller's TTL, not silently dropped
    u = Usage(cache_creation_input_tokens=1_000_000, cache_creation_5m_tokens=250_000)
    expected_5m = 5.00 * (0.25 * CACHE_WRITE_FACTOR + 0.75 * CACHE_WRITE_FACTOR)
    expected_1h = 5.00 * (0.25 * CACHE_WRITE_FACTOR + 0.75 * CACHE_WRITE_FACTOR_1H)
    assert u.cost_usd("claude-opus-5") == pytest.approx(expected_5m)
    assert u.cost_usd("claude-opus-5", write_ttl="1h") == pytest.approx(expected_1h)


def test_bad_ttl_raises_even_for_unpriced_model():
    u = Usage(cache_creation_input_tokens=10)
    with pytest.raises(ValueError):
        u.cost_usd("claude-opus-5", write_ttl="2h")
    with pytest.raises(ValueError):
        u.cost_usd("not-a-model", write_ttl="2h")
    with pytest.raises(ValueError):
        cache_invalidation_cost_usd(10, "claude-opus-5", write_ttl="never")


def test_add_sums_breakdown_and_as_dict_carries_it():
    u = Usage(cache_creation_input_tokens=5, cache_creation_5m_tokens=3,
              cache_creation_1h_tokens=2) + Usage(cache_creation_input_tokens=7,
                                                  cache_creation_1h_tokens=7)
    assert u.cache_creation_input_tokens == 12
    assert u.cache_creation_5m_tokens == 3 and u.cache_creation_1h_tokens == 9
    d = u.as_dict()
    assert d["cache_creation_5m_tokens"] == 3 and d["cache_creation_1h_tokens"] == 9


def test_invalidation_cost_doubles_premium_gap_at_1h():
    at_5m = cache_invalidation_cost_usd(1_000_000, "claude-opus-5")
    at_1h = cache_invalidation_cost_usd(1_000_000, "claude-opus-5", write_ttl="1h")
    assert at_5m == pytest.approx(5.00 * (CACHE_WRITE_FACTOR - 0.1))
    assert at_1h == pytest.approx(5.00 * (CACHE_WRITE_FACTOR_1H - 0.1))


def test_agent_prices_writes_at_llms_configured_ttl():
    turn = AssistantTurn(text="done", usage=Usage(cache_creation_input_tokens=1_000_000))
    llm = MockLLM([turn])
    llm.model = "claude-opus-5"
    llm.cache = {"type": "ephemeral", "ttl": "1h"}
    agent = Agent(llm, ToolRegistry([]), AgentConfig(max_steps=2))
    result = agent.run("t")
    assert result.cost_usd == pytest.approx(5.00 * CACHE_WRITE_FACTOR_1H)
    llm2 = MockLLM([AssistantTurn(text="done", usage=Usage(cache_creation_input_tokens=1_000_000))])
    llm2.model = "claude-opus-5"          # no cache attribute -> 5m default
    result2 = Agent(llm2, ToolRegistry([]), AgentConfig(max_steps=2)).run("t")
    assert result2.cost_usd == pytest.approx(5.00 * CACHE_WRITE_FACTOR)


# -------------------------------------------------- server compaction ---

def test_server_compaction_sends_beta_and_edit():
    llm, t = make([api_ok([{"type": "text", "text": "hi"}])], server_compaction=True)
    llm.complete(HIST, [])
    call = t.calls[0]
    assert COMPACTION_BETA in call["headers"].get("anthropic-beta", "")
    assert call["body"]["context_management"] == {"edits": [{"type": "compact_20260112"}]}


def test_server_compaction_off_by_default():
    llm, t = make([api_ok([{"type": "text", "text": "hi"}])])
    llm.complete(HIST, [])
    call = t.calls[0]
    assert "context_management" not in call["body"]
    assert COMPACTION_BETA not in call["headers"].get("anthropic-beta", "")


def test_count_tokens_strips_context_management():
    llm, t = make([(200, json.dumps({"input_tokens": 42}), {})], server_compaction=True)
    assert llm.count_tokens(HIST, []) == 42
    assert "context_management" not in t.calls[0]["body"]


def test_compaction_block_rides_raw_content_and_replays_verbatim():
    content = [{"type": "compaction", "content": "summary of earlier turns"},
               {"type": "text", "text": "and the answer is 4"}]
    turn = parse_api_message({"content": content, "stop_reason": "end_turn", "usage": {}})
    assert turn.text == "and the answer is 4"
    assert turn.raw_content == content
    # what agent.py stores, to_anthropic_messages must replay unmodified
    hist = HIST + [{"role": "assistant", "content": turn.text, "raw_content": turn.raw_content}]
    _, msgs = to_anthropic_messages(hist)
    assert msgs[-1]["content"] == content


def test_stream_unknown_delta_accumulates_string_fields():
    events = [
        ("message_start", {"message": {"id": "m", "usage": {"input_tokens": 1}}}),
        ("content_block_start", {"index": 0, "content_block": {"type": "compaction"}}),
        ("content_block_delta", {"index": 0, "delta": {"type": "compaction_delta",
                                                       "content": "part one, "}}),
        ("content_block_delta", {"index": 0, "delta": {"type": "compaction_delta",
                                                       "content": "part two"}}),
        ("content_block_stop", {"index": 0}),
        ("message_delta", {"delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 2}}),
        ("message_stop", {}),
    ]
    msg, err = accumulate_stream(events)
    assert err is None
    assert msg["content"] == [{"type": "compaction", "content": "part one, part two"}]


# ------------------------------------------------------- elision order ---

def history(n_steps, obs_chars=1000):
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "task"}]
    for i in range(n_steps):
        msgs.append({"role": "assistant", "content": "", "tool_calls": [
            {"name": "read_file", "args": {"path": "f%d" % i}, "call_id": "c%d" % i}]})
        msgs.append({"role": "tool", "content": "x" * obs_chars, "tool_call_id": "c%d" % i,
                     "tool_name": "read_file", "ok": True})
    return msgs


def test_elide_order_validated():
    with pytest.raises(ValueError):
        ContextBudget(max_input_tokens=1000, elide_order="middle-out")


def test_newest_first_elides_tailmost_eligible_and_reports_min_index():
    est = TokenEstimator(chars_per_token=4.0)
    msgs = history(10)
    budget = ContextBudget(max_input_tokens=2000, keep_recent_results=2,
                           elide_order="newest")
    rep = compact(msgs, budget, est)
    assert rep.elided_results > 1
    elided = [i for i, m in enumerate(msgs) if m.get("elided")]
    eligible = [i for i, m in enumerate(msgs) if m.get("role") == "tool"][:-2]
    # tail-most eligible go first: the elided set is a SUFFIX of eligible
    assert elided == eligible[-len(elided):]
    # the two newest observations are never touched
    assert not msgs[-1].get("elided") and not msgs[-3].get("elided")
    assert rep.first_changed_index == min(elided)
    assert rep.invalidated_chars == sum(
        len(m.get("content") or "") + 8 if not m.get("tool_calls")
        else est.chars_of([m]) for m in msgs[rep.first_changed_index:])


def test_orders_save_equally_but_newest_invalidates_less():
    est_a, est_b = TokenEstimator(4.0), TokenEstimator(4.0)
    msgs_a, msgs_b = history(20), history(20)
    rep_a = compact(msgs_a, ContextBudget(max_input_tokens=3500, elide_order="oldest"), est_a)
    rep_b = compact(msgs_b, ContextBudget(max_input_tokens=3500, elide_order="newest"), est_b)
    assert rep_a.elided_results == rep_b.elided_results
    assert rep_a.after_tokens == rep_b.after_tokens
    assert rep_b.invalidated_chars < rep_a.invalidated_chars / 3
    assert rep_b.first_changed_index > rep_a.first_changed_index


def test_newest_first_recompaction_is_monotonic():
    est = TokenEstimator(chars_per_token=4.0)
    budget = ContextBudget(max_input_tokens=2000, keep_recent_results=2,
                           elide_order="newest")
    msgs = history(10)
    compact(msgs, budget, est)
    elided_before = [i for i, m in enumerate(msgs) if m.get("elided")]
    # history grows; the previously-protected observations become eligible
    msgs.extend(history(3)[2:])
    compact(msgs, budget, est)
    elided_after = [i for i, m in enumerate(msgs) if m.get("elided")]
    assert set(elided_before) <= set(elided_after)   # nothing un-elided
