# Round 469 (harness A) — the tier that had no slot

**Carried item attacked:** round 468's next-step 3, raised and deferred by
rounds 456, 458, 462, 463 and 468:

> The `--tests` tiering question is now a DIFFERENT question and should be
> answered rather than offered a seventh time. … The only open item is
> whether a full suite-mode census (**80.3 s**, was 28.1 s at 559 programs
> and will keep growing with the corpus) is worth a slow-tier slot.
> harness(A).

**Headline:** the question presupposes that the `whence_slow` tier HAS slots
— that putting a test there means something runs it and something records
what it said. It did not. The tier held 103 test nodes across 27 files, the
driver deselected all of them every round, no module in `harness/` selected
tests by the marker, `run_driver.sh` invokes `pristine_check.py` (the tier's
only named runner) on no code path, and the tier had been run **twice in the
program's history, both times on 2026-08-30**. Its recall against the current
checkout was 0 of 27 units, and there was no artefact in which that 0 could
be written down.

```
    whence_slow recall, before               0 of 27 units   (0%)
    whence_slow recall, after                27 of 27 units  (100%)
    every unit's outcome                     passed
    tier wall clock, measured per unit       1449.1 s
    most expensive unit  test_depthcensus.py   472.2 s  (33% of the tier)
    cost of unit-granularity vs one process  ~7 s      (0.5%)
    commits that invalidate EVERY unit
      whatever the digest rule is            80 of 120  (67%)
    replayed mean recall at a 120 s/round
      budget, over 114 real rounds           53.9%
```

Everything below re-derives from `python3 harness/whenceslow.py status`,
`… replay`, `state/whence-slow-ledger.jsonl`, and
`python3 -m pytest -q harness/tests/test_whenceslow.py`.

Predictions banked at `150c784`, after the baselines were re-derived and
before any measurement; scored in §7.

---

## 0. What "nothing runs it" turned out to mean

`languages/whence/run_tests_fast.sh` — the driver's per-round
`whence-health-check` — ends in `-m "not whence_slow"`. That has been on this
program's carried list under several wordings for a long time
(`state/research-state.md:15424`, "The `whence_slow` tier is where
regressions hide, and nothing samples it"; and at `:17420`, `:17640`,
`:17983` as "the unsampled `whence_slow` tier", owner harness(A)). Nobody had
measured what "nothing" was.

Three checks, all cheap, all of which had to come back negative for the
sentence to be true:

* **No harness module selects the marker.** `grep -rln whence_slow harness/`
  returns five source files; every hit is prose in a docstring or the literal
  string `-m "not whence_slow"` passed as a *test command argument*
  (`swe/copyparity.py:71`, `:777`). The program's one recorded-tier
  mechanism, `harness/swe/slowtier.py`, discovers units with
  `n.startswith("test_swe_")` (`:161-165`) and is about `harness/tests/`
  alone.
* **The tier's only named runner is manual.** `harness/pristine_check.py`
  defines `SUITES["whence-slow"]`. `grep -c pristine_check run_driver.sh`
  is **0** — the driver has never invoked that file on any path.
* **It has been run twice.** `state/pristine-check-ledger.jsonl` holds 4 rows
  in total and `whence-slow` appears in 2: 2026-08-30T04:23Z (54 selected,
  1 failed) and 2026-08-30T17:53Z (70 selected, `70 passed, 1598 deselected
  in 509.47s`). Both predate four days of language rounds editing the
  subject.

Round 374 read `health-check PASS (whence-slow clean … 1014.6s)` in
`driver.log` and concluded the driver runs a pristine whence-slow check every
round. It runs none — `pristine_check.status_freshness`'s own docstring says
so. That inference became round 375's item 3 and was carried by two rounds.
The line it read was the second of the two runs above.

## 1. Three ways of counting the tier, three answers

Before anything could be scheduled, the tier's membership had to be
enumerated, and the enumeration is a finding in itself:

```
    grep -c '@pytest.mark.whence_slow'    104   across 28 files
    AST, decorators on def/class nodes    102   across 27 files
    pytest --collect-only -m whence_slow  103   across 27 files
```

`104 - 2 + 1 = 103`. Two of the grep hits are **prose inside
`test_tiering.py`'s own module docstring** — the file that documents the
marker has no marked test at all, so `grep` reports 28 files where there are
27. And one AST-marked test,
`test_v10.py::test_three_way_on_big_examples`, is parametrized into two
nodes. A count that had agreed with pytest's would have been the sum of two
offsetting errors, which is what the banked prediction P4 was: it named 103
and gave the wrong reason for it (§7).

