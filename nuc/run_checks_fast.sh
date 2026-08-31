#!/usr/bin/env bash
# Fast, synchronous check for nuc/ — the FOURTH per-round health check,
# alongside round 241's harness/run_tests_fast.sh, round 247's
# languages/whence/run_tests_fast.sh and round 363's skills/run_checks_fast.sh.
#
# Round 388 (NUC-integration E). Round 382's handoff item 4 asked for
# `nuc/constant_audit.py` to run in a health check: "it is offline, under a
# second, and `test_the_live_nuc_tree_has_no_transform_risk` is the only thing
# currently making it run." That understates the gap by a factor of the whole
# subsystem. NOTHING under nuc/ runs outside an E round — not the 483 offline
# tests, not the five instruments (reachability_check, expert_cache, fast_lane,
# swap_watch, taskscript), not the audit. Detection latency for a break in any
# of them is bounded by the rotation: E comes round every SIXTH round, so a
# regression introduced by a language(C) or harness(A) round can sit green-
# looking for five rounds and then surface inside an E round that has a live
# box, a time budget, and something else to do. That is exactly round 363's
# argument for skills/, one track over.
#
# Everything here is OFFLINE by construction:
#   * `nuc/tests/` injects fake `ssh_runner`/`tailscale_runner`/`now_fn` into
#     `reachability_check` (round 334) and never opens a socket. No ssh, no
#     engine contact, and in particular no possibility of touching port 8001.
#   * `constant_audit.py` reads .py files with `ast` and nothing else.
# Wall cost measured on this box, round 388: 65.6 s total (490 tests + audit).
# That is roughly double the 30 s the suite takes alone, and the doubling is
# deliberate and self-inflicted: `test_the_fast_check_runs_green_on_this_tree`
# invokes this script end-to-end, so the pytest leg runs twice — once nested
# (guarded by NUC_FAST_CHECK_NESTED, which is what stops it recursing) and once
# outside. The alternative is an unexercised FAIL path in the one check whose
# last line the driver quotes; round 379 spent 38 driver rounds quoting the
# wrong line for exactly that reason. Cost stated, not hidden: it is the
# slowest of the four health checks (harness 34-45 s, whence 23 s, skills <3 s).
#
# Diagnostic-only, exactly like the other three: it logs a verdict, never
# blocks and never stops the driver — a broken check can itself be the NEXT
# round's legitimate fix target.
#
# Exit code is driven by ERRORS ONLY (a red test, or an audit
# `transform_risk`), never by the audit's `bare`-grade findings. Four of the
# tree's 19 size constants are legitimately bare — `DEFAULT_PAGE_BYTES = 4096`
# is not going to become derived — and a check that goes FAIL every round for a
# state the program has decided to keep gets ignored and then uninstalled.
# That is skills/run_checks_fast.sh's stated reason for the same split, and
# skill-authoring's own pitfall.
#
# NOT wired into run_driver.sh by this round, on purpose and by precedent:
# round 242 (language C) built `languages/whence/run_tests_fast.sh` and left
# the driver edit to round 247 (harness A), because the health-check block —
# its concurrency, its PID handling, its guarded-on-existence contract — is
# harness(A)'s artifact. Same handoff here. The wiring is four lines in the
# round-277 concurrent block plus a `nuc-health-check` log line and its own
# per-round log file, mirroring the whence check exactly.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

rc=0

set +e
python3 -m pytest -q nuc/tests/ "$@"
pytest_rc=$?
set -e
if [ $pytest_rc -ne 0 ]; then rc=1; fi

echo
set +e
audit_json=$(python3 nuc/constant_audit.py audit nuc/ --json)
audit_rc=$?
set -e

# `set +e` around the assignment is load-bearing: under `set -e` a command
# substitution that exits non-zero aborts the script AT the assignment, so the
# FAIL path would kill the check before it could print why. Verified both ways
# in round 388 (see `test_the_fast_check_reports_fail_on_a_transform_risk`).
set +e
summary=$(printf '%s' "$audit_json" | python3 -c '
import json, sys
try:
    s = json.load(sys.stdin)["summary"]
except Exception as exc:                     # a broken audit is a FAIL, loudly
    print(f"constant-audit PARSE-ERROR ({exc})"); raise SystemExit(2)
print("constant-audit {} constants, {} derived ({:.3f}), {} bare, {} transform-risk".format(
    s["n"], s["by_grade"].get("derived", 0), s["derived_fraction"],
    s["by_grade"].get("bare", 0), s["transform_risk"]))
raise SystemExit(1 if s["transform_risk"] else 0)
')
summary_rc=$?
set -e
echo "$summary"
if [ $summary_rc -ne 0 ] || [ $audit_rc -ne 0 ]; then rc=1; fi

echo "nuc-checks $([ $rc -eq 0 ] && echo PASS || echo FAIL) (pytest rc=$pytest_rc, audit rc=$audit_rc)"
exit $rc
