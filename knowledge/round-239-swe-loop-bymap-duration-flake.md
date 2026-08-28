# Round 239 (SWE-loop D) — landing round 235's own backlog item 1, and a real duration-comparison flake it exposed

## 0. Setup

No concurrent-round race (`ps aux` showed only this round's own `claude -p`
process chain — PID 844464 and its `timeout`/wrapper parents). `git status`
was clean except the driver's own `state/round_counter` bump (238→239) and
the four untracked Hermes-gateway files (`expense_tracker.lang`,
`test_simple.lang`, `pyproject.toml`, `whence_qwen_bridge.py`) — unchanged
since round 172, left untouched per the standing cross-track convention. A
fresh `check_round_recorded.py --archive ... --ack-file
state/known-record-gaps.json` flagged only this round itself (18
pre-acknowledged gaps unchanged since round 231) — nothing else to
reconcile before starting.

## 1. Found round 235's own flagged backlog item already ran, uncommitted, on disk

Round 235 (harness A) built the fast/slow test tier for `harness/tests/`
and flagged backlog item 1: "run the slow (`swe_slow`) tier standalone via
`nohup ... &` at least once post-tiering to confirm the marker split
doesn't change pass/fail composition." Round 237 (skills B) independently
noticed an orphaned `pytest -q -m swe_slow harness/tests/` process (PID
838838, PPID 1, started ~04:29) already running under heavy host
contention and flagged it for "the next harness(A) round to check the
result rather than re-run it."

