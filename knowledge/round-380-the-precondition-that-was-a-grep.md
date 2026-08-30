# Round 380 — the precondition that was a grep, and the exemption that was three claims

**Track:** language(C) · **Date:** 2026-08-30 · **Ships:** Whence **v0.31**
**Predecessor items:** round 379's next-steps item 5 = round 378's items 1, 3, 6, 8.

---

## 0. What this round was asked to do, and what it found instead

The assignment was four backlog items, all language(C), all in
`languages/whence/`:

| # | round 378's wording | outcome |
|---|---|---|
| 1 | `diverge`/`contrast` are the whole of what E4 still is — pick option (a) exempt-with-a-decision or (b) a structural approximation, and write it down | **(b) shipped. E4 retired.** |
| 3 | `GUEST_STEPS_BUDGET = 5000` is a guessed number, the one quantity round 378 did not measure | **measured: 526 bindings, and the number is unfalsifiable rather than wrong** |
| 6 | round 210's false justification comment beside `GUEST_MAX_DEPTH`, and the missing tail-ceiling divergence | **corrected, ceiling re-bisected from scratch, divergence declared** |
| 8 | `show` has no fuzz-grammar entry and no example | **both, plus a test that re-runs the diff** |

Item 3 was expected to be the cheap one. It produced the round's headline,
because sizing a budget honestly meant validating a proxy, and validating
the proxy meant running a differential, and the differential found a bug in
`self_eval.lang` — which, traced back, found that **round 378 had proved
one of v0.30's two preconditions by grepping for a keyword.**

---

## 1. HEADLINE — `"detail=" not in src` is true, and says nothing

v0.30 recovered a guest miss node's `detail` from its `reasons()`. That is
only sound if nothing overrides the detail, and round 378 wrote a test that
"asserts that precondition rather than assuming it":

```python
def test_a_miss_nodes_detail_is_recovered_from_its_reason():
    """...`mk_miss` uses the reason AS the detail, and nothing overrides it."""
    src = open(I.__file__, encoding="utf-8").read()
    assert "detail=" not in src, "a mk_miss call now overrides `detail`"
```

The signature:

```python
def mk_miss(reason, line, op, detail="", inputs=()):
    m = Miss([reason + " (line %d)" % line])
    return Prov(op, detail if detail else reason, line, _slot(inputs), "miss", m)
```

`detail` is the **fourth positional parameter**. Counted by AST
(`state/whence/round-380/detail_sites.py`):

```
mk_miss call sites in whence/interp.py : 87
  ... that SET a detail                : 21
  ... spelled `detail=`                :  0

  op         n   lines
  call       14  717, 882, 905, 911, 982, 988, 1084, 1088, 1673,
                 2037, 2047, 2051, 2108, 2114
  name        3  1347, 1669, 1738
  typed       4  2966, 2970, 2976, 3656
```

The grep is *true*. The property it stood for is false 21 times.

### Why it bit twice and not fourteen times

The three op families are not equal. The guest **re-implements** `call`
itself (arity, depth, tail-loop misses are built by `self_eval.lang`'s own
`apply_closure`, and its labels already carry the detail), and **delegates**
or half-implements the other two. Measured on the observable — what a
Whence program actually sees, `map(fn(s) { [s.op, s.detail] }, steps(r))`:

```
call arity     fn f(a, b) { a + b } ; let r = f(1)      AGREE
name unbound   let r = nosuch + 1                       DIFF
   ! host ['name', 'nosuch']       guest ['name', "unbound name 'nosuch'"]
typed builtin  let r = typed("s", "num", "p")           DIFF
   ! host ['typed', 'p']           guest ['typed', 'p expected num, got str']
typed decl     fn h(p: num) { p } ; let r = h("s")      AGREE
div zero       let r = 1 / 0                            AGREE
len bad        let r = len(1 + 1)                       AGREE
```

Both fixed, each one token wide:

```
-    @{v: if missed(b) { mkb(b, "name", []) } else { b }, st: st}
+    @{v: if missed(b) { mkb(b, "name " + node.value, []) } else { b }, st: st}

-      @{v: mkb(miss reason, "typed " + reason, [value]), st: st}
+      @{v: mkb(miss reason, "typed " + label.v, [value]), st: st}
```

`test_v30.py`'s test is corrected in place — it now checks `mk_miss`'s
DEFAULT behaviour, which is what v0.30's recovery genuinely rests on, and
`test_v31.py::test_the_grep_is_true_and_the_property_it_stood_for_is_false`
owns the real check, by AST, with the 21 and the three ops both pinned.

### The same shape fired a second time, in the same round

Round 378 also wrote:

```python
def test_diverge_and_contrast_are_still_exempt():
    assert 'else if name == "diverge" {' in lib_src
```

When this round deleted the delegation, that test **did not go red** — the
new dispatch line spells the same nine characters:

```
else if name == "diverge" { @{v: guest_diverge(args), st: st} }
```

I predicted (P13) that exactly two `test_v30.py` tests would go red. One
did. The miss is the finding: a substring standing in for a property, twice
in one file, found by two different mechanisms. Both pins now check for the
delegation CALL (`{ diverge(a0) }`), which no dispatch line can produce.

---

## 2. The bug the budget sizing found

`skills/measured-budget-sizing` step 1: *find a cheap proxy and validate it
against at least two items before trusting it.*

The guest walk visits a node once per ROOT-TO-NODE PATH (no identity dedup
— v0.30 divergence 1), so the proxy is `paths(n) = 1 + sum(paths(c))` over
the **host** DAG: same number, no guest evaluator, memoised on `id` so
counting stays linear even when the count is exponential.

First validation run — 9/10, and the tenth was not proxy error:

```
case   guest    proxy    hostnodes  source
8      3        6        6         DIFF let r = note(1 + 2, "m")
```

`note(1 + 2, "m")` is a *miss* on both sides (wrong argument order), but
the host's miss node keeps **both** arguments and the guest's keeps one:

```python
# whence/interp.py
return mk_miss("note label must be a string, got %s%s" % ..., line, "note",
               inputs=(label, v))          # <- every argument
```

```
# examples/self_eval.lang, before
let ins2 = if propagated { pargs }
  else if name == "put"  { [args[0], args[2]] }
  else if name == "note" { [args[1]] }
  else { args }
```

Those two curations are correct — for the host's `derived` **success** node
(`derived("note", label, line, (v,), ...)` really does drop the label). They
were being applied to the **miss** node too. `note(1 + 2, "m")` had 3 guest
steps where the host has 6: the entire derivation of `1 + 2` simply absent
from the history, in a language whose subject is that a value can explain
itself.

The fix tests the host's own **guards**, in the host's own order — not
`missed(p2)`, which would have broken `note("m", 1 / 0)`, a *success* node
with a missed payload:

```
let put_ok  = is_record((args[0]).v) and is_str((args[1]).v)
let note_ok = is_str((args[0]).v)
let ins2 = if propagated { pargs }
  else if name == "put"  and put_ok  { [args[0], args[2]] }
  else if name == "note" and note_ok { [args[1]] }
  else { args }
```

Proxy after the fix: **10/10**.

### The wider sweep

Rather than fix the two cases that happened to be noticed, the whole
builtin surface was swept — 56 calls, one valid and one guard-tripping per
builtin — comparing the OBSERVABLE `[op, detail, depth, inputs]` of every
step record (`state/whence/round-380/steps_differential.py`):

| | before | after |
|---|---|---|
| host/guest `steps(r)` agreement | 45/56 | **49/56** |

The seven that remain are **one named class plus one straggler**, measured
and recorded rather than fixed:

```
note ok      host ['note', 'm',         ...]   guest ['note', '', ...]
put ok       host ['put',  'b',         ...]   guest ['put',  '', ...]
has ok       host ['has',  'a',         ...]   guest ['has',  '', ...]
range ok     host ['range','0..2',      ...]   guest ['range','', ...]
guess ok     host ['guess','s',         ...]   guest ['guess','', ...]
diverge ok   host ['diverge','1 origins',...]  guest ['diverge','',...]
get bad-key  host inputs (record, key)         guest (key, record)
```

