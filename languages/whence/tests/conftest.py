"""Auto-registers the `whence_slow` marker (round 242) and fixes up
sys.path so `tests/` can `import whence` from a bare checkout with no
install step.

`whence_slow` is hand-placed on the ~35 individual test functions (out of
875) that dominate this suite's wall-clock — measured live via
`pytest --durations=0` (round 241: 875 tests / 404.61s total; the top 2
alone, `test_v10.py::test_three_way_on_big_examples[meta.lang]` and
`test_v09.py::test_three_way_on_examples_that_recurse`, are 92.91s+71.19s,
40% of the whole suite by themselves). Unlike harness/tests/'s
`test_swe_*.py` filename convention (round 235), Whence's slow tests are
scattered across shared, version-numbered files (test_v09.py, test_v10.py,
test_self_hosting.py, ...) that also hold plenty of fast tests, so there is
no filename prefix to key off — the marker has to sit on the individual
`def test_...():` line. Run `run_tests_fast.sh` (or
`pytest -m "not whence_slow" tests/`) for a synchronous, complete signal
that finishes in seconds instead of ~7 minutes; a bare `pytest tests/`
still runs everything, unchanged. See knowledge/round-242-whence-tests-
fast-slow-tiering.md for the full derivation and the regenerate recipe.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "whence_slow: individually-marked slow test (self-hosting/guest-"
        "evaluator/three-way-differential/bench-in-fresh-process) — real "
        "cost from running the actual interpreter over large programs, not "
        "a flake. Deselect with `-m \"not whence_slow\"` for a fast smoke "
        "run (see run_tests_fast.sh).",
    )
