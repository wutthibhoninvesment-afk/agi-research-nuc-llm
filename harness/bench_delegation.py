#!/usr/bin/env python3
"""Delegation economics: when is a fresh-context sub-agent cheaper than doing
the sub-task inline?

Two instruments, cross-checked:

  1. ANALYTIC — price a sequence of requests under prefix-cache accounting
     (each request reads its predecessor's rendering at 0.1x and writes the
     delta at 1.25x; outputs at the output price). Inline vs delegated
     differ in three places:
       (a) prefix avoidance: every inline sub-task step re-READS the parent
           prefix P; the child reads its own overhead O instead
           -> saves 0.1 * S * (P - O) token-equivalents;
       (b) carry: after the sub-task the parent carries V observation
           tokens for R more steps inline, but only the report rho when
           delegated -> saves 0.1 * R * (V - rho - a);
       (c) overhead: the child's O is written cold once (1.25x), its final
           report costs one extra request, and rho + a extra output tokens.
     Break-even R* solves inline(R) == delegated(R); both are linear in R.

  2. SIMULATED — run BOTH arms through the real Agent loop with
     CachingSimLLM (agentloop/sim.py) sharing one SimCache per arm, real
     ReadFileTool observations, real DelegateTool + usage roll-up, and
     compare AgentResult.cost_usd. This validates that the loop's
     accounting (tool-usage roll-up, child cost) reproduces the model, and
     exposes what the model leaves out (JSON framing, footer, task text).

    python3 bench_delegation.py            # grid + P3 row + simulation check
    python3 bench_delegation.py --json     # machine-readable rows
"""
import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass, replace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentloop import (Agent, AgentConfig, CachingSimLLM, ChildSpec, DelegateTool,  # noqa: E402
                       MockLLM, ReadFileTool, SimCache, ToolRegistry)
from agentloop.llm import text_turn, tool_turn  # noqa: E402
from agentloop.sim import render_request  # noqa: E402
from agentloop.usage import CACHE_READ_FACTOR, CACHE_WRITE_FACTOR, PRICES_PER_MTOK  # noqa: E402

MODEL = "claude-opus-5"


# ------------------------------------------------------------- analytic --

def price_sequence(sizes, outputs, model=MODEL, warm_prefix=0):
    """USD for requests whose renderings are each a prefix of the next.
    sizes[i] = input tokens of request i, outputs[i] = its output tokens;
    `warm_prefix` tokens of request 0 are already in the cache."""
    inp, out = PRICES_PER_MTOK[model]
    prev = warm_prefix
    cost = 0.0
    for s, o in zip(sizes, outputs):
        read = min(prev, s)
        write = max(0, s - read)
        cost += (read * CACHE_READ_FACTOR + write * CACHE_WRITE_FACTOR) * inp / 1e6
        cost += o * out / 1e6
        prev = s
    return cost


@dataclass
class Scenario:
    P: int            # parent prefix tokens (already cached) when the sub-task starts
    V: int            # sub-task observation tokens, total
    S: int            # sub-task steps (one tool result each)
    O: int = 1500     # child overhead: its system prompt + tools + framed task
    rho: int = 100    # report tokens the child returns
    a: int = 50       # assistant-turn tokens per step (tool call JSON / prose)
    g: int = 200      # parent growth per remaining step (small tool result + turn)
    R: int = 10       # parent steps remaining after the sub-task

    @property
    def d(self) -> int:
        """Per-step growth during the sub-task: observation + assistant turn."""
        return self.V // self.S + self.a


def inline_cost(sc: Scenario, model=MODEL) -> float:
    sizes = [sc.P + k * sc.d for k in range(sc.S)]
    base = sc.P + sc.S * sc.d
    sizes += [base + j * sc.g for j in range(sc.R)]
    sizes += [base + sc.R * sc.g]                       # the final-answer request
    outputs = [sc.a] * (sc.S + sc.R) + [sc.rho]
    return price_sequence(sizes, outputs, model, warm_prefix=sc.P)


def delegated_cost(sc: Scenario, model=MODEL) -> dict:
    parent_call = price_sequence([sc.P], [sc.a], model, warm_prefix=sc.P)
    child_sizes = [sc.O + k * sc.d for k in range(sc.S)] + [sc.O + sc.S * sc.d]
    child = price_sequence(child_sizes, [sc.a] * sc.S + [sc.rho], model, warm_prefix=0)
    base = sc.P + sc.a + sc.rho
    sizes = [base + j * sc.g for j in range(sc.R)] + [base + sc.R * sc.g]
    parent_rest = price_sequence(sizes, [sc.a] * sc.R + [sc.rho], model, warm_prefix=sc.P)
    return {"total": parent_call + child + parent_rest, "parent": parent_call + parent_rest,
            "child": child}


def delta(sc: Scenario, model=MODEL) -> float:
    """inline - delegated, USD (positive = delegation is cheaper)."""
    return inline_cost(sc, model) - delegated_cost(sc, model)["total"]


