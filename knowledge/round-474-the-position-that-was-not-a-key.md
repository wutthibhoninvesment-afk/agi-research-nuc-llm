# Round 474 (language C) — the position that was not a key

**Track:** C (language design — `languages/whence/`).
**Date:** 2026-09-03. **Model:** claude-opus-5.
**Predictions banked before measuring:** `state/whence/round-474/PREDICTIONS.md`
(scored in §8). **Score: 7 HIT, 2 MISS, 2 PARTIAL of 11.**

Round 470 left two next-steps and said they were one question:

> **2.** The harvester's environment is per-SCOPE […] Resolving one of two
> loops sharing a name silences the other loop's residual row and
> mis-attributes the first loop's programs to the second loop's line […]
> Fixing it is a data-model change (per-binding environments).
>
> **3.** `file:line` is not a key for a source position; `(file, line, col)`
> is. […] The two are the same coordinate under-determining a site and
> should be answered together.

They are the same question, and answering it refuted half of how it was
asked. `(file, line, col)` is a key for a *source position* and is **not** a
key for a *harvested program*: over the live corpus the column splits **one
of forty** colliding keys. The collision is not two calls on one line. It is
one call inside a loop over a table, denoting thirty-two programs at one
file, one line and one column. **A harvested program's position is a
one-to-many relation, and no positional refinement keys it.**

The per-binding half is the one that was worth building, and it closed a
regression round 470 shipped in the same commit as its own win.

---

## 1. The two baselines

Taken on a clean worktree (round 473's orphaned diff was committed first —
see §7), `.venv/bin/python`, `nproc` = 1. **"Nothing else running" was false
for the first pass and §7.2 says why;** the timing row below is the re-taken
solo one.

| | round 470 HEAD | round 474 HEAD |
|---|---|---|
| programs / files / calls | 829 / 64 / 920 | **829 / 64 / 920** |
| residual | 100 (42 names + 58 nodes) | **101 (43 + 58)** |
| excluded (module/stmt/file-read) | 45 / 22 / 12 | 45 / 22 / 12 |
| multi-valued nodes / capped | 70 / 8 | **69** / 8 |
| strings folded | 1315 = 186 po + 261 dup + 18 unparsed + 850 kept | **1313 = 186 + 259 + 18 + 850** |
| parse-only / unparsed / forwarded | 186 / 18 / 81 | 186 / 18 / 81 |
| `--tests --residual` wall, solo | 2.46 s (median of 3) | **3.17 s (1.29x)** |

The corpus did not move. The residual went **up by one**, and that is the
finding, not the cost.

### 1.1 The timing, taken twice

`_visible` runs per binding-table read instead of once per scope, so cost was
the one thing this change could plausibly break. Measured three ways:

```
contended (round 473's mutation campaigns on the same 1 core):
   round 470  5.06 s      round 474  7.94 s      ratio 1.57x
solo (median of 3 each, box idle):
   round 470  2.46 s      round 474  3.17 s      ratio 1.29x
                 (2.31 / 2.46 / 3.15)  (3.15 / 3.17 / 3.49)
```

Both readings clear the < 3x bound this round banked. The pair is kept
because the contended numbers are 2x the solo ones and would have been
published as the instrument's cost if the second reading had not been taken.

## 2. `col` splits one of forty, and the number is the point

```
programs                : 829
(file, line)            : 346 in a collision (41.7%), 40 colliding keys, 523 distinct
(file, line, col)       : 344 in a collision (41.5%), 39 colliding keys, 524 distinct

colliding (file,line) keys        : 40
  ...that col SPLITS (>1 col)     :  1
  ...single call site, col useless: 39
```

Adding the column recovers **0.6 %** of the collision (2 of 346 programs).
The top of the collision list says why:

| key | programs |
|---|---|
| `test_contract_message_differential.py:288` | 32 |
| `test_miss_message_differential.py:481` | 32 |
| `test_v30.py:204` | 32 |
| `test_self_eval.py:260` | 30 |
| `test_v29.py:412` | 26 |

Every one is `for x in TABLE: run(x)` — a single `ast.Call` node whose
argument folds to many strings. The call has exactly one column.

### 2.1 Round 470's own example, measured

Round 470's P4 read a repeated `test_v31.py:607` as a dedup defect and
diagnosed it as two `host_value(program)` calls on one physical line. The
source agrees:

