"""Real-model adapters behind the `LLM` interface.

ClaudeCLILLM drives the Claude Code CLI in print mode (`claude -p`) as a plain
completion engine: built-in tools are disabled, the harness's tool specs are
described in the system prompt, and the model is asked to emit tool calls as
a fenced ```tool block containing JSON. Conversation continuity uses the
CLI's own session (`--resume <session_id>`), so each turn only sends the new
tool observation, not the whole transcript.

Everything that touches a process is injected (`runner`) so the adapter is
unit-testable offline: tests hand it canned CLI JSON and assert on the argv it
builds and the turns it parses.
"""

import json
import os
import re
import subprocess
from typing import Callable, List, Optional, Sequence, Tuple

from .llm import LLM, AssistantTurn, ToolCall, RetryableLLMError, FatalLLMError, make_call_id
from .usage import Usage

TOOL_BLOCK = re.compile(r"```tool\s*\n(.*?)\n```", re.S)

PROTOCOL = """
You are being driven by a harness. You have NO built-in tools; the only
tools are the ones listed below. To call one, end your reply with exactly one
fenced block of the form:

```tool
{"name": "<tool name>", "args": {<json arguments>}}
```

The harness will run it and send you the result as the next user message.
You may call one tool per reply. When you are done, reply with plain text and
no tool block — that text is your final answer.

Tools:
"""


def _default_runner(argv: Sequence[str], stdin_text: str, timeout_s: float) -> Tuple[int, str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    try:
        p = subprocess.run(list(argv), input=stdin_text, capture_output=True, text=True,
                           timeout=timeout_s, env=env)
    except subprocess.TimeoutExpired:
        raise RetryableLLMError("claude CLI timed out after %.0fs" % timeout_s)
    return p.returncode, p.stdout, p.stderr


def render_tools(tools: Sequence[dict]) -> str:
    lines = []
    for t in tools:
        props = t.get("input_schema", {}).get("properties", {})
        req = set(t.get("input_schema", {}).get("required", []))
        args = ", ".join("%s%s: %s" % (k, "" if k in req else "?", v.get("type", "any"))
                         for k, v in props.items())
        lines.append("- %s(%s): %s" % (t["name"], args, t.get("description", "")))
    return "\n".join(lines)


BARE_FENCE = re.compile(r"\A```(?:json)?\s*\n(.*?)\n```\s*\Z", re.S)


def _bare_tool_call(text: str):
    """A reply that IS a tool call but lost its ```tool fence (observed live,
    round 17: sonnet emitted the JSON unfenced and the run ended early).
    Accepted only when the WHOLE reply — optionally inside a generic ``` or
    ```json fence — is one object shaped exactly {"name": str, "args": dict}
    (args optional). Task answers like {"claims": ...} do not match."""
    body = text.strip()
    m = BARE_FENCE.match(body)
    if m:
        body = m.group(1).strip()
    if not (body.startswith("{") and body.endswith("}")):
        return None
    try:
        payload = json.loads(body)
    except ValueError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("name"), str):
        return None
    args = payload.get("args", {})
    if not isinstance(args, dict) or set(payload) - {"name", "args"}:
        return None
    return ToolCall(payload["name"], args, make_call_id())


def parse_turn(text: str) -> AssistantTurn:
    """Split model text into prose + (at most one) tool call."""
    m = TOOL_BLOCK.search(text)
    if not m:
        call = _bare_tool_call(text)
        if call is not None:
            return AssistantTurn(text="", tool_calls=[call])
        return AssistantTurn(text=text.strip())
    prose = (text[:m.start()] + text[m.end():]).strip()
    try:
        payload = json.loads(m.group(1))
        name = payload["name"]
        args = payload.get("args", {}) or {}
        if not isinstance(args, dict):
            raise ValueError("args must be an object")
    except (ValueError, KeyError, TypeError) as e:
        # A malformed block becomes a call to a tool that cannot exist, so the
        # registry answers with an error the model can read and correct.
        return AssistantTurn(text=prose, tool_calls=[
            ToolCall("__malformed_tool_block__", {"error": str(e), "block": m.group(1)},
                     make_call_id())])
    return AssistantTurn(text=prose, tool_calls=[ToolCall(name, args, make_call_id())])


