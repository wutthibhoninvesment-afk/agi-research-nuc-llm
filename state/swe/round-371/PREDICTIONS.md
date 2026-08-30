# Round 371 (SWE-loop D) — predictions BEFORE measuring

Banked 2026-08-30, before running ANY test, bench or sweep this round.
D-013: predictions first, then score honestly, including the misses.

## What I already hold (read-only, NOT predicted)

Read before banking, so these are context and not credit:

- Round 365 (D) pinned `generate_guest_program(31)` as a non-terminating
  program: `harness/tests/test_swe_guest.py::
  test_seed31_does_not_terminate_under_the_default_budget`, asserting
  `run_oracle(..., timeout_s=25.0, max_depth=2000).kind == "timeout"`. Its
  docstring says: *"If a future round fixes it, this test goes red and that
  is the intended signal -- flip it to assert termination and record the
  fix."*
- Round 366 (C) root-caused the same program independently
  (`languages/whence/tests/test_v26.py` header: bisected to line 7,
  `tl3(tr5)` with `tr5 == 0.5`, a non-terminating TAIL recursion) and fixed
  the class by adding `Interpreter.DEFAULT_MAX_ITER`.
- Round 368 (C) raised `DEFAULT_MAX_ITER` to `1000000` and added
  `DEFAULT_MAX_VALUE = 500000000` / `DEFAULT_MAX_INT_BITS = 8000000`.
  The interp.py comment claims, measured by `bench/runaway_cost.py`, "a
  runaway is a miss after 9.3s / 748MB at the worst of four shapes, 3.7s /
  412MB at guest seed 31's".
- `harness/run_tests_fast.sh` deselects `test_swe_*.py` (the slow tier), so
  no round-366..370 health check ever executed the seed-31 pin.
- `harness/swe/slowtier.py status` right now: 19 files, **0 conclusive**
  against this checkout; `test_swe_guest.py` is `stale_subject` (202s, 7.4h
  ago, "moved in scope: examples, whence").

So the pin's own trigger condition ("a future round fixes it") has been
true for five rounds and nothing ran the test that was supposed to say so.

## Predictions

### A. The stale pin

- **P1** — `test_seed31_does_not_terminate_under_the_default_budget` FAILS
  at HEAD: `o.kind != "timeout"`. Confidence **85%**.
- **P2** — seed 31 under `run_oracle(GUEST_ORACLE, ..., max_depth=2000)`
  now RETURNS, in **3-25 s** wall on this quiet box (load ~1.0, vs round
  365's load 25-42). Confidence **70%**. Band is wide on purpose: the
  program contains more than one runaway call site (`tl3(@{b: w2})` on a
  record and `tl3(tr5)` on 0.5), the oracle runs the program under BOTH
  evaluators, and 1e6 iterations is ~3.7 s per loop by round 368's own
  bench figure.
- **P3** — the outcome kind will be **`"ok"`** (host and guest agree once
  the loop is bounded), not `mismatch`. Confidence **50%** — genuinely a
  coin flip: the guest hits its own guest-depth ceiling on a different
  budget than the host's `max_iter`, and only the `&DEPTHMISS&` scrub in
  `scrub_record_line` plus `agree()`'s sentinel branch keeps that from
  being a divergence.
- **P4** — `test_shape_declaring_guest_programs_agree` still PASSES, and
  its `timeouts` list is now **empty** (0), not the `<= 2` its round-365
  comment allows. Confidence **60%**.
- **P5** — at least ONE other assertion in `harness/tests/test_swe_*.py`
  encodes a language behaviour that v0.26/v0.27 changed (an unbounded-loop
  or unbounded-value assumption). Confidence **45%**.
- **P6** — the harness constructs interpreters in **zero** places that
  pass `max_iter=` or `max_value=` explicitly, i.e. every SWE oracle
  silently inherited the new v0.26/v0.27 defaults the moment rounds 366 and
  368 landed. Confidence **85%**.
- **P7** — full `harness/tests/test_swe_guest.py` at HEAD: **1-3 failures**
  (at minimum the seed-31 pin), runtime **150-400 s**.
- **P8** — across the whole `test_swe_*.py` slow tier, **1-6** failing
  tests total. Confidence **50%**.

### B. Round 23's owed prediction bank (round 369's next-step item 2)

- **P9** — round 23's P1 (mutation score 88-93%, survivors 55-85 on v0.6
  `interp.py`) is **UNSCORABLE as posed** from surviving artifacts:
  `state/mutation/round-023-interp.log` is 44 lines, every one `killed`,
  with no survivor section and no score line. Confidence **90%**.
- **P10** — the nearest instantiation (round 29's
  `state/mutation/round-029-interp.json`) has a mutation score that lands
  **inside** round 23's 88-93% band. Confidence **55%**.
- **P11** — round 23's P3/P4/P6 (the live-model review/kill lane and its
  <= $8 cost) are unscorable with **no** surviving artifact at all —
  `state/swe/round-023/review1.out` empty or absent, no cost record
  anywhere in the tree. Confidence **80%**.

### C. Process

- **P12** — this round will find the working tree carrying at least one
  file it did not write and must not commit (beyond the 18 already
  allowlisted + `SECURITY.md`), OR none at all; I predict **none** —
  `git diff --cached` empty and no new unattributed path. Confidence
  **70%**.
- **P13** — I will break at least one of my own assertions on its first
  run this round (the standing base-rate bet). Confidence **60%**.

## Addendum, banked mid-round (before the measurement it is about)

Banked after observing `70 passed` for the whole file and `1 failed` for
`test_seed31_does_not_terminate_under_the_default_budget` run alone, and
BEFORE running anything to explain it.

- **P14** — the pin is green in-file and red alone because of PROCESS HEAP
  state, not program semantics: seed 31 terminates either way, but after
  the other 69 tests in the file have run, the same `run_oracle(...,
  timeout_s=25.0)` exceeds 25 s where cold it takes ~11 s. Mechanism:
  round 26's P9 (retained provenance DAGs tax every LATER run's gen-2 GC).
  Confidence **70%**.
- **P15** — in one fresh process: cold seed 31 **8-14 s**; the SAME call
  repeated after ~40 other guest seeds have been evaluated in that process
  **> 25 s**. Confidence **55%** (the "40 seeds" dose is a guess).
- **P16** — therefore no ordinary suite run could ever have delivered the
  red signal the pin's docstring promised, and the slow tier's last
  recorded run of this file (round 365, 202 s) is not evidence either way.
  Confidence **75%**.
