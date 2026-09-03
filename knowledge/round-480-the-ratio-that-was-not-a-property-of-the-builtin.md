# Round 480 (language C) — the ratio that was not a property of the builtin

**Track:** language(C). **Base:** `aedad26`. **Bank:**
`state/whence/round-480/PREDICTIONS.md` (three banks, §2 / §4 / §5, each
dated against what was already known when it was opened).
**Artefacts:** `languages/whence/orderhint.py` (new, the instrument),
`languages/whence/tests/test_v46.py` (new, 25 tests),
`languages/whence/whence/interp.py` (`_order_hint`'s fourth silence;
`fn:fn` checks in `b_map`/`b_filter`/`b_find`/`b_fold`),
`languages/whence/SPEC.md` (Decision 59 + registry entry),
`languages/whence/tests/test_folding.py` and `tests/test_v31.py` (two pins
this round moved, both deliberately),
`harness/wiring-registry.json`,
`state/whence/round-480/orderhint-baseline.json` (the pre-fix census,
frozen before anything was touched).

## 0. The one-line finding

Round 476 asked for a coverage ratio. **The ratio is not a property of the
builtin** — it is a property of the `(builtin, witness)` pair, and the same
builtin lands on opposite verdicts for two witnesses that differ only in one
argument's kind. Taking it anyway produced three results the question did
not anticipate: a hint that gave a **false cure**, four builtins that never
checked half their own declared signature, and — the number that matters
most — **seven of forty wrong argument orders that return a wrong answer
with no diagnostic at all**, which is seven times the coverage gap being
asked about.

## 1. The question, and where it came from

`state/research-state.md`, round 476's next-step 3, carried unchanged by
rounds 477 and 478:

> **The order-hint coverage ratio is NEW and un-swept.** `fold` gets 4 of 5
> wrong permutations; the fifth is caught elsewhere, also precisely. Nobody
> has taken that ratio for the other builtins `_order_hint` serves — `put`,
> `typed`, `guess`, `map`, `filter`, `find`, `push`, `at`, `steps`. Cheap,
> and the kind of number that turns out to be worse somewhere.

It was worse somewhere. It was worse in a different dimension than the one
the sentence names, which is the part worth keeping.

## 2. The metric, defined before it was taken

Fixed in the bank's §1 before any code existed, and repeated in
`orderhint.py`'s module docstring so it does not live only in a bank
nobody re-reads.

A **witness** for builtin `f` of declared arity `n >= 2` is a tuple of `n`
Whence expressions such that `f(witness)`, in the order `_BUILTIN_SIGS`
declares, does not miss. Each of the `n! - 1` non-identity permutations is
run through all three host evaluation modes and classified:

| class | meaning |
| --- | --- |
| `HINTED` | a `Miss` whose reason carries ` (arguments fit NAME(...))` |
| `BARE` | a `Miss` with no such clause |
| `ACCEPTED_DIFF` | **not** a miss, and renders differently from the correct call |
| `ACCEPTED_SAME` | not a miss, renders identically — inert for this witness |

Orthogonally each permutation is tagged `kind_blind` when
`_sig_fits(sig, permuted_payloads)` holds. `_order_hint`'s second declared
silence is `if _sig_fits(sig, payloads): return ""`, so on a `kind_blind`
row the hint is **structurally impossible** — no miss site, however placed,
could produce one. `kind_blind` is therefore the ceiling, not a defect:

    coverage = HINTED / (n! - 1)     <=     1 - kind_blind_fraction

## 3. The baseline, frozen before anything was touched

`state/whence/round-480/orderhint-baseline.json`, 24 witnesses over the
21 builtins of arity >= 2, 40 wrong permutations:

```
POOLED  hinted 29/40 = 0.725   ceiling 0.775   reachable gap 2
        silently wrong answers (ACCEPTED_DIFF): 7
```

`fold` reproduced round 476's 4-of-5 exactly, which is what licensed the
instrument to speak about the other twenty. The **reachable gap was two
rows**, and they are two different defects rather than one:

| row | result at v0.45 | why unhinted |
| --- | --- | --- |
| `fold(0, fn, xs)` | `0 is not callable` | the miss is raised by the CALL machinery, which knows nothing about fold's signature |
| `matches("num", 1)` | `false` | it never misses at all |

