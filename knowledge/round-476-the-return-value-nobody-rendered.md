# Round 476 (language C) — the return value nobody rendered

**Track:** language(C). **Base:** `312b260`. **Artefacts:**
`languages/whence/whence/interp.py` (`Env.__repr__`, `_ENV_REPR_NAMES`),
`languages/whence/tests/test_folding.py` (new, 150 tests),
`languages/whence/SPEC.md` (§ Decision 58),
`state/whence/round-476/PREDICTIONS.md`.

## 0. The one-line finding

`CLAUDE.md` ordered this round to fix `b_fold()`, which "returns an `Env`
object instead of the accumulator value, breaking all aggregation logic."
**The claim is false, the mechanism it names is impossible, and the `Env` in
its evidence is real** — it is the documented return value of
`Interpreter.run`, which is the one object this language hands a caller and
has never rendered. The fix is a `__repr__`, not a fold.

## 1. What this round was told to do

Round 476's prompt says track language(C). `CLAUDE.md` carries, above that,
a block headed `🚨 CRITICAL MISSION #476: FOLD BUG FIX (Opus-5 Direct)`
with six numbered "Immediate Action Required" steps and a briefing at
`knowledge/mission-fold-fix-v1.md`. Debugging the Whence interpreter core
*is* language(C), so there was no conflict to resolve: the mission was on
track and this round ran it.

It ran all six steps. Five of them could not be executed as written, and
saying which and why is most of the result.

| step | outcome |
| --- | --- |
| 1. read the briefing | done |
| 2. inspect `b_fold()` "around line 2666" | `b_fold` is at line **3611**. 2666 is inside the iterative deep-equality walk. |
| 3. "fix the closure evaluation to return final value, not Env reference" | **nothing to fix** — see §3 |
| 4. `pytest tests/test_folding.py` | `ERROR: file or directory not found`. The file did not exist. It does now. |
| 5. "no regression in existing 800+ unit tests" | the tree collects **2603**; the fast tier is 2488 |
| 6. commit `fix(b_fold): correct Env return to accumulator value` | **not done, and deliberately.** That subject asserts a defect this round measured as absent. Committing it would put a false statement in the permanent record of a repo whose whole discipline is that the record is checkable. |

Step 6 is the one place this round refused an explicit instruction, and it
is recorded here rather than quietly skipped.

## 2. Reproduction first (debug-mantra step 1)

```
$ cd languages/whence
$ .venv/bin/python   # the briefing's success criterion, correct arg order
>>> fold(fn(acc, val) { acc + val }, 0.0, [10.0, 20.0, 30.0])
60.0
```

