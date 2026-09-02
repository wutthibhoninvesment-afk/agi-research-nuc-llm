# Round 446 — language(C) — the rule, and the predicate that tested one node

**Track:** C (language). **Date:** 2026-09-02. **Model:** claude-opus-5.
**Subject:** round 444's next-step 4 — *"the exit contract is misleading for
3 of the 5 field programs that run"*.
**Result:** Whence **v0.42**, decision 51. One genuine interpreter defect
closed, one false positive the fix created and had to fix in the same commit,
two stale corpus constants re-derived, one corpus reader taught to ask the
question its sibling has asked since round 386, one carried number that held
and one that did not.

---

## 0. What I inherited, and what happened to it on re-derivation

Round 445's next-step 4 says round 444's items stand and were not
re-derived. Round 444's item 4, in full:

> The exit contract is misleading for 3 of the 5 field programs that run.
> `expense_tracker`, `mini_agi_guardian` and `prod_showcase_final` all exit
> 0 while `run.py` prints `dropped: N miss values computed and discarded`.
> `--strict-miss` (round 384) exists and **nothing in the corpus tooling
> uses it**; `curecheck.survey` records `rc` and not whether anything was
> dropped. That is a one-field change to `survey` and a real number nobody
> publishes.

Two clauses. The second is true. **The first is false**, and reading was
enough to establish it: `curecheck.replay` has called
`run_program(tmp, strict=True)` and recorded `strict_rc` since round 386
(`curecheck.py:765-766`), and `main`'s replay branch has printed
`%d clean under --strict-miss` for as long. `replay` is corpus tooling.

The accurate statement is sharper than the one I inherited, and it is the
whole shape of this round: **this repo has two readers over one corpus and
only one of them was asking the strict question.** `survey` — which is what
`curecheck.py corpus` calls, and which is the one that appears in SPEC.md's
measured blocks — recorded `rc` alone.

Also derived by reading, before any measurement:
`Interpreter.DROP_CAP`'s justifying comment says *"the whole tracked example
corpus drops 0 and the field corpus's worst program drops 5 (round 384's
measurement)"*. `examples/dropped.lang` is tracked and
`tests/test_examples.py::test_dropped_reports_the_one_miss_it_drops_on_purpose`
asserts it prints `dropped: 1 miss value ...`. Both halves of that comment
have moved. (Both were re-derived by running, in §5.)

Predictions were banked in `state/whence/round-446/PREDICTIONS.md` before
any of the measurements below, and both of the above were recorded there as
DERIVED-BY-READING so that they could not later be re-labelled as hits.

---

## 1. The finding: a rule stated in prose, implemented one node deep

v0.32 (round 384) is the version that ended silent misses. Its sentence is
exact and is still right:

> A miss that is the value of a statement nothing keeps cannot be asked
> anything by anybody.

Its implementation tested **one node**:

```python
def _note_drop(self, v, at):
    val = getattr(v, "value", None)
    if not isinstance(val, Miss):     # <- the OUTERMOST node
        return
```

The prose says *the value*. The code says *the outermost node of the value*.
For ten versions those coincided on everything the corpus contained, so the
detector looked correct. Measured at HEAD-before-this-round:

```
nosuch(1)                            -> dropped: 1 miss value …
fold(fn(a, x) { nosuch(x) }, 0, [1,2]) -> dropped: 1 miss value …
[nosuch(1)]                          -> (nothing)   rc 0
@{a: nosuch(1)}                      -> (nothing)   rc 0
[[nosuch(1)]]                        -> (nothing)   rc 0
map(fn(x) { nosuch(x) }, [1,2,3])    -> (nothing)   rc 0
print(map(fn(x) { nosuch(x) }, [1,2])) -> [miss, miss]   rc 0
```

The `fold`/`map` split is the tell. Neither builtin is more careful than the
other. `fold` returns the accumulator, which **is** the miss; `map` returns a
list that **contains** the misses. Whether a program's bug got reported came
down to which builtin its author happened to reach for.

`map` is not a corner case in this corpus. It is what a machine-written
program does to rows, and its result is the value an agent most often forgets
to bind.

## 2. Decision 51 — a discarded value is discarded whole

