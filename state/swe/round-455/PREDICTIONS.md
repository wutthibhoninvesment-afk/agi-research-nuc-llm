# Round 455 (SWE-loop D) — predictions, banked BEFORE measuring

Written 2026-09-02, after the two observations below and before every other
number in this round. Scored honestly in
`knowledge/round-455-*.md`; a miss is the valuable outcome.

## Already observed when this file was written (NOT predictions)

* `harness/wiring_audit.py check` at HEAD: `rc=1`, two W001 errors —
  `languages/whence/depthcensus.py`, `nuc/reachability_recover.py`;
  summary `119 entry point(s), 99 in closure, 2 error(s), 0 warning(s)`.
* Its wall clock, 3 runs: 14.35 s / 12.63 s / 12.32 s.
* `logs/driver.log` says `health-check FAIL` with these same 3 tests for
  rounds 453 and 454.
* `harness/wiring-registry.json` holds 117 entries: 94 `wired`, 23 `manual`.

## The question

The three red tests live in `harness/tests/test_wiring_audit.py` and are run
by `harness/run_tests_fast.sh`. But their SUBJECT is the whole repo — 119
entry points spread over `harness/`, `languages/`, `nuc/`, `skills/`, the
root. The two violations were shipped by round 452 (language C) and round 454
(NUC-integration E). **Neither of those rounds runs `harness/tests/`.**

So: a live-tree assertion's *blast radius* is the whole repo, but its
*residence* is one track's suite, and a six-round rotation means most rounds
cannot see it even if they run their own suite in full. How big is that class?

## Predictions

**P1 — the fix.** Adding two registry entries turns all three
`test_wiring_audit.py::TestThisTree` failures green and `wiring_audit.py
check` to `rc=0`, with NO other harness fast-tier test going red.
Confidence 0.90.

**P2 — the two statuses.** Both new entries are `wired`, not `manual`:
each has a sibling test file (`languages/whence/tests/test_depthcensus.py`,
and I expect a `nuc/tests/test_reachability_recover.py`) that imports it, and
the driver runs both suites. Confidence 0.65 for both-wired; 0.80 that
`depthcensus.py` alone is `wired`.

**P3 — how many live-tree assertion CLASSES the harness tier has.** Test
classes/functions that assert a property of the checked-in tree rather than a
fixture. Point estimate **12**, 80% interval [6, 25].

**P4 — how many of those have a subject that extends OUTSIDE `harness/`.**
Point estimate **5**, 80% interval [2, 10]. These are the cross-track ones —
the class this round is about.

**P5 — the episode analysis over `driver.log`'s `health-check` lines.**
Replaying round 453's method one layer up. Over all `health-check` lines:
 - red rate: **20%**, 80% interval [10%, 35%];
 - number of episodes: **12**, interval [6, 25];
 - mean episode length: **2.0** rounds, interval [1.2, 3.5];
 - fraction of episodes OPENED by a non-harness(A) round: **0.70**,
   interval [0.4, 0.95]. (Round 453 measured 16/16 = 1.00 for the skills
   corpus. I predict the harness tier is lower but still a majority, because
   `harness/` code is edited by harness(A) and SWE-loop(D) both.)

**P6 — the reverse direction.** At least one of the OTHER three suites
(`languages/whence/`, `nuc/`, `skills/`) also contains a live-tree assertion
whose subject reaches outside its own directory. Confidence 0.85. Point
estimate for how many of the three: **3** (all of them).

**P7 — cost of a cross-track subset.** Running only the cross-track live-tree
assertions found in P4 costs under 60 s wall clock on this 1-CPU box.
Confidence 0.60. (`wiring_audit.py check` alone is already 12-14 s of it.)

**P8 — the carried SWE-loop(D) item.**
`harness/tests/test_swe_campaign.py::test_review_stage_and_report` is still
red at HEAD with `rep["corpus"]["no_killer"] == 0`, unchanged since round
433. Confidence 0.75.

**P9 — recall of the slow-tier instrument.** The standing next-steps say
"recall is still 0%". The driver log's last three `slowtier-slice` lines say
3%, 6%, 9%. I predict the state file's 0% is STALE and that HEAD's ledger
reports >= 9% against checkout `6a525eab44f60c1c`. Confidence 0.85.
