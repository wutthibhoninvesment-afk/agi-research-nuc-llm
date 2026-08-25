"""Context-window budgeting: estimate tokens, compact history when over budget.

The model's context is finite and every step appends to it. Without a
budget, a long run either fails with a 400 (request too large) or silently
degrades as early content falls off. This module gives the loop a
*deterministic* policy:

    1. estimate the tokens the next request will cost (cheap, local);
    2. if over budget, compact the history in place — oldest tool
       observations first, then whole early steps — until under budget;
    3. record what was removed so the model (and the trace) can tell.

Design decisions (each covered by a test):
  - Compaction is MONOTONIC and IN PLACE. Once an observation is elided it
    stays elided; the message prefix is stable across steps, which keeps
    provider prompt caches warm. (Rebuilding a fresh view each step would
    change the prefix every time.)
  - Pairing is preserved: an assistant turn that made tool calls is never
    separated from its tool results, and results are never dropped without
    their call. Steps are dropped as units (assistant + its results).
  - The system prompt and the original task are never touched. The most
    recent `keep_recent_results` observations are never elided — the model
    is usually acting on them right now.
  - Elision leaves a stub that says what was there and how big it was, so
    the model can re-run the tool if it needs the data back.
  - The estimator is a chars/token ratio that CALIBRATES against real usage
    reported by the provider (exponential moving average), so after a few
    steps the estimate tracks the real tokenizer without a network call.
  - chars_of() caches each message's char cost ON the message dict (`_chars`)
    the first time it is computed. A long-running loop calls chars_of() every
    step on a monotonically-growing history (agent.py:148, and compact()'s
    own entry check) — without a cache that is O(total transcript size) per
    step (re-running len()/json.dumps() over every past message, every step),
    which round 6 measured at 16ms/step at 2000 messages. With the cache,
    only messages appended (or mutated by elision) since the last call pay
    the json.dumps() cost; everything else is an int lookup + add. Mutation
    sites (_elide, the drop-stub replacement) are the only places that must
    invalidate the cache — they are enumerated here, not scattered.
"""

import json
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

ELIDED_STUB = "[observation elided to save context: {tool} returned {chars} chars; call it again if you need it]"
DROPPED_STUB = "[{n} earlier step(s) dropped to save context: {tools}]"


def _msg_chars(m: dict) -> int:
    """Char cost of one message, cached on the dict as `_chars`.

    Safe to cache because every code path that changes a message's `content`
    or `tool_calls` after it has been cached (currently only `_elide`) pops
    the cache key first. A message dict from the network / MockLLM never
    starts with `_chars` set, so a stale-looking cache can never be read
    before something in this file put it there.
    """
    cached = m.get("_chars")
    if cached is not None:
        return cached
    n = len(m.get("content") or "") + 8  # role/framing overhead
    for c in m.get("tool_calls") or []:
        n += len(c.get("name", "")) + len(json.dumps(c.get("args", {}), sort_keys=True)) + 8
    raw = m.get("raw_content")
    if raw:
        # Raw API content blocks (thinking/redacted_thinking/text/tool_use)
        # replayed verbatim are the true wire payload for this message; they
        # supersede the content/tool_calls estimate above rather than adding
        # to it (both are projections of the same turn).
        n = sum(len(json.dumps(b, sort_keys=True)) for b in raw) + 8
    m["_chars"] = n
    return n


