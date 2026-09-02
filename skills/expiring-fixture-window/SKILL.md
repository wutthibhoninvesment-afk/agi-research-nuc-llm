---
name: expiring-fixture-window
description: Use when a test, benchmark or check mixes a HARD-CODED absolute date/time/window with a data source that keeps growing — an append-only log, an audit trail, a metrics store, a journal, a ledger, a git history, a "latest N records" table. Symptoms the user will describe: a test that "started failing on its own", a suite that broke with no code change, a CI failure whose diff is empty, a fixture with a literal like 2026-08-31T00:00:00Z next to a call that reads the live production file, an assertion whose value jumped to something the size of "the whole most recent gap", or a test that has passed for months and asserts nothing that could fail. Covers deriving fixture windows from the data instead of from a literal, telling the LOUD failure mode from the QUIET one, and the neighbouring class of counts/positions pinned over an append-only file.
---

# A fixture window is a claim about the future, and it expires

A test that reads a live, growing file and bounds it with a hard-coded date is
making an undeclared assumption: *this file will not outgrow this window.* The
assumption is true when the test is written and false at a date nobody chose.
Nothing in the diff says so, because there is no diff — wall-clock did it.

The two failure modes are not equally visible, and the invisible one is worse.

**LOUD.** An assertion depends on the window. The day the data passes
`covers_to`, the bound the code was supposed to produce collapses to something
much larger, and the test fails with a number that reads like an instrument
regression rather than an expired fixture.

**QUIET.** No assertion depends on the window. The fixture simply covers a
shrinking prefix of a growing file, the test stays green forever, and it stops
testing its own subject. Nobody investigates a passing test.

Real instance (round 382 of this program). A continuity checker was covered by
a test that pinned a synthetic boot history and journal capture to
`2026-08-25T00:00:00Z .. 2026-08-31T00:00:00Z` — chosen five days earlier to
span an append-only reachability log — and asserted
`max_unobserved_outage_s <= 301.0`. The next round's own first record landed at
`2026-08-31T00:05:32Z`, **5m32s past `covers_to`**. The newest gap fell outside
coverage, its bound reverted to the gap's full length, and the assertion read
`15108.0 <= 301.0`. Its neighbour in the same file pinned
`2026-08-26T00:00:00Z..20:00:00Z` and had been silently vacuous for four days.

## When to use (triggers)

- A test or check reads a path under `state/`, `logs/`, `var/`, a database, or
  anything described as append-only, and a date/timestamp literal appears in
  the same function.
- A suite "started failing on its own", or a CI job went red with an empty
  diff, or a failure reproduces locally but nobody changed anything.
- A fixture supplies a coverage window, retention window, `since`/`until`,
  `covers_from`/`covers_to`, or a synthetic history to a function that also
  takes live data.
- A test asserts a COUNT, INDEX or POSITION over a file that grows —
  `len(x) == 29`, `verdicts == ["down", "down"]`, `results[1]`. Same class:
  a pin over a moving denominator.
- Reviewing a green test whose assertions do not mention the fixture it
  builds.

## Steps

1. **Reproduce and read the number, not just the failure.** The assertion's
   actual value is the diagnosis. A bound that jumps to "the length of the
   most recent gap" or "the whole span" means coverage ran out; a bound that
   moved by seconds means the data moved. Do not start editing thresholds.
   *Outcome:* the failing value, and which of the two it is.

2. **Find the boundary and check the clock against it.** Grep the test for
   date literals, convert them, and compare to the newest record in the live
   file. If the newest record is past the literal, the fixture expired; the
   code is innocent.
   *Outcome:* "expired at `<literal>`; newest record `<ts>`; overrun `<Δ>`".

3. **Derive the window from the data.** Replace the literals with values read
   from the live source, with a margin:
   ```python
   recs = load(LIVE_PATH)
   lo = ts(recs[0]) - MARGIN
   hi = ts(recs[-1]) + MARGIN
   ```
   Put it in one helper both tests call, so the next fixture cannot re-pin.
   *Outcome:* no absolute date remains in executable test code.

4. **Pin the failure you just fixed, deliberately.** Add a test that truncates
   coverage one unit short of the newest record and asserts the bound
   degrades — that the expired behaviour is *understood*, not merely absent.
   Without it the next expiry looks like a new bug again.
   *Outcome:* a named regression test for the coverage-hole behaviour.

