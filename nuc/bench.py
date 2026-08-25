#!/usr/bin/env python3
"""bench.py — TTFT / prefill / decode benchmark for an OpenAI-compatible engine.

Stdlib only (runs on the NUC's bare Python 3.12). Non-streaming by default,
as the E1 mission asks; ``--stream`` cross-checks TTFT via first-chunk timing.

Method per prompt size N (non-streaming):
  1. cold   : fresh-prefix prompt, max_tokens=1  -> TTFT_cold (≈ prefill + overhead)
  2. warm   : identical prompt, max_tokens=1     -> TTFT_warm (prefix-reuse probe)
  3. decode : identical prompt, max_tokens=D     -> decode tok/s = (C-1)/(t3 - TTFT_warm)
     where C = completion_tokens reported by the server.
Prompt sizes are hit without a tokenizer: the server's ``usage.prompt_tokens``
is exact, and a running linear fit tokens = a + b*chars re-sizes each prompt.

Safety: refuses any base URL on port 8001 (GLM frontier lane — never touch).
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Callable, Optional
from urllib.parse import urlparse

FORBIDDEN_PORTS = {8001}
DEFAULT_SIZES = (100, 1000, 4000, 8000)
DEFAULT_DECODE_TOKENS = 64
DEFAULT_CUTOFF_S = 300.0     # mission rule: if 4k prefill > 5 min, extrapolate 8k
WORDS = ("the quick brown fox jumps over lazy dog while seven quiet rivers carry "
         "small boats toward distant harbours under grey morning light and every "
         "sailor counts coins before trading salt for bread near old stone walls "
         "where merchants argue about copper prices then children chase kites "
         "across wide fields as farmers mend fences beside sleepy cattle").split()


class BenchError(RuntimeError):
    pass


def check_base_url(base_url: str) -> str:
    """Reject forbidden ports; return the URL without a trailing slash."""
    parsed = urlparse(base_url)
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    if port in FORBIDDEN_PORTS:
        raise BenchError(f"refusing to touch port {port} (frontier lane rule)")
    return base_url.rstrip("/")


# ---------------------------------------------------------------- prompts

def word_salad(n_chars: int, seed: int) -> str:
    """Deterministic pseudo-random prose of about n_chars characters.

    Every seed yields a distinct first sentence, so prompts of different sizes
    never share a prefix (a prefix cache could otherwise leak between sizes).
    """
    rng = random.Random(seed)
    out = [f"Note {seed}-{rng.randrange(10**6)}:"]
    length = len(out[0])
    while length < n_chars:
        w = rng.choice(WORDS)
        if rng.random() < 0.08:
            w += "."
        out.append(w)
        length += len(w) + 1
    return " ".join(out)


def make_prompt(n_chars: int, seed: int) -> str:
    body = word_salad(n_chars, seed)
    return ("Read the following notes. Reply with the single word OK, then, without "
            "stopping, write a very long detailed story about the notes.\n\n"
            + body + "\n\nBegin your reply with OK and keep writing.")


@dataclass
class TokenFit:
    """tokens ≈ intercept + slope * chars, refitted from observed (chars, tokens)."""
    slope: float = 1 / 4.5
    intercept: float = 15.0
    points: list = field(default_factory=list)

    def observe(self, chars: int, tokens: int) -> None:
        self.points.append((chars, tokens))
        if len(self.points) >= 2:
            xs = [p[0] for p in self.points]
            ys = [p[1] for p in self.points]
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            sxx = sum((x - mx) ** 2 for x in xs)
            if sxx > 0:
                self.slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
                self.intercept = my - self.slope * mx
        else:
            # one point: keep the default intercept, solve the slope
            self.slope = max((tokens - self.intercept), 1) / max(chars, 1)

    def chars_for(self, tokens: int) -> int:
        return max(int((tokens - self.intercept) / self.slope), 8)


# ---------------------------------------------------------------- transport

@dataclass
class Reply:
    wall_s: float
    queue_wait_s: float
    prompt_tokens: int
    completion_tokens: int
    text: str
    request_id: str = ""
    first_chunk_s: Optional[float] = None   # streaming only
    last_chunk_s: Optional[float] = None

    @property
    def service_s(self) -> float:
        return self.wall_s - self.queue_wait_s


def _post(url: str, body: dict, timeout: float, stream: bool = False):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def chat_once(base_url: str, model: str, prompt: str, max_tokens: int,
              timeout: float = 3600.0, stream: bool = False,
              opener: Optional[Callable] = None) -> Reply:
    """One /v1/chat/completions request, timed on the client side."""
    body = {"model": model, "max_tokens": max_tokens, "temperature": 0,
            "stream": stream,
            "messages": [{"role": "user", "content": prompt}]}
    if stream:
        body["stream_options"] = {"include_usage": True}
    opener = opener or _post
    t0 = time.perf_counter()
    try:
        resp = opener(f"{base_url}/v1/chat/completions", body, timeout, stream)
    except urllib.error.HTTPError as e:
        raise BenchError(f"HTTP {e.code}: {e.read()[:300]!r}") from None
    with resp:
        headers = {k.lower(): v for k, v in resp.headers.items()}
        queue_ms = float(headers.get("x-colibri-queue-wait-ms", 0) or 0)
        rid = headers.get("x-request-id", "")
        if not stream:
            payload = json.loads(resp.read().decode())
            wall = time.perf_counter() - t0
            usage = payload.get("usage") or {}
            text = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            return Reply(wall, queue_ms / 1000, int(usage.get("prompt_tokens", 0)),
                         int(usage.get("completion_tokens", 0)), text, rid)
        first = last = None
        usage: dict = {}
        text_parts = []
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                obj = json.loads(chunk)
            except ValueError:
                continue
            now = time.perf_counter() - t0
            if obj.get("usage"):
                usage = obj["usage"]
            for ch in obj.get("choices") or []:
                delta = (ch.get("delta") or {}).get("content")
                if delta:
                    text_parts.append(delta)
                    if first is None:
                        first = now
                    last = now
        wall = time.perf_counter() - t0
        return Reply(wall, queue_ms / 1000, int(usage.get("prompt_tokens", 0)),
                     int(usage.get("completion_tokens", 0)), "".join(text_parts),
                     rid, first, last)


# ---------------------------------------------------------------- measurement

@dataclass
class SizeResult:
    target_tokens: int
    prompt_tokens: int
    prompt_chars: int
    ttft_cold_s: float
    ttft_warm_s: Optional[float]
    decode_tokens: int
    decode_run_s: Optional[float]
    decode_tok_s: Optional[float]
    prefill_tok_s: float             # prompt_tokens / ttft_cold (includes overhead)
    warm_over_cold: Optional[float]
    extrapolated: bool = False
    ttft_fresh_s: Optional[float] = None     # different-seed prompt of the same size
    repeat_over_fresh: Optional[float] = None  # the prefix-reuse signal (drift-immune)
    stream_ttft_s: Optional[float] = None
    stream_decode_tok_s: Optional[float] = None
    reply_text: str = ""
    note: str = ""


def measure_size(base_url: str, model: str, target: int, fit: TokenFit,
                 seed: int, decode_tokens: int, warm: bool = True,
                 stream_check: bool = False, log=print,
                 opener: Optional[Callable] = None) -> SizeResult:
    chars = fit.chars_for(target)
    prompt = make_prompt(chars, seed)
    log(f"[{target}] prompt {len(prompt)} chars (fit slope={fit.slope:.4f} b={fit.intercept:.1f})")
    cold = chat_once(base_url, model, prompt, 1, opener=opener)
    fit.observe(len(prompt), cold.prompt_tokens)
    log(f"[{target}] cold: {cold.prompt_tokens} tok, TTFT {cold.service_s:.2f}s "
        f"(queue {cold.queue_wait_s:.2f}s) -> {cold.prompt_tokens / cold.service_s:.2f} tok/s")
    ttft_warm = ttft_fresh = None
    if warm:
        w = chat_once(base_url, model, prompt, 1, opener=opener)
        ttft_warm = w.service_s
        log(f"[{target}] warm: TTFT {ttft_warm:.2f}s  warm/cold={ttft_warm / cold.service_s:.2f}")
        fresh_prompt = make_prompt(chars, seed + 500_000)   # same size, different prefix
        fr = chat_once(base_url, model, fresh_prompt, 1, opener=opener)
        ttft_fresh = fr.service_s
        log(f"[{target}] fresh: {fr.prompt_tokens} tok, TTFT {ttft_fresh:.2f}s  "
            f"repeat/fresh={ttft_warm / ttft_fresh:.2f}")
    d = chat_once(base_url, model, prompt, decode_tokens, opener=opener)
    base = ttft_warm if ttft_warm is not None else cold.service_s
    dec = None
    if d.completion_tokens > 1 and d.service_s > base:
        dec = (d.completion_tokens - 1) / (d.service_s - base)
    log(f"[{target}] decode run: {d.completion_tokens} tok in {d.service_s:.2f}s -> "
        f"{dec if dec is None else round(dec, 2)} tok/s; reply={d.text[:40]!r}")
    res = SizeResult(target, cold.prompt_tokens, len(prompt), cold.service_s, ttft_warm,
                     d.completion_tokens, d.service_s, dec,
                     cold.prompt_tokens / cold.service_s,
                     None if ttft_warm is None else ttft_warm / cold.service_s,
                     reply_text=d.text[:80])
    if ttft_fresh is not None:
        res.ttft_fresh_s = ttft_fresh
        res.repeat_over_fresh = ttft_warm / ttft_fresh
    if stream_check:
        s = chat_once(base_url, model, prompt, decode_tokens, stream=True, opener=opener)
        res.stream_ttft_s = s.first_chunk_s
        if s.first_chunk_s is not None and s.last_chunk_s and s.completion_tokens > 1 \
                and s.last_chunk_s > s.first_chunk_s:
            res.stream_decode_tok_s = (s.completion_tokens - 1) / (s.last_chunk_s - s.first_chunk_s)
        log(f"[{target}] stream: TTFT {s.first_chunk_s} s, decode {res.stream_decode_tok_s} tok/s")
    return res


def linear_fit(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Least-squares y = a + b x. With one point: a = 0 (pure proportionality)."""
    if not points:
        raise BenchError("no points to fit")
    if len(points) == 1:
        x, y = points[0]
        return 0.0, y / x
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - b * mx, b


