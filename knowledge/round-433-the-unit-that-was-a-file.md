# Round 433 (harness A) — the unit that was a file

**Track:** A (harness engineering) · **Date:** 2026-09-01 · **Model:** claude-opus-5

Round 432's next-steps item 3 handed harness(A) a remedy:
`harness/tests/test_swe_campaign.py::test_cli_runs_offline_stages_and_stops`
"needs a slow marker so it stops being run inside a round's turn budget by
accident."

Re-derived first, per round 432's own item 6. **The marker is already there
and does nothing.** What was missing was not a marker. It was a unit of
evidence smaller than a file.

Predictions banked before any measurement: `state/round-433-predictions.md`.

---

## 1. The remedy that was already in place (A1, A2, A3 — all HIT)

`harness/tests/conftest.py` marks `swe_slow` by `basename.startswith("test_swe_")`
minus `harness/tier-budget.json`'s promotions. `test_swe_campaign.py` matches
the prefix and is absent from `promoted` (15 files are promoted; it is not one).
So it is already fully deselected:

```
$ python3 -m pytest -q -m "not swe_slow" harness/tests/test_swe_campaign.py --collect-only
no tests collected (20 deselected) in 0.09s
```

Adding a marker changes nothing. **A1 HIT.**

What the deselection buys is measured by what it costs. Over the whole
`state/slow-tier-ledger.jsonl` — 26 entries, 14 distinct files:

```
campaign entries: 0
timeout entries:  0
```

**A2 HIT.** The file has never had a single ledger entry, so its 20 tests
have never been evidence about any checkout. And no run has ever timed out,
because the planner is careful:

```
$ plan(status, budget_s=900)   -> 11 files, campaign not among them
$ plan(status, budget_s=3600)  -> 20 files, campaign still not among them
```

**A3 HIT**, and stronger than predicted: the file is not reachable even at a
budget larger than a round's entire wall clock. `plan` refuses to start what
it cannot finish, which is correct — and the correct behaviour, repeated 92
rounds, is indistinguishable from never having tried.

## 2. What the file actually costs (A5, A6 HIT; A7 MISS)

One process, `--durations=0`, everything except the one suspect test:

```
$ PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:randomly --durations=0 \
    harness/tests/test_swe_campaign.py \
    --deselect harness/tests/test_swe_campaign.py::test_cli_runs_offline_stages_and_stops
1 failed, 18 passed, 1 deselected in 571.32s (0:09:31)
```

**571.32 s for 19 of 20 tests — A6 HIT** (predicted < 600 s, and only just).
The per-test call times:

| test | s |
|---|---|
| `test_repair_stage_samples_killed_mutants_resumes_and_reports` | 78.19 |
| `test_live_kill_stage_resumes_from_partial_and_pins_verified_kills` | 75.12 |
| `test_review_stage_and_report` | 69.23 |
| `test_coverage_stage_triages_survivors_and_report_shows_the_split` | 66.13 |
| `test_recheck_reruns_timeouts_serially_and_records_flips` | 59.45 |
| `test_downstream_stages_survive_a_concurrent_edit_to_the_mutated_file` | 58.63 |
| `test_corpus_stage_pins_killers_and_verify_confirms_them` | 57.55 |
| `test_mutation_stage_checkpoints_per_mutant_and_resumes` | 30.44 |
| `test_report_carries_the_score_audit_of_its_own_mutation_report` | 30.01 |
| `test_a_red_baseline_refuses_to_run_a_single_mutant` | 15.33 |
| `test_manifest_is_created_and_stage_skipping_is_persistent` | 15.10 |
| `test_allow_red_baseline_runs_but_marks_every_number_not_evidence` | 14.44 |
| the other 7 | < 0.1 each |

And the 20th, alone, in a fresh process:

```
$ python3 -m pytest -q harness/tests/test_swe_campaign.py::test_cli_runs_offline_stages_and_stops
   ... 748 s elapsed, no output, killed
```

**A4 HIT** at its own stated threshold (600 s). Disclosed: the 1500 s cap was
never reached — the round's own wall clock ran out first and the process was
killed at 748 s, so this round measured a LOWER bound and no upper one. Round
432 independently verified the cost is pre-existing at HEAD in a worktree.

**A5 HIT**: exactly one test in the file exceeds 120 s, and the other 19 are
each under 120 s (max 78.19 s).

**A7 is a clean MISS**, and instructive. I predicted the floor was the
`checkout` fixture — a `_copy_project` of the whole whence tree, once per test,
which I guessed at 2–8 s. Measured:

```
A7 _copy_project seconds: [0.02, 0.01, 0.02]
```

Setup is 0.02 s per test; 568 s of the 571 s is `call` time in twelve tests
doing real mutation/corpus/review work. The cost is not one hot spot and not
fixture overhead — it is broadly distributed genuine work, which is why no
amount of fixture tuning would have made this file fit.

