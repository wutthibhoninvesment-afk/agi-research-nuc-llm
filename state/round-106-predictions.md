# Round 106 — predictions BEFORE measuring (banked 2026-08-25 ~14:55 +07)

Track E, mission **E4 — fast lane feasibility**, continuation of round 100 (which
measured bandwidth, converted the container, started the transfer, and died
without a knowledge file). NUC is DOWN this round (ping 0/3, `ssh: Host is down`
twice) — every measurement below is Mac-side (M-series, 8 GB RAM, Python 3.9.6,
libomp, `nuc/fast_lane/colibri-c/olmoe` = Mac-built v1.7.0 engine).

Context held, not predicted:
- Round-100 facts (from its transcript): NUC→HF 66.7 / 43.1 MB/s (shard 1),
  15.9 (shard 2), 8.7–11.6 (shard 3); Mac→HF 65.5 / 9.2 MB/s (shards 1/3);
  container 7,420,160,000 B; conversion 218.5 s wall, 3.96 GB peak RSS;
  "Paris" at cap 64; CHAT decode 4.6 tok/s @cap 16 (99 tok / 21.5 s),
  2.29 @cap 64 (199 tok / 87 s, 54.9 s sys of 85.9 s real); first `test_fast_lane`
  run 1 failed (E1-curve band), then 56 green; transfer 31.5 MB/s at 0.26 GB,
  died at 1.088 GB.
- Planner on measured NUC facts (deterministic, run today, NOT a prediction):
  qwen36 footprint 36.01 GB = 31.81 resident + 4.20 swapped; no-lane
  stop-swapping cap 204; lane cap 16 → qwen36 cap 143; lane 64 → cap 75.
- `ref_olmoe_real.json` harness mode prints Speed, expert-cache hit rate, PEAK RSS;
  a custom ref with N dummy continuation ids gives an N-token timed greedy decode.
- md5s from round 100: model-00000 65b9a2c6e92d6ed447d0bbcd7ea78948,
  model-00017 91e23cd1eec5df103c5320689ec16793.

| # | Metric | Prediction (range) | Basis | Conf. |
|---|---|---|---|---|
| M1 | Re-converted container: byte-identical (both md5s equal, size 7,420,160,000 B) | **yes** | row-quantisation in torch is deterministic on CPU; same script md5 d8c2f76c… | 75 % |
| M2 | Conversion wall incl. download / peak RSS | **3–8 min** / **< 4.5 GB** | 218 s last time; HF xet parallel fetch; 8 GB Mac | 65 % |
| M3 | Mac→HF 25-s single stream: shard 1 / shard 3 | **40–70** / **6–15 MB/s** | 65.5 / 9.2 yesterday; per-object CDN rates | 60 % |
| M4 | Ref-harness greedy decode, 200 new tokens, warm page cache: cap 16 / cap 64 | **3.5–5.5** / **1.5–3.0 tok/s** (cap 64 SLOWER) | 4.6 / 2.29 CHAT-mode yesterday; 8 GB Mac cannot hold 3.5 GB RSS + 7.4 GB container | 60 % |
| M5 | Expert-cache hit rate reported by the harness: cap 16 / cap 64 | **35–55 %** / **≥ 95 %** | uniform-routing floor 25 % at cap 16 (16/64); LRU locality adds; cap 64 = every expert resident after warm-up | 55 % |
| M6 | `EXPERT_DROP=1` vs `0` decode ratio at cap 16 | **0.6–1.05** | page cache is already ineffective on this Mac, so dropping pages costs little | 50 % |
| M7 | `sys` share of wall (`/usr/bin/time -l`): cap 64 / cap 16 | **> 50 %** / **< 40 %** | 64 % at cap 64 yesterday = page-fault bound; cap 16 RSS 2 GB leaves cache room | 55 % |
| M8 | Prefill rate, ref harness, ~200-token prompt, 1 new token, cap 16 | **10–30 tok/s** | batched prefill touches ~all experts once per layer (64×16×6.3 MB = 6.4 GB read at ~1 GB/s eff.) + compute | 50 % |
| M9 | New/changed offline tests, first run | **≥ 1 failure** | rounds 100 and 105 both failed first run; 3-clean streak ended | 60 % |
| M10 | Suite total after this round (`nuc/tests`, venv) | **70–85 passed** (57 now) | ~15–25 tests for the hand-off/plan/ref-json code | 55 % |

Falsification: range predictions miss when the measured value is outside;
M1/M9 are yes/no. NUC-side E4 predictions from round 100 that can't be scored
this round (P4 during-transfer TTFT, P10 lane decode on the NUC) roll to the
next E round with the hand-off script.

Rules for the round: no NUC contact after the two failed SSH attempts (recorded);
Mac-side writes only under `nuc/`, `state/`, `knowledge/`, `skills/`, `/tmp`.