def break_even_R(sc: Scenario, model=MODEL):
    """Remaining parent steps at which delegation starts paying. Both arms are
    linear in R. Returns 0.0 when it pays immediately (delta(R=0) >= 0),
    float('inf') when carrying never catches up (V <= rho + a), else the
    real-valued R* (round up to the first integer step)."""
    d0 = delta(replace(sc, R=0), model)
    d1 = delta(replace(sc, R=1), model)
    slope = d1 - d0
    if d0 >= 0:
        return 0.0
    if slope <= 0:
        return float("inf")
    return -d0 / slope


def closed_form_R(sc: Scenario, model=MODEL) -> float:
    """The same break-even by hand (documents the three effects); asserted
    equal to break_even_R in the tests."""
    inp, out = PRICES_PER_MTOK[model]
    w, r = CACHE_WRITE_FACTOR, CACHE_READ_FACTOR
    Sd = sc.S * sc.d
    # costs delegation adds (token-equivalents at the input price)
    overhead = w * sc.O + r * (sc.O + Sd) + (out / inp) * (sc.rho + sc.a)
    # what it saves before any carrying: S sub-task reads of (P - O) at 0.1x
    avoidance = r * sc.S * (sc.P - sc.O)
    # the cheaper first remaining-step read happens inside the carry term:
    carry_per_step = r * (Sd - sc.a - sc.rho)
    if carry_per_step <= 0:
        return float("inf")
    val = (overhead - avoidance) / carry_per_step
    return max(0.0, val)


# ------------------------------------------------------------ simulated --

FILLER = "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor "


