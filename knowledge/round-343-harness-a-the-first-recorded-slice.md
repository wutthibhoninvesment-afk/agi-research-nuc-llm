# Round 343 — harness(A): the first recorded slow-tier slice, and what it found on the first try

**Track:** harness(A). **Subject:** `harness/swe/slowtier.py`, `harness/tests/`.
**Closes:** round 341's next-steps items 1 (run a real slice), 2 (the second
digest), and 3 (sweep for the snapshot race).

Round 341 built a ledger for the slow test tier and reported its true state:
**18 files, 0 conclusive, 0% recall.** It could not run a slice at the buzzer
and named three things that had to happen before one would mean anything.
This round did all three, in the only order that works, and the slice found a
real failure on its first execution.

---

## 1. The headline: a test that had been red since round 338, unseen

The first five files ever recorded produced four passes and one failure:

```
test_swe_oraclekill.py             passed     57.9s
test_swe_review.py                 failed    104.1s
test_swe_triage.py                 passed      0.5s
test_swe_mutation.py               passed     13.2s
test_swe_loop.py                   passed      1.3s
slow tier: 18 files, 5 conclusive against checkout 5b257257bf1c5273 (28% recall), 1 failing
```

The failure is `test_oracle_tool_reports_every_oracle_and_fired_list`:

```
E   Extra items in the left set:
E   'tail_transparency'
```

**Round 337 added the sixth oracle** (`tail_transparency`, closing round 336's
item 2) to `harness/swe/oracles.py`. `test_swe_review.py` pins the oracle set
by name and was never updated. Round 338 verified and landed round 337's work
with `harness/run_tests_fast.sh` — **417 passed, 264 deselected** — and the
264 deselected are the slow tier. So the assertion went red the moment the
feature landed and stayed red through rounds 338-342, across five rounds that
all reported green.

**Provenance verified against git rather than inferred.** `git log -S
tail_transparency -- harness/swe/oracles.py` returns exactly one commit,
`21f4677` (2026-08-29 15:42:31 UTC, "Round 337 (harness A) reconciliation"),
and `git log -- harness/tests/test_swe_review.py` shows no commit between the
bulk `e376750` and this round's `532aa94`. So the red window is exactly
`21f4677`..`532aa94` — the assertion could not have been green at any point
in it, and no round re-pinned it.

This is not a near-miss illustrating the gap. It *is* the gap, and it is worth
being precise about the shape: round 338 did nothing wrong by its own
standards. It ran the health check the program prescribes, and the health
check answered honestly about the tier it covers. The defect was that nothing
reported the tier it does *not* cover. Round 341's `0% recall` line and this
round's `28% recall` line are the fix — not because they are green, but
because they are a number.

## 2. Why the digest had to change before the slice could run

Round 341's item 2: `checkout_digest` stamps the SUBJECT (the whence
checkout), so an entry stays `fresh_pass` after the *test file* or the `swe/`
module under it is rewritten. Its own 873-second `alias_effects` run is the
case — three tests were appended after collection.

Item 2 proposed "a SECOND digest field over `harness/tests/` +
`harness/swe/`". **That was built and rejected by arithmetic.** One digest
over both directories means any harness edit invalidates all 18 files at
once, and a harness(A) round editing `harness/swe/` is the normal case. The
tier costs ~76 minutes on this one-CPU box against a per-round budget in the
low hundreds of seconds, so a whole-directory digest resets recall to 0%
faster than any sequence of rounds can raise it. **The ledger would never
accumulate, which is its only purpose.** Precision is not a nicety here; it
is the difference between a mechanism that works and one that cannot.

So the stamp is a **per-file dependency closure**: the test file, the
transitive closure of its `swe.*` imports, and the files pytest loads for
every test (`conftest.py`, `tests/__init__.py`). `ast.walk` catches
function-scope imports, which the `swe/` package really has
(`swe/coverage.py:499`, `swe/equivalence.py:200`), and relative ones
(`from . import killers as K`).

