"""Retry with exponential backoff + jitter.

Sleep and randomness are injected so tests run instantly and
deterministically: pass sleep=fake, rng=lambda: 0.5.
"""

import random
import time
from dataclasses import dataclass, field
from typing import Callable, List, Tuple, Type


@dataclass
class RetryPolicy:
    max_attempts: int = 4
    base_delay: float = 1.0      # seconds before first retry
    multiplier: float = 2.0      # exponential growth
    max_delay: float = 30.0      # cap on any single delay
    jitter: float = 0.5          # +/- fraction of delay randomized

    def delay_for(self, attempt: int, rng: Callable[[], float]) -> float:
        """Delay before retry number `attempt` (1-based). rng() in [0,1)."""
        raw = min(self.base_delay * (self.multiplier ** (attempt - 1)), self.max_delay)
        # jitter=0.5 -> uniform in [0.5*raw, 1.5*raw)
        return raw * (1.0 - self.jitter + 2.0 * self.jitter * rng())


class RetriesExhausted(Exception):
    def __init__(self, attempts: int, last_error: Exception):
        super().__init__("gave up after %d attempts: %r" % (attempts, last_error))
        self.attempts = attempts
        self.last_error = last_error


def retry_call(
    fn: Callable[[], object],
    retry_on: Tuple[Type[BaseException], ...],
    policy: RetryPolicy = None,
    sleep: Callable[[float], None] = time.sleep,
    rng: Callable[[], float] = random.random,
    on_retry: Callable[[int, Exception, float], None] = None,
):
    """Call fn(); on an exception in retry_on, back off and try again.

    Exceptions NOT in retry_on propagate immediately (fatal errors must not
    burn the retry budget). on_retry(attempt, error, delay) is a hook for
    trace logging.

    If the exception carries a `retry_after` attribute (RetryableLLMError
    does, when the provider sent a `retry-after` header), that delay is used
    verbatim instead of the policy's exponential schedule — clamped only to a
    sane non-negative floor, never to policy.max_delay, since a server-stated
    wait is information the policy's guess does not have. rng() is still
    consumed exactly once per non-final attempt regardless of which delay
    source wins, so callers that assert on `rng` call counts are unaffected.
    """
    policy = policy or RetryPolicy()
    if policy.max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    last_error = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return fn()
        except retry_on as e:
            last_error = e
            if attempt == policy.max_attempts:
                break
            computed = policy.delay_for(attempt, rng)
            hint = getattr(e, "retry_after", None)
            delay = max(0.0, hint) if hint is not None else computed
            if on_retry is not None:
                on_retry(attempt, e, delay)
            sleep(delay)
    raise RetriesExhausted(policy.max_attempts, last_error)