class ClaudeCLILLM(LLM):
    def __init__(self, model: str = "claude-sonnet-5", runner: Callable = _default_runner,
                 timeout_s: float = 300.0, executable: str = "claude",
                 max_turns_per_call: int = 1):
        self.model = model
        self._runner = runner
        self.timeout_s = timeout_s
        self.executable = executable
        self.session_id: Optional[str] = None
        self.calls: List[dict] = []          # {"argv", "prompt", "raw"} per call
        self.usage = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}

    # ---------------------------------------------------------------- api --
    def complete(self, messages: Sequence[dict], tools: Sequence[dict]) -> AssistantTurn:
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        argv = [self.executable, "-p", "--output-format", "json", "--model", self.model,
                "--tools", "", "--system-prompt", system + "\n" + PROTOCOL + render_tools(tools)]
        if self.session_id is None:
            prompt = self._initial_prompt(messages)
        else:
            argv += ["--resume", self.session_id]
            prompt = self._latest_prompt(messages)
        rc, out, err = self._runner(argv, prompt, self.timeout_s)
        record = {"argv": argv, "prompt": prompt, "raw": out}
        self.calls.append(record)
        if rc != 0:
            if "rate limit" in (out + err).lower() or "overloaded" in (out + err).lower():
                raise RetryableLLMError("claude CLI rc=%d: %s" % (rc, (err or out)[:300]))
            raise FatalLLMError("claude CLI rc=%d: %s" % (rc, (err or out)[:300]))
        try:
            data = json.loads(out)
        except ValueError:
            raise FatalLLMError("claude CLI returned non-JSON: %r" % out[:200])
        if data.get("is_error"):
            raise RetryableLLMError("claude CLI error result: %s" % str(data.get("result"))[:300])
        self.session_id = data.get("session_id", self.session_id)
        u = data.get("usage", {}) or {}
        turn_usage = Usage.from_api(u)
        self.usage["input_tokens"] += turn_usage.total_input
        self.usage["output_tokens"] += turn_usage.output_tokens
        self.usage["cost_usd"] += data.get("total_cost_usd", 0.0) or 0.0
        turn = parse_turn(data.get("result", "") or "")
        turn.usage = turn_usage                      # per-turn, for the agent's accounting
        turn.raw_stop_reason = "cli"
        return turn

    # --------------------------------------------------------- checkpoint --
    def checkpoint_state(self) -> dict:
        """The CLI holds the transcript server-side under session_id; that id
        is the whole resumable state (checkpoint.py). A resumed run whose
        session no longer exists on this machine fails fast as a
        FatalLLMError from the CLI, not silently as a fresh conversation."""
        return {"session_id": self.session_id}

    def restore_state(self, state: dict) -> None:
        self.session_id = (state or {}).get("session_id") or None

    # ------------------------------------------------------------ prompts --
    @staticmethod
    def _initial_prompt(messages: Sequence[dict]) -> str:
        parts = []
        for m in messages:
            if m["role"] == "user":
                parts.append(m["content"])
            elif m["role"] == "tool":
                parts.append("Tool result (%s):\n%s" % (m.get("tool_name"), m["content"]))
        return "\n\n".join(parts)

    @staticmethod
    def _latest_prompt(messages: Sequence[dict]) -> str:
        """With --resume the CLI already holds the transcript; send only the
        tool results produced since the last assistant turn."""
        tail = []
        for m in reversed(messages):
            if m["role"] == "assistant":
                break
            tail.append(m)
        tail.reverse()
        return "\n\n".join("Tool result (%s):\n%s" % (m.get("tool_name"), m["content"])
                           if m["role"] == "tool" else m["content"] for m in tail) \
            or "(continue)"


# ======================================================================
# AnthropicAPILLM — direct Messages API over stdlib HTTP
# ======================================================================
#
# The harness is stdlib-first (Python 3.9), so this speaks the raw wire
# protocol (`POST /v1/messages`) through `urllib`; the official SDK 1.x needs
# Python >= 3.10. The transport is injected so every branch — tool_use
# parsing, is_error results, 429/529 vs 400 mapping, network faults — is
# unit-tested offline with canned responses.
#
# Wire mapping (provider-neutral history -> Anthropic messages):
#   system            -> top-level `system`
#   user              -> {"role": "user", "content": text}
#   assistant         -> content blocks: [text?] + [tool_use ...]
#   tool (run of N)   -> ONE user message with N tool_result blocks
#                        (results of parallel calls must come back together)
#   tool.ok == False  -> tool_result.is_error = true

