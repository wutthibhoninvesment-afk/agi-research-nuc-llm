# Round 110 — predictions BEFORE measuring (banked 2026-08-25 ~19:40)

Track C (language). Whence v0.11 — "the ceiling": measure the end of the
frame-removal strategy, slim the call path, automate the round-108 bug
class (frame-charge oracle), measure HOST_RESERVE.

Context held, not predicted (idle, load 1.4–1.7, fresh processes, min-of-3,
`bench/minof.py`, limit 6000; these ALSO fill round 108's §11):
- meta.lang direct **2.325 s**, fast 3.309 s
- fib20 direct **3.18 µs/call**, fast 5.52, slow 9.50
- tail100k direct 3.81 µs/iter, fast 4.81; self_eval 0.421 s; deep 1.095 s
  (3 fallbacks); retention 634 B/iter; whence suite 620 in 60.7 s
- profile (meta, direct, cProfile-inflated): _call_direct 1.05 s/154 k,
  f_eq 0.51/752 k, d_if 0.45/724 k, Prov.__init__ 0.41/2.68 M,
  f_name 0.31/2.28 M, f_bcall 0.30/243 k, f_field 0.30/1.17 M
- microbenchmarks that SHAPED the plan (context, not outcomes):
  * fusing a NameRef/const operand into its parent closure saves 10–20 ns
    per operand (374→355 ns `n < 2`; 171→160 `node.kind`; 190→155 two
    args) — call overhead is small, the env walk dominates
  * a hand-transpiled fib body (15 closure frames → 1 Python frame, why-tree
    identical) through the real `_call_direct`: **1.09×**
  * `_call_direct` with ALL bookkeeping ablated (no depth/peak/hits/try,
    entry cache, unrolled bind): **1.14×** on fib20 — the upper bound
  * `__slots__` on Interpreter: 285→250 ns for a call's attribute traffic
    (~0.3 % of a call) — declined
  * name lookups: meta.lang 2.28 M lookups, 0.33 failed probes each (73 %
    hit at hop 0) → static hop hints ≤ 1.2 % — declined
  * Env as a dict subclass: walk 145→165 ns (slower), create 160→141 —
    net ≈ 0 — declined

Planned: (W1) per-body entry cache `(bd, cost)` on the body node; (W2)
unrolled 1-/2-param binding; (W3) load-once/store-once `depth`/`_hleft`
traffic in `_call_direct`; (W4) `oracle_frames` in harness/swe/oracles.py
(setprofile: excess = host frames used − frames charged, max over the
run) + injected-bug test; (W5) `bench/reserve_probe.py` crash-threshold
search for HOST_RESERVE at limit 6000; (W6) campaigns incl. `--limit 6000`.

- **P1 fib20 direct:** −4 % … −12 % (2.80–3.05 µs/call; point −6 %; the
  ablation bound is −12.3 %). Conf 65 %.
- **P2 meta.lang direct:** −1 % … −6 % (154 k calls × ~0.3 µs ≈ 2 %).
  Conf 60 %. meta fast (direct=False — `_call_gen` untouched): −2 … +2 %.
- **P3 tail100k direct:** −0 % … −5 % (the loop re-binds 2 params per
  iteration; unrolling saves ~40 ns × 100 k ≈ 1 %). Conf 60 %.
- **P4 self_eval:** −1 % … −5 %. Conf 55 %. deep.lang: −0 … −6 %.
- **P5 retention:** 634 B/iter exact. Conf 90 %.
- **P6 frame-charge oracle:** over 300 fuzz programs + examples at the
  default limit the max excess (used − charged) is ≤ 60 frames for every
  program (conf 55 % — generator builtins and render helpers are the
  unknown); with the round-108 comprehension re-injected into `f_list`
  the oracle reports excess > 100 on ≥ 1 program (nest template) —
  conf 80 %.
- **P7 HOST_RESERVE:** the crash-threshold search (limit 6000, examples +
  deep fuzz templates) finds the true transient ≤ 120 limit-units on every
  program (conf 55 %); the reserve is reset to ≥ 2× the measured maximum
  and ≥ 150.
- **P8 byte-identity:** `ref_diff` examples 39/39 SAME (90 %); ref-fuzz
  2 seeds × 300 × 3 modes → 0 diffs (85 %); three-way over the test corpus
  identical (90 %).
- **P9 campaigns:** host fuzz 2×400 (default) + 2×400 (`--limit 6000`) →
  0 crash signatures (80 %); oracle fuzz 2×300 × 6 oracles → 0 finding
  signatures (65 % — the new oracle is the risk: 35 % it flags a shape I
  did not measure); guest 2×200 → 0 divergences (55 %).
- **P10 tests:** ≥ 1 of my own new tests wrong on first run (60 %);
  existing whence tests: 0 failures after W1–W3 (75 %).
- **P11 suite:** ≤ 665 tests, ≤ 75 s idle. Conf 65 %.
- **P12 harness suite:** ≤ 2 red, none caused by this round (60 %).
