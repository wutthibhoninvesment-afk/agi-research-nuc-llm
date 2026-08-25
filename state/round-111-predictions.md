# Round 111 (skills B) — predictions, banked BEFORE any probe (2026-08-25 20:05)

Instrument: trigger_eval v4.1 → v4.2 (this round), `claude -p` sonnet/haiku, host = this Mac.
Inheritance facts at banking time: 14 skills (cml r106, acg r109 shipped UNPROBED); 59 trigger
cases (8 new) + 13 body cases (2 new); strict lint exit 1 (gte body 483 lines, B002);
last clean strict baseline = round-105-strict-full.json (51 cases ×2, 100 % exact).

| id | prediction (band + mechanism) |
|---|---|
| P1 | Canary, all 4 sentinels: sonnet default 4/4, sonnet strict 4/4, haiku default 4–6/6, haiku strict 4–6/6; exit 0. (r105: 4/4, 6/6, 4/4, 6/6 — sonnet sits at N/N; haiku band is wide by design.) |
| P2 | Strict full run 59 cases ×2 (118 probes) sonnet: exact ≥ 95 %; negatives 0/24; ≤ 2 distinct cases with a miss; errors 0–2; vs round-105-strict-full: ≤ 1 REGRESSED, exactly 8 `new`, 0 `dropped`. Cost $4–6. |
| P2b | The 8 new cases: cml-near/mid/far fired 2/2 each, exact ≥ 5/6 probes; acg-near/mid 2/2 exact; **acg-far exact ≤ 1/2** with `fuzz-mutate-kill-loop` co-firing ("kill-stage results … failed at steps 1–3" is fmk's live-campaign vocabulary); cml-neg/acg-neg 0 fires. |
| P3 | Body ×2: body-cml fired 2/2, evidence ≥ 4/5 both; body-acg fired 2/2, evidence 4/4 both (acg markers are near-generic — "safe/retries/nudge" — so this measures competence as much as following; confound recorded). |
| P4 | Haiku strict, gte/tli subset ×6 BEFORE the gte edit (gte-near/mid/far, tli-near/mid/far, multi-2 = 42 probes): gte-near fires gte ≤ 2/6 and tli ≥ 4/6 (r105 default protocol: 1/6 vs 5/6); gte-mid, gte-far fire gte ≥ 4/6; tli-near/mid/far fire tli ≥ 5/6; multi-2 exact ≤ 2/6. |
| P5 | AFTER the symptom-first gte rewrite with a NOT-for naming tli's territory, same-day haiku ×6 with `--baseline` = the P4 run: gte-near fires gte ≥ 4/6 (verdict IMPROVED); gte-mid/far stay ≥ 4/6 (no REGRESSED); tli-near/mid/far no REGRESSED; tli's co-fire on gte-near does NOT rise above its pre-edit rate (naming the sibling in a NOT-for does not hand it vocabulary). Sonnet ×3 on gte-near/mid/far + tli-near/far + multi-2: 18/18 fired, ≥ 16/18 exact. |
| P6 | `--audit state/trigger-eval` before this round's full run: 12 skills `unverified` (probed only by pre-4.2 reports without description hashes), cml + acg `never`; exit 1. After the full run: 14 `probed`, exit 0 (or 1 solely from an under-floor case count, none expected: every skill has ≥ 3 positives). |
| P7 | Offline tests 131 → 145–160 (skill_lint tests unchanged). |
| P8 | ≥ 1 of my own new tests wrong on first run (4 of the last 4 skills rounds). |
| P9 | Total live cost $8–14 across ≈ 260 probes; 0–3 errored probes. |
| P10 | Re-scoring the r105-vs-r021 comparison under the new low-n rule: fmk-far (1/1 → 0/2) flips REGRESSED → `low-n`; 0–2 other rows change verdict (all to `low-n`). |
| P11 | Moving gte's "Exact commands" block into `references/commands.md`: body ≤ 450 lines, strict lint exit 0 for all 14 skills; body-gte unaffected (no files expected). |
