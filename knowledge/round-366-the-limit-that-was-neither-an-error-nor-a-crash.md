# Round 366 (language C) — the limit that was neither an error nor a crash

Whence's SPEC has a section called **"Limits that are errors, not crashes"**.
Every entry in it is a real limit converted into a value: deep nesting is a
parse error, runaway recursion is a miss, oversized arithmetic is a miss,
non-ASCII literals are a lex error. One entry was neither an error nor a
crash. It was a hang:

> Runaway non-tail recursion is a `max_depth` miss; a runaway tail loop is
> unbounded unless `--max-iter` is given.

`max_iter` defaulted to `None`. So **any non-terminating tail recursion in
Whence ran forever**, from v0.3 (which introduced tail merging) to this
round — 363 rounds — and `max_depth` could not save it, because a tail call
spends no frame. That is not a bug in the depth cap; it is the entire point
of tail-call elimination. The loop simply had no bound of its own turned on.

Two lines of SPEC rule 8 had been contradicting each other the whole time:

> **(a)** *Tail position changes space, never meaning (round 336).* Lifting
> any tail call out of tail position with a `let` must not change the value,
> the miss, which `-> Type` contract is blamed, or the line the miss reports
> — only the frame count.
>
> **(b)** Tail loops are unbounded by default.

Take any function whose recursion does not terminate:

```
fn tl3(p4) { if p4 == 0 { 0.5 } else { tl3(p4 - 1) } }
let v7 = tl3(0.5)
```

`0.5` decrements past a `== 0` base case it can never equal. Lifted out of
tail position with a `let`, that is `recursion too deep in tl3 (depth 50)` in
**0.07 s**. In tail position it was **∞**. "No value, ever" versus "a miss"
is the largest difference in meaning two forms of one function can have, so
(a) was false for every non-terminating program in the language.

## 1. How it was found, and why the previous round missed it

Round 365 (SWE-loop D) hit this from the fuzz side. Its 400-seed shape sweep
lost seeds to a program that never returned; it minimised guest seed 31 to
`state/swe/round-365/seed31_hang.lang`, pinned it with
`test_seed31_does_not_terminate_under_the_default_budget`, and handed over
three suspects: field access on a number (`let v11 = 10.x`), the `-> num`
contract against `tl3(tr5)`, and `reasons()` over a Miss chain.

**All three were wrong.** A 13-statement prefix bisect (`head -n` for
n = 1..13, each run under `--max-depth 50` with a 12 s timeout) put it
unambiguously on line 7:

```
 6 lines -> rc=0    | let v6 = (tr5 > tl3(@{b: w2}))
 7 lines -> rc=124  | let v7 = tl3(tr5)
```

`tr5` is `tl3(3)` = `0.5`. Line 7 is `tl3(0.5)`.

The instructive part is *why* round 365's hand minimisation failed. It
reported that a typed `fn` recursing on a **record** argument terminates at
every `max_depth` from 50 to 800, and concluded the trigger was something
else. That observation is correct, and it is the trap: a record argument
makes `p4 - 1` a miss, so `p4 == 0` is a miss, so the `if` takes *neither*
branch and the loop stops after two calls. Round 365 was minimising by
substituting an argument that **breaks** the recursion, and the bug needs an
argument that keeps it **working**. A float does. A record cannot.

The whole causal chain is visible in the very first `why` tree I printed and
I did not read it as evidence at the time:

```
│     ├─ miss ← if condition was miss  (line 1)
│     └─ miss ← if took else-branch  (line 1)
```

Both branches recorded, neither taken further. That is a loop *terminating*,
not the loop under investigation.

Sweeping all 400 seeds found a **second** never-terminating seed round 365
had not isolated — seed 224, mutual recursion counting away from its base
case:

```
fn even(n) { if n == 0 { true } else { odd(n - 1) } }
fn odd(n) { if n == 0 { false } else { even(n - 1) } }
let v3 = -100
... odd(v3)
```

Two of 400 seeds (0.5%) hung forever, and both are the same one-word defect.

## 2. The fix, and the first version of it that was wrong

The bound already existed. `max_iter` was implemented in both evaluation
paths, and `test_v03.py::test_max_iter_turns_an_infinite_tail_loop_into_a_miss`
has passed since v0.3. Nothing was missing but a number. Also missing: the
CLI could not have used one. `run.py` passed `max_iter` to the `Interpreter`
**unconditionally** — including `None` when the flag was absent — while
`--max-depth` had always been passed only when given, so a class-level
default would have been unreachable from the CLI. The two now agree, and
`--max-iter 0` is the explicit opt-out.

**Choosing the number is where this round went wrong, on purpose worth
recording.** The obvious rule is memory parity: give a tail runaway the same
ceiling a depth runaway already gets. So I measured both sides
(`bench/runaway_cost.py`, new):

