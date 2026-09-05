# Round 509 (SWE-loop D) — predictions, banked BEFORE any measurement

**Rule:** CLAUDE.md D-013. Written and committed before a single number below
was measured, and before any of the fourteen red nodes was run or its failure
text read.

**Subject:** the RED DEBT block in this round's own prompt — 14 red test nodes
in 7 suite files, 13 of them opened by a track that does not run the reddened
suite. SWE-loop(D) is the track whose remit (`harness/` + `languages/`) covers
five of those seven files, so this round is the *reader* for reds that three
other tracks opened and cannot see. The research question is not "make them
green"; it is **why the opener could not see it, and whether the tooling this
program already built (`harness/readset.py blast`, round 505) would have told
them.**

## Already OBSERVED before banking (NOT predictions — do not score these)

* O1. `nproc` on this box is 1. Every suite below is planned serialised.
* O2. `harness/tests/test_whenceslow.py:483` asserts `len(units) == 30` and
  `sum(len(u["tests"]) for u in units) == 118`, with a docstring recording
  four prior re-pins (rounds 470, 474/475, 482/485, 504/505). Read from source.
* O3. `harness/tests/test_swe_copyparity_real_subject.py` declares
  `MIN_FILES_SCANNED = 40` and `MIN_NODES_COLLECTED = 1500`, and runs
  `harness/swe/copyparity.py escapes|collect --root languages/whence` as real
  subprocesses from `REPO_ROOT`. Read from source.
* O4. Round 508's own state entry says it LEFT ONE TEST RED ON PURPOSE:
  `nuc/tests/test_survivor_impact.py::TestThisTree::test_the_committed_report_is_about_the_subject_at_head`.
  Read from `state/research-state.md`.
* O5. Round 503 → 504 is a recorded precedent for exactly this shape: round
  503 fixed two nodes and never DECLARED them in
  `harness/crosstrack-registry.json`, which is fail-closed, leaving
  `test_redattrib.py::TestThisTree`'s two nodes red. Read from the state file.
* O6. Round 507's state entry records that it edited `languages/whence/SPEC.md`
  and `skills/skill-authoring/scripts/`. Read from the state file.

## Predictions

### A. The four RECURRENT harness reds

* **P1.** `test_the_real_tree_yields_the_units_round_469_measured` fails on the
  FIRST assertion (`len(units) == 30`), not the second, because round 506
  (language C) added at least one new `@pytest.mark`-marked slow unit under
  `languages/whence/tests/`. It is the **FIFTH** occurrence of the
  opener-added-a-unit shape.
* **P2.** The actual unit count at HEAD is **31** (exactly one new unit).
* **P3.** The marked-node total at HEAD is in **[119, 125]**.
* **P4.** All THREE `test_swe_copyparity_real_subject.py` reds share ONE cause,
  not three. (Three nodes going red in the same round in the same file is a
  single upstream fact.)
* **P5.** That one cause is a NEW unguarded escaping path (a
  `dirname(dirname(...))`-shaped expression, or an `os.environ`/`..` join)
  introduced into a `languages/whence/**/*.py` file, i.e.
  `test_the_real_whence_tree_has_no_unguarded_escape` is the primary failure
  and the other two are downstream of the same scan.
* **P6.** The file carrying it was written or edited by round 507.
* **P7.** BOTH `test_redattrib.py::TestThisTree` nodes fail for the O4/O5
  reason: round 508's deliberately-red node is not declared in
  `harness/crosstrack-registry.json`, and the registry is fail-closed.
* **P8.** Adding exactly ONE declaration to that registry turns BOTH
  `test_redattrib.py` nodes green with no other change.

### B. The skills and whence reds

* **P9.** `corpus_check.py::unit_tests` is red for the SAME single fact as P7's
  cause — i.e. it runs a suite that contains round 508's deliberately-red node
  — and is therefore not independently fixable in `skills/`.
* **P10.** `corpus_check.py::state_claim_check` is red on a claim written in
  round 508's OWN state entry (the newest text is the least-checked text).
* **P11.** The four `languages/whence` reds (`test_assertshadow.py` x3,
  `test_subjprov.py` x1) are, like P4, ONE cause and not four; and it is a
  census/ledger drift caused by round 507's SPEC or script edits, not a bug in
  the assertion.
* **P12.** At least one of the 14 nodes will turn out NOT to reproduce solo —
  i.e. it is green when I run it alone and red only under the driver's four
  concurrent suites on a 1-core box. (The prompt warns about this explicitly;
  I predict the warning is earned by ≥1 node.)

### C. The instrument question — the one that matters

* **P13.** `python3 harness/readset.py blast` run against a working tree
  containing round 506's diff WOULD have named
  `test_whenceslow.py::test_the_real_tree_yields_the_units_round_469_measured`.
  (If it would not, `readset blast` does not solve the problem it was built for.)
* **P14.** `readset.py blast` would NOT have named the
  `test_redattrib.py::TestThisTree` nodes from round 508's diff, because
  round 508's red is caused by an ABSENCE (a missing registry declaration),
  and a diff-to-readset map keys on paths that were CHANGED.
* **P15.** Nothing in `run_driver.sh` invokes `readset.py` at all — it is a
  tool with no caller in the driver loop, 4 rounds after it was built.
* **P16.** The mean latency from open to close, over the reds this round can
  actually close, is **≥ 2 rounds**, and every one of them was closable at
  round-open time by the OPENER for zero extra cost had they run one command.

### D. What I will fail at

* **P17.** I will not close all 14. I predict I close **7–12** and name the
  rest with a measured reason.
* **P18.** At least one node I believe is "the same cause" (P4 or P11) will
  turn out to be two causes.