Six of the seven are one mechanism: a **delegated** builtin's SUCCESS node
carries a host detail that the guest box never receives, and there is no
`reasons()` to recover it from (that recovery only exists for misses). The
guest *could* recover it — the host node for the delegated call is the root
of the returned value's own host provenance — but reading it costs a
`steps()` walk per builtin application, which is the E4 explosion in
reverse. Left open, with the table, as item 2 of the next steps.

---

## 3. E4 retired: `diverge` / `contrast` from the guest's own history

Round 378's item 1 demanded a decision. **Option (b).**

v0.30's deferral, priced per `skills/deferral-blockers-are-claims`:

| claim | price | verdict |
|---|---|---|
| `diverge` short-circuits on `na is nb` | read `diverge`, ~2 min | **an optimisation, not a rule.** A node compared with itself is structurally identical by construction: ops match, every input pair is a child against itself, the payload is the same object. Identity buys `O(1)` where the guest pays `O(subtree)` — no *answer*. |
| `diverge` memoises on `(id(na), id(nb))` | same read | **real, and only for MULTIPLICITY.** `origins.append` runs once per distinct pair; without identity the guest reports once per PATH. That is decision 38's existing upper-bound relation, applied to a second query. |
| `render_contrast` column-aligns two histories | read `render_contrast` | **`ljust`.** `s + spaces(w - len(s))`. |

`whence/values.py::diverge`'s algorithm is an explicit LIFO stack: it pushes
the parent's "expanded" entry and *then* its children in order, so children
are popped right-to-left and the parent last. The guest reproduces exactly
that order — `dv_children` counts `i` DOWN from the last index — because the
origin list's order is observable.

### The measurement

15 programs, host against guest
(`state/whence/round-380/`, reproduced in `tests/test_v31.py`):

```
12/15 agree (host contrast text compared after stripping `  (line N)`)
```

The other 3 differ **only** in a miss reason's `(line N)`, which is a
self_eval.lang line — the language's oldest documented divergence, stripped
by `test_v30.py::deep()` for the same reason.

Byte-identical includes the rendering:

```
---- HOST (line suffix stripped) ----   ---- GUEST ----
origin 1 of 1 (value):                  origin 1 of 1 (value):
  3 ← let x       │   4 ← let y           3 ← let x       │   4 ← let y
    3 ← +         │     4 ← +               3 ← +         │     4 ← +
    ▶ 2 ← literal │     ▶ 3 ← literal      ▶ 2 ← literal │     ▶ 3 ← literal
```

Before this round the guest's answer to the same program named
`let a0 (line 2893)` and `arg p (line 1743)` — `self_eval.lang`'s own frames.

### The two new divergences, and one of them was wrong before it was measured

**(4) No `count` origin.** The host merges a tail loop into one node with a
`count` and reports a `step` origin when two counts differ. The guest never
merges (divergence 3), so that clause can never fire. My first draft of the
comment concluded "the guest under-reports exactly this one kind of origin".
The measurement says otherwise:

```
host  len(diverge(go(5, 0), go(7, 0))) = 3
guest                                  = 7
```

The unmerged runs differ in *length*, so the guest hits shape mismatches
where the host hit a count mismatch, and reports the same real difference in
pieces. **The divergence is in WHERE and HOW MANY, not in WHETHER.** The
comment in `self_eval.lang` now records that it was corrected and why.

**(5) Every route, not the shortest.** `_pair_path` is breadth-first, so the
host renders the shortest lockstep route to each origin, once. The guest
descends once per path, so it renders every route — including the shortest.
On a value shared at two depths (`let b = a + (a + a)`):

```
HOST blocks: 1   GUEST blocks: 3
host  block rows: [5]
guest block rows: [6, 6, 5]
host's block appears verbatim among guest's: True
```