def extrapolate(results: list[SizeResult], target: int) -> SizeResult:
    a, b = linear_fit([(r.prompt_tokens, r.ttft_cold_s) for r in results if not r.extrapolated])
    ttft = a + b * target
    decs = [r.decode_tok_s for r in results if r.decode_tok_s]
    return SizeResult(target, target, 0, ttft, None, 0, None,
                      decs[-1] if decs else None, target / ttft, None, extrapolated=True,
                      note=f"linear fit TTFT = {a:.1f} + {b:.4f}*tokens over measured sizes")


def engine_warmup(base_url: str, model: str, seed: int, opener=None, log=print) -> float:
    """One discarded small request so 'cold' means cold-prefix, not cold-engine.

    An idle engine pays expert-cache / page-cache warm-up on its first request
    (measured 63 s vs 16 s for 114 tokens on pgain-nuc); report it separately.
    """
    r = chat_once(base_url, model, make_prompt(200, seed + 900_000), 1, opener=opener)
    log(f"[warmup] {r.prompt_tokens} tok, {r.service_s:.2f}s (discarded; engine cold start)")
    return r.service_s


def run_bench(base_url: str, model: str, sizes=DEFAULT_SIZES, decode_tokens=DEFAULT_DECODE_TOKENS,
              cutoff_s=DEFAULT_CUTOFF_S, seed=1, warm_sizes=None, stream_check=False,
              log=print, opener: Optional[Callable] = None, warmup=True,
              meta: Optional[dict] = None) -> list[SizeResult]:
    base_url = check_base_url(base_url)
    if warmup:
        t = engine_warmup(base_url, model, seed, opener, log)
        if meta is not None:
            meta["engine_cold_start_s"] = round(t, 2)
    fit = TokenFit()
    results: list[SizeResult] = []
    for i, size in enumerate(sizes):
        if results and results[-1].ttft_cold_s > cutoff_s:
            log(f"[{size}] SKIPPED: previous TTFT {results[-1].ttft_cold_s:.0f}s > cutoff {cutoff_s:.0f}s; extrapolating")
            results.append(extrapolate(results, size))
            continue
        do_warm = True if warm_sizes is None else size in warm_sizes
        results.append(measure_size(base_url, model, size, fit, seed * 1000 + i,
                                    decode_tokens, warm=do_warm,
                                    stream_check=stream_check, log=log, opener=opener))
    return results