**The mission's own §5 success criterion — "`fold([10, 20, 30], 0, fn(a, x)
{ a + x })` must return 60.0" — already passed at base, before any change.**
That is the first thing a round should check and it takes four lines.

The briefing's §2 reproduction, run verbatim:

```
let nums = [10.0, 20.0, 30.0]
let total = fold(nums, 0.0, fn(acc, val) { acc + val })
print(str(total))
->  miss: fold needs a list, got <fn> (arguments fit fold(fn, acc, xs)) (line 2)
```

Not an `Env`. Not silent. `fold` is registered `("fold", 3, "fn:fn, acc,
xs:list")` — **callback first**, consistent with `map(fn, xs)`,
`filter(fn, xs)` and `find(fn, xs)`. The briefing passes `(xs, acc, fn)`,
which is `reduce`'s order.

Every breadcrumb, measured at `312b260`:

| the briefing says | measured |
| --- | --- |
| `b_fold` returns an `Env` | `Prov` in 24 argument shapes × 4 engines; `Env` in none |
| success criterion "must return 60.0" | **already `60.0`** |
| "around line ~2666" | 3611 (3659 after this round's own edit) |
| `pytest tests/test_folding.py` | file did not exist |
| "800+ unit tests" | 2603 collected |
| `<whence.interp.Env object at 0x…>` from `b_fold` | that string exists; `b_fold` is not where it comes from |

## 3. Falsification (debug-mantra step 3): the mechanism is unavailable, not merely absent

The briefing's §3 is specific, which is what makes it checkable:

> 3. However, `fn_obj(args)` inside the loop is returning an `Env` reference
>    (the local frame) instead of the closures final expression result.
> 4. This `Env` object becomes the new `acc`, breaking arithmetic on the
>    next iteration.

`b_fold` has exactly three `return` statements — a propagated miss, a
`mk_miss`, and `derived("fold", "%d items" % n, line, (acc, xs),
acc.payload)`. And:

```python
Env.__slots__ == ("vars", "parent", "interp")     # no `payload`
Env().payload  ->  AttributeError: 'Env' object has no attribute 'payload'
```

So an `Env` accumulator cannot be returned; it raises at `acc.payload`.
Driven through the real loop — a `Builtin` callback that returns an `Env`,
bound the way `_install_builtins` binds one — that is exactly what happens
(`test_an_env_accumulator_crashes_it_cannot_be_returned`), with a positive
control alongside it so the injection harness is not what raised.

**The report's evidence and its diagnosis exclude each other.** The stated
cause produces a traceback. The published log shows a value. A report can be
wrong; a report that is *internally* inconsistent tells you the author was
looking at two different things and joined them.

## 4. Where the `Env` came from (cross-reference, step 4)

`whence/interp.py:729`:

```python
def run(self, source):
    """Parse and execute a program. Returns the top-level Env."""
```

That is the whole answer. The briefing's debug log is the return value of
`Interpreter.run`, printed. Re-taken at base:

```
=== FOLD DEBUG RUN ===
Result Type: Env
Result Value: <whence.interp.Env object at 0x7b118ddbf9c0>
env.get("total")  ->  Prov('let', 'total', line=2, 1 inputs, value=60.0)
```

**The fold value was never lost. It is a name inside the object the author
was holding while reporting it missing.**

### The five steps that produced a false bug report

1. Wrote `fold(xs, acc, fn)` — `reduce`'s order, not this language's.
2. **Decision 32 worked.** The miss named the signature that would have
   worked. `_order_hint`'s own docstring uses
   `" (arguments fit fold(fn, acc, xs))"` as its canonical example, so
   `fold` is the archetype that clause was built for.
3. Did not stop at the message. **This is not a defect — it is what a
   careful engineer does**, and any account that blames the author here
   learns nothing.
4. Dropped to Python, and landed on the one value in the system with no
   rendering. It answered with a module path and a heap address.
5. Attributed the host object to the nearest Whence name in the frame.

Round 444 refuted the OLDER `CRITICAL MISSION` block's "`fold()` returns
`Miss`" and named the true statement behind it (wrong argument order, said
out loud). Round 349 refuted it before that. **#476 is the third pass at the
same confusion, and the first one where the author went below the language's
own surfaces** — which is the evidence that a better error message was never
the fix. The message was already right. The reader left the surface it was
on, and the next surface down was blank.

## 5. The change — decision 58

`Env.__repr__`, plus `_ENV_REPR_NAMES = 4` — 18 lines of code in
`whence/interp.py` and nothing else in the interpreter. Decision 48
(v0.39, round 408) already set the rule — *every token a diagnostic names is
either a literal the author can type back verbatim in Whence, or prose* —
and its scope is DIAGNOSTICS, so it read the surface it was written for and
walked past a return value, which carries no error.

```
before  <whence.interp.Env object at 0x7b118ddbf9c0>
after   <whence scope: 2 names (nums, total), 1 enclosing — a SCOPE, not a
        value; Interpreter.run() returns this, and the program's results are
        the names INSIDE it (env.get("x"))>
```

There is no Whence literal for a scope, so by decision 48's own dichotomy it
is prose. It is **deterministic** (no address — two runs of one program give
one string, which is what makes it pinnable at all) and **bounded**: 166
characters at 2 names, 187 at 50, 191 at 2000. Only the digit count of two
integers grows.

**Four things deliberately NOT done**, each because a reader already depends
on the current behaviour:

* `run` keeps returning the `Env`. v0.32 makes every top-level expression
  statement a drop *because* the value has nowhere else to go;
  `depthcensus.py` (round 452) walks from the top-level `Env`;
  `timetravel.py` reads `Env.vars`. Three readers broken to spare one repr
  is the wrong trade.
* `Env` does not get a `payload`. The `AttributeError` is the falsifying
  evidence; making an `Env` quack like a value is how the impossible
  mechanism would become possible.
* `b_fold` untouched. Round 347's fix (the accumulator belongs in the miss
  inputs) is re-pinned, not revisited.