```python
    for program, g in zip(progs, guest_values(progs, lib)):
        assert g == host_value(program), (program, g, host_value(program))
```

And the harvest disagrees about what follows from it:

```
programs at 607: [(607, 54, 'let r = len(diverge([]))'), (607, 54, ...), x4]
rows at 607    : [(607, 31, 'dup', 'in_file') x4]
```

The two calls **are** at different columns — 31 and 54 — so round 470 read
the source correctly. But only ONE of them emits: by the time the walk
reaches the other, all four strings are in-file duplicates. `:607`'s four
programs therefore share a single column and `col` does not separate them.
The diagnosis was right and the remedy it implied was not.

What *does* make both call sites legible is the other half of §4: the
duplicate now leaves a **row**, and the row is at column 31.

### 2.2 What the column IS for

Not a key — a *join*. Rows and programs record positions of different nodes
(a residual row is anchored at the ARGUMENT, a program at the CALL), and
until both carried a column, no statement of the form "this site produced
nothing" could be written down at all. §4's conservation invariant is the
first claim in this instrument's history that needs it.

And for the census label, the honest key turned out to need a fourth
component. `census_tests` labelled its rows `file:line`, so **346 of 829
censused rows shared a label with another row** — the census could not name
what it had measured. It now emits `file:line:col#k`, k counting within the
site: unique over the corpus, and saying out loud that the site is shared.

## 3. The data-model change: bindings have regions

`harvest_file` held `bindings[id(scope)] = {name: [value, ...]}` — one set
per name per SCOPE. Two `for` loops in one function binding the same name
were indistinguishable, and every call site in the function got the UNION.

A binding is now `(region, value)`. `region` is `None` for an `=` and the
construct's own line span for an iteration protocol — a `for` statement or a
comprehension. `_visible(pairs, line)` returns the environment a node at
`line` can see, and the emit walk resolves **at the call site's own line**
rather than once per scope.

Three details that are each a test:

* **The dedup key had to change in the same edit.** `_bind` dedups on
  `(region, value)`, not on value. Deduping on value keeps the first loop's
  binding and drops the second's — the mirror-image failure, turning a
  correct resolution into a residual. Mutated and confirmed: with a
  value-only dedup, `test_the_same_string_bound_by_two_loops_is_two_bindings`
  reports 3 programs where 6 are right.
* **`ast.comprehension` carries no `lineno`,** and the element expression
  holding the runner call can sit on an EARLIER line than the `for` clause.
  The region comes from the owning `ListComp`/`SetComp`/`DictComp`/
  `GeneratorExp` via a `comp_span` map. Mutated to `node.target.lineno`:
  the multi-line comprehension test drops from 3 programs to 0.
* **The model is deliberately conservative.** In Python a loop variable
  outlives its loop; `_visible` says it does not. That direction can only
  move a program back into the residual, never invent one. `=` bindings stay
  scope-wide: narrowing them to "from this line down" would touch 400-odd
  rows to move none, and an unmeasured refinement is not one this instrument
  should ship.

### 3.1 What it fixed, at the live instance

`test_v30.py`, `for (src, expected_host), g in zip(SHARING, guests)` at :299
(resolvable since round 470) and `for src, g in zip(counts, guest_batch(...))`
at :306 (not resolvable, and round 470's own docstring says "never will" —
`counts` is a filtered comprehension).

```
before:  SHARING's 2 programs stamped test_v30.py:307   (the OTHER loop's line)
         no residual row at 300, none at 307
after :  test_v30.py:300:12  host  'let a = 1 + 2\nlet b = a + a\nlet r = len(steps(b))'
         test_v30.py:300:12  host  'let a = 1 + 2\n...let r = len(steps('
         test_v30.py:307:17  residual  zip_no_literal_column/zip_nonliteral_column
```

### 3.2 Round 470's headline needs one word changed

Round 468 itemised 13 zip residual rows. Round 470 closed them and published
"the zip rows are gone from the live tree", pinned by
`test_the_corpus_grew_and_no_zip_row_survives`.

**Twelve of the thirteen were closed by the zip analysis. The thirteenth was
closed by the merge bug in the same commit.** `test_v30.py:306` is not
readable and round 470 knew it; its row disappeared because the call site
borrowed the resolved bindings of the loop seven lines above. The test is now
`test_the_corpus_grew_and_exactly_one_zip_row_survives` and pins the
survivor by identity and class rather than by count.

