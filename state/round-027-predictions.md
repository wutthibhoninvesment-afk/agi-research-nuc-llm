# Round 027 predictions — skills(B) — banked BEFORE building/measuring

Written after the inheritance audit (run.py reconstruction, 465+284+88 green)
and BEFORE any trigger_eval v4 code or live probe. Scoring rules: computed-by-me
quantities get narrow bands; machine-behavior quantities get explicit
wide bands (round-22 rule).

## Instrument / live-probe predictions

- **P1 — canary establishment (sonnet).** fmk-near, native, sonnet, ×6:
  fired-at-all 6/6. (Sonnet has been the stable instrument, 97–100% across
  rounds 8/15/21; fmk-near specifically has never missed on sonnet.)
  Band to freeze if it holds: ≥3/4 on future ×4 runs.
- **P2 — canary establishment (haiku).** fmk-near, native, haiku, ×6:
  fired-at-all 2–4 of 6. (Round-21 saw fmk collapse on haiku far cases
  (1/12 exact) with the host population drifted; near cases historically
  stronger; no same-day haiku baseline exists, so wide band.)
- **P3 — sonnet full rate run.** All 39 trigger cases ×2 (78 probes):
  aggregate exact ≥95%; negatives false-fire 0/14; at most 2 distinct
  cases show any miss across their repeats.
- **P4 — the gte-far/acb haiku question (backlog #3/#4).** Subset
  {gte-near,mid,far, acb-near,mid,far, neg-2, neg-5} ×6 on haiku:
  (a) gte-far fires gte in 2–4 of 6 (the 25–75% prior band holds);
  (b) acb false-fires alongside on gte-far in ≥2 of 6 (the applicability
  gate still leaks under gte's cache/history vocabulary);
  (c) on acb-far, the host `claude-api` skill fires in ≥1 of 6 runs
  (round-21 displacement repeats).
- **P5 — paired suppression re-probe.** sa-far ×4 per arm (plain vs the 5
  adversarial siblings staged), sonnet: gap ≤1 fire (round-21's
  description cure holds; the new --paired mode should report "ok").
- **P8 — body re-probe after SKILL.md body edit.** body-sa + body-saref
  ×2 each, sonnet: trigger 4/4; saref reads the reference in 2/2;
  body-sa reads it in 0/2 (necessity law holds).

## Process / artifact predictions

- **P6 — first-run failures.** Zero of my new offline tests fail on their
  first run (betting WITH the moved base rate after two clean rounds;
  the differential-helper + write-tests-with-feature discipline is real).
- **P7 — cost.** Total live probe spend this round $4–9.
- **P9 — offline suite size.** trigger_eval+skill_lint offline tests grow
  88 → 110–135.

## Amendments (added before the relevant measurement, if any)
(none yet)
