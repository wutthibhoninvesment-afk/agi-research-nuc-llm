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
#
# ---------------------------------------------------------------------------
# Round 442 (NUC-integration E): INTERPRETER RESOLUTION, and why it is here.
#
# This check reported FAIL on every round from 410 (when it was wired in) to
# 441. Thirty-two consecutive rounds; `grep "nuc-health-check PASS"
# logs/driver.log` returned nothing at all. It never had a green baseline, so
# nobody could tell "still broken" from "newly broken", which is the entire
# service a health check provides. Five track-E rounds (412, 418, 424, 430,
# 436) ran during that window and none of their knowledge files mentions it.
#
# The cause was not a bug in nuc/. It was that the check and the ROUND ran
# under DIFFERENT PYTHON INTERPRETERS:
#
#   * `claude-wrapper.sh` does `source .venv/bin/activate`, so every round —
#     and therefore every `pytest nuc/tests` a round types by hand — runs
#     under `.venv/bin/python3`, which has `tokenizers==0.23.1`.
#   * `run_driver.sh` never activates the venv. It only appends
#     `node_modules/.bin` to PATH, and it launches the four health checks from
#     its own shell. The live driver process carries `VIRTUAL_ENV` pointing at
#     `.venv` with NO `.venv/bin` on PATH — a half-activated venv — so bare
#     `python3` here resolved to `/usr/bin/python3`, which has pytest 9.1.1
#     and no `tokenizers`.
#
# Measured round 442: `pytest nuc/tests` is 794 passed / 0 failed under the
# venv and 2 failed / 787 passed / 5 skipped under /usr/bin/python3. Same
# tree, same pytest version, same Python 3.12.3 — different answer. A check
# that measures an interpreter no round ever runs is not measuring this
# program, so it resolves the interpreter itself rather than inheriting
# whatever PATH the caller happened to have.
#
# Preference order, and each step is deliberate:
#   1. `$NUC_CHECK_PYTHON` if set — an explicit override, which is also how
#      `nuc/tests/test_run_checks_interpreter.py` exercises both branches
#      without needing two interpreters to exist.
#   2. the repo's own `.venv/bin/python3` — the interpreter rounds use, and
#      the one `nuc/prompt_budget.py`'s docstring has named since round 22
#      ("run under the hermes venv python, which has `tokenizers`").
#   3. bare `python3` — for any checkout with no `.venv`.
# A candidate is only accepted if it can `import pytest`; otherwise the next
# one is tried. Trading "red because tokenizers is missing" for "red because
# pytest is missing" would be no improvement.
#
# The choice is EXPORTED, so the nested run that
# `test_the_fast_check_runs_green_on_this_tree` spawns inherits it instead of
# re-resolving and possibly disagreeing with its parent. Before this round
# that test genuinely returned different answers depending on which shell
# started it: green from inside a round, red from the driver.
#
# This is NOT the whole defect. All four health checks
# (`harness/run_tests_fast.sh`, `languages/whence/run_tests_fast.sh`,
# `skills/run_checks_fast.sh` and this one) call bare `python3` and are
# exposed identically; nuc/ is simply the only one with a venv-only import,
# so it is the only one that ever went red. The general fix belongs in
# `run_driver.sh`, which is harness(A)'s artifact — same handoff round 388
# made when it built this script and left the driver wiring to round 409.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# A candidate must PRINT the sentinel, not merely exit 0. `[ -x ]` plus a
# zero exit status is not enough: /bin/true is executable and exits 0 for any
# argv, so an exit-status-only test accepts it as a Python interpreter and the
# check then fails with something far more confusing than what it replaced.
_usable() {
  [ -n "$1" ] && [ -x "$1" ] || return 1
  [ "$("$1" -c 'import pytest; print("nuc-ok")' 2>/dev/null)" = "nuc-ok" ]
}

