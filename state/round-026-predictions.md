# Round 26 — predictions BEFORE implementing F3 (banked 2026-08-24)

Change under test: F3 — inline else-if CHAIN walking in the driver.
`_if_inline` loops through nested `If` branches whose conditions compile
fast, accumulating pending (node, which, cond) wrappers, instead of pushing
one `eval_If` generator per chain level. Innermost non-fast branch falls
back to a single chain generator (or `eval_If` when the chain is length 1,
i.e. today's behavior). Provenance must be byte-identical: wrap
innermost-out with `derived("if", which, ...)`; tail calls get pending ifs
appended innermost-first to `tc.ifs`.

Baselines measured THIS round, fresh-process, current tree (v0.7 + round-25
fix): fib20 fast 0.118–0.120s; tail100k 0.52s / 79 MB; retention 634 B/iter;
self_eval example 0.54s (66 checks); meta.lang in-process fast+gc_relief
4.31s (first run in process; second run anomaly 6.18s — investigated
separately this round). meta.lang profile: 40.0M py-calls, 2.36M generator
sends, 1.24M eval_If calls, 455k _call_gen frames.

- **P1** meta.lang (in-process, fast, gc_relief, first run): 4.31s →
  **2.9–3.5s** (19–33% faster). meta_eval's ~6-level kind chain is walked
  inline; the remaining cost is _call_gen frames for meta_eval recursion
  and put/lookup traffic, which F3 does not touch. Confidence 65%.
- **P2** meta.lang generator sends drop by **>35%** (2.36M → under 1.5M).
  Confidence 60%.
- **P3** fib20: unchanged ±5% (0.112–0.126s) — fib's single `if` has a
  non-fast, non-If, non-tail branch → pending stays empty → same path as
  today. Confidence 80%.
- **P4** tail100k: unchanged ±10% (0.47–0.57s) — tail-loop ifs already go
  through _tail_inline. Confidence 80%.
- **P5** retention: 634 B/iter ±2% — F3 changes execution, not node shapes.
  Confidence 85%.
- **P6** self_eval example: 0.54s → **0.42–0.51s** (5–22% faster) — its
  guest evaluator dispatches by kind chains too, but a bigger share of its
  time is record/store traffic. Confidence 55%.
- **P7** all 453 whence tests green after F3 with NO node-shape regressions
  (killer/history pins are sharp); at most one first-run failure of a NEW
  test or wrong expectation during development (program base rate ~70%
  says at least one — betting WITH the base rate this time, round 25's P6
  lesson). Confidence 70% that at least one first-run failure happens.
- **P8** standing fuzz (host 2×400, guest-differential 2×400): 0 crash /
  divergence signatures. Confidence 75%.
- **P9** second-run slowdown anomaly: caused by the first run's retained
  heap making GC scans slower (gc_relief raises gen0 threshold but gen2
  still scans the live interpreter+env graph); dropping the first
  interpreter + gc.collect() between runs restores ≥90% of first-run
  speed. Confidence 55%.
