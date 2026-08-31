"""Regression test for harness/tests/conftest.py's fast/slow test tiering
(round 235, re-based on a MEASURED boundary by round 385).

Round 223's own backlog item 3 named the problem this closes: six straight
rounds (193/199/205/207/215/222) tried a single synchronous
`pytest harness/tests/` run and none completed within a round's time/turn
budget, because harness/swe/'s test_swe_*.py files run the real Whence
interpreter through campaigns that took minutes each, while the actual
agent-harness core (agent loop, tools, driver, retry/backoff) is fully
mockable and fast.

Round 235's rule was the FILENAME alone. Round 385 measured every file in
that tier and found it mixed rather than slow, so the filename now sets the
DEFAULT and `harness/tier-budget.json` may promote a measured-cheap,
measured-green file out of it (see harness/tierbudget.py).

What this file pins is therefore no longer "the two tiers partition on the
filename". It is the pair of properties that make the new rule safe:

  * the two tiers still partition the collected set EXACTLY — nothing is
    silently dropped or double-counted, which was round 235's real
    contribution and is unchanged;
  * a file is in the FAST tier only if the filename rule says fast OR the
    registry promoted it. There is no third way in, so the tier cannot
    drift open.

Real subprocess pytest collection throughout, the same e2e style
test_run_driver_lock.py uses for process-level behaviour a unit test can't
reach directly.
"""

import glob
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tierbudget  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TESTS_DIR = os.path.join(REPO_ROOT, "harness", "tests")


def _collect(*extra_args):
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *extra_args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    node_ids = [
        line
        for line in out.stdout.splitlines()
        if "::" in line and line.startswith("harness/tests/")
    ]
    return node_ids


def _basename(node_id):
    return os.path.basename(node_id.split("::", 1)[0])


def test_the_two_tiers_partition_the_collected_set_exactly():
    fast = _collect("harness/tests/", "-m", "not swe_slow")
    slow = _collect("harness/tests/", "-m", "swe_slow")
    everything = _collect("harness/tests/")

    assert fast, "fast tier collected nothing — conftest.py likely broken"
    assert slow, "slow tier collected nothing — no test_swe_*.py found?"
    assert sorted(fast + slow) == sorted(everything)
    assert set(fast) & set(slow) == set()


def test_the_fast_tier_admits_nothing_the_rule_and_the_registry_did_not():
    """The one-way property. A file reaches the fast tier by not matching the
    filename rule, or by being in the registry — never by anything else."""
    registry = tierbudget.load_registry()
    promoted = set(registry["promoted"])
    for node_id in _collect("harness/tests/", "-m", "not swe_slow"):
        name = _basename(node_id)
        assert not name.startswith("test_swe_") or name in promoted, node_id


def test_the_slow_tier_is_exactly_the_unpromoted_swe_files():
    swe_files = {
        os.path.basename(p)
        for p in glob.glob(os.path.join(TESTS_DIR, "test_swe_*.py"))
    }
    promoted = set(tierbudget.load_registry()["promoted"])
    slow = _collect("harness/tests/", "-m", "swe_slow")
    covered = {_basename(n) for n in slow}
    assert covered == swe_files - promoted, (covered, swe_files, promoted)
    for name in covered:
        assert name.startswith("test_swe_"), name


def test_run_tests_fast_script_deselects_the_unpromoted_swe_tier():
    script = os.path.join(REPO_ROOT, "harness", "run_tests_fast.sh")
    out = subprocess.run(
        ["bash", script, "--collect-only"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert "deselected" in out.stdout
    node_ids = [
        line
        for line in out.stdout.splitlines()
        if line.startswith("harness/tests/") and "::" in line
    ]
    assert node_ids, out.stdout
    promoted = set(tierbudget.load_registry()["promoted"])
    for node_id in node_ids:
        name = _basename(node_id)
        assert not name.startswith("test_swe_") or name in promoted, node_id


def test_the_promoted_files_actually_reach_the_fast_tier():
    """The other direction, and the one that would catch a registry the
    conftest hook silently stopped reading."""
    promoted = set(tierbudget.load_registry()["promoted"])
    if not promoted:
        return
    fast = {_basename(n) for n in _collect("harness/tests/", "-m", "not swe_slow")}
    assert promoted <= fast, sorted(promoted - fast)
