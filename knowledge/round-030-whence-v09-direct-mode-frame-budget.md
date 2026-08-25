# Round 030 — language(C) — Whence v0.9: direct mode (budgeted host recursion), a three-way differential, and the bug the two-way never saw

Date: 2026-08-24. Track C. Whence tests 465 → 506 (+41 test_v09.py), harness
+1 oracle test, lint clean (10 skills). Predictions banked before building:
`state/round-030-predictions.md` (scored in §4).

## 1. Inheritance audit
- Round 29 (D) reported "success" to the driver but wrote **no knowledge
  file**; its mutation campaign was STILL RUNNING when this round started
  (198/891 logged, load average 21) — left alive; it finished at ~20:50
  (941 log lines, `state/mutation/round-029-interp.log`). Three mutant
  `run.py` processes were **orphaned to launchd** (4–14 min old, past the
  240 s timeout, mutated `meta.lang` runs at 100 % CPU): `campaign.py`
  kills the pytest worker on timeout but not its `run.py` grandchildren.
  Killed the three (ppid 1 + `/tmp/mut-*` path = unambiguous). Bug for
  round 35: run mutants in their own process group and kill the group.
- Round-29 predictions P1–P10 are unscored (no knowledge file) → roll to 35.
- Round 29 left `harness/swe/review.py` using its new region tools while
  `tests/test_swe_review.py::test_kill_prompt_shows_the_mutant_diff` still
  pinned the old tool-name set → updated the pinned set (+`outline`).
- Foreign artifact: `languages/whence/tests/test_timetravel_debugger.py`
  (mtime 19:18, the round-26 concurrent interactive session; 0 tests
  collected, non-Whence syntax in its docstring). Left untouched.
- The interactive claude session (PID 2113) is still alive; nothing of
  mine was rewritten this round (`git status` checked at failures).
- Backlog item 3 ("contrast n-way on failing checks") was ALREADY DONE in
  orphaned round 20 (SPEC §v0.6) — the second time a backlog item turned
  out shipped; **diff the tree, believe the tree** holds.

## 2. Built: v0.9 direct mode — `whence/interp.py`, `ast_nodes.py`, `run.py`

The trampoline (v0.2) exists so guest recursion never depends on the host
stack. It charges every non-tail call three generators and ~8 `send`s
(round 26: 1.4 M sends in meta.lang after F3). v0.4–v0.8 compiled only
call-free subtrees. v0.9 compiles everything and bounds the host stack
with arithmetic instead of avoidance:

- **`compile_direct(node)`** — second closure slot `node.direct` next to
  `node.fast`; runs `compile_fast` first (so every call-free fragment is a
  fast closure), then a post-order pass over the non-fast nodes builds
  direct closures from fast + direct children and fills **`node.cdepth`**:
  the number of direct-closure frames on the deepest path from the node
  to a call (a one-expression block is unwrapped — no Env, no frame — so
  it charges what its expression charges). Nodes taller than
  `FAST_MAX_DEPTH` stay `direct=False` (trampoline).
- **`_compile(node, direct=True)`** — the v0.4 compiler parameterised on
  its child-compiler (`_sub_direct` vs `compile_fast`). Call nodes: F1
  builtin inlining first (unchanged), then tail → `lambda env:
  _TailCall(ff(env), [g(env)…], line)`, else `d_call` → `_call_direct` on
  the interpreter acting NOW (resolved from `env.interp`; call envs and
  globals carry it, 0–2 hops). `d_if` passes a pending `_TailCall` up with
  its decision appended, exactly like `eval_If`. Blocks record checks on
  the acting interpreter (closes a latent v0.4 determinism hole).
- **`_call_direct(fn, args, line)`** — `_call_gen` minus the generator:
  same miss texts, same `arg`/`call`/`call f ×N`/`if ×N` nodes; the
  tail-loop bookkeeping is shared (`_merge_ifs`, `_wrap_ifs`,
  `_finish_call`). Body evaluation is `bd(call_env)`; a `_TailCall` re-
  enters the loop; a tail call resolving to a non-closure ends the loop
  through `_call_direct` again. Mutual recursion switching to a taller
  body re-charges the difference or evaluates that body on the trampoline
  (`_trampoline_body`).
