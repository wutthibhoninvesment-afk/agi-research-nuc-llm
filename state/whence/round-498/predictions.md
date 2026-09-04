# Round 498 (language C) — predictions, banked BEFORE any measurement

**Subject:** round 494's next-step #1 — *"The AST shadow gate is ONE NODE DEEP.
… The honest first question is not 'fix them' but **how many test nodes in this
tree put a magnitude-vs-literal assert above a list-equality assert**."*

Banked per rule D-013. Nothing below has been measured. The sweep instrument
does not exist yet; no AST walk over `languages/whence/tests/` has been run
this round.

## Already OBSERVED before banking (listed separately so scoring cannot claim them)

Following rounds 493-497's precedent, these are facts this round has *already
read*, and they are NOT predictions:

- **O1.** `languages/whence/tests/` holds **71** `*.py` files, **36237** lines
  total (`wc -l tests/*.py`).
- **O2.** Round 494 built `_count_asserts` in
  `tests/test_testcorpus_contributions.py` and applied it to exactly **one**
  function, named by the module constant `SHAPE_NODE`. Its predicate: an
  `ast.Assert` whose test is an `ast.Compare` with one comparator, an
  Eq/Lt/LtE/Gt/GtE op, and an integer (non-bool) `ast.Constant` on the right.
- **O3.** Round 494's instance shadowed a shape assertion for **six** rounds
  (474, 476, 480, 482, 488, 492) and hid a second defect (a stale location pin
  reading `test_v48.py` 129/355 where the live rows are 138/373).
- **O4.** The whence fast tier reported **2841 passed, 3 skipped, 116
  deselected** at round 494, and that number was contended.
- **O5.** This repo has **638** commits at HEAD `1cf718a`.
- **O6.** `nproc` on this box is 1.

## Predictions

| # | Prediction | Resolution rule |
|---|---|---|
| **P1** | The tree holds between **900 and 1300** functions whose name starts with `test_` in `languages/whence/tests/*.py`. | HIT if the count lands in [900, 1300] inclusive. |
| **P2** | Between **150 and 300** of those functions contain at least one *magnitude* assert under round 494's own `_count_asserts` predicate (O2). | HIT if in [150, 300]. |
| **P3** | Between **200 and 400** contain at least one *shape* assert (a comparison against a non-empty list/set/dict/tuple **display literal**, including `sorted(...) == [...]`). | HIT if in [200, 400]. |
| **P4** | **THE HEADLINE.** The number of *shadow candidates* — test functions where a magnitude assert precedes a shape assert in execution order — is between **25 and 70**. | HIT if in [25, 70]. |
| **P5** | The count is **at least 10**, i.e. round 494's node was not a one-off. | HIT if >= 10. Deliberately weaker than P4 so P4 can miss on magnitude while the direction still scores. |
| **P6** | The single file with the most shadow candidates is **`test_polarity.py`** (one of the three files round 494's next-step named as unswept). | HIT only if it is the strict maximum. |
| **P7** | The total number of *shape asserts made conditionally unreachable* across all candidates exceeds the candidate count by at least 40% (i.e. `shadowed_shape_asserts >= 1.4 x candidates`). | HIT if the ratio >= 1.4. |
| **P8** | At least one candidate **outside** the corpus-census family (`test_testcorpus_census.py`, `test_testcorpus_contributions.py`, `test_testcorpus_suite_census.py`, `test_depthcensus.py`) has a shadowing magnitude literal that git history shows has been **edited 3 or more times**. | HIT if >= 1 such node exists. |
| **P9** | The **median** number of literal edits per shadowing magnitude assert, over all candidates, is **1** (most have never moved since the line was written). | HIT if the median is exactly 1. |
| **P10** | `test_testcorpus_census.py` **still** contains at least one shadow candidate after round 494's fix — because round 494 moved one node and the file has 22 `ROUND NNN:` paragraphs. | HIT if >= 1. |
| **P11** | At least one shadow candidate lives in a `test_vNN.py` version file (the ordinary language-feature tests), proving the defect class is not confined to the census family. | HIT if >= 1. |
| **P12** | The sweep, applied to **its own new test file**, finds **0** shadow candidates in it. | HIT if 0. |
| **P13** | The full AST sweep over all 71 files runs in **under 3 s** solo. | HIT if wall < 3.0 s. |
| **P14** | Collecting git line-history for every candidate costs **more than 60 s** — which is the reason the "has this shadow ever fired" question has never been asked. | HIT if wall > 60 s. |
| **P15** | Fewer than **25%** of shadow candidates have their shadowing magnitude assert nested inside an `if`/`for`/`while`/`try` (i.e. most shadows are straight-line and unconditional). | HIT if the fraction < 0.25. |
| **P16** | Reproducing the two RED-DEBT `harness/tests/test_redattrib.py::TestThisTree` nodes solo, at HEAD, **reproduces both as red** (they are a genuine tree fact, not the runner) — in contrast with round 496's `nuc` node, which was green solo. | HIT if both fail solo. |

## Pre-registered, NOT scorable this round

- **P17.** Splitting a shadow candidate into two nodes changes node ids, so any
  node this round splits will appear to `harness/redattrib.py` as a *new* node
  with no episode history. If any split node ever goes red, its `reddebt` line
  will say `NEW` when the underlying assertion is years old. This is round
  494's next-step #2 question arriving from the other direction, and it can
  only be observed in a later round's health log.
