#!/usr/bin/env python3
"""OpenAI-compatible tool-calling adapter for the colibri qwen36 engine.

The upstream `coli serve` (qwen36 engine, :8000) rejects `tools` with 400
("Tool use is not wired up for the qwen36 engine yet"). This adapter accepts
standard OpenAI chat requests WITH tools, renders them into a deterministic
system prompt (JSON tool-call protocol), forwards a text-only request to
upstream, and parses the model's reply back into OpenAI `tool_calls`.

Design constraints (from /work/src/hermes CLAUDE.md ground rules):
- Lives OUTSIDE /work/src/colibri* (those internals are read-only).
- Does not touch hermes.service / colibri-* services; it only CALLS :8000.
- Never sends anything to :8001 (GLM frontier lane / KV-cache discipline).
- stdlib only; binds 127.0.0.1; single upstream engine => requests serialize.

Streaming: accepted for client comfort; internally non-streaming against the
slow CPU engine, then re-emitted as SSE chunks. Hermes gets a valid stream
either way.
"""
import json, os, re, threading, time, uuid, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("UPSTREAM", "http://127.0.0.1:8000/v1/chat/completions")
UPSTREAM_TIMEOUT = int(os.environ.get("UPSTREAM_TIMEOUT", "900"))
HOST = os.environ.get("ADAPTER_HOST", "127.0.0.1")
PORT = int(os.environ.get("ADAPTER_PORT", "8080"))
MODEL_ID = os.environ.get("ADAPTER_MODEL_ID", "qwen36-tools")
MAX_TOKENS = int(os.environ.get("ADAPTER_MAX_TOKENS", "1024"))
LOCK = threading.Lock()

TOOL_PROTOCOL = """You have tools available. Tools:
{tools_json}

PROTOCOL:
- To call a tool, reply with ONLY one line of JSON, no markdown, no other text:
  {{"tool_calls":[{{"name":"<tool name>","arguments":{{...}}}}]}}
- Multiple calls may appear in the same JSON array.
- Tool results come back to you; then continue reasoning or call again.
- When you have the final answer, reply in plain natural language (no JSON).
- Never invent tool results; wait for them."""


def render_tools(tools):
    slim = []
    for t in tools or []:
        f = t.get("function", t) if isinstance(t, dict) else {}
        slim.append({
            "name": f.get("name"),
            "description": f.get("description", ""),
            "parameters": f.get("parameters", {}),
        })
    return json.dumps(slim, ensure_ascii=False, indent=1)