**Why that one test is different, mechanically.** Every other expensive test
in the file either calls `_seed_green_baseline(c)` (which writes the campaign's
`baseline.json` and marks the stage `done`, i.e. takes the RESUME path) or
passes a fake `test_cmd` (`_OK` / `_RED`, a two-line `python -c`).
`test_cli_runs_offline_stages_and_stops` calls `C.main(...)` with the DEFAULT
`test_cmd`, so the campaign runs a full unfiltered whence suite as its baseline
pre-flight and a tracer-instrumented one for coverage. One test, two suites.

## 3. The finding: the tier's unit of evidence was a file

Every mechanism in this tier speaks about files. `conftest.py` marks by
basename. `tier-budget.json` promotes by basename. `slowtier.plan` estimates
per file, `run_slice` records per file, `classify` freshens per file. That
vocabulary cannot express the sentence the measurement just produced:

> Nineteen of these tests cost 571 s and one of them costs more than any
> budget this program grants a round.

So the tier did the only thing it could: it declined the file whole, forever,
and reported `unknown` — truthfully. The blind spot was not a bug in any of
those instruments. It was the absence of a noun.

**And it was hiding a live failure.** In the 571 s run,
`test_review_stage_and_report` FAILED:

```
    rep = c.stage_report()
    assert rep["total"] == 2 and rep["baseline"]["score"] == 0.5
>   assert rep["corpus"]["no_killer"] == 1 and rep["tests_added"] == 0
E   assert (0 == 1)
harness/tests/test_swe_campaign.py:310: AssertionError
```

Nobody could see it. The file is deselected from the fast tier by design and
has never had a slow-tier ledger entry, so for as long as the ledger has
existed this test's verdict has been literally unobserved. This round did not
have the wall clock left to root-cause it and does NOT claim a cause; it is
recorded as a live red with one static lead in §5.

## 4. What was built: a unit is a file plus a selector

`harness/swe/slowtier.py` grows a unit layer, and `harness/tier-units.json` is
its registry.

- A file with no declared heavy tests is **one unit whose id is its filename**.
  With an empty registry every id, every plan, every entry and every printed
  figure is byte-for-byte what it was — which is what makes this change free.
- A file with declared heavy tests becomes **two units**, `<file>[light]` and
  `<file>[heavy]`, each with its own ledger entry, cost estimate and
  freshness verdict.

```
$ python3 harness/swe/slowtier.py units
test_swe_campaign.py[light]   light  test_cli_runs_offline_stages_and_stops
test_swe_campaign.py[heavy]   heavy  test_cli_runs_offline_stages_and_stops
... 30 other files, all `whole`

$ python3 harness/swe/slowtier.py status | head -1
slow tier: 31 files / 32 units, 0 conclusive against checkout e937b353705e9381 (0% recall), 0 failing
```

**The direction is fail-closed, and it is the OPPOSITE direction to
`tier-budget.json`'s.** That registry can only ever move a file toward the
tier a human watches. This one can only ever SPLIT one claim into two smaller
ones: a `[light]` pass asserts strictly less than the file's pass did, and the
`[heavy]` unit it leaves behind starts `unknown` and stays in the recall
denominator. **Declaring a test here cannot make anything look greener than it
was.** (A9 HIT.)

**Rule 11**, the one asymmetry a split introduces — and the reason it needed
writing rather than assuming (A10 HIT):

> A whole-file entry whose outcome is `passed` IS evidence for every unit of
> that file: the run is a strict superset, and "everything passed" entails
> "these passed".
>
> A whole-file entry whose outcome is `failed` is evidence for the whole-file
> unit ONLY. pytest's exit code does not say WHO was red, so attributing it to
> a unit invents a verdict — and attributing a pass to the other unit invents
> the opposite one.

Evidence never flows the other way: `[light]` passing says nothing about
`[heavy]`. An inherited row is flagged `inherited`, and `plan` refuses to use
its `seconds` — a whole file's wall clock is the exact number the split exists
to stop believing.

Every refusal path returns the **single whole-file unit**, because that is the
strongest claim and therefore the safe fallback:

| condition | result |
|---|---|
| declared name is not a top-level `def test_*` in the file | whole + `REGISTRY ERROR ... — running it whole` |
| the file cannot be parsed | whole + `unreadable` error |
| every test in the file is declared heavy | whole + `the light unit would collect nothing` |
| the registry file is missing/malformed/wrong-shaped | nothing splits, no exception |

That last one is round 348's `pyproject.toml` outage guarded in advance:
`status` runs inside every round's fast health check, so a registry that could
abort it would be that outage with this repo's own name on it.

Two smaller decisions worth their lines:

- **`[heavy]` selects by node id, never `-k`.** `-k test_q` also matches
  `test_q_and_more`, which would silently widen the heavy unit and shrink the
  light one by a test nobody deselected. `test_heavy_selects_by_node_id_never_by_a_k_substring`
  pins it, and `test_the_two_units_of_a_split_file_are_complements` pins that
  `[light]`'s deselects are exactly `[heavy]`'s selects.