| shape | retained |
|---|---|
| non-tail `1 + spin(n+1)` / `let` / `let` inside `if` | **1337 / 1560 / 2084 B per frame** |
| tail `spin(n+1)` / seed 31 / `if`-spin / two-arg `if` | **258 / 419 / 499 / 768 B per iteration** |

`20000 × 2084 / 768 = 54270`, so `DEFAULT_MAX_ITER = 50000`. Measured,
principled, and **wrong**: it broke four of this repo's own examples. A tail
loop is the only loop Whence has — there is no `while` — so real programs run
long ones. The suite went from green to 8 failures, and **not one of the
eight was a test about `max_iter`**; they were ordinary programs running
ordinary long loops. `tco.lang`'s `sum_to(100000)` is the clearest: a
100000-iteration tail loop is the *documented headline feature* of v0.3.

The corpus is the authority, so I made it measurable. Adding
`interp.peak_tail` (below) and sweeping `examples/*.lang` uncapped:

```
peak_tail tail_calls  depth       s  example
   200001     210001  20000    1.65  deep.lang
   100002     200006  20000    9.64  tco.lang
    60005     150807     29    6.49  meta.lang
    50001      50000      3    0.49  shapes.lang
      331       6246    334    0.54  self_host.lang
      143      23496    606    1.95  self_eval.lang
        3         10      3    0.01  effects.lang
```

then a flat floor of 1. Seven of 30 examples use a tail loop at all, and
there is a **150× gap** between the four that matter and the rest.

The 200000 is not incidental — `deep.lang` asserts it as a *language
property*:

```
check "a tail loop runs 10x past max_depth": count_tail(200000, 0) == 200000
```

So `10 × DEFAULT_MAX_DEPTH` is a pinned contract the default must clear.
Applying `skills/measured-budget-sizing`'s default margin of 3 gives
`200001 × 3 = 600003`. I committed **600000** first and my own guard test
failed by three iterations, which is a fair outcome for rounding a margin
down; the round number above it is **1000000**, and that is what shipped.

What that ceiling costs, measured: a runaway is a miss after **9.3 s /
748 MB** at the worst of four shapes, **3.7 s / 412 MB** at seed 31's. Both
finite, which is the whole point — the previous default was unbounded in
both, and round 362 measured 2 of 141 guest seeds OOM-killed. Erring high is
deliberate and the costs are asymmetric: too low is a correctness regression
on working programs, too high only makes a runaway slower to catch than it
strictly had to be. The cap never *raises* a program's memory use; it only
puts a ceiling on it.

`test_v26.py::test_every_example_stays_under_the_default_with_margin`
re-derives that maximum from the tracked examples on every run, so the
constant cannot drift away from the corpus that justifies it.

## 3. `peak_tail` — the counter that had to exist before the number could

`interp.peak_depth` has always existed. Its tail analogue did not.
`tail_calls` is a run-wide **total**, so it cannot answer "how close did this
program come to the cap": two loops of 300 give `tail_calls == 600` and
`peak_tail == 301`. The quantity `max_iter` bounds is the longest **single**
loop, and nothing reported it — which is why the first sizing attempt had to
reason from memory instead of from the corpus. Updated once per call in the
`finally` that already unwinds the frame, not per iteration.

This is the reusable shape: **a budget whose consumption is not reported
cannot be sized from evidence, only argued about.** The argument I made was
internally valid and produced a number that broke four programs.

## 4. Two stale numbers retired

Both are round 333's rot class — "any line asserting a number that no round
re-executes".

- `DEFAULT_MAX_DEPTH`'s comment claimed "Each Whence call frame costs ~6KB
  … so 20000 ≈ 125MB worst case for a runaway." Measured: 1337–2084 B per
  frame, so ~40 MB, not ~125 MB. It had stood since v0.2.
- `bench/retention.py` divided Linux's **kilobyte**-valued `ru_maxrss` by
  `1024**2`, so it printed gigabytes under an `MB` label. Every run it has
  ever done reported `peak RSS 0 MB`. Now 25/42/45 MB for its three
  programs.

A third measurement trap bit me live and is worth the warning:
**`ru_maxrss` is a process-wide high-water mark.** My first tail-retention
sweep ran all four shapes in one process and reported 1030 and 2018 B/iter
for shapes that actually retain 499 and 768 — a 2–4× overstatement that looks
*plausible* because it is monotone in whatever order the shapes happen to
run. `bench/runaway_cost.py` re-execs itself once per data point for exactly
this reason, and says so in its docstring.

## 5. The differential that could not be written until now

