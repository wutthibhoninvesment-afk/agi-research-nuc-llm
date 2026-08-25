"""Offline tests for prompt_budget.py (round 22, mission E2).

Run under the hermes venv python (has `tokenizers`):
  ~/.hermes/hermes-agent/venv/bin/python -m pytest nuc/tests/test_prompt_budget.py -q
Tokenizer-dependent tests skip cleanly elsewhere.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import prompt_budget as pb  # noqa: E402

try:
    import tokenizers  # noqa: F401
    HAVE_TOK = os.path.exists(pb.TOKENIZER_JSON)
except ImportError:
    HAVE_TOK = False

needs_tok = pytest.mark.skipif(not HAVE_TOK, reason="tokenizers lib or tokenizer.json missing")


# --- engine template replica -------------------------------------------------

def test_template_frames_and_preclosed_think():
    msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
    out = pb.render_chat_qwen(msgs)
    assert out == ("<|im_start|>system\nS<|im_end|>\n"
                   "<|im_start|>user\nU<|im_end|>\n"
                   "<|im_start|>assistant\n<think>\n\n</think>\n\n")


def test_template_thinking_variant_and_developer_alias():
    out = pb.render_chat_qwen([{"role": "developer", "content": "D"}], enable_thinking=True)
    assert out == "<|im_start|>system\nD<|im_end|>\n<|im_start|>assistant\n<think>\n"


# --- adapter import (byte-identical NUC copy) --------------------------------

def test_adapter_renders_tools_into_system():
    ad = pb.load_adapter()
    tools = [{"type": "function", "function": {
        "name": "read_file", "description": "Read a file.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}]
    msgs = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}]
    rendered = ad.messages_to_text(msgs, tools)
    assert rendered[0]["role"] == "system"
    assert rendered[0]["content"].startswith("SYS\n\nYou have tools available.")
    assert '"name": "read_file"' in rendered[0]["content"]
    assert rendered[1] == {"role": "user", "content": "hi"}


def test_adapter_tool_result_flattening():
    ad = pb.load_adapter()
    msgs = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "tool_calls": [{"function": {
            "name": "f", "arguments": '{"a": 1}'}}]},
        {"role": "tool", "name": "f", "content": "result!"},
    ]
    rendered = ad.messages_to_text(msgs, None)
    roles = [m["role"] for m in rendered]
    assert roles == ["user", "assistant", "user"]
    assert '{"tool_calls": [{"name": "f", "arguments": {"a": 1}}]}' in rendered[1]["content"]
    assert rendered[2]["content"] == "[tool_result name=f]\nresult!\n[/tool_result]"


# --- token counting ----------------------------------------------------------

@needs_tok
def test_specials_are_single_tokens():
    c = pb.Counter()
    assert c.n("<|im_start|>") == 1
    assert c.n("<|im_end|>") == 1


@needs_tok
def test_breakdown_components_sum_to_total():
    c = pb.Counter()
    req = {
        "messages": [{"role": "system", "content": "You are a NUC agent."},
                     {"role": "user", "content": "list the files"}],
        "tools": [{"type": "function", "function": {
            "name": "ls", "description": "List directory.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}],
    }
    b = pb.breakdown(req, c)
    assert (b["framing_floor"] + b["system_prompt_tokens"] + b["tools_block_tokens"]
            + b["conversation_tokens"] == b["total_prompt_tokens"])
    assert b["n_tools"] == 1
    assert b["tools_block_tokens"] > 40  # protocol block alone is substantial


@needs_tok
def test_no_tools_request_has_zero_tools_block():
    c = pb.Counter()
    req = {"messages": [{"role": "user", "content": "hi"}]}
    b = pb.breakdown(req, c)
    assert b["tools_block_tokens"] == 0
    assert b["n_tools"] == 0


# --- timing model ------------------------------------------------------------

def test_ttft_hits_anchors_exactly():
    for tok, s in pb.E1_ANCHORS:
        assert abs(pb.ttft_projected(tok) - s) < 1e-9


def test_ttft_monotonic_and_convex_regions():
    xs = [50, 134, 500, 904, 2000, 3998, 8000, 26500]
    ys = [pb.ttft_projected(x) for x in xs]
    assert all(a < b for a, b in zip(ys, ys[1:]))
    # beyond last anchor: marginal rate, so 26.5k lands near E1's ~87 min claim
    assert 70 * 60 < pb.ttft_projected(26500) < 100 * 60


def test_turn_time_adds_decode():
    assert pb.turn_time(904, 60) == pytest.approx(143.1 + 60 / 5.3)


# --- engine-tokenizer emulation, pinned to 19 usage.prompt_tokens
# --- measurements taken from :8000 on 2026-08-24 (round 22)

CAL_SYS = ("You are a careful assistant running on a small local machine. Answer "
           "briefly and precisely, and do not speculate beyond the question asked.")
CAL_USR = ("Name the four largest moons of Jupiter and one distinguishing fact "
           "about each of them, in a compact numbered list.")


def _calib_msgs():
    return [{"role": "system", "content": CAL_SYS},
            {"role": "user", "content": CAL_USR}]


@needs_tok
def test_engine_emulation_matches_all_measurements():
    c = pb.Counter()
    full = pb.render_chat_qwen(_calib_msgs())
    h1 = f"<|im_start|>system\n{CAL_SYS}<|im_end|>\n"
    h2 = h1 + f"<|im_start|>user\n{CAL_USR}<|im_end|>\n"
    h3 = h2 + "<|im_start|>assistant\n"
    cases = [
        ("hello world", 2), (full, 73), ("<|im_start|>", 1),
        ("<think>\n\n</think>\n\n", 4),
        ("<|im_start|>system\nhi<|im_end|>\n", 6),
        (CAL_SYS, 26), (CAL_USR, 22),
        (h1, 35), (h2, 66), (h3, 69),
        ("<|im_start|>system\n" + CAL_SYS, 29),
        (CAL_SYS + "<|im_end|>\n", 32),
        ("system\n" + CAL_SYS, 28),
        ("asked.<|im_end|>\n", 9), ("asked!<|im_end|>\n", 9),
        ("asked<|im_end|>\n", 4), (".<|im_end|>", 6),
        ("asked.<|im_start|>", 8), ("asked.</think>", 5),
    ]
    for text, engine in cases:
        assert c.n_engine(text) == engine, (repr(text[:60]), c.n_engine(text), engine)


@needs_tok
def test_plain_vs_engine_divergence_is_punctuation_only():
    c = pb.Counter()
    # letters/whitespace before a special: two modes agree
    assert c.n("hi<|im_end|>\n") == c.n_engine("hi<|im_end|>\n")
    # punctuation before a special: engine spells the special out as text
    assert c.n_engine("x.<|im_end|>") > c.n("x.<|im_end|>")