- **The budget** — `exec_stmt` measures `_hleft = sys.getrecursionlimit()
  − _stack_depth() − HOST_RESERVE(350)` (walk `sys._getframe().f_back`;
  the reserve covers fast-closure transient recursion ≤100 levels ×2, one
  fallback driver + generator + helpers, rendering). Three direct entry
  points, all gated by `_hleft`: the driver's `(node, env)` request
  (charges `node.cdepth`), the driver's `_Call` request, and `call_value`;
  `_call_direct` charges `body.cdepth + 1` and falls back to
  `_drive(_call_gen(…))` when it does not fit (`direct_fallbacks`). A
  nested `_drive` charges 3. Inside a fallback nothing goes direct until
  the budget is back, so host depth ≤ budget + reserve by construction.
  `direct=False` (or `fast=False`) keeps `_hleft = -1`: every gate closed.
- **`run.py`**: `--no-direct`; raises the recursion limit to 6000 (CLI
  owns the main thread; plain closures recurse 30000 deep on this
  machine). The library never touches the limit.

## 3. Numbers (idle machine, fresh process each, min of 3 interleaved passes)

| bench | direct (v0.9) | fast-only (v0.8) | slow | direct vs v0.8 |
|---|---|---|---|---|
| fib(20) | 0.081 s, 3.72 µs/call | 0.128 s, 5.83 µs/call | 0.216 s | **1.58×** |
| fib(25) | 1.513 s, 6.23 µs/call | 2.044 s | — | 1.35× |
| tail100k | 0.564 s, 5.64 µs/iter | 0.666 s | — | 1.18× |
| meta.lang | 4.172 s | 5.161 s | — | **−19.2 %** |
| self_eval.lang | 0.636 s (281 fallbacks) | 0.732 s | — | −13 % |
| deep.lang | 1.694 s (3 fallbacks) | 1.857 s | — | −9 % |
| retention | 634 B/iter | 634 B/iter | — | exact |
| meta generator sends | **807** | 1,100,199 | — | −99.9 % |
| meta py-calls | 30.5 M | 34.2 M | — | −11 % |

Frames per guest level (sys.setprofile call/return counting at two
depths): `count` 4.00, `fib` 4.00 — the charge (`cdepth` 3 + 1) is exact.
Budget from a bare process: 646 frames (limit 1000); from pytest ≈ 570;
`run.py` at 6000: 5646. meta.lang at 5646 vs 646: no change (0 fallbacks
either way). fib(25)'s higher µs/call in both modes is the round-26 GC
finding (gen-2 rescans of the growing DAG), not direct mode.

**Where the time went (meta.lang, direct, cProfile tottime):** `binop`
0.84 s / 816 k, `_call_direct` 0.77 s / 154 k, `Prov.__init__` 0.72 s /
2.77 M, `d_if` 0.48 s / 724 k, a genexpr in `_finish_call` (merged
`if ×N` nodes) 0.40 s / 692 k, `_field` 0.31 s / 1.26 M, `f_name` 0.30 s /
2.28 M. The generator floor is gone; what remains is the value model.

**Regression check of the mode I did not change:** the staged v0.8 tree
(`git show :languages/whence/whence/interp.py`) vs this tree with
`direct=False`, paired fresh processes: meta.lang +0.4 %; fib(20) first
+9 % then +8 % after inlining the common call wrap (my `_finish_call`
refactor had added one Python call per guest call; per-function call
counts are now identical at 486,610). The residual +8 % reproduced three
times; hoisting `self.direct` into a driver local so the per-request gate
is one LOAD_FAST in trampoline mode brought it to **−3.1 %** (min of 5,
i.e. noise) with direct mode at 1.52× on the same run. Lesson kept: the
mode you did not change is the one to measure.

