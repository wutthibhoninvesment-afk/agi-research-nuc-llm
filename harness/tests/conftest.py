"""Auto-tiers harness/tests/ into a fast "core harness" set and a slow
"swe subsystem" set, so a round can get a complete, synchronous pass/fail
signal for the agent harness itself without paying for SWE-loop(D)'s
inherently slow, real-interpreter-driven campaigns (mutation testing,
corpus differentials, guest evaluation) in the same run.

Motivated by round 223's own backlog item 3: six straight rounds
(193/199/205/207/215/222) tried a single synchronous `pytest harness/tests/`
run and none completed within a round's time/turn budget. Per-file timing
data recorded across rounds 193-233 (see knowledge/round-235-*.md) shows why:
every `test_swe_*.py` file exercises the real Whence interpreter against
real programs (campaign runs, mutation sweeps, guest differentials) and
several take minutes each (test_swe_campaign.py alone: ~917s / 15min on this
host) — none of that is inherent to the harness core (agent loop, tool
registry, driver, retry/backoff), which is fully mockable and fast
(367 tests / ~43s, confirmed live by this round).

No `swe_slow`-marked test is skipped by default — this only adds the marker
and a `not swe_slow` deselection is opt-in (see run_fast.sh). A bare
`pytest harness/tests/` still runs everything, unchanged.
"""


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "swe_slow: real-interpreter-driven harness/swe/ subsystem test "
        "(mutation/campaign/guest/coverage) — slow by construction, not a "
        "flake. Deselect with `-m \"not swe_slow\"` for a fast core-harness "
        "smoke run.",
    )


def pytest_collection_modifyitems(config, items):
    import pytest

    for item in items:
        if item.fspath.basename.startswith("test_swe_"):
            item.add_marker(pytest.mark.swe_slow)
