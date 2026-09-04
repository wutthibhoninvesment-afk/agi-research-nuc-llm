# Round 485 (SWE-loop D) — the cost that was a property of one implementation

**Track:** SWE-loop(D) — the harness used on our own code.
**Subject:** one sentence round 479 wrote, and the bound it left unrepaired.

---

## 0. The sentence

Round 479 classified `test_plan_default_is_smaller_than_slowtiers` as
UNREACHABLE rather than vacuous — its only dependence on `harness/whenceslow.py`
is the float literal `120.0`, and `mutation._sites` emitted a `const` site for
`bool` and for `int` and for nothing else. It then declined the obvious repair
(`knowledge/round-473-...md` §4, round 479's own text):

> The obvious repair is a float operator (`f -> f + 1.0`), which would make
> this node reachable and would add 2/9/11/10 sites to the four subjects here.
> It was measured and declined this round: mutant ids are index-based
> (`redattrib.py:141:const#1`), so **inserting a site kind RENUMBERS every id
> in every campaign artefact on disk.** That is exactly the un-migrated-label
> defect round 474's own item 4 names. It is priced in round 479's next steps
> as a decision, not taken as a side effect.

The premise is correct: the id **is** positional. The conclusion does not
follow, and the whole round is the difference.

## 1. What the id actually is

`harness/swe/mutation.py:139`, unchanged since the module was written:

```python
mid = "%s:%d:%s#%d" % (os.path.basename(rel_path), node.lineno, op, i)
```

`i` is `enumerate(_sites(tree))` — **one counter over the whole file**, not a
per-kind ordinal, and the order is `ast.walk`'s, which is **breadth-first**,
not source order. That is why `redattrib.py:297:ifneg#4` and
`redattrib.py:297:not#32` are the same source line thirty indices apart: the
`If` node is shallow and the `not` inside its test is two levels down.
(Banked blind as P3, and half wrong: the counter is global, but the ordering
is BFS, not the kind-block structure the bank inferred from those six ids.)

`generate`'s `ops=` filter runs **after** `enumerate`, so a filtered campaign's
ids already name the same sites as an unfiltered one. That was load-bearing and
undocumented; it is now pinned.

## 2. The measurement round 479 did not take

Two implementations, four subjects, one command
(`state/swe/round-485/id-renumbering.json`):

| subject | legacy sites | float sites | naive: legacy ids kept | appended: legacy ids kept |
|---|---|---|---|---|
| `harness/whenceslow.py` | 315 | 11 | 55 / 315 = **17.5 %** | 315 / 315 = **100 %** |
| `harness/redattrib.py` | 443 | 10 | 137 / 443 = **30.9 %** | 443 / 443 = **100 %** |
| `harness/swe/scoreaudit.py` | 77 | 2 | 40 / 77 = **51.9 %** | 77 / 77 = **100 %** |
| `harness/tierbudget.py` | 95 | 9 | **1 / 95 = 1.1 %** | 95 / 95 = **100 %** |

*naive* = a `float` case folded into `_sites`' `elif isinstance(n, ast.Constant)`
branch, interleaved with the walk. *appended* = the same operator yielded from a
SECOND walk that runs once `_sites` is exhausted.

`tierbudget.py` is the extreme and it is instructive: its first float
(`DEFAULT_CAP_S = 25.0`, line 81) sits above almost every other site, so a
naive insertion shifts 94 of 95 ids. `scoreaudit.py`'s two floats sit late and
it keeps half. **The naive cost is a function of where the first new site
happens to sit** — which is exactly why it should not have been reasoned about
instead of measured.

The appended list is not merely the same set; it is a strict prefix-extension:
`ids_after[:315] == ids_before` on every subject. Nothing moved.

**So round 479 priced the repair against the wrong implementation.** That is
not a criticism of declining on an unmeasured cost — it is the reason the next
round measured it, and the measurement is four seconds of work.

### 2.1 And the corpus was already decaying, from a different cause

The obvious follow-up question is what the committed corpus is worth.
`state/swe/round-485/corpus-id-resolution.json`: of the **5 740** distinct
mutant ids in `state/swe/*/*.json` (excluding this round's own artefacts —
see §7.1), **3 626 = 63.2 % no longer name a site the engine generates at
HEAD.**

| subject basename | ids in artefacts | unresolvable | lost |
|---|---|---|---|
| `interp.py` | 4 743 | 3 465 | **73.1 %** |
| `values.py` | 83 | 82 | 98.8 % |
| `falsifiers.py` | 82 | 79 | 96.3 % |
| `whenceslow.py` | 313 | 0 | 0 % |
| `redattrib.py` | 204 | 0 | 0 % |
| `tierbudget.py` | 93 | 0 | 0 % |
| `scoreaudit.py` | 75 | 0 | 0 % |
| `lexer.py` / `parser.py` | 147 | 0 | 0 % |

Read that carefully in both directions. The decay is real and large, and it is
**entirely a source-edit effect**: `interp.py` is the Whence interpreter, which
a language(C) round edits every other round, and `falsifiers.py`'s 96 % is
*this round's own edit to falsifiers.py*, four hours old. The four subjects
this round is about have not moved and lost nothing.

This reframes the decision rather than settling it. A positional id decays
whenever its subject is edited; the operator set is one more way to move it,
and the only one that would have moved ids in files nobody touched. Appending
costs zero and removes that one way. A content-addressed id (`path:line:op#`
ordinal *within the same line and kind*) would additionally survive edits
elsewhere in the file — and would rewrite all 5 740 existing ids to buy it.
Round 485 did not take that trade and says so; the measurement above is what a
future round should decide it on.

## 3. `--ops` was bound 4's fourth knob, and it was the one the flag could not see

Round 479's bound 4 says a narrowed campaign cannot support a `never_red`
claim, and it enforced that by folding `site_coverage` into
`FalsifierReport.sound`. `site_coverage` is computed from the `selection` dict
that `select_sites` builds — and `--ops` never reached `select_sites`:

```python
mutants.extend(mutation.generate(src, rel, ops=ops))   # <- narrowed HERE
...
mutants, selection = select_sites(mutants, funcs=..., sample=..., limit=...)
#                                  ^ `sel["generated"] = len(mutants)`: the POST-filter list
```

So an `--ops fconst` campaign over `whenceslow.py` would have reported
`generated: 11`, `selected: 11`, `site_coverage: 1.0`, **`sound: true`**, and a
`never_red` list of 60-odd nodes — from 11 of 326 sites. Bound 4's exact
failure, through the one door bound 4 did not cover.

**And this round's own planned measurement was about to walk through it.** The
float-only campaign in §5 is an `--ops` campaign. The defect was found by
reading `select_sites` while preparing to run it, not by a test.

The fix is not a fourth special case, it is the removal of one: every narrowing
now happens in `select_sites`, against one `generated`. `audit` generates the
whole site list and passes `ops` along with `funcs`/`sample`/`limit`. The cost
is unparsing sites that are then dropped — ~1 ms each against a mutant run
measured in seconds. The report now says:

```
mutants 11 (326 generated, 2 in a __main__ guard, ops fconst)
VERDICT unsound: 60/67 node(s) never went red
!! NOT SOUND -- only 11 of 324 eligible site(s) were run (3%; ops=fconst).
   The list below is an UPPER BOUND on the never-red set, not the set.
```

**The rule that generalises, and it is the same one round 479 wrote one knob
too early:** a soundness flag is trusted precisely because nobody re-derives
it, so a knob that narrows the campaign *anywhere else in the codebase* is a
bound nobody applies. The question to ask of any such flag is not "is the
bound in it" but "**can the flag see every way the thing it bounds can be
narrowed**". Round 479 asked the first and shipped; the second one had a
counterexample already in the CLI.

## 4. Round 479's bound-5 pin could not go red for the event it names

Round 479 wrote a guard for exactly the change round 485 made:

```python
def_line = 1 + src[:src.index("\ndef plan(")].count("\n")
sites = [m for m in generate(src, "harness/whenceslow.py")
         if m.lineno <= def_line <= m.end_lineno]
assert sites == [], \
    "a site now covers `def plan`; the node may have become reachable"
```

`src.index("\ndef plan(")` is the offset of the newline **before** the `def`,
so the prefix holds one fewer newline than there are lines above it. It answers
**624** for a `def` on **625**. When round 485 put a site on 625, the guard
passed. The test went red on its *next* line — `unreachable_constants(...)
.get("float", 0) >= 1`, which stopped being true for an unrelated reason — and
that is the only reason anybody looked at it.

A guard that cannot go red for the event it names is this program's own
`named-guardian-must-go-red` failure, inside a test written to enforce
`falsifier-must-kill-something`. It is pinned as its own node now
(`test_round_479s_def_plan_locator_was_off_by_one`), asserting the off-by-one
rather than quietly correcting it, because the *shape* is the finding: an
off-by-one in a LOCATOR is invisible while the thing being located is absent,
and absence is what the assertion is about.

## 5. What the widened operator set actually bought

`fconst` (`f -> f + 1.0`) on the two subjects whose never-red rows were still
open. Both campaigns solo on a 1-CPU box, `--ops fconst`, whole test file:

| subject | float mutants | killed BEFORE | score BEFORE | killed AFTER | score AFTER | wall |
|---|---|---|---|---|---|---|
| `harness/whenceslow.py` | 11 | 3 | **27.3 %** | 6 | **54.5 %** | 33 s / 33 s |
| `harness/tierbudget.py` | 9 | 0 | **0.0 %** | 4 | **44.4 %** | 79 s / 74 s |

Artefacts: `state/swe/round-485/{whenceslow,tierbudget}-fconst{,-after}.json`.

**This is round 473's step 9 executed for the first time in this program** —
*"re-run the campaign after the repair and publish both numbers"* — which
round 473 wrote, never ran, and round 479 listed as honest failure 5.

### 5.1 The one node the widening reclassified

```
whenceslow.py:625:fconst#315   120.0 -> 121.0   killed
  red: harness.tests.test_whenceslow::test_plan_default_is_smaller_than_slowtiers
```

Round 473 published it `never_red`. Round 479 classified it *unreachable*.
Round 485 killed it without changing one character of the test. That is the
whole difference between reporting a bound and discharging one.

### 5.2 And exactly one node, out of two subjects

`tierbudget.py`'s three round-473 never-red rows are **still never-red** under
`fconst`: 0 of its 9 float mutants killed anything before this round's killers,
and none of the three rows is among the four killers afterwards. So the answer
to this round's banked no-basis line P13 — *does any other never-red node
become reachable* — is **no, zero, over the one other subject that had rows
open**. Widening an operator set is not a general remedy for absence; it
reclassified one node and produced a work list.

### 5.3 The work list is where the value was

The 20 float mutants surfaced 17 survivors nothing in either suite could see.
Four had a real decision behind them and are killed by this round's tests:

1. **`whenceslow.replay(..., default_s=120.0)` (line 780) is a SECOND copy of
   the 120 s default and nothing pinned it.** Round 469 pinned `plan`'s, with a
   docstring arguing the 120-vs-300 choice from the tier's recorded 5.4-7.3 s
   per marked test. `replay` is the function that *prices* a budget before
   anyone spends it, so an unpinned default there moves every published recall
   number silently. Killer asserts the two are EQUAL rather than re-typing the
   literal: they are two readings of one decision.
2. **`_size_prior`'s `/ 1e6`.** Its docstring says "scaled to a fraction of a
   second" and the justification for using it as a tie-break is that it cannot
   outweigh a measurement. Nothing tested the scale. At `1e3` a 200 kB test
   file prices at 200 s and the tie-break becomes the planner.
3. **`tierbudget`'s three registry defaults** (`DEFAULT_CAP_S = 25.0`,
   `DEFAULT_DRIFT_FACTOR = 2.0`, `DEFAULT_DRIFT_FLOOR_S = 3.0`). The live
   registry sets all three, so every test that reads it reads the FILE's
   numbers; the module's constants are the fallback for a registry that omits a
   key, and nothing exercised it. Both of `load_registry`'s fallback returns are
   now covered — one test per exit, because a test covering one would have left
   the other unguarded, which is how three float constants survived to round 485.
