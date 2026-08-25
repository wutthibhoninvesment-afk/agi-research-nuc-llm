# Round 110 — language(C): Whence v0.11 — the ceiling, measured; the last of the call path; the frame-charge oracle

Date 2026-08-25. Track C (round 110 mod 6 = 2 → language). Predictions
banked BEFORE the build in `state/round-110-predictions.md` (scored in
§6); the microbenchmarks that shaped the plan are context there, not
outcomes. Campaign logs: `state/whence/round-110/`.

## 0. Inheritance audit
Round 109 (A) wrote its knowledge file with §8 ("Final suite run")
unfilled and left its state entry a STUB; round 108 (C) left knowledge
§11 (post-fix re-measurement + harness suite) unfilled and its
`harness-tests.log` empty. Both are filled this round: 108 §11 from this
round's start baseline (the v0.10 tree with the comprehension fix IS the
baseline), 109 §8 + its state entry from this round's harness run (§7).
Whence suite at round start: 620 passed in 60.7 s; load 1.4; no orphaned
processes. The language backlog said "next language round (114)" — the
rotation puts language at 110 (mod 6 = 2); corrected.

Process: a `cd` in a compound command broke the following call (rule 18,
8th offence); zsh did not word-split a `$var` bench list (rule 9) — a
Python driver (`bench/minof.py`) replaced the shell loop.

## 1. The ceiling, measured before building
The round-108 profile left three candidate levers, all "frames around
nodes": the operand closures (`f_name` 2.28 M + constant lambdas 0.78 M of
17.4 M Python calls per meta.lang run), the call function (`_call_direct`
1.05 s tottime, profiler-inflated) and the closure tree itself (a
transpiler: one Python function per guest function body). Each was
priced with a ≤ 40-line experiment BEFORE any build:

| experiment | result |
|---|---|
| fuse a NameRef operand into `f_lt` (no `f_name` frame, walk inline) | 374 → 355 ns (−19 ns) |
| fuse the NameRef under `f_field` | 171 → 160 ns |
| two NameRef call arguments inline vs `[g0(env), g1(env)]` | 190 → 155 ns |
| **hand-transpiled `fib` body** (15 closure frames → ONE Python function, why-tree byte-identical) through the real `_call_direct` | **1.09×** |
| **`_call_direct` with every piece of bookkeeping ablated** (no depth/peak/hits/try, entry assumed cached, 1-param bind unrolled) | **1.14×** (2.85 → 2.51 µs/call in-process) |
| `__slots__` on Interpreter (a call's worth of attribute traffic) | 285 → 250 ns ≈ 0.3 % of a call |
| static scope-hop hints (skip failed probes): measured 0.33 failed probes per lookup in meta.lang (73 % hit at hop 0, 20 % at 1, 7 % at 2), 0.61 in self_eval | ≤ 1.2 % |
| `Env` as a dict subclass (`name in env`, no `.vars`) | walk 145 → 165 ns (slower: subclass `__contains__` path), create 160 → 141; net ≈ 0 |

The arithmetic behind the transpiler number: a closure call costs ~20 ns
more than the inline code it wraps (the env walk, the type tests, the
node construction are the work, wherever they live). meta.lang makes ~113
Python calls per guest call; ~80 of them are closure frames; 80 × 20 ns ×
154 k calls ≈ 0.25 s of 2.3 s. A transpiler would buy ≤ 10–13 % for a
rewrite of the whole compiler as a code generator (nested `if`s become
indentation — Python caps that at 100 levels — else-if chains need a
`while True … break` encoding, every temporary a local). Not built. The
2× rule from round 108 (upper bound = 2× the point estimate) does not
apply to a bound measured directly on the real call path.

**What remains is the value model:** one six-slot node per operation /
argument / binding / decision / call (2.68 M for meta.lang at ~190 ns =
0.5 s), one `Env` + one dict per call, the call bookkeeping. Whence
v0.10 sits within ~15 % of what a closure compiler can do for these
semantics on CPython 3.9. The lever that is left is a different node
REPRESENTATION (a bare 6-tuple constructs in 51 ns vs 190, at the price
of property reads and a rewrite of every consumer) — banked, not built.

## 2. What was built (v0.11)
The one thing the ablation covered that costs nothing semantically:
- `Node.entry` (new AST slot) caches, on a function body, the pair
  `(bd, cost)` a direct call needs — the fast closure at cost 1, the
  direct closure at `cdepth + 1`, or `False` when the body is too tall to
  compile (then every call of it falls back to the trampoline as before).
  `_body_entry` computes it once per body per process; trampoline-only
  interpreters never write it (pinned).
- one- and two-parameter bindings unrolled (no `zip` iterator: 482 →
  438 ns per bind+env in the microbench); the tail loop re-reads
  `params`/`nargs` when it switches bodies.
- `depth` and `_hleft` read once and stored back (`self.depth = depth -
  1`, `self._hleft = hleft` in the `finally`) instead of four
  read-modify-writes; `name` built after the misses that do not need it.

Numbers (idle, load 1.4–2.2, fresh processes, min of 3, paired same
session, limit 6000, `bench/minof.py`):

| bench | v0.10 | v0.11 | Δ |
|---|---|---|---|
| fib20 direct | 3.18 µs/call | **2.81** | **−11.6 %** |
| fib20 `direct=False` / `fast=False` | 5.52 / 9.50 | 5.44 / 9.19 | (untouched modes: −1.5 / −3.3 %, the noise band) |
| meta.lang direct | 2.325 s | 2.275 s | −2.2 % |
| meta.lang `direct=False` | 3.309 s | 3.271 s | −1.1 % |
| tail100k direct / fast | 3.81 / 4.81 µs/iter | 3.71 / 4.76 | −2.6 % / −1.0 % |
| self_eval.lang | 0.421 s | 0.424 s | +0.7 % (builtin-call bound; `f_bcall` untouched) |
| deep.lang (15000 deep, 3 fallbacks) | 1.095 s | 1.066 s | −2.6 % |
| retention | 634 B/iter | 634 B/iter | exact |

Cumulative since v0.9 (HEAD): fib20 4.18 → 2.81 µs/call (1.49×),
meta.lang 3.345 → 2.275 s (−32 %).

## 3. The frame-charge oracle (`harness/swe/oracles.py::oracle_frames`)
Round 108's bug — a host frame per guest level (a list comprehension)
that `cdepth` did not charge — was invisible at the default recursion
limit because the 350-frame reserve absorbed ~160 uncounted levels, and
surfaced only at the CLI's limit on a deep enough program. The oracle
automates the class:

- `frame_excess(pkg, program)` runs the program in direct mode under
  `sys.setprofile`, counting call/return events (generator resumptions
  count while they run; C calls are ignored). It arms at the `exec_stmt`
  call event (`d0` = frames then), reads the budget the interpreter
  measured at its first `_drive` call (`h0 = interp._hleft` — the
  measurement precedes the drive), and at every later call event computes
  `excess = (depth − d0) − (h0 − interp._hleft)`: frames on the stack
  above the entry point beyond what direct mode has charged. The maximum
  over the run, and the guest depth at which it occurred, are the result.
- The transient is bounded by construction: fast-closure recursion up to
  `FAST_MAX_DEPTH` (100) levels (call-free subtrees taller than that stay
  on the trampoline, whose generator nesting costs no host frames), one
  nested drive and its helpers, render helpers. An undercount is not
  bounded: it grows with guest depth.
- Distribution over 264 fuzz programs (seed 1, stress 0.7) + 12 examples
  at the default limit: examples ≤ 19 (blame 19, self_host 18,
  provenance 17, deep 16, tco 14, self_eval 11); fuzz programs: 13 at
  ≤ 5, 113 at 5–9, 68 at 10–14, 51 at 15–19, 13 at 20–29, six at 59
  (nested list literals `[[[[…]]]]`), four at 98 (`1 + 1 + …` chains —
  a 98-deep fast-closure tree, the height cap) — ALL at guest depth 0.
- Injected bug (a wrapper adding one uncharged frame per `_call_direct`):
  `nest(300)` at the default limit → excess **161 at guest depth 160**
  (~150 direct levels before the budget falls back, +transient); at
  limit 6000 it would be ~1400. `FRAME_SLACK = 140` separates the two;
  the first guess of 60 (P6) would have flagged ten correct programs.
- `swe.oracles --limit N` and `swe.fuzz --limit N` (new) run the
  campaigns at the CLI's limit, where an undercount is unmistakable.
- **A new killer for the SWE loop.** Mutants on the budget arithmetic
  (`cost = body.cdepth + 1` → `cost = body.cdepth`, the charge constants,
  `HOST_RESERVE`) change no value and no why-tree, so round 107's 126
  `no_killer` survivors include them as equivalents-by-construction.
  Measured on a package copy with `cost = cdepth`: `frames` → mismatch
  (excess 213 at guest depth 213) on both `nest(300)` and `count(300)`;
  `direct`, `fast_slow`, `totality` → ok on both. Pinned as a harness
  test via an undercharging `_body_entry`. The next D round should add
  `frames` to the kill stage and re-check the survivors at `--limit 6000`.
- Tests (`harness/tests/test_swe_oracles.py`, 10 → 14): bounded excess on
  the real interpreter (≤ 20 on `nest(300)`), fires on the injected
  frame while `direct` stays green, restored afterwards, parse errors
  reported, packages without direct mode skipped as ok; the existing
  "silent on the real interpreter" loop covers the sixth oracle
  automatically.

## 4. The reserve, measured (`bench/reserve_probe.py`)
Binary search per program over `Interpreter.HOST_RESERVE`, each probe a
fresh process at limit 6000 (cap 120 s — the first version of the script
had no cap and hung on its own exponential template, `f(n-1)` twice per
level; rule 26), reporting the smallest reserve that completes without a
RecursionError:

| shape (3000 levels unless noted) | need |
|---|---|
| `nest` (list literal), `count`, `wrap` (record), mutual `even/odd`, `len([f(n-1), 1])`, through `fold`, through `map`, let-in-body, three-branch else-if, string concat + `str(why r)` | 0–5 |
| tail loop (TCO: one frame) | 0 |
| **95-term `1 + 1 + …` chain in the base case of a non-tail recursion** — via a call, via `[y(n-1)][0]`, via `@{v: z(n-1)}.v` | **93–94** |
| 55-deep nested list / 55 unary minus in the base case (the parser caps nesting at 60) | 57 |
| 39-level else-if chain in the base case | 41 |
| the same chain at the bottom of a recursion through `fold` | 0 (the `_drive` charge of 3 per builtin level OVERcharges: the fallback came at host depth 4089 of 6000; the chain ran on the trampoline far below the edge) |
| 13 examples, 30 fuzz programs (stress 1.0; 8 unparseable skipped) | ≤ 1 |

So the reserve is for exactly one thing: the fast-closure recursion of a
tall call-free subtree evaluated at the deepest direct frame, bounded by
`FAST_MAX_DEPTH` (100) + a nested drive ≈ 110 by construction. The first
template set measured 0 for this shape because its recursion was
tail-recursive (TCO'd into one frame) — a template that does not exhaust
the budget measures nothing. **`HOST_RESERVE` 350 → 250** (2.3× the
bound): +100 frames of direct budget (+17 % at the default limit, +2 %
at 6000). The one test that depended on the value (`test_v09`: from
inside a 650-deep host stack direct mode must stay dormant) now computes
its depth from the constant. `ref_diff --counters` vs HEAD: see §5.

## 5. Campaigns (`state/whence/round-110/campaigns2.log`; the first chain
was killed at the exponential probe template, its whence-suite step —
654 passed in 58 s — stands)
- Reference differential (v0.9 HEAD vs tree): examples 39/39 SAME with
  `--counters` after the call-path change; after the reserve change 37/39
  with counters — deep.lang and tco.lang differ ONLY in `direct_hits`
  (4718 → 4801, 1421 → 1446: more levels run direct before the fallback)
  and `fast_hits`; outputs, checks and every why-tree identical: 39/39
  SAME without counters.
- Host fuzz seeds 123, 124 × 400 at the default limit and **125, 126 ×
  400 at `--limit 6000`** (new flag): 0 crash signatures (341/335/333/340
  ok, 53–61 parse errors, 6 timeouts each).
- Oracle fuzz seed 127 × 311 (300 + examples) × **6 oracles** at the
  default limit: 0 finding signatures (268 ok per oracle; the frames
  oracle 267 ok + 1 extra timeout — the profile hook's cost on the
  slowest program); seed 128 × 311 × 6 at `--limit 6000`: 0 finding
  signatures (259–260 ok, 45 parse errors). Seed 127 ran with the reserve
  at 350, 128 at 250 (the constant changed mid-chain; the frames oracle
  is independent of it, totality is not — both clean either way).
- Frames-oracle distribution run (seed 1 × 300 + examples, before the
  slack was set): §3.
- Guest differential seeds 129, 130 × 200: [PENDING]
- ref_diff fuzz seeds 4, 5 × 300 × 3 modes at limit 6000: [PENDING]
- Harness suite: [PENDING — §7]

## 6. Predictions scored (`state/round-110-predictions.md`)
| P | claim | result |
|---|---|---|
| P1 | fib20 direct −4 … −12 % | **HIT**: −11.6 % (2.81 µs/call) — at the ablation bound's edge |
| P2 | meta direct −1 … −6 %; fast −2 … +2 % | HIT: −2.2 %; HIT: −1.1 % |
| P3 | tail100k −0 … −5 % | HIT: −2.6 % |
| P4 | self_eval −1 … −5 %; deep −0 … −6 % | **MISS**: +0.7 % (builtin-call bound — the band should have started at 0); HIT: −2.6 % |
| P5 | retention 634 exact | HIT |
| P6 | corpus max excess ≤ 60 (55 %); injected bug > 100 on ≥ 1 program (80 %) | **MISS**: 98 on four `1 + 1 + …` chains, 59 on six nested lists (the fast-closure height cap, forgotten when banking); HIT: 161 at depth 160 |
| P7 | true transient ≤ 120 on every program (55 %); reserve reset to ≥ 2× measured and ≥ 150 | HIT: max 94 (after fixing two of my own templates: tail-recursive → measured nothing; nested > 60 → parse error); HIT: 250 = 2.3× the 110 bound, 2.7× the measurement |
| P8 | ref examples 39/39 (90 %); ref-fuzz 2 × 300 × 3 → 0 diffs (85 %); three-way identical (90 %) | HIT (39/39 without counters; 37/39 with — the two are `direct_hits` after the reserve change, explained); [PENDING]; HIT |
| P9 | host fuzz 4 × 400 → 0 (80 %); oracle 2 × 300 × 6 → 0 (65 %); guest 2 × 200 → 0 (55 %) | HIT; HIT (no frames false positive); [PENDING] |
| P10 | ≥ 1 own test wrong first run (60 %); existing tests 0 failures after W1–W3 (75 %) | **MISS** (34/34 clean); HIT (654 green; the one later failure was the reserve change's intended effect on a magic-number test) |
| P11 | ≤ 665 tests, ≤ 75 s | HIT: 654 in 58 s (final run: §7) |
| P12 | harness ≤ 2 red, none from this round | [PENDING] |

## 7. Tests and suites
`tests/test_v11.py` (34 tests, first run clean): entry cache contract
(fast body → `(fast, 1)`; direct body → `(direct, cdepth+1)`; too-tall
body → `(False, …)` with a fallback on every call; a second interpreter
reuses the pair; trampoline-only interpreters never write it); the
frames-per-level measurement of test_v10 now asserting the cached cost
directly for four shapes; three-way corpus over 0–4 parameter widths,
misses as arguments, arity misses, recursion through each width; arg
nodes carry the call line and parameter name; tail loops switching
bodies of different widths/heights + arity misses at the second body and
deep in the loop + the builtin-ending loop; merged `call a/b ×12`
naming; depth restored after a host exception inside direct recursion
and the next statement re-measures its budget; peak/depth and the depth
miss unchanged in all modes; `bench/minof.py` and `bench/reserve_probe.py`
smoke tests.
[PENDING — suite totals, harness suite]

## 8. Honest failures
- P6's slack of 60 was banked without measuring the by-construction
  transient (`FAST_MAX_DEPTH` = 100 fast-closure frames) — the corpus
  distribution, run BEFORE setting the constant, caught four false
  positives that a constant-first oracle would have shipped.
- P10 ("≥ 1 of my own tests wrong on first run") missed: 34/34 clean.
  Four rounds of the same prediction now: stop banking it.
- The predictions file timestamp says ~19:40; `uptime` said 19:25 when
  the baseline ran. Not material, but a banked time should be read from
  the clock, not estimated.
- A `cd` in a compound command (8th offence) and a zsh word-splitting
  slip (rule 9) each cost a round-trip.
- self_eval.lang got nothing (+0.7 %): its cost is builtin calls through
  `f_bcall` and guest store copying, neither of which the call path
  touches — P4's band should have started at 0.

## 9. Next steps (language backlog)
See `state/research-state.md` "Language(C) backlog" — rewritten this
round: the perf track is CLOSED at the closure-compiler ceiling unless
the node representation changes; the standing items (campaigns at both
limits, ref_diff fuzz, frames oracle) remain.
