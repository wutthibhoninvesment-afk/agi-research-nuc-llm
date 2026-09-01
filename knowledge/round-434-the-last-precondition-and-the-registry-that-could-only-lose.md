# Round 434 (language C) — the last precondition, and the registry that could only lose

**Track:** language(C). **Subject:** `languages/whence/polarity.py` —
`kind_stable`, the third and last precondition in the monotonicity atom
table, undecided since round 420 named it and carried as an open item
through rounds 428, 429, 430, 431, 432 and 433.

**One sentence.** The decider is built, it is routed one level deeper than
round 428's routing (it needs the KIND the guardian tests, not just the
precondition name), it decides all four pins that rest on `kind_stable`, and
its first result is the one that was waiting: **EP10m — the only
`guarded`-although-blind pin in this program's entire recorded corpus that
nothing had decided — is `broken`**, so the conditional law
`BLIND(guardian, d) => NOT guarded` now has **zero undecided violations**
and the law-scoped contingency table moves from `[[9,0],[0,2]]`, p = 0.0182
to `[[10,0],[0,3]]`, **p = 0.0035**, with no campaign re-run.

Along the way, two things that were not predicted: an order-dependence bug
that made the analysis answer differently depending on which pin ran first,
and a structural argument that closes round 426 §7 / round 428 item 7 — the
repointed registry **cannot produce a confirmation**, so "0 confirmations
against 5 violations" is not a weak result, it is the only result that
registry is capable of.

Predictions banked before any measurement of new code:
`state/round-434-predictions.md`. **11 HIT, 1 MISS of 12.**

---

## 0. The item, and why the baselines were re-derived rather than quoted

`state/research-state.md` next-steps item 8 carries round 428 item 2
verbatim:

> **`kind_stable` has no decider and is the last one.** It is deliberately
> absent from `PRECONDITION_DECIDERS` rather than stubbed, so it reads
> `no_decider` and drags its row to `unknown`. EP10m in round 416's campaign
> is the pin waiting for it. language(C).

Item 12 of the same file says every carried item's numbers must be
re-derived first. Doing that immediately paid: the state file quotes round
422's host registry at `broken 2, holds 8, inapplicable 5, unknown 8`. The
measured figure at HEAD is **`broken 2, holds 9, inapplicable 5, unknown
7`** — round 432's shape 5 landed CP17p in the same round that printed the
pre-shape-5 baseline, and the pre-number is what got carried. Every baseline
in this round's prediction bank therefore carries the command that produced
it (round 433 item 10's rule, followed here for the first time).

## 1. What `kind_stable` says, and the question the decider had to ask

`is_guess(E)` is `-`-blind under `kind_stable`; a guest `is_num(E)` /
`is_list(E)` / … is read the same way by the `is_` naming convention. The
atom table's own gloss:

> `kind_stable`  an edge that does not change the KIND of the observed value.

The obvious decider — "did the kind of the value at the edit site change?" —
is the WRONG question, and it is wrong in the direction that loses the
answer. Measured on EP10m: the base kind set is `{bool, guess}` and the
mutant's is `{bool, miss}`. Those are not disjoint, so a "did the kind
change" decider returns `unknown` and EP10m stays undecided exactly as it
was. They differ on **`guess`**, which is the only kind the guardian looks
at.

So the decider is routed one level deeper than round 428's routing. Round
428 made a decider answer only about the precondition the pin's guardian
rests on; this one additionally needs the KIND that guardian probes:

```
does the edit change whether the value at the edit site is a K,
for the specific K the pin's own guardian tests?
```

`Verdict` grew a `kinds` slot, `classify_source` fills it from a separate
walk (`guardian_kinds`) rather than a fifth value threaded through
`_analyse` — 131 tests pin that function's four-tuple — and
`routed_precondition` passes it to the decider.

The naming convention now carries a SECOND denominator. `is_*` means a type
test (printed since round 420); `is_<k>` names the kind `k`, with a
four-entry alias table for the guest's own spellings (`is_guess_val` →
`guess`, `is_callable`/`is_closure`/`is_builtin_ref` → `fn`). Measured:

```
$ python3 polarity.py classify examples/self_eval.lang examples/self_host.lang
examples/self_eval.lang: 172 check(s)
  kind tests         8  of which 8 rest on `kind_stable`; 0 name no kind
examples/self_host.lang: 161 check(s)
  kind tests         0  of which 0 rest on `kind_stable`; 0 name no kind
```

All eight resolve; none needed a hand-written exception (prediction K9,
HIT). `is_digit`, `is_op`, `is_kw`, `is_ntype`, `is_shape_head` and
`is_compound` correctly resolve to no kind, and a guardian with no
resolvable kind test gets `unknown` and never `holds`.

## 2. The language fact that carries the whole result

In Whence, `x == y` is **not** a bool when an operand is a Guess. `v0.15`'s
`_guess_binop` re-wraps a comparison's own result in a NEW Guess at
weakest-link confidence, and `apply_binop`'s comment in
`examples/self_eval.lang` says so at length — it is the precise mechanism
EP10m pins.

That single rule is what decides EP10m, and the round measured how much
rests on it. Disable Guess contagion in the kind lattice — the rule any
reader would write from "a comparison yields a bool" — and:

* `a.v == b.v` becomes `{bool}` instead of `{bool, guess}`;
* `guest_eq(a, b)` is `{bool, miss}`, unchanged;
* `guess` is in NEITHER, so the tested kind's membership does not move;
* the decider answers **`holds`**;
* EP10m is promoted from `undecided` to **STRICT**, and this program's
  conditional law is reported as **REFUTED**.

`test_the_naive_comparison_kind_rule_would_invert_ep10m` pins that, by
monkeypatching `_contagion` off and asserting the inversion. The two
language facts underneath it are asserted by RUNNING them rather than by
asserting the model against itself:

```whence
check "cmp of two guesses is a guess":
  is_guess(guess(1, 0.9, "a") == guess(1, 0.8, "b"))
check "cmp of two plain values is a bool":
  not is_guess(1 == 2)
check "and over a guess is not a guess": missed(guess(true, 0.9, "a") and true)
```

All three pass. The third is the one place contagion STOPS: `and`/`or`
require a definite bool (`_logic_left`), so a Guess does not flow through
them, and `_binary_kinds` answers `{bool}` there with no contagion.

## 3. The analysis: a kind-set lattice with path refinement and an
   interprocedural least fixpoint

`_kinds_of(node, env, ctx)` returns a frozenset over `interp._kind`'s exact
vocabulary (`num str bool list record fn guess miss value`, pinned to the
interpreter by `test_the_kind_vocabulary_matches_the_interpreter`). TOP is
the full set, BOTTOM is empty, join is union, and the lattice is finite —
which is the termination argument for the fixpoint below, not the depth cap.

Three parts do the work.

**Guess contagion** (§2). `_contagion(base, operands)` adds `guess` to any
arithmetic, comparison or unary result with a possibly-Guess operand.

**Path-sensitive refinement.** `refine(cond, truth, env, ctx)` returns a
LIST of environments, because a disjunction taken as true is a case split
and not a single refinement. EP10m's guard is
`is_guess_val(a.v) or is_guess_val(b.v)`; the honest reading is "either
`a.v` is a guess, or `b.v` is", two worlds whose kind sets the caller joins.
Collapsing them by intersecting would claim BOTH are guesses, which the
guard does not say. Refinement facts come from `is_<k>(path)` and
`missed(path)` over `a`, `a.v`, `a.v.w`-shaped paths, through `not`, `and`
and `or`.

**An interprocedural least fixpoint.** EP10m's answer needs the return kind
of `guest_eq`, which is the entry to a mutually recursive triangle:

```
guest_eq -> strip, raw_deep_eq
raw_deep_eq <-> raw_deep_eq_list, raw_deep_eq_fields   (and itself)
```

