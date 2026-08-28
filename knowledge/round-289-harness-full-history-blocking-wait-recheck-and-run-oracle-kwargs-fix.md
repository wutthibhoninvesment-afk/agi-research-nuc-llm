# Round 289 — harness(A) — full-history `blocking_wait_gap_s` recheck corrects the round 223/265/283 mechanism claim, plus a real `run_oracle` gap it led to

## Pre-flight

`ps -eo pid,ppid,etime,cmd` showed only this round's own driver process tree
(no concurrent research round). `git diff --cached --stat` was empty.
`git status --short` showed the standing 4 Hermes-owned untracked
`languages/whence/` files, confirmed unchanged (identical mtime to every
prior round's observation) — left alone.

## Context

Round 283's backlog item 2 flagged `is_blocking_wait_kill`'s
`min_gap_s=100.0` default as chosen from only two known clusters (0s vs.
200s+) with "a wide margin either side," and explicitly said: "if a future
round ever produces a genuine blocking wait in the 10-100s range... the
threshold may need revisiting." Round 283's own analysis was scoped to just
5 logs (`logs/round-{210,222,224,263,278}.json`) — every `interrupted`
round anyone had looked at closely by hand across rounds 223/265/283.

## What this round did

### 1. Extended the analysis back to round 152 (not just the 5 known logs)

Ran `summarize_turns`/`blocking_wait_gap_s`/`last_assistant_tool_use`
against every `logs/round-*.json` on disk (152 through 288 — 137 files;
`round-289.json`, this round's OWN still-in-progress log, was correctly
excluded after noticing it showed up as a spurious 18th "interrupted"
hit purely because the round wasn't finished yet — a live round's own log
will always look unfinished from inside itself; worth remembering for any
future round that runs this same kind of self-scan mid-round). Found
**17 real `interrupted` rounds**, not 5:

| round | gap (s) | last-assistant tool | last-overall event type |
|-------|---------|----------------------|--------------------------|
| 169   | 0.0     | Bash                 | assistant (same event)  |
| 176   | 0.0     | Bash                 | assistant (same event)  |
| 177   | 0.0     | Write                | assistant (same event)  |
| 210   | 0.0     | None (plain text)    | assistant (same event)  |
| 224   | 0.0     | Bash                 | assistant (same event)  |
| 192   | 9.214   | Bash                 | user (tool_result)      |
| 174   | 27.771  | Bash                 | user (tool_result)      |
| 162   | 87.791  | Bash                 | user (tool_result)      |
| 173   | 88.912  | Bash                 | user (tool_result)      |
| 164   | 189.397 | Bash                 | user (tool_result)      |
| 278   | 207.193 | TaskOutput           | user (tool_result)      |
| 222   | 303.512 | Bash                 | user (tool_result)      |
| 263   | 338.590 | TaskOutput           | user (tool_result)      |
| 194   | 363.588 | TaskOutput           | user (tool_result)      |
| 236   | 505.828 | TaskOutput           | user (tool_result)      |
| 197   | 584.158 | Bash                 | user (tool_result)      |
| 185   | 2912.156| Bash                 | user (tool_result)      |

### 2. This corrects, not just extends, the round 223/265/283 diagnosis

Round 283's own docstring for `is_blocking_wait_kill` claimed 222/263/278
were "genuinely, synchronously blocked on a tool result" — implying the
tool call never returned before the driver's outer `timeout` killed the
process. Directly re-reading the raw events for **all 12 nonzero-gap
rounds** (162,164,173,174,185,192,194,197,222,236,263,278) shows every
single one's LAST event overall is a `type: "user"` **tool_result that DID
arrive** — not a dangling `tool_use`. Only the 5 exact-`0.0`-gap rounds
(169,176,177,210,224) actually end on the assistant's own event with
nothing after it.

The real, corrected story for every nonzero-gap round: the last tool call
(Bash or TaskOutput, 9s to 2912s) finished and returned a result, and then
the round died with no wall-clock budget left for a further assistant
turn. There is no dangling-tool-forever mechanism anywhere in this dataset
— `blocking_wait_gap_s`'s value in this shape is dominated by **how long
that one last tool call happened to take**, which is a confound (an
ordinary command duration), not proof of a harness hang.

### 3. The gap distribution is a smooth continuum, not two clusters

Sorted: 9.214, 27.771, 87.791, 88.912, 189.397, 207.193, 303.512, 338.590,
363.588, 505.828, 584.158, 2912.156. Round 283's "well below the smallest
confirmed instance (207.193s)" framing for the old 100.0 default was an
artifact of only having sampled the extremes (0 and 200+) — the middle
(9–89s: rounds 162/173/174/192) was real, on-disk data nobody had checked.
Under the old default, those 4 rounds silently read `False` despite
sharing the exact same structural shape as the "confirmed" instances.

**Fix**: `min_gap_s` default lowered `100.0` → `1.0` — still comfortably
above float/CLI-flush jitter around exact `0.0`, comfortably below every
confirmed nonzero gap (smallest: 9.214s) — so the boolean now tracks the
real structural split (`gap > 0` vs. `gap == 0`) rather than an arbitrary
cutoff partway through one continuum. Docstrings for both
`blocking_wait_gap_s` and `is_blocking_wait_kill` rewritten to describe the
corrected mechanism. 3 new regression tests pin rounds 192, 174, and 185
(the smallest confirmed gap, a mid-continuum one, and the new extreme);
`test_is_blocking_wait_kill_respects_custom_min_gap` rewritten with
0.5s/0.1s values so it still demonstrates threshold sensitivity under the
new default.

### 4. Root-caused round 185's own extreme case (2912.156s) — a real bug, now fixed

Round 185's last Bash call (`harness/tests/test_swe_guest.py`-adjacent
exploratory work, not a test file itself) ran a one-off `python3 -c`
script: build ONE shared `GuestHarness` (avoids re-parsing the ~800-line
`self_eval.lang` library per case) and call
`swe.guest.oracle_self_eval(pkg, src, harness=h)` **directly**, across 4
hand-written test cases. One case was self-recursive with no base case:
`fn f6() { let t7 = f6()\n sqrt(num(2.0)) }`.