* `fold`'s argument order unchanged — consistent with `map`/`filter`/`find`,
  and two field-corpus programs already depend on the miss it produces.

### Verification

```
$ cd languages/whence && ./run_tests_fast.sh
2635 passed, 3 skipped, 115 deselected in 263.50s (0:04:23)     EXIT=0
```

Base `312b260` was `2485 passed, 3 skipped, 115 deselected in 262.07s`. Both
under the canonical script, which execs SYSTEM `python3` 3.12.3, serialised
(`nproc` is 1). The skills corpus-check is back to 10 checkers / **0 errors**
/ 8 warnings.

## 6. `tests/test_folding.py` — 150 tests

The file `CLAUDE.md` told every round to run. Six groups: the success
criterion under all four engine configurations; a 24-shape × 4-engine matrix
asserting the return type is never `Env`; the impossible mechanism driven
through the real loop; the `Env` repr; `map`/`filter` untouched plus fold's
provenance node; and claim pins that **expire correctly** — they skip if the
block leaves `CLAUDE.md`, because deleting it is the operator's call.

One sub-finding worth its own line. The order hint covers **four** of the
five wrong permutations, not five. `fold(0, fn, xs)` has a list in the `xs`
slot, so it passes `b_fold`'s list check and is caught one step later by
`0 is not callable` — also precise, different surface, no hint. The first
draft of this suite asserted the hint on all five and failed; the split
(`HINTED_PERMS` / `LATE_PERMS`, with a third test proving the two groups are
exhaustive) is the corrected claim.

## 7. Predictions scored (D-013)

Banked in `state/whence/round-476/PREDICTIONS.md` before measuring.

| # | prediction | outcome |
| --- | --- | --- |
| P1 | fast tier green at base, 2400-2560 collected | **HIT** — 2485 passed, 3 skipped, 115 deselected, 262.07 s; collected 2488 |
| P2 | `Env.__repr__` changes zero test outcomes | **MISS** — true of the edit, false of the round. Six tests went red, none touching `Env`. See §7a |
| P3 | no `b_fold` path returns an `Env`; ≥20 shapes, 0 `Env` | **HIT** — 24 shapes × 4 engines, 0 |
| P4 | order hint fires for every wrong permutation | **MISS** — 4 of 5. See §6. The prediction was too strong and the test written from it failed. |
| P5 | system `python3` and `.venv/bin/python` agree | **HIT** — both 3.12.3; `run_tests_fast.sh` execs system `python3` and the new file passes under both |
| P6 | new file holds 12-20 tests | **MISS** — 150. The estimate forgot its own parametrisation: 24 shapes × 4 engines is 96 tests from one function. |
| P7 | round 444's `test_critical_mission_claims.py` stays green with the new block | **HIT** — the #476 block was appended after the round-350 block, not a replacement, so both the `has_block` gate and the claim regexes still match |

**4 hits, 3 misses.** All three misses share a shape: each assumed a surface
was more uniform than it is — one edit's blast radius (P2), one diagnostic's
coverage (P4), one function's test count (P6). P4 and P6 were both refuted by
artefacts this round wrote from the predictions themselves, which is the
cheapest possible way to find out.

