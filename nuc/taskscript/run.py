#!/usr/bin/env python3
"""run.py SCRIPT.errand FLOW [k=v ...] [--transport dry|mock:FILE|http] [--trace FILE]
       [--chars-per-token N] [--tokenizer chars|qwen] [--seed N] [--events]

Exit codes: 0 every emitted value ok · 1 a miss was emitted or ended the flow ·
2 lex/parse/link error · 3 usage/transport error. `--transport dry` (the
default) prices the flow without any request; `http` is live against the lane
URLs (never port 8001 — the parser refuses such a lane).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from taskscript.interp import CallableTokenizer, CharsTokenizer, Interp, Miss, render, why  # noqa: E402
from taskscript.parser import ParseError, parse  # noqa: E402
from taskscript.transport import DryTransport, HTTPTransport, MockTransport, TransportError  # noqa: E402


def build_transport(spec: str):
    if spec == "dry":
        return DryTransport(), True
    if spec == "http":
        return HTTPTransport(), False
    if spec.startswith("mock:"):
        return MockTransport.from_file(spec[5:]), False
    raise TransportError(f"unknown transport {spec!r} (dry | mock:FILE | http)", retryable=False)


def build_tokenizer(kind: str, cpt: float):
    if kind == "chars":
        return CharsTokenizer(cpt)
    if kind == "qwen":
        import prompt_budget  # E2's real tokenizer (needs `tokenizers` in the venv)
        counter = prompt_budget.Counter()
        t = CallableTokenizer(counter.n_engine)
        t.name = "qwen"
        return t
    raise TransportError(f"unknown tokenizer {kind!r}", retryable=False)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script")
    ap.add_argument("flow")
    ap.add_argument("args", nargs="*", help="k=v flow arguments")
    ap.add_argument("--transport", default="dry")
    ap.add_argument("--trace", default=None, help="append JSONL telemetry here")
    ap.add_argument("--chars-per-token", type=float, default=4.0)
    ap.add_argument("--tokenizer", default="chars", choices=["chars", "qwen"])
    ap.add_argument("--seed", type=int, default=None, help="rng seed for retry jitter")
    ap.add_argument("--events", action="store_true", help="print telemetry events to stderr")
    a = ap.parse_args(argv)

    try:
        with open(a.script, encoding="utf-8") as fh:
            src = fh.read()
    except OSError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 3
    try:
        prog = parse(src)
    except ParseError as ex:
        print(f"{a.script}: {ex}", file=sys.stderr)
        return 2
    args: dict = {}
    for kv in a.args:
        if "=" not in kv:
            print(f"error: flow argument {kv!r} is not k=v", file=sys.stderr)
            return 3
        k, v = kv.split("=", 1)
        args[k] = v
    try:
        transport, dry = build_transport(a.transport)
        tok = build_tokenizer(a.tokenizer, a.chars_per_token)
    except (TransportError, ImportError, OSError) as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 3

    sink = None
    if a.trace:
        sink = open(a.trace, "a", encoding="utf-8")

    def trace(ev: dict) -> None:
        line = json.dumps(ev, sort_keys=True)
        if sink is not None:
            sink.write(line + "\n")
        if a.events:
            print(line, file=sys.stderr)

    rng = random.Random(a.seed).random if a.seed is not None else random.random
    it = Interp(prog, transport, tok, trace=trace, dry_run=dry, rng=rng)
    try:
        res = it.run_flow(a.flow, args)
    except KeyError as ex:
        print(f"error: {ex.args[0]}", file=sys.stderr)
        return 3
    finally:
        if sink is not None:
            sink.close()
    for v in res.emitted:
        print(render(v))
    if res.miss is not None:
        print("flow ended in a miss:", file=sys.stderr)
        print(json.dumps(why(res.miss), indent=1, sort_keys=True), file=sys.stderr)
    led = res.ledger
    lanes = ", ".join(f"{k}: {v['calls']} call(s) {v['seconds']:.1f} s" for k, v in led["per_lane"].items()) or "no calls"
    mode = "projected" if dry else "measured"
    print(f"flow {a.flow}: {'ok' if res.ok else 'MISS'} · {led['calls']} task call(s) · {led['spent_s']:.1f} s {mode}"
          + (f" of {led['limit_s']:.0f} s budget {led['budget']}" if led['limit_s'] else "")
          + f" · {lanes}", file=sys.stderr)
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
