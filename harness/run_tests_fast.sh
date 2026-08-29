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
# harness/swe/ subsystem itself changed — that still needs the slow tier.
#
# Round 341: do NOT reach for the standing `nohup ... &` convention for
# that. On this one-CPU box the slow tier outlives its own round, and the
# NEXT round is routinely a language(C) one editing `languages/whence/`
# underneath it — which silently invalidates the result (four of round
# 338's five slow-tier failures are that race, not real bugs). Use
# `python3 harness/swe/slowtier.py run --budget-s N` instead: it runs a
# bounded slice INSIDE the round, records each outcome against the
# checkout digest it was computed against, and refuses to count any
# result whose checkout moved mid-run.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

set +e
python3 -m pytest -q -m "not swe_slow" harness/tests/ "$@"
rc=$?
set -e

# Round 341 (SWE-loop D): print the slow tier's RECORDED status after the
# fast run. Round 338's item 1 named the real problem — deselecting the
# slow tier means a green round report is not evidence about it, the same
# coverage-gap shape as round 283's `git_committed` gap — and named this
# as the fix that matters more than either of the five failures it found:
# "a periodic full run whose result is RECORDED, not an orphaned
# background process nobody reads."
#
# Cheap by construction (reads one JSONL and digests ~20 `.py` files,
# milliseconds), and DIAGNOSTIC ONLY: `rc` is still the fast tier's own
# exit code, because a stale or failing SLOW-tier file must not relabel
# the FAST tier's result. `|| true` keeps `slowtier status`'s own non-zero
# "there are fresh failures" exit from leaking into it.
echo
python3 harness/swe/slowtier.py status || true

exit $rc