import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com"
API_VERSION = "2023-06-01"
OAUTH_BETA = "oauth-2025-04-20"
FALLBACK_BETA_ARRAY = "server-side-fallback-2026-06-01"    # fallbacks=[{"model": ...}]
FALLBACK_BETA_DEFAULT = "server-side-fallback-2026-07-01"  # fallbacks="default"
COMPACTION_BETA = "compact-2026-01-12"                     # server-side compaction
COMPACTION_EDIT = {"type": "compact_20260112"}             # context_management edit
RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 529}


def _urllib_transport(url: str, headers: dict, body: bytes, timeout_s: float):
    """(url, headers, body) -> (status, text, headers dict). Raises
    RetryableLLMError on network faults."""
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers or {})
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RetryableLLMError("network error: %r" % (e,))


def _parse_retry_after(headers: dict) -> Optional[float]:
    """Case-insensitive `retry-after` header lookup; delta-seconds form only
    (the only form Anthropic's API sends — HTTP-date is not attempted)."""
    for k, v in (headers or {}).items():
        if k.lower() == "retry-after":
            try:
                return max(0.0, float(v))
            except (TypeError, ValueError):
                return None
    return None


def to_anthropic_messages(messages: Sequence[dict]) -> Tuple[str, List[dict]]:
    """Convert harness history to (system, messages) in API shape."""
    system_parts = []
    out: List[dict] = []
    pending_results: List[dict] = []

    def flush_results():
        if pending_results:
            out.append({"role": "user", "content": list(pending_results)})
            pending_results.clear()

    for m in messages:
        role = m.get("role")
        if role == "system":
            system_parts.append(m.get("content") or "")
            continue
        if role == "tool":
            block = {"type": "tool_result", "tool_use_id": m.get("tool_call_id", ""),
                     "content": m.get("content") or ""}
            if m.get("ok") is False:
                block["is_error"] = True
            pending_results.append(block)
            continue
        flush_results()
        if role == "user":
            out.append({"role": "user", "content": m.get("content") or ""})
        elif role == "assistant":
            raw = m.get("raw_content")
            if raw:
                # Replay the provider's own content blocks verbatim. This is
                # required, not cosmetic: when extended thinking is on and a
                # turn made tool calls, the API rejects the next request
                # (400) unless the thinking/redacted_thinking blocks that
                # preceded those tool_use blocks come back byte-identical,
                # signature included — reconstructing from text/tool_calls
                # below silently drops them.
                blocks = list(raw)
            else:
                blocks = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for c in m.get("tool_calls") or []:
                    blocks.append({"type": "tool_use", "id": c.get("call_id") or make_call_id("toolu"),
                                   "name": c["name"], "input": c.get("args") or {}})
                if not blocks:
                    blocks.append({"type": "text", "text": "(no content)"})
            out.append({"role": "assistant", "content": blocks})
        else:
            raise FatalLLMError("unknown message role %r" % role)
    flush_results()
    return "\n\n".join(p for p in system_parts if p), out


