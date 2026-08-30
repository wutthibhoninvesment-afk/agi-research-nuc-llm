# Round 375 (skills B) — predictions, banked BEFORE measuring (rule D-013)

Subject: **round 369's own parting finding — `case_coverage.py`'s P004 keys
on FRESHNESS, not on the RESULT.** A skill whose newest probe found it 0
times out of 3 reads `probed` in every corpus check, and the headline
*"35 probed under the description on disk"* is true and much weaker than it
reads.

The reports needed to answer "did the probe PASS" are already committed
under `state/trigger-eval/` — every result carries `expect` and `fired`. So
the outcome half is FREE, exactly as the coverage half was, and nothing
reads it.

## Already known before these predictions were written
Not scored. From round 369's `state/research-state.md` entry and its
knowledge file, read while picking this round's subject:
- Round 369 probed `measured-budget-sizing` at **0/3** and the new
  `obligation-ledger` at **1/3**, edited both descriptions, re-probed 6
  cases, and neither edit helped (mbs unchanged; ol 1/3 -> 0/3). Round 141's
  stop-rule applied: no third edit, both kept, neither claimed validated.
- `policy-replay-over-history` scored **3/4 recall, 100% precision**.
- The current corpus check reports 36 skills, 142 cases (26 negative), 35
  probed under the description on disk, 0 errors.
- `state/known-unprobed-skills.json` is EMPTY (round 369 paid both entries).

## Predictions

**P1 — the gap is total, not partial.** No existing test in
`skills/skill-authoring/scripts/test_case_coverage.py` or
`test_trigger_eval.py` asserts anything about a probe's RECALL as opposed to
its freshness. Scored on: grep for an assertion over `fired` vs `expect` in
the audit path.

**P2 — more than two skills are affected.** Scoring each skill against its
newest probing report, **at least 8 of the 36** have recall < 100%.

**P3 — at least one zero is not one of round 369's two.** At least one skill
whose newest probing report fires it on ZERO of its expected cases is
neither `measured-budget-sizing` nor `obligation-ledger`.

**P4 — aggregate recall lands in 60–85%.** Over every skill's newest probing
report, (cases where the skill fired) / (cases expecting it) is between 0.60
and 0.85 inclusive.

**P5 — "probed" also under-samples.** For at least one skill, the newest
probing report is a TARGETED re-probe covering strictly fewer cases than the
skill has positive cases on disk — so `probed` is asserted from a subset,
and the audit's own `probes` column already shows a number smaller than
`positives`.

**P6 — a re-probe can mask a full-corpus result.** `audit_skills` takes the
FIRST report in `load_reports` order that contains a non-errored probe. For
at least one skill, that report is a small round-363/369 re-probe rather
than the round-357 full-corpus run, and the two disagree about whether the
skill fires.

**P7 — the outcome-aware count is materially worse than the freshness
count.** Fewer than 30 of the 36 skills are BOTH fresh (`probed`) AND at
100% recall in that report, against the 35 the headline reports today.

**P8 — the `remainder` conflation is real and costs exactly two warnings.**
`carryforward_check.py`'s K004 reads the PRESENCE of a `remainder` field as
outstanding debt, so rounds 373 and 374 — whose remainders both open with
"None outstanding" — are reported as partially discharged. Splitting the
field drops the corpus check's warning count from 11 to 9 with no debt
un-recorded.

**P9 — round 374's slow tier is green.** `pytest -m whence_slow tests/` at
the inherited tree passes with **0 failures** and ≥ 77 tests, so round 374's
`SLOW_RESULT` placeholder can be filled with a real number rather than
re-run or dropped.

**P10 — the new checker finds nothing in the two skills I add cases for.**
Any skill I write this round will pass the new outcome check only because it
is UNPROBED (a probe is a priced run), which the check must therefore not
count as a pass. Scored on: whether the implemented check distinguishes
"no probe" from "a probe that passed".

**P11 — I do not close the owed banks.** 132, 362 and 368 stay `unscored`
with owner language(C); round 372's P10 and round 374's P11 both already
deferred them and they are not this track's.

**P12 — cost.** This round spends **$0.00** on live probes. Every number
above is derived from reports already committed under `state/trigger-eval/`.
