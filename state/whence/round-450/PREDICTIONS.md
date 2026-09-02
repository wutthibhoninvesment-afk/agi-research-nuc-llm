# Round 450 (language C) — predictions, banked BEFORE measuring

Rule D-013: written and committed before any command in this round's subject
was run. Scored honestly in the round's knowledge file. Round 435's next-step
7 applies: where I have no basis I say so rather than guessing, and an
abstention is recorded as an abstention. Round 419's rule applies too: the
DISPOSITION is fixed here, before the numbers, so no measurement can choose
the fix. Round 449's step 11/12 apply: a wall-time band states its contention
condition, and a count band names its counter.

**Subject:** round 446's next-step 1 — *"the rendering residual is the only
thing keeping 'print is observation' from being literally true. `full_show`
shows a nested miss as the bare token `miss` with no reason, so
`print([nosuch(1)])` is suppressed on a promise it does not keep. Decide
between (a) a nested rendering that carries the reason plus 11 re-pinned
killers, or (b) keeping the rendering and making the SUPPRESSION narrower (a
container is observed only when it renders every miss inside it). Say which,
and run the corpus before and after."* — plus its item 2 (`Guess` is the one
aggregate v0.42 does not walk, on a written argument that is not tested).

## DISPOSITION, fixed before the measurement

I will implement **(a) AND (b) together**, because I claim they are not
alternatives: (b) alone re-opens the `history.lang` false positive that
forced v0.42's companion half, since under the CURRENT rendering a container
never renders any miss's reason, so "observed only when it renders every miss
inside it" would be false for every container. (b) is only reachable on top
of (a). If the measurement shows (b) is viable alone I will say so and this
disposition is a scored MISS.

Concretely: `_show`'s `Miss` branch carries the reason; and `b_print` stops
marking the CONTAINER observed and instead marks exactly the miss NODES the
rendering actually named, computed by a walk that shares the renderer's depth
bound. Nothing about the drop DETECTOR (`_misses_within`) changes.

## Already DERIVED by reading, therefore NOT predictions

Recorded so I cannot later re-label them as hits.

- D1. `tests/test_generated_killers.py:35`'s `vals` is
  `full_show(v.payload)`, so round 446's "eleven pinned killers quote
  `[miss, miss]`" is a claim about the RIGHT function. I expected on first
  reading that it would be the limited `show_payload` snapshot path and it is
  not. Read at tests/test_generated_killers.py:14-38.
- D2. `full_show` bounds container nesting at `values.SHOW_NEST = 3` (via
  `show_payload` -> `_show`, which returns `[…]` / `@{…}` at
  `nest >= SHOW_NEST`), while `Interpreter._misses_within` has NO depth bound
  at all — only the `DROP_SCAN_NODES` node budget. Detector and suppressor
  therefore have different shapes. Read at whence/values.py:522-533, 605-644;
  whence/interp.py:841-899.
- D3. `full_show` has its own `WList`/`Record` branch that re-renders each
  element at `nest=0` rather than delegating to `show_payload(p, None)`, so a
  printed container gets exactly ONE more level of visible nesting than the
  same value rendered through `show_payload`. Read at whence/values.py:646-660.

## Predictions

- **P1 (the second residual exists and is unnamed).** `print` marks a
  container observed on a promise the renderer does not keep AT ANY DEPTH
  past `SHOW_NEST`, not merely a promise it keeps thinly. Specifically, the
  program `print([[[[[nosuch(1)]]]]])` will print a line containing **no
  occurrence of the substring `miss`** and will report **0** drops. Basis:
  D2 + D3. Confidence: high on the drop count, medium on the exact
  rendering.