- **The size prior is prorated.** Bytes are a per-file quantity, so both units
  of a split file carried the same tie-break value and sorted adjacently at the
  tail. `[light]` is now scaled by its share of the file's tests and `[heavy]`
  keeps the full prior, because being expensive is the reason the registry
  named it. Both remain priors; a real measurement still beats them.

Schema bumped 4 -> 5. `file` deliberately stays a FILENAME so `ledgerreplay`,
`latest_by_file` and a human grepping the JSONL are unaffected; `unit` is the
new freshness key, and for an unsplit file the two strings are equal, so **no
ledger migration exists or is needed**.

New CLI verb `units`. `verb_audit.py` picked it up with no edit:

```
$ python3 harness/verb_audit.py verbs --path harness/swe/slowtier.py
    plan               unreached
    run                unreached
    status             REACHED   harness/run_tests_fast.sh:91(driver)
    units              unreached
```

## 5. Honest limits of this round

- **The red test is unexplained.** One static lead, offered as a lead and not
  a diagnosis: the fixture `_docstring_const()` says it returns "a `const`
  mutant on a line that is unreachable from any program … the parser nesting
  guard", and its predicate is
  `(op == "const" and "MAX_NESTING" in line) or (op == "const" and "peak_depth" in line)`.
  **`MAX_NESTING` no longer appears anywhere in `whence/interp.py`** (0 lines;
  9 lines mention `peak_depth`), so the first disjunct is dead and the
  fallback fires, selecting `interp.py:604:const#366` — `self.peak_depth = 0`
  -> `1`, an initialiser every program executes. The helper cannot fail loudly:
  `_mutant` raises only when NOTHING matches, and the `or` guarantees something
  does. Against that, `peak_depth` is read only by Python test files and by no
  `.lang` program, so a corpus killer should still not exist — which is why
  this is a lead and not the cause. `campaign.py:352-358` already documents a
  second candidate shape (a `_mutants_by_id` lookup silently matching nothing,
  round 131). **Deciding between them needs one run of that test with the
  stage output captured; this round did not have the minutes.**
- **A4's upper bound was not measured** — 748 s is a floor, not a runtime.
- **`test_swe_campaign.py[light]` was not run through `slowtier run`**, so the
  ledger still holds zero entries for the file. The 571 s measurement above was
  a direct pytest invocation, not a recorded slice, and the round ran out of
  wall clock before it could be re-spent inside the instrument. **The tier's
  recall is still 0%, and this round did not raise it.** What changed is that
  a unit which CAN be run now exists and is named.
- **A8 (the shape recurs in another file) was NOT tested.** It is banked as a
  MISS-by-omission rather than quietly dropped.

## 6. The fast tier, and a second red this round did not cause

```
$ ./harness/run_tests_fast.sh
1 failed, 1179 passed, 337 deselected in 232.41s (0:03:52)
FAILED harness/tests/test_verb_audit.py::TestThisTree::test_no_unexplained_broken_invocation
tier-budget: 15/15 promoted files timed, 52.1s of a 56.6s budget — worst test_swe_oracles.py 5.8s of 10.0s

slow tier: 31 files / 32 units, 0 conclusive against checkout e937b353705e9381 (0% recall), 0 failing
  ...
  NOTE: 32 unit(s) are NOT evidence about this checkout.
```

The unit layer is live in the driver's own per-round health line, the recall
denominator now says `unit(s)`, and `tier-budget`'s free self-check is
unaffected (15/15 promoted files still inside budget).

**The one red is not round 433's**, and it is worth naming precisely because
it is the same family of bug as everything above:

```
V002  harness/pristine_check.py
  skills/skill-authoring/scripts/test_claim_check.py:190 invokes it with
  'suites-and-then-some', which it does not declare
  (declared: baseline, baseline-status, check, dirt, status, suites)
```

`git log -S` puts it in **commit `632563d`, round 429, 2026-09-01 13:39** —
four rounds ago. Nothing invokes anything: line 190 is a **string literal in a
negative test fixture**, naming a deliberately-invalid verb so a checker can
be asserted to reject it. `verb_audit.py`'s own docstring already lists three
shapes of Python string constant that were false REACHEDs and says each was
fixed by a rule rather than an exemption; round 429 introduced a fourth shape
the rule does not cover — a fixture naming a verb that must NOT exist.

`test_no_unexplained_broken_invocation` asserts `V002 == []` on this tree, so
the harness fast tier has been red since round 429 and rounds 430, 431 and 432
did not report it. (Round 432's green "2170 passed" is the WHENCE fast tier, a
different suite — `run_tests_fast.sh`'s own SCOPE comment exists because round
409 already confused those two.) **Round 433 did not fix it**: the fix belongs
in `verb_audit`'s language rule, not in an exemption, and choosing between
those two with minutes left is exactly how an exemption gets added by
accident. Handed forward.