NUC_PY=""
for _cand in "${NUC_CHECK_PYTHON:-}" "$PWD/.venv/bin/python3" "$(command -v python3 || true)"; do
  if _usable "$_cand"; then NUC_PY="$_cand"; break; fi
done
if [ -z "$NUC_PY" ]; then
  echo "nuc-checks interpreter: NONE USABLE (no python3 with pytest)"
  echo "nuc-checks FAIL (pytest rc=None, audit rc=None)"
  exit 1
fi
export NUC_CHECK_PYTHON="$NUC_PY"

if "$NUC_PY" -c "import tokenizers" >/dev/null 2>&1; then _tok=present; else _tok=absent; fi
echo "nuc-checks interpreter: $NUC_PY (tokenizers $_tok)"

rc=0

set +e
"$NUC_PY" -m pytest -q nuc/tests/ "$@"
pytest_rc=$?
set -e
if [ $pytest_rc -ne 0 ]; then rc=1; fi

echo
set +e
audit_json=$("$NUC_PY" nuc/constant_audit.py audit nuc/ --json)
audit_rc=$?
set -e

# `set +e` around the assignment is load-bearing: under `set -e` a command
# substitution that exits non-zero aborts the script AT the assignment, so the
# FAIL path would kill the check before it could print why. Verified both ways
# in round 388 (see `test_the_fast_check_reports_fail_on_a_transform_risk`).
set +e
summary=$(printf '%s' "$audit_json" | "$NUC_PY" -c '
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

# ---------------------------------------------------------------------------
# Round 460 (NUC-integration E): the strict instruments, as a DIAGNOSTIC line.
#
# `reachability_check.py` ships three checks with a `--strict` mode whose whole
# purpose is to exit non-zero, and NOTHING runs them. They run when an E round
# remembers to type them, which is every sixth round at best -- round 454 built
# `coverage --strict` and called it "the enforcer the rule never had", and it
# has no enforcer of its own. Round 460 measured the cost of that: `lastseen-
# drift --strict` has been exiting 1 since round 448 introduced it, and no
# round file says so, because nothing asked.
#
# Printed, NOT folded into `rc`, and that is deliberate on two counts:
#
#   1. The `nuc-checks ... (pytest rc=N, audit rc=N)` line below is PARSED by
#      `harness/driver_health.py` and pinned by `harness/tests/
#      test_nuc_health_line.py`. Flipping it to FAIL while it still reports
#      only two of three exit codes would make the driver's summary say
#      something untrue. Widening it is harness(A)'s artifact -- the same
#      handoff this file's header makes twice already (round 388 -> 409 for the
#      driver wiring, round 442 for the general interpreter fix).
#   2. `lastseen-drift` going red is NOT a break. Round 448 established that
#      tailscale recomputes `LastSeen`, and the check reports that fact. A
#      health check that goes FAIL every round for a state the program has
#      decided to keep gets ignored and then uninstalled -- this file's own
#      header says so about `constant_audit`'s bare grade.
#
# So: make it visible every round, let the round that widens the contract
# decide which of the three belong in the exit code. `coverage` and
# `precision-audit` are the two that mean "a published conclusion is wrong";
# `lastseen-drift` means "the field moved again".
set +e
_cov=$("$NUC_PY" nuc/reachability_check.py coverage --strict >/dev/null 2>&1; echo $?)
_prec=$("$NUC_PY" nuc/reachability_check.py precision-audit --strict >/dev/null 2>&1; echo $?)
_drift=$("$NUC_PY" nuc/reachability_check.py lastseen-drift --strict >/dev/null 2>&1; echo $?)
set -e
echo "nuc-instruments coverage=$_cov precision-audit=$_prec lastseen-drift=$_drift (diagnostic only, not in the exit code)"

echo "nuc-checks $([ $rc -eq 0 ] && echo PASS || echo FAIL) (pytest rc=$pytest_rc, audit rc=$audit_rc)"
exit $rc
