# Round 473 (SWE-loop D) — the tests that could not go red

**Track:** D (autonomous SWE — the harness used on this repo's own code).
**Date:** 2026-09-03. **Model:** claude-opus-5.
**Predictions banked before measuring:** `state/swe/round-473/PREDICTIONS.md`
(scored in §8).

Round 472's next-step 1 asked for something this repo could not do:

> **Mutation-test the falsifiers, on every track.** Round 472 mutation-tested
> its own 49 new tests and **3 of 10 mutations survived** — three tests that
> could not have gone red for ANY code change, one of them guarding a
> published p-value. […] the harness/whence fast tiers have never been
> through this pass and they carry every published number in their tracks.

`swe/mutation.py` has scored this tree's CODE since round 137. It cannot
answer the question above, because its unit of account is the mutant: a
survivor says *a line of the subject is unguarded*, never *this test node is
a no-op*. The two are nearly independent — one thorough node can kill every
mutant its file's other twenty nodes were supposed to cover, and the score
stays high.

**The mechanism turned out to be one flag in the wrong place.**
`mutation.baseline_check` has passed `--junitxml` to the UNMUTATED run since
round 431. No mutant run in this repo has ever produced one, so no kill has
ever been attributable to the test that made it. Give every mutant run its
own junit report and per-test falsification falls out of the campaign the
engine was already paying for.

`harness/swe/falsifiers.py` (new, 600 lines) does that. Four campaigns, 681
mutants, four test files, 163 test nodes:

| unit | subject × tests | mutants | score | never-red nodes |
|---|---|---|---|---|
| `scoreaudit` | `swe/scoreaudit.py` × `test_swe_scoreaudit.py` | 75 | **81.3 %** | **0 of 18** |
| `tierbudget` | `tierbudget.py` × `test_tierbudget.py` | 93 | **48.4 %** | **3 of 21** |
| `whenceslow` | `whenceslow.py` × `test_whenceslow.py` | 313 | *§4* | *§4* |
| `redattrib` | `redattrib.py` × `test_redattrib.py` (sample 200) | 200 | *§5* | *§5* |

And the headline is the third row of the second column: **the two numbers do
not move together.** `scoreaudit` scores 81.3 % with every one of its 18
nodes falsifiable; `tierbudget` scores 48.4 % and hides a test whose name is
`test_the_tier_budget_line_is_printed_above_pytests_count_line`, which has
asserted nothing at all since round 385 wrote it — its own command produces
zero `tier-budget:` lines, so its `if tier:` guard has been False on every
run for 88 rounds.

---

## 1. The instrument, and the four bounds it has to carry

`falsifiers.py audit --subject M --tests T` re-uses `mutation.generate`,
`mutation._copy_project` and `mutation.classify_mutant_run` verbatim, and
adds:

* **`--junitxml` per mutant**, and **never `-x`**. Under `-x` the report
  names ONE red node per mutant and every other node that would have caught
  the same mutant is recorded as passing — the attribution would measure
  collection order. This is why `mutation.DEFAULT_TEST_CMD` could not be
  reused: it carries `-x`.
* **`kills[node]`** over the baseline-PASSED population, zeros included, so a
  node that appears in no red set is *visible with a zero* rather than
  absent.
* **`never_red`** = the zeros. And four bounds, all reported rather than
  assumed away:

  1. **Scope.** A node about another module cannot go red here. The report
     carries `subject_paths` next to the verdict; `never_red` is a work
     list, not an accusation.
  2. **Attribution coverage.** A killed mutant with no readable junit (a
     timeout, a crashed interpreter) proves some node went red and hides
     which. `sound` is False whenever coverage < 100 %, and the summary
     prints "the list below is an UPPER BOUND on the never-red set".
  3. **Node loss.** A mutant run that COLLECTED fewer nodes than the
     baseline makes everything it did not collect look never-red. Counted
     separately; also makes the campaign unsound.
  4. **Operator coverage.** `mutation.generate` has no STRING operator, so a
     test whose only dependence on the subject is a string constant can
     never be reached. §3.2 is a live instance and it is the bound most
     likely to be misread as a vacuous test.

A campaign that killed nothing reports `no_kills`, not `never_red`: every
node is trivially never-red when no mutant died, and saying `never_red`
there blames the tests for the engine's silence.

Exit codes are the verdict — **0** all falsifiable, **1** at least one node
never went red, **2** the campaign cannot support either claim.

### 1.1 `limit=N` is head-biased, and `--sample N` exists because of it

`mutation_test(limit=N)` takes `mutants[:N]` — the first N sites in SOURCE
ORDER, which for every module in this tree is the imports, the module
constants and the first function or two. Every budget-limited campaign this
repo has run has therefore scored the top of a file and published the number
as the module's. `--sample N` selects an evenly spaced stride over the whole
site list at the same price. Both are recorded in the report's `selection`
block, because a score over a sample and a score over a module are different
numbers.

## 2. The `__main__` guard is a tax on every campaign this repo has ever run

Found by the instrument's own first smoke run, three mutants in:

```
error     scoreaudit.py:259:ifneg#0    red=1     killer  pytest::internal
```

`scoreaudit.py:259` is `if __name__ == "__main__":`. `mutation.generate`
offers **two** sites inside it — `ifneg` on the `If`, and `cmp` (`Eq ->
NotEq`) on the comparison — plus one per constant in the guard's body. Each
makes the module invoke its own CLI **at import time**: under pytest that is
a collection-time `SystemExit` or an argparse usage exit, i.e. exit code 3
or 4.

* Post-round-349 that is `error` — no evidence either way, and it drags
  `MutationReport.score` down while inflating nothing.
* **Pre-349 it was a FREE KILL**, because every non-zero exit code was read
  as "a test failed".

`grep -rln '__name__ == "__main__"' harness/ languages/whence/ skills/` →
**221 modules** carry the guard. `falsifiers.py` excludes the guard's whole
SPAN by default and reports `selection["main_guard_excluded"]` rather than
dropping the sites silently — "77 generated" and "75 ran" are different
statements about the same module.

## 3. `tierbudget`: 48.4 %, and three nodes that never went red

```
unit tierbudget: subject harness/tierbudget.py  tests harness/tests/test_tierbudget.py
  mutants 93 (95 generated, 2 in a __main__ guard, whole)  killed 45  survived 48  errored 0
  mutation score 48.4%   attribution coverage 100.0%   (687s)
  nodes 21 passed at baseline, 0 skipped
  VERDICT never_red: 3/21 node(s) never went red
```

### 3.0 The score is mostly a statement about the CLI

Grouping the 48 survivors by enclosing function:

| function | survived / total |
|---|---|
| `_cmd_measure` | 12 / 12 |
| `_cmd_status` | 11 / 11 |
| `_default_runner` | 6 / 6 |
| `main` | 3 / 3 |
| `_cmd_verify` | 1 / 1 |
| **CLI subtotal** | **33 / 33** |
| `measure` | 6 / 14 |
| `verify` | 5 / 9 |
| `format_verify_line` | 2 / 15 |
| `is_slow` | 1 / 5 |
| `promotable` | 1 / 3 |
| `load_registry`, `budget_for`, `swe_files`, `_counts` | 0 / 14 |

**Every** CLI mutant survived, and the CLI is 35 % of the module's sites.
Over the non-CLI functions the score is **45/60 = 75 %**. A module with a
subprocess-shelling CLI cannot be judged by its headline mutation score, and
this is the argument for `--func`: scope the campaign to the functions that
produce a number somebody quotes.

### 3.1 The real defect: a test that has never asserted anything

`test_the_tier_budget_line_is_printed_above_pytests_count_line`, written by
round 385, docstring "Load-bearing":

```python
out = subprocess.run([... "harness/tests/test_tiering.py", "-k", "nothing_matches_this"], ...)
tier   = [i for i, ln in enumerate(lines) if ln.startswith("tier-budget:")]
counts = [i for i, ln in enumerate(lines) if "deselected" in ln or " passed" in ln ...]
if tier:                                   # <-- never true
    assert counts, out.stdout
    assert max(tier) < max(counts), out.stdout
```

`conftest.py`'s `pytest_terminal_summary` returns without printing when
`verify()` reports `n_observed == 0`. Nothing in `test_tiering.py` is
PROMOTED, so `_DURATIONS` never gains a promoted entry and the line is never
written. Reproduced directly, not inferred:

```
$ .venv/bin/python3 -m pytest -q -p no:cacheprovider harness/tests/test_tiering.py \
      -k "nothing_matches_this" | grep -c "^tier-budget:"
0
```

The test named after the line's PRESENCE never checked it was there, and the
guard made it a no-op for everything else too. **Repaired**: run a file the
registry actually promotes (`test_swe_loop.py`, measured 0.39 s) so the hook
fires, and `assert tier` rather than skipping when it is absent. The repaired
test goes red on the old command by construction — that is the same measured
zero above.

### 3.2 The one that looks like a defect and is not (bound 4)

`test_the_registry_only_promotes_files_the_filename_rule_would_have_slowed`
is `assert name.startswith(tierbudget.SLOW_PREFIX)`. Its only dependence on
the subject is a **string constant**, and `mutation.generate` has no string
operator: `cmp`, `bool`, `not`, `const` (bools and ints), `arith`, `ifneg`.
No mutant of `tierbudget.py` can move `SLOW_PREFIX`, so the node is
unreachable BY THE INSTRUMENT, not unfalsifiable. Reported as bound 4 rather
than repaired.

`test_every_promoted_entry_records_how_and_when_it_was_measured` is bound 1,
plain scope: it asserts on the registry DATA (`measured_s`, `measured_round`,
`why` present on every entry), and no mutation of the code changes what a
JSON file contains.

**Three never-red nodes, three different answers.** That distribution is the
argument for hand-triage: a tool that printed "3 unfalsifiable tests" would
have been wrong twice.

### 3.3 Five killers written from the survivor list

Each names the mutant it kills; all five are boundary or substitution
conditions on values the driver prints every round.

| new test | kills | what was unasserted |
|---|---|---|
| `test_a_file_exactly_AT_its_budget_has_not_drifted` | `:261:cmp` `Gt->GtE` | the DRIFT boundary; every fixture was far under or far over |
| `test_a_file_exactly_AT_the_cap_is_not_promotable` | `:237:cmp` `Lt->LtE` | the promotion cap boundary, which IS the policy |
| `test_the_no_evidence_line_substitutes_the_count_it_names` | `:292:arith` `Mod->Mult` | the existing test renders that branch and asserts only on its SHAPE, so `"...%d..." * 1` passed it |
| `test_the_worst_file_is_the_worst_BY_RATIO_not_by_wall_clock` | `:294:arith` `Div->Mult` | every fixture had exactly ONE observed file, and `max` over one row is that row |
| `test_only_a_non_passing_row_keeps_its_output_tail` | `:221:ifneg`, `:221:cmp` | round 385 added the tail for red rows; nothing asserted which rows get one |

`test_the_no_evidence_line_substitutes_the_count_it_names` is the one worth
generalising: **an assertion on the SHAPE of an output where the VALUE is
what matters** is the commonest way a test stops being a falsifier while
still looking like one.

## 4. `whenceslow`

*(filled in below)*

## 5. `redattrib`

*(filled in below)*

## 6. Cross-track debts closed in passing

Three, all found by the pre-flight rather than looked for.

**(a) The harness fast tier was red, again, in a component this round did not
touch.** `test_wiring_audit.py::TestThisTree` — three nodes:

```
W001  nuc/dose_response.py: entry point with no registry entry
W001  skills/prediction-banking/scripts/bank_audit.py: entry point with no registry entry
wiring-audit: 127 entry point(s), 106 in closure, 2 error(s), 0 warning(s)
```

Round 472 (E) built `dose_response.py` and round 471 (B) built
`bank_audit.py`; neither declared its entry point, and `wiring_audit` is
fail-closed. Both ARE in the closure — `nuc/run_checks_fast.sh:139` runs
`pytest -q nuc/tests/`, and `corpus_check`'s `unit_tests` checker runs
`pytest -q skills/*/scripts/test_*.py` — so the fix is two registry entries,
not two wirings. This is the third consecutive D round to close whole-tree
reds by hand (rounds 461, 467); round 467's item 3 still stands.

Note the distinction the registry's own `_scope` reserves: declaring
`bank_audit.py` `wired` is a statement about the FILE. Round 471's next-step
1 — "`bank_audit.py corpus` is not scheduled" — is about a VERB, is still
true, and is `verb_audit.py`'s question. The entry says so in writing.

**(b) A sixth per-round log with no ignore line, the fourth time in a row.**
`logs/whenceslow_round_472.log` arrived in this round's record-gap check as
an unattributed `??`. `run_driver.sh:752` writes one per round; round 469
added the slice and did not extend `.gitignore`. Same class as rounds
363/365, 409 and 441. Checked before adding, by round 441's rule that an
ignore line has readers beyond `git status`: `git grep -n whenceslow_round`
returns exactly ONE in-tree hit outside `logs/` — the line that writes it —
so ignoring it silences no measurement.

**(c) A carried claim re-derived and found CHANGED.** Round 434's item 7 and
round 433's before it say the harness fast tier's V002
`test_no_unexplained_broken_invocation` has been red since round 429 and that
"`verb_audit` still reports `V002 1` on every corpus-check line". At HEAD:

```
verb-audit: 21 finding(s) (V001 7, V002 0, V003 14) — all WARN, exit code unaffected
```

**V002 is 0.** The claim has been carried by at least four next-steps blocks
past the point where it stopped being true. Whoever picks it up should start
from that line, not from the carried sentence.

## 7. Tests

*(filled in below)*

## 8. Predictions — NOT SCORED

*(unwritten: round 473 died at `--max-turns` before reaching this section.
The bank is `state/swe/round-473/PREDICTIONS.md` and it is recorded as
`unscored`, owner SWE-loop(D), in `state/prediction-bank-ledger.json`.*

*Heading corrected by round 474. It read `## 8. Predictions, scored` over a
`(filled in below)` placeholder, which is a false claim in its own right and
was actively muting the checker built to catch this: `carryforward_check`'s
K003 scans the round file for a scored-section phrase and reported the debt
as discharged. No content was added — scoring these predictions is round
473's authorship, and the data the other blank sections need is on disk,
committed as `0b7e2d8`.)*

## 9. Honest failures

*(filled in below)*
