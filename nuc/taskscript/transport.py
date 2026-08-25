"""Transports for Errand tasks: Mock (scripted replies, records requests),
Dry (no request, placeholder reply flagged `dry`), HTTP (OpenAI-compatible
`/v1/chat/completions`, stdlib urllib). One interface:

    reply = transport.send(lane, request, timeout_s)   # -> Reply
    raise TransportError(msg, status=..., retryable=...)

Retryable = transport-level failures (connection, timeout) and HTTP 408 / 429 /
5xx; any other 4xx is final (the request itself is wrong; retrying re-pays the
prefill for nothing).
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

from .parser import FORBIDDEN_PORTS, Lane


class TransportError(Exception):
    def __init__(self, msg: str, status: Optional[int] = None, retryable: bool = True):
        super().__init__(msg)
        self.status = status
        self.retryable = retryable


def retryable_status(status: int) -> bool:
    return status in (408, 429) or status >= 500


@dataclass
class Reply:
    text: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    status: int = 200
    dry: bool = False


@dataclass
class MockTransport:
    """replies: {model_or_'*': [str | dict | Exception, ...]} consumed in order.
    A dict entry may carry text/prompt_tokens/completion_tokens/status; an
    Exception entry is raised (TransportError keeps its retryable flag)."""
    replies: dict = field(default_factory=dict)
    requests: list = field(default_factory=list)

    def send(self, lane: Lane, request: dict, timeout_s: float) -> Reply:
        self.requests.append({"lane": lane.name, "model": lane.model, "request": request,
                              "timeout_s": timeout_s})
        queue = self.replies.get(lane.model)
        if queue is None:
            queue = self.replies.get("*")
        if not queue:
            raise TransportError(f"mock: no reply scripted for model {lane.model!r}", retryable=False)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, dict):
            return Reply(str(item.get("text", "")), item.get("prompt_tokens"),
                         item.get("completion_tokens"), int(item.get("status", 200)))
        return Reply(str(item))

    @classmethod
    def from_file(cls, path: str) -> "MockTransport":
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise TransportError(f"mock file {path}: want an object {{model: [replies]}}", retryable=False)
        return cls({k: list(v) for k, v in data.items()})


class DryTransport:
    """Never touches the network: the interpreter charges projected seconds
    and skips `expect` for dry replies (taking the first option), so a whole
    flow can be priced with the box down."""
    def __init__(self) -> None:
        self.requests: list = []

    def send(self, lane: Lane, request: dict, timeout_s: float) -> Reply:
        self.requests.append({"lane": lane.name, "model": lane.model, "request": request,
                              "timeout_s": timeout_s})
        return Reply("<dry-run>", dry=True)


class HTTPTransport:
    def __init__(self, path: str = "/v1/chat/completions", opener=None):
        self.path = path
        self.opener = opener or urllib.request.urlopen

    def send(self, lane: Lane, request: dict, timeout_s: float) -> Reply:
        parsed = urlparse(lane.url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port in FORBIDDEN_PORTS:                      # belt and braces: the parser refused it already
            raise TransportError(f"refusing to send to forbidden port {port}", retryable=False)
        url = lane.url.rstrip("/") + self.path
        body = json.dumps(request).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"},
                                     method="POST")
        try:
            with self.opener(req, timeout=max(1.0, timeout_s)) as resp:
                raw = resp.read()
                status = getattr(resp, "status", 200)
        except urllib.error.HTTPError as ex:
            detail = ex.read()[:300].decode("utf-8", "replace") if hasattr(ex, "read") else ""
            raise TransportError(f"HTTP {ex.code}: {detail}", status=ex.code,
                                 retryable=retryable_status(ex.code)) from None
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as ex:
            raise TransportError(f"transport: {ex}", retryable=True) from None
        try:
            data = json.loads(raw.decode("utf-8"))
            choice = data["choices"][0]
            text = choice.get("message", {}).get("content")
            if text is None:
                text = choice.get("text", "")
            usage = data.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError) as ex:
            raise TransportError(f"bad response body: {ex}", status=status, retryable=False) from None
        return Reply(text or "", usage.get("prompt_tokens"), usage.get("completion_tokens"), status)
