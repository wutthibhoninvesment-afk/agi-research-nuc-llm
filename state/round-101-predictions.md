# Round 101 — predictions BEFORE measuring (banked 2026-08-24 ~23:25)

Track D (SWE-loop). Rounds 32–99 were driver 429 no-ops; the last real D
round was 29, which died after its mutation run (log + JSON exist, never
scored). Context held, not predicted:
- Whence v0.9 (round 30) `interp.py` = 2227 lines → **1056 mutants**
  (ifneg 344, cmp 234, const 229, arith 99, bool 78, not 72); v0.8 had 891.
- Round-29 v0.8 baseline, read for the first time this round: 891 mutants,
  841 killed + 8 timeouts (counted killed) = **95.3 %**, 42 survivors,
  wall 2250 s at 5 workers.
- Whence suite: 506 tests, 48 s serial on an idle machine (6 cores, 8 GB).
- Nested `claude -p` auth VERIFIED (sonnet-5, $0.045/probe, 3.9 s).
- Harness suite: round 31 reported 298 green + 1 red (`test_swe_campaign`
  selection bug); re-run pending as I write this.

- **P1 (v0.9 mutation baseline, 1056 mutants, full suite, 5 workers, 240 s):**
  score **93–96 %**, survivors **45–75**. Round 29 beat its own 89–93 %
  prediction with 95.3 %; direct mode adds 165 mutants covered by a three-way
  differential, but every fast-path layer breeds equivalents. Conf 65 %.
- **P2 (wall):** **30–55 min** (killed mutants stop at first failure in a few
  seconds; survivors pay the full 48 s+ under load). Conf 60 %.
- **P3 (timeouts):** 3–12 timeouts under load; serial recheck flips ≥1 of
  them. Conf 55 %.
- **P4 (corpus killers: 300 random + examples + round-29 extra programs):**
  kills **25–45 %** of survivors. Conf 55 %.
- **P5 (NEW coverage triage):** of the survivors, **30–60 %** sit on lines the
  suite never executes (pure test gaps, not equivalents). Conf 50 %. AND the
  corpus kill rate on *uncovered* survivors is HIGHER than on covered
  survivors (covered-but-survived skews equivalent). Conf 60 %.
- **P6 (live kill, sonnet, 8 sampled `no_killer` survivors, 20 steps):** kills
  **40–70 %** (3–6 of 8); ≥1 `equivalent` verdict; ≥1 claimed-equivalent is
  genuinely equivalent on my reading of the code. Conf 55 %.
- **P7 (live review, sonnet, interp.py, 30 steps, region tools):**
  `oracle_check` called ≥5 times; a JSON answer is emitted; claims 1–4,
  confirmed 0–1, precision ≤50 %. Conf 60 %.
- **P8 (NEW repair bench, sonnet, 6 killed mutants injected as bugs; the
  model sees the failing pytest output + region tools + edit_file + pytest in
  a scratch copy, 25 steps):** suite-green rate **50–83 %** (3–5 of 6);
  exact-revert rate **33–67 %**; ≥1 run is green-but-not-exact (an
  alternative or over-broad fix); mean cost ≤ **$0.60** per attempt. Conf 50 %.
- **P9 (pins):** 100 % of corpus- and model-found killers re-kill their mutant
  when run as the pinned test file alone. Conf 70 %.
- **P10 (standing campaigns, AFTER mutation to avoid load skew):** host fuzz
  2 × 400 → 0 crash signatures (75 %); oracle fuzz 2 × 300 → 0 findings
  (70 %); guest differential 1 × 300 → 0 divergences (75 %).
- **P11 (cost):** whole live lane (kills + review + repairs) ≤ **$12**
  CLI-reported. Conf 60 %.
- **P12 (process):** ≥1 of my own new tests fails on first run. Conf 60 %.

Round-29's banked P1–P10 are scored in the round file against the round-29
log (P1–P3) and this round's nearest instantiation (P4–P10), flagging the
v0.8→v0.9 drift (891→1056 mutants).
