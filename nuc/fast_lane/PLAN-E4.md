# E4 — OLMoE-1B-7B int8 fast lane beside Qwen3.6 on pgain-nuc: feasibility plan

Rounds 100 (measurements on the NUC, 2026-08-24 15:41–16:09 UTC) + 106
(scoring, Mac-side lane measurements, transfer/hand-off tooling, this plan;
NUC unreachable on 2026-08-25). Every NUC number below carries its round-100
transcript timestamp; every Mac number is from `lane-bench-r106.jsonl`.

## 1. Bandwidth gate — PASS

NUC → HuggingFace (`allenai/OLMoE-1B-7B-0125-Instruct`, `curl -o /dev/null`,
single stream, per shard; CDN = AWS ap-southeast-1 xet-bridge, IPs 13.214/54.169/18.136):

| object | size | 30 s sample | 25 s sample | 20 s sample |
|---|---|---|---|---|
| shard 1 | 4,997,744,872 B | **66.7 MB/s** (15:48) | 43.1 MB/s (15:50) | — |
| shard 2 | 4,997,235,176 B | — | 15.9 MB/s (15:50) | — |
| shard 3 | 3,843,741,912 B | 8.7 MB/s (15:48) | 9.0 MB/s (15:50) | 11.6 MB/s (15:53) |

- Gate `> 3 MB/s sustained`: passes on every object; the *slowest* object
  clears it 2.9×. `fast_lane.py gate --min-rate 8.66 --disk-free-gb 677
  --disk-needed-gb 7.42` → `ok: true`.
- Full 13.84 GB download on the NUC at per-object rates: **12.0–14.5 min**
  (`download_time_s`: 720–872 s). Not needed: the container is converted on
  the Mac (§4), so the NUC only ever receives the 7.42 GB int8 container.
- Reference hosts are useless here: tele2 0.11–0.15 MB/s, OVH 0.19, Linode
  SGP/Tokyo 0.19–0.24, Vultr SGP 3.9 MB/s, `speed.cloudflare.com` 403
  (UA block). The link is not the bottleneck; the CDN edge is.
- Mac → HF for comparison: 65.5 / 9.2 MB/s (08-24), 33.7 / 9.1 MB/s (08-25).

## 2. Disk gate — PASS

`/work` 738 GB LV, 677 GB free (15:41); `/` 80 GB free. Container 7.42 GB
(7,416,456,839 B in 24 top-level files + `_meta/`). Margin 91×.

## 3. RAM — the real constraint (and a finding about the production engine)

Read from the worker's cgroup and `/proc` (15:59 UTC, engine idle):

| fact | value |
|---|---|
| cgroup | `user.slice/…/app.slice/qwen36-colibri.service` (a **user** unit — it exists; the "units no longer exist" notes in rounds 16/22 were a `systemctl` vs `systemctl --user` scope error) |
| `memory.current` / `memory.max` / `memory.peak` | 32,211,791,872 / 32,212,254,720 / 32,212,254,720 B — **at the ceiling** |
| `memory.swap.current` | 4,214,800,384 B (`/swap.img` 4 GB: 4,146,640 kB used) |
| `VmRSS` / `VmSwap` / `VmHWM` | 31,063,372 / 4,100,900 / 31,388,568 kB |
| `MemAvailable` | 584,028 kB; `SwapFree` 929 MB → 48 MB during a probe |
| vmstat since boot | pswpin 1,594,468 pages (6.5 GB), pswpout 6,251,936 (25.6 GB), pgmajfault 305,080 |
| TTFT probes (166-tok prompt, `max_tokens=1`) | 38.97 s (first), 24.02, 23.23 s; a probe moved 1,626 pages in / 2,066 out and 531 major faults |

**Qwen3.6 at `--cap 256` does not fit: its footprint is 36.0 GB (31.8 resident
+ 4.2 swapped) on a 31.2 GiB box.** The engine has been paging its expert
cache through a 4 GB swap file since the 08-23 deployment. This is
independent of any lane.

Cap arithmetic (`fast_lane.py plan`, expert = 1,769,472 B, 40 layers,
NVMe assumed 1500 MB/s; `rss(cap) = 36.01 GB − (256 − cap)·40·1.77 MB`):

