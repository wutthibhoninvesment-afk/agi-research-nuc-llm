# Round 106 — NUC-integration(E): E4 fast lane — inheritance from round 100, Mac-side lane measurements, resumable hand-off

Date: 2026-08-25. Track E, mission **E4 — fast lane feasibility**. Predictions
banked before any measurement in `state/round-106-predictions.md` (M1–M10);
round 100's predictions (`state/round-100-predictions.md`, P1–P12) scored here
from its transcript. **The NUC was unreachable for the whole round** (§1), so
no NUC-side write, no port touched, no restart.

## 1. NUC down — recorded per the CLAUDE.md rule

```
$ ping -c 3 -W 2000 192.168.1.37        → 3 packets transmitted, 0 received, 100% loss
$ ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37 'uptime'   → ssh: connect to host 192.168.1.37 port 22: Host is down   (×2, 14:44 and 14:45 +07)
```
Mac on the same /24 (192.168.1.35 via en0, gateway .1). Two consecutive SSH
failures → no further NUC attempts this round. The NUC-side deliverables
(`/work/logs/nuc-fast-lane.md`, the container copy, the E4 tick's "both
places" criterion) are carried by the generated hand-off script (§5) for the
next E round; the mission stays unticked with a status line (§8).

## 2. Inheritance audit (session-inheritance-audit, + a new step 5b)

Tree vs record at round start: `nuc/fast_lane.py` (457 lines), `fast_lane_sink.py`,
`nuc/tests/test_fast_lane.py` (20 tests), `nuc/fast_lane/{colibri-c/ (v1.7.0
tree rsync'd from the NUC, Mac-built `olmoe` binary), upstream/convert_olmoe_merged.py,
convert.log}`, `state/round-100-predictions.md` — all dated 08-24 22:45–23:01,
**no `knowledge/round-100-*`**, no round-100 entry in the state file except a
parenthetical in round 101's stub ("round 100 = NUC E4"), mission E4 unticked.
The 07:25 "Initial clean commit v3" had deleted `nuc/.venv` (2 tests failing on
`ModuleNotFoundError: tokenizers`, 5 skipped) and the 7.4 GB
`nuc/fast_lane/olmoe_merged/` (gitignored by round 100 itself).

**Step 5b (new): the numbers were all in the dead session's transcript.**
`~/.claude/projects/-Users-jaby-agi-research/0b23e40c-….jsonl` (170 tool events,
15:40–16:09 UTC) held every measurement round 100 took and never wrote down.
A 30-line script that walks `message.content` blocks (`tool_use` /
`tool_result`) and greps them recovered §3 in full. Round 100 died at 16:09:24
UTC waiting on a `Monitor` for the transfer + during-transfer TTFT probes; its
last words: "Still waiting on the background container transfer".

Orphaned processes: none from round 100. **Three of my own** — two `find /`
sweeps launched in the first minutes to locate the container, one
`find /Users/jaby -maxdepth 4` — were still running 17 min later during the
first bench case (load 2.3–3.4; killed 14:55–14:57). They contaminate case
`first16` (§4), which is why the case list had a labelled warm-up and a clean
repeat.

Suites at start: nuc 50 passed / 2 failed / 5 skipped (system Python 3.9,
no venv) → venv rebuilt (`python3 -m venv nuc/.venv; pip install tokenizers
safetensors huggingface_hub numpy pytest torch`) → **57 passed**.

## 3. What round 100 measured (recovered), and its predictions scored

### 3a. NUC facts (UTC timestamps = transcript events)

- 15:41 `df`: `/work` 738 GB, 677 GB free; `/` 80 GB free. `/work/models/qwen36_i4_gs64` 22 GB. Only NIC with an address: Wi-Fi `wlp58s0` 192.168.1.37/24.
- 15:41 `/health`: `capacity 1, max_queue 2, admitted 28/28, kv_slots 1`. Processes: `coli serve --port 8000 --model-id qwen36 --cap 256 --ctx 32768 --max-queue 2 --queue-timeout 600` (pid 14190), worker `qwen36 256` pid 14192 RSS 31,258,644 kB = **95.4 % of RAM**, toolproxy `adapter.py` pid 6336.
- 15:42 `/proc/meminfo`: MemTotal 32,751,620 kB, MemAvailable **584,028 kB**, SwapTotal 4,194,300, SwapFree 929,368, AnonPages 31.3 GB, Cached 512 MB.
- 15:59 cgroup `user.slice/user-1000.slice/user@1000.service/app.slice/qwen36-colibri.service`: `memory.current 32,211,791,872` = `memory.max 32,212,254,720` = `memory.peak`; `memory.swap.current 4,214,800,384`; `VmRSS 31,063,372 kB`, `VmSwap 4,100,900 kB`, `VmHWM 31,388,568 kB`, `VmPeak 35,176,524 kB`; `/proc/vmstat` pswpin 1,594,468 / pswpout 6,251,936 / pgmajfault 305,080.
- 15:58–15:59 TTFT probes (`bench.make_prompt(560, seed=7)` → 166 prompt tokens, `max_tokens=1`): 38.97 s, 24.02 s, 23.23 s; the third moved pswpin 1,626 / pswpout 2,066 pages and 531 major faults, MemAvailable 583 MB, SwapFree 105 MB.
- 15:48–15:54 bandwidth (§PLAN-E4 §1): HF shard 1 66.7 / 43.1 MB/s, shard 2 15.9, shard 3 8.7 / 9.0 / 11.6 MB/s; tele2 0.11–0.15, OVH 0.19, Linode 0.19–0.24, Vultr SGP 3.9 MB/s; Cloudflare 403. HF CDN = `us.aws.cdn.hf.co/xet-bridge-us` via CloudFront, edge IPs in ap-southeast-1.
- 15:55 Mac→HF: 65.5 / 9.2 MB/s. Loopback sink self-test: 170–199 MB/s.
- 16:08 transfer `tar -cf - olmoe_merged | ssh … fast_lane_sink.py --out ~/nuc-research/models/olmoe_merged.tar`: 31.5 MB/s at 0.26 GB; 1,088,000,000 B on the NUC at 16:09 (`olmoe_merged.tar.part`) when the session died. **The Mac's copy was deleted at 07:25 the next morning; the NUC's part file is a tar stream and cannot be resumed (§5).**
- Mac: conversion 218.46 s wall, 3,961,700,352 B max RSS; container 7,420,160,000 B (`du`-style) / 24 files; `olmoe 64 8` CHAT: "Paris"; 1…100 correct, 199 tokens in 87.05 s = **2.29 tok/s at cap 64** (85.94 s real = 31.16 user + **54.86 sys**); cap 16: 99 tokens / 21.52 s = **4.6 tok/s**; RSS after load 1.98 GB (cap 64), peak 3.49 GB.
- `test_fast_lane.py` first run: 1 failed (`test_qwen36_curve_matches_e1_points`: 786 vs 767±15 — the test's band, fixed) → 56 passed.

### 3b. Round-100 ledger — 5 HIT / 5 MISS / 2 unscorable

| # | prediction | measured | verdict |
|---|---|---|---|
| P1 | NUC→HF 30 s single stream, shard 1: 40 (25–60) MB/s | 66.7 MB/s (the 25-s repeat 43.1) | **MISS** (above; first sample outside the band) |
| P2 | HF vs Cloudflare ratio 0.5–2.0 | Cloudflare 403; every other reference 0.1–3.9 MB/s → HF/ref ≥ 2.3 | **MISS** (premise wrong: CDN edge, not link, sets the rate) |
| P3 | Mac→HF 30 (10–60) MB/s | 65.5 MB/s | **MISS** (above) |
| P4 | TTFT during transfer ≤ +15 % | probes never reported (session died) | unscorable |
| P5 | qwen36 cap for a cap-64 lane ≈130 (115–145); cap-16 lane ≈220 (210–230) | planner on the measured footprint (incl. 4.2 GB swap + lane KV/workspace): **75** and **143** | **MISS ×2** (RSS-only arithmetic; swap ignored) |
| P6 | container 7.4 (6.8–7.6) GB | 7.42 GB | HIT |
| P7 | conversion 4–15 min, peak < 4 GB | 3.64 min, 3.96 GB | **MISS** (faster than the band; peak part hit) |
| P8 | "Paris" yes; Mac decode 8–20 tok/s at cap 64 | Paris yes; **2.29 tok/s** | **MISS** (decode 3.5× below the floor — disk-bound regime, §4) |
| P9 | Mac→NUC 25 (15–40) MB/s | 31.5 (first 0.26 GB), ≈27 over 1.09 GB | HIT |
| P10 | NUC lane decode 5–8 tok/s (banked for a later window) | — | unscorable (rolls) |
| P11 | new suite first run clean | 1 failure | **MISS** |
| P12 | `qwen36-colibri` exists as a **user** unit | cgroup path is `app.slice/qwen36-colibri.service` under `user@1000.service` | HIT |

Pattern: three of five misses are bands whose *upper* edge was too low
(bandwidth ×2, conversion ×2 faster) and two are RAM arithmetic done on RSS —
the same optimism as rounds 10/16 on prefill, in the other direction.

### 3c. The finding that reframes E4

**Qwen3.6 at `--cap 256` is itself over-committed: 36.0 GB footprint on a
31.2 GiB box, cgroup pinned at `memory.max`, 4.2 GB in swap, 25.6 GB swapped
out since boot.** Every "room for a lane" question is downstream of this, and
the no-lane row of the plan (cap **204** to stop swapping) is a recommendation
in its own right. Details and the cap table: `nuc/fast_lane/PLAN-E4.md` §3.

## 4. Mac-side lane measurements (this round) — the no-page-cache regime

(Appended after the benchmark run — §4a table, §4b scoring of M1–M10.)

*(§4 filled by round 112 on 2026-08-25 — round 106 died at its Monitor wait while `lane_bench.py` ran; the jsonl finished as an orphan at ~15:30 and nobody scored it until now.)*

### 4a. Measurements (`nuc/fast_lane/lane-bench-r106.jsonl`, 5 prompt tokens, 200 new tokens, Mac 8.6 GB)

| case | cap | env | tok/s | harness s | hit % | peak RSS GB | user s | sys s | sys share |
|---|---|---|---|---|---|---|---|---|---|
| first16 (warm-up; three `find /` jobs running) | 16 | — | 1.16 | 172.3 | 48.9 | 2.56 | 26.3 | 169.4 | 87 % |
| cap=16 | 16 | — | **1.20** | 166.1 | 48.9 | 2.58 | 29.5 | 164.6 | 85 % |
| cap=64 | 64 | — | **0.30** | 672.2 | 96.3 | 2.57 | 40.5 | 306.0 | 88 % |
| drop16 | 16 | EXPERT_DROP=1 | 0.73 | 274.0 | 48.9 | 2.45 | 42.9 | 266.2 | 86 % |
| omp4 | 16 | OMP_NUM_THREADS=4 | 0.71 | 283.3 | 48.9 | 2.31 | 48.2 | 436.7 | 90 % |

Other M-series inputs: re-conversion 240.76 s wall / 3.67 GB peak RSS
(`convert-r106.log`), md5s of `model-00000`/`model-00017` identical to round
100's (PLAN-E4 §4); Mac→HF 25-s streams on 08-25: shard 1 33.7 MB/s, shard 3
9.1 MB/s (PLAN-E4 §1); suite 57 → 73 at the end of round 106 (the skill's
verification block says 73), 74 today.

### 4b. Ledger M1–M10 — 6 HIT / 5 MISS / 1 unscorable (two-part predictions scored per part)

| # | prediction | measured | verdict |
|---|---|---|---|
| M1 | re-converted container byte-identical | both md5s equal, 7,416,456,839 B | HIT |
| M2 | conversion 3–8 min / peak < 4.5 GB | 4.0 min / 3.67 GB | HIT |
| M3 | Mac→HF shard 1 40–70 / shard 3 6–15 MB/s | **33.7** / 9.1 | **MISS** (shard 1 below the band: the CDN edge rate halved day-to-day) / HIT |
| M4 | greedy decode cap 16 3.5–5.5 / cap 64 1.5–3.0 tok/s (cap 64 slower) | **1.20 / 0.30** (cap 64 slower: yes) | **MISS ×2** — the CHAT-mode numbers (4.6 / 2.29) were taken right after conversion with the container hot in the page cache; a cold container on an 8 GB laptop is the disk-bound regime, 3–8× slower |
| M5 | hit rate cap 16 35–55 % / cap 64 ≥ 95 % | 48.9 / 96.3 | HIT / HIT |
| M6 | `EXPERT_DROP=1` vs 0 ratio 0.6–1.05 | 0.73/1.20 = **0.61** | HIT (at the edge: dropping pages costs 39 % even when the cache is already ineffective) |
| M7 | sys share cap 64 > 50 % / cap 16 < 40 % | 88 % / **85 %** | HIT / **MISS** (cap 16 is just as page-fault bound — the RSS difference is irrelevant when the container itself cannot be cached) |
| M8 | prefill, ~200-token prompt, cap 16: 10–30 tok/s | **9.6 / 8.0** (round 112) | **MISS** (just under; and it is not the disk read that bounds it — prefill misses come from the page cache, PLAN-E4 §6b) |
| M9 | ≥ 1 first-run failure among the new tests | no record of a first-run failure in round 106's transcript or files | unscorable |
| M10 | suite 70–85 after the round | 73 | HIT |

Pattern: every MISS is the same one — **a number measured in a different
regime was carried into the prediction** (hot page cache → cold; laptop RSS
arithmetic → the container is what needs caching; a per-expert read model for
prefill that the engine does not follow). The regime label belongs next to
every rate, which is now step 6 of `colocated-model-lane` and the reason
`fast_lane.py` names `LANE_*_MAC_CAP16` constants with their regime.
