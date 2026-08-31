"""Tiers harness/tests/ into a fast "core harness" set and a slow "swe
subsystem" set, so a round can get a complete, synchronous pass/fail signal
for the agent harness itself without paying for SWE-loop(D)'s inherently
slow, real-interpreter-driven campaigns (mutation testing, corpus
differentials, guest evaluation) in the same run.

Motivated by round 223's own backlog item 3: six straight rounds
(193/199/205/207/215/222) tried a single synchronous `pytest harness/tests/`
run and none completed within a round's time/turn budget. Per-file timing
data recorded across rounds 193-233 (see knowledge/round-235-*.md) showed
why: `test_swe_campaign.py` alone was ~917s on this host, while the harness
core (agent loop, tool registry, driver, retry/backoff) is fully mockable
and fast.

Round 385: the rule is no longer the filename ALONE
---------------------------------------------------
Round 235's rule was `basename.startswith("test_swe_")`, with no cost input
of any kind, justified by a seven-row table it quoted out of rounds
193/209/215/217/221 rather than measured. `test_swe_*` names a SUBSYSTEM,
not a cost, and 150 rounds later most of that subsystem's files are cheap:
round 385's ladder (`python3 harness/tierbudget.py measure`) timed each file
alone in a fresh process and found the tier is mixed, not slow.

So the filename rule now decides the DEFAULT and `harness/tier-budget.json`
may promote a MEASURED-cheap, MEASURED-green file out of it. The direction
is one-way and fail-closed — see `harness/tierbudget.py`'s docstring — and
a file that does not match the prefix is fast no matter what the registry
says, so the registry cannot demote a core-harness file by accident.

If `tierbudget` cannot be imported or its registry cannot be read, this file
falls all the way back to round 235's rule with everything slow. A tier
registry must never be able to abort collection: that is round 348's
`pyproject.toml` outage (a third party's malformed config took all 1043
whence fast-tier tests down and the driver logged it as a test failure) with
this repo's own name on it.

No `swe_slow`-marked test is skipped by default — this only adds the marker;
`-m "not swe_slow"` is opt-in (see run_tests_fast.sh). A bare
`pytest harness/tests/` still runs everything, unchanged.
"""
import os
import sys

_HARNESS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HARNESS_DIR not in sys.path:
    sys.path.insert(0, _HARNESS_DIR)

try:
    import tierbudget as _tb
except Exception:                                   # pragma: no cover - see docstring
    _tb = None

#: basename -> seconds, accumulated over this session. Collection cost
#: (module import, which for these files is where the interpreter import
#: lives) plus every setup/call/teardown report. Round 385 measured this
#: against the ladder's standalone wall-clock; see knowledge/round-385-*.md.
_DURATIONS = {}


def _bump(nodeid, seconds):
    if not nodeid or seconds is None:
        return
    path = nodeid.split("::", 1)[0]
    if not path.endswith(".py"):
        return
    name = os.path.basename(path)
    _DURATIONS[name] = _DURATIONS.get(name, 0.0) + float(seconds)


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

    if _tb is None:
        for item in items:
            if item.fspath.basename.startswith("test_swe_"):
                item.add_marker(pytest.mark.swe_slow)
        return

    registry = _tb.load_registry()
    for item in items:
        if _tb.is_slow(item.fspath.basename, registry):
            item.add_marker(pytest.mark.swe_slow)


def pytest_collectreport(report):
    """Module collection — i.e. import time. `harness/swe/`'s modules pull in
    the real Whence interpreter, so for the promoted files this is a real
    share of the cost and leaving it out would flatter every budget."""
    _bump(getattr(report, "nodeid", None), getattr(report, "duration", None))


def pytest_runtest_logreport(report):
    _bump(getattr(report, "nodeid", None), getattr(report, "duration", None))


def pytest_terminal_summary(terminalreporter, exitstatus=None, config=None):
    """The free self-check: does this run agree with the numbers in the
    registry? Costs one dict comparison over data pytest already produced —
    no second process, no new dependency, and nothing anyone has to remember
    to run, which is the failure mode round 363 named.

    Pytest calls this BEFORE it writes its own terminal count line, so the
    count line stays last in the health log and
    `driver_health.classify_health_log`'s parenthetical is unchanged. That
    ordering is load-bearing and `test_tierbudget.py` pins it."""
    if _tb is None:
        return
    try:
        result = _tb.verify(_DURATIONS)
        if not result["n_observed"] and not result["load_error"]:
            return
        terminalreporter.write_line(_tb.format_verify_line(result))
    except Exception:                               # pragma: no cover
        return