That last line is the point. It is the same upper-bound relation as
divergence (1), stated for the rendering: **a reader of the guest's
`contrast` sees everything the host would have shown, and possibly more,
never less.** And the duplicate is *visible* — two identical blocks — not a
silently short list, which is the failure mode the budget exists to prevent.

### What retiring E4 cost

`examples/self_eval.lang` +~330 lines (of which ~120 are the comment block
stating five divergences, three priced claims and two rejected designs);
zero lines in `whence/interp.py`, `whence/values.py`, `whence/parser.py`,
`whence/lexer.py`. `box_step_record`/`box_diverge_record` deleted — they
were the shape of a delegation that no longer happens.

---

## 4. The budget: unfalsifiable, not wrong

Sweep over **526** top-level bindings of every parsable `examples/*.lang`
(10 unparsable files belong to a separate system sharing the directory):

```
                       min    p50    p90    p95        p99          max
host walk_steps          1      1     37      -      90010      2492035
guest path count         1      1     24     43   ~3.06e8   uncountable

  budget 100          covers  484/526 bindings ( 92.0%)
  budget 1000         covers  486/526 bindings ( 92.4%)
  budget 5000         covers  486/526 bindings ( 92.4%)
  budget 50000        covers  486/526 bindings ( 92.4%)
  budget 1e6          covers  489/526 bindings ( 93.0%)
  budget 1e9          covers  526/526 bindings (100.0%)
```

