"""AnthropicAPILLM streaming (stream=True): SSE parsing, block accumulation,
mid-stream vs pre-stream errors, and the full agent loop over a fake
streaming transport.

Round 13: streaming exists because Anthropic's Messages API rejects large
`max_tokens` requests outright unless stream=True (it will not hold a
non-streaming connection open for the many minutes a huge completion could
take). accumulate_stream() reconstructs the exact dict shape
parse_api_message() already handles for non-streaming responses, so thinking
replay / tool_use parsing / usage accounting all work unmodified -- only the
transport layer and event bookkeeping are new.
"""
import json

import pytest

from agentloop import Agent, AgentConfig, ToolRegistry
from agentloop.adapters import (AnthropicAPILLM, parse_sse_events, accumulate_stream,
                                parse_api_message)
from agentloop.llm import RetryableLLMError, FatalLLMError
from agentloop.tools import Tool, ToolResult


def sse(event, data):
    """One SSE frame as the list of raw lines a real connection would yield."""
    return ["event: %s" % event, "data: %s" % json.dumps(data), ""]


def stream_of(*frames):
    lines = []
    for event, data in frames:
        lines += sse(event, data)
    return lines


class FakeStreamTransport:
    """Queued (status, headers, lines) triples, one per call -- mirrors
    FakeTransport in test_anthropic_api.py but for the streaming shape."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, body, timeout_s):
        self.calls.append({"url": url, "headers": headers, "body": json.loads(body), "timeout": timeout_s})
        status, hdrs, lines = self.responses.pop(0)
        return status, hdrs, iter(lines)


class Echo(Tool):
    name = "echo"
    description = "echo"
    params = {"text": {"type": "string", "description": "t"}}
    required = ["text"]
    parallel_safe = True

    def run(self, text):
        return ToolResult(True, "echo:" + text)


def make(responses, **kw):
    t = FakeStreamTransport(responses)
    kw.setdefault("api_key", "sk-test")
    llm = AnthropicAPILLM(stream=True, stream_transport=t, **kw)
    return llm, t


# ------------------------------------------------------------- SSE parsing --

def test_parse_sse_events_groups_on_blank_lines_and_reads_event_and_data():
    lines = stream_of(("message_start", {"a": 1}), ("content_block_stop", {"b": 2}))
    events = list(parse_sse_events(lines))
    assert events == [("message_start", {"a": 1}), ("content_block_stop", {"b": 2})]


def test_parse_sse_events_skips_comments_and_falls_back_to_payload_type():
    lines = [": heartbeat", "data: %s" % json.dumps({"type": "ping"}), ""]
    events = list(parse_sse_events(lines))
    assert events == [("ping", {"type": "ping"})]   # no "event:" line -> payload's own type


def test_parse_sse_events_handles_missing_trailing_blank_line():
    lines = ["event: message_stop", "data: {}"]   # stream ends without a final blank line
    events = list(parse_sse_events(lines))
    assert events == [("message_stop", {})]


def test_parse_sse_events_malformed_json_data_yields_empty_dict_not_a_crash():
    lines = ["event: content_block_delta", "data: {not json", ""]
    events = list(parse_sse_events(lines))
    assert events == [("content_block_delta", {})]


# ------------------------------------------------------------ accumulation --

def test_accumulate_stream_reassembles_text_thinking_and_tool_use_blocks():
    frames = [
        ("message_start", {"message": {"id": "msg_1", "role": "assistant",
                                       "usage": {"input_tokens": 50, "output_tokens": 0}}}),
        ("content_block_start", {"index": 0, "content_block": {"type": "thinking", "thinking": "", "signature": ""}}),
        ("content_block_delta", {"index": 0, "delta": {"type": "thinking_delta", "thinking": "let me "}}),
        ("content_block_delta", {"index": 0, "delta": {"type": "thinking_delta", "thinking": "check"}}),
        ("content_block_delta", {"index": 0, "delta": {"type": "signature_delta", "signature": "sig123"}}),
        ("content_block_stop", {"index": 0}),
        ("content_block_start", {"index": 1, "content_block": {"type": "tool_use", "id": "toolu_1", "name": "echo"}}),
        ("content_block_delta", {"index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"tex'}}),
        ("content_block_delta", {"index": 1, "delta": {"type": "input_json_delta", "partial_json": 't": "hi"}'}}),
        ("content_block_stop", {"index": 1}),
        ("message_delta", {"delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 12}}),
        ("message_stop", {}),
    ]
    data, err = accumulate_stream(frames)
    assert err is None
    assert data["content"][0] == {"type": "thinking", "thinking": "let me check", "signature": "sig123"}
    assert data["content"][1] == {"type": "tool_use", "id": "toolu_1", "name": "echo", "input": {"text": "hi"}}
    assert data["stop_reason"] == "tool_use"
    assert data["usage"] == {"input_tokens": 50, "output_tokens": 12}
    # the assembled dict is exactly what the non-streaming parser expects
    turn = parse_api_message(data)
    assert turn.tool_calls[0].args == {"text": "hi"}
    assert turn.raw_content[0]["signature"] == "sig123"


def test_accumulate_stream_joins_text_deltas_across_multiple_frames():
    frames = [
        ("content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "Hel"}}),
        ("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "lo, "}}),
        ("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "world"}}),
        ("content_block_stop", {"index": 0}),
        ("message_delta", {"delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 3}}),
    ]
    data, err = accumulate_stream(frames)
    assert err is None
    turn = parse_api_message(data)
    assert turn.text == "Hello, world"


def test_accumulate_stream_malformed_tool_json_becomes_an_arg_error_not_a_crash():
    frames = [
        ("content_block_start", {"index": 0, "content_block": {"type": "tool_use", "id": "t", "name": "echo"}}),
        ("content_block_delta", {"index": 0, "delta": {"type": "input_json_delta", "partial_json": '{"broken'}}),
        ("content_block_stop", {"index": 0}),
    ]
    data, err = accumulate_stream(frames)
    assert err is None
    turn = parse_api_message(data)
    assert "error" in turn.tool_calls[0].args


def test_accumulate_stream_error_event_returns_partial_content_and_the_error():
    frames = [
        ("content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "partial"}}),
        ("error", {"error": {"type": "overloaded_error", "message": "server overloaded"}}),
    ]
    data, err = accumulate_stream(frames)
    assert err == ("overloaded_error", "server overloaded")
    assert data["content"][0]["text"] == "partial"   # what streamed before the drop is preserved


def test_accumulate_stream_out_of_order_or_unknown_index_does_not_crash():
    frames = [("content_block_delta", {"index": 5, "delta": {"type": "text_delta", "text": "x"}}),
             ("content_block_stop", {"index": 5})]
    data, err = accumulate_stream(frames)
    assert err is None and data["content"] == []   # skipped, not KeyError/IndexError


# -------------------------------------------------------- transport wiring --

def test_stream_true_sends_accept_header_and_stream_flag_in_body():
    llm, t = make([(200, {}, stream_of(
        ("content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "hi"}}),
        ("content_block_stop", {"index": 0}),
        ("message_delta", {"delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 1}}),
    ))])
    turn = llm.complete([{"role": "user", "content": "u"}], [])
    assert turn.text == "hi"
    call = t.calls[0]
    assert call["headers"]["accept"] == "text/event-stream"
    assert call["body"]["stream"] is True


def test_pre_stream_http_error_maps_status_like_non_streaming(monkeypatch):
    err_body = json.dumps({"type": "error", "error": {"type": "overloaded_error", "message": "busy"}})
    llm, t = make([(529, {}, err_body.splitlines())])
    with pytest.raises(RetryableLLMError) as ei:
        llm.complete([{"role": "user", "content": "u"}], [])
    assert "overloaded_error" in str(ei.value) and "busy" in str(ei.value)


def test_pre_stream_http_error_retry_after_header_is_parsed():
    err_body = json.dumps({"type": "error", "error": {"type": "rate_limit_error", "message": "slow"}})
    llm, t = make([(429, {"retry-after": "4"}, err_body.splitlines())])
    with pytest.raises(RetryableLLMError) as ei:
        llm.complete([{"role": "user", "content": "u"}], [])
    assert ei.value.retry_after == 4.0


def test_pre_stream_fatal_status_is_not_retried():
    err_body = json.dumps({"type": "error", "error": {"type": "invalid_request_error", "message": "bad"}})
    llm, t = make([(400, {}, err_body.splitlines())])
    with pytest.raises(FatalLLMError):
        llm.complete([{"role": "user", "content": "u"}], [])


def test_mid_stream_error_event_is_retryable_by_error_type():
    llm, t = make([(200, {}, stream_of(
        ("content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}}),
        ("error", {"error": {"type": "overloaded_error", "message": "dropped"}}),
    ))])
    with pytest.raises(RetryableLLMError) as ei:
        llm.complete([{"role": "user", "content": "u"}], [])
    assert "dropped" in str(ei.value)


def test_mid_stream_error_event_unknown_type_is_fatal():
    llm, t = make([(200, {}, stream_of(
        ("content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}}),
        ("error", {"error": {"type": "invalid_request_error", "message": "bad request mid-stream"}}),
    ))])
    with pytest.raises(FatalLLMError):
        llm.complete([{"role": "user", "content": "u"}], [])


# ---------------------------------------------------------- through a run --

def test_full_agent_run_over_a_streaming_backend_with_tool_use_and_thinking():
    responses = [
        (200, {}, stream_of(
            ("message_start", {"message": {"usage": {"input_tokens": 20, "output_tokens": 0}}}),
            ("content_block_start", {"index": 0, "content_block": {"type": "thinking", "thinking": "", "signature": ""}}),
            ("content_block_delta", {"index": 0, "delta": {"type": "thinking_delta", "thinking": "use echo"}}),
            ("content_block_delta", {"index": 0, "delta": {"type": "signature_delta", "signature": "sig9"}}),
            ("content_block_stop", {"index": 0}),
            ("content_block_start", {"index": 1, "content_block": {"type": "tool_use", "id": "toolu_1", "name": "echo"}}),
            ("content_block_delta", {"index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"text": "hi"}'}}),
            ("content_block_stop", {"index": 1}),
            ("message_delta", {"delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 15}}),
        )),
        (200, {}, stream_of(
            ("content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}}),
            ("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "done"}}),
            ("content_block_stop", {"index": 0}),
            ("message_delta", {"delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 2}}),
        )),
    ]
    llm, t = make(responses)
    agent = Agent(llm, ToolRegistry([Echo()]), AgentConfig())
    r = agent.run("go")
    assert r.ok and r.final_text == "done" and r.steps == 2 and r.tool_calls == 1
    # thinking block from step 1 was replayed verbatim into request 2
    second_body = t.calls[1]["body"]
    assistant_block = second_body["messages"][1]["content"]
    assert assistant_block[0]["type"] == "thinking" and assistant_block[0]["signature"] == "sig9"
    assert r.usage.input_tokens == 20 and r.usage.output_tokens == 17   # 15 + 2, summed across streamed turns