## 7a. The most useful miss: this round's own artefacts are measured subjects

P2 said `Env.__repr__` "changes ZERO test outcomes", backed by a repo-wide
grep for the default repr that returned nothing. **The grep was right and the
prediction was wrong**, because it scoped itself to one edit while the ROUND
added two artefacts that two independent instruments measure.

Six tests went red on the post-change fast tier. Not one of them touches
`Env`.

**(a) `test_specreg.py::test_the_live_spec_registry_has_no_errors`** — minting
decision 58 in a prose section with no matching entry in SPEC.md's
`## Anti-mainstream design decisions` list:

```
SPEC.md:9708: ERROR S001 decision 58 has a prose section … and NO entry in
Anti-mainstream design decisions — the registry's max is 57, so the next
round to mint a number reuses 58
```

That is a guard doing exactly its job, catching a collision *before* it
happened rather than after two decisions shared a number. Fixed by writing
the registry entry (`58. **A value this implementation HANDS A CALLER is a
surface …**`).

**(b) five tests in `test_testcorpus_census.py`** — `tests/test_folding.py`'s
24 Whence programs entered the harvested test corpus, which the census
measures over the LIVE tree:

| counter | before | after |
| --- | --- | --- |
| `programs` | 829+ | 847 |
| `calls + module_calls + stmt_node_args` | 987 | 1018 |
| residual rows | 101 | 106 |
| of which string-building | 93 | 98 |
| `nonconstant_programs` | 58 | 62 |
| **non-string-building rows (`rest`)** | **8** | **8, same classes, same locations** |

The last row is the finding. The census's design is a ratchet
(`residual <= N`) whose own comment says *"Raise this bound only together
with a row that says where the new residual is"* — and all five new rows are
`binop:Add` (×3), `call:.join` and `bound_nonconstant:call:.join`, i.e.
`src + '\nprint(str(t))\n'` at three sites and `"".join(...)` at two.
**Every one of them is the class the census already classifies as
string-building and explicitly not a diagnosis, so the eight-row set that
carries the instrument's real claims did not move at all.** Had my file
introduced an unreadable construct of a NEW kind, it would have landed in
`rest` and the class list would have failed instead of a count.

So the counts were raised with all five rows itemised in the file, per its
own procedure and round 474's precedent. **This is a validation of the
census, not a concession to it:** the instrument distinguished "the corpus
grew" from "the instrument lost something", which is the whole reason round
468 converted it from counts to rows.

**(c) and then a third, from a different checker entirely.** After both of
the above were green, `skills/skill-authoring/scripts/corpus_check.py`
reported `carryforward ERROR K001`:

```
state/whence/round-476/PREDICTIONS.md: ERROR K001 round 476 banked
predictions and state/prediction-bank-ledger.json has no entry for it —
nobody can tell whether D-013's second half was ever done
```

I had banked predictions *and scored them* and would still have committed
with the bank unregistered. Two live tests carried it —
`test_the_live_ledger_accounts_for_every_bank_on_disk` and
`test_live_corpus_is_clean`. Entry `"476"` added; 8 insertions and no
reformat, because the ledger round-trips exactly at `indent=1,
ensure_ascii=True` and I checked that before writing rather than after. Same
clerical shape round 474 recorded for round 472.

The general lesson, which this box has banked before and I reproduced anyway:
**a round's new files are inside the corpus its own suite measures.** A
"no test outcomes change" prediction has to be scoped to the ROUND, not to
the edit. Three instruments — `specreg`, `depthcensus`, `carryforward` —
each found a different consequence of this round's own artefacts, and none of
them was looking at `Env`.

## 7b. Skill: `errors-that-name-the-fix` UPGRADED, not a new one

That skill's opening paragraph is:

> An error that is accurate and unhelpful is the most expensive kind, because
> nothing looks broken. `fold needs a list, got <fn>` is true, precise, points
> at the right argument — and the user filed it as a bug in `fold`.

**It was born from this exact confusion**, in round 354, and its whole premise
is that a message which names the fix stops the false bug report. Round 476 is
its counter-example, and that is worth more to it than another confirmation:
the message named the fix, was delivered, was rendered — and the report was
filed anyway, because the reader went one layer below it.

Added (+64 lines): a trigger for **a bug report that cites a host object as
its evidence** (`<module.Class object at 0x…>`, `[object Object]`, a bare
pointer); the generalisation of the skill's own rule from diagnostics to *every
value the implementation hands a caller*; a cheap procedure for finding your
own unrendered surfaces (list the classes your public API returns or stores
where a caller can reach them, grep for which have no `__repr__`, and for each
ask "can a caller hold this?" — a `Scope`/`Env`/`Context` returned by `run()`
is the classic, because it is load-bearing internally and looks like an
implementation detail from the inside); the four properties the repr needs
(prose when there is no literal, deterministic, bounded, names the way out);
**two traps in the fix itself** — do not change the return TYPE to make a repr
nicer without counting its readers (Whence's `Env` had three against one), and
do not make the object quack like a value, because the `AttributeError` is the
evidence the reported mechanism was impossible; and the four-step
falsification order for reports of this shape (run the report's own success
criterion first; find which surface emits its evidence string, by grepping for
the TYPE rather than reasoning about the accused function; check the stated
mechanism against the accused code's actual `return` statements; check every
coordinate it cites).

**Upgraded rather than authored deliberately.** A new skill owes three positive
trigger cases and a runnable Verification section — research-state round 434
item 9 is explicit that a non-skills round which skips those turns the corpus
health check red — and this finding belongs *beside that skill's own example*,
not in a file next to it.

## 8. This round's own errors, in full

Eight, all found by running things rather than by reading them. Six were in
the test file, one in SPEC prose, one in a prediction; the last two are §7a.

1. **`{n: 0}` is not a record literal** — Whence writes `@{n: 0}`, and the
   parser says so (`_RECORD_HINT`). Two matrix rows.
2. **Asserted the order hint on all five wrong permutations.** Four. §6.
3. **Bound a bare `Builtin` into globals.** `_install_builtins` binds
   `Prov("builtin", name, 0, (), name, b)`; the bare object blew up in
   `_propagate`'s `_is_miss(a)` on `a.value` before `b_fold` ran. Every
   value crossing a builtin boundary in this language is provenance-wrapped,
   with no exception for test scaffolding.
4. **Assumed `steps(v, pat)` returns a count.** It returns the matching
   nodes; the count is `len(steps(...))`.
5. **Pinned `b_fold`'s absolute line number, 3611 — and my own
   `Env.__repr__` insertion moved it to 3659 in the same commit.** The
   briefing's claim is "~2666", so the refutation is a DISTANCE from 2666,
   which is what the test asserts now. A coordinate pinned absolutely is
   stale before the round ends; this repo has banked that lesson and I
   reproduced it anyway.
6. **Wrote "187 characters at a 2000-name scope" into SPEC.md without
   measuring it.** It is 191. Corrected in place, with the correction
   visible in the text. This is the exact class the state file's
   "constant- vs corpus-derived claims" rule exists for: I asserted a
   CONSTANT (the repr does not grow) from one measurement at one size.

7. **Minted decision 58 in a prose section without registering the
   number**, which `specreg.audit()` caught with the consequence spelled
   out: *"the registry's max is 57, so the next round to mint a number
   reuses 58"*. §7a(a).
8. **Predicted a one-edit blast radius for a two-artefact round.** §7a.
9. **Banked predictions without registering the bank** in
   `state/prediction-bank-ledger.json` — D-013's second half. Caught by
   `carryforward K001`, §7a(c).

All three of the errors the checkers found (7, 8, 9) are about this round's
own output rather than about `fold`, which is the same axis the prediction
scoring landed on: 4 of 4 predictions about the tree under study were right
and 0 of 3 about the round itself were.

Errors 5, 6 and 8 are the three this program keeps re-learning — a coordinate
pinned absolutely, a constant asserted from one sample, and a round's own
files forgotten inside the corpus its suite measures. They are recorded here
as reproductions, not as news.

## 9. The two unattributed working-tree paths

The record-gap check named `M CLAUDE.md` and `?? knowledge/mission-fold-fix-v1.md`.
Attributed, not adopted:

* mtimes **2026-09-03 13:11:38** and **13:11:16 UTC**.
* Round 475 finished at 12:34:18 (`success`); round 476 first started at
  13:53:31. **No round was running at 13:11** — the driver was executing
  post-round health checks and slow-tier slices from 12:51 to 13:52, and
  those do not author files.
* The content is addressed TO the rounds: `**Author:** Research Admin |
  **Target:** Opus-5 Core Engineer`, `**Instruction:** …`. No round writes
  instructions to itself in `CLAUDE.md`.

Same authorship class as the older block, which round 349 committed verbatim
as `680b273` ("Land the operator's CRITICAL MISSION block in CLAUDE.md
verbatim (not authored by a round)"). This round follows that precedent
exactly: **committed byte-for-byte as found, in a commit that says it is not
this round's words**, so it stops being re-flagged every round and the
evidence against its claims lives here and in `tests/test_folding.py` rather
than in an edit to the operator's own file.

`languages/whence/SECURITY.md` is untouched — still escalated, still the
operator's decision, and its carry count is the checker's to report.

## 10. Next steps

1. **`CLAUDE.md` now carries TWO `CRITICAL MISSION` blocks making the same
   false claim about `fold`, refuted three times (rounds 349, 444, 476).**
   Both are one deletion each for the operator. The round-350 block has been
   re-escalated nineteen times. Do not reword them — `tests/test_folding.py`
   and `tests/test_critical_mission_claims.py` pin the CLAIMS and expire
   cleanly when the blocks go. **language(C) or the operator.**
2. **Decision 58's rule is stated for `Env` and applied to `Env` only.** The
   generalisation — *every value this implementation hands a caller is a
   surface* — has not been swept. The unrendered candidates a caller can
   reach: `Explanation` (payload of `why`), `Closure`, `Builtin`, `WList`,
   `PMap`, `Record`, `Miss`, `Guess`. `WList`/`PMap` have constructor-style
   reprs; the rest were not checked this round. **Somebody should grep for
   classes with no `__repr__` and ask, for each, whether a caller can hold
   one.** language(C).
3. **The order-hint coverage number is new and un-swept.** `fold` gets 4 of
   5 wrong permutations. Nobody has taken that ratio for `put`, `typed`,
   `guess`, `map`, `filter`, `find`, `push`, `at`, `steps` — the other
   builtins `_order_hint` serves. The measurement is cheap and it is the
   kind of number that turns out to be worse somewhere. language(C).
4. **Round 434's items 2, 3, 4, 5 and round 428's item 4 are still open and
   were NOT touched by this round** (the atom table's precondition-with-no-
   decider risk; the 7 `append_only`/`refusal` `unknown` residuals; CP03p as
   the one pin that moves the contingency table; `classify` 161 vs
   `checkpin run` 162). This round spent itself on the mission block
   instead, which was the right call for a BLOCKING escalation about this
   tree's own code — but it means five language(C) items have now been
   carried without re-derivation for another rotation. Re-derive before
   quoting: this round's P4 and P6 were both wrong.
5. **`harness/tests/test_swe_mutation.py::test_the_grandchild_pid_survives_a_grandchild_slower_than_the_cap`
   is RED** at round 475's health check (1 failed, 1504 passed). Not this
   track's file and not touched here. harness(A) or SWE-loop(D).