# ---------------------------------------------------------------- reporting

def render_markdown(results: list[SizeResult], meta: dict) -> str:
    lines = ["# NUC bench — TTFT / prefill / decode", "",
             *(f"- {k}: {v}" for k, v in meta.items()), "",
             "| target | prompt tok | TTFT cold (s) | prefill tok/s | TTFT repeat (s) | TTFT fresh (s) | repeat/fresh | decode tok/s | decode run (s) | note |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        f = lambda v, d=2: "—" if v is None else f"{v:.{d}f}"
        note = ("EXTRAPOLATED: " + r.note) if r.extrapolated else r.note
        lines.append(f"| {r.target_tokens} | {r.prompt_tokens} | {f(r.ttft_cold_s, 1)} | "
                     f"{f(r.prefill_tok_s)} | {f(r.ttft_warm_s, 1)} | {f(r.ttft_fresh_s, 1)} | "
                     f"{f(r.repeat_over_fresh)} | {f(r.decode_tok_s)} | {f(r.decode_run_s, 1)} | {note} |")
    stream_rows = [r for r in results if r.stream_ttft_s is not None]
    if stream_rows:
        lines += ["", "Streaming cross-check:", "",
                  "| target | stream TTFT (s) | stream decode tok/s |", "|---|---|---|"]
        for r in stream_rows:
            lines.append(f"| {r.target_tokens} | {r.stream_ttft_s:.2f} | "
                         f"{'—' if r.stream_decode_tok_s is None else round(r.stream_decode_tok_s, 2)} |")
    measured = [r for r in results if not r.extrapolated]
    if len(measured) >= 2:
        a, b = linear_fit([(r.prompt_tokens, r.ttft_cold_s) for r in measured])
        lines += ["", f"Prefill model: TTFT ≈ {a:.2f} s + {b * 1000:.1f} s per 1k tokens "
                      f"(marginal prefill rate {1 / b:.2f} tok/s, fixed overhead {a:.2f} s)."]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--model", default="qwen36")
    ap.add_argument("--sizes", default=",".join(map(str, DEFAULT_SIZES)))
    ap.add_argument("--decode-tokens", type=int, default=DEFAULT_DECODE_TOKENS)
    ap.add_argument("--cutoff", type=float, default=DEFAULT_CUTOFF_S,
                    help="skip+extrapolate the next size when the previous cold TTFT exceeds this")
    ap.add_argument("--warm-sizes", default=None, help="comma list; default = all sizes")
    ap.add_argument("--stream-check", action="store_true")
    ap.add_argument("--no-warmup", action="store_true", help="skip the discarded engine warm-up request")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--md-out", default=None)
    args = ap.parse_args(argv)
    sizes = [int(s) for s in args.sizes.split(",") if s]
    warm = None if args.warm_sizes is None else {int(s) for s in args.warm_sizes.split(",") if s}
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    meta = {"base_url": args.base_url, "model": args.model, "started": started,
            "decode_tokens": args.decode_tokens, "cutoff_s": args.cutoff, "seed": args.seed,
            "mode": "non-streaming (+stream check)" if args.stream_check else "non-streaming"}
    try:
        results = run_bench(args.base_url, args.model, sizes, args.decode_tokens, args.cutoff,
                            args.seed, warm, args.stream_check, warmup=not args.no_warmup, meta=meta)
    except BenchError as e:
        print(f"bench error: {e}", file=sys.stderr)
        return 2
    meta["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    md = render_markdown(results, meta)
    print(md)
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump({"meta": meta, "results": [asdict(r) for r in results]}, f, indent=1)
    if args.md_out:
        with open(args.md_out, "w") as f:
            f.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
