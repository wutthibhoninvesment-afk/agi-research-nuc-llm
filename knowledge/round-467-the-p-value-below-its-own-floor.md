# Round 467 (SWE-loop D) — the p-value below its own floor

**Track:** D (autonomous SWE — the harness used on this repo's own code).
**Date:** 2026-09-03. **Model:** claude-opus-5.
**Predictions banked before measuring:** `state/swe/round-467/PREDICTIONS.md`
(12 HIT, 2 PARTIAL, 3 MISS of 17, plus one declared no-basis resolved).

Two things, and the second is why the first was worth doing.

**The harness fast tier had been red for four rounds** — 8 failing nodes at
rounds 465 and 466, three whole-tree checks, none of them broken by a round
that runs `harness/tests`. Both causes are single files shipped by other
tracks: `languages/whence/specreg.py` (round 464, language C) carrying an
unguarded import-time `os.path.abspath(os.path.join(HERE, "..", ".."))`, and
`harness/tests/test_corpus_evidence.py` (round 463, harness A) never declared
in the wiring registry. **`1372 passed, 361 deselected in 295.09s`, rc 0.**

**And the headline that measurement produces is smaller than it was
published.** Round 461's next-step 6 said `p = 9.81e-08` was "narrower than
the data earns" and asked for a round-clustered version. It is worse than
narrow. The p-value has no producer in the tree, two clusterings under it,
and — the part nobody had noticed — **a null whose own floor is 1/6**,
because a round's track is not a free variable: `run_driver.sh` assigns it by
round number mod 6. Every correction moves the number the same way:

| reading | p | what it stops assuming |
|---|---|---|
| naive Fisher over episodes (published) | **6.05e-07** | — |
| one row per NODE | 1.19e-04 | that `unit_tests`' 27 reds are 27 observations |
| scope labels shuffled across nodes | 5e-05 | that scope and node are independent |
| **rigid rotation of the driver's own rota** | **0.167** | that who was on duty is a free variable |
| the wide row ALONE, no analytic second row | **0.333** | that `own-suite` carries information |

The RATE survives all of it — 89% of whole-tree reds are opened by a round
that cannot see them, and moving the runner earlier still does not touch that
share. What does not survive is the claim that the association was
*discovered*: a period-6 rota produces ~78% invisibility mechanically, and
the measured 89% is 11 points above it, at p = 0.333.

---

## 1. The live reds, and why neither author could have closed them

```
logs/health_round_465.log, logs/health_round_466.log:  8 failed, 1335 passed
  test_redattrib.py::TestThisTree::test_the_cli_audit_exits_zero_on_this_tree
  test_redattrib.py::TestThisTree::test_the_registry_is_fail_closed_over_the_live_logs
  test_swe_copyparity_real_subject.py::test_the_real_whence_tree_has_no_unguarded_escape
  test_swe_copyparity_real_subject.py::test_the_escapes_cli_runs_on_the_real_subject...
  test_swe_copyparity_real_subject.py::test_json_output_carries_every_finding_field
  test_wiring_audit.py::TestThisTree::test_the_registry_is_clean
  test_wiring_audit.py::TestThisTree::test_every_entry_point_in_the_tree_is_declared
  test_wiring_audit.py::TestThisTree::test_the_cli_check_exits_zero_on_this_tree
```

Eight nodes, two causes, three cascades.

**(a) `languages/whence/specreg.py:132`.** Round 464 (language C) shipped the
SPEC.md decision registry with `REPO = os.path.abspath(os.path.join(HERE,
"..", ".."))` at import time. Under a mutation or repair copy that file lives
at `/tmp/<sandbox>/specreg.py`, so `HERE/../..` resolves to `/tmp` — outside
the copy AND outside the checkout, silently, because `os.path.dirname` never
raises. Seven other expressions in that same tree already reach the root
through `AGI_RESEARCH_ROOT`, which `harness/swe/proc.py` exports into every
sandbox. This one did not. The fix is the eighth:

```python
REPO = (os.environ.get("AGI_RESEARCH_ROOT")
        or os.path.abspath(os.path.join(HERE, "..", "..")))
```

```
before: 93 file(s) scanned, 1 escaping expression(s) (1 import-time), 7 env-guarded  rc=1
after : 93 file(s) scanned, 0 escaping expression(s), 8 env-guarded                  rc=0
```

**(b) `harness/tests/test_corpus_evidence.py` and `specreg.py`, undeclared.**
`harness/wiring-registry.json` is fail-closed: an entry point with no row is
W001. Round 463 shipped one file and round 464 the other; neither round runs
`harness/tests/`, and W001 stood for four rounds across three whole-tree
nodes. Both rows' `via`/`via_kind` come from `wiring_audit.py bootstrap`, not
from hand:

```
before: 123 entry point(s), 103 in closure, 2 error(s), 0 warning(s)   rc=1
after : 123 entry point(s), 103 in closure, 0 error(s), 0 warning(s)   rc=0
```

**(c) The registry that measures all this went red for lacking three rows
about (a).** `redattrib.py audit` was rc 1 with three R001s — the copyparity
trio had gone red at 464 and was undeclared. Which is the module's own
fail-closed design working, one round late, by construction.

*Neither original author skipped a check.* Round 464 was editing a language
and round 463 was editing a harness test; the rule they broke is asserted in
a suite neither runs. That is the phenomenon `redattrib.py` exists to
measure, and this round is a new data point in it — including the part where
the closing round is SWE-loop(D), the only other track that runs
`harness/tests`.

## 2. A sixth subject scope, forced by the subject

The copyparity trio could not be classified with the five values the registry
had, and the prediction file says so as a MISS: I predicted `whole-tree` from
the file's LOCATION, and the registry's own rule is to decide from what the
node READS.

`scan_escapes(WHENCE_ROOT)` reads the 93 `*.py` files under
`languages/whence` and nothing else. A change in `nuc/` cannot turn it red —
so not `whole-tree`. It lives in `harness/tests/` — so not `own-suite`. Its
subject is not a corpus every track writes — so not `shared-corpus`.

```
foreign-subject: the node's SUBJECT is one other tree, and the node LIVES in a
different track's suite. The visibility consequence is the worst of the six:
the track that can break it is BY CONSTRUCTION not the track that runs it.
```

It exists because round 425's whole point was that copyparity had never been
run against the tree it protects. Pointing it at `languages/whence` is what
put a language(C) subject under a harness(A) runner — the scope is a
consequence of a decision the program made on purpose.

**A second, older instance of the same sweep failure.**
`test_roundheadings.py::test_the_live_record_is_fully_canonical` was
`whole-tree`; its subject is `state/research-state.md`, which every track
appends to every round — the exact example `shared-corpus`'s own definition
gives, and the same file as `corpus_check.py::state_claim_check`, which IS
`shared-corpus`. Round 461 added the value and did not sweep the existing
entries for the shape it had just named. Reclassified. The headline does not
move (both scopes are 100% invisible here); the 2x2 does, and that is
published rather than absorbed.

## 3. Round 461's item 2 — the one-round lag, and a number it exposed

A fail-closed registry cannot fire in the round that breaks it: the evidence
is `logs/<check>_round_<N>.log`, and round N's copy is being written by the
run the assertion is part of. So R001 always names a node opened by an
earlier round while running inside a later one, and the message said neither.

```
R001  <node>: went red and has no registry entry -- FIRST RED in round 464's log
      (language(C)), and the earliest run that could have seen it is round 465,
      so the round reading this failure is not the round that caused it
```

`opened_by_log_round` and `first_firable_round` are now on every episode row.
And measuring the lag rather than asserting it produced a number nobody had:

**the lag is exactly 1 for all 94 episodes in the record — never 2, never
more.** "At least one round" is, in this program, "exactly one round",
because all four checks run every round. The floor and the actual latency are
the same thing here.

## 4. Was the label read off the data? Mostly not — and the cheap test says otherwise

The invisible-open rate and its p-value are computed over `subject_scope`, so
a scope read off the episode outcomes it later explains is circular. Round
467 made that checkable instead of arguable: every registry entry now
declares `evidence`, `subject` or `outcome`, with two fail-closed rules.

* **R005** — an entry with no evidence kind, or an unknown one.
* **R006** — an `outcome` label that is not `environmental`, or an
  `environmental` label claiming `subject` evidence. Both directions, because
  nothing about a subject can tell you a test is a clock flake, and a scope
  read off a verdict history is not admissible evidence about that history
  unless the scope IS about verdicts.

**Adjudicated: 3 of 34 entries are outcome-derived, and they are exactly the
three `environmental` ones** — whose 4 episodes `attribute` already excluded
from its `excl_environmental` headline before this round existed. So the
circularity worry is largely REFUTED, which was not the prediction (P13
predicted >= 12 of 31 and is a MISS).

**The way it would have been "confirmed" is the finding.** The mechanical
proxy — does `why` cite a round number, a track name, or "opened by" —
flags **31 of 34**:

| test | flags | verdict |
|---|---|---|
| `why` mentions a round / track / opener | 31 of 34 (91%) | would have CONFIRMED the prediction |
| scope survives deleting every such clause | 3 of 34 (9%) | REFUTES it |

Twenty-eight entries apart, and the cheap one points the flattering way. Most
of those 31 cite openers as *corroboration* after stating an argv or an
`os.walk` root. Round 462's `skills/residual-audited-both-ways` in one line:
classify item by item before narrowing.

## 5. The p-value, and the null that was not a symmetry

`p = 9.81e-08` is published in `knowledge/round-461-*.md` and in
`skills/unrun-checker-latency/SKILL.md`. **Nothing in the tree computed it.**
So the first thing `redattrib.py scope-test` does is reproduce both
previously published figures from their own tables, and
`test_the_published_p_values_are_reproduced` holds that open:

```
round 455  [12, 4, 1, 8]   published 0.0036     recomputed 0.00361     agree
round 461  [53, 4, 0, 8]   published 9.81e-08   recomputed 9.81e-08    agree
```

### 5.1 The bug the prediction caught

The rotation-shift null rigidly rotates the driver's round -> track map,
preserving the rounds, their order, each round's set of opened episodes, each
node's scope and the exact multiset of track labels, and destroying only
which round got which label. Round 466 (NUC E) had just written
`skills/null-must-preserve-the-shape` on exactly this reasoning.

The first implementation rotated the observed label SEQUENCE by position:
`labels[(i + k) % n]`. It reported **188 distinct relabelings of 314 shifts,
p = 0.0796**. The banked prediction said 6 and 0.167. 188 is not a number any
period-6 rule can produce, and that is what sent me looking.

`logs/driver.log` has no `start` line for rounds **229 and 313**. The
observed sequence is 314 long over a 316-round span, so rotating it by
position slides the labels across the two holes, changes phase halfway
through, and manufactures relabelings in which the rotation is no longer
period-6 at all. **A shift over POSITIONS is not a shift over the RULE.** The
symmetry of `track = f(round mod 6)` is shifting the residue, which is
invariant to holes. Pinned by
`test_a_gap_in_the_driver_log_does_not_change_the_null_size`, which builds
the same record with and without holes, requires the same orbit size, and
asserts that the positional rotation it replaced does NOT have that property.

The rotation itself was checked against the record rather than against
CLAUDE.md: **0 deviations in 314 rounds**, every residue one track.
`test_the_rotation_in_the_record_is_still_rigid` keeps that true, because the
null stops being a symmetry the day the driver stops obeying its own rule.

### 5.2 The floor

```
  3. rotation-shift null      p = 0.167   1 of 6 shift(s) >= observed
     the driver picks a track by round mod 6, so the null has 6 member(s),
     one of them the identity: it CANNOT return below 0.167, and no amount
     of further rounds will change that.
     observed 0.889, null mean 0.257, max 0.889
     null values by shift: [0.8889, -0.3016, -0.1131, 0.6071, 0.3671, 0.0933]
```

The observed table is the most extreme of the six, so 0.167 is the strongest
thing this null can say. **A p six orders of magnitude below your own null's
floor is not a strong result; it is a result from a null that does not
describe you.** No amount of extra rounds moves a floor of 1/k.

### 5.3 The analytic row

`_subject_scope`'s text for `own-suite` reads: *"the hosting track is the only
track that can open it, AND CAN SEE IT by running its own fast tier."* The
conclusion is inside the definition. Half the 2x2 could not have come out any
other way, which is why `own-suite` is 0 invisible / 8 visible and always was.

The comparison with no analytic row is the wide scope against the rota's own
base rate. Under the rotation a node in `harness/tests` is visible to 2 of the
6 slots and one in `skills/` to 1 of 6:

```
scope           episodes   observed   rotation
whole-tree            63        11%        27%   visible
own-suite              8       100%        40%   visible
```

and the same shift null over that one row alone:

```
  5. whole-tree ALONE:  p = 0.333   observed 89% invisible, null mean 78%,
     values by shift [0.8889, 0.6984, 0.7619, 0.8571, 0.4921, 0.9683]
```

**One shift beats the observation (96.8%).** The invisible-open rate is a
real and consequential fact; the *association with scope* is, once the
analytic row is removed and the rota is respected, indistinguishable from
what the rota produces on its own.

### 5.4 The two clusterings, for completeness

* **node** — `unit_tests` alone contributes 27 red rounds. Collapsed to one
  row per node, `[[10,1],[0,8]]`, n = 28, **p = 1.19e-04**.
* **round** — 11 rounds open episodes on two or three checkers at once. The
  node-scope permutation null shuffles scope labels across the 28 nodes,
  preserving every node's episode count and every round's co-occurrences
  exactly: **p = 5e-05**, 0 of 20 000 draws >= observed, seed 467. Declared
  no-basis in the predictions file and reported rather than predicted.

## 6. A pristine checkout cannot reproduce any of this, and now it says so

Round 461's item 7, closed on the instrument's side. `logs/*_round_*.log` is
gitignored (`.gitignore` 28, 29, 35, 60): `git ls-files logs/` is **9**
against the **602** this module reads. A `git worktree add HEAD --detach`
gave round 461 `4 failed, 15 passed` where the truth was `2 failed, 17
passed` — two of the four caused purely by the absence.

`evidence_base()` counts what the checkout can see; below `MIN_EVIDENCE_LOGS`
(50, far above a fresh clone's 0 and far below the live tree's 602)
`attribute` prints a NO EVIDENCE BASE banner and `TestThisTree` skips **with
that reason** instead of failing. A red meaning "you have no data" must not
look like a red meaning "the tree is broken".

**Measured, not asserted.** After committing, `git worktree add /tmp/wt467
HEAD --detach` (9 tracked files under `logs/`, 0 per-round health logs):

```
42 passed, 18 skipped in 0.15s
SKIPPED harness/tests/test_redattrib.py:593: this checkout holds 0 per-round
  log(s), below the floor of 50 -- `logs/*_round_*.log` is gitignored
  (.gitignore 28, 29, 35, 60), so these whole-tree assertions have no evidence
  to read. Not a failure of the tree.
```

against round 461's `4 failed, 15 passed` on the same kind of checkout. Every
skip prints the reason. The worktree was removed on the way out
(`git worktree remove --force`); five stale worktrees from rounds 410, 426,
427 and an old `pristine-check` run are still registered in `/tmp` and are not
this round's to delete.

Whether the logs belong in git is still the operator's question. Reporting a
confident wrong answer while it is open is not.

## 7. Tests

```
harness/tests/test_redattrib.py            60 passed in 2.02s   (29 at HEAD)
bash harness/run_tests_fast.sh             1372 passed, 361 deselected in 295.09s, rc 0
                                           (rounds 465/466: 8 failed, 1335 passed)
languages/whence/run_tests_fast.sh         2431 passed, 3 skipped, 103 deselected in 238.15s
bash nuc/run_checks_fast.sh                946 passed in 170.29s, rc 0
pytest skills/skill-authoring/scripts \
       skills/session-inheritance-audit/scripts  986 passed, 4 subtests in 108.90s, rc 0
corpus_check.py --precommit                9 checker(s), 0 error(s), 8 warning(s), rc 0, 29.1s
                                           (33.4s on the run before the bank was registered,
                                            which was 1 error: carryforward K001)
pristine worktree at HEAD                  42 passed, 18 skipped, 0 failed
harness/redattrib.py audit                 34 ever red, 34 declared, 0 errors, rc 0
harness/wiring_audit.py check              123 entry points, 103 in closure, 0 errors, rc 0
harness/swe/copyparity.py escapes          copy_safe, 0 escaping, 8 env-guarded, rc 0
languages/whence tests/test_specreg.py     39 passed in 4.30s
skill_lint --house --strict (both skills)  0 errors
```

31 new tests. The ones that would catch a regression of this round's own
reasoning: `test_the_published_p_values_are_reproduced`,
`test_a_gap_in_the_driver_log_does_not_change_the_null_size`,
`test_the_naive_p_is_the_most_extreme_of_the_five_readings`,
`test_an_outcome_label_outside_environmental_is_R006`,
`test_environmental_declared_subject_derived_is_ALSO_R006`,
`test_the_rotation_in_the_record_is_still_rigid`,
`test_an_empty_checkout_is_reported_as_no_evidence_rather_than_as_green`.

**All four of the driver's per-round check tiers are green**, which is what
`unit_tests` being the reddest node in the repo makes worth stating: the
skills corpus suite is one row of one log and it was run in full here rather
than left to the `--precommit` SUBSET, which deliberately skips it.

`nproc` on this box is 1. Everything above ran serially; nothing was started
while another suite was running.

## 8. Skills

No new skill. Two upgrades, both from measurements this round made, per the
standing "evaluate before authoring" rule:

* **`skills/null-must-preserve-the-shape`** (round 466's, three rounds old)
  gains steps 9-11 and a pitfall: **count your null's members, it has a
  floor**; **a shift over positions is not a shift over the rule** (with 188
  as the fingerprint); **check whether one arm of your comparison is
  analytic**; and **a label read off the outcome cannot then explain the
  outcome**, including the warning that the cheap proxy for that lies in the
  flattering direction. Verification section gains this round's runnable
  commands. `skill_lint --house --strict`: 0 errors, 0 warnings.
* **`skills/unrun-checker-latency`** — the `p = 9.8e-08` line is replaced by
  the five-reading table and the three lessons. `description` untouched in
  both, so no re-probe is owed.

## 9. Honest failures

* **P7, P11 and P13 are one error in three costumes**: a prediction about a
  population, derived by reasoning about the population instead of counting
  it. Round 465's item 3 and round 435's item 7 both already say so. The one
  prediction reasoned from a STRUCTURAL fact — P10, "a period-6 rota has six
  relabelings" — is the one that caught a bug.
* **I built the wrong null first**, three rounds after this program wrote the
  skill that says not to, while citing that skill in the docstring. The
  defect is kept in the code comment rather than tidied away.
* **`foreign-subject` is one observation wide.** Three nodes in one file.
  Round 461 declined to add a sixth scope on one observation (see
  `test_one_unit_has_never_been_evidence...`'s registry entry) and this round
  added one on three. The counter-argument is that the alternative was to
  call a `languages/whence`-only subject `whole-tree`, which is false about
  the blast radius in a way the vocabulary exists to prevent. It should be
  re-examined the next time a node with this shape appears.
* **The whole-tree row is still not clean.** It mixes nodes hosted in
  `skills/` (visible to 1 slot in 6) with nodes hosted in `harness/tests`
  (2 in 6), so its 27% rotation baseline is an average over two different
  structural rates. A per-host-suite version of section 5.3 would be
  sharper and was not built.
* **`case_coverage`'s 49-of-103, `claim_check`'s 0 of 431 commands, and the
  `--cap 196` escalation** are all untouched, as in every recent round.
