#!/usr/bin/env python3
"""lane_bench.py — micro-benchmark a colibri `olmoe` engine binary through its
ref.json harness mode (mission E4: OLMoE fast lane beside Qwen3.6).

The harness mode (`./olmoe <cap> <bits> <ref.json>`) prefills `prompt_ids`,
greedily generates `len(full_ids) - len(prompt_ids)` tokens, compares them
with `full_ids` and prints, on stdout:

    resident weights loaded in 0.7s | RSS after load: 1.98 GB
    Matching tokens: 12/12
    PEAK RSS: 3.49 GB
    Expert cache hit rate: 41.2%  (hit=1234 miss=1760)
    Speed: 4.60 tok/s (43.5s for 200 tokens)
    TUNE decode: 200 tokens in 43.478s

so a ref file whose `full_ids` continue the prompt with N *dummy* ids is an
N-token timed greedy decode with cache statistics — the comparison merely
reports 0 matches. With N = 1 the elapsed time is (almost) pure prefill of
`len(prompt_ids)` tokens.

This module builds such refs, runs cases (cap / env-var combinations) under
`resource.getrusage(RUSAGE_CHILDREN)` so user/sys CPU time is captured per
case (sys share = page-fault / read-bound share on a RAM-tight box), parses
the output, and renders a markdown table. Stdlib only; the engine is the only
dependency and is passed as a path.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import resource
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Optional, Sequence

# Token ids from colibri's shipped ref_olmoe_real.json ("The capital of France is"
# in the OLMoE/GPT-NeoX tokenizer) — valid ids for any OLMoE container.
DEFAULT_PROMPT_IDS = (510, 5347, 273, 6181, 310)


class LaneBenchError(RuntimeError):
    pass


# ------------------------------------------------------------------ ref files

def make_ref(prompt_ids: Sequence[int], n_new: int, filler_id: int = 0) -> dict:
    """A ref.json whose continuation is `n_new` dummy ids (greedy decode of
    `n_new` tokens; 'Matching tokens' will read ~0/n_new, which is expected)."""
    if not prompt_ids:
        raise LaneBenchError("prompt_ids must not be empty")
    if n_new < 1:
        raise LaneBenchError("n_new must be >= 1")
    ids = [int(i) for i in prompt_ids]
    return {"prompt_ids": ids, "full_ids": ids + [int(filler_id)] * n_new}


def prompt_of_length(n: int, base: Sequence[int] = DEFAULT_PROMPT_IDS) -> list[int]:
    """Cycle a known-valid id sequence up to `n` tokens (prefill sizing)."""
    if n < 1:
        raise LaneBenchError("n must be >= 1")
    base = list(base)
    return [base[i % len(base)] for i in range(n)]


def write_ref(path: str, ref: dict) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(ref, fh)
    return path


# ------------------------------------------------------------------ parsing

_RE = {
    "load_s": re.compile(r"resident weights loaded in ([0-9.]+)s"),
    "rss_after_load_gb": re.compile(r"RSS after load: ([0-9.]+) GB"),
    "peak_rss_gb": re.compile(r"PEAK RSS: ([0-9.]+) GB"),
    "hit_rate_pct": re.compile(r"Expert cache hit rate: ([0-9.]+)%"),
    "hits": re.compile(r"hit=(\d+)"),
    "misses": re.compile(r"miss=(\d+)"),
    "matching": re.compile(r"Matching tokens: (\d+)/(\d+)"),
    "tune": re.compile(r"TUNE decode: (\d+) tokens in ([0-9.]+)s"),
    "speed": re.compile(r"Speed: ([0-9.]+) tok/s \(([0-9.]+)s for (\d+) tokens\)"),
}


@dataclass
class EngineStats:
    tokens: int
    seconds: float
    tok_s: float
    load_s: Optional[float] = None
    rss_after_load_gb: Optional[float] = None
    peak_rss_gb: Optional[float] = None
    hit_rate_pct: Optional[float] = None
    hits: Optional[int] = None
    misses: Optional[int] = None
    matching: Optional[int] = None


def parse_engine_output(text: str) -> EngineStats:
    """Read the harness summary. The TUNE line (full precision) wins over the
    two-decimal Speed line; tok/s is recomputed from tokens/seconds."""
    m = _RE["tune"].search(text)
    if m:
        tokens, seconds = int(m.group(1)), float(m.group(2))
    else:
        m = _RE["speed"].search(text)
        if not m:
            raise LaneBenchError("no 'TUNE decode' or 'Speed:' line in engine output")
        seconds, tokens = float(m.group(2)), int(m.group(3))
    if seconds <= 0:
        raise LaneBenchError("non-positive elapsed time in engine output")
    st = EngineStats(tokens=tokens, seconds=seconds, tok_s=tokens / seconds)
    for key in ("load_s", "rss_after_load_gb", "peak_rss_gb", "hit_rate_pct"):
        mm = _RE[key].search(text)
        if mm:
            setattr(st, key, float(mm.group(1)))
    for key in ("hits", "misses"):
        mm = _RE[key].search(text)
        if mm:
            setattr(st, key, int(mm.group(1)))
    mm = _RE["matching"].search(text)
    if mm:
        st.matching = int(mm.group(1))
    return st


# ------------------------------------------------------------------ cases

@dataclass
class Case:
    name: str
    cap: int
    bits: int = 8
    env: dict = field(default_factory=dict)

    @classmethod
    def parse(cls, spec: str) -> "Case":
        """'cap=16' | 'cap=64,EXPERT_DROP=1,OMP_NUM_THREADS=4' | 'name:cap=16,...'"""
        name = spec
        if ":" in spec:
            name, spec = spec.split(":", 1)
        cap: Optional[int] = None
        bits = 8
        env: dict = {}
        for part in filter(None, (p.strip() for p in spec.split(","))):
            if "=" not in part:
                raise LaneBenchError(f"bad case token {part!r} (want key=value)")
            k, v = part.split("=", 1)
            if k == "cap":
                cap = int(v)
            elif k == "bits":
                bits = int(v)
            else:
                env[k] = v
        if cap is None:
            raise LaneBenchError(f"case {spec!r} has no cap=")
        return cls(name=name, cap=cap, bits=bits, env=env)


@dataclass
class CaseResult:
    name: str
    cap: int
    bits: int
    env: dict
    n_prompt: int
    n_new: int
    wall_s: float
    user_s: float
    sys_s: float
    stats: dict
    returncode: int
    stderr_tail: str = ""

    @property
    def sys_share(self) -> float:
        cpu = self.user_s + self.sys_s
        return self.sys_s / cpu if cpu > 0 else 0.0


def _rusage_children():
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime, r.ru_stime


def run_case(engine: str, snap: str, case: Case, ref_path: str, n_prompt: int, n_new: int,
             timeout_s: float = 900.0, cwd: Optional[str] = None) -> CaseResult:
    """Run one harness invocation; user/sys are RUSAGE_CHILDREN deltas so they
    belong to this child alone (call cases sequentially)."""
    env = dict(os.environ)
    env["SNAP"] = snap
    env.pop("CHAT", None)
    env.pop("SERVE", None)
    env.update({k: str(v) for k, v in case.env.items()})
    u0, s0 = _rusage_children()
    t0 = time.monotonic()
    p = subprocess.run([engine, str(case.cap), str(case.bits), ref_path], env=env,
                       capture_output=True, text=True, timeout=timeout_s, cwd=cwd)
    wall = time.monotonic() - t0
    u1, s1 = _rusage_children()
    if p.returncode != 0:
        raise LaneBenchError(f"engine exited {p.returncode}: {p.stderr[-800:]}")
    stats = parse_engine_output(p.stdout)
    return CaseResult(name=case.name, cap=case.cap, bits=case.bits, env=dict(case.env),
                      n_prompt=n_prompt, n_new=n_new, wall_s=round(wall, 3),
                      user_s=round(u1 - u0, 3), sys_s=round(s1 - s0, 3),
                      stats=asdict(stats), returncode=p.returncode,
                      stderr_tail=p.stderr[-400:])


def prefill_tok_s(res: CaseResult) -> Optional[float]:
    """For an n_new == 1 case the harness time is prefill(n_prompt) + one decode
    step; report prompt tokens per harness second (a lower bound)."""
    if res.n_new != 1:
        return None
    return res.n_prompt / res.stats["seconds"]


# ------------------------------------------------------------------ report

def markdown_table(results: Sequence[CaseResult]) -> str:
    rows = ["| case | cap | env | prompt | new | tok/s | harness s | hit % | peak RSS GB | load s | user s | sys s | sys share |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        st = r.stats
        env = ",".join(f"{k}={v}" for k, v in r.env.items()) or "—"
        hit = f"{st['hit_rate_pct']:.1f}" if st.get("hit_rate_pct") is not None else "—"
        peak = f"{st['peak_rss_gb']:.2f}" if st.get("peak_rss_gb") is not None else "—"
        load = f"{st['load_s']:.1f}" if st.get("load_s") is not None else "—"
        tps = prefill_tok_s(r)
        rate = f"{tps:.1f} (prefill)" if tps is not None else f"{st['tok_s']:.2f}"
        rows.append(f"| {r.name} | {r.cap} | {env} | {r.n_prompt} | {r.n_new} | {rate} | "
                    f"{st['seconds']:.1f} | {hit} | {peak} | {load} | {r.user_s:.1f} | "
                    f"{r.sys_s:.1f} | {r.sys_share * 100:.0f} % |")
    return "\n".join(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", required=True, help="path to the olmoe binary")
    ap.add_argument("--snap", required=True, help="converted container directory")
    ap.add_argument("--case", action="append", required=True,
                    help="'cap=16' or 'name:cap=64,EXPERT_DROP=1' (repeatable, run in order)")
    ap.add_argument("--n-new", type=int, default=200)
    ap.add_argument("--prompt-tokens", type=int, default=len(DEFAULT_PROMPT_IDS))
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--ref", default="/tmp/lane_bench_ref.json")
    ap.add_argument("--json", default=None, help="append one JSON line per case result")
    ap.add_argument("--timeout", type=float, default=900.0)
    a = ap.parse_args(argv)

    prompt = prompt_of_length(a.prompt_tokens)
    write_ref(a.ref, make_ref(prompt, a.n_new))
    cases = [Case.parse(s) for s in a.case]
    results: list[CaseResult] = []
    for rep in range(a.repeats):
        for c in cases:
            r = run_case(a.engine, a.snap, c, a.ref, len(prompt), a.n_new, timeout_s=a.timeout)
            if a.repeats > 1:
                r.name = f"{r.name}#{rep + 1}"
            results.append(r)
            print(json.dumps(asdict(r)), file=sys.stderr, flush=True)
            if a.json:
                with open(a.json, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(asdict(r)) + "\n")
    print(markdown_table(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
