#!/usr/bin/env python3
"""nuc-mini — a minimal agent profile for the pgain-nuc qwen36 lane (E2).

Design target: total first-turn prompt <= ~1000 engine tokens (the E1-measured
usable interactive ceiling: ~2.5 min prefill), while still allowing a real
agent turn (inspect the machine, run commands, read/write files) through the
existing tool-proxy on :8080 with NO server-side changes.

Two tiers:
  micro — ONE tool (run_shell). Shell covers read (cat) and write (heredoc)
          for short files; cheapest possible useful agent.
  mini  — run_shell + read_file + write_file: safer file round-trips, still
          three tight schemas.

Schema style rules (each rule is worth real tokens at 0.19 s/token prefill):
- descriptions are single short clauses, no examples, no markdown;
- no `required` lists where every param is required anyway is WRONG — keep
  `required` (the model needs it) but drop per-param descriptions that
  restate the name;
- system prompt states environment facts the model would otherwise burn a
  tool call discovering (host, user, allowed dirs).
- avoid ending any message text with punctuation directly before the frame
  boundary: the colibri worker mis-tokenizes a special token that follows
  punctuation (round-22 finding), spelling <|im_end|> out as text. Ending on
  a bare word keeps the control token real. (The adapter's protocol block
  ends with "wait for them." so the system frame is stuck with the wart
  until the proxy changes; user/tool frames we control end wordly.)
"""
import json

SYSTEM_MICRO = (
    "You are nuc-agent on pgain-nuc, a small Debian machine (user jab, 2 cores, "
    "31 GB RAM). Work step by step: call one tool, read its result, then decide. "
    "Keep replies under 80 words. Only touch files under /home/jab/nuc-research, "
    "/work/logs, or /tmp. When the task is complete, state the answer in plain "
    "text with no JSON"
)

TOOLS_MICRO = [
    {"type": "function", "function": {
        "name": "run_shell",
        "description": "Run a bash command on the host, returns stdout, stderr and exit code",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout_s": {"type": "integer"},
            },
            "required": ["command"],
        }}},
]

TOOLS_MINI = TOOLS_MICRO + [
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a UTF-8 text file, returns at most max_bytes of it",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "max_bytes": {"type": "integer"},
            },
            "required": ["path"],
        }}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Create or overwrite a UTF-8 text file with the given content",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        }}},
]


def request(user_text, tier="mini", history=()):
    """Build the OpenAI-shape request Hermes-or-anything would POST to :8080."""
    tools = TOOLS_MICRO if tier == "micro" else TOOLS_MINI
    msgs = [{"role": "system", "content": SYSTEM_MICRO}]
    msgs.extend(history)
    msgs.append({"role": "user", "content": user_text})
    return {"model": "qwen36-tools", "messages": msgs, "tools": tools,
            "max_tokens": 200, "stream": False}


if __name__ == "__main__":
    import prompt_budget as pb
    c = pb.Counter()
    for tier in ("micro", "mini"):
        req = request("How much disk space is free on the root filesystem", tier)
        b = pb.breakdown(req, c)
        t = b["total_prompt_tokens"]
        print(f"{tier}: {json.dumps({k: v for k, v in b.items() if k != 'per_tool'})}")
        print(f"  projected TTFT {pb.ttft_projected(t):.0f}s, "
              f"turn(+60 tok reply) {pb.turn_time(t)/60:.2f} min")