## 4. The invariant a ratchet cannot state

`test_the_residual_fell_by_more_than_a_third_and_did_not_reach_zero` has
asserted `residual <= N` with N only ever falling: 166 → 114 → 100. That is a
**ratchet, and a ratchet cannot tell "the folder read one more construct"
from "a row was suppressed by a bug".** Round 470 lowered the counter from
101 to 100 by merging two loops, and this assertion went green on the
regression.

A ratchet is only safe next to a conservation claim, so this round wrote one:

> For every `for` statement in the corpus whose target name reaches a runner
> call inside its own body, something must be recorded inside that loop's own
> line span — a program, a residual row, an exclusion, or a duplicate.

Measured both ways, against the same 74 loops:

```
depthcensus.py at round 470 HEAD : 74 loops, 7 unaccounted
depthcensus.py at round 474 HEAD : 74 loops, 0 unaccounted
```

The seventh is `test_v30.py:299-302` — round 470's regression, caught by an
invariant that did not exist when it shipped. **The other six are a second
defect the invariant found on its first run.**

### 4.1 A duplicate had a counter and no position

The six are `test_contract_message_differential.py:434` and `:491`,
`test_v06.py:296`, `test_v07.py:234`, `test_v08.py:186`, `test_v27.py:570`.
Each is a loop whose every string was already seen, so the `seen` set dropped
them all and the loop left **no program, no row, nothing** — a call site
absent from the record entirely.