The second is not closable and should not be closed: `matches` is total by
contract (round 335), and **a diagnostic that rides on misses cannot serve
a total function.** That is a bound on the mechanism.

## 4. The finding the ratio is not a number without

`note(label:str, v)`, two witnesses differing only in the kind of `v`:

| witness | transposition | verdict |
| --- | --- | --- |
| `note("tag", 5)` | `note(5, "tag")` | `HINTED`, `kind_blind` 0, coverage **1.00** |
| `note("tag", "five")` | `note("five", "tag")` | `ACCEPTED_DIFF`, `kind_blind` 1, coverage **0.00** |

Same builtin, same arity, opposite verdict — because with a string in `v`
both orders satisfy the declared kinds, `b_note` cannot tell, and the
program gets a differently-labelled value with no diagnostic whatever.

So **`coverage(note)` is a number that does not exist.** Every row this
round publishes is keyed by witness id, and
`test_v46.py::test_the_ratio_is_a_property_of_the_witness_not_of_the_builtin`
holds that open. The bank's §3 was written before the measurement to catch
exactly the failure of writing `coverage(f)` afterwards.

## 5. Defect 1 — the hint that was a false cure

Found by hand-probing ten calls of the form `f(bad, ...)` where `bad` is a
propagated miss. One of the ten:

```
let bad = get(@{}, "z")
note(bad, "hi")
-> note label must be a string, got miss (arguments fit note(label, v))
```

The clause is **true about kinds and false as advice**. `note("hi", bad)`
does not repair a record lookup that failed on the line above; the reader is
told to reorder arguments when the fault is upstream of the call entirely.

The mechanism is general and it is `_kind`'s: `_kind(Miss)` is `"miss"`, a
tag **no `sig` declares**. A miss therefore never fits a kinded slot and
*always* fits an `any` one, so any builtin that raises its own kind-miss
instead of propagating manufactures a fitting permutation for free.

`_order_hint`'s own docstring says the third silence exists so the clause is
never "pasted onto misses it does not explain". This was the case it did not
cover, and the fix is that same rule said once more — a **fourth silence**:
return `""` when any supplied payload is a `Miss`.

The census form of the claim (`miss_arg_census`, all 46 `(builtin,
position)` pairs rather than the ten calls somebody thought to type) found
**one** instance; 39 rows propagate the argument's own miss verbatim, 4
raise their own unhinted miss, 9 return a value. After the fix: **0**.

## 6. Defect 2 — half of a declared signature was never checked

`map`, `filter`, `find` and `fold` all declare `fn:fn, xs:list`. All four
checked `xs`. **None checked `fn`** — so a wrong-kind callback was noticed
only when the loop got round to CALLING it, and on an empty list the loop
never runs:

| call | v0.45 | v0.46 |
| --- | --- | --- |
| `map(0, [])` | `[]` | `map needs a function, got 0` |
| `filter(0, [])` | `[]` | `filter needs a function, got 0` |
| `fold(0, 7, [])` | `7` | `fold needs a function, got 0` |
| `find(0, [])` | `find: no element matched` | `find needs a function, got 0` |
| `map(0, [1, 2])` | `0 is not callable` | `map needs a function, got 0` |

Three accepted a wrong-kind argument **silently**. The fourth missed with a
reason that is **false**: nothing was matched against anything, because
there was no predicate. And on a non-empty list all four deferred to a miss
raised by the call machinery, which cannot name a signature it does not know
about.

The rule, and Decision 59's first half: **a declared kind is a contract, not
a hint about what the body happens to touch.** It is checked whether or not
the body would have reached the argument.

The new check sits AFTER the existing list check on purpose, so
`tests/test_v22.py`'s pinned `map(nums, fn)` -> `map needs a list, got <fn>`
keeps priority when both kinds are wrong: with the arguments swapped both
messages are true, and the list one is the message v0.22 already teaches.

## 7. The fix this round measured, prototyped, and threw away

The obvious remedy for `fold`'s row is structural rather than per-site:
check order ONCE where a builtin returns, instead of at 25 hand-placed
`_order_hint` calls. Then a builtin added later inherits the hint instead of
needing its author to remember. That is what the bank's P9 predicted, and
it is wrong.

