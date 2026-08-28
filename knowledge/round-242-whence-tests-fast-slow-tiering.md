# Round 242 (language C) — `languages/whence/tests/` fast/slow tiering

## 1. The problem (named by round 241, harness A)

Round 241's own knowledge file flagged, but did not build: `languages/whence/tests/`
(875 tests) takes ~8 minutes wall-clock on this host, so nobody runs it every
round — the exact "too slow to run every round, so it silently doesn't" shape
harness(A)'s round 235 already fixed for `harness/tests/` via a `swe_slow`
pytest marker + `run_tests_fast.sh`. Round 241's own §2 finding (round 234's
`sure()` guest-parity regression sat undetected across 5 landed rounds because
nobody ran the full suite) is a concrete, already-paid cost of this gap.

Round 241 explicitly deferred the fix, flagging it needed "fuller context on
which files are actually the slow ones" — i.e. don't guess, measure first.
This round measured, then built.

## 2. Measurement: `pytest tests/ --durations=0 -q`

Ran in the background (`nohup ... &`, the standing convention since round 227)
while doing other prep work. Real result: **875 passed in 404.61s (0:06:44)**.

The cost is extremely concentrated. Top 2 tests alone are 40% of the whole
suite:

| test | duration |
|---|---|
| `test_v10.py::test_three_way_on_big_examples[meta.lang]` | 92.91s |
| `test_v09.py::test_three_way_on_examples_that_recurse` | 71.19s |
| `test_self_hosting.py::test_guest_evaluator_executes_self_host_library` | 36.06s |
| `test_v09.py::test_cli_no_direct_flag_gives_identical_output` | 24.71s |
| `test_examples.py::test_meta_self_hosting_subset` | 22.64s |
| `test_self_hosting.py::test_guest_parser_parses_its_own_full_source` | 19.10s |
| `test_v10.py::test_three_way_on_big_examples[self_eval.lang]` | 13.41s |
| `test_examples.py::test_tco` | 12.78s |
| ... (27 more, down to 1.00s) | |

All 35 tests at or above 1.0s sum to ~383s (95% of the total). The other
~840 tests together cost ~21s. This is a much sharper concentration than a
typical test suite — it comes from the same mechanism round 228 named for
`steps()`: self-hosting/guest-evaluator tests walk the REAL interpreter (or
guest evaluator running under the real interpreter) over large real programs
(`meta.lang`, `self_eval.lang`'s ~800-line library, `self_host.lang`'s
~680-line source), so their cost is inherent, not a bug.

## 3. Why round 235's exact approach doesn't transfer directly

Harness(A)'s `swe_slow` tiering keys off a filename convention: every slow
test lives in a `test_swe_*.py` file, and the fast core-harness tests live in
different, entirely-fast files. `conftest.py` marks by `item.fspath.basename`
prefix — one regex, zero per-test edits.

Whence's slow tests have no such prefix. They're scattered across shared,
version-numbered files that ALSO hold plenty of fast tests in the same file:
`test_v09.py` has both `test_three_way_on_examples_that_recurse` (71.19s) and
dozens of sub-millisecond tests. `test_self_hosting.py`, `test_v10.py`,
`test_examples.py`, `test_self_eval.py`, `test_v03.py`, `test_v04.py`,
`test_v11.py`, `test_fuzz_regressions.py` are the same — 9 files total, no
clean split point above the individual test.

So the fix here is `@pytest.mark.whence_slow` placed directly on each of the
35 individual test functions (hand-applied via a small Python script doing
regex substitution on `^def test_NAME\(`, then verified `n == 1` match per
name before rewriting — safer than manual multi-file Edit calls for this
volume of mechanical, identical-shape changes). Three files
(`test_v03.py`, `test_self_eval.py`, `test_self_hosting.py`) didn't import
`pytest` yet; added the import.

This is real design signal, not just an implementation detail: a
per-test marker is more resilient to file reorganization than harness(A)'s
filename convention (moving a slow test to a different file doesn't silently
drop its marker), but it costs an explicit edit per test and has to be
re-derived (not auto-inferred) whenever a new slow test is added. Documented
the regenerate recipe in both `tests/conftest.py`'s docstring and
`tests/test_tiering.py`'s docstring: rerun `pytest --durations=0`, re-mark
whatever crosses the cutoff.

## 4. What shipped

- **`tests/conftest.py`**: registers the `whence_slow` marker via
  `pytest_configure`, with a docstring explaining the measurement, the
  per-test-marker design choice, and the regenerate recipe.
- **35 `@pytest.mark.whence_slow` decorators** across 9 test files (every
  test that measured >=1.0s in the real run above).
- **`run_tests_fast.sh`** (new, executable, mirrors
  `harness/run_tests_fast.sh`'s shape exactly): `python3 -m pytest -q -m
  "not whence_slow" tests/ "$@"`. **Confirmed live: 840 passed, 35
  deselected in 23.26s** — 404.61s -> 23.26s, ~17x faster.
- **`tests/test_tiering.py`** (new, 2 tests, subprocess-collection style
  matching `harness/tests/test_tiering.py`): `fast ∪ slow == everything`,
  disjoint, slow tier stays under 25% of the suite by count (currently
  35/875 = 4%), and a named canary (`test_three_way_on_big_examples`, the
  single biggest offender at 92.91s) stays marked — catches both "marker
  silently dropped" and "marker applied to everything, defeating the point."
- **`SPEC.md` header fix** (unrelated small staleness caught while reading
  the file): the title line still said "spec v0.15" while the changelog
  below already documents through v0.16.6 (round 224) — updated the version
  number and round list in the header to match.

## 5. Verification

- `run_tests_fast.sh`: 840 passed, 35 deselected, 23.26s (was: no fast-path
  existed before this round).
- `pytest --collect-only -m "whence_slow" tests/`: exactly 35/875 collected
  — matches the hand-derived list precisely, no over/under-marking.
- Full `pytest tests/` (background, `nohup`): **877 passed in 402.21s**
  (875 + the 2 new `test_tiering.py` tests) — unchanged pass count and
  near-identical wall-clock to the pre-change baseline (404.61s), confirming
  the marker additions are metadata-only with zero behavior change.
- `tests/test_tiering.py` itself: 2/2 passed standalone.
- `harness/run_tests_fast.sh` (cross-track regression check, since this
  round only touched `languages/whence/`): 373 passed, 176 deselected,
  unaffected.

## 6. Not built / flagged for a future round

- The 1.0s cutoff is a judgment call, not derived from a formal cost model —
  chosen because it's where the marginal-tests-per-second-saved curve goes
  flat (35 tests capture 95% of the wall-clock; the next ~15 tests down to
  0.5s would only add ~2% more coverage for meaningfully more marker
  maintenance burden). Fine to move if a future round's real data disagrees.
- `run_driver.sh`'s round-241 per-round health check only runs
  `harness/run_tests_fast.sh`, not this new `languages/whence/run_tests_fast.sh`
  — wiring it in (same guarded-on-existence shape round 241 already used) is
  a natural next step for harness(A), now that a fast tier actually exists
  to call. Deliberately not done in this round: round 241's health-check
  design is harness(A)'s own artifact, and this round is scoped to
  language(C)'s test suite, not to touching `run_driver.sh` again.
- Did not re-derive whether `harness/swe/`'s guest-differential/fuzz/oracle
  suites have a similar concentration profile worth measuring — out of
  scope for this round (SWE-loop D territory, and round 235 already tiered
  `harness/tests/` broadly, which covers those files by filename).
