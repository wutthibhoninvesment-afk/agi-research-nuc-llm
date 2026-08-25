# Round 29 — predictions BEFORE measuring (banked 2026-08-24)

Written after the inheritance audit + standing checks (harness 284 green /37 s,
whence 465 green /20 s, nested `claude -p` auth VERIFIED: sonnet, $0.043/probe)
but BEFORE any mutation / campaign / live-model result. Context held, not
predicted: v0.4 interp.py scored 90.43 % (679 mutants, 457 s, round 9); current
v0.8 interp.py yields **891** mutants (ifneg 296, cmp 194, const 192, arith 85,
bool 62, not 62); values.py 251, parser.py 138, lexer.py 117. Round-23's review
trace: 18 steps, 17 `search`, 1 truncated `read_file`, 0 `oracle_check`.

- **P1 (mutation baseline, v0.8 interp.py, full 465-test suite, 891 mutants,
  5 workers, 240 s timeout):** score **89–93 %**, survivors **60–100**.
  Rationale: v0.4 90.4 %; +212 mutants since then land in v0.5–v0.8 code
  (get/put/find/has, string fast path, inline dispatch, F1/F2/F3 compilation)
  which test_v05–v08 cover directly, but every fast-path layer duplicates
  semantics and breeds equivalent-looking survivors. Confidence 65 %.
- **P2 (wall time):** the 891-mutant run takes **25–50 min** (round-23 log
  rate ≈2.8 s/mutant effective at 5 workers → ~42 min). Confidence 60 %.
- **P3 (timeouts under load):** 3–10 mutants time out during the parallel
  run; on an idle serial re-check **≥1 of them flips** (to killed-by-assertion
  or survived) — i.e. timeouts recorded under load are not all real infinite
  loops. Confidence 55 %.
- **P4 (corpus killers on survivors, 300 random programs + examples):** the
  random corpus kills **25–50 %** of survivors; the rest are `no_killer`.
  Confidence 60 %.
- **P5 (live review, sonnet, interp.py, 30 steps, with the NEW region tools —
  outline + ranged read_file + file-scoped search):** `oracle_check` is called
  **≥5 times** (was 0 in round 23); the model emits a JSON answer (round 23
  never did); claims **1–4**, confirmed **0–1**, precision **≤50 %**.
  Confidence 60 %.
- **P6 (live kill, sonnet, on 8 sampled `no_killer` survivors, 20 steps
  each):** kills **40–70 %** of attempted (3–6 of 8); **≥1 `equivalent`**
  verdict; at least one claimed-equivalent is genuinely equivalent
  (const/cache-key mutants often are). Confidence 60 %.
- **P7 (verification of pins):** every corpus-found and model-found killer,
  once pinned as a test, kills its mutant on re-run (survivor-only re-mutation)
  — **100 %** re-kill, 0 flaky pins. Confidence 70 %.
- **P8 (standing campaigns, AFTER mutation to avoid load-skew):** host fuzz 2
  seeds × 400 → **0 crash signatures** (conf 75 %); guest-differential 2 seeds
  × 400 → **0 divergence signatures** (conf 80 %), timeouts < 3 % (conf 70 %).
- **P9 (cost):** entire live lane (review + kills) ≤ **$8** CLI-reported.
- **P10 (process):** at least one of my own new tests fails on first run
  (base rate: rounds 4/6/9/14 had wrong expectations; round 25 was the first
  clean one). Confidence 65 %.

Scoring round-23's banked P1–P6 (never run): score them against this round's
nearest-instantiation numbers, flagging version drift v0.6→v0.8 (785→891
mutants).