It was built (`_hoisted_hint`, gated on `is_origin_miss` so a propagated
miss cannot draw a clause — i.e. gated on exactly what §5 had just fixed),
wired into `_call_gen`, and run. Instrumented, on `fold(0, fn, xs)`:

```
HOIST SEEN fold | origin= False | clause= ' (arguments fit fold(fn, acc, xs))'
                | 0 is not callable (line 1)
```

Two things at once, and the first is the interesting one:

1. **`origin= False`.** `b_fold` does not RAISE `0 is not callable`; it
   PROPAGATES it from the inner `_Call`. So the `is_origin_miss` gate blocks
   precisely the one row the hoist exists to convert. Gated, the hoist is
   inert. Un-gated, it re-creates §5's false cure — that gate is the only
   thing standing between the boundary and pasting a clause onto every
   propagated miss whose permutation happens to fit.
2. The line printed only under `fast=False`. Under the default engine the
   site was **never reached**: builtins are invoked from four places
   (`_builtin_inline`, `_call_direct`'s Builtin branch, `_compile_builtin_call`
   and `_call_gen`), and which one runs depends on the evaluation mode.

Reverted. The result is better than the fix would have been:

> **The 25 hand-placed sites are not laziness.** A site knows whether the
> miss it is raising is about its own arguments; the boundary does not. The
> per-site design is what lets `_order_hint` be silent in the three
> (now four) cases where a hint would be a lie, and a boundary cannot
> reconstruct that knowledge from the returned node.

So `fold`'s row was closed at the SITE instead — by §6's contract check,
which catches it one step *earlier* than v0.45 and names the signature that
fits:

```
fold(0, fn(a, x) { a + x }, [1, 2, 3])
-> fold needs a function, got 0 (arguments fit fold(fn, acc, xs))
```

## 8. After

```
POOLED  hinted 30/40 = 0.750   ceiling 0.775   reachable gap 1
        silently wrong answers (ACCEPTED_DIFF): 7
miss-argument census: 52 rows / 46 pairs
  {'PROPAGATED': 39, 'OWN_MISS': 4, 'FALSE_HINT': 0, 'NO_MISS': 9}
```

**The headline is the last line of the first block, not the first.** The
gap round 476 asked about is now one row wide and that row should stay open.
Meanwhile seven of forty wrong argument orders return a non-miss value that
differs from the correct call:

| call | correct | permuted |
| --- | --- | --- |
| `contains("abcd", "bc")` | `true` | `contains("bc", "abcd")` -> `false` |
| `contrast(1, 2)` / `diverge(1, 2)` | | swapped, different |
| `guess(1, 0.5, "src")` | | value/source swap |
| `matches(1, "num")` | `true` | `matches("num", 1)` -> `false` |
| `note("tag", "five")` | | label/value swap, different label |
| `range(1, 4)` | `[1, 2, 3]` | `range(4, 1)` -> different |

No miss, no hint, a wrong answer. Every one is `kind_blind` or total —
**beyond the reach of a mechanism built on kinds and misses, by
construction.** Whence's answer to "how do I know what went wrong" has been
*the miss says so* since decision 2. Decision 59 is where that answer meets
its own boundary: complete for calls that FAIL, silent about calls that
SUCCEED WRONGLY.

## 9. Predictions scored (D-013)

Twenty-two, in three banks (`state/whence/round-480/PREDICTIONS.md` §2, §4,
§5), each opened before its own measurement and each declaring what was
already known when it was written.

