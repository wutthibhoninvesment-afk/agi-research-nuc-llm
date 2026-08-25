"""Usage arithmetic and pricing."""
import pytest

from agentloop.usage import Usage, PRICES_PER_MTOK, CACHE_READ_FACTOR, CACHE_WRITE_FACTOR


def test_add_is_fieldwise_and_immutable():
    a = Usage(10, 5, 100, 20)
    b = Usage(1, 1, 1, 1)
    c = a + b
    assert c == Usage(11, 6, 101, 21)
    assert a == Usage(10, 5, 100, 20)          # frozen: unchanged
    assert c.total_input == 11 + 101 + 21 and c.total == c.total_input + 6


def test_cost_uses_cache_factors():
    u = Usage(input_tokens=1_000_000, output_tokens=1_000_000,
              cache_read_input_tokens=1_000_000, cache_creation_input_tokens=1_000_000)
    inp, out = PRICES_PER_MTOK["claude-opus-5"]
    expected = inp + out + inp * CACHE_READ_FACTOR + inp * CACHE_WRITE_FACTOR
    assert u.cost_usd("claude-opus-5") == pytest.approx(expected)


def test_unknown_model_is_unpriced_not_guessed():
    assert Usage(5, 5).cost_usd("some-future-model") is None
    assert Usage(5, 5).cost_usd("x", prices={"x": (1.0, 2.0)}) == pytest.approx((5 + 10) / 1e6)


def test_from_api_tolerates_missing_and_null_fields():
    assert Usage.from_api(None).is_zero
    u = Usage.from_api({"input_tokens": 7, "output_tokens": None, "cache_read_input_tokens": 3})
    assert u == Usage(7, 0, 3, 0)
    assert u.as_dict()["cache_creation_input_tokens"] == 0
