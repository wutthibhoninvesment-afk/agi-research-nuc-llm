# Round 522 (language C) — predictions, banked BEFORE measuring

Rule D-013. Written after reproducing the 10 reds and after reading
`subjprov.compare_with_census`, and BEFORE regenerating anything or
running `readset blast` on round 521's actual diff.

## What is already established (not predictions)

- All 10 red nodes reported by the driver reproduce SOLO, serially, in one
  `pytest` process: `10 failed, 112 passed in 114.08s`. They are NOT the
  round-434/nproc=1 contention shape.
- The single cause is round 521's (SWE-loop D) legitimate fix to
  `languages/whence/tests/test_polarity.py` (commit `760b5b2`): a scratch
  `.lang` file was written into the LIVE `languages/whence/` directory and
  raced `shutil.copytree` in three harness suites. The fix moved it to
  `tempfile.mkdtemp` and added `import shutil`, shifting every line below
  `test_the_two_counterexamples_disagree_when_actually_run` by +15.
- `subjprov.compare_with_census` (subjprov.py:1018) pairs the on-disk
  census against the LIVE tree by `a["lineno"] == p["magnitude_line"]`,
  with `prov = "unknown"; subjects = {}` as the un-matched default.
- Measured consequence: all SIX `test_polarity.py` census rows now report
  `prov=unknown, subjects={}`. `unknown_residual` 5 -> 11, `tree` 12 -> 8,
  `local` 31 -> 29, `disagree` 3 -> 7, `agree` 56 -> 52.

## Predictions

**P1 — `readset blast` could not have warned round 521.**
`python3 harness/readset.py blast languages/whence/tests/test_polarity.py`
will implicate NONE of the four reddened suites.
*Confidence 0.75.*

**P1b —** the recorded map (`harness/readset-map.json` or wherever
`DEFAULT_MAP` points) contains ZERO node keys whose file lives under
`languages/whence/tests/`. *Confidence 0.60.*

**P2 — regeneration in the RIGHT order closes all 10.** Regenerating
`state/whence/assert-shadow-census.json` FIRST, then
`state/whence/subject-provenance.json`, turns all 10 red nodes green with
no test-source edit. *Confidence 0.70.*

**P2b — the order is load-bearing and there is a wrong one.** Regenerating
`subject-provenance.json` BEFORE the census bakes the six bogus `unknown`
rows into the ledger permanently. Every one of the 10 nodes then goes
GREEN on a WRONG number: `test_the_residual_is_small_named_and_never
_counted_as_derived` would still fail (it hard-codes 5 and four file
names), but `test_the_ledger_on_disk_matches_the_live_tree`,
`test_the_ledger_totals_are_the_sums_of_its_own_rows` and
`corpusledger`'s two nodes would all agree on `unknown_residual = 11`.
*Confidence 0.85.*

**P3 — `corpusledger.py --fix` does NOT model the dependency.** It
regenerates its ledgers in a fixed order (registry/alphabetical), with no
edge saying `subject-provenance.json` is DOWNSTREAM of
`assert-shadow-census.json`. *Confidence 0.60.* If true this is the second
finding of the round: a generated artefact whose input is another
generated artefact, in a regenerator that treats them as independent.
*Sub-prediction P3b: alphabetically `assert-shadow-census.json` sorts
before `subject-provenance.json`, so `--fix` gets the right answer by
ACCIDENT. Confidence 0.70.*

**P4 — subjprov's own `--check` cannot name this fault.** It reported the
drift only as changed TOTALS and changed ROWS (S001/S003). There is no
finding code that says "the census points at a line the live tree has no
assert on". Consequently, had the six rows' provenance happened to be
`unknown` already, `subjprov --check` would have said the ledger agrees
while the census was stale. The ONLY instrument that named the true cause
is `assertshadow.check_coordinates` (`MOVED ... ledger 706/708 -> tree
721/723`). *Confidence 0.70.*

**P5 — the fix's yield is exactly 6 now and exactly 0 after.** Adding a
staleness gate to `compare_with_census` that reports census pairs whose
`magnitude_line` matches no assert in the live function will report
exactly 6 rows on the tree as it stands, and exactly 0 after the census is
regenerated. *Confidence 0.85.*

**P6 — the residual population is the hiding place.** No existing whence
test fails when a census coordinate is stale AND the resulting `unknown`
count is not one of the two hard-coded literals. i.e. the guard on this
whole class is two integer literals in one test function
(`test_the_residual_is_small_named_and_never_counted_as_derived`), not a
structural check. *Confidence 0.65.*

## Scoring

Scored honestly in `knowledge/round-522-*.md`, misses included.