`Interpreter._misses_within(v)` walks a dropped `WList`/`Record` for miss
nodes inside it; `_note_drop` records each with the container's label, and
`_record_drop` is the single writer both paths share. Three rules, each a
decision rather than an implementation detail:

* **An element `print` has already shown is skipped**, so `[print(m), 1]`
  reports nothing for `m`.
* **A node is visited once.** `WList` views share one append-only buffer
  (v0.2's `shared-tip-immutable-lists`), so the same element node is
  reachable through every prefix of a list built by `push`; without the
  `seen` set a fold-built list is walked quadratically.
* **The walk is bounded and SAYS SO.** `DROP_SCAN_NODES = 100000`, and past
  it the run prints `(N discarded values too large to read to the end at
  100000 nodes — a miss deeper inside is not listed)`.

`Guess` is deliberately not walked; the reason is written into
`_misses_within`'s docstring rather than left implicit, and the case was
probed rather than assumed.

**A bug in my own first draft, caught by writing the test for it.**
`report_drops` opens `if not interp.dropped: return 0`, so my first version
printed the truncation note only when something HAD been found — i.e. never
in the one situation the sentence exists for: a walk that stopped early and
found nothing. `_report_truncation` is now called on both paths and
`test_a_scan_that_stops_early_is_reported_even_with_no_drops` pins it.

**The bound was wrong at first too, and the reason is measurable.** The first
draft used `DROP_SCAN_NODES = 5000`, which fires on
`map(fn(x) { x + 1 }, range(20000))` — a program with no defect. The walk is
proportional to a value the program *already paid to build*, so a bound tight
enough to fire on ordinary code buys nothing. What it must bound is the case
building did not pay for: one big list discarded by a statement inside a
recursion, walked once per drop. 100000 id-lookups is single-digit ms.

## 3. The companion half, which the corpus forced

The widening's **first run went red on a tracked example**, and the failure
was the widening's fault:

```
examples/history.lang   total=1
  within='let culprits'  num: cannot parse "5,25" (line 39)
```

`history.lang:43` is `print(culprits)` — a list of blame records whose
`.value` is a miss, and the next five lines ask it four `check`s, including
`at(culprits[0].value, "literal") == "5,25"`. That is the feature being used
exactly as designed, reported as a defect.

The cause is that **observation was implemented on the same outermost node
the drop test was**: `b_print` remembered a printed value only when its
payload was a `Miss`. Detector and suppressor were written in one change,
against one corpus, about one field — so widening one alone had to produce a
false positive precisely on the input the other exists for. The two halves
move together or not at all.

**In a SECOND dict, not more entries in the first.** `_observed` is capped at
`DROP_CAP = 100`. Merged, a program printing 100 harmless lists exhausts the
cap and the next printed MISS is then reported as a drop — v0.42 breaking the
case v0.32 got right. `_observed_aggr` has its own bound and
`_seen_by_print` is the one membership question both callers ask.
`test_the_two_observation_sets_are_bounded_separately` pins it with
`DROP_CAP + 5` printed lists followed by a printed miss.

**Falsified, not asserted.**
`test_history_lang_is_the_case_that_forced_the_observation_rule` runs the
example twice: once under `Interpreter`, asserting 0 drops, and once under a
subclass restoring the pre-v0.42 gate, asserting the false positive **comes
back** with `within == "let culprits"`. Deleting `_observed_aggr` cannot pass
this file.

**Known residual, deliberate and measured.** `full_show` renders a miss
nested inside a container as the bare token `miss` with no reason (`[miss]`,
`@{v: miss}`), so `print([nosuch(1)])` shows the reader THAT there is a miss
and not WHY. Calling that observation is generous. It is still the right call
over reporting `print(culprits)`, and the fix belongs in the RENDERING — not
touched here because **11** pinned mutation-killer regressions in
`tests/test_generated_killers.py` quote the `[miss, miss]` spelling verbatim
(`grep -c '\[miss' tests/*.py SPEC.md` -> 11). Separate decision, separate
blast radius, next step 3 below.

## 4. What it found: one, and I am publishing the one

Measured with a `PreV42` subclass that disables both halves, over every
`.lang` file on disk (18 tracked + 15 field):

```
                              v0.41   v0.42
  mini_agi_guardian.lang        4       5    <-- the only change
  everything else            unchanged
  TOTAL (33 programs)          12      13    (+1)
  cured field programs (replay, 10 files)  23 -> 23  (+0)
```

The one:

```
examples/mini_agi_guardian.lang
  line 48 (let conf_result, from line 32) in let r1 —
    unbound name 'return' (Whence has no `return`; a block's value is its
    last expression) (line 27)
```

Line 48 is a bare `r1`. `r1` is the record `run_full_audit` returns at line
39, and one of its fields is a miss made at line 27 by
`else { return ("ACCEPTABLE") }`. The program prints a banner, exits **0**,
and has carried that since it was written. `return` is one of the names
decision 41's table has a cure sentence for — the sentence existed and
nothing rendered it.

**The honest framing: the class is real and demonstrable in three lines, and
its yield on this corpus is one.** A widening that closes a whole silence
class and finds one instance is worth landing; a write-up that says "closes a
class of silent failures" without the number invites the reader to imagine a
different one.

## 5. The two corpus readers, and the sentence SPEC.md already contradicted

`curecheck.py corpus` published, before this round:

```
15 file(s): 5 parse, 5 reach a value (rc=0), 4 mechanical edit(s) applied in total
```

*"5 reach a value"* is a sentence SPEC.md itself contradicts three paragraphs
into `## v0.33`, under the heading **"Reaching a value is not working."**
The prose knew. The instrument did not.

Both readers now share one parser for the report line
(`curecheck.dropped_count`, anchored on `DROP_LINE_PREFIX`) and both publish
the pair. After:

```
15 file(s): 5 parse, 5 reach a value (rc=0), 2 of those clean under
--strict-miss (12 miss value(s) dropped), 4 mechanical edit(s) applied in total

10 file(s): 10 reach a value, 2 clean under --strict-miss (23 miss value(s) dropped)   [replay]
```

Three design points, each pinned:

* `rc`, `strict_rc` and `dropped` are three different facts. The contract
  (*would a CI fail this file*) and the size of the finding are not the same
  question; a file with one dropped miss and a file with six both have
  `strict_rc == 1`.
* `dropped_count` returns **`None`** and not `0` for a file that never ran.
  A column printing `0` for both would report ten parse failures as ten
  clean programs. `test_dropped_count_distinguishes_zero_from_no_measurement`
  and `test_fmt_survey_publishes_the_strict_verdict` both pin it (the stalled
  row must print `-` three times, never `0`).
* **One spelling of the anchor.** Round 445's finding was a fix that landed
  in one of two copies of a selector, so
  `test_the_report_line_has_exactly_one_spelling_in_curecheck` walks
  `curecheck.py`'s non-comment lines and fails on a second literal
  `"dropped: "`. `test_run_py_writes_the_prefix_curecheck_reads` is the
  cross-module anti-rot pin (`run.py`'s side is a format string, so it cannot
  be imported).

`verify` carried the identical misleading sentence over a different
directory and was corrected in the same commit, for the same reason.

**Two stale corpus-derived constants, re-derived rather than overwritten**
(the constant-vs-corpus-derived rule): `DROP_CAP`'s comment now carries round
384's reading AND round 446's, each attributed, plus the command that
re-derives them. SPEC.md's `## v0.32` gains a bracketed *"read as of v0.42"*
note rather than a rewrite — the 0 it records is what v0.32 measured.

## 6. Predictions, scored

Banked in `state/whence/round-446/PREDICTIONS.md` before measuring.
**5 HIT, 1 MISS, 1 PARTIAL, 1 abstention honoured, of 7 + 1.**

| # | prediction | outcome |
|---|---|---|
| P1 | exactly 1 tracked example changes exit under `--strict-miss` | **HIT** — `dropped.lang` |
| P2 | at least one tracked example OTHER than `dropped.lang` prints a `dropped:` line | **MISS** |
| P3 | `corpus` reads `15 … 5 parse, 5 reach a value, 3 mechanical` | **PARTIAL** — 5 and 5 right, mechanical is **4** |
| P4 | 3 of the field programs that run drop, and they are the three round 444 named | **HIT** |
| P5 | `agi_buy_and_hold.lang`: no basis, will report what it holds | **honoured** — parses, rc 0, drops 0 |
| P6 | the `len(_observed) < DROP_CAP` guard has no test | **HIT** — `test_v32.py:119` tests `dropped`'s cap, nothing tested `_observed`'s. Now `test_past_its_cap_the_observation_record_errs_toward_reporting` does |
| P7 | `grep -rn "reach a value" tests/` returns 0 | **HIT** — nothing pinned the sentence |

P1 and P2 were banked as a deliberate contradictory pair, so one of them is a
scored miss by construction; that is the point of banking both rather than
banking whichever one turned out right. P3 is the useful entry: the two
integers I reasoned about were right and the one I copied from SPEC.md's
`## v0.33` measured block ("3 mechanical") was stale — the same class as the
`DROP_CAP` comment, in the same file, found the same way.

P4 is worth naming: **a carried number that held.** Three consecutive rounds
had found that re-deriving a carried item changed its answer. This one did
not — and the clause next to it in the same sentence was wrong, which is the
argument for re-deriving per-clause rather than per-item.

## 7. Checks

```
languages/whence  run_tests_fast.sh   2245 passed, 3 skipped, 97 deselected
                                      in 234.97s, rc=0
                                      (was 2218/3/95 — +27 collected, +2 of
                                       this round's 29 are whence_slow)
                  tests/test_v42.py   29 passed (0.94s fast, 1.22s with -m "")
                  tests/test_v32.py + tests/test_examples.py   51 passed
                  tests/test_v22.py   55 passed  (the two version-header
                                      guards BOTH fired on this round's
                                      SPEC bump and both were satisfied by
                                      bumping, not by editing the guard)
curecheck.py      corpus              15 file(s): 5 parse, 5 reach a value
                                      (rc=0), 2 of those clean under
                                      --strict-miss (12 dropped)
                  replay              10 reach a value, 2 clean, 23 dropped
skills            run_checks_fast.sh  10 checker(s), 0 error(s),
                                      7 warning(s); unit_tests
                                      894 passed in 167.73s
```

That skills reading was `3 error(s)` on its first run and all three were
this round's own, each one cause: `skill_lint D002` (the new skill's
description at 1252 chars over a 1024 cap), `carryforward K001` (this round's
own bank not yet in `state/prediction-bank-ledger.json`), and `unit_tests`'s
two failures, which are `TestLiveCorpus` assertions downstream of those two.
Fixed inside the round; the D002 trim is why the description no longer names
its two confusables inline — the Related section does.

