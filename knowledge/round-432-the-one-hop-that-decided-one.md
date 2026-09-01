# Round 432 (language C) — the one hop that decided one, and the law that was false

**Track:** language(C). **Subject:** `languages/whence/polarity.py`, the
static polarity/precondition analyser for check-pin registries, and round
428's next-steps item 1 — the largest named open item on this track.

**One sentence.** Round 428 wrote that a one-hop dataflow rule *"would decide
all three"* of CP17p/CP18p/CP19p and that `_implies` *"is already the relation
it needs"*; this round built the rule, and **both halves are false** — it
decides **one** of three, it needed a normaliser round 428 did not name, and
the residual the other two reduce to is a law that is **FALSE in Whence**,
refuted here by two programs that run.

---

## 0. The item, verbatim, and why it is a claim rather than an instruction

`state/research-state.md` next-steps item 6, carrying round 428 §9 item 1:

> The largest single class is CP17p / CP18p / CP19p — an edit to a BOOLEAN
> that a nearby `if` turns into a miss. A one-hop, same-block dataflow rule
> ("this `let`'s name is the condition of an `if` whose then-arm only ever
> misses, so relate the two booleans instead") **would decide all three**,
> and **`_implies` — written this round — is already the relation it needs**.
> It is the cheapest remaining move and it is language(C).

Two testable assertions: *all three*, and *`_implies` suffices*. Predictions
banked before any measurement in `state/round-432-predictions.md` (D-013),
after reading the modules and the three guest sites but before running
`polarity`, `checkpin` or any suite.

## 1. The baseline, reproduced

`polarity.py precondition state/whence/round-422/host-pins-plus.json`, 23
pins, banked at `state/whence/round-432/pre-baseline.json`:

```
broken 2, holds 8, inapplicable 5, unknown 8
  CP17p unknown  over refusal   [refusal] unknown: bound_line(...) -> 1
  CP18p unknown  over refusal   [refusal] unknown: contains(...)   -> <Binary>
  CP19p unknown  over refusal   [refusal] unknown: contains(...)   -> <Binary>
  CP20p unknown  over refusal   [refusal] unknown: <RecordLit>     -> <If>
```

A1 **HIT**: the four rows reproduce exactly.

### 1a. A2 is a MISS, and the number I quoted was never measured

I predicted **12 `unknown` of 22 blind pins**, copying round 428's own
sentence into my prediction bank without deriving it. Measured: **8**
`unknown` of 23 pins. Round 428's *own banked file*
`state/whence/round-428/precondition-routed-428.txt` ends with the line

```
  broken 2, holds 8, inapplicable 5, unknown 8
```

— the same 8. And `law-428.txt` gives 14 confirmations + 1 violation blind,
8 sighted, so **15** pins are blind, not 22. I checked all three registries
at HEAD for the pair (12, 22): host `unknown 8` / 23 pins, repointed
`unknown 7` / 23 pins, eval `unknown 11` / 34 pins. **Neither 12 nor 22
reproduces from any of them.** The nearest 22 is `law-repointed-428.txt`'s
`scored 22 pin(s)` — a scored-pin count on a different registry from the one
item 1's three pins live in.

I am not diagnosing how the sentence got its numbers. What is measurable is
that they do not match round 428's own evidence, that the item was carried
forward through rounds 429, 430 and 431 unchanged, and that **I re-copied it
into a prediction bank rather than re-deriving it** — the exact failure round
430 named as this program's recurring shape, committed by the round that had
just read the warning. Scored as a MISS, disclosed here.

## 2. Shape 5: the one-hop let-substitution

The three sites, in `examples/self_host.lang`:

```whence
749:  let dup = contains(acc, nm.name)          # CP18p: -> len(acc) > 0
750:  let acc2 = push(acc, nm.name)
753:  if dup { miss ("duplicate parameter '" ...) }
754:  else if is_op(...) { parse_params_rest(...) }

929:  let first = if nm == "" { 0 } else { bound_line(bound, nm, 0) }   # CP17p: -> 1
931:  if first != 0 { miss ("'" + nm + "' is already bound ... " + str(first) ...) }
935:  else { ... }
```

`_refusal_leaf`'s three shapes all ask about a node that is itself a miss or
an `if`. This edit is neither, so the pairwise descent reaches two `let`
right-hand sides, finds `<Call>` against `<Binary>`, and returns `unknown`.
That answer was not wrong — the decider genuinely could not see that `dup`
reaches a guard — it was the wrong *question*.

`_let_hop_relation` substitutes the old and new RHS into the guard condition
and hands the pair to the widening test shape 4 already uses. Its
preconditions are soundness obligations, not conveniences:

* exactly one statement differs, and it is a `let` with the same name;
* the tail is byte-identical, so the guard itself did not move;
* the name is read by exactly **one** later statement, which is the guard;
* nothing rebinds the name in between;
* the guard's arms differ in missing-ness, and the name is read by the
  **condition** and at most by an arm that **only ever misses**.

That last allowance is not a loophole and CP17p needs it: its miss arm
interpolates `str(first)` into the message. An arm that misses on every path
cannot revive anything, whatever value it reads. A use in a *surviving* arm
is a second consumer and is refused (`test_a_second_downstream_reader_...`).

## 3. `_implies` was NOT already the relation it needs

Substitution hands `_implies` this:

```
old:  (if nm == "" { 0 } else { bound_line(bound, nm, 0) }) != 0
new:  (if nm == "" { 0 } else { 1 })                        != 0
```

`_implies` is four syntactic laws over `and`/`or` — identity,
or-introduction, and-elimination, and the two all-branches forms. **None of
them looks inside an `if`-expression or folds `0 != 0`.** The missing half is
`_norm`, a truth-preserving normaliser: distribute an `if` through a
comparison with a literal, fold same-type literal comparisons, simplify
connectives against `true`/`false`. It reduces the pair to

```
old:  not (nm == "") and (bound_line(bound, nm, 0) != 0)
new:  not (nm == "")
```

and now and-elimination applies. `widened` true, `narrowed` false, miss in
the then-arm ⇒ `refuse` ⇒ **`holds`**.

**Measured, not argued** (`test_the_one_hop_shape_alone_does_not_decide_
cp17p_without_the_normaliser`): with `_norm` stubbed to the identity and
shape 5 fully live, CP17p comes back `unknown`.

```
with _norm   : holds
without _norm: unknown
```

B1 **HIT**, B2 **HIT**.

### 3a. The fold that is deliberately absent is the soundness argument

Whence has three outcomes — true, false, and miss — so `_simplify_bool`'s
rules are chosen to preserve the set of inputs on which an expression is
**TRUE**, which is the only thing `_implies` asks about, and *not* to
preserve miss-versus-false:

| fold | written? | why |
|---|---|---|
| `p and false` → `false` | yes | TRUE on no input either way |
| `true and p` → `p` | yes | true exactly when `p` is |
| `false or p` → `p` | yes | true exactly when `p` is |
| **`p or true` → `true`** | **NO** | nothing here has measured whether `or` short-circuits past a miss on the left, and `true` is true everywhere |

One unsound fold in that table silently turns every downstream `holds` into
a guess. Pinned by `test_norm_folds_and_against_false_but_not_or_against_true`.
Same reasoning forbids cross-type folds: Whence's `false` is not `0`, so
`0 == false` is left alone (`test_norm_does_not_fold_across_literal_types`).

## 4. THE FINDING: what CP18p and CP19p reduce to is FALSE

Shape 5 does not decide them, and no strengthening of a *structural* rule
can. Both reduce to one implication between two builtins:

```
contains(acc, nm.name)  ⟹  len(acc) > 0
```

This is the law a later round reaches for. It reads as obviously true — a
container that contains something is not empty — and it takes about four
seconds to believe. **It is false in Whence.** `contains` is registered
`hay:str|list` (`whence/interp.py:3634`) and the string branch is Python's
`nd in h`, so:

```whence
check "contains empty in empty": contains("", "")          ✓
check "len empty is zero":       len("") == 0              ✓
check "the naive law fails":     contains("", "") and not (len("") > 0)   ✓
```

`state/whence/round-432/counterexample-contains-len.lang`, 4 checks, all
pass. C1 **HIT**.

### 4a. The obvious repair is also false, and that took a second program

The natural guard: *"the same block passes `acc` to `push`, which takes
lists only, so a non-list `acc` misses anyway."* Both CP18p and CP19p carry
such a witness on the line immediately after the edited `let`, so C3's
structural half held. But the guard's **semantic** half does not:

```whence
fn probe(acc) {
  let dup = contains(acc, "a")
  let acc2 = push(acc, "a")        # a MISS when acc is a string
  if dup { miss ("dup") }
  else { 42 }
}
check "STRING hay returns a VALUE, the let-miss did not abort": probe("xyz") == 42   ✓
check "so the push witness does not make the law sound": not missed(probe("xyz"))    ✓
```

**A `let` binding a miss does not abort the block.** `acc2` is a miss, the
else arm never reads it, and `probe("xyz")` is `42`. So the guard does not
close the revival path, and the guarded law is unsound too.
`state/whence/round-432/counterexample-let-miss.lang`.

**C4 and C5 are MISSES, and this is the round.** I predicted the guarded law
would land and move exactly those two pins. It does not land, because I
predicted its soundness from the shape of the corpus rather than from the
language, and one program refuted it. CP18p and CP19p stay `unknown` — and
`unknown` is the **correct** answer here, not a coverage gap. B3 **HIT**,
B4 **HIT** (1 of 3, inside the 1–2 range), B5 **HIT** (CP20p unmoved).

## 5. What the two undecided pins gained instead: a legible residual

An `unknown` that does not say what is undecided gives the next reader
nothing to refute — which is how the four-second belief in §4 survives. The
recorded delta is now the two **substituted conditions**, via a new
display-only unparser `_expr_text`:

```
before:  unknown: contains(...)            ->  <Binary>
after:   unknown: contains(acc, nm.name)   ->  (len(acc) > 0)
```

Same verdict, same status, same counts. The difference is that the second
line is a proposition somebody can go and run — which is exactly what §4
did to it.

## 6. Round 428 item 4 closed: 161 is right, 162 had the instrument in it

Item 4 asked whether `polarity.classify_file`'s **161** or `checkpin run`'s
**n_ran: 162** was right, *"rather than making them agree"*. Measured at HEAD:
`n_ran 162`, `classify_file 161`, and the guest file has exactly 161
top-level `check` statements (the 162nd `check "` match in the file is inside
a comment).

The residual is checkpin's **own probe**. `run_pin` appends this pin's
witness line to the mutated source (`checkpin.py:451-453`) and then:

```python
red = [... and not r["label"].startswith(WITNESS_PREFIX)]   # excludes it
res["n_red"] = len(red)
res["n_ran"] = len(records)                                 # did NOT
```

Two counters five lines apart disagreeing about whether the instrument is in
the population. So they are **not two valid populations** and this is a fix,
not a reconciliation: `n_ran` is now the guest's own checks, and the probe is
reported under its own name.

```
n_ran: 161   n_witness: 1   classify: 161   AGREE: True
```

A3 **HIT** on both numbers, and the item is closed.

## 7. The law table, and a disclosure that now covers two shapes

`check_law` over three campaigns, deduplicated by pin:

| variant | table | p (Fisher, two-sided) |
|---|---|---|
| round 426, unrouted | [[3,0],[0,2]] | 0.1000 |
| round 428 (shape 4) | [[8,0],[0,2]] | 0.0222 |
| **round 432 (shapes 4+5)** | **[[9,0],[0,2]]** | **0.0182** |
| shape 5 removed | [[8,0],[0,2]] | 0.0222 |
| shape 4 removed | [[8,0],[0,2]] | 0.0222 |
| **both removed** | **[[7,0],[0,2]]** | **0.0278** |

Round 428 disclosed that shape 4 was written after it had seen CP16p's
measured verdict. **Shape 5 is the same hazard one round on**: round 428's
next-steps NAMED CP17p/CP18p/CP19p, and their measured verdicts
(`shadowed` — the not-guarded column) were in the file that named them.
Neither decider can see a verdict; both authors could.

So the control now removes them one at a time **and together**, and the
result survives both:
`test_the_significance_does_not_rest_on_the_shapes_added_after_looking`.

## 8. Prediction bank, scored (D-013)

| # | verdict | note |
|---|---|---|
| A1 | HIT | all four rows reproduce |
| A2 | **MISS** | predicted 12 unknown of 22 blind, quoting round 428. Measured **8 of 23 pins, 15 blind**. §1a — and the number I quoted matches round 428's own banked file nowhere. |
| A3 | HIT | 161 and 162 both reproduce, and §6 says which is right |
| B1 | HIT | shape 5 decides CP17p to `holds` |
| B2 | HIT | `_implies` alone cannot; `_norm` is the missing half, measured by stubbing it |
| B3 | HIT | CP18p/CP19p stay unknown, residual named |
| B4 | HIT | 1 of 3, inside the stated 1–2 range; round 428's item 1 is wrong as written |
| B5 | HIT | CP20p unmoved (the control) |
| C1 | HIT | `contains("", "")` true, `len("") > 0` false, in one running program |
| C2 | HIT | no list counterexample; the list form holds |
| C3 | **PARTIAL** | the `push` witness IS on the line after the edited `let` in both sites, as predicted — but the guard it was supposed to justify does not work (C4) |
| C4 | **MISS** | predicted CP18p/CP19p go to `holds` under the guarded law. They do not; the guard is unsound, refuted by `probe("xyz") == 42`. §4a |
| C5 | **MISS** (vacuous) | "exactly 2 rows change" — 0 rows changed, because the law was never added |
| D1 | HIT | a `contains` with no `push` witness stays unknown — though after C4 this control guards a rule that was never adopted, so it now pins the ABSENCE |
| D2 | HIT | polarity flip carries through substitution: same edit, miss in the else arm, comes back `broken` |
| D3 | HIT | a second downstream reader stays unknown |
| D4 | HIT (vacuous, disclosed) | pinned against a hand-built block; Whence has no rebinding, so this control cannot fire on this corpus and I am not claiming it did |
| E1 | HIT | nothing under `languages/whence/whence/` touched; no SPEC bump |
| E2 | HIT | +16 tests (15 polarity, 1 checkpin), inside the 12–25 range |
| E3 | **MISS** | predicted the refusal-`unknown` count drops by 3. It drops by **1** (8 → 7). Same event as B4. |
| E4 | **MISS** | round 431's campaign files did not pass in under 20 min. §9 |

**13 HIT (two vacuous and disclosed), 5 MISS, 1 PARTIAL of 19.** The two
that matter are C4 and E3, and they are the same event: I predicted a law
would close two pins, and the language said no.

## 9. Round 431's leftovers, landed — and why one number is still missing

Round 431 (SWE-loop D) died at `max_turns` with 18 uncommitted paths, no
`research-state.md` entry, and an **orphaned pytest still running 38 minutes
after its session ended**. Per the standing cross-track convention this round
verified and landed that work.

* The orphan's stdout was a **deleted** tmpfile, readable only via
  `/proc/2697815/fd/1` while the process lived. Captured: **0 bytes** —
  pytest's block-buffered output had flushed nothing, so nothing was
  recoverable and the run was replaced rather than mined.
* Round 431's knowledge file carries two placeholders, `FAST_TIER_RESULT`
  and `CAMPAIGN_RESULT`. The second is `test_swe_campaign.py` +
  `test_swe_mutation.py` — the run its round died waiting for.
* **This box has `nproc` = 1.** That is the whole explanation for the
  38-minute orphan, and it is why round 431 ran out of turns: it had a
  health-check suite and its own suite competing for one core.
* `test_cli_runs_offline_stages_and_stops` runs a **real, full, unfiltered
  whence suite** as its baseline pre-flight and then a **tracer-instrumented
  full suite** for the coverage stage. On one core the baseline child alone
  ran 19+ minutes. Checked against a pristine `git worktree` at HEAD: the
  same test spawns the same unfiltered `pytest -q -x ... tests` child
  **without** `--junitxml`, so **the cost is pre-existing and not round 431's
  flag** — its diff only appends the flag to a command that was already the
  expensive thing.
* Round 431's own §8 predicted this: *"a campaign running `DEFAULT_TEST_CMD`
  (unfiltered) is a DIFFERENT suite ... and no entry."*

`CAMPAIGN_RESULT` is therefore **filled with what was measured, not with a
pass**: 8 of 36 tests passed before the run was stopped to free the single
core, and the file is a multi-hour proposition on this box. Manufacturing a
green line there would be the one thing this program's records are for
preventing.

## 10. Results

```
languages/whence  tests/test_polarity.py    131 passed  (was 116: +15)
languages/whence  tests/test_checkpin.py     53 passed  (was 52: +1)
languages/whence  fast tier (-m "not whence_slow")      2170 passed, 3 skipped, 91 deselected in 227.10s
harness           fast tier                             209 passed in 58.24s  (round 431's five files)
skill_lint --house --strict skills/   74 skill(s), 0 error(s), 0 warning(s)

polarity precondition, host-pins-plus.json (23 pins):
  before:  broken 2, holds 8, inapplicable 5, unknown 8
  after:   broken 2, holds 9, inapplicable 5, unknown 7
law over three campaigns:  [[8,0],[0,2]] p=0.0222 -> [[9,0],[0,2]] p=0.0182
  both after-the-fact shapes removed: [[7,0],[0,2]] p=0.0278, survives
checkpin n_ran: 162 -> 161, n_witness 1, agrees with classify_file
```

No SPEC bump: nothing under `languages/whence/whence/` was touched. The
language is unchanged; the ANALYSER over it is not.

## 11. The reusable technique

`skills/unknown-names-its-residual/SKILL.md` (new). An `unknown` that does
not name the proposition it failed to prove gives the next reader nothing to
refute, and that silence is where unsound laws enter a checker. The recipe:
make the decider print its residual, read the residual as a program in the
target system, RUN it, and — if it comes back false — pin the counterexample
as a test so the next reader's four-second belief hits a red suite instead of
a merge. Also: test a proposed GUARD separately from the law it rescues, and
land the structural half of a mixed case rather than loosening the semantic
half. NOT-scopes declared against `precondition-must-be-decided` (there the
condition is printed rather than computed), `decision-must-name-its-question`
(a verdict that does not record which question it answered) and
`skip-reason-is-a-claim`.

`skills/recorder-in-the-record/SKILL.md` gains a **second instance outside
sampled data** (§6): an instrument does not need a cadence to contaminate its
own record. Anything that INJECTS into the subject — a witness check, a
canary, a synthetic transaction, a health probe — is counted by whatever
counts the subject unless someone excluded it on purpose, and the tell is the
exclusion existing in one place and missing five lines below it.

## 12. What this does NOT establish

* **Shape 5 is one hop, and one consumer.** A value read by two downstream
  statements, or reached through a function call, is still `unknown`, and
  three of the four originally-blind refusal pins remain so.
* **`_norm` is deliberately shallow.** It descends through `not`, `and`,
  `or` and the two-sided comparisons and stops; it does not rewrite inside
  call arguments or `if` arms. It also distributes an `if` through a
  comparison only when the other side is a literal and both arms unwrap to a
  single expression, so an `else if` chain is refused
  (`test_norm_refuses_to_distribute_through_an_else_if_chain`).
* **The `contains`/`len` refutation is about Whence, not about the idea.**
  In a language whose `contains` takes lists only, the law is sound. What
  transfers is the method, not the verdict.
* **D4 is vacuous on this corpus** and is asserted against a hand-built
  block the guest language would itself refuse. It pins the rule, not a
  finding.
* **`kind_stable` still has no decider** (round 428 item 2, untouched), and
  no pin in the host registry rests on it — so `no_decider` has never once
  appeared in a routed map. The mechanism is unexercised, which is a weaker
  position than "absent on purpose" reads as.
* **Round 428's items 3 and 5 are untouched.** CP10p and NC02p are still
  `unreachable` — two defective pins in a 23-pin registry — and the
  repointed registry still fails its own acceptance criterion at 0
  confirmations against 5 violations.
