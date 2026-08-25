"""AnthropicAPILLM against a fake transport: wire shape, parsing, errors."""
import json

import pytest

from agentloop import Agent, AgentConfig, ContextBudget, ToolRegistry, RetryPolicy
from agentloop.adapters import AnthropicAPILLM, to_anthropic_messages, parse_api_message
from agentloop.llm import RetryableLLMError, FatalLLMError
from agentloop.tools import Tool, ToolResult
from agentloop.usage import Usage


def api_ok(content, stop="end_turn", usage=None, **extra):
    d = {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5",
         "content": content, "stop_reason": stop,
         "usage": usage or {"input_tokens": 100, "output_tokens": 10,
                            "cache_read_input_tokens": 50, "cache_creation_input_tokens": 0}}
    d.update(extra)
    return 200, json.dumps(d), {}


def api_err(status, etype, msg, headers=None):
    return status, json.dumps({"type": "error", "error": {"type": etype, "message": msg}}), (headers or {})


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, body, timeout_s):
        self.calls.append({"url": url, "headers": headers, "body": json.loads(body), "timeout": timeout_s})
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class Echo(Tool):
    name = "echo"
    description = "echo"
    params = {"text": {"type": "string", "description": "t"}}
    required = ["text"]
    parallel_safe = True

    def run(self, text):
        return ToolResult(text != "fail", "echo:" + text)


def make(responses, **kw):
    t = FakeTransport(responses)
    kw.setdefault("api_key", "sk-test")
    llm = AnthropicAPILLM(transport=t, **kw)
    return llm, t


# ------------------------------------------------------------- conversion --

def test_history_to_wire_shape_merges_tool_results_and_marks_errors():
    hist = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": "looking", "tool_calls": [
            {"name": "echo", "args": {"text": "a"}, "call_id": "toolu_1"},
            {"name": "echo", "args": {"text": "fail"}, "call_id": "toolu_2"}]},
        {"role": "tool", "content": "echo:a", "tool_call_id": "toolu_1", "tool_name": "echo", "ok": True},
        {"role": "tool", "content": "ERROR: echo:fail", "tool_call_id": "toolu_2", "tool_name": "echo", "ok": False},
        {"role": "assistant", "content": "done", "tool_calls": []},
    ]
    system, msgs = to_anthropic_messages(hist)
    assert system == "SYS"
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[1]["content"][0] == {"type": "text", "text": "looking"}
    assert msgs[1]["content"][1] == {"type": "tool_use", "id": "toolu_1", "name": "echo", "input": {"text": "a"}}
    results = msgs[2]["content"]
    assert len(results) == 2 and all(r["type"] == "tool_result" for r in results)
    assert "is_error" not in results[0] and results[1]["is_error"] is True
    assert results[1]["tool_use_id"] == "toolu_2"
    assert msgs[3]["content"] == [{"type": "text", "text": "done"}]


def test_empty_assistant_turn_gets_placeholder_block():
    _, msgs = to_anthropic_messages([{"role": "user", "content": "x"},
                                     {"role": "assistant", "content": "", "tool_calls": []}])
    assert msgs[1]["content"] == [{"type": "text", "text": "(no content)"}]


def test_unknown_role_is_fatal():
    with pytest.raises(FatalLLMError):
        to_anthropic_messages([{"role": "weird", "content": "x"}])


# ---------------------------------------------------------------- parsing --

def test_parse_tool_use_blocks_and_usage():
    turn = parse_api_message({"content": [
        {"type": "thinking", "thinking": ""},
        {"type": "text", "text": "I will echo."},
        {"type": "tool_use", "id": "toolu_9", "name": "echo", "input": {"text": "hi"}},
        {"type": "tool_use", "id": "toolu_10", "name": "echo", "input": "notdict"},
    ], "stop_reason": "tool_use", "usage": {"input_tokens": 3, "output_tokens": 4}})
    assert turn.text == "I will echo." and turn.raw_stop_reason == "tool_use"
    assert [c.call_id for c in turn.tool_calls] == ["toolu_9", "toolu_10"]
    assert turn.tool_calls[0].args == {"text": "hi"}
    assert "error" in turn.tool_calls[1].args           # bad input surfaces as an arg error
    assert turn.usage == Usage(3, 4, 0, 0)


