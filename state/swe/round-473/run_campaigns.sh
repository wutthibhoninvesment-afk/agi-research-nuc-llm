#!/usr/bin/env bash
# Round 473 (SWE-loop D): the four per-test falsification audits.
#
# SERIAL on purpose — `nproc` on this box is 1 and every band in
# state/swe/round-473/PREDICTIONS.md §0.4 is declared for a solo run.
# Each unit pairs a subject module with the test file that claims to be
# about it; the pairing is what bounds the `never_red` claim (see
# harness/swe/falsifiers.py, bound 1).
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
OUT=state/swe/round-473
PY=.venv/bin/python3

run() {  # run <unit> <subject> <tests> [extra...]
  local unit=$1 subject=$2 tests=$3; shift 3
  echo "=== $unit  $(date -u +%H:%M:%S) ==="
  /usr/bin/time -f "%e s wall  ($unit)" \
    $PY harness/swe/falsifiers.py audit \
      --unit "$unit" --subject "$subject" --tests "$tests" \
      --timeout-s 60 --quiet --json "$OUT/$unit.json" "$@"
  echo "rc=$?"
}

run scoreaudit harness/swe/scoreaudit.py  harness/tests/test_swe_scoreaudit.py
run tierbudget harness/tierbudget.py      harness/tests/test_tierbudget.py
run whenceslow harness/whenceslow.py      harness/tests/test_whenceslow.py
run redattrib  harness/redattrib.py       harness/tests/test_redattrib.py --sample 200
echo "=== done $(date -u +%H:%M:%S) ==="
