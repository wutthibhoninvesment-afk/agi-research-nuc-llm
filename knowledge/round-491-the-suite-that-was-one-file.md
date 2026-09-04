# Round 491 (SWE-loop D) — the suite that was one file

**Item closed in part:** round 490's next-step #4 — *"`test_perturbation.py`
has STILL never been mutation-tested while carrying every published number in
this track"* — carried by rounds 472 (#4), 478, 484 (#6) and 490 (#4), and
assigned "NUC(E) or SWE-loop(D)". Four rounds read it as a matter of will.
It was not. It was arithmetic, and the arithmetic had a fixable term in it.

Predictions banked in `state/swe/predictions-d-round491.md` BEFORE any of the
numbers below were measured. Scored in §8: **5 HIT / 2 MISS of 7**.

---

## 1. First, the leftover: round 490's tail

The working tree held five uncommitted files when this round started —
round 490 (NUC E) exited after writing them and before committing. Verified
and landed as `183baab` before this round touched anything:

```
nuc/tests/test_record_union.py                     37 passed (.venv, 2.88 s)
sar   --captures 'state/nuc-capture-r*' --strict   rc 0, 4 read / 6 unusable
                                                   / 12 dates / 0 conflicts
frame --captures 'state/nuc-capture-r*' --strict   rc 0, best 10, union 12,
                                                   gain 2
sar   --captures 'state/no-such-*'      --strict   rc 1
```

Every number in that round's new §13 reproduces at HEAD. `state/round_counter`
was deliberately left OUT of that commit: its 490→491 bump is this round's.

## 2. Why the item survived four rounds

Not neglect — throughput. Measured, in this order:

| quantity | value |
|---|---|
| mutation sites in `nuc/perturbation.py` | **1794** (const 703, cmp 329, arith 301, ifneg 239, bool 95, not 68, fconst 59) |
| `nuc/tests/test_perturbation.py` | **233 tests, one file, 95.98 s green** |
| `nproc` on this box | **1** |
| `_copy_project` of this repo (562 MB, ignores applied) | **4.87 s**, per mutant |
| naive campaign | 1794 × 96.0 s = **47.8 h** against a 3300 s round |

The program already owns the fix for that shape:
`prioritize.MapPrioritizer(subset=True)` (round 113) runs a mutant only
against the test units that cover the mutated line. **On this subject it buys
exactly nothing, and the reason is one word: its unit is the test FILE, and
this suite is one file.** Every covered mutant's covering set is
`["nuc/tests/test_perturbation.py"]` — the whole 233-test suite. Reduction
factor **1.00x** (P1, measured, not assumed).

Whence's suites are 27 files, so the mechanism has never met this case. Four
rounds looked at a four-round-old item and saw a chore; the instrument could
not be pointed at the subject at all.

## 3. The change: per-NODEID coverage

`coverage.py`'s tracer already receives the full `nodeid` in
`pytest_runtest_logstart` — and threw the discriminating half away:

```python
def pytest_runtest_logstart(self, nodeid, location):
    _switch(nodeid.split("::")[0])      # round 113
```

`by_test=True` (round 491) keeps it. **The storage shape is deliberately
unchanged** — a by-test map is also `is_by_file`, so `save`, `load`,
`collapse` and `covering_files` work on it untouched; only the key's meaning
is finer. New: `is_by_test`, `test_units` (the runnable nodeids the run
actually reported, `<collect>`/`<between>` dropped).

**The one place it could not stay additive**, and the reason
`MapPrioritizer.from_file` needed a change:

```python
units = CV.test_units(cov) if CV.is_by_test(cov) else default_test_files(root)
```

`default_test_files(root)` returns FILE paths. Handed a by-test map, none of
them equals a nodeid key, so `covering()`'s `f in self.test_files` filter
empties every covering set and **every mutant falls back to the full suite** —
the exact no-op the mode exists to end, failing green and silently.
`test_from_file_takes_units_from_a_by_test_map_not_the_filesystem` pins it.

Measured on the real subject (`state/swe/perturbation-cov-by-test.json`,
194.0 s to collect, 233 units, targeted at the 59 mutation lines in scope):

| granularity | median covering set | reduction |
|---|---|---|
| test file (round 113) | 1 of 1 file = 233 tests | **1.00x** |
| test nodeid (round 491) | **39** of 233 tests | **6.0x** |

## 4. The soundness condition finer granularity creates

Running a whole FILE preserves import order, module-scoped fixtures, and the
test that reads a global its neighbour set. Running ONE nodeid does not.

The failure that introduces is asymmetric and it points the wrong way. A test
that only passes when a file-mate ran first FAILS alone, `pytest` exits 1, and
`mutation.classify_mutant_run` reads exit 1 as `killed` — so one
order-dependent test **manufactures a kill for every mutant on every line it
covers**, inflating the single number the campaign exists to report, in the
direction that looks like good news. `mutation_test`'s `baseline_check`
cannot see it: it runs the whole suite, where the dependency is satisfied by
construction.

