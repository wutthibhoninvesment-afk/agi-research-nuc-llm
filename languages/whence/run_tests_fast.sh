#!/usr/bin/env bash
# Fast, synchronous smoke suite for languages/whence: every tests/*.py test
# EXCEPT the ~35 individually marked `whence_slow` ones (self-hosting/guest-
# evaluator/three-way-differential/bench-in-fresh-process — real cost from
# running the actual interpreter over large programs, not a flake). See
# tests/conftest.py and knowledge/round-242-whence-tests-fast-slow-tiering.md.
#
# Confirmed ~840 tests / a few seconds on this host, vs. 875 tests / 404.61s
# (~6:45) for the unfiltered suite (round 241's own measurement).
#
# Run this every round that touches whence/ core code (lexer, parser,
# interp, values) for a complete pass/fail signal that actually finishes
# inside a round's time budget. It does NOT replace a full
# `pytest tests/` run when self_eval.lang/self_host.lang or the guest-
# evaluator dispatch tables changed — background that (`nohup ... &`,
# the standing convention since round 227) instead.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
exec python3 -m pytest -q -m "not whence_slow" tests/ "$@"