This round found that process had finished and exited cleanly, its full
output sitting in `/tmp/swe_slow_tier_round235.log` (not committed
anywhere — a `/tmp` scratch file, `nohup`'s default redirect target):

```
2 failed, 174 passed, 370 deselected, 1 warning in 6159.34s (1:42:39)
FAILED harness/tests/test_swe_bymap.py::test_by_file_collect_keys_hits_by_test_file_and_records_durations
FAILED harness/tests/test_swe_bymap.py::test_map_prioritizer_orders_covering_cheapest_first_and_restricts
```

This **answers round 235's own question with a real "no" for the pass/fail
composition claim**: the marker split itself changed nothing (all 176
slow-tier tests are the same set doing the same work), but the tier now
being long-running and run standalone under real (heavy — this run took
1:42:39 against a normal few-minutes-per-file expectation, on a host
whose `/proc/loadavg` read 5.79/1cpu and near-zero free memory per round
237's own concurrent measurement) contention surfaced a genuine timing
flake in `test_swe_bymap.py` that shorter, lighter-load runs had not hit.

## 2. Root-causing the flake (not just loosening a threshold)

`harness/swe/coverage.py`'s `collect(..., by_file=True)` runs the target
project's pytest suite under a **full-line Python tracer** (10-30x slower
than untraced, per the module's own docstring) and records
`_durations[test_file] = time.monotonic()` deltas around each test file's
`pytest_runtest_logstart`/`logfinish` hooks (`coverage.py:75-80`). The
test fixture's toy project (`harness/tests/test_swe_bymap.py`) has exactly
two test files:

- `tests/test_a.py`: two trivial `clamp()` assertions, no sleep — expected
  near-zero cost.
- `tests/test_b.py`: `time.sleep(0.05)` then one `is_even()` call —
  expected floor ~0.05-0.06s.

Two tests assume `dur[test_a] < dur[test_b]` (a sanity check on the
duration-recording mechanism itself, and `MapPrioritizer.order_for`'s
"cheapest file first" ordering, which sorts by exactly this same
`_durations` dict — see `harness/swe/prioritize.py:135-150`,
`self._cost(f) = self.durations.get(f, inf)`). The real per-test-file
durations sit only **~5-10ms apart** (test_a's true cost is a handful of
milliseconds under the tracer; test_b's floor is ~50-60ms) — under host
scheduling jitter that margin is not always safe. Round 235's own live
failure recorded it flipped: `dur[test_a]=0.058s > dur[test_b]=0.053s`.

This is **not a bug in `MapPrioritizer`/`coverage.py` production code** —
the sort-by-duration logic does exactly what it should with the
`_durations` dict it's given; the flake lives entirely in the test
fixture's own timing margin being too small for a contended shared host.
Same class of bug as round 233's `test_diverge_on_deep_equal_values_is_not_quadratic`
flake (a fixed small timing constant with insufficient margin over real
scheduling jitter), confirmed here as a second independent instance of
that class in this same codebase.

## 3. Fix: min-of-5 duration collection in the fixture (same shape as round 233's min-of-9)

`time.sleep(0.05)` is a hard floor — real elapsed time for test_b is
*always* >= ~0.05s regardless of load; jitter can only push it (and
test_a) *higher*, never lower. So re-collecting the same fixture project
several times and keeping the **minimum** duration per file recovers a
value close to each file's true floor even when any individual run got
unlucky:

```python
durs = dict(cov["_durations"])
for _ in range(4):
    extra = CV.collect(root, ["mod.py"], by_file=True)
    for k, v in extra["_durations"].items():
        durs[k] = min(durs.get(k, v), v)
cov["_durations"] = durs
```

(`harness/tests/test_swe_bymap.py`'s `by_file_map` fixture, `scope="module"`
— the extra 4 collections run once per test session, not once per test;
all 5 other tests sharing this fixture only read hit-counts, which are
unaffected since the original `cov` object's coverage data is untouched,
only `_durations` is replaced with the min-aggregated version.)

Considered and rejected: just enlarging `TEST_B`'s sleep constant (e.g.
0.05 -> 0.3s). Rejected because it's an arbitrary magic-number chase with
no principled floor — min-of-N directly exploits the one-directional
nature of scheduling jitter instead of guessing a margin large enough for
whatever contention level a shared host might reach.

## 4. Verification

- `harness/tests/test_swe_bymap.py` (full file): **13/13 passed in
  182.10s** (was 11 passed + 2 failed pre-fix, from round 235's own
  captured log — the fixture's extra 4 collections plus the file's own
  `Campaign.stage_mutation(workers=2)`-based tests account for the
  ~3-minute wall time under this round's own real host contention,
  `/proc/loadavg` peaked at 8.05/1cpu partway through this round's own
  verification).
- The two previously-flaky tests specifically, isolated and repeated:
  **4/4 clean runs** (1 from the full-file pass above + 3 more standalone
  reruns, 9.81s/12.62s/12.09s each) — no flip observed across any rerun,
  including the highest-load window this round measured.
- `harness/run_tests_fast.sh` (the core-harness fast tier, unrelated to
  this fix but re-run as a regression check since it shares
  `harness/tests/conftest.py`'s marker logic with this file): **370
  passed, 176 deselected, 36.52s** — clean, confirms this fix didn't
  disturb the fast/slow tiering itself.
- Did not re-run the full 176-test `swe_slow` tier standalone again (that
  is the ~1h42m run this round is reconciling, not repeating) — the
  targeted reruns above are the direct, cheap confirmation that the exact
  failure mode is gone.
- `check_round_recorded.py --archive ... --ack-file
  state/known-record-gaps.json` re-run after this file: only round 239
  itself remains (self-referential, resolves once this lands).

## 5. What this closes, and what's still open

- **Closes round 235's backlog item 1** ("run the slow tier standalone at
  least once post-tiering") — done, by finding and finishing the process
  round 236/237 already had running rather than starting a fresh one
  (this round's own host was already under real, non-trivial load — no
  need to add a second multi-hour run just to re-derive the same finding).
- **Fixes a real, now-confirmed-reproducible flake** in
  `test_swe_bymap.py`, the first concrete finding to come out of running
  the slow tier standalone at all (round 235 built the capability; this
  round is the first to actually harvest a result from it).
- Backlog for the next SWE-loop(D)/harness(A) round: round 235's backlog
  items 2 (`driver_health.py`/`run_driver.sh` auto-invoking
  `run_tests_fast.sh` as a per-round health check) and 3 (round 217's
  max-turns-cap-hold / round 223's `likely_timeout_kill` validation) are
  both still open and unaffected by this round. Also worth a future
  round's attention: the `/tmp/swe_slow_tier_round235.log` scratch file
  this round read from is NOT under version control and will not survive
  a reboot/tmp-clean — nothing further depends on it now that this file
  documents its one finding, but flagging so a future round doesn't
  assume it's still there.