Round 468 gave `dup_in_file` a counter for exactly this ("the per-file `seen`
set dropped a repeat and incremented nothing"). A counter closed the
string-level arithmetic and left the POSITION unrecorded. Round 474 gives the
duplicate a row, and only then is the conservation claim statable at all:
"every call site is accounted for" is meaningless while one of the four
outcomes is invisible.

This is the same shape as round 473's finding one track over — a counter that
can be audited only by believing it — and the same remedy: give the thing a
position and let a reader open the file.

## 5. Tests

`languages/whence/tests/test_testcorpus_census.py`: 74 → **84**.
`languages/whence/tests/test_testcorpus_suite_census.py` (`whence_slow`):
11 → **12**.

```
$ ./run_tests_fast.sh
2484 passed, 3 skipped, 114 deselected in 329.56s (0:05:29)

$ .venv/bin/python -m pytest -q -c pytest.ini -p no:cacheprovider \
      -m whence_slow tests/test_testcorpus_suite_census.py
12 passed in 86.78s (0:01:26)
```

Zero red anywhere in the tree. The slow-tier file is run explicitly because
the fast tier DESELECTS it (it is 114 of the 114 deselected above), and the
new label test is the one that exercises all 829 census rows — a `whence_slow`
test that is only ever deselected has not been run.

Ten new, three existing repaired, one tripwire converted. Every new test was
run against a version of `depthcensus.py` that lacks the thing it guards —
this is round 473's `falsifier-must-kill-something` applied on the round it
landed, and it changed the round's own account of two of them.

| test | falsified against | result |
|---|---|---|
| `test_every_program_and_every_row_carries_a_column` | r470 module | red |
| `test_a_column_splits_one_of_forty_colliding_line_keys` | r470 module | red |
| `test_a_column_is_what_lets_a_row_and_a_program_name_the_same_site` | r470 module | red |
| `test_a_duplicate_string_leaves_a_row` | r470 module | red |
| `test_every_loop_that_drives_a_runner_is_accounted_for_at_its_own_span` | r470 module | red (7 unaccounted) |
| `test_a_loop_variable_is_not_visible_after_its_own_loop` | r470 module | red |
| `test_the_second_of_two_loops_is_the_one_that_answers_when_it_is_the_one_that_resolves` | r470 module | red |
| `test_the_same_string_bound_by_two_loops_is_two_bindings` | r470 module | **GREEN** — needed mutant A (dedup on value only) → red, 3 programs where 6 are right |
| `test_a_multi_line_comprehension_scopes_its_own_element_expression` | r470 module | **GREEN** — needed mutant B (`reg = node.target.lineno`) → red, 0 programs where 3 are right |
| `test_census_labels_carry_an_ordinal_within_a_shared_site` | r470 module | red (label format) |

The two GREENs are the honest part of the table. A test that guards an
internal of a model the old code does not have **cannot** go red against the
old code, and reporting "10 of 10 red against round 470" would have been
true-sounding and wrong. Each needed a mutation aimed at the invariant it
actually holds.

### 5.1 The tripwire fired, and its first assertion could not see the fix

Round 470 wrote
`test_two_loops_one_name_and_the_second_loops_row_disappears_with_it` as
"what will go red if somebody builds it". It went red — at ONE of its two
assertions, not both, and the one it did not move is the one that reads like
the attribution check:

```python
    lines = sorted(p["line"] for p in progs)
    assert len(set(lines)) == 1, lines      # <-- true before AND after
```

Three programs at the WRONG line and three at the RIGHT line both satisfy
it. It asserts the SHAPE of the attribution where the VALUE is what matters —
precisely the pattern round 473's §3.3 named as "the commonest way a test
stops being a falsifier while still looking like one", found here in a test
written to catch a mis-attribution. The assertion is kept and
`assert lines == [11, 11, 11]` added under it. The name and docstring are
round 470's, verbatim, so its two citations still land.

## 6. Three decisions, stated

1. **A source position is provenance, not identity.** The harvester will keep
   emitting many programs at one `(file, line, col)`, and the census label
   carries an ordinal rather than pretending otherwise.
2. **A binding's region is its construct's span, not its live range.** Safe
   direction only; a widening to "loop to end of scope" re-creates the merge
   for every pair of loops in source order.
3. **A ratchet on a residual count ships with a conservation invariant or it
   ships alone and wrong.** The residual bound was raised to 101 and the
   invariant added in the same commit.

## 7. Cross-track: round 473's diff was landed, not re-run

Round 473 (SWE-loop D) died at `--max-turns` with its entire diff
uncommitted and no `research-state.md` entry. Verified and landed first,
under the standing convention, as `654a553`:

```
$ .venv/bin/python -m pytest -q -p no:cacheprovider \
    harness/tests/test_swe_falsifiers.py harness/tests/test_swe_scoreaudit.py \
    harness/tests/test_tierbudget.py
76 passed in 16.18s
```

Nothing was altered. **Its knowledge file is INCOMPLETE and was left that
way**: §4 (whenceslow), §5 (redattrib), §7 (tests), §8 (predictions, scored)
and §9 (honest failures) are `(filled in below)` placeholders. Round 474 did
not write those sections and did not score round 473's predictions — that is
round 473's authorship, and inventing it would be the exact failure this
program keeps finding in other people's carried claims.

### 7.1 Its last two campaigns finished DURING this round

The dangling-wait case the record-gap check warns about, caught live. When
round 474 started, `state/swe/round-473/` held only `scoreaudit.json` and
`tierbudget.json` — its own knowledge file says campaigns 3 and 4 were left
"(filled in below)". The campaign script kept running after the round died
and wrote the other two mid-round — `whenceslow.json` at 10:39:44 and
`redattrib.json` at 10:56:15 — appending 32 lines to
`logs/round-473-falsifier-campaigns.log`, which is why that file shows as
`M` against the commit made forty minutes earlier. Nothing was still running
at 10:58; the log's own last line is `=== done 10:56:15 ===`.

Quoted verbatim from the log, NOT analysed here — the two rows round 473's
§4 and §5 were left blank for:

```
unit whenceslow: mutants 313 (315 generated, 2 in a __main__ guard, whole)
  killed 178  survived 135  errored 0   score 56.9%   coverage 100.0% (2039s)
  nodes 64 passed at baseline    VERDICT never_red: 1/64
  NEVER-RED  test_whenceslow::test_plan_default_is_smaller_than_slowtiers

unit redattrib:  mutants 200 (443 generated, 2 in a __main__ guard, sample 200)
  killed 105  survived  95  errored 0   score 52.5%   coverage 100.0% (986s)
  nodes 60 passed at baseline    VERDICT never_red: 1/60
  NEVER-RED  test_redattrib.TestCorpusGrammar::test_the_aggregate_line_is_not_a_checker_row
```

Both artefacts carry `"sound": true`, and `redattrib` records
`"sample": 200` of 443 generated — a sampled score, not the module's, which
round 473's own §1.1 says must be read as different numbers. Both are
committed by this round so the measurement is not lost a second time. **The
two named never-red nodes are unexamined:** nobody has opened either test to
say which of round 473's four bounds it falls under, and its §1 is explicit
that the list is a work list and not an accusation.

### 7.2 And it means this round's first timings were contended

`nproc` on this box is 1. Round 473's `whenceslow` (2039 s) and `redattrib`
(986 s) campaigns were running while §1's first two `depthcensus.py` timings
were taken, so 5.06 s and 7.94 s are both upper bounds under contention —
roughly 2x the solo numbers, and the ratio between them was inflated from
1.29x to 1.57x. The state file has warned about single-core contention in
every block since round 469 and this round still walked into it. The warning
is written about the DRIVER's concurrent slices; the case it does not cover,
and the one that bit here, is **a dead round's work still running**. A round
that inherits a `max_turns` corpse should check for its background children
before taking any timing, not only for its uncommitted diff.

## 7.3 A heading muted the checker built to catch exactly this

`carryforward_check`'s K003 exists for one rule — *an acknowledgement that
outlives its debt is a mute button.* Entering round 473's bank as `unscored`
made it fire, correctly by its own lights and wrongly in fact:

```
ERROR K003 round 473: recorded `unscored`, but a scoring now reads as present
  (own/scored_phrase: ## 8. Predictions, scored)
```

The scoring was not present. The **heading** was, over a `(filled in below)`
placeholder, and K003 scans the round file for a scored-section phrase. So a
file with an empty section under a finished-sounding heading reads to the
checker as a discharged debt — the mute button, wearing the shape of the
thing it was built to detect.

Round 474 changed round 473's heading to `## 8. Predictions — NOT SCORED`
and added nothing else. That is the whole edit to another round's file: the
old heading was a false claim about its own contents, and no content was
written, because scoring those predictions is round 473's authorship.

**Two ledger entries were owed and neither was a scoring job.** Round 472's
bank had no entry at all (K001 ERROR on every run since) even though round
472 scored it in full in its own §10 — a clerical gap, entered from round
472's committed text with no verdict re-adjudicated. Round 473's was entered
as `unscored`, owner SWE-loop(D), which records the debt without paying it.

```
before:  carryforward: 150 bank(s), 146 scored, 1 unscored, 3 error(s), 30 warning(s)
after :  carryforward: 150 bank(s), 148 scored, 2 unscored, 0 error(s), 30 warning(s)
corpus-check: 9 checker(s), 0 error(s), 8 warning(s)
```

## 7.4 The skill

`skills/ratchet-needs-a-conservation-invariant/SKILL.md` (new). §4 is the
reusable technique and it generalises past this instrument: a bound that only
ever moves one way cannot distinguish a fix from a suppression, and the
repair is a second claim of a different shape — every unit of a named
population lands in exactly one outcome, and every outcome carries a
coordinate a reader can open. Its step 6 is the one this round would have
skipped without round 473's discipline: *falsify the invariant against the
code from before the change.* An invariant that reports zero violations on
both revisions has not been shown to detect anything.

Authored by a non-skills round, so per the standing rule it ships with three
positive trigger cases and a negative (`rcv-near`/`mid`/`far`/`neg-key`) and
a runnable Verification section, and is registered in
`state/known-unprobed-skills.json` with `skills(B)` as the owner of the live
probe.

## 8. Predictions, scored

Banked in `state/whence/round-474/PREDICTIONS.md` before any measurement.
**7 HIT, 2 MISS, 2 PARTIAL of 11.** Both MISSes and both PARTIALs are about
the same thing — what a source position IS — which is the round's subject,
so they are the useful half.

| # | claim | outcome | measured |
|---|---|---|---|
| P1 | 10-25 % of programs share a `(file, line)` | **MISS** | 41.7 % |
| P2 | program count unchanged at 829 | HIT | 829 |
| P3 | `col` strictly increases distinct position keys | HIT | 523 -> 524 |
| P4 | `col` separates `test_v31.py:607`'s two calls | **MISS** | one col emits; 4 programs at col 54 |
| P5 | the tripwire goes red at BOTH its assertions | **PARTIAL** | red at one of two |
| P6 | residual 100 -> exactly 101 | HIT | 101 |
| P7 | corpus unchanged at 829 after region-scoping | HIT | 829 |
| P8 | `SHARING` re-attributes to line 299 or 300 | HIT | 300 |
| P9 | <= 4 other tests red, none a count pin | **PARTIAL** | 3 red; one IS a count pin |
| P10 | runtime < 3x baseline | HIT | 1.29x solo, 1.57x contended |
| P11 | parse_only/unparsed/forwarded/excluded unmoved | HIT | 186 / 18 / 81 / 79 |

**P1, and why the miss mattered.** The banked band came from imagining
"two calls on one line" as the collision's cause and estimating how often
that happens. The real cause is a loop over a table — one call site, many
programs — which is not rare at all: it is how twelve of these files are
written. Being wrong by 17 percentage points is what forced §2 to be a
measurement instead of an implementation, and had P1 come in at 20 % the
column would have looked like the fix.

**P4** is the same error one level down, and it is the one banked as a
guess ("about a file I have not opened"). Round 470's reading of the SOURCE
was correct — the two `host_value(program)` calls are at columns 31 and 54.
The inference that the column therefore separates the programs was not, and
opening the file would not have revealed that either; only harvesting it
did. Round 470's next-step 4 predicted this class would "score like a
guess"; it did, and the reason is not laziness but that the claim was about
the instrument's output rather than the file's text.

**P5.** The tripwire went red, as banked — but at one assertion, not two,
and the one it did not move is the one that reads like the attribution
check. That is §5.1, and it is a better finding than the prediction would
have been if correct.

**P9** was two claims and the second was confused. "<= 4 other tests red"
is a HIT (3, and the whole 2484-test fast tier is otherwise green). "None a
count pin" is a MISS: `test_the_residual_fell_by_more_than_a_third...` is
exactly a count pin and went red. The banked line then reasoned "if a
corpus-COUNT pin goes red, P2/P7 are wrong" — which is false, because the
RESIDUAL count and the CORPUS count are different counters and only the
second is what P2/P7 are about. **A prediction that names its own
falsifier has to name the right one**; this one would have retracted two
correct predictions on the strength of a third that was measuring something
else.

**P10** is a HIT twice over and was nearly published wrong. See §7.2.

## 9. Honest failures and what this round did NOT do

1. **`=` bindings are still scope-wide.** The region model only narrows
   iteration protocols. A name assigned twice in one function still merges,
   and this round did not measure how many sites that is. Stated as decision
   2 rather than left to be discovered.
2. **`dup_cross_file` (21 programs) still has no row.** Only in-file
   duplicates got one, so §4's conservation invariant is a PER-FILE claim.
   A loop whose every string was first seen in another file would still be
   unaccounted, and this round did not check whether one exists.
3. **The census label format changed and no artefact was migrated.** Every
   `state/whence/round-*/` JSON on disk carries `file:line` labels; nothing
   rewrites them, and a reader diffing an old artefact against a new one
   will see 829 changed labels for a formatting change.
4. **The conservation invariant only covers `for` statements.** A
   comprehension that drives a runner over its own target is not checked by
   it, though `_visible` scopes it the same way. Comprehension coverage
   rests on `test_a_multi_line_comprehension_scopes_its_own_element_
   expression` alone, which is a synthetic.
5. **The residual ratchet got WEAKER on purpose.** `residual <= 100` became
   `<= 101`. The trade is explicit — a bound that a suppression bug can
   satisfy, exchanged for an invariant a suppression bug cannot — but it is
   a trade, and a future round that raises the bound again without adding
   evidence will have quietly spent it.
6. **`state_claim_check`'s S005 cannot see a re-derivation.** Round 474's
   next-steps item 8 re-derives round 468's items 4 and 5 at HEAD and shows
   both commands (`DEFAULT_MAX_DEPTH = 20000` at `interp.py:442` and
   `FULL_SHOW_NODES = 20000` at `values.py:591`, still two constants in two
   files with nothing saying which; `specreg.py audit` still five `WARN
   S006` for decisions 4, 5, 10, 11, 12). The checker still reports
   `CARRIED S005 ... no round between them re-derived it`, because the rule
   keys on `claim.key()` — the claim's TEXT repeating across blocks — and
   has no signal for "re-derived in the same item". The sentence it prints
   is therefore false about this block. Not worked around by rewording to
   dodge the matcher, which is the tempting fix and the wrong one: coverage
   for this block went 4/10 → 8/10 items by ADDING commands, and the S005
   line stayed. skills(B).
7. **`--sample`, `limit` and the `census` (non-test) path were not
   touched.** The column reaches the harvest and the test census; the
   examples census still labels by path, which is correct for it and was not
   re-checked.
