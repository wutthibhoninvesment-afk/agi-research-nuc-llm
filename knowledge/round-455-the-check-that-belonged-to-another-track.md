# Round 455 (SWE-loop D) — the check that belonged to another track

**Subject.** `harness/wiring_audit.py check` was `rc=1` at HEAD with two W001
errors, and `test_wiring_audit.py::TestThisTree` had been red in the driver's
`health-check` for rounds 453 and 454. The two violations were shipped by
round **452** (language C, `languages/whence/depthcensus.py`) and round
**454** (NUC-integration E, `nuc/reachability_recover.py`). Neither round runs
`harness/tests/`.

**Result.** `skills/unrun-checker-latency/SKILL.md` says a post-round runner
has "a floor of one" and, from round 453's measurement of ONE check, states
the mechanism as *"Nobody who owns a checker breaks it."* Measured here over
**all four** checks and all **554** retained per-round logs, that mechanism
is **false as stated**: the owner-opens-its-own rate ranges from **0/16** to
**8/8** across the four checks, so ownership predicts nothing on its own.
What predicts it is the node's **subject scope**:

| subject scope | invisible to opener | visible | invisible rate |
|---|---|---|---|
| whole-tree | **12** | 4 | **75%** |
| own-suite | 1 | 8 | **11%** |

Fisher exact, two-sided, n=25: **p = 0.0036**. And the four "visible"
whole-tree episodes are **all round 415** — the round that *wrote*
`wiring_audit.py`. Every whole-tree red since has been opened by a round that
could not see it.

The overall **invisible-open rate is 15/28 = 54%** (13/26 = 50% excluding two
episodes nobody opened at all). That half is not a scheduling problem. Moving
the runner earlier does not touch it, because the round that breaks the rule
is not running that suite at any point in its life.

Instrument: `harness/redattrib.py`, registry `harness/crosstrack-registry.json`,
19 tests in `harness/tests/test_redattrib.py`.

---

## 1. The fix, and why neither author could have made it

Both orphans are real, documented artefacts with a sibling test file that
imports them, so both are already IN the invocation closure and the correct
status is `wired`. The `via`/`via_kind` values were computed by
`wiring_audit.py bootstrap`, not written by hand.

```
before: wiring-audit: 119 entry point(s), 99 in closure, 2 error(s), 0 warning(s)  rc=1
after : wiring-audit: 119 entry point(s), 99 in closure, 0 error(s), 0 warning(s)  rc=0
        pytest -q harness/tests/test_wiring_audit.py -> 62 passed in 69.43s
```

`wiring_audit.py check` costs **12.3–14.4 s** (3 runs). It is not expensive.
Round 452 and round 454 did not skip it because it was slow; they never had
a reason to think it concerned them. Round 452 was editing a language, round
454 was editing NUC tooling, and the rule they broke lives in the harness
suite.

## 2. Ground truth is the per-round log, not `driver.log`

`driver.log` names at most two failing tests per line and appends `(+N more)`.
A table built from it is truncated — and in one place simply wrong: its
round-362 line names `test_self_eval.py::test_shape_needs_three_adjacent_
tokens_on_both_sides`, while `logs/health_round_362.log` records the actual
failure as `test_run_driver_whence_health_check.py::
test_whence_health_check_fail_logged_when_script_fails`. All **554**
per-round logs are retained (212 health, 206 whence, 91 skills, 45 nuc) and
carry every `FAILED <nodeid>` line.

Over all of them: **20 distinct test nodes have ever gone red**, in 31
episodes. Twenty is small enough to classify by hand with a real reason each,
which is what `harness/crosstrack-registry.json` is — fail-closed, so the
next node to go red classifies itself or raises **R001**.

`redattrib.py`'s parse is cross-checked against the driver's own independent
verdict, exactly, for all three pytest-grammar checks
(`test_the_parser_agrees_with_the_drivers_own_verdict_count`):

| check | red runs parsed | driver FAIL + ERROR | reconciled by |
|---|---|---|---|
| health-check | 18 | 18 + 0 | — |
| whence-health-check | 7 | 8 + 2 | 3 could-not-run rounds |
| nuc-health-check | 32 | 32 + 0 | — |

## 3. Three things the first draft of the measurement got wrong

Each is the same class of error the analysis exists to find, committed by the
tool doing the finding. All three are fixed in the committed instrument.

**(a) A third verdict I did not know existed.** The driver emits
`PASS|FAIL|ERROR`; my first parser matched `PASS|FAIL` and dropped the 5
`skills-check ERROR` runs *entirely*, which silently merges two episodes
separated by an ERROR into one. Honest postscript: on this data the fix
changed nothing — still 16 episodes — so the defect was real and **latent**.
It would not have stayed latent.