4. **`tierbudget`'s `max(r["budget_s"], 1e-9)` divisor guard.** It exists to
   stop a zero budget dividing by zero; nothing pinned how *small* it has to
   be. `f -> f + 1.0` turns it into a ~1.0 FLOOR that rewrites the ratio of
   every sub-second budget, and the "worst BY RATIO" line then names the wrong
   file. Killed with a two-row fixture where the sub-second row is worst by
   ratio and neither row has drifted (the DRIFT branch returns first, which
   the killer's first version did not survive — see §7).

The five remaining `whenceslow` and five remaining `tierbudget` float
survivors are mostly `0.0` initialisers and fallbacks; they are left on the
list rather than killed for the sake of the number.

## 6. What shipped

| path | change |
|---|---|
| `harness/swe/mutation.py` | `_sites` declared FROZEN; `_docstring_ids` factored out; `_late_sites` + `_all_sites`; `fconst`; `LEGACY_OPS`, `LATE_OPS`, `MUTABLE_CONSTANT_TYPES`; a `THE ID SCHEME IS FROZEN` section carrying §2's table |
| `harness/swe/falsifiers.py` | `ops` moved into `select_sites` and folded into `site_coverage`/`sound`/`unsound_reasons`/`_selection_phrase`; `UNMUTABLE_KINDS` derived from `mutation.MUTABLE_CONSTANT_TYPES`; `unreachable_constants` calls `mutation._docstring_ids` instead of re-implementing it |
| `harness/tests/test_swe_mutation.py` | +9 nodes (24 → 33): the freeze, the counterfactual, the content pins, the two operator sets, the `ops`-filter invariant |
| `harness/tests/test_swe_falsifiers.py` | +7 nodes (51 → 58): the four `ops` narrowing pins, the derived-`UNMUTABLE_KINDS` pin, the off-by-one, and the bound-5 node inverted |
| `harness/tests/test_whenceslow.py` | +3 killers; the slow-tier membership pin re-pinned 28→29 units / 114→115 marked |
| `harness/tests/test_tierbudget.py` | +3 killers |
| `harness/tier-budget.json` | `test_swe_mutation.py` re-measured SOLO: 18.17 s → **20.63 s**, under the 25 s cap, green, promotion stands |
| `state/swe/round-485/` | `id-renumbering.json`, `legacy-id-pins.json`, `corpus-id-resolution.json`, four campaign reports, `PREDICTIONS.md` |

### 6.1 The pin that makes the freeze enforceable

`state/swe/round-485/legacy-id-pins.json` holds, per subject, the sha256 of
the newline-joined legacy id list, **keyed by the sha256 of the subject's own
source**. `test_the_legacy_id_digest_of_every_pinned_subject_still_matches`
skips a subject whose source digest has moved (an id list is *allowed* to
change when the source changes) and fails when the source is unchanged and the
id list is not — which is precisely a renumbering. Six subjects are pinned; the
test also refuses to be silently vacuous if every pin expires at once.

A convention that lives only in a docstring is a convention the next author
does not know about. This one goes red.

## 7. Honest failures

1. **The first fast-tier run of the round measured a tree that changed under
   it.** It was launched "first, before touching anything" and then
   `mutation.py` and `falsifiers.py` were edited while it ran, so its 8
   failures cannot be attributed. A pristine baseline at `6037bb7`
   (`pristine_check.py baseline --suite harness-fast`) was taken afterwards and
   is the number §8's P11 is scored against. The rule already exists in this
   repo's own memory and the round broke it anyway, in its first minute.

   A second, smaller one rides on that row. `pristine_check`'s ledger entry
   records `"counts": {"error": 5, "failed": 5, ...}` for a run whose own
   pytest line reads `5 failed, 1506 passed, 21 skipped, 412 deselected` and
   names no errors at all. This round quoted the `counts` dict into §8 before
   reading the tail, and corrected it from the pytest line. Nobody should quote
   that row's `error` field until somebody audits the counter behind it;
   harness(A).
2. **Two tests were wrong on their first run** (P10, banked). The first
   asserted `'"""docstring"""' in m.source` when `ast.unparse` re-quotes to
   `'docstring'` — an assertion about spelling where the claim was survival.
   The second put the `worst BY RATIO` fixture in DRIFT, and
   `format_verify_line` returns the drift branch before it ever computes
   `worst`.
3. **A `pkill -f` matched this session's own shell** and killed the chained
   command with exit 144 — the exact failure this box's memory records. PIDs
   were resolved first thereafter.
4. **A `cd languages/whence` leaked into the next command** and an edit script
   ran from the wrong directory. Also already in the memory.
5. **A corpus-resolution loop regenerated every mutant per id** and had to be
   killed after 120 s; the same measurement with one id-set per file takes
   seconds. `generate` unparses per site and the loop called it ~5 700 times.
6. **`state/swe/round-431/evaporating-test-kills-nothing.json`'s
   `baseline`-key contradiction is untouched for a fourth D round**, and so are
   `test_swe_campaign.py::test_review_stage_and_report` and the never-run
   `test_swe_campaign.py[light]` slow-tier slice. This round spent its budget
   on the id scheme and says so rather than listing them as "carried".

### 7.1 The four false positives this round created for itself

The first corpus-resolution run reported exactly one unresolvable id for each
of the four subjects. All four were `state/swe/round-485/id-renumbering.json` —
this round's own artefact, which records the NAIVE variant's ids, i.e. exactly
the ids the tree does not have. Scoped out and re-measured. *Your own artefacts
are in the corpus*, and an instrument that walks `state/swe/*/` walks the
directory you are writing into.

## 8. Predictions — scored

Bank: `state/swe/round-485/PREDICTIONS.md`, 14 rows, frozen at `580cddf`
(commit `6037bb7`) before `harness/swe/mutation.py` was opened.

| # | tag | axis | prediction | actual | verdict |
|---|---|---|---|---|---|
| P1 | STRUCTURAL | SYSTEM | the naive implementation DOES renumber ≥1 pre-existing id on `whenceslow.py` | 260 of 315 ids change; 17.5 % survive | **HIT** |
| P2 | STRUCTURAL | SYSTEM | appending a new kind after every existing one leaves **100 %** of legacy ids byte-identical on all four subjects | 315/315, 443/443, 77/77, 95/95, and each new list is a strict prefix-extension | **HIT** |
| P3 | STRUCTURAL | SYSTEM | `#N` is a single global counter, **and** `_sites` emits kind-by-kind | counter global — right. Emission is `ast.walk` BFS, not kind blocks — wrong. The six ids fit both hypotheses and the bank picked the wrong one | **SPLIT** |
| P4 | STRUCTURAL | SYSTEM | for ≥1 subject the float-site count ≠ `unreachable_constants['float']` (the `__main__` guard, or a literal the operator skips) | 11/10/2/9 — **equal on all four**. No float lives in a `__main__` guard in any of them | **MISS** |
| P5 | STRUCTURAL | SYSTEM | `test_plan_default_is_smaller_than_slowtiers` goes red for ≥1 float mutant | killed by `whenceslow.py:625:fconst#315` | **HIT** (banked as low-information, and it was) |
| P6 | RATE | SYSTEM | 20-70 % of `whenceslow`'s float mutants killed by the whole test file | 3 of 11 = **27.3 %** | **HIT** |
| P7 | RATE | SYSTEM | the float-only `whenceslow` campaign, solo, in 30-180 s | **33.2 s** wall (29.5 s campaign) | **HIT**, at the bottom edge — the band came from a per-mutant distribution and the baseline run it added is cheaper than assumed |
| P8 | STRUCTURAL | AUTHOR | the operator lands this round whatever P1/P2 return | landed, appended, default-on | **HIT** |
| P9 | RATE | AUTHOR | 10-24 new test functions, `grep -cE '^\s*def test_'`, both counters reported | **+22** by `def test_` against `6037bb7` across four files (9+7+3+3), and **+22** collected (165 -> 187). The two agree because nothing added is parametrised. One of the 22 is a split rather than a fresh node: round 479's bound-5 test became two (the off-by-one and the now-reachable pin) | **HIT** |
| P10 | STRUCTURAL | AUTHOR | ≥1 new test wrong on first run | two: the docstring-quoting assertion and the DRIFT-branch fixture | **HIT** |
| P11 | STRUCTURAL | SYSTEM | ≥1 red present that this round did not cause | pristine baseline at `6037bb7`: **5 failed, 1506 passed, 21 skipped, 412 deselected in 428.84 s** — `test_corpus_evidence`, `test_whenceslow`'s membership pin, three `test_wiring_audit` nodes | **HIT** |
| P12 | STRUCTURAL | SYSTEM | adding a kind makes ≥1 existing test red OUTSIDE the file the round adds tests to | exactly two, both in `test_swe_falsifiers.py`, both pinning the pre-`fconst` bound 5 | **HIT** |
| P13 | no-basis | SYSTEM | whether any OTHER never-red node becomes reachable — declared no basis, committed to report | **zero.** `tierbudget`'s three rows stay never-red; 0 of its 9 float mutants killed anything | **no-basis-reported** |
| P14 | no-basis | SYSTEM | what `check_round_recorded` reports afterwards — declared no basis, committed to report every shape | §9 | **no-basis-reported** |

**Tally: 10 HIT, 1 SPLIT, 1 MISS, 2 no-basis-reported of 14** — 10 of 12
scorable, 83.3 %, against a corpus lifetime near 70.8 %.

### 8.1 The miss pattern

There is one miss and one split and they are the same shape: **both are the
line where the bank reasoned from the artefact it had rather than from the
mechanism.**

- P3 read six id strings out of round 479's prose and inferred kind-blocks from
  `297:ifneg#4` / `297:not#32` being far apart. BFS explains that datum equally
  well and the bank never considered it, because six ids is a sample of an
  ordering and an ordering is not a thing six samples pin.
- P4 reasoned "`unreachable_constants` counts constants, an operator excludes
  the `__main__` guard, therefore they differ" — a mechanism that is real and
  a population that does not contain an instance of it. `whenceslow.py`'s two
  guard exclusions are an `if` and a call, not floats.

Both are *step 19's shape one level up*: not a rate extrapolated from n=1, but
a **structure** inferred from a handful of instances nobody counted. §0.3
counted the floats and got P4's own denominator right; what it did not count
was the guard's CONTENTS, which is the term the prediction actually turned on.
The rule to carry: **when a structural line rests on "these two things count
different populations", the bank owes the DIFFERENCE as a §0 count, not the
inequality as a §1 bet.**

The two AUTHOR count lines (P9, P10) both hit, and P9 is the first output-count
line in four D/skills rounds not to miss high — because it was banked at
10-24 with the counter named after three consecutive rounds missed exactly
that, and because the round wrote fewer, larger tests than it would have.

## 9. Record-gap check, as committed in P14

`check_round_recorded.py` at the start of round 485 reported one shape: round
479, no `research-state.md` entry, `knowledge_file=False`, `git_committed=True`
— its diff had been landed by round 480 and its authorship had not. Round 485
paid it: `knowledge/round-479-the-sample-that-bought-an-absence.md` and a
`### Round 479` entry, both reconstructed from committed artefacts,
`git show aedad26`, and `logs/round-479.json` — round 479's own raw event
stream, which carries all 106 tool calls WITH their results, and is why that
file can quote command output round 479 never wrote down.

**Round 479's own 17-row bank is scored below**, not in its own file: signing
round 485's scoring with round 479's name is the false authorship the
reconstruction exists to avoid.

### 9.1 Round 479's bank — SCORED: 8 HIT, 5 MISS, 1 SPLIT, 1 VOID, 2 no-basis-reported of 17

Every verdict is read off `logs/round-479.json` (the call number is given), off
a committed artefact, or off HEAD.

| # | prediction | actual | verdict |
|---|---|---|---|
| P1 | the `whenceslow` never-red node is not bound 1 (scope); it is a genuine vacuity or an equivalent-mutant region | not scope — right. Neither of the two named alternatives: it is bound 5, operator coverage, and round 479 itself said so | **SPLIT** |
| P2 | the `redattrib` node is never-red under operator coverage (a string/format constant) | REFUTED by round 479's own rerun: it goes red for two mutants the `--sample 200` stride skipped. A SELECTION artefact, not an operator one | **MISS** |
| P3 | round 473's 17 rows score 10-14 HIT | **10 HIT** | **HIT** (bottom edge) |
| P4 | ≥1 of round 473's rows cannot be scored from disk and needs a re-run or an `unscorable` verdict | all 17 scored from the artefacts, one as the declared no-basis line; nothing was unscorable | **MISS** |
| P5 | `whenceslow.json`'s score is inside 0.35-0.60 | **0.5687** (call 28) | **HIT** |
| P6 | its `never_red` list holds 1-6 entries | **1** | **HIT** |
| P7 | round 473's P9 misses low; pooled never-red share 0-12 % | **4 of 103 = 3.9 %** (call 85) | **HIT** |
| P8 | `test_swe_mutation.py` is `swe_slow`-marked and DESELECTED by the fast tier | PROMOTED since round 385 at 18.17 s; round 479's own call 44 printed `promoted? True`. Banked from `run_tests_fast.sh`'s header while its read-set said the registry was unopened | **MISS** |
| P9 | `test_the_grandchild_pid_survives_a_grandchild_slower_than_the_cap`, alone, today, FAILS | **passed in 2.15 s** (call 46) | **MISS** |
| P10 | ...and the cause is timing/environment on a 1-CPU box | antecedent false. Round 479 went further and re-ran it under four CPU hogs: 3 of 3 passed (call 47), which is evidence AGAINST the timing hypothesis rather than for it | **VOID** (unscorable, and the probe is worth more than the row) |
| P11 | a placeholder census over all knowledge files finds 1-4 FILES | **11 files** (call 29) | **MISS (high)** |
| P12 | ...and 5-20 OCCURRENCES | **18** (call 30) | **HIT** |
| P13 | 12-28 new test functions this round | **54 − 30 = 24** by its own counter (call 101) | **HIT** |
| P14 | ≥1 of my new tests is wrong on its first run | two, in its own log: call 71 `1 failed, 26 passed` and call 77 `1 failed, 44 passed` | **HIT** |
| P15 | the fast tier ends the round red in ≥1 component the round did not cause | call 103: `1 failed, 1504 passed` — `test_the_declared_debts_are_exactly_the_one_still_owed`, opened by round 477 | **HIT** |
| P16 | no-basis: how many mutants are classified `error` across round 473's four campaigns | **0** in all four (call 28); round 473's own P12 banded 0-8 and HIT | **no-basis-reported** |
| P17 | no-basis: whether either never-red node, once repaired, is killed by a re-run campaign | reported both: `redattrib`'s needed no repair (already killable), and `whenceslow`'s repair was measured and DECLINED with the reason written down. Round 485 took the declined repair and the node is killed | **no-basis-reported** |

**8 HIT, 5 MISS, 1 SPLIT, 1 VOID, 2 no-basis-reported. 8 of 14 scorable =
57.1 %**, against a corpus median bank of 73.5 %.

**The miss pattern is a different one from round 473's, and sharper.** Four of
round 479's five misses (P2, P4, P8, P9) are lines about **artefacts its own
read-set listed as NOT READ**, and every one of them was cheap to settle:
`harness/tier-budget.json` is one `json.load` (P8); the grandchild node is one
`pytest` invocation that round 479 ran itself, as call 46, minutes after
banking (P9); round 473's four campaign JSONs are on disk (P4). Round 479's
bank is the cleanest instance in this corpus of the rule its own skill already
carries as **step 14's last line — *if a band is cheap to convert into a
measurement, it is a baseline and not a prediction*** — and the read-set
discipline (step 15) is what made it visible: the lines that lost are exactly
the lines whose subject the file itself declared unopened.

That is not an argument for reading everything. It is an argument that
**"unopened" is a reason to move a line to §0 or to no-basis, not a licence to
bet on it** — P16 and P17 are the same round declining exactly that way, and
both discharged cleanly.

## 10. Skill

`skills/falsifier-must-kill-something/SKILL.md` gains step 6c and two pitfalls;
see §11 of that file's own Verification block. The transferable rule is §3's:
*a soundness flag can only enforce the bounds it can SEE, so the audit is over
the narrowing knobs, not over the flag.*
