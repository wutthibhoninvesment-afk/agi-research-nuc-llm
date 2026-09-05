# Round 500 (language C) — predictions, banked BEFORE measurement (D-013)

Written before running any new code. The job is round 498's next-step #2:

> "The `tree_derived` axis is the weakest thing in the instrument and it is
> the one that decides what gets fixed. It is a heuristic over fixture
> parameters plus a name list, and it produced 2 false positives out of 9 on
> its first outing... the honest version is dataflow (does the magnitude's
> subject trace to a value the function constructs, or to one it is handed)
> and nobody has costed that."

Plus round 499's next-step #1, which pre-registered an experiment for
"the next round to build an entry point". That is this round.

## What is being built

`languages/whence/subjprov.py` — an intraprocedural backward-slice that
resolves the PROVENANCE of each root name an assertion is about, rather than
asking a whole-function yes/no question. Lattice, most-drifting first:

    tree > handed > unknown > scratch > local

Stated assumption, to be falsified rather than trusted: **arguments
dominate.** A call to an opaque callable propagates the join of its
arguments; only a call to a known reader (`open`, `check_output`, ...) is
`tree` on its own. A no-argument call to an opaque callable is `unknown`.

## Predictions

- **P1.** The live census has **>= 20** of its 57 pairs marked
  `tree_derived: true` by the function-level heuristic.
- **P2.** Under subject-level provenance, `pairs_costly` (independent AND
  derived) falls from **7 to <= 2**.
- **P3.** `test_v30.py::test_the_guest_never_merges_a_tail_loop` is
  reclassified `local` and leaves the costly set. Its magnitude subject `h`
  traces to `host(src)` where `src` is a string literal built in the
  function body. Dataflow AGREES with round 498's hand-declared false
  positive.
- **P4.** `test_v10.py::test_ref_diff_same_on_identical_copy_and_diff_on_
  sabotage` does **NOT** leave the costly set entirely, and round 498's
  node-level "false positive" verdict is therefore TOO COARSE. Its four
  `r.returncode` pairs go (`r` traces to `_ref_diff(tmp, ...)` with `tmp`
  from `tempfile.mkdtemp`, i.e. scratch), but its two `s.count(old) > 1`
  pairs SURVIVE as `tree`, because `s = open(p).read()` over a copy of
  `interp.py` and that count genuinely drifts with the tree.
  So: `pairs_costly` 7 -> 2, `candidates_costly` 2 -> 1.
- **P5.** The two analyses disagree in BOTH directions. At least **15**
  pairs go True -> False, and at least **1** pair goes False -> True (a
  magnitude over a module-level constant in a function that takes no
  fixture and calls no reader — invisible to the function-level heuristic).
- **P6.** The "arguments dominate" assumption is violated by at least
  **1** resolvable module-level helper in `tests/` — a helper that reaches
  the tree without using any of its parameters.
- **P7.** The whole-tree subject-provenance sweep costs **< 3.0 s** with no
  git access.
- **P8.** (Round 499's pre-registered experiment.) The pre-commit hook
  installed by round 499 WILL print a warning naming `subjprov.py` in this
  round's own `git commit` output, and the commit will SUCCEED. The eighth
  instance of the W001 recurrence is therefore caught at commit time by its
  author, and the trio does not go red for round 501.
- **P9.** Landing two new files in `languages/whence/tests/` moves round
  494's contributions ledger by exactly **2** new rows, and reddens
  `test_assertshadow.py`'s census gate until the census is regenerated.
- **P10.** `tests/test_subjprov.py`, written with this instrument's own
  finding in mind, contributes **0** new shadow candidates to the census.

## Scoring rule

Every P above is scored HIT/MISS in the round file with the command that
decided it. A MISS is written up, not quietly rounded to a HIT — round
499's P5 miss (predicted >=110 of 117, actual 35) was the most useful
result that round produced.