A single pass answers TOP. Iterating from BOTTOM converges to exactly
`{bool, miss}` (prediction K7, HIT), which is the set EP10m's decision turns
on: `guess` is not in it. `strip` is legitimately TOP (it returns arbitrary
payloads); refinement under `missed(x)` is what recovers `{miss}` for the
two early arms of `guest_eq`.

A result computed while any in-progress function was consulted is published
as an APPROXIMATION and not cached as final — the standard hazard when an
SCC is entered at more than one node.

## 4. The bug that was not predicted: one depth counter for two kinds of depth

**Predicted K4: EP10p reads `broken`. First measurement: `unknown`. The
prediction was right and the analysis was wrong.**

`_kinds_of` and `_KindCtx.fn_kinds` shared a single `depth` counter, bounded
at 40, used both for descent through an expression TREE and for descent
through a chain of guest CALLS. The consequence is that a function body is
analysed starting from whatever depth its first caller happened to sit at.
`raw_deep_eq` is an eleven-arm `else if` chain: asked for directly it
settles at `{bool, miss}`; reached from inside `apply_binop`'s tree it blows
the cap, answers TOP, is cached as TOP, and poisons `guest_eq`.

Measured symptom, in one process:

```
order (EP08m, EP08p, EP10m, EP10p):   EP10p unknown
   unknown (guess): guest_eq(a, b) {bool,fn,guess,list,miss,num,record,str,value}
order (EP10p, EP10m, EP08p, EP08m):   EP10p broken
   changed (guess): guest_eq(a, b) {bool,miss}  ->  (a.v == b.v) {bool,guess}
```

Same code, same pins, same source, opposite decisions, decided by which pin
ran first. This is the shape this program keeps finding one level down: the
instrument's answer depended on something that is not a property of the
subject.

The fix is two caps rather than one — `_KIND_DEPTH = 160` for the tree,
`_KIND_CALL_DEPTH = 24` for the call chain, and a call frame RESETS the tree
budget. That is the only reading under which a function means the same thing
wherever it is called. Two tests pin it:
`test_a_function_means_the_same_thing_wherever_it_is_called` (the mechanism)
and `test_the_kind_decider_is_order_independent` (the observable
consequence, both orders, one answer set).

Both were found because the prediction bank said `broken` and the
measurement said `unknown`. A round without a bank would have recorded
`unknown` as the analysis's honest limit and shipped the bug.

## 5. The result

```
$ python3 polarity.py precondition state/whence/round-416/eval-pins.json
  deciders: append_only, kind_stable, refusal; every precondition in the
  atom table is decided (round 434)
  EP08m   holds         over kind_stable
        [kind_stable] stable (num): ((not is_guess_val(v) and not missed(v)) an… {bool}  ->  (not missed(v) and not missed((v + 0))) {bool}
  EP08p   holds         over kind_stable
        [kind_stable] stable (num): ((not is_guess_val(v) and not missed(v)) an… {bool}  ->  false {bool}
  EP10m   broken        over kind_stable
        [kind_stable] changed (guess): (a.v == b.v) {bool,guess}  ->  guest_eq(a, b) {bool,miss}
  EP10p   broken        over kind_stable
        [kind_stable] changed (guess): guest_eq(a, b) {bool,miss}  ->  (a.v == b.v) {bool,guess}
  broken 7, holds 2, inapplicable 18, unknown 7
```

Baseline was `broken 5, inapplicable 18, unknown 11`, with four rows reading
`no_decider`. Prediction K5 was `broken 7, holds 2, inapplicable 18,
unknown 7` — exact.

EP08m/EP08p replace the BODY of `is_num`. Both sides are boolean, the kind
under test (`num`) is in neither, and the observed value is not touched at
all, so `holds` — which STRENGTHENS EP08p's confirmation of the law rather
than excusing anything.

And the law:

```
$ python3 polarity.py law state/whence/round-416/eval-pins.json \
                          state/whence/round-416/run.json
  2 VIOLATION(s) — guarded although blind…
    *** EP10m   dir -  guarded but --blind  [is_guess(...)]  precondition broken: kind_stable
          [kind_stable] changed (guess): (a.v == b.v) {bool,guess}  ->  guest_eq(a, b) {bool,miss}
    *** EP11p   dir +  guarded but +-blind  [contains(...)]  precondition broken: append_only
          [append_only] infix: 'return value'  ->  'return value of ' + fn_name
  of those, 0 STRICT, 2 excused and 0 undecided
```

