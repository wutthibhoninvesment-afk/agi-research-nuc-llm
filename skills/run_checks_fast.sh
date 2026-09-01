#!/usr/bin/env bash
# Fast, synchronous corpus check for skills/ — the THIRD per-round health
# check, alongside round 241's harness/run_tests_fast.sh and round 247's
# languages/whence/run_tests_fast.sh.
#
# Round 363 (skills B). Both existing health checks read code trees; neither
# reads skills/. The corpus's checkers — skill_lint, case_coverage,
# claim_check, state_claim_check, xref_check, carryforward_check (round 369),
# verb_audit (round 423) and placeholder_check (round 429) — are all offline
# and all free, and until this file NOTHING RAN ANY OF THEM outside a
# skills(B) round. This comment said "six" and named the first six for two
# checkers' worth of drift; `corpus_check.checks()` is the list, this is a
# gloss, and round 429 stopped it claiming a count of its own. Detection latency for a corpus violation was therefore bounded by
# the rotation: up to six rounds.
#
# The measurement that justifies it (corpus_history.py, replaying every
# commit that touched skills/ against that commit's OWN checkers):
#
#   under the rules of the day   ERROR-red   2 of 59 commits, one episode,
#                                            open at HEAD when this was written
#                                strict-red 15 of 59, one episode (B002),
#                                            knowingly carried, closed on purpose
#   under today's rules          ERROR-red  44 of 59 commits, FOUR episodes
#
# The four episodes are the argument. Three of them are the same shape — a
# non-skills(B) round adds a skill with no trigger cases (P001) — opened by
# rounds 342, 354 and 361, closed by rounds 351, 357 and 363. Gaps of 9, 3
# and 2 rounds. Violations are RARE under the rules of the day; the debt that
# BECOMES one recurs every few rounds, and the rotation was the only detector.
#
# Diagnostic-only, exactly like the other two: it logs a verdict, never blocks
# and never stops the driver — a broken check can itself be the NEXT round's
# legitimate fix target.
#
# The exit code is driven by ERRORS ONLY, never warnings. In this repo a
# warning has meant a deliberately carried debt (B002's 415-line body, carried
# on purpose for eight skills(B) rounds), and a check that goes FAIL every
# round for a debt the program has decided to carry gets ignored and then
# uninstalled — skill-authoring's own pitfall, and case_coverage.py's own
# stated reason for splitting P001/P002 from P004. The warning COUNT rides in
# the summary line, which is the line run_driver.sh logs.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec python3 skills/skill-authoring/scripts/corpus_check.py "$@"
