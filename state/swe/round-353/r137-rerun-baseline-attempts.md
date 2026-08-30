# Round 353 — why round 137's archived tree could not narrow the interval

`swe.scoreaudit` puts round 137's true mutation score in **[0.7962, 1.0]**
from the recorded evidence alone (1016 evidenced kills + 0 timeouts of 1276;
260 kills with no verdict). Round 137's whole tree is archived at
`state/swe/round-137/orig-proj`, with `whence/interp.py` pinned byte-for-byte
to the campaign's own snapshot (verified with `diff`), so re-running those
260 mutants would collapse the interval to a point.

It cannot be done on this host. The gate this round added to `swe.campaign`
refused the measurement three times, each time for a different pre-existing
reason, and **none of them is about a mutant**. Recorded here rather than
worked around, because "the tree is not re-measurable" is the answer to
round 349's item 5, not an obstacle to it.

| # | command | result | cause |
|---|---|---|---|
| 1 | `pytest -q -x -p no:cacheprovider tests` | RED, exit 1, 149.3s — `1 failed, 613 passed` | `tests/test_v10.py::test_ref_diff_fuzz_mode_same_on_copy_and_diff_on_sabotage`: `ModuleNotFoundError: No module named 'swe'`. This snapshot's `bench/ref_diff.py` predates round 149's `AGI_RESEARCH_ROOT` fix and computes a tempdir-relative path to `harness/`. Diagnosed by round 155 §3. |
| 2 | same, with `PYTHONPATH=<repo>/harness` | RED, exit 1, 153.3s — `1 failed, 613 passed` | Same test, new failure: `assert (4 >= 5)`. With the import working it reaches its real assertion, which is about how many of 12 programs from **today's** `swe.fuzz.ProgramGen` parse. Today's generator is not round 137's. |
| 3 | same, `-k "not ref_diff_fuzz"` (no PYTHONPATH) | RED, exit 1, 214.8s — `1 failed, 613 passed, 1 deselected` | A SECOND test in the same family, `test_ref_diff_fuzz_transient_new_tree_timeout_is_retried_not_reported`, invisible until the first was deselected because `-x` stops at the first failure. |
| 4 | same, `-k "not ref_diff_fuzz"` (family filtered) | RED, exit 1, 62.0s — `1 failed, 64 passed, 3 deselected` | `tests/test_fuzz_regressions.py::test_diverge_on_deep_equal_values_is_not_quadratic` — round 233's known timing flake (`~1/5 isolated reruns`), fixed in round 233 and therefore NOT fixed in this round-137 snapshot. It failed here under real contention (1 CPU, load ~1.5, this round's own campaign tests running). |

Three independent causes, all already documented elsewhere in this repo,
all environmental. Attempt 4 was the stopping point: each further
deselection buys a smaller measurement of a different suite, and past two
the number would no longer be "round 137's score".

**What this does and does not license.**

* The interval [0.7962, 1.0] stands on the recorded evidence and needs no
  re-run.
* Round 137's published `corrected score 1.0` and `projected final score 1.0`
  are not measurements of 1276 mutants. They are measurements of 1016, with
  260 unknowns folded in on the flattering side.
* Nothing here says the 260 would have survived. It says nobody knows, and
  that round 137's own recheck stage could not have found out: it re-runs
  `survived` and `timeout` mutants only, and all 260 were recorded `killed`.

`rerun_r137_no_evidence.py` in this directory is the re-runnable script, left
in place with the `-k` filter from attempt 4. On a host where the archived
suite is green it runs to completion and is resumable; it aborts loudly
otherwise, which is what it did here.
