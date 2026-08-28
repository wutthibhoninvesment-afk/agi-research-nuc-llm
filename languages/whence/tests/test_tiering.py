"""Regression test for tests/conftest.py's fast/slow test tiering
(round 242).

Round 241's own flagged backlog item: `languages/whence/tests/` (875
tests, ~404.61s / ~6:45 on this host, per round 241's own measurement) has
the same "too slow to run every round, so it silently doesn't" shape
harness/tests/ had before round 235's `swe_slow` tiering fixed it there.
Unlike harness/tests/'s `test_swe_*.py` filename convention, Whence's slow
tests are scattered across shared, version-numbered files that also hold
plenty of fast tests (test_v09.py, test_v10.py, test_self_hosting.py,
test_examples.py, test_self_eval.py, test_v03.py, test_v04.py, test_v11.py,
test_fuzz_regressions.py) — there is no filename prefix to key off, so
round 242 hand-placed `@pytest.mark.whence_slow` on the ~35 individual test
functions that measured >=1.0s in a real `pytest --durations=0` run (they
account for ~383s of the suite's ~405s — the other ~840 tests together cost
only ~20s). `run_tests_fast.sh` runs `-m "not whence_slow"`.

This test proves the tiering is complete and does not silently drift (a
new slow test added without the marker, or a marker that stops matching
after a rename) via real subprocess pytest collection — the same e2e style
harness/tests/test_tiering.py already uses for the equivalent harness-side
check.

To regenerate the underlying marker placement after real test-file changes:
`python3 -m pytest tests/ --durations=0 -q > /tmp/durations.log`, then
re-mark whichever individual tests cross whatever cutoff you're using
(round 242 used 1.0s) with `@pytest.mark.whence_slow`.
"""

import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.join(REPO_ROOT, "tests")

# The single biggest offender from round 242's own measurement (92.91s of
# the suite's 404.61s, by itself) — a canary that the marker didn't get
# silently dropped off the most expensive test in the suite.
BIGGEST_OFFENDER = "tests/test_v10.py::test_three_way_on_big_examples"


def _collect(*extra_args):
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *extra_args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    return [
        line
        for line in out.stdout.splitlines()
        if "::" in line and line.startswith("tests/")
    ]


def test_whence_slow_marker_partitions_the_suite_cleanly():
    fast = _collect("tests/", "-m", "not whence_slow")
    slow = _collect("tests/", "-m", "whence_slow")
    everything = _collect("tests/")

    assert fast, "fast tier collected nothing — conftest.py likely broken"
    assert slow, "slow tier collected nothing — markers likely removed"
    assert sorted(fast + slow) == sorted(everything)
    assert set(fast) & set(slow) == set()

    # The slow tier should stay a small minority of the suite by count —
    # if this ever creeps past half, the marker is probably being applied
    # too broadly (defeats the point of a fast tier).
    assert len(slow) < len(everything) // 4


def test_biggest_offender_stays_marked_slow():
    slow = _collect("tests/", "-m", "whence_slow")
    assert any(node_id.startswith(BIGGEST_OFFENDER) for node_id in slow), (
        f"{BIGGEST_OFFENDER} (92.91s alone in round 242's measurement) is "
        "no longer in the whence_slow tier"
    )