**(b) A pytest-shaped heuristic pointed at a non-pytest grammar.** My
`could_not_run` detector (no pytest count line ⇒ the suite never ran)
reported **68 of the 91** `skills-check` logs as unrunnable. Every one had
run: that check's log is a checker/verdict *table* whose count line reads
`unit_tests  ok  939 passed in 367.50s`, indented rather than at line start.
The detector is now restricted to `PYTEST_LOGS`, and `skills-check` is
reported as an explicit **GRAMMAR GAP** — "driver.log records 23 FAIL runs,
this parser recovered 0 test nodes, so it is NOT represented in any number
below". A silent zero is indistinguishable from a healthy one, which is this
round's entire subject.

On the three checks it may legitimately read, the detector is exact:
rounds **348, 393, 394** of the whence suite, and the driver independently
calls those FAIL, ERROR, ERROR. Round 348 is
`pyproject.toml: Cannot declare ('project','optional-dependencies') twice`
— pytest exit 4, zero `FAILED` lines — i.e. the incident
`knowledge/round-349-a-suite-that-cannot-run-is-not-a-suite-that-passes.md`
is named after, rediscovered by a parser that would have scored it green.

**(c) Static detection of "whole-tree assertion" does not work here — measured
in both directions.** A loose AST/regex detector (test resolves a repo root,
takes no `tmp_path`) returned **2053 candidates in 95 files**, ~50× too many.
Tightening it to a body-local repo-root walk-up returned **59 in 21 files** —
and that set contains **neither `test_wiring_audit.py` nor
`test_verb_audit.py`**, the two files responsible for 15 of the 18 harness
reds, because they reach the tree through an imported `tracked_files()`
rather than a local walk-up. Over-matching by 50× and missing the two cases
that matter is not a heuristic worth tuning. **The retained logs are a better
oracle than the source**: a node is a demonstrated whole-tree assertion if it
has actually gone red for someone else's change.

## 4. The table, and the one row that decides it

```
red-attribution: 554 per-round log(s), 20 node(s) ever red, 31 episode(s)
check                  runs   red  nodes   eps unopnd own-opened   invisible
----------------------------------------------------------------------------
health-check            212    18      9    20      0    5/20      15/20
whence-health-check     206     7      8     8      0    8/8        0/8
nuc-health-check         45    32      3     3      3    0/0        0/0
skills-check             91     0      0     0      0    0/0        0/0   <- grammar gap
```

`whence-health-check` is the row that kills the ownership mechanism: **8 of 8**
episodes opened by `language(C)`, its own owner, and **0** invisible. Its
subject is confined to `languages/whence/`, which only language(C) edits. The
harness check's subject is the whole repo, and it inverts: 5 of 20.

Two classifications exist to stop the table lying:

* **`environmental` (2 episodes).** `test_swe_mutation.py::
  test_timeout_kills_grandchild_holding_stdout` went FAIL(442) PASS(443–446)
  FAIL(447) PASS(449+) on byte-identical code — `harness/swe/mutation.py`
  last changed at round 437 (`ce7a89d`). It is a timing assertion on a 1-CPU
  box. Rounds 442 (E) and 447 (B) are recorded by any naive tool as opening
  episodes they did not cause.
* **born-red (3 episodes, `unopnd`).** Round 409 (harness A) wired
  `nuc/run_checks_fast.sh` into `run_driver.sh`; its **first ever run**, at
  round 410, was red, and stayed red **32 rounds** until round 442 — the
  owning track — fixed it. Nobody opened it. Attributing it to round 410's
  language(C) work would report a C round as having broken the NUC suite.
  A check installed red is *ungoverned becoming governed*, not a regression.

## 5. The recipe this produces, and its honest price

The floor of one is not lowered by adding a checker or by moving the runner.
For a **whole-tree** assertion the fix is that the author of ANY track runs
it, and the only reason they don't is that they have never been told it is
theirs. At HEAD there are **five** whole-tree nodes, in three files:

```
python3 harness/wiring_audit.py check                      # 12-14 s -> 3 nodes
pytest -q harness/tests/test_verb_audit.py::TestThisTree \
         harness/tests/test_roundheadings.py \
         harness/tests/test_redattrib.py                   # 36.4 s -> 2 nodes
python3 harness/redattrib.py audit                         # R001 fail-closed
```

**Measured end to end on this 1-CPU box: 48 s**, run against this round's own
diff after `state/research-state.md` had been edited —
`70 passed in 36.36s`, `0 error(s)` twice. The costs are not additive: the
three pytest files share one interpreter start and one collection, and
`test_verb_audit.py::TestThisTree` alone is 35.4 s of the 36.4 s. Forty-eight
seconds is a price any track will pay, which is the whole argument.

**`wiring_audit` is blind to untracked files.** Run before `git add`, it
returned `0 error(s)` on a tree containing two brand-new, undeclared entry
points; staging them turned the same command red with two W001s. A
pre-commit check that cannot see what you are about to commit is the same
defect one step in. **Stage first, then check.**

## 6. Predictions, scored

Banked in `state/swe/round-455/PREDICTIONS.md` before any of section 3-5 was
measured. **7 hits, 3 misses, 1 unresolvable-as-posed.**