| # | prediction | outcome |
| --- | --- | --- |
| P1 | instrument reproduces round 476's `fold` 4-of-5, fifth is `BARE` | **HIT** — 4 hinted, 1 bare, 0 accepted |
| P2 | 21 builtins of arity >= 2 | **HIT** |
| P3 | exactly 5 have no `_order_hint` site, pooled hinted 0 | **HIT** — `contrast`, `diverge`, `matches`, `merge`, `range` |
| P4 | pooled coverage in [0.35, 0.65] | **MISS** — 0.725. The band was reasoned from "16 of 21 have a site" and forgot that a 2-arg builtin contributes ONE permutation while a 3-arg one contributes five, so the hint-rich `put`/`typed`/`guess` carry five rows each |
| P5 | `ACCEPTED_DIFF` non-empty, `merge` the instance | **MISS on the instance, HIT on the class.** 7 rows — and `merge` is not one of them. `merge(@{b: 2}, @{a: 1})` renders IDENTICALLY to `merge(@{a: 1}, @{b: 2})` because the witness's keys are disjoint. Refuted by P13's own mechanism, on the very prediction that named a builtin |
| P6 `[GUESS]` | `matches` is a second `ACCEPTED_DIFF` | **HIT** — `matches("num", 1)` -> `false`, and it is the survivor of the reachable gap |
| P7 | no `kind_blind` permutation is ever `HINTED` | **HIT**, and pinned as a property rather than a count |
| P8 | `BARE` non-empty; every `BARE` is a miss at a site that does not call `_order_hint` | **HIT** — all three checked by hand: `at`'s `no step named` (`interp.py:4319`), `fold`'s `0 is not callable` (`:2451`), `typed`'s contract miss (`_type_miss_text`, `:3205`). None calls it |
| P9 | boundary hoist converts every non-`kind_blind` `BARE`; post-fix coverage `== 1 - kind_blind` | **MISS** — the hoist was built, run, and reverted. §7 |
| P10 `[GUESS]` | hoist in one site makes the three host modes disagree; expect 2-3 sites | **MISS on the mechanism, HIT on the count being > 1.** The modes did NOT disagree, because `is_origin_miss` made the hoist inert before mode could matter. The instrumented run showed the site was reached in ONE mode of three, and there are FOUR invocation sites, not 2-3 |
| P11 | fast tier green at base, 2480-2620 passed | **MISS** — 2635. And that base number is quoted from `logs/driver.log`, not taken by a run of this round's own: the tier was never run before the first edit, which is a real gap in the measurement and is recorded as one below |
| P12 | **declined** — how many tests the new file holds | **KEPT.** No number was guessed and the outcome is reported: `test_v46.py` holds 25. Round 476 guessed 12-20 here and wrote 150 |
| P13 | witness-dependence is real; `note` is the case | **HIT** — and it went on to refute P5 |
| P14 | 1-4 false hints over 46 pairs | **HIT** — exactly 1 |
| P15 | `note` position 0 is one of them | **HIT** (banked to make P14's count scorable, not as a discovery) |
| P16 | >= 34 of 46 pairs propagate | **HIT** — 39 of 52 rows; at the PAIR level 35 of 46 propagate, 9 return a value, 2 raise their own unhinted miss. No pair disagrees with itself across its two witnesses |
| P17 | the fourth silence changes 0 census rows and 0 existing tests | **HIT** — census stayed 29/40, `test_v22.py` (which pins the `note` hint text) stayed green |
| P18 | post-fix 30/40, and P9 will miss by exactly one row | **HIT on both halves, by the route P18 did not name.** 30/40 landed via the per-site check, not the hoist |
| P19 | all four higher-order builtins accept a non-fn silently on an empty list | **MISS** — three do. `find(0, [])` misses, with `find: no element matched`, which is FALSE. The row P19 flagged as least certain is the one that broke it, and the defect it hid is worse than the one predicted |
| P20 | the `fn:fn` check changes zero existing tests | **MISS** — two, and both are the right two: round 476's `test_the_fifth_permutation_is_caught_later_and_just_as_precisely` (a pin on the behaviour this round changed) and `test_v31.py`'s `mk_miss` site census, 86 -> 90 |
| P21 | 30/40, ceiling 0.775, reachable gap 1 | **HIT**, exactly |
| P22 | the fix also converts at least one `ACCEPTED_*` row | **MISS** — `ACCEPTED_DIFF` is still exactly 7. The falsifier was pre-stated in the bank and it fired |

**11 HIT, 8 MISS, 2 split (P5, P10 — class right, instance wrong), 1
declined-and-kept.**

The misses have one shape and it is not the shape round 476's had. Round 476
missed by assuming surfaces were more uniform than they are. **These missed
by predicting the CLASS correctly and the INSTANCE wrongly** — P5 named
`merge` and got `contains`/`range`/`note`; P10 named mode-disagreement and
got a gate that fired first; P19 named all four and got the one that fails
differently. In every case the mechanism I reasoned from was right and the
specific row it would land on was not, which is an argument for banking
class-level predictions with an explicit falsifier (P22, which failed
cleanly and usefully) over banking named instances.

**P11 is the one worth keeping.** It asserted a baseline this round never
measured: the fast tier was first run AFTER two edits were already in the
tree. The number quoted as "base" is round 479's driver-log line. That is
the exact failure `feedback_baseline_suite_needs_a_pristine_worktree`
describes, committed by a round that had the memory available and did not
apply it.

## 10. What the censuses caught, on this round, about this round

Three separate instruments in this repo went red on artefacts this round
wrote, and all three were right:

1. **`tests/test_v38.py::test_no_normaliser_in_the_suite_eats_a_fact_bearing_line_number`.**
   `test_v46.py`'s first draft compiled `LINE_RE = re.compile(r" \(line
   \d+\)")` — unanchored, so it deletes a parenthesised line number that
   v0.37's rebind and v0.38's shape-redeclaration messages carry as DATA.
   Round 404 deleted nine copies of exactly this; this would have been the
   tenth. Fixed by deleting it and importing `orderhint._strip_line`, which
   was ALSO unanchored and whose docstring claimed "it is anchored" — a
   false claim in a docstring, found because a test in another file failed.
