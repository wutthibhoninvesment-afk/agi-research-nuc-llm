#!/usr/bin/env python3
"""E2 — Hermes prompt budget for the NUC (round 22).

Counts the EXACT engine-side prompt tokens of a Hermes agent turn without
paying NUC prefill: reproduce the full render pipeline locally
(Hermes request -> tool-proxy adapter rendering -> colibri qwen36 chat
template -> HF tokenizers on the model's own tokenizer.json), then
calibrate the pipeline against `usage.prompt_tokens` from :8000 with two
SMALL requests.

Pipeline fidelity:
- adapter stage: imported from nuc-adapter-copy.py (byte-identical copy of
  /work/src/qwen36-toolproxy/adapter.py, fetched this round) — not
  re-implemented, so it cannot drift.
- engine stage: render_chat_qwen replicated below from
  /work/src/colibri-v170/c/openai_server.py lines 921-949 (read this round);
  coli serve defaults enable_thinking=False -> pre-closed <think> block.
- tokenizer: /work/models/qwen36_i4_gs64/tokenizer.json (same file the
  engine loads), special tokens encode as single ids.

Usage (run under the hermes venv python, which has `tokenizers`):
  prompt_budget.py count REQUEST.json   # component token breakdown
  prompt_budget.py render REQUEST.json  # emit the exact engine prompt string
  prompt_budget.py project N [N...]     # TTFT/turn-time projection for N tokens
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOKENIZER_JSON = os.path.join(HERE, "tokenizer-qwen36.json")
ADAPTER_COPY = os.path.join(HERE, "nuc-adapter-copy.py")


def load_adapter():
    """Import the byte-identical local copy of the NUC tool-proxy adapter."""
    spec = importlib.util.spec_from_file_location("nuc_adapter", ADAPTER_COPY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def render_chat_qwen(messages, enable_thinking=False):
    """Replica of colibri openai_server.py render_chat_qwen (text-only subset
    of Qwen3.6's chat template). Roles must already be system/user/assistant
    (the adapter guarantees that)."""
    parts = []
    for message in messages:
        role = message.get("role")
        if role == "developer":
            role = "system"
        text = message.get("content") or ""
        parts.append(f"<|im_start|>{role}\n{text}<|im_end|>\n")
    parts.append("<|im_start|>assistant\n")
    parts.append("<think>\n" if enable_thinking else "<think>\n\n</think>\n\n")
    return "".join(parts)


SPECIALS = ("<|im_start|>", "<|im_end|>", "<think>", "</think>")


class Counter:
    """Token counter with two modes.

    `n(text)` — plain HF-tokenizers count (specials always match).
    `n_engine(text)` — replicates the colibri qwen36 WORKER's measured
    behavior (round 22 probes k1–k6): a special token directly preceded by a
    punctuation/symbol character does NOT match (the GPT-2-style pretokenizer
    glues the punctuation run to the special's leading "<", hiding it), and
    its literal text falls through to plain BPE merged with the surrounding
    text. Preceded by letters, digits, whitespace, start-of-string, or
    another matched special, it matches as one id. Verified against 17
    usage.prompt_tokens measurements from :8000 (see test file).
    """

    def __init__(self, tokenizer_path=TOKENIZER_JSON):
        from tokenizers import Tokenizer
        self.tok = Tokenizer.from_file(tokenizer_path)
        plain = json.load(open(tokenizer_path))
        for at in plain.get("added_tokens", []):
            at["content"] = "\x00PLAIN\x00" + at["content"]  # unmatchable
        self.tok_plain = Tokenizer.from_str(json.dumps(plain))

    def n(self, text: str) -> int:
        return len(self.tok.encode(text).ids)

    def n_engine(self, text: str) -> int:
        total, buf, i, prev_was_special = 0, [], 0, False
        while i < len(text):
            hit = next((s for s in SPECIALS if text.startswith(s, i)), None)
            if hit:
                boundary = (i == 0 or prev_was_special or
                            (buf and buf[-1] and (buf[-1][-1].isalnum()
                                                  or buf[-1][-1].isspace())))
                if boundary:
                    joined = "".join(buf)
                    if joined:
                        total += len(self.tok_plain.encode(joined).ids)
                    buf, total, prev_was_special = [], total + 1, True
                else:
                    buf.append(hit)          # failed match: literal text
                    prev_was_special = False
                i += len(hit)
            else:
                buf.append(text[i])
                prev_was_special = False
                i += 1
        joined = "".join(buf)
        if joined:
            total += len(self.tok_plain.encode(joined).ids)
        return total


def engine_prompt(request: dict, adapter=None) -> str:
    """Hermes-style OpenAI request dict -> exact engine prompt string."""
    adapter = adapter or load_adapter()
    rendered = adapter.messages_to_text(request.get("messages"), request.get("tools"))
    return render_chat_qwen(rendered)


def breakdown(request: dict, counter: Counter) -> dict:
    """Token cost per component, plus the exact total.

    Components are measured by differential rendering (render with/without a
    part), so shared framing tokens are attributed once and the parts sum to
    the total exactly.
    """
    adapter = load_adapter()
    msgs = request.get("messages") or []
    tools = request.get("tools")

    total = counter.n_engine(engine_prompt(request, adapter))
    no_tools = counter.n_engine(engine_prompt({"messages": msgs}, adapter))
    sys_only = counter.n_engine(engine_prompt(
        {"messages": [m for m in msgs if m.get("role") in ("system", "developer")]},
        adapter))
    empty = counter.n_engine(render_chat_qwen([]))  # generation-prompt framing floor

    n_tools = len(tools or [])
    per_tool = []
    if tools:
        base_one = counter.n_engine(engine_prompt({"messages": [], "tools": []}, adapter))
        for t in tools:
            f = t.get("function", t)
            one = counter.n_engine(engine_prompt({"messages": [], "tools": [t]}, adapter))
            per_tool.append({"name": f.get("name"), "tokens": one - base_one})

    return {
        "total_prompt_tokens": total,
        "framing_floor": empty,
        "system_prompt_tokens": sys_only - empty,
        "tools_block_tokens": total - no_tools,
        "conversation_tokens": no_tools - sys_only,
        "n_tools": n_tools,
        "per_tool": sorted(per_tool, key=lambda d: -d["tokens"]),
    }


# --- E1 timing model ---------------------------------------------------------
# Anchors: (prompt_tokens, TTFT_s) measured round 10/16, engine warm.
E1_ANCHORS = [(134, 23.3), (904, 143.1), (3998, 770.3)]
MARGINAL_S_PER_TOK = 0.196          # 1k-8k fit slope (5.1 tok/s)
DECODE_TOK_S_SMALL_KV = 5.3         # decode rate at KV <= ~1k


def ttft_projected(tokens: float) -> float:
    """Piecewise-linear interpolation over E1 anchors; marginal-rate
    extrapolation beyond the last anchor. Convexity-faithful for small
    prompts (the global linear fit over-predicts <1k by ~25%)."""
    a = E1_ANCHORS
    if tokens <= a[0][0]:
        return a[0][1] * tokens / a[0][0]
    for (x0, y0), (x1, y1) in zip(a, a[1:]):
        if tokens <= x1:
            return y0 + (y1 - y0) * (tokens - x0) / (x1 - x0)
    x_last, y_last = a[-1]
    return y_last + (tokens - x_last) * MARGINAL_S_PER_TOK


def turn_time(prompt_tokens: float, reply_tokens: float = 60.0) -> float:
    return ttft_projected(prompt_tokens) + reply_tokens / DECODE_TOK_S_SMALL_KV


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "project":
        for n in argv[2:]:
            n = float(n)
            print(f"{int(n):>6} tok  TTFT ~{ttft_projected(n):7.1f}s  "
                  f"turn(+60 tok reply) ~{turn_time(n)/60:5.1f} min")
        return 0
    request = json.load(open(argv[2]))
    if cmd == "render":
        sys.stdout.write(engine_prompt(request))
        return 0
    if cmd == "count":
        c = Counter()
        b = breakdown(request, c)
        per_tool = b.pop("per_tool")
        print(json.dumps(b, indent=2))
        if per_tool:
            print("\nper-tool tokens (marginal, incl. its slice of the JSON array):")
            for d in per_tool:
                print(f"  {d['tokens']:>6}  {d['name']}")
        t = b["total_prompt_tokens"]
        print(f"\nprojected TTFT: {ttft_projected(t):.1f}s "
              f"({ttft_projected(t)/60:.1f} min); "
              f"turn with 60-tok reply: {turn_time(t)/60:.1f} min")
        return 0
    print(f"unknown command {cmd!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
