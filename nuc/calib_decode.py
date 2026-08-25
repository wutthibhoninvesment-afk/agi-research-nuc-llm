#!/usr/bin/env python3
"""calib_decode.py — settle the streaming-vs-differencing decode discrepancy.

At 1k the two methods disagreed (stream 4.78 vs differencing 3.69 tok/s).
Both artifacts are window-size effects, so measure a LONG decode window
(max_tokens=256, ~70 s) behind a SHORT prefill (~130 tok, ~20 s, jitter
≤ ±0.5 s) and compare:
  differencing = (C-1) / (wall_256 - ttft_1tok)     across two requests
  streaming    = (C-1) / (last_chunk - first_chunk) inside one request
Per-chunk (elapsed_s, n_chars) pairs are recorded to expose flush batching.
"""
import json
import time
import urllib.request

from bench import chat_once, check_base_url, make_prompt

BASE = check_base_url("http://127.0.0.1:8000")
MODEL = "qwen36"
OUT = "/work/logs/nuc-bench-calib.json"


def stream_with_chunks(prompt: str, max_tokens: int) -> dict:
    body = {"model": MODEL, "max_tokens": max_tokens, "temperature": 0,
            "stream": True, "stream_options": {"include_usage": True},
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(f"{BASE}/v1/chat/completions",
                                 data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    chunks = []          # (elapsed_s, chars_in_delta)
    usage = {}
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=3600) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                obj = json.loads(payload)
            except ValueError:
                continue
            now = time.perf_counter() - t0
            if obj.get("usage"):
                usage = obj["usage"]
            for ch in obj.get("choices") or []:
                delta = (ch.get("delta") or {}).get("content")
                if delta:
                    chunks.append((round(now, 3), len(delta)))
    wall = time.perf_counter() - t0
    c = int(usage.get("completion_tokens", 0))
    rec = {"wall_s": wall, "completion_tokens": c,
           "prompt_tokens": int(usage.get("prompt_tokens", 0)),
           "n_chunks": len(chunks), "chunks": chunks}
    if len(chunks) >= 2 and c > 1:
        first, last = chunks[0][0], chunks[-1][0]
        rec["stream_decode_tok_s"] = (c - 1) / (last - first)
        # rate excluding the first chunk (kills any first-flush batching bias):
        # tokens in chunks[1:] approximated by char share
        chars_total = sum(n for _, n in chunks)
        chars_tail = sum(n for _, n in chunks[1:])
        tok_tail = (c * chars_tail / chars_total) if chars_total else 0
        if last > chunks[1][0] and tok_tail > 1:
            rec["stream_decode_tok_s_tail"] = (tok_tail - 1) / (last - chunks[1][0])
    return rec


def main() -> None:
    prompt = make_prompt(600, 777)
    out = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "prompt_chars": len(prompt)}

    r1 = chat_once(BASE, MODEL, prompt, 1)
    out["ttft_1tok_s"] = r1.service_s
    out["prompt_tokens"] = r1.prompt_tokens
    print(f"[calib] baseline: {r1.prompt_tokens} tok, TTFT {r1.service_s:.2f}s", flush=True)

    r2 = chat_once(BASE, MODEL, prompt, 256)
    out["wall_256_s"] = r2.service_s
    out["completion_tokens_256"] = r2.completion_tokens
    if r2.completion_tokens > 1 and r2.service_s > r1.service_s:
        out["diff_decode_tok_s"] = (r2.completion_tokens - 1) / (r2.service_s - r1.service_s)
    print(f"[calib] differencing: {r2.completion_tokens} tok in {r2.service_s:.2f}s "
          f"-> {out.get('diff_decode_tok_s')} tok/s", flush=True)

    out["stream"] = stream_with_chunks(prompt, 256)
    print(f"[calib] streaming: {out['stream'].get('stream_decode_tok_s')} tok/s "
          f"(tail {out['stream'].get('stream_decode_tok_s_tail')}), "
          f"{out['stream']['n_chunks']} chunks", flush=True)

    out["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "stream"}, indent=1), flush=True)


if __name__ == "__main__":
    main()