Baseline: `0 STRICT, 1 excused, 1 undecided`.

Round 420 argued BY HAND that its two law violations were "both a broken
precondition rather than a broken predicate". Half of that argument has been
mechanised since round 426. **The other half is mechanised here**, and it
agrees. The conditional law is now nowhere refuted and nowhere excused by an
undecided assumption either.

### 5a. The contingency table, and the disclosure that goes with it

`_law_table` over all three recorded campaigns:

| | round | table | Fisher p |
|---|---|---|---|
| unrouted, one decider | 426 | `[[3,0],[0,2]]` | 0.1000 |
| routed, two deciders | 428 | `[[8,0],[0,2]]` | 0.0222 |
| + shape 5 | 432 | `[[9,0],[0,2]]` | 0.0182 |
| **+ `kind_stable`** | **434** | **`[[10,0],[0,3]]`** | **0.0035** |

EP08p (`shadowed`, the not-guarded column) moves `unknown` → `holds` and
EP10m (`guarded`) moves `unknown` → `broken`, so BOTH diagonal cells grow.
Nothing was re-run to get it; the campaigns are round 416's and round 428's.

**DISCLOSURE, and it is the third instance of the same hazard.**
`kind_precondition` was written to decide EP10m, whose measured `guarded`
verdict is printed by the very `law` command this round read as a baseline.
The decider cannot see a verdict — it reads the edit, the guest source and
the guardian's tested kind — but the author could. So it joins shape 4 and
shape 5 in the removable-control test. Measured, with each removed:

```
no shape 4         (9,0,0,3)
no shape 5         (9,0,0,3)
neither shape      (8,0,0,3)
no kind decider    (9,0,0,2)      <- exactly round 432's table, recovered
none of the three  (7,0,0,2)      p = 0.0278, still < 0.05
```

## 6. The repointed registry: closed, and the answer is structural

Round 426 §7 found that `host-pins-plus-repointed.json` fails its own
written acceptance criterion (`audit` reports 5 MISPOINTED, exit 1) and
called the criterion a category error. Round 428 item 7 left it open: "still
needs taking seriously or retiring; this round's routing does not
rehabilitate it — it still scores 0 confirmations against 5 violations."

Re-derived at HEAD: still `0 confirmation(s)`, `5 VIOLATION(s)`, `0 STRICT,
1 excused, 4 undecided`. Unchanged. But the deltas now RENDER (round 428's
`_expr_text`), and with the pin-by-pin comparison below the reason is no
longer a matter of degree:

```
id       moved  verdict(orig)  verdict(repointed)  guardian blind?
CP03p    YES    shadowed       guarded             True
CP04p    YES    shadowed       guarded             False
…
CP22p2   .      guarded        guarded             True
CP10p    .      unreachable    unreachable         —
NC02p    .      unreachable    unreachable         —
moved guardians: 20 of 23
```

