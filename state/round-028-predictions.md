# Round 028 predictions — NUC-integration(E), mission E3 — banked BEFORE reading the serve path

Written after: `grep -n kv|slot|prefix` over qwen36.c + openai_server.py (greps only,
no code regions read yet), `ls` of the C dir (saw `kv_prefix.h`, `kv_persist.h`),
`ps` on the NUC (engine `coli serve … --cap 256 --ctx 32768 --max-queue 2`, no
`--kv-slots` flag). Rules (round-22): computed-by-me quantities → narrow bands;
machine-state quantities → explicit preconditions; code-reading claims → stated
confidence.

## Code-reading predictions (scored by reading, no NUC load)

- **P1 — `--kv-slots` is inert for qwen36.** The qwen36 worker parses the
  SUBMIT slot and discards it (`(void)slot;` at :2196); the family registry caps
  qwen36 at `max_kv_slots = 1`, so `--kv-slots 2` on this deployment would be
  rejected at startup, not silently ignored. Confidence 70 % on the registry cap
  (the alternative: registry allows >1 and the server routes conversations to
  slots the worker never honours — a silent no-op).
  → **HIT.** `family_registry.py:552` `FamilyLimits(8192, 262144, 1024, 8192, 1, 8, "Q36_MAXT")`
  (max_kv_slots = 1); `coli:1472` exits "supports at most 1 KV slot(s)".
- **P2 — the prefix machinery exists but only for DeepSeek V4.** `kv_prefix.h`
  and `kv_persist.h` are included by `deepseek_v4.c` and NOT by `qwen36.c`;
  the server's "prefix hint (optional 8th header field)" is emitted only when the
  family is DSV4. Confidence 80 %.
  → **MISS (partial).** qwen36 indeed includes neither and the hint is DSV4-only,
  but `kv_prefix.h` is a SHARED header already wired into `kimi_k3.c` and
  `inkling.c` too (and `kv_persist.h` belongs to colibri.c/GLM, not DSV4).
  qwen36 is the only non-GLM engine without prefix reuse — a stronger finding
  than predicted, and one `grep -l kv_prefix.h *.c` before banking would have shown.
- **P3 — per-request KV reset is unconditional in qwen36.** Confidence 90 %.
  → **HIT.** `serve_one`: `reset_recurrent(m); ensure_kv(m); m->kv_len = 0;`, no compare anywhere.
- **P4 — Qwen3.6-35B-A3B is a HYBRID; K/V fp32; band 32–256 KB/token.** Confidence 85 %.
  → **HIT.** 40 layers = 30 Gated DeltaNet + 10 Gated Attention (`i % 4 == 3`),
  `float **K, **V`, 2 KV heads × 256 dim → **40,960 B/token** (the source comment
  says "40 KB/token"). DeltaNet state per layer 32×128×128 f32 = 2 MB + conv ring
  8192×3 f32 — a full snapshot is **65.9 MB**, context-independent.
- **P5 — DSV4's design is a single shared-prefix checkpoint, not general LCP.** Confidence 75 %.
  → **MISS.** Richer: strict continuation via `kv_prefix.h` FIRST, then an LRU of
  up to 8 checkpoints of TWO kinds (system prefix from hint/LCP plan, and
  prompt-end captures after every prefill), persisted to `<model>/.coli_ckpt/`.
  The "no general LCP" half was right (ring window cannot rewind).
- **P6 — implementation size 80–250 lines of C.**
  → **HIT (at the edge).** `qwen36-prefix-reuse.patch` = +250/−27 lines after
  the stable-boundary hint was added (+228 before it); server +73 patch lines
  (code + test). The unit test (200 lines) is not counted.

## Live-probe predictions

- **P7 — `/health` reports `kv_slots: 1`; `cache_slot: 1` → 400 "between 0 and 0" without engine work.** Confidence 90 %.
  → **HIT.** Both exact; the 400 took 3.0 ms.
- **P8 — warm repeat ratio 0.85–1.02 (no KV component).**
  → **HIT.** 339-token prompt ×3: TTFT 48.33 / 47.58 / 47.57 s → 3rd/2nd = **1.000**.
  Cold branch NOT triggered: after ~2 h idle the first request cost only +0.75 s.
  Round 22's "idle-cold penalty ≈45–50 s" did not reproduce; re-diagnosis: that
  turn (10:47) was the first request after the engine RESTART at 10:34 — a
  post-restart page-cache warm-up, not an idle effect.

## Projection predictions

- **P9 — nuc-mini turn with a persisted prefix: 20–35 s, speedup 3.5–6×.**
  → **MISS (low) on the band, HIT on the ratio.** Modelled turns 2/3/4 prefill
  14.8 / 7.7 / 17.3 s (+~3–10 s decode) → ~18 / ~11 / ~27 s: two of three below
  the band because the real conversation deltas are 30–96 tokens, not the 100
  I assumed, and the stable-boundary snapshot reuses the reply framing too.
  Speedup vs measured warm turn (102 s): 5.7× (in band). Counted as MISS.
- **P10 — Hermes steady-state 2–5 min/turn; decode at 26k KV 1.5–2.8 tok/s.**
  → **MISS on decode.** A linear extrapolation of a hyperbolic quantity: the E1
  series in seconds-per-token is 0.189/0.209/0.301 @ 0.3k/1k/4k ≈ +0.030 s/tok
  per 1k → ~0.98 s/tok ≈ **1.0 tok/s** at 26.5k. Turn time then ≈ 18 s prefill
  + 200 s decode ≈ 3.6 min — inside 2–5 min, so the headline claim ("impossible
  → merely slow") stands, but decode, not prefill, is the Hermes ceiling.
  Counted as MISS (the computed sub-band was wrong).

## Process predictions

- **P11 — no restarts, no writes outside allowed paths.** → **HIT.** Written:
  `~/nuc-research/{kv_probe.py,probe_p1.json,kvreuse/**}`, `/tmp/r28_probe.*`,
  `/work/logs/nuc-kv-reuse.md`. Port 8001 untouched.
- **P12 — ≥8 of 12 HIT.** → **MISS.** Ledger: **7 HIT / 5 MISS**
  (P1 P3 P4 P6 P7 P8 P11 hit; P2 P5 P9 P10 P12 miss).

## Miss pattern
Two clusters: (a) under-predicting prior art already in the tree (P2, P5) —
rule: `grep -l` the header's includers BEFORE banking a "only X uses it" claim;
(b) computed bands built on the wrong model (P9 assumed 100-token deltas, P10
extrapolated tok/s linearly) — rule: extrapolate in the linear domain
(seconds-per-token, not tokens-per-second) and compute deltas from the real
rendered conversation, which was one function call away.

## Amendments (added before the relevant measurement, if any)
(none)
