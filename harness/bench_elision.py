#!/usr/bin/env python3
"""Measure prompt-cache damage of the two stage-1 elision orders (round 25).

Backlog claim under test: "newest-eligible-first preserves a longer warm
prefix for equal savings". Two experiments, both offline (estimator-driven,
no network):

  single   one forced compaction of a 40-step history: same token target,
           compare invalidated_chars (chars from the first mutated message
           to the end — what the next request re-writes at cache-write
           price instead of reading at ~0.1x).
  run      a growing 60-step agent run compacting whenever the estimate is
           over budget: compare number of compactions, total elisions,
           CUMULATIVE invalidated chars, and the summed one-time
           invalidation cost (claude-opus-5, 5m TTL).

Usage: python3 bench_elision.py
"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentloop.context import ContextBudget, TokenEstimator, compact  # noqa: E402
from agentloop.usage import cache_invalidation_cost_usd  # noqa: E402

OBS_CHARS = 4000
MODEL = "claude-opus-5"


def history(n_steps, obs_chars=OBS_CHARS):
    msgs = [{"role": "system", "content": "s" * 800},
            {"role": "user", "content": "t" * 400}]
    for i in range(n_steps):
        msgs.append({"role": "assistant", "content": "step %d" % i, "tool_calls": [
            {"name": "read_file", "args": {"path": "f%d" % i}, "call_id": "c%d" % i}]})
        msgs.append({"role": "tool", "content": "x" * obs_chars, "tool_call_id": "c%d" % i,
                     "tool_name": "read_file", "ok": True})
    return msgs


def inval_cost(est, invalidated_chars):
    return cache_invalidation_cost_usd(est.tokens_for_chars(invalidated_chars), MODEL)


def single(order):
    est = TokenEstimator(chars_per_token=4.0)
    msgs = history(40)
    budget = ContextBudget(max_input_tokens=30_000, keep_recent_results=2,
                           elide_order=order)
    rep = compact(msgs, budget, est)
    return {"order": order, "elided": rep.elided_results, "after": rep.after_tokens,
            "first_changed": rep.first_changed_index,
            "invalidated_chars": rep.invalidated_chars,
            "cost_usd": inval_cost(est, rep.invalidated_chars)}


def growing_run(order, steps=60):
    est = TokenEstimator(chars_per_token=4.0)
    budget = ContextBudget(max_input_tokens=30_000, keep_recent_results=2,
                           elide_order=order)
    msgs = history(0)
    n_compactions = elided = inval_chars = 0
    cost = 0.0
    for i in range(steps):
        rep = compact(msgs, budget, est)   # what the agent loop does pre-request
        if rep.changed:
            n_compactions += 1
            elided += rep.elided_results
            inval_chars += rep.invalidated_chars
            cost += inval_cost(est, rep.invalidated_chars)
        msgs.append({"role": "assistant", "content": "step %d" % i, "tool_calls": [
            {"name": "read_file", "args": {"path": "f%d" % i}, "call_id": "c%d" % i}]})
        msgs.append({"role": "tool", "content": "x" * OBS_CHARS, "tool_call_id": "c%d" % i,
                     "tool_name": "read_file", "ok": True})
    final = est.estimate(msgs)
    return {"order": order, "compactions": n_compactions, "elided": elided,
            "cum_invalidated_chars": inval_chars, "cum_cost_usd": cost,
            "final_tokens": final}


def main():
    print("== single forced compaction (40 steps, target 30k tok) ==")
    rows = [single("oldest"), single("newest")]
    for r in rows:
        print("  %(order)7s: elided %(elided)2d  after %(after)6d tok  "
              "first_changed %(first_changed)3s  invalidated %(invalidated_chars)7d ch"
              "  one-time cost $%(cost_usd).4f" % r)
    a, b = rows
    assert a["elided"] == b["elided"] and a["after"] == b["after"], "unequal savings!"
    print("  newest/oldest invalidated: %.1f%%  (equal savings: %d elisions, %d tok both)"
          % (100.0 * b["invalidated_chars"] / a["invalidated_chars"],
             a["elided"], a["after"]))

    print("== growing 60-step run, compact whenever over budget ==")
    rows = [growing_run("oldest"), growing_run("newest")]
    for r in rows:
        print("  %(order)7s: %(compactions)2d compactions  %(elided)2d elided  "
              "cum invalidated %(cum_invalidated_chars)8d ch  cum cost $%(cum_cost_usd).4f"
              "  final %(final_tokens)6d tok" % r)
    a, b = rows
    assert a["final_tokens"] == b["final_tokens"], "runs diverged in size"
    print("  newest/oldest cumulative invalidated: %.1f%%"
          % (100.0 * b["cum_invalidated_chars"] / a["cum_invalidated_chars"]))


if __name__ == "__main__":
    main()