def test_refusal_drops_tool_calls_and_labels_text():
    turn = parse_api_message({"content": [{"type": "tool_use", "id": "t", "name": "echo", "input": {}}],
                              "stop_reason": "refusal",
                              "stop_details": {"type": "refusal", "category": "cyber"}})
    assert turn.tool_calls == [] and "refused: cyber" in turn.text and not turn.wants_tools


# ------------------------------------------------------ thinking replay ---
# Round 13: when extended thinking is on and a turn calls tools, the API
# requires the thinking/redacted_thinking blocks that preceded the tool_use
# to come back byte-identical (signature included) on the next request, or
# it rejects it. parse_api_message keeps the raw blocks; to_anthropic_messages
# replays them instead of reconstructing from text/tool_calls.

THINKING_BLOCK = {"type": "thinking", "thinking": "let me check the file first",
                  "signature": "sig_abcdef123"}
REDACTED_BLOCK = {"type": "redacted_thinking", "data": "opaque_base64=="}


def test_parse_api_message_keeps_raw_content_with_thinking_blocks():
    content = [THINKING_BLOCK, {"type": "text", "text": "checking"},
               {"type": "tool_use", "id": "toolu_1", "name": "echo", "input": {"text": "hi"}}]
    turn = parse_api_message({"content": content, "stop_reason": "tool_use", "usage": {}})
    assert turn.raw_content == content            # exact blocks, in order, signature intact
    assert turn.text == "checking"                # thinking text itself never leaks into .text
    assert [c.name for c in turn.tool_calls] == ["echo"]


def test_parse_api_message_no_content_leaves_raw_content_none():
    turn = parse_api_message({"content": [], "stop_reason": "end_turn", "usage": {}})
    assert turn.raw_content is None


def test_to_anthropic_messages_replays_raw_content_verbatim():
    hist = [{"role": "user", "content": "u"},
            {"role": "assistant", "content": "checking", "tool_calls": [
                {"name": "echo", "args": {"text": "hi"}, "call_id": "toolu_1"}],
             "raw_content": [THINKING_BLOCK, REDACTED_BLOCK,
                             {"type": "text", "text": "checking"},
                             {"type": "tool_use", "id": "toolu_1", "name": "echo",
                              "input": {"text": "hi"}}]}]
    _, msgs = to_anthropic_messages(hist)
    # byte-identical to what the API sent, including the signature field --
    # NOT reconstructed from content/tool_calls (which would drop the two
    # thinking blocks entirely).
    assert msgs[1]["content"] == hist[0 + 1]["raw_content"]
    assert msgs[1]["content"][0]["signature"] == "sig_abcdef123"


def test_to_anthropic_messages_without_raw_content_falls_back_as_before():
    hist = [{"role": "user", "content": "u"},
            {"role": "assistant", "content": "no thinking here", "tool_calls": []}]
    _, msgs = to_anthropic_messages(hist)
    assert msgs[1]["content"] == [{"type": "text", "text": "no thinking here"}]


def test_full_agent_run_replays_thinking_blocks_on_the_second_request():
    responses = [
        api_ok([THINKING_BLOCK, {"type": "text", "text": "checking"},
               {"type": "tool_use", "id": "toolu_1", "name": "echo", "input": {"text": "hi"}}],
              stop="tool_use"),
        api_ok([{"type": "text", "text": "done"}]),
    ]
    llm, t = make(responses, thinking={"type": "enabled", "budget_tokens": 1024})
    agent = Agent(llm, ToolRegistry([Echo()]), AgentConfig())
    r = agent.run("go")
    assert r.ok and r.final_text == "done"
    assert r.messages[2].get("raw_content") is not None       # stashed on the assistant message
    second_body = t.calls[1]["body"]
    assistant_block = second_body["messages"][1]
    assert assistant_block["content"][0] == THINKING_BLOCK    # replayed verbatim, signature intact
    assert assistant_block["content"][0]["type"] == "thinking"


# ------------------------------------------------------------ transport ---