5. **Hunt the QUIET twin in the same file.** The loud one announces itself; its
   siblings do not. For every other test touching the same live source, ask:
   *does any assertion here depend on the fixture I just fixed?* If none does,
   the test is vacuous — fix the window AND assert the claim its comment makes.
   *Outcome:* each sibling either asserts something window-dependent or is
   documented as deliberately window-independent.

6. **Sweep mechanically, both halves.** A grep for dates over-reports. Parse
   instead: functions carrying a date literal in *executable* code (not the
   docstring) that also reference a repo-rooted path or a live-file constant.
   ```python
   # per function: DATE.search(body_outside_docstring) and REPO_PATH.search(body)
   ```
   Then sweep the count/position half separately: assertions comparing a
   length, an index or a literal list of per-record values against a live file.
   *Outcome:* a count of candidates and a verdict for each — most will be
   synthetic `tmp_path` fixtures and genuinely safe.

7. **Decide what each survivor should assert instead.** A count over a growing
   file becomes a monotone invariant (`>= 29`, "grows with the log") or a
   structural one (`set(verdicts) == {"down"}`). A window becomes derived. If
   a number genuinely must be pinned, freeze the INPUT — copy the file to a
   fixture — rather than pinning an output of the live one.
   *Outcome:* each survivor either derived, structural, or reading a frozen
   snapshot.

## Pitfalls

- **Widening the threshold "fixes" it and destroys the test.** `<= 301.0`
  becoming `<= 20000.0` passes forever and asserts nothing. The failing value
  is not noise to be accommodated; it is a different code path being taken.
- **The quiet mode is the common one.** A window pin only fails loudly if some
  assertion depends on it. Most do not, so most instances of this class are
  sitting green right now, testing less each day. Counting only the red ones
  under-counts the class systematically.
- **Fixing the window without asserting the subject leaves it vacuous.** Round
  382's quiet instance asserted `boot_history_boots == 1` and
  `journal_seconds_loaded == 0` — both true regardless of coverage. Deriving
  its window changed nothing until the claim in its own comment was asserted.
- **A date in a `tmp_path`-only fixture is fine.** Synthetic data with a
  synthetic date is self-consistent forever. The defect needs a LIVE source on
  the other side; flagging every date literal buries the real ones. (One repo:
  178 functions carried a date, exactly 3 touched a growing file.)
- **Historical dates about an immutable past region are fine too.** "The
  2026-08-29 outage ended at 02:10:07Z" is a fact, not a window. Ask whether
  wall-clock advancing can change the assertion's truth.
- **The sibling test is where the pattern lives.** Round 352 removed a
  `== ["up", "up"]` count pin and left the `== ["down", "down"]` twin one
  function below untouched, where it waited for the next outage. When you fix
  one, grep for its twin before closing.
- **Your own sweep tool has this bug too.** An auditor that requires a numeric
  literal will skip the fully-derived constants that are its own target state,
  and report progress it did not cause. Run the sweep against a known-bad
  historical revision and require it to fire.

## Verification

Against the tree this skill was written from (`nuc/`, round 382):

```
$ python3 -m pytest nuc/tests/test_reachability_check.py -q
# expected: >= 230 passed (round 459; was written as a bare output line,
#           which parses as a COMMAND — see claim_check's C005)

# the expired fixture, before the fix
E       assert 15108.0 <= 301.0          # == the full 376->382 gap, 4h11m48s
```

The mechanical sweep, step 6:

```
$ python3 /tmp/window_sweep2.py
178 function(s) carry an absolute date in executable code
1 of those also touch a repo-rooted (growing) file
```

— i.e. 177 of 178 date literals are safe synthetic fixtures. The class is rare
and worth finding precisely; a plain `grep 20[0-9][0-9]-` returns noise at
178:1 against signal.

Step 4's regression witness must show the degradation, not merely the fix:

```python
full = report(recs, silence=make_silence_fn(capture))
assert full["max_unobserved_outage_s"] <= step_s + 1
lost = report(recs, silence=make_silence_fn(truncated_by_one_second))
assert lost["max_unobserved_outage_s"] >= last_gap_seconds
```

Related: `carried-claim-rot` (a claim repeated without re-derivation),
`rerun-before-you-record` (a durable record from one nondeterministic run),
`lazy-fill-ceiling` (a measurement read as a bound).
