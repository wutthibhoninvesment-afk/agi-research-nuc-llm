#!/usr/bin/env bash
# Round 439 (harness A). The FIFTH per-round driver check, and the first one
# that MEASURES instead of reporting.
#
# Why this exists
# ---------------
# `harness/run_tests_fast.sh` has ended with `slowtier status` since round
# 341, so every round's driver log has carried the slow tier's recall — and
# every round it said the same thing, because nothing ever ran a slice. At
# round 439 the line read:
#
#   slow tier: 31 files / 32 units, 0 conclusive against checkout <d> (0% recall), 0 failing
#
# 0%. Twenty units had never been run at all and twelve carried a `stale_*`
# verdict 62-75 hours old. `run_tests_fast.sh`'s own header names the fix
# ("Use `python3 harness/swe/slowtier.py run --budget-s N` instead") and no
# round wired it, because each round's share of the cost is real and the
# benefit lands on some later round.
#
# What round 439 measured is what changes the trade. The tier's 0% recall was
# not merely failing to catch NEW breakage; it was failing to RETIRE fixed
# breakage. Two harness reds sat on this program's open list — the campaign
# suite's `test_review_stage_and_report` and verb_audit's V002 — both fixed
# by round 437, both re-listed as open by rounds 438/439's carry list,
# because retiring a red requires re-running it and nothing re-runs the slow
# tier on a schedule. A red that nobody can retire costs every subsequent
# round the wall clock to re-derive it, which is strictly more than the
# budget below.
#
# Design, deliberately identical to rounds 241/247/363's three checks:
#   * DIAGNOSTIC ONLY. Never blocks, never stops the driver, always exits 0.
#     `slowtier run` exits non-zero when a slice goes red, and a red slow
#     unit is exactly the finding a later round should FIX, not a reason to
#     halt the program.
#   * Guarded on existence at the call site, so a workspace with no harness
#     tree degrades to not running it.
#   * Bounded. `DRIVER_SLOWTIER_BUDGET_S` (default 240) is the planner's
#     budget, not a timeout: `plan()` picks whole units whose measured cost
#     fits, worst-evidence-first, and returns a single over-budget unit only
#     when nothing else fits (its own no-silent-truncation rule). So the
#     WORST CASE is not 240 s but the largest single unit in the tier — 873 s
#     for `test_swe_alias_effects.py`, measured round 341 — on the rounds
#     where nothing cheaper is stale. That is deliberate and it is the
#     cheaper error: capping it with an outer `timeout` would kill a unit
#     mid-run, and a killed run writes no ledger entry at all (rule 10: an
#     incomplete run may not narrow anything), so the tier's most expensive
#     units would be the exact ones that could never become evidence.
#   * SEQUENTIAL, not concurrent with the other four. `nproc` is 1 on this
#     box; round 434 ran two pytest processes at once by accident and each
#     took roughly twice its solo time. A slice that runs beside the three
#     suites would both mis-measure itself and inflate their numbers, and
#     the ledger's `seconds` field is read back by `plan()` as a cost
#     estimate — a number inflated by our own concurrency would re-order
#     every future plan.
#
# Set DRIVER_SLOWTIER_BUDGET_S=0 to skip the slice entirely and print the
# status line alone; that is the off switch, and it keeps the recall number
# in the log so turning it off stays visible.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

BUDGET="${DRIVER_SLOWTIER_BUDGET_S:-240}"

if [ "$BUDGET" = "0" ]; then
  echo "slowtier-slice: SKIPPED (DRIVER_SLOWTIER_BUDGET_S=0)"
else
  python3 harness/swe/slowtier.py run --budget-s "$BUDGET" || true
fi

# The status SUMMARY line last, so the driver's `tail -n 1` and a human both
# read the recall AFTER the slice this run paid for. `sed -n 1p`, not
# `tail -n 1`: `report_text` puts the summary FIRST and a per-unit table
# after it, so tailing this would log "NOTE: 32 unit(s) are NOT evidence"
# every round and never the number that moves. `|| true`: `status`
# exits 1 when a unit is failing, which is a finding, not a check failure.
python3 harness/swe/slowtier.py status | sed -n '1p' || true
exit 0
