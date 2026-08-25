#!/usr/bin/env python3
"""decode_fix.py — round-16 follow-up: proper decode measurement at 1k and 4k.

The round-10 run computed decode@4k = (64-1)/(775.6-770.3) = 11.84 tok/s by
differencing a decode run against the COLD TTFT of a separate ~770 s request;
~1.7 % prefill drift between the two requests swamps the decode signal.

Fix: ONE streaming request per size with the byte-identical round-10 prompt;
decode = (completion_tokens - 1) / (last_chunk - first_chunk) — intra-request
timing, immune to inter-request prefill drift. The 1k size runs first as a
method check against the trusted differencing figure (3.69 tok/s).
"""
import json
import time

from bench import TokenFit, chat_once, check_base_url, make_prompt

BASE = check_base_url("http://127.0.0.1:8000")
MODEL = "qwen36"
OUT = "/work/logs/nuc-bench-decodefix.json"


def rebuild_prompt(target: int, seed: int, expect_chars: int) -> str:
    # Reproduce the round-10 TokenFit state at the moment each prompt was built.
    fit = TokenFit()
    fit.observe(562, 134)            # 100-size cold observation
    if target >= 4000:
        fit.observe(4828, 904)       # 1000-size cold observation
    prompt = make_prompt(fit.chars_for(target), seed)
    assert len(prompt) == expect_chars, (target, len(prompt), expect_chars)
    return prompt


def measure(target: int, seed: int, expect_chars: int, max_tokens: int) -> dict:
    prompt = rebuild_prompt(target, seed, expect_chars)
    print(f"[{target}] streaming request, {len(prompt)} chars, max_tokens={max_tokens}",
          flush=True)
    r = chat_once(BASE, MODEL, prompt, max_tokens, stream=True)
    rec = {
        "target": target,
        "prompt_tokens": r.prompt_tokens,
        "completion_tokens": r.completion_tokens,
        "stream_ttft_s": r.first_chunk_s,
        "last_chunk_s": r.last_chunk_s,
        "wall_s": r.wall_s,
        "queue_wait_s": r.queue_wait_s,
        "reply_head": r.text[:60],
    }
    if (r.first_chunk_s is not None and r.last_chunk_s
            and r.completion_tokens > 1 and r.last_chunk_s > r.first_chunk_s):
        rec["decode_tok_s"] = (r.completion_tokens - 1) / (r.last_chunk_s - r.first_chunk_s)
    else:
        rec["decode_tok_s"] = None
    print(f"[{target}] TTFT {rec['stream_ttft_s']} s, "
          f"{r.completion_tokens} tok, decode {rec['decode_tok_s']} tok/s", flush=True)
    return rec


def main() -> None:
    out = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "runs": []}
    out["runs"].append(measure(1000, 1001, 4828, 128))   # method validation
    out["runs"].append(measure(4000, 1002, 22157, 128))  # the fix
    out["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1), flush=True)


if __name__ == "__main__":
    main()
