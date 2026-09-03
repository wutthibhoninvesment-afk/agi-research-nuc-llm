# Round 474 (language C) — predictions, banked BEFORE measuring

Rule D-013. Written 2026-09-03, before any of the measurements below was
taken. Scored in `knowledge/round-474-*.md` §8.

## 0. What was already read when this was written

Honest scope, per round 470's next-step 4 ("if your structural prediction is
about a file you have not opened, say so in the line, and expect it to score
like a guess"):

* READ: `depthcensus.py` `harvest_file` in full (the binding passes at
  :2098-2195, `_row` at :2207, the call walk and dedup at :2244-2350),
  `census_tests` at :2430, the `--residual` report at :2662-2718.
* READ: `tests/test_testcorpus_census.py::test_two_loops_one_name_and_the_
  second_loops_row_disappears_with_it` (:1234) and its docstring.
* NOT READ: `tests/test_v30.py` (the live instance), `tests/test_v31.py`
  (round 470's P4), and every other test that pins a harvested position.
  P4, P8 and P9 are about files not opened and are banked as guesses.

## 1. Baseline, measured before predicting (not a prediction)

```
$ .venv/bin/python depthcensus.py --tests --residual | head -3
harvest:  829 programs from 64 files, 920 calls
residual: 100 (42 unresolved names + 58 non-constant nodes)
```
5.06 s wall.

## 2. The predictions

**P1 (rate).** Of the 829 harvested programs, the share sharing a
`(file, line)` key with at least one OTHER program is between **10 % and
25 %**.

**P2 (structural, file read).** Adding `col` to a program's identity does
NOT change the program count: it stays **829**. The cross-file and in-file
dedup keys are `(src, max_depth)` and never a position — read at
`depthcensus.py:2334` (`key = (s, depth)`) and in `harvest_tests`.

**P3 (structural, file read).** `col` strictly increases the number of
distinct position keys over the corpus — at least one `(file, line)` pair
carries two programs at different columns.

**P4 (structural, file NOT opened — a guess).** `test_v31.py:607`, which
round 470's P4 misread as a dedup defect, is one of the colliding pairs,
and `col` separates its two `host_value(program)` calls.

**P5 (structural, file read).** Under per-BINDING (region-scoped) loop
environments, `test_two_loops_one_name_and_the_second_loops_row_disappears_
with_it` goes **RED**, and it goes red at BOTH of its two asserts: the
three programs no longer land on one line, and the unread loop's residual
row comes back. Round 470 wrote that test as the tripwire for exactly this
build; red is the intended outcome, not a regression.

**P6 (count, banked as a delta).** The residual row count rises from 100 by
**exactly +1**, to 101 — the `counts` loop at `test_v30.py:306` regaining
the row that resolving `SHARING` took from it. Not +2 and not +0.

**P7 (rate).** The harvested program count after region-scoping is
**unchanged at 829**. The test's own docstring says the `counts` loop's
programs reach the corpus through the `AGREE` loop at :204, so restoring
its residual row should cost the corpus nothing.

**P8 (structural, file NOT opened — a guess).** `SHARING`'s two programs
re-attribute from `test_v30.py:307` to line **299 or 300** (the first
loop's own `host(...)` call site).

**P9 (rate, files NOT opened — a guess).** The number of OTHER whence
fast-tier tests that go red from these two changes is **at most 4**, and
every one of them is an ATTRIBUTION/position pin rather than a corpus-count
pin. If a corpus-COUNT pin goes red, P2/P7 are wrong and the change is not
behaviour-preserving where it claimed to be.

**P10 (rate).** `depthcensus.py --tests --residual` after per-node region
filtering runs in **under 3x** the 5.06 s baseline, i.e. < 15.2 s. The
filter runs per binding-table read rather than per scope, which is the one
place this change can cost real time.

**P11 (structural, file read).** Region-scoping loop bindings does NOT
change the `parse_only`, `unparsed`, `forwarded` or `excluded` row counts
(186 / 18 / 81 / 79). Those rows are produced by branches that never read a
folded string value, so a narrower environment cannot move them.
