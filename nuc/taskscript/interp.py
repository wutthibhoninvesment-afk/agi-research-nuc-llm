"""Errand interpreter: values with trails, consumed budgets, mandatory
preflight, policy retries, JSONL telemetry (SPEC §1–5).

Everything time- or chance-dependent is injected (clock, sleep, rng) so the
whole retry/budget story is testable offline and byte-exact.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import parser as P
from .transport import Reply, TransportError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fast_lane import qwen36_prefill_s  # noqa: E402  (the measured E1 curve, round 16/100)


# ------------------------------------------------------------------ values

@dataclass
class Ok:
    value: object                    # str | int | float | bool
    prov: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"Ok({self.value!r})"


@dataclass
class Miss:
    reasons: list
    prov: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"Miss({self.reasons!r})"


def render(v) -> str:
    """How a value prints and interpolates."""
    if isinstance(v, Miss):
        return "miss(" + "; ".join(v.reasons) + ")"
    x = v.value
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, float):
        return repr(x)
    return str(x)


def why(v) -> dict:
    if isinstance(v, Miss):
        return {"ok": False, "reasons": list(v.reasons), "prov": v.prov}
    return {"ok": True, "value": v.value, "prov": v.prov}


# ------------------------------------------------------------------ tokens + projection

class CharsTokenizer:
    """chars / chars_per_token + per_message frame overhead. An ESTIMATE —
    Qwen on English prose runs ~4 chars/token; a real tokenizer (E2's
    `prompt_budget.Counter`) plugs in through the same `count` method."""
    name = "chars"

    def __init__(self, chars_per_token: float = 4.0, per_message: int = 5):
        self.cpt = chars_per_token
        self.per_message = per_message

    def count(self, text: str) -> int:
        return int(len(text) / self.cpt + 0.999) + self.per_message


class CallableTokenizer:
    name = "custom"

    def __init__(self, fn: Callable[[str], int], per_message: int = 5):
        self.fn = fn
        self.per_message = per_message

    def count(self, text: str) -> int:
        return int(self.fn(text)) + self.per_message


@dataclass
class Projection:
    prompt_tokens: int
    reply_tokens: int
    ttft_s: float
    decode_s: float
    cold: bool = False               # True if a lane.cold_penalty was folded into ttft_s

    @property
    def total_s(self) -> float:
        return self.ttft_s + self.decode_s


def project(lane: P.Lane, prompt_tokens: int, reply_tokens: int, idle_s: Optional[float] = None) -> Projection:
    """idle_s = seconds since this lane's last call, or None if never called
    yet this run. Round-124 found a live NUC lane at ~2x its warm TTFT after
    a >1-day idle gap but flat (no measurable penalty) at gaps up to 180s
    (round-130) — too little data for a decay curve, so the penalty here is a
    single declared step (lane.cold_penalty) applied when idle_s is unknown
    or at/above lane.cold_after, not a continuous function of idle time."""
    if lane.prefill == "e1":
        ttft = qwen36_prefill_s(prompt_tokens)          # the curve already carries its 2.4 s fixed cost
    else:
        ttft = lane.fixed + prompt_tokens / float(lane.prefill)
    cold = lane.cold_after is not None and (idle_s is None or idle_s >= lane.cold_after)
    if cold:
        ttft += lane.cold_penalty
    return Projection(prompt_tokens, reply_tokens, ttft, reply_tokens / lane.decode, cold)


# ------------------------------------------------------------------ ledger

class Ledger:
    """A consumed budget: seconds and tokens spent, optionally under limits,
    optionally nested (a flow inside a flow shares its parent's remaining)."""
    def __init__(self, name: Optional[str], limit_s: Optional[float], limit_tokens: Optional[int],
                 parent: Optional["Ledger"] = None):
        self.name = name
        self.limit_s = limit_s
        self.limit_tokens = limit_tokens
        self.parent = parent
        self.spent_s = 0.0
        self.tokens_in = 0
        self.tokens_out = 0
        self.per_lane: dict = {}
        self.calls = 0

    def spend(self, seconds: float, lane: Optional[str] = None, tokens_in: int = 0, tokens_out: int = 0) -> None:
        self.spent_s += seconds
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        if lane is not None:
            row = self.per_lane.setdefault(lane, {"calls": 0, "seconds": 0.0, "tokens_in": 0, "tokens_out": 0})
            row["calls"] += 1
            row["seconds"] += seconds
            row["tokens_in"] += tokens_in
            row["tokens_out"] += tokens_out
        if self.parent is not None:
            self.parent.spend(seconds, lane, tokens_in, tokens_out)

    def remaining_s(self) -> Optional[float]:
        mine = None if self.limit_s is None else max(0.0, self.limit_s - self.spent_s)
        up = self.parent.remaining_s() if self.parent is not None else None
        if mine is None:
            return up
        return mine if up is None else min(mine, up)

    def tightest(self) -> Optional[str]:
        """Name of the ledger whose remaining seconds bind (for messages)."""
        best, best_name = None, None
        node: Optional[Ledger] = self
        while node is not None:
            if node.limit_s is not None:
                r = node.limit_s - node.spent_s
                if best is None or r < best:
                    best, best_name = r, node.name
            node = node.parent
        return best_name

    def summary(self) -> dict:
        return {"budget": self.name, "limit_s": self.limit_s, "spent_s": round(self.spent_s, 3),
                "remaining_s": None if self.remaining_s() is None else round(self.remaining_s(), 3),
                "tokens_in": self.tokens_in, "tokens_out": self.tokens_out, "calls": self.calls,
                "per_lane": {k: {**v, "seconds": round(v["seconds"], 3)} for k, v in self.per_lane.items()}}


# ------------------------------------------------------------------ expect

_PUNCT = ".,;:!?\"'`)]}"


def check_expect(exp: Optional[P.Expect], text: str):
    """Return (ok, value_or_reason). one_of canonicalises to the matched option."""
    if exp is None:
        return True, text
    if exp.kind == "nonempty":
        return (True, text) if text.strip() else (False, "expect nonempty: empty reply")
    if exp.kind == "contains":
        needle = exp.args[0]
        return (True, text) if needle in text else (False, f"expect contains {needle!r}: not in reply {text[:60]!r}")
    if exp.kind == "json":
        try:
            json.loads(text)
            return True, text
        except ValueError as ex:
            return False, f"expect json: {ex}"
    if exp.kind == "one_of":
        norm = text.strip().strip(_PUNCT).strip().lower()
        for opt in exp.args:
            if norm == opt.lower():
                return True, opt
        first = norm.split()[0].strip(_PUNCT) if norm.split() else ""
        for opt in exp.args:
            if first == opt.lower():
                return True, opt
        return False, f"expect one_of {exp.args}: reply {text[:60]!r}"
    return False, f"unknown expect {exp.kind}"


# ------------------------------------------------------------------ results

@dataclass
class FlowResult:
    flow: str
    emitted: list
    miss: Optional[Miss]
    seconds: float
    ledger: dict

    @property
    def ok(self) -> bool:
        return self.miss is None and all(isinstance(v, Ok) for v in self.emitted)


class Interp:
    def __init__(self, prog: P.Program, transport, tokenizer=None, *, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep, rng: Callable[[], float] = random.random,
                 trace: Optional[Callable[[dict], None]] = None, dry_run: bool = False,
                 default_timeout_s: float = 3600.0):
        self.prog = prog
        self.transport = transport
        self.tok = tokenizer or CharsTokenizer()
        self.clock, self.sleep, self.rng = clock, sleep, rng
        self.trace_fn = trace
        self.dry_run = dry_run
        self.default_timeout_s = default_timeout_s
        self.events: list = []
        self.task_calls = 0
        self._lane_last_call: dict[str, float] = {}   # lane name -> clock() at last non-refused attempt

    # -- telemetry
    def trace(self, ev: dict) -> None:
        self.events.append(ev)
        if self.trace_fn is not None:
            self.trace_fn(ev)

    # -- entry
    def run_flow(self, name: str, args: dict, parent: Optional[Ledger] = None) -> FlowResult:
        flow = self.prog.flows.get(name)
        if flow is None:
            raise KeyError(f"no flow {name!r}")
        missing = [p for p in flow.params if p not in args]
        extra = [k for k in args if k not in flow.params]
        if missing or extra:
            raise KeyError(f"flow {name!r}: missing {missing}, unexpected {extra}")
        env = {p: (args[p] if isinstance(args[p], (Ok, Miss)) else Ok(args[p], {"kind": "param", "name": p}))
               for p in flow.params}
        ledger = self._ledger_for(flow.budget, parent)
        t0 = self.clock()
        self.trace({"ev": "flow_start", "flow": name, "budget": flow.budget,
                    "remaining_s": ledger.remaining_s()})
        emitted: list = []
        miss = self._block(flow.body, env, emitted, ledger)
        seconds = self.clock() - t0 if not self.dry_run else ledger.spent_s
        res = FlowResult(name, emitted, miss, seconds, ledger.summary())
        self.trace({"ev": "flow_end", "flow": name, "ok": res.ok, "seconds": round(seconds, 3),
                    "emitted": len(emitted), "miss": None if miss is None else miss.reasons,
                    "ledger": res.ledger})
        return res

    def _ledger_for(self, budget_name: Optional[str], parent: Optional[Ledger]) -> Ledger:
        if budget_name is None:
            return Ledger(None, None, None, parent)
        b = self.prog.budgets[budget_name]
        return Ledger(b.name, b.time_s, b.tokens, parent)

    # -- statements
    def _block(self, stmts: list, env: dict, emitted: list, ledger: Ledger) -> Optional[Miss]:
        env = dict(env)
        for s in stmts:
            if isinstance(s, P.Let):
                env[s.name] = self._expr(s.expr, env, ledger)
            elif isinstance(s, P.Emit):
                emitted.append(self._expr(s.expr, env, ledger))
            elif isinstance(s, P.If):
                c = self._expr(s.cond, env, ledger)
                if isinstance(c, Miss):
                    return Miss([f"if at line {s.line}: condition missed"] + c.reasons,
                                {"kind": "if", "line": s.line, "condition": c.prov})
                if not isinstance(c.value, bool):
                    return Miss([f"if at line {s.line}: condition is {render(c)!r}, not a boolean"],
                                {"kind": "if", "line": s.line, "condition": c.prov})
                m = self._block(s.then if c.value else s.else_, env, emitted, ledger)
                if m is not None:
                    return m
        return None

    # -- expressions
    def _expr(self, e, env: dict, ledger: Ledger):
        if isinstance(e, P.Num):
            return Ok(e.value, {"kind": "literal", "line": e.line})
        if isinstance(e, P.Bool):
            return Ok(e.value, {"kind": "literal", "line": e.line})
        if isinstance(e, P.Name):
            return env[e.name]
        if isinstance(e, P.Str):
            return self._interpolate(e, env)
        if isinstance(e, P.Rescue):
            left = self._expr(e.left, env, ledger)
            if isinstance(left, Ok):
                return left
            right = self._expr(e.right, env, ledger)
            if isinstance(right, Miss):
                return Miss(right.reasons + ["(rescue of: " + "; ".join(left.reasons) + ")"],
                            {"kind": "rescue", "line": e.line, "recovered": why(left), "prov": right.prov})
            return Ok(right.value, {"kind": "rescue", "line": e.line, "recovered": why(left), "prov": right.prov})
        if isinstance(e, P.Cmp):
            left = self._expr(e.left, env, ledger)
            right = self._expr(e.right, env, ledger)
            bad = [v for v in (left, right) if isinstance(v, Miss)]
            if bad:
                return Miss([f"{e.op} at line {e.line}: an operand missed"] + [r for v in bad for r in v.reasons],
                            {"kind": "cmp", "op": e.op, "line": e.line, "inputs": [why(left), why(right)]})
            eq = left.value == right.value and type(left.value) is type(right.value)
            return Ok(eq if e.op == "==" else not eq,
                      {"kind": "cmp", "op": e.op, "line": e.line, "inputs": [why(left), why(right)]})
        if isinstance(e, P.Call):
            args = [self._expr(a, env, ledger) for a in e.args]
            if e.name in P.BUILTINS:
                return self._builtin(e.name, args, e.line)
            if e.name in self.prog.tasks:
                return self._task(self.prog.tasks[e.name], args, ledger, e.line)
            flow = self.prog.flows[e.name]
            bad = [i for i, a in enumerate(args) if isinstance(a, Miss)]
            if bad:
                return Miss([f"flow {e.name} at line {e.line}: argument {bad[0] + 1} missed"] + args[bad[0]].reasons,
                            {"kind": "flow", "flow": e.name, "line": e.line, "inputs": [why(a) for a in args]})
            res = self.run_flow(e.name, dict(zip(flow.params, args)), parent=ledger)
            if res.miss is not None:
                return Miss([f"flow {e.name} at line {e.line} missed"] + res.miss.reasons,
                            {"kind": "flow", "flow": e.name, "line": e.line, "inner": why(res.miss)})
            if not res.emitted:
                return Miss([f"flow {e.name} at line {e.line} emitted nothing"],
                            {"kind": "flow", "flow": e.name, "line": e.line})
            last = res.emitted[-1]
            prov = {"kind": "flow", "flow": e.name, "line": e.line, "emitted": len(res.emitted),
                    "ledger": res.ledger, "prov": last.prov}
            return Miss(last.reasons, prov) if isinstance(last, Miss) else Ok(last.value, prov)
        raise TypeError(f"unknown expression node {type(e).__name__}")

    def _interpolate(self, s: P.Str, env: dict):
        out: list[str] = []
        inputs: list = []
        for part in s.parts:
            if isinstance(part, tuple):
                v = env[part[0]]
                if isinstance(v, Miss):
                    return Miss([f"string at line {s.line}: {{{part[0]}}} missed"] + v.reasons,
                                {"kind": "string", "line": s.line, "inputs": [why(v)]})
                inputs.append({"name": part[0], "prov": v.prov})
                out.append(render(v))
            else:
                out.append(part)
        prov = {"kind": "literal", "line": s.line}
        if inputs:
            prov = {"kind": "string", "line": s.line, "inputs": inputs}
        return Ok("".join(out), prov)

    def _builtin(self, name: str, args: list, line: int):
        (a,) = args
        if name == "why":
            return Ok(json.dumps(why(a), sort_keys=True), {"kind": "builtin", "name": "why", "line": line})
        if name == "missed":
            return Ok(isinstance(a, Miss), {"kind": "builtin", "name": "missed", "line": line})
        if isinstance(a, Miss):
            return Miss([f"{name} at line {line}: argument missed"] + a.reasons,
                        {"kind": "builtin", "name": name, "line": line, "inputs": [why(a)]})
        if not isinstance(a.value, str):
            return Miss([f"{name} at line {line}: wants a string, got {render(a)!r}"],
                        {"kind": "builtin", "name": name, "line": line, "inputs": [why(a)]})
        prov = {"kind": "builtin", "name": name, "line": line, "inputs": [why(a)]}
        if name == "len":
            return Ok(len(a.value), prov)
        if name == "lower":
            return Ok(a.value.lower(), prov)
        return Ok(a.value.strip(), prov)

    # -- tasks: preflight, attempts, retries
    def _task(self, task: P.Task, args: list, ledger: Ledger, line: int):
        lane = self.prog.lanes[task.lane]
        base = {"kind": "task", "task": task.name, "lane": lane.name, "line": line}
        bad = [i for i, a in enumerate(args) if isinstance(a, Miss)]
        if bad:
            return Miss([f"task {task.name} at line {line}: argument {bad[0] + 1} ({task.params[bad[0]]}) missed"]
                        + args[bad[0]].reasons, {**base, "inputs": [why(a) for a in args]})
        env = dict(zip(task.params, args))
        messages: list = []
        prompt_tokens = 0
        for role, s in (("system", task.system), ("user", task.user)):
            if s is None:
                continue
            text = self._interpolate(s, env).value
            messages.append({"role": role, "content": text})
            prompt_tokens += self.tok.count(text)
        request = {"model": lane.model, "messages": messages, "max_tokens": task.reply,
                   "temperature": 0, "stream": False}
        now = self.clock()
        last = self._lane_last_call.get(lane.name)
        idle_s = None if last is None else now - last
        proj = project(lane, prompt_tokens, task.reply, idle_s)
        self.task_calls += 1
        ledger.calls += 1

        # ---- preflight (SPEC §1): refuse before any request
        task_limit_s = task_limit_tokens = None
        if task.budget is not None:
            b = self.prog.budgets[task.budget]
            task_limit_s, task_limit_tokens = b.time_s, b.tokens
        remaining = ledger.remaining_s()
        limit_s = min(x for x in (task_limit_s, remaining) if x is not None) if (task_limit_s is not None or remaining is not None) else None
        bound = task.budget if (task_limit_s is not None and (remaining is None or task_limit_s <= remaining)) else ledger.tightest()
        refusal = None
        if lane.ctx is not None and prompt_tokens + task.reply > lane.ctx:
            refusal = f"preflight: {prompt_tokens} prompt + {task.reply} reply tokens exceed lane {lane.name} ctx {lane.ctx}"
        elif task_limit_tokens is not None and prompt_tokens > task_limit_tokens:
            refusal = f"preflight: {prompt_tokens} prompt tokens exceed budget {task.budget} tokens {task_limit_tokens}"
        elif ledger.limit_tokens is not None and prompt_tokens > ledger.limit_tokens:
            refusal = f"preflight: {prompt_tokens} prompt tokens exceed budget {ledger.name} tokens {ledger.limit_tokens}"
        elif limit_s is not None and proj.total_s > limit_s:
            refusal = (f"preflight: task {task.name} on {lane.name} projected {proj.total_s:.1f} s "
                       f"(ttft {proj.ttft_s:.1f} + decode {proj.decode_s:.1f}) > budget {bound} remaining {limit_s:.1f} s")
        self.trace({"ev": "preflight", "task": task.name, "lane": lane.name, "prompt_tokens": prompt_tokens,
                    "reply_tokens": task.reply, "projected_s": round(proj.total_s, 3),
                    "ttft_s": round(proj.ttft_s, 3), "limit_s": limit_s, "ok": refusal is None,
                    "refusal": refusal, "tokenizer": getattr(self.tok, "name", "?"),
                    "idle_s": None if idle_s is None else round(idle_s, 3), "cold": proj.cold})
        if refusal is not None:
            return Miss([refusal], {**base, "prompt_tokens": prompt_tokens, "projected_s": round(proj.total_s, 3),
                                    "refused": True, "inputs": [why(a) for a in args]})

        self._lane_last_call[lane.name] = now         # marks the lane "warm" from here for the next call

        # ---- attempts
        attempts: list = []
        max_attempts = task.retry + 1
        spent_here = 0.0
        for n in range(1, max_attempts + 1):
            left = None if limit_s is None else max(0.0, limit_s - spent_here)
            timeout = self.default_timeout_s if left is None else left
            t0 = self.clock()
            failure = None
            reply: Optional[Reply] = None
            try:
                reply = self.transport.send(lane, request, timeout)
            except TransportError as ex:
                failure = (str(ex), ex.retryable, ex.status)
            seconds = proj.total_s if self.dry_run else (self.clock() - t0)
            tin = reply.prompt_tokens if (reply is not None and reply.prompt_tokens is not None) else prompt_tokens
            tout = 0
            value = None
            if failure is None:
                if reply.dry:
                    value = task.expect.args[0] if (task.expect is not None and task.expect.kind == "one_of") else reply.text
                    tout = task.reply
                else:
                    tout = reply.completion_tokens if reply.completion_tokens is not None else self.tok.count(reply.text) - self.tok.per_message
                    okay, val = check_expect(task.expect, reply.text)
                    if okay:
                        value = val
                    else:
                        failure = (val, True, reply.status)
            spent_here += seconds
            ledger.spend(seconds, lane.name, tin, tout)
            rec = {"n": n, "seconds": round(seconds, 3), "tokens_in": tin, "tokens_out": tout,
                   "status": None if reply is None else reply.status,
                   "error": None if failure is None else failure[0]}
            attempts.append(rec)
            self.trace({"ev": "attempt", "task": task.name, "lane": lane.name, **rec})
            if failure is None:
                prov = {**base, "prompt_tokens": prompt_tokens, "projected_s": round(proj.total_s, 3),
                        "seconds": round(spent_here, 3), "attempts": attempts, "inputs": [why(a) for a in args]}
                self.trace({"ev": "result", "task": task.name, "ok": True, "attempts": n,
                            "seconds": round(spent_here, 3)})
                return Ok(value, prov)
            msg, retryable, _status = failure
            if not retryable or n == max_attempts:
                reason = f"task {task.name}: {'gave up after' if retryable else 'final failure at'} attempt {n}: {msg}"
                self.trace({"ev": "result", "task": task.name, "ok": False, "attempts": n,
                            "seconds": round(spent_here, 3), "reason": reason})
                return Miss([reason], {**base, "prompt_tokens": prompt_tokens, "attempts": attempts,
                                       "seconds": round(spent_here, 3), "inputs": [why(a) for a in args]})
            delay = task.backoff_s * (2 ** (n - 1)) * (0.5 + self.rng())
            left = None if limit_s is None else limit_s - spent_here
            if left is not None and delay + proj.total_s > left:
                reason = (f"task {task.name}: no budget for attempt {n + 1} (needs {delay:.1f} s wait + "
                          f"{proj.total_s:.1f} s, {left:.1f} s left in {bound}) after: {msg}")
                self.trace({"ev": "result", "task": task.name, "ok": False, "attempts": n,
                            "seconds": round(spent_here, 3), "reason": reason})
                return Miss([reason], {**base, "prompt_tokens": prompt_tokens, "attempts": attempts,
                                       "seconds": round(spent_here, 3), "inputs": [why(a) for a in args]})
            self.trace({"ev": "retry", "task": task.name, "after": n, "delay_s": round(delay, 3), "error": msg})
            if not self.dry_run:
                self.sleep(delay)
            spent_here += delay
            ledger.spend(delay)
        raise AssertionError("unreachable")
