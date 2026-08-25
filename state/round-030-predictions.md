# Round 30 — predictions BEFORE measuring (banked 2026-08-24, ~20:35)

Context held, not predicted: v0.8 tree, whence 465 green (67 s under load —
round-29's mutation campaign is running concurrently, load avg ≈21; the
recorded idle figure is ~20 s). Round-26 reference numbers (paired A/B, min
of passes, idle-ish machine): fib20 0.118–0.140 s (≈5.4 µs/call), meta.lang
3.97–4.29 s, self_eval 0.54–0.59 s, tail100k 0.52–0.57 s, retention 634
B/iter. Round-26 profile of meta.lang: 455k `_call_gen` frames (~1.8 s cum),
1.40M generator sends, 2.77M `Prov.__init__`.

Design being built (v0.9 "F4", direct mode): every subtree — calls included —
compiles to Python closures that recurse on the HOST stack; a closure call to
a non-fast body goes through `_call_direct` (same arity/depth/tail-loop
semantics as `_call_gen`, no generator); a frame budget derived from the live
`sys.getrecursionlimit()` minus the current stack depth minus a reserve gates
every direct entry, and an exhausted budget falls back to the trampoline
(nested `_drive`), so host stack depth is bounded by construction. Tail
loops stay frameless.

- **P1 (fib20, paired A/B direct vs `direct=False`, min of passes):**
  direct is **1.6–2.2× faster** (≈5.4 → 2.5–3.4 µs/call). Priced off what is
  removed per call: 3 generator allocations, ~8 sends, ~8 driver-loop
  dispatch iterations. Confidence 60 %.
- **P2 (meta.lang, same protocol):** **−20 to −35 %** wall. Priced off
  tottime this time: ~1.4M sends × ~0.25 µs + ~0.5M generator allocs +
  driver dispatch ≈ 0.8–1.3 s of ~4.0 s. Confidence 55 %.
- **P3 (self_eval.lang):** change within **±10 %** (its cost is store
  copying, round-14/26 finding). Confidence 65 %.
- **P4 (tail100k):** within **±10 %** — tail loops were already frameless;
  direct mode only changes how the body's `if` + tail call are evaluated.
  Confidence 60 %.
- **P5 (retention):** **634 B/iter exact** — no new retained node kinds.
  Confidence 85 %.
- **P6 (semantics):** at round end the THREE-mode differential (direct /
  fast-only / slow) is byte-identical in `render_why` on the whole corpus
  (calls, mutual recursion, tail loops with merged ifs, deferred ifs,
  rescue, map/filter/fold/find with closures, arity/depth/max_iter/
  non-callable misses, checks + print inside bodies); AND during
  development the differential catches **≥1 real divergence** in my first
  version. Confidence 70 %.
- **P7 (host-stack safety):** non-tail recursion depth 15000 (max_depth
  raised) under the DEFAULT recursion limit passes with budgeting; the same
  program with the budget disabled (`_hleft` forced huge) raises
  RecursionError — proving the guard is load-bearing. Also passes when
  `run()` is entered from inside a 600-frame-deep host recursion, and under
  `sys.setrecursionlimit(200)` (existing test) direct mode simply never
  engages. Confidence 80 %.
- **P8 (standing campaigns, after the mutation load clears):** host fuzz 2
  seeds × 400 → 0 crash signatures (conf 75 %); guest-differential 2 seeds ×
  400 → 0 divergence signatures, timeouts < 3 % (conf 75 %).
- **P9 (frames per guest level):** measured host frames per direct fib
  level = **4** (cdepth 3 + `_call_direct`), i.e. the charged cost equals the
  measured cost exactly. Confidence 60 %.
- **P10 (suite):** whole suite + new test_v09.py green; idle-machine suite
  wall time not more than 10 % slower than before. Confidence 60 %.
- **P11 (process):** ≥1 of my own new tests fails on first run (base rate
  ~50 % after two clean rounds). Confidence 55 % YES.
- **P12 (meta.lang generator sends):** drop from 1.40M to **< 0.4M**
  (only generator builtins, budget fallbacks and top-level statements
  remain). Confidence 60 %.

## Scored (end of round; details in knowledge/round-030-whence-v09-direct-mode-frame-budget.md §4)
P1 MISS (1.58× vs ≥1.6) · P2 MISS (−19.2 % vs ≥20 %) · P3 MISS upside (−13 %) ·
P4 MISS upside (−15 %) · P5 HIT (634) · P6 HIT (three-way identical; the
divergence found was a pre-existing v0.7 leftover in the slow path) · P7 HIT
(all four proofs) · P8 host HIT (0 sigs ×2), oracles HIT (0 sigs ×2 incl.
`direct`), guest: see the knowledge-file addendum · P9 HIT (4.00 measured,
4 charged — after unwrapping one-expression blocks; the first version
was 5/5) · P10 HIT · P11 MISS (41/41 first run) · P12 HIT (807 sends).
Tally 7 HIT / 5 MISS, guest pending at scoring time.