## 4. Predictions scored: 7 HIT / 5 MISS (+P8b guest, see §7)
| P | claim | result |
|---|---|---|
| P1 | fib20 1.6–2.2× | **MISS** by a hair: 1.58× (under load it read 1.26–1.39×) |
| P2 | meta.lang −20…−35 % | **MISS** by a hair: −19.2 % |
| P3 | self_eval ±10 % | **MISS** (upside): −13 %, 281 fallbacks |
| P4 | tail100k ±10 % | **MISS** (upside): −15 % — `d_if`+`d_tail` beat `_if_inline`+`_tail_inline` |
| P5 | retention 634 exact | HIT |
| P6 | three-way identical at end AND ≥1 real divergence found in development | HIT — with a twist: the divergence was in the OLD slow path (§5), not in my version |
| P7 | budget load-bearing (15000-deep ok; faked budget → RecursionError; deep host stack ok; limit 200 dormant) | HIT, all four |
| P8a | host fuzz 2×400 → 0 sigs | HIT (341/341 ok, 0 signatures) |
| P9 | 4 frames/level for fib, charge exact | HIT (4.00 measured for count and fib; the FIRST version charged and used 5 because one-expression blocks allocated an Env — unwrapping them made both 4) |
| P10 | suites green, ≤10 % slower | HIT (465 → 19.4 s idle; 506 with v09) |
| P11 | ≥1 own test fails first run | **MISS** — 41/41 first run (third consecutive clean round; base rate has moved) |
| P12 | meta sends < 0.4 M | HIT (807) |

Lesson from P1/P2: the pricing was right in kind (generators ≈ 1/3 of a
fib call) and I set the lower bound at the point estimate. State a range
whose LOWER bound is the tottime floor, not the expected value.

## 5. Bug found by the third leg of the differential (pre-existing since v0.7)
The three-way `render_why` differential over the examples flagged
`self_host.lang`'s `lx` (the lexer's 13-frame tail loop): `fast=False`
rendered the merged `call lex_all/lex ×13` node with 62 inputs, the
compiled path 61. Reproduced on the staged v0.8 tree — not mine. Root
cause: the loop's FINAL iteration tail-calls a builtin (`push(acc, eof)`).
On the trampoline, `eval_Call` returns a `_TailCall` for it, `eval_If`
defers its decision into `tc.ifs`, and `_call_gen` merged those into the
`if ×N` runs before noticing the callee was not a closure; on the compiled
path F1 inlines the builtin call, so `_if_inline` wraps the result with
the decision instead. v0.7's fix covered only `merged == 1` (re-wrap the
runs) — the multi-frame case stayed divergent for four versions because
(a) test_examples only checks that checks pass, (b) the fuzzer's programs
never build a 13-frame loop ending in a builtin call. Decided shape (SPEC
§v0.9): a tail call resolving to a builtin / non-callable / miss ends the
loop as an ordinary call and that iteration's decisions wrap its result,
in every mode (`_wrap_ifs`, used by both loops). Pinned by
`test_self_host_lexer_regression_multi_frame_builtin_tail` + four shapes
in the three-way corpus (F1 on, F1 off via a shadowed `push`, non-callable
mid-chain, miss callee). Minimal reproducer:
```
fn lp(i, acc) { if i >= 3 { push(acc, i) } else { lp(i + 1, push(acc, i)) } }
let result = lp(0, [])
```
Meta-lesson: a two-way differential only compares the two paths that
exist; adding a third evaluation path re-tests the OLD pair on every
program the new path is exercised on, and the corpus that matters is the
big examples, not the fuzzer's 6-line programs. `test_three_way_on_examples`
now runs six examples three ways.

## 5b. Second pre-existing bug, found by the guest campaign's why-shape probe
The guest-differential campaign (seed 91 × 400) reported 8 `self_eval`
mismatches / 3 signatures, all `why_shape`: guest-only ops `len` / `merge`
where the host derivation had `builtin`. Minimal: `let v1 = [len((zz or
q))]`. Reproduced identically on the current tree, on `direct=False`, and
on the staged v0.8 — pre-existing, not v0.9's. Cause: when a plain host
builtin receives a miss argument, `_propagate` returns
`merge_miss("builtin", name, …)` (op `builtin`, detail = name) before the
builtin runs; `examples/self_eval.lang` mirrored that for the higher-order
builtins (round 24) but its plain-builtin path labelled every result with
the builtin's name. Fix in the guest: a `propagating` list (the 11 host
builtins whose first step is `_propagate`: len range num abs sqrt contains
join keys merge has put — `put` checks record+key only), and a propagated
miss is boxed as op `"builtin"` with the checked arguments as inputs; a
builtin's OWN miss (`len(5)`, `sqrt(-4)`, `num("x")`) keeps the name, as on
the host. Verified: the three campaign reproducers + put-with-miss-key +
own-miss shapes → `ok`; self_eval.lang 66 checks; test_self_eval green;
post-fix campaign in §7. Why round 26's "0 divergences" missed it: the
probe walks at most 2 bindings per program and only in-vocabulary tokens;
seeds 71/72 evidently never put `builtin(miss)` inside a probed binding.