def parse_api_message(data: dict) -> AssistantTurn:
    """Response JSON -> AssistantTurn (text joined, tool_use blocks -> calls).

    `raw_content` keeps the full content-block list (thinking,
    redacted_thinking, text, tool_use — in the order the API returned them)
    so agent.py can stash it on the assistant message and
    to_anthropic_messages() can replay it verbatim on the next turn. See the
    comment there for why this matters with extended thinking + tool use.
    """
    texts, calls = [], []
    content = data.get("content") or []
    for block in content:
        t = block.get("type")
        if t == "text":
            texts.append(block.get("text", ""))
        elif t == "tool_use":
            args = block.get("input") or {}
            if not isinstance(args, dict):
                args = {"error": "tool input was not an object", "input": args}
            calls.append(ToolCall(block["name"], args, block.get("id", "")))
        # thinking / redacted_thinking / compaction blocks carry no
        # agent-visible text or calls; they are preserved only in
        # raw_content, below. For compaction blocks that preservation is
        # load-bearing: replaying them verbatim is how the server-side
        # compaction beta replaces the compacted history on later requests
        # — extracting only the text would silently lose that state.
    stop = data.get("stop_reason") or ""
    text = "\n".join(texts).strip()
    if stop == "refusal":
        details = data.get("stop_details") or {}
        text = (text + "\n" if text else "") + "[model refused: %s]" % (details.get("category") or "unspecified")
        calls = []  # never act on a refused turn
    return AssistantTurn(text=text, tool_calls=calls, usage=Usage.from_api(data.get("usage")),
                         raw_stop_reason=stop, raw_content=list(content) if content else None)


CACHE_MAX_BREAKPOINTS = 4        # API limit per request
CACHE_MOVING_BREAKPOINTS = 2     # markers we spend on the newest user messages


def apply_cache_markers(body: dict, cache: dict) -> int:
    """Place `cache_control` breakpoints on a built request body, in place.

    Strategy (see knowledge/round-019): the API's prompt cache is a prefix
    match keyed on rendered bytes in `tools` -> `system` -> `messages` order;
    `cache_control` markers are metadata, not content, so MOVING a marker
    between requests does not by itself invalidate anything.

      1. One marker on the (single) system block — because tools render
         before system, this caches tools + system together. If there is no
         system but there are tools, the marker goes on the last tool.
      2. Markers on the last content block of each of the newest
         CACHE_MOVING_BREAKPOINTS user-role messages. The newest one writes
         this request's entry; the previous one sits where LAST request's
         entry ended, keeping the lookup within the API's 20-block lookback
         window even when one turn appended many tool_result blocks.

    Total: at most 1 + CACHE_MOVING_BREAKPOINTS <= CACHE_MAX_BREAKPOINTS.

    Shape stability: every user message's string content is converted to a
    one-element text-block list whether or not it gets a marker this time.
    A message must not flip between string and block form as markers move
    across requests — the marker is invisible to the cache key, a shape
    change might not be.

    Only dicts built fresh by build_body/to_anthropic_messages are mutated
    (system/tools/user messages). Assistant messages are never touched: their
    blocks can be `raw_content` replayed by reference from the harness
    history, and marking those would mutate stored state.
    """
    placed = 0
    if body.get("system"):
        body["system"] = [{"type": "text", "text": body["system"],
                           "cache_control": dict(cache)}]
        placed += 1
    elif body.get("tools"):
        body["tools"][-1]["cache_control"] = dict(cache)
        placed += 1
    user_msgs = [m for m in body.get("messages") or [] if m.get("role") == "user"]
    for m in user_msgs:
        # Non-empty strings only: an empty text block is a wire error, and a
        # message that never converts can never flip shape either.
        if isinstance(m.get("content"), str) and m["content"]:
            m["content"] = [{"type": "text", "text": m["content"]}]
    for m in user_msgs[-CACHE_MOVING_BREAKPOINTS:]:
        blocks = m.get("content")
        if isinstance(blocks, list) and blocks:
            blocks[-1]["cache_control"] = dict(cache)
            placed += 1
    return placed


def _iter_response_lines(resp):
    """Decode a urllib response body as SSE lines, lazily (one HTTP read per
    line, no whole-body buffering) -- the point of streaming a large
    max_tokens completion is exactly to not hold the whole thing in memory
    or behind one long blocking read."""
    for raw_line in resp:
        yield raw_line.decode("utf-8", "replace").rstrip("\r\n")


def _urllib_stream_transport(url: str, headers: dict, body: bytes, timeout_s: float):
    """(url, headers, body) -> (status, headers dict, iterable of decoded
    lines). Unlike _urllib_transport this never reads the whole body up
    front for a 2xx response -- callers get an iterator. On HTTPError the
    body is small (a JSON error object) and is read eagerly, split into
    lines, to keep call sites uniform."""
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout_s)
        return resp.status, dict(resp.headers), _iter_response_lines(resp)
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        return e.code, dict(e.headers or {}), iter(text.splitlines())
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RetryableLLMError("network error: %r" % (e,))