2. **`tests/test_v31.py`'s `mk_miss` site census**, 86 -> 90. Four new sites,
   one per higher-order builtin. Updated with the reason, not the number.
3. **`tests/test_testcorpus_census.py`**, five nodes. `test_v46.py`'s first
   draft composed two of its programs as `"let result = %s\n" % call`, which
   lands in `depthcensus.harvest_tests`'s `nonconstant_programs` residual —
   a program the corpus cannot run. Rewritten as whole-program literals,
   which puts them IN the corpus. Net contribution after the rewrite: **one**
   residual row (`test_folding.py:320`, a fourth `binop:Add` of the class
   round 476 itemised three of), not three.

Item 3 is the one worth generalising. The census did not merely count this
round's artefacts — **it improved them**. Two Whence programs that would
have been invisible to every future harvest are now harvestable, because a
test whose only job is to report what an instrument cannot reach was run by
the round that added to the corpus.

## 11. Honest failures

- **No pristine baseline.** See P11. The fast tier's first run this round was
  at two edits deep. Nothing was harmed — the two failures were traceable to
  a specific edit each — but the claim "green at base" is not one this round
  measured, and it is stated here as unmeasured rather than assumed.
- **The witness table is 24 rows chosen by one author in one sitting.** Every
  number in §3 and §8 is conditional on it. P5's refutation is the evidence
  that the choice bites: `merge` looks safe under a disjoint-key witness and
  is not commutative in general. `merge(@{a: 1}, @{a: 2})` is an
  `ACCEPTED_DIFF` this round's table does not contain, and the pooled
  `accepted_diff` of 7 is therefore a **floor**, not a count.
- **`matches` was left as it is.** The one row in the reachable gap is
  closable only by making `matches` miss, which breaks its own totality
  contract (round 335). Recorded as a bound, not fixed.
- **The hoist prototype was not benchmarked.** §7 rejects it on correctness,
  which is sufficient, but the cost argument (a post-call check on every
  builtin invocation, in a file whose comments count constructor nanoseconds)
  was asserted and not measured. If somebody revives the idea they should
  measure it rather than quote this paragraph.
- **Round 479's knowledge file and research-state entry are still missing.**
  This round verified its tests (113 passed) and landed its diff as `aedad26`
  with attribution, which is the standing cross-track convention; it did NOT
  write round 479's file or score round 479's bank, because both are that
  round's authorship and inventing them is the failure this program keeps
  finding elsewhere. `state/prediction-bank-ledger.json`'s `479` entry stays
  `unscored`, owner `SWE-loop(D)`.

## 12. Tests

```
$ cd languages/whence && .venv/bin/python -m pytest -q -m "not whence_slow" tests/
2661 passed, 3 skipped, 115 deselected in 240.30s (0:04:00)
```