| # | claim | outcome |
|---|---|---|
| P1 | two registry entries clear all 3 reds, nothing else red | **HIT** — 62 passed |
| P2 | both entries are `wired`, not `manual` | **HIT** — both, via sibling-test import |
| P3 | ~12 live-tree assertion classes, [6,25] | **MISS (method)** — static detection gave 2053 loose / 59 strict, and the strict set omits the two files that matter. The question is not statically answerable here |
| P4 | ~5 of them cross-track, [2,10] | **HIT** — 5 whole-tree nodes at HEAD, reached by a different route |
| P5a | health-check red rate 20%, [10%,35%] | **MISS** — 8.5%, below the interval |
| P5b | 12 episodes, [6,25] | **HIT** — 7 per-check, 20 per-node; both inside |
| P5c | mean episode 2.0 rounds, [1.2,3.5] | **HIT** — 2.57 |
| P5d | 0.70 of episodes opened by a non-owner, [0.4,0.95] | **HIT** — 5/7 = 0.714 |
| P6 | all 3 other suites have a cross-track live-tree assertion | **MISS** — whence has one `shared-file-own-content` node, nuc has none, skills unmeasurable (grammar gap). The weaker "at least one" clause held |
| P7 | the cross-track subset costs < 60 s | **HIT** — **48 s** measured end to end (§5). I nearly scored this a miss by ADDING the per-file timings; the three pytest files share one collection |
| P8 | `test_swe_campaign.py::test_review_stage_and_report` still red | **MISS** — `1 passed in 53.62s` |
| P9 | the state file's "recall is still 0%" is stale | **HIT** — 9% (3 conclusive of 33) against checkout `6a525eab44f60c1c` |

The two most useful are the misses. **P5a** is wrong in the direction that
matters: the harness check is red *rarely* (8.5%), and I predicted a busier
check because I had just been staring at two consecutive red rounds. Rarity
is exactly why nobody has fixed the visibility problem — 8.5% is a rate at
which convention appears to work. **P3** failed because I assumed a property
of the tree was detectable from the tree; it was detectable only from its
history.

## 7. Three carried items re-derived — and the record already disagreed with itself

**First, my own error, because it shaped this section.** I opened the round
with `tail -150 state/research-state.md` and worked from the
`## Next steps (as of round 435)` block it returned. That block is not
current: in this file's recent region the next-steps blocks are ordered
**newest-first** (455, 454, 453, 451, 450, ... 437, 436, 435, 434), so `tail`
returns the OLDEST guidance in the file. The current block is round 454's, 1400
lines earlier. Same shape as the standing `tail -N can hide the measurement`
note, one file over.

That matters because the record already contradicted itself, and reading it
end-first is what exposed it. **Round 437's block — newer than 433/434/435's —
already records "V002 is fixed" and "`test_review_stage_and_report` is green
and explained."** Rounds 433, 434 and 435 carry both as red, and round 454's
current item 7 re-points at "rounds 434/433's carried items" without noting
that a newer block closed two of them. Three claims were checkable this round
and **none survived**:

| carried claim | HEAD |
|---|---|
| `test_verb_audit.py::TestThisTree::test_no_unexplained_broken_invocation` "red since round 429" | **GREEN** — `7 passed in 35.38s`. It was red rounds 429-436 and has been green for 18 rounds |
| `test_swe_campaign.py::test_review_stage_and_report` red, `no_killer` 0 | **GREEN** — `1 passed in 53.62s` |
| slow-tier instrument "recall is still 0%" | **9%** — 3 conclusive of 33 |

The fourth, `test_swe_campaign.py[light]` never having been run through the
slow-tier instrument, IS still true: `slowtier.py status` reports it
`unknown`.

So the honest finding is not "the carried items were stale" — for two of
three, a newer block had already said so and nothing propagated it back.
**A next-steps list that is appended to rather than reconciled will carry a
closed item forever**, and the round that closes one has no way to reach the
older blocks that still assert it. That is the same defect as this round's
subject in a different medium: the correction exists, and the reader who
needs it is not the reader who sees it.

## 8. What is still open

* **`skills-check` has no per-node ground truth.** Its logs are a
  checker/verdict table, so round 453's 16 episodes cannot be reproduced or
  refuted inside this instrument. Teaching `redattrib.py` that grammar would
  make the four checks comparable; until then the headline rate is over three
  checks, not four, and the GRAMMAR GAP line says so on every run.
* **The one off-diagonal own-suite row is debatable.** Round 362 (language C)
  opened `harness/tests/test_run_driver_whence_health_check.py`, classified
  `own-suite` because it lives in and tests the harness. Its subject is
  run_driver.sh's handling of the *whence* check, so a case can be made for
  `shared-file-own-content`. Reclassifying it moves own-suite from 1/9 to
  0/9 invisible and strengthens the association; it is left as the weaker
  reading on purpose.
* **Nothing yet makes a round of another track run the five whole-tree
  nodes.** This round wrote the recipe and measured its price; it did not
  install it. Doing so is a CLAUDE.md ground-rule change and belongs to
  harness(A) or the operator, not to a knowledge file.