def parse_sse_events(lines: Sequence[str]):
    """Group raw SSE lines into (event_type, data_dict) pairs.

    Anthropic's stream is standard SSE: `event: <type>` then one or more
    `data: <json-fragment>` lines (multi-line data is newline-joined per the
    spec, though Anthropic always sends one data line per event), terminated
    by a blank line. Lines starting with `:` are comments/heartbeats and are
    skipped. If a server ever omits the `event:` line, the parsed payload's
    own `type` field is used as a fallback (some SSE producers do this).
    """
    event_type = None
    data_lines: List[str] = []

    def _flush():
        if not data_lines:
            return None
        text = "\n".join(data_lines)
        try:
            data = json.loads(text)
        except ValueError:
            data = {}
        return (event_type or data.get("type") or "", data)

    for line in lines:
        if line == "":
            ev = _flush()
            if ev is not None:
                yield ev
            event_type = None
            data_lines = []
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            event_type = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].strip())
    ev = _flush()
    if ev is not None:
        yield ev


def accumulate_stream(events) -> Tuple[dict, Optional[Tuple[str, str]]]:
    """Replay `message_start`/`content_block_*`/`message_delta`/`error`
    events into the SAME dict shape parse_api_message() expects from a
    non-streaming response -- so the rest of the adapter (thinking replay,
    tool_use parsing, usage accounting) needs zero streaming-specific code.

    Returns (message, error). `error` is (type, message) when the stream
    carried a mid-connection `event: error` frame (the HTTP status was
    already 200 by the time that can happen, so it can't be read off status
    codes the way a pre-stream failure can -- see _post_stream).
    """
    message: dict = {"content": [], "stop_reason": None, "usage": {}}
    blocks: List[Optional[dict]] = []
    for etype, data in events:
        if etype == "message_start":
            msg = data.get("message") or {}
            for k in ("id", "model", "role", "type"):
                if k in msg:
                    message[k] = msg[k]
            message["usage"] = dict(msg.get("usage") or {})
        elif etype == "content_block_start":
            idx = data.get("index", len(blocks))
            block = dict(data.get("content_block") or {})
            block.setdefault("type", "text")
            while len(blocks) <= idx:
                blocks.append(None)
            blocks[idx] = block
        elif etype == "content_block_delta":
            idx = data.get("index")
            if idx is None or idx >= len(blocks) or blocks[idx] is None:
                continue  # malformed/out-of-order stream; skip rather than crash
            block = blocks[idx]
            delta = data.get("delta") or {}
            dtype = delta.get("type")
            if dtype == "text_delta":
                block["text"] = block.get("text", "") + delta.get("text", "")
            elif dtype == "thinking_delta":
                block["thinking"] = block.get("thinking", "") + delta.get("thinking", "")
            elif dtype == "signature_delta":
                block["signature"] = block.get("signature", "") + delta.get("signature", "")
            elif dtype == "input_json_delta":
                block["_partial_json"] = block.get("_partial_json", "") + delta.get("partial_json", "")
            else:
                # Unknown delta type (a future block kind — e.g. a
                # compaction block's content, if the server streams it as
                # <field>_delta). Every known delta appends one string
                # field to the same-named block field; apply that pattern
                # generically so tolerant replay does not silently drop
                # streamed state for block types this adapter predates.
                for k, v in delta.items():
                    if k != "type" and isinstance(v, str):
                        block[k] = block.get(k, "") + v
        elif etype == "content_block_stop":
            idx = data.get("index")
            if idx is None or idx >= len(blocks) or blocks[idx] is None:
                continue
            block = blocks[idx]
            if "_partial_json" in block:
                raw = block.pop("_partial_json")
                try:
                    block["input"] = json.loads(raw) if raw.strip() else {}
                except ValueError:
                    block["input"] = {"error": "malformed streamed tool input JSON", "raw": raw}
        elif etype == "message_delta":
            delta = data.get("delta") or {}
            if "stop_reason" in delta:
                message["stop_reason"] = delta["stop_reason"]
            if "stop_sequence" in delta:
                message["stop_sequence"] = delta["stop_sequence"]
            for k, v in (data.get("usage") or {}).items():
                if v is not None:
                    message["usage"][k] = v
        elif etype == "error":
            err = data.get("error") or {}
            message["content"] = [b for b in blocks if b is not None]
            return message, (err.get("type", "error"), err.get("message", "stream error"))
        # message_stop / ping / content_block_start with unknown extra keys: no-op
    message["content"] = [b for b in blocks if b is not None]
    return message, None


