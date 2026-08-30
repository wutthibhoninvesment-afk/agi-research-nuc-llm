# Round 366 (language C) — predictions banked BEFORE the fix (house rule D-013)

Root cause established before these were written: a tail loop is bounded only
by `max_iter`, which defaults to `None` (unbounded). `max_depth` cannot bound
it — a tail call spends no frame, by design (SPEC rule 8). So a
non-terminating tail recursion hangs forever, while the SAME function with the
recursive call lifted out of tail position by a `let` returns a `max_depth`
miss in 0.07 s.

Fix under test: `Interpreter.DEFAULT_MAX_ITER = 50000`, derived from measured
retention (see round-366 knowledge file §3), `max_iter=None` still meaning
"unbounded" as an explicit opt-out.

**Scored after the fact. The headline is that the FIX ITSELF was wrong and the
predictions are what caught it**: 50000 was derived from memory parity with
`DEFAULT_MAX_DEPTH`, which is a measured, principled and false rule, because a
tail loop is the only loop Whence has. P2 and P3 failing is what forced the
re-derivation from the corpus (200001 max, x3 margin, rounded up: 1000000).
Outcomes below are against the SHIPPED value of 1000000 except where the
50000 result is the informative one.

| # | Prediction | Outcome |
|---|------------|---------|
| P1 | Guest seeds 31 and 224 — the only two `timeout` kinds in the 141-seed shape sweep — both terminate under the new default, each in < 5 s. | **MISS (partial).** Both seeds terminate and both now return `ok` -- comparable differential data instead of discarded timeouts, which was the point. The `< 5 s` half is wrong: 7.48 s (seed 31) and 18.20 s (seed 224) through the guest harness, where each Whence iteration is itself interpreted by the guest evaluator. 18.20 s against `run_oracle`'s 30 s alarm is thinner headroom than is comfortable -- see next steps. |
| P2 | The whence suite (baseline 1460 passed, 3 skipped, 57 deselected) goes green with AT MOST 2 tests needing a change, and every one that needs a change is a test that explicitly asserts unbounded/`max_iter=None` tail-loop behaviour. | **MISS, badly.** 8 failed at 50000, not <=2: `test_examples.py` test_deep / test_tco / test_shapes / test_meta_self_hosting_subset, `test_v03.py` test_tail_loop_does_not_consume_depth / test_mutual_tail_recursion_merges_under_both_names, `test_v09.py::test_cli_no_direct_flag_gives_identical_output`, `test_v10.py::test_three_way_on_big_examples[meta.lang]`. And the second half of the prediction -- that any test needing a change would be one asserting unbounded behaviour -- was wrong in kind: NOT ONE of the eight was about `max_iter`. They were ordinary programs running ordinary long loops. At the shipped 1000000 the count is 0. |
| P3 | No `examples/*.lang` changes behaviour: none runs a tail loop of 50000+ iterations. | **MISS at 50000, HIT at 1000000.** Four examples ran tail loops past 50000: deep.lang 200001, tco.lang 100002, meta.lang 60005, shapes.lang 50001. I predicted none would. This is the single measurement that decided the constant. |
| P4 | `bench/retention.py` at its default n=20000 is unaffected; at n > 50000 its `tail-loop` program becomes a miss. This is a REAL regression for that bench and I will have to pass `max_iter` there explicitly. | **HIT.** `bench/retention.py` at n=20000 is unaffected; it and `reserve_probe.py` / `v06_bench.py` did need explicit `max_iter=None`, exactly as predicted, because `max_depth=10**6` was already their "do not cap me, I am measuring" signal and the tail cap needed the same. Bonus defect found there: `retention.py` divided KB-valued `ru_maxrss` by 1024**2, so it had printed "peak RSS 0 MB" for its whole existence. |
| P5 | The three-way differential (direct/fast/slow) stays consistent: the cap is enforced in BOTH `_call_direct` and `_call_gen`, so no mode sees a different answer. | **HIT.** `test_v26.py::test_the_bound_is_enforced_in_both_evaluation_modes[True/False]` passes; the full suite including the three-way differentials is green. |
| P6 | The `DEFAULT_MAX_DEPTH` docstring's "~6KB" per-frame figure is wrong (measured 1337-2084 B/frame across three non-tail shapes). Correcting it lowers the stated worst case from ~125 MB to ~40 MB. | **HIT.** Measured 1337 / 1560 / 2084 B per non-tail frame across three shapes, against the comment's "~6KB". The stated worst case for `DEFAULT_MAX_DEPTH=20000` drops from ~125 MB to ~40 MB. The comment had stood since v0.2 and no round had re-executed it. |