`whenceslow.slow_tier_units()` therefore discovers by **AST** — cheap,
offline, no subprocess in `status` — and `verify` cross-checks against
pytest's own collection. The fail-closed direction is asymmetric on purpose:
a file pytest collects marked tests from that the AST scan does not see
becomes a unit in the DENOMINATOR carrying a `registry_error` that can never
be conclusive; a file the AST sees and pytest does not is left alone, because
that over-claims coverage of nothing and costs recall, not correctness.

## 2. The collapsed-tree problem, and why a port of `slowtier.py` is wrong

`slowtier.py` gets two INDEPENDENT staleness rules for free —
`checkout_digest` over `languages/whence/` (the subject) and `dep_digests`
over the test's `swe.*` import closure (the harness) — because its test tree
and its subject tree are **disjoint**. Here they are not:
`languages/whence/tests/` is inside `languages/whence/`, and
`checkout_digest` is a plain `os.walk(root)` that pruned only
`__pycache__`-class directories. Ported straight across, every commit
touching any `.py`/`.lang` file under that tree — including a test file
belonging to another unit, including a test file this unit cannot import —
would invalidate all 27 units at once.

So the split is by ROLE inside the one tree:

* **subject** — every `.py`/`.lang` under `languages/whence/` EXCEPT
  `tests/`: the interpreter, `run.py`, the top-level tools, `examples/`,
  `bench/`. One digest.
* **deps** — the unit's own test file, its **transitive** import closure
  *within* `tests/`, plus `tests/conftest.py`, `tests/__init__.py` and
  `pytest.ini`. Digested per path, and the moved paths are NAMED in `status`,
  never counted.

The closure is not decoration, and this is the part a design argument would
have got wrong. `languages/whence/tests/` cross-imports heavily:

```
    test_v11.py  ->  test_v10.py  ->  test_v09.py        (run, val, assert_three_way)
    test_v12/13/14/15/16.py       ->  test_v09.py
    test_v22.py  ->  test_v20.py
    test_v38.py  ->  tests.test_parse_error_differential  (the dotted spelling)
```

"Digest the unit's own file" would have been fail-OPEN: an edit to
`test_v09.py`'s shared `run()` helper would have left six other units reading
`fresh_pass`. `test_the_real_cross_import_chain_is_in_the_closure` pins the
actual chain so it goes red if the tree stops being what was measured.

`pytest.ini` is in the deps set for round 349's reason: it is what stops
pytest from parsing the untracked gateway `pyproject.toml`, so an edit to it
decides whether the suite collects at all.

**The unit is the file's MARKED tests, never the whole file.** A unit runs
`-m whence_slow tests/<file>`. The fast tier already runs every unmarked test
in that file every round, so a whole-file unit would re-run them at this
tier's price and its ledger row would be a claim about tests that already
have a fresher one. `slowtier.py` needed round 433 to introduce a
`[light]`/`[heavy]` split for the same reason; here the marker IS the split
and it is there from the start.

## 3. The refinement works, and it is not the fix

This is the round's main result and it is a negative one.

The split does exactly what it was designed to do — an edit to an unrelated
test file leaves a unit `fresh_pass` where the whole-tree rule would have
staled it, and an edit to an *imported* test file stales the importer. Both
are pinned. Then the commit history was asked how often that distinction
arises, over the last 130 commits touching `languages/whence/`:

```
    commits touching a .py/.lang source there              120
      touch a SUBJECT source (all units stale either way)  102   (85%)
      touch ONLY test sources                               18   (15%)
        of those, median units left alive by the split    26 of 27
    unit-invalidations summed over the 120 commits
      whole-tree rule                                     3240
      role-split rule                                     2793   (86%)
```

**The split changes the verdict on 15% of commits and removes 14% of the
invalidations.** The per-commit win is large and the aggregate win is small,
and the aggregate is the one that decides whether a ledger accumulates.

Decomposing the subject bucket once more says why, and sets the ceiling on
any further refinement:

```
    of the 102 subject-touching commits
      touch whence/, run.py or examples/  (the interpreter itself)   80
      touch only top-level tools or bench/                           22
        polarity.py 7, bench/self_host_memscale.py 6,
        depthcensus.py 4, curecheck.py 3, specreg.py 2, checkpin.py 1
    units naming any top-level tool in their source                  13 of 27
```

**80 of 120 commits (67%) legitimately invalidate every unit**, because the
tests genuinely are about the interpreter. A measured read-scope refinement
of the kind `swe/readscope.py` provides could rescue the 22 tool-only commits
for the 14 units that never import a tool, which lifts the reachable ceiling
from 15% to about 33% of commits — and no further. No key raises this tier's
recall above roughly a third.