- **P2 (the exact rendering of P1's program).** That printed line will be
  exactly `[[[[…]]]]`. Basis: D3's one-extra-level claim. Confidence: low —
  this is the arithmetic I am least sure of and it is banked as a separate
  line precisely so a wrong bracket count cannot hide inside P1.
- **P3 (monotonicity violation, the sharpest statement of residual 1).**
  Adding a `print` to a program strictly REMOVES information about a miss.
  Program A = `[nosuch(1)]` as a bare statement: **1** drop reported, and the
  report text contains `unbound name 'nosuch'`. Program B =
  `print([nosuch(1)])`: **0** drops, and the program's ENTIRE stdout is
  `[miss]` — 6 characters, containing no reason. Confidence: high.
- **P4 (blast radius of the rendering change, counter = pytest test
  functions that go from pass to fail).** Changing `_show`'s `Miss` branch to
  carry reasons will redden **8 to 25** test functions across
  `languages/whence/tests/`. Basis: round 446 counted 11 grep LINES across
  two files; assertions are neither lines nor functions and `full_show` also
  feeds `str()`, `print`, and `run.py`'s report. Confidence: medium.
- **P5 (of those, the `test_generated_killers.py` share).** Between **4** and
  **12** of P4's functions will be in `tests/test_generated_killers.py`
  (counter = test functions, not lines). Basis: 11 grep lines in that file
  and SPEC.md together, several of them docstring quotations of a MUTANT's
  output rather than assertions. Confidence: medium.
- **P6 (`show:` fields do not move).** The `show: "miss"` field inside a
  `blame`/`history` record is computed by `show_payload` when the record is
  BUILT, not by `full_show` when it is rendered, so it will NOT change. Every
  killer line quoting `show: "miss"` while its sibling `value: miss` changes
  is evidence for this. Confidence: medium-high.
- **P7 (corpus impact of the SUPPRESSION fix — the "run the corpus before and
  after" round 446 asked for).** `python3 curecheck.py corpus`'s dropped
  total will be **12 before and 12 after**, and `replay`'s will be **23
  before and 23 after**. Basis: no corpus program is likely to print a
  container with a miss nested deeper than `SHOW_NEST`. Confidence: medium.
- **P8 (`history.lang` survives the suppression change unchanged).** Its
  `print(culprits)` misses live at nest 1 (list of records, `.value` a miss),
  so they stay inside the renderer's bound and stay observed.
  `tests/test_v42.py::test_history_lang_is_the_case_that_forced_the_
  observation_rule` will pass with **no edit to its body**. Confidence: high.
- **P9 (the tracked corpus is unmoved).** Tracked examples stay at **1** drop
  (`examples/dropped.lang`) after BOTH changes. Confidence: high.
- **P10 (`_observed_aggr` survives).** After the fix I will still keep two
  dicts, and `tests/test_v42.py::test_the_two_observation_sets_are_bounded_
  separately` will need its BODY changed (it pins containers into
  `_observed_aggr`; the fix puts miss NODES there) while keeping its name and
  its invariant. Prediction: 1 test body edited, 0 tests deleted.
  Confidence: medium.
- **P11 (round 446 item 2, `Guess`).** At HEAD, `guess(nosuch(1), 0.5, [])`
  as a dropped statement reports **0** drops (the written decision), and
  `print(guess(nosuch(1), 0.5, []))` renders its interior miss as the bare
  token `miss` as well — i.e. the Guess branch carries the SAME residual as
  the container branches and nobody has said so. Confidence: high on the
  first, medium on the second.
- **P12 (`Guess` and observation).** `print(guess(nosuch(1), 0.5, []))`
  currently marks **nothing** observed (a `Guess` payload is neither `Miss`
  nor `WList`/`Record`, so `b_print`'s gate does not fire), which is
  currently harmless only because `_misses_within` refuses to walk a `Guess`
  either. The two refusals agree by coincidence, not by construction.
  Confidence: medium.
- **P13 (suite size before).** `languages/whence/run_tests_fast.sh` at this
  round's start: **2245 passed, 3 skipped, 97 deselected**, rc 0. Basis:
  round 449's driver line `whence-health-check PASS (2245 passed, 3 skipped,
  97 deselected)`. Confidence: high.
- **P14 (wall time, with its contention condition).** Run **solo** on this
  1-core box with no other pytest process and no driver suite running,
  `run_tests_fast.sh` will finish in **200-300 s**. Basis: round 446 measured
  234.97 s solo at a smaller collection. If it is run contended I will report
  it as contended and P14 is unscorable rather than a hit.
- **P15 (`str()` is affected too, and that is a language-visible change).**
  Because `str` is `full_show`, the rendering change alters the value of
  `str([nosuch(1)])` inside a Whence program — not just diagnostic output. At
  least one test outside `test_generated_killers.py` and outside
  `test_v42.py` will go red for that reason. Confidence: medium.
- **P16 (the guest).** `examples/self_eval.lang` and the host/guest
  differential suites (`test_miss_message_differential.py`,
  `test_self_eval.py`, `test_self_hosting.py`) compare MISS MESSAGES and
  parse errors, not container renderings, so **0** of their test functions
  will redden from the rendering change. Confidence: low — I have not opened
  them and this is the risk I most expect to be wrong about.

## No basis, reported rather than guessed

- The number of `.lang` files on disk at this HEAD (round 446 said 33; the
  gateway adds files between rounds). I will report what I find.
- Whether any DOWNSTREAM consumer outside `languages/whence/` parses
  `full_show` output (the corpus checkers, `harness/swe/`). I have not looked
  and will not pretend a number.