class AnthropicAPILLM(LLM):
    def __init__(self, api_key: Optional[str] = None, auth_token: Optional[str] = None,
                 model: str = "claude-opus-5", max_tokens: int = 16000,
                 base_url: str = API_URL, timeout_s: float = 600.0,
                 effort: Optional[str] = None, thinking: Optional[dict] = None,
                 transport: Callable = _urllib_transport, extra_body: Optional[dict] = None,
                 stream: bool = False, stream_transport: Callable = _urllib_stream_transport,
                 cache: Optional[dict] = None, fallbacks=None,
                 server_compaction: bool = False):
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        auth_token = auth_token or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        if not api_key and not auth_token:
            raise FatalLLMError("no credentials: pass api_key/auth_token or set "
                                "ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN")
        self._api_key, self._auth_token = api_key, auth_token
        self.model, self.max_tokens = model, max_tokens
        self.base_url, self.timeout_s = base_url.rstrip("/"), timeout_s
        self.effort, self.thinking = effort, thinking
        self.extra_body = dict(extra_body or {})
        self._transport = transport
        # Anthropic requires stream=True for requests whose max_tokens implies
        # a long-running completion (the API rejects large-max_tokens,
        # non-streaming requests outright to avoid holding a connection open
        # for many minutes) -- this is what "streaming for large max_tokens"
        # on the harness backlog meant. stream is a plain opt-in flag, not
        # auto-detected from max_tokens: the harness stays behavior-explicit.
        self.stream = stream
        self._stream_transport = stream_transport
        # Prompt caching: a cache_control dict ({"type": "ephemeral"} or
        # {"type": "ephemeral", "ttl": "1h"}) turns on breakpoint placement
        # (see apply_cache_markers); None sends no markers at all. The API
        # silently skips caching below its per-model minimum prefix
        # (512-4096 tokens) — watch usage.cache_read_input_tokens, not errors.
        self.cache = dict(cache) if cache else None
        # Server-side refusal fallbacks: "default" (routes by refusal
        # category) or a list like [{"model": "claude-opus-4-8"}]. Each form
        # needs its own beta header — see _headers(). None = off.
        if fallbacks is not None and fallbacks != "default" and not isinstance(fallbacks, list):
            raise FatalLLMError('fallbacks must be None, "default", or a list of {"model": ...}')
        self.fallbacks = fallbacks
        # Server-side compaction (beta compact-2026-01-12): the API
        # summarizes earlier context into a `compaction` content block when
        # the conversation approaches the trigger threshold. The block comes
        # back inside the response content; because the harness stores and
        # replays assistant turns via raw_content VERBATIM, the "append full
        # response.content, never just the text" contract is already met
        # with no extra code. This is the no-prefix-damage alternative to
        # client compaction: nothing in the client transcript is mutated, so
        # the prompt-cache prefix stays byte-stable (claim is doc-sourced,
        # unverified live). Don't combine with an aggressive client
        # ContextBudget — two compactors fighting over the same history
        # makes the trace unreadable; pick one.
        self.server_compaction = bool(server_compaction)
        self.requests: List[dict] = []   # {"url", "body", "status", "raw"} per call
        self.usage = Usage()

    # ------------------------------------------------------------ headers --
    def _headers(self) -> dict:
        h = {"content-type": "application/json", "anthropic-version": API_VERSION}
        betas = []
        if self._api_key:
            h["x-api-key"] = self._api_key
        else:
            h["authorization"] = "Bearer " + self._auth_token
            betas.append(OAUTH_BETA)
        if self.fallbacks is not None:
            betas.append(FALLBACK_BETA_DEFAULT if self.fallbacks == "default"
                         else FALLBACK_BETA_ARRAY)
        if self.server_compaction:
            betas.append(COMPACTION_BETA)
        if betas:
            h["anthropic-beta"] = ",".join(betas)
        return h

    def _post(self, path: str, body: dict) -> dict:
        url = self.base_url + path
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        status, text, hdrs = self._transport(url, self._headers(), raw, self.timeout_s)
        self.requests.append({"url": url, "body": body, "status": status, "raw": text})
        try:
            data = json.loads(text) if text else {}
        except ValueError:
            data = {}
        if status >= 400 or data.get("type") == "error":
            err = (data.get("error") or {})
            msg = "HTTP %d %s: %s" % (status, err.get("type", "?"), err.get("message") or text[:300])
            if status in RETRYABLE_STATUS:
                raise RetryableLLMError(msg, retry_after=_parse_retry_after(hdrs))
            raise FatalLLMError(msg)
        if not isinstance(data, dict) or not data:
            raise FatalLLMError("non-JSON or empty response body: %r" % text[:200])
        return data

    # ---------------------------------------------------------------- api --
    def build_body(self, messages: Sequence[dict], tools: Sequence[dict]) -> dict:
        system, msgs = to_anthropic_messages(messages)
        body = {"model": self.model, "max_tokens": self.max_tokens, "messages": msgs}
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [{"name": t["name"], "description": t.get("description", ""),
                              "input_schema": t.get("input_schema", {"type": "object", "properties": {}})}
                             for t in tools]
        if self.thinking is not None:
            body["thinking"] = self.thinking
        if self.effort:
            body["output_config"] = {"effort": self.effort}
        if self.fallbacks is not None:
            body["fallbacks"] = self.fallbacks
        if self.server_compaction:
            body["context_management"] = {"edits": [dict(COMPACTION_EDIT)]}
        body.update(self.extra_body)
        if self.cache is not None:
            apply_cache_markers(body, self.cache)
        return body

    def complete(self, messages: Sequence[dict], tools: Sequence[dict]) -> AssistantTurn:
        body = self.build_body(messages, tools)
        if self.stream:
            body["stream"] = True
            data = self._post_stream(body)
        else:
            data = self._post("/v1/messages", body)
        turn = parse_api_message(data)
        self.usage = self.usage + turn.usage
        return turn

    def _post_stream(self, body: dict) -> dict:
        url = self.base_url + "/v1/messages"
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = self._headers()
        headers["accept"] = "text/event-stream"
        status, hdrs, lines = self._stream_transport(url, headers, raw, self.timeout_s)
        if status >= 400:
            # Failed before any SSE frame went out -- same shape as _post's
            # error handling, just fed from a line iterator instead of text.
            text = "\n".join(lines)
            self.requests.append({"url": url, "body": body, "status": status, "raw": text, "stream": True})
            try:
                data = json.loads(text) if text else {}
            except ValueError:
                data = {}
            err = (data.get("error") or {})
            msg = "HTTP %d %s: %s" % (status, err.get("type", "?"), err.get("message") or text[:300])
            if status in RETRYABLE_STATUS:
                raise RetryableLLMError(msg, retry_after=_parse_retry_after(hdrs))
            raise FatalLLMError(msg)
        events = list(parse_sse_events(lines))
        self.requests.append({"url": url, "body": body, "status": status, "raw": events, "stream": True})
        data, err = accumulate_stream(events)
        if err is not None:
            etype, emsg = err
            msg = "stream error %s: %s" % (etype, emsg)
            # No fresh HTTP status is available for a mid-stream error (the
            # connection was already a 200); classify by the error type the
            # non-streaming path would have seen in the same field.
            if etype in ("overloaded_error", "rate_limit_error", "api_error", "timeout_error"):
                raise RetryableLLMError(msg)
            raise FatalLLMError(msg)
        return data

    def count_tokens(self, messages: Sequence[dict], tools: Sequence[dict] = ()) -> int:
        body = self.build_body(messages, tools)
        body.pop("max_tokens", None)
        body.pop("fallbacks", None)  # completion-only parameter; not valid on count_tokens
        body.pop("context_management", None)  # ditto (compaction happens on completion)
        data = self._post("/v1/messages/count_tokens", body)
        return int(data.get("input_tokens", 0))
