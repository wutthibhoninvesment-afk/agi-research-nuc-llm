#!/usr/bin/env bash
# Round 469 (harness A). The SIXTH per-round driver check, and the second
# that MEASURES rather than reports.
#
# Why this exists
# ---------------
# `languages/whence/run_tests_fast.sh` — the driver's per-round
# `whence-health-check` — ends in `-m "not whence_slow"`. That deselects 103
# test nodes across 27 files, and until round 469 NOTHING ran them:
#
#   * no module under `harness/` selected tests by the marker (`slowtier.py`
#     filters on the filename prefix `test_swe_` and is about
#     `harness/tests/` alone);
#   * `pristine_check.py` defines a `whence-slow` SUITE, and `run_driver.sh`
#     invokes `pristine_check.py` on no code path, so that runner is manual;
#   * it had been run TWICE, both on 2026-08-30, both recorded in
#     `state/pristine-check-ledger.jsonl`.
#
# Round 469 built `harness/whenceslow.py` — the ledger, the fail-closed
# classifier and the planner — and then measured the thing that decides
# whether a ledger is enough: over the last 120 commits that touch a
# `.py`/`.lang` source under `languages/whence/`, **80 touch the interpreter,
# `run.py` or `examples/`**. Two thirds of commits legitimately invalidate
# every unit's freshness, whatever the digest rule is. So no key, however
# fine, raises this tier's recall above ~0. The only thing that does is
# taking the measurement more often, which is this script.
#
# That is round 439's lesson applied a second time: reporting a gap never
# closes one. `slowtier status` printed 0% for 99 rounds before round 439
# wired a slice; shipping `whenceslow status` without this would have
# reproduced that exactly, in a round whose own finding is that it does not
# work.
#
# Design, deliberately identical to round 439's:
#   * DIAGNOSTIC ONLY. Never blocks, never stops the driver, always exits 0.
#     `whenceslow run` exits non-zero when a unit goes red, and a red unit is
#     the finding a later round should FIX, not a reason to halt.
#   * Guarded on existence at the call site, so a workspace with no whence
#     tree degrades to not running it.
#   * Bounded. `DRIVER_WHENCESLOW_BUDGET_S` (default 120) is the planner's
#     budget, not a timeout: `plan()` picks whole units whose measured cost
#     fits, worst-evidence-first, and returns a single over-budget unit only
#     when nothing else fits (its own no-silent-truncation rule). The WORST
#     CASE is therefore the largest single unit, which round 469 measured —
#     see `state/whence-slow-ledger.jsonl` — not 120 s. Capping it with an
#     outer `timeout` would kill a unit mid-run, and `run_slice` stamps a
#     killed run `completed: false`, which narrows nothing; the tier's most
#     expensive units would become the exact ones that can never be evidence.
#   * SEQUENTIAL, after the slow-tier slice, never beside it. `nproc` is 1
#     here. Two pytest processes at once each take roughly twice their solo
#     time (round 434 measured it by accident), and both slices write a
#     `seconds` field their planners read back as a cost estimate — a number
#     inflated by our own concurrency would re-order every future plan in
#     BOTH tiers.
#
# THE COST IS NOT SILENT. With the slow-tier slice's 240 s default this makes
# the driver's per-round measured budget 360 s, not 240. Set
# DRIVER_WHENCESLOW_BUDGET_S=0 to skip the slice and print the recall line
# alone; that is the off switch, and it keeps the number in the log so
# turning it off stays visible.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

BUDGET="${DRIVER_WHENCESLOW_BUDGET_S:-120}"

if [ "$BUDGET" = "0" ]; then
  echo "whenceslow-slice: SKIPPED (DRIVER_WHENCESLOW_BUDGET_S=0)"
else
  python3 harness/whenceslow.py run --budget-s "$BUDGET" || true
fi

# The status SUMMARY line last, so the driver's `tail -n 1` and a human both
# read the recall AFTER the slice this run paid for. `sed -n 1p`, not
# `tail -n 1`: `report_text` puts the summary FIRST and a per-unit table
# after it. `|| true`: `status` exits 1 when a unit is failing, which is a
# finding, not a check failure.
python3 harness/whenceslow.py status | sed -n '1p' || true
exit 0
