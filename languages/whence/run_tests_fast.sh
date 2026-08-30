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
#
# Round 349 (harness A): `-c pytest.ini` is LOAD-BEARING, not cosmetic.
# Without it pytest discovers config by scanning the rootdir, which means
# it parses `languages/whence/pyproject.toml` — an UNTRACKED file owned by
# a separate system (allowlisted in state/known-standing-dirty-paths.json
# since round 291). Round 348 that file grew a duplicate
# `[project.optional-dependencies]` table; the TOML parse error aborted the
# run before collection and took all 1043 fast-tier tests down, and the
# driver logged `whence-health-check FAIL` for a breakage that had nothing
# to do with any test. `-c` makes pytest use the named file and stop
# scanning. Verified round 349 against the still-broken pyproject.toml:
# `-c pytest.ini` collects 1043/1095, plain discovery hard-errors,
# `--rootdir=` alone does NOT help (pytest still parses pyproject.toml).
exec python3 -m pytest -c pytest.ini -q -m "not whence_slow" tests/ "$@"
