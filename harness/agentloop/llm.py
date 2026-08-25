"""LLM interface + offline test doubles.

The harness talks to any LLM through one method:

    turn = llm.complete(messages, tools)

`messages` is a list of dicts in a provider-neutral shape:
    {"role": "system"|"user"|"assistant"|"tool", "content": str, ...}
Tool-result messages additionally carry {"tool_call_id": str, "tool_name": str}.

The LLM answers with an AssistantTurn: free text plus zero or more ToolCalls
(mirroring the Anthropic/OpenAI structured-tool-use shape, so swapping in a
real API client later is a thin adapter, not a rewrite).
"""

import itertools
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from .usage import Usage


@dataclass
class ToolCall:
    name: str
    args: Dict[str, object]
    call_id: str = ""


@dataclass
class AssistantTurn:
    text: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)   # tokens this completion cost
    raw_stop_reason: str = ""                     # provider's own stop reason, if any
    raw_content: Optional[List[dict]] = None      # verbatim API content blocks, if the
                                                   # backend has any (thinking/redacted_thinking
                                                   # included) — see adapters.to_anthropic_messages

    @property
    def wants_tools(self) -> bool:
        return len(self.tool_calls) > 0


class RetryableLLMError(Exception):
    """Transient failure (rate limit, overloaded, network). Safe to retry.

    `retry_after`, when the provider sent one (e.g. a `retry-after` response
    header), is a server-directed delay in seconds. retry_call() honors it
    over the policy's own backoff schedule — the server knows its own load,
    exponential guesswork does not.
    """

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class FatalLLMError(Exception):
    """Permanent failure (bad request, auth). Do not retry."""


class LLM:
    """Interface. Subclass and implement complete()."""

    def complete(self, messages: Sequence[dict], tools: Sequence[dict]) -> AssistantTurn:
        raise NotImplementedError


class MockLLM(LLM):
    """Plays back a fixed script of AssistantTurns, one per complete() call.

    Records every request it receives in .requests so tests can assert on
    exactly what the agent loop sent (message roles, tool results, truncation).
    Raises FatalLLMError if called more times than the script allows — a
    runaway loop in a test fails fast instead of hanging.
    """

    def __init__(self, script: Sequence[AssistantTurn]):
        self._script = list(script)
        self._cursor = 0
        self.requests: List[dict] = []  # {"messages": [...], "tools": [...]}

    def complete(self, messages: Sequence[dict], tools: Sequence[dict]) -> AssistantTurn:
        self.requests.append({"messages": list(messages), "tools": list(tools)})
        if self._cursor >= len(self._script):
            raise FatalLLMError(
                "MockLLM script exhausted after %d turns" % len(self._script)
            )
        turn = self._script[self._cursor]
        self._cursor += 1
        return turn

    @property
    def calls_made(self) -> int:
        return self._cursor


class FlakyLLM(LLM):
    """Wraps another LLM and fails the first `fail_times` calls.

    Used to test retry/backoff without a network. `error_factory` lets tests
    choose retryable vs fatal errors.
    """

    def __init__(
        self,
        inner: LLM,
        fail_times: int,
        error_factory: Callable[[], Exception] = None,
    ):
        self._inner = inner
        self._fail_times = fail_times
        self._error_factory = error_factory or (lambda: RetryableLLMError("simulated 529"))
        self.attempts = 0

    def complete(self, messages: Sequence[dict], tools: Sequence[dict]) -> AssistantTurn:
        self.attempts += 1
        if self.attempts <= self._fail_times:
            raise self._error_factory()
        return self._inner.complete(messages, tools)


_call_counter = itertools.count(1)


def make_call_id(prefix: str = "call") -> str:
    """Monotonic call ids ("call_1", "call_2", ...) — deterministic for tests."""
    return "%s_%d" % (prefix, next(_call_counter))


def tool_turn(name: str, /, **args: object) -> AssistantTurn:
    """Shorthand for scripting MockLLM turns: tool_turn("bash", cmd="ls")."""
    return AssistantTurn(tool_calls=[ToolCall(name=name, args=dict(args), call_id=make_call_id())])


def text_turn(text: str) -> AssistantTurn:
    return AssistantTurn(text=text)