def test_request_headers_body_and_url_for_api_key():
    llm, t = make([api_ok([{"type": "text", "text": "hi"}])], model="claude-opus-5",
                  max_tokens=999, effort="high", thinking={"type": "adaptive"})
    turn = llm.complete([{"role": "system", "content": "S"}, {"role": "user", "content": "U"}],
                        [Echo().spec()])
    assert turn.text == "hi"
    call = t.calls[0]
    assert call["url"] == "https://api.anthropic.com/v1/messages"
    h = call["headers"]
    assert h["x-api-key"] == "sk-test" and h["anthropic-version"] == "2023-06-01"
    assert "authorization" not in h
    b = call["body"]
    assert b["model"] == "claude-opus-5" and b["max_tokens"] == 999 and b["system"] == "S"
    assert b["messages"] == [{"role": "user", "content": "U"}]
    assert b["tools"][0]["name"] == "echo" and "input_schema" in b["tools"][0]
    assert b["thinking"] == {"type": "adaptive"} and b["output_config"] == {"effort": "high"}
    assert llm.usage == Usage(100, 10, 50, 0)


def test_extra_body_passes_through_arbitrary_fields_eg_fallbacks():
    # There is no dedicated `fallbacks` kwarg -- extra_body is the generic
    # escape hatch for any top-level Messages API field the adapter doesn't
    # special-case yet (model fallback lists included), merged last so it can
    # also override a field the adapter does set.
    llm, t = make([api_ok([{"type": "text", "text": "hi"}])],
                  model="claude-fable-5",
                  extra_body={"fallbacks": ["claude-opus-5", "claude-sonnet-5"],
                              "max_tokens": 555})
    llm.complete([{"role": "user", "content": "u"}], [])
    body = t.calls[0]["body"]
    assert body["fallbacks"] == ["claude-opus-5", "claude-sonnet-5"]
    assert body["max_tokens"] == 555          # extra_body overrides the constructor default
    assert body["model"] == "claude-fable-5"  # unrelated fields untouched


def test_oauth_token_uses_bearer_header_and_beta():
    llm, t = make([api_ok([{"type": "text", "text": "x"}])], api_key=None, auth_token="tok")
    llm.complete([{"role": "user", "content": "u"}], [])
    h = t.calls[0]["headers"]
    assert h["authorization"] == "Bearer tok" and h["anthropic-beta"] == "oauth-2025-04-20"
    assert "x-api-key" not in h


