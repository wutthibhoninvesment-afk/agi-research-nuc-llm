# Round 512 — predictions scored (D-013)

Banked in `predictions.json` (P1-P8, before any measurement) and
`predictions-2.json` (P9-P12 after scoring P1-P8; P13 and P14 each banked
immediately before the run that decided them). **11 kept, 3 missed.**

| id | verdict | what actually happened |
|----|---------|------------------------|
| P1 | KEPT | The merged map has keys for all four reddened suite files. |
| P2 | KEPT | Their `scans` sets contain `languages/whence/tests`. |
| P3 | KEPT | `blast languages/whence/tests/test_branchlive.py` names all four, reason `scan`. |
| P4 | KEPT | Not a detector gap. The instrument had the signal. |
| P5 | KEPT | No usable staleness line: the merged map's `head` is `""`, so `staleness()` returns "no git HEAD available on one side; cannot compare". |
| P6 | KEPT | Regenerating exactly two ledgers closed all 7 red nodes with no test-source edit *required*. (One further edit was made by choice — see P-note below.) |
| **P7** | **MISSED** | Predicted no other ledger was stale. **Three of five were stale, not one.** `assert-shadow-census.json` had been stale since round 500 (72→76 files, 1935→2029 test functions, 3908→4122 asserts) and `subject-provenance.json` was stale with **no red at all**. This was the round's main finding and I predicted its opposite. |
| P8 | KEPT | 20 files named, 4 actually red — precision 20%. The four are not distinguishable from the sixteen. |
| P9 | KEPT | The ledger-gate predicate selects fewer than 20. |
| **P10** | **MISSED** | Predicted the predicate would miss `test_subjprov.py` through the subprocess hole. It **caught** it — another node in that file reads the census in-process. |
| **P11** | **MISSED** | Predicted it would catch all three in-process readers. At NODE granularity it missed `test_testcorpus_census.py`, whose scan and whose ledger read land on different nodes via a module-scoped fixture — readset's own documented aggregation problem. Recomputing at FILE granularity gives recall 4/4, precision 4/6. |
| P12 | KEPT | `test_v31.py` scans the dir behind a `glob` import; nothing it asserts is a function of the directory's contents as a set. |
| **P13** | **MISSED** | Predicted `depthcensus.py --tests --by-file --json` does not run as written, because usage says `--tests suite\|default`. It runs fine: `--tests` takes an **optional** value guarded by a membership test against `("suite","default")`. Both cited forms produce byte-identical output. A usage string is not a parser. |
| P14 | KEPT | All five generators are byte-deterministic across two runs at fixed HEAD. This is the precondition the whole design rests on, which is why it was banked before being relied on. |

**P-note (honest scope creep).** P6 said "no source edit to any test", and that
is true of what the 7 reds *required*. But regenerating the census moved
`totals.pairs` 57 → 58, which exposed
`test_subjprov.py::test_every_census_pair_finds_its_assertion` asserting
`[len(rows), census_pairs] == [57, 57]`. That node was **green while the
ledger was twelve rounds stale**, because both sides of the comparison read
the same stale number. Round 512 split it into the invariant (`len(rows) ==
census_pairs`, total in what drifts) and a separate pinned size, per round
494's decision 64. That is one more changed test file than P6 anticipated,
and it is recorded here rather than folded into the "as predicted" column.

## What the three misses have in common

P7, P10 and P11 are all the same error: **I predicted the behaviour of an
instrument from its stated purpose rather than from its predicate.** P13 is
the same error one level down — I predicted a parser's behaviour from its
usage string. In every case reading the actual predicate took under a
minute and gave the opposite answer. That is the rule this round earns, and
it is the same rule the round's *finding* states about ledgers: what a check
is named for and what its predicate ranges over are different things, and
only the second one is load-bearing.