| lane cap | lane needs | qwen36 cap | qwen36 GB | miss % (uniform / skew 0.5) | decode +s/tok | prefill +s/req |
|---|---|---|---|---|---|---|
| none (stop swapping) | 0 | **204** | 32.33 | 20 / 10 | +0.077 / +0.038 | +2.5 |
| 16 | 4.25 GB | **143** | 28.01 | 44 / 22 | +0.167 / +0.083 | +5.3 |
| 32 | 5.87 GB | 121 | 26.45 | 53 / 26 | +0.199 / +0.100 | +6.4 |
| 64 | 9.10 GB | 75 | 23.20 | 71 / 35 | +0.267 / +0.133 | +8.5 |

qwen36 decodes at 0.19–0.30 s/token (5.3→3.3 tok/s), so a cap-16 lane costs it
28–88 % more decode time per token (skew 0.5 → uniform), while the prefill
penalty (+5 s per request) is noise against 23–770 s TTFTs. **Every option,
including "no lane", requires one engine restart with a lower `--cap`** —
an operator decision, not something a round may do (E4 is planning-only).

## 4. Container: converted off-box, deterministic, validated

- `convert_olmoe_merged.py` (upstream v1.7.0, md5 d8c2f76c…) on the Mac:
  round 100 218.5 s wall / 3.96 GB peak RSS; round 106 **240.8 s / 3.67 GB**
  (`--flush-every 128`). Output 7,416,456,839 B; `model-00000` md5
  65b9a2c6e92d6ed447d0bbcd7ea78948 and `model-00017`
  91e23cd1eec5df103c5320689ec16793 **identical across the two
  conversions** — a partial remote copy can be completed from a fresh
  conversion without re-sending verified files.
- Mac-built v1.7.0 `olmoe` (clang + libomp): "What is the capital of France?
  Answer in one word." → **Paris** (cap 64, TEMP 0); "Count from 1 to 100" →
  correct 1…100 (round 100, 16:03–16:06 UTC).