`oracle_self_eval` has no timeout of its own — the SIGALRM wall-clock
guard lives in `harness/swe/oracles.py`'s `run_oracle`, which wraps
whichever oracle function it looks up in `ORACLES[name]`
(`oracle_self_eval` is itself registered there as `GUEST_ORACLE`). But
`run_oracle`'s old signature was `(name, pkg, src, timeout_s, max_depth,
root)` — **no way to pass `harness=`** through to the wrapped call. A
caller who genuinely needs a shared harness (exactly round 185's situation)
is structurally forced to call the oracle function bare, silently losing
the timeout.

Reproduced directly (bounded, safe): a fresh `GuestHarness` + the same
`f6` program, called bare —

```
timeout 6 python3 -c "... G.oracle_self_eval(pkg, src, harness=h) ..."
# exit 124 — did not return within 6s
```

A second standalone run of the identical script (no bash timeout wrapper)
completed in **7.8s** — confirming the duration is genuinely load/timing-
dependent (the guest interpreter, built via `harness_for`/
`GuestHarness.__init__` with no `max_depth` passed, recurses to
`Interpreter.DEFAULT_MAX_DEPTH` = 20000 through the *doubly-interpreted*
self-hosted evaluator before its depth-Miss even fires — not a true
infinite loop, but expensive and apparently sensitive to system load, which
plausibly explains the 7.8s → 2912s range between a quiet re-run and the
actual live round).

**Fix**: `run_oracle(name, pkg, src, timeout_s=3.0, max_depth=500,
root=WHENCE_ROOT, **kwargs)` — `**kwargs` forwarded to
`fn(pkg, src, max_depth=max_depth, **kwargs)`. Every existing call site
(`fuzz_guest`, `fuzz_oracles`, `review.py`, all of `test_swe_oracles.py`)
passes no extra kwargs, so this is a pure addition — verified by grepping
every `run_oracle(` call site in the repo. Two new tests in
`harness/tests/test_swe_guest.py`:

- `test_run_oracle_forwards_kwargs_to_the_oracle_fn` — a shared, mutated
  (`_broken_harness`) harness passed via the new kwarg produces the SAME
  mismatch a bare call would, proving it's genuinely reaching the oracle
  function, not silently ignored.
- `test_run_oracle_kwargs_bounds_a_shared_harness_hang` — monkeypatches
  `eval_program` to `time.sleep(30)` (the real `f6` recursion's duration is
  too load-dependent to assert on directly in a test, per the 6s-vs-7.8s
  finding above) and confirms `run_oracle(..., harness=h, timeout_s=0.5)`
  now returns `kind="timeout"` instead of hanging — the actual mechanism
  under test (kwargs reaching the oracle so the SIGALRM wrapper can bound
  whatever that harness ends up doing).

Not fixed this round (flagged as backlog, deliberately out of scope): a
default `max_depth` for the guest-side interpreter itself
(`GuestHarness.__init__`/`harness_for` currently always build it with none,
relying entirely on `run_oracle`'s SIGALRM as the only guard even in the
NORMAL `fuzz_guest` campaign path) — that's a deeper, more speculative
change touching depth-skew semantics shared with language(C)/SWE-loop(D)
territory, and the `run_oracle` kwargs fix already closes the specific gap
that let round 185 bypass the existing safety net.

## Verification

- `harness/tests/test_driver_health.py`: 88 → **91 passed** (3 new pins for
  rounds 192/174/185; 1 existing test's fixture values updated for the new
  1.0s default, same assertions/shape).
- `harness/tests/test_swe_guest.py` (the file `run_oracle` and the fix live
  next to): full run (`python3 -m pytest harness/tests/test_swe_guest.py
  -q`, backgrounded — this file is real-interpreter-driven and slow by
  construction, ~minutes) — see research-state.md for the final count,
  confirmed passing before this round's commit.
- `bash harness/run_tests_fast.sh`: **403 passed, 194 deselected** (400 →
  403: the 3 new `test_driver_health.py` pins; `test_swe_guest.py`'s own 2
  new tests are `swe_slow`-marked and correctly excluded from this fast
  tier, consistent with `run_tests_fast.sh`'s documented scope).
- The `f6` self-recursion hang itself independently reproduced twice by
  hand outside pytest (bash `timeout 6` → exit 124; a second untimed run →
  7.8s) before writing the deterministic monkeypatch-based test — the real
  end-to-end shape is documented here rather than asserted flakily in CI.

## Files changed

- `harness/driver_health.py` — `blocking_wait_gap_s`/`is_blocking_wait_kill`
  docstrings rewritten to the corrected mechanism; `min_gap_s` default
  `100.0` → `1.0`.
- `harness/tests/test_driver_health.py` — 3 new pinned regressions (rounds
  192/174/185), 1 existing test's fixture values updated.
- `harness/swe/oracles.py` — `run_oracle` now accepts and forwards
  `**kwargs`.
- `harness/tests/test_swe_guest.py` — 2 new tests
  (`test_run_oracle_forwards_kwargs_to_the_oracle_fn`,
  `test_run_oracle_kwargs_bounds_a_shared_harness_hang`).

## What's still open

1. A default `max_depth` for `GuestHarness`/`harness_for`'s guest-side
   interpreter (see "Not fixed this round" above) — real, but a bigger,
   more speculative change than this round's scope; flagged for a future
   harness(A) or SWE-loop(D) round with more headroom to check depth-skew
   semantics carefully first.
2. Backlog item 12 (`session-inheritance-audit/SKILL.md` near its 400-line
   cap) — untouched this round, unrelated track.
3. `check_round_recorded.py`'s `git_committed`-coverage gap (round 283's
   backlog item 3) — untouched this round, owned by skills(B).
4. language(C)/SWE-loop(D)'s open fuzz/oracle-coverage items for Whence
   v0.14.7's nested-record-literal-field shape (round 288's next-steps
   item 1) — untouched this round, unrelated track.