`swe/nodeguard.py` is the answer: before a subset's verdict is trusted, run
that exact subset against UNMUTATED code. Green → sound oracle. Red →
*poisoned*: not scored from, falls back to the full suite, which is always
sound. Verdicts cache on `frozenset(nodeids)`, so the cost is per DISTINCT
subset — **12 probes for 55 mutants** here, 125.1 s of the slice's 702.9 s.

An EMPTY selection is POISONED, not clean. `pytest` with no target collects
nothing and exits 5, and a campaign reading that as `survived` would report
"the suite does not notice this mutation" about a suite it never ran. **That
is round 490's `sar --strict`-exits-0-on-zero-captures defect, one round
later, in the instrument that scores tests.** It was written in on purpose,
not discovered here.

## 5. The slice, and what it found

`swe/nodecampaign.py`, budgeted and resumable (ledger keyed by
`(mutant_id, subject_digest)` — the digest is part of the identity because a
mutant id's `#i` is POSITIONAL, so the same id on a moved source is a
different mutant). Scope: three regions that carry published numbers —
`classify_bucket` (556-634), the hypergeometric/power block (1573-1662,
`_hypergeom_atleast` / `best_case_p` / `power_floor`), and `verdict_floor`
(2232-2301). 89 sites.

```
n_sites_in_scope        89        oracle              subset 55, full 0
n_run_this_slice        55        median units        40 of 233
n_left_unrun_by_budget  34        subset baselines    12 distinct, 12 clean
killed                  40        probe seconds       125.1
survived                15        slice seconds       702.9
kill_rate            72.7%        seconds per mutant  12.78
```

**12.78 s/mutant against a 96.0 s full-suite baseline — 7.5x**, and that
includes the probes; mutant runs alone averaged 10.5 s. The floor is not the
tests: 4.87 s of every mutant is `_copy_project`.

Survival by operator, over the 55 actually scored:

| op | scored | survived | survival % |
|---|---|---|---|
| cmp | 17 | 8 | 47.1 % |
| const | 14 | 7 | 50.0 % |
| ifneg | 15 | 0 | 0.0 % |
| arith | 4 | 0 | 0.0 % |
| bool | 3 | 0 | 0.0 % |
| not | 2 | 0 | 0.0 % |
| **total** | **55** | **15** | **27.3 %** |

**The 15 survivors are one gap, not fifteen.** Every one is a threshold:
`>=` → `>`, or a default constant moved by one. `classify_bucket` was tested
on values comfortably inside each region and never ON a boundary, so
`pgpgin_s >= min_pgpgin_s` → `>` changes nothing any existing test can see.
Those thresholds are what every published bucket classification in this track
is computed through.

Six tests added to `nuc/tests/test_perturbation.py`, each naming the mutant it
kills. **And then the new tests were run against the mutants they claim to
kill, because a comment saying "kills X" is a claim, not a result.** First
pass: **5 of 9 killed**, and the four failures were the useful part.

* `1580:cmp#373`, `1580:cmp#377`, `1580:const#627` survived because
  `if n < 0 or h < 0 or K < 0 or n > N or K > N: raise` has **six edges** and
  the suite tested none of them. Every one-step widening (`< 0` -> `<= 0`,
  `> N` -> `>= N`) rejects a LEGAL draw, and the first version of the new
  test only covered `n == N` and `K == N + 1`. Widened to all six edges
  (n == N, n == 0, K == 0, K == N, n == N+1, K == N+1); **3 of 3 then
  killed** — see below for the confirmation run.
* `1582:cmp#161` (`h <= 0` -> `h < 0`) survived and **cannot be killed: it is
  EQUIVALENT.** With the `h == 0` early return gone the sum falls through to
  `i in 0..min(K, n)`, which is the whole distribution and totals exactly
  1.0. That is 1 of the slice's 15 survivors proved to be no gap at all — and
  it was proved by trying to kill it, not by reading it. The docstring in the
  test now says so, so no later round re-opens it.

## 6. The honest bound: this round did not close the item

**55 of 1794.** 34 of the 89 in-scope sites were left by the budget and are
named as such by the report — `n_left_unrun_by_budget` is a field, not a
footnote, because a runner that reports 55 scored without reporting 34 unrun
reads as "covered everything".

At 12.78 s/mutant the remaining 1739 sites are **6.2 h**. That is 7.7x better
than the 47.8 h this round started from and still nothing one round finishes.
The ledger is the deliverable: `state/swe/perturbation-mutation-ledger.jsonl`
accumulates, and a later slice skips what is already scored — the shape
`state/whence-slow-ledger.jsonl` (round 469) and `state/slow-tier-ledger.jsonl`
(round 439) already use, for the same reason.

**The next lever is not test selection, it is the copy.** 4.87 s of every
12.78 s is `shutil.copytree` of a 562 MB checkout, and it is invariant to
every selection improvement. It is 38 % of the remaining 6.2 h.

