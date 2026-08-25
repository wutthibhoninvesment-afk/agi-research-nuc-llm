# Round 112 (NUC E) — predictions, banked BEFORE any measurement (2026-08-25 20:14 +07)

Context at banking time: NUC down again (ping 0/3, `ssh: Host is down` ×2 at 20:09/20:10,
ARP `(incomplete)` — the box is off/asleep, not mis-routed). Second consecutive E round
without the NUC. Mac-side only: E4 remainder (the lane's PREFILL rate, never measured;
round-106 M1–M10 scoring) + E5 (task-script DSL, entirely Mac-side).
Instrument: `nuc/lane_bench.py` with `nuc/fast_lane/colibri-c/olmoe` (Mac-built v1.7.0),
container `nuc/fast_lane/olmoe_merged` (6.9 GB), 8.6 GB Mac = the no-page-cache regime.
Known: decode cap 16 = 1.20 tok/s (hit 48.9 %, sys share 85 %), cap 64 = 0.30 tok/s.

| id | prediction (band + mechanism) | conf |
|---|---|---|
| R1 | Prefill, cap 16, 200-token prompt, n_new=1: **5–25 prompt-tok/s** (harness s = prefill + 1 decode step). Mechanism: if prefill gathers tokens per expert it streams ~all 64×16 experts once (6.4 GB at the Mac's ~500 MB/s page-fault path ≈ 13 s) + compute; if it walks token-by-token through a 16-entry cache it is decode-like (1.2 tok/s → 167 s, would MISS low). | 55 % |
| R2 | Monotone in prompt length: rate(800) > rate(200) > rate(50); rate(800)/rate(50) ≥ 2. Reads amortise over more tokens. | 60 % |
| R3 | sys share of every prefill case > 60 % (still read-bound). | 65 % |
| R4 | Expert-cache hit rate in the prefill cases **below** decode's 48.9 % (20–45 %): batched prefill touches nearly every expert per layer, cache 16/64. (Hit ≥ 48.9 % would say prefill is token-serial.) | 55 % |
| R5 | Peak RSS ≤ 2.7 GB in every case (cap 16 cache 0.4 GB + dense). | 70 % |
| R6 | 200-token repeat within ±15 % of the first 200-token case (no other load). | 60 % |
| R7 | Break-even prompt length where a lane turn beats a qwen36 turn (60-token reply, lane decode 1.2 tok/s disk-bound, qwen36 3.3 tok/s + E1 curve): **150–600 prompt tokens**. Below it the lane's slow decode loses; above it qwen36's 0.16 s/token prefill loses. | 55 % |
| R8 | Round-106 M1–M10 ledger scored from `lane-bench-r106.jsonl` + `convert-r106.log`: **≥ 4 MISS** of the scorable ones (rounds 100/106/107 ran 40–50 % miss). | 60 % |
| R9 | E5 `nuc/taskscript/` first full test run: **≥ 1 failing test of my own** (4-round streak). | 60 % |
| R10 | E5 size: interpreter+parser+lexer 500–900 lines, tests 35–60, all green by round end; `examples/*.task` ≥ 3 runnable against the mock transport. | 55 % |
| R11 | Standing suites unchanged: nuc 74 → 90–110 (E5 tests added), whence 654 green, harness green, skill lint strict exit 0 with 15 skills (one new: the task-script skill). | 55 % |
| R12 | The E5 preflight on nuc-mini tiers (micro 338 tok / mini 600 tok, 60-token reply) projects qwen36 turns of 55–65 s / 95–115 s (from the E1 curve) — deterministic, listed to pin what the DSL must refuse under a 60 s budget: micro fits only when the budget ≥ 60 s; mini never. | — |

Falsification: range predictions miss outside the band; R2/R4/R9 are yes/no. NUC-side
predictions from rounds 100 (P4, P10) and 106 (NUC lane decode) roll again.