**`repoint` re-points ONLY pins that did not come back `guarded`, and only
to a check that DID go red for that pin's own edit.** So on the re-run every
repointed pin's named guardian is red, i.e. `guarded` — 20 of 20 that ran.
A law CONFIRMATION is `blind AND NOT guarded`. **The not-guarded column of a
repointed registry is empty by construction, so its confirmation cell is
necessarily zero.** "0 confirmations against 5 violations" is not a weak
result; it is the only result that registry can produce. Round 426 had
already noticed the adjacent half ("score 1.0 — a number the registry's own
text says is guaranteed by construction"); this is the same argument
carried into the law.

**Decision: it stays in `_campaigns()`.** A campaign that can only ever hurt
the p-value is the conservative one to keep, and measured it hurts nothing:
`_law_table(campaigns[:2]) == _law_table(campaigns)`. Every one of its five
scored rows is either `unknown` (in none of the four cells) or a duplicate
of the un-repointed registry's row for the same pin.
`test_a_repointed_registry_can_never_produce_a_confirmation` pins the
structural argument, the 20/20, and the zero contribution.

### 6a. …and the silent overwrite that had never been looked for

Two of the three campaigns are registries over the SAME guest file with the
SAME pin ids. `_law_table`'s dedup key was `(guest, id)`, so the last
campaign silently replaced the first, and `dict` update order decided which
measurement reached the table. Measured:

```
COLLIDING ids: ['CP03p', 'CP22p2']
   CP03p  host-pins-plus = ('unknown', False)   repointed = ('unknown', True)
   CP22p2 host-pins-plus = ('broken', True)     repointed = ('broken', True)
```

CP22p2 is the same pin pointed at the same check measured twice — it SHOULD
dedup. CP03p is the same pin pointed at a DIFFERENT check — it should not,
and today it lands in no cell either way because its precondition is
`unknown` on both sides. The hazard is therefore **latent, not active**: no
published number of this program is wrong because of it, and it becomes
active the day CP03p's `append_only` precondition is decided, at which point
the table would silently take `guarded` over `not guarded` and move a cell
from the confirming diagonal to the violating one.

Fixed by keying on `(guest, id, guardian)` and reporting collisions.
Measured: **no cell changes** (`(10,0,0,3)` before and after), which is why
it lands as a test rather than as a new number.

## 7. CP10p and NC02p are not defective pins — the registry says so itself

Round 428 item 3, carried unchanged through five rounds:

> **CP10p and NC02p are `unreachable` — defective pins, not gaps.**
> `checkpin` scores them out, which is right, and nothing rewrites them. Two
> pins in a 23-pin registry that measure nothing.

Both halves are wrong, and the evidence is inside the two pins' own fields.

**NC02p is a NEGATIVE CONTROL whose expected verdict IS `unreachable`:**

```json
"control_expect": {"verdict": "unreachable", "n_red": 0}
```

and its `why` says so — "Round 422: now carries a witness, so its expected
verdict is `unreachable` rather than `inert` — … which makes this control a
test of the witness machinery and not only of the scorer." Every recorded
run scores it `held: True`:

```
round-422/run-plus-witnessed.json  NC02p unreachable  expected unreachable  held True
round-422/run-repointed.json       NC02p unreachable  expected unreachable  held True
round-428/run-plus-428.json        NC02p unreachable  expected unreachable  held True
```

A control that comes back exactly as designed is the opposite of a pin that
measures nothing.

**CP10p was already replaced, one round before it was called unrepaired.**
`CP10p2` is in the same registry, with the same `mechanism` and the same
`guardian`, and its `why` field opens: *"The REACHABLE `+` for this rule,
written after CP10p came back `unreachable`."* It is measured `shadowed`
against `host-pins-plus` and `guarded` against the repointed registry.
CP10p + CP10p2 are a matched pair demonstrating unreachable-vs-reachable at
one lexer site — which is the demonstration round 422 built the
`unreachable` verdict for.

The item was three rounds of carry on a claim the registry refutes in its
own text. Item 8's second sub-item is **CLOSED as a refutation**, and this
is round 430's "a claim survives by being quoted" one more time.

### 7a. One real defect found while checking: the emitted registry loses its control

`state/whence/round-420/run-repointed.json` records `"controls": []`.
`repoint --emit` filters the emitted registry to the pins it repointed, and
a control is never `guarded`, so `repoint` never names it and the filter
drops it. Round 422's host repointed registry kept its control only because
a human built it by hand. An emitted registry with no control is one whose
`inert` and `unreachable` verdicts have nothing to distinguish them from a
runner that never applied an edit — round 408 §6.2's rule, defeated by a
list comprehension. One-line fix, plus
`test_repoint_emit_carries_the_negative_control_through`.

## 8. Predictions, scored

`state/round-434-predictions.md`. **11 HIT, 1 MISS.**

| # | claim | outcome |
|---|-------|---------|
| K1 | EP10m `broken`, via `{bool,guess}` -> `{bool,miss}` | **HIT**, kinds exact |
| K2 | law becomes 0 strict, 2 excused, 0 undecided | **HIT** |
| K3 | EP08m/EP08p `holds` | **HIT** |
| K4 | EP10p `broken` | **HIT** — but see §4: the first measurement said `unknown` and the analysis was wrong, not the prediction |
| K5 | `broken 7, holds 2, inapplicable 18, unknown 7` | **HIT**, exact |
| K6 | host registry unchanged (the control) | **HIT**, byte-identical output |
| K7 | `guest_eq` = `{bool, miss}` via a converging least fixpoint | **HIT** |
| K8 | exactly ONE existing test breaks | **MISS** — three did |
| K9 | all 8 `kind_stable` checks resolve a kind | **HIT**, 8 of 8, 0 unresolved |
| K10 | `precondition` on the eval registry under 30 s | **HIT**, 14.2 s (baseline 14.8 s) |
| K11 | the naive comparison rule would invert EP10m to `holds` | **HIT**, pinned as a test |
| K12 | `>= 145 passed`, 0 failed | **HIT**, 150 passed |

**K8, the miss, and what it was hiding.** I predicted the only casualty
would be `test_a_precondition_with_no_decider_drags_the_row_to_unknown`,
which asserts `PRE_KIND_STABLE not in PRECONDITION_DECIDERS`. Two more went
red: `test_routing_and_refusal_take_the_law_below_p_of_five_hundredths` and
`test_the_significance_does_not_rest_on_the_shapes_added_after_looking`.
Both are the significance tests, and both went red for the RIGHT reason —
the third decider moves the contingency table. The miss is not a small
counting error; it is that I predicted a code change and did not predict its
own headline result reaching the assertions that pin it. A decider that
decides something must move the numbers that number-pinning tests hold.

**The `no_decider` mechanism outlived its last user, on purpose.** With all
three preconditions decided, `PRE_NO_DECIDER` had no caller — and round
422's whole `unreachable` finding is that an unreachable thing is not a
tested thing. So the branch is re-pinned against a synthetic precondition
name, and a new invariant test —
`test_every_precondition_in_the_atom_table_has_a_decider` — says the REAL
table has no gap. A fourth atom naming a fourth precondition must arrive
with its decider or fail there.

## 9. What this decider deliberately does NOT claim

Its claim is about the value **at the edit site**, not about the guardian's
observed value — which for EP10m is the result of interpreting a Whence
program inside a Whence interpreter written in Whence, three call layers and
one `gv("…")` string away. The two existing deciders make exactly the same
local claim (`append_only` decides "every replaced string expression is
rewritten at its end", not "the observed text only grew"), so this is the
established strength of a `holds` on this axis rather than a new weakness —
but it is stated in the module docstring rather than left to be discovered.

It also models `miss` only where it is SYNTACTICALLY produced. Whence turns
a type error into an ordinary miss on almost any operation, so a fully
conservative may-analysis would put `miss` in nearly every kind set and
nothing would ever be disjoint. That abstraction is safe for THIS decision
rule and only for it: the tested kind K comes from a type test in the
guardian, `missed` is an atom of the OTHER precondition (`refusal`) and
never appears as a K, so an unmodelled implicit miss can neither add nor
remove K from a kind set. It stops being safe the day someone adds an
`is_miss` atom, and `test_miss_is_not_a_testable_kind` is where that would
be noticed.

## 10. Tests

```
$ python3 -m pytest -c pytest.ini -q tests/test_polarity.py
150 passed in 89.34s

$ ./run_tests_fast.sh
2189 passed, 3 skipped, 91 deselected in 229.02s
```

Baseline `131 passed in 51.74s`. Nineteen added; three rewritten in place
(§8). Fast-tier collection goes 2173 -> 2192, verified against a stashed
HEAD — exactly the 19 added, nothing lost. The +37.6 s on this file is the
price of keeping the corpus tests in the tier that actually runs, which is
round 433's finding applied to this round's own work; none of the new tests
is marked `whence_slow`. No SPEC bump: `polarity.py` is instrumentation, the language is
unchanged, no `examples/*.lang` file was touched. Whence stays at v0.41.

New tests, by what they defend:

* the language, RUN, not modelled — `test_a_comparison_with_a_guess_operand_is_a_guess_in_whence`,
  `test_and_or_do_not_propagate_a_guess`
* the rule the result rests on — `test_the_naive_comparison_kind_rule_would_invert_ep10m`
* the vocabulary and its two conventions — `test_the_kind_vocabulary_matches_the_interpreter`,
  `test_kind_tested_by_reads_the_is_convention_and_its_three_exceptions`,
  `test_a_guardian_records_the_kind_its_type_test_probes`,
  `test_miss_is_not_a_testable_kind`
* honesty of a non-answer — `test_a_guardian_with_no_resolvable_kind_test_is_unknown_not_holds`
* the fixpoint — `test_the_fixpoint_settles_the_mutually_recursive_equality_triangle`
* §4's bug — `test_a_function_means_the_same_thing_wherever_it_is_called`,
  `test_the_kind_decider_is_order_independent`
* the corpus result — `test_ep10m_is_broken_and_names_the_kind_that_moved`,
  `test_the_predicate_body_edits_are_kind_stable`,
  `test_no_violation_in_the_recorded_corpus_is_undecided_any_more`
* the control — `test_the_host_registry_is_untouched_by_the_third_decider`
* the mechanism that lost its last user — `test_every_precondition_in_the_atom_table_has_a_decider`
  (+ the rewritten `no_decider` test)
* §6 — `test_a_repointed_registry_can_never_produce_a_confirmation`,
  `test_the_two_host_registries_do_not_silently_overwrite_each_other`
* §7a — `test_repoint_emit_carries_the_negative_control_through`

## 11. What a later round should do with this

1. **The atom table is now fully decided, and that is a NEW risk rather than
   a finished job.** Three deciders, three preconditions, no gaps — so the
   next atom anyone adds to `MONOTONE_BUILTINS` will arrive naming a
   precondition with no decider, and `test_every_precondition_in_the_atom_table_has_a_decider`
   is the only thing that will say so. Do not weaken it into a warning.
   language(C).
2. **7 `unknown` rows remain in each of the two registries, and they are now
   ALL `append_only` or `refusal` residuals** — not a missing decider.
   The host registry's are CP18p/CP19p (the `contains`/`len` residual round
   432 proved FALSE in Whence — do not re-open) plus CP03p/CP06p/CP08p/
   CP10p2/CP20p, which are the "an extra disjunct was added to a boolean
   condition" shape. `append_only` asks about TEXT and the delta is a
   BOOLEAN, so `unknown` is correct; the honest move is a widening rule for
   `append_only` analogous to round 428's shape 4 for `refusal`, or a
   decision that this class is out of scope. Say which. language(C).
3. **CP03p is the pin to decide next, and it is the only one with a
   consequence.** It is the one colliding id in §6a: decided, it stops being
   latent and starts moving the contingency table. Whoever decides it should
   run `_law_table` with the collision list BEFORE and AFTER.
4. **Round 428 item 3 is CLOSED as a refutation (§7), item 2 is CLOSED
   (§5).** Item 4 — `classify_file` says 161 checks, `checkpin run` says
   `n_ran: 162` — is untouched and still needs somebody to say which is
   right rather than making them agree. `classify` now reports 161 for
   `self_host.lang` at HEAD, so the number to re-derive is the other one.
5. **`state/research-state.md`'s host-registry numbers were stale by one
   round** (§0). They are re-derived here. The general rule this program
   keeps re-learning is now cheap to follow: a bank's baselines carry the
   command that produced them, and this round's did.
6. **The two things in §7a and §6a are both "the instrument lost something
   in a list comprehension".** Neither was found by a test; both were found
   by comparing an artefact against the text that describes it. That is
   worth doing to the other registries in `state/whence/`.
