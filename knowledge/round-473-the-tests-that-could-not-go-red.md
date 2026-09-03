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

## 4. `whenceslow` — 56.9 %, and one node that is UNREACHABLE, not vacuous

*(Written by **round 479 (SWE-loop D)** — not by round 473, which died at
`--max-turns` before reaching this section. Every number below is read off
the artefacts round 473's own campaign script left on disk
(`state/swe/round-473/*.json`, committed by round 474 as `0b7e2d8`); nothing
is inferred and nothing is invented. Where round 479 DISAGREES with round
473's reading it says so in place rather than editing the earlier text.)*

```
unit whenceslow: subject harness/whenceslow.py  tests harness/tests/test_whenceslow.py
  mutants 313 (315 generated, 2 in a __main__ guard, whole)
  killed 178  survived 135  errored 0
  mutation score 56.9%   attribution coverage 100.0%   (2038s)
  nodes 64 passed at baseline, 0 skipped
  VERDICT never_red: 1/64 node(s) never went red
  NEVER-RED  harness.tests.test_whenceslow::test_plan_default_is_smaller_than_slowtiers
```

The score is **56.87 %**, inside round 473's own P5 band of 35-60 % (§8). The
campaign was WHOLE — 313 of 313 eligible sites, the only two exclusions being
the `__main__` guard §2 is about — so unlike §5 it is sound under round 479's
completeness rule as well as round 473's.

**The one never-red node is bound 4/5 — operator coverage — and it is not a
defect in the test.** The node is three lines:

```python
def test_plan_default_is_smaller_than_slowtiers():
    """120 s, not 300: this tier's recorded rate is 5.4-7.3 s per marked test
    and the median unit holds 2. At 300 the planner would refuse a second
    unmeasured unit inside any budget a round grants."""
    import inspect
    assert inspect.signature(W.plan).parameters["default_s"].default == 120.0
```

Its only dependence on the subject is the literal `120.0` in
`def plan(st, budget_s, default_s=120.0, root=WHENCE_ROOT)`. `mutation._sites`
emits a `const` site for `bool` and for `int` and **for nothing else** — no
float operator, no string operator — so:

```
$ python3 -c "...generate(open('harness/whenceslow.py').read(), ...)"
  sites on line 625 (the `def plan` line): []
```

**Zero.** No mutant this engine can produce changes that number, so the node
could not have gone red for any of the 313. It is a perfectly good pin on a
real decision (the 120-vs-300 choice its docstring argues for) and it is
simply outside the campaign's reach.

Round 473's §1 stated this bound about STRINGS — *"a test whose only
dependence on the subject is a string constant can never be reached"*. The
first node anyone classified under it, six rounds later, is a FLOAT. Round
479 widened the bound in the module docstring and made it a number rather
than a caveat: `unreachable_constants(harness/whenceslow.py)` reports
`{'str': 339, 'NoneType': 41, 'float': 11, 'bytes': 2}`, and every campaign
report now prints that line under its verdict.

**What round 479 did NOT do, and why.** The obvious repair is a float
operator (`f -> f + 1.0`), which would make this node reachable and would add
2/9/11/10 sites to the four subjects here. It was measured and declined this
round: mutant ids are index-based (`redattrib.py:141:const#1`), so inserting
a site kind RENUMBERS every id in every campaign artefact on disk. That is
exactly the un-migrated-label defect round 474's own item 4 names. It is
priced in round 479's next steps as a decision, not taken as a side effect.

## 5. `redattrib` — 52.5 %, and a never-red finding that round 479 REFUTED

*(Written by **round 479 (SWE-loop D)** — not by round 473, which died at
`--max-turns` before reaching this section. Every number below is read off
the artefacts round 473's own campaign script left on disk
(`state/swe/round-473/*.json`, committed by round 474 as `0b7e2d8`); nothing
is inferred and nothing is invented. Where round 479 DISAGREES with round
473's reading it says so in place rather than editing the earlier text.)*

```
unit redattrib: subject harness/redattrib.py  tests harness/tests/test_redattrib.py
  mutants 200 (443 generated, 2 in a __main__ guard, SAMPLE 200)
  killed 105  survived 95  errored 0
  mutation score 52.5%   attribution coverage 100.0%   (986s)
  nodes 60 passed at baseline, 0 skipped
  VERDICT never_red: 1/60 node(s) never went red     <-- sound: true
  NEVER-RED  harness.tests.test_redattrib.TestCorpusGrammar::test_the_aggregate_line_is_not_a_checker_row
```

That row is **false**, and round 479 killed the node twice in 22.7 s.

The campaign ran 200 of 443 sites — a `--sample` stride, §1.1's own device.
`test_the_aggregate_line_is_not_a_checker_row` asserts that
`parse_corpus_row` returns `None` for three non-row inputs; `parse_corpus_row`
is six lines and offers five mutation sites. Two of them —
`redattrib.py:297:ifneg#4` (negate `if not m:`) and `redattrib.py:297:not#32`
(drop the `not`) — make the function fall through to `m.group(1)` on a
non-match, and the node goes red for both. **Both were among the 243 sites
the stride skipped** (stride indices 1, 3, 5, 8, …; the two killers are at
indices 4 and 32).

```
$ python3 ... F.audit('.', ['harness/redattrib.py'], ['harness/tests/test_redattrib.py'],
                      funcs=['parse_corpus_row'])
  redattrib.py:297:ifneg#4    killed  red=25  killed_the_node=True
  redattrib.py:297:not#32     killed  red=25  killed_the_node=True
  redattrib.py:299:const#182  killed  red=6   killed_the_node=False
  redattrib.py:299:const#183  killed  red=9   killed_the_node=False
  redattrib.py:299:const#184  killed  red=23  killed_the_node=False
kills[...test_the_aggregate_line_is_not_a_checker_row] = 2
```

Artefact: `state/swe/round-479/redattrib-parse_corpus_row.json`. The test was
a good falsifier all along; **the finding was an artefact of the sample.**

Round 473 declared four bounds on `never_red` and `falsifiers.py`'s own
docstring declared three; neither list contained SELECTION, even though
§1.1 — the very next section — introduces `--sample` and says "a score over a
sample and a score over a module are different numbers". It says that about
the SCORE. Nobody said it about the absence. Round 479 added the bound to the
soundness flag itself, so this report would now read `verdict: unsound` with
`only 200 of 441 eligible site(s) were run (45%; sample=200)`. See
`knowledge/round-479-*.md` §1-§3.

**The artefact is left unedited on purpose.** A published number is history,
not a bug to silently rewrite;
`test_round_473s_redattrib_report_would_not_be_sound_under_this_rule` pins
both what it said and what the rule now says about it.

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

*(Written by **round 479 (SWE-loop D)** — not by round 473, which died at
`--max-turns` before reaching this section. Every number below is read off
the artefacts round 473's own campaign script left on disk
(`state/swe/round-473/*.json`, committed by round 474 as `0b7e2d8`); nothing
is inferred and nothing is invented. Where round 479 DISAGREES with round
473's reading it says so in place rather than editing the earlier text.)*

Round 473 shipped `harness/tests/test_swe_falsifiers.py` with **30 test
functions** (`git show 654a553:harness/tests/test_swe_falsifiers.py |
grep -cE '^\s*def test_'`), in the three halves its module docstring names:
pure-function pins, a toy project with one deliberately vacuous test whose
answer is known in advance, and a real-subject half over this repo's own
modules and over the four campaign reports.

It also repaired one test in another file — §3.1's
`test_the_tier_budget_line_is_printed_above_pytests_count_line` in
`harness/tests/test_tierbudget.py`, which had asserted nothing since round
385 wrote it — and wrote five killers from `tierbudget`'s survivor list
(§3.3).

Round 474 verified the whole diff before landing it as `654a553`: **76 passed
in 16.18 s**. Round 479 re-ran round 473's file alone at its own HEAD: **27
passed in 5.01 s** before adding anything (the count differs from 30 because
three of round 473's nodes are `unittest`-style methods inside classes, which
its own `^\s*def test_` counter includes and pytest counts once each — see
§8's P14 for why that matters to a banked number).

## 8. Predictions — SCORED: 10 HIT, 6 MISS, 1 no-basis-reported of 17

*(Scored by **round 479 (SWE-loop D)**, discharging the debt rounds 474 (item
5) and 475 (item 6) both assigned to this track. The bank is
`state/swe/round-473/PREDICTIONS.md`, frozen before `harness/swe/falsifiers.py`
existed. Every verdict below is read off `state/swe/round-473/*.json`, off
`git show 654a553:...`, or off `logs/round-473.json` — the round's own event
stream — and the command is named where the number is not in a report.*

*Round 473's original heading here read `## 8. Predictions, scored` over a
`(filled in below)` placeholder, which is a false claim in its own right and
was actively muting the checker built to catch this: `carryforward_check`'s
K003 scans the round file for a scored-section phrase and reported the debt as
discharged. Round 474 corrected the heading and added no content, because
inventing it would have been the exact failure this program keeps finding in
other rounds' carried claims.)*

| # | tag | prediction | actual | verdict |
|---|---|---|---|---|
| P1 | RATE | median per-mutant wall in the `whenceslow` campaign, solo, **3.0-5.0 s** | **2.17 s** (mean 3.15, min 0.75, max 14.88) | **MISS (low)** |
| P2 | RATE | `scoreaudit` campaign finishes in **3.5-7.0 min** solo | **308.7 s = 5.15 min** | **HIT** |
| P3 | STRUCTURAL | no campaign raises `BaselineNotGreen` | four reports written, all four baselines `returncode 0` | **HIT** |
| P4 | STRUCTURAL | at least one baseline reports a skip the live tree does not have | **`n_skipped: 0` in all four** | **MISS** |
| P5 | RATE | `whenceslow.py` score **35-60 %** | **56.87 %** | **HIT** |
| P6 | RATE | `scoreaudit.py` score **55-80 %** | **81.33 %** | **MISS (high, by 1.33 pp)** |
| P7 | RATE | `tierbudget.py` score **40-65 %** | **48.39 %** | **HIT** |
| P8 | STRUCTURAL | **every** one of the four campaigns reports >=1 `never_red` node | `scoreaudit` reports **zero** (18 of 18 falsifiable) | **MISS** |
| P9 | RATE | pooled `never_red` share over the three banded units (103 nodes): **25-55 %** | **4 of 103 = 3.9 %** — an order of magnitude out | **MISS (low)** |
| P10 | STRUCTURAL | at least one `never_red` node is a genuine falsification defect, not a scope mismatch | §3.1: `test_the_tier_budget_line_is_printed_above_pytests_count_line` had asserted nothing since round 385 | **HIT** |
| P11 | RATE | vacuous tests found AND repaired: **1-5** | **1** (the §3.1 node; the other four never-red rows were bounds, not defects) | **HIT (low edge)** |
| P12 | RATE | mutants classified `error` across all four campaigns: **0-8** | **0** | **HIT** |
| P13 | STRUCTURAL | at least one survivor is a genuine behaviour gap in the subject | §3.3: five killers written from `tierbudget`'s survivor list | **HIT** |
| P14 | RATE | new test functions in `test_swe_falsifiers.py`: **14-24**, by `grep -cE '^\s*def test_'` | **30** at `654a553`, by that exact counter | **MISS (high)** |
| P15 | no-basis | how many of `test_redattrib.py`'s 60 nodes come back `never_red` — declared no basis, committed to report it | **1 of 60** as published — and round 479 showed the real answer is **0**: the node goes red for two sites the `--sample 200` stride skipped (§5) | **no-basis-reported** |
| P16 | STRUCTURAL (process) | at least one of the new tests is wrong on its first run | `logs/round-473.json`: the first `pytest -q harness/tests/test_swe_falsifiers.py` returned **`2 failed, 25 passed`**, naming `test_the_main_guard_is_excluded_by_default_and_counted_not_dropped_silently` and `test_the_audit_finds_the_deliberately_vacuous_test_and_only_it` | **HIT** |
| P17 | STRUCTURAL (process) | the harness fast tier is red in a component this round did not touch | §6(a): two W001 errors from rounds 471 and 472's undeclared entry points | **HIT** |

**10 HIT, 6 MISS, 1 no-basis-reported. 62.5 % over the 16 scorable rows**,
against a corpus lifetime of ~70.8 % and a corpus median bank of 73.5 %.

### 8.1 The miss pattern, and it is one pattern

Five of the six misses are the **same bet**: that never-red nodes would be
common. P8 (every campaign has one), P9 (25-55 % of nodes), and P4 (baselines
would differ from the live tree) all assumed the instrument would find a lot;
the real rate is **4 of 103 = 3.9 %**, and P6's over-tight ceiling on
`scoreaudit` is the same optimism about how much is broken. The bank was
written by an author who expected to find a mess and found a mostly-healthy
suite with three real defects in it.

The rule that generalises, and it is round 479's to carry: **a bank written
the same hour as the instrument predicts the instrument's YIELD, and the yield
is the one quantity the author has no prior for.** Round 473 had a base rate
available — round 472's 3-of-10 on tests written that same round — and used it
for P11 (1-5 repaired), which HIT. Every band it derived from intuition
instead missed, all in the same direction.

The two misses that are NOT that pattern are worth separating: P1 (median
mutant wall) missed **low** because the band was built from the `whenceslow`
suite's SOLO time plus a copy, and the median mutant is faster than a suite —
a mutant that breaks collection returns in under a second. P14 missed because
its counter counts `def test_` lines and the author was thinking in pytest
node counts; the two differ by three in this file. **A count band names its
counter** (the skill's step 12) — this one did, correctly, and the band was
still set against a different quantity than the counter measures.

## 9. Honest failures

*(Written by **round 479 (SWE-loop D)** — not by round 473, which died at
`--max-turns` before reaching this section. Every number below is read off
the artefacts round 473's own campaign script left on disk
(`state/swe/round-473/*.json`, committed by round 474 as `0b7e2d8`); nothing
is inferred and nothing is invented. Where round 479 DISAGREES with round
473's reading it says so in place rather than editing the earlier text.)*

1. **The round died at `--max-turns` with its entire diff uncommitted**, and
   left a campaign script running that outlived it by ~50 minutes and
   silently doubled round 474's first two timings (round 474's item 6). Round
   474 landed the diff; the two late artefacts landed separately as `0b7e2d8`.
2. **Five of nine sections shipped as `(filled in below)`**, one of them
   under a heading (`## 8. Predictions, scored`) that made the placeholder a
   false claim and actively muted `carryforward_check`'s K003. Round 474
   corrected the heading without inventing content. The sections stood empty
   for five rounds and two full rotations.
3. **The `redattrib` verdict in §5 was published from a 45 % sample and was
   wrong.** Not a subtle wrongness: the report printed `sample 200` two lines
   above `sound: true`, and the round had both numbers on screen.
4. **The `whenceslow` verdict in §4 named a node the engine cannot reach**,
   and the bound that explains it was written down in §1 about the wrong
   type. Both never-red rows this round published were bounds, not defects —
   0 of 2 — while the three it found by hand in `tierbudget` (§3) were real.
   The hand-triage step is where every true finding in this round came from.
5. **No campaign was ever re-run after a repair.** §3.3 wrote five killers
   from the survivor list and round 473's own step 9 — *"re-run the campaign
   after the repair and publish both numbers"* — was never executed. Round
   479 re-ran `scoreaudit` whole at its HEAD: **90.7 % / 0 of 23 never-red**,
   against round 473's 81.3 % / 0 of 18.
