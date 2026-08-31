#!/usr/bin/env bash
# Fast, synchronous smoke suite for the agent-harness core: every
# harness/tests/*.py file EXCEPT the test_swe_*.py files that are still in
# the slow tier (real-interpreter-driven, slow by construction — see
# harness/tests/conftest.py and knowledge/round-235-*.md).
#
# Round 385 (harness A): "still in" is now a MEASURED distinction, not a
# filename. Round 235 tiered every `test_swe_*.py` file slow on the strength
# of a seven-row cost table it quoted out of rounds 193-221 rather than
# measured; 150 rounds later most of that tier is cheap. `harness/
# tierbudget.py measure` times each file alone under a cap, and
# `harness/tier-budget.json` promotes the measured-cheap, measured-green
# ones into this suite. The rule is fail-closed — a file absent from the
# registry is slow, so a new test_swe_*.py file still tiers itself with no
# edit anywhere — and every promoted file is re-timed for free by this very
# run, which prints a `tier-budget:` line just above pytest's count line.
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

# Round 379 (harness A): mark where THIS run's output ends, before anything
# recorded earlier is echoed below. Two readers need the boundary:
#
#  - `driver_health.classify_health_log`, which quotes a health log's last
#    line into `driver.log`. From round 341 (the slow-tier echo) to round
#    378, every one of the 38 `health-check` lines quoted an echo instead of
#    the suite's own result — 18 of them quoted a RECORDED FAILURE under the
#    word PASS, and 6 quoted a pristine-differential row measured once, at
#    round 373, at a commit the tree had since left.
#  - a human. Round 374 read `health-check PASS (whence-slow clean ...
#    1014.6s)` in driver.log and concluded from it that "the driver's
#    whence-slow health check runs a PRISTINE checkout of HEAD" every round.
#    It does not; the driver runs three FAST suites on the live tree and
#    never invokes pristine_check.py at all. That inference became round
#    375's next-steps item 3 and was carried by two rounds.
#
# The string is defined in `harness/driver_health.py` as
# `MEASURED_END_SENTINEL` and a test asserts it appears here, so the printer
# and the parser cannot drift apart.
echo
echo "--- end of measured output; recorded status below ---"

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

# Round 355 (harness A): and the RECORDED status of the pristine-checkout
# differential, for the same reason and at the same price (one JSONL read).
# The gap it covers is one level up from the slow tier's: every result above
# is measured in THIS working tree, which is not the repo — it also holds
# untracked files, 14 of them written by a separate autonomous system. Round
# 355 found `languages/whence/tests/test_lexer_guest_parity.py` had required
# those files to exist since round 350, so a fresh clone failed the suite
# while every round reported green. `pristine_check.py check` is the real
# run (a second full suite in a `git worktree`, minutes); this line is only
# its last recorded verdict, and prints "no recorded check" — never "pass" —
# when there isn't one.
echo
python3 harness/pristine_check.py status || true

# Round 403 (harness A): and whether a PREVIOUS round left a suite RUNNING.
# One `/proc` walk, milliseconds, and DIAGNOSTIC ONLY (`|| true`, `rc` is
# still the fast tier's).
#
# The gap this closes is not hypothetical and not old. Round 402 left two
# full suites running past its own commit; round 403 found them 27 minutes
# later still holding this box's single CPU, and one of them had written an
# `F` to a log whose path round 402 recorded nowhere. That `F` was a real
# regression — a stale `whence_slow` count pin in
# `languages/whence/tests/test_self_hosting.py` — which the fast tier
# deselects and which the full tier had not caught in twelve rounds.
#
# `scan` keys on cwd, not argv: every suite this program runs has the same
# argv, so argv cannot tell them apart. Our own driver -> wrapper -> claude
# chain is excluded by ancestry, so a quiet box prints `verdict=clean`
# rather than six lines of ourselves.
echo
python3 harness/procreap.py scan --no-record || true

exit $rc
