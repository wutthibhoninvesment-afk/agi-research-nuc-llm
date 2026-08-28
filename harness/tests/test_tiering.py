"""Regression test for harness/tests/conftest.py's fast/slow test tiering
(round 235).

Round 223's own backlog item 3 named the problem this closes: six straight
rounds (193/199/205/207/215/222) tried a single synchronous
`pytest harness/tests/` run and none completed within a round's time/turn
budget, because harness/swe/'s test_swe_*.py files run the real Whence
interpreter through minutes-long campaigns (test_swe_campaign.py alone:
~917s on this host, per round 209's own measurement) while the actual
agent-harness core (agent loop, tools, driver, retry/backoff) is fully
mockable and fast. `conftest.py` auto-marks every test collected from a
`test_swe_*.py` file `swe_slow`; `run_tests_fast.sh` runs `-m "not
swe_slow"` for a synchronous, complete core-harness smoke signal.

This test proves the marking is applied correctly and does not silently
drift (e.g. a future test_swe_*.py file added without the marker firing, or
the marker leaking onto a core-harness file) — via real subprocess pytest
collection, the same e2e style test_run_driver_lock.py already uses for
proving shell/process behaviour that unit-level mocking can't reach.
"""

import glob
import os
import subprocess
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TESTS_DIR = os.path.join(REPO_ROOT, "harness", "tests")


def _collect(*extra_args):
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *extra_args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    node_ids = [
        line
        for line in out.stdout.splitlines()
        if "::" in line and line.startswith("harness/tests/")
    ]
    return node_ids


def test_swe_slow_marker_selects_exactly_the_test_swe_files():
    fast = _collect("harness/tests/", "-m", "not swe_slow")
    slow = _collect("harness/tests/", "-m", "swe_slow")
    everything = _collect("harness/tests/")

    assert fast, "fast tier collected nothing — conftest.py likely broken"
    assert slow, "slow tier collected nothing — no test_swe_*.py found?"
    assert sorted(fast + slow) == sorted(everything)
    assert set(fast) & set(slow) == set()

    for node_id in slow:
        path = node_id.split("::", 1)[0]
        assert os.path.basename(path).startswith("test_swe_"), node_id
    for node_id in fast:
        path = node_id.split("::", 1)[0]
        assert not os.path.basename(path).startswith("test_swe_"), node_id


def test_every_test_swe_file_is_covered_by_the_slow_tier():
    swe_files = {
        os.path.basename(p)
        for p in glob.glob(os.path.join(TESTS_DIR, "test_swe_*.py"))
    }
    slow = _collect("harness/tests/", "-m", "swe_slow")
    covered_files = {node_id.split("::", 1)[0].rsplit("/", 1)[-1] for node_id in slow}
    assert swe_files == covered_files, (swe_files, covered_files)


def test_run_tests_fast_script_deselects_the_swe_tier():
    script = os.path.join(REPO_ROOT, "harness", "run_tests_fast.sh")
    out = subprocess.run(
        ["bash", script, "--collect-only"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert "deselected" in out.stdout
    node_ids = [
        line
        for line in out.stdout.splitlines()
        if line.startswith("harness/tests/")
    ]
    assert node_ids, out.stdout
    assert not any(
        line.split("/", 2)[-1].startswith("test_swe_") for line in node_ids
    )
