# Round 24 — predictions BEFORE implementing v0.7 (banked 2026-08-24)

Change under test: F1 (builtin-call inlining in compile_fast, gated on a
program-wide never-shadowed check + runtime identity fallback) + F2 (frameless
non-tail closure calls when the callee's body compiled fast). Baselines
measured this round, fresh-process unless noted: fib20 fast 0.115s;
meta.lang in-process fast 4.32s; self_eval example 0.60s; tail100k 0.51s;
retention 634 B/iter.

- **P1** fib(20): unchanged ±5% (0.109–0.121s) — fib's body contains user
  calls, so neither F1 nor F2 applies to it. Confidence 75%.
- **P2** meta.lang (in-process, fast, gc_relief): 4.32s → **2.6–3.5s**
  (25–40% faster) — lookup/tok/scan_while/slice bodies become fast via F1,
  their call sites frameless via F2; parse_*/meta_eval recursion unaffected.
  Confidence 60%.
- **P3** self_eval example run: 0.60s → **0.42–0.55s** (10–30%) — mkb/strip-
  style helpers should compile; less sure of their shapes. Confidence 55%.
- **P4** tail100k: unchanged ±10% — tail loops were already generator-free.
  Confidence 70%.
- **P5** retention: 634 B/iter ±2% — F1/F2 change execution, not nodes.
  Confidence 80%.
- **P6** all 430 existing tests green after the change with NO node-shape
  regressions; standing fuzz (host 2×400, guest-differential 2×400) → 0
  signatures. Confidence 65%.
- **P7** at least one first-run failure of my own new tests or a wrong
  expectation during development (program base rate). Confidence 70%.