class TokenEstimator:
    """Estimate request tokens from messages + tool specs. Calibratable."""

    def __init__(self, chars_per_token: float = 4.0, ema_alpha: float = 0.3,
                 min_ratio: float = 1.5, max_ratio: float = 10.0):
        if chars_per_token <= 0:
            raise ValueError("chars_per_token must be positive")
        self.chars_per_token = chars_per_token
        self.ema_alpha = ema_alpha
        self.min_ratio = min_ratio
        self.max_ratio = max_ratio
        self.observations = 0
        self._tools_cache: dict = {}  # id(tools) -> (len(tools), chars)

    # ---------------------------------------------------------------- size --
    def chars_of(self, messages: Sequence[dict], tools: Sequence[dict] = ()) -> int:
        return sum(_msg_chars(m) for m in messages) + self._tools_chars(tools)

    def _tools_chars(self, tools: Sequence[dict]) -> int:
        # Tool specs are one list object, built once per run and passed by
        # reference every step (agent.py) — safe to memoize by identity, with
        # a length check so a genuinely different list at the same id (would
        # need the old one GC'd and a new one allocated at the same address)
        # can't silently return a wrong cached value.
        key = id(tools)
        cached = self._tools_cache.get(key)
        if cached is not None and cached[0] == len(tools):
            return cached[1]
        n = sum(len(json.dumps(t, sort_keys=True)) for t in tools)
        self._tools_cache[key] = (len(tools), n)
        return n

    def estimate(self, messages: Sequence[dict], tools: Sequence[dict] = ()) -> int:
        return self.tokens_for_chars(self.chars_of(messages, tools))

    def tokens_for_chars(self, chars: int) -> int:
        return int(chars / self.chars_per_token) + 1

    # --------------------------------------------------------- calibration --
    def observe(self, chars: int, actual_tokens: int) -> None:
        """Feed a (chars sent, input tokens billed) pair; adjusts the ratio."""
        if chars <= 0 or actual_tokens <= 0:
            return
        ratio = chars / actual_tokens
        ratio = max(self.min_ratio, min(self.max_ratio, ratio))
        if self.observations == 0:
            self.chars_per_token = ratio
        else:
            a = self.ema_alpha
            self.chars_per_token = (1 - a) * self.chars_per_token + a * ratio
        self.observations += 1


@dataclass
class ContextBudget:
    max_input_tokens: int                 # hard ceiling for one request (estimated)
    keep_recent_results: int = 2          # newest tool observations never elided
    min_steps_kept: int = 1               # newest steps never dropped
    reserve_tokens: int = 0               # headroom under the ceiling (e.g. for output)
    # Which eligible observations stage 1 elides first (round 25):
    #   "oldest"  — information-preserving: the stalest observations go
    #               first. But the first mutation lands near the transcript
    #               HEAD, so nearly the whole rendered prompt after it is
    #               re-written at the cache-write price on the next request.
    #   "newest"  — cache-preserving: elide the newest ELIGIBLE observations
    #               (still never the keep_recent_results newest), so the
    #               mutation lands near the tail and the warm prefix ahead
    #               of it survives. Equal token savings, ~an order of
    #               magnitude less cache damage (bench_elision.py measures
    #               it); the cost is that fresher — likelier still relevant —
    #               observations are the ones stubbed out.
    # Default stays "oldest": task-information value is unmeasured, cache
    # damage is measured; don't silently trade the former for the latter.
    elide_order: str = "oldest"

    def __post_init__(self):
        if self.max_input_tokens <= 0:
            raise ValueError("max_input_tokens must be positive")
        if self.reserve_tokens >= self.max_input_tokens:
            raise ValueError("reserve_tokens must be < max_input_tokens")
        if self.elide_order not in ("oldest", "newest"):
            raise ValueError("elide_order must be 'oldest' or 'newest'")

    @property
    def target(self) -> int:
        return self.max_input_tokens - self.reserve_tokens


@dataclass
class CompactionReport:
    before_tokens: int
    after_tokens: int
    elided_results: int = 0
    dropped_steps: int = 0
    fits: bool = True
    # Prompt-cache damage accounting. Provider caches are a prefix match on
    # rendered bytes: mutating message i invalidates the cache for every
    # byte from i onward, so the NEXT request re-writes that suffix at the
    # cache-write price instead of reading it at ~0.1x. Monotonic in-place
    # compaction keeps the damage one-time-per-elision (the prefix before
    # the first mutation stays warm), but "monotonic" is not "free" — these
    # two fields quantify what one compact() call cost the cache.
    first_changed_index: Optional[int] = None  # smallest message index mutated, None if none
    invalidated_chars: int = 0                 # chars from that index to end, post-compaction

    @property
    def changed(self) -> bool:
        return self.elided_results > 0 or self.dropped_steps > 0

    def as_dict(self) -> dict:
        return {"before_tokens": self.before_tokens, "after_tokens": self.after_tokens,
                "elided_results": self.elided_results, "dropped_steps": self.dropped_steps,
                "fits": self.fits, "first_changed_index": self.first_changed_index,
                "invalidated_chars": self.invalidated_chars}


# ---------------------------------------------------------------- helpers --

def _steps(messages: Sequence[dict]) -> List[Tuple[int, int]]:
    """Index ranges [(start, end)) of each step: an assistant message plus the
    tool messages that follow it. Messages before the first assistant turn
    (system, task) are not steps."""
    steps = []
    i = 0
    n = len(messages)
    while i < n:
        if messages[i].get("role") == "assistant":
            j = i + 1
            while j < n and messages[j].get("role") == "tool":
                j += 1
            steps.append((i, j))
            i = j
        else:
            i += 1
    return steps