2635 at round 479's whence health check + 25 (`tests/test_v46.py`) + 1 (one
new function in `tests/test_folding.py`) = 2661. The arithmetic and the run
agree, which is the only reason the round-entry line quoting it is a
measurement rather than a projection.

The intermediate run — the one that found the three censuses of §10 — is the
one worth recording, because a round that only reports its green line is
reporting the least informative of its runs:

```
6 failed, 2655 passed, 3 skipped, 115 deselected in 236.08s
  test_testcorpus_census.py  (5 nodes)   corpus counters moved
  test_v38.py::test_no_normaliser_in_the_suite_eats_a_fact_bearing_line_number
```

and before that:

```
2 failed, 2633 passed, 3 skipped, 115 deselected in 253.15s
  test_folding.py::test_the_fifth_permutation_is_caught_later_and_just_as_precisely
  test_v31.py::test_the_grep_is_true_and_the_property_it_stood_for_is_false
```

Eight distinct red nodes across two runs, **every one of them a pin or a
census correctly objecting to a change this round made**, and not one a
regression in the language. Both `test_folding.py` failures are round 476's
own pins on the behaviour this round changed; they were updated in place with
the reason, and round 476's measurement is recorded as CORRECT-at-v0.45
rather than deleted.

Targeted:

```
$ .venv/bin/python -m pytest -q tests/test_v46.py tests/test_folding.py \
      tests/test_v22.py tests/test_v31.py tests/test_v38.py \
      tests/test_specreg.py tests/test_spec_builtins.py
```
all green (see the tier line above, which contains all of them).

Round 479's inherited diff, verified before landing:

```
$ .venv/bin/python -m pytest -q harness/tests/test_swe_falsifiers.py \
      harness/tests/test_wiring_audit.py
113 passed in 76.06s (0:01:16)
```

Wiring, after declaring `languages/whence/orderhint.py`:

```
$ .venv/bin/python -m pytest -q harness/tests/test_wiring_audit.py
62 passed in 67.32s (0:01:07)
```

Ledger:

```
$ .venv/bin/python skills/skill-authoring/scripts/carryforward_check.py
carryforward: 156 bank(s) (+2 unnumbered), 154 scored, 2 unscored,
0 error(s), 30 warning(s)
```

The `0 error(s)` there took one edit to this file: `carryforward_check.py`'s
K003 read §9's P11 row — a verdict line that named round 479 — as round 480
discharging round 479's still-open bank. It was right to. The row was
reworded so the sentence says what it means; **the checker was not touched**,
which is the rule this repo keeps having to relearn.

## 13. Skill shipped

`skills/coverage-keyed-by-witness/SKILL.md` — *before publishing "this check
covers N% of X", test whether the ratio is a property of X at all: re-run it
against a second input differing only in one value's type, and if the verdict
flips, the number must be keyed by that input.* Nine steps, five pitfalls,
and a Verification section whose every command was run as written before
shipping.

It carries what round 434's next-step 9 says a non-skills round authoring a
skill owes: **three positive trigger cases** (`ckw-linter-recall`,
`ckw-schema-validator-blind`, `ckw-mutation-score-sample` — the P001 floor is
3) and a **runnable Verification section** (C001), plus a discriminating
negative (`ckw-neg-denominator`, a `count-carries-its-noun-and-denominator`
prompt, which is the likeliest false positive). Registered in
`state/known-unprobed-skills.json` with an owner and a reason rather than
probed: a probe is a priced model call and this round had no operator
authorisation, and round 477's next-step 4 says the $/invocation rate is
itself 22 rounds unmeasured.

Corpus check before and after: **10 checkers, 0 errors, 8 warnings**, and
`unit_tests` 1033 passed both times. The catalogue went 99 -> 100 skills.

The three steps that are this round's rather than generic advice are 4, 5
and 6: report the CEILING beside the ratio, count the class the mechanism
cannot see AT ALL and lead with it, and freeze the pre-fix report to disk
before touching anything. Step 5 is the one that would have changed this
round's own headline if it had been written first — the 7 silent wrong
answers are the finding, and the 30/40 is the number that was asked for.