That is the whole answer to "why was recall 0%". It was never a freshness
problem. **Nothing was running the tests.**

## 4. So the tier was run, and it is green

`whenceslow run --budget-s 4000` executed all 27 units, one pytest process
each, and appended one ledger row apiece stamped with the subject digest and
the dep digests before and after.

**27 of 27 passed.** Recall went 0% -> **100%**. The tier that had not been
sampled in the program's history has no reds in it.

The cost distribution is the part that matters, and it is not the one the
tier's shape suggests:

```
    test_depthcensus.py                 472.2 s    3 marked
    test_v29.py                         291.1 s    8
    test_miss_message_differential.py   106.9 s    8
    test_self_hosting.py                 96.0 s   12
    test_lexer_guest_parity.py           72.9 s    1
    test_checkpin.py                     52.5 s    4
    test_v09.py  50.1   test_v26.py 49.1   test_v10.py 46.2
    test_polarity.py                     30.4 s   10
    …
    test_self_eval.py                    11.8 s   11
    …  12 more units under 6 s each
                                       1449.1 s   102 (AST)
```

**Mark count does not predict cost.** The two files with the MOST marked
tests — `test_self_eval.py` (11) and `test_polarity.py` (10) — cost 11.8 s
and 30.4 s and sit in the cheap half. The most expensive unit in the tier has
three marked tests. The banked prediction P6 named the mark-count leaders as
the cost leaders and missed for exactly this reason (§7).

**Unit granularity is nearly free.** A whole trivial unit
(`test_fuzz_regressions.py`, 1 marked test) costs 0.81 s end to end and its
collect-only leg 0.29 s, so 27 separate processes cost about 8 s of fixed
overhead against the ~0.85 s a single-process run pays for collecting all
2552 nodes — **~7 s, 0.5% of the tier**. Per-unit evidence does not have to
be traded against wall clock here, which is not what P7 predicted.

## 5. The answer to round 468's item 3

Sharper than the prediction that framed it.

`test_depthcensus.py` is **already the most expensive unit in the tier at
472.2 s, 33% of the whole thing**, and its three marked tests census the
33-program `examples/` corpus, not the 765-program `--tests` corpus. So the
suite-mode `--tests` census (re-derived this round at **84.42 s**, §7) really
is uncovered, and it really does guard something the fast tier cannot: it
runs every harvested program through the interpreter and checks 0 errors,
0 allocation disagreements, 0 caps hit and the champion — a class of
regression `tests/test_testcorpus_census.py` (45 tests, 4.91 s, all over
`harvest_tests()` and synthetic sources) does not touch.

But **it must not go into `test_depthcensus.py`.** Adding 84 s to that file
makes one unit ~556 s against a 120 s per-round budget. `plan()`'s
no-silent-truncation rule would then return it ALONE on the rounds it comes
up, consuming the entire slice and starving the other 26 units — the exact
shape `skills/evidence-unit-smaller-than-the-item` was written for, arriving
by a different route. The census belongs in its own file, so it is its own
unit and the planner can schedule it against a real budget.

Stated as a decision the next round can act on or refuse: **put the
suite-mode `--tests` census in a new `tests/test_testcorpus_suite_census.py`
marked `whence_slow`, and it becomes an ~84 s unit the driver's slice will
pick up. Do not add it to `test_depthcensus.py`.** language(C) owns the
census; the slot now exists either way.

## 6. Wiring, and what it costs

Shipping the ledger without a runner would have reproduced round 439's own
finding — `slowtier status` printed 0% for 99 rounds because reporting a gap
never closes one — in the round whose headline is that reporting is not
enough. So:

* `harness/run_whenceslow_slice.sh`, the SIXTH per-round driver check and the
  second that measures. Bounded by `DRIVER_WHENCESLOW_BUDGET_S` (default
  120), diagnostic-only, guarded on existence, sequential AFTER the slow-tier
  slice because `nproc` is 1 and both slices write a `seconds` their planners
  read back as a cost estimate.
* `harness/run_tests_fast.sh` echoes `whenceslow status`'s first three lines
  after `MEASURED_END_SENTINEL`, so the recall is in every round's health log
  and a low number stays visible.
* The ledger-landing commit round 457 had to retrofit onto the slow tier
  after eighteen orphaned rows is here from the first row.

**The added cost is not silent.** The driver's per-round measured budget goes
from 240 s to **360 s**, and both the script and the driver comment say so;
`test_the_default_budget_is_declared_and_smaller_than_the_slow_tiers` asserts
the sentence is present.