def _elide(msg: dict) -> int:
    """Replace a tool observation with a stub in place. Returns chars saved."""
    original = msg.get("content") or ""
    stub = ELIDED_STUB.format(tool=msg.get("tool_name", "tool"), chars=len(original))
    msg["content"] = stub
    msg["elided"] = True
    msg["elided_chars"] = len(original)
    msg.pop("_chars", None)  # content changed; invalidate the cached cost
    return len(original) - len(stub)


def compact(messages: List[dict], budget: ContextBudget, estimator: TokenEstimator,
            tools: Sequence[dict] = ()) -> CompactionReport:
    """Mutate `messages` until estimator says it fits `budget.target`.

    Ladder: (1) elide the oldest un-elided tool observations, leaving the
    newest `keep_recent_results` alone; (2) drop whole oldest steps, leaving
    `min_steps_kept`, replacing the dropped run with one summary user
    message. Returns a report; `fits=False` means even the floor is over.
    """
    before = estimator.estimate(messages, tools)
    report = CompactionReport(before_tokens=before, after_tokens=before)
    if before <= budget.target:
        return report

    # Stage 1: elide eligible observations in budget.elide_order ("oldest":
    # stalest info goes first; "newest": tail-most eligible goes first so the
    # cache prefix ahead of it survives — see ContextBudget). The running
    # size is kept incrementally (chars saved per elision) so a long history
    # costs O(n) per step, not O(n * elisions).
    tool_idx = [i for i, m in enumerate(messages)
                if m.get("role") == "tool" and not m.get("elided")]
    candidates = tool_idx[:max(0, len(tool_idx) - budget.keep_recent_results)]
    if budget.elide_order == "newest":
        candidates = candidates[::-1]
    chars = estimator.chars_of(messages, tools)
    for i in candidates:
        chars -= _elide(messages[i])
        report.elided_results += 1
        if report.first_changed_index is None or i < report.first_changed_index:
            report.first_changed_index = i
        if estimator.tokens_for_chars(chars) <= budget.target:
            break

    # Stage 2: drop whole early steps.
    if estimator.estimate(messages, tools) > budget.target:
        steps = _steps(messages)
        droppable = steps[:max(0, len(steps) - budget.min_steps_kept)]
        if droppable:
            # Drop one step at a time from the oldest, then re-check.
            dropped_tools: List[str] = []
            first_start = droppable[0][0]
            end = first_start
            for (s, e) in droppable:
                dropped_tools += [c.get("name", "?") for c in messages[s].get("tool_calls") or []]
                end = e
                report.dropped_steps += 1
                trial = messages[:first_start] + [_drop_stub(report.dropped_steps, dropped_tools)] + messages[end:]
                if estimator.estimate(trial, tools) <= budget.target:
                    break
            messages[first_start:end] = [_drop_stub(report.dropped_steps, dropped_tools)]
            # merge with a previous drop stub, if the prefix already had one
            _merge_drop_stubs(messages, first_start)
            merged = first_start > 0 and messages[first_start - 1].get("dropped_steps")
            drop_at = first_start - 1 if merged else first_start
            if report.first_changed_index is None or drop_at < report.first_changed_index:
                report.first_changed_index = drop_at

    report.after_tokens = estimator.estimate(messages, tools)
    report.fits = report.after_tokens <= budget.target
    if report.first_changed_index is not None:
        report.invalidated_chars = sum(_msg_chars(m)
                                       for m in messages[report.first_changed_index:])
    return report


def _drop_stub(n: int, tools: List[str]) -> dict:
    names = ", ".join(sorted(set(tools))) if tools else "no tools"
    return {"role": "user", "content": DROPPED_STUB.format(n=n, tools=names), "dropped_steps": n}


def _merge_drop_stubs(messages: List[dict], at: int) -> None:
    if at >= 1 and messages[at - 1].get("dropped_steps") and messages[at].get("dropped_steps"):
        prev, cur = messages[at - 1], messages[at]
        total = prev["dropped_steps"] + cur["dropped_steps"]
        tools = set()
        for m in (prev, cur):
            inner = m["content"].split(": ", 1)[1].rstrip("]") if ": " in m["content"] else ""
            tools.update(t for t in inner.split(", ") if t and t != "no tools")
        messages[at - 1:at + 1] = [_drop_stub(total, sorted(tools))]
