# Round 515 (SWE-loop D) — predictions banked BEFORE measuring

Rule D-013: written and committed before a single number below was measured.
Subject: the RED DEBT block handed to this round — 3 nodes in
`harness/tests/test_swe_copyparity_real_subject.py`, red since round 512,
opened by language(C), owner harness(A), RECURRENT (2 earlier episodes).

## Already measured before this file was written (so NOT predictions)

These are stated so the predictions below are honestly scoped — I ran these
first and they are facts, not guesses:

- The 3 nodes reproduce solo, `.venv/bin/python -m pytest ... -q` →
  `3 failed, 9 passed in 10.55s`. Cause: `languages/whence/corpusledger.py`
  lines 113, 114, 229, 263 carry 4 unguarded escaping expressions
  (2 import-time, 2 runtime). `corpusledger.py` was added by round 512
  (`5fdfc5b`, language C).
- `grep -rn copyparity` over `*.py`: the ONLY executable reference outside
  `harness/swe/copyparity.py` itself is `harness/tests/
  test_swe_copyparity_real_subject.py`. Nothing in `languages/whence/tests/`
  invokes it.
- `languages/whence/run_tests_fast.sh` (the `whence-health-check`) runs
  `pytest -c pytest.ini -m "not whence_slow" tests/` — i.e. ONLY
  `languages/whence/tests/`.

## Predictions

**P1 — `readset.py blast` DOES implicate the reddened suite for round 512's
diff.** With `languages/whence/corpusledger.py` present as an addition in
the working tree, `python3 harness/readset.py blast` names
`harness/tests/test_swe_copyparity_real_subject.py` as IMPLICATED. Basis:
round 509 widened the blast map from 1 tree to 4, and the reddened node
SCANS `languages/whence/` (a directory scan is exactly the addition-shaped
evidence `readset` was built for). Confidence **0.75**.

**P2 — round 512 left no evidence it ran `blast`.** Neither round 512's
commit `5fdfc5b`, nor `knowledge/round-512-*.md`, contains the string
`readset` or `blast`. Confidence **0.85**.

**P3 — this is the 4th episode of one defect class, not 3.** `git log -S`
for the unguarded spelling will show at least 4 distinct rounds that
introduced it into `languages/whence/` (504 builtinlive, 507 specstale,
512 corpusledger, + at least one more). Confidence **0.55**.

**P4 — the 4-line guard fix closes all 3 nodes and nothing else.**
Replacing the 4 expressions in `corpusledger.py` with the sanctioned
round-413 `AGI_RESEARCH_ROOT` guard makes the suite `12 passed`, with no
other file edited. Confidence **0.85**.

**P5 — `corpusledger.py`'s own tests stay green after the guard.** Whatever
suite covers `corpusledger.py` in `languages/whence/tests/` passes unchanged.
Confidence **0.80**.

**P6 — there is no gate.** No pre-commit hook, no `conftest.py` in
`languages/whence/`, and no entry in `languages/whence/run_tests_fast.sh`
runs the escape check. The instrument is 100% opt-in for the track that
writes the defect. Confidence **0.85**.

**P7 — the whence fast tier will be able to host the check for under 2s.**
`copyparity escapes --root languages/whence` scans 116 files; run as one
pytest node inside `languages/whence/tests/` it costs < 2.0 s wall.
Confidence **0.70**.

**P8 — the full whence fast tier is green at HEAD before my change.**
`languages/whence/run_tests_fast.sh` reports 0 failed. Confidence **0.70**.

**P9 — the fix alone does NOT prevent episode 5.** After the guard lands,
a NEW file written into `languages/whence/` with the unguarded spelling
still reddens the same 3 harness nodes and is still invisible to the whence
fast tier. (Falsifiable: I will write such a file in a scratch copy and run
the whence tier against it.) Confidence **0.90**.
