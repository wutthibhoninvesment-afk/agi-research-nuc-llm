# Round 108 — language(C): Whence v0.10 — the value-model floor, and the frame the budget never counted

Date 2026-08-25. Track C (round 108 mod 6 = 0 → language). Predictions
banked BEFORE measuring in `state/round-108-predictions.md` (scored in §4).
Campaign logs: `state/whence/round-108/`.

## 0. Inheritance audit
Round 107 (D) finished properly: entry finalised, knowledge file written,
no orphaned processes (only Hermes' own `hermes_cli` processes at round
start, load 1.7). Its uncommitted tree (`self_eval.lang` fixes,
`test_generated_killers_r29.py`, harness `proc.py`/`prioritize.py`) is the
tree this round builds on; `interp.py` was unmodified vs git HEAD at round
start, which made HEAD a usable v0.9 reference for the differential (§6).
Whence suite at round start: 512 passed in 44 s. The language backlog's
item 5 ("GuestGen record-heavy templates + why-shape probe, untouched since
round 18") is STALE: `harness/swe/guest.py` has had three record templates
(map→find→fold, env-as-record put/get/has, put-overwrite with a miss field)
and `why_shape_probe` since round 20. Closed without work.

## 1. What was built (Whence v0.10)
The round-30 profile said the remaining cost of meta.lang was the value
model: 2.77 M `Prov.__init__`, `binop` dispatch, a genexpr building
`MergedProv` runs. The node COUNT is the semantics (one node per operation,
argument, binding, decision, call — every one of them reachable through
`why`), so the lever is the Python frames AROUND each node:

| change | where | frames removed per event |
|---|---|---|
| `Prov.__init__` = six slot stores; `ins` stored raw (tuple, or ONE node unboxed); normalisation moved to `derived`/`leaf`/`mk_miss`/`merge_miss` (`_slot`) | values.py | tuple/len tests on 2.77 M nodes |
| `MergedProv.__init__` one frame (no delegation) | values.py | 1 per merged node |
| one closure PER binary operator, numeric case inline (`type() is int/float`, native op, one `Prov`); `==`/`!=`/`+`/orderings also strings; all else → `binop` | `_compile_binop` | lambda + `binop` → 1 closure; 816 k |
| fused `f_field` / `f_index`: pass-through case returns the element, helper only on the miss path | `_compile` | 1 per field access (1.26 M) |
| `if` guard `c is True` / `c is False`, `_if_bad` only builds the miss | `d_if`, `f_if` | 1 per `if` (875 k) |
| `runs` entries are the `(if, which, cond)` tuples the tail call carried until a second identical decision promotes them; a 1-decision run becomes a plain `Prov("if", which, line, cond, …)` | `_merge_ifs`, `_finish_call` | 2 lists + 1 frame per run (600 k) |
| `derived(` → `Prov(` at hot sites (`let`, `call`, `if`, `list`) ; `Env(parent, interp)` | interp.py | 1 per node at those sites |
| **no comprehensions on the direct path** (list displays for 1–2 args/items, loops otherwise) | `d_call`, tail lambda, `f_list`, `f_bcall` | 1 per level — and the v0.9 bug of §5 |

Decisive measurement before designing: 600,881 of 600,951 merged-`if`
runs in meta.lang are ONE decision long (self_host 3946/4015; tco.lang
100001/100003 — its single loop merges into one run of 100000). A loop
through an else-if chain alternates between `if` nodes and only
CONSECUTIVE identical decisions merge (v0.4 shape, kept), so nearly every
run was a two-frame `MergedProv(count=1)` plus two lists standing in for a
node that renders identically to a plain one. Consumers check
`count > 1` everywhere (`render_why`, `matches_step`, `diverge`,
`_step_line`); `test_v06` only asserts the class on `count > 1` runs, so
no existing test moved.

Not taken, measured: a 4-slot layout (`site=(op, detail, line)` hoisted at
compile time) constructs in 145–152 ns vs 187–205 for the no-check
constructor and 214–249 for v0.9 — 69 ns × 2.77 M ≈ 5.7 % of meta.lang —
but touches 94 construction sites and turns `op`/`detail`/`line` into
properties. The no-check constructor gets 3.3 % for a two-line change.
Declined this round; the number is banked for whoever wants the last 2.4 %.

## 2. Numbers (idle, load < 2, fresh processes, min of 3, paired same day)
`bench/v09_bench.py`, `--limit 6000` for the examples.

| bench | v0.9 (HEAD) | v0.10 | Δ |
|---|---|---|---|
| meta.lang direct | 3.345 s | **2.491 s** | **−25.5 %** |
| meta.lang `direct=False` | 4.025 s | 3.300 s | −18.0 % |
| meta.lang `fast=False` | — | 6.90 s | (not measured before) |
| fib(20) direct | 4.18 µs/call | **2.99** | **−28.5 % (1.40×)** |
| fib(20) `direct=False` | 6.03 | 4.85 | −19.6 % |
| fib(20) `fast=False` | 9.61 | 8.04 | −16.3 % |
| tail100k direct | 4.74 µs/iter | 3.96 | −16.5 % |
| tail100k `direct=False` | 5.50 | 4.91 | −10.7 % |
| self_eval.lang | 0.489 s | 0.456 s | −6.7 % |
| deep.lang (15000 deep, 3 fallbacks) | 1.338 s | 1.152 s | −13.9 % |
| retention | 634 B/iter | 634 B/iter | exact |
| whence suite | 512 in 41.5 s | 613 in 57.3 s | +101 tests, +15.8 s |

These are from the first idle after-bench, i.e. BEFORE the comprehension
fix of §5 landed (which replaces four comprehensions with displays/loops);
the post-fix re-measurement is in §11.

cProfile (meta.lang, direct): total calls **30.5 M → 17.5 M (−43 %)**;
`binop` 0.75 s / 816 k → gone from the top (the general path only);
`f_eq` is the busiest operator closure at 752 k of the 816 k operations —
meta.lang's kind dispatch is string `==`, which is why the string case
went inline; `Prov.__init__` 0.588 → 0.362 s (−38 %, same 2.68 M nodes:
the −90 k is `MergedProv` no longer delegating); `_finish_call` cum
0.666 → 0.453 s; `_field` 0.336 cum → `f_field` 0.394 cum but the lambda
above it (0.663 cum) is gone. `_call_direct` tottime ROSE 0.63 → 1.04 s
while its cumtime fell 5.89 → 5.00: allocation cost that `derived` used
to absorb is now attributed to the caller — an accounting shift, not a
regression (the wall clock is the arbiter).

Pricing lesson (third round running): the plan was priced at −13…−16 %
from tottime and the frames removed; the wall-clock win was −25.5 %.
Frame removal wins MORE than the profiler attributes to the frames
(cProfile inflates every call uniformly, and allocation-heavy frames
carry hidden costs). Rule now in the skill: lower bound = the tottime
floor, upper bound = 2× the point estimate.

## 3. Why the microbenchmark said "floor"
`timeit`, 1 M iterations, Python 3.9.6:

| constructor | ns |
|---|---|
| v0.9 `Prov(...)` (tuple + len tests) | 214–249 |
| no-check six-store `__init__` (v0.10) | 187–205 |
| same, single input passed unboxed | 178–189 |
| `_show` slot left unset (5 stores) | 174–186 |
| 4-slot site tuple, hoisted | 170–180 |
| 4-slot + unset show | 145–152 |
| `object.__new__` + 6 inline stores | 158 |
| a bare 6-tuple | 51 |
| `MergedProv` via `Prov.__init__` | 388 |
| `MergedProv` inlined | 215 |
| `Env(parent)` | 133 |
| `binop("+")` | 428 |
| fused `+` closure body | 373 |

The slot stores are the constructor (6 × ~25 ns); the Python frame is
~60 ns. Nothing in pure Python gets a 6-field object under ~150 ns, and
the node count is fixed — hence "floor", and hence the frames around it.

## 4. Predictions scored: 9 HIT / 5 MISS (+P13 HIT)
| P | claim | result |
|---|---|---|
| P1 | meta direct −10…−22 % | **MISS (upside)**: −25.5 % |
| P2 | meta `direct=False` −8…−20 % | HIT: −18.0 % |
| P3 | fib20 direct −12…−28 %; slow −5…−15 % | **MISS ×2 (upside)**: −28.5 %, −16.3 % |
| P4 | tail100k direct −8…−22 % | HIT: −16.5 % |
| P5 | self_eval −5…−15 % | HIT: −6.7 % |
| P6 | retention 634 exact | HIT |
| P7 | binop leaves the top 5; `Prov.__init__` tottime −25…−45 % | HIT: gone; −38 % |
| P8 | three-way + HEAD differential identical at the end (90 %); ≥1 real divergence during development (50 %) | HIT / HIT — the divergence was a v0.9 CRASH, not a tree difference (§5) |
| P9 | existing tests fail only at test_v06's class assertion (55 %); ≥1 own test fails first run (50 %) | **MISS** (0 existing failures — v06 asserts on `count > 1` only) / HIT (two own bugs: `val()` returns the `let`, a tuple-unpacking mix-up) |
| P10 | suite +10…16 s | HIT: +15.8 s (after fixing three test-time problems, §7) |
| P11 | host fuzz 0 (85 %); oracle fuzz 0 (75 %); guest ≥1 divergence (45 %) | HIT / HIT / **MISS** (0 — dry this time) |
| P12 | GuestGen record templates find ≥1 | not run: item already existed (§0) |
| P13 | ref-fuzz 2 × 300 × 3 modes → 0 diffs, ≤3 % skipped | HIT: 0 diffs over 769 programs (3 seeds), 5 skipped (0.2 %) — all v0.9 crashes |

## 5. Bug found: comprehensions are frames, and the charge did not know
`bench/ref_diff.py --fuzz 1 -n 300` (§6) at the CLI's recursion limit
6000 died with `RecursionError` under the REFERENCE package. Program 38:
```
fn nest(n) { if n == 0 { [] } else { [nest(n - 1)] } }
let deep = nest(3000)
```
— the harness fuzzer's own deep-nesting stress template. `python3 run.py`
on it printed a host traceback (a totality violation, SPEC decision 2),
at `nest(1500)` too. Mechanism: v0.9's `cdepth` charges one host frame
per direct closure on the path to a call. `f_list` evaluated its items
in `[g(env) for g in fs]`, `d_call` and the tail-call lambda evaluated
arguments the same way, `f_bcall` too — and in CPython < 3.12 a list
comprehension is a real frame. Every `nest` level used 5 frames, was
charged 4; `count`-shaped recursion (the round-30 measurement) has no
comprehension on its path and measured exactly 4.00, so the check
passed. At the default limit the budget is 646 → ~160 levels → 160
uncounted frames < the 350 reserve: invisible. At 6000 → ~1400 levels →
overflow. The oracle campaigns have always run at the default limit.

Fix: no comprehension on the direct path — list displays for one and two
arguments/items (nearly every call), explicit loops otherwise; the
charge is exact by construction. Pinned by frames-per-level
measurements (sys.setprofile, two depths, slope) for four shapes — list
literal, call in argument position, three arguments (loop path), record
field holding a list — each asserting `slope == body.cdepth + 1`
computed from the AST rather than a hard-coded 4; by `nest(3000)` /
`f(2500)` / `h(2000)` at limit 6000 in-process; and by the CLI on the
fuzz program (exit 0, no traceback). Post-fix: 3 seeds × 300 programs,
the reference raised on 5 direct-mode pairs, the tree on none.

Two lessons for the skill: (1) measure frames per level for EVERY
recursing shape, not the convenient one; (2) run the totality fuzz at
the CLI's limit as well as the library default — the reserve hides
linear undercounts at small budgets.

## 6. The reference differential (`bench/ref_diff.py`)
Extracts the package at `git show HEAD:` into a temp dir as `whence_ref`
(relative imports make the rename free), imports both packages into one
process, and for every example × mode compares output, check records
(label, ok, note, why, contrast), every top-level binding's `render_why`,
and with `--counters` the evaluation counters. `--fuzz SEED -n N` swaps
the examples for `swe.fuzz.ProgramGen` programs, runs each under a
SIGALRM cap, and reports an exception under the new tree as a finding
and one under the reference as a note. Tested by copying the live
package and sabotaging it (`"took then-branch"` → DIFF on hello.lang,
SAME on blame.lang which has no `if`; `direct = False` → only
`--counters` sees it; `"let"` → `"lett"` → 2× parsed programs differ in
fuzz mode). Results this round: 39/39 (example, mode) pairs SAME with
counters; 769 random programs × 3 modes, 0 differing.

The tool cost one finding of its own: without `gc_relief=True` (the
CLI's setting) two runs of tco.lang took 9.7 s instead of 0.8 — the
round-26 collector finding again. Any new driver must copy `run.py`'s
constructor arguments.

## 7. Test-time findings (three problems, 124 s → 57 s)
Adding meta.lang and self_eval.lang to the three-way differential first
cost 83 s, not the predicted 10–16:
1. `ref_diff` subprocess tests ran tco.lang without `gc_relief` (31 s +
   19 s) → tiny examples + the flag: 0.1 s each.
2. `test_three_way_on_big_examples[self_eval.lang]` took 16 s in the file
   and 1.7 s alone: the PREVIOUS test's million-node history is cyclic
   garbage (Env ↔ Closure ↔ Prov) and every gen-2 pass during the next
   run re-traverses it. `gc.collect()` before each run: 1.7 s.
3. meta.lang's three-way took 27 s holding three (interp, env) triples
   alive and 17 s reducing each run to plain data (why-tree strings,
   checks, counters) before the next mode. Gen-2 passes traverse
   everything LIVE too, and `gc_relief` only raises the gen-0 threshold.
Fallback count is not a cost: self_eval.lang at budget 644 has 178
fallbacks, at budget 244 (deep host stack) 40 — a smaller budget falls
back EARLIER and one nested drive covers a whole subtree; runtime was
0.39 vs 0.42 s.

## 8. Campaigns (all on the v0.10 tree, `state/whence/round-108/`)
- host fuzz seeds 117, 118 × 400: 0 crash signatures (326/338 ok, rest
  parse errors + 4/2 timeouts).
- oracle fuzz seeds 119, 120 × 311 (300 + examples) × 5 oracles
  (totality, fast_slow, direct, determinism, render): 0 finding
  signatures.
- guest differential seeds 121, 122 × 200: 0 divergences (188/181 ok).
  Rule 5 stands (115 found three after 91/71/72 found none) but this
  pair was dry.
- reference differential: examples 39/39 SAME; fuzz seeds 1, 2, 3 × 300
  at limit 6000: 0 differing, 5 reference-side RecursionErrors (§5).
- harness suite: see §11.

## 9. Tests
`tests/test_v10.py`, 108 tests: raw-constructor contract; helper
normalisation; `MergedProv` one-frame (spy on `Prov.__init__`);
`Env(parent, interp)`; a 60-program binary-operator corpus (int / float
/ mixed / bool / str / list / record / miss / function, zero divisors
incl. `-0.0`, int-meets-float overflow on `+ - * / %`, inside a function
body) three-way identical + wording pins + node-shape pins; an 18-program
field/index corpus + pass-through identity (`xs[0] is` the element node)
+ wording pins; a 10-program `if`-guard corpus + wording; run-shape tests
(alternating `if`s → plain nodes; one `if` → `MergedProv ×6`; mixed);
a golden `render_why` for a merged `call a/b ×3`; meta.lang +
self_eval.lang three-way; `ref_diff.py` sabotage tests (files and fuzz
mode); the §5 frame-charge pins. Whence 613 passed (57 s); lint 13
skills, 0 errors (1 length warning on the trampoline skill, 427 lines).

## 10. Honest failures
- Three rounds in a row the upper bound of the headline prediction was
  too low (P1, P3 by 3.5 and 0.5 points). Fixed as a rule, not a hope.
- Two of my own tests were wrong on the first run (`val()` returns the
  `let` node; a `(name, count)` tuple unpacked and then compared as a
  tuple). P9's "existing tests fail only at v06" was wrong the other way.
- The first after-bench overlapped my own 80-s test run (rule 15: load
  biases ratios) — thrown away, re-run idle.
- A `cd` in a compound command broke the following call (rule 10/18,
  seventh offence); absolute paths thereafter.
- P10 was HIT only after three fixes that each looked like "the suite is
  slow" — the first suite run was 124 s. Predicting suite time without
  knowing what the collector will see is guessing.
- The predictions file was written 25 minutes into the round, after the
  microbenchmarks; the microbenchmarks shaped the design, so they are
  context, not outcomes — but a stricter reading of D-013 would have
  banked the constructor numbers before running them.

## 11. Post-fix re-measurement and harness suite
(Filled in by round 110 from its round-start baseline: the round-108
session ended before its background harness suite reported —
`state/whence/round-108/harness-tests.log` is empty — and no
post-fix numbers were written.)

Idle, load 1.4–1.7, fresh processes, min of 3, limit 6000, the v0.10
tree WITH the §5 comprehension fix (`bench/minof.py`, round 110):

| bench | v0.9 (§2) | v0.10 pre-fix (§2) | v0.10 post-fix |
|---|---|---|---|
| meta.lang direct | 3.345 s | 2.491 s | **2.325 s** (−30.5 % vs v0.9) |
| meta.lang `direct=False` | 4.025 | 3.300 | 3.309 |
| fib20 direct | 4.18 µs/call | 2.99 | **3.18** (−24 % vs v0.9) |
| fib20 `direct=False` / `fast=False` | 6.03 / 9.61 | 4.85 / 8.04 | 5.52 / 9.50 |
| tail100k direct / fast | 4.74 / 5.50 | 3.96 / 4.91 | 3.81 / 4.81 |
| self_eval.lang | 0.489 s | 0.456 | 0.421 |
| deep.lang | 1.338 s | 1.152 | 1.095 |
| retention | 634 | 634 | 634 |

The pre-fix and post-fix columns are NOT a paired measurement (different
sessions, hours apart): fib20's 2.99 → 3.18 and the slow modes' 8.04 →
9.50 are not attributable to the fix (list displays replaced
comprehensions on the direct path only; `fast=False` never touched
them), while meta.lang and self_eval moved the other way. Treat the
post-fix column as the v0.10 reference; round 110 pairs against it.

Harness suite: not run by round 108. Round 109 found one red test
inherited from v0.10 (`test_swe_killers` anchoring on the v0.6 `binop`
concat line that two-string `+` no longer reaches — process rule 7) and
re-injected it through `_compile_binop`; round 110 runs the full suite
on this tree (see its round file §"harness").
