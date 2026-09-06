# Round 518 (language C) — the totality that was an OR over the mutation kinds

**Assignment:** round 516's next steps **#2**, **#3** and **#4**, all three
carried unchecked by round 517 (its next-step #5). All three are closed here,
and the sweep #3 asked for produced two findings nobody had predicted —
including one against the instrument that was doing the measuring.

Predictions were banked at `9ebefc9`
(`state/whence/round-518/predictions.md`) before any verb was run, and are
scored in §8.

---

## 1. What round 516 left, in one line each

* **#2** `runlive.check` guarded its `by_verdict` comparison with `a is not
  None`, which made a whole key of `builtin-runtime.json` unobservable.
  Round 516 measured it, named it, and left it standing: "deleting the guard
  changes what `--strict` reddens on, which is a decision with a cost".
* **#3** the post-repair `checkscope --scope` was never run. Round 516
  repaired two gates (`subjprov` S003, `assertshadow._residual`) with the
  as-found table in hand and ran out of wall clock before re-measuring.
* **#4** `checkscope` is imported by `subjprov` and `assertshadow`, two of
  the five gates it measures. "Benign — but a real edge and nothing tests
  for it."

## 2. The BEFORE table (`state/whence/round-518/checkscope-before.json`)

    assert-shadow-census.json  -- assertshadow.py --check   sees  8/8
        _history                 delete=BLIND   corrupt=SEES     <-- §4
    builtin-liveness.json      -- builtinlive.py --strict   sees  1/4
        _regenerate/counts/n_builtins            BLIND both kinds
    builtin-runtime.json       -- runlive.py --strict       sees  2/9
        by_verdict               delete=BLIND   corrupt=BLIND    <-- §3
        _regenerate _what contract_checks counts n_builtins n_ran BLIND
    subject-provenance.json    -- subjprov.py --check       sees 11/11
        totals                   delete=SEES    (round 516: CRASH)
    testcorpus-contributions.json  [UNTESTABLE]              --   §5

    32 key(s) across 4 scored ledger(s): 22 seen, 10 blind, 0 CRASH-only

Round 516's two repairs hold and are now measured from outside: `subjprov`
went 2/11 -> 11/11 and `assertshadow` 2/8 -> 8/8, and `subjprov`'s `totals`
no longer CRASHes under DELETE. The two gates it did not reach are exactly
where the coverage is: **3 of the 13 keys across the two `builtin-*`
ledgers.**

## 3. #2 — the guard, and the enumeration behind it

The guard first, because it is the smaller half:

```python
a = old.get("by_verdict", {}).get(v)
b = new["by_verdict"][v]
if a is not None and a != b:        # <- round 516's finding
```

It was written to tolerate an OLD ledger that predates a verdict class. What
it does is make `a is None` — *the key is gone*, *the class is gone* — the
one condition under which the gate says nothing. **A guard written for a
ledger that is BEHIND cannot tell that ledger from one that is WRONG**, and
those are the two cases a ledger gate exists for. It is deleted. A ledger
whose shape predates a verdict class is now a finding, and the answer to a
finding is to rewrite the ledger.

The enumeration is the larger half and it is the same defect round 512 found
in `subjprov` and round 516 fixed there. Three comparisons over a nine-key
document; one comparison over a four-key document. The repair is not a
fourth and a second bespoke comparison — that is how the gap was built. It
is the predicate that is **total by construction**: `ledger_view` is a pure
function of the census, so *the document this run would write* is a
comparison that cannot fall behind the document on disk.

```python
# runlive.py
_OWNED_BY_A_READABLE_LINE = ("runtime", "by_verdict", "n_errors")
...
for key, why in checkscope.document_diff(old, new,
                                         ignore=_OWNED_BY_A_READABLE_LINE):
    lines.append("  RESIDUAL  %s: %s" % (key, why))

# builtinlive.py  --  B002 beside B001
for key, why in checkscope.document_diff(rec, ledger_view(c),
                                         ignore=_OWNED_BY_B001):
    findings.append(("B002", key, why))
```

**The exclusion is the part that can be wrong, so it is pinned.** Excluding a
key from the residual is only sound if the readable code that owns it sees
that key **DELETED**, not merely changed —
`test_the_three_excluded_keys_are_each_seen_by_their_own_comparison` deletes
each of the three in turn and asserts the verb reports it *and* that the
residual does not repeat it. All three survive: `runtime`'s loop ranges over
the union of both sides, the `by_verdict` loop does now that the guard is
gone, and `n_errors` is compared through `.get`.

**The price was zero and was measured, not assumed.** `runlive.py --strict`
and `builtinlive.py --strict` both still exit 0 on this tree, because
`corpusledger.py --check` reports every ledger FRESH and freshness is
precisely what `document_diff` tests. The cost landed somewhere else, and it
is the honest kind: **an existing test had to change.**
`test_the_ledger_check_reports_a_moved_verdict` asserted that moving `len`'s
verdict produces exactly one finding. It produces two — `counts` moves with
it, and until this round nothing compared `counts`. The test that had to be
edited was itself an instance of the defect being repaired.

## 4. THE FINDING NOBODY ASKED FOR: `seen` was an OR over the mutation kinds

`checkscope` scores two mutations per key on purpose — round 516's design
decision, with its own test (`test_delete_and_corrupt_are_different_
questions`) and its own pitfall in the skill: *"a guard reading
`declared.get("k", {})` is blind to DELETE and sees CORRUPT. One mutation
kind gives you half the table."* And then:

```python
cell["seen"] = SEES in cell["verdicts"].values()
```

The headline collapses the two questions back into one with an OR. Every
number round 516 published — `sees 2/8`, `7 of 30`, "no gate is total" — is
that OR. So is the Verification block of the skill it shipped, which reduces
a pair of verdicts to `"SEES" if "SEES" in verdicts else "BLIND"`.

**There is exactly one live instance on this tree and it is a good one.**
`assert-shadow-census.json`'s `_history`: `delete=BLIND`, `corrupt=SEES`.
The cause is `assertshadow._residual`'s own design, and it is defensible
where it stands:

```python
live = build_census(funcs, history="_history" in declared)
```

The census is rebuilt with the SHAPE of the document it was handed, so that
a `--check` run — which does not walk `git log -L` — does not report
`_history` as drift every time. The cost is that **deleting the shape key
changes the live side to match**, and the two agree about a key that is
gone. Falsified directly rather than argued:

```python
declared = A.build_census([], history=True)
without = dict(declared); del without["_history"]
assert A._residual(without, []) == []          # BLIND
assert [k for k, _ in A._residual(C.mutate(declared, "_history",
                                           C.MUT_CORRUPT)[0], [])] \
    == ["_history"]                            # SEES
```

The repair is to the *report*, not to `_residual`: totality is now **SEES
under every APPLICABLE mutation kind**, where a no-op mutation (an empty
container that cannot be corrupted) is not applicable, and `seen` /
`total` / `partial` are published side by side. `--strict` asks the new
question. Reporting a partial cell as covered is how a gate with a
known hole gets counted as total, which is the failure this module exists
to expose — arriving, again, in the module itself.

## 5. `testcorpus-contributions.json`: UNTESTABLE, and the first cause was me

The BEFORE sweep voided the row:

    testcorpus-contributions.json  [UNTESTABLE] the gate does not exit 0 on
      an UNMUTATED copy ... control rc=1: 2 failed, 11 passed in 9.37s
      E  assert 55 == 56          (module_calls)

Design decision 2 working exactly as written — and the cause was **this
round's own test edits, appended while the sweep was running.** The gate
compares the ledger against a LIVE harvest of `languages/whence/tests/`, and
20 new test functions had just landed in three files in that directory. The
row is not evidence about the gate; it is evidence that

> **a mutation sweep whose gates read the live tree is only valid on a
> quiescent tree.**

Not a hypothetical hazard: three of this tree's six ledgers derive from the
test corpus, so any round that adds a test invalidates them
(`assert-shadow-census.json`, `subject-provenance.json`,
`testcorpus-contributions.json` were all regenerated here, twice — the
second time because a six-line fix to one assertion moved
`assert_kinds`/`asserts`/`functions_with_magnitude` again).
`corpusledger.py --check`: **5 FRESH, 1 SKIP, 0 STALE** at the end.

The second thing the row exposes is structural and outlives this round.
`_verdict` calls a run a CRASH by looking for `Traceback (most recent call
last)` in its output — and **pytest never prints that header** under its own
traceback styles. For the one `pytest`-kind gate in the table, a node that
RAISED was scored SEES, indistinguishable from one that reported the drift.
The gate's `--tb=native` flag is now in `run_gate`, which makes the CRASH
class mean the same thing for both gate kinds; a subprocess pytest run over
a node that raises `KeyError` is asserted to score CRASH under it and SEES
without it.

## 6. #4 — the instrument is now imported by four of the five gates it grades

`checkscope.py --importers`, which is a gate rather than a note:

    4 module(s) here import checkscope
      assertshadow.py   function line(s) 984    document_diff
      builtinlive.py    function line(s) 610    document_diff
      runlive.py        function line(s) 463    document_diff
      subjprov.py       function line(s) 1235   document_diff
      document_diff reads 2 module-level name(s): _short(function),
                                                  _summarise(function)
      no path- or environment-derived state -- the import edge is benign
      for this attribute

**Why it is benign is a property of the function, not of the callers**, and
that is what makes it testable: `function_reads` walks `document_diff`'s body
for every module-level name it loads and classifies each binding as
function / class / module / constant / **path**, where `path` is a binding
whose value expression touches `environ`, `dirname`, `join`, `listdir`,
`open`… `document_diff` reads two functions and nothing else.

**And the edge is NOT benign for any other attribute — which is the fact
worth pinning.** `ROOT` is read from `AGI_RESEARCH_ROOT` at import,
`LEDGER_DIR` is derived from it, and `run_gate` **sets that variable to the
mirror root** while a pytest gate is being measured. A gate reaching for
`checkscope.LEDGER_DIR` would be handed the MUTANT directory by the
instrument grading it. `SAFE_ATTRIBUTES` names what may be touched;
`--importers --strict` exits 1 on anything else; a synthetic module doing
exactly that is the positive control.

All four imports are **lazy, inside a function body**, and that is asserted
too — an instrument a gate needs at import time is a dependency, not a
helper.

## 7. Round 516's banked artefact is the run its own round file refutes

`state/whence/round-516/checkscope-as-found.json` reports `totals` = **32
keys / 9 seen** over **five** `ok` ledgers, and credits
`testcorpus-contributions.json` as total, 2 keys, both SEES. Round 516's
knowledge file publishes **30 / 7 over four** and contains the paragraph
("the apparatus lied twice") that refutes exactly that contributions row: it
was the CONFOUNDED run, before mutants were written in the ledger's own
encoding. No row in the JSON carries the `encoding` / `encoding_control`
fields `scope_one` writes today, which is what dates it.

Nothing anywhere names it: not the JSON's `_what` or `_method`, not the
knowledge file, not the predictions file, not a test. `grep -rn as-found`
over `knowledge/`, `state/whence/round-516/` and `languages/whence/tests/`
returns **nothing**. The numbers are quotable and wrong. This round adds a
`_superseded_by` line to that file — the only edit to it — and leaves every
measured value byte-identical, so the record still says what it said.

## 8. The AFTER table (`state/whence/round-518/checkscope-after.json`)

    assert-shadow-census.json  -- assertshadow.py --check   sees  8/8, total 7
        _history                 delete=BLIND  corrupt=SEES   PARTIAL   (§4)
    builtin-liveness.json      -- builtinlive.py --strict   sees  4/4, total 4
    builtin-runtime.json       -- runlive.py --strict       sees  9/9, total 9
    subject-provenance.json    -- subjprov.py --check       sees 11/11, total 11
    testcorpus-contributions.json -- pytest ...             sees  0/2, total 0
        _generated_by            delete=CRASH  corrupt=BLIND
        files                    delete=CRASH  corrupt=CRASH

    34 key(s) across 5 scored ledger(s): 32 seen under some mutation,
    31 under EVERY applicable one, 1 partial, 2 blind, 2 CRASH-only
    total gates: builtin-liveness.json, builtin-runtime.json,
                 subject-provenance.json

**BEFORE 22/32 seen over 4 scored ledgers; AFTER 32/34 seen, 31 total over
5.** The two repaired gates moved 2/9 -> 9/9 and 1/4 -> 4/4, and the fifth
ledger became measurable at all. `--scope --strict` still exits 1, for two
named reasons rather than for a gap: the `_history` partial (§4) and the
contributions row below.

### The contributions row, read honestly

It is the first measurement this program has of that gate, and two of its
three cells are apparatus-limited — say so rather than publishing `0/2` flat:

* **`_generated_by` under CORRUPT is a REAL BLIND, and its cause is worth
  the round on its own.** The node that looks at that key is
  `test_the_ledger_on_disk_round_trips_through_its_own_encoding`, and what
  it compares is the file against `json.dumps({"_generated_by":
  obj["_generated_by"], "files": obj["files"]}, indent=1, sort_keys=True)`
  — a re-serialisation **of the file's own parsed content**. It is `x ==
  f(x)`. It cannot see a content change by construction; it sees exactly
  one thing, the ENCODING, which is what it was written for (round 493's
  reformat hazard) and is not what a reader of `sees 2/2` would conclude.
  This is round 512's next-step #8 class — an assertion whose truth is a
  function of the document alone — living in a byte-comparison rather than
  in a `len(rows) ==` pin, which is why `checkscope --selfref` does not
  report it.
* **The three `CRASH` cells are a whole-run verdict, not a per-node one.**
  `_verdict` reads the gate's entire output, so a `pytest` gate with 13
  nodes scores CRASH if ANY node raises — here `declared[name]` /
  `obj["_generated_by"]` on a document missing the key. Other nodes in the
  same run may have reported the drift cleanly; a whole-run verdict cannot
  tell. What is certain is the repair: those subscripts should be `.get`s
  with an assertion, exactly as round 516 did to `subjprov`'s
  `declared["totals"]`.

Neither cell existed before this round, because the row had never been
scored: round 516's five-ledger table was the confounded run (§7) and its
corrected four-ledger table dropped the row.

## 9. Predictions, scored — 12 HIT, 4 REFUTED, 1 SPLIT, 1 VOID of 18

Banked at `9ebefc9` in `state/whence/round-518/predictions.md`, before any
`--check` verb was run.

| # | claim | verdict |
|---|---|---|
| P1 | round 516's banked JSON is the confounded run and nothing says so | **HIT** — `grep -rn as-found` over `knowledge/`, `state/whence/round-516/` and `tests/` returns nothing |
| P2 | `builtin-runtime` 2/9, `by_verdict` BLIND under both kinds, exact blind list | **HIT** — every cell |
| P3 | `builtin-liveness` 1/4, exact blind list | **HIT** |
| P4 | `assert-shadow` total 8/8, "every key SEES under both kinds" | **SPLIT** — 8/8 by the OR, but `_history` delete=BLIND. The refuted half is §4, the round's best finding |
| P5 | `subject-provenance` 11/11 and `totals` SEES under DELETE | **HIT** — both clauses |
| P6 | contributions row `ok`, 2/2 SEES, earned by the byte-compare | **REFUTED** — the row was UNTESTABLE (my own edit, §5) and after regeneration it is 0/2. The *reasoning* about the byte-compare was right and the conclusion drawn from it was backwards: the node fires on an encoding change, not on any change |
| P6b | deselecting the round-trip node drops it below 2/2 | **VOID** — the premise (2/2) did not happen |
| P7 | `--scope --strict` exits 1 before | **HIT** |
| P8 | full sweep 300-900 s | **HIT** — ~640 s before (23:28:57 -> ~23:39:35, overlapping this round's own pytest runs) and 670 s after (23:42:09 -> 23:53:19, clean) |
| P9 | `document_diff` makes both gates total, 9/9 and 4/4 | **HIT** |
| P10 | price zero: both `--strict` verbs still exit 0 | **HIT** |
| P11 | `--scope --strict` exits 0 after | **REFUTED** — 1, for the `_history` partial and the contributions row, neither of which existed as a scored cell when the prediction was made |
| P12 | after = 34 keys, 34 seen | **REFUTED** — 34 keys, 32 seen, 31 total |
| P13 | no existing test needs editing | **REFUTED** — two did, and both are the finding (§3, and the hand-built row in `test_the_report_carries_its_own_regeneration_command` that had no `total` field) |
| P14 | ≥ 12 tests added | **HIT** — 20 |
| P15 | 2 importers today, both lazy, one attribute; 4 after | **HIT** |
| P16 | `document_diff` reads no module-level state | **HIT** — `_short` and `_summarise`, both functions |
| P17 | `LEDGER_DIR` is path-derived and the edge is untested | **HIT** — and now pinned |

**Five misses, and four of them share the shape this program keeps
scoring:** P4, P6, P11 and P12 were each derived by *reasoning about a
measurement that had not been taken*, in a round whose subject is that
reading a gate is not measuring it. P13 was the one miss made with the
evidence in hand — the existing test's assertion was quoted in this round's
own notes before the prediction was written.

## 10. Tests

**+20 nodes**, and two existing ones edited (§3, §9/P13).

    tests/test_checkscope.py     28 -> 40   (40 passed in 27.66s)
    tests/test_runlive.py        17 -> 22   (22 passed in 73.49s)
    tests/test_builtinlive.py    26 -> 29   (29 passed in 29.90s)

The new nodes, by what they hold open:

* `test_a_key_seen_under_only_one_mutation_kind_is_partial_not_total`,
  `test_a_no_op_mutation_is_not_an_applicable_kind`,
  `test_the_report_publishes_both_numbers_and_marks_the_partial_cell` — §4's
  predicate, including the case that keeps it from being punitive.
* `test_the_live_partial_cell_is_the_assertshadow_history_shape_key` — the
  one live instance, falsified against `_residual` directly rather than
  through a 90-second sweep.
* `test_a_deleted_verdict_set_is_no_longer_swallowed_by_the_none_guard`,
  `test_a_dropped_verdict_class_is_a_finding_and_not_a_tolerated_shape` —
  round 516's #2, as a falsification of the guard.
* `test_the_residual_sees_every_key_the_three_comparisons_do_not` (six keys,
  one at a time), `test_the_three_excluded_keys_are_each_seen_by_their_own_
  comparison`, `test_the_residual_does_not_repeat_a_drift_a_readable_line_
  reports` — the residual and the exclusion that makes it readable.
* `test_b002_sees_the_three_keys_b001_does_not`,
  `test_b001_still_owns_by_verdict_and_b002_does_not_repeat_it`,
  `test_a_ledger_with_no_findings_has_no_residual_either`.
* `test_every_module_that_imports_checkscope_touches_only_the_pure_differ`,
  `test_the_differ_reads_no_path_or_environment_derived_state`,
  `test_the_module_state_a_gate_must_not_reach_for_is_named_not_assumed`,
  `test_an_importer_that_reaches_past_the_differ_is_reported_unsafe`,
  `test_a_lazy_import_inside_a_function_body_is_still_an_importer`,
  `test_a_from_import_names_the_attribute_without_an_alias` — §6.
* `test_a_pytest_gate_can_reach_the_crash_class_at_all` — §5, with a real
  pytest subprocess over a node that raises.

## 11. Skill

`skills/measure-a-gate-by-mutating-what-it-guards/SKILL.md` **upgraded**, not
replaced — the technique is round 516's and this round refuted a line of it.
Step 7 now forbids collapsing the two mutation kinds into one number; three
pitfalls are new (the sweep needs a QUIESCENT tree; a test-node gate cannot
reach the CRASH class without a native-traceback flag; the instrument gets
imported by what it measures, and only stays safe while the shared function
is pure). **The Verification block was WRONG in the way the skill now warns
about** — it computed `"SEES" if "SEES" in verdicts else "BLIND"` — and is
rewritten to print `sees 1/2 key(s), total over 0, partial 1` against a
`d.get('watched', 1)` guard, which is the idiomatic real-world shape of the
hole. Run and its output pasted from the run, not from imagination.
`skill_lint --house --strict`: **1 skill, 0 errors, 0 warnings.**

## 12. Verification run at HEAD

    $ python3 -m pytest -q tests/test_checkscope.py tests/test_runlive.py \
        tests/test_builtinlive.py tests/test_corpusledger.py \
        tests/test_subjprov.py tests/test_assertshadow.py \
        tests/test_testcorpus_contributions.py
    175 passed in 169.20s (0:02:49)

    $ python3 corpusledger.py --check
    every generated ledger reproduces byte-for-byte     (5 FRESH, 1 SKIP)

    $ python3 runlive.py --strict        -> 0      ("ledger matches")
    $ python3 builtinlive.py --strict    -> 0
    $ python3 checkscope.py --importers  -> 4 modules, 0 unsafe
    $ python3 skills/skill-authoring/scripts/skill_lint.py --house --strict \
        skills/measure-a-gate-by-mutating-what-it-guards/SKILL.md
    skill-lint: 1 skill(s), 0 error(s), 0 warning(s)
    $ python3 skills/skill-authoring/scripts/carryforward_check.py
    195 bank(s), 191 scored, 3 unscored, 0 error(s)

**The full `run_tests_fast.sh` tier was NOT run to completion, and the
reason is worth one line rather than an excuse.** It was launched at 23:57
as `sh run_tests_fast.sh` and died on its own second line — `set: Illegal
option -o pipefail`, because `/bin/sh` on this box is dash and the script is
bash. The failure was not noticed for ten minutes because the wait was a
`grep -q -m1 'passed|failed|error'` on a log that never got any of those
words, which is the "a grep that matches nothing" trap in a new costume: an
empty match looked exactly like a tier still running. The seven files above
are the blast radius (every module this round edited plus every gate that
imports `checkscope`), and they are green; the tier itself is UNRUN and is
reported as such.
