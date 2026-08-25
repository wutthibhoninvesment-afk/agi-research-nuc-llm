# Round 23 — predictions BEFORE measuring (banked 2026-08-24)

Written after the inheritance audit + standing checks (harness 266, whence 430,
lint clean, nested `claude -p` auth VERIFIED working) but BEFORE any mutation /
campaign / live-model result. Context I already hold and am not predicting:
round-9 mutation JSON exists (v0.4: 679 mutants, 90.43%, 456 s) — discovered
during the audit, so P1 is calibrated on it, honestly.

- **P1 (mutation baseline, v0.6 interp.py, full 430-test suite, 785 mutants,
  5 workers):** score **88–93%**, survivors **55–85**. Rationale: v0.4 scored
  90.43% at 679 mutants; since then +106 mutants land mostly in new v0.5/v0.6
  code (get/put/find, `has`, string fast path, inline dispatch) which
  test_v05/test_v06 cover directly, but fast-path duplication historically
  breeds equivalent-looking survivors. Confidence 70%.
- **P2 (corpus killers on survivors, 300 random programs + examples):** the
  random corpus kills **25–50%** of survivors; the rest are `no_killer` (hard
  core: equivalents + observability gaps). Confidence 60%.
- **P3 (live review, sonnet via ClaudeCLILLM, interp.py, 30 steps, budget
  visible per round-17's patch):** **0–1 confirmed claims**, precision **≤ 50%**
  (claims mostly plausible-but-not-reproducing; oracles dry after ~4k fuzz
  programs). Also: with the round-17 budget note in the prompt, the model DOES
  run oracle_check ≥ 5 times this time. Confidence 65%.
- **P4 (live kill, sonnet on ≥6 sampled no_killer survivors):** kills
  **40–70%** of attempted; ≥1 `equivalent` verdict, and at least one claimed
  equivalent is genuinely equivalent (const/cache-key mutants often are).
  Confidence 60%.
- **P5 (standing campaigns, run AFTER mutation to avoid load-skew):** host fuzz
  2 seeds × 400 → **0 crash signatures** (conf 75%); guest-differential 2 seeds
  × 400 → **0 divergence signatures** (conf 80%), timeouts < 3% (conf 70%).
- **P6 (cost):** entire live lane (review + kills + any fix) ≤ **$8** CLI-reported.

Scoring round-17's banked P2–P4 (never run): score them against this round's
nearest-instantiation numbers, flagging version drift v0.5→v0.6.
