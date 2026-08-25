# Round 100 — predictions BEFORE measuring (banked 2026-08-24 ~22:55 Mac / 15:55 UTC NUC)

Track E, mission **E4 — fast lane feasibility** (OLMoE-1B-7B int8 lane).

Context held, not predicted (read-only facts gathered before this file):
- NUC: i5-7260U 2c/4t, 31.2 GiB RAM, `/work` 677 GB free (738 GB LV, 4 % used),
  only NIC with an address is **Wi-Fi `wlp58s0`** (192.168.1.42/24).
- Production: user units `qwen36-colibri.service` (`MemoryMax=30G`, RSS 29.8 GiB,
  worker PID 14192) + `qwen36-toolproxy.service`; `MemAvailable` 584 MB, swap
  3.2 GB of 4 GB used; engine idle (`/health` active 0, admitted 28/28).
- OLMoE history on this box: converted 2026-08-05 (v1.4.0 `olmoe` binary + custom
  adapter on :8000), quality-probed 2026-08-17 (2.1 s trivia; 29.7 s / 66.7 s for
  200/400-token answers; RoPE answer "confidently wrong ×3"), adapter retired
  2026-08-18, container deleted with the 2026-08-23 qwen36 deployment.
- colibri v1.7.0: `coli serve` now speaks SERVE to `olmoe.c` (1530 lines vs 1193 in
  v1.4.0), `render_chat_olmoe` rejects `tools` with HTTP 400, no thinking, CTX ≤ 4096,
  no `kv_prefix.h` include (no prefix reuse). Upstream bench: Apple M3 base, cap 16 →
  3.69–4.18 tok/s, RSS 1.5–1.8 GB. `chat_olmoe.sh` cap 64 ⇒ ~7.8 GB peak.
- HF shards (HEAD): 4,997,744,872 + 4,997,235,176 + 3,843,741,912 B = **13.84 GB**.
- qwen36 container header: expert = 1,572,864 B (U8 merged) + 196,608 B (F32 gs64
  scales) = **1,769,472 B/expert**, 256 × 40 = 18.119 GB; dense 2.862 GB; embed 2.034 GB.
  Journal: "resident weights loaded … RSS after load: 9.25 GB" (before expert cache fill).
- Mac: 8 GB RAM, 99 GB free, Wi-Fi 192.168.1.39, libomp present, `nuc/.venv` now has
  torch 2.x + numpy + safetensors + huggingface_hub.
- Historical download: GLM-5.2 int4 358 GB fetched in 1:45:50 on 2026-08-05 ⇒ **56 MB/s**
  average (interface at the time unknown).

Design being built: `nuc/fast_lane.py` (bandwidth probe parser + gate, RAM/`--cap`
planner from container geometry, lane projection, O_DIRECT-safe transfer command)
+ `nuc/tests/test_fast_lane.py`; off-NUC conversion on the Mac with the upstream
`convert_olmoe_merged.py` (md5 d8c2f76c…, copied verbatim), engine built from the
v1.7.0 tree on the Mac to validate the container, container streamed to
`~/nuc-research/models/olmoe_merged` via `ssh … dd oflag=direct`.

| # | Metric | Prediction (range) | Basis | Conf. |
|---|---|---|---|---|
| P1 | NUC→HF sustained, 30 s single stream, shard 1 (`curl -o /dev/null`) | **40 MB/s (25–60)** | 56 MB/s GLM average on 08-05; 2×2 802.11ac real-world 30–60 MB/s; ≫ 3 MB/s gate | 65 % |
| P2 | HF CDN vs Cloudflare reference (`speed.cloudflare.com`) ratio | **0.5–2.0** (link-bound, not CDN-throttled) | Wi-Fi is the bottleneck; xet-bridge CDN is fast | 70 % |
| P3 | Mac→HF sustained, 30 s | **30 MB/s (10–60)** | same Wi-Fi network, different client radio | 55 % |
| P4 | Production TTFT (134-token probe, `max_tokens=1`, :8000) DURING the O_DIRECT container transfer vs baseline | **≤ +15 %** (baseline ≈ 18–24 s) | sshd decrypt ≈ ⅓ core at 30 MB/s competes with OMP prefill on 2 cores; page cache untouched by design | 60 % |
| P5 | RAM gate: `MemAvailable` < 1 GB **and** planner cap for a cap-64 OLMoE lane (needs ≈ 8.5 GB) | cap **≈ 130 (115–145)**; cap-16 lane (≈ 2.3 GB) **≈ 220 (210–230)** | RSS(cap) = RSS(256) − (256−cap)·40·1.769 MB; 1 GB ≈ 14 slots/layer | 70 % |
| P6 | Converted container size on the Mac | **7.4 GB (6.8–7.6)** | 16 layers × 64 experts × 6,291,456 B int8 = 6.44 GB + 64·16·3·1024·4 B scales (0.2 GB) + dense bf16 ≈ 0.94 GB | 65 % |
| P7 | Conversion wall time on the Mac, excluding download | **4–15 min**; peak RSS < 4 GB with `--flush-every 128` | 6.9 B params row-quantised in torch on CPU | 55 % |
| P8 | Mac-built v1.7.0 `olmoe` (libomp) + container: "capital of France?" answered coherently (contains "Paris") | **yes**, decode **8–20 tok/s** on the Mac at cap 64 | upstream M3 3.7–4.2 tok/s at cap 16 (disk-bound); cap 64 is compute-bound on a 6-core part | 60 % |
| P9 | Mac→NUC LAN transfer of the container via `ssh … dd oflag=direct` | **25 MB/s (15–40)** ⇒ 3–8 min for 7.4 GB | Wi-Fi to Wi-Fi through the AP halves airtime | 55 % |
| P10 | NUC lane projection banked for the operator window (NOT measured this round): decode at cap 64 | **5–8 tok/s**; prefill **20–60 tok/s** | 2026-08-17 operator runs: ~200 tok in 29.7 s, ~400 tok in 66.7 s ⇒ 6–7 tok/s incl. prefill | 60 % |
| P11 | New offline suite (`test_fast_lane.py`) first run | **clean** (0 failures) | three consecutive clean first runs (rounds 25–30) | 60 % |
| P12 | Round-25/28 pattern check: the `qwen36-colibri` unit exists as a **user** unit ⇒ earlier "units no longer exist" notes were a scope error (system vs `--user`) | true | `systemctl --user list-units` shows both active | 90 % |

Falsification: a prediction misses when the measured value falls outside the
range (P1–P3, P5–P7, P9), when the sign/threshold fails (P4, P8, P11, P12).
P10 is banked for a future round and cannot hit or miss here.

Rules for the round: no request to :8001; no colibri/hermes source edits; no
engine restart (E4 is a feasibility mission — the lane is planned + staged, not
launched); writes only under `~/nuc-research`, `/work/logs`, `/tmp`.