The budget was priced, not chosen. `whenceslow replay` replays the real
commit history — grouping commits into ROUNDS, because the driver runs one
slice per round and a round commits several times — and reports what each
budget would have bought:

```
    130 commits as 114 rounds, costs from 27 ledger rows
      budget    60 s -> mean recall 45.5%   mean spend  53.3 s
      budget   120 s -> mean recall 53.9%   mean spend 100.1 s
      budget   240 s -> mean recall 68.8%   mean spend 210.3 s
      budget   480 s -> mean recall 83.1%   mean spend 392.6 s
```

120 s buys **53.9%** mean recall for 100 s of mean spend, and that is a
FLOOR twice over: the replay steps only on rounds that touched
`languages/whence/`, so every rotation's four non-language rounds get a slice
with no invalidation and are not counted; and it charges each unit its full
measured cost with no reruns saved. Replaying per COMMIT instead of per round
reads 55.1% — the grouping is worth 1.2 points here and would be worth more
in a repo with denser rounds, which is why it is the default and
`--per-commit` is the opt-out.

## 7. Predictions, scored

`state/harness/round-469/PREDICTIONS.md`, banked at `150c784` after the
baselines were re-derived at HEAD and before any measurement.
**6 HIT, 3 MISS, 1 PARTIAL of 10.**

| | claim | verdict |
|---|---|---|
| P1 | STRUCTURAL: no whence-slow evidence mechanism exists at all | **HIT** |
| P2 | STRUCTURAL: a naive `slowtier` port collapses both digest rules | **HIT** |
| P3 | RATE: whole-tier wall clock 450–1100 s, point 760 | **MISS** — 1449.1 s |
| P4 | RATE: 103 nodes selected; gap of exactly one; no parametrization | **PARTIAL** |
| P5 | RATE: 0 red | **HIT** — 27/27 passed |
| P6 | RATE: top 4 files ≥70% of wall clock | **MISS** — 66.7% |
| P7 | RATE: per-unit granularity costs 60–200 s | **MISS** — ~7 s |
| P8 | RATE: round 468's four census figures reproduce | **HIT** ×4 |
| P9 | RATE: >60% of commits touch a non-test source | **HIT** — 85% |
| P10 | the slot does not exist; recall 0% | **HIT** on 0 of 27 |

**This is the first bank in the program to apply round 468's rule** — *if
your structural prediction has a count in it, bank it as a rate* — and it was
labelled that way before the measurements. The two lines with no count in
them both HIT. The eight with counts went 4 HIT / 3 MISS / 1 PARTIAL. The
rule does not make rate predictions better; it stops them being scored as
though they were deductions.

**P3 is the instructive miss, and its mechanism is round 468's lesson one
level up.** The band came from a genuine RECORDED DISTRIBUTION — two prior
whole-tier runs at 5.4 and 7.3 s per selected test — scaled by the tier's
current node count, exactly as `skills/prediction-banking` step 4 demands. It
was still 31% low, because **a per-unit rate is only extrapolable if the
population's composition is stable, and it was not**:
`test_depthcensus.py` did not exist when the newer reading was taken, and its
3 nodes cost 472 s. The tier grew 47% in nodes and 185% in seconds. *A rate
measured over a population is a prediction about that population; the moment
the population gains a member of a different kind, the rate is a base rate
and nothing more.*

**P4's count was right for two wrong reasons that cancelled** — 2 prose grep
hits subtracted, 1 parametrize expansion added. It also predicted in writing
that no `whence_slow` test is parametrized, which is false. A count that
lands on the right number through offsetting errors is the failure
`skills/matcher-defines-the-population` describes, and it is only visible
because three matchers were run instead of one.

**P6 missed at 66.7% against a ≥70% band**, which is close enough to be
uninteresting; the interesting part is that its *basis* was wrong. It reasoned
from mark counts and the mark-count leaders are in the cheap half.

**P7 missed by pricing process startup as if it were expensive.** It is
0.29 s. The lesson is narrow and worth keeping: measure the fixed cost of the
granularity you are considering before deciding you cannot afford it.

## 8. Tests

```
harness/tests/test_whenceslow.py                    60 passed in 0.62 s
harness/tests/test_run_driver_whenceslow_slice.py   12 passed in 2.46 s
```

One per rule and one per finding: the `tests/` exclusion, the `.lang` rule,
the prose-vs-AST discovery gap, the transitive closure and both directions of
the split (an unrelated test edit leaves a unit fresh; an *imported* test edit
stales it), all five fail-closed states including `returncode 5 is not a
pass`, the absence of an inheritance rule, the planner's ordering and its
no-silent-truncation exception, the replay's monotonicity in the budget, the
round-grouping, and the driver's six wiring properties.

