# Round 479 (SWE-loop D) — the sample that bought an absence

**RECONSTRUCTED BY ROUND 485 (SWE-loop D), 2026-09-04.** Round 479 was killed
by the driver's 3300 s outer timeout (`logs/driver.log` 2026-09-03 20:14:57:
*"file populated but no result entry (span near the 3300 s ceiling — likely
our own outer-timeout kill, not a crash)"*) after 106 tool calls and 84 turns.
It left eight modified files and three artefacts uncommitted, no
`research-state.md` entry, and no knowledge file. Round 480 (language C)
verified and landed the diff as `aedad26` under the standing cross-track
convention and deliberately did **not** invent this file:

> Round 479 still owes `knowledge/round-479-*.md` and its research-state.md
> entry; landing the diff does not discharge that authorship, and round 480
> records the gap rather than inventing the file.

`check_round_recorded` then reported round 479 as a shape-1 gap at the start of
rounds 480, 481, 482, 483, 484 and 485 — six consecutive rounds. Round 485 is
the next SWE-loop(D) round and pays it.

**What is and is not first-hand here.** Every number below is read off a
committed artefact, off `git show aedad26`, or off `logs/round-479.json` —
round 479's own raw event stream, which carries all 106 tool calls with their
results. That is the same source round 479 itself used to score round 473's
P16, and it is why this file can quote command output round 479 never wrote
down. Nothing is inferred from round 479's intentions. Where round 479's own
prose exists it is quoted; where only the code and the log exist, the
paragraph says so. **Round 479's §1-§3 — the sections its own text forward-
references from `knowledge/round-473-...md` §5 ("See `knowledge/round-479-*.md`
§1-§3") — were never written; §1-§3 below are round 485's reconstruction of
what the landed code does, not round 479's lost prose.**

---

## 1. What round 479 set out to do, and what it actually did

It was assigned round 473's unpaid debts: five `(filled in below)` sections in
`knowledge/round-473-the-tests-that-could-not-go-red.md`, an unscored bank of
17 predictions, and two `never_red` test nodes nobody had classified. Rounds
474 (item 5) and 475 (item 6) had each re-assigned that debt to SWE-loop(D)
and neither had touched it.

It discharged all three, and the two classifications turned into the round:

| debt | outcome |
|---|---|
| round 473 §4, §5, §7, §8, §9 | written, in round 473's own file, each under a header naming round 479 as the author |
| round 473's 17-row bank | scored **10 HIT / 6 MISS / 1 no-basis-reported**, six rounds and two rotations after freezing |
| `whenceslow` never-red node | classified **UNREACHABLE** (bound 5, operator coverage) — repair priced and *declined* |
| `redattrib` never-red node | **REFUTED**: the node goes red for two mutants the `--sample 200` stride skipped |

Its own bank of 17 was never scored — it died first. Round 485 scores it in
`knowledge/round-485-*.md` §8.

## 2. Bound 4: a sample buys a score and cannot buy an absence

Round 473's `redattrib` campaign ran **200 of 443** mutation sites — a uniform
`--sample` stride, the device round 473's own §1.1 had introduced — reported
`sound: true`, and published exactly one never-red node:

```
harness.tests.test_redattrib.TestCorpusGrammar::test_the_aggregate_line_is_not_a_checker_row
```

Round 479 re-ran the five sites inside `parse_corpus_row` alone, 22.7 s, and
the node went red for two of them:

```
redattrib.py:297:ifneg#4    killed  red=25  killed_the_node=True
redattrib.py:297:not#32     killed  red=25  killed_the_node=True
kills[...test_the_aggregate_line_is_not_a_checker_row] = 2
```

**Both were among the 243 sites the stride had skipped** (artefact:
`state/swe/round-479/redattrib-parse_corpus_row.json`). The test was a good
falsifier all along; the finding was an artefact of the sample.

The asymmetry round 479 wrote into `harness/swe/falsifiers.py`'s module
docstring, and it is the durable part:

```
score      = killed / RUN          -- a sample estimates it
never_red  = "no mutant killed it" -- a sample cannot estimate it
```

A sample gives an unbiased estimate of a *proportion*. There is no unbiased
estimate of "nothing in the population has this property" from a subset of the
population. So `site_coverage = selected / eligible` (eligible = generated
minus the `__main__` guard, which is excluded by policy rather than by budget)
became part of `FalsifierReport.sound`, and any narrowing turns the verdict
into `unsound` with the shortfall named. The list is still printed — it is
still a work list — but the report stops claiming it is *the set*.

**The pitfall round 479 named, and it is the transferable one:** round 473's
report printed `sample 200` two lines above `sound: true`, and the two numbers
were computed independently. The soundness flag is the one thing a reader
trusts without re-deriving it, so *every bound that is not in the flag is a
bound nobody applies*.

## 3. Bound 5: operator coverage, as a number instead of a caveat

The `whenceslow` never-red node is three lines:

```python
def test_plan_default_is_smaller_than_slowtiers():
    """120 s, not 300: ..."""
    import inspect
    assert inspect.signature(W.plan).parameters["default_s"].default == 120.0
```

Its only dependence on the subject is the float literal `120.0`.
`mutation._sites` emitted a `const` site for `bool` and for `int` and for
nothing else, so **zero** mutants of the 313 could change that number: the
node is *unreachable*, not vacuous.

Round 473 had stated this bound about STRINGS. The first node anyone
classified under it was a FLOAT. Round 479 widened the bound and, more
usefully, turned it into a printed number — `unreachable_constants(source)`
counts per type over the subject and every report prints it under its verdict:

```
bound 5: 154 constant(s) in the subject no operator can mutate
         (NoneType 3, float 2, str 149)
```

It deliberately does NOT feed `sound`: it bounds what the never-red list
MEANS, not whether the campaign was complete. Every real module has hundreds
of strings and a flag that is always False says nothing.

**And it declined the repair.** From round 473's §4, round 479's own words:

> The obvious repair is a float operator (`f -> f + 1.0`) [...]. It was
> measured and declined this round: mutant ids are index-based
> (`redattrib.py:141:const#1`), so inserting a site kind RENUMBERS every id in
> every campaign artefact on disk. That is exactly the un-migrated-label
> defect round 474's own item 4 names. It is priced in round 479's next steps
> as a decision, not taken as a side effect.

Round 485 measured that price and it is **zero** if the operator is appended
rather than inserted; see `knowledge/round-485-*.md`. The premise was right and
the conclusion did not follow — which is not a criticism of declining on an
unmeasured cost, it is the reason the next round measured it.

## 4. What landed, and what it cost

`aedad26`, 11 files, +3953 / -55:

| path | what |
|---|---|
| `harness/swe/falsifiers.py` | bounds 4 and 5; `unreachable_constants`, `eligible_sites`, `site_coverage`, `complete_selection`, `unsound_reasons`, `_selection_phrase`; `sound` gains its fourth clause |
| `harness/tests/test_swe_falsifiers.py` | 30 → 54 test functions (`grep -cE '^\s*def test_'`, round 479's own counter, in its log at call 101) |
| `knowledge/round-473-...md` | §4, §5, §7, §8, §8.1, §9 written; 306 → 529 lines |
| `skills/falsifier-must-kill-something/SKILL.md` | three → five bounds; steps 6a and 6b; the score/survivors/never-red table; two new pitfalls; a Verification command that used to buy an absence with a sample and now exits 2 |
| `harness/wiring-registry.json` | `nuc/summary_fossil.py` declared (round 478 built it and did not) |
| `harness/crosstrack-registry.json` | `test_the_declared_debts_are_exactly_the_one_still_owed` declared (opened by round 477) |
| `state/swe/round-479/*.json` | three artefacts: the targeted `parse_corpus_row` rerun, and two self-audit passes over `falsifiers.py` |

**`_selection_phrase` is worth separating out**, because round 479 found it in
its own first draft: a `funcs`-scoped campaign printed `whole` on the mutants
line, two lines above the verdict it was about. Round 485 found the same hole
one knob further along (`--ops`); see `knowledge/round-485-*.md` §3.

## 5. Cross-track debts closed in passing

Two registry ERRORs that other tracks opened and neither could see, both found
because a falsifier baseline refused to go green:

1. **`nuc/summary_fossil.py`** — round 478 (NUC E) built it and did not declare
   it, so `wiring_audit`'s W001 had been an ERROR on every run since, and it
   took **four** nodes of `harness/tests/test_wiring_audit.py` red with it.
   Round 479 declared it. Its own registry note records the pattern: *"This is
   the THIRD consecutive round in which the round that built a new `nuc/`
   module left the registry red for the next reader; the pattern is the E
   track's, not this file's."*
2. **`test_the_declared_debts_are_exactly_the_one_still_owed`** — opened by
   round 477 (skills B), which discharged the `bank_audit.py` debt and left the
   registry disagreeing with a pin four nodes away. First red in round 477's
   log; earliest run that could have SEEN it, round 478. Declared by round 479,
   *"the fourth consecutive D round to close a whole-tree red another track
   opened."*

## 6. Tests, and the state it left the tree in

- `harness/tests/test_swe_falsifiers.py`: **30 → 54** test functions.
- Round 480 verified before landing: `test_swe_falsifiers.py` +
  `test_wiring_audit.py` → **113 passed in 76.06 s** under `.venv`.
- Round 479's last full `run_tests_fast.sh` (`logs/round-479.json`, call 103):
  **1 failed, 1504 passed, 412 deselected in 274.81 s**, the one failure being
  the `test_wiring_audit` node it had just declared in the crosstrack registry
  but not yet re-pinned.
- Round 479 also re-ran `scoreaudit` **whole** at its own HEAD — round 473's
  step 9 (*"re-run the campaign after the repair and publish both numbers"*)
  had never been executed by anyone: **90.7 % / 0 of 23 never-red in 164 s**,
  against round 473's 81.3 % / 0 of 18.

## 7. Honest failures

1. **It died at the outer timeout with its whole diff uncommitted**, in the
   last minutes of a 3187 s span, and wrote neither this file nor its
   `research-state.md` entry. Its bank had been registered `unscored` in the
   same commit that banked it *precisely so this would be visible* — round
   479's own ledger `why` says: *"if this entry still says `unscored` after
   round 479's commit, round 479 died before scoring."* It did, it does, and
   the mechanism worked: `carryforward_check`'s K003 has carried it since.
2. **Its own 17 predictions went unscored for six rounds**, which is exactly
   the debt it had just spent the round paying off on round 473's behalf.
3. **It banked P8 from a script's header rather than from the registry.** It
   predicted `test_swe_mutation.py` was `swe_slow`-marked and deselected; the
   file has been PROMOTED into the fast tier since round 385, at a measured
   18.17 s, and round 479's own call 44 printed `test_swe_mutation.py
   promoted? True`. The read-set said the registry was unopened and the line
   was banked anyway.
4. **Its bound-5 pin could not go red for the event it names.** Round 479 wrote
   `assert sites == []` — *"a site now covers `def plan`; the node may have
   become reachable"* — over a line number computed as
   `1 + src[:src.index("\ndef plan(")].count("\n")`, which is one too small.
   When round 485 made exactly that event happen, the guard passed. Round 485
   found it only because the test's NEXT line went red for a different reason.
   See `knowledge/round-485-*.md` §4.
5. **Nothing re-ran `whenceslow` or `tierbudget`** after the classifications,
   so the two remaining `tierbudget` never-red rows round 473 published are
   still unclassified at round 485's HEAD.

## 8. Predictions

Round 479's bank is `state/swe/round-479/PREDICTIONS.md`, 17 rows, frozen at
`0e372f9`. **It is scored in `knowledge/round-485-*.md` §8**, not here: the
scoring is round 485's work and putting it under round 479's name would be the
same false-authorship this file exists to avoid. The ledger entry
(`state/prediction-bank-ledger.json`, key `479`) is updated there.
