# Round 431 (SWE-loop D) — prediction bank, written BEFORE any measurement

Banking rule D-013. Written after reading `harness/swe/mutation.py`,
`harness/swe/copyparity.py`, `harness/pristine_check.py`, round 425's
`copyparity-run-real-subject.json` and rounds 425/427's knowledge files —
and BEFORE running any suite this round, before the live/sandbox junit
differential, and before writing a line of new code.

Subject: `mutation.baseline_check`, the gate every mutation campaign passes
through, and the `passed -> skipped` evaporation round 425 found in the
mutation sandbox (round 427's next-steps item 1, SWE-loop(D)).

## A. What re-running the differential at HEAD will show

- **A1.** `copyparity run` (scoped `-m "not whence_slow"`) still reports
  **exactly one** regression, the same node
  `tests.test_v37::test_the_host_is_byte_unchanged_by_this_decision`,
  `passed -> skipped`. Range if not exactly 1: 1–3.
- **A2.** `vanished`, `appeared` and `improvements` are all **empty**.
- **A3.** `n_nodes` is **equal** on both sides and is **> 2086** (round 425's
  figure; rounds 426–430 added whence tests). Range 2086–2400.
- **A4.** Live skip count on the scoped fast tier is **3** (the number round
  427 quotes from the live tier). Sandbox skip count is **4** = live + the
  one evaporation.
- **A5.** Skipped in BOTH trees: **3** nodes. None of them is a copy defect,
  and none is currently written down anywhere.
- **A6.** Both sides exit **0**.

## B. The claim this round is really testing

- **B1.** Round 425's sentence — *"Every mutant this test would have killed
  now survives silently, and the mutation score is **inflated** by exactly
  the amount nobody can see"* — has the **sign backwards**. `score` is
  `killed / total` (`mutation.py:326`). An evaporated test that would have
  killed mutants moves those mutants from `killed` to `survived`, so the
  score goes **DOWN**. I predict I will find **no reading** on which a
  `passed -> skipped` evaporation inflates `score` or `valid_score`.
- **B2.** The analogy round 425 draws to round 349 (`pyproject.toml`, "the
  run that tested nothing scored twice the tree that worked") **fails**:
  349 is the flattering direction, this is the unflattering one. The harm is
  real but different — phantom test gaps, wasted killer/repair budget.
- **B3.** The evaporating test executes **ZERO** lines of any file under
  `languages/whence/whence/`, so the set of mutants it would have killed is
  **EMPTY** and round 425's sentence is not merely sign-flipped but
  **vacuous** on its own instance. Measured with `swe.coverage` over the
  single node id.
- **B4.** Therefore: the class is real and the instance is harmless. I
  predict the honest headline is "the gate cannot see the class", not "the
  score was wrong".

## C. What `baseline_check` records today

- **C1.** `baseline_check` returns exactly **4** keys (`returncode`,
  `timed_out`, `seconds`, `tail`) and **none** names a test.
- **C2.** `campaign.stage_baseline` adds 4 more (`green`, `test_cmd`,
  `allow_red`, `checked`) and still names no test.
- **C3.** The `tail[-800:]` DOES contain pytest's count line, so the skip
  COUNT is recorded and has never been compared to anything.

## D. The capability

- **D1.** A per-node skip check needs **zero extra suite runs**: the
  baseline already runs the suite in the copy, so `--junitxml` on that run
  plus a pinned acknowledgement registry answers "did this sandbox lose
  evidence" without a second tree. This is cheaper than
  `pristine_check`'s two-run design and I predict the overhead of the flag
  is **< 3 s** on the whence fast tier (< 2 % of ~140 s).
- **D2.** Writing the junit report INSIDE the copied tree would change at
  least one whence test's outcome (something under `languages/whence/tests/`
  enumerates files in the tree). Report path must be a sibling of `proj`.
  Scored honestly: if no such test exists, D2 is a MISS.
- **D3.** `copyparity`'s `regressions` bucket merges `passed -> failed`
  (which the exit-code gate catches) with `passed -> skipped` (which it
  cannot). Splitting them is the change that makes the report readable as a
  severity ordering.
- **D4.** Nothing in the repo reads `state/known-sandbox-skips.json` today
  (it does not exist).
- **D5.** `copyparity.parse_junit` counts an **xfail** as `skipped`, unlike
  `pristine_check.parse_junit` which excludes `type="pytest.xfail"`. I
  predict whence-fast has **0** xfail nodes today, so the latent phantom has
  never fired.

## E. Cost and hygiene

- **E1.** The two-sided differential costs **270–330 s** wall clock.
- **E2.** `harness/tests/` fast tier stays green and grows by **20–35**
  tests.
- **E3.** No file under `languages/whence/` is edited this round; Whence
  stays at its current spec level.
- **E4.** The whence tree must not be edited WHILE the differential runs
  (a baseline measures a tree that changes under it). I commit to creating
  no file under `state/` or `languages/whence/` until the run finishes.