def test_no_credentials_is_fatal_at_construction(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(FatalLLMError):
        AnthropicAPILLM(transport=FakeTransport([]))


@pytest.mark.parametrize("status,etype,exc", [
    (429, "rate_limit_error", RetryableLLMError),
    (529, "overloaded_error", RetryableLLMError),
    (500, "api_error", RetryableLLMError),
    (400, "invalid_request_error", FatalLLMError),
    (401, "authentication_error", FatalLLMError),
    (404, "not_found_error", FatalLLMError),
    (413, "request_too_large", FatalLLMError),
])
def test_status_code_mapping(status, etype, exc):
    llm, _ = make([api_err(status, etype, "boom")])
    with pytest.raises(exc) as ei:
        llm.complete([{"role": "user", "content": "u"}], [])
    assert etype in str(ei.value) and "boom" in str(ei.value)


# ---------------------------------------------------------- retry-after ---
# Round 13: a retryable HTTP response's `retry-after` header should reach
# retry_call() as RetryableLLMError.retry_after, so the harness waits exactly
# as long as the server asked instead of guessing exponentially.

def test_retry_after_header_parsed_onto_the_exception():
    llm, _ = make([api_err(429, "rate_limit_error", "slow down", headers={"retry-after": "2.5"})])
    with pytest.raises(RetryableLLMError) as ei:
        llm.complete([{"role": "user", "content": "u"}], [])
    assert ei.value.retry_after == pytest.approx(2.5)


def test_retry_after_header_lookup_is_case_insensitive():
    llm, _ = make([api_err(429, "rate_limit_error", "slow down", headers={"Retry-After": "9"})])
    with pytest.raises(RetryableLLMError) as ei:
        llm.complete([{"role": "user", "content": "u"}], [])
    assert ei.value.retry_after == 9.0


def test_retry_after_missing_or_non_numeric_is_none():
    llm, _ = make([api_err(429, "rate_limit_error", "slow down")])
    with pytest.raises(RetryableLLMError) as ei:
        llm.complete([{"role": "user", "content": "u"}], [])
    assert ei.value.retry_after is None

    llm2, _ = make([api_err(429, "rate_limit_error", "slow down",
                            headers={"retry-after": "Fri, 01 Jan 2027 00:00:00 GMT"})])
    with pytest.raises(RetryableLLMError) as ei2:
        llm2.complete([{"role": "user", "content": "u"}], [])
    assert ei2.value.retry_after is None   # HTTP-date form is not parsed, not guessed


def test_agent_run_honors_retry_after_over_exponential_backoff():
    responses = [
        api_err(429, "rate_limit_error", "slow down", headers={"retry-after": "17"}),
        api_ok([{"type": "text", "text": "ok"}]),
    ]
    llm, _ = make(responses)
    sleeps = []
    agent = Agent(llm, ToolRegistry([]),
                  AgentConfig(retry_policy=RetryPolicy(max_attempts=3, base_delay=1.0)),
                  sleep=sleeps.append, rng=lambda: 0.5)
    r = agent.run("hi")
    assert r.ok and sleeps == [17.0]   # not the policy's own 1.0s guess


def test_network_fault_and_garbage_body():
    llm, _ = make([RetryableLLMError("network error"), (200, "<html>", {})])
    with pytest.raises(RetryableLLMError):
        llm.complete([{"role": "user", "content": "u"}], [])
    with pytest.raises(FatalLLMError):
        llm.complete([{"role": "user", "content": "u"}], [])


def test_count_tokens_endpoint_strips_max_tokens():
    llm, t = make([(200, json.dumps({"input_tokens": 42}), {})])
    assert llm.count_tokens([{"role": "user", "content": "u"}], [Echo().spec()]) == 42
    assert t.calls[0]["url"].endswith("/v1/messages/count_tokens")
    assert "max_tokens" not in t.calls[0]["body"] and "tools" in t.calls[0]["body"]


# ------------------------------------------------------- through the loop --

def test_full_agent_run_calls_count_tokens_before_completion_when_exact_check_enabled():
    responses = [
        (200, json.dumps({"input_tokens": 7}), {}),   # exact check, step 1, before the completion
        api_ok([{"type": "text", "text": "done"}]),
    ]
    llm, t = make(responses)
    agent = Agent(llm, ToolRegistry([]),
                  AgentConfig(context_budget=ContextBudget(max_input_tokens=100_000),
                             exact_token_check=True, exact_token_margin=100_000))
    r = agent.run("hi")
    assert r.ok and r.final_text == "done"
    assert t.calls[0]["url"].endswith("/v1/messages/count_tokens")
    assert t.calls[1]["url"].endswith("/v1/messages")
    assert llm.usage.total_input > 0   # the real completion's usage, not the count_tokens call


def test_full_agent_run_over_fake_api_with_parallel_results_and_retry():
    responses = [
        api_err(529, "overloaded_error", "busy"),
        api_ok([{"type": "text", "text": "two echos"},
                {"type": "tool_use", "id": "toolu_a", "name": "echo", "input": {"text": "A"}},
                {"type": "tool_use", "id": "toolu_b", "name": "echo", "input": {"text": "fail"}}],
               stop="tool_use"),
        api_ok([{"type": "text", "text": "final"}], usage={"input_tokens": 200, "output_tokens": 20}),
    ]
    llm, t = make(responses, model="claude-opus-5")
    agent = Agent(llm, ToolRegistry([Echo()]),
                  AgentConfig(parallel_tools=True, retry_policy=RetryPolicy(max_attempts=3)),
                  sleep=lambda s: None, rng=lambda: 0.5)
    r = agent.run("echo things")
    assert r.ok and r.final_text == "final" and r.steps == 2 and r.tool_calls == 2
    # third request carries both results in ONE user message, with is_error on the failure
    last_body = t.calls[-1]["body"]
    assert last_body["messages"][-1]["role"] == "user"
    blocks = last_body["messages"][-1]["content"]
    assert [b["tool_use_id"] for b in blocks] == ["toolu_a", "toolu_b"]
    assert blocks[1].get("is_error") is True and blocks[1]["content"].startswith("ERROR:")
    # usage summed across both successful completions and priced
    assert r.usage == Usage(300, 30, 50, 0)
    assert r.cost_usd == pytest.approx(Usage(300, 30, 50, 0).cost_usd("claude-opus-5"))
    assert [e["event"] for e in agent.trace.events].count("llm_retry") == 1