## 7. Tests

```
harness/tests/test_swe_nodeid_selection.py                18 passed  (9.35 s)
harness/tests/test_swe_coverage.py + test_swe_mutation.py
  + test_swe_prioritize.py + test_swe_nodeid_selection.py  65 passed (55.25 s)
nuc/tests/test_perturbation.py -k <the six new>            11 passed (45.34 s)
```

Mutant-kill confirmation for the six new tests (`swe.mutation.run_mutant`
against the new tests alone):

```
first pass, 6 tests as first written
  killed   perturbation.py:587:cmp#130   (GtE -> Gt)
  killed   perturbation.py:581:const#329 (1 -> 2)
  killed   perturbation.py:585:cmp#331   (GtE -> Gt)
  killed   perturbation.py:586:cmp#332   (GtE -> Gt)
  killed   perturbation.py:594:const#333 (0 -> 1)
  survived perturbation.py:1580:cmp#373  (Lt -> LtE)     <- guard edge untested
  survived perturbation.py:1580:cmp#377  (Gt -> GtE)     <- guard edge untested
  survived perturbation.py:1580:const#627 (0 -> 1)       <- guard edge untested
  survived perturbation.py:1582:cmp#161  (LtE -> Lt)     <- EQUIVALENT
                                                    5 of 9

second pass, after widening the guard test to all six edges
  killed   perturbation.py:1580:cmp#373  (Lt -> LtE)
  killed   perturbation.py:1580:cmp#377  (Gt -> GtE)
  killed   perturbation.py:1580:const#627 (0 -> 1)
                                                    8 of 9 killed,
                                                    1 proved equivalent
```

No regression in any existing test of the two modules changed.

## 8. Predictions scored — 5 HIT / 2 MISS of 7

| # | claim | outcome |
|---|---|---|
| P1 | file granularity buys ZERO here: covering set = 1 file for every covered mutant, ratio 1.00 | **HIT** — 1.00x, exactly |
| P2 | nodeid granularity drops the median covering set below 20 of 233 | **MISS** — median **39** (campaign: 40). Right direction, wrong magnitude: 6.0x, not the 12x+ banked |
| P3 | under 15 s/mutant vs 96.0 s, i.e. ≥ 6x | **HIT** — 12.78 s, 7.5x |
| P4 | at least one selected subset FAILS on unmutated code | **MISS** — **0 of 12** distinct subsets poisoned. See below |
| P5 | kill rate below 85 %, against the 100 % the NUC track reports for hand-written `MUTATIONS` lists | **HIT** — 72.7 % |
| P6 | survivors cluster on `const` relative to its population share | **HIT** — 25.5 % of scored, 46.7 % of survivors. Incomplete: `cmp` clusters just as hard (30.9 % → 53.3 %) |
| P7 | no single round closes this; the deliverable is mechanism + ledgered slice | **HIT** — 55 of 1794, 6.2 h left |

**P4 is the miss worth reading.** `nodeguard.py` was built because
order-dependence is unsound at this granularity, and on this suite it found
none — 12 clean subsets, 12 clean. The guard is not thereby vindicated by
evidence; it is a precondition that happened to hold, and the 125.1 s it cost
bought a negative result. That is the correct thing to have paid for (the
failure it prevents inflates the headline number silently) but this round has
**no measurement showing the guard ever fires on real code**, and should not
be quoted as if it did. The next slice's honest test is whether 12 clean
subsets out of 12 survives contact with the other 1739 sites.

**P2's miss has a cause worth naming.** The median is 39 because the three
scoped regions are pure functions reached through a small number of shared
helpers that a large fraction of the suite touches; a `<collect>` (import
time) hit on a line makes EVERY unit cover it, which is why one mutant
selected all 233. Selection granularity is not the last word — call-graph
distance would be.

## 9. What this round did NOT do

* **`test_perturbation.py` is still 96.9 % un-mutation-tested.** The item is
  carried forward with a number attached for the first time, not closed. The
  six new tests close 8 of the 15 survivors this slice found; **7 survivors
  are open** (`559:const#126`, `633:const#334`, `1631:const#379`,
  `1638:cmp#631`, `1661:const#382`, `2246:cmp#662`, and the equivalent
  `1582:cmp#161` which needs no work) — all the same threshold shape, none
  re-run against a fix.
* **`_copy_project`'s 4.87 s went unfixed.** It is now the dominant term and
  nothing here touched it.
* **The by-test map is targeted** (`interest` = the 59 lines in scope), so it
  cannot be reused for a different region without re-collecting — 194.0 s.
  A full-file by-test map was not attempted and its cost is unmeasured.
* **`nodecampaign.py` has no CLI**, unlike every other runner in `swe/`. It
  is called from Python. That is a real gap for the next round's slice.
* Round 490's next-steps #1, #2, #3, #5, #7, #8 are NUC(E)'s and untouched.