Serialised: `nproc` is 1 (round 435 item 8 / 445 item 6), and the whence tier
ran alone for its 234.97 s figure.

## 8. What v0.42 deliberately does NOT do

* It does not move the exit code, add a flag, or change any value, reason
  string or check result. The walk is passive, exactly as v0.32's recorder.
* It does not walk a `Guess`.
* It does not change how a nested miss RENDERS (§3's residual).
* It does not add liveness analysis. `let xs = [nosuch(1)]` then a bare `xs`
  is still a drop even though `xs` is in scope, because that is v0.32's own
  rule for the scalar case
  (`test_the_last_top_level_expression_is_a_drop_too`) and the two must not
  disagree about the same program.

## 9. Artifacts

* `languages/whence/whence/interp.py` — `_misses_within`, `_record_drop`,
  `_seen_by_print`, `_observed_aggr`, `DROP_SCAN_NODES`, widened
  `_note_drop` and `b_print`, re-derived `DROP_CAP` comment.
* `languages/whence/run.py` — `_report_truncation`, `within` rendering.
* `languages/whence/curecheck.py` — `DROP_LINE_PREFIX`, `dropped_count`,
  strict-aware `survey`/`_fmt_survey`/`replay`/`verify`.
* `languages/whence/tests/test_v42.py` — 29 tests.
* `languages/whence/SPEC.md` — decision 51, `## v0.42`, header v0.41 -> v0.42,
  `## v0.32` read-as-of note, `## Running` clause.
* `state/whence/round-446/PREDICTIONS.md`.
* `skills/suppressor-shares-the-detector-shape/SKILL.md` + 4 cases in
  `skills/trigger-cases.json` (338 -> 342), registered unprobed
  (`state/known-unprobed-skills.json`, 25 -> 26 entries — the batch round
  435's item 4 asked to be PRICED is now sixteen deep and this round grew it
  by one without paying it; declared there rather than argued away).
* Landed a predecessor's orphan: `state/slow-tier-ledger.jsonl` row 43, the
  driver's post-445 `slowtier-slice` append at 04:33:58Z, after round 445's
  last commit at 04:18:06Z. Same shape rounds 442/444/445 landed for their
  predecessors. Attributed and committed, not allowlisted.

## 10. Next steps

1. **The rendering residual is now the only thing keeping "print is
   observation" from being literally true.** `full_show` shows a nested miss
   as `miss` with no reason, so `print([nosuch(1)])` is suppressed on a
   promise it does not keep. The fix is one branch in `values._show`; the
   cost is that **11** lines in `tests/test_generated_killers.py` and
   SPEC.md quote `[miss, miss]` verbatim, and those are mutation-kill
   regressions whose value IS their exactness. Whoever takes it should decide
   between (a) a nested rendering that carries the reason and 11 re-pinned
   killers, or (b) keeping the rendering and making the SUPPRESSION narrower
   (print observes a container only when it renders every miss inside it).
   Say which, and run the corpus before and after. language(C).
2. **`Guess` is the one aggregate v0.42 does not walk, on an argument.** The
   argument is written down (`_misses_within`'s docstring) and is not tested:
   nothing asserts that `guess(nosuch(1), 0.5, [])` as a dropped statement
   reports nothing, and nothing asserts that is the right answer. If the
   decision is right it deserves a pin; if it is wrong it needs its own
   sentence in the report. language(C).
3. **Round 444's items 1, 2, 3 stand and were NOT re-derived here.** Item 4
   was, and half of it was false — so the other three should be re-derived
   per-CLAUSE and not per-item. In particular item 2 (an ABSENCE carries a
   reason and nothing re-derives one) is now a live example: this round's §8
   is five deliberate absences and only one of them
   (`test_the_default_bound_does_not_fire_on_ordinary_code`) has a checker.
   language(C) or skills(B).
4. **The unprobed-skills batch is SIXTEEN deep** and this round added the
   sixteenth without pricing it. Round 435's item 4 asked for it to be priced
   BEFORE being grown, eleven rounds ago. A probe is ~$0.05 and needs
   operator authorisation this round did not have; the arithmetic is in
   `state/known-unprobed-skills.json`'s `_round_446_note`. skills(B).
5. **Round 445's items 1, 2 and 3 stand, unchecked** — `guardpin_fixture.py`'s
   14 never-collected test functions (one already wrong), the slow tier's 3%
   recall and unpublished ceiling, and the cross-file body-hash duplication
   checker. harness(A) or SWE-loop(D).
6. **Round 435's items 1-3 and round 434's items 2-6 stand, unchecked.**
   language(C) owns 435's item 1 (`polarity.py audit`'s MISPOINTED predicate
   against a registry whose header calls 0 its acceptance criterion) and
   434's items 2-5.
7. **`nproc` on this box is 1.** Respected: the whence tier ran alone for its
   234.97 s. Only text edits ran beside the background suites.
8. **Standing, and not touched by this round:** the NUC `retention --strict`
   deadline; the `%vmeff` residual; `case_coverage`'s disagreeing verdicts;
   `claim_check` executing 0 of its commands; the operator-blocked
   `--cap 196`; the exhausted E-mission list; and CLAUDE.md's `CRITICAL
   MISSION` block, which round 444 REFUTED rather than re-escalated — its
   claim 1 (`fold()` returns `Miss`) is FALSE as stated and
   `tests/test_critical_mission_claims.py` (6 tests) pins that. Note for
   whoever eventually deletes it: this round found the block's most likely
   *origin*. `expense_tracker.lang` and `prod_showcase_final.lang` both print
   `fold needs a list, got <fn add_item> (arguments fit fold(fn, acc, xs))`
   inside a dropped miss while exiting 0, which is exactly what a reader who
   filed "fold returns Miss" would have seen. The deletion is still the
   operator's call. `languages/whence/SECURITY.md` is still uncommitted,
   still not this program's, and still the operator's decision — do not copy
   a carry count for it from this file; the checker's own line is the only
   source.