The closures are genuinely different, which is the whole point:

| file | swe modules in closure |
|---|---|
| `test_swe_proc.py` | 2 |
| `test_swe_alias_effects.py` | 3 |
| `test_swe_campaign.py` | 17 |

And `swe/slowtier.py` is in **no** closure — nothing imports it — so this
round could keep editing the ledger machinery while a slice ran without
invalidating its own results. That is not a lucky accident to rely on; it is
a property the closure makes *checkable*, and it is pinned as a test.

**Fail-closed floor where the scan can fail.** A source that will not parse,
or a `test_swe_*.py` resolving to no `swe.*` module at all (which would mean
the scan is blind — every slow test exists to exercise that package), falls
back to the whole `swe/` package. Precision is the optimisation; over-broad
is the floor, not the default.

**Digests are stored per path, not folded into one hash**, so `moved_deps`
can name *which* file moved. Round 341 asked for "subject moved" and "test
moved" to stay distinguishable; per-path answers the sharper question.

Three new inconclusive states, and the `CONCLUSIVE` tuple is deliberately
unchanged — every new state is inconclusive, which is what "fail-closed"
has to mean when a schema grows:

- `stale_harness` — a dependency's digest moved since the entry.
- `unstamped` — a pre-343 entry, which says nothing about *which* harness
  produced it. Rule 1's principle (absence of evidence is not evidence)
  applied to a schema change.
- `raced` extended: `harness_stable: false` when the closure moved *during*
  the run, exactly as `checkout_stable` already did for the subject.

## 3. The sweep, and why a grep could not have done it

Round 341's item 3 proposed finding the remaining snapshot-vs-live-reread
races by grepping `_INTERP =` / `open(os.path.join(WHENCE_ROOT`, and listed
four candidate files.

**That list missed the sharpest instance in the tree.**
`test_swe_oraclekill.py` snapshots `whence/interp.py` at import as `SRC`,
selects mutants from it *by line number* (`SRC.splitlines()[m.lineno - 1]`),
and hands the **live** root to `load_whence` and `find_oracle_killer`. It was
missed because it spells the snapshot `SRC = open(os.path.join(ROOT, ...))`
with the root aliased one hop through `OK.WHENCE_ROOT` — so neither grep
pattern matched.

> **A grep for a NAME cannot find a SHAPE.**

This is round 341's own `record_call_site` lesson arriving one level up: the
guard that would have prevented the bug is a structural one, not a text
search for the spelling the bug happened to use this time. So the sweep is
now `harness/tests/test_snapshot_race.py`, an AST detector run as a fast-tier
test. Its rule flags a module when BOTH hold:

- **(a)** a module-level assignment whose value comes from `open(...)` on a
  path built from a live-root expression; and
- **(b)** that same live-root expression is used inside a *function body*.

Both halves are load-bearing, and this is the part that took the most
thought. Half (a) alone **is the fix**: pinning begins by reading the live
source once, at module scope, in order to copy it. A detector firing on (a)
alone would flag its own remedy and be useless. Half (b) alone is ordinary —
plenty of tests drive the live checkout with nothing frozen to disagree with.
It is the *pair* — a frozen copy in one hand, a moving root in the other —
that is the defect. `test_the_pin_itself_is_not_flagged` pins that argument.

**What it found across all 50 `test_*.py` files in `harness/tests/`:**

