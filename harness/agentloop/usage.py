"""Token usage and cost accounting.

Every LLM completion may report how many tokens it consumed. The harness
adds those up per run, prices them with a per-model table, and can stop a
run when a spend cap is hit — cost is a first-class stop reason, not a
surprise on the invoice.

Prices are USD per 1M tokens (Anthropic first-party API, cached 2026-06).
Cache reads are billed at 0.1x input; cache writes at 1.25x input for the
default 5-minute TTL and 2x for the 1-hour TTL (round 25 — previously
everything was priced at 1.25x with a documented gap). Which factor applies
is resolved in two layers: the response usage's `cache_creation` TTL
breakdown when the backend reports one, else the `write_ttl` the CALLER
configured — the client chose the TTL it sent in `cache_control`, so even
without the breakdown the attribution is exact for a single-TTL client
(round 19 called this unknowable; it isn't).
Unknown models price at 0 and are reported as unpriced, never guessed.
"""

from dataclasses import dataclass
from typing import Dict, Optional

# model -> (input $/1M, output $/1M)
PRICES_PER_MTOK: Dict[str, "tuple[float, float]"] = {
    "claude-fable-5": (10.00, 50.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}
CACHE_READ_FACTOR = 0.1
CACHE_WRITE_FACTOR = 1.25          # 5-minute-TTL write premium (default TTL)
CACHE_WRITE_FACTOR_1H = 2.0        # 1-hour-TTL write premium
_WRITE_FACTORS = {"5m": CACHE_WRITE_FACTOR, "1h": CACHE_WRITE_FACTOR_1H}


def _write_factor(write_ttl: str) -> float:
    try:
        return _WRITE_FACTORS[write_ttl]
    except KeyError:
        raise ValueError("unknown cache write TTL %r (use '5m' or '1h')" % (write_ttl,))


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0            # uncached input
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    # TTL breakdown of cache_creation_input_tokens, when the backend reports
    # a `cache_creation` object in usage; both 0 otherwise. NOT added into
    # total_input (they are a breakdown of the total above, not additional
    # tokens). Field names on the wire are ephemeral_5m_input_tokens /
    # ephemeral_1h_input_tokens (tolerated if present; unverified live —
    # the bundled API reference documents only the total).
    cache_creation_5m_tokens: int = 0
    cache_creation_1h_tokens: int = 0

    @property
    def total_input(self) -> int:
        return self.input_tokens + self.cache_read_input_tokens + self.cache_creation_input_tokens

    @property
    def total(self) -> int:
        return self.total_input + self.output_tokens

    @property
    def is_zero(self) -> bool:
        return self.total == 0

    @property
    def cache_hit_rate(self) -> float:
        """Fraction of input tokens served from the provider prompt cache.
        0.0 when nothing was sent (or the backend reports no cache fields)."""
        if self.total_input == 0:
            return 0.0
        return self.cache_read_input_tokens / self.total_input

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_input_tokens + other.cache_read_input_tokens,
            self.cache_creation_input_tokens + other.cache_creation_input_tokens,
            self.cache_creation_5m_tokens + other.cache_creation_5m_tokens,
            self.cache_creation_1h_tokens + other.cache_creation_1h_tokens,
        )

    def cost_usd(self, model: str, prices: Dict[str, "tuple[float, float]"] = None,
                 write_ttl: str = "5m") -> Optional[float]:
        """USD cost for this usage on `model`; None if the model is unpriced.

        Cache-write pricing: the per-TTL breakdown fields win when the
        backend reported them; any remainder (and everything, when there is
        no breakdown) is priced at `write_ttl`'s factor — pass the TTL the
        client actually configured in cache_control ("5m" default, "1h").
        """
        table = prices if prices is not None else PRICES_PER_MTOK
        if model not in table:
            _write_factor(write_ttl)   # still validate the caller's TTL
            return None
        inp, out = table[model]
        breakdown = self.cache_creation_5m_tokens + self.cache_creation_1h_tokens
        write_tokens_priced = (self.cache_creation_5m_tokens * CACHE_WRITE_FACTOR
                               + self.cache_creation_1h_tokens * CACHE_WRITE_FACTOR_1H)
        remainder = self.cache_creation_input_tokens - breakdown
        if remainder > 0:
            write_tokens_priced += remainder * _write_factor(write_ttl)
        return (self.input_tokens * inp
                + self.cache_read_input_tokens * inp * CACHE_READ_FACTOR
                + write_tokens_priced * inp
                + self.output_tokens * out) / 1_000_000

    def as_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_creation_5m_tokens": self.cache_creation_5m_tokens,
            "cache_creation_1h_tokens": self.cache_creation_1h_tokens,
        }

    @classmethod
    def from_api(cls, u: Optional[dict]) -> "Usage":
        """Build from an Anthropic-style usage dict; missing/None fields are 0.
        A `cache_creation` sub-object (per-TTL write breakdown) is parsed
        when present; its absence leaves the breakdown fields at 0 and
        pricing falls back to the caller-configured TTL."""
        u = u or {}
        cc = u.get("cache_creation") or {}
        return cls(
            int(u.get("input_tokens") or 0),
            int(u.get("output_tokens") or 0),
            int(u.get("cache_read_input_tokens") or 0),
            int(u.get("cache_creation_input_tokens") or 0),
            int(cc.get("ephemeral_5m_input_tokens") or 0),
            int(cc.get("ephemeral_1h_input_tokens") or 0),
        )


def cache_invalidation_cost_usd(invalidated_tokens: int, model: str,
                                prices: Dict[str, "tuple[float, float]"] = None,
                                write_ttl: str = "5m") -> Optional[float]:
    """One-time extra USD cost of breaking the prompt-cache prefix over
    `invalidated_tokens` tokens: they are re-WRITTEN once (1.25x input price
    at the default 5m TTL, 2x at 1h) instead of read (0.1x). None if the
    model is unpriced.

    This is the price of any prefix mutation — a compaction elision, an
    edited system prompt, a changed tool list. Compare it against the
    per-request tokens a compaction saves: eliding an old observation pays
    off only after roughly

        invalidated * (write_factor - 0.1) / (saved * 0.1)

    further requests (all-cached steady state; with an uncached suffix it
    pays off sooner). Pass the TTL the client configures in cache_control;
    at "1h" a break costs ~1.65x what it costs at "5m" per token, so the
    compact-only-when-forced rule matters even more there.
    """
    factor = _write_factor(write_ttl)
    table = prices if prices is not None else PRICES_PER_MTOK
    if model not in table:
        return None
    inp, _ = table[model]
    return invalidated_tokens * inp * (factor - CACHE_READ_FACTOR) / 1_000_000