def _text(n_chars: int, seed: str = "") -> str:
    body = (seed + FILLER) * (n_chars // len(seed + FILLER) + 1)
    return body[:n_chars]


def simulate(sc: Scenario, chars_per_token: float = 4.0, model: str = MODEL) -> dict:
    """Run inline and delegated arms through the real Agent loop on a
    CachingSimLLM; return both costs plus what the analytic model says when
    fed the sizes the simulator actually rendered."""
    cpt = chars_per_token
    ws = tempfile.mkdtemp(prefix="bench-delegation-")
    per_file = int((sc.V // sc.S) * cpt)
    for k in range(sc.S):
        with open(os.path.join(ws, "big%d.txt" % k), "w") as f:
            f.write(_text(per_file, "file%d " % k))
    with open(os.path.join(ws, "small.txt"), "w") as f:
        f.write(_text(int((sc.g - sc.a) * cpt), "small "))
    report = _text(int(sc.rho * cpt), "report ")
    parent_system = _text(int(sc.P * cpt), "parent-system ")
    child_system = _text(int(sc.O * cpt), "child-system ")
    task = "process the big files, then keep working"
    big_reads = [tool_turn("read_file", path="big%d.txt" % k) for k in range(sc.S)]
    small_reads = [tool_turn("read_file", path="small.txt") for _ in range(sc.R)]
    final = text_turn(report)

    def run_arm(delegated: bool) -> dict:
        cache = SimCache()
        cfg = AgentConfig(system_prompt=parent_system, max_steps=sc.S + sc.R + 5)
        children = []

        def factory(spec: ChildSpec) -> Agent:
            llm = CachingSimLLM(MockLLM(big_reads + [text_turn(report)]), cache=cache,
                                chars_per_token=cpt, model=model)
            children.append(llm)
            return Agent(llm, ToolRegistry([ReadFileTool(ws)]),
                         AgentConfig(system_prompt=child_system, max_steps=sc.S + 3))

        tools = [ReadFileTool(ws), DelegateTool(factory)]
        if delegated:
            script = [tool_turn("delegate", task="read every big*.txt file and report the gist")]
        else:
            script = list(big_reads)
        script += small_reads + [final]
        llm = CachingSimLLM(MockLLM(script), cache=cache, chars_per_token=cpt, model=model)
        agent = Agent(llm, ToolRegistry(tools), cfg)
        # the parent prefix is warm when the sub-task starts (as in the model)
        cache.store(render_request([{"role": "system", "content": parent_system},
                                    {"role": "user", "content": task}], agent.registry.specs()))
        res = agent.run(task)
        assert res.ok, res.stop_reason
        return {"cost": res.cost_usd, "usage": res.usage.as_dict(), "parent": llm,
                "children": children, "steps": res.steps}

    inline = run_arm(False)
    deleg = run_arm(True)
    # Calibrated analytic: feed the model the sizes the simulator rendered.
    pr = inline["parent"].requests
    P_act = pr[0]["chars"] / cpt
    d_act = (pr[1]["chars"] - pr[0]["chars"]) / cpt if sc.S >= 1 else sc.d
    g_act = ((pr[sc.S + 1]["chars"] - pr[sc.S]["chars"]) / cpt) if sc.R >= 1 else sc.g
    cr = deleg["children"][0].requests
    O_act = cr[0]["chars"] / cpt
    calibrated = Scenario(P=int(P_act), V=int((d_act - sc.a) * sc.S), S=sc.S, O=int(O_act),
                          rho=sc.rho, a=sc.a, g=int(g_act), R=sc.R)
    return {
        "scenario": sc.__dict__, "model": model,
        "sim_inline": inline["cost"], "sim_delegated": deleg["cost"],
        "sim_delta": inline["cost"] - deleg["cost"],
        "analytic_inline": inline_cost(sc, model), "analytic_delegated": delegated_cost(sc, model)["total"],
        "analytic_delta": delta(sc, model),
        "calibrated": calibrated.__dict__, "calibrated_delta": delta(calibrated, model),
        "sim_child_cost": sum(c.usage.cost_usd(model) for c in deleg["children"]),
        "sim_parent_requests": len(pr), "sim_delegated_parent_requests": len(deleg["parent"].requests),
    }


# ------------------------------------------------------------------ main --

def grid(model=MODEL):
    rows = []
    for P in (2000, 8000, 20000, 50000):
        for V in (2000, 8000, 30000):
            for S in (2, 5):
                sc = Scenario(P=P, V=V, S=S)
                rows.append({"P": P, "V": V, "S": S, "O": sc.O,
                             "delta_R0": delta(replace(sc, R=0), model),
                             "delta_R10": delta(replace(sc, R=10), model),
                             "delta_R30": delta(replace(sc, R=30), model),
                             "break_even_R": break_even_R(sc, model)})
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-sim", action="store_true")
    args = ap.parse_args(argv)
    rows = grid()
    p3 = Scenario(P=20000, V=8000, S=4)
    p3_flat = replace(p3, P=p3.O)      # no prefix-avoidance: what the banked formula assumed
    out = {"grid": rows,
           "p3_row": {"P": p3.P, "V": p3.V, "S": p3.S, "O": p3.O, "break_even_R": break_even_R(p3),
                      "closed_form_R": closed_form_R(p3), "delta_R0": delta(replace(p3, R=0))},
           "p3_flat_row": {"P": p3_flat.P, "break_even_R": break_even_R(p3_flat),
                           "closed_form_R": closed_form_R(p3_flat)}}
    if not args.no_sim:
        out["sim"] = [simulate(Scenario(P=20000, V=8000, S=4, R=10)),
                      simulate(Scenario(P=2000, V=2000, S=2, R=2)),
                      simulate(Scenario(P=8000, V=30000, S=5, R=20))]
    if args.json:
        print(json.dumps(out, indent=1, default=str))
        return 0
    print("model %s: input $%.2f / output $%.2f per MTok; cache read %.1fx, write %.2fx"
          % (MODEL, PRICES_PER_MTOK[MODEL][0], PRICES_PER_MTOK[MODEL][1], CACHE_READ_FACTOR, CACHE_WRITE_FACTOR))
    print("\nGRID: delta = inline - delegated (USD, + means delegation cheaper); O=%d rho=%d a=%d g=%d"
          % (p3.O, p3.rho, p3.a, p3.g))
    print("%7s %7s %3s | %10s %10s %10s | %s" % ("P", "V", "S", "dR=0", "dR=10", "dR=30", "break-even R"))
    for r in rows:
        be = r["break_even_R"]
        print("%7d %7d %3d | %+10.4f %+10.4f %+10.4f | %s"
              % (r["P"], r["V"], r["S"], r["delta_R0"], r["delta_R10"], r["delta_R30"],
                 "immediately" if be == 0 else ("never" if be == float("inf") else "%.1f" % be)))
    print("\nP3 row (P=%d V=%d S=%d O=%d): break-even R = %s (closed form %.2f), delta at R=0 = %+.4f"
          % (p3.P, p3.V, p3.S, p3.O, out["p3_row"]["break_even_R"], out["p3_row"]["closed_form_R"],
             out["p3_row"]["delta_R0"]))
    print("P3 row with NO prefix avoidance (P=O=%d): break-even R = %.2f (closed form %.2f)"
          % (p3_flat.P, out["p3_flat_row"]["break_even_R"], out["p3_flat_row"]["closed_form_R"]))
    for s in out.get("sim", []):
        sc = s["scenario"]
        print("\nSIM P=%d V=%d S=%d R=%d: inline $%.4f vs delegated $%.4f (child $%.4f) -> sim delta %+.4f"
              % (sc["P"], sc["V"], sc["S"], sc["R"], s["sim_inline"], s["sim_delegated"],
                 s["sim_child_cost"], s["sim_delta"]))
        print("     analytic delta %+.4f (nominal) / %+.4f (calibrated to rendered sizes: P=%d O=%d V=%d g=%d)"
              % (s["analytic_delta"], s["calibrated_delta"], s["calibrated"]["P"], s["calibrated"]["O"],
                 s["calibrated"]["V"], s["calibrated"]["g"]))
        if s["analytic_delta"]:
            print("     sim/nominal = %.3f, sim/calibrated = %.3f"
                  % (s["sim_delta"] / s["analytic_delta"], s["sim_delta"] / s["calibrated_delta"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
