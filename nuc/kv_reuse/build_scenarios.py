#!/usr/bin/env python3
"""Build real prompt sequences and project per-turn prefill under three
policies (none / strict / snapshot). Sessions:

  nuc-mini : turn 1 = the exact probe prompt (339 engine tokens), reply = the
             raw reply :8000 produced on 2026-08-24; later turns re-render it
             through the byte-identical adapter copy the way the tool-proxy does.
  hermes   : the real 26,483-token Hermes turn dumped in round 22, extended
             the same way (tool call -> tool result -> answer -> new question).
Writes kv_reuse/scenarios.json and kv_reuse/projections.json."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); NUC = os.path.dirname(HERE)
sys.path.insert(0, NUC)
import prompt_budget as pb, kv_reuse_model as krm

RAW_TOOL = '{"tool_calls":[{"name":"run_shell","arguments":{"command":"df -h /"}}]}'
RAW_TOOL2 = '{"tool_calls":[{"name":"run_shell","arguments":{"command":"free -m"}}]}'
ANSWER = "The root filesystem has 80 GB of free disk space."
ANSWER2 = "About 585 MB of RAM is available; the model worker holds most of it."
TOOL_OUT = "/dev/mapper/ubuntu--vg-root  98G   14G   80G  15% /"
TOOL_OUT2 = "Mem: 31984 31398 327 0 674 585\nSwap: 4095 3335 760"


def session(req1, replies_raw, followups, tool_outs):
    """Grow one OpenAI-shape conversation turn by turn; return (prompts, replies)."""
    ad = pb.load_adapter()
    msgs = list(req1["messages"]); tools = req1.get("tools")
    prompts, replies = [], []
    fu = list(followups); to = list(tool_outs)
    for raw in replies_raw:
        req = {"messages": msgs, "tools": tools}
        prompts.append(pb.engine_prompt(req, ad)); replies.append(raw)
        content, calls = ad.parse_tool_reply(raw) if tools else (raw, None)
        if calls:
            msgs = msgs + [{"role": "assistant", "content": content, "tool_calls": calls},
                           {"role": "tool", "name": calls[0]["function"]["name"], "content": to.pop(0)}]
        else:
            msgs = msgs + [{"role": "assistant", "content": raw}]
            if fu:
                msgs = msgs + [{"role": "user", "content": fu.pop(0)}]
    return prompts, replies


def main():
    probe = json.load(open(os.path.join(HERE, "probe_p1.json")))
    scenarios = {}
    scenarios["nuc-mini"] = session(probe["request"], [RAW_TOOL, ANSWER, RAW_TOOL2, ANSWER2],
                                    ["Now check how much memory is free"], [TOOL_OUT, TOOL_OUT2])
    hd = os.path.join(NUC, "hermes-dump", "full_turn_request.json")
    if os.path.exists(hd):
        h = json.load(open(hd))
        scenarios["hermes"] = session({"messages": h["messages"], "tools": h.get("tools")},
                                      [RAW_TOOL, ANSWER, RAW_TOOL2], ["Now check how much memory is free"],
                                      [TOOL_OUT, TOOL_OUT2])
    json.dump({k: {"prompts": p, "replies": r} for k, (p, r) in scenarios.items()},
              open(os.path.join(HERE, "scenarios.json"), "w"))
    proj = {}
    for name, (prompts, replies) in scenarios.items():
        proj[name] = {}
        for policy in ("none", "strict", "snapshot"):
            rows = krm.agent_session(prompts, replies, policy=policy)
            proj[name][policy] = rows
            tot = sum(r["prefill_s"] for r in rows)
            print(f"{name:>8} {policy:>8}: " +
                  "  ".join(f"t{i+1} reuse {r['reuse']}/{r['np']} -> {r['prefill_s']}s" for i, r in enumerate(rows)) +
                  f"  | prefill total {tot/60:.1f} min")
    json.dump(proj, open(os.path.join(HERE, "projections.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
