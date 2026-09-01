# Round 433 (harness A) — predictions, banked BEFORE measuring (D-013)

Subject: round 432's next-steps item 3 — "`harness/tests/test_swe_campaign.py::
test_cli_runs_offline_stages_and_stops` ... needs a slow marker so it stops being
run inside a round's turn budget by accident. harness(A) or SWE-loop(D)."

Baseline numbers this bank opens with, each with the command that produced it
(round 432's next-step item 4: a bank must DERIVE its baselines, not quote them):

  $ python3 harness/swe/slowtier.py status | head -1
    slow tier: 31 files, 0 conclusive against checkout e937b353705e9381
    (0% recall), 0 failing
  $ python3 -c "import json;d=json.load(open('harness/tier-budget.json'));
    print(len(d['promoted']), 'test_swe_campaign.py' in d['promoted'])"
    15 False
  $ grep -c '^def test_' harness/tests/test_swe_campaign.py
    20
  $ wc -l < state/slow-tier-ledger.jsonl
    26

## Predictions

**A1.** The remedy item 3 asks for is ALREADY IN PLACE. `test_swe_campaign.py`
matches `SLOW_PREFIX = "test_swe_"` and is absent from `tier-budget.json`'s
`promoted`, so `conftest.py` already marks every test in it `swe_slow` and
`run_tests_fast.sh`'s `-m "not swe_slow"` already deselects it. Adding a marker
changes nothing. HIT iff a live `--collect-only -m "not swe_slow"` run collects
0 tests from that file.

**A2.** The ledger has NEVER held an entry for `test_swe_campaign.py`, and holds
NO entry with `outcome: "timeout"` at all. HIT iff both counts are 0.

**A3.** `plan(status, budget_s=900)` does not pick `test_swe_campaign.py`.

**A4.** `test_cli_runs_offline_stages_and_stops` does NOT complete within a
600 s cap, run alone in a fresh process.

**A5.** Exactly ONE of the 20 tests in the file costs more than 120 s. The
other 19 are each under 120 s.

**A6.** The other 19 tests, run together as one pytest process, complete in
under 600 s.

**A7.** The per-test floor is the `checkout` fixture (`_copy_project` of the
whole whence tree, once per test). I predict a single `_copy_project` costs
between 2.0 s and 8.0 s on this box, so the 19-test complement's cost is
FIXTURE-dominated: fixture copies account for >50% of its wall clock.

**A8.** The gap is not unique to this file. At least one OTHER slow-tier file
that is `unknown` today also has a single test costing >50% of the file.
(Weak prior; stated so a miss is recorded.)

**A9.** Mechanism prediction. After splitting the file into a declared-heavy
unit and its complement, `slowtier status` will report MORE units than files
(32 units vs 31 files) and recall will be computed over units. Declaring a
heavy test can only ever LOWER a file's contribution to recall on the run it
is declared, never raise it — the fail-closed direction, mirroring
`tierbudget.py`'s.

**A10.** A whole-file ledger entry with `outcome: "passed"` IS sound evidence
for every sub-unit of that file (the run is a superset). A whole-file entry
with `outcome: "failed"` is NOT, because the failure cannot be attributed.
I predict no existing code path in `slowtier.py` encodes that asymmetry today
(there are no sub-units yet), so it has to be written and tested.