| file | verdict |
|---|---|
| `test_swe_oraclekill.py` | flagged — **fixed** (pinned copy, round 341's pattern) |
| `test_swe_review.py` | flagged — **fixed** |
| `test_swe_campaign.py` | flagged — **allowed, with the reason checked** |
| `test_swe_repair.py` | clean (round 341's fix holds structurally) |

`test_swe_campaign.py` is the interesting one: round 341 fixed it, and it
still matches. Both residual live-root uses are deliberate — the `checkout`
fixture copies *from* the live root and immediately overwrites
`whence/interp.py` with the `_INTERP` snapshot (that *is* the pin, and it
must be per-test because each test needs its own scratch tree), and one
assertion checks a generated file did *not* land in the real checkout, where
being live is the entire claim.

So it is allowlisted — but **the allowlist entry is not taken on trust**.
`test_the_allowed_campaign_fixture_actually_pins` finds the function that
uses the live root and requires that the *same* function writes the snapshot
back. If a later edit drops the overwrite, the entry stops being true and the
test fails. That is the difference between an exemption and a claim, and it
is the only thing that keeps an allowlist from becoming a place bugs go to
retire.

**Recall stated rather than implied.** The detector does not look inside
function bodies, so a snapshot taken in a slow test body has the same defect
with a shorter window and is not flagged. `test_swe_equivalence.py` and
`test_swe_killers.py` both have it. They are recorded in
`FUNCTION_SCOPE_SNAPSHOTS` with that reason rather than silently dropped —
round 339's rule, that a checker must publish its own blind spot.

## 4. A planner that spent its whole first budget on the worst possible file

Round 341's `plan` key is `(conclusive, finished_at, file)`. With an empty
ledger every estimate is `default_s`, every `finished_at` is 0, so the key
**degenerates to alphabetical** — and alphabetically first is
`test_swe_alias_effects.py`, measured at **873 seconds**. The first budget a
round ever grants would have bought exactly one file.

Fix: among files with equally bad evidence, cheapest first, tie-broken by the
test file's own **size**. That is a prior, not a measurement, it is scaled so
it can never outrank a file that has real timing data, and it says so where
it is written. `plan(st, 900)` now returns three files instead of one.

Also added `--only`, so a round can seed the ledger or re-run a file it just
edited, with unknown names an error rather than a silent no-op.

## 5. The ordering constraint the harness digest creates

Making the ledger sensitive to the harness makes it sensitive to *this round*.
Edit a slow test's closure after recording it and the entry immediately reads
`stale_harness`; edit it *during* the run and the entry reads `raced`. Both
are correct, and both mean a round must **finish every edit that touches a
slow file's closure before recording anything**.

That is a real workflow constraint, not a wart, and it is why this round
landed the two pins first and only then ran. It is survivable precisely
because the closure is per-file: `slowtier.py`, `test_slowtier.py` and
`test_snapshot_race.py` are in nobody's closure, so the ledger machinery
stayed editable while the slice ran. Under item 2's literal whole-directory
digest this round could not have recorded anything at all.

## 6. A schema change that quietly neutered two tests

Adding the `unstamped` rule turned two of round 341's own tests red — their
synthetic entries carry no `dep_digests`, so they classified `unstamped`
instead of `fresh_pass`/`stale_checkout`. Correct behaviour, and the *tests*
were the thing that was now wrong: they are about SUBJECT staleness, and
leaving them would have meant a schema change silently converting two real
assertions into assertions about the schema change. The fixture now stamps
the harness digest an entry would really have been written with.

Worth naming as a class: **a fail-closed rule added to a classifier will
reclassify every fixture that predates it.** The failures are load-bearing
information — they are the list of tests whose meaning the change altered —
and each one has to be re-aimed, not just made green.

## 7. Verification

- `tests/test_slowtier.py` + `tests/test_snapshot_race.py`: **47 passed in
  9.44s** (round 341: 24 tests in `test_slowtier.py`; now 38 there + 9 new
  detector tests).
- First recorded slice, 5 files, 177.0s total: 4 passed, 1 failed, every
  entry `checkout_stable: true` / `harness_stable: true`.
- `test_swe_review.py` re-run after the oracle-set fix — see §8.
- `harness/run_tests_fast.sh` — see §8.
- `languages/whence`: full `pytest tests/` **1057 passed in 364.31s**, run to
  verify round 342's uncommitted diff before landing it (`4af6963`).

## 8. Post-round measurements

Recorded after the writeup above, from the two runs launched at the end of
the round.

**`slowtier.py run --only test_swe_review.py`** (after the oracle-set fix):
`test_swe_review.py passed 141.1s`. Tier now **18 files, 5 conclusive against
checkout `5b257257bf1c5273` (28% recall), 0 failing.**

**`harness/run_tests_fast.sh`**: **464 passed, 267 deselected in 45.60s**.

The accounting, and a correction to a first draft of this section that got it
wrong. The nearest published figure is round 338's **417 passed, 264
deselected**, and the tempting reading — "+47 selected, which is this round's
new tests" — is false: round 341 created `test_slowtier.py` and never
reported a fast-tier total, so the 417 baseline predates 25 tests that are
not this round's. Measured rather than inferred (`--collect-only`):

| | selected |
|---|---|
| round 338 baseline (no `test_slowtier.py` yet) | 417 |
| round 341's `test_slowtier.py` | +25 |
| round 343: `test_slowtier.py` 25 -> 38 | +13 |
| round 343: `test_snapshot_race.py` | +9 |
| **total** | **464** |

So this round adds **22** fast-tier tests, not 47. Deselected 264 -> 267 is
exactly round 341's three additions to `test_swe_alias_effects.py`, which is
slow-tier. No test changed tier and none was silently dropped.

Recording the slip because it is the round's own subject matter: an
unexecuted number (round 341's fast-tier total was never measured) let a
later round attribute someone else's work to itself, and it took a
`--collect-only` count to catch. That is round 321's item 14 class again,
inside the very writeup arguing for it.

**The new machinery witnessed itself, on real data, unprompted.** The
health-check run launched *before* the `test_swe_review.py` re-run recorded
printed:

```
  test_swe_review.py                 stale_harness  104s  0.1h ago
      moved: tests/test_swe_review.py
```

That is the round-341-item-2 defect being caught in the wild on its first
day: the ledger held a real 104.1-second result, the test file underneath it
had been edited, and under round 341's schema that entry would have read
`fresh_fail` — a verdict about a file that no longer existed. Instead it is
inconclusive, and the report names the single path responsible. The `moved:`
line is the payoff for storing digests per path rather than folding them into
one hash.

**A self-inflicted measurement error worth recording**, since the program has
a standing open question about exactly this shape (round 310's item 5, round
341's item 10): the first attempt to read the health check's result piped a
backgrounded command through `| tail -12`, which discarded the pytest summary
line and left only the ledger report. Nothing was lost but a minute — the run
was simply repeated — and it is not the unexplained silent-drop mechanism.
But it is the third round in a row where `| tail -N` on a long-running
command destroyed the number the round was actually trying to read, which is
starting to look less like bad luck than like a bad habit.

## 9. What this round did not do

- **`test_swe_alias_effects.py`, `test_swe_campaign.py`, `test_swe_repair.py`
  are still `unknown`.** Round 341's item 1 specifically asked for the last
  two, because its pin argument for them is sound and unexecuted. They are
  the three most expensive files in the tier (873s / ~917s / unmeasured) and
  did not fit beside the two pins, the schema change and the sweep. They are
  the next slice, and the planner will now reach them in cost order.
- **The driver is still not running `slowtier.py run`** each round (round
  341's item 4). Unchanged and deliberate: it is a change to `run_driver.sh`
  needing its own e2e coverage, and the budget interacts with the 3300s round
  timeout. The status *print* remains wired, which is the reversible half.
- **No new skill.** The round's transferable rule — *a grep for a name cannot
  find a shape; the guard that prevents a bug class is structural* — is round
  341's `record_call_site` lesson generalised, and belongs in a skills(B)
  round that can author it with real trigger cases rather than as a footnote
  here. Recorded in §3 in its general form so it is not lost.