- Lane measurements on the Mac (8 GB RAM: the *no-page-cache* regime, i.e.
  the NUC's regime at MemAvailable 0.6 GB): see §6.

## 5. Transfer + launch recipe (for the next E round / the operator window)

1. `python3 nuc/fast_lane.py handoff nuc/fast_lane/olmoe_merged jab@192.168.1.37
   '~/nuc-research/models/olmoe_merged' --key ~/.ssh/id_ed25519_nuc --md5 > /tmp/handoff.sh`
   (with `--remote-sizes` from `fast_lane_sink.py --part-size` per file when
   resuming). The script: host guard → stage sink → per-file `cat|ssh sink`
   (fdatasync + fadvise DONTNEED every 256 MB, so the copy never grows the
   page cache under the saturated engine) → `md5sum` on the box vs local
   digests → one line in `/work/logs/nuc-fast-lane.md`. Expected 4–5 min at
   the measured 27–31.5 MB/s Mac→NUC Wi-Fi rate. Round 100's 1.09 GB
   `olmoe_merged.tar.part` on the NUC is unusable (tar headers differ) —
   delete it under `~/nuc-research/models/`.
2. Launch (only after the operator restarts qwen36 at cap ≤ 143 — §3):
   `cd /work/src/colibri-v170/c && SNAP=$HOME/nuc-research/models/olmoe_merged
   EXPERT_DROP=1 python3 coli serve --host 127.0.0.1 --port 8090 --model-id olmoe
   --cap 16 --ctx 2048` (port 8090: never 8000/8080/8001). `EXPERT_DROP=1`
   keeps the lane from competing with qwen36 for the page cache it does not
   have anyway. OLMoE returns HTTP 400 on `tools` (support matrix) and has
   CTX ≤ 4096, no thinking — the lane serves tool-free turns (classify,
   summarise, route, draft) via `/v1/chat/completions`.
3. Measure with `nuc/bench.py` against :8090 (predictions in the round file
   first), then decide the split: nuc-mini agent turns stay on :8080/qwen36,
   sub-1k-token tool-free turns go to :8090.

## 6. Lane measurements (Mac, no-page-cache regime) and NUC projection

Filled from `lane-bench-r106.jsonl` — see the table appended below and
`knowledge/round-106-nuc-e4-fast-lane-inheritance.md` §4 for the scoring.

### 6a. Decode (round 106, `lane-bench-r106.jsonl`, Mac 8.6 GB, cap 16 unless noted)

| case | cap | env | new tok | tok/s | hit % | peak RSS GB | sys share |
|---|---|---|---|---|---|---|---|
| first16 (warm-up, contaminated by 3 `find /` jobs) | 16 | — | 200 | 1.16 | 48.9 | 2.56 | 87 % |
| cap=16 | 16 | — | 200 | **1.20** | 48.9 | 2.58 | 85 % |
| cap=64 | 64 | — | 200 | **0.30** | 96.3 | 2.57 | 88 % |
| drop16 | 16 | EXPERT_DROP=1 | 200 | 0.73 | 48.9 | 2.45 | 86 % |
| omp4 | 16 | OMP_NUM_THREADS=4 | 200 | 0.71 | 48.9 | 2.31 | 90 % |

Decode is disk-bound (sys 85–90 %): 13,341 misses × 6.3 MB in 166 s ≈ 506 MB/s
through the page-fault path; cap 64 is 4× *slower* because every layer's full
expert set cycles through a page cache that cannot hold the 6.9 GB container.

### 6b. Prefill (round 112, `lane-prefill-r112.jsonl`, same binary/container, `n_new=1`)

| case | prompt tok | harness s | **prompt tok/s** | hit % | lookups | peak RSS GB | user s | sys s | sys share |
|---|---|---|---|---|---|---|---|---|---|
| p50 | 50 | 7.4 | 6.7 | 45.0 | 6,400 | 2.07 | 4.0 | 4.0 | 50 % |
| p200 | 200 | 20.9 | **9.6** | 43.6 | 25,600 | 0.85 | 14.7 | 11.0 | 43 % |
| p800 | 800 | 93.0 | 8.6 | 42.1 | 102,400 | 2.10 | 73.8 | 53.1 | 42 % |
| p200b (repeat) | 200 | 24.9 | 8.0 | 43.6 | 25,600 | 2.37 | 17.7 | 14.8 | 45 % |

- Lookups = prompt × 16 layers × top-8 exactly: the expert cache is consulted
  per token in prefill too, yet 14,451 misses complete in 20.9 s (≈ 4.4 GB/s of
  expert bytes) — **prefill misses are served from the page cache, decode
  misses from disk.** Prefill walks one layer for all tokens (a working set of
  ≤ 64 experts = 400 MB that fits), decode walks all 16 layers per token
  (6.4 GB that does not). Prefill is therefore compute-bound-ish here (user >
  sys), ~8× faster than decode, and flat in prompt length (6.7 → 9.6 → 8.6
  tok/s: the 800-token case is *not* faster than 200 — prediction R2 missed).
- The lane's prefill is only **1.7–1.9×** qwen36's marginal 5.1 tok/s while its
  decode is **2.75× slower** than qwen36's 3.3 tok/s in this regime.

### 6c. Break-even and the decision (`fast_lane.breakeven_prompt_tokens`, E1 curve for qwen36)

| lane rates (prefill / decode tok/s) | break-even prompt length, 60-token reply | 200-tok prompt: lane vs qwen36 | 600 tok | nuc-mini micro (338 tok, 20-tok reply) |
|---|---|---|---|---|
| 9.0 / 1.2 (Mac, measured) | **675 tokens** | 73 s vs 52 s | 117 vs 114 s | 55 vs 61 s |
| 8.0 / 1.2 (Mac repeat) | 935 | 76 vs 52 | 126 vs 114 | 59 vs 61 |
| 9.0 / 3.6 (NUC NVMe projection: 1500 MB/s ÷ 411 MB/token at miss 0.511) | 0 (wins everywhere) | 39 vs 52 | 84 vs 114 | 44 vs 61 |
| 5.0 / 1.2 (if the i5-7260U prefills at half the Mac's rate) | never | 90 vs 52 | 170 vs 114 | 85 vs 61 |

**Decision (E4 feasibility, Mac-side evidence):** bandwidth and disk pass (§1–2);
RAM does not (§3) — and even with RAM found by lowering qwen36's cap, the lane
is a *fast* lane only for prompts above ~700 tokens with short replies unless
its decode leaves the disk-bound regime, which needs ~7 GB of page cache the box
does not have (qwen36 cap ≈ 75, +0.27 s/token on every qwen36 decode). The
program's better lever for the same goal is E3's prefix-reuse patch (48 s →
8–17 s per nuc-mini turn, zero RAM). Recommendation to the operator: restart
qwen36 at `--cap 204` (stop the swapping, §3) and run the E3 A/B in that
window; treat the OLMoE lane as a classify/route helper for long-prompt
short-reply tasks only, and stage it (§5) only if the NVMe projection (3.6
tok/s decode) survives a 5-minute measurement on the box. The task-script DSL
(E5, `nuc/taskscript/`) encodes exactly this routing: `examples/triage.errand`
prices each task against the budget before any request.
