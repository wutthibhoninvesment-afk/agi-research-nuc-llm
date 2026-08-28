#!/usr/bin/env bash
# Fast, synchronous smoke suite for the agent-harness core: every
# harness/tests/*.py file EXCEPT harness/swe/'s test_swe_*.py (real-
# interpreter-driven, slow by construction — see harness/tests/conftest.py
# and knowledge/round-235-*.md). Confirmed 367 tests / ~45s on this host,
# vs. 30+ minutes for the full suite including test_swe_*.py.
#
# Run this every round that touches harness/ core code (agent loop, tool
# registry, driver, retry/backoff, driver_health) for a complete pass/fail
# signal that actually finishes inside a round's time budget. It does NOT
# replace a full `pytest harness/tests/` run when SWE-loop(D) or the
# harness/swe/ subsystem itself changed — that still needs the slow tier
# (background it, per the standing `nohup ... &` convention).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec python3 -m pytest -q -m "not swe_slow" harness/tests/ "$@"