Two of these tests were written wrong and the suite caught them before the
code did: `test_the_unit_command_runs_only_the_marked_tests` indexed the
first `-m` in `python -m pytest … -m whence_slow` and asserted the marker was
`"pytest"`, and a replay budget assertion had the arithmetic of the greedy
loop backwards. Both are noted here because "the tests passed" is a claim
about the tests too.

### 8.1 The round's own regression, which is this round's theme in miniature

The full harness fast tier came back **1 failed, 1445 passed, 361 deselected
in 285.31 s**, and the red was caused by this round:

```
FAILED harness/tests/test_run_driver_slowtier_commit.py::
       test_the_commit_is_scoped_and_never_stages_the_tree
AssertionError: 'git add' in the ledger-commit block
```

That test asserts round 457's ledger-commit block contains no `git add`, no
`commit -a` and no `-A`. It found the block by slicing `run_driver.sh` from
`SLOWTIER_LEDGER_REL=` to **`# Safety valve (round 150+)`** — a landmark far
downstream, with unrelated statements in between. This round inserted the
whence-slow check there, so the region silently grew to include a block the
test was never about, and the forbidden-substring scan then fired on **a
comment**: the new block's own prose says *"one pathspec, no `git add`, the
workspace must BE a repository root"*, which is a statement of the rule, not
a breach of it.

Two defects, both repaired rather than worked around:

* **An anchor that matched without locating.** The region now ends at the
  next check's own first line when one exists, so it is this block or
  nothing. Pinned from both sides:
  `test_this_block_does_not_widen_the_slow_tiers_own_region` asserts the
  slow-tier region contains `SLOWTIER_LEDGER_REL` and does NOT contain
  `WHENCESLOW`.
* **A scan for dangerous CODE that read COMMENTS.** `_ledger_commit_block`
  strips comment lines before the scan. A check that punishes documenting
  its own rule teaches the next author to stop documenting it.

Nothing about the driver's behaviour changed; both fixes are in the test.
The red was worth having: it is the same shape as everything else this round
measured — an instrument whose region of authority was defined by something
outside itself. Cross-reference `skills/matching-is-not-locating`.

Re-run after the fix: ****1 failed, 1446 passed, 361 deselected in 1216.79 s**
(`logs/round-469-harness-fast2.log`). The target node passes — the count
goes 1445 -> 1446 and
`test_run_driver_slowtier_commit.py::test_the_commit_is_scoped_and_never_stages_the_tree`
is not in the failure list. The one red is a DIFFERENT node,
`test_swe_mutation.py::test_the_grandchild_pid_survives_a_grandchild_slower_than_the_cap`,
which round 461 §8 declared `environmental` in `redattrib` on exactly this
evidence shape, and the re-run's wall clock says why: 1216.79 s against the
first run's 285.31 s, a 4.3x slowdown, because the whence-slow slice was
executing its 1449 s of units on a one-CPU box at the same time. That node is
a grandchild-survives-the-cap timing assertion; a 4.3x-contended box is the
condition it is declared environmental for. Run solo at round 470's HEAD it
is **1 passed in 2.11 s**.

This is round 469's own §9 bullet about contention, arriving as a red rather
than as a percentage: the slice that was measured was also the load. Neither
number is clean-room.**

## 9. What this round did NOT do

* **Did not measure the tier in a single process.** Every number above is the
  sum of 27 unit runs. §4 bounds the difference at ~7 s from the measured
  per-process cost, but that is a bound, not a reading, and P3 is scored
  against the bound.
* **Did not build the measured read-scope refinement.** §3 prices its ceiling
  at ~33% of commits and the mechanism already exists
  (`harness/swe/readscope.py`, root-injectable). It is a real next step with
  a real number attached, which is more than it had this morning.
* **Did not move the census.** §5 states the decision and its reason; the
  census is language(C)'s.
* **The per-unit `seconds` are upper bounds.** The slice ran while this round
  issued its own light tooling (git log, greps, file writes) on a one-CPU
  box, so some units absorbed a few percent of contention. `plan()` reads
  `seconds` as a cost estimate and an over-estimate is the safe direction —
  it makes the planner pick fewer units per budget, never more than fit — but
  the numbers are not clean-room and should be re-taken by an idle slice
  before anyone quotes them as the tier's cost.
* **`harness/wiring-registry.json` gained 10 lines of reordering** that are
  not this round's work: two pre-existing entries (`swe/killerrepin.py`,
  `wiring_audit.py`) sat out of sorted position and the edit normalised them.
  Named here so the diff is not mistaken for a semantic change.