def content_text(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(p.get("text", ""))
        return "\n".join(parts)
    return str(content)


def messages_to_text(messages, tools):
    """Flatten an OpenAI messages array (incl. tool roles / assistant
    tool_calls) into system/user/assistant-only turns the qwen36 template
    accepts. Deterministic rendering so identical conversations hit identical
    prompts."""
    sys_parts, convo = [], []
    for m in messages or []:
        role = m.get("role")
        text = content_text(m.get("content"))
        if role in ("system", "developer"):
            sys_parts.append(text)
        elif role == "tool":
            convo.append(("user",
                          f"[tool_result name={m.get('name','?')}]\n{text}\n[/tool_result]"))
        elif role == "assistant":
            tcs = m.get("tool_calls")
            if tcs:
                calls = []
                for tc in tcs:
                    fn = tc.get("function", {})
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {"raw": args}
                    calls.append({"name": fn.get("name"), "arguments": args})
                marker = json.dumps({"tool_calls": calls}, ensure_ascii=False)
                convo.append(("assistant", (text + "\n" + marker).strip() if text else marker))
            else:
                convo.append(("assistant", text))
        else:
            convo.append(("user", text))
    sys_text = "\n\n".join(p for p in sys_parts if p)
    if tools:
        proto = TOOL_PROTOCOL.format(tools_json=render_tools(tools))
        sys_text = (sys_text + "\n\n" + proto) if sys_text else proto
    out = []
    if sys_text:
        out.append({"role": "system", "content": sys_text})
    out.extend({"role": r, "content": c} for r, c in convo)
    return out


def parse_tool_reply(text):
    """Return (content_or_None, tool_calls_or_None) in OpenAI shape."""
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*\n?", "", s)
        s = re.sub(r"\n?```\s*$", "", s).strip()
    start, end = s.find("{"), s.rfind("}")
    if start >= 0 and end > start:
        try:
            d = json.loads(s[start:end + 1])
        except Exception:
            d = None
        if isinstance(d, dict) and isinstance(d.get("tool_calls"), list):
            calls = []
            for c in d["tool_calls"]:
                if not isinstance(c, dict) or not c.get("name"):
                    continue
                args = c.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {"raw": args}
                calls.append({
                    "id": "call_" + uuid.uuid4().hex[:12],
                    "type": "function",
                    "function": {"name": c["name"],
                                 "arguments": json.dumps(args, ensure_ascii=False)},
                })
            if calls:
                rest = (s[:start] + s[end + 1:]).strip()
                return (rest or None), calls
    return (text, None)


def upstream_completion(rendered, max_tokens):
    body = json.dumps({
        "model": "qwen36",
        "messages": rendered,
        "max_tokens": min(int(max_tokens or MAX_TOKENS), MAX_TOKENS),
        "stream": False,
    }).encode()
    req = urllib.request.Request(UPSTREAM, data=body,
                                 headers={"Content-Type": "application/json"})
    with LOCK:
        with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT) as r:
            return json.load(r)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print("[toolproxy] " + fmt % args, flush=True)

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/v1/models"):
            self._json(200, {"object": "list", "data": [
                {"id": MODEL_ID, "object": "model", "owned_by": "nuc-local"}]})
        elif self.path == "/healthz":
            self._json(200, {"ok": True, "upstream": UPSTREAM})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):
        if not self.path.startswith("/v1/chat/completions"):
            return self._json(404, {"error": {"message": "not found"}})
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n))
        except Exception as e:
            return self._json(400, {"error": {"message": f"bad request: {e}"}})

        tools = req.get("tools")
        if req.get("tool_choice") == "required" and not tools:
            return self._json(400, {"error": {"message": "tool_choice requires tools"}})
        rendered = messages_to_text(req.get("messages"), tools)
        t0 = time.time()
        try:
            up = upstream_completion(rendered, req.get("max_tokens"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            return self._json(e.code, {"error": {"message": f"upstream: {detail}"}})
        except Exception as e:
            return self._json(502, {"error": {"message": f"upstream error: {e}"}})

        msg = up["choices"][0]["message"]
        raw = content_text(msg.get("content"))
        content, tool_calls = (raw, None) if not tools else parse_tool_reply(raw)
        usage = up.get("usage") or {}
        base = {
            "id": "chatcmpl-" + uuid.uuid4().hex[:16],
            "object": "chat.completion",
            "created": int(time.time()),
            "model": MODEL_ID,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant",
                            "content": content if not tool_calls else content,
                            **({"tool_calls": tool_calls} if tool_calls else {})},
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }],
            "usage": {"prompt_tokens": usage.get("prompt_tokens"),
                      "completion_tokens": usage.get("completion_tokens"),
                      "total_tokens": usage.get("total_tokens")},
        }
        if not req.get("stream"):
            return self._json(200, base)

        # --- re-emit as SSE for streaming clients ---
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def sse(chunk):
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
            self.wfile.flush()

        cid = base["id"]
        created = base["created"]
        mk = lambda delta, fr=None: {"id": cid, "object": "chat.completion.chunk",
                                     "created": created, "model": MODEL_ID,
                                     "choices": [{"index": 0, "delta": delta,
                                                  "finish_reason": fr}]}
        sse(mk({"role": "assistant"}))
        if tool_calls:
            for i, tc in enumerate(tool_calls):
                sse(mk({"tool_calls": [{"index": i, "id": tc["id"], "type": "function",
                                        "function": tc["function"]}]}))
        elif content:
            sse(mk({"content": content}))
        sse(mk({}, fr="tool_calls" if tool_calls else "stop"))
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        print(f"[toolproxy] served in {time.time()-t0:.1f}s "
              f"(tool_calls={len(tool_calls) if tool_calls else 0})", flush=True)


if __name__ == "__main__":
    print(f"qwen36 tool-proxy: http://{HOST}:{PORT} -> {UPSTREAM}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