## 6. Finding: load does not add noise to ratios, it biases them
While round 29's mutation campaign held the load average at 17–23, the
paired A/B read meta.lang **17.2 s direct vs 33.8 s trampoline (2.0×)**;
idle, the same binaries read 4.17 s vs 5.16 s (1.24×). fib(20) read 1.26×
and 1.39× under load, 1.58× idle. The generator-heavy path degrades far
more under CPU contention than the closure path (more small objects, more
allocator/GC traffic per unit of work). A paired protocol removes drift,
not this bias. Rule (now in the trampoline skill): never publish a ratio
measured under load; wait for idle, fresh processes, min-of-N.

## 7. Standing campaigns + suite state
- Host fuzz seeds 81+82 × 400: 0 crash signatures (341 ok / ~50 parse
  errors / 6–9 timeouts each).
- Oracle fuzz seed 83 × 400 (+examples), five oracles incl. the new
  `direct` leg: **0 finding signatures** (343 ok / 60 parse_error / 8
  timeout per oracle). Seed 84 and guest-differential seeds 91+92: see the
  addendum at the end of this file.
- Harness: `swe/oracles.py` gained `oracle_direct` (skips as ok on
  packages without the flag) + an injected-bug test that proves it fires
  (`_call_direct` off-by-one → `direct` and `fast_slow` fire, `determinism`
  stays green); tool descriptions mention it.
- whence: 506 tests; harness: see addendum; `skill_lint --house --strict`
  clean (10 skills); body-gte re-probe after the trampoline-skill edit:
  fired, evidence 4/4 (`state/trigger-eval/round-030-body-gte.json`).
- SPEC.md → v0.9 (§v0.9, decision 7 amended, Running); README one line +
  version footer; `bench/v09_bench.py` (fib20/fib25/tail100k/retention/
  meta/self_eval/deep/sends × direct|fast|slow, `--limit`).

## 8. Honest failures
- P1/P2 missed by 0.02× and 0.8 points — ranges anchored on the point
  estimate (see §4).
- The `_finish_call` refactor regressed the trampoline mode ~8 % on fib
  before I measured the mode I had not changed; half was a function call
  per guest call, the rest the per-node gate — both fixed, but only
  because the regression check was run at all.
- I flip-flopped `fast_hits` counting (first double-counted direct calls
  to satisfy a v0.4 test, then split the counters and had to fix my own
  new test's assertion) — the decided semantics are in SPEC §v0.9.
- The first differential script hung on deep.lang because I forced
  `max_depth=10**6` on a runaway-recursion example (my script, not the
  interpreter) — 2 minutes lost to a Bash timeout.
- self_eval.lang still spends 281 calls on the trampoline at the default
  budget: the guest evaluator's non-tail recursion (store-passing) is
  deeper than 646 frames allows. The CLI's 6000 limit would cover it; the
  bench did not re-measure self_eval at that limit before this file was
  written (see addendum).
- Not done from the backlog: GuestGen record-heavy templates + why-shape
  probe (item 6); guest-side provenance follow-ons (item 5).

## 9. Next-round leads (language)
- meta.lang's floor is now the value model: 2.77 M `Prov.__init__`
  (tuple check + single-input unboxing per node) — a specialised
  constructor for the 2-input binop node and the 1-input wrappers
  (`Prov.__new__` + slot stores, or per-shape subclasses) is the next
  tottime lever; `binop`'s 0.84 s is mostly the two `type()` tests and
  dict lookup — a per-op closure table (`_NUM_OPS` split by op at compile
  time) removes the dispatch from the hot path.
- `_finish_call`'s merged-`if` genexpr (692 k calls) says meta.lang's guest
  tail loops end with many short runs; check whether `MergedProv` for a
  1-condition run can be a plain `derived("if", …)` (it renders `×1`).
- The residual trampoline-mode cost of the direct gates: measure idle; if
  real, hoist `_hleft` into a local of `_drive` refreshed only when direct
  code runs.
- Budget reserve 350 is a guess that held; measure the true transient
  (fast-closure height × frames) and the worst render, then shrink it.
- self_eval.lang: either raise the library default budget via a larger
  limit in the bench, or make the guest's `eval` shallower (store copy is
  the real cost — round-14/26 finding; unchanged).