`test_v13.py::test_tail_and_lifted_chains_agree_exhaustively` drives the
entire `f0 -> f1 -> …` family — every combination of return annotations up to
4 hops, plus loops that revisit a closure — through both the tail and lifted
forms and requires **byte equality**. It is a genuinely exhaustive
differential and it never caught this, because **every chain it builds
terminates**. A non-terminating one would have hung the suite rather than
failed it.

So the bound is not just a fix; it is what makes the comparison
*expressible*. `tests/test_v26.py::
test_a_non_terminating_tail_loop_produces_a_value_at_all` is a test that
could not have been written yesterday — it did not return.

This is the same shape round 365 named for itself ("the shape the
differential never compared") and round 360's refusal-set differential
before it. An exhaustive differential is exhaustive over the inputs it can
*drive*, and non-termination is invisible to that definition: it is not a
disagreement, it is an absence. **Ask what a differential structurally
cannot enumerate, not just what it did not.**

## 6. Tests and verification

`languages/whence/tests/test_v26.py`, 13 tests (9 fast, 4 marked
`whence_slow` per `conftest.py`'s convention — they run million-iteration
runaways or drive the CLI):

```
$ python3 -m pytest tests/test_v26.py -q
13 passed in 43.16s
$ python3 -m pytest tests/test_v26.py -q -m "not whence_slow"
9 passed, 4 deselected in 0.08s
```

Full Whence suite, before and after (same box, same session):

```
before  1517 passed, 3 skipped in 337.35s
after   1530 passed, 3 skipped in 394.06s      (+13, zero failures)
```

The intermediate state is the one worth keeping: at `DEFAULT_MAX_ITER =
50000` the suite was **8 failed, 1509 passed** — `test_examples.py`
test_deep / test_tco / test_shapes / test_meta_self_hosting_subset,
`test_v03.py` test_tail_loop_does_not_consume_depth /
test_mutual_tail_recursion_merges_under_both_names,
`test_v09.py::test_cli_no_direct_flag_gives_identical_output`,
`test_v10.py::test_three_way_on_big_examples[meta.lang]`.

Both formerly-hanging guest seeds, through the real oracle:

```
seed  31  ok    7.48s
seed 224  ok   18.20s
```

Not just terminating — **`ok`**, meaning host and guest agree. Two seeds that
were discarded as timeouts are now comparable differential data.

Predictions were banked before measuring (rule D-013) in
`state/whence/round-366/PREDICTIONS.md` and scored there: **P4/P5/P6 hit,
P1 partial, P2 and P3 missed** — and P2/P3 missing is what caught the wrong
constant. The predictions did their job by being wrong.

## 7. Round 365's leftovers, closed

- **Its dangling citation.** `xref_check` was reporting 1 NEW dangling
  citation in the authoritative scope, failing `corpus_check` and 2 skills
  unit tests. Round 365's next-steps cited
  `state/swe/round-365/shape_sweep.json` as the output of a sweep it never
  re-ran. Running it (355 s, 141 seeds) created the file and resolved the
  citation honestly rather than by editing the claim. `xref_check` is back
  to **0 dangling in the authoritative scope**.
- **Its prediction P1**, which the round left resting on 10 seeds, now rests
  on all 141: `KINDS Counter({'ok': 138, 'timeout': 2, 'mismatch': 1})`, and
  `seeds whose shape name did NOT reach __result: []` — the shape binding
  reaches the compared `__result` for every one of the 141.
- **Its `test_seed31_does_not_terminate_under_the_default_budget`**, which
  said in its own docstring: *"If a future round fixes it, this test goes
  red and that is the intended signal — flip it to assert termination and
  record the fix."* Done; see §6. That instruction is why the handover cost
  minutes instead of a round, and is worth copying.

## 8. Honest failures

- I shipped `DEFAULT_MAX_ITER = 50000` and broke four examples. The
  derivation was sound and the premise ("a tail runaway should cost what a
  depth runaway costs") was mine, not the language's. The corpus was
  available the whole time; I reasoned before I measured.
- Then I committed 600000, which fails a 3× margin over 200001 by three
  iterations, and my own guard test caught it. Twice in one round I
  preferred a tidy number to the rule I had just written down.
- My first retention measurement was wrong by 2–4× (`ru_maxrss` reuse) and I
  reported those numbers into a comment before catching it.
- Seed 224's 18.20 s under the guest harness is uncomfortably close to
  `run_oracle`'s 30 s alarm. It passes, but the margin is thin enough that a
  loaded box could still time it out — see next steps.
- `--max-iter 0` (unbounded) is now the only way to hang the interpreter on
  purpose, and `test_cli_max_iter_zero_restores_unbounded_and_hangs` asserts
  a *timeout*, which is the one assertion in this file that costs real
  wall-clock (8 s) and can only ever be evidence of "did not finish in 8 s",
  never of "runs forever".
