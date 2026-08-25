# Round 17 — predictions BEFORE measuring (banked 2026-08-24)

Written after building the guest-differential oracle + tests but BEFORE
reading any campaign/mutation/live-run result.

- **P1 (guest fuzz):** 2 seeds x 400 guest-safe programs find **>= 1 real
  host-vs-guest divergence signature**. Rationale: the round-14 hand corpus
  was 50 programs; random composition of index/field/miss-argument/closure
  corners should reach something the corpus did not. Confidence 60%.
- **P2 (mutation baseline, v0.5 interp.py, full suite):** score in
  **80–90%** (round 5 measured 82.4% on v0.2 with a much smaller suite;
  both the code and the suite have grown; fuzz-regression pins should kill
  more arithmetic mutants).
- **P3 (live review, sonnet via ClaudeCLILLM on interp.py):** **0–1
  confirmed claims**, precision <= 50%. Rationale: the four self-oracles
  are dry after thousands of fuzz programs; a fresh model reading code
  should mostly produce plausible-but-unreproducible claims.
- **P4 (live kill, sonnet on surviving mutants):** kills **>= 50%** of
  attempted survivors (the mutant_diff tool gives it exact feedback;
  round-8-style iterate-until-fired loops usually converge).
- **P5 (guest campaign hygiene):** timeout rate < 5% of programs (small
  programs; 8 s budget; no host-scale stress templates).

Score these in knowledge/round-017-*.md with HIT/MISS per item.
