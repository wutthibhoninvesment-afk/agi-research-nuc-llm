# Round 108 — predictions BEFORE measuring (banked 2026-08-25 ~18:30)

Track C (language). Whence v0.10 — "value-model floor": fuse the Python
frames around each provenance node (the node COUNT is fixed by semantics).

Context held, not predicted (measured at round start, idle machine, load 1.7,
fresh processes, min-of-3, `bench/v09_bench.py`, `--limit 6000` for examples):
- meta.lang direct **3.345 s**, fast (direct=False) **4.025 s**
- fib20 direct **4.18 µs/call**, fast 6.03, slow 9.61
- tail100k direct **4.74 µs/iter**, fast 5.50
- self_eval direct **0.489 s** (0 fallbacks at 5646), deep 1.338 s (3 fallbacks)
- retention 634 B/iter; whence suite 512 passed in 44 s
- cProfile (meta, direct): binop 0.75 s/816 k, _call_direct 0.63 s/154 k,
  Prov.__init__ 0.59 s/2.77 M, d_if 0.40 s/724 k, merged-if genexpr
  0.28 s/692 k, _field 0.26 s/1.26 M, f_name 0.26 s/2.28 M
- merged-`if` runs in meta.lang: 600,881 of 600,951 are 1-condition runs
  (99.99 %); self_host 3946/4015; tco 100001/100003
- microbench: Prov() 214–249 ns; without tuple/len checks 187–205;
  site-tuple 4-slot variant 145–152 (NOT taken: 94-site churn for ~2.4 %);
  MergedProv 388 → 215 ns with an inlined __init__; binop('+') 428 ns vs a
  fused per-op closure 373 ns (plus the eliminated lambda frame).

Planned changes (W1–W8): per-op compiled binary closures with the numeric
fast path inline; Prov.__init__ without normalisation (raw `_ins`);
MergedProv single-frame init; 1-condition runs become plain `if` nodes of
the same shape (class change only) + tuple-entries in `runs` until a merge;
inline `if` guard (`c is True / c is False`); fused field/index closures;
`derived` bypassed at hot sites; Env(parent, interp).

- **P1 meta.lang direct:** −10 % … −22 % (2.61–3.01 s; point −15 %). Lower
  bound = the frames I am certain to remove (binop lambda, MergedProv double
  init, genexpr). Conf 70 %.
- **P2 meta.lang fast (the mode I change least):** −8 % … −20 %. Conf 65 %.
- **P3 fib20 direct:** −12 % … −28 % (3.0–3.7 µs/call) — binop-dense.
  Conf 65 %. fib20 slow (pure trampoline: binop via eval_Binary generator,
  no compiled closures for call-bearing subtrees, but `n < 2`, `n - 1` are
  call-free → compile_fast → fused): −5 % … −15 %. Conf 55 %.
- **P4 tail100k direct:** −8 % … −22 % (its single-run merge does NOT hit
  the 1-cond lever). Conf 60 %.
- **P5 self_eval:** −5 % … −15 % (builtin-call heavy, f_bcall untouched).
  Conf 55 %.
- **P6 retention:** 634 B/iter EXACT (slots unchanged; 1-input nodes still
  unboxed). Conf 85 %.
- **P7 profile after:** `binop` leaves the top-5 tottime (general path only,
  < 100 k calls); Prov.__init__ tottime −25 % … −45 %. Conf 75 %.
- **P8 byte-identity:** three-way differential (direct/fast/slow) AND a new
  git-HEAD-vs-tree differential over every example + every binding's
  render_why + output + checks: identical at the end. Conf 90 %. During
  development ≥1 real divergence shows up (round 30 found one): conf 50 %.
- **P9 tests:** first full run after the edits: existing tests fail ONLY at
  test_v06's `isinstance(n, MergedProv)` assertion (a decided change).
  Conf 55 %. ≥1 of my own new tests fails on its first run: conf 50 %
  (three clean rounds in a row say no; the fused closures have many
  branches say yes).
- **P10 suite time:** adding meta.lang + self_eval.lang to the three-way
  example test adds 10–16 s to the 44 s suite. Conf 65 %.
- **P11 campaigns:** host fuzz 2×400 → 0 crash signatures (85 %); oracle
  fuzz 2×300 × 5 oracles → 0 finding signatures (75 %); guest differential
  2 seeds → ≥1 divergence (45 % — rule 5: it is not dry, 115 found three).
- **P12 GuestGen record templates (backlog 5, if reached):** a record-heavy
  template run of 300 finds ≥1 host/guest divergence (50 %).

Added 19:05 (before running it): `bench/ref_diff.py --fuzz SEED -n N` — the
reference differential over the harness's random programs (ProgramGen).
- **P13:** seeds 1 and 2 × 300 programs × 3 modes vs git HEAD → **0**
  differing (program, mode) pairs; ≤ 3 % of programs skipped for timing
  out under the reference. Conf 85 %.

## Scored (2026-08-25 ~19:40) — 9 HIT / 5 MISS, P12 not run, P13 HIT
- P1 **MISS (upside)**: meta direct −25.5 % (band −10…−22).
- P2 HIT: meta `direct=False` −18.0 %.
- P3 **MISS ×2 (upside)**: fib20 direct −28.5 % (band to −28), slow −16.3 % (band to −15).
- P4 HIT: tail100k direct −16.5 %.   P5 HIT: self_eval −6.7 %.   P6 HIT: 634 exact.
- P7 HIT: binop gone from the top; Prov.__init__ tottime −38 %.
- P8 HIT/HIT: identical at the end (39/39, then 769 fuzz programs); the
  development-time "divergence" was a v0.9 CRASH (RecursionError at limit
  6000 — comprehension frames uncounted by the budget), fixed and pinned.
- P9 **MISS** / HIT: 0 existing failures (test_v06 asserts the class on
  count > 1 only); two of my own tests failed first run.
- P10 HIT: +15.8 s (after three test-time fixes; the first run was +83 s).
- P11 HIT / HIT / **MISS**: 0 / 0 / 0 (guest dry this time).
- P12 not run: the record templates and why-shape probe exist since round 20.
- P13 HIT: 0 differing over 769 programs × 3 modes; 5 skipped (0.2 %), all
  reference-side RecursionErrors.
Lesson banked: for frame-removal work the wall-clock win exceeded the
tottime-priced estimate by ~1.6× — three rounds running. Upper bound =
2× the point estimate from now on (skill step 14).
