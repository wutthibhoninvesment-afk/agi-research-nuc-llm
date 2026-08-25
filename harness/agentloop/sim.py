"""CachingSimLLM — an offline double that PRICES requests like a provider.

MockLLM answers with scripted turns but reports whatever usage the script
says (usually nothing). That is fine for asserting loop behavior and
useless for asking economic questions ("is delegating this sub-task cheaper
than doing it inline?") whose answer depends on how the provider tokenizes
and caches a request. CachingSimLLM wraps any LLM and REPLACES each turn's
usage with a simulated bill:

  - tokens = chars / chars_per_token over the rendered request
    (tools, then system, then messages — the provider's render order);
  - prompt cache: the longest common prefix (in chars) between this
    request's rendering and any rendering in the shared `SimCache` store
    is billed as cache_read; the remainder as cache_creation (a write);
    plain uncached input_tokens are 0 because, like the real API with
    breakpoints on every request, everything new gets written;
  - output_tokens = the turn's text + tool-call JSON, same ratio.

Approximations, deliberately: the real cache matches at breakpoint
boundaries (not per char) and expires (TTL); neither is modelled — this
double answers "how much of the prefix is reusable", not "was it still
there". A shared store across a parent and its children mirrors one
provider account: a child whose system prompt differs from the parent's
shares nothing past the tools prefix, exactly like the real thing when the
breakpoint sits on system.
"""

import json
from typing import List, Sequence

from .llm import LLM, AssistantTurn
from .usage import Usage


def render_request(messages: Sequence[dict], tools: Sequence[dict]) -> str:
    """Deterministic rendering in provider order: tools, system, messages."""
    parts: List[str] = []
    for t in tools:
        parts.append(json.dumps(t, sort_keys=True))
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    for m in system + rest:
        parts.append(json.dumps({k: v for k, v in m.items() if k != "_chars"}, sort_keys=True))
    return "\n".join(parts)


def common_prefix_len(a: str, b: str) -> int:
    n = min(len(a), len(b))
    lo, hi = 0, n
    # a[:k] == b[:k] is monotone in k, so bisect instead of scanning.
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if a[:mid] == b[:mid]:
            lo = mid
        else:
            hi = mid - 1
    return lo


class SimCache:
    """The provider's prompt cache: every rendering ever sent, so a prefix
    can be matched against any earlier request (not just the last)."""

    def __init__(self):
        self.entries: List[str] = []

    def lookup(self, rendered: str) -> int:
        best = 0
        for e in self.entries:
            k = common_prefix_len(e, rendered)
            if k > best:
                best = k
        return best

    def store(self, rendered: str) -> None:
        self.entries.append(rendered)


class CachingSimLLM(LLM):
    def __init__(self, inner: LLM, cache: SimCache = None, chars_per_token: float = 4.0,
                 model: str = "claude-opus-5"):
        self.inner = inner
        # NOT named `cache`: agent.py reads `llm.cache` as the provider
        # cache_control dict (AnthropicAPILLM) to pick the write TTL — a
        # wrapper must not shadow that duck-typed attribute (found by test).
        self.sim_cache = cache if cache is not None else SimCache()
        self.chars_per_token = float(chars_per_token)
        self.model = model
        self.requests: List[dict] = []   # {"chars", "cached_chars", "usage"} per call
        self.usage = Usage()

    def _tokens(self, chars: int) -> int:
        return int(round(chars / self.chars_per_token))

    def complete(self, messages: Sequence[dict], tools: Sequence[dict]) -> AssistantTurn:
        rendered = render_request(messages, tools)
        cached_chars = self.sim_cache.lookup(rendered)
        self.sim_cache.store(rendered)
        turn = self.inner.complete(messages, tools)
        out_chars = len(turn.text) + sum(len(c.name) + len(json.dumps(c.args, sort_keys=True))
                                         for c in turn.tool_calls)
        usage = Usage(input_tokens=0,
                      output_tokens=self._tokens(out_chars),
                      cache_read_input_tokens=self._tokens(cached_chars),
                      cache_creation_input_tokens=self._tokens(len(rendered) - cached_chars))
        self.requests.append({"chars": len(rendered), "cached_chars": cached_chars,
                              "usage": usage.as_dict()})
        self.usage = self.usage + usage
        return AssistantTurn(text=turn.text, tool_calls=turn.tool_calls, usage=usage,
                             raw_stop_reason=turn.raw_stop_reason, raw_content=turn.raw_content)