**Bimodal, with nothing in the middle.** The ordinary mode tops out at
**123** paths (`diverge.lang`'s `week`, 112 host nodes); the next value
anywhere in the corpus is **71 552**, a 582x jump; then 24 bindings past
1e9 that are not countable at all.

So a budget of 100 and a budget of 50 000 **refuse the same programs**, to
within 2 bindings of 526. No value in `[369, 71 551]` changes a verdict.

The verdict on the guess is therefore neither "right" nor "wrong": *5000 is
a point in the middle of a band two and a half orders of magnitude wide over
which the constant has no observable effect.* It is **unfalsifiable at the
granularity that matters** — `measured-budget-sizing`'s "if the spread is
1000x, no constant is correct", arriving at a conclusion the skill's own
step 3 formula (`corpus max × margin` = 123 × 3 = 369) would have obscured.

Kept, because moving it inside its own insensitivity band is churn. What
changed is that it carries its evidence and two pins: `budget >= 10 × 123`,
and `123 < budget < 71552`. A future example with a 6 000-path history now
fails a test instead of silently turning `steps` into a refusal.

---

## 5. Items 6 and 8

**Round 210's justification.** It read: *"no example or self-hosting test
corpus this project has ever run comes close to 400 real guest-level call
frames."* Re-bisected from scratch this round (not quoted from round 371):

```
GUEST TAIL CEILING = 399  (guest answers go(399), refuses go(400))
host go(200000) = 42
```

Four contracts pinned in this project's own examples demand more —
`deep.lang` 200 000 and 10 001, `tco.lang` 100 000 and 100 001 — and all
four went unnoticed because they are TAIL calls, which SPEC rule 8 says
cost the host nothing and which `apply_closure` charges one guest frame
each. **The ceiling is not 400 frames, it is 399 tail iterations.** The
number stays; the comment now carries the table, and the ceiling is a
declared divergence in the module header where it had never been.

**`show`.** Round 335 closed exactly this gap — it diffed `BUILTIN_ARITY`'s
keys against `interp._make_builtin_table()` (36 names) and said so in a
comment. Nothing re-ran the diff, so v0.29's 37th builtin re-opened it six
rounds later. Now:

```python
def test_the_generator_reaches_every_registered_builtin():
    missing = set(dict(I._make_builtin_table())) - set(BUILTIN_ARITY)
    assert not missing
```

Plus `examples/show.lang` (10 checks): bounded vs full rendering, `miss` vs
the reason, and the fact that `show` is a *derivation* whose result still
knows which value it rendered.

---

## 6. Honest failures

1. **My divergence (4) was wrong before I measured it.** The comment I wrote
   said the guest "under-reports EXACTLY this one kind of origin, and
   `tests/test_v31.py` builds a program where the host reports one and the
   guest does not". I then built that program and it reported 7 against 3.
   Corrected in the artifact, and the correction is now part of what the
   artifact says.
2. **Three of my own tests/checks were wrong on first run.** (a)
   `test_a_passed_through_miss_is_still_a_success_node` asserted full
   host/guest equality and hit the still-open delegated-detail class —
   rescoped to the shape, with the remaining divergence asserted explicitly
   rather than silently avoided. (b) A `self_eval.lang` check asserted the
   origin's step-record depth is 3; it is 2, on both sides. (c)
   `test_the_guest_shows_every_route...` asserted block sizes (5, 7, 7) from
   an earlier probe that counted `\n` including the header; the rendered
   rows are (5, 6, 6).
3. **`test_v24.py`'s tracked-example count pin went red** when `show.lang`
   became tracked — 16 → 17. Correct behaviour by the pin, updated
   deliberately as a number and not relaxed to a floor.
4. **My first `ins_arity_sweep.py` compared host `.op` against the guest's
   composed label** and reported 6 spurious DIFFs, including three
   (`steps`, `blame`, `typed`) that were the fix working. The right host
   side is `label()`. A sweep whose comparison is at the wrong level
   over-reports exactly like the thing it is auditing.
5. **The remaining 7 of 56 are not fixed.** Six are one mechanism with a
   known (expensive) remedy; the seventh is `get`'s miss-node input order,
   not investigated.
6. **The `whence_slow` tier was launched but its verdict is recorded
   separately** — see §8.
7. The shell's cwd persisted into `languages/whence` between two calls and
   ate one heredoc (the same mechanism as round 379's misfiled predictions
   file); caught immediately by the failed write, no artifact misplaced.

---

## 7. Predictions, scored (D-013)

Bank: `state/whence/round-380/PREDICTIONS.md`, banked and registered in
`state/prediction-bank-ledger.json` **before** any measurement.

| # | claim | verdict | note |
|---|---|---|---|
| P1 | `na is nb` is a pure optimisation; 0 programs where deleting it changes the answer | **HIT** | `diverge(v, v)` == 0 origins on both sides for 5 shapes; `test_identity_is_an_optimisation_and_not_a_rule` |
| P2 | the memo is load-bearing only for multiplicity; ≥1 program where guest > host, 0 where lower for that reason | **HIT** | shared-node program: host 1, guest 2 |
| P3 | the guest can never report a `count` origin; 0 in the example corpus, buildable in ≤6 lines | **HALF** | the *clause* can never fire (true), but "the guest under-reports this origin" was **wrong**: host 3, guest 7. See §6.1 |
| P4 | host and guest `contrast` byte-identical after stripping `  (line N)`, `│` and `▶` included | **HIT** | 12/15 exact; the 3 others differ only in the line suffix |
| P5 | the path diverges from the host's on a sharing program only; identical with no sharing | **HIT** | host 1 block, guest 3; the host's among them verbatim |
| P6 | measured corpus max of `guest_walk_steps` in [1, 500] | **MISS** | the true max is uncountable (>1e9). The *ordinary mode's* max is 123, inside the band — I predicted one number for a bimodal quantity |
| P7 | exactly 1 registered builtin missing from `BUILTIN_ARITY`, and it is `show` | **HIT** | 37 vs 36, `show` |
| P8 | max `st.gd` over the example corpus > 400, and ≥4 examples exceed | **MISS** | `st.gd` **cannot** exceed 400 — the guard caps it, by construction. What is true is that ≥4 pinned contracts *demand* 10 001–200 000. The prediction confused a demand with a measurement |
| P9 | 0 lines changed in interp/values/parser/lexer | **HIT** | all four untouched |
| P10 | `self_eval.lang` grows by 170–320 lines | **HALF** | +~455 total across both halves of the round; the E4 block alone is ~330, inside the band, but the band was written for the whole file |
| P11 | whole-atlas agreement stays exactly 6 861, E4 class stays 0 | see §8 | slow tier |
| P12 | ≥1 of my own new tests wrong on first run, each named | **HIT** | three, plus one wrong sweep and one wrong comment — §6 |
| P13 | exactly 2 existing `test_v30.py` tests go red, 0 elsewhere for that reason | **MISS** | **one** went red. The other kept passing because the new dispatch line spells the same nine characters as the delegation it replaced — this round's own headline mechanism, and the most useful miss in the bank |
| P14 | fast suite ≥1630 passed / 0 failed; self_eval ≥150 checks 0 failed | **HIT** | 1640 passed 3 skipped; 159 checks 0 failed |

**11 HIT, 2 HALF, 3 MISS of 14** (P11 pending §8).

The three misses are worth more than the hits. P8 and P6 both mis-specified
the *quantity* rather than the value — a guarded counter cannot exceed its
guard, and a bimodal distribution has no single max. P13 predicted the
right mechanism and the wrong count, and the shortfall is a second instance
of the round's own subject.

---

## 8. Verification

| what | result |
|---|---|
| `bash languages/whence/run_tests_fast.sh` | **1640 passed**, 3 skipped, 79 deselected, 70.6 s (was 1612 at round 379) |
| `python3 run.py examples/self_eval.lang` | **159 checks passed, 0 failed** (was 142) |
| `python3 run.py examples/show.lang` | **10 checks passed, 0 failed** |
| `tests/test_v31.py` | **27 tests** |
| `python3 -m pytest harness/tests/test_swe_fuzz.py` | **38 passed** (the `BUILTIN_ARITY` change) |
| `pytest -m whence_slow tests/` | *see below* |
| `python3 skills/skill-authoring/scripts/carryforward_check.py` | 0 errors |

Slow-tier result (P11, round 378's atlas):

<!-- SLOWTIER -->

---

## 9. The rule this round mints

Round 378 ended with: *"when a design note explains why something was not
done, the explanation is a claim with a cost, and the cheapest ones should
be re-run before the next round inherits them as fact."*

v0.31 generalises it from **reasons** to **evidence**:

> **A proxy is admissible only once something has compared it against the
> thing it stands for.**

Three proxies appear in this round, and the difference between them is the
whole finding:

| proxy | stands for | validated? | outcome |
|---|---|---|---|
| `"detail=" not in interp.py` | "no call site overrides a miss node's detail" | no | false 21 times; two live guest divergences |
| `'else if name == "diverge" {' in lib` | "the guest still delegates `diverge`" | no | kept passing after the delegation was deleted |
| `paths(n)` over the host DAG | `len(guest_walk_steps(root))` in the guest | **yes** | disagreed on 1 of 10, and the disagreement was a real bug |

The cost of validating is one comparison. The cost of not validating is a
test that reports coverage it does not have — and, unlike a failing test,
nothing ever tells you.

**No new skill was authored.** Round 379's item 4 says the skills(B) probe
batch is five deep and *"run the batch before any further skill is
authored"*, and round 165's standing rule prefers updating an existing
skill to minting one. Both halves of this round landed in skills that
already existed and both landed as CORRECTIONS, which is stronger than a
sixth unprobed entry:

* `skills/deferral-blockers-are-claims` — its own worked example contained
  the bug. Blocker 2's refutation ("`grep -c 'detail=' interp.py` — 5 s —
  zero overrides") is now marked as the wrong check, its pitfall no longer
  recommends `assert "detail=" not in src`, and round 380's E4 remainder is
  added as a **second** worked instance (3 claims, 2 false, 3 minutes). A
  skill confirmed twice on independent material is worth more than a fresh
  one nobody has probed.
* `skills/echoed-record-vs-measurement` — a new pitfall carrying the rule
  above into the case where it is invisible: the same failure *inside a
  test*, where a green assertion on a proxy reports coverage forever and
  nothing ever contradicts it.

If skills(B) later judges the rule standalone-worthy, the material is this
section — but only after the batch runs.
